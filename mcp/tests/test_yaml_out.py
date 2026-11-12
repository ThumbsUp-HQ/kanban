# Copyright 2026 Kanban Platform Contributors
"""Test InlineSafeDumper YAML serializer, empty stripping, and flow formatting (Test Case 4)."""

from __future__ import annotations

import pytest
import yaml

from mcp.yaml_out import dump_yaml, strip_empty


def test_strip_empty_nested_structures() -> None:
    """Verify nested None, [], {}, and '' are removed at every depth while 0 and False survive."""
    data = {
        "zero": 0,
        "false": False,
        "true": True,
        "empty_str": "",
        "none_val": None,
        "empty_list": [],
        "empty_dict": {},
        "nested": {
            "keep_zero": 0,
            "drop_none": None,
            "drop_empty": "",
            "deeper": {
                "keep_false": False,
                "drop_empty_list": [],
            },
            "all_empty": {
                "drop1": "",
                "drop2": [],
            },
        },
        "list_with_empties": [0, False, "", None, [], {}, {"drop": ""}, {"keep": 42}],
    }

    cleaned = strip_empty(data)
    assert cleaned == {
        "zero": 0,
        "false": False,
        "true": True,
        "nested": {
            "keep_zero": 0,
            "deeper": {
                "keep_false": False,
            },
        },
        "list_with_empties": [0, False, {"keep": 42}],
    }


def test_strip_empty_top_level_empties() -> None:
    """Verify strip_empty returns None for empty top-level values."""
    assert strip_empty(None) is None
    assert strip_empty("") is None
    assert strip_empty([]) is None
    assert strip_empty({}) is None
    assert strip_empty(0) == 0
    false_val = False
    assert strip_empty(false_val) is False


def test_flow_style_for_scalar_lists_and_small_dicts() -> None:
    """Verify lists of scalars and small dicts render in flow style."""
    data = {
        "labels": ["a", "b"],
        "empty_items": [],
        "single_cycle": [{"name": "Cycle 4", "status": "active"}],
        "params": {"identifier": "KAN-142 | uuid", "description_mode": "append | replace"},
    }
    rendered = dump_yaml(data)

    assert "labels: [a, b]" in rendered
    assert "cycles" not in rendered  # Not in data
    assert "params: {identifier: KAN-142 | uuid, description_mode: append | replace}" in rendered
    assert "[{name: Cycle 4, status: active}]" in rendered


def test_multiline_markdown_renders_as_literal_block() -> None:
    """Verify multiline Markdown renders with literal block | and roundtrips byte-identical."""
    multiline_md = (
        "# Heading 1\n\n"
        "Paragraph with **bold** and `code` formatting.\n\n"
        "- Item 1\n"
        "- Item 2\n\n"
        "```python\n"
        "def hello() -> str:\n"
        "    return 'world'\n"
        "```\n"
    )
    payload = {"description_markdown": multiline_md}
    rendered = dump_yaml(payload)

    assert "description_markdown: |" in rendered
    assert "!!python" not in rendered

    loaded = yaml.safe_load(rendered)
    assert loaded["description_markdown"] == multiline_md


def test_dump_set_raises_type_error() -> None:
    """Verify dumping a set or frozenset raises TypeError and never emits Python tags."""
    with pytest.raises(TypeError, match="Cannot dump non-primitive type: set"):
        dump_yaml({"tags": {"security", "auth"}})

    with pytest.raises(TypeError, match="Cannot dump non-primitive type: frozenset"):
        dump_yaml({"tags": frozenset(["security"])})


def test_dump_custom_class_raises_type_error() -> None:
    """Verify dumping arbitrary custom objects raises TypeError."""

    class CustomObject:
        pass

    with pytest.raises(TypeError, match="Cannot dump non-primitive type: CustomObject"):
        dump_yaml({"obj": CustomObject()})


def test_dump_empty_cases() -> None:
    """Verify dump_yaml handles None and empty structures gracefully."""
    assert dump_yaml(None) == ""
    assert dump_yaml("") == ""
    assert dump_yaml({}) == "{}\n"
    assert dump_yaml([]) == "[]\n"
    assert dump_yaml({}, strip_nulls=False) == "{}\n"
    assert dump_yaml([], strip_nulls=False) == "[]\n"
    assert dump_yaml({"a": None}, strip_nulls=False) == "a: null\n"
    assert dump_yaml({"empty_list": []}, strip_nulls=False) == "empty_list: []\n"
