"""Tests for the shared contract-capture harness (KB-P3-01a case 7)."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import httpx

from kanban.tests.contract import REDACTED, ContractRecorder, redact_headers

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def _exchange() -> tuple[httpx.Request, httpx.Response]:
    request = httpx.Request(
        "POST",
        "http://test/api/v1/projects",
        headers={
            "Cookie": "kb_session=abc",
            "X-CSRF-Token": "tok",
            "Authorization": "Bearer secret",
            "Content-Type": "application/json",
        },
        json={"identifier": "KAN"},
    )
    response = httpx.Response(
        201,
        headers={"Set-Cookie": "kb_session=zzz", "Location": "/api/v1/projects/KAN"},
        json={"id": "1"},
    )
    return request, response


def test_case_7_redacts_credentials_and_writes_valid_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sensitive header values are redacted and the output file is valid JSON."""
    recorder = ContractRecorder(ticket="KANBA-67")
    request, response = _exchange()
    recorder.record("create", request, response)

    out = tmp_path / "nested" / "contract.json"
    monkeypatch.setenv("KB_CONTRACT_OUT", str(out))
    assert recorder.write_if_configured() is True

    document = json.loads(out.read_text(encoding="utf-8"))
    assert document["ticket"] == "KANBA-67"
    (exchange,) = document["exchanges"]
    assert exchange["name"] == "create"
    assert exchange["request"]["method"] == "POST"
    assert exchange["request"]["path"] == "/api/v1/projects"
    assert exchange["request"]["body"] == {"identifier": "KAN"}
    for header in ("cookie", "x-csrf-token", "authorization"):
        assert exchange["request"]["headers"][header] == REDACTED
    assert exchange["response"]["headers"]["set-cookie"] == REDACTED
    assert exchange["response"]["headers"]["location"] == "/api/v1/projects/KAN"
    assert exchange["response"]["status"] == 201
    raw = out.read_text(encoding="utf-8")
    assert "secret" not in raw
    assert "kb_session" not in raw


def test_unconfigured_recorder_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without KB_CONTRACT_OUT no file is produced; ticket falls back to KB_TICKET_ID."""
    monkeypatch.delenv("KB_CONTRACT_OUT", raising=False)
    monkeypatch.setenv("KB_TICKET_ID", "KANBA-1")
    recorder = ContractRecorder()
    assert recorder.ticket == "KANBA-1"
    assert recorder.write_if_configured() is False
    assert list(tmp_path.iterdir()) == []


def test_non_json_and_empty_bodies() -> None:
    """Non-JSON bodies are stored as text and empty bodies as null."""
    recorder = ContractRecorder(ticket="T")
    request = httpx.Request("GET", "http://test/healthz")
    response = httpx.Response(200, content=b"plain text")
    recorder.record("text", request, response)
    recorder.record("empty", request, httpx.Response(204))
    document = recorder.to_document()
    assert document["exchanges"][0]["response"]["body"] == "plain text"
    assert document["exchanges"][0]["request"]["body"] is None
    assert document["exchanges"][1]["response"]["body"] is None


def test_redact_headers_is_case_insensitive() -> None:
    """Header redaction ignores name case and leaves other headers untouched."""
    assert redact_headers({"AUTHORIZATION": "x", "Accept": "json"}) == {
        "AUTHORIZATION": REDACTED,
        "Accept": "json",
    }
