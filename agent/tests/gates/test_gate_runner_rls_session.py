# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Real-PG tests for GateWorkerRunner RLS session lifecycle and budget (KAN-430)."""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import uuid
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import ValidationError
from sqlalchemy import text

from agent.budget import BudgetEnforcer, get_current_period_dates
from agent.context.transition_context import RenderedContext
from agent.gates.runner import GateWorkerRunner
from agent.harnesses.in_app_sdk import InAppSdkHarness, StrictVerdictSchema
from agent.providers.base import (
    CompletionRequest,
    EmbedBatchRequest,
    HealthStatus,
    LLMProvider,
    StreamChunk,
    StructuredRequest,
    StructuredResponse,
    TModel,
)
from agent.tools.repo_path_guard import RepoToolPolicyError
from database.session import RLSSessionFactory

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession


class EphemeralOllamaServer:
    """Ephemeral in-process HTTP server simulating Ollama /api/chat endpoint."""

    def __init__(
        self,
        *,
        decision: str = "approve",
        reason: str = "Forensic proof verified cleanly.",
        prompt_tokens: int = 42,
        completion_tokens: int = 18,
        fail_with_500: bool = False,
    ) -> None:
        """Initialize mock server with configured decision verdict and token counters."""
        self.decision = decision
        self.reason = reason
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens
        self.fail_with_500 = fail_with_500
        self.server: asyncio.Server | None = None
        self.port: int = 0
        self.request_count = 0
        self.received_payloads: list[dict[str, Any]] = []

    async def _handle_client(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        self.request_count += 1
        await reader.readline()
        headers: dict[str, str] = {}
        while True:
            line = await reader.readline()
            if not line or line in (b"\r\n", b"\n"):
                break
            line_str = line.decode("utf-8", errors="replace").strip()
            if ":" in line_str:
                k, v = line_str.split(":", 1)
                headers[k.strip().lower()] = v.strip()

        content_len = int(headers.get("content-length", "0"))
        body_bytes = await reader.readexactly(content_len) if content_len > 0 else b""
        if body_bytes:
            with contextlib.suppress(Exception):
                self.received_payloads.append(json.loads(body_bytes.decode("utf-8")))

        if self.fail_with_500:
            resp = (
                b"HTTP/1.1 500 Internal Server Error\r\n"
                b"Content-Length: 0\r\nConnection: close\r\n\r\n"
            )
            writer.write(resp)
            await writer.drain()
            writer.close()
            await writer.wait_closed()
            return

        verdict_content = json.dumps({
            "decision": self.decision,
            "reason_markdown": self.reason,
            "add_labels": ["qa-approved"] if self.decision == "approve" else ["qa-rejected"],
            "cited_files": ["tests/test_gate.py"],
        })
        payload_data = {
            "model": "nemotron-3-super:latest",
            "message": {
                "role": "assistant",
                "content": verdict_content,
            },
            "prompt_eval_count": self.prompt_tokens,
            "eval_count": self.completion_tokens,
        }
        body = json.dumps(payload_data).encode("utf-8")
        resp = (
            b"HTTP/1.1 200 OK\r\n"
            b"Content-Type: application/json\r\n"
            b"Content-Length: " + str(len(body)).encode("ascii") + b"\r\n"
            b"Connection: close\r\n\r\n" + body
        )
        writer.write(resp)
        await writer.drain()
        writer.close()
        await writer.wait_closed()

    async def start(self) -> int:
        """Start listening on an ephemeral loopback port."""
        self.server = await asyncio.start_server(self._handle_client, "127.0.0.1", 0)
        self.port = self.server.sockets[0].getsockname()[1]
        return self.port

    async def stop(self) -> None:
        """Close server and wait for all active connections to terminate."""
        if self.server is not None:
            self.server.close()
            await self.server.wait_closed()


async def setup_gate_environment(
    pg_worker_db: AsyncEngine,
    mock_port: int,
    *,
    timeout_ms: int = 120000,
    incomplete_ticket: bool = False,
) -> dict[str, Any]:
    """Seed real PostgreSQL tables with an RLS-enforced workflow gate test harness."""
    ws_id = uuid.uuid4()
    admin_id = uuid.uuid4()
    proj_id = uuid.uuid4()
    cfg_id = uuid.uuid4()
    ledger_id = uuid.uuid4()
    hook_id = uuid.uuid4()
    agent_def_id = uuid.uuid4()
    issue_id = uuid.uuid4()
    exec_id = uuid.uuid4()
    inv_id = uuid.uuid4()
    d_start, _ = get_current_period_dates()
    manifest_sha = hashlib.sha256(b"manifest_test").digest()

    async with pg_worker_db.begin() as conn:
        # 1. Workspace
        await conn.execute(
            text(
                "INSERT INTO workspaces (id, slug, name) "
                "VALUES (:id, :slug, 'Gate Test Workspace')"
            ),
            {"id": ws_id, "slug": f"ws-{ws_id.hex[:12]}"},
        )
        # 2. Admin User
        await conn.execute(
            text(
                "SELECT register_object("
                "'user'::object_kind, :ws_id, NULL, :ckey, 'Admin User', :admin_id, :admin_id"
                ")"
            ),
            {"ws_id": ws_id, "ckey": f"admin-{admin_id.hex[:6]}", "admin_id": admin_id},
        )
        await conn.execute(
            text(
                "INSERT INTO principals (id, workspace_id, principal_type, display_name) "
                "VALUES (:id, :ws_id, 'USER', 'Admin User')"
            ),
            {"id": admin_id, "ws_id": ws_id},
        )
        await conn.execute(
            text(
                "INSERT INTO users (id, workspace_id, email) "
                "VALUES (:id, :ws_id, 'admin@example.com')"
            ),
            {"id": admin_id, "ws_id": ws_id},
        )
        # 3. Project
        await conn.execute(
            text(
                "SELECT register_object("
                "'project'::object_kind, :ws_id, NULL, 'PRJ', 'Test Project', :admin_id, :proj_id"
                ")"
            ),
            {"ws_id": ws_id, "admin_id": admin_id, "proj_id": proj_id},
        )
        await conn.execute(
            text(
                "INSERT INTO projects (id, workspace_id, identifier, name) "
                "VALUES (:id, :ws, 'PRJ', 'Test Project')"
            ),
            {"id": proj_id, "ws": ws_id},
        )
        await conn.execute(
            text(
                "INSERT INTO role_bindings "
                "(principal_id, workspace_id, role, scope_type, project_id) "
                "VALUES (:p_id, :ws_id, 'PROJECT_ADMIN', 'project', :proj_id)"
            ),
            {"ws_id": ws_id, "p_id": admin_id, "proj_id": proj_id},
        )
        await conn.execute(
            text(
                "INSERT INTO role_bindings "
                "(principal_id, workspace_id, role, scope_type, project_id) "
                "VALUES (:p_id, :ws_id, 'WORKSPACE_ADMIN', 'workspace', NULL)"
            ),
            {"ws_id": ws_id, "p_id": admin_id},
        )
        # 4. Fetch states
        res_states = await conn.execute(
            text("SELECT id, name FROM workflow_states WHERE project_id = :p_id"),
            {"p_id": proj_id},
        )
        states = {r.name: r.id for r in res_states.all()}
        in_prog_id = states["In Progress"]
        done_id = states["Done"]

        # 5. Fetch priority
        prio_res = await conn.execute(
            text(
                "SELECT id FROM project_priorities "
                "WHERE project_id = :p_id AND slug = 'medium' LIMIT 1"
            ),
            {"p_id": proj_id},
        )
        prio_id = prio_res.scalar_one()

        # 6. Issue
        seq = await conn.scalar(text("SELECT allocate_issue_sequence(:proj)"), {"proj": proj_id})
        issue_ckey = f"PRJ-{seq}"
        desc = (
            "## Definition of Done\n- [ ] Incomplete task\n"
            if incomplete_ticket
            else "## Definition of Done\n- [x] DoD pass\n## Verification Proof\nproof.png"
        )
        body_snap = hashlib.sha256(desc.encode("utf-8")).digest()
        summary = (
            "Incomplete ticket without proof"
            if incomplete_ticket
            else "Complete verified feature"
        )
        await conn.execute(
            text(
                "SELECT register_object("
                "'issue'::object_kind, :ws, :proj, :ckey, :summary, :uid, :id"
                ")"
            ),
            {
                "ws": ws_id,
                "proj": proj_id,
                "ckey": issue_ckey,
                "summary": summary,
                "uid": admin_id,
                "id": issue_id,
            },
        )
        await conn.execute(
            text(
                "INSERT INTO issues ("
                "  id, workspace_id, project_id, sequence_id, summary, "
                "  description_markdown, state_id, priority_id, created_by_id, "
                "  original_created_by_id, board_rank"
                ") VALUES ("
                "  :id, :ws_id, :proj_id, :seq, :summary, "
                "  :desc, :state_id, :prio_id, :cb_id, :cb_id, '0|i00000:'"
                ")"
            ),
            {
                "id": issue_id,
                "ws_id": ws_id,
                "proj_id": proj_id,
                "seq": seq,
                "summary": summary,
                "desc": desc,
                "state_id": in_prog_id,
                "prio_id": prio_id,
                "cb_id": admin_id,
            },
        )

        # 7. AI Provider Config (Ollama)
        await conn.execute(
            text(
                "INSERT INTO ai_provider_configs ("
                "  id, workspace_id, provider_kind, display_name, residency_tier, "
                "  model_allowlist, base_url, is_enabled, settings_json, priority"
                ") VALUES ("
                "  :id, :ws_id, 'ollama', 'Local Ollama Nemotron', 'default', "
                "  ARRAY['nemotron-3-super:latest'], :base_url, TRUE, "
                "  CAST(:settings_json AS jsonb), 1"
                ")"
            ),
            {
                "id": cfg_id,
                "ws_id": ws_id,
                "base_url": f"http://127.0.0.1:{mock_port}",
                "settings_json": json.dumps({"timeout_ms": timeout_ms}),
            },
        )

        # 8. Token Ledger
        await conn.execute(
            text(
                "INSERT INTO ai_token_ledgers ("
                "  id, workspace_id, project_id, provider_config_id, period_kind, "
                "  period_start, token_cap, tokens_reserved, tokens_used"
                ") VALUES ("
                "  :id, :ws_id, :proj_id, :cfg_id, 'daily', "
                "  :d_start, 500000, 0, 0"
                ")"
            ),
            {
                "id": ledger_id,
                "ws_id": ws_id,
                "proj_id": proj_id,
                "cfg_id": cfg_id,
                "d_start": d_start,
            },
        )

        # 9. Agent Definition
        await conn.execute(
            text(
                "INSERT INTO agent_definitions ("
                "  id, workspace_id, project_id, principal_id, slug, display_name, "
                "  harness_kind, provider_kind, model_id, timeout_ms, system_instructions_md"
                ") VALUES ("
                "  :id, :ws_id, :proj_id, :p_id, 'reality-checker', 'Reality Checker Agent', "
                "  'in_app_sdk', 'ollama', 'nemotron-3-super:latest', :timeout_ms, "
                "  'Audit ticket definition of done and evidence.'"
                ")"
            ),
            {
                "id": agent_def_id,
                "ws_id": ws_id,
                "proj_id": proj_id,
                "p_id": admin_id,
                "timeout_ms": timeout_ms,
            },
        )

        # 10. Workflow Transition Hook
        await conn.execute(
            text(
                "INSERT INTO workflow_transition_hooks ("
                "  id, workspace_id, project_id, name, from_state_id, to_state_id, "
                "  hook_kind, sort_rank, is_enabled, agent_definition_id, "
                "  failure_policy, manifest_sha256"
                ") VALUES ("
                "  :id, :ws_id, :proj_id, 'rc_gate', :from_st, :to_st, "
                "  'agent_interceptor', '0|i00001:', TRUE, :agent_def_id, "
                "  'fail_closed', :manifest_sha"
                ")"
            ),
            {
                "id": hook_id,
                "ws_id": ws_id,
                "proj_id": proj_id,
                "from_st": in_prog_id,
                "to_st": done_id,
                "agent_def_id": agent_def_id,
                "manifest_sha": manifest_sha,
            },
        )

        # 11. Workflow Transition Execution
        await conn.execute(
            text(
                "INSERT INTO workflow_transition_executions ("
                "  id, workspace_id, project_id, issue_id, invoking_principal_id, "
                "  from_state_id, to_state_id, status, hop_depth, issue_body_sha256_snapshot"
                ") VALUES ("
                "  :id, :ws_id, :proj_id, :issue_id, :p_id, "
                "  :from_st, :to_st, 'pending_async', 0, :snap"
                ")"
            ),
            {
                "id": exec_id,
                "ws_id": ws_id,
                "proj_id": proj_id,
                "issue_id": issue_id,
                "p_id": admin_id,
                "from_st": in_prog_id,
                "to_st": done_id,
                "snap": body_snap,
            },
        )

        # 12. Hook Invocation
        await conn.execute(
            text(
                "INSERT INTO workflow_hook_invocations ("
                "  id, workspace_id, execution_id, hook_id, hook_kind, "
                "  status, started_at"
                ") VALUES ("
                "  :id, :ws_id, :exec_id, :hook_id, 'agent_interceptor', "
                "  'running', NOW()"
                ")"
            ),
            {
                "id": inv_id,
                "ws_id": ws_id,
                "exec_id": exec_id,
                "hook_id": hook_id,
            },
        )

        # 13. Link issue pending execution
        await conn.execute(
            text("UPDATE issues SET pending_transition_exec_id = :exec_id WHERE id = :issue_id"),
            {"exec_id": exec_id, "issue_id": issue_id},
        )

    return {
        "workspace_id": ws_id,
        "admin_principal_id": admin_id,
        "project_id": proj_id,
        "provider_config_id": cfg_id,
        "ledger_id": ledger_id,
        "hook_id": hook_id,
        "agent_def_id": agent_def_id,
        "issue_id": issue_id,
        "execution_id": exec_id,
        "invocation_id": inv_id,
    }


@pytest.mark.enable_socket
@pytest.mark.asyncio
async def test_positive_e2e_real_pg_and_mock_ollama_gate_approval(
    pg_worker_db: AsyncEngine,
) -> None:
    """Positive E2E: GateWorkerRunner._load_entities -> handle_dispatch against real PG and Ollama.

    Verifies:
      - Ollama nemotron-3-super:latest with timeout_ms=120000.
      - BudgetEnforcer.reserve() and settle() execute in independent RLS transactions.
      - ZERO unbound RLS session errors.
      - Gate approval recorded cleanly.
    """
    mock_server = EphemeralOllamaServer(
        decision="approve",
        reason="Forensic proof verified cleanly. All DoD criteria satisfied.",
        prompt_tokens=50,
        completion_tokens=25,
    )
    port = await mock_server.start()
    try:
        env = await setup_gate_environment(pg_worker_db, port, timeout_ms=120000)
        session_factory = RLSSessionFactory(pg_worker_db)
        runner = GateWorkerRunner(
            session_factory=session_factory,
            workspace_id=env["workspace_id"],
            admin_principal_id=env["admin_principal_id"],
        )

        event = {
            "execution_id": str(env["execution_id"]),
            "hook_id": str(env["hook_id"]),
            "agent_definition_id": str(env["agent_def_id"]),
            "workspace_id": str(env["workspace_id"]),
            "admin_principal_id": str(env["admin_principal_id"]),
        }

        # Dispatch execution
        await runner.worker.handle_dispatch(event)

        assert mock_server.request_count == 1
        assert len(mock_server.received_payloads) == 1
        payload = mock_server.received_payloads[0]
        assert payload["model"] == "nemotron-3-super:latest"

        # Verify budget ledger state in real PostgreSQL:
        # tokens_reserved MUST be 0 (no lingering reservations).
        # tokens_used MUST be 75 (50 prompt + 25 completion tokens settled).
        async with pg_worker_db.connect() as conn:
            ledger_row = (
                await conn.execute(
                    text(
                        "SELECT tokens_reserved, tokens_used "
                        "FROM ai_token_ledgers WHERE id = :id"
                    ),
                    {"id": env["ledger_id"]},
                )
            ).mappings().one()

            assert ledger_row["tokens_reserved"] == 0
            assert ledger_row["tokens_used"] == 75

            # Verify decision record
            inv_row = (
                await conn.execute(
                    text(
                        "SELECT status, error_code FROM workflow_hook_invocations WHERE id = :id"
                    ),
                    {"id": env["invocation_id"]},
                )
            ).mappings().one()
            assert inv_row["status"] == "allowed"
            assert inv_row["error_code"] is None

            exec_row = (
                await conn.execute(
                    text("SELECT status FROM workflow_transition_executions WHERE id = :id"),
                    {"id": env["execution_id"]},
                )
            ).mappings().one()
            assert exec_row["status"] == "approved"
    finally:
        await mock_server.stop()


@pytest.mark.enable_socket
@pytest.mark.asyncio
async def test_negative_gate_rejection_on_incomplete_ticket(
    pg_worker_db: AsyncEngine,
) -> None:
    """Negative E2E: Incomplete ticket generates a reject decision without leaking tokens."""
    mock_server = EphemeralOllamaServer(
        decision="reject",
        reason="Unchecked Definition of Done items and missing verification proof.",
        prompt_tokens=40,
        completion_tokens=20,
    )
    port = await mock_server.start()
    try:
        env = await setup_gate_environment(
            pg_worker_db, port, timeout_ms=120000, incomplete_ticket=True
        )
        session_factory = RLSSessionFactory(pg_worker_db)
        runner = GateWorkerRunner(
            session_factory=session_factory,
            workspace_id=env["workspace_id"],
            admin_principal_id=env["admin_principal_id"],
        )

        event = {
            "execution_id": str(env["execution_id"]),
            "hook_id": str(env["hook_id"]),
            "agent_definition_id": str(env["agent_def_id"]),
            "workspace_id": str(env["workspace_id"]),
            "admin_principal_id": str(env["admin_principal_id"]),
        }

        await runner.worker.handle_dispatch(event)

        assert mock_server.request_count == 1

        async with pg_worker_db.connect() as conn:
            ledger_row = (
                await conn.execute(
                    text(
                        "SELECT tokens_reserved, tokens_used "
                        "FROM ai_token_ledgers WHERE id = :id"
                    ),
                    {"id": env["ledger_id"]},
                )
            ).mappings().one()

            assert ledger_row["tokens_reserved"] == 0
            assert ledger_row["tokens_used"] == 60

            inv_row = (
                await conn.execute(
                    text(
                        "SELECT status, error_code FROM workflow_hook_invocations WHERE id = :id"
                    ),
                    {"id": env["invocation_id"]},
                )
            ).mappings().one()
            assert inv_row["status"] == "rejected"
            assert inv_row["error_code"] is None

            exec_row = (
                await conn.execute(
                    text("SELECT status FROM workflow_transition_executions WHERE id = :id"),
                    {"id": env["execution_id"]},
                )
            ).mappings().one()
            assert exec_row["status"] == "rejected"
    finally:
        await mock_server.stop()


@pytest.mark.enable_socket
@pytest.mark.asyncio
async def test_negative_inference_failure_rollback(
    pg_worker_db: AsyncEngine,
) -> None:
    """Negative Failure: When LLM inference fails, BudgetEnforcer.release() restores tokens to 0."""
    mock_server = EphemeralOllamaServer(fail_with_500=True)
    port = await mock_server.start()
    try:
        env = await setup_gate_environment(pg_worker_db, port, timeout_ms=120000)
        session_factory = RLSSessionFactory(pg_worker_db)
        runner = GateWorkerRunner(
            session_factory=session_factory,
            workspace_id=env["workspace_id"],
            admin_principal_id=env["admin_principal_id"],
        )

        event = {
            "execution_id": str(env["execution_id"]),
            "hook_id": str(env["hook_id"]),
            "agent_definition_id": str(env["agent_def_id"]),
            "workspace_id": str(env["workspace_id"]),
            "admin_principal_id": str(env["admin_principal_id"]),
        }

        await runner.worker.handle_dispatch(event)

        assert mock_server.request_count == 1

        async with pg_worker_db.connect() as conn:
            ledger_row = (
                await conn.execute(
                    text(
                        "SELECT tokens_reserved, tokens_used "
                        "FROM ai_token_ledgers WHERE id = :id"
                    ),
                    {"id": env["ledger_id"]},
                )
            ).mappings().one()

            # Zero leaked tokens: tokens_reserved MUST be restored to 0!
            assert ledger_row["tokens_reserved"] == 0
            assert ledger_row["tokens_used"] == 0

            inv_row = (
                await conn.execute(
                    text(
                        "SELECT status, error_code FROM workflow_hook_invocations WHERE id = :id"
                    ),
                    {"id": env["invocation_id"]},
                )
            ).mappings().one()
            assert inv_row["status"] in ("failed", "rejected")
            assert inv_row["error_code"] is not None
            assert "HARNESS_ERROR:" in inv_row["error_code"]
    finally:
        await mock_server.stop()


def test_structured_request_deadline_boundary_cases() -> None:
    """Boundary Case: StructuredRequest validates deadlines up to 300000ms."""
    req_120k = StructuredRequest(
        model="nemotron-3-super:latest",
        prompt="Audit gate",
        response_model=StrictVerdictSchema,
        ttft_deadline_ms=120000,
    )
    assert req_120k.ttft_deadline_ms == 120000

    req_300k = StructuredRequest(
        model="nemotron-3-super:latest",
        prompt="Audit gate",
        response_model=StrictVerdictSchema,
        ttft_deadline_ms=300000,
    )
    assert req_300k.ttft_deadline_ms == 300000

    with pytest.raises(ValidationError):
        StructuredRequest(
            model="nemotron-3-super:latest",
            prompt="Audit gate",
            response_model=StrictVerdictSchema,
            ttft_deadline_ms=300001,
        )

    with pytest.raises(ValidationError):
        StructuredRequest(
            model="nemotron-3-super:latest",
            prompt="Audit gate",
            response_model=StrictVerdictSchema,
            ttft_deadline_ms=0,
        )


@pytest.mark.asyncio
async def test_budget_enforcer_resolve_and_scoped_session_coverage() -> None:
    """Test resolution fallbacks and errors in BudgetEnforcer._scoped_session."""
    enforcer = BudgetEnforcer()
    dummy_session: AsyncSession = AsyncMock()

    # Direct resolution
    assert enforcer._resolve_session(dummy_session) is dummy_session  # noqa: SLF001
    enforcer_bound = BudgetEnforcer(session=dummy_session)
    assert enforcer_bound._resolve_session(None) is dummy_session  # noqa: SLF001
    with pytest.raises(ValueError, match="requires an active AsyncSession"):
        enforcer._resolve_session(None)  # noqa: SLF001

    # Scoped session with session_factory but no rls_context
    class MockFactory:
        def __init__(self) -> None:
            self.contexts: list[object] = []

        @contextlib.asynccontextmanager
        async def session(self, ctx: object) -> AsyncIterator[AsyncSession]:
            self.contexts.append(ctx)
            mock_s: AsyncSession = AsyncMock()
            mock_s.execute = AsyncMock(  # type: ignore[method-assign]
                return_value=MagicMock(
                    mappings=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
                )
            )
            yield mock_s

    mf = MockFactory()
    enf_factory = BudgetEnforcer(session_factory=mf)
    res = await enf_factory.reserve(
        workspace_id=uuid.uuid4(),
        project_id=None,
        provider_config_id=uuid.uuid4(),
        estimate_tokens=10,
    )
    assert res.reserved_ledger_ids == ()
    assert len(mf.contexts) == 1
    assert getattr(mf.contexts[0], "principal_id", None) == uuid.UUID(int=0)

    # Non-callable session factory method raises ValueError
    enf_bad = BudgetEnforcer(session_factory=object())
    with pytest.raises(ValueError, match="requires an active AsyncSession"):
        await enf_bad.reserve(
            workspace_id=uuid.uuid4(),
            project_id=None,
            provider_config_id=uuid.uuid4(),
            estimate_tokens=10,
        )


@pytest.mark.asyncio
async def test_in_app_sdk_harness_coverage_branches() -> None:
    """Test session_factory attachment, uncallable tools, and verdict field defaulting."""
    # 1. Attachment of session_factory and rls_context to budget_enforcer
    enf = BudgetEnforcer()
    mock_fac = object()
    mock_ctx = object()
    InAppSdkHarness(
        budget_enforcer=enf,
        session_factory=mock_fac,
        rls_context=mock_ctx,
    )
    assert enf.session_factory is mock_fac
    assert enf.rls_context is mock_ctx

    # 2. Uncallable tool method in repo_toolkit
    class UncallableRepoToolkit:
        repo_tree = "not_callable_attribute"

    harness = InAppSdkHarness()
    with pytest.raises(RepoToolPolicyError, match="not available"):
        await harness._execute_single_tool(  # noqa: SLF001
            "repo_tree", {}, UncallableRepoToolkit(), None  # type: ignore[arg-type]
        )

    # 3. Final verdict add_labels and cited_files defaulting from parsed output
    class MockCustomProvider(LLMProvider):
        @property
        def residency_tier(self) -> str:
            return "fixture"

        def stream_complete(
            self, req: CompletionRequest
        ) -> AsyncIterator[StreamChunk]:
            del req
            raise NotImplementedError

        async def generate_structured(
            self, req: StructuredRequest[TModel]
        ) -> StructuredResponse[TModel]:
            del req
            parsed = StrictVerdictSchema(
                decision="approve",
                reason_markdown="Looks good",
                add_labels=["verified-1"],
                cited_files=["file1.py"],
            )
            return StructuredResponse(
                parsed=parsed,  # type: ignore[arg-type]
                raw_json=json.dumps({"decision": "approve", "reason_markdown": "Looks good"}),
                prompt_tokens=10,
                completion_tokens=5,
                ttft_ms=10.0,
                total_latency_ms=15.0,
            )

        async def embed_batch(
            self, req: EmbedBatchRequest
        ) -> list[list[float]]:
            del req
            raise NotImplementedError

        async def health_probe(self) -> HealthStatus:
            raise NotImplementedError

    custom_prov = MockCustomProvider()
    harness_custom = InAppSdkHarness(provider=custom_prov)
    rendered_ctx = RenderedContext(
        yaml_bytes=b"issue: {key: KAN-1}",
        sha256=hashlib.sha256(b"issue: {key: KAN-1}").hexdigest(),
        delimiter="---",
        verdict_nonce="test-nonce-12345",
        ephemeral_token=bytearray(b"dummy-token"),
        allowed_mutable_fields=frozenset({"labels", "priority"}),
    )
    raw_verdict = await harness_custom.run(rendered_ctx, agent_def={"slug": "test-agent"})
    parsed_verdict = json.loads(raw_verdict.decode("utf-8"))
    assert parsed_verdict["decision"] == "approve"
    assert parsed_verdict["add_labels"] == ["verified-1"]
    assert parsed_verdict["cited_files"] == ["file1.py"]
    assert parsed_verdict["nonce"] == "test-nonce-12345"
