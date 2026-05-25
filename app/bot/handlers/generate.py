from __future__ import annotations

from decimal import Decimal

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards import reserve_keyboard
from app.core.settings import get_settings
from app.db.redis import get_redis
from app.models.enums import AbuseSeverity, UserTier, UsernameStatus
from app.models.user import User
from app.models.username import UsernameAsset
from app.security.abuse import AbuseService, Actor
from app.security.rate_limiter import AdaptiveRateLimiter, DEFAULT_RULES
from app.services.generation import UsernameGenerator
from app.services.pricing import PricingContext, PricingEngine
from app.services.quota import QuotaService
from app.services.reservation import ReservationError, ReservationService
from app.workers.tasks import enqueue_availability_check

router = Router(name="generate")


def parse_args(text: str) -> tuple[str, int]:
    parts = text.split()
    style = parts[1].lower() if len(parts) > 1 else "startup"
    count = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 10
    return style, max(1, min(count, 40))


@router.message(Command("generate"))
async def generate(message: Message, db_session: AsyncSession, security_actor: Actor):
    settings = get_settings()
    user = (await db_session.execute(select(User).where(User.telegram_id == message.from_user.id))).scalar_one()
    style, count = parse_args(message.text or "")
    limiter = AdaptiveRateLimiter(get_redis())
    rule = DEFAULT_RULES["endpoint_vip_generate"] if user.tier != UserTier.FREE else DEFAULT_RULES["endpoint_generate"]
    decision = await limiter.check(str(user.telegram_id), rule, user.abuse_score, user.tier != UserTier.FREE)
    abuse = AbuseService(get_redis(), db_session)
    if not decision.allowed:
        await abuse.record(security_actor, "generation_rate_limited", AbuseSeverity.MEDIUM, 8, {"style": style, "retry_ms": decision.retry_after_ms})
        await message.answer(f"Cooldown active. retry_after_ms={decision.retry_after_ms}")
        return
    if not await abuse.inspect_generation(security_actor, style, count):
        await message.answer("Запрос заблокирован risk-engine: quota frozen/cooldown/captcha may be required.")
        return
    quota = QuotaService(db_session)
    credits_spent = 1 if user.tier != UserTier.FREE else 0
    q = await quota.consume_generation(user, style, credits_spent, security_actor.ip, security_actor.fingerprint)
    if not q.allowed:
        await message.answer(f"Quota denied: {q.reason}. Remaining={q.remaining}")
        return
    min_len = settings.free_min_username_len if user.tier == UserTier.FREE else 4
    names = await UsernameGenerator(get_redis()).generate(style, count, user.tier, min_len)
    pricing = PricingEngine()
    lines = [f"Generated {len(names)} / style={style} / remaining_credits={q.remaining}"]
    for n in names[:10]:
        price = pricing.quote(PricingContext(username=n.username, rarity_score=n.rarity_score))
        stmt = insert(UsernameAsset).values(username=n.username, normalized=n.username.lower(), source="generated", style=style, rarity_score=n.rarity_score, status=UsernameStatus.GENERATED, price_rub=price, availability_platform="telegram").on_conflict_do_update(index_elements=["normalized", "availability_platform"], set_={"rarity_score": n.rarity_score, "style": style, "price_rub": price}).returning(UsernameAsset.id)
        await db_session.execute(stmt)
        queue = "priority" if user.tier != UserTier.FREE else "availability"
        enqueue_availability_check.apply_async(args=[n.username, "telegram", user.id], queue=queue, priority=8 if user.tier != UserTier.FREE else 3)
        lines.append(f"@{n.username} · rarity={n.rarity_score} · {price} RUB")
    await message.answer("\n".join(lines), reply_markup=reserve_keyboard(names[0].username) if names else None)


@router.callback_query(F.data.startswith("reserve:"))
async def reserve(cb: CallbackQuery, db_session: AsyncSession):
    username = cb.data.split(":", 1)[1].lower()
    user = (await db_session.execute(select(User).where(User.telegram_id == cb.from_user.id))).scalar_one()
    asset = (await db_session.execute(select(UsernameAsset).where(UsernameAsset.normalized == username, UsernameAsset.availability_platform == "telegram"))).scalar_one_or_none()
    if not asset:
        await cb.answer("Asset not found", show_alert=True); return
    try:
        price = Decimal(str(asset.price_rub or "49.00"))
        r = await ReservationService(db_session).reserve(user, asset, price)
        await cb.message.answer(f"Reserved @{username} until {r.expires_at.isoformat()}. Use /buy to purchase.")
        await cb.answer("Reserved")
    except ReservationError as e:
        await cb.answer(str(e), show_alert=True)
