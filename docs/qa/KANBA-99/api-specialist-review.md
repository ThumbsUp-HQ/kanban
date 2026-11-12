# API Specialist Gate Review: KANBA-99 (KB-P3-06)

- **Ticket**: `KANBA-99` (`KB-P3-06`: Issue subscriptions, auto-subscribe rules, per-event mute & notifications via outbox)
- **Reviewer**: `@arch-reviewer` (Systems/Backend Architect & API Specialist)
- **Branch**: `feat/KANBA-99` (`HEAD: 08c95a2`)
- **Worktree**: `/tmp/kb-wt-KANBA-99`
- **Scope**: `database/migrations/versions/p3_06_notifications.py`, `kanban/api/v1/subscriptions.py`, `kanban/api/v1/notifications.py`, `kanban/api/v1/schemas/notifications.py`, `kanban/services/subscriptions.py`, `kanban/services/notifications.py`

---

### 1. Architectural & Security Evaluation

#### A. REST API Endpoints & Timing Floor (S7.2 8l, S3.4)
- All mutating endpoints (`subscribe_issue`, `patch_subscription`, `unsubscribe_issue`, `mark_notification_read`, `mark_all_read`) are wrapped in `timing_floor(floor_ms=25.0)`.
- Issue subscription routes (`/api/v1/issues/{issue_ref}/subscription`) require `VIEW` capability on the target issue. Unreadable or nonexistent issues return uniform HTTP 404 responses with zero principal or issue key leakage.
- `PATCH /api/v1/issues/{issue_ref}/subscription` validates `muted_event_types` against an allowlist of 7 mutable event types (`COMMENT_CREATED`, `ISSUE_STATE_CHANGED`, `ISSUE_FIELD_CHANGED`, `ISSUE_DESCRIPTION_CHANGED`, `ISSUE_LABELS_CHANGED`, `ASSIGNEE_ADDED`, `ASSIGNEE_REMOVED`), rejecting invalid types with HTTP 422 `EVENT_TYPE_NOT_MUTABLE` and un-subscribed issues with HTTP 409 `NOT_SUBSCRIBED`.
- Notification listing (`GET /api/v1/notifications`) implements keyset pagination on `(created_at, id)` with URL-safe base64 cursor encoding and strict page limit boundaries (`1..100`).
- Individual notification marking (`POST /api/v1/notifications/{id}/read`) enforces ownership via RLS and returns HTTP 404 for foreign notification identifiers.

#### B. Auto-Subscribe Logic & Tombstone Semantics (S7.2 8l)
- Auto-subscription is registered via the transactional activity listener:
  1. `ISSUE_CREATED`: Creator is auto-subscribed (`source=CREATOR`).
  2. `ASSIGNEE_ADDED`: Principal assignee holding `VIEW` capability is auto-subscribed (`source=ASSIGNEE`). Free-text assignees are ignored.
  3. `COMMENT_CREATED`: Mentioned principals holding `VIEW` capability are auto-subscribed (`source=MENTION`).
- Tombstone invariant: Explicit `DELETE` sets `unsubscribed_at`. Subsequent issue events (e.g. re-assignment or mention) inspect the tombstone and refuse to re-subscribe the user against their intent.
- Subscription state changes are strictly personal preferences and do not pollute the hash-chained activity ledger.

#### C. Notification Delivery, Live Access Check & Outbox Hygiene (S2.2, S2.4, S3.4)
- Actor exclusion: The event actor is excluded from receiving notifications for their own mutations (`sub_pid == envelope.actor_principal_id`).
- Live `VIEW` capability is evaluated inside the same database transaction against `effective_resource_access` (`allow_mask & 1 == 1` and `deny_mask & 1 == 0`). If a subscriber loses view permissions before event dispatch, notification creation is completely suppressed.
- Recipient bounded ceiling: Delivery is capped at 500 recipients per activity event (`MAX_NOTIFICATION_RECIPIENTS = 500`), logging a structured warning if exceeded to prevent transaction blowup.
- Sensitive data isolation: Outbox events (`topic="notification.created"`) write strictly entity IDs (`recipient_principal_id`, `notification_id`), completely omitting issue summary, description, or comment prose.
- Wakeup trigger: Transaction commits fire PostgreSQL notification channel `pg_notify('outbox_wakeup')`.

#### D. Database Schema & RLS Isolation
- Table `notifications` enforces `FORCE ROW LEVEL SECURITY`.
- RLS policies restrict `SELECT` and `UPDATE` strictly to `recipient_principal_id = app_current_principal_id()`.
- Partial index `notifications_unread` (`WHERE read_at IS NULL`) guarantees high-performance retrieval for active user notification trays.
- Composite unique constraint `UNIQUE (recipient_principal_id, activity_record_id)` prevents duplicate notifications per activity.

---

### 2. Verification & Test Metrics

- **Unit Tests**: 12/12 pytest passed in 4.71s across `test_subscriptions.py` and `test_notifications.py`.
- **Coverage**: 96.88% total coverage across touched modules:
  - `kanban/api/v1/notifications.py`: 100%
  - `kanban/api/v1/subscriptions.py`: 100%
  - `kanban/services/subscriptions.py`: 100%
  - `kanban/services/notifications.py`: 95%
- **Static Analysis**: Ruff check clean, Ruff format clean (323 files), Mypy strict clean (319 files), ImportLinter 2/2 kept, License gate 0 violations, zero Unicode dashes.
- **Proof Bundle**: Complete forensic bundle (`schema-dump.sql`, `outbox-sample.json`, `contract-sample.json`, `unit-test-results.txt`, `build-check.txt`, `git-diff.patch`).

---

### 3. Gate Verdict

The Issue Subscriptions and Notifications subsystem complies with all architectural, security, access control, and quality invariants.

**VERDICT: APPROVED**
