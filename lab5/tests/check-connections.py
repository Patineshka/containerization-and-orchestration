import json
import os
import socket
import sys

failed = 0
arguments = sys.argv[1:]
if len(arguments) % 3:
    raise SystemExit("Аргументы: HOST PORT allow|deny")

for index in range(0, len(arguments), 3):
    host, port, expected = arguments[index:index + 3]
    actual = "error"
    error = None

    try:
        address = socket.gethostbyname(host)
        try:
            with socket.create_connection((address, int(port)), timeout=3):
                actual = "allow"
        except socket.timeout:
            actual = "timeout"
    except OSError as exception:
        error = str(exception)

    passed = (
        expected == "allow" and actual == "allow"
        or expected == "deny" and actual == "timeout"
    )
    failed += not passed

    print(json.dumps({
        "source": os.getenv("HOSTNAME"),
        "destination": f"{host}:{port}",
        "expected": expected,
        "actual": actual,
        "result": "PASS" if passed else "FAIL",
        "error": error,
    }, ensure_ascii=False), flush=True)

print(json.dumps({
    "summary": True,
    "checks": len(arguments) // 3,
    "failed": failed,
}), flush=True)
sys.exit(1 if failed else 0)
