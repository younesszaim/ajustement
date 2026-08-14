import pandas as pd
import pytest

from lib.enrichments.contracts import CalculationContext, EnrichmentError
from lib.enrichments.parameter import apply_best_match_mapping
from lib.enrichments.pipeline import DataFrameCalculationAdapter
from lib.enrichments.registry import REGISTRY
from lib.enrichments.rules import calculate_buckets


def test_bucket_rule_handles_multiple_rows_without_changing_cardinality():
    frame = pd.DataFrame(
        [
            {"eurAmount0d": 100, "asofdate": "2026-08-06", "maturityDate": "2026-08-10"},
            {"eurAmount0d": 200, "asofdate": "2026-08-06", "maturityDate": "2026-10-01"},
        ]
    )

    result = calculate_buckets(frame, CalculationContext(stage="buckets"))

    assert len(result) == 2
    assert result.loc[0, "eurAmount7d"] == 100
    assert result.loc[0, "maturityBucket"] == "0-30D"
    assert result.loc[1, "eurAmount3m"] == 200
    assert result.loc[1, "maturityBucket"] == "31D+"


def test_parameter_enrichment_prefers_exact_row_over_wildcard():
    trades = pd.DataFrame([{"kind": "SECURITY", "country": "FR"}])
    parameter = pd.DataFrame(
        [
            {"KIND": "SECURITY", "COUNTRY": "*", "RESULT": "DEFAULT"},
            {"KIND": "SECURITY", "COUNTRY": "FR", "RESULT": "FRENCH_SECURITY"},
        ]
    )

    result = apply_best_match_mapping(
        trades,
        parameter,
        inputs={"kind": "KIND", "country": "COUNTRY"},
        output=("classification", "RESULT"),
        context=CalculationContext(stage="classification", mapping_name="test"),
    )

    assert result.loc[0, "classification"] == "FRENCH_SECURITY"


def test_parameter_enrichment_rejects_ambiguous_best_matches():
    trades = pd.DataFrame([{"kind": "SECURITY"}])
    parameter = pd.DataFrame(
        [
            {"KIND": "SECURITY", "RESULT": "A"},
            {"KIND": "SECURITY", "RESULT": "B"},
        ]
    )

    with pytest.raises(EnrichmentError, match="ambiguous mapping"):
        apply_best_match_mapping(
            trades,
            parameter,
            inputs={"kind": "KIND"},
            output=("classification", "RESULT"),
            context=CalculationContext(stage="classification"),
        )


def test_pipeline_records_rule_and_parameter_execution_metadata():
    class MappingProvider:
        def parameter_table(self, mapping_name):
            assert mapping_name == "reporting_line_mapping"
            return (
                pd.DataFrame(
                    [
                        {
                            "EXPOSURE_CLASS": "FINANCIAL",
                            "HQLA_LEVEL": "L1",
                            "MATURITY_BUCKET": "0-30D",
                            "REPORTING_LINE_LCR": "RL_SEC_01",
                        }
                    ]
                ),
                "s3://parameters/reporting-line.parquet",
            )

    row = {
        "amount": 100,
        "eurAmount0d": 100,
        "currency": "EUR",
        "asofdate": "2026-08-06",
        "maturityDate": "2026-08-20",
        "exposureClass": "FINANCIAL",
        "hqlaLevel": "L1",
    }

    result, fields, executions = DataFrameCalculationAdapter(MappingProvider()).recalculate(
        row, ["buckets", "reporting_lines"]
    )

    assert result["reportingLineLcr"] == "RL_SEC_01"
    assert "maturityBucket" in fields
    assert executions[0]["type"] == "rule"
    assert executions[1]["type"] == "parameter"
    assert executions[1]["mappingSource"].startswith("s3://")


def test_pipeline_requires_parameter_provider_and_rejects_unknown_stage():
    with pytest.raises(EnrichmentError, match="parameter provider is required"):
        DataFrameCalculationAdapter()

    class Provider:
        def parameter_table(self, mapping_name):
            raise AssertionError("An unknown stage must fail before loading a mapping")

    with pytest.raises(EnrichmentError, match="No enrichment function"):
        DataFrameCalculationAdapter(Provider()).recalculate({"amount": 1}, ["unknown"])


def test_every_dependency_stage_has_a_real_registered_function():
    from app.config import STAGE_DEPENDENCIES

    assert set(STAGE_DEPENDENCIES) == set(REGISTRY)
