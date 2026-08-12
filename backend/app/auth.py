"""Authentication boundary used by the mock SSO and future enterprise SSO.

The application consumes one stable identity model. Development uses signed,
HTTP-only mock sessions; production can replace the provider without changing
business services or authorization rules.
"""

from __future__ import annotations

from base64 import urlsafe_b64decode, urlsafe_b64encode
from dataclasses import asdict, dataclass
from hashlib import sha256
import hmac
import json
import os
import time
from typing import Callable

from fastapi import HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict


SESSION_COOKIE = "limon_session"
SESSION_TTL_SECONDS = 8 * 60 * 60

READ = "read"
PREVIEW = "preview"
BUSINESS_WRITE = "business_write"
TECHNICAL_ADMIN = "technical_admin"

ROLE_PERMISSIONS = {
    "reader": {READ, PREVIEW},
    "functional_admin": {READ, PREVIEW, BUSINESS_WRITE},
    "technical_admin": {READ, PREVIEW, TECHNICAL_ADMIN},
}


@dataclass(frozen=True)
class Identity:
    userId: str
    email: str
    displayName: str
    roles: tuple[str, ...]

    @property
    def permissions(self):
        return set().union(*(ROLE_PERMISSIONS.get(role, set()) for role in self.roles))

    @property
    def has_access(self):
        return bool(self.permissions)

    def public(self):
        return {
            **asdict(self),
            "roles": list(self.roles),
            "permissions": sorted(self.permissions),
            "authenticated": True,
            "hasAccess": self.has_access,
        }


MOCK_USERS = {
    "alice.reader": Identity(
        "mock-reader-001", "alice.reader@cacib.example", "Alice Reader", ("reader",)
    ),
    "francois.functional": Identity(
        "mock-functional-001",
        "francois.functional@cacib.example",
        "François Functional",
        ("functional_admin",),
    ),
    "thomas.technical": Identity(
        "mock-technical-001",
        "thomas.technical@cacib.example",
        "Thomas Technical",
        ("technical_admin",),
    ),
    "unauthorized.user": Identity(
        "mock-unauthorized-001",
        "unauthorized.user@cacib.example",
        "Unauthorized User",
        (),
    ),
}


class MockLoginRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={"example": {"username": "francois.functional"}}
    )

    username: str


def auth_mode():
    return os.getenv("AUTH_MODE", "mock").lower()


def _secret():
    configured = os.getenv("AUTH_SESSION_SECRET")
    if configured:
        return configured.encode()
    if auth_mode() != "mock":
        raise RuntimeError("AUTH_SESSION_SECRET is required outside mock mode.")
    return b"limon-local-development-session-secret"


def _encode(payload):
    body = urlsafe_b64encode(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    ).decode().rstrip("=")
    signature = urlsafe_b64encode(
        hmac.new(_secret(), body.encode(), sha256).digest()
    ).decode().rstrip("=")
    return f"{body}.{signature}"


def _decode(token):
    try:
        body, signature = token.split(".", 1)
        expected = urlsafe_b64encode(
            hmac.new(_secret(), body.encode(), sha256).digest()
        ).decode().rstrip("=")
        if not hmac.compare_digest(signature, expected):
            return None
        padded = body + "=" * (-len(body) % 4)
        payload = json.loads(urlsafe_b64decode(padded).decode())
        if payload["expiresAt"] < int(time.time()):
            return None
        return payload
    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        return None


def create_mock_session(response: Response, username: str):
    if auth_mode() != "mock":
        raise HTTPException(404, "Mock login is disabled.")
    identity = MOCK_USERS.get(username)
    if not identity:
        raise HTTPException(401, "Unknown mock SSO identity.")
    token = _encode(
        {"username": username, "expiresAt": int(time.time()) + SESSION_TTL_SECONDS}
    )
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=SESSION_TTL_SECONDS,
        httponly=True,
        secure=os.getenv("AUTH_COOKIE_SECURE", "false").lower() == "true",
        samesite="lax",
        path="/",
    )
    return identity


def clear_session(response: Response):
    response.delete_cookie(SESSION_COOKIE, path="/")


def current_identity(request: Request):
    if auth_mode() != "mock":
        raise HTTPException(503, "The enterprise SSO provider is not configured.")
    token = request.cookies.get(SESSION_COOKIE)
    payload = _decode(token) if token else None
    identity = MOCK_USERS.get(payload["username"]) if payload else None
    if not identity:
        raise HTTPException(401, "Authentication required.")
    return identity


def require(permission: str) -> Callable:
    def dependency(request: Request):
        identity = current_identity(request)
        if permission not in identity.permissions:
            raise HTTPException(
                403,
                f'Access denied. Permission "{permission}" is required.',
            )
        return identity

    return dependency
