"""Storage contracts used by LiMon adjustment orchestration.

Real LiMon implementations should satisfy these protocols with the existing
enterprise Vertica connection and calculation libraries.
"""

from typing import Any, Protocol


class LimonOutputRepository(Protocol):
    def asofdates(self) -> list[str]: ...
    def versions(self, asofdate: str) -> list[str]: ...
    def search(
        self, context, search: str, fo_system: str, page: int, page_size: int
    ) -> tuple[list[dict[str, Any]], int]: ...
    def fo_systems(self, context) -> list[str]: ...
    def batch_search(
        self, context, fo_system: str, filters: dict, page: int, page_size: int
    ) -> tuple[list[dict[str, Any]], int]: ...
    def get_effective_trade(self, context, row_id: str) -> dict[str, Any]: ...
    def get_lineage(self, context, row_id: str) -> dict[str, Any]: ...
    def get_rows_by_batch_reference(
        self, batch_reference: str
    ) -> list[dict[str, Any]]: ...
    def insert_adjustment_rows(
        self, context, batch_reference: str, rows: list[dict[str, Any]], user: str
    ) -> list[str]: ...


class AdjustmentAuditRepository(Protocol):
    def reserve_request(
        self,
        project_key: str,
        idempotency_key: str,
        context,
        user: str,
        reason: str,
        item_count: int,
        action_type: str = "ADJUSTMENT",
        reverted_batch_id: str | None = None,
    ) -> dict[str, Any]: ...
    def mark_vertica_committed(
        self, request_id: str, external_record_ids: list[str]
    ) -> None: ...
    def finalize_request(
        self, request_id: str, batch: dict[str, Any], items: list[dict[str, Any]]
    ) -> dict[str, Any]: ...
    def mark_request_failed(
        self, request_id: str, error_code: str, error_message: str
    ) -> None: ...
    def get_idempotent_result(
        self, project_key: str, idempotency_key: str
    ) -> dict[str, Any] | None: ...
    def get_history(self, project_key: str, row_id: str) -> list[dict[str, Any]]: ...
    def get_global_history(
        self, project_key: str, asofdate: str = "", asofdateflow: str = ""
    ) -> list[dict[str, Any]]: ...
    def get_recovery_request_by_batch_reference(
        self, project_key: str, batch_reference: str
    ) -> dict[str, Any] | None: ...
    def record_action(
        self,
        event_type: str,
        user: str,
        metadata: dict[str, Any],
        context=None,
        source_row_id: str | None = None,
        status: str = "SUCCESS",
    ) -> None: ...
