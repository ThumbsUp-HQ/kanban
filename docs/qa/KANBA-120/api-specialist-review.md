# API Specialist Gate Review: KANBA-120 (KB-P2-10)

- **Ticket**: `KANBA-120` (`KB-P2-10`: Auth card admin API: CRUD, toggle, COLLATE "C" fractional reorder, live test-handshake & public enabled-cards endpoint)
- **Reviewer**: `@arch-reviewer` (Systems/Backend Architect & API Specialist)
- **Branch**: `feat/KB-P2-10`
- **Worktree**: `/tmp/kb-wt-KB-P2-10`
- **Scope**: `database/migrations/versions/p2_10_auth_card_admin_ops.py`, `kanban/api/v1/auth_cards_public.py`, `kanban/api/v1/admin/auth_cards.py`, `kanban/auth/cards/`, `kanban/util/fractional_rank.py`
- **Board Ref**: Approved by `@arch-reviewer` in Swarm Message #763

---

### 1. Architectural & Security Evaluation

#### A. Database Schema & Privilege Isolation (Spec S4.1)
- The migration `database/migrations/sql/p2_10_auth_card_admin_ops.up.sql` extends `auth_provider_cards` with `last_admin_handshake_at TIMESTAMPTZ` and provides clean bidirectional Alembic reversibility (`upgrade head` -> `downgrade -1` -> `upgrade head`).
- All 5 functions (`card_list_enabled_public`, `card_admin_set_enabled`, `card_admin_reorder`, `card_admin_set_health`, `card_admin_delete`) are defined in `kb_auth`, owned by `kb_auth_owner`, declared `SECURITY DEFINER` with search path pinned to `pg_catalog, public`.
- Privileges are revoked from `PUBLIC` and granted selectively to `kanban_app`. Direct table access remains revoked under `FORCE ROW LEVEL SECURITY`.

#### B. Public Endpoint Projection & Zero Secret Leakage (Spec S4.3, Consumer KB-P3-35)
- `GET /api/v1/auth/cards` returns strictly the projection model `AuthCardPublic` (`extra="forbid"`): `id: UUID`, `slug`, `display_name`, `button_subtext`, `icon_preset`, `provider_kind`.
- Zero internal configurations (`client_id`, `issuer`, `allowed_email_domains`, `auto_provision_users`), health statuses (`last_health_status`), or encrypted blobs (`encrypted_secret_blob`, `wrapped_dek`, `dek_kid`) are ever emitted on the public wire.
- `GET /api/v1/auth/cards/{slug}/start` correctly maps query parameter `?next=` to `return_to` and delegates to `OidcFlow.start()` for enabled OIDC/OAuth2 cards, returning 404 for disabled or non-OIDC cards.

#### C. Fractional Indexing & COLLATE "C" Strict Byte Ordering (Spec S6.4)
- `kanban/util/fractional_rank.py` implements 62-character base-62 ordering: `0-9A-Za-z` where `'0' < '9' < 'A' < 'Z' < 'a' < 'z'`, matching PostgreSQL `COLLATE "C"`.
- `midpoint_rank(prev, nxt)` generates midpoints without trailing `'0'` characters, preventing string growth traps.
- `needs_rebalance` detects rank lengths exceeding 32 characters, and `rebalance_ranks` cleanly re-spaces cards using 4-character identifiers.

#### D. Admin API Security & AAL2 Guard (Spec S4.1, S4.2, Consumer KB-P3-36)
- Every route under `/api/v1/admin/auth-cards*` declares `Depends(require_admin_aal2)` and `Depends(require_server_admin)`. Non-SERVER_ADMIN callers are rejected with RFC 7807 403 `INSUFFICIENT_CAPABILITY`. Verified via `assert_admin_routes_protected(app)`.
- Client secrets accepted during `POST` and `PATCH` are immediately sealed using envelope encryption (`seal_card_secret`), and plaintext buffers are wiped immediately.
- `DELETE /api/v1/admin/auth-cards/{card_ref}` strictly enforces confirmation body `{"confirm_slug": "<slug>"}`, rejecting mismatches with 422 `CONFIRM_PHRASE_MISMATCH`.

#### E. Anti-Lockout Safeguards & Live Probe Boundaries (KB-P2-09)
- Both database trigger and application service enforce Layer 1 (never allow disabling/deleting the last enabled card that can authenticate an active SERVER_ADMIN) and Layer 2 (disabling LOCAL_ADMIN requires verified login on an external card within 15 minutes).
- Violations emit RFC 7807 409 `LOCKOUT_PREVENTED` with `{layer: "db_trigger" | "handshake_probe_15m"}`.
- `POST .../test-handshake` executes an 8.0s bounded probe of OIDC discovery/JWKS, OAuth2 endpoints, LDAP TCP/TLS/bind, and Local Admin Argon2id hashing, updating `last_health_status` while strictly never modifying `last_admin_handshake_at`.

---

### 2. Verification & Test Metrics

- **Unit Tests**: 39/39 pytest passing in 4.36s covering all 8 mandatory feature test cases:
  - Case 1: Positive CRUD & Public Projection
  - Case 2: Security & Zero Secret Leakage
  - Case 3: Fractional Rank & COLLATE "C" Invariant
  - Case 4: Live Test-Handshake & Health Status
  - Case 5: 3-Layer Anti-Lockout Enforcement Over HTTP
  - Case 6: Deletion Safeguards & Phrase Confirmation
  - Case 7: Authorization & AAL2 Wall
  - Case 8: Validation Boundaries & Slug Grammar
- **Test Coverage**: 95% total coverage across target modules (`schemas.py` 100%, `lockout.py` 100%, `repository.py` 99%, `handshake.py` 96%, `service.py` 92%).

---

### 3. Final Sign-Off
- **Verdict**: APPROVED. All API contracts, database security boundaries, anti-lockout layers, and secret sealing invariants meet architectural requirements without deviation.
