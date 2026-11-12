"""Thin asynchronous repository accessing kb_auth functions (KB-P2-03)."""

from __future__ import annotations

import json
import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import text

from database.models.auth import AuthProviderCard
from kanban.auth.cards.schemas import AuthCardAdmin, AuthCardPublic
from kanban.security.envelope import (
    KekProvider,
    SealedSecret,
    rewrap_dek,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


def to_admin_schema(card: AuthProviderCard) -> AuthCardAdmin:
    """Transform AuthProviderCard ORM model to sanitized AuthCardAdmin schema."""
    has_secret = bool(card.wrapped_dek is not None and card.encrypted_secret_blob is not None)
    return AuthCardAdmin(
        id=card.id,
        workspace_id=card.workspace_id,
        provider_kind=card.provider_kind,
        slug=card.slug,
        display_name=card.display_name,
        button_subtext=card.button_subtext,
        icon_preset=card.icon_preset or "key",
        is_enabled=bool(card.is_enabled),
        sort_rank=card.sort_rank,
        auto_provision_users=bool(card.auto_provision_users),
        allowed_email_domains=list(card.allowed_email_domains)
        if card.allowed_email_domains
        else [],
        public_config=dict(card.public_config) if card.public_config else {},
        dek_kid=card.dek_kid or "kek-v1",
        last_health_status=card.last_health_status or "UNVERIFIED",
        last_admin_handshake_at=getattr(card, "last_admin_handshake_at", None),
        created_at=card.created_at,
        updated_at=card.updated_at,
        has_secret=has_secret,
    )


async def list_enabled_public(session: AsyncSession) -> list[AuthCardPublic]:
    """Retrieve enabled cards for display on the public login view."""
    stmt = text(
        "SELECT slug, display_name, button_subtext, icon_preset, provider_kind, sort_rank "
        "FROM kb_auth.card_list_enabled_public()"
    )
    result = await session.execute(stmt)
    rows = result.mappings().all()
    return [
        AuthCardPublic(
            slug=r["slug"],
            display_name=r["display_name"],
            button_subtext=r["button_subtext"],
            icon_preset=r["icon_preset"],
            provider_kind=r["provider_kind"],
        )
        for r in rows
    ]


async def get_for_login(session: AsyncSession, slug: str) -> AuthProviderCard | None:
    """Retrieve enabled provider card by slug including ciphertext for login execution."""
    stmt = text("SELECT * FROM kb_auth.card_get_for_login(:slug)")
    result = await session.execute(stmt, {"slug": slug})
    row = result.mappings().first()
    if row is None:
        return None
    return AuthProviderCard(**dict(row))


async def admin_upsert(  # noqa: PLR0913
    session: AsyncSession,
    *,
    card_id: uuid.UUID | None = None,
    workspace_id: uuid.UUID | None = None,
    provider_kind: str,
    slug: str,
    display_name: str,
    button_subtext: str | None = None,
    icon_preset: str = "key",
    is_enabled: bool = False,
    sort_rank: str,
    auto_provision_users: bool = False,
    allowed_email_domains: list[str] | None = None,
    public_config: dict[str, Any] | None = None,
    encrypted_secret_blob: bytes | None = None,
    wrapped_dek: bytes | None = None,
    dek_kid: str = "kek-v1",
    last_health_status: str = "UNVERIFIED",
) -> uuid.UUID:
    """Upsert card configuration and credentials via kb_auth.card_admin_upsert."""
    cfg_json = json.dumps(public_config or {})
    stmt = text(
        "SELECT kb_auth.card_admin_upsert("
        ":p_id, :p_workspace_id, :p_provider_kind, :p_slug, :p_display_name, "
        ":p_button_subtext, :p_icon_preset, :p_is_enabled, :p_sort_rank, "
        ":p_auto_provision_users, :p_allowed_email_domains, :p_public_config, "
        ":p_encrypted_secret_blob, :p_wrapped_dek, :p_dek_kid, :p_last_health_status)"
    )
    result = await session.execute(
        stmt,
        {
            "p_id": card_id,
            "p_workspace_id": workspace_id,
            "p_provider_kind": provider_kind,
            "p_slug": slug,
            "p_display_name": display_name,
            "p_button_subtext": button_subtext,
            "p_icon_preset": icon_preset,
            "p_is_enabled": is_enabled,
            "p_sort_rank": sort_rank,
            "p_auto_provision_users": auto_provision_users,
            "p_allowed_email_domains": allowed_email_domains or [],
            "p_public_config": cfg_json,
            "p_encrypted_secret_blob": encrypted_secret_blob,
            "p_wrapped_dek": wrapped_dek,
            "p_dek_kid": dek_kid,
            "p_last_health_status": last_health_status,
        },
    )
    val = result.scalar_one()
    return uuid.UUID(str(val))


async def admin_get(session: AsyncSession, card_id: uuid.UUID) -> AuthProviderCard | None:
    """Retrieve complete card row by identifier under SERVER_ADMIN authorization."""
    stmt = text("SELECT * FROM kb_auth.card_admin_get(:id)")
    result = await session.execute(stmt, {"id": card_id})
    row = result.mappings().first()
    if row is None:
        return None
    return AuthProviderCard(**dict(row))


async def admin_list(session: AsyncSession) -> list[AuthProviderCard]:
    """List all provider cards ordered by sort rank under SERVER_ADMIN authorization."""
    stmt = text("SELECT * FROM kb_auth.card_admin_list()")
    result = await session.execute(stmt)
    rows = result.mappings().all()
    return [AuthProviderCard(**dict(r)) for r in rows]


async def card_rewrap(
    session: AsyncSession,
    card_id: uuid.UUID,
    wrapped_dek: bytes,
    old_kid: str,
    new_kid: str,
) -> bool:
    """Update wrapped DEK and kid on a card row via kb_auth.card_rewrap."""
    stmt = text("SELECT kb_auth.card_rewrap(:p_id, :p_wrapped_dek, :p_old_kid, :p_new_kid)")
    result = await session.execute(
        stmt,
        {
            "p_id": card_id,
            "p_wrapped_dek": wrapped_dek,
            "p_old_kid": old_kid,
            "p_new_kid": new_kid,
        },
    )
    return bool(result.scalar_one())


async def rewrap_all(
    session: AsyncSession,
    kek: KekProvider,
    new_kid: str,
) -> int:
    """Iterate through cards, rewrap any wrapped DEK under new_kid, and return count."""
    cards = await admin_list(session)
    count = 0
    for card in cards:
        if card.wrapped_dek is not None and card.encrypted_secret_blob is not None:
            if card.dek_kid == new_kid:
                continue
            sealed = SealedSecret(
                encrypted_secret_blob=card.encrypted_secret_blob,
                wrapped_dek=card.wrapped_dek,
                dek_kid=card.dek_kid,
            )
            rewrapped = rewrap_dek(card.id, sealed, kek, new_kid)
            success = await card_rewrap(
                session,
                card.id,
                rewrapped.wrapped_dek,
                card.dek_kid,
                new_kid,
            )
            if success:
                count += 1
    return count
