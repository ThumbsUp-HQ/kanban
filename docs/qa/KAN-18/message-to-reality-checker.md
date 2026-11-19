# Reality Checker Evidence Packet: KAN-18 (KB-P3-AUDIT-12)

## Executive Summary
This packet provides forensic verification for KAN-18: Consolidate /mcp/docs from 6 tools to 3 CLI-modeled tools (search, create, update) with surgical diff-patching, inline links, and type="DOC" auto-promotion.
This is a non-UI MCP ticket (`N/A - Non-UI Ticket`).
All four scoped problems are fully implemented, verified via Pytest integration and unit suites, achieving >= 95.10% line and branch coverage across all touched files, zero mypy errors, zero ruff errors, zero architectural import violations (`lint-imports`), and zero em/en-dashes.

## Scoped Problems and Implementations

### Problem 1: Consolidate /mcp/docs to 3 Tools
- **Files Modified**: `mcp/surfaces/docs/__init__.py`, `mcp/auth.py`, `mcp/protocol.py`, `mcp/errors.py`
- **Implementation**:
  - `DOCS_TOOL_NAMES` in `mcp/surfaces/docs/__init__.py` replaced with `("search", "create", "update")`. Legacy wrapper registrations removed.
  - `mcp/auth.py`: Added scope requirements mapping `search` to `docs:read`, `create` to `docs:write`, and `update` to `docs:write`.
  - `mcp/protocol.py`: Ephemeral read-only allowlist for `/mcp/docs` restricted strictly to `{"search"}`. Ephemeral tool introspection dynamically maps `search` to `search_knowledge` during database consumption to preserve PostgreSQL check constraints without schema modification.
  - `mcp/errors.py`: Registered error codes `PATCH_TARGET_NOT_FOUND` and `PATCH_TARGET_AMBIGUOUS`.

### Problem 2: Implement search & create Returning Compact YAML (InlineSafeDumper)
- **Files Added**: `mcp/surfaces/docs/search.py`, `mcp/surfaces/docs/create.py`
- **Implementation**:
  - `search(id?, query?, type="ALL"|"DOC"|"STICKY", project?, lod="summary"|"standard"|"full", include_tree=false, limit=20, cursor?)`:
    - `id="help"` mode outputs surface reference manual and available modes.
    - Read by identifier (canonical key, path, or UUID) resolves documents, child pages, and sticky notes, returning formatted nodes with breadcrumbs, access pills, outlines, and links according to requested LOD.
    - Hybrid search delegates to `POST /api/v1/search/knowledge` with query validation (1-500 chars), kinds filtering, snippet truncation (max 300 chars), and opaque cursor pagination.
    - Project and workspace listing modes support document tree hierarchies and sticky promotion indicators.
  - `create(type="DOC"|"STICKY", title, project?, content="", parent?, color="amber", links=[...])`:
    - Supports creating Doc roots, child Pages (when `parent` is provided for Doc), or Stickies.
    - Enforces hierarchy constraints: rejects `parent` for `type="STICKY"`.
    - Validates sticky colors against allowed color tokens.
    - Rejects child page nesting depth > 10.
    - Resolves human-readable project keys to project UUIDs before dispatching upstream HTTP requests.
    - Attaches inline links using Universal Object Graph `/api/v1/objects/{id}/links`.

### Problem 3: Unified update with Sticky Auto-Promotion (type="DOC") & Inline links Sync
- **Files Added**: `mcp/surfaces/docs/update.py`
- **Implementation**:
  - Sticky auto-promotion: When `id` resolves to an existing sticky and `type="DOC"` is passed, dispatches `POST /api/v1/stickies/{id}/promote-to-doc`.
  - Preserves ACLs row-for-row, applies optional `title`, `parent`, `content`, and inline `links`.
  - Rejects promotion if sticky was already promoted (`ALREADY_PROMOTED`).
  - Supports inline `links` delta syntax (`["+ARCH-1", "-ARCH-2"]` or `{"add": [...], "remove": [...]}`) to atomically sync `RELATES_TO` and `VERIFIED_BY_DOC` edges.

### Problem 4: Surgical original_text + replacement_text Diff-Patching
- **Files Added**: `mcp/surfaces/docs/update.py`
- **Implementation**:
  - ETag concurrency check: verifies client `if_match` against fresh `body_sha256` / `etag`, raising `CONFLICT_ETAG` with diagnostic hints on mismatch.
  - Single occurrence verification:
    - If `count == 1`: replaces the exact target substring in document or page body.
    - If `count == 0`: raises `PATCH_TARGET_NOT_FOUND` containing top-2 closest matches using `difflib.SequenceMatcher` with `{line_start, line_end, similarity, snippet}`.
    - If `count > 1`: raises `PATCH_TARGET_AMBIGUOUS` with list of 1-based line number hints where target appears.

## Test and Quality Validation

### Coverage Metrics on Touched Files
- `mcp/surfaces/docs/__init__.py`: 100%
- `mcp/surfaces/docs/create.py`: 98% (target >= 95.10%)
- `mcp/surfaces/docs/search.py`: 96% (target >= 95.10%)
- `mcp/surfaces/docs/update.py`: 97% (target >= 95.10%)
- Combined test run: 38 passed in 11.16s (`mcp/tests/docs/test_docs_surfaces_unit.py`, `mcp/tests/docs/test_docs_tools.py`, `mcp/tests/test_ephemeral_auth.py`, `mcp/tests/test_schema_budget.py`).

### Verification Checks
- `uv run ruff check mcp/`: PASSED (0 errors)
- `uv run ruff format --check mcp/`: PASSED (113 files already formatted)
- `uv run mypy mcp/`: PASSED (Success: no issues found in 111 source files)
- `uv run lint-imports`: PASSED (Contracts: 2 kept, 0 broken; mcp forbidden from importing database kept)
- `python3 -m scripts.check_no_dashes --all`: PASSED (0 em/en-dashes found)

## Artifact Manifest
- `docs/qa/KAN-18/contract-sample.yaml`: Raw compact YAML transcripts for search, create, update (patch, auto-promotion, and inline links).
- `docs/qa/KAN-18/screenshots/README.md`: Non-UI ticket verification notice.
- `docs/qa/KAN-18/changed-files-manifest.txt`: List of all touched and added repository files.
- `docs/qa/KAN-18/git-diff.patch`: Unified git diff patch of all implementation changes.
- `docs/qa/KAN-18/unit-test-results.txt`: Raw test execution log showing 38 passed tests and coverage table.
- `docs/qa/KAN-18/build-or-typecheck.txt`: Combined output of ruff, mypy, lint-imports, and check_no_dashes.
