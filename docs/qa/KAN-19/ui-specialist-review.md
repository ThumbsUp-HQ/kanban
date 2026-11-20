# UI/UX Specialist Review: KAN-19

## Audit Metadata
- Ticket ID: KAN-19 ([KB-P3-AUDIT-13])
- Title: Implement Progressive-Disclosure Self-Correcting YAML Error UX Across All MCP Surfaces
- Reviewer: ui-spec-2 (Clean-Room UI/UX Specialist)
- Date: 2026-11-20
- Target Path: `/home/adamoutler/kanban`
- Target Branch: `main`
- Commit: `18bcddb7` (18bcddb79754cb5c8a66699eb0155b4be4cf40c3)
- Wiki Commit: `535fe9e` (535fe9e06b544b652f9a3ed3bd1c245a9053407f)
- STATUS: APPROVED

---

## Executive Summary
This clean-room review evaluates the agent ergonomics, developer experience (DX), command-line interface (CLI) mental models, code block text wrapping, responsive layouts, and progressive-disclosure YAML error UX for ticket KAN-19 ([KB-P3-AUDIT-13]) on `main` (commit `18bcddb7`).

All 5 unmocked live-stack screenshots in `docs/qa/KAN-19/screenshots/` across Desktop (1440x900), Mobile (390x844), and Full-Page (1440x2160) viewports in Light and Dark themes were inspected and verified via binary image analysis:
1. **Markdown Code Block Wrapping & Readability (`MarkdownEditor.css` & `DocsWorkspaceView.css`):**
   - Enforced `white-space: pre-wrap;`, `overflow-wrap: break-word;`, `word-break: break-word;`, and `overflow-x: auto;` on `.ProseMirror pre`, `.kb-code-block`, and `.docs-prose pre`.
   - Verified that long YAML error properties (e.g. `valid_options: [id, type, title, content, parent, color, original_text, replacement_text, if_match, links]`) wrap cleanly onto subsequent lines with zero character clipping mid-word, zero horizontal scroll blowout, and zero edge overflow on both desktop and 390px mobile viewports.
2. **Self-Correcting YAML Error Schema Across All Error Paths (`mcp/errors.py`):**
   - Extended `KbMcpError` with structured remediation fields serialized via `InlineSafeDumper` (`strip_nulls=True`):
     - `field`: The exact parameter or property causing validation failure.
     - `valid_options`: Permitted enum values or allowed targets.
     - `did_you_mean`: High-confidence fuzzy suggestions or semantic aliases.
     - `hint` / `fix_hint`: Actionable remediation guidance for autonomous agent single-turn self-correction.
     - `cli_example`: Immediately runnable CLI invocation pre-filled with valid parameters.
     - `closest_match`: Snippet and line range fuzzy matching for document patch failures (`line_start`, `line_end`, `similarity`, `snippet`).
     - `line_hints` & `count`: Disambiguation hints for multi-match patch conflicts.
   - Populated `fix_hint` and `cli_example` across all `NOT_FOUND` / `ENTITY_NOT_FOUND` / `SECTION_NOT_FOUND` paths (`read_ticket.py`, `update_ticket.py`, `link_objects.py`, `docs/*`, `admin/*`, `internal_client.py`).
3. **Pre-Dispatch Schema Validation & Semantic Aliasing (`mcp/protocol.py`):**
   - Intercepts unknown parameters, missing required arguments, and type/enum violations before tool execution.
   - Leverages semantic alias mappings (`body` -> `content`, `ticket_id` -> `identifier`, etc.) and `difflib.get_close_matches` (`querry` -> `query`) to guide agents directly to the valid parameter name.
   - JIT-help handling intercepts all standard JIT parameters (`identifier`, `action`, `source`, `id`, `project`, `summary`) before pre-dispatch validation runs.
   - The `custom_fields` parameter warning is properly guarded to `spec.name == "update_ticket"`.
4. **Authoritative Documentation in Wiki (`thumbs-up-kanban.wiki` commit `535fe9e`):**
   - Aligned `MCP-Tools-Reference.md` Example 7 (`ALREADY_PROMOTED`) placing `target_doc_key` below `cli_example` to match runtime YAML output order verbatim.
   - Updated `_Sidebar.md` tool count to 24 Tools matching the official MCP catalog.
   - Aligned `manage_cycles_and_modules` action enum with all 17 valid operations and updated CLI example to `--action="list_cycles"`.
   - Aligned Example 6 (`CONFLICT_ETAG`) and Example 9 (`PATCH_TARGET_AMBIGUOUS`) with verbatim runtime contracts and field ordering.

---

## Visual & Ergonomics Verification (All 5 Live Screenshots)

### 1. Wrapped Code Blocks on Desktop (`live-kan19-mcp-docs-desktop-light.png` & `live-kan19-mcp-docs-desktop-dark.png`)
- Views Inspected:
  - `live-kan19-mcp-docs-desktop-light.png` (1440x900)
  - `live-kan19-mcp-docs-desktop-dark.png` (1440x900)
- Rendering: Examples 1 and 2 display rendered YAML code blocks in light and dark modes. Long lines such as `valid_options: [...]` wrap gracefully across lines without clipping characters or spilling outside the editor container boundary. Crisp contrast and readable typography.

### 2. Mobile Responsive Code Blocks (`live-kan19-mcp-docs-mobile-light.png`)
- View Inspected:
  - `live-kan19-mcp-docs-mobile-light.png` (390x844)
- Rendering: Verified on 390px mobile viewport. Code blocks enforce `white-space: pre-wrap; word-break: break-word;` so text flows vertically within the card container, maintaining `scrollWidth === 390` with zero horizontal viewport blowing.

### 3. Bottom Examples and Domain Errors (`live-kan19-mcp-docs-examples-bottom-desktop-light.png`)
- View Inspected:
  - `live-kan19-mcp-docs-examples-bottom-desktop-light.png` (1440x2160)
- Rendering: Shows Examples 6 through 10 in full page context:
  - Example 6 (`CONFLICT_ETAG`): Includes current ETag and ready-to-run retry command.
  - Example 7 (`ALREADY_PROMOTED`): Correctly shows `target_doc_key: DOC-KAN-42` placed after `cli_example`.
  - Example 8 (`PATCH_TARGET_NOT_FOUND`): Displays fuzzy match candidate snippets with line numbers (`line_start`, `line_end`) and similarity score.
  - Example 9 (`PATCH_TARGET_AMBIGUOUS`): Displays line hints and count disambiguation.
  - Example 10 (`NOT_FOUND`): Shows structured self-correcting 404 payload with actionable fix guidance and alternative CLI commands.

### 4. Admin Cycle Management Documentation (`live-kan19-mcp-docs-cycles-desktop-light.png`)
- View Inspected:
  - `live-kan19-mcp-docs-cycles-desktop-light.png` (1440x900)
- Rendering: Shows `manage_cycles_and_modules` documentation with the corrected CLI example `--action="list_cycles" --project=KAN`, matching the 17-action schema.

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
- Zero em-dashes (`\u2014`) or en-dashes (`\u2013`) in code, tests, or wiki documentation. All punctuation uses standard ASCII hyphens (-).
- Verified clean via `python3 -m scripts.check_no_dashes --all` and on wiki.

### 4. Test Coverage & Verification
- 356/356 Pytest unit tests passing in 46.07s.
- All 8 touched files meet or exceed 95% coverage (overall 96%):
  - `mcp/errors.py`: 100%
  - `mcp/internal_client.py`: 96%
  - `mcp/protocol.py`: 95%
  - `mcp/surfaces/admin/manage_cycles_and_modules.py`: 97%
  - `mcp/surfaces/agent/read_ticket.py`: 96%
  - `mcp/surfaces/agent/transition_ticket.py`: 95%
  - `mcp/surfaces/agent/update_ticket.py`: 97%
  - `mcp/surfaces/docs/update.py`: 97%
- Vitest suite: 434 tests passing across 38 files.

---

## Final Verification Checklist

1. [x] Extended `KbMcpError` with progressive-disclosure fields verified
2. [x] Pre-dispatch schema validation and semantic alias correction verified
3. [x] Domain conflict handling (`INVALID_TRANSITION`, `CONFLICT_ETAG`, `ALREADY_PROMOTED`) verified
4. [x] NOT_FOUND self-correction hints and CLI examples populated across all surfaces
5. [x] Patch fuzzy matching and disambiguation snippets verified (`line_hints`, `count`)
6. [x] Markdown `<pre>` code block wrapping verified across all 5 live screenshots
7. [x] `manage_cycles_and_modules` self-correction example fixed to `--action=list_cycles`
8. [x] `progressive-error-samples.yaml` programmatic verification confirmed across all 11 cases
9. [x] `thumbs-up-kanban.wiki` updated and committed (commit `535fe9e`) with 24 tools in `_Sidebar.md`
10. [x] Strict ASCII hyphenation verified (0 em/en-dashes across repo and wiki)
11. [x] Python test suite passes: 356 unit tests passing with >= 95% coverage on touched files

---

## Verdict & Certification
STATUS: APPROVED

All API ergonomics, CLI user experience, YAML formatting, Markdown code block wrapping across all 5 live screenshots, and documentation standards have been verified and certified. Ready for Clean-Room Reality-Checker QA.
