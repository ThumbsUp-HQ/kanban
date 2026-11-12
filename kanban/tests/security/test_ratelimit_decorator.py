"""Unit tests for rate limit decorator, fail modes, and factory (S2.4, KB-P2-18)."""

from __future__ import annotations

import base64
from typing import TYPE_CHECKING

import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient

from kanban.api.problems import (
    ProblemException,
    problem_exception_handler,
    unhandled_exception_handler,
)
from kanban.security.client_ip import resolve_client_ip
from kanban.security.keys import KeyMaterial
from kanban.security.ratelimit import (
    ATTACHMENT_UPLOAD_PRINCIPAL,
    AUTH_LOGIN_ACCOUNT,
    AUTH_LOGIN_IP,
    AUTH_MFA_VERIFY,
    MEDIA_PROXY_PRINCIPAL,
    SETUP_CLAIM_IP,
    PgRateLimiter,
    RateLimitDecision,
    RateLimiter,
    RateLimitPolicy,
    ValkeyRateLimiter,
    build_rate_limiter,
    rate_limited,
)
from kanban.security.ratelimit.base import make_key
from kanban.tests.security.fakes import FakeValkey

if TYPE_CHECKING:
    from starlette.requests import Request


class FailingLimiter:
    """Mock rate limiter simulating backend connection failures."""

    async def hit(self, policy: RateLimitPolicy, key: bytes) -> RateLimitDecision:
        """Simulate backend connection error during hit."""
        del policy, key
        msg = "connection lost to rate limit backend"
        raise ConnectionError(msg)

    async def reset(self, policy: RateLimitPolicy, key: bytes) -> None:
        """Simulate backend connection error during reset."""
        del policy, key
        msg = "connection lost to rate limit backend"
        raise ConnectionError(msg)


def _build_test_app(
    policy: RateLimitPolicy,
    limiter: RateLimiter | FailingLimiter,
    session_hmac_key: bytes = b"k" * 32,
) -> FastAPI:
    """Build a minimal FastAPI application wiring the rate_limited dependency."""
    app = FastAPI()
    app.add_exception_handler(ProblemException, problem_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, unhandled_exception_handler)

    dep = rate_limited(
        policy=policy,
        key_func=lambda req: [resolve_client_ip(req.scope)],
        limiter=limiter,
        session_hmac_key=session_hmac_key,
    )

    @app.get("/api/v1/resource", dependencies=[Depends(dep)])
    async def sample_endpoint() -> dict[str, str]:
        return {"status": "ok"}

    return app


@pytest.mark.asyncio
async def test_case_08_fail_mode_closed_and_open() -> None:
    """Test Case 8: ConnectionError yields 503 for closed, 200 for open."""
    failing_lim = FailingLimiter()

    # 1. Closed fail mode must fail-closed with 503 RATE_LIMIT_UNAVAILABLE
    closed_policy = RateLimitPolicy(
        name="closed_fail_mode", limit=10, window_seconds=60, fail_mode="closed"
    )
    closed_app = _build_test_app(closed_policy, failing_lim)

    async with AsyncClient(
        transport=ASGITransport(app=closed_app), base_url="http://testserver"
    ) as client:
        resp = await client.get("/api/v1/resource")
        assert resp.status_code == 503
        data = resp.json()
        assert data["code"] == "RATE_LIMIT_UNAVAILABLE"
        assert data["status"] == 503
        assert resp.headers["content-type"].startswith("application/problem+json")

    # 2. Open fail mode must fail-open with 200 OK
    open_policy = RateLimitPolicy(
        name="open_fail_mode", limit=10, window_seconds=60, fail_mode="open"
    )
    open_app = _build_test_app(open_policy, failing_lim)

    async with AsyncClient(
        transport=ASGITransport(app=open_app), base_url="http://testserver"
    ) as client:
        resp = await client.get("/api/v1/resource")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_case_09_decorator_deny_contract() -> None:
    """Test Case 9: Deny response is problem+json, code=RATE_LIMITED, Retry-After integer."""
    fake_valkey = FakeValkey()
    limiter = ValkeyRateLimiter(fake_valkey)

    policy = RateLimitPolicy(name="strict_burst", limit=2, window_seconds=60)
    app = _build_test_app(policy, limiter)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        # Hit 1 & 2: allowed
        r1 = await client.get("/api/v1/resource")
        assert r1.status_code == 200
        r2 = await client.get("/api/v1/resource")
        assert r2.status_code == 200

        # Hit 3: rate limit exceeded
        r3 = await client.get("/api/v1/resource")
        assert r3.status_code == 429
        assert r3.headers["content-type"].startswith("application/problem+json")
        assert "retry-after" in r3.headers
        retry_val = r3.headers["retry-after"]
        assert retry_val.isdigit()
        assert int(retry_val) >= 1

        body = r3.json()
        assert body["code"] == "RATE_LIMITED"
        assert body["status"] == 429
        assert "title" in body
        assert "request_id" in body


def test_case_11_policy_validation_boundaries() -> None:
    """Test Case 11: Policy validation rejects limit=0, window_seconds=86401, and invalid names."""
    # limit=0 -> ValueError
    with pytest.raises(ValueError, match="Invalid limit"):
        RateLimitPolicy(name="valid_name", limit=0, window_seconds=60)

    # limit > 100000 -> ValueError
    with pytest.raises(ValueError, match="Invalid limit"):
        RateLimitPolicy(name="valid_name", limit=100001, window_seconds=60)

    # window_seconds=86401 -> ValueError
    with pytest.raises(ValueError, match="Invalid window_seconds"):
        RateLimitPolicy(name="valid_name", limit=10, window_seconds=86401)

    # window_seconds=0 -> ValueError
    with pytest.raises(ValueError, match="Invalid window_seconds"):
        RateLimitPolicy(name="valid_name", limit=10, window_seconds=0)

    # name='Bad Name' (uppercase and space) -> ValueError
    with pytest.raises(ValueError, match="Invalid policy name"):
        RateLimitPolicy(name="Bad Name", limit=10, window_seconds=60)

    # name too short (<3 chars) -> ValueError
    with pytest.raises(ValueError, match="Invalid policy name"):
        RateLimitPolicy(name="ab", limit=10, window_seconds=60)

    # name too long (>48 chars) -> ValueError
    with pytest.raises(ValueError, match="Invalid policy name"):
        RateLimitPolicy(name="a" * 49, limit=10, window_seconds=60)

    # invalid fail_mode -> ValueError
    with pytest.raises(ValueError, match="Invalid fail_mode"):
        RateLimitPolicy(name="valid_name", limit=10, window_seconds=60, fail_mode="unknown")  # type: ignore[arg-type]


def test_predefined_policy_constants() -> None:
    """Verify all 6 predefined policy constants exist with required parameters."""
    assert AUTH_LOGIN_ACCOUNT.name == "auth_login_account"
    assert AUTH_LOGIN_ACCOUNT.limit == 5
    assert AUTH_LOGIN_ACCOUNT.window_seconds == 900

    assert AUTH_LOGIN_IP.name == "auth_login_ip"
    assert AUTH_LOGIN_IP.limit == 20
    assert AUTH_LOGIN_IP.window_seconds == 900

    assert AUTH_MFA_VERIFY.name == "auth_mfa_verify"
    assert AUTH_MFA_VERIFY.limit == 5
    assert AUTH_MFA_VERIFY.window_seconds == 300

    assert SETUP_CLAIM_IP.name == "setup_claim_ip"
    assert SETUP_CLAIM_IP.limit == 10
    assert SETUP_CLAIM_IP.window_seconds == 3600

    assert MEDIA_PROXY_PRINCIPAL.name == "media_proxy_principal"
    assert MEDIA_PROXY_PRINCIPAL.limit == 120
    assert MEDIA_PROXY_PRINCIPAL.window_seconds == 60

    assert ATTACHMENT_UPLOAD_PRINCIPAL.name == "attachment_upload_principal"
    assert ATTACHMENT_UPLOAD_PRINCIPAL.limit == 30
    assert ATTACHMENT_UPLOAD_PRINCIPAL.window_seconds == 60


def test_build_rate_limiter_factory(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify build_rate_limiter factory returns PgRateLimiter or ValkeyRateLimiter."""
    # 1. Standalone mode -> PgRateLimiter
    monkeypatch.setenv("KANBAN_DEPLOYMENT_MODE", "standalone")
    monkeypatch.delenv("KANBAN_VALKEY_URL", raising=False)
    lim1 = build_rate_limiter()
    assert isinstance(lim1, PgRateLimiter)

    # 2. Production mode without valkey URL -> PgRateLimiter
    monkeypatch.setenv("KANBAN_DEPLOYMENT_MODE", "production")
    monkeypatch.delenv("KANBAN_VALKEY_URL", raising=False)
    lim2 = build_rate_limiter()
    assert isinstance(lim2, PgRateLimiter)

    # 3. Production mode with valkey client -> ValkeyRateLimiter
    fake_vk = FakeValkey()
    lim3 = build_rate_limiter(valkey_client=fake_vk)
    assert isinstance(lim3, ValkeyRateLimiter)

    # 4. Production mode with KANBAN_VALKEY_URL -> ValkeyRateLimiter
    monkeypatch.setenv("KANBAN_VALKEY_URL", "redis://localhost:6379")
    lim4 = build_rate_limiter()
    assert isinstance(lim4, ValkeyRateLimiter)

    # 5. Settings object with attributes
    class DummySettings:
        deployment_mode = "standalone"
        valkey_url = None

    lim5 = build_rate_limiter(DummySettings())
    assert isinstance(lim5, PgRateLimiter)

    # 6. Fallback env vars KB_DEPLOYMENT_MODE and KB_VALKEY_URL
    monkeypatch.delenv("KANBAN_DEPLOYMENT_MODE", raising=False)
    monkeypatch.delenv("KANBAN_VALKEY_URL", raising=False)
    monkeypatch.setenv("KB_DEPLOYMENT_MODE", "production")
    monkeypatch.setenv("KB_VALKEY_URL", "redis://localhost:6379")
    lim6 = build_rate_limiter()
    assert isinstance(lim6, ValkeyRateLimiter)

    # 7. Production mode via settings object with valkey_url
    class ProdSettings:
        deployment_mode = "production"
        valkey_url = "redis://localhost:6379"

    lim7 = build_rate_limiter(ProdSettings())
    assert isinstance(lim7, ValkeyRateLimiter)

    # 8. String parameter for settings
    lim8 = build_rate_limiter("standalone")
    assert isinstance(lim8, PgRateLimiter)


@pytest.mark.asyncio
async def test_decorator_default_factory_construction(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify rate_limited builds limiter using default build_rate_limiter when none provided."""
    monkeypatch.setenv("KANBAN_DEPLOYMENT_MODE", "standalone")
    policy = RateLimitPolicy(name="auto_build_pol", limit=5, window_seconds=60, fail_mode="open")

    app = FastAPI()
    dep = rate_limited(
        policy=policy,
        key_func=lambda _req: ["auto_part"],
        session_hmac_key=b"k" * 32,
    )

    @app.get("/auto-test", dependencies=[Depends(dep)])
    async def handler() -> dict[str, str]:
        return {"status": "ok"}

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        res = await client.get("/auto-test")
        assert res.status_code == 200


@pytest.mark.asyncio
async def test_deferred_valkey_client_eval_rejection(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify deferred Valkey placeholder client raises RuntimeError upon eval execution."""
    monkeypatch.setenv("KANBAN_DEPLOYMENT_MODE", "production")
    monkeypatch.setenv("KANBAN_VALKEY_URL", "redis://localhost:6379")
    limiter = build_rate_limiter()
    assert isinstance(limiter, ValkeyRateLimiter)

    policy = RateLimitPolicy(name="deferred_test", limit=5, window_seconds=60)
    with pytest.raises(RuntimeError, match="Concrete Valkey client connection is deferred"):
        await limiter.hit(policy, b"0" * 32)


def test_make_key_resolution_branches(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify make_key key material resolution from params, env, and failure modes."""
    policy = RateLimitPolicy(name="key_res", limit=10, window_seconds=60)

    # 1. Explicit session_hmac_key
    k1 = make_key(policy, "part1", session_hmac_key=b"1" * 32)
    assert len(k1) == 32

    # 2. Environment variable KANBAN_SESSION_HMAC_KEY
    b64_key = base64.urlsafe_b64encode(b"2" * 32).decode("ascii").rstrip("=")
    monkeypatch.setenv("KANBAN_SESSION_HMAC_KEY", b64_key)
    monkeypatch.delenv("KANBAN_KEYRING_FILE", raising=False)
    monkeypatch.delenv("KANBAN_MASTER_KEK", raising=False)
    k2 = make_key(policy, "part1")
    assert len(k2) == 32

    # 3. Missing key material raises ValueError
    monkeypatch.delenv("KANBAN_SESSION_HMAC_KEY", raising=False)
    monkeypatch.delenv("KB_SESSION_HMAC_KEY", raising=False)
    monkeypatch.delenv("KANBAN_KEYRING_FILE", raising=False)
    monkeypatch.delenv("KANBAN_MASTER_KEK", raising=False)
    with pytest.raises(ValueError, match="session_hmac_key must be provided"):
        make_key(policy, "part1")


@pytest.mark.asyncio
async def test_decorator_app_state_dependencies() -> None:
    """Verify rate_limited decorator resolves limiter and key material from app.state."""
    fake_valkey = FakeValkey()
    limiter = ValkeyRateLimiter(fake_valkey)
    policy = RateLimitPolicy(name="app_state_pol", limit=5, window_seconds=60)

    km = KeyMaterial(
        master_kek=b"m" * 32,
        auth_pepper=b"p" * 32,
        session_hmac_key=b"s" * 32,
    )

    app = FastAPI()
    app.state.rate_limiter = limiter
    app.state.key_material = km

    dep = rate_limited(
        policy=policy,
        key_func=lambda _req: ["state_part"],
    )

    @app.get("/state-test", dependencies=[Depends(dep)])
    async def handler() -> dict[str, str]:
        return {"status": "ok"}

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        res = await client.get("/state-test")
        assert res.status_code == 200


@pytest.mark.asyncio
async def test_async_key_func_support() -> None:
    """Verify rate_limited decorator correctly awaits async key extraction callables."""
    fake_valkey = FakeValkey()
    limiter = ValkeyRateLimiter(fake_valkey)
    policy = RateLimitPolicy(name="async_key_policy", limit=1, window_seconds=60)

    app = FastAPI()
    app.add_exception_handler(ProblemException, problem_exception_handler)  # type: ignore[arg-type]

    async def async_keys(req: Request) -> list[str]:
        return [resolve_client_ip(req.scope)]

    dep = rate_limited(
        policy=policy,
        key_func=async_keys,
        limiter=limiter,
        session_hmac_key=b"a" * 32,
    )

    @app.get("/api/async-check", dependencies=[Depends(dep)])
    async def endpoint() -> dict[str, str]:
        return {"msg": "ok"}

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        r1 = await client.get("/api/async-check")
        assert r1.status_code == 200
        r2 = await client.get("/api/async-check")
        assert r2.status_code == 429
