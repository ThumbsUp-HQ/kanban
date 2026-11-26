# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Full automated live workout runner for KAN-413.

Executes Workouts 1-4 against real local Kanban server and companion on 127.0.0.1.
Zero mutations on k.hackedyour.info / 192.168.1.101 / inferrence1.
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.parse
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

# Setup test environment variables
os.environ["KANBAN_MASTER_KEK"] = base64.urlsafe_b64encode(b"m" * 32).decode()
os.environ["KANBAN_AUTH_PEPPER"] = base64.urlsafe_b64encode(b"p" * 32).decode()
os.environ["KANBAN_SESSION_HMAC_KEY"] = base64.urlsafe_b64encode(b"s" * 32).decode()
os.environ["KB_TEST_PGHOST"] = "/tmp/kb-pgsock-kan413"

from database.models.ai import AIProviderConfig, AITokenLedger
from database.models.principals import RoleBinding
from database.models.remote_runner import RemoteRunner
from database.models.workspace_settings import WorkspaceSettings
from database.testing.pg_harness import build_dsn
from kanban.app import create_app
from kanban.auth.sessions.service import SessionService
from kanban.runners.hub import (
    ChallengeHelloFrame,
    ChallengeResponseFrame,
    HelloAckFrame,
    HelloFrame,
)
from kanban.security.keys import load_key_material
from kanban.security.scrubber import scrub_text
from kanban.settings import Settings
from kanban.tests.security.helpers import (
    add_role_binding,
    create_project,
    create_registered_object,
    create_user,
    create_workspace,
    rebuild_era,
)

SERVER_PORT = 18413
COMPANION_PORT = 11435
SERVER_URL = f"http://127.0.0.1:{SERVER_PORT}"
COMPANION_URL = f"http://127.0.0.1:{COMPANION_PORT}"
PG_SOCKET = "/tmp/kb-pgsock-kan413"
DB_NAME = "kanban_test"

workout_evidence: dict[str, Any] = {}

def log_section(title: str) -> None:
    print(f"\n{'='*70}\n[KAN-413 WORKOUT] {title}\n{'='*70}", flush=True)

async def setup_database() -> dict[str, Any]:
    log_section("Initializing Clean Test Database on kan413-pg-test-1")
    # Reset kanban_test from kanban_template
    subprocess.run(["docker", "exec", "kan413-pg-test-1", "psql", "-U", "kanban_test", "-d", "postgres", "-c", "DROP DATABASE IF EXISTS kanban_test;"], check=True, stdout=subprocess.DEVNULL)
    subprocess.run(["docker", "exec", "kan413-pg-test-1", "psql", "-U", "kanban_test", "-d", "postgres", "-c", "CREATE DATABASE kanban_test TEMPLATE kanban_template;"], check=True, stdout=subprocess.DEVNULL)
    dsn = build_dsn(database=DB_NAME, host=PG_SOCKET, user="kanban_migrator")
    engine = create_async_engine(dsn)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        ws_id = await create_workspace(session, slug="kanban", name="Kanban Workout Workspace")
        
        # 1. Server Admin + Workspace Admin user
        admin_id = await create_user(
            session, ws_id, handle="workout-admin", display_name="Workout Admin", email="admin@kanban.local"
        )
        await add_role_binding(session, ws_id, admin_id, "SERVER_ADMIN", scope_type="server")
        await add_role_binding(session, ws_id, admin_id, "WORKSPACE_ADMIN", scope_type="workspace")

        # 2. Project 1 and Project 2
        proj1_id = await create_project(session, ws_id, identifier="PRJA", name="Project Alpha", created_by_id=admin_id)
        proj2_id = await create_project(session, ws_id, identifier="PRJB", name="Project Beta", created_by_id=admin_id)
        await add_role_binding(session, ws_id, admin_id, "PROJECT_ADMIN", scope_type="project", project_id=proj1_id)
        await add_role_binding(session, ws_id, admin_id, "PROJECT_ADMIN", scope_type="project", project_id=proj2_id)

        # 3. Project Admin user for Project Alpha only (for cross-project RLS isolation testing)
        proj_user_id = await create_user(
            session, ws_id, handle="proj-admin-alpha", display_name="Alpha Admin", email="alpha@kanban.local"
        )
        await add_role_binding(session, ws_id, proj_user_id, "PROJECT_ADMIN", scope_type="project", project_id=proj1_id)

        # 3b. Seed active MFA TOTP factors so require_admin_aal2 succeeds
        await session.execute(
            text(
                "INSERT INTO totp_factors (principal_id, status, encrypted_secret_blob, wrapped_dek, dek_kid) "
                "VALUES (:p_admin, 'ACTIVE', '\\x00'::bytea, '\\x00'::bytea, 'kek-v1'), "
                "       (:p_proj, 'ACTIVE', '\\x00'::bytea, '\\x00'::bytea, 'kek-v1')"
            ),
            {"p_admin": admin_id, "p_proj": proj_user_id},
        )

        # 4. Workspace settings are auto-created by trigger on workspaces insert

        # 5. Create a sticky note for sticky-to-doc synthesis test
        sticky_obj_id = await create_registered_object(
            session, ws_id, kind="sticky", key="STK-1", title="AI Incident Playbook", project_id=proj1_id, created_by_id=admin_id
        )
        await session.execute(
            text(
                "INSERT INTO stickies (id, object_type, workspace_id, project_id, body_markdown, color_token, sort_rank, provenance_tier) "
                "VALUES (:id, 'sticky', :ws_id, :proj_id, :content, 'amber', 'a0', 'trusted_member')"
            ),
            {
                "id": sticky_obj_id,
                "ws_id": ws_id,
                "proj_id": proj1_id,
                "content": "# Incident Response Spec\n\n1. Detect failure within 500ms.\n2. Fall back to secondary AI provider.\n3. Log forensic audit trail."
            }
        )

        await rebuild_era(session, ws_id)

        # Create sessions
        km = load_key_material()
        svc = SessionService(km.session_hmac_key)
        admin_session = await svc.create_after_login(
            session, principal_id=admin_id, workspace_id=ws_id, aal_level=2, mfa_pending=False, remember_me=True
        )
        proj_session = await svc.create_after_login(
            session, principal_id=proj_user_id, workspace_id=ws_id, aal_level=2, mfa_pending=False, remember_me=True
        )
        await session.commit()

    print(f"Database seeded: workspace_id={ws_id}, admin_id={admin_id}, proj1={proj1_id}, proj2={proj2_id}")
    return {
        "workspace_id": ws_id,
        "admin_id": admin_id,
        "proj1_id": proj1_id,
        "proj2_id": proj2_id,
        "proj_user_id": proj_user_id,
        "sticky_id": sticky_obj_id,
        "admin_cookie": admin_session.cookie_val,
        "admin_csrf": admin_session.csrf_token,
        "proj_cookie": proj_session.cookie_val,
        "proj_csrf": proj_session.csrf_token,
        "async_session": async_session,
        "engine": engine,
    }

async def run_workouts() -> None:
    db_ctx = await setup_database()
    ws_id = str(db_ctx["workspace_id"])
    admin_cookie = db_ctx["admin_cookie"]
    admin_csrf = db_ctx["admin_csrf"]
    proj_cookie = db_ctx["proj_cookie"]
    proj_csrf = db_ctx["proj_csrf"]

    # Start companion server
    log_section("Starting AI Companion on 127.0.0.1:11435")
    companion_proc = subprocess.Popen(
        [sys.executable, "scripts/kan413_ai_companion.py", str(COMPANION_PORT)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    time.sleep(1)

    # Start Uvicorn Kanban server
    log_section("Starting Local Kanban Server on 127.0.0.1:18413")
    server_env = os.environ.copy()
    server_env["KB_DEPLOYMENT_MODE"] = "standalone"
    server_env["KB_PUBLIC_BASE_URL"] = SERVER_URL
    server_env["KB_BLOCK_CLEARTEXT_HTTP"] = "false"
    server_env["KB_WEB_DIST"] = "kanban/web/dist"
    server_env["KB_DATABASE_URL"] = f"postgresql+asyncpg://kanban_app@/{DB_NAME}?host={PG_SOCKET}"
    server_env["PYTHONPATH"] = "."

    server_log = open("/tmp/kan413_server.log", "w")
    server_proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "scripts.kan413_app:create_app",
            "--factory",
            "--host",
            "127.0.0.1",
            "--port",
            str(SERVER_PORT),
            "--log-level",
            "info",
        ],
        env=server_env,
        stdout=server_log,
        stderr=subprocess.STDOUT,
    )

    workout_transcript_lines: list[str] = []

    def make_logging_client(
        base_url: str, cookies: dict[str, str], headers: dict[str, str], label: str = "Client"
    ) -> httpx.Client:
        def on_response(response: httpx.Response) -> None:
            try:
                response.read()
                req = response.request
                req_body = req.content.decode("utf-8", errors="replace") if req.content else ""
                resp_body = response.text
                query_str = req.url.query.decode("utf-8") if isinstance(req.url.query, bytes) else (str(req.url.query) if req.url.query else "")
                workout_transcript_lines.append(f"[{label}] >>> {req.method} {req.url.path}{('?' + query_str) if query_str else ''}")
                if req_body:
                    workout_transcript_lines.append(f"Request Body: {req_body}")
                workout_transcript_lines.append(f"[{label}] <<< HTTP {response.status_code}")
                if resp_body:
                    workout_transcript_lines.append(f"Response Body: {resp_body[:1000]}")
                workout_transcript_lines.append("-" * 50)
            except Exception as e:
                workout_transcript_lines.append(f"[{label}] (logging exception: {e})")

        return httpx.Client(
            base_url=base_url,
            cookies=cookies,
            headers=headers,
            timeout=15.0,
            event_hooks={"response": [on_response]},
        )

    # Wait for server ready
    client = make_logging_client(
        base_url=SERVER_URL,
        cookies={"kb_session": admin_cookie, "kb_csrf": admin_csrf},
        headers={"X-CSRF-Token": admin_csrf},
        label="ServerAdmin",
    )

    for _ in range(30):
        try:
            r = client.get("/api/v1/auth/session")
            if r.status_code == 200:
                print("Kanban server is UP and responding (200 OK)!")
                break
        except Exception:
            time.sleep(0.5)
    else:
        raise RuntimeError("Kanban server failed to start within 15 seconds")

    try:
        # =========================================================================
        # WORKOUT 1: Provider Creation, Probe, Connection Check & Failover Reorder
        # =========================================================================
        log_section("Workout 1: AI Provider Creation, Probe, Connection Check & Failover")

        # 1.1 Create Ollama Provider
        res_ollama = client.post(
            f"/api/v1/workspaces/{ws_id}/ai-providers",
            json={
                "provider_kind": "ollama",
                "display_name": "Local Ollama Runtime",
                "base_url": COMPANION_URL,
                "model_allowlist": ["llama3.2:latest", "qwen2.5-coder:latest"],
                "residency_tier": "local_only",
                "priority": 1,
            },
        )
        print("1.1 Create Ollama:", res_ollama.status_code, res_ollama.json().get("display_name"))
        assert res_ollama.status_code == 201, res_ollama.text
        ollama_id = res_ollama.json()["id"]

        # 1.2 Create OpenAI-Compatible Provider
        res_openai = client.post(
            f"/api/v1/workspaces/{ws_id}/ai-providers",
            json={
                "provider_kind": "openai",
                "display_name": "OpenAI / OpenAI-Compatible",
                "base_url": f"{COMPANION_URL}/v1",
                "model_allowlist": ["gpt-4o", "gpt-4o-mini"],
                "residency_tier": "local_only",
                "api_key": "sk-mock-openai-workout-key",
                "priority": 2,
            },
        )
        print("1.2 Create OpenAI:", res_openai.status_code, res_openai.json().get("display_name"))
        assert res_openai.status_code == 201, res_openai.text
        openai_id = res_openai.json()["id"]

        # 1.3 Create Gemini Provider (Local test endpoint)
        res_gemini = client.post(
            f"/api/v1/workspaces/{ws_id}/ai-providers",
            json={
                "provider_kind": "gemini",
                "display_name": "Google Gemini Workspace",
                "base_url": COMPANION_URL,
                "model_allowlist": ["gemini-2.5-flash", "gemini-2.5-pro"],
                "residency_tier": "local_only",
                "api_key": "AIzaSyMockGeminiKey",
                "priority": 3,
            },
        )
        print("1.3 Create Gemini:", res_gemini.status_code, res_gemini.json().get("display_name"))
        assert res_gemini.status_code == 201, res_gemini.text
        gemini_id = res_gemini.json()["id"]

        # 1.4 Probe Ollama models
        probe_ollama = client.post(
            f"/api/v1/workspaces/{ws_id}/ai-providers/{ollama_id}/probe-models",
            json={},
        )
        print("1.4 Probe Ollama models:", probe_ollama.status_code, probe_ollama.json())
        assert probe_ollama.status_code == 200
        assert probe_ollama.json()["ok"] is True
        assert "llama3.2:latest" in probe_ollama.json()["models"]

        # 1.5 Test OpenAI connection check
        test_openai = client.post(
            f"/api/v1/workspaces/{ws_id}/ai-providers/{openai_id}/test-connection",
            json={},
        )
        print("1.5 Test OpenAI connection:", test_openai.status_code, test_openai.json())
        assert test_openai.status_code == 200
        assert test_openai.json()["ok"] is True

        # 1.6 Probe Gemini models
        probe_gemini = client.post(
            f"/api/v1/workspaces/{ws_id}/ai-providers/{gemini_id}/probe-models",
            json={},
        )
        print("1.6 Probe Gemini models:", probe_gemini.status_code, probe_gemini.json())
        assert probe_gemini.status_code == 200
        assert probe_gemini.json()["ok"] is True

        # 1.7 Failover Priority Reorder: swap OpenAI (#1) and Ollama (#2)
        reorder_res = client.put(
            f"/api/v1/workspaces/{ws_id}/ai-providers/order",
            json={"ordered_ids": [openai_id, ollama_id, gemini_id]},
        )
        print("1.7 Reorder providers:", reorder_res.status_code, [p["display_name"] for p in reorder_res.json()])
        assert reorder_res.status_code == 200
        reordered = reorder_res.json()
        assert reordered[0]["id"] == openai_id
        assert reordered[1]["id"] == ollama_id

        workout_evidence["workout_1"] = {
            "status": "PASS",
            "ollama_probe": probe_ollama.json(),
            "openai_test": test_openai.json(),
            "gemini_probe": probe_gemini.json(),
            "reorder_ids": [p["id"] for p in reordered],
        }

        # =========================================================================
        # WORKOUT 2: Token Budgets (0 Freeze & 10B Unlimited) + air_gap_mode Cloud Block
        # =========================================================================
        log_section("Workout 2: Monthly Token Budgets (0-Freeze / 10B Unlimited) & Air-Gap Mode")

        # 2.1 Set monthly token budget to 0 (Freeze)
        b_freeze = client.put(
            f"/api/v1/workspaces/{ws_id}/ai-providers/budgets",
            json={
                "provider_config_id": ollama_id,
                "period_kind": "monthly",
                "token_cap": 0,
            },
        )
        print("2.1 Set token budget to 0 (Freeze):", b_freeze.status_code, b_freeze.json())
        assert b_freeze.status_code == 200
        assert b_freeze.json()["token_cap"] == 0

        # Verify budget query
        get_b = client.get(f"/api/v1/workspaces/{ws_id}/ai-providers/budgets?provider_config_id={ollama_id}")
        assert get_b.status_code == 200
        assert get_b.json()[0]["token_cap"] == 0

        # 2.1b Verify live completion/reservation blocked when token_cap=0 (Hard AI Freeze)
        res_sparkle_freeze = client.post(
            "/api/v1/sparkle/complete",
            json={
                "project_id": str(db_ctx["proj1_id"]),
                "surface": "sticky",
                "prefix": "def authenticate(user, password):\n    ",
                "suffix": "\n    return session",
                "client_request_id": str(uuid.uuid4()),
            },
        )
        print("2.1b Sparkle HTTP completion under token_cap=0:", res_sparkle_freeze.status_code, res_sparkle_freeze.text.strip())
        assert res_sparkle_freeze.status_code == 200
        assert '"status": "budget"' in res_sparkle_freeze.text
        assert "event: completion" not in res_sparkle_freeze.text

        from agent.budget import BudgetEnforcer, BudgetExceeded
        async_session = db_ctx["async_session"]
        async with async_session() as session:
            enforcer = BudgetEnforcer(session=session)
            freeze_blocked = False
            try:
                await enforcer.reserve(uuid.UUID(ws_id), None, uuid.UUID(ollama_id), estimate_tokens=100)
            except BudgetExceeded as exc:
                freeze_blocked = True
                print("2.1b Verified token_cap=0 hard freeze blocks reservation cleanly:", str(exc))
                assert "monthly" in str(exc).lower()
            assert freeze_blocked is True, "Expected BudgetExceeded when token_cap=0"

        # 2.1c Verify exhausted monthly cap (tokens_used >= token_cap) halts completions cleanly
        # Set monthly budget to 50 tokens
        b_exhaust_setup = client.put(
            f"/api/v1/workspaces/{ws_id}/ai-providers/budgets",
            json={
                "provider_config_id": ollama_id,
                "period_kind": "monthly",
                "token_cap": 50,
            },
        )
        assert b_exhaust_setup.status_code == 200
        # Exhaust the cap in database
        async with async_session() as session:
            await session.execute(
                text("UPDATE ai_token_ledgers SET tokens_used = 50 WHERE provider_config_id = :cid AND period_kind = 'monthly'"),
                {"cid": uuid.UUID(ollama_id)},
            )
            await session.commit()
            exhausted_blocked = False
            try:
                await enforcer.reserve(uuid.UUID(ws_id), None, uuid.UUID(ollama_id), estimate_tokens=10)
            except BudgetExceeded as exc:
                exhausted_blocked = True
                print("2.1c Verified exhausted cap (tokens_used >= token_cap) halts completions cleanly:", str(exc))
                assert "exceeded" in str(exc).lower()
            assert exhausted_blocked is True, "Expected BudgetExceeded when tokens_used >= token_cap"

        res_sparkle_exhaust = client.post(
            "/api/v1/sparkle/complete",
            json={
                "project_id": str(db_ctx["proj1_id"]),
                "surface": "sticky",
                "prefix": "def authenticate(user, password):\n    ",
                "suffix": "\n    return session",
                "client_request_id": str(uuid.uuid4()),
            },
        )
        print("2.1c Sparkle HTTP completion under exhausted cap:", res_sparkle_exhaust.status_code, res_sparkle_exhaust.text.strip())
        assert res_sparkle_exhaust.status_code == 200
        assert '"status": "budget"' in res_sparkle_exhaust.text
        assert "event: completion" not in res_sparkle_exhaust.text

        # 2.2 Set monthly token budget to 10B (Unlimited Quota)
        b_unlimited = client.put(
            f"/api/v1/workspaces/{ws_id}/ai-providers/budgets",
            json={
                "provider_config_id": ollama_id,
                "period_kind": "monthly",
                "token_cap": 10_000_000_000,
            },
        )
        print("2.2 Set token budget to 10B (Unlimited):", b_unlimited.status_code, b_unlimited.json())
        assert b_unlimited.status_code == 200
        assert b_unlimited.json()["token_cap"] == 10_000_000_000

        # 2.3 Air-Gap Mode: Enable air-gap and verify cloud provider blocked
        # Patch workspace settings to air_gap_mode = True
        patch_ws = client.patch(
            f"/api/v1/workspaces/{ws_id}/settings",
            json={"air_gap_mode": True},
        )
        print("2.3 Enable air-gap mode on workspace:", patch_ws.status_code, patch_ws.json().get("air_gap_mode"))
        assert patch_ws.status_code == 200
        assert patch_ws.json()["air_gap_mode"] is True

        # Attempt to create cloud provider with public egress URL
        cloud_deny = client.post(
            f"/api/v1/workspaces/{ws_id}/ai-providers",
            json={
                "provider_kind": "openai",
                "display_name": "Cloud OpenAI Egress Test",
                "base_url": "https://api.openai.com/v1",
                "model_allowlist": ["gpt-4o"],
                "api_key": "sk-cloud-test-key",
            },
        )
        print("2.4 Air-gap cloud provider creation blocked:", cloud_deny.status_code, cloud_deny.json().get("code"))
        assert cloud_deny.status_code == 409
        assert cloud_deny.json().get("code") == "AIR_GAP_EGRESS_DENIED"

        # Attempt to probe cloud provider with public egress URL
        probe_deny = client.post(
            f"/api/v1/workspaces/{ws_id}/ai-providers/probe-models",
            json={
                "provider_kind": "gemini",
                "base_url": "https://generativelanguage.googleapis.com",
                "api_key": "AIzaSyMockEgressKey",
            },
        )
        print("2.5 Air-gap probe models blocked:", probe_deny.status_code, probe_deny.json().get("error_code"))
        assert probe_deny.status_code == 200
        assert probe_deny.json()["ok"] is False
        assert probe_deny.json()["error_code"] == "AIR_GAP_EGRESS_DENIED"

        # Confirm local Ollama provider probe STILL SUCCEEDS in air-gap mode!
        ollama_local_probe = client.post(
            f"/api/v1/workspaces/{ws_id}/ai-providers/{ollama_id}/probe-models",
            json={},
        )
        print("2.6 Local Ollama allowed under air-gap:", ollama_local_probe.status_code, ollama_local_probe.json().get("ok"))
        assert ollama_local_probe.status_code == 200
        assert ollama_local_probe.json()["ok"] is True

        # Reset air-gap mode for subsequent tests
        client.patch(f"/api/v1/workspaces/{ws_id}/settings", json={"air_gap_mode": False})

        workout_evidence["workout_2"] = {
            "status": "PASS",
            "freeze_cap": b_freeze.json()["token_cap"],
            "unlimited_cap": b_unlimited.json()["token_cap"],
            "air_gap_blocked_code": cloud_deny.json().get("code"),
            "air_gap_probe_error": probe_deny.json().get("error_code"),
            "air_gap_local_allowed": ollama_local_probe.json()["ok"],
        }

        # =========================================================================
        # WORKOUT 3: Autonomous Agent :validate + Sparkle/Sticky Synthesis + Cross-Project RLS
        # =========================================================================
        log_section("Workout 3: AgentStudio :validate, Sparkle, Sticky Synthesis & RLS Isolation")
        proj1_id = db_ctx["proj1_id"]
        proj2_id = db_ctx["proj2_id"]

        # 3.1 Create Agent Definitions: in_app_sdk, cli_pipe, remote_runner
        res_agent1 = client.post(
            "/api/v1/admin/agent-definitions",
            json={
                "slug": "in-app-agent",
                "display_name": "In-App SDK Assistant",
                "harness_kind": "in_app_sdk",
                "provider_kind": "ollama",
                "model_id": "llama3.2:latest",
                "project_id": str(proj1_id),
            },
        )
        print("3.1 Create in_app_sdk agent:", res_agent1.status_code, res_agent1.text)
        assert res_agent1.status_code == 201
        agent1_id = res_agent1.json()["id"]

        res_agent2 = client.post(
            "/api/v1/admin/agent-definitions",
            json={
                "slug": "cli-pipe-agent",
                "display_name": "CLI Pipe Sandboxed Agent",
                "harness_kind": "cli_pipe",
                "cli_binary_allowlist_id": "agy",
                "cli_args": ["-p"],
                "project_id": str(proj1_id),
            },
        )
        print("3.2 Create cli_pipe agent:", res_agent2.status_code, res_agent2.json().get("slug"))
        assert res_agent2.status_code == 201
        agent2_id = res_agent2.json()["id"]

        res_agent3 = client.post(
            "/api/v1/admin/agent-definitions",
            json={
                "slug": "remote-runner-agent",
                "display_name": "mTLS Remote Worker Agent",
                "harness_kind": "remote_runner",
                "remote_runner_pool_slug": "default",
                "project_id": str(proj1_id),
            },
        )
        print("3.3 Create remote_runner agent:", res_agent3.status_code, res_agent3.json().get("slug"))
        assert res_agent3.status_code == 201
        agent3_id = res_agent3.json()["id"]

        # 3.2 Execute :validate on all 3 harnesses
        val1 = client.post(f"/api/v1/admin/agent-definitions/{agent1_id}:validate")
        print("3.4 Validate in_app_sdk:", val1.status_code, val1.json().get("status"), val1.json().get("valid"))
        assert val1.status_code == 200
        assert val1.json()["valid"] is True

        val2 = client.post(f"/api/v1/admin/agent-definitions/{agent2_id}:validate")
        print("3.5 Validate cli_pipe:", val2.status_code, val2.json().get("status"), val2.json().get("valid"))
        assert val2.status_code == 200
        assert val2.json()["valid"] is True

        val3 = client.post(f"/api/v1/admin/agent-definitions/{agent3_id}:validate")
        print("3.6 Validate remote_runner:", val3.status_code, val3.json().get("status"), val3.json().get("valid"))
        assert val3.status_code == 200
        assert val3.json()["valid"] is True

        # 3.3 Sticky -> Doc AI Promotion Preview
        sticky_id = db_ctx["sticky_id"]
        res_promo = client.post(f"/api/v1/stickies/{sticky_id}/promote-preview")
        print("3.7 Sticky-to-Doc promote preview:", res_promo.status_code, json.dumps(res_promo.json(), indent=2)[:300])
        assert res_promo.status_code == 200

        # 3.4 Sparkle FIM Completion Endpoint
        res_sparkle = client.post(
            "/api/v1/sparkle/complete",
            json={
                "project_id": str(proj1_id),
                "surface": "sticky",
                "prefix": "def authenticate(user, password):\n    ",
                "suffix": "\n    return session",
                "client_request_id": str(uuid.uuid4()),
            },
        )
        print("3.8 Sparkle FIM completion status:", res_sparkle.status_code, "Body preview:", res_sparkle.text[:120])
        assert res_sparkle.status_code == 200
        assert "text/event-stream" in res_sparkle.headers.get("content-type", "")
        assert "event: completion" in res_sparkle.text
        assert "event: done" in res_sparkle.text
        assert '"status": "ok"' in res_sparkle.text

        # 3.5 Cross-Project FORCE RLS Isolation:
        # proj-admin-alpha has PROJECT_ADMIN on Project Alpha only.
        # Attempt to patch or delete an agent definition in Project Beta (proj2_id)
        res_agent_beta = client.post(
            "/api/v1/admin/agent-definitions",
            json={
                "slug": "beta-agent",
                "display_name": "Project Beta Isolated Agent",
                "harness_kind": "in_app_sdk",
                "provider_kind": "ollama",
                "model_id": "llama3.2:latest",
                "project_id": str(proj2_id),
            },
        )
        assert res_agent_beta.status_code == 201
        beta_agent_id = res_agent_beta.json()["id"]

        proj_client = make_logging_client(
            base_url=SERVER_URL,
            cookies={"kb_session": proj_cookie, "kb_csrf": proj_csrf},
            headers={"X-CSRF-Token": proj_csrf},
            label="ProjectAdmin",
        )

        # 3.5a Project Admin calls :validate on its own project-scoped agent -> 200 OK valid: True
        res_proj_val = proj_client.post(f"/api/v1/agent-definitions/{agent1_id}:validate")
        print("3.9a Project Admin :validate on project agent:", res_proj_val.status_code, res_proj_val.json().get("valid"))
        assert res_proj_val.status_code == 200
        assert res_proj_val.json()["valid"] is True

        # 3.5b Project Admin calls :validate on cross-project agent in Project Beta (proj2_id) -> 404
        res_proj_val_cross = proj_client.post(f"/api/v1/agent-definitions/{beta_agent_id}:validate")
        print("3.9b Cross-project :validate blocked under RLS:", res_proj_val_cross.status_code)
        assert res_proj_val_cross.status_code in (403, 404)

        cross_patch = proj_client.patch(
            f"/api/v1/admin/agent-definitions/{beta_agent_id}",
            json={"display_name": "Hostile Cross-Project Mutation Attempt"},
        )
        print("3.9c Cross-project RLS isolation check:", cross_patch.status_code, cross_patch.json().get("code", cross_patch.text[:50]))
        assert cross_patch.status_code in (403, 404), f"Expected 403 or 404 under RLS, got {cross_patch.status_code}"

        # 3.6 /llms.txt and Agent Onboarding Preferences
        res_llmstxt = client.get("/llms.txt")
        print("3.10 GET /llms.txt:", res_llmstxt.status_code, f"Length: {len(res_llmstxt.text)} bytes")
        assert res_llmstxt.status_code == 200
        assert "kanban" in res_llmstxt.text.lower()

        # Read onboarding prefs
        get_prefs = client.get("/api/v1/users/me/preferences")
        print("3.11 GET agent onboarding prefs:", get_prefs.status_code, get_prefs.json().get("agent_onboarding_prefs"))
        assert get_prefs.status_code == 200

        # Patch onboarding prefs
        patch_prefs = client.patch(
            "/api/v1/users/me/preferences",
            json={
                "agent_onboarding_prefs": {
                    "custom_notes": "Enforce zero-tolerance security standards and passive forensic verification.",
                    "scope": "local_only",
                    "execution_mode": "swarm",
                    "qa_rigor": "strict_forensic",
                }
            },
        )
        print("3.12 PATCH agent onboarding prefs:", patch_prefs.status_code, patch_prefs.json()["agent_onboarding_prefs"]["qa_rigor"])
        assert patch_prefs.status_code == 200
        assert patch_prefs.json()["agent_onboarding_prefs"]["qa_rigor"] == "strict_forensic"

        workout_evidence["workout_3"] = {
            "status": "PASS",
            "in_app_validate": val1.json()["status"],
            "cli_pipe_validate": val2.json()["status"],
            "remote_runner_validate": val3.json()["status"],
            "sticky_doc_title": str(res_promo.json().get("proposal"))[:50],
            "cross_project_blocked_status": cross_patch.status_code,
            "llms_txt_bytes": len(res_llmstxt.text),
            "qa_rigor": patch_prefs.json()["agent_onboarding_prefs"]["qa_rigor"],
        }

        # =========================================================================
        # WORKOUT 4: Non-Root kanban-agent-runner enroll, mTLS Poll, Heartbeat & Revoke
        # =========================================================================
        log_section("Workout 4: Non-Root Runner Enroll, mTLS Poll/Heartbeat & Cert Revocation")

        # 4.1 Mint single-use runner enrollment token
        res_token = client.post(
            "/api/v1/admin/agent-runners/enrollment-tokens",
            json={"pool_slug": "default", "ttl_seconds": 600},
        )
        print("4.1 Mint enrollment token:", res_token.status_code, res_token.json().get("pool_slug"))
        assert res_token.status_code == 201
        token_data = res_token.json()
        raw_token = token_data["enrollment_token"]
        assert raw_token.startswith("kb_rnr_enroll_")

        # 4.2 Non-Root enrollment into isolated XDG state dir
        state_dir = Path(tempfile.mkdtemp(prefix="kan413-runner-state-"))
        os.chmod(state_dir, 0o700)

        enroll_cmd = [
            "uv",
            "run",
            "--no-sync",
            "kanban-agent-runner",
            "enroll",
            "--server-url",
            SERVER_URL,
            "--token-stdin",
            "--pool",
            "default",
            "--state-dir",
            str(state_dir),
            "--hostname",
            "worker-kan413.internal.test",
        ]
        enroll_proc = subprocess.run(
            enroll_cmd,
            input=raw_token.encode("ascii"),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        print("4.2 CLI runner enroll exit code:", enroll_proc.returncode, enroll_proc.stdout.decode().strip())
        assert enroll_proc.returncode == 0, f"Enroll error: {enroll_proc.stderr.decode()}"

        # Verify permissions: state_dir 0o700, client.key 0o600, ca.pem 0o600, client.crt 0o644
        st_mode = oct(state_dir.stat().st_mode & 0o777)
        key_mode = oct((state_dir / "client.key").stat().st_mode & 0o777)
        ca_mode = oct((state_dir / "ca.pem").stat().st_mode & 0o777)
        crt_mode = oct((state_dir / "client.crt").stat().st_mode & 0o777)
        print(f"4.3 Verified Permissions: dir={st_mode}, key={key_mode}, ca={ca_mode}, crt={crt_mode}")
        assert st_mode == "0o700"
        assert key_mode == "0o600"
        assert ca_mode == "0o600"
        assert crt_mode == "0o644"

        # 4.4 Verify replayed single-use token is rejected (401 Unauthorized)
        replay_state_dir = Path(tempfile.mkdtemp(prefix="kan413-runner-replay-"))
        replay_cmd = list(enroll_cmd)
        replay_cmd[replay_cmd.index(str(state_dir))] = str(replay_state_dir)
        replay_proc = subprocess.run(
            replay_cmd,
            input=raw_token.encode("ascii"),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        print("4.4 Replayed token rejected:", replay_proc.returncode, "Stderr:", replay_proc.stderr.decode().strip())
        assert replay_proc.returncode != 0
        shutil.rmtree(replay_state_dir, ignore_errors=True)

        # 4.4b Verify expired single-use token is rejected (401 / 403)
        res_exp_token = client.post(
            "/api/v1/admin/agent-runners/enrollment-tokens",
            json={"pool_slug": "default", "ttl_seconds": 60},
        )
        assert res_exp_token.status_code == 201
        exp_token_id = res_exp_token.json()["id"]
        exp_token_raw = res_exp_token.json()["enrollment_token"]

        # Force expires_at into the past in database
        async with async_session() as session:
            await session.execute(
                text("UPDATE remote_runner_enrollment_tokens SET expires_at = NOW() - INTERVAL '1 hour' WHERE id = :tid"),
                {"tid": uuid.UUID(exp_token_id)},
            )
            await session.commit()

        # Submit enrollment request with expired token
        from agent.remote_runner.cli import _generate_ecdsa_key_and_csr
        _, expired_csr_pem = _generate_ecdsa_key_and_csr("expired-node.internal.test")
        resp_expired = client.post(
            "/api/v1/agent-runners/enroll",
            json={
                "enrollment_token": exp_token_raw,
                "csr_pem": expired_csr_pem,
                "hostname": "expired-node.internal.test",
            },
        )
        print("4.4b Expired enrollment token rejected:", resp_expired.status_code, resp_expired.json())
        assert resp_expired.status_code in (401, 403)
        assert resp_expired.json().get("code") == "ENROLLMENT_TOKEN_INVALID"

        # Read enrolled runner from database / API
        runners_list = client.get("/api/v1/admin/agent-runners")
        print("4.5 Listed runners count:", len(runners_list.json()), "Status:", runners_list.json()[0]["status"])
        assert len(runners_list.json()) >= 1
        enrolled_runner = runners_list.json()[0]
        runner_id = enrolled_runner["id"]
        assert enrolled_runner["status"] in ("offline", "online")

        # 4.6 mTLS Poll / Heartbeat Simulation
        # Connect WebSocket to /api/v1/agent-runners/ws using client cert
        import websockets
        from kanban.runners.hub import HeartbeatFrame
        client_cert_pem = (state_dir / "client.crt").read_text()
        ws_url = f"ws://127.0.0.1:{SERVER_PORT}/api/v1/agent-runners/ws"

        async def ws_handshake():
            headers = [("X-Client-Cert-Pem", urllib.parse.quote(client_cert_pem))]
            async with websockets.connect(ws_url, additional_headers=headers) as ws:
                # Receive ChallengeHelloFrame
                resp_text = await ws.recv()
                data = json.loads(resp_text)
                challenge = ChallengeHelloFrame.model_validate(data)
                
                # Sign challenge with client private key
                cert = x509.load_pem_x509_certificate(client_cert_pem.encode("utf-8"))
                cert_fp = cert.fingerprint(hashes.SHA256()).hex()
                payload = f"kb-runner-pop-v1:{challenge.runner_id}:{challenge.nonce}:{cert_fp}".encode()
                print(f"CLIENT PAYLOAD: {payload!r}")

                key_pem = (state_dir / "client.key").read_bytes()
                from cryptography.hazmat.primitives.serialization import load_pem_private_key
                priv_key = load_pem_private_key(key_pem, password=None)
                from cryptography.hazmat.primitives.asymmetric import ec
                sig = priv_key.sign(payload, ec.ECDSA(hashes.SHA256()))

                resp_frame = ChallengeResponseFrame(
                    signature_b64=base64.b64encode(sig).decode("ascii")
                )
                await ws.send(resp_frame.model_dump_json())

                # Send HelloFrame
                hello_frame = HelloFrame(
                    schema="kb-runner-ws/v1",
                    runner_id=uuid.UUID(runner_id),
                    max_concurrency=1,
                    capabilities={"os": "linux", "arch": "x86_64"},
                )
                await ws.send(hello_frame.model_dump_json(by_alias=True))

                # Receive HelloAckFrame
                ack_text = await ws.recv()
                ack = HelloAckFrame.model_validate_json(ack_text)
                print("4.6 mTLS WebSocket Handshake completed successfully! Ack type:", ack.type)
                
                # Send heartbeat
                hb = HeartbeatFrame(runner_id=uuid.UUID(runner_id))
                await ws.send(hb.model_dump_json())
                await asyncio.sleep(0.1)
                return ack.type

        ack_type = await ws_handshake()
        assert ack_type == "hello_ack"

        # Verify last_heartbeat_at was updated
        runner_check = client.get("/api/v1/admin/agent-runners")
        updated_runner = next(r for r in runner_check.json() if r["id"] == runner_id)
        assert updated_runner["last_heartbeat_at"] is not None

        # 4.7 Runner Revocation
        res_revoke = client.post(f"/api/v1/admin/agent-runners/{runner_id}:revoke")
        print("4.7 Revoked runner:", res_revoke.status_code, res_revoke.json().get("status"))
        assert res_revoke.status_code == 200
        assert res_revoke.json()["status"] == "revoked"

        # Verify immediate rejection on re-connect with revoked cert
        async def ws_reconnect_revoked():
            headers = [("X-Client-Cert-Pem", urllib.parse.quote(client_cert_pem))]
            try:
                async with websockets.connect(ws_url, additional_headers=headers) as ws:
                    await ws.recv()
                    return False
            except Exception as e:
                print("4.8 Revoked runner connection immediately rejected:", type(e).__name__, str(e))
                return True

        rejected = await ws_reconnect_revoked()
        assert rejected is True

        workout_evidence["workout_4"] = {
            "status": "PASS",
            "token_prefix": raw_token[:14],
            "dir_permissions": st_mode,
            "key_permissions": key_mode,
            "handshake_ack": ack_type,
            "revocation_status": res_revoke.json()["status"],
            "reconnect_rejected": rejected,
        }

        # Clean up temp runner state
        shutil.rmtree(state_dir, ignore_errors=True)

        print("\nALL 4 WORKOUT PHASES COMPLETED WITH 100% SUCCESS!")

        # Write verbatim secret-scrubbed workout transcript
        log_section("Writing Verbatim Secret-Scrubbed Workout Transcript")
        raw_transcript = "\n".join(workout_transcript_lines)
        scrubbed_transcript = scrub_text(raw_transcript)
        # Scrub mock keys, CSRF tokens, and runner enrollment tokens
        scrubbed_transcript = re.sub(r"kb_rnr_enroll_[A-Za-z0-9_-]+", "[REDACTED:KANBAN_KEY]", scrubbed_transcript)
        scrubbed_transcript = re.sub(r"sk-(?:proj-)?[A-Za-z0-9_-]{10,}", "[REDACTED:API_KEY]", scrubbed_transcript)
        scrubbed_transcript = re.sub(r"AIza[A-Za-z0-9_-]{10,}", "[REDACTED:GOOGLE_KEY]", scrubbed_transcript)
        if admin_csrf:
            scrubbed_transcript = scrubbed_transcript.replace(admin_csrf, "[REDACTED:CSRF_TOKEN]")
        if proj_csrf:
            scrubbed_transcript = scrubbed_transcript.replace(proj_csrf, "[REDACTED:CSRF_TOKEN]")
        scrubbed_transcript = re.sub(r"(?i)(csrf[_-]?token['\":\s=]+)[A-Za-z0-9_-]{10,}", r"\1[REDACTED:CSRF_TOKEN]", scrubbed_transcript)
        transcript_path = Path("docs/qa/KAN-413/workout-transcript.txt")
        transcript_path.parent.mkdir(parents=True, exist_ok=True)
        transcript_path.write_text(scrubbed_transcript, encoding="utf-8")
        print(f"Scrubbed workout transcript saved to {transcript_path} ({len(scrubbed_transcript)} bytes)")

        # Capture Zero-Mock Playwright Multi-Viewport Screenshots
        log_section("Capturing Zero-Mock Playwright Multi-Viewport Screenshots")
        out_dir_1 = str(Path("docs/workouts/slice-2-ai-agents-runners/screenshots").resolve())
        out_dir_2 = str(Path("docs/qa/KAN-413/screenshots").resolve())

        screenshot_cmd = [
            "node",
            "scripts/capture_kan413_screenshots.mjs",
            SERVER_URL,
            admin_cookie,
            admin_csrf,
            out_dir_1,
            out_dir_2,
        ]
        sc_res = subprocess.run(screenshot_cmd, check=False)
        assert sc_res.returncode == 0, f"Screenshot capture failed with code {sc_res.returncode}"

    finally:
        client.close()
        # Shutdown server & companion
        server_proc.terminate()
        companion_proc.terminate()
        server_proc.wait(timeout=5)
        companion_proc.wait(timeout=5)
        if "engine" in db_ctx:
            await db_ctx["engine"].dispose()

if __name__ == "__main__":
    asyncio.run(run_workouts())
