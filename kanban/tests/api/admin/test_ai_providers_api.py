# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""REST API integration tests for AI provider & budget administration (KB-P5-05b)."""

from __future__ import annotations

import base64
import uuid
from typing import TYPE_CHECKING

import httpx
import pytest
from sqlalchemy import select, text
from sqlalchemy.orm import undefer

from database.models.activity import ActivityRecord
from database.models.ai import AIProviderConfig, AITokenLedger
from database.models.workspace_settings import WorkspaceSettings
from kanban.api.deps import PrincipalContext
from kanban.services.activity import ActivityEventType

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from kanban.tests.api.conftest import ApiEnv, SeededUser
    from kanban.tests.contract import ContractRecorder

pytestmark = pytest.mark.committed_db


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode("ascii").rstrip("=")


@pytest.fixture(autouse=True)
def setup_test_key_material(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set up valid test key material in environment."""
    monkeypatch.delenv("KANBAN_KEYRING_FILE", raising=False)
    monkeypatch.setenv("KANBAN_MASTER_KEK", _b64(b"k" * 32))
    monkeypatch.setenv("KANBAN_AUTH_PEPPER", _b64(b"p" * 32))
    monkeypatch.setenv("KANBAN_SESSION_HMAC_KEY", _b64(b"s" * 32))
    monkeypatch.setenv("KANBAN_MASTER_KEK_KID", "test-kid-1")


async def _enroll_totp_and_set_aal2(
    api_env: ApiEnv,
    user: SeededUser,
) -> None:
    """Enroll and confirm TOTP factor to permit AAL2 evaluation for user."""
    await api_env.seed.execute(
        text("SELECT kb_auth.totp_enroll(:p_id, :blob, :dek, 'test-kid-1')"),
        {
            "p_id": user.id,
            "blob": b"\x01" + b"\x00" * 28,
            "dek": b"\x01" + b"\x00" * 44,
        },
    )
    res = await api_env.seed.execute(
        text("SELECT id FROM kb_auth.totp_get_pending(:p_id)"),
        {"p_id": user.id},
    )
    p_row = res.mappings().first()
    if p_row:
        await api_env.seed.execute(
            text("SELECT kb_auth.totp_confirm(:p_fid, 100)"),
            {"p_fid": p_row["id"]},
        )
    await api_env.seed.commit()
    api_env.resolver.principal = PrincipalContext(
        principal_id=user.id,
        workspace_id=user.workspace_id,
        aal_level=2,
    )


@pytest.mark.asyncio
async def test_case_1_positive_rest_lifecycle_and_budget_usage(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    contract_recorder: ContractRecorder,
) -> None:
    """Test Case 1: Positive REST lifecycle.

    Admin creates ollama config, lists it, sets daily cap 100000, reads tokens_used=48.
    """
    admin_user = await make_user("admin_c1", workspace_role="WORKSPACE_ADMIN")
    await _enroll_totp_and_set_aal2(api_env, admin_user)
    client = api_env.client

    # 1. Create ollama provider configuration
    create_payload = {
        "provider_kind": "ollama",
        "display_name": "Local Ollama Llama3",
        "base_url": "http://127.0.0.1:11434",
        "model_allowlist": ["llama3:8b", "codellama:7b"],
        "residency_tier": "default",
        "priority": 10,
        "settings": {"temperature": 0.2},
        "is_enabled": True,
    }
    resp_create = await client.post("/api/v1/admin/ai/providers", json=create_payload)
    assert resp_create.status_code == 201
    contract_recorder.record("create_ai_provider_201", resp_create.request, resp_create)
    created_data = resp_create.json()
    config_id = created_data["id"]
    assert created_data["provider_kind"] == "ollama"
    assert created_data["display_name"] == "Local Ollama Llama3"
    assert created_data["api_key_set"] is False
    assert created_data["is_enabled"] is True
    assert "Location" in resp_create.headers

    # 2. Get provider by ID
    resp_get = await client.get(f"/api/v1/admin/ai/providers/{config_id}")
    assert resp_get.status_code == 200
    contract_recorder.record("get_ai_provider_200", resp_get.request, resp_get)
    assert resp_get.json()["id"] == config_id

    # 3. List providers
    resp_list = await client.get("/api/v1/admin/ai/providers")
    assert resp_list.status_code == 200
    contract_recorder.record("list_ai_providers_200", resp_list.request, resp_list)
    items = resp_list.json()
    assert any(item["id"] == config_id for item in items)

    # 4. Set daily budget cap 100000
    budget_payload = {
        "provider_config_id": config_id,
        "period_kind": "daily",
        "token_cap": 100000,
    }
    resp_budget = await client.put("/api/v1/admin/ai/budgets", json=budget_payload)
    assert resp_budget.status_code == 200
    contract_recorder.record("set_ai_budget_200", resp_budget.request, resp_budget)
    b_data = resp_budget.json()
    assert b_data["period_kind"] == "daily"
    assert b_data["token_cap"] == 100000
    assert b_data["tokens_used"] == 0
    assert b_data["tokens_reserved"] == 0

    # 5. Seed budget usage: set tokens_used=48
    await api_env.seed.execute(
        text(
            "UPDATE ai_token_ledgers SET tokens_used = 48 "
            "WHERE provider_config_id = :id AND period_kind = 'daily'"
        ),
        {"id": uuid.UUID(config_id)},
    )
    await api_env.seed.commit()

    # 6. Read budget usage: verify tokens_used=48
    resp_read_budget = await client.get(f"/api/v1/admin/ai/budgets?provider_config_id={config_id}")
    assert resp_read_budget.status_code == 200
    contract_recorder.record("get_ai_budgets_200", resp_read_budget.request, resp_read_budget)
    budgets = resp_read_budget.json()
    assert len(budgets) >= 1
    daily_b = next(b for b in budgets if b["period_kind"] == "daily")
    assert daily_b["token_cap"] == 100000
    assert daily_b["tokens_used"] == 48
    assert daily_b["tokens_reserved"] == 0


@pytest.mark.asyncio
async def test_case_3_security_secret_suppression(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    contract_recorder: ContractRecorder,
) -> None:
    """Test Case 3: Response JSON secret suppression.

    Response JSON never contains the submitted API key string nor wrapped_ fields.
    """
    admin_user = await make_user("admin_c3", workspace_role="WORKSPACE_ADMIN")
    await _enroll_totp_and_set_aal2(api_env, admin_user)
    client = api_env.client

    secret_key = "test-super-secret-canary-key-9876543210-xyz"
    create_payload = {
        "provider_kind": "openai",
        "display_name": "OpenAI Production",
        "model_allowlist": ["gpt-4o", "gpt-4o-mini"],
        "api_key": secret_key,
    }
    resp = await client.post("/api/v1/admin/ai/providers", json=create_payload)
    assert resp.status_code == 201
    contract_recorder.record("create_openai_with_secret_201", resp.request, resp)

    raw_json = resp.text
    assert secret_key not in raw_json
    assert "wrapped_" not in raw_json
    assert "wrapped_api_key" not in raw_json
    assert "wrapped_dek" not in raw_json
    assert "api_key_nonce" not in raw_json
    assert "dek_kid" not in raw_json
    assert resp.json()["api_key_set"] is True

    # Check GET /providers
    resp_get = await client.get(f"/api/v1/admin/ai/providers/{resp.json()['id']}")
    assert resp_get.status_code == 200
    assert secret_key not in resp_get.text
    assert "wrapped_" not in resp_get.text

    # Check database row: confirm key is encrypted and not in plaintext
    stmt = (
        select(AIProviderConfig)
        .options(undefer(AIProviderConfig.wrapped_api_key))
        .where(AIProviderConfig.id == uuid.UUID(resp.json()["id"]))
    )
    config_row = (await api_env.seed.execute(stmt)).scalar_one()
    assert config_row.wrapped_api_key is not None
    assert secret_key.encode("utf-8") not in bytes(config_row.wrapped_api_key)


@pytest.mark.asyncio
async def test_case_4_security_member_isolation(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
) -> None:
    """Test Case 4: Member isolation.

    MEMBER principal gets 404 for unreadable config, 403 where readable-not-admin.
    """
    admin_user = await make_user("admin_c4", workspace_role="WORKSPACE_ADMIN")
    member_user = await make_user("member_c4", workspace_role="WORKSPACE_MEMBER")
    project_id = await make_project("PRJA", created_by=admin_user, roles={member_user: "MEMBER"})
    await make_project("PRJB", created_by=admin_user, roles={member_user: "PROJECT_ADMIN"})
    await _enroll_totp_and_set_aal2(api_env, admin_user)
    client = api_env.client

    # 1. Admin creates workspace-level config and project-level config
    ws_resp = await client.post(
        "/api/v1/admin/ai/providers",
        json={
            "provider_kind": "ollama",
            "display_name": "WS Ollama",
            "model_allowlist": ["llama3"],
        },
    )
    assert ws_resp.status_code == 201
    ws_cfg_id = ws_resp.json()["id"]

    prj_resp = await client.post(
        "/api/v1/admin/ai/providers",
        json={
            "provider_kind": "ollama",
            "display_name": "Project Ollama",
            "model_allowlist": ["llama3"],
            "project_id": str(project_id),
        },
    )
    assert prj_resp.status_code == 201

    # 2. Member user (has PROJECT_ADMIN on PRJB, but only MEMBER on PRJA)
    await _enroll_totp_and_set_aal2(api_env, member_user)

    # 2a. Unreadable workspace config: member lacks workspace admin capability -> 404 NOT_FOUND
    # Note: RLS filters out workspace config, load_or_404 yields uniform 404
    resp_unreadable = await client.get(f"/api/v1/admin/ai/providers/{ws_cfg_id}")
    assert resp_unreadable.status_code == 404
    assert resp_unreadable.json()["code"] == "NOT_FOUND"

    # 2b. Readable project config: member has VIEW on project PRJA, but lacks admin -> 403 FORBIDDEN
    resp_readable_not_admin = await client.post(
        "/api/v1/admin/ai/providers",
        json={
            "provider_kind": "ollama",
            "display_name": "Hacked Title",
            "model_allowlist": ["llama3"],
            "project_id": str(project_id),
        },
    )
    assert resp_readable_not_admin.status_code == 403
    assert resp_readable_not_admin.json()["code"] == "FORBIDDEN"

    # 2c. Non-existent or unreadable project -> 404 NOT_FOUND
    resp_unreadable_proj = await client.post(
        "/api/v1/admin/ai/providers",
        json={
            "provider_kind": "ollama",
            "display_name": "Ghost Project",
            "model_allowlist": ["llama3"],
            "project_id": str(uuid.uuid4()),
        },
    )
    assert resp_unreadable_proj.status_code == 404
    assert resp_unreadable_proj.json()["code"] == "NOT_FOUND"


@pytest.mark.asyncio
async def test_case_5_security_csrf_and_airgap(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    contract_recorder: ContractRecorder,
) -> None:
    """Test Case 5: CSRF and air-gap security.

    POST without CSRF token -> 403; gemini create under air_gap_mode -> 409.
    """
    admin_user = await make_user("admin_c5", workspace_role="WORKSPACE_ADMIN")
    await _enroll_totp_and_set_aal2(api_env, admin_user)

    # 1. POST without CSRF header / cookie -> 403
    async with httpx.AsyncClient(
        transport=api_env.client._transport,  # noqa: SLF001
        base_url="http://test",
    ) as no_csrf_client:
        resp_no_csrf = await no_csrf_client.post(
            "/api/v1/admin/ai/providers",
            json={
                "provider_kind": "ollama",
                "display_name": "No CSRF",
                "model_allowlist": ["m1"],
            },
        )
        assert resp_no_csrf.status_code == 403
        assert resp_no_csrf.json()["code"] == "CSRF_REJECTED"

    # 2. Toggle air_gap_mode in WorkspaceSettings
    stmt = (
        select(WorkspaceSettings)
        .where(WorkspaceSettings.workspace_id == admin_user.workspace_id)
        .with_for_update()
    )
    res = await api_env.seed.execute(stmt)
    settings = res.scalar_one_or_none()
    if settings is None:
        settings = WorkspaceSettings(
            workspace_id=admin_user.workspace_id,
            display_name="Engineering",
            default_project_visibility="private",
            session_idle_timeout_min=60,
            session_absolute_timeout_min=720,
            trash_retention_days=30,
            mcp_key_max_ttl_days=90,
            air_gap_mode=True,
        )
        api_env.seed.add(settings)
    else:
        settings.air_gap_mode = True
    await api_env.seed.commit()

    # 3. Creating cloud provider 'gemini' under active air_gap_mode -> 409 AIR_GAP_EGRESS_DENIED
    client = api_env.client
    resp_air_gap = await client.post(
        "/api/v1/admin/ai/providers",
        json={
            "provider_kind": "gemini",
            "display_name": "Cloud Gemini",
            "model_allowlist": ["gemini-1.5-flash"],
        },
    )
    assert resp_air_gap.status_code == 409
    contract_recorder.record("create_gemini_air_gap_denied_409", resp_air_gap.request, resp_air_gap)
    assert resp_air_gap.json()["code"] == "AIR_GAP_EGRESS_DENIED"


@pytest.mark.asyncio
async def test_case_6_negative_base_url_ssrf_and_invalid_token_cap(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    contract_recorder: ContractRecorder,
) -> None:
    """Test Case 6: Negative base_url SSRF and token_cap validation.

    base_url http://169.254.169.254 -> 422 INVALID_BASE_URL; token_cap negative -> 422.
    """
    admin_user = await make_user("admin_c6", workspace_role="WORKSPACE_ADMIN")
    await _enroll_totp_and_set_aal2(api_env, admin_user)
    client = api_env.client

    # 1. SSRF link-local / cloud metadata IP -> 422 INVALID_BASE_URL
    resp_ssrf = await client.post(
        "/api/v1/admin/ai/providers",
        json={
            "provider_kind": "ollama",
            "display_name": "IMDS Ollama",
            "base_url": "http://169.254.169.254",
            "model_allowlist": ["llama3"],
        },
    )
    assert resp_ssrf.status_code == 422
    contract_recorder.record("create_provider_ssrf_422", resp_ssrf.request, resp_ssrf)
    assert resp_ssrf.json()["code"] == "INVALID_BASE_URL"

    # 2. Create valid provider for budget test
    resp_ok = await client.post(
        "/api/v1/admin/ai/providers",
        json={
            "provider_kind": "ollama",
            "display_name": "Valid Ollama",
            "model_allowlist": ["llama3"],
        },
    )
    assert resp_ok.status_code == 201
    cfg_id = resp_ok.json()["id"]

    # 3. Negative token_cap -> 422
    resp_neg_cap = await client.put(
        "/api/v1/admin/ai/budgets",
        json={
            "provider_config_id": cfg_id,
            "period_kind": "daily",
            "token_cap": -1,
        },
    )
    assert resp_neg_cap.status_code == 422


@pytest.mark.asyncio
async def test_case_7_boundary_key_length_and_patch_clear(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    contract_recorder: ContractRecorder,
) -> None:
    """Test Case 7: Boundary key length and patch clear.

    Key len 512 accepted, 513 rejected; PATCH omitted keeps key; api_key: null clears.
    """
    admin_user = await make_user("admin_c7", workspace_role="WORKSPACE_ADMIN")
    await _enroll_totp_and_set_aal2(api_env, admin_user)
    client = api_env.client

    # 1. 512-character key accepted
    key_512 = "k" * 512
    resp_512 = await client.post(
        "/api/v1/admin/ai/providers",
        json={
            "provider_kind": "openai",
            "display_name": "OpenAI 512",
            "model_allowlist": ["gpt-4o"],
            "api_key": key_512,
        },
    )
    assert resp_512.status_code == 201
    contract_recorder.record("create_key_512_201", resp_512.request, resp_512)
    cfg_id = resp_512.json()["id"]
    assert resp_512.json()["api_key_set"] is True

    # 2. 513-character key rejected with 422
    key_513 = "k" * 513
    resp_513 = await client.post(
        "/api/v1/admin/ai/providers",
        json={
            "provider_kind": "openai",
            "display_name": "OpenAI 513",
            "model_allowlist": ["gpt-4o"],
            "api_key": key_513,
        },
    )
    assert resp_513.status_code == 422

    # 3. PATCH with omitted api_key keeps existing key intact (api_key_set: True)
    resp_patch_omit = await client.patch(
        f"/api/v1/admin/ai/providers/{cfg_id}",
        json={"display_name": "OpenAI Renamed"},
    )
    assert resp_patch_omit.status_code == 200
    contract_recorder.record(
        "patch_provider_keep_key_200", resp_patch_omit.request, resp_patch_omit
    )
    assert resp_patch_omit.json()["display_name"] == "OpenAI Renamed"
    assert resp_patch_omit.json()["api_key_set"] is True

    # 4. PATCH with api_key: null clears key (api_key_set: False)
    resp_patch_clear = await client.patch(
        f"/api/v1/admin/ai/providers/{cfg_id}",
        json={"api_key": None},
    )
    assert resp_patch_clear.status_code == 200
    contract_recorder.record(
        "patch_provider_clear_key_200", resp_patch_clear.request, resp_patch_clear
    )
    assert resp_patch_clear.json()["api_key_set"] is False


@pytest.mark.asyncio
async def test_case_9_audit_activity_records(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
) -> None:
    """Test Case 9: Each mutation produces exactly one activity_records row with no key material."""
    admin_user = await make_user("admin_c9", workspace_role="WORKSPACE_ADMIN")
    await _enroll_totp_and_set_aal2(api_env, admin_user)
    client = api_env.client

    secret_key = "test-audit-canary-secret-12345"

    # 1. Create
    resp_create = await client.post(
        "/api/v1/admin/ai/providers",
        json={
            "provider_kind": "openai",
            "display_name": "Audit OpenAI",
            "model_allowlist": ["gpt-4o"],
            "api_key": secret_key,
        },
    )
    assert resp_create.status_code == 201
    cfg_id = resp_create.json()["id"]

    # Verify AI_PROVIDER_CONFIG_CREATED
    stmt = (
        select(ActivityRecord)
        .where(
            ActivityRecord.workspace_id == admin_user.workspace_id,
            ActivityRecord.event_type == ActivityEventType.AI_PROVIDER_CONFIG_CREATED,
        )
        .order_by(ActivityRecord.recorded_at.desc())
    )
    act_create = (await api_env.seed.execute(stmt)).scalar_one()
    assert act_create.payload["config_id"] == cfg_id
    assert secret_key not in str(act_create.payload)

    # 2. Update
    resp_update = await client.patch(
        f"/api/v1/admin/ai/providers/{cfg_id}",
        json={"display_name": "Audit OpenAI Updated"},
    )
    assert resp_update.status_code == 200

    stmt_up = (
        select(ActivityRecord)
        .where(
            ActivityRecord.workspace_id == admin_user.workspace_id,
            ActivityRecord.event_type == ActivityEventType.AI_PROVIDER_CONFIG_UPDATED,
        )
        .order_by(ActivityRecord.recorded_at.desc())
    )
    act_update = (await api_env.seed.execute(stmt_up)).scalar_one()
    assert act_update.payload["config_id"] == cfg_id
    assert secret_key not in str(act_update.payload)

    # 3. Disable
    resp_disable = await client.post(f"/api/v1/admin/ai/providers/{cfg_id}:disable")
    assert resp_disable.status_code == 200
    assert resp_disable.json()["is_enabled"] is False

    stmt_dis = (
        select(ActivityRecord)
        .where(
            ActivityRecord.workspace_id == admin_user.workspace_id,
            ActivityRecord.event_type == ActivityEventType.AI_PROVIDER_CONFIG_DISABLED,
        )
        .order_by(ActivityRecord.recorded_at.desc())
    )
    act_disable = (await api_env.seed.execute(stmt_dis)).scalar_one()
    assert act_disable.payload["config_id"] == cfg_id

    # 4. Set Budget
    resp_b = await client.put(
        "/api/v1/admin/ai/budgets",
        json={
            "provider_config_id": cfg_id,
            "period_kind": "monthly",
            "token_cap": 500000,
        },
    )
    assert resp_b.status_code == 200

    stmt_b = (
        select(ActivityRecord)
        .where(
            ActivityRecord.workspace_id == admin_user.workspace_id,
            ActivityRecord.event_type == ActivityEventType.AI_BUDGET_SET,
        )
        .order_by(ActivityRecord.recorded_at.desc())
    )
    act_budget = (await api_env.seed.execute(stmt_b)).scalar_one()
    assert act_budget.payload["provider_config_id"] == cfg_id
    assert act_budget.payload["token_cap"] == 500000


@pytest.mark.asyncio
async def test_additional_coverage_branches(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exercise remaining edge cases and branches for >=95% coverage."""
    admin_user = await make_user("admin_cov", workspace_role="WORKSPACE_ADMIN")
    proj_admin = await make_user("proj_admin_cov", workspace_role="WORKSPACE_MEMBER")
    proj_id = await make_project(
        "COVPRJ", created_by=admin_user, roles={proj_admin: "PROJECT_ADMIN"}
    )
    await _enroll_totp_and_set_aal2(api_env, admin_user)
    client = api_env.client

    # 1. Non-existent ID tests (404)
    fake_id = str(uuid.uuid4())
    assert (await client.get(f"/api/v1/admin/ai/providers/{fake_id}")).status_code == 404
    assert (
        await client.patch(f"/api/v1/admin/ai/providers/{fake_id}", json={"display_name": "X"})
    ).status_code == 404
    assert (await client.post(f"/api/v1/admin/ai/providers/{fake_id}:disable")).status_code == 404
    assert (
        await client.get(f"/api/v1/admin/ai/budgets?provider_config_id={fake_id}")
    ).status_code == 404
    assert (
        await client.put(
            "/api/v1/admin/ai/budgets",
            json={"provider_config_id": fake_id, "period_kind": "daily", "token_cap": 1000},
        )
    ).status_code == 404

    # 2. Create a test config
    resp = await client.post(
        "/api/v1/admin/ai/providers",
        json={
            "provider_kind": "ollama",
            "display_name": "Cov Ollama",
            "model_allowlist": ["llama3"],
        },
    )
    assert resp.status_code == 201
    cfg_id = resp.json()["id"]

    cloud_resp = await client.post(
        "/api/v1/admin/ai/providers",
        json={
            "provider_kind": "openai",
            "display_name": "Cloud Before Airgap",
            "model_allowlist": ["gpt-4o"],
        },
    )
    assert cloud_resp.status_code == 201
    cloud_id = cloud_resp.json()["id"]

    # 3. PATCH with new api_key
    resp_patch_key = await client.patch(
        f"/api/v1/admin/ai/providers/{cfg_id}",
        json={"api_key": "test-cov-new-key-1234"},
    )
    assert resp_patch_key.status_code == 200
    assert resp_patch_key.json()["api_key_set"] is True

    # 4. PATCH with >512 key -> 422
    resp_patch_long = await client.patch(
        f"/api/v1/admin/ai/providers/{cfg_id}",
        json={"api_key": "k" * 513},
    )
    assert resp_patch_long.status_code == 422

    # 5. PATCH with invalid base_url -> 422
    resp_patch_bad_url = await client.patch(
        f"/api/v1/admin/ai/providers/{cfg_id}",
        json={"base_url": "http://169.254.169.254"},
    )
    assert resp_patch_bad_url.status_code == 422

    # 5b. PUT /budgets with token_cap < tokens_used -> 422
    resp_init_b = await client.put(
        "/api/v1/admin/ai/budgets",
        json={
            "provider_config_id": cfg_id,
            "period_kind": "daily",
            "token_cap": 1000,
            "project_id": str(proj_id),
        },
    )
    assert resp_init_b.status_code == 200

    # Seed token usage on the budget
    ledger_stmt = select(AITokenLedger).where(
        AITokenLedger.provider_config_id == uuid.UUID(cfg_id),
        AITokenLedger.project_id == proj_id,
    )
    led = (await api_env.seed.execute(ledger_stmt)).scalar_one()
    led.tokens_used = 800
    await api_env.seed.commit()

    resp_bad_budget = await client.put(
        "/api/v1/admin/ai/budgets",
        json={
            "provider_config_id": cfg_id,
            "period_kind": "daily",
            "token_cap": 500,
            "project_id": str(proj_id),
        },
    )
    assert resp_bad_budget.status_code == 422
    assert resp_bad_budget.json()["code"] == "INVALID_REQUEST"

    # 6. Air gap via environment variable
    monkeypatch.setenv("KANBAN_AIR_GAP_MODE", "true")
    resp_egress = await client.post(
        "/api/v1/admin/ai/providers",
        json={
            "provider_kind": "openai",
            "display_name": "Blocked Cloud",
            "model_allowlist": ["gpt-4o"],
        },
    )
    assert resp_egress.status_code == 409
    assert resp_egress.json()["code"] == "AIR_GAP_EGRESS_DENIED"

    # 6b. PATCH air gap check on existing cloud provider -> 409
    resp_patch_egress = await client.patch(
        f"/api/v1/admin/ai/providers/{cloud_id}",
        json={"display_name": "Cloud Blocked Update"},
    )
    assert resp_patch_egress.status_code == 409
    assert resp_patch_egress.json()["code"] == "AIR_GAP_EGRESS_DENIED"

    # 7. Project admin attempting workspace list_providers -> 403
    await _enroll_totp_and_set_aal2(api_env, proj_admin)
    resp_ws_list = await client.get("/api/v1/admin/ai/providers")
    assert resp_ws_list.status_code == 403
