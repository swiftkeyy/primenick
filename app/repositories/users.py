from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


async def get_user_by_telegram(session: AsyncSession, telegram_id: int) -> User | None:
    return (await session.execute(select(User).where(User.telegram_id == telegram_id))).scalar_one_or_none()
