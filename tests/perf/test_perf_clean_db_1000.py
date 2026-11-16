# Copyright 2026 Kanban Platform Contributors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""1,000 Clean-DB SAVEPOINT isolation & throughput benchmark (KB-P6-04, S15.1).

Defines 1,000 parametrized test cases all inserting identical `canonical_key = 'PERF-1'`,
verifying that SAVEPOINT rollback isolation guarantees 100% clean isolation with zero
unique-constraint collisions, executing in < 10.0s wall-clock under pytest-xdist.
"""

# ruff: noqa: PT022
from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import (
    Issue,
    ObjectKind,
    ObjectRecord,
    Project,
    ProjectPriority,
    RbacRole,
    RoleBinding,
    User,
    WorkflowState,
    Workspace,
)
from database.session import RLSContext, bind_rls_context

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from sqlalchemy.ext.asyncio import AsyncEngine


@pytest.fixture(scope="module")
async def perf_spine(
    pg_worker_db: AsyncEngine,
) -> AsyncGenerator[tuple[uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID], None]:
    """Bootstrap a dedicated workspace, user, and project spine for the 1,000-run suite."""
    ws_id = uuid.uuid4()
    u_id = uuid.uuid4()
    proj_id = uuid.uuid4()

    async with AsyncSession(pg_worker_db) as init_session:
        # 1. Workspace
        ws = Workspace(id=ws_id, slug=f"ws-perf-{ws_id.hex[:8]}", name="Perf Workspace")
        init_session.add(ws)
        await init_session.flush()

        # 2. Principal + User ObjectRecord + User
        await init_session.execute(
            text(
                "INSERT INTO principals (id, principal_type, workspace_id, display_name) "
                "VALUES (:id, 'USER', :ws_id, 'Perf Benchmark User')"
            ),
            {"id": u_id, "ws_id": ws_id},
        )
        u_obj = ObjectRecord(
            id=u_id,
            object_type=ObjectKind.USER,
            workspace_id=ws_id,
            canonical_key=f"usr-{u_id.hex}",
            display_title="Perf Benchmark User",
            created_by_id=u_id,
        )
        init_session.add(u_obj)
        await init_session.flush()

        user = User(
            id=u_id,
            object_type=ObjectKind.USER,
            principal_type="USER",
            workspace_id=ws_id,
            email="perf@example.com",
        )
        init_session.add(user)
        await init_session.flush()

        # 3. Role Binding (WORKSPACE_ADMIN)
        rb = RoleBinding(
            workspace_id=ws_id,
            principal_id=u_id,
            role=RbacRole.WORKSPACE_ADMIN,
            scope_type="workspace",
            project_id=None,
        )
        init_session.add(rb)
        await init_session.flush()

        # 4. Project ObjectRecord + Project
        p_obj = ObjectRecord(
            id=proj_id,
            object_type=ObjectKind.PROJECT,
            workspace_id=ws_id,
            canonical_key="PERF",
            display_title="Perf Project",
            created_by_id=u_id,
        )
        init_session.add(p_obj)
        await init_session.flush()

        project = Project(
            id=proj_id,
            object_type=ObjectKind.PROJECT,
            workspace_id=ws_id,
            identifier="PERF",
            name="Perf Project",
        )
        init_session.add(project)
        await init_session.flush()

        # Query auto-seeded default state and priority
        state_res = await init_session.execute(
            select(WorkflowState).where(
                WorkflowState.project_id == proj_id, WorkflowState.is_default.is_(True)
            )
        )
        state = state_res.scalar_one()

        prio_res = await init_session.execute(
            select(ProjectPriority).where(
                ProjectPriority.project_id == proj_id, ProjectPriority.slug == "medium"
            )
        )
        priority = prio_res.scalar_one()

        state_id = state.id
        priority_id = priority.id

        await init_session.commit()

    yield ws_id, u_id, proj_id, state_id, priority_id


@pytest.mark.perf
@pytest.mark.asyncio
@pytest.mark.parametrize("slot", range(1000))
async def test_clean_db_savepoint_isolation_slot(
    slot: int,
    db_session: AsyncSession,
    perf_spine: tuple[uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID],
) -> None:
    """Validate 100% clean SAVEPOINT isolation across 1,000 runs using identical canonical_key."""
    ws_id, u_id, proj_id, state_id, priority_id = perf_spine

    rls_ctx = RLSContext(
        principal_id=u_id,
        workspace_id=ws_id,
    )

    async with db_session.begin():
        await bind_rls_context(db_session, rls_ctx)

        # Identical canonical_key in every single test slot!
        # Any leaked row from previous slots would violate uq_objects_workspace_type_key
        canonical_key = "PERF-1"
        iss_id = uuid.uuid4()

        obj = ObjectRecord(
            id=iss_id,
            object_type=ObjectKind.ISSUE,
            workspace_id=ws_id,
            project_id=proj_id,
            canonical_key=canonical_key,
            display_title=f"Benchmark Issue {slot}",
            created_by_id=u_id,
        )
        db_session.add(obj)
        await db_session.flush()

        # Allocate sequence 1 for PERF-1
        seq_res = await db_session.execute(
            text("SELECT allocate_issue_sequence(:p)"),
            {"p": proj_id},
        )
        seq = seq_res.scalar_one()

        issue = Issue(
            id=iss_id,
            workspace_id=ws_id,
            project_id=proj_id,
            sequence_id=seq,
            state_id=state_id,
            priority_id=priority_id,
            created_by_id=u_id,
            summary=f"Benchmark Issue #{slot}",
            description_markdown="Quantitative SAVEPOINT isolation benchmark test.",
            board_rank="0000000000000001",
        )
        db_session.add(issue)
        await db_session.flush()

        # Query back under FORCE RLS
        stmt = select(Issue).where(Issue.id == iss_id)
        res = await db_session.execute(stmt)
        loaded = res.scalar_one()
        assert loaded.id == iss_id
        assert loaded.summary == f"Benchmark Issue #{slot}"
