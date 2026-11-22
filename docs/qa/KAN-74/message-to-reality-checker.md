# Forensic Verification Proof Packet: KAN-74

## Ticket Identification
- **Ticket ID:** KAN-74 ([KB-AUTH-OIDC-EXCHANGE-01])
- **Title:** Add Headless Workload Identity Federation & RFC 8693 OAuth 2.0 Token Exchange for /mcp/*
- **Branch:** `feat/KAN-74-workload-oidc-exchange`
- **Worktree:** `/home/adamoutler/.gemini/antigravity-cli/worktrees/ceecd8ef-f0c3-4c2c-b75c-e6eb23e99760/swarm-b-kan74-0d650313`
- **Scope Classification:** UI and Backend Dual Specialist Gate (API, MCP, Security, Frontend Studio)

---

## 1. Executive Summary & Verification Narrative

Ticket KAN-74 implements headless Workload Identity Federation and RFC 8693 OAuth 2.0 Token Exchange for the Kanban platform. This allows headless CI/CD systems (GitHub Actions, GitLab CI, Kubernetes service accounts) to securely authenticate and access `/mcp/agent` and `/mcp/docs` surfaces without long-lived static API secrets or passwords.

### Core Problems Implemented:

1. **Problem 1: Database Storage & Invariants (`database/models/workload_identity.py`, `database/migrations/versions/p6_08_workload_identity_policies.py`)**
   - Tables: `workload_identity_policies` and `workload_jti_replays` with PostgreSQL Row-Level Security (`ENABLE ROW LEVEL SECURITY` and `FORCE ROW LEVEL SECURITY`).
   - RLS policy on `workload_jti_replays` supports public `/oauth/token` exchange where `app_current_workspace_id() IS NULL OR workspace_id = app_current_workspace_id()`.
   - Unique constraints on `(workspace_id, name)` and `(policy_id, jti)` prevent duplicate policies and enforce atomic token replay protection.
   - Synchronized SQLAlchemy models in `database/models/workload_identity.py` exported via `database/models/__init__.py`.

2. **Problem 2: SSRF-Safe Workload JWT Validation (`kanban/auth/oidc/workload.py`)**
   - Implements `validate_workload_jwt(session, raw_jwt, policy)` reusing `fetch_discovery()` and `JwksCache` from `kanban.auth.oidc.discovery`.
   - Algorithm enforcement: only `RS256`, `PS256`, `ES256`, `EdDSA` allowed; `alg="none"` and symmetric `HS*` algorithms strictly forbidden with 400 `invalid_grant`.
   - Claim validations: byte-for-byte `iss` match against `policy.issuer`, `aud` match against `policy.client_id`, `exp` and `nbf` time validity, and `iat` skew/age `<= 600s`.
   - Subject pattern matching: exact match or glob pattern via `fnmatch` against `policy.subject_pattern`.
   - Claims filtering: validates JSON subset matches in `policy.required_claims_json`.
   - Replay prevention: atomic PostgreSQL `ON CONFLICT DO NOTHING` insert into `workload_jti_replays`; returns 401 `WORKLOAD_TOKEN_REPLAYED` upon replay.

3. **Problem 3: RFC 8693 Token Exchange & Activity Logging (`kanban/api/v1/oauth.py`)**
   - Extends `/.well-known/oauth-authorization-server` declaring `urn:ietf:params:oauth:grant-type:token-exchange` in `grant_types_supported` and supported token types.
   - Handles `POST /oauth/token` for `grant_type=urn:ietf:params:oauth:grant-type:token-exchange`:
     - Accepts `subject_token_type` as `urn:ietf:params:oauth:token-type:jwt` or `id_token`.
     - Validates client IP against `policy.allowed_cidrs`.
     - Mints short-lived ES256 access tokens (`ttl <= policy.max_ttl_seconds`, zero `refresh_token`) embedding `surface`, `scopes`, `allowed_project_ids`, and `capability_mask`.
     - Emits `WORKLOAD_TOKEN_EXCHANGED` activity record on the SHA-256 ledger.

4. **Problem 4: Admin CRUD API & Frontend Studio (`kanban/api/v1/admin/workload_identities.py`, `kanban/web/src/features/settings/McpUnifiedStudio.tsx`)**
   - Full AAL2-protected REST CRUD routes: `GET`, `POST`, `PATCH`, `DELETE` at `/api/v1/admin/workload-identities`.
   - `McpUnifiedStudio.tsx`: includes `WorkloadFederationSection` component for administrators to view, create, edit, toggle, and delete workload federation policies with inline AAL2 step-up verification. Zero inline styles.
   - Fast-path MCP authentication in `mcp/auth.py`: validates workload access tokens directly, enforces `allowed_cidrs` and project boundaries via `CredentialBoundary`, and applies capability masking.

---

## 2. Definition of Done Checklist & Evidence Mapping

| Definition of Done Requirement | Status | Primary Evidence File | Verification Details |
| :--- | :---: | :--- | :--- |
| **Alembic Migration & RLS Models** | PASS | `database/migrations/versions/p6_08_workload_identity_policies.py` | 68 migrations valid, single-head chain, RLS enabled and forced, foreign keys cascade. |
| **Workload JWT Validator** | PASS | `kanban/auth/oidc/workload.py` | 96% branch coverage, rejection of unsigned/HMAC, SSRF-safe discovery, JTI replay prevention. |
| **RFC 8693 Token Exchange** | PASS | `kanban/api/v1/oauth.py` | Grant type supported, ES256 minted, CIDR enforced, ledger event logged. |
| **Admin CRUD Endpoints** | PASS | `kanban/api/v1/admin/workload_identities.py` | Full CRUD operations, AAL2 requirement enforced via `require_admin_aal2`. |
| **MCP Fast-Path Auth** | PASS | `mcp/auth.py` | Surface checks (/mcp/agent, /mcp/docs), CredentialBoundary enforcement, CIDR checks. |
| **Frontend Workload Studio** | PASS | `kanban/web/src/features/settings/McpUnifiedStudio.tsx` | WorkloadFederationSection, policy creation/edit modal, toggle, delete, AAL2 handling. |
| **Backend Test Suite (>=95% coverage)** | PASS | `docs/qa/KAN-74/unit-test-results.txt` | 21 tests pass, 96% branch coverage on workload.py, admin protection tests pass. |
| **Frontend Vitest Suite** | PASS | `docs/qa/KAN-74/unit-test-results.txt` | 22 tests pass in McpUnifiedStudio.test.tsx including 6 WorkloadFederationSection tests. |
| **Typecheck, Lint & Build** | PASS | `docs/qa/KAN-74/build-check.txt` | tsc -b, eslint 0 warnings, vite build 1.42s, make check (ruff, mypy, lint-imports). |
| **No Em-Dashes or En-Dashes** | PASS | `docs/qa/KAN-74/build-check.txt` | `check_no_dashes --all` reports 0 errors across entire repository. |

---

## 3. Forensic Proof Inventory

1. **`git-diff.patch`:** Git diff against `main` encompassing all owned backend, frontend, migration, and test changes.
2. **`unit-test-results.txt`:** Test logs of pytest and Vitest runs with branch coverage metrics.
3. **`build-check.txt`:** Verification logs of `make check` (ruff, mypy, lint-imports, check-migrations, check_no_dashes) and frontend typecheck, lint, and build.
4. **`contract-sample.json`:** Canonical JSON samples of policy creation, RFC 8693 token exchange, replay rejection, and MCP CredentialBoundary.
5. **`changed-files-manifest.txt`:** Cryptographic SHA-256 checksum manifest of all files touched in this ticket.
