# API Specialist Security & Architecture Audit Review: KAN-18

## Audit Metadata
- Ticket ID: KAN-18 ([KB-P3-AUDIT-12])
- Reviewer: api-spec-2 (Clean-Room Backend/API Specialist)
- Date: 2026-11-19
- Target Worktree: `/home/adamoutler/.gemini/antigravity-cli/worktrees/cec3609e-f993-4e05-b8c5-be0070e6116c/swarm-b-kan18-9a5e6950`
- Target Branch: feat/KAN-18
- Base Commit: cb25150
- Head Commit: 6b756e1
- STATUS: APPROVED

---

## Executive Summary
This clean-room audit evaluates the consolidation of the `/mcp/docs` Model Context Protocol surface from 6 redundant CRUD tools into 3 CLI-modeled tools (`search`, `create`, `update`). The implementation eliminates MCP schema context bloat, enforces unidirectional module boundaries (`mcp` forbidden from importing `database`), introduces surgical `original_text`/`replacement_text` diff-patching with similarity diagnostics, enables sticky-to-doc auto-promotion, and formats all outputs using compact YAML (`InlineSafeDumper`).

All changes adhere strictly to the authoritative specifications in `docs/ARCHITECTURE_AND_PRODUCT_SPEC.md` and `kanban/GEMINI.md`.

---

## Detailed Contract & Security Verification

### 1. Tool Consolidation & Authorization Scopes on `/mcp/docs`
- Files: `mcp/surfaces/docs/__init__.py`, `mcp/auth.py`, `mcp/protocol.py`, `mcp/errors.py`
- Invariant: Surface must expose exactly 3 canonical tools: `search`, `create`, and `update`. Token scopes must enforce least privilege (`docs:read` vs `docs:write`). Ephemeral tokens must remain read-only.
- Audit Findings:
  - `DOCS_TOOL_NAMES` in `mcp/surfaces/docs/__init__.py` replaced with `("search", "create", "update")`. Legacy wrapper tool registrations removed.
  - `mcp/auth.py`: Configured `SCOPE_REQUIREMENTS` mapping `search` to `docs:read`, and `create` / `update` to `docs:write`.
  - `mcp/protocol.py`: Ephemeral read-only allowlist for `/mcp/docs` restricted strictly to `{"search"}`. Ephemeral tool introspection dynamically maps `search` -> `search_knowledge` during database consumption to preserve PostgreSQL check constraints without schema modification.
  - Registered error codes `PATCH_TARGET_NOT_FOUND` and `PATCH_TARGET_AMBIGUOUS` in `mcp/errors.py`.

### 2. CLI-Modeled `search` & `create` Returning Compact YAML
- Files: `mcp/surfaces/docs/search.py`, `mcp/surfaces/docs/create.py`
- Contract Invariant: All responses formatted using `InlineSafeDumper` compact YAML with configurable Level of Detail (`lod="summary"|"standard"|"full"`).
- Audit Findings:
  - `search`:
    - `id="help"` outputs self-describing surface reference manual and parameters.
    - Resolves canonical keys, hierarchical paths, or UUIDs for docs, pages, and stickies, returning breadcrumbs, access pills, outlines, and body according to LOD.
    - Hybrid search queries `POST /api/v1/search/knowledge` with bounds checking (1-500 chars), kinds filtering, snippet truncation (max 300 chars), and opaque cursor pagination.
    - Project and workspace listing modes support hierarchical tree formatting and promotion status indicators.
  - `create`:
    - Creates Doc roots, child Pages (when `parent` is provided for Doc), or Stickies.
    - Rejects `parent` when `type="STICKY"`.
    - Validates sticky colors against allowed color tokens.
    - Rejects child page nesting depth > 10.
    - Resolves human-readable project keys to project UUIDs.
    - Attaches inline links using Universal Object Graph `/api/v1/objects/{id}/links`.

### 3. Unified `update` with Sticky Auto-Promotion & Inline Links Sync
- File: `mcp/surfaces/docs/update.py`
- Invariant: Passing `type="DOC"` on an existing sticky identifier must atomically promote it to a Doc, preserving access controls and applying updates.
- Audit Findings:
  - When `id` resolves to a sticky and `type="DOC"` is supplied, dispatches `POST /api/v1/stickies/{id}/promote-to-doc`.
  - Preserves ACLs row-for-row, applies optional `title`, `parent`, `content`, and inline `links`.
  - Rejects already promoted stickies with `ALREADY_PROMOTED`.
  - Supports inline `links` delta syntax (`["+ARCH-1", "-ARCH-2"]` or `{"add": [...], "remove": [...]}`) to atomically sync `RELATES_TO` and `VERIFIED_BY_DOC` edges.

### 4. Surgical `original_text` + `replacement_text` Diff-Patching
- File: `mcp/surfaces/docs/update.py`
- Invariant: When updating document content via substring replacement, target ambiguity or missing targets must produce actionable forensic diagnostic feedback.
- Audit Findings:
  - Concurrency control: verifies client `if_match` against fresh `body_sha256`, raising `CONFLICT_ETAG` on mismatch.
  - Occurrence counting:
    - If `count == 1`: replaces the exact target substring in document or page body.
    - If `count == 0`: raises `PATCH_TARGET_NOT_FOUND` containing top-2 closest matches using `difflib.SequenceMatcher` with `{line_start, line_end, similarity, snippet}`.
    - If `count > 1`: raises `PATCH_TARGET_AMBIGUOUS` with 1-based line number hints where target appears.

---

## Gate & Invariant Checklist

1. [x] Zero New Dependencies: No additions to `pyproject.toml` or `package.json`.
2. [x] Admin Route Security: All `/api/v1/admin/*` endpoints maintain mandatory `Depends(require_admin_aal2)`.
3. [x] Architectural Layering: `uv run lint-imports` verified 2 kept contracts, 0 broken (`mcp forbidden from importing database KEPT`).
4. [x] Test Coverage:
   - `mcp/surfaces/docs/__init__.py`: 100%
   - `mcp/surfaces/docs/create.py`: 98% line and branch coverage
   - `mcp/surfaces/docs/search.py`: 96% line and branch coverage
   - `mcp/surfaces/docs/update.py`: 97% line and branch coverage
   - All touched modules comfortably exceed >= 95.10% threshold.
   - All 38 unit and integration tests passing in 11.98s.
5. [x] Static Analysis: `ruff check mcp/`, `ruff format --check mcp/`, and `mypy mcp/` (111 source files) pass with 0 errors and 0 warnings.
6. [x] Zero Em/En-Dashes: Clean verification across code, tests, docs, and review markdown (0 em/en-dashes).
7. [x] Evidence Packet Complete: `git-diff.patch`, `changed-files-manifest.txt`, `unit-test-results.txt`, `build-or-typecheck.txt`, `contract-sample.yaml`, and `message-to-reality-checker.md` verified in `docs/qa/KAN-18/`.

---

## Verdict & Handoff
STATUS: APPROVED

The MCP tool contracts, security invariants, and test evidence are verified clean. Handoff to `@ui-spec-2` for non-UI classification sign-off (backend-only MCP surface; no UI screenshots expected).
