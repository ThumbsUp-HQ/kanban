"""Unit and integration tests for EmbeddingIndexer, idempotency, and fault handling."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import text

from agent.embeddings.base import EmbedderDimensionMismatchError
from agent.embeddings.indexer import (
    EmbeddingIndexer,
    _extract_event_fields,
    chunk_markdown,
)
from agent.providers.base import EmbedBatchRequest
from agent.providers.errors import ProviderTimeout
from agent.testing.fixtures import FixtureLLMProvider, load_cassette
from database.session import RLSContextError

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy.ext.asyncio import AsyncSession


class MockDeterministicEmbedder:
    """Mock embedder returning deterministic 384-dimensional unit vectors."""

    def __init__(self, model_id: str = "bge-small-en-v1.5-int8") -> None:
        """Initialize mock deterministic embedder."""
        self._model_id = model_id
        self.call_count = 0
        self.embedded_texts: list[str] = []

    @property
    def model_id(self) -> str:
        """Return model identifier."""
        return self._model_id

    @property
    def dimension(self) -> int:
        """Return embedding dimension."""
        return 384

    async def embed_batch(self, texts: Sequence[str]) -> list[list[float]]:
        """Return deterministic orthogonal unit vectors."""
        self.call_count += 1
        self.embedded_texts.extend(texts)
        results: list[list[float]] = []
        for idx, _ in enumerate(texts):
            vec = [0.0] * 384
            vec[idx % 384] = 1.0
            results.append(vec)
        return results


async def _setup_indexer_env(
    session: AsyncSession,
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID]:
    """Set up workspace, admin, indexer principal, and project."""
    ws_id = uuid.uuid4()
    admin_id = uuid.uuid4()
    indexer_id = uuid.uuid4()

    await session.execute(
        text("INSERT INTO workspaces (id, name, slug) VALUES (:id, 'Indexer WS', :slug)"),
        {"id": ws_id, "slug": f"ws-{ws_id.hex[:10]}"},
    )

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

    # Service principal for embedding indexer
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

    # Project setup
    ident = f"P{ws_id.hex[:4].upper()}"
    proj_id = await session.scalar(
        text(
            "SELECT register_object("
            "  'project'::object_kind, :ws_id, NULL, :ckey, 'Indexer Project', :uid"
            ")"
        ),
        {"ws_id": ws_id, "ckey": ident, "uid": admin_id},
    )
    assert isinstance(proj_id, uuid.UUID)

    await session.execute(
        text(
            "INSERT INTO projects (id, workspace_id, identifier, name) "
            "VALUES (:id, :ws_id, :ident, 'Indexer Project')"
        ),
        {"id": proj_id, "ws_id": ws_id, "ident": ident},
    )

    state_id = await session.scalar(
        text(
            "SELECT id FROM workflow_states "
            "WHERE project_id = :pid AND is_default = true LIMIT 1"
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

    return ws_id, admin_id, indexer_id, proj_id, state_id


async def _create_test_issue(
    session: AsyncSession,
    ws_id: uuid.UUID,
    proj_id: uuid.UUID,
    admin_id: uuid.UUID,
    markdown: str,
) -> uuid.UUID:
    """Register and create an issue object."""
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
        {"ws_id": ws_id, "pid": proj_id, "ckey": f"{proj_ident}-{seq_id}", "uid": admin_id},
    )
    assert isinstance(iss_id, uuid.UUID)

    state_id = await session.scalar(
        text(
            "SELECT id FROM workflow_states "
            "WHERE project_id = :pid AND is_default = true LIMIT 1"
        ),
        {"pid": proj_id},
    )
    prio_id = await session.scalar(
        text(
            "SELECT id FROM project_priorities "
            "WHERE project_id = :pid AND is_default = true LIMIT 1"
        ),
        {"pid": proj_id},
    )

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
            "uid": admin_id,
            "ancestry": str(seq_id),
        },
    )
    return iss_id


async def _create_test_doc(
    session: AsyncSession,
    ws_id: uuid.UUID,
    proj_id: uuid.UUID,
    admin_id: uuid.UUID,
    markdown: str,
) -> uuid.UUID:
    """Register and create a doc object."""
    doc_id = uuid.uuid4()
    await session.execute(
        text(
            "SELECT register_object('doc'::object_kind, :ws, :p, :ckey, 'Test Doc', :creator, :id)"
        ),
        {
            "ws": ws_id,
            "p": proj_id,
            "ckey": f"DOC-{doc_id.hex[:8]}",
            "creator": admin_id,
            "id": doc_id,
        },
    )
    await session.execute(
        text(
            "INSERT INTO docs (id, workspace_id, project_id, title, body_markdown) "
            "VALUES (:id, :ws, :p, 'Test Doc', :body)"
        ),
        {"id": doc_id, "ws": ws_id, "p": proj_id, "body": markdown},
    )
    return doc_id


async def _create_test_sticky(
    session: AsyncSession,
    ws_id: uuid.UUID,
    proj_id: uuid.UUID,
    admin_id: uuid.UUID,
    markdown: str,
) -> uuid.UUID:
    """Register and create a sticky object."""
    stk_id = uuid.uuid4()
    await session.execute(
        text(
            "SELECT register_object("
            "  'sticky'::object_kind, :ws, :p, :ckey, 'Test Sticky', :creator, :id"
            ")"
        ),
        {
            "ws": ws_id,
            "p": proj_id,
            "ckey": f"STK-{stk_id.hex[:8]}",
            "creator": admin_id,
            "id": stk_id,
        },
    )
    await session.execute(
        text(
            "INSERT INTO stickies (id, workspace_id, project_id, body_markdown) "
            "VALUES (:id, :ws, :p, :body)"
        ),
        {"id": stk_id, "ws": ws_id, "p": proj_id, "body": markdown},
    )
    return stk_id


async def _create_test_page(
    session: AsyncSession,
    ws_id: uuid.UUID,
    doc_id: uuid.UUID,
    admin_id: uuid.UUID,
    markdown: str,
) -> uuid.UUID:
    """Register and create a page object attached to a doc."""
    page_id = uuid.uuid4()
    doc_row = (
        await session.execute(
            text("SELECT project_id FROM docs WHERE id = :d"),
            {"d": doc_id},
        )
    ).fetchone()
    assert doc_row is not None
    doc_proj = doc_row.project_id

    await session.execute(
        text(
            "SELECT register_object("
            "  'page'::object_kind, :ws, :p, :ckey, 'Test Page', :creator, :id"
            ")"
        ),
        {
            "ws": ws_id,
            "p": doc_proj,
            "ckey": f"PAGE-{page_id.hex[:8]}",
            "creator": admin_id,
            "id": page_id,
        },
    )
    await session.execute(
        text(
            "INSERT INTO pages (id, workspace_id, doc_id, title, body_markdown) "
            "VALUES (:id, :ws, :doc_id, 'Test Page', :body)"
        ),
        {"id": page_id, "ws": ws_id, "doc_id": doc_id, "body": markdown},
    )
    return page_id


# ==============================================================================
# Feature Test Cases
# ==============================================================================


@pytest.mark.asyncio
async def test_case_06_idempotency_same_event_processed_twice(
    db_session: AsyncSession,
) -> None:
    """Test Case 6: Idempotency.

    Same event processed twice -> one embedding write batch;
    unchanged content -> zero writes.
    """
    ws_id, admin_id, indexer_id, proj_id, _ = await _setup_indexer_env(db_session)

    # 4100 chars -> 3 chunks (1500 + 1300 + 1300)
    chunk_1 = "A" * 1500
    chunk_2 = "B" * 1300
    chunk_3 = "C" * 1300
    markdown = chunk_1 + chunk_2 + chunk_3
    iss_id = await _create_test_issue(db_session, ws_id, proj_id, admin_id, markdown)

    embedder = MockDeterministicEmbedder()
    indexer = EmbeddingIndexer(embedder, indexer_principal_id=indexer_id)

    # First run: action="created"
    written_1 = await indexer.index_object(
        db_session,
        workspace_id=ws_id,
        object_type="issue",
        object_id=iss_id,
        project_id=proj_id,
        action="created",
    )
    assert written_1 == 3
    assert embedder.call_count == 1

    # Second run: same content, action="updated"
    written_2 = await indexer.index_object(
        db_session,
        workspace_id=ws_id,
        object_type="issue",
        object_id=iss_id,
        project_id=proj_id,
        action="updated",
    )
    assert written_2 == 0
    # Embedder was NOT called again because content_sha256 was unchanged
    assert embedder.call_count == 1

    # Verify rows in DB
    cnt = await db_session.scalar(
        text("SELECT count(*) FROM object_embeddings WHERE object_id = :id"),
        {"id": iss_id},
    )
    assert cnt == 3


@pytest.mark.asyncio
async def test_case_07_fault_timeout_retry_and_poison_ack(
    db_session: AsyncSession,
) -> None:
    """Test Case 7 Part A: Fault (Timeout retry and EMBEDDING_INDEX_FAILED poison log).

    Cassette embed_fault_timeout.yaml -> event retried, after 5 attempts acknowledged
    with EMBEDDING_INDEX_FAILED logged to activity_records via append_activity.
    """
    ws_id, admin_id, indexer_id, proj_id, _ = await _setup_indexer_env(db_session)
    iss_id = await _create_test_issue(
        db_session, ws_id, proj_id, admin_id, "Issue triggering timeout fault"
    )

    cassette = load_cassette(Path("tests/fixtures/ai/embed_fault_timeout.yaml"))
    provider = FixtureLLMProvider([cassette])

    mock_failing_embedder = MagicMock()
    mock_failing_embedder.model_id = "bge-small-en-v1.5"
    mock_failing_embedder.dimension = 384

    async def _failing_embed(texts: Sequence[str]) -> list[list[float]]:
        # This will trigger the fault from the cassette via provider
        req = EmbedBatchRequest(model="bge-small-en-v1.5", inputs=tuple(texts))
        await provider.embed_batch(req)
        return []

    mock_failing_embedder.embed_batch = AsyncMock(side_effect=_failing_embed)

    indexer = EmbeddingIndexer(
        mock_failing_embedder, max_attempts=5, indexer_principal_id=indexer_id
    )

    event_id = uuid.uuid4()
    event_dict = {
        "id": event_id,
        "topic": "issue.updated",
        "workspace_id": ws_id,
        "project_id": proj_id,
        "payload": {"object_id": iss_id, "project_id": proj_id},
    }

    # First 4 attempts should raise exception
    for _ in range(4):
        with pytest.raises(ProviderTimeout):
            await indexer.process_event(db_session, event_dict)

    # 5th attempt: poison threshold reached -> acknowledged and logs EMBEDDING_INDEX_FAILED
    ack = await indexer.process_event(db_session, event_dict)
    assert ack is True

    # Verify EMBEDDING_INDEX_FAILED record in activity_records
    act_row = (
        await db_session.execute(
            text(
                "SELECT event_type, payload FROM activity_records "
                "WHERE object_id = :obj_id AND event_type = 'EMBEDDING_INDEX_FAILED'"
            ),
            {"obj_id": iss_id},
        )
    ).fetchone()
    assert act_row is not None
    assert act_row[0] == "EMBEDDING_INDEX_FAILED"
    payload = act_row[1]
    assert str(event_id) in str(payload)


@pytest.mark.asyncio
async def test_case_07_fault_dim_mismatch_rejected(
    db_session: AsyncSession,
) -> None:
    """Test Case 7 Part B: Fault (Dimension mismatch rejected, no row written).

    Cassette embed_fault_dim_mismatch.yaml (returns 383) -> rejected, no row written.
    """
    ws_id, admin_id, indexer_id, proj_id, _ = await _setup_indexer_env(db_session)
    iss_id = await _create_test_issue(
        db_session, ws_id, proj_id, admin_id, "Issue with dimension mismatch"
    )

    # Mock embedder returning 383 dimension (mismatch from TARGET_DIMENSION=384)
    mismatch_embedder = MagicMock()
    mismatch_embedder.model_id = "mismatch-model"
    mismatch_embedder.dimension = 384
    mismatch_embedder.embed_batch = AsyncMock(return_value=[[0.1] * 383])

    indexer = EmbeddingIndexer(mismatch_embedder, indexer_principal_id=indexer_id)

    with pytest.raises(EmbedderDimensionMismatchError) as exc_info:
        await indexer.index_object(
            db_session,
            workspace_id=ws_id,
            object_type="issue",
            object_id=iss_id,
            project_id=proj_id,
            action="updated",
        )

    assert "Vector dimension mismatch: expected 384, got 383" in str(exc_info.value)

    # Verify 0 rows written in object_embeddings
    cnt = await db_session.scalar(
        text("SELECT count(*) FROM object_embeddings WHERE object_id = :id"),
        {"id": iss_id},
    )
    assert cnt == 0


@pytest.mark.asyncio
async def test_case_08_boundary_65_chunks_capped_at_64(
    db_session: AsyncSession,
) -> None:
    """Test Case 8 Part A: Boundary (Document producing 65 chunks stores exactly 64)."""
    ws_id, admin_id, indexer_id, proj_id, _ = await _setup_indexer_env(db_session)

    # 1500 + 64 * 1300 = 84700 chars produces 65 chunks
    large_markdown = "X" * 85000
    doc_id = await _create_test_doc(db_session, ws_id, proj_id, admin_id, large_markdown)

    embedder = MockDeterministicEmbedder()
    indexer = EmbeddingIndexer(embedder, indexer_principal_id=indexer_id)

    written = await indexer.index_object(
        db_session,
        workspace_id=ws_id,
        object_type="doc",
        object_id=doc_id,
        project_id=proj_id,
        action="created",
    )
    assert written == 64

    # Verify exactly 64 chunks stored in DB with indices 0 to 63
    chunks = (
        await db_session.execute(
            text(
                "SELECT chunk_index FROM object_embeddings "
                "WHERE object_id = :id ORDER BY chunk_index ASC"
            ),
            {"id": doc_id},
        )
    ).scalars().all()

    assert len(chunks) == 64
    assert chunks[0] == 0
    assert chunks[-1] == 63


@pytest.mark.asyncio
async def test_case_08_boundary_document_shrinking_prunes_chunks(
    db_session: AsyncSession,
) -> None:
    """Test Case 8 Part B: Boundary (Document shrinking prunes surplus chunks)."""
    ws_id, admin_id, indexer_id, proj_id, _ = await _setup_indexer_env(db_session)

    # 5 chunks: 1500 + 4 * 1300 = 6700 chars
    body_5_chunks = "Initial content. " * 400
    doc_id = await _create_test_doc(db_session, ws_id, proj_id, admin_id, body_5_chunks)

    embedder = MockDeterministicEmbedder()
    indexer = EmbeddingIndexer(embedder, indexer_principal_id=indexer_id)

    w1 = await indexer.index_object(
        db_session,
        workspace_id=ws_id,
        object_type="doc",
        object_id=doc_id,
        project_id=proj_id,
        action="created",
    )
    assert w1 > 2

    # Shrink doc to 2 chunks (1500 + 1300 = 2800 chars)
    body_2_chunks = "Shortened content. " * 100
    await db_session.execute(
        text("UPDATE docs SET body_markdown = :body WHERE id = :id"),
        {"id": doc_id, "body": body_2_chunks},
    )

    await indexer.index_object(
        db_session,
        workspace_id=ws_id,
        object_type="doc",
        object_id=doc_id,
        project_id=proj_id,
        action="updated",
    )

    # Verify remaining chunks are only indices 0 and 1
    chunks = (
        await db_session.execute(
            text(
                "SELECT chunk_index FROM object_embeddings "
                "WHERE object_id = :id ORDER BY chunk_index ASC"
            ),
            {"id": doc_id},
        )
    ).scalars().all()

    assert len(chunks) == 2
    assert chunks == [0, 1]


@pytest.mark.asyncio
async def test_case_08_delete_action_removes_all_chunks(
    db_session: AsyncSession,
) -> None:
    """Test Case 8 Part C: Delete event removes all chunks."""
    ws_id, admin_id, indexer_id, proj_id, _ = await _setup_indexer_env(db_session)
    stk_id = await _create_test_sticky(
        db_session, ws_id, proj_id, admin_id, "Sticky note content to delete"
    )

    embedder = MockDeterministicEmbedder()
    indexer = EmbeddingIndexer(embedder, indexer_principal_id=indexer_id)

    await indexer.index_object(
        db_session,
        workspace_id=ws_id,
        object_type="sticky",
        object_id=stk_id,
        project_id=proj_id,
        action="created",
    )

    # Verify 1 chunk exists
    cnt_before = await db_session.scalar(
        text("SELECT count(*) FROM object_embeddings WHERE object_id = :id"),
        {"id": stk_id},
    )
    assert cnt_before == 1

    # Delete action
    deleted_count = await indexer.index_object(
        db_session,
        workspace_id=ws_id,
        object_type="sticky",
        object_id=stk_id,
        project_id=proj_id,
        action="deleted",
    )
    assert deleted_count == 1

    cnt_after = await db_session.scalar(
        text("SELECT count(*) FROM object_embeddings WHERE object_id = :id"),
        {"id": stk_id},
    )
    assert cnt_after == 0


@pytest.mark.asyncio
async def test_page_object_indexing_and_empty_markdown(
    db_session: AsyncSession,
) -> None:
    """Test page object indexing and empty markdown body chunk cleanup."""
    ws_id, admin_id, indexer_id, proj_id, _ = await _setup_indexer_env(db_session)
    doc_id = await _create_test_doc(db_session, ws_id, proj_id, admin_id, "Parent Doc")
    page_id = await _create_test_page(
        db_session, ws_id, doc_id, admin_id, "Initial Page markdown text"
    )

    embedder = MockDeterministicEmbedder()
    indexer = EmbeddingIndexer(embedder, indexer_principal_id=indexer_id)

    # Index page
    written = await indexer.index_object(
        db_session,
        workspace_id=ws_id,
        object_type="page",
        object_id=page_id,
        project_id=proj_id,
        action="created",
    )
    assert written == 1

    # Empty body markdown removes chunks
    await db_session.execute(
        text("UPDATE pages SET body_markdown = '' WHERE id = :id"),
        {"id": page_id},
    )
    pruned = await indexer.index_object(
        db_session,
        workspace_id=ws_id,
        object_type="page",
        object_id=page_id,
        project_id=proj_id,
        action="updated",
    )
    assert pruned == 1


@pytest.mark.asyncio
async def test_missing_object_and_unsupported_kinds(
    db_session: AsyncSession,
) -> None:
    """Non-existent objects and unsupported event topics are handled cleanly."""
    ws_id, _, indexer_id, proj_id, _ = await _setup_indexer_env(db_session)
    embedder = MockDeterministicEmbedder()
    indexer = EmbeddingIndexer(embedder, indexer_principal_id=indexer_id)

    # Missing object
    res = await indexer.index_object(
        db_session,
        workspace_id=ws_id,
        object_type="issue",
        object_id=uuid.uuid4(),
        project_id=proj_id,
        action="updated",
    )
    assert res == 0

    # Unknown object type fetch returns None, None
    md, p = await indexer._fetch_object_markdown_and_project(  # noqa: SLF001
        db_session, "unknown_type", uuid.uuid4(), ws_id
    )
    assert md is None
    assert p is None

    # Unsupported object topic (e.g. user.created)
    user_event = {
        "id": uuid.uuid4(),
        "topic": "user.created",
        "workspace_id": ws_id,
        "payload": {"object_id": uuid.uuid4()},
    }
    assert await indexer.process_event(db_session, user_event) is True

    # Successful process_event covers lines 358-359
    good_event = {
        "id": uuid.uuid4(),
        "topic": "doc.created",
        "workspace_id": ws_id,
        "payload": {"object_id": uuid.uuid4(), "project_id": proj_id},
    }
    with patch.object(indexer, "index_object", return_value=1):
        assert await indexer.process_event(db_session, good_event) is True

    # None object_id
    none_event = {
        "id": uuid.uuid4(),
        "topic": "issue.updated",
        "workspace_id": ws_id,
        "object_id": None,
    }
    assert await indexer.process_event(db_session, none_event) is True


@pytest.mark.asyncio
async def test_process_batch_resilience(
    db_session: AsyncSession,
) -> None:
    """Batch processing continues despite individual event failures."""
    ws_id, admin_id, indexer_id, proj_id, _ = await _setup_indexer_env(db_session)
    iss_id = await _create_test_issue(db_session, ws_id, proj_id, admin_id, "Good Issue")

    embedder = MockDeterministicEmbedder()
    indexer = EmbeddingIndexer(embedder, indexer_principal_id=indexer_id)

    event_ok = {
        "id": uuid.uuid4(),
        "topic": "issue.created",
        "workspace_id": ws_id,
        "payload": {"object_id": iss_id, "project_id": proj_id},
    }

    # Bad event with a failing embedder call mocked
    event_bad = {
        "id": uuid.uuid4(),
        "topic": "issue.created",
        "workspace_id": ws_id,
        "payload": {"object_id": uuid.uuid4(), "project_id": proj_id},
    }

    batch_effects = [True, RuntimeError("Simulated event error"), True]
    with patch.object(indexer, "process_event", side_effect=batch_effects):
        res = await indexer.process_batch(db_session, [event_ok, event_bad, event_ok])
        assert res == [True, False, True]


@pytest.mark.asyncio
async def test_principal_resolution_and_context_binding(
    db_session: AsyncSession,
) -> None:
    """Test principal resolution caching, query, and context fallback."""
    ws_id, _, indexer_id, _, _ = await _setup_indexer_env(db_session)
    embedder = MockDeterministicEmbedder()
    indexer = EmbeddingIndexer(embedder, indexer_principal_id=None)

    # 1. Resolve via DB
    resolved_id = await indexer._resolve_indexer_principal_id(db_session, ws_id)  # noqa: SLF001
    assert resolved_id == indexer_id

    # 2. Resolve via cache
    resolved_cached = await indexer._resolve_indexer_principal_id(db_session, ws_id)  # noqa: SLF001
    assert resolved_cached == indexer_id

    # 3. Context binding fallback
    err = RLSContextError("fallback")
    with patch("agent.embeddings.indexer.bind_rls_context", side_effect=err):
        await indexer._bind_context(db_session, ws_id, indexer_id)  # noqa: SLF001

    # 4. Fallback to app_embedding_indexer_principal()
    empty_ws_id = uuid.uuid4()
    with patch.object(db_session, "execute") as mock_exec:
        # First call returns None, second call returns function result
        mock_res1 = MagicMock()
        mock_res1.scalar_one_or_none.return_value = None

        fn_uuid = uuid.uuid4()
        mock_res2 = MagicMock()
        mock_res2.scalar_one_or_none.return_value = fn_uuid

        mock_exec.side_effect = [mock_res1, mock_res2]
        indexer_dyn = EmbeddingIndexer(embedder, indexer_principal_id=None)
        res_fn = await indexer_dyn._resolve_indexer_principal_id(db_session, empty_ws_id)  # noqa: SLF001
        assert res_fn == fn_uuid

    # 5. Principal not found raises RuntimeError
    with patch.object(db_session, "execute") as mock_exec:
        mock_res = MagicMock()
        mock_res.scalar_one_or_none.return_value = None
        mock_exec.side_effect = [mock_res, mock_res]
        indexer_dyn = EmbeddingIndexer(embedder, indexer_principal_id=None)
        with pytest.raises(RuntimeError) as exc_info:
            await indexer_dyn._resolve_indexer_principal_id(db_session, empty_ws_id)  # noqa: SLF001
        assert "svc-embedding-indexer principal not found" in str(exc_info.value)


def test_chunk_markdown_edge_cases() -> None:
    """Test chunk_markdown with edge case parameters."""
    assert chunk_markdown("") == []
    assert chunk_markdown("small", chunk_size=100) == ["small"]

    # Overlap equals chunk size forces positive step fallback
    chunks = chunk_markdown("ABCDEFGHIJ", chunk_size=4, overlap=4)
    assert len(chunks) == 3
    assert chunks[0] == "ABCD"
    assert chunks[1] == "EFGH"
    assert chunks[2] == "IJ"


def test_extract_event_fields_helper() -> None:
    """Test _extract_event_fields with object having attributes and fallback dict."""
    ev_id = uuid.uuid4()
    ws_id = uuid.uuid4()
    obj_id = uuid.uuid4()

    class _MockEvent:
        def __init__(self) -> None:
            self.id = ev_id
            self.topic = "doc.updated"
            self.workspace_id = ws_id
            self.object_id = obj_id
            self.project_id = None
            self.payload: dict[str, Any] = {}

    ev_obj = _MockEvent()
    eid, top, wid, oid, pid = _extract_event_fields(ev_obj)
    assert eid == ev_id
    assert top == "doc.updated"
    assert wid == ws_id
    assert oid == obj_id
    assert pid is None
