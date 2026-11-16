"""Verification suite for public GitHub Actions CI workflows and runner routing (KANBA-181).

Verifies:
1. All public GitHub workflow definitions parse cleanly via PyYAML and target GitHub-hosted
   `ubuntu-latest` runners (never self-hosted or internal runners).
2. Dash log upload scripts fail open and cleanly exit 0 when tokens or endpoints are missing.
3. Zero leakage of RFC 1918 private network addresses in public workflow files.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from typing import Any, cast

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
GITHUB_DIR = REPO_ROOT / ".github"
WORKFLOWS_DIR = GITHUB_DIR / "workflows"
UPLOAD_DASH_SCRIPT = REPO_ROOT / "scripts" / "ci" / "upload_dash_log.sh"

RFC_1918_PATTERN = re.compile(
    r"\b(?:10\.\d{1,3}\.\d{1,3}\.\d{1,3}|"
    r"172\.(?:1[6-9]|2\d|3[0-1])\.\d{1,3}\.\d{1,3}|"
    r"192\.168\.\d{1,3}\.\d{1,3})\b"
)
USES_PINNED_PATTERN = re.compile(r"^[^@]+@[0-9a-f]{40}$")
DASH_NOTICE = "Notice: DASH_TOKEN or DASH_ENDPOINT missing; skipping Dash upload"


def _load_workflow(path: Path) -> dict[str, Any]:
    """Parse a workflow YAML file using safe_load."""
    content = path.read_text(encoding="utf-8")
    loaded = yaml.safe_load(content)
    assert isinstance(loaded, dict), f"Workflow {path} did not parse into a dictionary"
    return cast("dict[str, Any]", loaded)


def test_workflow_syntax_and_runner_targets() -> None:
    """Verifies that all .github/workflows/*.yml parse cleanly and target ubuntu-latest."""
    workflow_files = list(WORKFLOWS_DIR.glob("*.yml")) + list(WORKFLOWS_DIR.glob("*.yaml"))
    assert workflow_files, "No GitHub workflow files found in .github/workflows/"

    for wf_path in workflow_files:
        workflow = _load_workflow(wf_path)
        assert "jobs" in workflow, f"{wf_path.name} has no jobs definition"
        jobs = cast("dict[str, dict[str, Any]]", workflow["jobs"])
        assert jobs, f"{wf_path.name} contains an empty jobs map"

        for job_id, job in jobs.items():
            runs_on = job.get("runs-on")
            assert runs_on is not None, f"Job {job_id} in {wf_path.name} is missing runs-on"
            assert runs_on == "ubuntu-latest", (
                f"Job {job_id} in {wf_path.name} must run on ubuntu-latest for public CI, "
                f"got: {runs_on}"
            )

            # Security: verify timeout is bounded
            timeout = job.get("timeout-minutes")
            assert timeout is not None, f"Job {job_id} in {wf_path.name} missing timeout-minutes"
            assert 0 < timeout <= 20, (
                f"Job {job_id} in {wf_path.name} must have timeout-minutes <= 20"
            )

            # Security: all actions must be pinned to full 40-hex commit SHA
            for step in job.get("steps", []):
                uses = step.get("uses")
                if uses:
                    step_name = step.get("name", "unnamed")
                    assert USES_PINNED_PATTERN.match(uses), (
                        f"Step '{step_name}' in {job_id} uses unpinned action: {uses}"
                    )


@pytest.mark.parametrize(
    ("env_overrides", "expected_notice"),
    [
        ({"DASH_TOKEN": ""}, DASH_NOTICE),
        ({"DASH_ENDPOINT": ""}, DASH_NOTICE),
        (
            {"DASH_TOKEN": "", "DASH_ENDPOINT": ""},
            DASH_NOTICE,
        ),
    ],
)
def test_dash_upload_graceful_fallback(
    env_overrides: dict[str, str],
    expected_notice: str,
    tmp_path: Path,
) -> None:
    """Executes upload_dash_log.sh with empty or missing token/endpoint and asserts exit code 0."""
    assert UPLOAD_DASH_SCRIPT.is_file(), f"Script not found at {UPLOAD_DASH_SCRIPT}"

    env = dict(os.environ)
    env.update(env_overrides)
    env["CI_LOG_DIR"] = str(tmp_path)

    result = subprocess.run(
        ["bash", str(UPLOAD_DASH_SCRIPT), "lint-and-syntax"],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, (
        f"upload_dash_log.sh must exit 0 on missing/empty tokens, got {result.returncode}.\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
    assert expected_notice in result.stdout, (
        f"Expected notice '{expected_notice}' in stdout, got:\n{result.stdout}"
    )


def test_zero_private_network_leaks() -> None:
    """Scans all files under .github/ and asserts zero occurrences of RFC 1918 private IPs."""
    assert GITHUB_DIR.is_dir(), f".github directory not found at {GITHUB_DIR}"

    scanned_files = [p for p in GITHUB_DIR.rglob("*") if p.is_file()]
    assert scanned_files, f"No files found under {GITHUB_DIR} to scan"

    leaks: list[str] = []
    for file_path in scanned_files:
        try:
            content = file_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue

        matches = RFC_1918_PATTERN.findall(content)
        if matches:
            leaks.append(f"{file_path.relative_to(REPO_ROOT)}: {matches}")

    msg = "RFC 1918 private network addresses detected in .github/:\n" + "\n".join(leaks)
    assert not leaks, msg


def test_github_workflow_secrets_isolation() -> None:
    """Ensures public GitHub workflows do not reference private runner secrets or Dash tokens."""
    for wf_path in WORKFLOWS_DIR.glob("*.yml"):
        content = wf_path.read_text(encoding="utf-8")
        assert "inferrence1" not in content, f"Internal runner found in {wf_path.name}"
        assert "DASH_TOKEN" not in content, f"DASH_TOKEN found in {wf_path.name}"
        assert "dash.hackedyour.info" not in content, f"Internal Dash URL found in {wf_path.name}"
        assert "upload_dash_log.sh" not in content, f"Dash upload script found in {wf_path.name}"
