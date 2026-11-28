# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
# ruff: noqa: E501, PLR0915, RUF059, PLC0415, TRY003, EM101, TC003
"""Feature unit tests for BareGitRepoToolkit (KB-P5-20)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from agent.context.transition_context import RepoContext
from agent.tools.repo_path_guard import RepoToolPolicyError
from agent.tools.repo_tools import BareGitRepoToolkit, _cap_and_scrub


@pytest.fixture
def bare_repo_fixture(tmp_path: Path) -> tuple[Path, str, str, str]:
    """Create a real bare Git repository with source, secrets, binary, and 3 commits.

    Returns:
        (bare_mirror_path, commit1_sha, commit2_sha, commit3_sha)

    """
    work = tmp_path / "work"
    work.mkdir()

    def run_git(*args: str) -> str:
        res = subprocess.run(
            ["git", *args],
            cwd=work,
            check=True,
            capture_output=True,
            text=True,
        )
        return res.stdout.strip()

    run_git("init")
    run_git("config", "user.name", "Test Committer")
    run_git("config", "user.email", "test@example.com")
    run_git("config", "commit.gpgsign", "false")

    # Commit 1: Sources, secrets, binary, and embedded credential
    (work / "src").mkdir(parents=True)
    (work / "src" / "main.py").write_text("print('Commit 1 main')\n", encoding="utf-8")

    (work / "database").mkdir(parents=True)
    (work / "database" / "schema.sql").write_text(
        "CREATE TABLE users (id INT PRIMARY KEY);\n-- FORCE ROW LEVEL SECURITY\n",
        encoding="utf-8",
    )

    (work / "certs").mkdir(parents=True)
    (work / "certs" / "server.key").write_text(
        "-----BEGIN PRIVATE KEY-----\nMIIEvgIBADANBgkqhkiG9w0BAQEFAASC\n-----END PRIVATE KEY-----\n",
        encoding="utf-8",
    )

    (work / ".env.production").write_text(
        "DATABASE_URL=postgres://user:secret@localhost:5432/prod\n",
        encoding="utf-8",
    )

    (work / "assets").mkdir(parents=True)
    # Binary PNG containing NUL byte
    (work / "assets" / "logo.png").write_bytes(
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    )

    (work / "app_tokens.py").write_text(
        'GITHUB_TOKEN = "ghp_111122223333444455556666777788889999"\n',
        encoding="utf-8",
    )

    run_git("add", ".")
    run_git("commit", "-m", "Initial commit with mixed files")
    c1 = run_git("rev-parse", "HEAD")

    # Commit 2: Update source and add documentation
    (work / "src" / "main.py").write_text(
        "print('Commit 1 main')\nprint('Commit 2 update')\n", encoding="utf-8"
    )
    (work / "docs").mkdir(parents=True)
    (work / "docs" / "ARCHITECTURE.md").write_text(
        "# Architecture\nRead-only bare git.\n", encoding="utf-8"
    )
    run_git("add", ".")
    run_git("commit", "-m", "Add docs and update main")
    c2 = run_git("rev-parse", "HEAD")

    # Commit 3: Add new app module
    (work / "src" / "app.py").write_text("def app():\n    return 'OK'\n", encoding="utf-8")
    run_git("add", ".")
    run_git("commit", "-m", "Add app module")
    c3 = run_git("rev-parse", "HEAD")

    # Clone bare mirror
    bare_path = tmp_path / "repo.git"
    subprocess.run(
        ["git", "clone", "--bare", str(work), str(bare_path)],
        check=True,
        capture_output=True,
    )

    return bare_path, c1, c2, c3


async def test_repo_toolkit_positive_tools(bare_repo_fixture: tuple[Path, str, str, str]) -> None:
    """Test Case 2: All 5 bare-Git tools return accurate commit-pinned content."""
    bare_path, c1, c2, c3 = bare_repo_fixture
    toolkit = BareGitRepoToolkit(mirror_path=bare_path, head_commit=c3)

    # 1. repo_tree
    tree_out = await toolkit.repo_tree(path="", max_depth=3)
    assert "src/main.py" in tree_out
    assert "src/app.py" in tree_out
    assert "database/schema.sql" in tree_out
    # Asserts secret paths omitted
    assert ".env.production" not in tree_out
    assert "certs/server.key" not in tree_out

    # 2. repo_read_file
    file_out = await toolkit.repo_read_file("src/app.py", start_line=1, end_line=10)
    assert "def app():" in file_out
    assert "   1 | def app():" in file_out

    # 3. repo_grep
    grep_out = await toolkit.repo_grep("FORCE ROW LEVEL SECURITY", path="database/")
    assert "database/schema.sql" in grep_out
    assert "FORCE ROW LEVEL SECURITY" in grep_out
    # Asserts commit sha prefix stripped
    assert c3 not in grep_out

    # 4. repo_git_log
    log_out = await toolkit.repo_git_log(max_commits=10)
    assert "Add app module" in log_out
    assert "Add docs and update main" in log_out
    assert "Initial commit with mixed files" in log_out

    # 5. repo_git_diff
    diff_out = await toolkit.repo_git_diff(base_ref=c2)
    assert "src/app.py" in diff_out
    assert "+def app():" in diff_out


async def test_repo_toolkit_security_traversal_and_injection(
    bare_repo_fixture: tuple[Path, str, str, str],
    tmp_path: Path,
) -> None:
    """Test Case 3: Traversal and option injections are rejected; zero canary files created."""
    bare_path, _, _, c3 = bare_repo_fixture
    toolkit = BareGitRepoToolkit(mirror_path=bare_path, head_commit=c3)

    # Traversal in read_file
    with pytest.raises(RepoToolPolicyError) as exc_info:
        await toolkit.repo_read_file("../etc/passwd")
    assert exc_info.value.code == "REPO_PATH_INVALID"

    with pytest.raises(RepoToolPolicyError) as exc_info:
        await toolkit.repo_read_file("/etc/shadow")
    assert exc_info.value.code == "REPO_PATH_INVALID"

    # Option injection in repo_grep
    grep_res = await toolkit.repo_grep("--open-files-in-pager=sh", path="")
    assert grep_res == ""  # Treated as literal string with -e, no pager triggered

    # Option injection in repo_git_diff
    canary_file = tmp_path / "pwn"
    with pytest.raises(RepoToolPolicyError) as exc_info:
        await toolkit.repo_git_diff(f"--output={canary_file}")
    assert exc_info.value.code == "REPO_PATH_INVALID"
    assert not canary_file.exists()


async def test_repo_toolkit_secret_masking_and_scrubbing(
    bare_repo_fixture: tuple[Path, str, str, str],
) -> None:
    """Test Case 4: Secrets excluded from tree, grep, diff, and direct access blocked."""
    bare_path, c1, _, c3 = bare_repo_fixture
    toolkit = BareGitRepoToolkit(mirror_path=bare_path, head_commit=c3)

    # Direct read attempts raise REPO_SECRET_PATH_DENIED
    with pytest.raises(RepoToolPolicyError) as exc_info:
        await toolkit.repo_read_file(".env.production")
    assert exc_info.value.code == "REPO_SECRET_PATH_DENIED"

    with pytest.raises(RepoToolPolicyError) as exc_info:
        await toolkit.repo_read_file("certs/server.key")
    assert exc_info.value.code == "REPO_SECRET_PATH_DENIED"

    # repo_tree omits secrets
    tree_out = await toolkit.repo_tree()
    assert ".env" not in tree_out
    assert "server.key" not in tree_out

    # repo_grep omits secrets
    grep_env = await toolkit.repo_grep("DATABASE_URL")
    assert grep_env == ""
    assert ".env.production" not in grep_env

    grep_key = await toolkit.repo_grep("PRIVATE KEY")
    assert grep_key == ""
    assert "certs/server.key" not in grep_key

    # repo_git_diff from initial commit omits secret files
    diff_out = await toolkit.repo_git_diff(base_ref=c1)
    assert ".env.production" not in diff_out
    assert "server.key" not in diff_out

    # In-file credential scrubbing: ghp_ token in app_tokens.py is redacted
    secrets_read = await toolkit.repo_read_file("app_tokens.py")
    assert "ghp_111122223333444455556666777788889999" not in secrets_read
    assert "[REDACTED_GITHUB_TOKEN]" in secrets_read or "REDACTED" in secrets_read


async def test_repo_toolkit_binary_and_boundary_checks(
    bare_repo_fixture: tuple[Path, str, str, str],
) -> None:
    """Test Case 6: Binary file read returns REPO_BINARY_FILE_UNSUPPORTED and invalid ranges fail."""
    bare_path, _, _, c3 = bare_repo_fixture
    toolkit = BareGitRepoToolkit(mirror_path=bare_path, head_commit=c3)

    # Binary file read raises REPO_BINARY_FILE_UNSUPPORTED
    with pytest.raises(RepoToolPolicyError) as exc_info:
        await toolkit.repo_read_file("assets/logo.png")
    assert exc_info.value.code == "REPO_BINARY_FILE_UNSUPPORTED"

    # Non-existent file
    with pytest.raises(RepoToolPolicyError) as exc_info:
        await toolkit.repo_read_file("nonexistent.py")
    assert exc_info.value.code == "REPO_FILE_NOT_FOUND"

    # Line range boundaries
    with pytest.raises(RepoToolPolicyError) as exc_info:
        await toolkit.repo_read_file("src/main.py", start_line=10, end_line=5)
    assert exc_info.value.code == "REPO_PATH_INVALID"

    with pytest.raises(RepoToolPolicyError) as exc_info:
        await toolkit.repo_read_file("src/main.py", start_line=1, end_line=500)
    assert exc_info.value.code == "REPO_PATH_INVALID"

    # Grep pattern length boundary
    with pytest.raises(RepoToolPolicyError) as exc_info:
        await toolkit.repo_grep("x" * 201)
    assert exc_info.value.code == "REPO_GREP_PATTERN_INVALID"


def test_repo_toolkit_initialization_validation(tmp_path: Path) -> None:
    """Toolkit validates mirror existence and commit hash format."""
    non_existent = tmp_path / "missing.git"
    with pytest.raises(RepoToolPolicyError) as exc_info:
        BareGitRepoToolkit(mirror_path=non_existent, head_commit="0" * 40)
    assert exc_info.value.code == "REPO_PATH_INVALID"

    existing_dir = tmp_path / "existing.git"
    existing_dir.mkdir()
    with pytest.raises(RepoToolPolicyError) as exc_info:
        BareGitRepoToolkit(mirror_path=existing_dir, head_commit="invalid_commit")
    assert exc_info.value.code == "REPO_PATH_INVALID"

    # Construction from RepoContext
    repo_ctx = RepoContext(mount_path=str(existing_dir), access="read-only", head_commit="a" * 40)
    tk = BareGitRepoToolkit.from_repo_context(repo_ctx)
    assert tk.head_commit == "a" * 40

    # Construction from RepoContext with mirror_path set
    repo_ctx_m = RepoContext(
        mount_path="/foo", access="read-only", head_commit="b" * 40, mirror_path=existing_dir
    )
    tk_m = BareGitRepoToolkit.from_repo_context(repo_ctx_m)
    assert tk_m.head_commit == "b" * 40


async def test_repo_toolkit_error_branches_and_edge_cases(
    bare_repo_fixture: tuple[Path, str, str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exercise remaining edge cases and error paths across git tools."""
    bare_path, c1, c2, c3 = bare_repo_fixture
    toolkit = BareGitRepoToolkit(mirror_path=bare_path, head_commit=c3)

    # 1. repo_tree with specific directory path and depth
    src_tree = await toolkit.repo_tree(path="src", max_depth=1)
    assert "src/app.py" in src_tree

    # Secret path passed to repo_tree
    with pytest.raises(RepoToolPolicyError) as exc_info:
        await toolkit.repo_tree(path=".env.production")
    assert exc_info.value.code == "REPO_SECRET_PATH_DENIED"

    # 2. repo_read_file with empty path
    with pytest.raises(RepoToolPolicyError) as exc_info:
        await toolkit.repo_read_file("   ")
    assert exc_info.value.code == "REPO_PATH_INVALID"

    # 3. repo_grep with specific path and secret path
    grep_src = await toolkit.repo_grep("return 'OK'", path="src")
    assert "src/app.py" in grep_src

    with pytest.raises(RepoToolPolicyError) as exc_info:
        await toolkit.repo_grep("secret", path=".env.production")
    assert exc_info.value.code == "REPO_SECRET_PATH_DENIED"

    # 4. repo_git_log with path and secret path
    log_src = await toolkit.repo_git_log(path="src", max_commits=5)
    assert "Add app module" in log_src

    with pytest.raises(RepoToolPolicyError) as exc_info:
        await toolkit.repo_git_log(path="certs/server.key")
    assert exc_info.value.code == "REPO_SECRET_PATH_DENIED"

    # 5. repo_git_diff base_ref length > 120 and unresolvable ref
    with pytest.raises(RepoToolPolicyError) as exc_info:
        await toolkit.repo_git_diff("x" * 121)
    assert exc_info.value.code == "REPO_PATH_INVALID"

    with pytest.raises(RepoToolPolicyError) as exc_info:
        await toolkit.repo_git_diff("nonexistent_branch_ref")
    assert exc_info.value.code == "REPO_PATH_INVALID"

    with pytest.raises(RepoToolPolicyError) as exc_info:
        await toolkit.repo_git_diff(base_ref=c1, path="certs/server.key")
    assert exc_info.value.code == "REPO_SECRET_PATH_DENIED"

    # Error exit codes from git
    async def mock_exec_error(*args: str) -> tuple[int, bytes, bytes]:
        if "rev-parse" in args:
            return 0, c1.encode("utf-8"), b""
        return 128, b"", b"fatal: git error"

    monkeypatch.setattr(toolkit, "_exec_git", mock_exec_error)
    err_tree = await toolkit.repo_tree()
    assert "repo_tree error" in err_tree

    err_grep = await toolkit.repo_grep("pattern")
    assert err_grep == ""

    err_log = await toolkit.repo_git_log()
    assert "repo_git_log error" in err_log

    err_diff = await toolkit.repo_git_diff(base_ref=c1)
    assert "repo_git_diff error" in err_diff

    # Truncation test
    trunc_out = _cap_and_scrub(b"a" * 70_000)
    assert "[TRUNCATED]" in trunc_out

    # 6. Mock subprocess timeout and OS error
    toolkit_to = BareGitRepoToolkit(mirror_path=bare_path, head_commit=c3, timeout_s=0.0001)

    async def mock_timeout(*_args: object, **_kwargs: object) -> None:
        import asyncio

        await asyncio.sleep(0.01)

    monkeypatch.setattr("asyncio.create_subprocess_exec", mock_timeout)
    with pytest.raises(RepoToolPolicyError) as exc_info:
        await toolkit_to.repo_git_log()
    assert exc_info.value.code == "REPO_TIMEOUT"

    async def mock_os_error(*_args: object, **_kwargs: object) -> None:
        raise OSError("Simulated process failure")

    monkeypatch.setattr("asyncio.create_subprocess_exec", mock_os_error)
    with pytest.raises(RepoToolPolicyError) as exc_info:
        await toolkit_to.repo_git_log()
    assert exc_info.value.code == "REPO_EXEC_FAILED"
