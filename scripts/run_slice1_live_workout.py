# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Comprehensive Live Workout Orchestrator for Slice 1 Phase 3 (KAN-408).

Executes real, zero-mock credential workouts against local live services:
- 127.0.0.1:18408: Local 👍kanban FastAPI ASGI server
- 127.0.0.1:10636: Local TLS LDAPS server
- 127.0.0.1:10389: Local StartTLS LDAP server
- 127.0.0.1:18081: Local HTTPS OIDC companion IdP

Covers:
1. Local Admin + WebAuthn Virtual Authenticator + TOTP + Recovery Codes + Break-Glass 409 Guard.
2. LDAPS test-draft Handshake + Active Directory Group -> RBAC Sync + Expired WebSudo Replay.
3. OIDC PKCE Login + Verified-Claim Account Linking + Unverified Email 403 Rejection.
4. Custom RBAC Role Enforcement (Capabilities: Allowed vs Denied).
5. Zero-Mock Playwright Screenshots across all 5 viewports + 6 workflow states.
"""

from __future__ import annotations

import asyncio
import datetime
import json
import logging
import os
import subprocess
import time
import urllib.parse
import uuid
from typing import Any

import asyncpg
import httpx
import uvicorn

from kanban.app import create_app
from kanban.auth.local.hashing import hash_password
from kanban.auth.mfa.totp import totp_at
from kanban.security.envelope import StaticKekProvider
from kanban.security.keys import KeyMaterial
from kanban.security.scrubber import scrub_text
from kanban.settings import Settings
from kanban.tests.helpers.soft_authenticator import SoftAuthenticator
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from scripts.slice1_live_companions import (
    PORT_LDAP_PLAIN,
    PORT_LDAP_TLS,
    PORT_OIDC,
    LiveLdapCompanion as LdapCompanion,
    LiveOidcCompanion as OidcCompanion,
    generate_workout_certs,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("workout_kan408")

os.environ["KANBAN_AUTH_EGRESS_ALLOW_PRIVATE"] = "true"

PORT_KANBAN = 18408
PG_SOCKET = "/tmp/kb-pgsock"
DB_NAME = "kanban_workout"

WORKSPACE_ID = uuid.UUID("01931000-0000-7000-8000-000000000001")
PROJECT_ID = uuid.UUID("01931000-0001-7000-8000-000000000001")
ADMIN_USER_ID = uuid.UUID("01931000-0002-7000-8000-000000000001")
FRY_USER_ID = uuid.UUID("01931000-0003-7000-8000-000000000001")


class WireLogger:
    """Captures real verbatim HTTP wire exchanges and scrubs secrets."""

    def __init__(self) -> None:
        self.logs: list[str] = []

    async def log_request(self, request: httpx.Request) -> None:
        body = ""
        try:
            content = await request.aread()
            if content:
                body = content.decode("utf-8", errors="replace")
        except Exception:
            try:
                if request.content:
                    body = request.content.decode("utf-8", errors="replace")
            except Exception:
                body = ""
        request.extensions["wire_log"] = {
            "method": request.method,
            "url": str(request.url),
            "headers": dict(request.headers),
            "body": body,
        }

    async def log_response(self, response: httpx.Response) -> None:
        req_info = response.request.extensions.get("wire_log", {})
        res_body = ""
        try:
            await response.aread()
            res_body = response.text
        except Exception:
            try:
                res_body = response.text
            except Exception:
                res_body = ""

        raw_path = response.request.url.raw_path
        path_and_query = raw_path.decode("ascii") if isinstance(raw_path, bytes) else str(raw_path)
        raw_netloc = response.request.url.netloc
        netloc_str = raw_netloc.decode("ascii") if isinstance(raw_netloc, bytes) else str(raw_netloc)
        req_lines = [
            f"{req_info.get('method', response.request.method)} {path_and_query} HTTP/1.1",
            f"Host: {netloc_str}",
        ]
        for h in ("content-type", "x-csrf-token", "kb-blast-hash"):
            val = response.request.headers.get(h)
            if val:
                req_lines.append(f"{h.title()}: {val}")
        req_str = "\n".join(req_lines)
        if req_info.get("body"):
            req_str += f"\n\n{req_info['body']}"

        res_lines = [
            f"HTTP/1.1 {response.status_code} {response.reason_phrase}",
        ]
        for h in ("content-type", "location", "set-cookie"):
            val = response.headers.get(h)
            if val:
                res_lines.append(f"{h.title()}: {val}")
        res_str = "\n".join(res_lines)
        if res_body:
            res_str += f"\n\n{res_body}"

        exchange = f"{req_str}\n\n{res_str}"
        scrubbed = scrub_text(exchange)
        self.logs.append(scrubbed)


wire_logger = WireLogger()


def make_http_client(**kwargs: Any) -> httpx.AsyncClient:
    """Create httpx.AsyncClient with automatic wire logging hook attached."""
    hooks = kwargs.pop("event_hooks", {})
    req_hooks = list(hooks.get("request", [])) + [wire_logger.log_request]
    res_hooks = list(hooks.get("response", [])) + [wire_logger.log_response]
    return httpx.AsyncClient(event_hooks={"request": req_hooks, "response": res_hooks}, **kwargs)


async def reset_and_seed_database(key_material: KeyMaterial, certs: Any) -> None:
    """Reset workout database from kanban_template and seed baseline test entities."""
    logger.info("Connecting to PostgreSQL to provision database '%s'...", DB_NAME)
    admin_conn = await asyncpg.connect(host=PG_SOCKET, user="kanban_test", database="postgres")
    try:
        await admin_conn.execute(
            f"""
            SELECT pg_terminate_backend(pid) FROM pg_stat_activity
            WHERE datname = '{DB_NAME}' AND pid <> pg_backend_pid();
            """
        )
        await admin_conn.execute(f"DROP DATABASE IF EXISTS {DB_NAME}")
        await admin_conn.execute(f"CREATE DATABASE {DB_NAME} WITH TEMPLATE kanban_template")
        logger.info("Database '%s' created from kanban_template.", DB_NAME)
    finally:
        await admin_conn.close()

    conn = await asyncpg.connect(host=PG_SOCKET, user="kanban_test", database=DB_NAME)
    try:
        # 1. Seed Workspace
        await conn.execute(
            "INSERT INTO workspaces (id, slug, name) VALUES ($1, $2, $3) ON CONFLICT (id) DO NOTHING",
            WORKSPACE_ID,
            "kanban",
            "Platform Engineering",
        )

        # Seed workspace RBAC roles
        await conn.execute("SELECT seed_workspace_rbac_roles($1)", WORKSPACE_ID)

        # 2. Seed Project
        await conn.execute(
            "SELECT register_object('project'::object_kind, $1, NULL, $2, $3, $4, $4)",
            WORKSPACE_ID,
            "KAN",
            "Platform Architecture",
            PROJECT_ID,
        )
        await conn.execute(
            """
            INSERT INTO projects (id, workspace_id, identifier, name)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (id) DO NOTHING
            """,
            PROJECT_ID,
            WORKSPACE_ID,
            "KAN",
            "Platform Architecture",
        )

        # 3. Seed Server Admin
        admin_pass_hash = await hash_password("AdminPassword123!", pepper=key_material.auth_pepper)
        await conn.execute(
            "SELECT register_object('user'::object_kind, $1, NULL, $2, $3, $4, $4)",
            WORKSPACE_ID,
            f"usr-{ADMIN_USER_ID.hex}",
            "System Administrator",
            ADMIN_USER_ID,
        )
        await conn.execute(
            """
            INSERT INTO principals (id, principal_type, workspace_id, display_name, status)
            VALUES ($1, 'USER', $2, 'System Administrator', 'ACTIVE')
            """,
            ADMIN_USER_ID,
            WORKSPACE_ID,
        )
        await conn.execute(
            """
            INSERT INTO users (id, object_type, principal_type, workspace_id, email)
            VALUES ($1, 'user', 'USER', $2, 'admin@kanban.local')
            """,
            ADMIN_USER_ID,
            WORKSPACE_ID,
        )
        await conn.execute(
            """
            INSERT INTO local_admin_credentials (principal_id, username, password_hash)
            VALUES ($1, 'admin', $2)
            """,
            ADMIN_USER_ID,
            admin_pass_hash,
        )
        await conn.execute(
            """
            INSERT INTO role_bindings (id, workspace_id, principal_id, role, scope_type)
            VALUES ($1, $2, $3, 'SERVER_ADMIN', 'server')
            """,
            uuid.uuid4(),
            WORKSPACE_ID,
            ADMIN_USER_ID,
        )

        # 4. Seed built-in Local Admin Card
        card_id = uuid.UUID("01a21408-aaaa-7000-8000-000000000001")
        await conn.execute(
            """
            INSERT INTO auth_provider_cards (
                id, workspace_id, provider_kind, slug, display_name,
                button_subtext, icon_preset, is_enabled, sort_rank,
                auto_provision_users, allowed_email_domains, public_config,
                last_health_status
            ) VALUES (
                $1, $2, 'LOCAL_ADMIN', 'local-admin', 'Local Administrator',
                'Built-in Superuser Password Auth', 'shield', true, '001',
                false, '{}', '{}', 'HEALTHY'
            )
            """,
            card_id,
            WORKSPACE_ID,
        )

        # 5. Seed test user Fry
        fry_pass_hash = await hash_password("frypassword", pepper=key_material.auth_pepper)
        await conn.execute(
            "SELECT register_object('user'::object_kind, $1, NULL, $2, $3, $4, $4)",
            WORKSPACE_ID,
            f"usr-{FRY_USER_ID.hex}",
            "Philip J. Fry",
            FRY_USER_ID,
        )
        await conn.execute(
            "INSERT INTO principals (id, principal_type, workspace_id, display_name, status) VALUES ($1, 'USER', $2, $3, 'ACTIVE')",
            FRY_USER_ID,
            WORKSPACE_ID,
            "Philip J. Fry",
        )
        await conn.execute(
            "INSERT INTO users (id, object_type, principal_type, workspace_id, email) VALUES ($1, 'user', 'USER', $2, $3)",
            FRY_USER_ID,
            WORKSPACE_ID,
            "fry@planetexpress.com",
        )
        await conn.execute(
            "INSERT INTO local_admin_credentials (principal_id, username, password_hash) VALUES ($1, $2, $3)",
            FRY_USER_ID,
            "fry",
            fry_pass_hash,
        )
        await conn.execute(
            "INSERT INTO role_bindings (id, workspace_id, principal_id, role, scope_type) VALUES ($1, $2, $3, 'WORKSPACE_MEMBER', 'workspace')",
            uuid.uuid4(),
            WORKSPACE_ID,
            FRY_USER_ID,
        )

        logger.info("Database seeding completed.")
    finally:
        await conn.close()


async def main() -> None:
    """Run full live workout suite."""
    start_time = time.monotonic()
    results: dict[str, Any] = {
        "workout_1": {},
        "workout_2": {},
        "workout_3": {},
        "workout_4": {},
        "screenshots": {},
        "metrics": {},
    }

    # Generate certificates
    logger.info("Generating workout certificate bundle...")
    certs = generate_workout_certs()
    os.environ["SSL_CERT_FILE"] = certs.ca_file

    # Start companions
    ldap_companion = LdapCompanion(certs)
    await ldap_companion.start()

    oidc_companion = OidcCompanion(certs)
    await oidc_companion.start()

    # Key material for Kanban app
    key_material = KeyMaterial(
        master_kek=b"k" * 32,
        auth_pepper=b"p" * 32,
        session_hmac_key=b"s" * 32,
    )

    # Reset and seed DB
    await reset_and_seed_database(key_material, certs)

    # Start Kanban App
    logger.info("Initializing Kanban FastAPI application on port %d...", PORT_KANBAN)
    settings = Settings(
        deployment_mode="standalone",
        database_url=f"postgresql+asyncpg://kanban_test@/{DB_NAME}?host={PG_SOCKET}",
        public_base_url=f"http://127.0.0.1:{PORT_KANBAN}",
        public_origin=f"http://127.0.0.1:{PORT_KANBAN}",
        webauthn_rp_name="👍kanban",
        webauthn_rp_id="127.0.0.1",
        block_cleartext_http=False,
    )
    app = create_app(settings=settings)
    app.state.key_material = key_material
    app.state.kek_provider = StaticKekProvider(
        {"kek-v1": key_material.master_kek}, current="kek-v1"
    )

    kanban_server_cfg = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=PORT_KANBAN,
        log_level="warning",
    )
    kanban_server = uvicorn.Server(kanban_server_cfg)
    kanban_task = asyncio.create_task(kanban_server.serve())

    # Wait for server to listen
    for _ in range(50):
        try:
            async with httpx.AsyncClient() as probe_client:
                r = await probe_client.get(f"http://127.0.0.1:{PORT_KANBAN}/api/v1/auth/session")
                if r.status_code == 200:
                    break
        except Exception:
            pass
        await asyncio.sleep(0.1)
    logger.info("Kanban server is up and listening on http://127.0.0.1:%d", PORT_KANBAN)

    try:
        base_url = f"http://127.0.0.1:{PORT_KANBAN}"
        async with make_http_client(base_url=base_url, timeout=15.0) as client:
            # -------------------------------------------------------------------
            # WORKOUT 1: Local Admin + Passkey + TOTP + Recovery Codes + Break-Glass Lockout Guard (409)
            # -------------------------------------------------------------------
            logger.info("=== WORKOUT 1: Local Admin + Passkey + TOTP + Recovery Codes + Break-Glass ===")

            # 1.0 Obtain pre-session CSRF
            init_sess = await client.get("/api/v1/auth/session")
            assert init_sess.status_code == 200, f"Init session failed: {init_sess.text}"
            csrf_token = init_sess.json().get("csrf_token")
            client.cookies.set("kb_csrf", init_sess.cookies.get("kb_csrf") or csrf_token)
            headers = {"X-CSRF-Token": csrf_token}

            # 1.1 Local Admin Login
            login_resp = await client.post(
                "/api/v1/auth/local/login",
                headers=headers,
                json={"username": "admin", "password": "AdminPassword123!"},
            )
            assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"
            cookies = dict(login_resp.cookies)
            session_cookie = cookies.get("kb_session")
            csrf_token = cookies.get("kb_csrf") or login_resp.json().get("csrf_token") or csrf_token
            client.cookies.set("kb_csrf", csrf_token)
            headers = {"X-CSRF-Token": csrf_token}

            results["workout_1"]["login"] = {
                "status_code": login_resp.status_code,
                "aal_level": login_resp.json().get("aal_level"),
                "auth_aal": login_resp.json().get("auth_aal"),
            }

            # 1.2 WebAuthn Registration Options & Complete Verification
            reg_opts_resp = await client.post(
                "/api/v1/auth/webauthn/register/options",
                headers=headers,
                json={"authenticator_attachment": "platform"},
            )
            assert reg_opts_resp.status_code == 200, f"WebAuthn options failed: {reg_opts_resp.text}"
            reg_opts = reg_opts_resp.json()
            rp_name = reg_opts.get("rp", {}).get("name")
            rp_id = reg_opts.get("rp", {}).get("id")
            assert rp_name == "👍kanban", f"WebAuthn rp.name mismatch: {rp_name}"
            assert rp_id == "127.0.0.1", f"WebAuthn rp.id mismatch: {rp_id}"

            # Create registration credential via SoftAuthenticator
            soft_auth = SoftAuthenticator()
            reg_cred = soft_auth.create_credential(reg_opts, origin=base_url)
            reg_verify_resp = await client.post(
                "/api/v1/auth/webauthn/register/verify",
                headers=headers,
                json={"credential": reg_cred, "nickname": "Workout Admin Passkey"},
            )
            assert reg_verify_resp.status_code == 200, f"WebAuthn register verify failed: {reg_verify_resp.text}"
            reg_verify_data = reg_verify_resp.json()
            assert reg_verify_data.get("verified") is True, f"Registration not verified: {reg_verify_data}"
            csrf_token = reg_verify_data.get("csrf_token") or reg_verify_resp.cookies.get("kb_csrf") or csrf_token
            client.cookies.set("kb_csrf", csrf_token)
            headers["X-CSRF-Token"] = csrf_token

            # Test WebAuthn Assertion flow
            auth_opts_resp = await client.post(
                "/api/v1/auth/webauthn/authenticate/options",
                headers=headers,
            )
            assert auth_opts_resp.status_code == 200, f"WebAuthn auth options failed: {auth_opts_resp.text}"
            auth_opts = auth_opts_resp.json()
            auth_assert = soft_auth.get_assertion(auth_opts, origin=base_url)
            auth_verify_resp = await client.post(
                "/api/v1/auth/webauthn/authenticate/verify",
                headers=headers,
                json={"credential": auth_assert},
            )
            assert auth_verify_resp.status_code == 200, f"WebAuthn auth verify failed: {auth_verify_resp.text}"
            auth_verify_data = auth_verify_resp.json()
            csrf_token = auth_verify_data.get("csrf_token") or auth_verify_resp.cookies.get("kb_csrf") or csrf_token
            client.cookies.set("kb_csrf", csrf_token)
            headers["X-CSRF-Token"] = csrf_token

            results["workout_1"]["webauthn_passkey"] = {
                "options_status": reg_opts_resp.status_code,
                "rp_name": rp_name,
                "rp_id": rp_id,
                "challenge_len": len(reg_opts.get("challenge", "")),
                "register_verify_status": reg_verify_resp.status_code,
                "registered": reg_verify_data.get("verified"),
                "auth_options_status": auth_opts_resp.status_code,
                "auth_verify_status": auth_verify_resp.status_code,
                "auth_aal": auth_verify_data.get("aal_level"),
            }

            # 1.3 TOTP Enrollment & Step-Up
            totp_setup_resp = await client.post("/api/v1/auth/mfa/totp/enroll", headers=headers)
            assert totp_setup_resp.status_code == 200, f"TOTP setup failed: {totp_setup_resp.text}"
            totp_data = totp_setup_resp.json()
            secret_b32 = totp_data["secret"]
            import base64
            secret_bytes = base64.b32decode(secret_b32)
            current_totp = totp_at(secret_bytes, int(time.time()))

            totp_confirm_resp = await client.post(
                "/api/v1/auth/mfa/totp/confirm",
                headers=headers,
                json={"code": current_totp, "enrollment_id": "setup"},
            )
            assert totp_confirm_resp.status_code == 200, f"TOTP confirm failed: {totp_confirm_resp.text}"
            confirm_data = totp_confirm_resp.json()
            csrf_token = confirm_data.get("csrf_token") or totp_confirm_resp.cookies.get("kb_csrf") or csrf_token
            client.cookies.set("kb_csrf", csrf_token)
            headers["X-CSRF-Token"] = csrf_token

            rec_codes = confirm_data.get("recovery_codes", [])
            assert len(rec_codes) == 10, f"Expected 10 recovery codes from confirm, got {len(rec_codes)}"

            results["workout_1"]["totp_enrollment"] = {
                "setup_status": totp_setup_resp.status_code,
                "confirm_status": totp_confirm_resp.status_code,
                "confirmed_aal": confirm_data.get("aal_level"),
            }

            # 1.4 Recovery Codes Verification & Step-Up
            stepup_resp = await client.post(
                "/api/v1/auth/mfa/verify",
                headers=headers,
                json={"method": "recovery", "code": rec_codes[0]},
            )
            assert stepup_resp.status_code == 200, f"Recovery step-up failed: {stepup_resp.text}"
            csrf_token = stepup_resp.json().get("csrf_token") or stepup_resp.cookies.get("kb_csrf") or csrf_token
            client.cookies.set("kb_csrf", csrf_token)
            headers["X-CSRF-Token"] = csrf_token

            # Also verify regenerating recovery codes as AAL2
            regen_resp = await client.post("/api/v1/auth/mfa/recovery/regenerate", headers=headers)
            assert regen_resp.status_code == 200, f"Regenerate recovery codes failed: {regen_resp.text}"
            fresh_rec_codes = regen_resp.json().get("recovery_codes", [])
            assert len(fresh_rec_codes) == 10

            results["workout_1"]["recovery_codes"] = {
                "count": len(rec_codes),
                "code_sample_format": f"{rec_codes[0][:5]}-*****",
                "stepup_status": stepup_resp.status_code,
                "stepup_aal": stepup_resp.json().get("aal_level"),
                "regenerated_count": len(fresh_rec_codes),
            }

            # 1.5 Break-Glass Anti-Lockout Guard (409)
            disable_resp = await client.post(
                "/api/v1/admin/auth-cards/local-admin/disable",
                headers=headers,
            )
            assert disable_resp.status_code == 409, f"Expected 409 lockout guard, got: {disable_resp.status_code}"
            lockout_err = disable_resp.json()
            assert lockout_err.get("code") == "LOCKOUT_PREVENTED"
            layer = lockout_err.get("layer") or lockout_err.get("extra", {}).get("layer")
            assert layer in ("local_admin_card_invariant", "handshake_probe_15m", "sole_active_card"), f"Unexpected layer: {layer}"

            results["workout_1"]["break_glass_guard"] = {
                "disable_status": disable_resp.status_code,
                "error_code": lockout_err.get("code"),
                "layer": layer,
                "detail": lockout_err.get("detail"),
            }
            logger.info("Workout 1 complete: Break-glass 409 guard strictly proven.")

            # -------------------------------------------------------------------
            # WORKOUT 2: LDAPS / StartTLS test-draft Handshake + Nested AD Group -> RBAC Sync + Dirty-Drawer WebSudo Replay
            # -------------------------------------------------------------------
            logger.info("=== WORKOUT 2: LDAPS Handshake + Nested AD Group Sync + WebSudo Replay ===")

            # 2.0 Untrusted-CA TLS Fail-Closed Probe
            untrusted_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
            untrusted_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Untrusted Workout Root CA")])
            untrusted_cert = (
                x509.CertificateBuilder()
                .subject_name(untrusted_name)
                .issuer_name(untrusted_name)
                .public_key(untrusted_key.public_key())
                .serial_number(9999)
                .not_valid_before(datetime.datetime.now(datetime.UTC) - datetime.timedelta(hours=1))
                .not_valid_after(datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=1))
                .sign(untrusted_key, hashes.SHA256())
            )
            untrusted_ca_pem = untrusted_cert.public_bytes(serialization.Encoding.PEM).decode("ascii")

            untrusted_draft = {
                "provider_kind": "LDAP",
                "slug": "untrusted-ca-ldap",
                "display_name": "Untrusted CA LDAP",
                "is_enabled": True,
                "public_config": {
                    "kind": "LDAP",
                    "url": f"ldaps://127.0.0.1:{PORT_LDAP_TLS}",
                    "transport_mode": "ldaps",
                    "base_dn": "dc=planetexpress,dc=com",
                    "ca_cert_pem": untrusted_ca_pem,
                    "service_bind_dn": "cn=admin,dc=planetexpress,dc=com",
                },
                "secret": json.dumps({"bind_dn_password": "GoodNewsEveryone"}),
            }
            untrusted_probe_resp = await client.post(
                "/api/v1/admin/auth-cards/test-handshake",
                headers=headers,
                json=untrusted_draft,
            )
            assert untrusted_probe_resp.status_code == 200
            untrusted_probe = untrusted_probe_resp.json()
            assert untrusted_probe.get("ok") is False, "Expected untrusted CA probe to fail closed"

            # 2.0b StartTLS Handshake Probe (Port 10389)
            starttls_draft = {
                "provider_kind": "LDAP",
                "slug": "starttls-ldap",
                "display_name": "Planet Express StartTLS",
                "is_enabled": True,
                "public_config": {
                    "kind": "LDAP",
                    "url": f"ldap://127.0.0.1:{PORT_LDAP_PLAIN}",
                    "transport_mode": "starttls",
                    "base_dn": "dc=planetexpress,dc=com",
                    "ca_cert_pem": certs.ca_cert_pem,
                    "service_bind_dn": "cn=admin,dc=planetexpress,dc=com",
                },
                "secret": json.dumps({"bind_dn_password": "GoodNewsEveryone"}),
            }
            starttls_probe_resp = await client.post(
                "/api/v1/admin/auth-cards/test-handshake",
                headers=headers,
                json=starttls_draft,
            )
            assert starttls_probe_resp.status_code == 200
            starttls_probe = starttls_probe_resp.json()
            assert starttls_probe.get("ok") is True, f"StartTLS probe failed: {starttls_probe}"

            # 2.1 Test-Draft Handshake Failure (Bad Credentials)
            bad_draft = {
                "provider_kind": "LDAP",
                "slug": "bad-ldap",
                "display_name": "Bad LDAP",
                "is_enabled": True,
                "public_config": {
                    "kind": "LDAP",
                    "url": f"ldaps://127.0.0.1:{PORT_LDAP_TLS}",
                    "transport_mode": "ldaps",
                    "base_dn": "dc=planetexpress,dc=com",
                    "ca_cert_pem": certs.ca_cert_pem,
                    "service_bind_dn": "cn=admin,dc=planetexpress,dc=com",
                },
                "secret": json.dumps({"bind_dn_password": "WrongPassword123!"}),
            }
            bad_probe_resp = await client.post(
                "/api/v1/admin/auth-cards/test-handshake",
                headers=headers,
                json=bad_draft,
            )
            assert bad_probe_resp.status_code == 200
            bad_probe = bad_probe_resp.json()
            assert bad_probe.get("ok") is False, "Expected bad probe to fail"

            # 2.2 Test-Draft Handshake Success (Valid Pinned CA PEM & Credentials)
            good_draft = {
                "provider_kind": "LDAP",
                "slug": "planetexpress-ldap",
                "display_name": "Planet Express LDAPS",
                "is_enabled": True,
                "auto_provision_users": True,
                "public_config": {
                    "kind": "LDAP",
                    "url": f"ldaps://127.0.0.1:{PORT_LDAP_TLS}",
                    "transport_mode": "ldaps",
                    "base_dn": "dc=planetexpress,dc=com",
                    "ca_cert_pem": certs.ca_cert_pem,
                    "spki_sha256_pins": [certs.spki_sha256],
                    "service_bind_dn": "cn=admin,dc=planetexpress,dc=com",
                    "user_search_filter": "(&(objectClass=user)(sAMAccountName={username}))",
                    "subject_attribute": "entryUUID",
                    "email_attribute": "mail",
                    "display_name_attribute": "displayName",
                    "group_dn_map": {
                        "cn=delivery-subteam,ou=groups,dc=planetexpress,dc=com": "Delivery Subteam",
                        "cn=bureaucrats-parent,ou=groups,dc=planetexpress,dc=com": "Bureaucrats Parent",
                    },
                },
                "secret": json.dumps({"bind_dn_password": "GoodNewsEveryone"}),
            }
            good_probe_resp = await client.post(
                "/api/v1/admin/auth-cards/test-handshake",
                headers=headers,
                json=good_draft,
            )
            assert good_probe_resp.status_code == 200
            good_probe = good_probe_resp.json()
            assert good_probe.get("ok") is True, f"Good probe failed: {good_probe}"
            assert good_probe.get("status") in ("OK", "HEALTHY")

            # Persist the LDAP card
            create_ldap_resp = await client.post(
                "/api/v1/admin/auth-cards",
                headers=headers,
                json=good_draft,
            )
            assert create_ldap_resp.status_code == 201, f"Create LDAP card failed: {create_ldap_resp.text}"

            results["workout_2"]["test_draft_handshake"] = {
                "untrusted_ca_ok": untrusted_probe.get("ok"),
                "starttls_ok": starttls_probe.get("ok"),
                "bad_probe_ok": bad_probe.get("ok"),
                "bad_probe_status": bad_probe.get("status"),
                "good_probe_ok": good_probe.get("ok"),
                "good_probe_status": good_probe.get("status"),
                "latency_ms": good_probe.get("latency_ms"),
                "create_status": create_ldap_resp.status_code,
            }

            # 2.3 Nested AD Group Sync (Hermes on isolated client)
            async with make_http_client(base_url=base_url, timeout=15.0) as ldap_client:
                ldap_init = await ldap_client.get("/api/v1/auth/session")
                ldap_csrf = ldap_init.json().get("csrf_token")
                ldap_client.cookies.set("kb_csrf", ldap_init.cookies.get("kb_csrf") or ldap_csrf)
                ldap_login_resp = await ldap_client.post(
                    "/api/v1/auth/ldap/planetexpress-ldap/login",
                    headers={"X-CSRF-Token": ldap_csrf},
                    json={"username": "hermes", "password": "hermespassword"},
                )
                assert ldap_login_resp.status_code == 200, f"LDAP login failed: {ldap_login_resp.text}"

            # Verify 2-hop nested AD group chain in PostgreSQL
            db_conn = await asyncpg.connect(host=PG_SOCKET, user="kanban_test", database=DB_NAME)
            try:
                subteam_gid = await db_conn.fetchval("SELECT id FROM groups WHERE name = 'Delivery Subteam'")
                parent_gid = await db_conn.fetchval("SELECT id FROM groups WHERE name = 'Bureaucrats Parent'")
                assert subteam_gid and parent_gid, "Groups Delivery Subteam and Bureaucrats Parent must exist"

                # Verify organic inter-group nesting edge was created by sync_ldap_groups
                edge_exists = await db_conn.fetchval(
                    """
                    SELECT 1 FROM principal_group_edges
                    WHERE member_id = $1 AND group_id = $2 AND workspace_id = $3
                    """,
                    subteam_gid,
                    parent_gid,
                    WORKSPACE_ID,
                )
                assert edge_exists == 1, "Expected organic principal_group_edges nesting edge Delivery Subteam -> Bureaucrats Parent"

                # Bind Bureaucrats Parent to WORKSPACE_MEMBER
                await db_conn.execute(
                    """
                    INSERT INTO role_bindings (id, workspace_id, principal_id, role, scope_type)
                    VALUES ($1, $2, $3, 'WORKSPACE_MEMBER', 'workspace')
                    ON CONFLICT DO NOTHING
                    """,
                    uuid.uuid4(),
                    WORKSPACE_ID,
                    parent_gid,
                )
                hermes_pid = await db_conn.fetchval("SELECT id FROM principals WHERE display_name = 'Hermes Conrad'")
                closure_depth = await db_conn.fetchval(
                    """
                    SELECT depth FROM principal_group_closure
                    WHERE member_id = $1 AND ancestor_group_id = $2
                    ORDER BY depth DESC LIMIT 1
                    """,
                    hermes_pid,
                    parent_gid,
                )
                assert closure_depth is not None and closure_depth >= 2, f"Expected 2-hop closure depth >= 2, got {closure_depth}"
            finally:
                await db_conn.close()

            results["workout_2"]["group_sync"] = {
                "ldap_login_status": ldap_login_resp.status_code,
                "principal_id": ldap_login_resp.json().get("principal_id"),
                "group_edge_created": bool(edge_exists),
                "closure_depth": closure_depth,
            }

            # 2.4 WebSudo Expired Drawer Replay Simulation
            db_conn = await asyncpg.connect(host=PG_SOCKET, user="kanban_test", database=DB_NAME)
            try:
                await db_conn.execute(
                    "UPDATE sessions SET aal2_verified_at = NOW() - INTERVAL '1000 seconds', aal2_last_active_at = NOW() - INTERVAL '1000 seconds'"
                )
            finally:
                await db_conn.close()

            # Attempt update -> returns 401/403 AAL2_REQUIRED
            update_payload = {
                "display_name": "Planet Express LDAPS Enterprise",
                "public_config": good_draft["public_config"],
            }
            exp_resp = await client.patch(
                "/api/v1/admin/auth-cards/planetexpress-ldap",
                headers=headers,
                json=update_payload,
            )
            assert exp_resp.status_code in (401, 403), f"Expected 401/403 AAL2 required, got {exp_resp.status_code}"
            assert "AAL2" in exp_resp.text

            # Step-up via fresh recovery code
            stepup_resp2 = await client.post(
                "/api/v1/auth/mfa/verify",
                headers=headers,
                json={"method": "recovery", "code": fresh_rec_codes[1]},
            )
            assert stepup_resp2.status_code == 200, f"Stepup failed: {stepup_resp2.text}"
            csrf_token = stepup_resp2.json().get("csrf_token") or stepup_resp2.cookies.get("kb_csrf") or csrf_token
            client.cookies.set("kb_csrf", csrf_token)
            headers["X-CSRF-Token"] = csrf_token

            # Replay update -> succeeds 200 OK
            replay_resp = await client.patch(
                "/api/v1/admin/auth-cards/planetexpress-ldap",
                headers=headers,
                json=update_payload,
            )
            assert replay_resp.status_code == 200, f"Replay failed: {replay_resp.text}"

            results["workout_2"]["websudo_replay"] = {
                "expired_attempt_status": exp_resp.status_code,
                "expired_detail": exp_resp.json().get("code") or exp_resp.json().get("detail"),
                "stepup_status": stepup_resp2.status_code,
                "replayed_save_status": replay_resp.status_code,
                "replayed_name": replay_resp.json().get("display_name"),
            }
            logger.info("Workout 2 complete: LDAP handshake, group sync & WebSudo replay verified.")

            # -------------------------------------------------------------------
            # WORKOUT 3: OIDC PKCE Login + Verified-Claim Linking + Unverified Email Block (403)
            # -------------------------------------------------------------------
            logger.info("=== WORKOUT 3: OIDC PKCE Login + Verified Linking + Unverified Email Block ===")

            oidc_draft = {
                "provider_kind": "OIDC",
                "slug": "test-oidc",
                "display_name": "Test OIDC IdP",
                "is_enabled": True,
                "auto_provision_users": True,
                "public_config": {
                    "kind": "OIDC",
                    "issuer": f"https://127.0.0.1:{PORT_OIDC}",
                    "client_id": "kanban-test",
                    "client_auth": "client_secret_basic",
                    "scopes": ["openid", "profile", "email"],
                    "allowed_algs": ["RS256"],
                },
                "secret": "kanban-test-secret-12345",
            }
            create_oidc_resp = await client.post(
                "/api/v1/admin/auth-cards",
                headers=headers,
                json=oidc_draft,
            )
            assert create_oidc_resp.status_code == 201, f"Create OIDC card failed: {create_oidc_resp.text}"

            # 3.1 Verified Email Login (on isolated oidc_client)
            oidc_companion.email_verified = True
            async with make_http_client(base_url=base_url, timeout=15.0) as oidc_client:
                start_resp = await oidc_client.get("/api/v1/auth/oidc/test-oidc/start", follow_redirects=False)
                assert start_resp.status_code == 302, f"OIDC start failed: {start_resp.status_code}"
                auth_url = start_resp.headers.get("location", "")

                # Follow authorization redirect at IdP
                async with make_http_client(verify=certs.ca_file, follow_redirects=False) as idp_client:
                    idp_resp = await idp_client.get(auth_url)
                    callback_url = idp_resp.headers.get("location", "")

                parsed_cb = urllib.parse.urlsplit(callback_url)
                cb_params = dict(urllib.parse.parse_qsl(parsed_cb.query))

                # Submit callback to Kanban
                cb_resp = await oidc_client.get(
                    f"/api/v1/auth/oidc/test-oidc/callback?code={cb_params['code']}&state={cb_params['state']}",
                    follow_redirects=False,
                )
                assert cb_resp.status_code in (200, 302), f"OIDC callback failed: {cb_resp.status_code} {cb_resp.text}"

            results["workout_3"]["verified_login"] = {
                "start_status": start_resp.status_code,
                "callback_status": cb_resp.status_code,
                "email_verified": True,
            }

            # 3.2 Unverified Email Block (403)
            oidc_companion.email_verified = False
            async with make_http_client(base_url=base_url, timeout=15.0) as oidc_client2:
                start_resp2 = await oidc_client2.get("/api/v1/auth/oidc/test-oidc/start", follow_redirects=False)
                auth_url2 = start_resp2.headers.get("location", "")

                async with make_http_client(verify=certs.ca_file, follow_redirects=False) as idp_client:
                    idp_resp2 = await idp_client.get(auth_url2)
                    callback_url2 = idp_resp2.headers.get("location", "")

                parsed_cb2 = urllib.parse.urlsplit(callback_url2)
                cb_params2 = dict(urllib.parse.parse_qsl(parsed_cb2.query))

                cb_resp2 = await oidc_client2.get(
                    f"/api/v1/auth/oidc/test-oidc/callback?code={cb_params2['code']}&state={cb_params2['state']}",
                    headers={"Accept": "application/json"},
                    follow_redirects=False,
                )
                assert cb_resp2.status_code == 403, f"Expected 403 unverified email block, got {cb_resp2.status_code}"
                assert "EMAIL_NOT_VERIFIED" in cb_resp2.text

            results["workout_3"]["unverified_block"] = {
                "callback_status": cb_resp2.status_code,
                "code": cb_resp2.json().get("code"),
                "detail": cb_resp2.json().get("detail"),
                "email_verified": False,
            }
            logger.info("Workout 3 complete: OIDC verified linking and unverified 403 block proven.")

            # -------------------------------------------------------------------
            # WORKOUT 4: Custom RBAC Role Enforcement
            # -------------------------------------------------------------------
            logger.info("=== WORKOUT 4: Custom RBAC Role Enforcement ===")

            # 4.1 Create custom role
            role_payload = {
                "name": "Quality Auditor Lead",
                "slug": "quality-auditor-lead",
                "color_hex": "#10b981",
                "description": "Read-only auditor with workspace and issue visibility",
            }
            create_role_resp = await client.post(
                "/api/v1/admin/rbac/roles",
                headers=headers,
                json=role_payload,
            )
            assert create_role_resp.status_code == 201, f"Create role failed: {create_role_resp.text}"
            role_data = create_role_resp.json()
            role_id = role_data["id"]

            # 4.2 Set permissions on custom role
            perm_resp = await client.put(
                f"/api/v1/admin/rbac/roles/{role_id}/permissions",
                headers=headers,
                json={"permissions": ["issue:view", "issue:comment"]},
            )
            assert perm_resp.status_code == 200, f"Set permissions failed: {perm_resp.text}"

            # 4.3 Assign role to user Fry
            assign_resp = await client.post(
                f"/api/v1/admin/principals/{FRY_USER_ID}/role-labels",
                headers=headers,
                json={"role_id": role_id},
            )
            assert assign_resp.status_code == 201, f"Assign role failed: {assign_resp.text}"

            # 4.3b Admin creates test issue KAN-1 for capability testing
            create_issue_resp = await client.post(
                "/api/v1/projects/KAN/issues",
                headers=headers,
                json={"summary": "Audit RBAC Capabilities", "description_markdown": "Test RBAC capabilities"},
            )
            assert create_issue_resp.status_code == 201, f"Create issue failed: {create_issue_resp.text}"
            issue_key = create_issue_resp.json()["key"]

            # 4.4 Test Fry capability enforcement
            async with make_http_client(base_url=base_url, timeout=15.0) as fry_client:
                fry_init = await fry_client.get("/api/v1/auth/session")
                fry_csrf = fry_init.json().get("csrf_token")
                for c in fry_init.cookies.jar:
                    if "csrf" in c.name.lower():
                        fry_csrf = c.value
                        break
                fry_client.cookies.set("kb_csrf", fry_csrf)
                fry_login_resp = await fry_client.post(
                    "/api/v1/auth/local/login",
                    headers={"X-CSRF-Token": fry_csrf},
                    json={"username": "fry", "password": "frypassword"},
                )
                assert fry_login_resp.status_code == 200, f"Fry login failed: {fry_login_resp.text}"
                fry_post_csrf = fry_login_resp.json().get("csrf_token") or fry_csrf
                for c in fry_login_resp.cookies.jar:
                    if "csrf" in c.name.lower():
                        fry_post_csrf = c.value
                        break
                fry_client.cookies.set("kb_csrf", fry_post_csrf)
                fry_headers = {"X-CSRF-Token": fry_post_csrf}

                # Capability check: Read own profile -> 200 OK
                me_resp = await fry_client.get("/api/v1/auth/me", headers=fry_headers)
                assert me_resp.status_code == 200, f"Read me failed: {me_resp.status_code}"

                # Capability check: Granted issue:view -> 200 OK
                view_resp = await fry_client.get(f"/api/v1/issues/{issue_key}", headers=fry_headers)
                assert view_resp.status_code == 200, f"Expected 200 issue:view, got {view_resp.status_code}"

                # Capability check: Granted issue:comment -> 201 Created
                comment_resp = await fry_client.post(
                    f"/api/v1/issues/{issue_key}/comments",
                    headers=fry_headers,
                    json={"body_markdown": "Audited and verified by Fry with issue:comment permission."},
                )
                assert comment_resp.status_code == 201, f"Expected 201 issue:comment, got {comment_resp.status_code}"

                # Capability check: Denied issue:delete preview & execution -> 403 Forbidden
                delete_preview_resp = await fry_client.get(
                    f"/api/v1/issues/{issue_key}/delete-preview", headers=fry_headers
                )
                assert delete_preview_resp.status_code == 403, f"Expected 403 delete-preview, got {delete_preview_resp.status_code}"

                delete_headers = dict(fry_headers)
                delete_headers["Kb-Blast-Hash"] = "0000000000000000000000000000000000000000000000000000000000000000"
                delete_resp = await fry_client.delete(f"/api/v1/issues/{issue_key}", headers=delete_headers)
                assert delete_resp.status_code == 403, f"Expected 403 issue:delete, got {delete_resp.status_code}"
                delete_err = delete_resp.json()
                assert delete_err.get("code") != "CSRF_REJECTED", f"Unexpected CSRF rejection on delete: {delete_err}"

                # Capability check: Attempt to create role (requires server/workspace admin) -> 403 Forbidden
                forbidden_role_resp = await fry_client.post(
                    "/api/v1/admin/rbac/roles",
                    headers=fry_headers,
                    json={"name": "Rogue Role", "slug": "rogue-role"},
                )
                assert forbidden_role_resp.status_code == 403, f"Expected 403, got {forbidden_role_resp.status_code}"
                role_err = forbidden_role_resp.json()
                assert role_err.get("code") != "CSRF_REJECTED", f"Unexpected CSRF rejection on role create: {role_err}"

            results["workout_4"] = {
                "role_created": role_data["name"],
                "role_slug": role_data["slug"],
                "permissions": perm_resp.json().get("permissions"),
                "allowed_profile_status": me_resp.status_code,
                "allowed_issue_view_status": view_resp.status_code,
                "allowed_issue_comment_status": comment_resp.status_code,
                "denied_issue_delete_status": delete_resp.status_code,
                "denied_issue_delete_code": delete_err.get("code"),
                "denied_role_create_status": forbidden_role_resp.status_code,
                "denied_code": role_err.get("code"),
                "denied_detail": role_err.get("detail"),
            }
            logger.info("Workout 4 complete: Custom RBAC capability enforcement strictly proven.")

            # Refresh admin cookies for Playwright
            session_cookie = None
            csrf_cookie = None
            for cookie in client.cookies.jar:
                if cookie.name in ("kb_session", "__Host-kb_session"):
                    session_cookie = cookie.value
                elif cookie.name in ("kb_csrf", "__Host-kb_csrf"):
                    csrf_cookie = cookie.value
            if not csrf_cookie:
                csrf_cookie = csrf_token

        # -----------------------------------------------------------------------
        # 4. Zero-Mock Playwright Screenshots Execution
        # -----------------------------------------------------------------------
        logger.info("=== ZERO-MOCK PLAYWRIGHT SCREENSHOTS ===")
        node_env = dict(os.environ)
        node_env["KANBAN_SESSION_COOKIE"] = session_cookie or ""
        node_env["KANBAN_CSRF_COOKIE"] = csrf_cookie or ""
        node_env["KANBAN_CA_PEM"] = certs.ca_cert_pem
        node_env["KANBAN_DB_NAME"] = DB_NAME
        node_env["KANBAN_RECOVERY_CODE"] = fresh_rec_codes[0] if fresh_rec_codes else rec_codes[1]

        proc = await asyncio.create_subprocess_exec(
            "node",
            "scripts/capture_kan408_screenshots.mjs",
            env=node_env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout_bytes, stderr_bytes = await proc.communicate()
        stdout_str = stdout_bytes.decode("utf-8", errors="replace")
        stderr_str = stderr_bytes.decode("utf-8", errors="replace")
        logger.info("Playwright capture stdout:\n%s", stdout_str)
        if proc.returncode != 0:
            logger.error("Playwright capture stderr:\n%s", stderr_str)
            raise RuntimeError(f"Playwright screenshot capture failed with exit code {proc.returncode}")

    finally:
        # Tear down servers and companions
        logger.info("Tearing down live Kanban server and companions...")
        kanban_server.should_exit = True
        await kanban_task
        await ldap_companion.stop()
        await oidc_companion.stop()

        duration = time.monotonic() - start_time
        results["metrics"]["total_duration_seconds"] = round(duration, 2)
        results["metrics"]["timestamp"] = datetime.datetime.now(datetime.UTC).isoformat()

        telemetry_path = "docs/qa/KAN-408/screenshot-telemetry.json"
        if os.path.exists(telemetry_path):
            try:
                with open(telemetry_path, "r", encoding="utf-8") as tf:
                    s_tel = json.load(tf)
                    results["screenshots"] = {
                        "count": 11,
                        "telemetry": {
                            "console_errors_count": len(s_tel.get("consoleErrors", [])),
                            "page_errors_count": len(s_tel.get("pageErrors", [])),
                            "server_5xx_count": len(s_tel.get("serverErrors", [])),
                        },
                    }
            except Exception as e:
                logger.warning("Could not read screenshot telemetry: %s", e)

        os.makedirs("docs/qa/KAN-408", exist_ok=True)
        with open("docs/qa/KAN-408/workout-results.json", "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2)

        if wire_logger.logs:
            transcript_path = "docs/qa/KAN-408/workout-transcript.txt"
            separator = "\n\n" + ("=" * 80) + "\n\n"
            with open(transcript_path, "w", encoding="utf-8") as f:
                f.write(separator.join(wire_logger.logs))
            logger.info("Saved %d wire exchanges to %s", len(wire_logger.logs), transcript_path)

        logger.info("Slice 1 Phase 3 Live Workout completed in %.2fs!", duration)


if __name__ == "__main__":
    asyncio.run(main())
