"""Harness registration and verdict grade validation tests (KAN-544)."""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import ValidationError

from agent.context.verdict import TransitionVerdict, VerdictParseError, parse_verdict_output
from agent.gates.worker import HarnessRegistry

NONCE = "n" * 24
GRADES = ["A+", "A", "A-", "B+", "B", "B-", "C+", "C", "F"]


def test_registry_registers_all_default_harnesses() -> None:
    registry = HarnessRegistry()
    for kind in ("in_app_sdk", "cli_pipe", "remote_runner"):
        assert kind in registry
        assert registry.get(kind) is not None


def test_registry_without_defaults_is_empty() -> None:
    registry = HarnessRegistry(auto_register_defaults=False)
    assert "cli_pipe" not in registry


@pytest.mark.parametrize("grade", GRADES)
def test_transition_verdict_accepts_grade(grade: Any) -> None:
    verdict = TransitionVerdict(nonce=NONCE, decision="approve", reason_markdown="ok", grade=grade)
    assert verdict.grade == grade


@pytest.mark.parametrize("grade", ["D", "a", "A++", "", "Z"])
def test_transition_verdict_rejects_invalid_grade(grade: Any) -> None:
    with pytest.raises(ValidationError):
        TransitionVerdict(nonce=NONCE, decision="approve", reason_markdown="ok", grade=grade)


def test_grade_defaults_to_none() -> None:
    assert TransitionVerdict(nonce=NONCE, decision="approve", reason_markdown="ok").grade is None


def _raw(grade: str | None) -> str:
    body: dict[str, object] = {
        "schema": "kb-transition-verdict/v1",
        "nonce": NONCE,
        "decision": "approve",
        "reason_markdown": "fine",
    }
    if grade is not None:
        body["grade"] = grade
    return json.dumps(body)


@pytest.mark.parametrize("grade", [*GRADES, None])
def test_parse_verdict_output_forwards_grade(grade: str | None) -> None:
    ctx = SimpleNamespace(verdict_nonce=NONCE, allowed_mutable_fields=frozenset())
    result = parse_verdict_output(_raw(grade).encode("utf-8"), ctx)  # type: ignore[arg-type]
    assert result.decision.grade == grade
    assert result.verdict.grade == grade


def test_parse_verdict_output_rejects_invalid_grade() -> None:
    ctx = SimpleNamespace(verdict_nonce=NONCE, allowed_mutable_fields=frozenset())
    with pytest.raises(VerdictParseError):
        parse_verdict_output(_raw("D").encode("utf-8"), ctx)  # type: ignore[arg-type]
