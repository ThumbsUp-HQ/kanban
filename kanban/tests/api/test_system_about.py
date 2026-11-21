# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Integration and unit tests for System About and CycloneDX 1.5 SBOM endpoints (KAN-34)."""

from __future__ import annotations

import subprocess
import uuid
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI

from kanban.api.deps import PrincipalContext, get_principal
from kanban.api.problems import ProblemException, problem_exception_handler
from kanban.api.v1 import build_v1_router
from kanban.api.v1.system import get_platform_summary
from kanban.app import create_app
from kanban.ops.build_info import (
    compute_openapi_bundle_hash,
    get_build_info,
    resolve_build_timestamp,
    resolve_frontend_bundle_hash,
    resolve_git_commit,
)
from kanban.settings import Settings


def _create_test_app() -> FastAPI:
    """Create test FastAPI instance with v1 router and problem exception handler."""
    app = FastAPI()
    app.add_exception_handler(ProblemException, problem_exception_handler)  # type: ignore[arg-type]
    v1 = build_v1_router()
    app.include_router(v1, prefix="/api/v1")
    return app


@pytest.fixture
def test_principal() -> PrincipalContext:
    """Fixture providing standard authenticated user principal."""
    return PrincipalContext(
        principal_id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        aal_level=1,
    )


@pytest.mark.asyncio
async def test_system_about_unauthenticated_returns_401() -> None:
    """Unauthenticated request to /api/v1/system/about returns 401."""
    app = _create_test_app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        resp = await client.get("/api/v1/system/about")
        assert resp.status_code == 401
        data = resp.json()
        assert data["code"] == "AUTHENTICATION_REQUIRED"


@pytest.mark.asyncio
async def test_system_about_authenticated_returns_full_metadata(
    test_principal: PrincipalContext,
) -> None:
    """Authenticated request to /api/v1/system/about returns 200 with platform details."""
    app = _create_test_app()
    app.dependency_overrides[get_principal] = lambda: test_principal

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        resp = await client.get("/api/v1/system/about")
        assert resp.status_code == 200
        data = resp.json()

        assert data["platform"] == "👍kanban"
        assert data["slug"] == "thumbs-up-kanban"
        assert data["tagline"] == "The difference between a swarm and an Agile team is a kanban."
        assert data["version"] == "2.0.0"
        assert data["license_spdx"] == "Apache-2.0"

        # Build and bundle metadata (KAN-57)
        assert data["git_commit"] is not None
        assert "build_timestamp" in data
        assert data["openapi_version"] == "2.0.0"
        assert data["openapi_bundle_hash"] is not None
        assert len(data["openapi_bundle_hash"]) == 64
        assert "frontend_bundle_hash" in data

        # Interactive API Documentation URLs
        api_docs = data["api_docs_urls"]
        assert api_docs["swagger_ui"] == "/api/docs"
        assert api_docs["redoc"] == "/api/redoc"
        assert api_docs["openapi_json"] == "/api/openapi.json"

        # Verbatim texts
        assert "Apache License" in data["license"]
        assert "Version 2.0" in data["license"]
        assert "Kanban Platform" in data["notice"]
        assert data["license_text"] == data["license"]
        assert data["notice_text"] == data["notice"]

        # SBOM summary and components
        summary = data["sbom_summary"]
        assert summary["total_components"] > 10
        assert summary["python_components"] > 0
        assert summary["permissive_count"] > 0
        assert summary["deny_count"] == 0

        components = data["components"]
        assert len(components) == summary["total_components"]
        assert any(c["name"] == "fastapi" for c in components)
        fastapi_comp = next(c for c in components if c["name"] == "fastapi")
        assert fastapi_comp["ecosystem"] == "python"
        assert fastapi_comp["license_verdict"] == "ALLOW"
        assert fastapi_comp["purl"].startswith("pkg:pypi/fastapi@")


@pytest.mark.asyncio
async def test_system_sbom_unauthenticated_returns_401() -> None:
    """Unauthenticated request to /api/v1/system/sbom returns 401."""
    app = _create_test_app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        resp = await client.get("/api/v1/system/sbom")
        assert resp.status_code == 401


@pytest.mark.asyncio
async def test_system_sbom_authenticated_inline_json(
    test_principal: PrincipalContext,
) -> None:
    """Authenticated GET /api/v1/system/sbom returns valid CycloneDX 1.5 JSON."""
    app = _create_test_app()
    app.dependency_overrides[get_principal] = lambda: test_principal

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        resp = await client.get("/api/v1/system/sbom")
        assert resp.status_code == 200
        assert "application/vnd.cyclonedx+json" in resp.headers["content-type"]
        assert resp.headers["x-content-type-options"] == "nosniff"
        assert "content-disposition" not in resp.headers

        data = resp.json()
        assert data["bomFormat"] == "CycloneDX"
        assert data["specVersion"] == "1.5"
        assert data["serialNumber"].startswith("urn:uuid:")
        assert data["metadata"]["component"]["name"] == "thumbs-up-kanban"
        assert len(data["components"]) > 10


@pytest.mark.asyncio
async def test_system_sbom_authenticated_download_attachment(
    test_principal: PrincipalContext,
) -> None:
    """Authenticated GET /api/v1/system/sbom?download=true returns attachment header."""
    app = _create_test_app()
    app.dependency_overrides[get_principal] = lambda: test_principal

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        resp = await client.get("/api/v1/system/sbom?download=true")
        assert resp.status_code == 200
        assert resp.headers["x-content-type-options"] == "nosniff"
        assert (
            resp.headers["content-disposition"]
            == 'attachment; filename="thumbs-up-kanban-sbom-cdx-1.5.json"'
        )


@pytest.mark.asyncio
async def test_live_app_docs_and_openapi_endpoints_resolve_200() -> None:
    """Verify live FastAPI app mounts /api/docs, /api/redoc, and /api/openapi.json."""
    settings = Settings()
    app = create_app(settings)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        # 1. Swagger UI at /api/docs
        resp_swagger = await client.get("/api/docs")
        assert resp_swagger.status_code == 200
        assert "text/html" in resp_swagger.headers["content-type"]
        assert "SwaggerUIBundle" in resp_swagger.text or "swagger" in resp_swagger.text.lower()

        # 2. ReDoc at /api/redoc
        resp_redoc = await client.get("/api/redoc")
        assert resp_redoc.status_code == 200
        assert "text/html" in resp_redoc.headers["content-type"]
        assert "redoc" in resp_redoc.text.lower()

        # 3. OpenAPI specification at /api/openapi.json
        resp_openapi = await client.get("/api/openapi.json")
        assert resp_openapi.status_code == 200
        openapi_data = resp_openapi.json()
        assert "openapi" in openapi_data
        assert "/api/v1/system/about" in openapi_data["paths"]
        assert "/api/v1/system/sbom" in openapi_data["paths"]

        # 4. Root redirect /openapi.json -> /api/openapi.json
        resp_redirect = await client.get("/openapi.json", follow_redirects=False)
        assert resp_redirect.status_code == 307
        assert resp_redirect.headers["location"] == "/api/openapi.json"


@pytest.mark.asyncio
async def test_platform_summary_endpoints() -> None:
    """Verify /platform-summary and alias /summary return verified capability metadata."""
    app = _create_test_app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        resp1 = await client.get("/api/v1/system/platform-summary")
        assert resp1.status_code == 200
        data1 = resp1.json()
        assert data1["platform"] == "👍kanban"
        assert data1["pillar_1_agent_first"]["summary_token_budget"] == 1000

        resp2 = await client.get("/api/v1/system/summary")
        assert resp2.status_code == 200
        data2 = resp2.json()
        assert data2 == data1

    # Verify get_platform_summary with settings passed
    settings = Settings()
    summary = get_platform_summary(settings)
    assert summary.platform == "👍kanban"


def test_build_info_resolve_git_commit(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Verify resolve_git_commit honors env vars, git subprocess, and fallbacks."""
    # 1. KB_GIT_COMMIT precedence
    monkeypatch.setenv("KB_GIT_COMMIT", "commit-kb-123")
    monkeypatch.setenv("GIT_SHA", "commit-sha-456")
    assert resolve_git_commit() == "commit-kb-123"

    # 2. GIT_SHA fallback
    monkeypatch.delenv("KB_GIT_COMMIT", raising=False)
    assert resolve_git_commit() == "commit-sha-456"

    # 3. No env var -> subprocess or fallback
    monkeypatch.delenv("GIT_SHA", raising=False)
    commit = resolve_git_commit()
    assert commit is not None
    assert len(commit) > 0

    # 4. Failed subprocess in empty dir without git
    empty_dir = tmp_path / "not_a_git_repo"
    empty_dir.mkdir()
    fallback_commit = resolve_git_commit(cwd=empty_dir)
    assert fallback_commit == "unknown"

    # 5. Subprocess raises exception
    def _mock_raising_run(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        msg = "git binary unavailable"
        raise OSError(msg)

    monkeypatch.setattr(subprocess, "run", _mock_raising_run)
    assert resolve_git_commit() == "unknown"


def test_build_info_resolve_build_timestamp(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify resolve_build_timestamp returns string when set and None otherwise."""
    monkeypatch.setenv("KB_BUILD_TIMESTAMP", "2026-11-21T05:00:00Z")
    assert resolve_build_timestamp() == "2026-11-21T05:00:00Z"

    monkeypatch.delenv("KB_BUILD_TIMESTAMP", raising=False)
    assert resolve_build_timestamp() is None


def test_build_info_compute_openapi_bundle_hash() -> None:
    """Verify compute_openapi_bundle_hash produces deterministic SHA-256 fingerprint."""
    doc1 = {
        "paths": {"/api/v1/health": {"get": {"summary": "Health"}}},
        "components": {"schemas": {"HealthResponse": {"type": "object"}}},
    }
    doc2 = {
        "components": {"schemas": {"HealthResponse": {"type": "object"}}},
        "paths": {"/api/v1/health": {"get": {"summary": "Health"}}},
    }

    hash1 = compute_openapi_bundle_hash(doc1)
    hash2 = compute_openapi_bundle_hash(doc2)

    assert len(hash1) == 64
    assert hash1 == hash2

    # Empty document fallback
    empty_hash = compute_openapi_bundle_hash({})
    assert len(empty_hash) == 64


def test_build_info_resolve_frontend_bundle_hash(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Verify resolve_frontend_bundle_hash checks sri-manifest.json, index bundle, and env."""
    # 1. Nonexistent dist returns None
    assert resolve_frontend_bundle_hash(repo_root=tmp_path) is None

    # 2. Dist with sri-manifest.json
    fake_dist = tmp_path / "kanban" / "web" / "dist"
    fake_dist.mkdir(parents=True)
    manifest = fake_dist / "sri-manifest.json"
    manifest.write_text('{"entry": "abc"}', encoding="utf-8")
    assert resolve_frontend_bundle_hash(repo_root=tmp_path) is not None

    # 3. Dist with index-*.js in assets (no sri-manifest)
    manifest.unlink()
    assets = fake_dist / "assets"
    assets.mkdir()
    index_js = assets / "index-abc1234.js"
    index_js.write_text("console.log('test')", encoding="utf-8")
    assert resolve_frontend_bundle_hash(repo_root=tmp_path) is not None

    # 4. Custom KB_WEB_DIST env var
    custom_dist = tmp_path / "custom_dist"
    custom_dist.mkdir()
    custom_manifest = custom_dist / "sri-manifest.json"
    custom_manifest.write_text('{"custom": true}', encoding="utf-8")
    monkeypatch.setenv("KB_WEB_DIST", str(custom_dist))
    # With non-matching repo_root, falls back to env var
    empty_root = tmp_path / "empty_root"
    empty_root.mkdir()
    assert resolve_frontend_bundle_hash(repo_root=empty_root) is not None

    # 5. Empty assets directory without index-*.js returns None
    monkeypatch.delenv("KB_WEB_DIST", raising=False)
    index_js.unlink()
    assert resolve_frontend_bundle_hash(repo_root=tmp_path) is None

    # 6. Read failure on manifest and asset handles exceptions gracefully
    manifest.write_text('{"entry": "abc"}', encoding="utf-8")
    original_read_bytes = Path.read_bytes

    def _mock_raising_read(self_path: Path) -> bytes:
        if self_path.name in ("sri-manifest.json", "index-abc1234.js"):
            msg = "I/O failure"
            raise OSError(msg)
        return original_read_bytes(self_path)

    monkeypatch.setattr(Path, "read_bytes", _mock_raising_read)
    assert resolve_frontend_bundle_hash(repo_root=tmp_path) is None


def test_build_info_get_build_info(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify get_build_info builds complete BuildInfo instance."""
    monkeypatch.setenv("KB_GIT_COMMIT", "test-commit-sha")
    monkeypatch.setenv("KB_BUILD_TIMESTAMP", "2026-11-21T05:30:00Z")

    info = get_build_info(openapi_doc={"paths": {}, "components": {}})
    assert info.git_commit == "test-commit-sha"
    assert info.build_timestamp == "2026-11-21T05:30:00Z"
    assert info.openapi_version == "2.0.0"
    assert info.openapi_bundle_hash is not None
    assert len(info.openapi_bundle_hash) == 64

    # Without openapi_doc
    info_no_doc = get_build_info(openapi_doc=None)
    assert info_no_doc.openapi_bundle_hash is None
