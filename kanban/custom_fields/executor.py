# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Custom field executor and partitioned cache manager (KB-P5-13, S13.2, S13.3)."""

from __future__ import annotations

import base64
import hashlib
import json
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
    from kanban.api.deps import PrincipalContext

_HASH_BYTES_LEN: Final[int] = 32
_HEX_DIGEST_LEN: Final[int] = 64


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
        input_payload = {
            "schema": "kb-field-input/v1",
            "issue": {
                "id": str(issue.id),
                "key": issue_key,
                "summary": issue.summary,
                "description_markdown": issue.description_markdown or "",
                "state": str(issue.state_id),
                "priority": str(issue.priority_id),
                "labels": [],
            },
            "scope": definition.target_scope,
            "credential_mode": definition.credential_mode,
        }
        input_bytes = json.dumps(input_payload).encode("utf-8")

        # Execute according to execution tier
        latency_ms = 0
        fuel_consumed = 0
        if definition.tier == "wasm":
            # Load wasm binary
            if definition.wasm_module_sha256 is not None:
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
            else:
                try:
                    wasm_bytes = bytes.fromhex(definition.script_source or "")
                except ValueError:
                    try:
                        wasm_bytes = base64.b64decode(definition.script_source or "")
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
