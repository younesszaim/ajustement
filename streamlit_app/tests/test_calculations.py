"""Examples that make the ordered recalculation contract executable."""

from pathlib import Path

import pytest

from streamlit_app.calculations import CalculationPipeline, recalculate_by_instrument
from streamlit_app.config import load_settings


def configured_row():
    """Return one real-shaped Cash row using the Vertica field configuration."""
    return {
        "AsOfDate": "2026-08-06",
        "InstrumentType": "SEC",
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


def test_exposure_override_runs_complete_pipeline():
    result, steps = CalculationPipeline().run(
        configured_row(), columns(), {"exposure_class": "FINANCIAL"}
    )

    assert steps == [
        "exposure_class",
        "reportline_code",
        "maturity_date",
        "calculate_buckets",
        "calculate_ldp_impacts",
    ]
    assert result["exposure_class"] == "FINANCIAL"
    assert result["reporting_line_lcr"] == "RL_SEC_03"


def test_reportline_override_runs_complete_pipeline_and_remains_protected():
    result, steps = CalculationPipeline().run(
        configured_row(), columns(), {"reporting_line_lcr": "RL_SEC_03"}
    )

    assert steps == [
        "exposure_class",
        "reportline_code",
        "maturity_date",
        "calculate_buckets",
        "calculate_ldp_impacts",
    ]
    assert result["reporting_line_lcr"] == "RL_SEC_03"


def test_multiple_manual_overrides_are_not_overwritten_downstream():
    result, steps = CalculationPipeline().run(
        configured_row(),
        columns(),
        {"exposure_class": "CORPORATE", "reporting_line_lcr": "RL_SEC_03"},
    )

    assert steps[0] == "exposure_class"
    assert result["exposure_class"] == "CORPORATE"
    # The demo reportline function would derive RL_LOAN_01 from CORPORATE, but
    # the user's explicit reporting-line override must remain authoritative.
    assert result["reporting_line_lcr"] == "RL_SEC_03"


def test_amount_change_runs_complete_pipeline():
    events = []
    result, steps = CalculationPipeline().run(
        configured_row(),
        columns(),
        {"cash_amount_eur": 250.0},
        progress_callback=lambda stage, completed, total, status: events.append(
            (stage, completed, total, status)
        ),
    )

    assert steps == [
        "exposure_class",
        "reportline_code",
        "maturity_date",
        "calculate_buckets",
        "calculate_ldp_impacts",
    ]
    assert result["eur_amount_7d"] == 250.0
    assert result["ldp_impact_asset_cash_gestion"] == 250.0
    assert events == [
        ("exposure_class", 0, 5, "RUNNING"),
        ("exposure_class", 1, 5, "COMPLETED"),
        ("reportline_code", 1, 5, "RUNNING"),
        ("reportline_code", 2, 5, "COMPLETED"),
        ("maturity_date", 2, 5, "RUNNING"),
        ("maturity_date", 3, 5, "COMPLETED"),
        ("calculate_buckets", 3, 5, "RUNNING"),
        ("calculate_buckets", 4, 5, "COMPLETED"),
        ("calculate_ldp_impacts", 4, 5, "RUNNING"),
        ("calculate_ldp_impacts", 5, 5, "COMPLETED"),
    ]


@pytest.mark.parametrize("instrument_type", ["OST", "SEC", "EQUITY"])
def test_dispatcher_selects_configured_full_pipeline(instrument_type):
    settings = load_settings(Path(__file__).parents[1] / "project.yaml")
    row = configured_row()
    row["InstrumentType"] = instrument_type.lower()
    events = []

    result, steps = recalculate_by_instrument(
        row,
        columns(),
        {"cash_amount_eur": 250.0},
        progress_callback=lambda *event: events.append(event),
        calculation_config=settings.calculation_config,
    )

    assert result["InstrumentType"] == instrument_type.lower()
    assert steps == [
        f"{instrument_type}/exposure_class",
        f"{instrument_type}/reportline_code",
        f"{instrument_type}/maturity_date",
        f"{instrument_type}/calculate_buckets",
        f"{instrument_type}/calculate_ldp_impacts",
    ]
    assert events[0] == (f"{instrument_type}/exposure_class", 0, 5, "RUNNING")
    assert events[-1] == (
        f"{instrument_type}/calculate_ldp_impacts",
        5,
        5,
        "COMPLETED",
    )


def test_dispatcher_rejects_missing_or_unsupported_instrument_type():
    settings = load_settings(Path(__file__).parents[1] / "project.yaml")
    row = configured_row()
    row["InstrumentType"] = None
    with pytest.raises(ValueError, match="Instrument type is missing"):
        recalculate_by_instrument(
            row, columns(), {}, calculation_config=settings.calculation_config
        )

    row["InstrumentType"] = "UNKNOWN"
    with pytest.raises(ValueError, match="unsupported"):
        recalculate_by_instrument(
            row, columns(), {}, calculation_config=settings.calculation_config
        )


def test_dispatcher_lists_missing_required_inputs_before_pipeline_runs():
    settings = load_settings(Path(__file__).parents[1] / "project.yaml")
    row = configured_row()
    del row["MaturityDate"]

    with pytest.raises(ValueError, match="maturity_date"):
        recalculate_by_instrument(
            row, columns(), {}, calculation_config=settings.calculation_config
        )
