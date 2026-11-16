# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""World-class platform standards verification tests (KANBA-182 / GitHub Issue #1)."""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import TYPE_CHECKING, Any

import anyio
import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import text

from kanban.api.v1.system import PlatformSummaryResponse, get_platform_summary
from kanban.api.v1.system import router as system_router
from kanban.content.normalize import normalize_to_markdown
from kanban.content.unicode_guard import (
    ContentNormalizeError,
    strip_invisible_and_control_chars,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


def _estimate_tokens(text_content: str) -> int:
    """Heuristic token estimator (1 token ~ 4 characters)."""
    return (len(text_content) + 3) // 4


def _check_migration_ddl() -> None:
    """Verify migration file DDL synchronously to avoid async blocking warnings."""
    migration_file = Path("database/migrations/sql/p1_14_force_rls.up.sql")
    assert migration_file.exists(), f"Missing migration file: {migration_file}"
    migration_content = migration_file.read_text(encoding="utf-8")
    assert "FORCE ROW LEVEL SECURITY" in migration_content


def _assert_summary_pillars(summary: PlatformSummaryResponse) -> None:
    """Verify all 4 core pillars and parity matrix on PlatformSummaryResponse."""
    assert summary.platform == "👍kanban"
    assert summary.slug == "thumbs-up-kanban"
    assert summary.license == "Apache-2.0"
    assert summary.version == "2.0.0"
    assert summary.github_issue_1_resolved is True

    # Pillar 1: Native Agent-First Architecture
    p1 = summary.pillar_1_agent_first
    assert "/mcp/agent" in p1.mcp_surfaces
    assert "/mcp/docs" in p1.mcp_surfaces
    assert "/mcp/admin" in p1.mcp_surfaces
    assert "summary" in p1.lod_tiers
    assert p1.summary_token_budget <= 1000
    assert "agy -p" in p1.cli_pipe_harnesses
    assert "codex -p" in p1.cli_pipe_harnesses
    assert "gemini" in p1.ai_providers
    assert "Claude Code" in p1.agent_harnesses_supported

    # Pillar 2: Priority #0 Hardened Security
    p2 = summary.pillar_2_security_first
    assert p2.force_rls is True
    assert p2.surrogate_rejection is True
    assert p2.zero_plaintext_secrets is True
    assert p2.aal2_admin_enforcement is True
    assert p2.csp_hardened is True

    # Pillar 3: Friction-Free FOSS Deployment
    p3 = summary.pillar_3_friction_free
    assert p3.standalone_single_container is True
    assert p3.docker_compose_production is True
    assert p3.sub_3s_startup is True
    assert p3.zero_cloud_telemetry is True
    assert p3.air_gap_ready is True

    # Pillar 4: Enterprise Whitespace & High-Ergonomics UI
    p4 = summary.pillar_4_enterprise_ux
    assert p4.whitespace_optimized is True
    assert p4.emoji_hover_elaboration is True
    assert p4.sparkle_cursor_completion is True
    assert p4.canonical_markdown_storage is True
    assert p4.safe_mermaid_rendering is True
    assert p4.optimistic_drag_and_drop is True

    # Competitive Parity Matrix
    parity = summary.parity_matrix
    assert parity.zero_saas_paywalls is True
    assert parity.unlimited_seats is True
    assert parity.unlimited_mcp_keys is True
    assert "Jira" in parity.competitive_parity
    assert "Plane" in parity.competitive_parity
    assert "Vibe Kanban" in parity.competitive_parity


def test_mcp_compact_token_budget() -> None:
    """Assert summary LOD tool responses stay strictly <1000 tokens (<4000 chars).

    Prevents context exhaustion across autonomous agents (Claude Code, OpenAI Codex,
    and Gemini CLI / Antigravity).
    """
    mcp_lod = importlib.import_module("mcp.lod")
    mcp_yaml = importlib.import_module("mcp.yaml_out")

    lod_summary = mcp_lod.Lod.SUMMARY
    lod_full = mcp_lod.Lod.FULL
    dump_yaml = mcp_yaml.dump_yaml
    raw_desc = "# Extensive Description\n" + "Long specification text block. " * 300
    raw_issue: dict[str, Any] = {
        "key": "KANBA-182",
        "summary": "World-Class Kanban Platform: Address GitHub Issue #1",
        "state": "In Progress",
        "priority": "P0",
        "assignees": [f"agent-worker-{i:03d}" for i in range(15)],
        "workspace": "kanban",
        "description_markdown": raw_desc,
        "labels": ["platform", "security", "agent-first", "core", "standards"],
        "cycle": "Cycle 42",
        "modules": ["kanban", "database", "mcp", "agent"],
        "parent": "KANBA-1",
        "start_date": "2026-11-01",
        "due_date": "2026-11-30",
        "links": [{"type": "relates_to", "target": f"KANBA-{j}"} for j in range(20)],
        "etag": "W/deadbeef12345678",
        "access": {"users": ["sec-lead", "platform-lead"], "groups": ["engineering"]},
        "access_manifest": {"raw_details": "x" * 2048},
        "custom_fields": {f"custom_field_{k}": f"value_{k}" for k in range(30)},
        "comments": [
            {"author": f"commenter_{c}", "body": f"Forensic audit trail comment {c}"}
            for c in range(25)
        ],
        "activity": [
            {"timestamp": f"2026-11-15T{h:02d}:00:00Z", "event": "transition"} for h in range(24)
        ],
        "gate_verdicts": {"qa": "READY", "ui": "APPROVED", "api": "APPROVED"},
        "provenance": {"origin": "cli", "harness": "agy -p"},
    }

    # 1. Project Issue under Lod.SUMMARY and serialize to YAML
    projected_issue = mcp_lod.project_issue(raw_issue, lod_summary)
    issue_yaml = dump_yaml(projected_issue)
    issue_tokens = _estimate_tokens(issue_yaml)

    assert len(issue_yaml) < 4000, f"Summary issue YAML exceeds 4000 chars: {len(issue_yaml)}"
    assert issue_tokens < 1000, f"Summary issue YAML exceeds 1000 tokens: {issue_tokens}"
    assert "description_markdown" not in projected_issue
    assert "custom_fields" not in projected_issue
    assert "comments" not in projected_issue

    # 2. Compare against Lod.FULL to prove compression ratio
    full_issue = mcp_lod.project_issue(raw_issue, lod_full)
    full_yaml = dump_yaml(full_issue)
    assert len(full_yaml) > len(issue_yaml) * 3, "Expected Lod.FULL to be substantially larger"

    # 3. Project Doc under Lod.SUMMARY
    raw_doc: dict[str, Any] = {
        "slug": "architecture-spec",
        "title": "Platform Architecture Specification",
        "path": "kanban.architecture.v2",
        "created_at": "2026-11-01T00:00:00Z",
        "updated_at": "2026-11-15T00:00:00Z",
        "etag": "W/doc12345",
        "body_markdown": "# Spec\n" + "Enterprise-grade specification contents. " * 400,
        "access": {"users": ["adamoutler"]},
        "access_manifest": {"large": "manifest " * 100},
    }
    projected_doc = mcp_lod.project_doc(raw_doc, lod_summary)
    doc_yaml = dump_yaml(projected_doc)
    doc_tokens = _estimate_tokens(doc_yaml)

    assert len(doc_yaml) < 4000, f"Summary doc YAML exceeds 4000 chars: {len(doc_yaml)}"
    assert doc_tokens < 1000, f"Summary doc YAML exceeds 1000 tokens: {doc_tokens}"
    assert "body_markdown" not in projected_doc

    # 4. Project Sticky under Lod.SUMMARY
    raw_sticky: dict[str, Any] = {
        "id": "stk-001",
        "project": "KANBA",
        "color": "yellow",
        "content_markdown": "Short sticky memo with quick thoughts.",
        "created_at": "2026-11-15T00:00:00Z",
        "updated_at": "2026-11-15T00:00:00Z",
        "etag": "W/stk123",
        "access": {"groups": ["core"]},
        "access_manifest": {"raw": "details"},
    }
    projected_sticky = mcp_lod.project_sticky(raw_sticky, lod_summary)
    sticky_yaml = dump_yaml(projected_sticky)
    sticky_tokens = _estimate_tokens(sticky_yaml)

    assert len(sticky_yaml) < 4000
    assert sticky_tokens < 1000

    # 5. Project Project under Lod.SUMMARY
    raw_project: dict[str, Any] = {
        "key": "KANBA",
        "name": "thumbs-up-kanban core",
        "description_markdown": "# Project description\n" + "Detailed charter. " * 150,
        "visibility": "private",
        "modules": ["kanban", "database", "mcp", "agent"],
        "cycles_active": 3,
        "access": {"users": ["lead"]},
        "access_manifest": {"full_acl": "..." * 50},
    }
    projected_project = mcp_lod.project_project(raw_project, lod_summary)
    project_yaml = dump_yaml(projected_project)
    project_tokens = _estimate_tokens(project_yaml)

    assert len(project_yaml) < 4000
    assert project_tokens < 1000

    # 6. Generic project_entity dispatcher check
    dispatched = mcp_lod.project_entity("issue", raw_issue, lod_summary)
    assert dispatched["key"] == "KANBA-182"
    assert "description_markdown" not in dispatched


@pytest.mark.asyncio
async def test_security_rls_and_sanitizer_invariants(db_session: AsyncSession) -> None:
    """Assert PostgreSQL FORCE RLS is active and lone-surrogate rejection works."""
    # 1. Catalog check: verify relrowsecurity and relforcerowsecurity on all tenant tables
    catalog_query = text(
        """
        SELECT
            c.relname,
            c.relrowsecurity,
            c.relforcerowsecurity
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public'
          AND c.relkind IN ('r', 'p')
          AND c.relname NOT IN ('alembic_version', 'link_type_matrix')
        ORDER BY c.relname;
        """
    )
    result = await db_session.execute(catalog_query)
    rows = result.mappings().all()

    assert len(rows) >= 25, f"Expected at least 25 tenant tables/partitions, found {len(rows)}"
    unprotected = [
        r["relname"] for r in rows if not r["relrowsecurity"] or not r["relforcerowsecurity"]
    ]
    assert len(unprotected) == 0, (
        f"Tenant tables missing PostgreSQL FORCE ROW LEVEL SECURITY: {unprotected}"
    )

    # 2. DDL static analysis check: verify FORCE ROW LEVEL SECURITY migration presence
    await anyio.to_thread.run_sync(_check_migration_ddl)

    # 3. Unicode sanitizer check: UTF-16 lone surrogate rejection
    # High surrogate boundary \uD800
    with pytest.raises(ContentNormalizeError) as exc_info_high:
        strip_invisible_and_control_chars("Malicious payload with surrogate \ud800")
    assert exc_info_high.value.code == "INVALID_UTF8_SURROGATE"

    # Low surrogate boundary \uDFFF
    with pytest.raises(ContentNormalizeError) as exc_info_low:
        strip_invisible_and_control_chars("Malicious payload with surrogate \udfff")
    assert exc_info_low.value.code == "INVALID_UTF8_SURROGATE"

    # Mid surrogate \uDC00
    with pytest.raises(ContentNormalizeError) as exc_info_mid:
        strip_invisible_and_control_chars("Malicious mid surrogate \udc00 injection")
    assert exc_info_mid.value.code == "INVALID_UTF8_SURROGATE"

    # Full content normalization with lone surrogate must also raise INVALID_UTF8_SURROGATE
    with pytest.raises(ContentNormalizeError) as exc_info_norm:
        normalize_to_markdown("Content with lone surrogate \ud83d boundary attack")
    assert exc_info_norm.value.code == "INVALID_UTF8_SURROGATE"

    # 4. Valid emojis and characters must pass without error
    valid_content = "👍kanban security-first: 🛡️ access pill & ✨ inline sparkle completion"
    cleaned, zw_count, ctrl_count = strip_invisible_and_control_chars(valid_content)
    assert cleaned == valid_content
    assert zw_count == 0
    assert ctrl_count == 0

    # Zero-width spaces must be pruned
    text_with_zw = "clean\u200btext\u200cwith\u200dzero-width"
    sanitized_zw, zw_stripped, _ = strip_invisible_and_control_chars(text_with_zw)
    assert sanitized_zw == "cleantextwithzero-width"
    assert zw_stripped == 3


@pytest.mark.asyncio
async def test_standalone_readiness_and_platform_summary() -> None:
    """Assert platform summary returns verified enterprise capabilities with zero SaaS paywalls."""
    summary = get_platform_summary()
    _assert_summary_pillars(summary)

    # HTTP endpoint integration test
    test_app = FastAPI()
    test_app.include_router(system_router)

    transport = httpx.ASGITransport(app=test_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/system/platform-summary")
        assert resp.status_code == 200
        data = resp.json()
        assert data["platform"] == "👍kanban"
        assert data["github_issue_1_resolved"] is True
        assert data["pillar_1_agent_first"]["summary_token_budget"] == 1000

        # Alias route check
        alias_resp = await client.get("/system/summary")
        assert alias_resp.status_code == 200
        assert alias_resp.json()["platform"] == "👍kanban"
