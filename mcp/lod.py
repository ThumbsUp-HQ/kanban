# Copyright 2026 Kanban Platform Contributors
"""LOD (Level of Detail) tiers and field projection tables (S11.1)."""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Final

from mcp.errors import KbMcpError, McpErrorCode

__all__ = [
    "Lod",
    "parse_lod",
    "project_doc",
    "project_entity",
    "project_issue",
    "project_project",
    "project_sticky",
]


class Lod(StrEnum):
    """Level of detail for projected MCP entity responses."""

    SUMMARY = "summary"
    STANDARD = "standard"
    FULL = "full"


def parse_lod(value: str | Lod | None) -> Lod:
    """Validate and parse lod parameter, raising VALIDATION_FAILED on invalid value."""
    if value is None:
        return Lod.SUMMARY
    if isinstance(value, Lod):
        return value
    if isinstance(value, str):
        val_lower = value.strip().lower()
        for tier in Lod:
            if tier.value == val_lower:
                return tier
    msg = f"Unknown lod '{value}'. Must be one of: summary, standard, full"
    raise KbMcpError(
        McpErrorCode.VALIDATION_FAILED,
        msg,
        hint="Pass lod='summary', lod='standard', or lod='full'",
    )


_SUMMARY_ISSUE_KEYS: Final[tuple[str, ...]] = (
    "key",
    "summary",
    "state",
    "priority",
    "assignees",
)

_STANDARD_ISSUE_KEYS: Final[tuple[str, ...]] = (
    *_SUMMARY_ISSUE_KEYS,
    "description_markdown",
    "labels",
    "cycle",
    "modules",
    "parent",
    "start_date",
    "due_date",
    "links",
    "etag",
    "access",
)

_FULL_ISSUE_KEYS: Final[tuple[str, ...]] = (
    *_STANDARD_ISSUE_KEYS,
    "access_manifest",
    "custom_fields",
    "comments",
    "activity",
    "gate_verdicts",
    "provenance",
)


def _is_gate_pending(gate: object) -> bool:
    """Check if gate status is pending."""
    if isinstance(gate, str):
        return gate.lower() == "pending"
    if isinstance(gate, dict):
        status = gate.get("status")
        return isinstance(status, str) and status.lower() == "pending"
    return False


def _project_issue_summary(raw: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for k in _SUMMARY_ISSUE_KEYS:
        if k in raw:
            result[k] = raw[k]
    gate = raw.get("gate")
    if _is_gate_pending(gate):
        result["gate"] = gate
    return result


def _project_issue_standard(raw: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for k in _STANDARD_ISSUE_KEYS:
        if k in raw:
            result[k] = raw[k]
    gate = raw.get("gate")
    if _is_gate_pending(gate):
        result["gate"] = gate
    return result


def _extract_provenance(raw: dict[str, Any]) -> dict[str, Any] | None:
    if "provenance" in raw:
        prov_val = raw["provenance"]
        return prov_val if isinstance(prov_val, dict) else {"raw": prov_val}
    prov: dict[str, Any] = {}
    for pkey in ("created_by", "original_created_by", "creator_modified_by"):
        if pkey in raw and raw[pkey] is not None:
            prov[pkey] = raw[pkey]
    return prov or None


def _project_issue_full(raw: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for k in _FULL_ISSUE_KEYS:
        if k in ("comments", "activity"):
            items = raw.get(k)
            if isinstance(items, list):
                result[k] = items[-50:]
            elif k in raw:
                result[k] = raw[k]
        elif k == "provenance":
            prov = _extract_provenance(raw)
            if prov is not None:
                result["provenance"] = prov
        elif k in raw:
            result[k] = raw[k]

    gate = raw.get("gate")
    if gate is not None:
        result["gate"] = gate
    return result


def project_issue(raw: dict[str, Any], lod: Lod | str) -> dict[str, Any]:
    """Project issue dictionary according to specified LOD tier."""
    tier = parse_lod(lod)
    if tier == Lod.SUMMARY:
        return _project_issue_summary(raw)
    if tier == Lod.STANDARD:
        return _project_issue_standard(raw)
    return _project_issue_full(raw)


def project_doc(raw: dict[str, Any], lod: Lod | str) -> dict[str, Any]:
    """Project doc dictionary according to specified LOD tier."""
    tier = parse_lod(lod)
    summary_keys = ("id", "key", "title", "project", "state", "updated_at")
    standard_keys = (*summary_keys, "content_markdown", "parent", "labels", "etag", "access")
    full_keys = (*standard_keys, "access_manifest", "comments", "activity", "provenance")

    active_keys: tuple[str, ...]
    if tier == Lod.SUMMARY:
        active_keys = summary_keys
    elif tier == Lod.STANDARD:
        active_keys = standard_keys
    else:
        active_keys = full_keys

    result: dict[str, Any] = {}
    for k in active_keys:
        if k in ("comments", "activity") and tier == Lod.FULL:
            items = raw.get(k)
            if isinstance(items, list):
                result[k] = items[-50:]
            elif k in raw:
                result[k] = raw[k]
        elif k in raw:
            result[k] = raw[k]
    return result


def project_sticky(raw: dict[str, Any], lod: Lod | str) -> dict[str, Any]:
    """Project sticky dictionary according to specified LOD tier."""
    tier = parse_lod(lod)
    summary_keys = ("id", "project", "color", "content", "position")
    standard_keys = (*summary_keys, "content_markdown", "author", "updated_at", "access")
    full_keys = (*standard_keys, "access_manifest", "promoted_to_doc_id", "provenance")

    active_keys: tuple[str, ...]
    if tier == Lod.SUMMARY:
        active_keys = summary_keys
    elif tier == Lod.STANDARD:
        active_keys = standard_keys
    else:
        active_keys = full_keys

    result: dict[str, Any] = {}
    for k in active_keys:
        if k in raw:
            result[k] = raw[k]
    return result


def project_project(raw: dict[str, Any], lod: Lod | str) -> dict[str, Any]:
    """Project project dictionary according to specified LOD tier."""
    tier = parse_lod(lod)
    summary_keys = ("id", "key", "name", "status")
    standard_keys = (
        *summary_keys,
        "description",
        "modules_enabled",
        "lead",
        "created_at",
        "access",
    )
    full_keys = (*standard_keys, "access_manifest", "members", "cycle_count", "issue_count")

    active_keys: tuple[str, ...]
    if tier == Lod.SUMMARY:
        active_keys = summary_keys
    elif tier == Lod.STANDARD:
        active_keys = standard_keys
    else:
        active_keys = full_keys

    result: dict[str, Any] = {}
    for k in active_keys:
        if k in raw:
            result[k] = raw[k]
    return result


def project_entity(kind: str, raw: dict[str, Any], lod: Lod | str) -> dict[str, Any]:
    """Dispatch projection for any entity kind."""
    normalized_kind = kind.lower().strip()
    if normalized_kind == "issue":
        return project_issue(raw, lod)
    if normalized_kind == "doc":
        return project_doc(raw, lod)
    if normalized_kind == "sticky":
        return project_sticky(raw, lod)
    if normalized_kind == "project":
        return project_project(raw, lod)

    # Fallback generic projection
    tier = parse_lod(lod)
    if tier == Lod.SUMMARY:
        return {k: raw[k] for k in ("id", "key", "title", "name") if k in raw}
    return raw
