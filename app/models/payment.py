from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin
from app.models.enums import PaymentStatus


class Payment(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "payments"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False, default="robokassa")
    provider_payment_id: Mapped[str | None] = mapped_column(String(128), nullable=True, unique=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    status: Mapped[PaymentStatus] = mapped_column(Enum(PaymentStatus, name="payment_status", values_callable=lambda x: [e.value for e in x]), nullable=False, default=PaymentStatus.PENDING)
    amount_rub: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb"))
    confirmation_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    user = relationship("User", back_populates="payments")

    __table_args__ = (Index("ix_payments_user_status", "user_id", "status"),)


class PaymentWebhookEvent(UUIDMixin, Base):
    __tablename__ = "payment_webhook_events"

    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    event_id: Mapped[str] = mapped_column(String(128), nullable=False)
    event_type: Mapped[str] = mapped_column(String(128), nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    payload_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)

    __table_args__ = (UniqueConstraint("provider", "event_id", name="uq_provider_event_id"), Index("ix_payment_webhook_received", "received_at"),)


class PaymentAuditLog(UUIDMixin, Base):
    __tablename__ = "payment_audit_logs"

    payment_id: Mapped[str | None] = mapped_column(ForeignKey("payments.id", ondelete="SET NULL"), nullable=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    actor: Mapped[str] = mapped_column(String(64), nullable=False)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    details: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

    __table_args__ = (Index("ix_payment_audit_payment_created", "payment_id", "created_at"),)
