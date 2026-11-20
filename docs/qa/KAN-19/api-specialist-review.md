# API Specialist Review: KAN-19 (KB-P3-AUDIT-13)

- Ticket: KAN-19
- Title: Implement Progressive-Disclosure Self-Correcting YAML Error UX Across All MCP Surfaces
- Reviewer: api-spec-2 (Clean-Room Backend / API / Security Specialist)
- Date: 2026-11-20
- Worktree: `/home/adamoutler/.gemini/antigravity-cli/worktrees/cec3609e-f993-4e05-b8c5-be0070e6116c/swarm-b-kan19-a63c3819`
- Branch: `feat/KAN-19`
- Status: STATUS: APPROVED

---

## 1. Executive Summary

This clean-room API and Architecture audit inspects ticket KAN-19 on branch `feat/KAN-19` (`b8eacc6` off `887e7e0`). The ticket implements self-correcting progressive-disclosure YAML error handling across all MCP surfaces (`/mcp/agent`, `/mcp/docs`, `/mcp/admin`).

The implementation adheres to all architectural invariants, schema validation requirements, and API standards:
1. `KbMcpError` in `mcp/errors.py` is extended with structured remediation fields (`field`, `valid_options`, `did_you_mean`, `fix_hint`, `cli_example`, `closest_match`), serialized via `InlineSafeDumper` (`strip_nulls=True`) to maintain a minimal token footprint for LLM context windows.
2. Pre-dispatch schema validation in `mcp/protocol.py` intercepts unknown parameters, missing required arguments, type mismatches, and enum violations before tool handlers execute. It leverages `SEMANTIC_ALIASES` and fuzzy string matching (`difflib.get_close_matches`) to supply actionable corrections and ready-to-run CLI examples.
3. Domain error handlers in `/mcp/agent`, `/mcp/docs`, and `/mcp/admin` expose detailed conflict recovery information (`INVALID_TRANSITION`, `CONFLICT_ETAG`, `ALREADY_PROMOTED`, `PATCH_TARGET_NOT_FOUND`).
4. Full architectural layering is preserved: `mcp` maintains zero runtime imports from `database`.
5. 73 unit tests pass in `mcp/tests/` with 100% coverage on `mcp/errors.py` and >= 90% on all touched MCP protocol and surface files.
6. Zero em-dashes or en-dashes are used across code, tests, YAML samples, and wiki documentation.

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
    - `closest_match`: Snippet and line range fuzzy matching for document patch failures.
- Token Efficiency: All optional fields evaluate to `None` by default and are pruned during serialization via `strip_nulls=True`, avoiding token bloat.

### 2.2 Protocol-Layer Validation & Semantic Correction (`mcp/protocol.py`)
- Semantic Aliasing:
  - Maps common intuitive aliases (`body` -> `content`, `ticket_id` -> `identifier`, `ticket` -> `identifier`, `title` -> `summary`, `originalText` -> `original_text`, etc.).
- Pre-Dispatch Validation:
  - Missing required fields: Identifies missing parameters and formats a CLI example retaining previously supplied arguments.
  - Unknown fields: Recommends valid parameters via alias mapping or fuzzy matching (`querry` -> `query`).
  - Enum validation: Discloses valid options and identifies case-insensitive or close matches.
  - Type & pattern validation: Explains expected types or formats (e.g., 64-hex SHA-256 ETag) with helpful placeholders.

### 2.3 Surface-Level Domain Error Hardening
- `/mcp/agent`:
  - `transition_ticket`: When an illegal workflow transition is requested (`INVALID_TRANSITION`), it lists `valid_options` of allowed next states and provides an updated `cli_example`.
  - `update_ticket`: Concurrency conflicts (`CONFLICT_ETAG`) return the current ETag and a pre-formatted retry command.
- `/mcp/docs`:
  - `update`: When attempting to promote an already-promoted sticky (`ALREADY_PROMOTED`), it provides direct links and keys to the existing doc.
  - Patch disambiguation: When `original_text` does not match, fuzzy line scanning identifies candidate line numbers and context snippets (`PATCH_TARGET_NOT_FOUND` / `PATCH_TARGET_AMBIGUOUS`).
- `/mcp/admin`:
  - `manage_cycles_and_modules`: Subcommand dispatch errors provide valid action options and closest match.

### 2.4 Representative Error Verification (`progressive-error-samples.yaml`)
- Verified all 10 captured error samples in `docs/qa/KAN-19/progressive-error-samples.yaml`.
- Error outputs validate cleanly against the progressive disclosure schema.

---

## 3. Dependency, Layering & Code Cleanliness Audit

- External Dependencies: 0 new external dependencies added.
- Layering Contracts: `uv run lint-imports` verified 2 kept, 0 broken (`agent -> mcp -> kanban -> database`; `mcp` does not import `database`).
- Static Analysis:
  - `uv run ruff check .`: 0 errors.
  - `uv run mypy`: 0 errors across 113 source files.
  - `python3 -m scripts.check_no_dashes --all`: 0 errors.
- Clean Patch Artifact: `docs/qa/KAN-19/git-diff.patch` verified to contain zero `docs/qa/*` files.
- Authoritative Wiki Documentation: `thumbs-up-kanban.wiki/MCP-Tools-Reference.md` updated at `d8393af` with 0 em/en-dashes.

---

## 4. Test Coverage Audit

- Pytest Suite:
  - 73 passed in 20.71s across `mcp/tests/`.
  - `mcp/errors.py`: 100% coverage.
  - `mcp/surfaces/docs/update.py`: 95% coverage.
  - `mcp/internal_client.py`: 91% coverage.
  - `mcp/protocol.py`: 90% coverage.
- Verbatim raw test output is preserved in `docs/qa/KAN-19/unit-test-results.txt`.

---

## 5. Verification Verdict

All MCP progressive disclosure error contracts, schema validations, and DX ergonomics are verified and approved.

STATUS: APPROVED
Reviewed by: api-spec-2
