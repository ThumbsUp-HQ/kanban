"""Valkey-backed sliding-window rate limiter using atomic Lua script (S2.4, S3.3)."""

from __future__ import annotations

import datetime as dt
from typing import TYPE_CHECKING, Any, Protocol

from kanban.security.ratelimit.base import RateLimitDecision

if TYPE_CHECKING:
    from collections.abc import Sequence

    from kanban.security.ratelimit.base import RateLimitPolicy

_KEY_LENGTH = 32

SLIDING_WINDOW_LUA = """
local prefix = KEYS[1]
local limit = tonumber(ARGV[1])
local window = tonumber(ARGV[2])

local now_sec, now_usec
if #ARGV >= 3 and ARGV[3] ~= nil and ARGV[3] ~= "" then
    local ts = tonumber(ARGV[3])
    now_sec = math.floor(ts)
    now_usec = math.floor((ts - now_sec) * 1000000)
else
    local redis_time = redis.call('TIME')
    now_sec = tonumber(redis_time[1])
    now_usec = tonumber(redis_time[2])
end

local window_idx = math.floor(now_sec / window)
local curr_key = prefix .. ":" .. window_idx
local prev_key = prefix .. ":" .. (window_idx - 1)

local curr_count = tonumber(redis.call('GET', curr_key) or "0")
local prev_count = tonumber(redis.call('GET', prev_key) or "0")

local elapsed = (now_sec % window) + (now_usec / 1000000.0)
local weight = (window - elapsed) / window
if weight < 0.0 then
    weight = 0.0
end
if weight > 1.0 then
    weight = 1.0
end

local estimated_hits = math.floor((prev_count * weight) + curr_count)

if estimated_hits >= limit then
    local retry_after = math.ceil(window - elapsed)
    if retry_after < 1 then
        retry_after = 1
    end
    return {0, 0, retry_after}
end

local new_curr = redis.call('INCR', curr_key)
if new_curr == 1 then
    redis.call('EXPIRE', curr_key, window * 2)
end

local new_estimated = math.floor((prev_count * weight) + new_curr)
local remaining = limit - new_estimated
if remaining < 0 then
    remaining = 0
end

return {1, remaining, 0}
"""

_RESET_LUA = """
local prefix = KEYS[1]
local window = tonumber(ARGV[1])

local now_sec
if #ARGV >= 2 and ARGV[2] ~= nil and ARGV[2] ~= "" then
    local ts = tonumber(ARGV[2])
    now_sec = math.floor(ts)
else
    local redis_time = redis.call('TIME')
    now_sec = tonumber(redis_time[1])
end

local window_idx = math.floor(now_sec / window)
local curr_key = prefix .. ":" .. window_idx
local prev_key = prefix .. ":" .. (window_idx - 1)
local next_key = prefix .. ":" .. (window_idx + 1)

redis.call('DEL', curr_key, prev_key, next_key)
return {1, 0, 0}
"""


class ValkeyCommands(Protocol):
    """Protocol for Valkey/Redis client supporting Lua eval."""

    async def eval(self, script: str, numkeys: int, *args: object) -> list[int]:
        """Execute Lua script returning integer status and metrics."""
        ...


class ValkeyRateLimiter:
    """Valkey-backed sliding-window rate limiter using atomic Lua script."""

    def __init__(self, client: ValkeyCommands) -> None:
        """Initialize Valkey rate limiter with client instance."""
        self._client = client

    async def hit(
        self,
        policy: RateLimitPolicy,
        key: bytes,
        now: float | dt.datetime | None = None,
    ) -> RateLimitDecision:
        """Record hit against Valkey sliding-window bucket and return decision."""
        if len(key) != _KEY_LENGTH:
            msg = f"Rate limit key must be exactly {_KEY_LENGTH} bytes (got {len(key)})"
            raise ValueError(msg)

        prefix = f"kb:rl:{policy.name}:{key.hex()}"
        args: list[Any] = [str(policy.limit), str(policy.window_seconds)]

        if now is not None:
            now_sec = now.timestamp() if isinstance(now, dt.datetime) else float(now)
            args.append(f"{now_sec:.6f}")

        res: Sequence[int] = await self._client.eval(SLIDING_WINDOW_LUA, 1, prefix, *args)
        return RateLimitDecision(
            allowed=bool(res[0]),
            remaining=int(res[1]),
            retry_after_seconds=int(res[2]),
        )

    async def reset(
        self,
        policy: RateLimitPolicy,
        key: bytes,
        now: float | dt.datetime | None = None,
    ) -> None:
        """Clear rate limit keys for the specified policy and key."""
        if len(key) != _KEY_LENGTH:
            msg = f"Rate limit key must be exactly {_KEY_LENGTH} bytes (got {len(key)})"
            raise ValueError(msg)

        prefix = f"kb:rl:{policy.name}:{key.hex()}"
        args: list[Any] = [str(policy.window_seconds)]
        if now is not None:
            now_sec = now.timestamp() if isinstance(now, dt.datetime) else float(now)
            args.append(f"{now_sec:.6f}")

        await self._client.eval(_RESET_LUA, 1, prefix, *args)
