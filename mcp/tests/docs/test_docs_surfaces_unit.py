# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
# ruff: noqa: E501, PLR0915, D103, ANN401, ARG001, ARG005, PLC0415, F841, C901, PT018
"""Unit tests targeting 100% branch and line coverage for mcp/surfaces/docs (KANBA-127)."""

from __future__ import annotations

import json
import uuid
from typing import Any

import httpx
import pytest

from mcp.errors import KbMcpError, McpErrorCode
from mcp.internal_client import KanbanApiClient
from mcp.lod import Lod
from mcp.settings import McpSettings
from mcp.surfaces.docs.create import (
    _parse_link_target as parse_create_link,
)
from mcp.surfaces.docs.create import (
    _sync_inline_links as sync_create_links,
)
from mcp.surfaces.docs.create import (
    create_docs_create_tool,
)
from mcp.surfaces.docs.create import (
    create_handler as create_v2_handler,
)
from mcp.surfaces.docs.link_knowledge import link_knowledge_handler
from mcp.surfaces.docs.manage_stickies import manage_stickies_handler
from mcp.surfaces.docs.promote_sticky_to_doc import promote_sticky_to_doc_handler
from mcp.surfaces.docs.read_doc import read_doc_handler
from mcp.surfaces.docs.search import (
    _extract_headings,
    _extract_sticky_title,
    _format_access_pill,
    _read_doc_or_page,
    _read_sticky,
    _try_get_page_or_doc,
    _try_get_sticky,
    create_docs_search_tool,
)
from mcp.surfaces.docs.search import (
    search_handler as search_v2_handler,
)
from mcp.surfaces.docs.search_knowledge import search_knowledge_handler
from mcp.surfaces.docs.update import (
    _diff_patch_content,
    _fetch_current_entity,
    _find_closest_matches,
    _find_line_hints,
    _resolve_parent_ids,
    create_docs_update_tool,
)
from mcp.surfaces.docs.update import (
    _parse_link_target as parse_update_link,
)
from mcp.surfaces.docs.update import (
    _sync_inline_links as sync_update_links,
)
from mcp.surfaces.docs.update import (
    _try_get_sticky as _try_get_sticky_update,
)
from mcp.surfaces.docs.update import (
    update_handler as update_v2_handler,
)
from mcp.surfaces.docs.upsert_doc import upsert_doc_handler


def _build_mock_client(handler_fn: Any) -> KanbanApiClient:
    def wrapped_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/auth/session":
            return httpx.Response(200, json={"csrf_token": "mock-csrf-token"})
        return handler_fn(request)  # type: ignore[no-any-return]

    transport = httpx.MockTransport(wrapped_handler)
    settings = McpSettings(mode="standalone_inprocess", auth_enabled=False)
    return KanbanApiClient(settings, transport=transport)


# =============================================================================
# MANAGE STICKIES UNIT TESTS
# =============================================================================


@pytest.mark.asyncio
async def test_manage_stickies_validations() -> None:
    client = _build_mock_client(lambda r: httpx.Response(200, json={}))

    # 1. Missing action
    with pytest.raises(KbMcpError) as exc:
        await manage_stickies_handler({})
    assert exc.value.code == McpErrorCode.VALIDATION_FAILED

    # 2. Unknown action
    with pytest.raises(KbMcpError) as exc:
        await manage_stickies_handler({"action": "unknown"})
    assert exc.value.code == McpErrorCode.VALIDATION_FAILED

    # 3. Missing project
    with pytest.raises(KbMcpError) as exc:
        await manage_stickies_handler({"action": "create"})
    assert exc.value.code == McpErrorCode.VALIDATION_FAILED

    # 4. Invalid color
    with pytest.raises(KbMcpError) as exc:
        await manage_stickies_handler({"action": "create", "project": "P", "color": "rainbow"})
    assert exc.value.code == McpErrorCode.VALIDATION_FAILED

    # 5. Oversized body
    with pytest.raises(KbMcpError) as exc:
        await manage_stickies_handler(
            {"action": "create", "project": "P", "body_markdown": "x" * 65537}
        )
    assert exc.value.code == McpErrorCode.VALIDATION_FAILED

    # 6. Missing sticky on edit
    with pytest.raises(KbMcpError) as exc:
        await manage_stickies_handler({"action": "edit", "project": "P"}, client=client)
    assert exc.value.code == McpErrorCode.VALIDATION_FAILED

    # 7. Missing body on edit
    with pytest.raises(KbMcpError) as exc:
        await manage_stickies_handler(
            {"action": "edit", "project": "P", "sticky": str(uuid.uuid4())}, client=client
        )
    assert exc.value.code == McpErrorCode.VALIDATION_FAILED

    # 8. Missing color on recolor
    with pytest.raises(KbMcpError) as exc:
        await manage_stickies_handler(
            {"action": "recolor", "project": "P", "sticky": str(uuid.uuid4())}, client=client
        )
    assert exc.value.code == McpErrorCode.VALIDATION_FAILED


@pytest.mark.asyncio
async def test_manage_stickies_mock_flows() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and "/stickies" in request.url.path:
            return httpx.Response(
                200,
                json=[
                    {
                        "id": "018f-1",
                        "color_token": "mint",
                        "body_markdown": "# Note 1\nBody",
                        "promotion_recommended": True,
                    },
                    {
                        "id": "018f-2",
                        "color_token": "sky",
                        "body_markdown": "",
                        "promotion_recommended": False,
                    },
                    "not-a-dict",
                ],
            )
        if request.method == "POST" and "/stickies" in request.url.path:
            return httpx.Response(
                200,
                json={
                    "id": "018f-new",
                    "color_token": "amber",
                    "body_markdown": "New",
                    "promotion_recommended": False,
                },
            )
        if request.method == "PATCH" and "/stickies/" in request.url.path:
            return httpx.Response(
                200,
                json={"id": "018f-patched", "color_token": "coral", "body_markdown": "# Patched"},
            )
        return httpx.Response(404, json={"detail": "not found"})

    client = _build_mock_client(handler)

    # List with populated items
    list_res = await manage_stickies_handler({"action": "list", "project": "PROJ"}, client=client)
    assert len(list_res["stickies"]) == 2

    # Create
    create_res = await manage_stickies_handler(
        {"action": "create", "project": "PROJ", "body_markdown": "New"}, client=client
    )
    assert create_res["status"] == "created"

    # Edit with color
    edit_res = await manage_stickies_handler(
        {
            "action": "edit",
            "project": "PROJ",
            "sticky": "018f-1",
            "body_markdown": "Updated",
            "color": "coral",
        },
        client=client,
    )
    assert edit_res["status"] == "updated"

    # Recolor
    recolor_res = await manage_stickies_handler(
        {"action": "recolor", "project": "PROJ", "sticky": "018f-1", "color": "coral"},
        client=client,
    )
    assert recolor_res["status"] == "recolored"


# =============================================================================
# READ DOC UNIT TESTS
# =============================================================================


@pytest.mark.asyncio
async def test_read_doc_validations_and_sticky() -> None:
    # 1. Missing identifier
    with pytest.raises(KbMcpError) as exc:
        await read_doc_handler({})
    assert exc.value.code == McpErrorCode.VALIDATION_FAILED

    # Sticky mocks
    def sticky_handler(request: httpx.Request) -> httpx.Response:
        if "/stickies/" in request.url.path:
            return httpx.Response(
                200,
                json={
                    "id": "018f-sticky",
                    "color_token": "sky",
                    "body_markdown": "# Sticky Heading\nDetails text.",
                    "promotion_recommended": True,
                    "etag": "tag123",
                    "access_manifest": {"scope": "WORKSPACE"},
                    "capabilities": ["VIEW", "EDIT"],
                    "triggers": ["CHAR_COUNT"],
                    "promoted_to_doc_id": "018f-doc",
                },
            )
        return httpx.Response(404, json={"detail": "not found"})

    client = _build_mock_client(sticky_handler)
    uid = str(uuid.uuid4())

    # Summary
    s_res = await read_doc_handler({"identifier": uid, "lod": "summary"}, client=client)
    assert s_res["kind"] == "sticky"
    assert s_res["title"] == "Sticky Heading"

    # Standard
    std_res = await read_doc_handler({"identifier": uid, "lod": "standard"}, client=client)
    assert std_res["access"] == "workspace"
    assert "body_markdown" in std_res

    # Full
    f_res = await read_doc_handler({"identifier": uid, "lod": "full"}, client=client)
    assert f_res["promoted_to_doc_id"] == "018f-doc"
    assert "capabilities" in f_res


@pytest.mark.asyncio
async def test_read_doc_pages_and_breadcrumbs() -> None:
    def doc_handler(request: httpx.Request) -> httpx.Response:
        p = request.url.path
        if "auth" in p:
            return httpx.Response(
                200,
                json={
                    "id": "018f-page",
                    "canonical_key": "docs/arch/auth",
                    "title": "Auth Page",
                    "version_seq": 2,
                    "parent_title": "Architecture",
                    "etag": "etag1",
                    "body_markdown": "# Auth Page\n\n```python\n# not a heading\n```\n\n## Section 1\nContent.",
                    "outline": [{"level": 2, "text": "Section 1", "anchor": "#section-1"}],
                    "access_manifest": {"scope": "PROJECT"},
                    "permissions": ["VIEW"],
                },
            )
        if "docs" in p or "arch" in p:
            return httpx.Response(
                200,
                json={
                    "id": "018f-doc",
                    "canonical_key": "docs/arch",
                    "title": "Architecture",
                    "version_seq": 1,
                    "breadcrumbs": [{"title": "Root"}, {"title": "Architecture"}],
                    "etag": "etag0",
                    "body_markdown": "# Architecture",
                    "outline": [],
                },
            )
        return httpx.Response(404, json={"detail": "not found"})

    client = _build_mock_client(doc_handler)

    # Read page with parent_title breadcrumbs
    p_res = await read_doc_handler(
        {"identifier": "pages/arch/auth", "lod": "summary"}, client=client
    )
    assert p_res["breadcrumbs"] == ["Architecture", "Auth Page"]

    # Read page standard
    p_std = await read_doc_handler(
        {"identifier": "docs/arch/auth", "lod": "standard"}, client=client
    )
    assert "body_markdown" in p_std

    # Read page full
    p_full = await read_doc_handler({"identifier": "docs/arch/auth", "lod": "full"}, client=client)
    assert p_full["outline"][0]["anchor"] == "#auth-page"
    assert p_full["outline"][1]["anchor"] == "#section-1"
    assert "access_manifest" in p_full

    # Read doc
    d_res = await read_doc_handler({"identifier": "docs/arch", "lod": "summary"}, client=client)
    assert d_res["breadcrumbs"] == ["Root", "Architecture"]


# =============================================================================
# SEARCH KNOWLEDGE UNIT TESTS
# =============================================================================


@pytest.mark.asyncio
async def test_search_knowledge_mock() -> None:
    def search_handler(request: httpx.Request) -> httpx.Response:
        data = json.loads(request.content.decode("utf-8"))
        assert data["query"] == "PKCE"
        return httpx.Response(
            200,
            json={
                "total": 1,
                "next_cursor": "cur-next",
                "items": [
                    {
                        "kind": "doc",
                        "key": "docs/auth",
                        "title": "Auth Spec",
                        "anchor": "pkce",
                        "snippet": "S" * 350,
                    },
                    "not-a-dict",
                ],
            },
        )

    client = _build_mock_client(search_handler)
    res = await search_knowledge_handler(
        {"query": "PKCE", "cursor": "cur-1", "project": "SEC"},
        client=client,
    )
    assert res["total"] == 1
    assert res["next_cursor"] == "cur-next"
    assert res["items"][0]["anchor"] == "#pkce"
    assert len(res["items"][0]["snippet"]) == 300


# =============================================================================
# UPSERT DOC UNIT TESTS
# =============================================================================


@pytest.mark.asyncio
async def test_upsert_doc_modes_and_validations() -> None:
    client_dummy = _build_mock_client(lambda r: httpx.Response(200, json={}))

    # 1. Missing if_match on update
    with pytest.raises(KbMcpError) as exc:
        await upsert_doc_handler(
            {"identifier": "docs/existing", "body_markdown": "x"}, client=client_dummy
        )
    assert exc.value.code == McpErrorCode.VALIDATION_FAILED

    # 2. Missing section_heading on section_patch
    def entity_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "id": "018f-e",
                "canonical_key": "docs/doc",
                "etag": "tag-a",
                "body_markdown": "## Sec\nText",
                "version_seq": 1,
            },
        )

    client = _build_mock_client(entity_handler)

    with pytest.raises(KbMcpError) as exc:
        await upsert_doc_handler(
            {
                "identifier": "docs/doc",
                "if_match": "tag-a",
                "mode": "section_patch",
                "body_markdown": "x",
            },
            client=client,
        )
    assert exc.value.code == McpErrorCode.VALIDATION_FAILED

    # Replace mode
    res_replace = await upsert_doc_handler(
        {
            "identifier": "docs/doc",
            "if_match": "tag-a",
            "mode": "replace",
            "body_markdown": "# New Doc",
            "title": "New Title",
        },
        client=client,
    )
    assert res_replace["status"] == "updated"


# =============================================================================
# PROMOTE STICKY UNIT TESTS
# =============================================================================


@pytest.mark.asyncio
async def test_promote_sticky_parent_resolutions() -> None:
    def parent_handler(request: httpx.Request) -> httpx.Response:
        p = request.url.path
        if "/stickies/" in p and request.method == "GET":
            return httpx.Response(200, json={"id": "018f-stk", "is_promoted_stub": False})
        if "/pages/" in p and request.method == "GET":
            return httpx.Response(200, json={"id": "018f-parent-page", "doc_id": "018f-parent-doc"})
        if "/docs/" in p and request.method == "GET":
            return httpx.Response(200, json={"id": "018f-parent-doc"})
        if "/promote-to-doc" in p:
            return httpx.Response(200, json={"promoted_to_doc": {"canonical_key": "docs/promoted"}})
        return httpx.Response(404)

    client = _build_mock_client(parent_handler)
    uid = str(uuid.uuid4())

    # Promote under page
    res_page = await promote_sticky_to_doc_handler(
        {"sticky": uid, "parent": "docs/arch/auth", "title": "Page Promoted"},
        client=client,
    )
    assert res_page["status"] == "promoted"
    assert res_page["doc"] == "docs/promoted"

    # Promote under raw UUID
    raw_uid = str(uuid.uuid4())
    res_raw = await promote_sticky_to_doc_handler(
        {"sticky": uid, "parent": raw_uid, "title": "UUID Promoted"},
        client=client,
    )
    assert res_raw["status"] == "promoted"


# =============================================================================
# LINK KNOWLEDGE UNIT TESTS
# =============================================================================


@pytest.mark.asyncio
async def test_link_knowledge_validations_and_remove() -> None:
    # Missing source
    with pytest.raises(KbMcpError) as exc:
        await link_knowledge_handler({"target": "T", "target_kind": "issue"})
    assert exc.value.code == McpErrorCode.VALIDATION_FAILED

    # Missing target
    with pytest.raises(KbMcpError) as exc:
        await link_knowledge_handler({"source": "S", "target_kind": "issue"})
    assert exc.value.code == McpErrorCode.VALIDATION_FAILED

    # Missing target_kind
    with pytest.raises(KbMcpError) as exc:
        await link_knowledge_handler({"source": "S", "target": "T"})
    assert exc.value.code == McpErrorCode.VALIDATION_FAILED

    # Sticky with VERIFIED_BY_DOC rejection
    def sticky_client_handler(request: httpx.Request) -> httpx.Response:
        if "/stickies/" in request.url.path:
            return httpx.Response(200, json={"id": "018f-stk", "color_token": "sky"})
        return httpx.Response(404)

    client = _build_mock_client(sticky_client_handler)
    stk_uid = str(uuid.uuid4())

    with pytest.raises(KbMcpError) as exc:
        await link_knowledge_handler(
            {
                "source": stk_uid,
                "target": "ISSUE-1",
                "target_kind": "issue",
                "link_type": "VERIFIED_BY_DOC",
            },
            client=client,
        )
    assert exc.value.code == McpErrorCode.LINK_TYPE_NOT_ALLOWED

    # Action remove with matching outbound edge
    def remove_handler(request: httpx.Request) -> httpx.Response:
        p = request.url.path
        if "/links" in p and request.method == "GET":
            return httpx.Response(
                200,
                json={
                    "outbound": [
                        {
                            "id": "link-123",
                            "type": "RELATES_TO",
                            "target": {"key": "ISSUE-1", "id": "018f-target"},
                        }
                    ]
                },
            )
        if "/links/link-123" in p and request.method == "DELETE":
            return httpx.Response(204)
        return httpx.Response(200, json={"id": "018f-src"})

    rem_client = _build_mock_client(remove_handler)
    res_rem = await link_knowledge_handler(
        {
            "source": "pages/my-page",
            "target": "ISSUE-1",
            "target_kind": "issue",
            "action": "remove",
        },
        client=rem_client,
    )
    assert res_rem["status"] == "unlinked"


@pytest.mark.asyncio
async def test_docs_additional_edge_branches() -> None:
    # 1. search_knowledge resp not dict
    c_empty = _build_mock_client(lambda r: httpx.Response(200, content=b"[]"))
    res_empty_search = await search_knowledge_handler({"query": "q"}, client=c_empty)
    assert res_empty_search["total"] == 0

    # 2. search_knowledge hit without anchor
    c_no_anchor = _build_mock_client(
        lambda r: httpx.Response(
            200, json={"items": [{"kind": "doc", "title": "T", "key": "k", "snippet": "S"}]}
        )
    )
    res_no_anchor = await search_knowledge_handler({"query": "q"}, client=c_no_anchor)
    assert "anchor" not in res_no_anchor["items"][0]

    # 3. promote_sticky_to_doc parent resolution as doc
    def promote_doc_handler(request: httpx.Request) -> httpx.Response:
        p = request.url.path
        if "/stickies/" in p and request.method == "GET":
            return httpx.Response(200, json={"id": "018f-stk", "is_promoted_stub": False})
        if "/pages/" in p and request.method == "GET":
            return httpx.Response(404)
        if "/docs/" in p and request.method == "GET":
            return httpx.Response(200, json={"id": "018f-parent-doc-only"})
        if "/promote-to-doc" in p:
            return httpx.Response(200, json={"promoted_to_doc": {"id": "018f-p-id"}})
        return httpx.Response(404)

    c_prom_doc = _build_mock_client(promote_doc_handler)
    res_prom_doc = await promote_sticky_to_doc_handler(
        {"sticky": str(uuid.uuid4()), "parent": "docs/my-parent"},
        client=c_prom_doc,
    )
    assert res_prom_doc["status"] == "promoted"

    # 4. promote_sticky_to_doc already promoted
    c_promoted = _build_mock_client(lambda r: httpx.Response(200, json={"is_promoted_stub": True}))
    with pytest.raises(KbMcpError) as exc_prom:
        await promote_sticky_to_doc_handler({"sticky": str(uuid.uuid4())}, client=c_promoted)
    assert exc_prom.value.code == McpErrorCode.ALREADY_PROMOTED

    # 5. read_doc not found
    c_404 = _build_mock_client(lambda r: httpx.Response(404))
    with pytest.raises(KbMcpError) as exc_404:
        await read_doc_handler({"identifier": "docs/unknown"}, client=c_404)
    assert exc_404.value.code == McpErrorCode.NOT_FOUND

    # 6. upsert_doc oversized body
    with pytest.raises(KbMcpError) as exc_size:
        await upsert_doc_handler({"title": "Too big", "body_markdown": "x" * 1048577}, client=c_404)
    assert exc_size.value.code == McpErrorCode.VALIDATION_FAILED

    # 7. upsert_doc depth limit
    with pytest.raises(KbMcpError) as exc_depth:
        await upsert_doc_handler(
            {"title": "Deep", "parent": "docs/1/2/3/4/5/6/7/8/9/10"}, client=c_404
        )
    assert exc_depth.value.code == McpErrorCode.VALIDATION_FAILED

    # 8. manage_stickies body_markdown non-string conversion
    c_stk = _build_mock_client(
        lambda r: httpx.Response(
            200, json={"id": "018f-stk", "color_token": "amber", "body_markdown": "123"}
        )
    )
    stk_non_str = await manage_stickies_handler(
        {"action": "create", "project": "P", "body_markdown": 123}, client=c_stk
    )
    assert stk_non_str["status"] == "created"

    # 9. upstream error branches (non-dict returns)
    c_nondict = _build_mock_client(lambda r: httpx.Response(200, content=b"[]"))

    with pytest.raises(KbMcpError):
        await manage_stickies_handler({"action": "create", "project": "P"}, client=c_nondict)

    with pytest.raises(KbMcpError):
        await manage_stickies_handler(
            {"action": "edit", "project": "P", "sticky": str(uuid.uuid4()), "body_markdown": "b"},
            client=c_nondict,
        )

    with pytest.raises(KbMcpError):
        await upsert_doc_handler({"title": "T"}, client=c_nondict)

    with pytest.raises(KbMcpError):
        await upsert_doc_handler({"title": "T", "parent": "docs/p"}, client=c_nondict)

    with pytest.raises(KbMcpError):
        await upsert_doc_handler(
            {"identifier": "docs/d", "if_match": "tag", "body_markdown": "b"}, client=c_nondict
        )

    with pytest.raises(KbMcpError):
        await promote_sticky_to_doc_handler({"sticky": str(uuid.uuid4())}, client=c_nondict)

    # 10. promote_sticky_to_doc with promoted_to_doc_id fallback
    def promote_id_fallback(request: httpx.Request) -> httpx.Response:
        p = request.url.path
        if "/stickies/" in p and request.method == "GET":
            return httpx.Response(200, json={"id": "018f-stk", "is_promoted_stub": False})
        if "/promote-to-doc" in p:
            return httpx.Response(200, json={"promoted_to_doc_id": "018f-fallback-doc"})
        return httpx.Response(404)

    c_prom_fb = _build_mock_client(promote_id_fallback)
    res_fb = await promote_sticky_to_doc_handler({"sticky": str(uuid.uuid4())}, client=c_prom_fb)
    assert res_fb["doc"] == "docs/018f-fallback-doc"

    # 11. read_doc sticky with empty first line fallback
    def sticky_empty_title_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"id": "018f-stk", "color_token": "coral", "body_markdown": "#\nSecond line"}
        )

    # 12. link_knowledge _resolve_source_id branches & remove matching t_id
    def link_id_matching_handler(request: httpx.Request) -> httpx.Response:
        p = request.url.path
        if "/pages/" in p:
            return httpx.Response(200, json={"id": "018f-page-id"})
        if "/docs/" in p:
            return httpx.Response(200, json={"id": "018f-doc-id"})
        if "/links" in p and request.method == "GET":
            return httpx.Response(
                200,
                json={
                    "outbound": [
                        "not-a-dict",
                        {
                            "link_type": "RELATES_TO",
                            "target": {"id": "target-uuid", "key": "OTHER"},
                        },
                    ]
                },
            )
        if request.method == "DELETE":
            return httpx.Response(204)
        return httpx.Response(200, json={})

    c_link_id = _build_mock_client(link_id_matching_handler)
    res_rem_id = await link_knowledge_handler(
        {
            "source": "docs/arch-doc",
            "target": "target-uuid",
            "target_kind": "cycle",
            "action": "remove",
        },
        client=c_link_id,
    )
    assert res_rem_id["status"] == "unlinked"

    # Raw UUID source for link_knowledge
    raw_src_uid = str(uuid.uuid4())
    res_raw_link = await link_knowledge_handler(
        {
            "source": raw_src_uid,
            "target": "target-uuid",
            "target_kind": "module",
            "action": "remove",
        },
        client=c_link_id,
    )
    assert res_raw_link["status"] == "unlinked"

    # 13. Tool registration factories coverage
    from mcp.surfaces.docs.link_knowledge import create_link_knowledge_tool
    from mcp.surfaces.docs.manage_stickies import create_manage_stickies_tool
    from mcp.surfaces.docs.promote_sticky_to_doc import create_promote_sticky_to_doc_tool
    from mcp.surfaces.docs.read_doc import create_read_doc_tool
    from mcp.surfaces.docs.search_knowledge import create_search_knowledge_tool
    from mcp.surfaces.docs.upsert_doc import create_upsert_doc_tool

    assert create_link_knowledge_tool(client=c_link_id).name == "link_knowledge"
    assert create_manage_stickies_tool(client=c_link_id).name == "manage_stickies"
    assert create_promote_sticky_to_doc_tool(client=c_link_id).name == "promote_sticky_to_doc"
    assert create_read_doc_tool(client=c_link_id).name == "read_doc"
    assert create_search_knowledge_tool(client=c_link_id).name == "search_knowledge"
    assert create_upsert_doc_tool(client=c_link_id).name == "upsert_doc"

    # 14. read_doc breadcrumbs default fallback
    def doc_no_crumbs(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "id": "018f-doc",
                "canonical_key": "docs/plain",
                "title": "Plain Doc",
                "version_seq": 1,
            },
        )

    c_plain = _build_mock_client(doc_no_crumbs)
    res_plain = await read_doc_handler(
        {"identifier": "docs/plain", "lod": "summary"}, client=c_plain
    )
    assert res_plain["breadcrumbs"] == ["Plain Doc"]


@pytest.mark.asyncio
async def test_docs_all_remaining_uncovered_branches() -> None:
    """Test all remaining defensive, error, and client=None branches for >=95% coverage."""
    # 1. client=None on all 6 handlers
    with pytest.raises(KbMcpError) as exc:
        await search_knowledge_handler({"query": "q"})
    assert exc.value.code == McpErrorCode.UPSTREAM_UNAVAILABLE

    with pytest.raises(KbMcpError) as exc:
        await read_doc_handler({"identifier": "docs/test"})
    assert exc.value.code == McpErrorCode.UPSTREAM_UNAVAILABLE

    with pytest.raises(KbMcpError) as exc:
        await upsert_doc_handler({"title": "T"})
    assert exc.value.code == McpErrorCode.UPSTREAM_UNAVAILABLE

    with pytest.raises(KbMcpError) as exc:
        await manage_stickies_handler({"action": "list", "project": "P"})
    assert exc.value.code == McpErrorCode.UPSTREAM_UNAVAILABLE

    with pytest.raises(KbMcpError) as exc:
        await promote_sticky_to_doc_handler({"sticky": str(uuid.uuid4())})
    assert exc.value.code == McpErrorCode.UPSTREAM_UNAVAILABLE

    with pytest.raises(KbMcpError) as exc:
        await link_knowledge_handler({"source": "s", "target": "t", "target_kind": "issue"})
    assert exc.value.code == McpErrorCode.UPSTREAM_UNAVAILABLE

    # 2. Tool wrappers invocation
    def dummy_handler(request: httpx.Request) -> httpx.Response:
        p = request.url.path
        if "/search" in p:
            return httpx.Response(200, json={"items": [], "next_cursor": None})
        if "/promote-to-doc" in p:
            return httpx.Response(200, json={"promoted_to_doc": {"canonical_key": "docs/dummy"}})
        if "/docs" in p or "/pages" in p:
            return httpx.Response(
                200,
                json={
                    "id": "018f-dummy",
                    "canonical_key": "docs/dummy",
                    "title": "Dummy",
                    "version_seq": 1,
                },
            )
        if "/stickies" in p:
            return httpx.Response(200, json=[])
        if "/links" in p:
            return httpx.Response(200, json={})
        return httpx.Response(200, json={})

    client = _build_mock_client(dummy_handler)

    from mcp.surfaces.docs.link_knowledge import create_link_knowledge_tool
    from mcp.surfaces.docs.manage_stickies import create_manage_stickies_tool
    from mcp.surfaces.docs.promote_sticky_to_doc import create_promote_sticky_to_doc_tool
    from mcp.surfaces.docs.read_doc import create_read_doc_tool
    from mcp.surfaces.docs.search_knowledge import create_search_knowledge_tool
    from mcp.surfaces.docs.upsert_doc import create_upsert_doc_tool

    # Invoking each tool's handler
    t_search = create_search_knowledge_tool()
    res = await t_search.handler({"query": "hello"}, client=client)  # type: ignore[call-arg]
    assert "items" in res

    t_read = create_read_doc_tool()
    res = await t_read.handler({"identifier": "docs/dummy"}, client=client)  # type: ignore[call-arg]
    assert res["title"] == "Dummy"

    t_upsert = create_upsert_doc_tool()
    res = await t_upsert.handler({"title": "Dummy", "body_markdown": "Body"}, client=client)  # type: ignore[call-arg]
    assert res["status"] == "created"

    t_stickies = create_manage_stickies_tool()
    res = await t_stickies.handler({"action": "list", "project": "P"}, client=client)  # type: ignore[call-arg]
    assert "stickies" in res

    t_promote = create_promote_sticky_to_doc_tool()
    res = await t_promote.handler({"sticky": str(uuid.uuid4())}, client=client)  # type: ignore[call-arg]
    assert res["doc"] == "docs/dummy"

    t_link = create_link_knowledge_tool()
    res = await t_link.handler(  # type: ignore[call-arg]
        {"source": "docs/dummy", "target": "018f-other", "target_kind": "issue"}, client=client
    )
    assert res["status"] == "linked"

    # 3. link_knowledge: VERIFIED_BY_DOC sticky rejection
    stk_uuid = str(uuid.uuid4())

    def sticky_client_handler(request: httpx.Request) -> httpx.Response:
        p = request.url.path
        if f"/stickies/{stk_uuid}" in p:
            return httpx.Response(200, json={"id": stk_uuid, "color_token": "mint"})
        return httpx.Response(404)

    c_stk = _build_mock_client(sticky_client_handler)
    with pytest.raises(KbMcpError) as exc:
        await link_knowledge_handler(
            {
                "source": stk_uuid,
                "target": "018f-issue",
                "target_kind": "issue",
                "link_type": "VERIFIED_BY_DOC",
            },
            client=c_stk,
        )
    assert exc.value.code == McpErrorCode.LINK_TYPE_NOT_ALLOWED

    # 4. link_knowledge: pages/ prefix and slash resolution failure fallthrough
    def not_found_resolver(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and "/links" in request.url.path:
            return httpx.Response(201, json={"id": "new-link"})
        return httpx.Response(404, json={"detail": "not found"})

    c_not_found = _build_mock_client(not_found_resolver)
    # pages/ prefix not found
    res = await link_knowledge_handler(
        {"source": "pages/missing-page", "target": "ISSUE-1", "target_kind": "issue"},
        client=c_not_found,
    )
    assert res["status"] == "linked"

    # slash path not found
    res = await link_knowledge_handler(
        {"source": "docs/missing-doc/sub", "target": "ISSUE-1", "target_kind": "issue"},
        client=c_not_found,
    )
    assert res["status"] == "linked"

    # 5. upsert_doc parent not found & section_patch without section_heading
    c_404 = _build_mock_client(lambda r: httpx.Response(404, json={"detail": "not found"}))
    with pytest.raises(KbMcpError) as exc:
        await upsert_doc_handler(
            {"title": "Child", "parent": "docs/nonexistent-parent"},
            client=c_404,
        )
    assert exc.value.code == McpErrorCode.NOT_FOUND

    c_matched_etag = _build_mock_client(
        lambda r: httpx.Response(
            200, json={"id": "018f-dummy", "canonical_key": "docs/dummy", "etag": "abc123"}
        )
    )
    with pytest.raises(KbMcpError) as exc:
        await upsert_doc_handler(
            {"identifier": "docs/dummy", "if_match": "abc123", "mode": "section_patch"},
            client=c_matched_etag,
        )
    assert exc.value.code == McpErrorCode.VALIDATION_FAILED

    # upsert_doc without body_markdown (covers line 126 body_markdown = "")
    res_no_body = await upsert_doc_handler({"title": "No Body Doc"}, client=client)
    assert res_no_body["status"] == "created"

    # 6. read_doc additional paths (pages/ prefix, direct page, standard lod)
    def read_doc_multi_handler(request: httpx.Request) -> httpx.Response:
        p = request.url.path
        if "/pages/prefixed" in p:
            return httpx.Response(
                200,
                json={
                    "id": "018f-p1",
                    "title": "Prefixed Page",
                    "body_markdown": "Body P1",
                    "breadcrumbs": ["Root", "Prefixed Page"],
                    "version_seq": 1,
                },
            )
        if "/pages/direct-page" in p:
            return httpx.Response(
                200,
                json={
                    "id": "018f-p2",
                    "title": "Direct Page",
                    "content_markdown": "Content P2",
                    "breadcrumbs": ["Direct Page"],
                    "version_seq": 2,
                },
            )
        if "/stickies/" in p:
            return httpx.Response(
                200, json={"id": "018f-stk", "color_token": "sky", "body_markdown": ""}
            )
        return httpx.Response(404)

    c_read_multi = _build_mock_client(read_doc_multi_handler)
    res_pref = await read_doc_handler(
        {"identifier": "pages/prefixed", "lod": "standard"}, client=c_read_multi
    )
    assert res_pref["title"] == "Prefixed Page"
    assert res_pref["body_markdown"] == "Body P1"

    res_dir = await read_doc_handler(
        {"identifier": "direct-page", "lod": "standard"}, client=c_read_multi
    )
    assert res_dir["title"] == "Direct Page"
    assert res_dir["body_markdown"] == "Content P2"

    # read_doc sticky with empty body
    res_stk_empty = await read_doc_handler(
        {"identifier": str(uuid.uuid4()), "lod": "summary"}, client=c_read_multi
    )
    assert res_stk_empty["title"] == "Sticky sky"

    # 7. promote_sticky_to_doc parent resolution returning None & upstream non-dict error
    def promote_no_parent(request: httpx.Request) -> httpx.Response:
        if "/stickies/" in request.url.path and request.method == "GET":
            return httpx.Response(200, json={"id": "018f-stk", "is_promoted_stub": False})
        if "/promote-to-doc" in request.url.path:
            return httpx.Response(200, json=["not-a-dict"])
        return httpx.Response(404)

    c_prom_np = _build_mock_client(promote_no_parent)
    with pytest.raises(KbMcpError) as exc:
        await promote_sticky_to_doc_handler(
            {"sticky": str(uuid.uuid4()), "parent": "docs/unknown-parent"},
            client=c_prom_np,
        )
    assert exc.value.code == McpErrorCode.UPSTREAM_ERROR

    with pytest.raises(KbMcpError) as exc:
        await promote_sticky_to_doc_handler(
            {"sticky": str(uuid.uuid4())},
            client=c_prom_np,
        )
    assert exc.value.code == McpErrorCode.UPSTREAM_ERROR

    # promote_sticky_to_doc on already promoted sticky
    def promote_already_done(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"id": "018f-stk", "is_promoted_stub": True})

    c_already = _build_mock_client(promote_already_done)
    with pytest.raises(KbMcpError) as exc:
        await promote_sticky_to_doc_handler({"sticky": str(uuid.uuid4())}, client=c_already)
    assert exc.value.code == McpErrorCode.ALREADY_PROMOTED

    # 8. read_doc sticky with lod="full"
    def sticky_full_handler(request: httpx.Request) -> httpx.Response:
        if "/stickies/" in request.url.path:
            return httpx.Response(
                200,
                json={
                    "id": "018f-stk",
                    "color_token": "mint",
                    "body_markdown": "# Title\nBody full",
                },
            )
        return httpx.Response(404)

    c_stk_full = _build_mock_client(sticky_full_handler)
    res_stk_full = await read_doc_handler(
        {"identifier": str(uuid.uuid4()), "lod": "full"}, client=c_stk_full
    )
    assert res_stk_full["body_markdown"] == "# Title\nBody full"

    # 9. upsert_doc non-dict response on update
    def update_non_dict_handler(request: httpx.Request) -> httpx.Response:
        p = request.url.path
        if request.method == "GET":
            return httpx.Response(
                200,
                json={
                    "id": "018f-doc",
                    "canonical_key": "docs/test",
                    "etag": "abc123",
                    "body_markdown": "old",
                },
            )
        if request.method == "PATCH":
            return httpx.Response(200, json=["not-a-dict"])
        return httpx.Response(404)

    c_up_non_dict = _build_mock_client(update_non_dict_handler)
    with pytest.raises(KbMcpError) as exc:
        await upsert_doc_handler(
            {
                "identifier": "docs/test",
                "body_markdown": "new",
                "if_match": "abc123",
                "mode": "replace",
            },
            client=c_up_non_dict,
        )
    assert exc.value.code == McpErrorCode.UPSTREAM_ERROR

    # 10. Help actions and modes
    res_stk_help = await manage_stickies_handler({"action": "help"}, client=client)
    assert "actions" in res_stk_help or "help" in str(res_stk_help)

    res_read_help = await read_doc_handler({"identifier": "help"}, client=client)
    assert res_read_help["title"] == "Dummy"

    # 11. link_knowledge resolution branches
    def multi_resolve_handler(request: httpx.Request) -> httpx.Response:
        p = request.url.path
        if "/pages/valid-page" in p:
            return httpx.Response(200, json={"id": "page-uuid-1"})
        if "/pages/docs/valid/sub" in p:
            return httpx.Response(200, json={"id": "subpage-uuid-2"})
        if "/docs/valid-doc" in p:
            return httpx.Response(200, json={"id": "doc-uuid-3"})
        if "/links" in p and request.method == "POST":
            return httpx.Response(201, json={"id": "link-ok"})
        return httpx.Response(404)

    c_multi_res = _build_mock_client(multi_resolve_handler)
    res_p1 = await link_knowledge_handler(
        {"source": "pages/valid-page", "target": "018f-iss", "target_kind": "issue"},
        client=c_multi_res,
    )
    assert res_p1["status"] == "linked"

    res_p2 = await link_knowledge_handler(
        {"source": "docs/valid/sub", "target": "018f-iss", "target_kind": "issue"},
        client=c_multi_res,
    )
    assert res_p2["status"] == "linked"

    res_p3 = await link_knowledge_handler(
        {"source": "docs/valid-doc", "target": "018f-iss", "target_kind": "issue"},
        client=c_multi_res,
    )
    assert res_p3["status"] == "linked"


# =============================================================================
# CONSOLIDATED /mcp/docs V2 TOOLS UNIT TESTS (KAN-18)
# =============================================================================


@pytest.mark.asyncio
async def test_create_v2_unit_coverage() -> None:
    client = _build_mock_client(lambda r: httpx.Response(201, json={"id": "doc-uuid-1"}))

    # Link targets parsing
    t1, lt1 = parse_create_link("VERIFIED_BY_DOC:XYZ")
    assert t1 == "XYZ" and lt1 == "VERIFIED_BY_DOC"
    t2, lt2 = parse_create_link("PLAIN")
    assert t2 == "PLAIN" and lt2 == "RELATES_TO"

    # Sync links with dict and failure
    def link_err_h(req: httpx.Request) -> httpx.Response:
        if "fail" in str(req.read()):
            return httpx.Response(500, json={"error": "db err"})
        return httpx.Response(201, json={"status": "ok"})

    c_link = _build_mock_client(link_err_h)
    res_sync = await sync_create_links(
        c_link,
        "src-1",
        {
            "add": ["T1", "fail-target"],
            "remove": [],
        },
        None,
    )
    assert len(res_sync) == 2

    # Validation errors
    with pytest.raises(KbMcpError) as exc:
        await create_v2_handler({"type": "DOC", "title": "T"}, client=None)
    assert exc.value.code == McpErrorCode.UPSTREAM_UNAVAILABLE

    with pytest.raises(KbMcpError) as exc:
        await create_v2_handler({}, client=client)
    assert exc.value.code == McpErrorCode.VALIDATION_FAILED

    with pytest.raises(KbMcpError) as exc:
        await create_v2_handler({"type": "BOGUS", "title": "T"}, client=client)
    assert exc.value.code == McpErrorCode.VALIDATION_FAILED

    with pytest.raises(KbMcpError) as exc:
        await create_v2_handler({"type": "STICKY", "title": "S", "parent": "p"}, client=client)
    assert exc.value.code == McpErrorCode.VALIDATION_FAILED

    with pytest.raises(KbMcpError) as exc:
        await create_v2_handler({"type": "STICKY", "title": "S"}, client=client)
    assert exc.value.code == McpErrorCode.VALIDATION_FAILED

    with pytest.raises(KbMcpError) as exc:
        await create_v2_handler(
            {"type": "STICKY", "title": "S", "project": "P", "color": "bad"}, client=client
        )
    assert exc.value.code == McpErrorCode.VALIDATION_FAILED

    # Sticky content without title prefix
    def stk_h(req: httpx.Request) -> httpx.Response:
        return httpx.Response(201, json={"id": "stk-id-1", "color_token": "mint"})

    c_stk = _build_mock_client(stk_h)
    stk_res = await create_v2_handler(
        {"type": "STICKY", "title": "Title", "project": "P", "content": "Raw content"},
        client=c_stk,
    )
    assert stk_res["status"] == "created"

    # Sticky upstream error
    c_stk_err = _build_mock_client(lambda r: httpx.Response(200, json=["non-dict"]))
    with pytest.raises(KbMcpError) as exc:
        await create_v2_handler(
            {"type": "STICKY", "title": "Title", "project": "P"}, client=c_stk_err
        )
    assert exc.value.code == McpErrorCode.UPSTREAM_ERROR

    # Doc with project UUID
    u = str(uuid.uuid4())
    doc_uuid_res = await create_v2_handler(
        {"type": "DOC", "title": "Doc Title", "project": u}, client=client
    )
    assert doc_uuid_res["status"] == "created"

    # Doc upstream error
    with pytest.raises(KbMcpError) as exc:
        await create_v2_handler({"type": "DOC", "title": "Doc"}, client=c_stk_err)
    assert exc.value.code == McpErrorCode.UPSTREAM_ERROR

    # Project key resolution failure raises NOT_FOUND
    def proj_fail_h(req: httpx.Request) -> httpx.Response:
        if "/projects/" in req.url.path:
            return httpx.Response(404, json={"detail": "not found"})
        return httpx.Response(201, json={"id": "d-id-pf"})

    c_pf = _build_mock_client(proj_fail_h)
    with pytest.raises(KbMcpError) as exc:
        await create_v2_handler({"type": "DOC", "title": "Doc", "project": "FAIL_KEY"}, client=c_pf)
    assert exc.value.code == McpErrorCode.NOT_FOUND

    # Project key resolution success and inline links variations
    def proj_succ_h(req: httpx.Request) -> httpx.Response:
        p = req.url.path
        if "/projects/SUCC_KEY" in p:
            return httpx.Response(200, json={"id": "proj-uuid-succ"})
        if "/links" in p:
            return httpx.Response(201, json={"status": "ok"})
        return httpx.Response(201, json={"id": "d-id-ps"})

    c_ps = _build_mock_client(proj_succ_h)
    res_ps = await create_v2_handler(
        {
            "type": "DOC",
            "title": "Doc Succ",
            "project": "SUCC_KEY",
            "links": [
                "+PREFIX:T1",
                {"action": "add", "target": "T2", "link_type": "VERIFIED_BY_DOC"},
                "",
            ],
        },
        client=c_ps,
    )
    assert res_ps["status"] == "created"

    # ToolSpec builder handler
    tool = create_docs_create_tool(client=client)
    res_tool = await tool.handler({"type": "DOC", "title": "Tool Doc"})
    assert res_tool["status"] == "created"


@pytest.mark.asyncio
async def test_search_v2_unit_coverage() -> None:
    # Heading outline with code fences
    md = "# H1\n```python\n# inside fence\n```\n~~~bash\n# fence 2\n~~~\n## H2\n"
    outl = _extract_headings(md)
    assert len(outl) == 2

    # Sticky title extraction
    assert _extract_sticky_title("", "mint") == "Sticky mint"
    assert _extract_sticky_title("Line", "sky") == "Line"

    # Access pill
    assert _format_access_pill(None) == "project"
    assert _format_access_pill({"scope": "WORKSPACE"}) == "workspace"

    # Client unavailable
    with pytest.raises(KbMcpError) as exc:
        await search_v2_handler({}, client=None)
    assert exc.value.code == McpErrorCode.UPSTREAM_UNAVAILABLE

    # Sticky not found when type is STICKY
    c_404 = _build_mock_client(lambda r: httpx.Response(404, json={}))
    with pytest.raises(KbMcpError) as exc:
        await search_v2_handler({"id": str(uuid.uuid4()), "type": "STICKY"}, client=c_404)
    assert exc.value.code == McpErrorCode.NOT_FOUND

    # Doc not found
    with pytest.raises(KbMcpError) as exc:
        await search_v2_handler({"id": "docs/nonexistent"}, client=c_404)
    assert exc.value.code == McpErrorCode.NOT_FOUND

    # _read_sticky branches (LODs, promoted_to_doc_id, links failure)
    def stk_full_h(req: httpx.Request) -> httpx.Response:
        if "/links" in req.url.path:
            return httpx.Response(500, json={"error": "db err"})
        return httpx.Response(404)

    c_stk_links_err = _build_mock_client(stk_full_h)
    stk_d = {
        "id": "s-id-1",
        "color_token": "mint",
        "body_markdown": "# Note\nBody",
        "etag": "e",
        "promoted_to_doc_id": "doc-uuid-target",
    }
    r_stk_sum = await _read_sticky(stk_d, Lod.SUMMARY, c_stk_links_err, None)
    assert "body_markdown" not in r_stk_sum

    r_stk_std = await _read_sticky(stk_d, Lod.STANDARD, c_stk_links_err, None)
    assert "body_markdown" in r_stk_std

    r_stk_full = await _read_sticky(stk_d, Lod.FULL, c_stk_links_err, None)
    assert r_stk_full["promoted_to_doc_id"] == "doc-uuid-target"
    assert r_stk_full["links"] == []

    # _read_doc_or_page with parent_title and tree list
    def doc_full_h(req: httpx.Request) -> httpx.Response:
        p = req.url.path
        if "/tree" in p:
            return httpx.Response(200, json=[{"title": "Child"}])
        if "/links" in p:
            return httpx.Response(200, json=["non-dict"])
        return httpx.Response(404)

    c_doc_full = _build_mock_client(doc_full_h)
    doc_d = {
        "id": "d-id-1",
        "canonical_key": "docs/k",
        "title": "Title",
        "parent_title": "Parent",
        "body_markdown": "# H\nContent",
    }
    r_doc_full = await _read_doc_or_page(
        "doc",
        doc_d,
        "docs/k",
        Lod.FULL,
        include_tree=True,
        active_client=c_doc_full,
        active_token=None,
    )
    assert r_doc_full["breadcrumbs"] == ["Parent", "Title"]
    assert "tree" in r_doc_full
    assert r_doc_full["links"] == []

    # Hybrid search formatting (truncation, next_cursor, no key fallback, mode forwarding)
    captured_payloads: list[dict[str, Any]] = []

    def search_h(req: httpx.Request) -> httpx.Response:
        import json

        captured_payloads.append(json.loads(req.content.decode()))
        return httpx.Response(
            200,
            json={
                "total": 1,
                "executed_mode": "hybrid",
                "items": [
                    {
                        "kind": "doc",
                        "id": "hit-id-1",
                        "title": "Hit",
                        "snippet": "x" * 350,
                    }
                ],
                "next_cursor": "cur-next",
            },
        )

    c_srch = _build_mock_client(search_h)
    res_srch = await search_v2_handler(
        {"query": "q", "project": "P", "type": "ALL", "cursor": "c1"}, client=c_srch
    )
    assert res_srch["total"] == 1
    assert res_srch["items"][0]["key"] == "hit-id-1"
    assert len(res_srch["items"][0]["snippet"]) <= 300
    assert res_srch["next_cursor"] == "cur-next"
    assert res_srch["mode"] == "hybrid"
    assert res_srch["executed_mode"] == "hybrid"
    assert captured_payloads[-1]["mode"] == "hybrid"

    # Explicit mode="lexical"
    await search_v2_handler({"query": "q", "mode": "lexical"}, client=c_srch)
    assert captured_payloads[-1]["mode"] == "lexical"

    # Invalid mode validation error
    with pytest.raises(KbMcpError) as exc_mode:
        await search_v2_handler({"query": "q", "mode": "invalid"}, client=c_srch)
    assert exc_mode.value.code == McpErrorCode.VALIDATION_FAILED

    # Hybrid search non-dict response
    c_srch_nd = _build_mock_client(lambda r: httpx.Response(200, json="non-dict"))
    res_srch_nd = await search_v2_handler({"query": "q"}, client=c_srch_nd)
    assert res_srch_nd["total"] == 0

    # Project and workspace lists with non-dict items
    def list_nd_h(req: httpx.Request) -> httpx.Response:
        p = req.url.path
        if "/stickies" in p:
            return httpx.Response(
                200, json=["non-dict", {"id": "s", "color_token": "amber", "body_markdown": ""}]
            )
        if "/docs" in p:
            return httpx.Response(
                200, json=["non-dict", {"id": "d", "canonical_key": "docs/d", "title": "D"}]
            )
        if "/projects/" in p:
            return httpx.Response(200, json={"id": "proj-uuid-exh"})
        return httpx.Response(404)

    c_list_nd = _build_mock_client(list_nd_h)
    res_p_nd = await search_v2_handler({"project": "EXH", "type": "ALL"}, client=c_list_nd)
    assert len(res_p_nd["docs"]) == 1
    assert len(res_p_nd["stickies"]) == 1

    res_w_nd = await search_v2_handler({"type": "ALL"}, client=c_list_nd)
    assert len(res_w_nd["docs"]) == 1
    assert len(res_w_nd["stickies"]) == 1

    # Project list error fallback
    def list_err_h(req: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "fail"})

    c_list_err = _build_mock_client(list_err_h)
    res_p_err = await search_v2_handler(
        {"project": "EXH", "type": "DOC", "include_tree": True}, client=c_list_err
    )
    assert res_p_err["tree"] == []

    # _try_get_page_or_doc paths
    def resolve_paths_h(req: httpx.Request) -> httpx.Response:
        p = req.url.path
        if p == "/api/v1/pages/my-page":
            return httpx.Response(200, json={"id": "p-1"})
        if p == "/api/v1/pages/sub/p":
            return httpx.Response(200, json={"id": "sub-p"})
        if p == "/api/v1/docs/sub/d":
            return httpx.Response(200, json={"id": "sub-d"})
        if p == "/api/v1/docs/root-d":
            return httpx.Response(200, json={"id": "root-d"})
        if p == "/api/v1/pages/orphan-p":
            return httpx.Response(200, json={"id": "orphan-p"})
        return httpx.Response(404)

    c_rp = _build_mock_client(resolve_paths_h)
    assert await _try_get_page_or_doc(c_rp, "pages/my-page", None) == ("page", {"id": "p-1"})
    assert await _try_get_page_or_doc(c_rp, "sub/p", None) == ("page", {"id": "sub-p"})
    assert await _try_get_page_or_doc(c_rp, "docs/sub/d", None) == ("doc", {"id": "sub-d"})
    assert await _try_get_page_or_doc(c_rp, "root-d", None) == ("doc", {"id": "root-d"})
    assert await _try_get_page_or_doc(c_rp, "orphan-p", None) == ("page", {"id": "orphan-p"})
    assert await _try_get_page_or_doc(c_rp, "totally-missing", None) is None

    # _try_get_sticky with missing id and error
    c_stk_miss = _build_mock_client(lambda r: httpx.Response(200, json={}))
    assert await _try_get_sticky(c_stk_miss, str(uuid.uuid4()), None) is None
    c_stk_err_sticky = _build_mock_client(lambda r: httpx.Response(500, json={}))
    assert await _try_get_sticky(c_stk_err_sticky, str(uuid.uuid4()), None) is None

    # _read_sticky LOD FULL non-dict links
    c_links_nd = _build_mock_client(lambda r: httpx.Response(200, json=["non-dict"]))
    r_stk_nd = await _read_sticky(
        {"id": "s-nd", "color_token": "amber", "body_markdown": "x"},
        Lod.FULL,
        c_links_nd,
        None,
    )
    assert r_stk_nd["links"] == []

    # _read_doc_or_page standalone breadcrumbs & tree error fallback to outline
    r_doc_basic = await _read_doc_or_page(
        "doc",
        {"title": "Standalone", "id": "d-std"},
        "docs/std",
        Lod.FULL,
        include_tree=False,
        active_client=c_rp,
        active_token=None,
    )
    assert r_doc_basic["breadcrumbs"] == ["Standalone"]
    c_tree_err = _build_mock_client(lambda r: httpx.Response(500, json={}))
    r_doc_tree_err = await _read_doc_or_page(
        "doc",
        {"title": "T", "id": "d-1", "body_markdown": "# Sec 1\nBody"},
        "docs/t",
        Lod.STANDARD,
        include_tree=True,
        active_client=c_tree_err,
        active_token=None,
    )
    assert "outline" in r_doc_tree_err

    # Hybrid search extra branches (anchor without hash, non-dict item)
    def srch_extra_h(req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "total": 2,
                "items": [
                    "non-dict",
                    {
                        "kind": "page",
                        "id": "p-hit",
                        "anchor": "section-one",
                        "snippet": "short",
                    },
                ],
            },
        )

    c_srch_extra = _build_mock_client(srch_extra_h)
    res_extra = await search_v2_handler({"query": "q", "type": "ALL"}, client=c_srch_extra)
    assert res_extra["items"][0]["anchor"] == "#section-one"

    # Project docs list without tree (include_tree=False) and stickies list error
    def p_list_h(req: httpx.Request) -> httpx.Response:
        p = req.url.path
        if "/projects/PROJ" in p:
            return httpx.Response(200, json={"id": "0193457a-1111-7000-8000-000000000001"})
        if "/docs" in p:
            assert "project=0193457a-1111-7000-8000-000000000001" in str(req.url)
            return httpx.Response(
                200, json=[{"id": "d1", "canonical_key": "docs/d1", "title": "D1"}]
            )
        if "/stickies" in p:
            return httpx.Response(500, json={})
        return httpx.Response(404)

    c_plist = _build_mock_client(p_list_h)
    res_plist = await search_v2_handler(
        {"project": "PROJ", "type": "ALL", "include_tree": False}, client=c_plist
    )
    assert len(res_plist["docs"]) == 1
    assert res_plist["stickies"] == []

    # Project not found on include_tree=False raises NOT_FOUND
    c_p_404 = _build_mock_client(lambda r: httpx.Response(404, json={}))
    with pytest.raises(KbMcpError) as exc:
        await search_v2_handler(
            {"project": "UNKNOWN_PROJ", "type": "DOC", "include_tree": False}, client=c_p_404
        )
    assert exc.value.code == McpErrorCode.NOT_FOUND

    # Workspace list for type="DOC" and type="STICKY" with error handling
    def w_list_err_h(req: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={})

    c_wlist_err = _build_mock_client(w_list_err_h)
    res_w_doc_err = await search_v2_handler({"type": "DOC"}, client=c_wlist_err)
    assert res_w_doc_err["docs"] == []
    res_w_stk_err = await search_v2_handler({"type": "STICKY"}, client=c_wlist_err)
    assert res_w_stk_err["stickies"] == []

    # ToolSpec builder for search
    t_srch = create_docs_search_tool(client=c_list_nd)
    assert "mode" in t_srch.input_schema["properties"]
    assert t_srch.input_schema["properties"]["mode"]["enum"] == ["lexical", "hybrid"]
    assert t_srch.input_schema["properties"]["mode"]["default"] == "hybrid"
    res_t_srch = await t_srch.handler({"id": "help"})
    assert res_t_srch["tool"] == "search"


@pytest.mark.asyncio
async def test_update_v2_unit_coverage() -> None:
    # Parse link targets
    t, lt = parse_update_link("VERIFIED_BY_DOC:XYZ")
    assert t == "XYZ" and lt == "VERIFIED_BY_DOC"

    # _resolve_parent_ids
    def parent_h(req: httpx.Request) -> httpx.Response:
        p = req.url.path
        if p.startswith("/api/v1/pages/my-page"):
            return httpx.Response(200, json={"id": "page-id-99", "doc_id": "doc-id-88"})
        if p.startswith("/api/v1/docs/my-doc"):
            return httpx.Response(200, json={"id": "doc-id-77"})
        return httpx.Response(404)

    c_par = _build_mock_client(parent_h)
    d_uuid = str(uuid.uuid4())
    res_u_doc, res_u_page = await _resolve_parent_ids(c_par, d_uuid, None)
    assert res_u_doc == d_uuid and res_u_page is None

    res_p_doc, res_p_page = await _resolve_parent_ids(c_par, "my-page", None)
    assert res_p_doc == "doc-id-88" and res_p_page == "page-id-99"

    res_d_doc, res_d_page = await _resolve_parent_ids(c_par, "docs/my-doc", None)
    assert res_d_doc == "doc-id-77" and res_d_page is None

    with pytest.raises(KbMcpError) as exc:
        await _resolve_parent_ids(c_par, "missing", None)
    assert exc.value.code == McpErrorCode.NOT_FOUND

    # _fetch_current_entity
    def fetch_h(req: httpx.Request) -> httpx.Response:
        p = req.url.path
        if p.startswith("/api/v1/pages/p1"):
            return httpx.Response(200, json={"id": "p-1", "canonical_key": "pages/p1"})
        if p.startswith("/api/v1/docs/d1"):
            return httpx.Response(200, json={"id": "d-1", "canonical_key": "docs/d1"})
        return httpx.Response(404)

    c_fetch = _build_mock_client(fetch_h)
    kp, dp = await _fetch_current_entity(c_fetch, "pages/p1", None)
    assert kp == "page" and dp["id"] == "p-1"

    kd, dd = await _fetch_current_entity(c_fetch, "docs/d1", None)
    assert kd == "doc" and dd["id"] == "d-1"

    with pytest.raises(KbMcpError) as exc:
        await _fetch_current_entity(c_fetch, "missing", None)
    assert exc.value.code == McpErrorCode.NOT_FOUND

    # _find_closest_matches and _find_line_hints
    assert _find_closest_matches("", "target") == []
    assert _find_line_hints("line 1\ntarget\nline 3\ntarget", "target") == [2, 4]

    # _diff_patch_content ETag mismatch
    with pytest.raises(KbMcpError) as exc:
        _diff_patch_content("body", "orig", "rep", "sha1", "sha2")
    assert exc.value.code == McpErrorCode.CONFLICT_ETAG

    # _sync_inline_links
    def sync_h(req: httpx.Request) -> httpx.Response:
        p = req.url.path
        if req.method == "GET" and "/links" in p:
            return httpx.Response(
                200,
                json={
                    "outbound": [
                        {
                            "id": "link-1",
                            "type": "RELATES_TO",
                            "target": {"key": "T1", "id": "uuid-1"},
                        }
                    ]
                },
            )
        if req.method == "POST" and "/links" in p:
            return httpx.Response(201, json={"status": "ok"})
        if req.method == "DELETE" and "/links/" in p:
            return httpx.Response(204)
        return httpx.Response(404)

    c_sync = _build_mock_client(sync_h)
    ops = await sync_update_links(
        c_sync,
        "src-id",
        ["+T2", "-T1", "-NONEXISTENT", {"action": "add", "target": "T3"}],
        None,
    )
    assert any(o["action"] == "added" for o in ops)
    assert any(o["action"] == "removed" for o in ops)

    # Validations: client none, missing id, long title, bad color
    c_dummy = _build_mock_client(lambda r: httpx.Response(200, json={}))
    with pytest.raises(KbMcpError) as exc:
        await update_v2_handler({"id": "some-id"}, client=None)
    assert exc.value.code == McpErrorCode.UPSTREAM_UNAVAILABLE

    with pytest.raises(KbMcpError) as exc:
        await update_v2_handler({}, client=c_dummy)
    assert exc.value.code == McpErrorCode.VALIDATION_FAILED

    with pytest.raises(KbMcpError) as exc:
        await update_v2_handler({"id": "x", "title": "x" * 201}, client=c_dummy)
    assert exc.value.code == McpErrorCode.VALIDATION_FAILED

    with pytest.raises(KbMcpError) as exc:
        await update_v2_handler({"id": "x", "color": "bad"}, client=c_dummy)
    assert exc.value.code == McpErrorCode.VALIDATION_FAILED

    # Sticky ETag conflicts
    def stk_etag_h(req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"id": "s-1", "etag": "fresh", "body_sha256": "fresh", "color_token": "amber"}
        )

    c_stk_etag = _build_mock_client(stk_etag_h)
    with pytest.raises(KbMcpError) as exc:
        await update_v2_handler(
            {"id": str(uuid.uuid4()), "type": "DOC", "if_match": "stale"}, client=c_stk_etag
        )
    assert exc.value.code == McpErrorCode.CONFLICT_ETAG

    with pytest.raises(KbMcpError) as exc:
        await update_v2_handler(
            {"id": str(uuid.uuid4()), "content": "c", "if_match": "stale"}, client=c_stk_etag
        )
    assert exc.value.code == McpErrorCode.CONFLICT_ETAG

    # Doc update ETag conflict
    def doc_etag_h(req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "id": "d-1",
                "canonical_key": "docs/d",
                "etag": "fresh",
                "body_sha256": "fresh",
            },
        )

    c_doc_etag = _build_mock_client(doc_etag_h)
    with pytest.raises(KbMcpError) as exc:
        await update_v2_handler(
            {"id": "docs/d", "content": "c", "if_match": "stale"}, client=c_doc_etag
        )
    assert exc.value.code == McpErrorCode.CONFLICT_ETAG

    # Sticky promotion and update upstream errors
    def stk_err_h(req: httpx.Request) -> httpx.Response:
        if req.method == "GET":
            return httpx.Response(200, json={"id": "s-1", "etag": "e"})
        return httpx.Response(200, json=["non-dict"])

    c_stk_err = _build_mock_client(stk_err_h)
    with pytest.raises(KbMcpError) as exc:
        await update_v2_handler({"id": str(uuid.uuid4()), "type": "DOC"}, client=c_stk_err)
    assert exc.value.code == McpErrorCode.UPSTREAM_ERROR

    with pytest.raises(KbMcpError) as exc:
        await update_v2_handler({"id": str(uuid.uuid4()), "color": "sky"}, client=c_stk_err)
    assert exc.value.code == McpErrorCode.UPSTREAM_ERROR

    # Promotion with parent page and links
    def prom_full_h(req: httpx.Request) -> httpx.Response:
        p = req.url.path
        if req.method == "GET" and "/stickies/" in p:
            return httpx.Response(200, json={"id": "s-1", "etag": "sha-f", "body_sha256": "sha-f"})
        if req.method == "GET" and p.startswith("/api/v1/pages/mp"):
            return httpx.Response(200, json={"id": "p-99", "doc_id": "d-99"})
        if req.method == "POST" and "/promote-to-doc" in p:
            return httpx.Response(
                200,
                json={"promoted_to_doc": {"id": "d-99", "canonical_key": "docs/p", "title": "P"}},
            )
        if req.method == "POST" and "/links" in p:
            return httpx.Response(201, json={"status": "ok"})
        return httpx.Response(404)

    c_prom_f = _build_mock_client(prom_full_h)
    res_prom_f = await update_v2_handler(
        {
            "id": str(uuid.uuid4()),
            "type": "DOC",
            "parent": "mp",
            "content": "# Body",
            "title": "Prom",
            "if_match": "sha-f",
            "links": ["T1"],
        },
        client=c_prom_f,
    )
    assert res_prom_f["status"] == "promoted"

    # Sticky already promoted via promoted_to_doc_id
    c_already = _build_mock_client(
        lambda r: httpx.Response(
            200, json={"id": "s-1", "promoted_to_doc_id": "doc-target", "etag": "e"}
        )
    )
    with pytest.raises(KbMcpError) as exc:
        await update_v2_handler({"id": str(uuid.uuid4()), "type": "DOC"}, client=c_already)
    assert exc.value.code == McpErrorCode.ALREADY_PROMOTED

    # Page update (starts with pages/)
    def page_patch_h(req: httpx.Request) -> httpx.Response:
        p = req.url.path
        if req.method == "GET":
            return httpx.Response(
                200,
                json={
                    "id": "p-5",
                    "canonical_key": "pages/p5",
                    "etag": "e5",
                    "body_markdown": "orig",
                },
            )
        if req.method == "PATCH":
            return httpx.Response(
                200, json={"id": "p-5", "canonical_key": "pages/p5", "etag": "e6", "version_seq": 2}
            )
        return httpx.Response(404)

    c_pp = _build_mock_client(page_patch_h)
    res_pp = await update_v2_handler(
        {"id": "pages/p5", "original_text": "orig", "replacement_text": "rep"}, client=c_pp
    )
    assert res_pp["status"] == "updated" and res_pp["kind"] == "page"

    # Doc update with if_match
    def doc_im_h(req: httpx.Request) -> httpx.Response:
        if req.method == "GET":
            return httpx.Response(
                200,
                json={
                    "id": "d-im",
                    "canonical_key": "docs/im",
                    "etag": "im-e",
                    "body_markdown": "a",
                },
            )
        if req.method == "PATCH":
            assert req.headers.get("if-match") == '"im-e"'
            return httpx.Response(
                200, json={"id": "d-im", "canonical_key": "docs/im", "version_seq": 2}
            )
        return httpx.Response(404)

    c_im = _build_mock_client(doc_im_h)
    res_im = await update_v2_handler(
        {"id": "docs/im", "content": "new", "if_match": "im-e"}, client=c_im
    )
    assert res_im["status"] == "updated"

    # Extra update coverage: parent fallback missing fields, closest matches deduplication, links delete error
    def par_miss_h(req: httpx.Request) -> httpx.Response:
        p = req.url.path
        if p == "/api/v1/pages/some-page":
            return httpx.Response(200, json={"id": "p-noid"})  # no doc_id
        if p == "/api/v1/pages/no-page-id":
            return httpx.Response(200, json={})  # page dict without id -> falls through to doc
        if p == "/api/v1/docs/no-page-id":
            return httpx.Response(200, json={"id": "doc-fallback-id"})
        if p == "/api/v1/docs/missing-id":
            return httpx.Response(200, json={})  # doc dict without id
        return httpx.Response(404)

    c_pm = _build_mock_client(par_miss_h)
    d_id, p_id = await _resolve_parent_ids(c_pm, "some-page", None)
    assert d_id is None and p_id == "p-noid"
    d_id_fb, p_id_fb = await _resolve_parent_ids(c_pm, "no-page-id", None)
    assert d_id_fb == "doc-fallback-id" and p_id_fb is None
    with pytest.raises(KbMcpError) as exc:
        await _resolve_parent_ids(c_pm, "missing-id", None)
    assert exc.value.code == McpErrorCode.NOT_FOUND

    # _fetch_current_entity fallbacks
    def fetch_fall_h(req: httpx.Request) -> httpx.Response:
        p = req.url.path
        if p == "/api/v1/pages/docs/fb":
            return httpx.Response(404)
        if p == "/api/v1/docs/fb":
            return httpx.Response(200, json={"id": "fb-doc", "canonical_key": "docs/fb"})
        if p == "/api/v1/docs/orphan-fb":
            return httpx.Response(404)
        if p == "/api/v1/pages/orphan-fb":
            return httpx.Response(200, json={"id": "fb-page", "canonical_key": "pages/orphan-fb"})
        return httpx.Response(404)

    c_ff = _build_mock_client(fetch_fall_h)
    k_fb, d_fb = await _fetch_current_entity(c_ff, "docs/fb", None)
    assert k_fb == "doc" and d_fb["id"] == "fb-doc"
    k_ofb, d_ofb = await _fetch_current_entity(c_ff, "orphan-fb", None)
    assert k_ofb == "page" and d_ofb["id"] == "fb-page"

    # _try_get_sticky error (both search and update variants)
    c_stk_500 = _build_mock_client(lambda r: httpx.Response(500, json={}))
    assert await _try_get_sticky(c_stk_500, str(uuid.uuid4()), None) is None
    assert await _try_get_sticky_update(c_stk_500, str(uuid.uuid4()), None) is None

    # Closest matches seen_starts deduplication
    assert (
        len(_find_closest_matches("hello world\nhello world\nhello world", "hello world", top_n=2))
        <= 2
    )

    # sync_update_links with plain string, dict with link_type, and delete error
    def sync_del_err_h(req: httpx.Request) -> httpx.Response:
        if req.method == "GET":
            return httpx.Response(
                200,
                json={
                    "outbound": [
                        {
                            "id": "link-del",
                            "type": "RELATES_TO",
                            "target": {"key": "T-DEL", "id": "uuid-del"},
                        }
                    ]
                },
            )
        if req.method == "POST":
            return httpx.Response(500, json={"error": "fail add"})
        if req.method == "DELETE":
            return httpx.Response(500, json={"error": "fail del"})
        return httpx.Response(404)

    c_sde = _build_mock_client(sync_del_err_h)
    ops_sde = await sync_update_links(
        c_sde,
        "src-1",
        [
            "ARCH-PLAIN",
            "+ARCH-PLUS",
            "-T-DEL",
            {"action": "add", "target": "FAIL-ADD", "link_type": "VERIFIED_BY_DOC"},
            "",
        ],
        None,
    )
    assert any(o.get("action") == "failed" for o in ops_sde)

    # Doc update without diff patch and no ETag in entity
    def doc_no_etag_h(req: httpx.Request) -> httpx.Response:
        if req.method == "GET":
            return httpx.Response(
                200, json={"id": "d-no-e", "canonical_key": "docs/noe", "body_markdown": "x"}
            )
        if req.method == "PATCH":
            return httpx.Response(200, json=["non-dict"])
        return httpx.Response(404)

    c_dne = _build_mock_client(doc_no_etag_h)
    res_dne = await update_v2_handler({"id": "docs/noe", "title": "New Title"}, client=c_dne)
    assert res_dne["status"] == "updated"

    # ToolSpec builder for update
    t_up = create_docs_update_tool(client=c_im)
    res_t_up = await t_up.handler({"id": "docs/im", "title": "T"})
    assert res_t_up["status"] == "updated"

    # Nested page path resolution (clean_id.count("/") >= 2)
    def nested_h(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/api/v1/pages/docs/d1/p1":
            return httpx.Response(200, json={"id": "p-nested", "canonical_key": "pages/docs/d1/p1"})
        return httpx.Response(404)

    c_nested = _build_mock_client(nested_h)
    k_nest, d_nest = await _fetch_current_entity(c_nested, "docs/d1/p1", None)
    assert k_nest == "page" and d_nest["id"] == "p-nested"

    # Sticky patch color and unquoted ETag with If-Match quotes
    def stk_patch_h(req: httpx.Request) -> httpx.Response:
        p = req.url.path
        if req.method == "GET" and "/stickies/" in p:
            return httpx.Response(
                200, json={"id": "s-col", "color_token": "amber", "etag": "sha-c"}
            )
        if req.method == "PATCH" and "/stickies/" in p:
            assert req.headers.get("if-match") == '"sha-c"'
            return httpx.Response(
                200, json={"id": "s-col", "color_token": "sky", "etag": "sha-new"}
            )
        return httpx.Response(404)

    c_stk_patch = _build_mock_client(stk_patch_h)
    res_stk_patch = await update_v2_handler(
        {"id": str(uuid.uuid4()), "color": "sky", "if_match": '"sha-c"'},
        client=c_stk_patch,
    )
    assert res_stk_patch["status"] == "updated"
    assert res_stk_patch["color"] == "sky"

    # Sticky update with title without type="DOC" raises VALIDATION_FAILED
    with pytest.raises(KbMcpError) as exc_stk_title:
        await update_v2_handler(
            {"id": str(uuid.uuid4()), "title": "Forbidden Sticky Title"},
            client=c_stk_patch,
        )
    assert exc_stk_title.value.code == McpErrorCode.VALIDATION_FAILED

    # Half-supplied diff patch raises VALIDATION_FAILED
    with pytest.raises(KbMcpError) as exc_half_orig:
        await update_v2_handler({"id": "docs/im", "original_text": "a"}, client=c_im)
    assert exc_half_orig.value.code == McpErrorCode.VALIDATION_FAILED

    with pytest.raises(KbMcpError) as exc_half_rep:
        await update_v2_handler({"id": "docs/im", "replacement_text": "b"}, client=c_im)
    assert exc_half_rep.value.code == McpErrorCode.VALIDATION_FAILED

    # sync_update_links with dict format {"add": [...], "remove": [...]}
    ops_dict = await sync_update_links(c_sync, "src-id", {"add": ["T4"], "remove": ["T1"]}, None)
    assert any(o["action"] == "added" for o in ops_dict)
    assert any(o["action"] == "removed" for o in ops_dict)

    # Additional _fetch_current_entity branch tests
    def fetch_branches_h(req: httpx.Request) -> httpx.Response:
        p = req.url.path
        if p == "/api/v1/pages/fail-pages":
            return httpx.Response(500, json={})
        if p == "/api/v1/pages/fail/nested/path":
            return httpx.Response(500, json={})
        if p == "/api/v1/docs/fail-doc-fb":
            return httpx.Response(500, json={})
        if p == "/api/v1/pages/docs/fail-doc-fb":
            return httpx.Response(
                200, json={"id": "page-recovered", "canonical_key": "pages/docs/fail-doc-fb"}
            )
        return httpx.Response(404)

    c_fb_branches = _build_mock_client(fetch_branches_h)
    # 1. clean_id.startswith("pages/") that fails upstream
    with pytest.raises(KbMcpError) as exc_fb1:
        await _fetch_current_entity(c_fb_branches, "pages/fail-pages", None)
    assert exc_fb1.value.code == McpErrorCode.NOT_FOUND

    # 2. clean_id.count("/") >= 2 that fails upstream
    with pytest.raises(KbMcpError) as exc_fb2:
        await _fetch_current_entity(c_fb_branches, "fail/nested/path", None)
    assert exc_fb2.value.code == McpErrorCode.NOT_FOUND

    # 3. clean_id.startswith("docs/") where doc fails but page succeeds
    k_rec, d_rec = await _fetch_current_entity(c_fb_branches, "docs/fail-doc-fb", None)
    assert k_rec == "page" and d_rec["id"] == "page-recovered"

    # Sticky promotion without current_sha (body_sha256/etag absent)
    def prom_nosha_h(req: httpx.Request) -> httpx.Response:
        p = req.url.path
        if req.method == "GET" and "/stickies/" in p:
            return httpx.Response(200, json={"id": "s-nosha"})
        if req.method == "POST" and "/promote-to-doc" in p:
            assert "expected_sticky_sha256" not in req.headers
            return httpx.Response(
                200, json={"promoted_to_doc": {"id": "d-nosha", "canonical_key": "docs/nosha"}}
            )
        return httpx.Response(404)

    c_nosha = _build_mock_client(prom_nosha_h)
    res_nosha = await update_v2_handler({"id": str(uuid.uuid4()), "type": "DOC"}, client=c_nosha)
    assert res_nosha["status"] == "promoted"

    # MODE 4: List Project / Workspace Knowledge
    def list_h(req: httpx.Request) -> httpx.Response:
        p = req.url.path
        if "/api/v1/docs" in p:
            return httpx.Response(
                200,
                json=[{"id": str(uuid.uuid4()), "canonical_key": "docs/test", "title": "Test Doc"}],
            )
        if "/stickies" in p:
            return httpx.Response(
                200,
                json=[
                    {"id": str(uuid.uuid4()), "color_token": "blue", "body_markdown": "Note body"}
                ],
            )
        if "/projects/" in p:
            return httpx.Response(404, json={})
        return httpx.Response(200, json=[])

    c_list = _build_mock_client(list_h)
    u_proj = str(uuid.uuid4())
    res_list = await search_v2_handler(
        {"project": u_proj, "target_type": "ALL", "include_tree": False}, client=c_list
    )
    assert "docs" in res_list
    assert "stickies" in res_list

    # Nonexistent named project raises NOT_FOUND
    with pytest.raises(KbMcpError) as exc_pnotfound:
        await search_v2_handler(
            {"project": "MISSING_PROJ", "target_type": "DOC", "include_tree": False}, client=c_list
        )
    assert exc_pnotfound.value.code == McpErrorCode.NOT_FOUND

    # Workspace-level list (no project)
    res_ws = await search_v2_handler({"target_type": "ALL"}, client=c_list)
    assert "docs" in res_ws

    # Project response as dict without "id" triggers McpErrorCode.NOT_FOUND in MODE 4
    def noid_proj_h(req: httpx.Request) -> httpx.Response:
        p = req.url.path
        if "/projects/noid-proj" in p:
            return httpx.Response(200, json={"some_field": "no id key"})
        return httpx.Response(404, json={})

    c_noid = _build_mock_client(noid_proj_h)
    with pytest.raises(KbMcpError) as exc_noid:
        await search_v2_handler(
            {"project": "noid-proj", "target_type": "DOC", "include_tree": False}, client=c_noid
        )
    assert exc_noid.value.code == McpErrorCode.NOT_FOUND
