# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Tool search: CLI-modeled discovery, reading, listing, and hybrid search (S11.3, KAN-18)."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any, Final

from mcp.context import current_internal_client, current_subject_token, get_current_mcp_context
from mcp.errors import KbMcpError, McpErrorCode
from mcp.lod import Lod, parse_lod
from mcp.registry import Surface, ToolSpec

if TYPE_CHECKING:
    from mcp.internal_client import KanbanApiClient

__all__ = [
    "create_docs_search_tool",
    "search_handler",
]

_TOOL_NAME: Final[str] = "search"
_DESCRIPTION: Final[str] = (
    "Read by id (or id='help'), list project docs/stickies, or run hybrid knowledge search."
)

_MAX_QUERY_LEN: Final[int] = 500
_MAX_SNIPPET_LEN: Final[int] = 300
_SNIPPET_TRUNCATE_LEN: Final[int] = 297

_UUID_REGEX: Final[re.Pattern[str]] = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)

_INPUT_SCHEMA: Final[dict[str, Any]] = {
    "type": "object",
    "properties": {
        "id": {
            "type": "string",
            "description": "Page path, doc key, doc/page/sticky UUID, or 'help' to read",
        },
        "query": {
            "type": "string",
            "minLength": 1,
            "maxLength": 500,
            "description": "Lexical or semantic search query (1..500 chars)",
        },
        "type": {
            "type": "string",
            "enum": ["ALL", "DOC", "STICKY", "all", "doc", "sticky"],
            "default": "ALL",
            "description": "Filter entity type: ALL, DOC, or STICKY",
        },
        "project": {
            "type": "string",
            "description": "Project key or UUID scope filter",
        },
        "lod": {
            "type": "string",
            "enum": ["summary", "standard", "full"],
            "default": "standard",
            "description": "Level of detail: summary, standard, or full",
        },
        "include_tree": {
            "type": "boolean",
            "default": False,
            "description": "Whether to include hierarchical page tree or document outline",
        },
        "limit": {
            "type": "integer",
            "minimum": 1,
            "maximum": 50,
            "default": 20,
            "description": "Max search hits or list items to return (1..50, default 20)",
        },
        "cursor": {
            "type": "string",
            "description": "Opaque pagination cursor from previous search",
        },
    },
    "additionalProperties": False,
}


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


def _extract_sticky_title(body: str | None, default_color: str) -> str:
    """Derive display title from first line of Markdown or default color."""
    if not body:
        return f"Sticky {default_color}"
    first_line = body.strip().splitlines()[0] if body.strip() else ""
    clean = first_line.lstrip("#").strip()
    return clean[:80] if clean else f"Sticky {default_color}"


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

    if "/" in clean_id:
        try:
            resp = await client.request(
                "GET", f"/api/v1/pages/{clean_id}", subject_token=subject_token
            )
            if isinstance(resp, dict):
                return "page", resp
        except KbMcpError:
            pass

    doc_path = clean_id.removeprefix("docs/")
    try:
        resp = await client.request("GET", f"/api/v1/docs/{doc_path}", subject_token=subject_token)
        if isinstance(resp, dict):
            return "doc", resp
    except KbMcpError:
        pass

    try:
        resp = await client.request("GET", f"/api/v1/pages/{clean_id}", subject_token=subject_token)
        if isinstance(resp, dict):
            return "page", resp
    except KbMcpError:
        pass

    return None


async def _read_sticky(
    sticky_data: dict[str, Any],
    lod: Lod,
    active_client: KanbanApiClient,
    active_token: str | None,
) -> dict[str, Any]:
    """Format sticky data according to requested LOD."""
    s_color = sticky_data.get("color_token", "amber")
    s_body = sticky_data.get("body_markdown", "")
    title = _extract_sticky_title(s_body, s_color)

    summary_out: dict[str, Any] = {
        "kind": "sticky",
        "id": str(sticky_data.get("id")),
        "color": s_color,
        "title": title,
        "promotion_recommended": bool(sticky_data.get("promotion_recommended", False)),
    }
    if lod == Lod.SUMMARY:
        return summary_out

    standard_out = dict(summary_out)
    standard_out["body_markdown"] = s_body
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

    # Fetch object links if available
    sticky_id = sticky_data.get("id")
    if sticky_id:
        try:
            links_resp = await active_client.request(
                "GET",
                f"/api/v1/objects/{sticky_id}/links",
                subject_token=active_token,
            )
            if isinstance(links_resp, dict):
                full_out["links"] = links_resp.get("outbound", []) + links_resp.get("inbound", [])
            else:
                full_out["links"] = []
        except KbMcpError:
            full_out["links"] = []
    else:
        full_out["links"] = []

    return full_out


async def _read_doc_or_page(  # noqa: C901, PLR0912, PLR0913, PLR0915, PLR0917
    kind: str,
    entity_data: dict[str, Any],
    clean_id: str,
    lod: Lod,
    include_tree: bool,  # noqa: FBT001
    active_client: KanbanApiClient,
    active_token: str | None,
) -> dict[str, Any]:
    """Format doc or page data according to requested LOD and tree options."""
    key = str(entity_data.get("canonical_key") or entity_data.get("path") or clean_id)
    title = str(entity_data.get("title", ""))
    version_seq = entity_data.get("version_seq", 1)

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
    if lod == Lod.SUMMARY and not include_tree:
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

    outline = _extract_headings(body_markdown)

    if include_tree or lod == Lod.FULL:
        # Attempt to retrieve hierarchical page tree if it's a doc
        doc_id = entity_data.get("id") or key
        tree_data: list[Any] | None = None
        if kind == "doc":
            clean_doc_ref = str(doc_id).removeprefix("docs/")
            try:
                tree_resp = await active_client.request(
                    "GET",
                    f"/api/v1/docs/{clean_doc_ref}/tree",
                    subject_token=active_token,
                )
                if isinstance(tree_resp, list):
                    tree_data = tree_resp
            except KbMcpError:
                tree_data = None
        if tree_data is not None:
            standard_doc["tree"] = tree_data
        elif outline:
            standard_doc["outline"] = outline

    if lod == Lod.STANDARD:
        return standard_doc

    full_doc = dict(standard_doc)
    full_doc["access_manifest"] = access_manifest or {}
    full_doc["outline"] = outline

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


async def search_handler(  # noqa: C901, PLR0911, PLR0912, PLR0915
    arguments: dict[str, Any],
    *,
    client: KanbanApiClient | None = None,
    subject_token: str | None = None,
) -> dict[str, Any]:
    """Execute unified search tool invocation."""
    identifier = arguments.get("id")
    query = arguments.get("query")
    raw_type = arguments.get("type", "ALL")
    target_type = str(raw_type).strip().upper() if raw_type else "ALL"
    if target_type not in ("ALL", "DOC", "STICKY"):
        msg = f"Invalid type '{raw_type}'. Must be one of: ALL, DOC, STICKY"
        raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

    if query is not None and (
        not isinstance(query, str) or not (1 <= len(query.strip()) <= _MAX_QUERY_LEN)
    ):
        msg = f"Query parameter must be between 1 and {_MAX_QUERY_LEN} characters"
        raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

    raw_lod = arguments.get("lod", "standard")
    lod = parse_lod(raw_lod)
    include_tree = bool(arguments.get("include_tree", False))
    limit = int(arguments.get("limit", 20))
    cursor = arguments.get("cursor")

    active_client = client or current_internal_client.get()
    active_token = subject_token or current_subject_token.get()

    if active_client is None:
        msg = "Internal API client is unavailable"
        raise KbMcpError(McpErrorCode.UPSTREAM_UNAVAILABLE, msg)

    # -------------------------------------------------------------------------
    # MODE 1: JIT Help
    # -------------------------------------------------------------------------
    if identifier == "help":
        return {
            "tool": _TOOL_NAME,
            "modes": ["read_by_id", "hybrid_search", "list_project_knowledge"],
            "parameters": {
                "id": "Entity key, path, UUID, or 'help' to read",
                "query": "Search query for lexical/semantic hybrid search",
                "type": "ALL, DOC, or STICKY",
                "project": "Project key or UUID scope filter",
                "lod": "Level of detail: summary, standard, full",
                "include_tree": "Whether to include page hierarchy or heading outline",
                "limit": "Max items to return (1..50)",
                "cursor": "Opaque pagination cursor",
            },
        }

    # -------------------------------------------------------------------------
    # MODE 2: Read by ID
    # -------------------------------------------------------------------------
    if identifier and isinstance(identifier, str) and identifier.strip():
        clean_id = identifier.strip()

        # If type is STICKY or ALL, check sticky if UUID
        if target_type in ("STICKY", "ALL") and _UUID_REGEX.match(clean_id):
            sticky_data = await _try_get_sticky(active_client, clean_id, active_token)
            if sticky_data is not None:
                return await _read_sticky(sticky_data, lod, active_client, active_token)
            if target_type == "STICKY":
                msg = f"Sticky note '{clean_id}' not found"
                raise KbMcpError(McpErrorCode.NOT_FOUND, msg)

        if target_type in ("DOC", "ALL"):
            found = await _try_get_page_or_doc(active_client, clean_id, active_token)
            if found is not None:
                kind, entity_data = found
                return await _read_doc_or_page(
                    kind,
                    entity_data,
                    clean_id,
                    lod,
                    include_tree,
                    active_client,
                    active_token,
                )

        msg = f"Document, page, or sticky '{clean_id}' not found"
        raise KbMcpError(McpErrorCode.NOT_FOUND, msg)

    # -------------------------------------------------------------------------
    # MODE 3: Hybrid Search
    # -------------------------------------------------------------------------
    if query is not None:
        clean_query = query.strip()
        if target_type == "DOC":
            kinds = ["doc", "page"]
        elif target_type == "STICKY":
            kinds = ["sticky"]
        else:
            kinds = ["doc", "page", "sticky"]

        search_payload: dict[str, Any] = {
            "query": clean_query,
            "kinds": kinds,
            "limit": limit,
        }
        project_arg = arguments.get("project")
        if project_arg:
            search_payload["project"] = str(project_arg)
        if cursor:
            search_payload["cursor"] = str(cursor)

        resp = await active_client.request(
            "POST",
            "/api/v1/search/knowledge",
            json_data=search_payload,
            subject_token=active_token,
        )

        if not isinstance(resp, dict):
            return {"total": 0, "items": []}

        items_raw = resp.get("items", [])
        formatted_items: list[dict[str, Any]] = []
        for it in items_raw:
            if not isinstance(it, dict):
                continue
            hit_kind = it.get("kind", "doc")
            hit_key = it.get("key") or str(it.get("id", ""))
            hit_title = it.get("title", "")
            anchor = it.get("anchor")
            if anchor and not str(anchor).startswith("#"):
                anchor = f"#{anchor}"

            snippet = it.get("snippet", "")
            if len(snippet) > _MAX_SNIPPET_LEN:
                snippet = snippet[:_SNIPPET_TRUNCATE_LEN] + "..."

            hit: dict[str, Any] = {
                "kind": hit_kind,
                "key": hit_key,
                "title": hit_title,
            }
            if anchor:
                hit["anchor"] = anchor
            hit["snippet"] = snippet
            formatted_items.append(hit)

        out_search: dict[str, Any] = {
            "total": resp.get("total", len(formatted_items)),
            "items": formatted_items,
        }
        if resp.get("next_cursor"):
            out_search["next_cursor"] = resp["next_cursor"]
        return out_search

    # -------------------------------------------------------------------------
    # MODE 4: List Project / Workspace Knowledge
    # -------------------------------------------------------------------------
    project = arguments.get("project")
    if not project:
        ctx = get_current_mcp_context()
        if ctx is not None and getattr(ctx, "connection_scope", None):
            project = getattr(ctx.connection_scope, "project_key", None)

    out_list: dict[str, Any] = {}
    if project:
        clean_project = str(project).strip()
        out_list["project"] = clean_project

        if target_type in ("DOC", "ALL"):
            if include_tree:
                try:
                    tree_resp = await active_client.request(
                        "GET",
                        f"/api/v1/projects/{clean_project}/docs/tree",
                        subject_token=active_token,
                    )
                    out_list["tree"] = tree_resp if isinstance(tree_resp, list) else []
                except KbMcpError:
                    out_list["tree"] = []
            else:
                try:
                    docs_resp = await active_client.request(
                        "GET",
                        "/api/v1/docs",
                        subject_token=active_token,
                    )
                    docs_list = []
                    if isinstance(docs_resp, list):
                        for d in docs_resp:
                            if not isinstance(d, dict):
                                continue
                            docs_list.append(
                                {
                                    "id": str(d.get("id", "")),
                                    "key": str(d.get("canonical_key", "")),
                                    "title": str(d.get("title", "")),
                                    "version_seq": d.get("version_seq", 1),
                                }
                            )
                    out_list["docs"] = docs_list
                except KbMcpError:
                    out_list["docs"] = []

        if target_type in ("STICKY", "ALL"):
            try:
                stickies_resp = await active_client.request(
                    "GET",
                    f"/api/v1/projects/{clean_project}/stickies",
                    subject_token=active_token,
                )
                stickies_list = []
                if isinstance(stickies_resp, list):
                    for s in stickies_resp:
                        if not isinstance(s, dict):
                            continue
                        s_color = s.get("color_token", "amber")
                        s_body = s.get("body_markdown", "")
                        stickies_list.append(
                            {
                                "id": str(s.get("id")),
                                "color": s_color,
                                "title": _extract_sticky_title(s_body, s_color),
                                "promotion_recommended": bool(
                                    s.get("promotion_recommended", False)
                                ),
                            }
                        )
                out_list["stickies"] = stickies_list
            except KbMcpError:
                out_list["stickies"] = []

        return out_list

    # Workspace level list
    if target_type in ("DOC", "ALL"):
        try:
            docs_resp = await active_client.request(
                "GET", "/api/v1/docs", subject_token=active_token
            )
            docs_list = []
            if isinstance(docs_resp, list):
                for d in docs_resp:
                    if not isinstance(d, dict):
                        continue
                    docs_list.append(
                        {
                            "id": str(d.get("id", "")),
                            "key": str(d.get("canonical_key", "")),
                            "title": str(d.get("title", "")),
                            "version_seq": d.get("version_seq", 1),
                        }
                    )
            out_list["docs"] = docs_list
        except KbMcpError:
            out_list["docs"] = []

    if target_type in ("STICKY", "ALL"):
        try:
            stickies_resp = await active_client.request(
                "GET", f"/api/v1/stickies?limit={limit}", subject_token=active_token
            )
            stickies_list = []
            raw_items = (
                stickies_resp.get("items", [])
                if isinstance(stickies_resp, dict)
                else (stickies_resp if isinstance(stickies_resp, list) else [])
            )
            for s in raw_items:
                if not isinstance(s, dict):
                    continue
                s_color = s.get("color_token", "amber")
                s_body = s.get("body_markdown", "")
                stickies_list.append(
                    {
                        "id": str(s.get("id")),
                        "color": s_color,
                        "title": _extract_sticky_title(s_body, s_color),
                        "promotion_recommended": bool(s.get("promotion_recommended", False)),
                    }
                )
            out_list["stickies"] = stickies_list
        except KbMcpError:
            out_list["stickies"] = []

    return out_list


def create_docs_search_tool(client: KanbanApiClient | None = None) -> ToolSpec:
    """Construct ToolSpec for unified docs search tool."""

    async def _handler(arguments: dict[str, Any], **kwargs: object) -> dict[str, Any]:
        raw_client = kwargs.get("client") or kwargs.get("internal_client")
        active_client = client or (raw_client if hasattr(raw_client, "request") else None)
        raw_token = kwargs.get("subject_token")
        active_token = str(raw_token) if raw_token is not None else None
        return await search_handler(
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
