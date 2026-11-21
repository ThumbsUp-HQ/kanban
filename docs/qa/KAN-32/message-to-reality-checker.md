# Reality-Checker Verification Packet: KAN-32 (Round 3 Live Full-Stack Verification)

**Ticket ID:** KAN-32  
**Title:** [KB-P3-AUDIT-26] Gate Custom Fields nsjail Sandbox in Standalone Mode, Fix tier_b_runner Wiring, Publish Step-by-Step [Guide] How to Use Custom Fields, and Resolve Dark Mode Contrast and Built-in Wasm Fallback  
**Branch:** `main` (commit `78074a1d`)  
**Container Environment:** `http://127.0.0.1:18961` (container: `kanban-liveqa-1`)  
**Live Stack Status:** `OVERALL LIVE_STACK_VERDICT: PASS`  
**Wiki Commit:** `c616de596be8df0e96472f2d0b14219f94d2e3ee`  

---

## 1. Executive Summary & Verification Highlights

This packet provides comprehensive forensic verification for ticket **KAN-32** on `main` at commit `78074a1d`, incorporating empirical results from zero-mock Live Full-Stack QA against isolated container `kanban-liveqa-1` (`http://127.0.0.1:18961`, PostgreSQL 16 + FORCE RLS).

All forensic requirements and audit findings have been fully remediated and verified:
1. **Unbroken 220-Char Formula Wrapping & (tier=wasm) Log Verification:**
   - 220-char unbroken formula log cleanly wraps inside `.custom-field-test-result` (`resultScrollWidth=768 == resultClientWidth=768`, `resultFitsCard=true`), `[data-testid="test-output-pill"]` (`pillScrollWidth=744 == pillClientWidth=744`), and `pre.custom-field-test-logs` (`logsScrollWidth=742 == logsClientWidth=742`, `logsFitsCard=true`, `preOverflowsCard=false`).
   - Test execute log string explicitly outputs `(tier=wasm)` instead of `(flavor=wasm)` (`hasTierWasmLog=true`, `hasLegacyFlavorWasmLog=false`).
   - Screenshot: `docs/qa/KAN-32/screenshots/live-long-log-wrap-light.png`.
2. **Bare Example 3 Formula Copy-Paste & Saved Field List View:**
   - Evaluated bare Example 3 expression from `Guide-Custom-Fields.md` without `"formula: "` prefix: `POST /api/v1/projects/SEC2/custom-fields/test-execute` returned HTTP 200 OK in 10ms with `status="SUCCESS"` and parsed severity pill value `{"level":"low","score":2,"label":"Low"}`.
   - Saved field "Incident Severity Pill" (slug: `incident-severity-pill`): `POST /api/v1/projects/SEC2/custom-fields` returned HTTP 201 Created. Rendered row `[data-testid="field-item-incident-severity-pill"]` in left Custom Fields list alongside selected editor.
   - Screenshot: `docs/qa/KAN-32/screenshots/live-desktop-light.png`.
3. **Control Heights:** Single-line inputs and selects enforce standard single-line height (`min-height: 38px`), while `min-height: 140px` is applied exclusively to `.custom-field-textarea`.
4. **STARTER_TEMPLATES.wasm, DB Override Precedence, & Test-Execute:**
   - Updated `STARTER_TEMPLATES.wasm` in `CustomFieldDefinitionEditor.tsx` to include `// echo_cvss.wasm - WebAssembly Tier A Module (Base64)\n${DEFAULT_WASM_BASE64}`.
   - `_resolve_by_bytecode` in `kanban/custom_fields/builtin_wasm.py` allows `computed_sha in BUILTIN_STARTER_WASM_BY_SHA` regardless of comment text, checking workspace `ApprovedWasmModule` DB overrides first.
   - Comment-only `// echo_cvss.wasm` resolution checks workspace `ApprovedWasmModule` DB overrides first before returning the built-in preset module.
5. **Standalone nsjail Disabled Badges:** Clarified badge text to `"nsjail option requires Multi-Container Compose"`.
6. **Prevent Duplicate Score Display in Severity Pill:** In `CustomFieldValue.tsx`, leading score text is trimmed from `displayLabel` so `{displayScore}` renders in `.custom-field-severity-score` and `.custom-field-severity-label` renders clean label (e.g. `"8.8 High"`).

---

## 2. Test Suite & Coverage Evidence

### Python Pytest and Coverage (All 78 tests passing, 97% coverage)
Command:
```bash
uv run pytest kanban/tests/custom_fields/ --cov=kanban/custom_fields --cov-report=term-missing
```

Results:
- **Test Files:** 12 passed (12 total)
- **Tests:** 78 passed (78 total) in 33.20s
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

### TypeScript Vitest & Scoped Coverage (All 79 tests passing, 0 act warnings)
Command:
```bash
pnpm --dir kanban/web exec vitest run --coverage src/styles/__tests__/cssTokensAudit.test.ts src/features/custom-fields/__tests__/CustomFieldValue.test.tsx src/features/custom-fields/__tests__/CustomFieldDefinitionEditor.test.tsx
```

Results:
- **Test Files:** 3 passed (3 total)
- **Tests:** 79 passed (79 total) in 4.49s
- **Pass Rate:** 100%
- **act(...) Warnings:** 0

| File | % Stmts | % Branch | % Funcs | % Lines |
| :--- | :---: | :---: | :---: | :---: |
| **All files** | **99.73%** | **96.64%** | **100%** | **100%** |
| `CustomFieldDefinitionEditor.tsx` | 100% | 96.07% | 100% | 100% |
| `CustomFieldValue.tsx` | 99.17% | 97.39% | 100% | 100% |
| `cssTokensAudit.test.ts` | 100% | 100% | 100% | 100% |

---

## 3. Static Quality Gates & Invariants Checklist

| Invariant / Check | Command / Tool | Status | Evidence |
| :--- | :--- | :---: | :--- |
| **Database Migrations** | `uv run kanban-ctl db check-migrations` | PASS | 63 migrations valid, single head (`p4_24_agent_safe_sequences`) |
| **Python Linter** | `uv run ruff check .` | PASS | All checks passed across 2023 files |
| **Python Formatter** | `uv run ruff format --check .` | PASS | Clean across 2023 files |
| **Strict Typecheck** | `uv run mypy database kanban mcp agent` | PASS | Success: no issues found in 995 source files |
| **Module Layering** | `uv run lint-imports` | PASS | Contracts: 2 kept, 0 broken (`agent -> mcp -> kanban -> database`) |
| **Web Typecheck** | `pnpm --dir kanban/web run typecheck` | PASS | `tsc -b --noEmit` exited code 0 |
| **Web ESLint** | `pnpm --dir kanban/web run lint` | PASS | `eslint . --max-warnings 0` exited code 0 (0 warnings) |
| **Web Production Build** | `pnpm --dir kanban/web run build` | PASS | Production bundle built in 1.15s |
| **Typography Standards** | `python3 -m scripts.check_no_dashes --all` | PASS | 0 forbidden unicode dashes across repo and wiki |
| **Untracked Hygiene** | `git status` check | PASS | `.backup_schedule.json` and `backups/` untouched |

---

## 4. Artifact Index in `docs/qa/KAN-32/`

- `live-fullstack-proof.txt`: Round 3 live black-box execution telemetry against `kanban-liveqa-1` (`:18961`, commit `78074a1d`)
- `unit-test-results.txt`: Verbatim Pytest (78 passed, 97% coverage) and Vitest (79 passed, 96.64% branch coverage) outputs
- `build-or-typecheck.txt`: Verbatim static check and build outputs
- `api-specialist-review.md`: Dual-specialist API and security audit signoff
- `ui-specialist-review.md`: Dual-specialist UI and layout audit signoff
- `screenshots/live-long-log-wrap-light.png`: Verified wrapping of 220-char unbroken formula log
- `screenshots/live-wiki-example3-test-exec-light.png`: Verified bare Example 3 copy-paste test execute
- `screenshots/live-desktop-light.png`: Distinct list and editor view with saved Incident Severity Pill
