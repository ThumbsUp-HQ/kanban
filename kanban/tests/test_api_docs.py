"""Unit tests for OpenAPI redirect, API docs, and Web App Manifest (KANBA-228)."""

import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from kanban.api_docs import (
    DOCS_CSS,
    MANIFEST_BYTES,
    _group_operations_by_tag,
    _render_opblock,
    _render_params_table,
    _render_redoc_endpoint_card,
    _render_responses_table,
    get_redoc_html,
    get_swagger_ui_html,
    render_redoc_html,
    render_swagger_ui_html,
)
from kanban.app import create_app
from kanban.security.headers import CSP_POLICY
from kanban.settings import Settings


@pytest.fixture
def dummy_dist(tmp_path: Path) -> Path:
    """Fixture providing isolated settings with dummy web_dist directory."""
    dist_dir = tmp_path / "web_dist"
    dist_dir.mkdir()
    index_file = dist_dir / "index.html"
    index_file.write_text("<!doctype html><html><body>SPA Shell</body></html>", encoding="utf-8")
    return dist_dir


@pytest.fixture
def test_settings(dummy_dist: Path) -> Settings:
    """Fixture providing isolated settings."""
    return Settings(
        web_dist=dummy_dist,
        deployment_mode="production",
    )


@pytest.mark.asyncio
async def test_openapi_redirect_endpoint(test_settings: Settings) -> None:
    """Test GET /openapi.json redirects (307) to /api/openapi.json and HEAD also redirects."""
    app = create_app(test_settings)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://localhost", follow_redirects=False
    ) as client:
        # GET /openapi.json returns 307
        resp_get = await client.get("/openapi.json")
        assert resp_get.status_code == 307
        assert resp_get.headers.get("location") == "/api/openapi.json"

        # HEAD /openapi.json returns 307
        resp_head = await client.head("/openapi.json")
        assert resp_head.status_code == 307
        assert resp_head.headers.get("location") == "/api/openapi.json"

    # Following redirects yields 200 OK and valid OpenAPI JSON schema
    async with httpx.AsyncClient(
        transport=transport, base_url="http://localhost", follow_redirects=True
    ) as client:
        resp_followed = await client.get("/openapi.json")
        assert resp_followed.status_code == 200
        assert resp_followed.headers.get("content-type") == "application/json"
        data = resp_followed.json()
        assert "openapi" in data
        assert data["info"]["title"] == "👍kanban API"


@pytest.mark.asyncio
async def test_api_openapi_json_direct(test_settings: Settings) -> None:
    """Test GET /api/openapi.json serves valid 200 OK schema."""
    app = create_app(test_settings)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as client:
        resp = await client.get("/api/openapi.json")
        assert resp.status_code == 200
        assert resp.headers.get("content-type") == "application/json"
        data = resp.json()
        assert data["openapi"].startswith("3.")
        assert len(data.get("paths", {})) > 0


@pytest.mark.asyncio
async def test_api_docs_swagger_ui_and_csp(test_settings: Settings) -> None:
    """Test GET /api/docs renders CSP-safe Swagger UI HTML without external CDNs."""
    app = create_app(test_settings)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as client:
        resp = await client.get("/api/docs")
        assert resp.status_code == 200
        assert "text/html" in resp.headers.get("content-type", "")
        # Verify strict CSP compliance
        assert resp.headers.get("content-security-policy") == CSP_POLICY
        assert resp.headers.get("x-content-type-options") == "nosniff"

        # Content assertions
        text = resp.text
        assert "<title>kanban API - Swagger UI</title>" in text
        assert "Swagger UI" in text
        assert '<link rel="stylesheet" href="/api/docs/docs.css"/>' in text
        assert '<link rel="manifest" href="/manifest.json"/>' in text
        assert "/api/openapi.json" in text
        assert "/api/redoc" in text
        assert "/docs" in text

        # Zero CDN references allowed
        assert "cdn.jsdelivr.net" not in text
        assert "unpkg.com" not in text
        assert "cdn.redoc.ly" not in text
        assert "<script" not in text

        # Second request exercises cached HTML path
        resp_cached = await client.get("/api/docs")
        assert resp_cached.status_code == 200
        assert resp_cached.text == text


@pytest.mark.asyncio
async def test_api_redoc_and_csp(test_settings: Settings) -> None:
    """Test GET /api/redoc renders CSP-safe ReDoc HTML without external CDNs."""
    app = create_app(test_settings)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as client:
        resp = await client.get("/api/redoc")
        assert resp.status_code == 200
        assert "text/html" in resp.headers.get("content-type", "")
        # Verify strict CSP compliance
        assert resp.headers.get("content-security-policy") == CSP_POLICY
        assert resp.headers.get("x-content-type-options") == "nosniff"

        # Content assertions
        text = resp.text
        assert "<title>kanban API - ReDoc</title>" in text
        assert "ReDoc" in text
        assert '<link rel="stylesheet" href="/api/docs/docs.css"/>' in text
        assert '<link rel="manifest" href="/manifest.json"/>' in text
        assert "/api/openapi.json" in text
        assert "/api/docs" in text
        assert "/docs" in text

        # Zero CDN references allowed
        assert "cdn.jsdelivr.net" not in text
        assert "unpkg.com" not in text
        assert "cdn.redoc.ly" not in text
        assert "<script" not in text

        # Second request exercises cached HTML path
        resp_cached = await client.get("/api/redoc")
        assert resp_cached.status_code == 200
        assert resp_cached.text == text


@pytest.mark.asyncio
async def test_api_docs_css_endpoint(test_settings: Settings) -> None:
    """Test GET /api/docs/docs.css serves stylesheet with 200 OK and cache control."""
    app = create_app(test_settings)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as client:
        resp = await client.get("/api/docs/docs.css")
        assert resp.status_code == 200
        assert "text/css" in resp.headers.get("content-type", "")
        assert "public, max-age=86400" in resp.headers.get("cache-control", "")
        assert resp.text.strip() == DOCS_CSS.strip()


@pytest.mark.asyncio
async def test_docs_spa_route_disambiguation(test_settings: Settings) -> None:
    """Test /docs and /docs/subpage render SPA index.html, not Swagger UI or ReDoc."""
    app = create_app(test_settings)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as client:
        # GET /docs serves SPA shell
        resp_docs = await client.get("/docs")
        assert resp_docs.status_code == 200
        assert "SPA Shell" in resp_docs.text
        assert "Swagger UI" not in resp_docs.text
        assert "ReDoc" not in resp_docs.text

        # GET /docs/knowledge-page serves SPA shell
        resp_sub = await client.get("/docs/knowledge-page")
        assert resp_sub.status_code == 200
        assert "SPA Shell" in resp_sub.text


@pytest.mark.asyncio
async def test_manifest_endpoints(test_settings: Settings) -> None:
    """Test GET /manifest.json and /manifest.webmanifest serve valid PWA manifest."""
    app = create_app(test_settings)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as client:
        for path in ("/manifest.json", "/manifest.webmanifest"):
            resp = await client.get(path)
            assert resp.status_code == 200
            assert resp.headers.get("content-type") == "application/manifest+json"
            assert "public, max-age=86400" in resp.headers.get("cache-control", "")
            data = resp.json()
            assert data["name"] == "👍kanban"
            assert data["short_name"] == "👍kanban"
            assert data["start_url"] == "/"
            assert data["display"] == "standalone"
            assert data["theme_color"] == "#1d4ed8"
            assert data["background_color"] == "#f7f8fa"
            assert isinstance(data["icons"], list)
            assert data["icons"][0]["src"] == "/favicon.ico"
            assert data["icons"][0]["type"] == "image/svg+xml"


def test_api_docs_helpers_standalone_coverage() -> None:
    """Unit tests for standalone helper functions in kanban.api_docs for full coverage."""
    sample_schema: dict[str, Any] = {
        "openapi": "3.1.0",
        "info": {
            "title": "👍kanban API",
            "version": "1.2.3",
            "description": "Test custom description",
        },
        "paths": {
            "/api/v1/custom-get": {
                "get": {
                    "summary": "Custom GET summary",
                    "description": "Detailed description of custom GET",
                    "tags": ["custom-tag"],
                    "parameters": [
                        {
                            "name": "limit",
                            "in": "query",
                            "required": False,
                            "schema": {"type": "integer"},
                            "description": "Max results",
                        },
                        {
                            "name": "id",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "string"},
                            "description": "Resource identifier",
                        },
                    ],
                    "responses": {
                        "200": {"description": "Successful retrieval"},
                        "404": {"description": "Resource not found"},
                        "500": {"description": "Internal server error"},
                    },
                },
                "options": {
                    "summary": "Ignore options",
                },
            },
            "/api/v1/fallback-tag": {
                "post": {
                    "summary": "",
                    "description": "",
                    # No tags specified, falls back to ['default']
                    "parameters": [],
                    "responses": {
                        "201": "Direct string description",
                    },
                },
            },
        },
    }

    # Test group operations
    grouped = _group_operations_by_tag(sample_schema["paths"])
    assert "custom-tag" in grouped
    assert "default" in grouped
    assert len(grouped["custom-tag"]) == 1
    assert len(grouped["default"]) == 1

    # Test params table
    params_html = _render_params_table(
        sample_schema["paths"]["/api/v1/custom-get"]["get"]["parameters"]
    )
    assert any("limit" in line for line in params_html)
    assert any("query" in line for line in params_html)

    # Test responses table
    resp_html = _render_responses_table(
        sample_schema["paths"]["/api/v1/custom-get"]["get"]["responses"]
    )
    assert any("status-2xx" in line for line in resp_html)
    assert any("status-4xx" in line for line in resp_html)
    assert any("status-5xx" in line for line in resp_html)

    # Test opblock render
    op_lines = _render_opblock(
        "GET",
        "/api/v1/custom-get",
        sample_schema["paths"]["/api/v1/custom-get"]["get"],
    )
    assert any("Custom GET summary" in line for line in op_lines)
    assert any("curl -X GET" in line for line in op_lines)

    # Test redoc endpoint card
    redoc_lines = _render_redoc_endpoint_card(
        "GET",
        "/api/v1/custom-get",
        sample_schema["paths"]["/api/v1/custom-get"]["get"],
    )
    assert any("Custom GET summary" in line for line in redoc_lines)
    assert any("curl -X GET" in line for line in redoc_lines)

    # Test complete renders
    swagger_rendered = render_swagger_ui_html(sample_schema)
    assert "Test custom description" in swagger_rendered
    assert "custom-tag" in swagger_rendered

    redoc_rendered = render_redoc_html(sample_schema)
    assert "Test custom description" in redoc_rendered
    assert "custom-tag" in redoc_rendered

    # Test caching functions
    c_swag = get_swagger_ui_html(sample_schema)
    assert c_swag is not None
    c_redoc = get_redoc_html(sample_schema)
    assert c_redoc is not None

    # Test manifest bytes
    loaded_manifest = json.loads(MANIFEST_BYTES.decode("utf-8"))
    assert loaded_manifest["name"] == "👍kanban"
