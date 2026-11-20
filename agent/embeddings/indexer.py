"""Outbox-driven vector embeddings indexing worker for canonical markdown objects."""

from __future__ import annotations

import hashlib
import inspect
import json
import logging
import uuid
from typing import TYPE_CHECKING, Any, Final, cast

from sqlalchemy import text

from agent.embeddings.base import EmbedderDimensionMismatchError
from database.session import RLSContext, RLSContextError, bind_rls_context

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy.ext.asyncio import AsyncSession

    from agent.embeddings.base import Embedder

logger = logging.getLogger("agent.embeddings.indexer")

SUPPORTED_KINDS: Final[set[str]] = {"issue", "doc", "sticky", "page"}
DEFAULT_CHUNK_SIZE: Final[int] = 1500
DEFAULT_OVERLAP: Final[int] = 200
DEFAULT_MAX_CHUNKS: Final[int] = 64
MAX_ATTEMPTS: Final[int] = 5
TARGET_DIMENSION: Final[int] = 384


def chunk_markdown(
    text_content: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_OVERLAP,
    max_chunks: int = DEFAULT_MAX_CHUNKS,
) -> list[str]:
    """Slice canonical markdown into overlapping chunks capped at max_chunks."""
    if not text_content:
        return []

    chunks: list[str] = []
    step = chunk_size - overlap
    if step <= 0:
        step = chunk_size

    start = 0
    text_len = len(text_content)
    while start < text_len and len(chunks) < max_chunks:
        chunk = text_content[start : start + chunk_size]
        chunks.append(chunk)
        if start + chunk_size >= text_len:
            break
        start += step

    return chunks


def _extract_event_fields(
    event: object,
) -> tuple[uuid.UUID, str, uuid.UUID, uuid.UUID | None, uuid.UUID | None]:
    """Extract identity, routing, and payload identifiers from an outbox event."""
    event_id: uuid.UUID = getattr(event, "id", None) or uuid.UUID(str(cast("Any", event)["id"]))
    topic: str = getattr(event, "topic", None) or str(cast("Any", event)["topic"])
    workspace_id: uuid.UUID = getattr(event, "workspace_id", None) or uuid.UUID(
        str(cast("Any", event)["workspace_id"])
    )
    payload: dict[str, Any] = getattr(event, "payload", {}) or (
        cast("Any", event).get("payload", {}) if isinstance(event, dict) else {}
    )
    raw_obj = getattr(event, "object_id", None) or payload.get("object_id") or payload.get("id")
    object_id = uuid.UUID(str(raw_obj)) if raw_obj else None

    raw_proj = getattr(event, "project_id", None) or payload.get("project_id")
    project_id = uuid.UUID(str(raw_proj)) if raw_proj else None

    return event_id, topic, workspace_id, object_id, project_id


class EmbeddingIndexer:
    """Consumes outbox domain events and synchronizes vector embeddings with canonical markdown."""

    def __init__(
        self,
        embedder: Embedder,
        *,
        max_attempts: int = MAX_ATTEMPTS,
        indexer_principal_id: uuid.UUID | None = None,
    ) -> None:
        """Initialize indexer with target embedding engine and retry policy."""
        self._embedder = embedder
        self._max_attempts = max_attempts
        self._fixed_indexer_principal_id = indexer_principal_id
        self._principal_cache: dict[uuid.UUID, uuid.UUID] = {}
        self._attempts: dict[uuid.UUID, int] = {}

    async def _resolve_indexer_principal_id(
        self, session: AsyncSession, workspace_id: uuid.UUID
    ) -> uuid.UUID:
        """Resolve svc-embedding-indexer principal id for the given workspace."""
        if self._fixed_indexer_principal_id is not None:
            return self._fixed_indexer_principal_id

        if workspace_id in self._principal_cache:
            return self._principal_cache[workspace_id]

        res = await session.execute(
            text(
                "SELECT id FROM principals "
                "WHERE principal_type = 'SERVICE_PRINCIPAL' "
                "  AND display_name = 'svc-embedding-indexer' "
                "  AND workspace_id = :ws_id "
                "ORDER BY created_at ASC LIMIT 1"
            ),
            {"ws_id": workspace_id},
        )
        p_id = res.scalar_one_or_none()
        if p_id is not None:
            val = uuid.UUID(str(p_id))
            self._principal_cache[workspace_id] = val
            return val

        fn_res = await session.execute(text("SELECT app_embedding_indexer_principal()"))
        fn_id = fn_res.scalar_one_or_none()
        if fn_id is not None:
            val = uuid.UUID(str(fn_id))
            self._principal_cache[workspace_id] = val
            return val

        msg = f"svc-embedding-indexer principal not found for workspace {workspace_id}"
        raise RuntimeError(msg)

    async def _bind_context(
        self, session: AsyncSession, workspace_id: uuid.UUID, principal_id: uuid.UUID
    ) -> None:
        """Bind session RLS context variables for the indexer principal."""
        try:
            ctx = RLSContext(workspace_id=workspace_id, principal_id=principal_id)
            await bind_rls_context(session, ctx)
        except (RLSContextError, RuntimeError):
            await session.execute(
                text(
                    "SELECT set_config('app.workspace_id', :ws_id, true), "
                    "       set_config('app.principal_id', :princ_id, true)"
                ),
                {"ws_id": str(workspace_id), "princ_id": str(principal_id)},
            )

    async def _fetch_object_markdown_and_project(
        self,
        session: AsyncSession,
        object_type: str,
        object_id: uuid.UUID,
        workspace_id: uuid.UUID,
    ) -> tuple[str | None, uuid.UUID | None]:
        """Fetch canonical markdown and project association for a given object."""
        queries: dict[str, str] = {
            "issue": (
                "SELECT description_markdown, project_id FROM issues "
                "WHERE id = :obj_id AND workspace_id = :ws_id"
            ),
            "doc": (
                "SELECT body_markdown, project_id FROM docs "
                "WHERE id = :obj_id AND workspace_id = :ws_id"
            ),
            "sticky": (
                "SELECT body_markdown, project_id FROM stickies "
                "WHERE id = :obj_id AND workspace_id = :ws_id"
            ),
            "page": (
                "SELECT p.body_markdown, d.project_id "
                "FROM pages p "
                "LEFT JOIN docs d ON d.id = p.doc_id "
                "WHERE p.id = :obj_id AND p.workspace_id = :ws_id"
            ),
        }
        sql = queries.get(object_type)
        if not sql:
            return None, None

        res = await session.execute(text(sql), {"obj_id": object_id, "ws_id": workspace_id})
        row = res.one_or_none()
        if row is None:
            return None, None

        proj_id = uuid.UUID(str(row[1])) if row[1] else None
        return str(row[0]), proj_id

    async def index_object(  # noqa: C901, PLR0913
        self,
        session: AsyncSession,
        *,
        workspace_id: uuid.UUID,
        object_type: str,
        object_id: uuid.UUID,
        project_id: uuid.UUID | None = None,
        action: str = "updated",
    ) -> int:
        """Index or delete embeddings for an object based on canonical markdown state."""
        principal_id = await self._resolve_indexer_principal_id(session, workspace_id)
        await self._bind_context(session, workspace_id, principal_id)

        if action == "deleted":
            res = await session.execute(
                text(
                    "DELETE FROM object_embeddings "
                    "WHERE object_id = :obj_id AND workspace_id = :ws_id"
                ),
                {"obj_id": object_id, "ws_id": workspace_id},
            )
            raw_rc = getattr(res, "rowcount", 0)
            return int(raw_rc)

        markdown, eff_proj_id = await self._fetch_object_markdown_and_project(
            session, object_type, object_id, workspace_id
        )
        if markdown is None:
            res = await session.execute(
                text(
                    "DELETE FROM object_embeddings "
                    "WHERE object_id = :obj_id AND workspace_id = :ws_id"
                ),
                {"obj_id": object_id, "ws_id": workspace_id},
            )
            raw_rc = getattr(res, "rowcount", 0)
            return int(raw_rc)

        final_proj_id = eff_proj_id or project_id
        chunks = chunk_markdown(markdown)
        if not chunks:
            res = await session.execute(
                text(
                    "DELETE FROM object_embeddings "
                    "WHERE object_id = :obj_id AND workspace_id = :ws_id"
                ),
                {"obj_id": object_id, "ws_id": workspace_id},
            )
            raw_rc = getattr(res, "rowcount", 0)
            return int(raw_rc)

        res = await session.execute(
            text(
                "SELECT chunk_index, content_sha256, model_id FROM object_embeddings "
                "WHERE object_id = :obj_id AND workspace_id = :ws_id"
            ),
            {"obj_id": object_id, "ws_id": workspace_id},
        )
        existing: dict[int, tuple[bytes, str]] = {
            row[0]: (bytes(row[1]), str(row[2])) for row in res.all()
        }

        chunks_to_embed: list[tuple[int, str, bytes]] = []
        for idx, chunk_text in enumerate(chunks):
            sha = hashlib.sha256(chunk_text.encode("utf-8")).digest()
            prev = existing.get(idx)
            if prev is not None and prev[0] == sha and prev[1] == self._embedder.model_id:
                continue
            chunks_to_embed.append((idx, chunk_text, sha))

        writes_count = 0
        if chunks_to_embed:
            raw_texts = [c[1] for c in chunks_to_embed]
            embed_rich = getattr(self._embedder, "embed_batch_rich", None)
            if callable(embed_rich) and inspect.iscoroutinefunction(embed_rich):
                rich_payloads = await embed_rich(raw_texts)
                vectors = [p.embedding for p in rich_payloads]
            else:
                vectors = await self._embedder.embed_batch(raw_texts)

            for (idx, _, sha), vec in zip(chunks_to_embed, vectors, strict=True):
                if len(vec) != TARGET_DIMENSION:
                    msg = f"Vector dimension mismatch: expected {TARGET_DIMENSION}, got {len(vec)}"
                    raise EmbedderDimensionMismatchError(msg)

                await session.execute(
                    text(
                        "INSERT INTO object_embeddings ("
                        "  object_id, object_type, chunk_index, workspace_id, project_id, "
                        "  content_sha256, model_id, embedding, updated_at"
                        ") VALUES ("
                        "  :obj_id, CAST(:obj_type AS object_kind), :chunk_idx, :ws_id, :proj_id, "
                        "  :sha256, :model_id, CAST(:embedding AS vector), clock_timestamp()"
                        ") ON CONFLICT (object_id, chunk_index) DO UPDATE SET "
                        "  content_sha256 = EXCLUDED.content_sha256, "
                        "  model_id = EXCLUDED.model_id, "
                        "  embedding = EXCLUDED.embedding, "
                        "  updated_at = clock_timestamp()"
                    ),
                    {
                        "obj_id": object_id,
                        "obj_type": object_type,
                        "chunk_idx": idx,
                        "ws_id": workspace_id,
                        "proj_id": final_proj_id,
                        "sha256": sha,
                        "model_id": self._embedder.model_id,
                        "embedding": str(vec),
                    },
                )
                writes_count += 1

        if len(existing) > len(chunks):
            await session.execute(
                text(
                    "DELETE FROM object_embeddings "
                    "WHERE object_id = :obj_id AND workspace_id = :ws_id "
                    "  AND chunk_index >= :max_idx"
                ),
                {"obj_id": object_id, "ws_id": workspace_id, "max_idx": len(chunks)},
            )

        return writes_count

    async def process_event(self, session: AsyncSession, event: object) -> bool:
        """Process an outbox event, retrying up to max_attempts before logging failure."""
        event_id, topic, workspace_id, object_id, project_id = _extract_event_fields(event)
        if object_id is None:
            return True

        parts = topic.split(".", 1)
        object_type = parts[0]
        action = parts[1] if len(parts) > 1 else "updated"

        if object_type not in SUPPORTED_KINDS:
            return True

        try:
            await self.index_object(
                session,
                workspace_id=workspace_id,
                object_type=object_type,
                object_id=object_id,
                project_id=project_id,
                action=action,
            )
        except Exception as exc:
            self._attempts[event_id] = self._attempts.get(event_id, 0) + 1
            if self._attempts[event_id] >= self._max_attempts:
                # Poison event: log EMBEDDING_INDEX_FAILED to activity ledger and acknowledge
                principal_id = await self._resolve_indexer_principal_id(session, workspace_id)
                await self._bind_context(session, workspace_id, principal_id)
                payload = json.dumps({"event_id": str(event_id), "error": str(exc)})
                await session.execute(
                    text(
                        "SELECT append_activity("
                        "  :ws_id, :obj_id, CAST(:obj_type AS object_kind), :actor_id, "
                        "  'EMBEDDING_INDEX_FAILED', CAST(:payload AS jsonb)"
                        ")"
                    ),
                    {
                        "ws_id": workspace_id,
                        "obj_id": object_id,
                        "obj_type": object_type,
                        "actor_id": principal_id,
                        "payload": payload,
                    },
                )
                self._attempts.pop(event_id, None)
                return True
            raise
        else:
            self._attempts.pop(event_id, None)
            return True

    async def process_batch(self, session: AsyncSession, events: Sequence[object]) -> list[bool]:
        """Process a batch of events, ensuring failure of one event does not block others."""
        results: list[bool] = []
        for ev in events:
            try:
                ok = await self.process_event(session, ev)
                results.append(ok)
            except Exception:  # noqa: BLE001
                results.append(False)
        return results
