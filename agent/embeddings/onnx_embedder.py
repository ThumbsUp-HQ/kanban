"""Int8 ONNX bge-small-en-v1.5 embedding engine with cryptographic integrity pinning."""

from __future__ import annotations

import asyncio
import hashlib
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final, cast

import numpy as np
import onnxruntime  # type: ignore[import-untyped]
import tokenizers

from agent.embeddings.base import Embedder, EmbedderIntegrityError
from agent.embeddings.quantizer import (
    EmbeddedChunkPayload,
    MatryoshkaQuantizer,
    compute_binary_sign,
    dequantize_int8,
    extract_heading_anchors,
    extract_matryoshka_head,
    int8_dot_product,
    quantize_int8,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

__all__ = [
    "BGE_SMALL_INT8_ONNX_SHA256",
    "BGE_SMALL_TOKENIZER_SHA256",
    "EMBED_DIMENSION",
    "MAX_BATCH_SIZE",
    "MAX_SEQ_LENGTH",
    "MODEL_ID",
    "EmbeddedChunkPayload",
    "FixtureEmbedder",
    "MatryoshkaQuantizer",
    "OnnxBgeSmallEmbedder",
    "compute_binary_sign",
    "dequantize_int8",
    "extract_heading_anchors",
    "extract_matryoshka_head",
    "int8_dot_product",
    "quantize_int8",
]

_NORM_EPSILON: Final[float] = 1e-12
BGE_SMALL_INT8_ONNX_SHA256: Final[str] = (
    "9c7d42cf38a9e88fb5e98214fa8b2b73bc701f56860ebaa8ca0199d985223067"
)
BGE_SMALL_TOKENIZER_SHA256: Final[str] = (
    "c5e933615e47bcbe65f8c6fb73d1ee0c77461019623e1291cfb77f985a9bc8d7"
)
MAX_BATCH_SIZE: Final[int] = 32
MAX_SEQ_LENGTH: Final[int] = 512
EMBED_DIMENSION: Final[int] = 384
MODEL_ID: Final[str] = "bge-small-en-v1.5-int8"
_TENSOR_RANK_3: Final[int] = 3


class FixtureEmbedder(Embedder):
    """Deterministic, zero-egress offline embedder for hermetic testing."""

    def __init__(
        self,
        dimension: int = EMBED_DIMENSION,
        model_id: str = "fixture-bge-small-en-v1.5",
    ) -> None:
        """Initialize deterministic fixture embedder."""
        self._dimension = dimension
        self._model_id = model_id

    @property
    def model_id(self) -> str:
        """Return model identifier."""
        return self._model_id

    @property
    def dimension(self) -> int:
        """Return embedding dimension."""
        return self._dimension

    def _generate_vector(self, text: str) -> list[float]:
        """Generate deterministic L2-normalized float vector from text hash."""
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        seed = int.from_bytes(digest[:8], "big")
        rng = np.random.default_rng(seed)
        raw = rng.standard_normal(self._dimension).astype(np.float32)
        norm = float(np.linalg.norm(raw))
        if norm > _NORM_EPSILON:
            raw = raw / norm
        return [float(x) for x in raw.tolist()]

    async def embed_batch(self, texts: Sequence[str]) -> list[list[float]]:
        """Compute deterministic vector batch without external network calls."""
        if not texts:
            return []
        return [self._generate_vector(t) for t in texts]

    async def embed_batch_rich(self, texts: Sequence[str]) -> list[EmbeddedChunkPayload]:
        """Compute rich payloads with Matryoshka head and int8 quantization."""
        if not texts:
            return []
        vectors = await self.embed_batch(texts)
        results: list[EmbeddedChunkPayload] = []
        for text_content, vec in zip(texts, vectors, strict=True):
            head_128 = extract_matryoshka_head(vec, 128)
            binary_sign = compute_binary_sign(vec, 128)
            full_q8, q8_scale = quantize_int8(vec)
            heading_anchors = extract_heading_anchors(text_content)
            results.append(
                EmbeddedChunkPayload(
                    embedding=vec,
                    head_128=head_128,
                    binary_sign=binary_sign,
                    full_q8=full_q8,
                    q8_scale=q8_scale,
                    heading_anchors=heading_anchors,
                )
            )
        return results


class OnnxBgeSmallEmbedder(Embedder):
    """Local, offline bge-small-en-v1.5 embedder running on CPU via ONNX Runtime."""

    def __init__(  # noqa: PLR0913
        self,
        model_dir: str | Path | None = None,
        *,
        expected_model_sha256: str = BGE_SMALL_INT8_ONNX_SHA256,
        expected_tokenizer_sha256: str = BGE_SMALL_TOKENIZER_SHA256,
        inference_session: object | None = None,
        tokenizer: object | None = None,
        fallback_to_fixture: bool = False,
    ) -> None:
        """Initialize embedder with file hash verification and session configuration."""
        self._fixture_fallback: FixtureEmbedder | None = None
        use_fixture = fallback_to_fixture or os.environ.get("KANBAN_EMBED_FIXTURE") == "1"

        resolved_dir_str = model_dir or os.environ.get("KANBAN_EMBED_MODEL_DIR")
        if not resolved_dir_str and inference_session is None:
            if use_fixture:
                self._fixture_fallback = FixtureEmbedder()
                self._model_dir = None
                self._semaphore = asyncio.Semaphore(2)
                return
            msg = "KANBAN_EMBED_MODEL_DIR environment variable or model_dir must be configured"
            raise EmbedderIntegrityError(msg)

        self._model_dir = Path(resolved_dir_str) if resolved_dir_str else None
        self._semaphore = asyncio.Semaphore(2)

        if self._model_dir is not None:
            try:
                self._verify_assets(
                    self._model_dir, expected_model_sha256, expected_tokenizer_sha256
                )
            except EmbedderIntegrityError:
                if use_fixture:
                    self._fixture_fallback = FixtureEmbedder()
                    return
                raise

        try:
            self._tokenizer = self._setup_tokenizer(tokenizer)
            self._session = self._setup_session(inference_session)
        except EmbedderIntegrityError:
            if use_fixture:
                self._fixture_fallback = FixtureEmbedder()
                return
            raise

    def _verify_assets(
        self,
        model_dir: Path,
        expected_model_sha: str,
        expected_tok_sha: str,
    ) -> None:
        """Verify presence and cryptographic SHA-256 hashes of model files."""
        model_path = model_dir / "model_int8.onnx"
        tokenizer_path = model_dir / "tokenizer.json"

        if not model_path.is_file():
            msg = f"Model binary not found: {model_path}"
            raise EmbedderIntegrityError(msg)
        if not tokenizer_path.is_file():
            msg = f"Tokenizer file not found: {tokenizer_path}"
            raise EmbedderIntegrityError(msg)

        model_sha = hashlib.sha256(model_path.read_bytes()).hexdigest()
        tok_sha = hashlib.sha256(tokenizer_path.read_bytes()).hexdigest()

        if model_sha != expected_model_sha:
            msg = (
                f"model_int8.onnx integrity mismatch: expected {expected_model_sha}, "
                f"got {model_sha}"
            )
            raise EmbedderIntegrityError(msg)

        if tok_sha != expected_tok_sha:
            msg = f"tokenizer.json integrity mismatch: expected {expected_tok_sha}, got {tok_sha}"
            raise EmbedderIntegrityError(msg)

    def _setup_tokenizer(self, custom_tok: object | None) -> object:
        """Initialize and configure HuggingFace Rust tokenizer instance."""
        if custom_tok is not None:
            return custom_tok
        if self._model_dir is not None:
            tok = tokenizers.Tokenizer.from_file(str(self._model_dir / "tokenizer.json"))
            tok.enable_truncation(max_length=MAX_SEQ_LENGTH)
            tok.enable_padding(length=MAX_SEQ_LENGTH)
            return tok
        msg = "Tokenizer instance or model_dir required"
        raise EmbedderIntegrityError(msg)

    def _setup_session(self, custom_session: object | None) -> object:
        """Initialize and configure ONNX Runtime CPU inference session."""
        if custom_session is not None:
            return custom_session
        if self._model_dir is not None:
            sess_options = onnxruntime.SessionOptions()
            sess_options.intra_op_num_threads = 1
            sess_options.graph_optimization_level = (
                onnxruntime.GraphOptimizationLevel.ORT_ENABLE_ALL
            )
            return onnxruntime.InferenceSession(
                str(self._model_dir / "model_int8.onnx"),
                sess_options=sess_options,
                providers=["CPUExecutionProvider"],
            )
        msg = "Inference session or model_dir required"
        raise EmbedderIntegrityError(msg)

    @property
    def model_id(self) -> str:
        """Return the unique model identifier string."""
        if self._fixture_fallback is not None:
            return self._fixture_fallback.model_id
        return MODEL_ID

    @property
    def dimension(self) -> int:
        """Return vector dimension."""
        if self._fixture_fallback is not None:
            return self._fixture_fallback.dimension
        return EMBED_DIMENSION

    def _run_inference(self, batch_texts: list[str]) -> list[list[float]]:
        """Run tokenization, ONNX inference, CLS pooling, and L2 normalization."""
        if not batch_texts:
            return []

        tok: Any = self._tokenizer
        encodings = tok.encode_batch(batch_texts)
        input_ids = [enc.ids[:MAX_SEQ_LENGTH] for enc in encodings]
        attention_mask = [enc.attention_mask[:MAX_SEQ_LENGTH] for enc in encodings]

        sess: Any = self._session
        input_names = {inp.name for inp in sess.get_inputs()}
        ort_inputs: dict[str, Any] = {
            "input_ids": np.array(input_ids, dtype=np.int64),
            "attention_mask": np.array(attention_mask, dtype=np.int64),
        }
        if "token_type_ids" in input_names:
            ort_inputs["token_type_ids"] = np.zeros_like(ort_inputs["input_ids"])

        outputs = sess.run(None, ort_inputs)
        last_hidden_state = outputs[0]

        # CLS pooling: token 0 representation
        if len(last_hidden_state.shape) == _TENSOR_RANK_3:
            cls_embeddings = last_hidden_state[:, 0, :]
        else:
            cls_embeddings = last_hidden_state

        # L2 normalization to unit hypersphere
        norms = np.linalg.norm(cls_embeddings, ord=2, axis=1, keepdims=True)
        norms = np.where(norms == 0, 1e-12, norms)
        normalized = cls_embeddings / norms

        return cast("list[list[float]]", normalized.astype(np.float32).tolist())

    async def embed_batch(self, texts: Sequence[str]) -> list[list[float]]:
        """Compute L2-normalized vector embeddings for input texts in chunks <= 32."""
        if not texts:
            return []
        if self._fixture_fallback is not None:
            return await self._fixture_fallback.embed_batch(texts)

        results: list[list[float]] = []
        text_list = list(texts)

        for i in range(0, len(text_list), MAX_BATCH_SIZE):
            chunk = text_list[i : i + MAX_BATCH_SIZE]
            async with self._semaphore:
                batch_vectors = await asyncio.to_thread(self._run_inference, chunk)
            results.extend(batch_vectors)

        return results

    async def embed_batch_rich(self, texts: Sequence[str]) -> list[EmbeddedChunkPayload]:
        """Compute rich payloads with Matryoshka head, binary sign, and int8 quantization."""
        if not texts:
            return []
        if self._fixture_fallback is not None:
            return await self._fixture_fallback.embed_batch_rich(texts)

        vectors = await self.embed_batch(texts)
        results: list[EmbeddedChunkPayload] = []
        for text_content, vec in zip(texts, vectors, strict=True):
            head_128 = extract_matryoshka_head(vec, 128)
            binary_sign = compute_binary_sign(vec, 128)
            full_q8, q8_scale = quantize_int8(vec)
            heading_anchors = extract_heading_anchors(text_content)
            results.append(
                EmbeddedChunkPayload(
                    embedding=vec,
                    head_128=head_128,
                    binary_sign=binary_sign,
                    full_q8=full_q8,
                    q8_scale=q8_scale,
                    heading_anchors=heading_anchors,
                )
            )
        return results
