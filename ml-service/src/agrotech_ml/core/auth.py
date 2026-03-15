from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
from datetime import UTC, datetime, timedelta
from typing import Any

from agrotech_ml.core.settings import AppSettings


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
