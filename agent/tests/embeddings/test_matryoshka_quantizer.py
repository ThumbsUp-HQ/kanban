# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Unit tests for Matryoshka quantizer, int8 dot-product rescorer, and rich embedder."""

from __future__ import annotations

import math
import time
import uuid

import numpy as np
import pytest

from agent.embeddings.onnx_embedder import (
    EMBED_DIMENSION,
    FixtureEmbedder,
    OnnxBgeSmallEmbedder,
)
from agent.embeddings.quantizer import (
    MatryoshkaQuantizer,
    compute_binary_sign,
    dequantize_int8,
    exact_identifier_heading_maxsim,
    extract_heading_anchors,
    extract_matryoshka_head,
    int8_dot_product,
    quantize_int8,
    reciprocal_rank_fusion,
)


def _cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    """Compute cosine similarity between two float vectors."""
    dot = sum(a * b for a, b in zip(vec_a, vec_b, strict=True))
    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


class TestMatryoshkaQuantizer:
    """Tests for Matryoshka dimension truncation and L2 normalization."""

    def test_extract_head_standard_dim(self) -> None:
        """extract_matryoshka_head truncates to dim and L2 normalizes."""
        rng = np.random.default_rng(seed=123)
        vec = rng.standard_normal(384).tolist()

        head = extract_matryoshka_head(vec, dim=128)
        assert len(head) == 128

        # L2 norm should be 1.0 within float precision
        norm = math.sqrt(sum(x * x for x in head))
        assert math.isclose(norm, 1.0, rel_tol=1e-5)

        # Check directional alignment with prefix
        prefix_norm = math.sqrt(sum(x * x for x in vec[:128]))
        expected_head = [x / prefix_norm for x in vec[:128]]
        for a, b in zip(head, expected_head, strict=True):
            assert math.isclose(a, b, rel_tol=1e-5)

    def test_extract_head_zero_vector(self) -> None:
        """extract_matryoshka_head handles all-zero vector gracefully without division by zero."""
        zero_vec = [0.0] * 384
        head = extract_matryoshka_head(zero_vec, dim=128)
        assert len(head) == 128
        assert all(x == 0.0 for x in head)

    def test_extract_head_short_vector(self) -> None:
        """extract_matryoshka_head handles vector shorter than dim."""
        short_vec = [1.0, 2.0, 3.0]
        head = extract_matryoshka_head(short_vec, dim=128)
        assert len(head) == 3
        norm = math.sqrt(sum(x * x for x in head))
        assert math.isclose(norm, 1.0, rel_tol=1e-5)

    def test_compute_binary_sign(self) -> None:
        """compute_binary_sign produces 16 packed bytes for 128 dimensions."""
        vec = [1.0 if i % 2 == 0 else -1.0 for i in range(128)]
        packed = compute_binary_sign(vec, dim=128)
        assert len(packed) == 16

        # In numpy packbits(bits): bit 0 is MSB of first byte
        assert isinstance(packed, bytes)
        assert len(packed) == 16

    def test_compute_binary_sign_all_positive_and_all_negative(self) -> None:
        """compute_binary_sign correctly packs all-1s and all-0s."""
        pos = [0.5] * 128
        packed_pos = compute_binary_sign(pos, dim=128)
        assert packed_pos == bytes([255] * 16)

        neg = [-0.5] * 128
        packed_neg = compute_binary_sign(neg, dim=128)
        assert packed_neg == bytes([0] * 16)


class TestInt8QuantizationAndDotProduct:
    """Tests for int8 symmetric quantization, dequantization, and SIMD/vector dot product."""

    def test_quantize_and_dequantize_fidelity(self) -> None:
        """quantize_int8 and dequantize_int8 achieve > 0.999 cosine similarity."""
        rng = np.random.default_rng(seed=456)
        vec = rng.standard_normal(384).tolist()
        norm = math.sqrt(sum(x * x for x in vec))
        unit_vec = [x / norm for x in vec]

        q8_bytes, scale = quantize_int8(unit_vec)
        assert len(q8_bytes) == 384
        assert scale > 0.0

        recovered = dequantize_int8(q8_bytes, scale)
        assert len(recovered) == 384

        cos_sim = _cosine_similarity(unit_vec, recovered)
        assert cos_sim > 0.999

    def test_quantize_zero_vector(self) -> None:
        """quantize_int8 handles all-zero vector."""
        zero_vec = [0.0] * 384
        q8_bytes, scale = quantize_int8(zero_vec)
        assert len(q8_bytes) == 384
        assert scale == 1.0
        assert all(b == 0 for b in q8_bytes)
        recovered = dequantize_int8(q8_bytes, scale)
        assert all(x == 0.0 for x in recovered)

    def test_int8_dot_product_accuracy_and_latency(self) -> None:
        """int8_dot_product approximates float dot product within 0.015 and executes in < 2ms."""
        rng = np.random.default_rng(seed=789)
        vec_a = rng.standard_normal(384).tolist()
        vec_b = rng.standard_normal(384).tolist()
        norm_a = math.sqrt(sum(x * x for x in vec_a))
        norm_b = math.sqrt(sum(x * x for x in vec_b))
        unit_a = [x / norm_a for x in vec_a]
        unit_b = [x / norm_b for x in vec_b]

        expected_dot = sum(a * b for a, b in zip(unit_a, unit_b, strict=True))

        q8_a, scale_a = quantize_int8(unit_a)
        q8_b, scale_b = quantize_int8(unit_b)

        # Accuracy check
        rescored_dot = int8_dot_product(q8_a, scale_a, q8_b, scale_b)
        assert abs(rescored_dot - expected_dot) < 0.015

        # Latency check: 100 dot products must finish well within 2ms budget (< 20 us each)
        t0 = time.perf_counter()
        for _ in range(100):
            _ = int8_dot_product(q8_a, scale_a, q8_b, scale_b)
        elapsed_total = time.perf_counter() - t0
        elapsed_per_call_ms = (elapsed_total / 100) * 1000.0
        assert elapsed_per_call_ms < 2.0


class TestHeadingAnchorsAndMaxSim:
    """Tests for heading-anchor extraction and MaxSim exact boosts."""

    def test_extract_heading_anchors_markdown(self) -> None:
        """extract_heading_anchors parses headers and micro-spans accurately."""
        md = (
            "# Architecture Overview\n\n"
            "This is introduction.\n\n"
            "## Database Schema\n\n"
            "Details about tables.\n\n"
            "### Link Auditor Invariant\n\n"
            "Audit rules.\n"
        )
        anchors = extract_heading_anchors(md)
        assert len(anchors) == 3
        assert anchors[0]["level"] == 1
        assert anchors[0]["title"] == "Architecture Overview"
        assert anchors[0]["anchor"] == "#architecture-overview"

        assert anchors[1]["level"] == 2
        assert anchors[1]["title"] == "Database Schema"
        assert anchors[1]["anchor"] == "#database-schema"

        assert anchors[2]["level"] == 3
        assert anchors[2]["title"] == "Link Auditor Invariant"
        assert anchors[2]["anchor"] == "#link-auditor-invariant"

    def test_extract_heading_anchors_empty(self) -> None:
        """extract_heading_anchors handles empty or non-heading text."""
        assert extract_heading_anchors("") == []
        assert extract_heading_anchors("Just plain text with no headings.") == []

    def test_exact_identifier_heading_maxsim(self) -> None:
        """exact_identifier_heading_maxsim scores exact key matches and heading token overlap."""
        # Exact identifier match gives high boost
        boost_id = exact_identifier_heading_maxsim(
            query="KAN-20 semantic search",
            title="Semantic Search",
            headings=["Semantic Search"],
            identifier="KAN-20",
        )
        assert boost_id >= 10.0

        # Title / heading overlap gives moderate boost
        boost_title = exact_identifier_heading_maxsim(
            query="database schema",
            title="Postgres Tables",
            headings=["Database Schema"],
            identifier="KAN-21",
        )
        assert boost_title > 0.0

        # No overlap gives zero
        boost_zero = exact_identifier_heading_maxsim(
            query="completely unrelated terms",
            title="Something Else",
            headings=[],
            identifier="KAN-99",
        )
        assert boost_zero == 0.0


class TestReciprocalRankFusion:
    """Tests for Reciprocal Rank Fusion (RRF)."""

    def test_rrf_formula_and_deduplication(self) -> None:
        """reciprocal_rank_fusion fuses ranks with 1 / (60 + rank)."""
        id1 = uuid.uuid4()
        id2 = uuid.uuid4()
        id3 = uuid.uuid4()
        id4 = uuid.uuid4()

        list_a = [id1, id2, id3]
        list_b = [id2, id4, id1]

        fused = reciprocal_rank_fusion([list_a, list_b], k=60)
        # Expected scores:
        # id1: 1/(60+1) + 1/(60+3) = 1/61 + 1/63 = 0.016393 + 0.015873 = 0.032266
        # id2: 1/(60+2) + 1/(60+1) = 1/62 + 1/61 = 0.016129 + 0.016393 = 0.032522
        # id3: 1/(60+3) = 1/63 = 0.015873
        # id4: 1/(60+2) = 1/62 = 0.016129
        # id2 should have highest score
        assert fused[id2] > fused[id1]
        assert fused[id1] > fused[id4]
        assert fused[id4] > fused[id3]

    def test_rrf_empty(self) -> None:
        """reciprocal_rank_fusion handles empty rankings."""
        assert reciprocal_rank_fusion([]) == {}
        assert reciprocal_rank_fusion([[], []]) == {}


class TestFixtureEmbedderAndOnnxEmbedderRich:
    """Tests for FixtureEmbedder and OnnxBgeSmallEmbedder embed_batch_rich."""

    @pytest.mark.asyncio
    async def test_fixture_embedder_deterministic(self) -> None:
        """FixtureEmbedder returns deterministic unit vectors and rich payloads."""
        embedder = FixtureEmbedder(dimension=384)
        assert embedder.dimension == 384
        assert embedder.model_id == "fixture-bge-small-en-v1.5"

        texts = ["First chunk of text", "Second chunk of text"]
        vecs = await embedder.embed_batch(texts)
        assert len(vecs) == 2
        assert len(vecs[0]) == 384

        norm0 = math.sqrt(sum(x * x for x in vecs[0]))
        assert math.isclose(norm0, 1.0, rel_tol=1e-5)

        # Idempotency: same text yields same vector
        vecs_repeat = await embedder.embed_batch(["First chunk of text"])
        assert vecs[0] == vecs_repeat[0]

        # embed_batch_rich
        rich_payloads = await embedder.embed_batch_rich(texts)
        assert len(rich_payloads) == 2
        payload0 = rich_payloads[0]
        assert len(payload0.embedding) == 384
        assert len(payload0.head_128) == 128
        assert len(payload0.binary_sign) == 16
        assert len(payload0.full_q8) == 384
        assert payload0.q8_scale > 0.0

    @pytest.mark.asyncio
    async def test_onnx_embedder_fallback_to_fixture(self) -> None:
        """OnnxBgeSmallEmbedder with fallback_to_fixture=True runs without external dependencies."""
        embedder = OnnxBgeSmallEmbedder(fallback_to_fixture=True)
        assert embedder.dimension == EMBED_DIMENSION

        res = await embedder.embed_batch(["Test markdown # Header 1"])
        assert len(res) == 1
        assert len(res[0]) == EMBED_DIMENSION

        rich = await embedder.embed_batch_rich(["# Heading One\nContent inside here."])
        assert len(rich) == 1
        p = rich[0]
        assert len(p.head_128) == 128
        assert len(p.binary_sign) == 16
        assert len(p.heading_anchors) == 1
        assert p.heading_anchors[0]["title"] == "Heading One"

    def test_matryoshka_quantizer_helper_class(self) -> None:
        """MatryoshkaQuantizer helper class wraps methods correctly."""
        vec = [0.1] * 384
        head = MatryoshkaQuantizer.extract_head(vec, 128)
        assert len(head) == 128

        bsign = MatryoshkaQuantizer.binary_sign(head)
        assert len(bsign) == 16

        q8, scale = MatryoshkaQuantizer.quantize(vec)
        assert len(q8) == 384
        assert scale > 0.0

        recovered = MatryoshkaQuantizer.dequantize(q8, scale)
        assert len(recovered) == 384

        dot = MatryoshkaQuantizer.dot_product(q8, scale, q8, scale)
        assert isinstance(dot, float)

        u1 = uuid.uuid4()
        rrf = MatryoshkaQuantizer.rrf([[u1]], k=60)
        assert u1 in rrf

    def test_quantizer_edge_cases(self) -> None:
        """Cover quantizer padding, empty array, numpy array inputs, and mismatched lengths."""
        # Padding for binary sign when vector length < dim
        short_vec = [1.0, -1.0]
        packed = compute_binary_sign(short_vec, dim=128)
        assert len(packed) == 16

        # Empty vector quantization
        empty_q8, scale = quantize_int8([])
        assert empty_q8 == b""
        assert scale == 1.0

        # Dequantize with ndarray
        arr_in = np.array([10, -10], dtype=np.int8)
        deq = dequantize_int8(arr_in, 0.5)
        assert math.isclose(deq[0], 5.0)
        assert math.isclose(deq[1], -5.0)

        # Dot product with empty payload
        dot_empty = int8_dot_product(b"", 1.0, b"\x01", 1.0)
        assert dot_empty == 0.0

        # Dot product with ndarray inputs
        arr_a = np.array([127, 0], dtype=np.int8)
        arr_b = np.array([127, 0], dtype=np.int8)
        dot_arr = int8_dot_product(arr_a, 1.0, arr_b, 1.0)
        assert dot_arr > 0.0

    def test_exact_identifier_heading_maxsim_edge_cases(self) -> None:
        """Cover empty queries, non-word tokens, and partial ratio matches."""
        # Empty query
        assert exact_identifier_heading_maxsim("", "Title", [], "KEY-1") == 0.0

        # Query with only single-letter or non-word tokens
        assert exact_identifier_heading_maxsim("a .", "Title", [], None) == 0.0

        # Candidate text with no matching tokens
        assert exact_identifier_heading_maxsim("hello world", "", [], None) == 0.0

        # Ratio < 0.5 match (1 out of 4 tokens matches)
        boost = exact_identifier_heading_maxsim("apple banana cherry date", "apple", [], None)
        assert boost == 0.0

    @pytest.mark.asyncio
    async def test_embed_batch_empty(self) -> None:
        """embed_batch with empty text list returns empty list."""
        embedder = FixtureEmbedder()
        assert await embedder.embed_batch([]) == []
        assert await embedder.embed_batch_rich([]) == []
