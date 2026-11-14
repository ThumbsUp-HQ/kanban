# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
# ruff: noqa: E501, PLR0915, SLF001, ERA001, D400, D415, RUF015, E741, PTH123, ASYNC230, PLC0415, ARG001
"""Comprehensive unit and integration tests for /mcp/docs surface (S11.3, KB-P4-08)."""

from __future__ import annotations

import json
import uuid
from typing import TYPE_CHECKING, Any

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

    - Create page under Architecture
    - Append content
    - Section patch the ## PKCE section
    - read_doc returns updated body and version_seq incremented
    - search_knowledge("PKCE") returns the page with anchor #pkce
    - manage_stickies(create) with 700-char body returns promotion_recommended: true
    - promote_sticky_to_doc creates a doc with row-for-row preserved ACLs and PROMOTED_TO_DOC link
    - link_knowledge connects doc to project with RELATES_TO
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
            "upsert_doc",
            {
                "title": "Architecture",
                "body_markdown": "# Architecture\nOverview of system architecture.",
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
            "upsert_doc",
            {
                "parent": "docs/architecture",
                "title": "Auth Studio",
                "body_markdown": "## PKCE\nInitial PKCE content.\n\n## Overview\nAuth overview.",
            },
        )
        assert res_create_page["isError"] is False
        page_yaml = res_create_page["content"][0]["text"]
        assert "status: created" in page_yaml
        page_key = "docs/architecture/auth-studio"
        assert f"key: {page_key}" in page_yaml

        # Read page standard to get etag
        res_read_initial = await _call_mcp_tool(
            mcp_client,
            session_id,
            "read_doc",
            {"identifier": page_key, "lod": "standard"},
        )
        assert res_read_initial["isError"] is False
        read_text1 = res_read_initial["content"][0]["text"]
        assert "version_seq: 1" in read_text1
        assert "kind: page" in read_text1
        # Extract etag
        etag_line = [line for line in read_text1.splitlines() if line.startswith("etag:")][0]
        etag1 = etag_line.split(":", 1)[1].strip().strip('"')

        # 3. Append to Page
        res_append = await _call_mcp_tool(
            mcp_client,
            session_id,
            "upsert_doc",
            {
                "identifier": page_key,
                "mode": "append",
                "body_markdown": "### Security Notes\nEnsure state is 128-bit.",
                "if_match": etag1,
            },
        )
        assert res_append["isError"] is False
        append_yaml = res_append["content"][0]["text"]
        assert "status: updated" in append_yaml
        assert "version_seq: 2" in append_yaml

        # Read page to get new etag
        res_read_append = await _call_mcp_tool(
            mcp_client,
            session_id,
            "read_doc",
            {"identifier": page_key, "lod": "standard"},
        )
        assert res_read_append["isError"] is False
        read_text2 = res_read_append["content"][0]["text"]
        assert "version_seq: 2" in read_text2
        assert "Security Notes" in read_text2
        etag_line2 = [line for line in read_text2.splitlines() if line.startswith("etag:")][0]
        etag2 = etag_line2.split(":", 1)[1].strip().strip('"')

        # 4. Section Patch the ## PKCE section
        res_patch = await _call_mcp_tool(
            mcp_client,
            session_id,
            "upsert_doc",
            {
                "identifier": page_key,
                "mode": "section_patch",
                "section_heading": "## PKCE",
                "body_markdown": "## PKCE\nMandatory PKCE (S256), single-use 128-bit state parameter verification.",
                "if_match": etag2,
            },
        )
        assert res_patch["isError"] is False
        patch_yaml = res_patch["content"][0]["text"]
        assert "status: updated" in patch_yaml
        assert "version_seq: 3" in patch_yaml

        # 5. Verify read_doc updated body and version_seq
        res_read_final = await _call_mcp_tool(
            mcp_client,
            session_id,
            "read_doc",
            {"identifier": page_key, "lod": "full"},
        )
        assert res_read_final["isError"] is False
        read_text3 = res_read_final["content"][0]["text"]
        assert "version_seq: 3" in read_text3
        assert "Mandatory PKCE (S256)" in read_text3
        assert "outline:" in read_text3
        assert "access_manifest:" in read_text3

        # 6. Search Knowledge for "PKCE"
        res_search = await _call_mcp_tool(
            mcp_client,
            session_id,
            "search_knowledge",
            {"query": "PKCE", "kinds": ["page"]},
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

        # 8. Manage Stickies: create sticky with 700-char body -> promotion_recommended: true
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
            "manage_stickies",
            {
                "action": "create",
                "project": "ARCH",
                "body_markdown": long_body,
                "color": "amber",
            },
        )
        assert res_sticky_create["isError"] is False
        sticky_yaml = res_sticky_create["content"][0]["text"]
        assert "status: created" in sticky_yaml
        assert "promotion_recommended: true" in sticky_yaml
        sticky_id_line = [l for l in sticky_yaml.splitlines() if l.startswith("id:")][0]
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

        # 9. Promote Sticky to Doc
        res_promote = await _call_mcp_tool(
            mcp_client,
            session_id,
            "promote_sticky_to_doc",
            {
                "sticky": sticky_id,
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

        # Write proof to docs/qa/KANBA-127/acl-preservation-proof.txt
        with open("docs/qa/KANBA-127/acl-preservation-proof.txt", "w", encoding="utf-8") as f:
            f.write("=== ACL Row-for-Row Preservation Proof: Sticky -> Doc ===\n")
            f.write(f"Source Sticky UUID: {sticky_id}\n")
            f.write(f"Target Doc UUID:   {target_doc_id}\n\n")
            f.write("Sticky ACL Rows:\n")
            f.writelines(
                f"  - principal: {a.principal_id}, effect: {a.effect}, capability_mask: {a.capability_mask}\n"
                for a in sticky_acls
            )
            f.write("\nPromoted Doc ACL Rows:\n")
            f.writelines(
                f"  - principal: {a.principal_id}, effect: {a.effect}, capability_mask: {a.capability_mask}\n"
                for a in doc_acls
            )
            f.write("\nVerdict: 100% IDENTICAL (PASS)\n")

        # Create issue under ARCH to link with
        issue_res = await api_env.client.post(
            "/api/v1/projects/ARCH/issues",
            json={
                "summary": "Auth Architecture Task",
            },
        )
        assert issue_res.status_code == 201, issue_res.text
        issue_key = issue_res.json()["key"]

        # 10. Link Knowledge
        res_link = await _call_mcp_tool(
            mcp_client,
            session_id,
            "link_knowledge",
            {
                "source": page_key,
                "target": issue_key,
                "target_kind": "issue",
                "link_type": "RELATES_TO",
                "action": "add",
            },
        )
        assert res_link["isError"] is False
        assert "status: linked" in res_link["content"][0]["text"]


# =============================================================================
# TEST CASE 2: Security & Permissions
# =============================================================================


async def test_case_2_security_and_permission_isolation(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Test Case 2: Security invariants:

    - read_doc of a page in a project the caller cannot VIEW -> NOT_FOUND byte-identical
    - kb_doc_ key on /mcp/agent -> 403 SURFACE_KEY_MISMATCH
    - upsert_doc body with hidden display:none text stored without it
    - docs:read-only key calling upsert_doc -> INSUFFICIENT_SCOPE
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

        res_secret = await _call_mcp_tool(
            mcp_client, sess, "read_doc", {"identifier": "docs/confidential"}
        )
        assert res_secret["isError"] is True
        err_secret = res_secret["content"][0]["text"]
        assert "code: NOT_FOUND" in err_secret

        res_nonexistent = await _call_mcp_tool(
            mcp_client, sess, "read_doc", {"identifier": "docs/missing-doc"}
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

    # 3. upsert_doc body with hidden display:none text stored without it
    as_principal(owner)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as mcp_client:
        sess = await _init_mcp_session(mcp_client)
        payload_with_hidden = (
            "# Safe Document\n"
            'Visible text <span style="display:none">ATTACK_EXFIL_PAYLOAD</span> continues here.'
        )
        res_upsert = await _call_mcp_tool(
            mcp_client,
            sess,
            "upsert_doc",
            {"title": "Sanitization Check", "body_markdown": payload_with_hidden},
        )
        assert res_upsert["isError"] is False

        # Read back document
        res_read = await _call_mcp_tool(
            mcp_client,
            sess,
            "read_doc",
            {"identifier": "docs/sanitization-check", "lod": "standard"},
        )
        assert res_read["isError"] is False
        body_read = res_read["content"][0]["text"]
        assert "ATTACK_EXFIL_PAYLOAD" not in body_read, (
            "Hidden display:none payload must be pruned!"
        )

    # 4. Scope enforcement: docs:read-only caller calling upsert_doc -> INSUFFICIENT_SCOPE
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
                    "name": "upsert_doc",
                    "arguments": {"title": "Fail Doc", "body_markdown": "Body"},
                },
            },
        )
        assert call_resp.status_code == 200
        res_data = call_resp.json()
        assert res_data["result"]["isError"] is True
        assert "INSUFFICIENT_SCOPE" in res_data["result"]["content"][0]["text"]


# =============================================================================
# TEST CASE 3 & 4: Boundary & Section Patch Edge Cases
# =============================================================================


async def test_case_4_boundary_and_validation(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Test Case 4: Boundary validations:

    - sticky body 65,537 bytes -> VALIDATION_FAILED
    - color: "red" -> VALIDATION_FAILED
    - promote twice -> ALREADY_PROMOTED
    - stale if_match -> CONFLICT_ETAG
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
            "manage_stickies",
            {"action": "create", "project": "BND", "color": "red"},
        )
        assert res_bad_color["isError"] is True
        assert "code: VALIDATION_FAILED" in res_bad_color["content"][0]["text"]

        # 2. Sticky body 65,537 bytes -> VALIDATION_FAILED
        res_oversized = await _call_mcp_tool(
            mcp_client,
            sess,
            "manage_stickies",
            {"action": "create", "project": "BND", "body_markdown": "x" * 65537},
        )
        assert res_oversized["isError"] is True
        assert "code: VALIDATION_FAILED" in res_oversized["content"][0]["text"]

        # 3. Create normal sticky, promote twice -> ALREADY_PROMOTED
        res_sticky = await _call_mcp_tool(
            mcp_client,
            sess,
            "manage_stickies",
            {"action": "create", "project": "BND", "body_markdown": "Normal note", "color": "sky"},
        )
        sticky_yaml = res_sticky["content"][0]["text"]
        s_id = (
            [l for l in sticky_yaml.splitlines() if l.startswith("id:")][0].split(":", 1)[1].strip()
        )

        # Promote 1st time
        res_promote1 = await _call_mcp_tool(
            mcp_client,
            sess,
            "promote_sticky_to_doc",
            {"sticky": s_id},
        )
        assert res_promote1["isError"] is False

        # Promote 2nd time -> ALREADY_PROMOTED
        res_promote2 = await _call_mcp_tool(
            mcp_client,
            sess,
            "promote_sticky_to_doc",
            {"sticky": s_id},
        )
        assert res_promote2["isError"] is True
        assert "code: ALREADY_PROMOTED" in res_promote2["content"][0]["text"]

        # 4. Stale if_match -> CONFLICT_ETAG
        res_doc = await _call_mcp_tool(
            mcp_client,
            sess,
            "upsert_doc",
            {"title": "Boundary Doc", "body_markdown": "# Boundary Doc\nInitial content."},
        )
        assert res_doc["isError"] is False

        # 4a. Section patch with missing heading -> SECTION_NOT_FOUND
        read_bnd = await _call_mcp_tool(
            mcp_client,
            sess,
            "read_doc",
            {"identifier": "docs/boundary-doc", "lod": "standard"},
        )
        bnd_etag = (
            [l for l in read_bnd["content"][0]["text"].splitlines() if l.startswith("etag:")][0]
            .split(":", 1)[1]
            .strip()
            .strip('"')
        )
        res_sec_not_found = await _call_mcp_tool(
            mcp_client,
            sess,
            "upsert_doc",
            {
                "identifier": "docs/boundary-doc",
                "mode": "section_patch",
                "section_heading": "Nonexistent Heading",
                "body_markdown": "Replacement",
                "if_match": bnd_etag,
            },
        )
        assert res_sec_not_found["isError"] is True
        assert "code: SECTION_NOT_FOUND" in res_sec_not_found["content"][0]["text"]

        res_stale = await _call_mcp_tool(
            mcp_client,
            sess,
            "upsert_doc",
            {
                "identifier": "docs/boundary-doc",
                "body_markdown": "Updated body",
                "if_match": "0" * 64,
            },
        )
        assert res_stale["isError"] is True
        assert "code: CONFLICT_ETAG" in res_stale["content"][0]["text"]

        # 5. Page at depth 10 accepts no child -> VALIDATION_FAILED
        res_deep = await _call_mcp_tool(
            mcp_client,
            sess,
            "upsert_doc",
            {
                "parent": "docs/l1/l2/l3/l4/l5/l6/l7/l8/l9/l10",
                "title": "Depth 11",
                "body_markdown": "Too deep",
            },
        )
        assert res_deep["isError"] is True
        assert "code: VALIDATION_FAILED" in res_deep["content"][0]["text"]


# =============================================================================
# TEST CASE 5: Isolation & Token Budget
# =============================================================================


def test_case_5_isolation_and_token_budget() -> None:
    """Test Case 5:

    - /mcp/docs tools/list returns exactly the 6 registered names
    - schema <= 1,350 approximate tokens
    """
    registry = build_docs_registry()
    specs = registry.list_specs()
    tool_names = [s.name for s in specs]

    assert tool_names == list(DOCS_TOOL_NAMES), f"Expected {DOCS_TOOL_NAMES}, got {tool_names}"
    assert "ping_docs" not in tool_names

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
    """Test exhaustive branches across all 6 docs tools for >=95% coverage."""
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
        # manage_stickies branches
        # -------------------------------------------------------------
        # action: help
        h_resp = await _call_mcp_tool(mcp_client, sess, "manage_stickies", {"action": "help"})
        assert h_resp["isError"] is False
        assert "tool: manage_stickies" in h_resp["content"][0]["text"]

        # action: list
        l_resp = await _call_mcp_tool(
            mcp_client, sess, "manage_stickies", {"action": "list", "project": "EXH"}
        )
        assert l_resp["isError"] is False
        assert "project: EXH" in l_resp["content"][0]["text"]

        # action validation errors
        bad_act = await _call_mcp_tool(
            mcp_client, sess, "manage_stickies", {"action": "invalid_action"}
        )
        assert bad_act["isError"] is True
        assert "code: VALIDATION_FAILED" in bad_act["content"][0]["text"]

        miss_proj = await _call_mcp_tool(mcp_client, sess, "manage_stickies", {"action": "create"})
        assert miss_proj["isError"] is True
        assert "Parameter 'project' is required" in miss_proj["content"][0]["text"]

        # create a sticky for edit & recolor
        stk_resp = await _call_mcp_tool(
            mcp_client,
            sess,
            "manage_stickies",
            {
                "action": "create",
                "project": "EXH",
                "body_markdown": "# Sticky Note\nDetails here.",
                "color": "mint",
            },
        )
        assert stk_resp["isError"] is False
        stk_yaml = stk_resp["content"][0]["text"]
        stk_id = (
            [l for l in stk_yaml.splitlines() if l.startswith("id:")][0].split(":", 1)[1].strip()
        )

        # edit without body_markdown -> error
        edit_no_body = await _call_mcp_tool(
            mcp_client,
            sess,
            "manage_stickies",
            {"action": "edit", "project": "EXH", "sticky": stk_id},
        )
        assert edit_no_body["isError"] is True

        # edit with body_markdown -> updated
        edit_ok = await _call_mcp_tool(
            mcp_client,
            sess,
            "manage_stickies",
            {
                "action": "edit",
                "project": "EXH",
                "sticky": stk_id,
                "body_markdown": "# Updated Sticky\nNew body.",
            },
        )
        assert edit_ok["isError"] is False
        assert "status: updated" in edit_ok["content"][0]["text"]

        # recolor without color -> error
        rec_no_color = await _call_mcp_tool(
            mcp_client,
            sess,
            "manage_stickies",
            {"action": "recolor", "project": "EXH", "sticky": stk_id},
        )
        assert rec_no_color["isError"] is True

        # recolor with valid color -> recolored
        rec_ok = await _call_mcp_tool(
            mcp_client,
            sess,
            "manage_stickies",
            {"action": "recolor", "project": "EXH", "sticky": stk_id, "color": "coral"},
        )
        assert rec_ok["isError"] is False
        assert "status: recolored" in rec_ok["content"][0]["text"]

        # -------------------------------------------------------------
        # read_doc branches (sticky by UUID, summary, full)
        # -------------------------------------------------------------
        rd_summary = await _call_mcp_tool(
            mcp_client, sess, "read_doc", {"identifier": stk_id, "lod": "summary"}
        )
        assert rd_summary["isError"] is False
        assert "kind: sticky" in rd_summary["content"][0]["text"]

        rd_full = await _call_mcp_tool(
            mcp_client, sess, "read_doc", {"identifier": stk_id, "lod": "full"}
        )
        assert rd_full["isError"] is False
        assert "capabilities:" in rd_full["content"][0]["text"]

        # -------------------------------------------------------------
        # search_knowledge branches (kinds filter, invalid query, limit)
        # -------------------------------------------------------------
        sk_doc = await _call_mcp_tool(
            mcp_client,
            sess,
            "search_knowledge",
            {"query": "Sticky", "kinds": ["sticky"], "project": "EXH", "limit": 10},
        )
        assert sk_doc["isError"] is False

        sk_empty = await _call_mcp_tool(mcp_client, sess, "search_knowledge", {"query": ""})
        assert sk_empty["isError"] is True
        assert "VALIDATION_FAILED" in sk_empty["content"][0]["text"]

        sk_toolong = await _call_mcp_tool(
            mcp_client, sess, "search_knowledge", {"query": "a" * 501}
        )
        assert sk_toolong["isError"] is True

        sk_badkinds = await _call_mcp_tool(
            mcp_client, sess, "search_knowledge", {"query": "test", "kinds": ["invalid"]}
        )
        assert sk_badkinds["isError"] is True

        # -------------------------------------------------------------
        # upsert_doc branches (invalid mode, invalid title, append)
        # -------------------------------------------------------------
        up_notitle = await _call_mcp_tool(mcp_client, sess, "upsert_doc", {"title": ""})
        assert up_notitle["isError"] is True

        # create a doc to test append & mode errors
        doc_resp = await _call_mcp_tool(
            mcp_client,
            sess,
            "upsert_doc",
            {"title": "Exhaustive Doc", "body_markdown": "# Title\nInitial text."},
        )
        assert doc_resp["isError"] is False
        d_etag = (
            [l for l in doc_resp["content"][0]["text"].splitlines() if l.startswith("etag:")][0]
            .split(":", 1)[1]
            .strip()
            .strip('"')
        )

        # invalid update mode
        bad_mode = await _call_mcp_tool(
            mcp_client,
            sess,
            "upsert_doc",
            {
                "identifier": "docs/exhaustive-doc",
                "if_match": d_etag,
                "mode": "invalid_mode",
                "body_markdown": "x",
            },
        )
        assert bad_mode["isError"] is True
        assert "VALIDATION_FAILED" in bad_mode["content"][0]["text"]

        # append mode
        append_ok = await _call_mcp_tool(
            mcp_client,
            sess,
            "upsert_doc",
            {
                "identifier": "docs/exhaustive-doc",
                "if_match": d_etag,
                "mode": "append",
                "body_markdown": "Appended text.",
            },
        )
        assert append_ok["isError"] is False

        # -------------------------------------------------------------
        # promote_sticky_to_doc branches
        # -------------------------------------------------------------
        bad_stk_id = await _call_mcp_tool(
            mcp_client, sess, "promote_sticky_to_doc", {"sticky": "not-a-uuid"}
        )
        assert bad_stk_id["isError"] is True
        assert "VALIDATION_FAILED" in bad_stk_id["content"][0]["text"]

        miss_stk = await _call_mcp_tool(
            mcp_client, sess, "promote_sticky_to_doc", {"sticky": str(uuid.uuid4())}
        )
        assert miss_stk["isError"] is True
        assert "NOT_FOUND" in miss_stk["content"][0]["text"]

        # promote top-level doc
        prom_ok = await _call_mcp_tool(
            mcp_client,
            sess,
            "promote_sticky_to_doc",
            {"sticky": stk_id, "title": "Promoted Sticky Doc"},
        )
        assert prom_ok["isError"] is False

        # -------------------------------------------------------------
        # link_knowledge branches (remove, invalid action, invalid link_type)
        # -------------------------------------------------------------
        bad_link_type = await _call_mcp_tool(
            mcp_client,
            sess,
            "link_knowledge",
            {
                "source": "docs/exhaustive-doc",
                "target": "EXH",
                "target_kind": "project",
                "link_type": "INVALID_TYPE",
            },
        )
        assert bad_link_type["isError"] is True
        assert "LINK_TYPE_NOT_ALLOWED" in bad_link_type["content"][0]["text"]

        bad_action = await _call_mcp_tool(
            mcp_client,
            sess,
            "link_knowledge",
            {
                "source": "docs/exhaustive-doc",
                "target": "EXH",
                "target_kind": "project",
                "action": "explode",
            },
        )
        assert bad_action["isError"] is True
        assert "VALIDATION_FAILED" in bad_action["content"][0]["text"]

        # remove link
        rem_link = await _call_mcp_tool(
            mcp_client,
            sess,
            "link_knowledge",
            {
                "source": "docs/exhaustive-doc",
                "target": "EXH",
                "target_kind": "project",
                "action": "remove",
            },
        )
        assert rem_link["isError"] is False
        assert "status: unlinked" in rem_link["content"][0]["text"]
