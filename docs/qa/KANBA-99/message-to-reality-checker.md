# Reality-Checker Audit Note: KANBA-99 (KB-P3-06)

## Architectural Scope & Technical Implementation
This ticket (`KANBA-99` / `KB-P3-06`: `[Phase 3 / API] Issue subscriptions, auto-subscribe rules, per-event mute & notifications via outbox`) implements personal issue subscriptions, per-event mute rules, auto-subscription lifecycle on domain activities, and zero-leakage notification delivery via transactional outbox under Spec S7.2 (8l), S2.2, and S2.4:

1. **Target Files**:
   - `database/migrations/versions/p3_06_notifications.py`: Schema migration extending `issue_subscriptions` with `muted_event_types TEXT[]` and `unsubscribed_at TIMESTAMPTZ`, and creating `notifications` with FORCE RLS and partial unread index.
   - `database/migrations/sql/p3_06_notifications.up.sql` and `p3_06_notifications.down.sql`: Idempotent SQL scripts with strict RLS policies: `recipient_principal_id = app_current_principal_id()`.
   - `database/models/issues.py`: Extended `IssueSubscription` model with `muted_event_types` and `unsubscribed_at`.
   - `database/models/notifications.py`: Created `Notification` DeclarativeBase model with unique constraint on `(recipient_principal_id, activity_record_id)`.
   - `kanban/api/v1/schemas/notifications.py`: Pydantic request and response schemas with `ConfigDict(extra="forbid")`, supporting `SubscriptionResponse`, `SubscriptionPut`, `SubscriptionPatch`, `NotificationListResponse`, and `MarkAllReadResponse`.
   - `kanban/services/subscriptions.py`: Issue subscription service managing personal subscriptions, mute allowlists, and tombstone records.
   - `kanban/services/notifications.py`: Notifications service and in-transaction activity listener managing auto-subscriptions and outbox-backed notification delivery.
   - `kanban/api/v1/subscriptions.py`: 4 REST endpoints mounted on `build_v1_router()` (`GET`, `PUT`, `PATCH`, `DELETE` `/api/v1/issues/{issue_ref}/subscription`).
   - `kanban/api/v1/notifications.py`: 3 REST endpoints mounted on `build_v1_router()` (`GET /api/v1/notifications`, `POST /api/v1/notifications/{id}/read`, `POST /api/v1/notifications/read-all`).

2. **Security & State Machine Invariants**:
   - **Zero Sensitive Data Leakage in Outbox**: Outbox payloads carry only IDs (`topic`, `recipient_principal_id`, `notification_id`), with zero issue summary, zero issue body, and zero issue text.
   - **Tombstone Invariant**: An explicit `DELETE` records `unsubscribed_at` tombstone timestamp; subsequent activity rules (`ASSIGNEE_ADDED`, `COMMENT_CREATED` mentions) never re-subscribe the user.
   - **Actor Exclusion**: Actors never receive notifications for their own mutations.
   - **Per-Event Mute Allowlists**: Muting specific event types (`COMMENT_CREATED`, `ISSUE_STATE_CHANGED`, etc.) suppresses delivery for those events while retaining unmuted events.
   - **Live Capability Gate**: Delivery verifies live `VIEW` capability in `effective_resource_access` (`(allow_mask & 1 = 1) AND (deny_mask & 1 = 0)`) in the same transaction.
   - **Bounded Delivery**: Capped at 500 recipients per event to bound transaction time and memory.
   - **Row-Level Security**: `notifications` table has `FORCE ROW LEVEL SECURITY` ensuring users can only query or update their own notification records.
   - **Zero Activity Pollution**: Subscribe, unsubscribe, and mute are personal preferences and emit zero activity records to the immutable ledger.

3. **Verification & Quality Status**:
   - **Unit Tests**: 12/12 tests passing in 4.73s with **96.88%** branch + line coverage (`kanban.api.v1.notifications` 100%, `kanban.api.v1.subscriptions` 100%, `kanban.services.subscriptions` 100%, `kanban.services.notifications` 95%), exceeding the 95% threshold.
   - **Static Checks**: Ruff check clean, Ruff format clean (323 files), Mypy strict clean (319 files), Lint-imports clean (2 kept, 0 broken), License gate clean (violations=0), Zero non-ASCII dashes repo-wide.
   - **Contract Proof**: `contract-sample.json` captures all 5 wire exchanges required by Reality-Checker (`unsubscribe_204`, `subscribe_200`, `mute_200`, `invalid_mute_422`, `notifications_list_200`, `foreign_notification_read_404`).
   - **Outbox Proof**: `outbox-sample.json` captures raw JSON structure of `notification.created` event confirming zero summary/body leakage.
   - **Schema Dump**: `schema-dump.sql` captures DDL, indexes, and RLS policies for `notifications` and `issue_subscriptions`.
