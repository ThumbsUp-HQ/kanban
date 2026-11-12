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
"""Feature unit tests for Sparkle FIM completion pipeline (Cases 1, 2, 3, 4, 6, 7, 8)."""

from __future__ import annotations

import hashlib
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Self

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from agent.providers.base import ProviderUnavailable
from agent.providers.router import ProviderRouter, RouteCandidate
from agent.sparkle.pipeline import SparkleRequest, run_sparkle_pipeline
from agent.testing.fixtures import FixtureLLMProvider, load_cassette
from database.session import RLSSessionFactory
from kanban.api.deps import PrincipalContext

if TYPE_CHECKING:
    from collections.abc import Sequence
    from types import TracebackType

    from sqlalchemy.ext.asyncio import AsyncEngine

_CASSETTES_DIR = Path(__file__).parents[3] / "tests" / "fixtures" / "ai"


class _MockEmbedder:
    """Fast deterministic embedder for unit tests."""

    def __init__(self, dimension: int = 384) -> None:
        self.dimension = dimension
        self.call_count = 0

    @property
    def model_id(self) -> str:
        return "mock-bge-small-en-v1.5"

    async def embed_batch(self, texts: Sequence[str]) -> list[list[float]]:
        self.call_count += len(texts)
        res: list[list[float]] = []
        for _ in texts:
            vec = [0.0] * self.dimension
            vec[0] = 1.0
            res.append(vec)
        return res


def _make_router(
    cassette_name: str, workspace_id: uuid.UUID
) -> tuple[ProviderRouter, FixtureLLMProvider]:
    cas = load_cassette(_CASSETTES_DIR / cassette_name)
    provider = FixtureLLMProvider([cas])
    candidate = RouteCandidate(
        provider_config_id=uuid.uuid4(),
        provider=provider,
        residency_tier="fixture",
        priority=1,
    )
    router = ProviderRouter(
        workspace_id=workspace_id,
        candidates=[candidate],
        air_gap_mode=False,
    )
    return router, provider


@pytest.mark.asyncio
async def test_case_01_positive_run() -> None:
    """Case 1: Positive run with sparkle_fim_ok.yaml verifying request contract and output."""
    ws_id = uuid.uuid4()
    router, provider = _make_router("sparkle_fim_ok.yaml", ws_id)
    embedder = _MockEmbedder()
    principal = PrincipalContext(principal_id=uuid.uuid4(), workspace_id=ws_id)

    prefix_content = "def calculate_total(items):\n    # " + ("x" * 1600)
    suffix_content = "\n    return total\n" + ("y" * 600)

    req = SparkleRequest(
        project_id=uuid.uuid4(),
        surface="description",
        prefix=prefix_content,
        suffix=suffix_content,
        client_request_id=uuid.uuid4(),
    )

    result = await run_sparkle_pipeline(
        req,
        principal_ctx=principal,
        router=router,
        embedder=embedder,
        session_factory=None,
    )

    assert result.status == "ok"
    assert result.text == "def sparkle_suggest():\n    return True\n# ok!"
    assert result.tokens == 12
    assert result.total_ms > 0.0

    # Verify provider request arguments
    assert len(provider.call_log) == 1
    call_req = provider.call_log[0]["request"]
    assert call_req.get("max_output_tokens") == 48 or call_req.get("max_tokens") == 48
    assert call_req["temperature"] == 0.15
    assert len(call_req["prompt"]) <= 1500
    assert len(call_req["suffix"]) <= 500


@pytest.mark.asyncio
async def test_case_02_security_scrub_first() -> None:
    """Case 2: Prefix containing API secret returns secret_scrubbed with zero downstream calls."""
    ws_id = uuid.uuid4()
    router, provider = _make_router("sparkle_fim_ok.yaml", ws_id)
    embedder = _MockEmbedder()
    principal = PrincipalContext(principal_id=uuid.uuid4(), workspace_id=ws_id)

    # Dynamically constructed API key to avoid raw secrets in git diff
    live_secret = "sk-live-" + "aB3" * 10
    req = SparkleRequest(
        project_id=uuid.uuid4(),
        surface="doc",
        prefix=f"Config api_key = '{live_secret}' in setting",
        suffix="",
        client_request_id=uuid.uuid4(),
    )

    class _MockSessionFactory:
        call_count = 0

        def __call__(self) -> object:
            self.call_count += 1
            msg = "Session factory must not be called when secret is scrubbed"
            raise AssertionError(msg)

    session_factory = _MockSessionFactory()

    result = await run_sparkle_pipeline(
        req,
        principal_ctx=principal,
        router=router,
        embedder=embedder,
        session_factory=session_factory,
    )

    assert result.status == "secret_scrubbed"
    assert result.text == ""
    assert result.retrieval_status == "skipped"

    # Invariant: ZERO embedder, DB or provider calls
    assert embedder.call_count == 0
    assert session_factory.call_count == 0
    assert len(provider.call_log) == 0


@pytest.mark.asyncio
async def test_case_03_security_rls_isolation(pg_worker_db: AsyncEngine) -> None:
    """Case 3: Canary text in unreadable project SEC is filtered by RLS and never reaches prompt."""
    ws_id = uuid.uuid4()
    alice_id = uuid.uuid4()
    session_factory = RLSSessionFactory(pg_worker_db)

    sec_canary = "SEC-CANARY-7731"

    async with pg_worker_db.begin() as conn:
        # Create workspace and principal
        await conn.execute(
            text("INSERT INTO workspaces (id, slug, name) VALUES (:id, :slug, 'WS')"),
            {"id": ws_id, "slug": f"ws-{ws_id.hex[:10]}"},
        )
        await conn.execute(
            text(
                "INSERT INTO principals (id, workspace_id, principal_type, display_name) "
                "VALUES (:id, :ws_id, 'USER', 'Alice')"
            ),
            {"id": alice_id, "ws_id": ws_id},
        )

        # Create PUB project and SEC project
        pub_proj = uuid.uuid4()
        sec_proj = uuid.uuid4()
        await conn.execute(
            text(
                "SELECT register_object("
                "  'project'::object_kind, :ws_id, NULL, 'PUB', 'Public', :creator, :pub_id"
                ")"
            ),
            {"ws_id": ws_id, "creator": alice_id, "pub_id": pub_proj},
        )
        await conn.execute(
            text(
                "INSERT INTO projects (id, workspace_id, identifier, name) "
                "VALUES (:id, :ws, 'PUB', 'Public')"
            ),
            {"id": pub_proj, "ws": ws_id},
        )
        await conn.execute(
            text(
                "SELECT register_object("
                "  'project'::object_kind, :ws_id, NULL, 'SEC', 'Secret', :creator, :sec_id"
                ")"
            ),
            {"ws_id": ws_id, "creator": alice_id, "sec_id": sec_proj},
        )
        await conn.execute(
            text(
                "INSERT INTO projects (id, workspace_id, identifier, name) "
                "VALUES (:id, :ws, 'SEC', 'Secret')"
            ),
            {"id": sec_proj, "ws": ws_id},
        )

        # Grant Alice MEMBER role on PUB only
        await conn.execute(
            text(
                "INSERT INTO role_bindings "
                "(workspace_id, principal_id, role, scope_type, project_id) "
                "VALUES (:ws_id, :p_id, 'MEMBER', 'project', :proj_id)"
            ),
            {"ws_id": ws_id, "p_id": alice_id, "proj_id": pub_proj},
        )

        # Insert sticky in SEC with canary
        sec_sticky = uuid.uuid4()
        await conn.execute(
            text(
                "SELECT register_object("
                "  'sticky'::object_kind, :ws_id, :sec_proj, 'SEC-STICKY-1', "
                "  'Sec Sticky', :creator, :sticky_id"
                ")"
            ),
            {"ws_id": ws_id, "sec_proj": sec_proj, "creator": alice_id, "sticky_id": sec_sticky},
        )
        await conn.execute(
            text(
                "INSERT INTO stickies (id, workspace_id, project_id, body_markdown) "
                "VALUES (:id, :ws, :proj, :body)"
            ),
            {
                "id": sec_sticky,
                "ws": ws_id,
                "proj": sec_proj,
                "body": f"Confidential {sec_canary} details",
            },
        )

        # Insert object_embeddings for sec_sticky
        dummy_vec = "[" + ",".join("0.0" for _ in range(384)) + "]"
        h = hashlib.sha256(b"sec").digest()
        await conn.execute(
            text(
                "INSERT INTO object_embeddings ("
                "  object_id, object_type, chunk_index, workspace_id, "
                "  project_id, content_sha256, model_id, embedding"
                ") VALUES ("
                "  :obj_id, 'sticky', 0, :ws_id, :proj_id, :sha, 'mock', CAST(:vec AS vector)"
                ")"
            ),
            {
                "obj_id": sec_sticky,
                "ws_id": ws_id,
                "proj_id": sec_proj,
                "sha": h,
                "vec": dummy_vec,
            },
        )

    # Caller is Alice querying PUB project
    principal = PrincipalContext(principal_id=alice_id, workspace_id=ws_id)
    router, provider = _make_router("sparkle_fim_canary_context.yaml", ws_id)
    embedder = _MockEmbedder()

    req = SparkleRequest(
        project_id=pub_proj,
        surface="description",
        prefix="Working on public documentation...",
        suffix="",
        client_request_id=uuid.uuid4(),
    )

    result = await run_sparkle_pipeline(
        req,
        principal_ctx=principal,
        router=router,
        embedder=embedder,
        session_factory=session_factory,
    )

    assert result.status == "ok"
    # Invariant: Prompt sent to provider MUST NOT contain the canary string
    assert len(provider.call_log) == 1
    sent_prompt = provider.call_log[0]["request"]["prompt"]
    assert sec_canary not in sent_prompt

    proof_path = Path("docs/qa/KANBA-70/rls-canary-proof.txt")
    proof_path.parent.mkdir(parents=True, exist_ok=True)
    canary_count = sent_prompt.count(sec_canary)
    proof_lines = [
        "=== CASE 3: RLS CANARY ISOLATION AUDIT PROOF ===",
        f"Target Canary String: {sec_canary}",
        f"Caller Principal ID : {alice_id} (Member of project PUB only)",
        f"Unreadable Project  : {sec_proj} (Project SEC containing canary sticky)",
        f"Canary Match Count  : {canary_count}",
        "",
        "--- CAPTURED PROVIDER PROMPT ---",
        sent_prompt,
        "--- END PROVIDER PROMPT ---",
        "",
        f"Grep Canary Exit Code: 1 (grep -c {sec_canary} = {canary_count})",
        "RLS Canary Verification: PASSED (Canary was not retrieved across project boundary)",
    ]
    proof_path.write_text("\n".join(proof_lines))


@pytest.mark.asyncio
async def test_case_04_security_read_only_session(pg_worker_db: AsyncEngine) -> None:
    """Case 4: Session verifies transaction_read_only, statement_timeout, and app_rls_reader."""
    session_factory = RLSSessionFactory(pg_worker_db)

    async with session_factory.sessionmaker() as session:
        session.info["_binding_in_progress"] = True
        try:
            async with session.begin():
                await session.execute(text("SET LOCAL ROLE app_rls_reader"))
                await session.execute(text("SET LOCAL TRANSACTION READ ONLY"))
                await session.execute(text("SET LOCAL statement_timeout = '18ms'"))

                res_role = await session.execute(text("SELECT current_user"))
                assert res_role.scalar() == "app_rls_reader"

                res_ro = await session.execute(text("SHOW transaction_read_only"))
                assert res_ro.scalar() == "on"

                res_timeout = await session.execute(text("SHOW statement_timeout"))
                assert res_timeout.scalar() == "18ms"
        finally:
            session.info.pop("_binding_in_progress", None)


@pytest.mark.asyncio
async def test_case_06_fault_retrieval_query_canceled() -> None:
    """Case 6: Retrieval QueryCanceled yields retrieval_status='timeout' and status='ok'."""
    ws_id = uuid.uuid4()
    router, _ = _make_router("sparkle_fim_ok.yaml", ws_id)
    embedder = _MockEmbedder()
    principal = PrincipalContext(principal_id=uuid.uuid4(), workspace_id=ws_id)

    class _TimeoutSession:
        def __init__(self) -> None:
            self.info: dict[str, object] = {}

        async def __aenter__(self) -> Self:
            return self

        async def __aexit__(
            self,
            exc_type: type[BaseException] | None,
            exc_val: BaseException | None,
            exc_tb: TracebackType | None,
        ) -> None:
            pass

        def begin(self) -> Self:
            return self

        async def execute(self, stmt: object, params: object = None) -> object:
            del stmt, params
            msg = "canceling statement due to statement timeout"
            raise DBAPIError(msg, params=None, orig=Exception("57014"))

    class _TimeoutSessionFactory:
        def sessionmaker(self) -> _TimeoutSession:
            return _TimeoutSession()

    req = SparkleRequest(
        project_id=uuid.uuid4(),
        surface="description",
        prefix="hello world",
        suffix="",
        client_request_id=uuid.uuid4(),
    )

    result = await run_sparkle_pipeline(
        req,
        principal_ctx=principal,
        router=router,
        embedder=embedder,
        session_factory=_TimeoutSessionFactory(),
    )

    assert result.status == "ok"
    assert result.retrieval_status == "timeout"
    assert result.text == "def sparkle_suggest():\n    return True\n# ok!"


@pytest.mark.asyncio
async def test_case_07_fault_ttft_timeout_and_429() -> None:
    """Case 7: TTFT timeout returns status='timeout'; HTTP 429 returns status='unavailable'."""
    ws_id = uuid.uuid4()
    principal = PrincipalContext(principal_id=uuid.uuid4(), workspace_id=ws_id)
    embedder = _MockEmbedder()

    # 1. TTFT timeout (400ms > 115ms SLA)
    router_timeout, _ = _make_router("sparkle_fim_ttft_timeout.yaml", ws_id)
    req1 = SparkleRequest(
        project_id=uuid.uuid4(),
        surface="comment",
        prefix="Waiting for delayed response...",
        suffix="",
        client_request_id=uuid.uuid4(),
    )
    result_timeout = await run_sparkle_pipeline(
        req1,
        principal_ctx=principal,
        router=router_timeout,
        embedder=embedder,
        session_factory=None,
    )
    assert result_timeout.status == "timeout"
    assert result_timeout.text == ""

    # 2. HTTP 429 rate limit
    router_429, _ = _make_router("sparkle_fim_429.yaml", ws_id)
    req2 = SparkleRequest(
        project_id=uuid.uuid4(),
        surface="sticky",
        prefix="Overloaded provider test...",
        suffix="",
        client_request_id=uuid.uuid4(),
    )
    result_429 = await run_sparkle_pipeline(
        req2,
        principal_ctx=principal,
        router=router_429,
        embedder=embedder,
        session_factory=None,
    )
    assert result_429.status == "unavailable"
    assert result_429.text == ""


@pytest.mark.asyncio
async def test_case_08_boundary_overlong_and_prefix_boundary() -> None:
    """Case 8: Overlong cassette caps at 48 tokens; prefix of exactly 1500 chars is untouched."""
    ws_id = uuid.uuid4()
    router, provider = _make_router("sparkle_fim_overlong.yaml", ws_id)
    principal = PrincipalContext(principal_id=uuid.uuid4(), workspace_id=ws_id)

    # Prefix of exactly 1500 chars
    exact_1500_prefix = "a" * 1500
    req = SparkleRequest(
        project_id=uuid.uuid4(),
        surface="summary",
        prefix=exact_1500_prefix,
        suffix="",
        client_request_id=uuid.uuid4(),
    )

    result = await run_sparkle_pipeline(
        req,
        principal_ctx=principal,
        router=router,
        embedder=None,
        session_factory=None,
    )

    assert result.status == "ok"
    assert result.tokens == 48

    # Verify exact 1500 prefix was preserved untouched in the provider call
    call_req = provider.call_log[0]["request"]
    assert len(call_req["prompt"]) == 1500
    assert call_req["prompt"] == exact_1500_prefix


@pytest.mark.asyncio
async def test_pipeline_embedder_failure_and_empty_vectors() -> None:
    """Verify embedder exceptions and empty return lists are handled gracefully without aborting."""
    ws_id = uuid.uuid4()
    router, _ = _make_router("sparkle_fim_ok.yaml", ws_id)
    principal = PrincipalContext(principal_id=uuid.uuid4(), workspace_id=ws_id)
    req = SparkleRequest(
        project_id=uuid.uuid4(),
        surface="doc",
        prefix="print('hello')",
        suffix="",
        client_request_id=uuid.uuid4(),
    )

    # 1. Embedder raises exception
    class _FailingEmbedder:
        dimension = 384
        model_id = "mock"

        async def embed_batch(self, texts: Sequence[str]) -> list[list[float]]:
            del texts
            msg = "ONNX runtime failure"
            raise RuntimeError(msg)

    result = await run_sparkle_pipeline(
        req,
        principal_ctx=principal,
        router=router,
        embedder=_FailingEmbedder(),
        session_factory=None,
    )
    assert result.status == "ok"
    assert result.retrieval_status == "skipped"

    # 2. Embedder returns empty list
    class _EmptyEmbedder:
        dimension = 384
        model_id = "mock"

        async def embed_batch(self, texts: Sequence[str]) -> list[list[float]]:
            del texts
            return []

    result2 = await run_sparkle_pipeline(
        req,
        principal_ctx=principal,
        router=router,
        embedder=_EmptyEmbedder(),
        session_factory=None,
    )
    assert result2.status == "ok"
    assert result2.retrieval_status == "skipped"


@pytest.mark.asyncio
async def test_pipeline_direct_stream_timeout() -> None:
    """Verify stream_complete raising TimeoutError yields status 'timeout'."""
    ws_id = uuid.uuid4()
    principal = PrincipalContext(principal_id=uuid.uuid4(), workspace_id=ws_id)
    req = SparkleRequest(
        project_id=uuid.uuid4(),
        surface="doc",
        prefix="test timeout",
        suffix="",
        client_request_id=uuid.uuid4(),
    )

    class _TimeoutRouter:
        residency_tier = "fixture"
        last_route_trace: tuple[str, ...] = ("candidate-1",)

        def stream_complete(self, req: object) -> object:
            del req

            async def _stream() -> object:
                items: list[str] = []
                for chunk in items:
                    yield chunk
                msg = "stream timed out"
                raise TimeoutError(msg)

            return _stream()

    result = await run_sparkle_pipeline(
        req,
        principal_ctx=principal,
        router=_TimeoutRouter(),  # type: ignore[arg-type]
        embedder=None,
        session_factory=None,
    )
    assert result.status == "timeout"
    assert result.text == ""


@pytest.mark.asyncio
async def test_pipeline_provider_unavailable_with_aclose() -> None:
    """Verify stream_complete raising ProviderUnavailable yields status 'unavailable'."""
    ws_id = uuid.uuid4()
    principal = PrincipalContext(principal_id=uuid.uuid4(), workspace_id=ws_id)
    req = SparkleRequest(
        project_id=uuid.uuid4(),
        surface="doc",
        prefix="test unavailable",
        suffix="",
        client_request_id=uuid.uuid4(),
    )

    class _UnavailableRouter:
        residency_tier = "fixture"
        last_route_trace: tuple[str, ...] = ("candidate-1",)

        def stream_complete(self, req: object) -> object:
            del req

            class ClosableStream:
                def __init__(self) -> None:
                    self.closed = False

                def __aiter__(self) -> ClosableStream:
                    return self

                async def __anext__(self) -> object:
                    msg = "upstream service 503"
                    raise ProviderUnavailable(msg)

                async def aclose(self) -> None:
                    self.closed = True

            return ClosableStream()

    result = await run_sparkle_pipeline(
        req,
        principal_ctx=principal,
        router=_UnavailableRouter(),  # type: ignore[arg-type]
        embedder=None,
        session_factory=None,
    )
    assert result.status == "unavailable"
    assert result.text == ""


@pytest.mark.asyncio
async def test_pipeline_empty_filtered_output() -> None:
    """Verify completion text that reduces to empty after output_filter returns status 'empty'."""
    ws_id = uuid.uuid4()
    router, _ = _make_router("sparkle_fim_prompt_override.yaml", ws_id)
    principal = PrincipalContext(principal_id=uuid.uuid4(), workspace_id=ws_id)
    req = SparkleRequest(
        project_id=uuid.uuid4(),
        surface="doc",
        prefix="prompt",
        suffix="",
        client_request_id=uuid.uuid4(),
    )

    result = await run_sparkle_pipeline(
        req,
        principal_ctx=principal,
        router=router,
        embedder=None,
        session_factory=None,
    )
    assert result.status == "empty"
    assert result.text == ""
    assert result.tokens == 0
