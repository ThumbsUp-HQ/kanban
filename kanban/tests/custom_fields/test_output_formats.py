# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Unit tests for custom field output format schemas and validators (KB-P5-11, S13.1, S13.2)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import pytest
from pydantic import ValidationError

from kanban.custom_fields.manifest import (
    compute_field_manifest_sha256,
    validate_egress_allowlist,
)
from kanban.custom_fields.output_formats import (
    _METADATA_ADAPTER,
    parse_output_format_metadata,
    validate_field_output_value,
)


def test_01_all_7_output_formats_valid_parsing() -> None:
    """Verify parsing and validation of all 7 supported metadata schemas."""
    # 1. Text
    text_meta = parse_output_format_metadata("text", {"max_length": 100, "monospace": True})
    assert text_meta.format == "text"
    assert validate_field_output_value("text", text_meta, "hello world") == "hello world"

    # 2. Number
    num_meta = parse_output_format_metadata(
        "number",
        {"maximum_fraction_digits": 2, "min_value": 0.0, "max_value": 100.0, "unit_suffix": "ms"},
    )
    assert num_meta.format == "number"
    assert validate_field_output_value("number", num_meta, 42.567) == 42.57

    # 3. Badge
    badge_meta = parse_output_format_metadata(
        "badge",
        {"color_token": "success", "allowed_labels": ["PASS", "FAIL"]},
    )
    assert badge_meta.format == "badge"
    assert validate_field_output_value("badge", badge_meta, "PASS") == "PASS"

    # 4. Markdown snippet
    md_meta = parse_output_format_metadata("markdown_snippet", {"max_chars": 500})
    assert md_meta.format == "markdown_snippet"
    assert (
        validate_field_output_value("markdown_snippet", md_meta, "**bold text**") == "**bold text**"
    )

    # 5. URL
    url_meta = parse_output_format_metadata(
        "url",
        {"allowed_schemes": ["https"], "allowed_host_suffixes": ["example.com"]},
    )
    assert url_meta.format == "url"
    assert (
        validate_field_output_value("url", url_meta, "https://sub.example.com/path")
        == "https://sub.example.com/path"
    )

    # 6. JSON Table
    table_meta = parse_output_format_metadata(
        "json_table",
        {
            "columns": [{"key": "id", "label": "ID"}, {"key": "name", "label": "Name"}],
            "max_rows": 10,
        },
    )
    assert table_meta.format == "json_table"
    table_val = [{"id": 1, "name": "Item A", "extra": "ignored"}]
    cleaned = validate_field_output_value("json_table", table_meta, table_val)
    assert cleaned == [{"id": 1, "name": "Item A"}]

    # 7. Severity Pill
    sev_meta = parse_output_format_metadata("severity_pill", {})
    assert sev_meta.format == "severity_pill"
    sev_val = {"level": "high", "score": 8.5, "label": "High Priority"}
    assert validate_field_output_value("severity_pill", sev_meta, sev_val) == {
        "level": "high",
        "score": 8.5,
        "label": "High Priority",
    }


def test_02_rejection_of_raw_html_and_forbidden_formats() -> None:
    """Test 3: Reject raw HTML, CSS injection, dangerous URI schemes, and script tags."""
    # 1. output_format='html' or 'raw_html' must be rejected
    with pytest.raises(ValueError, match="Invalid output_format"):
        parse_output_format_metadata("html", {})

    with pytest.raises(ValueError, match="Invalid output_format"):
        parse_output_format_metadata("raw_html", {})

    # 2. Badge with arbitrary CSS or hex color in metadata or value rejected
    with pytest.raises(ValidationError):
        parse_output_format_metadata(
            "badge",
            {"color_token": "#ff0000;background:url(x)"},
        )

    badge_meta = parse_output_format_metadata("badge", {"color_token": "neutral"})
    with pytest.raises(ValueError, match="disallowed CSS"):
        validate_field_output_value("badge", badge_meta, "#ff0000;background:url(x)")

    # 3. URL with dangerous schemes or embedded credentials rejected
    url_meta = parse_output_format_metadata("url", {"allowed_schemes": ["https"]})
    with pytest.raises(ValueError, match="URL scheme 'javascript' not allowed"):
        validate_field_output_value("url", url_meta, "javascript:alert(1)")

    with pytest.raises(ValueError, match="URL scheme 'data' not allowed"):
        validate_field_output_value("url", url_meta, "data:text/html,<script>")

    with pytest.raises(ValueError, match="URL with embedded credentials"):
        validate_field_output_value("url", url_meta, "https://user:pass@example.com")

    with pytest.raises(ValueError, match="include a valid hostname"):
        validate_field_output_value("url", url_meta, "https://")

    # Host suffix restriction
    url_suffix_meta = parse_output_format_metadata(
        "url", {"allowed_schemes": ["https"], "allowed_host_suffixes": ["internal.org"]}
    )
    with pytest.raises(ValueError, match="does not match allowed host suffixes"):
        validate_field_output_value("url", url_suffix_meta, "https://evil.com/leak")

    # 4. Markdown snippet sanitization: strips <script>, <img>, and onerror
    md_meta = parse_output_format_metadata("markdown_snippet", {"max_chars": 2000})
    raw_md = "<script>alert(1)</script><img src=x onerror=alert(1)>**ok**"
    sanitized = validate_field_output_value("markdown_snippet", md_meta, raw_md)
    assert isinstance(sanitized, str)
    assert "<script>" not in sanitized
    assert "</script>" not in sanitized
    assert "<img" not in sanitized
    assert "onerror" not in sanitized
    assert "ok" in sanitized


def test_03_boundary_checks() -> None:  # noqa: PLR0915
    """Test 6: Boundary enforcement on script size, json_table bounds, number NaN, egress paths."""
    # 1. Number NaN/Inf rejected
    num_meta = parse_output_format_metadata("number", {})
    with pytest.raises(ValueError, match="Numeric value must be finite"):
        validate_field_output_value("number", num_meta, float("nan"))

    with pytest.raises(ValueError, match="Numeric value must be finite"):
        validate_field_output_value("number", num_meta, float("inf"))

    bool_val = True
    with pytest.raises(TypeError, match="Expected numeric value"):
        validate_field_output_value("number", num_meta, bool_val)

    # Number min / max bounds
    num_bounds = parse_output_format_metadata("number", {"min_value": 10.0, "max_value": 50.0})
    with pytest.raises(ValueError, match="less than minimum"):
        validate_field_output_value("number", num_bounds, 5.0)
    with pytest.raises(ValueError, match="greater than maximum"):
        validate_field_output_value("number", num_bounds, 60.0)

    # 2. json_table column and row boundaries
    # > 10 columns rejected
    too_many_cols = [{"key": f"col_{i}", "label": f"Col {i}"} for i in range(11)]
    with pytest.raises(ValidationError):
        parse_output_format_metadata("json_table", {"columns": too_many_cols})

    # > 50 rows rejected
    table_meta = parse_output_format_metadata(
        "json_table",
        {"columns": [{"key": "c", "label": "Col"}], "max_rows": 50},
    )
    too_many_rows = [{"c": i} for i in range(51)]
    with pytest.raises(ValueError, match="Row count"):
        validate_field_output_value("json_table", table_meta, too_many_rows)

    # Nested structure in json_table cell rejected
    with pytest.raises(TypeError, match="nested structure"):
        validate_field_output_value("json_table", table_meta, [{"c": {"nested": "dict"}}])

    # Script tag in json_table cell rejected
    with pytest.raises(ValueError, match="forbidden script tag"):
        validate_field_output_value("json_table", table_meta, [{"c": "<script>alert(1)</script>"}])

    # 3. Severity pill boundaries
    sev_meta = parse_output_format_metadata("severity_pill", {})
    with pytest.raises(ValueError, match="Invalid severity level"):
        validate_field_output_value("severity_pill", sev_meta, {"level": "unknown"})

    with pytest.raises(
        ValueError, match=r"Severity score must be finite and between 0\.0 and 10\.0"
    ):
        validate_field_output_value("severity_pill", sev_meta, {"level": "low", "score": 15.0})

    with pytest.raises(ValueError, match="Severity label must be a string of at most 32"):
        validate_field_output_value("severity_pill", sev_meta, {"level": "low", "label": "x" * 33})

    with pytest.raises(ValueError, match="Severity label cannot contain HTML"):
        validate_field_output_value(
            "severity_pill", sev_meta, {"level": "low", "label": "<b>bold</b>"}
        )

    # 4. Egress allowlist boundaries
    with pytest.raises(ValueError, match="Path traversal"):
        validate_egress_allowlist(["/api/v1/../admin"])

    with pytest.raises(ValueError, match="does not match required pattern"):
        validate_egress_allowlist(["https://evil.com/leak"])

    with pytest.raises(ValueError, match="contains whitespace"):
        validate_egress_allowlist(["/api/v1/projects "])

    with pytest.raises(ValueError, match="Query parameters"):
        validate_egress_allowlist(["/api/v1/projects?all=true"])

    with pytest.raises(ValueError, match="exceeds maximum allowed"):
        validate_egress_allowlist([f"/api/v1/ep_{i}" for i in range(17)])

    # Valid egress paths cleaned and sorted
    cleaned = validate_egress_allowlist(["/api/v1/issues", "/api/v1/cycles", "/api/v1/issues"])
    assert cleaned == ["/api/v1/cycles", "/api/v1/issues"]

    # 5. Manifest calculation: editing 1 byte of script_source changes manifest_sha256
    hash1 = compute_field_manifest_sha256(
        script_source="export default function() { return 1; }",
        output_format="number",
        output_format_metadata={"maximum_fraction_digits": 0},
    )
    hash2 = compute_field_manifest_sha256(
        script_source="export default function() { return 2; }",
        output_format="number",
        output_format_metadata={"maximum_fraction_digits": 0},
    )
    assert len(hash1) == 32
    assert len(hash2) == 32
    assert hash1 != hash2


def test_04_schema_parity() -> None:
    """Test 7: Committed output-format-metadata-v1.json matches live Pydantic JSON Schema."""
    schema_path = (
        Path(__file__).resolve().parents[2]
        / "custom_fields"
        / "schemas"
        / "output-format-metadata-v1.json"
    )
    assert schema_path.exists(), f"Schema file not found at {schema_path}"

    committed_schema = json.loads(schema_path.read_text(encoding="utf-8"))
    live_schema = _METADATA_ADAPTER.json_schema()

    assert committed_schema == live_schema, "Committed JSON Schema differs from live Pydantic model"


def test_05_format_and_cell_validators() -> None:
    """Test error branches and type guards across output_formats."""
    # 1. Invalid format in parse_output_format_metadata
    with pytest.raises(ValueError, match="Invalid output_format"):
        parse_output_format_metadata("unsupported_fmt", {})

    # 2. Number bounds check_finite
    with pytest.raises(ValueError, match="Bound values must be finite"):
        parse_output_format_metadata("number", {"min_value": float("nan")})

    # 3. Badge allowed_labels check
    with pytest.raises(ValueError, match="between 1 and 64"):
        parse_output_format_metadata("badge", {"color_token": "neutral", "allowed_labels": [""]})

    with pytest.raises(ValueError, match="between 1 and 64"):
        parse_output_format_metadata(
            "badge", {"color_token": "neutral", "allowed_labels": ["x" * 65]}
        )

    with pytest.raises(ValueError, match="forbidden CSS"):
        parse_output_format_metadata(
            "badge", {"color_token": "neutral", "allowed_labels": ["bad;css"]}
        )

    # 4. validate_field_output_value unsupported format
    dummy_meta = parse_output_format_metadata("text", {})
    with pytest.raises(ValueError, match="Unsupported output format"):
        validate_field_output_value("nonexistent", dummy_meta, "val")

    # 5. Type errors for non-str inputs where str expected
    text_meta = parse_output_format_metadata("text", {"max_length": 10})
    with pytest.raises(TypeError, match="Expected str for 'text'"):
        validate_field_output_value("text", text_meta, 123)

    with pytest.raises(ValueError, match="exceeds configured max_length"):
        validate_field_output_value("text", text_meta, "a" * 11)

    badge_meta = parse_output_format_metadata(
        "badge", {"color_token": "info", "allowed_labels": ["OK"]}
    )
    with pytest.raises(TypeError, match="Expected str for 'badge'"):
        validate_field_output_value("badge", badge_meta, 999)

    with pytest.raises(ValueError, match="between 1 and 64"):
        validate_field_output_value("badge", badge_meta, "   ")

    with pytest.raises(ValueError, match="between 1 and 64"):
        validate_field_output_value("badge", badge_meta, "x" * 65)

    with pytest.raises(ValueError, match="not in allowed_labels"):
        validate_field_output_value("badge", badge_meta, "NOT_OK")

    md_meta = parse_output_format_metadata("markdown_snippet", {"max_chars": 20})
    with pytest.raises(TypeError, match="Expected str for 'markdown_snippet'"):
        validate_field_output_value("markdown_snippet", md_meta, ["not", "str"])

    with pytest.raises(ValueError, match="exceeds max_chars"):
        validate_field_output_value("markdown_snippet", md_meta, "a" * 25)

    url_meta = parse_output_format_metadata("url", {"allowed_schemes": ["https"]})
    with pytest.raises(TypeError, match="Expected str for 'url'"):
        validate_field_output_value("url", url_meta, 12345)

    # 6. JSON table type errors and non-finite cells
    table_meta = parse_output_format_metadata(
        "json_table", {"columns": [{"key": "c", "label": "C"}]}
    )
    with pytest.raises(TypeError, match="Expected list of dicts"):
        validate_field_output_value("json_table", table_meta, "not a list")

    with pytest.raises(TypeError, match="must be a dict"):
        validate_field_output_value("json_table", table_meta, ["not a dict"])

    with pytest.raises(ValueError, match="non-finite float"):
        validate_field_output_value("json_table", table_meta, [{"c": float("nan")}])


def test_06_severity_and_manifest_validators() -> None:
    """Test severity pill bounds and manifest egress allowlist guards."""
    sev_meta = parse_output_format_metadata("severity_pill", {})
    with pytest.raises(TypeError, match="Expected dict for 'severity_pill'"):
        validate_field_output_value("severity_pill", sev_meta, "not a dict")

    with pytest.raises(TypeError, match="Expected numeric score"):
        validate_field_output_value("severity_pill", sev_meta, {"level": "low", "score": "not-num"})

    with pytest.raises(TypeError, match="Expected numeric score"):
        validate_field_output_value("severity_pill", sev_meta, {"level": "low", "score": True})

    with pytest.raises(ValueError, match="Severity score must be finite"):
        validate_field_output_value(
            "severity_pill", sev_meta, {"level": "low", "score": float("nan")}
        )

    with pytest.raises(ValueError, match="Severity score must be finite"):
        validate_field_output_value("severity_pill", sev_meta, {"level": "low", "score": -1.0})

    with pytest.raises(ValueError, match="Severity label must be a string"):
        validate_field_output_value("severity_pill", sev_meta, {"level": "low", "label": 123})

    # Manifest egress allowlist path invalid types and pattern check
    with pytest.raises(TypeError, match="entry must be a string"):
        validate_egress_allowlist(cast("list[str]", [123]))

    with pytest.raises(ValueError, match="does not match required pattern"):
        validate_egress_allowlist(["/api/v1/" + "x" * 255])

    with pytest.raises(ValueError, match="does not match required pattern"):
        validate_egress_allowlist(["/api/v2/issues"])
