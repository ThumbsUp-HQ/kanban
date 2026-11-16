# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Feature unit tests for repo_path_guard (KB-P5-20)."""

from __future__ import annotations

import pytest

from agent.tools.repo_path_guard import (
    MAX_REPO_PATH_BYTES,
    RepoToolPolicyError,
    is_secret_repo_path,
    normalize_repo_relpath,
)


def test_normalize_repo_relpath_valid() -> None:
    """Valid relative paths normalize cleanly."""
    assert normalize_repo_relpath("") == ""
    assert normalize_repo_relpath("   ") == ""
    assert normalize_repo_relpath("foo.py") == "foo.py"
    assert normalize_repo_relpath("src/app/main.py") == "src/app/main.py"
    assert normalize_repo_relpath("database/migrations/env.py") == "database/migrations/env.py"
    assert normalize_repo_relpath("database/") == "database"
    assert normalize_repo_relpath("src/app/") == "src/app"


def test_normalize_repo_relpath_traversal_rejected() -> None:
    """Traversal segments (., ..) are strictly rejected with REPO_PATH_INVALID."""
    traversals = [
        "../etc/passwd",
        "foo/../bar",
        "./foo",
        "foo/.",
        "..",
        ".",
        "a/b/../../c",
    ]
    for path in traversals:
        with pytest.raises(RepoToolPolicyError) as exc_info:
            normalize_repo_relpath(path)
        assert exc_info.value.code == "REPO_PATH_INVALID"


def test_normalize_repo_relpath_option_injection_rejected() -> None:
    """Paths starting with dash (option injection) are rejected."""
    dashes = ["-foo", "--option", "-e", "--open-files-in-pager=sh"]
    for path in dashes:
        with pytest.raises(RepoToolPolicyError) as exc_info:
            normalize_repo_relpath(path)
        assert exc_info.value.code == "REPO_PATH_INVALID"


def test_normalize_repo_relpath_absolute_paths_rejected() -> None:
    """Absolute paths starting with slash are rejected."""
    absolutes = ["/etc/shadow", "/tmp/pwn", "/"]
    for path in absolutes:
        with pytest.raises(RepoToolPolicyError) as exc_info:
            normalize_repo_relpath(path)
        assert exc_info.value.code == "REPO_PATH_INVALID"


def test_normalize_repo_relpath_invalid_characters() -> None:
    """NUL, CR, LF, backslashes, and consecutive slashes are rejected."""
    invalids = [
        "foo\0bar",
        "foo\nbar",
        "foo\rbar",
        "foo\\bar",
        "foo//bar",
    ]
    for path in invalids:
        with pytest.raises(RepoToolPolicyError) as exc_info:
            normalize_repo_relpath(path)
        assert exc_info.value.code == "REPO_PATH_INVALID"


def test_normalize_repo_relpath_oversize_and_types() -> None:
    """Paths exceeding 512 bytes, non-string inputs, or unencodable chars are rejected."""
    long_path = "a" * (MAX_REPO_PATH_BYTES + 1)
    with pytest.raises(RepoToolPolicyError) as exc_info:
        normalize_repo_relpath(long_path)
    assert exc_info.value.code == "REPO_PATH_INVALID"

    with pytest.raises(RepoToolPolicyError) as exc_info_type:
        normalize_repo_relpath(123)  # type: ignore[arg-type]
    assert exc_info_type.value.code == "REPO_PATH_INVALID"

    # Lone surrogate character triggers UnicodeEncodeError
    with pytest.raises(RepoToolPolicyError) as exc_info_surrogate:
        normalize_repo_relpath("\ud800")
    assert exc_info_surrogate.value.code == "REPO_PATH_INVALID"


def test_is_secret_repo_path_detection() -> None:
    """Secret configuration and key paths are detected across segments and basenames."""
    secrets = [
        ".env",
        ".env.production",
        ".env.local",
        "config/.env",
        "secrets/app.env",
        "certs/server.key",
        "tls/cert.pem",
        "keystore/signing.jks",
        "auth/key.p12",
        "auth/bundle.pfx",
        "ssh/id_rsa",
        "ssh/id_rsa.pub",
        "ssh/id_ed25519",
        "ssh/id_ecdsa",
        ".git",
        ".git/config",
        ".git/HEAD",
        ".netrc",
        "home/.netrc",
        ".npmrc",
        ".pypirc",
        "SUBDIR/.ENV.PRODUCTION",  # case-insensitive
    ]
    for s in secrets:
        assert is_secret_repo_path(s) is True, f"Failed to identify secret path: {s}"


def test_is_secret_repo_path_non_secret() -> None:
    """Normal source and documentation files are not flagged as secrets."""
    safe_paths = [
        "",
        "src/main.py",
        "docs/ARCHITECTURE.md",
        "tests/test_auth.py",
        "environment/setup.py",
        "keyboard/layout.json",
        "pki/readme.txt",
    ]
    for path in safe_paths:
        assert is_secret_repo_path(path) is False, f"Falsely flagged safe path: {path}"


def test_repo_tool_policy_error_formatting() -> None:
    """RepoToolPolicyError formats code and message as expected."""
    err1 = RepoToolPolicyError("CUSTOM_CODE")
    assert err1.code == "CUSTOM_CODE"
    assert "CUSTOM_CODE" in str(err1)

    err2 = RepoToolPolicyError("CUSTOM_CODE", "detailed description")
    assert err2.code == "CUSTOM_CODE"
    assert err2.message == "detailed description"
    assert "[CUSTOM_CODE] detailed description" in str(err2)
