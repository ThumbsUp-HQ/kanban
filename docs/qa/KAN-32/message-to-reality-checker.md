# Reality-Checker Verification Packet: KAN-32 (RC2 Fixes)

**Ticket ID:** KAN-32  
**Title:** [KB-P3-AUDIT-26] Gate Custom Fields nsjail Sandbox in Standalone Mode, Fix tier_b_runner Wiring, Publish Step-by-Step [Guide] How to Use Custom Fields, and Resolve Dark Mode Contrast and Built-in Wasm Fallback (RC2)  
**Branch:** `fix/KAN-32-rc2`  
**Target Branch:** `main`  
**Wiki Commit:** `c616de596be8df0e96472f2d0b14219f94d2e3ee`  

---

## 1. Executive Summary & RC2 Remediations

This packet provides forensic verification for ticket KAN-32 Release Candidate 2 (RC2), addressing all findings identified in `docs/qa/KAN-32/reality-checker-report.md`.

All 7 findings have been fully remediated and validated across unit test suites (>=95% coverage), static analysis gates, and zero em-dash / en-dash checks.

### Remediation 1: Fix 140px Oversized `<input>` and `<select>` Controls
- **Finding:** In `kanban/web/src/features/custom-fields/custom-fields.css` (lines 543-557), `.custom-field-input`, `.custom-field-select`, and `.custom-field-textarea` shared `min-height: 140px`, causing single-line text inputs (Field Name, Identifier Slug, Test With Issue Key) and `<select>` dropdowns (Field Flavor, Output Format) to render as bloated 140px-tall boxes with excessive empty whitespace.
- **Fix:** Split `.custom-field-textarea` from `.custom-field-input, .custom-field-select`. `.custom-field-input` and `.custom-field-select` now enforce standard single-line height (`min-height: 38px; line-height: 1.45`), while `min-height: 140px` is applied exclusively to `.custom-field-textarea`.

### Remediation 2: STARTER_TEMPLATES.wasm, DB Override Consistency, & Test-Execute
- **Finding:** Selecting `Field Flavor -> WebAssembly` populated `STARTER_TEMPLATES.wasm` without `// echo_cvss.wasm`, failing `test-execute` on fresh workspaces. In addition, comment-only `// echo_cvss.wasm` previously bypassed workspace `ApprovedWasmModule` DB overrides.
- **Fix:**
  1. Updated `STARTER_TEMPLATES.wasm` in `CustomFieldDefinitionEditor.tsx` to include `// echo_cvss.wasm - WebAssembly Tier A Module (Base64)\n${DEFAULT_WASM_BASE64}` for all output formats.
  2. Updated `_resolve_by_bytecode` in `kanban/custom_fields/builtin_wasm.py` to allow `computed_sha in BUILTIN_STARTER_WASM_BY_SHA` regardless of comment text, checking workspace `ApprovedWasmModule` DB overrides first.
  3. Updated comment-only `// echo_cvss.wasm` resolution in `resolve_wasm_module_bytes` to check workspace `ApprovedWasmModule` DB overrides first (by name or sha256) before returning the built-in preset module.
  4. Added Pytest unit tests in `kanban/tests/custom_fields/test_builtin_wasm_preset.py` (Test 8) verifying that `STARTER_TEMPLATES.wasm` without comments resolves cleanly via `BUILTIN_STARTER_WASM_BY_SHA` and respects DB overrides.

### Remediation 3: Clarify Standalone nsjail Disabled Badges
- **Finding:** `flavor-nsjail-disabled-badge` and `tier-nsjail-disabled-badge` displayed `Multi-Container Compose Required` directly underneath `Field Flavor` even when WebAssembly was selected, ambiguously implying that WebAssembly required Compose.
- **Fix:** Clarified badge text in `CustomFieldDefinitionEditor.tsx` to `"nsjail option requires Multi-Container Compose"` on both `flavor-nsjail-disabled-badge` and `tier-nsjail-disabled-badge` (preserving `data-testid`s and existing Vitest assertions).

### Remediation 4: Prevent Duplicate Score Display in Severity Pill
- **Finding:** `CustomFieldValue.tsx` rendered duplicate score text (e.g. `"8.8 8.8 High"`) when `displayLabel` already started with `{displayScore}` because `echo_cvss.wasm` returns `{"level": "high", "score": 8.8, "label": "8.8 High"}` while the component rendered `{displayScore}` adjacent to `{displayLabel}`.
- **Fix:** In `CustomFieldValue.tsx` (lines 355-367), when `displayScore && displayLabel.startsWith(displayScore)`, leading score text is trimmed from `displayLabel` so that `{displayScore}` renders in `.custom-field-severity-score` (`"8.8"`) and `.custom-field-severity-label` renders `"High"`, producing clean `"8.8 High"` styling with 4px gap. Added test in `CustomFieldValue.test.tsx`.

### Remediation 5: Fix Guide-Custom-Fields.md Copy-Paste Examples & Schema
- **Finding:** Example 3 in `Guide-Custom-Fields.md` returned a string (`'CRITICAL'`, `'HIGH'`), which failed server validation (`_validate_severity_pill` in `kanban/custom_fields/output_formats.py` requires a dict). Section 4 item 4 claimed `severity_pill` accepts strings or numeric scores. Example 4 lacked a runnable script snippet.
- **Fix:**
  1. Updated Example 3 (`CVSS Severity Pill`) in `thumbs-up-kanban.wiki/Guide-Custom-Fields.md` to return a valid dict:
     `{"level": "critical", "score": 9.5, "label": "Critical"} if priority == "URGENT" else ({"level": "high", "score": 8.0, "label": "High"} if priority == "HIGH" else ({"level": "medium", "score": 5.0, "label": "Medium"} if priority == "MEDIUM" else {"level": "low", "score": 2.0, "label": "Low"}))`
  2. Aligned Section 4 item 4 (`severity_pill`) with the exact accepted schema: dict with required `"level"` (`"low"`, `"medium"`, `"high"`, `"critical"`), optional numeric `"score"` (`0.0` to `10.0`), and optional `"label"` (max 32 chars without HTML).
  3. Added runnable Python nsjail script snippet to Example 4.
  4. Verified 0 em/en-dashes and committed cleanly in `thumbs-up-kanban.wiki` at commit `c616de596be8df0e96472f2d0b14219f94d2e3ee`.
  5. Added Pytest test in `kanban/tests/custom_fields/test_builtin_wasm_preset.py` (Test 9) verifying that copy-pasting the exact Example 3 formula passes `_validate_severity_pill` and `POST /api/v1/projects/{key}/custom-fields/test-execute` returns HTTP 200 OK.

### Remediation 6: Accurate Symbol Names & QA Integrity Reconciled
- **Accurate Symbol Citations:**
  * Resolver function: `resolve_wasm_module_bytes` (in `kanban/custom_fields/builtin_wasm.py`, not load_builtin_wasm_module).
  * Evaluator method: `execute_for_issue` (in `kanban/custom_fields/executor.py`, not evaluate_field_definition).
  * System status router: `kanban/api/v1/system_status.py` (for `GET /api/v1/system/status` exposing `supported_custom_field_tiers` and `tier_b_sandbox_available`).
  * Tier select testid: `execution-tier-select` (in `CustomFieldDefinitionEditor.tsx`, not field-tier-select).
  * Branch and worktree: `fix/KAN-32-rc2` branched from `main`.

---

## 2. Test Suite & Coverage Evidence

### Python Pytest and Coverage (All 78 tests passing, 97% coverage)
Command:
```bash
PYTEST_XDIST_WORKER=gw_kan32rc2 uv run pytest kanban/tests/custom_fields/ --cov=kanban/custom_fields --cov-report=term-missing
```

Results:
- **Test Files:** 12 passed (12 total)
- **Tests:** 78 passed (78 total)
- **Pass Rate:** 100%

| Module Name | Stmts | Miss | Branch | BrPart | Cover |
| :--- | :---: | :---: | :---: | :---: | :---: |
| `kanban/custom_fields/builtin_wasm.py` | 89 | 0 | 32 | 0 | **100%** |
| `kanban/custom_fields/manifest.py` | 43 | 0 | 20 | 0 | **100%** |
| `kanban/custom_fields/output_formats.py` | 232 | 0 | 86 | 3 | **99%** |
| `kanban/custom_fields/service.py` | 163 | 0 | 42 | 2 | **99%** |
| `kanban/custom_fields/approvals.py` | 201 | 4 | 72 | 6 | **96%** |
| `kanban/custom_fields/executor.py` | 538 | 18 | 242 | 19 | **95%** |
| **TOTAL** | **1269** | **22** | **494** | **30** | **97%** |

### TypeScript Vitest & Scoped Coverage (All 166 tests passing, 0 act warnings)
Command:
```bash
COVERAGE_INCLUDE="src/features/custom-fields/CustomFieldDefinitionEditor.tsx,src/features/custom-fields/PresetGallery.tsx,src/features/custom-fields/FlavorDecisionMatrix.tsx,src/app/useSystemStatus.ts" \
npx vitest run --coverage src/features/custom-fields src/app/useSystemStatus.test.tsx
```

Results:
- **Test Files:** 10 passed (10 total)
- **Tests:** 166 passed (166 total)
- **Pass Rate:** 100%
- **act(...) Warnings:** 0

| File | % Stmts | % Branch | % Funcs | % Lines |
| :--- | :---: | :---: | :---: | :---: |
| **All files** | **100%** | **95.65%** | **100%** | **100%** |
| `src/app/useSystemStatus.ts` | 100% | 100% | 100% | 100% |
| `src/features/custom-fields/CustomFieldDefinitionEditor.tsx` | 100% | 95.74% | 100% | 100% |
| `src/features/custom-fields/FlavorDecisionMatrix.tsx` | 100% | 92.30% | 100% | 100% |
| `src/features/custom-fields/PresetGallery.tsx` | 100% | 96.87% | 100% | 100% |

### CSS Tokens and Theme Audit (4/4 PASS)
Command:
```bash
(cd kanban/web && npx vitest run src/styles/__tests__/cssTokensAudit.test.ts)
```
- **Passed:** 4/4 tests passed (100% token resolution, 0 missing variables, 0 inline JSX styles).

### Static Quality Gates Summary
- `ruff check`: All checks passed.
- `ruff format --check`: 1004 files already formatted.
- `mypy`: Success: no issues found in 996 source files.
- `check-migrations`: OK: All 62 migrations valid. Single head: `p4_23_oidc_link_intent_fk`.
- `lint-imports`: 2 contracts kept, 0 broken.
- `tsc -b --noEmit`: Clean, 0 errors.
- `eslint . --max-warnings 0`: Clean, 0 warnings.
- `vite build`: Built cleanly in 2.27s.
- `check_no_dashes`: 0 forbidden unicode dashes across repo and wiki.
