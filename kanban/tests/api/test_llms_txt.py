# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Integration and unit tests for /llms.txt, /llms-full.txt, and skills catalog (KAN-80)."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import TYPE_CHECKING

import httpx
import pytest

from kanban.app import create_app

if TYPE_CHECKING:
    from fastapi import FastAPI
from kanban.ops.llms_txt import (
    ALLOWED_SKILL_SLUGS,
    MAX_LLMS_FULL_BYTES,
    MAX_LLMS_TXT_BYTES,
    MAX_SKILL_BYTES,
    get_llms_full_txt_content,
    get_llms_txt_content,
    get_skill_assets,
)
from kanban.settings import Settings


@pytest.fixture
def app() -> FastAPI:
    """Create test FastAPI application instance with all routes mounted."""
    settings = Settings()
    return create_app(settings)


@pytest.mark.asyncio
async def test_llms_txt_positive_get_and_head(app: FastAPI) -> None:  # noqa: PLR0915
    """Verify GET and HEAD /llms.txt returns 200, text/plain, valid ETag, and required content."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        # 1. GET /llms.txt
        res = await client.get("/llms.txt")
        assert res.status_code == 200
        assert "text/plain" in res.headers["content-type"]
        assert "charset=utf-8" in res.headers["content-type"].lower()
        assert res.headers.get("x-content-type-options") == "nosniff"
        assert res.headers.get("cache-control") == "public, max-age=300, must-revalidate"
        etag = res.headers.get("etag")
        assert etag is not None
        assert etag.startswith('"')
        assert etag.endswith('"')

        body_text = res.text
        raw_bytes = res.content
        assert len(raw_bytes) <= MAX_LLMS_TXT_BYTES

        # Verify Humans and Agents sections
        assert "## Humans" in body_text
        assert "## Agents" in body_text
        assert "Copy and paste the contents of `/llms.txt`" in body_text
        assert "Deliver this `/llms.txt` URL directly to your agent" in body_text
        assert "Claude Code, OpenAI Codex, Gemini CLI / Antigravity, Cursor" in body_text

        # Verify section ordering: ## Humans < ## Agents < ### 1. < ### 2. < ### 3. < ### 4.
        idx_humans = body_text.index("## Humans")
        idx_agents = body_text.index("## Agents")
        idx_sec1 = body_text.index("### 1. Platform & 3-Surface MCP Quick-Map")
        idx_sec2 = body_text.index("### 2. How to Create & Approach Tickets (kanban-ticket Rules)")
        idx_sec3 = body_text.index("### 3. Mandatory Interactive Onboarding Directive")
        idx_sec4 = body_text.index("### 4. Recommended Skills Catalog")
        assert idx_humans < idx_agents < idx_sec1 < idx_sec2 < idx_sec3 < idx_sec4

        # Negative checks: zero demoted numbered headings remain at ## level
        assert "\n## 1. " not in body_text
        assert "\n## 2. " not in body_text
        assert "\n## 3. " not in body_text
        assert "\n## 4. " not in body_text
        for line in body_text.splitlines():
            for i in (1, 2, 3, 4):
                assert not line.startswith(f"## {i}. "), f"Found demoted H2 heading: {line}"

        # Verify Platform & 3-Surface MCP Quick-Map
        assert "Platform & 3-Surface MCP Quick-Map" in body_text
        assert "/mcp/agent" in body_text
        assert "/mcp/docs" in body_text
        assert "/mcp/admin" in body_text
        assert "OAuth 2.1" in body_text
        assert "summary" in body_text
        assert "1,000-token" in body_text

        # Verify How to Create & Approach Tickets
        assert "How to Create & Approach Tickets" in body_text
        assert "Definition of Done" in body_text
        assert "Verification Proof" in body_text
        assert "reality-checker" in body_text

        # Verify Recommended Skills Catalog (4 skills)
        assert "Recommended Skills Catalog" in body_text
        for slug in ALLOWED_SKILL_SLUGS:
            assert f"/llms-skills/{slug}.md" in body_text

        # Verify Mandatory Interactive Onboarding Directive & 4 preference axes
        assert "Interview Before Writing Skills" in body_text
        assert "Axis 1 (Execution Topology)" in body_text
        assert "[1A] Single-Threaded" in body_text
        assert "[1B] Teamwork" in body_text
        assert "[1C] Multi-Agent Swarm" in body_text

        assert "Axis 2 (Token Budget & Model Tier)" in body_text
        assert "[2A] Quota-Sipping" in body_text
        assert "Flash 3.8" in body_text
        assert "[2B] Balanced Hybrid" in body_text
        assert "[2C] Unconstrained" in body_text
        assert "Sol MAX" in body_text
        assert "Claude Ultra" in body_text
        assert "Gemini Carbon" in body_text

        assert "Axis 3 (QA, Coverage & CI Rigor)" in body_text
        assert "[3A] Pragmatic" in body_text
        assert "[3B] Clean-Room Forensic" in body_text
        assert "reality-checker" in body_text

        assert "Axis 4 (Persistence Scope)" in body_text
        assert "[4A] Project" in body_text
        assert "[4B] Global" in body_text
        assert "[4C] Both" in body_text

        # Verify /llms-full.txt reference
        assert "/llms-full.txt" in body_text

        # 2. HEAD /llms.txt
        head_res = await client.head("/llms.txt")
        assert head_res.status_code == 200
        assert "text/plain" in head_res.headers["content-type"]
        assert head_res.headers.get("etag") == etag
        assert head_res.headers.get("content-length") == str(len(raw_bytes))
        assert head_res.content == b""

        # 3. Conditional GET with matching If-None-Match -> 304 Not Modified
        not_mod_res = await client.get("/llms.txt", headers={"If-None-Match": etag})
        assert not_mod_res.status_code == 304
        assert not_mod_res.headers.get("etag") == etag
        assert not_mod_res.content == b""

        # 4. Conditional GET with stale If-None-Match -> 200 OK
        stale_res = await client.get("/llms.txt", headers={"If-None-Match": '"stale-etag-value"'})
        assert stale_res.status_code == 200
        assert stale_res.text == body_text


@pytest.mark.asyncio
async def test_llms_full_txt_positive_get_and_head(app: FastAPI) -> None:
    """Verify GET and HEAD /llms-full.txt returns 200, concatenated skill bundle with delimiters."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        # 1. GET /llms-full.txt
        res = await client.get("/llms-full.txt")
        assert res.status_code == 200
        assert "text/plain" in res.headers["content-type"]
        assert "charset=utf-8" in res.headers["content-type"].lower()
        assert res.headers.get("x-content-type-options") == "nosniff"
        etag = res.headers.get("etag")
        assert etag is not None

        body_text = res.text
        raw_bytes = res.content
        assert len(raw_bytes) <= MAX_LLMS_FULL_BYTES

        # Verify standard /llms.txt header content is included
        assert "## Humans" in body_text
        assert "## Agents" in body_text
        assert "### 1. Platform & 3-Surface MCP Quick-Map" in body_text
        assert "Interview Before Writing Skills" in body_text
        assert "\n## 1. " not in body_text
        assert "\n## 2. " not in body_text
        assert "\n## 3. " not in body_text
        assert "\n## 4. " not in body_text
        for line in body_text.splitlines():
            for i in (1, 2, 3, 4):
                assert not line.startswith(f"## {i}. "), f"Found demoted H2 heading: {line}"

        # Verify all 4 skills are concatenated with clear delimiters
        for slug in ALLOWED_SKILL_SLUGS:
            assert f"<!-- BEGIN SKILL: {slug} -->" in body_text
            assert f"<!-- END SKILL: {slug} -->" in body_text

        # 2. HEAD /llms-full.txt
        head_res = await client.head("/llms-full.txt")
        assert head_res.status_code == 200
        assert head_res.headers.get("etag") == etag
        assert head_res.headers.get("content-length") == str(len(raw_bytes))
        assert head_res.content == b""

        # 3. Conditional GET with matching If-None-Match -> 304 Not Modified
        not_mod_res = await client.get("/llms-full.txt", headers={"If-None-Match": etag})
        assert not_mod_res.status_code == 304
        assert not_mod_res.content == b""


@pytest.mark.asyncio
async def test_llms_skills_endpoints_positive(app: FastAPI) -> None:
    """Verify GET and HEAD /llms-skills/{skill_slug}.md for all allowed skills."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        assets = get_skill_assets()
        for slug in ALLOWED_SKILL_SLUGS:
            res = await client.get(f"/llms-skills/{slug}.md")
            assert res.status_code == 200
            assert "text/markdown" in res.headers["content-type"]
            assert "charset=utf-8" in res.headers["content-type"].lower()
            assert res.headers.get("x-content-type-options") == "nosniff"
            assert res.headers.get("cache-control") == "public, max-age=300, must-revalidate"
            etag = res.headers.get("etag")
            assert etag is not None
            assert len(res.content) <= MAX_SKILL_BYTES
            assert res.text == assets[slug].content

            # HEAD request
            head_res = await client.head(f"/llms-skills/{slug}.md")
            assert head_res.status_code == 200
            assert head_res.headers.get("etag") == etag
            assert head_res.headers.get("content-length") == str(len(res.content))
            assert head_res.content == b""

            # Conditional GET 304
            not_mod = await client.get(
                f"/llms-skills/{slug}.md",
                headers={"If-None-Match": etag},
            )
            assert not_mod.status_code == 304
            assert not_mod.content == b""


@pytest.mark.asyncio
async def test_system_skills_catalog_endpoint(app: FastAPI) -> None:
    """Verify GET /api/v1/system/skills returns complete catalog and formatted onboarding prompt."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        res = await client.get("/api/v1/system/skills")
        assert res.status_code == 200
        data = res.json()

        assert data["llms_txt_url"] == "/llms.txt"
        assert data["llms_full_url"] == "/llms-full.txt"
        assert "onboarding_prompt" in data
        assert "interview me on Execution Mode" in data["onboarding_prompt"]

        skills = data["skills"]
        assert len(skills) == len(ALLOWED_SKILL_SLUGS)
        assets = get_skill_assets()
        for item in skills:
            slug = item["slug"]
            assert slug in ALLOWED_SKILL_SLUGS
            assert item["url"] == f"/llms-skills/{slug}.md"
            asset = assets[slug]
            assert item["title"] == asset.title
            assert item["summary"] == asset.summary
            assert item["install_path"] == asset.install_path
            assert item["bytes"] == asset.bytes
            assert item["sha256"] == asset.sha256
            assert item["estimated_tokens"] == asset.estimated_tokens
            assert item["bytes"] > 0
            assert item["estimated_tokens"] > 0


@pytest.mark.asyncio
async def test_negative_and_security_cases(app: FastAPI) -> None:
    """Verify 404 ProblemDetails, 405 on disallowed methods, and security headers."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        # 1. Unknown skill slug -> 404 ProblemDetails
        res404 = await client.get("/llms-skills/unknown-skill.md")
        assert res404.status_code == 404
        assert "application/problem+json" in res404.headers["content-type"]
        problem = res404.json()
        assert problem["title"] == "Not Found"
        assert problem["status"] == 404

        # 2. Path traversal slug attempt -> 404 ProblemDetails
        res_trav = await client.get("/llms-skills/..%2Fetc%2Fpasswd.md")
        assert res_trav.status_code == 404
        assert "application/problem+json" in res_trav.headers["content-type"]

        # 3. Missing .md suffix -> 404 ProblemDetails
        res_no_ext = await client.get("/llms-skills/kanban-ticket")
        assert res_no_ext.status_code == 404

        # 4. Disallowed HTTP methods -> 405 Method Not Allowed
        res_post_txt = await client.post("/llms.txt", content=b"attack")
        assert res_post_txt.status_code == 405
        assert "Allow" in res_post_txt.headers
        assert "GET" in res_post_txt.headers["Allow"]
        assert "HEAD" in res_post_txt.headers["Allow"]

        res_post_full = await client.post("/llms-full.txt", content=b"attack")
        assert res_post_full.status_code == 405
        assert "Allow" in res_post_full.headers

        res_post_skill = await client.post("/llms-skills/kanban-ticket.md", content=b"attack")
        assert res_post_skill.status_code == 405
        assert "Allow" in res_post_skill.headers

        res_put = await client.put("/llms.txt", content=b"attack")
        assert res_put.status_code == 405

        res_del = await client.delete("/llms.txt")
        assert res_del.status_code == 405

        # 5. Host header control characters / CRLF rejection
        res_crlf = await client.get("/llms.txt", headers={"Host": "localhost\r\nInjected: 1"})
        assert res_crlf.status_code == 400
        assert "application/problem+json" in res_crlf.headers["content-type"]

        # 6. Hardened security headers enforced by SecurityHeadersMiddleware
        get_res = await client.get("/llms.txt")
        assert get_res.headers.get("x-frame-options") == "DENY"
        assert get_res.headers.get("referrer-policy") == "no-referrer"
        assert "default-src 'none'" in get_res.headers.get("content-security-policy", "")


def test_content_invariants_and_byte_budgets() -> None:
    """Verify byte budgets, zero UTF-16 surrogates, zero em/en-dashes, and caching invariants."""
    # 1. Byte budgets
    llms_txt = get_llms_txt_content()
    assert len(llms_txt.encode("utf-8")) <= MAX_LLMS_TXT_BYTES

    llms_full = get_llms_full_txt_content()
    assert len(llms_full.encode("utf-8")) <= MAX_LLMS_FULL_BYTES

    assets = get_skill_assets()
    assert set(assets.keys()) == ALLOWED_SKILL_SLUGS
    for slug, asset in assets.items():
        assert asset.bytes <= MAX_SKILL_BYTES, f"Skill '{slug}' exceeds {MAX_SKILL_BYTES} bytes"

    # 2. Zero non-ASCII em/en-dashes across all templates
    all_texts = [llms_txt, llms_full] + [a.content for a in assets.values()]
    for text in all_texts:
        assert "\u2014" not in text, "Found forbidden em-dash U+2014"
        assert "\u2013" not in text, "Found forbidden en-dash U+2013"

    # 3. Zero UTF-16 lone surrogates
    for text in all_texts:
        for ch in text:
            code = ord(ch)
            assert not (0xD800 <= code <= 0xDFFF), f"Found UTF-16 surrogate U+{code:04X}"

    # 4. In-memory caching identity check
    assert get_llms_txt_content() is get_llms_txt_content()
    assert get_llms_full_txt_content() is get_llms_full_txt_content()
    assert get_skill_assets() is get_skill_assets()

    # 5. Section headings structure: ## Humans, ## Agents, and ### 1. - 4.
    for doc in (llms_txt, llms_full):
        assert "## Humans" in doc
        assert "## Agents" in doc
        assert "### 1. Platform & 3-Surface MCP Quick-Map" in doc
        assert "### 2. How to Create & Approach Tickets (kanban-ticket Rules)" in doc
        assert "### 3. Mandatory Interactive Onboarding Directive" in doc
        assert "### 4. Recommended Skills Catalog" in doc
        assert "\n## 1. " not in doc
        assert "\n## 2. " not in doc
        assert "\n## 3. " not in doc
        assert "\n## 4. " not in doc
        for line in doc.splitlines():
            for i in (1, 2, 3, 4):
                assert not line.startswith(f"## {i}. "), f"Found demoted H2 heading: {line}"

    # 6. Wheel package inclusion in kanban/pyproject.toml
    pyproject_path = Path("kanban/pyproject.toml")
    with pyproject_path.open("rb") as f:
        data = tomllib.load(f)
    hatch_build = data.get("tool", {}).get("hatch", {}).get("build", {})
    wheel_include = hatch_build.get("targets", {}).get("wheel", {}).get("include", [])
    assert "*.md" in wheel_include or "**/*.md" in wheel_include
    assert "*.txt" in wheel_include or "**/*.txt" in wheel_include


def test_byte_limit_exceeded_guards(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify RuntimeError is raised if byte limits are exceeded."""
    get_llms_txt_content.cache_clear()
    get_llms_full_txt_content.cache_clear()
    get_skill_assets.cache_clear()

    try:
        monkeypatch.setattr("kanban.ops.llms_txt.MAX_LLMS_TXT_BYTES", 10)
        with pytest.raises(RuntimeError, match="exceeds 10 bytes"):
            get_llms_txt_content()
        get_llms_txt_content.cache_clear()
        monkeypatch.setattr("kanban.ops.llms_txt.MAX_LLMS_TXT_BYTES", MAX_LLMS_TXT_BYTES)

        monkeypatch.setattr("kanban.ops.llms_txt.MAX_SKILL_BYTES", 10)
        with pytest.raises(RuntimeError, match="exceeds 10 bytes"):
            get_skill_assets()
        get_skill_assets.cache_clear()
        monkeypatch.setattr("kanban.ops.llms_txt.MAX_SKILL_BYTES", MAX_SKILL_BYTES)

        monkeypatch.setattr("kanban.ops.llms_txt.MAX_LLMS_FULL_BYTES", 10)
        with pytest.raises(RuntimeError, match="exceeds 10 bytes"):
            get_llms_full_txt_content()
        get_llms_full_txt_content.cache_clear()
    finally:
        get_llms_txt_content.cache_clear()
        get_llms_full_txt_content.cache_clear()
        get_skill_assets.cache_clear()
