-- Revert Phase 1 / Database: Transactional outbox_events, OutboxRelay and RealtimeBroker (KB-P1-18)

REVOKE EXECUTE ON FUNCTION mark_outbox_failed(uuid, text, integer, timestamptz) FROM kanban_app;
REVOKE EXECUTE ON FUNCTION mark_outbox_published(uuid[], timestamptz) FROM kanban_app;
REVOKE EXECUTE ON FUNCTION claim_outbox_batch(integer, timestamptz) FROM kanban_app;

DROP FUNCTION IF EXISTS mark_outbox_failed(uuid, text, integer, timestamptz);
DROP FUNCTION IF EXISTS mark_outbox_published(uuid[], timestamptz);
DROP FUNCTION IF EXISTS claim_outbox_batch(integer, timestamptz);

DROP TRIGGER IF EXISTS outbox_events_wakeup_ai ON outbox_events;
DROP FUNCTION IF EXISTS outbox_events_wakeup_fn();

DROP POLICY IF EXISTS outbox_events_select_rls ON outbox_events;
DROP POLICY IF EXISTS outbox_events_insert_rls ON outbox_events;

DROP TABLE IF EXISTS outbox_events CASCADE;
