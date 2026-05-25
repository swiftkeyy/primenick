from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def reserve_keyboard(username: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=f"Прикрепить @{username}", callback_data=f"reserve:{username}")]])


def vip_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="VIP 500 credits", callback_data="buyvip:vip_500")],
        [InlineKeyboardButton(text="VIP 1000 credits", callback_data="buyvip:vip_1000")],
        [InlineKeyboardButton(text="VIP 3000 credits", callback_data="buyvip:vip_3000")],
        [InlineKeyboardButton(text="VIP Unlimited", callback_data="buyvip:vip_unlimited")],
    ])
