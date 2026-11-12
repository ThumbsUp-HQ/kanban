DROP TRIGGER IF EXISTS principal_group_edges_closure_aiud_trg ON principal_group_edges;
DROP FUNCTION IF EXISTS principal_group_edges_closure_aiud();
DROP TRIGGER IF EXISTS principal_group_edges_guard_biu_trg ON principal_group_edges;
DROP FUNCTION IF EXISTS principal_group_edges_guard_biu();
DROP FUNCTION IF EXISTS rebuild_group_closure(uuid);

DROP TRIGGER IF EXISTS groups_workspace_match_biu_trg ON groups;
DROP FUNCTION IF EXISTS groups_workspace_match_biu();
DROP TRIGGER IF EXISTS users_workspace_match_biu_trg ON users;
DROP FUNCTION IF EXISTS users_workspace_match_biu();

DROP TABLE IF EXISTS principal_group_closure;
DROP TABLE IF EXISTS principal_group_edges;
DROP TABLE IF EXISTS groups;
DROP TABLE IF EXISTS users;
DROP TABLE IF EXISTS principals;
