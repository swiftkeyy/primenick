from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDMixin


class RateLimitDecision(UUIDMixin, Base):
    __tablename__ = "rate_limit_decisions"

    scope: Mapped[str] = mapped_column(String(64), nullable=False)
    key_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    allowed: Mapped[int] = mapped_column(Integer, nullable=False)
    limit_value: Mapped[int] = mapped_column(Integer, nullable=False)
    remaining: Mapped[int] = mapped_column(Integer, nullable=False)
    retry_after_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

    __table_args__ = (Index("ix_rate_limit_scope_created", "scope", "created_at"), Index("ix_rate_limit_key_created", "key_hash", "created_at"),)
