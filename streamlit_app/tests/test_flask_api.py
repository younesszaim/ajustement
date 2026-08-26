from streamlit_app.config import load_settings
from streamlit_app.flask_api import create_app
from streamlit_app.models import Preview
from streamlit_app.service import AdjustmentError


class OutputStub:
    def context_values(self, key, filters=None):
        return {
            "asofdate": ["2026-08-06"],
            "version": ["2026-08-07T11:14:09"],
            "fo_system": ["Murex"],
        }[key]

    def search_active(self, context, search, limit):
        return [{"output_record_id": "ROW-1", "trade_no": "T-100"}]


class OperationsStub:
    def list_recent(self, limit):
        return [{"operation_id": "OP-1", "status": "COMMITTED"}]


class ServiceStub:
    def preview(self, context, draft, **kwargs):
        row = {"output_record_id": draft.source_output_id}
        return Preview(row, row, row, ["calculate_buckets"])

    def commit(self, context, draft):
        if draft.reason == "conflict":
            raise AdjustmentError("The row is stale")
        return {"operation_id": "OP-1", "status": "COMMITTED"}

    def commit_cancel(self, context, draft):
        return {
            "operation_id": "CANCEL-OP-1",
            "status": "COMMITTED",
            "output_ids": [f"REV-{draft.idempotency_key}"],
        }

    def revert(self, operation_id, reason, idempotency_key):
        return {"operation_id": "REV-OP-1", "status": "COMMITTED"}


def runtime_stub():
    return load_settings(), OutputStub(), OperationsStub(), ServiceStub()


def adjustment_json(reason="Correction"):
    return {
        "context": {
            "asofdate": "2026-08-06",
            "version": "2026-08-07T11:14:09",
            "fo_system": "Murex",
            "leg_flag": 0,
        },
        "source_output_id": "ROW-1",
        "new_amount": 250.0,
        "reason": reason,
        "idempotency_key": "intent-1",
        "changes": {"exposure_class": "CORPORATE"},
    }


def test_flask_routes_keep_the_fastapi_http_contract():
    client = create_app(runtime_stub).test_client()

    assert client.get("/health").status_code == 200
    assert client.get("/contexts/asofdates").json["items"] == ["2026-08-06"]
    search = client.get(
        "/trades",
        query_string={
            "asofdate": "2026-08-06",
            "version": "2026-08-07T11:14:09",
            "fo_system": "Murex",
            "leg_flag": 0,
        },
    )
    assert search.status_code == 200
    assert search.json["items"][0]["output_record_id"] == "ROW-1"
    assert client.post("/adjustments/preview", json=adjustment_json()).status_code == 200
    assert client.post("/adjustments/commit", json=adjustment_json()).json["status"] == "COMMITTED"
    cancellation = client.post(
        "/adjustments/cancel",
        json={
            "context": adjustment_json()["context"],
            "source_output_id": "ROW-1",
            "reason": "Cancel duplicate trade",
            "idempotency_key": "cancel-1",
        },
    )
    assert cancellation.status_code == 200
    assert cancellation.json["output_ids"] == ["REV-cancel-1"]
    assert client.get("/adjustments").json["items"][0]["operation_id"] == "OP-1"
    revert = client.post(
        "/adjustments/OP-1/revert",
        json={"reason": "Undo", "idempotency_key": "revert-1"},
    )
    assert revert.status_code == 200


def test_flask_manually_translates_validation_domain_and_runtime_errors():
    client = create_app(runtime_stub).test_client()

    invalid = client.post("/adjustments/commit", json={})
    assert invalid.status_code == 422
    assert isinstance(invalid.json["detail"], list)

    conflict = client.post("/adjustments/commit", json=adjustment_json("conflict"))
    assert conflict.status_code == 409
    assert conflict.json == {"detail": "The row is stale"}

    unavailable = create_app(lambda: (_ for _ in ()).throw(RuntimeError("secret"))).test_client()
    response = unavailable.get("/health")
    assert response.status_code == 503
    assert response.json == {"detail": "Database configuration is unavailable"}
