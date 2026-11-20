# Clean-Room API Specialist Review: KAN-32 (Live Full-Stack QA Verification)

- **Ticket:** KAN-32
- **Title:** Custom Fields Studio Controls, WebAssembly Module Resolution, and Preset Tier Gating
- **Reviewer:** `api-spec-2` (Clean-Room Backend, API, MCP, and Security Specialist)
- **Date:** 2026-11-20
- **Target Directory:** `/home/adamoutler/kanban/docs/qa/KAN-32`
- **Branch:** `main` (commit `7913c2c8`)
- **Container Environment:** `http://127.0.0.1:18961` (container: `kanban-liveqa-1`)
- **Live Stack Status:** `LIVE_STACK_VERDICT: PASS`
- **Status:** APPROVED

---

## 1. Executive Summary

This clean-room API, Security, and Architectural audit inspects ticket **KAN-32** on branch `main` at commit `7913c2c8`. The review incorporates empirical verification results from zero-mock Live Full-Stack QA execution against container `kanban-liveqa-1` (`http://127.0.0.1:18961`, PostgreSQL 16 + FORCE RLS) documented in `docs/qa/KAN-32/live-fullstack-proof.txt`, visual screenshots in `docs/qa/KAN-32/screenshots/`, backend unit test and coverage reports (`unit-test-results.txt`), and static build outputs (`build-or-typecheck.txt`).

The ticket resolves all forensic findings from `reality-checker-report.md`, verifying backend symbol accuracy, WebAssembly module resolution, database override precedence, safe formula evaluation, tier gating, log formatting, and wiki documentation synchronization:
1. **Bare Formula Copy-Paste Normalization:** The endpoint `POST /api/v1/projects/{project_ref}/custom-fields/test-execute` cleanly evaluates expressions pasted directly from documentation without mandatory `"formula: "` prefixes, resolving the prior HTTP 422 `WASM_BINARY_INVALID` regression.
2. **WebAssembly Starter & Database Precedence:** `resolve_wasm_module_bytes` in `kanban/custom_fields/builtin_wasm.py` prioritizes workspace `ApprovedWasmModule` database records before falling back to built-in presets (`echo_cvss.wasm`), eliminating false `UNAPPROVED_WASM_MODULE` errors on fresh workspaces.
3. **Fail-Closed nsjail Sandbox Gating:** Standalone deployments strictly reject `nsjail` script execution and drafting with HTTP 422 `SANDBOX_UNAVAILABLE_IN_STANDALONE`.
4. **Form Ergonomics & Layout Parity:** Single-line form inputs and selects strictly render at 38px height (separating `.custom-field-textarea` at 140px). Unbroken 220-character formula execution logs wrap cleanly (`scrollWidth === clientWidth`) inside `pre.custom-field-test-logs`.
5. **Quality & Coverage:** Backend `kanban/custom_fields` suite achieved 97% overall coverage across 1269 statements (78/78 Pytest passing). Frontend Vitest suite achieved 95.65% branch coverage (166/166 passing). Static analysis, lint-imports, and check_no_dashes passed with 0 errors.

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

### 2.2 Live Stack Execution on Container `kanban-liveqa-1` (`:18961`)
1. **Bare Example 3 Formula Copy-Paste:**
   - Endpoint: `POST http://127.0.0.1:18961/api/v1/projects/SEC2/custom-fields/test-execute`
   - Payload: Bare expression from `Guide-Custom-Fields.md` Example 3 without `"formula: "` prefix:
     ```python
     {"level": "critical", "score": 9.5, "label": "Critical"} if priority == "URGENT" else (
         {"level": "high", "score": 8.0, "label": "High"}
         if priority == "HIGH"
         else (
             {"level": "medium", "score": 5.0, "label": "Medium"}
             if priority == "MEDIUM"
             else {"level": "low", "score": 2.0, "label": "Low"}
         )
     )
     ```
   - Response: HTTP 200 OK in 3ms.
     ```json
     {
       "output_format": "severity_pill",
       "value": {"level": "low", "score": 2, "label": "Low"},
       "latency_ms": 3,
       "logs": "Draft test execution on SEC2-1 (flavor=wasm)\nEvaluated Formula expression: ...",
       "status": "SUCCESS",
       "error": null
     }
     ```
   - UI Preview: Rendered pill `"2.0 Low"`, 0 HTTP 422 `WASM_BINARY_INVALID` errors.
2. **Manual WebAssembly Test Execute (`STARTER_TEMPLATES.wasm.severity_pill`):**
   - Executed against issue `SEC2-1`: HTTP 200 OK in 10ms.
   - Rendered Output Pill: `"8.8 High"` with `hasDuplicateScore=false`.
3. **220-Character Unbroken Log Line Wrapping:**
   - Evaluated 220-character unbroken formula log in `pre.custom-field-test-logs`:
   - Measured dimensions: `scrollWidth=742`, `clientWidth=742`, `scrollEqualsClient=true`, `overflowsCard=false`.
   - Styles applied: `white-space: pre-wrap; overflow-wrap: anywhere; word-break: break-all;`.
4. **Form Control Heights:**
   - `field-name-input`: 38px
   - `field-slug-input`: 38px
   - `field-flavor-select`: 38px
   - `output-format-select`: 38px
   - `test-issue-key-input`: 38px
   - `execution-tier-select`: 38px
   - Zero 140px bloated inputs detected.
5. **Advanced Tier Gating:**
   - In Standalone mode, nsjail options are disabled and badged: `"nsjail option requires Multi-Container Compose"`.

---

## 3. Test Suites, Coverage, & Static Gate Results

### 3.1 Backend Pytest & Coverage
- Command: `PYTEST_XDIST_WORKER=gw_kan32rc2 uv run pytest kanban/tests/custom_fields/ --cov=kanban/custom_fields --cov-report=term-missing`
- Results: 78/78 tests passed in 34.05s.
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
- Command: `vitest run --coverage src/features/custom-fields src/app/useSystemStatus.test.tsx`
- Results: 10 test files passed, 166 passed (166), 0 failed.
- Branch Coverage: 95.65% across scoped custom fields components.
- Design Token Audit (`cssTokensAudit.test.ts`): 4/4 passed (0 inline JSX `style={...}` attributes).

### 3.3 Static Gate Verification
- Ruff Check (`uv run ruff check`): All checks passed.
- Ruff Format Check (`uv run ruff format --check`): 1004 files already formatted.
- Mypy (`uv run mypy`): Success: no issues found in 996 source files.
- Migrations (`uv run kanban-ctl db check-migrations`): OK: 62 migrations valid, single head.
- Import Linter (`uv run lint-imports`): 2 contracts kept, 0 broken (`agent -> mcp -> kanban -> database`).
- TypeScript (`tsc -b --noEmit`): 0 errors.
- ESLint (`eslint . --max-warnings 0`): 0 warnings.
- Vite Production Build: Clean build completed in 2.27s (720 modules transformed).
- Check No Dashes (`python3 -m scripts.check_no_dashes --all`): 0 forbidden unicode dashes across repository and wiki.

---

## 4. Security & Architecture Invariants Checklist

| Invariant / Check | Requirement | Live Verification Result |
| :--- | :--- | :--- |
| **Fail-Closed nsjail Gating** | Reject nsjail execution in Standalone | HTTP 422 `SANDBOX_UNAVAILABLE_IN_STANDALONE` |
| **Starter Wasm Fallback** | Accept `echo_cvss.wasm` starter bytecode | Built-in bytecode accepted after DB check |
| **DB Override Precedence** | Custom `ApprovedWasmModule` overrides built-in | DB query runs before built-in dict lookup |
| **Formula Normalization** | Accept bare formula expressions without prefix | HTTP 200 OK in 3ms, pill rendered "2.0 Low" |
| **No Duplicate Score** | Prevent redundant score display in pill | Clean `"8.8 High"` formatted pill |
| **Log Wrapping** | Prevent horizontal overflow from long expressions | `pre.custom-field-test-logs` `scrollWidth === clientWidth` |
| **Control Heights** | Single-line inputs/selects normal height (~38px) | 38px verified across all controls |
| **Layering Invariants** | Unidirectional module layering | `agent -> mcp -> kanban -> database` KEPT |
| **Typography Standards** | 0 em-dashes and 0 en-dashes | `scripts.check_no_dashes` passed cleanly |

---

## 5. Certification Signoff

STATUS: APPROVED

Ticket KAN-32 is completely verified on `main` against live container `kanban-liveqa-1` (`:18961`, commit `7913c2c8`). All backend symbols, WebAssembly fallback and database override paths, test execution endpoints, and layout invariants are certified ready for reality-checker QA gate closure.
