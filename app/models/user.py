from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Enum, Index, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin
from app.models.enums import UserTier


class User(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "users"

    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    first_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    tier: Mapped[UserTier] = mapped_column(Enum(UserTier, name="user_tier", values_callable=lambda x: [e.value for e in x]), nullable=False, default=UserTier.FREE, server_default=UserTier.FREE.value)
    vip_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_banned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))
    quota_frozen: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))
    require_captcha: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))
    abuse_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    last_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_fingerprint: Mapped[str | None] = mapped_column(String(128), nullable=True)

    reservations = relationship("UsernameReservation", back_populates="user")
    payments = relationship("Payment", back_populates="user")
