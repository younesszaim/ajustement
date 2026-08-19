"""Composition root used only by FastAPI, never by the Streamlit UI."""

from __future__ import annotations

from functools import lru_cache

from .config import load_settings
from .service import AdjustmentService
from .storage import PostgresOperationStore, SqlOutputStore


@lru_cache(maxsize=1)
def build_runtime():
    """Wire configuration, stores and domain service for FastAPI.

    The function is cached, but its stores open short-lived database
    connections for each operation rather than holding one global connection.
    """
    import psycopg

    settings = load_settings()
    if not settings.postgres_url:
        raise RuntimeError("No usable PostgreSQL URL is configured")
    postgres_factory = lambda: psycopg.connect(settings.postgres_url)
    if settings.output_database == "postgres":
        output_factory = postgres_factory
    else:
        import vertica_python

        required = ("host", "database", "user", "password")
        if not all(settings.vertica.get(key) for key in required):
            raise RuntimeError("Vertica connection variables are incomplete")
        output_factory = lambda: vertica_python.connect(**settings.vertica)

    output = SqlOutputStore(output_factory, settings)
    operations = PostgresOperationStore(postgres_factory, settings.postgres_schema)
    service = AdjustmentService(output, operations, settings)
    return settings, output, operations, service
