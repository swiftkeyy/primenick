from __future__ import annotations

from celery import Celery
from celery.schedules import crontab

from app.core.settings import get_settings

settings = get_settings()
celery_app = Celery("rarehandle", broker=str(settings.celery_broker_url), backend=str(settings.celery_result_backend), include=["app.workers.tasks"])
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    broker_connection_retry_on_startup=True,
    task_routes={
        "availability.check": {"queue": "availability"},
        "availability.check_priority": {"queue": "priority"},
        "quota.refill_monthly": {"queue": "analytics"},
        "reservations.expire": {"queue": "default"},
        "payments.reconcile": {"queue": "payments"},
    },
    task_default_retry_delay=5,
    task_time_limit=45,
    task_soft_time_limit=30,
    broker_transport_options={"visibility_timeout": 3600, "queue_order_strategy": "priority"},
    task_default_queue="default",
    task_create_missing_queues=True,
    beat_schedule={
        "quota-refill-every-hour": {"task": "quota.refill_monthly", "schedule": crontab(minute=7)},
        "reservation-expire-every-minute": {"task": "reservations.expire", "schedule": crontab()},
        "payments-reconcile": {"task": "payments.reconcile", "schedule": crontab(minute="*/5")},
    },
)
