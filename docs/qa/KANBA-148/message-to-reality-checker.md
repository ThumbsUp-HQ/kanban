# Forensic QA Handoff: KANBA-148 (KB-P5-26)

## Ticket Overview
- **Ticket ID:** `KANBA-148` (`KB-P5-26`)
- **Title:** `[Phase 5 / Agent + API + CLI] Sticky -> Doc AI structuring preview, ACL-preserving confirm contract & kanban-agent validate-sticky-promo`
- **Spec Sections:** S8.2 (Sticky -> Doc AI structuring preview + confirm contract), S15.3 (Ex 3: kanban-agent validate-sticky-promo)
- **Gates:** `reality-checker`, API Specialist (`arch-reviewer`), UI Specialist (`ui-specialist`)
- **Target Branch:** `feat/KANBA-148`

---

## Implemented Components

### 1. Proposal Schema & Canonical Markdown Assembly
- `agent/sticky_promo/schemas.py`:
  - `StickyDocProposal`: Strict schema adhering to `kb-sticky-doc-proposal/v1` with `proposed_title` (1..140 chars, single-line), `summary_markdown` (1..4096 chars), `sections` (1..20 `DocSection` objects with heading, level 2..3, body_markdown), and optional single-line `extracted_action_items` (1..280 chars each).
  - `render_canonical_doc_markdown()`: Canonical Markdown serialization of proposal assembling `# Title`, summary blockquote, `##`/`###` sections, and `## Open Action Items` checklist, normalized via KB-P2-13 canonical normalizer (0 scripts, 0 dangerous URI schemes).
- `agent/schemas/kb-sticky-doc-proposal-v1.json`: Machine-readable JSON schema with `additionalProperties: false`.

### 2. AI Structuring Pipeline & Lossless Diagram Guard
- `agent/sticky_promo/structurer.py`:
  - `structure_sticky_to_doc_proposal()`: 4-step pipeline with size guard (131,072 bytes cap), secret scrubbing first, spotlight boundary isolation (`<<<UNTRUSTED_STICKY_DATA_<nonce>>>>`), routing + budget reservation (`BudgetEnforcer`), and air-gap egress checks.
  - `verify_fenced_blocks_preserved()`, `extract_fenced_blocks()`, `append_missing_fenced_blocks()`: Verifies all fenced code blocks and Mermaid diagrams in rough sticky notes are preserved verbatim. If dropped or modified, appends deterministic fallback blocks and flags with `FENCED_BLOCK_MODIFIED` (or raises `FencedBlockModifiedError` under strict mode).

### 3. Test Fixtures & Deterministic Cassettes
- `examples/stickies/rough-auth-notes.md`: Canonical sample scratchpad sticky with Mermaid sequence diagram and action items.
- `tests/fixtures/ai/`:
  - `sticky_promo_auth_notes_ok.yaml`: Positive structuring response with title, summary, 3 sections (preserving Mermaid diagram verbatim), and 2 action items.
  - `sticky_promo_dropped_mermaid.yaml`: Incomplete LLM response omitting the Mermaid diagram.
  - `sticky_promo_hostile_html_output.yaml`: Hostile model response containing `<script>` and `javascript:` URIs.
  - `sticky_promo_schema_invalid.yaml`: Invalid response violating schema constraints (empty sections list).

### 4. REST Endpoints & Service Contracts
- `kanban/api/v1/schemas/stickies.py`:
  - `StickyPromoteRequest`: Extended with optional `structured_body_markdown` and `expected_sticky_sha256`.
  - `StickyPromotePreviewResponse`: Response model with `proposal`, `rendered_markdown`, `original_sha256`, `warnings`, and `acl_preview`.
- `kanban/api/v1/sticky_promo_ai.py`:
  - `POST /api/v1/stickies/{sticky_id}/promote-preview`: Zero-write preview endpoint mounted in `build_v1_router()`, protected by 25.0ms timing floor and `load_or_404` semantics, requiring `VIEW` and `EDIT` capabilities, rejecting already promoted (409) or oversized (413) stickies. Uses dynamic module resolution to keep module layering clean (`lint-imports`).
- `kanban/services/stickies.py`:
  - Atomic TOCTOU concurrency check comparing `expected_sticky_sha256` against `sticky.body_sha256` stored in PostgreSQL, raising 409 `STICKY_MODIFIED_SINCE_PREVIEW` on conflict.
  - Propagates structured markdown to created Doc and Pages.
  - Preserves all direct ACL entries verbatim on the new Doc and Page objects.

### 5. CLI Verification Command
- `agent/cli_commands/validate_sticky_promo.py` & `agent/cli.py`:
  - Registered `validate-sticky-promo` subcommand with all 4 S15.3 report sections (`RENDERED CONTEXT`, `TOOL TRACE`, `LATENCY & TOKENS`, `SCHEMA & POLICY STATUS`).
  - Supports `--provider`, `--model`, `--cassette`, `--air-gap`, `--strict-blocks`, `--acl-fixture`, and `--report text|json`.
  - Deterministic exit codes: 0 (OK), 1 (Runtime Error), 2 (Schema or Policy Violation).

### 6. Documentation Manifests
- `agent/GEMINI.md`: Added Sticky to Doc AI Structuring section.
- `kanban/GEMINI.md`: Added Sticky to Doc promotion preview and confirm contract entry.

---

## Mandatory Feature Test Verification

All 5 required integration test cases and comprehensive unit test suites are passing with 100% success rate:

| Test Case | Description | File | Result |
| :--- | :--- | :--- | :--- |
| Case 1 | Positive preview: zero writes, returns proposal, rendered markdown, original_sha256, acl_preview | `kanban/tests/stickies/test_sticky_promo_ai_api.py` | PASSED |
| Case 2 | Confirm with structured markdown: Doc and Page created, direct ACL entries preserved verbatim, PROMOTED link | `kanban/tests/stickies/test_sticky_promo_ai_api.py` | PASSED |
| Case 3 | Security & TOCTOU: stale sha256 -> 409 STICKY_MODIFIED_SINCE_PREVIEW, VIEWER without EDIT -> 403, unreadable -> 404 | `kanban/tests/stickies/test_sticky_promo_ai_api.py` | PASSED |
| Case 4 | Security & sanitization: outbound secret scrubbed, hostile HTML in completion sanitized | `kanban/tests/stickies/test_sticky_promo_ai_api.py` | PASSED |
| Case 5 | Fault & boundary: dropped Mermaid warning, oversized sticky -> 413, already promoted -> 409 | `kanban/tests/stickies/test_sticky_promo_ai_api.py` | PASSED |
| Case 6 | App state structurer override & default router fallback | `kanban/tests/stickies/test_sticky_promo_ai_api.py` | PASSED |
| CLI Suite | 13 test cases covering all flags, exit codes, and reports | `agent/tests/cli/test_validate_sticky_promo.py` | PASSED |
| Structurer Suite | 15 test cases covering schemas, scrubbing, air-gap, budget, fenced blocks | `agent/tests/sticky_promo/test_structurer.py` | PASSED |

### Coverage Gate
- Required: `>= 95%` line + branch
- Achieved:
  - `agent/cli_commands/validate_sticky_promo.py`: 99%
  - `agent/sticky_promo/__init__.py`: 100%
  - `agent/sticky_promo/schemas.py`: 100%
  - `agent/sticky_promo/structurer.py`: 100%
  - `kanban/api/v1/sticky_promo_ai.py`: 100%
  - Combined Target Coverage: **99.77%** (352 statements, 0 missed, 84 branches, 1 partial)

---

## Forensic Audit Artifacts in `docs/qa/KANBA-148/`
1. `git-diff.patch`: Unified diff of all changes against base commit.
2. `unit-test-results.txt`: Raw output and exit code 0 of DoD pytest command.
3. `build-check.txt`: Raw output of ruff check, ruff format --check, mypy --strict, and lint-imports (all exit code 0).
4. `cli-run.txt`: Raw outputs of all 3 required CLI execution paths.
5. `contract-sample.json`: Representative JSON contract samples for preview, 409 conflict, and confirm.
6. `api-specialist-review.md`: Verbatim API specialist audit and approval.
7. `ui-specialist-review.md`: Verbatim UI specialist audit and approval.
8. `message-to-reality-checker.md`: This document.
