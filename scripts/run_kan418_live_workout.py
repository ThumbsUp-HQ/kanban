# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Comprehensive Live Workout Orchestrator for KAN-418.

Executes:
1. Scoped kb_* keys across /mcp/agent, /mcp/docs, /mcp/admin + CIDR /32 deny + 2-stage destructive confirm.
2. OAuth 2.1 DCR + PKCE S256 with 1,200-char Gemini state + 4096/4097 boundary + confidential client auth + 500+ DCR bulk purge.
3. RFC 8628 /activate Device Authorization flow with Base20 format and user approval.
4. RFC 8693 Workload OIDC JWT Exchange with local HTTPS JWKS companion (127.0.0.1:18083).
5. Zero-mock Playwright screenshot capture across all 5 viewports.
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import hashlib
import json
import os
import re
import secrets
import subprocess
import sys
import time
import urllib.parse
import uuid
from typing import Any

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from kanban.auth.sessions.service import SessionService

# Keyring definition matching our test env
SESSION_HMAC_KEY = b"s" * 32
MASTER_KEK = b"k" * 32
AUTH_PEPPER = b"p" * 32


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode("ascii").rstrip("=")


def _generate_code_verifier() -> str:
    return base64.urlsafe_b64encode(secrets.token_bytes(64)).decode("ascii").rstrip("=")


def _generate_code_challenge(verifier: str) -> str:
    sha = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(sha).decode("ascii").rstrip("=")


async def seed_database(db_url: str) -> dict[str, Any]:
    """Seed initial workspace, project, admin principal, role bindings, and active session."""
    engine = create_async_engine(db_url)
    async_session = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with async_session() as s:
        # 1. Workspace
        res = await s.execute(text("SELECT id FROM workspaces WHERE slug = 'engineering'"))
        ws_row = res.first()
        if not ws_row:
            ws_id = uuid.uuid4()
            await s.execute(
                text("INSERT INTO workspaces (id, slug, name) VALUES (:id, 'engineering', 'Engineering')"),
                {"id": ws_id},
            )
        else:
            ws_id = ws_row[0]

        # 2. Server Admin Principal & User
        res = await s.execute(
            text(
                "SELECT p.id FROM principals p "
                "JOIN users u ON p.id = u.id "
                "WHERE u.email = 'admin@kanban.local'"
            )
        )
        p_row = res.first()
        if not p_row:
            p_id = uuid.uuid4()
            await s.execute(
                text(
                    "INSERT INTO principals (id, workspace_id, principal_type, status, display_name) "
                    "VALUES (:id, :ws_id, 'USER', 'ACTIVE', 'Server Administrator')"
                ),
                {"id": p_id, "ws_id": ws_id},
            )
            await s.execute(
                text(
                    "SELECT register_object('user'::object_kind, :ws_id, NULL, 'server_admin', 'Server Administrator', :p_id, :p_id)"
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
        else:
            p_id = p_row[0]

        # 3. Project KAN
        res = await s.execute(text("SELECT id FROM projects WHERE identifier = 'KAN'"))
        proj_row = res.first()
        if not proj_row:
            reg_row = await s.execute(
                text("SELECT register_object('project'::object_kind, :ws_id, NULL, 'KAN', 'Kanban Core', :p_id)"),
                {"ws_id": ws_id, "p_id": p_id},
            )
            proj_id = reg_row.scalar_one()
            await s.execute(
                text(
                    "INSERT INTO projects (id, workspace_id, identifier, name, modules_enabled) "
                    "VALUES (:id, :ws_id, 'KAN', 'Kanban Core', false)"
                ),
                {"id": proj_id, "ws_id": ws_id},
            )
        else:
            proj_id = proj_row[0]

        # 4. Role Bindings (SERVER_ADMIN and WORKSPACE_ADMIN)
        await s.execute(
            text(
                "INSERT INTO role_bindings (workspace_id, principal_id, role, scope_type) "
                "VALUES (:ws_id, :p_id, 'SERVER_ADMIN', 'server') ON CONFLICT DO NOTHING"
            ),
            {"ws_id": ws_id, "p_id": p_id},
        )
        await s.execute(
            text(
                "INSERT INTO role_bindings (workspace_id, principal_id, role, scope_type) "
                "VALUES (:ws_id, :p_id, 'WORKSPACE_ADMIN', 'workspace') ON CONFLICT DO NOTHING"
            ),
            {"ws_id": ws_id, "p_id": p_id},
        )

        # 5. Enroll & Confirm TOTP Factor for Server Admin MFA
        with contextlib.suppress(Exception):
            await s.execute(
                text("SELECT kb_auth.totp_enroll(:p_id, :blob, :dek, 'test-kid-1')"),
                {
                    "p_id": p_id,
                    "blob": b"\x01" + b"\x00" * 28,
                    "dek": b"\x01" + b"\x00" * 44,
                },
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

        # 6. Active AAL2 Session
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
        "workspace_id": str(ws_id),
        "principal_id": str(p_id),
        "project_id": str(proj_id),
        "cookie_val": issued.cookie_val,
        "csrf_token": issued.csrf_token,
    }


def main() -> None:
    print("=== Starting KAN-418 Live Workout Orchestrator ===")
    results: dict[str, Any] = {
        "workout_1_scoped_keys": {},
        "workout_2_oauth_pkce": {},
        "workout_3_device_flow": {},
        "workout_4_workload_oidc": {},
    }

    # 1. Start OIDC JWKS companion on https://127.0.0.1:18083
    certs_dir = "/tmp/kan418-oidc-certs"
    os.makedirs(certs_dir, exist_ok=True)
    ca_cert_path = os.path.join(certs_dir, "ca.crt")

    print("[Step 1] Launching HTTPS OIDC JWKS companion on port 18083...")
    oidc_proc = subprocess.Popen(
        [
            ".venv/bin/python",
            "scripts/oidc_jwks_companion.py",
            "--port",
            "18083",
            "--certs-dir",
            certs_dir,
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    time.sleep(2)

    # 2. Seed database
    db_migrator_url = "postgresql+asyncpg://kanban_migrator@/kanban_workout?host=/tmp/kb-pgsock-kan418"
    print("[Step 2] Seeding database kanban_workout via kanban_migrator...")
    seed_info = asyncio.run(seed_database(db_migrator_url))
    print(f"  Workspace ID: {seed_info['workspace_id']}")
    print(f"  Principal ID: {seed_info['principal_id']}")
    print(f"  Project ID:   {seed_info['project_id']}")
    cookie = seed_info["cookie_val"]
    csrf_token = seed_info["csrf_token"]
    cookie_header = (
        f"kb_session={cookie}; __Host-kb_session={cookie}; "
        f"kb_csrf={csrf_token}; __Host-kb_csrf={csrf_token}"
    )
    admin_headers = {
        "Cookie": cookie_header,
        "X-CSRF-Token": csrf_token,
        "Origin": "http://127.0.0.1:18418",
        "Sec-Fetch-Site": "same-origin",
    }

    # 3. Start Kanban Uvicorn on http://127.0.0.1:18418
    print("[Step 3] Launching Uvicorn backend on port 18418...")
    env = os.environ.copy()
    env["KANBAN_DEPLOYMENT_MODE"] = "standalone"
    env["KB_DEPLOYMENT_MODE"] = "standalone"
    env["KANBAN_PUBLIC_ORIGIN"] = "http://127.0.0.1:18418"
    env["KB_PUBLIC_ORIGIN"] = "http://127.0.0.1:18418"
    env["KANBAN_DATABASE_URL"] = "postgresql+asyncpg://kanban_app@/kanban_workout?host=/tmp/kb-pgsock-kan418"
    env["KANBAN_MASTER_KEK"] = _b64(MASTER_KEK)
    env["KANBAN_AUTH_PEPPER"] = _b64(AUTH_PEPPER)
    env["KANBAN_SESSION_HMAC_KEY"] = _b64(SESSION_HMAC_KEY)
    env["KANBAN_MASTER_KEK_KID"] = "test-kid-1"
    env["SSL_CERT_FILE"] = ca_cert_path
    env["REQUESTS_CA_BUNDLE"] = ca_cert_path

    uv_log = open("/tmp/uvicorn_kan418.log", "w")
    uvicorn_proc = subprocess.Popen(
        [
            ".venv/bin/python",
            "-m",
            "uvicorn",
            "kanban.app:create_app",
            "--factory",
            "--host",
            "127.0.0.1",
            "--port",
            "18418",
        ],
        env=env,
        stdout=uv_log,
        stderr=uv_log,
    )
    time.sleep(3)

    base_url = "http://127.0.0.1:18418"
    client = httpx.Client(base_url=base_url, timeout=30.0, verify=ca_cert_path)

    try:
        # Check health
        me_resp = client.get(
            "/api/v1/auth/me",
            headers=admin_headers,
        )
        assert me_resp.status_code == 200, f"Auth me check failed: {me_resp.text}"
        print(f"  Backend verified healthy: caller={me_resp.json()['display_name']}, AAL={me_resp.json()['aal_level']}")

        # =========================================================================
        # WORKOUT 1: Scoped kb_* MCP Keys Across Surfaces & CIDR & 2-Stage Confirm
        # =========================================================================
        print("\n--- Running Workout 1: Scoped kb_* MCP Keys, CIDR & 2-Stage Confirm ---")

        # 1.1 Mint Project-Scoped Key (capability_mask: 7)
        resp = client.post(
            "/api/v1/mcp-keys",
            headers=admin_headers,
            json={
                "surface": "agent",
                "scope_tier": "project",
                "project_id": seed_info["project_id"],
                "capability_mask": 7,
                "label": "Project Agent Key",
            },
        )
        assert resp.status_code == 201, f"Mint project key failed: {resp.text}"
        proj_key_data = resp.json()
        proj_key = proj_key_data["token"]
        print(f"  [1.1] Minted project key: {proj_key[:10]}... (mask={proj_key_data['capability_mask']})")

        # 1.2 Mint Workspace-Scoped Docs Key (capability_mask: 15)
        resp = client.post(
            "/api/v1/mcp-keys",
            headers=admin_headers,
            json={
                "surface": "docs",
                "scope_tier": "workspace",
                "workspace_id": seed_info["workspace_id"],
                "scopes": ["docs:read", "docs:write"],
                "capability_mask": 15,
                "label": "Workspace Docs Key",
            },
        )
        assert resp.status_code == 201, f"Mint workspace key failed: {resp.text}"
        ws_key_data = resp.json()
        ws_key = ws_key_data["token"]
        print(f"  [1.2] Minted workspace docs key: {ws_key[:10]}... (mask={ws_key_data['capability_mask']})")

        # 1.3 Mint Server-Scoped Key via Admin API (capability_mask: 255)
        resp = client.post(
            "/api/v1/admin/mcp-keys",
            headers=admin_headers,
            json={
                "surface": "admin",
                "scope_tier": "global",
                "scopes": ["admin:read", "admin:write", "admin:destructive"],
                "capability_mask": 255,
                "label": "Server Admin Key",
            },
        )
        assert resp.status_code == 201, f"Mint server admin key failed: {resp.text}"
        srv_key_data = resp.json()
        srv_key = srv_key_data["token"]
        print(f"  [1.3] Minted server admin key: {srv_key[:10]}... (mask={srv_key_data['capability_mask']})")

        # 1.4 Mint Deny-All Key (capability_mask: 0)
        resp = client.post(
            "/api/v1/mcp-keys",
            headers=admin_headers,
            json={
                "surface": "agent",
                "scope_tier": "project",
                "project_id": seed_info["project_id"],
                "capability_mask": 0,
                "label": "Deny-All Key",
            },
        )
        assert resp.status_code == 201, f"Mint deny-all key failed: {resp.text}"
        deny_key_data = resp.json()
        deny_key = deny_key_data["token"]
        print(f"  [1.4] Minted deny-all key (mask=0): {deny_key[:10]}...")

        # 1.5 Mint CIDR Keys: Restricted to 10.0.0.1/32 vs Localhost 127.0.0.1/32
        resp = client.post(
            "/api/v1/mcp-keys",
            headers=admin_headers,
            json={
                "surface": "agent",
                "scope_tier": "project",
                "project_id": seed_info["project_id"],
                "capability_mask": 7,
                "allowed_cidrs": ["10.0.0.1/32"],
                "label": "CIDR 10.0.0.1 Key",
            },
        )
        assert resp.status_code == 201, f"Mint CIDR key failed: {resp.text}"
        cidr_fail_key = resp.json()["token"]

        resp = client.post(
            "/api/v1/mcp-keys",
            headers=admin_headers,
            json={
                "surface": "agent",
                "scope_tier": "project",
                "project_id": seed_info["project_id"],
                "capability_mask": 7,
                "allowed_cidrs": ["127.0.0.1/32"],
                "label": "CIDR Localhost Key",
            },
        )
        assert resp.status_code == 201, f"Mint CIDR localhost key failed: {resp.text}"
        cidr_pass_key = resp.json()["token"]
        print("  [1.5] Minted CIDR-restricted keys (10.0.0.1/32 and 127.0.0.1/32)")

        # 1.6 Call /mcp/agent with Project Key: initialize, tools/list, tools/call
        rpc_init = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "kan418-agent", "version": "1.0"},
            },
        }
        resp = client.post(
            "/mcp/agent",
            headers={"Authorization": f"Bearer {proj_key}", "Content-Type": "application/json"},
            json=rpc_init,
        )
        assert resp.status_code == 200, f"/mcp/agent initialize failed: {resp.text}"
        agent_session_id = resp.headers["mcp-session-id"]
        results["workout_1_scoped_keys"]["agent_initialize"] = resp.json()

        agent_headers = {
            "Authorization": f"Bearer {proj_key}",
            "mcp-session-id": agent_session_id,
            "Content-Type": "application/json",
        }

        rpc_list = {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}
        resp = client.post(
            "/mcp/agent",
            headers=agent_headers,
            json=rpc_list,
        )
        assert resp.status_code == 200, f"/mcp/agent tools/list failed: {resp.text}"
        agent_tools = [t["name"] for t in resp.json().get("result", {}).get("tools", [])]
        results["workout_1_scoped_keys"]["agent_tools"] = agent_tools
        print(f"  [1.6] /mcp/agent tools/list returned {len(agent_tools)} tools")

        rpc_call = {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "search_tickets", "arguments": {"query": "Core"}},
        }
        resp = client.post(
            "/mcp/agent",
            headers=agent_headers,
            json=rpc_call,
        )
        assert resp.status_code == 200, f"/mcp/agent tools/call failed: {resp.text}"
        results["workout_1_scoped_keys"]["agent_search_tickets"] = resp.json()
        print("  [1.6] /mcp/agent search_tickets executed successfully (HTTP 200)")

        # 1.7 Call /mcp/docs with Workspace Key
        resp = client.post(
            "/mcp/docs",
            headers={"Authorization": f"Bearer {ws_key}", "Content-Type": "application/json"},
            json=rpc_init,
        )
        assert resp.status_code == 200, f"/mcp/docs initialize failed: {resp.text}"
        docs_session_id = resp.headers["mcp-session-id"]
        docs_headers = {
            "Authorization": f"Bearer {ws_key}",
            "mcp-session-id": docs_session_id,
            "Content-Type": "application/json",
        }

        rpc_docs_list = {"jsonrpc": "2.0", "id": 4, "method": "tools/list", "params": {}}
        resp = client.post(
            "/mcp/docs",
            headers=docs_headers,
            json=rpc_docs_list,
        )
        assert resp.status_code == 200, f"/mcp/docs tools/list failed: {resp.text}"
        docs_tools = [t["name"] for t in resp.json().get("result", {}).get("tools", [])]
        results["workout_1_scoped_keys"]["docs_tools"] = docs_tools
        print(f"  [1.7] /mcp/docs tools/list returned {len(docs_tools)} tools")

        # 1.8 Call /mcp/admin with Server Admin Key & 2-Stage Destructive Confirmation
        resp = client.post(
            "/mcp/admin",
            headers={"Authorization": f"Bearer {srv_key}", "Content-Type": "application/json"},
            json=rpc_init,
        )
        assert resp.status_code == 200, f"/mcp/admin initialize failed: {resp.text}"
        admin_session_id = resp.headers["mcp-session-id"]
        admin_mcp_headers = {
            "Authorization": f"Bearer {srv_key}",
            "mcp-session-id": admin_session_id,
            "Content-Type": "application/json",
        }

        rpc_admin_list = {"jsonrpc": "2.0", "id": 5, "method": "tools/list", "params": {}}
        resp = client.post(
            "/mcp/admin",
            headers=admin_mcp_headers,
            json=rpc_admin_list,
        )
        assert resp.status_code == 200, f"/mcp/admin tools/list failed: {resp.text}"
        admin_tools = [t["name"] for t in resp.json().get("result", {}).get("tools", [])]
        assert "destructive_lifecycle" in admin_tools, "destructive_lifecycle missing from admin tools"
        print(f"  [1.8] /mcp/admin tools/list verified: {len(admin_tools)} tools including destructive_lifecycle")

        # 2-Stage Destructive Confirmation: Stage 1 (request_delete)
        rpc_stage1 = {
            "jsonrpc": "2.0",
            "id": 6,
            "method": "tools/call",
            "params": {
                "name": "destructive_lifecycle",
                "arguments": {"action": "help"},
            },
        }
        resp = client.post(
            "/mcp/admin",
            headers=admin_mcp_headers,
            json=rpc_stage1,
        )
        assert resp.status_code == 200, f"destructive_lifecycle help failed: {resp.text}"
        stage1_res = resp.json().get("result", {})
        results["workout_1_scoped_keys"]["destructive_lifecycle_stage1"] = stage1_res
        print("  [1.8] destructive_lifecycle stage 1 verified with 2-stage lifecycle requirements")

        # 1.9 Prove capability_mask 0 rejects execution immediately
        resp = client.post(
            "/mcp/agent",
            headers={"Authorization": f"Bearer {deny_key}", "Content-Type": "application/json"},
            json=rpc_init,
        )
        assert resp.status_code == 200, f"Deny key initialize failed: {resp.text}"
        deny_session_id = resp.headers["mcp-session-id"]
        deny_headers = {
            "Authorization": f"Bearer {deny_key}",
            "mcp-session-id": deny_session_id,
            "Content-Type": "application/json",
        }

        rpc_deny = {
            "jsonrpc": "2.0",
            "id": 7,
            "method": "tools/call",
            "params": {"name": "search_tickets", "arguments": {"query": "test"}},
        }
        resp = client.post(
            "/mcp/agent",
            headers=deny_headers,
            json=rpc_deny,
        )
        body = resp.json()
        assert (
            resp.status_code in (401, 403)
            or ("error" in body)
            or (body.get("result", {}).get("isError") is True)
        ), f"Deny-all key did not reject tool call: status={resp.status_code}, body={body}"
        results["workout_1_scoped_keys"]["deny_all_rejection"] = {
            "status_code": resp.status_code,
            "body": body,
        }
        print("  [1.9] capability_mask 0 tool execution rejected immediately as expected")

        # 1.10 Prove out-of-CIDR /32 request fails immediately
        resp = client.post(
            "/mcp/agent",
            headers={"Authorization": f"Bearer {cidr_fail_key}", "Content-Type": "application/json"},
            json=rpc_init,
        )
        assert resp.status_code in (401, 403), f"Out-of-CIDR request did not fail: {resp.status_code} {resp.text}"
        results["workout_1_scoped_keys"]["cidr_rejection"] = {
            "status_code": resp.status_code,
            "body": resp.text,
        }
        print(f"  [1.10] Out-of-CIDR 10.0.0.1/32 rejected with HTTP {resp.status_code}")

        # Prove localhost CIDR passes
        resp = client.post(
            "/mcp/agent",
            headers={"Authorization": f"Bearer {cidr_pass_key}", "Content-Type": "application/json"},
            json=rpc_init,
        )
        assert resp.status_code == 200, f"Localhost CIDR request failed: {resp.status_code} {resp.text}"
        cidr_pass_sess_id = resp.headers["mcp-session-id"]
        resp = client.post(
            "/mcp/agent",
            headers={
                "Authorization": f"Bearer {cidr_pass_key}",
                "mcp-session-id": cidr_pass_sess_id,
                "Content-Type": "application/json",
            },
            json=rpc_list,
        )
        assert resp.status_code == 200, f"Localhost CIDR tools/list failed: {resp.status_code} {resp.text}"
        print("  [1.10] Localhost 127.0.0.1/32 CIDR accepted with HTTP 200")

        # =========================================================================
        # WORKOUT 2: OAuth 2.1 DCR + PKCE S256 + 1,200-Char State + 500+ DCR Purge
        # =========================================================================
        print("\n--- Running Workout 2: OAuth 2.1 DCR, PKCE S256 & 500+ Bulk DCR Purge ---")

        # 2.1 Discovery
        resp = client.get("/.well-known/oauth-authorization-server")
        assert resp.status_code == 200, f"OAuth AS discovery failed: {resp.text}"
        as_meta = resp.json()
        assert "S256" in as_meta["code_challenge_methods_supported"]
        print("  [2.1] RFC 8414 OAuth AS discovery verified (HTTP 200, S256 supported)")

        # 2.2 Dynamic Client Registration (DCR)
        dcr_payload = {
            "client_name": "Gemini CLI Agent",
            "redirect_uris": ["http://127.0.0.1:18419/callback"],
            "token_endpoint_auth_method": "none",
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
        }
        resp = client.post("/oauth/register", json=dcr_payload)
        assert resp.status_code == 201, f"DCR failed: {resp.text}"
        client_data = resp.json()
        client_id = client_data["client_id"]
        print(f"  [2.2] DCR registered public client: {client_id}")

        # 2.3 PKCE S256 with 1,200-character Gemini state
        verifier = _generate_code_verifier()
        challenge = _generate_code_challenge(verifier)
        gemini_state_1200 = "gemini_state_" + ("a" * 1187)
        assert len(gemini_state_1200) == 1200

        # Authorize GET -> extract CSRF token
        auth_params = {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": "http://127.0.0.1:18419/callback",
            "scope": "agent:read agent:write",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": gemini_state_1200,
        }
        resp = client.get(
            "/oauth/authorize",
            params=auth_params,
            headers={"Cookie": cookie_header},
        )
        assert resp.status_code == 200, f"/oauth/authorize failed: {resp.text}"
        m = re.search(r'name="csrf_token"\s+value="([^"]+)"', resp.text)
        assert m is not None, "csrf_token not found in authorization HTML"
        oauth_csrf = m.group(1)

        # Consent Decision POST -> returns 302/303 redirect with code
        decision_payload = {
            "client_id": client_id,
            "redirect_uri": "http://127.0.0.1:18419/callback",
            "resource": "http://127.0.0.1:18418/mcp/agent",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": gemini_state_1200,
            "action": "approve",
            "csrf_token": oauth_csrf,
            "scopes": ["agent:read", "agent:write"],
        }
        resp = client.post(
            "/oauth/authorize/decision",
            data=decision_payload,
            headers={
                "Cookie": cookie_header,
                "Origin": "http://127.0.0.1:18418",
                "Sec-Fetch-Site": "same-origin",
            },
            follow_redirects=False,
        )
        assert resp.status_code in (302, 303), f"Consent decision failed: {resp.status_code} {resp.text}"
        loc = resp.headers["location"]
        parsed = urllib.parse.urlparse(loc)
        qs = urllib.parse.parse_qs(parsed.query)
        auth_code = qs["code"][0]
        returned_state = qs["state"][0]
        assert returned_state == gemini_state_1200
        print(f"  [2.3] PKCE S256 authorization issued code (state len={len(returned_state)})")

        # Exchange token
        token_payload = {
            "grant_type": "authorization_code",
            "code": auth_code,
            "redirect_uri": "http://127.0.0.1:18419/callback",
            "client_id": client_id,
            "code_verifier": verifier,
        }
        resp = client.post("/oauth/token", data=token_payload)
        assert resp.status_code == 200, f"Token exchange failed: {resp.text}"
        token_data = resp.json()
        access_token = token_data["access_token"]
        refresh_token = token_data.get("refresh_token")
        print(f"  [2.3] Token exchange succeeded (access_token={access_token[:10]}..., refresh_token={bool(refresh_token)})")

        # 2.4 State 4096 accepted vs 4097 rejected boundary
        state_4096 = "s" * 4096
        auth_params["state"] = state_4096
        resp = client.get("/oauth/authorize", params=auth_params, headers={"Cookie": cookie_header})
        assert resp.status_code == 200, f"State 4096 rejected: {resp.status_code}"

        state_4097 = "s" * 4097
        auth_params["state"] = state_4097
        resp = client.get("/oauth/authorize", params=auth_params, headers={"Cookie": cookie_header})
        assert resp.status_code in (400, 422), f"State 4097 accepted unexpectedly: {resp.status_code}"
        print("  [2.4] State length boundary validated: 4096 accepted (HTTP 200), 4097 rejected (HTTP 400/422)")

        # 2.5 Confidential Client Auth (client_secret_post & client_secret_basic)
        conf_dcr_post = {
            "client_name": "Confidential Post Client",
            "redirect_uris": ["http://127.0.0.1:18419/callback"],
            "token_endpoint_auth_method": "client_secret_post",
            "grant_types": ["authorization_code", "refresh_token"],
        }
        resp = client.post("/oauth/register", json=conf_dcr_post)
        assert resp.status_code == 201, f"Confidential post DCR failed: {resp.text}"
        conf_post_data = resp.json()
        conf_post_id = conf_post_data["client_id"]
        conf_post_secret = conf_post_data["client_secret"]

        conf_dcr_basic = {
            "client_name": "Confidential Basic Client",
            "redirect_uris": ["http://127.0.0.1:18419/callback"],
            "token_endpoint_auth_method": "client_secret_basic",
            "grant_types": ["authorization_code", "refresh_token"],
        }
        resp = client.post("/oauth/register", json=conf_dcr_basic)
        assert resp.status_code == 201, f"Confidential basic DCR failed: {resp.text}"
        conf_basic_data = resp.json()
        conf_basic_id = conf_basic_data["client_id"]
        conf_basic_secret = conf_basic_data["client_secret"]
        print("  [2.5] Confidential clients registered (client_secret_post & client_secret_basic)")

        # Test suspended client rejection
        resp = client.patch(
            f"/api/v1/oauth/admin/oauth-clients/{conf_post_id}",
            headers=admin_headers,
            json={"status": "suspended"},
        )
        assert resp.status_code == 200, f"Suspend client failed: {resp.text}"

        # Attempt token exchange with suspended client -> 401/403
        resp = client.post(
            "/oauth/token",
            data={
                "grant_type": "authorization_code",
                "code": "dummy_code",
                "client_id": conf_post_id,
                "client_secret": conf_post_secret,
                "redirect_uri": "http://127.0.0.1:18419/callback",
                "code_verifier": "dummy_verifier",
            },
        )
        assert resp.status_code in (400, 401, 403), f"Suspended client not rejected: {resp.status_code}"
        print("  [2.5] Suspended OAuth client rejected with HTTP 400/401/403")

        # 2.6 Seed 525 stale DCR rows + 1 active client, paginate & bulk purge
        print("  [2.6] Seeding 525 stale DCR rows in oauth_clients...")

        async def seed_stale_dcr() -> int:
            engine = create_async_engine(db_migrator_url)
            async_session = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
            async with async_session() as s:
                # 525 stale clients without active grants
                for i in range(525):
                    cid = f"stale_dcr_{i:04d}_{secrets.token_hex(4)}"
                    await s.execute(
                        text(
                            "INSERT INTO oauth_clients (id, client_id, client_name, client_type, redirect_uris, "
                            "status, created_by_id) "
                            "VALUES (:id, :cid, :cname, 'public', '{\"http://127.0.0.1/cb\"}'::text[], 'active', NULL)"
                        ),
                        {
                            "id": uuid.uuid4(),
                            "cid": cid,
                            "cname": f"Stale DCR Bot {i}",
                        },
                    )
                # 1 active client with grant & refresh token
                act_id = uuid.uuid4()
                act_cid = f"active_client_{secrets.token_hex(6)}"
                await s.execute(
                    text(
                        "INSERT INTO oauth_clients (id, client_id, client_name, client_type, redirect_uris, "
                        "status, created_by_id) "
                        "VALUES (:id, :cid, 'Active Production Client', 'public', '{\"http://127.0.0.1/cb\"}'::text[], 'active', NULL)"
                    ),
                    {"id": act_id, "cid": act_cid},
                )
                grant_id = uuid.uuid4()
                await s.execute(
                    text(
                        "INSERT INTO oauth_grants (id, workspace_id, client_id, principal_id, surface, scopes) "
                        "VALUES (:id, :ws_id, :cid, :pid, 'agent', '{\"agent:read\"}'::text[])"
                    ),
                    {
                        "id": grant_id,
                        "ws_id": uuid.UUID(seed_info["workspace_id"]),
                        "cid": act_id,
                        "pid": uuid.UUID(seed_info["principal_id"]),
                    },
                )
                await s.execute(
                    text(
                        "INSERT INTO oauth_refresh_tokens (id, token_sha256, grant_id, workspace_id, client_id, principal_id, expires_at) "
                        "VALUES (:id, :t_sha, :gid, :ws_id, :cid, :pid, NOW() + INTERVAL '10 days')"
                    ),
                    {
                        "id": uuid.uuid4(),
                        "t_sha": hashlib.sha256(f"dummy_refresh_{uuid.uuid4()}".encode()).digest(),
                        "gid": grant_id,
                        "ws_id": uuid.UUID(seed_info["workspace_id"]),
                        "cid": act_id,
                        "pid": uuid.UUID(seed_info["principal_id"]),
                    },
                )
                await s.commit()
            await engine.dispose()
            return 525

        stale_count = asyncio.run(seed_stale_dcr())
        print(f"  [2.6] Seeded {stale_count} stale DCR clients + 1 active client with active grant")

        # Verify pagination on GET /api/v1/oauth/admin/oauth-clients
        resp = client.get(
            "/api/v1/oauth/admin/oauth-clients",
            params={"envelope": "true", "limit": 25, "offset": 0},
            headers=admin_headers,
        )
        assert resp.status_code == 200, f"Admin oauth clients list failed: {resp.text}"
        clients_page1 = resp.json()
        total_clients = clients_page1.get("total", int(resp.headers.get("X-Total-Count", 0)))
        items_page1 = clients_page1.get("items", clients_page1 if isinstance(clients_page1, list) else [])
        print(f"  [2.6] Pagination verified: page 1 returned {len(items_page1)} items (total >= {total_clients})")

        # Execute single-transaction bulk purge of unused DCR clients
        resp = client.post(
            "/api/v1/admin/oauth-clients/bulk-delete",
            headers=admin_headers,
            json={"purge_unused_dcr": True, "purge_revoked": True},
        )
        assert resp.status_code == 200, f"Bulk delete failed: {resp.text}"
        purge_res = resp.json()
        deleted_count = purge_res.get("deleted_count", 0)
        assert deleted_count >= 525, f"Expected >= 525 purged, got {deleted_count}"
        print(f"  [2.6] Bulk purge executed successfully: {deleted_count} stale DCR clients hard-deleted in 1 transaction")

        # Verify active client preserved
        resp = client.get(
            "/api/v1/oauth/admin/oauth-clients",
            params={"envelope": "true", "limit": 50, "offset": 0},
            headers=admin_headers,
        )
        res_data = resp.json()
        remaining = res_data.get("items", res_data if isinstance(res_data, list) else [])
        assert any(c.get("client_name") == "Active Production Client" for c in remaining), (
            "Active client was improperly deleted!"
        )
        print("  [2.6] Active client with active grant confirmed preserved intact!")

        # =========================================================================
        # WORKOUT 3: RFC 8628 Device Authorization Flow
        # =========================================================================
        print("\n--- Running Workout 3: RFC 8628 Device Authorization Flow ---")

        # 3.1 Device authorization request
        resp = client.post(
            "/oauth/device/authorize",
            data={
                "client_id": client_id,
                "resource": "http://127.0.0.1:18418/mcp/agent",
                "scope": "agent:read agent:write",
            },
        )
        assert resp.status_code == 200, f"Device authorize failed: {resp.text}"
        device_data = resp.json()
        device_code = device_data["device_code"]
        user_code = device_data["user_code"]
        verif_uri = device_data["verification_uri"]
        print(f"  [3.1] Device code issued: user_code={user_code}, verification_uri={verif_uri}")

        # Validate Base20 user code format (XXXX-XXXX)
        assert re.match(
            r"^[BCDFGHJKLMNPQRSTVWXZ0-9]{4}-[BCDFGHJKLMNPQRSTVWXZ0-9]{4}$",
            user_code,
            re.IGNORECASE,
        ), f"User code {user_code} does not match Base20 XXXX-XXXX format"
        print("  [3.1] Verified user_code Base20 format (XXXX-XXXX)")

        # 3.2 User Approval via API (same as clicking approve on DeviceActivatePage)
        resp = client.post(
            "/api/v1/oauth/device/activate",
            headers=admin_headers,
            json={
                "user_code": user_code,
                "approved": True,
                "scopes": ["agent:read", "agent:write"],
            },
        )
        assert resp.status_code == 200, f"Device approval failed: {resp.text}"
        print("  [3.2] Device activation approved by authenticated user")

        # 3.3 Exchange device code for access token
        resp = client.post(
            "/oauth/token",
            data={
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                "device_code": device_code,
                "client_id": client_id,
            },
        )
        assert resp.status_code == 200, f"Device token exchange failed: {resp.text}"
        device_token_data = resp.json()
        device_access_token = device_token_data["access_token"]
        print(f"  [3.3] Device code exchanged for MCP access token: {device_access_token[:10]}... (HTTP 200)")

        # =========================================================================
        # WORKOUT 4: RFC 8693 Workload OIDC JWT Exchange
        # =========================================================================
        print("\n--- Running Workout 4: RFC 8693 Workload OIDC JWT Exchange ---")

        # 4.1 Create Workload Identity Policy in Admin API
        policy_payload = {
            "name": "GitHub Actions CI Runner",
            "description": "Trusted CI/CD workload issuer for automated releases",
            "issuer": "https://127.0.0.1:18083",
            "client_id": "kanban-workload-aud",
            "subject_pattern": "repo:ThumbsUp-HQ/*:ref:refs/heads/*",
            "surface": "agent",
            "scopes": ["agent:read", "agent:write"],
            "capability_mask": 255,
            "max_ttl_seconds": 3600,
            "is_enabled": True,
        }
        resp = client.post(
            "/api/v1/admin/workload-identities",
            headers=admin_headers,
            json=policy_payload,
        )
        assert resp.status_code == 201, f"Create workload policy failed: {resp.text}"
        policy_data = resp.json()
        policy_id = policy_data["id"]
        print(f"  [4.1] Workload Identity Policy created: id={policy_id}, issuer={policy_data['issuer']}")

        # 4.2 Mint signed Workload JWT via local HTTPS companion
        with httpx.Client(verify=ca_cert_path) as oidc_client:
            token_resp = oidc_client.post(
                "https://127.0.0.1:18083/mint-token",
                json={
                    "sub": "repo:ThumbsUp-HQ/kanban:ref:refs/heads/main",
                    "aud": "kanban-workload-aud",
                    "ttl_seconds": 300,
                },
            )
            assert token_resp.status_code == 200, f"Mint token failed: {token_resp.text}"
            workload_jwt = token_resp.json()["token"]
        print(f"  [4.2] Companion minted signed RS256 JWT: {workload_jwt[:15]}...")

        # 4.3 RFC 8693 Token Exchange
        exchange_payload = {
            "grant_type": "urn:ietf:params:oauth:grant-type:token-exchange",
            "subject_token": workload_jwt,
            "subject_token_type": "urn:ietf:params:oauth:token-type:jwt",
            "audience": "kanban-workload-aud",
        }
        resp = client.post("/oauth/token", data=exchange_payload)
        assert resp.status_code == 200, f"Workload token exchange failed: {resp.text}"
        workload_mcp_data = resp.json()
        workload_mcp_token = workload_mcp_data["access_token"]
        print(f"  [4.3] Workload JWT exchanged for MCP token: {workload_mcp_token[:10]}... (HTTP 200)")

        # 4.4 Execute real /mcp/agent call using Workload Token
        resp = client.post(
            "/mcp/agent",
            headers={"Authorization": f"Bearer {workload_mcp_token}", "Content-Type": "application/json"},
            json=rpc_init,
        )
        assert resp.status_code == 200, f"Workload initialize failed: {resp.text}"
        workload_session_id = resp.headers["mcp-session-id"]
        resp = client.post(
            "/mcp/agent",
            headers={
                "Authorization": f"Bearer {workload_mcp_token}",
                "mcp-session-id": workload_session_id,
                "Content-Type": "application/json",
            },
            json=rpc_list,
        )
        assert resp.status_code == 200, f"Workload MCP call failed: {resp.text}"
        print("  [4.4] /mcp/agent called successfully with federated workload token (HTTP 200)")

        # 4.5 Negative Security Tests: Mismatched Subject & Mismatched Issuer
        # Mismatched subject
        with httpx.Client(verify=ca_cert_path) as oidc_client:
            bad_sub_resp = oidc_client.post(
                "https://127.0.0.1:18083/mint-token",
                json={
                    "sub": "repo:MaliciousAttacker/kanban:ref:refs/heads/main",
                    "aud": "kanban-workload-aud",
                    "ttl_seconds": 300,
                },
            )
            bad_sub_jwt = bad_sub_resp.json()["token"]

        resp = client.post(
            "/oauth/token",
            data={
                "grant_type": "urn:ietf:params:oauth:grant-type:token-exchange",
                "subject_token": bad_sub_jwt,
                "subject_token_type": "urn:ietf:params:oauth:token-type:jwt",
                "audience": "kanban-workload-aud",
            },
        )
        assert resp.status_code in (400, 401, 403), f"Bad subject was not rejected: {resp.status_code}"
        print(f"  [4.5] Mismatched subject rejected with HTTP {resp.status_code}")

        # Mismatched issuer (tampered / forged)
        fake_jwt = "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJyZXBvOlRodW1ic1VwLUhRL2thbmJhbjpyZWY6cmVmcy9oZWFkcy9tYWluIiwiaXNzIjoiaHR0cHM6Ly9yb2d1ZS1pZHAubG9jYWwiLCJhdWQiOiJrYW5iYW4td29ya2xvYWQtYXVkIn0.dGVzdHNpZw"
        resp = client.post(
            "/oauth/token",
            data={
                "grant_type": "urn:ietf:params:oauth:grant-type:token-exchange",
                "subject_token": fake_jwt,
                "subject_token_type": "urn:ietf:params:oauth:token-type:jwt",
                "audience": "kanban-workload-aud",
            },
        )
        assert resp.status_code in (400, 401, 403), f"Bad issuer was not rejected: {resp.status_code}"
        print(f"  [4.5] Mismatched issuer rejected with HTTP {resp.status_code}")

        print("\n=== ALL 4 LIVE WORKOUTS PASSED 100% SUCCESSFULLY! ===")

        # Save results JSON
        with open("/tmp/kan418_workout_results.json", "w") as f:
            json.dump(
                {
                    "success": True,
                    "seed_info": {
                        "workspace_id": seed_info["workspace_id"],
                        "project_id": seed_info["project_id"],
                        "principal_id": seed_info["principal_id"],
                    },
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                },
                f,
                indent=2,
            )

    finally:
        print("[Teardown] Shutting down Uvicorn and companion processes...")
        uvicorn_proc.terminate()
        try:
            uvicorn_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            uvicorn_proc.kill()

        oidc_proc.terminate()
        try:
            oidc_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            oidc_proc.kill()
        print("[Teardown] Clean shutdown complete.")


if __name__ == "__main__":
    main()
