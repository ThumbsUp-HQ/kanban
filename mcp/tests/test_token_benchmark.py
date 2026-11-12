# Copyright 2026 Kanban Platform Contributors
"""Test token benchmark asserting >= 78% reduction on fixture (Test Case 6)."""

from __future__ import annotations

from pathlib import Path

import pytest

from mcp.bench.token_benchmark import count_tokens, main, run_benchmark


def test_token_benchmark_reduction_threshold() -> None:
    """Assert token reduction on fixture achieves >= 78%."""
    default_fixture = Path(__file__).parent / "fixtures" / "issues_raw_rest.json"
    raw_tokens, yaml_tokens, reduction_pct = run_benchmark(default_fixture)
    assert raw_tokens > 0
    assert yaml_tokens > 0
    assert yaml_tokens < raw_tokens
    assert reduction_pct >= 78.0

    # Also test with default None path
    r_def, y_def, _red_def = run_benchmark()
    assert r_def == raw_tokens
    assert y_def == yaml_tokens


def test_count_tokens_punctuation_and_words() -> None:
    """Verify approximate tokenizer handles words and punctuation deterministically."""
    sample = "key: KAN-142, state: [Todo, Done]"
    tokens = count_tokens(sample)
    assert tokens > 0
    assert count_tokens("") == 0


def test_run_benchmark_zero_tokens_raises_value_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify ValueError is raised if raw fixture produces 0 tokens."""
    monkeypatch.setattr("mcp.bench.token_benchmark.count_tokens", lambda _text: 0)
    with pytest.raises(ValueError, match="0 raw tokens"):
        run_benchmark()


def test_main_cli_exit_zero(capsys: pytest.CaptureFixture[str]) -> None:
    """Verify main() exits 0 when reduction meets threshold."""
    with pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == 0
    out = capsys.readouterr().out
    assert "BENCHMARK STATUS: PASSED" in out


def test_main_cli_exit_one_on_low_reduction(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Verify main() exits 1 when reduction falls below threshold."""
    monkeypatch.setattr("mcp.bench.token_benchmark.run_benchmark", lambda: (100, 90, 10.0))
    with pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert "ERROR: Token reduction" in (captured.out + captured.err)
