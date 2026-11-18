"""Project business logic: CRUD, module defaults and response assembly (S7.2 8c/8f/8p).

Every function runs inside the caller's RLS-bound request transaction (KB-P2-01
``get_rls_session``); no function opens its own connection. Reads rely on PostgreSQL RLS for
visibility, so an unreadable project is indistinguishable from an absent one.

Failure modes (all raised as ``ProblemException`` with a stable ``code``):
    - 404 NOT_FOUND: project absent or caller lacks VIEW (identical response).
    - 403 INSUFFICIENT_CAPABILITY: caller can view but lacks the required capability.
    - 409 PROJECT_IDENTIFIER_TAKEN, 409 MODULES_IN_USE.
    - 422 INVALID_CURSOR, IDENTIFIER_IMMUTABLE, DESCRIPTION_TOO_LARGE, MODULES_DISABLED,
      MODULE_NOT_IN_PROJECT, INVALID_CONTENT.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import re
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Final

from sqlalchemy import delete, func, select, text
from sqlalchemy.exc import IntegrityError

from database.models import Module, Project, ProjectModuleDefault
from kanban.api.problems import ProblemException, not_found
from kanban.api.v1.schemas.projects import (
    ProjectList,
    ProjectMemberAdd,
    ProjectMemberResponse,
    ProjectResponse,
)
from kanban.content import ContentNormalizeError, normalize_to_markdown
from kanban.security.access_manifest import build_access_manifest
from kanban.security.permissions import (
    Capability,
    capabilities_to_names,
    evaluate_capabilities,
    parse_token_scope_mask,
    require_capability,
)
from kanban.services.activity import ActivityEventType, JSONValue, record_activity

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy.ext.asyncio import AsyncSession

    from kanban.api.deps import PrincipalContext
    from kanban.api.v1.schemas.projects import ProjectCreate, ProjectPatch

MAX_DESCRIPTION_BYTES: Final[int] = 524288
_IDENTIFIER_RE: Final[re.Pattern[str]] = re.compile(r"^[A-Z][A-Z0-9]{1,9}$")
_UNIQUE_VIOLATION: Final[str] = "23505"


def _sha256_hex(value: str) -> str:
    """Return the lowercase SHA-256 hex digest of ``value`` encoded as UTF-8."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _problem(*, code: str, status: int, title: str, detail: str | None = None) -> ProblemException:
    """Build a ``ProblemException`` with no echoed user input."""
    return ProblemException(code=code, status=status, title=title, detail=detail)


def _is_unique_violation(exc: IntegrityError) -> bool:
    """Return True when the wrapped driver error carries SQLSTATE 23505."""
    orig = exc.orig
    candidates = (orig, getattr(orig, "__cause__", None))
    return any(
        getattr(c, "sqlstate", None) == _UNIQUE_VIOLATION
        or getattr(c, "pgcode", None) == _UNIQUE_VIOLATION
        for c in candidates
    )


def _normalize_description(raw: str) -> str:
    """Normalize Markdown and enforce the 524288 byte description cap."""
    try:
        normalized = normalize_to_markdown(raw)
    except ContentNormalizeError as exc:
        if exc.code == "CONTENT_TOO_LARGE":
            raise _problem(
                code="DESCRIPTION_TOO_LARGE", status=422, title="Description Too Large"
            ) from exc
        raise _problem(code="INVALID_CONTENT", status=422, title="Invalid Content") from exc
    except UnicodeEncodeError as exc:
        # normalize_inspect encodes before its own surrogate guard, so lone surrogates surface here.
        raise _problem(code="INVALID_CONTENT", status=422, title="Invalid Content") from exc
    if len(normalized.encode("utf-8")) > MAX_DESCRIPTION_BYTES:
        raise _problem(code="DESCRIPTION_TOO_LARGE", status=422, title="Description Too Large")
    return normalized


def encode_cursor(identifier: str) -> str:
    """Encode the last returned identifier as an opaque base64url cursor."""
    return base64.urlsafe_b64encode(identifier.encode("ascii")).decode("ascii").rstrip("=")


def decode_cursor(cursor: str) -> str:
    """Decode an opaque cursor, raising ``422 INVALID_CURSOR`` on any malformed input."""
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        identifier = base64.urlsafe_b64decode(padded.encode("ascii")).decode("ascii")
    except (binascii.Error, UnicodeError, ValueError) as exc:
        raise _problem(code="INVALID_CURSOR", status=422, title="Invalid Cursor") from exc
    if not _IDENTIFIER_RE.fullmatch(identifier):
        raise _problem(code="INVALID_CURSOR", status=422, title="Invalid Cursor")
    return identifier


async def _require_project_creator(session: AsyncSession, caller: PrincipalContext) -> None:
    """Allow only workspace or server admins holding a token scope that includes ADMIN."""
    is_admin = (
        await session.execute(
            text("SELECT app_principal_has_role(NULL, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN'])")
        )
    ).scalar_one()
    scope_ok = Capability.ADMIN in parse_token_scope_mask(caller.token_scopes)
    if caller.agent_principal_id is not None or not is_admin or not scope_ok:
        raise _problem(code="INSUFFICIENT_CAPABILITY", status=403, title="Insufficient Capability")


async def _default_module_ids(session: AsyncSession, project_id: uuid.UUID) -> list[uuid.UUID]:
    """Return the project's default module ids in stable order."""
    rows = await session.execute(
        select(ProjectModuleDefault.module_id)
        .where(ProjectModuleDefault.project_id == project_id)
        .order_by(ProjectModuleDefault.module_id)
    )
    return list(rows.scalars().all())


async def serialize_project(
    session: AsyncSession, caller: PrincipalContext, project: Project
) -> ProjectResponse:
    """Assemble the canonical response including access manifest and caller capabilities."""
    manifest = await build_access_manifest(session, caller, project.id)
    caps = await evaluate_capabilities(session, caller, project.id)
    cap_names = capabilities_to_names(caps)
    is_project_admin = "ADMIN" in cap_names

    rb_res = await session.execute(
        text(
            "SELECT role::text FROM role_bindings "
            "WHERE principal_id = :p_id AND project_id = :proj_id "
            "LIMIT 1"
        ),
        {"p_id": caller.principal_id, "proj_id": project.id},
    )
    explicit_role = rb_res.scalar_one_or_none()
    if explicit_role:
        project_role = explicit_role
    elif is_project_admin:
        project_role = "PROJECT_ADMIN"
    elif "EDIT" in cap_names:
        project_role = "MEMBER"
    elif "VIEW" in cap_names:
        project_role = "VIEWER"
    else:
        project_role = None

    return ProjectResponse(
        id=project.id,
        identifier=project.identifier,
        name=project.name,
        description_markdown=project.description_markdown,
        modules_enabled=project.modules_enabled,
        default_module_ids=await _default_module_ids(session, project.id),
        auto_archive_days=project.auto_archive_days,
        access_manifest=manifest,
        capabilities=cap_names,
        is_project_admin=is_project_admin,
        project_role=project_role,
    )


async def get_project_or_404(
    session: AsyncSession, caller: PrincipalContext, project_ref: str
) -> Project:
    """Resolve ``project_ref`` (identifier or UUID) through RLS or raise the canonical 404."""
    stmt = select(Project).where(Project.workspace_id == caller.workspace_id)
    if _IDENTIFIER_RE.fullmatch(project_ref):
        stmt = stmt.where(Project.identifier == project_ref)
    else:
        try:
            stmt = stmt.where(Project.id == uuid.UUID(project_ref))
        except ValueError:
            not_found()
    project = (await session.execute(stmt)).scalar_one_or_none()
    if project is None:
        not_found()
    return project


async def create_project(
    session: AsyncSession, caller: PrincipalContext, body: ProjectCreate
) -> ProjectResponse:
    """Create a project, seeded defaults, creator ADMIN binding and PROJECT_CREATED activity."""
    await _require_project_creator(session, caller)
    description = _normalize_description(body.description_markdown)
    project_id: uuid.UUID
    try:
        async with session.begin_nested():
            project_id = (
                await session.execute(
                    text(
                        "SELECT register_object("
                        "  CAST('project' AS object_kind), :ws, NULL, :ident, :name, :creator"
                        ")"
                    ),
                    {
                        "ws": caller.workspace_id,
                        "ident": body.identifier,
                        "name": body.name,
                        "creator": caller.principal_id,
                    },
                )
            ).scalar_one()
            session.add(
                Project(
                    id=project_id,
                    workspace_id=caller.workspace_id,
                    identifier=body.identifier,
                    name=body.name,
                    description_markdown=description,
                    modules_enabled=body.modules_enabled,
                    auto_archive_days=body.auto_archive_days,
                )
            )
            await session.flush()
            await session.execute(
                text(
                    "INSERT INTO role_bindings (workspace_id, principal_id, role, scope_type,"
                    " project_id) VALUES (:ws, :pid, CAST('PROJECT_ADMIN' AS rbac_role),"
                    " 'project', :proj)"
                ),
                {"ws": caller.workspace_id, "pid": caller.principal_id, "proj": project_id},
            )
    except IntegrityError as exc:
        if _is_unique_violation(exc):
            raise _problem(
                code="PROJECT_IDENTIFIER_TAKEN",
                status=409,
                title="Project Identifier Taken",
                detail=f"Identifier {body.identifier} is already in use.",
            ) from exc
        raise

    await record_activity(
        session,
        workspace_id=caller.workspace_id,
        object_id=project_id,
        actor_principal_id=caller.principal_id,
        event_type=ActivityEventType.PROJECT_CREATED,
        payload={"identifier": body.identifier},
    )
    project = await session.get(Project, project_id)
    if project is None:  # pragma: no cover  # Defensive: row was inserted above
        not_found()
    return await serialize_project(session, caller, project)


async def list_projects(
    session: AsyncSession, caller: PrincipalContext, *, cursor: str | None, limit: int
) -> ProjectList:
    """List RLS-visible projects in identifier order using keyset pagination."""
    stmt = select(Project).where(Project.workspace_id == caller.workspace_id)
    if cursor is not None:
        stmt = stmt.where(Project.identifier > decode_cursor(cursor))
    rows: Sequence[Project] = (
        (await session.execute(stmt.order_by(Project.identifier).limit(limit + 1))).scalars().all()
    )
    page = list(rows[:limit])
    next_cursor = encode_cursor(page[-1].identifier) if len(rows) > limit else None
    return ProjectList(
        items=[await serialize_project(session, caller, p) for p in page],
        next_cursor=next_cursor,
    )


async def update_project(
    session: AsyncSession,
    caller: PrincipalContext,
    project_ref: str,
    body: ProjectPatch,
) -> ProjectResponse:
    """Apply a PATCH (name, description, modules_enabled, auto_archive_days)."""
    project = await get_project_or_404(session, caller, project_ref)
    await require_capability(session, caller, project.id, Capability.ADMIN)
    if "identifier" in body.model_fields_set:
        raise _problem(code="IDENTIFIER_IMMUTABLE", status=422, title="Identifier Immutable")

    changes: dict[str, JSONValue] = {}
    fields = body.model_fields_set

    if "name" in fields and body.name is not None and body.name != project.name:
        changes["name"] = {"old": project.name, "new": body.name}
        project.name = body.name

    if "description_markdown" in fields and body.description_markdown is not None:
        new_desc = _normalize_description(body.description_markdown)
        if new_desc != project.description_markdown:
            changes["description_markdown"] = {
                "old_sha256": _sha256_hex(project.description_markdown),
                "new_sha256": _sha256_hex(new_desc),
            }
            project.description_markdown = new_desc

    if (
        "modules_enabled" in fields
        and body.modules_enabled is not None
        and body.modules_enabled != project.modules_enabled
    ):
        if not body.modules_enabled:
            module_count = (
                await session.execute(
                    select(func.count()).select_from(Module).where(Module.project_id == project.id)
                )
            ).scalar_one()
            if module_count > 0:
                raise _problem(code="MODULES_IN_USE", status=409, title="Modules In Use")
        changes["modules_enabled"] = {"old": project.modules_enabled, "new": body.modules_enabled}
        project.modules_enabled = body.modules_enabled

    if "auto_archive_days" in fields and body.auto_archive_days != project.auto_archive_days:
        changes["auto_archive_days"] = {
            "old": project.auto_archive_days,
            "new": body.auto_archive_days,
        }
        project.auto_archive_days = body.auto_archive_days

    if changes:
        await session.flush()
        await record_activity(
            session,
            workspace_id=caller.workspace_id,
            object_id=project.id,
            actor_principal_id=caller.principal_id,
            event_type=ActivityEventType.PROJECT_UPDATED,
            payload={"changes": changes},
        )
    return await serialize_project(session, caller, project)


async def replace_module_defaults(
    session: AsyncSession,
    caller: PrincipalContext,
    project_ref: str,
    module_ids: list[uuid.UUID],
) -> ProjectResponse:
    """Replace ``project_module_defaults`` rows for a project with modules enabled."""
    project = await get_project_or_404(session, caller, project_ref)
    await require_capability(session, caller, project.id, Capability.ADMIN)
    if not project.modules_enabled:
        raise _problem(code="MODULES_DISABLED", status=422, title="Modules Disabled")

    if module_ids:
        found = set(
            (
                await session.execute(
                    select(Module.id).where(
                        Module.project_id == project.id, Module.id.in_(module_ids)
                    )
                )
            )
            .scalars()
            .all()
        )
        if found != set(module_ids):
            raise _problem(code="MODULE_NOT_IN_PROJECT", status=422, title="Module Not In Project")

    old_ids = await _default_module_ids(session, project.id)
    await session.execute(
        delete(ProjectModuleDefault).where(ProjectModuleDefault.project_id == project.id)
    )
    session.add_all(
        ProjectModuleDefault(
            project_id=project.id, module_id=module_id, workspace_id=caller.workspace_id
        )
        for module_id in module_ids
    )
    await session.flush()
    await record_activity(
        session,
        workspace_id=caller.workspace_id,
        object_id=project.id,
        actor_principal_id=caller.principal_id,
        event_type=ActivityEventType.MODULE_DEFAULTS_CHANGED,
        payload={
            "old_module_ids": [str(m) for m in old_ids],
            "new_module_ids": sorted(str(m) for m in module_ids),
        },
    )
    return await serialize_project(session, caller, project)


async def list_project_members(
    session: AsyncSession, caller: PrincipalContext, project_ref: str
) -> list[ProjectMemberResponse]:
    """List role bindings for principals on this project."""
    project = await get_project_or_404(session, caller, project_ref)
    await require_capability(session, caller, project.id, Capability.VIEW)

    stmt = text(
        "SELECT rb.id, rb.principal_id, rb.project_id, rb.role::text AS role, rb.created_at, "
        "       p.display_name, o.canonical_key AS handle, u.email "
        "FROM role_bindings rb "
        "JOIN principals p ON p.id = rb.principal_id "
        "LEFT JOIN users u ON u.id = rb.principal_id "
        "LEFT JOIN objects o ON o.id = rb.principal_id "
        "WHERE rb.project_id = :proj_id AND rb.scope_type = 'project' "
        "ORDER BY rb.created_at ASC"
    )
    res = await session.execute(stmt, {"proj_id": project.id})
    return [
        ProjectMemberResponse(
            id=row["id"],
            principal_id=row["principal_id"],
            project_id=row["project_id"],
            role=row["role"],
            display_name=row["display_name"],
            handle=row["handle"],
            email=row["email"],
            created_at=row["created_at"],
        )
        for row in res.mappings()
    ]


async def add_project_member(
    session: AsyncSession, caller: PrincipalContext, project_ref: str, body: ProjectMemberAdd
) -> ProjectMemberResponse:
    """Add or update a principal role binding on project scope (requires Capability.ADMIN)."""
    project = await get_project_or_404(session, caller, project_ref)
    await require_capability(session, caller, project.id, Capability.ADMIN)

    # Check principal exists in this workspace
    p_stmt = text(
        "SELECT p.id, p.display_name, o.canonical_key AS handle, u.email "
        "FROM principals p "
        "LEFT JOIN users u ON u.id = p.id "
        "LEFT JOIN objects o ON o.id = p.id "
        "WHERE p.id = :p_id AND p.workspace_id = :ws_id"
    )
    p_res = (
        (await session.execute(p_stmt, {"p_id": body.principal_id, "ws_id": caller.workspace_id}))
        .mappings()
        .first()
    )
    if p_res is None:
        not_found()

    # Check existing binding
    existing_stmt = text(
        "SELECT id FROM role_bindings "
        "WHERE project_id = :proj_id AND principal_id = :p_id AND scope_type = 'project'"
    )
    existing_id = (
        await session.execute(existing_stmt, {"proj_id": project.id, "p_id": body.principal_id})
    ).scalar_one_or_none()

    if existing_id is not None:
        await session.execute(
            text("UPDATE role_bindings SET role = CAST(:role AS rbac_role) WHERE id = :binding_id"),
            {"role": body.role, "binding_id": existing_id},
        )
        binding_id = existing_id
    else:
        new_id = uuid.uuid4()
        await session.execute(
            text(
                "INSERT INTO role_bindings "
                "(id, workspace_id, principal_id, role, scope_type, project_id) "
                "VALUES (:id, :ws_id, :p_id, CAST(:role AS rbac_role), 'project', :proj_id)"
            ),
            {
                "id": new_id,
                "ws_id": caller.workspace_id,
                "p_id": body.principal_id,
                "role": body.role,
                "proj_id": project.id,
            },
        )
        binding_id = new_id

    await session.flush()
    return ProjectMemberResponse(
        id=binding_id,
        principal_id=body.principal_id,
        project_id=project.id,
        role=body.role,
        display_name=p_res["display_name"],
        handle=p_res["handle"],
        email=p_res["email"],
        created_at=datetime.now(UTC),
    )


async def delete_project_member(
    session: AsyncSession, caller: PrincipalContext, project_ref: str, principal_id: uuid.UUID
) -> None:
    """Remove a principal role binding from project scope (requires Capability.ADMIN)."""
    project = await get_project_or_404(session, caller, project_ref)
    await require_capability(session, caller, project.id, Capability.ADMIN)

    await session.execute(
        text(
            "DELETE FROM role_bindings "
            "WHERE project_id = :proj_id AND principal_id = :p_id AND scope_type = 'project'"
        ),
        {"proj_id": project.id, "p_id": principal_id},
    )
    await session.flush()
