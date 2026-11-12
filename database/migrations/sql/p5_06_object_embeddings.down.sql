-- Migration: p5_06_object_embeddings (down)

DROP POLICY IF EXISTS object_embeddings_delete_rls ON object_embeddings;
DROP POLICY IF EXISTS object_embeddings_update_rls ON object_embeddings;
DROP POLICY IF EXISTS object_embeddings_insert_rls ON object_embeddings;
DROP POLICY IF EXISTS object_embeddings_select_rls ON object_embeddings;

DROP TRIGGER IF EXISTS object_embeddings_set_updated_at ON object_embeddings;

DROP TABLE IF EXISTS object_embeddings CASCADE;

DROP FUNCTION IF EXISTS app_embedding_indexer_principal();
