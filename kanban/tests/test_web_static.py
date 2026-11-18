"""Unit tests for PrecompressedSPAStaticApp and asset negotiation."""

import contextlib
import gzip
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest
from starlette.types import Message, Scope

from kanban.app import create_app
from kanban.settings import Settings
from kanban.web_static import PrecompressedSPAStaticApp


@pytest.fixture
def static_dist(tmp_path: Path) -> Path:
    """Fixture populating a test static distribution directory."""
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir()

    # index.html
    index_file = dist_dir / "index.html"
    index_file.write_bytes(b"<!doctype html><html><body>Root App</body></html>")

    # assets/
    assets_dir = dist_dir / "assets"
    assets_dir.mkdir()

    # app.js and compressed variants
    js_raw = b"console.log('identity js content');" * 20
    js_br = b"BR_COMPRESSED_DATA_CONTENT"
    js_gz = gzip.compress(js_raw, mtime=0)

    (assets_dir / "app.js").write_bytes(js_raw)
    (assets_dir / "app.js.br").write_bytes(js_br)
    (assets_dir / "app.js.gz").write_bytes(js_gz)

    # Stylesheet
    css_raw = b"body { background: #fff; }"
    (assets_dir / "style.css").write_bytes(css_raw)

    return dist_dir


@pytest.mark.asyncio
async def test_precompressed_encoding_negotiation(static_dist: Path) -> None:
    """Test Accept-Encoding negotiation prefers br, then gzip, then identity."""
    settings = Settings(web_dist=static_dist)
    app = create_app(settings)
    transport = httpx.ASGITransport(app=app)
    expected_js_raw = b"console.log('identity js content');" * 20
    expected_js_gz = gzip.compress(expected_js_raw, mtime=0)

    async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as client:
        # Prefer Brotli when both br and gzip are acceptable
        r_br = await client.get("/assets/app.js", headers={"Accept-Encoding": "br, gzip"})
        assert r_br.status_code == 200
        assert r_br.content == b"BR_COMPRESSED_DATA_CONTENT"
        assert r_br.headers.get("content-encoding") == "br"
        assert r_br.headers.get("vary") == "Accept-Encoding"
        assert r_br.headers.get("content-type") == "text/javascript; charset=utf-8"
        assert "immutable" in r_br.headers.get("cache-control", "")

        # Prefer Gzip when br is not accepted (httpx automatically decodes gzip payload)
        r_gz = await client.get("/assets/app.js", headers={"Accept-Encoding": "gzip"})
        assert r_gz.status_code == 200
        assert r_gz.content == expected_js_raw
        assert r_gz.headers.get("content-encoding") == "gzip"

        # Verify wire-level Gzip payload via streaming
        async with client.stream(
            "GET", "/assets/app.js", headers={"Accept-Encoding": "gzip"}
        ) as s_gz:
            assert b"".join([c async for c in s_gz.aiter_raw()]) == expected_js_gz

        # Explicit q=0 for br with gzip acceptable
        r_q0 = await client.get("/assets/app.js", headers={"Accept-Encoding": "br;q=0, gzip"})
        assert r_q0.status_code == 200
        assert r_q0.content == expected_js_raw
        assert r_q0.headers.get("content-encoding") == "gzip"

        # No Accept-Encoding header serves identity
        r_id = await client.get("/assets/app.js", headers={"Accept-Encoding": ""})
        assert r_id.status_code == 200
        assert r_id.content == expected_js_raw
        assert "content-encoding" not in r_id.headers

        # ETag revalidation with If-None-Match
        etag = r_br.headers.get("etag")
        assert etag is not None
        r_304 = await client.get(
            "/assets/app.js",
            headers={"Accept-Encoding": "br, gzip", "If-None-Match": etag},
        )
        assert r_304.status_code == 304
        assert r_304.headers.get("etag") == etag
        assert r_304.headers.get("vary") == "Accept-Encoding"
        assert len(r_304.content) == 0


@pytest.mark.asyncio
async def test_spa_fallback_routing(static_dist: Path) -> None:
    """Test SPA fallback serves index.html for client-side navigation paths."""
    settings = Settings(web_dist=static_dist)
    app = create_app(settings)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as client:
        # Client-side router path without dot serves index.html
        resp = await client.get("/projects/KAN/board")
        assert resp.status_code == 200
        assert b"Root App" in resp.content
        assert resp.headers.get("cache-control") == "no-cache"

        # Missing file with extension must NOT fallback; returns 404 plain text
        missing_file_resp = await client.get("/assets/missing.js")
        assert missing_file_resp.status_code == 404
        assert missing_file_resp.text == "Not Found"

        # Reserved prefix /api must not trigger SPA fallback
        api_resp = await client.get("/api/v2/x")
        assert api_resp.status_code == 404
        assert api_resp.headers.get("content-type") == "application/problem+json"


@pytest.mark.asyncio
async def test_security_and_path_traversal_guards(static_dist: Path, tmp_path: Path) -> None:
    """Test path traversal, null bytes, backslashes, and symlinks outside root are rejected."""
    # Create external secret file outside static_dist
    secret_dir = tmp_path / "secret_dir"
    secret_dir.mkdir()
    secret_file = secret_dir / "secret.txt"
    secret_file.write_bytes(b"TOP_SECRET_CREDENTIAL")

    # Symlink inside static_dist pointing outside
    symlink_file = static_dist / "leak.txt"
    with contextlib.suppress(OSError):
        symlink_file.symlink_to(secret_file)

    settings = Settings(web_dist=static_dist)
    app = create_app(settings)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as client:
        # Directory traversal attacks
        traversal_attempts = [
            "/../pyproject.toml",
            "/%2e%2e/secret",
            "/assets/%00.js",
            "/assets\\x.js",
        ]
        for path in traversal_attempts:
            resp = await client.get(path)
            assert resp.status_code == 404

        # Symlink escape
        if symlink_file.is_symlink():
            resp_symlink = await client.get("/leak.txt")
            assert resp_symlink.status_code == 404

        # HTTP method not allowed: POST to static app returns 405 with Allow header
        resp_post = await client.post("/")
        assert resp_post.status_code == 405
        assert resp_post.headers.get("allow") == "GET, HEAD"


@pytest.mark.asyncio
async def test_head_method_and_size_boundary(static_dist: Path) -> None:
    """Test HEAD requests and oversized file rejection."""
    # Create file slightly larger than 50 MiB limit using sparse file
    large_file = static_dist / "assets" / "oversized.bin"
    with large_file.open("wb") as f:
        f.seek(50 * 1024 * 1024)
        f.write(b"X")

    settings = Settings(web_dist=static_dist)
    app = create_app(settings)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as client:
        # HEAD request on valid file returns headers with Content-Length and empty body
        resp_head = await client.head("/assets/style.css")
        assert resp_head.status_code == 200
        assert int(resp_head.headers.get("content-length", "0")) > 0
        assert len(resp_head.content) == 0

        # Oversized file > 50 MiB returns 404
        resp_large = await client.get("/assets/oversized.bin")
        assert resp_large.status_code == 404


@pytest.mark.asyncio
async def test_non_asset_file_caching_and_asgi_scope(static_dist: Path) -> None:
    """Test non-assets static files receive no-cache and non-http scopes return early."""
    # Create a non-asset file at root (e.g. robots.txt)
    robots_file = static_dist / "robots.txt"
    robots_file.write_text("User-agent: *\nDisallow: /", encoding="utf-8")

    settings = Settings(web_dist=static_dist)
    app = create_app(settings)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as client:
        # Non-assets static file should receive no-cache
        resp = await client.get("/robots.txt")
        assert resp.status_code == 200
        assert resp.headers.get("cache-control") == "no-cache"
        assert "User-agent" in resp.text

        # Invalid q-value parse error falls back to q=0.0
        resp_bad_q = await client.get(
            "/assets/app.js",
            headers={"Accept-Encoding": "gzip;q=invalid, *;q=0.5"},
        )
        assert resp_bad_q.status_code == 200

    # Non-http scope test directly on PrecompressedSPAStaticApp
    static_app = PrecompressedSPAStaticApp(dist_dir=static_dist)
    sent_messages: list[Message] = []

    async def dummy_receive() -> Message:
        return {"type": "http.request"}

    async def dummy_send(msg: Message) -> None:
        sent_messages.append(msg)

    # Lifespan scope returns early without sending anything
    scope: Scope = {"type": "lifespan", "asgi": {"version": "3.0"}}
    await static_app(scope, dummy_receive, dummy_send)
    assert len(sent_messages) == 0

    # Missing index.html fallback coverage
    empty_dist = static_dist.parent / "empty_dist"
    empty_dist.mkdir()
    empty_settings = Settings(web_dist=empty_dist)
    empty_app = create_app(empty_settings)
    empty_transport = httpx.ASGITransport(app=empty_app)
    async with httpx.AsyncClient(transport=empty_transport, base_url="http://localhost") as c:
        resp_no_index = await c.get("/some/route")
        assert resp_no_index.status_code == 404


@pytest.mark.asyncio
async def test_precompressed_webmanifest_mime_and_cache(tmp_path: Path) -> None:
    """Test PrecompressedSPAStaticApp serves webmanifest files with correct MIME and caching."""
    dist_dir = tmp_path / "manifest_dist"
    dist_dir.mkdir()
    manifest_bytes = b'{"name": "test-app", "display": "standalone"}'
    (dist_dir / "manifest.json").write_bytes(manifest_bytes)
    (dist_dir / "manifest.webmanifest").write_bytes(manifest_bytes)
    (dist_dir / "index.html").write_bytes(b"<!doctype html><html></html>")

    app = PrecompressedSPAStaticApp(dist_dir=dist_dir)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as client:
        # Test manifest.json served from disk
        r_json = await client.get("/manifest.json")
        assert r_json.status_code == 200
        assert r_json.headers.get("content-type") == "application/manifest+json"
        assert r_json.headers.get("cache-control") == "public, max-age=86400"

        # Test manifest.webmanifest served from disk
        r_webmanifest = await client.get("/manifest.webmanifest")
        assert r_webmanifest.status_code == 200
        assert r_webmanifest.headers.get("content-type") == "application/manifest+json"
        assert r_webmanifest.headers.get("cache-control") == "public, max-age=86400"


@pytest.mark.asyncio
async def test_web_static_encoding_and_resolution_edge_cases(tmp_path: Path) -> None:
    """Test PrecompressedSPAStaticApp encodings, multi-ETag, and symlink defenses."""
    dist_dir = tmp_path / "edge_dist"
    dist_dir.mkdir()
    (dist_dir / "index.html").write_bytes(b"<!doctype html><html></html>")
    normal_file = dist_dir / "normal.txt"
    normal_file.write_bytes(b"hello world")

    # Outside symlink test
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    outside_file = outside_dir / "secret.txt"
    outside_file.write_bytes(b"top secret")
    symlink_target = dist_dir / "symlink_escape.txt"
    symlink_target.symlink_to(outside_file)

    outside_index = outside_dir / "outside_index.html"
    outside_index.write_bytes(b"outside index")
    symlink_index_dist = tmp_path / "symlink_index_dist"
    symlink_index_dist.mkdir()
    (symlink_index_dist / "index.html").symlink_to(outside_index)

    static_app = PrecompressedSPAStaticApp(dist_dir=dist_dir)
    transport = httpx.ASGITransport(app=static_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as client:
        # Accept-encoding parsing branch with non-q parameters and invalid q-value
        resp_enc = await client.get(
            "/normal.txt",
            headers={"Accept-Encoding": "gzip; other_param=1; q=0.8, br; q=invalid"},
        )
        assert resp_enc.status_code == 200

        # Multi-value ETag matching branch
        etag = resp_enc.headers.get("etag")
        assert etag is not None
        resp_304 = await client.get(
            "/normal.txt",
            headers={"If-None-Match": f'"other-tag", {etag}'},
        )
        assert resp_304.status_code == 304

        resp_nomatch = await client.get(
            "/normal.txt",
            headers={"If-None-Match": '"other-tag", "different-tag"'},
        )
        assert resp_nomatch.status_code == 200

        # Symlink escape outside dist_dir returns 404 (line 86-87 branch)
        resp_symlink = await client.get("/symlink_escape.txt")
        assert resp_symlink.status_code == 404

    # Symlink index outside dist_dir returns None for fallback
    symlink_app = PrecompressedSPAStaticApp(dist_dir=symlink_index_dist)
    symlink_transport = httpx.ASGITransport(app=symlink_app)
    async with httpx.AsyncClient(
        transport=symlink_transport, base_url="http://localhost"
    ) as client:
        resp_out_fallback = await client.get("/extensionless/route")
        assert resp_out_fallback.status_code == 404


@pytest.mark.asyncio
async def test_web_static_io_errors_and_limits(tmp_path: Path) -> None:
    """Test PrecompressedSPAStaticApp I/O error handling, method checks, and file limits."""
    dist_dir = tmp_path / "io_dist"
    dist_dir.mkdir()
    (dist_dir / "index.html").write_bytes(b"<!doctype html><html></html>")
    (dist_dir / "empty.txt").write_bytes(b"")
    normal_file = dist_dir / "normal.txt"
    normal_file.write_bytes(b"hello world")

    static_app = PrecompressedSPAStaticApp(dist_dir=dist_dir)
    transport = httpx.ASGITransport(app=static_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as client:
        # Method not allowed (405)
        resp_post = await client.post("/normal.txt")
        assert resp_post.status_code == 405
        assert "allow" in resp_post.headers

        # Empty 0-byte file (line 248 branch)
        resp_empty = await client.get("/empty.txt")
        assert resp_empty.status_code == 200
        assert resp_empty.content == b""

        # Oversized file (> 50MB) returns 404 via patched limit
        with patch("kanban.web_static._MAX_FILE_SIZE", 5):
            resp_oversize = await client.get("/normal.txt")
            assert resp_oversize.status_code == 404

        # Target file resolve raises OSError returns 404
        with patch.object(Path, "resolve", side_effect=OSError("Disk failure")):
            resp_res_err = await client.get("/normal.txt")
            assert resp_res_err.status_code == 404

            resp_fallback_err = await client.get("/route")
            assert resp_fallback_err.status_code == 404

        # SPA fallback non-relative index returns 404
        with patch.object(Path, "is_relative_to", return_value=False):
            resp_non_rel = await client.get("/route")
            assert resp_non_rel.status_code == 404

        # Read_bytes raises OSError returns 404
        with patch.object(Path, "read_bytes", side_effect=OSError("Read error")):
            resp_read_err = await client.get("/normal.txt")
            assert resp_read_err.status_code == 404

        # Stat raises OSError returns 404
        with (
            patch.object(
                PrecompressedSPAStaticApp,
                "_resolve_file",
                return_value=(normal_file, False),
            ),
            patch.object(Path, "stat", side_effect=OSError("Disk error")),
        ):
            resp_stat_err = await client.get("/normal.txt")
            assert resp_stat_err.status_code == 404
