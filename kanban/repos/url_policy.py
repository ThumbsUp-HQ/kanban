# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Strict URL policy validation and SSRF defenses for git repositories (KB-P5-19b, S14.3)."""

from __future__ import annotations

import ipaddress
import re
import socket
import urllib.parse
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from kanban.api.problems import ProblemException

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

__all__ = [
    "RepoUrlRejectedError",
    "ValidatedRemoteUrl",
    "classify_ip_address",
    "resolve_host_ips",
    "validate_remote_url",
]

_MAX_URL_LENGTH: Final[int] = 2048
_IPV6_VERSION: Final[int] = 6
_IPV4_VERSION: Final[int] = 4
_ASCII_SPACE: Final[int] = 32
_ASCII_DEL: Final[int] = 127
_DISALLOWED_SCHEME_PREFIXES: Final[tuple[str, ...]] = (
    "file://",
    "ext::",
    "fd::",
    "git://",
    "http://",
    "ftp://",
    "ftps://",
)

_SCP_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^([a-zA-Z0-9._-]+)@([a-zA-Z0-9.-]+):([a-zA-Z0-9._/~-]+)$"
)


class RepoUrlRejectedError(ProblemException):
    """Raised when a remote repository URL fails security or scheme validation."""

    def __init__(self, reason: str, detail: str | None = None) -> None:
        """Initialize exception with machine-readable reason code."""
        msg = detail or f"Repository URL rejected: {reason}"
        super().__init__(
            code="REPO_URL_REJECTED",
            status=422,
            title="Repository URL Rejected",
            detail=msg,
            extra={"reason": reason},
        )
        self.reason = reason


@dataclass(frozen=True, slots=True)
class ValidatedRemoteUrl:
    """Validated and normalized remote repository URL with DNS pinning data."""

    raw_url: str
    normalized_url: str
    scheme: str  # "https" | "ssh"
    host: str
    port: int
    pinned_ip: str | None
    path: str


def resolve_host_ips(host: str) -> list[str]:
    """Resolve DNS host to IPv4 and IPv6 addresses."""
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        return [host]

    try:
        addrinfo = socket.getaddrinfo(host, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
    except socket.gaierror:
        return []
    else:
        ips: list[str] = []
        for item in addrinfo:
            sockaddr = item[4]
            ip_str = str(sockaddr[0])
            if ip_str not in ips:
                ips.append(ip_str)
        return ips


def classify_ip_address(ip_addr: ipaddress.IPv4Address | ipaddress.IPv6Address) -> str | None:
    """Classify IP address into SSRF risk categories, returning forbidden reason or None."""
    target_addr: ipaddress.IPv4Address | ipaddress.IPv6Address = ip_addr
    if isinstance(ip_addr, ipaddress.IPv6Address) and ip_addr.ipv4_mapped:
        target_addr = ip_addr.ipv4_mapped

    if target_addr.is_loopback:
        return "LOOPBACK_ADDRESS_FORBIDDEN"

    if str(target_addr) in ("169.254.169.254", "fd00:ec2::254") or target_addr.is_link_local:
        return "METADATA_OR_LINK_LOCAL_ADDRESS"

    if target_addr.is_multicast or target_addr.is_unspecified or target_addr.is_reserved:
        return "DISALLOWED_IP_RANGE"

    if target_addr.is_private:
        return "RFC1918_ADDRESS_FORBIDDEN"

    return None


def _is_ip_in_cidrs(
    ip_addr: ipaddress.IPv4Address | ipaddress.IPv6Address,
    cidrs: Sequence[str],
) -> bool:
    """Return True if ip_addr is contained in any of the allowed CIDR blocks."""
    for cidr_str in cidrs:
        try:
            net = ipaddress.ip_network(cidr_str.strip(), strict=False)
            target: ipaddress.IPv4Address | ipaddress.IPv6Address = ip_addr
            if (
                isinstance(ip_addr, ipaddress.IPv6Address)
                and ip_addr.ipv4_mapped
                and net.version == _IPV4_VERSION
            ):
                target = ip_addr.ipv4_mapped
            if target.version == net.version and target in net:
                return True
        except ValueError:
            continue
    return False


def validate_remote_url(  # noqa: C901, PLR0912, PLR0915
    url: str,
    *,
    allowed_git_cidrs: Sequence[str] | None = None,
    air_gap_mode: bool = False,
    resolver: Callable[[str], list[str]] | None = None,
) -> ValidatedRemoteUrl:
    """Validate remote URL for strict scheme, bounds, and SSRF avoidance."""
    if not url or not url.strip():
        reason_empty = "EMPTY_URL"
        msg_empty = "Repository URL cannot be empty"
        raise RepoUrlRejectedError(reason_empty, msg_empty)

    if url.startswith("-"):
        reason_opt = "OPTION_INJECTION"
        msg_opt = "Leading option characters are rejected"
        raise RepoUrlRejectedError(reason_opt, msg_opt)

    # Explicit disallowed scheme checks
    lower_url = url.lower()
    if lower_url.startswith("file://"):
        reason_file = "SCHEME_FILE_DISALLOWED"
        msg_file = "file:// scheme is forbidden"
        raise RepoUrlRejectedError(reason_file, msg_file)
    if lower_url.startswith("ext::"):
        reason_ext = "SCHEME_EXT_DISALLOWED"
        msg_ext = "ext:: remote helper is forbidden"
        raise RepoUrlRejectedError(reason_ext, msg_ext)
    if lower_url.startswith("fd::"):
        reason_fd = "SCHEME_FD_DISALLOWED"
        msg_fd = "fd:: remote helper is forbidden"
        raise RepoUrlRejectedError(reason_fd, msg_fd)
    if lower_url.startswith("git://"):
        reason_git = "SCHEME_GIT_DISALLOWED"
        msg_git = "git:// insecure protocol is forbidden"
        raise RepoUrlRejectedError(reason_git, msg_git)
    if lower_url.startswith("http://"):
        reason_http = "INSECURE_HTTP_SCHEME"
        msg_http = "http:// cleartext protocol is forbidden"
        raise RepoUrlRejectedError(reason_http, msg_http)

    for disallowed in _DISALLOWED_SCHEME_PREFIXES:
        if lower_url.startswith(disallowed):
            reason_disallowed = "DISALLOWED_SCHEME"
            msg_disallowed = f"Protocol {disallowed} is not permitted"
            raise RepoUrlRejectedError(reason_disallowed, msg_disallowed)

    if any(c.isspace() or ord(c) < _ASCII_SPACE or ord(c) == _ASCII_DEL for c in url):
        reason_char = "INVALID_CHARACTERS"
        msg_char = "Whitespace or control characters are rejected"
        raise RepoUrlRejectedError(reason_char, msg_char)

    if len(url) > _MAX_URL_LENGTH:
        reason_len = "URL_TOO_LONG"
        msg_len = f"URL exceeds {_MAX_URL_LENGTH} characters"
        raise RepoUrlRejectedError(reason_len, msg_len)

    # Normalize scp-like ssh syntax: git@host:path -> ssh://git@host/path
    scp_match = _SCP_PATTERN.match(url)
    if scp_match:
        user, host, path = scp_match.groups()
        normalized_url = f"ssh://{user}@{host}/{path}"
    else:
        normalized_url = url

    parsed = urllib.parse.urlsplit(normalized_url)
    scheme = parsed.scheme.lower()

    if scheme not in ("https", "ssh"):
        reason_unsupported = "DISALLOWED_SCHEME"
        msg_unsupported = f"Unsupported repository scheme '{scheme}'"
        raise RepoUrlRejectedError(reason_unsupported, msg_unsupported)

    if scheme == "https" and (parsed.username or parsed.password):
        reason_creds = "EMBEDDED_CREDENTIALS"
        msg_creds = "Embedded user credentials in HTTPS URLs are forbidden"
        raise RepoUrlRejectedError(reason_creds, msg_creds)
    if scheme == "ssh" and parsed.password:
        reason_creds_ssh = "EMBEDDED_CREDENTIALS"
        msg_creds_ssh = "Embedded passwords in SSH URLs are forbidden"
        raise RepoUrlRejectedError(reason_creds_ssh, msg_creds_ssh)

    host = parsed.hostname
    if not host:
        reason_no_host = "MISSING_HOST"
        msg_no_host = "Missing host in repository URL"
        raise RepoUrlRejectedError(reason_no_host, msg_no_host)

    port = parsed.port or (443 if scheme == "https" else 22)

    # Resolve host
    dns_resolver = resolver or resolve_host_ips
    resolved_ips = dns_resolver(host)
    if not resolved_ips:
        reason_dns = "HOST_RESOLUTION_FAILED"
        msg_dns = f"Could not resolve host '{host}'"
        raise RepoUrlRejectedError(reason_dns, msg_dns)

    allowed_cidrs = list(allowed_git_cidrs or [])
    pinned_ip: str | None = None

    for ip_str in resolved_ips:
        try:
            ip_obj = ipaddress.ip_address(ip_str)
        except ValueError:
            reason_bad_ip = "INVALID_RESOLVED_IP"
            msg_bad_ip = f"Invalid IP returned by resolver: {ip_str}"
            raise RepoUrlRejectedError(reason_bad_ip, msg_bad_ip) from None

        is_allowed_by_cidr = _is_ip_in_cidrs(ip_obj, allowed_cidrs)

        if air_gap_mode and not is_allowed_by_cidr:
            reason_air = "AIR_GAP_HOST_NOT_ALLOWED"
            msg_air = f"Host '{host}' ({ip_str}) is not in allowed_git_cidrs under air-gap mode"
            raise RepoUrlRejectedError(reason_air, msg_air)

        if not is_allowed_by_cidr:
            risk_category = classify_ip_address(ip_obj)
            if risk_category:
                msg_risk = f"Host '{host}' resolves to forbidden IP {ip_str}"
                raise RepoUrlRejectedError(risk_category, msg_risk)

        if pinned_ip is None:
            pinned_ip = ip_str

    return ValidatedRemoteUrl(
        raw_url=url,
        normalized_url=normalized_url,
        scheme=scheme,
        host=host,
        port=port,
        pinned_ip=pinned_ip,
        path=parsed.path,
    )
