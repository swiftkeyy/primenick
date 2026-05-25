from __future__ import annotations

from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
from aiohttp import web

REQUESTS = Counter("rarehandle_requests_total", "Inbound HTTP/webhook requests", ["route", "status"])
REQUEST_LATENCY = Histogram("rarehandle_request_latency_seconds", "Request latency", ["route"], buckets=(.005,.01,.025,.05,.1,.25,.5,1,2,5,10))
RATE_LIMITED = Counter("rarehandle_rate_limited_total", "Rate limited decisions", ["scope"])
ABUSE_EVENTS = Counter("rarehandle_abuse_events_total", "Abuse events", ["type", "severity"])
GENERATION = Counter("rarehandle_generation_total", "Username generations", ["style", "tier"])
AVAILABILITY = Counter("rarehandle_availability_checks_total", "Availability checks", ["platform", "result"])
PAYMENTS = Counter("rarehandle_payments_total", "Payments", ["provider", "status"])
QUEUE_DEPTH = Gauge("rarehandle_queue_depth", "Redis/Celery queue depth", ["queue"])


async def metrics_handler(_: web.Request) -> web.Response:
    return web.Response(body=generate_latest(), content_type=CONTENT_TYPE_LATEST)
