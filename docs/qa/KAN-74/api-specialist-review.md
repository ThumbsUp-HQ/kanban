# API and Security Specialist Review: KAN-74

- **Ticket:** KAN-74 ([KB-AUTH-OIDC-EXCHANGE-01]) - Add Headless Workload Identity Federation & RFC 8693 OAuth 2.0 Token Exchange for /mcp/*
- **Reviewer:** API & Security Specialist Reviewer (`api-spec`)
- **Review Date:** 2026-11-22
- **Branch:** `feat/KAN-74-workload-oidc-exchange`
- **Commit Under Audit:** `824f2edb` (`feat(auth): add headless workload identity federation and RFC 8693 token exchange for /mcp/* (KAN-74)`)
- **Target Worktree:** `/home/adamoutler/.gemini/antigravity-cli/worktrees/ceecd8ef-f0c3-4c2c-b75c-e6eb23e99760/swarm-b-kan74-0d650313`
- **Status:** APPROVED

---

## 1. Executive Authentication, OAuth, and Security Evaluation

Ticket KAN-74 implements headless Workload Identity Federation and RFC 8693 OAuth 2.0 Token Exchange, enabling external CI/CD pipelines (GitHub Actions, GitLab CI, Kubernetes) to acquire scoped, ephemeral MCP tokens without static API keys.

Key architecture, cryptographic, and security capabilities audited:
1. **Database Schema & RLS Policy Invariants (Alembic `p6_08`):**
   - Implements `workload_identity_policies` and `workload_jti_replays` tables under `ENABLE ROW LEVEL SECURITY` and `FORCE ROW LEVEL SECURITY`.
   - The `workload_jti_replays` RLS policy supports unauthenticated `/oauth/token` exchange while strictly preserving workspace isolation.
   - Unique constraints on `(workspace_id, name)` and `(policy_id, jti)` prevent policy namespace collisions and guarantee atomic JTI token replay rejection.
   - Synchronized SQLAlchemy models in `database/models/workload_identity.py` maintain ORM schema parity.
2. **SSRF-Safe Workload JWT Validation (`kanban/auth/oidc/workload.py`):**
   - Reuses `fetch_discovery()` and `JwksCache` from the hardened OIDC discovery stack.
   - Enforces cryptographic algorithm allowlists: strictly limits allowed algorithms to asymmetric curves (`RS256`, `PS256`, `ES256`, `EdDSA`). Rejects `none` and symmetric `HS*` algorithms with 400 `invalid_grant`.
   - Validates `iss` against configured policy issuer, `aud` against client ID, `exp`/`nbf` timestamps, and enforces `iat` skew `<= 600s`.
   - Evaluates subject claim against `subject_pattern` using exact or `fnmatch` glob pattern matching, and verifies JSON subset matches for `required_claims_json`.
   - Implements atomic replay prevention via PostgreSQL `ON CONFLICT DO NOTHING` in `workload_jti_replays`, returning HTTP 401 `WORKLOAD_TOKEN_REPLAYED` on duplicate submissions.
3. **RFC 8693 OAuth 2.0 Token Exchange Engine (`kanban/api/v1/oauth.py`):**
   - Advertises `urn:ietf:params:oauth:grant-type:token-exchange` in `/.well-known/oauth-authorization-server`.
   - Handles `POST /oauth/token` for token exchange grant requests.
   - Enforces client IP matching against `policy.allowed_cidrs`.
   - Mints ephemeral, ES256-signed access tokens (`ttl <= policy.max_ttl_seconds`, zero refresh tokens) encapsulating `surface`, `scopes`, `allowed_project_ids`, and `capability_mask`.
   - Records an immutable `WORKLOAD_TOKEN_EXCHANGED` event to the SHA-256 activity ledger.
4. **Administration CRUD API & MCP Authentication:**
   - Administrative endpoints at `/api/v1/admin/workload-identities` are strictly protected with `Depends(require_admin_aal2)`.
   - Fast-path MCP authentication in `mcp/auth.py` directly validates workload access tokens, builds the appropriate `CredentialBoundary`, enforces capability masks, and restricts access to declared surfaces (`/mcp/agent`, `/mcp/docs`).

---

## 2. Wire Contracts & Security Invariants

### A. Token Exchange Wire Contracts
- `POST /oauth/token` with valid workload JWT returns HTTP 200 with standard OAuth 2.0 token response (`access_token`, `token_type: "Bearer"`, `expires_in`, `scope`, `issued_token_type`).
- Replay attempt returns HTTP 401 with `error: "WORKLOAD_TOKEN_REPLAYED"`.
- Malformed token or unauthorized claims return HTTP 400 `invalid_grant`.

### B. Tenancy & Anti-Enumeration
- Workload identity policies are strictly workspace-isolated under Row-Level Security.
- Minted tokens cannot escape the `allowed_project_ids` boundary or exceed the specified `capability_mask`.

---

## 3. Unit Test Coverage & Verification Metrics

- **Backend Pytest Results:** 21 passed in 6.52s (`kanban/tests/auth/test_workload_oidc_exchange.py`, `kanban/tests/security/test_admin_routes_protected.py`, `mcp/tests/test_workload_jwt_auth.py`).
- **Backend Branch Coverage:** `kanban/auth/oidc/workload.py` achieved 97% branch coverage (140 statements, 3 misses, 50 branches, 3 partial branches). Exceeds the 95% project threshold.
- **Frontend Vitest Results:** 22 passed in `McpUnifiedStudio.test.tsx` (including 6 dedicated WorkloadFederationSection tests).
- **Static Quality Checks:**
  - `ruff check`: All checks passed (0 errors).
  - `ruff format --check`: 2228 files formatted.
  - `mypy`: 0 issues found in 1240 source files.
  - `lint-imports`: 2 kept, 0 broken contracts.
  - `check-migrations`: Valid single head `p6_08_workload_identity_policies`.
  - `check_no_dashes`: Clean across repository (0 violations).
  - `pnpm typecheck`, `lint`, and `build`: Clean production build in 1.24s.

---

## 4. Final Verdict

- **Result:** APPROVED.
- **Handoff:** Handing off directly to `@ui-spec` for UI Specialist review and routing to `@merge-ci`.
