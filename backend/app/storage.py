"""Select storage composition without changing API or business services."""

import importlib, os
from .adapters.postgres_adjustment_repository import (
    PostgresAdjustmentRepository,
    connection_from_environment,
)
from .adapters.postgres_audit_repository import PostgresAuditRepository
from .adapters.hybrid_adjustment_repository import HybridAdjustmentRepository
from .adapters.vertica_repository import VerticaColumnMap, VerticaLimonRepository
from .adapters.postgres_vertica_simulator import PostgresVerticaSimulatorRepository
from .adapters.postgres_simulation_audit_repository import (
    PostgresSimulationAuditRepository,
)


def _load_factory(path: str):
    if ":" not in path:
        raise RuntimeError(
            "LIMON_VERTICA_CONNECTION_FACTORY must use module.path:function format"
        )
    module, name = path.split(":", 1)
    return getattr(importlib.import_module(module), name)


def build_repository():
    mode = os.getenv("STORAGE_MODE", "supabase").lower()
    project = os.getenv("ADJUSTMENT_PROJECT_KEY", "limon_ldp_bmf")
    if mode == "supabase":
        return PostgresAdjustmentRepository(connection_from_environment, project)
    if mode == "hybrid_sim":
        return HybridAdjustmentRepository(
            PostgresVerticaSimulatorRepository(
                _postgres_factory("OUTPUT_DB_URL", "SUPABASE_DB_URL")
            ),
            PostgresSimulationAuditRepository(
                _postgres_factory("METADATA_DB_URL", "SUPABASE_DB_URL")
            ),
            project,
        )
    if mode == "hybrid":
        factory_path = os.getenv("LIMON_VERTICA_CONNECTION_FACTORY")
        if not factory_path:
            raise RuntimeError(
                "LIMON_VERTICA_CONNECTION_FACTORY is required for STORAGE_MODE=hybrid"
            )
        columns = VerticaColumnMap(
            table=os.getenv("VERTICA_OUTPUT_TABLE", "output_completude_table")
        )
        output = VerticaLimonRepository(_load_factory(factory_path), columns)
        audit = PostgresAuditRepository(connection_from_environment)
        return HybridAdjustmentRepository(output, audit, project)
    raise RuntimeError(f"Unsupported STORAGE_MODE: {mode}")


def _postgres_factory(primary_name, fallback_name):
    def connect():
        import psycopg
        from psycopg.rows import dict_row

        url = os.getenv(primary_name) or os.getenv(fallback_name)
        if not url:
            raise RuntimeError(f"{primary_name} or {fallback_name} is required")
        return psycopg.connect(url, connect_timeout=10, row_factory=dict_row)

    return connect
