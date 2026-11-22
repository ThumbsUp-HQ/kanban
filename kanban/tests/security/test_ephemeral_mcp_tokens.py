# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Unit and security tests for ephemeral kb_agt_eph_* MCP tokens (KB-P4-13 / S14.3)."""

# ruff: noqa: PLR0915

from __future__ import annotations

import asyncio
import base64
import json
import uuid
from typing import TYPE_CHECKING

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from database.session import RLSContext, RLSSessionFactory, bind_rls_context
from kanban.api.deps import PrincipalContext
from kanban.api.problems import ProblemException
from kanban.app import create_app, create_internal_app
from kanban.security.ephemeral_mcp_tokens import (
    EPHEMERAL_TOKEN_PREFIX,
    generate_ephemeral_mcp_token,
    introspect_and_consume_ephemeral_token,
    mint_ephemeral_token,
    revoke_ephemeral_tokens_by_execution,
)
from kanban.security.mcp_keys import (
    McpIntrospectionResult,
    hash_mcp_api_key,
)
from kanban.security.permissions import (
    Capability,
    evaluate_capabilities,
    require_capability,
)
from kanban.security.service_auth import create_internal_service_auth_header
from kanban.settings import Settings
from kanban.tests.security.helpers import (
    add_acl_entry,
    create_agent,
    create_project,
    create_registered_object,
    create_user,
    create_workspace,
    rebuild_era,
)
from kanban.tests.security.test_internal_route_isolation import seed_bound_execution

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode("ascii").rstrip("=")


@pytest.fixture(autouse=True)
def setup_test_key_material(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set up valid test key material in environment."""
    monkeypatch.delenv("KANBAN_KEYRING_FILE", raising=False)
    monkeypatch.setenv("KANBAN_MASTER_KEK", _b64(b"k" * 32))
    monkeypatch.setenv("KANBAN_AUTH_PEPPER", _b64(b"p" * 32))
    monkeypatch.setenv("KANBAN_SESSION_HMAC_KEY", _b64(b"s" * 32))
    monkeypatch.setenv("KANBAN_MASTER_KEK_KID", "test-kid-1")


@pytest.mark.asyncio
async def test_case_1_positive_mint_and_token_format(db_session: AsyncSession) -> None:
    """Test Case 1: Positive mint, token prefix, length, hash check, DB catalog check."""
    ws_id = await create_workspace(db_session, name="WS-Eph-1")
    adam_id = await create_user(db_session, ws_id, handle="@adam", display_name="Adam")
    agent_id = await create_agent(db_session, ws_id, display_name="agy-gate")
    proj_id = await create_project(db_session, ws_id, identifier="KAN", name="Kanban")
    exec_id = await seed_bound_execution(
        db_session,
        ws_id=ws_id,
        proj_id=proj_id,
        invoking_principal_id=adam_id,
        agent_principal_id=agent_id,
    )

    record, token = await mint_ephemeral_token(
        db_session,
        workspace_id=ws_id,
        execution_id=exec_id,
        invoking_principal_id=adam_id,
        agent_principal_id=agent_id,
        project_id=proj_id,
        allowed_tools=["search_tickets", "read_ticket"],
        ttl_seconds=60,
        max_calls=3,
    )

    # 1. Plaintext format check
    assert token.startswith(EPHEMERAL_TOKEN_PREFIX)
    assert len(token) == 11 + 43  # kb_agt_eph_ (11) + 43 = 54 chars
    assert record.max_calls == 3
    assert record.calls_used == 0
    assert record.allowed_tools == ["search_tickets", "read_ticket"]
    assert record.token_sha256 == hash_mcp_api_key(token)
    assert record.execution_id == exec_id
    assert record.workspace_id == ws_id
    assert record.project_id == proj_id

    # 2. Non-consuming introspection
    intro = await introspect_and_consume_ephemeral_token(
        db_session,
        token=token,
        surface="agent",
        consume_call=False,
    )
    assert intro.active is True
    assert intro.token_kind == "ephemeral"
    assert intro.surface == "agent"
    assert intro.scopes == ["agent:read", "docs:read"]
    assert intro.principal_id == adam_id
    assert intro.agent_principal_id == agent_id
    assert intro.workspace_id == ws_id
    assert intro.project_id == proj_id
    assert intro.execution_id == exec_id
    assert intro.allowed_tools is not None
    assert set(intro.allowed_tools) == {
        "search_tickets",
        "read_ticket",
    }
    assert intro.calls_used == 0
    assert intro.max_calls == 3

    # 3. Consuming introspection on search_tickets (call 1)
    c1 = await introspect_and_consume_ephemeral_token(
        db_session,
        token=token,
        surface="agent",
        consume_call=True,
        tool_name="search_tickets",
    )
    assert c1.active is True
    assert c1.calls_used == 1

    # 4. Consuming introspection on read_ticket (call 2)
    c2 = await introspect_and_consume_ephemeral_token(
        db_session,
        token=token,
        surface="agent",
        consume_call=True,
        tool_name="read_ticket",
    )
    assert c2.active is True
    assert c2.calls_used == 2

    # 5. Consuming introspection on read_ticket (call 3)
    c3 = await introspect_and_consume_ephemeral_token(
        db_session,
        token=token,
        surface="agent",
        consume_call=True,
        tool_name="read_ticket",
    )
    assert c3.active is True
    assert c3.calls_used == 3

    # 6. Call 4 fails with EPHEMERAL_CALL_BUDGET_EXCEEDED
    c4 = await introspect_and_consume_ephemeral_token(
        db_session,
        token=token,
        surface="agent",
        consume_call=True,
        tool_name="read_ticket",
    )
    assert c4.active is False
    assert c4.reason == "EPHEMERAL_CALL_BUDGET_EXCEEDED"
    assert c4.calls_used == 3
    assert c4.max_calls == 3


@pytest.mark.asyncio
async def test_case_2_validation_and_db_checks(db_session: AsyncSession) -> None:
    """Test Case 2: Validation of TTL, max_calls, allowed_tools, and DB check constraints."""
    ws_id = await create_workspace(db_session, name="WS-Eph-2")
    user_id = await create_user(db_session, ws_id, handle="@user2", display_name="User 2")
    agent_id = await create_agent(db_session, ws_id, display_name="agent-2")
    proj_id = await create_project(db_session, ws_id, identifier="PRJ2", name="Project 2")
    exec_id = uuid.uuid4()

    # 1. TTL > 120s rejected with 422
    with pytest.raises(ProblemException) as exc1:
        await mint_ephemeral_token(
            db_session,
            workspace_id=ws_id,
            execution_id=exec_id,
            invoking_principal_id=user_id,
            agent_principal_id=agent_id,
            project_id=proj_id,
            ttl_seconds=121,
        )
    assert exc1.value.status == 422
    assert exc1.value.code == "INVALID_EXPIRATION"

    # 2. max_calls > 25 rejected with 422
    with pytest.raises(ProblemException) as exc2:
        await mint_ephemeral_token(
            db_session,
            workspace_id=ws_id,
            execution_id=exec_id,
            invoking_principal_id=user_id,
            agent_principal_id=agent_id,
            project_id=proj_id,
            max_calls=26,
        )
    assert exc2.value.status == 422
    assert exc2.value.code == "INVALID_CALL_BUDGET"

    # 3. Disallowed tool (write tool) rejected with 422
    with pytest.raises(ProblemException) as exc3:
        await mint_ephemeral_token(
            db_session,
            workspace_id=ws_id,
            execution_id=exec_id,
            invoking_principal_id=user_id,
            agent_principal_id=agent_id,
            project_id=proj_id,
            allowed_tools=["create_ticket"],
        )
    assert exc3.value.status == 422
    assert exc3.value.code == "INVALID_TOOLS"

    # 4. Empty allowed_tools rejected with 422
    with pytest.raises(ProblemException) as exc4:
        await mint_ephemeral_token(
            db_session,
            workspace_id=ws_id,
            execution_id=exec_id,
            invoking_principal_id=user_id,
            agent_principal_id=agent_id,
            project_id=proj_id,
            allowed_tools=[],
        )
    assert exc4.value.status == 422
    assert exc4.value.code == "INVALID_TOOLS"

    # 5. Non-agent as agent_principal rejected with 422
    with pytest.raises(ProblemException) as exc5:
        await mint_ephemeral_token(
            db_session,
            workspace_id=ws_id,
            execution_id=exec_id,
            invoking_principal_id=user_id,
            agent_principal_id=user_id,  # User, not AGENT
            project_id=proj_id,
        )
    assert exc5.value.status == 422
    assert exc5.value.code == "INVALID_PRINCIPAL"

    # 6. Direct SQL insert violating DB CHECK max_calls > 25
    _, tok_hash = generate_ephemeral_mcp_token()
    with pytest.raises(IntegrityError):
        await db_session.execute(
            text(
                "INSERT INTO mcp_ephemeral_tokens ("
                "  workspace_id, execution_id, invoking_principal_id, agent_principal_id, "
                "  project_id, token_sha256, allowed_tools, max_calls, expires_at"
                ") VALUES ("
                "  :ws, :ex, :inv, :agt, :proj, :hash, ARRAY['read_ticket']::text[], 26, "
                "  clock_timestamp() + interval '60 seconds'"
                ")"
            ),
            {
                "ws": ws_id,
                "ex": exec_id,
                "inv": user_id,
                "agt": agent_id,
                "proj": proj_id,
                "hash": tok_hash,
            },
        )
    await db_session.rollback()

    # 7. Direct SQL insert violating DB CHECK TTL > 120s
    with pytest.raises(IntegrityError):
        await db_session.execute(
            text(
                "INSERT INTO mcp_ephemeral_tokens ("
                "  workspace_id, execution_id, invoking_principal_id, agent_principal_id, "
                "  project_id, token_sha256, allowed_tools, max_calls, expires_at"
                ") VALUES ("
                "  :ws, :ex, :inv, :agt, :proj, :hash, ARRAY['read_ticket']::text[], 10, "
                "  clock_timestamp() + interval '125 seconds'"
                ")"
            ),
            {
                "ws": ws_id,
                "ex": exec_id,
                "inv": user_id,
                "agt": agent_id,
                "proj": proj_id,
                "hash": tok_hash,
            },
        )
    await db_session.rollback()

    # 8. Direct SQL insert violating DB CHECK allowed_tools subset
    with pytest.raises(IntegrityError):
        await db_session.execute(
            text(
                "INSERT INTO mcp_ephemeral_tokens ("
                "  workspace_id, execution_id, invoking_principal_id, agent_principal_id, "
                "  project_id, token_sha256, allowed_tools, max_calls, expires_at"
                ") VALUES ("
                "  :ws, :ex, :inv, :agt, :proj, :hash, ARRAY['create_ticket']::text[], 10, "
                "  clock_timestamp() + interval '60 seconds'"
                ")"
            ),
            {
                "ws": ws_id,
                "ex": exec_id,
                "inv": user_id,
                "agt": agent_id,
                "proj": proj_id,
                "hash": tok_hash,
            },
        )
    await db_session.rollback()


@pytest.mark.asyncio
async def test_case_3_surface_isolation_and_revocation(db_session: AsyncSession) -> None:
    """Test Case 3: Surface check, forbidden tool check, and revocation by execution_id."""
    ws_id = await create_workspace(db_session, name="WS-Eph-3")
    user_id = await create_user(db_session, ws_id, handle="@user3", display_name="User 3")
    agent_id = await create_agent(db_session, ws_id, display_name="agent-3")
    proj_id = await create_project(db_session, ws_id, identifier="PRJ3", name="Project 3")
    exec_id = await seed_bound_execution(
        db_session,
        ws_id=ws_id,
        proj_id=proj_id,
        invoking_principal_id=user_id,
        agent_principal_id=agent_id,
    )

    _rec, token = await mint_ephemeral_token(
        db_session,
        workspace_id=ws_id,
        execution_id=exec_id,
        invoking_principal_id=user_id,
        agent_principal_id=agent_id,
        project_id=proj_id,
        allowed_tools=["search_tickets", "read_ticket", "search_knowledge", "read_doc"],
        ttl_seconds=100,
        max_calls=10,
    )

    # 1. Admin surface rejected with SURFACE_KEY_MISMATCH
    intro_admin = await introspect_and_consume_ephemeral_token(
        db_session,
        token=token,
        surface="admin",
        consume_call=False,
    )
    assert intro_admin.active is False
    assert intro_admin.reason == "SURFACE_KEY_MISMATCH"

    # 2. Tool forbidden check on agent surface: search_knowledge belongs to docs, not agent
    intro_wrong_surface_tool = await introspect_and_consume_ephemeral_token(
        db_session,
        token=token,
        surface="agent",
        consume_call=True,
        tool_name="search_knowledge",
    )
    assert intro_wrong_surface_tool.active is False
    assert intro_wrong_surface_tool.reason == "EPHEMERAL_TOOL_FORBIDDEN"

    # 3. Disallowed mutating tool: create_ticket
    intro_write = await introspect_and_consume_ephemeral_token(
        db_session,
        token=token,
        surface="agent",
        consume_call=True,
        tool_name="create_ticket",
    )
    assert intro_write.active is False
    assert intro_write.reason == "EPHEMERAL_TOOL_FORBIDDEN"

    # 4. Revocation by execution_id
    revoked_count = await revoke_ephemeral_tokens_by_execution(db_session, execution_id=exec_id)
    assert revoked_count == 1

    # 5. Immediate next call returns TOKEN_EXPIRED_OR_REVOKED
    intro_post_revoke = await introspect_and_consume_ephemeral_token(
        db_session,
        token=token,
        surface="agent",
        consume_call=False,
    )
    assert intro_post_revoke.active is False
    assert intro_post_revoke.reason == "TOKEN_EXPIRED_OR_REVOKED"


@pytest.mark.asyncio
async def test_case_4_triple_intersection_and_project_pin(db_session: AsyncSession) -> None:
    """Test Case 4: Triple intersection (Invoker ∩ Agent ∩ Project) and READ ONLY transaction."""
    ws_id = await create_workspace(db_session, name="WS-Eph-4")
    adam_id = await create_user(db_session, ws_id, handle="@adam4", display_name="Adam 4")
    agent_id = await create_agent(db_session, ws_id, display_name="agy-gate-4")

    # Seed projects KAN and SEC
    kan_id = await create_project(db_session, ws_id, identifier="KAN", name="Kanban Project")
    sec_id = await create_project(db_session, ws_id, identifier="SEC", name="Security Project")

    # Give both adam and agy-gate VIEW on KAN and SEC
    await add_acl_entry(
        db_session, ws_id, kan_id, adam_id, effect="ALLOW", capability_mask=Capability.VIEW
    )
    await add_acl_entry(
        db_session, ws_id, kan_id, agent_id, effect="ALLOW", capability_mask=Capability.VIEW
    )
    await add_acl_entry(
        db_session, ws_id, sec_id, adam_id, effect="ALLOW", capability_mask=Capability.VIEW
    )
    await add_acl_entry(
        db_session, ws_id, sec_id, agent_id, effect="ALLOW", capability_mask=Capability.VIEW
    )

    # Seed issues:
    # KAN-1: Both adam and agent hold VIEW
    kan_1_id = await create_registered_object(
        db_session,
        ws_id,
        kind="issue",
        key="KAN-1",
        title="Issue 1",
        project_id=kan_id,
        created_by_id=adam_id,
    )
    await add_acl_entry(
        db_session, ws_id, kan_1_id, adam_id, effect="ALLOW", capability_mask=Capability.VIEW
    )
    await add_acl_entry(
        db_session, ws_id, kan_1_id, agent_id, effect="ALLOW", capability_mask=Capability.VIEW
    )

    # KAN-2: adam holds VIEW, agent has NO grant
    kan_2_id = await create_registered_object(
        db_session,
        ws_id,
        kind="issue",
        key="KAN-2",
        title="Issue 2",
        project_id=kan_id,
        created_by_id=adam_id,
    )
    await add_acl_entry(
        db_session, ws_id, kan_2_id, adam_id, effect="ALLOW", capability_mask=Capability.VIEW
    )

    # KAN-3: agent holds VIEW, adam has DENY VIEW
    kan_3_id = await create_registered_object(
        db_session,
        ws_id,
        kind="issue",
        key="KAN-3",
        title="Issue 3",
        project_id=kan_id,
        created_by_id=adam_id,
    )
    await add_acl_entry(
        db_session, ws_id, kan_3_id, agent_id, effect="ALLOW", capability_mask=Capability.VIEW
    )
    await add_acl_entry(
        db_session, ws_id, kan_3_id, adam_id, effect="DENY", capability_mask=Capability.VIEW
    )

    # SEC-1: Issue in foreign project SEC (both hold VIEW on object)
    sec_1_id = await create_registered_object(
        db_session,
        ws_id,
        kind="issue",
        key="SEC-1",
        title="Security Issue 1",
        project_id=sec_id,
        created_by_id=adam_id,
    )
    await add_acl_entry(
        db_session, ws_id, sec_1_id, adam_id, effect="ALLOW", capability_mask=Capability.VIEW
    )
    await add_acl_entry(
        db_session, ws_id, sec_1_id, agent_id, effect="ALLOW", capability_mask=Capability.VIEW
    )

    await rebuild_era(db_session, ws_id)

    # Build PrincipalContext pinned to project KAN
    p_ctx = PrincipalContext(
        principal_id=adam_id,
        workspace_id=ws_id,
        token_scopes=("agent:read", "docs:read"),
        agent_principal_id=agent_id,
        ephemeral_project_id=kan_id,
        read_only=True,
    )

    # 1. KAN-1 has VIEW (both invoker and agent have VIEW, and project matches KAN)
    caps_1 = await evaluate_capabilities(db_session, p_ctx, kan_1_id)
    assert Capability.VIEW in caps_1

    # 2. SEC-1 belongs to SEC -> evaluated as NONE due to project pin
    caps_sec = await evaluate_capabilities(db_session, p_ctx, sec_1_id)
    assert caps_sec == Capability.NONE
    with pytest.raises(ProblemException) as exc_sec:
        await require_capability(db_session, p_ctx, sec_1_id, Capability.VIEW)
    assert exc_sec.value.status == 404

    # 3. KAN-2: agent lacks grant -> evaluated as NONE
    caps_2 = await evaluate_capabilities(db_session, p_ctx, kan_2_id)
    assert caps_2 == Capability.NONE
    with pytest.raises(ProblemException) as exc_2:
        await require_capability(db_session, p_ctx, kan_2_id, Capability.VIEW)
    assert exc_2.value.status == 404

    # 4. KAN-3: invoker has explicit DENY -> evaluated as NONE
    caps_3 = await evaluate_capabilities(db_session, p_ctx, kan_3_id)
    assert caps_3 == Capability.NONE
    with pytest.raises(ProblemException) as exc_3:
        await require_capability(db_session, p_ctx, kan_3_id, Capability.VIEW)
    assert exc_3.value.status == 404

    # 5. Database session SET LOCAL TRANSACTION READ ONLY defense-in-depth
    rls_ctx = RLSContext(
        principal_id=adam_id,
        workspace_id=ws_id,
        token_scopes=("agent:read", "docs:read"),
        agent_principal_id=agent_id,
        ephemeral_project_id=kan_id,
        read_only=True,
    )
    await bind_rls_context(db_session, rls_ctx)

    # Attempting to insert in READ ONLY transaction fails with 25006
    with pytest.raises((IntegrityError, DBAPIError)):
        await db_session.execute(
            text("INSERT INTO workspaces (slug, name) VALUES ('ro-test', 'ReadOnlyTest')")
        )
    await db_session.rollback()


@pytest.mark.asyncio
async def test_case_5_internal_endpoints_and_mtls_boundary(db_session: AsyncSession) -> None:
    """Test Case 5: Role-bound HMAC boundary for minting (mcp-gateway 403, agent-runtime 201)."""
    ws_id = await create_workspace(db_session, name="WS-Eph-5")
    user_id = await create_user(db_session, ws_id, handle="@user5", display_name="User 5")
    agent_id = await create_agent(db_session, ws_id, display_name="agent-5")
    proj_id = await create_project(db_session, ws_id, identifier="PRJ5", name="Project 5")
    exec_id = await seed_bound_execution(
        db_session,
        ws_id=ws_id,
        proj_id=proj_id,
        invoking_principal_id=user_id,
        agent_principal_id=agent_id,
    )

    settings = Settings()
    app = create_app(settings)
    app.state.session_factory = RLSSessionFactory(db_session.bind)  # type: ignore[arg-type]
    internal_app = create_internal_app(app)

    await db_session.commit()

    transport = httpx.ASGITransport(app=internal_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        mint_path = "/internal/v1/mcp/ephemeral-tokens"
        mint_payload = {
            "workspace_id": str(ws_id),
            "execution_id": str(exec_id),
            "invoking_principal_id": str(user_id),
            "agent_principal_id": str(agent_id),
            "project_id": str(proj_id),
            "ttl_seconds": 60,
            "max_calls": 10,
        }
        mint_body = json.dumps(mint_payload).encode("utf-8")

        # 1. Unauthenticated request -> 401
        res_unauth = await client.post(mint_path, json=mint_payload)
        assert res_unauth.status_code == 401

        # 2. mcp-gateway service principal -> 403 Forbidden
        gw_hdr = create_internal_service_auth_header(
            principal="mcp-gateway",
            method="POST",
            path=mint_path,
            body_bytes=mint_body,
        )
        res_gw = await client.post(
            mint_path,
            content=mint_body,
            headers={"Content-Type": "application/json", "X-KB-Internal-Auth": gw_hdr},
        )
        assert res_gw.status_code == 403
        assert res_gw.json()["code"] == "FORBIDDEN"

        # 3. agent-runtime service principal -> 201 Created
        agt_hdr = create_internal_service_auth_header(
            principal="agent-runtime",
            method="POST",
            path=mint_path,
            body_bytes=mint_body,
        )
        res_agent = await client.post(
            mint_path,
            content=mint_body,
            headers={"Content-Type": "application/json", "X-KB-Internal-Auth": agt_hdr},
        )
        assert res_agent.status_code == 201
        data = res_agent.json()
        assert data["token"].startswith(EPHEMERAL_TOKEN_PREFIX)
        assert data["max_calls"] == 10
        assert "search_tickets" in data["allowed_tools"]
        minted_token = data["token"]

        # 4. Introspect through /internal/v1/mcp/introspect
        intro_path = "/internal/v1/mcp/introspect"
        intro_body = json.dumps(
            {"token": minted_token, "surface": "agent", "consume_call": False}
        ).encode("utf-8")
        intro_hdr = create_internal_service_auth_header(
            principal="mcp-gateway",
            method="POST",
            path=intro_path,
            body_bytes=intro_body,
        )
        res_intro = await client.post(
            intro_path,
            content=intro_body,
            headers={"Content-Type": "application/json", "X-KB-Internal-Auth": intro_hdr},
        )
        assert res_intro.status_code == 200
        intro_data = res_intro.json()
        assert intro_data["active"] is True
        assert intro_data["token_kind"] == "ephemeral"
        assert set(intro_data["allowed_tools"]) == {"search_tickets", "read_ticket"}

        # 5. Revoke by execution ID
        revoke_path = f"/internal/v1/mcp/ephemeral-tokens/by-execution/{exec_id}/revoke"
        revoke_hdr = create_internal_service_auth_header(
            principal="agent-runtime",
            method="POST",
            path=revoke_path,
            body_bytes=b"",
        )
        res_revoke = await client.post(
            revoke_path,
            headers={"X-KB-Internal-Auth": revoke_hdr},
        )
        assert res_revoke.status_code == 200
        assert res_revoke.json()["revoked_count"] == 1

        # 6. Introspect post-revoke -> inactive
        res_intro_revoked = await client.post(
            intro_path,
            content=intro_body,
            headers={"Content-Type": "application/json", "X-KB-Internal-Auth": intro_hdr},
        )
        assert res_intro_revoked.status_code == 200
        assert res_intro_revoked.json()["active"] is False


@pytest.mark.asyncio
async def test_case_6_concurrent_budget_exhaustion(db_session: AsyncSession) -> None:
    """Test Case 6: 10 concurrent consumption attempts against max_calls=5."""
    ws_id = await create_workspace(db_session, name="WS-Eph-6")
    user_id = await create_user(db_session, ws_id, handle="@user6", display_name="User 6")
    agent_id = await create_agent(db_session, ws_id, display_name="agent-6")
    proj_id = await create_project(db_session, ws_id, identifier="PRJ6", name="Project 6")
    exec_id = await seed_bound_execution(
        db_session,
        ws_id=ws_id,
        proj_id=proj_id,
        invoking_principal_id=user_id,
        agent_principal_id=agent_id,
    )

    _record, token = await mint_ephemeral_token(
        db_session,
        workspace_id=ws_id,
        execution_id=exec_id,
        invoking_principal_id=user_id,
        agent_principal_id=agent_id,
        project_id=proj_id,
        ttl_seconds=60,
        max_calls=5,
    )
    await db_session.commit()

    session_maker = async_sessionmaker(db_session.bind, expire_on_commit=False)

    async def _call_introspect() -> McpIntrospectionResult:
        async with session_maker() as s:
            return await introspect_and_consume_ephemeral_token(
                s,
                token=token,
                surface="agent",
                consume_call=True,
                tool_name="read_ticket",
            )

    results = await asyncio.gather(*[_call_introspect() for _ in range(10)])
    active_results = [r for r in results if r.active is True]
    failed_results = [r for r in results if r.active is False]

    assert len(active_results) == 5
    assert len(failed_results) == 5
    for r in failed_results:
        assert r.reason == "EPHEMERAL_CALL_BUDGET_EXCEEDED"


@pytest.mark.asyncio
async def test_case_7_edge_cases_and_branch_coverage(db_session: AsyncSession) -> None:
    """Test Case 7: Edge cases and branch coverage for ephemeral tokens service and routes."""
    ws_id = await create_workspace(db_session, name="WS-Eph-7")
    user_id = await create_user(db_session, ws_id, handle="@user7", display_name="User 7")
    agent_id = await create_agent(db_session, ws_id, display_name="agent-7")
    proj_id = await create_project(db_session, ws_id, identifier="PRJ7", name="Project 7")
    other_ws_id = await create_workspace(db_session, name="WS-Eph-7-Other")
    other_proj_id = await create_project(db_session, other_ws_id, identifier="OTH7", name="Other 7")
    exec_id = await seed_bound_execution(
        db_session,
        ws_id=ws_id,
        proj_id=proj_id,
        invoking_principal_id=user_id,
        agent_principal_id=agent_id,
    )

    # 1. Invalid invoking principal (non-existent)
    with pytest.raises(ProblemException) as exc1:
        await mint_ephemeral_token(
            db_session,
            workspace_id=ws_id,
            execution_id=exec_id,
            invoking_principal_id=uuid.uuid4(),
            agent_principal_id=agent_id,
            project_id=proj_id,
        )
    assert exc1.value.code == "INVALID_PRINCIPAL"

    # 2. Invalid project (wrong workspace)
    with pytest.raises(ProblemException) as exc2:
        await mint_ephemeral_token(
            db_session,
            workspace_id=ws_id,
            execution_id=exec_id,
            invoking_principal_id=user_id,
            agent_principal_id=agent_id,
            project_id=other_proj_id,
        )
    assert exc2.value.code == "INVALID_PROJECT"

    # 3. Mint valid token for edge testing
    _rec, token = await mint_ephemeral_token(
        db_session,
        workspace_id=ws_id,
        execution_id=exec_id,
        invoking_principal_id=user_id,
        agent_principal_id=agent_id,
        project_id=proj_id,
        allowed_tools=["search_tickets"],
        max_calls=1,
    )
    await db_session.commit()

    # 4. Unknown surface
    res_surf = await introspect_and_consume_ephemeral_token(
        db_session,
        token=token,
        surface="unknown",
        consume_call=False,
    )
    assert res_surf.active is False
    assert res_surf.reason == "SURFACE_KEY_MISMATCH"

    # 5. Unknown token
    fake_token = EPHEMERAL_TOKEN_PREFIX + "f" * 43
    res_fake = await introspect_and_consume_ephemeral_token(
        db_session,
        token=fake_token,
        surface="agent",
        consume_call=False,
    )
    assert res_fake.active is False
    assert res_fake.reason == "SURFACE_KEY_MISMATCH"

    res_fake_c = await introspect_and_consume_ephemeral_token(
        db_session,
        token=fake_token,
        surface="agent",
        consume_call=True,
        tool_name="search_tickets",
    )
    assert res_fake_c.active is False
    assert res_fake_c.reason == "NOT_FOUND"

    # 6. Consuming with no tool_name
    res_no_tool = await introspect_and_consume_ephemeral_token(
        db_session,
        token=token,
        surface="agent",
        consume_call=True,
        tool_name=None,
    )
    assert res_no_tool.active is False
    assert res_no_tool.reason == "EPHEMERAL_TOOL_FORBIDDEN"

    # 7. Consuming with tool not in allowed_tools of token (read_ticket not allowed)
    res_disallowed = await introspect_and_consume_ephemeral_token(
        db_session,
        token=token,
        surface="agent",
        consume_call=True,
        tool_name="read_ticket",
    )
    assert res_disallowed.active is False
    assert res_disallowed.reason == "EPHEMERAL_TOOL_FORBIDDEN"

    # 8. Deactivated principal
    await db_session.execute(
        text("UPDATE principals SET status = 'DISABLED' WHERE id = :p"),
        {"p": user_id},
    )
    await db_session.commit()

    res_inact_nc = await introspect_and_consume_ephemeral_token(
        db_session,
        token=token,
        surface="agent",
        consume_call=False,
    )
    assert res_inact_nc.active is False
    assert res_inact_nc.reason == "TOKEN_EXPIRED_OR_REVOKED"

    # Reset status back to ACTIVE
    await db_session.execute(
        text("UPDATE principals SET status = 'ACTIVE' WHERE id = :p"),
        {"p": user_id},
    )
    await db_session.commit()

    # 9. Exhaust budget then test non-consuming introspect with calls_used >= max_calls
    c1 = await introspect_and_consume_ephemeral_token(
        db_session,
        token=token,
        surface="agent",
        consume_call=True,
        tool_name="search_tickets",
    )
    assert c1.active is True
    assert c1.calls_used == 1

    res_budget_nc = await introspect_and_consume_ephemeral_token(
        db_session,
        token=token,
        surface="agent",
        consume_call=False,
    )
    assert res_budget_nc.active is False
    assert res_budget_nc.reason == "EPHEMERAL_CALL_BUDGET_EXCEEDED"

    # 10. Internal endpoint auth checks
    exec_id_2 = await seed_bound_execution(
        db_session,
        ws_id=ws_id,
        proj_id=proj_id,
        invoking_principal_id=user_id,
        agent_principal_id=agent_id,
    )
    await db_session.commit()

    settings = Settings()
    app = create_app(settings)
    app.state.session_factory = RLSSessionFactory(db_session.bind)  # type: ignore[arg-type]
    internal_app = create_internal_app(app)

    transport = httpx.ASGITransport(app=internal_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        revoke_path = f"/internal/v1/mcp/ephemeral-tokens/by-execution/{exec_id}/revoke"
        # Revoke unauthenticated
        res_rev_unauth = await client.post(revoke_path)
        assert res_rev_unauth.status_code == 401

        # Revoke with unverified X-SSL-Client-Cert header is rejected (401)
        res_rev_cert = await client.post(
            revoke_path,
            headers={"X-SSL-Client-Cert": "test-cert"},
        )
        assert res_rev_cert.status_code == 401

        # Revoke with role-bound internal HMAC auth header
        hmac_header = create_internal_service_auth_header(
            principal="mcp-gateway",
            method="POST",
            path=revoke_path,
            body_bytes=b"",
        )
        res_rev_hmac = await client.post(
            revoke_path,
            headers={"X-KB-Internal-Auth": hmac_header},
        )
        assert res_rev_hmac.status_code == 200

        # Mint with role-bound kanban-api HMAC signature
        mint_path = "/internal/v1/mcp/ephemeral-tokens"
        mint_body = json.dumps(
            {
                "workspace_id": str(ws_id),
                "execution_id": str(exec_id_2),
                "invoking_principal_id": str(user_id),
                "agent_principal_id": str(agent_id),
                "project_id": str(proj_id),
            }
        ).encode("utf-8")
        mint_hmac = create_internal_service_auth_header(
            principal="kanban-api",
            method="POST",
            path=mint_path,
            body_bytes=mint_body,
        )
        res_mint_cert = await client.post(
            mint_path,
            content=mint_body,
            headers={"Content-Type": "application/json", "X-KB-Internal-Auth": mint_hmac},
        )
        assert res_mint_cert.status_code == 201
