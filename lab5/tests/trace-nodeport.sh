#!/usr/bin/env bash
set -euo pipefail

ROOT="$HOME/lab5"
PIDS=()

cleanup() {
  for node in lab2 lab2-m02; do
    docker exec "$node" iptables -w -t raw -D PREROUTING \
      -p tcp --dport 30080 \
      -m comment --comment lab5-nodeport-trace \
      -j TRACE 2>/dev/null || true
  done
  for pid in "${PIDS[@]}"; do
    kill "$pid" 2>/dev/null || true
  done
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

for node in lab2 lab2-m02; do
  docker exec "$node" sh -c 'command -v xtables-monitor'
done

for node in lab2 lab2-m02; do
  docker exec "$node" timeout 90s xtables-monitor --trace \
    > "$ROOT/reports/netfilter-trace-$node.txt" 2>&1 &
  PIDS+=("$!")

  docker exec "$node" iptables -w -t raw -I PREROUTING 1 \
    -p tcp --dport 30080 \
    -m comment --comment lab5-nodeport-trace \
    -j TRACE
done

sleep 2
bash "$ROOT/tests/diagnose-nodeport-packets.sh"

for node in lab2 lab2-m02; do
  echo "=== Трассировка $node ==="
  tail -n 100 "$ROOT/reports/netfilter-trace-$node.txt"
done
