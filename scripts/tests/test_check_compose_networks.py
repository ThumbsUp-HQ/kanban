"""Unit tests for scripts.check_compose_networks validating isolation and hardening."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, cast
from unittest.mock import MagicMock, patch

import pytest

from scripts.check_compose_networks import (
    main,
    validate_compose_dict,
)

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "compose_config.json"


@pytest.fixture
def base_compose_config() -> dict[str, Any]:
    """Load canonical fixture JSON config."""
    with FIXTURE_PATH.open(encoding="utf-8") as f:
        return cast("dict[str, Any]", json.load(f))


def test_positive_committed_fixture(capsys: pytest.CaptureFixture[str]) -> None:
    """Test Case 1: Positive run on committed fixture yields exit 0 and PASS message."""
    exit_code = main(["--config-json", str(FIXTURE_PATH)])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "PASS: Docker Compose network isolation and hardening policies verified." in captured.out
    assert captured.err == ""


def test_negative_mcp_server_joins_data_net(
    base_compose_config: dict[str, Any],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Test Case 2a: mcp-server connected to data_net causes exit 1 naming mcp-server."""
    config = copy.deepcopy(base_compose_config)
    config["services"]["mcp-server"]["networks"] = ["app_net", "data_net"]

    cfg_file = tmp_path / "mcp_violation.json"
    cfg_file.write_text(json.dumps(config), encoding="utf-8")

    exit_code = main(["--config-json", str(cfg_file)])
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "FAIL: 2 compose policy violation(s) found:" in captured.out
    assert "Service 'mcp-server' must NOT connect to 'data_net'" in captured.out
    assert "Service 'mcp-server' networks mismatch" in captured.out


def test_negative_data_net_internal_false(
    base_compose_config: dict[str, Any],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Test Case 2b: data_net internal flag set to false causes exit 1."""
    config = copy.deepcopy(base_compose_config)
    config["networks"]["data_net"]["internal"] = False

    cfg_file = tmp_path / "data_net_violation.json"
    cfg_file.write_text(json.dumps(config), encoding="utf-8")

    exit_code = main(["--config-json", str(cfg_file)])
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "Network 'data_net' internal flag mismatch: expected True, got False" in captured.out


def test_negative_postgres_publishes_ports(
    base_compose_config: dict[str, Any],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Test Case 2c: non-reverse-proxy service publishing ports causes exit 1."""
    config = copy.deepcopy(base_compose_config)
    config["services"]["postgres"]["ports"] = ["5432:5432"]

    cfg_file = tmp_path / "port_violation.json"
    cfg_file.write_text(json.dumps(config), encoding="utf-8")

    exit_code = main(["--config-json", str(cfg_file)])
    captured = capsys.readouterr()

    assert exit_code == 1
    expected_msg = (
        "Service 'postgres' publishes ports ['5432:5432']; only 'reverse-proxy' may publish ports"
    )
    assert expected_msg in captured.out


def test_negative_plaintext_secret_environment(
    base_compose_config: dict[str, Any],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Test Case 3a: Plaintext secret in environment dictionary causes exit 1."""
    config = copy.deepcopy(base_compose_config)
    config["services"]["postgres"]["environment"] = {
        "POSTGRES_PASSWORD": "hunter2hunter2",
    }

    cfg_file = tmp_path / "secret_violation.json"
    cfg_file.write_text(json.dumps(config), encoding="utf-8")

    exit_code = main(["--config-json", str(cfg_file)])
    captured = capsys.readouterr()

    assert exit_code == 1
    expected_msg = (
        "Service 'postgres' contains potential secret in environment: 'POSTGRES_PASSWORD'"
    )
    assert expected_msg in captured.out


def test_negative_plaintext_secret_environment_list(
    base_compose_config: dict[str, Any],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Test Case 3b: Plaintext secret in environment list causes exit 1."""
    config = copy.deepcopy(base_compose_config)
    config["services"]["postgres"]["environment"] = [
        "POSTGRES_PASSWORD=hunter2hunter2",
        "POSTGRES_PASSWORD_FILE=/run/secrets/pg_pass",
        "SAFE_KEY_VALUE=harmless",
    ]

    cfg_file = tmp_path / "secret_list_violation.json"
    cfg_file.write_text(json.dumps(config), encoding="utf-8")

    exit_code = main(["--config-json", str(cfg_file)])
    captured = capsys.readouterr()

    assert exit_code == 1
    expected_msg = (
        "Service 'postgres' contains potential secret in environment: "
        "'POSTGRES_PASSWORD=hunter2hunter2'"
    )
    assert expected_msg in captured.out


def test_negative_missing_cap_drop_and_no_new_privileges(
    base_compose_config: dict[str, Any],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Test Case 3c: Service missing cap_drop ALL or no-new-privileges causes exit 1."""
    config = copy.deepcopy(base_compose_config)
    config["services"]["kanban-api"]["cap_drop"] = []
    config["services"]["kanban-api"]["security_opt"] = []

    cfg_file = tmp_path / "hardening_violation.json"
    cfg_file.write_text(json.dumps(config), encoding="utf-8")

    exit_code = main(["--config-json", str(cfg_file)])
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "Service 'kanban-api' missing cap_drop containing 'ALL'" in captured.out
    assert "Service 'kanban-api' missing 'no-new-privileges:true' in security_opt" in captured.out


def test_boundary_missing_or_invalid_json(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Test Case 4a: Missing config file or invalid JSON string causes exit 3."""
    missing_file = tmp_path / "does_not_exist.json"
    exit_code = main(["--config-json", str(missing_file)])
    captured = capsys.readouterr()
    assert exit_code == 3
    assert f"Error reading JSON config '{missing_file}'" in captured.err

    corrupt_file = tmp_path / "corrupt.json"
    corrupt_file.write_text("{not-valid-json", encoding="utf-8")
    exit_code_corrupt = main(["--config-json", str(corrupt_file)])
    captured_corrupt = capsys.readouterr()
    assert exit_code_corrupt == 3
    assert f"Error reading JSON config '{corrupt_file}'" in captured_corrupt.err


def test_boundary_script_sandbox_profile_and_networks(
    base_compose_config: dict[str, Any],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Test Case 4b: script-sandbox without sandbox profile or wrong network causes exit 1."""
    config = copy.deepcopy(base_compose_config)
    config["services"]["script-sandbox"]["profiles"] = ["other"]
    config["services"]["script-sandbox"]["networks"] = ["app_net"]

    cfg_file = tmp_path / "sandbox_violation.json"
    cfg_file.write_text(json.dumps(config), encoding="utf-8")

    exit_code = main(["--config-json", str(cfg_file)])
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "Service 'script-sandbox' must specify profile 'sandbox'" in captured.out
    assert (
        "Service 'script-sandbox' networks mismatch: expected ['sandbox_net'], got ['app_net']"
        in captured.out
    )


def test_boundary_dynamic_collector_subprocess_failure(capsys: pytest.CaptureFixture[str]) -> None:
    """Test Case 4c: Subprocess failure in dynamic collection causes exit 3."""
    mock_proc = MagicMock()
    mock_proc.returncode = 1
    mock_proc.stderr = "Docker daemon not running"

    with patch("subprocess.run", return_value=mock_proc):
        exit_code = main([])
        captured = capsys.readouterr()

    assert exit_code == 3
    assert "docker compose config command failed:" in captured.err
    assert "Docker daemon not running" in captured.err


def test_boundary_dynamic_collector_exception(capsys: pytest.CaptureFixture[str]) -> None:
    """Test Case 4d: Exception raised during subprocess execution causes exit 3."""
    with patch("subprocess.run", side_effect=OSError("Command not found")):
        exit_code = main([])
        captured = capsys.readouterr()

    assert exit_code == 3
    assert "Error executing docker compose config: Command not found" in captured.err


def test_boundary_top_level_services_invalid() -> None:
    """Validate top-level services mapping missing or wrong type."""
    assert validate_compose_dict({}) == ["Top-level 'services' mapping is missing or invalid"]
    assert validate_compose_dict({"services": []}) == [
        "Top-level 'services' mapping is missing or invalid"
    ]


def test_boundary_missing_and_unexpected_services(base_compose_config: dict[str, Any]) -> None:
    """Validate reporting of missing expected service and extra unexpected service."""
    config = copy.deepcopy(base_compose_config)
    del config["services"]["reverse-proxy"]
    config["services"]["rogue-miner"] = {
        "image": "busybox",
        "networks": ["edge_net"],
        "cap_drop": ["ALL"],
        "security_opt": ["no-new-privileges:true"],
    }

    violations = validate_compose_dict(config)
    assert any("Missing required services: ['reverse-proxy']" in v for v in violations)
    assert any("Unexpected services found: ['rogue-miner']" in v for v in violations)


def test_boundary_top_level_networks_invalid(base_compose_config: dict[str, Any]) -> None:
    """Validate top-level networks mapping missing or invalid."""
    config = copy.deepcopy(base_compose_config)
    del config["networks"]

    violations = validate_compose_dict(config)
    assert "Top-level 'networks' mapping is missing or invalid" in violations


def test_boundary_missing_network_in_definition(base_compose_config: dict[str, Any]) -> None:
    """Validate network missing from top-level definitions."""
    config = copy.deepcopy(base_compose_config)
    del config["networks"]["sandbox_net"]

    violations = validate_compose_dict(config)
    assert "Network 'sandbox_net' is missing from networks definition" in violations


def test_boundary_non_dict_config_payload(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Validate config returning non-dict JSON root causes exit 3."""
    cfg_file = tmp_path / "array_root.json"
    cfg_file.write_text("[1, 2, 3]", encoding="utf-8")

    exit_code = main(["--config-json", str(cfg_file)])
    captured = capsys.readouterr()

    assert exit_code == 3
    assert "Parsed Compose configuration is not a valid JSON object" in captured.err


def test_boundary_dynamic_collector_success(
    base_compose_config: dict[str, Any],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Verify dynamic collection through subprocess when docker compose succeeds."""
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.stdout = json.dumps(base_compose_config)
    mock_proc.stderr = ""

    with patch("subprocess.run", return_value=mock_proc):
        exit_code = main([])
        captured = capsys.readouterr()

    assert exit_code == 0
    assert "PASS: Docker Compose network isolation and hardening policies verified." in captured.out


def test_boundary_dynamic_collector_non_dict_stdout(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Verify dynamic collection returns 3 if compose config returns non-dict JSON."""
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.stdout = "[1, 2, 3]"
    mock_proc.stderr = ""

    with patch("subprocess.run", return_value=mock_proc):
        exit_code = main([])
        captured = capsys.readouterr()

    assert exit_code == 3
    assert "Parsed Compose configuration is not a valid JSON object" in captured.err


def test_boundary_script_sandbox_omitted(base_compose_config: dict[str, Any]) -> None:
    """Verify handling when script-sandbox is absent from services."""
    config = copy.deepcopy(base_compose_config)
    del config["services"]["script-sandbox"]
    violations = validate_compose_dict(config)
    assert any("Missing required services: ['script-sandbox']" in v for v in violations)


def test_environment_file_variables_are_allowed(base_compose_config: dict[str, Any]) -> None:
    """Ensure environment variables referencing file paths (_FILE) do not trigger violations."""
    config = copy.deepcopy(base_compose_config)
    config["services"]["postgres"]["environment"] = {
        "POSTGRES_PASSWORD_FILE": "/run/secrets/postgres_password",
        "MASTER_KEK_FILE": "/run/secrets/master_kek",
    }
    violations = validate_compose_dict(config)
    assert not any("contains potential secret in environment" in v for v in violations)


def test_environment_list_without_secrets(base_compose_config: dict[str, Any]) -> None:
    """Ensure environment list with harmless strings passes without violations."""
    config = copy.deepcopy(base_compose_config)
    config["services"]["postgres"]["environment"] = [
        "POSTGRES_DB=kanbandb",
        "PGDATA=/var/lib/postgresql/data/pgdata",
    ]
    violations = validate_compose_dict(config)
    assert not any("contains potential secret in environment" in v for v in violations)
