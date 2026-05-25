from __future__ import annotations

import secrets
import string
from dataclasses import dataclass

from redis.asyncio import Redis

from app.models.enums import UserTier
from app.services.rarity import rarity_score

ALPHA = string.ascii_lowercase
DIGITS = string.digits

STYLE_POOLS = {
    "aesthetic": ["luna", "aura", "vibe", "muse", "halo", "sol", "noir", "ivory", "velvet"],
    "rare": ["xq", "vx", "qora", "nyx", "zora", "rune", "kairo", "orion"],
    "crypto": ["chain", "mint", "yield", "vault", "token", "ledger", "satoshi"],
    "ai": ["ai", "neuro", "prompt", "vector", "agent", "model", "latent"],
    "dark": ["void", "shade", "oblivion", "hex", "night", "crypt", "zero"],
    "minimal": ["zen", "mono", "pure", "clear", "lite", "base", "form"],
    "startup": ["prime", "forge", "labs", "stack", "flux", "nova", "scale"],
    "gaming": ["rage", "clutch", "pixel", "boss", "frag", "quest", "rank"],
    "anime": ["kira", "yuki", "akira", "hikari", "sora", "kitsune", "senpai"],
    "short": ["io", "ai", "vx", "rx", "gg", "hq", "xq"],
}

@dataclass(frozen=True)
class GeneratedName:
    username: str
    style: str
    rarity_score: int


class UsernameGenerator:
    def __init__(self, redis: Redis):
        self.redis = redis

    async def generate(self, style: str, count: int, tier: UserTier, min_len: int) -> list[GeneratedName]:
        if style not in STYLE_POOLS:
            style = "startup"
        count = max(1, min(count, 40 if tier == UserTier.FREE else 200))
        allow_short = tier != UserTier.FREE
        names: list[GeneratedName] = []
        attempts = 0
        while len(names) < count and attempts < count * 25:
            attempts += 1
            candidate = self._candidate(style, allow_short)
            if len(candidate) < min_len:
                candidate += secrets.choice(ALPHA) + secrets.choice(DIGITS)
            if not self._valid(candidate):
                continue
            seen = await self.redis.set(f"gen:dedupe:{candidate}", "1", nx=True, ex=86400)
            if not seen:
                continue
            names.append(GeneratedName(candidate, style, rarity_score(candidate)))
        if len(names) < count:
            names.extend(await self._fallback(style, count - len(names), min_len))
        return names

    def _candidate(self, style: str, allow_short: bool) -> str:
        pool = STYLE_POOLS[style]
        r = secrets.randbelow(100)
        if style == "short" and allow_short:
            length = secrets.choice([4, 5, 6])
            return "".join(secrets.choice(ALPHA + DIGITS) for _ in range(length))
        if r < 45:
            return secrets.choice(pool) + secrets.choice(STYLE_POOLS["startup"])
        if r < 75:
            return secrets.choice(pool) + str(secrets.randbelow(99)).zfill(2)
        return secrets.choice(pool) + secrets.choice(ALPHA) + secrets.choice(DIGITS)

    async def _fallback(self, style: str, count: int, min_len: int) -> list[GeneratedName]:
        out = []
        for _ in range(count):
            token = secrets.token_urlsafe(8).lower().replace("-", "").replace("_", "")[:max(min_len, 8)]
            out.append(GeneratedName(token, style, rarity_score(token)))
        return out

    def _valid(self, u: str) -> bool:
        return 4 <= len(u) <= 32 and u[0].isalpha() and all(c.isalnum() or c == "_" for c in u) and not u.endswith("_") and "__" not in u
