# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Feature unit tests for MCP write tools secret push-protection (KB-SEC-SCRUB-01)."""

from __future__ import annotations

import json

import pytest

from mcp.errors import KbMcpError, McpErrorCode
from mcp.internal_client import KanbanApiClient
from mcp.settings import McpSettings
from mcp.surfaces.agent.add_comment import _validate_add_comment_arguments
from mcp.surfaces.agent.complete_work import _validate_complete_work_arguments
from mcp.surfaces.agent.create_ticket import _validate_node_scalars
from mcp.surfaces.docs.create import create_handler
from mcp.surfaces.docs.update import update_handler


def test_mcp_create_ticket_rejects_secrets_in_summary() -> None:
    """Verify create_ticket rejects secret credentials in summary field."""
    secret = "ghp_1234567890abcdef1234567890abcdef1234"
    node = {
        "summary": f"Create ticket with token {secret}",
        "description_markdown": "Normal description text",
    }
    with pytest.raises(KbMcpError) as exc_info:
        _validate_node_scalars(node)

    err = exc_info.value
    assert err.code == McpErrorCode.SECRET_DETECTED_IN_PAYLOAD
    assert err.field == "summary"
    assert err.extra is not None
    assert err.extra["rule_id"] == "GITHUB_TOKEN"
    assert secret not in err.message
    assert err.hint is not None


def test_mcp_create_ticket_rejects_secrets_in_description() -> None:
    """Verify create_ticket rejects secret credentials in description field."""
    key = "AKIAIOSFODNN7EXAMPLE"
    node = {
        "summary": "Legitimate summary without secrets",
        "description_markdown": f"AWS Key: {key}",
    }
    with pytest.raises(KbMcpError) as exc_info:
        _validate_node_scalars(node)

    err = exc_info.value
    assert err.code == McpErrorCode.SECRET_DETECTED_IN_PAYLOAD
    assert err.field == "description_markdown"
    assert err.extra is not None
    assert err.extra["rule_id"] == "AWS_ACCESS_KEY"
    assert key not in err.message


def test_mcp_add_comment_rejects_secrets() -> None:
    """Verify add_comment rejects secret credentials in comment body."""
    secret = "glpat-1234567890abcdefghij"
    arguments = {
        "identifier": "KAN-42",
        "body_markdown": f"Here is the token: {secret}",
    }
    with pytest.raises(KbMcpError) as exc_info:
        _validate_add_comment_arguments(arguments)

    err = exc_info.value
    assert err.code == McpErrorCode.SECRET_DETECTED_IN_PAYLOAD
    assert err.field == "body_markdown"
    assert err.extra is not None
    assert err.extra["rule_id"] == "GITLAB_TOKEN"
    assert secret not in err.message


def test_mcp_complete_work_rejects_secrets_in_summary() -> None:
    """Verify complete_work rejects secret credentials in summary_markdown."""
    secret = "xoxb-" + "123456789012-abcdefghijklmnopqrstuvwx"
    arguments = {
        "identifier": "KAN-42",
        "summary_markdown": f"Finished work. Slack token was {secret}",
        "verification_proof": {
            "qa_dir": "docs/qa/KAN-42/",
            "reality_checker": {"verdict": "READY", "grade": "A"},
        },
    }
    with pytest.raises(KbMcpError) as exc_info:
        _validate_complete_work_arguments(arguments)

    err = exc_info.value
    assert err.code == McpErrorCode.SECRET_DETECTED_IN_PAYLOAD
    assert err.field == "summary_markdown"
    assert err.extra is not None
    assert err.extra["rule_id"] == "SLACK_TOKEN"
    assert secret not in err.message


@pytest.mark.asyncio
async def test_mcp_docs_create_rejects_secrets() -> None:
    """Verify docs create tool rejects secrets in title or content."""
    secret = "AIzaSyA1234567890abcdefghijklmnopqrstuv"
    # Secret in title
    with pytest.raises(KbMcpError) as exc_info:
        await create_handler(
            {"type": "DOC", "title": f"Doc with {secret}", "project": "KAN", "content": "body"}
        )
    assert exc_info.value.code == McpErrorCode.SECRET_DETECTED_IN_PAYLOAD
    assert exc_info.value.field == "title"

    # Secret in content
    with pytest.raises(KbMcpError) as exc_info:
        await create_handler(
            {
                "type": "DOC",
                "title": "Clean Title",
                "project": "KAN",
                "content": f"Secret: {secret}",
            }
        )
    assert exc_info.value.code == McpErrorCode.SECRET_DETECTED_IN_PAYLOAD
    assert exc_info.value.field == "content"


@pytest.mark.asyncio
async def test_mcp_docs_update_rejects_secrets() -> None:
    """Verify docs update tool rejects secrets in title or content."""
    dsn = "postgresql://user:pass123456@db:5432/test"
    with pytest.raises(KbMcpError) as exc_info:
        await update_handler({"id": "doc-123", "content": f"Connect via {dsn}"})

    assert exc_info.value.code == McpErrorCode.SECRET_DETECTED_IN_PAYLOAD
    assert exc_info.value.field == "content"
    assert "pass123456" not in exc_info.value.message


def test_mcp_internal_client_maps_upstream_secret_problem() -> None:
    """Verify internal client maps 422 SECRET_DETECTED_IN_PAYLOAD to structured KbMcpError."""
    client = KanbanApiClient(McpSettings())
    problem_payload = {
        "type": "urn:kanban:problem:SECRET_DETECTED_IN_PAYLOAD",
        "title": "Secret Detected In Payload",
        "status": 422,
        "code": "SECRET_DETECTED_IN_PAYLOAD",
        "detail": "Secret material detected in field 'summary' at line 1",
        "field": "summary",
        "rule_id": "GITHUB_TOKEN",
        "secret_kind": "GITHUB_TOKEN",
        "line": 1,
        "fingerprint": "ghp_...1234",
    }
    body_bytes = json.dumps(problem_payload).encode("utf-8")

    with pytest.raises(KbMcpError) as exc_info:
        client._map_upstream_error(422, body_bytes)  # noqa: SLF001

    err = exc_info.value
    assert err.code == McpErrorCode.SECRET_DETECTED_IN_PAYLOAD
    assert err.field == "summary"
    assert err.extra is not None
    assert err.extra["rule_id"] == "GITHUB_TOKEN"
    assert err.extra["secret_kind"] == "GITHUB_TOKEN"
    assert err.extra["line"] == 1
    assert err.extra["fingerprint"] == "ghp_...1234"
    assert err.hint is not None
    msg = "Remove sensitive credentials"
    assert msg in err.hint or msg in (err.fix_hint or "")
