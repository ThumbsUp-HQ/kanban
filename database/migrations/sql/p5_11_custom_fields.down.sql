-- Revert KB-P5-11: Custom field definitions & values

REVOKE ALL ON custom_field_definitions, custom_field_values FROM kanban_app, app_rls_reader;
REVOKE EXECUTE ON FUNCTION app_caller_access_hash() FROM kanban_app, app_rls_reader, kanban_migrator;

DROP TABLE IF EXISTS custom_field_values CASCADE;
DROP TABLE IF EXISTS custom_field_definitions CASCADE;
DROP FUNCTION IF EXISTS app_caller_access_hash();
