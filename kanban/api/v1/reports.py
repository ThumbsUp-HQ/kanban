# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""REST API router for Jinja2 Report Templates and Multi-Format Export Engine (KB-JINJA-REPORTS)."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from database.models.issues import Issue
from database.models.principals import Principal
from database.models.projects import Project, ProjectPriority, WorkflowState
from database.models.report_template import ReportTemplate
from database.models.spine import ObjectRecord, Workspace
from database.models.workspace_settings import WorkspaceSettings
from kanban.api.deps import PrincipalContext, get_principal, get_rls_session
from kanban.api.problems import ProblemException
from kanban.api.timing import timing_floor
from kanban.api.v1.schemas.reports import (
    ReportGenerateRequest,
    ReportPreviewRequest,
    ReportPreviewResponse,
    ReportTemplateCreateRequest,
    ReportTemplateListResponse,
    ReportTemplateResponse,
    ReportTemplateUpdateRequest,
)
from kanban.reports.renderers import render_html, render_report_bundle
from kanban.reports.sandbox import (
    HardenedSandboxedEnvironment,
    ReportContext,
    ReportIssueRow,
    build_report_stats,
    render_sandboxed_template,
)
from kanban.reports.zip_packaging import create_aes256_zip
from kanban.services.activity import ActivityEventType, record_activity
from kanban.settings import get_settings

logger = logging.getLogger(__name__)

router = APIRouter(tags=["reports"])

Caller = Annotated[PrincipalContext, Depends(get_principal)]
Session = Annotated[AsyncSession, Depends(get_rls_session)]

_MAX_TEMPLATE_BYTES = 131072
_MAX_EXPORT_ISSUES = 5000
_DEFAULT_FORMATS = ["PDF", "XLSX", "CSV", "DOCX", "ODT", "HTML", "MD"]
_PREVIEW_ISSUE_LIMIT = 5


async def _resolve_workspace_id(
    session: AsyncSession,
    caller: PrincipalContext,
    workspace_ref: str,
) -> uuid.UUID:
    """Resolve workspace reference (UUID or slug) under caller scope."""
    try:
        parsed_uuid = uuid.UUID(workspace_ref)
        if parsed_uuid == caller.workspace_id:
            return caller.workspace_id
        if caller.is_server_admin:
            stmt = select(Workspace.id).where(Workspace.id == parsed_uuid)
            ws_id = (await session.execute(stmt)).scalar_one_or_none()
            if ws_id is not None:
                return ws_id
    except ValueError:
        pass

    stmt_func = text("SELECT resolve_workspace_by_slug_or_id(:ident)")
    res_ws = (await session.execute(stmt_func, {"ident": workspace_ref})).scalar_one_or_none()
    if res_ws is not None:
        res_uuid = uuid.UUID(str(res_ws))
        if caller.is_server_admin or res_uuid == caller.workspace_id:
            return res_uuid

    if workspace_ref.strip().lower() in ("default", "current", "~", "@"):
        return caller.workspace_id

    raise ProblemException(
        code="NOT_FOUND",
        status=404,
        title="Workspace Not Found",
        detail=f"Workspace '{workspace_ref}' not found.",
    )


async def _resolve_project_id(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    project_ref: str,
) -> tuple[uuid.UUID, str]:
    """Resolve project reference (UUID or identifier) to (project_id, identifier)."""
    try:
        parsed_uuid = uuid.UUID(project_ref)
        stmt = select(Project.id, Project.identifier).where(
            Project.id == parsed_uuid,
            Project.workspace_id == workspace_id,
        )
        row = (await session.execute(stmt)).first()
        if row is not None:
            return row[0], row[1]
    except ValueError:
        pass

    stmt_ident = select(Project.id, Project.identifier).where(
        Project.identifier == project_ref.upper(),
        Project.workspace_id == workspace_id,
    )
    row = (await session.execute(stmt_ident)).first()
    if row is not None:
        return row[0], row[1]

    raise ProblemException(
        code="NOT_FOUND",
        status=404,
        title="Project Not Found",
        detail=f"Project '{project_ref}' not found in workspace.",
    )


async def _check_report_governance(
    session: AsyncSession,
    caller: PrincipalContext,
    workspace_id: uuid.UUID,
    project_id: uuid.UUID | None = None,
) -> None:
    """Enforce 3-tier governance: System setting -> Workspace setting -> Role permission."""
    settings = get_settings()
    enabled_templates = getattr(settings, "enable_report_templates", True)
    enabled_exports = getattr(settings, "enable_issue_export", True)
    if not enabled_templates or not enabled_exports:
        raise ProblemException(
            code="REPORT_EXPORT_DISABLED",
            status=403,
            title="Report Export Disabled",
            detail="Report templates and exports are disabled system-wide.",
        )

    ws_settings = (
        await session.execute(
            select(WorkspaceSettings).where(WorkspaceSettings.workspace_id == workspace_id)
        )
    ).scalar_one_or_none()

    if ws_settings is not None and not ws_settings.report_export_enabled:
        raise ProblemException(
            code="REPORT_EXPORT_DISABLED",
            status=403,
            title="Report Export Disabled",
            detail="Report export is disabled for this workspace.",
        )

    if caller.is_server_admin:
        return

    allowed_roles = ws_settings.report_export_allowed_roles if ws_settings else ["ADMIN", "MEMBER"]
    expanded_roles: set[str] = set()
    for role in allowed_roles:
        r_upper = role.upper()
        if r_upper == "ADMIN":
            expanded_roles.update({"SERVER_ADMIN", "WORKSPACE_ADMIN", "PROJECT_ADMIN", "ADMIN"})
        elif r_upper == "MEMBER":
            expanded_roles.update(
                {
                    "WORKSPACE_MEMBER",
                    "PROJECT_MEMBER",
                    "MEMBER",
                    "SERVER_ADMIN",
                    "WORKSPACE_ADMIN",
                    "PROJECT_ADMIN",
                }
            )
        elif r_upper == "VIEWER":
            expanded_roles.update(
                {
                    "PROJECT_VIEWER",
                    "VIEWER",
                    "WORKSPACE_MEMBER",
                    "PROJECT_MEMBER",
                    "MEMBER",
                    "SERVER_ADMIN",
                    "WORKSPACE_ADMIN",
                    "PROJECT_ADMIN",
                }
            )
        else:
            expanded_roles.add(r_upper)

    role_check_stmt = text("SELECT app_principal_has_role(:p_id, :roles)")
    role_res = await session.execute(
        role_check_stmt, {"p_id": project_id, "roles": list(expanded_roles)}
    )
    has_role = bool(role_res.scalar_one())
    if not has_role:
        raise ProblemException(
            code="INSUFFICIENT_CAPABILITY",
            status=403,
            title="Insufficient Capability",
            detail="Your role is not permitted to export reports.",
        )


async def _require_template_admin(session: AsyncSession, caller: PrincipalContext) -> None:
    """Verify caller possesses WORKSPACE_ADMIN or SERVER_ADMIN role to manage templates."""
    if caller.is_server_admin:
        return
    stmt = text("SELECT app_principal_has_role(NULL, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN'])")
    is_admin = bool((await session.execute(stmt)).scalar_one())
    if not is_admin:
        raise ProblemException(
            code="INSUFFICIENT_CAPABILITY",
            status=403,
            title="Insufficient Capability",
            detail="Managing report templates requires WORKSPACE_ADMIN or SERVER_ADMIN role.",
        )


async def _find_template_by_ref(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    template_ref: str,
) -> ReportTemplate:
    """Find a template by UUID or slug within the workspace."""
    try:
        parsed_uuid = uuid.UUID(template_ref)
        stmt = select(ReportTemplate).where(
            ReportTemplate.workspace_id == workspace_id,
            ReportTemplate.id == parsed_uuid,
        )
        tpl = (await session.execute(stmt)).scalar_one_or_none()
        if tpl is not None:
            return tpl
    except ValueError:
        pass

    stmt_slug = select(ReportTemplate).where(
        ReportTemplate.workspace_id == workspace_id,
        ReportTemplate.slug == template_ref,
    )
    tpl = (await session.execute(stmt_slug)).scalar_one_or_none()
    if tpl is not None:
        return tpl

    raise ProblemException(
        code="NOT_FOUND",
        status=404,
        title="Report Template Not Found",
        detail=f"Report template '{template_ref}' not found in workspace.",
    )


async def _fetch_issue_rows(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    project_id: uuid.UUID | None = None,
    issue_ids: list[uuid.UUID] | None = None,
    limit: int = _MAX_EXPORT_ISSUES,
) -> tuple[list[ReportIssueRow], set[str]]:
    """Fetch matching issues under RLS, convert to ReportIssueRow, and return project ids."""
    stmt = (
        select(
            Issue.id,
            Issue.sequence_id,
            Issue.summary,
            Issue.description_markdown,
            ObjectRecord.created_at,
            ObjectRecord.updated_at,
            Issue.due_date,
            Project.identifier.label("project_identifier"),
            WorkflowState.name.label("state_name"),
            ProjectPriority.label.label("priority_label"),
            Principal.display_name.label("creator_name"),
        )
        .join(ObjectRecord, Issue.id == ObjectRecord.id)
        .join(Project, Issue.project_id == Project.id)
        .outerjoin(WorkflowState, Issue.state_id == WorkflowState.id)
        .outerjoin(ProjectPriority, Issue.priority_id == ProjectPriority.id)
        .outerjoin(Principal, Issue.created_by_id == Principal.id)
        .where(Issue.workspace_id == workspace_id)
    )

    if project_id is not None:
        stmt = stmt.where(Issue.project_id == project_id)

    if issue_ids:
        stmt = stmt.where(Issue.id.in_(issue_ids))

    stmt = stmt.order_by(ObjectRecord.created_at.desc()).limit(limit)

    result = await session.execute(stmt)
    rows = result.all()

    issue_rows: list[ReportIssueRow] = []
    project_identifiers: set[str] = set()

    for r in rows:
        proj_ident = r.project_identifier or "ISSUE"
        project_identifiers.add(proj_ident)
        identifier = f"{proj_ident}-{r.sequence_id}"
        created_str = r.created_at.strftime("%Y-%m-%d %H:%M UTC") if r.created_at else ""
        due_str = r.due_date.strftime("%Y-%m-%d") if r.due_date else ""

        issue_rows.append(
            ReportIssueRow(
                id=str(r.id),
                key=identifier,
                sequence_number=r.sequence_id,
                summary=r.summary,
                description_markdown=r.description_markdown or "",
                state=r.state_name or "Backlog",
                priority=r.priority_label or "Normal",
                assignees=(),
                created_date=created_str,
                due_date=due_str or None,
                labels=(),
                cycle=None,
                modules=(),
            )
        )

    return issue_rows, project_identifiers


@router.get(
    "/workspaces/{workspace_ref}/report-templates",
    response_model=ReportTemplateListResponse,
    summary="List report templates in workspace",
)
async def list_report_templates(
    workspace_ref: str,
    caller: Caller,
    session: Session,
    project_ref: Annotated[str | None, Query(description="Optional project scope filter")] = None,
) -> ReportTemplateListResponse:
    """List built-in and workspace custom report templates visible to caller."""
    async with timing_floor(floor_ms=25.0):
        ws_id = await _resolve_workspace_id(session, caller, workspace_ref)
        project_id: uuid.UUID | None = None
        if project_ref:
            project_id, _ = await _resolve_project_id(session, ws_id, project_ref)

        stmt = select(ReportTemplate).where(ReportTemplate.workspace_id == ws_id)
        if project_id:
            stmt = stmt.where(
                (ReportTemplate.project_id.is_(None)) | (ReportTemplate.project_id == project_id)
            )
        stmt = stmt.order_by(ReportTemplate.is_builtin.desc(), ReportTemplate.name.asc())

        items = list((await session.execute(stmt)).scalars().all())
        responses = [ReportTemplateResponse.model_validate(t) for t in items]
        return ReportTemplateListResponse(items=responses, total=len(responses))


@router.post(
    "/workspaces/{workspace_ref}/report-templates",
    status_code=201,
    response_model=ReportTemplateResponse,
    summary="Create custom report template",
)
async def create_report_template(
    workspace_ref: str,
    body: ReportTemplateCreateRequest,
    caller: Caller,
    session: Session,
) -> ReportTemplateResponse:
    """Create a new custom report template under workspace."""
    async with timing_floor(floor_ms=25.0):
        ws_id = await _resolve_workspace_id(session, caller, workspace_ref)
        await _require_template_admin(session, caller)

        # Validate template syntax with AST sandbox
        env = HardenedSandboxedEnvironment()
        try:
            env.parse(body.template_markdown)
        except Exception as exc:
            raise ProblemException(
                code="INVALID_TEMPLATE_SYNTAX",
                status=422,
                title="Invalid Template Syntax",
                detail=f"Template contains invalid Jinja2 syntax or restricted features: {exc}",
            ) from exc

        # Check slug uniqueness in workspace
        existing = (
            await session.execute(
                select(ReportTemplate.id).where(
                    ReportTemplate.workspace_id == ws_id,
                    ReportTemplate.slug == body.slug,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            raise ProblemException(
                code="SLUG_EXISTS",
                status=409,
                title="Template Slug Conflict",
                detail=f"Template slug '{body.slug}' already exists in workspace.",
            )

        new_tpl = ReportTemplate(
            workspace_id=ws_id,
            project_id=body.project_id,
            slug=body.slug,
            name=body.name,
            description=body.description,
            is_builtin=False,
            template_markdown=body.template_markdown,
            parameters_schema_json=body.parameters_schema_json or {},
            csv_columns_json=body.csv_columns_json or [],
            allowed_formats=body.allowed_formats or _DEFAULT_FORMATS,
            created_by_user_id=caller.principal_id,
        )
        session.add(new_tpl)
        await session.flush()
        await session.refresh(new_tpl)

        await record_activity(
            session,
            workspace_id=ws_id,
            actor_principal_id=caller.principal_id,
            event_type=ActivityEventType.REPORT_TEMPLATE_CREATED,
            payload={
                "template_id": str(new_tpl.id),
                "slug": new_tpl.slug,
                "name": new_tpl.name,
            },
        )

        return ReportTemplateResponse.model_validate(new_tpl)


@router.get(
    "/workspaces/{workspace_ref}/report-templates/{template_ref}",
    response_model=ReportTemplateResponse,
    summary="Get single report template",
)
async def get_report_template(
    workspace_ref: str,
    template_ref: str,
    caller: Caller,
    session: Session,
) -> ReportTemplateResponse:
    """Retrieve full descriptor and markdown of a report template."""
    async with timing_floor(floor_ms=25.0):
        ws_id = await _resolve_workspace_id(session, caller, workspace_ref)
        tpl = await _find_template_by_ref(session, ws_id, template_ref)
        return ReportTemplateResponse.model_validate(tpl)


@router.patch(
    "/workspaces/{workspace_ref}/report-templates/{template_ref}",
    response_model=ReportTemplateResponse,
    summary="Update custom report template",
)
async def update_report_template(
    workspace_ref: str,
    template_ref: str,
    body: ReportTemplateUpdateRequest,
    caller: Caller,
    session: Session,
) -> ReportTemplateResponse:
    """Update a custom report template (built-in templates are immutable)."""
    async with timing_floor(floor_ms=25.0):
        ws_id = await _resolve_workspace_id(session, caller, workspace_ref)
        await _require_template_admin(session, caller)
        tpl = await _find_template_by_ref(session, ws_id, template_ref)

        if tpl.is_builtin:
            raise ProblemException(
                code="BUILTIN_IMMUTABLE",
                status=403,
                title="Built-in Template Immutable",
                detail="Built-in report templates cannot be modified.",
            )

        if body.template_markdown is not None:
            env = HardenedSandboxedEnvironment()
            try:
                env.parse(body.template_markdown)
            except Exception as exc:
                raise ProblemException(
                    code="INVALID_TEMPLATE_SYNTAX",
                    status=422,
                    title="Invalid Template Syntax",
                    detail=f"Template contains invalid Jinja2 syntax or restricted features: {exc}",
                ) from exc
            tpl.template_markdown = body.template_markdown

        if body.name is not None:
            tpl.name = body.name
        if body.description is not None:
            tpl.description = body.description
        if body.parameters_schema_json is not None:
            tpl.parameters_schema_json = body.parameters_schema_json
        if body.csv_columns_json is not None:
            tpl.csv_columns_json = body.csv_columns_json
        if body.allowed_formats is not None:
            tpl.allowed_formats = body.allowed_formats

        tpl.updated_at = datetime.now(UTC)
        await session.flush()
        await session.refresh(tpl)

        await record_activity(
            session,
            workspace_id=ws_id,
            actor_principal_id=caller.principal_id,
            event_type=ActivityEventType.REPORT_TEMPLATE_UPDATED,
            payload={
                "template_id": str(tpl.id),
                "slug": tpl.slug,
                "name": tpl.name,
            },
        )

        return ReportTemplateResponse.model_validate(tpl)


@router.delete(
    "/workspaces/{workspace_ref}/report-templates/{template_ref}",
    status_code=204,
    summary="Delete custom report template",
)
async def delete_report_template(
    workspace_ref: str,
    template_ref: str,
    caller: Caller,
    session: Session,
) -> Response:
    """Delete a custom report template (built-in templates cannot be deleted)."""
    async with timing_floor(floor_ms=25.0):
        ws_id = await _resolve_workspace_id(session, caller, workspace_ref)
        await _require_template_admin(session, caller)
        tpl = await _find_template_by_ref(session, ws_id, template_ref)

        if tpl.is_builtin:
            raise ProblemException(
                code="BUILTIN_IMMUTABLE",
                status=403,
                title="Built-in Template Immutable",
                detail="Built-in report templates cannot be deleted.",
            )

        tpl_id = str(tpl.id)
        tpl_slug = tpl.slug
        await session.delete(tpl)
        await session.flush()

        await record_activity(
            session,
            workspace_id=ws_id,
            actor_principal_id=caller.principal_id,
            event_type=ActivityEventType.REPORT_TEMPLATE_DELETED,
            payload={"template_id": tpl_id, "slug": tpl_slug},
        )

        return Response(status_code=204)


@router.post(
    "/workspaces/{workspace_ref}/reports/preview",
    response_model=ReportPreviewResponse,
    summary="Render fast live preview of report template",
)
async def preview_report(
    workspace_ref: str,
    body: ReportPreviewRequest,
    caller: Caller,
    session: Session,
) -> ReportPreviewResponse:
    """Render a live preview of a report against up to 5 matching issues."""
    async with timing_floor(floor_ms=25.0):
        ws_id = await _resolve_workspace_id(session, caller, workspace_ref)
        proj_id: uuid.UUID | None = None
        if body.project_ref:
            proj_id, _ = await _resolve_project_id(session, ws_id, body.project_ref)

        await _check_report_governance(session, caller, ws_id, proj_id)

        template_md: str
        if body.template_markdown:
            template_md = body.template_markdown
        elif body.template_ref:
            tpl = await _find_template_by_ref(session, ws_id, body.template_ref)
            template_md = tpl.template_markdown
        else:
            raise ProblemException(
                code="MISSING_TEMPLATE",
                status=422,
                title="Missing Template",
                detail="Either template_ref or template_markdown must be provided.",
            )

        issues, _project_idents = await _fetch_issue_rows(
            session=session,
            workspace_id=ws_id,
            project_id=proj_id,
            issue_ids=body.issue_ids,
            limit=_PREVIEW_ISSUE_LIMIT,
        )

        # Render preview bundle
        context = ReportContext(
            workspace_name="Preview Workspace",
            project_name="Preview Project" if proj_id else None,
            issues=issues,
            stats=build_report_stats(issues),
            parameters=body.parameters,
        )
        rendered_md = render_sandboxed_template(template_md, context)
        if body.format.upper() == "HTML":
            preview_str = render_html(rendered_md, context).decode("utf-8")
        else:
            preview_str = rendered_md

        return ReportPreviewResponse(
            rendered_content=preview_str,
            format=body.format,
            issue_count=len(issues),
        )


@router.post(
    "/workspaces/{workspace_ref}/reports/generate",
    summary="Generate full report export for workspace",
)
async def generate_workspace_report(
    workspace_ref: str,
    body: ReportGenerateRequest,
    caller: Caller,
    session: Session,
) -> Response:
    """Generate multi-format document report export for workspace issues."""
    async with timing_floor(floor_ms=25.0):
        ws_id = await _resolve_workspace_id(session, caller, workspace_ref)
        await _check_report_governance(session, caller, ws_id, None)
        tpl = await _find_template_by_ref(session, ws_id, body.template_ref)

        format_norm = body.format.upper()
        if format_norm not in [f.upper() for f in tpl.allowed_formats]:
            raise ProblemException(
                code="FORMAT_NOT_ALLOWED",
                status=422,
                title="Format Not Allowed",
                detail=f"Format '{body.format}' is not permitted for template '{tpl.name}'.",
            )

        issues, _project_idents = await _fetch_issue_rows(
            session=session,
            workspace_id=ws_id,
            project_id=None,
            issue_ids=body.issue_ids,
            limit=_MAX_EXPORT_ISSUES,
        )

        ws_name = "Workspace"
        ws_obj = (
            await session.execute(select(Workspace).where(Workspace.id == ws_id))
        ).scalar_one_or_none()
        if ws_obj:
            ws_name = ws_obj.name

        context = ReportContext(
            workspace_name=ws_name,
            project_name=None,
            issues=issues,
            stats=build_report_stats(issues),
            parameters=body.parameters,
        )
        rendered_md = render_sandboxed_template(tpl.template_markdown, context)
        file_bytes, content_type, ext = render_report_bundle(
            format_type=format_norm.lower(),  # type: ignore[arg-type]
            rendered_markdown=rendered_md,
            context=context,
            custom_columns=tpl.csv_columns_json,
        )
        timestamp_str = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        final_filename = f"{tpl.slug}_{timestamp_str}.{ext}"

        # Optional WinZip AE-2 AES-256 encrypted zip packaging
        if body.zip_password:
            zip_bytes = create_aes256_zip([(final_filename, file_bytes)], body.zip_password)
            file_bytes = zip_bytes
            final_filename = f"{final_filename}.zip"
            content_type = "application/zip"

        await record_activity(
            session,
            workspace_id=ws_id,
            actor_principal_id=caller.principal_id,
            event_type=ActivityEventType.REPORT_EXPORTED,
            payload={
                "template_slug": tpl.slug,
                "format": format_norm,
                "issue_count": len(issues),
                "is_encrypted": bool(body.zip_password),
                "filename": final_filename,
            },
        )

        headers = {
            "Content-Disposition": f'attachment; filename="{final_filename}"',
            "X-Report-Format": format_norm,
            "X-Report-Issues-Count": str(len(issues)),
        }
        return Response(content=file_bytes, media_type=content_type, headers=headers)


@router.post(
    "/projects/{project_ref}/reports/generate",
    summary="Generate full report export for project",
)
async def generate_project_report(
    project_ref: str,
    body: ReportGenerateRequest,
    caller: Caller,
    session: Session,
) -> Response:
    """Generate multi-format document report export for project issues."""
    async with timing_floor(floor_ms=25.0):
        # Resolve project under caller's current workspace
        proj_id, proj_ident = await _resolve_project_id(session, caller.workspace_id, project_ref)
        await _check_report_governance(session, caller, caller.workspace_id, proj_id)
        tpl = await _find_template_by_ref(session, caller.workspace_id, body.template_ref)

        format_norm = body.format.upper()
        if format_norm not in [f.upper() for f in tpl.allowed_formats]:
            raise ProblemException(
                code="FORMAT_NOT_ALLOWED",
                status=422,
                title="Format Not Allowed",
                detail=f"Format '{body.format}' is not permitted for template '{tpl.name}'.",
            )

        issues, _project_idents = await _fetch_issue_rows(
            session=session,
            workspace_id=caller.workspace_id,
            project_id=proj_id,
            issue_ids=body.issue_ids,
            limit=_MAX_EXPORT_ISSUES,
        )

        proj_name = proj_ident
        proj_obj = (
            await session.execute(select(Project).where(Project.id == proj_id))
        ).scalar_one_or_none()
        if proj_obj:
            proj_name = proj_obj.name

        context = ReportContext(
            workspace_name="Workspace",
            project_name=proj_name,
            project_key=proj_ident,
            issues=issues,
            stats=build_report_stats(issues),
            parameters=body.parameters,
        )
        rendered_md = render_sandboxed_template(tpl.template_markdown, context)
        file_bytes, content_type, ext = render_report_bundle(
            format_type=format_norm.lower(),  # type: ignore[arg-type]
            rendered_markdown=rendered_md,
            context=context,
            custom_columns=tpl.csv_columns_json,
        )
        timestamp_str = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        final_filename = f"{proj_ident.lower()}_{tpl.slug}_{timestamp_str}.{ext}"

        # Optional WinZip AE-2 AES-256 encrypted zip packaging
        if body.zip_password:
            zip_bytes = create_aes256_zip([(final_filename, file_bytes)], body.zip_password)
            file_bytes = zip_bytes
            final_filename = f"{final_filename}.zip"
            content_type = "application/zip"

        await record_activity(
            session,
            workspace_id=caller.workspace_id,
            actor_principal_id=caller.principal_id,
            event_type=ActivityEventType.REPORT_EXPORTED,
            payload={
                "project_identifier": proj_ident,
                "template_slug": tpl.slug,
                "format": format_norm,
                "issue_count": len(issues),
                "is_encrypted": bool(body.zip_password),
                "filename": final_filename,
            },
        )

        headers = {
            "Content-Disposition": f'attachment; filename="{final_filename}"',
            "X-Report-Format": format_norm,
            "X-Report-Issues-Count": str(len(issues)),
        }
        return Response(content=file_bytes, media_type=content_type, headers=headers)
