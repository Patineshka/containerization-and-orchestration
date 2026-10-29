import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path.home() / 'lab5'
K = ['minikube', '-p', 'lab2', 'kubectl', '--']
REPORTS = ROOT / 'reports'
REPORTS.mkdir(parents=True, exist_ok=True)


def get(*args):
    return json.loads(subprocess.check_output(K + list(args) + ['-o', 'json'], text=True))


services = get('get', 'services', '-n', 'lab3')['items']
ips = {item['metadata']['name']: item['spec']['clusterIP'] for item in services}
ports = {'shop-api': 8080, 'shop-worker': 8080, 'shop-postgres-rw': 5432}
for name in ports:
    if not ips.get(name) or ips[name] == 'None':
        raise SystemExit(f'Не найден ClusterIP сервиса {name}')

# Same-role/self Service connections are not included: they are not defined
# in the target access matrix and may be routed back to the sender itself.
matrix = {
    'shop-api': [('shop-postgres-rw', 'allow'), ('shop-worker', 'deny')],
    'shop-worker': [('shop-postgres-rw', 'allow'), ('shop-api', 'deny')],
    'shop-client': [('shop-api', 'allow'), ('shop-worker', 'deny'), ('shop-postgres-rw', 'deny')],
    'shop-postgres': [('shop-api', 'deny'), ('shop-worker', 'deny')],
    'shop-outsider': [('shop-api', 'deny'), ('shop-worker', 'deny'), ('shop-postgres-rw', 'deny')],
}

sources = []
for namespace in ['lab3', 'lab5-outsider']:
    for pod in get('get', 'pods', '-n', namespace)['items']:
        role = pod['metadata'].get('labels', {}).get('app')
        if role not in matrix:
            continue
        if pod['metadata'].get('deletionTimestamp'):
            raise SystemExit('Идёт завершение Pod. Дождись окончания rollout и повтори проверку.')
        ready = any(c['type'] == 'Ready' and c['status'] == 'True'
                    for c in pod.get('status', {}).get('conditions', []))
        if not ready:
            raise SystemExit(f"Pod {pod['metadata']['name']} ещё не Ready")
        sources.append((namespace, pod['metadata']['name'], role))

missing = set(matrix) - {role for _, _, role in sources}
if missing:
    raise SystemExit('Не найдены готовые Pod: ' + ', '.join(sorted(missing)))

probe = '''
import socket, sys
try:
    with socket.create_connection((sys.argv[1], int(sys.argv[2])), timeout=3):
        pass
except socket.timeout:
    sys.exit(10)
except OSError as error:
    print(str(error), file=sys.stderr)
    sys.exit(20)
'''

rows = []
started = datetime.now(timezone.utc).isoformat()
print('Проверяем все найденные реплики; тайм-аут сам по себе ещё не является доказательством policy drop.', flush=True)
for namespace, pod, role in sorted(sources):
    for service, expected in matrix[role]:
        port = ports[service]
        ip = ips[service]
        if role == 'shop-postgres':
            # The PostgreSQL image need not contain Python. Use a bounded
            # Bash TCP open against a numeric IP so DNS cannot mimic denial.
            command = ['timeout', '4', 'bash', '-c', 'exec 3<>"/dev/tcp/$1/$2"', '_', ip, str(port)]
            timeout_code = 124
        else:
            command = ['python3', '-c', probe, ip, str(port)]
            timeout_code = 10
        result = subprocess.run(K + ['exec', '-n', namespace, pod, '--'] + command,
                                text=True, capture_output=True, timeout=20)
        actual = ('allow' if result.returncode == 0 else
                  'timeout' if result.returncode == timeout_code else 'error')
        passed = actual == ('allow' if expected == 'allow' else 'timeout')
        row = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'namespace': namespace, 'pod': pod, 'role': role,
            'destination': service, 'ip': ip, 'port': port,
            'expected': expected, 'actual': actual,
            'result': 'PASS' if passed else 'FAIL',
            'error': result.stderr.strip() if actual == 'error' else None,
        }
        rows.append(row)
        print(f"{row['result']:4} | {pod} -> {service}:{port} | ожидаемо={expected}, фактически={actual}", flush=True)

summary = {'started_utc': started, 'finished_utc': datetime.now(timezone.utc).isoformat(),
           'source_pods': len(sources), 'checks': len(rows),
           'failed': sum(row['result'] != 'PASS' for row in rows)}
(REPORTS / 'access-matrix-full.json').write_text(
    json.dumps({'summary': summary, 'checks': rows}, ensure_ascii=False, indent=2) + '\n')
lines = ['# Проверка целевой матрицы из всех реплик', '',
         '| Namespace | Pod-источник | Назначение | Ожидаемо | Фактически | Результат |',
         '|---|---|---|---|---|---|']
for row in rows:
    lines.append(f"| {row['namespace']} | {row['pod']} | {row['destination']}:{row['port']} | {row['expected']} | {row['actual']} | {row['result']} |")
lines += ['', 'Проверяются связи целевой матрицы между ролями. Соединения с собственным сервисом не включены.',
          'Назначения проверяются по ClusterIP; DNS проверен отдельно. Тайм-ауты запретов нужно сопоставить с Hubble.',
          '', f"Итого: {summary['source_pods']} Pod, {summary['checks']} проверок, ошибок: {summary['failed']}."]
(REPORTS / 'access-matrix-full.md').write_text('\n'.join(lines) + '\n')
print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
raise SystemExit(1 if summary['failed'] else 0)
