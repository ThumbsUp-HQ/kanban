# Forensic QA Verification Packet: KANBA-62

## 1. Ticket Metadata
- **Ticket ID:** `KANBA-62` (`KB-P4-01`)
- **Module:** `mcp` (`kanban-mcp`)
- **Title:** MCP server skeleton: 3 isolated Streamable HTTP mounts + internal kanban-api client
- **Git Branch:** `feat/KANBA-62` in isolated worktree `/tmp/kb-wt-KANBA-62`
- **Target Specification:** `docs/tickets/KB-P4-01.md`, `docs/ARCHITECTURE_AND_PRODUCT_SPEC.md` (S11.1, S2.3, S2.4, S2.1), `AGENTS.md`

## 2. Scoped Definition of Done Audit

| Item | Requirement | Status | Evidence / Verification |
| :--- | :--- | :---: | :--- |
| 1 | Target Files Implementation | PASS | `mcp/app.py`, `mcp/protocol.py`, `mcp/registry.py`, `mcp/errors.py`, `mcp/internal_client.py`, `mcp/settings.py` implemented cleanly. |
| 2 | No PyPI `mcp` SDK | PASS | Confirmed: `uv.lock` contains zero `mcp` package entries. Cryptographically pinned `httpx==0.28.1` and `h2==4.4.1` with SHA256 hashes. |
| 3 | Unit Tests Passing & Coverage >= 95% | PASS | 19 tests passing in 1.07s; 97.73% line+branch coverage across `mcp` (recorded in `unit-test-results.txt`). |
| 4 | Build / Type / Lint Clean | PASS | `ruff check mcp` (clean), `ruff format --check mcp` (clean), `mypy --strict mcp` (clean), `lint-imports` (clean, 2 kept 0 broken), `make license` (0 violations), `check_no_dashes --all` (clean). |
| 5 | Transcript Captured & Redacted | PASS | `mcp-transcript.txt` captured via `KB_MCP_TRANSCRIPT_PATH` with initialize, tools/list, ping_agent, cross-surface ping_admin (NOT_FOUND), and zero unredacted `kb_` tokens. |
| 6 | Forensic Proof Packet Complete | PASS | All 9 required artifacts exist in `docs/qa/KANBA-62/`. |

## 3. Architecture & Security Invariants
- **Import Boundary (Priority #0):** `mcp/` imports zero code from `database/`. Enforced via forbidden contract in `pyproject.toml` and verified by `uv run lint-imports` (`import-linter.txt`).
- **Surface Isolation:** Distinct `ToolRegistry` instances for `/mcp/agent`, `/mcp/docs`, and `/mcp/admin`. Cross-surface execution is blocked at runtime (`Tool 'ping_admin' not found on surface 'agent'`).
- **Streamable HTTP JSON-RPC 2.0 Compliance:** Adheres to spec version `2025-06-18`. Methods supported: `initialize`, `notifications/initialized`, `ping`, `tools/list`, `tools/call`. Standalone SSE streams rejected (HTTP 405). Batch requests rejected (HTTP 400). Request bodies capped at 1 MiB.
- **DNS-Rebinding Protection:** Origin header validated against `allowed_origins` (HTTP 403 on mismatch).
- **Internal mTLS HTTP/2 Client:** `KanbanApiClient` forwards caller subject credential in `X-KB-Subject-Token` and session id in `X-KB-MCP-Session`. Rejects plaintext `http://` in mTLS mode. Connect timeout: 2.0s, read/write: 10.0s, pool: 2.0s. Response bodies > 8 MiB aborted with `UPSTREAM_ERROR`. RFC 7807 problem details mapped to canonical `McpErrorCode`s.
- **Zero Unicode Dashes:** Pure ASCII hyphens `-` across all code and documentation files.

## 4. Test Suite Traceability
- **Test Case 1 (mcp/tests/test_protocol.py):** Positive `initialize` and `tools/list` on all 3 mounts (`/mcp/agent`, `/mcp/docs`, `/mcp/admin`).
- **Test Case 2 (mcp/tests/test_registry_isolation.py):** Surface validation, freeze mutation rejection, and cross-surface isolation.
- **Test Case 3 (mcp/tests/test_protocol.py):** Protocol error codes (-32700, -32600, -32601, -32602) and HTTP negative constraints (405, 413, 404, 403, 400).
- **Test Case 4 (mcp/tests/test_protocol.py):** Session store capacity LRU eviction on 10,001st session and idle TTL expiry.
- **Test Case 5 (mcp/tests/test_internal_client.py):** Upstream problem status mapping (404, 409, 412, 422, 429, 503), streaming response abort on bodies > 8 MiB, and plaintext rejection.
- **Test Case 6 (mcp/tests/test_protocol.py & conftest.py):** Transcript recording and credential redaction (`Authorization` and `X-KB-Subject-Token`).

## 5. Evidence Artifact Index
- `docs/qa/KANBA-62/git-diff.patch`
- `docs/qa/KANBA-62/unit-test-results.txt`
- `docs/qa/KANBA-62/build-check.txt`
- `docs/qa/KANBA-62/mcp-transcript.txt`
- `docs/qa/KANBA-62/import-linter.txt`
- `docs/qa/KANBA-62/dependency-evaluation.md`
- `docs/qa/KANBA-62/api-specialist-review.md`
- `docs/qa/KANBA-62/ui-specialist-review.md`
- `docs/qa/KANBA-62/message-to-reality-checker.md`
