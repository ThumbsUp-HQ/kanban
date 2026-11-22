"""Tests for canonical OpenAPI specification exporter (KB-P3-33)."""

from __future__ import annotations

import json
import runpy
import sys
import warnings
from typing import TYPE_CHECKING, Any

from kanban.api_docs import (
    _group_operations_by_tag,
    _render_opblock,
    _render_problem_schemas_section,
    _render_redoc_endpoint_card,
    _render_security_schemes_section,
    get_redoc_html,
    get_swagger_ui_html,
    render_redoc_html,
    render_swagger_ui_html,
)
from kanban.ops.build_info import resolve_platform_version
from kanban.ops.openapi_builder import _enrich_paths
from kanban.tools.export_openapi import export_openapi, main

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def test_export_openapi_valid_json() -> None:
    """Verify export_openapi produces valid JSON document with required metadata."""
    raw = export_openapi()
    data: dict[str, Any] = json.loads(raw)

    assert "openapi" in data
    assert "info" in data
    assert "paths" in data
    assert data["info"]["title"] == "👍kanban API"


def test_export_openapi_deterministic() -> None:
    """Verify export_openapi generates identical deterministic string on multiple calls."""
    run1 = export_openapi()
    run2 = export_openapi()

    assert run1 == run2


def test_export_openapi_contains_issue_routes() -> None:
    """Verify export_openapi contains issue paths from KB-P3-02."""
    raw = export_openapi()
    data: dict[str, Any] = json.loads(raw)
    paths: dict[str, Any] = data["paths"]

    assert "/api/v1/issues/{issue_key}" in paths
    assert "get" in paths["/api/v1/issues/{issue_key}"]
    assert "patch" in paths["/api/v1/issues/{issue_key}"]


def test_export_openapi_cli_to_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify CLI main exports document to target file when argument provided."""
    target_file = tmp_path / "openapi.json"
    monkeypatch.setattr("sys.argv", ["export_openapi", str(target_file)])

    main()

    assert target_file.exists()
    content = target_file.read_text(encoding="utf-8")
    assert '"/api/v1/issues/{issue_key}"' in content


def test_export_openapi_cli_to_stdout(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify CLI main writes document to stdout when no argument provided."""
    monkeypatch.setattr("sys.argv", ["export_openapi"])

    main()

    captured = capsys.readouterr()
    assert '"/api/v1/issues/{issue_key}"' in captured.out


def test_export_openapi_module_main_execution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify python -m kanban.tools.export_openapi executes main via __name__ == '__main__'."""
    target_file = tmp_path / "main_out.json"
    monkeypatch.setattr("sys.argv", ["export_openapi", str(target_file)])

    saved = sys.modules.pop("kanban.tools.export_openapi", None)
    try:
        runpy.run_module("kanban.tools.export_openapi", run_name="__main__")
    finally:
        if saved is not None:
            sys.modules["kanban.tools.export_openapi"] = saved

    assert target_file.exists()
    content = target_file.read_text(encoding="utf-8")
    assert '"/api/v1/issues/{issue_key}"' in content


def test_export_openapi_issue_and_activity_response_schemas() -> None:
    """Verify IssueResponse and ActivityItemResponse schemas contain documented properties."""
    raw = export_openapi()
    data: dict[str, Any] = json.loads(raw)
    schemas: dict[str, Any] = data["components"]["schemas"]

    assert "IssueResponse" in schemas
    issue_schema = schemas["IssueResponse"]
    assert (
        issue_schema.get("description")
        == "Canonical issue representation returned by all issue endpoints."
    )
    assert "properties" in issue_schema
    assert len(issue_schema["properties"]) >= 20
    assert "id" in issue_schema["properties"]
    assert "key" in issue_schema["properties"]

    assert "ActivityItemResponse" in schemas
    activity_schema = schemas["ActivityItemResponse"]
    assert (
        activity_schema.get("description")
        == "A single activity feed item with actor and comment hydration."
    )
    assert "properties" in activity_schema
    assert len(activity_schema["properties"]) >= 8


def test_export_openapi_security_schemes_and_top_level_security() -> None:
    """Verify OpenAPI document registers securitySchemes and default security requirements."""
    raw = export_openapi()
    data: dict[str, Any] = json.loads(raw)
    components: dict[str, Any] = data.get("components", {})
    schemes: dict[str, Any] = components.get("securitySchemes", {})

    # SessionCookieAuth
    assert "SessionCookieAuth" in schemes
    cookie_auth = schemes["SessionCookieAuth"]
    assert cookie_auth["type"] == "apiKey"
    assert cookie_auth["in"] == "cookie"
    assert cookie_auth["name"] == "__Host-kb_session"

    # CsrfHeaderAuth
    assert "CsrfHeaderAuth" in schemes
    csrf_auth = schemes["CsrfHeaderAuth"]
    assert csrf_auth["type"] == "apiKey"
    assert csrf_auth["in"] == "header"
    assert csrf_auth["name"] == "X-CSRF-Token"

    # BearerTokenAuth
    assert "BearerTokenAuth" in schemes
    bearer_auth = schemes["BearerTokenAuth"]
    assert bearer_auth["type"] == "http"
    assert bearer_auth["scheme"] == "bearer"

    # Top-level security requirement
    assert "security" in data
    assert isinstance(data["security"], list)
    assert len(data["security"]) >= 1


def test_export_openapi_public_routes_empty_security() -> None:
    """Verify unauthenticated/public endpoints have explicit empty security requirement."""
    raw = export_openapi()
    data: dict[str, Any] = json.loads(raw)
    paths: dict[str, Any] = data["paths"]

    public_probe_paths = [
        ("/healthz", "get"),
        ("/readyz", "get"),
        ("/api/v1/system/platform-summary", "get"),
        ("/api/v1/auth/cards", "get"),
        ("/api/v1/auth/session", "get"),
        ("/oauth/token", "post"),
    ]

    for path, method in public_probe_paths:
        if path in paths and method in paths[path]:
            op = paths[path][method]
            assert op.get("security") == [], (
                f"Expected security: [] on public route {path} {method}"
            )


def test_export_openapi_rfc7807_responses_and_schemas() -> None:
    """Verify ProblemDetails schema and 401, 412, and 429 RFC 7807 responses are registered."""
    raw = export_openapi()
    data: dict[str, Any] = json.loads(raw)
    schemas: dict[str, Any] = data["components"]["schemas"]
    paths: dict[str, Any] = data["paths"]

    assert "ProblemDetails" in schemas
    problem_schema = schemas["ProblemDetails"]
    assert "type" in problem_schema.get("properties", {})
    assert "title" in problem_schema.get("properties", {})
    assert "status" in problem_schema.get("properties", {})

    # Authenticated route must define 401 ProblemDetails
    issue_op = paths["/api/v1/issues/{issue_key}"]["get"]
    assert "401" in issue_op["responses"]
    assert "application/problem+json" in issue_op["responses"]["401"]["content"]

    # ETag / If-Match route must define 412 Precondition Failed ProblemDetails
    patch_op = paths["/api/v1/issues/{issue_key}"]["patch"]
    assert "412" in patch_op["responses"]
    assert "application/problem+json" in patch_op["responses"]["412"]["content"]

    # Rate-limited endpoint must define 429 Too Many Requests ProblemDetails
    login_op = paths["/api/v1/auth/local/login"]["post"]
    assert "429" in login_op["responses"]
    assert "application/problem+json" in login_op["responses"]["429"]["content"]


def test_export_openapi_build_info_metadata_and_hashes() -> None:
    """Verify OpenAPI info object exposes version 2.0.0, commit, and bundle hash."""
    raw = export_openapi()
    data: dict[str, Any] = json.loads(raw)
    info: dict[str, Any] = data["info"]

    assert info["version"] == resolve_platform_version()
    assert "x-build-commit" in info
    assert info["x-build-commit"] is not None
    assert "x-openapi-bundle-hash" in info
    assert len(info["x-openapi-bundle-hash"]) == 64


def test_export_openapi_no_duplicate_operation_ids() -> None:
    """Verify zero duplicate operationId warnings and distinct agent validation IDs."""
    with warnings.catch_warnings(record=True) as recorded_warnings:
        warnings.simplefilter("always")
        raw = export_openapi()
        data: dict[str, Any] = json.loads(raw)

        duplicate_warnings = [
            w for w in recorded_warnings if "Duplicate Operation ID" in str(w.message)
        ]
        assert not duplicate_warnings, (
            f"Found duplicate operation ID warnings: {duplicate_warnings}"
        )

    paths: dict[str, Any] = data["paths"]
    colon_id = paths["/api/v1/admin/agent-definitions/{agent}:validate"]["post"]["operationId"]
    slash_id = paths["/api/v1/admin/agent-definitions/{agent}/validate"]["post"]["operationId"]

    assert colon_id == "validate_agent_definition_colon"
    assert slash_id == "validate_agent_definition_slash"
    assert colon_id != slash_id


def test_openapi_builder_enrich_paths_defensive_types() -> None:
    """Verify _enrich_paths handles non-dict path items and non-method keys gracefully."""
    mock_schema: dict[str, Any] = {
        "paths": {
            "/invalid": "not-a-dict",
            "/valid": {
                "parameters": "not-a-method-dict",
                "get": {"summary": "valid get"},
            },
        }
    }
    _enrich_paths(
        mock_schema,
        {"401": {"desc": "401"}, "412": {"desc": "412"}, "429": {"desc": "429"}},
    )
    valid_path = mock_schema["paths"]["/valid"]
    assert isinstance(valid_path, dict)
    assert "security" in valid_path["get"]


def test_export_openapi_openid_configuration_public() -> None:
    """Verify /.well-known/openid-configuration is unauthenticated with security: []."""
    raw = export_openapi()
    data: dict[str, Any] = json.loads(raw)
    paths: dict[str, Any] = data["paths"]

    assert "/.well-known/openid-configuration" in paths
    op = paths["/.well-known/openid-configuration"]["get"]
    assert op.get("security") == []
    assert "401" not in op.get("responses", {})


def test_api_docs_swagger_and_redoc_security_and_problem_schemas() -> None:
    """Verify Swagger UI and ReDoc render security schemes, ProblemDetails, and single branding."""
    raw = export_openapi()
    data: dict[str, Any] = json.loads(raw)

    swagger_html = render_swagger_ui_html(data)
    assert "👍 👍" not in swagger_html
    assert "SessionCookieAuth" in swagger_html
    assert "CsrfHeaderAuth" in swagger_html
    assert "BearerTokenAuth" in swagger_html
    assert "ProblemDetails" in swagger_html
    assert "401" in swagger_html
    assert "412" in swagger_html
    assert "429" in swagger_html
    assert "Authentication &amp; Security Schemes" in swagger_html
    assert "Canonical Error &amp; Problem Schemas" in swagger_html

    redoc_html = render_redoc_html(data)
    assert "👍 👍" not in redoc_html
    assert "SessionCookieAuth" in redoc_html
    assert "CsrfHeaderAuth" in redoc_html
    assert "BearerTokenAuth" in redoc_html
    assert "ProblemDetails" in redoc_html
    assert "Authentication &amp; Security Schemes" in redoc_html
    assert "Canonical Error &amp; Problem Schemas" in redoc_html

    # Test cache retrieval
    assert get_swagger_ui_html(data) == get_swagger_ui_html(data)
    assert get_redoc_html(data) == get_redoc_html(data)

    # Test edge cases and helper branches
    assert _render_security_schemes_section({}) == []
    empty_problem_section = _render_problem_schemas_section({})
    assert "Canonical Error &amp; Problem Schemas" in "".join(empty_problem_section)

    mock_problem_section = _render_problem_schemas_section(
        {
            "ProblemDetails": {
                "properties": {
                    "code": {"type": "string", "description": "Machine-readable error code"},
                    "detail": {"type": "string", "title": "Human-readable explanation"},
                }
            }
        }
    )
    combined_mock = "".join(mock_problem_section)
    assert "ProblemDetails Model Specification" in combined_mock
    assert "Machine-readable error code" in combined_mock

    # Test _group_operations_by_tag with non-standard method
    tags_map = _group_operations_by_tag(
        {
            "/test": {
                "head": {"summary": "ignore head"},
                "get": {"summary": "get test", "tags": ["test-tag"]},
            }
        }
    )
    assert "test-tag" in tags_map
    assert len(tags_map["test-tag"]) == 1

    # Test minimal endpoint card without desc, params, or responses
    minimal_card = "".join(
        _render_opblock(
            "GET",
            "/minimal",
            {"summary": "Minimal"},
        )
    )
    assert "curl -X GET" in minimal_card

    # Test redoc endpoint card with desc, params, and responses
    detailed_redoc = "".join(
        _render_redoc_endpoint_card(
            "POST",
            "/detailed",
            {
                "summary": "Detailed",
                "description": "Endpoint description",
                "parameters": [{"name": "q", "in": "query", "schema": {"type": "string"}}],
                "responses": {"200": {"description": "OK"}},
            },
        )
    )
    assert "Endpoint description" in detailed_redoc
