# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Tool upsert_doc: Create or update Docs/Pages with section patching (S11.3)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Final

from mcp.context import current_internal_client, current_subject_token
from mcp.errors import KbMcpError, McpErrorCode
from mcp.markdown_sections import patch_markdown_section
from mcp.registry import Surface, ToolSpec

if TYPE_CHECKING:
    from mcp.internal_client import KanbanApiClient

__all__ = [
    "create_upsert_doc_tool",
    "upsert_doc_handler",
]

_TOOL_NAME: Final[str] = "upsert_doc"
_DESCRIPTION: Final[str] = (
    "Create or update hierarchical Docs/Pages in canonical Markdown with section patching."
)

_MAX_BODY_BYTES: Final[int] = 1_048_576  # 1 MiB
_MAX_TITLE_LEN: Final[int] = 200
_MAX_PAGE_DEPTH: Final[int] = 10

_INPUT_SCHEMA: Final[dict[str, Any]] = {
    "type": "object",
    "properties": {
        "identifier": {
            "type": "string",
            "description": (
                "Existing doc/page canonical key, path, or UUID to update; omit to create"
            ),
        },
        "parent": {
            "type": "string",
            "description": "Parent doc key or page path when creating a child page",
        },
        "title": {
            "type": "string",
            "minLength": 1,
            "maxLength": 200,
            "description": "Document or page display title (1..200 characters)",
        },
        "body_markdown": {
            "type": "string",
            "description": "Canonical Markdown body content (<= 1,048,576 bytes)",
        },
        "mode": {
            "type": "string",
            "enum": ["replace", "append", "section_patch"],
            "default": "replace",
            "description": "Content update mode: replace, append, or section_patch",
        },
        "section_heading": {
            "type": "string",
            "description": "Case-sensitive target ATX heading required when mode=section_patch",
        },
        "if_match": {
            "type": "string",
            "description": (
                "64-character hex SHA-256 ETag required for concurrency control on update"
            ),
        },
    },
    "additionalProperties": False,
}


async def _fetch_current_entity(
    client: KanbanApiClient,
    identifier: str,
    subject_token: str | None,
) -> tuple[str, dict[str, Any]]:
    """Fetch current doc or page entity to verify existence, retrieve body and ETag."""
    clean_id = identifier.strip().lstrip("/")

    # Try as page
    try:
        page_resp = await client.request(
            "GET", f"/api/v1/pages/{clean_id}", subject_token=subject_token
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


async def upsert_doc_handler(  # noqa: C901, PLR0912, PLR0915
    arguments: dict[str, Any],
    *,
    client: KanbanApiClient | None = None,
    subject_token: str | None = None,
) -> dict[str, Any]:
    """Execute upsert_doc tool invocation."""
    active_client = client or current_internal_client.get()
    active_token = subject_token or current_subject_token.get()

    if active_client is None:
        msg = "Internal API client is unavailable"
        raise KbMcpError(McpErrorCode.UPSTREAM_UNAVAILABLE, msg)

    identifier = arguments.get("identifier")
    parent = arguments.get("parent")
    title = arguments.get("title")
    body_markdown = arguments.get("body_markdown", "")
    mode = arguments.get("mode", "replace")
    section_heading = arguments.get("section_heading")
    if_match = arguments.get("if_match")

    # Validate body size
    if isinstance(body_markdown, str):
        if len(body_markdown.encode("utf-8")) > _MAX_BODY_BYTES:
            msg = f"body_markdown exceeds maximum allowed size of {_MAX_BODY_BYTES} bytes"
            raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)
    else:
        body_markdown = ""

    # =========================================================================
    # CREATE FLOW
    # =========================================================================
    if not identifier:
        if (
            not title
            or not isinstance(title, str)
            or not (1 <= len(title.strip()) <= _MAX_TITLE_LEN)
        ):
            msg = f"Parameter 'title' (1..{_MAX_TITLE_LEN} characters) is required"
            raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

        if parent:
            # Creating child page under parent
            clean_parent = parent.strip().lstrip("/")
            # Check hierarchy depth
            depth_guess = len(clean_parent.split("/"))
            if depth_guess >= _MAX_PAGE_DEPTH:
                msg = (
                    f"Maximum page hierarchy depth ({_MAX_PAGE_DEPTH}) exceeded "
                    f"under parent '{clean_parent}'"
                )
                raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

            create_page_payload = {
                "title": title.strip(),
                "body_markdown": body_markdown,
            }
            # Parent could be doc or page
            page_target = clean_parent
            if page_target.startswith("docs/"):
                page_target = page_target.removeprefix("docs/")
            create_resp = await active_client.request(
                "POST",
                f"/api/v1/docs/{page_target}/pages",
                json_data=create_page_payload,
                subject_token=active_token,
            )
            if not isinstance(create_resp, dict):
                msg = "Failed to create page upstream"
                raise KbMcpError(McpErrorCode.UPSTREAM_ERROR, msg)

            key = str(create_resp.get("canonical_key", ""))
            version_seq = create_resp.get("version_seq", 1)
            etag = str(create_resp.get("etag") or create_resp.get("body_sha256") or "")
            return {
                "status": "created",
                "key": key,
                "version_seq": version_seq,
                "etag": etag,
            }

        # Creating top-level document
        create_doc_payload = {
            "title": title.strip(),
            "body_markdown": body_markdown,
        }
        create_resp = await active_client.request(
            "POST",
            "/api/v1/docs",
            json_data=create_doc_payload,
            subject_token=active_token,
        )
        if not isinstance(create_resp, dict):
            msg = "Failed to create document upstream"
            raise KbMcpError(McpErrorCode.UPSTREAM_ERROR, msg)

        key = str(create_resp.get("canonical_key", ""))
        version_seq = create_resp.get("version_seq", 1)
        etag = str(create_resp.get("etag") or create_resp.get("body_sha256") or "")
        return {
            "status": "created",
            "key": key,
            "version_seq": version_seq,
            "etag": etag,
        }

    # =========================================================================
    # UPDATE FLOW
    # =========================================================================
    # UPDATE FLOW
    # =========================================================================
    if not if_match or not isinstance(if_match, str):
        msg = "Parameter 'if_match' is required when updating a document or page"
        raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

    clean_if_match = if_match.strip().strip('"')

    # Fetch current entity
    entity_kind, current_entity = await _fetch_current_entity(
        active_client, identifier, active_token
    )
    raw_etag = current_entity.get("etag") or current_entity.get("body_sha256") or ""
    current_etag = str(raw_etag).strip().strip('"')

    if clean_if_match != current_etag:
        msg = f"ETag mismatch: client provided '{clean_if_match}', current is '{current_etag}'"
        raise KbMcpError(McpErrorCode.CONFLICT_ETAG, msg)

    raw_body = current_entity.get("body_markdown") or current_entity.get("content_markdown") or ""
    current_body = str(raw_body)

    if mode == "section_patch":
        if not section_heading or not isinstance(section_heading, str):
            msg = "Parameter 'section_heading' is required when mode='section_patch'"
            raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)
        new_body = patch_markdown_section(current_body, section_heading, body_markdown)
    elif mode == "append":
        new_body = f"{current_body}\n\n{body_markdown}" if current_body else body_markdown
    elif mode == "replace":
        new_body = body_markdown
    else:
        msg = f"Unknown mode '{mode}'. Must be one of: replace, append, section_patch"
        raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

    update_payload: dict[str, Any] = {"body_markdown": new_body}
    if title:
        update_payload["title"] = title.strip()

    req_headers = {"If-Match": f'"{clean_if_match}"'}
    canonical_ref = str(current_entity.get("canonical_key") or identifier).lstrip("/")

    if entity_kind == "page":
        update_endpoint = f"/api/v1/pages/{canonical_ref}"
    else:
        doc_ref = canonical_ref.removeprefix("docs/")
        update_endpoint = f"/api/v1/docs/{doc_ref}"

    update_resp = await active_client.request(
        "PATCH",
        update_endpoint,
        json_data=update_payload,
        headers=req_headers,
        subject_token=active_token,
    )

    if not isinstance(update_resp, dict):
        msg = "Failed to update entity upstream"
        raise KbMcpError(McpErrorCode.UPSTREAM_ERROR, msg)

    key = str(update_resp.get("canonical_key", canonical_ref))
    version_seq = update_resp.get("version_seq", current_entity.get("version_seq", 1) + 1)
    etag = str(update_resp.get("etag") or update_resp.get("body_sha256") or "")
    return {
        "status": "updated",
        "key": key,
        "version_seq": version_seq,
        "etag": etag,
    }


def create_upsert_doc_tool(client: KanbanApiClient | None = None) -> ToolSpec:
    """Construct ToolSpec for upsert_doc."""

    async def _handler(arguments: dict[str, Any], **kwargs: object) -> dict[str, Any]:
        raw_client = kwargs.get("client") or kwargs.get("internal_client")
        active_client = client or (raw_client if hasattr(raw_client, "request") else None)
        raw_token = kwargs.get("subject_token")
        active_token = str(raw_token) if raw_token is not None else None
        return await upsert_doc_handler(
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
