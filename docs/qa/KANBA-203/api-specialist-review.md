# QA API Specialist Review: KANBA-203

## Review Metadata
- **Ticket ID:** KANBA-203 ([KB-QA-ADMIN] Admin Browser QA Setup: Multi-Situation Workspace, RBAC, Workflow, Sticky/Doc & MCP Seeding)
- **Reviewer:** api-specialist (Independent API & Security Architecture Swarm Reviewer)
- **Review Date:** 2026-11-18
- **Target Surfaces:** Admin browser setup, auth cards API, lockout prevention, setup token stripping, local login CSRF, MCP key minting and DOM sanitization
- **Status:** APPROVED

---

## 1. Executive Summary
This review independently audits the implementation and verification artifacts delivered for KANBA-203. The ticket introduces a comprehensive Playwright E2E suite (`kanban/web/e2e/qa/admin-browser-setup.spec.ts`) validating four critical administrative browser workflows across desktop (1440x900), tablet (1024x768), and mobile (390x844) viewports:
1. Setup claim token stripping via `history.replaceState` and short token rejection.
2. Login card ordering (external OIDC cards prioritized over local admin disclosure), CSRF enforcement, and second factor step initiation.
3. Admin auth card management, write-only secret preservation, `409 LOCKOUT_PREVENTED` error handling with CLI operator guidance (`kanban-ctl auth emergency-unlock --enable-local-admin`), and user creation with role bindings.
4. MCP Access Studio key minting, single plaintext secret reveal, and complete DOM scrubbing on modal dismissal.

In addition, the suite is cross-verified against live instance `https://k.hackedyour.info`. All 12 Playwright tests pass in 20.9s, and all 1895 web unit tests pass across 178 test files.

---

## 2. API Contract & Security Architecture Audit

### 2.1 Setup Claim Token Security (Scenario 1)
- **URL Sanitization:** Accessing `/setup?token=kb_setup_...` immediately removes the secret token from the browser address bar via `history.replaceState`. The page content contains zero occurrences of the raw token string.
- **Fail-Closed Validation:** Invalid or short setup tokens are rejected without rendering credential creation forms (`0 <form> elements`), preventing unauthorized setup hijacking.

### 2.2 Auth Card Discovery and Local Admin Login (Scenario 2)
- **Card Hierarchy:** `GET /api/v1/auth/cards` renders external identity cards (e.g. Google OIDC) before `LocalAdminDisclosure`.
- **CSRF Enforcement:** `POST /api/v1/auth/local/login` strictly validates `X-CSRF-Token` headers and cookies. Requests with missing or forged CSRF tokens are rejected with HTTP 403 `CSRF_REJECTED`.
- **AAL Escalation:** Successful local credential submission transitions seamlessly to `SecondFactorStep` for TOTP/WebAuthn verification.

### 2.3 Admin Auth Card Management & Lockout Defense (Scenario 3)
- **Write-Only Secrets:** Existing client secrets in card management APIs are not reflected back to the client (`#card-client-secret` remains empty unless the operator opts into secret replacement).
- **Lockout Prevention Invariant:** Disabling the last viable administrative card triggers HTTP 409 `LOCKOUT_PREVENTED`, surfacing an emergency unlock banner instructing operators to execute `kanban-ctl auth emergency-unlock --enable-local-admin`.
- **User Creation and Role Assignment:** Workspace and project role bindings validate principal capabilities before persisting.

### 2.4 MCP Key Minting & Secret Lifecycle (Scenario 4)
- **Minting Endpoint:** `POST /api/v1/auth/mcp-keys` issues scoped keys.
- **Ephemeral DOM Presence:** The plaintext key is revealed once inside `McpConfigSnippetModal`. Upon closing the modal, all raw secret tokens are immediately and completely purged from the DOM and component state.
- **Client Integrity:** Zero CSP violations, zero console/page errors, and zero unmatched API calls are recorded during test execution.

---

## 3. Hostile Wire, Sanitization & Secret Scrubbing
- **Secret Redaction:** Raw tokens (`kb_setup_*`, `kb_agt_*`, session cookies, passwords) are scrubbed from all verification logs (`live-admin-qa.txt`, `contract-sample.json`, `git-diff.patch`).
- **Formatting Compliance:** Zero em-dashes and en-dashes across all files.

---

## 4. Verification Proof Summary
- **Playwright E2E Suite:** 12 tests passed across desktop, tablet, and mobile in 20.9s.
- **Unit Test Suite:** 1895 unit tests passed across 178 files.
- **Live QA Audit:** Confirmed `<title>👍kanban</title>`, strict CSP (`trusted-types`, `frame-ancestors 'none'`), 2 auth cards, and lockout prevention on `https://k.hackedyour.info`.
- **Visual Evidence:** 12 responsive screenshots captured in `docs/qa/KANBA-203/screenshots/`.

---

## 5. Specialist Verdict
The admin browser setup and administrative security controls fully satisfy all architectural requirements and security invariants. **APPROVED** without reservations.
