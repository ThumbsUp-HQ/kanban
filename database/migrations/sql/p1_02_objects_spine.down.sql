DROP FUNCTION IF EXISTS register_object(object_kind, uuid, uuid, text, text, uuid, uuid);
DROP TRIGGER IF EXISTS objects_guard_bu_trg ON objects;
DROP FUNCTION IF EXISTS objects_guard_bu();
DROP TRIGGER IF EXISTS objects_set_updated_at ON objects;
DROP TRIGGER IF EXISTS workspaces_set_updated_at ON workspaces;
DROP TABLE IF EXISTS objects CASCADE;
DROP TYPE IF EXISTS object_kind CASCADE;
DROP TABLE IF EXISTS workspaces CASCADE;
