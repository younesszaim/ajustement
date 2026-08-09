"""Select storage composition without changing API or business services."""

import importlib, os
from .adapters.postgres_adjustment_repository import (
    PostgresAdjustmentRepository,
    connection_from_environment,
)
from .adapters.postgres_audit_repository import PostgresAuditRepository
from .adapters.hybrid_adjustment_repository import HybridAdjustmentRepository
from .adapters.vertica_repository import VerticaColumnMap, VerticaLimonRepository


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
