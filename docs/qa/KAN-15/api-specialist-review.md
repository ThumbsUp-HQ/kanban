# API Specialist Review: KAN-15-rc1 (KB-P3-AUDIT-09)

- Ticket: KAN-15
- Title: [KB-P3-AUDIT-09] Add (?) FieldHelpHint Popovers, 4-Flavor Decision Matrix, and 6-Preset Starter Gallery (CVSS, Total Project Issues, SLA) to Custom Fields Studio (3 Problems)
- Reviewer: api-spec-2 (Clean-Room Backend / API / Security Specialist)
- Date: 2026-11-20
- Target Worktree: `/home/adamoutler/.gemini/antigravity-cli/worktrees/cec3609e-f993-4e05-b8c5-be0070e6116c/swarm-b-kan15-rc1-825368b6`
- Target Branch: `fix/KAN-15-rc1`
- Base Commit: `5998e9ab`
- Head Commit: `82f8683d`
- Status: STATUS: APPROVED

---

## 1. Executive Summary

This clean-room API, Security, and Architecture audit inspects ticket KAN-15 remediation on branch `fix/KAN-15-rc1` (commit `82f8683d`). The ticket resolves live-QA validation feedback where dictionary literals in formulas failed AST parsing due to naive regex ternary conversion, and runtime issue context lacked required attributes (`days_until_due`, `blocker_count`, `completed_sub_issue_count`, `sub_issue_count`).

All API contracts, security invariants, AST parser boundaries, database context enrichment routines, and test coverage requirements are verified and approved:
1. Robust Recursive Ternary Parser: Replaced naive regex in `kanban/custom_fields/executor.py` with bracket-, brace-, parenthesis-, and quote-aware recursive parser `_convert_js_ternary` and `_strip_outer_parens`. Colons inside dictionary literals (`{"level": ...}`) are cleanly skipped and no longer corrupt formula parsing into Python AST.
2. Safe AST Evaluator Expansion: `_eval_safe_formula` safely evaluates `ast.Tuple`, `ast.BoolOp` (`And`, `Or`), `ast.Compare` (`Eq`, `NotEq`, `Lt`, `LtE`, `Gt`, `GtE`, `Is`, `IsNot`, `In`, `NotIn` with safe fallbacks), and `ast.Call` on allowlisted safe functions (`round`, `int`, `float`, `min`, `max`, `len`, `abs`, `str`), while enforcing strict DoS limits (`_MAX_FORMULA_NODES = 64`, `_MAX_FORMULA_DEPTH = 12`).
3. Runtime Issue Context Enrichment (`build_issue_context`): Safely queries PostgreSQL for issue workflow state name, state group, project priority slug, start date, due date, calculated `days_until_due`, active blocker count (`LinkKind.BLOCKED_BY`), total sub-issues, and completed sub-issues.
4. Presets Aligned: Updated all 3 formula presets in `kanban/web/src/features/custom-fields/presets.ts` (`days-until-due-sla`, `blocker-count`, `sub-issue-completion`) to valid Python syntax referencing real runtime issue context keys and producing schema-compliant outputs (`severity_pill`, `badge`, `number`).
5. Real PostgreSQL Integration Test: `kanban/tests/custom_fields/test_preset_formulas_e2e.py` reads `presets.ts` directly from disk and verifies all formula presets across overdue, due soon, no due date, urgent priority, high priority, blockers > 0, blockers == 0, cancelled, and sub-issue variations with 200 OK computed responses and zero NoneType or 422 failures.
6. High Test Coverage: 61/61 backend Pytest tests pass with 96% coverage on `kanban/custom_fields/executor.py`. 157/157 frontend Vitest tests pass with 100% lines coverage across custom fields components.
7. Static Analysis & Code Style: Clean across `ruff check`, `mypy`, `lint-imports` (2 kept, 0 broken), and `check_no_dashes` (0 em/en-dashes).

---

## 2. Detailed Contract & Security Verification

### 2.1 Formula AST Parser & Safe Evaluator (`kanban/custom_fields/executor.py`)
- In `_convert_js_ternary`:
  - Tracks nesting depth for `{}` (braces), `[]` (brackets), and `()` (parentheses), and tracks quotation state (`'` and `"`).
  - Only processes `?` and `:` at top-level depth 0 outside quotes.
  - Recursively converts nested expressions into clean Python `(val_true) if (cond) else (val_false)` syntax.
- In `_eval_safe_formula`:
  - Enforces `_check_formula_ast_bounds(tree)`.
  - Safely evaluates AST nodes:
    - `ast.Constant`: scalars (int, float, str, bool, None).
    - `ast.Name`: looks up in `issue` dict context.
    - `ast.Attribute`: safely resolves nested attributes or methods.
    - `ast.Dict`: builds dictionary literals.
    - `ast.List` / `ast.Tuple`: builds collections.
    - `ast.BinOp` / `ast.UnaryOp`: arithmetic and logical negation.
    - `ast.BoolOp`: short-circuit `And` / `Or`.
    - `ast.Compare`: equality, inequality, order, and containment checks.
    - `ast.IfExp`: ternary conditional evaluation.
    - `ast.Call`: restricted strictly to `_SAFE_FORMULA_FUNCS` (`round`, `int`, `float`, `min`, `max`, `len`, `abs`, `str`).
  - All dangerous operations (builtins, imports, attribute mutation, file access, exec/eval) are strictly rejected with `ProblemException(400)`.

### 2.2 Runtime Issue Context Enrichment (`build_issue_context`)
- Asynchronously resolves related metadata from PostgreSQL:
  - `state`: WorkflowState.name
  - `state_group`: WorkflowState.state_group
  - `priority`: ProjectPriority.slug.upper()
  - `priority_slug`: ProjectPriority.slug.lower()
  - `priority_label`: ProjectPriority.label
  - `days_until_due`: `(issue.due_date - date.today()).days` (or `None`)
  - `blocker_count`: count of active `BLOCKED_BY` links where issue is source
  - `sub_issue_count`: count of child issues where `parent_issue_id == issue.id`
  - `completed_sub_issue_count`: count of child issues in `completed` state group
- Handles non-orm or mock contexts gracefully with safe defaults.

### 2.3 Formula Presets Verification (`presets.ts`)
- Days Until Due SLA:
  ```python
  {"level": "critical", "score": 9.5, "label": "SLA Breached"} if (issue.days_until_due < 0 or issue.priority == "URGENT") else ({"level": "high", "score": 7.0, "label": "Due Soon"} if (issue.days_until_due <= 2 or issue.priority == "HIGH") else {"level": "low", "score": 2.0, "label": "Within SLA"})
  ```
- Blocker Count Badge:
  ```python
  "Blocked" if (issue.blocker_count > 0 or issue.state in ("BLOCKED", "CANCELLED")) else "Clear"
  ```
- Sub-Issue Completion %:
  ```python
  ((issue.completed_sub_issue_count * 100.0) / issue.sub_issue_count) if (issue.sub_issue_count > 0) else (100.0 if issue.state in ("DONE", "Done") else 0.0)
  ```

### 2.4 Test Suite & Coverage Verification
- Real PostgreSQL E2E Suite: `kanban/tests/custom_fields/test_preset_formulas_e2e.py` PASSED (5/5).
- Safe Formula Unit Suite: `kanban/tests/custom_fields/test_safe_formula_unit.py` PASSED (6/6).
- Full Custom Fields Pytest Suite: 61/61 tests pass with 96% coverage on `kanban/custom_fields/executor.py`.
- Frontend Vitest Suite: 157/157 tests pass with 100% lines coverage across custom fields components.

### 2.5 Security, Boundary, and Code Style Compliance
- Dependency Invariant: Zero external packages added (`Apache-2.0` compliant).
- Boundary Invariant: `lint-imports` confirms strict unidirectional layering (`agent -> mcp -> kanban -> database`).
- Static Checks: `tsc -b --noEmit` (0 errors), `eslint . --max-warnings 0` (0 warnings), `mypy` (0 issues), `ruff check` (clean), `check_no_dashes` (0 em/en-dashes).

---

## 3. Specialist Checklist

1. [x] Colons inside dictionary literals correctly parsed without breaking ternary expressions
2. [x] `_convert_js_ternary` handles nested braces, brackets, parentheses, and quotes
3. [x] Safe AST evaluator supports tuple, bool op, comparison, and allowlisted math functions
4. [x] `build_issue_context` enriches runtime payload with days_until_due, blocker_count, and sub_issue counts
5. [x] All 3 formula presets updated to valid Python syntax matching enriched context keys
6. [x] Real PostgreSQL E2E test `test_preset_formulas_e2e.py` passes all preset variations
7. [x] 61/61 Pytest tests pass with 96% coverage on `executor.py`
8. [x] 157/157 Vitest tests pass with 100% lines coverage
9. [x] Static typecheck and linting clean (`tsc`, `eslint`, `mypy`, `ruff`, `lint-imports`)
10. [x] Zero em-dashes or en-dashes across all code and documentation

---

## 4. Verdict & Certification

STATUS: APPROVED

The KAN-15 RC1 remediation on branch `fix/KAN-15-rc1` (commit `82f8683d`) resolves the formula AST parser and runtime context mismatch, providing robust, fail-safe formula evaluation and full parity with frontend starter presets. Ready for dual specialist signoff and merge into `main`.
