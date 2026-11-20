# Reality-Checker Verification Packet: KAN-32 (RC1 Fixes)

**Ticket ID:** KAN-32  
**Title:** [KB-P3-AUDIT-26] Gate Custom Fields nsjail Sandbox in Standalone Mode, Fix tier_b_runner Wiring, Publish Step-by-Step [Guide] How to Use Custom Fields, and Resolve Dark Mode Contrast and Built-in Wasm Fallback (RC1)  
**Branch:** `fix/KAN-32-rc1`  

---

## 1. Executive Summary and Verification Proof

This packet provides forensic verification for ticket KAN-32 and its Release Candidate 1 (RC1) remediation addressing live QA findings from `docs/qa/KAN-32/live-fullstack-proof.txt`.

All defects identified in live zero-mock stack testing have been resolved, verified with unit test suites (>=95% coverage), validated against all static quality gates, and authored with zero em-dashes and zero en-dashes.

### RC1 Defect 1: Dark Mode WCAG Contrast Fix in Custom Fields Studio
- **Defect:** In Dark Mode (`[data-theme="dark"]`), `.custom-fields-def-item--selected` in `kanban/web/src/features/custom-fields/custom-fields.css` hardcoded light-theme colors (`background-color: #eff6ff; border-color: #bfdbfe;`) while inheriting dark-mode white `var(--fg-primary)` text. This created unreadable white-on-light-blue text in dark mode (`live-desktop-dark.png`).
- **Remediation:**
  * Added canonical semantic dark-aware CSS tokens in `kanban/web/src/styles/theme.css`: `--bg-accent-subtle`, `--bg-surface-selected`, and `--border-accent-subtle` defined across `:root`, `[data-theme="dark"]`, and `@media (prefers-color-scheme: dark)`.
  * Updated `kanban/web/src/features/custom-fields/custom-fields.css` to use semantic CSS variables for `.custom-fields-def-item--selected` (`background-color: var(--bg-surface-selected); border-color: var(--border-accent-subtle); color: var(--fg-primary);`) and explicit dark theme rules (`[data-theme="dark"] .custom-fields-def-item--selected`).
  * Replaced all legacy hardcoded hex backgrounds across `custom-fields.css` with semantic theme tokens.
  * Verified 100% token resolution and zero regressions via `cssTokensAudit.test.ts` (4/4 passing).

### RC1 Defect 2: Horizontal Log Overflow Fix in Test Execute Card
- **Defect:** `pre.custom-field-test-logs` overflowed horizontally beyond its card border on long log output lines (`live-desktop-test-exec.png`).
- **Remediation:**
  * Updated `kanban/web/src/features/custom-fields/custom-fields.css` for `pre.custom-field-test-logs` and `.custom-field-logs` with `white-space: pre-wrap; overflow-wrap: anywhere; word-break: break-word; max-width: 100%; box-sizing: border-box;`.
  * Logs wrap cleanly within their card container without horizontal distortion.

### RC1 Defect 3: Built-In Starter Preset echo_cvss.wasm Resolution Out-of-the-Box
- **Defect:** On a fresh project with zero rows in `approved_wasm_modules`, clicking "Use Preset" on `cvss-score` (`wasm`) and clicking "Test Execute" returned HTTP `404 WASM_MODULE_NOT_FOUND` unless `echo_cvss.wasm` had been manually uploaded first.
- **Remediation:**
  * Created `kanban/custom_fields/builtin_wasm.py` exporting built-in starter preset bytecode (`ECHO_CVSS_WASM_BYTES`, `ECHO_CVSS_SHA256_BYTES`, `ECHO_CVSS_SHA256_HEX`) and module resolver `resolve_wasm_module_bytes`.
  * `resolve_wasm_module_bytes` resolves Wasm modules seamlessly:
    1. Workspace DB check (`ApprovedWasmModule`) runs first. If a workspace administrator has uploaded an explicit module with matching name or sha256, the DB row overrides the built-in module.
    2. If no DB row exists, starter presets (`echo_cvss`, `echo_cvss.wasm`, `cvss-score`, or script source with comments referencing `echo_cvss`) resolve directly to the embedded binary.
    3. Untrusted, unattributed bytecode continues to be strictly gated and rejected with HTTP 404 or 422 to preserve security invariants.
  * Updated `kanban/custom_fields/executor.py` (`evaluate_field_definition` and `test_execute`) and `kanban/api/v1/custom_field_execution.py` (`test_execute_custom_field`) to route through `resolve_wasm_module_bytes`.
  * Added comprehensive test suite `kanban/tests/custom_fields/test_builtin_wasm_preset.py` (7 tests, 100% coverage on `builtin_wasm.py`) verifying name resolution, sha256 resolution, comments resolution, workspace DB override, error conditions, and end-to-end HTTP 200 OK test-execute on fresh projects.

---

## 2. Test Suite and Coverage Evidence

### Python Pytest and Coverage
Command:
```bash
KB_TEST_PGSOCKET_DIR=/tmp/kb-pgsock-b-kan32 KB_TEST_PGHOST=/tmp/kb-pgsock-b-kan32 uv run pytest \
  kanban/tests/custom_fields/test_standalone_nsjail_gate.py \
  kanban/tests/custom_fields/test_custom_fields_api.py \
  kanban/tests/custom_fields/test_execution_api.py \
  kanban/tests/custom_fields/test_manifest_and_formula_security.py \
  kanban/tests/custom_fields/test_builtin_wasm_preset.py \
  --cov=kanban.custom_fields.service \
  --cov=kanban.custom_fields.builtin_wasm \
  --cov=kanban.api.v1.custom_field_execution \
  --cov=kanban.api.v1.custom_fields \
  --cov-report=term-missing
```

Results:
- **Test Files:** 5 passed (5 total)
- **Tests:** 33 passed (33 total)
- **Pass Rate:** 100%

| Module Name | Stmts | Miss | Branch | BrPart | Cover | Missing Lines |
| :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| `kanban/custom_fields/builtin_wasm.py` | 77 | 0 | 30 | 0 | **100%** | None |
| `kanban/api/v1/custom_fields.py` | 30 | 0 | 0 | 0 | **100%** | None |
| `kanban/custom_fields/service.py` | 163 | 0 | 42 | 2 | **99%** | 355->359, 361->365 |
| `kanban/api/v1/custom_field_execution.py` | 99 | 0 | 18 | 2 | **98%** | 71->74, 109->125 |
| **TOTAL** | **369** | **0** | **90** | **4** | **99%** | |

### TypeScript Vitest and Coverage
Command:
```bash
COVERAGE_INCLUDE="src/features/custom-fields/CustomFieldDefinitionEditor.tsx,src/features/custom-fields/PresetGallery.tsx,src/features/custom-fields/FlavorDecisionMatrix.tsx,src/app/useSystemStatus.ts" \
pnpm --filter @kanban/web test:coverage src/features/custom-fields src/app/useSystemStatus.test.tsx
```

Results:
- **Test Files:** 10 passed (10 total)
- **Tests:** 165 passed (165 total)
- **Pass Rate:** 100%

| File | % Stmts | % Branch | % Funcs | % Lines |
| :--- | :---: | :---: | :---: | :---: |
| **All files** | **100%** | **95.65%** | **100%** | **100%** |
| `src/app/useSystemStatus.ts` | 100% | 100% | 100% | 100% |
| `src/features/custom-fields/CustomFieldDefinitionEditor.tsx` | 100% | 95.74% | 100% | 100% |
| `src/features/custom-fields/FlavorDecisionMatrix.tsx` | 100% | 92.30% | 100% | 100% |
| `src/features/custom-fields/PresetGallery.tsx` | 100% | 96.87% | 100% | 100% |

### CSS Tokens and Theme Audit
Command:
```bash
(cd kanban/web && npx vitest run src/styles/__tests__/cssTokensAudit.test.ts)
```
Results:
- **Passed:** 4/4 tests passed (100% token resolution, 0 missing variables, 0 inline JSX style regressions).

---

## 3. Mandatory Static Quality Gates

All 7 mandatory checks execute cleanly with zero errors and zero warnings:

1. **Ruff Check:** Passed (`uv run ruff check .` -> `All checks passed!`).
2. **Ruff Format Check:** Passed (`uv run ruff format --check .` -> `1945 files already formatted`).
3. **Mypy Typecheck:** Passed (`uv run mypy` -> `Success: no issues found in 1121 source files`).
4. **Lint-Imports Architectural Boundary Gate:** Passed (`Contracts: 2 kept, 0 broken`).
5. **TypeScript Compiler and Vite Build:** Passed (`pnpm --filter @kanban/web build` -> `tsc -b && vite build` built in 1.80s).
6. **ESLint:** Passed (`pnpm --filter @kanban/web lint` -> `eslint . --max-warnings 0` with 0 warnings/errors).
7. **No Dashes Guard:** Passed (`python3 -m scripts.check_no_dashes --all` -> strictly 0 em/en-dashes).

---

## 4. Manifest of Forensic Artifacts

- `docs/qa/KAN-32/unit-test-results.txt`: Verbatim pytest and vitest test execution logs and coverage tables.
- `docs/qa/KAN-32/build-or-typecheck.txt`: Verbatim outputs of ruff, mypy, lint-imports, tsc, eslint, check_no_dashes, and cssTokensAudit.
- `docs/qa/KAN-32/git-diff.patch`: Scoped patch containing all changes on `fix/KAN-32-rc1` relative to `main` (`b3b0f4ba`).
- `docs/qa/KAN-32/live-fullstack-proof.txt`: Raw evidence log from zero-mock live stack verification.
- `docs/qa/KAN-32/changed-files-manifest.txt`: List of all modified and created files.
- `docs/qa/KAN-32/message-to-reality-checker.md`: This forensic audit document.
