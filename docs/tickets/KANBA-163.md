---
id: KANBA-163
title: "[Phase 0+2 / Priority #0 Remediation] Restore green root pytest, RLS privilege-revoked table assertion, admin MCP-keys AAL2 dependency & Dash CI testdb lifecycle"
epic: KB-E0
depends_on: ["KANBA-18", "KANBA-28", "KANBA-73", "KANBA-81", "KANBA-95", "KANBA-162"]
spec_sections: ["4.2", "11.1", "15.1", "15.4"]
new_dependencies: []
---

### User Story
As a **Systems Security & Release Architect**, I need root `uv run pytest` collection, `database/tests/test_p1_14_rls_policies.py`, `kanban/tests/auth/test_aal2_policy.py`, OpenAPI operation-id uniqueness, and `.forgejo/workflows/ci.yml` / `.github/workflows/ci.yml` PostgreSQL test-harness orchestration remediated immediately so that `main` and remote Dash CI (`AI/thumbs-up-kanban`) pass 100% of unit, security, and `>=95%` coverage gates before merging Waves W16-W18.

**Requirement Traceability:** `[S4.2, S11.1, S15.1, S15.4]` | **Dependencies:** `KANBA-18`, `KANBA-73`, `KANBA-81`, `KANBA-95`, `KANBA-162`

### Scoped Technical Actions
1. **Target Files:**
   - `kanban/tests/conftest.py` (new or updated), `kanban/tests/agents/conftest.py`, `kanban/tests/attachments/conftest.py`
   - `database/tests/test_p1_14_rls_policies.py`
   - `kanban/api/v1/admin/mcp_keys.py`, `kanban/auth/mfa/policy.py`, and `kanban/tests/api/test_admin_mcp_keys_api.py`
   - `kanban/api/v1/views.py`
   - `.forgejo/workflows/ci.yml` and `.github/workflows/ci.yml`
2. **Fix Pytest 9.2+ Root Collection Without Layer Inversion:**
   - Remove `pytest_plugins = ["kanban.tests.api.conftest"]` from non-top-level `kanban/tests/agents/conftest.py` and `kanban/tests/attachments/conftest.py` (forbidden by Pytest 9.2+).
   - Re-export shared API test fixtures explicitly inside `kanban/tests/conftest.py` (do NOT load `kanban.*` in root `/conftest.py`, preserving strict `import-linter` isolation for `database/tests/` and `mcp/tests/`).
3. **Harden `test_p1_14_rls_policies.py` for `SECURITY DEFINER`-Isolated Auth Tables:**
   - Add `'oidc_auth_requests'` (alongside any public-schema `kb_auth_owner` tables such as `totp_factors`, `recovery_codes`, `webauthn_credentials`, `webauthn_challenges` where privileges are revoked from `kanban_app` and `app_rls_reader`) to the `NOT IN` exclusion list for `SELECT count(*)` in `test_01_zero_context_fail_closed`.
   - Add an explicit positive security assertion verifying `has_table_privilege('kanban_app', tbl, priv) = false` and `has_table_privilege('app_rls_reader', tbl, priv) = false` across `SELECT, INSERT, UPDATE, DELETE` for every `kb_auth_owner` table.
4. **Enforce `Depends(require_admin_aal2)` on `/api/v1/admin/mcp-keys` & Deduplicate OpenAPI `operation_id`:**
   - Remove the shadowed local `require_admin_aal2` helper in `kanban/api/v1/admin/mcp_keys.py` and wire canonical `kanban.auth.mfa.policy.require_admin_aal2` (`Caller = Annotated[PrincipalContext, Depends(require_admin_aal2)]` / `dependencies=[Depends(require_admin_aal2)]`), ensuring `WORKSPACE_ADMIN` is recognized alongside `SERVER_ADMIN` and `PROJECT_ADMIN` in `kanban/auth/mfa/policy.py` and seeding a confirmed MFA factor for `mcp_admin` in `kanban/tests/api/test_admin_mcp_keys_api.py` so `test_aal2_policy.py::test_case_10_assert_admin_routes_protected` passes with `[]`.
   - Set `include_in_schema=False` (or distinct `operation_id="query_project_issues_adhoc_slash_alias"`) on the secondary `/projects/{project_ref}/issues/query` slash-alias decorator in `kanban/api/v1/views.py` so zero FastAPI duplicate `operation_id` warnings are emitted.
5. **Wire `make testdb-up` / `make testdb-down` & Coverage Gates in CI (`inferrence1`):**
   - Update `.forgejo/workflows/ci.yml` and `.github/workflows/ci.yml` to launch `make testdb-up` prior to `uv run pytest`, run `pnpm --dir kanban/web test:unit --coverage` and `make license`, always tear down via `if: always()` `make testdb-down`, and verify green remote Dash status (`AI/thumbs-up-kanban`).

### Mandatory Feature Unit Tests
- **Test File(s):**
  - `database/tests/test_p1_14_rls_policies.py`
  - `kanban/tests/auth/test_aal2_policy.py`
  - `kanban/tests/api/test_admin_mcp_keys_api.py`
  - `kanban/tests/test_export_openapi.py`
- **Required Test Cases:**
  1. **Root Collection & Suite Pass:** `uv run pytest -q` invoked from repository root `/home/adamoutler/kanban` collects all `database`, `kanban`, `mcp`, `agent`, `tests/deploy`, and `scripts/tests` suites with `0` collection errors and `0` failures.
  2. **Privilege-Revoked Auth Table Proof:** `test_p1_14_rls_policies.py` verifies both zero-context `0`-row return on tenant RLS tables and `has_table_privilege = false` for `kanban_app` and `app_rls_reader` across `kb_auth_owner` tables (`oidc_auth_requests`, `totp_factors`, `recovery_codes`, `webauthn_credentials`, `webauthn_challenges`).
  3. **Admin Route AAL2 Gate Proof:** `test_aal2_policy.py::test_case_10_assert_admin_routes_protected` returns `[]` across the full `build_v1_router()` application, and `/api/v1/admin/mcp-keys` rejects AAL1 or MFA-unenrolled admin principals with `403` (`AAL2_REQUIRED` / `MFA_ENROLLMENT_REQUIRED`).
  4. **Zero Duplicate OpenAPI Operation IDs:** OpenAPI export emits `0` `UserWarning: Duplicate Operation ID` warnings.

### Scoped Definition of Done (Literal Pass Criteria for Reality-Checker)
- [ ] **File Existence & Implementation:** `kanban/tests/agents/conftest.py`, `kanban/tests/attachments/conftest.py`, `kanban/tests/conftest.py`, `database/tests/test_p1_14_rls_policies.py`, `kanban/api/v1/admin/mcp_keys.py`, `kanban/auth/mfa/policy.py`, `kanban/tests/api/test_admin_mcp_keys_api.py`, `kanban/api/v1/views.py`, `.forgejo/workflows/ci.yml`, and `.github/workflows/ci.yml` implement all 5 Scoped Technical Actions.
- [ ] **Unit Tests Implemented & Passing:** Root `uv run pytest -q` and `pnpm --dir kanban/web test:unit --coverage` both exit with code `0` and `0` failures.
- [ ] **Build / Type / Lint Clean:** `make check && make license` exits with code `0` and `0` warnings/errors, and remote Dash CI for `AI/thumbs-up-kanban` reports `success`.
- [ ] **Forensic Proof Packet Complete:** All required raw proof files are written to `docs/qa/KANBA-163/`.

### Forensic Verification Proof (Passive Audit Bundle for Reality-Checker)
The implementing sub-agent MUST populate `docs/qa/KANBA-163/` with the following raw, unedited artifacts (no summaries; **visual browser screenshots are NOT applicable (`N/A - Non-UI Backend/CI Remediation Ticket`)**):
1. `docs/qa/KANBA-163/git-diff.patch` - Complete unified `git diff` showing all code, test, and CI workflow changes for `KANBA-163`.
2. `docs/qa/KANBA-163/unit-test-results.txt` - Full, unedited console output (`stdout`/`stderr` and exit code) of root `uv run pytest` and `pnpm --dir kanban/web test:unit --coverage`.
3. `docs/qa/KANBA-163/build-check.txt` - Full, unedited console output of `make check && make license` plus verified Dash CI status output.
4. `docs/qa/KANBA-163/api-specialist-review.md` - Raw audit and sign-off from `.agents/agents/backend-architect.md` or `.agents/agents/api-tester.md` covering `/api/v1/admin/mcp-keys` AAL2 enforcement and `/issues:query` OpenAPI schema.
5. `docs/qa/KANBA-163/ui-specialist-review.md` - Raw audit and sign-off from `.agents/agents/ui-designer.md` or `.agents/agents/ux-architect.md` verifying OpenAPI client compatibility and AAL2 error contract alignment.
6. `docs/qa/KANBA-163/message-to-reality-checker.md` - Explains why browser screenshots are `N/A` and maps each DoD item to exact line evidence.
