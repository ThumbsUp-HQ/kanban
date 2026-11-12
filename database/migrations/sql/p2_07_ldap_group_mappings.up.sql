-- Copyright 2026 Kanban Platform Contributors
-- Apache-2.0 License. See LICENSE for details.
-- Phase 2 / Auth: ldap_group_mappings table with FORCE RLS (KB-P2-07)

CREATE TABLE ldap_group_mappings (
    id UUID PRIMARY KEY DEFAULT uuidv7(),
    card_id UUID NOT NULL REFERENCES auth_provider_cards(id) ON DELETE CASCADE,
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    ldap_dn TEXT NOT NULL CHECK (char_length(btrim(ldap_dn)) BETWEEN 1 AND 1024),
    group_name TEXT NOT NULL CHECK (char_length(btrim(group_name)) BETWEEN 1 AND 200),
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT ldap_group_mappings_card_dn_uq UNIQUE (card_id, ldap_dn)
);

CREATE INDEX idx_ldap_group_mappings_card ON ldap_group_mappings (card_id);
CREATE INDEX idx_ldap_group_mappings_ws ON ldap_group_mappings (workspace_id);

ALTER TABLE ldap_group_mappings ENABLE ROW LEVEL SECURITY;
ALTER TABLE ldap_group_mappings FORCE ROW LEVEL SECURITY;

CREATE POLICY ldap_group_mappings_select_rls ON ldap_group_mappings
    FOR SELECT USING (
        workspace_id = app_current_workspace_id()
        AND cardinality(app_effective_principal_set()) > 0
    );

CREATE POLICY ldap_group_mappings_insert_rls ON ldap_group_mappings
    FOR INSERT WITH CHECK (
        workspace_id = app_current_workspace_id()
        AND app_principal_has_role(NULL, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN'])
    );

CREATE POLICY ldap_group_mappings_update_rls ON ldap_group_mappings
    FOR UPDATE USING (
        workspace_id = app_current_workspace_id()
        AND app_principal_has_role(NULL, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN'])
    ) WITH CHECK (
        workspace_id = app_current_workspace_id()
        AND app_principal_has_role(NULL, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN'])
    );

CREATE POLICY ldap_group_mappings_delete_rls ON ldap_group_mappings
    FOR DELETE USING (
        workspace_id = app_current_workspace_id()
        AND app_principal_has_role(NULL, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN'])
    );

CREATE TRIGGER ldap_group_mappings_set_updated_at
    BEFORE UPDATE ON ldap_group_mappings
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE ldap_group_mappings TO kanban_app;
GRANT SELECT ON TABLE ldap_group_mappings TO app_rls_reader;
