# API Specialist Gate Review: KANBA-143 (KB-P5-13)

- **Ticket**: `KANBA-143` (`KB-P5-13`: Tier A Wasmtime runner, partitioned execution API, `/mcp/admin` tool 7)
- **Reviewer**: `@arch-reviewer` (Systems/Backend Architect & API Specialist), independent audit
- **Branch / Commit audited**: `feat/KANBA-143` at `ffdde0d` (initial audit at `11ec86b` and uncommitted tree, changes requested, re-audited twice)

## Findings raised and resolved
1. Host-memory DoS: `host_kb_output` appended every call with no cap. Fixed: exactly one call permitted (second call traps `SCRIPT_TRAP`), explicit `ptr >= 0`, `length >= 0`, `ptr + length <= data_len` bounds check, NaN canonicalization enabled.
2. `cached_only` (script depth >= 1) path called a non-existent method and ignored partitioning. Fixed: `assert_execution_authorized` (fail closed, `APPROVAL_REVOKED`), `compute_cache_partition_key`, `script_version` and `expires_at` filters, SERVER scope always `not_computed`, zero runner invocations.
3. Unbounded forced execution. Fixed: 6 requests/minute per (principal, issue, field).
4. Rate-limit bypass: first fix counted inside the request transaction, so failing scripts (422) rolled the hit back. Fixed in `ffdde0d`: hit commits on its own engine connection; test shows 6 x 422 then 429 against `infinite_loop.wasm`.
5. Module upload had no ledger row. Fixed: `WASM_MODULE_UPLOADED` (sha256, name, size; no bytes), `base64 validate=True`, request length cap, no commit inside handler.

## Verified
- Engine: fuel (<= 50M) + epoch interruption (5ms ticker, <= 500ms), store limits <= 32 MiB, downward-only `WasmRunLimits`, only `env.kb_output` import allowed (`WASM_FORBIDDEN_IMPORT` otherwise), ABI exports validated, module LRU keyed by sha256.
- Partition key `(issue, field, script_version, user_access_hash)`; PROJECT_ADMIN_SP shared; SERVER scope zero-cache with `CUSTOM_FIELD_SERVER_INVOKED` ledger record.
- Upload requires project ADMIN + AAL2; execution fails closed on revoked approval (409).
- Tests: 39 pass, 95.68% line+branch; ruff, format, mypy --strict, lint-imports, license gate, no-dashes clean; `wasmtime` dependency evaluation present.

## Non-blocking
- Tier B recursion: `ScriptDepthGuardMiddleware` (KANBA-145) must be merged so `request.state.script_depth` is populated; the header fallback covers the interim.
- Input payload `labels` is empty and `state`/`priority` are ids; ticket if scripts need names.

**Verdict: APPROVED**
