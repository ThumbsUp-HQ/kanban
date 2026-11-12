# Copyright 2026 Kanban Platform Contributors
"""Per-(workspace, provider) circuit breakers for LLM provider resilience."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from agent.providers.errors import (
    ProviderHTTPError,
    ProviderPolicyError,
    ProviderRefusal,
    ProviderSafetyBlock,
    ProviderSchemaError,
    ProviderTimeout,
    ProviderUnavailable,
)

if TYPE_CHECKING:
    from collections.abc import Callable
    from uuid import UUID

__all__ = [
    "DEFAULT_FAILURE_THRESHOLD",
    "DEFAULT_OPEN_COOLDOWN_S",
    "MAX_COOLDOWN_S",
    "CircuitBreaker",
    "CircuitBreakerEntry",
    "CircuitBreakerState",
    "is_availability_failure",
]

_logger = logging.getLogger(__name__)

DEFAULT_FAILURE_THRESHOLD: int = 5
DEFAULT_OPEN_COOLDOWN_S: float = 30.0
MAX_COOLDOWN_S: float = 300.0

_HTTP_STATUS_TOO_MANY_REQUESTS: int = 429
_HTTP_STATUS_INTERNAL_ERROR: int = 500


def is_availability_failure(err: BaseException) -> bool:
    """Return True if error represents an availability or transient network failure.

    Trip conditions: ProviderHTTPError (status 429 or >= 500), ProviderTimeout,
    ProviderUnavailable.
    Content and policy outcomes (ProviderSchemaError, ProviderSafetyBlock,
    ProviderRefusal, ProviderPolicyError) do NOT count as availability failures.
    """
    if isinstance(
        err,
        (
            ProviderSchemaError,
            ProviderSafetyBlock,
            ProviderRefusal,
            ProviderPolicyError,
        ),
    ):
        return False
    if isinstance(err, ProviderHTTPError):
        return (
            err.status == _HTTP_STATUS_TOO_MANY_REQUESTS
            or err.status >= _HTTP_STATUS_INTERNAL_ERROR
        )
    return isinstance(err, (ProviderTimeout, ProviderUnavailable))


class CircuitBreakerState(StrEnum):
    """Three-state circuit breaker state machine."""

    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


@dataclass
class CircuitBreakerEntry:
    """Internal state representation for a single (workspace_id, provider_config_id) breaker."""

    workspace_id: UUID
    provider_config_id: UUID
    state: CircuitBreakerState = CircuitBreakerState.CLOSED
    consecutive_failures: int = 0
    opened_at: float = 0.0
    cooldown_until: float = 0.0
    probe_in_flight: bool = False


class CircuitBreaker:
    """Registry and state machine for per-(workspace, provider) circuit breakers.

    State key: (workspace_id: UUID, provider_config_id: UUID).
    Registry is an in-process dictionary (per-replica state).
    Clock is injected (Callable[[], float]) so tests never sleep.
    """

    def __init__(
        self,
        *,
        failure_threshold: int = DEFAULT_FAILURE_THRESHOLD,
        open_cooldown_s: float = DEFAULT_OPEN_COOLDOWN_S,
        max_cooldown_s: float = MAX_COOLDOWN_S,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        """Initialize circuit breaker registry with configurable thresholds and clock."""
        self.failure_threshold: int = failure_threshold
        self.open_cooldown_s: float = open_cooldown_s
        self.max_cooldown_s: float = max_cooldown_s
        self._clock: Callable[[], float] = clock
        self._entries: dict[tuple[UUID, UUID], CircuitBreakerEntry] = {}
        self._transition_log: list[dict[str, object]] = []

    @property
    def transition_log(self) -> list[dict[str, object]]:
        """Return shallow copy of recorded state transition history."""
        return list(self._transition_log)

    def _get_entry(self, workspace_id: UUID, provider_config_id: UUID) -> CircuitBreakerEntry:
        key = (workspace_id, provider_config_id)
        entry = self._entries.get(key)
        if entry is None:
            entry = CircuitBreakerEntry(
                workspace_id=workspace_id,
                provider_config_id=provider_config_id,
            )
            self._entries[key] = entry
        return entry

    def _log_transition(
        self,
        entry: CircuitBreakerEntry,
        old_state: CircuitBreakerState,
        new_state: CircuitBreakerState,
        reason: str,
    ) -> None:
        now = self._clock()
        record: dict[str, object] = {
            "timestamp": now,
            "workspace_id": str(entry.workspace_id),
            "provider_config_id": str(entry.provider_config_id),
            "old_state": old_state.value,
            "new_state": new_state.value,
            "reason": reason,
        }
        self._transition_log.append(record)
        _logger.info(
            "[t=%.2fs] Breaker (%s, %s): %s -> %s (reason: %s)",
            now,
            entry.workspace_id,
            entry.provider_config_id,
            old_state.value,
            new_state.value,
            reason,
        )

    def get_state(self, workspace_id: UUID, provider_config_id: UUID) -> CircuitBreakerState:
        """Return current state, advancing from OPEN to HALF_OPEN if cooldown elapsed."""
        entry = self._get_entry(workspace_id, provider_config_id)
        now = self._clock()
        if entry.state == CircuitBreakerState.OPEN and now >= entry.cooldown_until:
            old_state = entry.state
            entry.state = CircuitBreakerState.HALF_OPEN
            entry.probe_in_flight = False
            self._log_transition(entry, old_state, entry.state, "Cooldown elapsed, ready to probe")
        return entry.state

    def can_attempt(self, workspace_id: UUID, provider_config_id: UUID) -> bool:
        """Evaluate if an outbound call may proceed, admitting exactly 1 probe in HALF_OPEN."""
        entry = self._get_entry(workspace_id, provider_config_id)
        now = self._clock()
        if entry.state == CircuitBreakerState.OPEN:
            if now >= entry.cooldown_until:
                old_state = entry.state
                entry.state = CircuitBreakerState.HALF_OPEN
                entry.probe_in_flight = True
                self._log_transition(
                    entry,
                    old_state,
                    entry.state,
                    "Cooldown elapsed, admitted 1 probe",
                )
                return True
            return False

        if entry.state == CircuitBreakerState.HALF_OPEN:
            if not entry.probe_in_flight:
                entry.probe_in_flight = True
                return True
            return False

        return True

    def record_success(self, workspace_id: UUID, provider_config_id: UUID) -> None:
        """Record successful invocation, resetting failure count and closing breaker."""
        entry = self._get_entry(workspace_id, provider_config_id)
        old_state = entry.state
        entry.consecutive_failures = 0
        entry.probe_in_flight = False
        if old_state != CircuitBreakerState.CLOSED:
            entry.state = CircuitBreakerState.CLOSED
            self._log_transition(
                entry,
                old_state,
                entry.state,
                "Probe call succeeded, reset consecutive failures to 0",
            )

    def record_failure(
        self,
        workspace_id: UUID,
        provider_config_id: UUID,
        err: BaseException | None = None,
        *,
        retry_after_s: float | None = None,
    ) -> None:
        """Record invocation failure; trips to OPEN if threshold reached or probe failed."""
        if err is not None and not is_availability_failure(err):
            return

        entry = self._get_entry(workspace_id, provider_config_id)
        now = self._clock()

        if retry_after_s is None and isinstance(err, ProviderHTTPError):
            retry_after_s = err.retry_after_s

        cooldown = self.open_cooldown_s
        if retry_after_s is not None:
            cooldown = max(self.open_cooldown_s, float(retry_after_s))
        cooldown = min(cooldown, self.max_cooldown_s)

        old_state = entry.state
        if entry.state == CircuitBreakerState.HALF_OPEN:
            entry.state = CircuitBreakerState.OPEN
            entry.opened_at = now
            entry.cooldown_until = now + cooldown
            entry.probe_in_flight = False
            self._log_transition(
                entry,
                old_state,
                entry.state,
                f"Probe call failed, cooldown restarted for {cooldown:.1f}s",
            )
            return

        entry.consecutive_failures += 1
        if entry.consecutive_failures >= self.failure_threshold:
            entry.state = CircuitBreakerState.OPEN
            entry.opened_at = now
            entry.cooldown_until = now + cooldown
            entry.probe_in_flight = False
            self._log_transition(
                entry,
                old_state,
                entry.state,
                f"Consecutive failures ({entry.consecutive_failures}) reached threshold "
                f"({self.failure_threshold}), open for {cooldown:.1f}s",
            )

    def reset(
        self,
        workspace_id: UUID | None = None,
        provider_config_id: UUID | None = None,
    ) -> None:
        """Reset state for a specific key or all recorded breakers."""
        if workspace_id is not None and provider_config_id is not None:
            self._entries.pop((workspace_id, provider_config_id), None)
        else:
            self._entries.clear()
            self._transition_log.clear()
