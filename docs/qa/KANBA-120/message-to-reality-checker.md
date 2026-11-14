# Message to Reality-Checker: KANBA-120 (KB-P2-10)

## Overview & Executive Summary

- **Ticket**: `KANBA-120` (`KB-P2-10`: `[Phase 2 / Auth] Auth card admin API: CRUD, toggle, COLLATE "C" fractional reorder, live test-handshake & public enabled-cards endpoint`)
- **Worktree**: `/tmp/kb-wt-KB-P2-10`
- **Branch**: `feat/KB-P2-10`
- **Target Modules**:
  - `database/migrations/versions/p2_10_auth_card_admin_ops.py`
  - `database/migrations/sql/p2_10_auth_card_admin_ops.up.sql`
  - `database/migrations/sql/p2_10_auth_card_admin_ops.down.sql`
  - `kanban/util/fractional_rank.py`
  - `kanban/auth/cards/schemas.py`
  - `kanban/auth/cards/repository.py`
  - `kanban/auth/cards/lockout.py`
  - `kanban/auth/cards/handshake.py`
  - `kanban/auth/cards/service.py`
  - `kanban/api/v1/auth_cards_public.py`
  - `kanban/api/v1/admin/auth_cards.py`
  - `kanban/services/activity.py`

This implementation delivers the administrative management API and public projection for Multi-Card Authentication. It enforces zero secret leakage across public and admin wire contracts, strict base-62 fractional indexing under PostgreSQL `COLLATE "C"`, multi-layer anti-lockout safeguards, an 8.0s bounded live test-handshake probe, write-only envelope encryption of credentials, and role-based capability enforcement (`SERVER_ADMIN` + AAL2).

---

## Architectural & Security Invariants

### 1. Database Privileges & Schema Definers (Spec S4.1)
- The migration extends `auth_provider_cards` with `last_admin_handshake_at TIMESTAMPTZ` and deploys 5 `SECURITY DEFINER` functions in schema `kb_auth`:
  - `card_list_enabled_public`: Returns `(id, slug, display_name, button_subtext, icon_preset, provider_kind)` for enabled cards ordered by `sort_rank COLLATE "C" ASC, id ASC`.
  - `card_admin_set_enabled`: Toggles card enablement while enforcing anti-lockout checks.
  - `card_admin_reorder`: Updates card `sort_rank`.
  - `card_admin_set_health`: Updates `last_health_status` (`"OK"` or `"FAILED:<CODE>"`) without touching `last_admin_handshake_at`.
  - `card_admin_delete`: Deletes a card while enforcing anti-lockout checks.
- All functions are owned by `kb_auth_owner`, revoked from `PUBLIC`, and granted to `kanban_app`. Tables remain protected by `FORCE ROW LEVEL SECURITY`.

### 2. Base-62 Fractional Ranking Under COLLATE "C" (Spec S6.4)
- Implemented in `kanban/util/fractional_rank.py` using 62 ASCII characters (`0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz`) matching PostgreSQL `COLLATE "C"` byte ordering (`'0' < '9' < 'A' < 'Z' < 'a' < 'z'`).
- `midpoint_rank(prev, nxt)` computes lexicographic midpoints without trailing `'0'` characters, preventing fractional string growth traps.
- `needs_rebalance` flags cards when `len(sort_rank) > 32`, and `rebalance_ranks` cleanly re-spaces ranks using 4-character identifiers.

### 3. Public Login Projection (Spec S4.3, Consumer KB-P3-35)
- `GET /api/v1/auth/cards` emits strictly the `AuthCardPublic` model with `extra="forbid"` containing only public button metadata (`id`, `slug`, `display_name`, `button_subtext`, `icon_preset`, `provider_kind`).
- Zero secrets (`encrypted_secret_blob`, `wrapped_dek`, `dek_kid`), configurations (`client_id`, `issuer`), or operational metrics (`last_health_status`) appear in the public payload.
- `GET /api/v1/auth/cards/{slug}/start` translates `?next=` to `return_to` and routes OIDC/OAuth2 authentication flows, returning 404 for disabled or non-OIDC cards.

### 4. Admin API & AAL2 Guard (Spec S4.1, S4.2, Consumer KB-P3-36)
- Every `/api/v1/admin/auth-cards*` route enforces `Depends(require_admin_aal2)` and `Depends(require_server_admin)` (`403 INSUFFICIENT_CAPABILITY` for non-server admins).
- Client secrets accepted in `POST` / `PATCH` are immediately sealed via `seal_card_secret` using envelope encryption, and memory buffers are erased immediately.
- `DELETE /api/v1/admin/auth-cards/{card_ref}` requires request body `{"confirm_slug": "<slug>"}`, returning `422 CONFIRM_PHRASE_MISMATCH` on mismatch.

### 5. Multi-Layer Anti-Lockout Safeguards (KB-P2-09)
- Both database trigger and application service enforce:
  - **Layer 1**: Disabling or deleting a card must not leave zero enabled cards capable of authenticating an active `SERVER_ADMIN`.
  - **Layer 2**: Disabling `LOCAL_ADMIN` requires a verified login on an external card (`OIDC`, `OAUTH2`, `LDAP`) by a `SERVER_ADMIN` within 15 minutes (`last_admin_handshake_at >= clock_timestamp() - INTERVAL '15 minutes'`).
- Violations produce RFC 7807 409 `LOCKOUT_PREVENTED` with `{layer: "db_trigger" | "handshake_probe_15m"}`.

### 6. Live Test-Handshake Probe (Spec S4.1)
- `POST .../test-handshake` runs an 8.0s timeout probe across OIDC discovery/JWKS keysets, OAuth2 authorization endpoints, LDAP TCP/TLS/bind, and Local Admin Argon2id hashing.
- Updates `last_health_status` without ever modifying `last_admin_handshake_at`.

---

## Test Verification & Quality Metrics

1. **Mandatory Feature Test Cases (8/8 Passed)**:
   - Case 1: Positive CRUD & Public Projection (`test_case_1_positive_crud_and_public_projection`) - PASSED
   - Case 2: Security & Zero Secret Leakage (`test_case_2_security_zero_secret_leakage`) - PASSED
   - Case 3: Fractional Rank & COLLATE "C" Invariant (`test_case_3_fractional_rank_collate_c`) - PASSED
   - Case 4: Live Test-Handshake & Health Status (`test_case_4_handshake_probe_diagnostics`) - PASSED
   - Case 5: 3-Layer Anti-Lockout Enforcement Over HTTP (`test_case_5_lockout_enforcement_over_http`) - PASSED
   - Case 6: Deletion Safeguards & Phrase Confirmation (`test_case_6_delete_confirmation`) - PASSED
   - Case 7: Authorization & AAL2 Wall (`test_case_7_authz_and_aal2_wall`) - PASSED
   - Case 8: Validation Boundaries & Slug Grammar (`test_case_8_validation_boundaries`) - PASSED

2. **Automated Test Results**:
   - Total tests executed: 39 passed in ~4.4s.
   - Test suites:
     - `kanban/tests/util/test_fractional_rank.py`: 5 passed
     - `kanban/tests/auth/test_auth_cards_admin_api.py`: 7 passed
     - `kanban/tests/auth/test_auth_cards_public_api.py`: 4 passed
     - `kanban/tests/auth/test_auth_cards_handshake_unit.py`: 12 passed
     - `kanban/tests/auth/test_auth_cards_service_unit.py`: 9 passed
     - `kanban/tests/auth/test_card_repository.py`: 2 passed
   - Combined coverage: 95% total across target modules (`schemas.py` 100%, `lockout.py` 100%, `repository.py` 99%, `handshake.py` 96%, `service.py` 92%).

3. **Static Analysis & Linters**:
   - `ruff check .`: 0 errors
   - `ruff format --check .`: 0 errors (955 files verified)
   - `mypy --strict kanban database`: 0 issues (452 source files)
   - `lint-imports`: 2 kept, 0 broken
   - `scripts/license_gate.py`: 0 violations
   - `scripts/check_no_dashes.py --all`: 0 violations

4. **Dual Specialist Sign-Offs**:
   - API Specialist Gate: APPROVED by `@arch-reviewer` (`docs/qa/KANBA-120/api-specialist-review.md`, Board #763)
   - UI Specialist Gate: APPROVED by `@ui-specialist` (`docs/qa/KANBA-120/ui-specialist-review.md`, Board #771)
   - Dependency Evaluation: Verified zero new runtime or build dependencies declared.
