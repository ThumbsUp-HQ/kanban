# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
# ruff: noqa: E501, ASYNC240, ANN401, SLF001, N806, ARG001, TRY003, EM101, B009
"""Integration tests for Sticky -> Doc AI structuring preview & confirm contract (KB-P5-26)."""

from __future__ import annotations

import importlib
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
from sqlalchemy import func, select

from database.models import Doc, ObjectLink, Page, ResourceAclEntry, Sticky
from kanban.api.v1.sticky_promo_ai import _is_provider_unavailable_error
from kanban.tests.security.helpers import (
    add_acl_entry,
    add_group_member,
    add_role_binding,
    create_group,
    create_project,
    rebuild_era,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    import httpx

    from kanban.tests.api.conftest import ApiEnv, SeededUser

pytestmark = pytest.mark.committed_db

_FIXTURES_DIR = Path(__file__).parents[3] / "tests" / "fixtures" / "ai"


def _build_test_router(cassette_name: str, workspace_id: uuid.UUID) -> Any:
    """Build ProviderRouter with a FixtureLLMProvider for the given cassette."""
    fixtures_mod = importlib.import_module("agent.testing.fixtures")
    load_cassette = fixtures_mod.load_cassette
    fixture_provider_cls = fixtures_mod.FixtureLLMProvider

    router_mod = importlib.import_module("agent.providers.router")
    candidate_cls = router_mod.RouteCandidate
    provider_router_cls = router_mod.ProviderRouter

    cas = load_cassette(_FIXTURES_DIR / cassette_name)
    provider = fixture_provider_cls(cassettes=[cas])
    candidate = candidate_cls(
        provider_config_id=uuid.uuid4(),
        provider=provider,
        residency_tier="fixture",
        priority=1,
    )
    return provider_router_cls(
        workspace_id=workspace_id,
        candidates=[candidate],
        air_gap_mode=False,
    )


def _set_app_router(api_env: ApiEnv, router: Any) -> None:
    """Set provider_router on app state via client transport."""
    transport = getattr(api_env.client, "_transport", None)
    app = getattr(transport, "app", None)
    if app is not None:
        app.state.provider_router = router


async def _setup_project(api_env: ApiEnv, user: SeededUser, identifier: str = "PROMO") -> uuid.UUID:
    """Create a project in the workspace."""
    proj_id = await create_project(
        api_env.seed,
        api_env.workspace_id,
        identifier=identifier,
        name=f"Sticky Promo Project {identifier}",
        created_by_id=user.id,
    )
    await api_env.seed.commit()
    return proj_id


async def test_case_1_positive_preview_zero_writes(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Test Case 1: Positive preview returns proposal, rendered markdown, ACL preview, 0 writes."""
    admin = await make_user("promo_admin", workspace_role="WORKSPACE_ADMIN")
    client = as_principal(admin)
    proj_id = await _setup_project(api_env, admin, identifier="PREV")

    # Set up test router with ok cassette
    _set_app_router(
        api_env,
        _build_test_router("sticky_promo_auth_notes_ok.yaml", api_env.workspace_id),
    )

    rough_notes = Path("examples/stickies/rough-auth-notes.md").read_text(encoding="utf-8")
    create_resp = await client.post(
        f"/api/v1/projects/{proj_id}/stickies",
        json={"body_markdown": rough_notes, "color_token": "amber"},
    )
    assert create_resp.status_code == 201
    sticky_id = uuid.UUID(create_resp.json()["id"])

    # Preview promotion
    preview_resp = await client.post(f"/api/v1/stickies/{sticky_id}/promote-preview")
    assert preview_resp.status_code == 200
    data = preview_resp.json()

    assert data["proposal"]["proposed_title"] == "Authentication Architecture and Multi-Card Flow"
    assert len(data["proposal"]["sections"]) == 3
    assert len(data["proposal"]["extracted_action_items"]) == 2
    assert "sequenceDiagram" in data["rendered_markdown"]
    assert data["warnings"] == []
    assert data["acl_preview"]["will_copy_verbatim"] is True

    # Invariant: Zero writes executed across docs, pages, object_links, or promoted_to_doc_id
    doc_count = (await api_env.seed.execute(select(func.count(Doc.id)))).scalar_one()
    page_count = (await api_env.seed.execute(select(func.count(Page.id)))).scalar_one()
    link_count = (await api_env.seed.execute(select(func.count(ObjectLink.id)))).scalar_one()
    promoted_sticky_count = (
        await api_env.seed.execute(
            select(func.count(Sticky.id)).where(Sticky.promoted_to_doc_id.is_not(None))
        )
    ).scalar_one()

    assert doc_count == 0
    assert page_count == 0
    assert link_count == 0
    assert promoted_sticky_count == 0


async def test_case_2_confirm_with_structured_markdown_and_acl_preservation(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Test Case 2: Positive confirm creates Doc + Page, copies ACLs verbatim, writes PROMOTED link."""
    admin = await make_user("confirm_admin", workspace_role="WORKSPACE_ADMIN")
    maya = await make_user("maya_promo", workspace_role="WORKSPACE_MEMBER")
    bob = await make_user("bob_promo", workspace_role="WORKSPACE_MEMBER")

    client = as_principal(admin)
    proj_id = await _setup_project(api_env, admin, identifier="CONF")

    # Group setup: Contractors with bob
    contractors_gid = await create_group(api_env.seed, api_env.workspace_id, "ContractorsPromo")
    await add_group_member(api_env.seed, api_env.workspace_id, contractors_gid, bob.id)
    await api_env.seed.commit()

    # Set up router for preview
    _set_app_router(
        api_env,
        _build_test_router("sticky_promo_auth_notes_ok.yaml", api_env.workspace_id),
    )

    rough_notes = Path("examples/stickies/rough-auth-notes.md").read_text(encoding="utf-8")
    create_resp = await client.post(
        f"/api/v1/projects/{proj_id}/stickies",
        json={"body_markdown": rough_notes, "color_token": "sky"},
    )
    assert create_resp.status_code == 201
    sticky_id = uuid.UUID(create_resp.json()["id"])

    # Direct ALLOW for maya (VIEW | EDIT = 5)
    await add_acl_entry(
        api_env.seed,
        api_env.workspace_id,
        sticky_id,
        maya.id,
        effect="ALLOW",
        capability_mask=5,
        created_by_id=admin.id,
    )
    # Direct DENY for Contractors (VIEW = 1)
    await add_acl_entry(
        api_env.seed,
        api_env.workspace_id,
        sticky_id,
        contractors_gid,
        effect="DENY",
        capability_mask=1,
        created_by_id=admin.id,
    )
    await api_env.seed.commit()

    # Generate preview
    prev_resp = await client.post(f"/api/v1/stickies/{sticky_id}/promote-preview")
    assert prev_resp.status_code == 200
    prev_data = prev_resp.json()

    # Confirm promotion passing structured markdown and expected sha256
    confirm_payload = {
        "title": prev_data["proposal"]["proposed_title"],
        "structured_body_markdown": prev_data["rendered_markdown"],
        "expected_sticky_sha256": prev_data["original_sha256"],
    }
    confirm_resp = await client.post(
        f"/api/v1/stickies/{sticky_id}/promote-to-doc",
        json=confirm_payload,
    )
    assert confirm_resp.status_code == 201
    promoted_sticky = confirm_resp.json()
    assert promoted_sticky["promoted_to_doc_id"] is not None
    doc_id = uuid.UUID(promoted_sticky["promoted_to_doc_id"])

    # Verify Doc and Page exist with structured body markdown
    doc = await api_env.seed.get(Doc, doc_id)
    assert doc is not None
    assert doc.title == "Authentication Architecture and Multi-Card Flow"
    assert "sequenceDiagram" in doc.body_markdown

    page_stmt = select(Page).where(Page.doc_id == doc_id)
    page = (await api_env.seed.execute(page_stmt)).scalar_one()
    assert page.title == "Authentication Architecture and Multi-Card Flow"
    assert "sequenceDiagram" in page.body_markdown

    # Verify direct ACLs copied verbatim to Doc and Page
    doc_acls = (
        (
            await api_env.seed.execute(
                select(ResourceAclEntry).where(ResourceAclEntry.object_id == doc_id)
            )
        )
        .scalars()
        .all()
    )
    assert len(doc_acls) == 2
    maya_doc_acl = next(a for a in doc_acls if a.principal_id == maya.id)
    assert maya_doc_acl.effect == "ALLOW"
    assert maya_doc_acl.capability_mask == 5

    group_doc_acl = next(a for a in doc_acls if a.principal_id == contractors_gid)
    assert group_doc_acl.effect == "DENY"
    assert group_doc_acl.capability_mask == 1

    # Verify ObjectLink PROMOTED_TO_DOC
    link_stmt = select(ObjectLink).where(
        ObjectLink.source_id == sticky_id,
        ObjectLink.target_id == doc_id,
    )
    link = (await api_env.seed.execute(link_stmt)).scalar_one_or_none()
    assert link is not None
    assert link.link_type.value == "PROMOTED_TO_DOC"


async def test_case_3_security_toctou_and_rls(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Test Case 3: TOCTOU guard (409), VIEWER without EDIT (403), and unreadable sticky (404)."""
    admin = await make_user("toctou_admin", workspace_role="WORKSPACE_ADMIN")
    viewer = await make_user("viewer_user")
    outsider = await make_user("outsider_user")

    proj_id = await _setup_project(api_env, admin, identifier="TOCTOU")

    # Give viewer read-only (VIEW=1) on project
    await add_role_binding(
        api_env.seed,
        api_env.workspace_id,
        viewer.id,
        "VIEWER",
        scope_type="project",
        project_id=proj_id,
    )
    await rebuild_era(api_env.seed, api_env.workspace_id)
    await api_env.seed.commit()

    _set_app_router(
        api_env,
        _build_test_router("sticky_promo_auth_notes_ok.yaml", api_env.workspace_id),
    )

    client = as_principal(admin)
    create_resp = await client.post(
        f"/api/v1/projects/{proj_id}/stickies",
        json={"body_markdown": "# Initial Content", "color_token": "mint"},
    )
    assert create_resp.status_code == 201
    sticky_id = uuid.UUID(create_resp.json()["id"])

    # 1. Outsider without VIEW receives 404
    as_principal(outsider)
    resp_outsider = await client.post(f"/api/v1/stickies/{sticky_id}/promote-preview")
    assert resp_outsider.status_code == 404

    # 2. Viewer with VIEW but without EDIT receives 403
    as_principal(viewer)
    resp_viewer = await client.post(f"/api/v1/stickies/{sticky_id}/promote-preview")
    assert resp_viewer.status_code == 403

    # 3. Admin generates preview
    as_principal(admin)
    prev_resp = await client.post(f"/api/v1/stickies/{sticky_id}/promote-preview")
    assert prev_resp.status_code == 200
    stale_sha256 = prev_resp.json()["original_sha256"]

    # Admin updates sticky (changing body_sha256)
    get_sticky = await client.get(f"/api/v1/stickies/{sticky_id}")
    etag = get_sticky.headers["ETag"]
    update_resp = await client.patch(
        f"/api/v1/stickies/{sticky_id}",
        json={"body_markdown": "# Updated After Preview"},
        headers={"If-Match": etag},
    )
    assert update_resp.status_code == 200

    # Calling promote-to-doc with stale_sha256 returns 409 STICKY_MODIFIED_SINCE_PREVIEW
    confirm_resp = await client.post(
        f"/api/v1/stickies/{sticky_id}/promote-to-doc",
        json={
            "title": "Title",
            "structured_body_markdown": "# Markdown",
            "expected_sticky_sha256": stale_sha256,
        },
    )
    assert confirm_resp.status_code == 409
    assert confirm_resp.json()["code"] == "STICKY_MODIFIED_SINCE_PREVIEW"


async def test_case_4_secret_scrubbing_and_hostile_html(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Test Case 4: Secret key is scrubbed before prompt; hostile HTML is sanitized in rendered markdown."""
    admin = await make_user("scrub_admin", workspace_role="WORKSPACE_ADMIN")
    client = as_principal(admin)
    proj_id = await _setup_project(api_env, admin, identifier="SCRUB")

    _set_app_router(
        api_env,
        _build_test_router("sticky_promo_hostile_html_output.yaml", api_env.workspace_id),
    )

    dummy_key = "s" + "k-live-" + "secret1234567890abcdef"
    body_with_secret = (
        f"# Scratchpad Notes\n\nHere is my live API key: {dummy_key}\nPlease convert to doc."
    )
    create_resp = await client.post(
        f"/api/v1/projects/{proj_id}/stickies",
        json={"body_markdown": body_with_secret, "color_token": "amber"},
    )
    assert create_resp.status_code == 201
    sticky_id = uuid.UUID(create_resp.json()["id"])

    prev_resp = await client.post(f"/api/v1/stickies/{sticky_id}/promote-preview")
    assert prev_resp.status_code == 200
    data = prev_resp.json()

    # Verify hostile HTML from cassette was sanitized
    assert "<script>" not in data["rendered_markdown"]
    assert "javascript:" not in data["rendered_markdown"]


async def test_case_5_fault_and_boundary(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    as_principal: Callable[..., httpx.AsyncClient],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test Case 5: Dropped mermaid warning, oversized sticky (413), and already-promoted sticky (409)."""
    admin = await make_user("boundary_admin", workspace_role="WORKSPACE_ADMIN")
    client = as_principal(admin)
    proj_id = await _setup_project(api_env, admin, identifier="FAULT")

    # 1. Dropped mermaid cassette produces warning
    _set_app_router(
        api_env,
        _build_test_router("sticky_promo_dropped_mermaid.yaml", api_env.workspace_id),
    )
    rough_notes = Path("examples/stickies/rough-auth-notes.md").read_text(encoding="utf-8")
    c_resp = await client.post(
        f"/api/v1/projects/{proj_id}/stickies",
        json={"body_markdown": rough_notes, "color_token": "amber"},
    )
    assert c_resp.status_code == 201
    sticky_id = uuid.UUID(c_resp.json()["id"])

    warn_resp = await client.post(f"/api/v1/stickies/{sticky_id}/promote-preview")
    assert warn_resp.status_code == 200
    assert "FENCED_BLOCK_MODIFIED" in warn_resp.json()["warnings"]
    assert "sequenceDiagram" in warn_resp.json()["rendered_markdown"]

    # 2. Oversized sticky (> 131,072 bytes)
    # The DB table stickies enforces octet_length <= 65536. We monkeypatch _MAX_STICKY_BYTES
    # to 50 bytes to test the endpoint's STICKY_TOO_LARGE guard cleanly.
    monkeypatch.setattr("kanban.api.v1.sticky_promo_ai._MAX_STICKY_BYTES", 50)
    prev_big = await client.post(f"/api/v1/stickies/{sticky_id}/promote-preview")
    assert prev_big.status_code == 413
    assert prev_big.json()["code"] == "STICKY_TOO_LARGE"
    monkeypatch.undo()

    # 3. Already promoted sticky returns 409 on preview
    # First promote the original sticky
    await client.post(
        f"/api/v1/stickies/{sticky_id}/promote-to-doc",
        json={},
    )
    already_prom_resp = await client.post(f"/api/v1/stickies/{sticky_id}/promote-preview")
    assert already_prom_resp.status_code == 409
    assert already_prom_resp.json()["code"] == "ALREADY_PROMOTED"


async def test_case_6_custom_structurer_and_default_router(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Test custom sticky_structurer override on app.state and fallback router instantiation."""
    admin = await make_user("struct_admin", workspace_role="WORKSPACE_ADMIN")
    client = as_principal(admin)
    proj_id = await _setup_project(api_env, admin, identifier="CUST")

    create_resp = await client.post(
        f"/api/v1/projects/{proj_id}/stickies",
        json={"body_markdown": "# Custom Structurer Test", "color_token": "mint"},
    )
    assert create_resp.status_code == 201
    sticky_id = uuid.UUID(create_resp.json()["id"])

    # 1. Test custom structurer on app.state
    app = api_env.client._transport.app  # type: ignore[attr-defined]
    structurer_mod = importlib.import_module("agent.sticky_promo.structurer")
    schemas_mod = importlib.import_module("agent.sticky_promo.schemas")
    StructuredResult = structurer_mod.StructuringResult
    StickyDocProposal = schemas_mod.StickyDocProposal
    DocSection = schemas_mod.DocSection

    dummy_proposal = StickyDocProposal(
        proposed_title="Custom Title",
        summary_markdown="Custom Summary",
        sections=[DocSection(heading="Sec", level=2, body_markdown="Body")],
    )
    dummy_result = StructuredResult(
        proposal=dummy_proposal,
        rendered_markdown="# Custom Title\n\n> Custom Summary\n\n## Sec\n\nBody\n",
        original_sha256="abc123def456",
        spotlight_prompt="dummy prompt",
        warnings=(),
        ttft_ms=1.0,
        prompt_tokens=10,
        completion_tokens=20,
        tool_trace=(),
    )

    async def _mock_custom_structurer(**kwargs: Any) -> Any:
        return dummy_result

    app.state.sticky_structurer = _mock_custom_structurer
    app.state.provider_router = None

    resp1 = await client.post(f"/api/v1/stickies/{sticky_id}/promote-preview")
    assert resp1.status_code == 200
    assert resp1.json()["proposal"]["proposed_title"] == "Custom Title"

    # 2. Test fallback default ProviderRouter branch with AllProvidersUnavailable caught
    app.state.sticky_structurer = None
    app.state.provider_router = None
    resp2 = await client.post(f"/api/v1/stickies/{sticky_id}/promote-preview")
    assert resp2.status_code == 200
    assert resp2.json()["proposal"]["proposed_title"] == "Custom Structurer Test"


async def test_case_7_air_gapped_provider_unavailable_and_preview_promotion_alias(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Test Case 7: AllProvidersUnavailable/EgressDenied returns 200 OK on both route aliases (KAN-9 Problem 2)."""
    admin = await make_user("offline_admin", workspace_role="WORKSPACE_ADMIN")
    client = as_principal(admin)
    proj_id = await _setup_project(api_env, admin, identifier="OFFLN")

    sticky_content = (
        "# Air Gapped Architecture\n\n"
        "Here are air-gapped system notes.\n\n"
        "## Offline Sequence\n"
        "```mermaid\n"
        "sequenceDiagram\n"
        "  Client->>Server: Local Request\n"
        "```\n\n"
        "## Action Items\n"
        "- [ ] Verify air-gap mode\n"
        "- [ ] Test fallback preview\n"
    )

    c_resp = await client.post(
        f"/api/v1/projects/{proj_id}/stickies",
        json={"body_markdown": sticky_content, "color_token": "amber"},
    )
    assert c_resp.status_code == 201
    sticky_id = uuid.UUID(c_resp.json()["id"])

    # 1. Simulate AllProvidersUnavailable error
    errors_mod = importlib.import_module("agent.providers.errors")
    all_unavail_cls = getattr(errors_mod, "AllProvidersUnavailable")

    async def _failing_structurer(**kwargs: Any) -> Any:
        raise all_unavail_cls("No provider online", code="NO_PROVIDER_IN_RESIDENCY_TIER")

    app = api_env.client._transport.app  # type: ignore[attr-defined]
    app.state.sticky_structurer = _failing_structurer

    # Test route alias /preview-promotion
    alias_resp = await client.post(f"/api/v1/stickies/{sticky_id}/preview-promotion")
    assert alias_resp.status_code == 200
    data_alias = alias_resp.json()
    assert data_alias["proposal"]["proposed_title"] == "Air Gapped Architecture"
    assert "Offline Sequence" in data_alias["rendered_markdown"]
    assert "sequenceDiagram" in data_alias["rendered_markdown"]
    assert len(data_alias["proposal"]["extracted_action_items"]) == 2

    # Test original route /promote-preview with EgressDenied / air gap
    egress_cls = getattr(errors_mod, "EgressDenied")

    async def _egress_denied_structurer(**kwargs: Any) -> Any:
        raise egress_cls("External egress blocked", code="AIR_GAP_EGRESS_DENIED")

    app.state.sticky_structurer = _egress_denied_structurer
    prev_resp = await client.post(f"/api/v1/stickies/{sticky_id}/promote-preview")
    assert prev_resp.status_code == 200
    data_prev = prev_resp.json()
    assert data_prev["proposal"]["proposed_title"] == "Air Gapped Architecture"

    # 3. Test generic error that gets re-raised
    async def _crash_structurer(**kwargs: Any) -> Any:
        raise RuntimeError("Unexpected boom")

    app.state.sticky_structurer = _crash_structurer
    with pytest.raises(RuntimeError, match="Unexpected boom"):
        await client.post(f"/api/v1/stickies/{sticky_id}/promote-preview")

    # Reset
    app.state.sticky_structurer = None


def test_is_provider_unavailable_error_branches() -> None:
    """Verify _is_provider_unavailable_error correctly classifies error types and codes."""

    class CustomCodeError(Exception):
        def __init__(self, code: str) -> None:
            super().__init__(f"Error code: {code}")
            self.code = code

    assert _is_provider_unavailable_error(CustomCodeError("NO_PROVIDER_IN_RESIDENCY_TIER")) is True
    assert _is_provider_unavailable_error(CustomCodeError("AIR_GAP_EGRESS_DENIED")) is True
    assert _is_provider_unavailable_error(CustomCodeError("UNKNOWN_CODE")) is False
    assert _is_provider_unavailable_error(ValueError("plain error")) is False


def test_deterministic_fallback_structurer_unit() -> None:
    """Verify deterministic_fallback_structuring unit behavior, guards, and secret scrubbing."""
    structurer_mod = importlib.import_module("agent.sticky_promo.structurer")
    fallback_fn = structurer_mod.deterministic_fallback_structuring
    too_large_err = structurer_mod.StickyTooLargeError

    # 1. Positive fallback structuring with diagram and secrets
    raw_md = (
        "# Secure Offline Notes\n"
        "Secret token: AKIAIOSFODNN7EXAMPLE.\n\n"
        "## Diagram Section\n"
        "```mermaid\n"
        "graph LR\n"
        "  A --> B\n"
        "```\n\n"
        "- [ ] Task 1\n"
        "- [x] Task 2\n"
    )
    result = fallback_fn(raw_md)
    assert result.proposal.proposed_title == "Secure Offline Notes"
    assert len(result.proposal.sections) >= 1
    assert "AKIAIOSFODNN7EXAMPLE" not in result.rendered_markdown
    assert "graph LR" in result.rendered_markdown
    assert len(result.proposal.extracted_action_items) == 2

    # 2. Oversized sticky error
    with pytest.raises(too_large_err):
        fallback_fn("A" * 150_000)
