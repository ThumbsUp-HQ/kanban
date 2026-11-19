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
"""Sparkle FIM completion pipeline: scrub-first, 18ms retrieval, bounded FIM streaming."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Final, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from agent.providers.base import CompletionRequest
from agent.providers.errors import (
    AllProvidersUnavailable,
    ProviderHTTPError,
    ProviderTimeout,
    ProviderUnavailable,
)
from agent.sparkle.output_filter import filter_completion
from agent.sparkle.retrieval import RetrievalStatus, retrieve_context
from kanban.security.scrubber import outbound_secret_scrubber

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from agent.embeddings.base import Embedder
    from agent.providers.router import ProviderRouter
    from database.session import RLSContext
    from kanban.api.deps import PrincipalContext

__all__ = [
    "SparkleRequest",
    "SparkleResult",
    "SparkleStatus",
    "run_sparkle_pipeline",
]

_logger = logging.getLogger(__name__)

SparkleStatus = Literal["ok", "empty", "timeout", "secret_scrubbed", "unavailable", "budget"]

_MAX_PREFIX_CHARS: Final[int] = 1500
_MAX_SUFFIX_CHARS: Final[int] = 500
_MAX_EMBED_CHARS: Final[int] = 512
_MAX_OUTPUT_TOKENS: Final[int] = 48
_MAX_CHAR_CAP: Final[int] = 400
_PIPELINE_TIMEOUT_SECONDS: Final[float] = 0.130
_TTFT_DEADLINE_MS: Final[int] = 115
_DEFAULT_TEMPERATURE: Final[float] = 0.15


class SparkleRequest(BaseModel):
    """Inbound request contract for Sparkle FIM suggestion."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    project_id: UUID | str | None = None
    object_id: UUID | None = None
    surface: Literal["summary", "description", "comment", "sticky", "doc"]
    prefix: str = Field(..., max_length=6000)
    suffix: str = Field(default="", max_length=2000)
    client_request_id: UUID


@dataclass(frozen=True, slots=True)
class SparkleResult:
    """Outcome and telemetry of a Sparkle FIM execution."""

    status: SparkleStatus
    text: str = ""
    ttft_ms: float = 0.0
    total_ms: float = 0.0
    tokens: int = 0
    retrieval_status: RetrievalStatus = "empty"
    route_trace: list[dict[str, Any]] = field(default_factory=list)


async def run_sparkle_pipeline(  # noqa: C901, PLR0912, PLR0913, PLR0915  # End-to-end pipeline orchestrator
    req: SparkleRequest,
    *,
    principal_ctx: PrincipalContext | RLSContext,
    router: ProviderRouter,
    embedder: Embedder | None = None,
    session_factory: Any = None,  # noqa: ANN401
    clock: Callable[[], float] = time.monotonic,
) -> SparkleResult:
    """Execute the end-to-end Sparkle completion pipeline in strict order.

    Order of Operations:
    1. Truncate prefix/suffix to last 1,500 and first 500 characters.
    2. Run outbound_secret_scrubber on prefix and suffix. If ANY credential or
       token is detected, return status='secret_scrubbed' immediately with ZERO
       embedder, DB, or provider calls.
    3. Embed the last 512 characters of the scrubbed prefix via the local embedder.
    4. Retrieve context under app_rls_reader bounded by an 18ms statement_timeout.
    5. Stream FIM completion from ProviderRouter bounded by a 130ms overall timeout
       and 115ms TTFT deadline.
    6. Buffer up to 48 tokens and sanitize through filter_completion().
    7. Return SparkleResult with telemetry and route trace.
    """
    t0 = clock()

    # Step 1: Truncate prefix to last 1,500 chars and suffix to first 500 chars
    prefix = req.prefix[-_MAX_PREFIX_CHARS:] if len(req.prefix) > _MAX_PREFIX_CHARS else req.prefix
    suffix = req.suffix[:_MAX_SUFFIX_CHARS] if len(req.suffix) > _MAX_SUFFIX_CHARS else req.suffix

    # Step 2: Outbound secret scrubber check; zero sockets/calls on redaction
    scrub_prefix = outbound_secret_scrubber(prefix)
    scrub_suffix = outbound_secret_scrubber(suffix)
    if scrub_prefix.redacted or scrub_suffix.redacted:
        elapsed = (clock() - t0) * 1000.0
        return SparkleResult(
            status="secret_scrubbed",
            text="",
            ttft_ms=0.0,
            total_ms=elapsed,
            tokens=0,
            retrieval_status="skipped",
            route_trace=[],
        )

    clean_prefix = scrub_prefix.text
    clean_suffix = scrub_suffix.text

    # Step 3: Embed last 512 chars of scrubbed prefix
    query_vector: Sequence[float] = ()
    if embedder is not None:
        embed_input = clean_prefix[-_MAX_EMBED_CHARS:]
        try:
            vectors = await embedder.embed_batch([embed_input])
            if vectors:
                query_vector = vectors[0]
        except Exception as exc:  # noqa: BLE001
            _logger.warning("Local embedder failure during Sparkle retrieval: %s", exc)

    # Step 4: Context retrieval under app_rls_reader (18ms budget)
    snippets: list[str] = []
    ret_status: RetrievalStatus = "skipped"
    resolved_proj_uuid: UUID | None = None
    if isinstance(req.project_id, UUID):
        resolved_proj_uuid = req.project_id
    elif isinstance(req.project_id, str):
        with contextlib.suppress(ValueError):
            resolved_proj_uuid = UUID(req.project_id)

    if query_vector and session_factory is not None and resolved_proj_uuid is not None:
        snippets, ret_status = await retrieve_context(
            project_id=resolved_proj_uuid,
            query_vector=query_vector,
            principal_ctx=principal_ctx,
            session_factory=session_factory,
        )

    # Compose final prompt (untrusted context prepended if present)
    prompt_text = "\n\n".join(snippets) + "\n\n" + clean_prefix if snippets else clean_prefix

    # Step 5: Streaming FIM bounded by 130ms overall timeout and 115ms TTFT SLA
    stream_iter = None
    chunks: list[str] = []
    ttft_ms = 0.0

    try:
        async with asyncio.timeout(_PIPELINE_TIMEOUT_SECONDS):
            compl_req = CompletionRequest(
                model=getattr(router, "residency_tier", "default"),
                prompt=prompt_text,
                suffix=clean_suffix,
                temperature=_DEFAULT_TEMPERATURE,
                max_output_tokens=_MAX_OUTPUT_TOKENS,
                ttft_deadline_ms=_TTFT_DEADLINE_MS,
            )
            stream_iter = router.stream_complete(compl_req)

            async for chunk in stream_iter:
                if not chunks:
                    ttft_ms = (clock() - t0) * 1000.0
                chunks.append(chunk.delta)
                if len(chunks) >= _MAX_OUTPUT_TOKENS:
                    break

    except (TimeoutError, ProviderTimeout) as exc:
        _logger.info("Sparkle FIM stream timeout: %s", exc)
        if stream_iter is not None and hasattr(stream_iter, "aclose"):
            await stream_iter.aclose()
        elapsed = (clock() - t0) * 1000.0
        return SparkleResult(
            status="timeout",
            text="",
            ttft_ms=ttft_ms,
            total_ms=elapsed,
            tokens=0,
            retrieval_status=ret_status,
            route_trace=list(getattr(router, "last_route_trace", [])),
        )
    except (AllProvidersUnavailable, ProviderUnavailable, ProviderHTTPError) as exc:
        cause = getattr(exc, "__cause__", None)
        is_timeout = (
            isinstance(cause, (TimeoutError, ProviderTimeout))
            or "timeout" in str(exc).lower()
            or "ttft" in str(exc).lower()
        )
        status_val: SparkleStatus = "timeout" if is_timeout else "unavailable"
        _logger.warning("Sparkle FIM provider %s: %s", status_val, exc)
        if stream_iter is not None and hasattr(stream_iter, "aclose"):
            await stream_iter.aclose()
        elapsed = (clock() - t0) * 1000.0
        return SparkleResult(
            status=status_val,
            text="",
            ttft_ms=ttft_ms,
            total_ms=elapsed,
            tokens=0,
            retrieval_status=ret_status,
            route_trace=list(getattr(router, "last_route_trace", [])),
        )

    # Step 6: Buffer and sanitize completion
    raw_completion = "".join(chunks[:_MAX_OUTPUT_TOKENS])
    filtered_text = filter_completion(
        raw_completion, max_tokens=_MAX_OUTPUT_TOKENS, max_chars=_MAX_CHAR_CAP
    )
    token_count = len(chunks[:_MAX_OUTPUT_TOKENS])

    elapsed = (clock() - t0) * 1000.0

    if not filtered_text:
        return SparkleResult(
            status="empty",
            text="",
            ttft_ms=ttft_ms,
            total_ms=elapsed,
            tokens=0,
            retrieval_status=ret_status,
            route_trace=list(getattr(router, "last_route_trace", [])),
        )

    # Step 7: Success
    return SparkleResult(
        status="ok",
        text=filtered_text,
        ttft_ms=ttft_ms,
        total_ms=elapsed,
        tokens=token_count,
        retrieval_status=ret_status,
        route_trace=list(getattr(router, "last_route_trace", [])),
    )
