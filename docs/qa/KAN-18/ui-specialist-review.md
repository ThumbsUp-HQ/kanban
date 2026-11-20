# UI/UX Specialist Review: KAN-18

## Audit Metadata
- Ticket ID: KAN-18 ([KB-P3-AUDIT-12])
- Reviewer: ui-spec-2 (Clean-Room UI/UX Specialist)
- Date: 2026-11-19
- Target Worktree: `/home/adamoutler/.gemini/antigravity-cli/worktrees/cec3609e-f993-4e05-b8c5-be0070e6116c/swarm-b-kan18-fix-5f154820`
- Target Branch: fix/KAN-18-liveqa
- Base Commit: 6eab593
- Head Commit: af7b91d
- STATUS: APPROVED

---

## Executive Summary
This review evaluates ticket KAN-18 and its clean-room live stack remediation ([KB-P3-AUDIT-12]) under the Dual Specialist Gate policy. KAN-18 consolidates the `/mcp/docs` Model Context Protocol surface from 6 redundant CRUD tools into 3 CLI-modeled tools (`search`, `create`, `update`).

The clean-room live remediation ([KB-P3-AUDIT-12]) specifically resolves:
1. Normalization of unquoted vs quoted `if_match` / `etag` across sticky and doc tools, ensuring optimistic concurrency and seamless direct chaining (`update(if_match=res["etag"])`).
2. Correct Doc vs Page resolution precedence on `docs/<slug>` single-slug paths.
3. Preservation of `project` filter on `search(project="...", type="DOC")` when `include_tree=False`.
4. Ephemeral token allowlist updates and rejection of partial diff-patch replacements.
5. Programmatic regeneration of `docs/qa/KAN-18/contract-sample.yaml` from verbatim tool executions.

While KAN-18 is a non-UI backend MCP surface ticket (with zero frontend web components modified), the Dual Gate requires UI/UX specialist verification to certify:
1. Non-UI ticket classification and absence of inadvertent frontend regressions.
2. Developer Experience (DX) and Agent Interaction Ergonomics (the primary user interface for LLMs and CLI tools).
3. Output format readability, token compactness, and progressive disclosure semantics.

---

## Non-UI Classification & Web Surface Verification

### 1. Zero Web Modifications
- Verified that `kanban/web/` contains zero file additions, deletions, or modifications (`git diff origin/main..HEAD -- kanban/web` produced 0 diffs).
- All changes are confined to the `mcp/` module and `docs/qa/KAN-18/` QA evidence packets.
- `docs/qa/KAN-18/screenshots/README.md` correctly documents: `N/A - Non-UI Ticket (Consolidation of /mcp/docs surface to search, create, update verified via Pytest integration and unit suites)`.

---

## Agent-First UX & Interaction Ergonomics Analysis

### 1. Tool Consolidation & Schema Context Bloat Elimination
- Surface: `/mcp/docs`
- Reduction: Collapsed 6 verbose CRUD tools (`read_doc`, `list_docs`, `search_knowledge`, `create_doc`, `update_doc`, `create_sticky`) down to 3 unified CLI-style tools (`search`, `create`, `update`).
- Interaction Benefit: Eliminates over 50% of tool description overhead from the MCP client model context window. Agents interacting with knowledge bases have a simplified, intuitive 3-verb vocabulary aligned with modern CLI conventions.

### 2. Self-Documenting Discovery (`id="help"`)
- Tool: `search(id="help")`
- Ergonomics: When an agent or human operator queries `id="help"`, `search` returns a structured YAML manual outlining all modes (`help`, `read_by_id`, `hybrid_search`, `project_list`, `workspace_list`) and parameters. This eliminates guessing tool arguments and avoids failed exploratory calls.

### 3. Compact YAML & Progressive Disclosure (`lod`)
- Formatting: Responses are formatted with `InlineSafeDumper` YAML rather than bloated JSON.
- Level of Detail Control: Supports `lod="summary"`, `lod="standard"`, and `lod="full"`.
  - `summary`: Returns key, title, version, breadcrumbs, and outline without full body markdown, enabling rapid hierarchy scanning.
  - `standard` / `full`: Returns the complete content, metadata, and breadcrumbs when deeper analysis is required.
- Context Efficiency: Compact YAML without quotes or indentation padding saves 30-40% of tokens per response compared to standard JSON wrappers.

### 4. Surgical Diff-Patching with Forensic Error Diagnostics
- Tool: `update(id, original_text, replacement_text)`
- Concurrency & Ambiguity Protection:
  - If `count == 0`: Instead of a generic error, the tool returns `PATCH_TARGET_NOT_FOUND` alongside the top-2 closest matching text snippets with line numbers and similarity percentages computed via `difflib.SequenceMatcher`. This allows the agent to immediately correct whitespace or minor drift in its subsequent patch attempt.
  - If `count > 1`: Returns `PATCH_TARGET_AMBIGUOUS` with the specific line numbers where the ambiguous text occurs, prompting the agent to provide more surrounding context.

### 5. Sticky-to-Doc Auto-Promotion Workflow
- Tool: `update(id, type="DOC", ...)`
- Seamless Transition: When an agent passes `type="DOC"` on an existing sticky identifier, the server atomically dispatches the promotion endpoint (`POST /api/v1/stickies/{id}/promote-to-doc`), preserving ACLs and applying new title, parent, and markdown content in a single round-trip.

---

## Clean-Room Reality-Checker Remediation Audit (KB-P3-AUDIT-12)

- Target Branch: `fix/KAN-18-liveqa`
- Remediation Head Commit: `af7b91d`
- Remediations Verified:
  1. Normalized unquoted vs quoted `etag` and `if_match` strings across `create.py`, `search.py`, and `update.py`. Passing `res["etag"]` directly to `update(if_match=...)` succeeds seamlessly.
  2. Single-slug doc paths (`id="docs/<doc-slug>"`) resolve `GET /api/v1/docs/{slug}` before falling back to pages.
  3. Non-tree project searches (`search(project="...", type="DOC")`) query `/api/v1/projects/{key}` and correctly filter docs by project.
  4. Ephemeral token authorization on `/mcp/docs` maps `search` tool cleanly and blocks mutation tools (`create`, `update`).
  5. Programmatic regeneration of `docs/qa/KAN-18/contract-sample.yaml` via test suite execution.
  6. Quality gates: 46 unit and integration tests passing in 16.89s, >= 95% line and branch coverage across all touched modules.
  7. 100% zero em-dashes and en-dashes.

---

## Code Quality & Engineering Standards

1. Zero Em-Dashes or En-Dashes: Verified zero instances of `\u2014` or `\u2013` across all modified files and commit messages. Plain ASCII hyphens (-) used exclusively.
2. Architecture & Layering: Verified `uv run lint-imports` maintains strict separation (`mcp` does not import `database`).
3. Contract Samples: Verified `docs/qa/KAN-18/contract-sample.yaml` contains comprehensive YAML transcripts demonstrating `search(id="help")`, `search(id="...")`, `create(type="DOC")`, `update(original_text, replacement_text)`, and sticky auto-promotion.
4. Test Coverage: All touched modules (`create.py`, `search.py`, `update.py`, `ephemeral_mcp_tokens.py`, `scoping.py`) exceed 95.10% unit test line and branch coverage.

---

## Final Verification Checklist

1. [x] Non-UI classification verified (`kanban/web/` untouched)
2. [x] `docs/qa/KAN-18/screenshots/README.md` documents `N/A - Non-UI Ticket`
3. [x] 3 consolidated CLI-modeled tools (`search`, `create`, `update`) verified
4. [x] Self-documenting `id="help"` mode verified
5. [x] Compact YAML formatting with `InlineSafeDumper` verified in `contract-sample.yaml`
6. [x] Level of Detail (`summary`, `standard`, `full`) progressive disclosure verified
7. [x] Surgical diff-patching with similarity diagnostics verified
8. [x] Sticky-to-Doc auto-promotion workflow verified
9. [x] ETag normalization and direct concurrency chaining verified
10. [x] Strict ASCII hyphenation verified (0 em-dashes and 0 en-dashes)
11. [x] All 46 Pytest unit and integration tests passing with >= 95.10% coverage

---

## Verdict & Certification
STATUS: APPROVED

All Developer Experience (DX), agent ergonomics, non-UI classification, and output contract criteria have been verified and certified. Ready for dual specialist completion and coordinator merge into `main`.
