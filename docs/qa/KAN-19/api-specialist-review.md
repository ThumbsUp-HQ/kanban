# API Specialist Review: KAN-19 (KB-P3-AUDIT-13)

- Ticket: KAN-19
- Title: Implement Progressive-Disclosure Self-Correcting YAML Error UX Across All MCP Surfaces
- Reviewer: api-spec-2 (Clean-Room Backend / API / Security Specialist)
- Date: 2026-11-20
- Worktree: `/home/adamoutler/.gemini/antigravity-cli/worktrees/cec3609e-f993-4e05-b8c5-be0070e6116c/swarm-b-kan19-rc3-a8e13b04`
- Branch: `fix/KAN-19-rc3`
- Commit: `b559f55`
- Status: STATUS: APPROVED

---

## 1. Executive Summary

This clean-room API and Architecture audit inspects ticket KAN-19 on remediation branch `fix/KAN-19-rc3` (commit `b559f55`). The ticket implements self-correcting progressive-disclosure YAML error handling across all MCP surfaces (`/mcp/agent`, `/mcp/docs`, `/mcp/admin`), fixes the JIT-help bypass regression, guards `custom_fields` parameter handling to `update_ticket`, corrects the self-correction CLI example in `manage_cycles_and_modules` to `--action=list_cycles`, aligns all wiki CLI and error documentation with runtime contracts, programmatically regenerates all 10 error samples, and verifies 354 passing unit tests with `>= 95%` coverage on every touched MCP file (overall 97%).

The implementation adheres to all architectural invariants, schema validation requirements, and API standards:
1. `KbMcpError` in `mcp/errors.py` is extended with structured remediation fields (`field`, `valid_options`, `did_you_mean`, `fix_hint`, `cli_example`, `closest_match`), serialized via `InlineSafeDumper` (`strip_nulls=True`) to maintain a minimal token footprint for LLM context windows.
2. Pre-dispatch schema validation in `mcp/protocol.py` intercepts unknown parameters, missing required arguments, type mismatches, and enum violations before tool handlers execute. It leverages `SEMANTIC_ALIASES` and fuzzy string matching (`difflib.get_close_matches`) to supply actionable corrections and ready-to-run CLI examples.
3. JIT-help handling in `mcp/protocol.py` recognizes all standard JIT help parameters (`identifier`, `action`, `source`, `id`, `project`, `summary`) before pre-dispatch validation runs, ensuring seamless JIT assistance.
4. Parameter check for `custom_fields` in `mcp/protocol.py:1196` is safely scoped to `spec.name == "update_ticket"`.
5. `_map_cycle_error` in `mcp/surfaces/admin/manage_cycles_and_modules.py:197` formats `--action=list_cycles`, matching `MANAGE_CYCLES_AND_MODULES_SCHEMA` enum choices.
6. Domain error handlers in `/mcp/agent`, `/mcp/docs`, and `/mcp/admin` expose detailed conflict recovery information (`INVALID_TRANSITION`, `CONFLICT_ETAG`, `ALREADY_PROMOTED`, `PATCH_TARGET_NOT_FOUND`).
7. Full architectural layering is preserved: `mcp` maintains zero runtime imports from `database`.
8. Full test suite: 354 passed, 0 failed in 52.51s, with every touched file reaching `>= 95%` coverage:
   - `mcp/errors.py`: 100%
   - `mcp/internal_client.py`: 97%
   - `mcp/protocol.py`: 95%
   - `mcp/surfaces/admin/manage_cycles_and_modules.py`: 97%
   - `mcp/surfaces/agent/transition_ticket.py`: 95%
   - `mcp/surfaces/agent/update_ticket.py`: 97%
   - `mcp/surfaces/docs/update.py`: 96%
   - Overall touched files coverage: 97%.
9. Zero em-dashes or en-dashes are used across code, tests, YAML samples, and wiki documentation.

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
- JIT Help Hardening:
  - Bypasses argument schema validation when any parameter (`identifier`, `action`, `source`, `id`, `project`, `summary`) equals `"help"`, cleanly returning tool guidance and schema information without false positive validation errors.
- Target Scoping:
  - `custom_fields` parameter warning in `_validate_tool_arguments_schema` is explicitly guarded with `spec.name == "update_ticket"`.

### 2.3 Surface-Level Domain Error Hardening
- `/mcp/agent`:
  - `transition_ticket`: When an illegal workflow transition is requested (`INVALID_TRANSITION`), it lists `valid_options` of allowed next states and provides an updated `cli_example`.
  - `update_ticket`: Concurrency conflicts (`CONFLICT_ETAG`) return the current ETag and a pre-formatted retry command.
- `/mcp/docs`:
  - `update`: When attempting to promote an already-promoted sticky (`ALREADY_PROMOTED`), it provides direct links and keys to the existing doc.
  - Patch disambiguation: When `original_text` does not match, fuzzy line scanning identifies candidate line numbers and context snippets (`PATCH_TARGET_NOT_FOUND` / `PATCH_TARGET_AMBIGUOUS`) with `line_start`, `line_end`, `similarity`, and `snippet`.
- `/mcp/admin`:
  - `manage_cycles_and_modules`: Subcommand dispatch errors provide valid action options and closest match (`--action=list_cycles`).

### 2.4 Programmatic Error Sample Verification (`progressive-error-samples.yaml`)
- Verified all 10 captured error samples in `docs/qa/KAN-19/progressive-error-samples.yaml`.
- Error outputs were programmatically generated from the live `McpProtocolHandler` and `KbMcpError.to_yaml()` runtime code, ensuring 100% exact fidelity including `hint:` fields.

---

## 3. Dependency, Layering & Code Cleanliness Audit

- External Dependencies: 0 new external dependencies added.
- Layering Contracts: `uv run lint-imports` verified 2 kept, 0 broken (`agent -> mcp -> kanban -> database`; `mcp` does not import `database`).
- Static Analysis:
  - `uv run ruff check .`: 0 errors.
  - `uv run mypy mcp/`: 0 errors across 113 source files.
  - `python3 -m scripts.check_no_dashes --all`: 0 errors.
- Clean Patch Artifact: `docs/qa/KAN-19/git-diff.patch` verified to contain zero `docs/qa/*` files.
- Authoritative Wiki Documentation: `thumbs-up-kanban.wiki/MCP-Tools-Reference.md` updated at `58aa9cd` with 0 em/en-dashes.

---

## 4. Test Coverage Audit

- Pytest Suite:
  - Full suite: 354 passed, 0 failed in 52.51s.
  - Every touched file meets the `>= 95%` coverage threshold:
    - `mcp/errors.py`: 100%
    - `mcp/internal_client.py`: 97%
    - `mcp/protocol.py`: 95%
    - `mcp/surfaces/admin/manage_cycles_and_modules.py`: 97%
    - `mcp/surfaces/agent/transition_ticket.py`: 95%
    - `mcp/surfaces/agent/update_ticket.py`: 97%
    - `mcp/surfaces/docs/update.py`: 96%
    - Total touched files: 97% coverage.
- Verbatim raw test output is preserved in `docs/qa/KAN-19/unit-test-results.txt`.

---

## 5. Verification Verdict

All MCP progressive disclosure error contracts, schema validations, JIT-help routes, wiki documentation, and unit test coverage thresholds are verified and approved.

STATUS: APPROVED
Reviewed by: api-spec-2
