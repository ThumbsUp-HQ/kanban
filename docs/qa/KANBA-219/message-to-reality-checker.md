# Message to Reality-Checker: KANBA-219

## Overview and Executive Summary
- **Ticket ID:** KANBA-219
- **Title:** [KB-AUDIT-13] Implement Workspace AI Providers, Token Budgets, Autonomous Agent Definitions, and Remote mTLS Runners Admin Studio
- **Implementing Agent:** w6-ai (Wave 6 Builder)
- **Branch:** `feat/w6-ai`
- **Target Audience:** `reality-checker` (Forensic QA Gate)
- **Certification Request:** Grade-A READY Certification

---

## 1. Compliance Matrix Against Scoped Definition of Done

### Requirement 1: AI Providers and Token Caps Studio (`/admin/ai` or `/workspaces/settings/ai`)
- **CRUD and Provider Controls:** Full CRUD and enable/disable support implemented for `openai`, `gemini`, `ollama`, and `custom` providers in `AiStudioPage.tsx` and `AiProviderEditorDrawer.tsx`.
- **Write-Only Secret Custody:** Provider API keys are write-only. Existing keys are masked with `********` placeholder, preserved on partial updates, and can be cleared via an explicit checkbox.
- **Residency Tiers and Model Allowlists:** Residency metadata (`local`, `us-east`, `eu-central`, `default`) and comma-separated model allowlists are configured and displayed on provider cards.
- **Token Budget Ledger and Caps:** Monthly and daily workspace token caps and usage accounting are managed in `AiBudgetModal.tsx` with progress bar metrics tracking tokens used, tokens reserved, and burn rates.
- **Air-Gap Mode Guardrail:** When Air-Gap Mode is enabled, a high-contrast warning banner (>= 4.5:1 contrast in light and dark modes) is displayed, and client-side and server-side validation blocks saving or enabling cloud providers (`openai`, `gemini`).

### Requirement 2: Autonomous Agent Definitions Studio (`/admin/agents`)
- **Agent Registry and Harness Kinds:** Full management for `in_app_sdk`, `cli_pipe`, and `remote_runner` harnesses in `AgentStudioPage.tsx` and `AgentDefinitionEditorDrawer.tsx`.
- **CLI Policy and Banned Flags Enforcement:**
  - `agy` commands must strictly begin with `['-p']`.
  - `codex` commands must strictly begin with `['exec', '-s', 'read-only', '-']`.
  - Banned flags (`--yolo`, `--dangerously*`, `--full-auto`, `--elevated`, `--no-sandbox`) are rejected immediately with actionable error feedback.
- **Timeout and Tool Bounds:** Execution timeouts clamped between 1,000ms (1 second) and 300,000ms (5 minutes). Tool allowlist selection configured cleanly.
- **Live Test-Validation Echo Modal:** `AgentValidationModal.tsx` connects to `POST /api/v1/admin/agent-definitions/{id}:validate` executing the `kanban-agent validate-echo` test probe, displaying round-trip latency, exit code, and execution report output.
- **Strict Route Protection:** Nav items are hidden from non-admin users, and direct unauthorized navigation renders the standardized `NotFoundView` ("Not found or no access") with zero information leakage.

### Requirement 3: Remote mTLS Runners Studio (`/admin/agent-runners`)
- **Runner Inventory:** `RunnerStudioPage.tsx` lists active, offline, and revoked runner nodes with hostname, worker pool slug, status pill, last heartbeat timestamp, SHA-256 client certificate fingerprint, certificate expiration, and capability tags.
- **Single-Reveal Enrollment Tokens:** `MintEnrollmentTokenModal.tsx` generates single-use enrollment tokens with a strict 15-minute TTL. Tokens are displayed in a secure single-reveal view with 1-click copy feedback ("Copied!") and an explicit warning notice that tokens cannot be recovered after modal dismissal.
- **1-Click Immediate Revocation:** Runners can be revoked immediately via a protected confirmation dialog, invalidating active credentials and rejecting further connections.

---

## 2. Test Coverage and CI Validation Proof

- **Global Vitest Branch Coverage:**
  - Exceeds the mandatory `>= 95.10%` threshold (currently **96.04%**!).
  - 202 test files passed (100%).
  - 2,583 unit tests passed (100%).
- **Per-File Branch Coverage for All Touched Files (All >= 95%):**
  - `src/features/admin-ai/`: **96.95%**
    - `AiStudioPage.tsx`: 95.45%
    - `AiProviderEditorDrawer.tsx`: 97.97%
    - `AiBudgetModal.tsx`: 96.15%
    - `aiAdminApi.ts`: 100%
  - `src/features/admin-agents/`: **97.57%**
    - `AgentStudioPage.tsx`: 96.15%
    - `AgentDefinitionEditorDrawer.tsx`: 97.93%
    - `AgentValidationModal.tsx`: 95.45%
    - `cliPolicy.ts`: 100%
    - `agentDefinitionsApi.ts`: 100%
  - `src/features/admin-runners/`: **98.27%**
    - `RunnerStudioPage.tsx`: 97.36%
    - `MintEnrollmentTokenModal.tsx`: 100%
    - `runnersAdminApi.ts`: 100%
- **Static Analysis and Typecheck:**
  - TypeScript (`pnpm tsc -b`): 0 errors.
  - ESLint (`./node_modules/.bin/eslint`): 0 errors, 0 warnings.
  - Canonical CSS Tokens Audit (`cssTokensAudit.test.ts`): Passed (100% canonical tokens used).
- **Playwright Visual Proof Suite:**
  - 30 annotated screenshots captured across Desktop (1440x900), Tablet (1024x768), and Mobile (390x844) viewports in `docs/qa/KANBA-219/screenshots/`.
  - Verified with `read_file` for responsive fidelity, zero overflow clipping, and WCAG 2.1 AA compliance.

---

## 3. Forensic Artifact Index

All evidence files are located in `docs/qa/KANBA-219/`:
1. `git-diff.patch` (Full unified diff of all implementation and test files)
2. `changed-files-manifest.txt` (List of modified and added files with status)
3. `unit-test-results.txt` (Complete stdout from Vitest test runner)
4. `build-or-typecheck.txt` (Complete stdout from TypeScript check and Vite production build)
5. `ui-specialist-review.md` (Signed UI Designer and UX Architect review - Approved)
6. `api-specialist-review.md` (Signed Backend Architect and API Security Specialist review - Approved)
7. `screenshots/*.png` (30 visual proof captures across Light and Dark themes, Desktop, Tablet, and Mobile viewports)
8. `message-to-reality-checker.md` (This document)

---

## 4. Verification Instructions for Reality-Checker

All artifacts are fully preserved on disk for forensic inspection:
- Read `docs/qa/KANBA-219/ui-specialist-review.md` and `docs/qa/KANBA-219/api-specialist-review.md`.
- Read `docs/qa/KANBA-219/unit-test-results.txt` to verify all unit tests and coverage thresholds passed.
- Read `docs/qa/KANBA-219/build-or-typecheck.txt` to verify 0 typecheck and bundler errors.
- Inspect the 30 screenshot files in `docs/qa/KANBA-219/screenshots/`.
- Verify absence of forbidden unicode dashes via `python3 -m scripts.check_no_dashes --all`.
