-- Migration: p1_13_access_control (down)
-- Revert role bindings, resource ACL entries, and effective_resource_access.

DROP TRIGGER IF EXISTS views_era_refresh_trg ON views;
DROP FUNCTION IF EXISTS views_era_refresh_au();
DROP TRIGGER IF EXISTS objects_era_refresh_trg ON objects;
DROP FUNCTION IF EXISTS objects_era_refresh_aiud();
DROP TRIGGER IF EXISTS principals_era_refresh_trg ON principals;
DROP FUNCTION IF EXISTS principals_era_refresh_au();
DROP TRIGGER IF EXISTS principal_group_edges_era_refresh_trg ON principal_group_edges;
DROP FUNCTION IF EXISTS principal_group_edges_era_refresh_aiud();
DROP TRIGGER IF EXISTS resource_acl_era_refresh_trg ON resource_acl_entries;
DROP FUNCTION IF EXISTS resource_acl_era_refresh_aiud();
DROP TRIGGER IF EXISTS resource_acl_guard_biu_trg ON resource_acl_entries;
DROP FUNCTION IF EXISTS resource_acl_guard_biu();
DROP TRIGGER IF EXISTS role_bindings_era_refresh_trg ON role_bindings;
DROP FUNCTION IF EXISTS role_bindings_era_refresh_aiud();
DROP TRIGGER IF EXISTS role_bindings_guard_biu_trg ON role_bindings;
DROP FUNCTION IF EXISTS role_bindings_guard_biu();

DROP FUNCTION IF EXISTS app_principal_has_role(uuid, text[]);
DROP FUNCTION IF EXISTS app_effective_principal_set();
DROP FUNCTION IF EXISTS rebuild_effective_access_for_object(uuid);
DROP FUNCTION IF EXISTS rebuild_effective_access_for_workspace(uuid);

DROP TABLE IF EXISTS effective_resource_access CASCADE;
DROP TABLE IF EXISTS resource_acl_entries CASCADE;
DROP TABLE IF EXISTS role_bindings CASCADE;

DROP FUNCTION IF EXISTS rbac_role_mask(rbac_role);
DROP TYPE IF EXISTS rbac_role;
DROP FUNCTION IF EXISTS capability_bit(text);
