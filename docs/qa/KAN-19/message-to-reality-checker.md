# Reality-Checker Verification Packet: KAN-19

## Summary of Implementation

Ticket **KAN-19** (`[KB-P3-AUDIT-13] Implement Progressive-Disclosure Self-Correcting YAML Error UX (did_you_mean, valid_options, cli_example) Across All MCP Surfaces (3 Problems)`) has been implemented on branch `fix/KAN-19-rc1` off `main` (`887e7e0`).

The implementation addresses all three scoped problems and satisfies the forensic QA requirements:
- 100% backward compatibility
- Zero forbidden imports (`mcp` strictly does not import `database`)
- Zero em/en-dashes across all public docs, comments, and code
- >=95% unit test coverage across all 7 touched files (overall 97% coverage)
- 100% full MCP test suite passing (354 passed, 0 failed)

### Problem 1: First-Class Progressive-Disclosure Error Model in `KbMcpError`
- Extended `KbMcpError` in `mcp/errors.py` with first-class optional fields:
  * `field: str | None = None`
  * `fix_hint: str | None = None`
  * `cli_example: str | None = None`
  * `valid_options: list[str] | None = None`
  * `did_you_mean: list[str] | None = None`
  * `closest_match: list[dict[str, Any]] | None = None`
- Updated `to_yaml()` to serialize optional fields cleanly via `InlineSafeDumper` (`strip_nulls=True`), omitting any `None` fields.
- Preserved backward compatibility by mirroring `hint` and `fix_hint` when only one is supplied, ensuring existing test assertions pass seamlessly.

### Problem 2: Central Pre-Dispatch Schema Validation in `McpProtocolHandler`
- Implemented `_validate_tool_arguments_schema` in `mcp/protocol.py` before handler execution:
  * **Unknown parameter:** Uses `SEMANTIC_ALIASES` mapping (`body` -> `content`/`description_markdown`, `identifier` -> `id`, `kind` -> `type`, `ticket_id` -> `identifier`, `title` -> `summary`, etc.) combined with `difflib.get_close_matches` to suggest valid keys. Populates `field`, `did_you_mean`, `valid_options`, `fix_hint`, and `cli_example`.
  * **Invalid enum/format/type:** Performs case-insensitive fuzzy matching for enum values, handles union schema types (such as `["array", "object"]`), and provides format pattern validation with intuitive placeholders (`<64-hex-sha256>`).
  * **Missing required parameter:** Generates a pre-filled CLI example retaining valid caller arguments and inserting `<missing_parameter>`.
  * **Unknown tool on surface:** Pre-dispatch tool resolution recommends closest matching tools with surface CLI syntax.
  * **JIT Help bypass:** Ensured progressive-disclosure JIT help (`"help"`) across all parameter aliases (`identifier`, `action`, `source`, `id`, `project`, `summary`) cleanly routes to live help without blocking on required parameters.

### Problem 3: Upgraded Domain Error Paths Across All 3 MCP Surfaces & Wiki Reference
- Enhanced domain error paths across `/mcp/agent`, `/mcp/docs`, and `/mcp/admin`:
  * `INVALID_TRANSITION`: Supplies `valid_options` of allowed target states, actionable `fix_hint`, and corrected `cli_example`.
  * `CONFLICT_ETAG`: Returns `extra={"current_etag": current_sha}`, actionable `fix_hint`, and retry `cli_example` with fresh SHA.
  * `ALREADY_PROMOTED`: Includes `extra={"target_doc_key": target_doc_key}`, `fix_hint`, and `cli_example` pointing directly to the target Doc.
  * `PATCH_TARGET_NOT_FOUND` / `NOT_FOUND`: Populates `closest_match` candidate sections without cross-tenant RLS leakage.
- Updated `thumbs-up-kanban.wiki/MCP-Tools-Reference.md` (committed on `feat/KAN-19` at `d8393af`):
  * Documented consolidated 3-tool `/mcp/docs` CLI UX (`kanban-cli-docs search|create|update`).
  * Documented progressive-disclosure self-correcting YAML error contract with 9 real copy-paste YAML samples.
  * Preserved `_Sidebar.md` untouched.
- Programmatically verified error outputs captured in `docs/qa/KAN-19/progressive-error-samples.yaml`.

## Evidence Artifacts

1. **Unit Test Results:** `docs/qa/KAN-19/unit-test-results.txt`
   * Full suite: 354 passed, 0 failed in 108.83s
   * `mcp/errors.py`: 100% coverage
   * `mcp/internal_client.py`: 97% coverage
   * `mcp/protocol.py`: 95% coverage
   * `mcp/surfaces/admin/manage_cycles_and_modules.py`: 97% coverage
   * `mcp/surfaces/agent/transition_ticket.py`: 95% coverage
   * `mcp/surfaces/agent/update_ticket.py`: 97% coverage
   * `mcp/surfaces/docs/update.py`: 96% coverage
   * Overall coverage across all 7 touched files: 97% (exceeds >=95% gate)
2. **Build and Typecheck:** `docs/qa/KAN-19/build-or-typecheck.txt`
   * `ruff check .`: 0 errors
   * `mypy mcp/`: 0 errors across 113 source files
   * `lint-imports`: 2 kept, 0 broken (`mcp` forbidden from importing `database` KEPT)
   * `check_no_dashes`: 0 dash violations across repository and wiki
3. **Live Stack Verification Proof & Screenshots:**
   * `docs/qa/KAN-19/live-fullstack-proof.txt`: Full-stack JSON-RPC verification against live server
   * `docs/qa/KAN-19/screenshots/live-kan19-mcp-docs-desktop-dark.png`: Dark mode desktop capture
   * `docs/qa/KAN-19/screenshots/live-kan19-mcp-docs-desktop-light.png`: Light mode desktop capture
   * `docs/qa/KAN-19/screenshots/live-kan19-mcp-docs-mobile-light.png`: Mobile viewport capture
4. **Patches and Manifests:**
   * `docs/qa/KAN-19/git-diff.patch`: Clean patch against `887e7e0` excluding `docs/qa/` files
   * `docs/qa/KAN-19/wiki-diff.patch`: Clean patch of wiki updates
   * `docs/qa/KAN-19/changed-files-manifest.txt`: List of touched code and test files
   * `docs/qa/KAN-19/progressive-error-samples.yaml`: Real YAML outputs captured via test harness
