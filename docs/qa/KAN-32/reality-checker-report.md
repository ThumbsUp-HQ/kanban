# Integration Agent Reality-Based Report

## 🔍 Reality Check Validation
**Commands Executed**: Passive clean-room forensic inspection only (`read_file` exclusively; zero shell commands executed, zero URLs visited, zero files modified, strictly adhering to `.agents/agents/reality-checker.md`).
**Evidence Captured**:
- Verification packet files inspected in `docs/qa/KAN-32/`:
  - `docs/qa/KAN-32/message-to-reality-checker.md`
  - `docs/qa/KAN-32/changed-files-manifest.txt`
  - `docs/qa/KAN-32/git-diff.patch` (122 lines; covers `kanban/web/src/features/custom-fields/CustomFieldDefinitionEditor.tsx` only)
  - `docs/qa/KAN-32/unit-test-results.txt`
  - `docs/qa/KAN-32/build-or-typecheck.txt`
  - `docs/qa/KAN-32/live-fullstack-proof.txt`
  - `docs/qa/KAN-32/api-specialist-review.md`
  - `docs/qa/KAN-32/ui-specialist-review.md`
  - `docs/qa/KAN-32/reality-checker-report.md` (Round 1 baseline)
  - `docs/qa/KAN-32/wiki-diff.patch`
- All 11 live PNG screenshots inspected via `read_file` in `docs/qa/KAN-32/screenshots/`:
  - `live-desktop-light.png`, `live-new-field-matrix-presets-light.png`, `live-advanced-tier-gating-light.png`, `live-wiki-example3-test-exec-light.png`, `live-wasm-test-execute-light.png`, `live-desktop-test-exec.png`, `live-desktop-dark.png`, `live-long-log-wrap-light.png`, `live-tablet.png`, `live-mobile.png`, `live-guide-custom-fields-desktop-light.png`
- On-disk implementation and test files cross-checked:
  - `kanban/web/src/features/custom-fields/CustomFieldDefinitionEditor.tsx`
  - `kanban/web/src/features/custom-fields/__tests__/CustomFieldDefinitionEditor.test.tsx` (note: located under `__tests__/`, not directly in `custom-fields/`)
  - `kanban/web/src/features/custom-fields/custom-fields.css` (note: kebab-case filename on disk, not `customFields.css`)
  - `kanban/web/src/features/custom-fields/CustomFieldValue.tsx`
  - `kanban/custom_fields/builtin_wasm.py`
  - `kanban/custom_fields/executor.py`
  - `kanban/api/v1/custom_fields.py`
  - `kanban/api/v1/custom_field_execution.py`
  - `kanban/tests/custom_fields/test_builtin_wasm_preset.py`
  - `thumbs-up-kanban.wiki/Guide-Custom-Fields.md`
  - Note: `kanban/services/custom_fields.py` does not exist on disk; custom field service logic resides under `kanban/custom_fields/service.py`.

**QA Cross-Validation**:
- **Confirmed (Round 1 Remediations Verified)**:
  - **Single-line `<input>` / `<select>` 38px height parity**: `kanban/web/src/features/custom-fields/custom-fields.css` (lines 543-570) separates `.custom-field-input, .custom-field-select` (`min-height: 38px; line-height: 1.45;`) from `.custom-field-textarea` (`min-height: 140px;`). Visually confirmed across `live-tablet.png`, `live-advanced-tier-gating-light.png`, `live-wiki-example3-test-exec-light.png`, and `live-long-log-wrap-light.png`, and measured at `38px` in `live-fullstack-proof.txt` (lines 11-17).
  - **Bare formula copy-paste normalization**: `normalizeScriptSource` in `CustomFieldDefinitionEditor.tsx` (lines 189-207, invoked at lines 533, 574, 582) prepends `formula: ` (or `scalar: `) when missing. Confirmed by `CustomFieldDefinitionEditor.test.tsx` (lines 1042-1109) and live container proof in `live-wiki-example3-test-exec-light.png` + `live-fullstack-proof.txt` (lines 26-33: HTTP 200 OK in 3ms, pill `"2.0 Low"`).
  - **Built-in `STARTER_TEMPLATES.wasm` and DB override precedence**: `CustomFieldDefinitionEditor.tsx` (lines 65-73) includes `// echo_cvss.wasm - WebAssembly Tier A Module (Base64)`; `builtin_wasm.py` `_resolve_by_bytecode` (lines 140-149) and comment-only fallback (lines 215-226) query workspace `ApprovedWasmModule` overrides first before returning built-in `echo_cvss.wasm`. Confirmed by `test_builtin_wasm_preset.py` (Test 8, lines 226-266) and `live-wasm-test-execute-light.png` (HTTP 200 OK, 10ms).
  - **Duplicate severity score eliminated**: `CustomFieldValue.tsx` (lines 355-362) strips leading `displayScore` from `displayLabel`. Visually confirmed in `live-wasm-test-execute-light.png`, `live-desktop-test-exec.png`, and `live-desktop-dark.png` rendering `"8.8 High"` instead of `"8.8 8.8 High"`.
  - **Standalone `nsjail` badge clarification**: `CustomFieldDefinitionEditor.tsx` (lines 923, 1185) updates `flavor-nsjail-disabled-badge` and `tier-nsjail-disabled-badge` to `"nsjail option requires Multi-Container Compose"`, visually confirmed in `live-tablet.png` and `live-advanced-tier-gating-light.png`.
  - **`Guide-Custom-Fields.md` Example 3 & 4 fixes**: `thumbs-up-kanban.wiki/Guide-Custom-Fields.md` (lines 93-147, 188) updates Example 3 to return a valid `severity_pill` dict, aligns Section 4 item 4 with `_validate_severity_pill`, and adds a runnable Python snippet to Example 4. Confirmed by `test_builtin_wasm_preset.py` (Test 9, lines 269-321) and `live-wiki-example3-test-exec-light.png`.
- **Challenged (Specialist Reviews Missed a Live Visual Overflow Defect & Packet Drift)**:
  - Both `ui-specialist-review.md` (`STATUS: APPROVED`) and `api-specialist-review.md` (`STATUS: APPROVED`) overlooked a blatant visual overflow inside `live-long-log-wrap-light.png`: while `pre.custom-field-test-logs` wraps cleanly (`scrollWidth=742 === clientWidth=742`), the **`Rendered Output Pill:`** directly above it renders the 220-character `"UNBROKEN_LOG_LINE_XXX..."` string via `.custom-field-text`, shooting straight past the right border of `.custom-field-test-result`, outside `.custom-field-test-panel`, and clipping off the right edge of the 1440px viewport.
  - `api-specialist-review.md` (lines 128-137) and `message-to-reality-checker.md` (lines 108-117) claim to certify `main` commit `7913c2c8` while quoting stale worktree static metrics (`1004 files`, `996 source files`, `62 migrations`, `p4_23_oidc_link_intent_fk`, `2.27s` Vite build) from `fix/KAN-32-rc2` (`unit-test-results.txt`) instead of `build-or-typecheck.txt` on `7913c2c8` (`2018 files`, `995 source files`, `63 migrations`, `p4_24_agent_safe_sequences`, `1.22s` Vite build).
  - `unit-test-results.txt` was captured in worktree `swarm-b-kan32-rc2-081cdef1` rather than on `main` commit `7913c2c8`, and its Vitest `COVERAGE_INCLUDE` filter omitted `CustomFieldValue.tsx` (which was modified in RC2).

## 📸 Complete System Evidence
**Visual Documentation**:
- Full system screenshots (`docs/qa/KAN-32/screenshots/`):
  - `live-desktop-light.png` (1440x900 Desktop Light; sha256 `0b07c247...`, byte-identical to `live-new-field-matrix-presets-light.png`)
  - `live-new-field-matrix-presets-light.png` (1440x900 Desktop Light, `+ New Field` view with `Standalone Mode Active` callout, `FlavorDecisionMatrix`, and `PresetGallery`)
  - `live-advanced-tier-gating-light.png` (1440x900 Desktop Light, `Advanced` tab showing `Execution Sandbox`, `Token Scope`, `Credential Mode` selects at 38px and `nsjail option requires Multi-Container Compose` badge)
  - `live-wiki-example3-test-exec-light.png` (1440x900 Desktop Light, bare Example 3 formula Test Execute returning `SUCCESS`, `3.0 ms`, pill `2.0 Low`)
  - `live-wasm-test-execute-light.png` (1440x900 Desktop Light, manual WebAssembly `STARTER_TEMPLATES.wasm` Test Execute returning `SUCCESS`, `10.0 ms`, pill `8.8 High`)
  - `live-desktop-test-exec.png` (1440x900 Desktop Light, duplicate/alternate capture of WebAssembly `8.8 High` Test Execute view)
  - `live-desktop-dark.png` (1440x900 Desktop Dark, WebAssembly `8.8 High` Test Execute view with legible dark-mode contrast)
  - `live-long-log-wrap-light.png` (1440x900 Desktop Light, 220-char unbroken formula string Test Execute)
  - `live-tablet.png` (768x1024 Tablet Light, Basic tab showing 38px inputs/selects, clarified `nsjail` badge, and bare Example 3 expression)
  - `live-mobile.png` (390x844 Mobile Light, `PresetGallery` cards only; Basic form and Test Execute panel are not shown on mobile)
  - `live-guide-custom-fields-desktop-light.png` (Desktop Light, `/docs/Guide-Custom-Fields` Chapter 10 of 28)
- User journey evidence: Covers `+ New Field` matrix/presets, `Basic` tab inputs, `Advanced` tab tier gating, bare Example 3 copy-paste execution, manual `echo_cvss.wasm` execution, light/dark modes, and offline docs guide.
- Cross-browser comparison: Chromium/Playwright only (no Firefox or WebKit captures).

**What System Actually Delivers**:
- **Visual Quality**:
  - Input/select sizing, dark-mode contrast, `8.8 High` pill spacing, `2.0 Low` pill rendering, and `pre.custom-field-test-logs` wrapping are all clean.
  - **Uncontained Text Overflow in `live-long-log-wrap-light.png`**: Inside `Rendered Output Pill:`, `<span class="custom-field-text">` renders the 220-character unbroken string without wrapping (`custom-fields.css` line 173 `.custom-field-text { font-size: 12px; }` lacks `overflow-wrap: anywhere; word-break: break-all;`), causing the string to break out of `.custom-field-test-result`, `.custom-field-test-panel`, and clip past the right edge of the 1440px viewport.
  - On `live-wiki-example3-test-exec-light.png` and `live-long-log-wrap-light.png`, `Truncated Logs:` displays `Draft test execution on SEC2-1 (flavor=wasm)` even when executing a Formula expression, because `kanban/custom_fields/executor.py` line 982 interpolates `tier_val` (`"wasm"`) under the label `flavor=`.
- **Actual vs. Claimed Functionality**:
  - Bare Example 3 formula normalization, `STARTER_TEMPLATES.wasm` Test Execute, DB `ApprovedWasmModule` override precedence, and fail-closed standalone `nsjail` gating all work end-to-end against real PostgreSQL 16 + `FORCE ROW LEVEL SECURITY` with zero mocks (`live-fullstack-proof.txt`: 0 console errors, 0 page errors, 0 HTTP 5xx).
  - `live-fullstack-proof.txt` (lines 44-47) verified `scrollWidth === clientWidth` (742px) solely on `pre.custom-field-test-logs` and did not measure `scrollWidth` on `.custom-field-test-result` or `.custom-field-pill-preview`, missing the horizontal overflow visible in `live-long-log-wrap-light.png`.

## 🧪 Integration Testing Results
**End-to-End User Journeys**: **PARTIAL PASS / NEEDS WORK**
- **Journey 1 - Standalone `nsjail` Gating & Advanced Tab (`live-new-field-matrix-presets-light.png`, `live-advanced-tier-gating-light.png`)**: **PASS** (38px select height, disabled `nsjail` options, clear `"nsjail option requires Multi-Container Compose"` badges).
- **Journey 2 - Guide Example 3 Bare Formula Copy-Paste Normalization (`live-wiki-example3-test-exec-light.png`, `live-tablet.png`)**: **PASS** (38px inputs/selects, `POST .../test-execute` HTTP 200 OK in 3ms, pill `"2.0 Low"`).
- **Journey 3 - Manual WebAssembly `STARTER_TEMPLATES.wasm` Execution (`live-wasm-test-execute-light.png`, `live-desktop-dark.png`)**: **PASS** (HTTP 200 OK in 10ms, pill `"8.8 High"`, no duplicate score).
- **Journey 4 - 220-Char Unbroken Formula/Log Display (`live-long-log-wrap-light.png`)**: **FAIL** (`pre.custom-field-test-logs` wraps cleanly at 742px, but `Rendered Output Pill:` directly above it overflows horizontally out of the card and off the right edge of the viewport).

**Cross-Device Consistency**: **PASS WITH CAVEAT**
- `live-desktop-light.png` (1440x900), `live-tablet.png` (768x1024, `scrollWidth=768`), and `live-mobile.png` (390x844, `scrollWidth=390`) show clean responsive layout without viewport overflow on the preset gallery and basic tab, though mobile Test Execute output was not captured and the long unbroken `.custom-field-text` pill overflows on desktop.

**Performance Validation**: **PASS**
- `live-fullstack-proof.txt` reports `/projects/SEC2/settings/custom-fields` load in 848ms, bare Example 3 `test-execute` in 3ms, WebAssembly `test-execute` in 10ms, and 220-char formula `test-execute` in 6ms (all well below 3s).

**Specification Compliance**: **PARTIAL PASS**
- Standalone `nsjail` gating, `tier_b_runner` wiring, input height parity, bare formula normalization, `STARTER_TEMPLATES.wasm` resolution, DB overrides, and `Guide-Custom-Fields.md` examples are implemented and verified, except for the unbroken text pill overflow in `CustomFieldValue` / `custom-fields.css` and packet/test-run reconciliation on `main`.

## 📊 Comprehensive Issue Assessment
**Issues from QA Still Present**:
1. **Medium / Visual Overflow - Long Unbroken Text Output Overflows Card and Viewport (`live-long-log-wrap-light.png`, `custom-fields.css` lines 173-175 & 1462-1464)**: While `pre.custom-field-test-logs` wraps cleanly, `Rendered Output Pill:` (`<span class="custom-field-text">`) lacks `overflow-wrap: anywhere; word-break: break-all;` (and `.custom-field-test-result` / `.custom-field-pill-preview` lacks `min-width: 0; max-width: 100%;`), causing the 220-char unbroken string in `live-long-log-wrap-light.png` to visually breach the card border and clip past the right edge of the viewport.
2. **Low / QA Packet Integrity & Stale Worktree Metrics (`unit-test-results.txt`, `build-or-typecheck.txt`, `api-specialist-review.md`, `changed-files-manifest.txt`, `git-diff.patch`)**:
   - `unit-test-results.txt` was run in worktree `swarm-b-kan32-rc2-081cdef1` (`fix/KAN-32-rc2`, 62 migrations, 1004 ruff files, 996 mypy files, 2.27s build) rather than on `main` commit `7913c2c8` (`build-or-typecheck.txt`: 63 migrations, 2018 ruff files, 995 mypy files, 1.22s build), and `api-specialist-review.md` / `message-to-reality-checker.md` repeat the stale worktree static metrics under the `7913c2c8` header.
   - `unit-test-results.txt` Vitest `COVERAGE_INCLUDE` omitted `CustomFieldValue.tsx`.
   - `changed-files-manifest.txt` hashes only 3 source files (`kanban/api/v1/custom_fields.py`, `CustomFieldDefinitionEditor.tsx`, `Guide-Custom-Fields.md`) and `git-diff.patch` contains only `CustomFieldDefinitionEditor.tsx`.
   - `live-desktop-light.png` and `live-new-field-matrix-presets-light.png` are byte-identical (`0b07c247...`).

**New Issues Discovered**:
1. **Low / Misleading Test-Execute Log Label (`kanban/custom_fields/executor.py` line 982, `live-wiki-example3-test-exec-light.png`)**: `logs = f"Draft test execution on {body.issue_key} (flavor={tier_val})\n"` logs `(flavor=wasm)` for Formula and Scalar expressions because `tier_val` (`"wasm"`) is printed as `flavor=`.

**Critical Issues**: None remaining (all Round 1 critical functional issues in `Guide-Custom-Fields.md` Example 3, `STARTER_TEMPLATES.wasm`, bare formula normalization, and `ApprovedWasmModule` DB overrides are resolved and verified live).
**Medium Issues**:
- `.custom-field-text` / `.custom-field-pill-preview` horizontal overflow on long unbroken strings in `live-long-log-wrap-light.png`.
- Reconciling `unit-test-results.txt` (including `CustomFieldValue.tsx` coverage), `changed-files-manifest.txt`, and specialist review metrics on `main`.

## 🎯 Realistic Quality Certification
**Overall Quality Rating**: B+
**Design Implementation Level**: Good (all 7 Round 1 findings were genuinely fixed, except the newly exposed `Rendered Output Pill` overflow in `live-long-log-wrap-light.png` and packet/metric drift)
**System Completeness**: 95%
**Production Readiness**: NEEDS WORK

## 🔄 Deployment Readiness Assessment
**Status**: NEEDS WORK

**Required Fixes Before Production**:
1. **Fix `.custom-field-text` / `.custom-field-pill-preview` Horizontal Overflow (`kanban/web/src/features/custom-fields/custom-fields.css` lines 173-175, 953-962, 1462-1464)**: Add `overflow-wrap: anywhere; word-break: break-all; max-width: 100%;` (and `min-width: 0; max-width: 100%;` on `.custom-field-test-result` / `.custom-field-test-preview-wrap` / `.custom-field-pill-preview-mt`) so unbroken strings wrap cleanly inside the `Rendered Output Pill:` card as well as `pre.custom-field-test-logs`. Prove with an updated `live-long-log-wrap-light.png` and DOM `scrollWidth <= clientWidth` check on both `pre.custom-field-test-logs` and `.custom-field-test-result`.
2. **Clarify `executor.py:982` Log Label (Optional / Low)**: Change `(flavor={tier_val})` to `(tier={tier_val})` or report the detected flavor (`scalar` / `formula` / `wasm` / `nsjail`) so Formula/Scalar logs do not claim `flavor=wasm`.
3. **Reconcile QA Packet on Target `main` Commit**: Re-run `pytest` and `vitest --coverage` (including `CustomFieldValue.tsx` in `COVERAGE_INCLUDE`) on the final `main` commit, align static gate counts in `api-specialist-review.md` and `message-to-reality-checker.md` with `build-or-typecheck.txt`, and ensure `changed-files-manifest.txt` and `git-diff.patch` cover all changed source/test files.

**Timeline for Production Readiness**: 1 short polish pass (estimated 1-2 hours for CSS fix, test re-run on `main`, and fresh `live-long-log-wrap-light.png` capture)
**Revision Cycle Required**: YES

## 📈 Success Metrics for Next Iteration
**What Needs Improvement**:
- Contain unbroken output values inside `.custom-field-test-result` (`Rendered Output Pill`) just as `pre.custom-field-test-logs` already does.
- Ensure live Playwright assertions check container-level `scrollWidth <= clientWidth` on `.custom-field-test-result` (not only `pre.custom-field-test-logs`).
- Keep `unit-test-results.txt`, `build-or-typecheck.txt`, and specialist reviews aligned to the exact same `main` commit SHA.

**Quality Targets**:
- Zero horizontal overflow (`scrollWidth <= clientWidth`) on both `.custom-field-test-result` and `pre.custom-field-test-logs` for 220+ char unbroken outputs.
- `>=95%` Python and TypeScript coverage (including `CustomFieldValue.tsx`) verified on the target `main` commit.

**Evidence Requirements**:
- Updated `docs/qa/KAN-32/screenshots/live-long-log-wrap-light.png` visually showing both `Rendered Output Pill` and `Truncated Logs` wrapped cleanly inside the card bounds.
- Updated `docs/qa/KAN-32/live-fullstack-proof.txt` asserting `scrollWidth <= clientWidth` on `.custom-field-test-result` and `pre.custom-field-test-logs`.
- Reconciled `docs/qa/KAN-32/unit-test-results.txt`, `build-or-typecheck.txt`, and specialist reviews matching the exact final `main` commit.

---
**Integration Agent**: RealityIntegration
**Assessment Date**: 2026-11-20
**Evidence Location**: docs/qa/KAN-32/
**Re-assessment Required**: After fixes implemented
