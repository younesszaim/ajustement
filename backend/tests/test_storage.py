from app.storage import build_repository
from app.adapters.simulation_adjustment_repository import SimulationAdjustmentRepository
from app.adapters.postgres_simulation_audit_repository import PostgresSimulationAuditRepository
from app.adapters.postgres_vertica_simulator import PostgresVerticaSimulatorRepository
from datetime import date, datetime


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


def test_output_adapter_maps_leg_amounts_and_ldp_impacts():
    repository = PostgresVerticaSimulatorRepository(lambda: None)
    row = {
        "output_record_id": "OUT-1", "asofdate": date(2026, 8, 6),
        "asofdateflow": datetime(2026, 8, 7, 4, 45), "trade_no": "T-1",
        "fo_system": "APEX", "record_type": "BASE", "security_leg_flag": 0,
        "cash_amount_eur": 400, "security_amount_eur": 0,
        "ldp_impact_asset": 0, "ldp_impact_asset_cash_gestion": 400,
        "ldp_impact_inflow": 0, "ldp_impact_outflow": 80,
        "ldp_impact_lcr_reglementaire": -80, "ldp_impact_lcr_gestion": 320,
    }

    trade = repository._domain(row)
    assert trade["securityLegFlag"] == 0
    assert trade["cashAmountEur"] == 400
    assert trade["ldpImpactLcrGestion"] == 320
