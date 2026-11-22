# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Ephemeral kb_agt_eph_* read-only MCP tokens (KB-P4-13 / S14.3)."""

from __future__ import annotations

import base64
import secrets
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any, Final, cast

from sqlalchemy import CursorResult, select, text

from database.models.mcp_ephemeral_token import McpEphemeralToken
from database.models.principals import Principal
from database.models.projects import Project
from database.models.workflow import WorkflowTransitionExecution
from kanban.api.problems import ProblemException
from kanban.security.mcp_keys import McpIntrospectionResult, hash_mcp_api_key

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession

__all__ = [
    "ALLOWED_EPHEMERAL_TOOLS",
    "EPHEMERAL_TOKEN_PREFIX",
    "MAX_ALLOWED_EPHEMERAL_TOOLS",
    "MAX_EPHEMERAL_CALLS",
    "MAX_EPHEMERAL_TTL_SECONDS",
    "SURFACE_ALLOWED_EPHEMERAL_TOOLS",
    "generate_ephemeral_mcp_token",
    "introspect_and_consume_ephemeral_token",
    "mint_ephemeral_token",
    "revoke_ephemeral_tokens_by_execution",
]

EPHEMERAL_TOKEN_PREFIX: Final[str] = "kb_agt_eph_"  # noqa: S105
MAX_EPHEMERAL_TTL_SECONDS: Final[int] = 120
MAX_EPHEMERAL_CALLS: Final[int] = 25
MAX_ALLOWED_EPHEMERAL_TOOLS: Final[int] = 4

ALLOWED_EPHEMERAL_TOOLS: Final[frozenset[str]] = frozenset(
    {"search_tickets", "read_ticket", "search_knowledge", "read_doc", "search"}
)

SURFACE_ALLOWED_EPHEMERAL_TOOLS: Final[dict[str, frozenset[str]]] = {
    "agent": frozenset({"search_tickets", "read_ticket"}),
    "docs": frozenset({"search_knowledge", "read_doc", "search"}),
}


def generate_ephemeral_mcp_token() -> tuple[str, bytes]:
    """Generate high-entropy ephemeral agent token.

    Format: kb_agt_eph_<base64url(os.urandom(32)) without padding>

    Returns:
        (plaintext_token, sha256_digest)

    """
    raw_bytes = secrets.token_bytes(32)
    b64 = base64.urlsafe_b64encode(raw_bytes).decode("ascii").rstrip("=")
    token = f"{EPHEMERAL_TOKEN_PREFIX}{b64}"
    digest = hash_mcp_api_key(token)
    return token, digest


async def _verify_active_execution_binding(  # noqa: PLR0913
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    execution_id: uuid.UUID,
    invoking_principal_id: uuid.UUID,
    agent_principal_id: uuid.UUID,
    project_id: uuid.UUID,
) -> None:
    """Verify execution_id is active and bound to a hook whose agent_definition owns agent."""
    execution = await session.get(WorkflowTransitionExecution, execution_id)
    if execution is None:
        raise ProblemException(
            code="INVALID_EXECUTION",
            status=422,
            title="Invalid Execution",
            detail="execution_id does not exist in workflow_transition_executions.",
        )

    if execution.status not in ("running_sync", "pending_async"):
        raise ProblemException(
            code="INACTIVE_EXECUTION",
            status=422,
            title="Inactive Execution",
            detail=(
                f"execution_id is in inactive status {execution.status!r}; "
                "must be 'running_sync' or 'pending_async'."
            ),
        )

    if (
        execution.workspace_id != workspace_id
        or execution.project_id != project_id
        or execution.invoking_principal_id != invoking_principal_id
    ):
        raise ProblemException(
            code="EXECUTION_SCOPE_MISMATCH",
            status=403,
            title="Execution Scope Mismatch",
            detail=(
                "execution_id tuple does not match "
                "(workspace_id, invoking_principal_id, project_id)."
            ),
        )

    hook_binding_stmt = text(
        """
        SELECT 1
        FROM workflow_transition_hooks wth
        JOIN agent_definitions ad ON ad.id = wth.agent_definition_id
        WHERE wth.workspace_id = :ws_id
          AND wth.project_id = :proj_id
          AND ad.workspace_id = :ws_id
          AND ad.principal_id = :agent_pid
          AND (
              (
                  wth.is_enabled IS TRUE
                  AND wth.to_state_id = :to_state_id
                  AND (wth.from_state_id IS NULL OR wth.from_state_id = :from_state_id)
              )
              OR EXISTS (
                  SELECT 1
                  FROM workflow_hook_invocations whi
                  WHERE whi.execution_id = :exec_id
                    AND whi.hook_id = wth.id
                    AND whi.workspace_id = :ws_id
                    AND whi.status = 'running'
              )
          )
        LIMIT 1
        """
    )
    bound_hook = (
        await session.execute(
            hook_binding_stmt,
            {
                "ws_id": workspace_id,
                "proj_id": project_id,
                "agent_pid": agent_principal_id,
                "to_state_id": execution.to_state_id,
                "from_state_id": execution.from_state_id,
                "exec_id": execution_id,
            },
        )
    ).first()
    if bound_hook is None:
        raise ProblemException(
            code="EXECUTION_AGENT_MISMATCH",
            status=403,
            title="Execution Agent Mismatch",
            detail=(
                "execution_id is not bound to an attached workflow hook whose "
                "agent_definition_id owns agent_principal_id."
            ),
        )


async def mint_ephemeral_token(  # noqa: PLR0913
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    execution_id: uuid.UUID,
    invoking_principal_id: uuid.UUID,
    agent_principal_id: uuid.UUID,
    project_id: uuid.UUID,
    allowed_tools: list[str] | None = None,
    ttl_seconds: int = 120,
    max_calls: int = 25,
) -> tuple[McpEphemeralToken, str]:
    """Mint a short-lived ephemeral read-only MCP token bound to execution and triple intersection.

    Enforces TTL <= 120s, max_calls <= 25, 4-tool read-only subset, and active principals.
    """
    if ttl_seconds <= 0 or ttl_seconds > MAX_EPHEMERAL_TTL_SECONDS:
        raise ProblemException(
            code="INVALID_EXPIRATION",
            status=422,
            title="Invalid Expiration",
            detail=f"Ephemeral TTL must be between 1 and {MAX_EPHEMERAL_TTL_SECONDS} seconds.",
        )

    if max_calls < 1 or max_calls > MAX_EPHEMERAL_CALLS:
        raise ProblemException(
            code="INVALID_CALL_BUDGET",
            status=422,
            title="Invalid Call Budget",
            detail=f"max_calls must be between 1 and {MAX_EPHEMERAL_CALLS}.",
        )

    effective_tools = (
        allowed_tools
        if allowed_tools is not None
        else ["read_doc", "read_ticket", "search_knowledge", "search_tickets"]
    )
    if not effective_tools or not (1 <= len(effective_tools) <= MAX_ALLOWED_EPHEMERAL_TOOLS):
        raise ProblemException(
            code="INVALID_TOOLS",
            status=422,
            title="Invalid Allowed Tools",
            detail=f"allowed_tools must contain between 1 and {MAX_ALLOWED_EPHEMERAL_TOOLS} tools.",
        )

    disallowed_tools = [t for t in effective_tools if t not in ALLOWED_EPHEMERAL_TOOLS]
    if disallowed_tools:
        raise ProblemException(
            code="INVALID_TOOLS",
            status=422,
            title="Invalid Allowed Tools",
            detail=(
                f"Tools {disallowed_tools} not allowed. Ephemeral tokens allow only: "
                f"{sorted(ALLOWED_EPHEMERAL_TOOLS)}."
            ),
        )

    # Normalize tools for database check constraint compatibility
    # (map 'search' -> 'search_knowledge')
    db_tools = list(
        dict.fromkeys("search_knowledge" if t == "search" else t for t in effective_tools)
    )

    # Ensure transaction RLS context is bound when running under non-bypass kanban_app role
    curr_ws = (
        await session.execute(text("SELECT NULLIF(current_setting('app.workspace_id', true), '')"))
    ).scalar_one_or_none()
    if not curr_ws:
        await session.execute(
            text(
                "SELECT set_config('app.workspace_id', :ws, true), "
                "set_config('app.principal_id', :pid, true)"
            ),
            {"ws": str(workspace_id), "pid": str(invoking_principal_id)},
        )

    # Validate agent principal
    agent_principal = await session.get(Principal, agent_principal_id)
    if (
        agent_principal is None
        or agent_principal.workspace_id != workspace_id
        or agent_principal.status != "ACTIVE"
        or agent_principal.principal_type != "AGENT"
    ):
        raise ProblemException(
            code="INVALID_PRINCIPAL",
            status=422,
            title="Invalid Agent Principal",
            detail="agent_principal_id must refer to an active AGENT principal in the workspace.",
        )

    # Validate invoking principal
    invoking_principal = await session.get(Principal, invoking_principal_id)
    if (
        invoking_principal is None
        or invoking_principal.workspace_id != workspace_id
        or invoking_principal.status != "ACTIVE"
    ):
        raise ProblemException(
            code="INVALID_PRINCIPAL",
            status=422,
            title="Invalid Invoking Principal",
            detail="invoking_principal_id must refer to an active principal in the workspace.",
        )

    # Validate project
    project = await session.get(Project, project_id)
    if project is None or project.workspace_id != workspace_id:
        raise ProblemException(
            code="INVALID_PROJECT",
            status=422,
            title="Invalid Project",
            detail="project_id must refer to a project in the target workspace.",
        )

    # Validate active workflow transition execution and hook-to-agent binding (KAN-63 / Action 3)
    await _verify_active_execution_binding(
        session,
        workspace_id=workspace_id,
        execution_id=execution_id,
        invoking_principal_id=invoking_principal_id,
        agent_principal_id=agent_principal_id,
        project_id=project_id,
    )

    token, token_sha256 = generate_ephemeral_mcp_token()
    now = datetime.now(UTC)
    expires_at = now + timedelta(seconds=ttl_seconds)

    record = McpEphemeralToken(
        workspace_id=workspace_id,
        execution_id=execution_id,
        invoking_principal_id=invoking_principal_id,
        agent_principal_id=agent_principal_id,
        project_id=project_id,
        token_sha256=token_sha256,
        allowed_tools=db_tools,
        max_calls=max_calls,
        calls_used=0,
        created_at=now,
        expires_at=expires_at,
    )
    session.add(record)
    await session.flush()
    await session.refresh(record)

    return record, token


async def revoke_ephemeral_tokens_by_execution(
    session: AsyncSession,
    *,
    execution_id: uuid.UUID,
) -> int:
    """Revoke all active ephemeral MCP tokens bound to execution_id."""
    stmt = text(
        "UPDATE mcp_ephemeral_tokens "
        "SET revoked_at = clock_timestamp() "
        "WHERE execution_id = :exec_id AND revoked_at IS NULL"
    )
    result = await session.execute(stmt, {"exec_id": execution_id})
    return int(cast("CursorResult[Any]", result).rowcount)


async def introspect_and_consume_ephemeral_token(  # noqa: C901, PLR0911, PLR0912
    session: AsyncSession,
    *,
    token: str,
    surface: str | None = None,
    consume_call: bool = False,
    tool_name: str | None = None,
) -> McpIntrospectionResult:
    """Introspect and conditionally consume an ephemeral MCP token.

    Enforces:
    - Surface: valid only on 'agent' and 'docs'; 'admin' returns SURFACE_KEY_MISMATCH.
    - Zero-cache atomic budget decrement on consume_call=True.
    - Read-only tool allowlist check.
    """
    if surface == "admin":
        return McpIntrospectionResult(active=False, reason="SURFACE_KEY_MISMATCH")

    if surface is not None and surface not in ("agent", "docs"):
        return McpIntrospectionResult(active=False, reason="SURFACE_KEY_MISMATCH")

    digest = hash_mcp_api_key(token)
    now = datetime.now(UTC)

    if not consume_call:
        # Non-consuming check (e.g. initialize, tools/list)
        stmt = text(
            "SELECT id, workspace_id, execution_id, invoking_principal_id, "
            "agent_principal_id, project_id, allowed_tools, max_calls, calls_used, "
            "expires_at, revoked_at "
            "FROM mcp_ephemeral_tokens "
            "WHERE token_sha256 = :digest"
        )
        row = (await session.execute(stmt, {"digest": digest})).first()
        if row is None:
            return McpIntrospectionResult(active=False, reason="SURFACE_KEY_MISMATCH")

        (
            _id,
            workspace_id,
            execution_id,
            invoking_principal_id,
            agent_principal_id,
            project_id,
            allowed_tools,
            max_calls,
            calls_used,
            expires_at,
            revoked_at,
        ) = row

        if revoked_at is not None or expires_at <= now:
            return McpIntrospectionResult(active=False, reason="TOKEN_EXPIRED_OR_REVOKED")

        if calls_used >= max_calls:
            return McpIntrospectionResult(
                active=False,
                reason="EPHEMERAL_CALL_BUDGET_EXCEEDED",
                calls_used=calls_used,
                max_calls=max_calls,
                workspace_id=workspace_id,
                project_id=project_id,
                execution_id=execution_id,
            )

        # Check principal status
        invoker_status = (
            await session.execute(
                select(Principal.status).where(Principal.id == invoking_principal_id)
            )
        ).scalar_one_or_none()
        agent_status = (
            await session.execute(
                select(Principal.status).where(Principal.id == agent_principal_id)
            )
        ).scalar_one_or_none()

        if invoker_status != "ACTIVE" or agent_status != "ACTIVE":
            return McpIntrospectionResult(active=False, reason="TOKEN_EXPIRED_OR_REVOKED")

        surface_key = surface or "agent"
        allowed_set = SURFACE_ALLOWED_EPHEMERAL_TOOLS.get(surface_key, frozenset())
        surface_tools = sorted(t for t in allowed_tools if t in allowed_set)
        if (
            surface_key == "docs"
            and (
                "search_knowledge" in allowed_tools
                or "read_doc" in allowed_tools
                or "search" in allowed_tools
            )
            and "search" not in surface_tools
        ):
            surface_tools = sorted([*surface_tools, "search"])

        return McpIntrospectionResult(
            active=True,
            principal_id=invoking_principal_id,
            agent_principal_id=agent_principal_id,
            workspace_id=workspace_id,
            project_id=project_id,
            execution_id=execution_id,
            surface=surface_key,
            scopes=["agent:read", "docs:read"],
            token_kind="ephemeral",  # noqa: S106
            allowed_tools=surface_tools,
            calls_used=calls_used,
            max_calls=max_calls,
            expires_at=expires_at,
        )

    # Consuming call (tools/call)
    if tool_name is None:
        return McpIntrospectionResult(active=False, reason="EPHEMERAL_TOOL_FORBIDDEN")

    surface_key = surface or "agent"
    surface_allowed_set = SURFACE_ALLOWED_EPHEMERAL_TOOLS.get(surface_key, frozenset())
    if tool_name not in ALLOWED_EPHEMERAL_TOOLS or tool_name not in surface_allowed_set:
        return McpIntrospectionResult(active=False, reason="EPHEMERAL_TOOL_FORBIDDEN")

    # Atomic call budget decrement
    update_stmt = text(
        "UPDATE mcp_ephemeral_tokens "
        "SET calls_used = calls_used + 1 "
        "WHERE token_sha256 = :digest "
        "  AND revoked_at IS NULL "
        "  AND expires_at > clock_timestamp() "
        "  AND calls_used < max_calls "
        "  AND ("
        "       :tool_name = ANY(allowed_tools) "
        "       OR (:tool_name = 'search' AND ("
        "            'search_knowledge' = ANY(allowed_tools) "
        "            OR 'read_doc' = ANY(allowed_tools)"
        "       ))"
        "  ) "
        "RETURNING id, workspace_id, execution_id, invoking_principal_id, "
        "agent_principal_id, project_id, allowed_tools, max_calls, calls_used, expires_at"
    )
    updated_row = (
        await session.execute(update_stmt, {"digest": digest, "tool_name": tool_name})
    ).first()

    if updated_row is not None:
        (
            _id,
            workspace_id,
            execution_id,
            invoking_principal_id,
            agent_principal_id,
            project_id,
            allowed_tools,
            max_calls,
            calls_used,
            expires_at,
        ) = updated_row

        # Verify active principals
        invoker_status = (
            await session.execute(
                select(Principal.status).where(Principal.id == invoking_principal_id)
            )
        ).scalar_one_or_none()
        agent_status = (
            await session.execute(
                select(Principal.status).where(Principal.id == agent_principal_id)
            )
        ).scalar_one_or_none()

        if invoker_status != "ACTIVE" or agent_status != "ACTIVE":
            return McpIntrospectionResult(active=False, reason="TOKEN_EXPIRED_OR_REVOKED")

        surface_tools = sorted(t for t in allowed_tools if t in surface_allowed_set)
        if (
            surface_key == "docs"
            and (
                "search_knowledge" in allowed_tools
                or "read_doc" in allowed_tools
                or "search" in allowed_tools
            )
            and "search" not in surface_tools
        ):
            surface_tools = sorted([*surface_tools, "search"])
        return McpIntrospectionResult(
            active=True,
            principal_id=invoking_principal_id,
            agent_principal_id=agent_principal_id,
            workspace_id=workspace_id,
            project_id=project_id,
            execution_id=execution_id,
            surface=surface_key,
            scopes=["agent:read", "docs:read"],
            token_kind="ephemeral",  # noqa: S106
            allowed_tools=surface_tools,
            calls_used=calls_used,
            max_calls=max_calls,
            expires_at=expires_at,
        )

    # 0 rows updated: determine exact failure reason
    inspect_stmt = text(
        "SELECT calls_used, max_calls, expires_at, revoked_at, allowed_tools, "
        "workspace_id, project_id, execution_id "
        "FROM mcp_ephemeral_tokens WHERE token_sha256 = :digest"
    )
    rec = (await session.execute(inspect_stmt, {"digest": digest})).first()
    if rec is None:
        return McpIntrospectionResult(active=False, reason="NOT_FOUND")

    (
        rec_calls_used,
        rec_max_calls,
        rec_expires,
        rec_revoked,
        rec_tools,
        rec_ws_id,
        rec_proj_id,
        rec_exec_id,
    ) = rec
    tool_allowed = tool_name in rec_tools or (
        tool_name == "search" and ("search_knowledge" in rec_tools or "read_doc" in rec_tools)
    )
    if not tool_allowed:
        return McpIntrospectionResult(active=False, reason="EPHEMERAL_TOOL_FORBIDDEN")
    if rec_revoked is not None or rec_expires <= now:
        return McpIntrospectionResult(active=False, reason="TOKEN_EXPIRED_OR_REVOKED")
    if rec_calls_used >= rec_max_calls:
        return McpIntrospectionResult(
            active=False,
            reason="EPHEMERAL_CALL_BUDGET_EXCEEDED",
            calls_used=rec_calls_used,
            max_calls=rec_max_calls,
            workspace_id=rec_ws_id,
            project_id=rec_proj_id,
            execution_id=rec_exec_id,
        )

    return McpIntrospectionResult(active=False, reason="TOKEN_EXPIRED_OR_REVOKED")
