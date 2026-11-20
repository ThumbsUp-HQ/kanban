-- Copyright 2026 Kanban Platform Contributors
-- Apache-2.0 License. See LICENSE for details.

DROP FUNCTION IF EXISTS get_outbox_missed_count(UUID, BIGINT, INT) CASCADE;
DROP FUNCTION IF EXISTS get_outbox_retention_stats(UUID, INT) CASCADE;
DROP FUNCTION IF EXISTS fetch_replay_outbox_events(UUID, BIGINT, INT, INT) CASCADE;
