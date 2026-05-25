from __future__ import annotations

import os

from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

try:
    import uvloop
    uvloop.install()
except Exception:
    pass

from app.api.middlewares import request_context_middleware, security_headers_middleware
from app.api.webhooks import robokassa_fail, robokassa_result, robokassa_success
from app.bot.handlers import routers
from app.bot.middlewares.security import BotSecurityMiddleware
from app.core.logging import configure_logging, get_logger
from app.core.settings import get_settings
from app.db.redis import close_redis
from app.db.session import dispose_engines
from app.monitoring.metrics import metrics_handler
from app.security.signatures import verify_telegram_secret

log = get_logger(__name__)


async def healthz(_: web.Request) -> web.Response:
    return web.json_response({"ok": True})


def create_app() -> web.Application:
    settings = get_settings()
    configure_logging(settings.log_level)
    bot = Bot(settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()
    dp.update.middleware(BotSecurityMiddleware())
    for r in routers:
        dp.include_router(r)

    app = web.Application(middlewares=[request_context_middleware, security_headers_middleware], client_max_size=256 * 1024)
    app["bot"] = bot
    app["dp"] = dp
    app.router.add_get("/healthz", healthz)
    app.router.add_get("/metrics", metrics_handler)
    app.router.add_route("*", settings.robokassa_result_path, robokassa_result)
    app.router.add_route("*", settings.robokassa_success_path, robokassa_success)
    app.router.add_route("*", settings.robokassa_fail_path, robokassa_fail)

    class HardenedTelegramHandler(SimpleRequestHandler):
        async def handle(self, request: web.Request) -> web.Response:
            if not verify_telegram_secret(request):
                raise web.HTTPForbidden(reason="bad telegram secret")
            return await super().handle(request)

    HardenedTelegramHandler(dispatcher=dp, bot=bot, secret_token=settings.bot_webhook_secret).register(app, path=settings.telegram_webhook_path)
    setup_application(app, dp, bot=bot)

    async def on_startup(app: web.Application):
        await bot.set_webhook(settings.telegram_webhook_url, secret_token=settings.bot_webhook_secret, allowed_updates=dp.resolve_used_update_types(), drop_pending_updates=False, max_connections=100)
        log.info("bot_started", webhook=settings.telegram_webhook_url)

    async def on_shutdown(app: web.Application):
        await bot.session.close()
        await close_redis()
        await dispose_engines()
        log.info("bot_shutdown")

    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)
    return app


def main() -> None:
    app = create_app()
    port = int(os.getenv("PORT", "8080"))
    web.run_app(app, host="0.0.0.0", port=port, shutdown_timeout=30)


if __name__ == "__main__":
    main()
