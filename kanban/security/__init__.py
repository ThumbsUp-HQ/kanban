"""Security utilities, key provider, and middleware for the Kanban platform."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from kanban.security.access_manifest import (
    AccessManifest,
    InheritedScope,
    ManifestAgent,
    ManifestDenyOverride,
    ManifestGroup,
    ManifestRedactedEntry,
    ManifestUser,
    build_access_manifest,
)
from kanban.security.envelope import (
    EnvelopeDecryptError,
    EnvelopeInputError,
    KekProvider,
    SealedSecret,
    StaticKekProvider,
    UnknownKekError,
    open_card_secret,
    rewrap_dek,
    seal_card_secret,
)
from kanban.security.headers import CSP_POLICY, SecurityHeadersMiddleware
from kanban.security.permissions import (
    SCOPE_CAPABILITY_MAP,
    Capability,
    capabilities_to_names,
    evaluate_capabilities,
    parse_token_scope_mask,
    require_capability,
)
from kanban.security.push_protection import (
    DEFAULT_PUSH_PROTECTION_CODE,
    PushProtectionMode,
    SecretFinding,
    calculate_shannon_entropy,
    enforce_secret_push_protection,
    is_exempt_token,
    mask_fingerprint,
    redact_text_findings,
    scan_text_for_secrets,
)
from kanban.security.read_taint import (
    TaintGuard,
    TaintRecorder,
    get_taint_guard,
    get_taint_recorder,
)
from kanban.security.scrubber import (
    ScrubFinding,
    ScrubResult,
    SecretKind,
    outbound_secret_scrubber,
    scrub_text,
)

if TYPE_CHECKING:
    from kanban.security.keys import (
        KeyMaterial,
        KeyMaterialError,
        derive_subkey,
        load_key_material,
    )

__all__ = [
    "CSP_POLICY",
    "DEFAULT_PUSH_PROTECTION_CODE",
    "SCOPE_CAPABILITY_MAP",
    "AccessManifest",
    "Capability",
    "EnvelopeDecryptError",
    "EnvelopeInputError",
    "InheritedScope",
    "KekProvider",
    "KeyMaterial",
    "KeyMaterialError",
    "ManifestAgent",
    "ManifestDenyOverride",
    "ManifestGroup",
    "ManifestRedactedEntry",
    "ManifestUser",
    "PushProtectionMode",
    "ScrubFinding",
    "ScrubResult",
    "SealedSecret",
    "SecretFinding",
    "SecretKind",
    "SecurityHeadersMiddleware",
    "StaticKekProvider",
    "TaintGuard",
    "TaintRecorder",
    "UnknownKekError",
    "build_access_manifest",
    "calculate_shannon_entropy",
    "capabilities_to_names",
    "derive_subkey",
    "enforce_secret_push_protection",
    "evaluate_capabilities",
    "get_taint_guard",
    "get_taint_recorder",
    "is_exempt_token",
    "load_key_material",
    "mask_fingerprint",
    "open_card_secret",
    "outbound_secret_scrubber",
    "parse_token_scope_mask",
    "redact_text_findings",
    "require_capability",
    "resolve_client_ip",
    "rewrap_dek",
    "scan_text_for_secrets",
    "scrub_text",
    "seal_card_secret",
]


def __getattr__(name: str) -> Any:  # noqa: ANN401
    """Lazy import keys module to prevent premature import during test setup."""
    if name in ("KeyMaterial", "KeyMaterialError", "load_key_material", "derive_subkey"):
        import kanban.security.keys as _keys  # noqa: PLC0415

        return getattr(_keys, name)
    if name == "resolve_client_ip":
        from kanban.security.client_ip import resolve_client_ip as _rcip  # noqa: PLC0415

        return _rcip
    msg = f"module {__name__!r} has no attribute {name!r}"
    raise AttributeError(msg)
