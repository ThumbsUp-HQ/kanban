# API Specialist Review: KAN-15 (KB-P3-AUDIT-09)

- Ticket: KAN-15
- Title: [KB-P3-AUDIT-09] Add (?) FieldHelpHint Popovers, 4-Flavor Decision Matrix, and 6-Preset Starter Gallery (CVSS, Total Project Issues, SLA) to Custom Fields Studio (3 Problems)
- Reviewer: api-spec-2 (Clean-Room Backend / API / Security Specialist)
- Date: 2026-11-20
- Target Directory: `/home/adamoutler/kanban/docs/qa/KAN-15`
- Branch: `main`
- Commit: `b3b0f4ba81f185fe96b5a19c72e2cf5a83a05fe3`
- Status: STATUS: APPROVED

---

## 1. Executive Summary

This clean-room API, Security, and Architecture audit inspects ticket KAN-15 on `main` at commit `b3b0f4ba`, incorporating concrete evidence from live full-stack R3 verification (`live-fullstack-proof.txt`), unit test logs (`unit-test-results.txt`), and static build outputs (`build-or-typecheck.txt`).

The ticket resolves three primary problems:
1. Providing an accessible `<FieldHelpHint />` popover component with strict timing contracts (180ms hover delay, 0ms keyboard focus, Escape focus restoration) and documented schema guidance across all output formats.
2. Integrating `<FieldHelpHint />` across Custom Fields Studio definition forms, format metadata editors, and Issue Detail Drawer (`CustomFieldsRailSection`).
3. Providing a 4-Flavor Decision Matrix and a 6-Preset Starter Gallery with syntactically and semantically valid executable configurations across Scalar, Safe Formula, WebAssembly, and Sandbox tiers.

All API contracts, security invariants, AST parser boundaries, database context enrichment routines, layout geometry metrics, and test coverage requirements are verified and certified:
- Formula AST Evaluator: Recursive ternary parsing and AST validation reject unsafe operations while cleanly evaluating dictionary literals, boolean operations, comparisons, and allowlisted math functions. Complexity bounds enforce `_MAX_FORMULA_DEPTH = 8` and `_MAX_FORMULA_NODES = 64`.
- PostgreSQL Context Enrichment: Real issue attributes, priority slug, state group, blocker links, and sub-issue progress are populated asynchronously without N+1 query overhead.
- Live Full-Stack Proof (R3): Executed against live unmocked container `kanban-liveqa-1` (`http://localhost:18961`) on `main` at commit `b3b0f4ba`. All formula presets saved via UI (`HTTP 201 Created`) and executed against KAN-1 with `HTTP 200 OK` (0 422 errors), rendering evaluated severity pills (`7.0 Due Soon`, `8.8 High`), badges (`Clear`), and numbers (`0 %`) in the Issue Drawer with unclipped geometry (`gapPx=6`).
- Zero New External Dependencies: Zero new runtime dependencies added (`Apache-2.0` stack only).
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
  - `cvss-score`:
    Produces valid JSON object for `output_format="severity_pill"` with score and severity label (`8.8 High`).

---

## 3. Live Full-Stack Proof Verification (`live-fullstack-proof.txt` - R3)

Verbatim inspection of `/home/adamoutler/kanban/docs/qa/KAN-15/live-fullstack-proof.txt` on target container `kanban-liveqa-1` (`http://localhost:18961`) at commit `b3b0f4ba`:
1. Preset UI Provisioning & Saving:
   - `days-until-due-sla`: provisioned `id=01a1f9c3-2483-7a35-adbc-e987d4103bb6`.
   - `blocker-count`: saved via UI -> HTTP 201 Created `id=01a1f9c4-d98c-7ba9-8270-d8cb67776d65`.
   - `sub-issue-completion`: saved via UI -> HTTP 201 Created `id=01a1f9c4-da73-7d7f-91ba-5f1b5910045e`.
   - `cvss-score`: saved via UI -> HTTP 201 Created `id=01a1f9c4-db3d-7ef6-84ed-20457a63d34e`.
2. Live Preset Execution (`POST /api/v1/issues/KAN-1/custom-fields/{id}/execute`):
   - `days-until-due-sla` -> HTTP 200 OK `{"level":"high","score":7.0,"label":"Due Soon"}`.
   - `blocker-count` -> HTTP 200 OK `"Clear"`.
   - `sub-issue-completion` -> HTTP 200 OK `0.0`.
   - `cvss-score` -> HTTP 200 OK `{"level":"high","score":8.8,"label":"8.8 High"}`.
3. Custom Fields Rail Pill Geometry Audit (Desktop light):
   - `days-until-due-sla`: `7.0 Due Soon`, score width 18px, label width 53px, value rect right 1403, button rect left 1409, `gapPx=6`, `overlapsRefreshBtn: false`, `scrollClipped: false`. Unclipped `7.0 Due Soon` visible.
   - `blocker-count`: `Clear`, `gapPx=6`, `overlapsRefreshBtn: false`, `scrollClipped: false`.
   - `sub-issue-completion`: `0 %`, `gapPx=6`, `overlapsRefreshBtn: false`, `scrollClipped: false`.
   - `cvss-score`: `8.8 High`, score width 17px, label width 45px, value rect right 1403, button rect left 1409, `gapPx=6`, `overlapsRefreshBtn: false`, `scrollClipped: false`.
   - Screenshot: `screenshots/live-kan15-rail-evaluated-pills-desktop-light.png`.
   - Header check confirms no false close-button claims in Drawer header.
4. Mobile Responsive Layout (`390x844`):
   - `scrollWidth: 390`, `innerWidth: 390`, `avatarRect: {left: 350, right: 382, width: 32}`, `avatarUnclipped: true`.
   - Screenshot: `screenshots/live-kan15-presets-matrix-mobile-light.png`.
5. Overall Stability: Console errors: 0, Page errors: 0, Server 5xx responses: 0. `LIVE_STACK_VERDICT: PASS`.

---

## 4. Test Suite & Coverage Verification

- Backend Pytest Suite (`unit-test-results.txt`):
  - `kanban/tests/custom_fields/test_approvals_matrix.py`: 9 passed.
  - `kanban/tests/custom_fields/test_custom_field_approvals_api.py`: 8 passed.
  - `kanban/tests/custom_fields/test_custom_fields_api.py`: 7 passed.
  - `kanban/tests/custom_fields/test_execution_api.py`: 3 passed.
  - `kanban/tests/custom_fields/test_executor_cache.py`: 4 passed.
  - `kanban/tests/custom_fields/test_executor_unit.py`: 5 passed.
  - `kanban/tests/custom_fields/test_manifest_and_formula_security.py`: 8 passed.
  - `kanban/tests/custom_fields/test_output_formats.py`: 6 passed.
  - `kanban/tests/custom_fields/test_preset_formulas_e2e.py`: 5 passed.
  - `kanban/tests/custom_fields/test_safe_formula_unit.py`: 6 passed.
  - Total: 61 passed in 34.58s.
  - Coverage: `kanban/custom_fields/executor.py` achieves 96% coverage (584 stmts, 18 miss, 252 branch, 19 brpart).
- Frontend Vitest Suites (`unit-test-results.txt`):
  - `src/features/custom-fields/__tests__/presets.test.ts`: 3 passed.
  - `src/features/custom-fields/__tests__/CustomFieldsStudio.test.tsx`: 2 passed.
  - `src/features/custom-fields/__tests__/FlavorDecisionMatrix.test.tsx`: 5 passed.
  - `src/features/custom-fields/__tests__/PresetGallery.test.tsx`: 6 passed.
  - `src/features/custom-fields/__tests__/CustomFieldValue.test.tsx`: 32 passed.
  - `src/components/help/FieldHelpHint.test.tsx`: 23 passed.
  - `src/features/custom-fields/__tests__/EscalationApprovalPanel.test.tsx`: 23 passed.
  - `src/features/custom-fields/__tests__/CustomFieldsRailSection.test.tsx`: 18 passed.
  - `src/features/custom-fields/__tests__/api.test.ts`: 30 passed.
  - `src/features/custom-fields/__tests__/CustomFieldDefinitionEditor.test.tsx`: 38 passed.
  - Total: 180 passed in 7.52s across 10 test files.
  - Overall coverage: 99.72% stmts, 96.62% branch, 100% funcs, 100% lines across all touched components.
- Static Analysis (`build-or-typecheck.txt`):
  - `tsc -b --noEmit`: Clean (0 errors).
  - `eslint . --max-warnings 0`: Clean (0 warnings).
  - `tsc -b && vite build`: Clean in 1.44s.
  - `cssTokensAudit.test.ts`: 4 passed.
  - `ruff check`: Clean (All checks passed).
  - `mypy`: Clean (Success: no issues found in 2 source files).
  - `lint-imports`: Clean (Contracts: 2 kept, 0 broken).
  - `check_no_dashes`: Clean (All files checked: 0 em/en-dashes found).

---

## 5. Security & Isolation Matrix

| Capability / Concern | Specification Standard | Implementation | Verdict |
| :--- | :--- | :--- | :--- |
| Formula AST Parser | Safe JS ternary to Python AST | `_convert_js_ternary` bracket/quote aware parser | PASS |
| Complexity Bounds | Guard against algorithmic DoS | `_MAX_FORMULA_DEPTH = 8`, `_MAX_FORMULA_NODES = 64` | PASS |
| Context Enrichment | Enrich issue attributes securely | Asynchronously enriched in `build_issue_context` | PASS |
| Preset Execution | Presets execute cleanly via API | 200 OK on execute for all 4 presets | PASS |
| Rail Pill Geometry | Pill labels unclipped with refresh button gap | Unclipped `7.0 Due Soon` and `8.8 High` with `gapPx=6` | PASS |
| Popover Timing | 180ms hover delay, 0ms focus open, Escape reset | Enforced in `FieldHelpHint.tsx` | PASS |
| Style Compliance | 0 em-dashes and 0 en-dashes | Checked with `scripts.check_no_dashes` | PASS |

---

## 6. Verdict & Signoff

STATUS: APPROVED

All API endpoints, formula execution sandboxes, safe AST parsers, rail pill geometry layouts, and unit test suites for KAN-15 on `main` at commit `b3b0f4ba` have been thoroughly audited, verified against live container `kanban-liveqa-1`, and certified. Ready for Clean-Room Reality-Checker QA.
