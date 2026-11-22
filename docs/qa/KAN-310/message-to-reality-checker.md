# Forensic Verification Proof Summary - KAN-310

## Audited Commit & Visual Proof Summary
- **Merged `main` Commit SHA:** `9f3656d153b2e08af69a9c44547e17c25bb79c58` (`9f3656d1`, merging `feat/KAN-310-ws-notifications` at `60228314089adeb693d2d7625220b67916ba52d7`)
- **Zero-Mock Live Container Playwright Screenshots (`docs/qa/KAN-310/screenshots/`, captured against local `kanban-liveqa-1` on `http://localhost:18961` with `data-realtime-state="open"` and `data-polling-active="false"`):**
  - `docs/qa/KAN-310/screenshots/01-desktop-light-notifications-tray.png` (`1440x900` Light)
  - `docs/qa/KAN-310/screenshots/02-desktop-dark-notifications-tray.png` (`1440x900` Dark)
  - `docs/qa/KAN-310/screenshots/03-tablet-notifications-tray.png` (`768x1024` Tablet)
  - `docs/qa/KAN-310/screenshots/04-mobile-portrait-notifications-tray.png` (`390x844` Mobile Portrait)
  - `docs/qa/KAN-310/screenshots/05-mobile-landscape-notifications-tray.png` (`844x390` Mobile Landscape)

## Ticket Summary
`[KB-NOTIF-WS-01] Deliver Recipient-Scoped Notifications Over WebSocket/SSE with Multi-Tab Read Sync and Transport-Gated Fallback Polling (4 Problems)`

## Scoped Definition of Done Mapping

1. **Problem 1 - Recipient-Scoped Channel Resolution & Strict Isolation Across Live Dispatch, RLS Filter & Replay:**
   - `NOTIFICATION_TOPICS = frozenset({"notification.created", "notification.read", "notification.read_all"})` defined in `kanban/realtime/rls_filter.py` and shared across `kanban/realtime/hub.py` and `kanban/realtime/replay.py`.
   - `RealtimeHub.resolve_channel` (`kanban/realtime/hub.py`) resolves `"notifications:self"` and `"user:<self_uuid>"` to `("user:<principal_id>", principal_id, "user")`, while rejecting any other user's UUID or malformed channel with `None` (`NOT_FOUND` on WebSocket, silent omission on SSE).
   - `RealtimeHub.handle_unsubscribe` cleans up both `"notifications:self"` and `"user:<principal_id>"`.
   - `_resolve_candidate_connections` and `dispatch_envelope` (`kanban/realtime/hub.py`) route `NOTIFICATION_TOPICS` strictly via `get_user_connections(envelope.workspace_id, recipient_uuid)` matching ONLY `("notifications:self", f"user:{recipient_uuid}")` (never `workspace:*`, `project:*`, `issue:*`, or `doc:*`), while continuing to check `authorize_event_recipients` for post-commit `VIEW` revocation on `notification.created`.
   - `authorize_event_recipients` (`kanban/realtime/rls_filter.py`) intersects `candidate_principals` with `{recipient_uuid}` on all `NOTIFICATION_TOPICS` (including when `object_id=None, project_id=None` on `notification.read` / `notification.read_all`).
   - `OutboxReplayer` (`kanban/realtime/replay.py`) enforces identical recipient + workspace + `notifications:self`/`user:<id>` channel isolation on `Last-Event-ID` replay.
   - Proof: `docs/qa/KAN-310/unit-test-results.txt` (`kanban/tests/realtime/test_notification_realtime_isolation.py`, `6 passed`), `docs/qa/KAN-310/contract-sample.json`.

2. **Problem 2 - Multi-Tab Read Sync Outbox Events:**
   - `mark_notification_read` (`kanban/services/notifications.py`) emits 1 ID-only `OutboxEvent` row (`topic="notification.read"`, `project_id=None`, `object_id=None`, payload `{"topic": "notification.read", "recipient_principal_id": ..., "notification_id": ...}`) via `insert(OutboxEvent).inline()` without `RETURNING` strictly on `read_at is None` transitions (idempotent repeat calls emit `0` rows).
   - `mark_all_read` (`kanban/services/notifications.py`) emits 1 ID-only `OutboxEvent` row (`topic="notification.read_all"`, `project_id=None`, `object_id=None`, payload `{"topic": "notification.read_all", "recipient_principal_id": ..., "marked_count": marked}`) via `insert(OutboxEvent).inline()` without `RETURNING` strictly when `marked > 0`.
   - Proof: `docs/qa/KAN-310/unit-test-results.txt` (`kanban/tests/api/test_notifications.py`, `3 passed`, `kanban/services/notifications.py` at `99%` coverage).

3. **Problem 3 - Frontend Realtime Wiring, SSE Parity & Frame Hardening:**
   - `kanban/web/src/api/realtime.ts` adds `'notification.created'`, `'notification.read'`, and `'notification.read_all'` to `SSE_EVENT_NAMES`.
   - `sseUrl` forwards `last_event_id` when `this.lastEventId !== undefined`.
   - `handleFrame` parses incoming JSON via `safeJsonParse` (stripping `__proto__`, `constructor`, `prototype`) and drops `notification.*` frames with mismatched `recipient_principal_id` (`droppedEvents += 1`).
   - `bindQueryInvalidation` invalidates `['notifications']` on `notification.created` and optimistically patches `qk.notifications()` in-place on `notification.read` and `notification.read_all` (falling back to invalidation only when uncached).
   - Proof: `docs/qa/KAN-310/unit-test-results.txt` (`src/api/realtime.test.ts`, `48 passed`, `99.41%` statement / `96.18%` branch coverage).

4. **Problem 4 - Transport-Gated Fallback Polling, Recovery Resync & Accessible Bell UX:**
   - `kanban/web/src/features/notifications/NotificationsBell.tsx` subscribes to `'notifications:self'`, reads `useRealtimeLiveState()`, gates `refetchInterval: isFallbackPolling ? 30000 : false` (`isFallbackPolling = realtimeState === 'reconnecting' || realtimeState === 'closed'`, `refetchIntervalInBackground: false`, `refetchOnWindowFocus: false`), fires single-shot recovery resync on `'reconnecting' | 'closed' -> 'open' | 'sse-fallback'` (and not on `'connecting' -> 'open'`), aligns `unreadCount` with `isNotificationUnread`, exposes `data-realtime-state` and `data-polling-active` on `data-testid="notifications-bell"`, and renders coalesced `1000ms` polite `data-testid="notifications-live-announcer"`.
   - Proof: `docs/qa/KAN-310/unit-test-results.txt` (`src/features/notifications/NotificationsBell.test.tsx`, `14 passed`, `100%` statement / `95%` branch coverage).

5. **Coverage & Build Verification Summary:**
   - Python coverage (`docs/qa/KAN-310/unit-test-results.txt`):
     - `kanban/realtime/hub.py`: `95%`
     - `kanban/realtime/replay.py`: `99%`
     - `kanban/realtime/rls_filter.py`: `97%`
     - `kanban/services/notifications.py`: `99%`
     - Total Python coverage across touched files: `97%` (`65 passed, 0 failed`).
   - Frontend Vitest coverage (`docs/qa/KAN-310/unit-test-results.txt`):
     - `kanban/web/src/api/realtime.ts`: `99.41%` statements, `96.18%` branches, `100%` functions, `99.41%` lines (`48 passed`).
     - `kanban/web/src/features/notifications/NotificationsBell.tsx`: `100%` statements, `95.00%` branches, `100%` functions, `100%` lines (`14 passed`).
   - Build / Lint / Type / Dash checks (`docs/qa/KAN-310/build-check.txt`):
     - `make check` (`ruff check`, `ruff format --check`, `mypy`, `lint-imports`, `check_no_dashes --all`, `check-migrations --static-only`): `0` errors.
     - `pnpm --dir kanban/web typecheck`, `pnpm --dir kanban/web lint`, `pnpm --dir kanban/web build`: `0` errors, `0` warnings.
