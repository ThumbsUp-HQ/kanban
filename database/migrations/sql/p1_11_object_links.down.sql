DROP TRIGGER IF EXISTS object_links_guard_bu_trg ON object_links;
DROP FUNCTION IF EXISTS object_links_guard_bu();
DROP TRIGGER IF EXISTS object_links_validate_bi_trg ON object_links;
DROP FUNCTION IF EXISTS object_links_validate_bi();
DROP TABLE IF EXISTS object_links;
DROP TABLE IF EXISTS link_type_matrix;
DROP TYPE IF EXISTS link_kind;
