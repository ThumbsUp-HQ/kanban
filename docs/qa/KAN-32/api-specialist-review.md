# Clean-Room API Specialist Review: KAN-32 (Live Full-Stack QA Verification)

- **Ticket:** KAN-32
- **Title:** Custom Fields Studio Controls, WebAssembly Module Resolution, and Preset Tier Gating
- **Reviewer:** `api-spec-2` (Clean-Room Backend, API, MCP, and Security Specialist)
- **Date:** 2026-11-20
- **Target Directory:** `/home/adamoutler/kanban/docs/qa/KAN-32`
- **Branch:** `main` (commit `78074a1d`)
- **Container Environment:** `http://127.0.0.1:18961` (container: `kanban-liveqa-1`)
- **Live Stack Status:** `LIVE_STACK_VERDICT: PASS`
- **Status:** APPROVED

---

## 1. Executive Summary

This clean-room API, Security, and Architectural audit inspects ticket **KAN-32** on branch `main` at commit `78074a1d`. The review incorporates empirical verification results from zero-mock Live Full-Stack QA execution against container `kanban-liveqa-1` (`http://127.0.0.1:18961`, PostgreSQL 16 + FORCE RLS) documented in `docs/qa/KAN-32/live-fullstack-proof.txt`, visual screenshots in `docs/qa/KAN-32/screenshots/`, backend unit test and coverage reports (`unit-test-results.txt`), and static build outputs (`build-or-typecheck.txt`).

The ticket resolves all forensic findings from `reality-checker-report.md`, verifying backend symbol accuracy, WebAssembly module resolution, database override precedence, safe formula evaluation, tier gating, log formatting, and wiki documentation synchronization:
1. **Bare Formula Copy-Paste Normalization:** The endpoint `POST /api/v1/projects/{project_ref}/custom-fields/test-execute` cleanly evaluates expressions pasted directly from documentation without mandatory `"formula: "` prefixes, resolving the prior HTTP 422 `WASM_BINARY_INVALID` regression. In Round 3 live testing, pasting the bare Example 3 expression returned HTTP 200 OK in 10ms with `status="SUCCESS"` and parsed severity pill value `{"level":"low","score":2,"label":"Low"}`.
2. **WebAssembly Starter & Database Precedence:** `resolve_wasm_module_bytes` in `kanban/custom_fields/builtin_wasm.py` prioritizes workspace `ApprovedWasmModule` database records before falling back to built-in presets (`echo_cvss.wasm`), eliminating false `UNAPPROVED_WASM_MODULE` errors on fresh workspaces.
3. **Fail-Closed nsjail Sandbox Gating:** Standalone deployments strictly reject `nsjail` script execution and drafting with HTTP 422 `SANDBOX_UNAVAILABLE_IN_STANDALONE`.
4. **Form Ergonomics & Layout Parity:** Single-line form inputs and selects strictly render at 38px height (separating `.custom-field-textarea` at 140px). Unbroken 220-character formula execution logs wrap cleanly (`scrollWidth === clientWidth`) inside `pre.custom-field-test-logs` (742px / 742px) and `.custom-field-test-result` (768px / 768px).
5. **Log Format Parity:** Test execution logs print `(tier=wasm)` instead of `(flavor=wasm)`, verified via `hasTierWasmLog=true` and `hasLegacyFlavorWasmLog=false`.
6. **Saved Field List Parity:** Saved custom field "Incident Severity Pill" (slug: `incident-severity-pill`) renders distinctly in the left list view alongside the selected editor (`live-desktop-light.png`).
7. **Quality & Coverage:** Backend `kanban/custom_fields` suite achieved 97% overall coverage across 1269 statements (78/78 Pytest passing). Frontend Vitest suite achieved 96.64% branch coverage and 100% lines/stmts (79/79 passing). Static analysis, lint-imports, and check_no_dashes passed with 0 errors.

---

## 2. Forensic API & Security Implementation Audit

### 2.1 WebAssembly Bytecode & Database Override Resolution (`kanban/custom_fields/builtin_wasm.py`)
- **Function Symbol:** Audited exact function `resolve_wasm_module_bytes`.
- **Bytecode Resolution Logic (`_resolve_by_bytecode`):**
  ```python
  if computed_sha in BUILTIN_STARTER_WASM_BY_SHA:
      mod_stmt = select(ApprovedWasmModule).where(
          ApprovedWasmModule.workspace_id == workspace_id,
          ApprovedWasmModule.sha256 == computed_sha,
      )
      wasm_mod = (await session.execute(mod_stmt)).scalar_one_or_none()
      if wasm_mod is not None:
          return wasm_mod.wasm_bytes, bytes(wasm_mod.sha256)
      return wasm_bytes, computed_sha
  ```
  - Logic verifies that matching starter hashes do not require comment string matching (`clean_src`).
  - Database overrides (`ApprovedWasmModule`) take precedence over built-in bytecode. If no override exists, the starter bytecode is accepted without false `UNAPPROVED_WASM_MODULE` rejections.
- **Comment-Only and Name Resolution:**
  ```python
  matched_name = next(
      (k for k in BUILTIN_STARTER_WASM_BY_NAME if k in clean_src.lower()),
      None,
  )
  if matched_name is not None:
      mod_stmt = select(ApprovedWasmModule).where(
          ApprovedWasmModule.workspace_id == workspace_id,
          (ApprovedWasmModule.name == matched_name)
          | (ApprovedWasmModule.sha256 == ECHO_CVSS_SHA256_BYTES),
      )
      wasm_mod = (await session.execute(mod_stmt)).scalar_one_or_none()
      if wasm_mod is not None:
          return wasm_mod.wasm_bytes, bytes(wasm_mod.sha256)
      lower_name = matched_name.lower()
      mod_bytes = BUILTIN_STARTER_WASM_BY_NAME[lower_name]
      return mod_bytes, hashlib.sha256(mod_bytes).digest()
  ```
  - Queries database overrides by name or SHA-256 before falling back to built-in dictionary.
  - Unmatched identifiers fail closed with HTTP 404 `WASM_MODULE_NOT_FOUND`.

### 2.2 Live Stack Execution on Container `kanban-liveqa-1` (`:18961`, Commit `78074a1d`)
1. **220-Character Unbroken Formula Wrapping & (tier=wasm) Log Verification:**
   - Script: `round3_auth_qa.mjs` on `/projects/SEC2/settings/custom-fields` (issue `SEC2-1`, `@admin` AAL2).
   - Executed 220-char unbroken formula string (`"UNBROKEN_LOG_LINE_" + "X" * 220`) with Field Flavor = formula, Output Format = text:
     * `POST /api/v1/projects/SEC2/custom-fields/test-execute` -> HTTP 200 OK.
     * Logs verbatim:
       `"Draft test execution on SEC2-1 (tier=wasm)\nEvaluated Formula expression: \"UNBROKEN_LOG_LINE_...\"\nSuccess: validated format text\n"`
     * Verified log line prints `(tier=wasm)` (`hasTierWasmLog=true`, `hasLegacyFlavorWasmLog=false`).
     * Wrapping metrics:
       - `.custom-field-test-result`: `resultScrollWidth=768`, `resultClientWidth=768` (`resultFitsCard=true`).
       - `[data-testid="test-output-pill"]`: `pillScrollWidth=744`, `pillClientWidth=744` (`textOverflowsCard=false`).
       - `pre.custom-field-test-logs`: `logsScrollWidth=742`, `logsClientWidth=742` (`logsFitsCard=true`, `preOverflowsCard=false`).
       - `viewportOverflows=false`.
     * Visual screenshot: `docs/qa/KAN-32/screenshots/live-long-log-wrap-light.png`.
2. **Bare Example 3 Formula Copy-Paste & Saved Field List View:**
   - Selected Field Flavor = formula, Output Format = severity_pill, pasted exact bare Example 3 expression from `Guide-Custom-Fields.md` without `"formula: "` prefix:
     * `POST /api/v1/projects/SEC2/custom-fields/test-execute` -> HTTP 200 OK (latency 10ms).
     * Response: `{"output_format":"severity_pill","value":{"level":"low","score":2,"label":"Low"},"latency_ms":10,"logs":"Draft test execution on SEC2-1 (tier=wasm)\nEvaluated Formula expression: ...","status":"SUCCESS","error":null}`.
     * `ex3HasTierWasm=true`.
     * Screenshot: `docs/qa/KAN-32/screenshots/live-wiki-example3-test-exec-light.png`.
   - Saved field "Incident Severity Pill" (slug: `incident-severity-pill`):
     * `POST /api/v1/projects/SEC2/custom-fields` -> HTTP 201 Created.
     * Verified saved row `[data-testid="field-item-incident-severity-pill"]` rendered in left Custom Fields list alongside selected editor.
     * Distinct list+editor screenshot: `docs/qa/KAN-32/screenshots/live-desktop-light.png`.
3. **Form Control Heights:**
   - `field-name-input`: 38px
   - `field-slug-input`: 38px
   - `field-flavor-select`: 38px
   - `output-format-select`: 38px
   - `test-issue-key-input`: 38px
   - `execution-tier-select`: 38px
   - Zero 140px bloated inputs detected.
4. **Advanced Tier Gating:**
   - In Standalone mode, nsjail options are disabled and badged: `"nsjail option requires Multi-Container Compose"`.

---

## 3. Test Suites, Coverage, & Static Gate Results

### 3.1 Backend Pytest & Coverage
- Command: `uv run pytest kanban/tests/custom_fields/ --cov=kanban/custom_fields --cov-report=term-missing`
- Results: 78/78 tests passed in 33.20s.
- Module Breakdown:
  * `kanban/custom_fields/__init__.py`: 100%
  * `kanban/custom_fields/approvals.py`: 96%
  * `kanban/custom_fields/builtin_wasm.py`: 100% (89 stmts, 32 branches)
  * `kanban/custom_fields/executor.py`: 95%
  * `kanban/custom_fields/manifest.py`: 100%
  * `kanban/custom_fields/output_formats.py`: 99%
  * `kanban/custom_fields/service.py`: 99%
  * **Total `kanban/custom_fields` Coverage:** 97% across 1269 statements (surpassing 95% threshold).

### 3.2 Frontend Vitest & Design Token Audit
- Command: `vitest run --coverage src/styles/__tests__/cssTokensAudit.test.ts src/features/custom-fields/__tests__/CustomFieldValue.test.tsx src/features/custom-fields/__tests__/CustomFieldDefinitionEditor.test.tsx`
- Results: 3 test files passed, 79 passed (79), 0 failed.
- Branch Coverage: 96.64% across scoped custom fields components (100% lines, 100% statements, 100% functions).
- Design Token Audit (`cssTokensAudit.test.ts`): 4/4 passed (0 inline JSX `style={...}` attributes).

### 3.3 Static Gate Verification (Commit `78074a1d`)
- Ruff Check (`uv run ruff check .`): All checks passed across 2023 files.
- Ruff Format Check (`uv run ruff format --check .`): Clean across 2023 files.
- Mypy (`uv run mypy database kanban mcp agent`): Success: no issues found in 995 source files.
- Migrations (`uv run kanban-ctl db check-migrations`): OK: 63 migrations valid, single head (`p4_24_agent_safe_sequences`).
- Import Linter (`uv run lint-imports`): 2 contracts kept, 0 broken (`agent -> mcp -> kanban -> database`).
- TypeScript (`pnpm --dir kanban/web run typecheck`): Clean (exit code 0).
- ESLint (`pnpm --dir kanban/web run lint`): Clean (0 errors, 0 warnings).
- Vite Production Build (`pnpm --dir kanban/web run build`): Clean build completed in 1.15s.
- Check No Dashes (`python3 -m scripts.check_no_dashes --all` and `thumbs-up-kanban.wiki`): 0 forbidden unicode dashes found across repository.

---

## 4. Security & Architecture Invariants Checklist

| Invariant / Check | Requirement | Live Verification Result |
| :--- | :--- | :--- |
| **Fail-Closed nsjail Gating** | Reject nsjail execution in Standalone | HTTP 422 `SANDBOX_UNAVAILABLE_IN_STANDALONE` |
| **Starter Wasm Fallback** | Accept `echo_cvss.wasm` starter bytecode | Built-in bytecode accepted after DB check |
| **DB Override Precedence** | Custom `ApprovedWasmModule` overrides built-in | DB query runs before built-in dict lookup |
| **Formula Normalization** | Accept bare formula expressions without prefix | HTTP 200 OK in 10ms, pill rendered "2.0 Low" |
| **Log Format Parity** | Logs print (tier=wasm) instead of (flavor=wasm) | Verified in live execution (`hasTierWasmLog=true`) |
| **No Duplicate Score** | Prevent redundant score display in pill | Clean `"8.8 High"` formatted pill |
| **Log Wrapping** | Prevent horizontal overflow from long expressions | `pre.custom-field-test-logs` `scrollWidth === clientWidth` |
| **Control Heights** | Single-line inputs/selects normal height (~38px) | 38px verified across all controls |
| **Layering Invariants** | Unidirectional module layering | `agent -> mcp -> kanban -> database` KEPT |
| **Typography Standards** | 0 em-dashes and 0 en-dashes | `scripts.check_no_dashes` passed cleanly |

---

## 5. Certification Signoff

STATUS: APPROVED

Ticket KAN-32 is completely verified on `main` against live container `kanban-liveqa-1` (`:18961`, commit `78074a1d`). All backend symbols, WebAssembly fallback and database override paths, test execution endpoints, log format strings, and layout invariants are certified ready for reality-checker QA gate closure.
