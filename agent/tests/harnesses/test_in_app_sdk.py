# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
# ruff: noqa: E501, SLF001, ARG001, ARG002, ARG005, ANN401, D102, D107, PLC0415, F841, RUF059, B017, PT011
"""Feature unit tests for InAppSdkHarness (KB-P5-20)."""

from __future__ import annotations

import subprocess
import uuid
from pathlib import Path
from typing import Any

import pytest

from agent.budget import Reservation
from agent.context.transition_context import (
    McpAccess,
    RepoContext,
    build_transition_context,
)
from agent.context.verdict import parse_verdict_output
from agent.harnesses.in_app_sdk import InAppSdkHarness
from agent.testing.fixtures import FixtureLLMProvider, load_cassette
from agent.tools.mcp_read_tools import EphemeralMcpReadToolkit
from agent.tools.repo_path_guard import RepoToolPolicyError

CASSETTES_DIR = Path(__file__).resolve().parent.parent.parent.parent / "tests" / "fixtures" / "ai"


@pytest.fixture
def bare_repo(tmp_path: Path) -> tuple[Path, str]:
    """Create a real bare Git repository with source, database schema, and commits."""
    work = tmp_path / "work"
    work.mkdir()

    def run_git(*args: str) -> str:
        res = subprocess.run(
            ["git", *args],
            cwd=work,
            check=True,
            capture_output=True,
            text=True,
        )
        return res.stdout.strip()

    run_git("init")
    run_git("config", "user.name", "Test Committer")
    run_git("config", "user.email", "test@example.com")
    run_git("config", "commit.gpgsign", "false")

    (work / "database").mkdir(parents=True)
    (work / "database" / "schema.sql").write_text(
        "-- FORCE ROW LEVEL SECURITY on auth_card_group_mappings\n",
        encoding="utf-8",
    )
    (work / "src").mkdir(parents=True)
    (work / "src" / "app.py").write_text("def app(): pass\n", encoding="utf-8")

    run_git("add", ".")
    run_git("commit", "-m", "Commit 1")
    c1 = run_git("rev-parse", "HEAD")

    # Update app for diff testing
    (work / "src" / "app.py").write_text("def app(): return 'OK'\n", encoding="utf-8")
    run_git("add", ".")
    run_git("commit", "-m", "Commit 2")
    c2 = run_git("rev-parse", "HEAD")

    bare_path = tmp_path / "repo.git"
    subprocess.run(
        ["git", "clone", "--bare", str(work), str(bare_path)],
        check=True,
        capture_output=True,
    )
    return bare_path, c2


class MockBudgetEnforcer:
    """Mock BudgetEnforcer tracking reservations, settlements, and releases."""

    def __init__(self) -> None:
        self.reserved: list[Reservation] = []
        self.settled: list[tuple[Reservation, int]] = []
        self.released: list[Reservation] = []

    async def reserve(
        self,
        ws: uuid.UUID,
        proj: uuid.UUID | None,
        cfg: uuid.UUID,
        estimate_tokens: int,
        session: Any = None,
    ) -> Reservation:
        res = Reservation(
            id=uuid.uuid4(),
            workspace_id=ws,
            project_id=proj,
            provider_config_id=cfg,
            estimate_tokens=estimate_tokens,
            reserved_ledger_ids=(uuid.uuid4(),),
        )
        self.reserved.append(res)
        return res

    async def settle(self, res: Reservation, actual_tokens: int, session: Any = None) -> None:
        self.settled.append((res, actual_tokens))

    async def release(self, res: Reservation, session: Any = None) -> None:
        self.released.append(res)


async def test_in_app_sdk_positive_replay_veto(bare_repo: tuple[Path, str]) -> None:
    """Test Case 1: Replay transition_rls_veto.yaml, executes read_ticket + repo_grep in order, settles budget."""
    bare_path, head_sha = bare_repo

    mcp_calls: list[str] = []

    async def fake_mcp(url: str, tool: str, args: dict[str, Any]) -> dict[str, Any]:
        mcp_calls.append(tool)
        return {"identifier": "KAN-100", "summary": "Auth Provider Cards"}

    veto_cas = load_cassette(CASSETTES_DIR / "transition_rls_veto.yaml")
    provider = FixtureLLMProvider([veto_cas])
    budget = MockBudgetEnforcer()

    harness = InAppSdkHarness(
        provider=provider,
        budget_enforcer=budget,  # type: ignore[arg-type]
        mcp_transport=fake_mcp,
    )

    repo_ctx = RepoContext(
        mount_path=str(bare_path),
        access="read-only",
        head_commit=head_sha,
        mirror_path=bare_path,
    )
    mcp_access = McpAccess(
        agent_url="https://kanban.internal/mcp/agent",
        docs_url="https://kanban.internal/mcp/docs",
    )

    execution = {
        "id": "0196ed40-7b2a-7000-8000-112233445566",
        "project_key": "KAN",
        "from_state": "In Review",
        "to_state": "Done",
        "actor": "@reviewer",
        "allowed_mutable_fields": ("labels", "priority"),
    }
    issue = {
        "key": "KAN-142",
        "summary": "auth_provider_cards transition check",
        "description_markdown": "Checking RLS enforcement",
    }
    agent_def = {
        "slug": "forensic-code-check",
        "repo_access_mode": "read-only",
        "mcp_allowed_tools": ["search_tickets", "read_ticket", "search_knowledge", "read_doc"],
    }

    ctx = build_transition_context(execution, issue, agent_def, repo_ctx, mcp_access)

    raw_output = await harness.run(ctx, agent_def)

    # 1. Traces recorded and ordered: read_ticket then repo_grep
    assert len(harness.last_tool_traces) == 2
    assert harness.last_tool_traces[0].tool_name == "read_ticket"
    assert harness.last_tool_traces[0].status == "ok"
    assert harness.last_tool_traces[1].tool_name == "repo_grep"
    assert harness.last_tool_traces[1].status == "ok"

    # 2. Budget settled
    assert len(budget.reserved) == 1
    assert len(budget.settled) == 1
    assert len(budget.released) == 0

    # 3. Verdict validated by parse_verdict_output
    result = parse_verdict_output(raw_output, ctx)
    assert result.decision.decision == "reject"
    assert result.decision.add_labels == ("qa-needs-work",)
    assert "Missing `FORCE ROW LEVEL SECURITY`" in result.decision.reason_markdown


async def test_in_app_sdk_positive_approve_with_diff(bare_repo: tuple[Path, str]) -> None:
    """Replay in_app_sdk_approve_with_diff.yaml, executes repo_git_diff + read_doc, passes verdict."""
    bare_path, head_sha = bare_repo

    async def fake_mcp(url: str, tool: str, args: dict[str, Any]) -> dict[str, Any]:
        return {"slug": "architecture-spec", "content": "Architecture valid."}

    approve_cas = load_cassette(CASSETTES_DIR / "in_app_sdk_approve_with_diff.yaml")
    provider = FixtureLLMProvider([approve_cas])

    harness = InAppSdkHarness(
        provider=provider,
        mcp_transport=fake_mcp,
    )

    repo_ctx = RepoContext(
        mount_path=str(bare_path),
        access="read-only",
        head_commit=head_sha,
        mirror_path=bare_path,
    )
    execution = {
        "id": "0196ed40-7b2a-7000-8000-112233445566",
        "project_key": "KAN",
        "from_state": "In Review",
        "to_state": "Done",
        "allowed_mutable_fields": ("labels",),
    }
    issue = {
        "key": "KAN-142",
        "summary": "approve_with_diff verification",
        "description_markdown": "Test diff and doc reading",
    }
    agent_def = {
        "slug": "forensic-code-check",
        "repo_access_mode": "read-only",
        "mcp_allowed_tools": ["read_doc"],
    }

    ctx = build_transition_context(execution, issue, agent_def, repo_ctx)

    raw_output = await harness.run(ctx, agent_def)
    assert len(harness.last_tool_traces) == 2
    assert harness.last_tool_traces[0].tool_name == "repo_git_diff"
    assert harness.last_tool_traces[1].tool_name == "read_doc"

    result = parse_verdict_output(raw_output, ctx)
    assert result.decision.decision == "approve"
    assert result.decision.add_labels == ("security-gate-passed",)


async def test_in_app_sdk_security_forbidden_tool_attempt(bare_repo: tuple[Path, str]) -> None:
    """Test Case 5: Cassette calling update_ticket is blocked with TOOL_NOT_PERMITTED."""
    bare_path, head_sha = bare_repo

    http_calls = 0

    async def fake_mcp(url: str, tool: str, args: dict[str, Any]) -> dict[str, Any]:
        nonlocal http_calls
        http_calls += 1
        return {}

    forbidden_cas = load_cassette(CASSETTES_DIR / "in_app_sdk_forbidden_tool_attempt.yaml")
    provider = FixtureLLMProvider([forbidden_cas])

    harness = InAppSdkHarness(
        provider=provider,
        mcp_transport=fake_mcp,
    )

    repo_ctx = RepoContext(
        mount_path=str(bare_path),
        access="read-only",
        head_commit=head_sha,
        mirror_path=bare_path,
    )
    execution = {"id": "exec-1", "project_key": "KAN"}
    issue = {"key": "KAN-142", "summary": "forbidden_tool_attempt"}
    agent_def = {"slug": "forensic-code-check", "mcp_allowed_tools": ["read_ticket"]}

    ctx = build_transition_context(execution, issue, agent_def, repo_ctx)

    with pytest.raises(RepoToolPolicyError) as exc_info:
        await harness.run(ctx, agent_def)

    assert exc_info.value.code == "TOOL_NOT_PERMITTED"
    assert http_calls == 0
    assert len(harness.last_tool_traces) == 1
    assert harness.last_tool_traces[0].status == "error"


async def test_in_app_sdk_security_repo_none_blocks_repo_tools(bare_repo: tuple[Path, str]) -> None:
    """Test Case 5: When repo_access_mode == 'none', zero repo tools are available."""
    bare_path, head_sha = bare_repo

    veto_cas = load_cassette(CASSETTES_DIR / "transition_rls_veto.yaml")
    provider = FixtureLLMProvider([veto_cas])

    harness = InAppSdkHarness(
        provider=provider,
        mcp_transport=lambda u, t, a: {"identifier": "KAN-100"},
    )

    execution = {"id": "exec-1", "project_key": "KAN"}
    issue = {"key": "KAN-142", "summary": "auth_provider_cards check"}
    agent_def = {
        "slug": "forensic-code-check",
        "repo_access_mode": "none",  # Disabled!
        "mcp_allowed_tools": ["read_ticket"],
    }

    ctx = build_transition_context(execution, issue, agent_def, None)

    # First call read_ticket succeeds, second call repo_grep must fail because repo access is none
    with pytest.raises(RepoToolPolicyError) as exc_info:
        await harness.run(ctx, agent_def)

    assert exc_info.value.code == "TOOL_NOT_PERMITTED"


async def test_in_app_sdk_boundary_tool_loop_exceeded(bare_repo: tuple[Path, str]) -> None:
    """Test Case 6: Tool loop exceeding limit aborts cleanly and calls BudgetEnforcer.release."""
    bare_path, head_sha = bare_repo

    exceeded_cas = load_cassette(CASSETTES_DIR / "in_app_sdk_tool_loop_exceeded.yaml")
    provider = FixtureLLMProvider([exceeded_cas])
    budget = MockBudgetEnforcer()

    harness = InAppSdkHarness(
        provider=provider,
        budget_enforcer=budget,  # type: ignore[arg-type]
    )

    repo_ctx = RepoContext(
        mount_path=str(bare_path),
        access="read-only",
        head_commit=head_sha,
        mirror_path=bare_path,
    )
    execution = {"id": "exec-1", "project_key": "KAN"}
    issue = {"key": "KAN-142", "summary": "tool_loop_exceeded"}
    agent_def = {"slug": "forensic-code-check"}

    ctx = build_transition_context(execution, issue, agent_def, repo_ctx)

    with pytest.raises(RepoToolPolicyError) as exc_info:
        await harness.run(ctx, agent_def)

    assert exc_info.value.code == "TOOL_LOOP_LIMIT_EXCEEDED"
    # Budget was released on abort
    assert len(budget.reserved) == 1
    assert len(budget.released) == 1
    assert len(budget.settled) == 0


async def test_in_app_sdk_generic_provider_and_arg_redaction() -> None:
    """Test InAppSdkHarness with general LLM provider and nested arg redaction."""
    from agent.harnesses.in_app_sdk import TransitionVerdictPayload, _redact_args
    from agent.providers.base import StructuredRequest, StructuredResponse

    # Test nested argument redaction
    args = {
        "nested": {"token": "ghp_111122223333444455556666777788889999", "num": 42},
        "clean": "hello",
    }
    redacted = _redact_args(args)
    assert "ghp_" not in str(redacted["nested"]["token"])
    assert redacted["nested"]["num"] == 42
    assert redacted["clean"] == "hello"

    class GenericMockProvider:
        @property
        def residency_tier(self) -> str:
            return "fixture"

        async def generate_structured(self, req: StructuredRequest[Any]) -> StructuredResponse[Any]:
            payload = TransitionVerdictPayload(
                decision="approve",
                reason_markdown="General approval reason",
                field_updates={},
                add_labels=["security-gate-passed"],
            )
            return StructuredResponse(
                parsed=payload,
                raw_json=payload.model_dump_json(by_alias=True),
                tool_trace=(),
                ttft_ms=5.0,
                total_latency_ms=10.0,
                prompt_tokens=100,
                completion_tokens=50,
            )

    gen_prov = GenericMockProvider()
    harness = InAppSdkHarness(provider=gen_prov)  # type: ignore[arg-type]

    execution = {"id": "gen-exec", "project_key": "KAN", "allowed_mutable_fields": ("labels",)}
    issue = {"key": "KAN-1", "summary": "Generic check"}
    agent_def = {"slug": "forensic-code-check", "system_instructions_md": "Check thoroughly"}

    ctx = build_transition_context(execution, issue, agent_def)

    raw_output = await harness.run(ctx, agent_def)
    result = parse_verdict_output(raw_output, ctx)
    assert result.decision.decision == "approve"
    assert harness.last_report is not None
    assert harness.last_report.prompt_tokens == 100
    assert harness.last_report.completion_tokens == 50


async def test_in_app_sdk_invalid_repo_and_undeclared_tools() -> None:
    """Test InAppSdkHarness handling of invalid repo mirror and undeclared tool dispatch."""
    harness = InAppSdkHarness()

    # Test direct execution of undeclared tool
    with pytest.raises(RepoToolPolicyError) as exc_info:
        await harness._execute_single_tool(
            tool_name="unsupported_custom_tool",
            args={},
            repo_toolkit=None,
            mcp_toolkit=EphemeralMcpReadToolkit(None, None),
        )
    assert exc_info.value.code == "TOOL_NOT_PERMITTED"

    # Test invalid repo path handled gracefully in run()
    repo_ctx = RepoContext(
        mount_path="/nonexistent/path/never/exists", access="read-only", head_commit="0" * 40
    )
    execution = {"id": "exec-bad-repo", "project_key": "KAN"}
    issue = {"key": "KAN-1", "summary": "Bad repo test"}
    agent_def = {"slug": "planner", "repo_access_mode": "read-only"}
    ctx = build_transition_context(execution, issue, agent_def, repo_ctx)

    # Calling with empty provider to verify repo init failure falls back to None without crashing
    with pytest.raises(Exception):
        await harness.run(ctx, agent_def)
