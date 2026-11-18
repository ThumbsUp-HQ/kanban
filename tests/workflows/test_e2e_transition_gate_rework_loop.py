# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
# ruff: noqa: E501, PLR0915, ASYNC221, D107, TC003
"""E2E Transition Gate Reject -> Rework -> Accept Loop (KB-QA-RECONCILE, KANBA-206).

Exercises a full real-world ticket lifecycle transition through an agent-gated state
against a temporary Git repository snapshot:
1. Transition 1: Enters pending_agent (⏳🤖), verifier evaluates initial commit SHA,
   finds defect in cited files, records verdict="REJECT" with cited_files,
   rolls back to source state (🛑🤖), and posts rejection rationale comment.
2. Rework: Developer commits fix to the repository and transitions ticket a second time.
3. Transition 2: Verifier inspects updated commit SHA via RoRepoSnapshotManager,
   records verdict="APPROVE", advances ticket to target state (✅🤖),
   and records immutable audit ledger provenance.
"""

from __future__ import annotations

import json
import subprocess
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
from sqlalchemy import select

from agent.context.transition_context import RenderedContext, RepoContext
from agent.gates.worker import GateWorker, Harness, HarnessRegistry
from agent.runners.repo_snapshot import RoRepoSnapshotManager
from database.models.activity import ActivityRecord
from database.models.agent_definition import AgentDefinition
from database.models.issues import Issue, IssueComment
from database.models.outbox import OutboxEvent
from database.models.principals import Principal
from database.models.projects import WorkflowState
from database.models.workflow import (
    WorkflowHookInvocation,
    WorkflowTransitionExecution,
    WorkflowTransitionHook,
)
from kanban.workflows.async_gate import GateCoordinator
from kanban.workflows.manifest import compute_hook_manifest_sha256

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    import httpx
    from sqlalchemy.ext.asyncio import AsyncSession

    from kanban.tests.api.conftest import ApiEnv, SeededUser

pytestmark = pytest.mark.committed_db


class RepoVerifierHarness(Harness):
    """Custom verifier harness that extracts repo snapshot via RoRepoSnapshotManager and verifies code."""

    def __init__(self, tmp_base_dir: Path) -> None:
        self.tmp_base_dir = tmp_base_dir
        self.invocations: list[dict[str, Any]] = []

    async def run(self, ctx: RenderedContext, agent_def: object) -> bytes:
        """Inspect repo snapshot and return schema-valid verdict JSON."""
        del agent_def
        repo_ctx = ctx.repo_context
        assert repo_ctx is not None, "RepoContext must be present"

        # Materialize detached read-only snapshot of head commit
        mgr = RoRepoSnapshotManager(
            execution_id=ctx.verdict_nonce,
            repo_context=repo_ctx,
            base_dir=self.tmp_base_dir,
        )
        staging_dir = await mgr.materialize()
        try:
            assert staging_dir is not None
            calc_path = staging_dir / "src" / "calc.py"
            assert calc_path.is_file(), f"calc.py not found in snapshot at {staging_dir}"
            code_text = calc_path.read_text(encoding="utf-8")

            # Check for defect: compute() must return non-negative value
            is_buggy = "-1" in code_text or "return -1" in code_text
            self.invocations.append(
                {
                    "head_commit": repo_ctx.head_commit,
                    "is_buggy": is_buggy,
                }
            )

            if is_buggy:
                verdict = {
                    "schema": "kb-transition-verdict/v1",
                    "nonce": ctx.verdict_nonce,
                    "decision": "reject",
                    "reason_markdown": (
                        f"Code verification failed at commit {repo_ctx.head_commit[:8]}: "
                        "`compute()` in `src/calc.py` returns invalid negative output."
                    ),
                    "cited_files": ["src/calc.py"],
                    "field_updates": {},
                    "add_labels": [],
                    "add_links": [],
                }
            else:
                verdict = {
                    "schema": "kb-transition-verdict/v1",
                    "nonce": ctx.verdict_nonce,
                    "decision": "approve",
                    "reason_markdown": (
                        f"Code verification passed at commit {repo_ctx.head_commit[:8]}: "
                        "`compute()` in `src/calc.py` correctly returns valid positive output."
                    ),
                    "cited_files": ["src/calc.py"],
                    "field_updates": {},
                    "add_labels": [],
                    "add_links": [],
                }

            return json.dumps(verdict).encode("utf-8")
        finally:
            mgr.cleanup()


async def _get_states(session: AsyncSession, project_id: uuid.UUID) -> dict[str, uuid.UUID]:
    """Fetch workflow state IDs by name."""
    await session.rollback()
    stmt = select(WorkflowState.name, WorkflowState.id).where(
        WorkflowState.project_id == project_id
    )
    rows = (await session.execute(stmt)).all()
    return {str(r[0]): r[1] for r in rows}


async def test_e2e_transition_gate_reject_rework_accept_loop(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
    tmp_path: Path,
) -> None:
    """E2E reject -> rework -> accept loop with real git commits and RoRepoSnapshotManager."""
    # -------------------------------------------------------------------------
    # 1. Setup local Git repository fixture with initial buggy commit
    # -------------------------------------------------------------------------
    repo_work = tmp_path / "work_repo"
    repo_work.mkdir(parents=True)

    def git(*args: str) -> str:
        res = subprocess.run(
            ["git", *args],
            cwd=repo_work,
            check=True,
            capture_output=True,
            text=True,
        )
        return res.stdout.strip()

    git("init")
    git("config", "user.name", "Developer")
    git("config", "user.email", "dev@example.com")
    git("config", "commit.gpgsign", "false")

    src_dir = repo_work / "src"
    src_dir.mkdir(parents=True)
    calc_file = src_dir / "calc.py"
    calc_file.write_text("def compute() -> int:\n    return -1  # Defect\n", encoding="utf-8")

    git("add", ".")
    git("commit", "-m", "feat: initial buggy implementation")
    commit_sha_1 = git("rev-parse", "HEAD")

    # Create bare mirror repo so RoRepoSnapshotManager can git archive from it
    bare_repo_dir = tmp_path / "mirror.git"
    subprocess.run(
        ["git", "clone", "--bare", str(repo_work), str(bare_repo_dir)],
        check=True,
        capture_output=True,
    )

    # -------------------------------------------------------------------------
    # 2. Provision DB: workspace, project, workflow hook, and verifier agent
    # -------------------------------------------------------------------------
    admin = await make_user("e2e_admin", workspace_role="WORKSPACE_ADMIN")
    proj_id = await make_project("E2EP", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    client = as_principal(admin)

    states = await _get_states(api_env.seed, proj_id)
    in_prog_id = states["In Progress"]
    done_id = states["Done"]

    # Provision agent principal & agent definition
    agent_principal = Principal(
        id=uuid.uuid7() if hasattr(uuid, "uuid7") else uuid.uuid4(),
        workspace_id=api_env.workspace_id,
        principal_type="AGENT",
        display_name="Quality Gate Verifier",
    )
    api_env.seed.add(agent_principal)
    await api_env.seed.flush()

    agent_def = AgentDefinition(
        id=uuid.uuid7() if hasattr(uuid, "uuid7") else uuid.uuid4(),
        workspace_id=api_env.workspace_id,
        project_id=proj_id,
        principal_id=agent_principal.id,
        slug="qa-code-verifier",
        display_name="Quality Gate Verifier",
        harness_kind="in_app_sdk",
        provider_kind="openai",
        model_id="gpt-4o",
        repo_access_mode="ro_vfs_mount",
        timeout_ms=30000,
    )
    api_env.seed.add(agent_def)

    # Provision workflow transition hook to Done
    hook_manifest_sha = compute_hook_manifest_sha256(
        hook_kind="agent_interceptor",
        wasm_module_sha256=None,
        agent_definition_id=agent_def.id,
        allowed_mutable_fields=[],
        failure_policy="fail_closed",
        from_state_id=None,
        to_state_id=done_id,
    )
    hook = WorkflowTransitionHook(
        id=uuid.uuid7() if hasattr(uuid, "uuid7") else uuid.uuid4(),
        workspace_id=api_env.workspace_id,
        project_id=proj_id,
        from_state_id=None,
        to_state_id=done_id,
        sort_rank="10",
        name="verify_code_gate",
        hook_kind="agent_interceptor",
        is_enabled=True,
        wasm_module_sha256=None,
        agent_definition_id=agent_def.id,
        allowed_mutable_fields=[],
        failure_policy="fail_closed",
        manifest_sha256=hook_manifest_sha,
    )
    api_env.seed.add(hook)
    agent_principal_id = agent_principal.id
    hook_id = hook.id
    await api_env.seed.commit()

    # Create issue in In Progress
    create_resp = await client.post(
        "/api/v1/projects/E2EP/issues",
        json={
            "summary": "Implement arithmetic calculation engine",
            "description_markdown": "Need compute function returning integer.",
            "state_id": str(in_prog_id),
        },
    )
    assert create_resp.status_code == 201
    issue_data = create_resp.json()
    issue_key = issue_data["key"]
    issue_id = uuid.UUID(issue_data["id"])
    await api_env.seed.rollback()

    # -------------------------------------------------------------------------
    # 3. Setup GateWorker with custom verifier harness
    # -------------------------------------------------------------------------
    verifier_harness = RepoVerifierHarness(tmp_base_dir=tmp_path / "snapshots")
    registry = HarnessRegistry(auto_register_defaults=False)
    registry.register("in_app_sdk", verifier_harness)

    class DBGateCoordinatorAdapter:
        """Adapts GateCoordinator class methods for GateWorker protocol."""

        def __init__(self, session: AsyncSession) -> None:
            self.session = session

        async def record_decision(
            self, execution_id: object, hook_id: object, decision: object
        ) -> object:
            return await GateCoordinator.record_decision(
                self.session,
                uuid.UUID(str(execution_id)),
                uuid.UUID(str(hook_id)),
                decision,  # type: ignore[arg-type]
            )

        async def record_failure(self, execution_id: object, hook_id: object, code: str) -> object:
            return await GateCoordinator.record_failure(
                self.session,
                uuid.UUID(str(execution_id)),
                uuid.UUID(str(hook_id)),
                code,
            )

    worker = GateWorker(
        registry=registry,
        coordinator=DBGateCoordinatorAdapter(api_env.seed),
    )

    # -------------------------------------------------------------------------
    # 4. FIRST TRANSITION: Buggy commit -> Enters pending hold (⏳🤖) -> REJECT (🛑🤖)
    # -------------------------------------------------------------------------
    t1_resp = await client.post(
        f"/api/v1/issues/{issue_key}/transitions",
        json={"to_state": "Done"},
    )
    assert t1_resp.status_code == 202
    t1_body = t1_resp.json()
    assert t1_body["status"] == "pending_agent_gate"
    assert t1_body["active_agent"] == "qa-code-verifier"
    assert t1_body["state"] == "In Progress"
    exec1_id = uuid.UUID(t1_body["execution_id"])

    # Verify hold is active in DB
    await api_env.seed.rollback()
    issue_row_1 = (
        await api_env.seed.execute(select(Issue).where(Issue.id == issue_id))
    ).scalar_one()
    assert issue_row_1.pending_transition_exec_id == exec1_id
    assert issue_row_1.state_id == in_prog_id

    # Construct dispatch event with repo_context pointing to commit_sha_1
    dispatch_event_1 = {
        "execution_id": str(exec1_id),
        "hook_id": str(hook.id),
        "execution": {
            "id": str(exec1_id),
            "project_key": "E2EP",
            "from_state": "In Progress",
            "to_state": "Done",
            "actor": "developer",
            "allowed_mutable_fields": (),
        },
        "issue": {
            "key": issue_key,
            "summary": "Implement arithmetic calculation engine",
            "description_markdown": "Need compute function returning integer.",
        },
        "agent_def": {
            "slug": "qa-code-verifier",
            "harness_kind": "in_app_sdk",
            "timeout_ms": 30000,
        },
        "repo_context": RepoContext(
            mount_path=str(bare_repo_dir),
            access="read-only",
            head_commit=commit_sha_1,
            mirror_path=bare_repo_dir,
        ),
    }

    # Execute gate worker against first commit
    await worker.handle_dispatch(dispatch_event_1)
    await api_env.seed.commit()

    # Assert verifier was invoked and rejected defect
    assert len(verifier_harness.invocations) == 1
    assert verifier_harness.invocations[0]["head_commit"] == commit_sha_1
    assert verifier_harness.invocations[0]["is_buggy"] is True

    # Assert execution recorded status=rejected with cited_files
    await api_env.seed.rollback()
    exec1_db = (
        await api_env.seed.execute(
            select(WorkflowTransitionExecution).where(WorkflowTransitionExecution.id == exec1_id)
        )
    ).scalar_one()
    assert exec1_db.status == "rejected"
    assert exec1_db.verdict_json is not None
    assert exec1_db.verdict_json["decision"] == "reject"
    assert exec1_db.verdict_json["cited_files"] == ["src/calc.py"]

    # Assert invocation record
    inv1_db = (
        await api_env.seed.execute(
            select(WorkflowHookInvocation).where(
                WorkflowHookInvocation.execution_id == exec1_id,
                WorkflowHookInvocation.hook_id == hook_id,
            )
        )
    ).scalar_one()
    assert inv1_db.status == "rejected"
    assert inv1_db.output_json["cited_files"] == ["src/calc.py"]

    # Assert issue rolled back to source state (In Progress) and hold was cleared
    issue_post_1 = (
        await api_env.seed.execute(select(Issue).where(Issue.id == issue_id))
    ).scalar_one()
    assert issue_post_1.state_id == in_prog_id
    assert issue_post_1.pending_transition_exec_id is None

    # Assert veto comment posted with agent principal attribution
    comments_1 = (
        (await api_env.seed.execute(select(IssueComment).where(IssueComment.issue_id == issue_id)))
        .scalars()
        .all()
    )
    assert len(comments_1) == 1
    assert comments_1[0].author_id == agent_principal_id
    assert "🛑🤖 Gate `verify_code_gate`" in comments_1[0].body_markdown
    assert "Code verification failed" in comments_1[0].body_markdown
    assert "src/calc.py" in comments_1[0].body_markdown

    # -------------------------------------------------------------------------
    # 5. REWORK STEP: Fix the bug and commit to repo snapshot
    # -------------------------------------------------------------------------
    calc_file.write_text("def compute() -> int:\n    return 42  # Fixed!\n", encoding="utf-8")
    git("add", ".")
    git("commit", "-m", "fix: correct compute logic to return valid non-negative integer")
    commit_sha_2 = git("rev-parse", "HEAD")
    assert commit_sha_2 != commit_sha_1

    # Push/update bare mirror repository with the fix
    subprocess.run(
        ["git", "push", str(bare_repo_dir), "HEAD:master"],
        cwd=repo_work,
        check=True,
        capture_output=True,
    )

    # -------------------------------------------------------------------------
    # 6. SECOND TRANSITION: Fixed commit -> Enters pending hold (⏳🤖) -> APPROVE (✅🤖)
    # -------------------------------------------------------------------------
    t2_resp = await client.post(
        f"/api/v1/issues/{issue_key}/transitions",
        json={"to_state": "Done"},
    )
    assert t2_resp.status_code == 202
    t2_body = t2_resp.json()
    assert t2_body["status"] == "pending_agent_gate"
    assert t2_body["active_agent"] == "qa-code-verifier"
    exec2_id = uuid.UUID(t2_body["execution_id"])
    assert exec2_id != exec1_id

    # Verify hold is active in DB for execution 2
    await api_env.seed.rollback()
    issue_row_2 = (
        await api_env.seed.execute(select(Issue).where(Issue.id == issue_id))
    ).scalar_one()
    assert issue_row_2.pending_transition_exec_id == exec2_id
    assert issue_row_2.state_id == in_prog_id

    # Construct dispatch event 2 with repo_context pointing to commit_sha_2
    dispatch_event_2 = {
        "execution_id": str(exec2_id),
        "hook_id": str(hook_id),
        "execution": {
            "id": str(exec2_id),
            "project_key": "E2EP",
            "from_state": "In Progress",
            "to_state": "Done",
            "actor": "developer",
            "allowed_mutable_fields": (),
        },
        "issue": {
            "key": issue_key,
            "summary": "Implement arithmetic calculation engine",
            "description_markdown": "Need compute function returning integer.",
        },
        "agent_def": {
            "slug": "qa-code-verifier",
            "harness_kind": "in_app_sdk",
            "timeout_ms": 30000,
        },
        "repo_context": RepoContext(
            mount_path=str(bare_repo_dir),
            access="read-only",
            head_commit=commit_sha_2,
            mirror_path=bare_repo_dir,
        ),
    }

    # Execute gate worker against second commit
    await worker.handle_dispatch(dispatch_event_2)
    await api_env.seed.commit()

    # Assert verifier was invoked second time and approved
    assert len(verifier_harness.invocations) == 2
    assert verifier_harness.invocations[1]["head_commit"] == commit_sha_2
    assert verifier_harness.invocations[1]["is_buggy"] is False

    # Assert execution recorded status=approved
    await api_env.seed.rollback()
    exec2_db = (
        await api_env.seed.execute(
            select(WorkflowTransitionExecution).where(WorkflowTransitionExecution.id == exec2_id)
        )
    ).scalar_one()
    assert exec2_db.status == "approved"
    assert exec2_db.verdict_json is not None
    assert exec2_db.verdict_json["decision"] == "approve"
    assert exec2_db.verdict_json["cited_files"] == ["src/calc.py"]

    # Assert issue advanced to Done (✅🤖) and hold was cleared
    issue_post_2 = (
        await api_env.seed.execute(select(Issue).where(Issue.id == issue_id))
    ).scalar_one()
    assert issue_post_2.state_id == done_id
    assert issue_post_2.pending_transition_exec_id is None

    # -------------------------------------------------------------------------
    # 7. Verify Immutable Activity Audit Ledger Provenance & Hash Chain
    # -------------------------------------------------------------------------
    stmt = (
        select(ActivityRecord)
        .where(
            ActivityRecord.object_id == issue_id,
            ActivityRecord.workspace_id == api_env.workspace_id,
        )
        .order_by(ActivityRecord.chain_seq.asc())
    )
    records = (await api_env.seed.execute(stmt)).scalars().all()
    event_types = [r.event_type for r in records]

    # Verify key lifecycle audit records exist in immutable ledger
    assert "GATE_REJECTED" in event_types
    assert "GATE_APPROVED" in event_types
    assert "ISSUE_STATE_CHANGED" in event_types

    # Verify cryptographic hash chain integrity across all records
    for i in range(1, len(records)):
        assert records[i].prev_hash == records[i - 1].row_hash, (
            f"Hash chain broken between seq {records[i - 1].chain_seq} and {records[i].chain_seq}"
        )

    # Verify outbox events emitted for both rejection and approval
    outbox_approved = (
        (
            await api_env.seed.execute(
                select(OutboxEvent).where(
                    OutboxEvent.object_id == issue_id,
                    OutboxEvent.topic == "workflow.gate.approved",
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(outbox_approved) >= 1
    assert outbox_approved[0].payload["execution_id"] == str(exec2_id)
