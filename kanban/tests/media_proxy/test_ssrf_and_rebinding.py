"""Unit tests for DNS-resolve-then-pin SSRF defenses and rebinding prevention (S5.4, S10.2)."""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from ipaddress import IPv4Address, IPv6Address
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from kanban.api.problems import ProblemException
from kanban.media_proxy.client import PinnedTlsMediaClient
from kanban.media_proxy.service import MediaProxyService
from kanban.media_proxy.ssrf import (
    DefaultAsyncHostResolver,
    is_public_global_ip,
    resolve_and_select_pinned_ip,
)

if TYPE_CHECKING:
    from collections.abc import Sequence


class MockSpyResolver:
    """Configurable resolver tracking call counts and returning canned IP records."""

    def __init__(self, records_sequence: Sequence[Sequence[IPv4Address | IPv6Address]]) -> None:
        """Initialize spy with a sequence of canned record batches."""
        self._sequence = list(records_sequence)
        self.call_count = 0
        self.resolved_hosts: list[str] = []

    async def resolve(self, host: str) -> Sequence[IPv4Address | IPv6Address]:
        """Record invocation and return next record batch."""
        self.call_count += 1
        self.resolved_hosts.append(host)
        if not self._sequence:
            return []
        if len(self._sequence) == 1:
            return self._sequence[0]
        idx = min(self.call_count - 1, len(self._sequence) - 1)
        return self._sequence[idx]


class MockSpyTransport:
    """Mock socket transport tracking open_connection invocations."""

    def __init__(self) -> None:
        """Initialize spy transport."""
        self.connect_calls: list[dict[str, object]] = []

    async def open_connection(
        self,
        ip: str,
        port: int,
        server_hostname: str,
        connect_timeout: float,
    ) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        """Record connection parameters and return mock stream pair."""
        self.connect_calls.append(
            {
                "ip": ip,
                "port": port,
                "server_hostname": server_hostname,
                "timeout": connect_timeout,
            }
        )
        reader = asyncio.StreamReader()
        reader.feed_data(
            b"HTTP/1.1 200 OK\r\n"
            b"Content-Type: image/png\r\n"
            b"Content-Length: 8\r\n\r\n"
            b"\x89PNG\r\n\x1a\n"
        )
        reader.feed_eof()
        writer_mock = MagicMock()
        writer_mock.write = MagicMock()
        writer_mock.close = MagicMock()
        writer_mock.drain = AsyncMock()
        writer_mock.wait_closed = AsyncMock()
        return reader, writer_mock


_BLOCKED_TEST_IPS: tuple[str, ...] = (
    "127.0.0.1",
    "10.0.0.1",
    "172.16.5.4",
    "192.168.1.1",
    "169.254.169.254",
    "100.64.0.1",
    "0.0.0.0",  # noqa: S104
    "::1",
    "fe80::1",
    "fc00::1",
    "fd12:3456::1",
    "::ffff:127.0.0.1",
    "::ffff:169.254.169.254",
    "64:ff9b::a9fe:a9fe",
)


@pytest.mark.asyncio
async def test_case_3_ssrf_ip_matrix() -> None:
    """Test Case 3: Blocked IP matrix and mixed-record DNS rejection (S5.4, S10.2)."""
    table_rows: list[str] = [
        "| Category | Resolved Address | Expected | Result | Code | Socket Connects |",
        "| :--- | :--- | :---: | :---: | :---: | :---: |",
    ]

    for ip_str in _BLOCKED_TEST_IPS:
        ip_obj = ipaddress.ip_address(ip_str)
        resolver = MockSpyResolver([[ip_obj]])
        transport = MockSpyTransport()
        client = PinnedTlsMediaClient(transport=transport)
        service = MediaProxyService(resolver=resolver, client=client)

        with pytest.raises(ProblemException) as exc_info:
            await service.fetch_proxy_media("https://ssrf-target.example.com/test.png")

        exc = exc_info.value
        assert exc.status == 403
        assert exc.code == "MEDIA_HOST_BLOCKED"
        assert len(transport.connect_calls) == 0

        table_rows.append(
            f"| Single-Record Block | `{ip_str}` | 403 BLOCKED | PASS | "
            f"`{exc.code}` | {len(transport.connect_calls)} |"
        )

    # Multi-record mixed public + private response: [93.184.216.34, 10.0.0.5]
    mixed_ips = [
        ipaddress.ip_address("93.184.216.34"),
        ipaddress.ip_address("10.0.0.5"),
    ]
    mixed_resolver = MockSpyResolver([mixed_ips])
    mixed_transport = MockSpyTransport()
    mixed_client = PinnedTlsMediaClient(transport=mixed_transport)
    mixed_service = MediaProxyService(resolver=mixed_resolver, client=mixed_client)

    with pytest.raises(ProblemException) as exc_info_mixed:
        await mixed_service.fetch_proxy_media("https://mixed-dns.example.com/test.png")

    exc_mixed = exc_info_mixed.value
    assert exc_mixed.status == 403
    assert exc_mixed.code == "MEDIA_HOST_BLOCKED"
    assert len(mixed_transport.connect_calls) == 0

    table_rows.append(
        "| Multi-Record Mixed | `[93.184.216.34, 10.0.0.5]` | 403 BLOCKED | PASS | "
        f"`{exc_mixed.code}` | {len(mixed_transport.connect_calls)} |"
    )

    # Write ssrf-matrix-results.txt QA proof
    proof_dir = Path("docs/qa/KANBA-66")
    proof_dir.mkdir(parents=True, exist_ok=True)  # noqa: ASYNC240
    matrix_file = proof_dir / "ssrf-matrix-results.txt"
    matrix_content = (
        "KANBA-66 / KB-P2-16 SSRF Blocked IP Matrix Verification (S5.4, S10.2)\n"
        "====================================================================\n\n"
        + "\n".join(table_rows)
        + "\n\nAll non-public, loopback, private, IMDS, and mixed DNS responses "
        "were rejected with 403 MEDIA_HOST_BLOCKED and zero TCP connections.\n"
    )
    matrix_file.write_text(matrix_content, encoding="utf-8")


@pytest.mark.asyncio
async def test_case_4_dns_rebinding_toctou() -> None:
    """Test Case 4: DNS rebinding TOCTOU defense pinning resolved IP (S5.4, S10.2)."""
    public_ip = ipaddress.ip_address("93.184.216.34")
    rebind_imds_ip = ipaddress.ip_address("169.254.169.254")

    # Resolver configured to return public IP on lookup 1 and IMDS on lookup 2
    resolver = MockSpyResolver([[public_ip], [rebind_imds_ip]])
    transport = MockSpyTransport()
    client = PinnedTlsMediaClient(transport=transport)
    service = MediaProxyService(resolver=resolver, client=client)

    target_host = "rebind.example.com"
    target_url = f"https://{target_host}/image.png"

    content_type, body_bytes, _headers = await service.fetch_proxy_media(target_url)

    assert content_type == "image/png"
    assert body_bytes.startswith(b"\x89PNG")

    # Assert resolver was invoked exactly ONCE
    assert resolver.call_count == 1
    assert resolver.resolved_hosts == [target_host]

    # Assert socket connection was opened to the literal public IP with TLS SNI of the hostname
    assert len(transport.connect_calls) == 1
    connect_call = transport.connect_calls[0]
    assert connect_call["ip"] == "93.184.216.34"
    assert connect_call["server_hostname"] == target_host
    assert connect_call["port"] == 443


@pytest.mark.asyncio
async def test_dns_resolver_failures_and_timeouts() -> None:
    """Verify resolver errors, empty records, and timeouts map to 403 MEDIA_HOST_BLOCKED."""
    # Empty records
    empty_resolver = MockSpyResolver([[]])
    with pytest.raises(ProblemException) as exc_empty:
        await resolve_and_select_pinned_ip("empty.example.com", resolver=empty_resolver)
    assert exc_empty.value.status == 403
    assert exc_empty.value.code == "MEDIA_HOST_BLOCKED"

    # Resolver timeout
    class SlowResolver:
        async def resolve(self, _host: str) -> Sequence[IPv4Address | IPv6Address]:
            await asyncio.sleep(5.0)
            return [ipaddress.ip_address("93.184.216.34")]

    with pytest.raises(ProblemException) as exc_timeout:
        await resolve_and_select_pinned_ip("slow.example.com", resolver=SlowResolver())
    assert exc_timeout.value.status == 403
    assert exc_timeout.value.code == "MEDIA_HOST_BLOCKED"


@pytest.mark.asyncio
async def test_default_async_host_resolver() -> None:
    """Verify DefaultAsyncHostResolver socket.gaierror handling and successful resolution."""
    resolver = DefaultAsyncHostResolver()

    # Successful resolution using loopback mock and duplicate IP deduplication
    mock_addrinfo = [
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443)),
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443)),
    ]
    with patch("asyncio.get_running_loop") as mock_loop_fn:
        mock_loop = AsyncMock()
        mock_loop.getaddrinfo = AsyncMock(return_value=mock_addrinfo)
        mock_loop_fn.return_value = mock_loop

        ips = await resolver.resolve("example.com")
        assert len(ips) == 1
        assert str(ips[0]) == "93.184.216.34"

    # socket.gaierror mapping to 403 MEDIA_HOST_BLOCKED
    with patch("asyncio.get_running_loop") as mock_loop_fn:
        mock_loop = AsyncMock()
        mock_loop.getaddrinfo = AsyncMock(side_effect=socket.gaierror("Name or service not known"))
        mock_loop_fn.return_value = mock_loop

        with pytest.raises(ProblemException) as exc_gai:
            await resolver.resolve("nonexistent.example.com")
        assert exc_gai.value.status == 403
        assert exc_gai.value.code == "MEDIA_HOST_BLOCKED"


def test_is_public_global_ip_coverage() -> None:
    """Verify public and disallowed IP classifications."""
    assert is_public_global_ip("93.184.216.34") is True
    assert is_public_global_ip("1.1.1.1") is True
    assert is_public_global_ip("2606:4700:4700::1111") is True

    assert is_public_global_ip("invalid-ip-string") is False
    assert is_public_global_ip("127.0.0.1") is False
    assert is_public_global_ip("10.0.0.1") is False
    assert is_public_global_ip("172.20.0.1") is False
    assert is_public_global_ip("192.168.0.1") is False
    assert is_public_global_ip("169.254.1.1") is False
    assert is_public_global_ip("100.64.1.1") is False
    assert is_public_global_ip("192.0.2.1") is False
    assert is_public_global_ip("198.51.100.1") is False
    assert is_public_global_ip("203.0.113.1") is False
    assert is_public_global_ip("224.0.0.1") is False
    assert is_public_global_ip("240.0.0.1") is False
    assert is_public_global_ip("255.255.255.255") is False
    assert is_public_global_ip("::1") is False
    assert is_public_global_ip("::") is False
    assert is_public_global_ip("fe80::1") is False
    assert is_public_global_ip("fc00::1") is False
    assert is_public_global_ip("fec0::1") is False
    assert is_public_global_ip("2001:db8::1") is False
    assert is_public_global_ip("::ffff:10.0.0.1") is False
    assert is_public_global_ip("64:ff9b::a9fe:0101") is False
