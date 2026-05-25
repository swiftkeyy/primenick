from __future__ import annotations

import time
import uuid

from aiohttp import web

from app.core.logging import request_id_ctx
from app.monitoring.metrics import REQUESTS, REQUEST_LATENCY


@web.middleware
async def request_context_middleware(request: web.Request, handler):
    rid = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    request_id_ctx.set(rid)
    route = request.match_info.route.resource.canonical if request.match_info.route and request.match_info.route.resource else request.path
    start = time.perf_counter()
    try:
        resp = await handler(request)
        return resp
    finally:
        elapsed = time.perf_counter() - start
        status = getattr(locals().get("resp", None), "status", 500)
        REQUESTS.labels(route=route, status=str(status)).inc()
        REQUEST_LATENCY.labels(route=route).observe(elapsed)


@web.middleware
async def security_headers_middleware(request: web.Request, handler):
    resp = await handler(request)
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Referrer-Policy"] = "no-referrer"
    resp.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"
    resp.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains; preload"
    return resp
