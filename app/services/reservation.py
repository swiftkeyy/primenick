from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.settings import get_settings
from app.models.enums import ReservationStatus, UserTier, UsernameStatus
from app.models.user import User
from app.models.username import UsernameAsset, UsernameReservation


class ReservationError(Exception):
    pass


class ReservationService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.settings = get_settings()

    async def reserve(self, user: User, asset: UsernameAsset, price: Decimal) -> UsernameReservation:
        limit = self.settings.vip_reservation_limit if user.tier != UserTier.FREE else self.settings.free_reservation_limit
        active_count = (await self.session.execute(select(func.count(UsernameReservation.id)).where(UsernameReservation.user_id == user.id, UsernameReservation.status == ReservationStatus.ACTIVE, UsernameReservation.expires_at > datetime.now(timezone.utc)))).scalar_one()
        if active_count >= limit:
            raise ReservationError("reservation_limit_reached")
        locked_asset = (await self.session.execute(select(UsernameAsset).where(UsernameAsset.id == asset.id).with_for_update(nowait=True))).scalar_one()
        if locked_asset.status not in (UsernameStatus.AVAILABLE, UsernameStatus.GENERATED):
            raise ReservationError("username_not_available")
        exists = (await self.session.execute(select(UsernameReservation).where(UsernameReservation.normalized == locked_asset.normalized, UsernameReservation.status == ReservationStatus.ACTIVE, UsernameReservation.expires_at > datetime.now(timezone.utc)).with_for_update(skip_locked=True))).scalar_one_or_none()
        if exists:
            raise ReservationError("already_reserved")
        ttl = timedelta(hours=48 if user.tier != UserTier.FREE else 12)
        locked_asset.status = UsernameStatus.RESERVED
        locked_asset.price_rub = price
        locked_asset.version += 1
        reservation = UsernameReservation(user_id=user.id, asset_id=locked_asset.id, normalized=locked_asset.normalized, status=ReservationStatus.ACTIVE, expires_at=datetime.now(timezone.utc) + ttl, auto_renew=user.tier != UserTier.FREE, lock_token=secrets.token_urlsafe(32), price_snapshot_rub=price)
        self.session.add(reservation)
        await self.session.flush()
        return reservation

    async def expire_due(self, limit: int = 1000) -> int:
        rows = (await self.session.execute(select(UsernameReservation).where(UsernameReservation.status == ReservationStatus.ACTIVE, UsernameReservation.expires_at <= datetime.now(timezone.utc)).limit(limit).with_for_update(skip_locked=True))).scalars().all()
        for r in rows:
            r.status = ReservationStatus.EXPIRED
            asset = await self.session.get(UsernameAsset, r.asset_id, with_for_update=True)
            if asset and asset.status == UsernameStatus.RESERVED:
                asset.status = UsernameStatus.EXPIRED
        return len(rows)
