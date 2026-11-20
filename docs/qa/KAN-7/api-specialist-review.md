# API Specialist Security & Architecture Audit Review: KAN-7

## Audit Metadata
- Ticket ID: KAN-7 ([KB-P3-AUDIT-01])
- Reviewer: api-spec-2 (Clean-Room Backend/API Specialist)
- Date: 2026-11-20
- Target Worktree: `/home/adamoutler/.gemini/antigravity-cli/worktrees/cec3609e-f993-4e05-b8c5-be0070e6116c/swarm-b-kan7-rc4-09e793fa`
- Target Branch: fix/KAN-7-rc4
- Base Commit: c43f946
- Head Commit: d263409
- STATUS: APPROVED

---

## Executive Summary
This clean-room audit evaluates the setup bootstrapping flow, row-level security (RLS) session lifecycle, headless setup token persistence, authentication input validation, fail-closed AppShell auth gating, and Clean-Room Reality-Checker Round 4 unit test coverage hardening ([KB-P3-AUDIT-01]) implemented for ticket KAN-7. The delivery resolves setup claim RLS context binding, container token persistence across unprivileged boundaries, fail-closed realtime session lifecycle management, clean synchronization of client-side logout events, elimination of premature 401 requests during root route navigation, and achievement of 99% unit test coverage on standalone entrypoint deployment scripts.

All implementations adhere strictly to the authoritative specifications in `docs/ARCHITECTURE_AND_PRODUCT_SPEC.md` and `kanban/GEMINI.md`.

---

## Detailed Contract & Security Verification

### 1. Setup Claim RLS Context Binding
- File: `kanban/auth/setup.py` (lines 238-248)
- Invariant: All mutations to `objects` and `projects` tables must execute under an active authenticated RLS context satisfying PostgreSQL `FORCE ROW LEVEL SECURITY`.
- Audit Findings:
  - Previously, `SetupBootstrapService.claim_initial_admin` executed under anonymous session state (principal 0, workspace 0). After `setup_consume_and_create_admin` created the admin principal, workspace, and local card credential, subsequent queries verifying the default project and inserting into `objects` and `projects` failed under `objects_insert_rls`.
  - Fix verified: Immediately following admin creation, the session binds the authenticated context via `await bind_rls_context(session, RLSContext(principal_id=admin_principal_id, workspace_id=admin_workspace_id))`.
  - Security impact: Eliminates setup wizard 500 crashes while preserving strict fail-closed RLS policy enforcement.

### 2. Headless Setup Token Permissions & Multi-Path Fallback
- Files: `deploy/standalone/entrypoint.py` (lines 409, 556-571), `kanban/auth/setup.py` (lines 127-177)
- Invariant: Setup token persistence must succeed on root and unprivileged container runs without leaking secrets or crashing the daemon.
- Audit Findings:
  - Added `"KB_SETUP_TOKEN_FILE"` to `_PASSTHROUGH_ENV_VARS` in `entrypoint.py`, ensuring customized token paths are preserved across unprivileged process isolation boundaries.
  - Ensured `/run/kanban` directory is created and chowned to UID 65532 (mode `0o775`) on container root boot.
  - In `SetupBootstrapService._persist_token`, graceful fallback candidates (`KB_DATA_DIR`, `KB_RUN_DIR`, `/var/lib/kanban/data`, `/var/lib/kanban`, and `tempfile.gettempdir()`) prevent fatal crashes when primary destination permissions are restricted. Files are created with strict `0o600` permissions.

### 3. Recovery Code HTML5 Pattern `/v` Regex Compatibility
- File: `kanban/web/src/features/auth/SecondFactorStep.tsx` (line 304)
- Audit Findings:
  - Pattern updated to `[A-Za-z0-9\-]{8,32}`.
  - Verified compatible with `new RegExp(pattern, 'v')` (Chromium / ECMAScript 2024 UnicodeSets mode), eliminating unhandled `SyntaxError` crashes during recovery code authentication.

### 4. DOM Testability Attribute
- File: `kanban/web/src/features/auth/SecondFactorStep.tsx` (line 161)
- Audit Findings:
  - Root wrapper container now declares `data-testid="second-factor-step"`, enabling deterministic automated selection.

---

## Clean-Room Reality-Checker Remediation Audit (KB-P3-AUDIT-01 Round 4)

- Target Branch: `fix/KAN-7-rc4`
- Remediation Head Commit: `d263409`
- Remediations Verified:
  1. **Standalone Entrypoint Coverage Hardening (`deploy/standalone/entrypoint.py`):**
     - Statement coverage raised to 99% (286/286 statements, 0 missing, 72 branches, 5 partial).
     - Added comprehensive unit tests in `tests/deploy/test_standalone_entrypoint.py` properly mocking `shutil.chown`, `Path.mkdir`, `Path.chmod`, warm boot concurrent execution, and supervisor polling loops.
     - Total combined Python touched-file coverage: 99% (413/413 statements, 0 missing; `kanban/auth/setup.py` 100%, `deploy/standalone/entrypoint.py` 99%).
  2. **Fail-Closed AppShell Auth Gating (`kanban/web/src/app/AppShell.tsx`):**
     - Captured `useSessionGuard()`, computed `isAuthReady = sessionGuard.status === 'authenticated' && !sessionGuard.mfaPending && sessionGuard.authenticated !== false`.
     - When `!isAuthReady`, renders minimal clean placeholder `<div className="kb-app-shell" data-testid="app-shell-auth-loading" />` with 0 inline styles without mounting `<Topbar />`, `<Sidebar />`, or `<Outlet />`.
     - Gated `meQuery` (`/api/v1/auth/me`) and `useRealtimeSubscription` on `isAuthReady`, completely eliminating premature 401 requests on `/` before session redirection completes.
  3. **Visual Proof & Screenshot Synchronization:**
     - Verified all 12 live Playwright PNG screenshots in `docs/qa/KAN-7/screenshots/`:
       * `live-01-setup-claim-light-desktop.png`
       * `live-01b-setup-passkey-enrolled-light.png`
       * `live-02-setup-recovery-codes-light.png`
       * `live-03-workspace-light-desktop.png`
       * `live-04-workspace-dark-desktop.png`
       * `live-05-workspace-light-mobile.png`
       * `live-06-login-light-desktop.png`
       * `live-06b-login-light-mobile.png`
       * `live-07-second-factor-initial-light.png`
       * `live-08-second-factor-totp-tab-dark.png`
       * `live-09-second-factor-recovery-tab-light.png`
       * `live-10-second-factor-mobile-dark.png`
  4. **Quality Gates & Static Verification:**
     - Vitest: 134 unit tests passing across touched features with 99.29% statements and 96.30% branch coverage.
     - Pytest: 46 unit tests passing across `test_standalone_entrypoint.py` and `test_setup.py`.
     - Static checks: `uv run mypy` (1094 files clean), `uv run ruff check .` (clean), `uv run ruff format --check .` (clean), `tsc -b --noEmit` (0 errors), `eslint . --max-warnings 0` (0 errors/warnings), `vite build` (clean in 1.11s).
     - Punctuation: 0 em-dashes and 0 en-dashes across all code, tests, and documentation.
     - Evidence packet: `git-diff.patch` cleanly generated against `31aca8e` across 15 KAN-7 code and test files with zero `docs/qa/` files included.

---

## Gate & Invariant Checklist

1. [x] Zero New Dependencies: No additions to `pyproject.toml` or `package.json`.
2. [x] Admin Route Security: All `/api/v1/admin/*` routes maintain mandatory `Depends(require_admin_aal2)`.
3. [x] Architectural Layering: `uv run lint-imports` verified 2 kept contracts, 0 broken (`agent -> mcp -> kanban -> database`).
4. [x] Test Coverage:
   - Backend: `deploy/standalone/entrypoint.py` 99% and `kanban/auth/setup.py` 100% statement coverage (46 pytest tests passing).
   - Frontend: Touched web features achieved 99.29% statement and 96.30% branch coverage (134 vitest tests passing).
5. [x] Static Analysis: `ruff check`, `ruff format --check`, `mypy` (1094 source files), `tsc -b --noEmit`, and `eslint` pass with 0 errors and 0 warnings.
6. [x] Zero Em/En-Dashes: Clean verification across code, tests, docs, and review markdown (0 em/en-dashes).
7. [x] Evidence Packet Complete: `git-diff.patch`, `changed-files-manifest.txt`, `unit-test-results.txt`, `build-or-typecheck.txt`, and 12 live Playwright screenshots verified in `docs/qa/KAN-7/`.

---

## Verdict & Handoff
STATUS: APPROVED

The API contracts, security invariants, entrypoint test coverage, fail-closed AppShell auth gate, and live screenshots are verified clean. Ready for final coordinator merge into `main`.
