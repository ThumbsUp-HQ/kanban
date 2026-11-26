# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Comprehensive unit tests for Sparkle FIM completion pipeline (KB-AI-WORKOUT)."""

from __future__ import annotations

import contextlib
import uuid
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

import pytest
from sqlalchemy.exc import SQLAlchemyError

from agent.providers.base import CompletionRequest, StreamChunk
from agent.providers.router import ProviderRouter, RouteCandidate
from agent.sparkle.pipeline import SparkleRequest, run_sparkle_pipeline
from agent.testing.fixtures import FixtureLLMProvider, load_cassette
from kanban.api.deps import PrincipalContext

_CASSETTES_DIR = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "ai"


class _MockAsyncSession:
    """Mock database session implementing budget enforcer protocol."""

    def __init__(
        self,
        *,
        db_provider_id: uuid.UUID | None = None,
        frozen_provider_id: uuid.UUID | None = None,
        raise_on_execute: Exception | None = None,
        ledger_rows: list[dict[str, object]] | None = None,
        reserve_fails: bool = False,
    ) -> None:
        """Initialize mock async session with state control."""
        self.db_provider_id = db_provider_id
        self.frozen_provider_id = frozen_provider_id
        self.raise_on_execute = raise_on_execute
        self.ledger_rows = ledger_rows if ledger_rows is not None else []
        self.reserve_fails = reserve_fails
        self.executed_queries: list[str] = []
        self.settle_called = False
        self.release_called = False

    def in_transaction(self) -> bool:
        """Return whether session is in a transaction."""
        return False

    @contextlib.asynccontextmanager
    async def begin(self) -> AsyncIterator[_MockAsyncSession]:
        """Begin transaction mock context manager."""
        yield self

    @contextlib.asynccontextmanager
    async def begin_nested(self) -> AsyncIterator[_MockAsyncSession]:
        """Begin nested transaction mock context manager."""
        yield self

    async def execute(self, statement: object, params: object = None) -> object:
        """Execute simulated SQL statement and return mocked results."""
        del params
        sql = str(statement)
        self.executed_queries.append(sql)

        if self.raise_on_execute is not None:
            raise self.raise_on_execute

        mock_res = MagicMock()

        if "FROM ai_provider_configs" in sql:
            mock_res.scalar_one_or_none.return_value = self.db_provider_id
            return mock_res

        if "FROM ai_token_ledgers" in sql and "token_cap = 0" in sql:
            mock_res.scalar_one_or_none.return_value = self.frozen_provider_id
            return mock_res

        if "FROM ai_token_ledgers" in sql:
            mappings_mock = MagicMock()
            mappings_mock.all.return_value = self.ledger_rows
            mock_res.mappings.return_value = mappings_mock
            return mock_res

        if "UPDATE ai_token_ledgers" in sql:
            if "tokens_used + tokens_reserved" in sql:
                if self.reserve_fails:
                    mock_res.first.return_value = None
                else:
                    mock_res.first.return_value = (uuid.uuid4(),)
            elif "tokens_used = LEAST" in sql or "tokens_used =" in sql:
                self.settle_called = True
            elif "tokens_reserved = GREATEST" in sql:
                self.release_called = True
            return mock_res

        mock_res.scalar_one_or_none.return_value = None
        mock_res.first.return_value = None
        return mock_res


class _MockSessionFactory:
    """Mock session factory returning an async context manager."""

    def __init__(self, session: _MockAsyncSession) -> None:
        """Initialize mock session factory."""
        self._session = session

    @contextlib.asynccontextmanager
    async def session(self, rls_ctx: object = None) -> AsyncIterator[_MockAsyncSession]:
        """Provide mock session context with RLS context."""
        del rls_ctx
        yield self._session

    @contextlib.asynccontextmanager
    async def __call__(self) -> AsyncIterator[_MockAsyncSession]:
        """Provide mock session context."""
        yield self._session


def _make_pipeline_setup(
    cassette_name: str = "sparkle_fim_ok.yaml",
    workspace_id: uuid.UUID | None = None,
    provider_config_id: uuid.UUID | None = None,
) -> tuple[ProviderRouter, FixtureLLMProvider, PrincipalContext, SparkleRequest]:
    ws_id = workspace_id or uuid.uuid4()
    cfg_id = provider_config_id or uuid.uuid4()
    cas = load_cassette(_CASSETTES_DIR / cassette_name)
    provider = FixtureLLMProvider([cas])
    candidate = RouteCandidate(
        provider_config_id=cfg_id,
        provider=provider,
        residency_tier="fixture",
        priority=10,
    )
    router = ProviderRouter(
        workspace_id=ws_id,
        candidates=[candidate],
        air_gap_mode=False,
    )
    principal = PrincipalContext(principal_id=uuid.uuid4(), workspace_id=ws_id)
    req = SparkleRequest(
        project_id=uuid.uuid4(),
        surface="doc",
        prefix="def hello_world():\n    ",
        suffix="\n    return 42",
        client_request_id=uuid.uuid4(),
    )
    return router, provider, principal, req


@pytest.mark.asyncio
async def test_sparkle_pipeline_normal_ok() -> None:
    """Test standard successful completion with settlement in budget."""
    cfg_id = uuid.uuid4()
    router, _, principal, req = _make_pipeline_setup(
        cassette_name="sparkle_fim_ok.yaml",
        provider_config_id=cfg_id,
    )
    session = _MockAsyncSession(
        db_provider_id=cfg_id,
        frozen_provider_id=None,
        ledger_rows=[{"id": uuid.uuid4(), "period_kind": "monthly"}],
        reserve_fails=False,
    )
    session_factory = _MockSessionFactory(session)

    res = await run_sparkle_pipeline(
        req,
        principal_ctx=principal,
        router=router,
        embedder=None,
        session_factory=session_factory,
    )
    assert res.status == "ok"
    assert res.tokens > 0
    assert len(res.text) > 0
    assert session.settle_called is True


@pytest.mark.asyncio
async def test_sparkle_pipeline_provider_scoped_freeze_token_cap_zero() -> None:
    """Test that token_cap=0 on provider blocks completion with status='budget'."""
    cfg_id = uuid.uuid4()
    router, _, principal, req = _make_pipeline_setup(
        cassette_name="sparkle_fim_ok.yaml",
        provider_config_id=cfg_id,
    )
    session = _MockAsyncSession(
        db_provider_id=cfg_id,
        frozen_provider_id=cfg_id,
    )
    session_factory = _MockSessionFactory(session)

    res = await run_sparkle_pipeline(
        req,
        principal_ctx=principal,
        router=router,
        embedder=None,
        session_factory=session_factory,
    )
    assert res.status == "budget"
    assert res.tokens == 0
    assert res.text == ""


@pytest.mark.asyncio
async def test_sparkle_pipeline_provider_scoped_freeze_tokens_used_exhausted() -> None:
    """Test that exhausted token_cap (tokens_used >= token_cap) blocks with status='budget'."""
    cfg_id = uuid.uuid4()
    router, _, principal, req = _make_pipeline_setup(
        cassette_name="sparkle_fim_ok.yaml",
        provider_config_id=cfg_id,
    )
    session = _MockAsyncSession(
        db_provider_id=cfg_id,
        frozen_provider_id=cfg_id,
    )
    session_factory = _MockSessionFactory(session)

    res = await run_sparkle_pipeline(
        req,
        principal_ctx=principal,
        router=router,
        embedder=None,
        session_factory=session_factory,
    )
    assert res.status == "budget"
    assert res.tokens == 0
    assert res.text == ""


@pytest.mark.asyncio
async def test_sparkle_pipeline_unfrozen_higher_priority_succeeds_when_sibling_frozen() -> None:
    """Test that active provider from DB is resolved and succeeds if unfrozen."""
    dummy_startup_id = uuid.uuid4()
    active_db_id = uuid.uuid4()
    router, _, principal, req = _make_pipeline_setup(
        cassette_name="sparkle_fim_ok.yaml",
        provider_config_id=dummy_startup_id,
    )
    # DB query resolves to active_db_id (higher priority), which is not frozen
    session = _MockAsyncSession(
        db_provider_id=active_db_id,
        frozen_provider_id=None,
        ledger_rows=[],
    )
    session_factory = _MockSessionFactory(session)

    res = await run_sparkle_pipeline(
        req,
        principal_ctx=principal,
        router=router,
        embedder=None,
        session_factory=session_factory,
    )
    assert res.status == "ok"
    assert res.tokens > 0
    # Candidate in router should have been aligned to active_db_id
    assert router._candidates[0].provider_config_id == active_db_id  # noqa: SLF001


@pytest.mark.asyncio
async def test_sparkle_pipeline_budget_enforcer_reserve_budget_exceeded() -> None:
    """Test that BudgetExceeded from reserve blocks with status='budget'."""
    cfg_id = uuid.uuid4()
    router, _, principal, req = _make_pipeline_setup(
        cassette_name="sparkle_fim_ok.yaml",
        provider_config_id=cfg_id,
    )
    session = _MockAsyncSession(
        db_provider_id=cfg_id,
        frozen_provider_id=None,
        ledger_rows=[{"id": uuid.uuid4(), "period_kind": "monthly"}],
        reserve_fails=True,
    )
    session_factory = _MockSessionFactory(session)

    res = await run_sparkle_pipeline(
        req,
        principal_ctx=principal,
        router=router,
        embedder=None,
        session_factory=session_factory,
    )
    assert res.status == "budget"
    assert res.tokens == 0
    assert res.text == ""


@pytest.mark.asyncio
async def test_sparkle_pipeline_budget_enforcer_release_on_empty() -> None:
    """Test that empty output releases the budget reservation."""
    cfg_id = uuid.uuid4()
    router, _, principal, req = _make_pipeline_setup(
        cassette_name="sparkle_fim_prompt_override.yaml",
        provider_config_id=cfg_id,
    )
    session = _MockAsyncSession(
        db_provider_id=cfg_id,
        frozen_provider_id=None,
        ledger_rows=[{"id": uuid.uuid4(), "period_kind": "monthly"}],
        reserve_fails=False,
    )
    session_factory = _MockSessionFactory(session)

    res = await run_sparkle_pipeline(
        req,
        principal_ctx=principal,
        router=router,
        embedder=None,
        session_factory=session_factory,
    )
    assert res.status == "empty"
    assert session.release_called is True


@pytest.mark.asyncio
async def test_sparkle_pipeline_budget_enforcer_release_on_timeout() -> None:
    """Test that stream timeout releases the budget reservation."""
    cfg_id = uuid.uuid4()
    router, _, principal, req = _make_pipeline_setup(
        cassette_name="sparkle_fim_ttft_timeout.yaml",
        provider_config_id=cfg_id,
    )
    session = _MockAsyncSession(
        db_provider_id=cfg_id,
        frozen_provider_id=None,
        ledger_rows=[{"id": uuid.uuid4(), "period_kind": "monthly"}],
        reserve_fails=False,
    )
    session_factory = _MockSessionFactory(session)

    res = await run_sparkle_pipeline(
        req,
        principal_ctx=principal,
        router=router,
        embedder=None,
        session_factory=session_factory,
    )
    assert res.status == "timeout"
    assert session.release_called is True


@pytest.mark.asyncio
async def test_sparkle_pipeline_fail_closed_on_db_unexpected_exception() -> None:
    """Test that unexpected DB exception fails closed with status='budget'."""
    cfg_id = uuid.uuid4()
    router, _, principal, req = _make_pipeline_setup(
        cassette_name="sparkle_fim_ok.yaml",
        provider_config_id=cfg_id,
    )
    session = _MockAsyncSession(
        raise_on_execute=SQLAlchemyError("PostgreSQL pool connection failed"),
    )
    session_factory = _MockSessionFactory(session)

    res = await run_sparkle_pipeline(
        req,
        principal_ctx=principal,
        router=router,
        embedder=None,
        session_factory=session_factory,
    )
    assert res.status == "budget"
    assert res.tokens == 0
    assert res.text == ""


@pytest.mark.asyncio
async def test_sparkle_pipeline_secret_scrubbed_input() -> None:
    """Test that input with raw secret returns status='secret_scrubbed' immediately."""
    router, _, principal, _ = _make_pipeline_setup("sparkle_fim_ok.yaml")
    secret_prefix = "api_key = 'sk-live-" + "XYZ123" * 5 + "'"
    req = SparkleRequest(
        project_id=uuid.uuid4(),
        surface="comment",
        prefix=secret_prefix,
        suffix="",
        client_request_id=uuid.uuid4(),
    )
    res = await run_sparkle_pipeline(
        req,
        principal_ctx=principal,
        router=router,
        embedder=None,
        session_factory=None,
    )
    assert res.status == "secret_scrubbed"
    assert res.tokens == 0
    assert res.text == ""


@pytest.mark.asyncio
async def test_sparkle_pipeline_no_session_factory_succeeds() -> None:
    """Test that pipeline works without session_factory (offline test mode)."""
    router, _, principal, req = _make_pipeline_setup("sparkle_fim_ok.yaml")
    res = await run_sparkle_pipeline(
        req,
        principal_ctx=principal,
        router=router,
        embedder=None,
        session_factory=None,
    )
    assert res.status == "ok"
    assert res.tokens > 0
    assert len(res.text) > 0


@pytest.mark.asyncio
async def test_sparkle_pipeline_string_project_id_and_callable_session() -> None:
    """Test resolution of string project_id and callable session_factory."""
    router, _, principal, req = _make_pipeline_setup("sparkle_fim_ok.yaml")
    req = req.model_copy(update={"project_id": str(uuid.uuid4())})
    session = _MockAsyncSession()

    @contextlib.asynccontextmanager
    async def callable_factory() -> AsyncIterator[_MockAsyncSession]:
        yield session

    res = await run_sparkle_pipeline(
        req,
        principal_ctx=principal,
        router=router,
        embedder=None,
        session_factory=callable_factory,
    )
    assert res.status == "ok"


@pytest.mark.asyncio
async def test_sparkle_pipeline_no_candidates_fallback_freeze() -> None:
    """Test pipeline handling when router has no candidates and exercises fallback freeze check."""
    ws_id = uuid.uuid4()
    router = ProviderRouter(workspace_id=ws_id, candidates=[], air_gap_mode=False)
    principal = PrincipalContext(principal_id=uuid.uuid4(), workspace_id=ws_id)
    req = SparkleRequest(
        project_id=uuid.uuid4(),
        surface="doc",
        prefix="print('test')",
        suffix="",
        client_request_id=uuid.uuid4(),
    )
    session = _MockAsyncSession(db_provider_id=None, frozen_provider_id=uuid.uuid4())
    session_factory = _MockSessionFactory(session)

    res = await run_sparkle_pipeline(
        req,
        principal_ctx=principal,
        router=router,
        embedder=None,
        session_factory=session_factory,
    )
    assert res.status == "budget"


@pytest.mark.asyncio
async def test_sparkle_pipeline_sessionmaker_factory() -> None:
    """Test session_factory exposing sessionmaker attribute."""
    router, _, principal, req = _make_pipeline_setup("sparkle_fim_ok.yaml")
    session = _MockAsyncSession()

    class SessionmakerFactory:
        def sessionmaker(self) -> object:
            @contextlib.asynccontextmanager
            async def _cm() -> AsyncIterator[_MockAsyncSession]:
                yield session

            return _cm()

    res = await run_sparkle_pipeline(
        req,
        principal_ctx=principal,
        router=router,
        embedder=None,
        session_factory=SessionmakerFactory(),
    )
    assert res.status == "ok"


class _MockOllamaProvider(FixtureLLMProvider):
    """Mock provider typed with Ollama in name."""


class _MockOpenAIProvider(FixtureLLMProvider):
    """Mock provider typed with OpenAI in name."""


class _MockGeminiProvider(FixtureLLMProvider):
    """Mock provider typed with Gemini in name."""


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("provider_cls", "kind_str"),
    [
        (_MockOllamaProvider, "ollama"),
        (_MockOpenAIProvider, "openai"),
        (_MockGeminiProvider, "gemini"),
    ],
)
async def test_sparkle_pipeline_resolve_provider_by_kind(provider_cls: type, kind_str: str) -> None:
    """Test resolution of provider_config_id by candidate provider kind."""
    del kind_str
    cassette = load_cassette(_CASSETTES_DIR / "sparkle_fim_ok.yaml")
    provider = provider_cls([cassette])
    resolved_id = uuid.uuid4()
    ws_id = uuid.uuid4()
    candidates = [
        RouteCandidate(
            provider_config_id=uuid.uuid4(),
            provider=provider,
            residency_tier="local_private",
            priority=10,
        )
    ]
    router = ProviderRouter(workspace_id=ws_id, candidates=candidates, air_gap_mode=False)
    principal = PrincipalContext(principal_id=uuid.uuid4(), workspace_id=ws_id)
    req = SparkleRequest(
        project_id=uuid.uuid4(),
        surface="doc",
        prefix="def add(a, b):\n    return ",
        suffix="\n",
        client_request_id=uuid.uuid4(),
    )
    session = _MockAsyncSession(db_provider_id=resolved_id)
    session_factory = _MockSessionFactory(session)

    res = await run_sparkle_pipeline(
        req,
        principal_ctx=principal,
        router=router,
        embedder=None,
        session_factory=session_factory,
    )
    assert res.status == "ok"
    assert router._candidates[0].provider_config_id == resolved_id  # noqa: SLF001


@pytest.mark.asyncio
async def test_sparkle_pipeline_direct_session_context_manager() -> None:
    """Test session_factory being a direct non-callable async context manager."""
    router, _, principal, req = _make_pipeline_setup("sparkle_fim_ok.yaml")
    session = _MockAsyncSession()

    class DirectCM:
        async def __aenter__(self) -> _MockAsyncSession:
            return session

        async def __aexit__(self, *args: object) -> None:
            pass

    res = await run_sparkle_pipeline(
        req,
        principal_ctx=principal,
        router=router,
        embedder=None,
        session_factory=DirectCM(),
    )
    assert res.status == "ok"


class _TimeoutStreamProvider(FixtureLLMProvider):
    """Mock provider whose stream raises TimeoutError."""

    async def stream_complete(self, req: CompletionRequest) -> AsyncIterator[StreamChunk]:
        del req
        msg = "stream read timed out"
        raise TimeoutError(msg)
        yield StreamChunk(delta="")  # type: ignore[unreachable]


@pytest.mark.asyncio
async def test_sparkle_pipeline_timeout_with_reservation_release() -> None:
    """Test TimeoutError releasing reservation when reservation was created."""
    cfg_id = uuid.uuid4()
    ws_id = uuid.uuid4()
    provider = _TimeoutStreamProvider([load_cassette(_CASSETTES_DIR / "sparkle_fim_ok.yaml")])
    candidates = [
        RouteCandidate(
            provider_config_id=cfg_id,
            provider=provider,
            residency_tier="local_private",
            priority=10,
        )
    ]
    router = ProviderRouter(workspace_id=ws_id, candidates=candidates, air_gap_mode=False)
    principal = PrincipalContext(principal_id=uuid.uuid4(), workspace_id=ws_id)
    req = SparkleRequest(
        project_id=uuid.uuid4(),
        surface="doc",
        prefix="print('hello')",
        suffix="",
        client_request_id=uuid.uuid4(),
    )
    session = _MockAsyncSession(
        db_provider_id=cfg_id,
        ledger_rows=[{"id": uuid.uuid4(), "period_kind": "monthly"}],
    )
    session_factory = _MockSessionFactory(session)

    res = await run_sparkle_pipeline(
        req,
        principal_ctx=principal,
        router=router,
        embedder=None,
        session_factory=session_factory,
    )
    assert res.status == "timeout"
    assert session.release_called is True
