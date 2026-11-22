# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Tree creation service and DAG validation for hierarchical issue trees (KB-P4-05)."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any, Final

from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError, IntegrityError

from database.models.base import LinkKind, ObjectKind
from database.models.issues import Issue, IssueAssignee, IssueLabel, IssueModule
from database.models.principals import Principal, User
from database.models.projects import (
    Cycle,
    Module,
    Project,
    ProjectLabel,
    ProjectModuleDefault,
    ProjectPriority,
    WorkflowState,
)
from database.models.spine import ObjectLink, ObjectRecord
from kanban.api.problems import ProblemException
from kanban.api.v1.schemas.issue_trees import (
    IssueTreeChildSummary,
    IssueTreeNode,
    IssueTreeResponse,
    IssueTreeRootSummary,
)
from kanban.content import (
    ContentNormalizeError,
    normalize_plain_text,
    normalize_to_markdown,
)
from kanban.security.permissions import Capability, require_capability
from kanban.security.push_protection import enforce_secret_push_protection
from kanban.services.activity import ActivityEventType, record_activity
from kanban.services.board_rank import allocate_initial_board_rank
from kanban.services.projects import get_project_or_404

if TYPE_CHECKING:
    from datetime import date

    from sqlalchemy.ext.asyncio import AsyncSession

    from kanban.api.deps import PrincipalContext

MAX_NODES_PER_CALL: Final[int] = 50
MAX_HIERARCHY_DEPTH: Final[int] = 6
MAX_SUMMARY_LENGTH: Final[int] = 500
MAX_DESCRIPTION_BYTES: Final[int] = 1048576
MAX_ASSIGNEES_PER_NODE: Final[int] = 20
MAX_FREE_TEXT_ASSIGNEES: Final[int] = 10
MIN_FREE_TEXT_LENGTH: Final[int] = 1
MAX_FREE_TEXT_LENGTH: Final[int] = 120


def count_nodes(node: IssueTreeNode) -> int:
    """Recursively compute the total number of issues represented by the tree."""
    return 1 + sum(count_nodes(child) for child in node.children)


def get_tree_height(node: IssueTreeNode) -> int:
    """Recursively compute the maximum height of the given issue tree."""
    if not node.children:
        return 1
    return 1 + max(get_tree_height(child) for child in node.children)


def _normalize_summary(raw: str) -> str:
    """Normalize summary to plain text and enforce 1..500 characters constraint."""
    try:
        normalized = normalize_plain_text(raw)
    except (ContentNormalizeError, UnicodeEncodeError) as exc:
        raise ProblemException(
            code="INVALID_CONTENT",
            status=422,
            title="Invalid Content",
            detail="Summary contains invalid content",
            field="summary",
        ) from exc

    cleaned = normalized.strip()
    if len(cleaned) < 1 or len(cleaned) > MAX_SUMMARY_LENGTH:
        raise ProblemException(
            code="SUMMARY_LENGTH",
            status=422,
            title="Summary Length",
            detail="Summary must be between 1 and 500 characters",
            field="summary",
        )
    return cleaned


def _normalize_description(raw: str) -> str:
    """Normalize description to canonical Markdown and enforce 1 MiB byte cap."""
    try:
        normalized = normalize_to_markdown(raw)
    except ContentNormalizeError as exc:
        if exc.code == "CONTENT_TOO_LARGE":
            raise ProblemException(
                code="DESCRIPTION_TOO_LARGE",
                status=422,
                title="Description Too Large",
                detail="Description exceeds 1,048,576 bytes",
            ) from exc
        raise ProblemException(
            code="INVALID_CONTENT",
            status=422,
            title="Invalid Content",
            detail="Description contains invalid content",
        ) from exc
    except UnicodeEncodeError as exc:
        raise ProblemException(
            code="INVALID_CONTENT",
            status=422,
            title="Invalid Content",
            detail="Description contains invalid content",
        ) from exc

    if len(normalized.encode("utf-8")) > MAX_DESCRIPTION_BYTES:
        raise ProblemException(
            code="DESCRIPTION_TOO_LARGE",
            status=422,
            title="Description Too Large",
            detail="Description exceeds 1,048,576 bytes",
        )
    return normalized


def _validate_dates(start_date: date | None, due_date: date | None) -> None:
    """Enforce due_date >= start_date constraint."""
    if start_date is not None and due_date is not None and due_date < start_date:
        raise ProblemException(
            code="DATE_ORDER",
            status=422,
            title="Invalid Date Order",
            detail="due_date cannot be earlier than start_date",
        )


def _handle_parent_dag_error(exc: Exception) -> None:
    """Map PostgreSQL parent trigger errors to canonical RFC 7807 problem exceptions."""
    msg = str(exc)
    if "PARENT_CYCLE" in msg or "PARENT_SELF_REFERENCE" in msg:
        raise ProblemException(
            code="PARENT_CYCLE",
            status=422,
            title="Parent Cycle",
            detail="Setting parent would create a cycle in the issue hierarchy",
            field="parent",
        ) from exc
    if "PARENT_MAX_DEPTH_EXCEEDED" in msg or "issues_ancestry_depth_chk" in msg:
        raise ProblemException(
            code="PARENT_DEPTH_EXCEEDED",
            status=422,
            title="Parent Depth Exceeded",
            detail="Maximum issue hierarchy depth (6 levels) exceeded",
            field="parent",
        ) from exc
    if "PARENT_NOT_FOUND" in msg or "PARENT_CROSS_PROJECT" in msg:
        raise ProblemException(
            code="INVALID_REFERENCE",
            status=422,
            title="Invalid Reference",
            detail="Parent issue does not exist or belongs to another project",
            field="parent",
        ) from exc


async def _resolve_parent(
    session: AsyncSession,
    caller: PrincipalContext,
    project: Project,
    parent_ref: str | uuid.UUID,
) -> Issue:
    """Resolve an existing parent issue within the current project and workspace."""
    stmt = (
        select(Issue)
        .join(ObjectRecord, ObjectRecord.id == Issue.id)
        .where(
            Issue.workspace_id == caller.workspace_id,
            Issue.project_id == project.id,
            ObjectRecord.deleted_at.is_(None),
        )
    )

    if isinstance(parent_ref, uuid.UUID):
        stmt = stmt.where(Issue.id == parent_ref)
    else:
        raw_str = str(parent_ref).strip()
        try:
            p_uuid = uuid.UUID(raw_str)
            stmt = stmt.where(Issue.id == p_uuid)
        except ValueError:
            if "-" in raw_str:
                ident, seq_str = raw_str.rsplit("-", 1)
                if ident != project.identifier:
                    raise ProblemException(
                        code="INVALID_REFERENCE",
                        status=422,
                        title="Invalid Reference",
                        detail="Parent issue belongs to another project",
                        field="parent",
                    ) from None
                try:
                    stmt = stmt.where(Issue.sequence_id == int(seq_str))
                except ValueError:
                    raise ProblemException(
                        code="INVALID_REFERENCE",
                        status=422,
                        title="Invalid Reference",
                        detail="Invalid sequence ID format in parent reference",
                        field="parent",
                    ) from None
            else:
                raise ProblemException(
                    code="INVALID_REFERENCE",
                    status=422,
                    title="Invalid Reference",
                    detail="Invalid parent reference format",
                    field="parent",
                ) from None

    parent_issue = (await session.execute(stmt)).scalar_one_or_none()
    if parent_issue is None:
        raise ProblemException(
            code="INVALID_REFERENCE",
            status=422,
            title="Invalid Reference",
            detail="Parent issue does not exist or is not readable",
            field="parent",
        )
    return parent_issue


def _traverse_all_nodes(root: IssueTreeNode) -> list[IssueTreeNode]:
    """Collect all nodes in breadth-first traversal order."""
    nodes: list[IssueTreeNode] = []
    queue: list[IssueTreeNode] = [root]
    while queue:
        curr = queue.pop(0)
        nodes.append(curr)
        queue.extend(curr.children)
    return nodes


def _resolve_single_label(
    item: str | uuid.UUID,
    labels_by_name: dict[str, ProjectLabel],
    labels_by_id: dict[uuid.UUID, ProjectLabel],
) -> ProjectLabel:
    """Resolve a single label reference by UUID or name."""
    if isinstance(item, uuid.UUID):
        if item in labels_by_id:
            return labels_by_id[item]
        raise ProblemException(
            code="INVALID_REFERENCE",
            status=422,
            title="Invalid Reference",
            detail=f"Label UUID '{item}' not found in project",
            field="labels",
        )
    clean = str(item).strip().lower()
    if clean in labels_by_name:
        return labels_by_name[clean]
    try:
        u = uuid.UUID(clean)
        if u in labels_by_id:
            return labels_by_id[u]
    except ValueError:
        pass
    raise ProblemException(
        code="INVALID_REFERENCE",
        status=422,
        title="Invalid Reference",
        detail=f"Label '{item}' not found in project",
        field="labels",
    )


async def create_issue_tree(  # noqa: C901, PLR0912, PLR0915
    session: AsyncSession,
    caller: PrincipalContext,
    project_ref: str,
    tree: IssueTreeNode,
) -> IssueTreeResponse:
    """Create an issue tree hierarchy atomically inside a single database transaction."""
    project = await get_project_or_404(session, caller, project_ref)
    await require_capability(session, caller, project.id, Capability.EDIT)

    total_nodes = count_nodes(tree)
    if total_nodes > MAX_NODES_PER_CALL:
        raise ProblemException(
            code="TREE_TOO_LARGE",
            status=422,
            title="Tree Too Large",
            detail=f"Total nodes per call ({total_nodes}) cannot exceed {MAX_NODES_PER_CALL}",
        )

    parent_issue: Issue | None = None
    parent_depth = 0
    if tree.parent is not None:
        parent_issue = await _resolve_parent(session, caller, project, tree.parent)
        ancestry = parent_issue.ancestry_path or ""
        parent_depth = len(ancestry.split(".")) if ancestry else 1

    tree_height = get_tree_height(tree)
    if parent_depth + tree_height > MAX_HIERARCHY_DEPTH:
        raise ProblemException(
            code="PARENT_DEPTH_EXCEEDED",
            status=422,
            title="Parent Depth Exceeded",
            detail=f"Maximum issue hierarchy depth ({MAX_HIERARCHY_DEPTH} levels) exceeded",
            field="parent",
        )

    all_nodes = _traverse_all_nodes(tree)
    for node in all_nodes:
        enforce_secret_push_protection(node.summary, field="summary")
        enforce_secret_push_protection(node.description_markdown, field="description_markdown")

    # 1. Modules validation
    if not project.modules_enabled:
        for node in all_nodes:
            if node.modules is not None and len(node.modules) > 0:
                raise ProblemException(
                    code="MODULES_DISABLED",
                    status=422,
                    title="Modules Disabled",
                    detail="Modules are disabled for this project",
                )

    project_default_module_ids: list[uuid.UUID] = []
    if project.modules_enabled:
        project_default_module_ids = list(
            (
                await session.execute(
                    select(ProjectModuleDefault.module_id)
                    .where(ProjectModuleDefault.project_id == project.id)
                    .order_by(ProjectModuleDefault.module_id)
                )
            )
            .scalars()
            .all()
        )

    # Pre-fetch project workflow states
    states = (
        (await session.execute(select(WorkflowState).where(WorkflowState.project_id == project.id)))
        .scalars()
        .all()
    )
    default_state = next((s for s in states if s.is_default), states[0] if states else None)
    if default_state is None:
        raise ProblemException(
            code="INVALID_STATE",
            status=422,
            title="Invalid State",
            detail="No workflow states configured for project",
        )
    states_by_name = {s.name.lower(): s for s in states}
    states_by_id = {s.id: s for s in states}

    # Pre-fetch project priorities
    priorities = (
        (
            await session.execute(
                select(ProjectPriority).where(ProjectPriority.project_id == project.id)
            )
        )
        .scalars()
        .all()
    )
    default_priority = next(
        (p for p in priorities if p.is_default), priorities[0] if priorities else None
    )
    if default_priority is None:
        raise ProblemException(
            code="INVALID_PRIORITY",
            status=422,
            title="Invalid Priority",
            detail="No priorities configured for project",
        )
    pri_by_slug = {p.slug.lower(): p for p in priorities}
    pri_by_id = {p.id: p for p in priorities}

    # Pre-fetch project labels
    labels = (
        (await session.execute(select(ProjectLabel).where(ProjectLabel.project_id == project.id)))
        .scalars()
        .all()
    )
    labels_by_name = {lbl.name.lower(): lbl for lbl in labels}
    labels_by_id = {lbl.id: lbl for lbl in labels}

    # Pre-fetch project modules if enabled
    modules = (
        (await session.execute(select(Module).where(Module.project_id == project.id)))
        .scalars()
        .all()
        if project.modules_enabled
        else []
    )
    modules_by_name = {m.name.lower(): m for m in modules}
    modules_by_id = {m.id: m for m in modules}

    # Pre-fetch project cycles
    cycles = (
        (await session.execute(select(Cycle).where(Cycle.project_id == project.id))).scalars().all()
    )
    cycles_by_name = {c.name.lower(): c for c in cycles}
    cycles_by_id = {c.id: c for c in cycles}

    # Helper to resolve state
    def resolve_node_state(val: str | uuid.UUID | None) -> WorkflowState:
        if val is None:
            return default_state
        if isinstance(val, uuid.UUID):
            if val in states_by_id:
                return states_by_id[val]
            raise ProblemException(
                code="INVALID_REFERENCE",
                status=422,
                title="Invalid Reference",
                detail=f"Workflow state UUID '{val}' not found in project",
                field="state",
            )
        clean = str(val).strip().lower()
        if clean in states_by_name:
            return states_by_name[clean]
        try:
            u = uuid.UUID(clean)
            if u in states_by_id:
                return states_by_id[u]
        except ValueError:
            pass
        raise ProblemException(
            code="INVALID_REFERENCE",
            status=422,
            title="Invalid Reference",
            detail=f"Workflow state '{val}' not found in project",
            field="state",
        )

    # Helper to resolve priority
    def resolve_node_priority(val: str | uuid.UUID | None) -> ProjectPriority:
        if val is None:
            return default_priority
        if isinstance(val, uuid.UUID):
            if val in pri_by_id:
                return pri_by_id[val]
            raise ProblemException(
                code="INVALID_REFERENCE",
                status=422,
                title="Invalid Reference",
                detail=f"Priority UUID '{val}' not found in project",
                field="priority",
            )
        clean = str(val).strip().lower()
        if clean in pri_by_slug:
            return pri_by_slug[clean]
        try:
            u = uuid.UUID(clean)
            if u in pri_by_id:
                return pri_by_id[u]
        except ValueError:
            pass
        raise ProblemException(
            code="INVALID_REFERENCE",
            status=422,
            title="Invalid Reference",
            detail=f"Priority '{val}' not found in project",
            field="priority",
        )

    # Helper to resolve cycle
    def resolve_node_cycle(val: str | uuid.UUID | None) -> uuid.UUID | None:
        if val is None:
            return None
        if isinstance(val, uuid.UUID):
            if val in cycles_by_id:
                return val
            raise ProblemException(
                code="INVALID_REFERENCE",
                status=422,
                title="Invalid Reference",
                detail=f"Cycle UUID '{val}' not found in project",
                field="cycle",
            )
        clean = str(val).strip().lower()
        if clean in cycles_by_name:
            return cycles_by_name[clean].id
        try:
            u = uuid.UUID(clean)
            if u in cycles_by_id:
                return u
        except ValueError:
            pass
        raise ProblemException(
            code="INVALID_REFERENCE",
            status=422,
            title="Invalid Reference",
            detail=f"Cycle '{val}' not found in project",
            field="cycle",
        )

    # Helper to resolve modules
    def resolve_node_modules(val: list[str | uuid.UUID] | None) -> list[uuid.UUID]:
        if not project.modules_enabled:
            return []
        if val is None:
            return list(project_default_module_ids)
        resolved: list[uuid.UUID] = []
        for item in val:
            if isinstance(item, uuid.UUID):
                if item in modules_by_id:
                    resolved.append(item)
                else:
                    raise ProblemException(
                        code="INVALID_REFERENCE",
                        status=422,
                        title="Invalid Reference",
                        detail=f"Module UUID '{item}' not found in project",
                        field="modules",
                    )
            else:
                clean = str(item).strip().lower()
                if clean in modules_by_name:
                    resolved.append(modules_by_name[clean].id)
                else:
                    try:
                        u = uuid.UUID(clean)
                        if u in modules_by_id:
                            resolved.append(u)
                            continue
                    except ValueError:
                        pass
                    raise ProblemException(
                        code="INVALID_REFERENCE",
                        status=422,
                        title="Invalid Reference",
                        detail=f"Module '{item}' not found in project",
                        field="modules",
                    )
        return list(dict.fromkeys(resolved))

    # Helper to resolve labels
    def resolve_node_labels(val: list[str | uuid.UUID]) -> list[uuid.UUID]:
        if not val:
            return []
        resolved_objs = [_resolve_single_label(item, labels_by_name, labels_by_id) for item in val]
        groups_seen: set[str] = set()
        for lbl in resolved_objs:
            if lbl.exclusive_group:
                if lbl.exclusive_group in groups_seen:
                    raise ProblemException(
                        code="EXCLUSIVE_GROUP_CONFLICT",
                        status=422,
                        title="Exclusive Group Conflict",
                        detail=f"Multiple labels share exclusive group '{lbl.exclusive_group}'",
                    )
                groups_seen.add(lbl.exclusive_group)
        return [lbl.id for lbl in resolved_objs]

    # Pre-validate all node fields (dates, summary bounds, assignees) before DB execution
    resolved_nodes_data: list[dict[str, Any]] = []
    for node in all_nodes:
        _validate_dates(node.start_date, node.due_date)
        clean_summary = _normalize_summary(node.summary)
        clean_desc = _normalize_description(node.description_markdown or "")
        st = resolve_node_state(node.state)
        pr = resolve_node_priority(node.priority)
        cy = resolve_node_cycle(node.cycle)
        mods = resolve_node_modules(node.modules)
        lbls = resolve_node_labels(node.labels)

        # Validate and resolve assignees
        if len(node.assignees) > MAX_ASSIGNEES_PER_NODE:
            raise ProblemException(
                code="ASSIGNEE_LIMIT",
                status=422,
                title="Assignee Limit Exceeded",
                detail=f"Issue cannot have more than {MAX_ASSIGNEES_PER_NODE} assignees",
            )

        resolved_principals: list[uuid.UUID] = []
        resolved_free_text: list[str] = []

        for raw_a in node.assignees:
            a_str = str(raw_a).strip()
            clean_handle = a_str.lstrip("@")
            found_user_id: uuid.UUID | None = None

            # 1. Try UUID lookup
            try:
                u_candidate = uuid.UUID(a_str)
                p_row = (
                    await session.execute(
                        select(Principal.id).where(
                            Principal.id == u_candidate,
                            Principal.workspace_id == caller.workspace_id,
                            Principal.status == "ACTIVE",
                        )
                    )
                ).scalar_one_or_none()
                if p_row is not None:
                    found_user_id = p_row
            except ValueError:
                pass

            # 2. Try User & Principal lookup (bypasses object-level RLS, safe across workspace)
            if found_user_id is None:
                compact_name = func.lower(func.replace(Principal.display_name, " ", ""))
                p_user = (
                    (
                        await session.execute(
                            select(Principal.id)
                            .join(User, User.id == Principal.id)
                            .where(
                                Principal.workspace_id == caller.workspace_id,
                                Principal.status == "ACTIVE",
                                (
                                    (compact_name == clean_handle.lower())
                                    | (func.lower(Principal.display_name) == clean_handle.lower())
                                    | (func.lower(User.email) == a_str.lower())
                                    | (
                                        func.lower(User.email)
                                        == f"{clean_handle.lower()}@example.com"
                                    )
                                    | (
                                        func.split_part(func.lower(User.email), "@", 1)
                                        == clean_handle.lower()
                                    )
                                ),
                            )
                        )
                    )
                    .scalars()
                    .first()
                )
                if p_user is not None:
                    found_user_id = p_user

            # 3. If string started with '@' or user exists: check access
            if found_user_id is not None or a_str.startswith("@"):
                if found_user_id is None:
                    # Explicit handle that does not exist in workspace
                    msg_ineligible = (
                        f"The specified principal '{a_str}' is not eligible "
                        "for assignment in this project"
                    )
                    raise ProblemException(
                        code="ASSIGNEE_NOT_ELIGIBLE",
                        status=422,
                        title="Assignee Not Eligible",
                        detail=msg_ineligible,
                        extra={"hint": a_str},
                    )

                # Check effective_resource_access for project VIEW capability
                era_row = (
                    await session.execute(
                        text(
                            "SELECT allow_mask, deny_mask FROM effective_resource_access "
                            "WHERE object_id = :project_id "
                            "  AND principal_id = :principal_id "
                            "  AND workspace_id = :workspace_id "
                        ),
                        {
                            "project_id": project.id,
                            "principal_id": found_user_id,
                            "workspace_id": caller.workspace_id,
                        },
                    )
                ).first()
                has_view = False
                if era_row is not None and (era_row[0] & 1) == 1 and (era_row[1] & 1) == 0:
                    has_view = True
                if not has_view:
                    rb_count = (
                        await session.execute(
                            text(
                                "SELECT count(*) FROM role_bindings "
                                "WHERE principal_id = :principal_id "
                                "  AND workspace_id = :workspace_id "
                                "  AND ("
                                "    (scope_type = 'workspace' AND "
                                "     role IN ('WORKSPACE_ADMIN', 'WORKSPACE_MEMBER')) "
                                "    OR (scope_type = 'project' AND project_id = :project_id)"
                                "  )"
                            ),
                            {
                                "project_id": project.id,
                                "principal_id": found_user_id,
                                "workspace_id": caller.workspace_id,
                            },
                        )
                    ).scalar() or 0
                    if rb_count > 0:
                        has_view = True

                if not has_view:
                    msg_ineligible = (
                        f"The specified principal '{a_str}' is not eligible "
                        "for assignment in this project"
                    )
                    raise ProblemException(
                        code="ASSIGNEE_NOT_ELIGIBLE",
                        status=422,
                        title="Assignee Not Eligible",
                        detail=msg_ineligible,
                        extra={"hint": a_str},
                    )
                resolved_principals.append(found_user_id)
            else:
                # Free-text assignee
                ft_clean = normalize_plain_text(a_str).strip()
                if not (MIN_FREE_TEXT_LENGTH <= len(ft_clean) <= MAX_FREE_TEXT_LENGTH):
                    msg_ft = (
                        f"Free text assignee must be between {MIN_FREE_TEXT_LENGTH} "
                        f"and {MAX_FREE_TEXT_LENGTH} characters"
                    )
                    raise ProblemException(
                        code="FREE_TEXT_INVALID",
                        status=422,
                        title="Invalid Free Text",
                        detail=msg_ft,
                    )
                resolved_free_text.append(ft_clean)

        if len(resolved_free_text) > MAX_FREE_TEXT_ASSIGNEES:
            raise ProblemException(
                code="ASSIGNEE_LIMIT",
                status=422,
                title="Assignee Limit Exceeded",
                detail=f"Issue cannot have more than {MAX_FREE_TEXT_ASSIGNEES} free-text assignees",
            )

        resolved_nodes_data.append(
            {
                "node": node,
                "summary": clean_summary,
                "description": clean_desc,
                "state": st,
                "priority": pr,
                "cycle_id": cy,
                "module_ids": mods,
                "label_ids": lbls,
                "principals": resolved_principals,
                "free_texts": resolved_free_text,
            }
        )

    # Map node objects to resolved data
    node_to_data = {id(item["node"]): item for item in resolved_nodes_data}

    # Now execute inside nested transaction with atomic rollback on failure
    root_summary_res: IssueTreeRootSummary | None = None
    children_summaries: list[IssueTreeChildSummary] = []
    created_count = 0

    try:
        async with session.begin_nested():
            # Queue holds: (node, parent_id, parent_key)
            initial_parent_id: uuid.UUID | None = parent_issue.id if parent_issue else None
            initial_parent_key: str | None = (
                f"{project.identifier}-{parent_issue.sequence_id}" if parent_issue else None
            )

            queue: list[tuple[IssueTreeNode, uuid.UUID | None, str | None, bool]] = [
                (tree, initial_parent_id, initial_parent_key, True)
            ]

            total_nodes = len(resolved_nodes_data)
            seq_row = (
                await session.execute(
                    text(
                        "SELECT allocated_sequences, skipped_sequences "
                        "FROM allocate_issue_sequences(:proj, :count, false)"
                    ),
                    {"proj": project.id, "count": total_nodes},
                )
            ).one()
            allocated_seqs: list[int] = list(seq_row[0])
            skipped_seqs: list[int] = list(seq_row[1])

            if skipped_seqs:
                await record_activity(
                    session,
                    workspace_id=caller.workspace_id,
                    object_id=project.id,
                    actor_principal_id=caller.principal_id,
                    event_type=ActivityEventType.SEQUENCE_SKIPPED,
                    payload={
                        "project_key": project.identifier,
                        "skipped_sequences": skipped_seqs,
                        "allocated_sequence": allocated_seqs[0],
                        "reason": "agent_safe_sequence_numbering",
                    },
                )

            seq_idx = 0
            while queue:
                curr_node, curr_parent_id, curr_parent_key, is_root = queue.pop(0)
                data = node_to_data[id(curr_node)]

                seq_id = allocated_seqs[seq_idx]
                seq_idx += 1

                canonical_key = f"{project.identifier}-{seq_id}"
                board_rank = allocate_initial_board_rank(seq_id)

                issue_id = (
                    await session.execute(
                        text(
                            "SELECT register_object("
                            "  CAST('issue' AS object_kind), :ws, :proj, :key, :title, :creator"
                            ")"
                        ),
                        {
                            "ws": caller.workspace_id,
                            "proj": project.id,
                            "key": canonical_key,
                            "title": data["summary"],
                            "creator": caller.principal_id,
                        },
                    )
                ).scalar_one()

                issue = Issue(
                    id=issue_id,
                    workspace_id=caller.workspace_id,
                    project_id=project.id,
                    sequence_id=seq_id,
                    summary=data["summary"],
                    description_markdown=data["description"],
                    state_id=data["state"].id,
                    priority_id=data["priority"].id,
                    created_by_id=caller.principal_id,
                    original_created_by_id=caller.principal_id,
                    start_date=curr_node.start_date,
                    due_date=curr_node.due_date,
                    cycle_id=data["cycle_id"],
                    parent_issue_id=curr_parent_id,
                    board_rank=board_rank,
                    ancestry_path=issue_id.hex,
                )
                session.add(issue)
                await session.flush()

                # Insert modules if explicitly specified
                if curr_node.modules is not None:
                    await session.execute(
                        text("DELETE FROM issue_modules WHERE issue_id = :iss"),
                        {"iss": issue_id},
                    )
                    for mid in data["module_ids"]:
                        session.add(
                            IssueModule(
                                issue_id=issue_id,
                                module_id=mid,
                                workspace_id=caller.workspace_id,
                            )
                        )

                # Insert labels
                for lid in data["label_ids"]:
                    session.add(
                        IssueLabel(
                            issue_id=issue_id,
                            label_id=lid,
                            workspace_id=caller.workspace_id,
                        )
                    )

                # Insert assignees
                for p_id in data["principals"]:
                    session.add(
                        IssueAssignee(
                            workspace_id=caller.workspace_id,
                            issue_id=issue_id,
                            principal_id=p_id,
                        )
                    )
                for ft in data["free_texts"]:
                    session.add(
                        IssueAssignee(
                            workspace_id=caller.workspace_id,
                            issue_id=issue_id,
                            free_text_assignee=ft,
                        )
                    )

                # Insert PARENT_OF link if issue has parent
                if curr_parent_id is not None and curr_parent_key is not None:
                    link = ObjectLink(
                        workspace_id=caller.workspace_id,
                        source_id=curr_parent_id,
                        source_type=ObjectKind.ISSUE,
                        target_id=issue_id,
                        target_type=ObjectKind.ISSUE,
                        link_type=LinkKind.PARENT_OF,
                        link_state="ACTIVE",
                        source_key_snapshot=curr_parent_key,
                        target_key_snapshot=canonical_key,
                        created_by_id=caller.principal_id,
                    )
                    session.add(link)

                await session.flush()

                # Activity
                await record_activity(
                    session,
                    workspace_id=caller.workspace_id,
                    object_id=issue_id,
                    actor_principal_id=caller.principal_id,
                    event_type=ActivityEventType.ISSUE_CREATED,
                    payload={"key": canonical_key, "copied_from": None},
                )

                created_count += 1

                if is_root:
                    root_summary_res = IssueTreeRootSummary(
                        id=issue_id,
                        key=canonical_key,
                        summary=data["summary"],
                        state=data["state"].name,
                        priority=data["priority"].slug,
                        parent=curr_parent_key,
                    )
                else:
                    children_summaries.append(
                        IssueTreeChildSummary(
                            id=issue_id,
                            key=canonical_key,
                            summary=data["summary"],
                            parent=curr_parent_key or "",
                        )
                    )

                # Enqueue children
                queue.extend(
                    (child, issue_id, canonical_key, False) for child in curr_node.children
                )

    except (IntegrityError, DBAPIError) as exc:
        _handle_parent_dag_error(exc)
        raise

    if root_summary_res is None:
        raise ProblemException(
            code="INTERNAL_ERROR",
            status=500,
            title="Internal Server Error",
            detail="Failed to generate root summary",
        )

    return IssueTreeResponse(
        created=created_count,
        root=root_summary_res,
        children=children_summaries,
    )
