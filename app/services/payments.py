from __future__ import annotations

import hashlib
import secrets
import urllib.parse
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Mapping

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.settings import get_settings
from app.models.enums import PaymentStatus, ReservationStatus, UsernameStatus, UserTier
from app.models.payment import Payment, PaymentAuditLog, PaymentWebhookEvent
from app.models.quota import VipGenerationCredit
from app.models.user import User
from app.models.username import UsernameAsset, UsernameReservation
from app.services.quota import PLAN_CREDITS


class RobokassaSignatureError(Exception):
    pass


class PaymentService:
    """Robokassa payment integration.

    Security model:
    - invoice creation uses Password #1 signature;
    - ResultURL callback uses Password #2 signature;
    - SuccessURL is verified but never fulfills orders;
    - fulfillment is idempotent and bound to internal payment_id via Shp_payment_id;
    - PaymentWebhookEvent(provider,event_id) prevents replay processing.
    """

    provider = "robokassa"

    def __init__(self, session: AsyncSession):
        self.session = session
        self.settings = get_settings()

    async def create_invoice(self, user_id: str, amount: Decimal, description: str, metadata: dict) -> Payment:
        amount = amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        idem = secrets.token_urlsafe(32)
        inv_id = await self._allocate_inv_id()
        expires = datetime.now(timezone.utc) + timedelta(minutes=20)
        payment = Payment(
            user_id=user_id,
            provider=self.provider,
            provider_payment_id=str(inv_id),
            idempotency_key=idem,
            status=PaymentStatus.PENDING,
            amount_rub=amount,
            description=description,
            metadata_json={**metadata, "inv_id": inv_id},
            expires_at=expires,
        )
        self.session.add(payment)
        await self.session.flush()
        shp = {"Shp_payment_id": payment.id}
        out_sum = self._amount(amount)
        signature = self._signature_init(out_sum=out_sum, inv_id=inv_id, shp=shp)
        params = {
            "MerchantLogin": self.settings.robokassa_merchant_login,
            "OutSum": out_sum,
            "InvId": str(inv_id),
            "Description": description[:100],
            "SignatureValue": signature,
            "Culture": "ru",
            "Encoding": "utf-8",
            "IsTest": "1" if self.settings.robokassa_is_test else "0",
            **shp,
        }
        payment.confirmation_url = f"{self.settings.robokassa_payment_url}?{urllib.parse.urlencode(params)}"
        self.session.add(PaymentAuditLog(payment_id=payment.id, action="invoice_created", actor="system", details={"provider": self.provider, "inv_id": inv_id}))
        return payment

    async def ingest_result_callback(self, params: Mapping[str, str], ip: str | None = None) -> tuple[bool, str]:
        out_sum = self._required(params, "OutSum")
        inv_id = self._required(params, "InvId")
        signature = self._required(params, "SignatureValue")
        shp = self._extract_shp(params)
        self._verify_result_signature(out_sum, inv_id, signature, shp)
        payment_id = shp.get("Shp_payment_id")
        event_id = f"result:{inv_id}:{signature.upper()}"
        payload_hash = hashlib.sha256(urllib.parse.urlencode(sorted(params.items())).encode()).hexdigest()
        existing = (await self.session.execute(select(PaymentWebhookEvent).where(PaymentWebhookEvent.provider == self.provider, PaymentWebhookEvent.event_id == event_id))).scalar_one_or_none()
        if existing:
            return False, f"OK{inv_id}"
        event = PaymentWebhookEvent(provider=self.provider, event_id=event_id, event_type="result", payload_hash=payload_hash, payload=dict(params))
        self.session.add(event)
        payment = await self._load_payment_for_callback(inv_id, payment_id)
        if payment is None:
            event.processed_at = datetime.now(timezone.utc)
            return True, f"OK{inv_id}"
        if Decimal(out_sum).quantize(Decimal("0.01")) != Decimal(payment.amount_rub).quantize(Decimal("0.01")):
            payment.status = PaymentStatus.CANCELLED
            self.session.add(PaymentAuditLog(payment_id=payment.id, action="amount_mismatch", actor="robokassa", ip=ip, details={"out_sum": out_sum, "expected": str(payment.amount_rub)}))
            event.processed_at = datetime.now(timezone.utc)
            raise RobokassaSignatureError("amount_mismatch")
        if payment.expires_at < datetime.now(timezone.utc):
            payment.status = PaymentStatus.EXPIRED
            self.session.add(PaymentAuditLog(payment_id=payment.id, action="expired_callback", actor="robokassa", ip=ip, details={"inv_id": inv_id}))
            event.processed_at = datetime.now(timezone.utc)
            return True, f"OK{inv_id}"
        if payment.status != PaymentStatus.SUCCEEDED:
            payment.status = PaymentStatus.SUCCEEDED
            await self._fulfill(payment)
        self.session.add(PaymentAuditLog(payment_id=payment.id, action="result_callback_accepted", actor="robokassa", ip=ip, details={"inv_id": inv_id}))
        event.processed_at = datetime.now(timezone.utc)
        return True, f"OK{inv_id}"

    async def verify_success_callback(self, params: Mapping[str, str]) -> Payment | None:
        out_sum = self._required(params, "OutSum")
        inv_id = self._required(params, "InvId")
        signature = self._required(params, "SignatureValue")
        shp = self._extract_shp(params)
        self._verify_success_signature(out_sum, inv_id, signature, shp)
        return await self._load_payment_for_callback(inv_id, shp.get("Shp_payment_id"), lock=False)

    async def mark_failed_return(self, params: Mapping[str, str], ip: str | None = None) -> None:
        inv_id = params.get("InvId")
        payment_id = params.get("Shp_payment_id")
        payment = await self._load_payment_for_callback(inv_id, payment_id, lock=True) if inv_id else None
        if payment and payment.status == PaymentStatus.PENDING:
            payment.status = PaymentStatus.CANCELLED
            self.session.add(PaymentAuditLog(payment_id=payment.id, action="fail_return", actor="robokassa", ip=ip, details=dict(params)))

    async def _load_payment_for_callback(self, inv_id: str | None, payment_id: str | None, lock: bool = True) -> Payment | None:
        query = select(Payment).where(Payment.provider == self.provider)
        if payment_id:
            query = query.where(Payment.id == payment_id)
        elif inv_id:
            query = query.where(Payment.provider_payment_id == str(inv_id))
        else:
            return None
        if lock:
            query = query.with_for_update()
        return (await self.session.execute(query)).scalar_one_or_none()

    async def _allocate_inv_id(self) -> int:
        for _ in range(20):
            inv_id = secrets.randbelow(2_000_000_000 - 10_000_000) + 10_000_000
            exists = (await self.session.execute(select(Payment.id).where(Payment.provider == self.provider, Payment.provider_payment_id == str(inv_id)))).scalar_one_or_none()
            if not exists:
                return inv_id
        raise RuntimeError("robokassa_inv_id_exhausted")

    def _signature_init(self, out_sum: str, inv_id: int, shp: dict[str, str]) -> str:
        parts = [self.settings.robokassa_merchant_login, out_sum, str(inv_id), self.settings.robokassa_password1]
        parts.extend(self._shp_parts(shp))
        return self._digest(":".join(parts))

    def _verify_result_signature(self, out_sum: str, inv_id: str, provided: str, shp: dict[str, str]) -> None:
        parts = [out_sum, inv_id, self.settings.robokassa_password2]
        parts.extend(self._shp_parts(shp))
        expected = self._digest(":".join(parts))
        if not secrets.compare_digest(expected.upper(), provided.upper()):
            raise RobokassaSignatureError("bad_result_signature")

    def _verify_success_signature(self, out_sum: str, inv_id: str, provided: str, shp: dict[str, str]) -> None:
        parts = [out_sum, inv_id, self.settings.robokassa_password1]
        parts.extend(self._shp_parts(shp))
        expected = self._digest(":".join(parts))
        if not secrets.compare_digest(expected.upper(), provided.upper()):
            raise RobokassaSignatureError("bad_success_signature")

    def _digest(self, value: str) -> str:
        algo = self.settings.robokassa_hash_algorithm.lower()
        if algo == "md5":
            return hashlib.md5(value.encode("utf-8")).hexdigest().upper()  # noqa: S324 - Robokassa legacy option
        if algo == "sha256":
            return hashlib.sha256(value.encode("utf-8")).hexdigest().upper()
        if algo == "sha512":
            return hashlib.sha512(value.encode("utf-8")).hexdigest().upper()
        raise RuntimeError("unsupported_robokassa_hash_algorithm")

    def _extract_shp(self, params: Mapping[str, str]) -> dict[str, str]:
        return {k: str(v) for k, v in params.items() if k.startswith("Shp_")}

    def _shp_parts(self, shp: dict[str, str]) -> list[str]:
        return [f"{k}={shp[k]}" for k in sorted(shp)]

    def _required(self, params: Mapping[str, str], key: str) -> str:
        value = params.get(key)
        if value is None or value == "":
            raise RobokassaSignatureError(f"missing_{key}")
        return str(value)

    def _amount(self, amount: Decimal) -> str:
        return str(amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

    async def _fulfill(self, payment: Payment) -> None:
        kind = payment.metadata_json.get("kind")
        if kind == "reservation_purchase":
            rid = payment.metadata_json["reservation_id"]
            reservation = (await self.session.execute(select(UsernameReservation).where(UsernameReservation.id == rid).with_for_update())).scalar_one()
            reservation.status = ReservationStatus.PURCHASED
            asset = await self.session.get(UsernameAsset, reservation.asset_id, with_for_update=True)
            if asset:
                asset.status = UsernameStatus.SOLD
        elif kind == "vip_subscription":
            plan = UserTier(payment.metadata_json["plan"])
            await self.session.execute(update(User).where(User.id == payment.user_id).values(tier=plan, vip_until=datetime.now(timezone.utc) + timedelta(days=30)))
            row = (await self.session.execute(select(VipGenerationCredit).where(VipGenerationCredit.user_id == payment.user_id).with_for_update())).scalar_one_or_none()
            if row:
                row.plan_type = plan
                row.credits_total = PLAN_CREDITS[plan]
                row.credits_used = 0
                row.reset_at = datetime.now(timezone.utc) + timedelta(days=30)
                row.frozen_at = None
            else:
                self.session.add(VipGenerationCredit(user_id=payment.user_id, plan_type=plan, credits_total=PLAN_CREDITS[plan], credits_used=0, reset_at=datetime.now(timezone.utc) + timedelta(days=30)))
