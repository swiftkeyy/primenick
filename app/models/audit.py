from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Index, String, text
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDMixin


class AuditLog(UUIDMixin, Base):
    __tablename__ = "audit_logs"

    actor_user_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    telegram_id: Mapped[int | None] = mapped_column(nullable=True)
    ip: Mapped[str | None] = mapped_column(INET, nullable=True)
    fingerprint: Mapped[str | None] = mapped_column(String(128), nullable=True)
    action: Mapped[str] = mapped_column(String(96), nullable=False)
    entity_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    entity_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

    __table_args__ = (Index("ix_audit_actor_created", "actor_user_id", "created_at"), Index("ix_audit_action_created", "action", "created_at"),)
