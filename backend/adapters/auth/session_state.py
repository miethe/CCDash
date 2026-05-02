"""Signed cookie helpers for hosted browser auth sessions."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass
from typing import Any, Mapping

from fastapi import Request, Response

from backend.config import AuthProviderConfig


STATE_COOKIE_SUFFIX = "_state"


@dataclass(frozen=True, slots=True)
class SignedCookieEnvelope:
    kind: str
    payload: Mapping[str, Any]
    issued_at: int
    expires_at: int


def new_token(bytes_count: int = 32) -> str:
    return secrets.token_urlsafe(bytes_count)


def sign_payload(
    payload: Mapping[str, Any],
    *,
    kind: str,
    secret: str,
    ttl_seconds: int,
    now: int | None = None,
) -> str:
    issued_at = int(time.time() if now is None else now)
    envelope = {
        "v": 1,
        "kind": kind,
        "iat": issued_at,
        "exp": issued_at + max(1, int(ttl_seconds)),
        "payload": dict(payload),
    }
    body = _b64encode(_json_bytes(envelope))
    signature = _signature(body, secret)
    return f"{body}.{signature}"


def verify_payload(
    value: str | None,
    *,
    kind: str,
    secret: str,
    now: int | None = None,
) -> SignedCookieEnvelope | None:
    raw = str(value or "").strip()
    if not raw or "." not in raw or not secret:
        return None
    body, signature = raw.rsplit(".", 1)
    expected = _signature(body, secret)
    if not hmac.compare_digest(signature, expected):
        return None
    try:
        decoded = json.loads(_b64decode(body).decode("utf-8"))
    except Exception:
        return None
    if not isinstance(decoded, dict) or decoded.get("kind") != kind:
        return None
    expires_at = _int_value(decoded.get("exp"))
    issued_at = _int_value(decoded.get("iat"))
    if expires_at is None or issued_at is None:
        return None
    checked_at = int(time.time() if now is None else now)
    if expires_at <= checked_at:
        return None
    payload = decoded.get("payload")
    if not isinstance(payload, Mapping):
        return None
    return SignedCookieEnvelope(
        kind=kind,
        payload=dict(payload),
        issued_at=issued_at,
        expires_at=expires_at,
    )


def read_session_cookie(
    request: Request,
    config: AuthProviderConfig,
    *,
    secret: str,
) -> SignedCookieEnvelope | None:
    return verify_payload(
        request.cookies.get(config.session_cookie_name),
        kind="auth_session",
        secret=secret,
    )


def set_session_cookie(
    response: Response,
    config: AuthProviderConfig,
    value: str,
    *,
    max_age_seconds: int,
) -> None:
    _set_cookie(response, config, config.session_cookie_name, value, max_age_seconds=max_age_seconds)


def clear_session_cookie(response: Response, config: AuthProviderConfig) -> None:
    _delete_cookie(response, config, config.session_cookie_name)


def state_cookie_name(config: AuthProviderConfig) -> str:
    return f"{config.session_cookie_name}{STATE_COOKIE_SUFFIX}"


def read_state_cookie(
    request: Request,
    config: AuthProviderConfig,
    *,
    secret: str,
) -> SignedCookieEnvelope | None:
    return verify_payload(
        request.cookies.get(state_cookie_name(config)),
        kind="auth_state",
        secret=secret,
    )


def set_state_cookie(
    response: Response,
    config: AuthProviderConfig,
    value: str,
    *,
    max_age_seconds: int,
) -> None:
    _set_cookie(response, config, state_cookie_name(config), value, max_age_seconds=max_age_seconds)


def clear_state_cookie(response: Response, config: AuthProviderConfig) -> None:
    _delete_cookie(response, config, state_cookie_name(config))


def _set_cookie(
    response: Response,
    config: AuthProviderConfig,
    name: str,
    value: str,
    *,
    max_age_seconds: int,
) -> None:
    response.set_cookie(
        name,
        value,
        max_age=max_age_seconds,
        httponly=True,
        secure=bool(config.session_cookie_secure),
        samesite=str(config.session_cookie_samesite),
        domain=config.session_cookie_domain or None,
        path="/",
    )


def _delete_cookie(response: Response, config: AuthProviderConfig, name: str) -> None:
    response.delete_cookie(
        name,
        domain=config.session_cookie_domain or None,
        path="/",
        secure=bool(config.session_cookie_secure),
        samesite=str(config.session_cookie_samesite),
        httponly=True,
    )


def _json_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def _signature(body: str, secret: str) -> str:
    digest = hmac.new(secret.encode("utf-8"), body.encode("ascii"), hashlib.sha256).digest()
    return _b64encode(digest)


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(f"{value}{padding}")


def _int_value(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
