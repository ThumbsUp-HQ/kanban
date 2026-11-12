# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""OIDC and OAuth2 authentication module (KB-P2-06)."""

from __future__ import annotations

from kanban.auth.identity import (
    ExternalIdentityAssertion,
    IdentityResolver,
    RejectAllIdentityResolver,
    ResolvedLogin,
)
from kanban.auth.oidc.config import OidcCardConfig
from kanban.auth.oidc.discovery import (
    JwksCache,
    OidcDiscoveryDoc,
    OidcError,
    fetch_discovery,
)
from kanban.auth.oidc.flow import (
    OidcFlow,
    OidcStartResponse,
    build_browser_binding_cookie,
    build_clear_browser_binding_cookie,
    sanitize_return_to,
)
from kanban.auth.oidc.tokens import (
    build_private_key_jwt,
    validate_id_token,
)

__all__ = [
    "ExternalIdentityAssertion",
    "IdentityResolver",
    "JwksCache",
    "OidcCardConfig",
    "OidcDiscoveryDoc",
    "OidcError",
    "OidcFlow",
    "OidcStartResponse",
    "RejectAllIdentityResolver",
    "ResolvedLogin",
    "build_browser_binding_cookie",
    "build_clear_browser_binding_cookie",
    "build_private_key_jwt",
    "fetch_discovery",
    "sanitize_return_to",
    "validate_id_token",
]
