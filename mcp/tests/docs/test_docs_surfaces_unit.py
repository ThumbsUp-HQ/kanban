# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
# ruff: noqa: E501, PLR0915, D103, ANN401, ARG001, ARG005, PLC0415, F841, C901
"""Unit tests targeting 100% branch and line coverage for mcp/surfaces/docs (KANBA-127)."""

from __future__ import annotations

import json
import uuid
from typing import Any

import httpx
import pytest

from mcp.errors import KbMcpError, McpErrorCode
from mcp.internal_client import KanbanApiClient
from mcp.settings import McpSettings
from mcp.surfaces.docs.link_knowledge import link_knowledge_handler
from mcp.surfaces.docs.manage_stickies import manage_stickies_handler
from mcp.surfaces.docs.promote_sticky_to_doc import promote_sticky_to_doc_handler
from mcp.surfaces.docs.read_doc import read_doc_handler
from mcp.surfaces.docs.search_knowledge import search_knowledge_handler
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
