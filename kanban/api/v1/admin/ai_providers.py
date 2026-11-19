# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""REST API router for AI Provider and Budget administration (KB-P5-05b, S10.2, S11.4)."""

from __future__ import annotations

import logging
import os
import uuid  # noqa: TC003
from typing import Annotated, Literal, cast

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from database.models.ai import AIProviderConfig
from database.models.workspace_settings import WorkspaceSettings
from kanban.ai_config.service import (
    AIConfigValidationError,
    AIProviderConfigService,
    AirGapViolation,
)
from kanban.api.deps import PrincipalContext, get_rls_session
from kanban.api.problems import ProblemException, not_found
from kanban.api.timing import timing_floor
from kanban.api.v1.admin.ai_schemas import (
    BudgetRecord,
    BudgetSetRequest,
    ProviderConfigCreate,
    ProviderConfigPublic,
    ProviderConfigUpdate,
)
from kanban.auth.mfa.policy import require_admin_aal2
from kanban.services.activity import ActivityEventType, record_activity

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/admin/ai",
    tags=["admin-ai"],
    dependencies=[Depends(require_admin_aal2)],
)

Caller = Annotated[PrincipalContext, Depends(require_admin_aal2)]
Session = Annotated[AsyncSession, Depends(get_rls_session)]


def _to_public_config(config: AIProviderConfig) -> ProviderConfigPublic:
    """Project AIProviderConfig ORM model into public representation omitting secret material."""
    has_key = bool(config.dek_kid is not None or config.__dict__.get("wrapped_api_key") is not None)
    return ProviderConfigPublic(
        id=config.id,
        provider_kind=config.provider_kind,
        display_name=config.display_name,
        base_url=config.base_url,
        model_allowlist=list(config.model_allowlist),
        residency_tier=config.residency_tier,
        priority=config.priority,
        settings=dict(config.settings_json or {}),
        api_key_set=has_key,
        is_enabled=config.is_enabled,
        project_id=config.project_id,
    )


async def _is_air_gap_active(session: AsyncSession, workspace_id: uuid.UUID) -> bool:
    """Evaluate whether air-gap mode is active via environment or workspace settings."""
    env_val = os.environ.get("KANBAN_AIR_GAP_MODE") or os.environ.get("KB_AIR_GAP_MODE", "")
    if env_val.strip().lower() in ("true", "1", "yes"):
        return True
    stmt = select(WorkspaceSettings.air_gap_mode).where(
        WorkspaceSettings.workspace_id == workspace_id
    )
    res = await session.execute(stmt)
    val = res.scalar_one_or_none()
    return bool(val) if val is not None else False


async def _assert_admin_for_scope(
    session: AsyncSession,
    caller: PrincipalContext,
    project_id: uuid.UUID | None,
) -> None:
    """Verify caller possesses administrative authority over target workspace or project.

    Raises:
        ProblemException(404): when project is non-existent or unreadable to caller.
        ProblemException(403): when caller can view/read target but lacks admin rights.

    """
    if project_id is not None:
        view_stmt = text("SELECT app_has_object_capability(:proj_id, 1)")
        can_view = bool(
            (await session.execute(view_stmt, {"proj_id": project_id})).scalar_one_or_none()
        )
        if not can_view:
            not_found()

        admin_stmt = text(
            "SELECT app_has_object_capability(:proj_id, 64) "
            "OR app_has_object_capability(:ws_id, 64) "
            "OR app_principal_has_role(:proj_id, "
            "ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN', 'PROJECT_ADMIN'])"
        )
        is_admin = bool(
            (
                await session.execute(
                    admin_stmt, {"proj_id": project_id, "ws_id": caller.workspace_id}
                )
            ).scalar_one_or_none()
        )
        if not is_admin:
            raise ProblemException(
                code="FORBIDDEN",
                status=403,
                title="Forbidden",
                detail="Operation requires admin capability on target project.",
            )
    else:
        admin_stmt = text(
            "SELECT app_has_object_capability(:ws_id, 64) "
            "OR app_principal_has_role(NULL, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN'])"
        )
        is_admin = bool(
            (await session.execute(admin_stmt, {"ws_id": caller.workspace_id})).scalar_one_or_none()
        )
        if not is_admin:
            raise ProblemException(
                code="FORBIDDEN",
                status=403,
                title="Forbidden",
                detail="Operation requires WORKSPACE_ADMIN or SERVER_ADMIN role.",
            )


@router.get(
    "/providers",
    response_model=list[ProviderConfigPublic],
    summary="List AI provider configurations",
)
async def list_providers(
    caller: Caller,
    session: Session,
    project_id: Annotated[uuid.UUID | None, Query()] = None,
) -> list[ProviderConfigPublic]:
    """List AI provider configurations for workspace or project with API keys omitted."""
    async with timing_floor(floor_ms=25.0):
        await _assert_admin_for_scope(session, caller, project_id)
        service = AIProviderConfigService(session)
        configs = await service.list_configs(
            workspace_id=caller.workspace_id,
            project_id=project_id,
        )
        return [_to_public_config(c) for c in configs]


@router.get(
    "/providers/{provider_id}",
    response_model=ProviderConfigPublic,
    summary="Get AI provider configuration by ID",
)
async def get_provider(
    provider_id: uuid.UUID,
    caller: Caller,
    session: Session,
) -> ProviderConfigPublic:
    """Retrieve public metadata and status for a specific AI provider configuration by UUID."""
    async with timing_floor(floor_ms=25.0):
        stmt = select(AIProviderConfig).where(AIProviderConfig.id == provider_id)
        res = await session.execute(stmt)
        config = res.scalar_one_or_none()
        if config is None:
            not_found()
        await _assert_admin_for_scope(session, caller, config.project_id)
        return _to_public_config(config)


@router.post(
    "/providers",
    response_model=ProviderConfigPublic,
    status_code=status.HTTP_201_CREATED,
    summary="Create AI provider configuration",
)
async def create_provider(
    body: ProviderConfigCreate,
    caller: Caller,
    session: Session,
    response: Response,
) -> ProviderConfigPublic:
    """Create an AI provider configuration enforcing residency tier, air gap, and custody."""
    async with timing_floor(floor_ms=25.0):
        await _assert_admin_for_scope(session, caller, body.project_id)

        service = AIProviderConfigService(session)
        is_air_gap = await _is_air_gap_active(session, caller.workspace_id)
        api_key_str = body.api_key.get_secret_value() if body.api_key is not None else None

        try:
            config = await service.create_config(
                workspace_id=caller.workspace_id,
                provider_kind=body.provider_kind,
                display_name=body.display_name,
                model_allowlist=body.model_allowlist,
                residency_tier=body.residency_tier,
                base_url=body.base_url,
                priority=body.priority,
                settings_json=body.settings,
                project_id=body.project_id,
                api_key=api_key_str,
                is_enabled=body.is_enabled,
                air_gap_mode=is_air_gap,
            )
        except AirGapViolation as exc:
            raise ProblemException(
                code="AIR_GAP_EGRESS_DENIED",
                status=409,
                title="Air Gap Egress Denied",
                detail=str(exc),
            ) from exc
        except AIConfigValidationError as exc:
            code = "INVALID_BASE_URL" if "base_url" in str(exc) else "INVALID_REQUEST"
            raise ProblemException(
                code=code,
                status=422,
                title="Validation Error",
                detail=str(exc),
            ) from exc

        await record_activity(
            session=session,
            workspace_id=caller.workspace_id,
            actor_principal_id=caller.principal_id,
            event_type=ActivityEventType.AI_PROVIDER_CONFIG_CREATED,
            payload={
                "config_id": str(config.id),
                "provider_kind": config.provider_kind,
                "display_name": config.display_name,
                "is_enabled": config.is_enabled,
                "project_id": str(config.project_id) if config.project_id else None,
            },
        )

        response.headers["Location"] = f"/api/v1/admin/ai/providers/{config.id}"
        return _to_public_config(config)


@router.patch(
    "/providers/{provider_id}",
    response_model=ProviderConfigPublic,
    summary="Update AI provider configuration",
)
async def update_provider(
    provider_id: uuid.UUID,
    body: ProviderConfigUpdate,
    caller: Caller,
    session: Session,
) -> ProviderConfigPublic:
    """Update settings, model allowlist, URL, priority, or credentials on an AI provider."""
    async with timing_floor(floor_ms=25.0):
        stmt = select(AIProviderConfig).where(AIProviderConfig.id == provider_id)
        res = await session.execute(stmt)
        config = res.scalar_one_or_none()
        if config is None:
            not_found()

        await _assert_admin_for_scope(session, caller, config.project_id)

        clear_key = False
        new_key: str | None = None
        if "api_key" in body.model_fields_set:
            if body.api_key is None:
                clear_key = True
            else:
                new_key = body.api_key.get_secret_value()

        service = AIProviderConfigService(session)
        is_air_gap = await _is_air_gap_active(session, caller.workspace_id)

        try:
            updated = await service.update_config(
                config_id=provider_id,
                display_name=body.display_name,
                model_allowlist=body.model_allowlist,
                residency_tier=body.residency_tier,
                base_url=body.base_url,
                priority=body.priority,
                settings_json=body.settings,
                is_enabled=body.is_enabled,
                api_key=new_key,
                clear_api_key=clear_key,
                air_gap_mode=is_air_gap,
            )
        except AirGapViolation as exc:
            raise ProblemException(
                code="AIR_GAP_EGRESS_DENIED",
                status=409,
                title="Air Gap Egress Denied",
                detail=str(exc),
            ) from exc
        except AIConfigValidationError as exc:
            code = "INVALID_BASE_URL" if "base_url" in str(exc) else "INVALID_REQUEST"
            raise ProblemException(
                code=code,
                status=422,
                title="Validation Error",
                detail=str(exc),
            ) from exc

        await record_activity(
            session=session,
            workspace_id=caller.workspace_id,
            actor_principal_id=caller.principal_id,
            event_type=ActivityEventType.AI_PROVIDER_CONFIG_UPDATED,
            payload={
                "config_id": str(updated.id),
                "display_name": updated.display_name,
                "is_enabled": updated.is_enabled,
                "api_key_cleared": clear_key,
                "api_key_updated": bool(new_key is not None),
            },
        )
        return _to_public_config(updated)


@router.post(
    "/providers/{provider_id}:disable",
    response_model=ProviderConfigPublic,
    summary="Disable AI provider configuration",
)
async def disable_provider(
    provider_id: uuid.UUID,
    caller: Caller,
    session: Session,
) -> ProviderConfigPublic:
    """Disable an active AI provider configuration, preventing subsequent completions."""
    async with timing_floor(floor_ms=25.0):
        stmt = select(AIProviderConfig).where(AIProviderConfig.id == provider_id)
        res = await session.execute(stmt)
        config = res.scalar_one_or_none()
        if config is None:
            not_found()

        await _assert_admin_for_scope(session, caller, config.project_id)

        service = AIProviderConfigService(session)
        disabled = await service.disable_config(provider_id)

        await record_activity(
            session=session,
            workspace_id=caller.workspace_id,
            actor_principal_id=caller.principal_id,
            event_type=ActivityEventType.AI_PROVIDER_CONFIG_DISABLED,
            payload={
                "config_id": str(disabled.id),
                "provider_kind": disabled.provider_kind,
                "display_name": disabled.display_name,
            },
        )
        return _to_public_config(disabled)


@router.delete(
    "/providers/{provider_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete AI provider configuration",
)
async def delete_provider(
    provider_id: uuid.UUID,
    caller: Caller,
    session: Session,
) -> Response:
    """Delete an AI provider configuration."""
    async with timing_floor(floor_ms=25.0):
        stmt = select(AIProviderConfig).where(AIProviderConfig.id == provider_id)
        res = await session.execute(stmt)
        config = res.scalar_one_or_none()
        if config is None:
            not_found()

        await _assert_admin_for_scope(session, caller, config.project_id)

        service = AIProviderConfigService(session)
        await service.delete_config(provider_id)

        await record_activity(
            session=session,
            workspace_id=caller.workspace_id,
            actor_principal_id=caller.principal_id,
            event_type=ActivityEventType.AI_PROVIDER_CONFIG_DISABLED,
            payload={
                "config_id": str(provider_id),
                "provider_kind": config.provider_kind,
                "display_name": config.display_name,
                "action": "deleted",
            },
        )
        return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/budgets",
    response_model=list[BudgetRecord],
    summary="Get budget records for provider configuration",
)
async def get_budgets(
    provider_config_id: uuid.UUID,
    caller: Caller,
    session: Session,
) -> list[BudgetRecord]:
    """List token consumption ledger records and caps for a provider configuration."""
    async with timing_floor(floor_ms=25.0):
        stmt = select(AIProviderConfig).where(AIProviderConfig.id == provider_config_id)
        res = await session.execute(stmt)
        config = res.scalar_one_or_none()
        if config is None:
            not_found()

        await _assert_admin_for_scope(session, caller, config.project_id)

        service = AIProviderConfigService(session)
        ledgers = await service.get_budgets(
            provider_config_id=provider_config_id,
            project_id=config.project_id,
        )
        return [
            BudgetRecord(
                period_kind=cast("Literal['daily', 'monthly']", row.period_kind),
                period_start=row.period_start,
                token_cap=row.token_cap,
                tokens_used=row.tokens_used,
                tokens_reserved=row.tokens_reserved,
            )
            for row in ledgers
        ]


@router.put(
    "/budgets",
    response_model=BudgetRecord,
    summary="Set token budget cap for provider configuration",
)
async def set_budget(
    body: BudgetSetRequest,
    caller: Caller,
    session: Session,
) -> BudgetRecord:
    """Configure or update maximum token budget limits for an AI provider configuration."""
    async with timing_floor(floor_ms=25.0):
        stmt = select(AIProviderConfig).where(AIProviderConfig.id == body.provider_config_id)
        res = await session.execute(stmt)
        config = res.scalar_one_or_none()
        if config is None:
            not_found()

        target_project_id = body.project_id or config.project_id
        await _assert_admin_for_scope(session, caller, target_project_id)

        service = AIProviderConfigService(session)
        try:
            ledger = await service.set_budget(
                workspace_id=caller.workspace_id,
                provider_config_id=body.provider_config_id,
                period_kind=body.period_kind,
                token_cap=body.token_cap,
                project_id=body.project_id,
            )
        except AIConfigValidationError as exc:
            raise ProblemException(
                code="INVALID_REQUEST",
                status=422,
                title="Validation Error",
                detail=str(exc),
            ) from exc

        await record_activity(
            session=session,
            workspace_id=caller.workspace_id,
            actor_principal_id=caller.principal_id,
            event_type=ActivityEventType.AI_BUDGET_SET,
            payload={
                "provider_config_id": str(body.provider_config_id),
                "period_kind": body.period_kind,
                "token_cap": body.token_cap,
                "project_id": str(body.project_id) if body.project_id else None,
            },
        )
        return BudgetRecord(
            period_kind=cast("Literal['daily', 'monthly']", ledger.period_kind),
            period_start=ledger.period_start,
            token_cap=ledger.token_cap,
            tokens_used=ledger.tokens_used,
            tokens_reserved=ledger.tokens_reserved,
        )
