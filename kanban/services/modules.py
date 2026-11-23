# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Module business service: lifecycle, access gates, and issue assignment (KB-P3-10b)."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any, Final

from sqlalchemy import delete, func, select, text

from database.models.issues import IssueModule
from database.models.projects import Module, Project, ProjectModuleDefault
from database.models.spine import ObjectRecord
from kanban.api.problems import ProblemException, not_found
from kanban.api.v1.schemas.modules import (
    MAX_MODULES_PER_ISSUE,
    ModuleCreate,
    ModuleLeadSummary,
    ModulePatch,
    ModuleResponse,
)
from kanban.security.granular_permissions import GranularPermission, require_permissions
from kanban.security.permissions import Capability, require_capability
from kanban.services.activity import ActivityEventType, record_activity
from kanban.services.issue_keys import resolve_issue_ref
from kanban.services.projects import get_project_or_404

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from kanban.api.deps import PrincipalContext

MODULES_DISABLED_CODE: Final[str] = "MODULES_DISABLED"


def require_modules_enabled(project: Project) -> None:
    """Verify project has modules feature enabled; raises equalized 404 if disabled."""
    if not project.modules_enabled:
        raise ProblemException(
            code=MODULES_DISABLED_CODE,
            status=404,
            title="Not Found",
            detail="Modules feature is disabled for this project",
        )


async def _verify_lead_eligible(
    session: AsyncSession,
    caller: PrincipalContext,
    project_id: uuid.UUID,
    lead_id: uuid.UUID,
) -> None:
    """Verify lead principal exists, is active, and holds VIEW capability on the project."""
    era_row = (
        await session.execute(
            text(
                "SELECT 1 FROM principals p "
                "JOIN effective_resource_access era ON era.principal_id = p.id "
                "WHERE p.id = :lead_id "
                "  AND p.workspace_id = :ws_id "
                "  AND p.status = 'ACTIVE' "
                "  AND p.principal_type IN ('USER', 'AGENT') "
                "  AND era.object_id = :proj_id "
                "  AND era.workspace_id = :ws_id "
                "  AND (era.allow_mask & 1) = 1 "
                "  AND (era.deny_mask & 1) = 0"
            ),
            {
                "lead_id": lead_id,
                "proj_id": project_id,
                "ws_id": caller.workspace_id,
            },
        )
    ).first()

    if era_row is None:
        raise ProblemException(
            code="LEAD_NOT_ELIGIBLE",
            status=422,
            title="Lead Not Eligible",
            detail="The specified principal is not eligible to lead a module in this project",
        )


async def _get_lead_summary(
    session: AsyncSession,
    lead_id: uuid.UUID | None,
    workspace_id: uuid.UUID,
) -> ModuleLeadSummary | None:
    """Resolve lead principal to ModuleLeadSummary."""
    if lead_id is None:
        return None

    row = (
        (
            await session.execute(
                text(
                    "SELECT p.id, o.canonical_key AS handle, "
                    "p.display_name, p.principal_type AS type "
                    "FROM principals p "
                    "JOIN objects o ON o.id = p.id "
                    "WHERE p.id = :lead_id AND p.workspace_id = :ws_id"
                ),
                {"lead_id": lead_id, "ws_id": workspace_id},
            )
        )
        .mappings()
        .first()
    )

    if row is None:
        return None  # pragma: no cover

    return ModuleLeadSummary(
        id=row["id"],
        handle=row["handle"] or "",
        display_name=row["display_name"],
        type=row["type"],
    )


async def _serialize_module(
    session: AsyncSession,
    caller: PrincipalContext,
    module: Module,
) -> ModuleResponse:
    """Serialize a Module model into ModuleResponse with RLS-filtered issue counts."""
    lead_summary = await _get_lead_summary(session, module.lead_principal_id, caller.workspace_id)

    # Compute issue counts over module_issues rows visible under caller's RLS
    counts_row = (
        (
            await session.execute(
                text(
                    "SELECT "
                    "  COUNT(im.issue_id) AS total_count, "
                    "  COUNT(im.issue_id) "
                    "    FILTER (WHERE s.state_group = 'completed') AS completed_count "
                    "FROM issue_modules im "
                    "JOIN issues i ON i.id = im.issue_id "
                    "JOIN workflow_states s ON s.id = i.state_id "
                    "WHERE im.module_id = :module_id"
                ),
                {"module_id": module.id},
            )
        )
        .mappings()
        .one()
    )

    return ModuleResponse(
        id=module.id,
        name=module.name,
        status=module.status,
        lead=lead_summary,
        description_markdown=module.description_markdown,
        start_date=module.start_date,
        target_date=module.target_date,
        issue_count=counts_row["total_count"],
        completed_count=counts_row["completed_count"],
    )


async def list_modules(
    session: AsyncSession,
    caller: PrincipalContext,
    project_ref: str,
) -> list[ModuleResponse]:
    """List all modules for a project ordered by name."""
    project = await get_project_or_404(session, caller, project_ref)
    require_modules_enabled(project)
    await require_capability(session, caller, project.id, Capability.VIEW)

    modules = (
        (
            await session.execute(
                select(Module)
                .join(ObjectRecord, ObjectRecord.id == Module.id)
                .where(
                    Module.project_id == project.id,
                    Module.workspace_id == caller.workspace_id,
                    ObjectRecord.deleted_at.is_(None),
                )
                .order_by(Module.name.asc())
            )
        )
        .scalars()
        .all()
    )

    return [await _serialize_module(session, caller, m) for m in modules]


async def create_module(
    session: AsyncSession,
    caller: PrincipalContext,
    project_ref: str,
    body: ModuleCreate,
) -> ModuleResponse:
    """Create a new module within a project (project EDIT required)."""
    project = await get_project_or_404(session, caller, project_ref)
    require_modules_enabled(project)
    await require_capability(session, caller, project.id, Capability.EDIT)

    # Check case-insensitive name uniqueness within project
    existing = (
        await session.execute(
            select(Module.id).where(
                Module.project_id == project.id,
                func.lower(Module.name) == body.name.lower(),
            )
        )
    ).first()
    if existing is not None:
        raise ProblemException(
            code="MODULE_NAME_TAKEN",
            status=409,
            title="Module Name Taken",
            detail=f"Module with name '{body.name}' already exists in this project",
        )

    # Verify lead eligibility if provided
    if body.lead_principal_id is not None:
        await _verify_lead_eligible(session, caller, project.id, body.lead_principal_id)

    module_id = uuid.uuid4()
    canonical_key = f"{project.identifier.lower()}-{body.name.lower().replace(' ', '-')}"[:200]
    await session.execute(
        text(
            "SELECT register_object("
            "  'module'::object_kind, :ws_id, :proj_id, :canonical_key, :title, :created_by_id, :id"
            ")"
        ),
        {
            "ws_id": caller.workspace_id,
            "proj_id": project.id,
            "canonical_key": canonical_key,
            "title": body.name,
            "created_by_id": caller.principal_id,
            "id": module_id,
        },
    )

    new_mod = Module(
        id=module_id,
        workspace_id=caller.workspace_id,
        project_id=project.id,
        name=body.name,
        description_markdown=body.description_markdown,
        lead_principal_id=body.lead_principal_id,
        status=body.status,
        start_date=body.start_date,
        target_date=body.target_date,
    )
    session.add(new_mod)
    await session.flush()

    await record_activity(
        session,
        workspace_id=caller.workspace_id,
        object_id=module_id,
        actor_principal_id=caller.principal_id,
        event_type=ActivityEventType.MODULE_CREATED,
        payload={"name": body.name, "status": body.status},
    )

    return await _serialize_module(session, caller, new_mod)


async def get_module_or_404(
    session: AsyncSession,
    caller: PrincipalContext,
    module_id: uuid.UUID,
) -> tuple[Module, Project]:
    """Retrieve module and project, verifying project VIEW and modules_enabled flag."""
    mod = await session.get(Module, module_id)
    if mod is None:
        not_found()

    # Verify project is visible to caller under RLS
    project = await session.get(Project, mod.project_id)
    if project is None:  # pragma: no cover
        not_found()

    try:
        await require_capability(session, caller, project.id, Capability.VIEW)
    except ProblemException:  # pragma: no cover
        not_found()

    require_modules_enabled(project)
    return mod, project


async def get_module(
    session: AsyncSession,
    caller: PrincipalContext,
    module_id: uuid.UUID,
) -> ModuleResponse:
    """Retrieve a single module by ID."""
    mod, _ = await get_module_or_404(session, caller, module_id)
    return await _serialize_module(session, caller, mod)


async def patch_module(  # noqa: C901
    session: AsyncSession,
    caller: PrincipalContext,
    module_id: uuid.UUID,
    body: ModulePatch,
) -> ModuleResponse:
    """Update a module partially (project EDIT required)."""
    mod, project = await get_module_or_404(session, caller, module_id)
    await require_capability(session, caller, project.id, Capability.EDIT)

    changes: dict[str, Any] = {}

    if "name" in body.model_fields_set and body.name is not None and body.name != mod.name:
        existing = (
            await session.execute(
                select(Module.id).where(
                    Module.project_id == project.id,
                    Module.id != mod.id,
                    func.lower(Module.name) == body.name.lower(),
                )
            )
        ).first()
        if existing is not None:
            raise ProblemException(
                code="MODULE_NAME_TAKEN",
                status=409,
                title="Module Name Taken",
                detail=f"Module with name '{body.name}' already exists in this project",
            )
        changes["name"] = {"old": mod.name, "new": body.name}
        mod.name = body.name
        new_ckey = f"{project.identifier.lower()}-{body.name.lower().replace(' ', '-')}"[:200]
        await session.execute(
            text("UPDATE objects SET canonical_key = :ckey, display_title = :title WHERE id = :id"),
            {"ckey": new_ckey, "title": body.name, "id": mod.id},
        )

    if (
        "description_markdown" in body.model_fields_set
        and body.description_markdown is not None
        and body.description_markdown != mod.description_markdown
    ):
        changes["description_markdown"] = {
            "old": mod.description_markdown,
            "new": body.description_markdown,
        }
        mod.description_markdown = body.description_markdown

    if (
        "lead_principal_id" in body.model_fields_set
        and body.lead_principal_id != mod.lead_principal_id
    ):
        if body.lead_principal_id is not None:
            await _verify_lead_eligible(session, caller, project.id, body.lead_principal_id)
        changes["lead_principal_id"] = {
            "old": str(mod.lead_principal_id) if mod.lead_principal_id else None,
            "new": str(body.lead_principal_id) if body.lead_principal_id else None,
        }
        mod.lead_principal_id = body.lead_principal_id

    if "status" in body.model_fields_set and body.status is not None and body.status != mod.status:
        changes["status"] = {"old": mod.status, "new": body.status}
        mod.status = body.status

    if "start_date" in body.model_fields_set and body.start_date != mod.start_date:
        changes["start_date"] = {
            "old": str(mod.start_date) if mod.start_date else None,
            "new": str(body.start_date) if body.start_date else None,
        }
        mod.start_date = body.start_date

    if "target_date" in body.model_fields_set and body.target_date != mod.target_date:
        changes["target_date"] = {
            "old": str(mod.target_date) if mod.target_date else None,
            "new": str(body.target_date) if body.target_date else None,
        }
        mod.target_date = body.target_date

    if mod.start_date and mod.target_date and mod.target_date < mod.start_date:
        raise ProblemException(
            code="INVALID_DATE_RANGE",
            status=422,
            title="Invalid Date Range",
            detail="Target date cannot be earlier than start date.",
        )

    await session.flush()

    if changes:
        await record_activity(
            session,
            workspace_id=caller.workspace_id,
            object_id=mod.id,
            actor_principal_id=caller.principal_id,
            event_type=ActivityEventType.MODULE_UPDATED,
            payload={"changes": changes},
        )

    return await _serialize_module(session, caller, mod)


async def delete_module(
    session: AsyncSession,
    caller: PrincipalContext,
    module_id: uuid.UUID,
) -> None:
    """Delete a module and remove all its issue links (project ADMIN required)."""
    mod, project = await get_module_or_404(session, caller, module_id)
    await require_capability(session, caller, project.id, Capability.ADMIN)

    # Count affected issue links before deletion
    removed_count = (
        await session.execute(
            select(func.count(IssueModule.issue_id)).where(IssueModule.module_id == mod.id)
        )
    ).scalar_one()

    # Delete cascade join rows
    await session.execute(delete(IssueModule).where(IssueModule.module_id == mod.id))
    await session.execute(
        delete(ProjectModuleDefault).where(ProjectModuleDefault.module_id == mod.id)
    )
    await session.delete(mod)

    # Soft delete object record
    await session.execute(
        text("UPDATE objects SET deleted_at = clock_timestamp() WHERE id = :id"),
        {"id": mod.id},
    )
    await session.flush()

    await record_activity(
        session,
        workspace_id=caller.workspace_id,
        object_id=mod.id,
        actor_principal_id=caller.principal_id,
        event_type=ActivityEventType.MODULE_DELETED,
        payload={"removed_issue_links": removed_count},
    )


async def update_issue_modules(
    session: AsyncSession,
    caller: PrincipalContext,
    issue_ref: str,
    module_ids: list[uuid.UUID],
) -> list[uuid.UUID]:
    """Replace all module assignments on an issue (issue EDIT required)."""
    issue = await resolve_issue_ref(session, caller, issue_ref)
    project = await session.get(Project, issue.project_id)
    if project is None:  # pragma: no cover
        not_found()

    require_modules_enabled(project)
    await require_capability(session, caller, issue.id, Capability.EDIT)
    await require_permissions(
        session,
        caller,
        issue.workspace_id,
        {GranularPermission.FIELD_MODIFY_MODULES.value},
        project_id=issue.project_id,
        object_readable=True,
    )
    await require_permissions(
        session,
        caller,
        issue.workspace_id,
        {GranularPermission.FIELD_MODIFY_MODULES.value},
        project_id=issue.project_id,
        object_readable=True,
    )

    if len(module_ids) > MAX_MODULES_PER_ISSUE:
        raise ProblemException(
            code="MODULE_LIMIT",
            status=422,
            title="Module Limit Exceeded",
            detail=f"An issue cannot be assigned to more than {MAX_MODULES_PER_ISSUE} modules",
        )

    # Validate all requested modules belong to the issue's project
    if module_ids:
        found_mods = (
            await session.execute(
                select(Module.id, Module.project_id).where(Module.id.in_(module_ids))
            )
        ).all()
        found_map = {row[0]: row[1] for row in found_mods}

        for mid in module_ids:
            if mid not in found_map or found_map[mid] != issue.project_id:
                raise ProblemException(
                    code="MODULE_NOT_IN_PROJECT",
                    status=422,
                    title="Module Not In Project",
                    detail=f"Module {mid} does not belong to the issue's project",
                )

    # Get current assignments
    curr_rows = (
        (
            await session.execute(
                select(IssueModule.module_id).where(IssueModule.issue_id == issue.id)
            )
        )
        .scalars()
        .all()
    )
    curr_set = set(curr_rows)
    target_set = set(module_ids)

    added = [mid for mid in module_ids if mid not in curr_set]
    removed = [mid for mid in curr_rows if mid not in target_set]

    if removed:
        await session.execute(
            delete(IssueModule).where(
                IssueModule.issue_id == issue.id,
                IssueModule.module_id.in_(removed),
            )
        )

    for mid in added:
        session.add(
            IssueModule(
                issue_id=issue.id,
                module_id=mid,
                workspace_id=caller.workspace_id,
                added_by_id=caller.principal_id,
            )
        )

    await session.flush()

    if added or removed:
        await record_activity(
            session,
            workspace_id=caller.workspace_id,
            object_id=issue.id,
            actor_principal_id=caller.principal_id,
            event_type=ActivityEventType.ISSUE_MODULES_CHANGED,
            payload={
                "added": [str(m) for m in added],
                "removed": [str(m) for m in removed],
            },
        )

    return module_ids


async def add_issue_to_module(
    session: AsyncSession,
    caller: PrincipalContext,
    module_id: uuid.UUID,
    issue_ref: str,
) -> None:
    """Add a single issue to a module (issue EDIT and project VIEW required)."""
    issue = await resolve_issue_ref(session, caller, issue_ref)
    mod, _project = await get_module_or_404(session, caller, module_id)
    await require_capability(session, caller, issue.id, Capability.EDIT)
    await require_permissions(
        session,
        caller,
        issue.workspace_id,
        {GranularPermission.FIELD_MODIFY_MODULES.value},
        project_id=issue.project_id,
        object_readable=True,
    )

    if mod.project_id != issue.project_id:
        raise ProblemException(
            code="CROSS_PROJECT_NOT_ALLOWED",
            status=422,
            title="Cross-Project Not Allowed",
            detail="Cannot assign issue to a module of a different project",
        )

    # Check limit on issue
    curr_count = (
        await session.execute(
            select(func.count(IssueModule.module_id)).where(IssueModule.issue_id == issue.id)
        )
    ).scalar_one()

    # Check if already assigned
    existing = (
        await session.execute(
            select(IssueModule).where(
                IssueModule.issue_id == issue.id,
                IssueModule.module_id == module_id,
            )
        )
    ).first()

    if existing is not None:
        return

    if curr_count >= MAX_MODULES_PER_ISSUE:
        raise ProblemException(
            code="MODULE_LIMIT",
            status=422,
            title="Module Limit Exceeded",
            detail=f"An issue cannot be assigned to more than {MAX_MODULES_PER_ISSUE} modules",
        )

    session.add(
        IssueModule(
            issue_id=issue.id,
            module_id=module_id,
            workspace_id=caller.workspace_id,
            added_by_id=caller.principal_id,
        )
    )
    await session.flush()

    await record_activity(
        session,
        workspace_id=caller.workspace_id,
        object_id=issue.id,
        actor_principal_id=caller.principal_id,
        event_type=ActivityEventType.ISSUE_MODULE_ADDED,
        payload={"module_id": str(module_id)},
    )


async def remove_issue_from_module(
    session: AsyncSession,
    caller: PrincipalContext,
    module_id: uuid.UUID,
    issue_ref: str,
) -> None:
    """Remove a single issue from a module (issue EDIT required)."""
    issue = await resolve_issue_ref(session, caller, issue_ref)
    _, _project = await get_module_or_404(session, caller, module_id)
    await require_capability(session, caller, issue.id, Capability.EDIT)
    await require_permissions(
        session,
        caller,
        issue.workspace_id,
        {GranularPermission.FIELD_MODIFY_MODULES.value},
        project_id=issue.project_id,
        object_readable=True,
    )

    await session.execute(
        delete(IssueModule).where(
            IssueModule.issue_id == issue.id,
            IssueModule.module_id == module_id,
        )
    )
    await session.flush()

    await record_activity(
        session,
        workspace_id=caller.workspace_id,
        object_id=issue.id,
        actor_principal_id=caller.principal_id,
        event_type=ActivityEventType.ISSUE_MODULE_REMOVED,
        payload={"module_id": str(module_id)},
    )
