# API Specialist Gate Independent Forensic Re-Audit: APPROVED for KANBA-69 (KB-P4-03)

- Ticket: `KANBA-69` (`KB-P4-03`): EntityResolver, InlineSafeDumper YAML, summary/standard/full LOD tiers & JIT help
- Auditor: `arch-reviewer` (Swarm Systems/Backend Architect & API Specialist Gate Auditor)
- Date: 2026-11-12
- Worktree: `/tmp/kb-wt-KANBA-69` on branch `feat/KANBA-69`
- Scope: `GET /api/v1/resolve` contract, `kanban/resolve/service.py`, `mcp/resolver.py`, `mcp/internal_client.py` error mapping, `mcp/help.py` JIT help, `mcp/yaml_out.py`, `mcp/protocol.py`, `contract-sample.json`, and resolution of F1, F2, F3 findings.

---

### 1. Re-Audit of Scrutiny Points & Flaw Remediation

1. **F1 (JIT Help Progressive Disclosure & Live Metadata Resolution) - RESOLVED:**
   - The hardcoded mock constants (`_DEFAULT_STATES`, `_DEFAULT_PRIORITIES`, `_DEFAULT_LABELS`, `_DEFAULT_CYCLES`, `Cycle 4`, `qa-needs-work`) have been completely excised from the production execution path in `mcp/help.py`.
   - `build_help` and `_handle_jit_help` now cleanly forward the caller's credentials (`subject_token` and `mcp_session_id`) to `KanbanApiClient` for both `/api/v1/resolve` and `/api/v1/projects/{proj_key}`.
   - When live project metadata is fetched, actual project workflow attributes (`states`, `priorities`, `labels`, `cycles`, `modules`) are rendered. If an upstream endpoint or attribute is unavailable, the key is cleanly omitted rather than fabricating mock values.
   - Mandatory keys `custom_fields: []` and `agents: []` are reliably initialized per Action 6 specifications. Injected `project_metadata` remains supported for isolated unit test fixtures without polluting runtime behavior.

2. **F2 (Internal Exception Non-Disclosure & Sanitization) - RESOLVED:**
   - In `mcp/protocol.py`, the catch-all `except Exception:` block no longer interpolates `{exc}` into client responses. It logs the full exception with session id correlation on the server (`_logger.exception("Internal tool execution error (session=%s)", session_id)`) and returns a fixed, sanitized error message:
     ```python
     internal_err = KbMcpError(
         code=McpErrorCode.INTERNAL,
         message="Internal tool execution error",
     )
     ```
   - Regression test `test_internal_exception_non_disclosure` in `mcp/tests/test_lod_help.py` explicitly proves that an unhandled `RuntimeError("SELECT secret FROM x at /srv/app.py")` yields `isError: True` and contains none of `SELECT`, `/srv/`, `RuntimeError`, or `secret`.
   - Aligned assertion in `mcp/tests/test_registry_isolation.py` (line 194) to verify non-disclosure and ensure all 47 MCP tests pass cleanly.

3. **F3 (Placeholder Tool Test Hook Removal) - RESOLVED:**
   - `create_placeholder_tool` in `mcp/registry.py` is now completely clean; the `action == "ambiguous"` test hook has been removed from production code. Ambiguity resolution is tested strictly via dynamic tool registration in test suites.

---

### 2. Comprehensive Verification Matrix

| Dimension | Target | Observed | Verdict |
| :--- | :--- | :--- | :--- |
| Resolve endpoint | `GET /api/v1/resolve?kind&ref&project` inside `timing_floor(25.0)` | Present in `kanban/api/v1/resolve.py`, mounted in `build_v1_router()`, RLS session + principal dependency | PASS |
| Anti-enumeration | 0 or unreadable matches -> identical 404 | `not_found()` on empty match set; project context resolved under RLS first, so `MODULES_DISABLED` cannot reveal an unreadable project | PASS |
| Ambiguity | 409 with at most 5 `{key,title}` candidates | `matches[:5]`; candidates come only from RLS-visible rows; `Problem.candidates` additive field | PASS |
| Input hardening | `ref <= 200`, control chars -> 422 | `_validate_ref` rejects length and `< 0x20` / `0x7f` | PASS |
| Cross-workspace handle | other workspace `@handle` -> 404 | Workspace-scoped query plus RLS; covered by unit test | PASS |
| Client error mapping | 404/409/412/422/429/5xx + `AMBIGUOUS_IDENTIFIER`, `MODULES_DISABLED` | `_resolve_error_code` extended without regressing KB-P4-01 mapping | PASS |
| YAML dumper | `SafeDumper` subclass, no `!!python`, `TypeError` on non-primitives, 0/False preserved | `InlineSafeDumper` derived from `yaml.SafeDumper`, `_reject_non_primitive` fallback | PASS |
| Static quality gates | ruff, mypy --strict, lint-imports, license, check_no_dashes | All clean (2 architectural contracts kept, 0 license violations, 0 non-ASCII dashes) | PASS |
| JIT help (`mcp/help.py`) | LIVE project data, caller credential forwarding, no invented constants | Live resolution via `KanbanApiClient` with forwarded identity; mock constants removed; keys omitted when absent | PASS |
| Error Sanitization | Sanitized 500 error, zero traceback/path/SQL leak | Catch-all returns fixed `"Internal tool execution error"` with `McpErrorCode.INTERNAL` | PASS |

---

### 3. Test & Coverage Evidence

- Target modules under test: `kanban.resolve`, `mcp.bench.token_benchmark`, `mcp.help`, `mcp.lod`, `mcp.resolver`, `mcp.yaml_out`.
- Line & Branch Coverage: **97.07%** (exceeds `>= 95%` requirement).
- Full MCP Test Suite: 47 / 47 tests passed in 0.22s.
- Target Ticket Suite: 35 / 35 tests passed in 2.25s.
- Resolution Endpoint Suite: 7 / 7 tests passed in 1.70s.
- `kanban-agent validate-qa-packet --deterministic-only`: **Grade A READY** (7/7 passed).

---

### 4. Verdict

All blocking findings (F1, F2) and advisories (F3) have been addressed with rigorous architectural precision, zero data leaks, and zero non-ASCII dashes.

APPROVED
