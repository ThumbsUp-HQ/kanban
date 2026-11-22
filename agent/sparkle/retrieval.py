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
"""Sparkle FIM RLS-pinned 18ms context retrieval engine."""

from __future__ import annotations

import logging
import secrets
from typing import TYPE_CHECKING, Any, Final, Literal
from uuid import UUID  # noqa: TC003  # Type annotation on project_id parameter

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from agent.embeddings.indexer import chunk_markdown
from kanban.security.scrubber import outbound_secret_scrubber

if TYPE_CHECKING:
    from collections.abc import Sequence

    from database.session import RLSContext
    from kanban.api.deps import PrincipalContext

__all__ = ["retrieve_context"]

_logger = logging.getLogger(__name__)

RetrievalStatus = Literal["ok", "timeout", "empty", "skipped"]

_MAX_SNIPPET_CHARS: Final[int] = 400
_STATEMENT_TIMEOUT_SETTING: Final[str] = "SET LOCAL statement_timeout = '18ms'"


def _format_vector_literal(vector: Sequence[float]) -> str:
    """Format float sequence into a PostgreSQL pgvector literal."""
    return "[" + ",".join(f"{x:.6f}" for x in vector) + "]"


def _is_timeout_error(exc: Exception) -> bool:
    """Detect PostgreSQL statement_timeout or QueryCanceled conditions."""
    name = exc.__class__.__name__
    if "QueryCanceled" in name or "Timeout" in name:
        return True
    orig = getattr(exc, "orig", None)
    if orig is not None:
        orig_name = orig.__class__.__name__
        if "QueryCanceled" in orig_name or "Timeout" in orig_name:
            return True
        sqlstate = getattr(orig, "sqlstate", None)
        if sqlstate == "57014":  # query_canceled
            return True
    msg = str(exc).lower()
    return "query_canceled" in msg or "canceling statement due to statement timeout" in msg


async def retrieve_context(  # noqa: C901, PLR0912, PLR0915  # Database transaction and base-table dispatch
    *,
    project_id: UUID,
    query_vector: Sequence[float],
    principal_ctx: PrincipalContext | RLSContext,
    session_factory: Any,  # noqa: ANN401
    delimiter_hex: str | None = None,
) -> tuple[list[str], RetrievalStatus]:
    """Retrieve nearest context chunks under app_rls_reader within an 18ms budget.

    Security invariants:
    1. Dedicated connection executing as least-privilege role app_rls_reader.
    2. Enforces SET LOCAL TRANSACTION READ ONLY.
    3. Enforces SET LOCAL statement_timeout = '18ms'.
    4. Binds session context (principal_id, workspace_id, token_scopes, aal_level)
       strictly from the verified principal_ctx.
    5. Queries object_embeddings filtered by project_id and ordered by cosine distance.
    6. Resolves text content through RLS-protected base tables (issues, docs, stickies, pages).
    7. Catches query timeouts (statement_timeout / 57014), continuing gracefully
       with zero snippets and status 'timeout'.
    8. Caps snippets at 400 characters, re-scrubs with outbound_secret_scrubber,
       and wraps in per-request random delimiters <<<UNTRUSTED_CONTEXT_<16 hex>>>>.

    Returns:
        Tuple of (formatted_snippets, retrieval_status).

    """
    if session_factory is None:
        return [], "skipped"

    token = delimiter_hex if delimiter_hex is not None else secrets.token_hex(8)
    delimiter = f"<<<UNTRUSTED_CONTEXT_{token}>>>"

    # Acquire session instance from factory or callable
    if hasattr(session_factory, "sessionmaker"):
        session_cm = session_factory.sessionmaker()
    elif callable(session_factory):
        session_cm = session_factory()
    else:
        session_cm = session_factory

    snippets: list[str] = []

    try:
        async with session_cm as session, session.begin():
            session.info["_binding_in_progress"] = True
            try:
                # Enforce role boundary and read-only 18ms execution constraints
                await session.execute(text("SET LOCAL ROLE app_rls_reader"))
                await session.execute(text("SET LOCAL TRANSACTION READ ONLY"))
                await session.execute(text(_STATEMENT_TIMEOUT_SETTING))

                # Bind session context strictly from principal_ctx
                p_id = str(principal_ctx.principal_id)
                w_id = str(principal_ctx.workspace_id)
                scopes = ",".join(getattr(principal_ctx, "token_scopes", ()))
                aal = str(getattr(principal_ctx, "aal_level", 1))

                await session.execute(
                    text(
                        "SELECT set_config('app.principal_id', :p_id, true), "
                        "       set_config('app.workspace_id', :w_id, true), "
                        "       set_config('app.token_scopes', :scopes, true), "
                        "       set_config('app.aal_level', :aal, true)"
                    ),
                    {"p_id": p_id, "w_id": w_id, "scopes": scopes, "aal": aal},
                )
                session.info["rls_bound"] = True
            finally:
                session.info.pop("_binding_in_progress", None)

            # Enable hnsw.iterative_scan for pgvector RLS recall with safe fallback
            try:
                async with session.begin_nested():
                    await session.execute(text("SET LOCAL hnsw.iterative_scan = 'relaxed_order'"))
            except Exception:  # noqa: BLE001, S110
                pass

            # Query nearest embeddings in same project
            q_literal = _format_vector_literal(query_vector)
            knn_stmt = text(
                "SELECT object_id, CAST(object_type AS text) AS obj_type, chunk_index "
                "FROM object_embeddings "
                "WHERE project_id = :proj_id "
                "ORDER BY embedding <=> CAST(:query_vec AS vector) "
                "LIMIT 4"
            )
            result = await session.execute(
                knn_stmt,
                {"proj_id": project_id, "query_vec": q_literal},
            )
            rows = result.fetchall()

            # Fetch chunk content through RLS-protected base tables
            for row in rows:
                obj_id: UUID = row[0]
                obj_type: str = str(row[1]).lower()
                chunk_idx: int = int(row[2])

                table_query = None
                if obj_type in ("issue", "issues"):
                    table_query = text("SELECT description_markdown FROM issues WHERE id = :id")
                elif obj_type in ("doc", "docs"):
                    table_query = text("SELECT body_markdown FROM docs WHERE id = :id")
                elif obj_type in ("sticky", "stickies"):
                    table_query = text("SELECT body_markdown FROM stickies WHERE id = :id")
                elif obj_type in ("page", "pages"):
                    table_query = text("SELECT body_markdown FROM pages WHERE id = :id")

                if table_query is None:
                    continue

                base_res = await session.execute(table_query, {"id": obj_id})
                raw_markdown = base_res.scalar_one_or_none()
                if not raw_markdown:
                    continue

                chunks = chunk_markdown(raw_markdown)
                if 0 <= chunk_idx < len(chunks):
                    raw_chunk = chunks[chunk_idx]
                    capped_chunk = raw_chunk[:_MAX_SNIPPET_CHARS]
                    scrub_result = outbound_secret_scrubber(capped_chunk)
                    snippet_text = scrub_result.text
                    snippets.append(f"{delimiter}\n{snippet_text}\n{delimiter}")

    except (DBAPIError, Exception) as exc:  # noqa: BLE001  # Catching statement timeouts and driver cancellations
        if _is_timeout_error(exc):
            _logger.info("Sparkle context retrieval statement_timeout triggered (18ms budget)")
            return [], "timeout"
        _logger.warning("Sparkle context retrieval error: %s", exc)
        return [], "empty"

    status: RetrievalStatus = "ok" if snippets else "empty"
    return snippets, status
