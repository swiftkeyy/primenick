from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import jwt

from app.core.settings import get_settings


def issue_internal_jwt(subject: str, claims: dict[str, Any], ttl_seconds: int = 300) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    payload = {"sub": subject, "iat": now, "exp": now + timedelta(seconds=ttl_seconds), **claims}
    return jwt.encode(payload, settings.jwt_secret_2026_05, algorithm="HS256", headers={"kid": settings.jwt_active_kid})


def decode_internal_jwt(token: str) -> dict[str, Any]:
    settings = get_settings()
    header = jwt.get_unverified_header(token)
    if header.get("kid") != settings.jwt_active_kid:
        raise jwt.InvalidTokenError("unknown kid")
    return jwt.decode(token, settings.jwt_secret_2026_05, algorithms=["HS256"], options={"require": ["exp", "iat", "sub"]})
