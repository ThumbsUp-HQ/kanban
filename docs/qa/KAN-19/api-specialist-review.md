# API Specialist Review: KAN-19 (KB-P3-AUDIT-13)

- Ticket: KAN-19
- Title: Implement Progressive-Disclosure Self-Correcting YAML Error UX Across All MCP Surfaces
- Reviewer: api-spec-2 (Clean-Room Backend / API / Security Specialist)
- Date: 2026-11-20
- Worktree: `/home/adamoutler/.gemini/antigravity-cli/worktrees/cec3609e-f993-4e05-b8c5-be0070e6116c/swarm-b-kan19-rc4-a70467c2`
- Branch: `fix/KAN-19-rc4`
- Commit: `7d0889b910c626e4923c1e2661c0b5d5addcb1d3`
- Wiki Commit: `535fe9e06b544b652f9a3ed3bd1c245a9053407f`
- Status: STATUS: APPROVED

---

## 1. Executive Summary

This clean-room API and Architecture audit inspects ticket KAN-19 on remediation branch `fix/KAN-19-rc4` (commit `7d0889b9`). The ticket implements self-correcting progressive-disclosure YAML error handling across all MCP surfaces (`/mcp/agent`, `/mcp/docs`, `/mcp/admin`), fixes the JIT-help bypass regression, guards `custom_fields` parameter handling to `update_ticket`, corrects the self-correction CLI example in `manage_cycles_and_modules` to `--action=list_cycles`, enriches all `NOT_FOUND` / `ENTITY_NOT_FOUND` / `SECTION_NOT_FOUND` paths with `fix_hint` and `cli_example` self-correction guidance, aligns all wiki CLI and error documentation with runtime contracts, wraps `<pre>` code blocks in Markdown viewers, and verifies 356 passing unit tests with `>= 95%` coverage on every touched MCP file (overall 96%).

The implementation adheres to all architectural invariants, schema validation requirements, and API standards:
1. `KbMcpError` in `mcp/errors.py` is extended with structured remediation fields (`field`, `valid_options`, `did_you_mean`, `fix_hint`, `cli_example`, `closest_match`), serialized via `InlineSafeDumper` (`strip_nulls=True`) to maintain a minimal token footprint for LLM context windows.
2. Pre-dispatch schema validation in `mcp/protocol.py` intercepts unknown parameters, missing required arguments, type mismatches, and enum violations before tool handlers execute. It leverages `SEMANTIC_ALIASES` and fuzzy string matching (`difflib.get_close_matches`) to supply actionable corrections and ready-to-run CLI examples.
3. JIT-help handling in `mcp/protocol.py` recognizes all standard JIT help parameters (`identifier`, `action`, `source`, `id`, `project`, `summary`) before pre-dispatch validation runs, ensuring seamless JIT assistance.
4. Parameter check for `custom_fields` in `mcp/protocol.py:1196` is safely scoped to `spec.name == "update_ticket"`.
5. `_map_cycle_error` in `mcp/surfaces/admin/manage_cycles_and_modules.py:197` formats `--action=list_cycles`, matching `MANAGE_CYCLES_AND_MODULES_SCHEMA` enum choices.
6. All `NOT_FOUND` / `ENTITY_NOT_FOUND` / `SECTION_NOT_FOUND` domain error handlers across `/mcp/agent`, `/mcp/docs`, and `/mcp/admin` expose detailed self-correcting information (`fix_hint` and `cli_example`) so callers immediately receive discovery suggestions rather than dead-ends.
7. Explicit regression test `test_not_found_regression_progressive_disclosure` confirms both `read_ticket` and `docs update` return structured YAML containing `code: NOT_FOUND`, `hint:`, `fix_hint:`, and pre-populated `cli_example:`.
8. Full architectural layering is preserved: `mcp` maintains zero runtime imports from `database`.
9. Full test suite: 356 passed, 0 failed in 46.07s, with every touched file reaching `>= 95%` coverage:
   - `mcp/errors.py`: 100%
   - `mcp/internal_client.py`: 96%
   - `mcp/protocol.py`: 95%
   - `mcp/surfaces/admin/manage_cycles_and_modules.py`: 97%
   - `mcp/surfaces/agent/read_ticket.py`: 96%
   - `mcp/surfaces/agent/transition_ticket.py`: 95%
   - `mcp/surfaces/agent/update_ticket.py`: 97%
   - `mcp/surfaces/docs/update.py`: 97%
   - Overall touched files coverage: 96%.
10. Frontend and wiki alignment: 434/434 Vitest unit tests pass across 38 suites, CSS token audit passed 4/4, wiki Example 7 key ordering aligned with runtime serialization, tool count reconciled to 24 in `_Sidebar.md`, and 0 em-dashes or en-dashes across codebase and wiki.

---

## 2. API Contract & Progressive-Disclosure Audit

### 2.1 Extended Error Schema (`mcp/errors.py`)
- Schema Payload:
  - Base fields: `code` (string from `McpErrorCode`), `message` (string).
  - Progressive-disclosure fields:
    - `field`: Specific parameter causing validation failure.
    - `valid_options`: Permitted enum choices or valid tool names.
    - `did_you_mean`: High-confidence fuzzy matches or semantic alias targets.
    - `fix_hint`: Human/agent-readable remediation instructions.
    - `cli_example`: Immediately runnable CLI invocation pre-populated with caller arguments.
    - `closest_match`: Snippet and line range fuzzy matching for document patch failures (`line_start`, `line_end`, `similarity`, `snippet`).
- Token Efficiency: All optional fields evaluate to `None` by default and are pruned during serialization via `strip_nulls=True`, avoiding token bloat.

### 2.2 Protocol-Layer Validation & Semantic Correction (`mcp/protocol.py`)
- Semantic Aliasing:
  - Maps common intuitive aliases (`body` -> `content`, `ticket_id` -> `identifier`, `ticket` -> `identifier`, `title` -> `summary`, `originalText` -> `original_text`, etc.).
- Pre-Dispatch Validation:
  - Missing required fields: Identifies missing parameters and formats a CLI example retaining previously supplied arguments.
  - Unknown fields: Recommends valid parameters via alias mapping or fuzzy matching (`querry` -> `query`).
  - Enum validation: Discloses valid options and identifies case-insensitive or close matches.
  - Type & pattern validation: Explains expected types or formats (e.g., 64-hex SHA-256 ETag) with helpful placeholders.

### 2.3 Domain Conflict & Not-Found Remediation
- Concurrency conflicts (`CONFLICT_ETAG`): Includes current ETag and formatted command with `--if-match="<current_etag>"`.
- Invalid state transitions (`INVALID_TRANSITION`): Enumerates currently available destination states.
- Sticky promotion conflicts (`ALREADY_PROMOTED`): Points to promoted Doc key and provides `kanban-cli-docs update --id="DOC-..."`.
- Missing entities (`NOT_FOUND` / `ENTITY_NOT_FOUND` / `SECTION_NOT_FOUND`):
  - In `internal_client.py`, unmapped 404 responses automatically synthesize `fix_hint` advising callers to verify the identifier or run search tools.
  - Pre-populates contextual `cli_example`: e.g. `kanban-cli-agent search_tickets --query="KAN-99999"` or `kanban-cli-docs search --query="DOC-99999"`.
  - Specific tools (`read_ticket`, `update_ticket`, `link_objects`, `docs/update`, `docs/search`, `docs/read_doc`, `admin/architect_project`, `admin/manage_cycles_and_modules`) provide dedicated discovery suggestions.

---

## 3. Layering, Static Quality & Security Verification

- Layering Invariant: Zero `database` imports inside `mcp/` (`uv run lint-imports` confirmed 2 kept, 0 broken).
- Static Quality:
  - `uv run ruff check .`: 0 errors.
  - `uv run ruff format --check .`: Clean (1880 files formatted).
  - `uv run mypy mcp/`: 0 errors across 113 source files.
  - `python3 -m scripts.check_no_dashes --all`: 0 em-dashes, 0 en-dashes.
  - `python3 -m scripts.check_no_dashes /home/adamoutler/kanban/thumbs-up-kanban.wiki`: 0 em-dashes, 0 en-dashes.
- Clean Patch Artifacts: `docs/qa/KAN-19/git-diff.patch` and `wiki-diff.patch` verified to exclude extraneous temporary files.

---

## 4. Test Coverage Audit

- Pytest Coverage:
  - 356 tests passed in 46.07s across `mcp/tests/`.
  - Unraisable mock warnings eliminated in `mcp/tests/test_app.py`.
  - Touched files coverage breakdown:
    * `mcp/errors.py`: 100%
    * `mcp/internal_client.py`: 96%
    * `mcp/protocol.py`: 95%
    * `mcp/surfaces/admin/manage_cycles_and_modules.py`: 97%
    * `mcp/surfaces/agent/read_ticket.py`: 96%
    * `mcp/surfaces/agent/transition_ticket.py`: 95%
    * `mcp/surfaces/agent/update_ticket.py`: 97%
    * `mcp/surfaces/docs/update.py`: 97%
    * Total touched coverage: 96% (exceeds >= 95% mandate).
- Web Vitest Suite:
  - 434 tests passed across 38 suites.
  - `cssTokensAudit.test.ts`: Passed 4/4 (100% canonical tokens, 0 inline styles).
- Verbatim raw test output is preserved in `docs/qa/KAN-19/unit-test-results.txt`.

---

## 5. Verification Verdict

All MCP protocol schema enhancements, progressive-disclosure error disclosures, NOT_FOUND self-correction hints, documentation alignments, and test coverage standards are verified and approved.

STATUS: APPROVED
Reviewed by: api-spec-2
