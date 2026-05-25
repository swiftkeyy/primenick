from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.settings import get_settings
from app.db.redis import get_redis
from app.models.username import AvailabilityCheck
from app.monitoring.metrics import AVAILABILITY
from app.services.circuit_breaker import CircuitBreaker
from app.services.proxy_pool import ProxyPool

@dataclass(frozen=True)
class AvailabilityResult:
    username: str
    platform: str
    available: bool | None
    status_code: int | None
    latency_ms: int
    error_class: str | None = None


class AvailabilityChecker:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.redis = get_redis()
        self.proxy_pool = ProxyPool(self.redis)

    async def check(self, username: str, platform: str, user_id: str | None = None) -> AvailabilityResult:
        cb = CircuitBreaker(self.redis, f"availability:{platform}")
        if not await cb.allow():
            return AvailabilityResult(username, platform, None, None, 0, "CircuitOpen")
        start = time.perf_counter()
        try:
            if platform == "telegram":
                result = await self._telegram(username)
            else:
                result = await self._http_profile(username, platform)
            await cb.success()
        except Exception as exc:
            await cb.failure()
            result = AvailabilityResult(username, platform, None, None, int((time.perf_counter() - start) * 1000), exc.__class__.__name__)
        self.session.add(AvailabilityCheck(normalized=username.lower(), platform=platform, requested_by_user_id=user_id, available=result.available, status_code=result.status_code, latency_ms=result.latency_ms, error_class=result.error_class))
        AVAILABILITY.labels(platform=platform, result=str(result.available)).inc()
        return result

    async def _telegram(self, username: str) -> AvailabilityResult:
        # Pyrogram imports sync helpers that call asyncio.get_event_loop() at import time.
        # Import lazily inside a running coroutine so uvloop/Python 3.13 always has a current loop.
        from pyrogram import Client
        from pyrogram.errors import FloodWait, UsernameInvalid, UsernameOccupied

        settings = get_settings()
        start = time.perf_counter()
        async with Client(settings.pyrogram_session_name, api_id=settings.telegram_api_id, api_hash=settings.telegram_api_hash, in_memory=False) as app:
            try:
                await asyncio.wait_for(app.get_users(username), timeout=8)
                return AvailabilityResult(username, "telegram", False, 200, int((time.perf_counter()-start)*1000))
            except UsernameInvalid:
                return AvailabilityResult(username, "telegram", False, 400, int((time.perf_counter()-start)*1000), "UsernameInvalid")
            except UsernameOccupied:
                return AvailabilityResult(username, "telegram", False, 409, int((time.perf_counter()-start)*1000), "UsernameOccupied")
            except FloodWait as e:
                raise RuntimeError(f"TelegramFloodWait:{e.value}") from e
            except Exception as e:
                if "PEER_ID_INVALID" in str(e).upper() or "USERNAME_NOT_OCCUPIED" in str(e).upper():
                    return AvailabilityResult(username, "telegram", True, 404, int((time.perf_counter()-start)*1000))
                raise

    async def _http_profile(self, username: str, platform: str) -> AvailabilityResult:
        urls = {"instagram": f"https://www.instagram.com/{username}/", "tiktok": f"https://www.tiktok.com/@{username}"}
        if platform not in urls:
            raise ValueError("unsupported_platform")
        proxy = await self.proxy_pool.choose(platform)
        headers = {"User-Agent": "PrimeNickAvailabilityBot/1.0 (+compliance-contact@example.com)", "Accept": "text/html,application/xhtml+xml", "Accept-Language": "en-US,en;q=0.7"}
        start = time.perf_counter()
        async with httpx.AsyncClient(http2=True, timeout=httpx.Timeout(8.0, connect=2.0), proxies=proxy.url, headers=headers, follow_redirects=False) as client:
            resp = await client.get(urls[platform])
        await self.proxy_pool.report(proxy, resp.status_code in {200, 404}, platform)
        available = True if resp.status_code == 404 else False if resp.status_code in {200, 301, 302} else None
        return AvailabilityResult(username, platform, available, resp.status_code, int((time.perf_counter()-start)*1000))
