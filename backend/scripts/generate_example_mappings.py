"""Generate small local Parquet mappings used by the development manifest."""

from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq


OUTPUT_DIR = Path(__file__).parents[1] / "mapping_data" / "examples"

MAPPINGS = {
    "exposure_class_2026-08-12.parquet": [
        {"INSTRUMENT_TYPE": "SECURITY", "COUNTERPARTY_TYPE": "BANK", "COUNTRY": "*", "EXPOSURE_CLASS": "FINANCIAL"},
        {"INSTRUMENT_TYPE": "SECURITY", "COUNTERPARTY_TYPE": "SOVEREIGN", "COUNTRY": "EU", "EXPOSURE_CLASS": "SOVEREIGN"},
        {"INSTRUMENT_TYPE": "LOAN", "COUNTERPARTY_TYPE": "CORPORATE", "COUNTRY": "*", "EXPOSURE_CLASS": "CORPORATE"},
        {"INSTRUMENT_TYPE": "DEPOSIT", "COUNTERPARTY_TYPE": "CENTRAL_BANK", "COUNTRY": "*", "EXPOSURE_CLASS": "CENTRAL_BANK"},
        {"INSTRUMENT_TYPE": "LOAN", "COUNTERPARTY_TYPE": "RETAIL", "COUNTRY": "*", "EXPOSURE_CLASS": "RETAIL"},
    ],
    "hqla_2026-08-12.parquet": [
        {"EXPOSURE_CLASS": "SOVEREIGN", "INSTRUMENT_TYPE": "SECURITY", "RATING": "AAA-AA", "HQLA_LEVEL": "L1"},
        {"EXPOSURE_CLASS": "FINANCIAL", "INSTRUMENT_TYPE": "SECURITY", "RATING": "A", "HQLA_LEVEL": "L2A"},
        {"EXPOSURE_CLASS": "CORPORATE", "INSTRUMENT_TYPE": "SECURITY", "RATING": "BBB", "HQLA_LEVEL": "L2B"},
        {"EXPOSURE_CLASS": "*", "INSTRUMENT_TYPE": "LOAN", "RATING": "*", "HQLA_LEVEL": "NON_HQLA"},
    ],
    "reporting_line_2026-08-12.parquet": [
        {"EXPOSURE_CLASS": "FINANCIAL", "HQLA_LEVEL": "L1", "MATURITY_BUCKET": "0-30D", "REPORTING_LINE_LCR": "RL_SEC_01"},
        {"EXPOSURE_CLASS": "FINANCIAL", "HQLA_LEVEL": "L1", "MATURITY_BUCKET": "31D+", "REPORTING_LINE_LCR": "RL_SEC_03"},
        {"EXPOSURE_CLASS": "CORPORATE", "HQLA_LEVEL": "NON_HQLA", "MATURITY_BUCKET": "*", "REPORTING_LINE_LCR": "RL_LOAN_01"},
        {"EXPOSURE_CLASS": "CENTRAL_BANK", "HQLA_LEVEL": "L1", "MATURITY_BUCKET": "*", "REPORTING_LINE_LCR": "RL_DEP_01"},
    ],
}


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for filename, rows in MAPPINGS.items():
        path = OUTPUT_DIR / filename
        pq.write_table(pa.Table.from_pylist(rows), path, compression="snappy")
        print(f"Generated {path} ({len(rows)} rows)")


if __name__ == "__main__":
    main()
