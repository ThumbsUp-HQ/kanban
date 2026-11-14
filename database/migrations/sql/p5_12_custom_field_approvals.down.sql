-- Copyright 2026 Kanban Platform Contributors
-- Apache-2.0 License. See LICENSE for details.
-- Migration p5_12_custom_field_approvals.down.sql

DROP TRIGGER IF EXISTS custom_field_manifest_tamper_revoke ON custom_field_definitions;
DROP FUNCTION IF EXISTS custom_field_manifest_tamper_revoke_tf();
DROP TABLE IF EXISTS custom_field_approvals CASCADE;
