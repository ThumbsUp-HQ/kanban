# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Database and DDL tests for auth_provider_cards and kb_auth boundary (KB-P2-03)."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


async def _setup_server_admin(
    session: AsyncSession,
) -> tuple[uuid.UUID, uuid.UUID]:
    """Provision workspace, active user principal, and SERVER_ADMIN binding."""
    ws_id = uuid.uuid4()
    await session.execute(
        text("INSERT INTO workspaces (id, slug, name) VALUES (:id, :slug, :name)"),
        {"id": ws_id, "slug": f"ws-{ws_id.hex[:10]}", "name": "Admin WS"},
    )

    u_id = uuid.uuid4()
    # Register in objects spine first
    await session.execute(
        text(
            "SELECT register_object('user'::object_kind, :ws_id, NULL, :ckey, :title, :u_id, :u_id)"
        ),
        {
            "ws_id": ws_id,
            "ckey": f"usr-{u_id.hex}",
            "title": "Server Admin User",
            "u_id": u_id,
        },
    )

    # Insert into principals
    await session.execute(
        text(
            "INSERT INTO principals (id, principal_type, workspace_id, display_name, status) "
            "VALUES (:id, 'USER', :ws_id, 'Server Admin User', 'ACTIVE')"
        ),
        {"id": u_id, "ws_id": ws_id},
    )

    # Insert into users
    await session.execute(
        text(
            "INSERT INTO users (id, object_type, principal_type, workspace_id, email) "
            "VALUES (:id, 'user', 'USER', :ws_id, 'admin@example.com')"
        ),
        {"id": u_id, "ws_id": ws_id},
    )

    # Bind SERVER_ADMIN role
    rb_id = uuid.uuid4()
    await session.execute(
        text(
            "INSERT INTO role_bindings "
            "(id, workspace_id, principal_id, role, scope_type, project_id) "
            "VALUES (:id, :ws_id, :p_id, 'SERVER_ADMIN', 'server', NULL)"
        ),
        {"id": rb_id, "ws_id": ws_id, "p_id": u_id},
    )

    return ws_id, u_id


@pytest.mark.asyncio
async def test_07_db_boundary_and_privileges(db_session: AsyncSession) -> None:
    """Test Case 7: RLS and role boundaries for auth_provider_cards and kb_auth functions."""
    # Setup data under superuser
    ws_id, admin_id = await _setup_server_admin(db_session)

    # Switch session to least-privileged kanban_app role
    await db_session.execute(text("SET LOCAL SESSION AUTHORIZATION kanban_app"))

    # 1. As kanban_app, direct SELECT * FROM auth_provider_cards raises 42501
    with pytest.raises(DBAPIError) as exc_info:
        async with db_session.begin_nested():
            await db_session.execute(text("SELECT * FROM auth_provider_cards"))
    assert "42501" in str(exc_info.value) or "permission denied" in str(exc_info.value).lower()

    # 2. SELECT encrypted_secret_blob from card_list_enabled_public() raises undefined column
    with pytest.raises(DBAPIError) as exc_info:
        async with db_session.begin_nested():
            await db_session.execute(
                text("SELECT encrypted_secret_blob FROM kb_auth.card_list_enabled_public()")
            )
    err_msg = str(exc_info.value).lower()
    assert "does not exist" in err_msg or "42703" in str(exc_info.value)

    # 3. kb_auth.card_admin_list() without SERVER_ADMIN context raises 42501
    with pytest.raises(DBAPIError) as exc_info:
        async with db_session.begin_nested():
            await db_session.execute(text("SELECT * FROM kb_auth.card_admin_list()"))
    assert getattr(
        exc_info.value.orig, "sqlstate", None
    ) == "42501" or "insufficient_privilege" in str(exc_info.value)

    # 4. With SERVER_ADMIN but app.aal_level = '1' raises 42501
    await db_session.execute(
        text(
            "SELECT set_config('app.principal_id', :p_id, true), "
            "set_config('app.workspace_id', :w_id, true), "
            "set_config('app.aal_level', '1', true)"
        ),
        {"p_id": str(admin_id), "w_id": str(ws_id)},
    )
    with pytest.raises(DBAPIError) as exc_info:
        async with db_session.begin_nested():
            await db_session.execute(text("SELECT * FROM kb_auth.card_admin_list()"))
    assert getattr(
        exc_info.value.orig, "sqlstate", None
    ) == "42501" or "insufficient_privilege" in str(exc_info.value)

    # 5. With SERVER_ADMIN and app.aal_level = '2' -> rows returned
    await db_session.execute(text("SELECT set_config('app.aal_level', '2', true)"))
    res = await db_session.execute(text("SELECT * FROM kb_auth.card_admin_list()"))
    rows = res.mappings().all()
    assert isinstance(rows, list)


@pytest.mark.asyncio
async def test_08_db_ddl_constraints_and_search_path(db_session: AsyncSession) -> None:
    """Test Case 8: DDL check constraints and search_path hijack defense."""
    ws_id = uuid.uuid4()
    await db_session.execute(
        text("INSERT INTO workspaces (id, slug, name) VALUES (:id, :slug, :name)"),
        {"id": ws_id, "slug": f"ws-{ws_id.hex[:10]}", "name": "DDL WS"},
    )

    async def try_insert(
        slug: str,
        kind: str = "OIDC",
        secret: bytes | None = None,
        dek: bytes | None = None,
    ) -> None:
        c_id = uuid.uuid4()
        await db_session.execute(
            text(
                "INSERT INTO auth_provider_cards ("
                "  id, workspace_id, provider_kind, slug, display_name, sort_rank, "
                "  encrypted_secret_blob, wrapped_dek"
                ") VALUES (:id, :ws_id, :kind, :slug, :name, :rank, :secret, :dek)"
            ),
            {
                "id": c_id,
                "ws_id": ws_id,
                "kind": kind,
                "slug": slug,
                "name": "Test IdP",
                "rank": "0|hzzzzz:",
                "secret": secret,
                "dek": dek,
            },
        )

    # 1. Invalid slugs rejected
    for bad_slug in ("-bad", "a", "UPPER", "a" * 49):
        with pytest.raises(DBAPIError) as exc_info:
            async with db_session.begin_nested():
                await try_insert(bad_slug)
        assert "check" in str(exc_info.value).lower() or "23514" in str(exc_info.value)

    # 2. provider_kind='SAML' rejected
    with pytest.raises(DBAPIError) as exc_info:
        async with db_session.begin_nested():
            await try_insert("valid-saml-card", kind="SAML")
    assert "check" in str(exc_info.value).lower() or "23514" in str(exc_info.value)

    # 3. Secret blob set with NULL wrapped_dek rejected by CHECK constraint
    with pytest.raises(DBAPIError) as exc_info:
        async with db_session.begin_nested():
            await try_insert("secret-without-dek", secret=b"\x01test", dek=None)
    assert "check" in str(exc_info.value).lower() or "23514" in str(exc_info.value)

    with pytest.raises(DBAPIError) as exc_info:
        async with db_session.begin_nested():
            await try_insert("dek-without-secret", secret=None, dek=b"\x01dek")
    assert "check" in str(exc_info.value).lower() or "23514" in str(exc_info.value)

    # 4. Valid card insert succeeds
    valid_id = uuid.uuid4()
    await db_session.execute(
        text(
            "INSERT INTO auth_provider_cards ("
            "  id, workspace_id, provider_kind, slug, display_name, sort_rank, "
            "  is_enabled, encrypted_secret_blob, wrapped_dek"
            ") VALUES (:id, :ws_id, 'OIDC', 'valid-oidc-slug', 'Valid OIDC', '0|hzzzzz:', "
            "  true, :secret, :dek)"
        ),
        {
            "id": valid_id,
            "ws_id": ws_id,
            "secret": b"\x01secretblob123456789012345678",
            "dek": b"\x01wrappeddek123456789012345678",
        },
    )

    # 5. search_path hijack attempt: shadow lower() in public
    await db_session.execute(
        text(
            "CREATE OR REPLACE FUNCTION public.lower(text) RETURNS text LANGUAGE sql AS "
            "$$ SELECT 'HIJACKED'::text; $$"
        )
    )
    try:
        res = await db_session.execute(
            text("SELECT slug, display_name FROM kb_auth.card_list_enabled_public()")
        )
        row = res.mappings().first()
        assert row is not None
        assert row["slug"] == "valid-oidc-slug"
        assert row["display_name"] == "Valid OIDC"
    finally:
        await db_session.execute(text("DROP FUNCTION IF EXISTS public.lower(text)"))
