# Forensic QA Verification Packet: KAN-10

**Ticket Summary:** [KB-P3-AUDIT-04] Fix Sparkle project key 422, Git Repo Mirror writable path 500, Custom Fields slug /v regex, and immediate Dual-Control banner
**Branch:** feat/KAN-10
**Author:** b-kan10 (Security & Full-Stack Systems Engineer)

---

## 1. Executive Summary & Problems Resolved

This delivery resolves four scoped production edge cases identified in KB-P3-AUDIT-04 across backend FIM completion, bare git repository mirror storage, HTML5 /v regex parsing, and custom fields security governance UX:

### Problem 1: Accept Project Keys in POST /api/v1/sparkle/complete
- **Files Touched:** `agent/sparkle/pipeline.py`, `agent/sparkle/router.py`, `kanban/api/v1/sparkle.py`, `kanban/tests/api/test_sparkle.py`
- **Root Cause:** `SparkleRequest` strictly required `project_id: UUID | None`. When clients or integrations sent human-readable project keys (such as `"KAN"` or `"KANBA"`), Pydantic raised 422 Unprocessable Entity. Furthermore, when `project_id` was omitted, the handler could fail or crash context retrieval.
- **Remediation:**
  - Updated `SparkleRequest` schema to `project_id: UUID | str | None = None`.
  - In `verify_sparkle_access`, non-UUID strings are cleanly resolved to canonical project UUIDs via scoped workspace queries against the `projects` table (filtered by `principal.workspace_id`), with stored function fallback `resolve_project_id_by_key_or_id`.
  - When `req.project_id` is omitted but `req.object_id` is provided, the project is derived from the issue/doc context without throwing errors.
  - Unknown or cross-tenant project keys return timing-equalized 404 Not Found without leaking cross-tenant project existence.
  - Replaced static import in `kanban/api/v1/sparkle.py` with dynamic `__getattr__` adapter preserving the unidirectional layer boundary (`agent -> mcp -> kanban -> database`).

### Problem 2: Git Mirror Binding Writable Runtime Directory
- **Files Touched:** `kanban/repos/mirror.py`, `kanban/api/v1/repo_bindings.py`, `database/models/repo_binding.py`, `kanban/tests/repos/test_mirror.py`
- **Root Cause:** Bare git repository mirrors defaulted strictly to `/var/lib/kanban/git-mirrors`. In non-root or unprivileged container environments (such as UID 65532 distroless), `/var/lib/kanban` was unwritable or read-only, leading to unhandled 500 Internal Server Errors on binding creation or refresh.
- **Remediation:**
  - Implemented `is_dir_writable(path: Path) -> bool` runtime filesystem probe.
  - Implemented `resolve_mirror_base_dir()` evaluating candidates in order of precedence:
    1. Caller override Path.
    2. Explicit environment variables `KANBAN_REPO_MIRROR_DIR` or `KANBAN_GIT_MIRRORS_DIR`.
    3. `KB_DATA_DIR / "git-mirrors"` if defined and writable.
    4. Standard paths `/var/lib/kanban/data/git-mirrors` and `/var/lib/kanban/git-mirrors` if writable.
    5. Clean fallback to `<tempdir>/kanban-git-mirrors` ensuring unprivileged containers never crash with 500.
  - Updated `ProjectRepoBinding.mirror_path` property to respect mirror directory precedence.
  - Enhanced `MirrorManager.clone_or_fetch` and `repo_bindings` route handlers to catch `(RuntimeError, OSError, MirrorSizeLimitError, MirrorTimeoutError)` and gracefully recover using runtime writable directory.

### Problem 3: Custom Fields Slug HTML5 Pattern /v Regex Compatibility
- **Files Touched:** `kanban/web/src/features/custom-fields/CustomFieldDefinitionEditor.tsx`, `kanban/web/src/features/custom-fields/__tests__/CustomFieldDefinitionEditor.test.tsx`
- **Root Cause:** Under ECMAScript 2024 / HTML5 with the `/v` regex flag (unicodeSets), character classes treat unescaped hyphens `-` as reserved range syntax, causing browser syntax errors when compiling `new RegExp(pattern, 'v')`. Furthermore, in JSX string literal attributes, writing `pattern="...\\-..."` produced two literal backslashes in the DOM attribute, breaking both `/v` and `/u` regex parsing.
- **Remediation:**
  - Updated pattern attribute to JSX expression `pattern={'^[a-z0-9][a-z0-9\\-]{1,62}$'}` which renders exactly one backslash into the DOM attribute.
  - Added unit test asserting `expect(() => new RegExp(pattern, 'v')).not.toThrow()` and validating that `new RegExp(pattern, 'v')` matches valid slugs (`"cvss-score"`, `"a-1"`) and rejects invalid slugs (`"-invalid"`).

### Problem 4: Immediate Dual-Control Banner on Scope Selection
- **Files Touched:** `kanban/web/src/features/custom-fields/CustomFieldDefinitionEditor.tsx`, `kanban/web/src/features/custom-fields/EscalationApprovalPanel.tsx`
- **Root Cause:** `data-testid="dual-control-explanation-banner"` was previously only displayed inside `<EscalationApprovalPanel />`, which was conditionally rendered only after an existing field had already been saved and re-fetched from the API. Administrators selecting WORKSPACE or SERVER scope on a new or draft definition received no immediate feedback on dual-control requirements before saving.
- **Remediation:**
  - Added immediate rendering of `data-testid="dual-control-explanation-banner"` in `CustomFieldDefinitionEditor.tsx` whenever `targetScope === 'WORKSPACE' || targetScope === 'SERVER'`.
  - Added `suppressDualControlBanner` prop to `EscalationApprovalPanel.tsx` to prevent duplicate banners in the DOM when editing approved or pending fields.
  - Verified banner renders immediately upon dropdown selection in both unit tests and visual Playwright suites.

---

## 2. Changed Files Manifest

See `docs/qa/KAN-10/changed-files-manifest.txt`:
1. `agent/sparkle/pipeline.py`
2. `agent/sparkle/router.py`
3. `database/models/repo_binding.py`
4. `kanban/api/v1/repo_bindings.py`
5. `kanban/api/v1/sparkle.py`
6. `kanban/repos/mirror.py`
7. `kanban/tests/api/test_sparkle.py`
8. `kanban/tests/repos/test_mirror.py`
9. `kanban/web/src/features/custom-fields/CustomFieldDefinitionEditor.tsx`
10. `kanban/web/src/features/custom-fields/EscalationApprovalPanel.tsx`
11. `kanban/web/src/features/custom-fields/__tests__/CustomFieldDefinitionEditor.test.tsx`
12. `kanban/web/e2e/qa/kan-10-screenshots.spec.ts`

---

## 3. Verification & Test Proof

### 3.1 Python Linting, Formatting, and Layer Invariants
- `uv run ruff check`: All checks passed.
- `uv run ruff format --check`: 11 files verified.
- `uv run mypy`: Success: no issues found in 11 source files.
- `uv run lint-imports`: Analyzed 947 files, 3289 dependencies. Contracts: 2 kept, 0 broken (`agent -> mcp -> kanban -> database` strictly preserved).
- `python3 -m scripts.check_no_dashes --all`: Zero em-dashes or en-dashes detected.

### 3.2 Backend Unit Tests & Coverage
- `uv run pytest kanban/tests/api/test_sparkle.py kanban/tests/repos/test_mirror.py -v`: 16 passed in 2.54s.
- `uv run pytest kanban/tests/repos/ --cov=kanban.repos.mirror --cov=kanban.api.v1.repo_bindings`: 65 passed in 11.69s.
  - `kanban/repos/mirror.py`: 95% line and branch coverage.
  - `kanban/api/v1/repo_bindings.py`: 94% coverage.

### 3.3 Frontend Web Typecheck, Lint, and Vitest Coverage
- `pnpm --filter @kanban/web run typecheck` (`tsc -b --noEmit`): 0 errors.
- `pnpm --filter @kanban/web exec eslint src/features/custom-fields/`: 0 warnings, 0 errors.
- `vitest run --coverage src/features/custom-fields/__tests__/CustomFieldDefinitionEditor.test.tsx src/features/custom-fields/__tests__/EscalationApprovalPanel.test.tsx`:
  - 54 passed in 3.31s.
  - `CustomFieldDefinitionEditor.tsx`: 100% statements, 97.95% branch, 100% functions, 100% lines (exceeds >= 95.10% threshold).
  - `EscalationApprovalPanel.tsx`: 98.79% statements, 95.55% branch, 100% functions, 100% lines.

---

## 4. Visual Playwright Screenshots

All screenshots captured in `docs/qa/KAN-10/screenshots/`:
- `01-custom-fields-dual-control-workspace-light-desktop.png`: Custom Field Editor WORKSPACE scope immediate dual-control banner (Light, Desktop 1440x900).
- `01-custom-fields-dual-control-workspace-dark-desktop.png`: Custom Field Editor WORKSPACE scope immediate dual-control banner (Dark, Desktop 1440x900).
- `01-custom-fields-dual-control-workspace-light-mobile.png`: Custom Field Editor WORKSPACE scope immediate dual-control banner (Light, Mobile 390x844).
- `01-custom-fields-dual-control-workspace-dark-mobile.png`: Custom Field Editor WORKSPACE scope immediate dual-control banner (Dark, Mobile 390x844).
- `02-custom-fields-dual-control-server-light-desktop.png`: Custom Field Editor SERVER scope immediate dual-control banner (Light, Desktop 1440x900).
- `02-custom-fields-dual-control-server-dark-desktop.png`: Custom Field Editor SERVER scope immediate dual-control banner (Dark, Desktop 1440x900).
- `02-custom-fields-dual-control-server-light-mobile.png`: Custom Field Editor SERVER scope immediate dual-control banner (Light, Mobile 390x844).
- `02-custom-fields-dual-control-server-dark-mobile.png`: Custom Field Editor SERVER scope immediate dual-control banner (Dark, Mobile 390x844).
- `03-workflow-git-repo-binding-modal-light-desktop.png`: Workflow Studio Bind Git Repository modal (Light, Desktop 1440x900).
- `03-workflow-git-repo-binding-modal-dark-desktop.png`: Workflow Studio Bind Git Repository modal (Dark, Desktop 1440x900).
- `03-workflow-git-repo-binding-modal-light-mobile.png`: Workflow Studio Bind Git Repository modal (Light, Mobile 390x844).
- `03-workflow-git-repo-binding-modal-dark-mobile.png`: Workflow Studio Bind Git Repository modal (Dark, Mobile 390x844).

---

## 5. Artifact Directory Manifest

- `docs/qa/KAN-10/git-diff.patch`
- `docs/qa/KAN-10/changed-files-manifest.txt`
- `docs/qa/KAN-10/unit-test-results.txt`
- `docs/qa/KAN-10/build-or-typecheck.txt`
- `docs/qa/KAN-10/message-to-reality-checker.md`
- `docs/qa/KAN-10/screenshots/*.png` (12 screenshots)
