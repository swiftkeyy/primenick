from __future__ import annotations

from dataclasses import dataclass
from time import time

from redis.asyncio import Redis

from app.monitoring.metrics import RATE_LIMITED

TOKEN_BUCKET_LUA = """
local key = KEYS[1]
local rate = tonumber(ARGV[1])
local burst = tonumber(ARGV[2])
local now = tonumber(ARGV[3])
local cost = tonumber(ARGV[4])
local ttl = tonumber(ARGV[5])
local data = redis.call('HMGET', key, 'tokens', 'ts')
local tokens = tonumber(data[1])
local ts = tonumber(data[2])
if tokens == nil then tokens = burst end
if ts == nil then ts = now end
local delta = math.max(0, now - ts)
tokens = math.min(burst, tokens + delta * rate)
local allowed = tokens >= cost
local retry_after = 0
if allowed then
  tokens = tokens - cost
else
  retry_after = math.ceil(((cost - tokens) / rate) * 1000)
end
redis.call('HSET', key, 'tokens', tokens, 'ts', now)
redis.call('PEXPIRE', key, ttl)
return { allowed and 1 or 0, math.floor(tokens), retry_after }
"""

SLIDING_WINDOW_LUA = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
local member = ARGV[4]
redis.call('ZREMRANGEBYSCORE', key, 0, now - window)
local count = redis.call('ZCARD', key)
if count >= limit then
  local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')[2]
  local retry = math.ceil((window - (now - tonumber(oldest))) * 1000)
  return {0, limit - count, retry}
end
redis.call('ZADD', key, now, member)
redis.call('PEXPIRE', key, math.ceil(window * 1000) + 1000)
return {1, limit - count - 1, 0}
"""

@dataclass(frozen=True)
class LimitRule:
    scope: str
    rate_per_sec: float
    burst: int
    window_seconds: int
    window_limit: int
    cost: int = 1

@dataclass(frozen=True)
class LimitDecision:
    allowed: bool
    scope: str
    remaining: int
    retry_after_ms: int


class AdaptiveRateLimiter:
    def __init__(self, redis: Redis):
        self.redis = redis
        self._tb_sha: str | None = None
        self._sw_sha: str | None = None

    async def load(self) -> None:
        if self._tb_sha is None:
            self._tb_sha = await self.redis.script_load(TOKEN_BUCKET_LUA)
        if self._sw_sha is None:
            self._sw_sha = await self.redis.script_load(SLIDING_WINDOW_LUA)

    async def check(self, identity: str, rule: LimitRule, abuse_score: int = 0, vip: bool = False) -> LimitDecision:
        await self.load()
        penalty = 1.0 + min(abuse_score, 100) / 100
        vip_boost = 1.75 if vip and abuse_score < 30 else 1.0
        rate = max(0.05, rule.rate_per_sec * vip_boost / penalty)
        burst = max(1, int(rule.burst * vip_boost / penalty))
        now = time()
        tb_key = f"rl:tb:{rule.scope}:{identity}"
        sw_key = f"rl:sw:{rule.scope}:{identity}"
        tb = await self.redis.evalsha(self._tb_sha, 1, tb_key, rate, burst, now, rule.cost, max(rule.window_seconds * 2000, 60000))
        if int(tb[0]) != 1:
            RATE_LIMITED.labels(scope=rule.scope).inc()
            return LimitDecision(False, rule.scope, int(tb[1]), int(tb[2]))
        sw = await self.redis.evalsha(self._sw_sha, 1, sw_key, now, rule.window_seconds, max(1, int(rule.window_limit * vip_boost / penalty)), f"{now}:{identity}")
        if int(sw[0]) != 1:
            RATE_LIMITED.labels(scope=rule.scope).inc()
            return LimitDecision(False, rule.scope, int(sw[1]), int(sw[2]))
        return LimitDecision(True, rule.scope, min(int(tb[1]), int(sw[1])), 0)


DEFAULT_RULES = {
    "global": LimitRule("global", rate_per_sec=800, burst=2000, window_seconds=1, window_limit=1200),
    "telegram_id": LimitRule("telegram_id", rate_per_sec=0.7, burst=6, window_seconds=60, window_limit=30),
    "ip": LimitRule("ip", rate_per_sec=3.0, burst=40, window_seconds=60, window_limit=180),
    "endpoint_generate": LimitRule("endpoint_generate", rate_per_sec=0.15, burst=2, window_seconds=12*60*60, window_limit=2),
    "endpoint_vip_generate": LimitRule("endpoint_vip_generate", rate_per_sec=2.0, burst=20, window_seconds=60, window_limit=240),
    "payments": LimitRule("payments", rate_per_sec=0.2, burst=5, window_seconds=300, window_limit=20),
}
