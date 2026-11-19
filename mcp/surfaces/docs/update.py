# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Tool update: Unified Doc/Page/Sticky update and auto-promotion (S11.3, KAN-18)."""

from __future__ import annotations

import difflib
import re
from typing import TYPE_CHECKING, Any, Final

from mcp.context import current_internal_client, current_subject_token
from mcp.errors import KbMcpError, McpErrorCode
from mcp.registry import Surface, ToolSpec

if TYPE_CHECKING:
    from mcp.internal_client import KanbanApiClient

__all__ = [
    "create_docs_update_tool",
    "update_handler",
]

_TOOL_NAME: Final[str] = "update"
_DESCRIPTION: Final[str] = (
    "Update Doc, Page, or Sticky with surgical diff-patching, inline links, "
    "or type='DOC' auto-promotion."
)

_MAX_TITLE_LEN: Final[int] = 200
_MAX_BODY_BYTES: Final[int] = 1_048_576  # 1 MiB
_MAX_STICKY_BYTES: Final[int] = 65_536  # 64 KiB

_UUID_REGEX: Final[re.Pattern[str]] = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)

ALLOWED_STICKY_COLORS: Final[frozenset[str]] = frozenset(
    {"amber", "mint", "sky", "lavender", "coral", "slate"}
)

_INPUT_SCHEMA: Final[dict[str, Any]] = {
    "type": "object",
    "properties": {
        "id": {
            "type": "string",
            "description": "Doc key, page path, or doc/page/sticky UUID to update",
        },
        "type": {
            "type": "string",
            "enum": ["DOC", "STICKY", "doc", "sticky"],
            "description": "Target entity type. When STICKY and type is DOC, auto-promotes to Doc.",
        },
        "title": {
            "type": "string",
            "minLength": 1,
            "maxLength": 200,
            "description": "New title for doc, page, or promoted document",
        },
        "content": {
            "type": "string",
            "description": "Replacement markdown content (or structured content for promotion)",
        },
        "parent": {
            "type": "string",
            "description": "Parent doc key or page path when auto-promoting sticky to child page",
        },
        "color": {
            "type": "string",
            "enum": ["amber", "mint", "sky", "lavender", "coral", "slate"],
            "description": "New color token for sticky notes",
        },
        "original_text": {
            "type": "string",
            "description": "Exact text snippet to be replaced in surgical diff-patching",
        },
        "replacement_text": {
            "type": "string",
            "description": "Replacement text snippet for surgical diff-patching",
        },
        "if_match": {
            "type": "string",
            "description": "64-character SHA-256 hex ETag required for concurrency control",
        },
        "links": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Inline links list/delta syntax (e.g. ['KAN-1', '+KAN-2', '-KAN-3'])",
        },
    },
    "required": ["id"],
    "additionalProperties": False,
}


def _parse_link_target(raw: str) -> tuple[str, str]:
    """Parse link target and optional link_type prefix."""
    clean = raw.strip()
    for known_type in ("VERIFIED_BY_DOC", "RELATES_TO", "DERIVED_FROM_STICKY"):
        if clean.startswith(f"{known_type}:"):
            return clean.removeprefix(f"{known_type}:").strip(), known_type
    return clean, "RELATES_TO"


async def _resolve_parent_ids(
    client: KanbanApiClient,
    parent_ref: str,
    subject_token: str | None,
) -> tuple[str | None, str | None]:
    """Resolve parent doc UUID or page UUID from string reference."""
    clean_ref = parent_ref.strip().lstrip("/")
    if _UUID_REGEX.match(clean_ref):
        return clean_ref, None

    # Try as page
    try:
        page_resp = await client.request(
            "GET", f"/api/v1/pages/{clean_ref}", subject_token=subject_token
        )
        if isinstance(page_resp, dict) and "id" in page_resp:
            p_id = str(page_resp["id"])
            doc_id = str(page_resp.get("doc_id", "")) or None
            return doc_id, p_id
    except KbMcpError:
        pass

    # Try as doc
    clean_doc = clean_ref.removeprefix("docs/")
    try:
        doc_resp = await client.request(
            "GET", f"/api/v1/docs/{clean_doc}", subject_token=subject_token
        )
        if isinstance(doc_resp, dict) and "id" in doc_resp:
            return str(doc_resp["id"]), None
    except KbMcpError:
        pass

    return None, None


async def _try_get_sticky(
    client: KanbanApiClient,
    sticky_uuid: str,
    subject_token: str | None,
) -> dict[str, Any] | None:
    """Attempt to fetch sticky note by UUID."""
    try:
        resp = await client.request(
            "GET",
            f"/api/v1/stickies/{sticky_uuid}",
            subject_token=subject_token,
        )
        if isinstance(resp, dict) and "id" in resp:
            return resp
    except KbMcpError:
        pass
    return None


async def _fetch_current_entity(
    client: KanbanApiClient,
    identifier: str,
    subject_token: str | None,
) -> tuple[str, dict[str, Any]]:
    """Fetch current doc or page entity to verify existence, retrieve body and ETag."""
    clean_id = identifier.strip().lstrip("/")

    # Try as page
    clean_page = clean_id.removeprefix("pages/")
    try:
        page_resp = await client.request(
            "GET", f"/api/v1/pages/{clean_page}", subject_token=subject_token
        )
        if isinstance(page_resp, dict) and ("canonical_key" in page_resp or "id" in page_resp):
            return "page", page_resp
    except KbMcpError:
        pass

    # Try as doc
    clean_doc = clean_id.removeprefix("docs/")
    try:
        doc_resp = await client.request(
            "GET", f"/api/v1/docs/{clean_doc}", subject_token=subject_token
        )
        if isinstance(doc_resp, dict) and ("canonical_key" in doc_resp or "id" in doc_resp):
            return "doc", doc_resp
    except KbMcpError:
        pass

    msg = f"Document or page '{clean_id}' not found"
    raise KbMcpError(McpErrorCode.NOT_FOUND, msg)


def _find_closest_matches(
    body: str,
    target: str,
    top_n: int = 2,
) -> list[dict[str, Any]]:
    """Locate top-N closest matching line windows using SequenceMatcher."""
    lines = body.splitlines()
    if not lines:
        return []

    target_lines = target.splitlines()
    k = max(1, len(target_lines))

    candidates: list[tuple[float, int, int, str]] = []
    window_sizes = {k, max(1, k - 1), k + 1}
    for w in window_sizes:
        for start_idx in range(len(lines)):
            end_idx = min(len(lines), start_idx + w)
            candidate_snippet = "\n".join(lines[start_idx:end_idx])
            sim = difflib.SequenceMatcher(None, target, candidate_snippet).ratio()
            candidates.append((sim, start_idx + 1, end_idx, candidate_snippet))

    candidates.sort(key=lambda c: c[0], reverse=True)

    results: list[dict[str, Any]] = []
    seen_starts: set[int] = set()
    for sim, start_l, end_l, snippet in candidates:
        if start_l in seen_starts:
            continue
        seen_starts.add(start_l)
        results.append(
            {
                "line_start": start_l,
                "line_end": end_l,
                "similarity": round(sim, 3),
                "snippet": snippet,
            }
        )
        if len(results) >= top_n:
            break

    return results


def _find_line_hints(body: str, target: str) -> list[int]:
    """Return 1-based line numbers where target text starts in body."""
    line_numbers: list[int] = []
    start = 0
    while True:
        idx = body.find(target, start)
        if idx == -1:
            break
        line_num = body[:idx].count("\n") + 1
        line_numbers.append(line_num)
        start = idx + len(target)
    return line_numbers


def _diff_patch_content(
    current_body: str,
    original_text: str,
    replacement_text: str,
    current_sha: str,
    if_match: str | None,
) -> str:
    """Perform surgical diff-patching on text content."""
    if if_match is not None and if_match.strip() != current_sha:
        msg = f"ETag mismatch: client provided '{if_match}', current is '{current_sha}'"
        raise KbMcpError(
            McpErrorCode.CONFLICT_ETAG, msg, hint=f"Current fresh ETag is {current_sha}"
        )

    count = current_body.count(original_text)
    if count == 0:
        closest = _find_closest_matches(current_body, original_text, top_n=2)
        msg = "Target text not found in document"
        raise KbMcpError(
            McpErrorCode.PATCH_TARGET_NOT_FOUND,
            msg,
            extra={"closest_match": closest},
            hint="Verify exact whitespace and indentation, or inspect closest_match suggestions.",
        )

    if count > 1:
        line_hints = _find_line_hints(current_body, original_text)
        msg = f"Target text appears {count} times in document; provide more surrounding context"
        raise KbMcpError(
            McpErrorCode.PATCH_TARGET_AMBIGUOUS,
            msg,
            extra={"line_hints": line_hints, "count": count},
            hint="Include unique surrounding lines to disambiguate the target region.",
        )

    return current_body.replace(original_text, replacement_text, 1)


async def _sync_inline_links(  # noqa: C901, PLR0912, PLR0915
    client: KanbanApiClient,
    source_id: str,
    links: list[Any] | dict[str, Any],
    subject_token: str | None,
) -> list[dict[str, Any]]:
    """Synchronize inline links with delta syntax (+target, -target, or {add, remove})."""
    operations: list[tuple[str, str, str]] = []

    if isinstance(links, dict):
        for t in links.get("add", []):
            target_str, link_type = _parse_link_target(str(t))
            operations.append(("add", target_str, link_type))
        for t in links.get("remove", []):
            target_str, link_type = _parse_link_target(str(t))
            operations.append(("remove", target_str, link_type))
    elif isinstance(links, list):
        for item in links:
            if isinstance(item, dict):
                action = item.get("action", "add").lower()
                target_str, link_type = _parse_link_target(str(item.get("target", "")))
                if "link_type" in item:
                    link_type = str(item["link_type"])
                operations.append((action, target_str, link_type))
            elif isinstance(item, str):
                s = item.strip()
                if s.startswith("-"):
                    target_str, link_type = _parse_link_target(s[1:].strip())
                    operations.append(("remove", target_str, link_type))
                elif s.startswith("+"):
                    target_str, link_type = _parse_link_target(s[1:].strip())
                    operations.append(("add", target_str, link_type))
                else:
                    target_str, link_type = _parse_link_target(s)
                    operations.append(("add", target_str, link_type))

    has_remove = any(op[0] == "remove" for op in operations)
    existing_outbound: list[dict[str, Any]] = []
    if has_remove:
        try:
            links_resp = await client.request(
                "GET",
                f"/api/v1/objects/{source_id}/links",
                subject_token=subject_token,
            )
            if isinstance(links_resp, dict):
                existing_outbound = links_resp.get("outbound", [])
        except KbMcpError:
            existing_outbound = []

    results: list[dict[str, Any]] = []
    for action, target, link_type in operations:
        if not target:
            continue
        if action == "add":
            try:
                await client.request(
                    "POST",
                    f"/api/v1/objects/{source_id}/links",
                    json_data={"target": target, "link_type": link_type},
                    subject_token=subject_token,
                )
                results.append({"action": "added", "target": target, "link_type": link_type})
            except KbMcpError as err:
                results.append({"action": "failed", "target": target, "error": err.message})
        elif action == "remove":
            link_id_to_delete = None
            for edge in existing_outbound:
                e_type = edge.get("type") or edge.get("link_type")
                target_obj = edge.get("target", {})
                t_key = target_obj.get("key") if isinstance(target_obj, dict) else str(target_obj)
                t_id = target_obj.get("id") if isinstance(target_obj, dict) else ""
                if e_type == link_type and target in (t_key, t_id):
                    link_id_to_delete = str(edge.get("id", ""))
                    break
            if link_id_to_delete:
                try:
                    await client.request(
                        "DELETE",
                        f"/api/v1/links/{link_id_to_delete}",
                        subject_token=subject_token,
                    )
                    results.append({"action": "removed", "target": target, "link_type": link_type})
                except KbMcpError:
                    pass

    return results


async def update_handler(  # noqa: C901, PLR0912, PLR0915
    arguments: dict[str, Any],
    *,
    client: KanbanApiClient | None = None,
    subject_token: str | None = None,
) -> dict[str, Any]:
    """Execute update tool invocation."""
    raw_id = arguments.get("id")
    if not raw_id or not isinstance(raw_id, str) or not raw_id.strip():
        msg = "Parameter 'id' is required"
        raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)
    clean_id = raw_id.strip()

    raw_type = arguments.get("type")
    target_type = str(raw_type).strip().upper() if raw_type else None

    title_arg = arguments.get("title")
    title = str(title_arg).strip() if title_arg is not None else None
    if title is not None and not (1 <= len(title) <= _MAX_TITLE_LEN):
        msg = f"Parameter 'title' must be 1..{_MAX_TITLE_LEN} characters"
        raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

    content_arg = arguments.get("content")
    content = str(content_arg) if content_arg is not None else None
    parent_arg = arguments.get("parent")
    color_arg = arguments.get("color")
    color = str(color_arg).strip().lower() if color_arg else None
    if color is not None and color not in ALLOWED_STICKY_COLORS:
        msg = f"Invalid color '{color_arg}'. Must be one of: {sorted(ALLOWED_STICKY_COLORS)}"
        raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

    original_text = arguments.get("original_text")
    replacement_text = arguments.get("replacement_text")
    if_match = arguments.get("if_match")
    if if_match is not None:
        if_match = str(if_match).strip()

    links_arg = arguments.get("links")

    active_client = client or current_internal_client.get()
    active_token = subject_token or current_subject_token.get()

    if active_client is None:
        msg = "Internal API client is unavailable"
        raise KbMcpError(McpErrorCode.UPSTREAM_UNAVAILABLE, msg)

    # Check if id resolves to an existing sticky
    sticky_info: dict[str, Any] | None = None
    if _UUID_REGEX.match(clean_id):
        sticky_info = await _try_get_sticky(active_client, clean_id, active_token)

    # =========================================================================
    # CASE 1: Sticky Auto-Promotion (target_type == "DOC")
    # =========================================================================
    if sticky_info is not None and target_type == "DOC":
        if sticky_info.get("is_promoted_stub") or sticky_info.get("promoted_to_doc_id"):
            msg = f"Sticky '{clean_id}' has already been promoted to a document"
            raise KbMcpError(McpErrorCode.ALREADY_PROMOTED, msg)

        current_sha = str(sticky_info.get("body_sha256") or sticky_info.get("etag", ""))
        if if_match and if_match != current_sha:
            msg = f"ETag mismatch: client provided '{if_match}', current is '{current_sha}'"
            raise KbMcpError(
                McpErrorCode.CONFLICT_ETAG, msg, hint=f"Current fresh ETag is {current_sha}"
            )

        parent_doc_id: str | None = None
        parent_page_id: str | None = None
        if parent_arg:
            parent_doc_id, parent_page_id = await _resolve_parent_ids(
                active_client, str(parent_arg), active_token
            )

        promote_payload: dict[str, Any] = {}
        if title:
            promote_payload["title"] = title
        if parent_doc_id:
            promote_payload["parent_doc_id"] = parent_doc_id
        if parent_page_id:
            promote_payload["parent_page_id"] = parent_page_id
        if content is not None:
            promote_payload["structured_body_markdown"] = content
        if current_sha:
            promote_payload["expected_sticky_sha256"] = current_sha

        resp = await active_client.request(
            "POST",
            f"/api/v1/stickies/{clean_id}/promote-to-doc",
            json_data=promote_payload,
            subject_token=active_token,
        )
        if not isinstance(resp, dict):
            msg = "Failed to promote sticky upstream"
            raise KbMcpError(McpErrorCode.UPSTREAM_ERROR, msg)

        promoted_meta = resp.get("promoted_to_doc") or {}
        doc_key = str(
            promoted_meta.get("canonical_key")
            or promoted_meta.get("id")
            or resp.get("promoted_to_doc_id", "")
        )
        target_obj_id = str(promoted_meta.get("id") or resp.get("promoted_to_doc_id") or clean_id)

        synced_links: list[dict[str, Any]] = []
        if links_arg:
            synced_links = await _sync_inline_links(
                active_client,
                target_obj_id,
                links_arg,
                active_token,
            )

        out_promoted: dict[str, Any] = {
            "status": "promoted",
            "id": clean_id,
            "doc": doc_key,
            "link": "PROMOTED_TO_DOC",
            "title": promoted_meta.get("title") or title or "",
        }
        if synced_links:
            out_promoted["links"] = synced_links
        return out_promoted

    # =========================================================================
    # CASE 2: Sticky Update (not promoted to doc)
    # =========================================================================
    if sticky_info is not None:
        current_sha = str(sticky_info.get("body_sha256") or sticky_info.get("etag", ""))
        current_body = str(sticky_info.get("body_markdown", ""))

        patch_payload: dict[str, Any] = {}
        if original_text is not None and replacement_text is not None:
            new_body = _diff_patch_content(
                current_body,
                str(original_text),
                str(replacement_text),
                current_sha,
                if_match,
            )
            patch_payload["body_markdown"] = new_body
        elif content is not None:
            if if_match and if_match != current_sha:
                msg = f"ETag mismatch: client provided '{if_match}', current is '{current_sha}'"
                raise KbMcpError(
                    McpErrorCode.CONFLICT_ETAG, msg, hint=f"Current fresh ETag is {current_sha}"
                )
            patch_payload["body_markdown"] = content

        if color:
            patch_payload["color_token"] = color

        headers = {"If-Match": "*"}
        if patch_payload:
            resp = await active_client.request(
                "PATCH",
                f"/api/v1/stickies/{clean_id}",
                json_data=patch_payload,
                headers=headers,
                subject_token=active_token,
            )
            if not isinstance(resp, dict):
                msg = "Failed to update sticky upstream"
                raise KbMcpError(McpErrorCode.UPSTREAM_ERROR, msg)
            sticky_info = resp

        synced_links = []
        if links_arg:
            synced_links = await _sync_inline_links(
                active_client,
                clean_id,
                links_arg,
                active_token,
            )

        s_color = str(sticky_info.get("color_token", color or "amber"))
        s_body = str(sticky_info.get("body_markdown", ""))
        first_line = s_body.strip().splitlines()[0] if s_body.strip() else ""
        s_title = first_line.lstrip("#").strip()[:80] if first_line else f"Sticky {s_color}"

        out_sticky: dict[str, Any] = {
            "status": "updated",
            "kind": "sticky",
            "id": clean_id,
            "color": s_color,
            "title": s_title,
            "etag": str(sticky_info.get("etag", "")),
        }
        if synced_links:
            out_sticky["links"] = synced_links
        return out_sticky

    # =========================================================================
    # CASE 3: Doc / Page Update
    # =========================================================================
    kind, entity_data = await _fetch_current_entity(active_client, clean_id, active_token)
    entity_id = str(entity_data.get("id", clean_id))
    current_sha = str(entity_data.get("body_sha256") or entity_data.get("etag", ""))
    current_body = str(
        entity_data.get("body_markdown") or entity_data.get("content_markdown") or ""
    )

    doc_patch_payload: dict[str, Any] = {}
    if original_text is not None and replacement_text is not None:
        new_body = _diff_patch_content(
            current_body,
            str(original_text),
            str(replacement_text),
            current_sha,
            if_match,
        )
        doc_patch_payload["body_markdown"] = new_body
    elif content is not None:
        if if_match and if_match != current_sha:
            msg = f"ETag mismatch: client provided '{if_match}', current is '{current_sha}'"
            raise KbMcpError(
                McpErrorCode.CONFLICT_ETAG, msg, hint=f"Current fresh ETag is {current_sha}"
            )
        doc_patch_payload["body_markdown"] = content

    if title:
        doc_patch_payload["title"] = title

    headers = {}
    if if_match:
        headers["If-Match"] = if_match
    elif current_sha:
        headers["If-Match"] = current_sha

    if doc_patch_payload:
        if kind == "page":
            clean_page_ref = clean_id.removeprefix("pages/")
            resp = await active_client.request(
                "PATCH",
                f"/api/v1/pages/{clean_page_ref}",
                json_data=doc_patch_payload,
                headers=headers,
                subject_token=active_token,
            )
        else:
            clean_doc_ref = clean_id.removeprefix("docs/")
            resp = await active_client.request(
                "PATCH",
                f"/api/v1/docs/{clean_doc_ref}",
                json_data=doc_patch_payload,
                headers=headers,
                subject_token=active_token,
            )
        if isinstance(resp, dict):
            entity_data = resp

    synced_links = []
    if links_arg:
        synced_links = await _sync_inline_links(
            active_client,
            entity_id,
            links_arg,
            active_token,
        )

    out_doc: dict[str, Any] = {
        "status": "updated",
        "kind": kind,
        "id": entity_id,
        "key": str(entity_data.get("canonical_key", clean_id)),
        "title": str(entity_data.get("title", title or "")),
        "version_seq": entity_data.get("version_seq", 1),
        "etag": str(entity_data.get("etag") or entity_data.get("body_sha256") or ""),
    }
    if synced_links:
        out_doc["links"] = synced_links
    return out_doc


def create_docs_update_tool(client: KanbanApiClient | None = None) -> ToolSpec:
    """Construct ToolSpec for unified docs update tool."""

    async def _handler(arguments: dict[str, Any], **kwargs: object) -> dict[str, Any]:
        raw_client = kwargs.get("client") or kwargs.get("internal_client")
        active_client = client or (raw_client if hasattr(raw_client, "request") else None)
        raw_token = kwargs.get("subject_token")
        active_token = str(raw_token) if raw_token is not None else None
        return await update_handler(
            arguments,
            client=active_client,  # type: ignore[arg-type]
            subject_token=active_token,
        )

    return ToolSpec(
        name=_TOOL_NAME,
        description=_DESCRIPTION,
        input_schema=_INPUT_SCHEMA,
        surface=Surface.DOCS,
        handler=_handler,
    )
