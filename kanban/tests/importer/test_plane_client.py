# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Unit tests for Plane client, SSRF defenses, and bundle parser (KB-P6-01)."""

# ruff: noqa: ARG001, PLC0415, SIM117

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from kanban.importer.plane_client import (
    MAX_PAGE_BYTES,
    PlaneClient,
    PlaneClientError,
    PlaneSecurityError,
    validate_target_url,
)

FIXTURE_DIR = Path("tests/fixtures/plane_export_kanba").resolve()


def test_ssrf_rejects_http_and_private_ips() -> None:
    """Test Case 4: plane_client rejects http:// non-loopback, link-local, and private CIDRs."""
    # 1. Plain HTTP without loopback
    with pytest.raises(PlaneSecurityError, match="HTTP scheme forbidden"):
        validate_target_url("http://example.com/api", allow_loopback_http=False)

    # 2. Unsupported scheme
    with pytest.raises(PlaneSecurityError, match="Unsupported URL scheme"):
        validate_target_url("ftp://example.com/api")

    # 3. Missing hostname
    with pytest.raises(PlaneSecurityError, match="missing hostname"):
        validate_target_url("https:///api")

    # 4. Link-local 169.254.169.254
    with pytest.raises(PlaneSecurityError, match="blocked private/reserved IP"):
        validate_target_url("https://169.254.169.254/api")

    # 5. Private IP 10.0.0.1
    with pytest.raises(PlaneSecurityError, match="blocked private/reserved IP"):
        validate_target_url("https://10.0.0.1/api")

    # 6. Loopback without allow_loopback_http
    with pytest.raises(PlaneSecurityError, match="loopback IP"):
        validate_target_url("https://127.0.0.1/api", allow_loopback_http=False)

    # 7. Loopback with allow_loopback_http
    hostname, ips = validate_target_url(
        "http://127.0.0.1/api",
        allow_loopback_http=True,
    )
    assert hostname == "127.0.0.1"
    assert "127.0.0.1" in ips


def test_load_bundle_from_fixture_directory() -> None:
    """Verify loading recorded fixture bundle populates all entity collections."""
    client = PlaneClient()
    bundle = client.load_bundle_from_dir(FIXTURE_DIR)

    assert len(bundle.projects) == 2
    assert bundle.projects[0].identifier == "KANBA"
    assert bundle.projects[1].identifier == "SEC"

    assert len(bundle.states) == 6
    assert len(bundle.labels) == 2
    assert len(bundle.cycles) == 2
    assert len(bundle.modules) == 1

    # 12 issues total (6 in KANBA, 6 in SEC)
    assert len(bundle.issues) == 12
    kanba_19 = next((i for i in bundle.issues if i.sequence_id == 19), None)
    assert kanba_19 is not None
    assert kanba_19.name == "Plane importer cutover feature"

    assert len(bundle.comments) == 1
    assert len(bundle.relations) == 4
    assert len(bundle.members) == 2
    assert len(bundle.attachments) == 2
    assert "asset-png.png" in bundle.attachments
    assert "asset-svg.svg" in bundle.attachments


def test_load_bundle_nonexistent_dir() -> None:
    """Verify loading from nonexistent directory raises PlaneClientError."""
    client = PlaneClient()
    with pytest.raises(PlaneClientError, match="does not exist"):
        client.load_bundle_from_dir("/tmp/nonexistent-bundle-dir-xyz")


def test_load_bundle_oversized_file(tmp_path: Path) -> None:
    """Verify files exceeding 25 MiB raise PlaneClientError."""
    oversized = tmp_path / "project.json"
    oversized.write_bytes(b" " * (MAX_PAGE_BYTES + 1))
    client = PlaneClient()
    with pytest.raises(PlaneClientError, match="exceeds maximum allowable size"):
        client.load_bundle_from_dir(tmp_path)


@pytest.mark.asyncio
async def test_fetch_snapshot_redirect_rejection(tmp_path: Path) -> None:
    """Test Case 4: fetch_snapshot rejects 302 redirects fail-closed."""
    client = PlaneClient(allow_loopback_http=True)

    mock_resp = httpx.Response(
        status_code=302,
        headers={"Location": "https://evil.example/other"},
        request=httpx.Request("GET", "http://127.0.0.1/api"),
    )

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_resp

        with pytest.raises(PlaneSecurityError, match="Redirect rejected"):
            await client.fetch_snapshot(
                base_url="http://127.0.0.1:8000",
                workspace_slug="demo",
                project_identifier="KANBA",
                out_dir=tmp_path,
                api_key="test-api-key",
            )


@pytest.mark.asyncio
async def test_fetch_snapshot_rate_limit_backoff(tmp_path: Path) -> None:
    """Verify exponential backoff retry on HTTP 429."""
    client = PlaneClient(allow_loopback_http=True)

    resp_429 = httpx.Response(
        status_code=429,
        headers={"Retry-After": "0.01"},
        request=httpx.Request("GET", "http://127.0.0.1/api"),
    )
    resp_200 = httpx.Response(
        status_code=200,
        text=json.dumps({"id": "p-1", "identifier": "KANBA", "name": "Kanban"}),
        request=httpx.Request("GET", "http://127.0.0.1/api"),
    )
    resp_empty = httpx.Response(
        status_code=200,
        text="[]",
        request=httpx.Request("GET", "http://127.0.0.1/api"),
    )

    call_count = 0

    async def mock_get(url: str, **kwargs: object) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return resp_429
        if "project" in url:
            return resp_200
        return resp_empty

    with patch("httpx.AsyncClient.get", side_effect=mock_get):
        out_dir = tmp_path / "fetched"
        result_dir = await client.fetch_snapshot(
            base_url="http://127.0.0.1:8000",
            workspace_slug="demo",
            project_identifier="KANBA",
            out_dir=out_dir,
            api_key="test-api-key",
        )
        assert result_dir == out_dir
        assert (out_dir / "project.json").exists()
        assert call_count > 1


def test_dns_resolution_failure() -> None:
    """Verify validate_target_url raises PlaneSecurityError on DNS failure."""
    import socket

    with patch("socket.getaddrinfo", side_effect=socket.gaierror("Name or service not known")):
        with pytest.raises(PlaneSecurityError, match="DNS resolution failed"):
            validate_target_url("https://unknown-domain-xyz.invalid/api")


def test_load_bundle_with_subdirectories_and_links_file(tmp_path: Path) -> None:
    """Verify loading bundle with issues/ and comments/ dirs and links.json."""
    bundle_dir = tmp_path / "bundle_subdirs"
    bundle_dir.mkdir()
    (bundle_dir / "projects.json").write_text(
        json.dumps([{"id": "p-sub", "identifier": "SUB", "name": "Sub Project"}]),
        encoding="utf-8",
    )
    issues_dir = bundle_dir / "issues"
    issues_dir.mkdir()
    (issues_dir / "001.json").write_text(
        json.dumps([{"id": "iss-1", "project": "p-sub", "sequence_id": 1, "name": "Issue One"}]),
        encoding="utf-8",
    )
    comments_dir = bundle_dir / "comments"
    comments_dir.mkdir()
    (comments_dir / "001.json").write_text(
        json.dumps([{"id": "comm-1", "issue": "iss-1", "comment_html": "<p>Hello</p>"}]),
        encoding="utf-8",
    )
    (bundle_dir / "links.json").write_text(
        json.dumps([{"id": "rel-1", "issue": "iss-1", "relation_type": "relates_to"}]),
        encoding="utf-8",
    )

    client = PlaneClient()
    bundle = client.load_bundle_from_dir(bundle_dir)
    assert len(bundle.projects) == 1
    assert len(bundle.issues) == 1
    assert len(bundle.comments) == 1
    assert len(bundle.relations) == 1


@pytest.mark.asyncio
async def test_fetch_snapshot_http_error(tmp_path: Path) -> None:
    """Verify fetch_snapshot raises PlaneClientError on HTTP 500 error."""
    client = PlaneClient(allow_loopback_http=True)
    resp_500 = httpx.Response(
        status_code=500,
        text="Internal Server Error",
        request=httpx.Request("GET", "http://127.0.0.1/api"),
    )
    with patch("httpx.AsyncClient.get", return_value=resp_500):
        with pytest.raises(PlaneClientError, match="failed with status 500"):
            await client.fetch_snapshot(
                base_url="http://127.0.0.1:8000",
                workspace_slug="demo",
                project_identifier="KANBA",
                out_dir=tmp_path / "fetched",
                api_key="test-api-key",
            )


@pytest.mark.asyncio
async def test_fetch_snapshot_oversized_response(tmp_path: Path) -> None:
    """Verify fetch_snapshot raises PlaneClientError on oversized page content."""
    client = PlaneClient(allow_loopback_http=True)
    resp_large = httpx.Response(
        status_code=200,
        content=b"x" * (MAX_PAGE_BYTES + 1),
        request=httpx.Request("GET", "http://127.0.0.1/api"),
    )
    with patch("httpx.AsyncClient.get", return_value=resp_large):
        with pytest.raises(PlaneClientError, match="exceeded 25 MiB limit"):
            await client.fetch_snapshot(
                base_url="http://127.0.0.1:8000",
                workspace_slug="demo",
                project_identifier="KANBA",
                out_dir=tmp_path / "fetched",
                api_key="test-api-key",
            )


@pytest.mark.asyncio
async def test_fetch_snapshot_max_retries_exceeded(tmp_path: Path) -> None:
    """Verify fetch_snapshot raises PlaneClientError when 429 retries are exhausted."""
    client = PlaneClient(allow_loopback_http=True)
    resp_429 = httpx.Response(
        status_code=429,
        headers={"Retry-After": "0.001"},
        request=httpx.Request("GET", "http://127.0.0.1/api"),
    )
    with patch("httpx.AsyncClient.get", return_value=resp_429):
        with pytest.raises(PlaneClientError, match="Exceeded max retries"):
            await client.fetch_snapshot(
                base_url="http://127.0.0.1:8000",
                workspace_slug="demo",
                project_identifier="KANBA",
                out_dir=tmp_path / "fetched",
                api_key="test-api-key",
            )
