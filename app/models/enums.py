from __future__ import annotations

from enum import StrEnum


class UserTier(StrEnum):
    FREE = "free"
    VIP_500 = "vip_500"
    VIP_1000 = "vip_1000"
    VIP_3000 = "vip_3000"
    VIP_UNLIMITED = "vip_unlimited"


class UsernameStatus(StrEnum):
    GENERATED = "generated"
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    RESERVED = "reserved"
    SOLD = "sold"
    EXPIRED = "expired"
    LOCKED = "locked"


class ReservationStatus(StrEnum):
    ACTIVE = "active"
    EXPIRED = "expired"
    PURCHASED = "purchased"
    CANCELLED = "cancelled"


class PaymentStatus(StrEnum):
    PENDING = "pending"
    WAITING_FOR_CAPTURE = "waiting_for_capture"
    SUCCEEDED = "succeeded"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"
    EXPIRED = "expired"


class BanScope(StrEnum):
    TELEGRAM_ID = "telegram_id"
    IP = "ip"
    FINGERPRINT = "fingerprint"
    SUBNET = "subnet"


class AbuseSeverity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"
