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
from kanban.security.headers import CSP_POLICY, SecurityHeadersMiddleware
from kanban.security.permissions import (
    SCOPE_CAPABILITY_MAP,
    Capability,
    capabilities_to_names,
    evaluate_capabilities,
    parse_token_scope_mask,
    require_capability,
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
    "SCOPE_CAPABILITY_MAP",
    "AccessManifest",
    "Capability",
    "InheritedScope",
    "KeyMaterial",
    "KeyMaterialError",
    "ManifestAgent",
    "ManifestDenyOverride",
    "ManifestGroup",
    "ManifestRedactedEntry",
    "ManifestUser",
    "ScrubFinding",
    "ScrubResult",
    "SecretKind",
    "SecurityHeadersMiddleware",
    "build_access_manifest",
    "capabilities_to_names",
    "derive_subkey",
    "evaluate_capabilities",
    "load_key_material",
    "outbound_secret_scrubber",
    "parse_token_scope_mask",
    "require_capability",
    "scrub_text",
]


def __getattr__(name: str) -> Any:  # noqa: ANN401
    """Lazy import keys module to prevent premature import during test setup."""
    if name in ("KeyMaterial", "KeyMaterialError", "load_key_material", "derive_subkey"):
        import kanban.security.keys as _keys  # noqa: PLC0415

        return getattr(_keys, name)
    msg = f"module {__name__!r} has no attribute {name!r}"
    raise AttributeError(msg)
