from __future__ import annotations

from aiohttp import web

from app.db.session import SessionLocal
from app.security.proxy import client_ip
from app.services.payments import PaymentService, RobokassaSignatureError


async def _params(request: web.Request) -> dict[str, str]:
    data: dict[str, str] = {k: v for k, v in request.query.items()}
    if request.method == "POST":
        post = await request.post()
        data.update({k: str(v) for k, v in post.items()})
    return data


async def robokassa_result(request: web.Request) -> web.Response:
    params = await _params(request)
    async with SessionLocal() as session:
        try:
            _, response_text = await PaymentService(session).ingest_result_callback(params, ip=client_ip(request))
            await session.commit()
            return web.Response(text=response_text, content_type="text/plain")
        except RobokassaSignatureError as exc:
            await session.rollback()
            raise web.HTTPForbidden(reason=str(exc))


async def robokassa_success(request: web.Request) -> web.Response:
    params = await _params(request)
    async with SessionLocal() as session:
        try:
            payment = await PaymentService(session).verify_success_callback(params)
            await session.commit()
        except RobokassaSignatureError as exc:
            await session.rollback()
            raise web.HTTPForbidden(reason=str(exc))
    if payment:
        return web.Response(text="PRIME NICK: payment accepted. Return to Telegram bot.", content_type="text/plain")
    return web.Response(text="PRIME NICK: payment is being processed.", content_type="text/plain")


async def robokassa_fail(request: web.Request) -> web.Response:
    params = await _params(request)
    async with SessionLocal() as session:
        await PaymentService(session).mark_failed_return(params, ip=client_ip(request))
        await session.commit()
    return web.Response(text="PRIME NICK: payment cancelled or failed. Return to Telegram bot.", content_type="text/plain")
