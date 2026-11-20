# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Two-stage destructive lifecycle service (KB-P4-12, S11.4, S7.2, S12.3)."""

from __future__ import annotations

import hashlib
import json
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any, Final, Literal

from sqlalchemy import delete, func, select, text

from database.models.base import ObjectKind
from database.models.destructive_token import DestructiveConfirmationToken
from database.models.issues import (
    Issue,
    IssueAssignee,
    IssueComment,
    IssueLabel,
    IssueModule,
    IssueSubscription,
)
from database.models.knowledge import Doc, Page, PageVersion, Sticky
from database.models.projects import (
    Cycle,
    Module,
    Project,
    ProjectLabel,
    ProjectModuleDefault,
    ProjectPriority,
    View,
    WorkflowState,
)
from database.models.spine import ObjectLink, ObjectRecord, Workspace
from kanban.api.problems import ProblemException, not_found
from kanban.security.permissions import Capability, require_capability
from kanban.services.activity import ActivityEventType, record_activity

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from kanban.api.deps import PrincipalContext

__all__ = [
    "ALLOWED_TARGET_KINDS",
    "DestructiveExecuteResult",
    "DestructiveRequestResult",
    "DestructiveRestoreResult",
    "ObjectBlastRadius",
    "compute_object_blast_radius",
    "execute_delete",
    "request_delete",
    "restore_object",
]

ALLOWED_TARGET_KINDS: Final[frozenset[str]] = frozenset(
    {"issue", "project", "doc", "page", "sticky", "cycle", "module", "view"}
)
_MAX_TOKEN_TTL_SECONDS: Final[int] = 300
_REQUIRED_AAL: Final[int] = 2
_REASON_MIN_LEN: Final[int] = 10
_REASON_MAX_LEN: Final[int] = 500


@dataclass(frozen=True, slots=True)
class ObjectBlastRadius:
    """Exact blast radius and deterministic SHA-256 blast hash."""

    target_id: uuid.UUID
    target_kind: str
    canonical_key: str
    mode: str
    summary_text: str
    blast_hash: str
    confirm_phrase: str
    child_counts: dict[str, int]
    descendant_ids: tuple[uuid.UUID, ...]
    inbound_link_ids: tuple[uuid.UUID, ...]
    outbound_link_ids: tuple[uuid.UUID, ...]
    content_etag_or_updated_at: str

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dictionary."""
        return {
            "target_id": str(self.target_id),
            "target_kind": self.target_kind,
            "canonical_key": self.canonical_key,
            "mode": self.mode,
            "summary_text": self.summary_text,
            "blast_hash": self.blast_hash,
            "confirm_phrase": self.confirm_phrase,
            "child_counts": self.child_counts,
            "descendant_count": len(self.descendant_ids),
            "inbound_link_count": len(self.inbound_link_ids),
            "outbound_link_count": len(self.outbound_link_ids),
        }


@dataclass(frozen=True, slots=True)
class DestructiveRequestResult:
    """Output returned by Stage 1 request_delete."""

    stage: str
    target: str
    target_kind: str
    target_id: str
    mode: str
    blast_summary: str
    blast_hash: str
    confirm_phrase: str
    confirmation_token: str
    expires_in_sec: int

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict representation."""
        return {
            "stage": self.stage,
            "target": self.target,
            "target_kind": self.target_kind,
            "target_id": self.target_id,
            "mode": self.mode,
            "blast_summary": self.blast_summary,
            "blast_hash": self.blast_hash,
            "confirm_phrase": self.confirm_phrase,
            "confirmation_token": self.confirmation_token,
            "expires_in_sec": self.expires_in_sec,
        }


@dataclass(frozen=True, slots=True)
class DestructiveExecuteResult:
    """Output returned by Stage 2 execute_delete."""

    status: str
    target: str
    target_kind: str
    target_id: str
    mode: str
    reason: str
    blast_hash: str

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict representation."""
        return {
            "status": self.status,
            "target": self.target,
            "target_kind": self.target_kind,
            "target_id": self.target_id,
            "mode": self.mode,
            "reason": self.reason,
            "blast_hash": self.blast_hash,
        }


@dataclass(frozen=True, slots=True)
class DestructiveRestoreResult:
    """Output returned by restore_object."""

    status: str
    target: str
    target_kind: str
    target_id: str
    reason: str

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict representation."""
        return {
            "status": self.status,
            "target": self.target,
            "target_kind": self.target_kind,
            "target_id": self.target_id,
            "reason": self.reason,
        }


async def _is_server_admin(session: AsyncSession) -> bool:
    """Check if current active session user has SERVER_ADMIN role."""
    stmt = text("SELECT app_principal_has_role(NULL, ARRAY['SERVER_ADMIN'])")
    result = await session.execute(stmt)
    return bool(result.scalar_one_or_none())


async def _resolve_target_entity(  # noqa: C901, PLR0912, PLR0913, PLR0915
    session: AsyncSession,
    caller: PrincipalContext,
    target_kind: str,
    target_ref: str,
    *,
    for_update: bool = False,
    include_deleted: bool = False,
) -> tuple[Any, ObjectRecord, str]:
    """Resolve target reference to entity instance, ObjectRecord, and canonical key.

    Returns:
        (entity_instance, object_record, canonical_key)
    Raises 404 if not found, not accessible, or soft-deleted when include_deleted is False.

    """
    ref = target_ref.strip()
    parsed_uuid: uuid.UUID | None = None
    try:
        parsed_uuid = uuid.UUID(ref)
    except ValueError:
        parsed_uuid = None

    entity: Any = None
    canonical_key: str = ""

    if target_kind == "issue":
        if parsed_uuid is not None:
            stmt = select(Issue, Project.identifier).join(Project, Project.id == Issue.project_id)
            stmt = stmt.where(
                Issue.id == parsed_uuid,
                Issue.workspace_id == caller.workspace_id,
            )
        elif "-" in ref:
            parts = ref.split("-", 1)
            prefix, seq_str = parts[0].upper(), parts[1]
            if not seq_str.isdigit():
                not_found()
            stmt = select(Issue, Project.identifier).join(Project, Project.id == Issue.project_id)
            stmt = stmt.where(
                Project.identifier == prefix,
                Issue.sequence_id == int(seq_str),
                Issue.workspace_id == caller.workspace_id,
            )
        else:
            not_found()

        if for_update:
            stmt = stmt.with_for_update(of=Issue)
        row = (await session.execute(stmt)).first()
        if row is None:
            not_found()
        entity, proj_ident = row
        canonical_key = f"{proj_ident}-{entity.sequence_id}"

    elif target_kind == "project":
        if parsed_uuid is not None:
            stmt_proj = select(Project).where(
                Project.id == parsed_uuid, Project.workspace_id == caller.workspace_id
            )
        else:
            stmt_proj = select(Project).where(
                Project.identifier == ref.upper(), Project.workspace_id == caller.workspace_id
            )
        if for_update:
            stmt_proj = stmt_proj.with_for_update()
        entity = (await session.execute(stmt_proj)).scalar_one_or_none()
        if entity is None:
            not_found()
        canonical_key = entity.identifier

    elif target_kind == "doc":
        if parsed_uuid is not None:
            stmt_doc = select(Doc).where(
                Doc.id == parsed_uuid, Doc.workspace_id == caller.workspace_id
            )
        else:
            stmt_doc = select(Doc).where(Doc.title == ref, Doc.workspace_id == caller.workspace_id)
        if for_update:
            stmt_doc = stmt_doc.with_for_update()
        entity = (await session.execute(stmt_doc)).scalar_one_or_none()
        if entity is None:
            not_found()
        canonical_key = entity.title

    elif target_kind == "page":
        if parsed_uuid is not None:
            stmt_page = select(Page).where(
                Page.id == parsed_uuid, Page.workspace_id == caller.workspace_id
            )
        else:
            stmt_page = select(Page).where(
                Page.title == ref, Page.workspace_id == caller.workspace_id
            )
        if for_update:
            stmt_page = stmt_page.with_for_update()
        entity = (await session.execute(stmt_page)).scalar_one_or_none()
        if entity is None:
            not_found()
        canonical_key = entity.title

    elif target_kind == "sticky":
        if parsed_uuid is None:
            not_found()
        stmt_sticky = select(Sticky).where(
            Sticky.id == parsed_uuid, Sticky.workspace_id == caller.workspace_id
        )
        if for_update:
            stmt_sticky = stmt_sticky.with_for_update()
        entity = (await session.execute(stmt_sticky)).scalar_one_or_none()
        if entity is None:
            not_found()
        canonical_key = str(entity.id)

    elif target_kind == "cycle":
        if parsed_uuid is not None:
            stmt_cyc = select(Cycle).where(
                Cycle.id == parsed_uuid, Cycle.workspace_id == caller.workspace_id
            )
        else:
            stmt_cyc = select(Cycle).where(
                Cycle.name == ref, Cycle.workspace_id == caller.workspace_id
            )
        if for_update:
            stmt_cyc = stmt_cyc.with_for_update()
        entity = (await session.execute(stmt_cyc)).scalar_one_or_none()
        if entity is None:
            not_found()
        canonical_key = entity.name

    elif target_kind == "module":
        if parsed_uuid is not None:
            stmt_mod = select(Module).where(
                Module.id == parsed_uuid, Module.workspace_id == caller.workspace_id
            )
        else:
            stmt_mod = select(Module).where(
                Module.name == ref, Module.workspace_id == caller.workspace_id
            )
        if for_update:
            stmt_mod = stmt_mod.with_for_update()
        entity = (await session.execute(stmt_mod)).scalar_one_or_none()
        if entity is None:
            not_found()
        canonical_key = entity.name

    elif target_kind == "view":
        if parsed_uuid is not None:
            stmt_view = select(View).where(
                View.id == parsed_uuid, View.workspace_id == caller.workspace_id
            )
        else:
            stmt_view = select(View).where(
                View.name == ref, View.workspace_id == caller.workspace_id
            )
        if for_update:
            stmt_view = stmt_view.with_for_update()
        entity = (await session.execute(stmt_view)).scalar_one_or_none()
        if entity is None:
            not_found()
        canonical_key = entity.name
    else:
        not_found()

    obj_stmt = select(ObjectRecord).where(
        ObjectRecord.id == entity.id,
        ObjectRecord.object_type == target_kind,
        ObjectRecord.workspace_id == caller.workspace_id,
    )
    if for_update:
        obj_stmt = obj_stmt.with_for_update()
    obj = (await session.execute(obj_stmt)).scalar_one_or_none()
    if obj is None:
        not_found()

    if not include_deleted and obj.deleted_at is not None:
        not_found()

    return entity, obj, canonical_key


async def compute_object_blast_radius(  # noqa: PLR0913, PLR0915
    session: AsyncSession,
    caller: PrincipalContext,
    target_kind: str,
    target_ref: str,
    mode: Literal["trash", "permanent_purge", "restore"] = "trash",
    *,
    for_update: bool = False,
) -> ObjectBlastRadius:
    """Compute exact blast radius, affected IDs, and deterministic SHA-256 blast hash.

    Follows S7.2 8q, S11.4 Tool 12, and S12.3:
    blast_hash = lowercase SHA-256 hex of canonical JSON:
    {
      "child_counts": dict[str, int],
      "content_etag_or_updated_at": str,
      "mode": str,
      "sorted_descendant_ids": list[str],
      "sorted_inbound_link_ids": list[str],
      "sorted_outbound_link_ids": list[str],
      "target_object_id": str,
      "target_object_type": str,
    }
    """
    if target_kind not in ALLOWED_TARGET_KINDS:
        raise ProblemException(
            code="VALIDATION_FAILED",
            status=422,
            title="Validation Failed",
            detail=f"target_kind '{target_kind}' must be one of {sorted(ALLOWED_TARGET_KINDS)}",
        )

    include_deleted = mode in ("permanent_purge", "restore")
    entity, obj, canonical_key = await _resolve_target_entity(
        session,
        caller,
        target_kind,
        target_ref,
        for_update=for_update,
        include_deleted=include_deleted,
    )

    # Inbound and outbound links
    inbound_res = await session.execute(
        select(ObjectLink.id)
        .where(
            ObjectLink.target_id == obj.id,
            ObjectLink.link_state != "PURGED",
            ObjectLink.workspace_id == caller.workspace_id,
        )
        .order_by(ObjectLink.id)
    )
    inbound_link_ids = tuple(inbound_res.scalars().all())

    outbound_res = await session.execute(
        select(ObjectLink.id)
        .where(
            ObjectLink.source_id == obj.id,
            ObjectLink.link_state != "PURGED",
            ObjectLink.workspace_id == caller.workspace_id,
        )
        .order_by(ObjectLink.id)
    )
    outbound_link_ids = tuple(outbound_res.scalars().all())

    descendant_ids: list[uuid.UUID] = []
    child_counts: dict[str, int] = {}
    summary_text = ""

    if target_kind == "issue":
        # Direct children
        child_res = await session.execute(
            select(Issue.id).where(Issue.parent_issue_id == obj.id).order_by(Issue.id)
        )
        direct_child_ids = list(child_res.scalars().all())
        descendant_ids = direct_child_ids

        # Comments & attachments counts
        comment_count = (
            await session.execute(
                select(func.count(IssueComment.id)).where(IssueComment.issue_id == obj.id)
            )
        ).scalar_one() or 0
        attachment_count = (
            await session.execute(
                text("SELECT count(*) FROM attachments WHERE issue_id = :issue_id"),
                {"issue_id": obj.id},
            )
        ).scalar_one() or 0

        child_counts = {
            "sub_issues_unparented": len(direct_child_ids),
            "comments": comment_count,
            "attachments": attachment_count,
        }
        sub_plural = "s" if len(direct_child_ids) != 1 else ""
        in_plural = "s" if len(inbound_link_ids) != 1 else ""
        summary_text = (
            f"{len(direct_child_ids)} sub-issue{sub_plural} unparented, "
            f"{len(inbound_link_ids)} inbound object_link{in_plural} flagged"
        )

    elif target_kind == "project":
        issues_res = await session.execute(select(Issue.id).where(Issue.project_id == obj.id))
        project_issue_ids = list(issues_res.scalars().all())
        docs_res = await session.execute(select(Doc.id).where(Doc.project_id == obj.id))
        project_doc_ids = list(docs_res.scalars().all())
        pages_res = await session.execute(
            select(Page.id).where(Page.doc_id.in_(project_doc_ids))
            if project_doc_ids
            else select(Page.id).where(text("false"))
        )
        project_page_ids = list(pages_res.scalars().all())
        stickies_res = await session.execute(select(Sticky.id).where(Sticky.project_id == obj.id))
        project_sticky_ids = list(stickies_res.scalars().all())
        cycles_res = await session.execute(select(Cycle.id).where(Cycle.project_id == obj.id))
        project_cycle_ids = list(cycles_res.scalars().all())
        modules_res = await session.execute(select(Module.id).where(Module.project_id == obj.id))
        project_module_ids = list(modules_res.scalars().all())
        views_res = await session.execute(select(View.id).where(View.project_id == obj.id))
        project_view_ids = list(views_res.scalars().all())

        descendant_ids = (
            project_issue_ids
            + project_doc_ids
            + project_page_ids
            + project_sticky_ids
            + project_cycle_ids
            + project_module_ids
            + project_view_ids
        )
        child_counts = {
            "issues": len(project_issue_ids),
            "docs": len(project_doc_ids),
            "pages": len(project_page_ids),
            "stickies": len(project_sticky_ids),
            "cycles": len(project_cycle_ids),
            "modules": len(project_module_ids),
            "views": len(project_view_ids),
        }
        summary_text = (
            f"{len(project_issue_ids)} issues, {len(project_doc_ids)} docs, "
            f"{len(project_page_ids)} pages, {len(project_cycle_ids)} cycles, "
            f"{len(project_module_ids)} modules to be removed"
        )

    elif target_kind == "doc":
        pages_res = await session.execute(select(Page.id).where(Page.doc_id == obj.id))
        doc_page_ids = list(pages_res.scalars().all())
        descendant_ids = doc_page_ids
        version_count = (
            await session.execute(
                select(func.count()).where(PageVersion.page_id.in_(doc_page_ids))
                if doc_page_ids
                else select(func.count()).where(text("false"))
            )
        ).scalar_one() or 0
        child_counts = {"pages": len(doc_page_ids), "page_versions": version_count}
        summary_text = f"{len(doc_page_ids)} pages, {version_count} page versions to be removed"

    elif target_kind == "page":
        # Descendant pages by hierarchy_path
        page_stmt = select(Page.id).where(
            Page.doc_id == entity.doc_id,
            text("pages.hierarchy_path <@ cast(:path as ltree) AND pages.id != :page_id"),
        )
        desc_res = await session.execute(
            page_stmt, {"path": entity.hierarchy_path, "page_id": obj.id}
        )
        page_desc_ids = list(desc_res.scalars().all())
        descendant_ids = page_desc_ids
        all_affected_page_ids = [obj.id, *page_desc_ids]
        version_count = (
            await session.execute(
                select(func.count()).where(PageVersion.page_id.in_(all_affected_page_ids))
            )
        ).scalar_one() or 0
        child_counts = {
            "descendant_pages": len(page_desc_ids),
            "page_versions": version_count,
        }
        summary_text = (
            f"{len(page_desc_ids)} descendant pages, {version_count} page versions to be removed"
        )

    elif target_kind == "sticky":
        descendant_ids = []
        child_counts = {}
        total_links = len(inbound_link_ids) + len(outbound_link_ids)
        summary_text = f"1 sticky note, {total_links} object_links to be removed"

    elif target_kind == "cycle":
        assigned_res = await session.execute(select(Issue.id).where(Issue.cycle_id == obj.id))
        cycle_issue_ids = list(assigned_res.scalars().all())
        descendant_ids = cycle_issue_ids
        child_counts = {"assigned_issues": len(cycle_issue_ids)}
        summary_text = f"{len(cycle_issue_ids)} assigned issues to be unassigned"

    elif target_kind == "module":
        assigned_res = await session.execute(
            select(IssueModule.issue_id).where(IssueModule.module_id == obj.id)
        )
        mod_issue_ids = list(assigned_res.scalars().all())
        descendant_ids = mod_issue_ids
        child_counts = {"assigned_issues": len(mod_issue_ids)}
        summary_text = f"{len(mod_issue_ids)} assigned issues to be unassigned"

    elif target_kind == "view":
        descendant_ids = []
        child_counts = {}
        summary_text = "1 saved view to be removed"

    content_etag_or_updated_at = obj.updated_at.isoformat()

    canonical_dict = {
        "child_counts": child_counts,
        "content_etag_or_updated_at": content_etag_or_updated_at,
        "mode": mode,
        "sorted_descendant_ids": sorted([str(uid) for uid in descendant_ids]),
        "sorted_inbound_link_ids": sorted([str(uid) for uid in inbound_link_ids]),
        "sorted_outbound_link_ids": sorted([str(uid) for uid in outbound_link_ids]),
        "target_object_id": str(obj.id),
        "target_object_type": target_kind,
    }
    canonical_json = json.dumps(canonical_dict, sort_keys=True, separators=(",", ":"))
    blast_hash = hashlib.sha256(canonical_json.encode("utf-8")).hexdigest().lower()

    action_verb = "TRASH" if mode == "trash" else ("RESTORE" if mode == "restore" else "PURGE")
    confirm_phrase = f"{action_verb} {target_kind.upper()} {canonical_key}"

    return ObjectBlastRadius(
        target_id=obj.id,
        target_kind=target_kind,
        canonical_key=canonical_key,
        mode=mode,
        summary_text=summary_text,
        blast_hash=blast_hash,
        confirm_phrase=confirm_phrase,
        child_counts=child_counts,
        descendant_ids=tuple(sorted(descendant_ids)),
        inbound_link_ids=tuple(inbound_link_ids),
        outbound_link_ids=tuple(outbound_link_ids),
        content_etag_or_updated_at=content_etag_or_updated_at,
    )


async def request_delete(
    session: AsyncSession,
    caller: PrincipalContext,
    target_kind: str,
    target_ref: str,
    mode: Literal["trash", "permanent_purge"] = "trash",
) -> DestructiveRequestResult:
    """Stage 1: Compute blast radius and mint single-use 5-minute confirmation token."""
    if caller.aal_level < _REQUIRED_AAL:
        raise ProblemException(
            code="AAL2_REQUIRED",
            status=403,
            title="AAL2 Required",
            detail="Operation requires Authenticator Assurance Level 2 (AAL2).",
        )

    if mode not in ("trash", "permanent_purge"):
        raise ProblemException(
            code="VALIDATION_FAILED",
            status=422,
            title="Validation Failed",
            detail=f"mode '{mode}' must be 'trash' or 'permanent_purge'",
        )

    if mode == "trash" and target_kind in ("cycle", "module", "view"):
        raise ProblemException(
            code="VALIDATION_FAILED",
            status=422,
            title="Validation Failed",
            detail=(
                f"Entities of kind '{target_kind}' do not support soft-trash; "
                "use mode='permanent_purge' instead."
            ),
        )

    if mode == "permanent_purge" and not await _is_server_admin(session):
        raise ProblemException(
            code="SERVER_ADMIN_REQUIRED",
            status=403,
            title="Server Admin Required",
            detail="Permanent purge is restricted strictly to SERVER_ADMIN.",
        )

    include_deleted = mode == "permanent_purge"
    _entity, obj, _ = await _resolve_target_entity(
        session, caller, target_kind, target_ref, include_deleted=include_deleted
    )

    if mode == "permanent_purge":
        if target_kind in ("issue", "project", "doc", "page", "sticky") and obj.deleted_at is None:
            raise ProblemException(
                code="SOFT_TRASH_REQUIRED_FIRST",
                status=409,
                title="Soft Trash Required First",
                detail=(
                    f"Target {target_kind} must be moved to soft-trash before permanent purge."
                ),
            )
    else:
        # In soft-trash mode
        await require_capability(session, caller, obj.id, Capability.DELETE)

    blast = await compute_object_blast_radius(session, caller, target_kind, target_ref, mode=mode)

    raw_token = f"kb_del_{secrets.token_urlsafe(32)}"
    token_sha256 = hashlib.sha256(raw_token.encode("utf-8")).digest()
    expires_at = datetime.now(UTC) + timedelta(seconds=_MAX_TOKEN_TTL_SECONDS)

    db_token = DestructiveConfirmationToken(
        workspace_id=caller.workspace_id,
        token_sha256=token_sha256,
        caller_principal_id=caller.principal_id,
        target_object_id=obj.id,
        target_object_type=ObjectKind(target_kind),
        mode=mode,
        blast_hash=blast.blast_hash,
        confirm_phrase=blast.confirm_phrase,
        blast_summary_json=blast.to_dict(),
        expires_at=expires_at,
    )
    session.add(db_token)
    await session.flush()

    return DestructiveRequestResult(
        stage="confirmation_required",
        target=blast.canonical_key,
        target_kind=target_kind,
        target_id=str(obj.id),
        mode=mode,
        blast_summary=blast.summary_text,
        blast_hash=blast.blast_hash,
        confirm_phrase=blast.confirm_phrase,
        confirmation_token=raw_token,
        expires_in_sec=_MAX_TOKEN_TTL_SECONDS,
    )


async def execute_delete(  # noqa: C901, PLR0912, PLR0913, PLR0915, PLR0917
    session: AsyncSession,
    caller: PrincipalContext,
    target_kind: str,
    target_ref: str,
    mode: Literal["trash", "permanent_purge"],
    confirmation_token: str,
    confirm_phrase: str,
    reason: str,
) -> DestructiveExecuteResult:
    """Stage 2: Atomic single-use claim, fail-closed verification, and destructive execution."""
    if caller.aal_level < _REQUIRED_AAL:
        raise ProblemException(
            code="AAL2_REQUIRED",
            status=403,
            title="AAL2 Required",
            detail="Operation requires Authenticator Assurance Level 2 (AAL2).",
        )

    if not reason or len(reason.strip()) < _REASON_MIN_LEN or len(reason.strip()) > _REASON_MAX_LEN:
        raise ProblemException(
            code="VALIDATION_FAILED",
            status=422,
            title="Validation Failed",
            detail=f"reason must be between {_REASON_MIN_LEN} and {_REASON_MAX_LEN} characters",
        )

    raw_token = confirmation_token.strip()
    token_sha256 = hashlib.sha256(raw_token.encode("utf-8")).digest()

    # Step 1: Atomic single-use claim
    claim_stmt = text(
        "UPDATE destructive_confirmation_tokens "
        "SET consumed_at = clock_timestamp() "
        "WHERE token_sha256 = :token_digest "
        "  AND consumed_at IS NULL "
        "  AND expires_at > clock_timestamp() "
        "RETURNING id, workspace_id, caller_principal_id, target_object_id, "
        "          target_object_type, mode, blast_hash, confirm_phrase"
    )
    res = await session.execute(claim_stmt, {"token_digest": token_sha256})
    claimed_row = res.mappings().one_or_none()

    if claimed_row is None:
        raise ProblemException(
            code="CONFIRMATION_TOKEN_INVALID_OR_EXPIRED",
            status=409,
            title="Confirmation Token Invalid or Expired",
            detail="Confirmation token has expired, already been consumed, or does not exist",
        )

    # Step 2: Fail-closed checks with token permanently consumed
    if claimed_row["caller_principal_id"] != caller.principal_id:
        await session.commit()
        raise ProblemException(
            code="TOKEN_CALLER_MISMATCH",
            status=403,
            title="Token Caller Mismatch",
            detail="Confirmation token was issued to a different principal",
        )

    include_deleted = mode == "permanent_purge"
    try:
        _, target_obj, _ = await _resolve_target_entity(
            session, caller, target_kind, target_ref, include_deleted=include_deleted
        )
    except Exception:
        await session.commit()
        raise

    if (
        claimed_row["target_object_id"] != target_obj.id
        or claimed_row["target_object_type"] != target_kind
        or claimed_row["mode"] != mode
    ):
        await session.commit()
        raise ProblemException(
            code="TOKEN_TARGET_MISMATCH",
            status=409,
            title="Token Target Mismatch",
            detail="Confirmation token target or mode does not match execution request",
        )

    if confirm_phrase.strip() != claimed_row["confirm_phrase"]:
        await session.commit()
        raise ProblemException(
            code="CONFIRM_PHRASE_MISMATCH",
            status=422,
            title="Confirm Phrase Mismatch",
            detail=f"Required confirm phrase: '{claimed_row['confirm_phrase']}'",
        )

    # Step 3: Target lock and live blast radius verification
    live_blast = await compute_object_blast_radius(
        session, caller, target_kind, target_ref, mode=mode, for_update=True
    )
    if live_blast.blast_hash.lower() != claimed_row["blast_hash"].lower():
        await session.commit()
        raise ProblemException(
            code="BLAST_RADIUS_CHANGED",
            status=412,
            title="Blast Radius Changed",
            detail="The target blast radius has changed since confirmation token was minted",
            current_preview=live_blast.to_dict(),
        )

    # Step 4: Destructive execution
    now_ts = datetime.now(UTC)

    if mode == "trash":
        target_obj.deleted_at = now_ts

        if target_kind == "issue":
            # Direct children get parent_issue_id = NULL
            await session.execute(
                text("SELECT unparent_issue_children_privileged(:issue_id)"),
                {"issue_id": target_obj.id},
            )
            await record_activity(
                session=session,
                workspace_id=caller.workspace_id,
                object_id=target_obj.id,
                actor_principal_id=caller.principal_id,
                event_type=ActivityEventType.ISSUE_TRASHED,
                payload={
                    "blast_hash": live_blast.blast_hash,
                    "reason": reason,
                    "unparented_child_ids": [str(c) for c in live_blast.descendant_ids],
                },
            )
        elif target_kind == "doc":
            # Soft-delete all child pages of doc
            await session.execute(
                text(
                    "UPDATE objects SET deleted_at = :now "
                    "WHERE id IN (SELECT id FROM pages WHERE doc_id = :doc_id) "
                    "  AND deleted_at IS NULL"
                ),
                {"now": now_ts, "doc_id": target_obj.id},
            )
        elif target_kind == "page":
            # Soft-delete all descendant pages
            if live_blast.descendant_ids:
                await session.execute(
                    text(
                        "UPDATE objects SET deleted_at = :now "
                        "WHERE id = ANY(:page_ids) AND deleted_at IS NULL"
                    ),
                    {"now": now_ts, "page_ids": list(live_blast.descendant_ids)},
                )
        elif target_kind == "project":
            # Soft-delete all project items
            await session.execute(
                text(
                    "UPDATE objects SET deleted_at = :now "
                    "WHERE id IN (SELECT id FROM issues WHERE project_id = :proj_id) "
                    "  AND deleted_at IS NULL"
                ),
                {"now": now_ts, "proj_id": target_obj.id},
            )

        await record_activity(
            session=session,
            workspace_id=caller.workspace_id,
            object_id=target_obj.id,
            actor_principal_id=caller.principal_id,
            event_type=ActivityEventType.DESTRUCTIVE_LIFECYCLE_EXECUTED,
            payload={
                "target_id": str(target_obj.id),
                "target_kind": target_kind,
                "mode": mode,
                "reason": reason,
                "blast_hash": live_blast.blast_hash,
            },
        )

    else:
        # In permanent_purge mode
        if not await _is_server_admin(session):
            raise ProblemException(
                code="SERVER_ADMIN_REQUIRED",
                status=403,
                title="Server Admin Required",
                detail="Permanent purge is restricted strictly to SERVER_ADMIN.",
            )

        # 4a: Run link auditor and link purger for zero silent cascade drops (S12.3)
        all_target_ids = [target_obj.id, *live_blast.descendant_ids]
        links_res = await session.execute(
            text(
                "SELECT id FROM object_links "
                "WHERE (source_id = ANY(:target_ids) OR target_id = ANY(:target_ids)) "
                "  AND link_state <> 'PURGED'"
            ),
            {"target_ids": all_target_ids},
        )
        link_ids = list(links_res.scalars().all())
        for lid in link_ids:
            await session.execute(
                text(
                    "SELECT * FROM audit_single_object_link("
                    ":lid, clock_timestamp() + interval '365 days')"
                ),
                {"lid": lid},
            )

        touching_audits_stmt = text(
            "SELECT a.id FROM invalid_object_link_audits a "
            "JOIN object_links l ON l.id = a.link_id "
            "WHERE a.workspace_id = :ws_id "
            "  AND a.purged_at IS NULL "
            "  AND a.resolved_at IS NULL "
            "  AND (l.source_id = ANY(:target_ids) OR l.target_id = ANY(:target_ids))"
        )
        touching_audits = (
            (
                await session.execute(
                    touching_audits_stmt,
                    {"ws_id": caller.workspace_id, "target_ids": all_target_ids},
                )
            )
            .scalars()
            .all()
        )

        if touching_audits:
            await session.execute(
                text("SELECT * FROM purge_invalid_object_links(:audit_ids, :actor_id, :reason)"),
                {
                    "audit_ids": list(touching_audits),
                    "actor_id": caller.principal_id,
                    "reason": reason,
                },
            )

        # 4b: Delete entity rows and objects spine
        if target_kind == "issue":
            await session.execute(
                delete(IssueComment).where(IssueComment.issue_id == target_obj.id)
            )
            await session.execute(
                delete(IssueAssignee).where(IssueAssignee.issue_id == target_obj.id)
            )
            await session.execute(delete(IssueLabel).where(IssueLabel.issue_id == target_obj.id))
            await session.execute(delete(IssueModule).where(IssueModule.issue_id == target_obj.id))
            await session.execute(
                delete(IssueSubscription).where(IssueSubscription.issue_id == target_obj.id)
            )
            await session.execute(delete(Issue).where(Issue.id == target_obj.id))

        elif target_kind == "page":
            affected_page_ids = [target_obj.id, *live_blast.descendant_ids]
            await session.execute(
                delete(PageVersion).where(PageVersion.page_id.in_(affected_page_ids))
            )
            # Delete children first
            for pid in reversed(live_blast.descendant_ids):
                await session.execute(delete(Page).where(Page.id == pid))
                await session.execute(delete(ObjectRecord).where(ObjectRecord.id == pid))
            await session.execute(delete(Page).where(Page.id == target_obj.id))

        elif target_kind == "doc":
            pages_res = await session.execute(select(Page.id).where(Page.doc_id == target_obj.id))
            doc_page_ids = list(pages_res.scalars().all())
            if doc_page_ids:
                await session.execute(
                    delete(PageVersion).where(PageVersion.page_id.in_(doc_page_ids))
                )
                for pid in doc_page_ids:
                    await session.execute(delete(Page).where(Page.id == pid))
                    await session.execute(delete(ObjectRecord).where(ObjectRecord.id == pid))
            await session.execute(delete(Doc).where(Doc.id == target_obj.id))

        elif target_kind == "cycle":
            await session.execute(
                text("UPDATE issues SET cycle_id = NULL WHERE cycle_id = :cycle_id"),
                {"cycle_id": target_obj.id},
            )
            await session.execute(delete(Cycle).where(Cycle.id == target_obj.id))

        elif target_kind == "module":
            await session.execute(delete(IssueModule).where(IssueModule.module_id == target_obj.id))
            await session.execute(
                delete(ProjectModuleDefault).where(ProjectModuleDefault.module_id == target_obj.id)
            )
            await session.execute(delete(Module).where(Module.id == target_obj.id))

        elif target_kind == "view":
            await session.execute(delete(View).where(View.id == target_obj.id))

        elif target_kind == "sticky":
            await session.execute(delete(Sticky).where(Sticky.id == target_obj.id))

        elif target_kind == "project":
            # 1. Project contained issues
            issues_res = await session.execute(
                select(Issue.id).where(Issue.project_id == target_obj.id)
            )
            proj_issue_ids = list(issues_res.scalars().all())
            if proj_issue_ids:
                await session.execute(
                    delete(IssueComment).where(IssueComment.issue_id.in_(proj_issue_ids))
                )
                await session.execute(
                    delete(IssueAssignee).where(IssueAssignee.issue_id.in_(proj_issue_ids))
                )
                await session.execute(
                    delete(IssueLabel).where(IssueLabel.issue_id.in_(proj_issue_ids))
                )
                await session.execute(
                    delete(IssueModule).where(IssueModule.issue_id.in_(proj_issue_ids))
                )
                await session.execute(
                    delete(IssueSubscription).where(IssueSubscription.issue_id.in_(proj_issue_ids))
                )
                await session.execute(delete(Issue).where(Issue.id.in_(proj_issue_ids)))
                await session.execute(
                    delete(ObjectRecord).where(ObjectRecord.id.in_(proj_issue_ids))
                )

            # 2. Project contained pages and docs
            docs_res = await session.execute(select(Doc.id).where(Doc.project_id == target_obj.id))
            proj_doc_ids = list(docs_res.scalars().all())
            pages_res = await session.execute(
                select(Page.id).where(Page.doc_id.in_(proj_doc_ids))
                if proj_doc_ids
                else select(Page.id).where(text("false"))
            )
            proj_page_ids = list(pages_res.scalars().all())
            if proj_page_ids:
                await session.execute(
                    delete(PageVersion).where(PageVersion.page_id.in_(proj_page_ids))
                )
                await session.execute(delete(Page).where(Page.id.in_(proj_page_ids)))
                await session.execute(
                    delete(ObjectRecord).where(ObjectRecord.id.in_(proj_page_ids))
                )
            if proj_doc_ids:
                await session.execute(delete(Doc).where(Doc.id.in_(proj_doc_ids)))
                await session.execute(delete(ObjectRecord).where(ObjectRecord.id.in_(proj_doc_ids)))

            # 3. Project contained stickies
            stickies_res = await session.execute(
                select(Sticky.id).where(Sticky.project_id == target_obj.id)
            )
            proj_sticky_ids = list(stickies_res.scalars().all())
            if proj_sticky_ids:
                await session.execute(delete(Sticky).where(Sticky.id.in_(proj_sticky_ids)))
                await session.execute(
                    delete(ObjectRecord).where(ObjectRecord.id.in_(proj_sticky_ids))
                )

            # 4. Project contained cycles
            cycles_res = await session.execute(
                select(Cycle.id).where(Cycle.project_id == target_obj.id)
            )
            proj_cycle_ids = list(cycles_res.scalars().all())
            if proj_cycle_ids:
                await session.execute(delete(Cycle).where(Cycle.id.in_(proj_cycle_ids)))
                await session.execute(
                    delete(ObjectRecord).where(ObjectRecord.id.in_(proj_cycle_ids))
                )

            # 5. Project contained modules
            modules_res = await session.execute(
                select(Module.id).where(Module.project_id == target_obj.id)
            )
            proj_mod_ids = list(modules_res.scalars().all())
            if proj_mod_ids:
                await session.execute(
                    delete(ProjectModuleDefault).where(
                        ProjectModuleDefault.module_id.in_(proj_mod_ids)
                    )
                )
                await session.execute(
                    delete(IssueModule).where(IssueModule.module_id.in_(proj_mod_ids))
                )
                await session.execute(delete(Module).where(Module.id.in_(proj_mod_ids)))
                await session.execute(delete(ObjectRecord).where(ObjectRecord.id.in_(proj_mod_ids)))

            # 6. Project contained views
            views_res = await session.execute(
                select(View.id).where(View.project_id == target_obj.id)
            )
            proj_view_ids = list(views_res.scalars().all())
            if proj_view_ids:
                await session.execute(delete(View).where(View.id.in_(proj_view_ids)))
                await session.execute(
                    delete(ObjectRecord).where(ObjectRecord.id.in_(proj_view_ids))
                )

            # 7. Project metadata
            await session.execute(text("SET LOCAL kanban.allow_project_delete = 'on'"))
            await session.execute(
                delete(ProjectModuleDefault).where(ProjectModuleDefault.project_id == target_obj.id)
            )
            await session.execute(
                delete(ProjectPriority).where(ProjectPriority.project_id == target_obj.id)
            )
            await session.execute(
                delete(ProjectLabel).where(ProjectLabel.project_id == target_obj.id)
            )
            await session.execute(
                delete(WorkflowState).where(WorkflowState.project_id == target_obj.id)
            )
            await session.execute(delete(Project).where(Project.id == target_obj.id))

        # Record activity before deleting from objects spine
        await record_activity(
            session=session,
            workspace_id=caller.workspace_id,
            object_id=target_obj.id,
            actor_principal_id=caller.principal_id,
            event_type=ActivityEventType.DESTRUCTIVE_LIFECYCLE_EXECUTED,
            payload={
                "target_id": str(target_obj.id),
                "target_kind": target_kind,
                "mode": mode,
                "reason": reason,
                "blast_hash": live_blast.blast_hash,
            },
        )

        # Delete from objects spine
        await session.execute(delete(ObjectRecord).where(ObjectRecord.id == target_obj.id))

    return DestructiveExecuteResult(
        status="executed",
        target=live_blast.canonical_key,
        target_kind=target_kind,
        target_id=str(target_obj.id),
        mode=mode,
        reason=reason,
        blast_hash=live_blast.blast_hash,
    )


async def restore_object(
    session: AsyncSession,
    caller: PrincipalContext,
    target_kind: str,
    target_ref: str,
    reason: str,
) -> DestructiveRestoreResult:
    """Restore a soft-deleted object from trash back to active state."""
    if caller.aal_level < _REQUIRED_AAL:
        raise ProblemException(
            code="AAL2_REQUIRED",
            status=403,
            title="AAL2 Required",
            detail="Operation requires Authenticator Assurance Level 2 (AAL2).",
        )

    if not reason or len(reason.strip()) < _REASON_MIN_LEN or len(reason.strip()) > _REASON_MAX_LEN:
        raise ProblemException(
            code="VALIDATION_FAILED",
            status=422,
            title="Validation Failed",
            detail=f"reason must be between {_REASON_MIN_LEN} and {_REASON_MAX_LEN} characters",
        )

    _, obj, canonical_key = await _resolve_target_entity(
        session, caller, target_kind, target_ref, include_deleted=True, for_update=True
    )
    await require_capability(session, caller, obj.id, Capability.DELETE)

    if obj.deleted_at is None:
        raise ProblemException(
            code="NOT_IN_TRASH",
            status=409,
            title="Not in Trash",
            detail=f"{target_kind} is not in trash",
        )

    # Per-workspace retention window
    ws = await session.get(Workspace, obj.workspace_id)
    retention_days = ws.trash_retention_days if ws and ws.trash_retention_days else 30
    now_ts = datetime.now(UTC)
    if obj.deleted_at + timedelta(days=retention_days) < now_ts:
        raise ProblemException(
            code="RETENTION_EXPIRED",
            status=409,
            title="Retention Expired",
            detail=f"{target_kind} retention window has expired and cannot be restored",
        )

    deleted_timestamp = obj.deleted_at
    obj.deleted_at = None

    if target_kind == "doc":
        await session.execute(
            text(
                "UPDATE objects SET deleted_at = NULL "
                "WHERE id IN (SELECT id FROM pages WHERE doc_id = :doc_id) "
                "  AND deleted_at = :del_ts"
            ),
            {"doc_id": obj.id, "del_ts": deleted_timestamp},
        )
    elif target_kind == "page":
        # Restore descendant pages that were deleted at the same timestamp
        desc_res = await session.execute(
            text(
                "SELECT id FROM pages "
                "WHERE doc_id = (SELECT doc_id FROM pages WHERE id = :page_id) "
                "  AND hierarchy_path <@ (SELECT hierarchy_path FROM pages WHERE id = :page_id)"
            ),
            {"page_id": obj.id},
        )
        desc_ids = list(desc_res.scalars().all())
        if desc_ids:
            await session.execute(
                text(
                    "UPDATE objects SET deleted_at = NULL "
                    "WHERE id = ANY(:ids) AND deleted_at = :del_ts"
                ),
                {"ids": desc_ids, "del_ts": deleted_timestamp},
            )
    elif target_kind == "project":
        await session.execute(
            text(
                "UPDATE objects SET deleted_at = NULL "
                "WHERE id IN (SELECT id FROM issues WHERE project_id = :proj_id) "
                "  AND deleted_at = :del_ts"
            ),
            {"proj_id": obj.id, "del_ts": deleted_timestamp},
        )

    await record_activity(
        session=session,
        workspace_id=caller.workspace_id,
        object_id=obj.id,
        actor_principal_id=caller.principal_id,
        event_type=ActivityEventType.DESTRUCTIVE_LIFECYCLE_EXECUTED,
        payload={
            "target_id": str(obj.id),
            "target_kind": target_kind,
            "mode": "restore",
            "reason": reason,
        },
    )

    return DestructiveRestoreResult(
        status="restored",
        target=canonical_key,
        target_kind=target_kind,
        target_id=str(obj.id),
        reason=reason,
    )
