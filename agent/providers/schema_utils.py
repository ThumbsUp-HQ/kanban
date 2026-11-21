# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""JSON schema utilities for strict structured outputs and provider compatibility."""

from __future__ import annotations

import copy
import re
from typing import Any

from pydantic import BaseModel

__all__ = [
    "clean_gemini_schema",
    "dereference_json_schema",
    "make_strict_json_schema",
    "strip_think_tags",
]

_RE_THINK_TAGS: re.Pattern[str] = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


def strip_think_tags(text: str) -> str:
    """Strip reasoning model <think>...</think> blocks and trim surrounding whitespace."""
    if "<think" not in text.lower():
        return text.strip()
    return _RE_THINK_TAGS.sub("", text).strip()


def dereference_json_schema(schema: dict[str, Any]) -> dict[str, Any]:  # noqa: C901
    """Inline and dereference all $defs and definitions in a JSON schema.

    Produces a flat, self-contained schema with all $ref pointers resolved,
    eliminating top-level $defs and definitions keywords.
    """
    schema_copy = copy.deepcopy(schema)
    defs: dict[str, Any] = {}
    if "$defs" in schema_copy and isinstance(schema_copy["$defs"], dict):
        defs.update(schema_copy["$defs"])
    if "definitions" in schema_copy and isinstance(schema_copy["definitions"], dict):
        defs.update(schema_copy["definitions"])

    def _resolve_ref(ref_str: str) -> dict[str, Any]:
        prefix_defs = "#/$defs/"
        prefix_definitions = "#/definitions/"
        key = None
        if ref_str.startswith(prefix_defs):
            key = ref_str[len(prefix_defs) :]
        elif ref_str.startswith(prefix_definitions):
            key = ref_str[len(prefix_definitions) :]
        if key and key in defs:
            return copy.deepcopy(defs[key])
        return {}

    def _walk(node: Any, seen_refs: set[str] | None = None) -> Any:  # noqa: ANN401
        if seen_refs is None:
            seen_refs = set()
        if isinstance(node, dict):
            if "$ref" in node and isinstance(node["$ref"], str):
                ref = node["$ref"]
                if ref not in seen_refs:
                    target = _resolve_ref(ref)
                    merged = {k: v for k, v in node.items() if k != "$ref"}
                    resolved = _walk(target, seen_refs | {ref})
                    if isinstance(resolved, dict):
                        merged = {**resolved, **merged}
                    return merged
                return {k: v for k, v in node.items() if k != "$ref"}
            result: dict[str, Any] = {}
            for k, v in node.items():
                if k in ("$defs", "definitions"):
                    continue
                result[k] = _walk(v, seen_refs)
            return result
        if isinstance(node, list):
            return [_walk(item, seen_refs) for item in node]
        return node

    dereferenced = _walk(schema_copy)
    if isinstance(dereferenced, dict):
        dereferenced.pop("$defs", None)
        dereferenced.pop("definitions", None)
        return dereferenced
    return schema_copy


def clean_gemini_schema(schema: dict[str, Any] | type[BaseModel]) -> dict[str, Any]:
    """Produce Gemini-compatible OpenAPI subset schema without $defs, $ref, title, or default."""
    raw_schema: dict[str, Any] = schema if isinstance(schema, dict) else schema.model_json_schema()

    derefed = dereference_json_schema(raw_schema)

    def _strip_unsupported(node: Any) -> Any:  # noqa: ANN401
        if isinstance(node, dict):
            cleaned: dict[str, Any] = {}
            for k, v in node.items():
                if k in ("$defs", "definitions", "title", "default"):
                    continue
                cleaned[k] = _strip_unsupported(v)
            return cleaned
        if isinstance(node, list):
            return [_strip_unsupported(item) for item in node]
        return node

    res = _strip_unsupported(derefed)
    return res if isinstance(res, dict) else {}


def _enforce_strict_dict(node: dict[str, Any]) -> None:
    """Enforce strict structured output rules on dictionary schema node."""
    if node.get("type") == "object" or "properties" in node:
        node["additionalProperties"] = False
        props = node.setdefault("properties", {})
        if isinstance(props, dict):
            req_list = node.setdefault("required", [])
            for prop in props:
                if prop not in req_list:
                    req_list.append(prop)
    for v in node.values():
        _enforce_strict(v)


def _enforce_strict(node: object) -> None:
    """Recursively enforce additionalProperties=False and required fields."""
    if isinstance(node, dict):
        _enforce_strict_dict(node)
    elif isinstance(node, list):
        for item in node:
            _enforce_strict(item)


def make_strict_json_schema(model: type[BaseModel], *, dereference: bool = False) -> dict[str, Any]:
    """Generate OpenAI-compliant strict JSON schema with additionalProperties=False.

    If dereference=True, inlines any $defs or $ref references.
    """
    raw_schema = model.model_json_schema()
    if dereference:
        raw_schema = dereference_json_schema(raw_schema)
    _enforce_strict(raw_schema)
    return raw_schema
