# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Feature unit tests for /mcp/agent tool: read_ticket (KB-P4-04)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast
from unittest.mock import AsyncMock

import pytest
import yaml

from mcp.context import McpRequestContext
from mcp.errors import KbMcpError, McpErrorCode
from mcp.registry import Surface
from mcp.surfaces.agent.read_ticket import (
    _format_assignees,
    _format_parent,
    _load_links,
    _validate_read_arguments,
    read_ticket,
)

if TYPE_CHECKING:
    from mcp.tests.agent.conftest import AgentTestEnv

pytestmark = pytest.mark.committed_db


async def _call_read_ticket(
    env: AgentTestEnv,
    arguments: dict[str, Any],
    *,
    subject_token: str | None = None,
    session_id: str | None = None,
) -> dict[str, Any]:
    """Invoke read_ticket via JSON-RPC 2.0 tools/call."""
    active_session_id = session_id
    if active_session_id is None:
        init_resp = await env.mcp_client.post(
            "/mcp/agent",
            json={
                "jsonrpc": "2.0",
                "id": 999,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "test-agent", "version": "1.0"},
                },
            },
            headers={"X-KB-Subject-Token": subject_token} if subject_token else {},
        )
        assert init_resp.status_code == 200
        active_session_id = init_resp.headers["mcp-session-id"]

    headers: dict[str, str] = {"mcp-session-id": active_session_id}
    if subject_token is not None:
        headers["X-KB-Subject-Token"] = subject_token

    req_payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "read_ticket",
            "arguments": arguments,
        },
    }
    resp = await env.mcp_client.post("/mcp/agent", json=req_payload, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["jsonrpc"] == "2.0"
    assert data["id"] == 1
    return cast("dict[str, Any]", data["result"])


@pytest.mark.asyncio
async def test_case_1_positive_read_ticket_all_lods(agent_test_env: AgentTestEnv) -> None:
    """Case 1: read_ticket('KAN-142', lod='full') contains all detailed fields."""
    env = agent_test_env

    # 1. Full LOD
    res_full = await _call_read_ticket(env, {"identifier": "KAN-142", "lod": "full"})
    assert res_full["isError"] is False
    content_full = res_full["content"][0]["text"]
    parsed_full = yaml.safe_load(content_full)

    assert parsed_full["key"] == "KAN-142"
    assert parsed_full["summary"] == "Harden Multi-Card OIDC & LDAPS Auth Studio"
    assert parsed_full["state"] == "In Progress"
    assert parsed_full["priority"] == "urgent"
    assert parsed_full["assignees"] == ["@adam"]
    assert "# OIDC Architecture" in parsed_full["description_markdown"]
    assert "access_manifest" in parsed_full
    assert "links" in parsed_full
    assert "comments" in parsed_full
    assert len(parsed_full["comments"]) == 1
    assert parsed_full["comments"][0]["body_markdown"] == "Initial security audit comment for OIDC."
    assert "activity" in parsed_full
    assert "etag" in parsed_full
    assert len(parsed_full["etag"]) == 64

    # 2. Standard LOD
    res_std = await _call_read_ticket(env, {"identifier": "KAN-142", "lod": "standard"})
    assert res_std["isError"] is False
    content_std = res_std["content"][0]["text"]
    parsed_std = yaml.safe_load(content_std)

    assert parsed_std["key"] == "KAN-142"
    assert parsed_std["summary"] == "Harden Multi-Card OIDC & LDAPS Auth Studio"
    assert parsed_std["state"] == "In Progress"
    assert parsed_std["priority"] == "urgent"
    assert parsed_std["assignees"] == ["@adam"]
    assert "# OIDC Architecture" in parsed_std["description_markdown"]
    assert "links" in parsed_std
    assert "etag" in parsed_std
    # Standard omits comments, activity, and access_manifest
    assert "access_manifest" not in parsed_std
    assert "comments" not in parsed_std
    assert "activity" not in parsed_std

    # 3. Summary LOD
    res_sum = await _call_read_ticket(env, {"identifier": "KAN-142", "lod": "summary"})
    assert res_sum["isError"] is False
    content_sum = res_sum["content"][0]["text"]
    parsed_sum = yaml.safe_load(content_sum)

    assert parsed_sum["key"] == "KAN-142"
    assert parsed_sum["summary"] == "Harden Multi-Card OIDC & LDAPS Auth Studio"
    assert parsed_sum["state"] == "In Progress"
    assert parsed_sum["priority"] == "urgent"
    assert parsed_sum["assignees"] == ["@adam"]
    # Summary omits description, access_manifest, links, comments, activity
    assert "description_markdown" not in parsed_sum
    assert "access_manifest" not in parsed_sum
    assert "links" not in parsed_sum


@pytest.mark.asyncio
async def test_case_2_rls_security_identical_404(agent_test_env: AgentTestEnv) -> None:
    """Case 2: RLS security: caller without access gets byte-identical 404."""
    env = agent_test_env

    # 1. Call unreadable SEC-1 under Adam
    res_sec = await _call_read_ticket(
        env,
        {"identifier": "SEC-1"},
        subject_token=env.token_adam,
    )
    assert res_sec["isError"] is True
    text_sec = res_sec["content"][0]["text"]

    # 2. Call non-existent KAN-99999 under Adam
    res_missing = await _call_read_ticket(
        env,
        {"identifier": "KAN-99999"},
        subject_token=env.token_adam,
    )
    assert res_missing["isError"] is True
    text_missing = res_missing["content"][0]["text"]

    # Byte-identical assertion
    assert text_sec == text_missing
    parsed = yaml.safe_load(text_sec)
    assert parsed["error"]["code"] == "NOT_FOUND"
    assert parsed["error"]["message"] == "ticket not found"


@pytest.mark.asyncio
async def test_case_3_boundary_validation_read_ticket(agent_test_env: AgentTestEnv) -> None:
    """Case 3: Boundary and input schema validation for read_ticket."""
    env = agent_test_env

    # 1. Missing identifier
    res_no_id = await _call_read_ticket(env, {})
    assert res_no_id["isError"] is True
    err1 = yaml.safe_load(res_no_id["content"][0]["text"])
    assert err1["error"]["code"] == "VALIDATION_FAILED"

    # 2. Unknown key
    res_unknown = await _call_read_ticket(env, {"identifier": "KAN-142", "extra": "invalid"})
    assert res_unknown["isError"] is True
    err2 = yaml.safe_load(res_unknown["content"][0]["text"])
    assert err2["error"]["code"] == "VALIDATION_FAILED"
    assert "Unknown parameter 'extra'" in err2["error"]["message"]

    # 3. Invalid lod
    res_bad_lod = await _call_read_ticket(env, {"identifier": "KAN-142", "lod": "super_full"})
    assert res_bad_lod["isError"] is True
    err3 = yaml.safe_load(res_bad_lod["content"][0]["text"])
    assert err3["error"]["code"] == "VALIDATION_FAILED"

    # 4. comments_limit out of bounds
    res_bad_limit = await _call_read_ticket(env, {"identifier": "KAN-142", "comments_limit": 51})
    assert res_bad_limit["isError"] is True
    err4 = yaml.safe_load(res_bad_limit["content"][0]["text"])
    assert err4["error"]["code"] == "VALIDATION_FAILED"
    assert "comments_limit must be an integer between 0 and 50" in err4["error"]["message"]

    res_neg_limit = await _call_read_ticket(env, {"identifier": "KAN-142", "comments_limit": -1})
    assert res_neg_limit["isError"] is True
    err5 = yaml.safe_load(res_neg_limit["content"][0]["text"])
    assert err5["error"]["code"] == "VALIDATION_FAILED"


@pytest.mark.asyncio
async def test_case_5_read_ticket_help(agent_test_env: AgentTestEnv) -> None:
    """Case 5: read_ticket(identifier='help') returns JIT progressive disclosure help block."""
    env = agent_test_env

    res_help = await _call_read_ticket(env, {"identifier": "help"})
    assert res_help["isError"] is False
    text_help = res_help["content"][0]["text"]
    parsed_help = yaml.safe_load(text_help)

    assert parsed_help["tool"] == "read_ticket"
    assert "params" in parsed_help
    assert "identifier" in parsed_help["params"]
    assert "lod" in parsed_help["params"]


def test_read_ticket_formatting_helpers() -> None:
    """Verify assignee and parent formatting helpers."""
    # Assignees
    raw_assignees = [
        "@alice",
        {"kind": "free_text", "free_text": "External Contributor"},
        {"kind": "principal", "principal": {"handle": "bob"}},
        {"kind": "principal", "principal": {"handle": "@charlie"}},
        {"kind": "principal", "principal": {"display_name": "Dave Smith"}},
        {"kind": "principal", "principal": {"id": "11111111-1111-1111-1111-111111111111"}},
        {"handle": "eve"},
        {"handle": "@frank"},
    ]
    formatted = _format_assignees(raw_assignees)
    assert "@alice" in formatted
    assert "External Contributor" in formatted
    assert "@bob" in formatted
    assert "@charlie" in formatted
    assert "@davesmith" in formatted
    assert "11111111-1111-1111-1111-111111111111" in formatted
    assert "@eve" in formatted
    assert "@frank" in formatted

    # Parent
    assert _format_parent(None) is None
    assert _format_parent("PAR-1") == "PAR-1"
    assert _format_parent({"restricted": True}) == {
        "restricted": True,
        "label": "🔒 Restricted Parent Issue",
    }
    assert _format_parent({"key": "PAR-2", "summary": "Parent Issue"}) == "PAR-2"
    assert _format_parent({"summary": "Only Summary"}) == "Only Summary"


@pytest.mark.asyncio
async def test_read_ticket_additional_validations() -> None:
    """Verify extra boundary validation paths in read_ticket."""
    # Context None
    with pytest.raises(KbMcpError) as exc_ctx:
        await read_ticket({"identifier": "KAN-142"})
    assert exc_ctx.value.code == McpErrorCode.INTERNAL

    # Non-string identifier
    with pytest.raises(KbMcpError) as exc_non_str:
        _validate_read_arguments({"identifier": 12345})
    assert exc_non_str.value.code == McpErrorCode.VALIDATION_FAILED

    # Whitespace identifier
    with pytest.raises(KbMcpError) as exc_ws:
        _validate_read_arguments({"identifier": "   "})
    assert exc_ws.value.code == McpErrorCode.VALIDATION_FAILED

    # Overly long identifier
    with pytest.raises(KbMcpError) as exc_long:
        _validate_read_arguments({"identifier": "K" * 201})
    assert exc_long.value.code == McpErrorCode.VALIDATION_FAILED

    # Boolean comments_limit
    with pytest.raises(KbMcpError) as exc_bool:
        _validate_read_arguments({"identifier": "KAN-1", "comments_limit": True})
    assert exc_bool.value.code == McpErrorCode.VALIDATION_FAILED

    # String comments_limit
    with pytest.raises(KbMcpError) as exc_str_limit:
        _validate_read_arguments({"identifier": "KAN-1", "comments_limit": "10"})
    assert exc_str_limit.value.code == McpErrorCode.VALIDATION_FAILED


@pytest.mark.asyncio
async def test_read_ticket_comments_limit_zero(agent_test_env: AgentTestEnv) -> None:
    """Verify read_ticket with comments_limit=0 returns empty comments without query."""
    env = agent_test_env
    res = await _call_read_ticket(
        env,
        {"identifier": "KAN-142", "lod": "full", "comments_limit": 0},
    )
    assert res["isError"] is False
    parsed = yaml.safe_load(res["content"][0]["text"])
    assert parsed["key"] == "KAN-142"
    assert parsed.get("comments", []) == []


@pytest.mark.asyncio
async def test_read_ticket_links_projection_unit() -> None:
    """Verify _load_links omits empty links and projects compact outbound/inbound and truncated."""
    # 1. Empty outbound and inbound -> None
    mock_client = AsyncMock()
    mock_client.request.return_value = {"outbound": [], "inbound": [], "truncated": False}
    ctx = McpRequestContext(surface=Surface.AGENT, client=mock_client)
    res_none = await _load_links("KAN-1", ctx)
    assert res_none is None

    # 2. Populated links with truncated=True
    mock_client.request.return_value = {
        "outbound": [
            {
                "id": "link-1",
                "link_type": "BLOCKS",
                "target": {"id": "uuid-2", "key": "KAN-2", "summary": "Blockee", "type": "issue"},
            }
        ],
        "inbound": [
            {
                "id": "link-2",
                "link_type": "RELATES_TO",
                "source": {"id": "uuid-3", "key": "KAN-3", "summary": "Relater", "type": "issue"},
            }
        ],
        "truncated": True,
    }
    res_links = await _load_links("KAN-1", ctx)
    assert res_links is not None
    assert res_links["truncated"] is True
    assert res_links["outbound"] == [
        {"link_type": "BLOCKS", "target": {"key": "KAN-2", "summary": "Blockee"}}
    ]
    assert res_links["inbound"] == [
        {"link_type": "RELATES_TO", "source": {"key": "KAN-3", "summary": "Relater"}}
    ]

    # 3. Populated links with truncated=False -> truncated key omitted
    mock_client.request.return_value = {
        "outbound": [
            {
                "id": "link-1",
                "link_type": "BLOCKS",
                "target": {"key": "KAN-2"},
            }
        ],
        "inbound": [],
        "truncated": False,
    }
    res_links_notrunc = await _load_links("KAN-1", ctx)
    assert res_links_notrunc is not None
    assert "truncated" not in res_links_notrunc
    assert "inbound" not in res_links_notrunc
    assert res_links_notrunc["outbound"] == [{"link_type": "BLOCKS", "target": {"key": "KAN-2"}}]


@pytest.mark.asyncio
async def test_read_ticket_empty_links_omitted_standard(agent_test_env: AgentTestEnv) -> None:
    """Verify read_ticket with lod=standard omits links when empty and formats populated links."""
    env = agent_test_env

    # 1. KAN-3 has no links -> links omitted
    res = await _call_read_ticket(env, {"identifier": "KAN-3", "lod": "standard"})
    assert res["isError"] is False
    parsed = yaml.safe_load(res["content"][0]["text"])
    assert "links" not in parsed

    # 2. KAN-142 has links -> compact link entries without truncated=false
    res_142 = await _call_read_ticket(env, {"identifier": "KAN-142", "lod": "standard"})
    parsed_142 = yaml.safe_load(res_142["content"][0]["text"])
    assert "links" in parsed_142
    assert "outbound" in parsed_142["links"]
    assert "truncated" not in parsed_142["links"]
    assert parsed_142["links"]["outbound"][0]["link_type"] == "RELATES_TO"
    assert parsed_142["links"]["outbound"][0]["target"]["key"] == "KAN-150"


@pytest.mark.asyncio
async def test_read_ticket_standard_populates_access_from_pill_label(
    agent_test_env: AgentTestEnv,
) -> None:
    """Verify read_ticket in standard LOD populates access from access_manifest pill_label."""
    env = agent_test_env

    res = await _call_read_ticket(env, {"identifier": "KAN-142", "lod": "standard"})
    assert res["isError"] is False
    parsed = yaml.safe_load(res["content"][0]["text"])
    assert "access" in parsed
    assert parsed["access"] == "Project"
    assert "access_manifest" not in parsed


@pytest.mark.asyncio
async def test_read_ticket_full_compacts_manifest_activity_provenance(
    agent_test_env: AgentTestEnv,
) -> None:
    """Verify read_ticket in full LOD compacts manifest, activity, comments, provenance."""
    env = agent_test_env

    res = await _call_read_ticket(env, {"identifier": "KAN-142", "lod": "full"})
    assert res["isError"] is False
    parsed = yaml.safe_load(res["content"][0]["text"])

    # access_manifest check
    assert "access_manifest" in parsed
    manifest = parsed["access_manifest"]
    assert "workspace_id" not in manifest
    assert "project_id" not in manifest
    assert "canonical_key" not in manifest
    assert "object_type" not in manifest
    assert manifest.get("pill_label") == "Project"

    # comments check
    assert "comments" in parsed
    if parsed["comments"]:
        for comm in parsed["comments"]:
            assert "author_id" not in comm
            assert "issue_id" not in comm
            assert "body_sha256" not in comm
            if "author" in comm:
                assert comm["author"].startswith("@")

    # activity check
    assert "activity" in parsed
    if parsed["activity"]:
        for act in parsed["activity"]:
            assert "id" not in act
            assert "category" not in act
            if "payload" in act:
                assert "from_state_id" not in act["payload"]
                assert "to_state_id" not in act["payload"]
                assert "body_sha256" not in act["payload"]
                assert "comment" not in act["payload"]
                assert "body_markdown" not in act["payload"]
            if "actor" in act:
                assert str(act["actor"]).startswith("@") or str(act["actor"]).isalnum()

    # provenance check when present
    if "provenance" in parsed:
        assert "created_by" in parsed["provenance"]
        assert str(parsed["provenance"]["created_by"]).startswith("@")


@pytest.mark.asyncio
async def test_read_ticket_free_text_secret_scrubbing(agent_test_env: AgentTestEnv) -> None:
    """Verify read_ticket output scrubs known secret patterns in description and comments."""
    env = agent_test_env

    # 1. Create issue with secret patterns in description
    pem_key = (
        "-----BEGIN RSA PRIVATE KEY-----\n"
        "MIIEowIBAAKCAQEA0Y1234567890abcdefghijklmnopqrstuvwxyzABCDEFGHIJ\n"
        "KLMNOPQRSTUVWXYZ0123456789+/abcdefghijklmnopqrstuvwxyzABCDEFGHIJ\n"
        "-----END RSA PRIVATE KEY-----"
    )
    desc_with_secrets = (
        "# Secret Manifest\n\n"
        "Testing outbound redaction:\n"
        "- OpenAI: sk-proj-1234567890abcdef1234567890abcdef1234567890\n"
        "- GitHub: ghp_1234567890abcdefghijklmnopqrstuvwxyz12\n"
        "- AWS: AKIAIOSFODNN7EXAMPLE\n"
        "- Kanban agent: kb_agt_0123456789abcdef\n"
        f"- Private key:\n```\n{pem_key}\n```\n"
    )

    issue_res = await env.internal_client.request(
        "POST",
        "/api/v1/projects/KAN/issues",
        json_data={"summary": "Ticket with Secrets", "description_markdown": desc_with_secrets},
        subject_token=env.token_adam,
    )
    assert isinstance(issue_res, dict)
    issue_key = str(issue_res["key"])

    # 2. Add comment with secret patterns
    await env.internal_client.request(
        "POST",
        f"/api/v1/issues/{issue_key}/comments",
        json_data={
            "body_markdown": (
                "Comment secret: sk-proj-1234567890abcdef1234567890abcdef1234567890 "
                "and AKIAIOSFODNN7EXAMPLE"
            )
        },
        subject_token=env.token_adam,
        mcp_session_id="test-session-secret-scrub",
    )

    # 3. Call read_ticket via MCP with lod=full
    res = await _call_read_ticket(env, {"identifier": issue_key, "lod": "full"})
    assert res["isError"] is False
    yaml_text = res["content"][0]["text"]

    # 4. Verify raw secrets are absent and redacted placeholders appear in YAML output
    assert "sk-proj-1234567890" not in yaml_text
    assert "ghp_1234567890" not in yaml_text
    assert "AKIAIOSFODNN7EXAMPLE" not in yaml_text
    assert "kb_agt_0123456789" not in yaml_text
    assert "BEGIN RSA PRIVATE KEY" not in yaml_text

    assert "[REDACTED:API_KEY]" in yaml_text
    assert "[REDACTED:GITHUB_TOKEN]" in yaml_text
    assert "[REDACTED:AWS_ACCESS_KEY]" in yaml_text
    assert "[REDACTED:KANBAN_KEY]" in yaml_text
    assert "[REDACTED:PRIVATE_KEY]" in yaml_text

    # 5. Verify parsed structure also has scrubbed values
    parsed = yaml.safe_load(yaml_text)
    assert "[REDACTED:API_KEY]" in parsed["description_markdown"]
    assert len(parsed["comments"]) > 0
    assert "[REDACTED:API_KEY]" in parsed["comments"][0]["body_markdown"]
