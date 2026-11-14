# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Integration test suite for full-text and trigram lexical search API (KB-P3-17)."""

from __future__ import annotations

import base64
import json
import urllib.parse
import uuid
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import text

from kanban.api.problems import ProblemException
from kanban.services.search import _get_signing_key, decode_search_cursor, validate_limit
from kanban.tests.security.helpers import rebuild_era

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    import httpx
    from sqlalchemy.ext.asyncio import AsyncSession

    from kanban.tests.api.conftest import ApiEnv, SeededUser
    from kanban.tests.contract import ContractRecorder

pytestmark = pytest.mark.committed_db


async def _seed_test_issue(  # noqa: PLR0913, PLR0917
    session: AsyncSession,
    ws_id: uuid.UUID,
    proj_id: uuid.UUID,
    identifier: str,
    seq: int,
    summary: str,
    description: str,
    user_id: uuid.UUID,
    state_id: uuid.UUID,
    priority_id: uuid.UUID,
    board_rank: str = "a0",
) -> uuid.UUID:
    """Seed an issue with sequence allocation and object registration."""
    await session.execute(
        text(
            "UPDATE projects SET issue_seq_counter = GREATEST(issue_seq_counter, :seq) "
            "WHERE id = :p"
        ),
        {"p": proj_id, "seq": seq},
    )
    iss_id = uuid.uuid4()
    await session.execute(
        text("SELECT register_object('issue'::object_kind, :ws, :proj, :ckey, :title, :cr, :id)"),
        {
            "ws": ws_id,
            "proj": proj_id,
            "ckey": f"{identifier}-{seq}",
            "title": summary,
            "cr": user_id,
            "id": iss_id,
        },
    )
    await session.execute(
        text(
            "INSERT INTO issues (id, object_type, workspace_id, project_id, sequence_id, summary, "
            "description_markdown, state_id, priority_id, created_by_id, original_created_by_id, "
            "board_rank, ancestry_path) "
            "VALUES (:id, 'issue', :ws, :proj, :seq, :summary, :desc, :st, :pri, :cr, :cr, "
            ":rnk, 'top')"
        ),
        {
            "id": iss_id,
            "ws": ws_id,
            "proj": proj_id,
            "seq": seq,
            "summary": summary,
            "desc": description,
            "st": state_id,
            "pri": priority_id,
            "cr": user_id,
            "rnk": board_rank,
        },
    )
    return iss_id


async def test_case_1_positive_cross_entity_ranking_and_key_boost(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
    contract_recorder: ContractRecorder,
) -> None:
    """Case 1: Positive cross-entity ranking, issue key boost, and typo matches."""
    admin = await make_user("admin1", workspace_role="WORKSPACE_ADMIN")
    proj_id = await make_project("KAN", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    client = as_principal(admin)
    ws_id = api_env.workspace_id

    # Get state and priority
    state_row = (
        await api_env.seed.execute(
            text("SELECT id FROM workflow_states WHERE project_id = :p LIMIT 1"), {"p": proj_id}
        )
    ).scalar_one()
    pri_row = (
        await api_env.seed.execute(
            text("SELECT id FROM project_priorities WHERE project_id = :p LIMIT 1"), {"p": proj_id}
        )
    ).scalar_one()

    # Seed issues: KAN-142 and KAN-150

    issue_142 = await _seed_test_issue(
        api_env.seed,
        ws_id,
        proj_id,
        "KAN",
        142,
        "Harden OIDC authentication with PKCE",
        "All OAuth 2.1 client flows must implement PKCE S256 verification.",
        admin.id,
        state_row,
        pri_row,
        "a000142",
    )
    await _seed_test_issue(
        api_env.seed,
        ws_id,
        proj_id,
        "KAN",
        150,
        "Fix database query engine",
        "Refactor query engine filter predicate compilation.",
        admin.id,
        state_row,
        pri_row,
        "a000150",
    )

    # Seed Doc with ## PKCE (S256) heading
    doc_id = uuid.uuid4()
    await api_env.seed.execute(
        text("SELECT register_object('doc'::object_kind, :ws, :proj, :ckey, :title, :cr, :id)"),
        {
            "ws": ws_id,
            "proj": proj_id,
            "ckey": "docs/arch/auth-studio",
            "title": "Auth Studio Architecture",
            "cr": admin.id,
            "id": doc_id,
        },
    )
    doc_body = (
        "# Auth Studio\n"
        "Overview of the authentication studio subsystem.\n\n"
        "## PKCE (S256)\n"
        "Detailed protocol specifications for PKCE with S256 challenge.\n"
    )
    await api_env.seed.execute(
        text(
            "INSERT INTO docs (id, object_type, workspace_id, project_id, title, "
            "body_markdown, hierarchy_path) "
            "VALUES (:id, 'doc', :ws, :proj, :title, :body, 'top')"
        ),
        {
            "id": doc_id,
            "ws": ws_id,
            "proj": proj_id,
            "title": "Auth Studio Architecture",
            "body": doc_body,
        },
    )

    # Seed Sticky note with typo target
    sticky_id = uuid.uuid4()
    await api_env.seed.execute(
        text(
            "SELECT register_object('sticky'::object_kind, :ws, :proj, :ckey, 'Sticky Note', "
            ":cr, :id)"
        ),
        {
            "ws": ws_id,
            "proj": proj_id,
            "ckey": f"KAN/stickies/{sticky_id}",
            "cr": admin.id,
            "id": sticky_id,
        },
    )
    await api_env.seed.execute(
        text(
            "INSERT INTO stickies (id, object_type, workspace_id, project_id, "
            "body_markdown, color_token) "
            "VALUES (:id, 'sticky', :ws, :proj, :body, 'amber')"
        ),
        {
            "id": sticky_id,
            "ws": ws_id,
            "proj": proj_id,
            "body": "Remember to audit Authenitcation procedures across all login cards.",
        },
    )

    await rebuild_era(api_env.seed, ws_id)
    await api_env.seed.commit()

    # 1. Exact issue key boost: GET /api/v1/search?q=KAN-142
    resp_key = await client.get("/api/v1/search?q=KAN-142")
    assert resp_key.status_code == 200
    data_key = resp_key.json()
    assert data_key["total"] >= 1
    assert data_key["items"][0]["key"] == "KAN-142"
    assert data_key["items"][0]["score"] == 100.0
    contract_recorder.record("unified_search_key_boost_200", resp_key.request, resp_key)

    # Lowercase issue key prefix test: kan-142
    resp_lower = await client.get("/api/v1/search?q=kan-142")
    assert resp_lower.status_code == 200
    assert resp_lower.json()["items"][0]["key"] == "KAN-142"

    # 2. Knowledge search for PKCE returns anchor #pkce-s256 and len <= 300
    resp_know = await client.post(
        "/api/v1/search/knowledge",
        json={"query": "PKCE", "kinds": ["doc", "page", "sticky"]},
    )
    assert resp_know.status_code == 200
    data_know = resp_know.json()
    assert data_know["total"] >= 1
    anchored_item = next(
        (it for it in data_know["items"] if it["anchor"] == "#pkce-s256"),
        None,
    )
    assert anchored_item is not None
    assert len(anchored_item["snippet"]) <= 300
    contract_recorder.record("knowledge_search_anchor_200", resp_know.request, resp_know)

    # 3. Typo matching via pg_trgm
    resp_typo = await client.get("/api/v1/search?q=Authenitcation")
    assert resp_typo.status_code == 200
    data_typo = resp_typo.json()
    assert data_typo["total"] >= 1
    matched_ids = {it["id"] for it in data_typo["items"]}
    assert str(issue_142) in matched_ids or str(sticky_id) in matched_ids


async def test_case_2_structured_filter_composition(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
    contract_recorder: ContractRecorder,
) -> None:
    """Case 2: Structured filter composition (POST /api/v1/search/issues with FilterSpec)."""
    admin = await make_user("admin2", workspace_role="WORKSPACE_ADMIN")
    member = await make_user("member2")
    proj_id = await make_project(
        "FLT", created_by=admin, roles={admin: "PROJECT_ADMIN", member: "MEMBER"}
    )
    client_admin = as_principal(admin)
    ws_id = api_env.workspace_id

    # Retrieve distinct workflow states: unstarted and started
    st_started = (
        await api_env.seed.execute(
            text(
                "SELECT id FROM workflow_states "
                "WHERE project_id = :p AND state_group = 'started' LIMIT 1"
            ),
            {"p": proj_id},
        )
    ).scalar_one()
    st_backlog = (
        await api_env.seed.execute(
            text(
                "SELECT id FROM workflow_states "
                "WHERE project_id = :p AND state_group = 'unstarted' LIMIT 1"
            ),
            {"p": proj_id},
        )
    ).scalar_one()
    pri_row = (
        await api_env.seed.execute(
            text("SELECT id FROM project_priorities WHERE project_id = :p LIMIT 1"), {"p": proj_id}
        )
    ).scalar_one()

    # Issue 1: "OIDC implementation" in started state, assigned to admin
    iss_started = await _seed_test_issue(
        api_env.seed,
        ws_id,
        proj_id,
        "FLT",
        1,
        "OIDC implementation",
        "Implement OIDC authentication protocol.",
        admin.id,
        st_started,
        pri_row,
        "a000001",
    )
    await api_env.seed.execute(
        text("INSERT INTO issue_assignees (issue_id, principal_id) VALUES (:iss, :user)"),
        {"iss": iss_started, "user": admin.id},
    )

    # Issue 2: "OIDC documentation" in backlog state, unassigned
    await _seed_test_issue(
        api_env.seed,
        ws_id,
        proj_id,
        "FLT",
        2,
        "OIDC documentation",
        "Document OIDC configuration parameters.",
        admin.id,
        st_backlog,
        pri_row,
        "a000002",
    )

    # Issue 3: "OIDC testing" in started state, assigned to member
    iss_member = await _seed_test_issue(
        api_env.seed,
        ws_id,
        proj_id,
        "FLT",
        3,
        "OIDC testing",
        "Write tests for OIDC flows.",
        admin.id,
        st_started,
        pri_row,
        "a000003",
    )
    await api_env.seed.execute(
        text("INSERT INTO issue_assignees (issue_id, principal_id) VALUES (:iss, :user)"),
        {"iss": iss_member, "user": member.id},
    )

    await rebuild_era(api_env.seed, ws_id)
    await api_env.seed.commit()

    # Search with FilterSpec: state_groups=["started"], assignee_ids=["me"]
    # Should match ONLY iss_started (matching OIDC, started group, assigned to admin)
    payload = {
        "query": "OIDC",
        "project": "FLT",
        "filters": {
            "state_groups": ["started"],
            "assignee_ids": ["me"],
        },
        "mode": "lexical",
        "limit": 20,
    }
    resp = await client_admin.post("/api/v1/search/issues", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert len(data["items"]) == 1
    assert data["items"][0]["id"] == str(iss_started)
    assert data["items"][0]["key"] == "FLT-1"
    contract_recorder.record("search_issues_with_filters_200", resp.request, resp)


async def test_case_3_rls_and_zero_side_channel_security(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
    contract_recorder: ContractRecorder,
) -> None:
    """Case 3: RLS isolation and equalized 404 responses for unreadable projects."""
    admin = await make_user("admin3", workspace_role="WORKSPACE_ADMIN")
    bob = await make_user("bob3")
    ws_id = api_env.workspace_id

    # Create restricted project SEC only accessible by admin
    sec_id = await make_project("SEC", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    # Create public project PUB accessible by Bob
    await make_project("PUB", created_by=admin, roles={admin: "PROJECT_ADMIN", bob: "MEMBER"})

    sec_state = (
        await api_env.seed.execute(
            text("SELECT id FROM workflow_states WHERE project_id = :p LIMIT 1"), {"p": sec_id}
        )
    ).scalar_one()
    sec_pri = (
        await api_env.seed.execute(
            text("SELECT id FROM project_priorities WHERE project_id = :p LIMIT 1"), {"p": sec_id}
        )
    ).scalar_one()

    # Seed canary object ULTRASECRET-991 in restricted project SEC
    await _seed_test_issue(
        api_env.seed,
        ws_id,
        sec_id,
        "SEC",
        991,
        "ULTRASECRET-991 Confidential security blueprint",
        "Canary text for secret security auditing.",
        admin.id,
        sec_state,
        sec_pri,
        "a000991",
    )

    await rebuild_era(api_env.seed, ws_id)
    await api_env.seed.commit()

    # Switch to Bob who has zero access to SEC
    client_bob = as_principal(bob)

    # 1. Unified search returns total 0
    resp_u = await client_bob.get("/api/v1/search?q=ULTRASECRET-991")
    assert resp_u.status_code == 200
    assert resp_u.json()["total"] == 0
    assert resp_u.json()["items"] == []

    # 2. Issues search returns total 0
    resp_i = await client_bob.post("/api/v1/search/issues", json={"query": "ULTRASECRET-991"})
    assert resp_i.status_code == 200
    assert resp_i.json()["total"] == 0
    assert resp_i.json()["items"] == []

    # 3. Knowledge search returns total 0
    resp_k = await client_bob.post("/api/v1/search/knowledge", json={"query": "ULTRASECRET-991"})
    assert resp_k.status_code == 200
    assert resp_k.json()["total"] == 0
    assert resp_k.json()["items"] == []
    contract_recorder.record("search_rls_zero_leak_200", resp_u.request, resp_u)

    # 4. Scope filtering on unreadable project returns equalized 404
    resp_unreadable = await client_bob.get("/api/v1/search?q=test&project=SEC")
    resp_nonexistent = await client_bob.get("/api/v1/search?q=test&project=NOPE")
    assert resp_unreadable.status_code == 404
    assert resp_nonexistent.status_code == 404
    body_u = resp_unreadable.json()
    body_n = resp_nonexistent.json()
    assert body_u["code"] == body_n["code"] == "NOT_FOUND"
    assert body_u["status"] == body_n["status"] == 404
    assert body_u["title"] == body_n["title"] == "Not Found"
    assert body_u["type"] == body_n["type"]
    contract_recorder.record(
        "search_unreadable_project_404", resp_unreadable.request, resp_unreadable
    )


async def test_case_4_hostile_query_and_snippet_safety(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Case 4: Hostile query punctuation and HTML wrapper tag suppression."""
    admin = await make_user("admin4", workspace_role="WORKSPACE_ADMIN")
    proj_id = await make_project("HST", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    client = as_principal(admin)
    ws_id = api_env.workspace_id

    # Seed doc containing raw HTML wrapper tags and scripts
    doc_id = uuid.uuid4()
    await api_env.seed.execute(
        text("SELECT register_object('doc'::object_kind, :ws, :proj, :ckey, :title, :cr, :id)"),
        {
            "ws": ws_id,
            "proj": proj_id,
            "ckey": "docs/security/hardening",
            "title": "Security Hardening",
            "cr": admin.id,
            "id": doc_id,
        },
    )
    doc_body = (
        "## Policy\n"
        "Here is a <script>alert('xss')</script>script with <b>bolded target keyword</b> "
        "and <mark>highlighted section</mark>."
    )
    await api_env.seed.execute(
        text(
            "INSERT INTO docs (id, object_type, workspace_id, project_id, title, "
            "body_markdown, hierarchy_path) "
            "VALUES (:id, 'doc', :ws, :proj, :title, :body, 'top')"
        ),
        {
            "id": doc_id,
            "ws": ws_id,
            "proj": proj_id,
            "title": "Security Hardening",
            "body": doc_body,
        },
    )

    await rebuild_era(api_env.seed, ws_id)
    await api_env.seed.commit()

    # 1. Hostile query containing syntax operators and control characters
    hostile_query = "' | & ! : * ( ) \x00 <script>"
    encoded_q = urllib.parse.quote(hostile_query)
    resp_hostile = await client.get(f"/api/v1/search?q={encoded_q}")
    assert resp_hostile.status_code == 200

    resp_hostile_post = await client.post(
        "/api/v1/search/knowledge",
        json={"query": hostile_query, "kinds": ["doc"]},
    )
    assert resp_hostile_post.status_code == 200

    # 2. Search for keyword in doc and verify zero raw HTML wrapper tags in snippet
    resp_clean = await client.post(
        "/api/v1/search/knowledge",
        json={"query": "keyword", "kinds": ["doc"]},
    )
    assert resp_clean.status_code == 200
    items = resp_clean.json()["items"]
    assert len(items) >= 1
    snippet = items[0]["snippet"]
    assert "<script>" not in snippet
    assert "</script>" not in snippet
    assert "<b>" not in snippet
    assert "</b>" not in snippet
    assert "<mark>" not in snippet
    assert "</mark>" not in snippet


async def test_case_5_boundaries_and_pagination(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Case 5: Input boundaries (422) and deterministic keyset cursor pagination across 35 items."""
    admin = await make_user("admin5", workspace_role="WORKSPACE_ADMIN")
    proj_id = await make_project("BND", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    client = as_principal(admin)
    ws_id = api_env.workspace_id

    # 1. Boundary validations
    # Empty / whitespace query -> 422
    r_empty = await client.get("/api/v1/search?q=")
    assert r_empty.status_code == 422
    assert r_empty.json()["code"] == "QUERY_LENGTH"

    r_space = await client.get("/api/v1/search?q=   ")
    assert r_space.status_code == 422
    assert r_space.json()["code"] == "QUERY_LENGTH"

    # Query length 501 chars -> 422
    r_long = await client.get(f"/api/v1/search?q={'a' * 501}")
    assert r_long.status_code == 422
    assert r_long.json()["code"] == "QUERY_LENGTH"

    # Limit = 51 -> 422
    r_lim = await client.get("/api/v1/search?q=valid&limit=51")
    assert r_lim.status_code == 422

    # Invalid kind -> 422
    r_kind = await client.get("/api/v1/search?q=valid&kinds=invalid_kind")
    assert r_kind.status_code == 422

    # 2. Seed 35 issues matching "Scalability"
    state_id = (
        await api_env.seed.execute(
            text("SELECT id FROM workflow_states WHERE project_id = :p LIMIT 1"), {"p": proj_id}
        )
    ).scalar_one()
    pri_id = (
        await api_env.seed.execute(
            text("SELECT id FROM project_priorities WHERE project_id = :p LIMIT 1"), {"p": proj_id}
        )
    ).scalar_one()

    all_seeded_ids: list[uuid.UUID] = []
    for i in range(1, 36):
        iss_id = await _seed_test_issue(
            api_env.seed,
            ws_id,
            proj_id,
            "BND",
            i,
            f"Scalability test issue {i}",
            f"Benchmark data for scalability testing iteration {i}.",
            admin.id,
            state_id,
            pri_id,
            f"a{i:06d}",
        )
        all_seeded_ids.append(iss_id)

    await rebuild_era(api_env.seed, ws_id)
    await api_env.seed.commit()

    # Page 1: limit=20
    resp_p1 = await client.post(
        "/api/v1/search/issues",
        json={"query": "Scalability", "project": "BND", "limit": 20},
    )
    assert resp_p1.status_code == 200
    d1 = resp_p1.json()
    assert d1["total"] == 35
    assert len(d1["items"]) == 20
    cursor_1 = d1["next_cursor"]
    assert cursor_1 is not None

    # Page 2: limit=20 with cursor_1
    resp_p2 = await client.post(
        "/api/v1/search/issues",
        json={"query": "Scalability", "project": "BND", "limit": 20, "cursor": cursor_1},
    )
    assert resp_p2.status_code == 200
    d2 = resp_p2.json()
    assert d2["total"] == 35
    assert len(d2["items"]) == 15
    assert d2["next_cursor"] is None

    # Verify deterministic pagination: Page 1 and Page 2 have disjoint ID sets
    ids_p1 = {it["id"] for it in d1["items"]}
    ids_p2 = {it["id"] for it in d2["items"]}
    assert len(ids_p1) == 20
    assert len(ids_p2) == 15
    assert ids_p1.isdisjoint(ids_p2)
    assert (ids_p1 | ids_p2) == {str(uid) for uid in all_seeded_ids}

    # 3. Invalid cursor tampering -> 422 INVALID_CURSOR
    resp_tampered = await client.post(
        "/api/v1/search/issues",
        json={
            "query": "Scalability",
            "project": "BND",
            "limit": 20,
            "cursor": "tampered_cursor_data",
        },
    )
    assert resp_tampered.status_code == 422
    assert resp_tampered.json()["code"] == "INVALID_CURSOR"

    # Mismatched query cursor -> 422 INVALID_CURSOR
    resp_mismatch = await client.post(
        "/api/v1/search/issues",
        json={"query": "DifferentQuery", "project": "BND", "limit": 20, "cursor": cursor_1},
    )
    assert resp_mismatch.status_code == 422
    assert resp_mismatch.json()["code"] == "INVALID_CURSOR"


async def test_case_6_coverage_and_edge_cases(  # noqa: PLR0915
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Case 6: Edge cases, page/sticky queries, query lengths < 3, and pagination cursors."""
    admin = await make_user("admin6", workspace_role="WORKSPACE_ADMIN")
    proj_id = await make_project("EDG", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    client = as_principal(admin)
    ws_id = api_env.workspace_id

    # 1. Custom signing key in env
    monkeypatch.delenv("SESSION_SECRET", raising=False)
    monkeypatch.setenv("SECRET_KEY", "custom-secret-key-12345")
    assert _get_signing_key() == "custom-secret-key-12345"

    # 2. Tampered HMAC signature in decode_search_cursor
    tampered_packet = {"v": "1.0", "i": str(uuid.uuid4()), "q": "abc", "s": "bad_sig_hex"}
    b64_tampered = base64.urlsafe_b64encode(json.dumps(tampered_packet).encode()).decode()
    with pytest.raises(ProblemException) as exc_info:
        decode_search_cursor(b64_tampered, "abc")
    assert exc_info.value.code == "INVALID_CURSOR"

    # 3. Limit invalid direct service validation
    with pytest.raises(ProblemException) as exc_lim:
        validate_limit(0)
    assert exc_lim.value.code == "LIMIT_INVALID"

    with pytest.raises(ProblemException) as exc_lim2:
        validate_limit(51)
    assert exc_lim2.value.code == "LIMIT_INVALID"

    # 4. Search invalid kind
    r_bad_kind = await client.get("/api/v1/search?q=test&kinds=invalid")
    assert r_bad_kind.status_code == 422
    assert r_bad_kind.json()["code"] == "INVALID_KIND"

    # 5. Short query len < 3 (skips trigram path)
    r_short = await client.get("/api/v1/search?q=ab")
    assert r_short.status_code == 200

    # 6. Seed Doc, Page and Sticky
    doc_id = uuid.uuid4()
    await api_env.seed.execute(
        text("SELECT register_object('doc'::object_kind, :ws, :proj, :ckey, 'Edge Doc', :cr, :id)"),
        {
            "ws": ws_id,
            "proj": proj_id,
            "ckey": f"doc-{doc_id.hex[:8]}",
            "cr": admin.id,
            "id": doc_id,
        },
    )
    await api_env.seed.execute(
        text(
            "INSERT INTO docs (id, workspace_id, project_id, title, body_markdown) "
            "VALUES (:id, :ws, :proj, 'Edge Doc', 'Doc markdown')"
        ),
        {"id": doc_id, "ws": ws_id, "proj": proj_id},
    )

    page_id = uuid.uuid4()
    await api_env.seed.execute(
        text("SELECT register_object('page'::object_kind, :ws, :proj, :ckey, :title, :cr, :id)"),
        {
            "ws": ws_id,
            "proj": proj_id,
            "ckey": "EDG/pages/security-overview",
            "title": "Edge Security Page",
            "cr": admin.id,
            "id": page_id,
        },
    )
    await api_env.seed.execute(
        text(
            "INSERT INTO pages (id, workspace_id, doc_id, title, body_markdown) "
            "VALUES (:id, :ws, :doc, :title, :body)"
        ),
        {
            "id": page_id,
            "ws": ws_id,
            "doc": doc_id,
            "title": "Edge Security Page",
            "body": "Edge security page documentation details.",
        },
    )

    sticky_id = uuid.uuid4()
    await api_env.seed.execute(
        text("SELECT register_object('sticky'::object_kind, :ws, :proj, :ckey, :title, :cr, :id)"),
        {
            "ws": ws_id,
            "proj": proj_id,
            "ckey": f"EDG/stickies/{sticky_id}",
            "title": "Sticky Note",
            "cr": admin.id,
            "id": sticky_id,
        },
    )
    await api_env.seed.execute(
        text(
            "INSERT INTO stickies (id, workspace_id, project_id, body_markdown) "
            "VALUES (:id, :ws, :proj, :body)"
        ),
        {
            "id": sticky_id,
            "ws": ws_id,
            "proj": proj_id,
            "body": "Sticky note reminder about edge security configurations.",
        },
    )

    # Seed 25 test pages for knowledge cursor pagination
    for k in range(1, 26):
        pid = uuid.uuid4()
        await api_env.seed.execute(
            text(
                "SELECT register_object('page'::object_kind, :ws, :proj, :ckey, :title, :cr, :id)"
            ),
            {
                "ws": ws_id,
                "proj": proj_id,
                "ckey": f"EDG/pages/perf-{k}",
                "title": f"Performance Benchmark Page {k}",
                "cr": admin.id,
                "id": pid,
            },
        )
        await api_env.seed.execute(
            text(
                "INSERT INTO pages (id, workspace_id, doc_id, title, body_markdown) "
                "VALUES (:id, :ws, :doc, :title, :body)"
            ),
            {
                "id": pid,
                "ws": ws_id,
                "doc": doc_id,
                "title": f"Performance Benchmark Page {k}",
                "body": f"Page {k} content details on performance benchmarking.",
            },
        )

    # Seed an issue with key EDG-1
    st_id = (
        await api_env.seed.execute(
            text("SELECT id FROM workflow_states WHERE project_id = :p LIMIT 1"), {"p": proj_id}
        )
    ).scalar_one()
    pri_id = (
        await api_env.seed.execute(
            text("SELECT id FROM project_priorities WHERE project_id = :p LIMIT 1"), {"p": proj_id}
        )
    ).scalar_one()
    await _seed_test_issue(
        api_env.seed,
        ws_id,
        proj_id,
        "EDG",
        1,
        "Edge issue title",
        "Edge issue description.",
        admin.id,
        st_id,
        pri_id,
        "a0",
    )

    await rebuild_era(api_env.seed, ws_id)
    await api_env.seed.commit()

    # Query with specific kinds
    r_page = await client.get("/api/v1/search?q=Edge&kinds=page")
    assert r_page.status_code == 200
    assert any(it["kind"] == "page" for it in r_page.json()["items"])

    r_sticky = await client.get("/api/v1/search?q=reminder&kinds=sticky")
    assert r_sticky.status_code == 200
    assert any(it["kind"] == "sticky" for it in r_sticky.json()["items"])

    # Issue search with key match EDG-1
    r_key = await client.post("/api/v1/search/issues", json={"query": "EDG-1", "project": "EDG"})
    assert r_key.status_code == 200
    assert r_key.json()["items"][0]["key"] == "EDG-1"

    # Knowledge search pagination across 25 pages
    r_k_p1 = await client.post(
        "/api/v1/search/knowledge",
        json={"query": "Performance", "project": "EDG", "kinds": ["page"], "limit": 20},
    )
    assert r_k_p1.status_code == 200
    d_k_p1 = r_k_p1.json()
    assert d_k_p1["total"] == 25
    assert len(d_k_p1["items"]) == 20
    cursor_k = d_k_p1["next_cursor"]
    assert cursor_k is not None

    r_k_p2 = await client.post(
        "/api/v1/search/knowledge",
        json={
            "query": "Performance",
            "project": "EDG",
            "kinds": ["page"],
            "limit": 20,
            "cursor": cursor_k,
        },
    )
    assert r_k_p2.status_code == 200
    d_k_p2 = r_k_p2.json()
    assert d_k_p2["total"] == 25
    assert len(d_k_p2["items"]) == 5
    assert d_k_p2["next_cursor"] is None

    # Unified search pagination across 25 pages
    r_u_p1 = await client.get("/api/v1/search?q=Performance&project=EDG&limit=20")
    assert r_u_p1.status_code == 200
    d_u_p1 = r_u_p1.json()
    assert d_u_p1["total"] == 25
    assert len(d_u_p1["items"]) == 20
    cursor_u = d_u_p1["next_cursor"]
    assert cursor_u is not None

    r_u_p2 = await client.get(
        f"/api/v1/search?q=Performance&project=EDG&limit=20&cursor={cursor_u}"
    )
    assert r_u_p2.status_code == 200
    d_u_p2 = r_u_p2.json()
    assert d_u_p2["total"] == 25
    assert len(d_u_p2["items"]) == 5
    assert d_u_p2["next_cursor"] is None
