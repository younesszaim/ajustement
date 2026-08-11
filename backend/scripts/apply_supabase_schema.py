"""Apply the reviewed schema without placing database credentials in shell history."""

from getpass import getpass
from pathlib import Path
import psycopg

HOST = "db.szozfcqawdkfzugwrzdh.supabase.co"
PORT = 5432
DATABASE = "postgres"
USER = "postgres"


def main():
    password = getpass("Supabase database password: ")
    migration_dir = Path(__file__).parents[1] / "migrations"
    with psycopg.connect(
        host=HOST,
        port=PORT,
        dbname=DATABASE,
        user=USER,
        password=password,
        sslmode="require",
        connect_timeout=15,
    ) as connection:
        for migration in sorted(migration_dir.glob("*.sql")):
            connection.execute(migration.read_text())
            print(f"Applied {migration.name}")
        rows = connection.execute("""SELECT table_name FROM information_schema.tables
          WHERE table_schema='public' AND (table_name='out_completude_ldp_bmf' OR table_name LIKE 'adjustment_%')
          ORDER BY table_name""").fetchall()
        views = connection.execute("""SELECT table_name FROM information_schema.views
          WHERE table_schema='public' AND table_name IN ('v_out_completude_ldp_bmf_current','v_adjustment_register')
          ORDER BY table_name""").fetchall()
        print(f"Schema applied. Verified {len(rows)} tables and {len(views)} views.")
        for (name,) in rows + views:
            print(name)
        counts = connection.execute("""SELECT
          (SELECT count(*) FROM public.out_completude_ldp_bmf) AS output_rows,
          (SELECT count(*) FROM public.adjustment_batches) AS adjustment_batches,
          (SELECT count(*) FROM public.adjustment_action_events) AS action_events""").fetchone()
        print(
            f"Data counts: output_rows={counts[0]}, adjustment_batches={counts[1]}, action_events={counts[2]}"
        )
        simulation = connection.execute("""SELECT
          (SELECT count(*) FROM vertica_sim.output_completude_table) AS output_rows,
          (SELECT count(*) FROM adjustment_meta.requests) AS requests,
          (SELECT count(*) FROM adjustment_meta.batches) AS batches,
          (SELECT count(*) FROM adjustment_meta.item_snapshots) AS snapshots""").fetchone()
        print(
            "Hybrid simulation: "
            f"output_rows={simulation[0]}, requests={simulation[1]}, "
            f"batches={simulation[2]}, snapshots={simulation[3]}"
        )


if __name__ == "__main__":
    main()
