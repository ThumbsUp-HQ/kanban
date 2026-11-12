# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""OIDC and OAuth2 provider card configuration schema and SSRF validation (KB-P2-06)."""

from __future__ import annotations

import ipaddress
import os
import urllib.parse
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def _validate_safe_url(url_str: str | None, field_name: str) -> str | None:
    """Validate that URL is https and does not target loopback or cloud metadata IPs."""
    if url_str is None:
        return None

    cleaned = url_str.strip()
    parsed = urllib.parse.urlsplit(cleaned)
    if parsed.scheme.lower() != "https":
        msg = f"{field_name} must use the https:// scheme"
        raise ValueError(msg)

    hostname = parsed.hostname
    if not hostname:
        msg = f"{field_name} must specify a valid hostname"
        raise ValueError(msg)

    allow_private = os.environ.get("KANBAN_AUTH_EGRESS_ALLOW_PRIVATE", "false").lower() == "true"

    if hostname.lower() in ("localhost", "localhost.localdomain") and not allow_private:
        msg = f"{field_name} targets loopback hostname '{hostname}'"
        raise ValueError(msg)

    # Check numeric IP addresses
    try:
        ip = ipaddress.ip_address(hostname)
    except ValueError:
        # Domain name, allowed
        return cleaned

    # Check loopback
    if ip.is_loopback and not allow_private:
        msg = f"{field_name} targets loopback IP '{ip}'"
        raise ValueError(msg)

    # Check link-local / AWS metadata (169.254.0.0/16, fe80::/10)
    link_local_v4 = ipaddress.ip_network("169.254.0.0/16")
    link_local_v6 = ipaddress.ip_network("fe80::/10")
    if ip in link_local_v4 or ip in link_local_v6 or ip.is_link_local:
        msg = f"{field_name} targets prohibited link-local or cloud metadata IP '{ip}'"
        raise ValueError(msg)

    return cleaned


AllowedAlg = Literal["RS256", "PS256", "ES256", "EdDSA"]


def _default_allowed_algs() -> list[AllowedAlg]:
    return ["RS256", "ES256"]


class OidcCardConfig(BaseModel):
    """Configuration schema for OIDC and OAuth2 authentication provider cards."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["OIDC", "OAUTH2"]
    issuer: str | None = None
    authorization_endpoint: str | None = None
    token_endpoint: str | None = None
    userinfo_endpoint: str | None = None
    jwks_uri: str | None = None
    client_id: str = Field(min_length=1, max_length=255)
    client_auth: Literal["client_secret_basic", "private_key_jwt"] = "client_secret_basic"
    scopes: list[str] = Field(default_factory=lambda: ["openid", "profile", "email"])
    subject_claim: str = "sub"
    email_claim: str = "email"
    email_verified_claim: str = "email_verified"
    groups_claim: str | None = None
    allowed_algs: list[AllowedAlg] = Field(default_factory=_default_allowed_algs)

    @field_validator(
        "issuer",
        "authorization_endpoint",
        "token_endpoint",
        "userinfo_endpoint",
        "jwks_uri",
        mode="after",
    )
    @classmethod
    def validate_endpoints(cls, v: str | None, info: object) -> str | None:
        """Validate URL scheme and SSRF constraints on endpoints."""
        field_name = getattr(info, "field_name", "endpoint")
        return _validate_safe_url(v, field_name)

    @model_validator(mode="after")
    def validate_kind_requirements(self) -> OidcCardConfig:
        """Validate mandatory endpoints and scopes depending on provider kind."""
        if self.kind == "OIDC":
            if not self.issuer:
                msg = "OIDC provider cards require an 'issuer' endpoint"
                raise ValueError(msg)
            if "openid" not in self.scopes:
                msg = "OIDC provider cards must include 'openid' scope"
                raise ValueError(msg)
        elif self.kind == "OAUTH2":
            if not self.authorization_endpoint:
                msg = "OAuth2 provider cards require an 'authorization_endpoint'"
                raise ValueError(msg)
            if not self.token_endpoint:
                msg = "OAuth2 provider cards require a 'token_endpoint'"
                raise ValueError(msg)
            if not self.userinfo_endpoint:
                msg = "OAuth2 provider cards require a 'userinfo_endpoint'"
                raise ValueError(msg)

        if not self.allowed_algs:
            msg = "allowed_algs cannot be empty"
            raise ValueError(msg)

        return self
