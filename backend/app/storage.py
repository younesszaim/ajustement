"""Compose the only supported storage: two isolated PostgreSQL schemas."""

import os
from .adapters.simulation_adjustment_repository import SimulationAdjustmentRepository
from .adapters.postgres_vertica_simulator import PostgresVerticaSimulatorRepository
from .adapters.postgres_simulation_audit_repository import (
    PostgresSimulationAuditRepository,
)


def build_repository():
    """Use ``vertica_sim`` for output and ``adjustment_meta`` for audit."""
    project = os.getenv("ADJUSTMENT_PROJECT_KEY", "limon_ldp_bmf")
    connection_factory = _postgres_factory()
    return SimulationAdjustmentRepository(
        PostgresVerticaSimulatorRepository(connection_factory, "vertica_sim"),
        PostgresSimulationAuditRepository(connection_factory, "adjustment_meta"),
        project,
    )


def _postgres_factory():
    def connect():
        import psycopg
        from psycopg.rows import dict_row

        url = os.getenv("DATABASE_URL")
        if not url:
            raise RuntimeError("DATABASE_URL is required")
        return psycopg.connect(url, connect_timeout=10, row_factory=dict_row)

    return connect
