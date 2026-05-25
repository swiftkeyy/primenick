from __future__ import annotations

import hashlib
import hmac

from app.core.settings import get_settings


def stable_hmac(value: str) -> str:
    secret = get_settings().internal_hmac_secret.encode()
    return hmac.new(secret, value.encode(), hashlib.sha256).hexdigest()
