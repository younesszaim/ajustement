from fastapi.testclient import TestClient
from psycopg import OperationalError

import app.main as main


def authenticated_client():
    client = TestClient(main.app, raise_server_exceptions=False)
    response = client.post(
        "/api/auth/mock-login",
        json={"username": "francois.functional"},
    )
    assert response.status_code == 200
    return client
def test_asofdates_route_returns_repository_dates(monkeypatch):
    class Repository:
        def asofdates(self):
            return ["2026-08-06"]

    monkeypatch.setattr(main, "repo", Repository())
    response = authenticated_client().get("/api/asofdates")
    assert response.status_code == 200
    assert response.json() == ["2026-08-06"]


def test_missing_database_configuration_is_actionable_503(monkeypatch):
    class Repository:
        def asofdates(self):
            raise RuntimeError("DATABASE_URL is required")

    monkeypatch.setattr(main, "repo", Repository())
    response = authenticated_client().get("/api/asofdates")
    assert response.status_code == 503
    assert response.json()["code"] == "BACKEND_CONFIGURATION_ERROR"


def test_database_authentication_failure_is_safe_and_actionable(monkeypatch):
    class Repository:
        def asofdates(self):
            raise OperationalError("password authentication failed for user postgres")

    monkeypatch.setattr(main, "repo", Repository())
    response = authenticated_client().get("/api/asofdates")
    assert response.status_code == 503
    assert response.json()["code"] == "DATABASE_AUTHENTICATION_FAILED"
    assert "password" in response.json()["detail"].lower()


def test_macos_dns_failure_is_classified(monkeypatch):
    class Repository:
        def asofdates(self):
            raise OperationalError("nodename nor servname provided, or not known")

    monkeypatch.setattr(main, "repo", Repository())
    response = authenticated_client().get("/api/asofdates")
    assert response.status_code == 503
    assert response.json()["code"] == "DATABASE_HOST_NOT_FOUND"
