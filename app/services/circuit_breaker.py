from __future__ import annotations

import time
from dataclasses import dataclass

from redis.asyncio import Redis


@dataclass(frozen=True)
class CircuitState:
    open: bool
    failures: int
    reset_at: float


class CircuitBreaker:
    def __init__(self, redis: Redis, name: str, threshold: int = 8, cooldown: int = 60):
        self.redis = redis
        self.name = name
        self.threshold = threshold
        self.cooldown = cooldown

    async def allow(self) -> bool:
        reset_at = float(await self.redis.get(f"cb:{self.name}:reset") or 0)
        return reset_at <= time.time()

    async def success(self) -> None:
        await self.redis.delete(f"cb:{self.name}:fail", f"cb:{self.name}:reset")

    async def failure(self) -> None:
        fail = await self.redis.incr(f"cb:{self.name}:fail")
        await self.redis.expire(f"cb:{self.name}:fail", self.cooldown * 5)
        if fail >= self.threshold:
            await self.redis.setex(f"cb:{self.name}:reset", self.cooldown, str(time.time() + self.cooldown))
