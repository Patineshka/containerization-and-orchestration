import json
import os
import time
import urllib.request
from datetime import datetime, timezone

duration = int(os.getenv("DURATION_SECONDS", "300"))
started = time.monotonic()
total = failed = cycle = 0

try:
    while time.monotonic() - started < duration:
        cycle_started = time.monotonic()
        node_ip = ["192.168.49.2", "192.168.49.3"][cycle % 2]
        targets = [
            ("dns-service", "http://shop-api.lab3.svc.cluster.local:8080/order"),
            ("nodeport", f"http://{node_ip}:30080/order"),
        ]

        for target, url in targets:
            before = time.monotonic()
            status = None
            error = None
            try:
                request = urllib.request.Request(
                    url,
                    data=json.dumps({
                        "item": "lab5-continuity",
                        "quantity": 1,
                    }).encode(),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(request, timeout=5) as response:
                    status = response.status
                    response.read()
            except Exception as exc:
                status = getattr(exc, "code", None)
                error = str(exc)

            total += 1
            success = status == 201
            failed += int(not success)
            print(json.dumps({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "target": target,
                "url": url,
                "status": status,
                "success": success,
                "latency_ms": round((time.monotonic() - before) * 1000, 2),
                "total": total,
                "failed": failed,
                "error": error,
            }), flush=True)

        cycle += 1
        time.sleep(max(0, 1 - (time.monotonic() - cycle_started)))
finally:
    print(json.dumps({
        "summary": True,
        "total": total,
        "failed": failed,
    }), flush=True)
