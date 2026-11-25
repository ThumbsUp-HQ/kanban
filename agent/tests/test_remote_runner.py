# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
# ruff: noqa: D102, D105, D107, SLF001, ARG005, ASYNC110, S106, E501
"""Unit and E2E tests for KAN-64: runner.toml, ca.pem 0600, and daemon PoP challenge."""

from __future__ import annotations

import asyncio
import base64
import io
import json
import os
import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from agent.remote_runner.cli import (
    default_runner_config_path,
    default_runner_state_dir,
    enroll_runner,
    main,
)
from agent.remote_runner.config import (
    RunnerConfig,
    load_runner_config,
)
from agent.remote_runner.daemon import RemoteRunnerDaemon, RunnerDaemon
from kanban.runners.hub import (
    ChallengeResponseFrame,
)


def _generate_test_certs(tmp_path: Path, runner_id: uuid.UUID) -> tuple[Path, Path, Path]:
    """Generate self-signed test CA, client cert, and client key."""
    ca_key = ec.generate_private_key(ec.SECP256R1())
    ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Test Runner CA")])
    now = datetime.now(UTC)
    ca_cert = (
        x509.CertificateBuilder()
        .subject_name(ca_name)
        .issuer_name(ca_name)
        .public_key(ca_key.public_key())
        .serial_number(1)
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=365))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .sign(ca_key, hashes.SHA256())
    )

    client_key = ec.generate_private_key(ec.SECP256R1())
    client_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, f"runner:{runner_id}")])
    client_cert = (
        x509.CertificateBuilder()
        .subject_name(client_name)
        .issuer_name(ca_cert.subject)
        .public_key(client_key.public_key())
        .serial_number(2)
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=30))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(
            x509.ExtendedKeyUsage([x509.oid.ExtendedKeyUsageOID.CLIENT_AUTH]), critical=False
        )
        .sign(ca_key, hashes.SHA256())
    )

    ca_path = tmp_path / "ca.pem"
    cert_path = tmp_path / "client.crt"
    key_path = tmp_path / "client.key"

    ca_path.write_bytes(ca_cert.public_bytes(serialization.Encoding.PEM))
    ca_path.chmod(0o600)
    cert_path.write_bytes(client_cert.public_bytes(serialization.Encoding.PEM))
    cert_path.chmod(0o644)
    key_path.write_bytes(
        client_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    key_path.chmod(0o600)

    return ca_path, cert_path, key_path


def test_runner_config_toml_loading(tmp_path: Path) -> None:
    """Action 4: Test loading runner.toml with cert_path, key_path, ca_cert_path, allowed_repos."""
    runner_id = uuid.uuid4()
    ca_path, cert_path, key_path = _generate_test_certs(tmp_path, runner_id)

    toml_content = f"""
runner_id = "{runner_id}"
server_url = "https://kanban.internal"
cert_path = "{cert_path}"
key_path = "{key_path}"
ca_cert_path = "{ca_path}"
allowed_repos = ["repo-alpha", "repo-beta"]
pool_slug = "linux-workers"
"""
    toml_path = tmp_path / "runner.toml"
    toml_path.write_text(toml_content.strip(), encoding="utf-8")
    toml_path.chmod(0o600)

    cfg = load_runner_config(toml_path)
    assert cfg.runner_id == runner_id
    assert cfg.server_url == "https://kanban.internal"
    assert cfg.client_cert_path == cert_path
    assert cfg.client_key_path == key_path
    assert cfg.ca_cert_path == ca_path
    assert cfg.allowed_repos == ["repo-alpha", "repo-beta"]
    assert cfg.pool_slug == "linux-workers"


def test_enroll_runner_persists_ca_pem_0600_and_runner_toml(tmp_path: Path) -> None:
    """Action 4: Verify enroll_runner writes ca.pem with mode 0o600 and writes runner.toml."""
    state_dir = tmp_path / "enrolled-state"
    runner_id_str = "0196ed40-7b2a-7000-8000-112233445566"

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/agent-runners/enroll"
        return httpx.Response(
            status_code=201,
            json={
                "runner_id": runner_id_str,
                "client_cert_pem": "-----BEGIN CERTIFICATE-----\nMIIB...\n-----END CERTIFICATE-----",
                "ca_cert_pem": "-----BEGIN CERTIFICATE-----\nMIIC...\n-----END CERTIFICATE-----",
                "wss_url": "wss://kanban.internal/api/v1/agent-runners/ws",
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    cfg_path = enroll_runner(
        server_url="https://kanban.internal",
        enrollment_token="kb_rnr_enroll_secret_abc123",
        pool_slug="ci-pool",
        state_dir=state_dir,
        hostname="worker-node-1",
        client=client,
    )

    assert cfg_path.is_file()
    assert state_dir.is_dir()
    assert (state_dir.stat().st_mode & 0o777) == 0o700
    ca_pem = state_dir / "ca.pem"
    runner_toml = state_dir / "runner.toml"

    assert ca_pem.is_file()
    assert runner_toml.is_file()

    # Verify ca.pem has strict 0o600 permissions per KAN-64 Action 4
    mode = ca_pem.stat().st_mode & 0o777
    assert mode == 0o600

    # Verify runner.toml has strict 0o600 permissions
    toml_mode = runner_toml.stat().st_mode & 0o777
    assert toml_mode == 0o600

    # Verify runner.toml contains all required fields
    toml_text = runner_toml.read_text(encoding="utf-8")
    assert f'runner_id = "{runner_id_str}"' in toml_text
    assert 'server_url = "https://kanban.internal"' in toml_text
    assert "cert_path =" in toml_text
    assert "key_path =" in toml_text
    assert "ca_cert_path =" in toml_text
    assert "allowed_repos =" in toml_text

    # Verify runner.toml loads cleanly via load_runner_config
    cfg = load_runner_config(runner_toml)
    assert str(cfg.runner_id) == runner_id_str
    assert cfg.server_url == "https://kanban.internal"
    assert cfg.ca_cert_path == ca_pem


@pytest.mark.asyncio
async def test_daemon_signs_pop_challenge_automatically(tmp_path: Path) -> None:
    """Action 2: RemoteRunnerDaemon automatically signs challenge_hello and returns valid challenge_response."""
    runner_id = uuid.uuid4()
    ca_path, cert_path, key_path = _generate_test_certs(tmp_path, runner_id)

    cfg = RunnerConfig(
        server_url="https://kanban.internal",
        pool_slug="test-pool",
        cert_path=cert_path,
        key_path=key_path,
        ca_cert_path=ca_path,
        runner_id=runner_id,
    )

    daemon = RemoteRunnerDaemon(cfg)
    assert isinstance(daemon, RunnerDaemon)

    # Test direct challenge signing helper
    test_nonce = "abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789"
    sig_b64 = daemon._sign_challenge(test_nonce, runner_id)
    sig_bytes = base64.b64decode(sig_b64)

    # Verify signature with leaf certificate public key
    cert = x509.load_pem_x509_certificate(cert_path.read_bytes())
    cert_fp = cert.fingerprint(hashes.SHA256()).hex()
    expected_msg = f"kb-runner-pop-v1:{runner_id}:{test_nonce}:{cert_fp}".encode()

    pubkey = cert.public_key()
    assert isinstance(pubkey, ec.EllipticCurvePublicKey)
    pubkey.verify(sig_bytes, expected_msg, ec.ECDSA(hashes.SHA256()))


class MockWebSocketPeer:
    """Mock WebSocket peer simulating server challenge-response flow."""

    def __init__(self, runner_id: uuid.UUID) -> None:
        self.runner_id = runner_id
        self.sent_frames: list[str] = []
        self.step = 0
        self.verified_pop = False
        self._stopped = False

    async def send(self, data: str) -> None:
        self.sent_frames.append(data)

    def __aiter__(self) -> MockWebSocketPeer:
        return self

    async def __anext__(self) -> str:
        while not self._stopped:
            await asyncio.sleep(0.01)
        raise StopAsyncIteration

    async def close(self) -> None:
        self._stopped = True

    async def recv(self) -> str:
        self.step += 1
        if self.step == 1:
            # Server sends challenge_hello
            return json.dumps(
                {
                    "type": "challenge_hello",
                    "nonce": "11" * 32,
                    "runner_id": str(self.runner_id),
                }
            )
        if self.step == 2:
            # Server sends hello_ack
            return json.dumps({"type": "hello_ack", "heartbeat_interval_s": 15})
        # Sleep until cancelled
        await asyncio.sleep(100)
        return ""


@pytest.mark.asyncio
async def test_daemon_full_pop_handshake_flow(tmp_path: Path) -> None:
    """Action 2: RemoteRunnerDaemon handles challenge_hello seamlessly during _connect_and_run."""
    runner_id = uuid.uuid4()
    ca_path, cert_path, key_path = _generate_test_certs(tmp_path, runner_id)

    cfg = RunnerConfig(
        server_url="https://kanban.internal",
        pool_slug="test-pool",
        cert_path=cert_path,
        key_path=key_path,
        ca_cert_path=ca_path,
        runner_id=runner_id,
        heartbeat_interval_s=60.0,
    )

    mock_ws = MockWebSocketPeer(runner_id)

    class MockWsContext:
        async def __aenter__(self) -> MockWebSocketPeer:
            return mock_ws

        async def __aexit__(self, *args: object) -> None:
            pass

    daemon = RemoteRunnerDaemon(cfg, ws_connector=lambda *a, **k: MockWsContext())

    # Stop daemon after 100ms
    async def _stop_later() -> None:
        await asyncio.sleep(0.1)
        daemon.stop()
        await mock_ws.close()

    stop_task = asyncio.create_task(_stop_later())
    await daemon._connect_and_run(
        "wss://kanban.internal/api/v1/agent-runners/ws", daemon.build_ssl_context()
    )
    await stop_task

    # Inspect sent frames from daemon:
    # 1. HelloFrame
    # 2. ChallengeResponseFrame
    types = [json.loads(f).get("type") for f in mock_ws.sent_frames]
    assert "hello" in types
    assert "challenge_response" in types

    # Verify the challenge_response signature
    resp_frame = next(
        f for f in mock_ws.sent_frames if json.loads(f).get("type") == "challenge_response"
    )
    pop_resp = ChallengeResponseFrame.model_validate(json.loads(resp_frame))
    sig_bytes = base64.b64decode(pop_resp.signature_b64)

    cert = x509.load_pem_x509_certificate(cert_path.read_bytes())
    cert_fp = cert.fingerprint(hashes.SHA256()).hex()
    expected_msg = f"kb-runner-pop-v1:{runner_id}:{'11' * 32}:{cert_fp}".encode()

    pubkey = cert.public_key()
    assert isinstance(pubkey, ec.EllipticCurvePublicKey)
    pubkey.verify(sig_bytes, expected_msg, ec.ECDSA(hashes.SHA256()))


def test_default_runner_state_dir_env_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify KB_RUNNER_STATE_DIR env override returns configured path with 0o700 mode."""
    custom_dir = tmp_path / "custom-state"
    monkeypatch.setenv("KB_RUNNER_STATE_DIR", str(custom_dir))
    res = default_runner_state_dir()
    assert res == custom_dir
    assert res.is_dir()
    assert (res.stat().st_mode & 0o777) == 0o700


def test_default_runner_state_dir_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify default runner state directory for root user returns /var/lib/kanban-runner."""
    monkeypatch.delenv("KB_RUNNER_STATE_DIR", raising=False)
    monkeypatch.setattr(os, "geteuid", lambda: 0)
    mock_target = tmp_path / "var-lib-kanban-runner"
    orig_mkdir = Path.mkdir
    orig_chmod = os.chmod

    def mock_mkdir(
        self: Path,
        mode: int = 0o777,
        parents: bool = False,  # noqa: FBT001, FBT002
        exist_ok: bool = False,  # noqa: FBT001, FBT002
    ) -> None:
        target = mock_target if self == Path("/var/lib/kanban-runner") else self
        orig_mkdir(target, mode=mode, parents=parents, exist_ok=exist_ok)

    monkeypatch.setattr(Path, "mkdir", mock_mkdir)
    monkeypatch.setattr(
        os,
        "chmod",
        lambda p, m: orig_chmod(mock_target if Path(p) == Path("/var/lib/kanban-runner") else p, m),
    )
    res = default_runner_state_dir()
    assert res == Path("/var/lib/kanban-runner")
    assert mock_target.is_dir()
    assert (mock_target.stat().st_mode & 0o777) == 0o700


def test_default_runner_state_dir_user_with_and_without_xdg(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify default runner state directory for non-root user with and without XDG_DATA_HOME."""
    monkeypatch.delenv("KB_RUNNER_STATE_DIR", raising=False)
    monkeypatch.setattr(os, "geteuid", lambda: 1000)

    # 1. With XDG_DATA_HOME
    xdg_dir = tmp_path / "xdg-data"
    monkeypatch.setenv("XDG_DATA_HOME", str(xdg_dir))
    res_xdg = default_runner_state_dir()
    assert res_xdg == xdg_dir / "kanban-runner"
    assert res_xdg.is_dir()
    assert (res_xdg.stat().st_mode & 0o777) == 0o700

    # 2. Without XDG_DATA_HOME
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    fake_home = tmp_path / "fake-home"
    monkeypatch.setattr(Path, "home", lambda: fake_home)
    res_home = default_runner_state_dir()
    assert res_home == fake_home / ".local" / "share" / "kanban-runner"
    assert res_home.is_dir()
    assert (res_home.stat().st_mode & 0o777) == 0o700


def test_default_runner_config_path_variations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify auto-detection order for default runner configuration path."""
    state_dir = tmp_path / "state"
    monkeypatch.setenv("KB_RUNNER_STATE_DIR", str(state_dir))

    # 1. KB_RUNNER_CONFIG env override
    custom_cfg = tmp_path / "my-config.toml"
    monkeypatch.setenv("KB_RUNNER_CONFIG", str(custom_cfg))
    assert default_runner_config_path() == custom_cfg
    monkeypatch.delenv("KB_RUNNER_CONFIG")

    # 2. Default fallback when no config exists
    assert default_runner_config_path() == state_dir / "runner.toml"

    # 3. runner.toml in state_dir exists
    (state_dir / "runner.toml").write_text("server_url = 'test'")
    assert default_runner_config_path() == state_dir / "runner.toml"

    # 4. config.yaml in state_dir exists when runner.toml is absent
    (state_dir / "runner.toml").unlink()
    (state_dir / "config.yaml").write_text("server_url: test")
    assert default_runner_config_path() == state_dir / "config.yaml"

    # 5. /etc/kanban-runner fallback check
    (state_dir / "config.yaml").unlink()
    etc_runner = tmp_path / "etc-kanban-runner"
    etc_runner.mkdir(parents=True, exist_ok=True)
    etc_toml = etc_runner / "runner.toml"
    etc_toml.write_text("server_url = 'etc'")

    orig_is_file = Path.is_file

    def mock_is_file(self: Path) -> bool:
        if self == Path("/etc/kanban-runner/runner.toml"):
            return True
        return orig_is_file(self)

    monkeypatch.setattr(Path, "is_file", mock_is_file)
    assert default_runner_config_path() == Path("/etc/kanban-runner/runner.toml")


def test_cli_enroll_server_url_and_url_alias(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify CLI enroll accepts canonical --server-url and backwards-compatible --url alias."""
    state_dir = tmp_path / "cli-state"
    monkeypatch.setattr(sys, "stdin", io.StringIO("enroll_secret_123\n"))
    orig_client = httpx.Client

    def mock_client_factory(*_a: object, **_k: object) -> httpx.Client:
        return orig_client(
            transport=httpx.MockTransport(
                lambda _req: httpx.Response(
                    201,
                    json={
                        "runner_id": str(uuid.uuid4()),
                        "client_cert_pem": "---CERT---",
                        "ca_cert_pem": "---CA---",
                        "wss_url": "wss://test/ws",
                    },
                )
            )
        )

    monkeypatch.setattr(httpx, "Client", mock_client_factory)

    # 1. Using canonical --server-url
    rc = main(
        [
            "enroll",
            "--server-url",
            "https://kanban.internal",
            "--token-stdin",
            "--pool",
            "default",
            "--state-dir",
            str(state_dir),
        ]
    )
    assert rc == 0
    assert (state_dir / "runner.toml").is_file()

    # 2. Using alias --url
    state_dir_alias = tmp_path / "cli-state-alias"
    monkeypatch.setattr(sys, "stdin", io.StringIO("enroll_secret_456\n"))
    rc_alias = main(
        [
            "enroll",
            "--url",
            "https://kanban.internal",
            "--token-stdin",
            "--pool",
            "default",
            "--state-dir",
            str(state_dir_alias),
        ]
    )
    assert rc_alias == 0
    assert (state_dir_alias / "runner.toml").is_file()


def test_cli_enroll_and_run_defaults(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify CLI enroll and run subcommands default cleanly without explicit paths."""
    state_dir = tmp_path / "default-state"
    monkeypatch.setenv("KB_RUNNER_STATE_DIR", str(state_dir))
    monkeypatch.setattr(sys, "stdin", io.StringIO("enroll_secret_789\n"))
    orig_client = httpx.Client

    def mock_client_factory(*_a: object, **_k: object) -> httpx.Client:
        return orig_client(
            transport=httpx.MockTransport(
                lambda _req: httpx.Response(
                    201,
                    json={
                        "runner_id": str(uuid.uuid4()),
                        "client_cert_pem": "---CERT---",
                        "ca_cert_pem": "---CA---",
                        "wss_url": "wss://test/ws",
                    },
                )
            )
        )

    monkeypatch.setattr(httpx, "Client", mock_client_factory)

    # Enroll without --state-dir defaults to default_runner_state_dir()
    rc = main(
        [
            "enroll",
            "--server-url",
            "https://kanban.internal",
            "--token-stdin",
            "--pool",
            "default",
        ]
    )
    assert rc == 0
    assert (state_dir / "runner.toml").is_file()

    # Run without --config uses default_runner_config_path()
    mock_ran_path: list[Path] = []

    def mock_run_daemon(path: Path) -> int:
        mock_ran_path.append(path)
        return 0

    monkeypatch.setattr("agent.remote_runner.cli.run_daemon", mock_run_daemon)
    rc_run = main(["run"])
    assert rc_run == 0
    assert mock_ran_path == [state_dir / "runner.toml"]
