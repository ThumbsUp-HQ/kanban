# API Specialist Review & Verification: KAN-404 (Round-1 Reality-Checker Remediation)

- **Ticket ID:** KAN-404 (`[GATE-0][KB-WEBSUDO-SLIDING-AND-REPLAY] Global Sliding-Window WebSudo (AAL2) + Singleflight In-Place Modal & Transparent Request Replay`)
- **Reviewer Persona:** Senior Backend & API Security Architect (`@api-spec`)
- **Branch:** `fix/KAN-404-rc1` (commit `4a827901`)
- **Status:** APPROVED
- **Date:** 2026-11-25

---

## 1. Scope & Backend Topology Audit

### A. Linear Database Migration & Schema Invariants
- **Migration `p6_18_websudo_sliding_aal2`**:
  - Adds `aal2_last_active_at TIMESTAMPTZ` to `sessions` table with historical backfill from `aal2_verified_at` for active AAL2 rows.
  - Recreates `kb_auth.session_create`, `session_resolve`, `session_rotate`, and `session_get_metadata` to include `aal2_last_active_at` without introducing sliding writes inside `session_resolve`.
  - Implements `SECURITY DEFINER` RPCs:
    - `kb_auth.session_touch_aal2(p_session_id UUID, p_idle_seconds INT, p_abs_seconds INT, p_force BOOLEAN)`: Enforces 900s idle timeout, 14400s (4h) absolute lifetime cap, and 30s database write throttle to prevent write amplification.
    - `kb_auth.session_drop_aal2(p_session_id UUID)`: Safely revokes elevation.
  - Verified with `uv run kanban-ctl db check-migrations --static-only`: 82 migrations valid, single head (`p6_20_oauth_clients_status_check`; 0 new migrations introduced in KAN-404 remediation).
  - ORM parity verified on `UserSession` in `database/models/auth.py`.

### B. Elevation Policy & Strict Dual-Control Guard
- **Strict Dual-Control Guard (`kanban/custom_fields/approvals.py`)**:
  - Remediated `CustomFieldApprovalService.approve` to strictly reject callers where `caller.aal2_verified_at is None` with HTTP 403 `AAL2_REQUIRED`. Callers must have an explicit timestamp recorded within `AAL2_FRESHNESS_SECONDS` (900s).
  - Verified that high-risk irreversible operations (`custom_fields/approvals.py`, `DELETE /api/v1/auth/webauthn/credentials/{id}`, `DELETE /api/v1/auth/mfa/totp`, `POST /api/v1/auth/mfa/recovery/regenerate`) enforce `verification_only=True` (`aal2_verified_at <= 900s`), preventing indefinitely extended sliding sessions from executing destructive credential purges.
- **Sliding Elevation Policy**:
  - Standard admin routes and WebSudo operations validate and slide via `session_touch_aal2`.
  - Non-advancement on session read verified: `session_resolve` does not update `aal2_last_active_at`.
  - 30-second write throttle and 14,400-second (4-hour) absolute ceiling verified by automated tests.
- **API Endpoints**:
  - `POST /api/v1/auth/aal2/touch`: Returns 200 `{ "aal2_active": bool, "aal2_expires_at": str | None }` without throwing 403 when expired, enabling smooth polling and keepalives.
  - `POST /api/v1/auth/aal2/drop`: Revokes AAL2 elevation immediately.
  - Emits `X-KB-AAL2-Expires-At` header on elevated responses.
  - Passes 100% of admin route checks in `test_admin_routes_protected.py`.

---

## 2. Frontend Replay, Security Invariants & Wire Safety

- **Singleflight Coordinator (`client.ts`)**:
  - Enforces cookie-first CSRF resolution (`__Host-kb_csrf` / `kb_csrf`).
  - Traps 403 AAL2 step-up challenges behind a singleflight `pendingAal2StepUp` promise, refreshing CSRF tokens and replaying requests with a strict max-1 replay limit.
  - Emits `kb:aal2-expires-at` window event whenever `X-KB-AAL2-Expires-At` response header is received.
  - Added `isAal2StepUpCancelled(err)` helper. Cancelling the elevation dialog cleanly rejects with `Aal2StepUpCancelledError`.
- **Drawer Secret Preservation & Modal Consolidation**:
  - Consolidated duplicate local `aal2Challenge` state/modals across all 8 Studio/Settings pages into the global singleflight `WebSudoModalHost.tsx`.
  - In `AuthCardEditorDrawer.tsx`, secrets (`secretInput`) are preserved upon cancellation/failure and never wiped in `finally`.
  - Focus trap and Escape key listener implemented in `WebSudoModalHost.tsx`.
- **Authentic Dirty Keepalive**:
  - `useAal2DirtyKeepalive` is wired to real form dirty state (`hasUnsavedChanges` / `isDirty`) in `AuthCardEditorDrawer`, `AiProviderEditorDrawer`, and `AgentDefinitionEditorDrawer`. Untouched open drawers do not fire `/api/v1/auth/aal2/touch`.

---

## 3. Quality Gates & Test Results

- **Unit Tests**:
  - 38 Pytest backend tests passing in 21.68s with >= 95% coverage on all target modules (database.models.auth: 100%, kanban.api.v1.auth_session: 96%, kanban.auth.mfa.policy: 97%, kanban.custom_fields.approvals: 96%; Total: 97%).
  - 606 Vitest frontend tests passing across 19 test suites with branch coverage >= 95% (All files: 99.36% stmts / 96.29% branch / 99.60% funcs / 99.41% lines; WebSudoModalHost: 100% stmts / 100% branch; AdminStudioSubnav: 100% stmts / 100% branch; client.ts: 99.45% lines / 95.08% branch).
- **Static Analysis & Build**:
  - 0 ruff errors (`uv run ruff check .`).
  - 0 mypy errors in 1369 source files (`uv run mypy`).
  - 0 tsc errors, 0 linter warnings (`pnpm typecheck`, `pnpm lint`).
  - Clean production build (1.26s, 762 modules transformed).
  - 0 forbidden Unicode dashes (`python3 scripts/check_no_dashes.py --all`).
  - Manifest verified 100% OK with `sha256sum -c`.

Verdict: **APPROVED**.
