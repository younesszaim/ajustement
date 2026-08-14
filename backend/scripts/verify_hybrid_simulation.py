"""Run a recovery/idempotency smoke test against the Supabase hybrid simulator."""

from getpass import getpass
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parents[1]))

import psycopg
from psycopg.rows import dict_row

from app.adapters.hybrid_adjustment_repository import HybridAdjustmentRepository
from app.adapters.postgres_simulation_audit_repository import (
    PostgresSimulationAuditRepository,
)
from app.adapters.postgres_vertica_simulator import (
    PostgresVerticaSimulatorRepository,
)
from app.models import CommitRequest, LimonContext
from app.services import AdjustmentService, InfrastructureError
from app.mappings import build_mapping_provider

HOST = "db.szozfcqawdkfzugwrzdh.supabase.co"
IDEMPOTENCY_KEY = "hybrid-sim-recovery-verification-v2"


def main():
    password = getpass("Supabase database password: ")

    def connection():
        return psycopg.connect(
            host=HOST,
            port=5432,
            dbname="postgres",
            user="postgres",
            password=password,
            sslmode="require",
            connect_timeout=15,
            row_factory=dict_row,
        )

    output = PostgresVerticaSimulatorRepository(connection)
    audit = PostgresSimulationAuditRepository(connection)
    repository = HybridAdjustmentRepository(output, audit, "limon_ldp_bmf")
    service = AdjustmentService(repository, build_mapping_provider())

    existing = repository.get_idempotent(IDEMPOTENCY_KEY)
    if existing:
        result = existing
        print("Existing committed verification batch reused.")
    else:
        context = LimonContext(
            asofdate="2026-08-06", asofdateflow="2026-08-07T11:14:09"
        )
        preview = service.preview(context, "SIM-ROW-0002", {"amount": 761000})
        request = CommitRequest(
            context=context,
            rowId="SIM-ROW-0002",
            changes={"amount": 761000},
            reason="Hybrid recovery verification",
            expectedVersion=preview["rowVersion"],
            idempotencyKey=IDEMPOTENCY_KEY,
        )
        os.environ["SIMULATED_FAILURE_POINT"] = "AFTER_OUTPUT_COMMITTED"
        try:
            service.commit(request, "hybrid.verifier")
            raise AssertionError("Expected the simulated post-output failure.")
        except InfrastructureError as error:
            if "Simulated infrastructure failure" not in str(error):
                raise
            print("Simulated crash after output commit observed.")
        finally:
            os.environ.pop("SIMULATED_FAILURE_POINT", None)
        result = service.commit(request, "hybrid.verifier")
        assert service.commit(request, "hybrid.verifier") == result
        print("Retry recovered and repeated retry reused the committed result.")

    with connection() as database:
        request_row = database.execute(
            """SELECT status,batch_reference FROM adjustment_meta.requests
               WHERE idempotency_key=%s""",
            (IDEMPOTENCY_KEY,),
        ).fetchone()
        output_count = database.execute(
            """SELECT count(*) AS count FROM vertica_sim.output_completude_table
               WHERE adjustment_reference=%s""",
            (request_row["batch_reference"],),
        ).fetchone()["count"]
        net_amount = database.execute(
            """SELECT sum(amount) AS amount FROM vertica_sim.output_completude_table
               WHERE asofdate='2026-08-06' AND asofdateflow='2026-08-07 11:14:09'
                 AND trade_no='MX-441082'"""
        ).fetchone()["amount"]
        net_bucket = database.execute(
            """SELECT sum(eur_amount_3m) AS amount FROM vertica_sim.output_completude_table
               WHERE asofdate='2026-08-06' AND asofdateflow='2026-08-07 11:14:09'
                 AND trade_no='MX-441082'"""
        ).fetchone()["amount"]
        metadata_items = database.execute(
            """SELECT count(*) AS count FROM adjustment_meta.item_snapshots s
               JOIN adjustment_meta.batches b USING(adjustment_batch_id)
               WHERE b.batch_reference=%s""",
            (request_row["batch_reference"],),
        ).fetchone()["count"]

    assert request_row["status"] == "COMMITTED"
    assert output_count == 2
    assert float(net_amount) == 761000
    assert float(net_bucket) == 761000
    assert metadata_items == 1
    print(f"Result: {result}")
    print("Verified: 2 output rows, 1 metadata item, net Power BI amount and 3M bucket 761000.")


if __name__ == "__main__":
    main()
