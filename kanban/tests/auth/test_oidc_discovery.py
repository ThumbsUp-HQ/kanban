# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Unit tests for OIDC discovery and rate-limited JWKS caching (KB-P2-06)."""

from __future__ import annotations

import uuid
from typing import Any

import httpx
import pytest
from joserfc.jwk import KeySet

from kanban.auth.oidc.discovery import (
    DEFAULT_JWKS_TTL_SECONDS,
    DEFAULT_REFETCH_COOLDOWN_SECONDS,
    JwksCache,
    OidcDiscoveryDoc,
    OidcError,
    fetch_discovery,
)
from kanban.tests.fixtures.fake_idp import FakeIdP


@pytest.fixture
def fake_idp() -> FakeIdP:
    """Fixture providing an in-memory FakeIdP instance."""
    return FakeIdP(issuer="https://idp.example.com")


@pytest.mark.asyncio
async def test_discovery_success(fake_idp: FakeIdP) -> None:
    """Verify normal retrieval and parsing of OpenID Connect discovery document."""
    async with httpx.AsyncClient(transport=fake_idp.as_transport()) as client:
        doc = await fetch_discovery(fake_idp.issuer, client=client)

    assert isinstance(doc, OidcDiscoveryDoc)
    assert doc.issuer == fake_idp.issuer
    assert doc.authorization_endpoint == f"{fake_idp.issuer}/oauth/authorize"
    assert doc.token_endpoint == f"{fake_idp.issuer}/oauth/token"
    assert doc.jwks_uri == f"{fake_idp.issuer}/.well-known/jwks.json"
    assert doc.userinfo_endpoint == f"{fake_idp.issuer}/oauth/userinfo"


@pytest.mark.asyncio
async def test_discovery_issuer_mixup_defense(fake_idp: FakeIdP) -> None:
    """Test 9: discovery doc whose issuer differs from configured -> OidcError(ISSUER_MISMATCH)."""
    fake_idp.discovery_override = lambda _req: httpx.Response(
        200,
        json={
            "issuer": "https://attacker.example.com",
            "authorization_endpoint": "https://attacker.example.com/auth",
            "token_endpoint": "https://attacker.example.com/token",
            "jwks_uri": "https://attacker.example.com/jwks",
        },
    )

    async with httpx.AsyncClient(transport=fake_idp.as_transport()) as client:
        with pytest.raises(OidcError) as exc_info:
            await fetch_discovery(fake_idp.issuer, client=client)

        assert exc_info.value.code == "ISSUER_MISMATCH"


@pytest.mark.asyncio
async def test_discovery_redirect_refused(fake_idp: FakeIdP) -> None:
    """Test 12 (part 2): redirect 302 from discovery endpoint is rejected."""
    fake_idp.discovery_override = lambda _req: httpx.Response(
        302,
        headers={"Location": "https://evil.example.com/redirect"},
    )

    async with httpx.AsyncClient(transport=fake_idp.as_transport()) as client:
        with pytest.raises(OidcError) as exc_info:
            await fetch_discovery(fake_idp.issuer, client=client)

        assert exc_info.value.code == "REDIRECT_REFUSED"


@pytest.mark.asyncio
async def test_discovery_http_error(fake_idp: FakeIdP) -> None:
    """Verify discovery endpoint returning non-200 HTTP code raises DISCOVERY_FAILED."""
    fake_idp.discovery_override = lambda _req: httpx.Response(500, text="Internal Error")

    async with httpx.AsyncClient(transport=fake_idp.as_transport()) as client:
        with pytest.raises(OidcError) as exc_info:
            await fetch_discovery(fake_idp.issuer, client=client)

        assert exc_info.value.code == "DISCOVERY_FAILED"


@pytest.mark.asyncio
async def test_discovery_oversized_response(fake_idp: FakeIdP) -> None:
    """Verify discovery document exceeding 256 KiB raises RESPONSE_TOO_LARGE."""
    oversized_data = {"issuer": fake_idp.issuer, "junk": "x" * 270000}
    fake_idp.discovery_override = lambda _req: httpx.Response(200, json=oversized_data)

    async with httpx.AsyncClient(transport=fake_idp.as_transport()) as client:
        with pytest.raises(OidcError) as exc_info:
            await fetch_discovery(fake_idp.issuer, client=client)

        assert exc_info.value.code == "RESPONSE_TOO_LARGE"


@pytest.mark.asyncio
async def test_discovery_invalid_json(fake_idp: FakeIdP) -> None:
    """Verify non-JSON response from discovery endpoint raises DISCOVERY_FAILED."""
    fake_idp.discovery_override = lambda _req: httpx.Response(200, text="not json")

    async with httpx.AsyncClient(transport=fake_idp.as_transport()) as client:
        with pytest.raises(OidcError) as exc_info:
            await fetch_discovery(fake_idp.issuer, client=client)

        assert exc_info.value.code == "DISCOVERY_FAILED"


@pytest.mark.asyncio
async def test_discovery_missing_endpoints(fake_idp: FakeIdP) -> None:
    """Verify discovery document missing required endpoints raises DISCOVERY_FAILED."""
    fake_idp.discovery_override = lambda _req: httpx.Response(
        200,
        json={"issuer": fake_idp.issuer},
    )

    async with httpx.AsyncClient(transport=fake_idp.as_transport()) as client:
        with pytest.raises(OidcError) as exc_info:
            await fetch_discovery(fake_idp.issuer, client=client)

        assert exc_info.value.code == "DISCOVERY_FAILED"


@pytest.mark.asyncio
async def test_jwks_cache_and_flood_defense(fake_idp: FakeIdP) -> None:
    """Test 10 (part 1): 50 tokens with random unknown kid within 60s -> exactly 1 JWKS refetch."""
    cache = JwksCache(
        ttl_seconds=DEFAULT_JWKS_TTL_SECONDS,
        refetch_cooldown_seconds=DEFAULT_REFETCH_COOLDOWN_SECONDS,
    )
    card_id = uuid.uuid4()
    jwks_uri = f"{fake_idp.issuer}/.well-known/jwks.json"

    async with httpx.AsyncClient(transport=fake_idp.as_transport()) as client:
        # Initial fetch
        keyset = await cache.get_keyset(card_id, jwks_uri, client=client, now=1000.0)
        assert isinstance(keyset, KeySet)
        assert fake_idp.jwks_fetch_count == 1

        # Known kid does not refetch
        keyset_known = await cache.get_keyset(
            card_id, jwks_uri, kid=fake_idp.kid, client=client, now=1005.0
        )
        assert keyset_known is not None
        assert fake_idp.jwks_fetch_count == 1

        # 50 requests with unknown kid within 60s cooldown
        for idx in range(50):
            unknown_kid = f"unknown-kid-{idx}"
            await cache.get_keyset(
                card_id, jwks_uri, kid=unknown_kid, client=client, now=1000.0 + (idx * 0.5)
            )

        # Because cooldown is 60s and time progressed only to 1025.0s, exactly 1 fetch total
        assert fake_idp.jwks_fetch_count == 1

        # Beyond 60s cooldown, an unknown kid triggers a single refetch
        await cache.get_keyset(
            card_id, jwks_uri, kid="new-kid-after-cooldown", client=client, now=1065.0
        )
        assert fake_idp.jwks_fetch_count == 2


@pytest.mark.asyncio
async def test_jwks_reject_private_key_members(fake_idp: FakeIdP) -> None:
    """Test 10 (part 2): JWKS containing 'd' member (private key leak) is rejected."""
    # Build JWKS with 'd' parameter present
    private_jwk = dict(fake_idp.jwk_public_dict)
    private_jwk["d"] = "fake-private-exponent"

    fake_idp.jwks_override = lambda _req: httpx.Response(
        200,
        json={"keys": [private_jwk]},
    )

    cache = JwksCache()
    card_id = uuid.uuid4()
    jwks_uri = f"{fake_idp.issuer}/.well-known/jwks.json"

    async with httpx.AsyncClient(transport=fake_idp.as_transport()) as client:
        with pytest.raises(OidcError) as exc_info:
            await cache.get_keyset(card_id, jwks_uri, client=client)

        assert exc_info.value.code == "JWKS_PRIVATE_KEY_FORBIDDEN"


@pytest.mark.asyncio
async def test_jwks_max_key_limit(fake_idp: FakeIdP) -> None:
    """Verify JWKS containing > 20 keys raises JWKS_TOO_LARGE."""
    too_many_keys = [{"kid": f"k-{i}", "kty": "RSA", "n": "abc", "e": "AQAB"} for i in range(25)]
    fake_idp.jwks_override = lambda _req: httpx.Response(200, json={"keys": too_many_keys})

    cache = JwksCache()
    card_id = uuid.uuid4()
    jwks_uri = f"{fake_idp.issuer}/.well-known/jwks.json"

    async with httpx.AsyncClient(transport=fake_idp.as_transport()) as client:
        with pytest.raises(OidcError) as exc_info:
            await cache.get_keyset(card_id, jwks_uri, client=client)

        assert exc_info.value.code == "JWKS_TOO_LARGE"


@pytest.mark.asyncio
async def test_jwks_redirect_refused(fake_idp: FakeIdP) -> None:
    """Verify redirect returned by JWKS endpoint raises REDIRECT_REFUSED."""
    fake_idp.jwks_override = lambda _req: httpx.Response(
        302,
        headers={"Location": "https://evil.example.com/jwks"},
    )

    cache = JwksCache()
    card_id = uuid.uuid4()
    jwks_uri = f"{fake_idp.issuer}/.well-known/jwks.json"

    async with httpx.AsyncClient(transport=fake_idp.as_transport()) as client:
        with pytest.raises(OidcError) as exc_info:
            await cache.get_keyset(card_id, jwks_uri, client=client)

        assert exc_info.value.code == "REDIRECT_REFUSED"


@pytest.mark.asyncio
async def test_jwks_http_failure(fake_idp: FakeIdP) -> None:
    """Verify non-200 HTTP code from JWKS endpoint raises JWKS_FETCH_FAILED."""
    fake_idp.jwks_override = lambda _req: httpx.Response(500, text="Internal Error")

    cache = JwksCache()
    card_id = uuid.uuid4()
    jwks_uri = f"{fake_idp.issuer}/.well-known/jwks.json"

    async with httpx.AsyncClient(transport=fake_idp.as_transport()) as client:
        with pytest.raises(OidcError) as exc_info:
            await cache.get_keyset(card_id, jwks_uri, client=client)

        assert exc_info.value.code == "JWKS_FETCH_FAILED"


@pytest.mark.asyncio
async def test_jwks_oversized_response(fake_idp: FakeIdP) -> None:
    """Verify JWKS response exceeding 256 KiB raises RESPONSE_TOO_LARGE."""
    oversized = {"keys": [fake_idp.jwk_public_dict], "padding": "x" * 270000}
    fake_idp.jwks_override = lambda _req: httpx.Response(200, json=oversized)

    cache = JwksCache()
    card_id = uuid.uuid4()
    jwks_uri = f"{fake_idp.issuer}/.well-known/jwks.json"

    async with httpx.AsyncClient(transport=fake_idp.as_transport()) as client:
        with pytest.raises(OidcError) as exc_info:
            await cache.get_keyset(card_id, jwks_uri, client=client)

        assert exc_info.value.code == "RESPONSE_TOO_LARGE"


@pytest.mark.asyncio
async def test_jwks_cache_clear(fake_idp: FakeIdP) -> None:
    """Verify clearing cache forces re-fetch on next request."""
    cache = JwksCache()
    card_id = uuid.uuid4()
    jwks_uri = f"{fake_idp.issuer}/.well-known/jwks.json"

    async with httpx.AsyncClient(transport=fake_idp.as_transport()) as client:
        await cache.get_keyset(card_id, jwks_uri, client=client)
        assert fake_idp.jwks_fetch_count == 1

        cache.clear()
        await cache.get_keyset(card_id, jwks_uri, client=client)
        assert fake_idp.jwks_fetch_count == 2


@pytest.mark.asyncio
async def test_jwks_ttl_hit_without_kid(fake_idp: FakeIdP) -> None:
    """Verify get_keyset without kid uses cached entry within TTL."""
    cache = JwksCache(ttl_seconds=3600.0)
    card_id = uuid.uuid4()
    jwks_uri = f"{fake_idp.issuer}/.well-known/jwks.json"

    async with httpx.AsyncClient(transport=fake_idp.as_transport()) as client:
        await cache.get_keyset(card_id, jwks_uri, client=client, now=1000.0)
        assert fake_idp.jwks_fetch_count == 1

        # Second call within TTL without kid
        keyset = await cache.get_keyset(card_id, jwks_uri, client=client, now=1500.0)
        assert isinstance(keyset, KeySet)
        assert fake_idp.jwks_fetch_count == 1


@pytest.mark.asyncio
async def test_jwks_malformed_json_and_keys(fake_idp: FakeIdP) -> None:
    """Verify JWKS parser handles non-JSON response, non-dict keys, and invalid JWK structure."""
    cache = JwksCache()
    card_id = uuid.uuid4()
    jwks_uri = f"{fake_idp.issuer}/.well-known/jwks.json"

    async with httpx.AsyncClient(transport=fake_idp.as_transport()) as client:
        # 1. Non-JSON response
        fake_idp.jwks_override = lambda _req: httpx.Response(200, text="not json at all")
        with pytest.raises(OidcError) as exc1:
            await cache.get_keyset(card_id, jwks_uri, client=client)
        assert exc1.value.code == "JWKS_FETCH_FAILED"

        # 2. Non-dict key entries skipped
        fake_idp.jwks_override = lambda _req: httpx.Response(
            200,
            json={"keys": ["not-a-dict", 12345, fake_idp.jwk_public_dict]},
        )
        keyset = await cache.get_keyset(card_id, jwks_uri, client=client)
        assert isinstance(keyset, KeySet)

        # 3. Invalid JWK structure causing import failure
        cache.clear()
        fake_idp.jwks_override = lambda _req: httpx.Response(
            200,
            json={"keys": [{"kty": "RSA", "kid": "broken"}]},  # Missing n, e
        )
        with pytest.raises(OidcError) as exc3:
            await cache.get_keyset(card_id, jwks_uri, client=client)
        assert exc3.value.code == "JWKS_PARSE_FAILED"


@pytest.mark.asyncio
async def test_default_client_fallback(fake_idp: FakeIdP, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify default httpx.AsyncClient fallback when client parameter is None."""
    real_async_client = httpx.AsyncClient

    def mock_async_client(**kwargs: Any) -> httpx.AsyncClient:  # noqa: ANN401
        kwargs["transport"] = fake_idp.as_transport()
        return real_async_client(**kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", mock_async_client)

    # 1. fetch_discovery with client=None
    doc = await fetch_discovery(fake_idp.issuer, client=None)
    assert doc.issuer == fake_idp.issuer

    # 2. get_keyset with client=None
    cache = JwksCache()
    card_id = uuid.uuid4()
    keyset = await cache.get_keyset(
        card_id, f"{fake_idp.issuer}/.well-known/jwks.json", client=None
    )
    assert isinstance(keyset, KeySet)
