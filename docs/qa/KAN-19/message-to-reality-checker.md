# Reality-Checker Verification Packet: KAN-19

## Summary of Implementation

Ticket **KAN-19** (`[KB-P3-AUDIT-13] Implement Progressive-Disclosure Self-Correcting YAML Error UX (did_you_mean, valid_options, cli_example) Across All MCP Surfaces (3 Problems)`) has been fully remediated and verified on branch `fix/KAN-19-rc3` off `main` (`4067eb4`).

The remediation directly reconciles all code and wiki contract items caught by Clean-Room Reality-Checker (`c7959a7c`):
1. **Fix Broken `--action=list` Self-Correction in `manage_cycles_and_modules` (`mcp/surfaces/admin/manage_cycles_and_modules.py` and `thumbs-up-kanban.wiki/MCP-Tools-Reference.md`):**
   - Corrected line 197 self-correction example in `mcp/surfaces/admin/manage_cycles_and_modules.py` from `--action=list` to `--action=list_cycles` matching `MANAGE_CYCLES_AND_MODULES_SCHEMA` enum.
   - Added regression assertion in `mcp/tests/admin/test_manage_cycles_and_modules.py` (lines 586-589) verifying `e2.cli_example` includes `--action=list_cycles`.
   - Updated `thumbs-up-kanban.wiki/MCP-Tools-Reference.md` (lines 288, 294) `action` enum list to include all 17 valid operations (`list_cycles`, `create_cycle`, `update_cycle`, `start_cycle`, `complete_cycle`, `rollover`, `list_modules`, `create_module`, `update_module`, `list_views`, `create_view`, `update_view`, `bind_project_repo`, `list_repo_bindings`, `refresh_repo_binding`, `unbind_project_repo`, `help`) and CLI example to `--action="list_cycles"`.
2. **Align Wiki Examples 6 and 9 and `progressive-error-samples.yaml` Sample 7 with Actual Runtime Output:**
   - In `thumbs-up-kanban.wiki/MCP-Tools-Reference.md` Example 6 (`CONFLICT_ETAG`) and `docs/qa/KAN-19/progressive-error-samples.yaml` (`sample_7_domain_conflict_etag`), aligned with actual `mcp/surfaces/agent/update_ticket.py:368-381` runtime output: no `field: if_match`, `hint: 'current etag: ...'`, `fix_hint`, and `current_etag` after `cli_example`.
   - In `thumbs-up-kanban.wiki/MCP-Tools-Reference.md` Example 9 (`PATCH_TARGET_AMBIGUOUS`), aligned with actual `mcp/surfaces/docs/update.py:347-362` runtime output: `message: Target text appears 2 times in document; provide more surrounding context`, `field: original_text`, `hint: Include unique surrounding lines to disambiguate the target region.`, `fix_hint: Target text appears 2 times at lines [1, 3]. Include unique surrounding lines in original_text to disambiguate.`, `cli_example`, `line_hints: [1, 3]`, and `count: 2`.
   - Committed in `./thumbs-up-kanban.wiki` on `fix/KAN-19-rc3` (commit `58aa9cd`, 0 em/en-dashes) and regenerated clean `docs/qa/KAN-19/wiki-diff.patch` against pre-KAN-19 base `5e93c1a`.
3. **Refreshed Proof Packet and Dual Specialist Reviews:**
   - 354/354 MCP tests passed in 52.51s with >=95% coverage on all 7 touched files (overall 97% coverage).
   - Clean static analysis: Ruff, MyPy (113 source files), Lint-Imports (2 kept, 0 broken), and 0 em/en-dashes.
   - Restored any stray test artifact modifications (`docs/qa/KAN-18/contract-sample.yaml`, `docs/qa/KANBA-141/taint-canary-db-proof.txt`).
   - Dual specialist reviews (API and UI) re-certified on branch `fix/KAN-19-rc3`.

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
  * `CONFLICT_ETAG`: Returns `extra={"current_etag": fresh_sha}`, actionable `fix_hint`, `hint: current etag: <etag>`, and retry `cli_example` with fresh SHA.
  * `ALREADY_PROMOTED`: Includes `extra={"target_doc_key": target_doc_key}`, `fix_hint`, and `cli_example` pointing directly to the target Doc.
  * `PATCH_TARGET_NOT_FOUND` / `NOT_FOUND`: Populates `closest_match` candidate sections without cross-tenant RLS leakage.
  * `PATCH_TARGET_AMBIGUOUS`: Populates `extra={"line_hints": line_hints, "count": count}`, `hint`, `fix_hint`, and `cli_example`.
- Updated `thumbs-up-kanban.wiki/MCP-Tools-Reference.md`:
  * Documented consolidated 3-tool `/mcp/docs` CLI UX (`kanban-cli-docs search|read|update`).
  * Documented progressive-disclosure self-correcting YAML error contract with 9 real copy-paste YAML samples matching runtime output.
  * Preserved `_Sidebar.md` untouched.
- Programmatically verified error outputs captured in `docs/qa/KAN-19/progressive-error-samples.yaml`.

## Evidence Artifacts

1. **Unit Test Results:** `docs/qa/KAN-19/unit-test-results.txt`
   * Full suite: 354 passed, 0 failed in 52.51s
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
   * `docs/qa/KAN-19/wiki-diff.patch`: Clean patch of wiki updates against `5e93c1a`
   * `docs/qa/KAN-19/changed-files-manifest.txt`: List of touched code and test files
   * `docs/qa/KAN-19/progressive-error-samples.yaml`: Real YAML outputs captured via test harness
