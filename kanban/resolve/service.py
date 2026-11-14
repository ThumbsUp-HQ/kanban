# Copyright 2026 Kanban Platform Contributors
"""Entity resolution service for human-readable keys and UUIDs (S11.1, S1.1)."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, Protocol

from sqlalchemy import func, select

from database.models.issues import Issue
from database.models.principals import Principal, User
from database.models.projects import Cycle, Module, Project, ProjectLabel, WorkflowState
from database.models.spine import Workspace
from kanban.api.problems import FieldError, ProblemException, not_found

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

__all__ = [
    "KindProvider",
    "ResolutionService",
    "ResolvedRef",
]

_MAX_REF_LENGTH: Final[int] = 200
_ASCII_SPACE: Final[int] = 32
_ASCII_DEL: Final[int] = 127
_RFC4122_UUID_REGEX: Final[re.Pattern[str]] = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)
_PROJECT_IDENTIFIER_REGEX: Final[re.Pattern[str]] = re.compile(r"^[A-Z][A-Z0-9]{1,9}$")
_ISSUE_KEY_REGEX: Final[re.Pattern[str]] = re.compile(r"^([A-Z][A-Z0-9]{1,9})-([0-9]{1,18})$")


@dataclass(frozen=True, slots=True)
class ResolvedRef:
    """Resolved entity identity, kind, human-readable key, and descriptive title."""

    id: uuid.UUID
    kind: str
    key: str
    title: str
    workspace: str | None = None


class KindProvider(Protocol):
    """Protocol for pluggable entity kind resolution providers."""

    async def resolve(
        self,
        session: AsyncSession,
        ref: str,
        *,
        project_id: uuid.UUID | None = None,
        workspace_id: uuid.UUID | None = None,
    ) -> list[ResolvedRef]:
        """Resolve entity reference into candidate matches."""
        ...


class StubHookProvider:
    """Test stub provider for hook resolution until KB-P5-17 wires workflow hooks."""

    def __init__(self) -> None:
        self._hooks: dict[str, ResolvedRef] = {}

    def add_stub(self, ref: str, resolved: ResolvedRef) -> None:
        """Register a test hook reference."""
        self._hooks[ref.lower()] = resolved

    async def resolve(
        self,
        session: AsyncSession,
        ref: str,
        *,
        project_id: uuid.UUID | None = None,
        workspace_id: uuid.UUID | None = None,
    ) -> list[ResolvedRef]:
        """Return registered stub hooks matching ref."""
        del session, project_id, workspace_id
        match = self._hooks.get(ref.lower())
        return [match] if match is not None else []


class ResolutionService:
    """Service resolving human-readable references and UUIDs across entity kinds."""

    def __init__(self) -> None:
        """Initialize service with default pluggable providers."""
        self._providers: dict[str, KindProvider] = {
            "hook": StubHookProvider(),
        }

    def register_provider(self, kind: str, provider: KindProvider) -> None:
        """Register an external kind resolution provider."""
        self._providers[kind] = provider

    def _validate_ref(self, ref: str) -> None:
        """Validate input length constraints and reject control characters."""
        if len(ref) > _MAX_REF_LENGTH:
            msg = f"Ref exceeds maximum length of {_MAX_REF_LENGTH} characters"
            raise ProblemException(
                code="VALIDATION_FAILED",
                status=422,
                title="Validation Failed",
                detail=msg,
                errors=[FieldError(path="ref", message=msg)],
            )

        if any(ord(c) < _ASCII_SPACE or ord(c) == _ASCII_DEL for c in ref):
            msg = "Control characters are strictly rejected in entity references"
            raise ProblemException(
                code="VALIDATION_FAILED",
                status=422,
                title="Validation Failed",
                detail=msg,
                errors=[FieldError(path="ref", message=msg)],
            )

    async def resolve(  # noqa: PLR0913
        self,
        session: AsyncSession,
        kind: str,
        ref: str,
        *,
        project_ref: str | None = None,
        caller_principal_id: uuid.UUID | None = None,
        caller_workspace_id: uuid.UUID | None = None,
        workspace_ref: str | None = None,
    ) -> ResolvedRef:
        """Resolve entity reference within scope or raise appropriate ProblemException."""
        self._validate_ref(ref)

        effective_ws_id = caller_workspace_id
        if workspace_ref:
            try:
                effective_ws_id = uuid.UUID(workspace_ref)
            except ValueError:
                ws_stmt = select(Workspace.id).where(Workspace.slug == workspace_ref)
                effective_ws_id = (await session.execute(ws_stmt)).scalar_one_or_none()
                if effective_ws_id is None:
                    not_found()

        project_context: ResolvedRef | None = None
        if kind in ("state", "cycle", "module", "label"):
            if not project_ref:
                msg = "pass project=<KEY>"
                raise ProblemException(
                    code="VALIDATION_FAILED",
                    status=422,
                    title="Validation Failed",
                    detail=msg,
                    errors=[FieldError(path="project", message=msg)],
                )
            project_context = await self.resolve(
                session,
                "project",
                project_ref,
                caller_workspace_id=effective_ws_id,
            )

        matches = await self._find_matches(
            session=session,
            kind=kind,
            ref=ref,
            project_context=project_context,
            caller_principal_id=caller_principal_id,
            caller_workspace_id=effective_ws_id,
        )

        if not matches:
            not_found()

        if len(matches) > 1:
            candidates = [
                {
                    "key": m.key,
                    "title": m.title,
                    **({"workspace": m.workspace} if m.workspace else {}),
                }
                for m in matches[:5]
            ]
            msg = f"Reference '{ref}' matched multiple candidates for kind '{kind}'"
            extra = {}
            if kind == "issue":
                extra["hint"] = "pass workspace=<slug> or connect via /mcp/agent/w/<slug>"
            raise ProblemException(
                code="AMBIGUOUS_IDENTIFIER",
                status=409,
                title="Ambiguous Identifier",
                detail=msg,
                candidates=candidates,
                extra=extra or None,
            )

        return matches[0]

    async def _find_matches(  # noqa: PLR0913, PLR0917, PLR0911
        self,
        session: AsyncSession,
        kind: str,
        ref: str,
        project_context: ResolvedRef | None,
        caller_principal_id: uuid.UUID | None,
        caller_workspace_id: uuid.UUID | None,
    ) -> list[ResolvedRef]:
        """Dispatch resolution to kind-specific query logic."""
        is_uuid = bool(_RFC4122_UUID_REGEX.match(ref))
        uuid_val = uuid.UUID(ref) if is_uuid else None

        if kind == "project":
            return await self._resolve_project(
                session, ref, is_uuid=is_uuid, uuid_val=uuid_val, workspace_id=caller_workspace_id
            )

        if kind == "issue":
            return await self._resolve_issue(
                session, ref, is_uuid=is_uuid, uuid_val=uuid_val, workspace_id=caller_workspace_id
            )

        if kind == "user":
            return await self._resolve_user(
                session,
                ref,
                is_uuid=is_uuid,
                uuid_val=uuid_val,
                caller_principal_id=caller_principal_id,
                caller_workspace_id=caller_workspace_id,
            )

        if kind in ("state", "cycle", "module", "label") and project_context is None:
            msg = f"Project context is required for {kind} resolution"
            raise ProblemException(
                code="VALIDATION_FAILED",
                status=422,
                title="Validation Failed",
                detail=msg,
                errors=[FieldError(path="project", message=msg)],
            )

        if kind == "state" and project_context is not None:
            return await self._resolve_state(
                session, ref, is_uuid=is_uuid, uuid_val=uuid_val, project_id=project_context.id
            )

        if kind == "cycle" and project_context is not None:
            return await self._resolve_cycle(
                session, ref, is_uuid=is_uuid, uuid_val=uuid_val, project_id=project_context.id
            )

        if kind == "module" and project_context is not None:
            return await self._resolve_module(
                session,
                ref,
                is_uuid=is_uuid,
                uuid_val=uuid_val,
                project_context=project_context,
            )

        if kind == "label" and project_context is not None:
            return await self._resolve_label(
                session, ref, is_uuid=is_uuid, uuid_val=uuid_val, project_id=project_context.id
            )

        if kind in self._providers:
            provider = self._providers[kind]
            proj_id = project_context.id if project_context else None
            return await provider.resolve(
                session, ref, project_id=proj_id, workspace_id=caller_workspace_id
            )

        msg = f"Unsupported resolution kind '{kind}'"
        raise ProblemException(
            code="VALIDATION_FAILED",
            status=422,
            title="Validation Failed",
            detail=msg,
            errors=[FieldError(path="kind", message=msg)],
        )

    async def _resolve_project(
        self,
        session: AsyncSession,
        ref: str,
        *,
        is_uuid: bool,
        uuid_val: uuid.UUID | None,
        workspace_id: uuid.UUID | None,
    ) -> list[ResolvedRef]:
        if is_uuid and uuid_val is not None:
            stmt = select(Project).where(Project.id == uuid_val)
            proj = (await session.execute(stmt)).scalar_one_or_none()
            if proj is not None:
                return [
                    ResolvedRef(id=proj.id, kind="project", key=proj.identifier, title=proj.name)
                ]
            return []

        # Try exact identifier match if valid identifier syntax
        if _PROJECT_IDENTIFIER_REGEX.match(ref):
            stmt_id = select(Project).where(Project.identifier == ref)
            if workspace_id is not None:
                stmt_id = stmt_id.where(Project.workspace_id == workspace_id)
            matches = list((await session.execute(stmt_id)).scalars().all())
            if matches:
                return [
                    ResolvedRef(id=p.id, kind="project", key=p.identifier, title=p.name)
                    for p in matches
                ]

        # Case-insensitive name match
        stmt_name = select(Project).where(func.lower(Project.name) == ref.lower())
        if workspace_id is not None:
            stmt_name = stmt_name.where(Project.workspace_id == workspace_id)
        name_matches = list((await session.execute(stmt_name)).scalars().all())
        return [
            ResolvedRef(id=p.id, kind="project", key=p.identifier, title=p.name)
            for p in name_matches
        ]

    async def _resolve_issue(
        self,
        session: AsyncSession,
        ref: str,
        *,
        is_uuid: bool,
        uuid_val: uuid.UUID | None,
        workspace_id: uuid.UUID | None = None,
    ) -> list[ResolvedRef]:
        if is_uuid and uuid_val is not None:
            stmt = (
                select(Issue, Project.identifier, Workspace.slug)
                .join(Project, Issue.project_id == Project.id)
                .join(Workspace, Project.workspace_id == Workspace.id)
                .where(Issue.id == uuid_val)
            )
            if workspace_id is not None:
                stmt = stmt.where(Project.workspace_id == workspace_id)
            rows = (await session.execute(stmt)).all()
            return [
                ResolvedRef(
                    id=issue.id,
                    kind="issue",
                    key=f"{proj_ident}-{issue.sequence_id}",
                    title=issue.summary,
                    workspace=ws_slug,
                )
                for issue, proj_ident, ws_slug in rows
            ]

        match = _ISSUE_KEY_REGEX.match(ref)
        if not match:
            return []

        proj_ident = match.group(1)
        seq_id = int(match.group(2))

        stmt_key = (
            select(Issue, Project.identifier, Workspace.slug)
            .join(Project, Issue.project_id == Project.id)
            .join(Workspace, Project.workspace_id == Workspace.id)
            .where(Project.identifier == proj_ident, Issue.sequence_id == seq_id)
        )
        if workspace_id is not None:
            stmt_key = stmt_key.where(Project.workspace_id == workspace_id)
        rows_key = (await session.execute(stmt_key)).all()
        return [
            ResolvedRef(
                id=issue.id,
                kind="issue",
                key=f"{p_ident}-{issue.sequence_id}",
                title=issue.summary,
                workspace=ws_slug,
            )
            for issue, p_ident, ws_slug in rows_key
        ]

    async def _resolve_user(  # noqa: PLR0913
        self,
        session: AsyncSession,
        ref: str,
        *,
        is_uuid: bool,
        uuid_val: uuid.UUID | None,
        caller_principal_id: uuid.UUID | None,
        caller_workspace_id: uuid.UUID | None,
    ) -> list[ResolvedRef]:
        # 'me' resolves to the caller principal
        if ref.lower() == "me":
            if caller_principal_id is None:
                return []
            stmt_caller = select(Principal).where(Principal.id == caller_principal_id)
            caller = (await session.execute(stmt_caller)).scalar_one_or_none()
            if caller is not None:
                return [
                    ResolvedRef(
                        id=caller.id,
                        kind="user",
                        key=f"@{caller.display_name.lower().replace(' ', '')}",
                        title=caller.display_name,
                    )
                ]
            return []

        if is_uuid and uuid_val is not None:
            stmt_uuid = (
                select(User, Principal.display_name)
                .join(Principal, User.id == Principal.id)
                .where(User.id == uuid_val)
            )
            if caller_workspace_id is not None:
                stmt_uuid = stmt_uuid.where(User.workspace_id == caller_workspace_id)
            row_uuid = (await session.execute(stmt_uuid)).first()
            if row_uuid is not None:
                user, display_name = row_uuid
                return [
                    ResolvedRef(
                        id=user.id,
                        kind="user",
                        key=f"@{display_name.lower().replace(' ', '')}",
                        title=display_name,
                    )
                ]
            return []

        # Handle @handle or email or exact display_name
        stmt_users = select(User, Principal.display_name).join(Principal, User.id == Principal.id)
        if caller_workspace_id is not None:
            stmt_users = stmt_users.where(User.workspace_id == caller_workspace_id)

        clean_ref = ref.removeprefix("@")
        lower_ref = clean_ref.lower()

        if ref.startswith("@"):
            stmt_users = stmt_users.where(
                func.lower(func.replace(Principal.display_name, " ", "")) == lower_ref
            )
        elif "@" in ref:
            stmt_users = stmt_users.where(func.lower(User.email) == ref.lower())
        else:
            stmt_users = stmt_users.where(
                (func.lower(func.replace(Principal.display_name, " ", "")) == lower_ref)
                | (func.lower(Principal.display_name) == ref.lower())
            )

        rows = (await session.execute(stmt_users)).all()
        return [
            ResolvedRef(
                id=u.id,
                kind="user",
                key=f"@{disp.lower().replace(' ', '')}",
                title=disp,
            )
            for u, disp in rows
        ]

    async def _resolve_state(
        self,
        session: AsyncSession,
        ref: str,
        *,
        is_uuid: bool,
        uuid_val: uuid.UUID | None,
        project_id: uuid.UUID,
    ) -> list[ResolvedRef]:
        if is_uuid and uuid_val is not None:
            stmt = select(WorkflowState).where(
                WorkflowState.id == uuid_val,
                WorkflowState.project_id == project_id,
            )
            state = (await session.execute(stmt)).scalar_one_or_none()
            if state is not None:
                return [ResolvedRef(id=state.id, kind="state", key=state.name, title=state.name)]
            return []

        stmt_name = select(WorkflowState).where(
            WorkflowState.project_id == project_id,
            func.lower(WorkflowState.name) == ref.lower(),
        )
        states = list((await session.execute(stmt_name)).scalars().all())
        return [ResolvedRef(id=s.id, kind="state", key=s.name, title=s.name) for s in states]

    async def _resolve_cycle(
        self,
        session: AsyncSession,
        ref: str,
        *,
        is_uuid: bool,
        uuid_val: uuid.UUID | None,
        project_id: uuid.UUID,
    ) -> list[ResolvedRef]:
        if is_uuid and uuid_val is not None:
            stmt = select(Cycle).where(
                Cycle.id == uuid_val,
                Cycle.project_id == project_id,
            )
            cycle = (await session.execute(stmt)).scalar_one_or_none()
            if cycle is not None:
                return [ResolvedRef(id=cycle.id, kind="cycle", key=cycle.name, title=cycle.name)]
            return []

        stmt_name = select(Cycle).where(
            Cycle.project_id == project_id,
            func.lower(Cycle.name) == ref.lower(),
        )
        cycles = list((await session.execute(stmt_name)).scalars().all())
        return [ResolvedRef(id=c.id, kind="cycle", key=c.name, title=c.name) for c in cycles]

    async def _resolve_module(
        self,
        session: AsyncSession,
        ref: str,
        *,
        is_uuid: bool,
        uuid_val: uuid.UUID | None,
        project_context: ResolvedRef,
    ) -> list[ResolvedRef]:
        # Verify modules_enabled on project
        stmt_proj = select(Project.modules_enabled).where(Project.id == project_context.id)
        modules_enabled = (await session.execute(stmt_proj)).scalar_one_or_none()
        if not modules_enabled:
            msg = f"Modules are disabled for project '{project_context.key}'"
            raise ProblemException(
                code="MODULES_DISABLED",
                status=422,
                title="Modules Disabled",
                detail=msg,
                errors=[FieldError(path="module", message=msg)],
            )

        if is_uuid and uuid_val is not None:
            stmt = select(Module).where(
                Module.id == uuid_val,
                Module.project_id == project_context.id,
            )
            mod = (await session.execute(stmt)).scalar_one_or_none()
            if mod is not None:
                return [ResolvedRef(id=mod.id, kind="module", key=mod.name, title=mod.name)]
            return []

        stmt_name = select(Module).where(
            Module.project_id == project_context.id,
            func.lower(Module.name) == ref.lower(),
        )
        mods = list((await session.execute(stmt_name)).scalars().all())
        return [ResolvedRef(id=m.id, kind="module", key=m.name, title=m.name) for m in mods]

    async def _resolve_label(
        self,
        session: AsyncSession,
        ref: str,
        *,
        is_uuid: bool,
        uuid_val: uuid.UUID | None,
        project_id: uuid.UUID,
    ) -> list[ResolvedRef]:
        if is_uuid and uuid_val is not None:
            stmt = select(ProjectLabel).where(
                ProjectLabel.id == uuid_val,
                ProjectLabel.project_id == project_id,
            )
            label = (await session.execute(stmt)).scalar_one_or_none()
            if label is not None:
                return [ResolvedRef(id=label.id, kind="label", key=label.name, title=label.name)]
            return []

        stmt_name = select(ProjectLabel).where(
            ProjectLabel.project_id == project_id,
            func.lower(ProjectLabel.name) == ref.lower(),
        )
        labels = list((await session.execute(stmt_name)).scalars().all())
        return [
            ResolvedRef(id=label.id, kind="label", key=label.name, title=label.name)
            for label in labels
        ]
