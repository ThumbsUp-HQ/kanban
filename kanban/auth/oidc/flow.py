# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""OIDC and OAuth2 authorization-code flow orchestration with PKCE S256 (KB-P2-06)."""

from __future__ import annotations

import base64
import contextlib
import hashlib
import logging
import os
import re
import secrets
import urllib.parse
from datetime import UTC, datetime, timedelta
from http import HTTPStatus
from typing import TYPE_CHECKING, Final

import httpx
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import text
from starlette.requests import Request
from starlette.responses import RedirectResponse, Response

from kanban.api.problems import ProblemException
from kanban.auth.cards.repository import get_for_login
from kanban.auth.identity import (
    MAX_SUBJECT_LENGTH,
    ExternalIdentityAssertion,
    IdentityResolver,
    RejectAllIdentityResolver,
)
from kanban.auth.oidc.config import OidcCardConfig
from kanban.auth.oidc.discovery import (
    ERR_RESPONSE_TOO_LARGE,
    JwksCache,
    OidcError,
    fetch_discovery,
)
from kanban.auth.oidc.tokens import build_private_key_jwt, validate_id_token
from kanban.auth.sessions.cookies import build_set_cookie_header
from kanban.auth.sessions.csrf import build_set_csrf_cookie_header
from kanban.security.envelope import SealedSecret, StaticKekProvider, open_card_secret
from kanban.security.keys import derive_subkey

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession

    from kanban.auth.sessions.service import SessionService
    from kanban.security.keys import KeyMaterial

logger = logging.getLogger(__name__)

RETURN_TO_REGEX: Final[re.Pattern[str]] = re.compile(r"^/(?![/\\])[A-Za-z0-9/_.\-?=&%:+~]{0,2048}$")

BROWSER_BINDING_COOKIE_NAME: Final[str] = "__Host-kb_oidc"
BROWSER_BINDING_TTL_SECONDS: Final[int] = 300
MAX_TOKEN_RESPONSE_BYTES: Final[int] = 65536  # 64 KiB


def sanitize_return_to(return_to: str | None) -> str:
    """Validate and sanitize redirect return_to target against open-redirect vectors."""
    if not return_to:
        return "/"

    # Invariant: Must match regex, starting with single '/' and no immediate slash or backslash
    if not RETURN_TO_REGEX.match(return_to):
        return "/"

    path_part, _, _query_part = return_to.partition("?")
    unquoted_path = urllib.parse.unquote(path_part)
    if not unquoted_path.startswith("/") or unquoted_path.startswith(("//", "/\\")):
        return "/"

    if "\\" in unquoted_path or ":" in unquoted_path:
        return "/"

    # Invariant: Unquoted full target must not contain backslashes
    unquoted = urllib.parse.unquote(return_to)
    if "\\" in unquoted:
        return "/"

    return return_to


def build_browser_binding_cookie(
    cookie_val: str, max_age: int = BROWSER_BINDING_TTL_SECONDS
) -> str:
    """Construct Set-Cookie header for __Host-kb_oidc browser-binding cookie."""
    return (
        f"{BROWSER_BINDING_COOKIE_NAME}={cookie_val}; "
        f"Path=/; Max-Age={max_age}; HttpOnly; SameSite=Lax; Secure"
    )


def build_clear_browser_binding_cookie() -> str:
    """Construct Set-Cookie header to clear __Host-kb_oidc cookie."""
    return f"{BROWSER_BINDING_COOKIE_NAME}=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax; Secure"


class OidcStartResponse(RedirectResponse):
    """HTTP 302 redirect response initializing an OIDC/OAuth2 authentication flow."""

    def __init__(  # noqa: PLR0913
        self,
        url: str,
        *,
        state: str,
        nonce: str | None,
        code_challenge: str,
        browser_binding: str,
        cookie_header: str,
    ) -> None:
        """Initialize OidcStartResponse with redirect URL and browser-binding cookies."""
        super().__init__(url=url, status_code=302)
        self.state = state
        self.nonce = nonce
        self.code_challenge = code_challenge
        self.browser_binding = browser_binding
        self.headers["Set-Cookie"] = cookie_header
        self.headers["Location"] = url


class OidcFlow:
    """Orchestrates authorization-code flow with PKCE S256 for OIDC and OAuth2 cards."""

    def __init__(  # noqa: PLR0913, PLR0917
        self,
        key_material: KeyMaterial,
        jwks_cache: JwksCache | None = None,
        identity_resolver: IdentityResolver | None = None,
        session_service: SessionService | None = None,
        http_client: httpx.AsyncClient | None = None,
        public_origin: str | None = None,
    ) -> None:
        """Initialize OidcFlow orchestrator."""
        self._key_material = key_material
        self._jwks_cache = jwks_cache or JwksCache()
        self._identity_resolver = identity_resolver or RejectAllIdentityResolver()
        self._session_service = session_service
        self._http_client = http_client
        self._public_origin = (
            public_origin or os.environ.get("KANBAN_PUBLIC_ORIGIN", "http://localhost:8000")
        ).rstrip("/")

    @property
    def key_material(self) -> KeyMaterial:
        """Return key material provider."""
        return self._key_material

    @property
    def jwks_cache(self) -> JwksCache:
        """Return rate-limited JWKS cache."""
        return self._jwks_cache

    @property
    def identity_resolver(self) -> IdentityResolver:
        """Return identity resolver."""
        return self._identity_resolver

    @property
    def session_service(self) -> SessionService | None:
        """Return session service if configured."""
        return self._session_service

    @property
    def public_origin(self) -> str:
        """Return canonical public origin for callback redirects."""
        return self._public_origin

    def _resolve_public_origin(self, request: Request | None = None) -> str:
        """Derive scheme/host from KANBAN_PUBLIC_ORIGIN, headers, or request.base_url."""
        env_origin = os.environ.get("KANBAN_PUBLIC_ORIGIN", "").strip()
        if env_origin:
            return env_origin.rstrip("/")

        if request is not None:
            proto = request.headers.get("x-forwarded-proto")
            host = request.headers.get("x-forwarded-host") or request.headers.get("host")
            if proto and host:
                return f"{proto}://{host}".rstrip("/")
            if host:
                scheme = (
                    request.url.scheme if hasattr(request, "url") and request.url.scheme else "http"
                )
                return f"{scheme}://{host}".rstrip("/")
            if hasattr(request, "base_url"):
                return str(request.base_url).rstrip("/")

        return self._public_origin

    async def start(  # noqa: PLR0913
        self,
        session: AsyncSession,
        slug: str,
        *,
        return_to: str | None = None,
        link_intent_id: uuid.UUID | None = None,
        request: Request | None = None,
        ttl_seconds: int = BROWSER_BINDING_TTL_SECONDS,
    ) -> OidcStartResponse:
        """Initialize authorization-code flow with PKCE S256 and browser-bound state."""
        card = await get_for_login(session, slug)
        if card is None or card.provider_kind not in ("OIDC", "OAUTH2"):
            raise ProblemException(
                code="AUTH_PROVIDER_NOT_FOUND",
                status=404,
                title="Auth Provider Not Found",
                detail=f"Provider card '{slug}' not found or disabled",
            )

        config = OidcCardConfig.model_validate(card.public_config or {})
        sanitized_return_to = sanitize_return_to(return_to)

        # Generate cryptographic single-use entropy
        state_bytes = secrets.token_bytes(16)
        nonce_bytes = secrets.token_bytes(16)
        code_verifier = secrets.token_urlsafe(32)

        # PKCE S256 code challenge
        verifier_hash = hashlib.sha256(code_verifier.encode("ascii")).digest()
        code_challenge = base64.urlsafe_b64encode(verifier_hash).rstrip(b"=").decode("ascii")

        # Browser binding cookie
        browser_binding = secrets.token_bytes(32)
        browser_binding_cookie_val = (
            base64.urlsafe_b64encode(browser_binding).rstrip(b"=").decode("ascii")
        )
        browser_binding_hash = hashlib.sha256(browser_binding).digest()

        # Database state hashes
        state_hash = hashlib.sha256(state_bytes).digest()
        state_str = base64.urlsafe_b64encode(state_bytes).rstrip(b"=").decode("ascii")
        nonce_str = base64.urlsafe_b64encode(nonce_bytes).rstrip(b"=").decode("ascii")

        # Seal code_verifier using AES-256-GCM subkey bound to card_id
        sub_key = derive_subkey(self._key_material.master_kek, "oidc/code-verifier")
        aes_nonce = os.urandom(12)
        code_verifier_ct = AESGCM(sub_key).encrypt(
            aes_nonce, code_verifier.encode("utf-8"), card.id.bytes
        )
        code_verifier_sealed = aes_nonce + code_verifier_ct

        expires_at = datetime.now(UTC) + timedelta(seconds=ttl_seconds)

        # Store auth request atomically in database
        stmt = text(
            "SELECT kb_auth.oidc_request_create("
            "    :p_card_id, "
            "    :p_state_hash, "
            "    :p_nonce, "
            "    :p_code_verifier_sealed, "
            "    :p_browser_binding_hash, "
            "    :p_return_to, "
            "    :p_link_intent_id, "
            "    :p_expires_at"
            ")"
        )
        await session.execute(
            stmt,
            {
                "p_card_id": card.id,
                "p_state_hash": state_hash,
                "p_nonce": nonce_bytes,
                "p_code_verifier_sealed": code_verifier_sealed,
                "p_browser_binding_hash": browser_binding_hash,
                "p_return_to": sanitized_return_to,
                "p_link_intent_id": link_intent_id,
                "p_expires_at": expires_at,
            },
        )
        await session.commit()

        # Resolve authorization endpoint
        if config.kind == "OIDC":
            discovery = await fetch_discovery(str(config.issuer), client=self._http_client)
            auth_endpoint = discovery.authorization_endpoint
        else:
            auth_endpoint = str(config.authorization_endpoint)

        public_origin = self._resolve_public_origin(request)
        redirect_uri = f"{public_origin}/api/v1/auth/oidc/{slug}/callback"

        query_params: dict[str, str] = {
            "response_type": "code",
            "client_id": config.client_id,
            "redirect_uri": redirect_uri,
            "scope": " ".join(config.scopes),
            "state": state_str,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }
        if config.kind == "OIDC":
            query_params["nonce"] = nonce_str

        encoded_params = urllib.parse.urlencode(query_params)
        delimiter = "&" if "?" in auth_endpoint else "?"
        authorization_url = f"{auth_endpoint}{delimiter}{encoded_params}"

        cookie_header = build_browser_binding_cookie(browser_binding_cookie_val)
        return OidcStartResponse(
            url=authorization_url,
            state=state_str,
            nonce=nonce_str if config.kind == "OIDC" else None,
            code_challenge=code_challenge,
            browser_binding=browser_binding_cookie_val,
            cookie_header=cookie_header,
        )

    async def callback(  # noqa: C901, PLR0912, PLR0913, PLR0915
        self,
        session: AsyncSession,
        slug: str,
        *,
        code: str | None = None,
        state: str | None = None,
        error: str | None = None,
        error_description: str | None = None,
        browser_binding_cookie: str | None = None,
        request: Request | None = None,
        link_intent_id: uuid.UUID | None = None,
    ) -> Response:
        """Handle IdP callback, validate single-use state/nonce, and resolve identity."""
        del error_description  # Strictly never echoed in responses or logs

        if error:
            raise ProblemException(
                code="OIDC_PROVIDER_ERROR",
                status=400,
                title="IdP Provider Error",
                detail="Authentication was rejected by the external identity provider",
            )

        if not code or not state:
            raise ProblemException(
                code="OIDC_STATE_INVALID",
                status=400,
                title="Invalid State",
                detail="Missing authorization code or state parameter",
            )

        if not browser_binding_cookie:
            raise ProblemException(
                code="OIDC_STATE_INVALID",
                status=400,
                title="Invalid State",
                detail="Missing browser binding cookie",
            )

        try:
            state_padding = "=" * (-len(state) % 4)
            state_bytes = base64.urlsafe_b64decode(state + state_padding)
        except Exception as err:
            raise ProblemException(
                code="OIDC_STATE_INVALID",
                status=400,
                title="Invalid State",
                detail="Malformed state parameter",
            ) from err

        try:
            cookie_padding = "=" * (-len(browser_binding_cookie) % 4)
            binding_bytes = base64.urlsafe_b64decode(browser_binding_cookie + cookie_padding)
        except Exception as err:
            raise ProblemException(
                code="OIDC_STATE_INVALID",
                status=400,
                title="Invalid State",
                detail="Malformed browser binding cookie",
            ) from err

        state_hash = hashlib.sha256(state_bytes).digest()
        binding_hash = hashlib.sha256(binding_bytes).digest()

        # Atomically consume auth request row
        stmt = text(
            "SELECT id, card_id, nonce, code_verifier_sealed, return_to, link_intent_id, status "
            "FROM kb_auth.oidc_request_consume(:p_state_hash, :p_browser_binding_hash)"
        )
        res = await session.execute(
            stmt,
            {
                "p_state_hash": state_hash,
                "p_browser_binding_hash": binding_hash,
            },
        )
        row = res.mappings().first()
        await session.commit()

        if not row or row["status"] != "OK":
            raise ProblemException(
                code="OIDC_STATE_INVALID",
                status=400,
                title="Invalid State",
                detail="State parameter is invalid, expired, or already consumed",
            )

        req_card_id: uuid.UUID = row["card_id"]
        nonce_bytes: bytes = bytes(row["nonce"])
        code_verifier_sealed: bytes = bytes(row["code_verifier_sealed"])
        return_to: str = str(row["return_to"])
        resolved_link_intent_id: uuid.UUID | None = row["link_intent_id"] or link_intent_id

        # Unseal code_verifier
        sub_key = derive_subkey(self._key_material.master_kek, "oidc/code-verifier")
        min_sealed_length = 12 + 16
        if len(code_verifier_sealed) < min_sealed_length:
            raise ProblemException(
                code="OIDC_STATE_INVALID",
                status=400,
                title="Invalid State",
                detail="Corrupt sealed code verifier",
            )

        aes_nonce = code_verifier_sealed[:12]
        ct = code_verifier_sealed[12:]
        try:
            code_verifier = (
                AESGCM(sub_key).decrypt(aes_nonce, ct, req_card_id.bytes).decode("utf-8")
            )
        except Exception as err:
            raise ProblemException(
                code="OIDC_STATE_INVALID",
                status=400,
                title="Invalid State",
                detail="Failed to decrypt code verifier",
            ) from err

        # Load card
        card = await get_for_login(session, slug)
        if card is None or card.id != req_card_id:
            raise ProblemException(
                code="AUTH_PROVIDER_NOT_FOUND",
                status=404,
                title="Auth Provider Not Found",
                detail=f"Provider card '{slug}' not found or mismatched",
            )

        config = OidcCardConfig.model_validate(card.public_config or {})

        # Open secret if present
        card_secret_str: str | None = None
        if card.encrypted_secret_blob and card.wrapped_dek:
            sealed = SealedSecret(
                encrypted_secret_blob=card.encrypted_secret_blob,
                wrapped_dek=card.wrapped_dek,
                dek_kid=card.dek_kid or "kek-v1",
            )
            kek_provider = StaticKekProvider.from_key_material(self._key_material)
            secret_bytes = open_card_secret(card.id, card.provider_kind, sealed, kek_provider)
            try:
                card_secret_str = secret_bytes.decode("utf-8")
            finally:
                for idx in range(len(secret_bytes)):
                    secret_bytes[idx] = 0

        # Resolve endpoints
        if config.kind == "OIDC":
            discovery = await fetch_discovery(str(config.issuer), client=self._http_client)
            token_endpoint = discovery.token_endpoint
            jwks_uri = discovery.jwks_uri
            issuer_pinned = discovery.issuer
            userinfo_endpoint = discovery.userinfo_endpoint or config.userinfo_endpoint
        else:
            token_endpoint = str(config.token_endpoint)
            jwks_uri = None
            issuer_pinned = None
            userinfo_endpoint = str(config.userinfo_endpoint)

        public_origin = self._resolve_public_origin(request)
        redirect_uri = f"{public_origin}/api/v1/auth/oidc/{slug}/callback"

        # Exchange authorization code for token
        token_payload: dict[str, str] = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "code_verifier": code_verifier,
        }
        token_headers: dict[str, str] = {
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
        }

        if config.client_auth == "client_secret_basic":
            if not card_secret_str:
                raise ProblemException(
                    code="OIDC_TOKEN_INVALID",
                    status=401,
                    title="Authentication Failed",
                    detail="Missing client secret for basic authentication",
                )
            basic_creds = f"{config.client_id}:{card_secret_str}".encode()
            b64_creds = base64.b64encode(basic_creds).decode("ascii")
            token_headers["Authorization"] = f"Basic {b64_creds}"
        elif config.client_auth == "private_key_jwt":
            if not card_secret_str:
                raise ProblemException(
                    code="OIDC_TOKEN_INVALID",
                    status=401,
                    title="Authentication Failed",
                    detail="Missing private key for client assertion",
                )
            client_jwt = build_private_key_jwt(config.client_id, token_endpoint, card_secret_str)
            token_payload["client_assertion_type"] = (
                "urn:ietf:params:oauth:client-assertion-type:jwt-bearer"
            )
            token_payload["client_assertion"] = client_jwt

        # POST to token endpoint
        async def _do_token_post(c: httpx.AsyncClient) -> httpx.Response:
            return await c.post(
                token_endpoint,
                data=token_payload,
                headers=token_headers,
                timeout=httpx.Timeout(5.0),
            )

        if self._http_client is not None:
            token_resp = await _do_token_post(self._http_client)
        else:
            async with httpx.AsyncClient(follow_redirects=False) as default_client:
                token_resp = await _do_token_post(default_client)

        if len(token_resp.content) > MAX_TOKEN_RESPONSE_BYTES:
            raise OidcError(
                ERR_RESPONSE_TOO_LARGE,
                f"Token response exceeded {MAX_TOKEN_RESPONSE_BYTES} bytes",
            )

        if token_resp.status_code != HTTPStatus.OK:
            idp_err = ""
            with contextlib.suppress(Exception):
                err_json = token_resp.json()
                if isinstance(err_json, dict) and err_json.get("error"):
                    idp_err = f" ({err_json['error']})"
            logger.warning(
                "OIDC token exchange failed on card '%s': HTTP %d%s (redirect_uri=%s)",
                slug,
                token_resp.status_code,
                idp_err,
                redirect_uri,
            )
            raise ProblemException(
                code="OIDC_TOKEN_INVALID",
                status=401,
                title="Token Exchange Failed",
                detail=(
                    f"Token endpoint returned non-200 status code "
                    f"(HTTP {token_resp.status_code}{idp_err})"
                ),
            )

        try:
            token_data = token_resp.json()
        except Exception as err:
            raise ProblemException(
                code="OIDC_TOKEN_INVALID",
                status=401,
                title="Token Exchange Failed",
                detail="Token endpoint returned malformed JSON",
            ) from err

        # Process token claims or userinfo
        if config.kind == "OIDC":
            raw_id_token = token_data.get("id_token")
            if not raw_id_token or not isinstance(raw_id_token, str):
                raise ProblemException(
                    code="OIDC_TOKEN_INVALID",
                    status=401,
                    title="Invalid ID Token",
                    detail="Token response missing id_token",
                )
            if not jwks_uri or not issuer_pinned:
                raise ProblemException(
                    code="OIDC_TOKEN_INVALID",
                    status=401,
                    title="Invalid ID Token",
                    detail="Missing JWKS URI or issuer in discovery",
                )

            jwks = await self._jwks_cache.get_keyset(card.id, jwks_uri, client=self._http_client)
            claims = validate_id_token(
                raw_id_token,
                jwks,
                issuer=issuer_pinned,
                client_id=config.client_id,
                expected_nonce=nonce_bytes,
                allowed_algs=config.allowed_algs,
            )

            raw_sub = claims.get(config.subject_claim, claims.get("sub"))
            if raw_sub is None or len(str(raw_sub)) == 0 or len(str(raw_sub)) > MAX_SUBJECT_LENGTH:
                raise ProblemException(
                    code="OIDC_TOKEN_INVALID",
                    status=401,
                    title="Invalid Subject",
                    detail=f"Subject claim is missing or exceeds {MAX_SUBJECT_LENGTH} characters",
                )
            subject = str(raw_sub)
            email_val = claims.get(config.email_claim)
            email = str(email_val) if email_val is not None else None
            email_verified = bool(claims.get(config.email_verified_claim, False))
            name_val = claims.get("name") or claims.get("preferred_username")
            display_name = str(name_val) if name_val is not None else None
            groups_val = claims.get(config.groups_claim) if config.groups_claim else ()
            groups = (
                tuple(str(g) for g in groups_val) if isinstance(groups_val, (list, tuple)) else ()
            )
        else:
            # OAuth2 flow
            access_token = token_data.get("access_token")
            if not access_token or not isinstance(access_token, str):
                raise ProblemException(
                    code="OIDC_TOKEN_INVALID",
                    status=401,
                    title="Missing Access Token",
                    detail="Token response missing access_token",
                )
            if not userinfo_endpoint:
                raise ProblemException(
                    code="OIDC_TOKEN_INVALID",
                    status=401,
                    title="Missing Userinfo Endpoint",
                    detail="OAuth2 card requires userinfo_endpoint",
                )

            async def _do_userinfo_get(c: httpx.AsyncClient) -> httpx.Response:
                return await c.get(
                    userinfo_endpoint,
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Accept": "application/json",
                    },
                    timeout=httpx.Timeout(5.0),
                )

            if self._http_client is not None:
                userinfo_resp = await _do_userinfo_get(self._http_client)
            else:
                async with httpx.AsyncClient(follow_redirects=False) as default_client:
                    userinfo_resp = await _do_userinfo_get(default_client)

            if len(userinfo_resp.content) > MAX_TOKEN_RESPONSE_BYTES:
                raise OidcError(
                    ERR_RESPONSE_TOO_LARGE,
                    f"Userinfo response exceeded {MAX_TOKEN_RESPONSE_BYTES} bytes",
                )

            if userinfo_resp.status_code != HTTPStatus.OK:
                logger.warning(
                    "OAuth2 userinfo request failed on card '%s': HTTP %d",
                    slug,
                    userinfo_resp.status_code,
                )
                raise ProblemException(
                    code="OIDC_TOKEN_INVALID",
                    status=401,
                    title="Userinfo Failed",
                    detail=(
                        f"Userinfo endpoint returned non-200 status code "
                        f"(HTTP {userinfo_resp.status_code})"
                    ),
                )

            try:
                userinfo = userinfo_resp.json()
            except Exception as err:
                raise ProblemException(
                    code="OIDC_TOKEN_INVALID",
                    status=401,
                    title="Userinfo Failed",
                    detail="Userinfo endpoint returned malformed JSON",
                ) from err

            raw_sub = userinfo.get(config.subject_claim)
            if raw_sub is None and "id" in userinfo:
                raw_sub = userinfo["id"]
            if raw_sub is None or len(str(raw_sub)) == 0 or len(str(raw_sub)) > MAX_SUBJECT_LENGTH:
                raise ProblemException(
                    code="OIDC_TOKEN_INVALID",
                    status=401,
                    title="Invalid Subject",
                    detail=f"Subject claim is missing or exceeds {MAX_SUBJECT_LENGTH} characters",
                )
            subject = str(raw_sub)
            email_val = userinfo.get(config.email_claim)
            email = str(email_val) if email_val is not None else None
            email_verified = bool(userinfo.get(config.email_verified_claim, False))

            # GitHub email handling: fetch /user/emails or fallback {login}@users.noreply.github.com
            if not email and userinfo_endpoint and "api.github.com" in userinfo_endpoint:
                emails_url = "https://api.github.com/user/emails"

                async def _do_emails_get(c: httpx.AsyncClient) -> httpx.Response:
                    return await c.get(
                        emails_url,
                        headers={
                            "Authorization": f"Bearer {access_token}",
                            "Accept": "application/json",
                        },
                        timeout=httpx.Timeout(5.0),
                    )

                try:
                    if self._http_client is not None:
                        emails_resp = await _do_emails_get(self._http_client)
                    else:
                        async with httpx.AsyncClient(follow_redirects=False) as default_client:
                            emails_resp = await _do_emails_get(default_client)

                    if emails_resp.status_code == HTTPStatus.OK:
                        emails_data = emails_resp.json()
                        if isinstance(emails_data, list):
                            for em_item in emails_data:
                                if (
                                    isinstance(em_item, dict)
                                    and em_item.get("primary")
                                    and em_item.get("verified")
                                ):
                                    email = str(em_item.get("email"))
                                    break
                            if (
                                not email
                                and len(emails_data) > 0
                                and isinstance(emails_data[0], dict)
                            ):
                                email = str(emails_data[0].get("email"))
                except Exception:
                    logger.debug(
                        "Failed to retrieve emails from GitHub /user/emails", exc_info=True
                    )

                if not email:
                    login_name = userinfo.get("login") or "user"
                    email = f"{login_name}@users.noreply.github.com"
                email_verified = True

            name_val = userinfo.get("name") or userinfo.get("login")
            display_name = str(name_val) if name_val is not None else None
            groups_val = userinfo.get(config.groups_claim) if config.groups_claim else ()
            groups = (
                tuple(str(g) for g in groups_val) if isinstance(groups_val, (list, tuple)) else ()
            )

        assertion = ExternalIdentityAssertion(
            card_id=card.id,
            subject=subject,
            email=email,
            email_verified=email_verified,
            display_name=display_name,
            groups=groups,
        )

        dummy_req = request
        if dummy_req is None:
            dummy_req = Request(
                {
                    "type": "http",
                    "method": "GET",
                    "path": redirect_uri,
                    "headers": [],
                }
            )

        resolved_login = await self._identity_resolver.resolve(
            assertion, dummy_req, resolved_link_intent_id
        )

        # Clear the browser binding cookie on the response
        clear_cookie_hdr = build_clear_browser_binding_cookie()
        response = RedirectResponse(url=return_to, status_code=302)
        response.headers.append("Set-Cookie", clear_cookie_hdr)

        # If SessionService is configured, issue session & CSRF cookies
        if self._session_service is not None:
            issued_session = await self._session_service.create_after_login(
                session,
                principal_id=resolved_login.principal_id,
                workspace_id=resolved_login.workspace_id,
                auth_card_id=card.id,
                aal_level=2,
                mfa_pending=False,
            )
            response.headers.append(
                "Set-Cookie",
                build_set_cookie_header(issued_session.cookie_val, issued_session.idle_expires_at),
            )
            response.headers.append(
                "Set-Cookie",
                build_set_csrf_cookie_header(issued_session.csrf_token),
            )

        return response
