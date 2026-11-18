# Copyright 2026 Kanban Platform Contributors
"""LOD (Level of Detail) tiers and field projection tables (S11.1)."""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Final

from mcp.errors import KbMcpError, McpErrorCode

__all__ = [
    "Lod",
    "_compact_access_manifest",
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
    if raw.get("workspace"):
        result["workspace"] = raw["workspace"]
    gate = raw.get("gate")
    if _is_gate_pending(gate):
        result["gate"] = gate
    return result


def _project_issue_standard(raw: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for k in _STANDARD_ISSUE_KEYS:
        if k in raw:
            result[k] = raw[k]
    if raw.get("workspace"):
        result["workspace"] = raw["workspace"]
    gate = raw.get("gate")
    if _is_gate_pending(gate):
        result["gate"] = gate
    return result


def _compact_manifest_principals(manifest: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Extract and compact users, groups, agents, and principals lists."""
    groups_out: dict[str, list[dict[str, Any]]] = {}
    for p_group in ("users", "groups", "agents", "principals"):
        items = manifest.get(p_group)
        if not isinstance(items, list):
            continue
        compact_list: list[dict[str, Any]] = []
        for p in items:
            if not isinstance(p, dict):
                continue
            entry: dict[str, Any] = {}
            handle = p.get("handle") or p.get("slug") or p.get("name")
            if handle:
                s_handle = str(handle).strip()
                entry["handle"] = s_handle if s_handle.startswith("@") else f"@{s_handle}"
            if p.get("grant_source"):
                entry["grant_source"] = p["grant_source"]
            if p.get("capabilities"):
                entry["capabilities"] = p["capabilities"]
            if entry:
                compact_list.append(entry)
        if compact_list:
            groups_out[p_group] = compact_list
    return groups_out


def _compact_inherited_scope(inh: object) -> object:
    """Compact inherited scope object, retaining only kind, scope_label, project_key."""
    if not isinstance(inh, dict):
        return inh
    compact_inh: dict[str, Any] = {}
    for k in ("kind", "scope_label", "project_key"):
        if inh.get(k) is not None:
            compact_inh[k] = inh[k]
    return compact_inh or None


def _compact_access_manifest(manifest: object) -> object:
    """Compact access_manifest by stripping internal UUIDs, zero counts, and redundant keys."""
    if not isinstance(manifest, dict):
        return manifest

    compact: dict[str, Any] = {}
    if manifest.get("pill_label"):
        compact["pill_label"] = manifest["pill_label"]

    eg_count = manifest.get("explicit_grant_count")
    if isinstance(eg_count, int) and eg_count > 0:
        compact["explicit_grant_count"] = eg_count

    red_count = manifest.get("redacted_count")
    if isinstance(red_count, int) and red_count > 0:
        compact["redacted_count"] = red_count

    if "inherited_scope" in manifest:
        compact_inh = _compact_inherited_scope(manifest["inherited_scope"])
        if compact_inh is not None:
            compact["inherited_scope"] = compact_inh

    compact.update(_compact_manifest_principals(manifest))

    if manifest.get("caller_capabilities"):
        compact["caller_capabilities"] = manifest["caller_capabilities"]
    if manifest.get("scope"):
        compact["scope"] = manifest["scope"]

    return compact or manifest


def _format_provenance_handle(val: object) -> str | None:
    """Format provenance creator as clean @handle string."""
    if isinstance(val, dict):
        h = val.get("handle") or val.get("name") or val.get("id")
        if h is not None:
            s = str(h).strip()
            return s if s.startswith("@") else f"@{s}"
        return None
    if isinstance(val, str) and val.strip():
        s = val.strip()
        return s if s.startswith("@") else f"@{s}"
    return None


def _get_raw_provenance_dict(raw: dict[str, Any]) -> dict[str, Any] | None:
    """Extract dictionary representation of provenance from issue data."""
    if "provenance" in raw:
        prov_val = raw["provenance"]
        if isinstance(prov_val, dict):
            return prov_val
        return None
    prov_dict: dict[str, Any] = {}
    for pkey in ("created_by", "original_created_by", "creator_modified_by", "overridden"):
        if pkey in raw and raw[pkey] is not None:
            prov_dict[pkey] = raw[pkey]
    return prov_dict or None


def _extract_provenance(raw: dict[str, Any]) -> dict[str, Any] | None:
    if "provenance" in raw and not isinstance(raw["provenance"], dict) and raw["provenance"]:
        return {"raw": raw["provenance"]}

    prov_dict = _get_raw_provenance_dict(raw)
    if not prov_dict:
        return None

    result: dict[str, Any] = {}
    created_by = _format_provenance_handle(prov_dict.get("created_by"))
    if created_by:
        result["created_by"] = created_by

    is_overridden_false = prov_dict.get("overridden") is False
    if not is_overridden_false:
        orig = _format_provenance_handle(prov_dict.get("original_created_by"))
        if orig:
            result["original_created_by"] = orig
        if prov_dict.get("overridden") is True:
            result["overridden"] = True

    if prov_dict.get("creator_modified_by") is not None:
        mod = _format_provenance_handle(prov_dict["creator_modified_by"])
        if mod:
            result["creator_modified_by"] = mod

    if prov_dict.get("source"):
        result["source"] = prov_dict["source"]

    return result or None


def _project_issue_full_field(k: str, raw: dict[str, Any], result: dict[str, Any]) -> None:
    """Project a single field for full LOD issue."""
    if k in ("comments", "activity"):
        items = raw.get(k)
        if isinstance(items, list):
            result[k] = items[-50:]
        elif k in raw:
            result[k] = raw[k]
    elif k == "access_manifest":
        manifest = raw.get("access_manifest")
        if manifest is not None:
            compact_m = _compact_access_manifest(manifest)
            if compact_m is not None:
                result["access_manifest"] = compact_m
    elif k == "provenance":
        prov = _extract_provenance(raw)
        if prov is not None:
            result["provenance"] = prov
    elif k in raw:
        result[k] = raw[k]


def _project_issue_full(raw: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for k in _FULL_ISSUE_KEYS:
        _project_issue_full_field(k, raw, result)

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
