import socket

for host, port in [
    ("shop-postgres-rw", 5432),
    ("shop-worker", 8080),
]:
    try:
        addresses = socket.getaddrinfo(
            host, port, type=socket.SOCK_STREAM
        )
    except socket.gaierror as error:
        print(f"CHECK: {host}:{port} — ошибка DNS: {error}", flush=True)
        continue

    address = addresses[0][4]
    try:
        with socket.create_connection(address, timeout=3):
            print(
                f"FAIL: {host}:{port} — запрещённое соединение установлено",
                flush=True,
            )
    except socket.timeout:
        print(
            f"EXPECTED: {host}:{port} — соединение завершилось тайм-аутом",
            flush=True,
        )
    except OSError as error:
        print(f"CHECK: {host}:{port} — {error}", flush=True)
