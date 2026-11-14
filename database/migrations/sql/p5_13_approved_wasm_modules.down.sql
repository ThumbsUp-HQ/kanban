-- Phase 5 / Sandbox: approved_wasm_modules downgrade (KB-P5-13, S13.3)

DROP POLICY IF EXISTS approved_wasm_modules_delete_rls ON approved_wasm_modules;
DROP POLICY IF EXISTS approved_wasm_modules_update_rls ON approved_wasm_modules;
DROP POLICY IF EXISTS approved_wasm_modules_insert_rls ON approved_wasm_modules;
DROP POLICY IF EXISTS approved_wasm_modules_select_rls ON approved_wasm_modules;

ALTER TABLE IF EXISTS approved_wasm_modules NO FORCE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS approved_wasm_modules DISABLE ROW LEVEL SECURITY;

DROP TABLE IF EXISTS approved_wasm_modules CASCADE;
