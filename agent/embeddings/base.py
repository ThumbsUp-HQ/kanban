"""Base protocols, adapters, and errors for embedding engines."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

from agent.providers.base import EmbedBatchRequest
from kanban.security.scrubber import scrub_text

if TYPE_CHECKING:
    from collections.abc import Sequence

    from agent.providers.base import LLMProvider


class EmbedderError(Exception):
    """Base exception for all embedding engine operations."""


class EmbedderIntegrityError(EmbedderError):
    """Raised when an embedding model file or tokenizer fails cryptographic integrity checks."""


class EmbedderDimensionMismatchError(EmbedderError):
    """Raised when generated embedding vectors do not match the expected dimensionality."""


@runtime_checkable
class Embedder(Protocol):
    """Vendor-neutral protocol for vector embedding generation engines."""

    @property
    def model_id(self) -> str:
        """Return the unique model identifier string."""
        ...

    @property
    def dimension(self) -> int:
        """Return the expected vector dimension."""
        ...

    async def embed_batch(self, texts: Sequence[str]) -> list[list[float]]:
        """Generate batch vector embeddings for a sequence of texts."""
        ...


class ProviderEmbedder:
    """Adapter over LLMProvider.embed_batch with outbound secret scrubbing."""

    def __init__(
        self,
        provider: LLMProvider,
        *,
        model: str = "bge-small-en-v1.5",
        dimension: int = 384,
        scrub: bool = True,
    ) -> None:
        """Initialize provider embedder with target model, dimension, and scrubbing flag."""
        self._provider = provider
        self._model = model
        self._dimension = dimension
        self._scrub = scrub

    @property
    def model_id(self) -> str:
        """Return the unique model identifier string."""
        return self._model

    @property
    def dimension(self) -> int:
        """Return the expected vector dimension."""
        return self._dimension

    async def embed_batch(self, texts: Sequence[str]) -> list[list[float]]:
        """Scrub texts if configured and delegate embedding to underlying LLMProvider."""
        if not texts:
            return []

        inputs = [scrub_text(t) for t in texts] if self._scrub else list(texts)

        req = EmbedBatchRequest(model=self._model, inputs=tuple(inputs))
        vectors = await self._provider.embed_batch(req)

        for vec in vectors:
            if len(vec) != self._dimension:
                msg = f"Vector dimension mismatch: expected {self._dimension}, got {len(vec)}"
                raise EmbedderDimensionMismatchError(msg)

        return vectors
