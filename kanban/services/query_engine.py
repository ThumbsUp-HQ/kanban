"""2D Swimlane and Filter Query Engine executing inside PostgreSQL FORCE RLS (S6.4, S3.4)."""

from __future__ import annotations

import base64
import datetime as dt
import hashlib
import hmac
import json
import uuid
from typing import TYPE_CHECKING, Any, NamedTuple

from sqlalchemy import desc, func, select

from database.models import (
    Cycle,
    Issue,
    IssueAssignee,
    IssueLabel,
    IssueModule,
    Module,
    ObjectLink,
    Principal,
    Project,
    ProjectLabel,
    ProjectPriority,
    WorkflowState,
)
from kanban.api.problems import ProblemException
from kanban.api.v1.schemas.views import (
    FilterSpec,
    GroupAxis,
    GroupResult,
    SortDir,
    SortField,
    SubGroupResult,
    TimelineLink,
    ViewLayout,
    ViewQueryResponse,
    WipStatus,
)
from kanban.services.issues import serialize_issue
from kanban.services.view_dsl import (
    compile_issue_filter_predicates,
    validate_group_axes,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy.orm import InstrumentedAttribute
    from sqlalchemy.sql.elements import ColumnElement

    from kanban.api.deps import PrincipalContext

_DEFAULT_SIGNING_KEY = "kb-query-engine-signer-v1"


class _IssueContext(NamedTuple):
    labels: set[uuid.UUID]
    assignees: set[uuid.UUID]
    modules: set[uuid.UUID]


def _compute_query_hash(
    project_id: uuid.UUID,
    params: dict[str, Any],
) -> str:
    """Compute deterministic SHA-256 hash of canonical query parameters."""
    canonical_dict = {"project_id": str(project_id), **params}
    canonical_json = json.dumps(canonical_dict, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical_json.encode()).hexdigest()


def encode_query_cursor(
    sort_value: object,
    issue_id: uuid.UUID,
    query_hash: str,
    secret_key: str | None = None,
) -> str:
    """Generate tamper-proof base64url cursor bound to the specific query hash."""
    key = secret_key or _DEFAULT_SIGNING_KEY
    val_str = str(sort_value) if sort_value is not None else ""
    id_str = str(issue_id)
    raw_payload = f"{val_str}|{id_str}|{query_hash}"
    sig = hmac.new(key.encode(), raw_payload.encode(), hashlib.sha256).hexdigest()
    packet = {
        "v": val_str,
        "i": id_str,
        "q": query_hash,
        "s": sig,
    }
    dumped = json.dumps(packet, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(dumped).decode("ascii").rstrip("=")


def _invalid_cursor(detail: str) -> ProblemException:
    """Build canonical 422 INVALID_CURSOR problem exception."""
    return ProblemException(
        code="INVALID_CURSOR",
        status=422,
        title="Invalid Cursor",
        detail=detail,
    )


def decode_query_cursor(
    cursor: str,
    expected_query_hash: str,
    secret_key: str | None = None,
) -> tuple[str, uuid.UUID]:
    """Decode and cryptographically verify query cursor, raising 422 INVALID_CURSOR on mismatch."""
    key = secret_key or _DEFAULT_SIGNING_KEY
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        raw_bytes = base64.urlsafe_b64decode(padded)
        packet = json.loads(raw_bytes.decode())
        val_str = str(packet["v"])
        id_str = str(packet["i"])
        q_hash = str(packet["q"])
        sig = str(packet["s"])
    except (ValueError, KeyError, TypeError) as exc:
        msg = "Cursor payload is malformed"
        raise _invalid_cursor(msg) from exc

    expected_sig = hmac.new(
        key.encode(),
        f"{val_str}|{id_str}|{q_hash}".encode(),
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(sig, expected_sig):
        msg = "Cursor signature verification failed"
        raise _invalid_cursor(msg)
    if q_hash != expected_query_hash:
        msg = "Cursor was issued for a different query"
        raise _invalid_cursor(msg)

    try:
        target_uuid = uuid.UUID(id_str)
    except ValueError as exc:
        msg = "Cursor contains invalid issue identifier"
        raise _invalid_cursor(msg) from exc

    return val_str, target_uuid


def _select_sort_column(
    sort_by: SortField,
) -> InstrumentedAttribute[Any] | ColumnElement[Any]:
    """Select the primary sort column for the issue query."""
    sort_map: dict[SortField, InstrumentedAttribute[Any] | ColumnElement[Any]] = {
        SortField.BOARD_RANK: Issue.board_rank,
        SortField.SEQUENCE_ID: Issue.sequence_id,
        SortField.CREATED_AT: Issue.sequence_id,
        SortField.UPDATED_AT: Issue.sequence_id,
        SortField.DUE_DATE: Issue.due_date,
        SortField.PRIORITY: Issue.priority_id,
    }
    return sort_map.get(sort_by, Issue.board_rank)


def _parse_cursor_val(sort_by: SortField, raw_val: str) -> Any:  # noqa: ANN401
    """Convert stringified cursor value back to its SQL-compatible column type."""
    if sort_by in (SortField.SEQUENCE_ID, SortField.CREATED_AT, SortField.UPDATED_AT):
        try:
            return int(raw_val)
        except ValueError:
            return 0
    if sort_by == SortField.DUE_DATE:
        try:
            return dt.date.fromisoformat(raw_val)
        except ValueError:
            return None
    return raw_val


async def execute_view_query(  # noqa: PLR0913, PLR0917
    session: AsyncSession,
    caller: PrincipalContext,
    project: Project,
    filters: FilterSpec,
    layout: ViewLayout = ViewLayout.BOARD,
    group_by: GroupAxis = GroupAxis.NONE,
    sub_group_by: GroupAxis = GroupAxis.NONE,
    sort_by: SortField = SortField.BOARD_RANK,
    sort_dir: SortDir = SortDir.ASC,
    wip_limits_override: dict[str, Any] | None = None,
    limit: int = 50,
    cursor: str | None = None,
    secret_key: str | None = None,
) -> ViewQueryResponse:
    """Execute parameterized query engine inside PostgreSQL FORCE RLS session."""
    validate_group_axes(project, group_by, sub_group_by, filters)

    predicates = compile_issue_filter_predicates(session, project, filters, caller.principal_id)
    count_stmt = select(func.count(Issue.id)).where(*predicates)
    total_matching: int = (await session.execute(count_stmt)).scalar_one()

    q_hash = _compute_query_hash(
        project.id,
        {
            "filters": filters.model_dump(mode="json"),
            "sort_by": sort_by.value,
            "sort_dir": sort_dir.value,
            "group_by": group_by.value,
            "sub_group_by": sub_group_by.value,
        },
    )

    sort_col = _select_sort_column(sort_by)
    query_predicates = list(predicates)
    if cursor:
        cursor_val, cursor_id = decode_query_cursor(cursor, q_hash, secret_key)
        parsed_val = _parse_cursor_val(sort_by, cursor_val)
        if sort_dir == SortDir.ASC:
            query_predicates.append(
                (sort_col > parsed_val) | ((sort_col == parsed_val) & (Issue.id > cursor_id))
            )
        else:
            query_predicates.append(
                (sort_col < parsed_val) | ((sort_col == parsed_val) & (Issue.id < cursor_id))
            )

    stmt = (
        select(Issue)
        .where(*query_predicates)
        .order_by(
            sort_col if sort_dir == SortDir.ASC else desc(sort_col),
            Issue.id if sort_dir == SortDir.ASC else desc(Issue.id),
        )
        .limit(limit + 1)
    )

    issue_rows = list((await session.execute(stmt)).scalars().all())
    has_more = len(issue_rows) > limit
    page_issues = issue_rows[:limit]

    next_cursor = None
    if has_more and page_issues:
        last_issue = page_issues[-1]
        col_key = getattr(sort_col, "key", "board_rank")
        last_val = getattr(last_issue, col_key, None)
        next_cursor = encode_query_cursor(last_val, last_issue.id, q_hash, secret_key)

    items = [await serialize_issue(session, caller, item) for item in page_issues]
    page_issue_ids = [item.id for item in page_issues]
    id_to_key = {item.id: item.key for item in items}

    timeline_links: list[TimelineLink] = []
    if layout == ViewLayout.TIMELINE and page_issue_ids:
        links_stmt = select(ObjectLink).where(
            ObjectLink.link_type == "BLOCKS",
            ObjectLink.link_state == "ACTIVE",
            ObjectLink.source_id.in_(page_issue_ids),
            ObjectLink.target_id.in_(page_issue_ids),
        )
        for link in (await session.execute(links_stmt)).scalars().all():
            src_key = id_to_key.get(link.source_id)
            tgt_key = id_to_key.get(link.target_id)
            if src_key and tgt_key:
                timeline_links.append(
                    TimelineLink(
                        source_key=src_key,
                        target_key=tgt_key,
                        link_type=link.link_type,
                    )
                )

    groups: list[GroupResult] = []
    if group_by != GroupAxis.NONE:
        groups = await _build_2d_groups(
            session=session,
            project=project,
            matching_issues=page_issues,
            group_by=group_by,
            sub_group_by=sub_group_by,
            wip_limits_override=wip_limits_override or {},
        )

    return ViewQueryResponse(
        items=items,
        groups=groups,
        timeline_links=timeline_links,
        next_cursor=next_cursor,
        total_matching=total_matching,
    )


async def _load_issue_associations(
    session: AsyncSession,
    page_ids: list[uuid.UUID],
    axes: tuple[GroupAxis, GroupAxis],
) -> dict[uuid.UUID, _IssueContext]:
    """Pre-fetch label, assignee, and module associations for the page issues."""
    labels_map: dict[uuid.UUID, set[uuid.UUID]] = {i: set() for i in page_ids}
    assignees_map: dict[uuid.UUID, set[uuid.UUID]] = {i: set() for i in page_ids}
    modules_map: dict[uuid.UUID, set[uuid.UUID]] = {i: set() for i in page_ids}

    if not page_ids:
        return {i: _IssueContext(labels=set(), assignees=set(), modules=set()) for i in page_ids}

    if GroupAxis.LABEL in axes:
        rows = await session.execute(
            select(IssueLabel.issue_id, IssueLabel.label_id).where(
                IssueLabel.issue_id.in_(page_ids)
            )
        )
        for iss_id, lbl_id in rows.all():
            labels_map[iss_id].add(lbl_id)

    if GroupAxis.ASSIGNEE in axes:
        rows = await session.execute(
            select(IssueAssignee.issue_id, IssueAssignee.principal_id).where(
                IssueAssignee.issue_id.in_(page_ids)
            )
        )
        for iss_id, pr_id in rows.all():
            assignees_map[iss_id].add(pr_id)

    if GroupAxis.MODULE in axes:
        rows = await session.execute(
            select(IssueModule.issue_id, IssueModule.module_id).where(
                IssueModule.issue_id.in_(page_ids)
            )
        )
        for iss_id, mod_id in rows.all():
            modules_map[iss_id].add(mod_id)

    return {
        i: _IssueContext(
            labels=labels_map.get(i, set()),
            assignees=assignees_map.get(i, set()),
            modules=modules_map.get(i, set()),
        )
        for i in page_ids
    }


def _issue_matches_bucket(
    issue: Issue,
    axis: GroupAxis,
    bucket_val: object,
    *,
    is_none: bool,
    ctx: _IssueContext,
) -> bool:
    """Evaluate whether an issue belongs to a specific group/sub-group bucket."""
    if axis == GroupAxis.STATE:
        res = issue.state_id == bucket_val
    elif axis == GroupAxis.PRIORITY:
        res = issue.priority_id == bucket_val
    elif axis == GroupAxis.CYCLE:
        res = issue.cycle_id is None if is_none else issue.cycle_id == bucket_val
    elif axis == GroupAxis.ASSIGNEE:
        res = len(ctx.assignees) == 0 if is_none else bucket_val in ctx.assignees
    elif axis == GroupAxis.LABEL:
        res = len(ctx.labels) == 0 if is_none else bucket_val in ctx.labels
    elif axis == GroupAxis.MODULE:
        res = len(ctx.modules) == 0 if is_none else bucket_val in ctx.modules
    else:
        res = True
    return res


async def _build_2d_groups(  # noqa: PLR0913, PLR0917
    session: AsyncSession,
    project: Project,
    matching_issues: list[Issue],
    group_by: GroupAxis,
    sub_group_by: GroupAxis,
    wip_limits_override: dict[str, Any],
) -> list[GroupResult]:
    """Calculate 2D group/sub-group swimlane matrix with WIP status."""
    primary_buckets = await _fetch_axis_buckets(session, project, group_by)
    secondary_buckets = (
        await _fetch_axis_buckets(session, project, sub_group_by)
        if sub_group_by != GroupAxis.NONE
        else []
    )

    page_ids = [iss.id for iss in matching_issues]
    contexts = await _load_issue_associations(session, page_ids, (group_by, sub_group_by))

    results: list[GroupResult] = []
    for p_key, p_label, p_val, p_is_none, default_soft, default_hard in primary_buckets:
        eff_soft = default_soft
        eff_hard = default_hard
        override = wip_limits_override.get(str(p_val)) or wip_limits_override.get(p_key)
        if isinstance(override, dict):
            eff_soft = override.get("soft", default_soft)
            eff_hard = override.get("hard", default_hard)

        group_issues = [
            iss
            for iss in matching_issues
            if _issue_matches_bucket(
                iss,
                group_by,
                p_val,
                is_none=p_is_none,
                ctx=contexts.get(iss.id, _IssueContext(set(), set(), set())),
            )
        ]
        group_count = len(group_issues)

        wip = None
        if eff_soft is not None or eff_hard is not None:
            exceeded = None
            if eff_hard is not None and group_count > eff_hard:
                exceeded = "hard"
            elif eff_soft is not None and group_count > eff_soft:
                exceeded = "soft"
            wip = WipStatus(soft=eff_soft, hard=eff_hard, exceeded=exceeded)

        sub_group_results: list[SubGroupResult] = []
        if secondary_buckets:
            for s_key, s_label, s_val, s_is_none, _, _ in secondary_buckets:
                sub_issues = [
                    iss
                    for iss in group_issues
                    if _issue_matches_bucket(
                        iss,
                        sub_group_by,
                        s_val,
                        is_none=s_is_none,
                        ctx=contexts.get(iss.id, _IssueContext(set(), set(), set())),
                    )
                ]
                sub_ids = [iss.id for iss in sub_issues]
                sub_group_results.append(
                    SubGroupResult(
                        sub_group_key=s_key,
                        key=s_key,
                        label=s_label,
                        count=len(sub_ids),
                        issue_ids=sub_ids,
                        items=sub_ids,
                    )
                )

        results.append(
            GroupResult(
                group_key=p_key,
                key=p_key,
                label=p_label,
                count=group_count,
                wip=wip,
                sub_groups=sub_group_results,
            )
        )

    return results


async def _fetch_state_buckets(
    session: AsyncSession, project_id: uuid.UUID
) -> list[tuple[str, str, Any, bool, int | None, int | None]]:
    """Fetch workflow state buckets."""
    rows = (
        (
            await session.execute(
                select(WorkflowState)
                .where(WorkflowState.project_id == project_id)
                .order_by(WorkflowState.sort_order)
            )
        )
        .scalars()
        .all()
    )
    return [
        (f"state:{st.id}", st.name, st.id, False, st.wip_soft_limit, st.wip_hard_limit)
        for st in rows
    ]


async def _fetch_priority_buckets(
    session: AsyncSession, project_id: uuid.UUID
) -> list[tuple[str, str, Any, bool, int | None, int | None]]:
    """Fetch priority buckets."""
    rows = (
        (
            await session.execute(
                select(ProjectPriority)
                .where(ProjectPriority.project_id == project_id)
                .order_by(ProjectPriority.sort_order)
            )
        )
        .scalars()
        .all()
    )
    return [(f"priority:{pr.id}", pr.label, pr.id, False, None, None) for pr in rows]


async def _fetch_cycle_buckets(
    session: AsyncSession, project_id: uuid.UUID
) -> list[tuple[str, str, Any, bool, int | None, int | None]]:
    """Fetch cycle buckets."""
    rows = (
        (
            await session.execute(
                select(Cycle).where(Cycle.project_id == project_id).order_by(Cycle.start_date)
            )
        )
        .scalars()
        .all()
    )
    buckets: list[tuple[str, str, Any, bool, int | None, int | None]] = [
        (f"cycle:{cy.id}", cy.name, cy.id, False, None, None) for cy in rows
    ]
    buckets.append(("cycle:none", "No Cycle", None, True, None, None))
    return buckets


async def _fetch_label_buckets(
    session: AsyncSession, project_id: uuid.UUID
) -> list[tuple[str, str, Any, bool, int | None, int | None]]:
    """Fetch label buckets."""
    rows = (
        (
            await session.execute(
                select(ProjectLabel)
                .where(ProjectLabel.project_id == project_id)
                .order_by(ProjectLabel.name)
            )
        )
        .scalars()
        .all()
    )
    buckets: list[tuple[str, str, Any, bool, int | None, int | None]] = [
        (f"label:{lbl.id}", lbl.name, lbl.id, False, None, None) for lbl in rows
    ]
    buckets.append(("label:none", "No Label", None, True, None, None))
    return buckets


async def _fetch_module_buckets(
    session: AsyncSession, project: Project
) -> list[tuple[str, str, Any, bool, int | None, int | None]]:
    """Fetch module buckets."""
    buckets: list[tuple[str, str, Any, bool, int | None, int | None]] = []
    if project.modules_enabled:
        rows = (
            (
                await session.execute(
                    select(Module).where(Module.project_id == project.id).order_by(Module.name)
                )
            )
            .scalars()
            .all()
        )
        buckets.extend((f"module:{mod.id}", mod.name, mod.id, False, None, None) for mod in rows)
    buckets.append(("module:none", "No Module", None, True, None, None))
    return buckets


async def _fetch_assignee_buckets(
    session: AsyncSession, workspace_id: uuid.UUID
) -> list[tuple[str, str, Any, bool, int | None, int | None]]:
    """Fetch assignee buckets."""
    rows = (
        (
            await session.execute(
                select(Principal)
                .where(Principal.workspace_id == workspace_id)
                .order_by(Principal.display_name)
            )
        )
        .scalars()
        .all()
    )
    buckets: list[tuple[str, str, Any, bool, int | None, int | None]] = [
        (f"assignee:{pr.id}", pr.display_name, pr.id, False, None, None) for pr in rows
    ]
    buckets.append(("assignee:unassigned", "Unassigned", None, True, None, None))
    return buckets


async def _fetch_axis_buckets(
    session: AsyncSession,
    project: Project,
    axis: GroupAxis,
) -> list[tuple[str, str, Any, bool, int | None, int | None]]:
    """Fetch all possible buckets for a given grouping axis."""
    fetch_map = {
        GroupAxis.STATE: lambda: _fetch_state_buckets(session, project.id),
        GroupAxis.PRIORITY: lambda: _fetch_priority_buckets(session, project.id),
        GroupAxis.CYCLE: lambda: _fetch_cycle_buckets(session, project.id),
        GroupAxis.LABEL: lambda: _fetch_label_buckets(session, project.id),
        GroupAxis.MODULE: lambda: _fetch_module_buckets(session, project),
        GroupAxis.ASSIGNEE: lambda: _fetch_assignee_buckets(session, project.workspace_id),
    }
    fetcher = fetch_map.get(axis)
    if fetcher:
        return await fetcher()
    return []
