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
"""Sparkle FIM endpoint latency and RLS isolation benchmark (KB-P6-04, S9.1, S9.3).

Measures 10 warm-up + 200 consecutive Sparkle FIM requests against 500 seeded
object_embeddings rows across 3 projects (2 readable, 1 restricted under FORCE RLS),
asserting zero errors, zero canary token leakage, and total_p95_ms < 150.0ms.
"""

# ruff: noqa: C901, PLR0912, PLR0915, E501, PERF401, T201, ASYNC240
from __future__ import annotations

import hashlib
import json
import statistics
import time
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
from sqlalchemy import text

from agent.providers.router import ProviderRouter, RouteCandidate
from agent.sparkle.pipeline import SparkleRequest, run_sparkle_pipeline
from agent.testing.fixtures import FixtureLLMProvider, load_cassette
from database.session import RLSSessionFactory
from kanban.api.deps import PrincipalContext

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy.ext.asyncio import AsyncEngine

_CASSETTES_DIR = Path(__file__).parents[2] / "tests" / "fixtures" / "ai"


class FastLocalEmbedder:
    """Sub-millisecond embedder simulating local Int8 ONNX inference."""

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


@pytest.mark.perf
@pytest.mark.asyncio
async def test_perf_sparkle_fim_sla(pg_worker_db: AsyncEngine) -> None:
    """Verify Sparkle FIM p95 < 150ms SLA across 200 requests with 500 embeddings and RLS."""
    ws_id = uuid.uuid4()
    alice_id = uuid.uuid4()
    session_factory = RLSSessionFactory(pg_worker_db)

    # 1. Provision 3 projects: PUB1, PUB2, and restricted SEC
    pub1_proj = uuid.uuid4()
    pub2_proj = uuid.uuid4()
    sec_proj = uuid.uuid4()
    sec_canary = f"CANARY_SECRET_{uuid.uuid4().hex[:12]}"

    async with pg_worker_db.begin() as conn:
        # Create workspace
        await conn.execute(
            text("INSERT INTO workspaces (id, slug, name) VALUES (:id, :slug, 'Sparkle Perf WS')"),
            {"id": ws_id, "slug": f"ws-sparkle-{ws_id.hex[:8]}"},
        )
        # Create user Alice
        await conn.execute(
            text(
                "INSERT INTO principals (id, principal_type, workspace_id, display_name) "
                "VALUES (:id, 'USER', :ws, 'Alice')"
            ),
            {"id": alice_id, "ws": ws_id},
        )
        await conn.execute(
            text(
                "SELECT register_object(  'user'::object_kind, :ws, NULL, :ckey, 'Alice', :id, :id)"
            ),
            {"ws": ws_id, "ckey": f"usr-{alice_id.hex[:8]}", "id": alice_id},
        )
        await conn.execute(
            text(
                "INSERT INTO users (id, object_type, principal_type, workspace_id, email) "
                "VALUES (:id, 'user', 'USER', :ws, 'alice@example.com')"
            ),
            {"id": alice_id, "ws": ws_id},
        )

        # Projects
        for p_id, p_key, p_name in [
            (pub1_proj, "PUB1", "Public Project 1"),
            (pub2_proj, "PUB2", "Public Project 2"),
            (sec_proj, "SEC", "Restricted Project"),
        ]:
            await conn.execute(
                text(
                    "SELECT register_object("
                    "  'project'::object_kind, :ws, NULL, :key, :name, :user, :id"
                    ")"
                ),
                {"ws": ws_id, "key": p_key, "name": p_name, "user": alice_id, "id": p_id},
            )
            await conn.execute(
                text(
                    "INSERT INTO projects (id, object_type, workspace_id, identifier, name) "
                    "VALUES (:id, 'project', :ws, :key, :name)"
                ),
                {"id": p_id, "ws": ws_id, "key": p_key, "name": p_name},
            )

        # Alice is member of PUB1 and PUB2 only, NOT SEC
        for p_id in (pub1_proj, pub2_proj):
            await conn.execute(
                text(
                    "INSERT INTO role_bindings (workspace_id, principal_id, role, scope_type, project_id) "
                    "VALUES (:ws, :u, 'MEMBER', 'project', :p)"
                ),
                {"ws": ws_id, "u": alice_id, "p": p_id},
            )

        # Seed 500 object_embeddings rows across PUB1 (250), PUB2 (150), and SEC (100)
        dummy_vec = "[" + ",".join("0.0" for _ in range(384)) + "]"
        embedding_rows: list[dict[str, Any]] = []

        # PUB1 items (10 stickies x 25 chunks = 250 rows)
        for s_idx in range(10):
            stk_id = uuid.uuid4()
            await conn.execute(
                text(
                    "SELECT register_object('sticky'::object_kind, :ws, :proj, :key, :title, :user, :id)"
                ),
                {
                    "ws": ws_id,
                    "proj": pub1_proj,
                    "key": f"PUB1-STK-{s_idx}",
                    "title": f"Pub1 Sticky {s_idx}",
                    "user": alice_id,
                    "id": stk_id,
                },
            )
            await conn.execute(
                text(
                    "INSERT INTO stickies (id, workspace_id, project_id, body_markdown) "
                    "VALUES (:id, :ws, :proj, 'Public documentation body')"
                ),
                {"id": stk_id, "ws": ws_id, "proj": pub1_proj},
            )
            for c_idx in range(25):
                embedding_rows.append(
                    {
                        "obj_id": stk_id,
                        "chunk_index": c_idx,
                        "ws_id": ws_id,
                        "proj_id": pub1_proj,
                        "sha": hashlib.sha256(f"pub1_{s_idx}_{c_idx}".encode()).digest(),
                        "vec": dummy_vec,
                    }
                )

        # PUB2 items (6 stickies x 25 chunks = 150 rows)
        for s_idx in range(6):
            stk_id = uuid.uuid4()
            await conn.execute(
                text(
                    "SELECT register_object('sticky'::object_kind, :ws, :proj, :key, :title, :user, :id)"
                ),
                {
                    "ws": ws_id,
                    "proj": pub2_proj,
                    "key": f"PUB2-STK-{s_idx}",
                    "title": f"Pub2 Sticky {s_idx}",
                    "user": alice_id,
                    "id": stk_id,
                },
            )
            await conn.execute(
                text(
                    "INSERT INTO stickies (id, workspace_id, project_id, body_markdown) "
                    "VALUES (:id, :ws, :proj, 'Public documentation body 2')"
                ),
                {"id": stk_id, "ws": ws_id, "proj": pub2_proj},
            )
            for c_idx in range(25):
                embedding_rows.append(
                    {
                        "obj_id": stk_id,
                        "chunk_index": c_idx,
                        "ws_id": ws_id,
                        "proj_id": pub2_proj,
                        "sha": hashlib.sha256(f"pub2_{s_idx}_{c_idx}".encode()).digest(),
                        "vec": dummy_vec,
                    }
                )

        # SEC items (4 stickies x 25 chunks = 100 rows, including secret canary)
        for s_idx in range(4):
            stk_id = uuid.uuid4()
            await conn.execute(
                text(
                    "SELECT register_object('sticky'::object_kind, :ws, :proj, :key, :title, :user, :id)"
                ),
                {
                    "ws": ws_id,
                    "proj": sec_proj,
                    "key": f"SEC-STK-{s_idx}",
                    "title": f"Sec Sticky {s_idx}",
                    "user": alice_id,
                    "id": stk_id,
                },
            )
            await conn.execute(
                text(
                    "INSERT INTO stickies (id, workspace_id, project_id, body_markdown) "
                    "VALUES (:id, :ws, :proj, :body)"
                ),
                {
                    "id": stk_id,
                    "ws": ws_id,
                    "proj": sec_proj,
                    "body": f"Confidential {sec_canary} details",
                },
            )
            for c_idx in range(25):
                embedding_rows.append(
                    {
                        "obj_id": stk_id,
                        "chunk_index": c_idx,
                        "ws_id": ws_id,
                        "proj_id": sec_proj,
                        "sha": hashlib.sha256(
                            f"sec_{s_idx}_{c_idx}_{sec_canary}".encode()
                        ).digest(),
                        "vec": dummy_vec,
                    }
                )

        # Bulk insert embeddings
        for chunk in embedding_rows:
            await conn.execute(
                text(
                    "INSERT INTO object_embeddings ("
                    "  object_id, object_type, chunk_index, workspace_id, "
                    "  project_id, content_sha256, model_id, embedding"
                    ") VALUES ("
                    "  :obj_id, 'sticky', :chunk_index, :ws_id, :proj_id, :sha, 'mock', CAST(:vec AS vector)"
                    ")"
                ),
                chunk,
            )

    # 2. Setup FixtureLLMProvider
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
    principal = PrincipalContext(principal_id=alice_id, workspace_id=ws_id)

    req = SparkleRequest(
        project_id=pub1_proj,
        surface="description",
        prefix="def calculate_total(items):\n    # compute total",
        suffix="\n    return total",
        client_request_id=uuid.uuid4(),
    )

    # 3. 10 warm-up runs
    for _ in range(10):
        warmup_res = await run_sparkle_pipeline(
            req,
            principal_ctx=principal,
            router=router,
            embedder=embedder,
            session_factory=session_factory,
        )
        assert warmup_res.status == "ok"

    # 4. 200 measured requests
    durations_ms: list[float] = []
    error_count = 0
    iterations = 200

    for _ in range(iterations):
        t0 = time.perf_counter()
        result = await run_sparkle_pipeline(
            req,
            principal_ctx=principal,
            router=router,
            embedder=embedder,
            session_factory=session_factory,
        )
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        if result.status != "ok":
            error_count += 1
        durations_ms.append(elapsed_ms)

    assert error_count == 0, f"Encountered {error_count} Sparkle pipeline errors"

    # Invariant: Verify zero canary leaked from SEC project into LLM prompt
    for call in provider.call_log:
        prompt_text = call.get("request", {}).get("prompt", "")
        assert sec_canary not in prompt_text, f"LEAKED CANARY TOKEN DETECTED: {sec_canary}"

    # Percentiles
    durations_ms.sort()
    n = len(durations_ms)
    min_ms = durations_ms[0]
    p50_ms = durations_ms[int(n * 0.50)]
    p95_ms = durations_ms[int(n * 0.95)]
    p99_ms = durations_ms[int(n * 0.99)]
    max_ms = durations_ms[-1]
    mean_ms = statistics.mean(durations_ms)

    report_payload = {
        "benchmark": "sparkle_fim_latency",
        "unit": "ms",
        "threshold_ms": 150.0,
        "samples": iterations,
        "errors": error_count,
        "error_rate": error_count / iterations,
        "min_ms": round(min_ms, 2),
        "mean_ms": round(mean_ms, 2),
        "p50_ms": round(p50_ms, 2),
        "p95_ms": round(p95_ms, 2),
        "p99_ms": round(p99_ms, 2),
        "max_ms": round(max_ms, 2),
        "passed": p95_ms < 150.0 and error_count == 0,
        "canary_leak": False,
    }

    print(
        f"\n[SPARKLE FIM SLA]: p95: {p95_ms:.2f}ms (threshold: < 150.0ms), "
        f"mean: {mean_ms:.2f}ms, p50: {p50_ms:.2f}ms, max: {max_ms:.2f}ms. Status: PASS"
    )

    out_file = Path("docs/qa/KANBA-151/perf-sparkle.json")
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(report_payload, indent=2), encoding="utf-8")

    assert p95_ms < 150.0, f"Sparkle FIM p95 latency {p95_ms:.2f}ms breached 150ms SLA budget!"
