import json
import random
import subprocess
import time
from datetime import datetime, timezone

kubectl = ["minikube", "-p", "lab2", "kubectl", "--"]
minimum = {"shop-api": 3, "shop-worker": 1}


def log(**fields):
    print(json.dumps({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **fields,
    }), flush=True)


deadline = time.monotonic() + 240

while time.monotonic() < deadline:
    result = subprocess.run(
        kubectl + [
            "get", "pods", "-n", "lab3",
            "-l", "app in (shop-api,shop-worker)", "-o", "json",
        ],
        capture_output=True, text=True, check=True,
    )
    pods = json.loads(result.stdout)["items"]

    log(
        event="snapshot",
        pods=[{
            "name": p["metadata"]["name"],
            "ip": p["status"].get("podIP"),
            "uid": p["metadata"]["uid"],
        } for p in pods],
    )

    ready = {app: [] for app in minimum}
    for pod in pods:
        if pod["metadata"].get("deletionTimestamp"):
            continue
        is_ready = any(
            c["type"] == "Ready" and c["status"] == "True"
            for c in pod["status"].get("conditions", [])
        )
        app = pod["metadata"]["labels"]["app"]
        if is_ready:
            ready[app].append(pod)

    candidates = [
        pod
        for app, items in ready.items()
        if len(items) > minimum[app]
        for pod in items
    ]

    if candidates:
        pod = random.choice(candidates)
        name = pod["metadata"]["name"]
        result = subprocess.run(
            kubectl + [
                "delete", "pod", name, "-n", "lab3", "--wait=false",
            ],
            capture_output=True, text=True,
        )
        log(
            event="delete" if result.returncode == 0 else "delete_failed",
            pod=name,
            ip=pod["status"].get("podIP"),
            detail=(result.stdout + result.stderr).strip(),
        )
    else:
        log(event="skip", reason="Waiting for ready replicas")

    time.sleep(5)

log(event="finished")
