# API Specialist Review & Verification: KAN-404

- **Ticket ID:** KAN-404 (`[GATE-0][KB-WEBSUDO-SLIDING-AND-REPLAY] Global Sliding-Window WebSudo (AAL2) + Singleflight In-Place Modal & Transparent Request Replay`)
- **Reviewer Persona:** Senior Backend & API Security Architect (`@api-spec`)
- **Branch:** `feat/KAN-404-websudo-sliding-replay` (commit `f24f31e8`)
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
  - Verified with `uv run kanban-ctl db check-migrations --static-only`: 80 migrations valid, single head (`p6_18_websudo_sliding_aal2`).
  - ORM parity verified on `UserSession` in `database/models/auth.py`.

### B. Elevation Policy & Dual Security Invariant
- **Sliding Elevation vs Strict Verification**:
  - Standard admin routes and WebSudo operations validate and slide via `session_touch_aal2`.
  - High-risk irreversible operations (`custom_fields/approvals.py`, `DELETE /api/v1/auth/webauthn/credentials/{id}`, `DELETE /api/v1/auth/mfa/totp`, `POST /api/v1/auth/mfa/recovery/regenerate`) enforce `verification_only=True` (`aal2_verified_at <= 900s`), preventing indefinitely extended sliding sessions from executing destructive credential purges.
- **API Endpoints**:
  - `POST /api/v1/auth/aal2/touch`: Returns 200 `{ "aal2_active": bool, "aal2_expires_at": str | None }` without throwing 403 when expired, enabling smooth polling and keepalives.
  - `POST /api/v1/auth/aal2/drop`: Revokes AAL2 elevation immediately.
  - Emits `X-KB-AAL2-Expires-At` header on elevated responses.
  - Passes 100% of admin route checks in `test_admin_routes_protected.py`.

---

## 2. Frontend Replay & Wire Safety

- **Singleflight Coordinator (`client.ts`)**:
  - Enforces cookie-first CSRF resolution (`__Host-kb_csrf` / `kb_csrf`).
  - Traps 403 AAL2 step-up challenges behind a singleflight `pendingAal2StepUp` promise, refreshing CSRF tokens and replaying requests with a strict max-1 replay limit.
  - Cancelling the elevation dialog cleanly rejects with `Aal2StepUpCancelledError`.
- **Drawer Keepalive**:
  - `useAal2DirtyKeepalive` actively prevents session expiration while users edit unsaved drawers in `AuthCardEditorDrawer`, `AiProviderEditorDrawer`, and `AgentDefinitionEditorDrawer`.

---

## 3. Quality Gates & Test Results

- **Unit Tests**:
  - 17 Pytest tests passing (`test_websudo_sliding_aal2.py`, migration tests).
  - 16 Vitest tests passing (`websudoReplay.test.tsx`, `AdminStudioSubnav.test.tsx`).
- **Static Analysis & Build**:
  - 0 ruff errors, 0 mypy errors, 0 tsc errors, 0 linter warnings.
  - Clean production build (1.18s).
  - 0 forbidden Unicode dashes (`check_no_dashes.py --all`).
  - Manifest verified 100% OK with `sha256sum -c`.

Verdict: **APPROVED**.
