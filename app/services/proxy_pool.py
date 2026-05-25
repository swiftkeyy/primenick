from __future__ import annotations

from dataclasses import dataclass
import secrets

from redis.asyncio import Redis


@dataclass(frozen=True)
class EgressProxy:
    id: str
    url: str | None


class ProxyPool:
    def __init__(self, redis: Redis):
        self.redis = redis

    async def choose(self, platform: str) -> EgressProxy:
        items = await self.redis.smembers(f"proxy:{platform}:healthy")
        if not items:
            return EgressProxy("direct", None)
        item = secrets.choice(list(items))
        return EgressProxy(item.split("|", 1)[0], item.split("|", 1)[1])

    async def report(self, proxy: EgressProxy, ok: bool, platform: str) -> None:
        if proxy.id == "direct":
            return
        key = f"proxy:{platform}:score:{proxy.id}"
        if ok:
            await self.redis.decrby(key, 1)
        else:
            score = await self.redis.incrby(key, 3)
            await self.redis.expire(key, 3600)
            if score > 20:
                await self.redis.srem(f"proxy:{platform}:healthy", f"{proxy.id}|{proxy.url}")
