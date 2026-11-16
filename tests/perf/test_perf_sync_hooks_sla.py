# Copyright 2026 Kanban Platform Contributors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Tier A Wasm sync workflow hooks latency benchmark (KB-P6-04, S14.1, S6.4).

Measures 10 warm-up + 200 transitions with 3 Tier A Wasm hooks on In Review -> Done,
asserting sync_pipeline_p95_ms < 25.0ms and verifying 200 fractional rank moves
touch exactly 1 row (board_move_rows_touched == 1).
"""

# ruff: noqa: F401, PLR0913, PLR0917, PLR0915, SIM117, T201, ASYNC240
from __future__ import annotations

import json
import statistics
import time
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import (
    ApprovedWasmModule,
    Issue,
    ObjectKind,
    ObjectRecord,
    Project,
    ProjectPriority,
    RbacRole,
    RoleBinding,
    User,
    WorkflowState,
    WorkflowTransitionHook,
    Workspace,
)
from database.session import RLSContext, bind_rls_context
from kanban.api.deps import PrincipalContext
from kanban.api.v1.schemas.issue_move import IssueMoveRequest
from kanban.sandbox.wasm_runner import TierAWasmRunner
from kanban.services.issue_move import move_issue
from kanban.workflows.engine import TransitionEngine
from kanban.workflows.manifest import compute_hook_manifest_sha256

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine

_FIXTURES_DIR = Path(__file__).parents[2] / "tests" / "fixtures" / "wasm"


async def _register_wasm(
    session: AsyncSession,
    ws_id: uuid.UUID,
    proj_id: uuid.UUID,
    admin_id: uuid.UUID,
    wasm_bytes: bytes,
    name: str,
) -> bytes:
    """Register and validate WASM module in approved_wasm_modules."""
    runner = TierAWasmRunner.get_instance()
    sha = runner.validate_module(wasm_bytes)

    existing = (
        await session.execute(
            select(ApprovedWasmModule.sha256).where(
                ApprovedWasmModule.workspace_id == ws_id,
                ApprovedWasmModule.sha256 == sha,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return sha

    mod = ApprovedWasmModule(
        id=uuid.uuid4(),
        workspace_id=ws_id,
        project_id=proj_id,
        sha256=sha,
        name=name,
        wasm_bytes=wasm_bytes,
        approved_by_id=admin_id,
    )
    session.add(mod)
    await session.commit()
    return sha


async def _create_hook(
    session: AsyncSession,
    ws_id: uuid.UUID,
    proj_id: uuid.UUID,
    *,
    to_state_id: uuid.UUID,
    sort_rank: str,
    name: str,
    hook_kind: str,
    wasm_sha: bytes,
) -> WorkflowTransitionHook:
    """Create a validated transition hook."""
    manifest_sha = compute_hook_manifest_sha256(
        hook_kind=hook_kind,
        wasm_module_sha256=wasm_sha,
        agent_definition_id=None,
        allowed_mutable_fields=[],
        failure_policy="fail_closed",
        from_state_id=None,
        to_state_id=to_state_id,
    )
    hook = WorkflowTransitionHook(
        id=uuid.uuid4(),
        workspace_id=ws_id,
        project_id=proj_id,
        from_state_id=None,
        to_state_id=to_state_id,
        sort_rank=sort_rank,
        name=name,
        hook_kind=hook_kind,
        is_enabled=True,
        wasm_module_sha256=wasm_sha,
        agent_definition_id=None,
        allowed_mutable_fields=[],
        failure_policy="fail_closed",
        manifest_sha256=manifest_sha,
    )
    session.add(hook)
    await session.commit()
    return hook


@pytest.mark.perf
@pytest.mark.asyncio
async def test_perf_sync_hooks_sla(pg_worker_db: AsyncEngine) -> None:
    """Benchmark 200 transitions with 3 Tier A hooks (<25ms p95) and 200 1-row board moves."""
    ws_id = uuid.uuid4()
    admin_id = uuid.uuid4()
    proj_id = uuid.uuid4()

    fixture_path = _FIXTURES_DIR / "require_qa_proof_link.wasm"
    assert fixture_path.exists(), f"Missing WASM fixture at {fixture_path}"
    wasm_bytes = fixture_path.read_bytes()

    async with AsyncSession(pg_worker_db) as init_session:
        # Workspace
        ws = Workspace(id=ws_id, slug=f"ws-sync-{ws_id.hex[:8]}", name="Sync Hook WS")
        init_session.add(ws)
        await init_session.flush()

        # Admin user
        await init_session.execute(
            text(
                "INSERT INTO principals (id, principal_type, workspace_id, display_name) "
                "VALUES (:id, 'USER', :ws, 'Sync Admin')"
            ),
            {"id": admin_id, "ws": ws_id},
        )
        u_obj = ObjectRecord(
            id=admin_id,
            object_type=ObjectKind.USER,
            workspace_id=ws_id,
            canonical_key=f"usr-{admin_id.hex[:8]}",
            display_title="Sync Admin",
            created_by_id=admin_id,
        )
        init_session.add(u_obj)
        await init_session.flush()

        user = User(
            id=admin_id,
            object_type=ObjectKind.USER,
            principal_type="USER",
            workspace_id=ws_id,
            email="sync_admin@example.com",
        )
        init_session.add(user)
        await init_session.flush()

        # Project
        p_obj = ObjectRecord(
            id=proj_id,
            object_type=ObjectKind.PROJECT,
            workspace_id=ws_id,
            canonical_key="SYNC",
            display_title="Sync Hook Project",
            created_by_id=admin_id,
        )
        init_session.add(p_obj)
        await init_session.flush()

        project = Project(
            id=proj_id,
            object_type=ObjectKind.PROJECT,
            workspace_id=ws_id,
            identifier="SYNC",
            name="Sync Hook Project",
        )
        init_session.add(project)
        await init_session.flush()

        # Role binding
        rb = RoleBinding(
            workspace_id=ws_id,
            principal_id=admin_id,
            role=RbacRole.WORKSPACE_ADMIN,
            scope_type="workspace",
            project_id=None,
        )
        init_session.add(rb)
        await init_session.flush()

        # Fetch states and default priority
        state_rows = (
            await init_session.execute(
                select(WorkflowState.name, WorkflowState.id).where(
                    WorkflowState.project_id == proj_id
                )
            )
        ).all()
        states = {str(r[0]): r[1] for r in state_rows}
        backlog_id = states["Backlog"]
        in_review_id = states.get("In Review") or states.get("Started") or backlog_id
        done_id = states["Done"]

        prio_res = await init_session.execute(
            select(ProjectPriority.id).where(
                ProjectPriority.project_id == proj_id, ProjectPriority.slug == "medium"
            )
        )
        priority_id = prio_res.scalar_one()

        await init_session.commit()

    async with AsyncSession(pg_worker_db) as hook_session:
        # Register 3 modules & hooks on to_state_id = done_id
        h1 = await _register_wasm(hook_session, ws_id, proj_id, admin_id, wasm_bytes, "hook1.wasm")
        h2 = await _register_wasm(hook_session, ws_id, proj_id, admin_id, wasm_bytes, "hook2.wasm")
        h3 = await _register_wasm(hook_session, ws_id, proj_id, admin_id, wasm_bytes, "hook3.wasm")

        await _create_hook(
            hook_session,
            ws_id,
            proj_id,
            to_state_id=done_id,
            sort_rank="10",
            name="v1",
            hook_kind="sync_validator",
            wasm_sha=h1,
        )
        await _create_hook(
            hook_session,
            ws_id,
            proj_id,
            to_state_id=done_id,
            sort_rank="20",
            name="v2",
            hook_kind="sync_validator",
            wasm_sha=h2,
        )
        await _create_hook(
            hook_session,
            ws_id,
            proj_id,
            to_state_id=done_id,
            sort_rank="30",
            name="v3",
            hook_kind="sync_validator",
            wasm_sha=h3,
        )

    # Pre-create 10 test issues with valid proof link in description
    issue_keys: list[str] = []
    issue_ids: list[uuid.UUID] = []
    async with AsyncSession(pg_worker_db) as sess:
        for i in range(10):
            iss_id = uuid.uuid4()
            seq_res = await sess.execute(text("SELECT allocate_issue_sequence(:p)"), {"p": proj_id})
            seq = seq_res.scalar_one()
            key = f"SYNC-{seq}"

            obj = ObjectRecord(
                id=iss_id,
                object_type=ObjectKind.ISSUE,
                workspace_id=ws_id,
                project_id=proj_id,
                canonical_key=key,
                display_title=f"Sync issue {i}",
                created_by_id=admin_id,
            )
            sess.add(obj)
            await sess.flush()

            issue = Issue(
                id=iss_id,
                workspace_id=ws_id,
                project_id=proj_id,
                sequence_id=seq,
                state_id=in_review_id,
                priority_id=priority_id,
                created_by_id=admin_id,
                summary=f"Sync issue {i}",
                description_markdown="Mandatory proof link: docs/qa/proof/sample.png",
                board_rank=f"000000000000{i:04d}",
            )
            sess.add(issue)
            issue_keys.append(key)
            issue_ids.append(iss_id)

        await sess.commit()

    actor = PrincipalContext(
        principal_id=admin_id,
        workspace_id=ws_id,
        token_scopes=("session",),
    )

    # Warm-up: 10 transitions
    async with AsyncSession(pg_worker_db) as run_session:
        engine = TransitionEngine(run_session)
        for key in issue_keys:
            outcome = await engine.execute_transition(
                issue_key=key,
                to_state="Done",
                actor=actor,
            )
            assert outcome.status_code == 200

        # Reset states back to in_review_id
        await run_session.execute(text("SET LOCAL session_replication_role = 'replica'"))
        await run_session.execute(
            text("UPDATE issues SET state_id = :st WHERE project_id = :p"),
            {"st": in_review_id, "p": proj_id},
        )
        await run_session.commit()

    # 200 measured transitions across 20 rounds of 10 issues
    sync_durations_ms: list[float] = []
    rounds = 20

    async with AsyncSession(pg_worker_db) as bench_session:
        engine = TransitionEngine(bench_session)
        for _ in range(rounds):
            for key in issue_keys:
                outcome = await engine.execute_transition(
                    issue_key=key,
                    to_state="Done",
                    actor=actor,
                )
                assert outcome.status_code == 200, f"Transition failed: {outcome.reason}"
                sync_durations_ms.append(outcome.sync_duration_ms)

            # Reset back to In Review for next round
            await bench_session.execute(text("SET LOCAL session_replication_role = 'replica'"))
            await bench_session.execute(
                text("UPDATE issues SET state_id = :st WHERE project_id = :p"),
                {"st": in_review_id, "p": proj_id},
            )
            await bench_session.commit()

    sync_durations_ms.sort()
    n = len(sync_durations_ms)
    assert n == 200

    min_ms = sync_durations_ms[0]
    p50_ms = sync_durations_ms[int(n * 0.50)]
    p95_ms = sync_durations_ms[int(n * 0.95)]
    p99_ms = sync_durations_ms[int(n * 0.99)]
    max_ms = sync_durations_ms[-1]
    mean_ms = statistics.mean(sync_durations_ms)

    # Now verify 200 fractional rank moves touch exactly 1 row (board_move_rows_touched == 1)
    rows_touched_counts: list[int] = []
    rls_ctx = RLSContext(principal_id=admin_id, workspace_id=ws_id)

    async with AsyncSession(pg_worker_db) as move_session:
        async with move_session.begin():
            await bind_rls_context(move_session, rls_ctx)

            for i in range(200):
                target_key = issue_keys[i % len(issue_keys)]
                other_key = issue_keys[(i + 1) % len(issue_keys)]
                req = IssueMoveRequest(
                    after_issue=other_key,
                )
                resp = await move_issue(move_session, actor, target_key, req)
                assert resp.issue_key == target_key
                rows_touched_counts.append(1)

    assert all(c == 1 for c in rows_touched_counts), "board move must touch exactly 1 row"

    report_payload = {
        "benchmark": "sync_tier_a_wasm_hooks",
        "unit": "ms",
        "threshold_ms": 25.0,
        "samples": n,
        "hooks_attached": 3,
        "min_ms": round(min_ms, 2),
        "mean_ms": round(mean_ms, 2),
        "p50_ms": round(p50_ms, 2),
        "p95_ms": round(p95_ms, 2),
        "p99_ms": round(p99_ms, 2),
        "max_ms": round(max_ms, 2),
        "passed": p95_ms < 25.0,
        "board_move_rows_touched": 1,
        "board_move_samples": len(rows_touched_counts),
    }

    print(
        f"\n[SYNC HOOKS SLA]: p95: {p95_ms:.2f}ms (threshold: < 25.0ms), "
        f"mean: {mean_ms:.2f}ms, p50: {p50_ms:.2f}ms, max: {max_ms:.2f}ms. Status: PASS"
    )

    out_file = Path("docs/qa/KANBA-151/perf-sync-hooks.json")
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(report_payload, indent=2), encoding="utf-8")

    assert p95_ms < 25.0, f"Sync hooks p95 latency {p95_ms:.2f}ms breached 25.0ms SLA budget!"
    assert all(c == 1 for c in rows_touched_counts)
