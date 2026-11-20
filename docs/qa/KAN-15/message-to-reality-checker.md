# Reality-Checker Verification Packet: KAN-15

**Ticket ID:** KAN-15  
**Title:** [KB-P3-AUDIT-09] Add (?) FieldHelpHint Popovers, 4-Flavor Decision Matrix, and 6-Preset Starter Gallery (CVSS, Total Project Issues, SLA) to Custom Fields Studio (3 Problems)  
**Branch:** `fix/KAN-15-rc2`  

---

## 1. Executive Summary & Verification Proof

All 3 scoped problems for ticket KAN-15 have been fully implemented, verified with automated test suites, checked against strict static gates, and documented without em-dashes or en-dashes.

### Problem 1: Accessible `<FieldHelpHint />` Component
- Created `kanban/web/src/components/help/FieldHelpHint.tsx` and `kanban/web/src/components/help/FieldHelpHint.css`.
- Reused existing infrastructure: `HintPortal`, `positionHint`, and `hintTiming.ts`.
- Interaction timing:
  * 180ms hover open delay
  * 0ms keyboard Tab focus open delay
  * 120ms hover-bridge grace period so pointer can move into popover without premature close
  * Escape key closes popover and immediately returns focus to trigger button
  * 44x44px touch hit target for coarse pointers via `@media (pointer: coarse)` and CSS pseudo-element hit-area expansion
- Layout & Content:
  * Header with bold Title (`.field-help-hint-title`)
  * Plain-English Summary paragraph
  * Optional `<dl>` definition list for Valid Config Values
  * Optional Example block with code formatting
  * Optional Caution block with warning callout
  * Footer with accessible link (`More info ->`) supporting configurable `docHref` prop
- Security & CSP:
  * Strict `style-src 'self'` compliance with zero inline `style={...}` props in JSX.
  * Popover coordinates and arrow offsets are applied via CSS custom properties on the DOM element (`style.setProperty`).
  * 100% canonical CSS design tokens verified via `cssTokensAudit.test.ts`.

### Problem 2: Attached `<FieldHelpHint />` Across Custom Fields Studio & Issue Rail
- Attached `<FieldHelpHint />` to every field in `CustomFieldDefinitionEditor.tsx`:
  * Display Name (`hint-field-name`)
  * Identifier Slug (`hint-field-slug`)
  * Field Flavor (`hint-field-flavor`)
  * Output Format (`hint-output-format`)
  * Format Metadata JSON (`hint-format-metadata`)
  * Sandbox Execution Tier (`hint-execution-tier`)
  * Target Scope (`hint-target-scope`)
  * Credential Mode (`hint-credential-mode`)
  * Egress Allowlist (`hint-egress-allowlist`)
  * Script / Formula Source (`hint-script-source`)
- Attached `<FieldHelpHint />` to every field in `EscalationApprovalPanel.tsx`:
  * Target Scope (`hint-escalation-target-scope`)
  * Credential Mode (`hint-escalation-credential-mode`)
  * Business Justification (`hint-escalation-justification`)
  * AAL2 Step-Up Verification (`hint-escalation-aal2`)
- Attached `<FieldHelpHint />` to custom field rows in `CustomFieldsRailSection.tsx` (`rail-field-hint-${def.slug}`).

### Problem 3: 4-Flavor Decision Matrix & 6-Preset Starter Gallery
- Created `FlavorDecisionMatrix.tsx`:
  * Interactive comparison of 4 field flavors:
    1. Scalar (<1ms static constant/badge)
    2. Formula (<5ms single-issue AST math on `issue.*`, with `_MAX_FORMULA_NODES = 64` and `_MAX_FORMULA_DEPTH = 8`)
    3. WebAssembly (<25ms compiled deterministic scoring like CVSS)
    4. Project Rollup / nsjail (<=3,000ms cross-issue aggregation via `/api/v1/` egress proxy or external PR metadata)
  * Latency pill indicators with semantic performance metrics.
  * Direct selection buttons allowing users to choose a flavor and automatically update the form template.
- Created `PresetGallery.tsx` and `presets.ts`:
  * 6 one-click starter presets with valid configurations matching backend models:
    1. CVSS 3.1/4.0 Score (`wasm` -> `severity_pill`)
    2. Total Issues in Project (`nsjail` -> `number`)
    3. Days Until Due / SLA Breach (`formula` -> `severity_pill`)
    4. Blocker Count (`formula` -> `badge`)
    5. Sub-Issue Completion % (`formula` -> `number`)
    6. Git PR Link Badge (`nsjail` -> `url`)
  * Filter pills to filter presets by flavor (`all`, `formula`, `wasm`, `nsjail`).
  * Non-destructive confirmation modal before loading a preset when the editor form has unsaved edits.
  * Undo strip (`preset-undo-strip`) allowing instant one-click revert back to the exact previous form state.

---

## 2. Test Suite & Coverage Evidence

Commands executed (recorded in unified `docs/qa/KAN-15/unit-test-results.txt`):
```bash
# Backend Pytest
KB_TEST_PGHOST=/tmp/kb-pgsock-kan15 KB_TEST_PGSOCKET_DIR=/tmp/kb-pgsock-kan15 \
  uv run pytest kanban/tests/custom_fields/ --cov=kanban.custom_fields.executor --cov-report=term-missing

# Frontend Vitest
COVERAGE_INCLUDE="src/features/custom-fields/**,src/components/help/**" \
  pnpm --dir kanban/web run test:coverage src/features/custom-fields/ src/components/help/FieldHelpHint.test.tsx
```

Results:
- **Backend Pytest:** 61 passed in 34.58s (100% pass)
- **Frontend Vitest:** 10 test files, 180 passed in 7.52s (100% pass, 0 stderr `act(...)` warnings)
- **Overall Coverage:** `>=95%` on all touched files

### Coverage Table (Frontend V8):
| File | % Stmts | % Branch | % Funcs | % Lines |
| :--- | :---: | :---: | :---: | :---: |
| **All files** | **99.72%** | **96.62%** | **100.00%** | **100.00%** |
| `components/help/FieldHelpHint.tsx` | 100.00% | 95.45% | 100.00% | 100.00% |
| `features/custom-fields/CustomFieldDefinitionEditor.tsx` | 100.00% | 95.31% | 100.00% | 100.00% |
| `features/custom-fields/CustomFieldsRailSection.tsx` | 100.00% | 98.30% | 100.00% | 100.00% |
| `features/custom-fields/EscalationApprovalPanel.tsx` | 98.79% | 95.55% | 100.00% | 100.00% |
| `features/custom-fields/FlavorDecisionMatrix.tsx` | 100.00% | 100.00% | 100.00% | 100.00% |
| `features/custom-fields/PresetGallery.tsx` | 100.00% | 95.23% | 100.00% | 100.00% |
| `features/custom-fields/presets.ts` | 100.00% | 100.00% | 100.00% | 100.00% |
| `features/custom-fields/CustomFieldValue.tsx` | 99.14% | 98.16% | 100.00% | 100.00% |
| `features/custom-fields/CustomFieldsStudio.tsx` | 100.00% | 100.00% | 100.00% | 100.00% |
| `features/custom-fields/api.ts` | 100.00% | 97.91% | 100.00% | 100.00% |

### Coverage Table (Backend Pytest):
| File | Stmts | Miss | Branch | BrPart | Cover |
| :--- | :---: | :---: | :---: | :---: | :---: |
| `kanban/custom_fields/executor.py` | 584 | 18 | 252 | 19 | 96% |

Every file strictly satisfies the `>=95%` project gate.

---

## 3. Static Verification Gates

All static validation commands pass with exit code 0 (recorded in `docs/qa/KAN-15/build-or-typecheck.txt`):
1. `tsc -b --noEmit`: 0 TypeScript compiler errors.
2. `eslint . --max-warnings 0`: 0 lint errors, 0 lint warnings across the entire repository.
3. `pnpm --dir kanban/web run build`: Production build passes in 1.44s.
4. `pnpm --dir kanban/web run test:unit src/styles/__tests__/cssTokensAudit.test.ts`: 4 passed (4 total), 100% canonical tokens.
5. `uv run ruff check kanban/custom_fields/ kanban/tests/custom_fields/`: All checks passed.
6. `uv run mypy kanban/custom_fields/executor.py kanban/tests/custom_fields/test_preset_formulas_e2e.py`: Success (0 issues in 2 source files).
7. `uv run lint-imports`: Contracts: 2 kept, 0 broken.
8. `python3 -m scripts.check_no_dashes`: Clean, 0 em-dashes and 0 en-dashes found.
9. Strict CSP: 0 inline `style={...}` JSX attributes across all new/modified components.

---

## 4. Verification Files in `docs/qa/KAN-15/`

- `unit-test-results.txt`: Verbatim output of unified Pytest (61 passed) + Vitest (180 passed, 0 stderr warnings) with full coverage metrics.
- `build-or-typecheck.txt`: Verbatim output of tsc, eslint, vite build, cssTokensAudit, ruff, mypy, lint-imports, and check_no_dashes.
- `changed-files-manifest.txt`: List of all changed and created files.
- `git-diff.patch`: Scoped git diff of the 18 implementation and test files against base.
- `message-to-reality-checker.md`: This forensic verification packet.
- `api-specialist-review.md`: Clean-room API and Security specialist review.
- `ui-specialist-review.md`: Clean-room UI and UX specialist review.
- `live-fullstack-proof.txt`: Raw zero-mock full-stack verification log.

---

## 5. Zero-Mock Live Full-Stack Verification (`kanban-liveqa-2`, commit `23ae056d`, R2)

**Target:** `http://localhost:18952` (`standalone_embedded_pg` with PostgreSQL 16 `FORCE ROW LEVEL SECURITY`, UID 65532 `uvicorn`)  
**Raw Proof Log:** `docs/qa/KAN-15/live-fullstack-proof.txt`  
**Screenshots (`docs/qa/KAN-15/screenshots/`):**
- `live-kan15-presets-matrix-desktop-light.png` (`1440x900` light, 4-Flavor Matrix)
- `live-kan15-presets-matrix-desktop-dark.png` (`1440x900` dark, 4-Flavor Matrix)
- `live-kan15-presets-matrix-tablet-light.png` (`768x1024` tablet light, 4-Flavor Matrix)
- `live-kan15-presets-matrix-mobile-light.png` (`390x844` mobile light, `scrollWidth === 390`)
- `live-kan15-field-help-popover-desktop-light.png` (`1440x900` light, `FieldHelpHint` popover)
- `live-kan15-field-help-popover-desktop-dark.png` (`1440x900` dark, `FieldHelpHint` popover)
- `live-kan15-dirty-confirm-undo-desktop-light.png` (`1440x900` light, 6-Preset Gallery + undo strip)
- `live-kan15-rail-evaluated-pills-desktop-light.png` (`1440x900` light, `KAN-1` Drawer `CustomFieldsRailSection` showing live evaluated `severity_pill`, `badge`, `number` pills and `(?)` rail hint)

### R2 Live Verification Summary (All 3 Problems PASS)
- **Problems 1 & 2 (`<FieldHelpHint />` & Studio/Rail Integration):** **PASS**
  - `0` inline JSX `style="..."` attributes, `0` CSP violations, `0` console/page/5xx errors, `scrollWidth === 390` on mobile, `scrollWidth === 768` on tablet.
  - `FieldHelpHint` `180ms` hover delay (`0` at 40ms, `1` at 260ms), `0ms` keyboard focus open, `Escape` close + focus restore, `<dl>` valid values, and `More info ->` verified live.
- **Problem 3 (4-Flavor Matrix, 6-Preset Starter Gallery & Live Formula Execution):** **PASS**
  - Dirty-form confirmation modal, Undo strip revert, and `POST /api/v1/projects/KAN/custom-fields` (`201 Created`) verified for all 3 `formula` presets (`days-until-due-sla`, `blocker-count`, `sub-issue-completion`).
  - Executing all 3 presets against `KAN-1` (with `due_date` set) via `POST /api/v1/issues/KAN-1/custom-fields/{id}/execute` AND in `KAN-1` Drawer (`CustomFieldsRailSection` refresh) returned **HTTP `200` (`status: "computed"`)** with **ZERO `422 SCRIPT_OUTPUT_SCHEMA_INVALID`** and rendered live `severity_pill` (`7.0 Due Soon`), `badge` (`Clear`), and `number` (`0 %`) pills.

**`LIVE_STACK_VERDICT: PASS`**

---

## 6. Targeted Live-QA Remediation (`fix/KAN-15-rc1`)

### 1. Root Cause Resolution
- **`kanban/custom_fields/executor.py`:**
  * Replaced naive regex in `_eval_safe_formula` with bracket-, brace-, parenthesis-, and quote-aware parser `_convert_js_ternary` and `_strip_outer_parens`.
  * Added AST node support for `ast.Tuple`, `ast.BoolOp` (`And`, `Or`), `ast.Compare` (`Eq`, `NotEq`, `Lt`, `LtE`, `Gt`, `GtE`, `Is`, `IsNot`, `In`, `NotIn` with safe `None`/`""` fallbacks), and `ast.Call` on allowlisted safe functions (`round`, `int`, `float`, `min`, `max`, `len`, `abs`, `str`), enforcing `_MAX_FORMULA_NODES = 64` and `_MAX_FORMULA_DEPTH = 8`.
  * Enriched `build_issue_context` with runtime fields: `days_until_due`, `due_date`, `start_date`, `blocker_count`, `sub_issue_count`, `completed_sub_issue_count`, `priority` (uppercase), `priority_slug` (lowercase), `state`, `state_group`.
- **`kanban/web/src/features/custom-fields/presets.ts`:**
  * Updated all formula presets (`days-until-due-sla`, `blocker-count`, `sub-issue-completion`) to use clean Python syntax referencing real runtime issue context keys and producing schema-compliant outputs (`severity_pill`, `badge`, `number`).
- **`kanban/tests/custom_fields/test_preset_formulas_e2e.py`:**
  * Real full-stack integration tests reading `presets.ts` directly from disk.
  * Verified all 3 formula presets across a complete matrix of issue states (overdue, due soon, no due date, urgent priority, high priority, blockers > 0, blockers == 0, cancelled, sub-issues positive, zero done, zero todo) with 0 NoneType / 422 failures.
  * Executed live PostgreSQL `CustomFieldExecutor.execute_for_issue` and `CustomFieldExecutor.test_execute` on all formula presets with 200 OK computed responses.

---

## 7. RC2 Clean-Room Remediation (`fix/KAN-15-rc2`)

### 1. Issue Detail Drawer Rail Pill Clipping Fix (`custom-fields.css` & `FieldHelpHint.css`)
- In `custom-fields.css`:
  * Added `flex-shrink: 0;` on `.custom-fields-refresh-btn` and `.custom-fields-rail-pill .emoji-hint` to prevent them from shrinking against long text.
  * Replaced restrictive `max-width: calc(100% - 130px)` on `.custom-fields-rail-pill` with `flex-shrink: 0; max-width: 100%;` to allow spacious pill display.
  * Set `min-width: 0;` on `.custom-fields-rail-value`, `.custom-fields-rail-label`, and `.custom-fields-rail-label-text` for proper flex layout behavior.
  * Added `gap: var(--space-2, 8px);` to `.custom-fields-rail-row` and `flex-shrink: 0;` on `.custom-field-severity-pill`.
- In `FieldHelpHint.css`:
  * Added `flex-shrink: 0;` on `.field-help-hint` trigger button.
- Clean design token compliance: 0 inline styles, 100% canonical tokens verified via `cssTokensAudit.test.ts`.

### 2. Elimination of React `act(...)` Warnings
- In `EscalationApprovalPanel.test.tsx`:
  * Wrapped state update in `act(() => { resolveRequest(pendingApproval); })` followed by `await waitFor(() => expect(screen.queryByTestId('approval-request-modal')).toBeNull())` to ensure the mutation settlement completes before test teardown.
- In `CustomFieldsRailSection.test.tsx`:
  * Wrapped execution completion in `act(() => { resolveExecution(firstRes); })` followed by `await waitFor(() => expect(refreshBtn.getAttribute('aria-busy')).toBe('false'))`.
- Verified 0 React `act(...)` stderr warnings across all 180 tests in Vitest.

### 3. Factual Alignment with Actual Implementation
- Documented `_MAX_FORMULA_DEPTH = 8` matching `kanban/custom_fields/executor.py` line 64.
- Documented 4 filter pills (`'all' | 'formula' | 'wasm' | 'nsjail'`) matching `PresetGallery.tsx` line 72.
- Documented exact testIds: `rail-field-hint-${def.slug}` (`CustomFieldsRailSection.tsx` line 178) and `hint-escalation-aal2` (`EscalationApprovalPanel.tsx` line 443).
- Popover header documented with bold title (`.field-help-hint-title`) without false close-button claims.
- Single unified `unit-test-results.txt` capturing both Pytest (61 passed) and Vitest (180 passed across both `src/features/custom-fields/` and `src/components/help/`).

**`FINAL_VERDICT: READY`**
