# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Unit tests verifying all 12 /mcp/admin tools are registered in SCOPE_REQUIREMENTS."""

from __future__ import annotations

from mcp.auth import SCOPE_REQUIREMENTS
from mcp.surfaces.admin import ADMIN_TOOL_NAMES


def test_all_12_admin_tools_in_scope_requirements() -> None:
    """Verify all 12 official /mcp/admin tools exist in SCOPE_REQUIREMENTS."""
    assert len(ADMIN_TOOL_NAMES) == 12
    for tool_name in ADMIN_TOOL_NAMES:
        assert (
            tool_name in SCOPE_REQUIREMENTS
        ), f"Tool '{tool_name}' missing from SCOPE_REQUIREMENTS"
        scopes = SCOPE_REQUIREMENTS[tool_name]
        assert isinstance(scopes, frozenset)
        assert any(s.startswith("admin:") for s in scopes)


def test_scope_requirements_expected_scopes() -> None:
    """Verify expected base scope assignments."""
    assert "admin:read" in SCOPE_REQUIREMENTS["configure_workspace"]
    assert "admin:read" in SCOPE_REQUIREMENTS["manage_auth_cards"]
    assert "admin:read" in SCOPE_REQUIREMENTS["architect_project"]
    assert "admin:read" in SCOPE_REQUIREMENTS["manage_cycles_and_modules"]
    assert "admin:read" in SCOPE_REQUIREMENTS["manage_custom_fields_and_scripts"]
    assert "admin:read" in SCOPE_REQUIREMENTS["manage_workflow_interceptors"]
    assert "admin:read" in SCOPE_REQUIREMENTS["manage_principals_and_groups"]
    assert "admin:read" in SCOPE_REQUIREMENTS["manage_access_policies"]
    assert "admin:read" in SCOPE_REQUIREMENTS["manage_ai_and_agent_runners"]
    assert "admin:write" in SCOPE_REQUIREMENTS["override_ticket_provenance"]
    assert "admin:read" in SCOPE_REQUIREMENTS["audit_and_purge_object_links"]
    assert "admin:destructive" in SCOPE_REQUIREMENTS["destructive_lifecycle"]
