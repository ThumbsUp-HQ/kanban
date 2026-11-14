"""Behavior tests for scripts/ci/upload_dash_log.sh against a local fake Dash server."""

from __future__ import annotations

import json
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from collections.abc import Iterator

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "ci" / "upload_dash_log.sh"
TOKEN = "unit-test-token-value"


class _State:
    posts: list[dict[str, Any]]
    get_log: str
    url: str


@pytest.fixture
def dash(socket_enabled: None) -> Iterator[_State]:  # noqa: ARG001
    """Run a loopback fake Dash that records POSTs and serves one existing log."""
    state = _State()
    state.posts = []
    state.get_log = "previous-job-log"

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            payload = json.dumps({"log": state.get_log}).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length", "0"))
            state.posts.append(
                {
                    "path": self.path,
                    "auth": self.headers.get("Authorization"),
                    "body": self.rfile.read(length).decode(),
                }
            )
            self.send_response(200)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, *_args: object) -> None:
            return

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    state.url = f"http://127.0.0.1:{server.server_port}"
    yield state
    server.shutdown()
    server.server_close()


def _run(
    tmp_path: Path, *args: str, token: str | None = TOKEN, url: str = "http://127.0.0.1:1"
) -> subprocess.CompletedProcess[str]:
    env = {
        "PATH": "/usr/bin:/bin:/usr/local/bin",
        "DASH_URL": url,
        "GITHUB_SHA": "abc123",
        "CI_LOG_DIR": str(tmp_path / "logs"),
    }
    if token is not None:
        env["DASH_TOKEN"] = token
    return subprocess.run(
        [str(SCRIPT), *args], capture_output=True, text=True, check=False, env=env, cwd=tmp_path
    )


def _write_log(tmp_path: Path, name: str, text: str, code: str) -> None:
    logs = tmp_path / "logs"
    logs.mkdir(exist_ok=True)
    (logs / f"{name}.log").write_text(text)
    (logs / f"{name}.exit").write_text(code)


def test_uploads_job_log_with_auth_sha_and_existing_log(tmp_path: Path, dash: _State) -> None:
    """Positive: POST carries bearer auth, sha, prior log, job header and exit code."""
    _write_log(tmp_path, "unit-tests", "all green\n", "0\n")
    result = _run(tmp_path, "python-tests", url=dash.url)
    assert result.returncode == 0
    assert len(dash.posts) == 1
    post = dash.posts[0]
    assert post["auth"] == f"Bearer {TOKEN}"
    assert "sha=abc123" in post["path"]
    assert "provider=forgejo" in post["path"]
    assert "previous-job-log" in post["body"]
    assert "##### job: python-tests #####" in post["body"]
    assert "unit-tests.log (exit 0)" in post["body"]
    assert "all green" in post["body"]


def test_token_never_printed(tmp_path: Path, dash: _State) -> None:
    """Security: the bearer token never reaches stdout or stderr."""
    _write_log(tmp_path, "x", "log\n", "0\n")
    result = _run(tmp_path, "lint-type", url=dash.url)
    assert TOKEN not in result.stdout
    assert TOKEN not in result.stderr


def test_missing_token_skips_without_failing(tmp_path: Path, dash: _State) -> None:
    """Negative: no token means no network call and exit 0."""
    _write_log(tmp_path, "x", "log\n", "0\n")
    result = _run(tmp_path, "lint-type", token=None, url=dash.url)
    assert result.returncode == 0
    assert "DASH_TOKEN missing" in result.stdout
    assert dash.posts == []


def test_no_logs_skips_without_failing(tmp_path: Path, dash: _State) -> None:
    """Boundary: an empty log dir uploads nothing and exits 0."""
    result = _run(tmp_path, "lint-type", url=dash.url)
    assert result.returncode == 0
    assert "no" in result.stdout
    assert dash.posts == []


def test_unreachable_dash_never_fails_job(tmp_path: Path) -> None:
    """Negative: a Dash outage must not turn the job red."""
    _write_log(tmp_path, "x", "log\n", "1\n")
    result = _run(tmp_path, "lint-type")
    assert result.returncode == 0


def test_invalid_job_name_rejected(tmp_path: Path, dash: _State) -> None:
    """Security: job names outside ^[a-z0-9-]+$ exit 64 and upload nothing."""
    _write_log(tmp_path, "x", "log\n", "0\n")
    for bad in ("../x", "Bad", "a b", ""):
        assert _run(tmp_path, bad, url=dash.url).returncode == 64
    assert dash.posts == []
