# API Specialist Gate Final Audit: APPROVED for KANBA-91 (KB-P3-12)

- Auditor: arch-reviewer (Swarm Systems/Backend Architect & API Specialist Gate)
- Worktree: `/tmp/kb-wt-KANBA-91`
- Branch: `feat/KANBA-91`
- Ticket: `KANBA-91` (`KB-P3-12`: `[Phase 3 / API] Fractional Base-62 COLLATE "C" board rank, 1-row move API, WIP limits & background rebalance`)

---

### 1. Executive Summary & Verification Matrix
A forensic backend architecture and API Specialist Gate audit was conducted for `KANBA-91` in `/tmp/kb-wt-KANBA-91`. `KB-P3-12` delivers the core card positioning, drag-and-drop movement, and column WIP enforcement engine. The architecture features a strictly ordered Fractional Base-62 engine aligning with PostgreSQL `COLLATE "C"`, single-row atomic card repositioning, soft WIP warning telemetry, hard WIP policy enforcement with audited AAL2 admin overrides, and an advisory-locked background column rebalancing service with transactional outbox publishing. All implementations were evaluated against Spec Sections 6.4 (items 1 & 3), 1.3, 11.4, 3.4, and 5.4.

| Verification Dimension | Specification Target | Observed Status | Verdict |
| :--- | :--- | :--- | :--- |
| **REST Router & Mounting** | `POST /issues/{issue_ref}/move` mounted | Mounted on `build_v1_router()` via `issue_move_router` in `kanban/api/v1/issue_move.py` | PASS |
| **Timing Equalization** | 25.0ms timing floor on move endpoint | Wrapped in `async with timing_floor(floor_ms=25.0):` | PASS |
| **Single-Row Mutation** | Updates strictly 1 row on reorder/move | Executes `UPDATE issues SET state_id = :s, board_rank = :r WHERE id = :id` | PASS |
| **Fractional Base-62 Engine** | `0-9 < A-Z < a-z` matching `COLLATE "C"` | `ALPHABET` byte-order matches PostgreSQL `COLLATE "C"`; non-zero tail enforced | PASS |
| **Dense Midpoint Invariant** | Compute shortest midpoint `prev < m < next` | 200 adversarial bisections satisfy `prev.encode() < mid.encode() < next.encode()` | PASS |
| **Anchor Positioning & Locks** | Advisory state lock & row lock `FOR UPDATE` | Locks target state advisory lock and moved issue row; resolves anchors under VIEW | PASS |
| **Anchor Conflict Guard** | Detect concurrent anchor shifts | Rejects reversed anchors with RFC 7807 `409 ANCHOR_ORDER_CONFLICT` | PASS |
| **RBAC & Capability Check** | `EDIT` for intra-column, `TRANSITION` for cross | Enforced; missing capabilities reject with `403 INSUFFICIENT_CAPABILITY` | PASS |
| **Soft WIP Telemetry** | Returns 200 with `wip_warning` payload | Move succeeds 200 with `wip_warning: {soft_limit, resulting_count}` | PASS |
| **Hard WIP Enforcement** | Non-admins blocked on hard limit | Rejects non-admin moves with RFC 7807 `409 WIP_HARD_LIMIT_EXCEEDED` | PASS |
| **AAL2 Admin Hard Override** | AAL2 + 10..500 char justification required | Rejects AAL1 (`403 AAL2_REQUIRED`) and short reason (`409 WIP_HARD_LIMIT_OVERRIDE_REQUIRED`) | PASS |
| **Overridden Audit Ledger** | Emit `WIP_HARD_LIMIT_OVERRIDDEN` | Emitted under category `HISTORY` with reason, hard_limit, and resulting count | PASS |
| **Background Rebalance** | Rebalances columns when `len(rank) > 32` | Advisory-locked rebalance generates <=7 char ranks, emits `BOARD_COLUMN_REBALANCED` | PASS |
| **Outbox Event Integration** | Transactional `column.rebalanced` event | Enqueued in `outbox_events` within the same transaction as bulk updates | PASS |
| **Unit Test Coverage** | Mandatory Feature Tests (>=95%) | 18/18 passed in 4.13s; 99.24% branch+line coverage across target modules | PASS |
| **Build & Lint Cleanliness** | Zero-Tolerance Quality Mandate | Ruff clean, Ruff format clean (211 files), Mypy strict clean (209 files), Lint-imports clean | PASS |

---

### 2. Forensic Architectural Analysis

1. **Fractional Base-62 Engine & PostgreSQL `COLLATE "C"` (Spec S6.4 item 1):**
   - In `kanban/services/board_rank.py`, `ALPHABET` is defined as `"0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"`.
   - This alphabet adheres strictly to ASCII numeric order: digits `0x30..0x39`, uppercase letters `0x41..0x5A`, and lowercase letters `0x61..0x7A`.
   - String comparisons in Python (`<`, `<=`, `>`, `>=`) evaluate identical byte sequences to PostgreSQL `ORDER BY board_rank COLLATE "C"`.
   - Canonical ranks adhere to `^[0-9A-Za-z]{1,256}$` with a strict **non-zero final character invariant** (`rank[-1] != '0'`). This guarantees that the fractional space between any two ranks remains infinitely subdivisible without hitting trailing zero truncations.
   - `midpoint_rank()` computes the shortest midpoint satisfying `prev < mid < next`. If `prev >= next`, it raises `RankOrderError`.
   - Property tests confirm that 200 sequential head, tail, and adversarial same-slot bisection insertions maintain exact monotonic ordering matching PostgreSQL `COLLATE "C"`.

2. **Single-Row Mutation & Concurrency-Safe Anchoring (Spec S6.4 item 1, S1.3):**
   - The endpoint `POST /api/v1/issues/{issue_ref}/move` in `kanban/api/v1/issue_move.py` is wrapped with `async with timing_floor(floor_ms=25.0):`.
   - Moving a card executes a single SQL update:
     `UPDATE issues SET state_id = :s, board_rank = :r WHERE id = :id`
     All neighboring cards remain 100% untouched and byte-identical, eliminating N-row cascading write locks and database churn.
   - Target column concurrency is serialized via `pg_advisory_xact_lock(hashtext('kanban.state.' || target_state_id::text))`, and the moved issue row is locked with `SELECT ... FOR UPDATE`.
   - `after_issue` and `before_issue` anchors are validated under the caller's RLS session. If anchors are reversed or shifted by a concurrent transaction (`prev_rank >= next_rank`), the endpoint emits RFC 7807 `409 ANCHOR_ORDER_CONFLICT`, prompting the frontend to reload column state.
   - When neither anchor is specified, the card is appended to the bottom of the column (`prev = max(board_rank)`).

3. **RBAC & Capability Authorization (Spec S3.4):**
   - Unreadable issues or nonexistent issue references return indistinguishable RFC 7807 `404 NOT_FOUND`.
   - Moving an archived issue fails closed with RFC 7807 `409 ISSUE_ARCHIVED`.
   - Intra-column reordering (`target_state_id == issue.state_id`) requires `Capability.EDIT`.
   - Cross-column state transitions require both `Capability.EDIT` and `Capability.TRANSITION` on the issue. Missing either capability returns RFC 7807 `403 INSUFFICIENT_CAPABILITY`.

4. **Soft & Hard WIP Limit Enforcement & Audited AAL2 Override (Spec S6.4 item 3, S11.4):**
   - WIP limits are evaluated only when crossing column boundaries into `target_state_id`. Intra-column reordering never triggers WIP limits.
   - Active cards (non-deleted, non-archived) in `target_state_id` are counted globally across the project, preventing WIP bypasses via private card creation.
   - **Soft WIP:** When `resulting_count > wip_soft_limit`, the move succeeds with HTTP 200 and returns `wip_warning: {"soft_limit": N, "resulting_count": M}`.
   - **Hard WIP:**
     * Standard project members (`MEMBER`, `VIEWER`, `GUEST`) are blocked with RFC 7807 `409 WIP_HARD_LIMIT_EXCEEDED` (`{"hard_limit": N, "current_count": M}`).
     * Administrators (`PROJECT_ADMIN`, `SERVER_ADMIN`) with session AAL1 are blocked with RFC 7807 `403 AAL2_REQUIRED`.
     * Administrators lacking a valid plain-text justification between 10 and 500 characters are blocked with RFC 7807 `409 WIP_HARD_LIMIT_OVERRIDE_REQUIRED`.
     * Administrators with verified AAL2 and a valid justification succeed with HTTP 200. The override is immutably recorded to the activity ledger as `WIP_HARD_LIMIT_OVERRIDDEN` with the justification, hard limit, and resulting count.

5. **Advisory-Locked Background Column Rebalancing (Spec S6.4 item 3):**
   - When successive bisections cause `len(board_rank) > 32` (`REBALANCE_THRESHOLD_LEN`), the response sets `rebalance_scheduled: true`.
   - In `kanban/jobs/board_rebalance.py`, `rebalance_column()` acquires a transaction-scoped advisory lock `pg_try_advisory_xact_lock(hashtext('kanban.rebalance.' || state_id::text))`.
   - Queries all active issues in the column ordered by `board_rank COLLATE "C" ASC, id ASC`, generates evenly spaced ranks (`generate_evenly_spaced_ranks(n)` of width `<= 7` chars), and bulk-updates only changed rows.
   - Emits a single `BOARD_COLUMN_REBALANCED` activity record on the project and publishes a transactional `column.rebalanced` event to `outbox_events`.
   - Registered under the CLI job runner: `kanban-ctl jobs run board-rebalance [--project <IDENT>]`.

---

### 3. Formatting & Typography Compliance
- Strictly plain ASCII hyphens `-` used throughout. Zero Unicode em-dashes (`U+2014`) or en-dashes (`U+2013`) detected.

---

### 4. Gate Sign-Off
I have completed the backend architecture and API Specialist Gate audit for `KANBA-91`. All single-row mutations, timing floors, Base-62 COLLATE "C" rank mathematics, soft and hard WIP limits, AAL2 override gates, and advisory-locked rebalancing workflows are satisfied.

Verdict: APPROVED
