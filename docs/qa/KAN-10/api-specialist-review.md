# API Specialist Security & Architecture Audit Review: KAN-10

## Audit Metadata
- Ticket ID: KAN-10 ([KB-P3-AUDIT-04])
- Reviewer: api-spec-2 (Clean-Room Backend/API Specialist)
- Date: 2026-11-19
- Target Worktree: `/home/adamoutler/.gemini/antigravity-cli/worktrees/cec3609e-f993-4e05-b8c5-be0070e6116c/swarm-b-kan10-bc77d2a0`
- Target Branch: feat/KAN-10
- Base Commit: 3dd6b9d
- Head Commit: b8259e0
- STATUS: APPROVED

---

## Executive Summary
This clean-room audit evaluates the backend API schema flexibility, runtime mirror storage resilience, architectural layering contracts, and custom field governance UX delivered for ticket KAN-10. The implementation resolves four critical production edge cases across FIM completion (Sparkle), bare git repository mirror storage in unprivileged container environments, HTML5 regex compilation under ECMAScript 2024 UnicodeSets (`/v` flag), and dual-control escalation feedback.

All changes adhere strictly to the authoritative specifications in `docs/ARCHITECTURE_AND_PRODUCT_SPEC.md` and `kanban/GEMINI.md`.

---

## Detailed Contract & Security Verification

### 1. Sparkle Human-Readable Project Key Resolution & Tenant Boundary Integrity
- Files: `agent/sparkle/pipeline.py`, `agent/sparkle/router.py`, `kanban/api/v1/sparkle.py`
- Invariant: Clients may provide human-readable project keys (such as `"KAN"` or `"KANBA"`). Resolution must never expose cross-tenant project existence or permit tenant boundary traversal.
- Audit Findings:
  - `SparkleRequest` now defines `project_id: UUID | str | None = None`.
  - Non-UUID strings are resolved through scoped database queries against `projects` filtered strictly by `principal.workspace_id` (with fallback to `resolve_project_id_by_key_or_id`).
  - Unknown, invalid, or cross-tenant project keys return timing-equalized 404 Not Found without leaking project metadata.
  - When `project_id` is omitted but `object_id` is present, the project is derived from the issue or document object context.
  - In `kanban/api/v1/sparkle.py`, dynamic `__getattr__` loading preserves strict unidirectional module boundaries (`agent -> mcp -> kanban -> database`), verified clean by `lint-imports`.

### 2. Git Mirror Binding Writable Runtime Directory
- Files: `kanban/repos/mirror.py`, `kanban/api/v1/repo_bindings.py`, `database/models/repo_binding.py`
- Invariant: Bare git repository mirroring must operate reliably across unprivileged container runtimes (such as UID 65532 distroless) without raising unhandled 500 errors on read-only system directories.
- Audit Findings:
  - Implemented `is_dir_writable(path: Path) -> bool` probe and `resolve_mirror_base_dir()` evaluating candidates in order: caller override, `KANBAN_REPO_MIRROR_DIR`, `KB_DATA_DIR / "git-mirrors"`, `/var/lib/kanban/data/git-mirrors`, `/var/lib/kanban/git-mirrors`, and `<tempdir>/kanban-git-mirrors`.
  - Updated `ProjectRepoBinding.mirror_path` property and `MirrorManager.clone_or_fetch` error handling, ensuring unprivileged container environments fall back to writable directories without crashing.

### 3. Custom Fields Slug HTML5 Pattern `/v` Regex Compatibility
- File: `kanban/web/src/features/custom-fields/CustomFieldDefinitionEditor.tsx` (line 434)
- Audit Findings:
  - Attribute rendered via JSX expression `pattern={'^[a-z0-9][a-z0-9\\-]{1,62}$'}` rendering a single escaped hyphen in DOM.
  - Verified compatible with `new RegExp(pattern, 'v')` under ECMAScript 2024 / Chromium unicodeSets mode without throwing `SyntaxError`.

### 4. Immediate Dual-Control Explanation Banner Rendering
- Files: `kanban/web/src/features/custom-fields/CustomFieldDefinitionEditor.tsx`, `kanban/web/src/features/custom-fields/EscalationApprovalPanel.tsx`
- Audit Findings:
  - `data-testid="dual-control-explanation-banner"` renders immediately upon selecting WORKSPACE or SERVER scope, informing administrators before first save.
  - `suppressDualControlBanner` prop prevents redundant banners when editing existing approved fields.

---

## Gate & Invariant Checklist

1. [x] Zero New Dependencies: No additions to `pyproject.toml` or `package.json`.
2. [x] Admin Route Security: All `/api/v1/admin/*` routes maintain mandatory `Depends(require_admin_aal2)`. Verified by `kanban/tests/auth/test_aal2_policy.py`.
3. [x] Architectural Layering: `uv run lint-imports` verified 2 kept contracts, 0 broken (`agent -> mcp -> kanban -> database`).
4. [x] Test Coverage:
   - Backend: 19 unit and integration tests passing (`test_sparkle.py`, `test_mirror.py`, `test_aal2_policy.py`). `kanban/repos/mirror.py` achieved 95% coverage.
   - Frontend: `CustomFieldDefinitionEditor.tsx` achieved 100% statement and 97.95% branch coverage; `EscalationApprovalPanel.tsx` achieved 98.79% statement and 95.55% branch coverage (54 vitest tests passing).
5. [x] Static Analysis: `ruff check`, `ruff format --check`, `mypy` (1082 source files), `tsc -b --noEmit`, and `eslint` pass with 0 errors and 0 warnings.
6. [x] Zero Em/En-Dashes: Clean verification across code, tests, docs, and review markdown (0 em/en-dashes).
7. [x] Evidence Packet Complete: `git-diff.patch`, `changed-files-manifest.txt`, `unit-test-results.txt`, `build-or-typecheck.txt`, `message-to-reality-checker.md`, and 12 Playwright screenshot PNGs verified in `docs/qa/KAN-10/`.

---

## Verdict & Handoff
STATUS: APPROVED

The API contracts, security invariants, and test evidence are verified clean. Handoff to `@ui-spec-2` for visual, UX, and accessibility verification of `docs/qa/KAN-10/screenshots/`.
