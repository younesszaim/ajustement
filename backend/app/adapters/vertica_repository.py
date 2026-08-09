"""Vertica boundary for real LiMon `output_completude_table`.

Replace the connection factory with the existing enterprise utility and map
logical names only in `VerticaColumnMap`; React never sees physical columns.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class VerticaColumnMap:
    table: str = "output_completude_table"
    asofdate: str = "asofdate"
    asofdateflow: str = "asofdateflow"
    source_row_id: str = "source_row_id"
    trade_no: str = "tradeno"
    fo_system: str = "fo_system"
    record_type: str = "record_type"
    batch_reference: str = "adjustment_batch_id"
    row_version: str = "row_version"


class VerticaLimonRepository:
    def __init__(
        self, connection_factory, columns=VerticaColumnMap(), domain_mapper=None
    ):
        self.connection_factory = connection_factory
        self.columns = columns
        self.domain_mapper = domain_mapper

    def asofdates(self):
        raise NotImplementedError(
            "Use SELECT DISTINCT against the mapped LiMon output table."
        )

    def versions(self, asofdate):
        raise NotImplementedError("Return exact timestamps sorted newest first.")

    def search(self, context, search, fo_system, page, page_size):
        raise NotImplementedError(
            "Use server-side Vertica filtering/pagination and expand associated adjustment rows."
        )

    def get_effective_trade(self, context, row_id):
        raise NotImplementedError(
            "Resolve the latest BASE/ADJUSTMENT_REPLACEMENT for this exact context."
        )

    def get_lineage(self, context, row_id):
        raise NotImplementedError(
            "Return original, cancellation and replacement rows from Vertica."
        )

    def get_rows_by_batch_reference(self, batch_reference):
        raise NotImplementedError(
            "Required by recovery after a cross-database failure."
        )

    def insert_adjustment_rows(self, context, batch_reference, rows, user):
        """Insert every cancellation/replacement row in one native Vertica transaction.

        The real implementation must enforce a unique batch-reference/record-type/
        source-row key so retries are idempotent.
        """
        raise NotImplementedError("Wire to the existing LiMon Vertica insert utility.")
