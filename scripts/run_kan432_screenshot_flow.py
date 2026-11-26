# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Zero-Mock Screenshot Orchestrator for KAN-432.

Binds temporary test server strictly to 127.0.0.1:18432.
Seeds hermetic test database kanban_live432 from kanban_template.
Tears down server cleanly after capture.
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import json
import os
import subprocess
import time
import uuid
from typing import Any

import asyncpg
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from kanban.auth.sessions.service import SessionService
from database.models.workflow import WorkflowTransitionHook
from kanban.workflows.manifest import compute_hook_manifest_sha256

SOCKET_DIR = os.environ.get("KB_TEST_PGHOST", "/tmp/kb-pgsock-kan431")
PORT = 18432
DB_NAME = "kanban_live432"
SUPERUSER_DSN = f"postgresql://kanban_test@/{DB_NAME}?host={SOCKET_DIR}"
MIGRATOR_URL = f"postgresql+asyncpg://kanban_migrator@/{DB_NAME}?host={SOCKET_DIR}"
APP_URL = f"postgresql+asyncpg://kanban_app@/{DB_NAME}?host={SOCKET_DIR}"

SESSION_HMAC_KEY = b"s" * 32
MASTER_KEK = b"k" * 32
AUTH_PEPPER = b"p" * 32


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode("ascii").rstrip("=")


async def prepare_database() -> dict[str, Any]:
    print("[KAN-432 Prep] Creating pristine database from kanban_template...")
    conn = await asyncpg.connect(user="kanban_test", database="postgres", host=SOCKET_DIR)
    try:
        await conn.execute(f'DROP DATABASE IF EXISTS "{DB_NAME}" WITH (FORCE)')
        await conn.execute(f'CREATE DATABASE "{DB_NAME}" TEMPLATE kanban_template')
    finally:
        await conn.close()

    print("[KAN-432 Prep] Seeding workspace, project KAN, states, priorities, agent, hooks, and issues...")
    engine = create_async_engine(MIGRATOR_URL)
    async_session = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with async_session() as s:
        # 1. Workspace
        ws_id = uuid.uuid4()
        await s.execute(
            text("INSERT INTO workspaces (id, slug, name) VALUES (:id, 'engineering', 'Engineering')"),
            {"id": ws_id},
        )

        # 2. Server Admin Principal & User
        p_id = uuid.uuid4()
        await s.execute(
            text(
                "INSERT INTO principals (id, workspace_id, principal_type, status, display_name) "
                "VALUES (:id, :ws_id, 'USER', 'ACTIVE', 'Admin User')"
            ),
            {"id": p_id, "ws_id": ws_id},
        )
        await s.execute(
            text(
                "SELECT register_object('user'::object_kind, :ws_id, NULL, 'server_admin', 'Admin User', :p_id, :p_id)"
            ),
            {"ws_id": ws_id, "p_id": p_id},
        )
        await s.execute(
            text(
                "INSERT INTO users (id, object_type, principal_type, workspace_id, email) "
                "VALUES (:id, 'user', 'USER', :ws_id, 'admin@kanban.local')"
            ),
            {"id": p_id, "ws_id": ws_id},
        )

        # 3. Project KAN
        reg_row = await s.execute(
            text("SELECT register_object('project'::object_kind, :ws_id, NULL, 'KAN', 'Core Platform', :p_id)"),
            {"ws_id": ws_id, "p_id": p_id},
        )
        proj_id = reg_row.scalar_one()
        await s.execute(
            text(
                "INSERT INTO projects (id, workspace_id, identifier, name, modules_enabled) "
                "VALUES (:id, :ws_id, 'KAN', 'Core Platform', false)"
            ),
            {"id": proj_id, "ws_id": ws_id},
        )

        # 4. Workflow States
        existing_states = (
            await s.execute(
                text("SELECT id, name FROM workflow_states WHERE project_id = :p_id"),
                {"p_id": proj_id},
            )
        ).fetchall()
        state_ids = {row[1]: row[0] for row in existing_states}

        states_to_seed = [
            ("Backlog", "backlog", "#94a3b8", 10, True),
            ("To Do", "unstarted", "#64748b", 20, False),
            ("In Progress", "started", "#3b82f6", 30, False),
            ("Done", "completed", "#22c55e", 40, False),
        ]
        for sname, sgroup, scolor, sorder, is_def in states_to_seed:
            if sname not in state_ids:
                sid = uuid.uuid4()
                state_ids[sname] = sid
                await s.execute(
                    text(
                        "INSERT INTO workflow_states (id, workspace_id, project_id, name, state_group, color_hex, sort_order, is_default, wip_soft_limit) "
                        "VALUES (:id, :ws_id, :p_id, :name, :sgroup, :scolor, :sorder, :is_def, :wip)"
                    ),
                    {
                        "id": sid,
                        "ws_id": ws_id,
                        "p_id": proj_id,
                        "name": sname,
                        "sgroup": sgroup,
                        "scolor": scolor,
                        "sorder": sorder,
                        "is_def": is_def,
                        "wip": 5 if sname == "In Progress" else None,
                    },
                )

        # 5. Fetch project priorities
        prio_rows = (
            await s.execute(
                text("SELECT id, slug FROM project_priorities WHERE project_id = :p"),
                {"p": proj_id},
            )
        ).fetchall()
        prio_map = {row[1]: row[0] for row in prio_rows}

        # 6. Role Bindings
        await s.execute(
            text(
                "INSERT INTO role_bindings (workspace_id, principal_id, role, scope_type) "
                "VALUES (:ws_id, :p_id, 'SERVER_ADMIN', 'server'), (:ws_id, :p_id, 'WORKSPACE_ADMIN', 'workspace')"
            ),
            {"ws_id": ws_id, "p_id": p_id},
        )
        await s.execute(
            text(
                "INSERT INTO role_bindings (workspace_id, principal_id, role, scope_type, project_id) "
                "VALUES (:ws_id, :p_id, 'PROJECT_ADMIN', 'project', :proj_id)"
            ),
            {"ws_id": ws_id, "p_id": p_id, "proj_id": proj_id},
        )

        # 7. Agent Definition
        agent1_id = uuid.uuid4()
        instructions = (
            "# Mandatory QA Gatekeeper Instructions\n\n"
            "1. Verify all test evidence before transitioning to Done.\n"
            "2. Ensure zero mock data in production.\n"
            "3. Validate test coverage >= 95%."
        )
        await s.execute(
            text(
                "INSERT INTO agent_definitions (id, workspace_id, principal_id, slug, display_name, harness_kind, provider_kind, model_id, cli_binary_allowlist_id, cli_args_json, repo_access_mode, mcp_allowed_tools, system_instructions_md, timeout_ms) "
                "VALUES (:id, :ws_id, :p_id, 'qa-gatekeeper', 'QA Gatekeeper', 'cli_pipe', NULL, NULL, 'agy', '[\"-p\"]'::jsonb, 'ro_vfs_mount', '{\"search_tickets\",\"read_ticket\"}', :instructions, 180000)"
            ),
            {"id": agent1_id, "ws_id": ws_id, "p_id": p_id, "instructions": instructions},
        )

        # 8. Workflow Transition Hook: In Progress -> Done
        msha1 = compute_hook_manifest_sha256(
            from_state_id=state_ids["In Progress"],
            to_state_id=state_ids["Done"],
            hook_kind="agent_interceptor",
            wasm_module_sha256=None,
            agent_definition_id=agent1_id,
            allowed_mutable_fields=[],
            failure_policy="fail_closed",
        )
        hook1 = WorkflowTransitionHook(
            workspace_id=ws_id,
            project_id=proj_id,
            name="QA Gatekeeper",
            from_state_id=state_ids["In Progress"],
            to_state_id=state_ids["Done"],
            hook_kind="agent_interceptor",
            sort_rank="0|hzzzzz:",
            is_enabled=True,
            agent_definition_id=agent1_id,
            manifest_sha256=msha1,
            allowed_mutable_fields=[],
            failure_policy="fail_closed",
        )
        s.add(hook1)
        await s.flush()

        # 9. Seed 5 Real Issues
        issue_specs = [
            (
                "KAN-1",
                "Sliding window rate limiter with lone-surrogate validation",
                "In Progress",
                "high",
                "0|hzzzz1:",
            ),
            (
                "KAN-2",
                "Universal Object Graph link auditor and integrity checker",
                "In Progress",
                "urgent",
                "0|hzzzz2:",
            ),
            (
                "KAN-3",
                "Content-Security-Policy manifest-src self directive header",
                "Done",
                "medium",
                "0|hzzzz3:",
            ),
            (
                "KAN-4",
                "Hardware token WebAuthn multi-card authenticator",
                "To Do",
                "low",
                "0|hzzzz4:",
            ),
            (
                "KAN-5",
                "Async agent interceptor gate lifecycle",
                "Backlog",
                "none",
                "0|hzzzz5:",
            ),
        ]

        created_issues: dict[str, uuid.UUID] = {}
        for key, summary, sname, prio_slug, rank in issue_specs:
            seq = await s.scalar(
                text("SELECT allocate_issue_sequence(:p)"),
                {"p": proj_id},
            )
            iss_id = await s.scalar(
                text(
                    "SELECT register_object('issue'::object_kind, :ws, :proj, :ckey, :name, :creator)"
                ),
                {
                    "ws": ws_id,
                    "proj": proj_id,
                    "ckey": key,
                    "name": summary,
                    "creator": p_id,
                },
            )
            created_issues[key] = iss_id
            await s.execute(
                text(
                    "INSERT INTO issues ("
                    "  id, workspace_id, project_id, sequence_id, summary, state_id, "
                    "  priority_id, board_rank, created_by_id, original_created_by_id"
                    ") VALUES ("
                    "  :id, :ws, :proj, :seq, :summary, :state, :prio, :rank, :creator, :creator"
                    ")"
                ),
                {
                    "id": iss_id,
                    "ws": ws_id,
                    "proj": proj_id,
                    "seq": seq,
                    "summary": summary,
                    "state": state_ids[sname],
                    "prio": prio_map.get(prio_slug, prio_map.get("none")),
                    "rank": rank,
                    "creator": p_id,
                },
            )

        # 10. Execution records for KAN-1, KAN-2, and KAN-3:
        # KAN-1: Pending gate execution
        exec1_id = uuid.uuid4()
        await s.execute(
            text(
                "INSERT INTO workflow_transition_executions ("
                "  id, workspace_id, project_id, issue_id, invoking_principal_id, from_state_id, to_state_id, "
                "  status, hop_depth, issue_body_sha256_snapshot"
                ") VALUES ("
                "  :id, :ws, :proj, :iss, :p_id, :from_s, :to_s, 'pending_async', 0, :snap"
                ")"
            ),
            {
                "id": exec1_id,
                "ws": ws_id,
                "proj": proj_id,
                "iss": created_issues["KAN-1"],
                "p_id": p_id,
                "from_s": state_ids["In Progress"],
                "to_s": state_ids["Done"],
                "snap": b"\x00" * 32,
            },
        )
        await s.execute(
            text(
                "INSERT INTO workflow_hook_invocations ("
                "  id, workspace_id, execution_id, hook_id, hook_kind, status, started_at"
                ") VALUES ("
                "  :id, :ws, :exec_id, :hook_id, 'agent_interceptor', 'running', clock_timestamp()"
                ")"
            ),
            {
                "id": uuid.uuid4(),
                "ws": ws_id,
                "exec_id": exec1_id,
                "hook_id": hook1.id,
            },
        )
        await s.execute(
            text("UPDATE issues SET pending_transition_exec_id = :exec_id WHERE id = :iss_id"),
            {"exec_id": exec1_id, "iss_id": created_issues["KAN-1"]},
        )

        # KAN-2: Vetoed / rejected gate execution
        exec2_id = uuid.uuid4()
        verdict2 = json.dumps(
            {
                "decision": "reject",
                "hook_name": "Reality Checker QA Gate",
                "latency_ms": 320,
                "verdict_sha256": "432abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890",
            }
        )
        await s.execute(
            text(
                "INSERT INTO workflow_transition_executions ("
                "  id, workspace_id, project_id, issue_id, invoking_principal_id, from_state_id, to_state_id, "
                "  status, hop_depth, issue_body_sha256_snapshot, completed_at, verdict_json"
                ") VALUES ("
                "  :id, :ws, :proj, :iss, :p_id, :from_s, :to_s, 'rejected', 0, :snap, clock_timestamp(), CAST(:vjson AS jsonb)"
                ")"
            ),
            {
                "id": exec2_id,
                "ws": ws_id,
                "proj": proj_id,
                "iss": created_issues["KAN-2"],
                "p_id": p_id,
                "from_s": state_ids["In Progress"],
                "to_s": state_ids["Done"],
                "snap": b"\x00" * 32,
                "vjson": verdict2,
            },
        )
        await s.execute(
            text(
                "INSERT INTO workflow_hook_invocations ("
                "  id, workspace_id, execution_id, hook_id, hook_kind, status, duration_us, started_at, completed_at, output_json"
                ") VALUES ("
                "  :id, :ws, :exec_id, :hook_id, 'agent_interceptor', 'rejected', 320000, clock_timestamp(), clock_timestamp(), CAST(:out_json AS jsonb)"
                ")"
            ),
            {
                "id": uuid.uuid4(),
                "ws": ws_id,
                "exec_id": exec2_id,
                "hook_id": hook1.id,
                "out_json": verdict2,
            },
        )
        await s.execute(
            text(
                "INSERT INTO activity_records ("
                "  workspace_id, object_id, object_type, actor_id, event_type, payload, recorded_at"
                ") VALUES ("
                "  :ws, :oid, 'issue'::object_kind, :actor, 'GATE_REJECTED', CAST(:payload AS jsonb), clock_timestamp()"
                ")"
            ),
            {
                "ws": ws_id,
                "oid": created_issues["KAN-2"],
                "actor": p_id,
                "payload": verdict2,
            },
        )

        # KAN-3: Approved gate execution
        exec3_id = uuid.uuid4()
        verdict3 = json.dumps(
            {
                "decision": "approve",
                "hook_name": "Security Gate",
                "latency_ms": 150,
                "verdict_sha256": "432fedcba0987654321fedcba0987654321fedcba0987654321fedcba0987654321",
            }
        )
        await s.execute(
            text(
                "INSERT INTO workflow_transition_executions ("
                "  id, workspace_id, project_id, issue_id, invoking_principal_id, from_state_id, to_state_id, "
                "  status, hop_depth, issue_body_sha256_snapshot, completed_at, verdict_json"
                ") VALUES ("
                "  :id, :ws, :proj, :iss, :p_id, :from_s, :to_s, 'approved', 0, :snap, clock_timestamp(), CAST(:vjson AS jsonb)"
                ")"
            ),
            {
                "id": exec3_id,
                "ws": ws_id,
                "proj": proj_id,
                "iss": created_issues["KAN-3"],
                "p_id": p_id,
                "from_s": state_ids["In Progress"],
                "to_s": state_ids["Done"],
                "snap": b"\x00" * 32,
                "vjson": verdict3,
            },
        )

        # 11. TOTP Setup
        with contextlib.suppress(Exception):
            await s.execute(
                text("SELECT kb_auth.totp_enroll(:p_id, :blob, :dek, 'test-kid-1')"),
                {"p_id": p_id, "blob": b"\x01" + b"\x00" * 28, "dek": b"\x01" + b"\x00" * 44},
            )
            res_totp = await s.execute(
                text("SELECT id FROM kb_auth.totp_get_pending(:p_id)"),
                {"p_id": p_id},
            )
            totp_row = res_totp.first()
            if totp_row:
                await s.execute(
                    text("SELECT kb_auth.totp_confirm(:p_fid, 100)"),
                    {"p_fid": totp_row[0]},
                )

        # 12. Issue AAL2 Session
        svc = SessionService(session_hmac_key=SESSION_HMAC_KEY)
        issued = await svc.create_after_login(
            s,
            principal_id=p_id,
            workspace_id=ws_id,
            aal_level=2,
            remember_me=True,
        )
        await s.commit()

    await engine.dispose()
    print("[KAN-432 Prep] Database preparation complete.")
    return {
        "cookie_val": issued.cookie_val,
        "csrf_token": issued.csrf_token,
    }


def main() -> None:
    seed_info = asyncio.run(prepare_database())
    env = os.environ.copy()
    env["KANBAN_DEPLOYMENT_MODE"] = "standalone"
    env["KB_BIND_HOST"] = "127.0.0.1"
    env["KB_BIND_PORT"] = str(PORT)
    env["KB_PUBLIC_ORIGIN"] = f"http://127.0.0.1:{PORT}"
    env["KANBAN_DATABASE_URL"] = APP_URL
    env["KANBAN_MASTER_KEK"] = _b64(MASTER_KEK)
    env["KANBAN_AUTH_PEPPER"] = _b64(AUTH_PEPPER)
    env["KANBAN_SESSION_HMAC_KEY"] = _b64(SESSION_HMAC_KEY)
    env["KANBAN_MASTER_KEK_KID"] = "test-kid-1"
    env["KAN432_PORT"] = str(PORT)
    env["KAN432_COOKIE"] = seed_info["cookie_val"]
    env["KAN432_CSRF"] = seed_info["csrf_token"]

    uv_log = open("/tmp/uvicorn_kan432.log", "w")
    print(f"[KAN-432] Spawning temporary Kanban server on 127.0.0.1:{PORT}...")
    python_bin = "/home/adamoutler/kanban/.venv/bin/python"
    if not os.path.exists(python_bin):
        python_bin = "python3"

    proc = subprocess.Popen(
        [
            python_bin,
            "-m",
            "uvicorn",
            "kanban.app:create_app",
            "--factory",
            "--host",
            "127.0.0.1",
            "--port",
            str(PORT),
            "--log-level",
            "info",
        ],
        env=env,
        stdout=uv_log,
        stderr=uv_log,
    )

    try:
        import urllib.request

        print(f"[KAN-432] Waiting for server on http://127.0.0.1:{PORT} to be ready...")
        ready = False
        for _ in range(40):
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/", timeout=1) as resp:
                    if resp.status in (200, 302, 404):
                        ready = True
                        break
            except Exception:
                time.sleep(0.5)

        if not ready:
            raise RuntimeError(f"Server on port {PORT} failed to become ready.")

        print(f"[KAN-432] Server is ready! Executing Playwright screenshot capture...")
        subprocess.run(
            ["node", "scripts/capture_kan432_screenshots.mjs"],
            env=env,
            check=True,
        )
        print("[KAN-432] Screenshots captured successfully!")
    finally:
        print("[KAN-432] Terminating temporary server cleanly...")
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        uv_log.close()
        print("[KAN-432] Teardown complete.")


if __name__ == "__main__":
    main()
