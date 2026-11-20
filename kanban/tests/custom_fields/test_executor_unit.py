# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Unit tests for CustomFieldExecutor and safe formula evaluation (KAN-17, KB-P3-AUDIT-11)."""

# ruff: noqa: E501, PLR0915, PLR0913, SLF001, ARG001, ANN401, TRY003, EM101

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import ApprovedWasmModule, CustomFieldDefinition, Project
from kanban.api.deps import PrincipalContext
from kanban.api.problems import ProblemException
from kanban.api.v1.schemas.custom_fields import CustomFieldTestExecuteRequest
from kanban.custom_fields.approvals import ApprovalRevokedError
from kanban.custom_fields.executor import (
    CustomFieldExecutor,
    _eval_safe_formula,
    _get_caller_access_hash,
)
from kanban.sandbox.wasm_runner import WasmRunError, WasmRunResult


def test_eval_safe_formula_edge_cases() -> None:
    """Test AST bounds, edge cases, error handlers, and operators in safe formula."""
    # Empty expression returns empty string
    assert _eval_safe_formula("", {}) == ""
    assert _eval_safe_formula("   ", {}) == ""

    # Syntax error or invalid expression returns None
    assert _eval_safe_formula("def foo(): pass", {}) is None
    assert _eval_safe_formula("1 + +", {}) is None

    # Dunder attribute or identifier starting with __ returns None
    assert _eval_safe_formula("__secret__", {}) is None
    assert _eval_safe_formula("issue.__dict__", {"issue": {}}) is None

    # JS Boolean and Null identifiers
    assert _eval_safe_formula("true", {}) is True
    assert _eval_safe_formula("false", {}) is False
    assert _eval_safe_formula("null", {}) is None
    assert _eval_safe_formula("None", {}) is None

    # Unknown variable returns identifier string
    assert _eval_safe_formula("unknown_variable", {}) == "unknown_variable"

    # Ternary without regex match (unmatched ? :)
    assert _eval_safe_formula("a ? b", {}) is None

    # Subscript access
    assert _eval_safe_formula('issue["key"]', {"issue": {"key": "K-1"}}) == "K-1"

    # Multiplication limits and negative factors
    assert _eval_safe_formula('"abc" * 3', {}) == "abcabcabc"
    assert _eval_safe_formula('"abc" * -1', {}) is None
    assert _eval_safe_formula('-1 * "abc"', {}) is None
    assert _eval_safe_formula('"a" * 5000', {}) is None
    assert _eval_safe_formula('5000 * "a"', {}) is None

    # Division by zero returns 0
    assert _eval_safe_formula("10 / 0", {}) == 0
    assert _eval_safe_formula("10 / 2", {}) == 5.0

    # Exponentiation edge cases
    assert _eval_safe_formula("2 ** 10", {}) == 1024
    assert _eval_safe_formula("2 ** 65", {}) is None  # Exponent > 64
    assert _eval_safe_formula("2 ** -65", {}) is None  # Exponent < -64
    assert _eval_safe_formula("2000000 ** 2", {}) is None  # Base > 1_000_000
    assert _eval_safe_formula('"str" ** 2', {}) is None  # Non-numeric base

    # Unary operators
    assert _eval_safe_formula("-42", {}) == -42
    assert _eval_safe_formula("-3.14", {}) == -3.14
    assert _eval_safe_formula('-"string"', {}) is None
    assert _eval_safe_formula("+42", {}) == 42
    assert _eval_safe_formula("+3.14", {}) == 3.14
    assert _eval_safe_formula('+"string"', {}) is None
    assert _eval_safe_formula("not False", {}) is True
    assert _eval_safe_formula("not True", {}) is False
    assert _eval_safe_formula("not 0", {}) is True

    # Comparisons
    assert _eval_safe_formula("1 == 1", {}) is True
    assert _eval_safe_formula("1 == 2", {}) is False
    assert _eval_safe_formula("1 != 2", {}) is True
    assert _eval_safe_formula("1 != 1", {}) is False

    # Dictionary and List literals
    assert _eval_safe_formula('{"key": "val", "num": 10}', {}) == {"key": "val", "num": 10}
    assert _eval_safe_formula("[1, 2, 3]", {}) == [1, 2, 3]

    # IfExp (inline ternary)
    assert _eval_safe_formula("1 if True else 2", {}) == 1
    assert _eval_safe_formula("1 if False else 2", {}) == 2


def test_get_caller_access_hash_variations() -> None:
    """Test deterministic derivation of caller access hash across bytes, hex string, and fallback."""
    # 1. 32-byte hash already present
    caller1 = MagicMock(spec=PrincipalContext)
    b32 = b"x" * 32
    caller1.user_access_hash = b32
    assert _get_caller_access_hash(caller1) == b32

    # 2. 64-char hex string
    caller2 = MagicMock(spec=PrincipalContext)
    hex64 = "ab" * 32
    caller2.user_access_hash = hex64
    assert _get_caller_access_hash(caller2) == bytes.fromhex(hex64)

    # 3. 64-char invalid hex string (trigger ValueError and fallback)
    caller3 = MagicMock(spec=PrincipalContext)
    caller3.user_access_hash = "zz" * 32
    caller3.workspace_id = uuid.uuid4()
    caller3.principal_id = uuid.uuid4()
    caller3.token_scopes = ("read", "write")
    res3 = _get_caller_access_hash(caller3)
    assert len(res3) == 32

    # 4. user_access_hash is None (fallback to workspace:principal:scopes)
    caller4 = MagicMock(spec=PrincipalContext)
    caller4.user_access_hash = None
    caller4.workspace_id = uuid.uuid4()
    caller4.principal_id = uuid.uuid4()
    caller4.token_scopes = ("session",)
    res4 = _get_caller_access_hash(caller4)
    assert len(res4) == 32


@pytest.mark.asyncio
async def test_execute_for_issue_tier_and_format_branches() -> None:
    """Test CustomFieldExecutor.execute_for_issue across tiers, invalid outputs, and audit."""
    session = AsyncMock(spec=AsyncSession)
    executor = CustomFieldExecutor(session)

    issue_id = uuid.uuid4()
    proj_id = uuid.uuid4()
    ws_id = uuid.uuid4()
    issue = MagicMock()
    issue.id = issue_id
    issue.workspace_id = ws_id
    issue.project_id = proj_id
    issue.summary = "Test Issue"
    issue.description_markdown = ""
    issue.state_id = uuid.uuid4()
    issue.priority_id = uuid.uuid4()

    caller = MagicMock(spec=PrincipalContext)
    caller.workspace_id = ws_id
    caller.principal_id = uuid.uuid4()
    caller.token_scopes = ("session",)
    caller.user_access_hash = b"0" * 32

    def create_mock_defn(
        *,
        tier: str = "wasm",
        target_scope: str = "PROJECT",
        script_source: str = "",
        output_format: str = "text",
        output_format_metadata: dict[str, Any] | None = None,
        wasm_module_sha256: bytes | None = None,
        is_enabled: bool = True,
    ) -> MagicMock:
        d = MagicMock(spec=CustomFieldDefinition)
        d.id = uuid.uuid4()
        d.workspace_id = ws_id
        d.project_id = proj_id
        d.slug = f"cf-{uuid.uuid4().hex[:6]}"
        d.name = "Test Field"
        d.output_format = output_format
        d.output_format_metadata = output_format_metadata or {}
        d.tier = tier
        d.target_scope = target_scope
        d.credential_mode = "INVOKING_USER"
        d.script_version = 1
        d.script_source = script_source
        d.wasm_module_sha256 = wasm_module_sha256
        d.is_enabled = is_enabled
        return d

    with (
        patch(
            "kanban.custom_fields.executor.resolve_issue_ref", new_callable=AsyncMock
        ) as mock_res,
        patch("kanban.custom_fields.executor.assert_execution_authorized", new_callable=AsyncMock),
    ):
        mock_res.return_value = issue

        # 0. Calling convention: (session, caller, issue_key, field_ref)
        defn_conv = create_mock_defn(script_source='scalar: "convention-test"')
        mock_res_db = MagicMock()
        mock_res_db.scalar_one_or_none.side_effect = [defn_conv, None]
        session.execute.return_value = mock_res_db
        res_conv = await executor.execute_for_issue(session, caller, "ISSUE-1", defn_conv.id)
        assert res_conv["status"] == "computed"
        assert res_conv["value"] == "convention-test"

        # 1. Cached value found and returned
        cached_row = MagicMock()
        cached_row.value_json = {"score": 42}
        cached_row.computed_at = datetime.now(UTC)
        cached_row.last_latency_ms = 5
        defn_cached = create_mock_defn(output_format="json")

        mock_res_db.scalar_one_or_none.side_effect = [defn_cached, cached_row]
        cached_res = await executor.execute_for_issue(
            "ISSUE-1", defn_cached.id, caller, session=session, force_refresh=False
        )
        assert cached_res["status"] == "cached"
        assert cached_res["value"] == {"score": 42}

        # 2. Scalar raw string fallback when not valid json
        defn_scalar = create_mock_defn(script_source="scalar: raw-plain-string")
        mock_res_db.scalar_one_or_none.side_effect = [defn_scalar]
        res = await executor.execute_for_issue(
            "ISSUE-1", defn_scalar.id, caller, session=session, force_refresh=True
        )
        assert res["status"] == "computed"
        assert res["value"] == "raw-plain-string"

        # 3. Formula execution
        defn_formula = create_mock_defn(output_format="number", script_source="formula: 20 + 22")
        mock_res_db.scalar_one_or_none.side_effect = [defn_formula]
        res = await executor.execute_for_issue(
            "ISSUE-1", defn_formula.id, caller, session=session, force_refresh=True
        )
        assert res["status"] == "computed"
        assert res["value"] == 42

        # 4. Return statement execution
        defn_ret = create_mock_defn(script_source='return "hello-from-script";')
        mock_res_db.scalar_one_or_none.side_effect = [defn_ret]
        res = await executor.execute_for_issue(
            "ISSUE-1", defn_ret.id, caller, session=session, force_refresh=True
        )
        assert res["status"] == "computed"
        assert res["value"] == "hello-from-script"

        # 5. Return statement fallback to raw string on json decode error
        defn_ret_raw = create_mock_defn(script_source="return raw-unquoted-value")
        mock_res_db.scalar_one_or_none.side_effect = [defn_ret_raw]
        res = await executor.execute_for_issue(
            "ISSUE-1", defn_ret_raw.id, caller, session=session, force_refresh=True
        )
        assert res["status"] == "computed"
        assert res["value"] == "raw-unquoted-value"

        # 6. Wasm module sha256 not found in DB
        defn_wasm_sha = create_mock_defn(wasm_module_sha256=b"1" * 32)
        mock_res_db.scalar_one_or_none.side_effect = [defn_wasm_sha, None]  # defn, mod_stmt
        with pytest.raises(ProblemException) as exc_info:
            await executor.execute_for_issue(
                "ISSUE-1", defn_wasm_sha.id, caller, session=session, force_refresh=True
            )
        assert exc_info.value.code == "WASM_MODULE_NOT_FOUND"

        # 7. Wasm module sha256 found, runner raises WasmRunError
        mock_wasm_mod = MagicMock(spec=ApprovedWasmModule)
        mock_wasm_mod.wasm_bytes = b"\x00asm\x01\x00\x00\x00"
        mock_res_db.scalar_one_or_none.side_effect = [defn_wasm_sha, mock_wasm_mod]

        with patch.object(
            executor._tier_a, "run", side_effect=WasmRunError("Fuel ran out", code="FUEL_EXHAUSTED")
        ):
            with pytest.raises(ProblemException) as exc_info:
                await executor.execute_for_issue(
                    "ISSUE-1", defn_wasm_sha.id, caller, session=session, force_refresh=True
                )
            assert exc_info.value.code == "FUEL_EXHAUSTED"

        # 8. Raw wasm bytecode invalid decoding
        defn_bad_bin = create_mock_defn(script_source="not-valid-hex-or-base64---!@#$%")
        mock_res_db.scalar_one_or_none.side_effect = [defn_bad_bin]
        with pytest.raises(ProblemException) as exc_info:
            await executor.execute_for_issue(
                "ISSUE-1", defn_bad_bin.id, caller, session=session, force_refresh=True
            )
        assert exc_info.value.code == "WASM_BINARY_INVALID"

        # 9. Raw wasm bytecode run error
        defn_valid_hex = create_mock_defn(script_source="0061736d01000000")
        mock_res_db.scalar_one_or_none.side_effect = [defn_valid_hex]
        with patch.object(
            executor._tier_a, "run", side_effect=WasmRunError("Trapped", code="TRAP_UNREACHABLE")
        ):
            with pytest.raises(ProblemException) as exc_info:
                await executor.execute_for_issue(
                    "ISSUE-1", defn_valid_hex.id, caller, session=session, force_refresh=True
                )
            assert exc_info.value.code == "TRAP_UNREACHABLE"

        # 10. Unsupported tier
        defn_bad_tier = create_mock_defn(tier="unsupported_sandbox")
        mock_res_db.scalar_one_or_none.side_effect = [defn_bad_tier]
        with pytest.raises(ProblemException) as exc_info:
            await executor.execute_for_issue(
                "ISSUE-1", defn_bad_tier.id, caller, session=session, force_refresh=True
            )
        assert exc_info.value.code == "INVALID_TIER"

        # 11. Script output is invalid JSON
        defn_bad_json = create_mock_defn(tier="nsjail", script_source="echo hello")
        mock_res_db.scalar_one_or_none.side_effect = [defn_bad_json]
        with patch.object(executor._tier_b, "run", new_callable=AsyncMock) as mock_tier_b:
            mock_tier_b.return_value = b"{not-valid-json"
            with pytest.raises(ProblemException) as exc_info:
                await executor.execute_for_issue(
                    "ISSUE-1", defn_bad_json.id, caller, session=session, force_refresh=True
                )
            assert exc_info.value.code == "SCRIPT_OUTPUT_SCHEMA_INVALID"

        # 12. Script output schema format validation failure
        defn_bad_format = create_mock_defn(
            tier="nsjail", output_format="number", output_format_metadata={"min": 10}
        )
        mock_res_db.scalar_one_or_none.side_effect = [defn_bad_format]
        with patch.object(executor._tier_b, "run", new_callable=AsyncMock) as mock_tier_b:
            mock_tier_b.return_value = b"5"  # < min: 10
            with pytest.raises(ProblemException) as exc_info:
                await executor.execute_for_issue(
                    "ISSUE-1", defn_bad_format.id, caller, session=session, force_refresh=True
                )
            assert exc_info.value.code == "SCRIPT_OUTPUT_SCHEMA_INVALID"

        # 13. SERVER scope records activity
        defn_server = create_mock_defn(target_scope="SERVER", script_source='scalar: "server-ok"')
        mock_res_db.scalar_one_or_none.side_effect = [defn_server]
        with patch(
            "kanban.custom_fields.executor.record_activity", new_callable=AsyncMock
        ) as mock_record:
            res = await executor.execute_for_issue(
                "ISSUE-1", defn_server.id, caller, session=session, force_refresh=True
            )
            assert res["status"] == "computed"
            assert res["value"] == "server-ok"
            mock_record.assert_called_once()

        # 14. ApprovalRevokedError handling
        with patch(
            "kanban.custom_fields.executor.assert_execution_authorized",
            side_effect=ApprovalRevokedError("Tamper detected"),
        ):
            defn_revoked = create_mock_defn()
            mock_res_db.scalar_one_or_none.side_effect = [defn_revoked]
            with pytest.raises(ProblemException) as exc_info:
                await executor.execute_for_issue(
                    "ISSUE-1", defn_revoked.id, caller, session=session, force_refresh=True
                )
            assert exc_info.value.code == "APPROVAL_REVOKED"


@pytest.mark.asyncio
async def test_list_values_for_issue_branches() -> None:
    """Test list_values_for_issue with uncacheable scopes, cached rows, and ProblemException handling."""
    session = AsyncMock(spec=AsyncSession)
    executor = CustomFieldExecutor(session)

    issue_id = uuid.uuid4()
    ws_id = uuid.uuid4()
    proj_id = uuid.uuid4()
    issue = MagicMock()
    issue.id = issue_id
    issue.workspace_id = ws_id
    issue.project_id = proj_id

    caller = MagicMock(spec=PrincipalContext)
    caller.workspace_id = ws_id
    caller.principal_id = uuid.uuid4()
    caller.token_scopes = ("session",)
    caller.user_access_hash = b"1" * 32

    # Uncacheable definition (target_scope=SERVER) -> status 'not_computed'
    defn_server = MagicMock(spec=CustomFieldDefinition)
    defn_server.id = uuid.uuid4()
    defn_server.slug = "server-field"
    defn_server.name = "Server Field"
    defn_server.output_format = "text"
    defn_server.output_format_metadata = {}
    defn_server.tier = "wasm"
    defn_server.target_scope = "SERVER"
    defn_server.credential_mode = "INVOKING_USER"
    defn_server.script_version = 1

    # Cacheable definition not in cache -> status 'not_computed'
    defn_uncached = MagicMock(spec=CustomFieldDefinition)
    defn_uncached.id = uuid.uuid4()
    defn_uncached.slug = "uncached-field"
    defn_uncached.name = "Uncached Field"
    defn_uncached.output_format = "text"
    defn_uncached.output_format_metadata = {}
    defn_uncached.tier = "wasm"
    defn_uncached.target_scope = "PROJECT"
    defn_uncached.credential_mode = "INVOKING_USER"
    defn_uncached.script_version = 1

    # Definition with revoked approval
    defn_revoked = MagicMock(spec=CustomFieldDefinition)
    defn_revoked.id = uuid.uuid4()
    defn_revoked.slug = "revoked-field"
    defn_revoked.name = "Revoked Field"
    defn_revoked.output_format = "text"
    defn_revoked.output_format_metadata = {}
    defn_revoked.tier = "wasm"
    defn_revoked.target_scope = "PROJECT"
    defn_revoked.credential_mode = "INVOKING_USER"
    defn_revoked.script_version = 1

    with patch(
        "kanban.custom_fields.executor.resolve_issue_ref", new_callable=AsyncMock
    ) as mock_res:
        mock_res.return_value = issue

        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [defn_server, defn_uncached, defn_revoked]
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_result.scalar_one_or_none.return_value = None
        session.execute.return_value = mock_result

        async def mock_auth_side_effect(sess: Any, d: Any) -> None:
            if d.slug == "revoked-field":
                raise ApprovalRevokedError("Manifest hash mismatch")

        with patch(
            "kanban.custom_fields.executor.assert_execution_authorized",
            side_effect=mock_auth_side_effect,
        ):
            # Test read-only query (cached_only=True)
            results = await executor.list_values_for_issue(
                session, caller, "ISSUE-1", cached_only=True
            )
            assert len(results) == 3
            assert results[0]["status"] == "not_computed"
            assert results[1]["status"] == "not_computed"
            assert results[2]["status"] == "APPROVAL_REVOKED"

            # Test compute loop where execute_for_issue raises ProblemException
            mock_scalars.all.return_value = [defn_uncached]
            with patch.object(executor, "execute_for_issue", new_callable=AsyncMock) as mock_exec:
                mock_exec.side_effect = ProblemException(
                    status=422, code="SCRIPT_FAILED", title="Failed"
                )
                results_fail = await executor.list_values_for_issue(
                    session, caller, "ISSUE-1", cached_only=False
                )
                assert len(results_fail) == 1
                assert results_fail[0]["status"] == "SCRIPT_FAILED"


@pytest.mark.asyncio
async def test_test_execute_edge_cases_and_exceptions() -> None:
    """Test CustomFieldExecutor.test_execute edge cases, error handlers, and sandboxes."""
    session = AsyncMock(spec=AsyncSession)
    executor = CustomFieldExecutor(session)

    proj_id = uuid.uuid4()
    project = MagicMock(spec=Project)
    project.id = proj_id
    project.key = "KAN"

    caller = MagicMock(spec=PrincipalContext)
    caller.workspace_id = uuid.uuid4()
    caller.principal_id = uuid.uuid4()

    # 1. Issue does not belong to project raises ProblemException directly
    issue_other_proj = MagicMock()
    issue_other_proj.id = uuid.uuid4()
    issue_other_proj.project_id = uuid.uuid4()

    req = CustomFieldTestExecuteRequest(
        issue_key="KAN-99",
        tier="wasm",
        output_format="text",
        output_format_metadata={},
        script_source='scalar: "ok"',
    )

    with patch(
        "kanban.custom_fields.executor.resolve_issue_ref", new_callable=AsyncMock
    ) as mock_res:
        mock_res.return_value = issue_other_proj
        with pytest.raises(ProblemException) as exc_info:
            await executor.test_execute(session, caller, project, req)
        assert exc_info.value.code == "ISSUE_NOT_IN_PROJECT"

    # Issue matches project
    issue = MagicMock()
    issue.id = uuid.uuid4()
    issue.project_id = proj_id
    issue.summary = "Matching issue"
    issue.description_markdown = ""
    issue.state_id = uuid.uuid4()
    issue.priority_id = uuid.uuid4()

    with patch(
        "kanban.custom_fields.executor.resolve_issue_ref", new_callable=AsyncMock
    ) as mock_res:
        mock_res.return_value = issue

        # 2. Return statement in test_execute
        req_ret = CustomFieldTestExecuteRequest(
            issue_key="KAN-1",
            tier="wasm",
            output_format="text",
            output_format_metadata={},
            script_source='return "ret-val";',
        )
        res_ret = await executor.test_execute(session, caller, project, req_ret)
        assert res_ret["status"] == "SUCCESS"
        assert res_ret["value"] == "ret-val"

        # 3. Return statement fallback on invalid json
        req_ret_raw = CustomFieldTestExecuteRequest(
            issue_key="KAN-1",
            tier="wasm",
            output_format="text",
            output_format_metadata={},
            script_source="return raw_text_no_quotes",
        )
        res_ret_raw = await executor.test_execute(session, caller, project, req_ret_raw)
        assert res_ret_raw["status"] == "SUCCESS"
        assert res_ret_raw["value"] == "raw_text_no_quotes"

        # 4. Wasm module sha256 not found in registry
        req_wasm_sha = CustomFieldTestExecuteRequest(
            issue_key="KAN-1",
            tier="wasm",
            output_format="text",
            output_format_metadata={},
            script_source="// wasm",
            wasm_module_sha256="aa" * 32,
        )
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute.return_value = mock_result

        res_sha_nf = await executor.test_execute(session, caller, project, req_wasm_sha)
        assert res_sha_nf["status"] == "ERROR"
        assert "WebAssembly module was not found" in (res_sha_nf["error"] or "")

        # 5. Wasm module sha256 found and executed
        mock_wasm_mod = MagicMock()
        mock_wasm_mod.wasm_bytes = b"\x00asm\x01\x00\x00\x00"
        mock_result.scalar_one_or_none.return_value = mock_wasm_mod
        with patch.object(executor._tier_a, "run", new_callable=AsyncMock) as mock_tier_a:
            mock_tier_a.return_value = WasmRunResult(
                output_bytes=b'"wasm-executed"', fuel_consumed=10, duration_ms=2
            )
            res_sha_ok = await executor.test_execute(session, caller, project, req_wasm_sha)
            assert res_sha_ok["status"] == "SUCCESS"
            assert res_sha_ok["value"] == "wasm-executed"

        # 6. Raw wasm bytecode invalid decoding
        req_bad_dec = CustomFieldTestExecuteRequest(
            issue_key="KAN-1",
            tier="wasm",
            output_format="text",
            output_format_metadata={},
            script_source="invalid_hex_or_base64_!@#$%",
        )
        res_bad_dec = await executor.test_execute(session, caller, project, req_bad_dec)
        assert res_bad_dec["status"] == "ERROR"
        assert "Cannot decode" in (res_bad_dec["error"] or "")

        # 7. Raw wasm bytecode not approved
        valid_hex = "0061736d01000000"
        req_hex = CustomFieldTestExecuteRequest(
            issue_key="KAN-1",
            tier="wasm",
            output_format="text",
            output_format_metadata={},
            script_source=valid_hex,
        )
        mock_result.scalar_one_or_none.return_value = None  # Not approved
        res_unapproved = await executor.test_execute(session, caller, project, req_hex)
        assert res_unapproved["status"] == "ERROR"
        assert "Approved WebAssembly module was not found" in (res_unapproved["error"] or "")

        # 8. Raw wasm bytecode approved and executed
        mock_result.scalar_one_or_none.return_value = mock_wasm_mod
        with patch.object(executor._tier_a, "run", new_callable=AsyncMock) as mock_tier_a:
            mock_tier_a.return_value = WasmRunResult(
                output_bytes=b'"raw-wasm-ok"', fuel_consumed=15, duration_ms=3
            )
            res_hex_ok = await executor.test_execute(session, caller, project, req_hex)
            assert res_hex_ok["status"] == "SUCCESS"
            assert res_hex_ok["value"] == "raw-wasm-ok"

        # 9. nsjail execution
        req_nsjail = CustomFieldTestExecuteRequest(
            issue_key="KAN-1",
            tier="nsjail",
            output_format="text",
            output_format_metadata={},
            script_source="print('hello')",
        )
        with patch.object(executor._tier_b, "run", new_callable=AsyncMock) as mock_tier_b:
            mock_tier_b.return_value = b'"nsjail-ok"'
            res_nsjail = await executor.test_execute(session, caller, project, req_nsjail)
            assert res_nsjail["status"] == "SUCCESS"
            assert res_nsjail["value"] == "nsjail-ok"

        # 10. Unsupported tier in test_execute
        req_bad_tier = CustomFieldTestExecuteRequest.model_construct(
            issue_key="KAN-1",
            tier="invalid_tier",
            output_format="text",
            output_format_metadata={},
            script_source="echo",
        )
        res_bad_tier = await executor.test_execute(session, caller, project, req_bad_tier)
        assert res_bad_tier["status"] == "ERROR"
        assert "Unsupported tier" in (res_bad_tier["error"] or "")

        # 11. Unexpected general exception handling
        with patch.object(executor._tier_b, "run", side_effect=RuntimeError("System fault")):
            res_runtime_err = await executor.test_execute(session, caller, project, req_nsjail)
            assert res_runtime_err["status"] == "ERROR"
            assert "System fault" in (res_runtime_err["error"] or "")
