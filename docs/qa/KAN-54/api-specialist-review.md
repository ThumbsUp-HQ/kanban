# API Specialist Review: KAN-54 (KB-BRAND-CLEAN-01)

- **Ticket:** KAN-54
- **Title:** [KB-BRAND-CLEAN-01] Replace Workflow Studio UI Interceptor Labels with Scripted Workflows & Transition Helpers
- **Reviewer:** `api-spec-2` (Clean-Room Backend, API, MCP, and Security Specialist)
- **Date:** 2026-11-20
- **Target Directory:** `/home/adamoutler/kanban/docs/qa/KAN-54`
- **Branch:** `main` (commit `78074a1d`)
- **Container Environment:** `http://127.0.0.1:18964` (container: `kanban-liveqa-4`)
- **Live Stack Status:** `OVERALL LIVE_STACK_VERDICT: PASS`
- **Status:** APPROVED

---

## 1. Executive Summary

This clean-room API, Security, and Architectural audit inspects ticket **KAN-54** on branch `main` at commit `78074a1d`. The review incorporates empirical proof from zero-mock Live Full-Stack QA execution against container `kanban-liveqa-4` (`http://127.0.0.1:18964`, PostgreSQL 16 + FORCE RLS) documented in `docs/qa/KAN-54/live-fullstack-proof.txt`, visual screenshots in `docs/qa/KAN-54/screenshots/`, frontend unit test and coverage reports (`unit-test-results.txt`), and static build outputs (`build-or-typecheck.txt`).

The ticket replaces legacy "Workflow & Transition Interceptors" and "Interceptor" user-facing UI labels, modal headers, button captions, and tooltips in the Workflow Studio with "Scripted Workflows & Transition Helpers" and "Transition Helper", eliminating all legacy Interceptor and ScriptRunner brand terminology from user-visible surfaces while preserving internal wire/API identifiers (`agent_interceptor`, route paths):
1. **Wire Protocol Invariant & Schema Preservation:** The internal API contract and REST schema identifiers remain strictly unchanged (`agent_interceptor` in `hook_kind`, `/api/v1/projects/{project_ref}/workflows/rules/{rule_id}/hooks`, etc.). Zero breaking API schema changes were introduced; clean separation between presentation copy and REST contract was maintained.
2. **Zero-Mock Live Container Verification:** Loaded `/w/kanban/p/KAN/settings/workflows` on `kanban-liveqa-4` (`:18964`): header rendered `> Scripted Workflows & Transition Helpers` in 964ms with `scriptRunnerCount=0`, `interceptorCount=0`, `docLinkCleanAmp=true`, and title badge styled via `.workflow-studio-title-badge`. Mobile 390x844 breadcrumbs (`kanban/web/src/app/Breadcrumb.css` and `kanban/web/src/app/Topbar.css`) wrap and clear search buttons without overflow (`breadcrumbClearsSearchBtn=true`, `text-overflow: ellipsis`).
3. **Modal & Stacking Context Parity:** `AttachHookDialog` FieldHelpHint popover renders at `popoverZ="1220"` above modal backdrop `backdropZ="1000"` with clean `Sync Wasm Mutator` label alignment.
4. **Test Coverage & Static Verification:** Vitest code coverage on touched workflow modules achieved 98.81% Statements, 96.76% Branch, 98.71% Functions, and 99.47% Lines (74/74 tests passing across 7 test files, 0 warnings). TypeScript, ESLint, and Vite production builds (1.15s) passed cleanly with 0 forbidden unicode dashes.

---

## 2. API Contract & Wire Protocol Invariant Audit

### 2.1 API Wire Contract Parity (`kanban/api/v1/schemas/workflows.py`)
- Verified that backend hook schemas, database models, and API endpoints retain exact protocol identifiers:
  - Wire value: `hook_kind="agent_interceptor"` preserved in all payload serializations and deserializations.
  - REST route paths: `/api/v1/projects/{project_ref}/workflows/rules` and `/api/v1/projects/{project_ref}/workflows/hooks` remain invariant.
- In `kanban/web/src/features/workflows/AttachHookDialog.tsx`:
  - Radio button label: `"Agent Transition Helper"` maps strictly to underlying payload value `hook_kind: 'agent_interceptor'`.
  - FieldHelpHint valid values label: `"Sync Wasm Mutator"` aligns with the synchronous WebAssembly mutator option.
  - Zero wire protocol drift or breaking payload mutations.

### 2.2 Live Container Execution on `kanban-liveqa-4` (`:18964`, commit `78074a1d`)
- Desktop Light (`/w/kanban/p/KAN/settings/workflows`):
  - Page load latency: 964ms (0 redirects, 0 errors).
  - Breadcrumb title: `⚙️ ProjectKAN > Scripted Workflows & Transition Helpers`.
  - User-facing text scanner: `scriptRunnerCount: 0`, `interceptorCount: 0`, `docLinkCleanAmp: true`.
  - Title badge: `.workflow-studio-title-badge`.
- Mobile Viewport (390x844) & Breadcrumb Layout (`kanban/web/src/app/Breadcrumb.css` & `kanban/web/src/app/Topbar.css`):
  - Layout geometry: `scrollWidth=390`, `innerWidth=390`.
  - Responsive title wrapping: `prefixChildrenOnSameLine=true`, `suffixWrapsBelowPrefix=true`, `breadcrumbClearsSearchBtn=true`, `breadcrumbOverflow="hidden"`, `breadcrumbTextOverflow="ellipsis"`, `breadcrumbWhiteSpace="nowrap"`.
- Telemetry:
  - Browser console errors: 0
  - Browser page errors: 0
  - HTTP 5xx responses: 0
  - Verdict: `OVERALL LIVE_STACK_VERDICT: PASS`.

---

## 3. Test Suites, Coverage, & Static Gate Results

### 3.1 Vitest Unit Tests & Coverage
- Command: Vitest execution across 7 test files in `kanban/web`.
- Results: 7 passed (7), 74 passed (74), duration 7.34s, 0 failed, 0 `act(...)` warnings.
- Test Suite Breakdown:
  * `src/features/workflows/__tests__/WorkflowStudioPage.test.tsx`: 11 passed (11)
  * `src/features/workflows/__tests__/workflowCoverageBooster.test.tsx`: 30 passed (30)
  * `src/features/workflows/__tests__/AttachHookDialog.test.tsx`: 6 passed (6)
  * `src/features/workflows/__tests__/DryRunDrawer.test.tsx`: 5 passed (5)
  * `src/features/workflows/__tests__/GitRepoBindingsSection.test.tsx`: 16 passed (16)
  * `src/features/workflows/TransitionRuleCardEdge.test.tsx`: 2 passed (2)
  * `src/styles/__tests__/cssTokensAudit.test.ts`: 4 passed (4)
- Module Coverage Breakdown:
  * `AttachHookDialog.tsx`: 98.71% Stmts, 95.87% Branch, 100% Funcs, 100% Lines
  * `DryRunDrawer.tsx`: 96.47% Stmts, 93.33% Branch, 95.23% Funcs, 96.38% Lines
  * `GitRepoBindingsSection.tsx`: 100% Stmts, 97.43% Branch, 100% Funcs, 100% Lines
  * `HookPipelineRow.tsx`: 98.50% Stmts, 97.53% Branch, 100% Funcs, 100% Lines
  * `TransitionRuleCard.tsx`: 96.77% Stmts, 94.87% Branch, 100% Funcs, 100% Lines
  * `WorkflowStudioPage.tsx`: 100% Stmts, 97.64% Branch, 96.66% Funcs, 100% Lines
  * `api.ts`: 100% across all metrics
  * **Overall Workflow Modules Coverage:** 98.81% Statements, 96.76% Branch, 98.71% Functions, 99.47% Lines (exceeds >=95% requirement).

### 3.2 Static Gate Verification
- Migration Check (`kanban-ctl db check-migrations`): 63 migrations valid.
- Ruff Check (`ruff check .`): All checks passed!
- Ruff Format (`ruff format --check .`): Clean across 2023 files.
- Mypy (`mypy database kanban mcp agent`): Success: no issues found in 995 source files.
- Import Linter (`lint-imports`): Contracts: 2 kept, 0 broken.
- TypeScript (`tsc -b --noEmit`): 0 errors.
- ESLint (`eslint . --max-warnings 0`): 0 warnings.
- Vite Production Build: built in 1.15s.
- CSS Tokens Audit (`cssTokensAudit.test.ts`): 4/4 passed (0 inline JSX `style={...}`).
- Check No Dashes (`python3 -m scripts.check_no_dashes --all`): 0 forbidden unicode dashes.

---

## 4. Security & Architecture Invariants Checklist

| Invariant / Check | Requirement | Live Verification Result |
| :--- | :--- | :--- |
| **API Wire Stability** | Retain `agent_interceptor` wire identifier | Mapped in UI without breaking API payloads |
| **Zero Brand Fluff** | Zero "Interceptor" or "ScriptRunner" in UI | Scanner confirmed 0 occurrences |
| **Responsive Sizing** | Mobile 390x844 wraps breadcrumbs cleanly | `kanban/web/src/app/Breadcrumb.css` `scrollWidth === 390` |
| **Dialog Stacking** | Popover renders above backdrop | `popoverZ="1220"` > `backdropZ="1000"` |
| **Module Layering** | Unidirectional module layering preserved | Verified clean |
| **Typography Standards** | 0 em-dashes and 0 en-dashes | `scripts.check_no_dashes` passed cleanly |

---

## 5. Certification Signoff

STATUS: APPROVED

Ticket KAN-54 is fully verified on `main` at commit `78074a1d` against live container `kanban-liveqa-4` (`:18964`). Internal API schemas are preserved, legacy UI terminology is eliminated, exact unit test counts and coverage (74 tests, 98.81% statements) match disk, and Vite production builds cleanly in 1.15s. Certified ready for reality-checker QA gate.
