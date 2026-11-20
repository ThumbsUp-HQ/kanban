-- Copyright 2026 Kanban Platform Contributors
-- Apache-2.0 License. See LICENSE for details.

-- Fix oidc_auth_requests.link_intent_id foreign key constraint to reference identity_link_intents
ALTER TABLE oidc_auth_requests
    DROP CONSTRAINT IF EXISTS oidc_auth_requests_link_intent_id_fkey;

ALTER TABLE oidc_auth_requests
    ADD CONSTRAINT oidc_auth_requests_link_intent_id_fkey
    FOREIGN KEY (link_intent_id)
    REFERENCES identity_link_intents(id)
    ON DELETE SET NULL;
