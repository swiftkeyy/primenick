from __future__ import annotations

from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Update
from sqlalchemy import select

from app.core.logging import request_id_ctx, user_id_ctx
from app.db.redis import get_redis
from app.db.session import SessionLocal
from app.models.enums import AbuseSeverity, UserTier
from app.models.user import User
from app.security.abuse import AbuseService, Actor
from app.security.fingerprint import request_fingerprint
from app.security.rate_limiter import AdaptiveRateLimiter, DEFAULT_RULES
from app.security.proxy import client_ip


class BotSecurityMiddleware(BaseMiddleware):
    async def __call__(self, handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]], event: TelegramObject, data: dict[str, Any]) -> Any:
        update: Update | None = data.get("event_update")
        aiohttp_request = data.get("aiohttp_request")
        tg_user = None
        if update:
            if update.message:
                tg_user = update.message.from_user
            elif update.callback_query:
                tg_user = update.callback_query.from_user
        telegram_id = tg_user.id if tg_user else None
        if telegram_id:
            user_id_ctx.set(telegram_id)
        ip = client_ip(aiohttp_request) if aiohttp_request else "0.0.0.0"
        fp = request_fingerprint(aiohttp_request, telegram_id) if aiohttp_request else "nofp"
        redis = get_redis()
        async with SessionLocal() as session:
            user = None
            if telegram_id:
                user = (await session.execute(select(User).where(User.telegram_id == telegram_id))).scalar_one_or_none()
                if user is None and tg_user:
                    user = User(telegram_id=telegram_id, username=tg_user.username, first_name=tg_user.first_name, last_ip=ip, last_fingerprint=fp)
                    session.add(user)
                    await session.commit()
                    await session.refresh(user)
            actor = Actor(telegram_id=telegram_id, user_id=user.id if user else None, ip=ip, fingerprint=fp, tier=user.tier if user else UserTier.FREE, abuse_score=user.abuse_score if user else 0)
            abuse = AbuseService(redis, session)
            banned, reason = await abuse.is_banned(actor)
            if banned:
                await session.commit()
                return None
            limiter = AdaptiveRateLimiter(redis)
            checks = [
                ("global", "all"),
                ("ip", ip),
            ]
            if telegram_id:
                checks.append(("telegram_id", str(telegram_id)))
            for scope, identity in checks:
                decision = await limiter.check(identity, DEFAULT_RULES[scope], abuse_score=actor.abuse_score, vip=actor.tier != UserTier.FREE)
                if not decision.allowed:
                    await abuse.record(actor, f"rate_limited_{scope}", severity=AbuseSeverity.LOW, score_delta=2, evidence={"retry_after_ms": decision.retry_after_ms})
                    await session.commit()
                    return None
            data["security_actor"] = actor
            data["db_session"] = session
            data["redis"] = redis
            result = await handler(event, data)
            await session.commit()
            return result
