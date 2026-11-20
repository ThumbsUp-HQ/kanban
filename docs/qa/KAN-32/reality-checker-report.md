# Integration Agent Reality-Based Report

## 🔍 Reality Check Validation
**Commands Executed**: Passive clean-room forensic inspection only (zero shell commands executed, zero URLs visited, zero files modified; `read_file` used exclusively across all QA artifacts, screenshots, and source files).
**Evidence Captured**:
- QA packet files inspected in `/home/adamoutler/kanban/docs/qa/KAN-32/`: `message-to-reality-checker.md`, `changed-files-manifest.txt`, `unit-test-results.txt`, `build-or-typecheck.txt`, `live-fullstack-proof.txt`, `api-specialist-review.md`, `ui-specialist-review.md`, `git-diff.patch` (lines 1-300).
- All 6 PNG screenshots inspected in `/home/adamoutler/kanban/docs/qa/KAN-32/screenshots/`: `live-desktop-light.png`, `live-desktop-dark.png`, `live-desktop-test-exec.png`, `live-tablet.png`, `live-mobile.png`, `live-guide-custom-fields-desktop-light.png`.
- On-disk implementation files cross-checked: `kanban/custom_fields/executor.py`, `kanban/custom_fields/builtin_wasm.py`, `kanban/custom_fields/service.py`, `kanban/custom_fields/output_formats.py`, `kanban/api/v1/custom_fields.py`, `kanban/api/v1/custom_field_execution.py`, `kanban/api/v1/system.py`, `kanban/api/v1/system_status.py`, `kanban/app.py`, `kanban/sandbox/nsjail_runner.py`, `kanban/sandbox/probe.py`, `kanban/web/src/app/useSystemStatus.ts`, `kanban/web/src/features/custom-fields/CustomFieldsStudio.tsx`, `kanban/web/src/features/custom-fields/CustomFieldDefinitionEditor.tsx`, `kanban/web/src/features/custom-fields/FlavorDecisionMatrix.tsx`, `kanban/web/src/features/custom-fields/PresetGallery.tsx`, `kanban/web/src/features/custom-fields/presets.ts`, `kanban/web/src/features/custom-fields/CustomFieldValue.tsx`, `kanban/web/src/features/custom-fields/custom-fields.css`, `kanban/web/src/styles/theme.css`, `kanban/tests/custom_fields/test_standalone_nsjail_gate.py`, `kanban/tests/custom_fields/test_builtin_wasm_preset.py`, `thumbs-up-kanban.wiki/Guide-Custom-Fields.md`, and `thumbs-up-kanban.wiki/_Sidebar.md`.

**QA Cross-Validation**:
- **Confirmed**:
  - `GET /api/v1/system/status` in `kanban/api/v1/system_status.py` (lines 50-68, 152-214) exposes `supported_custom_field_tiers: ["scalar", "formula", "wasm"]` and `sandbox_unavailable_reason` when `tier_b_sandbox_available` is `False`, matching `live-fullstack-proof.txt` (HTTP 200 in 6ms). Note that `kanban/api/v1/system.py` handles `/system/about`, `/system/sbom`, and `/system/platform-summary`, while `/system/status` lives in `kanban/api/v1/system_status.py`.
  - Fail-closed `nsjail` gating in `kanban/custom_fields/service.py` (`assert_tier_available` lines 59-78, `create_definition` lines 218-222, `update_definition` lines 380-385) and `kanban/api/v1/custom_field_execution.py` (`test_execute_custom_field` lines 240-243) rejects `tier="nsjail"` in Standalone mode with HTTP 422 `SANDBOX_UNAVAILABLE_IN_STANDALONE`, while permitting non-tier metadata edits on pre-existing `nsjail` definitions.
  - `tier_b_runner` wiring in `kanban/api/v1/custom_field_execution.py` (lines 77-80, 126-129, 273-276) passes `getattr(request.app.state, "tier_b_runner", None)` to `CustomFieldExecutor`, and `kanban/app.py` (lines 411-415) initializes `app.state.tier_b_runner = TierBNsjailRunner()` and `app.state.tier_b_sandbox_available`.
  - Built-in `echo_cvss.wasm` fallback in `kanban/custom_fields/builtin_wasm.py` (`resolve_wasm_module_bytes`) resolves `cvss-score` / `wasm:echo_cvss` on fresh workspaces without DB rows, confirmed by `live-desktop-test-exec.png` and `live-fullstack-proof.txt` (`POST .../test-execute` -> HTTP 200, `8.8 High`).
  - Dark mode selection contrast in `theme.css` (lines 89-90) and `custom-fields.css` (lines 407-420) resolves `.custom-fields-def-item--selected` to dark blue background with crisp white text (`live-desktop-dark.png`).
- **Challenged**:
  - Both `api-specialist-review.md` and `ui-specialist-review.md` issued `STATUS: APPROVED` despite visible UI layout/badge regressions in the screenshots, a broken copy-paste formula in `Guide-Custom-Fields.md` Example 3, a broken `STARTER_TEMPLATES.wasm` test-execute path, and stale/inaccurate symbol and build metric citations across the QA packet.
  - `api-specialist-review.md` (lines 25, 115) cites a non-existent function `load_builtin_wasm_module(module_name)` (actual symbol is `resolve_wasm_module_bytes`) and quotes stale pre-RC1 static gate metrics (`1942 files`, `1115 source files`, `1.48s` build) that do not match `build-or-typecheck.txt` (`1945 files`, `1121 source files`, `1.80s` build).
  - `message-to-reality-checker.md` (line 37) cites non-existent method `evaluate_field_definition` (actual method is `execute_for_issue`) and previously referenced `field-tier-select` (actual `data-testid` is `execution-tier-select`).
  - `ui-specialist-review.md` (line 92) reports `95.69%` TypeScript branch coverage, whereas `unit-test-results.txt` (line 66) reports `95.65%`.
  - `unit-test-results.txt` and `build-or-typecheck.txt` were generated in worktree `swarm-b-kan32-rc1-a2aa76a8` on branch `fix/KAN-32-rc1`, whereas `live-fullstack-proof.txt` and specialist reviews reference `main` commit `837f657d`, and `changed-files-manifest.txt` only lists 18 RC1 delta files rather than all KAN-32 files.

## 📸 Complete System Evidence
**Visual Documentation**:
- Full system screenshots:
  - `docs/qa/KAN-32/screenshots/live-desktop-light.png` (1440x900 Desktop Light, `/projects/SEC2/settings/custom-fields`)
  - `docs/qa/KAN-32/screenshots/live-desktop-dark.png` (1440x900 Desktop Dark, scrolled to script editor, Test Execute, and Escalation panel)
  - `docs/qa/KAN-32/screenshots/live-desktop-test-exec.png` (1440x900 Desktop Light, scrolled to Test Execute result and Escalation panel)
  - `docs/qa/KAN-32/screenshots/live-tablet.png` (768x1024 Tablet Light)
  - `docs/qa/KAN-32/screenshots/live-mobile.png` (390x844 Mobile Light)
  - `docs/qa/KAN-32/screenshots/live-guide-custom-fields-desktop-light.png` (Desktop Light full-page capture of `/docs/Guide-Custom-Fields`)
- User journey evidence: Partial; shows Custom Fields Studio loaded with saved `cvss-score` preset, Test Execute output in light and dark modes, tablet/mobile responsive views, and the published Docs guide. Missing screenshots for: `+ New Field` empty/preset gallery view showing `FlavorDecisionMatrix` and disabled `nsjail` presets, `Advanced` tab showing `execution-tier-select`, pre-existing `nsjail` warning banner, and a long unbroken log line inside `pre.custom-field-test-logs`.
- Cross-browser comparison: Chromium/Playwright only (no Firefox or WebKit captures).

**What System Actually Delivers**:
- **Visual Quality**:
  - `live-desktop-dark.png` confirms `.custom-fields-def-item--selected` now renders with dark translucent blue fill (`rgba(37, 99, 235, 0.25)`) and legible white text (`CVSS 3.1 / 4.0 Score`), fixing the light-blue bleed defect.
  - However, `live-desktop-light.png`, `live-desktop-dark.png`, `live-desktop-test-exec.png`, `live-tablet.png`, and `live-mobile.png` ALL visually expose a major form-field sizing defect: `.custom-field-input`, `.custom-field-select`, and `.custom-field-textarea` share `min-height: 140px` (`custom-fields.css` lines 543-557). Consequently, single-line text inputs (`Field Name`, `Identifier Slug`, `Test With Issue Key`) and `<select>` dropdowns (`Field Flavor`, `Output Format`) render as bloated 140px-tall boxes with massive empty whitespace below single lines of text.
  - In `live-desktop-light.png`, the `Multi-Container Compose Required` warning badge (`flavor-nsjail-disabled-badge`) renders unconditionally directly underneath `Field Flavor` even when `WebAssembly (Tier A sandboxed...)` is selected, visually implying that WebAssembly requires Multi-Container Compose.
  - In `live-desktop-test-exec.png` and `live-desktop-dark.png`, `Rendered Output Pill` displays `"8.8 8.8 High"` (duplicate `8.8` score) because `CustomFieldValue.tsx` (lines 364-365) renders `{displayScore}` next to `{displayLabel}` when `echo_cvss.wasm` returns `{"level": "high", "score": 8.8, "label": "8.8 High"}`.
  - In `live-desktop-test-exec.png`, `Truncated Logs:` shows 3 short lines (`Draft test execution on SEC2-3 (flavor=wasm)`, `Executed Wasm module: fuel=7`, `Success: validated format severity_pill`); no long unbroken log line is shown in the screenshot to visually demonstrate wrapping (though CSS properties on `pre.custom-field-test-logs` in `custom-fields.css` lines 990-1007 are correctly set to `white-space: pre-wrap; overflow-wrap: anywhere; word-break: break-all;`).
- **Actual vs. Claimed Functionality**:
  - Standalone `nsjail` gating, `tier_b_runner` wiring, and `cvss-score` preset execution work as evidenced in `live-fullstack-proof.txt` and `test_standalone_nsjail_gate.py` / `test_builtin_wasm_preset.py`.
  - Selecting `Field Flavor -> WebAssembly` manually in `CustomFieldDefinitionEditor.tsx` (without the `cvss-score` preset) populates `STARTER_TEMPLATES.wasm` (`// WebAssembly Tier A Module (Base64)\n<DEFAULT_WASM_BASE64>`), which fails `Test Execute` with HTTP 404 `WASM_MODULE_NOT_FOUND` on a fresh workspace because `builtin_wasm.py` line 141-142 requires `has_preset_name` to be true when `allow_raw_bytecode=False`.
  - `Guide-Custom-Fields.md` renders cleanly at `/docs/Guide-Custom-Fields` (`live-guide-custom-fields-desktop-light.png`), but Example 3 (`CVSS Severity Pill`, lines 93-111) instructs users to return a string (`'CRITICAL'`, `'HIGH'`, etc.) for `severity_pill`, which fails server validation (`output_formats.py` lines 335-345 strictly require a dict `{"level": ...}`).

## 🧪 Integration Testing Results
**End-to-End User Journeys**: **NEEDS WORK / PARTIAL FAIL**
- **Journey 1 - Standalone API Gate & Built-in Preset Flow**: **PASS** (`live-fullstack-proof.txt` confirms `GET /api/v1/system/status` 200 in 6ms, `POST .../custom-fields` (`nsjail`) 422, `POST .../test-execute` (`nsjail`) 422, `cvss-score` preset save 201 in 61ms, `test-execute` 200 in 62ms, `GET /api/v1/issues/SEC2-3/custom-fields` 200 in 30ms, 0 console/page/5xx errors).
- **Journey 2 - Manual WebAssembly Flavor Creation & Test Execute**: **FAIL (by code inspection)** (`CustomFieldDefinitionEditor.tsx:65-73` + `builtin_wasm.py:141-151` + `custom_field_execution.py:251` -> 404 `WASM_MODULE_NOT_FOUND` on fresh workspace because comment lacks `echo_cvss`).
- **Journey 3 - Custom Fields Guide Example 3 Copy-Paste Walkthrough**: **FAIL (by code inspection)** (`Guide-Custom-Fields.md:93-111` + `output_formats.py:335-345` -> HTTP 422 `SCRIPT_OUTPUT_SCHEMA_INVALID: Expected dict for 'severity_pill' output format, got str`).

**Cross-Device Consistency**: **PASS WITH VISUAL DEFECTS**
- `live-desktop-light.png` (1440x900), `live-desktop-dark.png` (1440x900), `live-tablet.png` (768x1024, `scrollWidth=768`), and `live-mobile.png` (390x844, `scrollWidth=390`) show responsive stacking and zero horizontal viewport overflow, though the 140px-tall input/select defect affects all viewports.

**Performance Validation**: **PASS (Measured Endpoints)**
- `live-fullstack-proof.txt` reports: `GET /api/v1/system/status` 6ms, `/projects/SEC2/settings/custom-fields` load 819ms, `POST /custom-fields` 61ms, `POST /test-execute` 62ms, `GET /issues/SEC2-3/custom-fields` 30ms, `/docs/Guide-Custom-Fields` load 877ms (all < 1s).

**Specification Compliance**: **FAIL (Partial Gaps)**
- **Required**:
  1. Gate `nsjail` in standalone mode and fix `tier_b_runner` wiring -> **PASS** (`system_status.py`, `service.py`, `custom_field_execution.py`, `app.py`).
  2. Disable/badge unavailable `nsjail` options in UI without breaking valid flavors -> **PARTIAL** (`nsjail` options are disabled/badged, but `flavor-nsjail-disabled-badge` and `tier-nsjail-disabled-badge` render underneath `WebAssembly`/`Scalar`/`Formula` selections in `live-desktop-light.png`, and `STARTER_TEMPLATES.wasm` fails Test Execute).
  3. Publish step-by-step `[Guide] How to Use Custom Fields` with working copy-paste examples -> **PARTIAL** (Guide is published and linked in `_Sidebar.md`, but Example 3 fails `severity_pill` dict validation, line 171 misstates `severity_pill` accepted inputs, and Example 4 lacks script source).

## 📊 Comprehensive Issue Assessment
**Issues from QA Still Present**:
1. **Test Log Visual Proof Gap (`live-desktop-test-exec.png`)**: While `custom-fields.css` lines 990-1007 adds `white-space: pre-wrap; overflow-wrap: anywhere; word-break: break-all;` and `live-fullstack-proof.txt` checks `scrollWidth === clientWidth` (742), `live-desktop-test-exec.png` only shows 3 short log lines and does not visually prove wrapping of an unbroken long log line.

**New Issues Discovered**:
1. **Critical / Functional - Guide Example 3 Breaks When Copy-Pasted (`Guide-Custom-Fields.md` lines 93-111, 171 vs `kanban/custom_fields/output_formats.py` lines 335-345)**: Example 3 (`CVSS Severity Pill`) returns a bare string (`'CRITICAL'`, `'HIGH'`, `'MEDIUM'`, `'LOW'`), and Section 4 item 4 (`severity_pill`) claims it accepts `NONE` or numeric CVSS scores `0.0` to `10.0`. `_validate_severity_pill` strictly requires a dict with `"level"` in `("low", "medium", "high", "critical")` and rejects strings, `"NONE"`, and numbers with HTTP 422.
2. **Critical / Functional - `STARTER_TEMPLATES.wasm` Fails Test Execute on Fresh Workspace (`CustomFieldDefinitionEditor.tsx` lines 65-73 vs `builtin_wasm.py` lines 141-151)**: Selecting `Field Flavor -> WebAssembly` populates `// WebAssembly Tier A Module (Base64)\n<DEFAULT_WASM_BASE64>`, which lacks `echo_cvss` in comments; `resolve_wasm_module_bytes` (`allow_raw_bytecode=False` during `test-execute`) requires `has_preset_name` even when `computed_sha` matches `BUILTIN_STARTER_WASM_BY_SHA`, causing HTTP 404 `WASM_MODULE_NOT_FOUND`.
3. **Medium / Visual UX - 140px Oversized `<input>` and `<select>` Controls (`custom-fields.css` lines 543-557)**: Sharing `min-height: 140px;` across `.custom-field-input, .custom-field-select, .custom-field-textarea` stretches single-line inputs (`Field Name`, `Identifier Slug`, `Test With Issue Key`) and `<select>` elements (`Field Flavor`, `Output Format`) to 140px tall across all 5 editor screenshots (`live-desktop-light.png`, `live-desktop-dark.png`, `live-desktop-test-exec.png`, `live-tablet.png`, `live-mobile.png`).
4. **Medium / Visual UX - Ambiguous `Multi-Container Compose Required` Badge Placement (`CustomFieldDefinitionEditor.tsx` lines 894-901, 1156-1163; `live-desktop-light.png`)**: The badge renders unconditionally below `Field Flavor` and `Execution Sandbox` whenever `!isTierBAvailable`, even when `WebAssembly` is selected, without specifying that it refers to `nsjail` (`nsjail options require Multi-Container Compose`).
5. **Medium / Security & Override Consistency (`builtin_wasm.py` lines 212-214)**: Comment-only `// echo_cvss.wasm` bypasses the workspace `ApprovedWasmModule` DB override check, unlike `wasm:echo_cvss` or bytecode-with-comment paths.
6. **Low / Visual Polish (`live-desktop-test-exec.png`, `live-desktop-dark.png`, `CustomFieldValue.tsx` lines 364-365)**: Pill renders `"8.8 8.8 High"` (duplicate `8.8`) because `echo_cvss.wasm` sets `"label": "8.8 High"` while `CustomFieldValue.tsx` prepends `{displayScore}`.
7. **Low / Documentation & QA Packet Integrity**:
   - `Guide-Custom-Fields.md` Example 4 (lines 113-129) omits a script/bytecode block.
   - `api-specialist-review.md` cites non-existent `load_builtin_wasm_module` and stale pre-RC1 counts (`1942 files`, `1115 source files`, `1.48s`); `message-to-reality-checker.md` cites non-existent `evaluate_field_definition` and `field-tier-select`; `ui-specialist-review.md` cites `95.69%` branch coverage vs `95.65%` in `unit-test-results.txt`.
   - `unit-test-results.txt` and `build-or-typecheck.txt` were captured in worktree `swarm-b-kan32-rc1-a2aa76a8` (`fix/KAN-32-rc1`) rather than on `main` (`837f657d`), and only scoped pytest/vitest subsets were executed (no full-repo test run).

## 🎯 Realistic Quality Certification
**Overall Quality Rating**: B-
**Design Implementation Level**: Good (core backend gating, `tier_b_runner` wiring, dark-mode contrast, and built-in `cvss-score` preset work, but UI form sizing, badge clarity, and guide accuracy need remediation)
**System Completeness**: 82%
**Production Readiness**: NEEDS WORK

## 🔄 Deployment Readiness Assessment
**Status**: NEEDS WORK

**Required Fixes Before Production**:
1. Fix `thumbs-up-kanban.wiki/Guide-Custom-Fields.md` Example 3 (lines 93-111) to return a valid `severity_pill` dict (e.g., `{"level": "critical", "score": 9.5, "label": "Critical"}` ...) and align Section 4 item 4 (line 171) with `_validate_severity_pill` (`output_formats.py` lines 335-345), plus add a runnable script/module snippet to Example 4.
2. Fix `custom-fields.css` lines 543-557 so `min-height: 140px;` applies only to `.custom-field-textarea` (not `.custom-field-input` or `.custom-field-select`), eliminating the 140px-tall single-line fields visible in `live-desktop-light.png`, `live-desktop-test-exec.png`, `live-tablet.png`, and `live-mobile.png`.
3. Fix `CustomFieldDefinitionEditor.tsx` (lines 65-73, 894-901, 1156-1163) and `builtin_wasm.py` (lines 141-151, 212-214):
   - Either allow `computed_sha in BUILTIN_STARTER_WASM_BY_SHA` in `_resolve_by_bytecode` regardless of comment text (after checking DB override) or include `echo_cvss.wasm` / `wasm:echo_cvss` in `STARTER_TEMPLATES.wasm` so manual WebAssembly selection passes `Test Execute`.
   - Ensure comment-only `echo_cvss` checks workspace `ApprovedWasmModule` DB overrides first.
   - Clarify the `Multi-Container Compose Required` badge text (e.g., `nsjail requires Multi-Container Compose`) or display it specifically when `nsjail` is referenced so it does not appear attached to `WebAssembly` in `live-desktop-light.png`.
4. Re-capture fresh evidence on the target branch/commit (including `+ New Field` preset gallery/matrix view, `Advanced` tab, and a long unbroken log line in `live-desktop-test-exec.png`) and reconcile `api-specialist-review.md`, `ui-specialist-review.md`, `message-to-reality-checker.md`, and `changed-files-manifest.txt` with exact symbols and command outputs.

**Timeline for Production Readiness**: 1 short revision cycle (estimated 2-4 hours for fixes, unit tests, static checks, and fresh live-stack screenshots)
**Revision Cycle Required**: YES

## 📈 Success Metrics for Next Iteration
**What Needs Improvement**:
- Copy-paste guide accuracy against live backend Pydantic schemas (`Guide-Custom-Fields.md` Example 3 & 4).
- Form control heights (`.custom-field-input`, `.custom-field-select`) and unambiguous standalone `nsjail` badging in `CustomFieldDefinitionEditor.tsx`.
- Alignment between `STARTER_TEMPLATES.wasm` and `builtin_wasm.py` plus DB override consistency.
- Exact consistency across `docs/qa/KAN-32/` artifacts (commit SHA, symbol names, coverage percentages, and complete manifest).

**Quality Targets**:
- 100% of copy-paste examples in `Guide-Custom-Fields.md` validated against `output_formats.py` and `test-execute`.
- Single-line inputs/selects rendered at standard control height (~36-40px) across desktop, tablet, and mobile.
- `>=95%` unit test coverage preserved with zero ruff/mypy/tsc/eslint/dash-guard errors.

**Evidence Requirements**:
- Updated `live-desktop-light.png` showing normal-height inputs/selects and unambiguous `nsjail` badge wording.
- Updated `live-desktop-test-exec.png` showing a long unbroken log line wrapping cleanly inside `pre.custom-field-test-logs`.
- Screenshot or Playwright proof of `+ New Field` (`FlavorDecisionMatrix` + `PresetGallery`) and `Advanced` tab in Standalone mode.
- Pytest + live-stack verification of Guide Example 3 formula and manual WebAssembly `STARTER_TEMPLATES.wasm` Test Execute returning HTTP 200.

---
**Integration Agent**: RealityIntegration
**Assessment Date**: 2026-11-20
**Evidence Location**: docs/qa/KAN-32/
**Re-assessment Required**: After fixes implemented
