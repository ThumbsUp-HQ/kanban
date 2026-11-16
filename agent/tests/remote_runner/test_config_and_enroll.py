# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Unit tests for RunnerConfig and kanban-agent-runner enroll CLI (KB-P5-22b, S14.2)."""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import httpx
import pytest
import yaml

from agent.remote_runner.cli import _write_secure_file, enroll_runner, main, run_daemon
from agent.remote_runner.config import (
    KeyPermissionsError,
    RunnerConfig,
    load_runner_config,
    validate_key_permissions,
)
from agent.remote_runner.daemon import RunnerRevokedError


def test_runner_config_defaults_and_validation(tmp_path: Path) -> None:
    """Test RunnerConfig field defaults, extra=forbid, and pool_slug regex."""
    cert_file = tmp_path / "client.crt"
    key_file = tmp_path / "client.key"
    ca_file = tmp_path / "ca.crt"

    cert_file.write_text("cert")
    key_file.write_text("key")
    key_file.chmod(0o600)
    ca_file.write_text("ca")

    cfg = RunnerConfig(
        server_url="https://kanban.example.com",
        pool_slug="gpu-pool-1",
        client_cert_path=cert_file,
        client_key_path=key_file,
        ca_cert_path=ca_file,
    )
    assert cfg.max_concurrency == 1
    assert cfg.heartbeat_interval_s == 15.0
    assert cfg.resolve_wss_url() == "wss://kanban.example.com/api/v1/agent-runners/ws"

    # URL resolution variations
    cfg_http = cfg.model_copy(update={"server_url": "http://localhost:8000"})
    assert cfg_http.resolve_wss_url() == "ws://localhost:8000/api/v1/agent-runners/ws"

    cfg_wss = cfg.model_copy(update={"wss_url": "wss://custom.internal/ws"})
    assert cfg_wss.resolve_wss_url() == "wss://custom.internal/ws"

    # Invalid pool slugs
    with pytest.raises(ValueError, match="Invalid pool_slug"):
        RunnerConfig(
            server_url="https://kanban.example.com",
            pool_slug="UPPERCASE_INVALID",
            client_cert_path=cert_file,
            client_key_path=key_file,
            ca_cert_path=ca_file,
        )

    with pytest.raises(ValueError, match="Invalid pool_slug"):
        RunnerConfig(
            server_url="https://kanban.example.com",
            pool_slug="invalid_underscores",
            client_cert_path=cert_file,
            client_key_path=key_file,
            ca_cert_path=ca_file,
        )

    # Extra forbid
    with pytest.raises(ValueError, match="extra_forbidden"):
        RunnerConfig.model_validate(
            {
                "server_url": "https://kanban.example.com",
                "pool_slug": "pool-a",
                "client_cert_path": str(cert_file),
                "client_key_path": str(key_file),
                "ca_cert_path": str(ca_file),
                "unauthorized_field": True,
            }
        )


def test_key_permissions_validation(tmp_path: Path) -> None:
    """Test validate_key_permissions rejects group/other permissions and accepts 0600/0400."""
    key_file = tmp_path / "private.key"
    key_file.write_text("test-secret-key")

    # Mode 0600: valid
    key_file.chmod(0o600)
    validate_key_permissions(key_file)

    # Mode 0400: valid
    key_file.chmod(0o400)
    validate_key_permissions(key_file)

    # Mode 0644: invalid (world readable)
    key_file.chmod(0o644)
    with pytest.raises(KeyPermissionsError, match="KEY_PERMISSIONS_TOO_OPEN"):
        validate_key_permissions(key_file)

    # Mode 0660: invalid (group readable)
    key_file.chmod(0o660)
    with pytest.raises(KeyPermissionsError, match="KEY_PERMISSIONS_TOO_OPEN"):
        validate_key_permissions(key_file)

    # Non-existent file: passes (not yet created)
    validate_key_permissions(tmp_path / "nonexistent.key")


def test_load_runner_config(tmp_path: Path) -> None:
    """Test loading and validating RunnerConfig from YAML file."""
    cfg_file = tmp_path / "config.yaml"
    key_file = tmp_path / "test.key"
    key_file.write_text("key")
    key_file.chmod(0o600)

    cfg_dict = {
        "server_url": "https://kanban.internal",
        "pool_slug": "air-gap-nodes",
        "client_cert_path": str(tmp_path / "test.crt"),
        "client_key_path": str(key_file),
        "ca_cert_path": str(tmp_path / "ca.crt"),
        "max_concurrency": 4,
    }
    cfg_file.write_text(yaml.safe_dump(cfg_dict), encoding="utf-8")

    loaded = load_runner_config(cfg_file)
    assert loaded.max_concurrency == 4
    assert loaded.pool_slug == "air-gap-nodes"

    # Missing file
    with pytest.raises(FileNotFoundError):
        load_runner_config(tmp_path / "missing.yaml")


def test_cli_token_cmdline_secrecy(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test passing --token on argv is rejected to prevent exposure in /proc/cmdline."""
    stderr_buf = io.StringIO()
    monkeypatch.setattr(sys, "stderr", stderr_buf)

    # Test --token
    rc1 = main(["enroll", "--server-url", "https://kanban", "--token", "secret", "--pool", "p"])
    assert rc1 == 2
    assert "Passing --token on CLI arguments is rejected for security" in stderr_buf.getvalue()

    # Test --token=
    stderr_buf.truncate(0)
    stderr_buf.seek(0)
    rc2 = main(["enroll", "--server-url", "https://kanban", "--token=secret", "--pool", "p"])
    assert rc2 == 2
    assert "Use --token-stdin" in stderr_buf.getvalue()


def test_enroll_runner_flow(tmp_path: Path) -> None:
    """Test enroll_runner generates key, CSR, exchanges token, and writes secure files."""
    state_dir = tmp_path / "runner-state"

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/agent-runners/enroll"
        data = json.loads(request.content)
        assert data["enrollment_token"] == "kb_rnr_enroll_test_token_123"
        assert "-----BEGIN CERTIFICATE REQUEST-----" in data["csr_pem"]
        assert data["hostname"] == "test-worker-1"

        return httpx.Response(
            status_code=201,
            json={
                "runner_id": "0196ed40-7b2a-7000-8000-112233445566",
                "client_cert_pem": (
                    "-----BEGIN CERTIFICATE-----\nMIIB...\n-----END CERTIFICATE-----"
                ),
                "ca_cert_pem": "-----BEGIN CERTIFICATE-----\nMIIC...\n-----END CERTIFICATE-----",
                "wss_url": "wss://kanban.internal/api/v1/agent-runners/ws",
            },
        )

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)

    cfg_path = enroll_runner(
        server_url="https://kanban.internal",
        enrollment_token="kb_rnr_enroll_test_token_123",  # noqa: S106
        pool_slug="gpu-workers",
        state_dir=state_dir,
        hostname="test-worker-1",
        client=client,
    )

    assert cfg_path.is_file()
    key_path = state_dir / "client.key"
    cert_path = state_dir / "client.crt"
    ca_path = state_dir / "ca.crt"

    assert key_path.is_file()
    assert cert_path.is_file()
    assert ca_path.is_file()

    # Verify atomic 0600 mode on private key and config
    assert (key_path.stat().st_mode & 0o077) == 0
    assert (cfg_path.stat().st_mode & 0o077) == 0

    # Verify config loads cleanly
    cfg = load_runner_config(cfg_path)
    assert cfg.pool_slug == "gpu-workers"
    assert cfg.server_url == "https://kanban.internal"

    # Empty token fails
    with pytest.raises(ValueError, match="Enrollment token is empty"):
        enroll_runner(
            server_url="https://kanban.internal",
            enrollment_token="   ",  # noqa: S106
            pool_slug="gpu-workers",
            state_dir=state_dir,
            client=client,
        )

    # Non-201 response fails
    def error_handler(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=401, text="Invalid token")

    err_client = httpx.Client(transport=httpx.MockTransport(error_handler))
    with pytest.raises(RuntimeError, match="Enrollment failed with status 401"):
        enroll_runner(
            server_url="https://kanban.internal",
            enrollment_token="invalid_token",  # noqa: S106
            pool_slug="gpu-workers",
            state_dir=state_dir,
            client=err_client,
        )


def test_cli_subcommands_dispatch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test main() CLI dispatching enroll and run subcommands."""
    state_dir = tmp_path / "cli-state"

    # 1. Enroll subcommand via stdin
    def mock_handler(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code=201,
            json={
                "runner_id": "0196ed40-7b2a-7000-8000-112233445566",
                "client_cert_pem": "client-cert",
                "ca_cert_pem": "ca-cert",
                "wss_url": "wss://kanban.internal/api/v1/agent-runners/ws",
            },
        )

    orig_client = httpx.Client
    monkeypatch.setattr(
        httpx,
        "Client",
        lambda *_args, **_kwargs: orig_client(transport=httpx.MockTransport(mock_handler)),
    )
    monkeypatch.setattr(sys, "stdin", io.StringIO("kb_rnr_enroll_token_abc\n"))

    stdout_buf = io.StringIO()
    monkeypatch.setattr(sys, "stdout", stdout_buf)

    rc_enroll = main(
        [
            "enroll",
            "--server-url",
            "https://kanban.internal",
            "--token-stdin",
            "--pool",
            "test-pool",
            "--state-dir",
            str(state_dir),
        ]
    )
    assert rc_enroll == 0
    assert "Enrollment successful" in stdout_buf.getvalue()

    # 2. Run subcommand with key permissions error
    key_file = state_dir / "client.key"
    key_file.chmod(0o666)  # world writable/readable
    stderr_buf = io.StringIO()
    monkeypatch.setattr(sys, "stderr", stderr_buf)

    rc_run = main(["run", "--config", str(state_dir / "config.yaml")])
    assert rc_run == 1
    assert "KEY_PERMISSIONS_TOO_OPEN" in stderr_buf.getvalue()


def test_runner_config_url_without_scheme(tmp_path: Path) -> None:
    """Test URL resolution when server_url lacks http/https prefix."""
    key_file = tmp_path / "client.key"
    key_file.write_text("key")
    key_file.chmod(0o600)

    cfg = RunnerConfig(
        server_url="kanban.internal",
        pool_slug="test-pool",
        client_cert_path=tmp_path / "client.crt",
        client_key_path=key_file,
        ca_cert_path=tmp_path / "ca.crt",
    )
    assert cfg.resolve_wss_url() == "wss://kanban.internal/api/v1/agent-runners/ws"

    with pytest.raises(FileNotFoundError):
        load_runner_config(tmp_path / "missing.yaml")


def test_write_secure_file_error_cleanup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test _write_secure_file unlinks temporary file on write failure."""

    def failing_replace(_src: Path, _dst: Path) -> None:
        msg = "Disk error"
        raise OSError(msg)

    monkeypatch.setattr(Path, "replace", failing_replace)
    target = tmp_path / "secure.txt"
    with pytest.raises(OSError, match="Disk error"):
        _write_secure_file(target, "secret-data")


def test_run_daemon_lifecycle(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test run_daemon lifecycle for normal exit, revocation (78), and SIGINT."""
    key_file = tmp_path / "client.key"
    key_file.write_text("key")
    key_file.chmod(0o600)
    cfg_file = tmp_path / "config.yaml"
    cfg = RunnerConfig(
        server_url="https://kanban.internal",
        pool_slug="test-pool",
        client_cert_path=tmp_path / "client.crt",
        client_key_path=key_file,
        ca_cert_path=tmp_path / "ca.crt",
    )
    cfg_file.write_text(yaml.safe_dump(cfg.model_dump(mode="json")))

    # 1. Normal run
    async def mock_run_ok(_self: object) -> None:
        pass

    monkeypatch.setattr("agent.remote_runner.daemon.RunnerDaemon.run_forever", mock_run_ok)
    assert run_daemon(cfg_file) == 0

    # 2. Revoked run (exit code 78)
    async def mock_run_revoked(_self: object) -> None:
        msg = "Revoked"
        raise RunnerRevokedError(msg)

    monkeypatch.setattr("agent.remote_runner.daemon.RunnerDaemon.run_forever", mock_run_revoked)
    assert run_daemon(cfg_file) == 78

    # 3. KeyboardInterrupt run
    async def mock_run_interrupt(_self: object) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr("agent.remote_runner.daemon.RunnerDaemon.run_forever", mock_run_interrupt)
    assert run_daemon(cfg_file) == 0


def test_main_cli_error_branches(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test main() error reporting for enrollment and daemon failures."""
    # 1. Enroll failure
    orig_client = httpx.Client
    monkeypatch.setattr(
        httpx,
        "Client",
        lambda *_args, **_kwargs: orig_client(
            transport=httpx.MockTransport(lambda _req: httpx.Response(401, text="Invalid token"))
        ),
    )
    monkeypatch.setattr(sys, "stdin", io.StringIO("invalid_token\n"))
    stderr_buf = io.StringIO()
    monkeypatch.setattr(sys, "stderr", stderr_buf)

    rc_enroll = main(
        [
            "enroll",
            "--server-url",
            "https://kanban.internal",
            "--token-stdin",
            "--pool",
            "test-pool",
            "--state-dir",
            str(tmp_path / "err-state"),
        ]
    )
    assert rc_enroll == 1
    assert "Enrollment error" in stderr_buf.getvalue()

    # 2. Run generic exception failure
    stderr_buf2 = io.StringIO()
    monkeypatch.setattr(sys, "stderr", stderr_buf2)

    def failing_run_daemon(_path: Path) -> int:
        msg = "Unexpected daemon crash"
        raise RuntimeError(msg)

    monkeypatch.setattr("agent.remote_runner.cli.run_daemon", failing_run_daemon)
    rc_run = main(["run", "--config", str(tmp_path / "dummy.yaml")])
    assert rc_run == 1
    assert "Runner error: Unexpected daemon crash" in stderr_buf2.getvalue()
