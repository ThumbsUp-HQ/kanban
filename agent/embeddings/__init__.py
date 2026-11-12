"""Vector embeddings and indexing subsystem for Kanban platform."""

from agent.embeddings.base import (
    Embedder,
    EmbedderDimensionMismatchError,
    EmbedderError,
    EmbedderIntegrityError,
    ProviderEmbedder,
)
from agent.embeddings.indexer import (
    DEFAULT_CHUNK_SIZE,
    DEFAULT_MAX_CHUNKS,
    DEFAULT_OVERLAP,
    EmbeddingIndexer,
    chunk_markdown,
)
from agent.embeddings.onnx_embedder import (
    BGE_SMALL_INT8_ONNX_SHA256,
    BGE_SMALL_TOKENIZER_SHA256,
    OnnxBgeSmallEmbedder,
)

__all__ = [
    "BGE_SMALL_INT8_ONNX_SHA256",
    "BGE_SMALL_TOKENIZER_SHA256",
    "DEFAULT_CHUNK_SIZE",
    "DEFAULT_MAX_CHUNKS",
    "DEFAULT_OVERLAP",
    "Embedder",
    "EmbedderDimensionMismatchError",
    "EmbedderError",
    "EmbedderIntegrityError",
    "EmbeddingIndexer",
    "OnnxBgeSmallEmbedder",
    "ProviderEmbedder",
    "chunk_markdown",
]
