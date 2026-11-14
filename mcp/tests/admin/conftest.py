# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Test fixtures and test environment for /mcp/admin surface tests (KB-P4-09a)."""

from __future__ import annotations

import base64
import os
import uuid  # noqa: TC003
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from database.session import RLSSessionFactory
from database.testing.pg_harness import build_dsn
from kanban.api.deps import PrincipalContext
from kanban.app import create_app
from kanban.auth.cards.service import AuthCardAdminService
from kanban.auth.sessions.csrf import (
    CSRF_COOKIE_NAME,
    CSRF_HEADER_NAME,
    PRE_SESSION_ID,
    generate_csrf_token,
)
from kanban.security.envelope import StaticKekProvider
from kanban.security.keys import KeyMaterial
from kanban.tests.security.helpers import (
    add_role_binding,
    create_user,
    create_workspace,
    rebuild_era,
)
from mcp.app import create_mcp_app
from mcp.internal_client import KanbanApiClient
from mcp.settings import McpSettings

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from starlette.requests import Request


@dataclass(frozen=True, slots=True)
class AdminSeededUser:
    """User principal representation in admin tests."""

    id: uuid.UUID
    workspace_id: uuid.UUID
    handle: str


@dataclass(slots=True)
class AdminTestEnv:
    """Complete test environment for /mcp/admin surface."""

    mcp_client: httpx.AsyncClient
    internal_client: KanbanApiClient
    seed_session: AsyncSession
    workspace_id: uuid.UUID
    server_admin: AdminSeededUser
    workspace_admin: AdminSeededUser
    member_user: AdminSeededUser
    token_server_admin_full: str
    token_server_admin_read: str
    token_server_admin_write: str
    token_server_admin_aal1: str
    token_workspace_admin: str
    token_member: str
    token_agent_key: str
    fastapi_app: Any
    kek_provider: StaticKekProvider
    auth_card_service: AuthCardAdminService


class _TestTokenResolver:
    """Resolves PrincipalContext by checking X-KB-Subject-Token header."""

    def __init__(
        self,
        default_principal: PrincipalContext,
        token_map: dict[str, PrincipalContext],
    ) -> None:
        self.default_principal = default_principal
        self.token_map = token_map

    async def resolve(self, request: Request) -> PrincipalContext | None:
        tok = request.headers.get("x-kb-subject-token")
        if tok and tok in self.token_map:
            return self.token_map[tok]
        return self.default_principal


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode("ascii").rstrip("=")


@pytest.fixture(autouse=True)
def setup_admin_test_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure key material is populated in environment."""
    monkeypatch.delenv("KANBAN_KEYRING_FILE", raising=False)
    monkeypatch.setenv("KANBAN_MASTER_KEK", _b64(b"k" * 32))
    monkeypatch.setenv("KANBAN_AUTH_PEPPER", _b64(b"p" * 32))
    monkeypatch.setenv("KANBAN_SESSION_HMAC_KEY", _b64(b"s" * 32))
    monkeypatch.setenv("KANBAN_MASTER_KEK_KID", "test-kid-1")


@pytest.fixture
async def admin_env(
    committed_db_session: AsyncSession,
    pg_worker_db: AsyncEngine,
) -> AsyncIterator[AdminTestEnv]:
    """Provision a complete running admin test environment."""
    ws_id = await create_workspace(committed_db_session, name="Engineering")

    # 1. Server Admin principal
    server_admin_id = await create_user(
        committed_db_session, ws_id, handle="@server_admin", display_name="Server Admin"
    )
    await add_role_binding(
        committed_db_session,
        ws_id,
        server_admin_id,
        role="SERVER_ADMIN",
        scope_type="server",
    )

    # 2. Workspace Admin principal
    ws_admin_id = await create_user(
        committed_db_session, ws_id, handle="@ws_admin", display_name="Workspace Admin"
    )
    await add_role_binding(
        committed_db_session,
        ws_id,
        ws_admin_id,
        role="WORKSPACE_ADMIN",
        scope_type="workspace",
    )

    # 3. Regular Member principal
    member_id = await create_user(
        committed_db_session, ws_id, handle="@member", display_name="Member"
    )
    await add_role_binding(
        committed_db_session,
        ws_id,
        member_id,
        role="WORKSPACE_MEMBER",
        scope_type="workspace",
    )

    # Enroll & confirm TOTP for both administrators to satisfy require_admin_aal2
    for p_id in (server_admin_id, ws_admin_id):
        await committed_db_session.execute(
            text("SELECT kb_auth.totp_enroll(:p_id, :blob, :dek, 'test-kid-1')"),
            {
                "p_id": p_id,
                "blob": b"\x01" + b"\x00" * 28,
                "dek": b"\x01" + b"\x00" * 44,
            },
        )
        res = await committed_db_session.execute(
            text("SELECT id FROM kb_auth.totp_get_pending(:p_id)"),
            {"p_id": p_id},
        )
        p_row = res.mappings().first()
        if p_row:
            await committed_db_session.execute(
                text("SELECT kb_auth.totp_confirm(:p_fid, 100)"),
                {"p_fid": p_row["id"]},
            )

    await rebuild_era(committed_db_session, ws_id)
    await committed_db_session.commit()

    # Tokens
    token_server_admin_full = "kb_adm_full_" + "1" * 32
    token_server_admin_read = "kb_adm_read_" + "2" * 32
    token_server_admin_write = "kb_adm_write_" + "3" * 32
    token_server_admin_aal1 = "kb_adm_aal1_" + "4" * 32
    token_workspace_admin = "kb_adm_wsadm_" + "5" * 32
    token_member = "kb_adm_member_" + "6" * 32
    token_agent_key = "kb_agt_agent_" + "7" * 32

    token_map = {
        token_server_admin_full: PrincipalContext(
            principal_id=server_admin_id,
            workspace_id=ws_id,
            token_scopes=("admin:read", "admin:write", "admin:destructive"),
            aal_level=2,
        ),
        token_server_admin_read: PrincipalContext(
            principal_id=server_admin_id,
            workspace_id=ws_id,
            token_scopes=("admin:read",),
            aal_level=2,
        ),
        token_server_admin_write: PrincipalContext(
            principal_id=server_admin_id,
            workspace_id=ws_id,
            token_scopes=("admin:read", "admin:write"),
            aal_level=2,
        ),
        token_server_admin_aal1: PrincipalContext(
            principal_id=server_admin_id,
            workspace_id=ws_id,
            token_scopes=("admin:read", "admin:write", "admin:destructive"),
            aal_level=1,
        ),
        token_workspace_admin: PrincipalContext(
            principal_id=ws_admin_id,
            workspace_id=ws_id,
            token_scopes=("admin:read", "admin:write"),
            aal_level=2,
        ),
        token_member: PrincipalContext(
            principal_id=member_id,
            workspace_id=ws_id,
            token_scopes=("session",),
            aal_level=2,
        ),
        token_agent_key: PrincipalContext(
            principal_id=server_admin_id,
            workspace_id=ws_id,
            token_scopes=("agent:read", "agent:write"),
            aal_level=2,
        ),
    }

    resolver = _TestTokenResolver(
        default_principal=token_map[token_server_admin_full],
        token_map=token_map,
    )

    db_name = pg_worker_db.url.database or "kanban_test"
    socket_dir = os.environ.get("KB_TEST_PGHOST", "/tmp/kb-pgsock")
    app_engine = create_async_engine(
        build_dsn(database=db_name, host=socket_dir, user="kanban_app"),
        poolclass=NullPool,
    )

    km = KeyMaterial(
        master_kek=b"k" * 32,
        master_kek_kid="test-kid-1",
        auth_pepper=b"p" * 32,
        session_hmac_key=b"s" * 32,
    )
    kek_provider = StaticKekProvider(keys={"test-kid-1": km.master_kek}, current="test-kid-1")
    auth_card_service = AuthCardAdminService(kek_provider=kek_provider)

    fastapi_app = create_app()
    fastapi_app.state.session_factory = RLSSessionFactory(app_engine)
    fastapi_app.state.principal_resolver = resolver
    fastapi_app.state.kek_provider = kek_provider
    fastapi_app.state.auth_card_admin_service = auth_card_service

    mcp_settings = McpSettings(mode="standalone_inprocess", auth_enabled=False)
    internal_client = KanbanApiClient(mcp_settings, kanban_app=fastapi_app)

    mcp_starlette_app = create_mcp_app(mcp_settings, kanban_app=fastapi_app)
    transport = httpx.ASGITransport(app=mcp_starlette_app)

    csrf_token = generate_csrf_token(PRE_SESSION_ID, b"\x00" * 32)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={
            CSRF_HEADER_NAME: csrf_token,
            "X-KB-Subject-Token": token_server_admin_full,
        },
        cookies={CSRF_COOKIE_NAME: csrf_token},
    ) as mcp_http_client:
        env = AdminTestEnv(
            mcp_client=mcp_http_client,
            internal_client=internal_client,
            seed_session=committed_db_session,
            workspace_id=ws_id,
            server_admin=AdminSeededUser(
                id=server_admin_id, workspace_id=ws_id, handle="server_admin"
            ),
            workspace_admin=AdminSeededUser(id=ws_admin_id, workspace_id=ws_id, handle="ws_admin"),
            member_user=AdminSeededUser(id=member_id, workspace_id=ws_id, handle="member"),
            token_server_admin_full=token_server_admin_full,
            token_server_admin_read=token_server_admin_read,
            token_server_admin_write=token_server_admin_write,
            token_server_admin_aal1=token_server_admin_aal1,
            token_workspace_admin=token_workspace_admin,
            token_member=token_member,
            token_agent_key=token_agent_key,
            fastapi_app=fastapi_app,
            kek_provider=kek_provider,
            auth_card_service=auth_card_service,
        )
        try:
            yield env
        finally:
            await internal_client.aclose()
            await app_engine.dispose()
