"""Agent definition service: CRUD operations, RLS, and activity auditing (KB-P5-16)."""

from __future__ import annotations

import json
import uuid
from typing import TYPE_CHECKING, Final

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from database.models.agent_definition import AgentDefinition
from database.models.principals import Principal
from kanban.agents.cli_policy import CliPolicyError, validate_cli_args
from kanban.agents.schemas import (
    AgentDefinitionCreate,
    AgentDefinitionPatch,
    AgentDefinitionResponse,
)
from kanban.api.problems import ProblemException, not_found

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from kanban.api.deps import PrincipalContext

_FOREIGN_KEY_VIOLATION: Final[str] = "23503"
_UNIQUE_VIOLATION: Final[str] = "23505"


def _is_fk_violation(exc: BaseException) -> bool:
    """Return True if wrapped database exception indicates foreign key restrict violation."""
    orig = getattr(exc, "orig", exc)
    candidates = (exc, orig, getattr(orig, "__cause__", None), getattr(exc, "__cause__", None))
    return any(
        getattr(c, "sqlstate", None) == _FOREIGN_KEY_VIOLATION
        or getattr(c, "pgcode", None) == _FOREIGN_KEY_VIOLATION
        for c in candidates
    )


def _is_unique_violation(exc: BaseException) -> bool:
    """Return True if wrapped database exception indicates unique constraint violation."""
    orig = getattr(exc, "orig", exc)
    candidates = (exc, orig, getattr(orig, "__cause__", None), getattr(exc, "__cause__", None))
    return any(
        getattr(c, "sqlstate", None) == _UNIQUE_VIOLATION
        or getattr(c, "pgcode", None) == _UNIQUE_VIOLATION
        for c in candidates
    )


def _serialize(agent: AgentDefinition) -> AgentDefinitionResponse:
    """Serialize AgentDefinition ORM instance to canonical API response."""
    args_list = [str(a) for a in agent.cli_args_json]
    return AgentDefinitionResponse(
        id=agent.id,
        workspace_id=agent.workspace_id,
        project_id=agent.project_id,
        principal_id=agent.principal_id,
        slug=agent.slug,
        display_name=agent.display_name,
        harness_kind=agent.harness_kind,
        provider_kind=agent.provider_kind,
        model_id=agent.model_id,
        cli_binary_allowlist_id=agent.cli_binary_allowlist_id,
        cli_args=args_list,
        remote_runner_pool_slug=agent.remote_runner_pool_slug,
        repo_access_mode=agent.repo_access_mode,
        mcp_allowed_tools=list(agent.mcp_allowed_tools),
        system_instructions_md=agent.system_instructions_md,
        timeout_ms=agent.timeout_ms,
    )


def _validate_patch_cli(agent: AgentDefinition, patch: AgentDefinitionPatch) -> None:
    """Validate CLI arguments when modifying cli_pipe agent."""
    if agent.harness_kind != "cli_pipe":
        return
    target_bin = (
        patch.cli_binary_allowlist_id
        if patch.cli_binary_allowlist_id is not None
        else agent.cli_binary_allowlist_id
    )
    target_args = patch.cli_args if patch.cli_args is not None else agent.cli_args_json
    if target_bin:
        try:
            validate_cli_args(target_bin, target_args)
        except CliPolicyError as exc:
            raise ProblemException(
                code=exc.code,
                status=exc.status,
                title="CLI Policy Violation",
                detail=exc.detail,
            ) from exc


def _apply_patch_fields(agent: AgentDefinition, patch: AgentDefinitionPatch) -> None:
    """Apply updated fields from patch schema to agent definition model."""
    mapping = {
        "display_name": patch.display_name,
        "provider_kind": patch.provider_kind,
        "model_id": patch.model_id,
        "cli_binary_allowlist_id": patch.cli_binary_allowlist_id,
        "remote_runner_pool_slug": patch.remote_runner_pool_slug,
        "repo_access_mode": patch.repo_access_mode,
        "mcp_allowed_tools": patch.mcp_allowed_tools,
        "system_instructions_md": patch.system_instructions_md,
        "timeout_ms": patch.timeout_ms,
    }
    for field, value in mapping.items():
        if value is not None:
            setattr(agent, field, value)
    if patch.cli_args is not None:
        agent.cli_args_json = patch.cli_args


class AgentDefinitionService:
    """Business logic and RLS enforcement for agent definition registry."""

    @staticmethod
    async def verify_workspace(
        session: AsyncSession, caller: PrincipalContext, workspace_ref: str
    ) -> None:
        """Assert caller belongs to the requested workspace reference (UUID or slug)."""
        if workspace_ref == "current":
            return
        try:
            ws_id = uuid.UUID(workspace_ref)
            if ws_id != caller.workspace_id:
                not_found()
        except ValueError:
            stmt = text("SELECT id FROM workspaces WHERE id = :wid AND slug = :slug")
            found = (
                await session.execute(stmt, {"wid": caller.workspace_id, "slug": workspace_ref})
            ).scalar_one_or_none()
            if found is None:
                not_found()

    @staticmethod
    async def require_admin_role(session: AsyncSession, project_id: uuid.UUID | None) -> None:
        """Require WORKSPACE_ADMIN for workspace agent, or PROJECT_ADMIN for project agent."""
        roles = ["SERVER_ADMIN", "WORKSPACE_ADMIN"]
        if project_id is not None:
            roles.append("PROJECT_ADMIN")

        stmt = text("SELECT app_principal_has_role(:project_id, :roles)")
        has_role = (
            await session.execute(stmt, {"project_id": project_id, "roles": roles})
        ).scalar_one()

        if not has_role:
            raise ProblemException(
                code="INSUFFICIENT_CAPABILITY",
                status=403,
                title="Insufficient Capability",
                detail="Caller lacks required admin role to manage agent definitions",
            )

    @classmethod
    async def create(
        cls,
        session: AsyncSession,
        caller: PrincipalContext,
        workspace_ref: str,
        payload: AgentDefinitionCreate,
    ) -> AgentDefinitionResponse:
        """Create a new agent definition and AGENT principal in a single transaction."""
        await cls.verify_workspace(session, caller, workspace_ref)
        await cls.require_admin_role(session, payload.project_id)

        principal_id = uuid.uuid4()
        principal = Principal(
            id=principal_id,
            principal_type="AGENT",
            workspace_id=caller.workspace_id,
            status="ACTIVE",
            display_name=payload.display_name,
        )
        session.add(principal)
        await session.flush()

        agent_id = uuid.uuid4()
        agent = AgentDefinition(
            id=agent_id,
            workspace_id=caller.workspace_id,
            project_id=payload.project_id,
            principal_id=principal_id,
            slug=payload.slug,
            display_name=payload.display_name,
            harness_kind=payload.harness_kind,
            provider_kind=payload.provider_kind,
            model_id=payload.model_id,
            cli_binary_allowlist_id=payload.cli_binary_allowlist_id,
            cli_args_json=payload.cli_args,
            remote_runner_pool_slug=payload.remote_runner_pool_slug,
            repo_access_mode=payload.repo_access_mode,
            mcp_allowed_tools=payload.mcp_allowed_tools,
            system_instructions_md=payload.system_instructions_md,
            timeout_ms=payload.timeout_ms,
        )
        session.add(agent)

        try:
            await session.flush()
        except (IntegrityError, Exception) as exc:
            await session.rollback()
            if _is_unique_violation(exc):
                detail_msg = (
                    f"Agent definition with slug {payload.slug!r} already exists in this workspace"
                )
                raise ProblemException(
                    code="CONFLICT",
                    status=409,
                    title="Agent Already Exists",
                    detail=detail_msg,
                ) from exc
            raise

        # Activity audit record
        argv: list[str] = []
        if agent.harness_kind == "cli_pipe" and agent.cli_binary_allowlist_id:
            argv = list(validate_cli_args(agent.cli_binary_allowlist_id, agent.cli_args_json).argv)

        audit_payload = {
            "agent_definition_id": str(agent.id),
            "slug": agent.slug,
            "harness_kind": agent.harness_kind,
            "argv": argv,
        }
        await session.execute(
            text(
                "SELECT append_activity("
                "  :ws, NULL, CAST(NULL AS object_kind), :actor, :etype, CAST(:payload AS jsonb)"
                ")"
            ),
            {
                "ws": caller.workspace_id,
                "actor": caller.principal_id,
                "etype": "AGENT_DEFINITION_CREATED",
                "payload": json.dumps(audit_payload),
            },
        )

        return _serialize(agent)

    @classmethod
    async def get_by_ref(
        cls, session: AsyncSession, caller: PrincipalContext, agent_ref: str
    ) -> AgentDefinition:
        """Fetch agent definition by UUID or slug in caller workspace, raising 404 if absent."""
        stmt = select(AgentDefinition).where(AgentDefinition.workspace_id == caller.workspace_id)
        try:
            agent_uuid = uuid.UUID(agent_ref)
            stmt = stmt.where(AgentDefinition.id == agent_uuid)
        except ValueError:
            stmt = stmt.where(AgentDefinition.slug == agent_ref)

        agent = (await session.execute(stmt)).scalar_one_or_none()
        if agent is None:
            not_found()
        return agent

    @classmethod
    async def get(
        cls, session: AsyncSession, caller: PrincipalContext, agent_ref: str
    ) -> AgentDefinitionResponse:
        """Fetch single agent definition."""
        agent = await cls.get_by_ref(session, caller, agent_ref)
        return _serialize(agent)

    @classmethod
    async def list_definitions(
        cls,
        session: AsyncSession,
        caller: PrincipalContext,
        workspace_ref: str,
        project_id: uuid.UUID | None = None,
    ) -> list[AgentDefinitionResponse]:
        """List all readable agent definitions in the workspace ordered by slug."""
        await cls.verify_workspace(session, caller, workspace_ref)
        stmt = select(AgentDefinition).where(AgentDefinition.workspace_id == caller.workspace_id)
        if project_id is not None:
            stmt = stmt.where(AgentDefinition.project_id == project_id)
        stmt = stmt.order_by(AgentDefinition.slug)
        results = (await session.execute(stmt)).scalars().all()
        return [_serialize(agent) for agent in results]

    @classmethod
    async def patch(
        cls,
        session: AsyncSession,
        caller: PrincipalContext,
        agent_ref: str,
        patch: AgentDefinitionPatch,
    ) -> AgentDefinitionResponse:
        """Update mutable fields of an agent definition."""
        agent = await cls.get_by_ref(session, caller, agent_ref)
        await cls.require_admin_role(session, agent.project_id)

        _validate_patch_cli(agent, patch)
        _apply_patch_fields(agent, patch)
        await session.flush()

        argv: list[str] = []
        if agent.harness_kind == "cli_pipe" and agent.cli_binary_allowlist_id:
            argv = list(validate_cli_args(agent.cli_binary_allowlist_id, agent.cli_args_json).argv)

        audit_payload = {
            "agent_definition_id": str(agent.id),
            "slug": agent.slug,
            "harness_kind": agent.harness_kind,
            "argv": argv,
        }
        await session.execute(
            text(
                "SELECT append_activity("
                "  :ws, NULL, CAST(NULL AS object_kind), :actor, :etype, CAST(:payload AS jsonb)"
                ")"
            ),
            {
                "ws": caller.workspace_id,
                "actor": caller.principal_id,
                "etype": "AGENT_DEFINITION_UPDATED",
                "payload": json.dumps(audit_payload),
            },
        )

        return _serialize(agent)

    @classmethod
    async def delete(cls, session: AsyncSession, caller: PrincipalContext, agent_ref: str) -> None:
        """Delete an agent definition, trapping FK RESTRICT violations as 409 AGENT_IN_USE."""
        agent = await cls.get_by_ref(session, caller, agent_ref)
        await cls.require_admin_role(session, agent.project_id)

        argv: list[str] = []
        if agent.harness_kind == "cli_pipe" and agent.cli_binary_allowlist_id:
            argv = list(validate_cli_args(agent.cli_binary_allowlist_id, agent.cli_args_json).argv)

        audit_payload = {
            "agent_definition_id": str(agent.id),
            "slug": agent.slug,
            "harness_kind": agent.harness_kind,
            "argv": argv,
        }

        try:
            async with session.begin_nested():
                await session.execute(
                    text(
                        "SELECT append_activity("
                        "  :ws, NULL, CAST(NULL AS object_kind),"
                        "  :actor, :etype, CAST(:payload AS jsonb)"
                        ")"
                    ),
                    {
                        "ws": caller.workspace_id,
                        "actor": caller.principal_id,
                        "etype": "AGENT_DEFINITION_DELETED",
                        "payload": json.dumps(audit_payload),
                    },
                )
                await session.delete(agent)
                await session.flush()
        except (IntegrityError, Exception) as exc:
            if _is_fk_violation(exc):
                msg = f"Agent definition {agent.slug!r} is referenced by transition hooks"
                raise ProblemException(
                    code="AGENT_IN_USE",
                    status=409,
                    title="Agent In Use",
                    detail=msg,
                ) from exc
            raise
