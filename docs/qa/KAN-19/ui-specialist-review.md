# UI/UX Specialist Review: KAN-19

## Audit Metadata
- Ticket ID: KAN-19 ([KB-P3-AUDIT-13])
- Title: Implement Progressive-Disclosure Self-Correcting YAML Error UX Across All MCP Surfaces
- Reviewer: ui-spec-2 (Clean-Room UI/UX Specialist)
- Date: 2026-11-20
- Target Worktree: `/home/adamoutler/.gemini/antigravity-cli/worktrees/cec3609e-f993-4e05-b8c5-be0070e6116c/swarm-b-kan19-rc2-7e0a322e`
- Target Branch: `fix/KAN-19-rc2`
- Base Commit: `4a3aaa9`
- Head Commit: `9191344`
- STATUS: APPROVED

---

## Executive Summary
This clean-room review evaluates the agent ergonomics, developer experience (DX), command-line interface (CLI) mental models, and progressive-disclosure YAML error UX for ticket KAN-19 ([KB-P3-AUDIT-13]) on remediation branch `fix/KAN-19-rc2` (commit `9191344`).

The implementation provides an intuitive, self-correcting error experience for autonomous AI agents and CLI operators interfacing with 👍kanban through MCP:
1. **Self-Correcting YAML Error Schema (`mcp/errors.py`):**
   - Extended `KbMcpError` with structured remediation fields serialized via `InlineSafeDumper` (`strip_nulls=True`):
     - `field`: The exact parameter or property causing validation failure.
     - `valid_options`: Permitted enum values or allowed targets.
     - `did_you_mean`: High-confidence fuzzy suggestions or semantic aliases.
     - `hint` / `fix_hint`: Actionable remediation guidance for autonomous agent single-turn self-correction.
     - `cli_example`: Immediately runnable CLI invocation pre-filled with valid parameters.
     - `closest_match`: Snippet and line range fuzzy matching for document patch failures (`line_start`, `line_end`, `similarity`, `snippet`).
2. **Pre-Dispatch Schema Validation & Semantic Aliasing (`mcp/protocol.py`):**
   - Intercepts unknown parameters, missing required arguments, and type/enum violations before tool execution.
   - Leverages semantic alias mappings (`body` -> `content`, `ticket_id` -> `identifier`, etc.) and `difflib.get_close_matches` (`querry` -> `query`) to guide agents directly to the valid parameter name.
   - JIT-help handling intercepts all standard JIT parameters (`identifier`, `action`, `source`, `id`, `project`, `summary`) before pre-dispatch validation runs.
   - The `custom_fields` parameter warning is properly guarded to `spec.name == "update_ticket"`.
3. **Domain Error Hardening Across All Surfaces:**
   - `/mcp/agent`: `INVALID_TRANSITION` enumerates allowed next workflow states; `CONFLICT_ETAG` provides `current_etag` and retry command.
   - `/mcp/docs`: `ALREADY_PROMOTED` links directly to target Doc key; `PATCH_TARGET_NOT_FOUND` / `PATCH_TARGET_AMBIGUOUS` provides fuzzy line numbers and context snippets.
   - `/mcp/admin`: Unknown subcommands guide operators with closest match and CLI examples.
4. **Authoritative Documentation in Wiki (`thumbs-up-kanban.wiki/MCP-Tools-Reference.md` commit `3358428`):**
   - Aligned `configure_workspace` required action parameter and CLI example to `--action="get"`, matching `valid_options: [get, update, help]`.
   - Updated Example 8 (`PATCH_TARGET_NOT_FOUND`) `closest_match` structure to reflect runtime fields: `line_start`, `line_end`, `similarity`, and `snippet`.
   - Aligned canonical YAML error examples (1-9) with runtime `KbMcpError.to_yaml()` output, including mirrored `hint:` where `fix_hint` is provided.

---

## Ergonomics & Developer Experience Audit

### 1. Progressive-Disclosure Error Structure (`progressive-error-samples.yaml`)
- Verified all 10 representative error scenarios in `docs/qa/KAN-19/progressive-error-samples.yaml`, programmatically regenerated from live runtime invocations:
  - Unknown parameter with semantic alias: Maps `body` to `did_you_mean: [content]` with complete `cli_example`.
  - Unknown parameter with typo: Maps `querry` to `did_you_mean: [query, cursor]`.
  - Missing parameter: Recommends missing `title` while retaining other supplied parameters in `cli_example`.
  - Invalid enum value: Discloses `valid_options: [DOC, STICKY, doc, sticky]` and suggests `did_you_mean: [doc]`.
  - Tool not found: Discloses available tools on that surface with closest match.
  - Concurrency conflict (`CONFLICT_ETAG`): Includes current ETag and ready-to-run retry command.
  - Patch target not found: Discloses candidate snippets with line numbers (`line_start`, `line_end`) and similarity scores >= 0.94.
- Output Cleanliness: Prunes all null or empty fields, keeping token footprint minimal for LLM consumption.

### 2. Actionable CLI Mental Model
- Commands use structured, human-legible CLI syntax (`kanban-cli-docs`, `kanban-cli-agent`, `kanban-cli-admin`).
- Eliminates guesswork by pre-populating arguments that the caller already correctly provided.

### 3. Wiki Documentation Alignment
- `thumbs-up-kanban.wiki/MCP-Tools-Reference.md` provides clear code blocks, argument tables, and error examples matching the implementation.
- Contains zero em-dashes or en-dashes.

---

## Code Quality & Standards

### 1. Layer Boundary & Import Invariants
- Verified `uv run lint-imports`: 2 kept, 0 broken.
- `mcp` does not import `database` directly, preserving clean architectural layering.

### 2. Static Analysis & Type Safety
- `uv run ruff check .`: Clean (0 errors).
- `uv run mypy`: Clean (0 errors across 113 source files).
- Strict typing and safe dictionaries used throughout `mcp/protocol.py` and `mcp/errors.py`.

### 3. Punctuation & Style Standard
- Zero em-dashes (`\u2014`) or en-dashes (`\u2013`) in code, tests, YAML fixtures, or wiki documentation. All punctuation uses standard ASCII hyphens (-).

### 4. Test Coverage & Verification
- 354/354 unit tests passing (0 failed) in 44.46s.
- All 7 touched files meet or exceed 95% coverage (overall 97%):
  - `mcp/errors.py`: 100%
  - `mcp/internal_client.py`: 97%
  - `mcp/protocol.py`: 95%
  - `mcp/surfaces/admin/manage_cycles_and_modules.py`: 97%
  - `mcp/surfaces/agent/transition_ticket.py`: 95%
  - `mcp/surfaces/agent/update_ticket.py`: 97%
  - `mcp/surfaces/docs/update.py`: 96%

---

## Verification Checklist

1. [x] Extended `KbMcpError` with progressive-disclosure fields verified
2. [x] Pre-dispatch schema validation and semantic alias correction verified
3. [x] Domain conflict handling (`INVALID_TRANSITION`, `CONFLICT_ETAG`, `ALREADY_PROMOTED`) verified
4. [x] Patch fuzzy matching and disambiguation snippets verified
5. [x] `progressive-error-samples.yaml` programmatic verification confirmed
6. [x] `thumbs-up-kanban.wiki/MCP-Tools-Reference.md` updated and committed on `fix/KAN-19-rc2` (commit `3358428`)
7. [x] Strict ASCII hyphenation verified (0 em/en-dashes across repo and wiki)
8. [x] Python test suite passes: 354 unit tests passing with >= 95% coverage on touched files

---

## Verdict & Certification
STATUS: APPROVED

All API ergonomics, CLI user experience, YAML formatting, and documentation standards have been verified and certified. Ready for dual specialist signoff, coordinator merge into `main`, and clean-room Reality-Checker QA.
