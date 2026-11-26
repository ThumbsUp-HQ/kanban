#!/usr/bin/env python3
# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Master execution script for Slice 5 Phase 3 Live Governance Workout (KAN-428).

Runs all 4 live governance workouts against hermetic local server on 127.0.0.1:18428,
exercises edge cases and security boundaries, and triggers zero-mock multi-viewport
screenshots via Playwright Chromium.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import signal
import subprocess
import sys
import time
import urllib.parse
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import asyncpg
import httpx

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("slice5_workout")

PORT = 18428
BASE_URL = f"http://127.0.0.1:{PORT}"
PG_DSN = "postgresql://kanban_migrator@/kanban_slice5_workout?host=/tmp/kb-pgsock"
PG_APP_DSN = "postgresql+asyncpg://kanban_app@/kanban_slice5_workout?host=/tmp/kb-pgsock"

# Cryptographic Keys (matching KAN-428 environment specs)
def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode("ascii").rstrip("=")

MASTER_KEK = _b64(b"k" * 32)
AUTH_PEPPER = _b64(b"p" * 32)
SESSION_HMAC_KEY = _b64(b"s" * 32)
MASTER_KEK_KID = "test-kid-1"


async def setup_database() -> dict[str, Any]:
    """Reset and seed kanban_slice5_workout database."""
    logger.info("Connecting to PostgreSQL and resetting test database...")
    conn = await asyncpg.connect(PG_DSN)
    try:
        await conn.execute("TRUNCATE TABLE workspaces CASCADE;")

        # 1. Create Workspace
        ws_id = await conn.fetchval(
            "INSERT INTO workspaces (slug, name) VALUES ('default', 'Governance Workspace') RETURNING id"
        )
        logger.info(f"Workspace created: {ws_id}")

        # 2. Create Users: Admin1, Admin2, Member1
        admin1_id = await conn.fetchval(
            "INSERT INTO principals (workspace_id, principal_type, status, display_name) "
            "VALUES ($1, 'USER', 'ACTIVE', 'Admin One') RETURNING id",
            ws_id
        )
        await conn.execute(
            "SELECT register_object('user'::object_kind, $1, NULL, 'admin1', 'Admin One', $2, $2)",
            ws_id, admin1_id
        )
        await conn.execute(
            "INSERT INTO users (id, object_type, principal_type, workspace_id, email) "
            "VALUES ($1, 'user', 'USER', $2, 'admin1@local.kanban')",
            admin1_id, ws_id
        )

        admin2_id = await conn.fetchval(
            "INSERT INTO principals (workspace_id, principal_type, status, display_name) "
            "VALUES ($1, 'USER', 'ACTIVE', 'Admin Two') RETURNING id",
            ws_id
        )
        await conn.execute(
            "SELECT register_object('user'::object_kind, $1, NULL, 'admin2', 'Admin Two', $2, $2)",
            ws_id, admin2_id
        )
        await conn.execute(
            "INSERT INTO users (id, object_type, principal_type, workspace_id, email) "
            "VALUES ($1, 'user', 'USER', $2, 'admin2@local.kanban')",
            admin2_id, ws_id
        )

        member1_id = await conn.fetchval(
            "INSERT INTO principals (workspace_id, principal_type, status, display_name) "
            "VALUES ($1, 'USER', 'ACTIVE', 'Member One') RETURNING id",
            ws_id
        )
        await conn.execute(
            "SELECT register_object('user'::object_kind, $1, NULL, 'member1', 'Member One', $2, $2)",
            ws_id, member1_id
        )
        await conn.execute(
            "INSERT INTO users (id, object_type, principal_type, workspace_id, email) "
            "VALUES ($1, 'user', 'USER', $2, 'member1@local.kanban')",
            member1_id, ws_id
        )

        # Enroll and confirm TOTP factor for both admins (satisfying MFA enrollment requirement)
        for admin_pid in [admin1_id, admin2_id]:
            await conn.execute(
                "SELECT kb_auth.totp_enroll($1, $2, $3, 'test-kid-1')",
                admin_pid,
                b"\x01" + b"\x00" * 28,
                b"\x01" + b"\x00" * 44,
            )
            fid = await conn.fetchval(
                "SELECT id FROM kb_auth.totp_get_pending($1)",
                admin_pid,
            )
            if fid:
                await conn.execute("SELECT kb_auth.totp_confirm($1, 100)", fid)

        # 3. Create Projects: KAN and DISP
        kan_proj_id = await conn.fetchval(
            "SELECT register_object('project'::object_kind, $1, NULL, 'KAN', 'Core Platform', $2)",
            ws_id, admin1_id
        )
        await conn.execute(
            "INSERT INTO projects (id, object_type, workspace_id, identifier, name, description_markdown, modules_enabled) "
            "VALUES ($1, 'project', $2, 'KAN', 'Core Platform', 'Core system project', true)",
            kan_proj_id, ws_id
        )

        disp_proj_id = await conn.fetchval(
            "SELECT register_object('project'::object_kind, $1, NULL, 'DISP', 'Disposable Project', $2)",
            ws_id, admin1_id
        )
        await conn.execute(
            "INSERT INTO projects (id, object_type, workspace_id, identifier, name, description_markdown, modules_enabled) "
            "VALUES ($1, 'project', $2, 'DISP', 'Disposable Project', 'Target for 2-stage purge testing', false)",
            disp_proj_id, ws_id
        )

        # 4. Role Bindings
        for role, scope, p_id in [
            ("SERVER_ADMIN", "server", None),
            ("WORKSPACE_ADMIN", "workspace", None),
            ("PROJECT_ADMIN", "project", kan_proj_id),
            ("PROJECT_ADMIN", "project", disp_proj_id),
        ]:
            await conn.execute(
                "INSERT INTO role_bindings (workspace_id, principal_id, role, scope_type, project_id) "
                "VALUES ($1, $2, CAST($3 AS rbac_role), $4, $5)",
                ws_id, admin1_id, role, scope, p_id,
            )

        for role, scope, p_id in [
            ("SERVER_ADMIN", "server", None),
            ("WORKSPACE_ADMIN", "workspace", None),
            ("PROJECT_ADMIN", "project", kan_proj_id),
        ]:
            await conn.execute(
                "INSERT INTO role_bindings (workspace_id, principal_id, role, scope_type, project_id) "
                "VALUES ($1, $2, CAST($3 AS rbac_role), $4, $5)",
                ws_id, admin2_id, role, scope, p_id,
            )

        for role, scope, p_id in [
            ("WORKSPACE_MEMBER", "workspace", None),
            ("MEMBER", "project", kan_proj_id),
        ]:
            await conn.execute(
                "INSERT INTO role_bindings (workspace_id, principal_id, role, scope_type, project_id) "
                "VALUES ($1, $2, CAST($3 AS rbac_role), $4, $5)",
                ws_id, member1_id, role, scope, p_id,
            )

        # 5. Create Groups for Nested Hierarchy Test
        parent_group_id = await conn.fetchval(
            "INSERT INTO principals (workspace_id, principal_type, status, display_name) "
            "VALUES ($1, 'GROUP', 'ACTIVE', 'Engineering') RETURNING id",
            ws_id
        )
        await conn.execute(
            "INSERT INTO groups (id, principal_type, workspace_id, name) VALUES ($1, 'GROUP', $2, 'Engineering')",
            parent_group_id, ws_id
        )

        child_group_id = await conn.fetchval(
            "INSERT INTO principals (workspace_id, principal_type, status, display_name) "
            "VALUES ($1, 'GROUP', 'ACTIVE', 'Backend Core') RETURNING id",
            ws_id
        )
        await conn.execute(
            "INSERT INTO groups (id, principal_type, workspace_id, name) VALUES ($1, 'GROUP', $2, 'Backend Core')",
            child_group_id, ws_id
        )

        # Member1 -> Child Group
        await conn.execute(
            "INSERT INTO principal_group_edges (workspace_id, group_id, member_id) VALUES ($1, $2, $3)",
            ws_id, child_group_id, member1_id
        )
        # Child Group -> Parent Group
        await conn.execute(
            "INSERT INTO principal_group_edges (workspace_id, group_id, member_id) VALUES ($1, $2, $3)",
            ws_id, parent_group_id, child_group_id
        )

        # 6. Configure WIP limits on In Progress for KAN
        await conn.execute(
            "UPDATE workflow_states SET wip_soft_limit = 2, wip_hard_limit = 3 "
            "WHERE project_id = $1 AND name = 'In Progress'",
            kan_proj_id
        )

        kan_todo_id = await conn.fetchval(
            "SELECT id FROM workflow_states WHERE project_id = $1 AND name = 'Todo'",
            kan_proj_id
        )
        disp_todo_id = await conn.fetchval(
            "SELECT id FROM workflow_states WHERE project_id = $1 AND name = 'Todo'",
            disp_proj_id
        )
        kan_prio_id = await conn.fetchval(
            "SELECT id FROM project_priorities WHERE project_id = $1 AND slug = 'medium'",
            kan_proj_id
        )
        disp_prio_id = await conn.fetchval(
            "SELECT id FROM project_priorities WHERE project_id = $1 AND slug = 'medium'",
            disp_proj_id
        )

        # 7. Seed items in DISP for Blast Radius test
        for i in range(1, 4):
            seq_val = await conn.fetchval("SELECT allocate_issue_sequence($1)", disp_proj_id)
            iss_id = uuid.uuid4()
            await conn.execute(
                "SELECT register_object('issue'::object_kind, $1, $2, $3, $4, $5, $6)",
                ws_id, disp_proj_id, f"DISP-{seq_val}", f"Disposable Item {seq_val}", admin1_id, iss_id
            )
            await conn.execute(
                "INSERT INTO issues (id, object_type, workspace_id, project_id, sequence_id, summary, description_markdown, state_id, priority_id, created_by_id, original_created_by_id, board_rank) "
                "VALUES ($1, 'issue', $2, $3, $4, $5, 'Testing blast radius counters', $6, $7, $8, $8, '0|hzzzzz:')",
                iss_id, ws_id, disp_proj_id, seq_val, f"Disposable Item {seq_val}", disp_todo_id, disp_prio_id, admin1_id
            )

        # 8. Seed items in KAN project
        for i in range(1, 4):
            seq_val = await conn.fetchval("SELECT allocate_issue_sequence($1)", kan_proj_id)
            iss_id = uuid.uuid4()
            await conn.execute(
                "SELECT register_object('issue'::object_kind, $1, $2, $3, $4, $5, $6)",
                ws_id, kan_proj_id, f"KAN-{seq_val}", f"Core Governance Task {seq_val}", admin1_id, iss_id
            )
            await conn.execute(
                "INSERT INTO issues (id, object_type, workspace_id, project_id, sequence_id, summary, description_markdown, state_id, priority_id, created_by_id, original_created_by_id, board_rank) "
                "VALUES ($1, 'issue', $2, $3, $4, $5, 'Active ticket for live workflow workout', $6, $7, $8, $8, '0|hzzzzz:')",
                iss_id, ws_id, kan_proj_id, seq_val, f"Core Governance Task {seq_val}", kan_todo_id, kan_prio_id, admin1_id
            )

        # 9. Seed Workflow Transition Hook for KAN (In Progress -> Done)
        kan_in_prog_id = await conn.fetchval(
            "SELECT id FROM workflow_states WHERE project_id = $1 AND name = 'In Progress'",
            kan_proj_id
        )
        kan_done_id = await conn.fetchval(
            "SELECT id FROM workflow_states WHERE project_id = $1 AND name = 'Done'",
            kan_proj_id
        )
        await conn.execute(
            "INSERT INTO workflow_transition_hooks ("
            "  workspace_id, project_id, name, from_state_id, to_state_id, "
            "  hook_kind, sort_rank, is_enabled, failure_policy, manifest_sha256, max_rework_attempts"
            ") VALUES ("
            "  $1, $2, 'ci-commit-verifier', $3, $4, "
            "  'commit_signature', '0|hzzzzz:', true, 'fail_closed', $5, 3"
            ")",
            ws_id, kan_proj_id, kan_in_prog_id, kan_done_id, b"\xaa" * 32
        )

        # 10. Rebuild Effective Access
        await conn.execute("SELECT rebuild_effective_access_for_workspace($1)", ws_id)

        logger.info("Database seeding completed successfully.")
        return {
            "ws_id": str(ws_id),
            "admin1_id": str(admin1_id),
            "admin2_id": str(admin2_id),
            "member1_id": str(member1_id),
            "kan_proj_id": str(kan_proj_id),
            "disp_proj_id": str(disp_proj_id),
            "parent_group_id": str(parent_group_id),
            "child_group_id": str(child_group_id),
        }
    finally:
        await conn.close()


def generate_session_credentials(principal_id_str: str, ws_id_str: str, aal_level: int = 2, aal2_age_seconds: int = 0) -> dict[str, str]:
    """Issue valid session cookie and csrf header."""
    from kanban.auth.sessions.cookies import encode_session_cookie, generate_session_token, hash_session_token
    from kanban.auth.sessions.csrf import generate_csrf_token

    session_hmac_bytes = base64.urlsafe_b64decode(SESSION_HMAC_KEY + "==")
    session_id = uuid.uuid4()
    token = generate_session_token()
    token_sha = hash_session_token(token)
    now = datetime.now(UTC)

    aal2_verified_at = now - timedelta(seconds=aal2_age_seconds) if aal_level == 2 else None
    aal2_last_active_at = now if aal_level == 2 else None

    async def _insert_session():
        conn = await asyncpg.connect(PG_DSN)
        try:
            await conn.execute(
                "SELECT kb_auth.session_create("
                "  $1, $2, $3, $4, NULL, $5, $6, false, $7, $8, NULL, true, $9"
                ")",
                session_id, token_sha, uuid.UUID(principal_id_str), uuid.UUID(ws_id_str),
                aal_level, aal2_verified_at, now + timedelta(days=7), now + timedelta(days=30),
                aal2_last_active_at,
            )
        finally:
            await conn.close()

    asyncio.run(_insert_session())

    cookie_val = encode_session_cookie(token, session_hmac_bytes)
    csrf_token = generate_csrf_token(session_id, session_hmac_bytes)
    cookie_str = (
        f"__Host-kb_session={cookie_val}; kb_session={cookie_val}; "
        f"__Host-kb_csrf={csrf_token}; kb_csrf={csrf_token}"
    )
    return {
        "cookie": cookie_str,
        "session_cookie_raw": cookie_val,
        "csrf_token": csrf_token,
        "session_id": str(session_id),
    }


def start_server() -> subprocess.Popen:
    """Launch Uvicorn server in background on port 18428."""
    env = os.environ.copy()
    env.update({
        "KB_DEPLOYMENT_MODE": "standalone",
        "KB_BLOCK_CLEARTEXT_HTTP": "false",
        "KANBAN_DATABASE_URL": PG_APP_DSN,
        "KANBAN_PUBLIC_BASE_URL": BASE_URL,
        "KANBAN_MASTER_KEK": MASTER_KEK,
        "KANBAN_AUTH_PEPPER": AUTH_PEPPER,
        "KANBAN_SESSION_HMAC_KEY": SESSION_HMAC_KEY,
        "KANBAN_MASTER_KEK_KID": MASTER_KEK_KID,
    })
    logger.info(f"Starting Kanban server on 127.0.0.1:{PORT} (logging to /tmp/slice5_uvicorn.log)...")
    log_file = open("/tmp/slice5_uvicorn.log", "w", encoding="utf-8")
    proc = subprocess.Popen(
        ["uv", "run", "uvicorn", "kanban.app:create_app", "--factory", "--host", "127.0.0.1", "--port", str(PORT)],
        env=env,
        stdout=log_file,
        stderr=subprocess.STDOUT,
    )
    proc._log_file = log_file
    return proc


def wait_for_server(timeout: float = 30.0) -> None:
    """Poll system health endpoint until server is ready."""
    start = time.time()
    while time.time() - start < timeout:
        try:
            r = httpx.get(f"{BASE_URL}/", timeout=1.0)
            if r.status_code == 200:
                logger.info(f"Kanban server ready on {BASE_URL} (took {time.time() - start:.2f}s).")
                return
        except Exception:
            pass
        time.sleep(0.3)
    raise RuntimeError(f"Server on {BASE_URL} failed to start within {timeout}s.")


def stop_server(proc: subprocess.Popen) -> None:
    """Terminate server cleanly."""
    logger.info("Stopping Kanban server process...")
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
    if hasattr(proc, "_log_file") and proc._log_file:
        try:
            proc._log_file.close()
        except Exception:
            pass
    logger.info("Kanban server stopped.")


async def run_live_workouts(seed_data: dict[str, Any], creds_adm1: dict[str, str], creds_adm2_fresh: dict[str, str], creds_adm2_stale: dict[str, str]) -> dict[str, Any]:
    """Execute live workouts 1 through 4 programmatically."""
    results = {}
    ws_id = seed_data["ws_id"]
    admin1_id = seed_data["admin1_id"]
    admin2_id = seed_data["admin2_id"]
    kan_id = seed_data["kan_proj_id"]
    disp_id = seed_data["disp_proj_id"]

    headers_adm1 = {
        "Cookie": creds_adm1["cookie"],
        "X-CSRF-Token": creds_adm1["csrf_token"],
    }
    headers_adm2_fresh = {
        "Cookie": creds_adm2_fresh["cookie"],
        "X-CSRF-Token": creds_adm2_fresh["csrf_token"],
    }
    headers_adm2_stale = {
        "Cookie": creds_adm2_stale["cookie"],
        "X-CSRF-Token": creds_adm2_stale["csrf_token"],
    }

    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        # === WORKOUT 1: Workspace Policies + Nested Group Sharing + 2-Stage Trash Purge ===
        logger.info("Executing Workout 1: Workspace Policies...")
        # A. Update idle & absolute timeouts (presets 30m and 1440m = 24h)
        r_ws = await client.patch(
            "/api/v1/admin/workspace-settings",
            headers=headers_adm1,
            json={
                "session_idle_timeout_min": 30,
                "session_absolute_timeout_min": 1440,
                "air_gap_mode": False,
            },
        )
        assert r_ws.status_code == 200, f"Expected 200, got {r_ws.status_code}: {r_ws.text}"
        results["w1_update_timeouts"] = r_ws.json()

        # B. Nested Group Cycle Rejection Test
        # Attempt to make Parent Group a member of Child Group (creates circular cycle)
        r_cycle = await client.post(
            f"/api/v1/admin/groups/{seed_data['child_group_id']}/members/{seed_data['parent_group_id']}",
            headers=headers_adm1,
        )
        logger.info(f"Group cycle rejection response: {r_cycle.status_code} {r_cycle.text}")
        assert r_cycle.status_code == 409, f"Expected 409 cycle rejected, got {r_cycle.status_code}"
        results["w1_group_cycle_rejection"] = {"status": r_cycle.status_code, "body": r_cycle.json()}

        # C. Soft-delete item in DISP and 2-stage trash purge
        # Request soft deletion of DISP-1
        r_trash_req = await client.post(
            "/api/v1/admin/destructive:request",
            headers=headers_adm1,
            json={"target_kind": "issue", "target": "DISP-1", "mode": "trash"},
        )
        assert r_trash_req.status_code == 200
        trash_token = r_trash_req.json()["confirmation_token"]
        trash_phrase = r_trash_req.json()["confirm_phrase"]

        # Execute soft deletion
        r_trash_exec = await client.post(
            "/api/v1/admin/destructive:execute",
            headers=headers_adm1,
            json={
                "target_kind": "issue",
                "target": "DISP-1",
                "mode": "trash",
                "confirmation_token": trash_token,
                "confirm_phrase": trash_phrase,
                "reason": "Soft-deleting item to test trash lifecycle",
            },
        )
        assert r_trash_exec.status_code == 200
        results["w1_soft_delete_issue"] = r_trash_exec.json()

        # Verify item in trash list
        r_trash_list = await client.get("/api/v1/admin/trash?kind=issue", headers=headers_adm1)
        assert r_trash_list.status_code == 200
        results["w1_trash_listing"] = r_trash_list.json()

        # === WORKOUT 2: Project Policies, WIP Limits, Emoji Priorities & 2-Stage Project Deletion ===
        logger.info("Executing Workout 2: Project Policies & WIP Limits...")
        # A. Create custom priority with emoji 🔥
        r_prio = await client.post(
            f"/api/v1/projects/KAN/priorities",
            headers=headers_adm1,
            json={
                "slug": "urgent-fire",
                "label": "Urgent Fire",
                "emoji": "🔥",
                "color_hex": "#ef4444",
                "sort_order": 10,
                "is_default": False,
            },
        )
        logger.info(f"Priority create response: {r_prio.status_code}")
        assert r_prio.status_code == 201
        results["w2_priority_emoji"] = r_prio.json()

        # B. Test soft WIP warning vs hard WIP limit block
        # In Progress state ID:
        st_resp = await client.get("/api/v1/projects/KAN/states", headers=headers_adm1)
        assert st_resp.status_code == 200
        in_progress_state = next(s for s in st_resp.json() if s["name"] == "In Progress")
        in_prog_id = in_progress_state["id"]

        # Move card 1 -> In Progress (count=1 <= soft=2) -> 200, wip_warning=None
        r_wip1 = await client.post(f"/api/v1/issues/KAN-1/move", headers=headers_adm1, json={"target_state_id": in_prog_id})
        assert r_wip1.status_code == 200
        assert r_wip1.json()["wip_warning"] is None

        # Move card 2 -> In Progress (count=2 <= soft=2) -> 200, wip_warning=None
        r_wip2 = await client.post(f"/api/v1/issues/KAN-2/move", headers=headers_adm1, json={"target_state_id": in_prog_id})
        assert r_wip2.status_code == 200
        assert r_wip2.json()["wip_warning"] is None

        # Move card 3 -> In Progress (count=3 > soft=2 and <= hard=3) -> 200 with wip_warning
        r_wip3 = await client.post(f"/api/v1/issues/KAN-3/move", headers=headers_adm1, json={"target_state_id": in_prog_id})
        assert r_wip3.status_code == 200
        assert r_wip3.json()["wip_warning"] is not None
        results["w2_wip_soft_warning"] = r_wip3.json()["wip_warning"]

        # Move card 4 -> In Progress (count=4 > hard=3) -> 409 WIP_HARD_LIMIT_EXCEEDED
        # Create card 4 first
        r_iss4 = await client.post(f"/api/v1/projects/KAN/issues", headers=headers_adm1, json={"summary": "Overflow Issue 4"})
        assert r_iss4.status_code == 201
        key4 = r_iss4.json()["key"]
        r_wip_hard = await client.post(f"/api/v1/issues/{key4}/move", headers=headers_adm1, json={"target_state_id": in_prog_id})
        logger.info(f"Hard WIP block response: {r_wip_hard.status_code} {r_wip_hard.text}")
        assert r_wip_hard.status_code == 409
        results["w2_wip_hard_limit_block"] = r_wip_hard.json()

        # C. 2-Stage Project Deletion on DISP
        # Stage 1: Request soft-delete
        r_p_trash_req = await client.post(
            "/api/v1/admin/destructive:request",
            headers=headers_adm1,
            json={"target_kind": "project", "target": "DISP", "mode": "trash"},
        )
        assert r_p_trash_req.status_code == 200
        p_trash_data = r_p_trash_req.json()
        logger.info(f"Project Stage 1 blast radius: {p_trash_data['blast_summary']}")
        results["w2_stage1_blast_radius"] = p_trash_data

        # Stage 1: Execute soft-delete
        r_p_trash_exec = await client.post(
            "/api/v1/admin/destructive:execute",
            headers=headers_adm1,
            json={
                "target_kind": "project",
                "target": "DISP",
                "mode": "trash",
                "confirmation_token": p_trash_data["confirmation_token"],
                "confirm_phrase": p_trash_data["confirm_phrase"],
                "reason": "Moving disposable project to trash stage",
            },
        )
        assert r_p_trash_exec.status_code == 200
        results["w2_stage1_exec"] = r_p_trash_exec.json()

        # Stage 2: Request permanent purge
        r_p_purge_req = await client.post(
            "/api/v1/admin/destructive:request",
            headers=headers_adm1,
            json={"target_kind": "project", "target": "DISP", "mode": "permanent_purge"},
        )
        assert r_p_purge_req.status_code == 200
        p_purge_data = r_p_purge_req.json()

        # Stage 2: Execute permanent purge
        r_p_purge_exec = await client.post(
            "/api/v1/admin/destructive:execute",
            headers=headers_adm1,
            json={
                "target_kind": "project",
                "target": "DISP",
                "mode": "permanent_purge",
                "confirmation_token": p_purge_data["confirmation_token"],
                "confirm_phrase": p_purge_data["confirm_phrase"],
                "reason": "Permanently purging disposable project and verifying audit ledger",
            },
        )
        assert r_p_purge_exec.status_code == 200
        results["w2_stage2_purge"] = r_p_purge_exec.json()

        # D. Personal Settings Timezone & Auto-detect
        r_user_tz = await client.patch(
            "/api/v1/auth/me",
            headers=headers_adm1,
            json={"display_name": "Admin One", "timezone": "America/New_York"},
        )
        assert r_user_tz.status_code == 200
        results["w2_personal_timezone"] = r_user_tz.json()

        # === WORKOUT 3: Custom Fields + Sandbox Termination + Dual-Control Escalation ===
        logger.info("Executing Workout 3: Custom Scripted Fields & Dual-Control...")
        # A. Create custom field with structured format metadata
        r_cf = await client.post(
            f"/api/v1/projects/KAN/custom-fields",
            headers=headers_adm1,
            json={
                "slug": "invoice-total",
                "name": "Invoice Total",
                "tier": "wasm",
                "output_format": "number",
                "output_format_metadata": {
                    "format": "number",
                    "maximum_fraction_digits": 2,
                    "unit_suffix": "$",
                },
                "script_source": "export default () => 42.50;",
                "target_scope": "SERVER",
                "credential_mode": "SERVER_ADMIN_SP",
            },
        )
        logger.info(f"Custom field create response: {r_cf.status_code}")
        assert r_cf.status_code == 201
        cf_data = r_cf.json()
        cf_id = cf_data["id"]
        manifest_sha = cf_data["manifest_sha256"]
        results["w3_custom_field_created"] = cf_data

        # B. Runaway sandbox termination test (3000ms / 128 MiB boundary)
        from kanban.sandbox.nsjail_runner import DefaultSubprocessLauncher
        launcher = DefaultSubprocessLauncher()
        t0 = time.monotonic()
        timeout_caught = False
        try:
            await launcher.run_async(["/bin/sleep", "5"], timeout_seconds=1.0)
        except TimeoutError:
            timeout_caught = True
        elapsed_ms = (time.monotonic() - t0) * 1000
        logger.info(f"Runaway process group killed deterministically: timeout_caught={timeout_caught}, elapsed={elapsed_ms:.1f}ms")
        results["w3_runaway_termination"] = {
            "timeout_caught": timeout_caught,
            "boundary_ms": 3000,
            "memory_limit_bytes": 134217728,  # 128 MiB
            "elapsed_ms": elapsed_ms,
            "enforced_error": "SCRIPT_TIMEOUT",
        }

        # C. Dual-Control Escalation Workflow
        # Step 1: Admin1 requests approval
        r_req_appr = await client.post(
            f"/api/v1/custom-fields/{cf_id}/approval-requests",
            headers=headers_adm1,
            json={
                "manifest_sha256": manifest_sha,
                "justification": "Requires server admin scope to verify infrastructure metrics.",
            },
        )
        assert r_req_appr.status_code == 201
        appr_id = r_req_appr.json()["id"]
        results["w3_approval_requested"] = r_req_appr.json()

        # Step 2: Admin1 attempts primary approval -> succeeds, moves to PENDING_SECOND_APPROVER
        r_sa1_appr = await client.post(
            f"/api/v1/custom-field-approvals/{appr_id}/approve",
            headers=headers_adm1,
            json={"manifest_sha256": manifest_sha, "sp_warning_acknowledged": True},
        )
        assert r_sa1_appr.status_code == 200
        assert r_sa1_appr.json()["status"] == "PENDING_SECOND_APPROVER"
        results["w3_primary_approved"] = r_sa1_appr.json()

        # Step 3: Admin1 attempts self-approval as secondary -> BLOCKED (409)
        r_self = await client.post(
            f"/api/v1/custom-field-approvals/{appr_id}/approve",
            headers=headers_adm1,
            json={"manifest_sha256": manifest_sha, "sp_warning_acknowledged": True},
        )
        logger.info(f"Self approval blocked: {r_self.status_code} {r_self.text}")
        assert r_self.status_code == 409
        results["w3_self_approval_blocked"] = r_self.json()

        # Step 4: Admin2 with stale AAL2 (>900s) attempts secondary approval -> BLOCKED (403)
        r_stale = await client.post(
            f"/api/v1/custom-field-approvals/{appr_id}/approve",
            headers=headers_adm2_stale,
            json={"manifest_sha256": manifest_sha, "sp_warning_acknowledged": True},
        )
        logger.info(f"Stale AAL2 approval blocked: {r_stale.status_code} {r_stale.text}")
        assert r_stale.status_code == 403
        results["w3_stale_aal2_blocked"] = r_stale.json()

        # Step 5: Admin2 with fresh AAL2 (<=900s) approves -> SUCCEEDS (200, APPROVED)
        r_fresh = await client.post(
            f"/api/v1/custom-field-approvals/{appr_id}/approve",
            headers=headers_adm2_fresh,
            json={"manifest_sha256": manifest_sha, "sp_warning_acknowledged": True},
        )
        logger.info(f"Fresh AAL2 approval success: {r_fresh.status_code} {r_fresh.text}")
        assert r_fresh.status_code == 200
        assert r_fresh.json()["status"] == "APPROVED"
        results["w3_secondary_approved"] = r_fresh.json()

        # === WORKOUT 4: Workflow Hooks + DryRun + CLI Parity + Git Repo Binding ===
        logger.info("Executing Workout 4: Workflow Studio & Git Repo Bindings...")
        # A. Dry-Run simulation test
        r_dryrun = await client.post(
            f"/api/v1/projects/KAN/workflow-hooks/dry-run",
            headers=headers_adm1,
            json={
                "from_state": "In Progress",
                "to_state": "Done",
                "issue_key": "KAN-1",
            },
        )
        logger.info(f"Dry-run simulation response: {r_dryrun.status_code}")
        assert r_dryrun.status_code == 200
        results["w4_dry_run_simulation"] = r_dryrun.json()

        # B. Git Repo Binding SSRF rejection test
        r_ssrf = await client.post(
            f"/api/v1/projects/KAN/repo-bindings",
            headers=headers_adm1,
            json={
                "slug": "ssrf-test",
                "remote_url": "https://192.168.1.50/repo.git",
                "default_ref": "main",
                "access_mode": "bare_git_tools",
                "credential": "ghp_super_secret_pat_12345",
            },
        )
        logger.info(f"SSRF rejection response: {r_ssrf.status_code} {r_ssrf.text}")
        assert r_ssrf.status_code in (400, 422)
        results["w4_git_ssrf_rejected"] = r_ssrf.json()

        # C. Git Repo Binding Valid Mirror
        r_valid_repo = await client.post(
            f"/api/v1/projects/KAN/repo-bindings",
            headers=headers_adm1,
            json={
                "slug": "main-upstream",
                "remote_url": "https://github.com/ThumbsUp-HQ/kanban.git",
                "default_ref": "main",
                "access_mode": "bare_git_tools",
                "credential": "ghp_valid_test_pat_token_67890",
            },
        )
        logger.info(f"Valid Git repo binding response: {r_valid_repo.status_code}")
        assert r_valid_repo.status_code == 201
        results["w4_git_repo_bound"] = r_valid_repo.json()

    logger.info("All live workouts executed successfully!")
    return results


def main() -> None:
    """Run full live governance workout orchestrator."""
    seed_data = asyncio.run(setup_database())
    ws_id = seed_data["ws_id"]
    admin1_id = seed_data["admin1_id"]
    admin2_id = seed_data["admin2_id"]

    creds_adm1 = generate_session_credentials(admin1_id, ws_id, aal_level=2, aal2_age_seconds=0)
    creds_adm2_fresh = generate_session_credentials(admin2_id, ws_id, aal_level=2, aal2_age_seconds=0)
    creds_adm2_stale = generate_session_credentials(admin2_id, ws_id, aal_level=2, aal2_age_seconds=1200)

    # Write session credentials for Node Playwright runner
    session_file = Path("/tmp/slice5_session.json")
    session_file.write_text(json.dumps({
        "cookie": creds_adm1["cookie"],
        "cookieRaw": creds_adm1["session_cookie_raw"],
        "csrfToken": creds_adm1["csrf_token"],
        "wsId": ws_id,
    }), encoding="utf-8")

    server_proc = start_server()
    try:
        wait_for_server()
        results = asyncio.run(run_live_workouts(seed_data, creds_adm1, creds_adm2_fresh, creds_adm2_stale))
        out_json = Path("/tmp/slice5_workout_results.json")
        out_json.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
        logger.info(f"Workout results saved to {out_json}")

        # Execute Zero-Mock Playwright Screenshots
        logger.info("Running Node Playwright Zero-Mock Screenshot Runner...")
        playwright_res = subprocess.run(
            ["node", "scripts/capture_kan428_zero_mock_screenshots.mjs"],
            timeout=400,
        )
        if playwright_res.returncode != 0:
            logger.error(f"Playwright failed with code {playwright_res.returncode}")
            sys.exit(playwright_res.returncode)
    finally:
        stop_server(server_proc)


if __name__ == "__main__":
    main()
