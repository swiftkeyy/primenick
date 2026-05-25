from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, Index, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import CIDR, INET, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDMixin
from app.models.enums import AbuseSeverity, BanScope


class AbuseEvent(UUIDMixin, Base):
    __tablename__ = "abuse_events"

    telegram_id: Mapped[int | None] = mapped_column(nullable=True)
    user_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ip: Mapped[str | None] = mapped_column(INET, nullable=True)
    fingerprint: Mapped[str | None] = mapped_column(String(128), nullable=True)
    event_type: Mapped[str] = mapped_column(String(96), nullable=False)
    severity: Mapped[AbuseSeverity] = mapped_column(Enum(AbuseSeverity, name="abuse_severity", values_callable=lambda x: [e.value for e in x]), nullable=False)
    score_delta: Mapped[int] = mapped_column(Integer, nullable=False)
    evidence: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

    __table_args__ = (
        Index("ix_abuse_events_tg_created", "telegram_id", "created_at"),
        Index("ix_abuse_events_ip_created", "ip", "created_at"),
        Index("ix_abuse_events_fp_created", "fingerprint", "created_at"),
        Index("ix_abuse_events_type_created", "event_type", "created_at"),
    )


class Ban(UUIDMixin, Base):
    __tablename__ = "bans"

    scope: Mapped[BanScope] = mapped_column(Enum(BanScope, name="ban_scope", values_callable=lambda x: [e.value for e in x]), nullable=False)
    value: Mapped[str] = mapped_column(String(128), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[AbuseSeverity] = mapped_column(Enum(AbuseSeverity, name="ban_severity", values_callable=lambda x: [e.value for e in x]), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

    __table_args__ = (UniqueConstraint("scope", "value", "active", name="uq_active_ban_scope_value"), Index("ix_bans_scope_value_active", "scope", "value", "active"),)


class SuspiciousActivity(UUIDMixin, Base):
    __tablename__ = "suspicious_activity"

    telegram_id: Mapped[int | None] = mapped_column(nullable=True)
    ip: Mapped[str | None] = mapped_column(INET, nullable=True)
    subnet: Mapped[str | None] = mapped_column(CIDR, nullable=True)
    fingerprint: Mapped[str | None] = mapped_column(String(128), nullable=True)
    activity_type: Mapped[str] = mapped_column(String(96), nullable=False)
    counter: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    evidence: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb"))

    __table_args__ = (Index("ix_suspicious_lookup", "telegram_id", "ip", "fingerprint", "activity_type"),)
