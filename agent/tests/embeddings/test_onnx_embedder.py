"""Unit tests for OnnxBgeSmallEmbedder with integrity pinning and CPU inference."""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from agent.embeddings.base import EmbedderIntegrityError
from agent.embeddings.onnx_embedder import (
    EMBED_DIMENSION,
    MAX_BATCH_SIZE,
    MAX_SEQ_LENGTH,
    MODEL_ID,
    OnnxBgeSmallEmbedder,
)

if TYPE_CHECKING:
    from pathlib import Path


class _MockEncoding:
    """Mock encoding object returned by HuggingFace Tokenizer."""

    def __init__(self, token_count: int = 600) -> None:
        self.ids = list(range(token_count))
        self.attention_mask = [1] * token_count


class _MockTokenizer:
    """Mock tokenizer returning sequences with configurable token count."""

    def __init__(self, token_count: int = 600) -> None:
        self.token_count = token_count
        self.enable_truncation_called = False
        self.enable_padding_called = False

    def enable_truncation(self, *, max_length: int) -> None:
        _ = max_length
        self.enable_truncation_called = True

    def enable_padding(self, *, length: int) -> None:
        _ = length
        self.enable_padding_called = True

    def encode_batch(self, texts: list[str]) -> list[_MockEncoding]:
        return [_MockEncoding(self.token_count) for _ in texts]


class _MockInputNode:
    """Mock ONNX node descriptor."""

    def __init__(self, name: str) -> None:
        self.name = name


class _MockInferenceSession:
    """Mock ONNX Runtime InferenceSession returning rank-3 or rank-2 hidden states."""

    def __init__(
        self,
        *,
        include_token_type: bool = True,
        rank_3: bool = True,
        all_zeros: bool = False,
    ) -> None:
        self.include_token_type = include_token_type
        self.rank_3 = rank_3
        self.all_zeros = all_zeros
        self.run_calls: list[dict[str, Any]] = []

    def get_inputs(self) -> list[_MockInputNode]:
        nodes = [_MockInputNode("input_ids"), _MockInputNode("attention_mask")]
        if self.include_token_type:
            nodes.append(_MockInputNode("token_type_ids"))
        return nodes

    def run(self, output_names: object, ort_inputs: dict[str, Any]) -> list[np.ndarray[Any, Any]]:
        _ = output_names
        self.run_calls.append(ort_inputs)
        batch_size = ort_inputs["input_ids"].shape[0]

        if self.all_zeros:
            if self.rank_3:
                hidden = np.zeros((batch_size, MAX_SEQ_LENGTH, EMBED_DIMENSION), dtype=np.float32)
            else:
                hidden = np.zeros((batch_size, EMBED_DIMENSION), dtype=np.float32)
            return [hidden]

        rng = np.random.default_rng(seed=42)
        if self.rank_3:
            hidden = rng.standard_normal(
                (batch_size, MAX_SEQ_LENGTH, EMBED_DIMENSION), dtype=np.float32
            )
        else:
            hidden = rng.standard_normal((batch_size, EMBED_DIMENSION), dtype=np.float32)
        return [hidden]


def _create_temp_model_files(
    tmp_path: Path,
) -> tuple[Path, str, str]:
    """Create dummy model_int8.onnx and tokenizer.json and return their sha256."""
    model_bytes = b"dummy ONNX model binary payload for unit testing"
    tok_bytes = b"dummy tokenizer JSON payload for unit testing"

    model_file = tmp_path / "model_int8.onnx"
    tok_file = tmp_path / "tokenizer.json"

    model_file.write_bytes(model_bytes)
    tok_file.write_bytes(tok_bytes)

    model_sha = hashlib.sha256(model_bytes).hexdigest()
    tok_sha = hashlib.sha256(tok_bytes).hexdigest()

    return tmp_path, model_sha, tok_sha


def test_case_04_tampered_model_file_fails_integrity(tmp_path: Path) -> None:
    """Test Case 4: Security (Tampered model file).

    Tampered model file (1 byte changed in a temp copy) -> EmbedderIntegrityError;
    embedder never calls InferenceSession.
    """
    model_dir, model_sha, tok_sha = _create_temp_model_files(tmp_path)

    # Tamper with model_int8.onnx by flipping bytes
    tampered_bytes = b"X" + (tmp_path / "model_int8.onnx").read_bytes()[1:]
    (tmp_path / "model_int8.onnx").write_bytes(tampered_bytes)

    with patch("onnxruntime.InferenceSession") as mock_session_cls:
        with pytest.raises(EmbedderIntegrityError) as exc_info:
            OnnxBgeSmallEmbedder(
                model_dir=model_dir,
                expected_model_sha256=model_sha,
                expected_tokenizer_sha256=tok_sha,
            )

        assert "model_int8.onnx integrity mismatch" in str(exc_info.value)
        # Verify InferenceSession was NEVER called
        assert mock_session_cls.call_count == 0


def test_tampered_tokenizer_fails_integrity(tmp_path: Path) -> None:
    """Tampered tokenizer.json fails integrity before initializing session."""
    model_dir, model_sha, tok_sha = _create_temp_model_files(tmp_path)

    # Tamper with tokenizer.json
    tampered_bytes = b"Y" + (tmp_path / "tokenizer.json").read_bytes()[1:]
    (tmp_path / "tokenizer.json").write_bytes(tampered_bytes)

    with patch("onnxruntime.InferenceSession") as mock_session_cls:
        with pytest.raises(EmbedderIntegrityError) as exc_info:
            OnnxBgeSmallEmbedder(
                model_dir=model_dir,
                expected_model_sha256=model_sha,
                expected_tokenizer_sha256=tok_sha,
            )

        assert "tokenizer.json integrity mismatch" in str(exc_info.value)
        assert mock_session_cls.call_count == 0


def test_missing_model_and_tokenizer_files_raise_integrity(tmp_path: Path) -> None:
    """Missing model or tokenizer file raises EmbedderIntegrityError."""
    # Empty dir
    with pytest.raises(EmbedderIntegrityError) as exc_info_m:
        OnnxBgeSmallEmbedder(model_dir=tmp_path)
    assert "Model binary not found" in str(exc_info_m.value)

    # Dir with only model file
    (tmp_path / "model_int8.onnx").write_bytes(b"data")
    with pytest.raises(EmbedderIntegrityError) as exc_info_t:
        OnnxBgeSmallEmbedder(model_dir=tmp_path)
    assert "Tokenizer file not found" in str(exc_info_t.value)


def test_missing_env_and_dir_raises_integrity() -> None:
    """Unset environment and None model_dir raises EmbedderIntegrityError."""
    with patch.dict("os.environ", {}, clear=True):
        with pytest.raises(EmbedderIntegrityError) as exc_info:
            OnnxBgeSmallEmbedder(model_dir=None, inference_session=None)
        assert "KANBAN_EMBED_MODEL_DIR" in str(exc_info.value)


@pytest.mark.asyncio
async def test_case_05_faked_inference_session_positive() -> None:
    """Test Case 5: Positive (Faked InferenceSession).

    OnnxBgeSmallEmbedder with InferenceSession faked:
    - returns L2-normalized vectors (norm 1.0 +/- 1e-6)
    - truncates 600-token input to 512 tokens
    - returns 384-dimensional vectors
    """
    tok = _MockTokenizer(token_count=600)
    sess = _MockInferenceSession(include_token_type=True, rank_3=True)

    embedder = OnnxBgeSmallEmbedder(
        model_dir=None,
        inference_session=sess,
        tokenizer=tok,
    )

    assert embedder.model_id == MODEL_ID
    assert embedder.dimension == EMBED_DIMENSION

    # Run embedding with 3 inputs
    texts = ["hello world", "rag search query", "architectural spec chunk"]
    vectors = await embedder.embed_batch(texts)

    assert len(vectors) == 3
    for vec in vectors:
        assert len(vec) == EMBED_DIMENSION
        # Check L2 normalization: norm should equal 1.0 within 1e-6
        norm = float(np.linalg.norm(np.array(vec, dtype=np.float32)))
        assert pytest.approx(norm, abs=1e-6) == 1.0

    # Verify input_ids was truncated to 512 tokens
    assert len(sess.run_calls) == 1
    input_ids = sess.run_calls[0]["input_ids"]
    attention_mask = sess.run_calls[0]["attention_mask"]
    token_type_ids = sess.run_calls[0]["token_type_ids"]

    assert input_ids.shape == (3, 512)
    assert attention_mask.shape == (3, 512)
    assert token_type_ids.shape == (3, 512)


@pytest.mark.asyncio
async def test_batch_slicing_over_max_batch_size() -> None:
    """Ensure texts exceeding MAX_BATCH_SIZE (32) are batched properly."""
    tok = _MockTokenizer(token_count=50)
    sess = _MockInferenceSession()

    embedder = OnnxBgeSmallEmbedder(
        model_dir=None,
        inference_session=sess,
        tokenizer=tok,
    )

    # 70 texts -> 3 batches (32, 32, 6)
    total_texts = 70
    texts = [f"Text sequence chunk number {i}" for i in range(total_texts)]
    vectors = await embedder.embed_batch(texts)

    assert len(vectors) == 70
    assert len(sess.run_calls) == 3
    assert sess.run_calls[0]["input_ids"].shape[0] == MAX_BATCH_SIZE
    assert sess.run_calls[1]["input_ids"].shape[0] == MAX_BATCH_SIZE
    assert sess.run_calls[2]["input_ids"].shape[0] == 6


@pytest.mark.asyncio
async def test_empty_input_handling() -> None:
    """Empty inputs return empty list without executing inference."""
    tok = _MockTokenizer()
    sess = _MockInferenceSession()
    embedder = OnnxBgeSmallEmbedder(
        model_dir=None,
        inference_session=sess,
        tokenizer=tok,
    )

    res = await embedder.embed_batch([])
    assert res == []
    assert len(sess.run_calls) == 0

    direct_res = embedder._run_inference([])  # noqa: SLF001
    assert direct_res == []


@pytest.mark.asyncio
async def test_rank_2_hidden_states_and_zero_norm_guard() -> None:
    """Test 2D tensor handling and zero-norm division guard."""
    tok = _MockTokenizer(token_count=100)
    sess_2d = _MockInferenceSession(include_token_type=False, rank_3=False, all_zeros=True)

    embedder = OnnxBgeSmallEmbedder(
        model_dir=None,
        inference_session=sess_2d,
        tokenizer=tok,
    )

    vectors = await embedder.embed_batch(["text with zero vector fallback"])
    assert len(vectors) == 1
    assert len(vectors[0]) == EMBED_DIMENSION
    assert all(not np.isnan(v) for v in vectors[0])


def test_asset_setup_from_valid_files(tmp_path: Path) -> None:
    """Test _setup_tokenizer and _setup_session with mocked factory calls."""
    model_dir, model_sha, tok_sha = _create_temp_model_files(tmp_path)

    mock_tok_instance = MagicMock()
    mock_sess_instance = MagicMock()

    with (
        patch("tokenizers.Tokenizer.from_file", return_value=mock_tok_instance) as mock_tok_fn,
        patch("onnxruntime.InferenceSession", return_value=mock_sess_instance) as mock_sess_fn,
    ):
        embedder = OnnxBgeSmallEmbedder(
            model_dir=model_dir,
            expected_model_sha256=model_sha,
            expected_tokenizer_sha256=tok_sha,
        )
        assert embedder._tokenizer == mock_tok_instance  # noqa: SLF001
        assert embedder._session == mock_sess_instance  # noqa: SLF001
        assert mock_tok_fn.call_count == 1
        assert mock_sess_fn.call_count == 1


def test_unsupported_setup_calls_without_model_dir() -> None:
    """Directly calling setup without model_dir and without custom object raises error."""
    embedder = OnnxBgeSmallEmbedder(
        model_dir=None,
        inference_session=MagicMock(),
        tokenizer=MagicMock(),
    )
    with pytest.raises(EmbedderIntegrityError) as exc_tok:
        embedder._setup_tokenizer(None)  # noqa: SLF001
    assert "Tokenizer instance or model_dir required" in str(exc_tok.value)

    with pytest.raises(EmbedderIntegrityError) as exc_sess:
        embedder._setup_session(None)  # noqa: SLF001
    assert "Inference session or model_dir required" in str(exc_sess.value)


@pytest.mark.asyncio
async def test_embed_batch_rich_on_direct_embedder() -> None:
    """Test embed_batch_rich with non-fallback direct inference session."""
    sess = _MockInferenceSession(include_token_type=True, rank_3=True)
    tok = _MockTokenizer(token_count=16)
    embedder = OnnxBgeSmallEmbedder(
        model_dir=None,
        inference_session=sess,
        tokenizer=tok,
    )

    # Empty inputs
    assert await embedder.embed_batch_rich([]) == []

    # Non-empty inputs with markdown headings
    markdown_text = "# Security Heading\nDetailed content for testing rich batch embedding."
    results = await embedder.embed_batch_rich([markdown_text])
    assert len(results) == 1
    chunk = results[0]
    assert len(chunk.embedding) == EMBED_DIMENSION
    assert len(chunk.head_128) == 128
    assert len(chunk.binary_sign) == 16
    assert len(chunk.full_q8) == EMBED_DIMENSION
    assert len(chunk.heading_anchors) == 1
    assert chunk.heading_anchors[0]["title"] == "Security Heading"

