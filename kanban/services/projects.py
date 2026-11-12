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
from typing import TYPE_CHECKING, Final

from sqlalchemy import delete, func, select, text
from sqlalchemy.exc import IntegrityError

from database.models import Module, Project, ProjectModuleDefault
from kanban.api.problems import ProblemException, not_found
from kanban.api.v1.schemas.projects import ProjectList, ProjectResponse
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
    return ProjectResponse(
        id=project.id,
        identifier=project.identifier,
        name=project.name,
        description_markdown=project.description_markdown,
        modules_enabled=project.modules_enabled,
        default_module_ids=await _default_module_ids(session, project.id),
        auto_archive_days=project.auto_archive_days,
        access_manifest=manifest,
        capabilities=capabilities_to_names(caps),
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
