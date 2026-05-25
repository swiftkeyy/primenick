from app.bot.handlers.dashboard import router as dashboard_router
from app.bot.handlers.generate import router as generate_router
from app.bot.handlers.start import router as start_router

routers = [start_router, generate_router, dashboard_router]
