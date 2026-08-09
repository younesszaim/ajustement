"""Read-only diagnostic for live adjustment/revert lineage."""

from getpass import getpass
from pathlib import Path
import sys, psycopg
from psycopg.rows import dict_row

sys.path.insert(0, str(Path(__file__).parents[1]))


def main():
    password = getpass("Supabase database password: ")
    with psycopg.connect(
        host="db.szozfcqawdkfzugwrzdh.supabase.co",
        port=5432,
        dbname="postgres",
        user="postgres",
        password=password,
        sslmode="require",
        row_factory=dict_row,
    ) as c:
        rows = c.execute("""SELECT b.adjustment_batch_id,b.batch_reference,b.action_type,b.status,b.base_asofdate,b.base_asofdateflow,b.created_at,b.created_by,b.reverted_adjustment_batch_id,i.source_row_id,i.trade_no
    FROM public.adjustment_batches b JOIN public.adjustment_batch_items i USING(adjustment_batch_id)
    ORDER BY b.created_at DESC""").fetchall()
        print(f"Adjustment items: {len(rows)}")
        for r in rows:
            print({k: (str(v) if v is not None else None) for k, v in r.items()})


if __name__ == "__main__":
    main()
