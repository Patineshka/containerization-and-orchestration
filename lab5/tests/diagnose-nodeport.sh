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
        "${H[@]}" --set networkPolicy.enabled=false || true
    fi
    for pid in "${PIDS[@]}"; do
        kill "$pid" 2>/dev/null || true
    done
    wait 2>/dev/null || true
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

for pod in $("${K[@]}" get pods \
    -n kube-system -l k8s-app=cilium \
    -o jsonpath='{.items[*].metadata.name}'); do

    timeout 120s "${K[@]}" exec \
        -n kube-system "$pod" -c cilium-agent -- \
        hubble observe --follow \
          --namespace lab3 --protocol TCP \
        > "$ROOT/reports/live-tcp-$pod.txt" 2>&1 &
    PIDS+=("$!")
done

sleep 3

echo "=== Включение политик ==="
RESTORE=1
"${H[@]}" --set networkPolicy.enabled=true

sleep 3

echo "=== Проверка запросов, максимум 25 секунд ==="
timeout 25s "${K[@]}" exec -i \
    -n lab3 shop-client -- \
    env DURATION_SECONDS=12 python3 -u - \
    < "$ROOT/tests/check-continuity.py" \
    > "$ROOT/reports/nodeport-diagnostic-client.jsonl" 2>&1 || true

sleep 2
