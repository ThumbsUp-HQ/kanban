# API & Security Specialist Review: KAN-310 (`[KB-NOTIF-WS-01]`)

- **Reviewer Persona:** `backend-architect` / `security-engineer` / `api-tester` (API & Security Specialist Reviewer)
- **Ticket:** `KAN-310` (`[KB-NOTIF-WS-01] Deliver Recipient-Scoped Notifications Over WebSocket/SSE with Multi-Tab Read Sync and Transport-Gated Fallback Polling`)
- **Audited Commit (`HEAD`):** `60228314089adeb693d2d7625220b67916ba52d7` (`60228314`)
- **Audited Branch:** `feat/KAN-310-ws-notifications`
- **Reviewed Artifacts:**
  - `docs/qa/KAN-310/git-diff.patch`
  - `docs/qa/KAN-310/contract-sample.json`
  - `docs/qa/KAN-310/unit-test-results.txt`
  - `docs/qa/KAN-310/build-check.txt`
  - `docs/qa/KAN-310/message-to-reality-checker.md`
- **Reviewed Source & Test Files:**
  - `kanban/realtime/hub.py`
  - `kanban/realtime/replay.py`
  - `kanban/realtime/rls_filter.py`
  - `kanban/services/notifications.py`
  - `kanban/tests/realtime/test_notification_realtime_isolation.py`
  - `kanban/tests/api/test_notifications.py`
  - `kanban/web/src/api/realtime.ts`
  - `kanban/web/src/features/notifications/NotificationsBell.tsx`
  - `kanban/web/src/api/realtime.test.ts`
  - `kanban/web/src/features/notifications/NotificationsBell.test.tsx`

**STATUS: APPROVED**

---

## 1. Executive Summary

The implementation of `KAN-310` delivers enterprise-grade, recipient-scoped realtime notification streaming over WebSocket and Server-Sent Events (SSE), coupled with transactional multi-tab read synchronization and transport-gated fallback polling.

From an API architecture and security perspective:
1. **Zero Information Disclosure & Anti-Enumeration:** Realtime channel resolution treats unauthorized cross-user subscription attempts (`user:<foreign_uuid>` or malformed identifiers) as indistinguishable `None` (`NOT_FOUND` on WebSocket subscribe; silent exclusion on SSE), preventing user existence enumeration.
2. **Strict RLS & Recipient Isolation:** Notification topics (`notification.created`, `notification.read`, `notification.read_all`) are restricted strictly to recipient connections matching `notifications:self` or `user:<recipient_uuid>` within the active workspace. Post-commit `VIEW` revocation checks on `notification.created` are fully preserved via `authorize_event_recipients`.
3. **Multi-Tab Read Sync with Clean RLS Insertion:** `mark_notification_read` and `mark_all_read` emit ID-only OutboxEvent records via `insert(OutboxEvent).inline()` without `RETURNING`, completely avoiding non-admin `WORKSPACE_MEMBER` select RLS violations while maintaining zero-leakage payload contracts (`topic`, `recipient_principal_id`, `notification_id` / `marked_count`).
4. **Transport-Gated Polling & Anti-Overfetch:** The web client subscribes to `notifications:self`, shuts off periodic HTTP polling entirely while WebSocket or SSE transport is active (`refetchInterval: false`), and only engages a 30s interval when transport is degraded (`reconnecting` or `closed`), with single-shot recovery resynchronization.
5. **Coverage & Hygiene:** 65 Python unit/integration tests and 62 Vitest tests pass with 97% overall Python coverage and >95% frontend coverage across all touched modules. Zero em/en-dashes exist across the repository.

---

## 2. API Contract, Wire Protocol & Enumeration Defense

### 2.1 Channel Resolution (`kanban/realtime/hub.py`)
- `_CHANNEL_REGEX` updated to support `user:<uuid>` and the literal alias `notifications:self`.
- `RealtimeHub._resolve_user_channel` and `resolve_channel`:
  - When `raw_id == "self"` and `kind == "notifications"`, resolves to canonical `("user:<principal_id>", principal_id, "user")`.
  - When `kind == "user"`, validates that parsed `target_uuid == principal_id`. If `target_uuid != principal_id` or malformed, returns `None`.
  - Rejection produces identical `NOT_FOUND` on WebSocket subscription (`subscribe_error` with `code="NOT_FOUND"`), preventing attackers from probing user UUID validity.
- `RealtimeHub.handle_unsubscribe`:
  - Transparently prunes both alias `notifications:self` and canonical `user:<principal_id>` from `conn.subscribed_channels`.

### 2.2 Wire Frame Contracts (`docs/qa/KAN-310/contract-sample.json`)
The wire contracts were verified via end-to-end recorded exchanges:
- `ws_subscribe_notifications_self_ack`: Valid client subscription receives `subscribe_ack` for `notifications:self`.
- `ws_subscribe_cross_user_not_found`: Probing foreign `user:<foreign_uuid>` or invalid `notifications:all` returns `NOT_FOUND`.
- `ws_notification_created_frame`: Carries minimal payload `{"topic": "notification.created", "recipient_principal_id": "...", "notification_id": "..."}`, omitting sensitive issue/comment Markdown bodies.
- `ws_notification_read_frame` & `ws_notification_read_all_frame`: Minimal ID-only sync payloads with `object_id: null` and `project_id: null`.
- `sse_notifications_self_replay`: SSE endpoint `/sse?channels=notifications:self&last_event_id=1` correctly filters and streams replayed notification events for the authenticated principal.

---

## 3. Security Architecture & Threat Mitigation

### 3.1 Recipient Intersection & View Authorization (`kanban/realtime/rls_filter.py`)
- `NOTIFICATION_TOPICS` constant explicitly defined as `frozenset({"notification.created", "notification.read", "notification.read_all"})`.
- `_filter_notification_candidates`:
  - Extracts `recipient_principal_id` from event payload.
  - Intersects `candidate_principals` with `{recipient_uuid}`. Any connection belonging to a different user is dropped before RLS checks or dispatch.
- `authorize_event_recipients`:
  - For `notification.created` (bound to `object_id = issue_id`): re-evaluates database RLS permissions in the context of the recipient. If the recipient was removed from the project or lost `VIEW` capability between commit and dispatch, the event is suppressed.
  - For `notification.read` and `notification.read_all` (`object_id = None, project_id = None`): safely bypasses object-level checks and returns the recipient principal.

### 3.2 Outbox Replay Isolation (`kanban/realtime/replay.py`)
- `OutboxReplayer._match_notification_channel`:
  - Enforces that notification replay events only match if `row_ws_id == workspace_id`, `recipient_principal_id == principal_id`, and the client requested `notifications:self` or `user:<principal_id>`.
  - Replay events never leak through `workspace:<ws_id>` or `project:<proj_id>` channels.

### 3.3 Transactional Outbox Insertion (`kanban/services/notifications.py`)
- `mark_notification_read`:
  - Verifies `notif.read_at is None` before executing state update.
  - Inserts into `OutboxEvent` using SQLAlchemy `.inline()` without `.returning()`. Non-admin members (`WORKSPACE_MEMBER`) have INSERT privileges but restricted SELECT privileges under RLS; avoiding RETURNING prevents Postgres RLS permission violations.
  - Idempotent: repeated calls when `read_at` is already set emit 0 Outbox rows.
- `mark_all_read`:
  - Checks `marked = int(result.rowcount)`. Only emits an OutboxEvent when `marked > 0`.
  - Repeated calls when 0 unread notifications remain emit 0 Outbox rows.

---

## 4. Test Verification & Code Coverage Analysis

### 4.1 Pytest Suite Execution
Executed 65 tests in `kanban/tests/realtime/` and `kanban/tests/api/`:
- `kanban/tests/realtime/test_notification_realtime_isolation.py`: 6 passed
  - Anti-enumeration on foreign UUID subscription
  - Multi-tab fanout to same user across multiple connections
  - Leak prevention across shared workspace and project channels
  - Post-commit VIEW revocation filtering
  - SSE replay isolation with last_event_id
  - Defensive replayer error handling
- `kanban/tests/api/test_notifications.py`: 3 passed
  - Non-admin MEMBER mark_read / mark_all_read RLS compliance
  - Forbidden payload keys verification (no sensitive summaries or bodies in outbox)
  - Foreign user 404 isolation
- Existing notification and realtime regression suites: 56 passed

### 4.2 Code Coverage Metrics
Total Python statement coverage across touched modules: **97%** (exceeds 95% threshold):
- `kanban/realtime/hub.py`: **95%**
- `kanban/realtime/replay.py`: **99%**
- `kanban/realtime/rls_filter.py`: **97%**
- `kanban/services/notifications.py`: **99%**

Total Frontend Vitest statement coverage:
- `kanban/web/src/api/realtime.ts`: **99.41%** (48 passed)
- `kanban/web/src/features/notifications/NotificationsBell.tsx`: **100%** (14 passed)

### 4.3 Static Checks
- `make check`: 0 errors (ruff check, ruff format, mypy, lint-imports, check-migrations)
- `pnpm --dir kanban/web typecheck`: 0 errors
- `pnpm --dir kanban/web lint`: 0 errors
- `pnpm --dir kanban/web build`: 0 errors
- `uv run python -m scripts.check_no_dashes --all`: 0 errors (0 em/en-dashes)

---

## 5. Review Sign-Off

The API, wire contracts, database RLS, and security architecture satisfy all requirements with zero deficiencies and comprehensive regression coverage.

**STATUS: APPROVED**
