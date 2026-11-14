# Forensic QA Handoff: KANBA-143 (KB-P5-13)

## Ticket Overview
- **Ticket ID:** `KANBA-143` (`KB-P5-13`)
- **Title:** `[Phase 5 / Sandbox + API + MCP] Tier A Wasmtime runner (<=50M fuel, <=32MiB, <=500ms), partitioned execution API & /mcp/admin tool 7`
- **Spec Sections:** S13.3 (WebAssembly Sandbox), S13.2 (Partitioned Caching & Escalation), S11.4 Tool 7 (`manage_custom_fields_and_scripts`)
- **Gates:** API Specialist Gate, UI Specialist Gate, Dependency Evaluation Gate, Reality-Checker Forensic Gate
- **Target Branch:** `feat/KANBA-143`

---

## Implemented Components

### 1. Dependency Management
- Added `wasmtime==50.0.1` (`Apache-2.0 WITH LLVM-exception`) to root `pyproject.toml`, `kanban/pyproject.toml`, and lockfile `uv.lock`.
- Zero transitive runtime dependencies.
- Verified compliant with `scripts/license_gate.py` (`SUMMARY python=116 node=1 violations=0`).
- Documented in `docs/qa/KANBA-143/dependency-evaluation.md` with wheel cryptographic SHA-256 hashes and 3 specialist sign-offs (`arch-reviewer`, `sec-eng`, `qa-eng`).

### 2. Database Migration & Models
- `database/migrations/versions/p5_13_approved_wasm_modules.py`: Alembic revision chained to `p5_12_custom_field_approvals`.
- `database/migrations/sql/p5_13_approved_wasm_modules.up.sql`: Table `approved_wasm_modules` (`UNIQUE (workspace_id, sha256)` with `ENABLE` + `FORCE ROW LEVEL SECURITY`, admin-only write policies, caller select policy).
- `database/migrations/sql/p5_13_approved_wasm_modules.down.sql`: Fully reversible teardown.
- `database/models/wasm_module.py`: SQLAlchemy ORM model `ApprovedWasmModule`, exported in `database/models/__init__.py`.
- Updated table count in `database/tests/test_p1_17_models.py` to 67 (5/5 passed).

### 3. Wasm Fixtures
- Built 5 reproducible `.wasm` test fixtures in `tests/fixtures/wasm/` via `build_fixtures.py`:
  - `echo_cvss.wasm`: Compliant ABI module reading JSON and emitting `{"level": "high", "score": 8.8, "label": "8.8 High"}`.
  - `infinite_loop.wasm`: Traps fuel exhaustion (<= 50M fuel) and timeout (<= 500ms).
  - `mem_grow_64mb.wasm`: Traps memory growth exceeding 512 64KiB pages (32 MiB).
  - `wasi_fs_import.wasm`: Traps host imports outside `kb_output` (`WASM_FORBIDDEN_IMPORT`).
  - `require_qa_proof_link.wasm`: Validates issue summary and verification links.

### 4. Sandbox Wasmtime Runner
- `kanban/sandbox/wasm_runner.py`:
  - `TierAWasmRunner` singleton engine with LRU module cache.
  - Monotonic epoch ticker thread ticking every 5ms for preemptive timeout interruptions.
  - Strict guest ABI: `(func (export "kb_alloc") (param i32) (result i32))` and `(func (export "kb_run") (param i32 i32) (result i32))`.
  - Zero host imports except `(import "env" "kb_output")`.
  - Downward-only resource configuration (`WasmRunLimits`).
  - Deterministic error codes: `SCRIPT_FUEL_EXHAUSTED`, `SCRIPT_TIMEOUT`, `SCRIPT_MEMORY_LIMIT`, `SCRIPT_TRAP`, `WASM_FORBIDDEN_IMPORT`, `WASM_BINARY_INVALID`.
  - Protocols `TierBRunner` and `UnavailableTierBRunner` for Tier B isolation.

### 5. Partitioned Custom Field Executor
- `kanban/custom_fields/executor.py`:
  - `CustomFieldExecutor`: partitioned caching in `custom_field_values` by `(workspace_id, issue_id, field_id, user_access_hash)`.
  - Distinct caller access hashes isolate cached values between users for `INVOKING_USER`.
  - Zero user access hash permits team-wide shared cache for `PROJECT_ADMIN_SP`.
  - `assert_execution_authorized`: Fail-closed escalation gate rejecting untrusted scripts or modified manifests (`APPROVAL_REVOKED`).
  - S13.2 Row 4 SERVER audit logging: Records `CUSTOM_FIELD_SERVER_INVOKED` in `activity_records` and bypasses cache (TTL = 0).

### 6. REST API Endpoints
- `kanban/api/v1/custom_field_execution.py`:
  - `GET /api/v1/issues/{issue_key}/custom-fields`: Lists custom fields and cached values under caller RLS.
  - `POST /api/v1/issues/{issue_key}/custom-fields/{field_id}/execute`: Executes custom field with `force_refresh` parameter.
  - `POST /api/v1/projects/{project}/wasm-modules`: Uploads and validates Wasm bytecode with `PROJECT_ADMIN` role and AAL2 requirement.
  - Mounted on FastAPI app router in `kanban/api/v1/__init__.py`.

### 7. MCP Admin Tool 7
- `mcp/admin/tools/manage_custom_fields_and_scripts.py` and re-export in `mcp/surfaces/admin/manage_custom_fields_and_scripts.py`:
  - Registered in `create_admin_registry()`.
  - Sub-commands: `list_fields`, `get_field`, `upsert_field`, `delete_field`, `upload_wasm_module`, `request_escalation`, `approve_escalation`, `execute_field`, `help`.
  - Surface check: Strictly `Surface.ADMIN` with `kb_adm_*` key.
  - Scope checks: `admin:read` for queries, `admin:write` for mutations, `admin:destructive` for deletion.
  - 2-stage destructive confirmation requiring `sp_warning_acknowledged` for Service Principal escalation.

---

## Mandatory Verification Proofs in `docs/qa/KANBA-143/`
1. `git-diff.patch`: Unified diff of all changes against base.
2. `unit-test-results.txt`: 37 passed, exit code 0, 96.68% total coverage.
3. `build-check.txt`: Ruff clean, ruff format clean, mypy clean, lint-imports 2 kept / 0 broken, license gate 0 violations.
4. `schema-dump.sql`: Complete PostgreSQL schema dump of `approved_wasm_modules` table with RLS policies and grants.
5. `wasm-benchmark.txt`: Benchmark results showing warm median latency of 0.212ms (< 2.0ms target) and cold start of 2.8ms.
6. `contract-sample.json`: REST request/response samples for GET values, POST execute, fuel exhaustion (400), and approval revocation (409).
7. `mcp-transcript.yaml`: Captured tool 7 calls across `help`, `upsert_field`, `approve_escalation`, `execute_field`, `delete_field`.
8. `dependency-evaluation.md`: Full audit of `wasmtime 50.0.1` with wheel SHA-256 hashes and specialist sign-offs.
9. `api-specialist-review.md`: API specialist review with `Verdict: APPROVED`.
10. `ui-specialist-review.md`: UI specialist review with `Verdict: APPROVED` (screenshots N/A for non-UI ticket).

---

## Test Execution Summary
- `kanban/tests/sandbox/test_wasm_runner.py`: 14 passed (94% coverage)
- `kanban/tests/custom_fields/test_executor_cache.py`: 4 passed (97% coverage)
- `kanban/tests/custom_fields/test_execution_api.py`: 3 passed (100% coverage)
- `mcp/tests/admin/test_manage_custom_fields_and_scripts.py`: 11 passed (99% coverage)
- `database/tests/test_p1_17_models.py`: 5 passed (Table count 67 verified)
- **Combined DoD coverage: 96.68% (Target: >= 95% -> PASS)**
- **Total Test Suite:** 37 passed in 4.72s.
