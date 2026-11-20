# Integration Agent Reality-Based Report

## 🔍 Reality Check Validation
**Commands Executed**:
- Read-only clean-room audit mode enforced: zero shell commands executed, zero URLs visited, zero files modified.
- Audited `.agents/agents/reality-checker.md` and all verification artifacts in `docs/qa/KAN-15/` (`message-to-reality-checker.md`, `changed-files-manifest.txt`, `unit-test-results.txt`, `build-or-typecheck.txt`, `live-fullstack-proof.txt`, `api-specialist-review.md`, `ui-specialist-review.md`, `git-diff.patch`).
- Visually inspected all 8 PNG screenshots in `docs/qa/KAN-15/screenshots/`.
- Cross-checked implementation and test files listed in `changed-files-manifest.txt` (`kanban/custom_fields/executor.py`, `kanban/tests/custom_fields/test_preset_formulas_e2e.py`, `kanban/web/src/components/help/FieldHelpHint.tsx`, `FieldHelpHint.css`, `FieldHelpHint.test.tsx`, `kanban/web/src/features/custom-fields/presets.ts`, `FlavorDecisionMatrix.tsx`, `PresetGallery.tsx`, `custom-fields.css`, `CustomFieldDefinitionEditor.tsx`, `EscalationApprovalPanel.tsx`, `CustomFieldsRailSection.tsx`, and associated unit test files).

**Evidence Captured**:
- Backend Pytest (`unit-test-results.txt`): 61 passed in 28.63s (`test_preset_formulas_e2e.py` 5/5 passed, `test_safe_formula_unit.py` 6/6 passed), 96% statement/branch coverage on `kanban/custom_fields/executor.py` (584 stmts, 18 missed, 252 branches, 19 partial).
- Frontend Vitest (`unit-test-results.txt`): 9 test files, 157 passed in 6.08s across `src/features/custom-fields/` (99.66% stmts, 96.84% branch, 100% funcs, 100% lines), with 3 React `act(...)` warnings logged on stderr in `EscalationApprovalPanel.test.tsx` and `CustomFieldsRailSection.test.tsx`. Note: `src/components/help/FieldHelpHint.test.tsx` was not included in the post-remediation `unit-test-results.txt` run.
- Static Gates (`build-or-typecheck.txt`): `tsc -b --noEmit` (0 errors), `eslint . --max-warnings 0` (0 warnings/errors), `cssTokensAudit.test.ts` (4/4 passed), `ruff check` (All checks passed), `mypy` (0 issues in 2 source files), `lint-imports` (2 kept, 0 broken), `check_no_dashes` (clean; skips `docs/qa/KANBA-205/mcp-transcript.txt` > 5 MiB).
- Live Full-Stack Proof (`live-fullstack-proof.txt`, R2 on `kanban-liveqa-2` at `http://localhost:18952`, commit `23ae056d`, `standalone_embedded_pg`): Zero mocks (`0` occurrences of `mockApi`, `page.route`, `context.route`). Verified `POST /api/v1/projects/KAN/custom-fields` (`201 Created`) and `POST /api/v1/issues/KAN-1/custom-fields/{id}/execute` (`200 OK`, `status="computed"`, `last_latency_ms=1`) for all 3 formula presets (`days-until-due-sla`, `blocker-count`, `sub-issue-completion`), plus Issue Detail Drawer rendering (`7.0 Due Soon`, `Clear`, `0 %`), `consoleErrors=0`, `pageErrors=0`, `cspViolations=0`, `serverErrors=0`, and `0` inline JSX `style="..."` attributes.

**QA Cross-Validation**:
- Confirmed core R2 live execution claims and AST/PostgreSQL context remediation in `api-specialist-review.md` (`STATUS: APPROVED`) and `ui-specialist-review.md` (`STATUS: APPROVED`).
- Challenged multiple overstated or inaccurate claims across `message-to-reality-checker.md`, `ui-specialist-review.md`, and `api-specialist-review.md`:
  1. `message-to-reality-checker.md` (line 23) and `ui-specialist-review.md` (line 23) claim `<FieldHelpHint />` renders a "Header with Title and close button (`aria-label="Close help popover"`)". Cross-checking `FieldHelpHint.tsx` lines 331-333 and all popover screenshots proves there is NO close button in `.field-help-hint-header` (only the `<strong>` title).
  2. `message-to-reality-checker.md` (line 70) claims filter pills cover `('all', 'formula', 'wasm', 'nsjail', 'scalar')`. `PresetGallery.tsx` line 72 and `live-kan15-dirty-confirm-undo-desktop-light.png` show only 4 filter buttons (`All Presets`, `Formula`, `WebAssembly`, `Nsjail`) - there is no `scalar` filter pill.
  3. `message-to-reality-checker.md` (lines 50-51) cites `hint-escalation-stepup` and `cf-field-hint-${field.slug}`, whereas actual code uses `hint-escalation-aal2` (`EscalationApprovalPanel.tsx` line 443) and `rail-field-hint-${def.slug}` (`CustomFieldsRailSection.tsx` line 178).
  4. `api-specialist-review.md` (line 42) states `_MAX_FORMULA_DEPTH = 12`, whereas `kanban/custom_fields/executor.py` line 64 actually enforces `_MAX_FORMULA_DEPTH = 8`.
  5. `message-to-reality-checker.md` Section 2 cites a 10-file / 180-test Vitest run (`99.81%` stmts) including `FieldHelpHint.test.tsx`, whereas the actual committed `unit-test-results.txt` only contains the 9-file / 157-test `src/features/custom-fields/` run from `fix/KAN-15-rc1` (omitting `src/components/help/`).

## 📸 Complete System Evidence
**Visual Documentation**:
- Full system & responsive matrix screenshots:
  - `docs/qa/KAN-15/screenshots/live-kan15-presets-matrix-desktop-light.png` (1440x900, light)
  - `docs/qa/KAN-15/screenshots/live-kan15-presets-matrix-desktop-dark.png` (1440x900, dark)
  - `docs/qa/KAN-15/screenshots/live-kan15-presets-matrix-tablet-light.png` (768x1024, tablet light)
  - `docs/qa/KAN-15/screenshots/live-kan15-presets-matrix-mobile-light.png` (390x844, mobile light)
- Interactive popover, preset undo, and live issue rail screenshots:
  - `docs/qa/KAN-15/screenshots/live-kan15-field-help-popover-desktop-light.png` (1440x900, light)
  - `docs/qa/KAN-15/screenshots/live-kan15-field-help-popover-desktop-dark.png` (1440x900, dark)
  - `docs/qa/KAN-15/screenshots/live-kan15-dirty-confirm-undo-desktop-light.png` (1440x900, light)
  - `docs/qa/KAN-15/screenshots/live-kan15-rail-evaluated-pills-desktop-light.png` (1440x900, light)
- Cross-browser comparison: Chromium headless only (no Firefox/WebKit screenshots captured).

**What System Actually Delivers**:
- **4-Flavor Decision Matrix (`presets-matrix-*`)**: Renders cleanly in light and dark modes on desktop (3+1 card grid), tablet (2x2 grid), and mobile (single stacked column, `scrollWidth === 390`). Note: in `live-kan15-presets-matrix-mobile-light.png`, the global topbar user avatar (`S`) is clipped at the right edge of the 390px viewport, though the Custom Fields Studio content itself does not overflow.
- **`<FieldHelpHint />` Popover (`field-help-popover-*`)**: Renders crisp typography, `<dl>` valid values for all 7 output formats, formatted JSON example block, and `More info ->` link in both light and dark modes with high contrast. No close button appears in the popover header.
- **6-Preset Gallery & Undo Strip (`dirty-confirm-undo-*`)**: Shows `All Presets`, `Formula`, `WebAssembly`, `Nsjail` filter pills, green undo strip (`Applied preset Days Until Due / SLA Breach.` + `Undo` + `x`), and preset cards (`CVSS 3.1 / 4.0 Score`, `Total Issues in Project`, `Days Until Due / SLA Breach`, `Blocker Count`).
- **KAN-1` Issue Detail Drawer (`rail-evaluated-pills-*`)**: Shows live evaluated `Blocker Count` (`Clear`) and `Sub-Issue Completion %` (`0 %`) pills and an open `Days Until Due / SLA Breach` `<FieldHelpHint />` popover (`Flavor: Formula`, `Tier: wasm`, `Scope: PROJECT`, `Mode: INVOKING_USER`, `More info ->`). **HOWEVER**, on the `Days Until Due / SLA Breach` row in the bottom-right corner, the `7.0 Due Soon` severity pill text is visibly clipped/overlapped at its right edge by the circular refresh button (`7.0 Due Soc` + refresh icon), because `.custom-fields-rail-pill` has `max-width: calc(100% - 130px)` and `.custom-fields-refresh-btn` lacks `flex-shrink: 0` in `custom-fields.css`.

## 🧪 Integration Testing Results
**End-to-End User Journeys**: PASS (functional backend/API) / PARTIAL (minor rail UI clipping)
- Setup -> `/projects/KAN/settings/custom-fields` -> 4-Flavor Matrix expand -> `<FieldHelpHint />` hover (`openAt40ms=0`, `openAt260ms=1`), focus (`openAtFocus0ms=1`), Escape focus restore (`openAfterEsc=0`, `activeElement="hint-format-metadata"`) -> dirty form confirm dialog -> undo strip revert -> create all 3 formula fields (`201 Created`) -> execute all 3 against `KAN-1` (`200 OK`, `status="computed"`, zero 422s) -> render in `KAN-1` Drawer.
- Visual issue observed in `live-kan15-rail-evaluated-pills-desktop-light.png`: `7.0 Due Soon` pill truncates awkwardly against the refresh button (`7.0 Due Soc`).

**Cross-Device Consistency**: PARTIAL PASS
- Desktop (1440x900 light/dark) and Tablet (768x1024 light) render Studio layouts cleanly.
- Mobile (390x844 light) Studio panel fits with `scrollWidth === 390`, but the global topbar avatar clips on the right edge, and no tablet/mobile screenshots were provided for the Issue Detail Drawer or `<FieldHelpHint />` popover.

**Performance Validation**: PASS
- `live-fullstack-proof.txt` measures `last_latency_ms: 1` for all 3 formula executions on `KAN-1` (within the `<5ms` Formula budget). Zero 5xx/422 errors, zero console/page/CSP errors. Page load timing in ms was not separately logged in `live-fullstack-proof.txt`.

**Specification Compliance**: PARTIAL PASS
- Core 3 problems are implemented and proven live against unmocked PostgreSQL + FastAPI + React.
- Minor spec/packet mismatches: popover header lacks the claimed close button (`FieldHelpHint.tsx` line 331), preset gallery lacks the claimed `scalar` filter pill (`PresetGallery.tsx` line 72), and `unit-test-results.txt` omits `FieldHelpHint.test.tsx` in the final post-remediation run.

## 📊 Comprehensive Issue Assessment
**Issues from QA Still Present**:
- None of the R1 formula execution failures (`422 SCRIPT_OUTPUT_SCHEMA_INVALID` / naive ternary regex / missing context keys) remain; all 3 formula presets execute cleanly with `200 OK`.

**New Issues Discovered**:
1. **[Medium] Evaluated pill text clipping/overlap in narrow Issue Detail Drawer rail**: In `docs/qa/KAN-15/screenshots/live-kan15-rail-evaluated-pills-desktop-light.png`, the `Days Until Due / SLA Breach` row renders `7.0 Due Soc` clipped against the `↻` refresh button (`custom-fields.css` lines 55-92: `.custom-fields-rail-pill` `max-width: calc(100% - 130px)` and `.custom-fields-refresh-btn` missing `flex-shrink: 0` / `.custom-fields-rail-value` `min-width: 0`).
2. **[Medium] Verification packet and specialist review factual inaccuracies**:
   - `message-to-reality-checker.md` and `ui-specialist-review.md` claim a popover close button (`aria-label="Close help popover"`) that does not exist in `FieldHelpHint.tsx`.
   - `message-to-reality-checker.md` claims a `scalar` filter pill (`PresetGallery.tsx` only has `all`, `formula`, `wasm`, `nsjail`) and misstates testIds (`cf-field-hint-*` vs `rail-field-hint-*`, `hint-escalation-stepup` vs `hint-escalation-aal2`).
   - `api-specialist-review.md` states `_MAX_FORMULA_DEPTH = 12` when `executor.py` line 64 defines `_MAX_FORMULA_DEPTH = 8`.
3. **[Medium] Incomplete post-remediation Vitest artifact & `act(...)` warnings**: `docs/qa/KAN-15/unit-test-results.txt` only reflects `src/features/custom-fields/` (9 files, 157 tests), omitting `src/components/help/FieldHelpHint.test.tsx` from the latest captured log, and emits 3 React `act(...)` warnings on stderr (`EscalationApprovalPanel.test.tsx`, `CustomFieldsRailSection.test.tsx`).
4. **[Low] Unverified non-formula presets in live R2 run & mobile topbar clipping**: `live-fullstack-proof.txt` R2 executed the 3 `formula` presets end-to-end (`days-until-due-sla`, `blocker-count`, `sub-issue-completion`), while `cvss-score` (`wasm`) execution was not re-captured in R2. Additionally, `live-kan15-presets-matrix-mobile-light.png` shows the global topbar user avatar `S` clipped at the right edge of 390px.

**Critical Issues**:
- None (no security bypasses, no broken API contracts, no 422/500 errors, no inline style CSP violations, no mock leakage in live QA).

**Medium Issues**:
1. Fix Issue Detail Drawer rail pill layout so `7.0 Due Soon` and the refresh button do not clip or overlap in `live-kan15-rail-evaluated-pills-desktop-light.png`.
2. Re-run and capture `unit-test-results.txt` covering BOTH `src/features/custom-fields/` AND `src/components/help/` together, and clean up the 3 React `act(...)` stderr warnings.
3. Align `message-to-reality-checker.md`, `ui-specialist-review.md`, and `api-specialist-review.md` with the exact implemented code (remove false close-button / `scalar`-filter claims, fix testId names and `_MAX_FORMULA_DEPTH = 8`).

## 🎯 Realistic Quality Certification
**Overall Quality Rating**: B+ (solid engineering and live R2 formula execution, held back from grade-A READY by visible rail pill clipping and verification-packet inaccuracies)
**Design Implementation Level**: Good
**System Completeness**: 95%
**Production Readiness**: NEEDS WORK

## 🔄 Deployment Readiness Assessment
**Status**: NEEDS WORK

**Required Fixes Before Production**:
1. **Fix Issue Rail Pill Clipping (`kanban/web/src/features/custom-fields/custom-fields.css`)**: Prevent `.custom-fields-rail-value` / `.custom-field-severity-pill` from clipping under/against `.custom-fields-refresh-btn` (as visible on `7.0 Due Soc` in `docs/qa/KAN-15/screenshots/live-kan15-rail-evaluated-pills-desktop-light.png`) by adding `flex-shrink: 0` on `.custom-fields-refresh-btn` and `EmojiHint` trigger, `min-width: 0` on `.custom-fields-rail-value`, and appropriate `max-width` / `gap` sizing in the rail row, then re-capture the live drawer screenshot.
2. **Regenerate Complete Frontend + Backend `unit-test-results.txt`**: Run Vitest across BOTH `src/features/custom-fields/` and `src/components/help/` in a single captured log (matching the 10-file scope claimed in `message-to-reality-checker.md`) and wrap async state updates in `EscalationApprovalPanel.test.tsx` and `CustomFieldsRailSection.test.tsx` to eliminate the 3 `act(...)` stderr warnings.
3. **Correct Factual Discrepancies in QA Docs**: Update `docs/qa/KAN-15/message-to-reality-checker.md`, `ui-specialist-review.md`, and `api-specialist-review.md` so they accurately reflect the implemented header (either add the close button or remove the false claim), filter pills (`all`, `formula`, `wasm`, `nsjail`), actual `testId` strings (`rail-field-hint-*`, `hint-escalation-aal2`), and `_MAX_FORMULA_DEPTH = 8`.

**Timeline for Production Readiness**: 0.5 to 1 day (1 focused polish and re-verification cycle).
**Revision Cycle Required**: YES

## 📈 Success Metrics for Next Iteration
**What Needs Improvement**:
- Narrow-rail pill spacing and truncation in `CustomFieldsRailSection` so multi-word `severity_pill` labels (`7.0 Due Soon`) display cleanly alongside the refresh icon.
- Strict alignment between specialist review documents, `message-to-reality-checker.md`, and actual TSX/Python source code.
- Clean Vitest output without React `act(...)` warnings and complete coverage inclusion for `src/components/help/` in `unit-test-results.txt`.

**Quality Targets**:
- Grade-A `READY` certification with 0 visual overlap/clipping in desktop, tablet, and mobile screenshots.
- 100% factual accuracy in `message-to-reality-checker.md` and specialist reviews.
- `>=95%` coverage across all modified backend and frontend files in a single unified `unit-test-results.txt` with 0 stderr `act(...)` warnings.

**Evidence Requirements**:
- Updated `live-kan15-rail-evaluated-pills-desktop-light.png` showing `7.0 Due Soon` completely legible with clean spacing before the refresh icon.
- Updated `unit-test-results.txt` including both `src/components/help/` and `src/features/custom-fields/` (0 `act(...)` warnings) alongside the 61 backend Pytest tests.
- Corrected `message-to-reality-checker.md` and specialist review files, plus optional live R2 execution proof for `cvss-score` (`wasm`) alongside the 3 formula presets.

---
**Integration Agent**: RealityIntegration
**Assessment Date**: 2026-11-20
**Evidence Location**: docs/qa/KAN-15/
**Re-assessment Required**: After fixes implemented
