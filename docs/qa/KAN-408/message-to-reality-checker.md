# Forensic QA Reality-Checker Handover Packet

**Ticket:** KAN-408 (`[SLICE-1-P3][KB-AUTH-WORKOUT]`)  
**Parent Epic:** KAN-405 (`[EPIC][SLICE-1-AUTH-RBAC]`)  
**Target Next Phase:** KAN-409 (`[SLICE-1-P4][KB-AUTH-RUNBOOKS]`)  
**Author:** b-kan408 (Paranoiac Android Security Architect)  
**Branch:** `feat/KAN-408-slice1-auth-workout`  
**Base Commit:** `1bbc9981`  
**Worktree:** `/home/adamoutler/.gemini/antigravity-cli/worktrees/9e0717fe-81d4-4260-b1a8-c35c5f951afb/swarm-b-kan408-7b120ade`  

---

## 1. Executive Summary & Verification Invariants

This packet provides indisputable forensic verification evidence for ticket **KAN-408: Phase 3 Live AD/LDAPS, OIDC, Passkey/TOTP & RBAC Credential Workout + Final Screenshots**.

- **Protected Pre-Production Protection (Priority #0):**
  - STRICT NON-DESTRUCTIVE INVARIANT: 100% of live workouts executed against isolated local companion daemons and local PostgreSQL (`/tmp/kb-pgsock`, container `swarm-b-kan408-7b120ade-pg-test-1`).
  - Zero requests, connections, or mutations directed to `k.hackedyour.info`, `192.168.1.101`, or `inferrence1`.
- **Disjoint Host Port Allocation & Clean Teardown:**
  - Bound exclusively to `127.0.0.1` using ports `18408` (Kanban ASGI), `10389` (Plain/StartTLS LDAP), `10636` (TLS LDAPS), and `18081` (HTTPS OIDC IdP).
  - All temporary companion daemons and workout containers were terminated immediately after evidence capture; verified `ss -tulpn | grep -E "18408|10389|10636|18081"` returns empty.
- **Zero-Mock Playwright Evidence:**
  - All 11 screenshots were captured via real Playwright Chromium instances executing against live backend HTTP responses on `http://127.0.0.1:18408` with zero `page.route` intercepts or mock API shims.
- **Zero Unicode Dashes:**
  - Verified 0 Unicode em-dash or en-dash characters across all documentation and QA files using `python3 scripts/check_no_dashes.py --all`.
- **Secret Scrubbing:**
  - All logs, reports, and payloads scrubbed via `kanban.security.scrubber.scrub_text` (0 exposed tokens, session cookies, private keys, or passwords).

---

## 2. Summary of Live Credential Workouts

### Workout 1: Local Admin, WebAuthn Passkeys, TOTP, Recovery Codes & Break-Glass Lockout Guard
- **WebAuthn Registration & Options:** Verified `rp.name = "👍kanban"` and ASCII FQDN `rp.id = "127.0.0.1"` (`POST /api/v1/auth/webauthn/register/options`).
- **TOTP Setup & Confirmation:** Setup and confirmed authenticator application stepping session up to AAL2 (`confirmed_aal: 2`).
- **Single-Use Recovery Code Redemption:** Successfully redeemed a single-use recovery code (`POST /api/v1/auth/mfa/recovery/stepup`) stepping session up to AAL2 (`stepup_aal: 2`).
- **Recovery Codes Regeneration:** Regenerated 10 fresh cryptographically random recovery codes as an authenticated AAL2 user (`POST /api/v1/auth/mfa/recovery/regenerate`).
- **Break-Glass Lockout Guard (HTTP 409 Conflict):** Attempted to disable the `LOCAL_ADMIN` auth card without a verified external admin login in the last 15 minutes. Backend strictly blocked mutation with HTTP 409 Conflict (`code: "LOCKOUT_PREVENTED"`, `layer: "handshake_probe_15m"`), preventing catastrophic administrator lockout.

### Workout 2: LDAPS / StartTLS Handshake, Nested AD Group Sync & Dirty-Drawer WebSudo Replay
- **Draft Handshake Probe:** `test-draft` endpoint failed closed on invalid credentials (`ok: false, status: "FAILED:LDAPBINDERROR"`) and succeeded in 3ms with valid pinned CA PEM.
- **Enterprise LDAPS Login & Provisioning:** User Hermes Conrad authenticated via LDAPS on port 10636 and was auto-provisioned into the local database with verified identity linking.
- **Nested AD Group -> RBAC Synchronization:** Nested Active Directory group `Bureaucrats Group` correctly mapped and synchronized external membership to the canonical `WORKSPACE_MEMBER` role.
- **Sliding-Window WebSudo Dirty-Drawer In-Modal Replay:** Dropped AAL2 elevation via `POST /api/v1/auth/aal2/drop`. Attempted card save in `AuthCardEditorDrawer` returned HTTP 403 `AAL2_REQUIRED`. The organic `Admin Verification Required (AAL2)` modal popped up directly over the dirty drawer preserving all typed LDAP parameters, entered recovery code, and replayed card save to HTTP 201 Created.

### Workout 3: OIDC PKCE S256 Login, Verified-Claim Linking & Unverified Email Block
- **PKCE S256 Code Flow:** Executed full authorization code grant with `code_challenge_method: "S256"` and secure loopback redirect.
- **Verified-Claim Account Linking:** User Amy Wong authenticated via OIDC with `email_verified: true`, auto-linking external OIDC identity to existing workspace account.
- **Unverified Email Auto-Merge Block (HTTP 403 Forbidden):** External identity presenting unverified email claim (`email_verified: false`) was strictly rejected from auto-merging with HTTP 403 (`code: "EMAIL_NOT_VERIFIED"`), stopping account takeover attacks cold.

### Workout 4: Custom RBAC Role Enforcement
- **Policy Builder Configuration:** Created custom role `Quality Auditor Lead` (color `#10b981`, auto-slug `quality-auditor-lead`) using bulk selectors (`Select All`, `Clear All`, `Read-Only`).
- **Granular Capability Assignment:** Assigned `issue:view` and `issue:comment` capabilities to user Philip J. Fry.
- **Live Capability Enforcement:** User Fry successfully accessed authorized profile and issue endpoints (`HTTP 200 OK`) while non-admin boundary strictly denied privilege escalation to administrative endpoints (`HTTP 403 Forbidden`).

---

## 3. Automated Test Verification & Quality Gates

### 3.1 Backend Test Suite (Pytest)
Command:
```bash
PYTHONPATH=. uv run --no-sync pytest \
  kanban/tests/auth/test_auth_cards*.py \
  kanban/tests/auth/test_ldap_tls_and_bind.py \
  kanban/tests/auth/test_ldap_service_unit.py \
  kanban/tests/auth/test_ldap_group_sync.py \
  kanban/tests/auth/test_oidc_flow.py \
  kanban/tests/auth/test_identity_linking_real_pg_e2e.py \
  kanban/tests/api/test_granular_rbac_api.py \
  --cov=kanban/auth/cards \
  --cov=kanban/auth/ldap \
  --cov-report=term-missing \
  -p no:xdist
```
- **Results:** 106 passed in 33.87s.
- **Warnings / Failures:** 0 errors, 0 failures, 0 warnings.
- **Coverage:** >=95% on all touched authentication and LDAP modules:
  - `kanban/auth/ldap/service.py`: **99%** (147 stmts, 0 missed, 48 branches, 2 part)
  - `kanban/auth/ldap/sync.py`: **100%** (74 stmts, 0 missed, 32 branches)
  - `kanban/auth/cards/service.py`: **98%** (328 stmts, 3 missed, 126 branches, 4 part)
  - `kanban/auth/cards/handshake.py`: **96%** (94 stmts, 2 missed, 28 branches, 3 part)
  - `kanban/auth/cards/schemas.py`: **100%** (100 stmts, 0 missed)
  - `kanban/auth/ldap/client.py`: **97%** (233 stmts, 6 missed)

### 3.2 Frontend Test Suite (Vitest)
Command:
```bash
(cd kanban/web && COVERAGE_INCLUDE="src/features/admin-auth/AuthStudioPage.tsx,src/features/admin-auth/AuthCardEditorDrawer.tsx,src/features/rbac/RbacPolicyBuilder.tsx" npx vitest run src/features/admin-auth/AuthStudioPage.test.tsx src/features/admin-auth/AuthCardEditorDrawer.test.tsx src/features/rbac/__tests__/RbacPolicyBuilder.test.tsx --coverage)
```
- **Results:** 122 passed in 8.92s across 3 test files.
- **Coverage Metrics:**
  - Statements: 99.02%
  - Branches: 95.76% (threshold: 95%)
  - Functions: 100.0%
  - Lines: 99.8%
- **Warnings:** 0 `act(...)` stderr warnings.

### 3.3 Static Linters & Build Pipeline
- `uv run ruff check kanban/`: Passed (0 errors).
- `uv run --no-sync mypy kanban/`: Passed (0 issues across 681 files).
- `python3 scripts/check_no_dashes.py --all`: Passed (0 Unicode dash violations).
- `pnpm --dir kanban/web typecheck`: Passed (0 TypeScript errors).
- `pnpm --dir kanban/web lint`: Passed (0 ESLint warnings or errors).
- `pnpm --dir kanban/web build`: Passed (built in 1.28s).

---

## 4. Reality-Checker Findings Remediation (Rounds 1, 2, and 3)

All findings from prior audit rounds have been fully resolved:
1. **Critical Secret Removal (Round 1):** Purged all references to temporary tokens. Verified `git diff 1bbc9981 | grep -E 'kb_agt_'` returns 0 matches.
2. **Workout 4 Real RBAC 403 Enforcement (Round 1):** Philip J. Fry verified granted permissions (`issue:view` -> HTTP 200, `issue:comment` -> HTTP 201) and strictly denied permissions (`issue:delete` preview -> HTTP 403, delete -> HTTP 403, role creation -> HTTP 403).
3. **WebAuthn Verification & StartTLS 10389 (Round 1):** Integrated `SoftAuthenticator` verifying registration (`200 OK`, `verified: true`) and assertion (`200 OK`, `auth_aal: 2`), untrusted CA probe, and StartTLS probe.
4. **Verbatim Wire Transcript (Round 2):** All HTTP blocks in `03-live-workout-report.md` generated directly from wire transcript in `workout-transcript.txt`.
5. **Distinct Screenshots 10 & 11 (Round 3):** Reordered capture sequence so authenticated views of Users & Permissions (10) and Roles & Permissions (11) are taken before session expiration. Distinct SHA-256 verified: `10` (`b739a303...`) != `11` (`04d313b3...`).
6. **Organic WebSudo Replay over Dirty Drawer (Round 3):** Dropped AAL2 via `/api/v1/auth/aal2/drop`. Screenshot `09-websudo-replay-active.png` (`c66e8657...`) captures the `Admin Verification Required (AAL2)` modal directly over the dirty LDAP drawer, entered recovery code, and replayed card save to HTTP 201 Created.
7. **Service Coverage >=95% (Round 3):** Created `kanban/tests/auth/test_ldap_service_unit.py` bringing `kanban/auth/ldap/service.py` to 99% coverage.

---

## 5. Visual Evidence & Screenshots

All 11 zero-mock captures were recorded in `docs/qa/KAN-408/screenshots/` and `docs/workouts/slice-1-auth-rbac/screenshots/` and visually verified via `read_file`:
- `01-desktop-1440x900-light.png`: 1440x900 Light Desktop - Add Auth Card drawer with 1-click presets and advanced settings.
- `02-desktop-1440x900-dark.png`: 1440x900 Dark Desktop - High-contrast dark theme with lockout prevention banner and Sudo status pill.
- `03-desktop-1024x768.png`: 1024x768 Small Desktop - Roles & Permissions view with permission category matrix.
- `04-tablet-portrait-768x1024.png`: 768x1024 Tablet Portrait - Corporate Google SSO OIDC drawer with loopback redirect URI notice.
- `05-mobile-portrait-390x844.png`: 390x844 Mobile Portrait - Vertical reflow of auth cards and responsive action controls without horizontal scroll.
- `06-passkey-webauthn-registered.png`: Desktop Profile Settings - Registered WebAuthn passkey and active 2FA status card.
- `07-totp-recovery-codes.png`: Desktop Modal - One-Time Recovery Codes modal with 10 cryptographically random codes and Copy action.
- `08-ldap-test-draft-success.png`: Desktop Drawer - Planet Express LDAPS Enterprise drawer with live handshake test parameters.
- `09-websudo-replay-active.png`: Desktop Modal - Admin Verification Required (AAL2) modal over blurred drawer backdrop preserving typed input (SHA `c66e8657...`).
- `10-oidc-verified-claim-linked.png`: Desktop Users Table - External LDAP and OAuth2 provisioned principals with role grant dropdowns (SHA `b739a303...`).
- `11-custom-rbac-policy-builder.png`: Desktop Role Builder - Custom RBAC Policy Builder with Quality Auditor Lead role and granular capabilities (SHA `04d313b3...`).

---

## 6. Specialist Audits

- **API Specialist Review:** Signed and **APPROVED** by `api-spec` in `docs/qa/KAN-408/api-specialist-review.md` targeting commit `ccf7c7c3` (review commit `1849fdde`).
- **UI Specialist Review:** Signed and **APPROVED** by `ui-spec` in `docs/qa/KAN-408/ui-specialist-review.md` targeting commit `ccf7c7c3` (review commit `ecf6ba19`).

---

## 7. Verification Commands for Reality-Checker

```bash
# 1. Verify git diff patch against merge-base
git diff $(git merge-base main HEAD)...HEAD -- ':!docs/qa/*' > /tmp/check-diff.patch
diff -u /tmp/check-diff.patch docs/qa/KAN-408/git-diff.patch

# 2. Verify all checksums in manifest
cd docs/qa/KAN-408 && sha256sum -c changed-files-manifest.txt

# 3. Verify zero forbidden Unicode dashes
python3 scripts/check_no_dashes.py --all docs/qa/KAN-408/ docs/workouts/slice-1-auth-rbac/

# 4. Run Pytest backend test suite
KB_TEST_PGHOST=/tmp/kb-pgsock-kan408 PYTHONPATH=. uv run --no-sync pytest \
  kanban/tests/auth/test_auth_cards*.py \
  kanban/tests/auth/test_ldap_tls_and_bind.py \
  kanban/tests/auth/test_ldap_service_unit.py \
  kanban/tests/auth/test_ldap_group_sync.py \
  kanban/tests/auth/test_oidc_flow.py \
  kanban/tests/auth/test_identity_linking_real_pg_e2e.py \
  kanban/tests/api/test_granular_rbac_api.py \
  --cov=kanban/auth/cards \
  --cov=kanban/auth/ldap \
  --cov-report=term-missing \
  -p no:xdist

# 5. Run Vitest frontend test suite
(cd kanban/web && COVERAGE_INCLUDE="src/features/admin-auth/AuthStudioPage.tsx,src/features/admin-auth/AuthCardEditorDrawer.tsx,src/features/rbac/RbacPolicyBuilder.tsx" npx vitest run src/features/admin-auth/AuthStudioPage.test.tsx src/features/admin-auth/AuthCardEditorDrawer.test.tsx src/features/rbac/__tests__/RbacPolicyBuilder.test.tsx --coverage)

# 6. Run static linters and build checks
uv run ruff check kanban/
uv run --no-sync mypy kanban/
python3 scripts/check_no_dashes.py --all
pnpm --dir kanban/web typecheck
pnpm --dir kanban/web lint
pnpm --dir kanban/web build
```
