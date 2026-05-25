from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from dateutil.relativedelta import relativedelta

from sqlalchemy import insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import UserTier
from app.models.quota import GenerationUsageLog, VipGenerationCredit
from app.models.user import User

PLAN_CREDITS = {UserTier.VIP_500: 500, UserTier.VIP_1000: 1000, UserTier.VIP_3000: 3000, UserTier.VIP_UNLIMITED: 2_147_000_000}

@dataclass(frozen=True)
class QuotaDecision:
    allowed: bool
    remaining: int
    reason: str


class QuotaService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def status(self, user_id: str) -> tuple[int, datetime | None, UserTier]:
        row = (await self.session.execute(select(VipGenerationCredit).where(VipGenerationCredit.user_id == user_id))).scalar_one_or_none()
        if row is None:
            return 0, None, UserTier.FREE
        return max(0, row.credits_total - row.credits_used), row.reset_at, row.plan_type

    async def consume_generation(self, user: User, generation_type: str, credits: int, ip: str | None, fingerprint: str | None) -> QuotaDecision:
        if user.quota_frozen:
            return QuotaDecision(False, 0, "quota_frozen")
        if user.tier == UserTier.FREE:
            self.session.add(GenerationUsageLog(user_id=user.id, generation_type=generation_type, credits_spent=0, ip=ip, fingerprint=fingerprint))
            return QuotaDecision(True, 0, "free_window_checked_by_rate_limiter")
        row = (await self.session.execute(select(VipGenerationCredit).where(VipGenerationCredit.user_id == user.id).with_for_update())).scalar_one_or_none()
        if row is None:
            row = await self.ensure_vip_quota(user)
        if row.frozen_at:
            return QuotaDecision(False, max(0, row.credits_total - row.credits_used), "quota_frozen")
        if row.reset_at <= datetime.now(timezone.utc):
            row.credits_total = PLAN_CREDITS.get(row.plan_type, 0)
            row.credits_used = 0
            row.reset_at = datetime.now(timezone.utc) + relativedelta(months=1)
        remaining = row.credits_total - row.credits_used
        if remaining < credits:
            return QuotaDecision(False, remaining, "credits_exhausted")
        row.credits_used += credits
        self.session.add(GenerationUsageLog(user_id=user.id, generation_type=generation_type, credits_spent=credits, ip=ip, fingerprint=fingerprint))
        return QuotaDecision(True, remaining - credits, "ok")

    async def ensure_vip_quota(self, user: User) -> VipGenerationCredit:
        total = PLAN_CREDITS[user.tier]
        row = VipGenerationCredit(user_id=user.id, credits_total=total, credits_used=0, reset_at=datetime.now(timezone.utc) + relativedelta(months=1), plan_type=user.tier)
        self.session.add(row)
        await self.session.flush()
        return row

    async def refill_due(self, limit: int = 1000) -> int:
        now = datetime.now(timezone.utc)
        rows = (await self.session.execute(select(VipGenerationCredit).where(VipGenerationCredit.reset_at <= now).limit(limit).with_for_update(skip_locked=True))).scalars().all()
        for row in rows:
            row.credits_total = PLAN_CREDITS.get(row.plan_type, 0)
            row.credits_used = 0
            row.reset_at = now + relativedelta(months=1)
            row.frozen_at = None
        return len(rows)
