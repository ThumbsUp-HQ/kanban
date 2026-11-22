# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Full-text and trigram lexical search service across issues, docs, pages, and stickies.

Implements S11.2, S11.3, S12.2, and KB-P3-17.
"""

from __future__ import annotations

import base64
import contextlib
import hashlib
import hmac
import importlib
import json
import os
import re
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final

from sqlalchemy import (
    ColumnElement,
    Float,
    Select,
    String,
    and_,
    case,
    cast,
    func,
    literal,
    or_,
    select,
    text,
    union_all,
)

from database.models import (
    Doc,
    Issue,
    IssueAssignee,
    ObjectRecord,
    Page,
    Principal,
    Project,
    ProjectPriority,
    Sticky,
    WorkflowState,
    Workspace,
)
from kanban.api.problems import ProblemException
from kanban.api.v1.schemas.search import (
    IssueSearchItem,
    IssueSearchRequest,
    IssueSearchResponse,
    KnowledgeSearchItem,
    KnowledgeSearchRequest,
    KnowledgeSearchResponse,
    SearchItem,
    SearchResponse,
)
from kanban.services.projects import get_project_or_404
from kanban.services.snippets import build_anchored_snippet
from kanban.services.synaptic_rescorer import (
    SynapticSeed,
    exact_identifier_heading_maxsim,
    int8_dot_product,
    quantize_int8,
    reciprocal_rank_fusion,
    spread_synaptic_activation,
)
from kanban.services.view_dsl import compile_issue_filter_predicates

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy.ext.asyncio import AsyncSession

    from kanban.api.deps import PrincipalContext
    from kanban.api.v1.schemas.views import FilterSpec

__all__ = [
    "decode_search_cursor",
    "encode_search_cursor",
    "search_issues",
    "search_knowledge",
    "search_unified",
    "validate_limit",
    "validate_query",
]

_CONTROL_CHARS_RE: Final[re.Pattern[str]] = re.compile(r"[\x00-\x1f]")
_ISSUE_KEY_RE: Final[re.Pattern[str]] = re.compile(r"^([A-Za-z][A-Za-z0-9]{1,9})-(\d+)$")
_DEFAULT_CURSOR_KEY: Final[str] = "kanban-search-cursor-secret-signing-key"

_SIM_THRESHOLD: Final[float] = 0.25
_MIN_TRIGRAM_CHARS: Final[int] = 3
_TEXT_RANK_WEIGHT: Final[float] = 0.75
_SIM_WEIGHT: Final[float] = 0.25
_EXACT_KEY_BOOST: Final[float] = 100.0
_RANK_NORMALIZATION: Final[int] = 32

_MAX_QUERY_CHARS: Final[int] = 500
_MAX_LIMIT: Final[int] = 50
_TARGET_DIMENSION: Final[int] = 384


def _get_signing_key() -> str:
    """Retrieve secret key for HMAC cursor signing."""
    return os.environ.get("SESSION_SECRET") or os.environ.get("SECRET_KEY") or _DEFAULT_CURSOR_KEY


def validate_query(raw_query: str) -> str:
    """Normalize and validate user query length.

    Args:
        raw_query: Raw input query string.

    Returns:
        Sanitized query string with control characters removed and whitespace trimmed.

    Raises:
        ProblemException: 422 QUERY_LENGTH if length not between 1 and 500 characters.

    """
    cleaned = _CONTROL_CHARS_RE.sub(" ", raw_query).strip()
    if not (1 <= len(cleaned) <= _MAX_QUERY_CHARS):
        raise ProblemException(
            code="QUERY_LENGTH",
            status=422,
            title="Invalid Query Length",
            detail="Search query must be between 1 and 500 characters.",
        )
    return cleaned


def validate_limit(limit: int) -> int:
    """Validate pagination limit bounds.

    Args:
        limit: Requested page limit.

    Returns:
        Validated integer limit.

    Raises:
        ProblemException: 422 LIMIT_INVALID if outside 1..50.

    """
    if not (1 <= limit <= _MAX_LIMIT):
        raise ProblemException(
            code="LIMIT_INVALID",
            status=422,
            title="Invalid Limit",
            detail="Limit must be between 1 and 50.",
        )
    return limit


def _compute_query_hash(query: str, kinds: list[str], project_ref: str | None) -> str:
    """Compute query hash for binding cursors to search parameters."""
    normalized_kinds = ",".join(sorted(kinds))
    payload = f"{query}|{normalized_kinds}|{project_ref or ''}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def encode_search_cursor(score: float, item_id: uuid.UUID, q_hash: str) -> str:
    """Encode an HMAC-signed keyset pagination cursor."""
    key = _get_signing_key()
    score_str = repr(float(score))
    id_str = str(item_id)
    raw = f"{score_str}|{id_str}|{q_hash}"
    sig = hmac.new(key.encode(), raw.encode(), hashlib.sha256).hexdigest()
    packet = {
        "v": score_str,
        "i": id_str,
        "q": q_hash,
        "s": sig,
    }
    dumped = json.dumps(packet, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(dumped).decode("ascii").rstrip("=")


def decode_search_cursor(cursor: str, expected_q_hash: str) -> tuple[float, uuid.UUID]:
    """Decode and verify an HMAC-signed keyset cursor.

    Args:
        cursor: Base64url cursor string.
        expected_q_hash: Bound query parameter hash.

    Returns:
        Tuple of (score, item_id).

    Raises:
        ProblemException: 422 INVALID_CURSOR if signature fails or query mismatches.

    """
    key = _get_signing_key()
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        raw_bytes = base64.urlsafe_b64decode(padded)
        packet = json.loads(raw_bytes.decode())
        score_str = str(packet["v"])
        id_str = str(packet["i"])
        q_hash = str(packet["q"])
        sig = str(packet["s"])
        score_val = float(score_str)
        item_uuid = uuid.UUID(id_str)
    except (ValueError, KeyError, TypeError) as exc:
        raise ProblemException(
            code="INVALID_CURSOR",
            status=422,
            title="Invalid Cursor",
            detail="The provided pagination cursor is invalid.",
        ) from exc

    expected_sig = hmac.new(
        key.encode(),
        f"{score_str}|{id_str}|{q_hash}".encode(),
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(sig, expected_sig):
        raise ProblemException(
            code="INVALID_CURSOR",
            status=422,
            title="Invalid Cursor",
            detail="Cursor signature verification failed.",
        )
    if q_hash != expected_q_hash:
        raise ProblemException(
            code="INVALID_CURSOR",
            status=422,
            title="Invalid Cursor",
            detail="Cursor was issued for a different query.",
        )

    return score_val, item_uuid


def _build_issue_query(
    clean_query: str,
    project_id: uuid.UUID | None,
    key_match: tuple[str, int] | None,
    extra_predicates: list[Any] | None = None,
    *,
    include_metadata: bool = False,
) -> Select[Any]:
    """Build issue search query expression."""
    match_conditions: list[ColumnElement[bool]] = []
    if clean_query:
        tsq = func.websearch_to_tsquery("english", clean_query)
        ts_rank = func.ts_rank_cd(Issue.search_tsv, tsq, _RANK_NORMALIZATION)
        w_sim = func.greatest(func.word_similarity(clean_query, Issue.summary), 0.0)
        raw_score = cast(_TEXT_RANK_WEIGHT * ts_rank + _SIM_WEIGHT * w_sim, Float)

        key_proj, key_seq = key_match or ("", -1)
        is_key_match = and_(
            func.upper(Project.identifier) == key_proj,
            Issue.sequence_id == key_seq,
        )

        score_expr = case(
            (is_key_match, literal(_EXACT_KEY_BOOST, type_=Float)),
            else_=raw_score,
        ).label("score")

        match_conditions.append(Issue.search_tsv.op("@@")(tsq))
        if len(clean_query) >= _MIN_TRIGRAM_CHARS:
            match_conditions.append(
                func.word_similarity(clean_query, Issue.summary) >= _SIM_THRESHOLD
            )
        if key_match:
            match_conditions.append(is_key_match)
    else:
        score_expr = literal(1.0, type_=Float).label("score")

    select_cols: list[Any] = [
        literal("issue").label("kind"),
        Issue.id.label("id"),
        (Project.identifier + "-" + cast(Issue.sequence_id, String)).label("key"),
        Issue.summary.label("title"),
        Issue.summary.label("summary"),
        Issue.description_markdown.label("body_markdown"),
        Project.identifier.label("project_identifier"),
        score_expr,
    ]
    if include_metadata:
        select_cols.extend(
            [
                WorkflowState.name.label("state_name"),
                ProjectPriority.slug.label("priority_slug"),
                Workspace.slug.label("workspace_slug"),
            ]
        )

    stmt = (
        select(*select_cols)
        .join(Project, Issue.project_id == Project.id)
        .join(ObjectRecord, Issue.id == ObjectRecord.id)
    )
    if include_metadata:
        stmt = (
            stmt.outerjoin(WorkflowState, Issue.state_id == WorkflowState.id)
            .outerjoin(ProjectPriority, Issue.priority_id == ProjectPriority.id)
            .outerjoin(Workspace, Project.workspace_id == Workspace.id)
        )

    stmt = stmt.where(
        ObjectRecord.deleted_at.is_(None),
        ObjectRecord.archived_at.is_(None),
    )
    if match_conditions:
        stmt = stmt.where(or_(*match_conditions))

    if project_id is not None:
        stmt = stmt.where(Issue.project_id == project_id)

    if extra_predicates:
        stmt = stmt.where(*extra_predicates)

    return stmt


def _build_doc_query(clean_query: str, project_id: uuid.UUID | None) -> Select[Any]:
    """Build doc search query expression."""
    tsq = func.websearch_to_tsquery("english", clean_query)
    ts_rank = func.ts_rank_cd(Doc.search_tsv, tsq, _RANK_NORMALIZATION)
    w_sim = func.greatest(func.word_similarity(clean_query, Doc.title), 0.0)
    score_expr = cast(_TEXT_RANK_WEIGHT * ts_rank + _SIM_WEIGHT * w_sim, Float).label("score")

    match_conditions: list[ColumnElement[bool]] = [Doc.search_tsv.op("@@")(tsq)]
    if len(clean_query) >= _MIN_TRIGRAM_CHARS:
        match_conditions.append(func.word_similarity(clean_query, Doc.title) >= _SIM_THRESHOLD)

    stmt = (
        select(
            literal("doc").label("kind"),
            Doc.id.label("id"),
            literal(None, type_=String).label("key"),
            Doc.title.label("title"),
            literal(None, type_=String).label("summary"),
            Doc.body_markdown.label("body_markdown"),
            Project.identifier.label("project_identifier"),
            score_expr,
        )
        .join(ObjectRecord, Doc.id == ObjectRecord.id)
        .outerjoin(Project, Doc.project_id == Project.id)
        .where(
            ObjectRecord.deleted_at.is_(None),
            ObjectRecord.archived_at.is_(None),
            or_(*match_conditions),
        )
    )

    if project_id is not None:
        stmt = stmt.where(Doc.project_id == project_id)

    return stmt


def _build_page_query(clean_query: str, project_id: uuid.UUID | None) -> Select[Any]:
    """Build page search query expression."""
    tsq = func.websearch_to_tsquery("english", clean_query)
    ts_rank = func.ts_rank_cd(Page.search_tsv, tsq, _RANK_NORMALIZATION)
    w_sim = func.greatest(func.word_similarity(clean_query, Page.title), 0.0)
    score_expr = cast(_TEXT_RANK_WEIGHT * ts_rank + _SIM_WEIGHT * w_sim, Float).label("score")

    match_conditions: list[ColumnElement[bool]] = [Page.search_tsv.op("@@")(tsq)]
    if len(clean_query) >= _MIN_TRIGRAM_CHARS:
        match_conditions.append(func.word_similarity(clean_query, Page.title) >= _SIM_THRESHOLD)

    stmt = (
        select(
            literal("page").label("kind"),
            Page.id.label("id"),
            literal(None, type_=String).label("key"),
            Page.title.label("title"),
            literal(None, type_=String).label("summary"),
            Page.body_markdown.label("body_markdown"),
            Project.identifier.label("project_identifier"),
            score_expr,
        )
        .join(Doc, Page.doc_id == Doc.id)
        .join(ObjectRecord, Page.id == ObjectRecord.id)
        .outerjoin(Project, Doc.project_id == Project.id)
        .where(
            ObjectRecord.deleted_at.is_(None),
            ObjectRecord.archived_at.is_(None),
            or_(*match_conditions),
        )
    )

    if project_id is not None:
        stmt = stmt.where(Doc.project_id == project_id)

    return stmt


def _build_sticky_query(
    clean_query: str,
    project_id: uuid.UUID | None,
    *,
    include_promoted: bool = False,
) -> Select[Any]:
    """Build sticky search query expression."""
    tsq = func.websearch_to_tsquery("english", clean_query)
    ts_rank = func.ts_rank_cd(Sticky.search_tsv, tsq, _RANK_NORMALIZATION)
    w_sim = func.greatest(func.word_similarity(clean_query, Sticky.body_markdown), 0.0)
    score_expr = cast(_TEXT_RANK_WEIGHT * ts_rank + _SIM_WEIGHT * w_sim, Float).label("score")

    match_conditions: list[ColumnElement[bool]] = [Sticky.search_tsv.op("@@")(tsq)]
    if len(clean_query) >= _MIN_TRIGRAM_CHARS:
        match_conditions.append(
            func.word_similarity(clean_query, Sticky.body_markdown) >= _SIM_THRESHOLD
        )

    stmt = (
        select(
            literal("sticky").label("kind"),
            Sticky.id.label("id"),
            literal(None, type_=String).label("key"),
            literal("Sticky Note").label("title"),
            literal(None, type_=String).label("summary"),
            Sticky.body_markdown.label("body_markdown"),
            Project.identifier.label("project_identifier"),
            score_expr,
        )
        .join(ObjectRecord, Sticky.id == ObjectRecord.id)
        .outerjoin(Project, Sticky.project_id == Project.id)
        .where(
            ObjectRecord.deleted_at.is_(None),
            ObjectRecord.archived_at.is_(None),
            or_(*match_conditions),
        )
    )

    if not include_promoted:
        stmt = stmt.where(Sticky.promoted_to_doc_id.is_(None))

    if project_id is not None:
        stmt = stmt.where(Sticky.project_id == project_id)

    return stmt


def _format_search_items(
    rows: Sequence[Any], query: str, default_match_reason: str = "Lexical match"
) -> list[SearchItem]:
    """Format unified search item rows with anchored snippets."""
    items: list[SearchItem] = []
    for r in rows:
        body = getattr(r, "body_markdown", None) or ""
        snippet_result = build_anchored_snippet(body, query)
        reason = getattr(r, "match_reason", None) or default_match_reason
        items.append(
            SearchItem(
                kind=r.kind,
                id=r.id,
                key=r.key,
                title=r.title,
                summary=getattr(r, "summary", None),
                project_identifier=getattr(r, "project_identifier", None),
                anchor=snippet_result.anchor,
                snippet=snippet_result.snippet,
                match_spans=snippet_result.match_spans,
                score=float(r.score),
                match_reason=reason,
            )
        )
    return items


@dataclass
class _HydratedCandidate:
    """Internal candidate representation across lexical, vector, and synaptic stages."""

    id: uuid.UUID
    kind: str
    key: str | None
    title: str
    summary: str | None
    body_markdown: str
    project_identifier: str | None
    score: float
    match_reason: str
    state_name: str | None = None
    priority_slug: str | None = None
    workspace_slug: str | None = None


async def _get_query_embedding(query: str) -> list[float] | None:
    """Dynamically acquire query embedding via agent ONNX or fixture embedder."""
    if not query or not query.strip():
        return None
    try:
        mod = importlib.import_module("agent.embeddings.onnx_embedder")
        embedder_cls = getattr(mod, "OnnxBgeSmallEmbedder", None)
        fixture_cls = getattr(mod, "FixtureEmbedder", None)
        embedder = None
        if embedder_cls is not None:
            with contextlib.suppress(Exception):
                embedder = embedder_cls(fallback_to_fixture=True)
        if embedder is None and fixture_cls is not None:
            embedder = fixture_cls()
        if embedder is not None:
            vectors = await embedder.embed_batch([query])
            if vectors and len(vectors[0]) == _TARGET_DIMENSION:
                return list(vectors[0])
    except Exception:  # noqa: BLE001
        return None
    return None


async def _query_vector_candidates(  # noqa: PLR0913, PLR0917
    session: AsyncSession,
    workspace_id: uuid.UUID,
    project_id: uuid.UUID | None,
    target_kinds: list[str],
    query_vector: list[float],
    limit: int = 50,
) -> list[tuple[uuid.UUID, str, int, list[float], float]] | None:
    """Query object_embeddings with cosine distance under READ ONLY statement_timeout <= 25ms."""
    try:
        async with session.begin_nested():
            await session.execute(text("SET LOCAL statement_timeout = '25ms'"))
            try:
                async with session.begin_nested():
                    await session.execute(text("SET LOCAL hnsw.iterative_scan = 'relaxed_order'"))
            except Exception:  # noqa: BLE001, S110
                pass
            q_literal = "[" + ",".join(str(float(x)) for x in query_vector) + "]"
            where_clauses = [
                "oe.workspace_id = :ws_id",
                "CAST(oe.object_type AS text) = ANY(CAST(:kinds AS text[]))",
            ]
            params: dict[str, Any] = {
                "ws_id": workspace_id,
                "kinds": target_kinds,
                "q_vec": q_literal,
                "lim": limit,
            }
            if project_id is not None:
                where_clauses.append("oe.project_id = :proj_id")
                params["proj_id"] = project_id

            sql = text(
                "SELECT "  # noqa: S608
                "  oe.object_id, "
                "  CAST(oe.object_type AS text) AS obj_type, "
                "  oe.chunk_index, "
                "  CAST(oe.embedding AS text) AS embedding_text, "
                "  (1.0 - (oe.embedding <=> CAST(:q_vec AS vector))) AS cosine_sim "
                "FROM object_embeddings oe "
                f"WHERE {' AND '.join(where_clauses)} "
                "ORDER BY oe.embedding <=> CAST(:q_vec AS vector) "
                "LIMIT :lim"
            )
            res = await session.execute(sql, params)
            await session.execute(text("SET LOCAL statement_timeout = 0"))
            rows = res.fetchall()
            if not rows:
                return None
            candidates = []
            for r in rows:
                oid = uuid.UUID(str(r[0]))
                otype = str(r[1])
                cidx = int(r[2])
                raw_text = str(r[3]).strip("[]")
                emb = [float(x) for x in raw_text.split(",") if x.strip()] if raw_text else []
                sim = float(r[4])
                candidates.append((oid, otype, cidx, emb, sim))
            return candidates
    except Exception:  # noqa: BLE001
        return None


async def _hydrate_object_candidates(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    object_ids: list[uuid.UUID],
    target_kinds: list[str],
) -> dict[uuid.UUID, _HydratedCandidate]:
    """Hydrate full entity metadata from database under caller RLS."""
    if not object_ids:
        return {}

    sql = text(
        "SELECT "
        "  o.id, "
        "  CAST(o.object_type AS text) AS kind, "
        "  o.canonical_key AS key, "
        "  o.display_title AS title, "
        "  p.identifier AS project_identifier, "
        "  i.summary AS issue_summary, "
        "  i.description_markdown AS issue_body, "
        "  d.body_markdown AS doc_body, "
        "  pg.body_markdown AS page_body, "
        "  st.body_markdown AS sticky_body, "
        "  ws.name AS state_name, "
        "  pp.slug AS priority_slug, "
        "  w.slug AS workspace_slug "
        "FROM objects o "
        "LEFT JOIN projects p ON p.id = o.project_id "
        "LEFT JOIN workspaces w ON w.id = o.workspace_id "
        "LEFT JOIN issues i ON i.id = o.id "
        "LEFT JOIN workflow_states ws ON ws.id = i.state_id "
        "LEFT JOIN project_priorities pp ON pp.id = i.priority_id "
        "LEFT JOIN docs d ON d.id = o.id "
        "LEFT JOIN pages pg ON pg.id = o.id "
        "LEFT JOIN stickies st ON st.id = o.id "
        "WHERE o.id = ANY(CAST(:ids AS uuid[])) "
        "  AND o.workspace_id = :ws_id "
        "  AND CAST(o.object_type AS text) = ANY(CAST(:kinds AS text[])) "
        "  AND o.deleted_at IS NULL "
        "  AND o.archived_at IS NULL "
        "  AND EXISTS ( "
        "    SELECT 1 FROM effective_resource_access era "
        "    WHERE era.object_id = o.id "
        "      AND era.principal_id = ANY(app_effective_principal_set()) "
        "      AND (era.allow_mask & 1) = 1 "
        "      AND (era.deny_mask & 1) = 0 "
        "  )"
    )

    rows = (
        await session.execute(
            sql,
            {"ids": object_ids, "ws_id": workspace_id, "kinds": target_kinds},
        )
    ).all()

    result: dict[uuid.UUID, _HydratedCandidate] = {}
    for r in rows:
        cid = uuid.UUID(str(r[0]))
        kind = str(r[1])
        key = str(r[2]) if r[2] else None
        title = str(r[3]) if r[3] else ""
        proj_ident = str(r[4]) if r[4] else None
        issue_sum = str(r[5]) if r[5] else None
        issue_b = str(r[6]) if r[6] else None
        doc_b = str(r[7]) if r[7] else None
        page_b = str(r[8]) if r[8] else None
        sticky_b = str(r[9]) if r[9] else None
        state_n = str(r[10]) if r[10] else None
        prio_s = str(r[11]) if r[11] else None
        ws_slug = str(r[12]) if r[12] else None

        body = issue_b or doc_b or page_b or sticky_b or ""
        summary = issue_sum or (title if kind == "issue" else None)

        result[cid] = _HydratedCandidate(
            id=cid,
            kind=kind,
            key=key,
            title=title or (summary or "Entity"),
            summary=summary,
            body_markdown=body,
            project_identifier=proj_ident,
            score=0.0,
            match_reason="Lexical match",
            state_name=state_n,
            priority_slug=prio_s,
            workspace_slug=ws_slug,
        )
    return result


async def _execute_hybrid_search_core(  # noqa: C901, PLR0912, PLR0913, PLR0915, PLR0917
    session: AsyncSession,
    caller: PrincipalContext,
    clean_query: str,
    target_kinds: list[str],
    project_id: uuid.UUID | None,
    lexical_rows: Sequence[Any],
) -> list[_HydratedCandidate] | None:
    """Core hybrid fusion: vector search, RRF, int8 rescoring, MaxSim boost, synaptic spreading."""
    query_vector = await _get_query_embedding(clean_query)
    if query_vector is None:
        return None

    await session.execute(
        text(
            "SELECT set_config('app.principal_id', :p_id, true), "
            "       set_config('app.workspace_id', :ws_id, true)"
        ),
        {"p_id": str(caller.principal_id), "ws_id": str(caller.workspace_id)},
    )

    vector_hits = await _query_vector_candidates(
        session=session,
        workspace_id=caller.workspace_id,
        project_id=project_id,
        target_kinds=target_kinds,
        query_vector=query_vector,
        limit=50,
    )
    if not vector_hits:
        return None

    # Deduplicate vector candidates: best cosine_sim per object_id
    best_vector: dict[uuid.UUID, tuple[str, list[float], float]] = {}
    for oid, otype, _cidx, emb, sim in vector_hits:
        prev = best_vector.get(oid)
        if prev is None or sim > prev[2]:
            best_vector[oid] = (otype, emb, sim)

    # Ranked vector IDs
    vector_ranked_ids = [
        oid for oid, _ in sorted(best_vector.items(), key=lambda it: it[1][2], reverse=True)
    ]
    # Ranked lexical IDs
    lexical_ranked_ids = [r.id for r in lexical_rows]

    # Reciprocal Rank Fusion
    fused_scores = reciprocal_rank_fusion([lexical_ranked_ids, vector_ranked_ids], k=60)
    all_candidate_ids = set(fused_scores.keys())

    # Build map of already-fetched lexical rows
    hydrated: dict[uuid.UUID, _HydratedCandidate] = {}
    for r in lexical_rows:
        hydrated[r.id] = _HydratedCandidate(
            id=r.id,
            kind=r.kind,
            key=r.key,
            title=r.title,
            summary=getattr(r, "summary", None),
            body_markdown=getattr(r, "body_markdown", "") or "",
            project_identifier=getattr(r, "project_identifier", None),
            score=float(r.score),
            match_reason="Lexical match",
            state_name=getattr(r, "state_name", None),
            priority_slug=getattr(r, "priority_slug", None),
            workspace_slug=getattr(r, "workspace_slug", None),
        )

    # Hydrate any vector candidates not present in lexical rows
    missing_ids = [oid for oid in all_candidate_ids if oid not in hydrated]
    if missing_ids:
        missing_hydrated = await _hydrate_object_candidates(
            session=session,
            workspace_id=caller.workspace_id,
            object_ids=missing_ids,
            target_kinds=target_kinds,
        )
        hydrated.update(missing_hydrated)

    # Int8 dot-product rescoring & MaxSim boosting under 2ms
    q_q8, q_scale = quantize_int8(query_vector)
    rescored_seeds: list[tuple[uuid.UUID, float, bool, bool]] = []

    for cid in list(all_candidate_ids):
        cand = hydrated.get(cid)
        if not cand:
            continue

        rrf_s = fused_scores.get(cid, 0.0)
        c_vec_info = best_vector.get(cid)
        int8_sim = 0.0
        had_semantic = False
        if c_vec_info and c_vec_info[1]:
            c_q8, c_scale = quantize_int8(c_vec_info[1])
            int8_sim = int8_dot_product(q_q8, q_scale, c_q8, c_scale)
            had_semantic = True

        had_lexical = cid in hydrated and any(r.id == cid for r in lexical_rows)

        maxsim = exact_identifier_heading_maxsim(
            query=clean_query,
            title=cand.title,
            headings=[cand.title],
            identifier=cand.key,
        )

        final_score = rrf_s + (0.5 * int8_sim) + maxsim
        cand.score = final_score
        cand.match_reason = "Semantic match" if had_semantic else "Lexical match"
        rescored_seeds.append((cid, final_score, had_semantic, had_lexical))

    # Sort seeds for synaptic spreading
    rescored_seeds.sort(key=lambda it: it[1], reverse=True)
    seeds: list[SynapticSeed] = []
    for cid, s_score, s_sem, s_lex in rescored_seeds[:20]:
        cand = hydrated[cid]
        seeds.append(
            SynapticSeed(
                object_id=cid,
                object_type=cand.kind,
                score=s_score,
                key=cand.key,
                title=cand.title,
                had_semantic_match=s_sem,
                had_lexical_match=s_lex,
            )
        )

    # 2-hop Synaptic Activation Spreading
    synaptic_map = await spread_synaptic_activation(
        session=session,
        caller=caller,
        seeds=seeds,
        workspace_id=caller.workspace_id,
        max_hops=2,
    )

    # Hydrate any new neighbors discovered via synaptic spreading
    new_neighbor_ids = [
        nid
        for nid, res in synaptic_map.items()
        if nid not in hydrated and res.activation_score > 0.0
    ]
    if new_neighbor_ids:
        new_hydrated = await _hydrate_object_candidates(
            session=session,
            workspace_id=caller.workspace_id,
            object_ids=new_neighbor_ids,
            target_kinds=target_kinds,
        )
        if project_id is not None:
            proj_obj = await session.get(Project, project_id)
            proj_ident = proj_obj.identifier.upper() if proj_obj else None
            if proj_ident is not None:
                new_hydrated = {
                    nid: cand
                    for nid, cand in new_hydrated.items()
                    if cand.project_identifier is not None
                    and cand.project_identifier.upper() == proj_ident
                }
        hydrated.update(new_hydrated)

    # Apply synaptic activation scores and provenance match_reasons
    final_candidates: list[_HydratedCandidate] = []
    for oid, cand in hydrated.items():
        syn_info = synaptic_map.get(oid)
        if syn_info:
            if syn_info.hop_distance == 0:
                cand.score = cand.score + (syn_info.activation_score * 0.1)
                cand.match_reason = syn_info.match_reason
            else:
                cand.score = syn_info.activation_score
                cand.match_reason = syn_info.match_reason
        final_candidates.append(cand)

    final_candidates.sort(key=lambda c: (c.score, c.id), reverse=True)
    return final_candidates


def _parse_target_kinds(kinds: list[str] | None) -> list[str]:
    """Validate and normalize requested entity kinds."""
    if not kinds:
        return ["issue", "doc", "page", "sticky"]
    valid_kinds_set = {"issue", "doc", "page", "sticky"}
    result: list[str] = []
    for k in kinds:
        cleaned = k.strip().lower()
        if not cleaned:
            continue
        if cleaned not in valid_kinds_set:
            raise ProblemException(
                code="INVALID_KIND",
                status=422,
                title="Invalid Kind",
                detail=f"Kind '{cleaned}' is invalid; must be issue, doc, page, or sticky.",
            )
        result.append(cleaned)
    return result or ["issue", "doc", "page", "sticky"]


def _collect_unified_queries(
    target_kinds: list[str],
    clean_query: str,
    project_id: uuid.UUID | None,
    key_match_tuple: tuple[str, int] | None,
) -> list[Select[Any]]:
    """Assemble individual entity SELECT statements for unified union."""
    queries: list[Select[Any]] = []
    if "issue" in target_kinds:
        queries.append(_build_issue_query(clean_query, project_id, key_match_tuple))
    if "doc" in target_kinds:
        queries.append(_build_doc_query(clean_query, project_id))
    if "page" in target_kinds:
        queries.append(_build_page_query(clean_query, project_id))
    if "sticky" in target_kinds:
        queries.append(_build_sticky_query(clean_query, project_id))
    return queries


async def search_unified(  # noqa: PLR0913, PLR0917
    session: AsyncSession,
    caller: PrincipalContext,
    query: str,
    kinds: list[str] | None = None,
    project_ref: str | None = None,
    limit: int = 20,
    cursor: str | None = None,
    mode: str = "lexical",
) -> SearchResponse:
    """Execute unified search across issues, docs, pages, and stickies."""
    clean_query = validate_query(query)
    valid_limit = validate_limit(limit)
    target_kinds = _parse_target_kinds(kinds)

    project_id: uuid.UUID | None = None
    resolved_proj_identifier: str | None = None
    if project_ref:
        proj = await get_project_or_404(session, caller, project_ref)
        project_id = proj.id
        resolved_proj_identifier = proj.identifier

    q_hash = _compute_query_hash(clean_query, target_kinds, project_ref)
    cursor_score: float | None = None
    cursor_id: uuid.UUID | None = None
    if cursor:
        cursor_score, cursor_id = decode_search_cursor(cursor, q_hash)

    key_match_tuple: tuple[str, int] | None = None
    key_match = _ISSUE_KEY_RE.match(clean_query)
    if key_match:
        key_match_tuple = (key_match.group(1).upper(), int(key_match.group(2)))

    queries = _collect_unified_queries(target_kinds, clean_query, project_id, key_match_tuple)
    union_stmt = union_all(*queries).subquery("search_results")

    if mode == "hybrid":
        lex_rows = (
            await session.execute(select(union_stmt).order_by(union_stmt.c.score.desc()).limit(50))
        ).all()
        hybrid_candidates = await _execute_hybrid_search_core(
            session=session,
            caller=caller,
            clean_query=clean_query,
            target_kinds=target_kinds,
            project_id=project_id,
            lexical_rows=lex_rows,
        )
        if hybrid_candidates is not None:
            filtered_cands = [
                c
                for c in hybrid_candidates
                if resolved_proj_identifier is None
                or (
                    c.project_identifier is not None
                    and c.project_identifier.upper() == resolved_proj_identifier.upper()
                )
            ]
            if cursor_score is not None and cursor_id is not None:
                filtered_cands = [
                    c
                    for c in filtered_cands
                    if c.score < cursor_score or (c.score == cursor_score and c.id < cursor_id)
                ]
            total_count = len(filtered_cands)
            has_more = len(filtered_cands) > valid_limit
            page_cands = filtered_cands[:valid_limit] if has_more else filtered_cands
            items = _format_search_items(
                page_cands, clean_query, default_match_reason="Semantic match"
            )

            next_cursor = None
            if has_more and page_cands:
                last_item = page_cands[-1]
                next_cursor = encode_search_cursor(last_item.score, last_item.id, q_hash)

            return SearchResponse(
                total=total_count,
                executed_mode="hybrid",
                items=items,
                next_cursor=next_cursor,
            )

    count_stmt = select(func.count()).select_from(union_stmt)
    total_count = (await session.execute(count_stmt)).scalar() or 0

    paged_stmt = select(union_stmt)
    if cursor_score is not None and cursor_id is not None:
        paged_stmt = paged_stmt.where(
            or_(
                union_stmt.c.score < cursor_score,
                and_(union_stmt.c.score == cursor_score, union_stmt.c.id < cursor_id),
            )
        )

    paged_stmt = paged_stmt.order_by(
        union_stmt.c.score.desc(),
        union_stmt.c.id.desc(),
    ).limit(valid_limit + 1)

    rows = (await session.execute(paged_stmt)).all()

    has_more = len(rows) > valid_limit
    page_rows = rows[:valid_limit] if has_more else rows
    items = _format_search_items(page_rows, clean_query, default_match_reason="Lexical match")

    next_cursor = None
    if has_more and page_rows:
        last_lex_item = page_rows[-1]
        next_cursor = encode_search_cursor(last_lex_item.score, last_lex_item.id, q_hash)

    return SearchResponse(
        total=total_count,
        executed_mode="lexical",
        items=items,
        next_cursor=next_cursor,
    )


async def _resolve_issue_search_scope(
    session: AsyncSession,
    caller: PrincipalContext,
    project_ref: str | None,
    filters: FilterSpec | None,
    workspace_ref: str | None = None,
) -> tuple[uuid.UUID | None, list[Any], str | None]:
    """Resolve project ID and optional filter DSL predicates for issue search."""
    project_id: uuid.UUID | None = None
    proj: Project | None = None
    if project_ref:
        proj = await get_project_or_404(session, caller, project_ref)
        project_id = proj.id

    extra_predicates: list[Any] = []
    if workspace_ref:
        extra_predicates.append(Workspace.slug == workspace_ref)
    if filters:
        extra_predicates.extend(
            compile_issue_filter_predicates(session, proj, filters, caller.principal_id)
        )
    return project_id, extra_predicates, proj.identifier if proj else None


def _extract_key_match_tuple(clean_query: str) -> tuple[str, int] | None:
    """Extract project key and sequence integer if query is exact issue key."""
    if not clean_query:
        return None
    key_match = _ISSUE_KEY_RE.match(clean_query)
    if key_match:
        return (key_match.group(1).upper(), int(key_match.group(2)))
    return None


async def search_issues(  # noqa: C901, PLR0912, PLR0915
    session: AsyncSession,
    caller: PrincipalContext,
    request: IssueSearchRequest,
) -> IssueSearchResponse:
    """Execute issue-scoped lexical search composed with FilterSpec DSL predicates."""
    clean_query = ""
    if request.query and request.query.strip():
        clean_query = validate_query(request.query)
    valid_limit = validate_limit(request.limit)

    project_id, extra_predicates, resolved_proj_identifier = await _resolve_issue_search_scope(
        session, caller, request.project, request.filters, request.workspace
    )

    q_hash = _compute_query_hash(clean_query, ["issue"], request.project)
    cursor_score: float | None = None
    cursor_id: uuid.UUID | None = None
    if request.cursor:
        cursor_score, cursor_id = decode_search_cursor(request.cursor, q_hash)

    key_match_tuple = _extract_key_match_tuple(clean_query)

    issue_query = _build_issue_query(
        clean_query,
        project_id,
        key_match_tuple,
        extra_predicates,
        include_metadata=True,
    ).subquery("issue_search_results")

    if request.mode == "hybrid" and clean_query:
        lex_rows = (
            await session.execute(
                select(issue_query).order_by(issue_query.c.score.desc()).limit(50)
            )
        ).all()
        hybrid_candidates = await _execute_hybrid_search_core(
            session=session,
            caller=caller,
            clean_query=clean_query,
            target_kinds=["issue"],
            project_id=project_id,
            lexical_rows=lex_rows,
        )
        if hybrid_candidates is not None:
            filtered_cands = [
                c
                for c in hybrid_candidates
                if c.kind == "issue"
                and (
                    resolved_proj_identifier is None
                    or (
                        c.project_identifier is not None
                        and c.project_identifier.upper() == resolved_proj_identifier.upper()
                    )
                )
            ]
            if extra_predicates and filtered_cands:
                cand_ids = [c.id for c in filtered_cands]
                filter_stmt = (
                    select(Issue.id)
                    .join(Project, Issue.project_id == Project.id)
                    .join(ObjectRecord, Issue.id == ObjectRecord.id)
                    .outerjoin(WorkflowState, Issue.state_id == WorkflowState.id)
                    .outerjoin(ProjectPriority, Issue.priority_id == ProjectPriority.id)
                    .outerjoin(Workspace, Project.workspace_id == Workspace.id)
                    .where(
                        ObjectRecord.deleted_at.is_(None),
                        ObjectRecord.archived_at.is_(None),
                        Issue.id.in_(cand_ids),
                        *extra_predicates,
                    )
                )
                if project_id is not None:
                    filter_stmt = filter_stmt.where(Issue.project_id == project_id)
                allowed_ids = set((await session.execute(filter_stmt)).scalars().all())
                filtered_cands = [c for c in filtered_cands if c.id in allowed_ids]
            if cursor_score is not None and cursor_id is not None:
                filtered_cands = [
                    c
                    for c in filtered_cands
                    if c.score < cursor_score or (c.score == cursor_score and c.id < cursor_id)
                ]
            total_count = len(filtered_cands)
            has_more = len(filtered_cands) > valid_limit
            hybrid_page_rows = filtered_cands[:valid_limit] if has_more else filtered_cands

            assignees_by_id: dict[uuid.UUID, list[str]] = {}
            if hybrid_page_rows:
                p_ids = [r.id for r in hybrid_page_rows]
                a_stmt = (
                    select(
                        IssueAssignee.issue_id,
                        IssueAssignee.free_text_assignee,
                        Principal.display_name,
                    )
                    .outerjoin(Principal, IssueAssignee.principal_id == Principal.id)
                    .where(IssueAssignee.issue_id.in_(p_ids))
                )
                for a_row in (await session.execute(a_stmt)).all():
                    iss_id, free_text, disp_name = a_row
                    val = free_text or (
                        f"@{disp_name.lower().replace(' ', '')}" if disp_name else None
                    )
                    if val:
                        assignees_by_id.setdefault(iss_id, []).append(val)

            hybrid_items: list[IssueSearchItem] = []
            for cand in hybrid_page_rows:
                body = cand.body_markdown or ""
                snippet_result = build_anchored_snippet(body, clean_query)
                hybrid_items.append(
                    IssueSearchItem(
                        kind="issue",
                        id=cand.id,
                        key=cand.key or "",
                        title=cand.title,
                        summary=cand.summary or cand.title,
                        project_identifier=cand.project_identifier or "",
                        workspace=cand.workspace_slug,
                        anchor=snippet_result.anchor,
                        snippet=snippet_result.snippet,
                        match_spans=snippet_result.match_spans,
                        score=float(cand.score),
                        state=cand.state_name,
                        priority=cand.priority_slug,
                        assignees=assignees_by_id.get(cand.id, []),
                        description_markdown=body,
                        match_reason=cand.match_reason,
                    )
                )

            next_cursor = None
            if has_more and hybrid_page_rows:
                hybrid_last_item = hybrid_page_rows[-1]
                next_cursor = encode_search_cursor(
                    hybrid_last_item.score, hybrid_last_item.id, q_hash
                )

            return IssueSearchResponse(
                total=total_count,
                executed_mode="hybrid",
                items=hybrid_items,
                next_cursor=next_cursor,
            )

    count_stmt = select(func.count()).select_from(issue_query)
    total_count = (await session.execute(count_stmt)).scalar() or 0

    paged_stmt = select(issue_query)
    if cursor_score is not None and cursor_id is not None:
        paged_stmt = paged_stmt.where(
            or_(
                issue_query.c.score < cursor_score,
                and_(issue_query.c.score == cursor_score, issue_query.c.id < cursor_id),
            )
        )

    paged_stmt = paged_stmt.order_by(
        issue_query.c.score.desc(),
        issue_query.c.id.desc(),
    ).limit(valid_limit + 1)

    rows = (await session.execute(paged_stmt)).all()

    has_more = len(rows) > valid_limit
    page_rows = rows[:valid_limit] if has_more else rows

    # Batch fetch assignees for page_rows
    assignees_by_id = {}
    if page_rows:
        p_ids = [r.id for r in page_rows]
        a_stmt = (
            select(IssueAssignee.issue_id, IssueAssignee.free_text_assignee, Principal.display_name)
            .outerjoin(Principal, IssueAssignee.principal_id == Principal.id)
            .where(IssueAssignee.issue_id.in_(p_ids))
        )
        for a_row in (await session.execute(a_stmt)).all():
            iss_id, free_text, disp_name = a_row
            val = free_text or (f"@{disp_name.lower().replace(' ', '')}" if disp_name else None)
            if val:
                assignees_by_id.setdefault(iss_id, []).append(val)

    items = []
    for r in page_rows:
        body = r.body_markdown or ""
        snippet_result = (
            build_anchored_snippet(body, clean_query)
            if clean_query
            else build_anchored_snippet(body, r.title)
        )
        items.append(
            IssueSearchItem(
                kind="issue",
                id=r.id,
                key=str(r.key or ""),
                title=r.title,
                summary=r.summary or r.title,
                project_identifier=str(r.project_identifier or ""),
                workspace=getattr(r, "workspace_slug", None),
                anchor=snippet_result.anchor,
                snippet=snippet_result.snippet,
                match_spans=snippet_result.match_spans,
                score=float(r.score),
                state=getattr(r, "state_name", None),
                priority=getattr(r, "priority_slug", None),
                assignees=assignees_by_id.get(r.id, []),
                description_markdown=body,
                match_reason="Lexical match",
            )
        )

    next_cursor = None
    if has_more and page_rows:
        last_lex_item = page_rows[-1]
        next_cursor = encode_search_cursor(last_lex_item.score, last_lex_item.id, q_hash)

    return IssueSearchResponse(
        total=total_count,
        executed_mode="lexical",
        items=items,
        next_cursor=next_cursor,
    )


async def search_knowledge(  # noqa: C901, PLR0912, PLR0915
    session: AsyncSession,
    caller: PrincipalContext,
    request: KnowledgeSearchRequest,
) -> KnowledgeSearchResponse:
    """Execute knowledge search across docs, pages, and stickies."""
    clean_query = validate_query(request.query)
    valid_limit = validate_limit(request.limit)

    target_kinds = [k.strip().lower() for k in request.kinds if k.strip()]
    valid_kinds_set = {"doc", "page", "sticky"}
    if not target_kinds or not set(target_kinds).issubset(valid_kinds_set):
        raise ProblemException(
            code="INVALID_KIND",
            status=422,
            title="Invalid Knowledge Kinds",
            detail="Knowledge kinds must be a non-empty subset of doc, page, sticky.",
        )

    project_id: uuid.UUID | None = None
    if request.project:
        proj = await get_project_or_404(session, caller, request.project)
        project_id = proj.id

    q_hash = _compute_query_hash(clean_query, target_kinds, request.project)
    cursor_score: float | None = None
    cursor_id: uuid.UUID | None = None
    if request.cursor:
        cursor_score, cursor_id = decode_search_cursor(request.cursor, q_hash)

    queries: list[Select[Any]] = []
    if "doc" in target_kinds:
        queries.append(_build_doc_query(clean_query, project_id))
    if "page" in target_kinds:
        queries.append(_build_page_query(clean_query, project_id))
    if "sticky" in target_kinds:
        queries.append(_build_sticky_query(clean_query, project_id))

    union_stmt = union_all(*queries).subquery("knowledge_results")

    if request.mode == "hybrid":
        lex_rows = (
            await session.execute(select(union_stmt).order_by(union_stmt.c.score.desc()).limit(50))
        ).all()
        hybrid_candidates = await _execute_hybrid_search_core(
            session=session,
            caller=caller,
            clean_query=clean_query,
            target_kinds=target_kinds,
            project_id=project_id,
            lexical_rows=lex_rows,
        )
        if hybrid_candidates is not None:
            filtered_cands = [c for c in hybrid_candidates if c.kind in target_kinds]
            if cursor_score is not None and cursor_id is not None:
                filtered_cands = [
                    c
                    for c in filtered_cands
                    if c.score < cursor_score or (c.score == cursor_score and c.id < cursor_id)
                ]
            total_count = len(filtered_cands)
            has_more = len(filtered_cands) > valid_limit
            hybrid_page_rows = filtered_cands[:valid_limit] if has_more else filtered_cands

            hybrid_items: list[KnowledgeSearchItem] = []
            for cand in hybrid_page_rows:
                body = cand.body_markdown or ""
                snippet_result = build_anchored_snippet(body, clean_query)
                hybrid_items.append(
                    KnowledgeSearchItem(
                        kind=cand.kind,  # type: ignore[arg-type]
                        id=cand.id,
                        key=cand.key,
                        title=cand.title,
                        project_identifier=cand.project_identifier,
                        anchor=snippet_result.anchor,
                        snippet=snippet_result.snippet,
                        match_spans=snippet_result.match_spans,
                        score=float(cand.score),
                        match_reason=cand.match_reason,
                    )
                )

            next_cursor = None
            if has_more and hybrid_page_rows:
                hybrid_last_item = hybrid_page_rows[-1]
                next_cursor = encode_search_cursor(
                    hybrid_last_item.score, hybrid_last_item.id, q_hash
                )

            return KnowledgeSearchResponse(
                total=total_count,
                executed_mode="hybrid",
                items=hybrid_items,
                next_cursor=next_cursor,
            )

    count_stmt = select(func.count()).select_from(union_stmt)
    total_count = (await session.execute(count_stmt)).scalar() or 0

    paged_stmt = select(union_stmt)
    if cursor_score is not None and cursor_id is not None:
        paged_stmt = paged_stmt.where(
            or_(
                union_stmt.c.score < cursor_score,
                and_(union_stmt.c.score == cursor_score, union_stmt.c.id < cursor_id),
            )
        )

    paged_stmt = paged_stmt.order_by(
        union_stmt.c.score.desc(),
        union_stmt.c.id.desc(),
    ).limit(valid_limit + 1)

    rows = (await session.execute(paged_stmt)).all()

    has_more = len(rows) > valid_limit
    page_rows = rows[:valid_limit] if has_more else rows

    items = []
    for r in page_rows:
        body = r.body_markdown or ""
        snippet_result = build_anchored_snippet(body, clean_query)
        items.append(
            KnowledgeSearchItem(
                kind=r.kind,
                id=r.id,
                key=r.key,
                title=r.title,
                project_identifier=r.project_identifier,
                anchor=snippet_result.anchor,
                snippet=snippet_result.snippet,
                match_spans=snippet_result.match_spans,
                score=float(r.score),
                match_reason="Lexical match",
            )
        )

    next_cursor = None
    if has_more and page_rows:
        last_lex_item = page_rows[-1]
        next_cursor = encode_search_cursor(last_lex_item.score, last_lex_item.id, q_hash)

    return KnowledgeSearchResponse(
        total=total_count,
        executed_mode="lexical",
        items=items,
        next_cursor=next_cursor,
    )
