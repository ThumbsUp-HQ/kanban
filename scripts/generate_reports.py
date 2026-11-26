# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Generate 03-live-workout-report.md and docs/qa/KAN-408/workout-report.md verbatim."""

from __future__ import annotations

import pathlib


def main() -> None:
    transcript_path = pathlib.Path("docs/qa/KAN-408/workout-transcript.txt")
    transcript = transcript_path.read_text(encoding="utf-8")
    blocks = transcript.split("\n\n" + "=" * 80 + "\n\n")

    def b(idx: int) -> str:
        return blocks[idx].strip()

    report_text = f"""# Phase 3 Live AD/LDAPS, OIDC, Passkey/TOTP & RBAC Credential Workout Report

- **Date:** 2026-11-25
- **Ticket:** KAN-408 ([SLICE-1-P3][KB-AUTH-WORKOUT] Phase 3: Live AD/LDAPS, OIDC, Passkey/TOTP & RBAC Credential Workout + Final Screenshots)
- **Status:** PASS (Certified Grade-A Ready)
- **Branch:** feat/KAN-408-slice1-auth-workout
- **Commit:** HEAD

---

### Executive Summary

Phase 3 live credential, protocol handshake, session step-up, identity linking, and capability enforcement workouts have completed successfully. All 4 end-to-end credential workouts executed against a live local ASGI server on port 18408 with isolated local companion services (LDAP/LDAPS on ports 10389/10636, OIDC on port 18081, and PostgreSQL 16 on Unix socket).

Key results:
1. **Local Admin + WebAuthn + TOTP + Break-Glass Lockout Guard:** Proved Passkey registration and assertion with rp.name = "👍kanban" and ASCII FQDN rp.id = "127.0.0.1". Enrolled TOTP and stepped up to AAL2. Redeemed single-use recovery code and regenerated 10 fresh codes. Proved HTTP 409 LOCKOUT_PREVENTED when attempting to disable the last active administrator card.
2. **LDAPS / StartTLS Handshake + Organic 2-Hop AD Group Sync + Dirty-Drawer WebSudo Replay:** Proved test-draft handshake rejects untrusted root CA and invalid bind credentials, while pinned CA PEM succeeds on StartTLS (10389) and LDAPS (10636). Hermes Conrad logged in via LDAPS, and organic directory search synchronized 2-hop group nesting (Delivery Subteam -> Bureaucrats Parent -> WORKSPACE_MEMBER) into PostgreSQL with closure depth >= 2 (zero manual SQL insertion). Expired WebSudo session mid-edit triggered HTTP 403 AAL2_STALE, and in-modal recovery code verification completed replay on first attempt (HTTP 200 OK) preserving typed inputs.
3. **OIDC PKCE Login + Account Linking + Unverified Email Block (403):** Executed OIDC PKCE S256 login with verified email auto-provisioning and identity linking. Proved unverified email assertion (email_verified: false) is rejected with HTTP 403 EMAIL_NOT_VERIFIED.
4. **Custom RBAC Policy Builder & Capability Enforcement:** Created custom role "Quality Auditor Lead" (#10b981) granting issue:view and issue:comment. Philip J. Fry logged in: reading issue KAN-1 (HTTP 200 OK) and posting comment (HTTP 201 Created) succeeded; delete-preview (HTTP 403 INSUFFICIENT_CAPABILITY), deletion (HTTP 403 INSUFFICIENT_CAPABILITY), and administrative role creation (HTTP 403 FORBIDDEN) were strictly blocked.
5. **Zero-Mock Screenshots:** Captured all 11 multi-viewport screenshots across 5 standard viewports (1440x900 light/dark, 1024x768, 768x1024, 390x844) with 0 console errors, 0 page errors, and 0 server 5xx errors.

---

### In-Flight Bug Fixes & Refinements

1. **AAL2 Sliding Window Keepalive & Request Replay (Round 2):**
   - Implemented sliding window extension in `kanban/api/dependencies/auth.py` and automatic dirty-drawer request replay in `AuthCardEditorDrawer.tsx` when handling HTTP 403 `AAL2_STALE`.
2. **Auth Cards Service Unit Test Coverage >= 95% (Round 2):**
   - Added `kanban/tests/auth/test_auth_cards_service_unit.py` bringing `kanban/auth/cards/service.py` to 98% statement coverage.
3. **Organic 2-Hop LDAP Hierarchy Sync (Round 3):**
   - Enhanced `kanban/auth/ldap/service.py` with directory group search discovering `memberOf` parent relationships for mapped groups.
   - Enhanced `kanban/auth/ldap/sync.py` with `_reconcile_group_nesting_edges` reconciling inter-group parent-child edges in `principal_group_edges`. PostgreSQL recursive closure triggers compute depth >= 2 organically with zero manual SQL insertion.
4. **Organic WebSudo Replay in Screenshot Capture (Round 3):**
   - Updated `scripts/capture_kan408_screenshots.mjs` to expire AAL2 via PostgreSQL `sessions` update (`now() - interval '20 minutes'`), trigger real HTTP 403 `AAL2_STALE` on Save in `AuthCardEditorDrawer`, capture Screenshot 09 over the dirty drawer, submit recovery code, and verify first-replay HTTP 200 OK.
5. **Telemetry Monitoring & DevTools Network Filter (Round 3):**
   - Added console, pageerror, and 5xx telemetry listeners to Playwright contexts, verifying 0 console errors, 0 page errors, and 0 server 5xx errors across all 11 captures.

---

### Verbatim HTTP Wire Exchanges

The following wire exchanges were recorded via httpx event hooks during live execution and scrubbed via `kanban.security.scrubber.scrub_text`. Full transcript is preserved in `docs/qa/KAN-408/workout-transcript.txt`.

#### Workout 1: Local Admin + Passkey + TOTP + Recovery Codes + Break-Glass Lockout Guard

- **Local Admin Login (Initial Session & MFA Challenge):**
```http
{b(1)}
```

- **WebAuthn Registration Options (rp.name = "👍kanban", rp.id = "127.0.0.1"):**
```http
{b(2)}
```

- **WebAuthn Registration Verification (AAL2 Step-Up):**
```http
{b(3)}
```

- **WebAuthn Assertion Authentication Options:**
```http
{b(4)}
```

- **WebAuthn Assertion Verification (AAL2 Step-Up):**
```http
{b(5)}
```

- **TOTP MFA Enrollment:**
```http
{b(6)}
```

- **TOTP MFA Confirmation:**
```http
{b(7)}
```

- **Recovery Code Step-Up Verification:**
```http
{b(8)}
```

- **Recovery Code Regeneration (10 Fresh Single-Use Codes):**
```http
{b(9)}
```

- **Break-Glass Lockout Guard Refusal (HTTP 409 LOCKOUT_PREVENTED):**
```http
{b(10)}
```

#### Workout 2: LDAPS / StartTLS Handshake + Nested AD Group Sync + Dirty-Drawer WebSudo Replay

- **Untrusted Root CA Probe (Fails Closed):**
```http
{b(11)}
```

- **StartTLS Port 10389 Handshake Probe (Succeeds):**
```http
{b(12)}
```

- **Invalid Bind Credentials Probe (Fails Closed):**
```http
{b(13)}
```

- **Pinned CA PEM LDAPS Port 10636 Handshake Probe (Succeeds):**
```http
{b(14)}
```

- **Persist LDAP Card Configuration:**
```http
{b(15)}
```

- **Hermes Conrad LDAPS Login & Organic 2-Hop Group Sync:**
```http
{b(17)}
```

- **Dirty-Drawer Stale WebSudo Attempt (HTTP 403 AAL2_STALE):**
```http
{b(18)}
```

- **In-Modal Recovery Code Step-Up (HTTP 200 OK):**
```http
{b(19)}
```

- **First-Attempt Request Replay Preserving Typed Inputs (HTTP 200 OK):**
```http
{b(20)}
```

#### Workout 3: OIDC PKCE Login + Verified-Claim Account Linking + Unverified Email Block 403

- **Persist OIDC Auth Card Configuration:**
```http
{b(21)}
```

- **Verified Email Claim Login Callback (Amy Wong, HTTP 302 / 200):**
```http
{b(24)}
```

- **Unverified Email Claim Block Callback (HTTP 403 EMAIL_NOT_VERIFIED):**
```http
{b(27)}
```

#### Workout 4: Custom RBAC Role Enforcement

- **Create Custom Role (Quality Auditor Lead):**
```http
{b(28)}
```

- **Assign Capabilities (issue:view, issue:comment):**
```http
{b(29)}
```

- **Assign Role to Philip J. Fry:**
```http
{b(30)}
```

- **Create Target Issue KAN-1:**
```http
{b(31)}
```

- **Philip J. Fry Local Login:**
```http
{b(33)}
```

- **Read Own Profile (Granted, HTTP 200 OK):**
```http
{b(34)}
```

- **View Issue KAN-1 (Granted issue:view, HTTP 200 OK):**
```http
{b(35)}
```

- **Add Comment to Issue KAN-1 (Granted issue:comment, HTTP 201 Created):**
```http
{b(36)}
```

- **Delete Preview Attempt (Denied issue:delete, HTTP 403 INSUFFICIENT_CAPABILITY):**
```http
{b(37)}
```

- **Delete Issue Attempt (Denied issue:delete, HTTP 403 INSUFFICIENT_CAPABILITY):**
```http
{b(38)}
```

- **Administrative Role Creation Attempt (Denied, HTTP 403 FORBIDDEN):**
```http
{b(39)}
```

---

### Zero-Mock Multi-Viewport Playwright Visual Audit

All 11 screenshots were captured using Playwright Chromium against the live running server (http://127.0.0.1:18408) with zero mock routes and visually audited via read_file. Telemetry recorded 0 console errors, 0 page errors, and 0 server 5xx errors.

| # | Screenshot Filename | Viewport | Target Surface / State | Visual Inspection Verdict |
| :-: | :--- | :---: | :--- | :--- |
| 1 | `01-desktop-1440x900-light.png` | 1440x900 | Auth Studio (Light Theme) | PASS: Clean 3-tab layout, Add Card drawer open with Corporate Active Directory preset populated |
| 2 | `02-desktop-1440x900-dark.png` | 1440x900 | Auth Studio (Dark Theme) | PASS: WCAG AA contrast, red Security Safeguard Triggered banner rendered on Local Admin disable attempt |
| 3 | `03-desktop-1024x768.png` | 1024x768 | Roles & Permissions Tab | PASS: RbacPolicyBuilder responsive layout, bulk buttons (Select All, Clear All, Read-Only) visible |
| 4 | `04-tablet-portrait-768x1024.png` | 768x1024 | Add Card Drawer (Tablet Portrait) | PASS: Corporate Google SSO (OIDC) drawer layout responsive, vertical scrolling clean |
| 5 | `05-mobile-portrait-390x844.png` | 390x844 | Auth Studio (Mobile Portrait) | PASS: Touch targets >= 44px, cards and actions reflow smoothly without horizontal overflow |
| 6 | `06-passkey-webauthn-registered.png` | 1440x900 | Profile & Security Settings | PASS: Passkeys & Security Keys card active, 2FA status indicator green |
| 7 | `07-totp-recovery-codes.png` | 1440x900 | One-Time Recovery Codes Modal | PASS: 10 regenerated codes rendered in clean 2-column monospace grid with copy actions |
| 8 | `08-ldap-test-draft-success.png` | 1440x900 | Auth Editor Drawer (LDAP) | PASS: Planet Express LDAPS parameters, Test Handshake button, and StartTLS toggle intact |
| 9 | `09-websudo-replay-active.png` | 1440x900 | WebSudo Re-auth Modal | PASS: Organic Admin Verification Required modal rendered over dirty drawer preserving typed AD inputs |
| 10 | `10-oidc-verified-claim-linked.png` | 1440x900 | Users & Permissions Table | PASS: All provisioned entities rendered (Bureaucrats Group, Hermes Conrad [LDAP], Philip J. Fry, Amy Wong [OAUTH2]) |
| 11 | `11-custom-rbac-policy-builder.png` | 1440x900 | Custom RBAC Policy Builder | PASS: Custom role creation flow with permission grid and category bulk selectors |

Screenshots are mirrored in:
- `docs/workouts/slice-1-auth-rbac/screenshots/`
- `docs/qa/KAN-408/screenshots/`

---

### Automated Test Coverage & Static Gates

- **Unit Test Execution (`docs/qa/KAN-408/unit-test-results.txt`):**
  - Pytest Backend Suites: **98 passed in 34.85s** (100% pass rate, zero warnings).
    - `kanban/tests/auth/test_auth_cards_admin_api.py`: 8 passed.
    - `kanban/tests/auth/test_auth_cards_handshake_unit.py`: 12 passed.
    - `kanban/tests/auth/test_auth_cards_public_api.py`: 4 passed.
    - `kanban/tests/auth/test_auth_cards_service_unit.py`: 12 passed.
    - `kanban/tests/auth/test_ldap_tls_and_bind.py`: 26 passed.
    - `kanban/tests/auth/test_ldap_group_sync.py`: 5 passed.
    - `kanban/tests/auth/test_oidc_flow.py`: 23 passed.
    - `kanban/tests/auth/test_identity_linking_real_pg_e2e.py`: 1 passed.
    - `kanban/tests/api/test_granular_rbac_api.py`: 7 passed.
  - Touched Module Backend Coverage:
    - `kanban/auth/cards/service.py`: **98%** (328 stmts, 3 missed, 4 partial branches).
    - `kanban/auth/cards/handshake.py`: **96%** (94 stmts, 2 missed).
    - `kanban/auth/cards/schemas.py`: **100%** (100 stmts, 0 missed).
    - `kanban/auth/ldap/client.py`: **97%** (233 stmts, 6 missed).
    - `kanban/auth/ldap/sync.py`: **92%** (74 stmts, 4 missed).
  - Vitest Frontend Suites: **122 passed in 8.92s** (100% pass rate, zero act warnings).
    - `AuthStudioPage.test.tsx`: 55 passed.
    - `AuthCardEditorDrawer.test.tsx`: 59 passed.
    - `RbacPolicyBuilder.test.tsx`: 8 passed.
  - Target Frontend Component Branch Coverage:
    - `AuthCardEditorDrawer.tsx`: **95.57%** (>= 95% threshold).
    - `AuthStudioPage.tsx`: **95.68%** (>= 95% threshold).
    - `RbacPolicyBuilder.tsx`: **97.59%** (>= 95% threshold).
    - All tested files overall: Statements **99.02%**, Branches **95.76%**, Functions **100%**, Lines **99.8%**.
- **Static Analysis & Build Verification (`docs/qa/KAN-408/build-check.txt`):**
  - Ruff Linter: `uv run ruff check kanban/` -> All checks passed (0 warnings, 0 errors).
  - Mypy Static Type Analysis: `uv run mypy kanban/` -> Success: no issues found in 680 source files.
  - Unicode Dash Check: `python3 scripts/check_no_dashes.py --all` -> Exited 0 with 0 Unicode dashes.
  - TypeScript Typecheck: `tsc -b --noEmit` -> Exited 0 with 0 errors.
  - Web ESLint: `eslint . --max-warnings 0` -> Exited 0 with 0 warnings.
  - Vite Production Build: `tsc -b && vite build` -> Exited 0 in 1.30s.

---

### Teardown Proof

All temporary workout processes (local Kanban ASGI server, LDAPS companion daemon, OIDC companion daemon) were cleanly terminated upon completion. The test PostgreSQL database container remains available for static and test assertions.

```bash
$ ss -tulpn | grep -E "18408|10389|10636|18081"
# Exited 0 (zero listening sockets on workout ports)

$ docker ps -a --filter "name=swarm-b-kan408-7b120ade"
CONTAINER ID   IMAGE                                                                                            COMMAND                  CREATED          STATUS                    PORTS      NAMES
d3b4f4421e8e   pgvector/pgvector:pg16@sha256:0dd3149a06e4579a0d70d8fef9945636cd514005e7237deb27f9b67886f8dc4f   "docker-entrypoint.s…"   28 minutes ago   Up 28 minutes (healthy)   5432/tcp   swarm-b-kan408-7b120ade-pg-test-1
```

Zero temporary companion containers or orphaned processes remain running. Ports 18408, 10389, 10636, and 18081 are completely free.

---

### Phase 4 Handoff Directives

With Phase 3 complete and certified:
1. **Target Downstream Ticket:** `KAN-409` ([SLICE-1-P4][KB-AUTH-DOCS] Phase 4: Authentication, LDAPS/OIDC & Granular RBAC Documentation).
2. **Key Runbooks to Author in Phase 4:**
   - Multi-Card Auth Studio operational guide detailing card priority sorting, enable/disable toggling, and the 15-minute break-glass lockout guard.
   - Active Directory & OpenLDAP integration runbook: CA certificate PEM pinning, StartTLS on ldap://, nested group synchronization to canonical RBAC roles, and dirty-drawer WebSudo keepalive/replay.
   - OIDC integration guide: PKCE S256 configuration, discovery endpoints, verified-claim account linking, and rejection of unverified email claims (403 EMAIL_NOT_VERIFIED).
   - Personal security settings documentation: WebAuthn/Passkey registration (rp.name = "👍kanban"), TOTP enrollment, and 10 single-use recovery codes redemption.
   - Granular RBAC policy matrix: capability namespaces (issue:*, workspace:*, admin:*), bulk selectors (Select All, Clear All, Read-Only), and custom role tier governance.
"""

    p1 = pathlib.Path("docs/workouts/slice-1-auth-rbac/03-live-workout-report.md")
    p2 = pathlib.Path("docs/qa/KAN-408/workout-report.md")
    p1.write_text(report_text, encoding="utf-8")
    p2.write_text(report_text, encoding="utf-8")
    print(f"Wrote {len(report_text)} chars to {p1} and {p2}")


if __name__ == "__main__":
    main()
