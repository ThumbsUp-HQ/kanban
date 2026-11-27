# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Background runner executing GateWorker against asynchronous transition gates (S14.3, KAN-45)."""

from __future__ import annotations

import asyncio
import contextlib
import datetime as dt
import logging
import uuid
from typing import TYPE_CHECKING, Any, Literal

from sqlalchemy import or_, select, text

from agent.gates.worker import GateWorker, HarnessRegistry
from database.models.agent_definition import AgentDefinition
from database.models.ai import AIProviderConfig
from database.models.issues import Issue, IssueComment
from database.models.projects import Project, WorkflowState
from database.models.repo_binding import ProjectRepoBinding
from database.models.workflow import (
    WorkflowHookInvocation,
    WorkflowTransitionExecution,
    WorkflowTransitionHook,
)
from database.session import RLSContext, RLSSessionFactory
from kanban.workflows.async_gate import GateCoordinator
from kanban.workflows.gate_types import resolve_effective_gate_timeout_ms

if TYPE_CHECKING:
    from agent.context.transition_context import RepoContext

logger = logging.getLogger(__name__)

__all__ = [
    "GateWorkerRunner",
    "start_gate_worker",
]


MAX_GATE_COMMENTS = 200


async def _load_issue_comments(session: Any, issue_id: uuid.UUID) -> list[dict[str, Any]]:  # noqa: ANN401
    """Load all non-deleted ticket comments (oldest first, bounded) as plain dicts."""
    rows = (
        (
            await session.execute(
                select(IssueComment)
                .where(IssueComment.issue_id == issue_id, IssueComment.deleted_at.is_(None))
                .order_by(IssueComment.created_at.asc())
                .limit(MAX_GATE_COMMENTS)
            )
        )
        .scalars()
        .all()
    )
    return [
        {
            "body": c.body_markdown,
            "author": str(c.author_id),
            "provenance_tier": c.provenance_tier,
        }
        for c in rows
    ]


async def _load_repo_context(session: Any, project_id: uuid.UUID) -> RepoContext | None:  # noqa: ANN401
    """Resolve a read-only RepoContext from the project's repo binding, or None."""
    binding = (
        await session.execute(
            select(ProjectRepoBinding)
            .where(ProjectRepoBinding.project_id == project_id)
            .order_by(ProjectRepoBinding.slug.asc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if binding is None:
        return None
    from agent.context.repo_context import resolve_repo_context  # noqa: PLC0415
    from agent.context.transition_context import RepoContext as _RepoContext  # noqa: PLC0415

    try:
        resolved = await resolve_repo_context(binding)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Repo context unavailable for project %s: %s", project_id, exc)
        return None
    return _RepoContext(head_commit=resolved.head_commit, mirror_path=resolved.mirror_path)


class GateWorkerRunner:
    """Consumes pending transition gate invocations and coordinates asynchronous decisions."""

    def __init__(  # noqa: PLR0913, PLR0917
        self,
        session_factory: RLSSessionFactory | None = None,
        harness_registry: HarnessRegistry | None = None,
        poll_interval_s: float = 1.0,
        workspace_id: uuid.UUID | None = None,
        admin_principal_id: uuid.UUID | None = None,
        worker_id: str | None = None,
        heartbeat_interval_s: float = 20.0,
        lease_ttl_s: float = 60.0,
    ) -> None:
        """Initialize runner with session factory, harness registry, and poll interval."""
        self.session_factory = session_factory
        self.registry = harness_registry or HarnessRegistry()
        self.poll_interval_s = poll_interval_s
        self.workspace_id = workspace_id
        self.admin_principal_id = admin_principal_id
        self.worker_id = worker_id or f"worker-{uuid.uuid4().hex[:8]}"
        self.heartbeat_interval_s = heartbeat_interval_s
        self.lease_ttl_s = lease_ttl_s
        self.worker = GateWorker(
            registry=self.registry,
            coordinator=self,
            entity_loader=self._load_entities,
        )
        self._active_invocations: set[uuid.UUID] = set()
        self._execution_contexts: dict[uuid.UUID, dict[str, Any]] = {}

    @property
    def active_invocations(self) -> frozenset[uuid.UUID]:
        """Active leased invocation IDs currently being processed."""
        return frozenset(self._active_invocations)

    async def _resolve_workspace_and_admin(
        self,
    ) -> tuple[uuid.UUID | None, uuid.UUID | None]:
        """Resolve target workspace and administrative/agent principal."""
        ws_id = self.workspace_id
        admin_pid = self.admin_principal_id

        if ws_id is not None and admin_pid is not None:
            return ws_id, admin_pid

        if self.session_factory is None:
            return ws_id, admin_pid

        engine = getattr(self.session_factory, "engine", None) or getattr(
            self.session_factory, "_engine", None
        )
        if engine is not None:
            try:
                async with engine.connect() as conn:
                    if ws_id is None:
                        res = await conn.execute(text("SELECT get_default_workspace_id()"))
                        ws_id = res.scalar()
                    if admin_pid is None:
                        res = await conn.execute(
                            text("SELECT principal_id FROM kb_auth.local_get_credential('admin')")
                        )
                        row = res.first()
                        if row is not None:
                            admin_pid = row[0]
            except Exception as exc:  # noqa: BLE001
                logger.debug("Could not resolve workspace/admin from DB: %s", exc)

        return ws_id, admin_pid

    async def record_decision(
        self, execution_id: object, hook_id: object, decision: object
    ) -> None:
        """Forward validated decision to GateCoordinator within an authorized RLS session."""
        if self.session_factory is None:
            return

        exec_uuid = (
            execution_id
            if isinstance(execution_id, uuid.UUID)
            else (uuid.UUID(str(execution_id)) if execution_id else None)
        )
        ctx_info = self._execution_contexts.get(exec_uuid, {}) if exec_uuid else {}
        ws_id = ctx_info.get("workspace_id") or self.workspace_id or uuid.UUID(int=0)
        p_id = (
            ctx_info.get("admin_principal_id")
            or self.admin_principal_id
            or ctx_info.get("agent_principal_id")
            or uuid.UUID(int=0)
        )

        admin_ctx = RLSContext(
            principal_id=p_id,
            workspace_id=ws_id,
            token_scopes=("admin",),
            aal_level=2,
        )
        async with self.session_factory.session(admin_ctx) as session:
            await GateCoordinator.record_decision(
                session=session,
                execution_id=execution_id,  # type: ignore[arg-type]
                hook_id=hook_id,  # type: ignore[arg-type]
                decision=decision,  # type: ignore[arg-type]
            )
            await session.commit()

    async def record_failure(
        self,
        execution_id: object,
        hook_id: object,
        code: str,
        *,
        invocation_id: uuid.UUID | str | None = None,
        detail: str | None = None,
    ) -> None:
        """Forward failure or timeout to GateCoordinator within an authorized RLS session."""
        if self.session_factory is None:
            return

        exec_uuid = (
            execution_id
            if isinstance(execution_id, uuid.UUID)
            else (uuid.UUID(str(execution_id)) if execution_id else None)
        )
        ctx_info = self._execution_contexts.get(exec_uuid, {}) if exec_uuid else {}
        ws_id = ctx_info.get("workspace_id") or self.workspace_id or uuid.UUID(int=0)
        p_id = (
            ctx_info.get("admin_principal_id")
            or self.admin_principal_id
            or ctx_info.get("agent_principal_id")
            or uuid.UUID(int=0)
        )

        admin_ctx = RLSContext(
            principal_id=p_id,
            workspace_id=ws_id,
            token_scopes=("admin",),
            aal_level=2,
        )
        async with self.session_factory.session(admin_ctx) as session:
            if invocation_id is not None:
                await GateCoordinator(session).record_failure(
                    invocation_id=invocation_id,
                    error_code=code,
                    detail=detail,
                )
            else:
                await GateCoordinator.record_failure(
                    session=session,
                    execution_id=execution_id,  # type: ignore[arg-type]
                    hook_id=hook_id,  # type: ignore[arg-type]
                    code=code,
                    detail=detail,
                )
            await session.commit()

    async def _load_entities(  # noqa: C901, PLR0912, PLR0915
        self, event: object
    ) -> tuple[object, object, object, RepoContext | None, object]:
        """Load execution, issue, agent_def, and metadata from database."""
        payload: dict[str, Any] = (
            event
            if isinstance(event, dict)
            else (
                getattr(event, "payload", {})
                if isinstance(getattr(event, "payload", None), dict)
                else {}
            )
        )
        execution_id_str = str(payload.get("execution_id") or getattr(event, "execution_id", ""))
        hook_id_str = str(payload.get("hook_id") or getattr(event, "hook_id", ""))
        agent_def_id_str = str(
            payload.get("agent_definition_id") or getattr(event, "agent_definition_id", "")
        )

        if self.session_factory is None:
            return (
                payload.get("execution"),
                payload.get("issue"),
                payload.get("agent_def"),
                None,
                payload.get("mcp_urls"),
            )

        exec_uuid = uuid.UUID(execution_id_str) if execution_id_str else None
        ctx_info = self._execution_contexts.get(exec_uuid, {}) if exec_uuid else {}
        ws_id_val = payload.get("workspace_id")
        ws_id = (
            (uuid.UUID(str(ws_id_val)) if ws_id_val else None)
            or ctx_info.get("workspace_id")
            or self.workspace_id
            or uuid.UUID(int=0)
        )
        admin_pid_val = payload.get("admin_principal_id")
        agent_pid_val = payload.get("agent_principal_id")
        p_id = (
            (uuid.UUID(str(admin_pid_val)) if admin_pid_val else None)
            or ctx_info.get("admin_principal_id")
            or self.admin_principal_id
            or (uuid.UUID(str(agent_pid_val)) if agent_pid_val else None)
            or ctx_info.get("agent_principal_id")
            or uuid.UUID(int=0)
        )

        admin_ctx = RLSContext(
            principal_id=p_id,
            workspace_id=ws_id,
            token_scopes=("admin",),
            aal_level=2,
        )
        async with self.session_factory.session(admin_ctx) as session:
            exec_uuid_val = uuid.UUID(execution_id_str) if execution_id_str else None
            hook_uuid_val = uuid.UUID(hook_id_str) if hook_id_str else None
            execution = (
                await session.get(WorkflowTransitionExecution, exec_uuid_val)
                if exec_uuid_val
                else None
            )
            hook = (
                await session.get(WorkflowTransitionHook, hook_uuid_val) if hook_uuid_val else None
            )
            agent_def = (
                await session.get(AgentDefinition, uuid.UUID(agent_def_id_str))
                if agent_def_id_str
                else (
                    await session.get(AgentDefinition, hook.agent_definition_id)
                    if hook and hook.agent_definition_id
                    else None
                )
            )
            issue = await session.get(Issue, execution.issue_id) if execution else None
            project = await session.get(Project, execution.project_id) if execution else None
            from_state = (
                await session.get(WorkflowState, execution.from_state_id) if execution else None
            )
            to_state = (
                await session.get(WorkflowState, execution.to_state_id) if execution else None
            )

            exec_dict = {
                "id": str(execution.id) if execution else execution_id_str,
                "project_key": project.identifier if project else "KAN",
                "from_state": from_state.name if from_state else "Unknown",
                "to_state": to_state.name if to_state else "Done",
                "actor": str(execution.invoking_principal_id) if execution else "@system",
                "allowed_mutable_fields": (
                    hook.allowed_mutable_fields if hook else ("labels", "priority")
                ),
            }
            issue_dict: dict[str, Any] = {
                "key": (
                    f"{project.identifier}-{issue.sequence_id}"
                    if project and issue
                    else str(issue.id if issue else "")
                ),
                "summary": issue.summary if issue else "",
                "description_markdown": issue.description_markdown if issue else "",
            }
            if issue is not None:
                issue_dict["comments"] = await _load_issue_comments(session, issue.id)
            repo_ctx = (
                await _load_repo_context(session, execution.project_id) if execution else None
            )
            base_timeout = resolve_effective_gate_timeout_ms(
                hook_timeout_ms=hook.timeout_ms if hook else None,
                project_default_timeout_ms=project.default_gate_timeout_ms if project else None,
                agent_timeout_ms=agent_def.timeout_ms if agent_def else None,
            )
            agent_dict: dict[str, Any] = {
                "slug": agent_def.slug if agent_def else "agent",
                "harness_kind": agent_def.harness_kind if agent_def else "in_app_sdk",
                "timeout_ms": base_timeout,
                "repo_access_mode": agent_def.repo_access_mode if agent_def else "read-only",
                "cli_binary_allowlist_id": (
                    agent_def.cli_binary_allowlist_id if agent_def else None
                ),
                "model": agent_def.model_id if agent_def else None,
                "model_identifier": agent_def.model_id if agent_def else None,
                "provider_kind": agent_def.provider_kind if agent_def else None,
                "system_instructions_md": (agent_def.system_instructions_md if agent_def else ""),
                "mcp_allowed_tools": (list(agent_def.mcp_allowed_tools or []) if agent_def else []),
            }

            live_provider = None
            if (
                agent_def
                and agent_def.provider_kind
                and agent_def.provider_kind != "fixture"
                and getattr(agent_def, "harness_kind", "in_app_sdk") != "fixture"
            ):
                provider_stmt = (
                    select(AIProviderConfig)
                    .where(
                        AIProviderConfig.workspace_id == ws_id,
                        AIProviderConfig.provider_kind == agent_def.provider_kind,
                        AIProviderConfig.is_enabled.is_(True),
                    )
                    .order_by(AIProviderConfig.priority.asc())
                    .limit(1)
                )
                prov_res = await session.execute(provider_stmt)
                provider_row = prov_res.scalar_one_or_none()

                if isinstance(provider_row, AIProviderConfig):
                    base_url_val = (provider_row.base_url or "").lower()
                    is_dummy_fixture = (
                        "fixture" in base_url_val
                        or getattr(agent_def, "harness_kind", "") == "fixture"
                    )
                    if not is_dummy_fixture:
                        prov_settings = dict(provider_row.settings_json or {})
                        prov_timeout = prov_settings.get("timeout_ms")
                        if prov_timeout is not None and int(prov_timeout) > 0:
                            base_timeout = min(int(prov_timeout), base_timeout)
                        agent_dict["timeout_ms"] = base_timeout
                        cutoff_s = float(base_timeout) / 1000.0

                        api_key_str: str | None = None
                        has_wrapped_key = (
                            provider_row.dek_kid is not None
                            or provider_row.__dict__.get("wrapped_api_key") is not None
                        )
                        if has_wrapped_key:
                            from kanban.ai_config.service import AIProviderConfigService  # noqa: PLC0415

                            cfg_svc = AIProviderConfigService(session)
                            try:
                                key_bytes = await cfg_svc.unwrap_api_key(provider_row.id)
                                api_key_str = key_bytes.decode("utf-8")
                            except Exception as unwrap_err:  # noqa: BLE001
                                logger.warning(
                                    "Could not unwrap API key for provider config %s: %s",
                                    provider_row.id,
                                    unwrap_err,
                                )

                        from pydantic import HttpUrl, SecretStr  # noqa: PLC0415

                        from agent.providers.registry import build_provider  # noqa: PLC0415

                        p_kind = provider_row.provider_kind.lower()
                        model_list = tuple(
                            provider_row.model_allowlist
                            or ([agent_def.model_id] if agent_def.model_id else ["default"])
                        )

                        try:
                            if p_kind == "ollama":
                                from agent.providers.ollama import OllamaSettings  # noqa: PLC0415

                                ollama_settings = OllamaSettings(
                                    base_url=HttpUrl(
                                        provider_row.base_url or "http://127.0.0.1:11434"
                                    ),
                                    model_allowlist=model_list,
                                    read_timeout_s=cutoff_s,
                                    connect_timeout_s=min(2.0, cutoff_s),
                                )
                                live_provider = build_provider("ollama", ollama_settings)
                            elif p_kind == "gemini":
                                from agent.providers.gemini import GeminiSettings  # noqa: PLC0415

                                gemini_base_url = (
                                    HttpUrl(provider_row.base_url)
                                    if provider_row.base_url
                                    else (
                                        HttpUrl("https://generativelanguage.googleapis.com")
                                        if (api_key_str and api_key_str.startswith("AQ."))
                                        else None
                                    )
                                )
                                gemini_mode: Literal[
                                    "vertex", "ai_studio_paid", "vertex_express"
                                ] = (
                                    "vertex_express"
                                    if (
                                        api_key_str
                                        and api_key_str.startswith("AQ.")
                                        and "aiplatform.googleapis.com"
                                        in str(gemini_base_url or "").lower()
                                    )
                                    else "ai_studio_paid"
                                )
                                gemini_settings = GeminiSettings(
                                    mode=gemini_mode,
                                    api_key=SecretStr(api_key_str) if api_key_str else None,
                                    base_url=gemini_base_url,
                                    model_allowlist=model_list,
                                    timeout_s=cutoff_s,
                                )
                                live_provider = build_provider("gemini", gemini_settings)
                            elif p_kind == "openai":
                                from agent.providers.openai_provider import OpenAISettings  # noqa: PLC0415

                                openai_settings = OpenAISettings(
                                    api_key=SecretStr(api_key_str) if api_key_str else None,
                                    base_url=(
                                        HttpUrl(provider_row.base_url)
                                        if provider_row.base_url
                                        else None
                                    ),
                                    model_allowlist=model_list,
                                    timeout_s=cutoff_s,
                                    residency_tier=provider_row.residency_tier or "openai-zdr-us",
                                )
                                live_provider = build_provider("openai", openai_settings)
                        except Exception as prov_err:  # noqa: BLE001
                            logger.warning(
                                "Could not instantiate live provider %s for gate execution: %s",
                                p_kind,
                                prov_err,
                            )
                            live_provider = None

                        if live_provider is not None:
                            from agent.budget import BudgetEnforcer  # noqa: PLC0415
                            from agent.harnesses.in_app_sdk import InAppSdkHarness  # noqa: PLC0415

                            budget_enforcer = BudgetEnforcer(
                                session_factory=self.session_factory,
                                rls_context=admin_ctx,
                            )
                            live_harness = InAppSdkHarness(
                                provider=live_provider,
                                budget_enforcer=budget_enforcer,
                                session_factory=self.session_factory,
                                rls_context=admin_ctx,
                            )
                            self.registry.register("in_app_sdk", live_harness)
                            agent_dict["provider"] = live_provider
                            agent_dict["provider_config_id"] = provider_row.id
                            agent_dict["workspace_id"] = ws_id
                            if execution is not None and execution.project_id is not None:
                                agent_dict["project_id"] = execution.project_id

            return exec_dict, issue_dict, agent_dict, repo_ctx, None

    async def poll_once(self) -> int:  # noqa: C901, PLR0912, PLR0915
        """Poll for pending running gate hook invocations with lease claiming and timeout sweep."""
        if self.session_factory is None:
            return 0

        handled = 0
        now = dt.datetime.now(dt.UTC)

        ws_id, admin_pid = await self._resolve_workspace_and_admin()
        bound_ws = ws_id or uuid.UUID(int=0)
        bound_pid = admin_pid or uuid.UUID(int=0)

        # 1. Short read transaction to claim/resolve invocations with
        # ZERO row locks held across dispatch
        admin_ctx = RLSContext(
            principal_id=bound_pid,
            workspace_id=bound_ws,
            token_scopes=("admin",),
            aal_level=2,
        )

        expired_candidates: list[dict[str, Any]] = []
        active_candidates: list[dict[str, Any]] = []

        async with self.session_factory.session(admin_ctx) as session:
            # Query ONLY valid status 'running' and hook_kind 'agent_interceptor'
            # via FOR UPDATE SKIP LOCKED
            sweep_stmt = (
                select(WorkflowHookInvocation)
                .where(
                    WorkflowHookInvocation.status == "running",
                    WorkflowHookInvocation.hook_kind == "agent_interceptor",
                    or_(
                        WorkflowHookInvocation.claim_expires_at.is_(None),
                        WorkflowHookInvocation.claim_expires_at <= now,
                        WorkflowHookInvocation.claimed_by_worker == self.worker_id,
                    ),
                )
                .order_by(WorkflowHookInvocation.started_at)
                .limit(50)
                .with_for_update(skip_locked=True)
            )
            raw_candidates = list((await session.execute(sweep_stmt)).scalars().all())

            for inv in raw_candidates:
                inv.claimed_by_worker = self.worker_id
                inv.claim_expires_at = now + dt.timedelta(seconds=self.lease_ttl_s)
            if hasattr(session, "flush"):
                await session.flush()

            for inv in raw_candidates:
                agent_pid = None
                agent_def_id = None
                hook = None
                project = None
                agent_def = None
                provider_timeout_ms = None
                if hasattr(session, "get"):
                    try:
                        hook = await session.get(WorkflowTransitionHook, inv.hook_id)
                        if hook:
                            if hook.project_id is not None:
                                project = await session.get(Project, hook.project_id)
                            if hook.agent_definition_id is not None:
                                agent_def_id = hook.agent_definition_id
                                agent_def = await session.get(
                                    AgentDefinition, hook.agent_definition_id
                                )
                                if agent_def:
                                    agent_pid = agent_def.principal_id
                                    if agent_def.provider_kind:
                                        prov_stmt = (
                                            select(AIProviderConfig)
                                            .where(
                                                AIProviderConfig.workspace_id == bound_ws,
                                                AIProviderConfig.provider_kind
                                                == agent_def.provider_kind,
                                                AIProviderConfig.is_enabled.is_(True),
                                            )
                                            .order_by(AIProviderConfig.priority.asc())
                                            .limit(1)
                                        )
                                        prov_res = await session.execute(prov_stmt)
                                        provider_row = prov_res.scalar_one_or_none()
                                        if provider_row and provider_row.settings_json:
                                            prov_settings = dict(provider_row.settings_json or {})
                                            prov_timeout = prov_settings.get("timeout_ms")
                                            if prov_timeout and int(prov_timeout) > 0:
                                                provider_timeout_ms = int(prov_timeout)
                    except (AttributeError, KeyError, TypeError) as exc:
                        logger.debug("Failed resolving hook agent info for sweep: %s", exc)

                timeout_ms = resolve_effective_gate_timeout_ms(
                    hook_timeout_ms=hook.timeout_ms if hook else None,
                    project_default_timeout_ms=project.default_gate_timeout_ms if project else None,
                    agent_timeout_ms=agent_def.timeout_ms if agent_def else None,
                )
                if provider_timeout_ms is not None and provider_timeout_ms > 0:
                    timeout_ms = min(provider_timeout_ms, timeout_ms)

                out_json = getattr(inv, "output_json", None) or {}
                raw_deadline = getattr(inv, "deadline_at", None) or out_json.get("deadline_at")
                if isinstance(raw_deadline, str):
                    try:
                        deadline = dt.datetime.fromisoformat(raw_deadline)
                    except ValueError:
                        deadline = None
                else:
                    deadline = raw_deadline

                if deadline is None and getattr(inv, "started_at", None) is not None:
                    deadline = inv.started_at + dt.timedelta(milliseconds=timeout_ms)

                info = {
                    "invocation_id": inv.id,
                    "execution_id": inv.execution_id,
                    "hook_id": inv.hook_id,
                    "workspace_id": getattr(inv, "workspace_id", bound_ws),
                    "agent_definition_id": agent_def_id,
                    "agent_principal_id": agent_pid,
                    "admin_principal_id": bound_pid,
                    "deadline_at": deadline,
                    "started_at": getattr(inv, "started_at", now),
                    "timeout_ms": timeout_ms,
                }
                if deadline is not None and deadline < now:
                    expired_candidates.append(info)
                elif inv.status == "running":
                    active_candidates.append(info)

        # Notice: The read session above is COMMITTED and CLOSED!
        # ZERO row locks are held on PostgreSQL across dispatch!

        # 2. Process expired invocations (GATE_TIMEOUT)
        for item in expired_candidates:
            inv_id = item["invocation_id"]
            exec_id = item["execution_id"]
            hook_id = item["hook_id"]
            if inv_id in self._active_invocations:
                continue

            self._active_invocations.add(inv_id)
            self._execution_contexts[exec_id] = item
            try:
                await self.record_failure(
                    exec_id,
                    hook_id,
                    "GATE_TIMEOUT",
                    invocation_id=inv_id,
                    detail="Async agent gate exceeded deadline_at",
                )
                handled += 1
            except Exception as exc:  # noqa: BLE001
                logger.debug("Error recording gate timeout failure: %s", exc)
            finally:
                self._active_invocations.discard(inv_id)
                self._execution_contexts.pop(exec_id, None)

        # 3. Dispatch active non-expired invocations with in-memory lease guard
        for item in active_candidates:
            inv_id = item["invocation_id"]
            exec_id = item["execution_id"]
            hook_id = item["hook_id"]
            if inv_id in self._active_invocations:
                continue

            self._active_invocations.add(inv_id)
            self._execution_contexts[exec_id] = item
            event = {
                "execution_id": str(exec_id),
                "hook_id": str(hook_id),
                "agent_definition_id": (
                    str(item["agent_definition_id"]) if item.get("agent_definition_id") else ""
                ),
                "workspace_id": str(item["workspace_id"]),
                "agent_principal_id": (
                    str(item["agent_principal_id"]) if item.get("agent_principal_id") else ""
                ),
                "admin_principal_id": (
                    str(item["admin_principal_id"]) if item.get("admin_principal_id") else ""
                ),
                "timeout_ms": item.get("timeout_ms"),
            }
            heartbeat_task: asyncio.Task[None] | None = None
            try:
                heartbeat_task = asyncio.create_task(
                    self._heartbeat_lease(
                        invocation_id=inv_id,
                        workspace_id=item["workspace_id"],
                        admin_principal_id=item["admin_principal_id"],
                        deadline_at=item.get("deadline_at"),
                    )
                )

                remaining_s: float | None = None
                deadline = item.get("deadline_at")
                if deadline is not None:
                    curr_now = dt.datetime.now(dt.UTC)
                    remaining_s = (deadline - curr_now).total_seconds()

                if remaining_s is not None and remaining_s <= 0.0:
                    msg = "Gate exceeded deadline_at before dispatch"
                    raise TimeoutError(msg)  # noqa: TRY301

                if remaining_s is not None:
                    await asyncio.wait_for(
                        self.worker.handle_dispatch(event),
                        timeout=remaining_s,
                    )
                else:
                    await self.worker.handle_dispatch(event)
                handled += 1
            except TimeoutError:
                logger.info("Invocation %s timed out against deadline_at", inv_id)
                try:
                    await self.record_failure(
                        exec_id,
                        hook_id,
                        "GATE_TIMEOUT",
                        invocation_id=inv_id,
                        detail="Async agent gate exceeded deadline_at",
                    )
                    handled += 1
                except Exception as exc:  # noqa: BLE001
                    logger.debug("Error recording timeout failure: %s", exc)
            except Exception as exc:  # noqa: BLE001
                logger.debug("Error handling gate dispatch: %s", exc)
            finally:
                if heartbeat_task is not None:
                    heartbeat_task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await heartbeat_task
                self._active_invocations.discard(inv_id)
                self._execution_contexts.pop(exec_id, None)

        return handled

    async def _heartbeat_lease(
        self,
        invocation_id: uuid.UUID,
        workspace_id: uuid.UUID,
        admin_principal_id: uuid.UUID,
        deadline_at: dt.datetime | None = None,
    ) -> None:
        """Periodically renew worker claim lease on workflow_hook_invocations."""
        while True:
            await asyncio.sleep(self.heartbeat_interval_s)
            if invocation_id not in self._active_invocations:
                break
            now = dt.datetime.now(dt.UTC)
            if deadline_at is not None and now >= deadline_at:
                logger.debug("Stopping heartbeat for %s: deadline_at exceeded", invocation_id)
                break

            new_expiry = now + dt.timedelta(seconds=self.lease_ttl_s)
            if deadline_at is not None and new_expiry > deadline_at:
                new_expiry = deadline_at

            try:
                if self.session_factory is not None:
                    admin_ctx = RLSContext(
                        principal_id=admin_principal_id,
                        workspace_id=workspace_id,
                        token_scopes=("admin",),
                        aal_level=2,
                    )
                    async with self.session_factory.session(admin_ctx) as session:
                        stmt = text(
                            "UPDATE workflow_hook_invocations "
                            "SET claim_expires_at = :new_expiry "
                            "WHERE id = :inv_id "
                            "  AND status = 'running' "
                            "  AND claimed_by_worker = :worker_id"
                        )
                        await session.execute(
                            stmt,
                            {
                                "new_expiry": new_expiry,
                                "inv_id": invocation_id,
                                "worker_id": self.worker_id,
                            },
                        )
                        if hasattr(session, "commit"):
                            await session.commit()
            except Exception as exc:  # noqa: BLE001
                logger.debug("Lease heartbeat iteration failed for %s: %s", invocation_id, exc)

    async def run(self, stop_event: asyncio.Event) -> None:
        """Run runner poll loop until stop_event is set."""
        while not stop_event.is_set():
            try:
                await self.poll_once()
            except Exception as exc:  # noqa: BLE001
                logger.debug("Gate worker runner poll iteration error: %s", exc)
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop_event.wait(), timeout=self.poll_interval_s)


async def start_gate_worker(
    app: object,
    session_target: RLSSessionFactory | None = None,
    workspace_id: uuid.UUID | None = None,
    admin_principal_id: uuid.UUID | None = None,
) -> tuple[asyncio.Task[None], asyncio.Event]:
    """Start background gate worker task during application lifespan."""
    stop_event = asyncio.Event()
    sf = session_target
    if sf is None and hasattr(app, "state"):
        sf = getattr(app.state, "session_factory", None)
    runner = GateWorkerRunner(
        session_factory=sf,
        workspace_id=workspace_id,
        admin_principal_id=admin_principal_id,
    )
    task = asyncio.create_task(runner.run(stop_event))
    return task, stop_event
