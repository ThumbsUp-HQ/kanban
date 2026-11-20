# API Specialist Security & Architecture Audit Review: KAN-7

## Audit Metadata
- Ticket ID: KAN-7 ([KB-P3-AUDIT-01])
- Reviewer: api-spec-2 (Clean-Room Backend/API Specialist)
- Date: 2026-11-19
- Target Worktree: `/home/adamoutler/.gemini/antigravity-cli/worktrees/cec3609e-f993-4e05-b8c5-be0070e6116c/swarm-b-kan7-rcfix-ca5cf51e`
- Target Branch: fix/KAN-7-rc2
- Base Commit: 036216b
- Head Commit: 402a8b9
- STATUS: APPROVED

---

## Executive Summary
This clean-room audit evaluates the setup bootstrapping flow, row-level security (RLS) session lifecycle, headless setup token persistence, and authentication input validation implemented for ticket KAN-7, alongside the Clean-Room Reality-Checker Round 2 surgical remediations ([KB-P3-AUDIT-01]). The delivery resolves setup claim RLS context binding, container token persistence across unprivileged boundaries, fail-closed realtime session lifecycle management, and clean synchronization of client-side logout events.

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

## Clean-Room Reality-Checker Remediation Audit (KB-P3-AUDIT-01 Round 2)

- Target Branch: `fix/KAN-7-rc2`
- Remediation Head Commit: `402a8b9`
- Remediations Verified:
  1. **Fail-Closed Realtime Initialization (`kanban/web/src/realtime/context.tsx`):**
     - `effectiveSession` now defaults fail-closed to `{ authenticated: false, mfa_pending: false }` whenever `propSession === undefined` and `sessionQuery.data` has not resolved to an authenticated, MFA-complete session.
     - Spurious 403 WebSocket/SSE console errors on direct navigation to `/` are eliminated.
     - Unit tests in `kanban/web/src/realtime/index.test.tsx` verify that query rejection or network errors result in `isSessionAllowed() === false`, `0` WebSocket connections, and `0` EventSource connections.
  2. **Synchronized Client-Side Logout & Session Invalidation (`Topbar.tsx`, `useSessionGuard.ts`, `api/realtime.ts`):**
     - In `kanban/web/src/api/realtime.ts` (`probeWebSocket()`), added `if (!this.isSessionAllowed()) return;` at entry, preventing background probes when the session is unauthenticated.
     - In `kanban/web/src/app/Topbar.tsx` (`handleLogout`) and `kanban/web/src/features/auth/useSessionGuard.ts` (redirecting unauthenticated or `mfa_pending` sessions), added synchronous dispatch of `window.dispatchEvent(new CustomEvent('kb:auth-logout'))` and invalidation of `['auth', 'session']`.
     - In `kanban/web/src/realtime/context.tsx`, `handleAuthChange` unconditionally calls `client.close()` if the client is not already closed.
  3. **Quality Gates & Test Coverage:**
     - Vitest: 122 tests passed across touched suites with 99.18% statements and 95.42% branch coverage.
     - Pytest: 38 tests passed with 100% coverage on `kanban/auth/setup.py`.
     - Static checks: `tsc -b --noEmit` (0 errors), `eslint . --max-warnings 0` (0 warnings/errors), `vite build` (clean in 1.40s).
     - Punctuation: 0 em-dashes and 0 en-dashes across all files.
     - Evidence packet: `git-diff.patch` cleanly generated against `31aca8e` with zero `docs/qa/` files included.

---

## Gate & Invariant Checklist

1. [x] Zero New Dependencies: No additions to `pyproject.toml` or `package.json`.
2. [x] Admin Route Security: All `/api/v1/admin/*` routes maintain mandatory `Depends(require_admin_aal2)`.
3. [x] Architectural Layering: `uv run lint-imports` verified 2 kept contracts, 0 broken (`agent -> mcp -> kanban -> database`).
4. [x] Test Coverage:
   - Backend: `kanban/auth/setup.py` achieved 100% statement and 100% branch coverage (38 pytest tests passing).
   - Frontend: Touched web features achieved 99.18% statement and 95.42% branch coverage (122 vitest tests passing).
5. [x] Static Analysis: `ruff check`, `ruff format --check`, `mypy`, `tsc -b --noEmit`, and `eslint` pass with 0 errors and 0 warnings.
6. [x] Zero Em/En-Dashes: Clean verification across code, tests, docs, and review markdown (0 em/en-dashes).
7. [x] Evidence Packet Complete: `git-diff.patch`, `changed-files-manifest.txt`, `unit-test-results.txt`, `build-or-typecheck.txt`, and Playwright screenshots verified in `docs/qa/KAN-7/`.

---

## Verdict & Handoff
STATUS: APPROVED

The API contracts, security invariants, fail-closed realtime session gating, and test evidence are verified clean. Ready for final coordinator merge into `main`.
