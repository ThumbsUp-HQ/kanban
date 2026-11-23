# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Feature unit and security tests for bounded-lifetime media proxy signed URLs (KAN-325).

Covers:
  1. Default bounded TTL (24h) and maximum TTL bounds (7 days).
  2. Bounded-lifetime expiration timestamp (exp) generation in signed URLs.
  3. Replay attack rejection: expired exp timestamps fail verification and return 403.
  4. Expiration tampering rejection: modified exp parameter fails HMAC verification.
  5. URL tampering rejection: modified target URL fails HMAC verification.
  6. Signature tampering rejection: modified signature fails constant-time check.
  7. Far-future timestamp rejection: exp exceeding MAX_MEDIA_PROXY_TTL_SECONDS rejected.
  8. Missing exp rejection: requests without exp parameter return 403 INVALID_SIGNATURE.
  9. End-to-end ASGI endpoint integration: valid fresh signed URLs succeed, expired URLs blocked.
"""

from __future__ import annotations

import time
import uuid
from unittest.mock import AsyncMock
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest

from kanban.api.deps import PrincipalContext
from kanban.api.problems import ProblemException
from kanban.app import create_app
from kanban.media_proxy.service import MediaProxyService
from kanban.media_proxy.signing import (
    DEFAULT_MEDIA_PROXY_TTL_SECONDS,
    MAX_MEDIA_PROXY_TTL_SECONDS,
    sign_media_proxy_url,
    verify_media_proxy_url,
)
from kanban.security.keys import KeyMaterial
from kanban.security.ratelimit.valkey import ValkeyRateLimiter
from kanban.settings import Settings
from kanban.tests.security.fakes import FakeValkey


class _TestPrincipalResolver:
    """Configurable principal resolver for testing authenticated routes."""

    def __init__(self, principal: PrincipalContext | None = None) -> None:
        self.principal = principal

    async def resolve(self, _request: object) -> PrincipalContext | None:
        return self.principal


@pytest.fixture
def key_material() -> KeyMaterial:
    """Return KeyMaterial fixture for media proxy signing tests."""
    return KeyMaterial(
        master_kek=b"K" * 32,
        auth_pepper=b"P" * 32,
        session_hmac_key=b"H" * 32,
    )


@pytest.fixture
def auth_principal() -> PrincipalContext:
    """Return PrincipalContext fixture for authenticated user."""
    return PrincipalContext(
        principal_id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        token_scopes=("session",),
    )


def test_sign_media_proxy_url_default_bounded_lifetime(key_material: KeyMaterial) -> None:
    """Verify signed URLs incorporate default bounded expiration (24 hours)."""
    target_url = "https://cdn.example.com/assets/diagram.png"
    now_before = int(time.time())
    signed = sign_media_proxy_url(target_url, key_material)
    now_after = int(time.time())

    assert signed.startswith("/api/v1/media-proxy?")
    parsed = urlsplit(signed)
    qs = parse_qs(parsed.query)

    assert "u" in qs
    assert "exp" in qs
    assert "sig" in qs

    exp = int(qs["exp"][0])
    sig = qs["sig"][0]

    min_exp = now_before + DEFAULT_MEDIA_PROXY_TTL_SECONDS
    max_exp = now_after + DEFAULT_MEDIA_PROXY_TTL_SECONDS
    assert min_exp <= exp <= max_exp
    assert verify_media_proxy_url(target_url, sig, key_material, exp=exp) is True


def test_sign_media_proxy_url_custom_ttl_and_bounds(key_material: KeyMaterial) -> None:
    """Verify custom TTL within allowed bounds and rejection of invalid TTLs."""
    target_url = "https://cdn.example.com/photo.jpg"

    # Custom 1-hour TTL
    signed = sign_media_proxy_url(target_url, key_material, expires_in=3600)
    qs = parse_qs(urlsplit(signed).query)
    exp = int(qs["exp"][0])
    now = int(time.time())
    assert now + 3590 <= exp <= now + 3610

    # Negative or zero TTL rejected
    with pytest.raises(ProblemException) as exc_zero:
        sign_media_proxy_url(target_url, key_material, expires_in=0)
    assert exc_zero.value.code == "INVALID_MEDIA_URL"
    assert exc_zero.value.status == 400

    # Excessive TTL (> 7 days) rejected
    with pytest.raises(ProblemException) as exc_excessive:
        sign_media_proxy_url(target_url, key_material, expires_in=MAX_MEDIA_PROXY_TTL_SECONDS + 1)
    assert exc_excessive.value.code == "INVALID_MEDIA_URL"
    assert exc_excessive.value.status == 400


def test_verify_media_proxy_url_expired_timestamp_rejected(key_material: KeyMaterial) -> None:
    """Verify that expired timestamp (exp < now) fails verification."""
    target_url = "https://cdn.example.com/stale.png"
    now = int(time.time())

    # Sign with explicit expired timestamp (5 minutes in the past)
    past_exp = now - 300
    signed = sign_media_proxy_url(target_url, key_material, exp=past_exp)
    qs = parse_qs(urlsplit(signed).query)
    sig = qs["sig"][0]

    # Verification must fail closed
    assert verify_media_proxy_url(target_url, sig, key_material, exp=past_exp) is False


def test_verify_media_proxy_url_tampered_expiration_rejected(key_material: KeyMaterial) -> None:
    """Verify that extending exp without recomputing HMAC fails verification."""
    target_url = "https://cdn.example.com/protected.png"
    signed = sign_media_proxy_url(target_url, key_material, expires_in=300)
    qs = parse_qs(urlsplit(signed).query)
    original_exp = int(qs["exp"][0])
    sig = qs["sig"][0]

    # Attacker tries to extend expiration by 1 day
    tampered_exp = original_exp + 86400
    assert verify_media_proxy_url(target_url, sig, key_material, exp=tampered_exp) is False


def test_verify_media_proxy_url_tampered_target_rejected(key_material: KeyMaterial) -> None:
    """Verify that swapping the target URL fails verification."""
    target_url = "https://cdn.example.com/good.png"
    signed = sign_media_proxy_url(target_url, key_material)
    qs = parse_qs(urlsplit(signed).query)
    exp = int(qs["exp"][0])
    sig = qs["sig"][0]

    attacker_url = "https://evil.example.com/exploit.png"
    assert verify_media_proxy_url(attacker_url, sig, key_material, exp=exp) is False


def test_verify_media_proxy_url_missing_exp_rejected(key_material: KeyMaterial) -> None:
    """Verify that omitting exp fails verification."""
    target_url = "https://cdn.example.com/image.png"
    signed = sign_media_proxy_url(target_url, key_material)
    qs = parse_qs(urlsplit(signed).query)
    sig = qs["sig"][0]

    assert verify_media_proxy_url(target_url, sig, key_material, exp=None) is False


def test_verify_media_proxy_url_far_future_rejected(key_material: KeyMaterial) -> None:
    """Verify that expiration timestamp exceeding maximum bounding window is rejected."""
    target_url = "https://cdn.example.com/image.png"
    now = int(time.time())
    far_future_exp = now + MAX_MEDIA_PROXY_TTL_SECONDS + 1000

    signed = sign_media_proxy_url(target_url, key_material, exp=far_future_exp)
    qs = parse_qs(urlsplit(signed).query)
    sig = qs["sig"][0]

    assert verify_media_proxy_url(target_url, sig, key_material, exp=far_future_exp) is False


def test_verify_media_proxy_url_edge_cases(key_material: KeyMaterial) -> None:
    """Verify defensive handling of invalid signatures and empty targets."""
    now = int(time.time())
    exp = now + 3600

    assert verify_media_proxy_url("", "sig", key_material, exp=exp) is False
    assert verify_media_proxy_url("https://example.com/a.png", "", key_material, exp=exp) is False
    assert (
        verify_media_proxy_url("https://example.com/a.png", "a" * 65, key_material, exp=exp)
        is False
    )
    assert (
        verify_media_proxy_url("https://example.com/a.png", "bad!!!base64", key_material, exp=exp)
        is False
    )


@pytest.mark.asyncio
async def test_get_media_proxy_endpoint_with_bounded_exp(
    key_material: KeyMaterial,
    auth_principal: PrincipalContext,
) -> None:
    """Verify live ASGI /api/v1/media-proxy endpoint honors exp validation."""
    settings = Settings(
        deployment_mode="standalone",
        public_base_url="http://testserver",
    )
    app = create_app(settings)
    app.state.key_material = key_material
    app.state.principal_resolver = _TestPrincipalResolver(auth_principal)
    app.state.rate_limiter = ValkeyRateLimiter(FakeValkey())

    # Mock media proxy service returning clean png
    mock_service = AsyncMock(spec=MediaProxyService)
    mock_service.fetch_proxy_media.return_value = (
        "image/png",
        b"\x89PNG\r\n\x1a\nfake_image_bytes",
        {"x-kanban-media-status": "proxied"},
    )
    app.state.media_proxy_service = mock_service

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        raw_url = "https://cdn.example.com/assets/logo.png"

        # 1. Valid fresh signed URL succeeds
        valid_path = sign_media_proxy_url(raw_url, key_material, expires_in=1800)
        resp_valid = await client.get(valid_path)
        assert resp_valid.status_code == 200
        assert resp_valid.headers["content-type"] == "image/png"

        # 2. Missing exp query parameter rejected with 403
        qs = parse_qs(urlsplit(valid_path).query)
        sig = qs["sig"][0]
        resp_missing_exp = await client.get(f"/api/v1/media-proxy?u={raw_url}&sig={sig}")
        assert resp_missing_exp.status_code == 403
        assert resp_missing_exp.json()["code"] == "INVALID_SIGNATURE"

        # 3. Expired exp query parameter rejected with 403
        expired_path = sign_media_proxy_url(raw_url, key_material, exp=int(time.time()) - 60)
        resp_expired = await client.get(expired_path)
        assert resp_expired.status_code == 403
        assert resp_expired.json()["code"] == "INVALID_SIGNATURE"

        # 4. Tampered exp query parameter rejected with 403
        tampered_exp = int(qs["exp"][0]) + 9999
        tampered_path = f"/api/v1/media-proxy?u={raw_url}&exp={tampered_exp}&sig={sig}"
        resp_tampered = await client.get(tampered_path)
        assert resp_tampered.status_code == 403
        assert resp_tampered.json()["code"] == "INVALID_SIGNATURE"

        # 5. Tampered signature rejected with 403
        exp_param = qs["exp"][0]
        bad_sig_path = f"/api/v1/media-proxy?u={raw_url}&exp={exp_param}&sig=tampered_sig"
        resp_bad_sig = await client.get(bad_sig_path)
        assert resp_bad_sig.status_code == 403
        assert resp_bad_sig.json()["code"] == "INVALID_SIGNATURE"
