import copy
import json
import random
import subprocess
from datetime import datetime, timezone
from pathlib import Path

root = Path.home() / "lab5"
reports = root / "reports"
reports.mkdir(exist_ok=True)
stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
folder = reports / f"fault-{stamp}"
folder.mkdir()

kubectl = ["minikube", "-p", "lab2", "kubectl", "--"]
helm = [
    "helm", "upgrade", "shop", str(root / "charts/shop"),
    "--namespace", "lab3", "--kube-context", "lab2",
    "-f", str(root / "charts/shop/values-resources.yaml"),
    "-f", str(root / "charts/shop/values-networking.yaml"),
    "-f", str(root / "charts/shop/values-networkpolicy.yaml"),
]

base = json.loads(
    (root / "charts/shop/values-networkpolicy.yaml").read_text()
)
(folder / "baseline-values.json").write_text(
    json.dumps(base, ensure_ascii=False, indent=2)
)
policies = base["networkPolicy"]["ciliumPolicies"]

scenario = random.choice(["api-db", "worker-db", "client-dns"])

if scenario in ("api-db", "worker-db"):
    role = "api" if scenario == "api-db" else "worker"
    key = f"converted-allow-{role}-egress"
    changed = copy.deepcopy(policies[key])
    replacements = 0
    for rule in changed["egress"]:
        for group in rule.get("toPorts", []):
            for port in group["ports"]:
                if port["port"] == "5432":
                    port["port"] = "5433"
                    replacements += 1
    assert replacements, "Не найден порт PostgreSQL"
else:
    key = "converted-allow-dns"
    changed = copy.deepcopy(policies[key])
    replacements = 0
    for expression in changed["endpointSelector"].get("matchExpressions", []):
        if expression["key"] == "k8s:app":
            if "shop-client" in expression.get("values", []):
                expression["values"].remove("shop-client")
                replacements += 1
    assert replacements, "Не найден selector клиента в DNS-политике"

overlay = folder / "fault-values.json"
overlay.write_text(json.dumps({
    "networkPolicy": {
        "enabled": True,
        "ciliumPolicies": {key: changed},
    }
}, ensure_ascii=False, indent=2))

def apply(extra, name):
    result = subprocess.run(
        helm + extra,
        text=True, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, timeout=100,
    )
    (folder / name).write_text(result.stdout)
    print(result.stdout, flush=True)
    result.check_returncode()

probe_source = (root / "tests/check-connections.py").read_text()

def probe(namespace, target, arguments, name):
    result = subprocess.run(
        kubectl + [
            "exec", "-i", "-n", namespace, target,
            "--", "python3", "-u", "-",
        ] + arguments,
        input=probe_source, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        timeout=45,
    )
    (folder / name).write_text(result.stdout)
    print(result.stdout, flush=True)
    return result.returncode

restore_needed = False
try:
    print("=== Внесение случайной неисправности ===", flush=True)
    restore_needed = True
    apply(["-f", str(overlay)], "helm-fault.txt")

    import time
    time.sleep(5)

    print("=== Диагностика разрешённых связей ===", flush=True)
    probe("lab3", "deployment/shop-api",
          ["shop-postgres-rw", "5432", "allow"], "fault-api.txt")
    probe("lab3", "deployment/shop-worker",
          ["shop-postgres-rw", "5432", "allow"], "fault-worker.txt")
    probe("lab3", "shop-client",
          ["shop-api", "8080", "allow"], "fault-client.txt")

    pods = json.loads(subprocess.check_output(
        kubectl + [
            "get", "pods", "-n", "kube-system",
            "-l", "k8s-app=cilium", "-o", "json",
        ], text=True,
    ))
    for item in pods["items"]:
        pod = item["metadata"]["name"]
        result = subprocess.run(
            kubectl + [
                "exec", "-n", "kube-system", pod,
                "-c", "cilium-agent", "--",
                "hubble", "observe", "--since", "2m",
                "--namespace", "lab3", "--verdict", "DROPPED",
            ],
            text=True, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, timeout=30,
        )
        (folder / f"hubble-{pod}.txt").write_text(result.stdout)
        print(result.stdout, flush=True)
finally:
    if restore_needed:
        print("=== Восстановление рабочих политик ===", flush=True)
        apply(["--set", "networkPolicy.enabled=true"], "helm-restore.txt")

print("=== Повторная проверка матрицы ===", flush=True)
checks = [
    ("lab3", "deployment/shop-api", [
        "shop-postgres-rw", "5432", "allow",
        "shop-worker", "8080", "deny",
    ], "restored-api.txt"),
    ("lab3", "deployment/shop-worker", [
        "shop-postgres-rw", "5432", "allow",
        "shop-api", "8080", "deny",
    ], "restored-worker.txt"),
    ("lab3", "shop-client", [
        "shop-api", "8080", "allow",
        "shop-worker", "8080", "deny",
        "shop-postgres-rw", "5432", "deny",
    ], "restored-client.txt"),
    ("lab5-outsider", "outsider", [
        "shop-api.lab3.svc.cluster.local", "8080", "deny",
        "shop-worker.lab3.svc.cluster.local", "8080", "deny",
        "shop-postgres-rw.lab3.svc.cluster.local", "5432", "deny",
    ], "restored-outsider.txt"),
]

time.sleep(5)
failed = sum(probe(*check) != 0 for check in checks)
(folder / "scenario.txt").write_text(scenario + "\n")
print("Сценарий:", scenario)
print("Отчёты:", folder)
print("Групп проверок с ошибками после восстановления:", failed)
raise SystemExit(1 if failed else 0)
