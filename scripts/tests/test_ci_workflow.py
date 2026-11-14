"""Structural and security tests for the CI workflow (KB-P0-06 / KANBA-28).

The project CI runs on the Forgejo runner ``inferrence1`` as six jobs. These tests pin the
invariants that keep failed runs diagnosable and the pipeline hardened: SHA-pinned actions,
least-privilege permissions, bounded jobs, and always-run log upload as the final step.
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
JOB_IDS = [
    "lint-type",
    "python-tests",
    "web-tests",
    "license-gate",
    "docker-build",
    "docker-push",
]
USES_PATTERN = re.compile(r"^[^@]+@[0-9a-f]{40}$")
ALLOWED_SECRETS = {"DASH_TOKEN", "DOCKERHUB_USERNAME", "DOCKERHUB_TOKEN"}
DOCKERHUB_SECRETS = {"DOCKERHUB_USERNAME", "DOCKERHUB_TOKEN"}


def _load(path: Path) -> dict[str, Any]:
    """Parse a workflow with ``safe_load`` only (never ``yaml.load``)."""
    return cast("dict[str, Any]", yaml.safe_load(path.read_text(encoding="utf-8")))


@pytest.fixture(scope="module")
def workflow() -> dict[str, Any]:
    """Return the parsed Forgejo workflow."""
    return _load(FORGEJO_WORKFLOW)


@pytest.fixture(scope="module")
def jobs(workflow: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Return the job mapping."""
    return cast("dict[str, dict[str, Any]]", workflow["jobs"])


def _run_text(job: dict[str, Any]) -> str:
    return "\n".join(str(s.get("run", "")) for s in job["steps"])


def test_workflow_copies_are_identical() -> None:
    """Positive: the GitHub and Forgejo workflow files must not drift."""
    assert GITHUB_WORKFLOW.read_bytes() == FORGEJO_WORKFLOW.read_bytes()


def test_six_jobs_exist_on_inferrence1(jobs: dict[str, dict[str, Any]]) -> None:
    """Positive: the five ticket jobs plus docker-push, all on the project runner."""
    assert list(jobs) == JOB_IDS
    for job in jobs.values():
        assert job["runs-on"] == ["inferrence1"]


def test_permissions_are_read_only(workflow: dict[str, Any]) -> None:
    """Security: top-level token permissions are contents: read only."""
    assert workflow["permissions"] == {"contents": "read"}


def test_every_job_has_bounded_timeout(jobs: dict[str, dict[str, Any]]) -> None:
    """Boundary: every job has timeout-minutes <= 20."""
    for name, job in jobs.items():
        assert 0 < job["timeout-minutes"] <= 20, name


def test_concurrency_cancels_superseded_runs(workflow: dict[str, Any]) -> None:
    """Positive: superseded runs on the same ref are cancelled."""
    assert workflow["concurrency"] == {
        "group": "ci-${{ github.ref }}",
        "cancel-in-progress": True,
    }


def test_triggers_exclude_pull_request_target(workflow: dict[str, Any]) -> None:
    """Security: no pull_request_target (it would expose secrets to forks)."""
    # YAML 1.1 (PyYAML) parses the bare key `on` as boolean True.
    raw = cast("dict[Any, Any]", workflow)
    triggers = raw.get("on", raw.get(True))
    assert triggers is not None
    assert "pull_request_target" not in triggers
    assert "push" in triggers
    assert "pull_request" in triggers


def test_every_uses_is_pinned_to_a_full_commit_sha(jobs: dict[str, dict[str, Any]]) -> None:
    """Security: every `uses:` is owner/repo@<40 hex> with a trailing version comment."""
    text = FORGEJO_WORKFLOW.read_text(encoding="utf-8")
    for job in jobs.values():
        for step in job["steps"]:
            if "uses" in step:
                assert USES_PATTERN.match(step["uses"]), step["uses"]
    for line in text.splitlines():
        if "uses:" in line:
            assert re.search(r"@[0-9a-f]{40} # v\d+\.\d+\.\d+$", line.strip()), line


def test_secrets_are_scoped_to_their_jobs(jobs: dict[str, dict[str, Any]]) -> None:
    """Security: Docker Hub secrets exist only in docker-push; none appear in `run:` bodies."""
    text = FORGEJO_WORKFLOW.read_text(encoding="utf-8")
    refs = {part.split("}}")[0].strip() for part in text.split("secrets.")[1:]}
    assert refs == ALLOWED_SECRETS
    for name, job in jobs.items():
        job_text = yaml.safe_dump(job)
        for secret in DOCKERHUB_SECRETS:
            assert (secret in job_text) == (name == "docker-push"), (name, secret)
        for step in job["steps"]:
            assert "secrets." not in str(step.get("run", "")), (name, step["name"])


def test_docker_push_gating_and_dependencies(jobs: dict[str, dict[str, Any]]) -> None:
    """Security: docker-push runs only for main pushes, after all five other jobs succeed."""
    job = jobs["docker-push"]
    assert job["needs"] == [
        "lint-type",
        "python-tests",
        "web-tests",
        "license-gate",
        "docker-build",
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


def test_only_docker_push_may_push_images(jobs: dict[str, dict[str, Any]]) -> None:
    """Security: no other job references push or the login/build-push actions."""
    for name, job in jobs.items():
        if name == "docker-push":
            continue
        assert "push" not in _run_text(job), name
        assert not any("docker/login-action" in str(s.get("uses", "")) for s in job["steps"]), name


def test_last_step_uploads_logs_artifact_always(jobs: dict[str, dict[str, Any]]) -> None:
    """Positive: each job ends with an always() upload-artifact of ci-logs/."""
    for name, job in jobs.items():
        last = job["steps"][-1]
        assert last["if"] == "always()", name
        assert last["uses"].startswith("actions/upload-artifact@"), name
        assert last["with"]["name"] == "ci-logs-${{ github.job }}", name
        assert last["with"]["path"] == "ci-logs/", name
        assert last["with"]["retention-days"] == 14, name
        assert last["with"]["if-no-files-found"] == "error", name


def test_dash_upload_runs_always_before_artifact(jobs: dict[str, dict[str, Any]]) -> None:
    """Positive: each job uploads to Dash with always(), token via env, before the artifact."""
    for name, job in jobs.items():
        dash = next(s for s in job["steps"] if s.get("name") == "Upload logs to Dash")
        assert dash["if"] == "always()", name
        assert dash["env"] == {"DASH_TOKEN": "${{ secrets.DASH_TOKEN }}"}, name
        assert dash["run"] == f"scripts/ci/upload_dash_log.sh {name}", name
        assert job["steps"].index(dash) < len(job["steps"]) - 1


def test_python_tests_reports_uploaded_always(jobs: dict[str, dict[str, Any]]) -> None:
    """Positive: coverage.xml and pytest.xml are uploaded with always()."""
    step = next(s for s in jobs["python-tests"]["steps"] if "reports/" in str(s.get("with", {})))
    assert step["if"] == "always()"
    assert step["with"]["path"] == "reports/"


def test_job_log_dir_env_matches_job_id(jobs: dict[str, dict[str, Any]]) -> None:
    """Positive: CI_JOB_NAME places logs under ci-logs/<job-id>/."""
    for name, job in jobs.items():
        assert job["env"] == {"CI_JOB_NAME": name}


def test_python_tests_enforce_coverage_threshold(jobs: dict[str, dict[str, Any]]) -> None:
    """Boundary: python-tests fails below 95% branch coverage and runs serially on shared DB."""
    run = _run_text(jobs["python-tests"])
    assert "--cov-fail-under=95" in run
    assert "--cov-branch" in run
    assert "make testdb-up" in run
    assert "make testdb-down" in run
    assert "-n auto" not in run


def test_testdb_teardown_always_runs(jobs: dict[str, dict[str, Any]]) -> None:
    """Positive: DB teardown runs on failure too."""
    step = next(s for s in jobs["python-tests"]["steps"] if s.get("name") == "Stop test database")
    assert step["if"] == "always()"


def test_web_tests_commands(jobs: dict[str, dict[str, Any]]) -> None:
    """Boundary: web-tests runs frozen install, typecheck, lint, coverage and build."""
    run = _run_text(jobs["web-tests"])
    assert "pnpm install --frozen-lockfile --ignore-scripts" in run
    assert "typecheck" in run
    assert "lint" in run
    assert "test:unit --coverage" in run
    assert "kanban/web build" in run


def test_lint_type_and_license_commands(jobs: dict[str, dict[str, Any]]) -> None:
    """Positive: Shift-Left gates stay in the pipeline."""
    assert "uv sync --locked && make check" in _run_text(jobs["lint-type"])
    license_run = _run_text(jobs["license-gate"])
    assert "make license" in license_run
    assert "uv sync --locked" in license_run
    assert "pnpm install --frozen-lockfile --ignore-scripts" in license_run


def test_docker_build_builds_both_targets(jobs: dict[str, dict[str, Any]]) -> None:
    """Positive: both image targets are built locally (no push) and listed."""
    run = _run_text(jobs["docker-build"])
    assert "--target runtime-slim -t kanban:runtime-slim --load ." in run
    assert "--target standalone -t kanban:standalone --load ." in run
    assert "docker image ls kanban" in run
    assert "push" not in run


def test_every_command_step_runs_through_run_and_log(jobs: dict[str, dict[str, Any]]) -> None:
    """Positive: only setup, apt and Dash/upload steps may bypass run_and_log.sh."""
    exempt = {"Install system dependencies", "Upload logs to Dash"}
    for job in jobs.values():
        for step in job["steps"]:
            if "run" in step and step["name"] not in exempt:
                assert "scripts/ci/run_and_log.sh" in step["run"], step["name"]


def test_ci_doc_has_required_sections() -> None:
    """Positive: docs/CI.md documents jobs, log reading and Dash verification."""
    text = (REPO_ROOT / "docs" / "CI.md").read_text(encoding="utf-8")
    for heading in ("## Jobs", "## Reading Logs", "## Dash Verification"):
        assert heading in text
    assert "https://dash.hackedyour.info/llms.txt" in text
