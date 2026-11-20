# Reality-Checker Verification Packet: KAN-32

**Ticket ID:** KAN-32  
**Title:** [KB-P3-AUDIT-26] Gate Custom Fields nsjail Sandbox in Standalone Mode, Fix tier_b_runner Wiring, and Publish Step-by-Step [Guide] How to Use Custom Fields (3 Problems)  
**Branch:** `feat/KAN-32`  

---

## 1. Executive Summary & Verification Proof

All 3 scoped problems for ticket KAN-32 have been fully implemented, verified with automated test suites, checked against strict static gates, and documented without em-dashes or en-dashes.

### Problem 1: Standalone `nsjail` Fail-Closed Gating & Multi-Container `tier_b_runner` Wiring
- Extended `SystemStatusResponse` in `kanban/api/v1/system_status.py` and TypeScript interface `SystemStatus` in `kanban/web/src/app/useSystemStatus.ts` with:
  * `supported_custom_field_tiers`: `["scalar", "formula", "wasm"]` in Standalone mode (`tier_b_sandbox_available == False`), and `["scalar", "formula", "wasm", "nsjail"]` in Multi-Container mode (`tier_b_sandbox_available == True`).
  * `sandbox_unavailable_reason`: Plain ASCII explanation when `tier_b_sandbox_available == False` (`"Isolated nsjail sandbox execution is unavailable in standalone mode. Multi-container compose deployment is required."`), and `None` when `True`.
- In `kanban/custom_fields/service.py`:
  * Added `is_tier_b_available` and `assert_tier_available` helper functions enforcing fail-closed gating.
  * In `create_definition`: Reject `tier == "nsjail"` when `tier_b_sandbox_available == False` with HTTP `422 SANDBOX_UNAVAILABLE_IN_STANDALONE`.
  * In `update_definition`: Reject patching `payload.tier == "nsjail"` when `tier_b_sandbox_available == False` with HTTP `422 SANDBOX_UNAVAILABLE_IN_STANDALONE`. Pre-existing `nsjail` definitions imported from backup can update metadata (name, description, enabled) without error.
- In `kanban/api/v1/custom_field_execution.py`:
  * In `test_execute_custom_field`: Enforce `assert_tier_available("nsjail", request=request)`. Reject `nsjail` test-execute in Standalone mode with HTTP `422 SANDBOX_UNAVAILABLE_IN_STANDALONE`.
  * In `list_custom_fields_for_issue`, `execute_custom_field_for_issue`, and `test_execute_custom_field`: Fixed `CustomFieldExecutor(session, tier_b_runner=getattr(request.app.state, "tier_b_runner", None))` wiring so multi-container deployments execute Tier B nsjail scripts seamlessly.
- In `kanban/app.py`: Initialized `app.state.tier_b_sandbox_available` during startup using `get_standalone_status(settings=settings)`.

### Problem 2: Disabled/Badged Unavailable `nsjail` Options in Web UI
- Connected `CustomFieldDefinitionEditor.tsx` and `PresetGallery.tsx` to `useSystemStatus()`.
- When `tier_b_sandbox_available === false`:
  * Rendered inline Standalone Guidance Callout (`standalone-guidance-callout`) in `CustomFieldDefinitionEditor.tsx` explaining that `Scalar` (<1ms), `Formula` (<5ms), and `WebAssembly` (<25ms) work out of the box in Standalone mode, with links to `[Guide] How to Use Custom Fields ->` (`/docs/Guide-Custom-Fields`) and `Promote to Multi-Container ->` (`/admin/standalone`).
  * In `CustomFieldDefinitionEditor.tsx`: Disabled `nsjail` options in both Field Flavor (`field-flavor-select`) and Execution Sandbox Tier (`field-tier-select`) selects, badged with `[Multi-Container Compose Required]`.
  * Rendered Pre-Existing nsjail Warning Banner (`preexisting-nsjail-warning-banner`) when inspecting an imported `nsjail` definition in Standalone mode.
  * In `FlavorDecisionMatrix.tsx`: Badged and disabled the `nsjail` card with `Multi-Container Compose Required` and tooltip when `!tierBAvailable`.
  * In `PresetGallery.tsx`: Badged and disabled `nsjail`-dependent presets (`total-project-issues` and `git-pr-link`) with `Multi-Container Compose Required`.
- Styled all callouts, banners, and badges using 100% canonical `theme.css` tokens with zero inline `style={...}` props, verified via `cssTokensAudit.test.ts`.

### Problem 3: Published Step-by-Step Wiki Guide
- Published `/home/adamoutler/kanban/thumbs-up-kanban.wiki/Guide-Custom-Fields.md` starting with `# [Guide] How to Use Custom Fields` and linked in `_Sidebar.md` under `Reference Guides`.
- Covered all 4 required sections:
  1. What Custom Fields do and where values appear (Issue Properties Rail, Table View, Board Cards, Filters and Search).
  2. Choosing between `Scalar`, `Safe Formula`, `WebAssembly (wasmtime)`, and `Isolated Sandbox (nsjail)` (Standalone vs Multi-Container Compose gating and promotion path).
  3. Step-by-step walkthroughs with copy-paste examples:
     * `Priority SLA Days`: Safe Formula (`1 if priority == 'URGENT' else 3 if priority == 'HIGH' else 7 if priority == 'MEDIUM' else 14`) -> format `number` with unit `d`.
     * `Sub-Issue Progress %`: Safe Formula (`round((completed_sub_issue_count * 100.0) / sub_issue_count, 1) if sub_issue_count > 0 else 100.0`) -> format `number` with unit `%`.
     * `CVSS Severity Pill`: Dynamic severity formula -> format `severity_pill`.
     * `Total Project Issues Rollup`: WebAssembly / nsjail project metric rollup -> format `number`.
     * Detailed specification and format metadata JSON schemas for all 7 canonical output formats (`text`, `number`, `badge`, `severity_pill`, `url`, `markdown_snippet`, `json_table`).
  4. Safe formula AST execution context reference and built-in function allowlist.
  5. Dry-running with `Test Execute` and `WORKSPACE`/`SERVER` scope escalation dual-control AAL2 approval workflows.
- Checked against `check_no_dashes` (strictly 0 em-dashes and 0 en-dashes).
- Committed to wiki repository on branch `main` (`bc6b15a`).

---

## 2. Test Suite & Coverage Evidence

### Python Pytest & Coverage
Command:
```bash
KB_TEST_PGSOCKET_DIR=/tmp/kb-pgsock-b-kan32 KB_TEST_PGHOST=/tmp/kb-pgsock-b-kan32 uv run pytest \
  kanban/tests/custom_fields/test_standalone_nsjail_gate.py \
  kanban/tests/custom_fields/test_custom_fields_api.py \
  kanban/tests/custom_fields/test_execution_api.py \
  kanban/tests/custom_fields/test_manifest_and_formula_security.py \
  --cov=kanban.custom_fields.service \
  --cov=kanban.api.v1.custom_field_execution \
  --cov=kanban.api.v1.custom_fields \
  --cov-report=term-missing
```

Results:
- **Test Files:** 4 passed (4 total)
- **Tests:** 26 passed (26 total)
- **Pass Rate:** 100%

| Name | Stmts | Miss | Branch | BrPart | Cover | Missing |
| :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| `kanban/api/v1/custom_field_execution.py` | 120 | 1 | 26 | 4 | **97%** | 71->74, 109->125, 261->282, 283 |
| `kanban/api/v1/custom_fields.py` | 30 | 0 | 0 | 0 | **100%** | |
| `kanban/custom_fields/service.py` | 163 | 0 | 42 | 2 | **99%** | 355->359, 361->365 |
| **TOTAL** | **313** | **1** | **68** | **6** | **98%** | |

### TypeScript Vitest & Coverage
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
| **All files** | **100%** | **95.69%** | **100%** | **100%** |
| `src/app/useSystemStatus.ts` | 100% | 100% | 100% | 100% |
| `src/features/custom-fields/CustomFieldDefinitionEditor.tsx` | 100% | 95.74% | 100% | 100% |
| `src/features/custom-fields/FlavorDecisionMatrix.tsx` | 100% | 92.30% | 100% | 100% |
| `src/features/custom-fields/PresetGallery.tsx` | 100% | 96.87% | 100% | 100% |

---

## 3. Mandatory Static Quality Gates

All 7 mandatory checks execute cleanly with zero errors:

1. **Ruff Check:** Passed (`All checks passed!`).
2. **Mypy Typecheck:** Passed (`Success: no issues found in 7 source files`).
3. **Lint-Imports Architectural Boundary Gate:** Passed (`Contracts: 2 kept, 0 broken`).
4. **TypeScript Compiler (`tsc -b`):** Passed with zero diagnostics.
5. **ESLint (`eslint . --max-warnings 0`):** Passed across entire frontend repository with zero warnings/errors.
6. **No Dashes Guard (`check_no_dashes --all`):** Passed with 0 em/en-dashes.
7. **CSS Tokens Audit (`cssTokensAudit.test.ts`):** Passed (4/4 tests passed, 0 inline JSX styles).

---

## 4. Manifest of Forensic Artifacts

- `docs/qa/KAN-32/unit-test-results.txt`: Verbatim pytest and vitest test execution logs and coverage tables.
- `docs/qa/KAN-32/build-or-typecheck.txt`: Verbatim outputs of ruff, mypy, lint-imports, tsc, eslint, check_no_dashes, and cssTokensAudit.
- `docs/qa/KAN-32/git-diff.patch`: Complete diff of all touched code on branch `feat/KAN-32`.
- `docs/qa/KAN-32/wiki-diff.patch`: Complete diff of published wiki documentation (`Guide-Custom-Fields.md` and `_Sidebar.md`).
- `docs/qa/KAN-32/changed-files-manifest.txt`: List of all modified and added files.
- `docs/qa/KAN-32/message-to-reality-checker.md`: This forensic audit document.
