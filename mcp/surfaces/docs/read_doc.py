# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Tool read_doc: Progressive disclosure reading for Docs, Pages, and Stickies (S11.3)."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any, Final

from mcp.context import current_internal_client, current_subject_token
from mcp.errors import KbMcpError, McpErrorCode
from mcp.lod import Lod, parse_lod
from mcp.registry import Surface, ToolSpec

if TYPE_CHECKING:
    from mcp.internal_client import KanbanApiClient

__all__ = [
    "create_read_doc_tool",
    "read_doc_handler",
]

_TOOL_NAME: Final[str] = "read_doc"
_DESCRIPTION: Final[str] = (
    "Read a Doc, Page, or Sticky in canonical Markdown with progressive LOD disclosure."
)

_INPUT_SCHEMA: Final[dict[str, Any]] = {
    "type": "object",
    "properties": {
        "identifier": {
            "type": "string",
            "description": "Page path, doc key, doc/page/sticky UUID, or 'help'",
        },
        "lod": {
            "type": "string",
            "enum": ["summary", "standard", "full"],
            "default": "standard",
            "description": "Level of detail: summary, standard, or full",
        },
    },
    "required": ["identifier"],
    "additionalProperties": False,
}

_UUID_REGEX: Final[re.Pattern[str]] = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


def _extract_headings(markdown_text: str) -> list[dict[str, Any]]:
    """Extract headings tree outline from canonical Markdown body."""
    outline: list[dict[str, Any]] = []
    lines = markdown_text.splitlines()
    in_fence = False

    for line in lines:
        stripped = line.strip()
        if stripped.startswith(("```", "~~~")):
            in_fence = not in_fence
            continue
        if in_fence:
            continue

        match = re.match(r"^(#{1,6})[ \t]+(.*?)(?:[ \t]+#+)?[ \t]*$", line)
        if match:
            level = len(match.group(1))
            text = match.group(2).strip()
            slug = re.sub(r"[^\w\s-]", "", text).strip().lower()
            slug = re.sub(r"[-\s]+", "-", slug)
            outline.append({"level": level, "text": text, "anchor": f"#{slug}" if slug else ""})
    return outline


def _format_access_pill(access_manifest: dict[str, Any] | None) -> str:
    """Format human-readable access pill string."""
    if not isinstance(access_manifest, dict):
        return "project"
    scope = access_manifest.get("inherited_scope") or access_manifest.get("scope", "project")
    return str(scope).lower()


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


async def _try_get_page_or_doc(  # noqa: C901
    client: KanbanApiClient,
    identifier: str,
    subject_token: str | None,
) -> tuple[str, dict[str, Any]] | None:
    """Attempt to fetch page or doc by path or UUID."""
    clean_id = identifier.strip().lstrip("/")

    # If starts with pages/ or contains /pages/
    if clean_id.startswith("pages/"):
        page_path = clean_id.removeprefix("pages/")
        try:
            resp = await client.request(
                "GET", f"/api/v1/pages/{page_path}", subject_token=subject_token
            )
            if isinstance(resp, dict):
                return "page", resp
        except KbMcpError:
            pass

    # Try as page first if it has a slash (hierarchical path like docs/arch/auth-studio)
    if "/" in clean_id:
        try:
            resp = await client.request(
                "GET", f"/api/v1/pages/{clean_id}", subject_token=subject_token
            )
            if isinstance(resp, dict):
                return "page", resp
        except KbMcpError:
            pass

    # Try as doc
    doc_path = clean_id.removeprefix("docs/")
    try:
        resp = await client.request("GET", f"/api/v1/docs/{doc_path}", subject_token=subject_token)
        if isinstance(resp, dict):
            return "doc", resp
    except KbMcpError:
        pass

    # Try as page directly
    try:
        resp = await client.request("GET", f"/api/v1/pages/{clean_id}", subject_token=subject_token)
        if isinstance(resp, dict):
            return "page", resp
    except KbMcpError:
        pass

    return None


async def read_doc_handler(  # noqa: C901, PLR0912, PLR0915
    arguments: dict[str, Any],
    *,
    client: KanbanApiClient | None = None,
    subject_token: str | None = None,
) -> dict[str, Any]:
    """Execute read_doc tool invocation."""
    identifier = arguments.get("identifier")
    if not isinstance(identifier, str) or not identifier.strip():
        msg = "Parameter 'identifier' is required"
        raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

    raw_lod = arguments.get("lod", "standard")
    lod = parse_lod(raw_lod)

    active_client = client or current_internal_client.get()
    active_token = subject_token or current_subject_token.get()

    if active_client is None:
        msg = "Internal API client is unavailable"
        raise KbMcpError(McpErrorCode.UPSTREAM_UNAVAILABLE, msg)

    clean_id = identifier.strip()

    # Check if UUID and try sticky
    if _UUID_REGEX.match(clean_id):
        sticky_data = await _try_get_sticky(active_client, clean_id, active_token)
        if sticky_data is not None:
            # Format sticky response according to LOD
            title = ""
            body = sticky_data.get("body_markdown", "")
            if body:
                first_line = body.strip().splitlines()[0]
                title = first_line.lstrip("#").strip()[:80]
            if not title:
                title = f"Sticky {sticky_data.get('color_token', 'amber')}"

            summary_out: dict[str, Any] = {
                "kind": "sticky",
                "id": str(sticky_data.get("id")),
                "color": sticky_data.get("color_token", "amber"),
                "title": title,
                "promotion_recommended": sticky_data.get("promotion_recommended", False),
            }
            if lod == Lod.SUMMARY:
                return summary_out

            standard_out = dict(summary_out)
            standard_out["body_markdown"] = body
            standard_out["etag"] = sticky_data.get("etag", "")
            standard_out["access"] = _format_access_pill(sticky_data.get("access_manifest"))
            if lod == Lod.STANDARD:
                return standard_out

            full_out = dict(standard_out)
            full_out["access_manifest"] = sticky_data.get("access_manifest", {})
            full_out["capabilities"] = sticky_data.get("capabilities", [])
            full_out["triggers"] = sticky_data.get("triggers", [])
            if sticky_data.get("promoted_to_doc_id"):
                full_out["promoted_to_doc_id"] = str(sticky_data["promoted_to_doc_id"])
            return full_out

    # Try doc or page
    found = await _try_get_page_or_doc(active_client, clean_id, active_token)
    if found is None:
        safe_id = clean_id.replace('"', '\\"')
        msg = f"Document, page, or sticky '{clean_id}' not found"
        raise KbMcpError(
            McpErrorCode.NOT_FOUND,
            msg,
            field="id",
            fix_hint=(
                f"Document, page, or sticky '{clean_id}' was not found "
                "or you do not have access. Search accessible documents first."
            ),
            cli_example=f'kanban-cli-docs search --query="{safe_id}"',
        )

    kind, entity_data = found

    key = str(entity_data.get("canonical_key") or entity_data.get("path") or clean_id)
    title = str(entity_data.get("title", ""))
    version_seq = entity_data.get("version_seq", 1)

    # Compute breadcrumbs
    breadcrumbs: list[str] = []
    if "breadcrumbs" in entity_data and isinstance(entity_data["breadcrumbs"], list):
        breadcrumbs = [
            str(b.get("title") if isinstance(b, dict) else b) for b in entity_data["breadcrumbs"]
        ]
    elif entity_data.get("parent_title"):
        breadcrumbs = [str(entity_data["parent_title"]), title]
    else:
        breadcrumbs = [title]

    summary_doc: dict[str, Any] = {
        "kind": kind,
        "key": key,
        "title": title,
        "breadcrumbs": breadcrumbs,
        "version_seq": version_seq,
    }
    if lod == Lod.SUMMARY:
        return summary_doc

    body_markdown = str(
        entity_data.get("body_markdown") or entity_data.get("content_markdown") or ""
    )
    etag = str(entity_data.get("etag") or entity_data.get("body_sha256") or "")
    access_manifest = entity_data.get("access_manifest")
    access = _format_access_pill(access_manifest if isinstance(access_manifest, dict) else None)

    standard_doc = dict(summary_doc)
    standard_doc["body_markdown"] = body_markdown
    standard_doc["etag"] = etag
    standard_doc["access"] = access

    if lod == Lod.STANDARD:
        return standard_doc

    full_doc = dict(standard_doc)
    full_doc["access_manifest"] = access_manifest or {}
    full_doc["outline"] = _extract_headings(body_markdown)

    # Fetch object links if available
    entity_id = entity_data.get("id")
    if entity_id:
        try:
            links_resp = await active_client.request(
                "GET",
                f"/api/v1/objects/{entity_id}/links",
                subject_token=active_token,
            )
            if isinstance(links_resp, dict):
                full_doc["links"] = links_resp.get("outbound", []) + links_resp.get("inbound", [])
            else:
                full_doc["links"] = []
        except KbMcpError:
            full_doc["links"] = []
    else:
        full_doc["links"] = []

    return full_doc


def create_read_doc_tool(client: KanbanApiClient | None = None) -> ToolSpec:
    """Construct ToolSpec for read_doc."""

    async def _handler(arguments: dict[str, Any], **kwargs: object) -> dict[str, Any]:
        raw_client = kwargs.get("client") or kwargs.get("internal_client")
        active_client = client or (raw_client if hasattr(raw_client, "request") else None)
        raw_token = kwargs.get("subject_token")
        active_token = str(raw_token) if raw_token is not None else None
        return await read_doc_handler(
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
