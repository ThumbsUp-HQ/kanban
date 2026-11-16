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
"""Standalone container warm boot SLA benchmark (< 3.0s) (KB-P6-04, S2.2).

Measures 3 consecutive warm container boots from `docker start` monotonic timestamp
to HTTP 200 on GET http://127.0.0.1:18080/, asserting max_warm_boot_s < 3.0s.
"""

# ruff: noqa: T201, S310
from __future__ import annotations

import json
import os
import statistics
import subprocess
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

import pytest

HOST_PORT = int(os.environ.get("KB_PERF_CONTAINER_PORT", "18080"))
TARGET_URL = f"http://127.0.0.1:{HOST_PORT}/"
IMAGE_TAG = os.environ.get("KB_CONTAINER_IMAGE", "kanban:latest")


def _wait_for_http_200(url: str, deadline: float, poll_interval: float = 0.01) -> bool:
    """Poll URL until HTTP 200 or deadline."""
    while time.monotonic() < deadline:
        try:
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=0.5) as resp:
                if resp.status == 200:
                    return True
        except (OSError, urllib.error.URLError):
            time.sleep(poll_interval)
    return False


@pytest.mark.perf
@pytest.mark.container
@pytest.mark.enable_socket
def test_perf_standalone_warm_boot_sla() -> None:
    """Measure 3 warm boots of standalone container, asserting max < 3.0s."""
    run_id = uuid.uuid4().hex[:6]
    container_name = f"kanban-perf-warm-{run_id}"
    volume_name = f"kanban-perf-vol-{run_id}"

    # Ensure clean initial state
    subprocess.run(["docker", "rm", "-f", container_name], capture_output=True, check=False)
    subprocess.run(["docker", "volume", "rm", "-f", volume_name], capture_output=True, check=False)
    subprocess.run(["docker", "volume", "create", volume_name], capture_output=True, check=True)

    try:
        # 1. Cold run: initialize DB cluster & migrations on volume
        cold_cmd = [
            "docker",
            "run",
            "-d",
            "--name",
            container_name,
            "-p",
            f"{HOST_PORT}:8080",
            "-v",
            f"{volume_name}:/var/lib/kanban/data",
            IMAGE_TAG,
        ]
        cold_proc = subprocess.run(cold_cmd, capture_output=True, text=True, check=True)
        assert cold_proc.returncode == 0

        cold_ready = _wait_for_http_200(
            TARGET_URL, deadline=time.monotonic() + 30.0, poll_interval=0.2
        )
        assert cold_ready, "Cold container failed to reach HTTP 200 within 30s"

        # Stop container cleanly
        subprocess.run(
            ["docker", "stop", "-t", "5", container_name], capture_output=True, check=True
        )

        # 2. Warm boots: 3 iterations
        warm_times_s: list[float] = []
        for iteration in range(3):
            t_start = time.monotonic()
            start_proc = subprocess.Popen(
                ["docker", "start", container_name],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

            ready = _wait_for_http_200(TARGET_URL, deadline=t_start + 10.0, poll_interval=0.005)
            elapsed_s = time.monotonic() - t_start
            start_proc.wait(timeout=5.0)
            assert start_proc.returncode == 0
            assert ready, f"Warm boot {iteration + 1} failed to reach HTTP 200 within 10s"

            warm_times_s.append(elapsed_s)
            print(f"[WARM BOOT {iteration + 1}]: {elapsed_s:.3f}s")

            if iteration < 2:
                subprocess.run(
                    ["docker", "stop", "-t", "5", container_name],
                    capture_output=True,
                    check=True,
                )

        min_s = min(warm_times_s)
        max_s = max(warm_times_s)
        mean_s = statistics.mean(warm_times_s)
        median_s = statistics.median(warm_times_s)

        report_payload = {
            "benchmark": "standalone_warm_boot",
            "unit": "s",
            "threshold_s": 3.0,
            "samples": len(warm_times_s),
            "iterations_s": [round(t, 3) for t in warm_times_s],
            "min_s": round(min_s, 3),
            "mean_s": round(mean_s, 3),
            "p50_s": round(median_s, 3),
            "max_s": round(max_s, 3),
            "passed": max_s < 3.0,
        }

        print(
            f"\n[STANDALONE WARM BOOT SLA]: max: {max_s:.3f}s (ceiling: < 3.0s), "
            f"min: {min_s:.3f}s, mean: {mean_s:.3f}s. Result: {'PASS' if max_s < 3.0 else 'FAIL'}"
        )

        out_file = Path("docs/qa/KANBA-151/perf-standalone-boot.json")
        out_file.parent.mkdir(parents=True, exist_ok=True)
        out_file.write_text(json.dumps(report_payload, indent=2), encoding="utf-8")

        assert max_s < 3.0, f"Max warm boot time {max_s:.3f}s breached 3.0s SLA ceiling!"

    finally:
        subprocess.run(["docker", "rm", "-f", container_name], capture_output=True, check=False)
        subprocess.run(
            ["docker", "volume", "rm", "-f", volume_name], capture_output=True, check=False
        )
