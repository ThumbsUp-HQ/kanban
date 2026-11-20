# UI/UX Specialist Review: KAN-19

## Audit Metadata
- Ticket ID: KAN-19 ([KB-P3-AUDIT-13])
- Title: Implement Progressive-Disclosure Self-Correcting YAML Error UX Across All MCP Surfaces
- Reviewer: ui-spec-2 (Clean-Room UI/UX Specialist)
- Date: 2026-11-20
- Target Worktree: `/home/adamoutler/.gemini/antigravity-cli/worktrees/cec3609e-f993-4e05-b8c5-be0070e6116c/swarm-b-kan19-rc4-a70467c2`
- Target Branch: `fix/KAN-19-rc4`
- Base Commit: `53f7b6e`
- Head Commit: `7d0889b9`
- STATUS: APPROVED

---

## Executive Summary
This clean-room review evaluates the agent ergonomics, developer experience (DX), command-line interface (CLI) mental models, code block text wrapping, and progressive-disclosure YAML error UX for ticket KAN-19 ([KB-P3-AUDIT-13]) on remediation branch `fix/KAN-19-rc4` (commit `7d0889b9`).

The implementation provides an intuitive, self-correcting error experience for autonomous AI agents and CLI operators interfacing with 👍kanban through MCP, complemented by clean, unclipped Markdown rendering:
1. **Self-Correcting YAML Error Schema Across All Error Paths (`mcp/errors.py`):**
   - Extended `KbMcpError` with structured remediation fields serialized via `InlineSafeDumper` (`strip_nulls=True`):
     - `field`: The exact parameter or property causing validation failure.
     - `valid_options`: Permitted enum values or allowed targets.
     - `did_you_mean`: High-confidence fuzzy suggestions or semantic aliases.
     - `hint` / `fix_hint`: Actionable remediation guidance for autonomous agent single-turn self-correction.
     - `cli_example`: Immediately runnable CLI invocation pre-filled with valid parameters.
     - `closest_match`: Snippet and line range fuzzy matching for document patch failures (`line_start`, `line_end`, `similarity`, `snippet`).
     - `line_hints` & `count`: Disambiguation hints for multi-match patch conflicts.
   - Populated `fix_hint` and `cli_example` across all `NOT_FOUND` / `ENTITY_NOT_FOUND` / `SECTION_NOT_FOUND` paths (`read_ticket.py`, `update_ticket.py`, `link_objects.py`, `docs/*`, `admin/*`, `internal_client.py`).
2. **Pre-Dispatch Schema Validation & Semantic Aliasing (`mcp/protocol.py`):**
   - Intercepts unknown parameters, missing required arguments, and type/enum violations before tool execution.
   - Leverages semantic alias mappings (`body` -> `content`, `ticket_id` -> `identifier`, etc.) and `difflib.get_close_matches` (`querry` -> `query`) to guide agents directly to the valid parameter name.
   - JIT-help handling intercepts all standard JIT parameters (`identifier`, `action`, `source`, `id`, `project`, `summary`) before pre-dispatch validation runs.
   - The `custom_fields` parameter warning is properly guarded to `spec.name == "update_ticket"`.
3. **Markdown Code Block Wrapping & Visual Proof:**
   - Enforced `white-space: pre-wrap;`, `overflow-wrap: break-word;`, and `word-break: break-word;` on Markdown `<pre>` blocks in `MarkdownEditor.css` and `DocsWorkspaceView.css`.
   - Verified on refreshed live screenshots in `docs/qa/KAN-19/screenshots/`:
     - `live-kan19-mcp-docs-desktop-dark.png`
     - `live-kan19-mcp-docs-desktop-light.png`
     - `live-kan19-mcp-docs-mobile-light.png`
     Confirming that long YAML options (`valid_options: ...`) wrap smoothly onto next lines without mid-word character clipping or horizontal layout breaking.
4. **Authoritative Documentation in Wiki (`thumbs-up-kanban.wiki` commit `535fe9e`):**
   - Aligned `MCP-Tools-Reference.md` Example 7 (`ALREADY_PROMOTED`) placing `target_doc_key` below `cli_example` to match runtime YAML output order verbatim.
   - Updated `_Sidebar.md` tool count to 24 Tools matching the official MCP catalog.
   - Aligned `manage_cycles_and_modules` action enum with all 17 valid operations and updated CLI example to `--action="list_cycles"`.
   - Aligned Example 6 (`CONFLICT_ETAG`) and Example 9 (`PATCH_TARGET_AMBIGUOUS`) with verbatim runtime contracts and field ordering.

---

## Ergonomics & Developer Experience Audit

### 1. Progressive-Disclosure Error Structure (`progressive-error-samples.yaml`)
- Verified all 11 representative error scenarios in `docs/qa/KAN-19/progressive-error-samples.yaml`, programmatically regenerated from live runtime invocations:
  - Unknown parameter with semantic alias: Maps `body` to `did_you_mean: [content]` with complete `cli_example`.
  - Unknown parameter with typo: Maps `querry` to `did_you_mean: [query, cursor]`.
  - Missing parameter: Recommends missing `title` while retaining other supplied parameters in `cli_example`.
  - Invalid enum value: Discloses `valid_options: [DOC, STICKY, doc, sticky]` and suggests `did_you_mean: [doc]`.
  - Tool not found: Discloses available tools on that surface with closest match.
  - Concurrency conflict (`CONFLICT_ETAG`): Includes current ETag and ready-to-run retry command matching runtime `mcp/surfaces/agent/update_ticket.py`.
  - Sticky already promoted: Directly links to promoted Doc key below CLI example.
  - Patch target not found: Discloses candidate snippets with line numbers (`line_start`, `line_end`) and similarity scores >= 0.94.
  - Patch target ambiguous: Discloses line numbers (`line_hints: [1, 3]`), count (2), and disambiguation hint matching runtime `mcp/surfaces/docs/update.py`.
  - Domain entity not found (`NOT_FOUND`): Discloses plain English guidance and ready-to-run CLI search or list alternative.
- Output Cleanliness: Prunes all null or empty fields, keeping token footprint minimal for LLM consumption.

### 2. Actionable CLI Mental Model
- Commands use structured, human-legible CLI syntax (`kanban-cli-docs`, `kanban-cli-agent`, `kanban-cli-admin`).
- Eliminates guesswork by pre-populating arguments that the caller already correctly provided.
- `manage_cycles_and_modules` self-correction example uses valid `--action=list_cycles` instead of non-existent `list`.

### 3. Wiki Documentation Alignment
- `thumbs-up-kanban.wiki/MCP-Tools-Reference.md` provides clear code blocks, argument tables, and error examples matching the implementation.
- Contains zero em-dashes or en-dashes.

---

## Code Quality & Standards

### 1. Content Security Policy (CSP) Compliance
- Zero inline `style={...}` JSX attributes introduced across all components.
- All styles reside strictly in canonical CSS stylesheets (`MarkdownEditor.css`, `DocsWorkspaceView.css`).
- `cssTokensAudit.test.ts` passes 4/4 tests cleanly.

### 2. Static Analysis & Type Safety
- `uv run ruff check .` and `uv run ruff format --check .`: Clean (0 errors).
- `uv run mypy`: Clean (0 errors across 113 source files).
- `uv run lint-imports`: Clean (2 kept, 0 broken).
- Strict typing and safe dictionaries used throughout `mcp/protocol.py` and `mcp/errors.py`.

### 3. Punctuation & Style Standard
- Zero em-dashes (`\u2014`) or en-dashes (`\u2013`) in code, tests, YAML fixtures, or wiki documentation. All punctuation uses standard ASCII hyphens (-).

### 4. Test Coverage & Verification
- 356/356 unit tests passing (0 failed) in 46.07s.
- All 8 touched files meet or exceed 95% coverage (overall 96%):
  - `mcp/errors.py`: 100%
  - `mcp/internal_client.py`: 97%
  - `mcp/protocol.py`: 95%
  - `mcp/surfaces/admin/manage_cycles_and_modules.py`: 97%
  - `mcp/surfaces/agent/transition_ticket.py`: 95%
  - `mcp/surfaces/agent/update_ticket.py`: 97%
  - `mcp/surfaces/agent/read_ticket.py`: 95%
  - `mcp/surfaces/docs/update.py`: 96%
- Vitest suite: 434 tests passing across 38 suites.

---

## Verification Checklist

1. [x] Extended `KbMcpError` with progressive-disclosure fields verified
2. [x] Pre-dispatch schema validation and semantic alias correction verified
3. [x] Domain conflict handling (`INVALID_TRANSITION`, `CONFLICT_ETAG`, `ALREADY_PROMOTED`) verified
4. [x] NOT_FOUND self-correction hints and CLI examples populated across all surfaces
5. [x] Patch fuzzy matching and disambiguation snippets verified (`line_hints`, `count`)
6. [x] Markdown `<pre>` code block wrapping verified without mid-word clipping across 3 live screenshots
7. [x] `manage_cycles_and_modules` self-correction example fixed to `--action=list_cycles`
8. [x] `progressive-error-samples.yaml` programmatic verification confirmed across all 11 cases
9. [x] `thumbs-up-kanban.wiki` updated and committed (commit `535fe9e`) with 24 tools in `_Sidebar.md`
10. [x] Strict ASCII hyphenation verified (0 em/en-dashes across repo and wiki)
11. [x] Python test suite passes: 356 unit tests passing with >= 95% coverage on touched files

---

## Verdict & Certification
STATUS: APPROVED

All API ergonomics, CLI user experience, YAML formatting, Markdown code block wrapping, and documentation standards have been verified and certified. Ready for dual specialist signoff, coordinator merge into `main`, and clean-room Reality-Checker QA.
