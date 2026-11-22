# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Security tests ensuring all administrative routes enforce AAL2 (KB-P6-03)."""

from __future__ import annotations

from kanban.app import create_app
from kanban.auth.mfa.policy import assert_admin_routes_protected


def test_assert_admin_routes_protected_compliance() -> None:
    """Verify Section 4.3 invariant: assert_admin_routes_protected returns empty list."""
    app = create_app()
    unprotected = assert_admin_routes_protected(app)
    assert unprotected == [], f"Found unprotected admin routes: {unprotected}"


def test_multi_source_and_export_routes_registered() -> None:
    """Verify newly added multi-source import and export routes are properly registered."""
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

    assert "/api/v1/admin/exports/portable" in admin_paths
    assert "/api/v1/admin/imports/jira" in admin_paths
    assert "/api/v1/admin/imports/github" in admin_paths
    assert "/api/v1/admin/imports/linear" in admin_paths
    assert "/api/v1/admin/audit-ledger/request-shred" in admin_paths
    assert "/api/v1/admin/audit-ledger/execute-shred" in admin_paths
    assert "/api/v1/admin/workload-identities" in admin_paths
    assert "/api/v1/admin/webhooks" in admin_paths
