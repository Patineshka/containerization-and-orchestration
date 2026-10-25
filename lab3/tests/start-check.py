import pathlib
import subprocess
import sys

script = pathlib.Path("/tmp/check-shop.py")
script.write_text(sys.stdin.read())

with open("/tmp/check-shop.log", "w") as log:
    process = subprocess.Popen(
        ["python3", "-u", str(script)],
        stdin=subprocess.DEVNULL,
        stdout=log,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )

pathlib.Path("/tmp/check-shop.pid").write_text(str(process.pid))
print("Проверка запущена, PID:", process.pid)