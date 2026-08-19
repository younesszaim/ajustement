"""Environment and YAML configuration for the simple application."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import re
from urllib.parse import urlparse
import yaml
from dotenv import load_dotenv


# Streamlit and IDE/debug launches do not execute ``source .env``. Load the
# project file once at import time while preserving explicitly exported values.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
STREAMLIT_ENV = PROJECT_ROOT / ".env.streamlit"
DEFAULT_ENV = PROJECT_ROOT / ".env"
load_dotenv(DEFAULT_ENV, override=False)
if STREAMLIT_ENV.exists():
    load_dotenv(STREAMLIT_ENV, override=False)


def _database_url() -> str:
    """Return the first usable URL, skipping template/example hostnames."""
    placeholders = {"host", "aws-region.pooler.supabase.com", "your-supabase-host"}
    for name in ("POSTGRES_URL", "DATABASE_URL", "SUPABASE_DB_URL"):
        value = os.getenv(name, "").strip()
        hostname = urlparse(value).hostname
        if value and hostname and hostname not in placeholders:
            return value
    return ""


@dataclass(frozen=True)
class Settings:
    """Resolved project dictionary, environment and physical column mapping."""
    project: dict
    fields: dict
    technical_fields: dict
    display_fields: list[str]
    editable_fields: list[dict]
    calculation_callable: str
    additive_column_patterns: list[str]
    record_types: dict[str, str]
    output_database: str
    postgres_url: str
    postgres_schema: str
    vertica: dict
    actor: str
    simulated_calculation_delay_seconds: float

    def column(self, key: str) -> str:
        """Translate a semantic field key to its physical database column.

        Example: ``column("isin")`` may return ``isin`` in Supabase and
        ``isin_code`` in the real Vertica configuration.
        """
        return self.fields[key]["column"]

    @property
    def output_columns(self) -> list[str]:
        """Return configured business and technical columns."""
        return [value["column"] for value in self.fields.values()] + list(self.technical_fields.values())

    @property
    def additive_columns(self) -> list[str]:
        """Return explicitly declared measures that a reversal must negate."""
        return [value["column"] for value in self.fields.values() if value.get("additive")]

    def is_additive(self, column: str) -> bool:
        """Check explicit declarations and reviewed column-name patterns."""
        return column in self.additive_columns or any(
            re.fullmatch(pattern, column) for pattern in self.additive_column_patterns
        )


def load_settings(path: str | Path | None = None) -> Settings:
    """Resolve database mode, YAML file and environment into one object.

    Example: when ``OUTPUT_DATABASE=postgres``, the default YAML is
    ``project.supabase.yaml`` and no Vertica connection is constructed.
    """
    output_database = os.getenv("OUTPUT_DATABASE")
    if not output_database:
        output_database = "postgres" if os.getenv("SUPABASE_DB_URL") else "vertica"
    configured_path = os.getenv("LIMON_PROJECT_CONFIG")
    default_name = "project.supabase.yaml" if output_database.lower() == "postgres" else "project.yaml"
    config_path = Path(path or configured_path or Path(__file__).with_name(default_name))
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    return Settings(
        project=raw["project"],
        fields=raw["fields"],
        technical_fields=raw["technical_fields"],
        display_fields=raw["display_fields"],
        editable_fields=raw.get("editable_fields", []),
        calculation_callable=raw["calculation"]["callable"],
        additive_column_patterns=raw.get("additive_column_patterns", []),
        record_types=raw.get(
            "record_types", {"base": "BASE", "reversal": "REVERSAL", "adjusted": "ADJUSTED"}
        ),
        output_database=output_database.lower(),
        postgres_url=_database_url(),
        postgres_schema=os.getenv("POSTGRES_SCHEMA", "adjustment_simple"),
        vertica={
            "host": os.getenv("VERTICA_HOST", ""),
            "port": int(os.getenv("VERTICA_PORT", "5433")),
            "database": os.getenv("VERTICA_DATABASE", ""),
            "user": os.getenv("VERTICA_USER", ""),
            "password": os.getenv("VERTICA_PASSWORD", ""),
            "connection_timeout": int(os.getenv("VERTICA_TIMEOUT", "10")),
        },
        actor=os.getenv("ADJUSTMENT_ACTOR", "limon-user"),
        simulated_calculation_delay_seconds=max(
            0.0, float(os.getenv("SIMULATED_CALCULATION_DELAY_SECONDS", "0"))
        ),
    )

if __name__ == "__main__":
    settings = load_settings()
    print(settings)
