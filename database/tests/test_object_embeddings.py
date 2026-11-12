"""Feature unit tests for object_embeddings, pgvector HNSW, and FORCE RLS (KB-P5-06)."""

from __future__ import annotations

import math
import uuid
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError, ProgrammingError

from database.models.embeddings import ObjectEmbedding
from database.tests.conftest import bind_ctx

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


async def _insert_test_embedding(  # noqa: PLR0913, PLR0917
    session: AsyncSession,
    ws_id: uuid.UUID,
    proj_id: uuid.UUID | None,
    object_id: uuid.UUID,
    object_type: str,
    chunk_index: int,
    vec: list[float],
    indexer_principal_id: uuid.UUID,
) -> None:
    """Insert embedding row under svc-embedding-indexer principal context."""
    await bind_ctx(session, indexer_principal_id, ws_id)
    await session.execute(
        text(
            "INSERT INTO object_embeddings ("
            "  object_id, object_type, chunk_index, workspace_id, project_id, "
            "  content_sha256, model_id, embedding"
            ") VALUES ("
            "  :obj_id, CAST(:obj_type AS object_kind), :chunk_idx, :ws_id, :proj_id, "
            "  :sha, 'bge-small-en-v1.5-int8', CAST(:emb AS vector)"
            ")"
        ),
        {
            "obj_id": object_id,
            "obj_type": object_type,
            "chunk_idx": chunk_index,
            "ws_id": ws_id,
            "proj_id": proj_id,
            "sha": b"0" * 32,
            "emb": str(vec),
        },
    )


async def _setup_workspace_and_users(
    session: AsyncSession,
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID]:
    """Provision workspace, admin user, reader user, and svc-embedding-indexer principal."""
    ws_id = uuid.uuid4()
    await session.execute(
        text("INSERT INTO workspaces (id, slug, name) VALUES (:id, :slug, :name)"),
        {"id": ws_id, "slug": f"ws-{ws_id.hex[:10]}", "name": "Embeddings Workspace"},
    )

    # Admin user
    admin_id = uuid.uuid4()
    await session.scalar(
        text(
            "SELECT register_object("
            "  'user'::object_kind, :ws_id, NULL, :ckey, 'Admin User', :uid, :id"
            ")"
        ),
        {"ws_id": ws_id, "ckey": f"usr-{admin_id.hex[:8]}", "uid": admin_id, "id": admin_id},
    )
    await session.execute(
        text(
            "INSERT INTO principals (id, workspace_id, principal_type, display_name) "
            "VALUES (:id, :ws_id, 'USER', 'Admin User')"
        ),
        {"id": admin_id, "ws_id": ws_id},
    )
    await session.execute(
        text("INSERT INTO users (id, workspace_id, email) VALUES (:id, :ws_id, :email)"),
        {"id": admin_id, "ws_id": ws_id, "email": f"admin-{admin_id.hex[:6]}@example.com"},
    )
    await session.execute(
        text(
            "INSERT INTO role_bindings (principal_id, workspace_id, role, scope_type, project_id) "
            "VALUES (:p_id, :ws_id, 'WORKSPACE_ADMIN', 'workspace', NULL)"
        ),
        {"p_id": admin_id, "ws_id": ws_id},
    )

    # Reader user
    reader_id = uuid.uuid4()
    await session.scalar(
        text(
            "SELECT register_object("
            "  'user'::object_kind, :ws_id, NULL, :ckey, 'Reader User', :uid, :id"
            ")"
        ),
        {"ws_id": ws_id, "ckey": f"usr-{reader_id.hex[:8]}", "uid": reader_id, "id": reader_id},
    )
    await session.execute(
        text(
            "INSERT INTO principals (id, workspace_id, principal_type, display_name) "
            "VALUES (:id, :ws_id, 'USER', 'Reader User')"
        ),
        {"id": reader_id, "ws_id": ws_id},
    )
    await session.execute(
        text("INSERT INTO users (id, workspace_id, email) VALUES (:id, :ws_id, :email)"),
        {"id": reader_id, "ws_id": ws_id, "email": f"reader-{reader_id.hex[:6]}@example.com"},
    )

    # Service principal for embedding indexer
    indexer_id = uuid.uuid4()
    await session.execute(
        text(
            "INSERT INTO principals (id, workspace_id, principal_type, display_name) "
            "VALUES (:id, :ws_id, 'SERVICE_PRINCIPAL', 'svc-embedding-indexer')"
        ),
        {"id": indexer_id, "ws_id": ws_id},
    )
    await session.execute(
        text(
            "INSERT INTO role_bindings (principal_id, workspace_id, role, scope_type, project_id) "
            "VALUES (:p_id, :ws_id, 'WORKSPACE_ADMIN', 'workspace', NULL)"
        ),
        {"p_id": indexer_id, "ws_id": ws_id},
    )

    await session.execute(
        text("SELECT rebuild_effective_access_for_workspace(:ws_id)"),
        {"ws_id": ws_id},
    )

    return ws_id, admin_id, reader_id, indexer_id


async def _create_test_project(
    session: AsyncSession,
    ws_id: uuid.UUID,
    creator_id: uuid.UUID,
    ident: str = "PRJA",
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """Register and insert a project entity with default workflow state and priority."""
    proj_id = await session.scalar(
        text("SELECT register_object('project'::object_kind, :ws_id, NULL, :ckey, :name, :uid)"),
        {"ws_id": ws_id, "ckey": ident, "name": f"Project {ident}", "uid": creator_id},
    )
    assert isinstance(proj_id, uuid.UUID)

    await session.execute(
        text(
            "INSERT INTO projects (id, workspace_id, identifier, name) "
            "VALUES (:id, :ws_id, :ident, :name)"
        ),
        {"id": proj_id, "ws_id": ws_id, "ident": ident, "name": f"Project {ident}"},
    )

    state_id = await session.scalar(
        text(
            "SELECT id FROM workflow_states WHERE project_id = :pid AND is_default = true LIMIT 1"
        ),
        {"pid": proj_id},
    )
    assert isinstance(state_id, uuid.UUID)

    prio_id = await session.scalar(
        text(
            "SELECT id FROM project_priorities "
            "WHERE project_id = :pid AND is_default = true LIMIT 1"
        ),
        {"pid": proj_id},
    )
    assert isinstance(prio_id, uuid.UUID)

    return proj_id, state_id, prio_id


async def _create_test_issue(  # noqa: PLR0913, PLR0917
    session: AsyncSession,
    ws_id: uuid.UUID,
    proj_id: uuid.UUID,
    creator_id: uuid.UUID,
    state_id: uuid.UUID,
    prio_id: uuid.UUID,
    markdown: str,
) -> uuid.UUID:
    """Create an issue object and row with specified markdown body."""
    seq_id = await session.scalar(
        text("SELECT allocate_issue_sequence(:pid)"),
        {"pid": proj_id},
    )
    proj_ident = await session.scalar(
        text("SELECT identifier FROM projects WHERE id = :pid"),
        {"pid": proj_id},
    )
    iss_id = await session.scalar(
        text(
            "SELECT register_object("
            "  'issue'::object_kind, :ws_id, :pid, :ckey, 'Test Issue', :uid"
            ")"
        ),
        {"ws_id": ws_id, "pid": proj_id, "ckey": f"{proj_ident}-{seq_id}", "uid": creator_id},
    )
    assert isinstance(iss_id, uuid.UUID)

    await session.execute(
        text(
            "INSERT INTO issues ("
            "  id, workspace_id, project_id, sequence_id, summary, description_markdown, "
            "  state_id, priority_id, created_by_id, ancestry_path, board_rank"
            ") VALUES ("
            "  :id, :ws_id, :pid, :seq, 'Test Issue', :desc, "
            "  :state_id, :prio_id, :uid, :ancestry, '0|hzzzzz:'"
            ")"
        ),
        {
            "id": iss_id,
            "ws_id": ws_id,
            "pid": proj_id,
            "seq": seq_id,
            "desc": markdown,
            "state_id": state_id,
            "prio_id": prio_id,
            "uid": creator_id,
            "ancestry": str(seq_id),
        },
    )
    return iss_id


@pytest.mark.asyncio
async def test_case_01_positive_db_knn_query(db_session: AsyncSession) -> None:
    """Test Case 1: Positive (DB, SAVEPOINT harness).

    Indexer inserts 3 chunks for an issue; KNN query ORDER BY embedding <=> :q LIMIT 4
    returns them for a reader with VIEW.
    """
    ws_id, admin_id, reader_id, indexer_id = await _setup_workspace_and_users(db_session)
    proj_id, state_id, prio_id = await _create_test_project(db_session, ws_id, admin_id, "PRJA")

    # Grant reader VIEW capability on project PRJA
    await db_session.execute(
        text(
            "INSERT INTO role_bindings (principal_id, workspace_id, role, scope_type, project_id) "
            "VALUES (:p_id, :ws_id, 'VIEWER', 'project', :proj_id)"
        ),
        {"p_id": reader_id, "ws_id": ws_id, "proj_id": proj_id},
    )
    await db_session.execute(
        text("SELECT rebuild_effective_access_for_workspace(:ws_id)"),
        {"ws_id": ws_id},
    )

    # 4100 chars produces exactly 3 chunks (1500 + 1300 + 1300 = 4100)
    chunk_1 = "A" * 1500
    chunk_2 = "B" * 1300
    chunk_3 = "C" * 1300
    issue_markdown = chunk_1 + chunk_2 + chunk_3
    iss_id = await _create_test_issue(
        db_session, ws_id, proj_id, admin_id, state_id, prio_id, issue_markdown
    )

    # Insert 3 chunks for the issue under indexer principal context
    for chunk_idx in range(3):
        vec = [0.0] * 384
        vec[chunk_idx] = 1.0
        await _insert_test_embedding(
            db_session,
            ws_id=ws_id,
            proj_id=proj_id,
            object_id=iss_id,
            object_type="issue",
            chunk_index=chunk_idx,
            vec=vec,
            indexer_principal_id=indexer_id,
        )

    # Verify SQLAlchemy model query coverage
    model_res = await db_session.execute(
        select(ObjectEmbedding).filter_by(object_id=iss_id, chunk_index=0)
    )
    row_obj = model_res.scalar_one()
    assert row_obj.chunk_index == 0
    assert row_obj.model_id == "bge-small-en-v1.5-int8"

    # Switch session context to reader with VIEW capability under kanban_app
    await db_session.execute(text("SET LOCAL SESSION AUTHORIZATION kanban_app"))
    await bind_ctx(db_session, reader_id, ws_id)

    # Prepare KNN query vector
    query_vec = [0.0] * 384
    query_vec[0] = 1.0  # matches chunk 0
    query_str = str(query_vec)

    knn_res = await db_session.execute(
        text(
            "SELECT object_id, chunk_index, (embedding <=> CAST(:q AS vector)) AS distance "
            "FROM object_embeddings "
            "ORDER BY embedding <=> CAST(:q AS vector) "
            "LIMIT 4"
        ),
        {"q": query_str},
    )
    rows = knn_res.all()
    assert len(rows) == 3
    assert rows[0][0] == iss_id
    assert rows[0][1] == 0
    assert math.isclose(rows[0][2], 0.0, abs_tol=1e-5)


@pytest.mark.asyncio
async def test_case_02_security_cross_project_isolation(db_session: AsyncSession) -> None:
    """Test Case 2: Security (Tenant / Project Isolation).

    Principal without VIEW on project B gets 0 rows from a KNN query that would otherwise
    rank B's object first.
    Prints raw query, principal ID, and 0-row result for forensic proof.
    """
    ws_id, admin_id, reader_id, indexer_id = await _setup_workspace_and_users(db_session)
    proj_b_id, state_b_id, prio_b_id = await _create_test_project(
        db_session, ws_id, admin_id, "PRJB"
    )

    # Reader has NO role and NO capability on project PRJB
    await db_session.execute(
        text("SELECT rebuild_effective_access_for_workspace(:ws_id)"),
        {"ws_id": ws_id},
    )

    # Create issue on project B
    issue_b_id = await _create_test_issue(
        db_session, ws_id, proj_b_id, admin_id, state_b_id, prio_b_id, "Private Project B Issue"
    )

    vec_b = [0.0] * 384
    vec_b[0] = 1.0
    await _insert_test_embedding(
        db_session,
        ws_id=ws_id,
        proj_id=proj_b_id,
        object_id=issue_b_id,
        object_type="issue",
        chunk_index=0,
        vec=vec_b,
        indexer_principal_id=indexer_id,
    )

    # Switch session context to reader (who lacks VIEW on project B) under kanban_app
    await db_session.execute(text("SET LOCAL SESSION AUTHORIZATION kanban_app"))
    await bind_ctx(db_session, reader_id, ws_id)

    query_vec = [0.0] * 384
    query_vec[0] = 1.0
    query_str = str(query_vec)

    knn_sql = (
        "SELECT object_id, chunk_index, (embedding <=> CAST(:q AS vector)) AS distance "
        "FROM object_embeddings "
        "ORDER BY embedding <=> CAST(:q AS vector) "
        "LIMIT 4"
    )
    knn_res = await db_session.execute(text(knn_sql), {"q": query_str})
    rows = knn_res.all()

    # Required forensic logging for docs/qa/KANBA-63/rls-knn-proof.txt
    print("\n--- RLS KNN PROOF: CASE 2 ---")  # noqa: T201
    print(f"Executing KNN Query: {knn_sql}")  # noqa: T201
    print(f"Target Object ID (Project B): {issue_b_id}")  # noqa: T201
    print(f"Active Principal ID (No VIEW on Project B): {reader_id}")  # noqa: T201
    print(f"Active Workspace ID: {ws_id}")  # noqa: T201
    print(f"Returned Rows Count: {len(rows)}")  # noqa: T201
    print(f"Returned Rows Payload: {rows}")  # noqa: T201
    print("Verification: 0 rows returned - project B embeddings masked by FORCE RLS.\n")  # noqa: T201

    assert len(rows) == 0


@pytest.mark.asyncio
async def test_case_03_security_write_restrictions(db_session: AsyncSession) -> None:
    """Test Case 3: Security (Write Restrictions).

    - app_rls_reader INSERT -> permission denied (Postgres 42501)
    - non-indexer principal under kanban_app -> RLS WITH CHECK violation (Postgres 44501)
    """
    ws_id, admin_id, _reader_id, _indexer_id = await _setup_workspace_and_users(db_session)
    proj_id, state_id, prio_id = await _create_test_project(db_session, ws_id, admin_id, "PRJW")
    iss_id = await _create_test_issue(
        db_session, ws_id, proj_id, admin_id, state_id, prio_id, "Write Security Issue"
    )

    sha32 = b"0" * 32
    dummy_vec = str([0.0] * 384)

    # Part A: app_rls_reader INSERT -> permission denied
    sp = await db_session.begin_nested()
    try:
        await db_session.execute(text("SET LOCAL SESSION AUTHORIZATION app_rls_reader"))
        with pytest.raises((DBAPIError, ProgrammingError)) as exc_info_a:
            await db_session.execute(
                text(
                    "INSERT INTO object_embeddings ("
                    "  object_id, object_type, chunk_index, workspace_id, project_id, "
                    "  content_sha256, model_id, embedding"
                    ") VALUES ("
                    "  :obj_id, 'issue', 0, :ws_id, :proj_id, :sha, 'test-model', "
                    "  CAST(:emb AS vector)"
                    ")"
                ),
                {
                    "obj_id": iss_id,
                    "ws_id": ws_id,
                    "proj_id": proj_id,
                    "sha": sha32,
                    "emb": dummy_vec,
                },
            )
        assert "permission denied for table object_embeddings" in str(exc_info_a.value).lower()
    finally:
        await sp.rollback()
        await db_session.execute(text("RESET SESSION AUTHORIZATION"))

    # Part B: non-indexer principal under kanban_app -> RLS WITH CHECK violation
    sp = await db_session.begin_nested()
    try:
        await db_session.execute(text("SET LOCAL SESSION AUTHORIZATION kanban_app"))
        await bind_ctx(db_session, admin_id, ws_id)  # admin_id is NOT svc-embedding-indexer!

        with pytest.raises((DBAPIError, ProgrammingError)) as exc_info_b:
            await db_session.execute(
                text(
                    "INSERT INTO object_embeddings ("
                    "  object_id, object_type, chunk_index, workspace_id, project_id, "
                    "  content_sha256, model_id, embedding"
                    ") VALUES ("
                    "  :obj_id, 'issue', 0, :ws_id, :proj_id, :sha, 'test-model', "
                    "  CAST(:emb AS vector)"
                    ")"
                ),
                {
                    "obj_id": iss_id,
                    "ws_id": ws_id,
                    "proj_id": proj_id,
                    "sha": sha32,
                    "emb": dummy_vec,
                },
            )
        assert "row-level security policy" in str(exc_info_b.value).lower()
    finally:
        await sp.rollback()
        await db_session.execute(text("RESET SESSION AUTHORIZATION"))


@pytest.mark.asyncio
async def test_case_08_db_boundary_and_hnsw_index(db_session: AsyncSession) -> None:
    """Test Case 8: Boundary & HNSW index presence.

    Verify HNSW index present in pg_indexes with vector_cosine_ops.
    """
    res = await db_session.execute(
        text(
            "SELECT indexname, indexdef FROM pg_indexes "
            "WHERE tablename = 'object_embeddings' AND indexname = 'object_embeddings_hnsw'"
        )
    )
    row = res.one_or_none()
    assert row is not None, "object_embeddings_hnsw index must exist in pg_indexes"
    idx_name, idx_def = row[0], row[1]
    assert idx_name == "object_embeddings_hnsw"
    assert "hnsw" in idx_def.lower()
    assert "vector_cosine_ops" in idx_def


@pytest.mark.asyncio
async def test_case_09_catalog_rls_flags(db_session: AsyncSession) -> None:
    """Test Case 9: Catalog.

    Verify object_embeddings has relrowsecurity and relforcerowsecurity TRUE.
    """
    res = await db_session.execute(
        text(
            "SELECT relrowsecurity, relforcerowsecurity FROM pg_class "
            "WHERE relname = 'object_embeddings'"
        )
    )
    row = res.one_or_none()
    assert row is not None, "object_embeddings table must exist in pg_class"
    assert row[0] is True, "relrowsecurity must be TRUE on object_embeddings"
    assert row[1] is True, "relforcerowsecurity must be TRUE on object_embeddings"
