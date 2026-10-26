import logging
import os

import psycopg
from flask import jsonify, request
from werkzeug.exceptions import BadRequest, UnsupportedMediaType

from db import connect, ensure_schema, serialize
from observability import app, tracer

app.config["MAX_CONTENT_LENGTH"] = 64 * 1024


@app.errorhandler(psycopg.Error)
def database_error(error):
    # Do not expose connection strings or credentials in logs/HTTP responses.
    from opentelemetry.trace import Status, StatusCode
    from opentelemetry import trace
    trace.get_current_span().set_status(Status(StatusCode.ERROR, "Database unavailable"))
    return jsonify(error="Database unavailable", kind=type(error).__name__), 503


@app.post("/order")
def create_order():
    try:
        data = request.get_json()
    except (BadRequest, UnsupportedMediaType):
        return jsonify(error="Expected a JSON object"), 400
    if not isinstance(data, dict):
        return jsonify(error="Expected a JSON object"), 400
    item = data.get("item")
    quantity = data.get("quantity", 1)
    if not isinstance(item, str) or not item.strip() or len(item) > 200:
        return jsonify(error="item must be a nonempty string, max 200 characters"), 400
    if type(quantity) is not int or not 1 <= quantity <= 1000:
        return jsonify(error="quantity must be an integer between 1 and 1000"), 400

    with tracer.start_as_current_span("db.create-order"):
        ensure_schema()
        with connect() as conn:
            row = conn.execute(
                "INSERT INTO orders (item, quantity) VALUES (%s, %s) RETURNING *",
                (item.strip(), quantity),
            ).fetchone()
    return jsonify(order=serialize(row), version=os.getenv("APP_VERSION", "v1")), 201


@app.get("/orders")
def list_orders():
    with tracer.start_as_current_span("db.list-orders"):
        ensure_schema()
        with connect() as conn:
            rows = conn.execute("SELECT * FROM orders ORDER BY id DESC LIMIT 100").fetchall()
    return jsonify(orders=[serialize(row) for row in rows], version=os.getenv("APP_VERSION", "v1"))


if __name__ == "__main__":
    logging.getLogger("werkzeug").disabled = True
    app.run(host="0.0.0.0", port=8080, threaded=True, debug=False, use_reloader=False)
