# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
# ruff: noqa: PTH101, PTH108, PTH110, PLR0917, F401, BLE001
"""Command-line interface for kanban-agent-runner: enroll & run subcommands (KB-P5-22b)."""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import os
import signal
import socket
import sys
import tempfile
from pathlib import Path
from typing import Any, Final

import httpx
import yaml
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from agent.remote_runner.config import (
    KeyPermissionsError,
    RunnerConfig,
    load_runner_config,
    validate_key_permissions,
)
from agent.remote_runner.daemon import (
    EXIT_CODE_REVOKED,
    RunnerDaemon,
    RunnerRevokedError,
)
from kanban.logging import configure_logging

__all__ = ["enroll_runner", "main", "run_daemon"]

_HTTP_CREATED: Final[int] = 201


def _generate_ecdsa_key_and_csr(hostname: str) -> tuple[bytes, str]:
    """Generate an ECDSA P-256 private key and PKCS#10 Certificate Signing Request."""
    private_key = ec.generate_private_key(ec.SECP256R1())
    key_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )

    csr = (
        x509.CertificateSigningRequestBuilder()
        .subject_name(
            x509.Name(
                [
                    x509.NameAttribute(NameOID.COMMON_NAME, hostname),
                    x509.NameAttribute(NameOID.ORGANIZATION_NAME, "👍kanban Remote Runner Node"),
                ]
            )
        )
        .sign(private_key, hashes.SHA256())
    )
    csr_pem = csr.public_bytes(serialization.Encoding.PEM).decode("ascii")
    return key_pem, csr_pem


def _write_secure_file(path: Path, data: bytes | str, mode: int = 0o600) -> None:
    """Atomically write file with strict POSIX permissions."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), prefix="tmp-key-", suffix=".tmp")
    try:
        os.chmod(tmp_path, mode)
        with os.fdopen(fd, "wb") as f:
            if isinstance(data, str):
                f.write(data.encode("utf-8"))
            else:
                f.write(data)
        Path(tmp_path).replace(path)
    except Exception:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise


def enroll_runner(  # noqa: PLR0913
    server_url: str,
    enrollment_token: str,
    pool_slug: str,
    state_dir: Path,
    hostname: str | None = None,
    ca_cert_path: Path | None = None,
    client: httpx.Client | None = None,
) -> Path:
    """Execute single-use enrollment exchange and write certificates to state directory."""
    token = enrollment_token.strip()
    if not token:
        msg = "Enrollment token is empty"
        raise ValueError(msg)

    host = hostname or socket.gethostname()
    key_pem, csr_pem = _generate_ecdsa_key_and_csr(host)

    state_dir.mkdir(parents=True, exist_ok=True)
    key_path = state_dir / "client.key"
    _write_secure_file(key_path, key_pem, mode=0o600)

    # Submit CSR to enrollment endpoint
    base_url = server_url.rstrip("/")
    enroll_url = f"{base_url}/api/v1/agent-runners/enroll"

    payload = {
        "enrollment_token": token,
        "csr_pem": csr_pem,
        "hostname": host,
        "capabilities": {"os": sys.platform, "python": sys.version.split()[0]},
    }

    verify: Any = str(ca_cert_path) if ca_cert_path and ca_cert_path.exists() else True
    if client is not None:
        resp = client.post(enroll_url, json=payload)
    else:
        with httpx.Client(verify=verify, timeout=30.0) as http_client:
            resp = http_client.post(enroll_url, json=payload)

    if resp.status_code != _HTTP_CREATED:
        msg = f"Enrollment failed with status {resp.status_code}: {resp.text}"
        raise RuntimeError(msg)

    data = resp.json()
    client_cert_pem = data["client_cert_pem"]
    ca_cert_pem = data["ca_cert_pem"]
    wss_url = data["wss_url"]

    cert_path = state_dir / "client.crt"
    _write_secure_file(cert_path, client_cert_pem, mode=0o644)

    ca_path = state_dir / "ca.crt"
    _write_secure_file(ca_path, ca_cert_pem, mode=0o644)

    # Generate initial config.yaml
    config_dict = {
        "server_url": server_url,
        "pool_slug": pool_slug,
        "client_cert_path": str(cert_path),
        "client_key_path": str(key_path),
        "ca_cert_path": str(ca_path),
        "wss_url": wss_url,
        "state_dir": str(state_dir),
        "max_concurrency": 1,
        "capabilities": {},
        "repo_mounts": {},
    }
    config_path = state_dir / "config.yaml"
    _write_secure_file(config_path, yaml.safe_dump(config_dict), mode=0o600)
    return config_path


def run_daemon(config_path: Path) -> int:
    """Run RunnerDaemon from config file, handling graceful shutdown."""
    config = load_runner_config(config_path)
    validate_key_permissions(config.client_key_path)

    daemon = RunnerDaemon(config)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    def _sig_handler() -> None:
        daemon.stop()

    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, _sig_handler)

    try:
        loop.run_until_complete(daemon.run_forever())
    except RunnerRevokedError:
        return EXIT_CODE_REVOKED
    except KeyboardInterrupt:
        daemon.stop()
        return 0
    else:
        return 0
    finally:
        loop.close()


def main(argv: list[str] | None = None) -> int:
    """Execute the main CLI entrypoint for kanban-agent-runner."""
    configure_logging()
    raw_args = list(argv if argv is not None else sys.argv[1:])

    # Security check: reject passing --token on CLI arguments to protect /proc/cmdline
    for arg in raw_args:
        if arg == "--token" or arg.startswith("--token="):
            sys.stderr.write(
                "ERROR: Passing --token on CLI arguments is rejected for security. "
                "Use --token-stdin to provide single-use enrollment tokens.\n"
            )
            return 2

    parser = argparse.ArgumentParser(
        prog="kanban-agent-runner",
        description="Outbound mTLS WSS agent runner daemon for 👍kanban",
    )
    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    # Enroll subcommand
    enroll_parser = subparsers.add_parser("enroll", help="Enroll runner with server using token")
    enroll_parser.add_argument(
        "--server-url", required=True, help="Base HTTPS URL of 👍kanban server"
    )
    enroll_parser.add_argument(
        "--token-stdin",
        action="store_true",
        required=True,
        help="Read single-use enrollment token from stdin",
    )
    enroll_parser.add_argument("--pool", required=True, dest="pool_slug", help="Pool slug")
    enroll_parser.add_argument(
        "--state-dir",
        type=Path,
        default=Path("/var/lib/kanban-runner"),
        help="Directory to store certificates and config",
    )
    enroll_parser.add_argument("--hostname", help="Node hostname for CSR common name")
    enroll_parser.add_argument(
        "--ca-cert", type=Path, dest="ca_cert_path", help="Server CA bundle path"
    )

    # Run subcommand
    run_parser = subparsers.add_parser("run", help="Start agent runner daemon")
    run_parser.add_argument(
        "--config",
        type=Path,
        default=Path("/etc/kanban-runner/config.yaml"),
        help="Path to runner config.yaml",
    )

    args = parser.parse_args(raw_args)

    if args.subcommand == "enroll":
        token = sys.stdin.read().strip()
        try:
            cfg_path = enroll_runner(
                server_url=args.server_url,
                enrollment_token=token,
                pool_slug=args.pool_slug,
                state_dir=args.state_dir,
                hostname=args.hostname,
                ca_cert_path=args.ca_cert_path,
            )
        except Exception as exc:
            sys.stderr.write(f"Enrollment error: {exc}\n")
            return 1
        else:
            sys.stdout.write(f"Enrollment successful. Config written to {cfg_path}\n")
            return 0

    if args.subcommand == "run":
        try:
            return run_daemon(args.config)
        except KeyPermissionsError as exc:
            sys.stderr.write(f"Security error: {exc}\n")
        except Exception as exc:
            sys.stderr.write(f"Runner error: {exc}\n")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
