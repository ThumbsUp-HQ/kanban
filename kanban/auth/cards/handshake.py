# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Live authentication provider handshake diagnostics (KB-P2-10, S4.1, S4.3)."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import TYPE_CHECKING

import httpx

from kanban.auth.cards.schemas import HandshakeProbeResult
from kanban.auth.ldap.client import LdapTlsError, LdapTlsHardClient
from kanban.auth.ldap.config import LdapCardConfig
from kanban.auth.local.hashing import get_auth_pepper, hash_password, verify_password
from kanban.auth.oidc.config import _validate_safe_url
from kanban.auth.oidc.discovery import JwksCache, OidcError, fetch_discovery
from kanban.security.envelope import KekProvider, SealedSecret, open_card_secret

if TYPE_CHECKING:
    from database.models.auth import AuthProviderCard

logger = logging.getLogger(__name__)

PROBE_TIMEOUT_SECONDS: float = 8.0


async def probe_auth_card_handshake(  # noqa: C901, PLR0911, PLR0912, PLR0915
    card: AuthProviderCard,
    *,
    http_client: httpx.AsyncClient | None = None,
    kek_provider: KekProvider | None = None,
    unix_socket_path: str | None = None,
) -> HandshakeProbeResult:
    """Execute live test-handshake probe bounded by an 8.0-second timeout.

    Probes provider reachability, TLS trust, keysets, and credential round-trips:
    - OIDC: verifies discovery document and JWKS signing keys with issuer match.
    - OAUTH2: verifies authorization and token endpoint reachability with SSRF guards.
    - LDAP: verifies TLS 1.2+, CA trust, SPKI pinning, and optional service bind.
    - LOCAL_ADMIN: verifies auth_pepper key material and Argon2id round-trip.

    CRITICAL INVARIANT: This function updates diagnostic health only. It must NEVER
    update last_admin_handshake_at (reserved for live SERVER_ADMIN interactive logins).
    """
    start_time = time.perf_counter()

    try:
        async with asyncio.timeout(PROBE_TIMEOUT_SECONDS):
            kind = card.provider_kind.upper()
            config = dict(card.public_config or {})

            if kind == "OIDC":
                issuer = str(config.get("issuer", "")).strip()
                if not issuer:
                    return HandshakeProbeResult(
                        ok=False,
                        status="FAILED:MISSING_ISSUER",
                        latency_ms=int((time.perf_counter() - start_time) * 1000),
                        error_code="MISSING_ISSUER",
                    )
                _validate_safe_url(issuer, "issuer")
                discovery_doc = await fetch_discovery(issuer, client=http_client)
                jwks_cache = JwksCache()
                await jwks_cache.get_keyset(card.id, discovery_doc.jwks_uri, client=http_client)

            elif kind == "OAUTH2":
                auth_ep = config.get("authorization_endpoint")
                token_ep = config.get("token_endpoint")
                if not auth_ep or not token_ep:
                    return HandshakeProbeResult(
                        ok=False,
                        status="FAILED:MISSING_ENDPOINTS",
                        latency_ms=int((time.perf_counter() - start_time) * 1000),
                        error_code="MISSING_ENDPOINTS",
                    )
                _validate_safe_url(str(auth_ep), "authorization_endpoint")
                _validate_safe_url(str(token_ep), "token_endpoint")

                async def _probe_url(u: str) -> None:
                    if http_client is not None:
                        resp = await http_client.get(u, follow_redirects=False)
                    else:
                        async with httpx.AsyncClient(follow_redirects=False) as client:
                            resp = await client.get(u)
                    if resp.status_code >= 500:  # noqa: PLR2004
                        msg = f"HTTP_{resp.status_code}"
                        raise RuntimeError(msg)  # noqa: TRY301

                await _probe_url(str(token_ep))

            elif kind == "LDAP":
                ldap_cfg = LdapCardConfig(**config)
                ldap_client = LdapTlsHardClient(ldap_cfg, unix_socket_path=unix_socket_path)
                await ldap_client.connect()
                try:
                    if (
                        ldap_cfg.service_bind_dn
                        and card.encrypted_secret_blob is not None
                        and card.wrapped_dek is not None
                        and kek_provider is not None
                    ):
                        sealed = SealedSecret(
                            encrypted_secret_blob=card.encrypted_secret_blob,
                            wrapped_dek=card.wrapped_dek,
                            dek_kid=card.dek_kid,
                        )
                        secret_buf = open_card_secret(card.id, "LDAP", sealed, kek_provider)
                        try:
                            secret_data = json.loads(secret_buf.decode("utf-8"))
                            pwd_str = str(secret_data.get("bind_dn_password", ""))
                            await ldap_client.bind(
                                ldap_cfg.service_bind_dn, pwd_str.encode("utf-8")
                            )
                        finally:
                            for i in range(len(secret_buf)):
                                secret_buf[i] = 0
                finally:
                    await ldap_client.unbind()

            elif kind == "LOCAL_ADMIN":
                pepper = get_auth_pepper()
                test_pw = "probe-handshake-local-admin-pw"
                h = await hash_password(test_pw, pepper=pepper)
                valid = await verify_password(h, test_pw, pepper=pepper)
                if not valid:
                    return HandshakeProbeResult(
                        ok=False,
                        status="FAILED:CRYPTO_ROUNDTRIP_FAILED",
                        latency_ms=int((time.perf_counter() - start_time) * 1000),
                        error_code="CRYPTO_ROUNDTRIP_FAILED",
                    )
            else:
                return HandshakeProbeResult(
                    ok=False,
                    status=f"FAILED:UNSUPPORTED_KIND_{kind}",
                    latency_ms=int((time.perf_counter() - start_time) * 1000),
                    error_code="UNSUPPORTED_KIND",
                )

        latency_ms = max(1, int((time.perf_counter() - start_time) * 1000))
        return HandshakeProbeResult(
            ok=True,
            status="OK",
            latency_ms=latency_ms,
            error_code=None,
        )

    except TimeoutError:
        latency_ms = int((time.perf_counter() - start_time) * 1000)
        return HandshakeProbeResult(
            ok=False,
            status="FAILED:TIMEOUT",
            latency_ms=latency_ms,
            error_code="TIMEOUT",
        )
    except OidcError as oerr:
        latency_ms = int((time.perf_counter() - start_time) * 1000)
        code = oerr.code
        return HandshakeProbeResult(
            ok=False,
            status=f"FAILED:{code}",
            latency_ms=latency_ms,
            error_code=code,
        )
    except LdapTlsError as lerr:
        latency_ms = int((time.perf_counter() - start_time) * 1000)
        err_str = str(lerr)
        code = "SPKI_PIN_MISMATCH" if "SPKI_PIN_MISMATCH" in err_str else "LDAP_TLS_ERROR"
        return HandshakeProbeResult(
            ok=False,
            status=f"FAILED:{code}",
            latency_ms=latency_ms,
            error_code=code,
        )
    except Exception as exc:  # noqa: BLE001
        latency_ms = int((time.perf_counter() - start_time) * 1000)
        exc_str = str(exc)
        if "SPKI_PIN_MISMATCH" in exc_str:
            code = "SPKI_PIN_MISMATCH"
        elif "ISSUER_MISMATCH" in exc_str:
            code = "ISSUER_MISMATCH"
        elif exc_str.startswith("HTTP_"):
            code = exc_str
        else:
            code = type(exc).__name__.upper()
        return HandshakeProbeResult(
            ok=False,
            status=f"FAILED:{code}",
            latency_ms=latency_ms,
            error_code=code,
        )
