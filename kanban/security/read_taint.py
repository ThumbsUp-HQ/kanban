# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Session read-taint exfiltration guard and recorder (KB-P4-07 / S3.5, S11.2)."""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Annotated, Any, Final, Literal, cast

from fastapi import Depends, Request
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: TC002

from database.models.projects import Project
from database.session import RLSContext, RLSSessionFactory
from kanban.api.deps import PrincipalContext, get_principal, get_rls_session
from kanban.api.problems import ProblemException
from kanban.security.service_auth import KNOWN_SERVICE_PRINCIPALS, verify_internal_service_auth
from kanban.services.activity import ActivityEventType, record_activity

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

__all__ = [
    "CREDENTIAL_TAINT_TTL_HOURS",
    "SESSION_TAINT_TTL_SECONDS",
    "TaintGuard",
    "TaintRecorder",
    "get_taint_guard",
    "get_taint_recorder",
]

SESSION_TAINT_TTL_SECONDS: Final[int] = 3600
CREDENTIAL_TAINT_TTL_HOURS: Final[int] = 8

_UUID_REGEX_LEN: Final[int] = 36


async def _resolve_project_uuid(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    project_ref: uuid.UUID | str,
) -> tuple[uuid.UUID, str] | None:
    """Resolve project reference (UUID or identifier) to (project_id, identifier)."""
    if isinstance(project_ref, uuid.UUID):
        stmt = select(Project.id, Project.identifier).where(
            Project.id == project_ref, Project.workspace_id == workspace_id
        )
        row = (await session.execute(stmt)).first()
        return (row[0], row[1]) if row is not None else None

    ref_str = str(project_ref).strip()
    try:
        parsed_uuid = uuid.UUID(ref_str)
        stmt = select(Project.id, Project.identifier).where(
            Project.id == parsed_uuid, Project.workspace_id == workspace_id
        )
        row = (await session.execute(stmt)).first()
        if row is not None:
            return (row[0], row[1])
    except ValueError:
        pass

    stmt = select(Project.id, Project.identifier).where(
        Project.identifier == ref_str, Project.workspace_id == workspace_id
    )
    row = (await session.execute(stmt)).first()
    return (row[0], row[1]) if row is not None else None


def _resolve_verified_service_principal(request: Request) -> str | None:
    """Resolve verified service principal via HMAC header or ASGI TLS client_cert only."""
    scope = getattr(request, "scope", None)
    if request.headers.get("x-kb-internal-auth") is not None or (
        isinstance(scope, dict) and scope.get("client_cert") is not None
    ):
        return verify_internal_service_auth(
            request,
            allowed_principals=KNOWN_SERVICE_PRINCIPALS,
        )
    return None


class TaintRecorder:
    """FastAPI dependency recording project read-taint for MCP sessions."""

    def __init__(
        self,
        request: Request,
        session: Annotated[AsyncSession, Depends(get_rls_session)],
        caller: Annotated[PrincipalContext, Depends(get_principal)],
    ) -> None:
        """Initialize TaintRecorder dependency and verify internal service authentication."""
        self.request: Final[Request] = request
        self.session: Final[AsyncSession] = session
        self.caller: Final[PrincipalContext] = caller
        self.session_id: Final[str | None] = request.headers.get("x-kb-mcp-session")
        self.service_principal: Final[str | None] = _resolve_verified_service_principal(request)

        if self.service_principal == "mcp-gateway" and not self.session_id:
            raise ProblemException(
                code="MISSING_MCP_SESSION",
                status=400,
                title="Missing MCP Session",
                detail=(
                    "Requests from mcp-gateway service principal require X-KB-MCP-Session header."
                ),
            )

    async def record_project_ids(
        self,
        project_refs: Iterable[uuid.UUID | str],
        *,
        untrusted_source_object_id: uuid.UUID | str | None = None,
        contains_untrusted_content: bool = False,
    ) -> None:
        """Record read-taint for all distinct project IDs returned in a response."""
        if not self.session_id or self.caller.read_only:
            return

        session_key = hashlib.sha256(self.session_id.encode("utf-8")).digest()
        subject_token = self.request.headers.get("x-kb-subject-token") or getattr(
            self.caller, "token", None
        )
        credential_key = (
            hashlib.sha256(subject_token.encode("utf-8")).digest()
            if subject_token is not None
            else None
        )

        now = datetime.now(UTC)
        session_expires = now + timedelta(seconds=SESSION_TAINT_TTL_SECONDS)
        cred_expires = now + timedelta(hours=CREDENTIAL_TAINT_TTL_HOURS)

        parsed_source_obj_id: uuid.UUID | None = None
        if untrusted_source_object_id is not None:
            if isinstance(untrusted_source_object_id, uuid.UUID):
                parsed_source_obj_id = untrusted_source_object_id
            else:
                try:
                    parsed_source_obj_id = uuid.UUID(str(untrusted_source_object_id))
                except (ValueError, TypeError):
                    parsed_source_obj_id = None

        upsert_sql = text(
            """
            INSERT INTO mcp_read_taint (
                workspace_id, taint_key, key_kind, project_id, first_read_at, expires_at,
                untrusted_source_object_id, contains_untrusted_content
            )
            VALUES (
                :ws_id, :taint_key, :key_kind, :proj_id, :now, :expires_at,
                :untrusted_source_object_id, :contains_untrusted_content
            )
            ON CONFLICT (taint_key, project_id)
            DO UPDATE SET
                expires_at = EXCLUDED.expires_at,
                contains_untrusted_content = (
                    mcp_read_taint.contains_untrusted_content
                    OR EXCLUDED.contains_untrusted_content
                ),
                untrusted_source_object_id = COALESCE(
                    EXCLUDED.untrusted_source_object_id,
                    mcp_read_taint.untrusted_source_object_id
                );
            """
        )

        seen_projects: set[uuid.UUID] = set()
        for ref in project_refs:
            resolved = await _resolve_project_uuid(self.session, self.caller.workspace_id, ref)
            if resolved is None:
                continue
            proj_id, _ = resolved
            if proj_id in seen_projects:
                continue
            seen_projects.add(proj_id)

            # Record session taint
            await self.session.execute(
                upsert_sql,
                {
                    "ws_id": self.caller.workspace_id,
                    "taint_key": session_key,
                    "key_kind": "session",
                    "proj_id": proj_id,
                    "now": now,
                    "expires_at": session_expires,
                    "untrusted_source_object_id": parsed_source_obj_id,
                    "contains_untrusted_content": contains_untrusted_content,
                },
            )

            # Record credential taint
            if credential_key is not None:
                await self.session.execute(
                    upsert_sql,
                    {
                        "ws_id": self.caller.workspace_id,
                        "taint_key": credential_key,
                        "key_kind": "credential",
                        "proj_id": proj_id,
                        "now": now,
                        "expires_at": cred_expires,
                        "untrusted_source_object_id": parsed_source_obj_id,
                        "contains_untrusted_content": contains_untrusted_content,
                    },
                )

        if seen_projects:
            await self.session.flush()

    async def record_untrusted_read(
        self,
        project_ref: uuid.UUID | str,
        untrusted_source_object_id: uuid.UUID | str | None = None,
    ) -> None:
        """Record untrusted content read-taint for a project and source object."""
        await self.record_project_ids(
            [project_ref],
            untrusted_source_object_id=untrusted_source_object_id,
            contains_untrusted_content=True,
        )


class TaintGuard:
    """FastAPI dependency enforcing read-taint exfiltration guards on MCP writes."""

    def __init__(
        self,
        request: Request,
        session: Annotated[AsyncSession, Depends(get_rls_session)],
        caller: Annotated[PrincipalContext, Depends(get_principal)],
    ) -> None:
        """Initialize TaintGuard dependency and verify internal service authentication."""
        self.request: Final[Request] = request
        self.session: Final[AsyncSession] = session
        self.caller: Final[PrincipalContext] = caller
        self.session_id: Final[str | None] = request.headers.get("x-kb-mcp-session")
        self.service_principal: Final[str | None] = _resolve_verified_service_principal(request)

        if self.service_principal == "mcp-gateway" and not self.session_id:
            raise ProblemException(
                code="MISSING_MCP_SESSION",
                status=400,
                title="Missing MCP Session",
                detail=(
                    "Requests from mcp-gateway service principal require X-KB-MCP-Session header."
                ),
            )

    async def _emit_blocked_activity(
        self,
        source_proj_id: uuid.UUID,
        target_proj_id: uuid.UUID,
        effective_tool: str,
        session_key: bytes,
        untrusted_source_object_id: uuid.UUID | None = None,
    ) -> None:
        """Emit MCP_TAINT_BLOCKED activity event to the immutable ledger."""
        session_key_hash = hashlib.sha256(session_key).hexdigest()
        payload: dict[str, Any] = {
            "session_key_hash": session_key_hash,
            "source_project_id": str(source_proj_id),
            "target_project_id": str(target_proj_id),
            "tool_name": effective_tool,
            "tool": effective_tool,
        }
        if untrusted_source_object_id is not None:
            payload["untrusted_source_object_id"] = str(untrusted_source_object_id)

        session_factory: RLSSessionFactory | None = getattr(
            self.request.app.state, "session_factory", None
        )
        if session_factory is not None:
            user_access_hash = self.caller.user_access_hash
            if user_access_hash is None:
                caller = self.caller
                scopes_str = ",".join(sorted(caller.token_scopes))
                raw = f"{caller.workspace_id}:{caller.principal_id}:{scopes_str}".encode()
                user_access_hash = hashlib.sha256(raw).digest()
            audit_ctx = RLSContext(
                principal_id=self.caller.principal_id,
                workspace_id=self.caller.workspace_id,
                token_scopes=self.caller.token_scopes,
                aal_level=cast("Literal[1, 2]", self.caller.aal_level),
                agent_principal_id=self.caller.agent_principal_id,
                ephemeral_project_id=self.caller.ephemeral_project_id,
                read_only=False,
                user_access_hash=user_access_hash,
            )
            async with session_factory.session(audit_ctx) as audit_session:
                await record_activity(
                    session=audit_session,
                    workspace_id=self.caller.workspace_id,
                    object_id=target_proj_id,
                    actor_principal_id=self.caller.principal_id,
                    event_type=ActivityEventType.MCP_TAINT_BLOCKED,
                    payload=payload,
                )
        else:
            await record_activity(
                session=self.session,
                workspace_id=self.caller.workspace_id,
                object_id=target_proj_id,
                actor_principal_id=self.caller.principal_id,
                event_type=ActivityEventType.MCP_TAINT_BLOCKED,
                payload=payload,
            )
            await self.session.flush()

    async def check_write(
        self,
        target_projects: uuid.UUID | str | Sequence[uuid.UUID | str],
        tool_name: str | None = None,
        confirmation_token: str | None = None,
    ) -> None:
        """Assert write target project(s) audience is not broader than any tainted project."""
        if not self.session_id:
            return

        session_key = hashlib.sha256(self.session_id.encode("utf-8")).digest()
        subject_token = self.request.headers.get("x-kb-subject-token") or getattr(
            self.caller, "token", None
        )
        taint_keys: list[bytes] = [session_key]
        if subject_token is not None:
            credential_key = hashlib.sha256(subject_token.encode("utf-8")).digest()
            taint_keys.append(credential_key)

        now = datetime.now(UTC)
        targets = (
            [target_projects]
            if isinstance(target_projects, (str, uuid.UUID))
            else list(target_projects)
        )

        query_token: str | None = None
        req_scope = getattr(self.request, "scope", None)
        if isinstance(req_scope, dict) and "query_string" in req_scope:
            query_token = self.request.query_params.get("confirmation_token")

        has_confirmation = bool(
            (confirmation_token and str(confirmation_token).strip())
            or self.request.headers.get("x-kb-confirmation-token", "").strip()
            or (query_token and str(query_token).strip())
        )
        effective_tool = tool_name or self.request.headers.get("x-kb-mcp-tool") or "unknown"

        # Problem 2: Same-project & cross-project untrusted prompt-injection taint block
        if not has_confirmation:
            untrusted_query = text(
                """
                SELECT t.project_id, p.identifier AS project_key, t.untrusted_source_object_id
                FROM mcp_read_taint t
                JOIN projects p ON p.id = t.project_id
                WHERE t.taint_key = ANY(:taint_keys)
                  AND t.expires_at > :now
                  AND t.contains_untrusted_content = TRUE
                LIMIT 1;
                """
            )
            untrusted_row = (
                await self.session.execute(
                    untrusted_query,
                    {
                        "taint_keys": taint_keys,
                        "now": now,
                    },
                )
            ).first()

            if untrusted_row is not None:
                source_proj_id, source_proj_key, untrusted_source_id = (
                    untrusted_row[0],
                    untrusted_row[1],
                    untrusted_row[2],
                )
                target_ref = targets[0] if targets else "unknown"
                resolved = await _resolve_project_uuid(
                    self.session, self.caller.workspace_id, target_ref
                )
                target_proj_id = resolved[0] if resolved else source_proj_id
                target_proj_key = resolved[1] if resolved else source_proj_key

                await self._emit_blocked_activity(
                    source_proj_id=source_proj_id,
                    target_proj_id=target_proj_id,
                    effective_tool=effective_tool,
                    session_key=session_key,
                    untrusted_source_object_id=untrusted_source_id,
                )

                raise ProblemException(
                    code="UNTRUSTED_CONTENT_TAINT_ACTIVE",
                    status=409,
                    title="Untrusted Content Taint Active",
                    type_uri="urn:kanban:problem:untrusted-content-taint",
                    detail=(
                        f"Mutating operation '{effective_tool}' blocked across project "
                        f"'{target_proj_key}' due to active untrusted content read-taint "
                        f"from '{source_proj_key}'."
                    ),
                    extra={
                        "tainted_by": [source_proj_key],
                        "untrusted_source_object_id": (
                            str(untrusted_source_id) if untrusted_source_id is not None else None
                        ),
                        "hint": (
                            "Ask a human to confirm or execute this mutating operation "
                            "in the web UI."
                        ),
                    },
                )

        # Cross-project broader-ACL exfiltration guard for trusted content
        query = text(
            """
            SELECT t.project_id, p.identifier AS project_key
            FROM mcp_read_taint t
            JOIN projects p ON p.id = t.project_id
            WHERE t.taint_key = ANY(:taint_keys)
              AND t.expires_at > :now
              AND t.project_id <> :target_project_id
              AND EXISTS (
                  SELECT 1 FROM effective_resource_access b
                  WHERE b.object_id = :target_project_id
                    AND (b.allow_mask & 1) = 1
                    AND (b.deny_mask & 1) = 0
                    AND NOT EXISTS (
                        SELECT 1 FROM effective_resource_access a
                        WHERE a.object_id = t.project_id
                          AND a.principal_id = b.principal_id
                          AND (a.allow_mask & 1) = 1
                          AND (a.deny_mask & 1) = 0
                    )
              )
            LIMIT 1;
            """
        )

        for ref in targets:
            resolved = await _resolve_project_uuid(self.session, self.caller.workspace_id, ref)
            if resolved is None:
                continue
            target_proj_id, target_proj_key = resolved

            result = (
                await self.session.execute(
                    query,
                    {
                        "taint_keys": taint_keys,
                        "now": now,
                        "target_project_id": target_proj_id,
                    },
                )
            ).first()

            if result is not None:
                source_proj_id, source_proj_key = result[0], result[1]
                await self._emit_blocked_activity(
                    source_proj_id=source_proj_id,
                    target_proj_id=target_proj_id,
                    effective_tool=effective_tool,
                    session_key=session_key,
                )

                raise ProblemException(
                    code="CROSS_SCOPE_TAINT_CONFIRMATION_REQUIRED",
                    status=409,
                    title="Cross-Scope Taint Confirmation Required",
                    type_uri="urn:kanban:problem:cross-scope-taint",
                    detail=(
                        f"Write to project '{target_proj_key}' blocked due to session read-taint "
                        f"from '{source_proj_key}'."
                    ),
                    extra={
                        "tainted_by": [source_proj_key],
                        "hint": "Ask a human to perform this write in the web UI.",
                    },
                )


def get_taint_recorder(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_rls_session)],
    caller: Annotated[PrincipalContext, Depends(get_principal)],
) -> TaintRecorder:
    """Dependency provider for TaintRecorder."""
    return TaintRecorder(request, session, caller)


def get_taint_guard(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_rls_session)],
    caller: Annotated[PrincipalContext, Depends(get_principal)],
) -> TaintGuard:
    """Dependency provider for TaintGuard."""
    return TaintGuard(request, session, caller)
