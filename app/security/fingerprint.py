from __future__ import annotations

import hashlib
from aiohttp import web

SALT_VERSION = "fpv1"


def request_fingerprint(request: web.Request, telegram_id: int | None = None) -> str:
    headers = request.headers
    material = "|".join([
        SALT_VERSION,
        str(telegram_id or "anon"),
        headers.get("User-Agent", "")[:160],
        headers.get("Accept-Language", "")[:64],
        headers.get("CF-IPCountry", "")[:8],
        headers.get("Sec-CH-UA-Platform", "")[:64],
    ])
    return hashlib.blake2b(material.encode(), digest_size=16).hexdigest()
