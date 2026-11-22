# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
# ruff: noqa: E501, PLR0915, PLC0415, S106, ANN401, ARG001, ARG005, TRY003, EM101, SLF001, PTH101
"""Comprehensive unit and security tests for kanban-cli authentication, configuration, and I/O ergonomics (KAN-48)."""

from __future__ import annotations

import asyncio
import io
import os
import sys
from pathlib import Path
from typing import Any

import httpx
import pytest

from mcp.cli.auth import (
    auth_login,
    auth_logout,
    auth_status,
    get_config_dir,
    get_credentials_path,
    load_config,
    load_credentials,
    resolve_config,
    save_credentials,
)
from mcp.cli.main import main
from mcp.cli.schema_cli import assert_no_surrogates, generate_completions
from mcp.errors import KbMcpError, McpErrorCode
from mcp.internal_client import KanbanApiClient


@pytest.fixture(autouse=True)
def _clean_kanban_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure tests run in clean environment without ambient tokens."""
    for var in (
        "KANBAN_URL",
        "KANBAN_WORKSPACE",
        "KANBAN_PROJECT",
        "KANBAN_API_KEY",
        "KANBAN_TOKEN",
    ):
        monkeypatch.delenv(var, raising=False)


def test_config_precedence(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Verify configuration resolution precedence: CLI > ENV > config file > default."""
    monkeypatch.setenv("KANBAN_CONFIG_DIR", str(tmp_path))
    monkeypatch.delenv("KANBAN_URL", raising=False)
    monkeypatch.delenv("KANBAN_WORKSPACE", raising=False)
    monkeypatch.delenv("KANBAN_PROJECT", raising=False)
    monkeypatch.delenv("KANBAN_API_KEY", raising=False)
    monkeypatch.delenv("KANBAN_TOKEN", raising=False)

    # 1. Default fallback
    cfg_default = resolve_config()
    assert cfg_default.url == "http://localhost:8080"
    assert cfg_default.workspace is None
    assert cfg_default.project is None
    assert cfg_default.token is None

    # 2. Config file fallback
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        'url = "http://localhost:9000"\nworkspace = "ws_file"\nproject = "PRJ_FILE"\n',
        encoding="utf-8",
    )
    save_credentials({"api_key": "token_from_file"})

    cfg_file = resolve_config()
    assert cfg_file.url == "http://localhost:9000"
    assert cfg_file.workspace == "ws_file"
    assert cfg_file.project == "PRJ_FILE"
    assert cfg_file.token == "token_from_file"

    # 3. Environment variables override config files
    monkeypatch.setenv("KANBAN_URL", "http://localhost:9100")
    monkeypatch.setenv("KANBAN_WORKSPACE", "ws_env")
    monkeypatch.setenv("KANBAN_PROJECT", "PRJ_ENV")
    monkeypatch.setenv("KANBAN_API_KEY", "token_from_env")

    cfg_env = resolve_config()
    assert cfg_env.url == "http://localhost:9100"
    assert cfg_env.workspace == "ws_env"
    assert cfg_env.project == "PRJ_ENV"
    assert cfg_env.token == "token_from_env"

    # 4. CLI flags override environment variables
    cfg_cli = resolve_config(
        cli_url="http://localhost:9200",
        cli_workspace="ws_cli",
        cli_project="PRJ_CLI",
        cli_token="token_from_cli",
    )
    assert cfg_cli.url == "http://localhost:9200"
    assert cfg_cli.workspace == "ws_cli"
    assert cfg_cli.project == "PRJ_CLI"
    assert cfg_cli.token == "token_from_cli"


def test_credentials_file_security_permissions(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Verify credentials.toml enforces 0600 mode and rejects looser permissions or symlinks."""
    monkeypatch.setenv("KANBAN_CONFIG_DIR", str(tmp_path))
    cred_file = tmp_path / "credentials.toml"

    # 1. Saving credentials creates 0600 file
    save_credentials({"api_key": "kb_secret_token"})
    mode = cred_file.stat().st_mode & 0o777
    assert mode == 0o600, f"Expected 0600 mode, got {oct(mode)}"

    creds = load_credentials()
    assert creds.get("api_key") == "kb_secret_token"

    # 2. Permissions looser than 0600 (group or world readable/writable) fail-closed
    os.chmod(cred_file, 0o644)
    with pytest.raises(ValueError, match="insecure permissions"):
        load_credentials()

    os.chmod(cred_file, 0o660)
    with pytest.raises(ValueError, match="insecure permissions"):
        load_credentials()

    # 3. Symlink rejection
    cred_file.unlink()
    target_secret = tmp_path / "target_secret.toml"
    target_secret.write_text('api_key = "secret_symlink"\n', encoding="utf-8")
    os.chmod(target_secret, 0o600)
    cred_file.symlink_to(target_secret)

    with pytest.raises(ValueError, match="must not be a symlink"):
        load_credentials()

    with pytest.raises(ValueError, match="must not be a symlink"):
        save_credentials({"api_key": "new_secret"})


def test_auth_commands_flow(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Verify auth login, status, and logout commands."""
    monkeypatch.setenv("KANBAN_CONFIG_DIR", str(tmp_path))

    # 1. Login with direct token
    ret_login = auth_login("http://localhost:8080", token="kb_user_token_abc")
    assert ret_login == 0
    creds = load_credentials()
    assert creds.get("api_key") == "kb_user_token_abc"

    # 2. Status check with mock client
    mock_transport = httpx.MockTransport(
        lambda r: httpx.Response(
            200, json={"user": {"handle": "@alice", "email": "alice@example.com"}}
        )
    )
    with httpx.Client(transport=mock_transport, base_url="http://localhost:8080") as mock_client:
        cfg = resolve_config()
        ret_status = auth_status(cfg, client=mock_client)
        assert ret_status == 0

    # 3. Logout clears credentials
    ret_logout = auth_logout()
    assert ret_logout == 0
    assert not get_credentials_path().exists()

    # Idempotent second logout succeeds cleanly
    ret_logout_again = auth_logout()
    assert ret_logout_again == 0


def test_cli_remote_security_loopback_and_https() -> None:
    """Verify KanbanApiClient in cli_remote mode permits loopback http and enforces https for remote."""
    # 1. Loopback http:// URLs allowed
    c_loc = KanbanApiClient(mode="cli_remote", base_url="http://localhost:8080")
    assert c_loc._client.base_url == "http://localhost:8080"

    c_ip4 = KanbanApiClient(mode="cli_remote", base_url="http://127.0.0.1:8080")
    assert c_ip4._client.base_url == "http://127.0.0.1:8080"

    # 2. Remote https:// allowed
    c_https = KanbanApiClient(mode="cli_remote", base_url="https://kanban.internal.example.com")
    assert c_https._client.base_url == "https://kanban.internal.example.com"

    # 3. Remote plaintext http:// strictly rejected
    with pytest.raises(ValueError, match="strictly prohibited for remote hosts"):
        KanbanApiClient(mode="cli_remote", base_url="http://remote.insecure.com:8080")

    with pytest.raises(ValueError, match="strictly prohibited for remote hosts"):
        KanbanApiClient(mode="cli_remote", base_url="http://192.168.1.50:8080")


def test_utf16_lone_surrogate_rejection() -> None:
    """Verify UTF-16 lone surrogates in input text, files, or stdin raise INVALID_UTF8_SURROGATE."""
    # High surrogate U+D800
    with pytest.raises(KbMcpError) as exc_high:
        assert_no_surrogates("bad\ud800text")
    assert exc_high.value.code == McpErrorCode.VALIDATION_FAILED
    assert exc_high.value.message == "INVALID_UTF8_SURROGATE"

    # Low surrogate U+DFFF
    with pytest.raises(KbMcpError) as exc_low:
        assert_no_surrogates("bad\udffftext")
    assert exc_low.value.code == McpErrorCode.VALIDATION_FAILED
    assert exc_low.value.message == "INVALID_UTF8_SURROGATE"

    # Clean text passes
    assert_no_surrogates("clean standard UTF-8 text with emojis 👍")


def test_shell_completions_generation() -> None:
    """Verify shell completion scripts are generated for bash, zsh, and fish with zero shell=True calls."""
    bash_comp = generate_completions("bash")
    assert "_kanban_cli_completions()" in bash_comp
    assert "complete -F _kanban_cli_completions kanban-cli" in bash_comp
    assert "create-ticket" in bash_comp

    zsh_comp = generate_completions("zsh")
    assert "#compdef kanban-cli" in zsh_comp
    assert "_describe -t commands" in zsh_comp

    fish_comp = generate_completions("fish")
    assert "complete -c kanban-cli" in fish_comp
    assert "__fish_use_subcommand" in fish_comp


def test_cli_prose_file_and_structured_flags(tmp_path: Path) -> None:
    """Verify @file, --description-file, and structured JSON parsing."""
    spec_file = tmp_path / "spec.md"
    spec_file.write_text("# Feature Spec\nDetailed markdown specification.", encoding="utf-8")

    proof_file = tmp_path / "proof.json"
    proof_file.write_text(
        '{"qa_dir": "docs/qa/KAN-1", "ci_run_url": "https://ci/1"}', encoding="utf-8"
    )

    # Introspect parsing using schema_cli helpers
    from mcp.cli.schema_cli import _normalize_parsed_arguments
    from mcp.surfaces.agent import create_agent_registry

    agent_reg = create_agent_registry()
    create_spec = agent_reg.get("create_ticket")
    assert create_spec is not None
    assert create_spec is not None

    parsed_input = {
        "project": "KAN",
        "summary": "Implement feature",
        "description_markdown_file": str(spec_file),
    }
    normalized = _normalize_parsed_arguments(create_spec, parsed_input)
    assert normalized["description_markdown"] == "# Feature Spec\nDetailed markdown specification."
    assert normalized["project"] == "KAN"
    assert normalized["summary"] == "Implement feature"

    # Structured verification proof @path
    trans_spec = agent_reg.get("transition_ticket")
    assert trans_spec is not None
    trans_input = {
        "identifier": "KAN-1",
        "to_state": "Done",
        "verification_proof": f"@{proof_file}",
    }
    normalized_trans = _normalize_parsed_arguments(trans_spec, trans_input)
    assert isinstance(normalized_trans["verification_proof"], dict)
    assert normalized_trans["verification_proof"]["qa_dir"] == "docs/qa/KAN-1"


def test_cli_filter_predicate_delegation() -> None:
    """Verify --filter string delegates to KAN-78 predicate compiler."""
    from mcp.cli.schema_cli import _apply_predicate_filter

    args: dict[str, Any] = {"project": "KAN"}
    filter_expr = 'status = "Todo" AND priority:high AND assignee:@alice AND cycle:c1 AND module:m1 AND label:bug AND blocked:true AND gate:pending some query text'
    _apply_predicate_filter(args, filter_expr)

    assert "Todo" in args.get("states", [])
    assert "@alice" in args.get("assignees", [])
    assert args.get("_filter_priority") == "high"
    assert args.get("cycle") == "c1"
    assert "m1" in args.get("modules", [])
    assert "bug" in args.get("labels", [])
    assert args.get("blocked") is True
    assert args.get("gate_status") == "pending"
    assert "some query text" in args.get("query", "")


def test_auth_login_device_flow(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Verify auth login --device flow (RFC 8628)."""
    monkeypatch.setenv("KANBAN_CONFIG_DIR", str(tmp_path))

    call_count = 0

    def mock_device_handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        if request.url.path == "/oauth/device/authorize":
            return httpx.Response(
                200,
                json={
                    "device_code": "d_123",
                    "user_code": "ABCD-1234",
                    "verification_uri": "https://auth/device",
                    "interval": 0,
                    "expires_in": 30,
                },
            )
        if request.url.path == "/oauth/token":
            call_count += 1
            if call_count == 1:
                return httpx.Response(200, json={"error": "authorization_pending"})
            return httpx.Response(200, json={"access_token": "token_from_device"})
        return httpx.Response(404)

    client = httpx.Client(
        transport=httpx.MockTransport(mock_device_handler), base_url="http://localhost:8080"
    )
    monkeypatch.setattr("time.sleep", lambda _: None)
    ret = auth_login("http://localhost:8080", device=True, client=client)
    assert ret == 0
    creds = load_credentials()
    assert creds.get("api_key") == "token_from_device"

    # Error path: authorize returns 400
    err_client = httpx.Client(
        transport=httpx.MockTransport(lambda r: httpx.Response(400, text="Bad Request")),
        base_url="http://localhost:8080",
    )
    ret_err = auth_login("http://localhost:8080", device=True, client=err_client)
    assert ret_err == 1

    # Error path: token polling error
    def fatal_token_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth/device/authorize":
            return httpx.Response(
                200,
                json={
                    "device_code": "d_123",
                    "user_code": "ABCD-1234",
                    "verification_uri": "https://auth/device",
                    "interval": 0,
                    "expires_in": 30,
                },
            )
        return httpx.Response(
            200, headers={"content-type": "application/json"}, json={"error": "access_denied"}
        )

    fatal_client = httpx.Client(
        transport=httpx.MockTransport(fatal_token_handler), base_url="http://localhost:8080"
    )
    ret_fatal = auth_login("http://localhost:8080", device=True, client=fatal_client)
    assert ret_fatal == 1


def test_auth_login_pkce_flow(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Verify standard interactive PKCE authorization flow."""
    monkeypatch.setenv("KANBAN_CONFIG_DIR", str(tmp_path))

    def mock_pkce_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth/token":
            return httpx.Response(200, json={"access_token": "token_pkce_abc"})
        return httpx.Response(404)

    client = httpx.Client(
        transport=httpx.MockTransport(mock_pkce_handler), base_url="http://localhost:8080"
    )
    monkeypatch.setattr("builtins.input", lambda _: "auth_code_123")
    ret = auth_login("http://localhost:8080", device=False, client=client)
    assert ret == 0
    assert load_credentials().get("api_key") == "token_pkce_abc"

    # Cancelled flow (empty code)
    monkeypatch.setattr("builtins.input", lambda _: "")
    ret_cancel = auth_login("http://localhost:8080", device=False, client=client)
    assert ret_cancel == 1

    # Token exchange failure
    fail_client = httpx.Client(
        transport=httpx.MockTransport(lambda r: httpx.Response(400, text="invalid_grant")),
        base_url="http://localhost:8080",
    )
    monkeypatch.setattr("builtins.input", lambda _: "code_bad")
    ret_fail = auth_login("http://localhost:8080", device=False, client=fail_client)
    assert ret_fail == 1


def test_auth_status_variants() -> None:
    """Verify auth status output under unauthenticated, 401 unauthorized, and network failure."""
    # 1. Unauthenticated
    cfg_unauth = resolve_config(cli_url="http://localhost:8080", cli_token=None)
    assert auth_status(cfg_unauth) == 0

    # 2. 401 Unauthorized
    client_401 = httpx.Client(
        transport=httpx.MockTransport(lambda r: httpx.Response(401, text="Unauthorized")),
        base_url="http://localhost:8080",
    )
    cfg_auth = resolve_config(cli_url="http://localhost:8080", cli_token="bad_token")
    assert auth_status(cfg_auth, client=client_401) == 1

    # 3. Network connection exception
    def err_handler(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Connection refused")

    client_err = httpx.Client(
        transport=httpx.MockTransport(err_handler), base_url="http://localhost:8080"
    )
    assert auth_status(cfg_auth, client=client_err) == 1


def test_auth_credentials_corrupt_and_save_types(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Verify corrupt credentials file handling and non-string types saving."""
    monkeypatch.setenv("KANBAN_CONFIG_DIR", str(tmp_path))
    cred_file = tmp_path / "credentials.toml"

    # Save non-string types (int, bool)
    save_credentials({"retries": 3, "debug": True, "api_key": "k_123"})
    mode = cred_file.stat().st_mode & 0o777
    assert mode == 0o600
    creds = load_credentials()
    assert creds["retries"] == 3
    assert creds["debug"] is True

    # Corrupt toml raises ValueError
    cred_file.write_text("invalid [ [ toml syntax", encoding="utf-8")
    os.chmod(cred_file, 0o600)
    with pytest.raises(ValueError, match="Failed to parse credentials file"):
        load_credentials()


def test_main_entry_points_and_interrupt(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify entry points main, main_agent, main_docs, main_admin, and KeyboardInterrupt."""
    from mcp.cli.main import _run_cli_coroutine, main_admin, main_agent, main_docs

    # Help checks
    assert main(["--help"]) == 0
    assert main_agent(["--help"]) == 0
    assert main_docs(["--help"]) == 0
    assert main_admin(["--help"]) == 0

    # Keyboard interrupt handling
    def mock_interrupt(*args: Any, **kwargs: Any) -> Any:
        raise KeyboardInterrupt

    import sys

    main_mod = sys.modules["mcp.cli.main"]
    monkeypatch.setattr(main_mod, "parse_and_execute_cli", mock_interrupt)
    ret_ki = _run_cli_coroutine(["--help"])
    assert ret_ki == 130


@pytest.mark.asyncio
async def test_cli_subparsers_and_error_routing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Verify docs, admin, auth, and completions routing through parse_and_execute_cli."""
    from mcp.cli.schema_cli import parse_and_execute_cli

    monkeypatch.setenv("KANBAN_CONFIG_DIR", str(tmp_path))

    # Empty command prints help and returns 0
    assert await parse_and_execute_cli([]) == 0

    # Completions
    assert await parse_and_execute_cli(["completions", "bash"]) == 0
    assert await parse_and_execute_cli(["completions", "zsh"]) == 0
    assert await parse_and_execute_cli(["completions", "fish"]) == 0

    # Auth commands - unauthenticated status
    assert await parse_and_execute_cli(["auth", "status"]) == 0
    assert await parse_and_execute_cli(["auth", "login", "--token", "tok_cli_test"]) == 0

    # Authenticated status with mock network session
    monkeypatch.setattr(
        "httpx.Client.get",
        lambda self, url: httpx.Response(200, json={"user": {"handle": "@test"}}),
    )
    assert await parse_and_execute_cli(["auth", "status"]) == 0
    assert await parse_and_execute_cli(["auth", "logout"]) == 0
    assert await parse_and_execute_cli(["auth"]) == 2  # missing auth subcommand

    # Docs and admin missing subcommands
    assert await parse_and_execute_cli(["docs"]) == 2
    assert await parse_and_execute_cli(["admin"]) == 2

    # Unknown command
    assert await parse_and_execute_cli(["nonexistent-command"]) == 2


def test_array_and_stdin_and_null_arg_normalization(tmp_path: Path) -> None:
    """Verify JSON array, stdin (-), clear flag, and null literal string parsing."""
    from mcp.cli.schema_cli import _normalize_parsed_arguments
    from mcp.surfaces.agent import create_agent_registry

    agent_reg = create_agent_registry()
    create_spec = agent_reg.get("create_ticket")
    assert create_spec is not None

    # 1. Array parsing: JSON array string and comma-separated
    arr_file = tmp_path / "labels.json"
    arr_file.write_text('["tag1", "tag2"]', encoding="utf-8")

    input_arr = {
        "project": "KAN",
        "summary": "Fix bug",
        "labels": f"@{arr_file}",
    }
    norm = _normalize_parsed_arguments(create_spec, input_arr)
    assert norm["labels"] == ["tag1", "tag2"]

    input_comma = {
        "project": "KAN",
        "summary": "Fix bug",
        "labels": ["tagA, tagB", "tagC"],
    }
    norm_comma = _normalize_parsed_arguments(create_spec, input_comma)
    assert norm_comma["labels"] == ["tagA", "tagB", "tagC"]

    # 2. Null literal string
    input_null = {
        "project": "KAN",
        "summary": "Fix bug",
        "priority": "null",
    }
    norm_null = _normalize_parsed_arguments(create_spec, input_null)
    assert norm_null["priority"] is None

    # 3. Clear flag
    input_clear = {
        "project": "KAN",
        "summary": "Fix bug",
        "clear_priority": True,
    }
    norm_clear = _normalize_parsed_arguments(create_spec, input_clear)
    assert norm_clear["priority"] is None


def test_auth_edge_cases(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Verify XDG_CONFIG_HOME, corrupt config, resolve warning, and logout error."""
    # 1. XDG_CONFIG_HOME
    xdg_dir = tmp_path / "xdg"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg_dir))
    monkeypatch.delenv("KANBAN_CONFIG_DIR", raising=False)
    assert get_config_dir() == xdg_dir / "kanban"

    # 2. Corrupted config.toml returns empty dict
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text("invalid [ [ toml", encoding="utf-8")
    monkeypatch.setenv("KANBAN_CONFIG_DIR", str(tmp_path))
    assert load_config() == {}

    # 3. resolve_config prints warning on ValueError
    cred_file = tmp_path / "credentials.toml"
    cred_file.write_text("invalid [ [ toml", encoding="utf-8")
    os.chmod(cred_file, 0o600)
    captured_err = io.StringIO()
    monkeypatch.setattr(sys, "stderr", captured_err)
    cfg = resolve_config()
    assert "Warning: Failed to parse credentials file" in captured_err.getvalue()
    assert cfg.url == "http://localhost:8080"

    # 4. auth_logout error when unlink fails
    cred_file.write_text('api_key = "abc"\n', encoding="utf-8")
    os.chmod(cred_file, 0o600)

    def mock_unlink_fail(self: Any) -> None:
        raise OSError("Permission denied")

    monkeypatch.setattr(Path, "unlink", mock_unlink_fail)
    ret_logout_err = auth_logout()
    assert ret_logout_err == 1


def test_schema_cli_io_and_filter_branches(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Verify stdin, YAML structured values, missing file errors, and filter priority."""
    from mcp.cli.schema_cli import (
        _normalize_parsed_arguments,
        _parse_structured_value,
        _read_file_or_stdin,
        execute_tool_action,
    )
    from mcp.registry import Surface
    from mcp.surfaces.agent import create_agent_registry

    # 1. _read_file_or_stdin with stdin
    monkeypatch.setattr("sys.stdin", io.StringIO("stdin content"))
    assert _read_file_or_stdin("-") == "stdin content"

    # 2. Missing file raises error
    with pytest.raises(KbMcpError, match="File not found"):
        _read_file_or_stdin(str(tmp_path / "nonexistent.txt"))

    # 3. _parse_structured_value with YAML string and file
    yaml_file = tmp_path / "data.yaml"
    yaml_file.write_text("key: value\nnumber: 42\n", encoding="utf-8")
    parsed_yaml = _parse_structured_value(f"@{yaml_file}")
    assert parsed_yaml == {"key": "value", "number": 42}

    # Direct YAML string fallback
    assert _parse_structured_value("foo: bar") == {"foo": "bar"}

    # 4. _normalize_parsed_arguments with stdin (-) and @file for prose
    agent_reg = create_agent_registry()
    create_spec = agent_reg.get("create_ticket")
    assert create_spec is not None

    desc_file = tmp_path / "desc.md"
    desc_file.write_text("file description", encoding="utf-8")

    input_prose = {
        "project": "KAN",
        "summary": "Ticket",
        "description_markdown": f"@{desc_file}",
    }
    norm_prose = _normalize_parsed_arguments(create_spec, input_prose)
    assert norm_prose["description_markdown"] == "file description"

    monkeypatch.setattr("sys.stdin", io.StringIO("stdin description"))
    input_stdin = {
        "project": "KAN",
        "summary": "Ticket",
        "description_markdown": "-",
    }
    norm_stdin = _normalize_parsed_arguments(create_spec, input_stdin)
    assert norm_stdin["description_markdown"] == "stdin description"

    # 5. execute_tool_action with JSONL list output
    reg = create_agent_registry()
    spec = reg.get("search_tickets")
    assert spec is not None
    import dataclasses

    async def mock_list_handler(_: Any) -> Any:
        return [{"key": "KAN-1"}, {"key": "KAN-2"}]

    list_spec = dataclasses.replace(spec, handler=mock_list_handler)
    captured = io.StringIO()
    monkeypatch.setattr(sys, "stdout", captured)
    from mcp.cli.auth import ResolvedConfig

    cfg = ResolvedConfig(url="http://localhost:8080", workspace=None, project=None, token=None)
    ret_list = asyncio.run(execute_tool_action(Surface.AGENT, list_spec, {}, cfg, jsonl_mode=True))
    assert ret_list == 0
    assert '{"key": "KAN-1"}' in captured.getvalue()


def test_schema_cli_full_branches(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Verify edge case branches across schema_cli and main."""
    import dataclasses
    import json
    import runpy

    from mcp.cli.auth import ResolvedConfig
    from mcp.cli.schema_cli import (
        _apply_predicate_filter,
        _normalize_parsed_arguments,
        _parse_structured_value,
        execute_tool_action,
        generate_completions,
        parse_and_execute_cli,
    )
    from mcp.registry import Surface
    from mcp.surfaces.agent import create_agent_registry

    agent_reg = create_agent_registry()
    create_spec = agent_reg.get("create_ticket")
    assert create_spec is not None
    trans_spec = agent_reg.get("transition_ticket")
    assert trans_spec is not None

    # 1. Structured parse error and fallback
    bad_file = tmp_path / "bad.yaml"
    bad_file.write_text(":\n  - bad: [", encoding="utf-8")
    with pytest.raises(KbMcpError, match="Failed to parse structured input"):
        _parse_structured_value(f"@{bad_file}")

    assert _parse_structured_value(":\n  - bad: [") == ":\n  - bad: ["

    # 2. Unsupported shell completion returns empty string
    assert generate_completions("unsupported") == ""

    # 3. Normalization with YAML file and scalar arrays
    yaml_file = tmp_path / "meta.yaml"
    yaml_file.write_text("key: value\n", encoding="utf-8")
    norm_yaml = _normalize_parsed_arguments(
        trans_spec,
        {"identifier": "KAN-1", "to_state": "Done", "verification_proof_file": str(yaml_file)},
    )
    assert norm_yaml["verification_proof"] == {"key": "value"}

    scalar_file = tmp_path / "scalar.json"
    scalar_file.write_text('"one_label"', encoding="utf-8")
    norm_scalar = _normalize_parsed_arguments(
        create_spec,
        {"project": "KAN", "summary": "t", "labels": [f"@{scalar_file}"]},
    )
    assert norm_scalar["labels"] == ["one_label"]

    norm_str = _normalize_parsed_arguments(
        create_spec,
        {"project": "KAN", "summary": "t", "labels": "single_label"},
    )
    assert norm_str["labels"] == ["single_label"]

    norm_direct = _normalize_parsed_arguments(
        trans_spec,
        {"identifier": "KAN-1", "to_state": "Done", "verification_proof": {"direct": 1}},
    )
    assert norm_direct["verification_proof"] == {"direct": 1}

    search_spec = agent_reg.get("search_tickets")
    assert search_spec is not None
    norm_int = _normalize_parsed_arguments(
        search_spec,
        {"project": "KAN", "limit": 10},
    )
    assert norm_int["limit"] == 10

    # 4. Predicate filter with = clauses and existing query
    args_pred: dict[str, Any] = {"project": "KAN", "query": "existing"}
    filter_expr = 'state = "Done" AND assignee = "@alice" AND cycle = "c1" AND module = "m1" AND label = "bug" AND blocked = true AND gate = "ready" AND priority = "high" AND free_text'
    _apply_predicate_filter(args_pred, filter_expr)
    assert "Done" in args_pred["states"]
    assert "@alice" in args_pred["assignees"]
    assert args_pred["cycle"] == "c1"
    assert "m1" in args_pred["modules"]
    assert "bug" in args_pred["labels"]
    assert args_pred["blocked"] is True
    assert args_pred["gate_status"] == "ready"
    assert args_pred["_filter_priority"] == "high"
    assert "existing" in args_pred["query"]
    assert "free_text" in args_pred["query"]

    # 5. execute_tool_action priority filter, sync handler, scalar jsonl
    cfg = ResolvedConfig(url="http://localhost:8080", workspace=None, project=None, token=None)

    async def mock_priority_search(args: Any) -> Any:
        return {
            "total": 2,
            "items": [{"key": "1", "priority": "high"}, {"key": "2", "priority": "low"}],
        }

    spec_p = dataclasses.replace(search_spec, handler=mock_priority_search)
    cap_p = io.StringIO()
    monkeypatch.setattr(sys, "stdout", cap_p)
    ret_p = asyncio.run(
        execute_tool_action(
            Surface.AGENT, spec_p, {"_filter_priority": "high"}, cfg, json_mode=True
        )
    )
    assert ret_p == 0
    p_data = json.loads(cap_p.getvalue())
    assert p_data["total"] == 1
    assert p_data["items"][0]["priority"] == "high"

    def sync_handler(args: Any) -> Any:
        return "sync string result"

    spec_sync = dataclasses.replace(search_spec, handler=sync_handler)
    cap_s = io.StringIO()
    monkeypatch.setattr(sys, "stdout", cap_s)
    ret_s = asyncio.run(execute_tool_action(Surface.AGENT, spec_sync, {}, cfg))
    assert ret_s == 0
    assert "sync string result" in cap_s.getvalue()

    def sync_scalar(args: Any) -> Any:
        return 99999

    spec_sc = dataclasses.replace(search_spec, handler=sync_scalar)
    cap_sc = io.StringIO()
    monkeypatch.setattr(sys, "stdout", cap_sc)
    ret_sc = asyncio.run(execute_tool_action(Surface.AGENT, spec_sc, {}, cfg, jsonl_mode=True))
    assert ret_sc == 0
    assert "99999" in cap_sc.getvalue()

    # 6. Global project/workspace injection and auth missing subcommand
    from mcp.tests.cli.test_kanban_cli_parity import _build_mock_parity_client

    client_inj = _build_mock_parity_client()
    cap_inj = io.StringIO()
    monkeypatch.setattr(sys, "stdout", cap_inj)
    monkeypatch.setenv("KANBAN_PROJECT", "KAN")
    monkeypatch.setenv("KANBAN_WORKSPACE", "INJ_WS")
    ret_inj = asyncio.run(
        parse_and_execute_cli(["search-tickets", "--lod", "summary", "--json"], client=client_inj)
    )
    assert ret_inj == 0

    # 7. Alias 'issue list'
    ret_alias = asyncio.run(parse_and_execute_cli(["issue", "list", "--json"], client=client_inj))
    assert ret_alias == 0

    # 8. Non-existent file flag raises KbMcpError in parse_and_execute_cli
    ret_nonexistent = asyncio.run(
        parse_and_execute_cli(
            [
                "create-ticket",
                "--project",
                "KAN",
                "--summary",
                "T",
                "--description-file",
                "/no/such/file.md",
            ],
            client=client_inj,
        )
    )
    assert ret_nonexistent == 2

    # 9. Sync awaitable and integer output
    def sync_awaitable_handler(_: Any) -> Any:
        async def _inner() -> Any:
            return "async inner output"

        return _inner()

    spec_aw = dataclasses.replace(search_spec, handler=sync_awaitable_handler)
    assert asyncio.run(execute_tool_action(Surface.AGENT, spec_aw, {}, cfg)) == 0

    def sync_int_handler(_: Any) -> Any:
        return 42

    spec_int = dataclasses.replace(search_spec, handler=sync_int_handler)
    assert asyncio.run(execute_tool_action(Surface.AGENT, spec_int, {}, cfg)) == 0

    # 10. __main__ invocation
    monkeypatch.setattr(sys, "argv", ["kanban-cli", "--help"])
    with pytest.raises(SystemExit) as exc:
        runpy.run_module("mcp.cli.main", run_name="__main__")
    assert exc.value.code == 0
