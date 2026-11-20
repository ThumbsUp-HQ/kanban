-- Copyright 2026 Kanban Platform Contributors
-- Apache-2.0 License. See LICENSE for details.

-- Revert oidc_auth_requests.link_intent_id foreign key constraint to reference principals
ALTER TABLE oidc_auth_requests
    DROP CONSTRAINT IF EXISTS oidc_auth_requests_link_intent_id_fkey;

ALTER TABLE oidc_auth_requests
    ADD CONSTRAINT oidc_auth_requests_link_intent_id_fkey
    FOREIGN KEY (link_intent_id)
    REFERENCES principals(id)
    ON DELETE SET NULL;
