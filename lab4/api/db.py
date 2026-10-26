import os
import threading

import psycopg
from psycopg.rows import dict_row

_schema_ready = False
_schema_lock = threading.Lock()


def connect():
    # PGHOST/PGPORT/PGDATABASE/PGUSER/PGPASSWORD are read by libpq.
    # Credentials will be provided by a Kubernetes Secret.
    return psycopg.connect(
        connect_timeout=3,
        options="-c statement_timeout=5000 -c lock_timeout=5000",
        application_name=os.getenv("SERVICE_NAME", "shop"),
        row_factory=dict_row,
    )


def ensure_schema():
    global _schema_ready
    if _schema_ready:
        return
    with _schema_lock:
        if _schema_ready:
            return
        with connect() as conn:
            # Serialize first-time table creation across all API/worker replicas.
            conn.execute("SELECT pg_advisory_xact_lock(33001)")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS orders (
                    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                    item TEXT NOT NULL,
                    quantity INTEGER NOT NULL CHECK (quantity > 0),
                    status TEXT NOT NULL DEFAULT 'new',
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    processed_at TIMESTAMPTZ,
                    processed_by TEXT
                )
            """)
        _schema_ready = True


def serialize(row):
    return {
        key: value.isoformat() if hasattr(value, "isoformat") else value
        for key, value in row.items()
    }
