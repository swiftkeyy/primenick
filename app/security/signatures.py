from __future__ import annotations

import base64
import hashlib
import hmac
import time
from dataclasses import dataclass

from aiohttp import web

from app.core.settings import get_settings


@dataclass(frozen=True)
class SignatureDecision:
    ok: bool
    reason: str = "ok"


def verify_hmac_signature(body: bytes, signature: str | None, timestamp: str | None, secret: str, max_age_seconds: int = 300) -> SignatureDecision:
    if not signature or not timestamp:
        return SignatureDecision(False, "missing_signature")
    try:
        ts = int(timestamp)
    except ValueError:
        return SignatureDecision(False, "bad_timestamp")
    if abs(int(time.time()) - ts) > max_age_seconds:
        return SignatureDecision(False, "expired_signature")
    signed = f"{ts}.".encode() + body
    expected = base64.urlsafe_b64encode(hmac.new(secret.encode(), signed, hashlib.sha256).digest()).decode().rstrip("=")
    provided = signature.removeprefix("v1=")
    if not hmac.compare_digest(expected, provided):
        return SignatureDecision(False, "signature_mismatch")
    return SignatureDecision(True)


def verify_telegram_secret(request: web.Request) -> bool:
    return hmac.compare_digest(request.headers.get("X-Telegram-Bot-Api-Secret-Token", ""), get_settings().bot_webhook_secret)
