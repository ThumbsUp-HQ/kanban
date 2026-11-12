-- Copyright 2026 Kanban Platform Contributors
-- Apache-2.0 License. See LICENSE for details.
-- Phase 2 / Auth: ldap_group_mappings table with FORCE RLS revert (KB-P2-07)

DROP TRIGGER IF EXISTS ldap_group_mappings_set_updated_at ON ldap_group_mappings;
DROP TABLE IF EXISTS ldap_group_mappings CASCADE;
