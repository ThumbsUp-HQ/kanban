# Reality-Checker Forensic QA Report: KAN-18

## Executive Summary
- Ticket ID: KAN-18 ([KB-P3-AUDIT-12])
- Title: Consolidate /mcp/docs from 6 tools to 3 CLI-modeled tools (search, create, update) with surgical diff-patching, inline links, and type="DOC" auto-promotion
- Target Worktree: `/home/adamoutler/.gemini/antigravity-cli/worktrees/cec3609e-f993-4e05-b8c5-be0070e6116c/swarm-b-kan18-9a5e6950`
- Target Branch: `feat/KAN-18`
- Reviewer: rc-gate-2 (Clean-Room Forensic QA Gate)
- Review Date: 2026-11-19
- Overall Quality Rating: A
- Production Readiness: READY

---

## Forensic Audit Verification Matrix

### Problem 1: Tool Consolidation & Authorization Scopes on `/mcp/docs`
- Defect: The `/mcp/docs` surface previously exposed 6 redundant CRUD tools (`read_doc`, `list_docs`, `search_knowledge`, `create_doc`, `update_doc`, `create_sticky`), creating MCP schema context bloat and confusing agent callers.
- Verification:
  - Inspected `mcp/surfaces/docs/__init__.py`: Replaced `DOCS_TOOL_NAMES` with exactly 3 canonical tools: `("search", "create", "update")`. Legacy wrapper registrations removed.
  - Inspected `mcp/auth.py`: Updated `SCOPE_REQUIREMENTS` to enforce `docs:read` for `search`, and `docs:write` for `create` and `update`.
  - Inspected `mcp/protocol.py`: Ephemeral read-only allowlist for `/mcp/docs` restricted strictly to `{"search"}`. Ephemeral tool introspection dynamically maps `search` -> `search_knowledge` during database consumption to preserve PostgreSQL check constraints without schema alterations.
  - Inspected `mcp/errors.py`: Registered error codes `PATCH_TARGET_NOT_FOUND` and `PATCH_TARGET_AMBIGUOUS`.
  - Status: VERIFIED RESOLVED

### Problem 2: CLI-Modeled `search` & `create` Returning Compact YAML (`InlineSafeDumper`)
- Defect: Tools emitted uncompressed JSON with high token overhead, lacked discovery modes, and did not support progressive disclosure via Level of Detail (LOD) controls.
- Verification:
  - Inspected `mcp/surfaces/docs/search.py`:
    - `id="help"` outputs structured surface reference manual detailing all available modes and parameters.
    - Read by identifier (key, path, UUID) resolves docs, pages, and stickies with breadcrumbs, access pills, outlines, and body according to requested LOD (`summary`, `standard`, `full`).
    - Hybrid search delegates to `POST /api/v1/search/knowledge` with length validation (1-500 chars), kinds filtering, snippet truncation (max 300 chars), and opaque cursor pagination.
    - Project and workspace listing modes support document tree hierarchies and sticky promotion indicators.
  - Inspected `mcp/surfaces/docs/create.py`:
    - Supports creating Doc roots, child Pages, or Stickies.
    - Enforces hierarchy rules: rejects `parent` for `type="STICKY"`.
    - Validates sticky colors against allowed color tokens.
    - Rejects child page nesting depth > 10.
    - Resolves human-readable project keys to project UUIDs before dispatching upstream requests.
    - Attaches inline links using Universal Object Graph `/api/v1/objects/{id}/links`.
  - Status: VERIFIED RESOLVED

### Problem 3: Unified `update` with Sticky Auto-Promotion (`type="DOC"`) & Inline Links Sync
- Defect: Promoting a sticky note to a canonical Doc required an out-of-band workflow, and linking objects required secondary tool calls.
- Verification:
  - Inspected `mcp/surfaces/docs/update.py`:
    - Sticky auto-promotion: When `id` resolves to an existing sticky and `type="DOC"` is supplied, dispatches `POST /api/v1/stickies/{id}/promote-to-doc`.
    - Preserves ACLs row-for-row, applies optional `title`, `parent`, `content`, and inline `links`.
    - Rejects already promoted stickies with `ALREADY_PROMOTED`.
    - Supports inline `links` delta syntax (`["+ARCH-1", "-ARCH-2"]` or `{"add": [...], "remove": [...]}`) to atomically sync `RELATES_TO` and `VERIFIED_BY_DOC` edges.
  - Status: VERIFIED RESOLVED

### Problem 4: Surgical `original_text` + `replacement_text` Diff-Patching
- Defect: Content updates previously overwrote entire documents, causing lost edits and race conditions.
- Verification:
  - Inspected `mcp/surfaces/docs/update.py`:
    - Concurrency control: verifies client `if_match` against fresh `body_sha256`, raising `CONFLICT_ETAG` on mismatch.
    - Occurrence counting:
      - If `count == 1`: replaces the exact target substring in document or page body.
      - If `count == 0`: raises `PATCH_TARGET_NOT_FOUND` containing top-2 closest matches using `difflib.SequenceMatcher` with `{line_start, line_end, similarity, snippet}`.
      - If `count > 1`: raises `PATCH_TARGET_AMBIGUOUS` with 1-based line number hints where target appears.
  - Status: VERIFIED RESOLVED

---

## Automated Test & Static Analysis Evidence

1. Unit & Integration Tests:
   - Python Pytest: 38 passed in 11.16s (`mcp/tests/docs/test_docs_surfaces_unit.py`, `mcp/tests/docs/test_docs_tools.py`, `mcp/tests/test_ephemeral_auth.py`, `mcp/tests/test_schema_budget.py`).
   - Coverage on touched modules:
     - `mcp/surfaces/docs/__init__.py`: 100%
     - `mcp/surfaces/docs/create.py`: 98% line and branch coverage
     - `mcp/surfaces/docs/search.py`: 96% line and branch coverage
     - `mcp/surfaces/docs/update.py`: 97% line and branch coverage
     - All touched modules comfortably exceed the >= 95.10% threshold.
   - Raw output logged in `docs/qa/KAN-18/unit-test-results.txt`.

2. Static Analysis & Type Checking:
   - Ruff check: clean (All checks passed).
   - Ruff format check: 113 files verified clean.
   - Mypy check: Success, no issues found in 111 source files.
   - Import Linter: 2 contracts kept, 0 broken (`mcp forbidden from importing database KEPT`).
   - Strict ASCII character check: Zero `\u2014` em-dashes and zero `\u2013` en-dashes across all modified files.
   - Raw output logged in `docs/qa/KAN-18/build-or-typecheck.txt`.

---

## Dual Specialist Gate Audits

1. API Specialist Audit:
   - File: `docs/qa/KAN-18/api-specialist-review.md`
   - Reviewer: `api-spec-2`
   - Status: APPROVED
   - Findings: Verified 3-tool consolidation, token scopes, compact YAML responses, diff-patching diagnostics, and architectural layer isolation.

2. UI/UX Specialist Audit:
   - File: `docs/qa/KAN-18/ui-specialist-review.md`
   - Reviewer: `ui-spec-2`
   - Status: APPROVED
   - Findings: Verified non-UI classification (`kanban/web/` untouched), agent-first DX ergonomics, self-documenting `id="help"` discovery, and progressive disclosure tokens.

---

## Visual Proof & Artifacts

- Artifacts verified in `docs/qa/KAN-18/`:
  - `git-diff.patch`
  - `changed-files-manifest.txt`
  - `unit-test-results.txt`
  - `build-or-typecheck.txt`
  - `message-to-reality-checker.md`
  - `contract-sample.yaml` (Exhaustive YAML transcripts for search, create, update, diff-patch, and sticky auto-promotion)
  - `screenshots/README.md` (Confirmed non-UI ticket)

---

## Final Gate Certification
- Overall Quality Rating: A
- Production Readiness: READY
- Recommendation: Proceed to merge into `main` branch.
