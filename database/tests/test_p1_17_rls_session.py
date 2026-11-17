"""Unit tests for SET LOCAL RLS session binder, isolation, and guards (KANBA-55 / KB-P1-17)."""

import os
import uuid

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

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
from database.session import (
    RLSContext,
    RLSContextError,
    RLSRoleViolationError,
    RLSSessionFactory,
    UnboundRLSSessionError,
    bind_rls_context,
    create_rls_engine,
)
from database.testing.pg_harness import build_dsn


async def _setup_workspace_fixture(
    session: AsyncSession,
    slug_prefix: str,
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """Set up workspace, user, project, and one issue, returning (ws_id, u_id, iss_id)."""
    ws_id = uuid.uuid4()
    ws = Workspace(id=ws_id, slug=f"{slug_prefix}-{ws_id.hex[:8]}", name=f"{slug_prefix} WS")
    session.add(ws)
    await session.flush()

    u_id = uuid.uuid4()
    await session.execute(
        text(
            "INSERT INTO principals (id, principal_type, workspace_id, display_name) "
            "VALUES (:id, 'USER', :ws_id, :name)"
        ),
        {"id": u_id, "ws_id": ws_id, "name": f"{slug_prefix} User"},
    )
    u_obj = ObjectRecord(
        id=u_id,
        object_type=ObjectKind.USER,
        workspace_id=ws_id,
        canonical_key=f"usr-{u_id.hex}",
        display_title=f"{slug_prefix} User",
        created_by_id=u_id,
    )
    session.add(u_obj)
    await session.flush()

    user = User(
        id=u_id,
        object_type=ObjectKind.USER,
        principal_type="USER",
        workspace_id=ws_id,
        email=f"{slug_prefix}@example.com",
    )
    session.add(user)

    # Workspace Admin RoleBinding
    rb = RoleBinding(
        workspace_id=ws_id,
        principal_id=u_id,
        role=RbacRole.WORKSPACE_ADMIN,
        scope_type="workspace",
        project_id=None,
    )
    session.add(rb)
    await session.flush()

    # Project
    p_id = uuid.uuid4()
    ident = f"P{slug_prefix[:3].upper()}"
    p_obj = ObjectRecord(
        id=p_id,
        object_type=ObjectKind.PROJECT,
        workspace_id=ws_id,
        canonical_key=ident,
        display_title=f"{slug_prefix} Project",
        created_by_id=u_id,
    )
    session.add(p_obj)
    await session.flush()

    project = Project(
        id=p_id,
        object_type=ObjectKind.PROJECT,
        workspace_id=ws_id,
        identifier=ident,
        name=f"{slug_prefix} Project",
    )
    session.add(project)
    await session.flush()

    # Query seeded WorkflowState and Priority
    state_res = await session.execute(
        select(WorkflowState).where(
            WorkflowState.project_id == p_id, WorkflowState.is_default.is_(True)
        )
    )
    state = state_res.scalar_one()

    priority_res = await session.execute(
        select(ProjectPriority).where(
            ProjectPriority.project_id == p_id, ProjectPriority.slug == "medium"
        )
    )
    priority = priority_res.scalar_one()

    # Allocate sequence and insert Issue
    seq_id = await session.scalar(text("SELECT allocate_issue_sequence(:p_id)"), {"p_id": p_id})
    iss_id = uuid.uuid4()
    iss_obj = ObjectRecord(
        id=iss_id,
        object_type=ObjectKind.ISSUE,
        workspace_id=ws_id,
        project_id=p_id,
        canonical_key=f"{ident}-{seq_id}",
        display_title=f"{slug_prefix} Issue",
        created_by_id=u_id,
    )
    session.add(iss_obj)
    await session.flush()

    issue = Issue(
        id=iss_id,
        object_type=ObjectKind.ISSUE,
        workspace_id=ws_id,
        project_id=p_id,
        sequence_id=seq_id,
        summary=f"{slug_prefix} Issue",
        description_markdown=f"{slug_prefix} description",
        state_id=state.id,
        priority_id=priority.id,
        created_by_id=u_id,
        original_created_by_id=u_id,
        ancestry_path=str(seq_id),
        board_rank="0|hzzzzz:",
    )
    session.add(issue)
    await session.flush()

    # Rebuild access closure for the workspace
    await session.execute(
        text("SELECT rebuild_effective_access_for_workspace(:ws_id)"),
        {"ws_id": ws_id},
    )
    await session.flush()

    return ws_id, u_id, iss_id


@pytest.mark.committed_db
@pytest.mark.asyncio
async def test_set_local_binding_and_isolation_with_pool_reuse(
    committed_db_session: AsyncSession,
    pg_worker_db: AsyncEngine,
) -> None:
    """Verify SET LOCAL tenant isolation with single-connection pool reuse (Test Case 2)."""
    # 1. Setup WS1 and WS2 in committed session
    ws1_id, u_ws1, iss1_id = await _setup_workspace_fixture(committed_db_session, "wsone")
    ws2_id, u_ws2, iss2_id = await _setup_workspace_fixture(committed_db_session, "wstwo")
    await committed_db_session.commit()

    db_name = pg_worker_db.url.database or "kanban_test_master"
    socket_dir = os.environ.get("KB_TEST_PGHOST", "/tmp/kb-pgsock")

    # 2. Open RLSSessionFactory with pool_size=1, max_overflow=0 under kanban_app role
    app_dsn = build_dsn(database=db_name, host=socket_dir, user="kanban_app")
    engine = create_rls_engine(app_dsn, pool_size=1, max_overflow=0)
    factory = RLSSessionFactory(engine)

    try:
        # Transaction 1: bound to WS1
        ctx1 = RLSContext(
            principal_id=u_ws1,
            workspace_id=ws1_id,
            token_scopes=("issue:read",),
            aal_level=1,
        )
        async with factory.session(ctx1) as sess1:
            issues_ws1 = (await sess1.scalars(select(Issue))).all()
            assert len(issues_ws1) == 1
            assert issues_ws1[0].id == iss1_id
            # Mid-session commit followed by subsequent query must succeed cleanly
            await sess1.commit()
            post_commit_ok = await sess1.scalar(text("SELECT 1"))
            assert post_commit_ok == 1

        # Transaction 2: bound to WS2 on the SAME single connection
        ctx2 = RLSContext(
            principal_id=u_ws2,
            workspace_id=ws2_id,
            token_scopes=("issue:read",),
            aal_level=1,
        )
        async with factory.session(ctx2) as sess2:
            issues_ws2 = (await sess2.scalars(select(Issue))).all()
            assert len(issues_ws2) == 1
            assert issues_ws2[0].id == iss2_id

        # 3. Open raw connection without binding RLS context
        async with engine.connect() as raw_conn:
            val = await raw_conn.scalar(text("SELECT current_setting('app.principal_id', true)"))
            assert val == "" or val is None

            val_ws = await raw_conn.scalar(text("SELECT current_setting('app.workspace_id', true)"))
            assert val_ws == "" or val_ws is None

            # RLS policy must deny all issues
            count = await raw_conn.scalar(text("SELECT count(*) FROM issues"))
            assert count == 0

    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_unbound_session_guard(
    pg_worker_db: AsyncEngine,
) -> None:
    """Verify unbound session queries raise UnboundRLSSessionError before hitting PG."""
    db_name = pg_worker_db.url.database or "kanban_test_master"
    socket_dir = os.environ.get("KB_TEST_PGHOST", "/tmp/kb-pgsock")

    app_dsn = build_dsn(database=db_name, host=socket_dir, user="kanban_app")
    engine = create_rls_engine(app_dsn, pool_size=1, max_overflow=0)
    factory = RLSSessionFactory(engine)

    ctx = RLSContext(principal_id=uuid.uuid4(), workspace_id=uuid.uuid4())

    try:
        # 1. Unbound session query raises UnboundRLSSessionError before hitting PG
        raw_sess = factory.sessionmaker()
        with pytest.raises(
            UnboundRLSSessionError,
            match="Executing query on unbound RLS session is forbidden",
        ):
            await raw_sess.execute(select(Issue))

        # 2. Calling bind_rls_context outside transaction raises RLSContextError
        with pytest.raises(
            RLSContextError, match="bind_rls_context requires an active transaction"
        ):
            await bind_rls_context(raw_sess, ctx)

        # 3. Inside a transaction, bind_rls_context succeeds and query succeeds
        async with raw_sess.begin():
            await bind_rls_context(raw_sess, ctx)
            assert raw_sess.info.get("rls_bound") is True
            # Nested savepoint transaction
            async with raw_sess.begin_nested():
                res_nested = await raw_sess.scalars(select(Issue))
                assert res_nested.all() == []
            # After nested transaction ends (parent is not None), rls_bound remains True
            assert raw_sess.info.get("rls_bound") is True

            # Query executes without raising UnboundRLSSessionError
            res = await raw_sess.scalars(select(Issue))
            assert res.all() == []

        # 4. After transaction ends, session is unbound again
        with pytest.raises(UnboundRLSSessionError):
            await raw_sess.execute(select(Issue))

        await raw_sess.close()

    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_verify_non_bypass_role(
    pg_worker_db: AsyncEngine,
) -> None:
    """Verify role checks fail-closed for SUPERUSER/BYPASSRLS and pass for app roles."""
    db_name = pg_worker_db.url.database or "kanban_test_master"
    socket_dir = os.environ.get("KB_TEST_PGHOST", "/tmp/kb-pgsock")

    # Superuser role (kanban_test) must fail closed
    test_dsn = build_dsn(database=db_name, host=socket_dir, user="kanban_test")
    test_engine = create_rls_engine(test_dsn, pool_size=1, max_overflow=0)
    test_factory = RLSSessionFactory(test_engine)
    try:
        with pytest.raises(RLSRoleViolationError, match="Database role has bypass privileges"):
            await test_factory.verify_non_bypass_role()
    finally:
        await test_engine.dispose()

    # Migrator role (kanban_migrator) has BYPASSRLS and must fail closed
    migrator_dsn = build_dsn(database=db_name, host=socket_dir, user="kanban_migrator")
    migrator_engine = create_rls_engine(migrator_dsn, pool_size=1, max_overflow=0)
    migrator_factory = RLSSessionFactory(migrator_engine)
    try:
        with pytest.raises(RLSRoleViolationError, match="Database role has bypass privileges"):
            await migrator_factory.verify_non_bypass_role()
    finally:
        await migrator_engine.dispose()

    # App role (kanban_app) must pass
    app_dsn = build_dsn(database=db_name, host=socket_dir, user="kanban_app")
    app_engine = create_rls_engine(app_dsn, pool_size=1, max_overflow=0)
    app_factory = RLSSessionFactory(app_engine)
    try:
        await app_factory.verify_non_bypass_role()
    finally:
        await app_engine.dispose()

    # Reader role (app_rls_reader) must pass
    reader_dsn = build_dsn(database=db_name, host=socket_dir, user="app_rls_reader")
    reader_engine = create_rls_engine(reader_dsn, pool_size=1, max_overflow=0)
    reader_factory = RLSSessionFactory(reader_engine)
    try:
        await reader_factory.verify_non_bypass_role()
    finally:
        await reader_engine.dispose()


@pytest.mark.asyncio
async def test_rls_context_validation() -> None:
    """Verify RLSContext dataclass validates aal_level and token_scopes (Test Case 4)."""
    p_id = uuid.uuid4()
    w_id = uuid.uuid4()

    # Valid instances
    ctx1 = RLSContext(principal_id=p_id, workspace_id=w_id)
    assert ctx1.aal_level == 1
    assert ctx1.token_scopes == ()

    ctx2 = RLSContext(
        principal_id=p_id,
        workspace_id=w_id,
        token_scopes=("issue:read", "project:write"),
        aal_level=2,
    )
    assert ctx2.aal_level == 2
    assert ctx2.token_scopes == ("issue:read", "project:write")

    # list converted to tuple
    ctx3 = RLSContext(
        principal_id=p_id,
        workspace_id=w_id,
        token_scopes=["issue:read"],  # type: ignore[arg-type]
    )
    assert ctx3.token_scopes == ("issue:read",)

    # non-str scope raises TypeError
    with pytest.raises(TypeError, match="Token scope must be a string"):
        RLSContext(
            principal_id=p_id,
            workspace_id=w_id,
            token_scopes=(123,),  # type: ignore[arg-type]
        )

    # RLSSessionFactory classmethod create_rls_engine
    engine = RLSSessionFactory.create_rls_engine(build_dsn("postgres"))
    assert isinstance(engine, AsyncEngine)
    await engine.dispose()

    # aal_level validation
    with pytest.raises(ValueError, match="Invalid aal_level: 3"):
        RLSContext(principal_id=p_id, workspace_id=w_id, aal_level=3)  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="Invalid aal_level: 0"):
        RLSContext(principal_id=p_id, workspace_id=w_id, aal_level=0)  # type: ignore[arg-type]

    # token_scopes validation: commas forbidden
    with pytest.raises(ValueError, match="Invalid token scope: 'issue:read,admin'"):
        RLSContext(
            principal_id=p_id,
            workspace_id=w_id,
            token_scopes=("issue:read,admin",),
        )

    # token_scopes validation: whitespace forbidden
    with pytest.raises(ValueError, match="Invalid token scope: 'issue:read admin'"):
        RLSContext(
            principal_id=p_id,
            workspace_id=w_id,
            token_scopes=("issue:read admin",),
        )

    # token_scopes validation: uppercase forbidden
    with pytest.raises(ValueError, match="Invalid token scope: 'UPPERCASE'"):
        RLSContext(
            principal_id=p_id,
            workspace_id=w_id,
            token_scopes=("UPPERCASE",),
        )
