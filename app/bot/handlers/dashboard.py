from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards import vip_keyboard
from app.models.enums import ReservationStatus, UserTier
from app.models.user import User
from app.models.username import UsernameReservation
from app.services.payments import PaymentService
from app.services.quota import QuotaService

router = Router(name="dashboard")
VIP_PRICES = {"vip_500": "499.00", "vip_1000": "899.00", "vip_3000": "1990.00", "vip_unlimited": "4990.00"}

@router.message(Command("vip"))
async def vip(message: Message, db_session: AsyncSession):
    user = (await db_session.execute(select(User).where(User.telegram_id == message.from_user.id))).scalar_one()
    remaining, reset_at, plan = await QuotaService(db_session).status(user.id)
    reserved = (await db_session.execute(select(func.count(UsernameReservation.id)).where(UsernameReservation.user_id == user.id, UsernameReservation.status == ReservationStatus.ACTIVE))).scalar_one()
    perks = "priority queue, fast-lane, AI premium, rare pools, short usernames, longer TTL, auto-renew"
    await message.answer(f"VIP status: {plan.value}\nremaining credits: {remaining if plan != UserTier.VIP_UNLIMITED else 'unlimited'}\nnext reset: {reset_at}\nqueue priority: {'priority' if user.tier != UserTier.FREE else 'default'}\nreserved usernames: {reserved}\nactive perks: {perks}", reply_markup=vip_keyboard())

@router.message(Command("pricing"))
async def pricing(message: Message):
    await message.answer("Pricing: 5 chars → 149 RUB, 6 chars → 89 RUB, 7 chars → 49 RUB. Dynamic coefficients: rarity, surge, inventory pressure, platform. VIP discount removed by design; VIP monetization is quota/priority economy.")

@router.message(Command("buy"))
async def buy(message: Message):
    await message.answer("Choose VIP plan or purchase an active reservation.", reply_markup=vip_keyboard())

@router.callback_query(F.data.startswith("buyvip:"))
async def buy_vip(cb: CallbackQuery, db_session: AsyncSession):
    from decimal import Decimal
    plan = cb.data.split(":", 1)[1]
    if plan not in VIP_PRICES:
        await cb.answer("unknown plan", show_alert=True); return
    user = (await db_session.execute(select(User).where(User.telegram_id == cb.from_user.id))).scalar_one()
    payment = await PaymentService(db_session).create_invoice(user.id, Decimal(VIP_PRICES[plan]), f"PRIME NICK {plan} subscription", {"kind": "vip_subscription", "plan": plan})
    await cb.message.answer(f"Invoice: {payment.confirmation_url}\nexpires_at={payment.expires_at.isoformat()}")
    await cb.answer("invoice created")

@router.message(Command("myusernames"))
async def myusernames(message: Message, db_session: AsyncSession):
    user = (await db_session.execute(select(User).where(User.telegram_id == message.from_user.id))).scalar_one()
    rows = (await db_session.execute(select(UsernameReservation).where(UsernameReservation.user_id == user.id, UsernameReservation.status == ReservationStatus.ACTIVE).order_by(UsernameReservation.expires_at.asc()).limit(100))).scalars().all()
    if not rows:
        await message.answer("No active reservations."); return
    await message.answer("\n".join([f"@{r.normalized} · expires {r.expires_at.isoformat()} · {r.price_snapshot_rub} RUB" for r in rows]))

@router.message(Command("stats"))
async def stats(message: Message, db_session: AsyncSession):
    user = (await db_session.execute(select(User).where(User.telegram_id == message.from_user.id))).scalar_one()
    reserved = (await db_session.execute(select(func.count(UsernameReservation.id)).where(UsernameReservation.user_id == user.id))).scalar_one()
    await message.answer(f"tier={user.tier.value}\nabuse_score={user.abuse_score}\nquota_frozen={user.quota_frozen}\nreservations_total={reserved}")
