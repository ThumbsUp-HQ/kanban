# Copyright 2026 Kanban Platform Contributors
"""Deterministic token benchmark comparing raw REST JSON vs LOD summary YAML (S11.1)."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

from mcp.lod import Lod, project_issue
from mcp.yaml_out import dump_yaml

__all__ = [
    "count_tokens",
    "run_benchmark",
]

_MIN_TOKEN_REDUCTION_PCT = 78.0


def count_tokens(text: str) -> int:
    """Deterministic approximate tokenizer counting word and punctuation tokens."""
    return len(re.findall(r"\w+|[^\w\s]", text))


def run_benchmark(fixture_path: Path | None = None) -> tuple[int, int, float]:
    """Execute token benchmark and return (raw_tokens, yaml_tokens, reduction_pct)."""
    if fixture_path is None:
        fixture_path = Path(__file__).parent.parent / "tests" / "fixtures" / "issues_raw_rest.json"

    with fixture_path.open("r", encoding="utf-8") as f:
        raw_issues: list[dict[str, Any]] = json.load(f)

    raw_json = json.dumps(raw_issues)
    raw_tokens = count_tokens(raw_json)

    summary_issues = [project_issue(iss, Lod.SUMMARY) for iss in raw_issues]
    yaml_summary = dump_yaml(summary_issues)
    yaml_tokens = count_tokens(yaml_summary)

    if raw_tokens == 0:
        msg = "Benchmark fixture yielded 0 raw tokens"
        raise ValueError(msg)

    reduction_pct = (1.0 - (yaml_tokens / raw_tokens)) * 100.0
    return raw_tokens, yaml_tokens, reduction_pct


def main() -> None:
    """CLI entrypoint for token benchmark."""
    raw_tokens, yaml_tokens, reduction = run_benchmark()
    sys.stdout.write("================ TOKEN EFFICIENCY BENCHMARK ================\n")
    sys.stdout.write(f"Raw REST JSON Tokens:    {raw_tokens}\n")
    sys.stdout.write(f"LOD Summary YAML Tokens: {yaml_tokens}\n")
    sys.stdout.write(f"Token Reduction:         {reduction:.2f}%\n")
    sys.stdout.write(f"Required Threshold:      {_MIN_TOKEN_REDUCTION_PCT:.2f}%\n")
    sys.stdout.write("=============================================================\n")

    if reduction < _MIN_TOKEN_REDUCTION_PCT:
        sys.stderr.write(
            f"ERROR: Token reduction ({reduction:.2f}%) fell below required "
            f"{_MIN_TOKEN_REDUCTION_PCT:.2f}%\n"
        )
        sys.exit(1)

    sys.stdout.write("BENCHMARK STATUS: PASSED\n")
    sys.exit(0)


if __name__ == "__main__":
    main()
