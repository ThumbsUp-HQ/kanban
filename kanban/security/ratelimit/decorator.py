"""FastAPI route dependency decorator and rate limiter factory (S2.4, S3.3)."""

from __future__ import annotations

import inspect
import logging
import os
from typing import TYPE_CHECKING

from starlette.requests import Request  # noqa: TC002

from kanban.api.problems import ProblemException
from kanban.security.ratelimit.base import (
    RateLimitDecision,
    RateLimiter,
    RateLimitPolicy,
    make_key,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Sequence

    from sqlalchemy.ext.asyncio import AsyncEngine

    from kanban.security.ratelimit.valkey import ValkeyCommands

logger = logging.getLogger(__name__)


def build_rate_limiter(
    settings: object = None,
    *,
    engine: AsyncEngine | None = None,
    valkey_client: ValkeyCommands | None = None,
) -> RateLimiter:
    """Construct RateLimiter implementation according to deployment mode and settings.

    Returns PgRateLimiter when KANBAN_DEPLOYMENT_MODE=standalone or no KANBAN_VALKEY_URL,
    otherwise returns ValkeyRateLimiter.
    """
    deployment_mode: str | None = None
    valkey_url: str | None = None

    if settings is not None:
        if isinstance(settings, str):
            deployment_mode = settings
        else:
            deployment_mode = getattr(settings, "deployment_mode", None)
            valkey_url = getattr(settings, "valkey_url", None)

    if deployment_mode is None:
        deployment_mode = os.environ.get("KANBAN_DEPLOYMENT_MODE") or os.environ.get(
            "KB_DEPLOYMENT_MODE", "standalone"
        )

    if valkey_url is None:
        valkey_url = os.environ.get("KANBAN_VALKEY_URL") or os.environ.get("KB_VALKEY_URL")

    is_standalone = deployment_mode == "standalone" or (not valkey_url and valkey_client is None)

    if is_standalone:
        from kanban.security.ratelimit.pg import PgRateLimiter  # noqa: PLC0415

        return PgRateLimiter(engine=engine)

    from kanban.security.ratelimit.valkey import ValkeyRateLimiter  # noqa: PLC0415

    if valkey_client is not None:
        return ValkeyRateLimiter(valkey_client)

    class _DeferredValkeyClient:
        async def eval(self, _script: str, _numkeys: int, *_args: object) -> list[int]:
            msg = (
                "Concrete Valkey client connection is deferred to the production "
                "connection wiring ticket"
            )
            raise RuntimeError(msg)

    return ValkeyRateLimiter(_DeferredValkeyClient())


def rate_limited(
    policy: RateLimitPolicy,
    key_func: Callable[[Request], Sequence[str] | Awaitable[Sequence[str]]],
    *,
    limiter: RateLimiter | None = None,
    session_hmac_key: bytes | None = None,
) -> Callable[[Request], Awaitable[RateLimitDecision]]:
    """Create a FastAPI route dependency enforcing sliding-window rate limits.

    On denial, raises RFC 7807 ProblemException(code='RATE_LIMITED', status=429)
    with the Retry-After header.
    On backend exception, if fail_mode='open', allows request and logs WARNING
    with policy name only; if fail_mode='closed', raises
    ProblemException(code='RATE_LIMIT_UNAVAILABLE', status=503).
    """

    async def dependency(request: Request) -> RateLimitDecision:
        active_limiter = limiter or getattr(request.app.state, "rate_limiter", None)
        if active_limiter is None:
            sf = getattr(request.app.state, "session_factory", None)
            engine = (getattr(sf, "engine", None) or getattr(sf, "_engine", None)) if sf else None
            active_limiter = build_rate_limiter(
                getattr(request.app.state, "settings", None),
                engine=engine,
            )

        raw_parts = key_func(request)
        if inspect.isawaitable(raw_parts):
            parts_seq = await raw_parts
        else:
            parts_seq = raw_parts

        parts = [str(item) for item in parts_seq]

        hmac_k = session_hmac_key
        if hmac_k is None:
            km = getattr(request.app.state, "key_material", None)
            if km is not None:
                hmac_k = km.session_hmac_key

        try:
            key = make_key(policy, *parts, session_hmac_key=hmac_k)
        except ValueError:
            key = make_key(policy, *parts, session_hmac_key=b"\x00" * 32)

        try:
            decision = await active_limiter.hit(policy, key)
        except Exception as exc:
            if policy.fail_mode == "open":
                logger.warning(
                    "Rate limit backend failure for policy %s; failing open", policy.name
                )
                return RateLimitDecision(allowed=True, remaining=1, retry_after_seconds=0)

            logger.warning(
                "Rate limit backend failure for policy %s; failing closed: %s", policy.name, exc
            )
            raise ProblemException(
                code="RATE_LIMIT_UNAVAILABLE",
                status=503,
                title="Rate Limiter Unavailable",
                detail="Rate limiting backend is temporarily unavailable",
            ) from exc

        if not decision.allowed:
            raise ProblemException(
                code="RATE_LIMITED",
                status=429,
                title="Rate Limit Exceeded",
                detail=f"Rate limit exceeded for policy '{policy.name}'",
                headers={"Retry-After": str(decision.retry_after_seconds)},
            )

        return decision

    return dependency
