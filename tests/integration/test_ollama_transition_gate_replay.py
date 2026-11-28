# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
# ruff: noqa: ANN401, D102, D103, D107, INP001, ARG001, ARG002, TC001, SLF001, PERF401
"""KAN-546: offline end-to-end replay of live nemotron-3-super multi-turn gate cassettes.

Pipeline under test (zero network calls):
OllamaProvider(CassetteTransport) -> InAppSdkHarness (real tool loop) -> BareGitRepoToolkit
(real temporary bare git repo) -> parse_verdict_output -> GateWorker -> coordinator ->
ticket state + comments + synchronous MCP transition_ticket response.
"""

from __future__ import annotations

import json
import subprocess
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
import pytest
from pydantic import BaseModel

from agent.context.transition_context import RepoContext
from agent.gates.worker import GateWorker, HarnessRegistry
from agent.harnesses.in_app_sdk import InAppSdkHarness
from agent.providers.base import ChatMessage, ChatTurnRequest
from agent.providers.errors import ProviderSchemaError
from agent.providers.ollama import OllamaProvider, OllamaSettings
from agent.testing.fixtures import (
    Cassette,
    CassetteMatcher,
    FixtureLLMProvider,
    load_cassette,
)
from agent.testing.http_cassette import CassetteTransport, RecordingTransport
from agent.tools.schemas import REPO_TOOL_DEFINITIONS
from kanban.workflows.async_gate import (
    _gate_result_from_row,
    format_approve_comment,
    format_veto_comment,
)
from kanban.workflows.gate_types import GateDecision
from mcp.surfaces.agent.transition_ticket import transition_ticket

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "ai"
PASS_CASSETTE = FIXTURES / "ollama_nemotron_multiturn_gate.yaml"
REJECT_CASSETTE = FIXTURES / "ollama_nemotron_multiturn_gate_reject.yaml"

LIVE_BASE_URL = "http://192.168.1.101:11434"
LIVE_MODEL = "nemotron-3-super:latest"
EXEC_ID = "0196ed40-7b2a-7000-8000-112233445566"
HOOK_ID = "0196ed40-7b2a-7000-8000-998877665544"

_LIMITER_GOOD = '''"""Token bucket rate limiter."""

from __future__ import annotations

import time


class TokenBucket:
    """Allow at most `capacity` events in a burst, refilling `rate` tokens per second."""

    def __init__(self, capacity: int, rate: float) -> None:
        self.capacity = capacity
        self.rate = rate
        self._tokens = float(capacity)
        self._stamp = time.monotonic()

    def allow(self) -> bool:
        now = time.monotonic()
        self._tokens = min(self.capacity, self._tokens + (now - self._stamp) * self.rate)
        self._stamp = now
        if self._tokens >= 1.0:
            self._tokens -= 1.0
            return True
        return False
'''

_LIMITER_STUB = '''"""Token bucket rate limiter."""

from __future__ import annotations


class TokenBucket:
    """Rate limiter (not implemented yet)."""

    def __init__(self, capacity: int, rate: float) -> None:
        self.capacity = capacity
        self.rate = rate

    def allow(self) -> bool:
        # TODO: implement token refill
        return True
'''

_TESTS_GOOD = """from ratelimit.limiter import TokenBucket


def test_burst_then_block():
    bucket = TokenBucket(capacity=2, rate=0.0)
    assert bucket.allow()
    assert bucket.allow()
    assert not bucket.allow()


def test_refill_over_time(monkeypatch):
    import ratelimit.limiter as mod

    now = [100.0]
    monkeypatch.setattr(mod.time, "monotonic", lambda: now[0])
    bucket = TokenBucket(capacity=1, rate=1.0)
    assert bucket.allow()
    assert not bucket.allow()
    now[0] += 1.0
    assert bucket.allow()
"""

_TESTS_STUB = """def test_placeholder():
    pass
"""

PASS_TICKET = (
    "Implement TokenBucket rate limiter. Definition of Done: "
    "(1) src/ratelimit/limiter.py defines TokenBucket.allow() that enforces capacity and "
    "refills tokens over time; (2) tests/test_limiter.py covers burst blocking and refill."
)
REJECT_TICKET = PASS_TICKET


def build_scenario_repo(tmp_path: Path, scenario: str) -> tuple[Path, str]:
    """Create a real bare git repo; scenario is 'pass' (implemented) or 'reject' (stub)."""
    work = tmp_path / f"work-{scenario}"
    work.mkdir()

    def git(*args: str) -> str:
        return subprocess.run(
            ["git", *args], cwd=work, check=True, capture_output=True, text=True
        ).stdout.strip()

    git("init")
    git("config", "user.name", "Test Committer")
    git("config", "user.email", "test@example.com")
    git("config", "commit.gpgsign", "false")
    (work / "src" / "ratelimit").mkdir(parents=True)
    (work / "tests").mkdir()
    (work / "src" / "ratelimit" / "__init__.py").write_text("", encoding="utf-8")
    good = scenario == "pass"
    (work / "src" / "ratelimit" / "limiter.py").write_text(
        _LIMITER_GOOD if good else _LIMITER_STUB, encoding="utf-8"
    )
    (work / "tests" / "test_limiter.py").write_text(
        _TESTS_GOOD if good else _TESTS_STUB, encoding="utf-8"
    )
    git("add", ".")
    git("commit", "-m", "Add token bucket")
    head = git("rev-parse", "HEAD")
    bare = tmp_path / f"repo-{scenario}.git"
    subprocess.run(
        ["git", "clone", "--bare", str(work), str(bare)], check=True, capture_output=True
    )
    return bare, head


def make_event(bare: tuple[Path, str], scenario: str) -> dict[str, Any]:
    bare_path, head = bare
    return {
        "execution_id": EXEC_ID,
        "hook_id": HOOK_ID,
        "execution": {
            "id": EXEC_ID,
            "project_key": "KAN",
            "from_state": "In Review",
            "to_state": "Done",
            "actor": "@test-operator",
            "allowed_mutable_fields": ("labels", "priority"),
        },
        "issue": {
            "key": "KAN-546",
            "summary": "Token bucket rate limiter",
            "description_markdown": PASS_TICKET if scenario == "pass" else REJECT_TICKET,
        },
        "agent_def": {
            "slug": "reality-checker",
            "harness_kind": "in_app_sdk",
            "timeout_ms": 240000,
            "repo_access_mode": "read-only",
            "reality_checker": True,
            "model": LIVE_MODEL,
        },
        "repo_context": RepoContext(
            mount_path=str(bare_path),
            access="read-only",
            head_commit=head,
            mirror_path=bare_path,
        ),
    }


def make_ollama(
    transport: httpx.AsyncBaseTransport, read_timeout_s: float = 180.0
) -> OllamaProvider:
    settings = OllamaSettings(
        base_url=LIVE_BASE_URL,  # type: ignore[arg-type]
        model_allowlist=(LIVE_MODEL,),
        read_timeout_s=read_timeout_s,
    )
    return OllamaProvider(settings, transport=transport)


@dataclass
class SimTicket:
    """Minimal ticket + workflow simulator driven by recorded gate decisions."""

    state: str = "In Review"
    comments: list[str] = field(default_factory=list)
    decisions: list[GateDecision] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)

    async def record_decision(
        self, execution_id: str, hook_id: str, decision: GateDecision
    ) -> None:
        self.decisions.append(decision)
        if decision.decision == "approve":
            self.state = "Done"
            self.comments.append(
                format_approve_comment(
                    "reality-checker",
                    "in_app_sdk",
                    "In Review",
                    "Done",
                    decision.reason_markdown,
                    grade=decision.grade,
                )
            )
        else:
            self.comments.append(
                format_veto_comment(
                    "reality-checker",
                    "in_app_sdk",
                    "In Review",
                    "Done",
                    decision.reason_markdown,
                    grade=decision.grade,
                )
            )

    async def record_failure(self, execution_id: str, hook_id: str, code: str) -> None:
        self.failures.append(code)

    def gate_payload(self) -> dict[str, Any]:
        d = self.decisions[0]
        status = "approved" if d.decision == "approve" else "rejected"
        return _gate_result_from_row(
            uuid.UUID(EXEC_ID),
            status,
            {
                "decision": d.decision,
                "grade": d.grade,
                "reason": d.reason_markdown,
                "cited_files": list(d.cited_files),
            },
        )


class McpClientStub:
    """Stands in for the REST client; returns the gate result the coordinator produced."""

    def __init__(self, gate: dict[str, Any]) -> None:
        self.gate = gate

    async def request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        return {"gate": self.gate, "sequence_number": 1}


async def run_gate(
    provider: OllamaProvider, bare: tuple[Path, str], scenario: str
) -> tuple[InAppSdkHarness, SimTicket]:
    harness = InAppSdkHarness(provider=provider)
    registry = HarnessRegistry(register_defaults=False)
    registry.register("in_app_sdk", harness)
    ticket = SimTicket()
    worker = GateWorker(registry=registry, coordinator=ticket)
    await worker.handle_dispatch(make_event(bare, scenario))
    return harness, ticket


@pytest.fixture
def pass_repo(tmp_path: Path) -> tuple[Path, str]:
    return build_scenario_repo(tmp_path, "pass")


@pytest.fixture
def reject_repo(tmp_path: Path) -> tuple[Path, str]:
    return build_scenario_repo(tmp_path, "reject")


def _no_network_guard(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_a: Any, **_k: Any) -> None:
        msg = "network access attempted during offline replay"
        raise AssertionError(msg)

    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", boom)


async def test_replay_pass_scenario(
    pass_repo: tuple[Path, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    _no_network_guard(monkeypatch)
    transport = CassetteTransport(PASS_CASSETTE)
    harness, ticket = await run_gate(make_ollama(transport), pass_repo, "pass")

    assert ticket.failures == []
    assert len(harness.last_tool_traces) >= 1
    assert any(t.status == "ok" for t in harness.last_tool_traces)
    assert {t.tool_name for t in harness.last_tool_traces} <= {
        "repo_tree",
        "repo_read_file",
        "repo_grep",
        "repo_git_log",
        "repo_git_diff",
    }
    assert transport.call_count == transport.exchange_count > len(harness.last_tool_traces)

    assert len(ticket.decisions) == 1
    decision = ticket.decisions[0]
    assert decision.decision == "approve"
    assert decision.grade is not None
    assert decision.reason_markdown.strip()
    assert decision.cited_files

    assert ticket.state == "Done"
    assert f"Grade: {decision.grade}" in ticket.comments[0]
    assert "Approved" in ticket.comments[0]

    res = await transition_ticket(
        {"identifier": "KAN-546", "to_state": "Done"},
        client=McpClientStub(ticket.gate_payload()),  # type: ignore[arg-type]
    )
    assert res["passed"] is True
    assert res["grade"] == decision.grade
    assert res["comment"] == decision.reason_markdown
    assert res["findings"] == list(decision.cited_files)


async def test_replay_reject_scenario(
    reject_repo: tuple[Path, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    _no_network_guard(monkeypatch)
    transport = CassetteTransport(REJECT_CASSETTE)
    harness, ticket = await run_gate(make_ollama(transport), reject_repo, "reject")

    assert ticket.failures == []
    assert len(harness.last_tool_traces) >= 1
    assert any(t.status == "ok" for t in harness.last_tool_traces)
    assert transport.call_count == transport.exchange_count > len(harness.last_tool_traces)

    assert len(ticket.decisions) == 1
    decision = ticket.decisions[0]
    assert decision.decision == "reject"
    assert decision.grade is not None
    assert decision.grade[0] in {"C", "F", "D"}
    assert decision.reason_markdown.strip()
    assert decision.cited_files

    assert ticket.state == "In Review"
    assert "vetoed" in ticket.comments[0]
    assert f"Grade: {decision.grade}" in ticket.comments[0]

    res = await transition_ticket(
        {"identifier": "KAN-546", "to_state": "Done"},
        client=McpClientStub(ticket.gate_payload()),  # type: ignore[arg-type]
    )
    assert res["passed"] is False
    assert res["grade"] == decision.grade
    assert res["comment"] == decision.reason_markdown


@pytest.mark.parametrize("cassette", [PASS_CASSETTE, REJECT_CASSETTE])
def test_recorded_cassettes_are_scrubbed_and_dash_free(cassette: Path) -> None:
    text = cassette.read_text(encoding="utf-8")
    assert "\u2014" not in text
    assert "\u2013" not in text
    data = load_cassette(cassette)
    assert data.cassette_version == 1
    assert data.http_exchanges
    for ex in data.http_exchanges:
        req = ex["request"]
        assert req["json_contains"]["model"] == LIVE_MODEL
        assert req["json_contains"]["stream"] is False
        assert "messages_len" in req
        assert "has_tools" in req
    assert data.http_exchanges[-1]["request"]["has_tools"] is False


async def test_replay_rejects_shape_mismatch() -> None:
    transport = CassetteTransport(
        {
            "http_exchanges": [
                {
                    "request": {
                        "method": "POST",
                        "path": "/api/chat",
                        "messages_len": 2,
                        "has_tools": True,
                    },
                    "response": {"json_body": {}},
                }
            ]
        }
    )
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(Exception, match="messages_len mismatch"):
            await client.post("http://x/api/chat", json={"messages": [1], "tools": [{"a": 1}]})


async def test_replay_has_tools_mismatch() -> None:
    transport = CassetteTransport(
        [
            {
                "request": {"method": "POST", "path": "/api/chat", "has_tools": True},
                "response": {"json_body": {}},
            }
        ]
    )
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(Exception, match="has_tools mismatch"):
            await client.post("http://x/api/chat", json={"messages": []})


async def test_recording_transport_scrubs_and_writes_valid_cassette(tmp_path: Path) -> None:
    secret = "ghp_" + "a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6q7R8"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"message": {"role": "assistant", "content": f"token {secret} leaked"}},
        )

    rec = RecordingTransport(httpx.MockTransport(handler))
    async with httpx.AsyncClient(transport=rec) as client:
        resp = await client.post(
            "http://x/api/chat",
            json={
                "model": "m",
                "stream": False,
                "messages": [{"role": "user", "content": "delimiter-XYZ-random"}],
                "tools": [{"type": "function"}],
            },
        )
        assert resp.status_code == 200
        assert secret in resp.text  # caller still receives the unmodified live body
    out = tmp_path / "rec.yaml"
    rec.save(out)
    text = out.read_text(encoding="utf-8")
    assert secret not in text
    assert "delimiter-XYZ-random" not in text
    cas = load_cassette(out)
    assert cas.http_exchanges is not None
    req = cas.http_exchanges[0]["request"]
    assert req == {
        "method": "POST",
        "path": "/api/chat",
        "json_contains": {"model": "m", "stream": False},
        "messages_len": 1,
        "has_tools": True,
    }
    replay = CassetteTransport(out)
    async with httpx.AsyncClient(transport=replay) as client:
        r2 = await client.post(
            "http://x/api/chat",
            json={"model": "m", "stream": False, "messages": [{}], "tools": [{"t": 1}]},
        )
    assert secret not in r2.text


async def test_recording_transport_non_json_and_defaults() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="plain body")

    rec = RecordingTransport(httpx.MockTransport(handler))
    async with httpx.AsyncClient(transport=rec) as client:
        await client.post("http://x/other", content=b"not json")
    assert rec.exchanges[0]["response"]["text"] == "plain body"
    assert rec.exchanges[0]["request"] == {
        "method": "POST",
        "path": "/other",
        "has_tools": False,
    } or ("json_contains" not in rec.exchanges[0]["request"])
    await rec.aclose()
    assert isinstance(RecordingTransport()._inner, httpx.AsyncHTTPTransport)


async def test_fixture_chat_turn_synthesizes_tool_turns_then_verdict() -> None:
    cas = Cassette.model_validate(
        {
            "cassette_version": 1,
            "matcher": {},
            "tool_script": [
                {"call": {"tool": "repo_tree", "args": {"path": ""}}},
                {"call": {"tool": "repo_read_file", "args": {"path": "a.py"}}},
            ],
            "final_verdict": {"decision": "approve", "reason_markdown": "ok"},
        }
    )
    provider = FixtureLLMProvider([cas])
    base = (ChatMessage(role="user", content="check"),)
    r1 = await provider.chat_turn(ChatTurnRequest(model="m", messages=base, tools=_tools()))
    assert cas.tool_script
    assert r1.message.tool_calls[0].name == cas.tool_script[0].call.tool
    assert r1.message.tool_calls[0].arguments == cas.tool_script[0].call.args

    msgs = [*base]
    for _ in cas.tool_script:
        msgs.append(ChatMessage(role="assistant", tool_calls=r1.message.tool_calls))
    done = await provider.chat_turn(
        ChatTurnRequest(model="m", messages=tuple(msgs), tools=_tools())
    )
    assert not done.message.tool_calls
    assert done.raw_content == "done"

    class Verdict(BaseModel):
        decision: str

    final = await provider.chat_turn(
        ChatTurnRequest(model="m", messages=base, response_model=Verdict)
    )
    assert json.loads(final.raw_content)["decision"] in {"approve", "reject"}
    assert provider.call_log[-1]["method"] == "chat_turn"


async def test_fixture_chat_turn_without_verdict_errors() -> None:
    class V(BaseModel):
        decision: str

    provider = FixtureLLMProvider([Cassette(matcher=CassetteMatcher())])
    with pytest.raises(ProviderSchemaError):
        await provider.chat_turn(
            ChatTurnRequest(
                model="m",
                messages=(ChatMessage(role="user", content="x"),),
                response_model=V,
            )
        )


def _tools() -> tuple[Any, ...]:
    return tuple(REPO_TOOL_DEFINITIONS)
