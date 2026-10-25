import json
import time
import urllib.request
from datetime import datetime, timezone

BASE_URL = "http://shop-api:8080"
total = 0
failed = 0

while True:
    for path in ("/health", "/orders"):
        total += 1
        timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")

        try:
            with urllib.request.urlopen(
                BASE_URL + path, timeout=3
            ) as response:
                body = response.read().decode()

                if path == "/orders":
                    details = {"orders": len(json.loads(body)["orders"])}
                else:
                    if body.strip() != "ok":
                        raise ValueError("Unexpected health response")
                    details = {"body": body.strip()}

                result = {
                    "timestamp": timestamp,
                    "path": path,
                    "status": response.status,
                    **details,
                }

        except Exception as error:
            failed += 1
            result = {
                "timestamp": timestamp,
                "path": path,
                "error": type(error).__name__,
            }

        print(
            json.dumps(
                {**result, "total": total, "failed": failed},
                ensure_ascii=False,
            ),
            flush=True,
        )

    time.sleep(2)