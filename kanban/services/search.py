# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Full-text and trigram lexical search service across issues, docs, pages, and stickies.

Implements S11.2, S11.3, S12.2, and KB-P3-17.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import uuid
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
    union_all,
)

from database.models import (
    Doc,
    Issue,
    ObjectRecord,
    Page,
    Project,
    Sticky,
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
from kanban.services.view_dsl import compile_issue_filter_predicates

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy.ext.asyncio import AsyncSession

    from kanban.api.deps import PrincipalContext

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
) -> Select[Any]:
    """Build issue search query expression."""
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

    match_conditions: list[ColumnElement[bool]] = [Issue.search_tsv.op("@@")(tsq)]
    if len(clean_query) >= _MIN_TRIGRAM_CHARS:
        match_conditions.append(func.word_similarity(clean_query, Issue.summary) >= _SIM_THRESHOLD)
    if key_match:
        match_conditions.append(is_key_match)

    stmt = (
        select(
            literal("issue").label("kind"),
            Issue.id.label("id"),
            (Project.identifier + "-" + cast(Issue.sequence_id, String)).label("key"),
            Issue.summary.label("title"),
            Issue.summary.label("summary"),
            Issue.description_markdown.label("body_markdown"),
            Project.identifier.label("project_identifier"),
            score_expr,
        )
        .join(Project, Issue.project_id == Project.id)
        .join(ObjectRecord, Issue.id == ObjectRecord.id)
        .where(
            ObjectRecord.deleted_at.is_(None),
            ObjectRecord.archived_at.is_(None),
            or_(*match_conditions),
        )
    )

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


def _format_search_items(rows: Sequence[Any], query: str) -> list[SearchItem]:
    """Format unified search item rows with anchored snippets."""
    items: list[SearchItem] = []
    for r in rows:
        body = r.body_markdown or ""
        snippet_result = build_anchored_snippet(body, query)
        items.append(
            SearchItem(
                kind=r.kind,
                id=r.id,
                key=r.key,
                title=r.title,
                summary=r.summary,
                project_identifier=r.project_identifier,
                anchor=snippet_result.anchor,
                snippet=snippet_result.snippet,
                match_spans=snippet_result.match_spans,
                score=float(r.score),
            )
        )
    return items


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
) -> SearchResponse:
    """Execute unified lexical search across issues, docs, pages, and stickies."""
    clean_query = validate_query(query)
    valid_limit = validate_limit(limit)
    target_kinds = _parse_target_kinds(kinds)

    project_id: uuid.UUID | None = None
    if project_ref:
        proj = await get_project_or_404(session, caller, project_ref)
        project_id = proj.id

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
    items = _format_search_items(page_rows, clean_query)

    next_cursor = None
    if has_more and page_rows:
        last_item = page_rows[-1]
        next_cursor = encode_search_cursor(last_item.score, last_item.id, q_hash)

    return SearchResponse(
        total=total_count,
        executed_mode="lexical",
        items=items,
        next_cursor=next_cursor,
    )


async def search_issues(
    session: AsyncSession,
    caller: PrincipalContext,
    request: IssueSearchRequest,
) -> IssueSearchResponse:
    """Execute issue-scoped lexical search composed with FilterSpec DSL predicates."""
    clean_query = validate_query(request.query)
    valid_limit = validate_limit(request.limit)

    project_id: uuid.UUID | None = None
    extra_predicates: list[Any] = []
    if request.project:
        proj = await get_project_or_404(session, caller, request.project)
        project_id = proj.id
        if request.filters:
            extra_predicates = compile_issue_filter_predicates(
                session, proj, request.filters, caller.principal_id
            )

    q_hash = _compute_query_hash(clean_query, ["issue"], request.project)
    cursor_score: float | None = None
    cursor_id: uuid.UUID | None = None
    if request.cursor:
        cursor_score, cursor_id = decode_search_cursor(request.cursor, q_hash)

    key_match_tuple: tuple[str, int] | None = None
    key_match = _ISSUE_KEY_RE.match(clean_query)
    if key_match:
        key_match_tuple = (key_match.group(1).upper(), int(key_match.group(2)))

    issue_query = _build_issue_query(
        clean_query, project_id, key_match_tuple, extra_predicates
    ).subquery("issue_search_results")

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

    items: list[IssueSearchItem] = []
    for r in page_rows:
        body = r.body_markdown or ""
        snippet_result = build_anchored_snippet(body, clean_query)
        items.append(
            IssueSearchItem(
                kind="issue",
                id=r.id,
                key=r.key,
                title=r.title,
                summary=r.summary or r.title,
                project_identifier=r.project_identifier,
                anchor=snippet_result.anchor,
                snippet=snippet_result.snippet,
                match_spans=snippet_result.match_spans,
                score=float(r.score),
            )
        )

    next_cursor = None
    if has_more and page_rows:
        last_item = page_rows[-1]
        next_cursor = encode_search_cursor(last_item.score, last_item.id, q_hash)

    return IssueSearchResponse(
        total=total_count,
        executed_mode="lexical",
        items=items,
        next_cursor=next_cursor,
    )


async def search_knowledge(
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

    items: list[KnowledgeSearchItem] = []
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
            )
        )

    next_cursor = None
    if has_more and page_rows:
        last_item = page_rows[-1]
        next_cursor = encode_search_cursor(last_item.score, last_item.id, q_hash)

    return KnowledgeSearchResponse(
        total=total_count,
        executed_mode="lexical",
        items=items,
        next_cursor=next_cursor,
    )
