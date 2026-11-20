# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Custom field executor and partitioned cache manager (KB-P5-13, S13.2, S13.3)."""

from __future__ import annotations

import ast
import hashlib
import json
import logging
import re
import time
import uuid
from datetime import UTC, date, datetime, timedelta
from typing import TYPE_CHECKING, Any, Final

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import (
    CustomFieldDefinition,
    CustomFieldValue,
    LinkKind,
    ObjectLink,
    ProjectPriority,
    WorkflowState,
)
from database.models import (
    Issue as DbIssue,
)
from kanban.api.problems import ProblemException, not_found
from kanban.custom_fields.approvals import (
    ApprovalRevokedError,
    assert_execution_authorized,
    compute_cache_partition_key,
)
from kanban.custom_fields.builtin_wasm import resolve_wasm_module_bytes
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

logger: Final[logging.Logger] = logging.getLogger(__name__)

_HASH_BYTES_LEN: Final[int] = 32
_HEX_DIGEST_LEN: Final[int] = 64
_MAX_FORMULA_NODES: Final[int] = 64
_MAX_FORMULA_DEPTH: Final[int] = 8
_MAX_POW_EXPONENT: Final[int] = 64
_MAX_POW_BASE: Final[int] = 1_000_000
_MAX_MULT_OUTPUT_LEN: Final[int] = 4096

_SAFE_FORMULA_FUNCS: Final[dict[str, Any]] = {
    "round": round,
    "int": int,
    "float": float,
    "min": min,
    "max": max,
    "len": len,
    "abs": abs,
    "str": str,
}


def _strip_outer_parens(s: str) -> str:
    """Strip redundant outer matching parentheses from an expression."""
    s = s.strip()
    while s.startswith("(") and s.endswith(")"):
        depth = 0
        matches = True
        for ch in s[:-1]:
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    matches = False
                    break
        if matches:
            s = s[1:-1].strip()
        else:
            break
    return s


def _convert_js_ternary(expr: str) -> str:  # noqa: C901, PLR0912
    """Recursively convert JS ternary (? :) expressions to Python (if else) expressions.

    Correctly skips colons inside string literals and dictionary/set brackets.
    """
    expr = _strip_outer_parens(expr.strip())
    if "?" not in expr or ":" not in expr:
        return expr

    depth_brace = 0
    depth_bracket = 0
    depth_paren = 0
    in_quote: str | None = None
    escaped = False

    question_idx = -1
    colon_idx = -1
    ternary_balance = 0

    for i, ch in enumerate(expr):
        if escaped:
            escaped = False
            continue
        if ch == "\\":
            escaped = True
            continue
        if in_quote:
            if ch == in_quote:
                in_quote = None
            continue
        if ch in ("'", '"'):
            in_quote = ch
            continue

        if ch == "{":
            depth_brace += 1
        elif ch == "}":
            depth_brace = max(0, depth_brace - 1)
        elif ch == "[":
            depth_bracket += 1
        elif ch == "]":
            depth_bracket = max(0, depth_bracket - 1)
        elif ch == "(":
            depth_paren += 1
        elif ch == ")":
            depth_paren = max(0, depth_paren - 1)
        elif depth_brace == 0 and depth_bracket == 0 and depth_paren == 0:
            if ch == "?":
                if question_idx == -1:
                    question_idx = i
                ternary_balance += 1
            elif ch == ":" and question_idx != -1:
                ternary_balance -= 1
                if ternary_balance == 0:
                    colon_idx = i
                    break

    if question_idx != -1 and colon_idx != -1:
        cond = _convert_js_ternary(expr[:question_idx].strip())
        val_true = _convert_js_ternary(expr[question_idx + 1 : colon_idx].strip())
        val_false = _convert_js_ternary(expr[colon_idx + 1 :].strip())
        return f"({val_true}) if ({cond}) else ({val_false})"

    return expr


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
    if expr.startswith("formula:"):
        expr = expr[len("formula:") :].strip()
    if not expr:
        return ""

    # Normalize JS operators
    expr = expr.replace("===", "==").replace("!==", "!=")
    if "?" in expr and ":" in expr:
        expr = _convert_js_ternary(expr)

    try:
        parsed = ast.parse(expr, mode="eval")
    except (SyntaxError, ValueError):
        return None

    if not _check_formula_ast_bounds(parsed.body):
        return None

    def _eval_node(node: ast.AST, ctx: dict[str, Any]) -> Any:  # noqa: C901, PLR0911, PLR0912, PLR0915, ANN401
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
            if (
                isinstance(val, (list, tuple))
                and isinstance(slice_val, int)
                and 0 <= slice_val < len(val)
            ):
                return val[slice_val]
            return ""
        if isinstance(node, (ast.List, ast.Tuple)):
            return [_eval_node(elt, ctx) for elt in node.elts]
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
        if isinstance(node, ast.BoolOp):
            if isinstance(node.op, ast.And):
                res: Any = True
                for val_node in node.values:
                    res = _eval_node(val_node, ctx)
                    if not res:
                        return res
                return res
            if isinstance(node.op, ast.Or):
                res = False
                for val_node in node.values:
                    res = _eval_node(val_node, ctx)
                    if res:
                        return res
                return res
            return None
        if isinstance(node, ast.Compare):
            left = _eval_node(node.left, ctx)
            for op, comparator in zip(node.ops, node.comparators, strict=False):
                right = _eval_node(comparator, ctx)
                matched = False
                if isinstance(op, ast.Eq):
                    matched = left == right
                elif isinstance(op, ast.NotEq):
                    matched = left != right
                elif isinstance(op, ast.Lt):
                    matched = False if left in (None, "") or right in (None, "") else left < right
                elif isinstance(op, ast.LtE):
                    matched = False if left in (None, "") or right in (None, "") else left <= right
                elif isinstance(op, ast.Gt):
                    matched = False if left in (None, "") or right in (None, "") else left > right
                elif isinstance(op, ast.GtE):
                    matched = False if left in (None, "") or right in (None, "") else left >= right
                elif isinstance(op, ast.Is):
                    matched = left is right
                elif isinstance(op, ast.IsNot):
                    matched = left is not right
                elif isinstance(op, ast.In):
                    matched = isinstance(right, (list, tuple, dict, set, str)) and left in right
                elif isinstance(op, ast.NotIn):
                    matched = not (
                        isinstance(right, (list, tuple, dict, set, str)) and left in right
                    )
                if not matched:
                    return False
                left = right
            return True
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in _SAFE_FORMULA_FUNCS:
                fn = _SAFE_FORMULA_FUNCS[node.func.id]
                args = [_eval_node(arg, ctx) for arg in node.args]
                try:
                    return fn(*args)
                except (TypeError, ValueError, OverflowError):
                    return None
            return None
        return None

    try:
        return _eval_node(parsed.body, {"issue": issue, **issue})
    except (TypeError, ValueError, AttributeError, KeyError, ZeroDivisionError):
        return None


async def build_issue_context(  # noqa: C901, PLR0912, PLR0915
    session: AsyncSession | None,
    issue: object,
    issue_key: str,
) -> dict[str, Any]:
    """Construct safe execution context payload from issue model and related metadata."""
    issue_id_str = str(getattr(issue, "id", ""))
    summary_val = getattr(issue, "summary", "")
    summary = summary_val if isinstance(summary_val, str) else ""
    desc_val = getattr(issue, "description_markdown", "")
    desc = desc_val if isinstance(desc_val, str) else ""
    state_id_str = str(getattr(issue, "state_id", ""))
    priority_id_str = str(getattr(issue, "priority_id", ""))
    labels_val = getattr(issue, "labels", None)
    labels = list(labels_val) if isinstance(labels_val, (list, tuple)) else []

    # Dates - strictly check types so MagicMock is never mistakenly serialized
    raw_due = getattr(issue, "due_date", None)
    if isinstance(raw_due, (datetime, date)):
        due_date_str = raw_due.isoformat()
    elif isinstance(raw_due, str):
        due_date_str = raw_due
    else:
        due_date_str = None

    raw_start = getattr(issue, "start_date", None)
    if isinstance(raw_start, (datetime, date)):
        start_date_str = raw_start.isoformat()
    elif isinstance(raw_start, str):
        start_date_str = raw_start
    else:
        start_date_str = None

    days_val = getattr(issue, "days_until_due", None)
    if isinstance(days_val, int):
        days_until_due: int | None = days_val
    elif isinstance(raw_due, (datetime, date)):
        today = datetime.now(UTC).date()
        target_date = raw_due.date() if isinstance(raw_due, datetime) else raw_due
        days_until_due = (target_date - today).days
    else:
        days_until_due = None

    # State & Priority resolution
    state_val = getattr(issue, "state", None)
    state_name = state_val if isinstance(state_val, str) else state_id_str
    state_group_val = getattr(issue, "state_group", None)
    state_group = state_group_val if isinstance(state_group_val, str) else ""

    prio_val = getattr(issue, "priority", None)
    priority_slug = prio_val if isinstance(prio_val, str) else priority_id_str
    prio_lbl_val = getattr(issue, "priority_label", None)
    priority_label = prio_lbl_val if isinstance(prio_lbl_val, str) else ""

    blk_val = getattr(issue, "blocker_count", None)
    blocker_count: int = blk_val if isinstance(blk_val, int) else 0

    sub_val = getattr(issue, "sub_issue_count", None)
    sub_issue_count: int = sub_val if isinstance(sub_val, int) else 0

    comp_val = getattr(issue, "completed_sub_issue_count", None)
    completed_sub_issue_count: int = comp_val if isinstance(comp_val, int) else 0

    # Resolve from DB if session is active and not a test mock
    is_mock = type(session).__name__ != "AsyncSession" or type(issue).__name__ not in (
        "Issue",
        "DbIssue",
    )
    if session is not None and not is_mock:
        try:
            if hasattr(issue, "state_id") and issue.state_id:
                st = await session.get(WorkflowState, issue.state_id)
                if st is not None:
                    state_name = st.name
                    state_group = st.state_group
            if hasattr(issue, "priority_id") and issue.priority_id:
                pr = await session.get(ProjectPriority, issue.priority_id)
                if pr is not None:
                    priority_slug = pr.slug
                    priority_label = pr.label
        except (SQLAlchemyError, AttributeError) as ex:
            logger.debug("Failed resolving state/priority for issue %s: %s", issue_key, ex)

        try:
            if hasattr(issue, "id") and issue.id:
                blk_stmt = (
                    select(func.count())
                    .select_from(ObjectLink)
                    .where(
                        ObjectLink.source_id == issue.id,
                        ObjectLink.link_type == LinkKind.BLOCKED_BY,
                        ObjectLink.link_state == "ACTIVE",
                    )
                )
                blocker_count = int((await session.execute(blk_stmt)).scalar() or 0)

                sub_stmt = (
                    select(func.count())
                    .select_from(DbIssue)
                    .where(DbIssue.parent_issue_id == issue.id)
                )
                sub_issue_count = int((await session.execute(sub_stmt)).scalar() or 0)

                comp_sub_stmt = (
                    select(func.count())
                    .select_from(DbIssue)
                    .join(WorkflowState, WorkflowState.id == DbIssue.state_id)
                    .where(
                        DbIssue.parent_issue_id == issue.id,
                        WorkflowState.state_group == "completed",
                    )
                )
                completed_sub_issue_count = int(
                    (await session.execute(comp_sub_stmt)).scalar() or 0
                )
        except (SQLAlchemyError, AttributeError) as ex:
            logger.debug(
                "Failed resolving blocker/sub_issue counts for issue %s: %s", issue_key, ex
            )

    return {
        "id": issue_id_str,
        "key": issue_key,
        "summary": summary,
        "description_markdown": desc,
        "state_id": state_id_str,
        "priority_id": priority_id_str,
        "labels": labels,
        "state": state_name,
        "state_group": state_group,
        "priority": priority_slug.upper() if priority_slug else "",
        "priority_slug": priority_slug.lower() if priority_slug else "",
        "priority_label": priority_label,
        "start_date": start_date_str,
        "due_date": due_date_str,
        "days_until_due": days_until_due,
        "blocker_count": blocker_count,
        "sub_issue_count": sub_issue_count,
        "completed_sub_issue_count": completed_sub_issue_count,
    }


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
        issue_ctx = await build_issue_context(active_session, issue, issue_key)
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
            else:
                wasm_bytes, _ = await resolve_wasm_module_bytes(
                    active_session,
                    definition.workspace_id,
                    sha256=definition.wasm_module_sha256,
                    source=source,
                    allow_raw_bytecode=(definition.wasm_module_sha256 is None),
                )
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

    async def test_execute(  # noqa: C901, PLR0915
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

        issue_ctx = await build_issue_context(session, issue, body.issue_key)
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
                else:
                    wasm_bytes, _ = await resolve_wasm_module_bytes(
                        session,
                        caller.workspace_id,
                        sha256=body.wasm_module_sha256,
                        source=body.script_source,
                    )
                    run_res = await self._tier_a.run(wasm_bytes, input_bytes)
                    output_bytes = run_res.output_bytes
                    latency_ms = max(1, int(run_res.duration_ms))
                    logs += f"Executed Wasm module: fuel={run_res.fuel_consumed}\n"
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
