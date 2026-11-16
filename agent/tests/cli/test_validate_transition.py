# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
# ruff: noqa: E501, ANN401, SLF001, ARG001, PLC0415, PLR0915
"""Feature unit tests for kanban-agent validate-transition CLI workbench (KB-P5-23)."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

import jsonschema
import pytest

from agent.cli import main

_REPO_ROOT = Path(__file__).resolve().parents[3]
_FIXTURES_DIR = _REPO_ROOT / "tests" / "fixtures" / "ai"
_EXAMPLES_AGENTS = _REPO_ROOT / "examples" / "agents"
_EXAMPLES_TICKETS = _REPO_ROOT / "examples" / "tickets"
_SCHEMA_PATH = _REPO_ROOT / "agent" / "schemas" / "kb-validate-transition-report-v1.json"


@pytest.fixture
def tmp_git_repo(tmp_path: Path) -> Path:
    """Create a temporary initialized Git repository with clean commits."""
    repo_dir = tmp_path / "sample_repo"
    repo_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "init", "-b", "main", str(repo_dir)],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test Committer"],
        cwd=repo_dir,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "committer@example.com"],
        cwd=repo_dir,
        check=True,
        capture_output=True,
    )

    (repo_dir / "README.md").write_text("# Test Repository\n", encoding="utf-8")
    db_dir = repo_dir / "database"
    db_dir.mkdir()
    (db_dir / "migration.sql").write_text("-- Initial migration\nSELECT 1;\n", encoding="utf-8")

    subprocess.run(["git", "add", "."], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"],
        cwd=repo_dir,
        check=True,
        capture_output=True,
    )
    return repo_dir


def test_cli_pipe_s15_3_example_1(
    tmp_git_repo: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Test Case 1: Positive cli_pipe running exact flag set from S15.3 example 1."""
    agent_config = str(_EXAMPLES_AGENTS / "agy-gate.yaml")
    ticket_file = str(_EXAMPLES_TICKETS / "kan-142.yaml")
    cassette = str(_FIXTURES_DIR / "cli_agy_approve.yaml")

    exit_code = main(
        [
            "validate-transition",
            "--agent-config",
            agent_config,
            "--ticket-file",
            ticket_file,
            "--repo-path",
            str(tmp_git_repo),
            "--from-state",
            "In Review",
            "--to-state",
            "Done",
            "--print-stdin-context",
            "--verbose-tools",
            "--cassette",
            cassette,
        ]
    )

    captured = capsys.readouterr()
    stdout = captured.out

    assert exit_code == 0
    assert "=== 1. RENDERED CONTEXT ===" in stdout
    assert "=== 2. TOOL TRACE ===" in stdout
    assert "=== 3. LATENCY & TOKENS ===" in stdout
    assert "=== 4. SCHEMA & POLICY STATUS ===" in stdout
    assert "schema: kb-transition-context/v1" in stdout
    assert "decision: approve" in stdout
    assert "Valid: true" in stdout


def test_in_app_sdk_gate(
    tmp_git_repo: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Test Case 2: Positive in_app_sdk executing tool loop, veto verdict, and --require-approve."""
    agent_config = str(_EXAMPLES_AGENTS / "ollama-gate.yaml")
    ticket_file = str(_EXAMPLES_TICKETS / "kan-142.yaml")
    cassette = str(_FIXTURES_DIR / "transition_rls_veto.yaml")
    mcp_fixture = str(_FIXTURES_DIR / "mcp_kan_100_fixture.yaml")

    # 1. Without --require-approve (reject is a valid gate verdict -> exit 0)
    exit_code_normal = main(
        [
            "validate-transition",
            "--agent-config",
            agent_config,
            "--ticket-file",
            ticket_file,
            "--repo-path",
            str(tmp_git_repo),
            "--from-state",
            "In Review",
            "--to-state",
            "Done",
            "--provider",
            "fixture",
            "--cassette",
            cassette,
            "--mcp-fixture",
            mcp_fixture,
        ]
    )

    captured = capsys.readouterr()
    stdout = captured.out

    assert exit_code_normal == 0
    assert "read_ticket" in stdout
    assert "repo_grep" in stdout
    assert "decision: reject" in stdout
    assert "Valid: true" in stdout

    # 2. With --require-approve (reject is treated as gate failure -> exit 2)
    exit_code_req = main(
        [
            "validate-transition",
            "--agent-config",
            agent_config,
            "--ticket-file",
            ticket_file,
            "--repo-path",
            str(tmp_git_repo),
            "--from-state",
            "In Review",
            "--to-state",
            "Done",
            "--provider",
            "fixture",
            "--cassette",
            cassette,
            "--mcp-fixture",
            mcp_fixture,
            "--require-approve",
        ]
    )

    captured_req = capsys.readouterr()
    assert exit_code_req == 2
    assert "REJECT_NOT_PERMITTED" in captured_req.out


def test_remote_runner_loopback(
    tmp_git_repo: Path,
    capsys: pytest.CaptureFixture[str],
    socket_enabled: Any,
) -> None:
    """Test Case 3: Positive remote_runner loopback over TLS 1.3 mTLS WSS frames."""
    agent_config = str(_EXAMPLES_AGENTS / "remote-gate.yaml")
    ticket_file = str(_EXAMPLES_TICKETS / "kan-142.yaml")
    cassette = str(_FIXTURES_DIR / "cli_codex_readonly_veto.yaml")

    exit_code = main(
        [
            "validate-transition",
            "--agent-config",
            agent_config,
            "--ticket-file",
            ticket_file,
            "--repo-path",
            str(tmp_git_repo),
            "--from-state",
            "In Review",
            "--to-state",
            "Done",
            "--remote-loopback",
            "--cassette",
            cassette,
        ]
    )

    captured = capsys.readouterr()
    stdout = captured.out

    assert exit_code == 0
    assert "=== 1. RENDERED CONTEXT ===" in stdout
    assert "=== 4. SCHEMA & POLICY STATUS ===" in stdout
    assert "decision: reject" in stdout
    assert "Valid: true" in stdout


def test_security_banned_flags_and_secret_masking(
    tmp_path: Path,
    tmp_git_repo: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Test Case 4: Security policy double-gate and strict secret scrubbing."""
    # 1. Banned flag --yolo
    cfg_yolo = tmp_path / "yolo_agent.yaml"
    cfg_yolo.write_text(
        "slug: yolo-agent\ncli_binary_allowlist_id: agy\ncli_args: ['--yolo']\n",
        encoding="utf-8",
    )
    ticket_file = str(_EXAMPLES_TICKETS / "kan-142.yaml")

    code_yolo = main(
        [
            "validate-transition",
            "--agent-config",
            str(cfg_yolo),
            "--ticket-file",
            ticket_file,
            "--from-state",
            "In Review",
            "--to-state",
            "Done",
        ]
    )
    assert code_yolo == 2
    out_yolo = capsys.readouterr().out
    assert "BANNED_CLI_FLAG" in out_yolo

    # 2. Codex sandbox override (missing -s read-only)
    cfg_codex = tmp_path / "unsafe_codex.yaml"
    cfg_codex.write_text(
        "slug: unsafe-codex\ncli_binary_allowlist_id: codex\ncli_args: ['-p']\n",
        encoding="utf-8",
    )
    code_codex = main(
        [
            "validate-transition",
            "--agent-config",
            str(cfg_codex),
            "--ticket-file",
            ticket_file,
            "--from-state",
            "In Review",
            "--to-state",
            "Done",
        ]
    )
    assert code_codex == 2
    out_codex = capsys.readouterr().out
    assert "CODEX_SANDBOX_OVERRIDE" in out_codex

    # 3. Secret masking: ghp_ token in ticket body must be scrubbed completely
    raw_token = "ghp_1234567890abcdef1234567890abcdef1234"
    secret_ticket = tmp_path / "secret_ticket.yaml"
    secret_ticket.write_text(
        f"id: KAN-142\ntitle: Auth Leak\ndescription_markdown: Secret key is {raw_token}\n",
        encoding="utf-8",
    )

    code_secret = main(
        [
            "validate-transition",
            "--agent-config",
            str(_EXAMPLES_AGENTS / "agy-gate.yaml"),
            "--ticket-file",
            str(secret_ticket),
            "--repo-path",
            str(tmp_git_repo),
            "--from-state",
            "In Review",
            "--to-state",
            "Done",
            "--print-stdin-context",
            "--cassette",
            str(_FIXTURES_DIR / "cli_agy_approve.yaml"),
        ]
    )
    assert code_secret == 0
    out_secret = capsys.readouterr().out
    assert raw_token not in out_secret
    assert "[REDACTED" in out_secret


def test_security_repo_immutability(
    tmp_git_repo: Path,
    capsys: pytest.CaptureFixture[str],
    socket_enabled: Any,
) -> None:
    """Test Case 5: Verify git status and working tree file mtimes are unmodified."""

    def _get_working_tree_mtimes(repo_dir: Path) -> dict[str, int]:
        mtimes: dict[str, int] = {}
        for root, dirs, files in os.walk(repo_dir):
            if ".git" in dirs:
                dirs.remove(".git")
            for f in files:
                fpath = Path(root) / f
                mtimes[str(fpath.relative_to(repo_dir))] = fpath.stat().st_mtime_ns
        return mtimes

    status_before = subprocess.check_output(["git", "status", "--porcelain"], cwd=tmp_git_repo)
    mtimes_before = _get_working_tree_mtimes(tmp_git_repo)

    # 1. Execute cli_pipe
    code_1 = main(
        [
            "validate-transition",
            "--agent-config",
            str(_EXAMPLES_AGENTS / "agy-gate.yaml"),
            "--ticket-file",
            str(_EXAMPLES_TICKETS / "kan-142.yaml"),
            "--repo-path",
            str(tmp_git_repo),
            "--from-state",
            "In Review",
            "--to-state",
            "Done",
            "--cassette",
            str(_FIXTURES_DIR / "cli_agy_approve.yaml"),
        ]
    )
    assert code_1 == 0
    capsys.readouterr()

    # 2. Execute in_app_sdk
    code_2 = main(
        [
            "validate-transition",
            "--agent-config",
            str(_EXAMPLES_AGENTS / "ollama-gate.yaml"),
            "--ticket-file",
            str(_EXAMPLES_TICKETS / "kan-142.yaml"),
            "--repo-path",
            str(tmp_git_repo),
            "--from-state",
            "In Review",
            "--to-state",
            "Done",
            "--provider",
            "fixture",
            "--cassette",
            str(_FIXTURES_DIR / "transition_rls_veto.yaml"),
            "--mcp-fixture",
            str(_FIXTURES_DIR / "mcp_kan_100_fixture.yaml"),
        ]
    )
    assert code_2 == 0
    capsys.readouterr()

    # 3. Execute remote_runner
    code_3 = main(
        [
            "validate-transition",
            "--agent-config",
            str(_EXAMPLES_AGENTS / "remote-gate.yaml"),
            "--ticket-file",
            str(_EXAMPLES_TICKETS / "kan-142.yaml"),
            "--repo-path",
            str(tmp_git_repo),
            "--from-state",
            "In Review",
            "--to-state",
            "Done",
            "--remote-loopback",
            "--cassette",
            str(_FIXTURES_DIR / "cli_codex_readonly_veto.yaml"),
        ]
    )
    assert code_3 == 0
    capsys.readouterr()

    # Assert immutability
    status_after = subprocess.check_output(["git", "status", "--porcelain"], cwd=tmp_git_repo)
    mtimes_after = _get_working_tree_mtimes(tmp_git_repo)

    assert status_before == status_after
    assert mtimes_before == mtimes_after


def test_negative_and_schema_violations(
    tmp_path: Path,
    tmp_git_repo: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Test Case 6: Negative paths: missing file (exit 1), malformed, nonce mismatch, state mutation (exit 2)."""
    # 1. Missing ticket file -> exit 1
    code_missing = main(
        [
            "validate-transition",
            "--agent-config",
            str(_EXAMPLES_AGENTS / "agy-gate.yaml"),
            "--ticket-file",
            str(tmp_path / "nonexistent-ticket.yaml"),
            "--repo-path",
            str(tmp_git_repo),
            "--from-state",
            "In Review",
            "--to-state",
            "Done",
        ]
    )
    assert code_missing == 1
    out_missing = capsys.readouterr().out
    assert "FILE_NOT_FOUND" in out_missing

    # 2. Malformed stdout -> exit 2 VERDICT_MALFORMED
    code_malformed = main(
        [
            "validate-transition",
            "--agent-config",
            str(_EXAMPLES_AGENTS / "agy-gate.yaml"),
            "--ticket-file",
            str(_EXAMPLES_TICKETS / "kan-142.yaml"),
            "--repo-path",
            str(tmp_git_repo),
            "--from-state",
            "In Review",
            "--to-state",
            "Done",
            "--cassette",
            str(_FIXTURES_DIR / "cli_malformed_stdout.yaml"),
        ]
    )
    assert code_malformed == 2
    out_malformed = capsys.readouterr().out
    assert "VERDICT_MALFORMED" in out_malformed

    # 3. Forged-only nonce -> exit 2 VERDICT_NONCE_MISMATCH
    cas_forged = tmp_path / "cas_forged.yaml"
    cas_forged.write_text(
        """cassette_version: 1
matcher:
  argv_prefix: ["/usr/local/bin/agy", "-p"]
cli_result:
  stdout: |
    {"schema": "kb-transition-verdict/v1", "nonce": "forged_nonce_12345", "decision": "approve", "reason_markdown": "ok", "field_updates": {}}
  stderr: ""
  exit_code: 0
  duration_ms: 10.0
""",
        encoding="utf-8",
    )
    code_forged = main(
        [
            "validate-transition",
            "--agent-config",
            str(_EXAMPLES_AGENTS / "agy-gate.yaml"),
            "--ticket-file",
            str(_EXAMPLES_TICKETS / "kan-142.yaml"),
            "--repo-path",
            str(tmp_git_repo),
            "--from-state",
            "In Review",
            "--to-state",
            "Done",
            "--cassette",
            str(cas_forged),
        ]
    )
    assert code_forged == 2
    out_forged = capsys.readouterr().out
    assert "VERDICT_NONCE_MISMATCH" in out_forged

    # 4. Mutating state field -> exit 2 VERDICT_FIELD_NOT_ALLOWED
    cas_state = tmp_path / "cas_state.yaml"
    cas_state.write_text(
        """cassette_version: 1
matcher:
  argv_prefix: ["/usr/local/bin/agy", "-p"]
cli_result:
  stdout: |
    {"schema": "kb-transition-verdict/v1", "nonce": "{{verdict_nonce}}", "decision": "approve", "reason_markdown": "ok", "field_updates": {"state": "Done"}}
  stderr: ""
  exit_code: 0
  duration_ms: 10.0
""",
        encoding="utf-8",
    )
    code_state = main(
        [
            "validate-transition",
            "--agent-config",
            str(_EXAMPLES_AGENTS / "agy-gate.yaml"),
            "--ticket-file",
            str(_EXAMPLES_TICKETS / "kan-142.yaml"),
            "--repo-path",
            str(tmp_git_repo),
            "--from-state",
            "In Review",
            "--to-state",
            "Done",
            "--cassette",
            str(cas_state),
        ]
    )
    assert code_state == 2
    out_state = capsys.readouterr().out
    assert "VERDICT_FIELD_NOT_ALLOWED" in out_state


def test_boundary_json_schema_validation(
    tmp_git_repo: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Test Case 7: Boundary --report json output validates strictly against JSON Schema."""
    agent_config = str(_EXAMPLES_AGENTS / "ollama-gate.yaml")
    ticket_file = str(_EXAMPLES_TICKETS / "kan-142.yaml")
    cassette = str(_FIXTURES_DIR / "transition_rls_veto.yaml")
    mcp_fixture = str(_FIXTURES_DIR / "mcp_kan_100_fixture.yaml")

    code_json = main(
        [
            "validate-transition",
            "--agent-config",
            agent_config,
            "--ticket-file",
            ticket_file,
            "--repo-path",
            str(tmp_git_repo),
            "--from-state",
            "In Review",
            "--to-state",
            "Done",
            "--provider",
            "fixture",
            "--cassette",
            cassette,
            "--mcp-fixture",
            mcp_fixture,
            "--report",
            "json",
        ]
    )
    assert code_json == 0

    captured = capsys.readouterr()
    report_data = json.loads(captured.out)

    schema = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
    jsonschema.validate(report_data, schema)

    assert report_data["schema_version"] == "kb-validate-transition-report/v1"
    assert report_data["command"] == "validate-transition"
    assert report_data["schema_status"]["valid"] is True
    assert report_data["schema_status"]["status"] == "passed"
    assert report_data["transition_details"]["harness"] == "in_app_sdk"
    assert report_data["transition_details"]["verdict"]["decision"] == "reject"


def test_cli_error_branches(tmp_path: Path, tmp_git_repo: Path) -> None:
    """Test error handling branches for config, tickets, and harness kinds."""
    # 1. Invalid YAML in agent config
    bad_cfg = tmp_path / "bad_cfg.yaml"
    bad_cfg.write_text("invalid: [yaml\n", encoding="utf-8")
    assert (
        main(
            [
                "validate-transition",
                "--agent-config",
                str(bad_cfg),
                "--ticket-file",
                str(_EXAMPLES_TICKETS / "kan-142.yaml"),
                "--from-state",
                "In Review",
                "--to-state",
                "Done",
            ]
        )
        == 1
    )

    # 2. Non-dict YAML in agent config
    non_dict_cfg = tmp_path / "non_dict.yaml"
    non_dict_cfg.write_text("- not a dict\n", encoding="utf-8")
    assert (
        main(
            [
                "validate-transition",
                "--agent-config",
                str(non_dict_cfg),
                "--ticket-file",
                str(_EXAMPLES_TICKETS / "kan-142.yaml"),
                "--from-state",
                "In Review",
                "--to-state",
                "Done",
            ]
        )
        == 1
    )

    # 3. Invalid YAML in ticket file
    bad_ticket = tmp_path / "bad_ticket.yaml"
    bad_ticket.write_text("invalid: [yaml\n", encoding="utf-8")
    assert (
        main(
            [
                "validate-transition",
                "--agent-config",
                str(_EXAMPLES_AGENTS / "agy-gate.yaml"),
                "--ticket-file",
                str(bad_ticket),
                "--from-state",
                "In Review",
                "--to-state",
                "Done",
            ]
        )
        == 1
    )

    # 4. Non-dict YAML in ticket file
    non_dict_ticket = tmp_path / "non_dict_ticket.yaml"
    non_dict_ticket.write_text("- item\n", encoding="utf-8")
    assert (
        main(
            [
                "validate-transition",
                "--agent-config",
                str(_EXAMPLES_AGENTS / "agy-gate.yaml"),
                "--ticket-file",
                str(non_dict_ticket),
                "--repo-path",
                str(tmp_git_repo),
                "--from-state",
                "In Review",
                "--to-state",
                "Done",
                "--cassette",
                str(_FIXTURES_DIR / "cli_agy_approve.yaml"),
            ]
        )
        == 0
    )

    # 5. Missing repo path when repo_access_mode != 'none'
    assert (
        main(
            [
                "validate-transition",
                "--agent-config",
                str(_EXAMPLES_AGENTS / "agy-gate.yaml"),
                "--ticket-file",
                str(_EXAMPLES_TICKETS / "kan-142.yaml"),
                "--from-state",
                "In Review",
                "--to-state",
                "Done",
            ]
        )
        == 1
    )

    # 6. Nonexistent repo path
    assert (
        main(
            [
                "validate-transition",
                "--agent-config",
                str(_EXAMPLES_AGENTS / "agy-gate.yaml"),
                "--ticket-file",
                str(_EXAMPLES_TICKETS / "kan-142.yaml"),
                "--repo-path",
                str(tmp_path / "does_not_exist"),
                "--from-state",
                "In Review",
                "--to-state",
                "Done",
            ]
        )
        == 1
    )

    # 7. Unknown harness kind
    unknown_harness_cfg = tmp_path / "unknown_harness.yaml"
    unknown_harness_cfg.write_text("slug: unknown\nharness_kind: bogus_harness\n", encoding="utf-8")
    assert (
        main(
            [
                "validate-transition",
                "--agent-config",
                str(unknown_harness_cfg),
                "--ticket-file",
                str(_EXAMPLES_TICKETS / "kan-142.yaml"),
                "--from-state",
                "In Review",
                "--to-state",
                "Done",
            ]
        )
        == 1
    )

    # 8. Remote runner without --remote-loopback
    assert (
        main(
            [
                "validate-transition",
                "--agent-config",
                str(_EXAMPLES_AGENTS / "remote-gate.yaml"),
                "--ticket-file",
                str(_EXAMPLES_TICKETS / "kan-142.yaml"),
                "--repo-path",
                str(tmp_git_repo),
                "--from-state",
                "In Review",
                "--to-state",
                "Done",
            ]
        )
        == 1
    )

    # 9. Markdown ticket with frontmatter and description
    md_ticket = tmp_path / "ticket.md"
    md_ticket.write_text(
        "---\nid: KAN-99\ntitle: MD Ticket\ndescription: Custom desc\nactor: '@tester'\n---\nBody markdown here",
        encoding="utf-8",
    )
    assert (
        main(
            [
                "validate-transition",
                "--agent-config",
                str(_EXAMPLES_AGENTS / "agy-gate.yaml"),
                "--ticket-file",
                str(md_ticket),
                "--repo-path",
                str(tmp_git_repo),
                "--from-state",
                "In Review",
                "--to-state",
                "Done",
                "--cassette",
                str(_FIXTURES_DIR / "cli_agy_approve.yaml"),
            ]
        )
        == 0
    )


async def test_direct_handler_and_helpers(tmp_path: Path, tmp_git_repo: Path) -> None:
    """Test helper functions and direct namespace validation without CLI runner."""
    import argparse
    from unittest.mock import AsyncMock, patch

    from agent.cli_commands.validate_transition import (
        ExplicitFixtureCLIRunner,
        ExplicitFixtureLLMProvider,
        _build_mcp_fixture_transport,
        _parse_ticket_file,
        _resolve_head_commit,
        handle_validate_transition,
    )
    from agent.testing.fixtures import load_cassette

    # 1. Multiple cassettes in ExplicitFixture providers
    cas1 = load_cassette(str(_FIXTURES_DIR / "cli_agy_approve.yaml"))
    cas2 = load_cassette(str(_FIXTURES_DIR / "cli_malformed_stdout.yaml"))
    llm_prov = ExplicitFixtureLLMProvider([cas1, cas2])
    match_llm = llm_prov._find_matching_cassette(
        model="dummy", prompt="", metadata={"agent_slug": "forensic-code-check"}
    )
    assert match_llm is not None

    cli_prov = ExplicitFixtureCLIRunner([cas1, cas2])
    match_cli = cli_prov._find_matching_cassette(
        argv=("/usr/local/bin/agy", "-p"), stdin_str="schema: kb-transition-context/v1"
    )
    assert match_cli is not None

    # 2. _resolve_head_commit branches
    # 2a. Valid repo
    assert len(_resolve_head_commit(tmp_git_repo, "HEAD")) == 40

    # 2b. Nonexistent git_dir
    assert len(_resolve_head_commit(tmp_path / "completely_nonexistent", "HEAD")) == 40

    # 2c. Subprocess OSError trigger
    with patch("subprocess.run", side_effect=OSError("Disk error")):
        assert len(_resolve_head_commit(tmp_git_repo, "HEAD")) == 40

    # 3. _build_mcp_fixture_transport branches
    mcp_data = {
        "dict_tool": {
            "val1": {"result": "ok_val1"},
            "default": {"result": "ok_default"},
        },
        "dict_tool_no_default": {
            "key1": {"result": "ok_key1"},
        },
        "scalar_tool": "scalar_result",
    }
    t = _build_mcp_fixture_transport(mcp_data)
    # Match candidate key
    assert t("url", "dict_tool", {"ticket_id": "val1"}) == {"result": "ok_val1"}
    # Match default
    assert t("url", "dict_tool", {"other": "val"}) == {"result": "ok_default"}
    # Dict without default and no match
    assert t("url", "dict_tool_no_default", {"other": "val"}) == {"key1": {"result": "ok_key1"}}
    # Scalar tool section
    assert t("url", "scalar_tool", {}) == "scalar_result"
    # Unknown tool
    assert t("url", "unknown", {})["tool"] == "unknown"

    # 4. _parse_ticket_file branches
    # 4a. Frontmatter with non-dict YAML
    bad_fm = tmp_path / "bad_fm.md"
    bad_fm.write_text("---\njust a string\n---\nbody text", encoding="utf-8")
    td1 = _parse_ticket_file(bad_fm)
    assert td1["description_markdown"] == "body text"

    # 4b. Incomplete frontmatter (< 3 parts)
    incomplete_fm = tmp_path / "incomplete_fm.md"
    incomplete_fm.write_text("---\nincomplete frontmatter", encoding="utf-8")
    td_inc = _parse_ticket_file(incomplete_fm)
    assert td_inc["description_markdown"] == "---\nincomplete frontmatter"

    # 4c. Plain markdown without frontmatter
    plain_md = tmp_path / "plain.md"
    plain_md.write_text("plain body text", encoding="utf-8")
    td2 = _parse_ticket_file(plain_md)
    assert td2["description_markdown"] == "plain body text"

    # 4d. YAML with description_markdown
    yaml_desc = tmp_path / "desc.yaml"
    yaml_desc.write_text("description_markdown: custom markdown\n", encoding="utf-8")
    td3 = _parse_ticket_file(yaml_desc)
    assert td3["description_markdown"] == "custom markdown"

    # 5. Direct handle_validate_transition error branches
    # 5a. Missing agent_config
    args_empty = argparse.Namespace()
    _, code1 = await handle_validate_transition(args_empty)
    assert code1 == 1

    # 5b. agent_config is directory
    args_dir = argparse.Namespace(agent_config=str(tmp_path))
    _, code_dir = await handle_validate_transition(args_dir)
    assert code_dir == 1

    # 5c. ticket_file is missing, directory, or does not exist
    valid_cfg = str(_EXAMPLES_AGENTS / "agy-gate.yaml")
    args_no_tf = argparse.Namespace(agent_config=valid_cfg)
    _, code_no_tf = await handle_validate_transition(args_no_tf)
    assert code_no_tf == 1

    args_tf_dir = argparse.Namespace(agent_config=valid_cfg, ticket_file=str(tmp_path))
    _, code_tf_dir = await handle_validate_transition(args_tf_dir)
    assert code_tf_dir == 1

    args_tf_missing = argparse.Namespace(
        agent_config=valid_cfg,
        ticket_file=str(tmp_path / "missing_ticket.yaml"),
    )
    _, code_tf_missing = await handle_validate_transition(args_tf_missing)
    assert code_tf_missing == 1

    # 5d. mcp_fixture is missing
    valid_tf = str(_EXAMPLES_TICKETS / "kan-142.yaml")
    args_bad_mcp = argparse.Namespace(
        agent_config=valid_cfg,
        ticket_file=valid_tf,
        mcp_fixture=str(tmp_path / "nonexistent.yaml"),
    )
    _, code_bad_mcp = await handle_validate_transition(args_bad_mcp)
    assert code_bad_mcp == 1

    # 5e. cassette is missing
    args_bad_cas = argparse.Namespace(
        agent_config=valid_cfg,
        ticket_file=valid_tf,
        cassette=str(tmp_path / "nonexistent.yaml"),
    )
    _, code_bad_cas = await handle_validate_transition(args_bad_cas)
    assert code_bad_cas == 1

    # 5f. unknown harness kind
    bad_harness_cfg = tmp_path / "unknown_harness.yaml"
    bad_harness_cfg.write_text("harness: unknown_harness\n", encoding="utf-8")
    args_unknown_harness = argparse.Namespace(
        agent_config=str(bad_harness_cfg),
        ticket_file=valid_tf,
        from_state="In Review",
        to_state="Done",
    )
    _, code_unk_harness = await handle_validate_transition(args_unknown_harness)
    assert code_unk_harness == 1

    # 5g. in_app_sdk without cassette and without mcp_fixture (mock InAppSdkHarness)
    from unittest.mock import MagicMock

    in_app_cfg = str(_EXAMPLES_AGENTS / "ollama-gate.yaml")

    async def fake_verdict_run(ctx: Any, *args: Any, **kwargs: Any) -> bytes:
        return json.dumps(
            {
                "schema": "kb-transition-verdict/v1",
                "nonce": ctx.verdict_nonce,
                "decision": "approve",
                "reason_markdown": "ok",
            }
        ).encode("utf-8")

    with patch("agent.cli_commands.validate_transition.InAppSdkHarness") as mock_harness_cls:
        instance = mock_harness_cls.return_value
        instance.run = AsyncMock(side_effect=fake_verdict_run)
        instance.last_tool_traces = []
        instance.last_report = MagicMock(prompt_tokens=42, completion_tokens=15)
        args_in_app = argparse.Namespace(
            agent_config=in_app_cfg,
            ticket_file=valid_tf,
            repo_path=str(tmp_path),
            from_state="In Review",
            to_state="Done",
        )
        rep, code_in_app = await handle_validate_transition(args_in_app)
        assert code_in_app == 0, (
            f"Error: {rep.schema_status.error_code}: {rep.schema_status.detail}"
        )

    # 5h. cli_pipe without cassette (mock CliPipeHarness)
    with patch("agent.cli_commands.validate_transition.CliPipeHarness") as mock_cli_cls:
        instance = mock_cli_cls.return_value
        instance.run = AsyncMock(side_effect=fake_verdict_run)
        args_cli = argparse.Namespace(
            agent_config=valid_cfg,
            ticket_file=valid_tf,
            repo_path=str(tmp_path),
            from_state="In Review",
            to_state="Done",
        )
        _, code_cli = await handle_validate_transition(args_cli)
        assert code_cli == 0

    # 5i. remote_runner without remote_loopback (mock RemoteRunnerHarness)
    remote_cfg = str(_EXAMPLES_AGENTS / "remote-gate.yaml")
    with patch("agent.cli_commands.validate_transition.RemoteRunnerHarness") as mock_rem_cls:
        instance = mock_rem_cls.return_value
        instance.run = AsyncMock(side_effect=fake_verdict_run)
        args_rem = argparse.Namespace(
            agent_config=remote_cfg,
            ticket_file=valid_tf,
            repo_path=str(tmp_path),
            from_state="In Review",
            to_state="Done",
            remote_loopback=False,
        )
        _, code_rem = await handle_validate_transition(args_rem)
        assert code_rem == 0
