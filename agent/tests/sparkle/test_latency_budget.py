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
"""Latency benchmark and budget verification for Sparkle FIM (Case 10)."""

from __future__ import annotations

import statistics
import time
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from agent.providers.router import ProviderRouter, RouteCandidate
from agent.sparkle.pipeline import SparkleRequest, run_sparkle_pipeline
from agent.testing.fixtures import FixtureLLMProvider, load_cassette
from database.session import RLSSessionFactory
from kanban.api.deps import PrincipalContext

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy.ext.asyncio import AsyncEngine

_CASSETTES_DIR = Path(__file__).parents[3] / "tests" / "fixtures" / "ai"


class FastLocalEmbedder:
    """Sub-millisecond mock embedder simulating local Int8 ONNX inference."""

    @property
    def model_id(self) -> str:
        """Embedder model identifier."""
        return "bge-small-en-v1.5"

    @property
    def dimension(self) -> int:
        """Embedding vector dimension."""
        return 384

    async def embed_batch(self, texts: Sequence[str]) -> list[list[float]]:
        """Return dummy embedding vectors for input texts."""
        vec = [0.0] * 384
        vec[0] = 0.5
        return [vec for _ in texts]


@pytest.mark.asyncio
async def test_case_10_latency_budget_200_iterations(pg_worker_db: AsyncEngine) -> None:
    """Case 10: 200 iterations with sparkle_fim_ok.yaml and clean test DB asserting p95 < 150ms."""
    ws_id = uuid.uuid4()
    principal = PrincipalContext(principal_id=uuid.uuid4(), workspace_id=ws_id)
    session_factory = RLSSessionFactory(pg_worker_db)

    cas = load_cassette(_CASSETTES_DIR / "sparkle_fim_ok.yaml")
    provider = FixtureLLMProvider([cas])
    candidate = RouteCandidate(
        provider_config_id=uuid.uuid4(),
        provider=provider,
        residency_tier="fixture",
        priority=1,
    )
    router = ProviderRouter(
        workspace_id=ws_id,
        candidates=[candidate],
        air_gap_mode=False,
    )
    embedder = FastLocalEmbedder()

    req = SparkleRequest(
        project_id=uuid.uuid4(),
        surface="description",
        prefix="def calculate_total(items):\n    # compute total",
        suffix="",
        client_request_id=uuid.uuid4(),
    )

    # Warmup
    warmup_result = await run_sparkle_pipeline(
        req,
        principal_ctx=principal,
        router=router,
        embedder=embedder,
        session_factory=session_factory,
    )
    assert warmup_result.status == "ok"

    durations_ms: list[float] = []
    iterations = 200

    for _ in range(iterations):
        t_start = time.perf_counter()
        result = await run_sparkle_pipeline(
            req,
            principal_ctx=principal,
            router=router,
            embedder=embedder,
            session_factory=session_factory,
        )
        t_elapsed = (time.perf_counter() - t_start) * 1000.0
        assert result.status == "ok"
        durations_ms.append(t_elapsed)

    durations_ms.sort()

    def p(pct: float) -> float:
        idx = int(pct * len(durations_ms))
        idx = min(idx, len(durations_ms) - 1)
        return durations_ms[idx]

    p50 = p(0.50)
    p90 = p(0.90)
    p95 = p(0.95)
    p99 = p(0.99)
    p_max = durations_ms[-1]
    p_min = durations_ms[0]
    p_mean = statistics.mean(durations_ms)

    # Print formatted percentile report
    report = (
        "\n============================================================\n"
        "SPARKLE FIM LATENCY BENCHMARK REPORT (200 ITERATIONS)\n"
        "============================================================\n"
        f"Total Iterations : {iterations}\n"
        f"Minimum Latency  : {p_min:.2f} ms\n"
        f"Mean Latency     : {p_mean:.2f} ms\n"
        f"p50 Latency      : {p50:.2f} ms\n"
        f"p90 Latency      : {p90:.2f} ms\n"
        f"p95 Latency      : {p95:.2f} ms  (SLA Budget: < 150.0 ms)\n"
        f"p99 Latency      : {p99:.2f} ms\n"
        f"Maximum Latency  : {p_max:.2f} ms\n"
        "============================================================\n"
        f"SLA Compliance   : {'PASS (p95 < 150ms)' if p95 < 150.0 else 'FAIL'}\n"
        "============================================================\n"
    )
    print(report)  # noqa: T201

    assert p95 < 150.0, f"Sparkle FIM p95 latency {p95:.2f}ms breached 150ms SLA budget!"
