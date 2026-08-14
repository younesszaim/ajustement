"""Build the small Parquet catalog used by local development and tests.

Production replaces only ``latest_mappings.json`` paths with S3 objects; the
calculation functions and pipeline remain unchanged.
"""

from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq


OUTPUT = Path(__file__).parents[1] / "mapping_data" / "examples"


TABLES = {
    "instrument_classification_2026-08-13.parquet": [
        {"RAW_INSTRUMENT_TYPE": value, "INSTRUMENT_CLASS": value}
        for value in ("SECURITY", "LOAN", "DEPOSIT")
    ],
    "issuer_2026-08-13.parquet": [
        {"ISSUER": "ISSUER_A", "COUNTRY": "EU", "RATING": "A"},
        {"ISSUER": "PROXY_ISSUER", "COUNTRY": "EU", "RATING": "A"},
        {"ISSUER": "*", "COUNTRY": "OTHER", "RATING": "UNRATED"},
    ],
    "counterparty_2026-08-13.parquet": [
        {"COUNTERPARTY": "CP_BANK_01", "COUNTERPARTY_TYPE": "BANK"},
        {"COUNTERPARTY": "CP_BANK_02", "COUNTERPARTY_TYPE": "BANK"},
        {"COUNTERPARTY": "CP_BANK_03", "COUNTERPARTY_TYPE": "BANK"},
        {"COUNTERPARTY": "CP_SOV_01", "COUNTERPARTY_TYPE": "SOVEREIGN"},
        {"COUNTERPARTY": "CP_CORP_01", "COUNTERPARTY_TYPE": "CORPORATE"},
        {"COUNTERPARTY": "CP_CORP_02", "COUNTERPARTY_TYPE": "CORPORATE"},
        {"COUNTERPARTY": "CP_PROXY", "COUNTERPARTY_TYPE": "BANK"},
        {"COUNTERPARTY": "*", "COUNTERPARTY_TYPE": "OTHER"},
    ],
    "exposure_class_2026-08-13.parquet": [
        {"INSTRUMENT_TYPE": "SECURITY", "COUNTERPARTY_TYPE": "BANK", "COUNTRY": "*", "EXPOSURE_CLASS": "FINANCIAL"},
        {"INSTRUMENT_TYPE": "SECURITY", "COUNTERPARTY_TYPE": "SOVEREIGN", "COUNTRY": "*", "EXPOSURE_CLASS": "SOVEREIGN"},
        {"INSTRUMENT_TYPE": "*", "COUNTERPARTY_TYPE": "CORPORATE", "COUNTRY": "*", "EXPOSURE_CLASS": "CORPORATE"},
        {"INSTRUMENT_TYPE": "LOAN", "COUNTERPARTY_TYPE": "*", "COUNTRY": "*", "EXPOSURE_CLASS": "CORPORATE"},
        {"INSTRUMENT_TYPE": "DEPOSIT", "COUNTERPARTY_TYPE": "*", "COUNTRY": "*", "EXPOSURE_CLASS": "FINANCIAL"},
        {"INSTRUMENT_TYPE": "*", "COUNTERPARTY_TYPE": "*", "COUNTRY": "*", "EXPOSURE_CLASS": "FINANCIAL"},
    ],
    "hqla_2026-08-13.parquet": [
        {"EXPOSURE_CLASS": "SOVEREIGN", "INSTRUMENT_TYPE": "SECURITY", "RATING": "*", "HQLA_LEVEL": "L1"},
        {"EXPOSURE_CLASS": "FINANCIAL", "INSTRUMENT_TYPE": "SECURITY", "RATING": "A", "HQLA_LEVEL": "L2A"},
        {"EXPOSURE_CLASS": "CORPORATE", "INSTRUMENT_TYPE": "SECURITY", "RATING": "*", "HQLA_LEVEL": "L2B"},
        {"EXPOSURE_CLASS": "*", "INSTRUMENT_TYPE": "LOAN", "RATING": "*", "HQLA_LEVEL": "NON_HQLA"},
        {"EXPOSURE_CLASS": "*", "INSTRUMENT_TYPE": "DEPOSIT", "RATING": "*", "HQLA_LEVEL": "NON_HQLA"},
    ],
    "reporting_line_2026-08-13.parquet": [
        {"EXPOSURE_CLASS": "FINANCIAL", "HQLA_LEVEL": "*", "MATURITY_BUCKET": "0-30D", "REPORTING_LINE_LCR": "RL_SEC_01"},
        {"EXPOSURE_CLASS": "FINANCIAL", "HQLA_LEVEL": "*", "MATURITY_BUCKET": "31D+", "REPORTING_LINE_LCR": "RL_SEC_03"},
        {"EXPOSURE_CLASS": "SOVEREIGN", "HQLA_LEVEL": "*", "MATURITY_BUCKET": "*", "REPORTING_LINE_LCR": "RL_SEC_01"},
        {"EXPOSURE_CLASS": "CORPORATE", "HQLA_LEVEL": "*", "MATURITY_BUCKET": "*", "REPORTING_LINE_LCR": "RL_LOAN_01"},
    ],
    "fx_rate_2026-08-13.parquet": [
        {"CURRENCY": "EUR", "RATE_TO_EUR": 1.0},
        {"CURRENCY": "USD", "RATE_TO_EUR": 0.92},
        {"CURRENCY": "GBP", "RATE_TO_EUR": 1.17},
    ],
    "lcr_factor_2026-08-13.parquet": [
        {"REPORTING_LINE_LCR": "RL_SEC_01", "OUTFLOW_FACTOR": 0.20, "INFLOW_FACTOR": 0.0},
        {"REPORTING_LINE_LCR": "RL_SEC_03", "OUTFLOW_FACTOR": 0.20, "INFLOW_FACTOR": 0.0},
        {"REPORTING_LINE_LCR": "RL_LOAN_01", "OUTFLOW_FACTOR": 0.20, "INFLOW_FACTOR": 0.0},
        {"REPORTING_LINE_LCR": "*", "OUTFLOW_FACTOR": 0.20, "INFLOW_FACTOR": 0.0},
    ],
}


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for filename, rows in TABLES.items():
        pq.write_table(pa.Table.from_pylist(rows), OUTPUT / filename)


if __name__ == "__main__":
    main()
