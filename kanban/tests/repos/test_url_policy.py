# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Unit tests for repository remote URL validation and SSRF defenses (KB-P5-19b, S14.3)."""

from __future__ import annotations

import ipaddress
import socket
from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from collections.abc import Callable

from kanban.repos.url_policy import (
    RepoUrlRejectedError,
    classify_ip_address,
    resolve_host_ips,
    validate_remote_url,
)


def _fake_resolver(ip: str) -> Callable[[str], list[str]]:
    """Return a fake resolver yielding the specified IP."""
    return lambda _host: [ip]


def test_validate_valid_https_url() -> None:
    """Valid public HTTPS url parses, normalizes and returns pinned IP."""
    url = "https://github.com/octocat/Hello-World.git"
    result = validate_remote_url(url, resolver=_fake_resolver("140.82.121.3"))
    assert result.scheme == "https"
    assert result.host == "github.com"
    assert result.port == 443
    assert result.pinned_ip == "140.82.121.3"
    assert result.path == "/octocat/Hello-World.git"
    assert result.normalized_url == url


def test_validate_valid_scp_ssh_url() -> None:
    """Valid SCP syntax git@host:path normalizes to ssh://git@host/path."""
    url = "git@github.com:octocat/Hello-World.git"
    result = validate_remote_url(url, resolver=_fake_resolver("140.82.121.3"))
    assert result.scheme == "ssh"
    assert result.host == "github.com"
    assert result.port == 22
    assert result.pinned_ip == "140.82.121.3"
    assert result.path == "/octocat/Hello-World.git"
    assert result.normalized_url == "ssh://git@github.com/octocat/Hello-World.git"


def test_validate_valid_ssh_custom_port() -> None:
    """Valid standard ssh:// url with custom port."""
    url = "ssh://git@gitlab.internal.corp:2222/group/project.git"
    result = validate_remote_url(
        url,
        allowed_git_cidrs=["192.168.0.0/16"],
        resolver=_fake_resolver("192.168.1.50"),
    )
    assert result.scheme == "ssh"
    assert result.host == "gitlab.internal.corp"
    assert result.port == 2222
    assert result.pinned_ip == "192.168.1.50"


def test_reject_empty_or_whitespace_only() -> None:
    """Empty or blank URLs are rejected with EMPTY_URL."""
    with pytest.raises(RepoUrlRejectedError) as exc_info:
        validate_remote_url("")
    assert exc_info.value.reason == "EMPTY_URL"
    assert exc_info.value.status == 422

    with pytest.raises(RepoUrlRejectedError) as exc_info2:
        validate_remote_url("   \t\n  ")
    assert exc_info2.value.reason == "EMPTY_URL"


def test_reject_option_injection() -> None:
    """URLs starting with a dash are rejected with OPTION_INJECTION."""
    with pytest.raises(RepoUrlRejectedError) as exc_info:
        validate_remote_url("--upload-pack=touch /tmp/pwned")
    assert exc_info.value.reason == "OPTION_INJECTION"


def test_reject_control_characters_or_whitespace() -> None:
    """URLs containing internal whitespace or control characters are rejected."""
    with pytest.raises(RepoUrlRejectedError) as exc_info:
        validate_remote_url("https://github.com/foo bar/baz.git")
    assert exc_info.value.reason == "INVALID_CHARACTERS"

    with pytest.raises(RepoUrlRejectedError) as exc_info2:
        validate_remote_url("https://github.com/foo\x00bar/baz.git")
    assert exc_info2.value.reason == "INVALID_CHARACTERS"


def test_reject_too_long() -> None:
    """URLs exceeding 2048 characters are rejected with URL_TOO_LONG."""
    long_url = "https://github.com/" + ("a" * 2050)
    with pytest.raises(RepoUrlRejectedError) as exc_info:
        validate_remote_url(long_url)
    assert exc_info.value.reason == "URL_TOO_LONG"


@pytest.mark.parametrize(
    ("bad_url", "expected_reason"),
    [
        ("file:///etc/passwd", "SCHEME_FILE_DISALLOWED"),
        ("ext::sh -c evil", "SCHEME_EXT_DISALLOWED"),
        ("fd::123", "SCHEME_FD_DISALLOWED"),
        ("git://github.com/repo.git", "SCHEME_GIT_DISALLOWED"),
        ("http://github.com/repo.git", "INSECURE_HTTP_SCHEME"),
        ("ftp://ftp.example.com/repo.git", "DISALLOWED_SCHEME"),
        ("ftps://ftp.example.com/repo.git", "DISALLOWED_SCHEME"),
        ("gopher://gopher.example.com/1", "DISALLOWED_SCHEME"),
    ],
)
def test_reject_disallowed_schemes(bad_url: str, expected_reason: str) -> None:
    """Disallowed schemes trigger appropriate rejection reason codes."""
    with pytest.raises(RepoUrlRejectedError) as exc_info:
        validate_remote_url(bad_url)
    assert exc_info.value.reason == expected_reason


def test_reject_embedded_credentials() -> None:
    """Embedded credentials in https or passwords in ssh are forbidden."""
    with pytest.raises(RepoUrlRejectedError) as exc_info:
        validate_remote_url("https://user:password@github.com/org/repo.git")
    assert exc_info.value.reason == "EMBEDDED_CREDENTIALS"

    with pytest.raises(RepoUrlRejectedError) as exc_info2:
        validate_remote_url("https://user@github.com/org/repo.git")
    assert exc_info2.value.reason == "EMBEDDED_CREDENTIALS"

    with pytest.raises(RepoUrlRejectedError) as exc_info3:
        validate_remote_url("ssh://git:secret@github.com/org/repo.git")
    assert exc_info3.value.reason == "EMBEDDED_CREDENTIALS"


def test_reject_missing_host() -> None:
    """Missing hostname is rejected with MISSING_HOST."""
    with pytest.raises(RepoUrlRejectedError) as exc_info:
        validate_remote_url("https:///repo.git")
    assert exc_info.value.reason == "MISSING_HOST"


def test_reject_host_resolution_failed() -> None:
    """Hosts that fail DNS resolution trigger HOST_RESOLUTION_FAILED."""
    with pytest.raises(RepoUrlRejectedError) as exc_info:
        validate_remote_url("https://nonexistent.invalid/repo.git", resolver=lambda _h: [])
    assert exc_info.value.reason == "HOST_RESOLUTION_FAILED"


def test_reject_invalid_resolved_ip() -> None:
    """Resolver returning a garbage IP format triggers INVALID_RESOLVED_IP."""
    with pytest.raises(RepoUrlRejectedError) as exc_info:
        validate_remote_url("https://github.com/repo.git", resolver=lambda _h: ["not-an-ip"])
    assert exc_info.value.reason == "INVALID_RESOLVED_IP"


@pytest.mark.parametrize(
    ("ip_str", "expected_reason"),
    [
        ("127.0.0.1", "LOOPBACK_ADDRESS_FORBIDDEN"),
        ("127.0.0.2", "LOOPBACK_ADDRESS_FORBIDDEN"),
        ("::1", "LOOPBACK_ADDRESS_FORBIDDEN"),
        ("::ffff:127.0.0.1", "LOOPBACK_ADDRESS_FORBIDDEN"),
        ("169.254.169.254", "METADATA_OR_LINK_LOCAL_ADDRESS"),
        ("169.254.1.1", "METADATA_OR_LINK_LOCAL_ADDRESS"),
        ("fd00:ec2::254", "METADATA_OR_LINK_LOCAL_ADDRESS"),
        ("fe80::1", "METADATA_OR_LINK_LOCAL_ADDRESS"),
        ("10.0.0.1", "RFC1918_ADDRESS_FORBIDDEN"),
        ("172.16.5.10", "RFC1918_ADDRESS_FORBIDDEN"),
        ("192.168.1.1", "RFC1918_ADDRESS_FORBIDDEN"),
        ("224.0.0.1", "DISALLOWED_IP_RANGE"),
        ("0.0.0.0", "DISALLOWED_IP_RANGE"),  # noqa: S104
        ("240.0.0.1", "DISALLOWED_IP_RANGE"),
    ],
)
def test_ssrf_forbidden_ips(ip_str: str, expected_reason: str) -> None:
    """Non-whitelisted loopback, metadata, RFC1918, and multicast IPs are blocked."""
    with pytest.raises(RepoUrlRejectedError) as exc_info:
        validate_remote_url("https://internal.test/repo.git", resolver=_fake_resolver(ip_str))
    assert exc_info.value.reason == expected_reason


def test_allowed_cidrs_permits_private_ip() -> None:
    """Private IPs are allowed when covered by allowed_git_cidrs."""
    url = "https://internal.git.local/repo.git"
    result = validate_remote_url(
        url,
        allowed_git_cidrs=["10.50.0.0/16", "invalid-cidr-ignored"],
        resolver=_fake_resolver("10.50.12.34"),
    )
    assert result.pinned_ip == "10.50.12.34"
    assert result.host == "internal.git.local"


def test_air_gap_mode_enforcement() -> None:
    """Under air_gap_mode, any resolved IP not in allowed_git_cidrs is rejected."""
    url = "https://github.com/org/repo.git"
    with pytest.raises(RepoUrlRejectedError) as exc_info:
        validate_remote_url(
            url,
            air_gap_mode=True,
            allowed_git_cidrs=["10.0.0.0/8"],
            resolver=_fake_resolver("140.82.121.3"),
        )
    assert exc_info.value.reason == "AIR_GAP_HOST_NOT_ALLOWED"

    # Permitted when in CIDR
    res = validate_remote_url(
        "https://airgap.local/repo.git",
        air_gap_mode=True,
        allowed_git_cidrs=["10.0.0.0/8"],
        resolver=_fake_resolver("10.1.2.3"),
    )
    assert res.pinned_ip == "10.1.2.3"


def test_classify_ip_address_direct() -> None:
    """Direct checks on classify_ip_address helper."""
    assert classify_ip_address(ipaddress.ip_address("8.8.8.8")) is None
    assert classify_ip_address(ipaddress.ip_address("127.0.0.1")) == "LOOPBACK_ADDRESS_FORBIDDEN"
    assert classify_ip_address(ipaddress.ip_address("192.168.0.1")) == "RFC1918_ADDRESS_FORBIDDEN"


def test_resolve_host_ips_helper(monkeypatch: pytest.MonkeyPatch) -> None:
    """resolve_host_ips handles literal IPs and DNS resolution."""
    # Direct IP literal returns immediately without socket call
    assert resolve_host_ips("127.0.0.1") == ["127.0.0.1"]
    assert resolve_host_ips("::1") == ["::1"]

    def mock_getaddrinfo(
        host: str,
        _port: int | None,
        *_args: object,
        **_kwargs: object,
    ) -> list[Any]:
        if host == "localhost":
            return [
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 0)),
                (socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("::1", 0, 0, 0)),
            ]
        raise socket.gaierror(-2, "Name or service not known")

    monkeypatch.setattr(socket, "getaddrinfo", mock_getaddrinfo)

    # Valid resolution for localhost
    res = resolve_host_ips("localhost")
    assert "127.0.0.1" in res
    assert "::1" in res

    # Resolution failure returns empty list
    assert resolve_host_ips("nonexistent-domain-that-cannot-exist.invalid") == []
