# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Security unit and integration tests for internal MCP route isolation & service auth (KAN-63)."""

from __future__ import annotations

import base64
import datetime as dt
import hashlib
import json
import time
import uuid
from typing import TYPE_CHECKING, Any

import httpx
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID
from sqlalchemy import text
from starlette.requests import Request

from database.session import RLSSessionFactory
from kanban.api.problems import ProblemException
from kanban.app import create_app, create_internal_app
from kanban.security.ephemeral_mcp_tokens import EPHEMERAL_TOKEN_PREFIX
from kanban.security.keys import KeyMaterial
from kanban.security.service_auth import (
    create_internal_service_auth_header,
    derive_internal_service_key,
    verify_internal_service_auth,
)
from kanban.settings import Settings
from kanban.tests.security.helpers import (
    add_acl_entry,
    create_agent,
    create_project,
    create_user,
    create_workspace,
    rebuild_era,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode("ascii").rstrip("=")


@pytest.fixture(autouse=True)
def setup_test_key_material(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set up valid test key material in environment."""
    monkeypatch.delenv("KANBAN_KEYRING_FILE", raising=False)
    monkeypatch.setenv("KANBAN_MASTER_KEK", _b64(b"k" * 32))
    monkeypatch.setenv("KANBAN_AUTH_PEPPER", _b64(b"p" * 32))
    monkeypatch.setenv("KANBAN_SESSION_HMAC_KEY", _b64(b"s" * 32))
    monkeypatch.setenv("KANBAN_MASTER_KEK_KID", "test-kid-1")


async def seed_bound_execution(  # noqa: PLR0913
    session: AsyncSession,
    *,
    ws_id: uuid.UUID,
    proj_id: uuid.UUID,
    invoking_principal_id: uuid.UUID,
    agent_principal_id: uuid.UUID,
    status: str = "pending_async",
    execution_id: uuid.UUID | None = None,
    attach_hook: bool = True,
) -> uuid.UUID:
    """Seed an issue, agent_definition, workflow_transition_hook, and execution row."""
    for pid in (invoking_principal_id, agent_principal_id):
        await session.execute(
            text(
                "INSERT INTO resource_acl_entries ("
                "  workspace_id, object_id, principal_id, effect, capability_mask"
                ") VALUES (:ws_id, :obj_id, :p_id, 'ALLOW', 15) "
                "ON CONFLICT (object_id, principal_id, effect) DO NOTHING"
            ),
            {"ws_id": ws_id, "obj_id": proj_id, "p_id": pid},
        )

    state_rows = (
        await session.execute(
            text("SELECT id FROM workflow_states WHERE project_id = :p LIMIT 2"),
            {"p": proj_id},
        )
    ).fetchall()
    from_state_id = state_rows[0][0]
    to_state_id = state_rows[1][0] if len(state_rows) > 1 else state_rows[0][0]

    pri_id = (
        await session.execute(
            text("SELECT id FROM project_priorities WHERE project_id = :p LIMIT 1"),
            {"p": proj_id},
        )
    ).scalar_one()

    proj_row = (
        await session.execute(
            text(
                "UPDATE projects SET issue_seq_counter = issue_seq_counter + 1 "
                "WHERE id = :p RETURNING identifier, issue_seq_counter"
            ),
            {"p": proj_id},
        )
    ).one()
    proj_identifier, seq_num = str(proj_row[0]), int(proj_row[1])

    issue_id = uuid.uuid4()
    ckey = f"{proj_identifier}-{seq_num}"
    await session.execute(
        text(
            "SELECT register_object("
            "  'issue'::object_kind, :ws, :proj, :ckey, 'Test Issue', :cr, :id"
            ")"
        ),
        {"ws": ws_id, "proj": proj_id, "ckey": ckey, "cr": invoking_principal_id, "id": issue_id},
    )
    await session.execute(
        text(
            "INSERT INTO issues ("
            "  id, object_type, workspace_id, project_id, sequence_id, summary, "
            "  description_markdown, state_id, priority_id, created_by_id, "
            "  original_created_by_id, board_rank, ancestry_path"
            ") VALUES ("
            "  :id, 'issue', :ws, :proj, :seq, 'Test Issue', 'Body', :st, :pri, :cr, :cr, "
            "  :rank, 'top'"
            ")"
        ),
        {
            "id": issue_id,
            "ws": ws_id,
            "proj": proj_id,
            "seq": seq_num,
            "st": from_state_id,
            "pri": pri_id,
            "cr": invoking_principal_id,
            "rank": f"a{seq_num}",
        },
    )
    await add_acl_entry(
        session, ws_id, issue_id, invoking_principal_id, effect="ALLOW", capability_mask=15
    )
    await rebuild_era(session, ws_id)

    if attach_hook:
        agent_def_id = uuid.uuid4()
        slug = f"agent-def-{uuid.uuid4().hex[:10]}"
        await session.execute(
            text(
                "INSERT INTO agent_definitions ("
                "  id, workspace_id, project_id, principal_id, slug, display_name, "
                "  harness_kind, provider_kind, model_id"
                ") VALUES ("
                "  :id, :ws, :proj, :pid, :slug, 'Gate Agent', 'in_app_sdk', 'fixture', 'fixture-1'"
                ")"
            ),
            {
                "id": agent_def_id,
                "ws": ws_id,
                "proj": proj_id,
                "pid": agent_principal_id,
                "slug": slug,
            },
        )
        hook_id = uuid.uuid4()
        await session.execute(
            text(
                "INSERT INTO workflow_transition_hooks ("
                "  id, workspace_id, project_id, name, from_state_id, to_state_id, "
                "  hook_kind, sort_rank, is_enabled, agent_definition_id, manifest_sha256"
                ") VALUES ("
                "  :id, :ws, :proj, 'qa-gate', :fst, :tst, 'agent_interceptor', :rank, TRUE, "
                "  :ad_id, :sha"
                ")"
            ),
            {
                "id": hook_id,
                "ws": ws_id,
                "proj": proj_id,
                "fst": from_state_id,
                "tst": to_state_id,
                "rank": f"h{seq_num}",
                "ad_id": agent_def_id,
                "sha": hashlib.sha256(b"hook-manifest").digest(),
            },
        )

    exec_id = execution_id or uuid.uuid4()
    await session.execute(
        text(
            "INSERT INTO workflow_transition_executions ("
            "  id, workspace_id, project_id, issue_id, invoking_principal_id, "
            "  from_state_id, to_state_id, status, hop_depth, issue_body_sha256_snapshot"
            ") VALUES ("
            "  :id, :ws, :proj, :iss, :inv, :fst, :tst, :status, 0, :sha"
            ")"
        ),
        {
            "id": exec_id,
            "ws": ws_id,
            "proj": proj_id,
            "iss": issue_id,
            "inv": invoking_principal_id,
            "fst": from_state_id,
            "tst": to_state_id,
            "status": status,
            "sha": hashlib.sha256(b"Body").digest(),
        },
    )
    return exec_id


@pytest.mark.asyncio
async def test_case_1_positive_verified_service_auth_and_bound_execution(
    db_session: AsyncSession,
) -> None:
    """Case 1: Verified agent-runtime mints (201) for active execution; mcp-gateway introspects."""
    ws_id = await create_workspace(db_session, name="WS-KAN63-1")
    user_id = await create_user(db_session, ws_id, handle="@adam63", display_name="Adam 63")
    agent_id = await create_agent(db_session, ws_id, display_name="agent-63")
    proj_id = await create_project(
        db_session, ws_id, identifier="K63A", name="KAN-63 Project A", created_by_id=user_id
    )
    exec_id = await seed_bound_execution(
        db_session,
        ws_id=ws_id,
        proj_id=proj_id,
        invoking_principal_id=user_id,
        agent_principal_id=agent_id,
        status="pending_async",
    )
    await db_session.commit()

    app = create_app(Settings())
    app.state.session_factory = RLSSessionFactory(db_session.bind)  # type: ignore[arg-type]
    internal_app = create_internal_app(app)

    mint_path = "/internal/v1/mcp/ephemeral-tokens"
    mint_payload = {
        "workspace_id": str(ws_id),
        "execution_id": str(exec_id),
        "invoking_principal_id": str(user_id),
        "agent_principal_id": str(agent_id),
        "project_id": str(proj_id),
        "ttl_seconds": 60,
        "max_calls": 5,
    }
    mint_body = json.dumps(mint_payload).encode("utf-8")
    mint_auth = create_internal_service_auth_header(
        principal="agent-runtime",
        method="POST",
        path=mint_path,
        body_bytes=mint_body,
    )

    transport = httpx.ASGITransport(app=internal_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://internal.test") as client:
        # 1. Valid agent-runtime signature mints ephemeral token (201)
        res_mint = await client.post(
            mint_path,
            content=mint_body,
            headers={
                "Content-Type": "application/json",
                "X-KB-Internal-Auth": mint_auth,
            },
        )
        assert res_mint.status_code == 201
        mint_data = res_mint.json()
        token = mint_data["token"]
        assert token.startswith(EPHEMERAL_TOKEN_PREFIX)

        # 2. Valid mcp-gateway signature introspects token (200)
        intro_path = "/internal/v1/mcp/introspect"
        intro_body = json.dumps({"token": token, "surface": "agent", "consume_call": False}).encode(
            "utf-8"
        )
        intro_auth = create_internal_service_auth_header(
            principal="mcp-gateway",
            method="POST",
            path=intro_path,
            body_bytes=intro_body,
        )
        res_intro = await client.post(
            intro_path,
            content=intro_body,
            headers={
                "Content-Type": "application/json",
                "X-KB-Internal-Auth": intro_auth,
            },
        )
        assert res_intro.status_code == 200
        assert res_intro.json()["active"] is True
        assert res_intro.json()["execution_id"] == str(exec_id)

        # 3. Valid mcp-gateway signature revokes token by execution_id (200)
        revoke_path = f"/internal/v1/mcp/ephemeral-tokens/by-execution/{exec_id}/revoke"
        revoke_auth = create_internal_service_auth_header(
            principal="mcp-gateway",
            method="POST",
            path=revoke_path,
            body_bytes=b"",
        )
        res_revoke = await client.post(
            revoke_path,
            headers={"X-KB-Internal-Auth": revoke_auth},
        )
        assert res_revoke.status_code == 200
        assert res_revoke.json()["revoked_count"] == 1


@pytest.mark.asyncio
async def test_case_2_negative_public_route_removal_and_spoofed_headers_rejected(
    db_session: AsyncSession,
) -> None:
    """Case 2: /api/v1/internal/* and public /internal/* return 404; spoofed headers return 401."""
    app = create_app(Settings())
    app.state.session_factory = RLSSessionFactory(db_session.bind)  # type: ignore[arg-type]
    internal_app = create_internal_app(app)

    exec_id = uuid.uuid4()
    spoof_headers = {
        "X-KB-Service-Principal": "agent-runtime",
        "X-Client-Cert-CN": "agent-runtime",
        "X-SSL-Client-CN": "agent-runtime",
        "X-SSL-Client-Cert": "test-cert-agent-runtime",
        "Authorization": "Bearer fake-token",
    }

    # Verify public OpenAPI schema contains zero /internal/ routes
    schema_paths = list(app.openapi().get("paths", {}).keys())
    assert not any("/internal" in p for p in schema_paths)

    pub_transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=pub_transport, base_url="http://public.test"
    ) as pub_client:
        for path in (
            "/api/v1/internal/v1/mcp/ephemeral-tokens",
            f"/api/v1/internal/v1/mcp/ephemeral-tokens/by-execution/{exec_id}/revoke",
            "/api/v1/internal/v1/mcp/introspect",
            "/api/v1/internal/mcp/introspect",
            "/internal/v1/mcp/ephemeral-tokens",
            f"/internal/v1/mcp/ephemeral-tokens/by-execution/{exec_id}/revoke",
            "/internal/v1/mcp/introspect",
            "/internal/mcp/introspect",
        ):
            res_pub = await pub_client.post(path, json={"token": "x"}, headers=spoof_headers)
            assert res_pub.status_code == 404, f"Expected 404 on public app for {path}"

    # Verify internal_app rejects raw spoofed headers with 401 AUTHENTICATION_REQUIRED
    int_transport = httpx.ASGITransport(app=internal_app)
    async with httpx.AsyncClient(
        transport=int_transport, base_url="http://internal.test"
    ) as int_client:
        for int_path in (
            "/internal/v1/mcp/ephemeral-tokens",
            f"/internal/v1/mcp/ephemeral-tokens/by-execution/{exec_id}/revoke",
            "/internal/v1/mcp/introspect",
            "/internal/mcp/introspect",
        ):
            res_spoof = await int_client.post(
                int_path,
                json={"token": "x"},
                headers=spoof_headers,
            )
            assert res_spoof.status_code == 401
            assert res_spoof.json()["code"] == "AUTHENTICATION_REQUIRED"


@pytest.mark.asyncio
async def test_case_3_edge_cross_role_escalation_tampering_and_fabricated_execution(  # noqa: PLR0915
    db_session: AsyncSession,
) -> None:
    """Case 3: Cross-role 403, body/method/path/clock tampering 401, fabricated execution 403."""
    ws_id = await create_workspace(db_session, name="WS-KAN63-3")
    user_id = await create_user(db_session, ws_id, handle="@user63c", display_name="User 63C")
    other_user_id = await create_user(db_session, ws_id, handle="@other63c", display_name="Other")
    agent_id = await create_agent(db_session, ws_id, display_name="agent-63c")
    unbound_agent_id = await create_agent(db_session, ws_id, display_name="unbound-agent-63c")
    proj_id = await create_project(
        db_session, ws_id, identifier="K63C", name="KAN-63 Project C", created_by_id=user_id
    )
    active_exec_id = await seed_bound_execution(
        db_session,
        ws_id=ws_id,
        proj_id=proj_id,
        invoking_principal_id=user_id,
        agent_principal_id=agent_id,
        status="running_sync",
    )
    completed_exec_id = await seed_bound_execution(
        db_session,
        ws_id=ws_id,
        proj_id=proj_id,
        invoking_principal_id=user_id,
        agent_principal_id=agent_id,
        status="approved",
    )
    await db_session.commit()

    app = create_app(Settings())
    app.state.session_factory = RLSSessionFactory(db_session.bind)  # type: ignore[arg-type]
    internal_app = create_internal_app(app)

    mint_path = "/internal/v1/mcp/ephemeral-tokens"
    base_payload: dict[str, Any] = {
        "workspace_id": str(ws_id),
        "execution_id": str(active_exec_id),
        "invoking_principal_id": str(user_id),
        "agent_principal_id": str(agent_id),
        "project_id": str(proj_id),
        "ttl_seconds": 60,
        "max_calls": 5,
    }
    base_body = json.dumps(base_payload).encode("utf-8")

    transport = httpx.ASGITransport(app=internal_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://internal.test") as client:
        # 1. Valid mcp-gateway signature calling /internal/v1/mcp/ephemeral-tokens -> 403 FORBIDDEN
        gw_hdr = create_internal_service_auth_header(
            principal="mcp-gateway",
            method="POST",
            path=mint_path,
            body_bytes=base_body,
        )
        res_gw = await client.post(
            mint_path,
            content=base_body,
            headers={"Content-Type": "application/json", "X-KB-Internal-Auth": gw_hdr},
        )
        assert res_gw.status_code == 403
        assert res_gw.json()["code"] == "FORBIDDEN"

        # 2. Tampered JSON body with valid signature over original body -> 401
        valid_agent_hdr = create_internal_service_auth_header(
            principal="agent-runtime",
            method="POST",
            path=mint_path,
            body_bytes=base_body,
        )
        tampered_body = json.dumps({**base_payload, "max_calls": 25}).encode("utf-8")
        res_tampered_body = await client.post(
            mint_path,
            content=tampered_body,
            headers={"Content-Type": "application/json", "X-KB-Internal-Auth": valid_agent_hdr},
        )
        assert res_tampered_body.status_code == 401
        assert res_tampered_body.json()["code"] == "AUTHENTICATION_REQUIRED"

        # 3. Signature bound to wrong HTTP method or wrong path -> 401
        wrong_method_hdr = create_internal_service_auth_header(
            principal="agent-runtime",
            method="GET",
            path=mint_path,
            body_bytes=base_body,
        )
        res_wrong_method = await client.post(
            mint_path,
            content=base_body,
            headers={"Content-Type": "application/json", "X-KB-Internal-Auth": wrong_method_hdr},
        )
        assert res_wrong_method.status_code == 401

        wrong_path_hdr = create_internal_service_auth_header(
            principal="agent-runtime",
            method="POST",
            path="/internal/v1/mcp/introspect",
            body_bytes=base_body,
        )
        res_wrong_path = await client.post(
            mint_path,
            content=base_body,
            headers={"Content-Type": "application/json", "X-KB-Internal-Auth": wrong_path_hdr},
        )
        assert res_wrong_path.status_code == 401

        # 4. Clock skew > 300s -> 401
        expired_hdr = create_internal_service_auth_header(
            principal="agent-runtime",
            method="POST",
            path=mint_path,
            body_bytes=base_body,
            timestamp=time.time() - 360,
        )
        res_expired = await client.post(
            mint_path,
            content=base_body,
            headers={"Content-Type": "application/json", "X-KB-Internal-Auth": expired_hdr},
        )
        assert res_expired.status_code == 401

        # 5. Fabricated (non-existent) execution_id -> 422 INVALID_EXECUTION
        fab_body = json.dumps({**base_payload, "execution_id": str(uuid.uuid4())}).encode("utf-8")
        fab_hdr = create_internal_service_auth_header(
            principal="agent-runtime",
            method="POST",
            path=mint_path,
            body_bytes=fab_body,
        )
        res_fab = await client.post(
            mint_path,
            content=fab_body,
            headers={"Content-Type": "application/json", "X-KB-Internal-Auth": fab_hdr},
        )
        assert res_fab.status_code == 422
        assert res_fab.json()["code"] == "INVALID_EXECUTION"

        # 6. Completed execution_id -> 422 INACTIVE_EXECUTION
        comp_body = json.dumps({**base_payload, "execution_id": str(completed_exec_id)}).encode(
            "utf-8"
        )
        comp_hdr = create_internal_service_auth_header(
            principal="agent-runtime",
            method="POST",
            path=mint_path,
            body_bytes=comp_body,
        )
        res_comp = await client.post(
            mint_path,
            content=comp_body,
            headers={"Content-Type": "application/json", "X-KB-Internal-Auth": comp_hdr},
        )
        assert res_comp.status_code == 422
        assert res_comp.json()["code"] == "INACTIVE_EXECUTION"

        # 7. Mismatched invoking_principal_id tuple -> 403 EXECUTION_SCOPE_MISMATCH
        mis_inv_body = json.dumps(
            {**base_payload, "invoking_principal_id": str(other_user_id)}
        ).encode("utf-8")
        mis_inv_hdr = create_internal_service_auth_header(
            principal="agent-runtime",
            method="POST",
            path=mint_path,
            body_bytes=mis_inv_body,
        )
        res_mis_inv = await client.post(
            mint_path,
            content=mis_inv_body,
            headers={"Content-Type": "application/json", "X-KB-Internal-Auth": mis_inv_hdr},
        )
        assert res_mis_inv.status_code == 403
        assert res_mis_inv.json()["code"] == "EXECUTION_SCOPE_MISMATCH"

        # 8. Unbound agent_principal_id -> 403 EXECUTION_AGENT_MISMATCH
        mis_agt_body = json.dumps(
            {**base_payload, "agent_principal_id": str(unbound_agent_id)}
        ).encode("utf-8")
        mis_agt_hdr = create_internal_service_auth_header(
            principal="agent-runtime",
            method="POST",
            path=mint_path,
            body_bytes=mis_agt_body,
        )
        res_mis_agt = await client.post(
            mint_path,
            content=mis_agt_body,
            headers={"Content-Type": "application/json", "X-KB-Internal-Auth": mis_agt_hdr},
        )
        assert res_mis_agt.status_code == 403
        assert res_mis_agt.json()["code"] == "EXECUTION_AGENT_MISMATCH"


def _generate_x509_cert(cn: str, san_uri: str | None = None) -> x509.Certificate:
    priv_key = ec.generate_private_key(ec.SECP256R1())
    subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])
    now = dt.datetime.now(dt.UTC)
    builder = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(priv_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(minutes=5))
        .not_valid_after(now + dt.timedelta(hours=1))
    )
    if san_uri:
        builder = builder.add_extension(
            x509.SubjectAlternativeName(
                [
                    x509.DNSName(f"{cn}.internal"),
                    x509.UniformResourceIdentifier(san_uri),
                ]
            ),
            critical=False,
        )
    return builder.sign(priv_key, hashes.SHA256())


def test_case_4_service_auth_unit_and_x509_client_cert_branches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Case 4: Direct unit tests for HKDF key derivation, X.509 CN/SAN parsing, and edge cases."""
    # 1. Invalid principal rejected on key derivation
    with pytest.raises(ValueError, match="Unknown internal service principal"):
        derive_internal_service_key("malicious-principal")

    # 2. Explicit KeyMaterial and fallback root key resolution
    explicit_km = KeyMaterial(
        master_kek=b"a" * 32,
        auth_pepper=b"b" * 32,
        session_hmac_key=b"c" * 32,
    )
    hdr = create_internal_service_auth_header(
        principal="kanban-api",
        method="POST",
        path="/internal/v1/mcp/ephemeral-tokens",
        body_bytes="{}",
        key_material=explicit_km,
    )
    req_ok = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/internal/v1/mcp/ephemeral-tokens",
            "headers": [(b"x-kb-internal-auth", hdr.encode("ascii"))],
        }
    )
    assert (
        verify_internal_service_auth(
            req_ok,
            allowed_principals=("kanban-api",),
            body_bytes="{}",
            key_material=explicit_km,
        )
        == "kanban-api"
    )

    # 3. Malformed header strings rejected with 401
    for bad_hdr in (
        "invalid",
        "t=123,t=456,p=mcp-gateway,v2=abc",
        "t=notanint,p=mcp-gateway,v2=abc",
        "t=123,p=unknown-role,v2=abc",
        "t=123,p=mcp-gateway",
    ):
        req_bad = Request(
            {
                "type": "http",
                "method": "POST",
                "path": "/internal/v1/mcp/introspect",
                "headers": [(b"x-kb-internal-auth", bad_hdr.encode("ascii"))],
            }
        )
        with pytest.raises(ProblemException) as exc_info:
            verify_internal_service_auth(req_bad, allowed_principals=("mcp-gateway",))
        assert exc_info.value.status == 401

    # 4. Verified ASGI scope["client_cert"] X.509 Certificate object & PEM bytes
    cert_obj = _generate_x509_cert(
        "agent-runtime", san_uri="spiffe://kanban.internal/ns/default/sa/agent-runtime"
    )
    req_cert_obj = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/internal/v1/mcp/ephemeral-tokens",
            "headers": [],
            "client_cert": cert_obj,
        }
    )
    assert (
        verify_internal_service_auth(req_cert_obj, allowed_principals=("agent-runtime",))
        == "agent-runtime"
    )

    pem_bytes = cert_obj.public_bytes(serialization.Encoding.PEM)
    req_cert_pem = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/internal/v1/mcp/ephemeral-tokens",
            "headers": [],
            "client_cert": pem_bytes.decode("ascii"),
        }
    )
    assert (
        verify_internal_service_auth(req_cert_pem, allowed_principals=("agent-runtime",))
        == "agent-runtime"
    )

    # 5. Peer cert dictionary format (ssl.getpeercert() style) & matching HMAC+cert
    peer_dict = {
        "subject": ((("commonName", "mcp-gateway.internal"),),),
        "subjectAltName": (("DNS", "mcp-gateway.internal"), ("URI", "spiffe://k/sa/mcp-gateway")),
    }
    req_peer_dict = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/internal/v1/mcp/introspect",
            "headers": [],
            "client_cert": peer_dict,
        }
    )
    assert (
        verify_internal_service_auth(req_peer_dict, allowed_principals=("mcp-gateway",))
        == "mcp-gateway"
    )

    # Matching HMAC and client_cert succeeds
    req_match_both = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/internal/v1/mcp/ephemeral-tokens",
            "headers": [(b"x-kb-internal-auth", hdr.encode("ascii"))],
            "client_cert": {"cn": "kanban-api"},
        }
    )
    assert (
        verify_internal_service_auth(
            req_match_both,
            allowed_principals=("kanban-api",),
            body_bytes="{}",
            key_material=explicit_km,
        )
        == "kanban-api"
    )

    # X.509 cert without SAN extension and with body_bytes=None
    cert_no_san = _generate_x509_cert("kanban-api", san_uri=None)
    hdr_none_body = create_internal_service_auth_header(
        principal="kanban-api",
        method="POST",
        path="/internal/v1/mcp/introspect",
        body_bytes=None,
    )
    req_no_san = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/internal/v1/mcp/introspect",
            "headers": [(b"x-kb-internal-auth", hdr_none_body.encode("ascii"))],
            "client_cert": cert_no_san,
        }
    )
    assert (
        verify_internal_service_auth(req_no_san, allowed_principals=("kanban-api",)) == "kanban-api"
    )

    # Non-PEM string or empty candidate in scope["client_cert"] -> 401
    for bad_cert_val in ("plain-non-pem-string", {"cn": "   "}):
        req_non_pem = Request(
            {
                "type": "http",
                "method": "POST",
                "path": "/internal/v1/mcp/introspect",
                "headers": [],
                "client_cert": bad_cert_val,
            }
        )
        with pytest.raises(ProblemException) as exc_non_pem:
            verify_internal_service_auth(req_non_pem, allowed_principals=("mcp-gateway",))
        assert exc_non_pem.value.status == 401

    # 6. Mismatched HMAC principal vs client_cert principal -> 401
    req_mismatch_cert = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/internal/v1/mcp/ephemeral-tokens",
            "headers": [(b"x-kb-internal-auth", hdr.encode("ascii"))],
            "client_cert": peer_dict,
        }
    )
    with pytest.raises(ProblemException) as exc_mis:
        verify_internal_service_auth(
            req_mismatch_cert,
            allowed_principals=("kanban-api", "mcp-gateway"),
            body_bytes="{}",
            key_material=explicit_km,
        )
    assert exc_mis.value.status == 401

    # 7. Unrecognized client_cert -> 401
    req_unknown_cert = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/internal/v1/mcp/introspect",
            "headers": [],
            "client_cert": {"cn": "untrusted-caller", "san": ["other.local"]},
        }
    )
    with pytest.raises(ProblemException) as exc_unk:
        verify_internal_service_auth(req_unknown_cert, allowed_principals=("mcp-gateway",))
    assert exc_unk.value.status == 401

    # 8. Corrupt PEM in scope["client_cert"] -> 401
    req_bad_pem = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/internal/v1/mcp/introspect",
            "headers": [],
            "client_cert": "-----BEGIN CERTIFICATE-----\nnot-valid-der\n-----END CERTIFICATE-----",
        }
    )
    with pytest.raises(ProblemException) as exc_pem:
        verify_internal_service_auth(req_bad_pem, allowed_principals=("mcp-gateway",))
    assert exc_pem.value.status == 401

    # 9. Standalone create_internal_app() without owner_app
    standalone_internal = create_internal_app()
    assert standalone_internal.state.session_factory is None

    # 10. Process fallback key when no environment variables are set
    monkeypatch.delenv("KANBAN_MASTER_KEK", raising=False)
    monkeypatch.delenv("KANBAN_AUTH_PEPPER", raising=False)
    monkeypatch.delenv("KANBAN_SESSION_HMAC_KEY", raising=False)
    fb_hdr = create_internal_service_auth_header(
        "mcp-gateway", "POST", "/internal/v1/mcp/introspect"
    )
    req_fb = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/internal/v1/mcp/introspect",
            "headers": [(b"x-kb-internal-auth", fb_hdr.encode("ascii"))],
        }
    )
    assert (
        verify_internal_service_auth(req_fb, allowed_principals=("mcp-gateway",)) == "mcp-gateway"
    )
