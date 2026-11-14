# Reality Checker Forensic Audit Packet: KANBA-127 (KB-P4-08)

## Ticket Overview
- **Ticket ID**: KANBA-127
- **Ticket File**: `docs/tickets/KB-P4-08.md`
- **Title**: [Phase 4 / MCP] /mcp/docs surface: 6 knowledge & sticky tools
- **Epic**: KB-E4 (Phase 4 Model Context Protocol Server & Surface Registries)
- **Branch**: `feat/KANBA-127` in worktree `/tmp/kb-wt-KANBA-127`
- **Status**: In Progress (preserved per invariant; author never closes ticket directly)
- **Author**: builder-19

---

## Deliverables & Component Architecture

1. **`mcp/surfaces/docs/__init__.py`**:
   - Registers exactly the 6 knowledge and sticky tools: `search_knowledge`, `read_doc`, `upsert_doc`, `manage_stickies`, `promote_sticky_to_doc`, `link_knowledge`.
   - Replaces placeholder `ping_docs`.
   - Exports `build_docs_registry`, `create_docs_registry`, and `DOCS_TOOL_NAMES`.

2. **`mcp/surfaces/docs/search_knowledge.py`**:
   - Implements `search_knowledge` tool (`docs:read` scope).
   - Validates `query` (1..500 chars), `kinds` (`[doc, page, sticky]`), optional `project`, `limit` (1..50, default 20), and `cursor`.
   - Truncates context snippets to <= 300 characters centered around matched terms with ATX heading slug anchors.

3. **`mcp/surfaces/docs/read_doc.py`**:
   - Implements `read_doc` tool (`docs:read` scope).
   - Resolves by canonical page path, UUID, or `help` (JIT disclosure).
   - Projects 3 distinct LOD tiers:
     - `summary`: `kind`, `key`, `title`, `breadcrumbs`, `version_seq`.
     - `standard`: `summary` + `body_markdown`, `etag`, `access` pill (`public`, `project`, `workspace`, `restricted`).
     - `full`: `standard` + `access_manifest`, `outline` (headings tree), and `links` (typed object links).
   - Anti-enumeration: Missing docs and unreadable docs in restricted projects produce byte-identical 404 YAML outputs.

4. **`mcp/surfaces/docs/upsert_doc.py`**:
   - Implements `upsert_doc` tool (`docs:write` scope).
   - Supports 3 modes: `replace` (default), `append`, and `section_patch`.
   - Enforces ltree hierarchy depth <= 10 (`VALIDATION_FAILED` when depth exceeded).
   - Enforces optimistic concurrency via `if_match` SHA-256 hex ETag (`CONFLICT_ETAG` on mismatch).
   - Strips dangerous or hidden DOM constructs (such as `style="display:none"`).

5. **`mcp/markdown_sections.py`**:
   - Surgical ATX heading parser and section patch engine.
   - Ignores code blocks fenced with ``` and ~~~.
   - Exact case-sensitive matching against target heading. Raises `SECTION_NOT_FOUND` if absent, `AMBIGUOUS_IDENTIFIER` if duplicate identical headings exist.
   - Replaces content cleanly up to next heading of identical or higher level, or EOF.

6. **`mcp/surfaces/docs/manage_stickies.py`**:
   - Implements `manage_stickies` tool (`docs:write` / `docs:read` for list).
   - Supports actions: `list`, `create`, `edit`, `recolor`, `help`.
   - Enforces color allowlist: `amber`, `mint`, `sky`, `lavender`, `coral`, `slate` (`VALIDATION_FAILED` on invalid colors).
   - Body size capped at 65,536 bytes.
   - Server-computed heuristic: Evaluates `promotion_recommended` (body >= 500 chars or checklist count >= 3).

7. **`mcp/surfaces/docs/promote_sticky_to_doc.py`**:
   - Implements `promote_sticky_to_doc` tool (`docs:write` scope).
   - Atomically promotes sticky note into permanent doc in a single transaction via `POST /api/v1/stickies/{id}/promote-to-doc`.
   - Verbatim row-by-row ACL preservation: All `object_access_control` rows are copied with 100% identity to the new doc.
   - Registers typed object link `PROMOTED_TO_DOC`.
   - Already-promoted sticky rejects with `ALREADY_PROMOTED`.

8. **`mcp/surfaces/docs/link_knowledge.py`**:
   - Implements `link_knowledge` tool (`docs:write` scope).
   - Connects docs, pages, and stickies to issues, cycles, modules, or projects with typed links (`RELATES_TO`, `VERIFIED_BY_DOC`, `DERIVED_FROM_STICKY`).
   - Rejects matrix violations with `LINK_TYPE_NOT_ALLOWED`.

9. **`mcp/app.py`, `mcp/auth.py`, `mcp/errors.py`, `mcp/internal_client.py`, `mcp/context.py`**:
   - Mounted `create_mcp_app` wires `build_docs_registry` on `/mcp/docs`.
   - `mcp/auth.py` binds all 6 tool names to required `docs:read` / `docs:write` scopes.
   - `mcp/errors.py` declares typed `SECTION_NOT_FOUND`, `ALREADY_PROMOTED`, `LINK_TYPE_NOT_ALLOWED`.
   - `mcp/internal_client.py` acquires CSRF token cookie and header automatically for mutating operations and resolves error status mappings.
   - `mcp/context.py` provides thread-local and async-safe MCP request context propagation.

---

## Verification & Quality Metrics

### 1. Automated Unit Test Coverage (>=95% Standard)
- **Files**: `mcp/tests/docs/test_docs_tools.py`, `mcp/tests/docs/test_docs_surfaces_unit.py`, `mcp/tests/test_markdown_sections.py`
- **Results**: 22 passed in 5.35s
- **Coverage**: **96%** combined coverage across `mcp.surfaces.docs` and `mcp.markdown_sections` (761 statements, 14 missed, 272 branches, 25 partial)
  - `mcp/surfaces/docs/__init__.py`: 100%
  - `mcp/surfaces/docs/search_knowledge.py`: 100%
  - `mcp/markdown_sections.py`: 99%
  - `mcp/surfaces/docs/manage_stickies.py`: 99%
  - `mcp/surfaces/docs/upsert_doc.py`: 97%
  - `mcp/surfaces/docs/promote_sticky_to_doc.py`: 95%
  - `mcp/surfaces/docs/link_knowledge.py`: 93%
  - `mcp/surfaces/docs/read_doc.py`: 93%
- **Log**: `docs/qa/KANBA-127/unit-test-results.txt`

### 2. Forensic Proof Bundle Check
1. `docs/qa/KANBA-127/git-diff.patch`: Complete patch against merge base.
2. `docs/qa/KANBA-127/unit-test-results.txt`: 22 passed, 96% coverage.
3. `docs/qa/KANBA-127/build-check.txt`: Combined clean output from ruff check, ruff format check, mypy --strict, and lint-imports.
4. `docs/qa/KANBA-127/mcp-transcript.txt`: Full HTTP transcript capturing all 6 tools, `SECTION_NOT_FOUND`, and `ALREADY_PROMOTED`.
5. `docs/qa/KANBA-127/tools-list.json`: Raw `/mcp/docs` tools/list JSON containing exactly the 6 registered tools.
6. `docs/qa/KANBA-127/acl-preservation-proof.txt`: Raw SQL verification confirming identical row-by-row ACL rows between source sticky and promoted doc.
7. `docs/qa/KANBA-127/schema-budget.txt`: Token budget audit confirming 1,177 tokens <= 1,350 ceiling (173 tokens headroom).
8. `docs/qa/KANBA-127/api-specialist-review.md`: Signed and APPROVED by Systems Architect (`arch-reviewer`, message #842).
9. `docs/qa/KANBA-127/ui-specialist-review.md`: Signed and APPROVED by UI Specialist (`ui-specialist`, message #843).
10. Screenshots: N/A - Non-UI Ticket (per Ticket Spec line 73).

### 3. Static Analysis & Build Verification
- `ruff check .`: 0 errors (Exit Code: 0)
- `ruff format --check .`: Clean across 1,114 files (Exit Code: 0)
- `mypy --strict mcp`: Clean across 49 source files (Exit Code: 0)
- `lint-imports`: 2 kept, 0 broken (Exit Code: 0)
- Non-ASCII dash audit: ZERO U+2014 or U+2013 characters in any KANBA-127 files.
