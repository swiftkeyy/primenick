from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from celery import Task
from sqlalchemy import select

from app.core.celery_app import celery_app
from app.core.logging import configure_logging, get_logger
from app.db.session import WorkerSessionLocal
from app.models.enums import UsernameStatus
from app.models.username import UsernameAsset
from app.services.availability import AvailabilityChecker
from app.services.quota import QuotaService
from app.services.reservation import ReservationService

configure_logging()
log = get_logger(__name__)


class BaseTask(Task):
    autoretry_for = (ConnectionError, TimeoutError, RuntimeError)
    retry_backoff = True
    retry_backoff_max = 300
    retry_jitter = True
    max_retries = 5


def run(coro):
    return asyncio.run(coro)


@celery_app.task(bind=True, base=BaseTask, name="availability.check")
def enqueue_availability_check(self, username: str, platform: str, user_id: str | None = None):
    return run(_availability(username, platform, user_id))


@celery_app.task(bind=True, base=BaseTask, name="availability.check_priority")
def enqueue_priority_availability_check(self, username: str, platform: str, user_id: str | None = None):
    return run(_availability(username, platform, user_id))


async def _availability(username: str, platform: str, user_id: str | None):
    async with WorkerSessionLocal() as session:
        result = await AvailabilityChecker(session).check(username, platform, user_id)
        asset = (await session.execute(select(UsernameAsset).where(UsernameAsset.normalized == username.lower(), UsernameAsset.availability_platform == platform).with_for_update())).scalar_one_or_none()
        if asset and result.available is not None:
            asset.status = UsernameStatus.AVAILABLE if result.available else UsernameStatus.UNAVAILABLE
            asset.checked_at = datetime.now(timezone.utc)
        await session.commit()
        return result.__dict__


@celery_app.task(name="quota.refill_monthly", base=BaseTask)
def refill_monthly_quotas():
    async def _run():
        async with WorkerSessionLocal() as session:
            count = await QuotaService(session).refill_due()
            await session.commit()
            log.info("quota_refill_done", count=count)
            return count
    return run(_run())


@celery_app.task(name="reservations.expire", base=BaseTask)
def expire_reservations():
    async def _run():
        async with WorkerSessionLocal() as session:
            count = await ReservationService(session).expire_due()
            await session.commit()
            return count
    return run(_run())


@celery_app.task(name="payments.reconcile", base=BaseTask)
def reconcile_payments():
    async def _run():
        async with WorkerSessionLocal() as session:
            # Local expiration safeguard; Robokassa authoritative webhooks finalize captures.
            from app.models.payment import Payment
            from app.models.enums import PaymentStatus
            rows = (await session.execute(select(Payment).where(Payment.status == PaymentStatus.PENDING, Payment.expires_at < datetime.now(timezone.utc)).limit(500).with_for_update(skip_locked=True))).scalars().all()
            for p in rows:
                p.status = PaymentStatus.EXPIRED
            await session.commit()
            return len(rows)
    return run(_run())
