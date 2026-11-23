# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""AI provider configuration service: key custody and air-gap enforcement (KB-P5-05a)."""

from __future__ import annotations

import asyncio
import ipaddress
import logging
import re
import time
import urllib.parse
import uuid
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING, Any, Final

import httpx
from sqlalchemy import delete, select, text

from database.models.ai import AIProviderConfig, AITokenLedger
from kanban.ai_config.net_guard import (
    LOCAL_AND_PRIVATE_CIDRS,
    EgressDeniedError,
    Resolver,
    SSRFBlockedError,
    is_hard_denied,
    is_local_base_url,
    is_local_or_private_ip,
    is_private_lan_hostname,
    resolve_and_pin,
)
from kanban.security.envelope import (
    BLOB_VERSION,
    CODE_TAG_MISMATCH,
    NONCE_LENGTH_BYTES,
    EnvelopeDecryptError,
    KekProvider,
    SealedSecret,
    StaticKekProvider,
    open_bound,
    seal_bound,
)
from kanban.security.scrubber import scrub_text

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

_ALLOWED_PROVIDER_KINDS: Final[frozenset[str]] = frozenset(
    {"openai", "ollama", "gemini", "fixture"}
)
_CLOUD_PROVIDER_KINDS: Final[frozenset[str]] = frozenset({"openai", "gemini"})
_RESIDENCY_REGEX: Final[re.Pattern[str]] = re.compile(r"^[a-z0-9:._-]{1,64}$")
_LOOPBACK_HOSTS: Final[frozenset[str]] = frozenset({"127.0.0.1", "::1", "localhost"})

_MAX_DISPLAY_NAME_LEN: Final[int] = 80
_MAX_MODELS_LEN: Final[int] = 32
_IPV6_VERSION: Final[int] = 6
_MAX_TOKEN_CAP: Final[int] = 10_000_000_000
_HTTP_200: Final[int] = 200
_HTTP_401: Final[int] = 401
_HTTP_403: Final[int] = 403
_HTTP_404: Final[int] = 404


class AirGapViolation(Exception):  # noqa: N818
    """Raised when external cloud provider egress is attempted under active air-gap mode."""

    def __init__(
        self,
        message: str = "Outbound cloud egress is denied under air-gap mode",
        code: str = "AIR_GAP_EGRESS_DENIED",
    ) -> None:
        """Initialize AirGapViolation with diagnostic code and message."""
        super().__init__(message)
        self.code = code
        self.message = message


class EnvelopeIntegrityError(EnvelopeDecryptError):
    """Raised when GCM authentication tag verification fails (e.g., bit flipped or tampered)."""

    def __init__(
        self,
        code: str = CODE_TAG_MISMATCH,
        message: str = "Envelope integrity check failed (authentication tag mismatch)",
    ) -> None:
        """Initialize EnvelopeIntegrityError with diagnostic code and message."""
        super().__init__(code)
        self.message = message


class AIConfigValidationError(ValueError):
    """Raised when an AI provider configuration fails validation constraints."""


class AIConfigNotFoundError(KeyError):
    """Raised when the requested AI provider configuration is not found."""


def build_ai_provider_aad(
    config_id: uuid.UUID | str,
    workspace_id: uuid.UUID | str,
    provider_kind: str,
) -> bytes:
    """Construct canonical Additional Authenticated Data (AAD) for provider row binding."""
    return f"{config_id}|{workspace_id}|{provider_kind}".encode()


def _validate_base_url_host(parsed: urllib.parse.SplitResult) -> None:
    host = (parsed.hostname or "").strip("[]").lower()
    if not host:
        msg = "base_url must contain a valid host"
        raise AIConfigValidationError(msg)

    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        ip = None

    if ip is not None:
        if is_hard_denied(ip):
            msg = f"base_url must not target link-local, multicast, or metadata address '{host}'"
            raise AIConfigValidationError(msg)
        if parsed.scheme != "https" and not is_local_or_private_ip(ip):
            msg = (
                "base_url must use HTTPS unless targeting loopback (127.0.0.1, ::1, localhost) "
                f"or private LAN (got {host})"
            )
            raise AIConfigValidationError(msg)
    elif parsed.scheme != "https" and not is_private_lan_hostname(host):
        msg = (
            "base_url must use HTTPS unless targeting loopback (127.0.0.1, ::1, localhost) "
            "or private LAN"
        )
        raise AIConfigValidationError(msg)


def validate_base_url(base_url: str | None) -> str | None:
    """Validate base URL scheme, absence of userinfo/query/fragment, and private LAN rules."""
    if base_url is None:
        return None
    trimmed = base_url.strip()
    if not trimmed:
        return None

    parsed = urllib.parse.urlsplit(trimmed)
    if parsed.scheme not in ("http", "https"):
        msg = f"base_url scheme must be 'http' or 'https' (got {parsed.scheme!r})"
        raise AIConfigValidationError(msg)

    if parsed.username or parsed.password:
        msg = "base_url must not contain userinfo"
        raise AIConfigValidationError(msg)

    if parsed.query:
        msg = "base_url must not contain query parameters"
        raise AIConfigValidationError(msg)

    if parsed.fragment:
        msg = "base_url must not contain fragment"
        raise AIConfigValidationError(msg)

    _validate_base_url_host(parsed)
    return trimmed


def _validate_fields(
    provider_kind: str,
    display_name: str,
    model_allowlist: list[str],
    residency_tier: str,
    base_url: str | None,
) -> None:
    """Validate provider configuration field constraints against schema invariants."""
    norm_kind = provider_kind.strip().lower()
    if norm_kind not in _ALLOWED_PROVIDER_KINDS:
        msg = f"provider_kind must be one of {sorted(_ALLOWED_PROVIDER_KINDS)}"
        raise AIConfigValidationError(msg)

    name = display_name.strip()
    if not (1 <= len(name) <= _MAX_DISPLAY_NAME_LEN):
        msg = f"display_name length must be between 1 and {_MAX_DISPLAY_NAME_LEN} (got {len(name)})"
        raise AIConfigValidationError(msg)

    if not (1 <= len(model_allowlist) <= _MAX_MODELS_LEN):
        msg = f"model_allowlist cardinality must be between 1 and {_MAX_MODELS_LEN}"
        raise AIConfigValidationError(msg)

    for idx, model in enumerate(model_allowlist):
        if not model.strip():
            msg = f"model_allowlist entry at index {idx} must be a non-empty string"
            raise AIConfigValidationError(msg)

    tier = residency_tier.strip()
    if not _RESIDENCY_REGEX.match(tier):
        msg = f"residency_tier must match '^[a-z0-9:._-]{{1,64}}$' (got {residency_tier!r})"
        raise AIConfigValidationError(msg)

    validate_base_url(base_url)


def _check_air_gap(
    provider_kind: str,
    base_url: str | None = None,
    *,
    air_gap_mode: bool | None,
) -> None:
    """Enforce air-gap policy: cloud providers are forbidden unless targeting local endpoints."""
    norm_kind = provider_kind.strip().lower()
    if air_gap_mode is True:
        if norm_kind == "openai" and is_local_base_url(base_url):
            return
        if norm_kind in _CLOUD_PROVIDER_KINDS:
            msg = (
                f"Air-gap mode is active: outbound cloud egress to provider '{provider_kind}' "
                f"is strictly prohibited"
            )
            raise AirGapViolation(msg, code="AIR_GAP_EGRESS_DENIED")


_HTTP_OK = 200
_HTTP_BAD_REQUEST = 400
_HTTP_UNAUTHORIZED = 401
_HTTP_FORBIDDEN = 403
_HTTP_NOT_FOUND = 404


class AIProviderConfigService:
    """Service managing envelope-encrypted AI provider configurations and air-gap policy."""

    def __init__(
        self,
        session: AsyncSession,
        kek_provider: KekProvider | None = None,
        resolver: Resolver | None = None,
    ) -> None:
        """Initialize service with active database session and KEK provider."""
        self._session = session
        if kek_provider is None:
            try:
                from kanban.security.keys import load_key_material  # noqa: PLC0415

                km = load_key_material()
                kek_provider = StaticKekProvider(
                    {km.master_kek_kid: km.master_kek},
                    current=km.master_kek_kid,
                )
            except (KeyError, ValueError, RuntimeError, TypeError, OSError):
                kek_provider = None
        self._kek = kek_provider
        self._resolver = resolver

    @staticmethod
    def _seal_key_material(
        config_id: uuid.UUID,
        workspace_id: uuid.UUID,
        provider_kind: str,
        api_key: bytearray | bytes | str,
        kek_provider: KekProvider | None,
    ) -> tuple[bytes, bytes, bytes, str]:
        """Wrap plaintext API key using AES-256-GCM envelope encryption and zero source bytes."""
        if kek_provider is None:
            msg = "No KEK provider configured for AI provider secret sealing"
            raise RuntimeError(msg)
        if isinstance(api_key, str):
            raw_key = bytearray(api_key.encode("utf-8"))
        elif isinstance(api_key, bytes):
            raw_key = bytearray(api_key)
        else:
            raw_key = api_key

        try:
            aad = build_ai_provider_aad(config_id, workspace_id, provider_kind)
            sealed = seal_bound(bytes(raw_key), aad, kek_provider)

            blob = sealed.encrypted_secret_blob
            nonce = blob[1 : 1 + NONCE_LENGTH_BYTES]
            wrapped_key = blob[1 + NONCE_LENGTH_BYTES :]
            wrapped_dek = sealed.wrapped_dek
            dek_kid = sealed.dek_kid

            return wrapped_key, nonce, wrapped_dek, dek_kid
        finally:
            if isinstance(api_key, bytearray):
                for idx in range(len(api_key)):
                    api_key[idx] = 0
            if raw_key is not api_key:
                for idx in range(len(raw_key)):
                    raw_key[idx] = 0

    @staticmethod
    def _unwrap_key_material(  # noqa: PLR0913, PLR0917
        config_id: uuid.UUID,
        workspace_id: uuid.UUID,
        provider_kind: str,
        wrapped_api_key: bytes,
        api_key_nonce: bytes,
        wrapped_dek: bytes,
        dek_kid: str,
        kek_provider: KekProvider | None,
    ) -> bytearray:
        """Unwrap and authenticate encrypted API key returning a mutable bytearray."""
        if kek_provider is None:
            msg = "No KEK provider configured for AI provider secret unwrapping"
            raise RuntimeError(msg)
        aad = build_ai_provider_aad(config_id, workspace_id, provider_kind)
        encrypted_blob = bytes([BLOB_VERSION]) + api_key_nonce + wrapped_api_key
        sealed = SealedSecret(
            encrypted_secret_blob=encrypted_blob,
            wrapped_dek=wrapped_dek,
            dek_kid=dek_kid,
        )

        try:
            return open_bound(sealed, aad, kek_provider)
        except EnvelopeDecryptError as exc:
            raise EnvelopeIntegrityError(
                code=exc.code,
                message=f"Envelope integrity check failed: {exc.code}",
            ) from exc

    async def create_config(  # noqa: PLR0913
        self,
        workspace_id: uuid.UUID,
        provider_kind: str,
        display_name: str,
        model_allowlist: list[str],
        *,
        residency_tier: str = "default",
        project_id: uuid.UUID | None = None,
        base_url: str | None = None,
        priority: int = 100,
        settings_json: dict[str, Any] | None = None,
        api_key: bytearray | bytes | str | None = None,
        is_enabled: bool = True,
        air_gap_mode: bool | None = None,
        config_id: uuid.UUID | None = None,
    ) -> AIProviderConfig:
        """Create and persist a new AI provider configuration."""
        _validate_fields(
            provider_kind=provider_kind,
            display_name=display_name,
            model_allowlist=model_allowlist,
            residency_tier=residency_tier,
            base_url=base_url,
        )
        _check_air_gap(provider_kind, base_url=base_url, air_gap_mode=air_gap_mode)

        assigned_id = config_id if config_id is not None else uuid.uuid4()
        norm_kind = provider_kind.strip().lower()

        wrapped_key: bytes | None = None
        nonce: bytes | None = None
        wrapped_dek: bytes | None = None
        dek_kid: str | None = None

        if api_key is not None:
            wrapped_key, nonce, wrapped_dek, dek_kid = self._seal_key_material(
                config_id=assigned_id,
                workspace_id=workspace_id,
                provider_kind=norm_kind,
                api_key=api_key,
                kek_provider=self._kek,
            )

        config = AIProviderConfig(
            id=assigned_id,
            workspace_id=workspace_id,
            project_id=project_id,
            provider_kind=norm_kind,
            display_name=display_name.strip(),
            base_url=base_url.strip() if base_url else None,
            model_allowlist=[m.strip() for m in model_allowlist],
            residency_tier=residency_tier.strip(),
            priority=priority,
            settings_json=settings_json if settings_json is not None else {},
            wrapped_api_key=wrapped_key,
            api_key_nonce=nonce,
            wrapped_dek=wrapped_dek,
            dek_kid=dek_kid,
            is_enabled=is_enabled,
        )

        self._session.add(config)
        await self._session.flush()
        return config

    async def update_config(  # noqa: C901, PLR0912, PLR0913
        self,
        config_id: uuid.UUID,
        *,
        display_name: str | None = None,
        model_allowlist: list[str] | None = None,
        residency_tier: str | None = None,
        base_url: str | None = None,
        priority: int | None = None,
        settings_json: dict[str, Any] | None = None,
        api_key: bytearray | bytes | str | None = None,
        clear_api_key: bool = False,
        is_enabled: bool | None = None,
        air_gap_mode: bool | None = None,
    ) -> AIProviderConfig:
        """Update an existing AI provider configuration."""
        config = await self.get_config(config_id)
        if config is None:
            msg = f"AIProviderConfig {config_id} not found"
            raise AIConfigNotFoundError(msg)

        if air_gap_mode is not None:
            effective_base_url = base_url if base_url is not None else config.base_url
            _check_air_gap(
                config.provider_kind,
                base_url=effective_base_url,
                air_gap_mode=air_gap_mode,
            )

        if display_name is not None:
            name = display_name.strip()
            if not (1 <= len(name) <= _MAX_DISPLAY_NAME_LEN):
                msg = (
                    f"display_name length must be between 1 and {_MAX_DISPLAY_NAME_LEN} "
                    f"(got {len(name)})"
                )
                raise AIConfigValidationError(msg)
            config.display_name = name

        if model_allowlist is not None:
            if not (1 <= len(model_allowlist) <= _MAX_MODELS_LEN):
                msg = (
                    f"model_allowlist cardinality must be between 1 and {_MAX_MODELS_LEN} "
                    f"(got {len(model_allowlist)})"
                )
                raise AIConfigValidationError(msg)
            config.model_allowlist = [m.strip() for m in model_allowlist]

        if residency_tier is not None:
            tier = residency_tier.strip()
            if not _RESIDENCY_REGEX.match(tier):
                msg = f"residency_tier must match '^[a-z0-9:._-]{{1,64}}$' (got {tier!r})"
                raise AIConfigValidationError(msg)
            config.residency_tier = tier

        if base_url is not None:
            config.base_url = validate_base_url(base_url)

        if priority is not None:
            config.priority = priority

        if settings_json is not None:
            config.settings_json = settings_json

        if is_enabled is not None:
            config.is_enabled = is_enabled

        if clear_api_key:
            config.wrapped_api_key = None
            config.api_key_nonce = None
            config.wrapped_dek = None
            config.dek_kid = None
        elif api_key is not None:
            wrapped_key, nonce, wrapped_dek, dek_kid = self._seal_key_material(
                config_id=config.id,
                workspace_id=config.workspace_id,
                provider_kind=config.provider_kind,
                api_key=api_key,
                kek_provider=self._kek,
            )
            config.wrapped_api_key = wrapped_key
            config.api_key_nonce = nonce
            config.wrapped_dek = wrapped_dek
            config.dek_kid = dek_kid

        await self._session.flush()
        return config

    async def disable_config(self, config_id: uuid.UUID) -> AIProviderConfig:
        """Mark configuration row as disabled without deleting records."""
        return await self.update_config(config_id, is_enabled=False)

    async def delete_config(self, config_id: uuid.UUID) -> None:
        """Delete an AI provider configuration row and cascaded ledgers."""
        stmt = delete(AIProviderConfig).where(AIProviderConfig.id == config_id)
        await self._session.execute(stmt)
        await self._session.flush()

    async def get_config(self, config_id: uuid.UUID) -> AIProviderConfig | None:
        """Retrieve configuration row by primary key."""
        stmt = select(AIProviderConfig).where(AIProviderConfig.id == config_id)
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def list_configs(
        self,
        workspace_id: uuid.UUID,
        project_id: uuid.UUID | None = None,
    ) -> list[AIProviderConfig]:
        """List provider configurations for workspace, optionally filtered by project."""
        stmt = select(AIProviderConfig).where(AIProviderConfig.workspace_id == workspace_id)
        if project_id is not None:
            stmt = stmt.where(AIProviderConfig.project_id == project_id)
        stmt = stmt.order_by(AIProviderConfig.priority.asc(), AIProviderConfig.created_at.asc())
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    def to_public_dict(self, config: AIProviderConfig) -> dict[str, Any]:
        """Convert configuration to public dictionary with zero secret leakage."""
        return {
            "id": str(config.id),
            "workspace_id": str(config.workspace_id),
            "project_id": str(config.project_id) if config.project_id is not None else None,
            "provider_kind": config.provider_kind,
            "display_name": config.display_name,
            "base_url": config.base_url,
            "model_allowlist": list(config.model_allowlist),
            "residency_tier": config.residency_tier,
            "priority": config.priority,
            "settings_json": dict(config.settings_json or {}),
            "is_enabled": config.is_enabled,
            "api_key_set": bool(config.wrapped_api_key is not None),
            "created_at": config.created_at.isoformat(),
            "updated_at": config.updated_at.isoformat(),
        }

    async def unwrap_api_key(
        self,
        config_id: uuid.UUID,
        *,
        secret_override: tuple[bytes, bytes, bytes, str] | None = None,
    ) -> bytearray:
        """Unwrap envelope-encrypted API key via security definer function."""
        if secret_override is not None:
            wrapped_key, nonce, wrapped_dek, dek_kid = secret_override
            cfg_stmt = text(
                "SELECT workspace_id, provider_kind FROM ai_provider_configs WHERE id = :cid"
            )
            cfg_res = await self._session.execute(cfg_stmt, {"cid": config_id})
            cfg_row = cfg_res.mappings().first()
            if cfg_row is None:
                msg = f"AI provider config {config_id} not found"
                raise AIConfigNotFoundError(msg)
            ws_id = cfg_row["workspace_id"]
            kind = cfg_row["provider_kind"]
        else:
            fn_stmt = text(
                "SELECT wrapped_api_key, api_key_nonce, wrapped_dek, dek_kid "
                "FROM ai_provider_secret(:cid)"
            )
            res = await self._session.execute(fn_stmt, {"cid": config_id})
            row = res.mappings().first()
            if row is None or row["wrapped_api_key"] is None:
                msg = f"No secret or configuration found for config {config_id}"
                raise AIConfigNotFoundError(msg)

            wrapped_key = bytes(row["wrapped_api_key"])
            nonce = bytes(row["api_key_nonce"])
            wrapped_dek = bytes(row["wrapped_dek"])
            dek_kid = str(row["dek_kid"])

            cfg_stmt = text(
                "SELECT workspace_id, provider_kind FROM ai_provider_configs WHERE id = :cid"
            )
            cfg_res = await self._session.execute(cfg_stmt, {"cid": config_id})
            cfg_row = cfg_res.mappings().first()
            if cfg_row is None:
                msg = f"AI provider config {config_id} not found"
                raise AIConfigNotFoundError(msg)
            ws_id = cfg_row["workspace_id"]
            kind = cfg_row["provider_kind"]

        return self._unwrap_key_material(
            config_id=config_id,
            workspace_id=ws_id,
            provider_kind=kind,
            wrapped_api_key=wrapped_key,
            api_key_nonce=nonce,
            wrapped_dek=wrapped_dek,
            dek_kid=dek_kid,
            kek_provider=self._kek,
        )

    async def get_budgets(
        self,
        provider_config_id: uuid.UUID,
        project_id: uuid.UUID | None = None,
    ) -> list[AITokenLedger]:
        """List active and historical token ledger rows for provider config."""
        stmt = select(AITokenLedger).where(AITokenLedger.provider_config_id == provider_config_id)
        if project_id is not None:
            stmt = stmt.where(AITokenLedger.project_id == project_id)
        stmt = stmt.order_by(AITokenLedger.period_start.desc(), AITokenLedger.period_kind.asc())
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def set_budget(  # noqa: PLR0912, PLR0913
        self,
        workspace_id: uuid.UUID,
        provider_config_id: uuid.UUID,
        period_kind: str,
        token_cap: int,
        *,
        project_id: uuid.UUID | None = None,
        now_dt: datetime | None = None,
    ) -> AITokenLedger:
        """Upsert current-period token ledger cap for daily or monthly period."""
        if period_kind not in ("daily", "monthly"):
            msg = f"period_kind must be 'daily' or 'monthly' (got {period_kind!r})"
            raise AIConfigValidationError(msg)
        if not (0 <= token_cap <= _MAX_TOKEN_CAP):
            msg = f"token_cap must be between 0 and {_MAX_TOKEN_CAP} (got {token_cap})"
            raise AIConfigValidationError(msg)

        current_utc = now_dt.astimezone(UTC) if now_dt is not None else datetime.now(UTC)
        if period_kind == "daily":
            p_start = current_utc.date()
        else:
            p_start = date(current_utc.year, current_utc.month, 1)

        stmt = select(AITokenLedger).where(
            AITokenLedger.workspace_id == workspace_id,
            AITokenLedger.provider_config_id == provider_config_id,
            AITokenLedger.period_kind == period_kind,
            AITokenLedger.period_start == p_start,
        )
        if project_id is not None:
            stmt = stmt.where(AITokenLedger.project_id == project_id)
        else:
            stmt = stmt.where(AITokenLedger.project_id.is_(None))

        res = await self._session.execute(stmt)
        existing = res.scalars().first()

        if existing is not None:
            if token_cap < existing.tokens_used + existing.tokens_reserved:
                msg = (
                    f"New token_cap ({token_cap}) is less than currently used + reserved tokens "
                    f"({existing.tokens_used + existing.tokens_reserved})"
                )
                raise AIConfigValidationError(msg)
            existing.token_cap = token_cap
            ledger = existing
        else:
            ledger = AITokenLedger(
                id=uuid.uuid4(),
                workspace_id=workspace_id,
                project_id=project_id,
                provider_config_id=provider_config_id,
                period_kind=period_kind,
                period_start=p_start,
                token_cap=token_cap,
                tokens_reserved=0,
                tokens_used=0,
            )
            self._session.add(ledger)

        future_stmt = select(AITokenLedger).where(
            AITokenLedger.workspace_id == workspace_id,
            AITokenLedger.provider_config_id == provider_config_id,
            AITokenLedger.period_kind == period_kind,
            AITokenLedger.period_start > p_start,
        )
        if project_id is not None:
            future_stmt = future_stmt.where(AITokenLedger.project_id == project_id)
        else:
            future_stmt = future_stmt.where(AITokenLedger.project_id.is_(None))

        fut_res = await self._session.execute(future_stmt)
        for fut in fut_res.scalars().all():
            if token_cap >= fut.tokens_used + fut.tokens_reserved:
                fut.token_cap = token_cap

        await self._session.flush()
        return ledger

    async def probe_provider(  # noqa: C901, PLR0911, PLR0912, PLR0913, PLR0915
        self,
        provider_kind: str,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        config_id: uuid.UUID | None = None,
        air_gap_mode: bool | None = None,
        resolver: Resolver | None = None,
        timeout_ms: int | None = None,
        settings_json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Probe upstream provider models and latency with zeroize key cleanup and SSRF defense."""
        norm_kind = provider_kind.strip().lower()

        # 1. Determine base URL
        resolved_base_url: str
        if base_url is not None and base_url.strip():
            try:
                validated = validate_base_url(base_url)
            except AIConfigValidationError as exc:
                return {
                    "ok": False,
                    "latency_ms": 0.0,
                    "models": [],
                    "model_count": 0,
                    "error_code": "INVALID_BASE_URL",
                    "message": str(exc),
                }
            if validated is None:
                return {
                    "ok": False,
                    "latency_ms": 0.0,
                    "models": [],
                    "model_count": 0,
                    "error_code": "INVALID_BASE_URL",
                    "message": "base_url must not be empty",
                }
            resolved_base_url = validated
        elif norm_kind == "ollama":
            resolved_base_url = "http://127.0.0.1:11434"
        elif norm_kind == "gemini":
            resolved_base_url = "https://generativelanguage.googleapis.com"
        else:
            resolved_base_url = "https://api.openai.com/v1"

        # 2. Air gap validation
        try:
            _check_air_gap(norm_kind, base_url=resolved_base_url, air_gap_mode=air_gap_mode)
        except AirGapViolation as exc:
            return {
                "ok": False,
                "latency_ms": 0.0,
                "models": [],
                "model_count": 0,
                "error_code": "AIR_GAP_EGRESS_DENIED",
                "message": str(exc),
            }

        # 3. SSRF defense via resolve_and_pin and target reconstruction
        parsed = urllib.parse.urlsplit(resolved_base_url)
        host = (parsed.hostname or "").strip("[]")
        is_https = parsed.scheme == "https"
        default_port = 443 if is_https else 80
        port = parsed.port or default_port
        try:
            allowed_cidrs = None if is_https else LOCAL_AND_PRIVATE_CIDRS
            active_resolver = resolver if resolver is not None else self._resolver
            raw_pinned: Any = await resolve_and_pin(
                host,
                port,
                allowed_cidrs=allowed_cidrs,
                resolver=active_resolver,
            )
            pinned_ip: ipaddress.IPv4Address | ipaddress.IPv6Address
            if isinstance(raw_pinned, (ipaddress.IPv4Address, ipaddress.IPv6Address)):
                pinned_ip = raw_pinned
            else:
                pinned_ip = ipaddress.ip_address("127.0.0.1")

            if not is_https and not is_local_or_private_ip(pinned_ip):
                msg = (
                    f"HTTP endpoint '{host}' resolved to public IP '{pinned_ip}'; "
                    "cleartext HTTP is restricted to local/private addresses"
                )
                raise SSRFBlockedError(msg, code="SSRF_BLOCKED")
        except EgressDeniedError as exc:
            return {
                "ok": False,
                "latency_ms": 0.0,
                "models": [],
                "model_count": 0,
                "error_code": exc.code,
                "message": str(exc),
            }

        # Zero DNS rebinding: construct literal pinned IP target URL and headers
        host_repr = f"[{pinned_ip}]" if pinned_ip.version == _IPV6_VERSION else str(pinned_ip)
        port_suffix = f":{port}" if (parsed.port and parsed.port != default_port) else ""
        base_path = parsed.path.rstrip("/")
        pinned_base_url = f"{parsed.scheme}://{host_repr}{port_suffix}{base_path}"

        host_in_header = f"[{host}]" if ":" in host and not host.startswith("[") else host
        host_header = (
            f"{host_in_header}:{port}"
            if (parsed.port and parsed.port != default_port)
            else host_in_header
        )
        base_headers: dict[str, str] = {"Host": host_header}
        extensions: dict[str, Any] = {"sni_hostname": host} if is_https else {}

        # 4. Resolve API key with zeroize cleanup in finally
        key_material: bytearray | None = None
        try:
            if api_key is not None and api_key.strip():
                key_material = bytearray(api_key.encode("utf-8"))
            elif config_id is not None:
                try:
                    key_material = await self.unwrap_api_key(config_id)
                except AIConfigNotFoundError:
                    key_material = None

            active_key = key_material.decode("utf-8") if key_material is not None else ""

            if settings_json is None and config_id is not None:
                cfg_stmt = text("SELECT settings_json FROM ai_provider_configs WHERE id = :cid")
                cfg_res = await self._session.execute(cfg_stmt, {"cid": config_id})
                row = cfg_res.first()
                if row is not None and row[0]:
                    settings_json = dict(row[0])

            effective_timeout_ms = (
                timeout_ms or (settings_json.get("timeout_ms") if settings_json else None) or 8000
            )
            probe_timeout_s = float(effective_timeout_ms) / 1000.0

            # 5. Dispatch upstream probe request
            start_time = time.monotonic()
            async with (
                asyncio.timeout(probe_timeout_s),
                httpx.AsyncClient(
                    follow_redirects=False,
                    trust_env=False,
                    timeout=httpx.Timeout(probe_timeout_s),
                ) as client,
            ):
                if norm_kind == "ollama":
                    tags_url = f"{pinned_base_url.rstrip('/')}/api/tags"
                    resp = await client.get(tags_url, headers=base_headers, extensions=extensions)
                    latency = (time.monotonic() - start_time) * 1000.0
                    if resp.status_code != _HTTP_OK:
                        body_snip = resp.text[:200]
                        return {
                            "ok": False,
                            "latency_ms": round(latency, 2),
                            "models": [],
                            "model_count": 0,
                            "error_code": f"HTTP_{resp.status_code}",
                            "message": f"Ollama returned HTTP {resp.status_code}: {body_snip}",
                        }
                    data = resp.json()
                    models = [
                        m["name"]
                        for m in data.get("models", [])
                        if isinstance(m, dict) and "name" in m
                    ]
                    msg = f"Successfully connected to Ollama ({len(models)} models available)"
                    return {
                        "ok": True,
                        "latency_ms": round(latency, 2),
                        "models": models,
                        "model_count": len(models),
                        "error_code": None,
                        "message": msg,
                    }

                if norm_kind == "gemini":
                    models_url = f"{pinned_base_url.rstrip('/')}/v1beta/models"
                    headers = dict(base_headers)
                    if active_key:
                        headers["x-goog-api-key"] = active_key
                    resp = await client.get(models_url, headers=headers, extensions=extensions)
                    latency = (time.monotonic() - start_time) * 1000.0
                    bad_statuses = (
                        _HTTP_BAD_REQUEST,
                        _HTTP_UNAUTHORIZED,
                        _HTTP_FORBIDDEN,
                    )
                    if active_key.startswith("AQ.") and resp.status_code in bad_statuses:
                        v_host = "aiplatform.googleapis.com"
                        v_port = 443
                        try:
                            v_raw_pinned: Any = await resolve_and_pin(
                                v_host,
                                v_port,
                                allowed_cidrs=allowed_cidrs,
                                resolver=active_resolver,
                            )
                            v_pinned_ip = (
                                v_raw_pinned
                                if isinstance(
                                    v_raw_pinned,
                                    (ipaddress.IPv4Address, ipaddress.IPv6Address),
                                )
                                else ipaddress.ip_address("127.0.0.1")
                            )
                            v_host_repr = (
                                f"[{v_pinned_ip}]"
                                if v_pinned_ip.version == _IPV6_VERSION
                                else str(v_pinned_ip)
                            )
                            vertex_url = (
                                f"https://{v_host_repr}/v1/publishers/google/"
                                "models/gemini-2.5-flash-lite:countTokens"
                            )
                            v_headers = {
                                "Host": v_host,
                                "x-goog-api-key": active_key,
                                "Content-Type": "application/json",
                            }
                            v_extensions: dict[str, Any] = {"sni_hostname": v_host}
                            v_resp = await client.post(
                                vertex_url,
                                headers=v_headers,
                                json={"contents": [{"parts": [{"text": "ping"}]}]},
                                extensions=v_extensions,
                            )
                            if v_resp.status_code == _HTTP_OK:
                                models = [
                                    "gemini-2.5-flash-lite",
                                    "gemini-2.5-flash",
                                    "gemini-2.5-pro",
                                ]
                                msg = (
                                    "Successfully connected to Gemini (Vertex Express) "
                                    f"({len(models)} models available)"
                                )
                                return {
                                    "ok": True,
                                    "latency_ms": round(
                                        (time.monotonic() - start_time) * 1000.0, 2
                                    ),
                                    "models": models,
                                    "model_count": len(models),
                                    "error_code": None,
                                    "message": msg,
                                }
                        except Exception as v_exc:  # noqa: BLE001
                            logger.debug(
                                "Vertex express fallback probe failed: %s",
                                scrub_text(str(v_exc)),
                            )
                    if resp.status_code in (_HTTP_UNAUTHORIZED, _HTTP_FORBIDDEN):
                        return {
                            "ok": False,
                            "latency_ms": round(latency, 2),
                            "models": [],
                            "model_count": 0,
                            "error_code": "UPSTREAM_AUTH_FAILED",
                            "message": f"Gemini authentication failed (HTTP {resp.status_code})",
                        }
                    if resp.status_code != _HTTP_OK:
                        body_snip = resp.text[:200]
                        return {
                            "ok": False,
                            "latency_ms": round(latency, 2),
                            "models": [],
                            "model_count": 0,
                            "error_code": f"HTTP_{resp.status_code}",
                            "message": f"Gemini returned HTTP {resp.status_code}: {body_snip}",
                        }
                    data = resp.json()
                    models = [
                        m["name"].removeprefix("models/")
                        for m in data.get("models", [])
                        if isinstance(m, dict) and "name" in m
                    ]
                    msg = f"Successfully connected to Gemini ({len(models)} models available)"
                    return {
                        "ok": True,
                        "latency_ms": round(latency, 2),
                        "models": models,
                        "model_count": len(models),
                        "error_code": None,
                        "message": msg,
                    }

                # Default: openai-compatible inference endpoints
                base = pinned_base_url.rstrip("/")
                models_url = f"{base}/models" if base.endswith("/v1") else f"{base}/v1/models"
                headers = dict(base_headers)
                if active_key:
                    headers["Authorization"] = f"Bearer {active_key}"
                resp = await client.get(models_url, headers=headers, extensions=extensions)
                if resp.status_code == _HTTP_NOT_FOUND and not base.endswith("/v1"):
                    resp = await client.get(
                        f"{base}/models",
                        headers=headers,
                        extensions=extensions,
                    )
                latency = (time.monotonic() - start_time) * 1000.0
                if resp.status_code in (_HTTP_UNAUTHORIZED, _HTTP_FORBIDDEN):
                    return {
                        "ok": False,
                        "latency_ms": round(latency, 2),
                        "models": [],
                        "model_count": 0,
                        "error_code": "UPSTREAM_AUTH_FAILED",
                        "message": f"OpenAI authentication failed (HTTP {resp.status_code})",
                    }
                if resp.status_code != _HTTP_OK:
                    body_snip = resp.text[:200]
                    return {
                        "ok": False,
                        "latency_ms": round(latency, 2),
                        "models": [],
                        "model_count": 0,
                        "error_code": f"HTTP_{resp.status_code}",
                        "message": f"OpenAI returned HTTP {resp.status_code}: {body_snip}",
                    }
                data = resp.json()
                models = [
                    m["id"] for m in data.get("data", []) if isinstance(m, dict) and "id" in m
                ]
                msg = f"Successfully connected to OpenAI ({len(models)} models available)"
                return {
                    "ok": True,
                    "latency_ms": round(latency, 2),
                    "models": models,
                    "model_count": len(models),
                    "error_code": None,
                    "message": msg,
                }

        except httpx.ConnectError as exc:
            return {
                "ok": False,
                "latency_ms": 0.0,
                "models": [],
                "model_count": 0,
                "error_code": "CONNECTION_REFUSED",
                "message": f"Connection refused: {scrub_text(str(exc))}",
            }
        except (httpx.TimeoutException, TimeoutError) as exc:
            lat = float(effective_timeout_ms if "effective_timeout_ms" in locals() else 8000.0)
            return {
                "ok": False,
                "latency_ms": lat,
                "models": [],
                "model_count": 0,
                "error_code": "UPSTREAM_TIMEOUT",
                "message": f"Connection timed out: {scrub_text(str(exc))}",
            }
        except Exception as exc:  # noqa: BLE001
            return {
                "ok": False,
                "latency_ms": 0.0,
                "models": [],
                "model_count": 0,
                "error_code": "PROBE_ERROR",
                "message": scrub_text(str(exc)),
            }
        finally:
            if key_material is not None:
                for idx in range(len(key_material)):
                    key_material[idx] = 0
