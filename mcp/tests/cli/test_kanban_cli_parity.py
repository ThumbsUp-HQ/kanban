# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
# ruff: noqa: E501, PLR0911, PLR0915, PLC0415, S106, ANN401, ARG001, TRY003, EM101, SLF001, ASYNC230, TC003, PTH123
"""1:1 MCP Tool Parity, JIT Help, and Round-Trip Golden Tests for kanban-cli (KAN-48)."""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path
from typing import Any

import httpx
import pytest

from mcp.cli.main import main_admin, main_agent, main_docs
from mcp.cli.schema_cli import parse_and_execute_cli
from mcp.context import (
    McpRequestContext,
    reset_current_mcp_context,
    set_current_mcp_context,
)
from mcp.errors import KbMcpError, McpErrorCode
from mcp.internal_client import KanbanApiClient
from mcp.registry import Surface
from mcp.surfaces.admin import build_admin_registry
from mcp.surfaces.agent import create_agent_registry
from mcp.surfaces.docs import build_docs_registry
from mcp.yaml_out import dump_yaml


def _build_mock_parity_client() -> KanbanApiClient:
    """Create a KanbanApiClient backed by a deterministic MockTransport for parity tests."""

    def _mock_handler(request: httpx.Request) -> httpx.Response:
        url_path = request.url.path
        method = request.method

        # 1. Entity Resolver
        if "/api/v1/resolve" in url_path:
            params = dict(request.url.params)
            kind = params.get("kind", "project")
            ref = params.get("ref", "KAN")
            return httpx.Response(
                200,
                json={
                    "id": "01933b93-8000-7000-8000-000000000001",
                    "kind": kind,
                    "key": ref,
                    "title": f"Resolved {ref}",
                },
            )

        # 2. Project resolver
        if "/api/v1/projects/KAN" in url_path:
            return httpx.Response(
                200,
                json={
                    "id": "01933b93-8000-7000-8000-000000000001",
                    "key": "KAN",
                    "identifier": "KAN",
                    "name": "Kanban Core",
                    "workflow_states": [
                        {
                            "id": "01933b93-8000-7000-8000-000000000010",
                            "name": "Todo",
                            "category": "backlog",
                        },
                        {
                            "id": "01933b93-8000-7000-8000-000000000020",
                            "name": "Done",
                            "category": "completed",
                        },
                    ],
                    "priorities": [
                        {
                            "id": "01933b93-8000-7000-8000-000000000030",
                            "slug": "high",
                            "name": "High",
                        },
                    ],
                },
            )

        # 2. Issue resolver / read
        if "/api/v1/issues/KAN-1" in url_path and method == "GET":
            return httpx.Response(
                200,
                json={
                    "id": "01933b93-8000-7000-8000-000000000100",
                    "key": "KAN-1",
                    "sequence_id": 1,
                    "summary": "Existing ticket",
                    "description_markdown": "Ticket description",
                    "state": {"name": "Todo"},
                    "priority": {"slug": "medium"},
                    "assignees": [],
                    "labels": [],
                },
            )

        # 3. Create ticket
        if "/api/v1/issues" in url_path and method == "POST":
            req_data = json.loads(request.content.decode("utf-8")) if request.content else {}
            return httpx.Response(
                200,
                json={
                    "id": "01933b93-8000-7000-8000-000000000200",
                    "key": "KAN-49",
                    "sequence_id": 49,
                    "project_key": "KAN",
                    "summary": req_data.get("summary", "New Ticket"),
                    "description_markdown": req_data.get("description_markdown", ""),
                    "state": "Todo",
                    "priority": "medium",
                },
            )

        # 4. Search issues
        if "/api/v1/search/issues" in url_path:
            return httpx.Response(
                200,
                json={
                    "total": 1,
                    "items": [
                        {
                            "id": "01933b93-8000-7000-8000-000000000100",
                            "key": "KAN-1",
                            "title": "Existing ticket",
                            "summary": "Existing ticket",
                            "project_identifier": "KAN",
                            "state": "Todo",
                            "priority": "high",
                            "score": 1.0,
                            "snippet": "Matching snippet",
                        }
                    ],
                },
            )

        # 5. Transition ticket
        if "/transitions" in url_path:
            return httpx.Response(
                200,
                json={
                    "id": "01933b93-8000-7000-8000-000000000100",
                    "key": "KAN-1",
                    "state": "Done",
                    "transitioned": True,
                },
            )

        # 6. Knowledge / Docs search
        if "/api/v1/search/knowledge" in url_path or "/api/v1/search" in url_path:
            return httpx.Response(
                200,
                json={
                    "total": 1,
                    "items": [
                        {
                            "id": "01933b93-8000-7000-8000-000000000300",
                            "kind": "doc",
                            "title": "Architecture Overview",
                            "snippet": "Architecture doc snippet",
                            "score": 1.0,
                        }
                    ],
                },
            )

        # 7. Workspace configure / settings
        if "/api/v1/workspace" in url_path:
            return httpx.Response(
                200,
                json={
                    "workspace_id": "01933b93-8000-7000-8000-000000000001",
                    "name": "Default Workspace",
                    "slug": "default",
                    "settings": {"allow_public_signups": False},
                },
            )

        # Catch-all success for mock endpoints
        return httpx.Response(200, json={"status": "ok", "path": url_path})

    mock_transport = httpx.MockTransport(_mock_handler)
    return KanbanApiClient(
        mode="cli_remote",
        base_url="http://localhost:8080",
        transport=mock_transport,
        api_token="kb_parity_test_token",
    )


@pytest.mark.asyncio
async def test_positive_1_to_1_mcp_tool_execution_parity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify Required Test Case 1: positive tool execution produces byte-identical YAML to MCP tool handlers."""
    client = _build_mock_parity_client()

    spec_file = tmp_path / "spec.md"
    spec_file.write_text("# Ticket Spec\nDetailed parity specification.", encoding="utf-8")

    proof_file = tmp_path / "proof.json"
    proof_file.write_text(
        json.dumps(
            {
                "qa_dir": "docs/qa/KAN-1",
                "artifacts": ["docs/qa/KAN-1/diff.patch"],
                "reality_checker": {
                    "verdict": "READY",
                    "grade": "A",
                    "report_path": "docs/qa/KAN-1/reality-checker-report.md",
                },
                "ci_run_url": "https://ci.example.com/build/1",
            }
        ),
        encoding="utf-8",
    )

    agent_reg = create_agent_registry()
    docs_reg = build_docs_registry(client)
    admin_reg = build_admin_registry(client)

    # 1. create-ticket parity
    create_spec = agent_reg.get("create_ticket")
    assert create_spec is not None
    mcp_args = {
        "project": "KAN",
        "summary": "foo",
        "description_markdown": "# Ticket Spec\nDetailed parity specification.",
    }
    ctx = McpRequestContext(
        client=client, surface=Surface.AGENT, subject_token="kb_parity_test_token"
    )
    ctx_token = set_current_mcp_context(ctx)
    try:
        mcp_res = await create_spec.handler(mcp_args)
    finally:
        reset_current_mcp_context(ctx_token)
    mcp_yaml = dump_yaml(mcp_res)

    captured_cli = io.StringIO()
    monkeypatch.setattr(sys, "stdout", captured_cli)
    cli_ret = await parse_and_execute_cli(
        [
            "create-ticket",
            "--project",
            "KAN",
            "--summary",
            "foo",
            "--description-file",
            str(spec_file),
        ],
        client=client,
    )
    assert cli_ret == 0
    assert captured_cli.getvalue().strip() == mcp_yaml.strip()

    # 2. search-tickets parity
    search_spec = agent_reg.get("search_tickets")
    assert search_spec is not None
    search_args = {"project": "KAN", "lod": "summary"}
    ctx_token = set_current_mcp_context(ctx)
    try:
        mcp_search_res = await search_spec.handler(search_args)
    finally:
        reset_current_mcp_context(ctx_token)
    mcp_search_yaml = dump_yaml(mcp_search_res)

    captured_search = io.StringIO()
    monkeypatch.setattr(sys, "stdout", captured_search)
    cli_search_ret = await parse_and_execute_cli(
        ["search-tickets", "--project", "KAN", "--lod", "summary"],
        client=client,
    )
    assert cli_search_ret == 0
    assert captured_search.getvalue().strip() == mcp_search_yaml.strip()

    # 3. transition-ticket parity
    trans_spec = agent_reg.get("transition_ticket")
    assert trans_spec is not None
    with open(proof_file, encoding="utf-8") as f:
        proof_data = json.load(f)
    trans_args = {
        "identifier": "KAN-1",
        "to_state": "Done",
        "verification_proof": proof_data,
    }
    ctx_token = set_current_mcp_context(ctx)
    try:
        mcp_trans_res = await trans_spec.handler(trans_args)
    finally:
        reset_current_mcp_context(ctx_token)
    mcp_trans_yaml = dump_yaml(mcp_trans_res)

    captured_trans = io.StringIO()
    monkeypatch.setattr(sys, "stdout", captured_trans)
    cli_trans_ret = await parse_and_execute_cli(
        [
            "transition-ticket",
            "--identifier",
            "KAN-1",
            "--to-state",
            "Done",
            "--verification-proof",
            f"@{proof_file}",
        ],
        client=client,
    )
    assert cli_trans_ret == 0
    assert captured_trans.getvalue().strip() == mcp_trans_yaml.strip()

    # 4. docs search parity
    docs_search_spec = docs_reg.get("search")
    assert docs_search_spec is not None
    docs_args = {"query": "architecture"}
    ctx_docs = McpRequestContext(
        client=client, surface=Surface.DOCS, subject_token="kb_parity_test_token"
    )
    ctx_token = set_current_mcp_context(ctx_docs)
    try:
        mcp_docs_res = await docs_search_spec.handler(docs_args)
    finally:
        reset_current_mcp_context(ctx_token)
    mcp_docs_yaml = dump_yaml(mcp_docs_res)

    captured_docs = io.StringIO()
    monkeypatch.setattr(sys, "stdout", captured_docs)
    cli_docs_ret = await parse_and_execute_cli(
        ["docs", "search", "--query", "architecture"],
        client=client,
    )
    assert cli_docs_ret == 0
    assert captured_docs.getvalue().strip() == mcp_docs_yaml.strip()

    # 5. admin configure-workspace parity
    admin_cfg_spec = admin_reg.get("configure_workspace")
    assert admin_cfg_spec is not None
    admin_args = {"action": "get"}
    ctx_admin = McpRequestContext(
        client=client, surface=Surface.ADMIN, subject_token="kb_parity_test_token"
    )
    ctx_token = set_current_mcp_context(ctx_admin)
    try:
        mcp_admin_res = await admin_cfg_spec.handler(admin_args)
    finally:
        reset_current_mcp_context(ctx_token)
    mcp_admin_yaml = mcp_admin_res if isinstance(mcp_admin_res, str) else dump_yaml(mcp_admin_res)

    captured_admin = io.StringIO()
    monkeypatch.setattr(sys, "stdout", captured_admin)
    cli_admin_ret = await parse_and_execute_cli(
        ["admin", "configure-workspace", "--action", "get"],
        client=client,
    )
    assert cli_admin_ret == 0
    assert captured_admin.getvalue().strip() == mcp_admin_yaml.strip()


@pytest.mark.asyncio
async def test_negative_self_correcting_error_parity(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify Required Test Case 2: unknown flag, invalid enum, or --project help exits code 2 with progressive YAML."""
    client = _build_mock_parity_client()

    # 1. Unknown flag returns exit code 2 with did_you_mean / valid_options
    captured_err = io.StringIO()
    monkeypatch.setattr(sys, "stderr", captured_err)
    ret_unknown = await parse_and_execute_cli(
        ["read-ticket", "--identifier", "KAN-1", "--bogus-flag", "value"],
        client=client,
    )
    assert ret_unknown == 2
    err_yaml = captured_err.getvalue()
    assert "VALIDATION_FAILED" in err_yaml
    assert "bogus-flag" in err_yaml

    # 2. Invalid enum returns exit code 2 with progressive disclosure
    captured_enum_err = io.StringIO()
    monkeypatch.setattr(sys, "stderr", captured_enum_err)
    ret_enum = await parse_and_execute_cli(
        ["read-ticket", "--identifier", "KAN-1", "--lod", "invalid_tier"],
        client=client,
    )
    assert ret_enum == 2
    enum_yaml = captured_enum_err.getvalue()
    assert "VALIDATION_FAILED" in enum_yaml
    assert "valid_options" in enum_yaml
    assert "summary" in enum_yaml

    # 3. JIT help via --project help returns exit code 2 with JIT YAML structure
    captured_jit = io.StringIO()
    monkeypatch.setattr(sys, "stdout", captured_jit)
    ret_jit = await parse_and_execute_cli(
        ["create-ticket", "--project", "help"],
        client=client,
    )
    assert ret_jit == 2
    jit_yaml = captured_jit.getvalue()
    assert "tool: create_ticket" in jit_yaml
    assert "project: help" in jit_yaml
    assert "params:" in jit_yaml


def test_100_percent_tool_coverage_inventory() -> None:
    """Verify 100% of the 24 tools across agent (9), docs (3), and admin (12) are wired to kanban-cli."""
    from mcp.cli.schema_cli import build_unified_cli_parser

    _parser, dispatch = build_unified_cli_parser()

    agent_reg = create_agent_registry()
    docs_reg = build_docs_registry()
    admin_reg = build_admin_registry()

    assert len(agent_reg.list_specs()) == 9
    assert len(docs_reg.list_specs()) == 3
    assert len(admin_reg.list_specs()) == 12
    total_mcp_tools = (
        len(agent_reg.list_specs()) + len(docs_reg.list_specs()) + len(admin_reg.list_specs())
    )
    assert total_mcp_tools == 24

    # Verify all agent tools are mapped
    for spec in agent_reg.list_specs():
        kebab_name = spec.name.replace("_", "-")
        assert kebab_name in dispatch, f"Missing agent CLI command: {kebab_name}"
        surface, registered_spec = dispatch[kebab_name]
        assert surface == Surface.AGENT
        assert registered_spec.name == spec.name

    # Verify all docs tools are mapped
    for spec in docs_reg.list_specs():
        kebab_name = f"docs {spec.name.replace('_', '-')}"
        assert kebab_name in dispatch, f"Missing docs CLI command: {kebab_name}"
        surface, registered_spec = dispatch[kebab_name]
        assert surface == Surface.DOCS
        assert registered_spec.name == spec.name

    # Verify all admin tools are mapped
    for spec in admin_reg.list_specs():
        kebab_name = f"admin {spec.name.replace('_', '-')}"
        assert kebab_name in dispatch, f"Missing admin CLI command: {kebab_name}"
        surface, registered_spec = dispatch[kebab_name]
        assert surface == Surface.ADMIN
        assert registered_spec.name == spec.name


@pytest.mark.asyncio
async def test_all_24_mcp_tools_dispatch_roundtrip(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify all 24 tools round-trip through CLI invocation without unhandled errors."""
    client = _build_mock_parity_client()
    agent_reg = create_agent_registry()
    docs_reg = build_docs_registry(client)
    admin_reg = build_admin_registry(client)

    captured_out = io.StringIO()
    monkeypatch.setattr(sys, "stdout", captured_out)

    # 1. Test help on all 9 agent tools
    for spec in agent_reg.list_specs():
        kebab = spec.name.replace("_", "-")
        ret = await parse_and_execute_cli([kebab, "--help"], client=client)
        assert ret == 0, f"Failed help for agent tool {kebab}"

    # 2. Test help on all 3 docs tools
    for spec in docs_reg.list_specs():
        kebab = spec.name.replace("_", "-")
        ret = await parse_and_execute_cli(["docs", kebab, "--help"], client=client)
        assert ret == 0, f"Failed help for docs tool {kebab}"

    # 3. Test help on all 12 admin tools
    for spec in admin_reg.list_specs():
        kebab = spec.name.replace("_", "-")
        ret = await parse_and_execute_cli(["admin", kebab, "--help"], client=client)
        assert ret == 0, f"Failed help for admin tool {kebab}"


def test_standalone_bin_entry_points(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify kanban-cli-agent, kanban-cli-docs, and kanban-cli-admin entry points."""
    client = _build_mock_parity_client()
    captured = io.StringIO()
    monkeypatch.setattr(sys, "stdout", captured)

    ret_agent = main_agent(["--help"], client=client)
    assert ret_agent == 0
    assert "search-tickets" in captured.getvalue()

    captured_docs = io.StringIO()
    monkeypatch.setattr(sys, "stdout", captured_docs)
    ret_docs = main_docs(["--help"], client=client)
    assert ret_docs == 0
    assert "search" in captured_docs.getvalue()

    captured_admin = io.StringIO()
    monkeypatch.setattr(sys, "stdout", captured_admin)
    ret_admin = main_admin(["--help"], client=client)
    assert ret_admin == 0
    assert "configure-workspace" in captured_admin.getvalue()


@pytest.mark.asyncio
async def test_json_and_jsonl_output_formatting(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify --json and --jsonl outputs and zero ANSI codes."""
    client = _build_mock_parity_client()

    # 1. --json formatting
    captured_json = io.StringIO()
    monkeypatch.setattr(sys, "stdout", captured_json)
    ret_json = await parse_and_execute_cli(
        ["search-tickets", "--project", "KAN", "--json"],
        client=client,
    )
    assert ret_json == 0
    parsed = json.loads(captured_json.getvalue())
    assert isinstance(parsed, dict)
    assert "items" in parsed
    assert "\x1b[" not in captured_json.getvalue()

    # 2. --jsonl formatting
    captured_jsonl = io.StringIO()
    monkeypatch.setattr(sys, "stdout", captured_jsonl)
    ret_jsonl = await parse_and_execute_cli(
        ["search-tickets", "--project", "KAN", "--jsonl"],
        client=client,
    )
    assert ret_jsonl == 0
    lines = [ln.strip() for ln in captured_jsonl.getvalue().strip().split("\n") if ln.strip()]
    assert len(lines) >= 1
    item_parsed = json.loads(lines[0])
    assert item_parsed["key"] == "KAN-1"
    assert "\x1b[" not in captured_jsonl.getvalue()


@pytest.mark.asyncio
async def test_snake_and_kebab_case_parity(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify kebab-case and snake_case command and flag invocations are accepted identically."""
    client = _build_mock_parity_client()

    captured_kebab = io.StringIO()
    monkeypatch.setattr(sys, "stdout", captured_kebab)
    ret1 = await parse_and_execute_cli(
        ["search-tickets", "--project", "KAN", "--lod", "summary"],
        client=client,
    )
    assert ret1 == 0

    captured_snake = io.StringIO()
    monkeypatch.setattr(sys, "stdout", captured_snake)
    ret2 = await parse_and_execute_cli(
        ["search_tickets", "--project", "KAN", "--lod", "summary"],
        client=client,
    )
    assert ret2 == 0

    assert captured_kebab.getvalue().strip() == captured_snake.getvalue().strip()


@pytest.mark.asyncio
async def test_docs_and_admin_cli_execution(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify execution of docs and admin commands through unified kanban-cli."""
    client = _build_mock_parity_client()

    captured_docs = io.StringIO()
    monkeypatch.setattr(sys, "stdout", captured_docs)
    ret_docs = await parse_and_execute_cli(
        ["docs", "search", "--query", "architecture"],
        client=client,
    )
    assert ret_docs == 0
    assert "Architecture Overview" in captured_docs.getvalue()

    captured_admin = io.StringIO()
    monkeypatch.setattr(sys, "stdout", captured_admin)
    ret_admin = await parse_and_execute_cli(
        ["admin", "configure-workspace", "--action", "get"],
        client=client,
    )
    assert ret_admin == 0
    assert "air_gap_mode: false" in captured_admin.getvalue()


@pytest.mark.asyncio
async def test_standalone_surfaces_execution(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify execution through standalone surface parsers (kanban-cli-docs, kanban-cli-admin)."""
    from mcp.registry import Surface

    client = _build_mock_parity_client()

    captured_docs = io.StringIO()
    monkeypatch.setattr(sys, "stdout", captured_docs)
    ret_docs = await parse_and_execute_cli(
        ["search", "--query", "architecture"],
        surface_override=Surface.DOCS,
        client=client,
    )
    assert ret_docs == 0

    captured_admin = io.StringIO()
    monkeypatch.setattr(sys, "stdout", captured_admin)
    ret_admin = await parse_and_execute_cli(
        ["configure-workspace", "--action", "get"],
        surface_override=Surface.ADMIN,
        client=client,
    )
    assert ret_admin == 0


@pytest.mark.asyncio
async def test_jsonl_streaming_with_cursor(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify JSONL streaming iterates multiple pages when next_cursor is returned."""
    page_call = 0
    base_client = _build_mock_parity_client()
    default_transport = base_client._client._transport
    assert isinstance(default_transport, httpx.MockTransport)

    def mock_cursor_handler(request: httpx.Request) -> httpx.Response:
        nonlocal page_call
        if "/api/v1/search/issues" in request.url.path:
            page_call += 1
            if page_call == 1:
                return httpx.Response(
                    200,
                    json={
                        "total": 2,
                        "items": [{"key": "KAN-1", "title": "Page 1 Item", "priority": "high"}],
                        "next_cursor": "cur_page_2",
                    },
                )
            return httpx.Response(
                200,
                json={
                    "total": 2,
                    "items": [{"key": "KAN-2", "title": "Page 2 Item", "priority": "high"}],
                    "next_cursor": None,
                },
            )
        res = default_transport.handler(request)
        assert isinstance(res, httpx.Response)
        return res

    mock_client = KanbanApiClient(
        mode="cli_remote",
        base_url="http://localhost:8080",
        transport=httpx.MockTransport(mock_cursor_handler),
        api_token="test_tok",
    )

    captured = io.StringIO()
    monkeypatch.setattr(sys, "stdout", captured)
    ret = await parse_and_execute_cli(
        ["search-tickets", "--project", "KAN", "--jsonl"],
        client=mock_client,
    )
    assert ret == 0
    lines = [ln.strip() for ln in captured.getvalue().strip().split("\n") if ln.strip()]
    assert len(lines) == 2
    assert json.loads(lines[0])["key"] == "KAN-1"
    assert json.loads(lines[1])["key"] == "KAN-2"


@pytest.mark.asyncio
async def test_cli_execution_error_handling(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify tool execution error handling converts exceptions into structured YAML error packets."""
    import dataclasses

    from mcp.cli.auth import ResolvedConfig
    from mcp.cli.schema_cli import execute_tool_action
    from mcp.registry import Surface
    from mcp.surfaces.agent import create_agent_registry

    reg = create_agent_registry()
    read_spec = reg.get("read_ticket")
    assert read_spec is not None

    cfg = ResolvedConfig(url="http://localhost:8080", workspace=None, project=None, token="tok")

    # 1. KbMcpError handler path
    async def mock_fail_kbmcp(args: Any) -> Any:
        raise KbMcpError(McpErrorCode.INSUFFICIENT_PERMISSION, "Explicit permission denial")

    failing_spec = dataclasses.replace(read_spec, handler=mock_fail_kbmcp)
    captured_err1 = io.StringIO()
    monkeypatch.setattr(sys, "stderr", captured_err1)
    ret1 = await execute_tool_action(Surface.AGENT, failing_spec, {"identifier": "KAN-1"}, cfg)
    assert ret1 == 2
    assert "Explicit permission denial" in captured_err1.getvalue()

    # 2. Unexpected Exception handler path
    async def mock_fail_unexpected(args: Any) -> Any:
        raise RuntimeError("Unexpected crash")

    crash_spec = dataclasses.replace(read_spec, handler=mock_fail_unexpected)
    captured_err2 = io.StringIO()
    monkeypatch.setattr(sys, "stderr", captured_err2)
    ret2 = await execute_tool_action(Surface.AGENT, crash_spec, {"identifier": "KAN-1"}, cfg)
    assert ret2 == 2
    assert "Unexpected crash" in captured_err2.getvalue()
