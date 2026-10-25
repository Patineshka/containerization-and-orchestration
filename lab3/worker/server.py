import json
import logging
import os
import threading
import time
from datetime import datetime, timezone

import psycopg
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode
from prometheus_client import Counter, Gauge

from db import connect, ensure_schema
from observability import app, tracer

PROCESSED = Counter("shop_worker_orders_processed_total", "Orders committed as processed")
FAILURES = Counter("shop_worker_errors_total", "Failed worker iterations")
LAST_SUCCESS = Gauge("shop_worker_last_success_timestamp_seconds", "Last successful DB poll")
BACKLOG = Gauge("shop_worker_pending_orders", "Pending orders observed at the last poll")
LAST_SUCCESS.set(0)
BACKLOG.set(0)


def log(message, level="INFO", **fields):
    context = trace.get_current_span().get_span_context()
    print(json.dumps({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "level": level,
        "message": message,
        "service": os.getenv("SERVICE_NAME", "shop-worker"),
        "trace_id": format(context.trace_id, "032x"),
        "span_id": format(context.span_id, "016x"),
        **fields,
    }, ensure_ascii=False), flush=True)


def run_worker():
    worker_name = os.getenv("HOSTNAME", "worker")
    while True:
        # /health checks the worker thread as well as the HTTP server.
        app.config["WORKER_HEARTBEAT"] = time.monotonic()
        with tracer.start_as_current_span("worker.poll-orders") as span:
            try:
                ensure_schema()
                with connect() as conn:
                    row = conn.execute("""
                        SELECT id FROM orders
                        WHERE status = 'new' ORDER BY id LIMIT 1
                        FOR UPDATE SKIP LOCKED
                    """).fetchone()
                    if row:
                        conn.execute("""
                            UPDATE orders SET status = 'processed',
                                processed_at = now(), processed_by = %s
                            WHERE id = %s
                        """, (worker_name, row["id"]))
                    pending = conn.execute(
                        "SELECT count(*) AS count FROM orders WHERE status = 'new'"
                    ).fetchone()["count"]
                # The connection context has committed before reporting success.
                LAST_SUCCESS.set(time.time())
                BACKLOG.set(pending)
                if row:
                    PROCESSED.inc()
                    log("Order processed", order_id=row["id"], worker=worker_name)
            except psycopg.Error as error:
                FAILURES.inc()
                span.set_status(Status(StatusCode.ERROR, "Database unavailable"))
                log("Database operation failed; retrying", "ERROR", kind=type(error).__name__)
        time.sleep(2)


original_health = app.view_functions["health"]


def worker_health():
    heartbeat = app.config.get("WORKER_HEARTBEAT", 0)
    if time.monotonic() - heartbeat > 30:
        return {"error": "Worker loop is not responding"}, 503
    return original_health()


app.view_functions["health"] = worker_health


if __name__ == "__main__":
    logging.getLogger("werkzeug").disabled = True
    threading.Thread(target=run_worker, daemon=True).start()
    app.run(host="0.0.0.0", port=8080, threaded=True, debug=False, use_reloader=False)
