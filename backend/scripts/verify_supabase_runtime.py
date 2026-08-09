"""Read-only smoke test for the same repository used by FastAPI."""

from getpass import getpass
from pathlib import Path
import sys
import psycopg
from psycopg.rows import dict_row

sys.path.insert(0, str(Path(__file__).parents[1]))
from app.adapters.postgres_adjustment_repository import PostgresAdjustmentRepository
from app.models import LimonContext


def main():
    password = getpass("Supabase database password: ")

    def connect():
        return psycopg.connect(
            host="db.szozfcqawdkfzugwrzdh.supabase.co",
            port=5432,
            dbname="postgres",
            user="postgres",
            password=password,
            sslmode="require",
            row_factory=dict_row,
        )

    repo = PostgresAdjustmentRepository(connect, "limon_ldp_bmf")
    dates = repo.asofdates()
    print("As Of Dates:", dates)
    for date in dates:
        print(f"Versions for {date}:", repo.versions(date))
    context = LimonContext(asofdate="2026-08-06", asofdateflow="2026-08-07T04:45:02")
    rows, total = repo.search(context, "OT-982731", "Orchestrade", 1, 10)
    print(
        f"Filtered repository search: total={total}, trade={rows[0]['tradeNo'] if rows else None}, role={rows[0]['lineageRole'] if rows else None}"
    )


if __name__ == "__main__":
    main()
