# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
# ruff: noqa: SLF001, ARG001, FBT003, PLC0415
"""Comprehensive unit tests for Progressive-Disclosure Self-Correction YAML Error UX (KAN-19)."""

from __future__ import annotations

import uuid
from typing import Any

import httpx
import pytest
import yaml

from mcp.errors import KbMcpError, McpErrorCode
from mcp.internal_client import KanbanApiClient
from mcp.protocol import (
    InMemorySessionStore,
    McpProtocolHandler,
    _format_flag_val,
    format_cli_example,
)
from mcp.registry import Surface, ToolRegistry, ToolSpec
from mcp.settings import McpSettings


def test_format_flag_val_and_cli_example() -> None:
    """Validate flag scalar and collection formatting and CLI syntax."""
    assert _format_flag_val(True) == "true"
    assert _format_flag_val(False) == "false"
    assert _format_flag_val(42) == "42"
    assert _format_flag_val(3.14) == "3.14"
    assert _format_flag_val("DOC") == "DOC"
    assert _format_flag_val("KAN-42") == "KAN-42"
    assert _format_flag_val("hello world") == '"hello world"'
    assert _format_flag_val(["a", "b"]) == '\'["a", "b"]\''
    assert _format_flag_val({"k": "v"}) == '\'{"k": "v"}\''

    docs_ex = format_cli_example(
        Surface.DOCS,
        "update",
        {"id": "docs/arch", "type": "DOC", "original_text": "old", "replacement_text": "new"},
    )
    assert docs_ex == (
        'kanban-cli-docs update --id="docs/arch" --type=DOC '
        '--original-text="old" --replacement-text="new"'
    )

    agent_ex = format_cli_example(
        Surface.AGENT,
        "transition_ticket",
        {"identifier": "KAN-19", "to_state": "Done"},
    )
    assert agent_ex == 'kanban-cli-agent transition_ticket --identifier=KAN-19 --to-state="Done"'

    admin_ex = format_cli_example(
        Surface.ADMIN,
        "architect_project",
        {"action": "plan", "project": "KAN"},
    )
    assert admin_ex == 'kanban-cli-admin architect_project --action="plan" --project=KAN'


def test_kb_mcp_error_to_yaml_and_fields() -> None:
    """Test KbMcpError progressive disclosure fields serialization."""
    err = KbMcpError(
        code=McpErrorCode.VALIDATION_FAILED,
        message="Unknown parameter 'body'",
        hint="Use semantic parameter",
        field="body",
        valid_options=["content", "description_markdown"],
        did_you_mean=["content"],
        fix_hint="Did you mean 'content'?",
        cli_example='kanban-cli-docs create --content="text"',
        closest_match=[{"line": 10, "text": "sample"}],
    )

    assert err.code == McpErrorCode.VALIDATION_FAILED
    assert err.field == "body"
    assert err.valid_options == ["content", "description_markdown"]
    assert err.did_you_mean == ["content"]
    assert err.fix_hint == "Did you mean 'content'?"
    assert err.cli_example == 'kanban-cli-docs create --content="text"'
    assert err.closest_match == [{"line": 10, "text": "sample"}]

    yaml_text = err.to_yaml()
    data = yaml.safe_load(yaml_text)
    error_obj = data["error"]
    assert error_obj["code"] == "VALIDATION_FAILED"
    assert error_obj["field"] == "body"
    assert error_obj["valid_options"] == ["content", "description_markdown"]
    assert error_obj["did_you_mean"] == ["content"]
    assert error_obj["fix_hint"] == "Did you mean 'content'?"
    assert error_obj["cli_example"] == 'kanban-cli-docs create --content="text"'
    assert error_obj["closest_match"] == [{"line": 10, "text": "sample"}]

    # Test minimal error has no None keys serialized
    minimal_err = KbMcpError(McpErrorCode.NOT_FOUND, "Entity missing", extra={"custom_flag": True})
    minimal_yaml = minimal_err.to_yaml()
    assert "custom_flag: true" in minimal_yaml
    assert "field:" not in minimal_yaml
    assert "valid_options:" not in minimal_yaml
    assert "did_you_mean:" not in minimal_yaml
    assert "fix_hint:" not in minimal_yaml
    assert "cli_example:" not in minimal_yaml
    assert "closest_match:" not in minimal_yaml


@pytest.mark.asyncio
async def test_protocol_pre_dispatch_unknown_param_semantic_alias() -> None:
    """Verify unknown parameter pre-dispatch catches aliases and populates did_you_mean."""
    reg = ToolRegistry(Surface.DOCS)

    async def dummy_handler(args: dict[str, Any]) -> str:
        return "ok"

    dummy_spec = ToolSpec(
        name="update",
        description="Update doc",
        surface=Surface.DOCS,
        input_schema={
            "type": "object",
            "properties": {
                "id": {"type": "string"},
                "content": {"type": "string"},
                "description_markdown": {"type": "string"},
            },
            "required": ["id"],
            "additionalProperties": False,
        },
        handler=dummy_handler,
    )
    reg.register(dummy_spec)
    store = InMemorySessionStore()
    handler = McpProtocolHandler(
        surface=Surface.DOCS,
        registry=reg,
        session_store=store,
        settings=McpSettings(),
    )

    # Calling with 'body' which is in SEMANTIC_ALIASES
    with pytest.raises(KbMcpError) as exc_info:
        handler._validate_tool_arguments_schema(dummy_spec, {"id": "DOC-1", "body": "text"})

    err = exc_info.value
    assert err.code == McpErrorCode.VALIDATION_FAILED
    assert err.field == "body"
    assert err.did_you_mean == ["content", "description_markdown"]
    assert "Unknown parameter 'body'" in err.message
    assert err.fix_hint is not None
    assert "Did you mean 'content'?" in err.fix_hint
    assert err.cli_example is not None
    assert "--content=" in err.cli_example


@pytest.mark.asyncio
async def test_protocol_pre_dispatch_unknown_param_fuzzy_difflib() -> None:
    """Verify unknown parameter pre-dispatch fuzzy matches close keys."""
    reg = ToolRegistry(Surface.DOCS)

    async def dummy_handler(args: dict[str, Any]) -> str:
        return "ok"

    dummy_spec = ToolSpec(
        name="search",
        description="Search docs",
        surface=Surface.DOCS,
        input_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer"},
            },
            "required": ["query"],
            "additionalProperties": False,
        },
        handler=dummy_handler,
    )
    reg.register(dummy_spec)
    store = InMemorySessionStore()
    handler = McpProtocolHandler(
        surface=Surface.DOCS,
        registry=reg,
        session_store=store,
        settings=McpSettings(),
    )

    # Calling with typo 'querry'
    with pytest.raises(KbMcpError) as exc_info:
        handler._validate_tool_arguments_schema(dummy_spec, {"querry": "terms"})

    err = exc_info.value
    assert err.code == McpErrorCode.VALIDATION_FAILED
    assert err.field == "querry"
    assert err.did_you_mean == ["query"]
    assert set(err.valid_options or []) == {"limit", "query"}
    assert "Did you mean 'query'?" in (err.fix_hint or "")
    assert err.cli_example is not None
    assert 'kanban-cli-docs search --query="terms"' in err.cli_example


@pytest.mark.asyncio
async def test_protocol_pre_dispatch_missing_required_parameter() -> None:
    """Verify missing required parameter formats pre-filled cli_example with placeholders."""
    reg = ToolRegistry(Surface.DOCS)

    async def dummy_handler(args: dict[str, Any]) -> str:
        return "ok"

    dummy_spec = ToolSpec(
        name="create",
        description="Create doc",
        surface=Surface.DOCS,
        input_schema={
            "type": "object",
            "properties": {
                "summary": {"type": "string"},
                "project_key": {"type": "string"},
                "content": {"type": "string"},
            },
            "required": ["project_key", "summary"],
            "additionalProperties": False,
        },
        handler=dummy_handler,
    )
    reg.register(dummy_spec)
    store = InMemorySessionStore()
    handler = McpProtocolHandler(
        surface=Surface.DOCS,
        registry=reg,
        session_store=store,
        settings=McpSettings(),
    )

    # Caller only gave summary
    with pytest.raises(KbMcpError) as exc_info:
        handler._validate_tool_arguments_schema(dummy_spec, {"summary": "Architecture"})

    err = exc_info.value
    assert err.code == McpErrorCode.VALIDATION_FAILED
    assert err.field == "project_key"
    assert "Missing required parameter 'project_key'" in err.message
    assert err.fix_hint == "Missing required parameter: 'project_key'. Provide a value to proceed."
    assert err.cli_example is not None
    assert '--summary="Architecture"' in err.cli_example
    assert '--project-key="<project_key>"' in err.cli_example


@pytest.mark.asyncio
async def test_protocol_pre_dispatch_invalid_enum_value() -> None:
    """Verify invalid enum value provides valid_options, did_you_mean, and corrected cli_example."""
    reg = ToolRegistry(Surface.DOCS)

    async def dummy_handler(args: dict[str, Any]) -> str:
        return "ok"

    dummy_spec = ToolSpec(
        name="create",
        description="Create entity",
        surface=Surface.DOCS,
        input_schema={
            "type": "object",
            "properties": {
                "type": {
                    "type": "string",
                    "enum": ["DOC", "STICKY"],
                },
                "summary": {"type": "string"},
            },
            "required": ["type", "summary"],
        },
        handler=dummy_handler,
    )
    reg.register(dummy_spec)
    store = InMemorySessionStore()
    handler = McpProtocolHandler(
        surface=Surface.DOCS,
        registry=reg,
        session_store=store,
        settings=McpSettings(),
    )

    with pytest.raises(KbMcpError) as exc_info:
        handler._validate_tool_arguments_schema(
            dummy_spec,
            {"type": "dco", "summary": "Note"},
        )

    err = exc_info.value
    assert err.code == McpErrorCode.VALIDATION_FAILED
    assert err.field == "type"
    assert err.valid_options == ["DOC", "STICKY"]
    assert err.did_you_mean == ["DOC"]
    assert "type must be 'DOC' or 'STICKY'" in err.message
    assert "Did you mean 'DOC'?" in (err.fix_hint or "")
    assert err.cli_example is not None
    assert "--type=DOC" in err.cli_example


@pytest.mark.asyncio
async def test_protocol_pre_dispatch_type_and_pattern_validations() -> None:
    """Verify type checking (string, integer, boolean, array) and pattern regex validation."""
    reg = ToolRegistry(Surface.ADMIN)

    async def dummy_handler(args: dict[str, Any]) -> str:
        return "ok"

    dummy_spec = ToolSpec(
        name="configure",
        description="Config tool",
        surface=Surface.ADMIN,
        input_schema={
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "count": {"type": "integer"},
                "active": {"type": "boolean"},
                "tags": {"type": "array"},
                "plan_sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
            },
        },
        handler=dummy_handler,
    )
    reg.register(dummy_spec)
    store = InMemorySessionStore()
    handler = McpProtocolHandler(
        surface=Surface.ADMIN,
        registry=reg,
        session_store=store,
        settings=McpSettings(),
    )

    # String type check
    with pytest.raises(KbMcpError) as exc_str:
        handler._validate_tool_arguments_schema(dummy_spec, {"name": 1234})
    assert exc_str.value.field == "name"
    assert "must be of type string" in exc_str.value.message

    # Integer type check
    with pytest.raises(KbMcpError) as exc_int:
        handler._validate_tool_arguments_schema(dummy_spec, {"count": "not-a-number"})
    assert exc_int.value.field == "count"
    assert "must be of type integer" in exc_int.value.message

    # Boolean type check
    with pytest.raises(KbMcpError) as exc_bool:
        handler._validate_tool_arguments_schema(dummy_spec, {"active": "yes"})
    assert exc_bool.value.field == "active"
    assert "must be of type boolean" in exc_bool.value.message

    # Array type check
    with pytest.raises(KbMcpError) as exc_arr:
        handler._validate_tool_arguments_schema(dummy_spec, {"tags": "single-tag"})
    assert exc_arr.value.field == "tags"
    assert "must be of type array" in exc_arr.value.message

    # Pattern check
    with pytest.raises(KbMcpError) as exc_pat:
        handler._validate_tool_arguments_schema(dummy_spec, {"plan_sha256": "bad-sha"})
    assert exc_pat.value.field == "plan_sha256"
    assert "does not match required format pattern" in exc_pat.value.message
    assert exc_pat.value.cli_example is not None
    assert "<64-hex-sha256>" in exc_pat.value.cli_example


@pytest.mark.asyncio
async def test_protocol_tool_not_found_progressive_disclosure() -> None:
    """Verify tool not found on surface suggests closest match and formats CLI example."""
    reg = ToolRegistry(Surface.DOCS)

    async def dummy_handler(args: dict[str, Any]) -> str:
        return "ok"

    reg.register(
        ToolSpec(
            name="search",
            description="Search docs",
            surface=Surface.DOCS,
            input_schema={},
            handler=dummy_handler,
        )
    )
    reg.register(
        ToolSpec(
            name="update",
            description="Update doc",
            surface=Surface.DOCS,
            input_schema={},
            handler=dummy_handler,
        )
    )

    store = InMemorySessionStore()
    session = store.create_session(Surface.DOCS)
    handler = McpProtocolHandler(
        surface=Surface.DOCS,
        registry=reg,
        session_store=store,
        settings=McpSettings(),
    )

    # Call 'search_docs' which is close to 'search'
    resp = await handler._handle_tools_call(
        req_id=1,
        params={"name": "search_docs", "arguments": {}},
        session_id=session.session_id,
    )
    data = bytes(resp.body).decode("utf-8")
    assert "NOT_FOUND" in data
    assert "did_you_mean:" in data
    assert "did_you_mean: [search]" in data
    assert "cli_example: kanban-cli-docs search" in data


def test_enrich_progressive_disclosure_domain_errors() -> None:
    """Verify KanbanApiClient._enrich_progressive_disclosure domain mappings."""
    # 1. INVALID_TRANSITION
    trans_enriched = KanbanApiClient._enrich_progressive_disclosure(
        McpErrorCode.INVALID_TRANSITION,
        {"extra": {"valid_states": ["Todo", "In Progress", "Done"]}},
        hint_str=None,
        extra_dict={},
    )
    assert trans_enriched["valid_options"] == ["Todo", "In Progress", "Done"]
    assert "Allowed target states: Todo, In Progress, Done" in trans_enriched["fix_hint"]
    assert '--to-state="Todo"' in trans_enriched["cli_example"]

    # 2. CONFLICT_ETAG
    conflict_extra: dict[str, Any] = {}
    conflict_enriched = KanbanApiClient._enrich_progressive_disclosure(
        McpErrorCode.CONFLICT_ETAG,
        {"current_etag": "sha256-current-version"},
        hint_str=None,
        extra_dict=conflict_extra,
    )
    assert conflict_extra["current_etag"] == "sha256-current-version"
    assert "Retry with current ETag: sha256-current-version" in conflict_enriched["fix_hint"]
    assert '--if-match="sha256-current-version"' in conflict_enriched["cli_example"]

    # 3. ALREADY_PROMOTED
    promoted_extra: dict[str, Any] = {}
    promoted_enriched = KanbanApiClient._enrich_progressive_disclosure(
        McpErrorCode.ALREADY_PROMOTED,
        {"target_doc_key": "DOC-99"},
        hint_str=None,
        extra_dict=promoted_extra,
    )
    assert promoted_extra["target_doc_key"] == "DOC-99"
    assert "Sticky has already been promoted to Doc 'DOC-99'" in promoted_enriched["fix_hint"]
    assert 'kanban-cli-docs update --id="DOC-99"' in promoted_enriched["cli_example"]

    # 4. NOT_FOUND without fix_hint
    nf_enriched = KanbanApiClient._enrich_progressive_disclosure(
        McpErrorCode.NOT_FOUND,
        {},
        hint_str=None,
        extra_dict={},
    )
    assert "Verify identifier or use search tool" in nf_enriched["fix_hint"]

    # 5. Fallback branches when details missing or custom fix_hint provided
    custom_enriched = KanbanApiClient._enrich_progressive_disclosure(
        McpErrorCode.INVALID_TRANSITION,
        {
            "field": "to_state",
            "fix_hint": "Custom transition hint",
            "cli_example": "custom-cli",
            "did_you_mean": ["Backlog"],
            "closest_match": [{"text": "candidate"}],
        },
        hint_str=None,
        extra_dict={},
    )
    assert custom_enriched["field"] == "to_state"
    assert custom_enriched["fix_hint"] == "Custom transition hint"
    assert custom_enriched["cli_example"] == "custom-cli"
    assert custom_enriched["did_you_mean"] == ["Backlog"]
    assert custom_enriched["closest_match"] == [{"text": "candidate"}]

    # 6. CONFLICT_ETAG and ALREADY_PROMOTED without identifiers
    empty_conflict = KanbanApiClient._enrich_progressive_disclosure(
        McpErrorCode.CONFLICT_ETAG, {}, hint_str=None, extra_dict={}
    )
    assert empty_conflict["cli_example"] is None

    empty_promoted = KanbanApiClient._enrich_progressive_disclosure(
        McpErrorCode.ALREADY_PROMOTED, {}, hint_str=None, extra_dict={}
    )
    assert empty_promoted["cli_example"] is None

    # 7. NOT_FOUND with existing fix_hint
    existing_nf = KanbanApiClient._enrich_progressive_disclosure(
        McpErrorCode.NOT_FOUND, {}, hint_str="Custom not found hint", extra_dict={}
    )
    assert existing_nf["fix_hint"] == "Custom not found hint"


def test_docs_apply_patch_progressive_disclosure() -> None:
    """Verify _diff_patch_content error paths for PATCH_TARGET_NOT_FOUND and AMBIGUOUS."""
    from mcp.surfaces.docs.update import _diff_patch_content

    doc_body = "Line 1: Introduction\nLine 2: Overview\nLine 3: Conclusion\n"

    # 1. Target not found -> suggestions with closest match
    with pytest.raises(KbMcpError) as exc_nf:
        _diff_patch_content(doc_body, "Line 2: Overvew", "Line 2: Revised", "sha1", "sha1")
    err_nf = exc_nf.value
    assert err_nf.code == McpErrorCode.PATCH_TARGET_NOT_FOUND
    assert err_nf.closest_match is not None
    assert len(err_nf.closest_match) > 0
    assert err_nf.fix_hint is not None
    assert "closest_match suggestions" in err_nf.fix_hint
    assert err_nf.cli_example is not None

    # 2. Target ambiguous (multiple matches)
    ambiguous_body = "apple\nbanana\napple\ncherry\n"
    with pytest.raises(KbMcpError) as exc_amb:
        _diff_patch_content(ambiguous_body, "apple", "orange", "sha1", "sha1")
    err_amb = exc_amb.value
    assert err_amb.code == McpErrorCode.PATCH_TARGET_AMBIGUOUS
    assert err_amb.fix_hint is not None
    assert "appears 2 times" in err_amb.fix_hint
    assert err_amb.cli_example is not None


def test_admin_map_cycle_error_progressive_disclosure() -> None:
    """Verify _map_cycle_error domain mappings with progressive disclosure."""
    from mcp.surfaces.admin.manage_cycles_and_modules import _map_cycle_error

    # 1. INVALID_CYCLE_TRANSITION
    orig_err = KbMcpError(McpErrorCode.INVALID_TRANSITION, "Invalid state jump")
    mapped = _map_cycle_error(orig_err)
    assert mapped.code == McpErrorCode.INVALID_TRANSITION
    assert mapped.valid_options == ["upcoming", "started", "completed"]
    assert "Cycle state transition must follow monotonicity" in (mapped.fix_hint or "")
    assert mapped.cli_example is not None

    # 2. MODULES_DISABLED
    orig_mod = KbMcpError(McpErrorCode.MODULES_DISABLED, "Modules disabled")
    mapped_mod = _map_cycle_error(orig_mod)
    assert mapped_mod.code == McpErrorCode.MODULES_DISABLED
    assert "Modules are disabled" in (mapped_mod.fix_hint or "")
    assert mapped_mod.cli_example is not None

    # 3. NOT_FOUND
    orig_nf = KbMcpError(McpErrorCode.NOT_FOUND, "Not found")
    mapped_nf = _map_cycle_error(orig_nf)
    assert mapped_nf.code == McpErrorCode.NOT_FOUND
    assert "Verify identifier or list project cycles/modules" in (mapped_nf.fix_hint or "")
    assert mapped_nf.cli_example is not None


@pytest.mark.asyncio
async def test_jit_help_bypass_pre_dispatch() -> None:
    """Verify action='help' or identifier='help' bypasses pre-dispatch schema validation."""
    reg = ToolRegistry(Surface.AGENT)

    async def dummy_handler(args: dict[str, Any]) -> str:
        return "ok: help rendered"

    spec = ToolSpec(
        name="read_ticket",
        description="Read ticket",
        surface=Surface.AGENT,
        input_schema={
            "type": "object",
            "properties": {
                "identifier": {"type": "string"},
                "fields": {"type": "array"},
            },
            "required": ["identifier"],
            "additionalProperties": False,
        },
        handler=dummy_handler,
    )
    reg.register(spec)
    store = InMemorySessionStore()
    handler = McpProtocolHandler(
        surface=Surface.AGENT,
        registry=reg,
        session_store=store,
        settings=McpSettings(),
    )

    # Calling with identifier='help' without other required fields does NOT fail
    # pre-dispatch validation
    handler._validate_tool_arguments_schema(spec, {"identifier": "help"})


@pytest.mark.asyncio
async def test_protocol_pre_dispatch_special_cases() -> None:
    """Test state hint, custom_fields hint, camelCase conversion, and no-fuzzy match."""
    reg = ToolRegistry(Surface.AGENT)

    async def dummy_handler(args: dict[str, Any]) -> str:
        return "ok"

    spec = ToolSpec(
        name="update_ticket",
        description="Update ticket",
        surface=Surface.AGENT,
        input_schema={
            "type": "object",
            "properties": {
                "identifier": {"type": "string"},
                "summary": {"type": "string"},
                "ticket_priority": {"type": "string"},
                "status_enum": {
                    "type": "string",
                    "enum": ["ACTIVE", "INACTIVE"],
                },
                "optional_note": {
                    "type": ["string", "null"],
                },
            },
            "required": ["identifier"],
            "additionalProperties": False,
        },
        handler=dummy_handler,
    )
    reg.register(spec)
    store = InMemorySessionStore()
    handler = McpProtocolHandler(
        surface=Surface.AGENT,
        registry=reg,
        session_store=store,
        settings=McpSettings(),
    )

    # 1. 'state' in update_ticket hints use transition_ticket
    with pytest.raises(KbMcpError) as exc_state:
        handler._validate_tool_arguments_schema(
            spec, {"identifier": "KAN-1", "state": "Done"}
        )
    assert exc_state.value.hint == "use transition_ticket"
    assert "use transition_ticket" in (exc_state.value.fix_hint or "")

    # 2. 'custom_fields' in update_ticket hints Phase 5
    with pytest.raises(KbMcpError) as exc_cf:
        handler._validate_tool_arguments_schema(
            spec, {"identifier": "KAN-1", "custom_fields": {"priority": 1}}
        )
    assert exc_cf.value.hint == "custom fields arrive in Phase 5"
    assert "custom fields arrive in Phase 5" in (exc_cf.value.fix_hint or "")

    # 3. camelCase 'ticketPriority' converted to snake_case 'ticket_priority'
    with pytest.raises(KbMcpError) as exc_camel:
        handler._validate_tool_arguments_schema(
            spec, {"identifier": "KAN-1", "ticketPriority": "High"}
        )
    assert exc_camel.value.did_you_mean == ["ticket_priority"]

    # 4. Unknown param with no close matches
    with pytest.raises(KbMcpError) as exc_none:
        handler._validate_tool_arguments_schema(
            spec, {"identifier": "KAN-1", "zzzz_completely_unknown_999": "val"}
        )
    assert exc_none.value.did_you_mean is None
    assert "Valid options:" in (exc_none.value.fix_hint or "")

    # 5. Enum with no close match
    with pytest.raises(KbMcpError) as exc_enum:
        handler._validate_tool_arguments_schema(
            spec, {"identifier": "KAN-1", "status_enum": "zzzzzz"}
        )
    assert exc_enum.value.did_you_mean is None
    assert "Valid options: ['ACTIVE', 'INACTIVE']" in (exc_enum.value.fix_hint or "")

    # 6. Nullable union with None passes
    handler._validate_tool_arguments_schema(
        spec, {"identifier": "KAN-1", "optional_note": None}
    )


@pytest.mark.asyncio
async def test_protocol_pre_dispatch_object_type_and_enum_fuzzy() -> None:
    """Verify object type check failure and direct fuzzy enum matches."""
    reg = ToolRegistry(Surface.ADMIN)

    async def dummy_handler(args: dict[str, Any]) -> str:
        return "ok"

    dummy_spec = ToolSpec(
        name="test_obj_tool",
        description="Test obj tool",
        surface=Surface.ADMIN,
        input_schema={
            "type": "object",
            "properties": {
                "config": {"type": "object"},
                "status": {"type": "string", "enum": ["ACTIVE", "INACTIVE"]},
            },
        },
        handler=dummy_handler,
    )
    reg.register(dummy_spec)
    store = InMemorySessionStore()
    handler = McpProtocolHandler(
        surface=Surface.ADMIN,
        registry=reg,
        session_store=store,
        settings=McpSettings(),
    )

    # Object type check failure
    with pytest.raises(KbMcpError) as exc_obj:
        handler._validate_tool_arguments_schema(dummy_spec, {"config": "not-a-dict"})
    assert exc_obj.value.field == "config"
    assert "must be of type object" in exc_obj.value.message
    assert exc_obj.value.cli_example is not None
    assert "--config='{}'" in exc_obj.value.cli_example

    # Enum direct fuzzy match (e.g. ACTIVEX matches ACTIVE)
    with pytest.raises(KbMcpError) as exc_enum:
        handler._validate_tool_arguments_schema(dummy_spec, {"status": "ACTIVEX"})
    assert exc_enum.value.field == "status"
    assert exc_enum.value.did_you_mean == ["ACTIVE"]


@pytest.mark.asyncio
async def test_docs_update_sticky_diff_patch_and_links_coverage() -> None:
    """Verify sticky diff patching, color, and link updates in update_handler."""
    from mcp.surfaces.docs.update import update_handler

    sticky_id = str(uuid.uuid4())

    async def mock_handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if f"/api/v1/stickies/{sticky_id}" in url and request.method == "GET":
            return httpx.Response(
                200,
                json={
                    "id": sticky_id,
                    "body_markdown": "line one\nline two",
                    "body_sha256": "sha123",
                    "color_token": "sky",
                    "project_id": "018f-p1",
                },
            )
        if f"/api/v1/stickies/{sticky_id}" in url and request.method == "PATCH":
            return httpx.Response(
                200,
                json={
                    "id": sticky_id,
                    "body_markdown": "line one\nline replaced",
                    "body_sha256": "sha456",
                    "color_token": "coral",
                    "project_id": "018f-p1",
                },
            )
        if f"/api/v1/objects/{sticky_id}/links" in url:
            if request.method == "GET":
                return httpx.Response(200, json={"outbound": []})
            if request.method == "POST":
                return httpx.Response(201, json={"status": "linked"})
        return httpx.Response(404, json={"detail": "not found"})

    client = KanbanApiClient(
        McpSettings(mode="standalone_inprocess"),
        transport=httpx.MockTransport(mock_handler),
    )

    res = await update_handler(
        {
            "id": sticky_id,
            "type": "STICKY",
            "original_text": "line two",
            "replacement_text": "line replaced",
            "color": "coral",
            "links": ["+KAN-10"],
        },
        client=client,
    )
    assert res["status"] == "updated"
    assert res["kind"] == "sticky"
    assert res["links"] == [{"action": "added", "target": "KAN-10", "link_type": "RELATES_TO"}]



