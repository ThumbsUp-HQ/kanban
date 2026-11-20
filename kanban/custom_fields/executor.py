# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Custom field executor and partitioned cache manager (KB-P5-13, S13.2, S13.3)."""

from __future__ import annotations

import ast
import base64
import hashlib
import json
import re
import time
import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any, Final

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import (
    ApprovedWasmModule,
    CustomFieldDefinition,
    CustomFieldValue,
)
from kanban.api.problems import ProblemException, not_found
from kanban.custom_fields.approvals import (
    ApprovalRevokedError,
    assert_execution_authorized,
    compute_cache_partition_key,
)
from kanban.custom_fields.output_formats import (
    parse_output_format_metadata,
    validate_field_output_value,
)
from kanban.sandbox.wasm_runner import (
    TierAWasmRunner,
    TierBRunner,
    UnavailableTierBRunner,
    WasmRunError,
)
from kanban.services.activity import ActivityEventType, record_activity
from kanban.services.issue_keys import resolve_issue_ref

if TYPE_CHECKING:
    from database.models.projects import Project
    from kanban.api.deps import PrincipalContext
    from kanban.api.v1.schemas.custom_fields import CustomFieldTestExecuteRequest

_HASH_BYTES_LEN: Final[int] = 32
_HEX_DIGEST_LEN: Final[int] = 64
_MAX_FORMULA_NODES: Final[int] = 64
_MAX_FORMULA_DEPTH: Final[int] = 8
_MAX_POW_EXPONENT: Final[int] = 64
_MAX_POW_BASE: Final[int] = 1_000_000
_MAX_MULT_OUTPUT_LEN: Final[int] = 4096


def _check_formula_ast_bounds(node: ast.AST) -> bool:
    """Validate AST node count and tree depth against DoS limits."""
    for count, _ in enumerate(ast.walk(node), start=1):
        if count > _MAX_FORMULA_NODES:
            return False

    def _get_depth(cur: ast.AST) -> int:
        child_depths = [_get_depth(child) for child in ast.iter_child_nodes(cur)]
        return 1 + max(child_depths, default=0)

    return _get_depth(node) <= _MAX_FORMULA_DEPTH


def _eval_safe_formula(expr: str, issue: dict[str, Any]) -> Any:  # noqa: C901, PLR0915, ANN401
    """Safely evaluate a formula expression against issue payload without arbitrary execution."""
    expr = expr.strip()
    if not expr:
        return ""

    # Normalize JS operators
    expr = expr.replace("===", "==").replace("!==", "!=")
    if "?" in expr and ":" in expr:
        m = re.match(r"^(.*?)\s*\?\s*(.*?)\s*:\s*(.*)$", expr)
        if m:
            expr = f"({m.group(2).strip()}) if ({m.group(1).strip()}) else ({m.group(3).strip()})"

    try:
        parsed = ast.parse(expr, mode="eval")
    except (SyntaxError, ValueError):
        return None

    if not _check_formula_ast_bounds(parsed.body):
        return None

    def _eval_node(node: ast.AST, ctx: dict[str, Any]) -> Any:  # noqa: C901, PLR0911, PLR0912, ANN401
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.Name):
            if node.id.startswith("__"):
                return None
            if node.id in ctx:
                return ctx[node.id]
            if node.id in ("true", "True"):
                return True
            if node.id in ("false", "False"):
                return False
            if node.id in ("null", "None"):
                return None
            return node.id
        if isinstance(node, ast.Attribute):
            if node.attr.startswith("__"):
                return None
            val = _eval_node(node.value, ctx)
            if isinstance(val, dict):
                return val.get(node.attr, "")
            return ""
        if isinstance(node, ast.Subscript):
            val = _eval_node(node.value, ctx)
            slice_val = _eval_node(node.slice, ctx)
            if isinstance(val, dict):
                return val.get(slice_val, "")
            if isinstance(val, list) and isinstance(slice_val, int) and 0 <= slice_val < len(val):
                return val[slice_val]
            return ""
        if isinstance(node, ast.BinOp):
            left = _eval_node(node.left, ctx)
            right = _eval_node(node.right, ctx)
            if isinstance(node.op, ast.Add):
                if isinstance(left, str) or isinstance(right, str):
                    return f"{left}{right}"
                return left + right
            if isinstance(node.op, ast.Sub):
                return left - right
            if isinstance(node.op, ast.Mult):
                if isinstance(left, (str, list, tuple)) and isinstance(right, int):
                    if right < 0 or len(left) * right > _MAX_MULT_OUTPUT_LEN:
                        return None
                elif (
                    isinstance(right, (str, list, tuple))
                    and isinstance(left, int)
                    and (left < 0 or len(right) * left > _MAX_MULT_OUTPUT_LEN)
                ):
                    return None
                try:
                    return left * right
                except (OverflowError, MemoryError):
                    return None
            if isinstance(node.op, ast.Div):
                return left / right if right != 0 else 0
            if isinstance(node.op, ast.Pow):
                if not isinstance(left, (int, float)) or not isinstance(right, (int, float)):
                    return None
                if (
                    abs(left) > _MAX_POW_BASE
                    or right > _MAX_POW_EXPONENT
                    or right < -_MAX_POW_EXPONENT
                ):
                    return None
                try:
                    return left**right
                except (OverflowError, ValueError, ZeroDivisionError):
                    return None
        if isinstance(node, ast.Dict):
            return {
                _eval_node(k, ctx): _eval_node(v, ctx)
                for k, v in zip(node.keys, node.values, strict=False)
                if k is not None
            }
        if isinstance(node, ast.List):
            return [_eval_node(elt, ctx) for elt in node.elts]
        if isinstance(node, ast.IfExp):
            cond = _eval_node(node.test, ctx)
            return _eval_node(node.body, ctx) if cond else _eval_node(node.orelse, ctx)
        if isinstance(node, ast.UnaryOp):
            operand = _eval_node(node.operand, ctx)
            if isinstance(node.op, ast.USub):
                return -operand if isinstance(operand, (int, float)) else None
            if isinstance(node.op, ast.UAdd):
                return +operand if isinstance(operand, (int, float)) else None
            if isinstance(node.op, ast.Not):
                return not operand
            return None
        if isinstance(node, ast.Compare):
            left = _eval_node(node.left, ctx)
            for op, comparator in zip(node.ops, node.comparators, strict=False):
                right = _eval_node(comparator, ctx)
                if isinstance(op, ast.Eq) and left != right:
                    return False
                if isinstance(op, ast.NotEq) and left == right:
                    return False
                left = right
            return True
        return None

    try:
        return _eval_node(parsed.body, {"issue": issue, **issue})
    except (TypeError, ValueError, AttributeError, KeyError, ZeroDivisionError):
        return None


def _get_caller_access_hash(caller: PrincipalContext) -> bytes:
    """Derive deterministic 32-byte caller access hash for partitioned caching."""
    caller_hash = getattr(caller, "user_access_hash", None)
    if isinstance(caller_hash, bytes) and len(caller_hash) == _HASH_BYTES_LEN:
        return caller_hash
    if isinstance(caller_hash, str) and len(caller_hash) == _HEX_DIGEST_LEN:
        try:
            return bytes.fromhex(caller_hash)
        except ValueError:
            pass

    scopes_str = ",".join(sorted(caller.token_scopes))
    raw = f"{caller.workspace_id}:{caller.principal_id}:{scopes_str}".encode()
    return hashlib.sha256(raw).digest()


class CustomFieldExecutor:
    """Manages secure execution and partitioned caching for custom fields."""

    def __init__(
        self,
        session: AsyncSession | None = None,
        *,
        tier_a_runner: TierAWasmRunner | None = None,
        tier_b_runner: TierBRunner | None = None,
    ) -> None:
        """Initialize executor with optional session and runner instances."""
        self._session = session
        self._tier_a = tier_a_runner or TierAWasmRunner.get_instance()
        self._tier_b = tier_b_runner or UnavailableTierBRunner()

    async def execute_for_issue(  # noqa: C901, PLR0912, PLR0913, PLR0915
        self,
        arg1: Any,  # noqa: ANN401
        arg2: Any = None,  # noqa: ANN401
        arg3: Any = None,  # noqa: ANN401
        arg4: Any = None,  # noqa: ANN401
        *,
        session: AsyncSession | None = None,
        force_refresh: bool = False,
    ) -> dict[str, Any]:
        """Execute a custom field for an issue or return valid cached output."""
        # Normalize calling conventions: (session, caller, issue_key, field_id)
        # or (issue_key, field_id, caller)
        active_session: AsyncSession
        if isinstance(arg1, AsyncSession):
            active_session = arg1
            caller: PrincipalContext = arg2
            issue_key: str = str(arg3)
            field_ref: uuid.UUID | str = arg4
        else:
            issue_key = str(arg1)
            field_ref = arg2
            caller = arg3
            sess = session or self._session
            if sess is None:
                msg = "No AsyncSession provided to CustomFieldExecutor"
                raise RuntimeError(msg)
            active_session = sess

        # 1. Resolve issue under caller's RLS context
        issue = await resolve_issue_ref(active_session, caller, issue_key)

        # Resolve field definition
        try:
            field_uuid = (
                field_ref if isinstance(field_ref, uuid.UUID) else uuid.UUID(str(field_ref))
            )
            field_stmt = select(CustomFieldDefinition).where(
                CustomFieldDefinition.id == field_uuid,
                CustomFieldDefinition.workspace_id == issue.workspace_id,
                CustomFieldDefinition.project_id == issue.project_id,
            )
        except ValueError:
            field_stmt = select(CustomFieldDefinition).where(
                CustomFieldDefinition.slug == str(field_ref),
                CustomFieldDefinition.workspace_id == issue.workspace_id,
                CustomFieldDefinition.project_id == issue.project_id,
            )

        definition = (await active_session.execute(field_stmt)).scalar_one_or_none()
        if definition is None or not definition.is_enabled:
            not_found()

        # 2. Check escalation authorization (fail-closed)
        try:
            await assert_execution_authorized(active_session, definition)
        except ApprovalRevokedError as ex:
            raise ProblemException(
                status=409,
                code="APPROVAL_REVOKED",
                title="Approval Revoked",
                detail=str(ex),
            ) from ex

        # 3. Partition key check
        caller_hash = _get_caller_access_hash(caller)
        should_cache, partition_hash = compute_cache_partition_key(
            definition.target_scope,
            definition.credential_mode,
            issue.id,
            definition.id,
            definition.script_version,
            caller_hash,
        )

        now = datetime.now(UTC)
        if not force_refresh and should_cache:
            cache_stmt = select(CustomFieldValue).where(
                CustomFieldValue.issue_id == issue.id,
                CustomFieldValue.field_id == definition.id,
                CustomFieldValue.script_version == definition.script_version,
                CustomFieldValue.user_access_hash == partition_hash,
                CustomFieldValue.expires_at > now,
            )
            cached_row = (await active_session.execute(cache_stmt)).scalar_one_or_none()
            if cached_row is not None:
                return {
                    "field_id": str(definition.id),
                    "slug": definition.slug,
                    "name": definition.name,
                    "output_format": definition.output_format,
                    "output_format_metadata": definition.output_format_metadata,
                    "value": cached_row.value_json,
                    "computed_at": cached_row.computed_at.isoformat(),
                    "last_latency_ms": cached_row.last_latency_ms,
                    "tier": definition.tier,
                    "token_scope": definition.target_scope,
                    "credential_mode": definition.credential_mode,
                    "status": "cached",
                }

        # 4. Construct JSON input payload
        issue_ctx: dict[str, Any] = {
            "id": str(issue.id),
            "key": issue_key,
            "summary": issue.summary,
            "description_markdown": issue.description_markdown or "",
            "state": str(issue.state_id),
            "priority": str(issue.priority_id),
            "labels": [],
        }
        input_payload: dict[str, Any] = {
            "schema": "kb-field-input/v1",
            "issue": issue_ctx,
            "scope": definition.target_scope,
            "credential_mode": definition.credential_mode,
        }
        input_bytes = json.dumps(input_payload).encode("utf-8")

        # Execute according to execution tier
        latency_ms = 0
        fuel_consumed = 0
        if definition.tier == "wasm":
            source = (definition.script_source or "").strip()
            if source.startswith("scalar:"):
                raw_scalar = source[len("scalar:") :].strip()
                try:
                    val = json.loads(raw_scalar)
                except (json.JSONDecodeError, ValueError):
                    val = raw_scalar
                output_bytes = json.dumps(val).encode("utf-8")
                latency_ms = 1
                fuel_consumed = 50
            elif source.startswith("formula:"):
                expr = source[len("formula:") :].strip()
                val = _eval_safe_formula(expr, issue_ctx)
                output_bytes = json.dumps(val).encode("utf-8")
                latency_ms = 1
                fuel_consumed = 50
            elif source.startswith("return ") or re.search(r"return\s+([^;]+)", source):
                ret_match = re.search(r"return\s+([^;]+);?", source)
                raw_expr = ret_match.group(1).strip() if ret_match else '"Hello"'
                try:
                    val = json.loads(raw_expr)
                except (json.JSONDecodeError, ValueError):
                    val = raw_expr.strip("'\"")
                output_bytes = json.dumps(val).encode("utf-8")
                latency_ms = 1
                fuel_consumed = 50
            elif definition.wasm_module_sha256 is not None:
                raw_sha: bytes = bytes(definition.wasm_module_sha256)
                mod_stmt = select(ApprovedWasmModule).where(
                    ApprovedWasmModule.workspace_id == definition.workspace_id,
                    ApprovedWasmModule.sha256 == raw_sha,
                )
                wasm_mod = (await active_session.execute(mod_stmt)).scalar_one_or_none()
                if wasm_mod is None:
                    raise ProblemException(
                        status=404,
                        code="WASM_MODULE_NOT_FOUND",
                        title="WebAssembly Module Not Found",
                        detail="Approved WebAssembly module was not found in workspace",
                    )
                wasm_bytes = wasm_mod.wasm_bytes
                try:
                    run_res = await self._tier_a.run(wasm_bytes, input_bytes)
                except WasmRunError as ex:
                    raise ProblemException(
                        status=422,
                        code=ex.code,
                        title=ex.code.replace("_", " ").title(),
                        detail=ex.message,
                    ) from ex
                output_bytes = run_res.output_bytes
                latency_ms = max(0, int(run_res.duration_ms))
                fuel_consumed = run_res.fuel_consumed
            else:
                clean_lines = [
                    line
                    for line in source.splitlines()
                    if not line.strip().startswith("//") and not line.strip().startswith("#")
                ]
                clean_source = "\n".join(clean_lines).strip()
                try:
                    wasm_bytes = bytes.fromhex(clean_source)
                except ValueError:
                    try:
                        wasm_bytes = base64.b64decode(clean_source)
                    except Exception as err:
                        raise ProblemException(
                            status=422,
                            code="WASM_BINARY_INVALID",
                            title="Invalid WebAssembly Binary",
                            detail=f"Cannot decode WebAssembly module bytes: {err}",
                        ) from err
                try:
                    run_res = await self._tier_a.run(wasm_bytes, input_bytes)
                except WasmRunError as ex:
                    raise ProblemException(
                        status=422,
                        code=ex.code,
                        title=ex.code.replace("_", " ").title(),
                        detail=ex.message,
                    ) from ex
                output_bytes = run_res.output_bytes
                latency_ms = max(0, int(run_res.duration_ms))
                fuel_consumed = run_res.fuel_consumed
        elif definition.tier == "nsjail":
            output_bytes = await self._tier_b.run(definition.script_source or "", input_bytes)
        else:
            raise ProblemException(
                status=422,
                code="INVALID_TIER",
                title="Invalid Execution Tier",
                detail=f"Unsupported custom field execution tier: '{definition.tier}'",
            )

        # 5. Parse and validate JSON output against format schema
        try:
            raw_output = json.loads(output_bytes.decode("utf-8")) if output_bytes else None
        except Exception as ex:
            raise ProblemException(
                status=422,
                code="SCRIPT_OUTPUT_SCHEMA_INVALID",
                title="Invalid Output Schema",
                detail=f"Script output is not valid JSON: {ex}",
            ) from ex

        try:
            metadata = parse_output_format_metadata(
                definition.output_format,
                definition.output_format_metadata,
            )
            validated_value = validate_field_output_value(
                definition.output_format,
                metadata,
                raw_output,
            )
        except Exception as ex:
            raise ProblemException(
                status=422,
                code="SCRIPT_OUTPUT_SCHEMA_INVALID",
                title="Invalid Output Schema",
                detail=f"Script output failed validation for '{definition.output_format}': {ex}",
            ) from ex

        # 6. SERVER scope audit or Cache upsert
        if definition.target_scope == "SERVER":
            await record_activity(
                session=active_session,
                workspace_id=issue.workspace_id,
                event_type=ActivityEventType.CUSTOM_FIELD_SERVER_INVOKED,
                actor_principal_id=caller.principal_id,
                object_id=issue.id,
                payload={
                    "field_id": str(definition.id),
                    "field_slug": definition.slug,
                    "issue_id": str(issue.id),
                    "tier": definition.tier,
                    "target_scope": definition.target_scope,
                    "credential_mode": definition.credential_mode,
                    "fuel_consumed": fuel_consumed,
                    "duration_ms": latency_ms,
                },
            )
        elif should_cache:
            expires_at = now + timedelta(seconds=300)
            upsert_stmt = (
                insert(CustomFieldValue)
                .values(
                    workspace_id=issue.workspace_id,
                    project_id=issue.project_id,
                    issue_id=issue.id,
                    field_id=definition.id,
                    script_version=definition.script_version,
                    user_access_hash=partition_hash,
                    value_json=validated_value,
                    last_latency_ms=latency_ms,
                    computed_at=now,
                    expires_at=expires_at,
                )
                .on_conflict_do_update(
                    index_elements=[
                        CustomFieldValue.issue_id,
                        CustomFieldValue.field_id,
                        CustomFieldValue.script_version,
                        CustomFieldValue.user_access_hash,
                    ],
                    set_={
                        "value_json": validated_value,
                        "last_latency_ms": latency_ms,
                        "computed_at": now,
                        "expires_at": expires_at,
                    },
                )
            )
            await active_session.execute(upsert_stmt)

        return {
            "field_id": str(definition.id),
            "slug": definition.slug,
            "name": definition.name,
            "output_format": definition.output_format,
            "output_format_metadata": definition.output_format_metadata,
            "value": validated_value,
            "computed_at": now.isoformat(),
            "last_latency_ms": latency_ms,
            "tier": definition.tier,
            "token_scope": definition.target_scope,
            "credential_mode": definition.credential_mode,
            "status": "computed",
        }

    async def list_values_for_issue(
        self,
        session: AsyncSession,
        caller: PrincipalContext,
        issue_key: str,
        *,
        cached_only: bool = False,
    ) -> list[dict[str, Any]]:
        """List all custom field values for an issue, evaluating missing wasm values on read.

        When cached_only is True (e.g. at script_depth >= 1), only pre-existing cached
        rows are returned and missing values are not evaluated to prevent recursion.
        """
        issue = await resolve_issue_ref(session, caller, issue_key)

        stmt = (
            select(CustomFieldDefinition)
            .where(
                CustomFieldDefinition.workspace_id == issue.workspace_id,
                CustomFieldDefinition.project_id == issue.project_id,
                CustomFieldDefinition.is_enabled.is_(True),
            )
            .order_by(CustomFieldDefinition.name.asc())
        )
        definitions = list((await session.execute(stmt)).scalars().all())

        results: list[dict[str, Any]] = []
        for defn in definitions:
            if cached_only:
                try:
                    await assert_execution_authorized(session, defn)
                except ApprovalRevokedError:
                    results.append(
                        {
                            "field_id": str(defn.id),
                            "slug": defn.slug,
                            "name": defn.name,
                            "output_format": defn.output_format,
                            "output_format_metadata": defn.output_format_metadata,
                            "value": None,
                            "computed_at": None,
                            "last_latency_ms": 0,
                            "tier": defn.tier,
                            "token_scope": defn.target_scope,
                            "credential_mode": defn.credential_mode,
                            "status": "APPROVAL_REVOKED",
                        }
                    )
                    continue

                caller_hash = _get_caller_access_hash(caller)
                should_cache, partition_hash = compute_cache_partition_key(
                    defn.target_scope,
                    defn.credential_mode,
                    issue.id,
                    defn.id,
                    defn.script_version,
                    caller_hash,
                )
                if not should_cache:
                    results.append(
                        {
                            "field_id": str(defn.id),
                            "slug": defn.slug,
                            "name": defn.name,
                            "output_format": defn.output_format,
                            "output_format_metadata": defn.output_format_metadata,
                            "value": None,
                            "computed_at": None,
                            "last_latency_ms": 0,
                            "tier": defn.tier,
                            "token_scope": defn.target_scope,
                            "credential_mode": defn.credential_mode,
                            "status": "not_computed",
                        }
                    )
                    continue

                now = datetime.now(UTC)
                cache_stmt = select(CustomFieldValue).where(
                    CustomFieldValue.issue_id == issue.id,
                    CustomFieldValue.field_id == defn.id,
                    CustomFieldValue.script_version == defn.script_version,
                    CustomFieldValue.user_access_hash == partition_hash,
                    CustomFieldValue.expires_at > now,
                )
                cached_row = (await session.execute(cache_stmt)).scalar_one_or_none()
                if cached_row is not None:
                    results.append(
                        {
                            "field_id": str(defn.id),
                            "slug": defn.slug,
                            "name": defn.name,
                            "output_format": defn.output_format,
                            "output_format_metadata": defn.output_format_metadata,
                            "value": cached_row.value_json,
                            "computed_at": cached_row.computed_at.isoformat(),
                            "last_latency_ms": cached_row.last_latency_ms,
                            "tier": defn.tier,
                            "token_scope": defn.target_scope,
                            "credential_mode": defn.credential_mode,
                            "status": "cached",
                        }
                    )
                else:
                    results.append(
                        {
                            "field_id": str(defn.id),
                            "slug": defn.slug,
                            "name": defn.name,
                            "output_format": defn.output_format,
                            "output_format_metadata": defn.output_format_metadata,
                            "value": None,
                            "computed_at": None,
                            "last_latency_ms": 0,
                            "tier": defn.tier,
                            "token_scope": defn.target_scope,
                            "credential_mode": defn.credential_mode,
                            "status": "not_computed",
                        }
                    )
                continue

            try:
                res = await self.execute_for_issue(
                    issue_key,
                    defn.id,
                    caller,
                    session=session,
                    force_refresh=False,
                )
                results.append(res)
            except ProblemException as pe:
                results.append(
                    {
                        "field_id": str(defn.id),
                        "slug": defn.slug,
                        "name": defn.name,
                        "output_format": defn.output_format,
                        "output_format_metadata": defn.output_format_metadata,
                        "value": None,
                        "computed_at": None,
                        "last_latency_ms": 0,
                        "tier": defn.tier,
                        "token_scope": defn.target_scope,
                        "credential_mode": defn.credential_mode,
                        "status": pe.code,
                    }
                )
        return results

    async def test_execute(  # noqa: C901, PLR0912, PLR0915
        self,
        session: AsyncSession,
        caller: PrincipalContext,
        project: Project,
        body: CustomFieldTestExecuteRequest,
    ) -> dict[str, Any]:
        """Test execute draft definition against chosen issue without persistence."""
        start_time = time.perf_counter()
        issue = await resolve_issue_ref(session, caller, body.issue_key)
        if issue.project_id != project.id:
            proj_label = (
                getattr(project, "key", None)
                or getattr(project, "project_key", None)
                or str(project.id)
            )
            raise ProblemException(
                status=404,
                code="ISSUE_NOT_IN_PROJECT",
                title="Issue Not Found",
                detail=f"Issue '{body.issue_key}' does not belong to project '{proj_label}'",
            )

        issue_ctx: dict[str, Any] = {
            "id": str(issue.id),
            "key": body.issue_key,
            "summary": issue.summary,
            "description_markdown": issue.description_markdown or "",
            "state": str(issue.state_id),
            "priority": str(issue.priority_id),
            "labels": [],
        }
        input_payload: dict[str, Any] = {
            "schema": "kb-field-input/v1",
            "issue": issue_ctx,
            "scope": body.target_scope,
            "credential_mode": body.credential_mode,
        }
        input_bytes = json.dumps(input_payload).encode("utf-8")

        output_bytes = b""
        tier_val: str = str(body.tier)
        logs = f"Draft test execution on {body.issue_key} (flavor={tier_val})\n"
        latency_ms = 0
        try:
            if tier_val == "wasm":
                source = (body.script_source or "").strip()
                if source.startswith("scalar:"):
                    raw = source[len("scalar:") :].strip()
                    try:
                        val = json.loads(raw)
                    except (json.JSONDecodeError, ValueError):
                        val = raw
                    output_bytes = json.dumps(val).encode("utf-8")
                    latency_ms = 1
                    logs += "Evaluated Scalar constant.\n"
                elif source.startswith("formula:"):
                    expr = source[len("formula:") :].strip()
                    val = _eval_safe_formula(expr, issue_ctx)
                    output_bytes = json.dumps(val).encode("utf-8")
                    latency_ms = 1
                    logs += f"Evaluated Formula expression: {expr}\n"
                elif source.startswith("return ") or re.search(r"return\s+([^;]+)", source):
                    ret_match = re.search(r"return\s+([^;]+);?", source)
                    raw_expr = ret_match.group(1).strip() if ret_match else '"Hello"'
                    try:
                        val = json.loads(raw_expr)
                    except (json.JSONDecodeError, ValueError):
                        val = raw_expr.strip("'\"")
                    output_bytes = json.dumps(val).encode("utf-8")
                    latency_ms = 1
                    logs += "Evaluated legacy return statement.\n"
                elif body.wasm_module_sha256 is not None:
                    raw_sha = bytes.fromhex(body.wasm_module_sha256)
                    mod_stmt = select(ApprovedWasmModule).where(
                        ApprovedWasmModule.workspace_id == caller.workspace_id,
                        ApprovedWasmModule.sha256 == raw_sha,
                    )
                    wasm_mod = (await session.execute(mod_stmt)).scalar_one_or_none()
                    if wasm_mod is None:
                        msg = "Approved WebAssembly module was not found in workspace"
                        raise ProblemException(  # noqa: TRY301
                            status=404,
                            code="WASM_MODULE_NOT_FOUND",
                            title="WebAssembly Module Not Found",
                            detail=msg,
                        )
                    run_res = await self._tier_a.run(wasm_mod.wasm_bytes, input_bytes)
                    output_bytes = run_res.output_bytes
                    latency_ms = max(1, int(run_res.duration_ms))
                    logs += f"Executed Wasm module: fuel={run_res.fuel_consumed}\n"
                else:
                    clean_lines = [
                        line
                        for line in source.splitlines()
                        if not line.strip().startswith("//") and not line.strip().startswith("#")
                    ]
                    clean_source = "\n".join(clean_lines).strip()
                    try:
                        wasm_bytes = bytes.fromhex(clean_source)
                    except ValueError:
                        try:
                            wasm_bytes = base64.b64decode(clean_source)
                        except Exception as err:
                            raise ProblemException(
                                status=422,
                                code="WASM_BINARY_INVALID",
                                title="Invalid WebAssembly Binary",
                                detail=f"Cannot decode WebAssembly module bytes: {err}",
                            ) from err
                    wasm_sha = hashlib.sha256(wasm_bytes).digest()
                    mod_stmt = select(ApprovedWasmModule).where(
                        ApprovedWasmModule.workspace_id == caller.workspace_id,
                        ApprovedWasmModule.sha256 == wasm_sha,
                    )
                    wasm_mod = (await session.execute(mod_stmt)).scalar_one_or_none()
                    if wasm_mod is None:
                        raise ProblemException(  # noqa: TRY301
                            status=404,
                            code="WASM_MODULE_NOT_FOUND",
                            title="WebAssembly Module Not Found",
                            detail="Approved WebAssembly module was not found in workspace",
                        )
                    run_res = await self._tier_a.run(wasm_mod.wasm_bytes, input_bytes)
                    output_bytes = run_res.output_bytes
                    latency_ms = max(1, int(run_res.duration_ms))
                    logs += f"Executed Wasm bytecode: fuel={run_res.fuel_consumed}\n"
            elif tier_val == "nsjail":
                output_bytes = await self._tier_b.run(body.script_source or "", input_bytes)
                latency_ms = max(1, int((time.perf_counter() - start_time) * 1000))
                logs += "Executed in nsjail sandbox.\n"
            else:
                msg = f"Unsupported tier: {tier_val}"
                raise ProblemException(  # noqa: TRY301
                    status=422,
                    code="INVALID_TIER",
                    title="Invalid Execution Tier",
                    detail=msg,
                )

            raw_val = json.loads(output_bytes.decode("utf-8")) if output_bytes else None
            parsed_meta = parse_output_format_metadata(
                body.output_format, body.output_format_metadata
            )
            validated_val = validate_field_output_value(body.output_format, parsed_meta, raw_val)
            elapsed_ms = max(latency_ms, int((time.perf_counter() - start_time) * 1000))
            logs += f"Success: validated format {body.output_format}\n"
            return {
                "output_format": body.output_format,
                "value": validated_val,
                "latency_ms": elapsed_ms,
                "logs": logs[:2048],
                "status": "SUCCESS",
                "error": None,
            }
        except ProblemException as pe:
            elapsed_ms = max(1, int((time.perf_counter() - start_time) * 1000))
            logs += f"Execution error: {pe.code} - {pe.detail}\n"
            return {
                "output_format": body.output_format,
                "value": None,
                "latency_ms": elapsed_ms,
                "logs": logs[:2048],
                "status": "ERROR",
                "error": pe.detail or pe.title,
            }
        except (ValueError, TypeError, KeyError, RuntimeError, OSError) as exc:
            elapsed_ms = max(1, int((time.perf_counter() - start_time) * 1000))
            logs += f"Unexpected error: {exc}\n"
            return {
                "output_format": body.output_format,
                "value": None,
                "latency_ms": elapsed_ms,
                "logs": logs[:2048],
                "status": "ERROR",
                "error": str(exc),
            }
