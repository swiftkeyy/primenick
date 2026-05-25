from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, Enum, ForeignKey, Index, Integer, Numeric, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin
from app.models.enums import ReservationStatus, UsernameStatus


class UsernameAsset(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "username_assets"

    username: Mapped[str] = mapped_column(String(32), nullable=False)
    normalized: Mapped[str] = mapped_column(String(32), nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="generated")
    style: Mapped[str] = mapped_column(String(32), nullable=False)
    rarity_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[UsernameStatus] = mapped_column(Enum(UsernameStatus, name="username_status", values_callable=lambda x: [e.value for e in x]), nullable=False, default=UsernameStatus.GENERATED)
    price_rub: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    availability_platform: Mapped[str] = mapped_column(String(24), nullable=False, default="telegram")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")

    reservations = relationship("UsernameReservation", back_populates="asset")

    __table_args__ = (
        UniqueConstraint("normalized", "availability_platform", name="uq_asset_normalized_platform"),
        Index("ix_username_assets_status_rarity", "status", "rarity_score"),
        CheckConstraint("length(normalized) between 4 and 32", name="username_length_valid"),
    )


class UsernameReservation(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "username_reservations"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    asset_id: Mapped[str] = mapped_column(ForeignKey("username_assets.id", ondelete="CASCADE"), nullable=False)
    normalized: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[ReservationStatus] = mapped_column(Enum(ReservationStatus, name="reservation_status", values_callable=lambda x: [e.value for e in x]), nullable=False, default=ReservationStatus.ACTIVE)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    auto_renew: Mapped[bool] = mapped_column(nullable=False, default=False, server_default=text("false"))
    lock_token: Mapped[str] = mapped_column(String(128), nullable=False)
    price_snapshot_rub: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)

    user = relationship("User", back_populates="reservations")
    asset = relationship("UsernameAsset", back_populates="reservations")

    __table_args__ = (
        UniqueConstraint("normalized", "status", name="uq_active_reservation_normalized_status"),
        Index("ix_reservations_user_status", "user_id", "status"),
        Index("ix_reservations_expiry", "status", "expires_at"),
    )


class AvailabilityCheck(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "availability_checks"

    normalized: Mapped[str] = mapped_column(String(32), nullable=False)
    platform: Mapped[str] = mapped_column(String(24), nullable=False)
    requested_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    available: Mapped[bool | None] = mapped_column(nullable=True)
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    proxy_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_class: Mapped[str | None] = mapped_column(String(128), nullable=True)

    __table_args__ = (Index("ix_availability_norm_platform_created", "normalized", "platform", "created_at"),)
