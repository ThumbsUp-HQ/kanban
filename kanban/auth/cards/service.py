# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Administrative service coordinating Auth Provider Cards lifecycle and security (KB-P2-10)."""

from __future__ import annotations

import json
import logging
import uuid
from typing import TYPE_CHECKING, Final

from sqlalchemy import text

from database.models.auth import AuthProviderCard
from kanban.api.problems import ProblemException
from kanban.auth.cards.handshake import probe_auth_card_handshake
from kanban.auth.cards.lockout import (
    LockoutPreventedError,
    assert_local_admin_disable_allowed,
    extract_lockout_layer,
)
from kanban.auth.cards.repository import admin_get, admin_list, admin_upsert, to_admin_schema
from kanban.auth.ldap.config import LdapCardConfig
from kanban.auth.oidc.config import OidcCardConfig
from kanban.security.envelope import KekProvider, seal_card_secret
from kanban.services.activity import ActivityEventType, record_activity
from kanban.util.fractional_rank import midpoint_rank, needs_rebalance, rebalance_ranks

if TYPE_CHECKING:
    import httpx
    from sqlalchemy.ext.asyncio import AsyncSession

    from kanban.auth.cards.schemas import (
        AuthCardAdmin,
        AuthCardCreate,
        AuthCardUpdate,
        HandshakeProbeResult,
    )

logger = logging.getLogger(__name__)

MAX_ALLOWED_EMAIL_DOMAINS: Final[int] = 50


def _is_valid_uuid(val: str) -> bool:
    try:
        uuid.UUID(val)
    except (ValueError, TypeError):
        return False
    else:
        return True


class AuthCardAdminService:
    """Service managing authentication cards, credentials, reordering, and diagnostics."""

    def __init__(
        self,
        *,
        kek_provider: KekProvider | None = None,
        http_client: httpx.AsyncClient | None = None,
        ldap_unix_socket_path: str | None = None,
    ) -> None:
        """Initialize AuthCardAdminService with optional KEK provider, HTTP client, and LDAP."""
        self._kek_provider = kek_provider
        self._http_client = http_client
        self._ldap_unix_socket_path = ldap_unix_socket_path

    async def list_cards(self, session: AsyncSession) -> list[AuthCardAdmin]:
        """List all authentication cards in the system ordered by sort_rank COLLATE 'C'."""
        cards = await admin_list(session)
        return [to_admin_schema(c) for c in cards]

    async def get_card(
        self,
        session: AsyncSession,
        card_ref: str | uuid.UUID,
    ) -> AuthCardAdmin:
        """Retrieve a specific card by slug or UUID."""
        card = await self._resolve_card(session, card_ref)
        if card is None:
            raise ProblemException(
                code="NOT_FOUND",
                status=404,
                title="Card Not Found",
                detail=f"Authentication provider card '{card_ref}' not found.",
            )
        return to_admin_schema(card)

    async def _resolve_card(
        self,
        session: AsyncSession,
        card_ref: str | uuid.UUID,
    ) -> AuthProviderCard | None:
        """Resolve an AuthProviderCard by UUID or unique slug."""
        if isinstance(card_ref, uuid.UUID):
            return await admin_get(session, card_ref)

        ref_str = str(card_ref).strip()
        if _is_valid_uuid(ref_str):
            card = await admin_get(session, uuid.UUID(ref_str))
            if card is not None:
                return card

        stmt = text("SELECT * FROM auth_provider_cards WHERE slug = :slug")
        result = await session.execute(stmt, {"slug": ref_str})
        row = result.mappings().first()
        if row is not None:
            return AuthProviderCard(**dict(row))
        return None

    async def create_card(  # noqa: C901, PLR0912, PLR0915
        self,
        session: AsyncSession,
        data: AuthCardCreate,
        actor_id: uuid.UUID,
        workspace_id: uuid.UUID | None = None,
    ) -> AuthCardAdmin:
        """Create a new authentication provider card with sealed secrets and activity record."""
        kind = data.provider_kind.upper()

        # Enforce max 1 LOCAL_ADMIN card per workspace
        if kind == "LOCAL_ADMIN":
            stmt = text(
                "SELECT 1 FROM auth_provider_cards "
                "WHERE (workspace_id IS NOT DISTINCT FROM :ws_id) "
                "  AND provider_kind = 'LOCAL_ADMIN'"
            )
            exists = (await session.execute(stmt, {"ws_id": workspace_id})).scalar_one_or_none()
            if exists:
                raise ProblemException(
                    code="LOCAL_ADMIN_CARD_EXISTS",
                    status=409,
                    title="Local Admin Card Exists",
                    detail="A LOCAL_ADMIN card already exists in this workspace.",
                )

        # Validate public_config according to kind
        public_config = dict(data.public_config)
        if kind in ("OIDC", "OAUTH2"):
            if "kind" not in public_config:
                public_config["kind"] = kind
            try:
                OidcCardConfig(**public_config)
            except Exception as exc:
                raise ProblemException(
                    code="INVALID_CARD_CONFIG",
                    status=422,
                    title="Invalid Card Configuration",
                    detail=f"Invalid OIDC/OAuth2 configuration: {exc}",
                ) from exc
        elif kind == "LDAP":
            try:
                LdapCardConfig(**public_config)
            except Exception as exc:
                raise ProblemException(
                    code="INVALID_CARD_CONFIG",
                    status=422,
                    title="Invalid Card Configuration",
                    detail=f"Invalid LDAP configuration: {exc}",
                ) from exc

        # Check allowed_email_domains bound
        if len(data.allowed_email_domains) > MAX_ALLOWED_EMAIL_DOMAINS:
            raise ProblemException(
                code="INVALID_EMAIL_DOMAINS",
                status=422,
                title="Invalid Email Domains",
                detail="Exceeds maximum limit of 50 allowed email domains.",
            )
        clean_domains = [d.strip().lower() for d in data.allowed_email_domains if d.strip()]

        # Generate unique card ID
        card_id = uuid.uuid4()

        # Determine sort_rank
        if data.sort_rank is None or not data.sort_rank.strip():
            existing = await admin_list(session)
            last_rank = existing[-1].sort_rank if existing else None
            sort_rank = midpoint_rank(last_rank, None)
        else:
            sort_rank = data.sort_rank

        # Seal secret if provided
        encrypted_blob: bytes | None = None
        wrapped_dek: bytes | None = None
        dek_kid: str = "kek-v1"

        if data.secret:
            if self._kek_provider is None:
                msg = "No KEK provider configured for secret sealing"
                raise RuntimeError(msg)

            secret_str = data.secret
            if kind == "LDAP" and not secret_str.strip().startswith("{"):
                secret_bytes = json.dumps({"bind_dn_password": secret_str}).encode("utf-8")
            else:
                secret_bytes = secret_str.encode("utf-8")

            secret_buf = bytearray(secret_bytes)
            try:
                sealed = seal_card_secret(
                    card_id,
                    kind,
                    bytes(secret_buf),
                    self._kek_provider,
                )
                encrypted_blob = sealed.encrypted_secret_blob
                wrapped_dek = sealed.wrapped_dek
                dek_kid = sealed.dek_kid
            finally:
                for i in range(len(secret_buf)):
                    secret_buf[i] = 0

        # Upsert card in database
        upserted_id = await admin_upsert(
            session,
            card_id=card_id,
            workspace_id=workspace_id,
            provider_kind=kind,
            slug=data.slug,
            display_name=data.display_name,
            button_subtext=data.button_subtext,
            icon_preset=data.icon_preset,
            is_enabled=data.is_enabled,
            sort_rank=sort_rank,
            auto_provision_users=data.auto_provision_users,
            allowed_email_domains=clean_domains,
            public_config=public_config,
            encrypted_secret_blob=encrypted_blob,
            wrapped_dek=wrapped_dek,
            dek_kid=dek_kid,
            last_health_status="UNVERIFIED",
        )

        # Record activity
        ws_target = workspace_id if workspace_id is not None else uuid.UUID(int=0)
        await record_activity(
            session,
            workspace_id=ws_target,
            actor_principal_id=actor_id,
            event_type=ActivityEventType.AUTH_CARD_CREATED,
            payload={
                "card_id": str(upserted_id),
                "slug": data.slug,
                "provider_kind": kind,
                "display_name": data.display_name,
            },
        )

        card = await admin_get(session, upserted_id)
        if card is None:
            raise ProblemException(
                code="NOT_FOUND",
                status=404,
                title="Card Not Found",
                detail="Created card could not be retrieved.",
            )
        return to_admin_schema(card)

    async def update_card(  # noqa: C901, PLR0912, PLR0915
        self,
        session: AsyncSession,
        card_ref: str | uuid.UUID,
        data: AuthCardUpdate,
        actor_id: uuid.UUID,
    ) -> AuthCardAdmin:
        """Update existing card metadata, configuration, or credentials."""
        card = await self._resolve_card(session, card_ref)
        if card is None:
            raise ProblemException(
                code="NOT_FOUND",
                status=404,
                title="Card Not Found",
                detail=f"Authentication provider card '{card_ref}' not found.",
            )

        kind = card.provider_kind.upper()
        display_name = data.display_name if data.display_name is not None else card.display_name
        button_subtext = (
            data.button_subtext if data.button_subtext is not None else card.button_subtext
        )
        icon_preset = data.icon_preset if data.icon_preset is not None else card.icon_preset
        auto_provision = (
            data.auto_provision_users
            if data.auto_provision_users is not None
            else card.auto_provision_users
        )

        # Email domains
        if data.allowed_email_domains is not None:
            if len(data.allowed_email_domains) > MAX_ALLOWED_EMAIL_DOMAINS:
                raise ProblemException(
                    code="INVALID_EMAIL_DOMAINS",
                    status=422,
                    title="Invalid Email Domains",
                    detail="Exceeds maximum limit of 50 allowed email domains.",
                )
            allowed_domains = [d.strip().lower() for d in data.allowed_email_domains if d.strip()]
        else:
            allowed_domains = list(card.allowed_email_domains or [])

        # Public config & health status
        config_changed = False
        if data.public_config is not None:
            config_changed = True
            public_config = dict(data.public_config)
            if kind in ("OIDC", "OAUTH2"):
                if "kind" not in public_config:
                    public_config["kind"] = kind
                try:
                    OidcCardConfig(**public_config)
                except Exception as exc:
                    raise ProblemException(
                        code="INVALID_CARD_CONFIG",
                        status=422,
                        title="Invalid Card Configuration",
                        detail=f"Invalid OIDC/OAuth2 configuration: {exc}",
                    ) from exc
            elif kind == "LDAP":
                try:
                    LdapCardConfig(**public_config)
                except Exception as exc:
                    raise ProblemException(
                        code="INVALID_CARD_CONFIG",
                        status=422,
                        title="Invalid Card Configuration",
                        detail=f"Invalid LDAP configuration: {exc}",
                    ) from exc
        else:
            public_config = dict(card.public_config or {})

        # Secret replacement
        secret_changed = False
        encrypted_blob = card.encrypted_secret_blob
        wrapped_dek = card.wrapped_dek
        dek_kid = card.dek_kid

        if data.secret:
            secret_changed = True
            if self._kek_provider is None:
                msg = "No KEK provider configured for secret sealing"
                raise RuntimeError(msg)

            secret_str = data.secret
            if kind == "LDAP" and not secret_str.strip().startswith("{"):
                secret_bytes = json.dumps({"bind_dn_password": secret_str}).encode("utf-8")
            else:
                secret_bytes = secret_str.encode("utf-8")

            secret_buf = bytearray(secret_bytes)
            try:
                sealed = seal_card_secret(
                    card.id,
                    kind,
                    bytes(secret_buf),
                    self._kek_provider,
                )
                encrypted_blob = sealed.encrypted_secret_blob
                wrapped_dek = sealed.wrapped_dek
                dek_kid = sealed.dek_kid
            finally:
                for i in range(len(secret_buf)):
                    secret_buf[i] = 0

        # Reset health status to UNVERIFIED if config or secret changed
        if config_changed or secret_changed:
            last_health_status = "UNVERIFIED"
        else:
            last_health_status = card.last_health_status or "UNVERIFIED"

        # Check enable toggle if specified
        target_enabled = data.is_enabled if data.is_enabled is not None else card.is_enabled
        if card.is_enabled and not target_enabled:
            # Check lockout safeguards before disabling
            if card.provider_kind == "LOCAL_ADMIN":
                await assert_local_admin_disable_allowed(session, card.workspace_id)
            try:
                stmt = text("SELECT kb_auth.card_admin_set_enabled(:id, false)")
                await session.execute(stmt, {"id": card.id})
            except Exception as exc:
                if "LOCKOUT_PREVENTED" in str(exc) or getattr(exc, "sqlstate", None) == "P0001":
                    layer = extract_lockout_layer(exc)
                    raise LockoutPreventedError(str(exc), layer=layer) from exc
                raise

        upserted_id = await admin_upsert(
            session,
            card_id=card.id,
            workspace_id=card.workspace_id,
            provider_kind=kind,
            slug=card.slug,
            display_name=display_name,
            button_subtext=button_subtext,
            icon_preset=icon_preset,
            is_enabled=target_enabled,
            sort_rank=card.sort_rank,
            auto_provision_users=auto_provision,
            allowed_email_domains=allowed_domains,
            public_config=public_config,
            encrypted_secret_blob=encrypted_blob,
            wrapped_dek=wrapped_dek,
            dek_kid=dek_kid,
            last_health_status=last_health_status,
        )

        ws_target = card.workspace_id if card.workspace_id is not None else uuid.UUID(int=0)
        await record_activity(
            session,
            workspace_id=ws_target,
            actor_principal_id=actor_id,
            event_type=ActivityEventType.AUTH_CARD_UPDATED,
            payload={
                "card_id": str(upserted_id),
                "slug": card.slug,
                "provider_kind": kind,
            },
        )

        updated = await admin_get(session, upserted_id)
        if updated is None:
            raise ProblemException(
                code="NOT_FOUND",
                status=404,
                title="Card Not Found",
                detail="Updated card could not be retrieved.",
            )
        return to_admin_schema(updated)

    async def set_enabled(
        self,
        session: AsyncSession,
        card_ref: str | uuid.UUID,
        is_enabled: bool,  # noqa: FBT001
        actor_id: uuid.UUID,
    ) -> AuthCardAdmin:
        """Enable or disable an authentication card under anti-lockout safeguards."""
        card = await self._resolve_card(session, card_ref)
        if card is None:
            raise ProblemException(
                code="NOT_FOUND",
                status=404,
                title="Card Not Found",
                detail=f"Authentication provider card '{card_ref}' not found.",
            )

        if card.is_enabled == is_enabled:
            return to_admin_schema(card)

        if not is_enabled and card.provider_kind == "LOCAL_ADMIN":
            await assert_local_admin_disable_allowed(session, card.workspace_id)

        try:
            stmt = text("SELECT kb_auth.card_admin_set_enabled(:id, :enabled)")
            await session.execute(stmt, {"id": card.id, "enabled": is_enabled})
        except Exception as exc:
            if "LOCKOUT_PREVENTED" in str(exc) or getattr(exc, "sqlstate", None) == "P0001":
                layer = extract_lockout_layer(exc)
                raise LockoutPreventedError(str(exc), layer=layer) from exc
            raise

        event_type = (
            ActivityEventType.AUTH_CARD_ENABLED
            if is_enabled
            else ActivityEventType.AUTH_CARD_DISABLED
        )
        ws_target = card.workspace_id if card.workspace_id is not None else uuid.UUID(int=0)
        await record_activity(
            session,
            workspace_id=ws_target,
            actor_principal_id=actor_id,
            event_type=event_type,
            payload={
                "card_id": str(card.id),
                "slug": card.slug,
                "is_enabled": is_enabled,
            },
        )

        updated = await admin_get(session, card.id)
        if updated is None:
            raise ProblemException(
                code="NOT_FOUND",
                status=404,
                title="Card Not Found",
                detail="Toggled card could not be retrieved.",
            )
        return to_admin_schema(updated)

    async def reorder_card(
        self,
        session: AsyncSession,
        card_ref: str | uuid.UUID,
        after: str | None,
        actor_id: uuid.UUID,
    ) -> AuthCardAdmin:
        """Reposition card in the display sequence using fractional indexing."""
        target = await self._resolve_card(session, card_ref)
        if target is None:
            raise ProblemException(
                code="NOT_FOUND",
                status=404,
                title="Card Not Found",
                detail=f"Authentication provider card '{card_ref}' not found.",
            )

        all_cards = await admin_list(session)
        remaining = [c for c in all_cards if c.id != target.id]

        if after is None or not after.strip():
            # Move to front
            prev_rank: str | None = None
            nxt_rank: str | None = remaining[0].sort_rank if remaining else None
        else:
            after_str = after.strip()
            # Match after by slug or UUID
            after_card = None
            after_idx = -1
            for idx, c in enumerate(remaining):
                if c.slug == after_str or str(c.id) == after_str:
                    after_card = c
                    after_idx = idx
                    break

            if after_card is None:
                raise ProblemException(
                    code="NOT_FOUND",
                    status=404,
                    title="Reference Card Not Found",
                    detail=f"Reference card '{after}' not found.",
                )

            prev_rank = after_card.sort_rank
            nxt_rank = (
                remaining[after_idx + 1].sort_rank if after_idx + 1 < len(remaining) else None
            )

        new_rank = midpoint_rank(prev_rank, nxt_rank)

        if needs_rebalance(new_rank):
            # Atomic workspace re-spacing with even 4-character ranks
            if after is None or not after.strip():
                ordered = [target, *remaining]
            else:
                ordered = [
                    *remaining[: after_idx + 1],
                    target,
                    *remaining[after_idx + 1 :],
                ]

            rebalanced = rebalance_ranks(ordered)
            for c, r in rebalanced:
                stmt = text("SELECT kb_auth.card_admin_reorder(:id, :rank)")
                await session.execute(stmt, {"id": c.id, "rank": r})
        else:
            stmt = text("SELECT kb_auth.card_admin_reorder(:id, :rank)")
            await session.execute(stmt, {"id": target.id, "rank": new_rank})

        ws_target = target.workspace_id if target.workspace_id is not None else uuid.UUID(int=0)
        await record_activity(
            session,
            workspace_id=ws_target,
            actor_principal_id=actor_id,
            event_type=ActivityEventType.AUTH_CARD_REORDERED,
            payload={
                "card_id": str(target.id),
                "slug": target.slug,
                "after": after,
            },
        )

        updated = await admin_get(session, target.id)
        if updated is None:
            raise ProblemException(
                code="NOT_FOUND",
                status=404,
                title="Card Not Found",
                detail="Reordered card could not be retrieved.",
            )
        return to_admin_schema(updated)

    async def test_handshake(
        self,
        session: AsyncSession,
        card_ref: str | uuid.UUID,
        actor_id: uuid.UUID,
    ) -> HandshakeProbeResult:
        """Execute live test-handshake probe and update diagnostic health."""
        card = await self._resolve_card(session, card_ref)
        if card is None:
            raise ProblemException(
                code="NOT_FOUND",
                status=404,
                title="Card Not Found",
                detail=f"Authentication provider card '{card_ref}' not found.",
            )

        probe_result = await probe_auth_card_handshake(
            card,
            http_client=self._http_client,
            kek_provider=self._kek_provider,
            unix_socket_path=self._ldap_unix_socket_path,
        )

        stmt = text("SELECT kb_auth.card_admin_set_health(:id, :status)")
        await session.execute(stmt, {"id": card.id, "status": probe_result.status})

        ws_target = card.workspace_id if card.workspace_id is not None else uuid.UUID(int=0)
        await record_activity(
            session,
            workspace_id=ws_target,
            actor_principal_id=actor_id,
            event_type=ActivityEventType.AUTH_CARD_HANDSHAKE_TESTED,
            payload={
                "card_id": str(card.id),
                "slug": card.slug,
                "ok": probe_result.ok,
                "status": probe_result.status,
                "latency_ms": probe_result.latency_ms,
                "error_code": probe_result.error_code,
            },
        )

        return probe_result

    async def delete_card(
        self,
        session: AsyncSession,
        card_ref: str | uuid.UUID,
        confirm_slug: str,
        actor_id: uuid.UUID,
    ) -> None:
        """Permanently delete card after confirming slug and verifying anti-lockout."""
        card = await self._resolve_card(session, card_ref)
        if card is None:
            raise ProblemException(
                code="NOT_FOUND",
                status=404,
                title="Card Not Found",
                detail=f"Authentication provider card '{card_ref}' not found.",
            )

        if confirm_slug != card.slug:
            raise ProblemException(
                code="CONFIRM_PHRASE_MISMATCH",
                status=422,
                title="Confirmation Phrase Mismatch",
                detail=f"confirm_slug must match card slug '{card.slug}'.",
            )

        if card.is_enabled and card.provider_kind == "LOCAL_ADMIN":
            await assert_local_admin_disable_allowed(session, card.workspace_id)

        try:
            stmt = text("SELECT kb_auth.card_admin_delete(:id)")
            await session.execute(stmt, {"id": card.id})
        except Exception as exc:
            if "LOCKOUT_PREVENTED" in str(exc) or getattr(exc, "sqlstate", None) == "P0001":
                layer = extract_lockout_layer(exc)
                raise LockoutPreventedError(str(exc), layer=layer) from exc
            raise

        ws_target = card.workspace_id if card.workspace_id is not None else uuid.UUID(int=0)
        await record_activity(
            session,
            workspace_id=ws_target,
            actor_principal_id=actor_id,
            event_type=ActivityEventType.AUTH_CARD_DELETED,
            payload={
                "card_id": str(card.id),
                "slug": card.slug,
                "provider_kind": card.provider_kind,
            },
        )
