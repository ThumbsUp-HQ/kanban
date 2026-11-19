# Reality-Checker Forensic QA Report: KAN-10

## Executive Summary
- Ticket ID: KAN-10 ([KB-P3-AUDIT-04])
- Title: Fix Sparkle project key 422, Git Repo Mirror writable path 500, Custom Fields slug /v regex, and immediate Dual-Control banner
- Target Worktree: `/home/adamoutler/.gemini/antigravity-cli/worktrees/cec3609e-f993-4e05-b8c5-be0070e6116c/swarm-b-kan10-bc77d2a0`
- Target Branch: `feat/KAN-10`
- Reviewer: rc-gate-2 (Clean-Room Forensic QA Gate)
- Review Date: 2026-11-19
- Overall Quality Rating: A
- Production Readiness: READY

---

## Forensic Audit Verification Matrix

### Problem 1: Sparkle Human-Readable Project Key Resolution (`POST /api/v1/sparkle/complete`)
- Defect: When clients or integrations sent human-readable project keys (such as "KAN" or "KANBA"), Pydantic raised 422 Unprocessable Entity because `project_id` strictly expected a UUID. Furthermore, omitting `project_id` caused context derivation crashes.
- Verification:
  - Inspected `agent/sparkle/pipeline.py`: `SparkleRequest` schema updated to `project_id: UUID | str | None = None`.
  - Inspected `agent/sparkle/router.py`: In `verify_sparkle_access`, non-UUID strings are resolved through scoped database queries against `projects` filtered strictly by `principal.workspace_id`.
  - Inspected `kanban/api/v1/sparkle.py`: Unidirectional module layering (`agent -> mcp -> kanban -> database`) maintained via dynamic `__getattr__` adapter, passing strict import linter checks.
  - Inspected `kanban/tests/api/test_sparkle.py`: Verified tests asserting valid string key resolution (`test_sparkle_accepts_project_key_string`), direct UUID handling, derived project resolution from object context, and timing-equalized 404 responses for cross-tenant or non-existent keys.
  - Status: VERIFIED RESOLVED

### Problem 2: Git Mirror Binding Writable Runtime Directory
- Defect: Bare git repository mirrors defaulted strictly to `/var/lib/kanban/git-mirrors`. In unprivileged or non-root container environments (such as UID 65532 distroless), unwritable paths caused unhandled 500 Internal Server Errors.
- Verification:
  - Inspected `kanban/repos/mirror.py`: Implemented `is_dir_writable(path: Path) -> bool` and `resolve_mirror_base_dir()` evaluating candidates in order: caller override, `KANBAN_REPO_MIRROR_DIR`, `KB_DATA_DIR / "git-mirrors"`, standard `/var/lib/kanban/...` paths, and `<tempdir>/kanban-git-mirrors`.
  - Inspected `database/models/repo_binding.py`: Updated `ProjectRepoBinding.mirror_path` property to respect mirror directory precedence.
  - Inspected `kanban/api/v1/repo_bindings.py` and `MirrorManager`: Added resilient exception handling for `(RuntimeError, OSError, MirrorSizeLimitError, MirrorTimeoutError)`.
  - Inspected `kanban/tests/repos/test_mirror.py`: Verified tests covering directory writability checks, precedence resolution, and fallback behavior under permission failures.
  - Status: VERIFIED RESOLVED

### Problem 3: Custom Fields Slug HTML5 Pattern `/v` Regex Compatibility
- Defect: Under modern Chromium with ECMAScript 2024 unicodeSets (`/v` flag), unescaped hyphens in character classes trigger `SyntaxError: Invalid regular expression`. In addition, string literal JSX patterns caused double-backslash escapes in the DOM.
- Verification:
  - Inspected `kanban/web/src/features/custom-fields/CustomFieldDefinitionEditor.tsx`: Pattern attribute updated to JSX expression `pattern={'^[a-z0-9][a-z0-9\\-]{1,62}$'}`, rendering a clean single-escaped hyphen in the DOM.
  - Inspected `kanban/web/src/features/custom-fields/__tests__/CustomFieldDefinitionEditor.test.tsx`: Verified unit tests testing `new RegExp(pattern, 'v')` compilation and assertion against valid/invalid slug inputs.
  - Status: VERIFIED RESOLVED

### Problem 4: Immediate Dual-Control Explanation Banner on Scope Selection
- Defect: The dual-control explanation banner was previously only visible inside `<EscalationApprovalPanel />`, which only loaded after a custom field definition was saved and re-fetched from the API. Administrators selecting WORKSPACE or SERVER scope on new fields received no upfront feedback.
- Verification:
  - Inspected `kanban/web/src/features/custom-fields/CustomFieldDefinitionEditor.tsx`: Added immediate rendering of `data-testid="dual-control-explanation-banner"` when `targetScope === 'WORKSPACE' || targetScope === 'SERVER'`.
  - Inspected `kanban/web/src/features/custom-fields/EscalationApprovalPanel.tsx`: Added `suppressDualControlBanner` prop to eliminate redundant banners when editing existing approved fields.
  - Inspected Vitest tests and Playwright screenshots confirming immediate banner visibility on scope selection.
  - Status: VERIFIED RESOLVED

---

## Automated Test & Static Analysis Evidence

1. Unit & Integration Tests:
   - Python Pytest (Sparkle & Mirror): 16 passed in 2.54s.
   - Python Pytest (Repos & Mirror Full Suite): 65 passed in 11.69s.
     - `kanban/repos/mirror.py`: 95% coverage.
     - `kanban/api/v1/repo_bindings.py`: 94% coverage.
   - Web Vitest (Custom Fields Definition Editor & Escalation): 54 passed in 3.31s.
     - `CustomFieldDefinitionEditor.tsx`: 100% statements, 97.95% branch coverage.
     - `EscalationApprovalPanel.tsx`: 98.79% statements, 95.55% branch coverage.
   - Raw output logged in `docs/qa/KAN-10/unit-test-results.txt`.

2. Static Analysis & Type Checking:
   - Ruff check: clean (All checks passed).
   - Ruff format check: 11 files verified clean.
   - Mypy check: Success, no issues found in 11 source files.
   - Import Linter: 2 contracts kept, 0 broken (`agent -> mcp -> kanban -> database` preserved).
   - TypeScript compiler (`tsc -b --noEmit`): 0 errors.
   - ESLint: 0 warnings, 0 errors.
   - Strict ASCII character check: Zero `\u2014` em-dashes and zero `\u2013` en-dashes across all modified files.
   - Raw output logged in `docs/qa/KAN-10/build-or-typecheck.txt`.

---

## Dual Specialist Gate Audits

1. API Specialist Audit:
   - File: `docs/qa/KAN-10/api-specialist-review.md`
   - Reviewer: `api-spec-2`
   - Status: APPROVED
   - Findings: Verified tenant isolation in Sparkle key resolution, runtime directory resilience for bare mirrors, and admin AAL2 policy adherence.

2. UI/UX Specialist Audit:
   - File: `docs/qa/KAN-10/ui-specialist-review.md`
   - Reviewer: `ui-spec-2`
   - Status: APPROVED
   - Findings: Verified immediate rendering of dual-control banner, banner deduplication, modal layout and URL validation, and mobile responsive adaptations.

---

## Visual Proof Artifacts (12 Screenshots Audited)

1. `01-custom-fields-dual-control-workspace-light-desktop.png`: Custom Field Editor WORKSPACE scope immediate dual-control banner (Light, Desktop 1440x900).
2. `01-custom-fields-dual-control-workspace-dark-desktop.png`: Custom Field Editor WORKSPACE scope immediate dual-control banner (Dark, Desktop 1440x900).
3. `01-custom-fields-dual-control-workspace-light-mobile.png`: Custom Field Editor WORKSPACE scope immediate dual-control banner (Light, Mobile 390x844).
4. `01-custom-fields-dual-control-workspace-dark-mobile.png`: Custom Field Editor WORKSPACE scope immediate dual-control banner (Dark, Mobile 390x844).
5. `02-custom-fields-dual-control-server-light-desktop.png`: Custom Field Editor SERVER scope immediate dual-control banner (Light, Desktop 1440x900).
6. `02-custom-fields-dual-control-server-dark-desktop.png`: Custom Field Editor SERVER scope immediate dual-control banner (Dark, Desktop 1440x900).
7. `02-custom-fields-dual-control-server-light-mobile.png`: Custom Field Editor SERVER scope immediate dual-control banner (Light, Mobile 390x844).
8. `02-custom-fields-dual-control-server-dark-mobile.png`: Custom Field Editor SERVER scope immediate dual-control banner (Dark, Mobile 390x844).
9. `03-workflow-git-repo-binding-modal-light-desktop.png`: Workflow Studio Bind Git Repository modal (Light, Desktop 1440x900).
10. `03-workflow-git-repo-binding-modal-dark-desktop.png`: Workflow Studio Bind Git Repository modal (Dark, Desktop 1440x900).
11. `03-workflow-git-repo-binding-modal-light-mobile.png`: Workflow Studio Bind Git Repository modal (Light, Mobile 390x844).
12. `03-workflow-git-repo-binding-modal-dark-mobile.png`: Workflow Studio Bind Git Repository modal (Dark, Mobile 390x844).

All 12 visual screenshots confirm correct component rendering, accessible contrast, and zero layout overflow.

---

## Final Gate Certification
- Overall Quality Rating: A
- Production Readiness: READY
- Recommendation: Proceed to merge into `main` branch.
