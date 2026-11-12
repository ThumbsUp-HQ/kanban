"""Tests for canonical OpenAPI specification exporter (KB-P3-33)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from kanban.tools.export_openapi import export_openapi, main


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


def test_export_openapi_cli_to_file(tmp_path: Path, monkeypatch: Any) -> None:
    """Verify CLI main exports document to target file when argument provided."""
    target_file = tmp_path / "openapi.json"
    monkeypatch.setattr("sys.argv", ["export_openapi", str(target_file)])

    main()

    assert target_file.exists()
    content = target_file.read_text(encoding="utf-8")
    assert '"/api/v1/issues/{issue_key}"' in content
