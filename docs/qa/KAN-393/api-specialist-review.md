# API and Security Specialist Review (KAN-393)

## Overview and Architecture Verification

- **Ticket**: KAN-393 (`[KB-UX-ERROR-DOCS-AAL2] Human-Readable AAL2 Stale Step-Up & Universal '?' / 'More Info' Documentation Links on All Error Messages`)
- **Module**: `kanban/api/problems.py`, `kanban/auth/mfa/policy.py`, `kanban/api/v1/auth_identities.py`, `kanban/api/v1/auth_webauthn.py`, `kanban/api/v1/admin/workspace_settings.py`, `kanban/tests/auth/test_aal2_policy.py`
- **Reviewed By**: API and Security Specialist (`@api-spec`)
- **Commit SHA**: `12e021bc` (branch `feat/kan-393`)
- **Status**: STATUS: APPROVED
- **Verdict**: APPROVED

---

## Verbatim API Specialist Audit Evaluation

### 1. RFC 7807 doc_href and help_summary Extensions
- In `kanban/api/problems.py`, the backend centralizes `PROBLEM_HELP_CATALOG: dict[str, tuple[str, str]]` covering all primary security and platform error codes (`AAL2_STALE`, `AAL2_REQUIRED`, `MFA_ENROLLMENT_REQUIRED`, `AUTHENTICATION_REQUIRED`, `FORBIDDEN`, `INSUFFICIENT_SCOPE`, `INSUFFICIENT_CAPABILITY`, `KEY_SCOPE_VIOLATION`, `CROSS_SCOPE_TAINT_CONFIRMATION_REQUIRED`, `MCP_TAINT_BLOCKED`, `LOCKOUT_PREVENTED`, `HARD_WIP_LIMIT_EXCEEDED`, `GATE_TIMEOUT`, `SCRIPT_RECURSION_BLOCKED`, `INVALID_UTF8_SURROGATE`, `JSON_DEPTH_EXCEEDED`, `JSON_KEYS_EXCEEDED`, `PAYLOAD_TOO_LARGE`, `BLAST_RADIUS_CHANGED`, `MANIFEST_MISMATCH`, `VALIDATION_FAILED`, `VALIDATION_ERROR`, `RATE_LIMITED`).
- `ProblemException` auto-populates `doc_href` and `help_summary` from the catalog if not explicitly passed, ensuring every exception raised in the codebase receives canonical documentation anchors.
- In `make_problem_details()`, `doc_href` and `help_summary` are properly included as RFC 7807 extension attributes in the response dictionary and validated before emission.
- `resolve_problem_help()` provides graceful status-code based fallbacks (`401`, `403`, `404`, `409`, `422`, `429`, `500`, and default to `/docs/admin-diagnostics-and-link-inspector-studio`), eliminating unhandled edge cases.

### 2. Human-Readable AAL2 Stale Copy Across All Endpoints
- The 5 backend `AAL2_STALE` enforcement points have been updated from cryptic internal strings to actionable, user-friendly language:
  - `kanban/auth/mfa/policy.py` (`_RequireAal2.__call__` and `require_admin_aal2`)
  - `kanban/api/v1/auth_identities.py`
  - `kanban/api/v1/auth_webauthn.py`
  - `kanban/api/v1/admin/workspace_settings.py`
- The human copy explicitly explains the 15-minute (900s) Admin 2FA security window and provides direct instructions to re-verify using Passkey or TOTP Authenticator app.

### 3. Security and Anti-Enumeration Integrity
- No secrets, tokens, internal stack traces, or tenant identifiers are leaked in `detail`, `doc_href`, or `help_summary`.
- Constant-time verification and authentication invariants remain completely intact.
- Re-verification flow maintains strict AAL2 assurance without session downgrade vulnerabilities.

### 4. Code Quality, Style, and Test Execution
- **Pytest**: 4/4 tests passed in `kanban/tests/auth/test_aal2_policy.py` (and 35/35 in `docs/qa/KAN-393/pytest.log`).
- **Vitest**: 106/106 tests passed across all error and studio components (`docs/qa/KAN-393/vitest.log`).
- **Linter**: `uv run ruff check` passed with 0 errors across all modified modules.
- **Style Gate**: Zero em-dashes and zero en-dashes verified with `scripts.check_no_dashes`.

**STATUS: APPROVED**
