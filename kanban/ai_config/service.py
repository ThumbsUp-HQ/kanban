# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""AI provider configuration service: key custody and air-gap enforcement (KB-P5-05a)."""

from __future__ import annotations

import re
import urllib.parse
import uuid
from typing import TYPE_CHECKING, Any, Final

from sqlalchemy import delete, select, text

from database.models.ai import AIProviderConfig
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

_DEFAULT_KEK_FALLBACK = StaticKekProvider(
    keys={"kek-v1": b"k" * 32},
    current="kek-v1",
)


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


def validate_base_url(base_url: str | None) -> str | None:
    """Validate base URL scheme, absence of userinfo/query/fragment, and loopback rules."""
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

    host = (parsed.hostname or "").strip("[]").lower()
    if parsed.scheme != "https" and host not in _LOOPBACK_HOSTS:
        msg = "base_url must use HTTPS unless targeting loopback (127.0.0.1, ::1, localhost)"
        raise AIConfigValidationError(msg)

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


def _check_air_gap(provider_kind: str, *, air_gap_mode: bool | None) -> None:
    """Enforce air-gap policy: cloud providers are forbidden when air_gap_mode is active."""
    norm_kind = provider_kind.strip().lower()
    if air_gap_mode is True and norm_kind in _CLOUD_PROVIDER_KINDS:
        msg = (
            f"Air-gap mode is active: outbound cloud egress to provider '{provider_kind}' "
            f"is strictly prohibited"
        )
        raise AirGapViolation(msg, code="AIR_GAP_EGRESS_DENIED")


class AIProviderConfigService:
    """Service managing envelope-encrypted AI provider configurations and air-gap policy."""

    def __init__(
        self,
        session: AsyncSession,
        kek_provider: KekProvider | None = None,
    ) -> None:
        """Initialize service with active database session and KEK provider."""
        self._session = session
        self._kek = kek_provider if kek_provider is not None else _DEFAULT_KEK_FALLBACK

    @staticmethod
    def _seal_key_material(
        config_id: uuid.UUID,
        workspace_id: uuid.UUID,
        provider_kind: str,
        api_key: bytearray | bytes | str,
        kek_provider: KekProvider,
    ) -> tuple[bytes, bytes, bytes, str]:
        """Wrap plaintext API key using AES-256-GCM envelope encryption and zero source bytes."""
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
        kek_provider: KekProvider,
    ) -> bytearray:
        """Unwrap and authenticate encrypted API key returning a mutable bytearray."""
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
        _check_air_gap(provider_kind, air_gap_mode=air_gap_mode)

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
        is_enabled: bool | None = None,
        air_gap_mode: bool | None = None,
    ) -> AIProviderConfig:
        """Update an existing AI provider configuration."""
        config = await self.get_config(config_id)
        if config is None:
            msg = f"AIProviderConfig {config_id} not found"
            raise AIConfigNotFoundError(msg)

        if air_gap_mode is not None:
            _check_air_gap(config.provider_kind, air_gap_mode=air_gap_mode)

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

        if api_key is not None:
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
