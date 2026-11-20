# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Security tests for custom field manifests, AST bounds, and test-execute (KB-P3-AUDIT-11)."""

from __future__ import annotations

import base64
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from kanban.api.deps import PrincipalContext
from kanban.api.middleware.script_depth import ScriptDepthGuardMiddleware
from kanban.custom_fields.executor import _eval_safe_formula
from kanban.custom_fields.manifest import compute_field_manifest_sha256

if TYPE_CHECKING:
    import uuid
    from collections.abc import Awaitable, Callable

    import httpx
    from starlette.requests import Request

    from kanban.tests.api.conftest import ApiEnv, SeededUser

pytestmark = pytest.mark.committed_db

WASM_DIR = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "wasm"


def _read_fixture(filename: str) -> bytes:
    p = WASM_DIR / filename
    return p.read_bytes()


def _as_admin_aal2(api_env: ApiEnv, user: SeededUser) -> httpx.AsyncClient:
    api_env.resolver.principal = PrincipalContext(
        principal_id=user.id,
        workspace_id=user.workspace_id,
        token_scopes=("session",),
        aal_level=2,
    )
    return api_env.client


def _as_user_aal1(api_env: ApiEnv, user: SeededUser) -> httpx.AsyncClient:
    api_env.resolver.principal = PrincipalContext(
        principal_id=user.id,
        workspace_id=user.workspace_id,
        token_scopes=("session",),
        aal_level=1,
    )
    return api_env.client


def test_manifest_sha256_binds_wasm_module_sha256() -> None:
    """Verify that wasm_module_sha256 is bound into manifest_sha256."""
    base_kwargs: dict[str, Any] = {
        "script_source": "scalar: 42",
        "output_format": "number",
        "output_format_metadata": {},
        "tier": "wasm",
        "target_scope": "PROJECT",
        "credential_mode": "INVOKING_USER",
    }

    hash_none = compute_field_manifest_sha256(**base_kwargs, wasm_module_sha256=None)
    hash_mod1 = compute_field_manifest_sha256(**base_kwargs, wasm_module_sha256=b"\x01" * 32)
    hash_mod2 = compute_field_manifest_sha256(**base_kwargs, wasm_module_sha256=b"\x02" * 32)
    hash_hex1 = compute_field_manifest_sha256(**base_kwargs, wasm_module_sha256=("01" * 32).upper())

    assert hash_none != hash_mod1
    assert hash_mod1 != hash_mod2
    assert hash_mod1 == hash_hex1


def test_eval_safe_formula_ast_node_and_depth_limits() -> None:
    """Verify AST node count (<= 64) and depth (<= 8) DoS ceilings."""
    ctx = {"issue": {"summary": "Safe Formula Test"}}

    # 1. Safe small formula passes
    assert _eval_safe_formula("1 + 2 * 3", ctx) == 7

    # 2. Formula exceeding max AST depth (> 8) returns None
    deep_expr = "1 + (1 + (1 + (1 + (1 + (1 + (1 + (1 + 1)))))))"
    assert _eval_safe_formula(deep_expr, ctx) is None

    # 3. Formula exceeding max AST node count (> 64) returns None
    many_nodes_expr = " + ".join(["1"] * 65)
    assert _eval_safe_formula(many_nodes_expr, ctx) is None


def test_eval_safe_formula_pow_and_mult_dos_bounds() -> None:
    """Verify bounds on ast.Pow and ast.Mult preventing event loop DoS."""
    ctx = {"issue": {"key": "KAN-1"}}

    # ast.Pow bounds: exponent <= 64, abs(base) <= 1_000_000
    assert _eval_safe_formula("2 ** 10", ctx) == 1024
    assert _eval_safe_formula("2 ** 64", ctx) == 2**64
    assert _eval_safe_formula("2 ** 65", ctx) is None
    assert _eval_safe_formula("1000001 ** 2", ctx) is None
    assert _eval_safe_formula("0 ** -1", ctx) is None
    assert _eval_safe_formula("0.0 ** -2", ctx) is None

    # ast.Mult bounds: sequence repetition <= 4096 chars/items
    assert len(_eval_safe_formula("'A' * 4096", ctx)) == 4096
    assert _eval_safe_formula("'A' * 4097", ctx) is None
    assert _eval_safe_formula("['item'] * 4097", ctx) is None
    assert len(_eval_safe_formula("['item'] * 10", ctx)) == 10
    # Regular math multiplication is unaffected
    assert _eval_safe_formula("5 * 20", ctx) == 100


def test_eval_safe_formula_attribute_restricts_to_dict_only() -> None:
    """Verify ast.Attribute restricts strictly to dict key lookups without getattr."""
    ctx = {
        "issue": {
            "summary": "Valid Summary",
            "number_val": 42,
        }
    }

    # Dict lookup works
    assert _eval_safe_formula("issue.summary", ctx) == "Valid Summary"

    # Accessing attributes on non-dict types does NOT invoke getattr
    assert _eval_safe_formula("(123).real", ctx) == ""
    assert _eval_safe_formula("'string'.capitalize", ctx) == ""
    assert _eval_safe_formula("issue.__class__.__name__", ctx) is None


def test_script_depth_middleware_blocks_test_execute_and_dry_run() -> None:
    """Verify ScriptDepthGuardMiddleware blocks test-execute and dry-run at depth >= 1."""

    async def dummy_endpoint(request: Request) -> JSONResponse:
        del request
        return JSONResponse({"ok": True})

    routes = [
        Route(
            "/api/v1/projects/{prj}/custom-fields/test-execute",
            dummy_endpoint,
            methods=["POST"],
        ),
        Route(
            "/api/v1/projects/{prj}/workflow-hooks/dry-run",
            dummy_endpoint,
            methods=["POST"],
        ),
    ]
    client = TestClient(
        Starlette(routes=routes, middleware=[Middleware(ScriptDepthGuardMiddleware)])
    )

    # 1. Normal depth 0 or absent header is allowed
    res_ok_cf = client.post("/api/v1/projects/PRJ/custom-fields/test-execute")
    assert res_ok_cf.status_code == 200

    res_ok_wf = client.post("/api/v1/projects/PRJ/workflow-hooks/dry-run")
    assert res_ok_wf.status_code == 200

    # 2. X-Kanban-Script-Depth >= 1 blocks test-execute with 409 SCRIPT_RECURSION_BLOCKED
    res_blocked_cf = client.post(
        "/api/v1/projects/PRJ/custom-fields/test-execute",
        headers={"X-Kanban-Script-Depth": "1"},
    )
    assert res_blocked_cf.status_code == 409
    assert res_blocked_cf.json()["code"] == "SCRIPT_RECURSION_BLOCKED"

    # 3. X-Kanban-Script-Depth >= 1 blocks dry-run with 409 SCRIPT_RECURSION_BLOCKED
    res_blocked_wf = client.post(
        "/api/v1/projects/PRJ/workflow-hooks/dry-run",
        headers={"X-Kanban-Script-Depth": "1"},
    )
    assert res_blocked_wf.status_code == 409
    assert res_blocked_wf.json()["code"] == "SCRIPT_RECURSION_BLOCKED"


async def test_test_execute_endpoint_security_and_wasm_verification(  # noqa: PLR0915
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
) -> None:
    """Verify PROJECT_ADMIN + AAL2 gating and ApprovedWasmModule verification on test-execute."""
    admin = await make_user("admin", workspace_role="WORKSPACE_ADMIN")
    member = await make_user("member")
    _ = await make_project(
        "SEC", created_by=admin, roles={admin: "PROJECT_ADMIN", member: "MEMBER"}
    )

    # Create issue SEC-1 as admin with AAL2
    resp_iss = await _as_admin_aal2(api_env, admin).post(
        "/api/v1/projects/SEC/issues",
        json={"summary": "Security Test Work Item", "description_markdown": "Test Description"},
    )
    assert resp_iss.status_code == 201
    issue_key = resp_iss.json()["key"]

    test_payload = {
        "issue_key": issue_key,
        "tier": "wasm",
        "output_format": "text",
        "output_format_metadata": {},
        "script_source": "formula: issue.summary",
    }

    # 1. Member user gets 403 INSUFFICIENT_CAPABILITY
    resp_member = await _as_admin_aal2(api_env, member).post(
        "/api/v1/projects/SEC/custom-fields/test-execute",
        json=test_payload,
    )
    assert resp_member.status_code == 403
    assert resp_member.json()["code"] in ("INSUFFICIENT_CAPABILITY", "PROJECT_ADMIN_REQUIRED")

    # 2. Admin with AAL1 gets 403 AAL2_REQUIRED
    resp_aal1 = await _as_user_aal1(api_env, admin).post(
        "/api/v1/projects/SEC/custom-fields/test-execute",
        json=test_payload,
    )
    assert resp_aal1.status_code == 403
    assert resp_aal1.json()["code"] == "AAL2_REQUIRED"

    # 3. Admin with AAL2 succeeds for safe formula
    resp_aal2 = await _as_admin_aal2(api_env, admin).post(
        "/api/v1/projects/SEC/custom-fields/test-execute",
        json=test_payload,
    )
    assert resp_aal2.status_code == 200
    assert resp_aal2.json()["status"] == "SUCCESS"
    assert resp_aal2.json()["value"] == "Security Test Work Item"

    # 4. Wasm test-execution with unapproved module sha256 gets 404 WASM_MODULE_NOT_FOUND
    resp_unapproved_sha = await _as_admin_aal2(api_env, admin).post(
        "/api/v1/projects/SEC/custom-fields/test-execute",
        json={
            "issue_key": issue_key,
            "tier": "wasm",
            "output_format": "severity_pill",
            "output_format_metadata": {},
            "script_source": "wasm:fake_module",
            "wasm_module_sha256": "ee" * 32,
        },
    )
    assert resp_unapproved_sha.status_code == 404
    assert resp_unapproved_sha.json()["code"] == "WASM_MODULE_NOT_FOUND"

    # 5. Wasm test-execution with unapproved raw bytecode gets 404 WASM_MODULE_NOT_FOUND
    echo_bytes = _read_fixture("echo_cvss.wasm")
    echo_b64 = base64.b64encode(echo_bytes).decode("ascii")
    resp_unapproved_bytes = await _as_admin_aal2(api_env, admin).post(
        "/api/v1/projects/SEC/custom-fields/test-execute",
        json={
            "issue_key": issue_key,
            "tier": "wasm",
            "output_format": "severity_pill",
            "output_format_metadata": {},
            "script_source": echo_b64,
        },
    )
    assert resp_unapproved_bytes.status_code == 404
    assert resp_unapproved_bytes.json()["code"] == "WASM_MODULE_NOT_FOUND"

    # 6. Upload approved wasm module
    resp_wasm = await _as_admin_aal2(api_env, admin).post(
        "/api/v1/projects/SEC/wasm-modules",
        json={"name": "echo_cvss", "wasm_base64": echo_b64},
    )
    assert resp_wasm.status_code == 201
    wasm_sha = resp_wasm.json()["sha256"]

    # 7. Wasm test-execution with approved module succeeds
    resp_approved_run = await _as_admin_aal2(api_env, admin).post(
        "/api/v1/projects/SEC/custom-fields/test-execute",
        json={
            "issue_key": issue_key,
            "tier": "wasm",
            "output_format": "severity_pill",
            "output_format_metadata": {},
            "script_source": "wasm:echo_cvss",
            "wasm_module_sha256": wasm_sha,
        },
    )
    assert resp_approved_run.status_code == 200
    assert resp_approved_run.json()["status"] == "SUCCESS"
    assert "Executed Wasm module" in resp_approved_run.json()["logs"]

    # 7b. Wasm test-execution with approved raw bytecode in script_source succeeds
    resp_approved_raw = await _as_admin_aal2(api_env, admin).post(
        "/api/v1/projects/SEC/custom-fields/test-execute",
        json={
            "issue_key": issue_key,
            "tier": "wasm",
            "output_format": "severity_pill",
            "output_format_metadata": {},
            "script_source": echo_b64,
            "wasm_module_sha256": None,
        },
    )
    assert resp_approved_raw.status_code == 200
    assert resp_approved_raw.json()["status"] == "SUCCESS"

    # 8. Invalid hex in wasm_module_sha256 returns 422 INVALID_WASM_SHA256
    resp_invalid_hex = await _as_admin_aal2(api_env, admin).post(
        "/api/v1/projects/SEC/custom-fields/test-execute",
        json={
            "issue_key": issue_key,
            "tier": "wasm",
            "output_format": "text",
            "output_format_metadata": {},
            "script_source": "test",
            "wasm_module_sha256": "not-valid-hex-zzz",
        },
    )
    assert resp_invalid_hex.status_code == 422
    assert resp_invalid_hex.json()["code"] == "INVALID_WASM_SHA256"

    # 9. Missing wasm source and no sha returns 404 WASM_MODULE_NOT_FOUND
    resp_no_wasm = await _as_admin_aal2(api_env, admin).post(
        "/api/v1/projects/SEC/custom-fields/test-execute",
        json={
            "issue_key": issue_key,
            "tier": "wasm",
            "output_format": "text",
            "output_format_metadata": {},
            "script_source": "// just comments\n# no bytes",
            "wasm_module_sha256": None,
        },
    )
    assert resp_no_wasm.status_code == 404
    assert resp_no_wasm.json()["code"] == "WASM_MODULE_NOT_FOUND"

    # 10. Invalid wasm binary bytes returns 422 WASM_BINARY_INVALID
    resp_invalid_wasm = await _as_admin_aal2(api_env, admin).post(
        "/api/v1/projects/SEC/custom-fields/test-execute",
        json={
            "issue_key": issue_key,
            "tier": "wasm",
            "output_format": "text",
            "output_format_metadata": {},
            "script_source": "???not_hex_or_base64!!!",
        },
    )
    assert resp_invalid_wasm.status_code == 422
    assert resp_invalid_wasm.json()["code"] == "WASM_BINARY_INVALID"

    # 11. Scalar execution succeeds
    resp_scalar = await _as_admin_aal2(api_env, admin).post(
        "/api/v1/projects/SEC/custom-fields/test-execute",
        json={
            "issue_key": issue_key,
            "tier": "wasm",
            "output_format": "number",
            "output_format_metadata": {},
            "script_source": "scalar: 42",
        },
    )
    assert resp_scalar.status_code == 200
    assert resp_scalar.json()["value"] == 42

    # 12. Legacy return execution succeeds
    resp_return = await _as_admin_aal2(api_env, admin).post(
        "/api/v1/projects/SEC/custom-fields/test-execute",
        json={
            "issue_key": issue_key,
            "tier": "wasm",
            "output_format": "text",
            "output_format_metadata": {},
            "script_source": "return 'Hello from return';",
        },
    )
    assert resp_return.status_code == 200
    assert resp_return.json()["value"] == "Hello from return"

    # 13. Invalid tier returns 422 from schema validation
    resp_bad_tier = await _as_admin_aal2(api_env, admin).post(
        "/api/v1/projects/SEC/custom-fields/test-execute",
        json={
            "issue_key": issue_key,
            "tier": "invalid_tier",
            "output_format": "text",
            "output_format_metadata": {},
            "script_source": "return 'abc';",
        },
    )
    assert resp_bad_tier.status_code == 422
    assert "tier" in str(resp_bad_tier.json())

    # 14. List values with script depth header
    resp_depth = await _as_admin_aal2(api_env, admin).get(
        f"/api/v1/issues/{issue_key}/custom-fields",
        headers={"x-kanban-script-depth": "1"},
    )
    assert resp_depth.status_code == 200

    # 15. Rate limiting on test-execute
    hit_429 = False
    for _ in range(15):
        resp_rl = await _as_admin_aal2(api_env, admin).post(
            "/api/v1/projects/SEC/custom-fields/test-execute",
            json=test_payload,
        )
        if resp_rl.status_code == 429:
            hit_429 = True
            assert resp_rl.json()["code"] == "RATE_LIMITED"
            break
    assert hit_429 is True


def test_eval_safe_formula_comprehensive_coverage() -> None:
    """Verify full coverage of formula evaluation paths."""
    ctx = {
        "issue": {
            "summary": "Sample",
            "count": 5,
            "items": ["a", "b", "c"],
            "meta": {"sub": "deep"},
        }
    }

    # Empty expression
    assert _eval_safe_formula("", ctx) == ""
    assert _eval_safe_formula("   ", ctx) == ""

    # Syntax error
    assert _eval_safe_formula("1 ++", ctx) is None

    # JS ternary
    assert _eval_safe_formula("true ? 'yes' : 'no'", ctx) == "yes"
    assert _eval_safe_formula("false ? 'yes' : 'no'", ctx) == "no"

    # Literals
    assert _eval_safe_formula("true", ctx) is True
    assert _eval_safe_formula("False", ctx) is False
    assert _eval_safe_formula("null", ctx) is None
    assert _eval_safe_formula("None", ctx) is None
    assert _eval_safe_formula("unknown_ident", ctx) == "unknown_ident"
    assert _eval_safe_formula("__private", ctx) is None

    # Dict subscript and list subscript
    assert _eval_safe_formula("issue['summary']", ctx) == "Sample"
    assert _eval_safe_formula("issue['missing']", ctx) == ""
    assert _eval_safe_formula("issue.items[1]", ctx) == "b"
    assert _eval_safe_formula("issue.items[10]", ctx) == ""
    assert _eval_safe_formula("issue.meta.sub", ctx) == "deep"
    assert _eval_safe_formula("issue.meta.missing", ctx) == ""
    assert _eval_safe_formula("issue.meta.__subclasses__", ctx) is None

    # Binary ops
    assert _eval_safe_formula("issue.summary + ' suffix'", ctx) == "Sample suffix"
    assert _eval_safe_formula("10 - 3", ctx) == 7
    assert _eval_safe_formula("10 / 2", ctx) == 5.0
    assert _eval_safe_formula("10 / 0", ctx) == 0
    assert _eval_safe_formula("2 ** -2", ctx) == 0.25
    assert _eval_safe_formula("2 ** -65", ctx) is None
    assert _eval_safe_formula("0 ** -1", ctx) is None
    assert _eval_safe_formula("0.0 ** -2", ctx) is None
    assert _eval_safe_formula("'a' ** 2", ctx) is None
    assert _eval_safe_formula("'a' * -1", ctx) is None
    assert _eval_safe_formula("-1 * 'a'", ctx) is None
    assert _eval_safe_formula("10 * 'a'", ctx) == "aaaaaaaaaa"

    # Dict literal
    assert _eval_safe_formula("{'key': 'val'}['key']", ctx) == "val"


async def test_patch_wasm_module_sha256_revokes_approved_escalation(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
) -> None:
    """Verify PATCH changing wasm_module_sha256 revokes approval via tamper trigger."""
    admin = await make_user("admin_tamper", workspace_role="WORKSPACE_ADMIN")
    _ = await make_project("TMPR", created_by=admin, roles={admin: "PROJECT_ADMIN"})

    # 1. Upload an approved wasm module
    echo_bytes = _read_fixture("echo_cvss.wasm")
    echo_b64 = base64.b64encode(echo_bytes).decode("ascii")
    resp_wasm = await _as_admin_aal2(api_env, admin).post(
        "/api/v1/projects/TMPR/wasm-modules",
        json={"name": "echo_cvss_tamper", "wasm_base64": echo_b64},
    )
    assert resp_wasm.status_code == 201
    wasm_sha1 = resp_wasm.json()["sha256"]

    # 2. Create escalated custom field (PROJECT_ADMIN_SP)
    resp_create = await _as_admin_aal2(api_env, admin).post(
        "/api/v1/projects/TMPR/custom-fields",
        json={
            "slug": "escalated-wasm-field",
            "name": "Escalated Wasm Field",
            "tier": "wasm",
            "output_format": "text",
            "output_format_metadata": {"format": "text", "max_length": 50},
            "script_source": "wasm:echo_cvss_tamper",
            "target_scope": "PROJECT",
            "credential_mode": "PROJECT_ADMIN_SP",
            "wasm_module_sha256": wasm_sha1,
        },
    )
    assert resp_create.status_code == 201
    field_data = resp_create.json()
    fid = field_data["id"]
    m_sha = field_data["manifest_sha256"]

    # 3. Request escalation approval and approve it
    resp_req = await _as_admin_aal2(api_env, admin).post(
        f"/api/v1/custom-fields/{fid}/approval-requests",
        json={"manifest_sha256": m_sha, "justification": "Escalation for tamper test"},
    )
    assert resp_req.status_code == 201
    appr_id = resp_req.json()["id"]

    resp_appr = await _as_admin_aal2(api_env, admin).post(
        f"/api/v1/custom-field-approvals/{appr_id}/approve",
        json={"manifest_sha256": m_sha, "sp_warning_acknowledged": True},
    )
    assert resp_appr.status_code == 200
    assert resp_appr.json()["status"] == "APPROVED"

    # 4. PATCH changing wasm_module_sha256
    wasm_sha2 = "aa" * 32
    resp_patch = await _as_admin_aal2(api_env, admin).patch(
        f"/api/v1/projects/TMPR/custom-fields/{fid}",
        json={"wasm_module_sha256": wasm_sha2},
    )
    assert resp_patch.status_code == 200
    assert resp_patch.json()["manifest_sha256"] != m_sha

    # 5. Verify escalation row is REVOKED via custom_field_manifest_tamper_revoke trigger
    resp_approvals = await _as_admin_aal2(api_env, admin).get(
        f"/api/v1/custom-fields/{fid}/approvals",
    )
    assert resp_approvals.status_code == 200
    items = resp_approvals.json()
    appr_row = next((a for a in items if a["id"] == appr_id), None)
    assert appr_row is not None
    assert appr_row["status"] == "REVOKED"
    assert appr_row["revoked_reason"] == "MANIFEST_SHA256_CHANGED"
    assert appr_row["revoked_at"] is not None
