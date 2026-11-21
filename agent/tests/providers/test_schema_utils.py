# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Comprehensive unit tests for schema_utils dereferencing, Gemini cleaning, and think stripping."""

from __future__ import annotations

from typing import Literal

import pytest
from pydantic import BaseModel, Field

from agent.providers.schema_utils import (
    clean_gemini_schema,
    dereference_json_schema,
    make_strict_json_schema,
    strip_think_tags,
)


class SubModel(BaseModel):
    """Sub-model to generate $defs reference."""

    identifier: str
    weight: float = Field(default=1.0)


class ComplexModel(BaseModel):
    """Complex model with nested object, array of objects, and literals."""

    decision: Literal["approve", "reject"]
    primary: SubModel
    backups: list[SubModel] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    reason: str = Field(default="Standard verification")


def test_dereference_json_schema() -> None:
    """Verify dereference_json_schema resolves and removes $defs."""
    raw = ComplexModel.model_json_schema()
    assert "$defs" in raw

    derefed = dereference_json_schema(raw)
    assert "$defs" not in derefed
    assert "definitions" not in derefed

    # Verify primary.identifier is inlined
    primary_props = derefed["properties"]["primary"]["properties"]
    assert "identifier" in primary_props
    assert "weight" in primary_props

    # Verify backups.items is inlined
    backup_items_props = derefed["properties"]["backups"]["items"]["properties"]
    assert "identifier" in backup_items_props
    assert "weight" in backup_items_props


def test_clean_gemini_schema() -> None:
    """Verify clean_gemini_schema removes title, default, and $defs."""
    cleaned = clean_gemini_schema(ComplexModel)
    assert "$defs" not in cleaned
    assert "definitions" not in cleaned
    assert "title" not in cleaned

    props = cleaned["properties"]
    assert "decision" in props
    assert "title" not in props["decision"]

    assert "reason" in props
    assert "default" not in props["reason"]

    primary_props = props["primary"]["properties"]
    assert "weight" in primary_props
    assert "default" not in primary_props["weight"]
    assert "title" not in primary_props["weight"]


def test_clean_gemini_schema_invalid_type() -> None:
    """Verify clean_gemini_schema raises TypeError on invalid schema argument."""
    with pytest.raises(TypeError, match="Expected dict or BaseModel class"):
        clean_gemini_schema(12345)  # type: ignore[arg-type]


def test_make_strict_json_schema_with_and_without_dereference() -> None:
    """Verify make_strict_json_schema enforces additionalProperties=False and required."""
    strict_deref = make_strict_json_schema(ComplexModel, dereference=True)
    assert "$defs" not in strict_deref
    assert strict_deref["additionalProperties"] is False
    assert "decision" in strict_deref["required"]
    assert "primary" in strict_deref["required"]
    assert strict_deref["properties"]["primary"]["additionalProperties"] is False

    strict_defs = make_strict_json_schema(ComplexModel, dereference=False)
    assert "$defs" in strict_defs
    assert strict_defs["additionalProperties"] is False
    assert strict_defs["$defs"]["SubModel"]["additionalProperties"] is False


def test_strip_think_tags() -> None:
    """Verify strip_think_tags handles various think block formats and trims whitespace."""
    no_tags = '{"decision": "approve"}'
    assert strip_think_tags(no_tags) == '{"decision": "approve"}'

    with_tags = '<think>\nLet me analyze the logs.\nTests pass.\n</think>\n{"decision": "approve"}'
    assert strip_think_tags(with_tags) == '{"decision": "approve"}'

    multiple_tags = '<think>thought 1</think>\n  {\n<think>thought 2</think>"ok": true}'
    assert strip_think_tags(multiple_tags) == '{\n"ok": true}'

    surrounding_whitespace = "   <think>done</think>  \n  42   "
    assert strip_think_tags(surrounding_whitespace) == "42"


def test_dereference_json_schema_edge_cases() -> None:
    """Verify definitions prefix, missing ref target, and cyclic ref handling."""
    schema_definitions = {
        "definitions": {
            "Item": {"type": "object", "properties": {"code": {"type": "string"}}},
        },
        "properties": {
            "item": {"$ref": "#/definitions/Item"},
            "missing": {"$ref": "#/$defs/NonExistent"},
        },
    }
    resolved = dereference_json_schema(schema_definitions)
    assert "definitions" not in resolved
    assert resolved["properties"]["item"]["properties"]["code"]["type"] == "string"
    assert resolved["properties"]["missing"] == {}

    cyclic_schema = {
        "$defs": {
            "Node": {
                "type": "object",
                "properties": {"next": {"$ref": "#/$defs/Node"}},
            }
        },
        "properties": {"root": {"$ref": "#/$defs/Node"}},
    }
    resolved_cyclic = dereference_json_schema(cyclic_schema)
    assert "$defs" not in resolved_cyclic
    assert resolved_cyclic["properties"]["root"]["type"] == "object"


def test_clean_gemini_schema_from_dict() -> None:
    """Verify clean_gemini_schema directly accepts schema dictionaries."""
    raw_dict = {
        "title": "RawDictModel",
        "type": "object",
        "properties": {
            "field": {"title": "Field", "type": "string", "default": "val"},
        },
    }
    cleaned = clean_gemini_schema(raw_dict)
    assert "title" not in cleaned
    assert "default" not in cleaned["properties"]["field"]
    assert cleaned["properties"]["field"]["type"] == "string"
