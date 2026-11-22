# Reality-Checker Verification Packet: KAN-70

**Ticket ID:** KAN-70  
**Title:** [KB-SEC-TAINT-01] Add Content Provenance Trust Tiers, Same-Project Prompt-Injection Taint Tracking & Dynamic MCP Capability Stripping (4 Problems)  
**Branch:** `feat/KAN-70-content-provenance-taint`  
**Workspace:** `/home/adamoutler/.gemini/antigravity-cli/worktrees/ceecd8ef-f0c3-4c2c-b75c-e6eb23e99760/swarm-b-kan70-13acc0b7`  

---

## 1. Executive Summary & Problem Breakdown

All 4 scoped problems for KAN-70 have been fully implemented, rigorously tested with 42 automated tests, and verified against all project static gates (`make check`).

### Problem 1: Content Provenance Trust Tiers & Schema Invariants
- **Alembic Migration:**
  * Created `database/migrations/versions/p6_07_content_provenance_and_taint.py` (`revision = "p6_07_content_provenance_and_taint"`, `down_revision = "p6_06_crypto_shredded_activity_ledger"`).
  * Up/Down SQL pair in `database/migrations/sql/p6_07_content_provenance_and_taint.{up,down}.sql`.
- **Database Schema & ORM Parity:**
  * Added `provenance_tier TEXT NOT NULL DEFAULT 'trusted_member'` with check constraint on valid values (`trusted_member`, `verified_agent`, `imported`, `external_webhook`, `public_reporter`, `untrusted_intake`).
  * Added stored generated column `is_untrusted_content BOOLEAN GENERATED ALWAYS AS (provenance_tier IN ('imported', 'external_webhook', 'public_reporter', 'untrusted_intake')) STORED`.
  * Applied across `issues`, `issue_comments`, `docs`, `pages`, and `stickies`.
  * ORM parity verified in `database/models/issues.py`, `database/models/knowledge.py`, `database/models/prose.py`, and `database/tests/test_p1_17_models.py`.
- **Server-Side Derivation & Self-Upgrade Protection:**
  * Implemented `_derive_provenance_tier(request, caller)` in `kanban/api/v1/issues.py`.
  * Untrusted ingestion channels (`x-kanban-channel` or `x-ingestion-channel` set to `imported`, `webhook`, `public_reporter`, `untrusted_intake`, or corresponding token scopes) cannot self-upgrade to `trusted_member` or `verified_agent`. Attempts are rejected with `403 PROVENANCE_SELF_UPGRADE_FORBIDDEN`.
  * Claiming `verified_agent` is strictly forbidden unless the principal is an authenticated agent.

### Problem 2: Same-Project Prompt-Injection Taint Tracking & Exfiltration Guard
- **Table Extension:**
  * Added `untrusted_source_object_id UUID NULL` and `contains_untrusted_content BOOLEAN NOT NULL DEFAULT FALSE` to `mcp_read_taint`.
- **Taint Guard & Taint Recorder:**
  * Extended `TaintRecorder.record_project_ids` and added `record_untrusted_read` in `kanban/security/read_taint.py`.
  * Reading untrusted content in Project A records `contains_untrusted_content = TRUE` and sets response header `X-Kanban-Untrusted-Taint: 1`.
  * Updated `TaintGuard.check_write()`:
    - Whenever `contains_untrusted_content = TRUE`, blocks subsequent mutating or linking operations across all projects (including the same project!) with `409 UNTRUSTED_CONTENT_TAINT_ACTIVE`.
    - Emits `MCP_TAINT_BLOCKED` activity event to the immutable ledger.
    - Supplying an explicit human confirmation token (`human_confirmation_token` query param or `X-KB-Human-Confirmation-Token` header) bypasses the block for safe human-in-the-loop overrides.
    - Crucial invariant preserved: Reading clean `trusted_member` content in Project A does NOT trigger untrusted taint, and normal same-project mutations continue without interruption.

### Problem 3: Dynamic MCP Capability Stripping & Notification
- **Session Taint Tracking:**
  * Added `tainted_by_untrusted: bool = False` to `Session` in `mcp/protocol.py`.
  * Added `mark_untrusted_tainted(session_id)` to `SessionStore` and `InMemorySessionStore`.
- **Dynamic Tool List Notification & Capability Advertising:**
  * Advertised `"tools": {"listChanged": True}` in `_handle_initialize` for dynamic clients.
  * Once a tool read returns untrusted content (marked via `X-Kanban-Untrusted-Taint: 1` or detected untrusted provenance), the session is marked untrusted-tainted.
  * In `_handle_tools_list()`, all mutating and linking tools (`create_ticket`, `update_ticket`, `begin_work`, `transition_ticket`, `complete_work`, `add_comment`, `link_objects`, etc.) are stripped from the tool catalog.
  * Pre-dispatch enforcement in `_handle_tools_call()`: If a client invokes a mutating tool on a tainted session, dispatch is aborted pre-execution with an `UNTRUSTED_CONTENT_TAINT_ACTIVE` error packet.

### Problem 4: Full-Field Transition Context Spotlighting & Delimiter Collision Safety
- **Full-Field Spotlighting:**
  * Updated `agent/context/transition_context.py` to support `actor` and hydrated `comments` on `TicketSnapshot`.
  * When untrusted content is present, spotlights `summary`, `priority`, `labels`, `actor`, and each hydrated comment with randomized `<<<UNTRUSTED_TICKET_DATA_{16-hex}>>>` delimiters.
  * Hydrated comments preserve their individual `provenance_tier` and spotlighted body text.
- **Delimiter Collision Resistance:**
  * Delimiter generation performs multi-field collision checking across `summary`, `priority`, `labels`, `description`, `actor`, and all comments.
  * Attempts up to 8 randomized suffixes (`MAX_DELIMITER_ATTEMPTS = 8`).
  * If hostile content matches candidate delimiters across all attempts, raises `ContextDelimiterCollisionError`.
  * Backwards-compatible Pydantic schema export via `__get_pydantic_json_schema__` preserves exact equality with canonical `kb-transition-context-v1.json`.

---

## 2. Test Execution & Coverage Evidence

Full test run log captured in `docs/qa/KAN-70/unit-test-results.txt`:
```bash
uv run pytest \
  kanban/tests/security/test_untrusted_content_taint.py \
  kanban/tests/security/test_read_taint.py \
  mcp/tests/test_dynamic_taint_stripping.py \
  mcp/tests/test_protocol.py \
  agent/tests/context/test_transition_context_spotlighting.py \
  agent/tests/context/test_transition_context.py \
  database/tests/test_p1_17_models.py
```
**Outcome:** 42 passed in 4.60 seconds (100% pass rate).

### Test Suite Breakdown:
1. `kanban/tests/security/test_untrusted_content_taint.py` (5 tests):
   - `test_trusted_member_same_project_mutation_allowed`: Positive control verifying trusted reads do not block same-project writes.
   - `test_untrusted_content_same_project_mutation_blocked`: Negative control verifying untrusted reads block subsequent same-project writes with 409 and emit `MCP_TAINT_BLOCKED`.
   - `test_untrusted_content_human_confirmation_bypass`: Bypass control verifying explicit human token permits execution.
   - `test_provenance_self_upgrade_forbidden`: Security control verifying untrusted channels cannot self-upgrade to trusted tiers (403).
   - `test_untrusted_comment_taint_propagation`: Comment control verifying untrusted comments on issues trigger untrusted taint headers.
2. `kanban/tests/security/test_read_taint.py` (7 tests): Cross-project exfiltration guard tests.
3. `mcp/tests/test_dynamic_taint_stripping.py` (2 tests):
   - `test_initialize_advertises_dynamic_tools_list_changed`: Verifies `listChanged: True`.
   - `test_dynamic_taint_stripping_lifecycle`: Verifies complete lifecycle (read untrusted -> session marked tainted -> mutating tools stripped from list -> mutating tools blocked pre-dispatch).
4. `mcp/tests/test_protocol.py` (12 tests): MCP protocol invariants and regression prevention.
5. `agent/tests/context/test_transition_context_spotlighting.py` (3 tests):
   - `test_untrusted_issue_full_field_spotlighting`: Verifies spotlighting across summary, priority, labels, actor, comments.
   - `test_delimiter_collision_detection_and_regeneration`: Verifies collision detection and safe re-generation.
   - `test_max_delimiter_collisions_raises_error`: Verifies exhaustion raises `ContextDelimiterCollisionError`.
6. `agent/tests/context/test_transition_context.py` (8 tests): Transition context canonical schema and size limits.
7. `database/tests/test_p1_17_models.py` (5 tests): Database model schema parity and registration.

---

## 3. Build & Static Quality Verification

Build log captured in `docs/qa/KAN-70/build-check.txt`:
```bash
make check
```
Results:
- `uv run ruff check .` -> All checks passed (0 errors)
- `uv run ruff format --check .` -> 2227 files already formatted (0 unformatted files)
- `uv run mypy` -> Success: no issues found in 1235 source files
- `uv run lint-imports` -> 2 kept, 0 broken (Contracts clean)
- `uv run python -m scripts.check_no_dashes --all` -> 0 violations
- `uv run python -m database.migrations.cli check-migrations --static-only` -> OK: All 69 migrations valid. Single head: `p6_07_content_provenance_and_taint`

---

## 4. Modified & Created Files Checklist

Strictly within the assigned owned slice:
- Migration:
  * `database/migrations/versions/p6_07_content_provenance_and_taint.py`
  * `database/migrations/sql/p6_07_content_provenance_and_taint.up.sql`
  * `database/migrations/sql/p6_07_content_provenance_and_taint.down.sql`
- Models & Schema:
  * `database/models/issues.py`
  * `database/models/knowledge.py`
  * `database/models/prose.py`
  * `database/models/mcp_read_taint.py`
  * `database/tests/test_p1_17_models.py`
- Security & API:
  * `kanban/security/read_taint.py`
  * `kanban/api/v1/issues.py`
  * `kanban/api/v1/comments.py`
  * `kanban/tests/security/test_untrusted_content_taint.py`
- MCP Protocol:
  * `mcp/protocol.py`
  * `mcp/tests/test_dynamic_taint_stripping.py`
- Agent Transition Context:
  * `agent/context/transition_context.py`
  * `agent/tests/context/test_transition_context_spotlighting.py`
- QA Evidence:
  * `docs/qa/KAN-70/build-check.txt`
  * `docs/qa/KAN-70/unit-test-results.txt`
  * `docs/qa/KAN-70/contract-sample.json`
  * `docs/qa/KAN-70/message-to-reality-checker.md`
  * `docs/qa/KAN-70/git-diff.patch`

---

## 5. Typography Compliance

Checked with `uv run python -m scripts.check_no_dashes --all`. Zero em-dashes and zero en-dashes across all files.
