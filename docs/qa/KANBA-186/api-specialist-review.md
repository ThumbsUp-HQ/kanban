# API Specialist Forensic QA Review: KANBA-186

## Metadata
- **Ticket ID:** KANBA-186
- **Title:** [KB-AUTH-PERSIST] Fix OIDC Session Rollback, Add Keep Me Signed In Persistence, and Remediate Accessibility
- **Reviewer:** api-specialist (Backend Architect & API Tester Persona)
- **Target Commit:** `2b3c84d` (merged into `main`)
- **Review Date:** 2026-11-17
- **Verdict:** APPROVED

---

## 1. Architectural & Engineering Assessment

### 1.1 Database Migration & Schema Consistency Standard (`database/GEMINI.md`)
- **Forward Migration Mapping:** In strict adherence to the Zero-Guesswork standard established in KANBA-189, the migration `p4_19_persistent_sessions` chains forward linearly from `p4_18_oauth_mcp_scoping`.
- **Single-Head Chain Verification:**
  - `uv run kanban-ctl db check-migrations --static-only` confirms exactly 1 head: `p4_19_persistent_sessions`.
  - Migration script `versions/p4_19_persistent_sessions.py` executes SQL pairing `sql/p4_19_persistent_sessions.up.sql` and `sql/p4_19_persistent_sessions.down.sql`.
  - `sessions` table updated with `remember_me: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)`.
  - `database/models/auth.py` updated with 100% column name, nullability, and primary key parity, verified by `database/tests/test_p1_17_models.py:test_orm_schema_parity`.

### 1.2 OIDC Session Rollback Remediation (`kanban/auth/oidc/flow.py`)
- **Root Cause & Fix:** In `OidcFlow.callback`, previously when a session was created via `create_after_login`, the active database transaction was not explicitly committed before returning the redirect response. Upon exiting the ASGI handler, the session was disposed and uncommitted rows rolled back.
- **Remediation:** Explicit `await session.commit()` is executed immediately after `session_service.create_after_login`, ensuring session records are durably committed prior to issuing the redirect response.

### 1.3 Cookie Security & Lifetimes (`kanban/auth/sessions/cookies.py`)
- **Unified Cookie Issuance Helper:** `attach_session_and_csrf_cookies` centralizes cookie setting across all authentication flows (Local Admin, LDAP, OIDC callback, MFA TOTP/Passkey step-up, and First-Boot Setup claim).
- **Persistent vs Ephemeral Lifetimes:**
  - When `remember_me=False`: session cookies are issued as browser session cookies (omitting `Max-Age` and `Expires`), causing the browser to discard them upon close.
  - When `remember_me=True`: session cookies carry `Max-Age=2592000` (30 days) and standard HTTP `Expires` attributes.
  - Idle timeout is extended to 7 days for persistent sessions while maintaining 30-day absolute expiration.
- **Dual Plain-HTTP Fallback:** Emits both prefixed `__Host-` cookies (for TLS/HTTPS environments) and un-prefixed fallback cookies (`kb_session`, `kb_csrf`) for direct loopback, Docker, and plain-HTTP development environments.
- **CSRF Cookie Stability (`GET /api/v1/auth/session`):**
  - When an incoming request presents a valid, active CSRF token, `GET /api/v1/auth/session` reuses it rather than issuing a new `Set-Cookie` header on every call. This prevents concurrency race conditions during parallel frontend requests.

---

## 2. Test Suite & Proof Verification

### 2.1 Backend Unit & Integration Tests
- Executed `kanban/tests/auth/test_session_persistence.py`, `database/tests/migrations/test_p4_19_persistent_sessions_migration.py`, `database/tests/test_migration_consistency_static.py`, and `database/tests/test_p1_17_models.py`:
  - 15 passed in 1.13s, 0 failures, 0 regressions.
  - Validated:
    - OIDC callback durable commit and session persistence.
    - Persistent sessions (`remember_me=True`) receive 30-day `Max-Age` and `Expires`.
    - Ephemeral sessions (`remember_me=False`) omit `Max-Age` / `Expires`.
    - Plain-HTTP fallback cookies set correctly.
    - CSRF token stability: zero redundant `Set-Cookie` on `/api/v1/auth/session`.
    - Alembic migration `p4_19_persistent_sessions` upgrade/downgrade round-trip and column parity.

### 2.2 Proof Artifacts Audit (`docs/qa/KANBA-186/`)
- `git-diff.patch`: Complete unified diff against base commit.
- `changed-files-manifest.txt`: 40 files cataloged with SHA-256 digests and line counts.
- `unit-test-results.txt`: Confirms all pytest and vitest suites passed cleanly.
- `build-check.txt`: Clean static analysis (`ruff check .`, `ruff format --check .`, `mypy`, `lint-imports`, `check-migrations --static-only`, `check_no_dashes`).
- `contract-sample.json`: Valid JSON contract sample documenting `login_persistent_true`, `login_persistent_false`, and `get_session_stability_with_existing_csrf`.
- `message-to-reality-checker.md`: Clear narrative summarizing requirements, forward migration chaining, and DoD fulfillment.

---

## 3. Specialist Verdict

The implementation in commit `2b3c84d` satisfies all backend architectural requirements, database migration invariants, session persistence contracts, and CSRF token stability guarantees specified in KANBA-186.

**Verdict: APPROVED**
