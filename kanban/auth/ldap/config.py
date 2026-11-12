# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""LDAP and StartTLS authentication card configuration schema (KB-P2-07)."""

from __future__ import annotations

import ipaddress
import os
import re
import urllib.parse
from typing import Final, Literal

from cryptography import x509
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

MAX_PEM_BYTES: Final[int] = 65536
MAX_SPKI_PINS: Final[int] = 4
MAX_DN_LENGTH: Final[int] = 512
MAX_GROUP_MAPPINGS: Final[int] = 200
MAX_GROUP_NAME_LENGTH: Final[int] = 200
PIN_REGEX: Final[re.Pattern[str]] = re.compile(r"^[0-9a-f]{64}$")
URL_REGEX: Final[re.Pattern[str]] = re.compile(r"^(ldaps|ldap)://[A-Za-z0-9.-]+(:[0-9]{1,5})?$")


def _raise_pem_empty() -> None:
    msg = "ca_cert_pem contains no valid X.509 certificates"
    raise ValueError(msg)


class LdapCardConfig(BaseModel):
    """Card public_config schema for LDAP/StartTLS provider cards (S4.2, KB-P2-07)."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["LDAP"] = "LDAP"
    url: str
    transport_mode: Literal["ldaps", "starttls"]
    ca_cert_pem: str | None = None
    spki_sha256_pins: list[str] = Field(default_factory=list)
    service_bind_dn: str | None = None
    base_dn: str = Field(min_length=1, max_length=MAX_DN_LENGTH)
    user_search_filter: str = "(&(objectClass=person)(uid={username}))"
    subject_attribute: str = "entryUUID"
    email_attribute: str = "mail"
    display_name_attribute: str = "cn"
    member_of_attribute: str = "memberOf"
    group_dn_map: dict[str, str] = Field(default_factory=dict)
    timeout_seconds: float = Field(default=5.0, ge=1.0, le=15.0)

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        """Validate LDAP URL format and reject dangerous loopback/link-local targets."""
        cleaned = v.strip()
        if not URL_REGEX.match(cleaned):
            msg = "url must match ^(ldaps|ldap)://[A-Za-z0-9.-]+(:[0-9]{1,5})?$"
            raise ValueError(msg)

        parsed = urllib.parse.urlsplit(cleaned)
        hostname = parsed.hostname
        if not hostname:
            msg = "url must specify a valid hostname"
            raise ValueError(msg)

        allow_private = (
            os.environ.get("KANBAN_AUTH_EGRESS_ALLOW_PRIVATE", "false").lower() == "true"
        )

        if hostname.lower() in ("localhost", "localhost.localdomain") and not allow_private:
            msg = f"url targets loopback hostname '{hostname}'"
            raise ValueError(msg)

        try:
            ip = ipaddress.ip_address(hostname)
        except ValueError:
            return cleaned

        if (ip.is_loopback or ip.is_link_local) and not allow_private:
            msg = f"url targets prohibited loopback or link-local IP '{ip}'"
            raise ValueError(msg)

        return cleaned

    @field_validator("ca_cert_pem")
    @classmethod
    def validate_ca_cert_pem(cls, v: str | None) -> str | None:
        """Validate PEM certificate bundle size and parseable X.509 format."""
        if v is None:
            return None
        cleaned = v.strip()
        if not cleaned:
            return None
        pem_bytes = cleaned.encode("utf-8")
        if len(pem_bytes) > MAX_PEM_BYTES:
            msg = f"ca_cert_pem must not exceed {MAX_PEM_BYTES} bytes"
            raise ValueError(msg)
        try:
            certs = x509.load_pem_x509_certificates(pem_bytes)
            if not certs:
                _raise_pem_empty()
        except Exception as exc:
            msg = f"ca_cert_pem contains invalid X.509 PEM data: {exc}"
            raise ValueError(msg) from exc
        return cleaned

    @field_validator("spki_sha256_pins")
    @classmethod
    def validate_spki_pins(cls, v: list[str]) -> list[str]:
        """Validate lowercase 64-hex SHA-256 SPKI digests."""
        if len(v) > MAX_SPKI_PINS:
            msg = f"spki_sha256_pins cannot exceed {MAX_SPKI_PINS} pins"
            raise ValueError(msg)
        normalized: list[str] = []
        for pin in v:
            lowered = pin.strip().lower()
            if not PIN_REGEX.match(lowered):
                msg = (
                    f"Invalid SPKI SHA-256 pin '{pin}': must be a 64-character lowercase hex digest"
                )
                raise ValueError(msg)
            normalized.append(lowered)
        return normalized

    @field_validator("service_bind_dn")
    @classmethod
    def validate_service_bind_dn(cls, v: str | None) -> str | None:
        """Validate service bind DN length."""
        if v is None:
            return None
        cleaned = v.strip()
        if not cleaned:
            return None
        if len(cleaned) > MAX_DN_LENGTH:
            msg = f"service_bind_dn cannot exceed {MAX_DN_LENGTH} characters"
            raise ValueError(msg)
        return cleaned

    @field_validator("user_search_filter")
    @classmethod
    def validate_search_filter(cls, v: str) -> str:
        """Validate filter contains username placeholder once and has balanced parentheses."""
        cleaned = v.strip()
        if cleaned.count("{username}") != 1:
            msg = "user_search_filter must contain exactly one '{username}' placeholder"
            raise ValueError(msg)
        depth = 0
        for ch in cleaned:
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth < 0:
                    msg = "user_search_filter has unbalanced parentheses"
                    raise ValueError(msg)
        if depth != 0:
            msg = "user_search_filter has unbalanced parentheses"
            raise ValueError(msg)
        return cleaned

    @field_validator("group_dn_map")
    @classmethod
    def validate_group_dn_map(cls, v: dict[str, str]) -> dict[str, str]:
        """Validate group DN mapping entry count and string bounds."""
        if len(v) > MAX_GROUP_MAPPINGS:
            msg = f"group_dn_map cannot contain more than {MAX_GROUP_MAPPINGS} mappings"
            raise ValueError(msg)
        result: dict[str, str] = {}
        for dn, group_name in v.items():
            cleaned_dn = dn.strip()
            cleaned_name = group_name.strip()
            if not cleaned_dn or len(cleaned_dn) > MAX_DN_LENGTH:
                msg = f"group_dn_map DN '{dn}' must be between 1 and {MAX_DN_LENGTH} characters"
                raise ValueError(msg)
            if not cleaned_name or len(cleaned_name) > MAX_GROUP_NAME_LENGTH:
                msg = (
                    f"group_dn_map target group name '{group_name}' "
                    f"must be between 1 and {MAX_GROUP_NAME_LENGTH} characters"
                )
                raise ValueError(msg)
            result[cleaned_dn] = cleaned_name
        return result

    @model_validator(mode="after")
    def validate_transport_scheme_pairing(self) -> LdapCardConfig:
        """Ensure scheme and transport_mode pair strictly (ldaps->ldaps, ldap->starttls)."""
        parsed = urllib.parse.urlsplit(self.url)
        scheme = parsed.scheme.lower()
        if scheme == "ldaps" and self.transport_mode != "ldaps":
            msg = "ldaps:// scheme requires transport_mode='ldaps'"
            raise ValueError(msg)
        if scheme == "ldap" and self.transport_mode != "starttls":
            msg = "ldap:// scheme requires transport_mode='starttls' (cleartext bind is prohibited)"
            raise ValueError(msg)
        return self
