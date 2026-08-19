"""Examples that make the ordered recalculation contract executable."""

from pathlib import Path

from streamlit_app.calculations import CalculationPipeline
from streamlit_app.config import load_settings


def configured_row():
    """Return one real-shaped Cash row using the Vertica field configuration."""
    return {
        "AsOfDate": "2026-08-06",
        "MaturityDate": "2026-08-12",
        "security_leg_flag": 0,
        "Cash_Amount_EUR": 100.0,
        "SecurityAmount_EUR": 0.0,
        "exposure_class": "RETAIL",
        "reporting_line_lcr": "RL_DEP_01",
        "eur_amount_7d": 100.0,
        "eur_amount_30d": 0.0,
        "eur_amount_3m": 0.0,
        "ldp_impact_asset": 0.0,
        "ldp_impact_asset_cash_gestion": 100.0,
        "ldp_impact_lcr_reglementaire": 100.0,
    }


def columns():
    settings = load_settings(Path(__file__).parents[1] / "project.yaml")
    return {key: value["column"] for key, value in settings.fields.items()}


def test_exposure_override_runs_every_stage_after_exposure():
    result, steps = CalculationPipeline().run(
        configured_row(), columns(), {"exposure_class": "FINANCIAL"}
    )

    assert steps == [
        "reportline_code",
        "maturity_date",
        "calculate_buckets",
        "calculate_ldp_impacts",
    ]
    assert result["exposure_class"] == "FINANCIAL"
    assert result["reporting_line_lcr"] == "RL_SEC_03"


def test_reportline_override_starts_after_reportline_function():
    result, steps = CalculationPipeline().run(
        configured_row(), columns(), {"reporting_line_lcr": "RL_SEC_03"}
    )

    assert steps == ["maturity_date", "calculate_buckets", "calculate_ldp_impacts"]
    assert result["reporting_line_lcr"] == "RL_SEC_03"


def test_multiple_manual_overrides_are_not_overwritten_downstream():
    result, steps = CalculationPipeline().run(
        configured_row(),
        columns(),
        {"exposure_class": "CORPORATE", "reporting_line_lcr": "RL_SEC_03"},
    )

    assert steps[0] == "reportline_code"
    assert result["exposure_class"] == "CORPORATE"
    # The demo reportline function would derive RL_LOAN_01 from CORPORATE, but
    # the user's explicit reporting-line override must remain authoritative.
    assert result["reporting_line_lcr"] == "RL_SEC_03"


def test_amount_change_starts_at_bucket_stage():
    events = []
    result, steps = CalculationPipeline().run(
        configured_row(),
        columns(),
        {"cash_amount_eur": 250.0},
        progress_callback=lambda stage, completed, total, status: events.append(
            (stage, completed, total, status)
        ),
    )

    assert steps == ["calculate_buckets", "calculate_ldp_impacts"]
    assert result["eur_amount_7d"] == 250.0
    assert result["ldp_impact_asset_cash_gestion"] == 250.0
    assert events == [
        ("calculate_buckets", 0, 2, "RUNNING"),
        ("calculate_buckets", 1, 2, "COMPLETED"),
        ("calculate_ldp_impacts", 1, 2, "RUNNING"),
        ("calculate_ldp_impacts", 2, 2, "COMPLETED"),
    ]
