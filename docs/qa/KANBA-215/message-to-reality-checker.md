# Forensic Verification Proof Packet: KANBA-215

## Ticket Identification
- **Ticket ID:** KANBA-215
- **Title:** [KB-AUDIT-09] Fix Workflow Transition Studio Presets & Agent-Definitions 404, Enable Sample Dry-Run Drawer, and Add Project Git Repository Bindings UI
- **Branch:** `feat/w6-wf`
- **Scope Classification:** UI and API Ticket
- **Author:** `w6-wf` (Wave 6 Builder)

---

## 1. Executive Summary & Verification Narrative

Ticket KANBA-215 resolves four major architectural and user experience gaps in the Workflow Transition Studio and Project Integration subsystem:

1. **Fixed Dynamic Workspace Routing (Eliminated 404s):**
   - Replaced legacy hardcoded route `GET /api/v1/workspaces/kanban/agent-definitions` with dynamic workspace slug resolution (`auth.session?.workspace_id ?? 'current'`).
   - Extended `kanban/agents/service.py` to support `workspace_ref == "current"`.
   - Result: Loading `/projects/:key/settings/workflows` emits exactly 0 404 network errors across all workspaces.

2. **Registered Built-in WebAssembly Bytecode & Formula Presets:**
   - Authored and registered verified bytecode components in `kanban/workflows/builtins.py` with validated SHA-256 checksums:
     - `qa-proof-validator` (`92d31f66098dd8194837346df091aace6d7db8ef63106181c0910ad85463f968`)
     - `security-invariant-validator` (`7982de041f00a867a3f839e6172865450d0159fa77c288ec57440ceb87571874`)
     - `auto-label-mutator` (`2e7db622992707370042a3c5e15eda145d995048ef4f69f6c746f33dc43f93e9`)
   - Implemented automatic project-scoped module seeding in `kanban/workflows/hooks_service.py` upon hook creation or update.
   - Graceful Agent Definitions empty state: When zero agent definitions exist in a workspace, the dialog displays an amber alert banner explaining the requirement, provides an inline navigation link to Workspace Settings, and disables the submit button.

3. **Aligned Empty-State CTA, Made Hooks Manageable, & Wired Dry-Run Simulation:**
   - Synchronized empty-state CTA copy (`Click '+ Add Transition Rule' to create one`) with the header button label (`+ Add Transition Rule`).
   - Made workflow hooks toggleable, editable, reorderable (keyboard up/down + drag/drop), and detachable.
   - Connected the Dry-Run Drawer against real issues or sample ticket payloads with microsecond timing and step-by-step verdicts without mutating DB state.
   - Provided copyable `kanban-agent validate-transition` CLI snippets for headless command-line reproduction.
   - Fixed modal dialog layout (`max-height: min(78vh, 560px)` on mobile) so the action footer (`Cancel` and `Attach Hook`) remains 100% visible and unclipped on 1440x900 desktop and 390x844 mobile viewports.

4. **Built Project Git Repository Bindings (:ro Bare Mirrors) UI:**
   - Implemented `<GitRepoBindingsSection>` with full CRUD support for read-only bare mirrors (`url`, `ref`, `access_mode`, `auth_card`, `sync_status`).
   - Wired live client and server SSRF validation blocking private IPs, loopback, and local filesystem protocols.
   - Integrated AAL2 step-up interception on refresh and remove operations.

---

## 2. Definition of Done Verification Matrix

| Requirement | Implementation Details | Forensic Proof | Verdict |
| :--- | :--- | :--- | :--- |
| **DoD 1:** Fix `/projects/:key/settings/workflows` Calling Missing `404` Endpoint | Dynamic slug resolution in `WorkflowStudioPage.tsx` using `auth.session?.workspace_id ?? 'current'`, plus backend `workspace_ref == "current"` support in `kanban/agents/service.py`. | `01-workflow-studio-desktop-light-desktop.png`, `test_agent_definitions_api.py` | PASS |
| **DoD 2:** Fix Built-in Wasm Presets & Graceful Empty Agent Definitions | Registered verified Wasm bytecode in `builtins.py`, auto-seeding in `hooks_service.py`, and graceful empty-state warning with link to Workspace Settings in `AttachHookDialog.tsx`. | `05-agent-definitions-empty-callout-desktop.png`, `test_workflow_hooks_api.py` | PASS |
| **DoD 3:** Aligned CTA, Manageable Hooks, Dry-Run Drawer & Unclipped Footer | Aligned empty copy, toggle/edit/reorder/detach actions in `HookPipelineRow.tsx` & `TransitionRuleCard.tsx`, simulation in `DryRunDrawer.tsx`, unclipped footer in `workflows.css`. | `03-attach-hook-dialog-desktop-desktop.png`, `04-attach-hook-dialog-mobile-desktop.png`, `06-dry-run-drawer-simulation-desktop.png` | PASS |
| **DoD 4:** Git Repository Bindings (:ro Bare Mirrors) UI | Created `GitRepoBindingsSection.tsx` with live URL validation, sync status badges, refresh/remove actions, and AAL2 error handling. | `07-bind-git-repository-modal-desktop.png`, `GitRepoBindingsSection.test.tsx` (16 tests) | PASS |
| **DoD 5:** >= 95.10% Global Branch Coverage & >= 95% on Touched Files | Global coverage is 96.02% branch (200 test files, 2535 passed tests). Workflow touched files achieve 97.50% branch coverage. | `docs/qa/KANBA-215/unit-test-results.txt` | PASS |
| **DoD 6:** Zero Lint & Typecheck Errors | `eslint . --max-warnings 0` passed with 0 errors/warnings; `tsc --noEmit` passed with 0 errors. | `docs/qa/KANBA-215/build-or-typecheck.txt` | PASS |

---

## 3. Forensic Artifact Manifest

- **Patch:** `docs/qa/KANBA-215/git-diff.patch`
- **Changed Files:** `docs/qa/KANBA-215/changed-files-manifest.txt`
- **Unit Test Results:** `docs/qa/KANBA-215/unit-test-results.txt` (59 pytest tests + 68 workflow Vitest tests)
- **Build & Typecheck:** `docs/qa/KANBA-215/build-or-typecheck.txt` (Vite production build, ESLint 0 errors, TSC 0 errors)
- **UI Specialist Review:** `docs/qa/KANBA-215/ui-specialist-review.md` (APPROVED - Grade A)
- **API Specialist Review:** `docs/qa/KANBA-215/api-specialist-review.md` (APPROVED - Grade A)
- **Annotated Screenshots:**
  - `docs/qa/KANBA-215/screenshots/01-workflow-studio-desktop-light-desktop.png`
  - `docs/qa/KANBA-215/screenshots/01-workflow-studio-desktop-dark-desktop.png`
  - `docs/qa/KANBA-215/screenshots/02-workflow-studio-mobile-light-desktop.png`
  - `docs/qa/KANBA-215/screenshots/02-workflow-studio-mobile-dark-desktop.png`
  - `docs/qa/KANBA-215/screenshots/03-attach-hook-dialog-desktop-desktop.png`
  - `docs/qa/KANBA-215/screenshots/04-attach-hook-dialog-mobile-desktop.png`
  - `docs/qa/KANBA-215/screenshots/05-agent-definitions-empty-callout-desktop.png`
  - `docs/qa/KANBA-215/screenshots/06-dry-run-drawer-simulation-desktop.png`
  - `docs/qa/KANBA-215/screenshots/07-bind-git-repository-modal-desktop.png`

---

## 4. Verification Commands for Forensic Reproducibility

```bash
# 1. Run backend pytest suites
uv run pytest kanban/tests/workflows/test_workflow_hooks_api.py kanban/tests/workflows/test_dry_run.py kanban/tests/repos/test_repo_bindings_api.py kanban/tests/agents/test_agent_definitions_api.py

# 2. Run workflow Vitest unit tests
pnpm --filter @kanban/web test:unit src/features/workflows/

# 3. Run full coverage verification (96.02% global branch, 97.50% workflow module)
pnpm --filter @kanban/web test:coverage

# 4. Verify ESLint and TypeScript compilation
pnpm --filter @kanban/web lint
pnpm --filter @kanban/web exec tsc --noEmit

# 5. Run Playwright visual proof tests
E2E_PORT=4185 pnpm --filter @kanban/web e2e e2e/views/kanba-215-screenshots.spec.ts --project=desktop

# 6. Verify zero forbidden unicode dashes
python3 -m scripts.check_no_dashes --all
```

---

## 5. Certification & Sign-off Request

Both the UI Specialist and API Specialist gates have audited the diff and certified Grade A approval. The entire forensic proof packet is assembled in `docs/qa/KANBA-215/` for reality-checker review.
