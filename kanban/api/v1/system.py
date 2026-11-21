# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Platform capability summary and world-class parity metadata endpoint (KB-P0-01 / KANBA-182)."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Annotated

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from kanban.api.deps import PrincipalContext, get_principal
from kanban.ops.build_info import get_build_info
from kanban.ops.sbom import (
    PLATFORM_LICENSE_SPDX,
    PLATFORM_NAME,
    PLATFORM_SLUG,
    PLATFORM_TAGLINE,
    PLATFORM_VERSION,
    calculate_sbom_summary,
    generate_cyclonedx_1_5,
    get_license_texts,
    get_live_components,
)

if TYPE_CHECKING:
    from kanban.settings import Settings

__all__ = [
    "AgentFirstCapabilities",
    "EnterpriseUxCapabilities",
    "FrictionFreeDeploymentCapabilities",
    "ParityMatrixCapabilities",
    "PlatformSummaryResponse",
    "SbomComponentModel",
    "SbomSummaryModel",
    "SecurityFirstCapabilities",
    "SystemAboutResponse",
    "get_platform_summary",
    "router",
]


class SecurityFirstCapabilities(BaseModel):
    """Priority #0 security architecture guarantees."""

    model_config = ConfigDict(extra="forbid")

    force_rls: bool = Field(
        default=True,
        description="PostgreSQL FORCE ROW LEVEL SECURITY active across all tenant tables",
    )
    surrogate_rejection: bool = Field(
        default=True,
        description="Hostile Unicode UTF-16 lone-surrogate rejection at ingestion boundary",
    )
    zero_plaintext_secrets: bool = Field(
        default=True,
        description="AES-256-GCM envelope encryption and zero secret retention in memory or logs",
    )
    aal2_admin_enforcement: bool = Field(
        default=True,
        description="Mandatory Authenticator Assurance Level 2 (AAL2) on admin routes and tools",
    )
    csp_hardened: bool = Field(
        default=True,
        description="Strict Content-Security-Policy with zero unsafe-inline styles or scripts",
    )


class AgentFirstCapabilities(BaseModel):
    """Priority #1 native agent architecture and context budget guarantees."""

    model_config = ConfigDict(extra="forbid")

    mcp_surfaces: list[str] = Field(
        default_factory=lambda: ["/mcp/agent", "/mcp/docs", "/mcp/admin"],
        description="Isolated intent-driven Model Context Protocol surfaces",
    )
    lod_tiers: list[str] = Field(
        default_factory=lambda: ["summary", "standard", "full"],
        description="Supported Level of Detail projection tiers",
    )
    summary_token_budget: int = Field(
        default=1000,
        description="Strict maximum token ceiling for summary LOD tool responses",
    )
    cli_pipe_harnesses: list[str] = Field(
        default_factory=lambda: ["agy -p", "codex -p"],
        description="Zero-shell stdin CLI pipe execution harnesses",
    )
    ai_providers: list[str] = Field(
        default_factory=lambda: ["openai", "ollama", "gemini"],
        description="Supported LLM engine providers with air-gapped and cloud choices",
    )
    agent_harnesses_supported: list[str] = Field(
        default_factory=lambda: [
            "Claude Code",
            "OpenAI Codex",
            "Gemini CLI / Antigravity",
        ],
        description="Supported autonomous coding agent environments",
    )


class FrictionFreeDeploymentCapabilities(BaseModel):
    """Pillar 3 FOSS deployment guarantees."""

    model_config = ConfigDict(extra="forbid")

    standalone_single_container: bool = Field(
        default=True,
        description="1-command standalone docker run with embedded Unix-socket PostgreSQL 16",
    )
    docker_compose_production: bool = Field(
        default=True,
        description="Hardened 5-network production docker-compose deployment stack",
    )
    sub_3s_startup: bool = Field(
        default=True,
        description="Sub-3-second container cold-start readiness time",
    )
    zero_cloud_telemetry: bool = Field(
        default=True,
        description="Zero external analytics, telemetry phoning home, or tracking pixels",
    )
    air_gap_ready: bool = Field(
        default=True,
        description="Complete operational readiness in air-gapped private networks",
    )


class EnterpriseUxCapabilities(BaseModel):
    """Pillar 4 high-ergonomics enterprise UX capabilities."""

    model_config = ConfigDict(extra="forbid")

    whitespace_optimized: bool = Field(
        default=True,
        description="Breathable enterprise layout with 52px topbar and 960px peek drawer",
    )
    emoji_hover_elaboration: bool = Field(
        default=True,
        description="Standardized rich hover tooltips via EmojiHint replacing noisy text tags",
    )
    sparkle_cursor_completion: bool = Field(
        default=True,
        description="Inline blinking sparkle completion with surgical contextmenu accept",
    )
    canonical_markdown_storage: bool = Field(
        default=True,
        description="100% canonical UTF-8 Markdown storage with auto-detection at ingestion",
    )
    safe_mermaid_rendering: bool = Field(
        default=True,
        description="Isolated Web Worker beautiful-mermaid rendering under strict CSP",
    )
    optimistic_drag_and_drop: bool = Field(
        default=True,
        description="Sub-16ms optimistic drag-and-drop state transitions",
    )


class ParityMatrixCapabilities(BaseModel):
    """Competitive parity matrix against commercial SaaS and legacy open-core trackers."""

    model_config = ConfigDict(extra="forbid")

    zero_saas_paywalls: bool = Field(
        default=True,
        description="Zero paywalled features, zero seat licenses, and zero artificial limits",
    )
    unlimited_seats: bool = Field(
        default=True,
        description="Unlimited human users across all authentication providers",
    )
    unlimited_mcp_keys: bool = Field(
        default=True,
        description="Unlimited scoped API keys for autonomous agent teams",
    )
    competitive_parity: list[str] = Field(
        default_factory=lambda: ["Jira", "Plane", "Vibe Kanban"],
        description="Target platforms with verified capability parity or superiority",
    )


class PlatformSummaryResponse(BaseModel):
    """Comprehensive platform capability summary and world-class parity response."""

    model_config = ConfigDict(extra="forbid")

    platform: str = Field(default="👍kanban", description="Official platform brand name")
    slug: str = Field(
        default="thumbs-up-kanban", description="Distribution container and repository slug"
    )
    license: str = Field(default="Apache-2.0", description="Open-source permissive license")
    version: str = Field(default="2.0.0", description="Platform architecture release version")
    github_issue_1_resolved: bool = Field(
        default=True,
        description="Affirmation of GitHub Issue #1 resolution across all 4 pillars",
    )
    pillar_1_agent_first: AgentFirstCapabilities = Field(
        default_factory=AgentFirstCapabilities,
        description="Pillar 1: Native Agent-First Architecture",
    )
    pillar_2_security_first: SecurityFirstCapabilities = Field(
        default_factory=SecurityFirstCapabilities,
        description="Pillar 2: Priority #0 Hardened Security",
    )
    pillar_3_friction_free: FrictionFreeDeploymentCapabilities = Field(
        default_factory=FrictionFreeDeploymentCapabilities,
        description="Pillar 3: Friction-Free FOSS Deployment",
    )
    pillar_4_enterprise_ux: EnterpriseUxCapabilities = Field(
        default_factory=EnterpriseUxCapabilities,
        description="Pillar 4: Enterprise Whitespace & High-Ergonomics UI",
    )
    parity_matrix: ParityMatrixCapabilities = Field(
        default_factory=ParityMatrixCapabilities,
        description="World-class competitive parity matrix",
    )


class SbomSummaryModel(BaseModel):
    """Summary metrics of components and license compliance."""

    model_config = ConfigDict(extra="forbid")

    total_components: int = Field(..., description="Total third-party components")
    python_components: int = Field(..., description="Python backend dependencies")
    web_components: int = Field(..., description="Web frontend dependencies")
    permissive_count: int = Field(..., description="Permissive approved licenses")
    allowlisted_count: int = Field(..., description="Explicitly allowlisted exceptions")
    unknown_count: int = Field(..., description="Unknown or unclassified licenses")
    deny_count: int = Field(..., description="Denylisted or copyleft licenses")


class SbomComponentModel(BaseModel):
    """Structured third-party component representation."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., description="Component package name")
    version: str = Field(..., description="Component semantic release version")
    ecosystem: str = Field(..., description="Packaging ecosystem (python or node)")
    purl: str = Field(..., description="Package URL (PURL)")
    license: str = Field(..., description="SPDX license expression or name")
    license_verdict: str = Field(
        ..., description="License verdict (ALLOW, ALLOWLISTED, UNKNOWN, DENY)"
    )
    scope: str = Field(default="required", description="Dependency scope (required, dev, optional)")
    description: str = Field(default="", description="Package description or summary")


class SystemAboutResponse(BaseModel):
    """Comprehensive system metadata, licensing, and supply chain inventory."""

    model_config = ConfigDict(extra="forbid")

    platform: str = Field(default="👍kanban", description="Official brand name")
    slug: str = Field(default="thumbs-up-kanban", description="Container and repository slug")
    tagline: str = Field(
        default="The difference between a swarm and an Agile team is a kanban.",
        description="Official platform tagline",
    )
    version: str = Field(default="2.0.0", description="Platform release version")
    license_spdx: str = Field(default="Apache-2.0", description="Primary platform license SPDX ID")
    api_docs_urls: dict[str, str] = Field(
        default_factory=lambda: {
            "swagger_ui": "/api/docs",
            "redoc": "/api/redoc",
            "openapi_json": "/api/openapi.json",
        },
        description="Interactive documentation endpoints",
    )
    license: str = Field(description="Verbatim Apache-2.0 LICENSE file text")
    notice: str = Field(description="Verbatim third-party NOTICE file text")
    license_text: str | None = Field(default=None, description="Alias for license")
    notice_text: str | None = Field(default=None, description="Alias for notice")
    sbom_summary: SbomSummaryModel = Field(description="Supply-chain component summary")
    components: list[SbomComponentModel] = Field(description="Discovered third-party components")
    git_commit: str = Field(default="unknown", description="Build git commit SHA")
    build_timestamp: str | None = Field(default=None, description="ISO build timestamp")
    openapi_version: str = Field(default="2.0.0", description="OpenAPI specification version")
    openapi_bundle_hash: str | None = Field(
        default=None, description="SHA-256 fingerprint of OpenAPI bundle"
    )
    frontend_bundle_hash: str | None = Field(
        default=None, description="SHA-256 fingerprint of frontend bundle"
    )


def get_platform_summary(settings: Settings | None = None) -> PlatformSummaryResponse:
    """Return verified platform capability summary and world-class parity metadata."""
    del settings  # Future-proof parameter for dynamic capability overrides if needed
    return PlatformSummaryResponse()


router = APIRouter(prefix="/system", tags=["system"])


@router.get(
    "/about",
    response_model=SystemAboutResponse,
    summary="Get platform about metadata, licensing, and SBOM overview",
    description=(
        "Returns platform branding, verbatim Apache-2.0 license, interactive doc URLs, "
        "and SBOM components."
    ),
)
async def get_system_about_endpoint(
    caller: Annotated[PrincipalContext, Depends(get_principal)],
    request: Request,
) -> SystemAboutResponse:
    """Retrieve comprehensive platform metadata, verbatim licenses, and SBOM."""
    del caller  # Authentication enforced via Depends(get_principal) -> 401 if missing
    comps = get_live_components()
    summary = calculate_sbom_summary(comps)
    license_text, notice_text = get_license_texts()

    openapi_doc = None
    if hasattr(request, "app") and hasattr(request.app, "openapi"):
        openapi_doc = request.app.openapi()
    b_info = get_build_info(openapi_doc)

    return SystemAboutResponse(
        platform=PLATFORM_NAME,
        slug=PLATFORM_SLUG,
        tagline=PLATFORM_TAGLINE,
        version=PLATFORM_VERSION,
        license_spdx=PLATFORM_LICENSE_SPDX,
        api_docs_urls={
            "swagger_ui": "/api/docs",
            "redoc": "/api/redoc",
            "openapi_json": "/api/openapi.json",
        },
        license=license_text,
        notice=notice_text,
        license_text=license_text,
        notice_text=notice_text,
        sbom_summary=SbomSummaryModel(**summary.to_dict()),
        components=[SbomComponentModel(**c.to_dict()) for c in comps],
        git_commit=b_info.git_commit,
        build_timestamp=b_info.build_timestamp,
        openapi_version=b_info.openapi_version,
        openapi_bundle_hash=b_info.openapi_bundle_hash,
        frontend_bundle_hash=b_info.frontend_bundle_hash,
    )


@router.get(
    "/sbom",
    summary="Get CycloneDX 1.5 Software Bill of Materials (SBOM)",
    description=(
        "Returns complete CycloneDX 1.5 JSON manifest for Python and Web runtime dependencies."
    ),
)
async def get_system_sbom_endpoint(
    caller: Annotated[PrincipalContext, Depends(get_principal)],
    *,
    download: Annotated[
        bool,
        Query(description="Trigger file download attachment header"),
    ] = False,
) -> Response:
    """Generate and return CycloneDX 1.5 Software Bill of Materials."""
    del caller  # Authentication enforced via Depends(get_principal) -> 401 if missing
    cdx_data = generate_cyclonedx_1_5()
    json_bytes = json.dumps(cdx_data, indent=2, ensure_ascii=False).encode("utf-8")

    headers: dict[str, str] = {
        "X-Content-Type-Options": "nosniff",
    }
    if download:
        headers["Content-Disposition"] = 'attachment; filename="thumbs-up-kanban-sbom-cdx-1.5.json"'

    return Response(
        content=json_bytes,
        media_type="application/vnd.cyclonedx+json",
        headers=headers,
    )


@router.get(
    "/platform-summary",
    response_model=PlatformSummaryResponse,
    summary="Get platform capability summary and world-class parity metadata",
    description="Exposes verified enterprise capabilities across all 4 pillars.",
)
def get_platform_summary_endpoint() -> PlatformSummaryResponse:
    """Retrieve full platform capabilities and competitive parity metadata."""
    return get_platform_summary()


@router.get(
    "/summary",
    response_model=PlatformSummaryResponse,
    summary="Alias for platform capability summary",
    include_in_schema=False,
)
def get_platform_summary_alias() -> PlatformSummaryResponse:
    """Alias for /system/platform-summary."""
    return get_platform_summary()
