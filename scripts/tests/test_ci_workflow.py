"""Structural and security tests for CI workflows (KB-P0-06 / KANBA-28).

The project uses a dual-workflow topology:
1. Forgejo CI (``.forgejo/workflows/ci.yml``): runs the complete gate suite on the
   self-hosted runner ``inferrence1`` with Dash CI reporting and local postgres fixtures.
2. GitHub CI (``.github/workflows/ci.yml``): runs lightweight, neutered smoke checks on
   ``ubuntu-latest`` for public GitHub pushes and pull requests without private runner
   or internal Dash endpoint dependencies.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, cast

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
GITHUB_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"
FORGEJO_WORKFLOW = REPO_ROOT / ".forgejo" / "workflows" / "ci.yml"
FORGEJO_JOB_IDS = [
    "lint-type",
    "python-tests",
    "stride-security-gate",
    "web-tests",
    "license-gate",
    "docker-build",
    "perf-budgets",
    "docker-push",
]
GITHUB_JOB_IDS = [
    "lint-and-syntax",
    "web-smoke",
    "docker-smoke",
    "docker-publish",
]
USES_PATTERN = re.compile(r"^[^@]+@[0-9a-f]{40}$")
ALLOWED_SECRETS = {"DASH_TOKEN", "DOCKERHUB_USERNAME", "DOCKERHUB_TOKEN"}
DOCKERHUB_SECRETS = {"DOCKERHUB_USERNAME", "DOCKERHUB_TOKEN"}


def _load(path: Path) -> dict[str, Any]:
    """Parse a workflow with ``safe_load`` only (never ``yaml.load``)."""
    return cast("dict[str, Any]", yaml.safe_load(path.read_text(encoding="utf-8")))


@pytest.fixture(scope="module")
def forgejo_workflow() -> dict[str, Any]:
    """Return the parsed Forgejo workflow."""
    return _load(FORGEJO_WORKFLOW)


@pytest.fixture(scope="module")
def forgejo_jobs(forgejo_workflow: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Return the Forgejo job mapping."""
    return cast("dict[str, dict[str, Any]]", forgejo_workflow["jobs"])


@pytest.fixture(scope="module")
def github_workflow() -> dict[str, Any]:
    """Return the parsed GitHub workflow."""
    return _load(GITHUB_WORKFLOW)


@pytest.fixture(scope="module")
def github_jobs(github_workflow: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Return the GitHub job mapping."""
    return cast("dict[str, dict[str, Any]]", github_workflow["jobs"])


def _run_text(job: dict[str, Any]) -> str:
    return "\n".join(str(s.get("run", "")) for s in job["steps"])


# --- Forgejo (Self-Hosted Runner) Tests ---


def test_forgejo_jobs_exist_on_inferrence1(forgejo_jobs: dict[str, dict[str, Any]]) -> None:
    """Positive: all local pipeline jobs run on the self-hosted inferrence1 runner."""
    assert list(forgejo_jobs) == FORGEJO_JOB_IDS
    for job in forgejo_jobs.values():
        assert job["runs-on"] == ["inferrence1"]


def test_forgejo_permissions_are_read_only(forgejo_workflow: dict[str, Any]) -> None:
    """Security: Forgejo top-level token permissions are contents: read only."""
    assert forgejo_workflow["permissions"] == {"contents": "read"}


def test_forgejo_every_job_has_bounded_timeout(forgejo_jobs: dict[str, dict[str, Any]]) -> None:
    """Boundary: every Forgejo job has timeout-minutes <= 20."""
    for name, job in forgejo_jobs.items():
        assert 0 < job["timeout-minutes"] <= 20, name


def test_forgejo_concurrency_cancels_superseded_runs(forgejo_workflow: dict[str, Any]) -> None:
    """Positive: superseded runs on the same ref are cancelled."""
    assert forgejo_workflow["concurrency"] == {
        "group": "ci-${{ github.ref }}",
        "cancel-in-progress": True,
    }


def test_forgejo_triggers_exclude_pull_request_target(forgejo_workflow: dict[str, Any]) -> None:
    """Security: no pull_request_target (it would expose secrets to forks)."""
    raw = cast("dict[Any, Any]", forgejo_workflow)
    triggers = raw.get("on", raw.get(True))
    assert triggers is not None
    assert "pull_request_target" not in triggers
    assert "push" in triggers
    assert "pull_request" in triggers


def test_forgejo_every_uses_is_pinned_to_a_full_commit_sha(
    forgejo_jobs: dict[str, dict[str, Any]],
) -> None:
    """Security: every `uses:` is owner/repo@<40 hex> with a trailing version comment."""
    text = FORGEJO_WORKFLOW.read_text(encoding="utf-8")
    for job in forgejo_jobs.values():
        for step in job["steps"]:
            if "uses" in step:
                assert USES_PATTERN.match(step["uses"]), step["uses"]
    for line in text.splitlines():
        if "uses:" in line:
            assert re.search(r"@[0-9a-f]{40} # v\d+\.\d+\.\d+$", line.strip()), line


def test_forgejo_secrets_are_scoped_to_their_jobs(forgejo_jobs: dict[str, dict[str, Any]]) -> None:
    """Security: Docker Hub secrets exist only in docker-push; none appear in `run:` bodies."""
    text = FORGEJO_WORKFLOW.read_text(encoding="utf-8")
    refs = {part.split("}}")[0].strip() for part in text.split("secrets.")[1:]}
    assert refs == ALLOWED_SECRETS
    for name, job in forgejo_jobs.items():
        job_text = yaml.safe_dump(job)
        for secret in DOCKERHUB_SECRETS:
            assert (secret in job_text) == (name == "docker-push"), (name, secret)
        for step in job["steps"]:
            assert "secrets." not in str(step.get("run", "")), (name, step["name"])


def test_forgejo_docker_push_gating_and_dependencies(
    forgejo_jobs: dict[str, dict[str, Any]],
) -> None:
    """Security: docker-push runs only for main pushes, after all seven other jobs succeed."""
    job = forgejo_jobs["docker-push"]
    assert job["needs"] == [
        "lint-type",
        "python-tests",
        "stride-security-gate",
        "web-tests",
        "license-gate",
        "docker-build",
        "perf-budgets",
    ]
    assert job["if"] == "github.ref == 'refs/heads/main' && github.event_name == 'push'"
    uses = [s["uses"].split("@")[0] for s in job["steps"] if "uses" in s]
    assert uses == [
        "actions/checkout",
        "docker/setup-buildx-action",
        "docker/login-action",
        "docker/build-push-action",
        "actions/upload-artifact",
    ]
    push = next(s for s in job["steps"] if s.get("name") == "Build and push Docker image")
    assert push["with"]["push"] is True
    assert push["with"]["tags"] == "${{ secrets.DOCKERHUB_USERNAME }}/thumbs-up-kanban:latest"


def test_forgejo_last_step_uploads_logs_artifact_always(
    forgejo_jobs: dict[str, dict[str, Any]],
) -> None:
    """Positive: each Forgejo job ends with an always() upload-artifact of ci-logs/."""
    for name, job in forgejo_jobs.items():
        last = job["steps"][-1]
        assert last["if"] == "always()", name
        assert last["uses"].startswith("actions/upload-artifact@"), name
        assert last["with"]["name"] == "ci-logs-${{ github.job }}", name
        assert last["with"]["path"] == "ci-logs/", name
        assert last["with"]["retention-days"] == 14, name
        assert last["with"]["if-no-files-found"] == "error", name


def test_forgejo_dash_upload_runs_always_before_artifact(
    forgejo_jobs: dict[str, dict[str, Any]],
) -> None:
    """Positive: each Forgejo job uploads to Dash with always() before the artifact."""
    for name, job in forgejo_jobs.items():
        dash = next(s for s in job["steps"] if s.get("name") == "Upload logs to Dash")
        assert dash["if"] == "always()", name
        assert dash["env"] == {"DASH_TOKEN": "${{ secrets.DASH_TOKEN }}"}, name
        assert dash["run"] == f"scripts/ci/upload_dash_log.sh {name}", name
        assert job["steps"].index(dash) < len(job["steps"]) - 1


def test_forgejo_python_tests_enforce_coverage_threshold(
    forgejo_jobs: dict[str, dict[str, Any]],
) -> None:
    """Boundary: python-tests fails below 95% branch coverage and runs serially on shared DB."""
    run = _run_text(forgejo_jobs["python-tests"])
    assert "--cov-fail-under=95" in run
    assert "--cov-branch" in run
    assert "make testdb-up" in run
    assert "make testdb-down" in run
    assert "-n auto" not in run


def test_forgejo_testdb_teardown_always_runs(forgejo_jobs: dict[str, dict[str, Any]]) -> None:
    """Positive: DB teardown runs on failure too."""
    step = next(
        s for s in forgejo_jobs["python-tests"]["steps"] if s.get("name") == "Stop test database"
    )
    assert step["if"] == "always()"


# --- GitHub (Public Neutered Runner) Tests ---


def test_github_jobs_use_ubuntu_latest(github_jobs: dict[str, dict[str, Any]]) -> None:
    """Positive: public GitHub jobs run on standard ubuntu-latest, never inferrence1."""
    assert list(github_jobs) == GITHUB_JOB_IDS
    for name, job in github_jobs.items():
        assert job["runs-on"] == "ubuntu-latest", f"{name} must run on ubuntu-latest"


def test_github_workflow_has_zero_dash_or_inferrence_dependencies() -> None:
    """Security: GitHub workflow must not leak or reference Dash endpoints or private runners."""
    text = GITHUB_WORKFLOW.read_text(encoding="utf-8")
    assert "inferrence1" not in text
    assert "DASH_TOKEN" not in text
    assert "dash.hackedyour.info" not in text
    assert "upload_dash_log.sh" not in text


def test_github_permissions_are_read_only(github_workflow: dict[str, Any]) -> None:
    """Security: GitHub top-level token permissions are contents: read only."""
    assert github_workflow["permissions"] == {"contents": "read"}


def test_github_every_job_has_bounded_timeout(github_jobs: dict[str, dict[str, Any]]) -> None:
    """Boundary: every GitHub job has timeout-minutes <= 20."""
    for name, job in github_jobs.items():
        assert 0 < job["timeout-minutes"] <= 20, name


def test_github_concurrency_cancels_superseded_runs(github_workflow: dict[str, Any]) -> None:
    """Positive: GitHub workflow cancels superseded runs on the same ref."""
    assert github_workflow["concurrency"] == {
        "group": "ci-${{ github.ref }}",
        "cancel-in-progress": True,
    }


def test_github_every_uses_is_pinned_to_a_full_commit_sha(
    github_jobs: dict[str, dict[str, Any]],
) -> None:
    """Security: every `uses:` in GitHub workflow is owner/repo@<40 hex> with version comment."""
    text = GITHUB_WORKFLOW.read_text(encoding="utf-8")
    for job in github_jobs.values():
        for step in job["steps"]:
            if "uses" in step:
                assert USES_PATTERN.match(step["uses"]), step["uses"]
    for line in text.splitlines():
        if "uses:" in line:
            assert re.search(r"@[0-9a-f]{40} # v\d+\.\d+\.\d+$", line.strip()), line


def test_github_docker_publish_is_non_blocking_without_secrets(
    github_jobs: dict[str, dict[str, Any]],
) -> None:
    """Positive: GitHub docker-publish checks credentials and skips cleanly if unconfigured."""
    job = github_jobs["docker-publish"]
    assert job["needs"] == ["lint-and-syntax", "web-smoke", "docker-smoke"]
    check_step = next(s for s in job["steps"] if s.get("id") == "check-auth")
    assert "configured=true" in check_step["run"]
    assert "configured=false" in check_step["run"]


def test_ci_doc_has_required_sections() -> None:
    """Positive: docs/CI.md documents jobs, log reading and Dash verification."""
    text = (REPO_ROOT / "docs" / "CI.md").read_text(encoding="utf-8")
    for heading in ("## Jobs", "## Reading Logs", "## Dash Verification"):
        assert heading in text
    assert "https://dash.hackedyour.info/llms.txt" in text
