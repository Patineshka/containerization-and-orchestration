#!/usr/bin/env bash
set -euo pipefail

ROOT="$HOME/lab5"
K=(minikube -p lab2 kubectl --)
H=(helm upgrade shop "$ROOT/charts/shop"
   --namespace lab3
   --kube-context lab2
   -f "$ROOT/charts/shop/values-resources.yaml"
   -f "$ROOT/charts/shop/values-networking.yaml"
   -f "$ROOT/charts/shop/values-networkpolicy.yaml")

PIDS=()
RESTORE=0

cleanup() {
    if [ "$RESTORE" = 1 ]; then
        echo "=== Отключение политик ==="
        if ! "${H[@]}" --set networkPolicy.enabled=false; then
            echo "ОШИБКА: автоматическое отключение политик не удалось"
        fi
    fi
    for pid in "${PIDS[@]}"; do
        kill "$pid" 2>/dev/null || true
    done
    wait 2>/dev/null || true
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

for node in lab2 lab2-m02; do
    docker exec "$node" tcpdump --version >/dev/null

    docker exec "$node" timeout 110s \
        tcpdump -i any -nn -l -tttt \
        'tcp port 30080 or tcp port 8080' \
        > "$ROOT/reports/nodeport-packets-$node.txt" 2>&1 &
    PIDS+=("$!")
done

for pod in $("${K[@]}" get pods \
    -n kube-system -l k8s-app=cilium \
    -o jsonpath='{.items[*].metadata.name}'); do

    timeout 110s "${K[@]}" exec \
        -n kube-system "$pod" -c cilium-agent -- \
        hubble observe --follow --namespace lab3 --protocol TCP \
        > "$ROOT/reports/nodeport-hubble-$pod.txt" 2>&1 &
    PIDS+=("$!")
done

sleep 3

echo "=== Включение политик ==="
RESTORE=1
"${H[@]}" --set networkPolicy.enabled=true

sleep 3

echo "=== NodePort с Ubuntu ==="
for ip in 192.168.49.2 192.168.49.3; do
    echo "URL: http://$ip:30080/health"
    curl -i --max-time 3 "http://$ip:30080/health" || true
    echo
done

echo "=== Запросы из shop-client ==="
timeout 25s "${K[@]}" exec -i \
    -n lab3 shop-client -- \
    env DURATION_SECONDS=12 python3 -u - \
    < "$ROOT/tests/check-continuity.py" \
    > "$ROOT/reports/nodeport-packet-client.jsonl" 2>&1 || true

cat "$ROOT/reports/nodeport-packet-client.jsonl"
sleep 2
