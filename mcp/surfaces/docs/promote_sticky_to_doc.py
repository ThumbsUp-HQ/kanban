# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Tool promote_sticky_to_doc: Atomic sticky-to-doc conversion preserving ACLs (S11.3)."""

from __future__ import annotations

import re
import uuid
from typing import TYPE_CHECKING, Any, Final

from mcp.context import current_internal_client, current_subject_token
from mcp.errors import KbMcpError, McpErrorCode
from mcp.registry import Surface, ToolSpec

if TYPE_CHECKING:
    from mcp.internal_client import KanbanApiClient

__all__ = [
    "create_promote_sticky_to_doc_tool",
    "promote_sticky_to_doc_handler",
]

_TOOL_NAME: Final[str] = "promote_sticky_to_doc"
_DESCRIPTION: Final[str] = (
    "Atomically promote a complex Sticky into a permanent Doc, "
    "preserving ACLs and creating PROMOTED_TO_DOC link."
)

_INPUT_SCHEMA: Final[dict[str, Any]] = {
    "type": "object",
    "properties": {
        "sticky": {
            "type": "string",
            "description": "UUID of the sticky note to promote",
        },
        "parent": {
            "type": "string",
            "description": "Optional parent doc key, page path, or UUID to promote into as a page",
        },
        "title": {
            "type": "string",
            "description": "Optional display title for the promoted document",
        },
    },
    "required": ["sticky"],
    "additionalProperties": False,
}

_UUID_REGEX: Final[re.Pattern[str]] = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


async def _resolve_parent_ids(
    client: KanbanApiClient,
    parent_ref: str,
    subject_token: str | None,
) -> tuple[str | None, str | None]:
    """Resolve parent doc UUID or page UUID from string reference."""
    clean_ref = parent_ref.strip().lstrip("/")
    if _UUID_REGEX.match(clean_ref):
        # Could be doc or page UUID
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


async def promote_sticky_to_doc_handler(  # noqa: C901
    arguments: dict[str, Any],
    *,
    client: KanbanApiClient | None = None,
    subject_token: str | None = None,
) -> dict[str, Any]:
    """Execute promote_sticky_to_doc tool invocation."""
    sticky_id = arguments.get("sticky")
    if not sticky_id or not isinstance(sticky_id, str):
        msg = "Parameter 'sticky' (UUID) is required"
        raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg)

    clean_sticky_id = sticky_id.strip()
    try:
        uuid.UUID(clean_sticky_id)
    except ValueError:
        msg = f"Invalid sticky UUID '{clean_sticky_id}'"
        raise KbMcpError(McpErrorCode.VALIDATION_FAILED, msg) from None

    active_client = client or current_internal_client.get()
    active_token = subject_token or current_subject_token.get()

    if active_client is None:
        msg = "Internal API client is unavailable"
        raise KbMcpError(McpErrorCode.UPSTREAM_UNAVAILABLE, msg)

    # Pre-check sticky existence and whether already promoted
    sticky_info = await active_client.request(
        "GET",
        f"/api/v1/stickies/{clean_sticky_id}",
        subject_token=active_token,
    )
    if isinstance(sticky_info, dict) and (
        sticky_info.get("is_promoted_stub") or sticky_info.get("promoted_to_doc_id")
    ):
        msg = f"Sticky '{clean_sticky_id}' has already been promoted to a document"
        raise KbMcpError(McpErrorCode.ALREADY_PROMOTED, msg)

    parent_ref = arguments.get("parent")
    title = arguments.get("title")

    parent_doc_id: str | None = None
    parent_page_id: str | None = None
    if parent_ref:
        parent_doc_id, parent_page_id = await _resolve_parent_ids(
            active_client, str(parent_ref), active_token
        )

    promote_payload: dict[str, Any] = {}
    if title:
        promote_payload["title"] = str(title).strip()
    if parent_doc_id:
        promote_payload["parent_doc_id"] = parent_doc_id
    if parent_page_id:
        promote_payload["parent_page_id"] = parent_page_id

    resp = await active_client.request(
        "POST",
        f"/api/v1/stickies/{clean_sticky_id}/promote-to-doc",
        json_data=promote_payload,
        subject_token=active_token,
    )

    if not isinstance(resp, dict):
        msg = "Failed to promote sticky upstream"
        raise KbMcpError(McpErrorCode.UPSTREAM_ERROR, msg)

    doc_key = ""
    promoted_meta = resp.get("promoted_to_doc")
    if isinstance(promoted_meta, dict):
        doc_key = str(promoted_meta.get("canonical_key") or promoted_meta.get("id") or "")
    if not doc_key and resp.get("promoted_to_doc_id"):
        doc_key = f"docs/{resp['promoted_to_doc_id']}"

    return {
        "status": "promoted",
        "doc": doc_key,
        "link": "PROMOTED_TO_DOC",
    }


def create_promote_sticky_to_doc_tool(client: KanbanApiClient | None = None) -> ToolSpec:
    """Construct ToolSpec for promote_sticky_to_doc."""

    async def _handler(arguments: dict[str, Any], **kwargs: object) -> dict[str, Any]:
        raw_client = kwargs.get("client") or kwargs.get("internal_client")
        active_client = client or (raw_client if hasattr(raw_client, "request") else None)
        raw_token = kwargs.get("subject_token")
        active_token = str(raw_token) if raw_token is not None else None
        return await promote_sticky_to_doc_handler(
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
