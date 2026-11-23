# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""REST API endpoints for Issue CSV import, export, and template generation (KAN-316)."""

from __future__ import annotations

import email
import logging
import uuid
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import desc, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import (
    Cycle,
    Issue,
    IssueAssignee,
    IssueLabel,
    IssueModule,
    Module,
    Principal,
    Project,
    ProjectLabel,
    ProjectPriority,
    WorkflowState,
    WorkspaceSettings,
)
from kanban.api.deps import PrincipalContext, get_principal, get_rls_session
from kanban.api.problems import ProblemException
from kanban.api.timing import timing_floor
from kanban.csv.aes_zip import (
    MIN_PASSWORD_LENGTH,
    create_winzip_aes256_zip,
    extract_winzip_aes256_zip,
)
from kanban.csv.issue_csv import (
    CsvImportDiffReport,
    export_issues_to_csv,
    generate_issue_import_template,
    parse_issues_from_csv,
    process_issue_import,
)
from kanban.security.permissions import Capability, require_capability
from kanban.security.read_taint import TaintRecorder, get_taint_recorder
from kanban.services.activity import ActivityEventType, record_activity
from kanban.services.projects import get_project_or_404
from kanban.settings import get_settings

logger = logging.getLogger(__name__)

router = APIRouter(tags=["issue-csv"])

Caller = Annotated[PrincipalContext, Depends(get_principal)]
Session = Annotated[AsyncSession, Depends(get_rls_session)]


class IssueExportRequest(BaseModel):
    """Filters and format configuration for issue export."""

    model_config = ConfigDict(extra="forbid")

    q: str | None = Field(default=None, description="Search query string")
    project_id: str | None = Field(default=None, description="Project ID or identifier scope")
    state_ids: list[str] | None = Field(default=None, description="Filter by state IDs")
    state_categories: list[str] | None = Field(
        default=None, description="Filter by state categories / groups"
    )
    priorities: list[str] | None = Field(
        default=None, description="Filter by priority slugs or IDs"
    )
    assignee_ids: list[str] | None = Field(
        default=None, description="Filter by assignee IDs or handles"
    )
    label_ids: list[str] | None = Field(default=None, description="Filter by label IDs")
    cycle_id: str | None = Field(default=None, description="Filter by cycle ID")
    module_id: str | None = Field(default=None, description="Filter by module ID")
    issue_ids: list[str] | None = Field(
        default=None, description="Specific issue IDs or keys to export"
    )
    sort_by: str | None = Field(
        default="created_at", description="Field to sort by (created_at, board_rank, sequence_id)"
    )
    sort_dir: Literal["asc", "desc"] | None = Field(default="asc", description="Sort direction")
    format: Literal["csv", "zip_csv"] = Field(
        default="csv", description="Output format: csv or Password-protected ZIP (AES-256) zip_csv"
    )
    zip_password: str | None = Field(
        default=None, description="Mandatory password when format is zip_csv (>= 12 characters)"
    )


async def _check_export_governance(
    session: AsyncSession,
    _caller: PrincipalContext,
    workspace_id: uuid.UUID,
    project_id: uuid.UUID | None = None,
) -> None:
    """Enforce 3-tier governance for issue export."""
    # Tier 1: System Admin
    settings = get_settings()
    if not settings.enable_issue_export:
        raise ProblemException(
            code="EXPORT_DISABLED_BY_SYSTEM_ADMIN",
            status=status.HTTP_403_FORBIDDEN,
            title="Export Disabled By System Admin",
            detail="Issue export is disabled system-wide by the system administrator.",
        )

    # Tier 2: Workspace Admin
    res = await session.execute(
        select(WorkspaceSettings).where(WorkspaceSettings.workspace_id == workspace_id)
    )
    ws_settings = res.scalar_one_or_none()
    issue_export_enabled = ws_settings.issue_export_enabled if ws_settings is not None else True
    if not issue_export_enabled:
        raise ProblemException(
            code="EXPORT_DISABLED_BY_WORKSPACE_ADMIN",
            status=status.HTTP_403_FORBIDDEN,
            title="Export Disabled By Workspace Admin",
            detail="Issue export is disabled for this workspace by the workspace administrator.",
        )

    # Tier 3: Role Governance
    allowed_roles = (
        list(ws_settings.issue_export_allowed_roles)
        if (ws_settings is not None and ws_settings.issue_export_allowed_roles is not None)
        else ["workspace_admin", "project_admin", "member"]
    )
    db_roles = [r.strip().upper() for r in allowed_roles]
    if "SERVER_ADMIN" not in db_roles:
        db_roles.append("SERVER_ADMIN")

    has_role = False
    if project_id is not None:
        p_check = await session.execute(
            text("SELECT app_principal_has_role(:p_id, CAST(:roles AS text[]))"),
            {"p_id": project_id, "roles": db_roles},
        )
        has_role = bool(p_check.scalar_one())

    if not has_role:
        ws_check = await session.execute(
            text("SELECT app_principal_has_role(NULL, CAST(:roles AS text[]))"),
            {"roles": db_roles},
        )
        has_role = bool(ws_check.scalar_one())

    if not has_role:
        raise ProblemException(
            code="INSUFFICIENT_CAPABILITY",
            status=status.HTTP_403_FORBIDDEN,
            title="Insufficient Capability",
            detail="Your active role is not authorized to export issues from this workspace.",
        )


async def _check_import_governance(
    session: AsyncSession,
    caller: PrincipalContext,
    workspace_id: uuid.UUID,
    project_id: uuid.UUID,
) -> None:
    """Enforce 3-tier governance for issue import."""
    # Tier 1: System Admin
    settings = get_settings()
    if not settings.enable_issue_import:
        raise ProblemException(
            code="IMPORT_DISABLED_BY_SYSTEM_ADMIN",
            status=status.HTTP_403_FORBIDDEN,
            title="Import Disabled By System Admin",
            detail="Issue import is disabled system-wide by the system administrator.",
        )

    # Tier 2: Workspace Admin
    res = await session.execute(
        select(WorkspaceSettings).where(WorkspaceSettings.workspace_id == workspace_id)
    )
    ws_settings = res.scalar_one_or_none()
    issue_import_enabled = ws_settings.issue_import_enabled if ws_settings is not None else True
    if not issue_import_enabled:
        raise ProblemException(
            code="IMPORT_DISABLED_BY_WORKSPACE_ADMIN",
            status=status.HTTP_403_FORBIDDEN,
            title="Import Disabled By Workspace Admin",
            detail="Issue import is disabled for this workspace by the workspace administrator.",
        )

    # Tier 3: Project EDIT capability
    await require_capability(session, caller, project_id, Capability.EDIT)


@router.get(
    "/projects/{project_ref}/issues/import-template.csv",
    summary="Download project-specific CSV import template",
    response_class=Response,
    responses={
        200: {
            "content": {"text/csv": {}},
            "description": "Pre-populated CSV template with project states and priorities",
        }
    },
)
async def download_project_import_template(
    project_ref: str,
    caller: Caller,
    session: Session,
) -> Response:
    """Return pre-populated RFC 4180 CSV template for importing issues into project."""
    async with timing_floor(floor_ms=25.0):
        project = await get_project_or_404(session, caller, project_ref)

        state_res = await session.execute(
            select(WorkflowState.name)
            .where(WorkflowState.project_id == project.id)
            .order_by(WorkflowState.sort_order)
        )
        states = list(state_res.scalars().all())

        prio_res = await session.execute(
            select(ProjectPriority.slug)
            .where(ProjectPriority.project_id == project.id)
            .order_by(ProjectPriority.sort_order)
        )
        priorities = list(prio_res.scalars().all())

        template_csv = generate_issue_import_template(
            project_key=project.identifier,
            state_names=states,
            priority_names=priorities,
        )

        filename = f"{project.identifier}-import-template.csv"
        return Response(
            content=template_csv,
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )


@router.get(
    "/workspaces/{workspace_ref}/issues/import-template.csv",
    summary="Download workspace-generic CSV import template",
    response_class=Response,
    responses={
        200: {
            "content": {"text/csv": {}},
            "description": "Generic workspace issue import template",
        }
    },
)
async def download_workspace_import_template(
    workspace_ref: str,
    _caller: Caller,
    session: Session,
) -> Response:
    """Return generic RFC 4180 CSV template for importing issues into workspace."""
    async with timing_floor(floor_ms=25.0):
        ws_res = await session.execute(
            text(
                "SELECT id, slug FROM workspaces WHERE id = resolve_workspace_by_slug_or_id(:ident)"
            ),
            {"ident": workspace_ref},
        )
        ws_row = ws_res.mappings().one_or_none()
        if not ws_row:
            raise ProblemException(
                code="WORKSPACE_NOT_FOUND",
                status=status.HTTP_404_NOT_FOUND,
                title="Workspace Not Found",
                detail=f"Workspace '{workspace_ref}' not found.",
            )

        template_csv = generate_issue_import_template(
            project_key="PROJECT",
            state_names=["Backlog", "Todo", "In Progress", "Done", "Cancelled"],
            priority_names=["urgent", "high", "medium", "low", "none"],
        )

        filename = f"{ws_row['slug']}-import-template.csv"
        return Response(
            content=template_csv,
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )


async def _execute_export_query(  # noqa: C901, PLR0912, PLR0915
    session: AsyncSession,
    caller: PrincipalContext,
    project_id: uuid.UUID | None,
    req: IssueExportRequest,
) -> list[dict[str, Any]]:
    """Query issues matching search/navigator filters and return serializable row dicts."""
    stmt = (
        select(
            Issue,
            Project.identifier.label("project_identifier"),
            WorkflowState.name.label("state_name"),
            ProjectPriority.slug.label("priority_slug"),
            Cycle.name.label("cycle_name"),
        )
        .join(Project, Project.id == Issue.project_id)
        .join(WorkflowState, WorkflowState.id == Issue.state_id)
        .join(ProjectPriority, ProjectPriority.id == Issue.priority_id)
        .outerjoin(Cycle, Cycle.id == Issue.cycle_id)
    )

    if project_id is not None:
        stmt = stmt.where(Issue.project_id == project_id)
    else:
        stmt = stmt.where(Issue.workspace_id == caller.workspace_id)

    if req.state_ids:
        state_uuids = [uuid.UUID(sid) for sid in req.state_ids if sid]
        stmt = stmt.where(Issue.state_id.in_(state_uuids))

    if req.priorities:
        stmt = stmt.where(ProjectPriority.slug.in_([p.lower() for p in req.priorities]))

    if req.cycle_id:
        stmt = stmt.where(Issue.cycle_id == uuid.UUID(req.cycle_id))

    if req.module_id:
        stmt = stmt.join(IssueModule, IssueModule.issue_id == Issue.id).where(
            IssueModule.module_id == uuid.UUID(req.module_id)
        )

    if req.label_ids:
        label_uuids = [uuid.UUID(lid) for lid in req.label_ids if lid]
        stmt = stmt.join(IssueLabel, IssueLabel.issue_id == Issue.id).where(
            IssueLabel.label_id.in_(label_uuids)
        )

    if req.issue_ids:
        # Match by key sequence or UUID
        seqs = [
            int(i.split("-")[-1]) for i in req.issue_ids if "-" in i and i.split("-")[-1].isdigit()
        ]
        stmt = stmt.where(Issue.sequence_id.in_(seqs))

    if req.q:
        search_filter = f"%{req.q.strip()}%"
        stmt = stmt.where(Issue.summary.ilike(search_filter))

    # Sorting
    if req.sort_by == "sequence_id":
        stmt = stmt.order_by(
            desc(Issue.sequence_id) if req.sort_dir == "desc" else Issue.sequence_id
        )
    elif req.sort_by == "board_rank":
        stmt = stmt.order_by(desc(Issue.board_rank) if req.sort_dir == "desc" else Issue.board_rank)
    else:
        stmt = stmt.order_by(
            desc(Issue.sequence_id) if req.sort_dir == "desc" else Issue.sequence_id
        )

    result = await session.execute(stmt)
    records = result.all()

    issue_ids = [r[0].id for r in records]

    # Batch fetch assignees, labels, modules for exported issues
    assignees_by_issue: dict[uuid.UUID, list[str]] = {iid: [] for iid in issue_ids}
    if issue_ids:
        asg_q = await session.execute(
            select(IssueAssignee.issue_id, IssueAssignee.free_text_assignee, Principal.display_name)
            .outerjoin(Principal, Principal.id == IssueAssignee.principal_id)
            .where(IssueAssignee.issue_id.in_(issue_ids))
        )
        for asg_row in asg_q.all():
            name = asg_row[2] or asg_row[1] or ""
            if name:
                assignees_by_issue[asg_row[0]].append(name)

    labels_by_issue: dict[uuid.UUID, list[str]] = {iid: [] for iid in issue_ids}
    if issue_ids:
        lbl_q = await session.execute(
            select(IssueLabel.issue_id, ProjectLabel.name)
            .join(ProjectLabel, ProjectLabel.id == IssueLabel.label_id)
            .where(IssueLabel.issue_id.in_(issue_ids))
        )
        for lbl_row in lbl_q.all():
            labels_by_issue[lbl_row[0]].append(lbl_row[1])

    modules_by_issue: dict[uuid.UUID, list[str]] = {iid: [] for iid in issue_ids}
    if issue_ids:
        mod_q = await session.execute(
            select(IssueModule.issue_id, Module.name)
            .join(Module, Module.id == IssueModule.module_id)
            .where(IssueModule.issue_id.in_(issue_ids))
        )
        for mod_row in mod_q.all():
            modules_by_issue[mod_row[0]].append(mod_row[1])

    rows: list[dict[str, Any]] = []
    for r in records:
        issue: Issue = r[0]
        proj_ident: str = r[1]
        state_name: str = r[2]
        priority_slug: str = r[3]
        cycle_name: str | None = r[4]

        rows.append(
            {
                "key": f"{proj_ident}-{issue.sequence_id}",
                "project_key": proj_ident,
                "summary": issue.summary,
                "description_markdown": issue.description_markdown,
                "state": state_name,
                "priority": priority_slug,
                "assignees": ", ".join(assignees_by_issue.get(issue.id, [])),
                "labels": ", ".join(labels_by_issue.get(issue.id, [])),
                "cycle": cycle_name or "",
                "modules": ", ".join(modules_by_issue.get(issue.id, [])),
                "parent_key": "",
                "start_date": issue.start_date.isoformat() if issue.start_date else "",
                "due_date": issue.due_date.isoformat() if issue.due_date else "",
                "created_at": "",
                "updated_at": "",
                "custom_fields_json": "{}",
            }
        )

    return rows


@router.post(
    "/projects/{project_ref}/issues/export",
    summary="Export issues in project to CSV or Password-protected ZIP (AES-256)",
    response_class=Response,
)
async def export_project_issues(
    project_ref: str,
    req: IssueExportRequest,
    caller: Caller,
    session: Session,
    taint_recorder: Annotated[TaintRecorder, Depends(get_taint_recorder)],
) -> Response:
    """Export project issues matching filters to CSV or Password-protected ZIP (AES-256)."""
    async with timing_floor(floor_ms=25.0):
        project = await get_project_or_404(session, caller, project_ref)
        await _check_export_governance(session, caller, project.workspace_id, project.id)

        rows = await _execute_export_query(session, caller, project.id, req)
        await taint_recorder.record_project_ids([project.id])

        csv_content = export_issues_to_csv(rows)

        await record_activity(
            session,
            workspace_id=project.workspace_id,
            object_id=project.id,
            actor_principal_id=caller.principal_id,
            event_type=ActivityEventType.ISSUE_BULK_EXPORTED,
            payload={
                "action": "issue.bulk_export",
                "project_id": str(project.id),
                "format": req.format,
                "count": len(rows),
            },
        )
        await session.commit()

        if req.format == "zip_csv":
            if not req.zip_password:
                raise ProblemException(
                    code="VALIDATION_FAILED",
                    status=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    title="Validation Failed",
                    detail="zip_password is required when format is zip_csv.",
                )
            if len(req.zip_password) < MIN_PASSWORD_LENGTH:
                raise ProblemException(
                    code="VALIDATION_FAILED",
                    status=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    title="Validation Failed",
                    detail=f"zip_password must be at least {MIN_PASSWORD_LENGTH} characters.",
                )
            zip_bytes = create_winzip_aes256_zip(
                {f"{project.identifier}-issues.csv": csv_content.encode("utf-8")},
                req.zip_password,
            )
            zip_disp = f'attachment; filename="{project.identifier}-issues-export.zip"'
            return Response(
                content=zip_bytes,
                media_type="application/zip",
                headers={"Content-Disposition": zip_disp},
            )

        csv_disp = f'attachment; filename="{project.identifier}-issues-export.csv"'
        return Response(
            content=csv_content,
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": csv_disp},
        )


@router.post(
    "/workspaces/{workspace_ref}/issues/export",
    summary="Export issues in workspace to CSV or Password-protected ZIP (AES-256)",
    response_class=Response,
)
async def export_workspace_issues(
    workspace_ref: str,
    req: IssueExportRequest,
    caller: Caller,
    session: Session,
    taint_recorder: Annotated[TaintRecorder, Depends(get_taint_recorder)],
) -> Response:
    """Export workspace issues matching filters to CSV or Password-protected ZIP (AES-256)."""
    async with timing_floor(floor_ms=25.0):
        ws_res = await session.execute(
            text(
                "SELECT id, slug FROM workspaces WHERE id = resolve_workspace_by_slug_or_id(:ident)"
            ),
            {"ident": workspace_ref},
        )
        ws_row = ws_res.mappings().one_or_none()
        if not ws_row:
            raise ProblemException(
                code="WORKSPACE_NOT_FOUND",
                status=status.HTTP_404_NOT_FOUND,
                title="Workspace Not Found",
                detail=f"Workspace '{workspace_ref}' not found.",
            )

        ws_id = ws_row["id"]
        ws_slug = ws_row["slug"]
        await _check_export_governance(session, caller, ws_id)

        rows = await _execute_export_query(session, caller, None, req)

        pids = {r["project_key"] for r in rows if r.get("project_key")}
        if pids:
            await taint_recorder.record_project_ids(pids)

        csv_content = export_issues_to_csv(rows)

        await record_activity(
            session,
            workspace_id=ws_id,
            object_id=ws_id,
            actor_principal_id=caller.principal_id,
            event_type=ActivityEventType.ISSUE_BULK_EXPORTED,
            payload={
                "action": "issue.bulk_export",
                "workspace_id": str(ws_id),
                "format": req.format,
                "count": len(rows),
            },
        )
        await session.commit()

        if req.format == "zip_csv":
            if not req.zip_password:
                raise ProblemException(
                    code="VALIDATION_FAILED",
                    status=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    title="Validation Failed",
                    detail="zip_password is required when format is zip_csv.",
                )
            if len(req.zip_password) < MIN_PASSWORD_LENGTH:
                raise ProblemException(
                    code="VALIDATION_FAILED",
                    status=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    title="Validation Failed",
                    detail=f"zip_password must be at least {MIN_PASSWORD_LENGTH} characters.",
                )
            zip_bytes = create_winzip_aes256_zip(
                {f"{ws_slug}-issues.csv": csv_content.encode("utf-8")},
                req.zip_password,
            )
            return Response(
                content=zip_bytes,
                media_type="application/zip",
                headers={
                    "Content-Disposition": f'attachment; filename="{ws_slug}-issues-export.zip"'
                },
            )

        return Response(
            content=csv_content,
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{ws_slug}-issues-export.csv"'},
        )


@router.post(
    "/projects/{project_ref}/issues/import",
    response_model=CsvImportDiffReport,
    summary="Import issues from CSV or Password-protected ZIP (AES-256) into project",
)
async def import_project_issues(  # noqa: C901, PLR0912
    project_ref: str,
    request: Request,
    caller: Caller,
    session: Session,
    *,
    dry_run: Annotated[
        bool, Query(description="Simulate import and return diff without committing")
    ] = True,
) -> CsvImportDiffReport:
    """Import issues from CSV or Password-protected ZIP (AES-256) archive into project."""
    async with timing_floor(floor_ms=25.0):
        project = await get_project_or_404(session, caller, project_ref)
        await _check_import_governance(session, caller, project.workspace_id, project.id)

        body_bytes = await request.body()
        content_type_header = request.headers.get("content-type", "")
        filename = request.query_params.get("filename", "")
        zip_password = request.query_params.get("zip_password")
        file_bytes = body_bytes

        if "multipart/form-data" in content_type_header.lower():
            msg_bytes = (
                b"Content-Type: " + content_type_header.encode("latin-1") + b"\r\n\r\n" + body_bytes
            )
            parsed_msg = email.message_from_bytes(msg_bytes)
            if parsed_msg.is_multipart():
                parts = parsed_msg.get_payload()
                if isinstance(parts, list):
                    for part in parts:
                        if not isinstance(part, email.message.Message):
                            continue
                        name = part.get_param("name", header="content-disposition")
                        payload_raw = part.get_payload(decode=True)
                        if not isinstance(payload_raw, bytes):
                            continue
                        if name == "zip_password":
                            zip_password = (
                                payload_raw.decode("utf-8", errors="replace").strip() or None
                            )
                        elif name in ("file", "archive") or part.get_filename():
                            filename = part.get_filename() or filename
                            file_bytes = payload_raw

        if not file_bytes:
            raise ProblemException(
                code="VALIDATION_FAILED",
                status=status.HTTP_422_UNPROCESSABLE_CONTENT,
                title="Validation Failed",
                detail="Uploaded file is empty.",
            )

        # Detect ZIP archive
        csv_text: str = ""
        is_zip = filename.lower().endswith(".zip") or file_bytes.startswith(b"PK")

        if is_zip:
            try:
                extracted = extract_winzip_aes256_zip(file_bytes, password=zip_password)
            except Exception as exc:
                raise ProblemException(
                    code="ZIP_EXTRACTION_FAILED",
                    status=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    title="ZIP Extraction Failed",
                    detail=f"Could not extract encrypted ZIP archive: {exc}",
                ) from exc

            # Find .csv entry
            csv_entry = next(
                (content for name, content in extracted.items() if name.lower().endswith(".csv")),
                None,
            )
            if csv_entry is None:
                raise ProblemException(
                    code="CSV_NOT_FOUND_IN_ZIP",
                    status=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    title="CSV Not Found In Archive",
                    detail="No .csv file found inside the ZIP archive.",
                )
            csv_text = csv_entry.decode("utf-8", errors="replace")
        else:
            try:
                csv_text = file_bytes.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise ProblemException(
                    code="INVALID_ENCODING",
                    status=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    title="Invalid Encoding",
                    detail="File must be encoded in UTF-8.",
                ) from exc

        rows = parse_issues_from_csv(csv_text)
        report = await process_issue_import(session, caller, project, rows, dry_run=dry_run)

        if not dry_run and not report.errors:
            await record_activity(
                session,
                workspace_id=project.workspace_id,
                object_id=project.id,
                actor_principal_id=caller.principal_id,
                event_type=ActivityEventType.ISSUE_BULK_IMPORTED,
                payload={
                    "action": "issue.bulk_import",
                    "project_id": str(project.id),
                    "to_create": report.to_create,
                    "to_update": report.to_update,
                },
            )
            await session.commit()

        return report
