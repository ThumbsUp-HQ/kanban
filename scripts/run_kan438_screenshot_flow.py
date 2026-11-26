# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Playwright Screenshot Orchestrator for KAN-438.

Binds temporary test server strictly to 127.0.0.1:18438.
Seeds hermetic test database kanban_live438 from kanban_template.
Captures responsive screenshots of:
1. System-Wide Default Workflow Hooks Studio (/admin/workflows)
2. Add Default Hook Template dialog
3. Project Workflow Studio (/projects/PROJ/settings/workflows) showing Inherited badge + Sync button
4. Workspace Default Workflow Hooks tab (/workspaces/settings#tab-workflows)
Tears down server cleanly after capture.
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import os
import subprocess
import sys
import time
import urllib.request
import uuid
from typing import Any

import asyncpg
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from database.models.workflow import DefaultWorkflowHook, WorkflowTransitionHook
from kanban.auth.sessions.service import SessionService
from kanban.workflows.manifest import compute_hook_manifest_sha256

SOCKET_DIR = os.environ.get("KB_TEST_PGHOST", "/tmp/kb-pgsock")
PORT = 18438
DB_NAME = "kanban_live438"
SUPERUSER_DSN = f"postgresql://kanban_test@/{DB_NAME}?host={SOCKET_DIR}"
MIGRATOR_URL = f"postgresql+asyncpg://kanban_migrator@/{DB_NAME}?host={SOCKET_DIR}"
APP_URL = f"postgresql+asyncpg://kanban_app@/{DB_NAME}?host={SOCKET_DIR}"

SESSION_HMAC_KEY = b"s" * 32
MASTER_KEK = b"k" * 32
AUTH_PEPPER = b"p" * 32


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode("ascii").rstrip("=")


async def prepare_database() -> dict[str, Any]:
    print("[KAN-438 Prep] Creating database from kanban_template...")
    conn = await asyncpg.connect(user="kanban_test", database="postgres", host=SOCKET_DIR)
    try:
        await conn.execute(f'DROP DATABASE IF EXISTS "{DB_NAME}" WITH (FORCE)')
        await conn.execute(f'CREATE DATABASE "{DB_NAME}" TEMPLATE kanban_template')
    finally:
        await conn.close()

    print("[KAN-438 Prep] Applying migration p6_24_default_workflow_hooks.up.sql...")
    with open("database/migrations/sql/p6_24_default_workflow_hooks.up.sql") as f:
        up_sql = f.read()
    mig_conn = await asyncpg.connect(user="kanban_migrator", database=DB_NAME, host=SOCKET_DIR)
    try:
        await mig_conn.execute(up_sql)
    finally:
        await mig_conn.close()

    print("[KAN-438 Prep] Seeding workspace, admin user, default hook templates, and project PROJ...")
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

        # 3. Agent Definition: Reality Checker
        agent_id = uuid.uuid4()
        instructions = (
            "# Mandatory Forensic Reality Checker\n\n"
            "1. Passive forensic audit of all code and test evidence.\n"
            "2. Ensure zero mock data and >=95% test coverage.\n"
            "3. Issue GRADE-A READY verification certification."
        )
        await s.execute(
            text(
                "INSERT INTO agent_definitions (id, workspace_id, principal_id, slug, display_name, harness_kind, provider_kind, model_id, cli_binary_allowlist_id, cli_args_json, repo_access_mode, mcp_allowed_tools, system_instructions_md, timeout_ms) "
                "VALUES (:id, :ws_id, :p_id, 'reality-checker', 'Forensic Reality Checker', 'cli_pipe', NULL, NULL, 'agy', '[\"-p\"]'::jsonb, 'none', '{\"search_tickets\",\"read_ticket\"}', :instructions, 60000)"
            ),
            {"id": agent_id, "ws_id": ws_id, "p_id": p_id, "instructions": instructions},
        )

        # 4. System Default Workflow Hook Template
        sys_tpl_id = uuid.uuid4()
        sys_tpl = DefaultWorkflowHook(
            id=sys_tpl_id,
            scope_kind="system",
            workspace_id=None,
            name="reality-checker-default-gate",
            from_state_name="In Progress",
            to_state_name="Done",
            hook_kind="agent_async",
            sort_rank=100,
            is_enabled=True,
            agent_slug="reality-checker",
            allowed_mutable_fields=["labels"],
            failure_policy="fail_closed",
            timeout_ms=60000,
            max_rework_attempts=3,
        )
        s.add(sys_tpl)

        # 5. Workspace Default Workflow Hook Template
        ws_tpl_id = uuid.uuid4()
        ws_tpl = DefaultWorkflowHook(
            id=ws_tpl_id,
            scope_kind="workspace",
            workspace_id=ws_id,
            name="ws-qa-validator",
            from_state_name="In QA",
            to_state_name="Done",
            hook_kind="wasm_sync",
            sort_rank=50,
            is_enabled=True,
            allowed_mutable_fields=[],
            failure_policy="fail_open_warn",
            timeout_ms=None,
            max_rework_attempts=3,
        )
        s.add(ws_tpl)
        await s.flush()

        # 6. Project PROJ
        reg_row = await s.execute(
            text("SELECT register_object('project'::object_kind, :ws_id, NULL, 'PROJ', 'Core Platform', :p_id)"),
            {"ws_id": ws_id, "p_id": p_id},
        )
        proj_id = reg_row.scalar_one()
        await s.execute(
            text(
                "INSERT INTO projects (id, workspace_id, identifier, name, modules_enabled) "
                "VALUES (:id, :ws_id, 'PROJ', 'Core Platform', false)"
            ),
            {"id": proj_id, "ws_id": ws_id},
        )

        # 7. Workflow States
        existing_states = (
            await s.execute(
                text("SELECT id, name FROM workflow_states WHERE project_id = :p_id"),
                {"p_id": proj_id},
            )
        ).fetchall()
        state_ids = {row[1]: row[0] for row in existing_states}

        states_to_seed = [
            ("Backlog", "backlog", "#94a3b8", 10),
            ("In Progress", "started", "#3b82f6", 20),
            ("In QA", "started", "#8b5cf6", 30),
            ("Done", "completed", "#22c55e", 40),
        ]
        for sname, sgroup, scolor, sorder in states_to_seed:
            if sname not in state_ids:
                sid = uuid.uuid4()
                state_ids[sname] = sid
                await s.execute(
                    text(
                        "INSERT INTO workflow_states (id, workspace_id, project_id, name, state_group, color_hex, sort_order) "
                        "VALUES (:id, :ws_id, :p_id, :name, :sgroup, :scolor, :sorder)"
                    ),
                    {
                        "id": sid,
                        "ws_id": ws_id,
                        "p_id": proj_id,
                        "name": sname,
                        "sgroup": sgroup,
                        "scolor": scolor,
                        "sorder": sorder,
                    },
                )

        # 8. Role Bindings
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

        # 9. Inherited Workflow Transition Hook on PROJ
        msha = compute_hook_manifest_sha256(
            from_state_id=state_ids["In Progress"],
            to_state_id=state_ids["Done"],
            hook_kind="agent_interceptor",
            wasm_module_sha256=None,
            agent_definition_id=agent_id,
            allowed_mutable_fields=["labels"],
            failure_policy="fail_closed",
        )
        hook = WorkflowTransitionHook(
            workspace_id=ws_id,
            project_id=proj_id,
            name="reality-checker-default-gate",
            from_state_id=state_ids["In Progress"],
            to_state_id=state_ids["Done"],
            hook_kind="agent_interceptor",
            sort_rank="0|hzzzzz:",
            is_enabled=True,
            agent_definition_id=agent_id,
            manifest_sha256=msha,
            allowed_mutable_fields=["labels"],
            failure_policy="fail_closed",
            timeout_ms=60000,
            inherited_from_template_id=sys_tpl_id,
        )
        s.add(hook)
        await s.flush()

        # 10. TOTP Setup
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

        # 11. Issue AAL2 Session
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
    env["KAN438_PORT"] = str(PORT)
    env["KAN438_COOKIE"] = seed_info["cookie_val"]
    env["KAN438_CSRF"] = seed_info["csrf_token"]

    uv_log = open("/tmp/uvicorn_kan438.log", "w")
    print(f"[KAN-438] Spawning temporary Kanban server on 127.0.0.1:{PORT}...")
    proc = subprocess.Popen(
        [
            sys.executable,
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
        print(f"[KAN-438] Waiting for server on http://127.0.0.1:{PORT} to be ready...")
        ready = False
        for _ in range(40):
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/api/v1/health", timeout=1) as resp:
                    if resp.status in (200, 302, 404):
                        ready = True
                        break
            except Exception:
                time.sleep(0.5)

        if not ready:
            print("[KAN-438] Server failed to become ready. Logs:")
            with open("/tmp/uvicorn_kan438.log") as f:
                print(f.read())
            raise RuntimeError(f"Server on port {PORT} failed to become ready.")

        print("[KAN-438] Server is ready! Executing Playwright capture...")
        subprocess.run(
            ["node", "scripts/capture_kan438_screenshots.mjs"],
            env=env,
            check=True,
        )
        print("[KAN-438] Screenshots captured successfully!")
    finally:
        print("[KAN-438] Terminating temporary server cleanly...")
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        uv_log.close()
        print("[KAN-438] Teardown complete.")


if __name__ == "__main__":
    main()
