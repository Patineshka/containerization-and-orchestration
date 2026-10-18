import sys
from pathlib import Path
from http.server import BaseHTTPRequestHandler, HTTPServer

cgroup = Path(sys.argv[1])


def read_number(filename):
    return int((cgroup / filename).read_text().strip())


def read_pairs(filename):
    return dict(
        line.split()
        for line in (cgroup / filename).read_text().splitlines()
    )


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/metrics":
            self.send_error(404)
            return

        try:
            cpu = read_pairs("cpu.stat")
            memory = read_pairs("memory.events")
            metrics = [
                ("lab1_memory_usage_bytes", "gauge",
                 read_number("memory.current")),
                ("lab1_memory_limit_bytes", "gauge",
                 read_number("memory.max")),
                ("lab1_cpu_usage_seconds_total", "counter",
                 int(cpu["usage_usec"]) / 1_000_000),
                ("lab1_cpu_throttled_seconds_total", "counter",
                 int(cpu["throttled_usec"]) / 1_000_000),
                ("lab1_cpu_periods_total", "counter",
                 int(cpu["nr_periods"])),
                ("lab1_cpu_throttled_periods_total", "counter",
                 int(cpu["nr_throttled"])),
                ("lab1_oom_kills_total", "counter",
                 int(memory["oom_kill"])),
            ]
        except (OSError, ValueError, KeyError) as error:
            self.send_error(503, str(error))
            return

        body = "".join(
            f"# TYPE {name} {kind}\n{name} {value}\n"
            for name, kind, value in metrics
        ).encode()

        self.send_response(200)
        self.send_header("Content-Type", "text/plain; version=0.0.4")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


print(f"Метрики: http://127.0.0.1:9105/metrics\nCgroup: {cgroup}",
      flush=True)
HTTPServer(("127.0.0.1", 9105), Handler).serve_forever()
