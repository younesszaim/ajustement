from app.storage import build_repository
from app.adapters.simulation_adjustment_repository import SimulationAdjustmentRepository
from app.adapters.postgres_simulation_audit_repository import PostgresSimulationAuditRepository
from app.adapters.postgres_vertica_simulator import PostgresVerticaSimulatorRepository


def test_only_supported_storage_uses_two_simulation_schemas(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://example.invalid/postgres")

    repository = build_repository()

    assert isinstance(repository, SimulationAdjustmentRepository)
    assert isinstance(repository.output, PostgresVerticaSimulatorRepository)
    assert isinstance(repository.audit, PostgresSimulationAuditRepository)
    assert repository.output.schema == "vertica_sim"
    assert repository.audit.schema == "adjustment_meta"


def test_single_database_url_is_required(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    repository = build_repository()

    try:
        repository.output.connection_factory()
    except RuntimeError as error:
        assert str(error) == "DATABASE_URL is required"
    else:
        raise AssertionError("Missing database configuration must fail")
