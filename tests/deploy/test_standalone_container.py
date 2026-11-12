"""Container integration smoke tests for standalone single-container deployment.

Requires Docker daemon and pre-built kanban:latest image.
"""

from __future__ import annotations

import subprocess
import time
import urllib.error
import urllib.request
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import Generator

CONTAINER_NAME = "kanban-smoke-test"
HOST_PORT = 18080
TARGET_URL = f"http://127.0.0.1:{HOST_PORT}/"


@pytest.fixture
def standalone_container() -> Generator[str, None, None]:
    """Fixture to manage the lifecycle of the standalone smoke container."""
    # Ensure no leftover container from previous runs
    subprocess.run(
        ["docker", "rm", "-f", CONTAINER_NAME],
        capture_output=True,
        check=False,
    )

    # Run container
    run_cmd = [
        "docker",
        "run",
        "-d",
        "--name",
        CONTAINER_NAME,
        "-p",
        f"{HOST_PORT}:8080",
        "kanban:latest",
    ]
    proc = subprocess.run(run_cmd, capture_output=True, text=True, check=True)
    container_id = proc.stdout.strip()

    try:
        yield container_id
    finally:
        subprocess.run(
            ["docker", "rm", "-f", CONTAINER_NAME],
            capture_output=True,
            check=False,
        )


@pytest.mark.container
@pytest.mark.enable_socket
@pytest.mark.usefixtures("standalone_container")
def test_standalone_container_smoke() -> None:
    """Validate that standalone container boots within 10s and has zero TCP DB listeners."""
    # 1. Wait for HTTP 200 within 10s
    deadline = time.monotonic() + 10.0
    status_code = None

    while time.monotonic() < deadline:
        try:
            req = urllib.request.Request(TARGET_URL)
            with urllib.request.urlopen(req, timeout=1.0) as resp:  # noqa: S310
                status_code = resp.status
                if status_code == 200:
                    break
        except (OSError, urllib.error.URLError):
            time.sleep(0.3)

    assert status_code == 200, f"Expected HTTP 200 within 10s, got {status_code}"

    # 2. Check /proc/net/tcp and /proc/net/tcp6: zero listeners on port 5432 (hex 1538)
    net_proc = subprocess.run(
        ["docker", "exec", CONTAINER_NAME, "cat", "/proc/net/tcp", "/proc/net/tcp6"],
        capture_output=True,
        text=True,
        check=True,
    )
    tcp_output = net_proc.stdout

    # Check for listening sockets on 5432 (port 5432 in hex is 1538; state 0A is LISTEN)
    for line in tcp_output.splitlines():
        parts = line.split()
        if len(parts) >= 4 and parts[3] == "0A":
            local_address = parts[1]
            assert ":1538" not in local_address, f"Found TCP DB listener: {line}"

    # 3. Check process UIDs: uvicorn as 65532, postgres as postgres UID (non-root, non-65532)
    ps_proc = subprocess.run(
        ["docker", "exec", CONTAINER_NAME, "ps", "-eo", "uid,comm"],
        capture_output=True,
        text=True,
        check=True,
    )
    ps_output = ps_proc.stdout

    uvicorn_found = False
    postgres_found = False

    for line in ps_output.splitlines():
        parts = line.split()
        if len(parts) >= 2:
            uid, comm = parts[0], parts[1]
            if "uvicorn" in comm:
                assert uid == "65532", f"Uvicorn must run as UID 65532, got {uid}"
                uvicorn_found = True
            elif "postgres" in comm or "postmaster" in comm:
                assert uid not in ("0", "65532"), (
                    f"PostgreSQL must not run as root or kanban: {uid}"
                )
                postgres_found = True

    assert uvicorn_found, "Uvicorn process was not found in container"
    assert postgres_found, "PostgreSQL process was not found in container"

    # 4. Graceful stop within 15s and verification of shutdown order
    stop_start = time.monotonic()
    subprocess.run(
        ["docker", "stop", "-t", "15", CONTAINER_NAME],
        capture_output=True,
        check=True,
        timeout=20.0,
    )
    stop_duration = time.monotonic() - stop_start
    assert stop_duration <= 15.0, f"docker stop took {stop_duration}s (> 15s)"

    # 5. Check logs show Uvicorn stopped before PostgreSQL
    log_proc = subprocess.run(
        ["docker", "logs", CONTAINER_NAME],
        capture_output=True,
        text=True,
        check=True,
    )
    logs = log_proc.stdout + log_proc.stderr

    assert "shutdown: sending SIGTERM to uvicorn" in logs
    assert "pg_stop: stopping PostgreSQL" in logs
    uvicorn_stop_idx = logs.find("shutdown: sending SIGTERM to uvicorn")
    pg_stop_idx = logs.find("pg_stop: stopping PostgreSQL")
    assert uvicorn_stop_idx < pg_stop_idx, "Uvicorn must stop before PostgreSQL"
