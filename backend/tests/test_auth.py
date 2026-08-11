from fastapi import Depends, FastAPI, Request, Response
from fastapi.testclient import TestClient

from app.auth import (
    BUSINESS_WRITE,
    READ,
    TECHNICAL_ADMIN,
    MockLoginRequest,
    clear_session,
    create_mock_session,
    current_identity,
    require,
)


def auth_test_app():
    app = FastAPI()

    @app.post("/login")
    def login(request: MockLoginRequest, response: Response):
        return create_mock_session(response, request.username).public()

    @app.get("/me")
    def me(request: Request):
        return current_identity(request).public()

    @app.post("/logout", status_code=204)
    def logout(response: Response):
        clear_session(response)

    @app.get("/read")
    def read(identity=Depends(require(READ))):
        return identity.public()

    @app.post("/commit")
    def commit(identity=Depends(require(BUSINESS_WRITE))):
        return identity.public()

    @app.post("/reconcile")
    def reconcile(identity=Depends(require(TECHNICAL_ADMIN))):
        return identity.public()

    return app


def test_mock_login_uses_http_only_session_and_returns_identity(monkeypatch):
    monkeypatch.setenv("AUTH_MODE", "mock")
    monkeypatch.setenv("AUTH_SESSION_SECRET", "test-secret")
    client = TestClient(auth_test_app())

    response = client.post("/login", json={"username": "alice.reader"})

    assert response.status_code == 200
    assert response.json()["roles"] == ["reader"]
    assert "HttpOnly" in response.headers["set-cookie"]
    assert client.get("/me").json()["email"] == "alice.reader@cacib.example"


def test_roles_are_enforced_by_backend(monkeypatch):
    monkeypatch.setenv("AUTH_MODE", "mock")
    monkeypatch.setenv("AUTH_SESSION_SECRET", "test-secret")
    client = TestClient(auth_test_app())

    client.post("/login", json={"username": "alice.reader"})
    assert client.get("/read").status_code == 200
    assert client.post("/commit").status_code == 403
    assert client.post("/reconcile").status_code == 403

    client.post("/login", json={"username": "francois.functional"})
    assert client.post("/commit").status_code == 200
    assert client.post("/reconcile").status_code == 403

    client.post("/login", json={"username": "thomas.technical"})
    assert client.post("/commit").status_code == 403
    assert client.post("/reconcile").status_code == 200


def test_unauthorized_identity_is_authenticated_without_app_access(monkeypatch):
    monkeypatch.setenv("AUTH_MODE", "mock")
    monkeypatch.setenv("AUTH_SESSION_SECRET", "test-secret")
    client = TestClient(auth_test_app())

    response = client.post("/login", json={"username": "unauthorized.user"})

    assert response.status_code == 200
    assert response.json()["authenticated"] is True
    assert response.json()["hasAccess"] is False
    assert client.get("/read").status_code == 403


def test_logout_invalidates_browser_session(monkeypatch):
    monkeypatch.setenv("AUTH_MODE", "mock")
    monkeypatch.setenv("AUTH_SESSION_SECRET", "test-secret")
    client = TestClient(auth_test_app())
    client.post("/login", json={"username": "alice.reader"})

    assert client.post("/logout").status_code == 204
    assert client.get("/me").status_code == 401
