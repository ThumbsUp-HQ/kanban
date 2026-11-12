# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""LDAP authentication service orchestrating search, ephemeral bind, and sync (KB-P2-07)."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import TYPE_CHECKING, Final, NoReturn

from sqlalchemy import select
from starlette.requests import Request as StarletteRequest

from database.models.auth import LdapGroupMapping
from kanban.api.problems import ProblemException
from kanban.auth.identity import ExternalIdentityAssertion
from kanban.auth.ldap.client import (
    DEFAULT_TOTAL_TIMEOUT,
    LdapBindError,
    LdapProtocolError,
    LdapSearchError,
    LdapTlsHardClient,
)
from kanban.auth.ldap.config import LdapCardConfig
from kanban.auth.ldap.escape import normalize_dn, render_user_filter
from kanban.auth.ldap.sync import sync_ldap_groups
from kanban.security.envelope import SealedSecret, open_card_secret

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
    from starlette.requests import Request

    from database.models.auth import AuthProviderCard
    from kanban.auth.identity import IdentityResolver, ResolvedLogin
    from kanban.security.envelope import KekProvider

logger = logging.getLogger(__name__)

UUID_BYTES_LEN: Final[int] = 16
MAX_SUBJECT_LEN: Final[int] = 255


def _raise_invalid_credentials() -> NoReturn:
    """Raise uniform 401 INVALID_CREDENTIALS error preventing user enumeration."""
    raise ProblemException(
        code="INVALID_CREDENTIALS",
        status=401,
        title="Authentication Failed",
        detail="Invalid credentials",
    )


def _format_subject_value(raw_bytes: bytes) -> str:
    """Format subject attribute value, converting 16-byte binary GUIDs to UUID strings."""
    if len(raw_bytes) == UUID_BYTES_LEN:
        try:
            return str(uuid.UUID(bytes_le=raw_bytes))
        except ValueError:
            pass
    decoded = raw_bytes.decode("utf-8", errors="replace").strip()
    return decoded[:MAX_SUBJECT_LEN]


class LdapAuthService:
    """Orchestrates LDAP search, ephemeral bind password verification, and group sync."""

    def __init__(
        self,
        kek_provider: KekProvider | None = None,
        identity_resolver: IdentityResolver | None = None,
        unix_socket_path: str | None = None,
    ) -> None:
        """Initialize authentication service."""
        self._kek_provider = kek_provider
        self._identity_resolver = identity_resolver
        self._unix_socket_path = unix_socket_path

    async def authenticate(  # noqa: C901, PLR0912, PLR0913, PLR0915, PLR0917
        self,
        session: AsyncSession,
        card: AuthProviderCard,
        username: str,
        password: str,
        request: Request | None = None,
        link_intent_id: uuid.UUID | None = None,
    ) -> tuple[ExternalIdentityAssertion, ResolvedLogin | None]:
        """Authenticate user against LDAP card.

        Zeroizes password buffers in finally blocks, prevents anonymous bind,
        enforces TLS_HARD and SPKI pinning, and synchronizes mapped groups.
        """
        # 1. Enforce password non-emptiness before opening any network socket
        if not password or not password.strip():
            _raise_invalid_credentials()

        clean_username = username.strip()
        if not clean_username:
            _raise_invalid_credentials()

        # 2. Verify card eligibility
        if not card.is_enabled or card.provider_kind != "LDAP":
            _raise_invalid_credentials()

        config = LdapCardConfig(**card.public_config)

        # 3. Create mutable user password bytearray (exact UTF-8 bytes, no normalization)
        pwd_bytes = password.encode("utf-8")
        user_pwd_buf = bytearray(pwd_bytes)
        del pwd_bytes

        # Fetch extra mappings from database if any
        group_dn_map = dict(config.group_dn_map)
        mapping_stmt = select(LdapGroupMapping).where(LdapGroupMapping.card_id == card.id)
        mapping_res = await session.execute(mapping_stmt)
        for row in mapping_res.scalars().all():
            group_dn_map[row.ldap_dn] = row.group_name

        try:
            async with asyncio.timeout(DEFAULT_TOTAL_TIMEOUT):
                # Step 1: Search Directory
                search_client = LdapTlsHardClient(config, unix_socket_path=self._unix_socket_path)
                await search_client.connect()
                try:
                    # Service bind if configured
                    if config.service_bind_dn:
                        if (
                            card.encrypted_secret_blob is None
                            or card.wrapped_dek is None
                            or self._kek_provider is None
                        ):
                            _raise_invalid_credentials()

                        sealed = SealedSecret(
                            encrypted_secret_blob=card.encrypted_secret_blob,
                            wrapped_dek=card.wrapped_dek,
                            dek_kid=card.dek_kid,
                        )
                        secret_buf = open_card_secret(
                            card.id,
                            card.provider_kind,
                            sealed,
                            self._kek_provider,
                        )
                        bind_pwd_buf: bytearray | None = None
                        try:
                            try:
                                secret_data = json.loads(secret_buf.decode("utf-8"))
                                pwd_str = str(secret_data.get("bind_dn_password", ""))
                            except (json.JSONDecodeError, UnicodeDecodeError):
                                pwd_str = secret_buf.decode("utf-8", errors="replace")
                            bind_pwd_buf = bytearray(pwd_str.encode("utf-8"))
                            del pwd_str
                            await search_client.bind(config.service_bind_dn, bind_pwd_buf)
                        finally:
                            if bind_pwd_buf is not None:
                                for idx in range(len(bind_pwd_buf)):
                                    bind_pwd_buf[idx] = 0
                            for idx in range(len(secret_buf)):
                                secret_buf[idx] = 0

                    # Render filter assertion with AST structural invariance check
                    filter_str = render_user_filter(config.user_search_filter, clean_username)
                    requested_attrs = [
                        config.subject_attribute,
                        config.email_attribute,
                        config.display_name_attribute,
                        config.member_of_attribute,
                    ]

                    entries = await search_client.search(
                        config.base_dn,
                        filter_str,
                        requested_attrs,
                        size_limit=2,
                        time_limit=int(config.timeout_seconds),
                    )

                    if len(entries) != 1:
                        logger.debug(
                            "LDAP search returned %d entries for filter assertion", len(entries)
                        )
                        _raise_invalid_credentials()

                    user_entry = entries[0]
                    user_dn = user_entry.dn
                    attrs = user_entry.attributes

                finally:
                    await search_client.unbind()

                # Extract entry attributes
                subject_bytes = attrs.get(config.subject_attribute.lower(), [b""])[0]
                if not subject_bytes:
                    _raise_invalid_credentials()
                subject = _format_subject_value(subject_bytes)

                email_bytes = attrs.get(config.email_attribute.lower(), [b""])[0]
                email = (
                    email_bytes.decode("utf-8", errors="replace").strip() if email_bytes else None
                )

                name_bytes = attrs.get(config.display_name_attribute.lower(), [b""])[0]
                display_name = (
                    name_bytes.decode("utf-8", errors="replace").strip() if name_bytes else None
                )

                member_of_dns = [
                    v.decode("utf-8", errors="replace")
                    for v in attrs.get(config.member_of_attribute.lower(), [])
                ]

                # Step 2: Ephemeral User Bind
                user_client = LdapTlsHardClient(config, unix_socket_path=self._unix_socket_path)
                await user_client.connect()
                try:
                    await user_client.bind(user_dn, user_pwd_buf)
                except (LdapBindError, LdapProtocolError):
                    logger.debug("LDAP ephemeral user bind failed for DN: %s", user_dn)
                    _raise_invalid_credentials()
                finally:
                    await user_client.unbind()

                # Step 3: Compute mapped group names
                canonical_map = {
                    normalize_dn(k): v.strip() for k, v in group_dn_map.items() if k.strip()
                }
                user_norm_dns = {normalize_dn(d) for d in member_of_dns if d.strip()}
                matched_group_names = sorted(
                    {canonical_map[d] for d in user_norm_dns if d in canonical_map}
                )

                # Step 4: Construct ExternalIdentityAssertion
                assertion = ExternalIdentityAssertion(
                    card_id=card.id,
                    subject=subject,
                    email=email,
                    email_verified=True,
                    display_name=display_name,
                    groups=tuple(matched_group_names),
                )

                # Step 5: Resolve principal via IdentityResolver
                resolved_login: ResolvedLogin | None = None
                if self._identity_resolver is not None:
                    effective_request = request or StarletteRequest(
                        scope={"type": "http", "headers": [], "client": ("127.0.0.1", 12345)}
                    )
                    resolved_login = await self._identity_resolver.resolve(
                        assertion, effective_request, link_intent_id
                    )
                    # Synchronize group memberships in DB
                    if card.workspace_id is not None:
                        await sync_ldap_groups(
                            session,
                            card.workspace_id,
                            resolved_login.principal_id,
                            member_of_dns,
                            group_dn_map,
                        )

                return assertion, resolved_login

        except (LdapBindError, LdapProtocolError, LdapSearchError, TimeoutError) as exc:
            logger.debug("LDAP authentication failed for card '%s': %s", card.slug, exc)
            _raise_invalid_credentials()

        finally:
            # Wipe user password buffer in mutable memory
            for idx in range(len(user_pwd_buf)):
                user_pwd_buf[idx] = 0
