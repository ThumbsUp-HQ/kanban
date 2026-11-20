# API Specialist Security & Architecture Audit Review: KAN-7

## Audit Metadata
- Ticket ID: KAN-7 ([KB-P3-AUDIT-01])
- Reviewer: api-spec-2 (Clean-Room Backend/API Specialist)
- Date: 2026-11-19
- Target Worktree: `/home/adamoutler/.gemini/antigravity-cli/worktrees/cec3609e-f993-4e05-b8c5-be0070e6116c/swarm-b-kan7-7e7025e9`
- Target Branch: feat/KAN-7
- Base Commit: 3dd6b9d
- Head Commit: f6f57fe
- STATUS: APPROVED

---

## Executive Summary
This clean-room audit evaluates the setup bootstrapping flow, row-level security (RLS) session lifecycle, headless setup token persistence, and authentication input validation implemented for ticket KAN-7. The delivery resolves four core runtime vulnerabilities and setup wizard failures without introducing external dependencies or compromising architectural boundaries.

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

## Gate & Invariant Checklist

1. [x] Zero New Dependencies: No additions to `pyproject.toml` or `package.json`.
2. [x] Admin Route Security: All `/api/v1/admin/*` routes maintain mandatory `Depends(require_admin_aal2)`.
3. [x] Architectural Layering: `uv run lint-imports` verified 2 kept contracts, 0 broken (`agent -> mcp -> kanban -> database`).
4. [x] Test Coverage:
   - Backend: `kanban/auth/setup.py` achieved 100% statement and 100% branch coverage (38 pytest tests passing).
   - Frontend: `SecondFactorStep.tsx` achieved 98.96% statement, 96.25% branch, 100% function, and 100% line coverage (19 vitest tests passing).
5. [x] Static Analysis: `ruff check`, `ruff format --check`, `mypy`, `tsc -b --noEmit`, and `eslint` pass with 0 errors and 0 warnings.
6. [x] Zero Em/En-Dashes: Clean verification across code, tests, docs, and review markdown (0 em/en-dashes).
7. [x] Evidence Packet Complete: `git-diff.patch`, `changed-files-manifest.txt`, `unit-test-results.txt`, `build-or-typecheck.txt`, `message-to-reality-checker.md`, and 8 Playwright screenshot PNGs verified in `docs/qa/KAN-7/`.

---

## 5. Clean-Room Reality-Checker Remediation Audit (KB-P3-AUDIT-01)

- Target Branch: `fix/KAN-7-liveqa`
- Remediation Head Commit: `3637ca1`
- Remediation Scope:
  1. Realtime WebSocket and SSE Session Gating:
     - In `kanban/web/src/api/realtime.ts` and `kanban/web/src/realtime/context.tsx`: Gated connection establishment strictly on `session?.authenticated === true && session?.mfa_pending !== true`.
     - Added synchronous suppression on unauthenticated routes (`/login`, `/setup`, `/activate`), eliminating 401/403 console errors during authentication and second-factor steps.
     - Added session observer and logout event handlers to terminate active connections immediately upon session expiration. Server close codes 4401, 4403, and 1008 terminate cleanly without reconnect loops.
  2. Mobile Viewport Layout and Tab Wrapping:
     - In `kanban/web/src/features/auth/auth.css`: Configured `.auth-tablist` with `flex-wrap: wrap; width: 100%; box-sizing: border-box;`, responsive token variables (`--space-1`, `--space-2`, `--text-xs`), and preserved tap target bounds (`--tap-min: 44px`).
     - Verified that all three tabs (`Authenticator code`, `Passkey`, `Recovery code`) wrap cleanly inside `.auth-panel` at 390px mobile viewport without horizontal overflow.
  3. Test and Coverage Verification:
     - 86 Vitest unit tests passing across touched features with > 95% branch coverage and > 99% statement coverage on all touched files (`api/realtime.ts`, `SecondFactorStep.tsx`, `realtime/context.tsx`).
     - 38 backend Pytest tests passing cleanly.
     - `cssTokensAudit.test.ts` (4/4 passed); zero inline styles; `tsc` (0 errors), `eslint` (0 errors), and `check_no_dashes` (0 em/en-dashes).

---

## Verdict & Handoff
STATUS: APPROVED

The API contracts, security invariants, and test evidence are verified clean. Handoff to `@ui-spec-2` for visual, UX, and accessibility verification of `docs/qa/KAN-7/screenshots/`.

