"""Unit tests for ProviderEmbedder, secret scrubbing, and base embedding errors."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

import pytest

from agent.embeddings.base import (
    EmbedderDimensionMismatchError,
    EmbedderError,
    EmbedderIntegrityError,
    ProviderEmbedder,
)
from agent.testing.fixtures import FixtureLLMProvider, load_cassette

if TYPE_CHECKING:
    from agent.providers.base import EmbedBatchRequest


def test_embedder_exception_hierarchy() -> None:
    """Verify typed exception inheritance hierarchy."""
    assert issubclass(EmbedderIntegrityError, EmbedderError)
    assert issubclass(EmbedderDimensionMismatchError, EmbedderError)


@pytest.mark.asyncio
async def test_provider_embedder_deterministic_cassette() -> None:
    """ProviderEmbedder successfully replays vectors from deterministic cassette."""
    cassette_path = Path("tests/fixtures/ai/embed_fixture_384_ok.yaml")
    cassette = load_cassette(cassette_path)
    provider = FixtureLLMProvider([cassette])

    embedder = ProviderEmbedder(provider, model="bge-small-en-v1.5", dimension=384)

    assert embedder.model_id == "bge-small-en-v1.5"
    assert embedder.dimension == 384

    texts = ["hello world", "rag indexing test"]
    vectors = await embedder.embed_batch(texts)

    assert len(vectors) == 2
    assert len(vectors[0]) == 384
    assert len(vectors[1]) == 384


@pytest.mark.asyncio
async def test_provider_embedder_empty_input() -> None:
    """Empty inputs return empty list without querying LLMProvider."""
    mock_provider = MagicMock()
    embedder = ProviderEmbedder(mock_provider, model="test-model", dimension=384)

    res = await embedder.embed_batch([])
    assert res == []
    assert mock_provider.embed_batch.call_count == 0


@pytest.mark.asyncio
async def test_provider_embedder_scrubbing_enabled_and_disabled() -> None:
    """Verify secret scrubbing behavior on outbound text."""
    secret_token = "gh" + "p_" + "1" * 36
    secret_text = f"API key: {secret_token}"
    dummy_vec = [0.1] * 384

    # Test with scrub=True (default)
    mock_provider_scrub = MagicMock()
    mock_provider_scrub.embed_batch = AsyncMock(return_value=[dummy_vec])

    embedder_scrub = ProviderEmbedder(
        mock_provider_scrub, model="test-model", dimension=384, scrub=True
    )
    await embedder_scrub.embed_batch([secret_text])

    req_scrub: EmbedBatchRequest = mock_provider_scrub.embed_batch.call_args[0][0]
    assert secret_token not in req_scrub.inputs[0]
    assert "[REDACTED" in req_scrub.inputs[0]

    # Test with scrub=False
    mock_provider_raw = MagicMock()
    mock_provider_raw.embed_batch = AsyncMock(return_value=[dummy_vec])

    embedder_raw = ProviderEmbedder(
        mock_provider_raw, model="test-model", dimension=384, scrub=False
    )
    await embedder_raw.embed_batch([secret_text])

    req_raw: EmbedBatchRequest = mock_provider_raw.embed_batch.call_args[0][0]
    assert req_raw.inputs[0] == secret_text


@pytest.mark.asyncio
async def test_provider_embedder_dimension_mismatch() -> None:
    """Cassette returning wrong dimension raises EmbedderDimensionMismatchError."""
    cassette_path = Path("tests/fixtures/ai/embed_fault_dim_mismatch.yaml")
    cassette = load_cassette(cassette_path)
    provider = FixtureLLMProvider([cassette])

    # Target dimension 384, but cassette provides 383
    embedder = ProviderEmbedder(provider, model="bge-small-en-v1.5", dimension=384)

    with pytest.raises(EmbedderDimensionMismatchError) as exc_info:
        await embedder.embed_batch(["text targeting 384"])

    assert "Vector dimension mismatch: expected 384, got 383" in str(exc_info.value)
