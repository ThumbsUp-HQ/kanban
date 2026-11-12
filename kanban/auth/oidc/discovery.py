# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""OIDC discovery document retrieval and rate-limited JWKS caching (KB-P2-06)."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from http import HTTPStatus
from typing import TYPE_CHECKING, Any, Final, cast

import httpx
from joserfc.errors import JoseError
from joserfc.jwk import KeySet

if TYPE_CHECKING:
    import uuid

DISCOVERY_TIMEOUT_SECONDS: Final[float] = 5.0
MAX_DISCOVERY_BYTES: Final[int] = 262144  # 256 KiB
MAX_JWKS_KEYS: Final[int] = 20
DEFAULT_JWKS_TTL_SECONDS: Final[float] = 3600.0  # 1 hour
DEFAULT_REFETCH_COOLDOWN_SECONDS: Final[float] = 60.0  # 60s flood protection

# Error codes
ERR_REDIRECT_REFUSED: Final[str] = "REDIRECT_REFUSED"
ERR_DISCOVERY_FAILED: Final[str] = "DISCOVERY_FAILED"
ERR_RESPONSE_TOO_LARGE: Final[str] = "RESPONSE_TOO_LARGE"
ERR_ISSUER_MISMATCH: Final[str] = "ISSUER_MISMATCH"
ERR_JWKS_FETCH_FAILED: Final[str] = "JWKS_FETCH_FAILED"
ERR_JWKS_TOO_LARGE: Final[str] = "JWKS_TOO_LARGE"
ERR_JWKS_PRIVATE_KEY_FORBIDDEN: Final[str] = "JWKS_PRIVATE_KEY_FORBIDDEN"
ERR_JWKS_PARSE_FAILED: Final[str] = "JWKS_PARSE_FAILED"


class OidcError(Exception):
    """Domain exception for OIDC / OAuth2 protocol failures.

    Does not leak remote response bodies in string representations.
    """

    def __init__(self, code: str, message: str = "") -> None:
        """Initialize OidcError with code and message."""
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}" if message else code)


@dataclass(frozen=True, slots=True)
class OidcDiscoveryDoc:
    """Resolved endpoints and metadata from OpenID Connect configuration."""

    issuer: str
    authorization_endpoint: str
    token_endpoint: str
    jwks_uri: str
    userinfo_endpoint: str | None = None
    id_token_signing_alg_values_supported: list[str] = field(default_factory=list)


async def fetch_discovery(
    issuer: str,
    client: httpx.AsyncClient | None = None,
) -> OidcDiscoveryDoc:
    """Fetch and validate .well-known/openid-configuration with mix-up protection."""
    url = f"{issuer.rstrip('/')}/.well-known/openid-configuration"

    async def _do_fetch(http_client: httpx.AsyncClient) -> httpx.Response:
        return await http_client.get(
            url,
            headers={"Accept": "application/json"},
            timeout=httpx.Timeout(DISCOVERY_TIMEOUT_SECONDS),
        )

    if client is not None:
        response = await _do_fetch(client)
    else:
        async with httpx.AsyncClient(follow_redirects=False) as default_client:
            response = await _do_fetch(default_client)

    if response.is_redirect:
        msg = "Discovery endpoint returned a redirect"
        raise OidcError(ERR_REDIRECT_REFUSED, msg)

    if response.status_code != HTTPStatus.OK:
        msg = f"Discovery endpoint returned HTTP {response.status_code}"
        raise OidcError(ERR_DISCOVERY_FAILED, msg)

    if len(response.content) > MAX_DISCOVERY_BYTES:
        msg = f"Discovery response exceeded {MAX_DISCOVERY_BYTES} bytes"
        raise OidcError(ERR_RESPONSE_TOO_LARGE, msg)

    try:
        data: dict[str, Any] = response.json()
    except (ValueError, TypeError, KeyError) as err:
        msg = f"Discovery endpoint returned invalid JSON: {err}"
        raise OidcError(ERR_DISCOVERY_FAILED, msg) from err

    # Section 4.2: returned issuer must equal configured issuer byte-for-byte
    returned_issuer = data.get("issuer")
    if returned_issuer != issuer.rstrip("/"):
        msg = (
            f"Discovery doc issuer '{returned_issuer}' does not match configured issuer '{issuer}'"
        )
        raise OidcError(ERR_ISSUER_MISMATCH, msg)

    auth_ep = data.get("authorization_endpoint")
    token_ep = data.get("token_endpoint")
    jwks_uri = data.get("jwks_uri")

    if not auth_ep or not token_ep or not jwks_uri:
        msg = "Discovery doc missing required endpoints (authorization, token, or jwks_uri)"
        raise OidcError(ERR_DISCOVERY_FAILED, msg)

    return OidcDiscoveryDoc(
        issuer=str(returned_issuer),
        authorization_endpoint=str(auth_ep),
        token_endpoint=str(token_ep),
        jwks_uri=str(jwks_uri),
        userinfo_endpoint=str(data["userinfo_endpoint"]) if "userinfo_endpoint" in data else None,
        id_token_signing_alg_values_supported=list(
            data.get("id_token_signing_alg_values_supported", [])
        ),
    )


@dataclass(slots=True)
class _JwksCacheEntry:
    keyset: KeySet
    kids: set[str]
    fetched_at: float
    last_refetch_at: float


class JwksCache:
    """Per-card rate-limited cache for JWKS keysets with JWKS flooding defense."""

    def __init__(
        self,
        ttl_seconds: float = DEFAULT_JWKS_TTL_SECONDS,
        refetch_cooldown_seconds: float = DEFAULT_REFETCH_COOLDOWN_SECONDS,
    ) -> None:
        """Initialize JwksCache with TTL and flood defense cooldown."""
        self._ttl = ttl_seconds
        self._cooldown = refetch_cooldown_seconds
        self._cache: dict[uuid.UUID, _JwksCacheEntry] = {}

    def clear(self) -> None:
        """Clear all cached JWKS keysets."""
        self._cache.clear()

    async def get_keyset(
        self,
        card_id: uuid.UUID,
        jwks_uri: str,
        *,
        kid: str | None = None,
        client: httpx.AsyncClient | None = None,
        now: float | None = None,
    ) -> KeySet:
        """Retrieve cached KeySet, refetching if expired or unknown kid arrives outside cooldown."""
        current_time = time.time() if now is None else now
        entry = self._cache.get(card_id)

        if entry is not None:
            if kid is not None:
                if kid in entry.kids:
                    return entry.keyset
                # Unknown kid: check flood cooldown
                if current_time - entry.last_refetch_at < self._cooldown:
                    return entry.keyset
            elif current_time - entry.fetched_at < self._ttl:
                return entry.keyset

        # Perform fetch
        keyset, kids = await self._fetch_jwks(jwks_uri, client=client)

        refetch_time = current_time
        self._cache[card_id] = _JwksCacheEntry(
            keyset=keyset,
            kids=kids,
            fetched_at=current_time,
            last_refetch_at=refetch_time,
        )
        return keyset

    async def _fetch_jwks(  # noqa: C901
        self,
        jwks_uri: str,
        client: httpx.AsyncClient | None = None,
    ) -> tuple[KeySet, set[str]]:
        """Fetch and parse JWKS, rejecting private keys and payloads over 20 keys."""

        async def _do_fetch(http_client: httpx.AsyncClient) -> httpx.Response:
            return await http_client.get(
                jwks_uri,
                headers={"Accept": "application/json"},
                timeout=httpx.Timeout(DISCOVERY_TIMEOUT_SECONDS),
            )

        if client is not None:
            response = await _do_fetch(client)
        else:
            async with httpx.AsyncClient(follow_redirects=False) as default_client:
                response = await _do_fetch(default_client)

        if response.is_redirect:
            msg = "JWKS endpoint returned a redirect"
            raise OidcError(ERR_REDIRECT_REFUSED, msg)

        if response.status_code != HTTPStatus.OK:
            msg = f"JWKS endpoint returned HTTP {response.status_code}"
            raise OidcError(ERR_JWKS_FETCH_FAILED, msg)

        if len(response.content) > MAX_DISCOVERY_BYTES:
            msg = f"JWKS response exceeded {MAX_DISCOVERY_BYTES} bytes"
            raise OidcError(ERR_RESPONSE_TOO_LARGE, msg)

        try:
            data: dict[str, Any] = response.json()
        except (ValueError, TypeError, KeyError) as err:
            msg = f"JWKS endpoint returned invalid JSON: {err}"
            raise OidcError(ERR_JWKS_FETCH_FAILED, msg) from err

        raw_keys = data.get("keys")
        keys_list: list[object] = raw_keys if isinstance(raw_keys, list) else []
        if len(keys_list) > MAX_JWKS_KEYS:
            msg = f"JWKS contains {len(keys_list)} keys, exceeding limit of {MAX_JWKS_KEYS}"
            raise OidcError(ERR_JWKS_TOO_LARGE, msg)

        # Security check: forbid private key components (d, p, q, dp, dq, qi)
        banned_private_members = {"d", "p", "q", "dp", "dq", "qi"}
        kids: set[str] = set()

        for k in keys_list:
            if not isinstance(k, dict):
                continue
            if banned_private_members.intersection(k.keys()):
                msg = "JWKS entry contains prohibited private key members"
                raise OidcError(ERR_JWKS_PRIVATE_KEY_FORBIDDEN, msg)
            kid_val = k.get("kid")
            if isinstance(kid_val, str):
                kids.add(kid_val)

        try:
            keyset = KeySet.import_key_set(cast("Any", data))
        except (ValueError, TypeError, KeyError, JoseError) as err:
            msg = f"Failed to parse JWKS: {err}"
            raise OidcError(ERR_JWKS_PARSE_FAILED, msg) from err

        return keyset, kids
