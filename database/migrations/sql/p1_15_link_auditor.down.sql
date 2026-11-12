-- Migration: p1_15_link_auditor (down)
-- Drops incremental triggers, link audit functions, table, and enum

DROP TRIGGER IF EXISTS z_role_bindings_link_audit_trg ON role_bindings;
DROP FUNCTION IF EXISTS role_bindings_link_audit_trg_fn();

DROP TRIGGER IF EXISTS z_resource_acl_link_audit_trg ON resource_acl_entries;
DROP FUNCTION IF EXISTS resource_acl_link_audit_trg_fn();

DROP TRIGGER IF EXISTS objects_link_audit_trg ON objects;
DROP FUNCTION IF EXISTS objects_link_audit_trg_fn();

DROP FUNCTION IF EXISTS audit_object_links_for_object(uuid);
DROP FUNCTION IF EXISTS audit_object_links(uuid, timestamptz);
DROP FUNCTION IF EXISTS audit_single_object_link(uuid, timestamptz);

DROP TRIGGER IF EXISTS invalid_link_audits_guard_bud_trg ON invalid_object_link_audits;
DROP FUNCTION IF EXISTS invalid_link_audits_guard_bud();

DROP TABLE IF EXISTS invalid_object_link_audits;
DROP TYPE IF EXISTS invalid_link_reason;
