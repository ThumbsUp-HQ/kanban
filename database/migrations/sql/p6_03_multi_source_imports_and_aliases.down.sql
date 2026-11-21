-- Copyright 2026 Kanban Platform Contributors
-- Apache-2.0 License. See LICENSE for details.

DROP TABLE IF EXISTS issue_key_aliases;

ALTER TABLE import_entity_mappings
    DROP CONSTRAINT IF EXISTS import_entity_mappings_source_system_check;

ALTER TABLE import_entity_mappings
    ADD CONSTRAINT import_entity_mappings_source_system_check
    CHECK (source_system = 'plane');
