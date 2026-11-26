#!/usr/bin/env python3
# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.

import asyncio
import uuid
import asyncpg

PG_DSN = "postgresql://kanban_migrator@/kanban_slice5_workout?host=/tmp/kb-pgsock"

async def setup():
    conn = await asyncpg.connect(PG_DSN)
    try:
        await conn.execute("TRUNCATE TABLE workspaces CASCADE;")
        
        # 1. Create Workspace
        ws_id = await conn.fetchval(
            "INSERT INTO workspaces (slug, name) VALUES ('default', 'Governance Workspace') RETURNING id"
        )
        print("Workspace created:", ws_id)
        
        # 2. Create Users: Admin1, Admin2, Member1
        admin1_id = await conn.fetchval(
            "INSERT INTO principals (workspace_id, principal_type, status, display_name) "
            "VALUES ($1, 'USER', 'ACTIVE', 'Admin One') RETURNING id",
            ws_id
        )
        await conn.execute(
            "SELECT register_object('user'::object_kind, $1, NULL, 'admin1', 'Admin One', $2, $2)",
            ws_id, admin1_id
        )
        await conn.execute(
            "INSERT INTO users (id, object_type, principal_type, workspace_id, email) "
            "VALUES ($1, 'user', 'USER', $2, 'admin1@local.kanban')",
            admin1_id, ws_id
        )

        admin2_id = await conn.fetchval(
            "INSERT INTO principals (workspace_id, principal_type, status, display_name) "
            "VALUES ($1, 'USER', 'ACTIVE', 'Admin Two') RETURNING id",
            ws_id
        )
        await conn.execute(
            "SELECT register_object('user'::object_kind, $1, NULL, 'admin2', 'Admin Two', $2, $2)",
            ws_id, admin2_id
        )
        await conn.execute(
            "INSERT INTO users (id, object_type, principal_type, workspace_id, email) "
            "VALUES ($1, 'user', 'USER', $2, 'admin2@local.kanban')",
            admin2_id, ws_id
        )

        member1_id = await conn.fetchval(
            "INSERT INTO principals (workspace_id, principal_type, status, display_name) "
            "VALUES ($1, 'USER', 'ACTIVE', 'Member One') RETURNING id",
            ws_id
        )
        await conn.execute(
            "SELECT register_object('user'::object_kind, $1, NULL, 'member1', 'Member One', $2, $2)",
            ws_id, member1_id
        )
        await conn.execute(
            "INSERT INTO users (id, object_type, principal_type, workspace_id, email) "
            "VALUES ($1, 'user', 'USER', $2, 'member1@local.kanban')",
            member1_id, ws_id
        )

        # 3. Create Projects: KAN and DISP
        kan_proj_id = await conn.fetchval(
            "SELECT register_object('project'::object_kind, $1, NULL, 'KAN', 'Core Platform', $2)",
            ws_id, admin1_id
        )
        await conn.execute(
            "INSERT INTO projects (id, object_type, workspace_id, identifier, name, description_markdown, modules_enabled) "
            "VALUES ($1, 'project', $2, 'KAN', 'Core Platform', 'Core system project', true)",
            kan_proj_id, ws_id
        )

        disp_proj_id = await conn.fetchval(
            "SELECT register_object('project'::object_kind, $1, NULL, 'DISP', 'Disposable Project', $2)",
            ws_id, admin1_id
        )
        await conn.execute(
            "INSERT INTO projects (id, object_type, workspace_id, identifier, name, description_markdown, modules_enabled) "
            "VALUES ($1, 'project', $2, 'DISP', 'Disposable Project', 'Target for 2-stage purge testing', false)",
            disp_proj_id, ws_id
        )

        # 4. Role Bindings
        # Admin1: SERVER_ADMIN, WORKSPACE_ADMIN, PROJECT_ADMIN on KAN & DISP
        for role, scope, p_id in [
            ("SERVER_ADMIN", "server", None),
            ("WORKSPACE_ADMIN", "workspace", None),
            ("PROJECT_ADMIN", "project", kan_proj_id),
            ("PROJECT_ADMIN", "project", disp_proj_id),
        ]:
            await conn.execute(
                "INSERT INTO role_bindings (workspace_id, principal_id, role, scope_type, project_id) "
                "VALUES ($1, $2, CAST($3 AS rbac_role), $4, $5)",
                ws_id, admin1_id, role, scope, p_id,
            )

        # Admin2: SERVER_ADMIN, WORKSPACE_ADMIN, PROJECT_ADMIN on KAN
        for role, scope, p_id in [
            ("SERVER_ADMIN", "server", None),
            ("WORKSPACE_ADMIN", "workspace", None),
            ("PROJECT_ADMIN", "project", kan_proj_id),
        ]:
            await conn.execute(
                "INSERT INTO role_bindings (workspace_id, principal_id, role, scope_type, project_id) "
                "VALUES ($1, $2, CAST($3 AS rbac_role), $4, $5)",
                ws_id, admin2_id, role, scope, p_id,
            )

        # Member1: WORKSPACE_MEMBER, MEMBER on KAN
        for role, scope, p_id in [
            ("WORKSPACE_MEMBER", "workspace", None),
            ("MEMBER", "project", kan_proj_id),
        ]:
            await conn.execute(
                "INSERT INTO role_bindings (workspace_id, principal_id, role, scope_type, project_id) "
                "VALUES ($1, $2, CAST($3 AS rbac_role), $4, $5)",
                ws_id, member1_id, role, scope, p_id,
            )

        # 5. Create Groups for Nested Hierarchy Test
        parent_group_id = await conn.fetchval(
            "INSERT INTO principals (workspace_id, principal_type, status, display_name) "
            "VALUES ($1, 'GROUP', 'ACTIVE', 'Engineering') RETURNING id",
            ws_id
        )
        await conn.execute(
            "INSERT INTO groups (id, principal_type, workspace_id, name) VALUES ($1, 'GROUP', $2, 'Engineering')",
            parent_group_id, ws_id
        )

        child_group_id = await conn.fetchval(
            "INSERT INTO principals (workspace_id, principal_type, status, display_name) "
            "VALUES ($1, 'GROUP', 'ACTIVE', 'Backend Core') RETURNING id",
            ws_id
        )
        await conn.execute(
            "INSERT INTO groups (id, principal_type, workspace_id, name) VALUES ($1, 'GROUP', $2, 'Backend Core')",
            child_group_id, ws_id
        )

        # Member1 -> Child Group
        await conn.execute(
            "INSERT INTO principal_group_edges (workspace_id, group_id, member_id) VALUES ($1, $2, $3)",
            ws_id, child_group_id, member1_id
        )
        # Child Group -> Parent Group
        await conn.execute(
            "INSERT INTO principal_group_edges (workspace_id, group_id, member_id) VALUES ($1, $2, $3)",
            ws_id, parent_group_id, child_group_id
        )

        # 6. Configure WIP limits on In Progress for KAN
        await conn.execute(
            "UPDATE workflow_states SET wip_soft_limit = 2, wip_hard_limit = 3 "
            "WHERE project_id = $1 AND name = 'In Progress'",
            kan_proj_id
        )

        kan_todo_id = await conn.fetchval(
            "SELECT id FROM workflow_states WHERE project_id = $1 AND name = 'Todo'",
            kan_proj_id
        )
        disp_todo_id = await conn.fetchval(
            "SELECT id FROM workflow_states WHERE project_id = $1 AND name = 'Todo'",
            disp_proj_id
        )
        kan_prio_id = await conn.fetchval(
            "SELECT id FROM project_priorities WHERE project_id = $1 AND slug = 'medium'",
            kan_proj_id
        )
        disp_prio_id = await conn.fetchval(
            "SELECT id FROM project_priorities WHERE project_id = $1 AND slug = 'medium'",
            disp_proj_id
        )

        # 7. Seed items in DISP for Blast Radius test
        for i in range(1, 4):
            seq_val = await conn.fetchval("SELECT allocate_issue_sequence($1)", disp_proj_id)
            iss_id = uuid.uuid4()
            await conn.execute(
                "SELECT register_object('issue'::object_kind, $1, $2, $3, $4, $5, $6)",
                ws_id, disp_proj_id, f"DISP-{seq_val}", f"Disposable Item {seq_val}", admin1_id, iss_id
            )
            await conn.execute(
                "INSERT INTO issues (id, object_type, workspace_id, project_id, sequence_id, summary, description_markdown, state_id, priority_id, created_by_id, original_created_by_id, board_rank) "
                "VALUES ($1, 'issue', $2, $3, $4, $5, 'Testing blast radius counters', $6, $7, $8, $8, '0|hzzzzz:')",
                iss_id, ws_id, disp_proj_id, seq_val, f"Disposable Item {seq_val}", disp_todo_id, disp_prio_id, admin1_id
            )

        # 8. Seed items in KAN project
        for i in range(1, 4):
            seq_val = await conn.fetchval("SELECT allocate_issue_sequence($1)", kan_proj_id)
            iss_id = uuid.uuid4()
            await conn.execute(
                "SELECT register_object('issue'::object_kind, $1, $2, $3, $4, $5, $6)",
                ws_id, kan_proj_id, f"KAN-{seq_val}", f"Core Governance Task {seq_val}", admin1_id, iss_id
            )
            await conn.execute(
                "INSERT INTO issues (id, object_type, workspace_id, project_id, sequence_id, summary, description_markdown, state_id, priority_id, created_by_id, original_created_by_id, board_rank) "
                "VALUES ($1, 'issue', $2, $3, $4, $5, 'Active ticket for live workflow workout', $6, $7, $8, $8, '0|hzzzzz:')",
                iss_id, ws_id, kan_proj_id, seq_val, f"Core Governance Task {seq_val}", kan_todo_id, kan_prio_id, admin1_id
            )

        # 9. Rebuild Effective Access
        await conn.execute("SELECT rebuild_effective_access_for_workspace($1)", ws_id)

        print("Seeding complete!")
        print(f"ws_id={ws_id}")
        print(f"admin1_id={admin1_id}")
        print(f"admin2_id={admin2_id}")
        print(f"kan_proj_id={kan_proj_id}")
        print(f"disp_proj_id={disp_proj_id}")
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(setup())
