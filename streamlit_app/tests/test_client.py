"""HTTP-client behavior that differs from the common request defaults."""

from streamlit_app.client import AdjustmentApiClient
from streamlit_app.models import AdjustmentDraft, Context


def test_commit_uses_long_timeout_without_changing_normal_client_timeout(monkeypatch):
    """A slow durable commit gets 120s while ordinary reads retain 30s."""
    calls = []

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"operation_id": "OP-1", "status": "COMMITTED"}

    def request(method, url, **kwargs):
        calls.append((method, url, kwargs))
        return Response()

    monkeypatch.setattr("streamlit_app.client.httpx.request", request)
    client = AdjustmentApiClient("http://api.example", timeout=30.0)
    context = Context("2026-08-06", "V1", "Murex", 1)
    draft = AdjustmentDraft("ROW-1", 150.0, "Correction", "KEY-1", {})

    client.commit(context, draft)

    assert calls[0][2]["timeout"] == 120.0
    assert client.timeout == 30.0
