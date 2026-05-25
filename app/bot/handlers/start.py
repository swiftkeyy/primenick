from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

router = Router(name="start")

START_TEXT = """PRIME NICK — premium AI username engine.

Команды:
/generate startup 10 — генерация
/myusernames — reserved usernames
/vip — кредиты, perks, priority queue
/pricing — правила pricing engine
/buy — покупка VIP
/stats — usage stats
/help — security/usage policy"""

@router.message(Command("start"))
async def start(message: Message):
    await message.answer(START_TEXT)

@router.message(Command("help"))
async def help_cmd(message: Message):
    await message.answer("Security-first SaaS: adaptive limits, abuse score, race-safe reservation locks. VIP = premium quota/priority, not discount.")
