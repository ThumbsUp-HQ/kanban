# API Specialist Gate Review: KANBA-148 (KB-P5-26)

- **Ticket**: `KANBA-148` (`KB-P5-26`: `[Phase 5 / Agent + API + CLI] Sticky -> Doc AI structuring preview, ACL-preserving confirm contract & kanban-agent validate-sticky-promo`)
- **Reviewer**: API Specialist (`backend-architect` persona)
- **Status**: APPROVED

---

## 1. Scope & Endpoint Architecture

The implementation delivers the Sticky to Doc AI structuring preview and confirm contract:
1. `POST /api/v1/stickies/{sticky_id}/promote-preview`
   - Zero-write preview: does not create or mutate database rows.
   - Enforces 25.0ms timing floor with `load_or_404` semantics to prevent object enumeration.
   - Requires `VIEW` and `EDIT` capabilities on the target sticky.
   - Rejects oversized stickies (`> 131,072` bytes) with 413 `STICKY_TOO_LARGE`.
   - Rejects already promoted stickies with 409 `ALREADY_PROMOTED`.
   - Returns structured proposal adhering to `kb-sticky-doc-proposal/v1`, normalized canonical markdown, `original_sha256`, warnings array, and read-only access manifest preview.
2. `POST /api/v1/stickies/{sticky_id}/promote-to-doc`
   - Extended request schema accepting optional `structured_body_markdown` and `expected_sticky_sha256`.
   - Atomic TOCTOU concurrency check: compares `expected_sticky_sha256` against `sticky.body_sha256` stored in PostgreSQL. If modified, raises 409 `STICKY_MODIFIED_SINCE_PREVIEW`.
   - Propagates structured markdown to the created `Doc` and its root `Page` (and sub-pages if present).
   - Preserves all direct ACL entries verbatim (`object_id` mapped from sticky to doc and pages).
   - Generates bidirectional `PROMOTED` object link (`sticky -> doc`) and converts sticky to promoted stub.

---

## 2. Security & Layering Invariants

1. **Clean Layering & Zero Dependency Cycles**:
   - `kanban/api/v1/sticky_promo_ai.py` avoids static imports of `agent/` to preserve the unidirectional layering invariant (`agent -> mcp -> kanban -> database`).
   - Dynamic module resolution loads the agent structuring pipeline and router at runtime (`importlib.import_module("agent...")`).
   - Verified via `lint-imports`: 2 contracts kept, 0 broken.
2. **Prompt Injection & Secret Leakage Defense**:
   - Outbound secret scrubber (`scrub_text`) runs before prompt construction, redacting API keys and passwords.
   - Spotlight boundary isolation encapsulates untrusted sticky markdown within cryptographically random delimiter tokens (`<<<UNTRUSTED_STICKY_DATA_<nonce>>>>`).
   - Canonical markdown normalizer strips dangerous HTML tags (`<script>`, `<iframe>`, `javascript:` URIs) from LLM output.
3. **Lossless Diagram & Fenced Block Integrity**:
   - All fenced code blocks and Mermaid diagrams in rough sticky notes are verified via `verify_fenced_blocks_preserved()`.
   - If dropped by the model, verbatim fallback blocks are appended automatically and flagged with `FENCED_BLOCK_MODIFIED`.
4. **Air-Gap Egress Protection**:
   - External provider routes (`gemini`, `openai`) reject egress in air-gapped workspaces with `AIR_GAP_EGRESS_DENIED`.

---

## 3. Test Coverage & Quality Verification

- Unit & integration tests pass with 100% success rate:
  - `agent/tests/sticky_promo`: 15 passed
  - `kanban/tests/stickies/test_sticky_promo_ai_api.py`: 6 passed
  - `agent/tests/cli/test_validate_sticky_promo.py`: 13 passed
- Combined line and branch coverage: **99.77%** (exceeds 95.0% mandate).
- Mypy strict mode: 0 issues across 460 files.
- Ruff linter & formatter: 0 issues.

The API contract is hardened, secure, and production-ready.
