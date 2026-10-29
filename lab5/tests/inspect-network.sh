#!/usr/bin/env bash
set -euo pipefail

WORKER=$(minikube -p lab2 kubectl -- get pods \
  -n lab3 -l app=shop-worker \
  --field-selector spec.nodeName=lab2-m02 \
  -o jsonpath='{.items[0].metadata.name}')

API_IP=$(minikube -p lab2 kubectl -- get pods \
  -n lab3 -l app=shop-api \
  --field-selector spec.nodeName=lab2 \
  -o jsonpath='{.items[0].status.podIP}')

echo "Worker: $WORKER, нода: lab2-m02"
echo "API на другой ноде: $API_IP"

SANDBOX=$(docker exec lab2-m02 crictl pods --name "$WORKER" -q)

PID=$(docker exec lab2-m02 crictl inspectp "$SANDBOX" |
  python3 -c 'import json,sys; print(json.load(sys.stdin)["info"]["pid"])')

echo
echo "=== Интерфейсы внутри network namespace worker ==="
docker exec lab2-m02 nsenter -t "$PID" -n ip -br addr

echo
echo "=== Маршруты внутри network namespace worker ==="
docker exec lab2-m02 nsenter -t "$PID" -n ip route

PEER=$(docker exec lab2-m02 nsenter -t "$PID" -n \
  ip -j link show eth0 |
  python3 -c 'import json,sys; print(json.load(sys.stdin)[0]["link_index"])')

echo
echo "=== Парный интерфейс на ноде: ifindex=$PEER ==="
docker exec lab2-m02 ip -j -d link show |
  python3 -c '
import json,sys
peer = int(sys.argv[1])
for interface in json.load(sys.stdin):
    if interface["ifindex"] == peer:
        print(json.dumps(interface, indent=2))
' "$PEER"

echo
echo "=== Прямой запрос к Pod API на другой ноде ==="
minikube -p lab2 kubectl -- exec -n lab3 "$WORKER" -- \
  python3 -c '
import requests,sys
url = "http://" + sys.argv[1] + ":8080/health"
r = requests.get(url, timeout=5)
print("URL:", url)
print("HTTP:", r.status_code)
print("Ответ:", r.text)
r.raise_for_status()
' "$API_IP"
