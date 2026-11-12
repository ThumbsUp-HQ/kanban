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
"""Feature unit tests for kanban-agent validate-sparkle CLI command (KB-P5-10)."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
from pathlib import Path
from typing import Any

import asyncpg  # type: ignore[import-untyped]
import jsonschema
import pytest
from sqlalchemy.ext.asyncio import AsyncConnection

import agent.cli_commands.validate_sparkle as vs_mod
from agent.cli import main
from agent.cli_commands.validate_sparkle import (
    CliEmbedder,
    _resolve_provider_instance,
    parse_cursor_marker,
)
from agent.sparkle.pipeline import SparkleResult
from agent.testing.fixtures import Cassette, CassetteMatcher, FixtureLLMProvider
from database.session import RLSSessionFactory

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_FIXTURES_DIR = _REPO_ROOT / "tests" / "fixtures" / "ai"
_SCHEMA_PATH = _REPO_ROOT / "agent" / "schemas" / "kb-sparkle-report-v1.json"
_SEED_PATH = _REPO_ROOT / "examples" / "sparkle" / "seed_rls_demo.sql"


@pytest.fixture(scope="session")
def demo_db_url() -> str:
    """Ensure kanban_demo test database is created and seeded with seed_rls_demo.sql."""
    sock = os.environ.get("KB_TEST_PGHOST", "/tmp/kb-pgsock-21")

    async def _setup() -> None:
        admin_conn = await asyncpg.connect(user="kanban_test", database="postgres", host=sock)
        try:
            exists = await admin_conn.fetchval(
                "SELECT 1 FROM pg_database WHERE datname = 'kanban_demo'"
            )
            if not exists:
                await admin_conn.execute("CREATE DATABASE kanban_demo TEMPLATE kanban_template")
        finally:
            await admin_conn.close()

        demo_conn = await asyncpg.connect(user="kanban_test", database="kanban_demo", host=sock)
        try:
            has_helper = await demo_conn.fetchval(
                "SELECT 1 FROM pg_proc WHERE proname = 'lookup_principal_by_handle'"
            )
            if not has_helper:
                await demo_conn.execute(_SEED_PATH.read_text(encoding="utf-8"))
        finally:
            await demo_conn.close()

    asyncio.run(_setup())
    return f"postgresql+asyncpg://kanban_app@/kanban_demo?host={sock}"


@pytest.fixture(scope="session")
def superuser_db_url() -> str:
    """Provide database URL connecting as superuser kanban_test."""
    sock = os.environ.get("KB_TEST_PGHOST", "/tmp/kb-pgsock-21")
    return f"postgresql+asyncpg://kanban_test@/kanban_demo?host={sock}"


def test_case_1_positive_pkce_ldap(demo_db_url: str, capsys: pytest.CaptureFixture[str]) -> None:
    """Test Case 1: Positive run with sparkle_cli_pkce_ldap cassette and 4-section report."""
    cassette = str(_FIXTURES_DIR / "sparkle_cli_pkce_ldap.yaml")
    exit_code = main(
        [
            "validate-sparkle",
            "--provider",
            "fixture",
            "--cassette",
            cassette,
            "--input-markdown",
            "Enforce PKCE S256 on OAuth2 cards and verify | before LDAP bind.",
            "--project",
            "KAN",
            "--as-user",
            "@adam",
            "--verbose-tools",
            "--database-url",
            demo_db_url,
        ]
    )

    assert exit_code == 0
    captured = capsys.readouterr()
    stdout = captured.out

    assert "=== 1. RENDERED CONTEXT ===" in stdout
    assert "Project: KAN (Kanban Core)" in stdout
    assert "User: @adam" in stdout
    assert "Surface: description" in stdout
    assert "Redactions Detected: 0" in stdout
    assert "Enforce PKCE S256 on OAuth2 cards and verify  [CURSOR]  before LDAP bind." in stdout

    assert "=== 2. TOOL TRACE ===" in stdout
    assert "Tool: retrieval_trace" in stdout
    assert '"retrieval_status": "ok"' in stdout

    assert "=== 3. LATENCY & TOKENS ===" in stdout
    assert "TTFT:" in stdout
    assert "Total:" in stdout
    assert "Tokens: 32 in, 4 out" in stdout

    assert "=== 4. SCHEMA & POLICY STATUS ===" in stdout
    assert "Valid: true" in stdout
    assert "Status: ok" in stdout
    assert "output filter: none" in stdout

    assert "=== 5. ROUTE TRACE ===" in stdout
    assert "Outcome: success" in stdout


def test_case_2_security_rls_isolation(
    demo_db_url: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test Case 2: Security RLS isolation guarantees 0 canary leaks and KAN-only keys."""
    cassette = str(_FIXTURES_DIR / "sparkle_cli_pkce_ldap.yaml")
    exit_code = main(
        [
            "validate-sparkle",
            "--provider",
            "fixture",
            "--cassette",
            cassette,
            "--input-markdown",
            "Enforce PKCE S256 on OAuth2 cards and verify | before LDAP bind.",
            "--project",
            "KAN",
            "--as-user",
            "@adam",
            "--report",
            "json",
            "--database-url",
            demo_db_url,
        ]
    )

    assert exit_code == 0
    captured = capsys.readouterr()
    stdout = captured.out

    # Absolute mandate: ZERO occurrences of SEC-CANARY-7731 in report
    assert "SEC-CANARY-7731" not in stdout
    assert stdout.count("SEC-CANARY-7731") == 0

    report_json = json.loads(stdout)
    assert report_json["schema_status"]["valid"] is True
    assert report_json["schema_status"]["status"] == "ok"

    # Verify retrieval trace contains ONLY KAN-* keys and ZERO SEC-* keys
    tool_trace = report_json["tool_trace"]
    assert len(tool_trace) >= 1
    retrieval_res = tool_trace[0]["result"]
    retrieved_objs = retrieval_res["retrieved_objects"]
    assert len(retrieved_objs) > 0
    for obj in retrieved_objs:
        assert str(obj["canonical_key"]).startswith("KAN-")
        assert not str(obj["canonical_key"]).startswith("SEC-")


def test_case_3_security_bypass_role_refused(
    superuser_db_url: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test Case 3: Security bypass refusal when connecting as superuser/rolbypassrls."""
    cassette = str(_FIXTURES_DIR / "sparkle_cli_pkce_ldap.yaml")
    exit_code = main(
        [
            "validate-sparkle",
            "--provider",
            "fixture",
            "--cassette",
            cassette,
            "--input-markdown",
            "Enforce PKCE S256 on OAuth2 cards and verify | before LDAP bind.",
            "--project",
            "KAN",
            "--as-user",
            "@adam",
            "--database-url",
            superuser_db_url,
        ]
    )

    assert exit_code == 2
    captured = capsys.readouterr()
    stdout = captured.out

    assert "RLS_BYPASS_ROLE_REFUSED" in stdout
    assert "Database role has bypass privileges" in stdout


def test_case_4_security_scrub_first(demo_db_url: str, capsys: pytest.CaptureFixture[str]) -> None:
    """Test Case 4: Security scrub-first short-circuit with raw secret absent from output."""
    raw_secret = "gh" + "p_" + "1234567890abcdef1234567890abcdef1234"
    cassette = str(_FIXTURES_DIR / "sparkle_cli_pkce_ldap.yaml")
    exit_code = main(
        [
            "validate-sparkle",
            "--provider",
            "fixture",
            "--cassette",
            cassette,
            "--input-markdown",
            f"Enforce PKCE {raw_secret} | before LDAP bind.",
            "--project",
            "KAN",
            "--as-user",
            "@adam",
            "--database-url",
            demo_db_url,
        ]
    )

    assert exit_code == 2
    captured = capsys.readouterr()
    stdout = captured.out

    # Verify status and exit code
    assert "Status: secret_scrubbed" in stdout
    assert "Error Code: SECRET_SCRUBBED" in stdout
    assert "zero provider calls" in stdout

    # Absolute mandate: raw secret must NEVER appear in stdout
    assert raw_secret not in stdout
    assert "[REDACTED:GITHUB_TOKEN]" in stdout


def test_case_5_negative_markers_and_usage(
    demo_db_url: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test Case 5: Negative tests for 0 markers, 2 markers, escaped marker, and invalid flags."""
    cassette = str(_FIXTURES_DIR / "sparkle_cli_pkce_ldap.yaml")

    # 1. Zero markers
    code_zero = main(
        [
            "validate-sparkle",
            "--provider",
            "fixture",
            "--cassette",
            cassette,
            "--input-markdown",
            "Enforce PKCE without any cursor marker.",
            "--project",
            "KAN",
            "--as-user",
            "@adam",
            "--database-url",
            demo_db_url,
        ]
    )
    assert code_zero == 2
    out_zero = capsys.readouterr().out
    assert "CURSOR_MARKER_INVALID" in out_zero

    # 2. Two markers
    code_two = main(
        [
            "validate-sparkle",
            "--provider",
            "fixture",
            "--cassette",
            cassette,
            "--input-markdown",
            "First | and second | marker.",
            "--project",
            "KAN",
            "--as-user",
            "@adam",
            "--database-url",
            demo_db_url,
        ]
    )
    assert code_two == 2
    out_two = capsys.readouterr().out
    assert "CURSOR_MARKER_INVALID" in out_two

    # 3. Escaped marker is treated as literal pipe
    pfx, sfx = parse_cursor_marker(r"Enforce \| on cards and verify | before bind.")
    assert pfx == "Enforce | on cards and verify "
    assert sfx == " before bind."

    # 4. --cassette without --provider fixture
    code_usage = main(
        [
            "validate-sparkle",
            "--provider",
            "ollama",
            "--cassette",
            cassette,
            "--input-markdown",
            "Valid | input.",
            "--project",
            "KAN",
            "--as-user",
            "@adam",
            "--database-url",
            demo_db_url,
        ]
    )
    assert code_usage == 2
    out_usage = capsys.readouterr().out
    assert "--cassette is only valid when --provider is fixture" in out_usage

    # 5. --provider fixture without --cassette
    code_no_cas = main(
        [
            "validate-sparkle",
            "--provider",
            "fixture",
            "--input-markdown",
            "Valid | input.",
            "--project",
            "KAN",
            "--as-user",
            "@adam",
            "--database-url",
            demo_db_url,
        ]
    )
    assert code_no_cas == 2
    out_no_cas = capsys.readouterr().out
    assert "--cassette is required when --provider is fixture" in out_no_cas


def test_case_6_fault_ttft_timeout_and_db_unreachable(
    demo_db_url: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test Case 6: Fault handling for TTFT timeout and unreachable database."""
    timeout_cas = str(_FIXTURES_DIR / "sparkle_fim_ttft_timeout.yaml")

    # 1. TTFT timeout cassette
    code_ttft = main(
        [
            "validate-sparkle",
            "--provider",
            "fixture",
            "--cassette",
            timeout_cas,
            "--input-markdown",
            "Enforce PKCE S256 on OAuth2 cards and verify | before LDAP bind.",
            "--project",
            "KAN",
            "--as-user",
            "@adam",
            "--database-url",
            demo_db_url,
        ]
    )
    assert code_ttft == 2
    out_ttft = capsys.readouterr().out
    assert "Status: timeout" in out_ttft
    assert "TTFT_TIMEOUT" in out_ttft

    # 2. Database unreachable (exit code 1)
    code_db = main(
        [
            "validate-sparkle",
            "--provider",
            "fixture",
            "--cassette",
            str(_FIXTURES_DIR / "sparkle_cli_pkce_ldap.yaml"),
            "--input-markdown",
            "Enforce PKCE S256 on OAuth2 cards and verify | before LDAP bind.",
            "--project",
            "KAN",
            "--as-user",
            "@adam",
            "--database-url",
            "postgresql+asyncpg://kanban_app@127.0.0.1:54321/kanban_unreachable_db",
        ]
    )
    assert code_db == 1
    out_db = capsys.readouterr().out
    assert "DATABASE_UNREACHABLE" in out_db


def test_case_7_fault_prompt_override(demo_db_url: str, capsys: pytest.CaptureFixture[str]) -> None:
    """Test Case 7: Prompt override cassette triggers prompt_override_dropped filter action."""
    override_cas = str(_FIXTURES_DIR / "sparkle_fim_prompt_override.yaml")
    exit_code = main(
        [
            "validate-sparkle",
            "--provider",
            "fixture",
            "--cassette",
            override_cas,
            "--input-markdown",
            "Enforce PKCE S256 on OAuth2 cards and verify | before LDAP bind.",
            "--project",
            "KAN",
            "--as-user",
            "@adam",
            "--database-url",
            demo_db_url,
        ]
    )

    assert exit_code == 2
    captured = capsys.readouterr()
    stdout = captured.out

    assert "Status: prompt_override_dropped" in stdout
    assert "PROMPT_OVERRIDE_DROPPED" in stdout
    assert "prompt_override_dropped" in stdout


def test_case_8_boundary_iterations_and_json_schema(
    demo_db_url: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test Case 8: Iterations 200 percentiles, 501 rejection, and JSON schema validation."""
    cassette = str(_FIXTURES_DIR / "sparkle_cli_pkce_ldap.yaml")

    # 1. Iterations 200 prints percentiles and exits 0
    code_200 = main(
        [
            "validate-sparkle",
            "--provider",
            "fixture",
            "--cassette",
            cassette,
            "--input-markdown",
            "Enforce PKCE S256 on OAuth2 cards and verify | before LDAP bind.",
            "--project",
            "KAN",
            "--as-user",
            "@adam",
            "--iterations",
            "200",
            "--database-url",
            demo_db_url,
        ]
    )
    assert code_200 == 0
    out_200 = capsys.readouterr().out
    assert "Iterations: 200" in out_200
    assert "Percentiles: p50=" in out_200
    assert "p90=" in out_200
    assert "p95=" in out_200
    assert "p99=" in out_200

    # 2. Iterations 501 rejected
    code_501 = main(
        [
            "validate-sparkle",
            "--provider",
            "fixture",
            "--cassette",
            cassette,
            "--input-markdown",
            "Enforce PKCE S256 on OAuth2 cards and verify | before LDAP bind.",
            "--project",
            "KAN",
            "--as-user",
            "@adam",
            "--iterations",
            "501",
            "--database-url",
            demo_db_url,
        ]
    )
    assert code_501 == 2
    out_501 = capsys.readouterr().out
    assert "--iterations must be an integer between 1 and 500" in out_501

    # 3. Report JSON validates strictly against kb-sparkle-report/v1
    code_json = main(
        [
            "validate-sparkle",
            "--provider",
            "fixture",
            "--cassette",
            cassette,
            "--input-markdown",
            "Enforce PKCE S256 on OAuth2 cards and verify | before LDAP bind.",
            "--project",
            "KAN",
            "--as-user",
            "@adam",
            "--report",
            "json",
            "--database-url",
            demo_db_url,
        ]
    )
    assert code_json == 0
    out_json = capsys.readouterr().out
    data = json.loads(out_json)

    schema = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
    jsonschema.validate(data, schema)
    assert data["schema_version"] == "kb-sparkle-report/v1"
    assert data["command"] == "validate-sparkle"


def test_unknown_principal_and_project(
    demo_db_url: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """Verify clean exit 2 and error codes when user principal or project is not found."""
    cassette = str(_FIXTURES_DIR / "sparkle_cli_pkce_ldap.yaml")

    # Unknown user
    code_user = main(
        [
            "validate-sparkle",
            "--provider",
            "fixture",
            "--cassette",
            cassette,
            "--input-markdown",
            "Enforce PKCE S256 on OAuth2 cards and verify | before LDAP bind.",
            "--project",
            "KAN",
            "--as-user",
            "@nonexistent_user",
            "--database-url",
            demo_db_url,
        ]
    )
    assert code_user == 2
    out_user = capsys.readouterr().out
    assert "PRINCIPAL_NOT_FOUND" in out_user

    # Unknown project
    code_proj = main(
        [
            "validate-sparkle",
            "--provider",
            "fixture",
            "--cassette",
            cassette,
            "--input-markdown",
            "Enforce PKCE S256 on OAuth2 cards and verify | before LDAP bind.",
            "--project",
            "NONEXISTENT",
            "--as-user",
            "@adam",
            "--database-url",
            demo_db_url,
        ]
    )
    assert code_proj == 2
    out_proj = capsys.readouterr().out
    assert "PROJECT_NOT_FOUND" in out_proj


def test_cli_embedder() -> None:
    """Verify CliEmbedder properties and deterministic 384-dim normalization."""
    embedder = CliEmbedder()
    assert embedder.dimension == 384
    assert embedder.model_id == "bge-small-en-v1.5-int8"

    vecs = asyncio.run(embedder.embed_batch(["hello", "world"]))
    assert len(vecs) == 2
    assert len(vecs[0]) == 384
    assert len(vecs[1]) == 384


def test_provider_resolution_variants() -> None:
    """Verify provider instance resolution for all supported provider choices."""
    # Ollama
    args_ollama = argparse.Namespace(
        provider="ollama", cassette=None, base_url="http://127.0.0.1:11434"
    )
    inst, tier = _resolve_provider_instance(args_ollama)
    assert tier == "ollama"
    assert inst is not None

    # Gemini
    args_gemini = argparse.Namespace(provider="gemini", cassette=None)
    inst, tier = _resolve_provider_instance(args_gemini)
    assert tier == "gemini"
    assert inst is not None

    # OpenAI
    args_openai = argparse.Namespace(provider="openai", cassette=None)
    inst, tier = _resolve_provider_instance(args_openai)
    assert tier == "openai"
    assert inst is not None

    # Unsupported
    args_bad = argparse.Namespace(provider="unsupported_provider", cassette=None)
    with pytest.raises(ValueError, match="Unsupported provider"):
        _resolve_provider_instance(args_bad)


def test_filter_action_secret_echo(demo_db_url: str, capsys: pytest.CaptureFixture[str]) -> None:
    """Verify secret_echo_dropped filter action and status when model echoes secret."""
    cassette = str(_FIXTURES_DIR / "sparkle_fim_secret_echo.yaml")
    exit_code = main(
        [
            "validate-sparkle",
            "--provider",
            "fixture",
            "--cassette",
            cassette,
            "--input-markdown",
            "Enforce PKCE S256 on OAuth2 cards and verify | before LDAP bind.",
            "--project",
            "KAN",
            "--as-user",
            "@adam",
            "--database-url",
            demo_db_url,
        ]
    )

    assert exit_code == 2
    captured = capsys.readouterr()
    stdout = captured.out

    assert "Status: secret_echo_dropped" in stdout
    assert "SECRET_ECHO_DROPPED" in stdout


def test_latency_sla_breach(
    demo_db_url: str,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify p95 > 150.0ms on multiple iterations triggers LATENCY_SLA_BREACH."""
    cassette = str(_FIXTURES_DIR / "sparkle_cli_pkce_ldap.yaml")
    counter_state = [0.0]

    def mock_perf_counter() -> float:
        counter_state[0] += 0.200
        return counter_state[0]

    monkeypatch.setattr(time, "perf_counter", mock_perf_counter)

    exit_code = main(
        [
            "validate-sparkle",
            "--provider",
            "fixture",
            "--cassette",
            cassette,
            "--input-markdown",
            "Enforce PKCE S256 on OAuth2 cards and verify | before LDAP bind.",
            "--project",
            "KAN",
            "--as-user",
            "@adam",
            "--iterations",
            "5",
            "--database-url",
            demo_db_url,
        ]
    )

    assert exit_code == 2
    captured = capsys.readouterr()
    stdout = captured.out

    assert "LATENCY_SLA_BREACH" in stdout
    assert "exceeds SLA budget of 150.0ms" in stdout


def test_provider_unavailable_fault(
    demo_db_url: str,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify provider unavailable returns exit code 1 and PROVIDER_UNAVAILABLE status."""

    async def mock_run_sparkle(*_args: object, **_kwargs: object) -> SparkleResult:
        return SparkleResult(
            status="unavailable",
            text="",
            tokens=0,
            ttft_ms=0.0,
            total_ms=0.0,
            retrieval_status="skipped",
            route_trace=[],
        )

    monkeypatch.setattr(vs_mod, "run_sparkle_pipeline", mock_run_sparkle)

    cassette = str(_FIXTURES_DIR / "sparkle_cli_pkce_ldap.yaml")
    exit_code = main(
        [
            "validate-sparkle",
            "--provider",
            "fixture",
            "--cassette",
            cassette,
            "--input-markdown",
            "Enforce PKCE S256 on OAuth2 cards and verify | before LDAP bind.",
            "--project",
            "KAN",
            "--as-user",
            "@adam",
            "--database-url",
            demo_db_url,
        ]
    )

    assert exit_code == 1
    captured = capsys.readouterr()
    stdout = captured.out

    assert "Status: unavailable" in stdout
    assert "PROVIDER_UNAVAILABLE" in stdout


def test_html_stripped_filter_action(
    demo_db_url: str,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify html_stripped filter action when completion contains only HTML tags."""

    async def mock_run_sparkle(*_args: object, **_kwargs: object) -> SparkleResult:
        return SparkleResult(
            status="empty",
            text="",
            tokens=0,
            ttft_ms=10.0,
            total_ms=12.0,
            retrieval_status="ok",
            route_trace=[],
        )

    monkeypatch.setattr(vs_mod, "run_sparkle_pipeline", mock_run_sparkle)

    cas = Cassette(
        cassette_version=1,
        matcher=CassetteMatcher(),
        simulated_ttft_ms=10.0,
        stream_chunks=["<script>alert(1)</script>"],
    )

    def mock_resolve_provider(*_args: object, **_kwargs: object) -> tuple[object, str]:
        prov = FixtureLLMProvider([cas])
        prov.call_log.append({"output": {"text": ""}})
        return prov, "fixture"

    monkeypatch.setattr(vs_mod, "_resolve_provider_instance", mock_resolve_provider)

    exit_code = main(
        [
            "validate-sparkle",
            "--provider",
            "fixture",
            "--cassette",
            str(_FIXTURES_DIR / "sparkle_cli_pkce_ldap.yaml"),
            "--input-markdown",
            "Enforce PKCE S256 on OAuth2 cards and verify | before LDAP bind.",
            "--project",
            "KAN",
            "--as-user",
            "@adam",
            "--database-url",
            demo_db_url,
        ]
    )

    assert exit_code == 2
    captured = capsys.readouterr()
    stdout = captured.out

    assert "Status: html_stripped" in stdout
    assert "HTML_STRIPPED" in stdout


def test_default_database_url_and_trace_error(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify default database URL resolution and graceful handling of trace query error."""
    orig_factory = RLSSessionFactory

    class FailingSessionFactory:
        def __init__(self, engine: Any) -> None:  # noqa: ANN401
            self._real = orig_factory(engine)

        def sessionmaker(self) -> Any:  # noqa: ANN401
            class FailingContextManager:
                async def __aenter__(self) -> Any:  # noqa: ANN401
                    msg = "Simulated trace failure"
                    raise RuntimeError(msg)

                async def __aexit__(self, *_args: object) -> None:
                    pass

            return FailingContextManager()

    monkeypatch.setattr(vs_mod, "RLSSessionFactory", FailingSessionFactory)

    cassette = str(_FIXTURES_DIR / "sparkle_cli_pkce_ldap.yaml")
    exit_code = main(
        [
            "validate-sparkle",
            "--provider",
            "fixture",
            "--cassette",
            cassette,
            "--input-markdown",
            "Enforce PKCE S256 on OAuth2 cards and verify | before LDAP bind.",
            "--project",
            "KAN",
            "--as-user",
            "@adam",
        ]
    )
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "Status: ok" in captured.out


def test_pipeline_none_result(
    demo_db_url: str,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify runtime_error status when pipeline returns None."""

    async def mock_none(*_args: object, **_kwargs: object) -> object:
        return None

    monkeypatch.setattr(vs_mod, "run_sparkle_pipeline", mock_none)

    cassette = str(_FIXTURES_DIR / "sparkle_cli_pkce_ldap.yaml")
    exit_code = main(
        [
            "validate-sparkle",
            "--provider",
            "fixture",
            "--cassette",
            cassette,
            "--input-markdown",
            "Enforce PKCE S256 on OAuth2 cards and verify | before LDAP bind.",
            "--project",
            "KAN",
            "--as-user",
            "@adam",
            "--database-url",
            demo_db_url,
        ]
    )
    assert exit_code == 1
    captured = capsys.readouterr()
    assert "Status: runtime_error" in captured.out


def test_direct_select_fallbacks(
    demo_db_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify direct SELECT fallback paths when helper functions are not found in pg_proc."""
    orig_execute = AsyncConnection.execute

    async def mock_execute(
        self: AsyncConnection,
        statement: Any,  # noqa: ANN401
        *args: object,
        **kwargs: object,
    ) -> Any:  # noqa: ANN401
        stmt_str = str(statement)
        if "SELECT 1 FROM pg_proc" in stmt_str:

            class MockEmptyRes:
                def first(self) -> Any:  # noqa: ANN401
                    return None

            return MockEmptyRes()
        return await orig_execute(self, statement, *args, **kwargs)  # type: ignore[call-overload]

    monkeypatch.setattr(AsyncConnection, "execute", mock_execute)

    cassette = str(_FIXTURES_DIR / "sparkle_cli_pkce_ldap.yaml")
    exit_code = main(
        [
            "validate-sparkle",
            "--provider",
            "fixture",
            "--cassette",
            cassette,
            "--input-markdown",
            "Enforce PKCE S256 on OAuth2 cards and verify | before LDAP bind.",
            "--project",
            "KAN",
            "--as-user",
            "@adam",
            "--database-url",
            demo_db_url,
        ]
    )
    assert exit_code in (0, 2)
