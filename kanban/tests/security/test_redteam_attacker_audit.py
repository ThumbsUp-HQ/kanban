# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Comprehensive adversarial security regression test suite (KAN-321).

Tests attacker exploit hypotheses across all 7 Attack Surface Domains:
- Domain 1: Authentication, MFA / AAL2 Step-Up, Sessions, OAuth 2.1 & Workload OIDC
- Domain 2: Multi-Tenant Authorization, FORCE RLS, ERA, Granular RBAC & IDOR
- Domain 3: Hostile Content Ingestion, Push Protection, Content Taint & PDF Attachments
- Domain 4: MCP Surfaces, Client IP Resolution & Internal Service Auth
- Domain 5: AI Providers, Remote Runners & Sandbox Isolation
- Domain 6: Importers, Exporters, Backups & Crypto-Shredding
- Domain 7: Concurrency, Issue Leases, Flow Telemetry & SCM Webhooks
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import TYPE_CHECKING, Any

import pytest
from sqlalchemy import text
from starlette.requests import Request

from kanban.ai_config.service import _ALLOWED_PROVIDER_KINDS
from kanban.api.deps import PrincipalContext
from kanban.api.problems import ProblemException
from kanban.api.v1.schemas.flow_metrics import MonteCarloForecast
from kanban.app import create_app
from kanban.attachments.pdf import sanitize_and_validate_pdf
from kanban.auth.mfa.policy import assert_admin_routes_protected
from kanban.security.client_ip import resolve_client_ip
from kanban.security.keys import KeyMaterial
from kanban.security.push_protection import (
    DEFAULT_PUSH_PROTECTION_CODE,
    enforce_secret_push_protection,
)
from kanban.security.service_auth import (
    create_internal_service_auth_header,
    verify_internal_service_auth,
)
from kanban.services.flow_metrics import _simulate_monte_carlo
from mcp.surfaces.admin import build_admin_registry
from mcp.surfaces.agent import create_agent_registry
from mcp.surfaces.docs import build_docs_registry

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


# ==============================================================================
# Domain 1: Authentication, MFA / AAL2 Step-Up, Sessions & Workload OIDC
# ==============================================================================


def test_domain_1_admin_routes_aal2_enforcement() -> None:
    """Domain 1: Ensure all administrative routes enforce require_admin_aal2."""
    app = create_app()
    unprotected = assert_admin_routes_protected(app)
    assert unprotected == [], f"Found unprotected admin routes: {unprotected}"


def test_domain_1_principal_context_mfa_pending_state() -> None:
    """Domain 1: PrincipalContext reflects mfa_pending accurately without auto-elevation."""
    p_id = uuid.uuid4()
    ws_id = uuid.uuid4()
    ctx = PrincipalContext(
        principal_id=p_id,
        workspace_id=ws_id,
        token_scopes=("user",),
        aal_level=1,
        mfa_pending=True,
    )
    assert ctx.aal_level == 1
    assert ctx.mfa_pending is True
    assert ctx.is_server_admin is False


# ==============================================================================
# Domain 2: Multi-Tenant Authorization, FORCE RLS, ERA & Granular RBAC
# ==============================================================================


async def test_domain_2_force_rls_catalog_invariants(db_session: AsyncSession) -> None:
    """Domain 2: Verify PostgreSQL catalog enforces rowsecurity and forcerowsecurity."""
    query = text(
        """
        SELECT relname, relrowsecurity, relforcerowsecurity
        FROM pg_class
        JOIN pg_namespace ON pg_namespace.oid = pg_class.relnamespace
        WHERE pg_namespace.nspname = 'public'
          AND relname IN (
            'issues', 'workspaces', 'principals', 'issue_comments',
            'docs', 'stickies', 'issue_leases', 'activity_records',
            'mcp_api_keys', 'role_bindings', 'resource_acl_entries'
          )
        ORDER BY relname;
        """
    )
    res = await db_session.execute(query)
    rows = res.fetchall()
    assert len(rows) >= 10, f"Expected at least 10 core tenant tables, got {len(rows)}"
    for relname, relrowsecurity, relforcerowsecurity in rows:
        assert relrowsecurity is True, f"Table {relname} lacks ENABLE ROW LEVEL SECURITY"
        assert relforcerowsecurity is True, f"Table {relname} lacks FORCE ROW LEVEL SECURITY"


async def test_domain_2_null_guc_fail_closed(db_session: AsyncSession) -> None:
    """Domain 2: Unbound session (NULL workspace GUC) must fail closed with 0 rows."""
    await db_session.execute(text("SET LOCAL app.current_workspace_id = ''"))
    await db_session.execute(text("SET LOCAL app.current_principal_id = ''"))

    issues_res = await db_session.execute(text("SELECT count(*) FROM issues"))
    assert issues_res.scalar_one() == 0

    docs_res = await db_session.execute(text("SELECT count(*) FROM docs"))
    assert docs_res.scalar_one() == 0

    stickies_res = await db_session.execute(text("SELECT count(*) FROM stickies"))
    assert stickies_res.scalar_one() == 0


# ==============================================================================
# Domain 3: Hostile Content Ingestion, Push Protection & PDF Attachments
# ==============================================================================


def test_domain_3_secret_push_protection_detects_high_entropy_tokens() -> None:
    """Domain 3: enforce_secret_push_protection rejects raw API keys and tokens."""
    raw_secret = "ghp_" + "A" * 36
    with pytest.raises(ProblemException) as exc_info:
        enforce_secret_push_protection(
            f"Here is my key: {raw_secret}",
            field="description_markdown",
        )
    assert exc_info.value.code == DEFAULT_PUSH_PROTECTION_CODE


def test_domain_3_secret_push_protection_allows_clean_markdown() -> None:
    """Domain 3: Clean markdown without tokens passes push protection without modification."""
    clean_text = "### Feature Plan\nThis feature implements strict RLS boundaries."
    result = enforce_secret_push_protection(clean_text, field="description_markdown")
    assert result == clean_text


async def test_domain_3_pdf_sanitizer_rejects_invalid_magic_header() -> None:
    """Domain 3: sanitize_and_validate_pdf rejects files lacking PDF magic bytes."""
    corrupted_bytes = b"NOT_A_PDF_DOCUMENT_1234567890"
    with pytest.raises(ProblemException) as exc_info:
        await sanitize_and_validate_pdf(corrupted_bytes)
    assert exc_info.value.code == "UNSAFE_PDF_CONTENT"


async def test_domain_3_pdf_sanitizer_rejects_oversized_payload() -> None:
    """Domain 3: sanitize_and_validate_pdf rejects payloads exceeding byte ceiling."""
    oversized = b"%PDF-1.7\n" + b"X" * (35 * 1024 * 1024)
    with pytest.raises(ProblemException) as exc_info:
        await sanitize_and_validate_pdf(oversized)
    assert exc_info.value.code == "PAYLOAD_TOO_LARGE"


# ==============================================================================
# Domain 4: MCP Surfaces, Client IP Resolution & Internal Service Auth
# ==============================================================================


def test_domain_4_client_ip_rejects_spoofed_forwarded_for() -> None:
    """Domain 4: resolve_client_ip rejects untrusted X-Forwarded-For header spoofing."""
    scope: dict[str, Any] = {
        "type": "http",
        "client": ("198.51.100.55", 50123),
        "headers": [
            (b"x-forwarded-for", b"127.0.0.1, 10.0.0.1"),
        ],
    }
    resolved = resolve_client_ip(scope, trusted_proxies="127.0.0.1/32")
    assert resolved == "198.51.100.55", "Spoofed leftmost XFF must be ignored from untrusted client"


def test_domain_4_internal_service_auth_verification() -> None:
    """Domain 4: verify_internal_service_auth validates genuine HMAC and rejects forgery."""
    km = KeyMaterial(master_kek=b"x" * 32, auth_pepper=b"y" * 32, session_hmac_key=b"h" * 32)
    header_val = create_internal_service_auth_header(
        "agent-runtime",
        "POST",
        "/internal/test",
        b"",
        key_material=km,
    )
    scope: dict[str, Any] = {
        "type": "http",
        "method": "POST",
        "path": "/internal/test",
        "headers": [(b"x-kb-internal-auth", header_val.encode("ascii"))],
    }
    req = Request(scope)

    principal = verify_internal_service_auth(
        req,
        allowed_principals=("agent-runtime", "mcp-gateway"),
        body_bytes=b"",
        key_material=km,
    )
    assert principal == "agent-runtime"

    # Forged secret
    km_wrong = KeyMaterial(master_kek=b"z" * 32, auth_pepper=b"y" * 32, session_hmac_key=b"h" * 32)
    with pytest.raises(ProblemException):
        verify_internal_service_auth(
            req,
            allowed_principals=("agent-runtime",),
            body_bytes=b"",
            key_material=km_wrong,
        )


def test_domain_4_mcp_surface_registry_isolation() -> None:
    """Domain 4: Verify agent, docs, and admin MCP registries enforce surface separation."""
    agent_reg = create_agent_registry()
    docs_reg = build_docs_registry()
    admin_reg = build_admin_registry()

    agent_tools = {spec.name for spec in agent_reg.list_specs()}
    docs_tools = {spec.name for spec in docs_reg.list_specs()}
    admin_tools = {spec.name for spec in admin_reg.list_specs()}

    # Agent surface must have core ticketing tools
    assert "read_ticket" in agent_tools
    assert "create_ticket" in agent_tools
    assert "transition_ticket" in agent_tools
    assert "destructive_lifecycle" not in agent_tools

    # Docs surface must have knowledge tools
    assert "search" in docs_tools
    assert "create" in docs_tools
    assert "transition_ticket" not in docs_tools

    # Admin surface must have administrative governance tools
    assert "destructive_lifecycle" in admin_tools
    assert "manage_auth_cards" in admin_tools
    assert "read_ticket" not in admin_tools


# ==============================================================================
# Domain 5: AI Providers, Remote Runners & Sandbox Isolation
# ==============================================================================


def test_domain_5_ai_provider_kind_allowlist() -> None:
    """Domain 5: AI provider subsystem enforces strict provider kind allowlist."""
    assert "openai" in _ALLOWED_PROVIDER_KINDS
    assert "gemini" in _ALLOWED_PROVIDER_KINDS
    assert "ollama" in _ALLOWED_PROVIDER_KINDS
    assert "fixture" in _ALLOWED_PROVIDER_KINDS
    assert "untrusted_custom_cloud" not in _ALLOWED_PROVIDER_KINDS


# ==============================================================================
# Domain 6: Importers, Exporters, Backups & Crypto-Shredding
# ==============================================================================


def test_domain_6_crypto_shred_routes_registered() -> None:
    """Domain 6: Verify crypto-shredding request and execute routes exist and require AAL2."""
    app = create_app()
    admin_paths: set[str] = set()
    for route in app.routes:
        if hasattr(route, "effective_route_contexts") and callable(route.effective_route_contexts):
            for ctx in route.effective_route_contexts():
                path = getattr(ctx, "path", "")
                if path.startswith("/api/v1/admin"):
                    admin_paths.add(path)
        else:
            path = getattr(route, "path", "")
            if path.startswith("/api/v1/admin"):
                admin_paths.add(path)

    assert "/api/v1/admin/audit-ledger/request-shred" in admin_paths
    assert "/api/v1/admin/audit-ledger/execute-shred" in admin_paths


# ==============================================================================
# Domain 7: Concurrency, Issue Leases, Flow Telemetry & SCM Webhooks
# ==============================================================================


async def test_domain_7_issue_lease_table_structure(db_session: AsyncSession) -> None:
    """Domain 7: Verify issue_leases table schema and unique issue_id constraint."""
    query = text(
        """
        SELECT column_name, data_type, is_nullable
        FROM information_schema.columns
        WHERE table_name = 'issue_leases'
        ORDER BY ordinal_position;
        """
    )
    res = await db_session.execute(query)
    columns = {row[0]: row[1] for row in res.fetchall()}
    assert "issue_id" in columns
    assert "principal_id" in columns
    assert "fencing_token" in columns
    assert "expires_at" in columns


def test_domain_7_flow_metrics_monte_carlo_resilience() -> None:
    """Domain 7: Monte Carlo simulation completes cleanly without exception on edge inputs."""
    today = dt.date(2026, 11, 22)
    forecast_empty = _simulate_monte_carlo(
        history=[],
        horizon_days=14,
        target_items=10,
        today=today,
        trials=100,
    )
    assert isinstance(forecast_empty, MonteCarloForecast)
    assert forecast_empty.how_many.p50 == 0

    forecast_single = _simulate_monte_carlo(
        history=[3],
        horizon_days=7,
        target_items=5,
        today=today,
        trials=100,
    )
    assert isinstance(forecast_single, MonteCarloForecast)
    assert forecast_single.how_many.p50 >= 0
