"""Apply migrations for the vertica_sim and adjustment_meta schemas."""

import os
from pathlib import Path

import psycopg
from dotenv import load_dotenv


BACKEND_DIR = Path(__file__).resolve().parents[1]
load_dotenv(BACKEND_DIR.parent / ".env")


def main():
    url = os.getenv("DATABASE_URL")
    if not url:
        raise SystemExit("DATABASE_URL is required")
    with psycopg.connect(url, connect_timeout=15) as connection:
        for migration in sorted((BACKEND_DIR / "migrations").glob("*.sql")):
            connection.execute(migration.read_text())
            print(f"Applied {migration.name}")
        counts = connection.execute("""SELECT
          (SELECT count(*) FROM vertica_sim.output_completude_table),
          (SELECT count(*) FROM adjustment_meta.requests),
          (SELECT count(*) FROM adjustment_meta.batches),
          (SELECT count(*) FROM adjustment_meta.item_snapshots)""").fetchone()
        print(
            "Simulation storage: "
            f"output_rows={counts[0]}, requests={counts[1]}, "
            f"batches={counts[2]}, snapshots={counts[3]}"
        )


if __name__ == "__main__":
    main()
