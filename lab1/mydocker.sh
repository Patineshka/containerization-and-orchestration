#!/usr/bin/env bash
set -euo pipefail

LAB_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$LAB_DIR/api"

CGROUP=/sys/fs/cgroup/lab1-run

sudo mkdir -p "$CGROUP"

echo 134217728 | sudo tee "$CGROUP/memory.max" >/dev/null
echo 0 | sudo tee "$CGROUP/memory.swap.max" >/dev/null
echo "50000 100000" | sudo tee "$CGROUP/cpu.max" >/dev/null
echo 16 | sudo tee "$CGROUP/pids.max" >/dev/null

echo "$$" | sudo tee "$CGROUP/cgroup.procs" >/dev/null

exec unshare --user --map-root-user --pid --fork \
  --mount --mount-proc --net --uts --ipc \
  sh -ec '
    hostname lab1
    ip link set lo up
    exec capsh --drop=all -- -c \
      "exec /usr/bin/python3 ../seccomp-run.py /usr/bin/python3 server.py"
  '