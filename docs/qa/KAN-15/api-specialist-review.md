# API Specialist Review: KAN-15 (KB-P3-AUDIT-09)

- Ticket: KAN-15
- Title: [KB-P3-AUDIT-09] Add (?) FieldHelpHint Popovers, 4-Flavor Decision Matrix, and 6-Preset Starter Gallery (CVSS, Total Project Issues, SLA) to Custom Fields Studio (3 Problems)
- Reviewer: api-spec-2 (Clean-Room Backend / API / Security Specialist)
- Date: 2026-11-20
- Target Directory: `/home/adamoutler/kanban/docs/qa/KAN-15`
- Branch: `main`
- Commit: `23ae056d9d6cf0f8614c82a6c04701b8ae536e18`
- Status: STATUS: APPROVED

---

## 1. Executive Summary

This clean-room API, Security, and Architecture audit inspects ticket KAN-15 on `main` (commit `23ae056d`), incorporating concrete evidence from zero-mock live full-stack verification (`docs/qa/KAN-15/live-fullstack-proof.txt`).

The ticket resolves three primary problems:
1. Providing an accessible `<FieldHelpHint />` popover component with strict timing contracts (180ms hover delay, 0ms keyboard focus, Escape focus restoration) and documented schema guidance across all output formats.
2. Integrating `<FieldHelpHint />` across Custom Fields Studio definition forms, format metadata editors, and Issue Detail Drawer (`CustomFieldsRailSection`).
3. Providing a 4-Flavor Decision Matrix and a 6-Preset Starter Gallery with syntactically and semantically valid executable configurations across Scalar, Safe Formula, WebAssembly, and Sandbox tiers.

During live-QA round 1 validation, formula presets failed execution because naive regex ternary conversion split dictionary literals (`{"level": ...}`) on colons, and runtime context lacked required attributes. The remediation in `fix/KAN-15-rc1` (now merged to `main` at `23ae056d`) resolved this via a bracket- and quote-aware recursive parser, expanded safe AST evaluation, enriched PostgreSQL runtime context (`days_until_due`, `blocker_count`, `sub_issue_count`, `completed_sub_issue_count`), and updated formula presets.

All API contracts, security invariants, AST parser boundaries, database context enrichment routines, and test coverage requirements are verified and approved:
- Formula AST Evaluator: Recursive ternary parsing and AST validation reject unsafe operations while cleanly evaluating dictionary literals, boolean operations, comparisons, and allowlisted math functions.
- PostgreSQL Context Enrichment: Real issue attributes, priority slug, state group, blocker links, and sub-issue progress are populated asynchronously without N+1 query overhead.
- Live Full-Stack Proof (R2): Executed against live unmocked container `kanban-liveqa-2` (`http://localhost:18952`) on `main` at commit `23ae056d`. All 3 formula presets saved via UI (`HTTP 201 Created`) and executed against KAN-1 with `HTTP 200 OK` (0 422 errors), rendering evaluated severity pills (`7.0 Due Soon`), badges (`Clear`), and numbers (`0 %`) in the Issue Drawer.
- Zero External Dependencies: Zero new runtime dependencies added (`Apache-2.0` compliant).
- Unidirectional Layering: Architecture satisfies `import-linter` contracts (`agent -> mcp -> kanban -> database`).
- Style & Quality: Zero compiler/linter warnings, zero console errors, zero CSP violations, and strict zero em-dashes and en-dashes.

---

## 2. Detailed Contract & Security Verification

### 2.1 Formula AST Parser and Safe Evaluator (`kanban/custom_fields/executor.py`)
- Source: `kanban/custom_fields/executor.py` (`_convert_js_ternary`, `_eval_safe_formula`)
- Verification:
  - `_convert_js_ternary` tracks nesting depth across braces (`{}`), brackets (`[]`), and parentheses (`()`), alongside quote status (`'` and `"`). Colons inside dictionary literals or strings are ignored during ternary condition/branch splitting.
  - Safe AST evaluation supports `ast.Constant`, `ast.Name`, `ast.Attribute`, `ast.Dict`, `ast.List`, `ast.Tuple`, `ast.BinOp`, `ast.UnaryOp`, `ast.BoolOp` (`And`, `Or`), `ast.Compare`, `ast.IfExp`, and allowlisted `ast.Call` (`round`, `int`, `float`, `min`, `max`, `len`, `abs`, `str`).
  - AST complexity bounds enforce `_MAX_FORMULA_NODES = 64` and `_MAX_FORMULA_DEPTH = 8` to prevent CPU exhaustion or algorithmic complexity attacks.
  - Dangerous operations (module imports, arbitrary builtins, filesystem/network access, attribute mutation) fail closed with `ProblemException(400)`.

### 2.2 PostgreSQL Runtime Issue Context (`build_issue_context`)
- Source: `kanban/custom_fields/executor.py` (`build_issue_context`)
- Verification:
  - Dynamically enriches runtime context from PostgreSQL:
    - `state`: `issue.state.name`
    - `state_group`: `issue.state.state_group`
    - `priority`: `issue.priority.slug.upper()`
    - `priority_slug`: `issue.priority.slug.lower()`
    - `priority_label`: `issue.priority.label`
    - `days_until_due`: `(issue.due_date - date.today()).days` (or `None`)
    - `blocker_count`: count of active `BLOCKED_BY` links where issue is source
    - `sub_issue_count`: count of child issues where `parent_issue_id == issue.id`
    - `completed_sub_issue_count`: count of child issues in `completed` state group
  - Non-ORM and mock objects fall back to safe default dictionaries.

### 2.3 Preset Formula Configurations (`kanban/web/src/features/custom-fields/presets.ts`)
- Verification:
  - `days-until-due-sla`:
    ```python
    {"level": "critical", "score": 9.5, "label": "SLA Breached"} if (
        issue.days_until_due < 0 or issue.priority == "URGENT"
    ) else (
        {"level": "high", "score": 7.0, "label": "Due Soon"}
        if (issue.days_until_due <= 2 or issue.priority == "HIGH")
        else {"level": "low", "score": 2.0, "label": "Within SLA"}
    )
    ```
    Produces valid JSON object for `output_format="severity_pill"`.
  - `blocker-count`:
    ```python
    "Blocked" if (issue.blocker_count > 0 or issue.state in ("BLOCKED", "CANCELLED")) else "Clear"
    ```
    Produces string matching `allowed_labels=["Blocked", "Clear"]` for `output_format="badge"`.
  - `sub-issue-completion`:
    ```python
    ((issue.completed_sub_issue_count * 100.0) / issue.sub_issue_count) if (
        issue.sub_issue_count > 0
    ) else (100.0 if issue.state in ("DONE", "Done") else 0.0)
    ```
    Produces float value formatted as percentage with `unit_suffix="%"`.

### 2.4 Live Full-Stack Proof Audit (`live-fullstack-proof.txt` - R2)
- Environment: Container `kanban-liveqa-2` (`http://localhost:18952`), commit `23ae056d`.
- Audit Results:
  - Accessible `<FieldHelpHint />`: Verified 180ms hover delay (trigger closed at 40ms, open at 260ms), 0ms open on keyboard focus, and immediate focus restoration to trigger upon pressing Escape. Popover renders dl list with all 7 output formats and footer link `/docs/custom-fields#format-metadata`.
  - Decision Matrix and Presets: Rendered 4 flavor cards and 6 preset cards. Verified 0 inline JSX style attributes (`count: 0`). Responsive across Tablet (768x1024) and Mobile (390x844, `scrollWidth: 390`). Dark theme verified.
  - Dirty Form & Undo: Dirty confirmation modal prompted and confirmed on unsaved input; undo strip successfully restored previous state.
  - PostgreSQL Persistence: Saved all 3 formula presets via `POST /api/v1/projects/KAN/custom-fields` -> HTTP 201 Created.
  - Formula Execution: Direct execution against KAN-1 (`POST /api/v1/issues/KAN-1/custom-fields/{id}/execute`) returned HTTP 200 OK:
    - `days-until-due-sla` -> `{"level": "high", "score": 7.0, "label": "Due Soon"}` (due tomorrow, priority High)
    - `blocker-count` -> `"Clear"`
    - `sub-issue-completion` -> `0.0`
  - Issue Drawer Rendering: Rendered `7.0 Due Soon` (severity pill), `Clear` (badge), and `0 %` (number). Zero 422 schema errors.

### 2.5 Test Suites and Coverage
- Backend Pytest Suite:
  - `kanban/tests/custom_fields/test_preset_formulas_e2e.py`: 5/5 passed against live PostgreSQL.
  - `kanban/tests/custom_fields/test_safe_formula_unit.py`: 6/6 passed.
  - Full suite: 61/61 tests passed with 96% statement coverage on `kanban/custom_fields/executor.py`.
- Frontend Vitest Suite:
  - 157/157 tests passed with 100% lines coverage across custom fields components.

---

## 3. Specialist Checklist

1. [x] Colons inside dictionary literals correctly parsed without corrupting ternary expressions
2. [x] `_convert_js_ternary` handles nested braces, brackets, parentheses, and string quotation
3. [x] Safe AST evaluator supports tuple, bool op, comparison, and allowlisted safe functions
4. [x] `build_issue_context` enriches runtime context with days_until_due, blocker_count, and sub_issue counts
5. [x] All 3 formula presets updated to valid Python syntax matching enriched context keys
6. [x] Real PostgreSQL E2E test `test_preset_formulas_e2e.py` passes all preset variations
7. [x] Live container verification confirms 201 Created on save and 200 OK on execute for all 3 presets
8. [x] Evaluated pills (`7.0 Due Soon`, `Clear`, `0 %`) render without 422 errors in Issue Detail Drawer
9. [x] `<FieldHelpHint />` verifies 180ms hover delay, 0ms focus open, and Escape key focus restoration
10. [x] 61/61 Pytest tests pass with 96% coverage on `executor.py`
11. [x] 157/157 Vitest tests pass with 100% lines coverage
12. [x] Static typecheck and linting clean (`tsc`, `eslint`, `mypy`, `ruff`, `lint-imports`)
13. [x] Zero em-dashes or en-dashes across all code and documentation

---

## 4. Verdict & Certification

STATUS: APPROVED

Ticket KAN-15 is verified and approved on `main` at commit `23ae056d`. The implementation provides robust formula evaluation, rich issue runtime context, accessible field guidance, and verified end-to-end execution on live containerized infrastructure. Ready for Clean-Room Reality-Checker QA.
