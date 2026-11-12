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
"""Exhaustive unit tests for Sparkle context retrieval under app_rls_reader."""

from __future__ import annotations

import hashlib
import uuid
from typing import TYPE_CHECKING, Self
from unittest.mock import MagicMock

import pytest
from sqlalchemy import text

from agent.sparkle.retrieval import _is_timeout_error, retrieve_context
from database.session import RLSSessionFactory
from kanban.api.deps import PrincipalContext

if TYPE_CHECKING:
    from types import TracebackType

    from sqlalchemy.ext.asyncio import AsyncEngine


class _MockAsyncSession:
    """Lightweight deterministic async session context manager for unit testing."""

    def __init__(
        self,
        execute_side_effect: Exception | None = None,
        execute_return_value: object = None,
    ) -> None:
        self.info: dict[str, object] = {}
        self.execute_side_effect = execute_side_effect
        self.execute_return_value = execute_return_value

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        pass

    def begin(self) -> Self:
        return self

    async def execute(self, stmt: object, params: object = None) -> object:
        del stmt, params
        if self.execute_side_effect is not None:
            raise self.execute_side_effect
        if self.execute_return_value is not None:
            return self.execute_return_value
        mock_res = MagicMock()
        mock_res.fetchall.return_value = []
        return mock_res


def test_is_timeout_error_detection() -> None:
    """Validate timeout and query cancellation error classification."""

    class QueryCanceledTestError(Exception):
        pass

    class CustomTimeoutError(Exception):
        pass

    class _WrappedError(Exception):
        orig: Exception | None = None

    assert _is_timeout_error(QueryCanceledTestError("canceled")) is True
    assert _is_timeout_error(CustomTimeoutError("timed out")) is True

    wrapped_timeout = _WrappedError("wrapped")
    wrapped_timeout.orig = CustomTimeoutError("inner")
    assert _is_timeout_error(wrapped_timeout) is True

    class SqlstateError(Exception):
        sqlstate = "57014"

    wrapped_sqlstate = _WrappedError("wrapped sqlstate")
    wrapped_sqlstate.orig = SqlstateError("57014 canceled")
    assert _is_timeout_error(wrapped_sqlstate) is True

    assert (
        _is_timeout_error(Exception("ERROR: canceling statement due to statement timeout")) is True
    )
    assert _is_timeout_error(Exception("DB query_canceled by administrator")) is True
    assert _is_timeout_error(ValueError("invalid parameter")) is False


@pytest.mark.asyncio
async def test_retrieve_context_none_factory() -> None:
    """retrieve_context returns ([], 'skipped') when session_factory is None."""
    p_ctx = PrincipalContext(principal_id=uuid.uuid4(), workspace_id=uuid.uuid4())
    snippets, status = await retrieve_context(
        project_id=uuid.uuid4(),
        query_vector=[0.1] * 384,
        principal_ctx=p_ctx,
        session_factory=None,
    )
    assert snippets == []
    assert status == "skipped"


@pytest.mark.asyncio
async def test_retrieve_context_session_factory_flavors() -> None:
    """retrieve_context supports sessionmaker, callable, or direct session object."""
    p_ctx = PrincipalContext(principal_id=uuid.uuid4(), workspace_id=uuid.uuid4())

    holder = MagicMock()
    holder.sessionmaker.return_value = _MockAsyncSession()
    snippets, status = await retrieve_context(
        project_id=uuid.uuid4(),
        query_vector=[0.1] * 384,
        principal_ctx=p_ctx,
        session_factory=holder,
    )
    assert snippets == []
    assert status == "empty"

    snippets2, status2 = await retrieve_context(
        project_id=uuid.uuid4(),
        query_vector=[0.1] * 384,
        principal_ctx=p_ctx,
        session_factory=_MockAsyncSession,
    )
    assert snippets2 == []
    assert status2 == "empty"

    snippets3, status3 = await retrieve_context(
        project_id=uuid.uuid4(),
        query_vector=[0.1] * 384,
        principal_ctx=p_ctx,
        session_factory=_MockAsyncSession(),
    )
    assert snippets3 == []
    assert status3 == "empty"


@pytest.mark.asyncio
async def test_retrieve_context_all_object_types_and_scrubbing(pg_worker_db: AsyncEngine) -> None:
    """Verify issues, docs, stickies, and pages dispatch with secret scrubbing and char capping."""
    ws_id = uuid.uuid4()
    user_id = uuid.uuid4()
    session_factory = RLSSessionFactory(pg_worker_db)

    async with pg_worker_db.begin() as conn:
        await conn.execute(
            text("INSERT INTO workspaces (id, slug, name) VALUES (:id, :slug, 'WS')"),
            {"id": ws_id, "slug": f"ws-{ws_id.hex[:10]}"},
        )
        await conn.execute(
            text(
                "SELECT register_object("
                "  'user'::object_kind, :ws_id, NULL, :ckey, 'Alice', :user_id, :user_id"
                ")"
            ),
            {"ws_id": ws_id, "ckey": f"user-{user_id.hex[:8]}", "user_id": user_id},
        )
        await conn.execute(
            text(
                "INSERT INTO principals (id, workspace_id, principal_type, display_name) "
                "VALUES (:id, :ws_id, 'USER', 'Alice')"
            ),
            {"id": user_id, "ws_id": ws_id},
        )
        await conn.execute(
            text("INSERT INTO users (id, workspace_id, email) VALUES (:id, :ws_id, :email)"),
            {"id": user_id, "ws_id": ws_id, "email": f"alice-{user_id.hex[:6]}@example.com"},
        )

        proj_id = await conn.scalar(
            text(
                "SELECT register_object("
                "  'project'::object_kind, :ws_id, NULL, 'PRJ', 'Project', :creator"
                ")"
            ),
            {"ws_id": ws_id, "creator": user_id},
        )
        assert isinstance(proj_id, uuid.UUID)
        await conn.execute(
            text(
                "INSERT INTO projects (id, workspace_id, identifier, name) "
                "VALUES (:id, :ws, 'PRJ', 'Project')"
            ),
            {"id": proj_id, "ws": ws_id},
        )
        await conn.execute(
            text(
                "INSERT INTO role_bindings "
                "(workspace_id, principal_id, role, scope_type, project_id) "
                "VALUES (:ws_id, :p_id, 'MEMBER', 'project', :proj_id)"
            ),
            {"ws_id": ws_id, "p_id": user_id, "proj_id": proj_id},
        )

        state_id = await conn.scalar(
            text(
                "SELECT id FROM workflow_states "
                "WHERE project_id = :pid AND is_default = true LIMIT 1"
            ),
            {"pid": proj_id},
        )
        prio_id = await conn.scalar(
            text(
                "SELECT id FROM project_priorities "
                "WHERE project_id = :pid AND is_default = true LIMIT 1"
            ),
            {"pid": proj_id},
        )

        secret_part = "ghp_" + ("A1b2C3d4" * 5)
        seq_id = await conn.scalar(
            text("SELECT allocate_issue_sequence(:pid)"),
            {"pid": proj_id},
        )
        issue_id = await conn.scalar(
            text(
                "SELECT register_object("
                "  'issue'::object_kind, :ws_id, :proj_id, :ckey, 'Issue 1', :creator"
                ")"
            ),
            {"ws_id": ws_id, "proj_id": proj_id, "ckey": f"PRJ-{seq_id}", "creator": user_id},
        )
        assert isinstance(issue_id, uuid.UUID)
        await conn.execute(
            text(
                "INSERT INTO issues ("
                "  id, workspace_id, project_id, sequence_id, summary, description_markdown, "
                "  state_id, priority_id, created_by_id, ancestry_path, board_rank"
                ") VALUES ("
                "  :id, :ws, :proj, :seq, 'Issue 1', :body, "
                "  :state_id, :prio_id, :creator, :ancestry, '0|hzzzzz:'"
                ")"
            ),
            {
                "id": issue_id,
                "ws": ws_id,
                "proj": proj_id,
                "seq": seq_id,
                "body": f"Auth token is {secret_part} here",
                "state_id": state_id,
                "prio_id": prio_id,
                "creator": user_id,
                "ancestry": str(seq_id),
            },
        )

        doc_id = uuid.uuid4()
        long_body = "Doc chunk text " + ("word " * 120)
        await conn.execute(
            text(
                "SELECT register_object("
                "  'doc'::object_kind, :ws_id, :proj_id, 'PRJ-DOC-1', 'Doc 1', :creator, :id"
                ")"
            ),
            {"ws_id": ws_id, "proj_id": proj_id, "creator": user_id, "id": doc_id},
        )
        await conn.execute(
            text(
                "INSERT INTO docs (id, workspace_id, project_id, title, body_markdown) "
                "VALUES (:id, :ws, :proj, 'Doc 1', :body)"
            ),
            {"id": doc_id, "ws": ws_id, "proj": proj_id, "body": long_body},
        )

        sticky_id = uuid.uuid4()
        await conn.execute(
            text(
                "SELECT register_object("
                "  'sticky'::object_kind, :ws_id, :proj_id, 'PRJ-STK-1', 'Sticky 1', :creator, :id"
                ")"
            ),
            {"ws_id": ws_id, "proj_id": proj_id, "creator": user_id, "id": sticky_id},
        )
        await conn.execute(
            text(
                "INSERT INTO stickies (id, workspace_id, project_id, body_markdown) "
                "VALUES (:id, :ws, :proj, 'Sticky note details')"
            ),
            {"id": sticky_id, "ws": ws_id, "proj": proj_id},
        )

        page_id = uuid.uuid4()
        await conn.execute(
            text(
                "SELECT register_object("
                "  'page'::object_kind, :ws_id, :proj_id, 'PRJ-PG-1', 'Page 1', :creator, :id"
                ")"
            ),
            {"ws_id": ws_id, "proj_id": proj_id, "creator": user_id, "id": page_id},
        )
        await conn.execute(
            text(
                "INSERT INTO pages ("
                "  id, workspace_id, doc_id, title, body_markdown, hierarchy_path"
                ") VALUES ("
                "  :id, :ws, :doc_id, 'Page 1', 'Page architecture text', CAST(:hpath AS ltree)"
                ")"
            ),
            {"id": page_id, "ws": ws_id, "doc_id": doc_id, "hpath": page_id.hex},
        )

        vec_str = "[" + ",".join("0.0" for _ in range(384)) + "]"
        for obj_id, otype in [
            (issue_id, "issue"),
            (doc_id, "doc"),
            (sticky_id, "sticky"),
            (page_id, "page"),
        ]:
            h = hashlib.sha256(str(obj_id).encode()).digest()
            await conn.execute(
                text(
                    "INSERT INTO object_embeddings ("
                    "  object_id, object_type, chunk_index, workspace_id, "
                    "  project_id, content_sha256, model_id, embedding"
                    ") VALUES ("
                    "  :obj_id, CAST(:otype AS object_kind), 0, :ws_id, "
                    "  :proj_id, :sha, 'mock', CAST(:vec AS vector)"
                    ")"
                ),
                {
                    "obj_id": obj_id,
                    "otype": otype,
                    "ws_id": ws_id,
                    "proj_id": proj_id,
                    "sha": h,
                    "vec": vec_str,
                },
            )

    principal_ctx = PrincipalContext(principal_id=user_id, workspace_id=ws_id)
    snippets, status = await retrieve_context(
        project_id=proj_id,
        query_vector=[0.0] * 384,
        principal_ctx=principal_ctx,
        session_factory=session_factory,
        delimiter_hex="deadbeef01234567",
    )

    assert status == "ok"
    assert len(snippets) == 4

    joined = "\n".join(snippets)
    assert "<<<UNTRUSTED_CONTEXT_deadbeef01234567>>>" in joined
    assert secret_part not in joined
    assert "[REDACTED:GITHUB_TOKEN]" in joined
    doc_snippet = next(s for s in snippets if "Doc chunk text" in s)
    content_lines = doc_snippet.strip().split("\n")[1:-1]
    raw_content = "\n".join(content_lines)
    assert len(raw_content) <= 400


@pytest.mark.asyncio
async def test_retrieve_context_skips_unknown_types_and_missing_rows(
    pg_worker_db: AsyncEngine,
) -> None:
    """Verify non-document object_kinds, missing rows, and out-of-range chunks are skipped."""
    ws_id = uuid.uuid4()
    user_id = uuid.uuid4()
    session_factory = RLSSessionFactory(pg_worker_db)

    async with pg_worker_db.begin() as conn:
        await conn.execute(
            text("INSERT INTO workspaces (id, slug, name) VALUES (:id, :slug, 'WS2')"),
            {"id": ws_id, "slug": f"ws-{ws_id.hex[:10]}"},
        )
        await conn.execute(
            text(
                "INSERT INTO principals (id, workspace_id, principal_type, display_name) "
                "VALUES (:id, :ws_id, 'USER', 'Bob')"
            ),
            {"id": user_id, "ws_id": ws_id},
        )
        proj_id = await conn.scalar(
            text(
                "SELECT register_object("
                "  'project'::object_kind, :ws_id, NULL, 'PRJ2', 'Project2', :creator"
                ")"
            ),
            {"ws_id": ws_id, "creator": user_id},
        )
        assert isinstance(proj_id, uuid.UUID)
        await conn.execute(
            text(
                "INSERT INTO projects (id, workspace_id, identifier, name) "
                "VALUES (:id, :ws, 'PRJ2', 'Project2')"
            ),
            {"id": proj_id, "ws": ws_id},
        )
        await conn.execute(
            text(
                "INSERT INTO role_bindings "
                "(workspace_id, principal_id, role, scope_type, project_id) "
                "VALUES (:ws_id, :p_id, 'MEMBER', 'project', :proj_id)"
            ),
            {"ws_id": ws_id, "p_id": user_id, "proj_id": proj_id},
        )

        vec_str = "[" + ",".join("0.0" for _ in range(384)) + "]"

        # 1. Non-document object_kind (use proj_id which is registered in objects as 'project')
        await conn.execute(
            text(
                "INSERT INTO object_embeddings ("
                "  object_id, object_type, chunk_index, workspace_id, "
                "  project_id, content_sha256, model_id, embedding"
                ") VALUES ("
                "  :obj_id, 'project'::object_kind, 0, :ws_id, "
                "  :proj_id, :sha, 'mock', CAST(:vec AS vector)"
                ")"
            ),
            {
                "obj_id": proj_id,
                "ws_id": ws_id,
                "proj_id": proj_id,
                "sha": b"x" * 32,
                "vec": vec_str,
            },
        )

        # 2. Missing base table row (register in objects as 'doc', but omit docs row)
        missing_doc_id = await conn.scalar(
            text(
                "SELECT register_object("
                "  'doc'::object_kind, :ws_id, :proj_id, 'PRJ2-MISSING', 'Missing Doc', :creator"
                ")"
            ),
            {"ws_id": ws_id, "proj_id": proj_id, "creator": user_id},
        )
        assert isinstance(missing_doc_id, uuid.UUID)
        await conn.execute(
            text(
                "INSERT INTO object_embeddings ("
                "  object_id, object_type, chunk_index, workspace_id, "
                "  project_id, content_sha256, model_id, embedding"
                ") VALUES ("
                "  :obj_id, 'doc'::object_kind, 0, :ws_id, "
                "  :proj_id, :sha, 'mock', CAST(:vec AS vector)"
                ")"
            ),
            {
                "obj_id": missing_doc_id,
                "ws_id": ws_id,
                "proj_id": proj_id,
                "sha": b"y" * 32,
                "vec": vec_str,
            },
        )

        # 3. Existing sticky, but chunk_index out of range (5 for 1-chunk text)
        real_sticky_id = uuid.uuid4()
        await conn.execute(
            text(
                "SELECT register_object("
                "  'sticky'::object_kind, :ws_id, :proj_id, 'PRJ-STK-5', 'Sticky 5', :creator, :id"
                ")"
            ),
            {"ws_id": ws_id, "proj_id": proj_id, "creator": user_id, "id": real_sticky_id},
        )
        await conn.execute(
            text(
                "INSERT INTO stickies (id, workspace_id, project_id, body_markdown) "
                "VALUES (:id, :ws, :proj, 'Single chunk sticky')"
            ),
            {"id": real_sticky_id, "ws": ws_id, "proj": proj_id},
        )
        await conn.execute(
            text(
                "INSERT INTO object_embeddings ("
                "  object_id, object_type, chunk_index, workspace_id, "
                "  project_id, content_sha256, model_id, embedding"
                ") VALUES ("
                "  :obj_id, 'sticky'::object_kind, 5, :ws_id, "
                "  :proj_id, :sha, 'mock', CAST(:vec AS vector)"
                ")"
            ),
            {
                "obj_id": real_sticky_id,
                "ws_id": ws_id,
                "proj_id": proj_id,
                "sha": b"z" * 32,
                "vec": vec_str,
            },
        )

    principal_ctx = PrincipalContext(principal_id=user_id, workspace_id=ws_id)
    snippets, status = await retrieve_context(
        project_id=proj_id,
        query_vector=[0.0] * 384,
        principal_ctx=principal_ctx,
        session_factory=session_factory,
    )

    assert snippets == []
    assert status == "empty"


@pytest.mark.asyncio
async def test_retrieve_context_statement_timeout_and_db_error() -> None:
    """Verify statement_timeout returns 'timeout' and other DB errors return 'empty'."""
    p_ctx = PrincipalContext(principal_id=uuid.uuid4(), workspace_id=uuid.uuid4())

    class StatementTimeoutError(Exception):
        pass

    timeout_sess = _MockAsyncSession(
        execute_side_effect=StatementTimeoutError("canceling statement due to statement timeout")
    )

    snippets, status = await retrieve_context(
        project_id=uuid.uuid4(),
        query_vector=[0.0] * 384,
        principal_ctx=p_ctx,
        session_factory=timeout_sess,
    )
    assert snippets == []
    assert status == "timeout"

    error_sess = _MockAsyncSession(execute_side_effect=RuntimeError("connection pool closed"))

    snippets2, status2 = await retrieve_context(
        project_id=uuid.uuid4(),
        query_vector=[0.0] * 384,
        principal_ctx=p_ctx,
        session_factory=error_sess,
    )
    assert snippets2 == []
    assert status2 == "empty"
