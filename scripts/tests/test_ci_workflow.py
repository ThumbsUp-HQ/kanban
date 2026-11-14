"""Structural and security tests for the CI workflow (KB-P0-06 / KANBA-28).

The project CI runs on the Forgejo runner ``inferrence1`` as a single
``build-test-push`` job. These tests pin the invariants that keep failed runs
diagnosable: every verification command is wrapped by ``run_and_log.sh``, the
Dash log upload always runs last, and the workflow never widens its trigger or
permission surface.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
GITHUB_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"
FORGEJO_WORKFLOW = REPO_ROOT / ".forgejo" / "workflows" / "ci.yml"
JOB_ID = "build-test-push"


def _load(path: Path) -> dict[str, Any]:
    """Parse a workflow with ``safe_load`` only (never ``yaml.load``)."""
    return cast("dict[str, Any]", yaml.safe_load(path.read_text(encoding="utf-8")))


@pytest.fixture(scope="module")
def workflow() -> dict[str, Any]:
    """Return the parsed Forgejo workflow."""
    return _load(FORGEJO_WORKFLOW)


@pytest.fixture(scope="module")
def steps(workflow: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the ordered steps of the single CI job."""
    return cast("list[dict[str, Any]]", workflow["jobs"][JOB_ID]["steps"])


def _step(steps: list[dict[str, Any]], name: str) -> dict[str, Any]:
    matches = [s for s in steps if s.get("name") == name]
    assert len(matches) == 1, f"expected exactly one step named {name!r}"
    return matches[0]


def test_workflow_copies_are_identical() -> None:
    """Positive: the GitHub and Forgejo workflow files must not drift."""
    assert GITHUB_WORKFLOW.read_text(encoding="utf-8") == FORGEJO_WORKFLOW.read_text(
        encoding="utf-8"
    )


def test_job_runs_on_inferrence1(workflow: dict[str, Any]) -> None:
    """Positive: the single job targets the project Forgejo runner."""
    assert list(workflow["jobs"]) == [JOB_ID]
    assert workflow["jobs"][JOB_ID]["runs-on"] == ["inferrence1"]


def test_triggers_exclude_pull_request_target(workflow: dict[str, Any]) -> None:
    """Security: no pull_request_target (it would expose secrets to forks)."""
    # YAML 1.1 (PyYAML) parses the bare key `on` as boolean True.
    raw = cast("dict[Any, Any]", workflow)
    triggers = raw.get("on", raw.get(True))
    assert triggers is not None
    assert "pull_request_target" not in triggers
    assert "push" in triggers
    assert "pull_request" in triggers


def test_verification_steps_use_run_and_log(steps: list[dict[str, Any]]) -> None:
    """Positive: lint, DB start/stop and tests are wrapped for log capture."""
    expected = {
        "Run lint and checks": "run_and_log.sh lint-type-license --",
        "Start test database": "run_and_log.sh testdb-up --",
        "Run tests": "run_and_log.sh unit-tests --",
        "Stop test database": "run_and_log.sh testdb-down --",
    }
    for name, needle in expected.items():
        assert needle in _step(steps, name)["run"]


def test_unit_test_command_excludes_container_marker(steps: list[dict[str, Any]]) -> None:
    """Boundary: the runner has no nested docker for container-marked tests."""
    assert 'pytest -q -m "not container"' in _step(steps, "Run tests")["run"]


def test_lint_step_runs_make_check_and_license(steps: list[dict[str, Any]]) -> None:
    """Positive: the Shift-Left gates stay in the pipeline."""
    run = _step(steps, "Run lint and checks")["run"]
    assert "make check" in run
    assert "make license" in run
    assert "uv sync --locked" in run


def test_testdb_teardown_always_runs(steps: list[dict[str, Any]]) -> None:
    """Positive: DB teardown runs on failure too."""
    assert _step(steps, "Stop test database")["if"] == "always()"


def test_dash_upload_is_last_and_always(steps: list[dict[str, Any]]) -> None:
    """Positive: logs are uploaded to Dash with if: always(), as the final step."""
    last = steps[-1]
    assert last["name"] == "Upload logs to Dash"
    assert last["if"] == "always()"
    assert "https://dash.hackedyour.info/api/logs" in last["run"]
    assert "ci-logs/*/*.log" in last["run"]


def test_dash_token_passed_via_env_not_inlined(steps: list[dict[str, Any]]) -> None:
    """Security: the Dash token is an env var, never interpolated into the script."""
    last = steps[-1]
    assert last["env"] == {"DASH_TOKEN": "${{ secrets.DASH_TOKEN }}"}
    assert "secrets." not in last["run"]


def test_dash_upload_tolerates_missing_token(steps: list[dict[str, Any]]) -> None:
    """Negative: a missing token skips the upload instead of failing the job."""
    run = steps[-1]["run"]
    assert 'if [ -z "${DASH_TOKEN:-}" ]' in run
    assert "exit 0" in run


def test_job_log_dir_env_is_set(workflow: dict[str, Any]) -> None:
    """Positive: CI_JOB_NAME places logs under ci-logs/build-test-push/."""
    assert workflow["env"] == {"CI_JOB_NAME": JOB_ID}


def test_only_expected_secrets_referenced() -> None:
    """Security: only the registry and Dash secrets are ever referenced."""
    text = FORGEJO_WORKFLOW.read_text(encoding="utf-8")
    refs = {part.split("}}")[0].strip() for part in text.split("secrets.")[1:]}
    assert refs <= {
        "DOCKERHUB_USERNAME",
        "DOCKERHUB_TOKEN",
        "DASH_TOKEN",
    }


def test_ci_doc_has_required_sections() -> None:
    """Positive: docs/CI.md documents jobs, log reading and Dash verification."""
    text = (REPO_ROOT / "docs" / "CI.md").read_text(encoding="utf-8")
    for heading in ("## Jobs", "## Reading Logs", "## Dash Verification"):
        assert heading in text
    assert "https://dash.hackedyour.info/llms.txt" in text
