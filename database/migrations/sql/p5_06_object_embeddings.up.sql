-- Migration: p5_06_object_embeddings (up)
-- pgvector extension, object_embeddings table, HNSW cosine index, FORCE RLS, indexer helper function

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE object_embeddings (
    object_id       UUID NOT NULL,
    object_type     object_kind NOT NULL,
    chunk_index     SMALLINT NOT NULL CHECK (chunk_index BETWEEN 0 AND 63),
    workspace_id    UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    project_id      UUID,
    content_sha256  BYTEA NOT NULL CHECK (octet_length(content_sha256) = 32),
    model_id        TEXT NOT NULL,
    embedding       vector(384) NOT NULL,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (object_id, chunk_index),
    FOREIGN KEY (object_id, object_type) REFERENCES objects(id, object_type) ON DELETE CASCADE
);

CREATE INDEX object_embeddings_hnsw ON object_embeddings
    USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64);

CREATE INDEX object_embeddings_scope ON object_embeddings (workspace_id, project_id);

CREATE TRIGGER object_embeddings_set_updated_at
    BEFORE UPDATE ON object_embeddings
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

ALTER TABLE object_embeddings ENABLE ROW LEVEL SECURITY;
ALTER TABLE object_embeddings FORCE ROW LEVEL SECURITY;

-- Helper function to identify the svc-embedding-indexer principal
CREATE OR REPLACE FUNCTION app_embedding_indexer_principal()
RETURNS uuid
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
    v_id uuid;
BEGIN
    SELECT id INTO v_id
    FROM principals
    WHERE principal_type = 'SERVICE_PRINCIPAL'
      AND display_name = 'svc-embedding-indexer'
      AND workspace_id = app_current_workspace_id()
    ORDER BY created_at ASC
    LIMIT 1;

    IF v_id IS NOT NULL THEN
        RETURN v_id;
    END IF;

    RETURN NULLIF(current_setting('app.embedding_indexer_principal_id', true), '')::uuid;
END;
$$;

GRANT EXECUTE ON FUNCTION app_embedding_indexer_principal() TO kanban_app, app_rls_reader, kanban_migrator;

-- SELECT policy: identical predicate to objects_select_rls (S3.3)
CREATE POLICY object_embeddings_select_rls ON object_embeddings
    FOR SELECT USING (
        workspace_id = app_current_workspace_id()
        AND EXISTS (
            SELECT 1 FROM effective_resource_access era
            WHERE era.object_id = object_embeddings.object_id
              AND era.principal_id = ANY (app_effective_principal_set())
              AND (era.allow_mask & 1) = 1
              AND (era.deny_mask  & 1) = 0
        )
    );

-- INSERT policy: workspace match and caller is svc-embedding-indexer
CREATE POLICY object_embeddings_insert_rls ON object_embeddings
    FOR INSERT WITH CHECK (
        workspace_id = app_current_workspace_id()
        AND app_current_principal_id() IS NOT NULL
        AND app_current_principal_id() = app_embedding_indexer_principal()
    );

-- UPDATE policy: workspace match and caller is svc-embedding-indexer
CREATE POLICY object_embeddings_update_rls ON object_embeddings
    FOR UPDATE USING (
        workspace_id = app_current_workspace_id()
        AND app_current_principal_id() IS NOT NULL
        AND app_current_principal_id() = app_embedding_indexer_principal()
    ) WITH CHECK (
        workspace_id = app_current_workspace_id()
        AND app_current_principal_id() IS NOT NULL
        AND app_current_principal_id() = app_embedding_indexer_principal()
    );

-- DELETE policy: workspace match and caller is svc-embedding-indexer
CREATE POLICY object_embeddings_delete_rls ON object_embeddings
    FOR DELETE USING (
        workspace_id = app_current_workspace_id()
        AND app_current_principal_id() IS NOT NULL
        AND app_current_principal_id() = app_embedding_indexer_principal()
    );

GRANT SELECT ON object_embeddings TO app_rls_reader;
REVOKE INSERT, UPDATE, DELETE ON object_embeddings FROM app_rls_reader;
GRANT SELECT, INSERT, UPDATE, DELETE ON object_embeddings TO kanban_app;
