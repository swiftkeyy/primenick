from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from ipaddress import ip_address

from redis.asyncio import Redis
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.abuse import AbuseEvent, Ban
from app.models.enums import AbuseSeverity, BanScope, UserTier
from app.models.user import User
from app.monitoring.metrics import ABUSE_EVENTS
from app.security.proxy import subnet24


@dataclass(frozen=True)
class Actor:
    telegram_id: int | None
    user_id: str | None
    ip: str
    fingerprint: str
    tier: UserTier = UserTier.FREE
    abuse_score: int = 0


class AbuseService:
    def __init__(self, redis: Redis, session: AsyncSession):
        self.redis = redis
        self.session = session

    async def is_banned(self, actor: Actor) -> tuple[bool, str | None]:
        values = [
            (BanScope.IP, actor.ip),
            (BanScope.FINGERPRINT, actor.fingerprint),
        ]
        if actor.telegram_id:
            values.append((BanScope.TELEGRAM_ID, str(actor.telegram_id)))
        try:
            values.append((BanScope.SUBNET, subnet24(actor.ip)))
        except ValueError:
            pass
        now = datetime.now(timezone.utc)
        for scope, value in values:
            cached = await self.redis.get(f"ban:{scope}:{value}")
            if cached:
                return True, cached
        rows = (await self.session.execute(select(Ban).where(Ban.active.is_(True), Ban.scope.in_([v[0] for v in values]), Ban.value.in_([v[1] for v in values])))).scalars().all()
        for ban in rows:
            if ban.expires_at is None or ban.expires_at > now:
                await self.redis.setex(f"ban:{ban.scope}:{ban.value}", 300, ban.reason)
                return True, ban.reason
        return False, None

    async def record(self, actor: Actor, event_type: str, severity: AbuseSeverity, score_delta: int, evidence: dict) -> None:
        self.session.add(AbuseEvent(telegram_id=actor.telegram_id, user_id=actor.user_id, ip=actor.ip, fingerprint=actor.fingerprint, event_type=event_type, severity=severity, score_delta=score_delta, evidence=evidence))
        ABUSE_EVENTS.labels(type=event_type, severity=severity.value).inc()
        if actor.user_id:
            await self.session.execute(update(User).where(User.id == actor.user_id).values(abuse_score=User.abuse_score + score_delta))
        key = f"abuse:score:{actor.fingerprint}:{actor.ip}"
        score = await self.redis.incrby(key, score_delta)
        await self.redis.expire(key, 24 * 3600)
        if score >= 80 or severity == AbuseSeverity.CRITICAL:
            await self.ban(actor, BanScope.FINGERPRINT, actor.fingerprint, "critical abuse automation", AbuseSeverity.CRITICAL, timedelta(hours=12))
        elif score >= 60:
            await self.redis.setex(f"cooldown:{actor.fingerprint}", 1800, "1")

    async def ban(self, actor: Actor, scope: BanScope, value: str, reason: str, severity: AbuseSeverity, duration: timedelta | None) -> None:
        expires = datetime.now(timezone.utc) + duration if duration else None
        self.session.add(Ban(scope=scope, value=value, reason=reason, severity=severity, expires_at=expires, active=True))
        ttl = int(duration.total_seconds()) if duration else 86400
        await self.redis.setex(f"ban:{scope}:{value}", ttl, reason)
        if actor.user_id and scope == BanScope.TELEGRAM_ID:
            await self.session.execute(update(User).where(User.id == actor.user_id).values(is_banned=True))

    async def inspect_generation(self, actor: Actor, style: str, count: int) -> bool:
        pipe = self.redis.pipeline()
        pipe.incr(f"gen:fp:{actor.fingerprint}:1m")
        pipe.expire(f"gen:fp:{actor.fingerprint}:1m", 60)
        pipe.pfadd(f"gen:devices:user:{actor.user_id}:24h", actor.fingerprint)
        pipe.expire(f"gen:devices:user:{actor.user_id}:24h", 86400)
        pipe.pfcount(f"gen:devices:user:{actor.user_id}:24h")
        res = await pipe.execute()
        minute_count = int(res[0])
        devices = int(res[-1])
        if minute_count > (120 if actor.tier != UserTier.FREE else 8):
            await self.record(actor, "scripted_generation_farming", AbuseSeverity.HIGH, 25, {"minute_count": minute_count, "style": style})
            return False
        if devices > 6 and actor.tier != UserTier.FREE:
            await self.record(actor, "vip_account_sharing_multi_device", AbuseSeverity.HIGH, 20, {"devices_24h": devices})
            await self.session.execute(update(User).where(User.id == actor.user_id).values(quota_frozen=True, require_captcha=True))
            return False
        if count > 100 and actor.tier == UserTier.FREE:
            await self.record(actor, "free_request_farming", AbuseSeverity.MEDIUM, 15, {"count": count})
            return False
        return True

    async def inspect_enumeration(self, actor: Actor, usernames: list[str]) -> bool:
        lengths = {len(u) for u in usernames}
        prefix_density = len({u[:3] for u in usernames if len(u) >= 3})
        if len(usernames) >= 10 and len(lengths) <= 2 and prefix_density <= 3:
            await self.record(actor, "username_enumeration_pattern", AbuseSeverity.HIGH, 30, {"sample": usernames[:10]})
            return False
        return True
