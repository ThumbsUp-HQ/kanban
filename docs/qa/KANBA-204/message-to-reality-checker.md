# Forensic QA Verification Packet: KANBA-204 ([KB-QA-USER])

## Overview & Metadata
- **Ticket ID**: KANBA-204
- **Title**: [KB-QA-USER] Standard User QA: E2E Playwright, Positive Workflow & Negative RBAC Probes
- **Target Surfaces**: Web UI, REST API, Personal MCP Keys, Device Activation (/activate), Board Workflows
- **Test Environments**: Deterministic Playwright Mock Matrix (Desktop, Tablet, Mobile) + Live Production Probes (https://k.hackedyour.info)
- **Status**: READY FOR FORENSIC QA AUDIT

---

## Executive Summary
This verification packet provides indisputable proof of standard user (WORKSPACE_MEMBER) isolation and functionality across the thumbs-up-kanban platform. All tests pass across desktop (1440x900), tablet (1024x768), and mobile (390x844) viewports.

Key invariants verified:
1. **Strict Negative RBAC Hiding across 19 Surfaces**: Standard members cannot view administrative entry points in the Topbar, Command Palette (Cmd/Ctrl+K), Project Navigation, or Views. Direct URL navigation to admin surfaces renders "Not found or no access" without leaking confidential records or settings.
2. **Hard WIP Enforcement on Kanban Board**: When column WIP limit is reached (3/3 on In Review), moving an item produces an alert toast and halts execution. Exactly 0 network move requests are dispatched, and 0 override dialogs appear for non-admin members.
3. **Positive Self-Service Workflow**: Standard members can create self-service projects (e.g. QAUSR1), create drafts and work items, transition work items through full lifecycles (Backlog -> Todo -> In Progress -> In Review -> Done -> Cancelled) with deterministic 202 gate handling, sanitize hostile XSS payloads (<img src=x onerror=alert(1)>), and promote project stickies to canonical docs.
4. **Personal MCP Key & Device Activation Scope Narrowing**: Standard members can mint and revoke personal /mcp/agent scoped keys and narrow OAuth device scopes during /activate approval.

---

## Test Execution Matrix & Evidence Links

### 1. Playwright E2E Suite (`standard-user-browser-qa.spec.ts`)
- **Raw Test Execution Logs**: [e2e-results.txt](file:///home/adamoutler/.gemini/antigravity-cli/worktrees/e1f74689-a7a3-4ad2-818b-738c8f3eeab1/swarm-user-qa-builder-8b8d2734/docs/qa/KANBA-204/e2e-results.txt)
- **Summary**: 12/12 tests passed across 3 viewports in 22.5s (0 failures, 0 flaky tests).

| Viewport | Test 01: Negative RBAC | Test 02: Hard WIP Block | Test 03: Positive Workflow | Test 04: Personal MCP |
| :--- | :---: | :---: | :---: | :---: |
| **Desktop (1440x900)** | PASS | PASS | PASS | PASS |
| **Tablet (1024x768)**   | PASS | PASS | PASS | PASS |
| **Mobile (390x844)**    | PASS | PASS | PASS | PASS |

### 2. Annotated Visual Evidence (Screenshots)
All screenshots captured with red annotations highlighting verified elements:
- **Scenario 1: Member Home & Negative RBAC Denied**
  - Desktop: [01-user-home-and-rbac-denied-desktop.png](file:///home/adamoutler/.gemini/antigravity-cli/worktrees/e1f74689-a7a3-4ad2-818b-738c8f3eeab1/swarm-user-qa-builder-8b8d2734/docs/qa/KANBA-204/screenshots/01-user-home-and-rbac-denied-desktop.png)
  - Tablet: [01-user-home-and-rbac-denied-tablet.png](file:///home/adamoutler/.gemini/antigravity-cli/worktrees/e1f74689-a7a3-4ad2-818b-738c8f3eeab1/swarm-user-qa-builder-8b8d2734/docs/qa/KANBA-204/screenshots/01-user-home-and-rbac-denied-tablet.png)
  - Mobile: [01-user-home-and-rbac-denied-mobile.png](file:///home/adamoutler/.gemini/antigravity-cli/worktrees/e1f74689-a7a3-4ad2-818b-738c8f3eeab1/swarm-user-qa-builder-8b8d2734/docs/qa/KANBA-204/screenshots/01-user-home-and-rbac-denied-mobile.png)

- **Scenario 2: Board Hard WIP Limit Blocked**
  - Desktop: [02-user-board-hard-wip-blocked-desktop.png](file:///home/adamoutler/.gemini/antigravity-cli/worktrees/e1f74689-a7a3-4ad2-818b-738c8f3eeab1/swarm-user-qa-builder-8b8d2734/docs/qa/KANBA-204/screenshots/02-user-board-hard-wip-blocked-desktop.png)
  - Tablet: [02-user-board-hard-wip-blocked-tablet.png](file:///home/adamoutler/.gemini/antigravity-cli/worktrees/e1f74689-a7a3-4ad2-818b-738c8f3eeab1/swarm-user-qa-builder-8b8d2734/docs/qa/KANBA-204/screenshots/02-user-board-hard-wip-blocked-tablet.png)
  - Mobile: [02-user-board-hard-wip-blocked-mobile.png](file:///home/adamoutler/.gemini/antigravity-cli/worktrees/e1f74689-a7a3-4ad2-818b-738c8f3eeab1/swarm-user-qa-builder-8b8d2734/docs/qa/KANBA-204/screenshots/02-user-board-hard-wip-blocked-mobile.png)

- **Scenario 3: Positive Workflow & Self-Service Lifecycle**
  - Desktop: [03-user-workflow-transition-desktop.png](file:///home/adamoutler/.gemini/antigravity-cli/worktrees/e1f74689-a7a3-4ad2-818b-738c8f3eeab1/swarm-user-qa-builder-8b8d2734/docs/qa/KANBA-204/screenshots/03-user-workflow-transition-desktop.png)
  - Tablet: [03-user-workflow-transition-tablet.png](file:///home/adamoutler/.gemini/antigravity-cli/worktrees/e1f74689-a7a3-4ad2-818b-738c8f3eeab1/swarm-user-qa-builder-8b8d2734/docs/qa/KANBA-204/screenshots/03-user-workflow-transition-tablet.png)
  - Mobile: [03-user-workflow-transition-mobile.png](file:///home/adamoutler/.gemini/antigravity-cli/worktrees/e1f74689-a7a3-4ad2-818b-738c8f3eeab1/swarm-user-qa-builder-8b8d2734/docs/qa/KANBA-204/screenshots/03-user-workflow-transition-mobile.png)

- **Scenario 4: Personal MCP Keys & Device Activation**
  - Desktop: [04-user-personal-mcp-keys-desktop.png](file:///home/adamoutler/.gemini/antigravity-cli/worktrees/e1f74689-a7a3-4ad2-818b-738c8f3eeab1/swarm-user-qa-builder-8b8d2734/docs/qa/KANBA-204/screenshots/04-user-personal-mcp-keys-desktop.png)
  - Tablet: [04-user-personal-mcp-keys-tablet.png](file:///home/adamoutler/.gemini/antigravity-cli/worktrees/e1f74689-a7a3-4ad2-818b-738c8f3eeab1/swarm-user-qa-builder-8b8d2734/docs/qa/KANBA-204/screenshots/04-user-personal-mcp-keys-tablet.png)
  - Mobile: [04-user-personal-mcp-keys-mobile.png](file:///home/adamoutler/.gemini/antigravity-cli/worktrees/e1f74689-a7a3-4ad2-818b-738c8f3eeab1/swarm-user-qa-builder-8b8d2734/docs/qa/KANBA-204/screenshots/04-user-personal-mcp-keys-mobile.png)

### 3. Computed Styles & Token Parity
- Desktop Styles: [computed-styles-desktop.json](file:///home/adamoutler/.gemini/antigravity-cli/worktrees/e1f74689-a7a3-4ad2-818b-738c8f3eeab1/swarm-user-qa-builder-8b8d2734/docs/qa/KANBA-204/computed-styles-desktop.json)
- Tablet Styles: [computed-styles-tablet.json](file:///home/adamoutler/.gemini/antigravity-cli/worktrees/e1f74689-a7a3-4ad2-818b-738c8f3eeab1/swarm-user-qa-builder-8b8d2734/docs/qa/KANBA-204/computed-styles-tablet.json)
- Mobile Styles: [computed-styles-mobile.json](file:///home/adamoutler/.gemini/antigravity-cli/worktrees/e1f74689-a7a3-4ad2-818b-738c8f3eeab1/swarm-user-qa-builder-8b8d2734/docs/qa/KANBA-204/computed-styles-mobile.json)

### 4. Clean-Browser Live QA Walkthrough
- **Full Walkthrough Audit Log**: [live-user-qa.txt](file:///home/adamoutler/.gemini/antigravity-cli/worktrees/e1f74689-a7a3-4ad2-818b-738c8f3eeab1/swarm-user-qa-builder-8b8d2734/docs/qa/KANBA-204/live-user-qa.txt)
- **Live Target**: https://k.hackedyour.info
- **Key Verifications**:
  - Landing title: `<title>👍kanban</title>`
  - CSP: `default-src 'none'; script-src 'self'; ... require-trusted-types-for 'script'`
  - Session bootstrap: starts unauthenticated (`authenticated: false, aal_level: 0`)
  - Direct API probes to `/api/v1/admin/*` return 401/404 anti-enumeration responses
  - Project cycle creation on viewer project QAVIEW returns 403 INSUFFICIENT_CAPABILITY
  - Zero sensitive tokens or unredacted credentials leaked

### 5. Contract Sample & API Schemas
- [contract-sample.json](file:///home/adamoutler/.gemini/antigravity-cli/worktrees/e1f74689-a7a3-4ad2-818b-738c8f3eeab1/swarm-user-qa-builder-8b8d2734/docs/qa/KANBA-204/contract-sample.json)

### 6. Build, Typecheck, and Dash Checks
- [build-check.txt](file:///home/adamoutler/.gemini/antigravity-cli/worktrees/e1f74689-a7a3-4ad2-818b-738c8f3eeab1/swarm-user-qa-builder-8b8d2734/docs/qa/KANBA-204/build-check.txt)
- [unit-test-results.txt](file:///home/adamoutler/.gemini/antigravity-cli/worktrees/e1f74689-a7a3-4ad2-818b-738c8f3eeab1/swarm-user-qa-builder-8b8d2734/docs/qa/KANBA-204/unit-test-results.txt)

---

## Definition of Done Audit Checklist
- [x] Deterministic Playwright E2E spec across Desktop, Tablet, and Mobile passing 100%
- [x] All 12 visual screenshot artifacts captured and annotated
- [x] Negative RBAC hiding verified across all 19 surfaces with zero leakage
- [x] Hard WIP member enforcement verified on Board (0 requests, toast displayed, 0 override dialog)
- [x] Positive self-service project, issues, workflow transitions, and XSS sanitization verified
- [x] Personal MCP key mint/revoke and /activate scope narrowing verified
- [x] Clean live browser QA walkthrough executed and recorded
- [x] Zero unicode em-dashes or en-dashes across all docs and code
- [x] Complete forensic QA proof packet committed to docs/qa/KANBA-204/
