# Copyright 2026 Kanban Platform Contributors
"""Test LOD projections and JIT progressive disclosure help (Test Case 5)."""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from mcp.app import create_mcp_app
from mcp.errors import KbMcpError, McpErrorCode
from mcp.help import build_help
from mcp.lod import (
    Lod,
    _compact_access_manifest,
    parse_lod,
    project_doc,
    project_entity,
    project_issue,
)
from mcp.registry import Surface, ToolRegistry, ToolSpec, create_placeholder_tool
from mcp.settings import McpSettings
from mcp.yaml_out import dump_yaml


def test_parse_lod_valid_and_invalid() -> None:
    """Verify parse_lod handles valid values and rejects unknown strings with VALIDATION_FAILED."""
    assert parse_lod(None) == Lod.SUMMARY
    assert parse_lod(Lod.FULL) == Lod.FULL
    assert parse_lod("summary") == Lod.SUMMARY
    assert parse_lod("STANDARD") == Lod.STANDARD
    assert parse_lod("full") == Lod.FULL

    with pytest.raises(KbMcpError) as exc_info:
        parse_lod("huge")
    assert exc_info.value.code == McpErrorCode.VALIDATION_FAILED
    assert "Unknown lod 'huge'" in exc_info.value.message


def test_issue_summary_projection_keys() -> None:
    """Verify issue at summary has exactly the summary keys (minus empties)."""
    raw_issue = {
        "id": "11111111-1111-1111-1111-111111111111",
        "key": "KAN-142",
        "summary": "Fix connection timeout",
        "state": "In Progress",
        "priority": "urgent",
        "assignees": ["@adam", "@reviewer"],
        "gate": "approved",
        "description_markdown": "Full description with sensitive details",
        "labels": ["security"],
        "access_manifest": {"users": ["@adam"]},
        "custom_fields": {"risk": "low"},
        "comments": [{"id": 1, "body": "Comment"}],
    }

    summary = project_issue(raw_issue, Lod.SUMMARY)
    assert set(summary.keys()) == {"key", "summary", "state", "priority", "assignees"}
    assert "description_markdown" not in summary
    assert "access_manifest" not in summary
    assert "gate" not in summary  # Gate omitted because not pending


def test_issue_summary_gate_included_only_when_pending() -> None:
    """Verify pending gate is preserved in summary projection."""
    raw_pending = {
        "key": "KAN-143",
        "summary": "Deploy check",
        "state": "In Review",
        "priority": "high",
        "assignees": ["@qa"],
        "gate": "pending",
    }
    summary = project_issue(raw_pending, Lod.SUMMARY)
    assert summary["gate"] == "pending"

    raw_dict_pending = {
        "key": "KAN-144",
        "summary": "Deploy check 2",
        "gate": {"status": "pending", "agent": "reality-checker"},
    }
    summary2 = project_issue(raw_dict_pending, Lod.SUMMARY)
    assert summary2["gate"] == {"status": "pending", "agent": "reality-checker"}


def test_issue_standard_and_full_projections() -> None:
    """Verify standard and full projections include expected extended fields."""
    raw_issue = {
        "key": "KAN-142",
        "summary": "Fix connection timeout",
        "state": "In Progress",
        "priority": "urgent",
        "assignees": ["@adam"],
        "description_markdown": "# Detailed Markdown\nSteps to reproduce...",
        "labels": ["security", "auth"],
        "cycle": "Cycle 4",
        "modules": ["Backend"],
        "parent": "KAN-100",
        "start_date": "2026-11-01",
        "due_date": "2026-11-15",
        "links": [["relates_to", "KAN-99"]],
        "etag": '"abc123etag"',
        "access": "Project + 2",
        "access_manifest": {"users": ["@adam"], "inherited_scope": "workspace"},
        "custom_fields": {"complexity": "high"},
        "comments": [{"id": i} for i in range(70)],
        "activity": [{"seq": i} for i in range(60)],
        "gate_verdicts": [{"verdict": "pass"}],
        "created_by": "@adam",
        "original_created_by": "@creator",
        "creator_modified_by": None,
    }

    standard = project_issue(raw_issue, Lod.STANDARD)
    assert "description_markdown" in standard
    assert "labels" in standard
    assert "access" in standard
    assert "access_manifest" not in standard
    assert "custom_fields" not in standard

    full = project_issue(raw_issue, Lod.FULL)
    assert "access_manifest" in full
    assert "custom_fields" in full
    assert len(full["comments"]) == 50  # Latest 50
    assert len(full["activity"]) == 50  # Latest 50
    assert full["provenance"] == {
        "created_by": "@adam",
        "original_created_by": "@creator",
    }


def test_provenance_overridden_boundary_cases() -> None:
    """Verify provenance overridden boundary cases for compact serialization."""
    raw_overridden_true = {
        "key": "KAN-1",
        "summary": "Overridden creator",
        "provenance": {
            "created_by": "adam",
            "original_created_by": "@bob",
            "overridden": True,
        },
    }
    full_true = project_issue(raw_overridden_true, Lod.FULL)
    assert full_true["provenance"] == {
        "created_by": "@adam",
        "original_created_by": "@bob",
        "overridden": True,
    }

    raw_overridden_false = {
        "key": "KAN-2",
        "summary": "Normal creator",
        "provenance": {
            "created_by": "@carol",
            "original_created_by": "@carol",
            "overridden": False,
        },
    }
    full_false = project_issue(raw_overridden_false, Lod.FULL)
    assert full_false["provenance"] == {
        "created_by": "@carol",
    }
    assert "original_created_by" not in full_false["provenance"]
    assert "overridden" not in full_false["provenance"]


def test_compact_access_manifest_unit() -> None:
    """Verify _compact_access_manifest strips internal UUIDs, zero counts, redundant keys."""
    raw_manifest = {
        "workspace_id": "018d-work-uuid",
        "project_id": "018d-proj-uuid",
        "canonical_key": "KAN-1",
        "object_type": "issue",
        "pill_label": "Project",
        "explicit_grant_count": 0,
        "redacted_count": 0,
        "caller_capabilities": ["read", "write"],
        "inherited_scope": {
            "workspace_id": "018d-work-uuid",
            "kind": "project",
            "scope_label": "Project Scope",
            "project_key": "KAN",
        },
        "users": [
            {
                "principal_id": "018d-user-uuid",
                "handle": "alice",
                "grant_source": "role",
                "capabilities": ["admin"],
            }
        ],
    }
    compact = _compact_access_manifest(raw_manifest)
    assert isinstance(compact, dict)
    assert compact["pill_label"] == "Project"
    assert "workspace_id" not in compact
    assert "project_id" not in compact
    assert "canonical_key" not in compact
    assert "object_type" not in compact
    assert "explicit_grant_count" not in compact
    assert "redacted_count" not in compact
    assert compact["caller_capabilities"] == ["read", "write"]
    assert compact["inherited_scope"] == {
        "kind": "project",
        "scope_label": "Project Scope",
        "project_key": "KAN",
    }
    assert compact["users"] == [
        {
            "handle": "@alice",
            "grant_source": "role",
            "capabilities": ["admin"],
        }
    ]


def test_doc_sticky_project_entity_projections() -> None:
    """Verify project_entity dispatches correctly across doc, sticky, project kinds."""
    raw_doc = {
        "id": "doc-1",
        "key": "DOC-1",
        "title": "Architecture Overview",
        "project": "KAN",
        "state": "published",
        "content_markdown": "# Spec",
        "access_manifest": {"scope": "public"},
    }
    doc_sum = project_entity("doc", raw_doc, Lod.SUMMARY)
    assert "content_markdown" not in doc_sum
    doc_full = project_entity("doc", raw_doc, Lod.FULL)
    assert "access_manifest" in doc_full

    raw_sticky = {
        "id": "st-1",
        "project": "KAN",
        "color": "yellow",
        "content": "Quick idea",
        "position": 1,
        "content_markdown": "Full idea",
    }
    sticky_sum = project_entity("sticky", raw_sticky, Lod.SUMMARY)
    assert "content_markdown" not in sticky_sum

    raw_project = {
        "id": "p-1",
        "key": "KAN",
        "name": "Kanban",
        "status": "active",
        "description": "Core tracker",
        "modules_enabled": True,
        "access_manifest": {"scope": "private"},
    }
    proj_sum = project_entity("project", raw_project, Lod.SUMMARY)
    assert "description" not in proj_sum
    proj_full = project_entity("project", raw_project, Lod.FULL)
    assert "access_manifest" in proj_full

    generic = project_entity("custom", {"id": "c-1", "secret": "hide"}, Lod.SUMMARY)
    assert generic == {"id": "c-1"}

    generic_full = project_entity("custom", {"id": "c-1", "secret": "show"}, Lod.FULL)
    assert generic_full == {"id": "c-1", "secret": "show"}

    issue_proj = project_entity("issue", {"key": "KAN-1", "summary": "One"}, Lod.SUMMARY)
    assert issue_proj == {"key": "KAN-1", "summary": "One"}


def test_issue_projections_edge_cases() -> None:
    """Verify edge branches in issue, doc, and sticky projections."""
    # Standard with pending gate
    std_gate = project_issue(
        {"key": "KAN-2", "summary": "Two", "gate": "pending", "description_markdown": "MD"},
        Lod.STANDARD,
    )
    assert std_gate["gate"] == "pending"

    # Full with non-list comments/activity and explicit provenance dict
    full_issue = project_issue(
        {
            "key": "KAN-3",
            "summary": "Three",
            "comments": "no-comments-list",
            "activity": "no-activity-list",
            "provenance": {"source": "import"},
            "gate": "approved",
        },
        Lod.FULL,
    )
    assert full_issue["comments"] == "no-comments-list"
    assert full_issue["activity"] == "no-activity-list"
    assert full_issue["provenance"] == {"source": "import"}
    assert full_issue["gate"] == "approved"

    # Full with no provenance keys at all
    full_no_prov = project_issue(
        {"key": "KAN-4", "summary": "Four"},
        Lod.FULL,
    )
    assert "provenance" not in full_no_prov

    # Doc with list comments and non-list comments
    doc_with_comments = project_doc(
        {"id": "d-1", "key": "D-1", "comments": [{"id": i} for i in range(60)]},
        Lod.FULL,
    )
    assert len(doc_with_comments["comments"]) == 50

    doc_nonlist_comments = project_doc(
        {"id": "d-2", "key": "D-2", "comments": "none"},
        Lod.FULL,
    )
    assert doc_nonlist_comments["comments"] == "none"

    doc_std = project_doc({"id": "d-3", "key": "D-3", "content_markdown": "text"}, Lod.STANDARD)
    assert doc_std["content_markdown"] == "text"


@pytest.mark.asyncio
async def test_build_help_with_mock_client() -> None:
    """Verify build_help live client resolution query and error handling."""

    class MockClientSuccess:
        def __init__(self) -> None:
            self.calls: list[dict[str, Any]] = []

        async def request(self, *args: object, **kwargs: object) -> dict[str, str]:
            self.calls.append({"args": args, "kwargs": kwargs})
            return {"key": "RESOLVED_KEY"}

    mock_client = MockClientSuccess()
    help_resolved = await build_help(
        "update_ticket",
        project="alias_name",
        client=mock_client,  # type: ignore[arg-type]
        subject_token="kb_usr_test",  # noqa: S106
        mcp_session_id="sess_123",
    )
    assert help_resolved["project"] == "RESOLVED_KEY"
    assert mock_client.calls[0]["kwargs"]["subject_token"] == "kb_usr_test"
    assert mock_client.calls[0]["kwargs"]["mcp_session_id"] == "sess_123"

    class MockClientFailure:
        async def request(self, *_args: object, **_kwargs: object) -> None:
            msg = "Network connection failed"
            raise RuntimeError(msg)

    help_failed = await build_help(
        "update_ticket",
        project="fallback_name",
        client=MockClientFailure(),  # type: ignore[arg-type]
    )
    assert help_failed["project"] == "fallback_name"


@pytest.mark.asyncio
async def test_build_help_with_live_project_metadata_success() -> None:
    """Verify build_help populates live states, priorities, labels, cycles on success."""

    class MockClientMetadata:
        async def request(
            self,
            _method: str,
            path: str,
            *_args: Any,  # noqa: ANN401
            **_kwargs: Any,  # noqa: ANN401
        ) -> Any:  # noqa: ANN401
            if path == "/api/v1/resolve":
                return {"key": "PROJ"}
            if path == "/api/v1/projects/PROJ":
                return {
                    "states": ["Open", "Closed"],
                    "priorities": ["urgent", "low"],
                    "labels": ["bug"],
                    "cycles": [{"name": "Cycle 1", "status": "active"}],
                    "modules": [{"name": "Mod1"}],
                    "modules_enabled": True,
                    "custom_fields": ["cf1"],
                    "agents": ["bot1"],
                }
            return {}

    help_doc = await build_help(
        "read_ticket",
        project="PROJ",
        client=MockClientMetadata(),  # type: ignore[arg-type]
    )
    assert help_doc["states"] == ["Open", "Closed"]
    assert help_doc["priorities"] == ["urgent", "low"]
    assert help_doc["labels"] == ["bug"]
    assert help_doc["cycles"] == [{"name": "Cycle 1", "status": "active"}]
    assert help_doc["modules"] == [{"name": "Mod1"}]
    assert help_doc["custom_fields"] == ["cf1"]
    assert help_doc["agents"] == ["bot1"]


@pytest.mark.asyncio
async def test_build_help_modules_disabled_omits_modules() -> None:
    """Verify JIT help for a project with modules disabled completely omits modules."""
    help_meta_enabled = {
        "modules_enabled": True,
        "modules": [{"name": "Core", "status": "active"}],
    }
    help_doc = await build_help("update_ticket", project="KAN", project_metadata=help_meta_enabled)
    assert "modules" in help_doc
    assert help_doc["tool"] == "update_ticket"
    assert help_doc["project"] == "KAN"

    help_meta_disabled = {
        "modules_enabled": False,
        "modules": [{"name": "Core", "status": "active"}],
    }
    help_doc_disabled = await build_help(
        "update_ticket", project="KAN", project_metadata=help_meta_disabled
    )
    assert "modules" not in help_doc_disabled


@pytest.mark.asyncio
async def test_build_help_yaml_rendering() -> None:
    """Verify help document renders into clean YAML matching specification sample."""
    help_doc = await build_help(
        "update_ticket",
        project="KAN",
        project_metadata={
            "states": ["Backlog", "Todo", "In Progress", "In Review", "Done", "Cancelled"],
            "priorities": ["urgent", "high", "medium", "low", "none"],
            "labels": ["security", "auth", "qa-needs-work"],
            "cycles": [{"name": "Cycle 4", "status": "active"}],
        },
        params_summary={"identifier": "KAN-142 | uuid", "description_mode": "append | replace"},
    )
    rendered = dump_yaml(help_doc)

    assert "tool: update_ticket" in rendered
    assert "project: KAN" in rendered
    assert "states: [Backlog, Todo, In Progress, In Review, Done, Cancelled]" in rendered
    assert "params: {identifier: KAN-142 | uuid, description_mode: append | replace}" in rendered


@pytest.mark.asyncio
async def test_mcp_transcript_help_and_ambiguity() -> None:
    """Capture MCP transcript showing ping_agent action=help and AMBIGUOUS_IDENTIFIER error."""
    test_reg = ToolRegistry(Surface.AGENT)
    test_reg.register(create_placeholder_tool(Surface.AGENT))

    async def _ambiguous_handler(_args: dict[str, Any]) -> dict[str, Any]:
        msg = "Reference 'bug' matched multiple candidates for kind 'label'"
        raise KbMcpError(
            McpErrorCode.AMBIGUOUS_IDENTIFIER,
            msg,
            hint="Specify exact UUID or qualified identifier",
            candidates=[{"key": "Bug", "title": "Bug"}, {"key": "bug", "title": "bug"}],
        )

    test_reg.register(
        ToolSpec(
            name="test_ambiguous_tool",
            description="Test ambiguity tool",
            surface=Surface.AGENT,
            input_schema={"type": "object"},
            handler=_ambiguous_handler,
        )
    )

    settings = McpSettings(mode="standalone_inprocess")
    test_app = create_mcp_app(settings, agent_registry=test_reg)
    transport = httpx.ASGITransport(app=test_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as mcp_client:
        # 1. Initialize
        init_resp = await mcp_client.post(
            "/mcp/agent",
            headers={"MCP-Protocol-Version": "2025-06-18"},
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
        session_id = init_resp.headers.get("mcp-session-id")
        headers = {"MCP-Protocol-Version": "2025-06-18"}
        if session_id:
            headers["mcp-session-id"] = session_id

        # 2. Call ping_agent with action="help"
        resp_help = await mcp_client.post(
            "/mcp/agent",
            headers=headers,
            json={
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "ping_agent",
                    "arguments": {"action": "help", "project": "KAN"},
                },
            },
        )
        assert resp_help.status_code == 200
        body_help = resp_help.json()
        assert body_help["result"]["isError"] is False
        assert "tool: ping_agent" in body_help["result"]["content"][0]["text"]

        # 3. Call test_ambiguous_tool -> AMBIGUOUS_IDENTIFIER error
        resp_amb = await mcp_client.post(
            "/mcp/agent",
            headers=headers,
            json={
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "test_ambiguous_tool",
                    "arguments": {"action": "ambiguous"},
                },
            },
        )
        assert resp_amb.status_code == 200
        body_amb = resp_amb.json()
        assert body_amb["result"]["isError"] is True
        assert "AMBIGUOUS_IDENTIFIER" in body_amb["result"]["content"][0]["text"]


@pytest.mark.asyncio
async def test_internal_exception_non_disclosure() -> None:
    """Verify internal exception traceback and message are not disclosed to client (F2)."""
    test_reg = ToolRegistry(Surface.AGENT)

    async def _leaky_handler(_args: dict[str, Any]) -> dict[str, Any]:
        msg = "SELECT secret FROM x at /srv/app.py"
        raise RuntimeError(msg)

    test_reg.register(
        ToolSpec(
            name="test_leaky_tool",
            description="Tool that raises internal exception",
            surface=Surface.AGENT,
            input_schema={"type": "object"},
            handler=_leaky_handler,
        )
    )

    settings = McpSettings(mode="standalone_inprocess")
    test_app = create_mcp_app(settings, agent_registry=test_reg)
    transport = httpx.ASGITransport(app=test_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        init_resp = await client.post(
            "/mcp/agent",
            headers={"MCP-Protocol-Version": "2025-06-18"},
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "test", "version": "1.0"},
                },
            },
        )
        session_id = init_resp.headers["mcp-session-id"]

        call_resp = await client.post(
            "/mcp/agent",
            headers={"MCP-Protocol-Version": "2025-06-18", "mcp-session-id": session_id},
            json={
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": "test_leaky_tool", "arguments": {}},
            },
        )
        assert call_resp.status_code == 200
        body = call_resp.json()
        assert body["result"]["isError"] is True
        error_text = body["result"]["content"][0]["text"]
        assert "Internal tool execution error" in error_text
        assert "SELECT" not in error_text
        assert "/srv/" not in error_text
        assert "RuntimeError" not in error_text
        assert "secret" not in error_text


@pytest.mark.asyncio
async def test_build_help_workflow_tools() -> None:
    """Verify build_help for transition_ticket and complete_work returns correct param defaults."""
    tt_help = await build_help("transition_ticket")
    assert tt_help["params"]["to_state"] == "str"
    assert "state" not in tt_help["params"]

    cw_help = await build_help("complete_work")
    assert cw_help["params"]["identifier"] == "KAN-142 | uuid"
    assert cw_help["params"]["summary_markdown"] == "str"
    assert cw_help["params"]["verification_proof"] == "object"
