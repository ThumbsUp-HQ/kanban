# Copyright 2026 Kanban Platform Contributors
"""Vendor-neutral LLM provider abstractions, DTOs, and error hierarchy."""

from agent.providers.air_gap import AirGapGuard
from agent.providers.base import (
    CLIRunner,
    CLIRunRequest,
    CLIRunResult,
    CompletionRequest,
    EmbedBatchRequest,
    HealthStatus,
    LLMProvider,
    StreamChunk,
    StructuredRequest,
    StructuredResponse,
    ToolCallStep,
)
from agent.providers.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerState,
    is_availability_failure,
)
from agent.providers.errors import (
    AllProvidersUnavailable,
    EgressDenied,
    ProviderError,
    ProviderHTTPError,
    ProviderPolicyError,
    ProviderProtocolError,
    ProviderRefusal,
    ProviderSafetyBlock,
    ProviderSchemaError,
    ProviderTimeout,
    ProviderUnavailable,
    redact_secrets,
)
from agent.providers.router import ProviderRouter, RouteCandidate

__all__ = [
    "AirGapGuard",
    "AllProvidersUnavailable",
    "CLIRunRequest",
    "CLIRunResult",
    "CLIRunner",
    "CircuitBreaker",
    "CircuitBreakerState",
    "CompletionRequest",
    "EgressDenied",
    "EmbedBatchRequest",
    "HealthStatus",
    "LLMProvider",
    "ProviderError",
    "ProviderHTTPError",
    "ProviderPolicyError",
    "ProviderProtocolError",
    "ProviderRefusal",
    "ProviderRouter",
    "ProviderSafetyBlock",
    "ProviderSchemaError",
    "ProviderTimeout",
    "ProviderUnavailable",
    "RouteCandidate",
    "StreamChunk",
    "StructuredRequest",
    "StructuredResponse",
    "ToolCallStep",
    "is_availability_failure",
    "redact_secrets",
]
