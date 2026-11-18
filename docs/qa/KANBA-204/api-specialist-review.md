# QA API Specialist Review: KANBA-204

## Review Metadata
- **Ticket ID:** KANBA-204 ([KB-QA-USER] Standard User QA: E2E Playwright, Positive Workflow & Negative RBAC Probes)
- **Reviewer:** api-specialist (Independent API & Security Architecture Swarm Reviewer)
- **Review Date:** 2026-11-18
- **Target Surfaces:** Standard member (`WORKSPACE_MEMBER`) API interactions, positive workflow lifecycle, negative RBAC anti-enumeration probes, Hard WIP constraint enforcement, hostile input sanitization, and personal MCP key scoping
- **Status:** APPROVED

---

## 1. Executive Summary
This review independently audits the implementation and verification artifacts delivered under KANBA-204. The ticket validates standard user (`WORKSPACE_MEMBER`) workflows, privilege boundaries, and negative RBAC enforcement across 19 distinct UI surfaces and backing REST endpoints.

Verification comprises:
- An offline, deterministic Playwright test suite (`kanban/web/e2e/qa/standard-user-browser-qa.spec.ts`) evaluating desktop (1440x900), tablet (1024x768), and mobile (390x844) viewports (12 tests passing in 22.5s).
- Live browser walkthrough and anti-enumeration probe execution via `scripts/live_user_qa.py` against `https://k.hackedyour.info`.
- Rigorous security checks: positive self-service project creation, complete issue state lifecycle with 202 gate handling, hostile XSS escaping (`<img src=x onerror=alert(1)>`), Hard WIP column limit blocking, and personal MCP key lifecycle without administrative elevation.

All 12 Playwright tests pass cleanly, 2,183 unit tests across 178 test files pass with 0 errors, and static analysis checks (`ruff`, `mypy`, `check_no_dashes`) report zero violations.

---

## 2. API Contract & Security Architecture Audit

### 2.1 Positive Self-Service Lifecycle (Scenario 3)
- **Project Creation:** Standard members holding `CREATE_PROJECT` capability can create projects via `POST /api/v1/projects` (e.g. `QAUSR1`). The creator is automatically bound with project-level `ADMIN` capability (`is_project_admin: true`), allowing them to configure their own project without server or workspace elevation.
- **Issue Transitions & 202 Gate Handling:** Transitions across `Backlog -> Todo -> In Progress -> In Review -> Done -> Cancelled` execute reliably. Transitions triggering automated quality gates (such as `reality-checker-qa`) yield HTTP 202 `Accepted` with interceptor details, correctly handling pending transitions without state corruption.
- **Hostile Input Sanitization:** Submitting hostile payloads such as `<img src=x onerror=alert(1)>` within Markdown fields is safely sanitized and escaped into plain text by the backend renderer. Zero unescaped `<img>` tags or event handlers reach the DOM.
- **Stickies-to-Doc Promotion:** Promoting notes via `POST /api/v1/stickies/{sticky_id}/promote-to-doc` succeeds with provenance preserved.

### 2.2 Hard WIP Limit Enforcement on Board (Scenario 2)
- **WIP Constraint:** When an issue is moved into a column at capacity (e.g. `In Review` at 3/3), non-admin users without project `ADMIN` capability are blocked.
- **Network Invariant:** The client displays an alert toast and halts. Exactly 0 move requests are dispatched across the wire, and 0 override dialogs are presented to standard members.

### 2.3 Strict Negative RBAC & Anti-Enumeration (Scenario 1 & Live QA)
- **Surface Gating:** Standard members cannot access administrative controls. All administrative entry points in Topbar, Command Palette (`Cmd/Ctrl+K`), Project Navigation, and Views are omitted.
- **Anti-Enumeration Responses:**
  - Probes to `GET /api/v1/admin/auth/cards` return HTTP 404 `Not Found` anti-enumeration responses.
  - Probes to `GET /api/v1/admin/workspace-settings` and `/api/v1/admin/principals` return HTTP 401 `AUTHENTICATION_REQUIRED`.
  - Probes to `/api/v1/projects/QAADM/workflow-hooks` return HTTP 401.
  - Direct UI navigation to `/admin/auth`, `/admin/mcp`, `/workspaces/settings`, and `/projects/QAADM/settings` renders "Not found or no access" with zero administrative records or settings leaked.
- **Viewer-Only Project Mutation Denial:** Attempting to create cycles on restricted project `QAVIEW` returns HTTP 403 `INSUFFICIENT_CAPABILITY` (or CSRF rejection on unsigned probes).
- **Custom Field Script Redaction:** Custom field script source definitions are redacted from API responses for standard members.

### 2.4 Personal MCP Key Lifecycle & Device Activation (Scenario 4)
- **Scoped Minting:** Standard members can mint and revoke `/mcp/agent` keys via `POST /api/v1/auth/mcp-keys`. The UI and API disallow selecting `/mcp/admin` surfaces for non-admin principals.
- **Device Authorization:** During OAuth device activation (`/activate`), standard members can narrow scopes before approval.

---

## 3. Hostile Wire, Sanitization & Secret Scrubbing
- **Secret Redaction:** Verification logs (`live-user-qa.txt`, `contract-sample.json`, `git-diff.patch`) strictly scrub session tokens, cookies, and raw credentials (`[REDACTED_CSRF_TOKEN]`).
- **Formatting Compliance:** Zero em-dashes and en-dashes across all files.

---

## 4. Verification Proof Summary
- **Playwright E2E Suite:** 12 tests passed across desktop, tablet, and mobile in 22.5s.
- **Unit Test Suite:** 2,183 unit tests passed across 178 files.
- **Live QA Walkthrough:** Confirmed `<title>👍kanban</title>`, CSP headers, and anti-enumeration behavior on `https://k.hackedyour.info`.
- **Visual Evidence:** 12 responsive screenshots captured in `docs/qa/KANBA-204/screenshots/`.

---

## 5. Specialist Verdict
The standard user workflow implementation, negative RBAC hiding, WIP enforcement, and API isolation satisfy all security invariants. **APPROVED** without reservations.
