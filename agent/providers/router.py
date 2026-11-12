# Copyright 2026 Kanban Platform Contributors
"""Resilient provider router with circuit breaking and air-gap enforcement."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from uuid import UUID

from agent.providers.air_gap import AirGapGuard
from agent.providers.base import (
    CompletionRequest,
    EmbedBatchRequest,
    HealthStatus,
    LLMProvider,
    StreamChunk,
    StructuredRequest,
    StructuredResponse,
)
from agent.providers.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerState,
    is_availability_failure,
)
from agent.providers.errors import AllProvidersUnavailable, EgressDenied, ProviderTimeout

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable, Sequence

    from pydantic import BaseModel

__all__ = [
    "ProviderRouter",
    "RouteCandidate",
]

_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RouteCandidate:
    """Candidate LLMProvider registered with the provider router."""

    provider_config_id: UUID
    provider: LLMProvider
    residency_tier: str
    priority: int


class ProviderRouter:
    """Multi-candidate router with residency locking, circuit breaking and air-gap guard."""

    def __init__(
        self,
        workspace_id: UUID | str,
        candidates: Sequence[RouteCandidate],
        *,
        air_gap_mode: bool | None = None,
        breakers: CircuitBreaker | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        """Initialize provider router for a specific workspace and candidate set."""
        self.workspace_id: UUID = UUID(str(workspace_id))
        self._candidates: list[RouteCandidate] = list(candidates)
        self.air_gap_mode: bool | None = air_gap_mode
        self._clock: Callable[[], float] = clock
        self._breakers: CircuitBreaker = (
            breakers if breakers is not None else CircuitBreaker(clock=clock)
        )
        self.last_route_trace: list[dict[str, Any]] = []

    @property
    def residency_tier(self) -> str:
        """Return residency tier of the primary candidate."""
        if self._candidates:
            sorted_candidates = sorted(self._candidates, key=lambda c: c.priority)
            return sorted_candidates[0].residency_tier
        return "router"

    def _record_trace(
        self,
        candidate_id: UUID,
        outcome: str,
        state: str,
        ttft_ms: float | None = None,
    ) -> None:
        self.last_route_trace.append(
            {
                "provider_config_id": str(candidate_id),
                "outcome": outcome,
                "breaker_state": state,
                "ttft_ms": ttft_ms,
            }
        )

    def _is_candidate_available(self, candidate_id: UUID) -> bool:
        st = self._breakers.get_state(self.workspace_id, candidate_id)
        if st == CircuitBreakerState.OPEN:
            self._record_trace(candidate_id, "skipped_breaker_open", st.value)
            return False
        if not self._breakers.can_attempt(self.workspace_id, candidate_id):
            self._record_trace(candidate_id, "skipped_probe_in_flight", st.value)
            return False
        return True

    def _get_candidate_kind(self, candidate: RouteCandidate) -> str:
        kind = getattr(candidate.provider, "kind", None)
        if isinstance(kind, str) and kind:
            return kind.lower()
        c_name = candidate.provider.__class__.__name__.lower()
        if "ollama" in c_name or "local" in candidate.residency_tier.lower():
            return "ollama"
        if "fixture" in c_name or "fixture" in candidate.residency_tier.lower():
            return "fixture"
        if "gemini" in c_name:
            return "gemini"
        if "openai" in c_name:
            return "openai"
        return candidate.residency_tier.lower()

    def _get_eligible_candidates(self) -> list[RouteCandidate]:
        candidates = self._candidates

        if self.air_gap_mode is not False:
            allowed: list[RouteCandidate] = []
            for c in candidates:
                kind = self._get_candidate_kind(c)
                try:
                    AirGapGuard.check(kind, air_gap_mode=self.air_gap_mode)
                    allowed.append(c)
                except EgressDenied:
                    pass
            candidates = allowed

        if not candidates:
            msg = "No provider available in residency tier"
            raise AllProvidersUnavailable(msg, code="NO_PROVIDER_IN_RESIDENCY_TIER")

        sorted_candidates = sorted(candidates, key=lambda c: c.priority)

        first_candidate: RouteCandidate | None = None
        for c in sorted_candidates:
            st = self._breakers.get_state(self.workspace_id, c.provider_config_id)
            if st != CircuitBreakerState.OPEN:
                first_candidate = c
                break

        if first_candidate is None:
            msg = "All candidate providers unavailable (circuit breakers OPEN)"
            raise AllProvidersUnavailable(msg, code="NO_PROVIDER_IN_RESIDENCY_TIER")

        target_residency = first_candidate.residency_tier
        eligible = [c for c in sorted_candidates if c.residency_tier == target_residency]
        return eligible[:3]

    async def _try_get_first_chunk(
        self,
        stream_iter: AsyncIterator[StreamChunk],
        ttft_deadline_ms: int | None,
    ) -> StreamChunk:
        if ttft_deadline_ms is not None:
            timeout_s = ttft_deadline_ms / 1000.0
            try:
                async with asyncio.timeout(timeout_s):
                    return await anext(stream_iter)
            except TimeoutError as err:
                if hasattr(stream_iter, "aclose"):
                    await stream_iter.aclose()
                msg = f"TTFT SLA breached ({ttft_deadline_ms}ms)"
                raise ProviderTimeout(msg, code="TIMEOUT") from err
        return await anext(stream_iter)

    @staticmethod
    async def _stream_tail(
        stream_iter: AsyncIterator[StreamChunk],
    ) -> AsyncIterator[StreamChunk]:
        try:
            async for chunk in stream_iter:
                yield chunk
        except Exception:
            if hasattr(stream_iter, "aclose"):
                await stream_iter.aclose()
            raise

    async def stream_complete(self, req: CompletionRequest) -> AsyncIterator[StreamChunk]:
        """Stream token chunks across eligible candidates with failover before first chunk."""
        self.last_route_trace = []
        eligible = self._get_eligible_candidates()
        last_err: BaseException | None = None

        for candidate in eligible:
            cid = candidate.provider_config_id
            if not self._is_candidate_available(cid):
                continue

            stream_iter = candidate.provider.stream_complete(req)
            try:
                first_chunk = await self._try_get_first_chunk(stream_iter, req.ttft_deadline_ms)
            except StopAsyncIteration:
                self._breakers.record_success(self.workspace_id, cid)
                st = self._breakers.get_state(self.workspace_id, cid)
                self._record_trace(cid, "success", st.value)
                return
            except Exception as err:
                last_err = err
                st = self._breakers.get_state(self.workspace_id, cid)
                if not is_availability_failure(err):
                    self._record_trace(cid, "policy_or_content_error", st.value)
                    raise
                self._breakers.record_failure(self.workspace_id, cid, err)
                new_st = self._breakers.get_state(self.workspace_id, cid)
                self._record_trace(cid, "failure", new_st.value)
                continue

            self._breakers.record_success(self.workspace_id, cid)
            st = self._breakers.get_state(self.workspace_id, cid)
            self._record_trace(cid, "success", st.value, first_chunk.ttft_ms)
            yield first_chunk

            async for chunk in self._stream_tail(stream_iter):
                yield chunk
            return

        msg = "All candidate providers failed in residency tier"
        if last_err is not None:
            raise AllProvidersUnavailable(msg, code="NO_PROVIDER_IN_RESIDENCY_TIER") from last_err
        raise AllProvidersUnavailable(msg, code="NO_PROVIDER_IN_RESIDENCY_TIER")

    async def generate_structured[TModel: BaseModel](
        self, req: StructuredRequest[TModel]
    ) -> StructuredResponse[TModel]:
        """Generate structured output with same-residency failover and TTFT timeout."""
        self.last_route_trace = []
        eligible = self._get_eligible_candidates()
        last_err: BaseException | None = None

        for candidate in eligible:
            cid = candidate.provider_config_id
            if not self._is_candidate_available(cid):
                continue

            try:
                if req.ttft_deadline_ms is not None:
                    timeout_s = req.ttft_deadline_ms / 1000.0
                    try:
                        async with asyncio.timeout(timeout_s):
                            resp = await candidate.provider.generate_structured(req)
                    except TimeoutError as err:
                        msg = f"TTFT SLA breached ({req.ttft_deadline_ms}ms)"
                        raise ProviderTimeout(msg, code="TIMEOUT") from err
                else:
                    resp = await candidate.provider.generate_structured(req)
            except Exception as err:
                last_err = err
                st = self._breakers.get_state(self.workspace_id, cid)
                if not is_availability_failure(err):
                    self._record_trace(cid, "policy_or_content_error", st.value)
                    raise
                self._breakers.record_failure(self.workspace_id, cid, err)
                new_st = self._breakers.get_state(self.workspace_id, cid)
                self._record_trace(cid, "failure", new_st.value)
                continue

            self._breakers.record_success(self.workspace_id, cid)
            st = self._breakers.get_state(self.workspace_id, cid)
            self._record_trace(cid, "success", st.value, resp.ttft_ms)
            return resp

        msg = "All candidate providers failed in residency tier"
        if last_err is not None:
            raise AllProvidersUnavailable(msg, code="NO_PROVIDER_IN_RESIDENCY_TIER") from last_err
        raise AllProvidersUnavailable(msg, code="NO_PROVIDER_IN_RESIDENCY_TIER")

    async def embed_batch(self, req: EmbedBatchRequest) -> list[list[float]]:
        """Generate vector embeddings with same-residency failover."""
        self.last_route_trace = []
        eligible = self._get_eligible_candidates()
        last_err: BaseException | None = None

        for candidate in eligible:
            cid = candidate.provider_config_id
            if not self._is_candidate_available(cid):
                continue

            try:
                vectors = await candidate.provider.embed_batch(req)
            except Exception as err:
                last_err = err
                st = self._breakers.get_state(self.workspace_id, cid)
                if not is_availability_failure(err):
                    self._record_trace(cid, "policy_or_content_error", st.value)
                    raise
                self._breakers.record_failure(self.workspace_id, cid, err)
                new_st = self._breakers.get_state(self.workspace_id, cid)
                self._record_trace(cid, "failure", new_st.value)
                continue

            self._breakers.record_success(self.workspace_id, cid)
            st = self._breakers.get_state(self.workspace_id, cid)
            self._record_trace(cid, "success", st.value, None)
            return vectors

        msg = "All candidate providers failed in residency tier"
        if last_err is not None:
            raise AllProvidersUnavailable(msg, code="NO_PROVIDER_IN_RESIDENCY_TIER") from last_err
        raise AllProvidersUnavailable(msg, code="NO_PROVIDER_IN_RESIDENCY_TIER")

    async def health_probe(self) -> HealthStatus:
        """Probe candidate health, returning first successful response."""
        eligible = self._get_eligible_candidates()
        for candidate in eligible:
            cid = candidate.provider_config_id
            if not self._is_candidate_available(cid):
                continue
            try:
                status = await candidate.provider.health_probe()
                if status.ok:
                    self._breakers.record_success(self.workspace_id, cid)
                    return status
            except Exception as err:  # noqa: BLE001
                _logger.debug("Candidate health probe failed: %s", err)
        return HealthStatus(ok=False, latency_ms=0.0, detail="All providers unhealthy")
