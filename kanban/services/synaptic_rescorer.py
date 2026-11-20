# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Synaptic object-graph rescoring, Matryoshka quantization, and activation spreading.

Implements KAN-20: Zero-Egress Synaptic Object-Graph Semantic Search.
Provides int8 quantization, Matryoshka head extraction, exact identifier MaxSim boosting,
Reciprocal Rank Fusion (RRF), and 2-hop RLS-governed synaptic activation spreading.
"""

from __future__ import annotations

import datetime as dt
import math
import re
import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Final

import numpy as np
from sqlalchemy import text

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy.ext.asyncio import AsyncSession

    from kanban.api.deps import PrincipalContext

__all__ = [
    "ACTIVE_LINK_WEIGHTS",
    "EmbeddedChunkPayload",
    "MatryoshkaQuantizer",
    "SynapticActivationResult",
    "SynapticSeed",
    "compute_binary_sign",
    "dequantize_int8",
    "exact_identifier_heading_maxsim",
    "extract_heading_anchors",
    "extract_matryoshka_head",
    "int8_dot_product",
    "quantize_int8",
    "reciprocal_rank_fusion",
    "spread_synaptic_activation",
]

# Typed active link activation weights
ACTIVE_LINK_WEIGHTS: Final[dict[str, float]] = {
    "VERIFIED_BY_DOC": 0.85,
    "BLOCKS": 0.75,
    "BLOCKED_BY": 0.75,
    "PARENT_OF": 0.70,
    "PROMOTED_TO_DOC": 0.65,
    "DERIVED_FROM_STICKY": 0.65,
    "RELATES_TO": 0.45,
}

_WORD_TOKEN_RE: Final[re.Pattern[str]] = re.compile(r"[A-Za-z0-9_-]+")
_HEADING_LINE_RE: Final[re.Pattern[str]] = re.compile(r"^(#{1,6})\s+(.+?)(?:\s+#+)?$")
_RECENCY_HALF_LIFE_DAYS: Final[float] = 30.0
_RECENCY_DECAY_LAMBDA: Final[float] = math.log(2.0) / _RECENCY_HALF_LIFE_DAYS
_HOP_ATTENUATION: Final[float] = 0.5
_NORM_EPSILON: Final[float] = 1e-12
_MIN_TOKEN_LEN: Final[int] = 2
_RATIO_THRESHOLD: Final[float] = 0.5


@dataclass(frozen=True, slots=True)
class EmbeddedChunkPayload:
    """Rich embedding payload containing full vector, Matryoshka head, and int8 quantization."""

    embedding: list[float]
    head_128: list[float]
    binary_sign: bytes
    full_q8: bytes
    q8_scale: float
    heading_anchors: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class SynapticSeed:
    """Seed entity for synaptic activation spreading."""

    object_id: uuid.UUID
    object_type: str
    score: float
    key: str | None = None
    title: str = ""
    had_semantic_match: bool = False
    had_lexical_match: bool = False


@dataclass(frozen=True, slots=True)
class SynapticActivationResult:
    """Result of synaptic spreading for a graph node."""

    object_id: uuid.UUID
    object_type: str
    activation_score: float
    match_reason: str
    key: str | None = None
    title: str = ""
    hop_distance: int = 0
    via_link_type: str | None = None
    connected_to_key: str | None = None


def extract_matryoshka_head(vec: Sequence[float], dim: int = 128) -> list[float]:
    """Extract and L2-normalize the first dim components of an embedding vector."""
    arr = np.asarray(vec[:dim], dtype=np.float32)
    norm = float(np.linalg.norm(arr))
    arr = arr / norm if norm > _NORM_EPSILON else np.zeros_like(arr)
    return [float(x) for x in arr.tolist()]


def compute_binary_sign(vec: Sequence[float], dim: int = 128) -> bytes:
    """Pack signs of first dim dimensions into 1-bit per element bytes."""
    arr = np.asarray(vec[:dim], dtype=np.float32)
    bits = (arr > 0).astype(np.uint8)
    if len(bits) < dim:
        padded = np.zeros(dim, dtype=np.uint8)
        padded[: len(bits)] = bits
        bits = padded
    packed = np.packbits(bits)
    return packed.tobytes()


def quantize_int8(vec: Sequence[float]) -> tuple[bytes, float]:
    """Quantize float32 vector to signed int8 and return payload bytes and scale factor."""
    arr = np.asarray(vec, dtype=np.float32)
    if len(arr) == 0:
        return b"", 1.0
    max_val = float(np.max(np.abs(arr)))
    scale = max_val / 127.0 if max_val > _NORM_EPSILON else 1.0
    q8 = np.clip(np.round(arr / scale), -128, 127).astype(np.int8)
    return q8.tobytes(), float(scale)


def dequantize_int8(payload: bytes | np.ndarray, scale: float) -> list[float]:
    """Reconstruct float32 vector approximation from int8 payload and scale factor."""
    if isinstance(payload, bytes):
        arr = np.frombuffer(payload, dtype=np.int8).astype(np.float32)
    else:
        arr = payload.astype(np.float32)
    result = arr * scale
    return [float(x) for x in result.tolist()]


def int8_dot_product(
    q8_a: bytes | np.ndarray,
    scale_a: float,
    q8_b: bytes | np.ndarray,
    scale_b: float,
) -> float:
    """Compute dot product in integer arithmetic scaled back to float32 under 2ms."""
    arr_a = np.frombuffer(q8_a, dtype=np.int8) if isinstance(q8_a, bytes) else q8_a
    arr_b = np.frombuffer(q8_b, dtype=np.int8) if isinstance(q8_b, bytes) else q8_b

    min_len = min(len(arr_a), len(arr_b))
    if min_len == 0:
        return 0.0

    raw_dot = int(np.dot(arr_a[:min_len].astype(np.int32), arr_b[:min_len].astype(np.int32)))
    return float(raw_dot) * float(scale_a) * float(scale_b)


def extract_heading_anchors(markdown_text: str) -> list[dict[str, Any]]:
    """Extract micro-span heading anchor metadata from markdown source text."""
    headings: list[dict[str, Any]] = []
    if not markdown_text:
        return headings

    current_offset = 0
    for line in markdown_text.splitlines(keepends=True):
        stripped = line.strip()
        m = _HEADING_LINE_RE.match(stripped)
        if m:
            level = len(m.group(1))
            title = m.group(2).strip()
            slug = re.sub(r"[^\w\s-]", "", title.lower()).strip()
            slug = re.sub(r"[\s-]+", "-", slug).strip("-") or "section"
            anchor = f"#{slug}"
            start_char = current_offset
            end_char = current_offset + len(line)
            headings.append(
                {
                    "level": level,
                    "title": title,
                    "anchor": anchor,
                    "start_char": start_char,
                    "end_char": end_char,
                }
            )
        current_offset += len(line)
    return headings


def exact_identifier_heading_maxsim(
    query: str,
    title: str,
    headings: Sequence[str] | None = None,
    identifier: str | None = None,
) -> float:
    """Compute MaxSim token similarity boost and exact key match boost."""
    clean_q = query.strip().upper()
    if not clean_q:
        return 0.0

    boost = 0.0
    clean_ident = (identifier or "").strip().upper()
    if clean_ident and (clean_q == clean_ident or clean_ident in clean_q or clean_q in clean_ident):
        boost += 10.0

    q_tokens = [t.lower() for t in _WORD_TOKEN_RE.findall(query) if len(t) >= _MIN_TOKEN_LEN]
    if not q_tokens:
        return boost

    candidate_texts: list[str] = [title]
    if headings:
        candidate_texts.extend(headings)

    cand_tokens: set[str] = set()
    for txt in candidate_texts:
        for t in _WORD_TOKEN_RE.findall(txt):
            cand_tokens.add(t.lower())

    if not cand_tokens:
        return boost

    matches = sum(1 for q in q_tokens if q in cand_tokens)
    ratio = matches / len(q_tokens)
    if ratio >= _RATIO_THRESHOLD:
        boost += ratio * 2.0

    return boost


def reciprocal_rank_fusion(
    ranked_lists: Sequence[Sequence[uuid.UUID]],
    k: int = 60,
) -> dict[uuid.UUID, float]:
    """Fuse multiple candidate ranking lists via Reciprocal Rank Fusion: 1 / (k + rank)."""
    scores: dict[uuid.UUID, float] = {}
    for r_list in ranked_lists:
        for rank_0, obj_id in enumerate(r_list):
            rank_1 = rank_0 + 1
            scores[obj_id] = scores.get(obj_id, 0.0) + (1.0 / (k + rank_1))
    return scores


class MatryoshkaQuantizer:
    """Convenience namespace for Matryoshka embeddings and int8 quantization operations."""

    @staticmethod
    def extract_head(vec: Sequence[float], dim: int = 128) -> list[float]:
        """Extract L2-normalized Matryoshka head vector."""
        return extract_matryoshka_head(vec, dim)

    @staticmethod
    def binary_sign(vec: Sequence[float], dim: int = 128) -> bytes:
        """Extract packed binary sign bits for Matryoshka head."""
        return compute_binary_sign(vec, dim)

    @staticmethod
    def quantize(vec: Sequence[float]) -> tuple[bytes, float]:
        """Quantize full dimension vector to int8 payload and scale."""
        return quantize_int8(vec)

    @staticmethod
    def dequantize(payload: bytes | np.ndarray, scale: float) -> list[float]:
        """Dequantize int8 payload back to float32 representation."""
        return dequantize_int8(payload, scale)

    @staticmethod
    def dot_product(
        q8_a: bytes | np.ndarray,
        scale_a: float,
        q8_b: bytes | np.ndarray,
        scale_b: float,
    ) -> float:
        """Fast int8 dot product rescoring under 2ms."""
        return int8_dot_product(q8_a, scale_a, q8_b, scale_b)

    @staticmethod
    def maxsim_boost(
        query: str,
        title: str,
        headings: Sequence[str] | None = None,
        identifier: str | None = None,
    ) -> float:
        """Compute exact key and heading MaxSim similarity boost."""
        return exact_identifier_heading_maxsim(query, title, headings, identifier)

    @staticmethod
    def rrf(ranked_lists: Sequence[Sequence[uuid.UUID]], k: int = 60) -> dict[uuid.UUID, float]:
        """Reciprocal Rank Fusion over candidate rankings."""
        return reciprocal_rank_fusion(ranked_lists, k)


def _compute_recency_decay(updated_at: dt.datetime | None) -> float:
    """Compute exponential recency decay factor bounded between 0.1 and 1.0."""
    if not updated_at:
        return 0.5
    now = dt.datetime.now(dt.UTC)
    if updated_at.tzinfo is None:
        updated_at = updated_at.replace(tzinfo=dt.UTC)
    delta_days = max(0.0, (now - updated_at).total_seconds() / 86400.0)
    decay = math.exp(-_RECENCY_DECAY_LAMBDA * delta_days)
    return max(0.1, min(1.0, decay))


async def spread_synaptic_activation(  # noqa: C901
    session: AsyncSession,
    caller: PrincipalContext,
    seeds: list[SynapticSeed],
    workspace_id: uuid.UUID,
    max_hops: int = 2,
) -> dict[uuid.UUID, SynapticActivationResult]:
    """Propagate activation across ACTIVE typed object_links with strict FORCE RLS check.

    Unauthorized neighbors (not matching allow_mask & 1 = 1 and deny_mask & 1 = 0 in ERA)
    contribute 0.0 activation and are pruned immediately (zero oracle leakage).
    """
    results: dict[uuid.UUID, SynapticActivationResult] = {}
    if not seeds:
        return results

    await session.execute(
        text(
            "SELECT set_config('app.principal_id', :p_id, true), "
            "       set_config('app.workspace_id', :ws_id, true)"
        ),
        {"p_id": str(caller.principal_id), "ws_id": str(workspace_id)},
    )

    # Record direct seed matches
    for s in seeds:
        if (s.had_semantic_match and s.had_lexical_match) or s.had_semantic_match:
            reason = "Semantic match"
        else:
            reason = "Lexical match"

        results[s.object_id] = SynapticActivationResult(
            object_id=s.object_id,
            object_type=s.object_type,
            activation_score=s.score,
            match_reason=reason,
            key=s.key,
            title=s.title,
            hop_distance=0,
        )

    current_frontier: list[tuple[uuid.UUID, float, str | None, str | None]] = [
        (s.object_id, s.score, s.key or s.title, None) for s in seeds[:20]
    ]
    visited_ids: set[uuid.UUID] = {s.object_id for s in seeds}

    for hop in range(1, max_hops + 1):
        if not current_frontier:
            break

        frontier_ids = [item[0] for item in current_frontier]
        frontier_map = {item[0]: (item[1], item[2]) for item in current_frontier}

        # Query active links and enforce RLS-equivalent ERA authorization in PostgreSQL
        query = text(
            "SELECT "
            "  ol.source_id, "
            "  CAST(ol.source_type AS text) AS source_type, "
            "  ol.target_id, "
            "  CAST(ol.target_type AS text) AS target_type, "
            "  CAST(ol.link_type AS text) AS link_type, "
            "  ol.source_key_snapshot, "
            "  ol.target_key_snapshot, "
            "  obj.id AS neighbor_id, "
            "  CAST(obj.object_type AS text) AS neighbor_type, "
            "  obj.canonical_key, "
            "  obj.display_title AS title, "
            "  obj.updated_at "
            "FROM object_links ol "
            "JOIN objects obj ON obj.id = CASE "
            "  WHEN ol.source_id = ANY(CAST(:f_ids AS uuid[])) THEN ol.target_id "
            "  ELSE ol.source_id "
            "END "
            "WHERE (ol.source_id = ANY(CAST(:f_ids AS uuid[])) "
            "       OR ol.target_id = ANY(CAST(:f_ids AS uuid[]))) "
            "  AND ol.workspace_id = :ws_id "
            "  AND ol.link_state = 'ACTIVE' "
            "  AND obj.deleted_at IS NULL "
            "  AND obj.archived_at IS NULL "
            "  AND EXISTS ( "
            "    SELECT 1 FROM effective_resource_access era "
            "    WHERE era.object_id = obj.id "
            "      AND era.principal_id = ANY(app_effective_principal_set()) "
            "      AND (era.allow_mask & 1) = 1 "
            "      AND (era.deny_mask & 1) = 0 "
            "  )"
        )

        rows = (
            await session.execute(
                query,
                {"f_ids": frontier_ids, "ws_id": workspace_id},
            )
        ).all()

        next_frontier: list[tuple[uuid.UUID, float, str | None, str | None]] = []

        for row in rows:
            src_id = uuid.UUID(str(row[0]))
            tgt_id = uuid.UUID(str(row[2]))
            link_type_str = str(row[4])
            src_key = str(row[5])
            tgt_key = str(row[6])
            n_id = uuid.UUID(str(row[7]))
            n_type = str(row[8])
            n_key = str(row[9]) if row[9] else None
            n_title = str(row[10]) if row[10] else ""
            n_updated_at = row[11]

            parent_id = src_id if n_id == tgt_id else tgt_id
            parent_info = frontier_map.get(parent_id)
            if not parent_info:
                continue

            parent_score, parent_label = parent_info
            link_weight = ACTIVE_LINK_WEIGHTS.get(link_type_str, 0.0)
            if link_weight <= 0.0:
                continue

            recency = _compute_recency_decay(n_updated_at)
            propagated_score = parent_score * link_weight * _HOP_ATTENUATION * recency

            if n_id not in visited_ids:
                visited_ids.add(n_id)
                display_label = parent_label or (src_key if n_id == tgt_id else tgt_key)
                match_reason = f"Linked via {link_type_str} to {display_label}"

                results[n_id] = SynapticActivationResult(
                    object_id=n_id,
                    object_type=n_type,
                    activation_score=propagated_score,
                    match_reason=match_reason,
                    key=n_key,
                    title=n_title,
                    hop_distance=hop,
                    via_link_type=link_type_str,
                    connected_to_key=display_label,
                )
                next_frontier.append((n_id, propagated_score, n_key or n_title, link_type_str))
            else:
                # Add supplemental activation bonus if already known
                prev = results.get(n_id)
                if prev is not None and prev.hop_distance > 0:
                    combined_score = prev.activation_score + (propagated_score * 0.5)
                    results[n_id] = SynapticActivationResult(
                        object_id=prev.object_id,
                        object_type=prev.object_type,
                        activation_score=combined_score,
                        match_reason=prev.match_reason,
                        key=prev.key,
                        title=prev.title,
                        hop_distance=prev.hop_distance,
                        via_link_type=prev.via_link_type,
                        connected_to_key=prev.connected_to_key,
                    )

        current_frontier = next_frontier

    return results
