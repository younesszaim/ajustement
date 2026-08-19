from fastapi.testclient import TestClient

from streamlit_app import api
from streamlit_app.config import load_settings


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
    pass


def test_context_search_and_register_routes(monkeypatch):
    settings = load_settings()
    monkeypatch.setattr(
        api, "build_runtime", lambda: (settings, OutputStub(), OperationsStub(), ServiceStub())
    )
    client = TestClient(api.app)

    assert client.get("/health").status_code == 200
    assert client.get("/contexts/asofdates").json()["items"] == ["2026-08-06"]
    response = client.get(
        "/trades",
        params={
            "asofdate": "2026-08-06",
            "version": "2026-08-07T11:14:09",
            "fo_system": "Murex",
            "leg_flag": 0,
        },
    )
    assert response.status_code == 200
    assert response.json()["items"][0]["output_record_id"] == "ROW-1"
    assert client.get("/adjustments").json()["items"][0]["status"] == "COMMITTED"
