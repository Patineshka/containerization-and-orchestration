import json
import os
import time
from datetime import datetime, timezone

import requests
from flask import Flask, Response, g, jsonify, request
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.flask import FlaskInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import Status, StatusCode
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest


provider = TracerProvider(resource=Resource.create({
    "service.name": os.getenv("OTEL_SERVICE_NAME", os.getenv("SERVICE_NAME", "shop-api"))
}))
endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
if endpoint:
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
trace.set_tracer_provider(provider)
tracer = trace.get_tracer(__name__)

app = Flask(__name__)
FlaskInstrumentor().instrument_app(app, excluded_urls=r".*/metrics$")
RequestsInstrumentor().instrument()

REQUESTS = Counter("api_requests_total", "Completed HTTP requests",
                   ["method", "route", "status"])
ERRORS = Counter("api_errors_total", "HTTP server errors", ["route"])
DURATION = Histogram("api_request_duration_seconds", "HTTP response duration",
                     ["route"], buckets=(.005, .01, .025, .05, .1, .25, .5, 1, 2, 3, 5, 10))


@app.before_request
def start_request():
    g.started = time.perf_counter()


@app.after_request
def finish_request(response):
    if request.path == "/metrics":
        return response
    duration = time.perf_counter() - g.started
    route = request.url_rule.rule if request.url_rule else "unmatched"
    REQUESTS.labels(request.method, route, str(response.status_code)).inc()
    DURATION.labels(route).observe(duration)
    span = trace.get_current_span()
    if response.status_code >= 500:
        ERRORS.labels(route).inc()
        span.set_status(Status(StatusCode.ERROR, "HTTP server error"))
    context = span.get_span_context()
    print(json.dumps({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "level": "ERROR" if response.status_code >= 500 else "INFO",
        "message": "HTTP request completed",
        "service": os.getenv("SERVICE_NAME", "shop-api"),
        "version": os.getenv("APP_VERSION", "v1"),
        "method": request.method,
        "route": route,
        "status": response.status_code,
        "duration_seconds": round(duration, 6),
        "trace_id": format(context.trace_id, "032x"),
        "span_id": format(context.span_id, "016x"),
    }, ensure_ascii=False), flush=True)
    return response


@app.get("/health")
def health():
    if os.getenv("HEALTH_FAIL", "false").lower() == "true":
        return jsonify(error="Intentional health failure"), 503
    return Response("ok", mimetype="text/plain")


@app.get("/fail")
def fail():
    trace.get_current_span().add_event("Intentional failure")
    return jsonify(error="Intentional failure"), 500


@app.get("/slow")
def slow():
    with tracer.start_as_current_span("slow-op"):
        time.sleep(2)
    return jsonify(result="ok", delay_seconds=2)


@app.get("/load")
def load():
    # A fixed batch avoids unbounded workloads and recursive calls to /load.
    base_url = os.getenv("SELF_URL", "http://127.0.0.1:8080").rstrip("/")
    successful = 0
    for _ in range(20):
        try:
            with requests.get(f"{base_url}/health", timeout=3) as response:
                successful += int(response.status_code == 200)
        except requests.RequestException:
            pass
    return jsonify(requested=20, successful=successful), 200 if successful == 20 else 503


@app.get("/metrics")
def metrics():
    return Response(generate_latest(), content_type=CONTENT_TYPE_LATEST)

