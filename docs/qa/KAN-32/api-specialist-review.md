# Clean-Room API Specialist Review: KAN-32 (RC2 Remediation)

**Reviewer:** `api-spec-2` (Clean-Room Backend, API, MCP, and Security Specialist)  
**Date:** 2026-11-20  
**Branch:** `fix/KAN-32-rc2`  
**Commit:** `89226e26696f378f4771a9dad49160ef4f34415c`  
**Status:** APPROVED  

---

## 1. Executive Summary

This clean-room audit evaluates ticket **KAN-32** on branch `fix/KAN-32-rc2` at commit `89226e26`. It specifically verifies the comprehensive resolution of all forensic findings raised in `reality-checker-report.md`, covering backend symbol alignment, WebAssembly module resolution, DB override precedence, test isolation, and guide schema synchronization.

All backend components, API contracts, and security boundaries have been verified on disk:
1. Exact function symbol audited: `resolve_wasm_module_bytes` in `kanban/custom_fields/builtin_wasm.py` (correcting prior references to `load_builtin_wasm_module`).
2. WebAssembly bytecode resolution now allows `computed_sha in BUILTIN_STARTER_WASM_BY_SHA` to fall back to the built-in `echo_cvss.wasm` module after prioritizing workspace `ApprovedWasmModule` database overrides.
3. Name-only or comment-only resolutions prioritize database overrides by name or sha256 before falling back to built-in presets.
4. Test harness isolation in `database/testing/pg_harness.py` falls back to `os.environ.get("PYTEST_XDIST_WORKER", "master")` to eliminate database name collisions during parallel test executions.
5. Wiki documentation in `thumbs-up-kanban.wiki/Guide-Custom-Fields.md` aligns with backend Pydantic validation schemas in `kanban/custom_fields/output_formats.py` (valid `severity_pill` dict format).
6. Complete static analysis and test suites achieve 100% pass rates, >=95% coverage, and 0 forbidden unicode dashes.

---

## 2. Forensic Code Audit

### 2.1. WebAssembly Starter and DB Resolution (`kanban/custom_fields/builtin_wasm.py`)
- **Bytecode Resolution (`_resolve_by_bytecode`)**:
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
  * Verified: The logic no longer requires a comment string match (`clean_src`) when the bytecode matches known starter hashes.
  * Verified: Database overrides (`ApprovedWasmModule`) take precedence over built-in bytecode. If no override exists, the starter bytecode is accepted without false `UNAPPROVED_WASM_MODULE` errors on fresh workspaces.

- **Comment-Only and Name Resolution (`resolve_wasm_module_bytes`)**:
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
  * Verified: Searches database overrides for matching name or sha256 before falling back to `BUILTIN_STARTER_WASM_BY_NAME`.
  * Verified: Unmatched identifiers raise HTTP 404 `WASM_MODULE_NOT_FOUND`.

### 2.2. Test Harness Database Isolation (`database/testing/pg_harness.py`)
In `pg_worker_db`:
```python
worker_id = getattr(request.config, "workerinput", {}).get(
    "workerid", os.environ.get("PYTEST_XDIST_WORKER", "master")
)
```
- Inspecting `PYTEST_XDIST_WORKER` environment variable enables running isolated test suites in separate processes without xdist orchestrator collisions on `kanban_test_master`.

### 2.3. Output Format and Wiki Schema Parity
- Verified `thumbs-up-kanban.wiki/Guide-Custom-Fields.md` Example 3 returns:
  ```python
  {"level": "critical", "score": 9.5, "label": "Critical"}
  ```
  This matches `_validate_severity_pill` in `kanban/custom_fields/output_formats.py` (lines 335-345), resolving the prior dict-vs-string type mismatch.
- Example 4 includes runnable Python snippet for nsjail script execution.

---

## 3. Test Suites, Coverage, and Static Analysis Verification

### 3.1. Backend Pytest Suite
- Command: `PYTEST_XDIST_WORKER=gw_kan32rc2 uv run pytest kanban/tests/custom_fields/ --cov=kanban/custom_fields --cov-report=term-missing`
- Results: 78/78 tests passed.
- Coverage Breakdown:
  * `kanban/custom_fields/__init__.py`: 100%
  * `kanban/custom_fields/builtin_wasm.py`: 100% (89 stmts, 32 branches)
  * `kanban/custom_fields/manifest.py`: 100%
  * `kanban/custom_fields/output_formats.py`: 99%
  * `kanban/custom_fields/service.py`: 99%
  * `kanban/custom_fields/approvals.py`: 96%
  * `kanban/custom_fields/executor.py`: 95%
  * Overall `kanban/custom_fields` coverage: 97% (exceeds 95% threshold).

### 3.2. Frontend Vitest Suite
- Results: 166/166 unit tests passed across 10 test files with 0 `act(...)` warnings.
- Coverage: 95.65% branch coverage maintained across scoped files.
- Design Tokens: `cssTokensAudit.test.ts` passed 4/4 (0 inline JSX `style={{...}}` properties).

### 3.3. Static Gates & Security Checks
- `uv run ruff check`: All checks passed.
- `uv run ruff format --check`: 1004 files already formatted.
- `uv run mypy`: Success: no issues found in 996 source files.
- `uv run lint-imports`: 2 contracts kept, 0 broken (`agent -> mcp -> kanban -> database`).
- `uv run kanban-ctl db check-migrations`: All 62 migrations valid, single head `p4_23_oidc_link_intent_fk`.
- `tsc -b --noEmit`: Clean (0 errors).
- `eslint . --max-warnings 0`: Clean (0 warnings).
- `vite build`: Clean production build completed in 2.27s (720 modules transformed).
- `python3 -m scripts.check_no_dashes`: 0 forbidden unicode dashes found across repository and wiki.

---

## 4. Security & Architecture Invariants

| Invariant / Check | Specification Requirement | Verification Result |
| :--- | :--- | :--- |
| **Fail-Closed nsjail Gating** | Rejects `nsjail` drafts and test execution in Standalone | HTTP 422 `SANDBOX_UNAVAILABLE_IN_STANDALONE` |
| **Starter Wasm Fallback** | Fallback for `cvss-score` / `echo_cvss.wasm` | Built-in bytecode accepted after DB check |
| **DB Override Precedence** | Custom `ApprovedWasmModule` overrides built-in | DB query runs before built-in dict lookup |
| **Form Sizing** | Normal height single-line inputs and selects (~38px) | Separated from textarea (140px) in CSS |
| **Badge Clarity** | Explains Compose requirement specifically for nsjail | `nsjail option requires Multi-Container Compose` |
| **No Duplicate Score** | Avoids redundant score display in pill | Clean `8.8 High` without duplicated score |
| **Layering Invariants** | Strict unidirectional layering | Unidirectional import boundaries maintained |
| **Typography Standards** | 0 em-dashes and 0 en-dashes | Checked with `scripts.check_no_dashes` |

---

## 5. Certification Signoff

STATUS: APPROVED

All findings from the reality-checker report have been fully remediated. Backend symbols, WebAssembly resolution logic, database override precedence, and guide code examples are verified. KAN-32 is certified ready for reality-checker QA gate on `fix/KAN-32-rc2`.
