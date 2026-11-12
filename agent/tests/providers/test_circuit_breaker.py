# Copyright 2026 Kanban Platform Contributors
"""Unit tests for per-(workspace, provider) circuit breakers."""

from __future__ import annotations

from uuid import uuid4

from agent.providers.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerState,
    is_availability_failure,
)
from agent.providers.errors import (
    ProviderHTTPError,
    ProviderPolicyError,
    ProviderRefusal,
    ProviderSafetyBlock,
    ProviderSchemaError,
    ProviderTimeout,
    ProviderUnavailable,
)


class FakeClock:
    """Controllable monotonic clock for hermetic circuit breaker tests."""

    def __init__(self, initial_time: float = 1000.0) -> None:
        """Initialize fake clock with starting monotonic timestamp."""
        self._current_time: float = initial_time

    def __call__(self) -> float:
        """Return current simulated monotonic timestamp."""
        return self._current_time

    def advance(self, seconds: float) -> None:
        """Advance simulated monotonic clock forward by seconds."""
        self._current_time += seconds


def test_is_availability_failure() -> None:
    """Verify availability vs policy/content error categorization."""
    assert is_availability_failure(ProviderHTTPError("rate limit", status=429))
    assert is_availability_failure(ProviderHTTPError("server error", status=500))
    assert is_availability_failure(ProviderHTTPError("service unavailable", status=503))
    assert is_availability_failure(ProviderTimeout("timeout"))
    assert is_availability_failure(ProviderUnavailable("offline"))

    assert not is_availability_failure(ProviderHTTPError("bad request", status=400))
    assert not is_availability_failure(ProviderHTTPError("not found", status=404))
    assert not is_availability_failure(ProviderSchemaError("schema error"))
    assert not is_availability_failure(ProviderSafetyBlock("safety block"))
    assert not is_availability_failure(ProviderRefusal("model refused"))
    assert not is_availability_failure(ProviderPolicyError("policy error"))


def test_case_2_breaker_transitions_and_probe_lifecycle() -> None:
    """Case 2: 5x 503 -> OPEN; 6th skips; after 30s -> HALF_OPEN admits 1 probe; probe life."""
    clock = FakeClock(100.0)
    breaker = CircuitBreaker(failure_threshold=5, open_cooldown_s=30.0, clock=clock)
    ws_id = uuid4()
    provider_id = uuid4()

    # Step 1: 5 consecutive 503 errors transition state from CLOSED to OPEN
    for i in range(1, 6):
        assert breaker.get_state(ws_id, provider_id) == CircuitBreakerState.CLOSED
        assert breaker.can_attempt(ws_id, provider_id)
        breaker.record_failure(ws_id, provider_id, ProviderHTTPError("503", status=503))
        st = breaker.get_state(ws_id, provider_id)
        print(f"[t={clock():.2f}s] Failure {i}/5 recorded. State: {st}")  # noqa: T201

    assert breaker.get_state(ws_id, provider_id) == CircuitBreakerState.OPEN

    # Step 2: 6th call skips provider (can_attempt returns False)
    assert not breaker.can_attempt(ws_id, provider_id)
    assert breaker.get_state(ws_id, provider_id) == CircuitBreakerState.OPEN
    print(f"[t={clock():.2f}s] 6th call correctly skipped: can_attempt = False")  # noqa: T201

    # Step 3: Advance fake clock by 29s (still OPEN)
    clock.advance(29.0)
    assert breaker.get_state(ws_id, provider_id) == CircuitBreakerState.OPEN
    assert not breaker.can_attempt(ws_id, provider_id)

    # Advance fake clock by 1s (total 30s elapsed -> transitions to HALF_OPEN)
    clock.advance(1.0)
    print(f"[t={clock():.2f}s] 30s cooldown elapsed. Advancing to HALF_OPEN")  # noqa: T201

    # Probe 1: Admitted
    assert breaker.can_attempt(ws_id, provider_id)
    assert breaker.get_state(ws_id, provider_id) == CircuitBreakerState.HALF_OPEN

    # Second concurrent attempt in HALF_OPEN while probe in-flight is denied
    assert not breaker.can_attempt(ws_id, provider_id)

    # Step 4: Probe success -> CLOSED (counter reset)
    breaker.record_success(ws_id, provider_id)
    print(f"[t={clock():.2f}s] Probe succeeded. State: {breaker.get_state(ws_id, provider_id)}")  # noqa: T201
    assert breaker.get_state(ws_id, provider_id) == CircuitBreakerState.CLOSED
    assert breaker.can_attempt(ws_id, provider_id)

    # Step 5: Test probe failure -> OPEN with cooldown restarted
    for _ in range(5):
        breaker.record_failure(ws_id, provider_id, ProviderHTTPError("503", status=503))
    assert breaker.get_state(ws_id, provider_id) == CircuitBreakerState.OPEN

    clock.advance(30.0)
    assert breaker.can_attempt(ws_id, provider_id)
    assert breaker.get_state(ws_id, provider_id) == CircuitBreakerState.HALF_OPEN

    breaker.record_failure(ws_id, provider_id, ProviderHTTPError("503", status=503))
    print(f"[t={clock():.2f}s] Probe failed. State: {breaker.get_state(ws_id, provider_id)}")  # noqa: T201
    assert breaker.get_state(ws_id, provider_id) == CircuitBreakerState.OPEN
    assert not breaker.can_attempt(ws_id, provider_id)


def test_case_3_retry_after_cooldown_extension_and_cap() -> None:
    """Case 3: 429 with Retry-After: 120 -> cooldown 120s; Retry-After: 9999 capped at 300s."""
    clock = FakeClock(200.0)
    breaker = CircuitBreaker(
        failure_threshold=1,
        open_cooldown_s=30.0,
        max_cooldown_s=300.0,
        clock=clock,
    )
    ws_id = uuid4()
    p1 = uuid4()
    p2 = uuid4()

    err_120 = ProviderHTTPError("Too Many Requests", status=429, retry_after_s=120.0)
    breaker.record_failure(ws_id, p1, err_120)
    assert breaker.get_state(ws_id, p1) == CircuitBreakerState.OPEN

    clock.advance(119.0)
    assert not breaker.can_attempt(ws_id, p1)
    clock.advance(1.5)
    assert breaker.can_attempt(ws_id, p1)

    err_9999 = ProviderHTTPError("Too Many Requests", status=429, retry_after_s=9999.0)
    breaker.record_failure(ws_id, p2, err_9999)
    assert breaker.get_state(ws_id, p2) == CircuitBreakerState.OPEN

    clock.advance(299.0)
    assert not breaker.can_attempt(ws_id, p2)
    clock.advance(1.5)
    assert breaker.can_attempt(ws_id, p2)


def test_case_4_schema_error_does_not_trip_breaker() -> None:
    """Case 4: Schema error x10 does not trip (state stays CLOSED)."""
    clock = FakeClock(100.0)
    breaker = CircuitBreaker(failure_threshold=5, clock=clock)
    ws_id = uuid4()
    p_id = uuid4()

    for _ in range(10):
        breaker.record_failure(ws_id, p_id, ProviderSchemaError("Malformed output schema"))

    assert breaker.get_state(ws_id, p_id) == CircuitBreakerState.CLOSED
    assert breaker.can_attempt(ws_id, p_id)


def test_case_11_per_key_workspace_isolation() -> None:
    """Case 11: Breaker OPEN for workspace A does not affect workspace B with same provider."""
    clock = FakeClock(100.0)
    breaker = CircuitBreaker(failure_threshold=2, clock=clock)
    ws_a = uuid4()
    ws_b = uuid4()
    shared_provider_id = uuid4()

    breaker.record_failure(ws_a, shared_provider_id, ProviderTimeout("timeout 1"))
    breaker.record_failure(ws_a, shared_provider_id, ProviderTimeout("timeout 2"))
    assert breaker.get_state(ws_a, shared_provider_id) == CircuitBreakerState.OPEN
    assert not breaker.can_attempt(ws_a, shared_provider_id)

    assert breaker.get_state(ws_b, shared_provider_id) == CircuitBreakerState.CLOSED
    assert breaker.can_attempt(ws_b, shared_provider_id)


def test_breaker_get_state_cooldown_and_closed_success() -> None:
    """Verify get_state directly transitions to HALF_OPEN after cooldown."""
    clock = FakeClock(10.0)
    breaker = CircuitBreaker(failure_threshold=1, open_cooldown_s=10.0, clock=clock)
    ws_id = uuid4()
    p_id = uuid4()

    breaker.record_success(ws_id, p_id)
    assert breaker.get_state(ws_id, p_id) == CircuitBreakerState.CLOSED

    breaker.record_failure(ws_id, p_id, ProviderTimeout("timeout"))
    assert breaker.get_state(ws_id, p_id) == CircuitBreakerState.OPEN

    clock.advance(15.0)
    assert breaker.get_state(ws_id, p_id) == CircuitBreakerState.HALF_OPEN
    assert breaker.can_attempt(ws_id, p_id)


def test_breaker_reset_and_history() -> None:
    """Verify reset functionality and transition log recording."""
    clock = FakeClock(50.0)
    breaker = CircuitBreaker(failure_threshold=1, clock=clock)
    ws_id = uuid4()
    p1 = uuid4()
    p2 = uuid4()

    breaker.record_failure(ws_id, p1, ProviderUnavailable("unavailable"))
    breaker.record_failure(ws_id, p2, ProviderUnavailable("unavailable"))
    assert len(breaker.transition_log) == 2

    breaker.reset(ws_id, p1)
    assert breaker.get_state(ws_id, p1) == CircuitBreakerState.CLOSED
    assert breaker.get_state(ws_id, p2) == CircuitBreakerState.OPEN

    breaker.reset()
    assert breaker.get_state(ws_id, p2) == CircuitBreakerState.CLOSED
    assert len(breaker.transition_log) == 0
