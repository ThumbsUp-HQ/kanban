# Message to Reality-Checker: KANBA-144 (KB-P5-05b)

## Overview & Executive Summary

- **Ticket**: `KANBA-144` (`KB-P5-05b`: `[Phase 5 / API + MCP] AI provider & budget admin REST API + /mcp/admin manage_ai_and_agent_runners (providers + budgets actions)`)
- **Worktree**: `/tmp/kb-wt-KANBA-144`
- **Branch**: `feat/KANBA-144`
- **Target Modules**:
  - `kanban/api/v1/admin/ai_schemas.py`
  - `kanban/api/v1/admin/ai_providers.py`
  - `kanban/api/v1/__init__.py`
  - `mcp/admin/tools/manage_ai_and_agent_runners.py`
  - `mcp/surfaces/admin/manage_ai_and_agent_runners.py`
  - `mcp/surfaces/admin/__init__.py`
  - `mcp/auth.py`
  - `mcp/errors.py`
  - `mcp/yaml_out.py`
  - `kanban/services/activity.py`
  - `kanban/tests/api/admin/test_ai_providers_api.py`
  - `mcp/tests/admin/test_manage_ai_and_agent_runners.py`

This implementation delivers the administrative REST API and MCP Tool 9 (`manage_ai_and_agent_runners`) for AI provider lifecycle management, write-only envelope-encrypted key custody, periodic token budget enforcement, and immutable activity ledger auditing.

---

## Mandates, Invariants & Security Architecture

### 1. Administrative Gate & AAL2 MFA Policy (Spec S4.3, S10.2)
- Mounted at `/api/v1/admin/ai/*` with `Depends(require_admin_aal2)`.
- Verified via `assert_admin_routes_protected`: callers lacking administrative role bindings (`SERVER_ADMIN`, `WORKSPACE_ADMIN`, `PROJECT_ADMIN`) receive HTTP 403 `FORBIDDEN`.
- Admins with unverified factors receive HTTP 403 `AAL2_REQUIRED` or `MFA_ENROLLMENT_REQUIRED`.

### 2. Timing-Equalized 404 & Anti-Enumeration Defense (Spec S14.3)
- All route handlers execute within `timing_floor(floor_ms=25.0)`.
- Requests for non-existent provider configs or configs unreadable under PostgreSQL RLS yield an identical HTTP 404 `NOT_FOUND` response with uniform byte structure and timing.

### 3. Write-Only Key Custody & Defense-in-Depth Scrubbing (Spec S10.1, S10.2, S11.4)
- Plaintext API keys (`api_key: SecretStr`, max 512 chars) are accepted exclusively during creation or update and are never echoed.
- Database storage is envelope-encrypted (`AES-256-GCM` with DEK wrapped by KMS master KEK). Columns `wrapped_api_key`, `api_key_nonce`, and `wrapped_dek` are revoked from `kanban_app` and `app_rls_reader` and mapped with `deferred=True`.
- Responses project `api_key_set: bool` derived safely from non-secret `dek_kid` column metadata without lazy-loading raw secrets.
- `mcp/yaml_out.py` actively strips any key named `"api_key"`, `"wrapped_api_key"`, or `"api_key_nonce"`.

### 4. Air-Gap Mode Outbound Egress Defense (Spec S10.1)
- Evaluates `air_gap_mode` from workspace settings or `KANBAN_AIR_GAP_MODE` environment variable.
- Outbound cloud provider registration (`openai`, `gemini`) is blocked with HTTP 409 `AIR_GAP_EGRESS_DENIED`. Local runners (`ollama`, `fixture`) remain functional.

### 5. SSRF Defense & Base URL Validation (Spec S10.2)
- Validates URLs against loopback allowlists, forbidding userinfo and query parameters.
- Rejects cloud metadata addresses (`169.254.169.254`) and link-local ranges (`169.254.0.0/16`) with HTTP 422 `INVALID_BASE_URL`.

### 6. MCP Tool 9: manage_ai_and_agent_runners (Spec S11.4)
- Implements 5 operational actions (`list_providers`, `upsert_provider`, `disable_provider`, `set_budget`, `get_budget_usage`) with multi-tier LOD formatting (`summary`, `standard`, `full`).
- Rejects non-admin agent keys (`kb_agt_*`) with HTTP 403 `SURFACE_KEY_MISMATCH`.
- Rejects unprivileged scopes with `INSUFFICIENT_SCOPE`.
- Deferred actions (`mint_runner_enrollment_token`, `upsert_agent_definition`, `list_agent_definitions`) yield structured `ACTION_NOT_AVAILABLE` faults.

### 7. Immutable Activity Audit Ledger (Spec S12.2)
- Logs `AI_PROVIDER_CONFIG_CREATED`, `AI_PROVIDER_CONFIG_UPDATED`, `AI_PROVIDER_CONFIG_DISABLED`, and `AI_BUDGET_SET` into partitioned, SHA-256 hash-chained `activity_records`.
- Key material is strictly excluded from activity payloads.

---

## Verification Proof Matrix

| Verification Dimension | Requirement / Threshold | Verified Result | Status |
| :--- | :--- | :--- | :--- |
| **Unit Test Suite** | 100% pass across REST API & MCP suites | 15 passed in 10.09s (`unit-test-results.txt`) | PASS |
| **Test Coverage** | >= 95.0% line + branch coverage across touched modules | **98.86%** combined (`unit-test-results.txt`) | PASS |
| **Static Code Quality** | Ruff linter + formatter check | 0 errors, 1197 files formatted (`build-check.txt`) | PASS |
| **Strict Type Checking** | Mypy strict mode across repository | 0 errors across 693 source files (`build-check.txt`) | PASS |
| **Import Architecture** | `lint-imports` contract enforcement | 2 contracts kept, 0 broken (`build-check.txt`) | PASS |
| **License Compliance** | Zero non-permissive runtime dependencies | 0 violations (`build-check.txt`) | PASS |
| **Typography Standard** | Strict ASCII hyphens `-` (zero em/en dashes) | Clean across all code, tests, docs, and patch | PASS |
| **Contract Samples** | `contract-sample.json` & `mcp-sample.yaml` | Captured without raw key material | PASS |
| **API Specialist Gate** | `@arch-reviewer` sign-off | APPROVED in `docs/qa/KANBA-144/api-specialist-review.md` | PASS |
| **UI Specialist Gate** | `@ui-specialist` sign-off | APPROVED in `docs/qa/KANBA-144/ui-specialist-review.md` | PASS |
| **Deterministic QA Gate** | `validate-qa-packet` | 7/7 deterministic checks passed (Grade: A, Readiness: READY) | PASS |
