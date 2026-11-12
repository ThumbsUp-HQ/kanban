# Reality-Checker Verification Packet: KANBA-56 (KB-P1-18)

## Ticket Metadata
- Ticket ID: `KANBA-56`
- Spec Key: `KB-P1-18`
- Title: `[Phase 1 / Database] Transactional outbox_events, OutboxRelay (SKIP LOCKED) & RealtimeBroker (PG LISTEN/NOTIFY + Valkey)`
- Epic: `KB-E1` (Phase 1 Database Architecture)
- Spec Sections: `2.2` (Standalone PG LISTEN/NOTIFY RealtimeBroker, Zero Valkey Container), `2.4` (outbox-relay: LISTEN outbox_wakeup + FOR UPDATE SKIP LOCKED -> Valkey 8 Streams & PubSub), Requirement `#3`
- Dependencies: `KB-P1-17` (SQLAlchemy 2.0 ORM Models)
- Gate: `reality-checker` (Passive Forensic Mode)

---

## User Story
As a distributed systems architect, I need a transactional `outbox_events` table with a `pg_notify('outbox_wakeup')` trigger, a `FOR UPDATE SKIP LOCKED` relay worker with dead-letter protection, and a `RealtimeBroker` protocol implemented by both `PgNotifyBroker` (zero-Valkey standalone) and `ValkeyBroker` (multi-replica production) so that every committed domain mutation fans out reliably without dual-write race conditions or requiring Valkey in `docker run` mode.

---

## Scoped Definition of Done Checklist
- [x] **File Existence & Implementation:** `database/migrations/versions/p1_18_outbox.py`, `database/migrations/sql/p1_18_outbox.up.sql`, `database/migrations/sql/p1_18_outbox.down.sql`, `database/models/outbox.py`, and `database/outbox/{__init__,broker,pg_broker,valkey_broker,relay}.py` exist and implement `outbox_events` with `ENABLE & FORCE ROW LEVEL SECURITY`, `outbox_events_wakeup_ai` trigger, `claim_outbox_batch` (`FOR UPDATE SKIP LOCKED`), `OutboxEnvelope`, `enqueue_outbox_event`, `RealtimeBroker`, `PgNotifyBroker`, `ValkeyBroker`, `build_realtime_broker`, and `OutboxRelay`.
- [x] **Single Alembic Head:** `uv run alembic -c database/alembic.ini heads` prints exactly one head: `p1_18_outbox (head)`.
- [x] **1:1 ORM & Schema Parity:** `OutboxEvent` registered in `database/models/__init__.py`. Both `test_p1_14_rls_catalog.py` and `test_p1_17_models.py` (`test_orm_schema_parity` across all 34 tables) pass 100%.
- [x] **Unit & Concurrency Tests Passing:** `uv run pytest database/tests/test_p1_18_outbox_broker.py database/tests/test_p1_18_relay_concurrency.py database/tests/test_p1_14_rls_catalog.py database/tests/migrations/test_p1_18_migration.py -q --cov=database.models.outbox --cov=database.outbox --cov-branch --cov-report=term-missing --cov-fail-under=95` exits `0` with 19 passed in 2.70s and 96.89% branch & line coverage.
- [x] **Build, Type, & Import Lint Clean:** `uv run ruff check database && uv run ruff format --check database && uv run mypy --strict database && uv run lint-imports` exits `0` with 0 warnings/errors.
- [x] **Supply Chain & Dash Verification:** 0 license violations across 94 Python and 1 Node packages via `scripts.license_gate`. 0 forbidden Unicode dashes via `scripts.check_no_dashes --all`.
- [x] **Docker Compose Command:** `outbox-relay` service in `docker-compose.yml` set to `["python", "-m", "database.outbox.relay"]`. `database/GEMINI.md` manifest updated.
- [x] **Forensic Proof Packet Complete:** All required proof files exist under `docs/qa/KANBA-56/`.

---

## Technical Architecture & Invariant Guarantees

1. **Transactional Atomicity (Dual-Write Prevention):**
   - Domain entities and `outbox_events` records are written in the same database transaction via `enqueue_outbox_event`.
   - If the transaction rolls back, 0 outbox rows are committed and 0 broker messages are published.
   - When committed, statement-level trigger `outbox_events_wakeup_ai` fires `pg_notify('outbox_wakeup', '')` exactly once per transaction to immediately wake `OutboxRelay`.

2. **SKIP LOCKED Concurrent Delivery & Visibility Leases:**
   - Multiple `OutboxRelay` worker instances claim work via `claim_outbox_batch(p_batch_size, p_now)`.
   - The query uses `FOR UPDATE SKIP LOCKED` so concurrent relay instances never block each other or duplicate processing during active leases.
   - Claimed rows have `next_attempt_at = p_now + interval '30 seconds'`, providing an automatic crash-recovery visibility lease.

3. **Poison-Pill & Dead-Letter Protection:**
   - Broker publication errors are isolated per event. One failing event in a batch never blocks healthy events from being marked `published_at`.
   - Failed events receive exponential backoff via `mark_outbox_failed`: `next_attempt_at = p_now + interval (least(300, 2^attempts) seconds)`.
   - After 5 consecutive failures, the event transitions to `dead_lettered_at = p_now` and is excluded from subsequent batch claims.

4. **Wire Payload Ceiling & Standalone Zero-Valkey Mode:**
   - `OutboxEnvelope.to_wire_json()` rejects envelopes exceeding 7900 bytes with `OutboxPayloadTooLargeError`, guaranteeing PostgreSQL NOTIFY's 8000-byte hard ceiling is never violated.
   - `build_realtime_broker("standalone")` instantiates `PgNotifyBroker`, enabling standalone `docker run` deployment mode with zero Valkey container.
   - `build_realtime_broker("production")` instantiates `ValkeyBroker` with dual stream (`kb:outbox:stream`) and pubsub (`kb:rt:<topic>`) channels.

---

## Forensic Artifacts in `docs/qa/KANBA-56/`
1. `git-diff.patch`: Unified diff of all changes against base commit.
2. `unit-test-results.txt`: Pytest execution output (19 passed in 2.70s, 96.89% branch & line coverage, EXIT_CODE=0).
3. `build-check.txt`: Static analysis output (ruff check, ruff format --check, mypy --strict database, lint-imports, EXIT_CODE=0).
4. `alembic-heads.txt`: Output of `uv run alembic heads` showing single head `p1_18_outbox (head)`.
5. `schema-dump.sql`: Complete `pg_dump` of `outbox_events` and function definitions `claim_outbox_batch` and `outbox_events_wakeup_fn`.
6. `relay-trace.txt`: End-to-end delivery trace showing 3.78ms delivery latency (budget: < 200ms) and verified 5-attempt dead-letter transition.
7. `message-to-reality-checker.md`: This forensic sign-off document.
