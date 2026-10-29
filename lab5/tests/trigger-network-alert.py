import json
import socket
import time

deadline = time.monotonic() + 180
attempts = 0
timeouts = 0
unexpected = 0

while time.monotonic() < deadline:
    attempts += 1
    try:
        with socket.create_connection(
            ("shop-postgres-rw", 5432), timeout=1
        ):
            unexpected += 1
            print("FAIL: запрещённое соединение установлено", flush=True)
    except socket.timeout:
        timeouts += 1
    except OSError as error:
        print(json.dumps({"error": str(error)}), flush=True)

    if attempts == 1 or attempts % 10 == 0:
        print(json.dumps({
            "attempts": attempts,
            "timeouts": timeouts,
            "unexpected_connections": unexpected,
        }), flush=True)

    time.sleep(1)

print("Генерация запрещённых запросов завершена", flush=True)
