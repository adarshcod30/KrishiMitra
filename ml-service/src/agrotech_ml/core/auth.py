from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import HTTPException, Request, status

from agrotech_ml.core.settings import AppSettings, get_settings


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes:
    padding = "=" * ((4 - len(data) % 4) % 4)
    return base64.urlsafe_b64decode(data + padding)


def hash_password(password: str, *, iterations: int = 600_000) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"pbkdf2_sha256${iterations}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        algorithm, iterations, salt_hex, digest_hex = stored_hash.split("$", 3)
    except ValueError:
        return False

    if algorithm != "pbkdf2_sha256":
        return False

    candidate = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        bytes.fromhex(salt_hex),
        int(iterations),
    )
    return hmac.compare_digest(candidate.hex(), digest_hex)


def authenticate_admin(settings: AppSettings, username: str, password: str) -> bool:
    if not settings.admin_username or username != settings.admin_username:
        return False

    if settings.admin_password_hash:
        return verify_password(password, settings.admin_password_hash)

    if settings.admin_password:
        return hmac.compare_digest(password, settings.admin_password)

    return False


def create_access_token(
    settings: AppSettings,
    *,
    subject: str,
    role: str = "admin",
) -> tuple[str, int]:
    if not settings.jwt_secret:
        raise RuntimeError("JWT secret is not configured")

    now = datetime.now(UTC)
    expires_at = now + timedelta(minutes=settings.access_token_ttl_minutes)

    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": subject,
        "role": role,
        "iss": "agrotech-ml",
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
    }

    signing_input = (
        f"{_b64url_encode(json.dumps(header, separators=(',', ':')).encode('utf-8'))}."
        f"{_b64url_encode(json.dumps(payload, separators=(',', ':')).encode('utf-8'))}"
    )
    signature = hmac.new(
        settings.jwt_secret.encode("utf-8"),
        signing_input.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    token = f"{signing_input}.{_b64url_encode(signature)}"
    return token, int((expires_at - now).total_seconds())


def decode_access_token(settings: AppSettings, token: str) -> dict[str, Any]:
    if not settings.jwt_secret:
        raise ValueError("JWT secret is not configured")

    try:
        header_segment, payload_segment, signature_segment = token.split(".", 2)
    except ValueError as exc:
        raise ValueError("Malformed access token") from exc

    signing_input = f"{header_segment}.{payload_segment}"
    expected_signature = hmac.new(
        settings.jwt_secret.encode("utf-8"),
        signing_input.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    provided_signature = _b64url_decode(signature_segment)

    if not hmac.compare_digest(expected_signature, provided_signature):
        raise ValueError("Invalid token signature")

    payload = json.loads(_b64url_decode(payload_segment).decode("utf-8"))
    exp = int(payload.get("exp", 0))
    if exp and datetime.now(UTC).timestamp() > exp:
        raise ValueError("Access token has expired")

    return payload


# ---------------------------------------------------------------------------
# FastAPI integration
#
# ``require_write_auth`` is the single switch. When it is false (the local
# development default) every dependency below is a pass-through, so behaviour
# is byte-for-byte unchanged without any GCP/Secret Manager configuration.
# When it is true, a valid ``Authorization: Bearer <jwt>`` header is mandatory.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AuthContext:
    """Who (if anyone) is behind the current request."""

    authenticated: bool = False
    subject: str | None = None
    role: str | None = None
    enforced: bool = False

    @property
    def actor_type(self) -> str:
        return "user" if self.authenticated else "anonymous"


ANONYMOUS = AuthContext()

_UNAUTHENTICATED_HEADERS = {"WWW-Authenticate": "Bearer"}


def bearer_token(request: Request) -> str | None:
    """Return the bearer credential of the request, or ``None``."""
    header = request.headers.get("authorization") or ""
    scheme, _, credential = header.partition(" ")
    credential = credential.strip()
    if scheme.lower() != "bearer" or not credential:
        return None
    return credential


def resolve_auth_context(request: Request, settings: AppSettings) -> AuthContext:
    """Validate the request credential according to ``settings``.

    Raises ``HTTPException(401)`` only when write auth is switched on.
    """
    enforced = bool(settings.require_write_auth)
    token = bearer_token(request)

    if token and settings.jwt_secret:
        try:
            payload = decode_access_token(settings, token)
        except ValueError as exc:
            if enforced:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail=str(exc),
                    headers=_UNAUTHENTICATED_HEADERS,
                ) from exc
            return AuthContext(enforced=enforced)
        return AuthContext(
            authenticated=True,
            subject=str(payload.get("sub")) if payload.get("sub") else None,
            role=str(payload.get("role")) if payload.get("role") else None,
            enforced=enforced,
        )

    if enforced:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. POST /auth/login to obtain a bearer token.",
            headers=_UNAUTHENTICATED_HEADERS,
        )

    return AuthContext(enforced=enforced)


def require_auth(request: Request) -> AuthContext:
    """FastAPI dependency guarding mutating and PII routes."""
    return resolve_auth_context(request, get_settings())


def optional_auth(request: Request) -> AuthContext:
    """Identify the caller without ever rejecting the request."""
    settings = get_settings()
    token = bearer_token(request)
    if not token or not settings.jwt_secret:
        return AuthContext(enforced=bool(settings.require_write_auth))
    try:
        payload = decode_access_token(settings, token)
    except ValueError:
        return AuthContext(enforced=bool(settings.require_write_auth))
    return AuthContext(
        authenticated=True,
        subject=str(payload.get("sub")) if payload.get("sub") else None,
        role=str(payload.get("role")) if payload.get("role") else None,
        enforced=bool(settings.require_write_auth),
    )


def login(settings: AppSettings, username: str, password: str) -> tuple[str, int]:
    """Authenticate an operator and mint an access token.

    Raises ``HTTPException`` so the route handler stays a one-liner.
    """
    if not settings.jwt_secret or not settings.admin_username:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Login is not configured. Set AGROTECH_JWT_SECRET, AGROTECH_ADMIN_USERNAME "
                "and AGROTECH_ADMIN_PASSWORD_HASH."
            ),
        )

    if not authenticate_admin(settings, username, password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
            headers=_UNAUTHENTICATED_HEADERS,
        )

    return create_access_token(settings, subject=username, role="admin")


__all__ = [
    "ANONYMOUS",
    "AuthContext",
    "authenticate_admin",
    "bearer_token",
    "create_access_token",
    "decode_access_token",
    "hash_password",
    "login",
    "optional_auth",
    "require_auth",
    "resolve_auth_context",
    "verify_password",
]
