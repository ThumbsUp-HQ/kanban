# API Specialist Review - KAN-535 (commit ab64d549)

Reviewer: clean-room, read-only (rv-kan535).

## Findings
- Migration p6_25_drop_mcp_read_taint: down_revision p6_24_default_workflow_hooks, single linear head. Up is DROP TABLE IF EXISTS ... CASCADE. Down recreates the table, indexes, FORCE RLS, 4 policies and grants. Model removed from database/models/__init__.py, so ORM parity holds. Round-trip migration test added (14 db tests passed per evidence). I did not re-execute it.
- kanban/api/deps.py: get_rls_session passes credential_boundary into RLSContext. database/rls/context.py already has the field and normalizer. getattr(..., None) is tolerant, but the principal dataclass already declares the field, so direct attribute access would be stricter.
- mcp/scoping.py: mutating_tools extended with update_workpad, add_comment, link_objects. Correct.
- Taint eradication: grep for TaintGuard/TaintRecorder/CROSS_SCOPE_TAINT in source finds none. One stale hit remains: mcp/tests/agent/test_add_comment.py:333 (docstring says 409 CROSS_SCOPE_TAINT_CONFIRMATION_REQUIRED). Line 336 there and the docstring in kanban/tests/security/test_untrusted_content_taint.py:9 still describe MCP_TAINT_BLOCKED / taint 409 behaviour. All are comments, but they are misleading. Stale __pycache__ files are untracked noise.
- MCP_TAINT_BLOCKED is kept in kanban/services/activity.py (enum, category map, allowlist) as a deprecated value. Acceptable. It has no deprecation comment, so one should be added.
- test_scoped_key_no_read_taint.py: (a) a workspace key reads restricted TEST and writes KAN without taint; (b) a project key cannot read or mutate a sibling project, checked at MCP and RLS. Both cases are present and reported passing (2 passed).

## Non-blocking requests
1. Fix the stale docstrings listed above.
2. Add a "deprecated" comment on MCP_TAINT_BLOCKED.

Verdict: APPROVED
