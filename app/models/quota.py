from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Integer, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDMixin
from app.models.enums import UserTier


class VipGenerationCredit(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "vip_generation_credits"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)
    credits_total: Mapped[int] = mapped_column(Integer, nullable=False)
    credits_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    reset_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    plan_type: Mapped[UserTier] = mapped_column(Enum(UserTier, name="vip_plan_type", values_callable=lambda x: [e.value for e in x]), nullable=False)
    frozen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (Index("ix_vip_credits_reset", "reset_at"),)


class GenerationUsageLog(UUIDMixin, Base):
    __tablename__ = "generation_usage_logs"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    generation_type: Mapped[str] = mapped_column(String(64), nullable=False)
    credits_spent: Mapped[int] = mapped_column(Integer, nullable=False)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    fingerprint: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

    __table_args__ = (Index("ix_generation_usage_user_created", "user_id", "created_at"), Index("ix_generation_usage_fp_created", "fingerprint", "created_at"))
