# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
# ruff: noqa: E501, PLR0915, SLF001, ERA001, D400, D415, RUF015, PLC0415, ARG001
"""Comprehensive unit and integration tests for consolidated /mcp/docs surface (S11.3, KAN-18)."""

from __future__ import annotations

import json
import uuid
from typing import TYPE_CHECKING, Any, cast

import httpx
import pytest
from sqlalchemy import select

from database.models import ObjectLink, ResourceAclEntry
from mcp.app import create_mcp_app
from mcp.settings import McpSettings
from mcp.surfaces.docs import DOCS_TOOL_NAMES, build_docs_registry

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from mcp.tests.docs.conftest import ApiEnv, SeededUser

pytestmark = pytest.mark.committed_db


async def _init_mcp_session(client: httpx.AsyncClient) -> str:
    """Initialize MCP session and return session ID."""
    resp = await client.post(
        "/mcp/docs",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "test-client", "version": "1.0"},
            },
        },
    )
    assert resp.status_code == 200, resp.text
    session_id = resp.headers.get("mcp-session-id")
    assert session_id is not None
    return str(session_id)


async def _call_mcp_tool(
    client: httpx.AsyncClient,
    session_id: str,
    tool_name: str,
    arguments: dict[str, Any],
    *,
    token: str | None = None,
) -> dict[str, Any]:
    """Call an MCP tool and return parsed result dict."""
    headers = {"mcp-session-id": session_id}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    resp = await client.post(
        "/mcp/docs",
        json={
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments,
            },
        },
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "result" in data, data
    res: dict[str, Any] = data["result"]
    return res


# =============================================================================
# TEST CASE 1: Positive Lifecycle & Verification Proofs
# =============================================================================


async def test_case_1_positive_knowledge_lifecycle(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Test Case 1: Positive lifecycle:

    - Create Doc "Architecture" via create tool
    - Create child Page under Architecture via create tool
    - Search by id (standard LOD) to get etag and version_seq
    - Surgical diff-patch via update tool with original_text and replacement_text
    - Search by id (full LOD) returns updated body, outline, and incremented version_seq
    - Hybrid search for "PKCE" returns the page with anchor
    - Create Sticky with 700-char body returning promotion_recommended: true
    - Add explicit ACL entry to sticky
    - Auto-promote Sticky to Doc via update(id=sticky_id, type="DOC") with row-for-row preserved ACLs
    - Sync inline links via update(id=page_key, links=["+ARCH-1", "-ARCH-1"])
    """
    user = await make_user("arch_author", workspace_role="WORKSPACE_ADMIN")
    as_principal(user)

    # 1. Initialize MCP app in-process with the kanban_app from api_env
    kanban_app = api_env.client._transport.app  # type: ignore[attr-defined]
    settings = McpSettings(mode="standalone_inprocess", auth_enabled=False)
    mcp_app = create_mcp_app(settings, kanban_app=kanban_app)
    transport = httpx.ASGITransport(app=mcp_app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as mcp_client:
        session_id = await _init_mcp_session(mcp_client)

        # 1. Create Doc "Architecture"
        res_create_doc = await _call_mcp_tool(
            mcp_client,
            session_id,
            "create",
            {
                "type": "DOC",
                "title": "Architecture",
                "content": "# Architecture\nOverview of system architecture.",
            },
        )
        assert res_create_doc["isError"] is False
        doc_yaml = res_create_doc["content"][0]["text"]
        assert "status: created" in doc_yaml
        assert "key: docs/architecture" in doc_yaml

        # 2. Create Page under Architecture
        res_create_page = await _call_mcp_tool(
            mcp_client,
            session_id,
            "create",
            {
                "type": "DOC",
                "parent": "docs/architecture",
                "title": "Auth Studio",
                "content": "## PKCE\nInitial PKCE content.\n\n## Overview\nAuth overview.",
            },
        )
        assert res_create_page["isError"] is False
        page_yaml = res_create_page["content"][0]["text"]
        assert "status: created" in page_yaml
        page_key = "docs/architecture/auth-studio"
        assert f"key: {page_key}" in page_yaml

        # 3. Read page via search tool to get etag and version_seq
        res_read_initial = await _call_mcp_tool(
            mcp_client,
            session_id,
            "search",
            {"id": page_key, "lod": "standard"},
        )
        assert res_read_initial["isError"] is False
        read_text1 = res_read_initial["content"][0]["text"]
        assert "version_seq: 1" in read_text1
        assert "kind: page" in read_text1
        # Extract etag
        etag_line = [line for line in read_text1.splitlines() if line.startswith("etag:")][0]
        etag1 = etag_line.split(":", 1)[1].strip().strip('"')

        # 4. Surgical diff-patch the ## PKCE section via update tool
        res_patch = await _call_mcp_tool(
            mcp_client,
            session_id,
            "update",
            {
                "id": page_key,
                "original_text": "Initial PKCE content.",
                "replacement_text": "Mandatory PKCE (S256), single-use 128-bit state parameter verification.",
                "if_match": etag1,
            },
        )
        assert res_patch["isError"] is False
        patch_yaml = res_patch["content"][0]["text"]
        assert "status: updated" in patch_yaml
        assert "version_seq: 2" in patch_yaml

        # 5. Verify search tool returns updated body and incremented version_seq
        res_read_final = await _call_mcp_tool(
            mcp_client,
            session_id,
            "search",
            {"id": page_key, "lod": "full", "include_tree": True},
        )
        assert res_read_final["isError"] is False
        read_text2 = res_read_final["content"][0]["text"]
        assert "version_seq: 2" in read_text2
        assert "Mandatory PKCE (S256)" in read_text2
        assert "outline:" in read_text2
        assert "access_manifest:" in read_text2

        # 6. Hybrid Search Knowledge for "PKCE"
        res_search = await _call_mcp_tool(
            mcp_client,
            session_id,
            "search",
            {"query": "PKCE", "type": "DOC"},
        )
        assert res_search["isError"] is False
        search_yaml = res_search["content"][0]["text"]
        assert "total:" in search_yaml
        assert "PKCE" in search_yaml or "Auth Studio" in search_yaml

        # 7. Create Project for Stickies
        create_proj_resp = await api_env.client.post(
            "/api/v1/projects",
            json={
                "identifier": "ARCH",
                "name": "Architecture Project",
            },
        )
        assert create_proj_resp.status_code == 201, create_proj_resp.text

        # 8. Create sticky with 700-char body -> promotion_recommended: true
        long_body = (
            "# Architecture Notes\n"
            "- Item 1: PKCE S256 verification\n"
            "- Item 2: Row-level security on PostgreSQLUniversalGraph\n"
            "- Item 3: Isolated MCP tool registries\n"
            + "Detailed explanation of architecture and product specifications. "
            * 10
        )
        assert len(long_body) >= 700

        res_sticky_create = await _call_mcp_tool(
            mcp_client,
            session_id,
            "create",
            {
                "type": "STICKY",
                "project": "ARCH",
                "title": "Architecture Notes",
                "content": long_body,
                "color": "amber",
            },
        )
        assert res_sticky_create["isError"] is False
        sticky_yaml = res_sticky_create["content"][0]["text"]
        assert "status: created" in sticky_yaml
        assert "promotion_recommended: true" in sticky_yaml
        sticky_id_line = [line for line in sticky_yaml.splitlines() if line.startswith("id:")][0]
        sticky_id = sticky_id_line.split(":", 1)[1].strip()

        # Add explicit ACL entry to sticky to test row-for-row preservation
        acl_entry = ResourceAclEntry(
            workspace_id=api_env.workspace_id,
            object_id=uuid.UUID(sticky_id),
            principal_id=user.id,
            effect="ALLOW",
            capability_mask=3,
            created_by_id=user.id,
        )
        api_env.seed.add(acl_entry)
        await api_env.seed.commit()

        # 9. Auto-promote Sticky to Doc via update(id=sticky_id, type="DOC")
        res_promote = await _call_mcp_tool(
            mcp_client,
            session_id,
            "update",
            {
                "id": sticky_id,
                "type": "DOC",
                "title": "Promoted Arch Notes",
            },
        )
        assert res_promote["isError"] is False
        promote_yaml = res_promote["content"][0]["text"]
        assert "status: promoted" in promote_yaml
        assert "link: PROMOTED_TO_DOC" in promote_yaml

        # Row-by-row ACL preservation audit
        sticky_acls = (
            (
                await api_env.seed.execute(
                    select(ResourceAclEntry).where(
                        ResourceAclEntry.object_id == uuid.UUID(sticky_id)
                    )
                )
            )
            .scalars()
            .all()
        )

        # Fetch promoted target doc
        sticky_row = (
            (
                await api_env.seed.execute(
                    select(ObjectLink).where(
                        ObjectLink.source_id == uuid.UUID(sticky_id),
                        ObjectLink.link_type == "PROMOTED_TO_DOC",
                    )
                )
            )
            .scalars()
            .first()
        )
        assert sticky_row is not None
        target_doc_id = sticky_row.target_id

        doc_acls = (
            (
                await api_env.seed.execute(
                    select(ResourceAclEntry).where(ResourceAclEntry.object_id == target_doc_id)
                )
            )
            .scalars()
            .all()
        )

        # Check row-for-row equality
        sticky_acl_tuples = {(a.principal_id, a.effect, a.capability_mask) for a in sticky_acls}
        doc_acl_tuples = {(a.principal_id, a.effect, a.capability_mask) for a in doc_acls}
        assert sticky_acl_tuples == doc_acl_tuples, "ACL rows must match row-by-row verbatim!"

        # Create issue under ARCH to link with
        issue_res = await api_env.client.post(
            "/api/v1/projects/ARCH/issues",
            json={
                "summary": "Auth Architecture Task",
            },
        )
        assert issue_res.status_code == 201, issue_res.text
        issue_key = issue_res.json()["key"]

        # 10. Sync inline links via update tool: add and remove
        res_link_add = await _call_mcp_tool(
            mcp_client,
            session_id,
            "update",
            {
                "id": page_key,
                "links": [f"+{issue_key}"],
            },
        )
        assert res_link_add["isError"] is False
        link_add_yaml = res_link_add["content"][0]["text"]
        assert "status: updated" in link_add_yaml
        assert "links:" in link_add_yaml

        # Now remove the link via delta syntax
        res_link_rem = await _call_mcp_tool(
            mcp_client,
            session_id,
            "update",
            {
                "id": page_key,
                "links": [f"-{issue_key}"],
            },
        )
        assert res_link_rem["isError"] is False
        link_rem_yaml = res_link_rem["content"][0]["text"]
        assert "status: updated" in link_rem_yaml


# =============================================================================
# TEST CASE 2: Security & Permissions
# =============================================================================


async def test_case_2_security_and_permission_isolation(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Test Case 2: Security invariants:

    - search of a page in a project the caller cannot VIEW -> NOT_FOUND byte-identical
    - kb_doc_ key on /mcp/agent -> 403 SURFACE_KEY_MISMATCH
    - create doc body with hidden display:none text stored without it
    - docs:read-only key calling update -> INSUFFICIENT_SCOPE
    """
    owner = await make_user("proj_owner", workspace_role="WORKSPACE_ADMIN")
    stranger = await make_user("stranger", workspace_role="WORKSPACE_MEMBER")

    # 1. Owner creates a doc in private project
    as_principal(owner)
    p_resp = await api_env.client.post(
        "/api/v1/projects", json={"identifier": "SEC", "name": "Secure Project"}
    )
    assert p_resp.status_code == 201

    d_resp = await api_env.client.post(
        "/api/v1/docs",
        json={
            "title": "Confidential",
            "body_markdown": "# Secret\nConfidential specs.",
            "project_id": p_resp.json()["id"],
        },
    )
    assert d_resp.status_code == 201
    doc_id = uuid.UUID(d_resp.json()["id"])

    # Attach explicit DENY (VIEW = 1) for stranger on doc
    from kanban.tests.security.helpers import add_acl_entry, rebuild_era

    await add_acl_entry(
        api_env.seed,
        api_env.workspace_id,
        doc_id,
        stranger.id,
        effect="DENY",
        capability_mask=1,
        created_by_id=owner.id,
    )
    await api_env.seed.commit()
    await rebuild_era(api_env.seed, api_env.workspace_id)
    await api_env.seed.commit()

    kanban_app = api_env.client._transport.app  # type: ignore[attr-defined]

    # Test stranger reading owner's doc -> NOT_FOUND byte-identical to missing path
    as_principal(stranger)
    settings = McpSettings(mode="standalone_inprocess", auth_enabled=False)
    mcp_app = create_mcp_app(settings, kanban_app=kanban_app)
    transport = httpx.ASGITransport(app=mcp_app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as mcp_client:
        sess = await _init_mcp_session(mcp_client)

        res_secret = await _call_mcp_tool(mcp_client, sess, "search", {"id": "docs/confidential"})
        assert res_secret["isError"] is True
        err_secret = res_secret["content"][0]["text"]
        assert "code: NOT_FOUND" in err_secret

        res_nonexistent = await _call_mcp_tool(
            mcp_client, sess, "search", {"id": "docs/missing-doc"}
        )
        err_nonexistent = res_nonexistent["content"][0]["text"]
        assert err_secret.replace("docs/confidential", "TARGET") == err_nonexistent.replace(
            "docs/missing-doc", "TARGET"
        ), "Anti-enumeration: unauthorized and missing must follow byte-identical error structure!"

    # 2. Surface Key Mismatch: kb_doc_ key presented on /mcp/agent -> 403 SURFACE_KEY_MISMATCH
    auth_settings = McpSettings(mode="standalone_inprocess", auth_enabled=True)
    auth_mcp_app = create_mcp_app(auth_settings, kanban_app=kanban_app)
    auth_transport = httpx.ASGITransport(app=auth_mcp_app)

    async with httpx.AsyncClient(transport=auth_transport, base_url="http://test") as auth_client:
        doc_token = "kb_doc_" + "a" * 43
        agent_init = await auth_client.post(
            "/mcp/agent",
            headers={"Authorization": f"Bearer {doc_token}"},
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
        )
        assert agent_init.status_code == 403
        assert agent_init.json() == {"error": "SURFACE_KEY_MISMATCH"}

    # 3. create doc body with hidden display:none text stored without it
    as_principal(owner)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as mcp_client:
        sess = await _init_mcp_session(mcp_client)
        payload_with_hidden = (
            "# Safe Document\n"
            'Visible text <span style="display:none">ATTACK_EXFIL_PAYLOAD</span> continues here.'
        )
        res_create = await _call_mcp_tool(
            mcp_client,
            sess,
            "create",
            {"type": "DOC", "title": "Sanitization Check", "content": payload_with_hidden},
        )
        assert res_create["isError"] is False

        # Read back document via search
        res_read = await _call_mcp_tool(
            mcp_client,
            sess,
            "search",
            {"id": "docs/sanitization-check", "lod": "standard"},
        )
        assert res_read["isError"] is False
        body_read = res_read["content"][0]["text"]
        assert "ATTACK_EXFIL_PAYLOAD" not in body_read, (
            "Hidden display:none payload must be pruned!"
        )

    # 4. Scope enforcement: docs:read-only caller calling update -> INSUFFICIENT_SCOPE
    def mock_docs_read_introspect(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "active": True,
                "principal_id": str(owner.id),
                "workspace_id": str(api_env.workspace_id),
                "surface": "docs",
                "scopes": ["docs:read"],
            },
        )

    read_only_transport = httpx.MockTransport(mock_docs_read_introspect)
    read_only_settings = McpSettings(mode="standalone_inprocess", auth_enabled=True)
    read_only_app = create_mcp_app(
        read_only_settings, kanban_app=kanban_app, transport=read_only_transport
    )
    doc_read_token = "kb_doc_" + "b" * 43

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=read_only_app), base_url="http://test"
    ) as ro_client:
        init_resp = await ro_client.post(
            "/mcp/docs",
            headers={"Authorization": f"Bearer {doc_read_token}"},
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "test-client", "version": "1.0"},
                },
            },
        )
        assert init_resp.status_code == 200
        ro_session_id = init_resp.headers["mcp-session-id"]

        call_resp = await ro_client.post(
            "/mcp/docs",
            headers={
                "Authorization": f"Bearer {doc_read_token}",
                "Mcp-Session-Id": ro_session_id,
            },
            json={
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "update",
                    "arguments": {"id": "docs/sanitization-check", "title": "Updated Title"},
                },
            },
        )
        assert call_resp.status_code == 200
        res_data = call_resp.json()
        assert res_data["result"]["isError"] is True
        assert "INSUFFICIENT_SCOPE" in res_data["result"]["content"][0]["text"]


# =============================================================================
# TEST CASE 4: Boundary & Surgical Diff-Patch Validation
# =============================================================================


async def test_case_4_boundary_and_validation(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Test Case 4: Boundary validations:

    - sticky with bad color -> VALIDATION_FAILED
    - sticky with parent -> VALIDATION_FAILED
    - sticky body 65,537 bytes -> VALIDATION_FAILED
    - promote twice -> ALREADY_PROMOTED
    - stale if_match -> CONFLICT_ETAG
    - diff-patch target not found -> PATCH_TARGET_NOT_FOUND with closest_match
    - diff-patch ambiguous target -> PATCH_TARGET_AMBIGUOUS with line_hints
    - page at depth 10 accepts no child -> VALIDATION_FAILED
    """
    user = await make_user("boundary_user", workspace_role="WORKSPACE_ADMIN")
    as_principal(user)

    p_resp = await api_env.client.post(
        "/api/v1/projects", json={"identifier": "BND", "name": "Boundary Project"}
    )
    assert p_resp.status_code == 201

    kanban_app = api_env.client._transport.app  # type: ignore[attr-defined]
    settings = McpSettings(mode="standalone_inprocess", auth_enabled=False)
    mcp_app = create_mcp_app(settings, kanban_app=kanban_app)
    transport = httpx.ASGITransport(app=mcp_app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as mcp_client:
        sess = await _init_mcp_session(mcp_client)

        # 1. Sticky color: "red" -> VALIDATION_FAILED
        res_bad_color = await _call_mcp_tool(
            mcp_client,
            sess,
            "create",
            {"type": "STICKY", "project": "BND", "title": "Bad Color", "color": "red"},
        )
        assert res_bad_color["isError"] is True
        assert "code: VALIDATION_FAILED" in res_bad_color["content"][0]["text"]

        # 2. Sticky with parent -> VALIDATION_FAILED
        res_bad_parent = await _call_mcp_tool(
            mcp_client,
            sess,
            "create",
            {
                "type": "STICKY",
                "project": "BND",
                "title": "Bad Parent",
                "parent": "docs/architecture",
            },
        )
        assert res_bad_parent["isError"] is True
        assert "code: VALIDATION_FAILED" in res_bad_parent["content"][0]["text"]

        # 3. Sticky body 65,537 bytes -> VALIDATION_FAILED
        res_oversized = await _call_mcp_tool(
            mcp_client,
            sess,
            "create",
            {"type": "STICKY", "project": "BND", "title": "Big", "content": "x" * 65537},
        )
        assert res_oversized["isError"] is True
        assert "code: VALIDATION_FAILED" in res_oversized["content"][0]["text"]

        # 4. Create normal sticky, promote twice -> ALREADY_PROMOTED
        res_sticky = await _call_mcp_tool(
            mcp_client,
            sess,
            "create",
            {
                "type": "STICKY",
                "project": "BND",
                "title": "Normal Note",
                "content": "Normal note",
                "color": "sky",
            },
        )
        sticky_yaml = res_sticky["content"][0]["text"]
        s_id = (
            [line for line in sticky_yaml.splitlines() if line.startswith("id:")][0]
            .split(":", 1)[1]
            .strip()
        )

        # Promote 1st time
        res_promote1 = await _call_mcp_tool(
            mcp_client,
            sess,
            "update",
            {"id": s_id, "type": "DOC", "title": "Promoted Once"},
        )
        assert res_promote1["isError"] is False

        # Promote 2nd time -> ALREADY_PROMOTED
        res_promote2 = await _call_mcp_tool(
            mcp_client,
            sess,
            "update",
            {"id": s_id, "type": "DOC", "title": "Promote Again"},
        )
        assert res_promote2["isError"] is True
        assert "code: ALREADY_PROMOTED" in res_promote2["content"][0]["text"]

        # 5. Create doc to test diff-patch errors and stale if_match
        res_doc = await _call_mcp_tool(
            mcp_client,
            sess,
            "create",
            {
                "type": "DOC",
                "title": "Boundary Doc",
                "content": "# Boundary Doc\nLine one alpha.\nLine two duplicate.\nLine three duplicate.\nLine four omega.",
            },
        )
        assert res_doc["isError"] is False
        doc_res_text = res_doc["content"][0]["text"]
        bnd_etag = (
            [line for line in doc_res_text.splitlines() if line.startswith("etag:")][0]
            .split(":", 1)[1]
            .strip()
            .strip('"')
        )

        # 5a. Stale if_match -> CONFLICT_ETAG
        res_stale = await _call_mcp_tool(
            mcp_client,
            sess,
            "update",
            {
                "id": "docs/boundary-doc",
                "original_text": "Line one alpha.",
                "replacement_text": "Line one beta.",
                "if_match": "0" * 64,
            },
        )
        assert res_stale["isError"] is True
        assert "code: CONFLICT_ETAG" in res_stale["content"][0]["text"]

        # 5b. Diff-patch count == 0 -> PATCH_TARGET_NOT_FOUND with closest_match
        res_not_found = await _call_mcp_tool(
            mcp_client,
            sess,
            "update",
            {
                "id": "docs/boundary-doc",
                "original_text": "Line one mispelled alpha.",
                "replacement_text": "Line one beta.",
                "if_match": bnd_etag,
            },
        )
        assert res_not_found["isError"] is True
        err_not_found = res_not_found["content"][0]["text"]
        assert "code: PATCH_TARGET_NOT_FOUND" in err_not_found
        assert "closest_match:" in err_not_found

        # 5c. Diff-patch count > 1 -> PATCH_TARGET_AMBIGUOUS with line_hints
        res_ambiguous = await _call_mcp_tool(
            mcp_client,
            sess,
            "update",
            {
                "id": "docs/boundary-doc",
                "original_text": "duplicate.",
                "replacement_text": "replacement.",
            },
        )
        assert res_ambiguous["isError"] is True
        err_ambig = res_ambiguous["content"][0]["text"]
        assert "code: PATCH_TARGET_AMBIGUOUS" in err_ambig
        assert "line_hints:" in err_ambig

        # 6. Page at depth 10 accepts no child -> VALIDATION_FAILED
        res_deep = await _call_mcp_tool(
            mcp_client,
            sess,
            "create",
            {
                "type": "DOC",
                "parent": "docs/l1/l2/l3/l4/l5/l6/l7/l8/l9/l10",
                "title": "Depth 11",
                "content": "Too deep",
            },
        )
        assert res_deep["isError"] is True
        assert "code: VALIDATION_FAILED" in res_deep["content"][0]["text"]


# =============================================================================
# TEST CASE 5: Isolation & Token Budget
# =============================================================================


def test_case_5_isolation_and_token_budget() -> None:
    """Test Case 5:

    - /mcp/docs tools/list returns exactly the 3 registered names (search, create, update)
    - schema <= 1,350 approximate tokens
    """
    registry = build_docs_registry()
    specs = registry.list_specs()
    tool_names = [s.name for s in specs]

    assert tool_names == list(DOCS_TOOL_NAMES), f"Expected {DOCS_TOOL_NAMES}, got {tool_names}"
    assert set(tool_names) == {"search", "create", "update"}
    assert "read_doc" not in tool_names
    assert "upsert_doc" not in tool_names

    tools_list = [
        {
            "name": s.name,
            "description": s.description,
            "inputSchema": s.input_schema,
        }
        for s in specs
    ]
    raw_json = json.dumps({"tools": tools_list})
    approx_tokens = len(raw_json) // 4
    assert approx_tokens <= 1350, f"Token budget exceeded: {approx_tokens} > 1350"


# =============================================================================
# TEST CASE 6: Handler Exhaustive Branches & Coverage Booster
# =============================================================================


async def test_case_6_handler_exhaustive_branches(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Test exhaustive branches across all 3 docs tools for >=95% coverage."""
    user = await make_user("branch_user", workspace_role="WORKSPACE_ADMIN")
    as_principal(user)

    p_resp = await api_env.client.post(
        "/api/v1/projects", json={"identifier": "EXH", "name": "Exhaustive Project"}
    )
    assert p_resp.status_code == 201

    kanban_app = api_env.client._transport.app  # type: ignore[attr-defined]
    settings = McpSettings(mode="standalone_inprocess", auth_enabled=False)
    mcp_app = create_mcp_app(settings, kanban_app=kanban_app)
    transport = httpx.ASGITransport(app=mcp_app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as mcp_client:
        sess = await _init_mcp_session(mcp_client)

        # -------------------------------------------------------------
        # search branches
        # -------------------------------------------------------------
        # id="help"
        h_resp = await _call_mcp_tool(mcp_client, sess, "search", {"id": "help"})
        assert h_resp["isError"] is False
        assert "tool: search" in h_resp["content"][0]["text"]

        # project listing with ALL
        l_resp = await _call_mcp_tool(mcp_client, sess, "search", {"project": "EXH", "type": "ALL"})
        assert l_resp["isError"] is False
        assert "project: EXH" in l_resp["content"][0]["text"]

        # project listing with DOC and include_tree
        tree_resp = await _call_mcp_tool(
            mcp_client, sess, "search", {"project": "EXH", "type": "DOC", "include_tree": True}
        )
        assert tree_resp["isError"] is False

        # workspace listing (no project, no id, no query)
        ws_resp = await _call_mcp_tool(mcp_client, sess, "search", {})
        assert ws_resp["isError"] is False

        # query validation: empty, too long, bad type
        q_empty = await _call_mcp_tool(mcp_client, sess, "search", {"query": ""})
        assert q_empty["isError"] is True

        q_long = await _call_mcp_tool(mcp_client, sess, "search", {"query": "a" * 501})
        assert q_long["isError"] is True

        q_bad_type = await _call_mcp_tool(
            mcp_client, sess, "search", {"query": "test", "type": "invalid"}
        )
        assert q_bad_type["isError"] is True

        # query with STICKY
        q_valid = await _call_mcp_tool(
            mcp_client,
            sess,
            "search",
            {"query": "test", "type": "STICKY", "project": "EXH", "limit": 10},
        )
        assert q_valid["isError"] is False

        # search by non-existent UUID -> NOT_FOUND
        missing_uuid = str(uuid.uuid4())
        miss_resp = await _call_mcp_tool(mcp_client, sess, "search", {"id": missing_uuid})
        assert miss_resp["isError"] is True
        assert "NOT_FOUND" in miss_resp["content"][0]["text"]

        # -------------------------------------------------------------
        # create branches
        # -------------------------------------------------------------
        # invalid type
        bad_type = await _call_mcp_tool(
            mcp_client, sess, "create", {"type": "INVALID", "title": "T"}
        )
        assert bad_type["isError"] is True

        # missing title
        miss_title = await _call_mcp_tool(mcp_client, sess, "create", {"type": "DOC", "title": ""})
        assert miss_title["isError"] is True

        # sticky missing project
        miss_proj = await _call_mcp_tool(
            mcp_client, sess, "create", {"type": "STICKY", "title": "T"}
        )
        assert miss_proj["isError"] is True

        # sticky with links and valid color
        stk_ok = await _call_mcp_tool(
            mcp_client,
            sess,
            "create",
            {
                "type": "STICKY",
                "project": "EXH",
                "title": "Branch Sticky",
                "content": "Sticky details here",
                "color": "mint",
                "links": ["EXH-1"],
            },
        )
        assert stk_ok["isError"] is False
        stk_yaml = stk_ok["content"][0]["text"]
        stk_id = (
            [line for line in stk_yaml.splitlines() if line.startswith("id:")][0]
            .split(":", 1)[1]
            .strip()
        )

        # search sticky by ID with summary and full LOD
        stk_sum = await _call_mcp_tool(mcp_client, sess, "search", {"id": stk_id, "lod": "summary"})
        assert stk_sum["isError"] is False
        assert "kind: sticky" in stk_sum["content"][0]["text"]

        stk_full = await _call_mcp_tool(mcp_client, sess, "search", {"id": stk_id, "lod": "full"})
        assert stk_full["isError"] is False
        assert "capabilities:" in stk_full["content"][0]["text"]

        # create doc with body > 1 MiB -> VALIDATION_FAILED
        from mcp.errors import KbMcpError, McpErrorCode
        from mcp.surfaces.docs.create import create_handler

        with pytest.raises(KbMcpError) as exc_large:
            await create_handler(
                {"type": "DOC", "title": "Large Doc", "content": "x" * 1_048_577},
                client=cast("Any", api_env.client),
            )
        assert exc_large.value.code == McpErrorCode.VALIDATION_FAILED

        # create doc with inline links
        doc_ok = await _call_mcp_tool(
            mcp_client,
            sess,
            "create",
            {
                "type": "DOC",
                "title": "Exhaustive Doc",
                "project": "EXH",
                "content": "# Exhaustive Doc\nInitial paragraph.",
                "links": ["EXH-1", "VERIFIED_BY_DOC:EXH-1"],
            },
        )
        assert doc_ok["isError"] is False
        doc_yaml = doc_ok["content"][0]["text"]
        doc_etag = (
            [line for line in doc_yaml.splitlines() if line.startswith("etag:")][0]
            .split(":", 1)[1]
            .strip()
            .strip('"')
        )

        # -------------------------------------------------------------
        # update branches
        # -------------------------------------------------------------
        # missing id
        up_noid = await _call_mcp_tool(mcp_client, sess, "update", {"id": ""})
        assert up_noid["isError"] is True

        # title length > 200
        up_badtitle = await _call_mcp_tool(
            mcp_client, sess, "update", {"id": "docs/exhaustive-doc", "title": "x" * 201}
        )
        assert up_badtitle["isError"] is True

        # sticky invalid color
        stk_badcol = await _call_mcp_tool(
            mcp_client, sess, "update", {"id": stk_id, "color": "invalid"}
        )
        assert stk_badcol["isError"] is True

        # update sticky color and diff-patch
        stk_up = await _call_mcp_tool(
            mcp_client,
            sess,
            "update",
            {
                "id": stk_id,
                "color": "coral",
                "original_text": "details here",
                "replacement_text": "updated details",
            },
        )
        assert stk_up["isError"] is False
        assert "color: coral" in stk_up["content"][0]["text"]

        # update sticky content directly
        stk_content = await _call_mcp_tool(
            mcp_client,
            sess,
            "update",
            {
                "id": stk_id,
                "content": "# New Sticky Title\nUpdated full content",
            },
        )
        assert stk_content["isError"] is False

        # update sticky links with dict syntax
        stk_links_dict = await _call_mcp_tool(
            mcp_client,
            sess,
            "update",
            {
                "id": stk_id,
                "links": {"add": ["EXH-1"], "remove": ["EXH-1"]},
            },
        )
        assert stk_links_dict["isError"] is False

        # update doc title and content directly with valid if_match
        doc_update_ok = await _call_mcp_tool(
            mcp_client,
            sess,
            "update",
            {
                "id": "docs/exhaustive-doc",
                "title": "Renamed Exhaustive Doc",
                "content": "# Renamed Doc\nAll new content here.",
                "if_match": doc_etag,
                "links": ["-EXH-1"],
            },
        )
        assert doc_update_ok["isError"] is False
        assert "title: Renamed Exhaustive Doc" in doc_update_ok["content"][0]["text"]

        # auto-promote sticky to child page under docs/exhaustive-doc
        stk_child = await _call_mcp_tool(
            mcp_client,
            sess,
            "create",
            {
                "type": "STICKY",
                "project": "EXH",
                "title": "Child Sticky",
                "content": "Content to be child page",
            },
        )
        child_stk_id = (
            [
                line
                for line in stk_child["content"][0]["text"].splitlines()
                if line.startswith("id:")
            ][0]
            .split(":", 1)[1]
            .strip()
        )

        promote_child = await _call_mcp_tool(
            mcp_client,
            sess,
            "update",
            {
                "id": child_stk_id,
                "type": "DOC",
                "parent": "docs/exhaustive-doc",
                "title": "Promoted Child Page",
                "links": ["+EXH-1"],
            },
        )
        assert promote_child["isError"] is False
        assert "status: promoted" in promote_child["content"][0]["text"]

        # Additional search coverage
        srch_sum = await _call_mcp_tool(
            mcp_client, sess, "search", {"id": "docs/exhaustive-doc", "lod": "summary"}
        )
        assert srch_sum["isError"] is False

        srch_std = await _call_mcp_tool(
            mcp_client, sess, "search", {"id": "docs/exhaustive-doc", "lod": "standard"}
        )
        assert srch_std["isError"] is False

        srch_full_tree = await _call_mcp_tool(
            mcp_client,
            sess,
            "search",
            {"id": "docs/exhaustive-doc", "lod": "full", "include_tree": True},
        )
        assert srch_full_tree["isError"] is False

        srch_stk_list = await _call_mcp_tool(
            mcp_client, sess, "search", {"project": "EXH", "type": "STICKY"}
        )
        assert srch_stk_list["isError"] is False

        srch_doc_list = await _call_mcp_tool(
            mcp_client, sess, "search", {"project": "EXH", "type": "DOC"}
        )
        assert srch_doc_list["isError"] is False

        srch_missing_doc = await _call_mcp_tool(
            mcp_client, sess, "search", {"id": "docs/nonexistent-doc"}
        )
        assert srch_missing_doc["isError"] is True
        assert "NOT_FOUND" in srch_missing_doc["content"][0]["text"]

        # Additional create coverage
        cr_empty_doc = await _call_mcp_tool(
            mcp_client, sess, "create", {"type": "DOC", "title": "Empty Doc"}
        )
        assert cr_empty_doc["isError"] is False

        cr_child_page = await _call_mcp_tool(
            mcp_client,
            sess,
            "create",
            {
                "type": "DOC",
                "parent": "docs/exhaustive-doc",
                "title": "Direct Child Page",
                "content": "Page content here",
            },
        )
        assert cr_child_page["isError"] is False
        page_ref = "docs/exhaustive-doc/direct-child-page"

        cr_bare_stk = await _call_mcp_tool(
            mcp_client, sess, "create", {"type": "STICKY", "project": "EXH", "title": "Bare Sticky"}
        )
        assert cr_bare_stk["isError"] is False

        # Additional update coverage
        up_page_patch = await _call_mcp_tool(
            mcp_client,
            sess,
            "update",
            {
                "id": page_ref,
                "original_text": "Page content",
                "replacement_text": "Patched page content",
            },
        )
        assert up_page_patch["isError"] is False
        assert "status: updated" in up_page_patch["content"][0]["text"]

        up_page_title = await _call_mcp_tool(
            mcp_client,
            sess,
            "update",
            {
                "id": page_ref,
                "title": "Renamed Direct Child Page",
            },
        )
        assert up_page_title["isError"] is False

        up_stk_empty_link = await _call_mcp_tool(
            mcp_client,
            sess,
            "update",
            {
                "id": stk_id,
                "links": [""],
            },
        )
        assert up_stk_empty_link["isError"] is False

        # Direct helper functions verification
        from mcp.surfaces.docs.create import (
            _parse_link_target as parse_create_link,
        )
        from mcp.surfaces.docs.create import (
            create_docs_create_tool,
        )
        from mcp.surfaces.docs.search import (
            _extract_headings,
            _extract_sticky_title,
            _format_access_pill,
            create_docs_search_tool,
        )
        from mcp.surfaces.docs.update import (
            _diff_patch_content,
            _find_closest_matches,
            _find_line_hints,
            create_docs_update_tool,
        )
        from mcp.surfaces.docs.update import (
            _parse_link_target as parse_update_link,
        )

        md_test = (
            "# Heading 1\n"
            "```python\n"
            "# Code comment\n"
            "```\n"
            "~~~bash\n"
            "# Bash comment\n"
            "~~~\n"
            "## Heading 2\n"
        )
        extracted = _extract_headings(md_test)
        assert len(extracted) == 2
        assert extracted[0]["text"] == "Heading 1"
        assert extracted[1]["text"] == "Heading 2"

        assert _format_access_pill(None) == "project"
        assert _format_access_pill({"scope": "WORKSPACE"}) == "workspace"
        assert _extract_sticky_title("", "mint") == "Sticky mint"
        assert _extract_sticky_title("First line", "amber") == "First line"

        t_c, lt_c = parse_create_link("DERIVED_FROM_STICKY:STK-1")
        assert t_c == "STK-1"
        assert lt_c == "DERIVED_FROM_STICKY"

        t_u, lt_u = parse_update_link("VERIFIED_BY_DOC:DOC-9")
        assert t_u == "DOC-9"
        assert lt_u == "VERIFIED_BY_DOC"

        assert _find_closest_matches("", "target") == []
        assert _find_line_hints("line 1\ntarget\nline 3\ntarget", "target") == [2, 4]

        with pytest.raises(KbMcpError) as exc_etag:
            _diff_patch_content("body", "orig", "rep", "sha1", "sha2")
        assert exc_etag.value.code == McpErrorCode.CONFLICT_ETAG

        # Verify tool builders
        assert create_docs_search_tool().name == "search"
        assert create_docs_create_tool().name == "create"
        assert create_docs_update_tool().name == "update"
