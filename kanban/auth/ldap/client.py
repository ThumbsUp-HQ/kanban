# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""TLS-Hard minimal LDAPv3 client enforcing TLS 1.2+ and SPKI pinning (KB-P2-07)."""

from __future__ import annotations

import asyncio
import hashlib
import ssl
import urllib.parse
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, Self

from cryptography import x509
from cryptography.hazmat.primitives import serialization

from kanban.auth.ldap.asn1_ber import (
    MAX_BER_MESSAGE_SIZE,
    RESULT_CODE_SUCCESS,
    LdapError,
    LdapProtocolError,
    build_bind_request,
    build_search_request,
    build_starttls_request,
    build_unbind_request,
    decode_ldap_message,
    read_ber_packet,
)

if TYPE_CHECKING:
    from types import TracebackType

    from kanban.auth.ldap.config import LdapCardConfig
    from kanban.auth.ldap.escape import FilterNode

__all__ = [
    "DEFAULT_CONNECT_TIMEOUT",
    "DEFAULT_OP_TIMEOUT",
    "DEFAULT_TOTAL_TIMEOUT",
    "LdapBindError",
    "LdapError",
    "LdapProtocolError",
    "LdapSearchError",
    "LdapTlsError",
    "LdapTlsHardClient",
    "SearchEntry",
]

DEFAULT_CONNECT_TIMEOUT: Final[float] = 3.0
DEFAULT_OP_TIMEOUT: Final[float] = 5.0
DEFAULT_TOTAL_TIMEOUT: Final[float] = 8.0
DEFAULT_LDAP_PORT: Final[int] = 389
DEFAULT_LDAPS_PORT: Final[int] = 636


class LdapTlsError(LdapError):
    """Raised on TLS handshake failure, downgrade attempt, or SPKI pin mismatch."""


class LdapBindError(LdapError):
    """Raised on LDAP simple bind failure (e.g. invalid credentials)."""


class LdapSearchError(LdapError):
    """Raised on LDAP search operation failure."""


@dataclass(frozen=True, slots=True)
class SearchEntry:
    """Represents an LDAP search result entry."""

    dn: str
    attributes: dict[str, list[bytes]]


def _raise_invalid_starttls_op(op_name: str) -> None:
    msg = f"Expected extendedResp for StartTLS, got '{op_name}'"
    raise LdapProtocolError(msg)


def _raise_starttls_rejected(result_code: int, diag: str) -> None:
    msg = f"StartTLS rejected by server (resultCode {result_code}): {diag}"
    raise LdapTlsError(msg)


class LdapTlsHardClient:
    """Hardened minimal LDAPv3 client.

    Guarantees that zero BindRequest bytes can ever traverse an unencrypted transport,
    enforces TLS >= 1.2, validates CA certificates, and verifies SPKI SHA-256 public-key pins.
    """

    def __init__(
        self,
        config: LdapCardConfig,
        unix_socket_path: str | None = None,
        op_timeout: float = DEFAULT_OP_TIMEOUT,
    ) -> None:
        """Initialize client with provider configuration and optional test socket override."""
        self._config = config
        self._unix_socket_path = unix_socket_path
        self._op_timeout = op_timeout
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._tls_established: bool = False
        self._verified_spki_sha256: str | None = None
        self._msg_id_counter: int = 0

    @property
    def is_connected(self) -> bool:
        """Return True if connection is open and active."""
        return self._writer is not None and not self._writer.is_closing()

    @property
    def is_tls_established(self) -> bool:
        """Return True if TLS 1.2+ has been verified and established."""
        return self._tls_established

    @property
    def verified_spki_sha256(self) -> str | None:
        """Return verified SPKI SHA-256 hex digest of the peer certificate."""
        return self._verified_spki_sha256

    def _next_msg_id(self) -> int:
        """Allocate next sequential LDAP message ID."""
        self._msg_id_counter += 1
        return self._msg_id_counter

    def _create_ssl_context(self) -> ssl.SSLContext:
        """Create hardened SSL context enforcing TLS 1.2+ and certificate verification."""
        if self._config.ca_cert_pem:
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            ctx.minimum_version = ssl.TLSVersion.TLSv1_2
            ctx.check_hostname = True
            ctx.verify_mode = ssl.CERT_REQUIRED
            ctx.load_verify_locations(cadata=self._config.ca_cert_pem)
        else:
            ctx = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
            ctx.minimum_version = ssl.TLSVersion.TLSv1_2
            ctx.check_hostname = True
            ctx.verify_mode = ssl.CERT_REQUIRED
        return ctx

    def _verify_spki_pin(self, writer: asyncio.StreamWriter) -> None:
        """Verify peer leaf certificate SPKI SHA-256 digest prior to sending any credentials."""
        ssl_obj = writer.get_extra_info("ssl_object")
        if ssl_obj is None:
            msg = "TLS object not found on secure transport"
            raise LdapTlsError(msg)

        der_cert = ssl_obj.getpeercert(binary_form=True)
        if not der_cert:
            msg = "Failed to retrieve peer certificate in binary form"
            raise LdapTlsError(msg)

        cert = x509.load_der_x509_certificate(der_cert)
        spki_der = cert.public_key().public_bytes(
            serialization.Encoding.DER,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        spki_digest = hashlib.sha256(spki_der).hexdigest().lower()
        self._verified_spki_sha256 = spki_digest

        if self._config.spki_sha256_pins:
            valid_pins = [p.lower() for p in self._config.spki_sha256_pins]
            if spki_digest not in valid_pins:
                msg = f"SPKI_PIN_MISMATCH: peer digest '{spki_digest}' not in approved pins"
                raise LdapTlsError(msg)

    async def _connect_ldaps(self, host: str, port: int) -> None:
        """Connect directly over TLS 1.2+."""
        ssl_ctx = self._create_ssl_context()
        if self._unix_socket_path:
            reader, writer = await asyncio.wait_for(
                asyncio.open_unix_connection(
                    self._unix_socket_path,
                    ssl=ssl_ctx,
                    server_hostname=host,
                ),
                timeout=DEFAULT_CONNECT_TIMEOUT,
            )
        else:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port, ssl=ssl_ctx, server_hostname=host),
                timeout=DEFAULT_CONNECT_TIMEOUT,
            )
        self._reader = reader
        self._writer = writer
        self._tls_established = True
        self._verify_spki_pin(writer)

    async def _connect_starttls(self, host: str, port: int) -> None:
        """Connect over plain TCP, send StartTLS, and upgrade before any bind."""
        if self._unix_socket_path:
            reader, writer = await asyncio.wait_for(
                asyncio.open_unix_connection(self._unix_socket_path),
                timeout=DEFAULT_CONNECT_TIMEOUT,
            )
        else:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port),
                timeout=DEFAULT_CONNECT_TIMEOUT,
            )
        self._reader = reader
        self._writer = writer
        self._tls_established = False

        # Send StartTLS extended operation as sequential messageID
        starttls_msg_id = self._next_msg_id()
        starttls_bytes = build_starttls_request(starttls_msg_id)
        async with asyncio.timeout(self._op_timeout):
            writer.write(starttls_bytes)
            await writer.drain()
            resp_bytes = await read_ber_packet(reader, MAX_BER_MESSAGE_SIZE)

        resp_msg_id, op_name, op_val = decode_ldap_message(resp_bytes)
        if resp_msg_id != starttls_msg_id:
            msg = (
                f"Mismatched messageID for StartTLS: expected {starttls_msg_id}, got {resp_msg_id}"
            )
            raise LdapProtocolError(msg)
        if op_name != "extendedResp":
            _raise_invalid_starttls_op(op_name)

        result_code = int(op_val["resultCode"])
        if result_code != RESULT_CODE_SUCCESS:
            diag = str(op_val["diagnosticMessage"])
            _raise_starttls_rejected(result_code, diag)

        # Check buffer before upgrade (CVE-2011-0411 plaintext injection prevention)
        if (hasattr(reader, "_buffer") and len(reader._buffer) > 0) or reader.at_eof():  # noqa: SLF001
            msg = "STARTTLS_BUFFER_INJECTION: unexpected plain bytes or EOF after StartTLS response"
            raise LdapTlsError(msg)

        # Upgrade plain transport to TLS 1.2+ using StreamWriter.start_tls (Python 3.12 API)
        ssl_ctx = self._create_ssl_context()
        async with asyncio.timeout(self._op_timeout):
            await writer.start_tls(ssl_ctx, server_hostname=host)

        # Re-check buffer after upgrade
        if hasattr(reader, "_buffer") and len(reader._buffer) > 0:  # noqa: SLF001
            msg = "STARTTLS_BUFFER_INJECTION: unexpected bytes in buffer after TLS upgrade"
            raise LdapTlsError(msg)

        self._tls_established = True
        self._verify_spki_pin(writer)

    async def connect(self) -> None:
        """Establish connection and enforce TLS_HARD and SPKI pinning prior to any bind."""
        parsed = urllib.parse.urlsplit(self._config.url)
        host = parsed.hostname or "localhost"
        port = parsed.port or (
            DEFAULT_LDAPS_PORT if self._config.transport_mode == "ldaps" else DEFAULT_LDAP_PORT
        )

        try:
            if self._config.transport_mode == "ldaps":
                await self._connect_ldaps(host, port)
            else:
                await self._connect_starttls(host, port)
        except Exception:
            await self.close()
            raise

    async def bind(self, bind_dn: str, password_bytes: bytes | bytearray) -> None:
        """Execute simple BindRequest over verified TLS connection."""
        if not self._tls_established:
            msg = "TLS_HARD invariant violation: TLS not established prior to bind"
            raise LdapTlsError(msg)
        if self._writer is None or self._reader is None:
            msg = "Client is not connected"
            raise LdapError(msg)
        if not password_bytes or len(password_bytes) == 0:
            msg = "Empty password simple bind is strictly prohibited"
            raise LdapBindError(msg)

        raw_pwd = bytes(password_bytes)
        req_msg_id = self._next_msg_id()
        req_bytes = build_bind_request(req_msg_id, bind_dn, raw_pwd)
        del raw_pwd

        async with asyncio.timeout(self._op_timeout):
            self._writer.write(req_bytes)
            await self._writer.drain()
            resp_bytes = await read_ber_packet(self._reader, MAX_BER_MESSAGE_SIZE)

        resp_msg_id, op_name, op_val = decode_ldap_message(resp_bytes)
        if resp_msg_id != req_msg_id:
            msg = f"Mismatched messageID: expected {req_msg_id}, got {resp_msg_id}"
            raise LdapProtocolError(msg)
        if op_name != "bindResponse":
            msg = f"Expected bindResponse, got '{op_name}'"
            raise LdapProtocolError(msg)

        result_code = int(op_val["resultCode"])
        if result_code != RESULT_CODE_SUCCESS:
            diag = str(op_val["diagnosticMessage"])
            msg = f"Bind failed with resultCode {result_code}: {diag}"
            raise LdapBindError(msg)

    async def search(  # noqa: C901
        self,
        base_dn: str,
        filter_node_or_str: FilterNode | str,
        attributes: list[str],
        size_limit: int = 2,
        time_limit: int = 5,
    ) -> list[SearchEntry]:
        """Execute SearchRequest with wholeSubtree scope and neverDerefAliases."""
        if not self._tls_established:
            msg = "TLS_HARD invariant violation: TLS not established prior to search"
            raise LdapTlsError(msg)
        if self._writer is None or self._reader is None:
            msg = "Client is not connected"
            raise LdapError(msg)

        req_msg_id = self._next_msg_id()
        req_bytes = build_search_request(
            req_msg_id,
            base_dn,
            filter_node_or_str,
            attributes,
            size_limit=size_limit,
            time_limit=time_limit,
        )
        async with asyncio.timeout(self._op_timeout):
            self._writer.write(req_bytes)
            await self._writer.drain()

        entries: list[SearchEntry] = []
        while True:
            async with asyncio.timeout(self._op_timeout):
                resp_packet = await read_ber_packet(self._reader, MAX_BER_MESSAGE_SIZE)
            resp_msg_id, op_name, op_val = decode_ldap_message(resp_packet)
            if resp_msg_id != req_msg_id:
                msg = f"Mismatched messageID in search: expected {req_msg_id}, got {resp_msg_id}"
                raise LdapProtocolError(msg)
            if op_name == "searchResEntry":
                if len(entries) >= size_limit:
                    msg = f"SIZE_LIMIT_EXCEEDED: server returned more than {size_limit} entries"
                    raise LdapSearchError(msg)
                entry_dn = str(op_val["objectName"])
                attr_dict: dict[str, list[bytes]] = {}
                for item in op_val["attributes"]:
                    attr_name = str(item["type"]).lower()
                    vals = [bytes(v.asOctets()) for v in item["vals"]]
                    attr_dict[attr_name] = vals
                entries.append(SearchEntry(dn=entry_dn, attributes=attr_dict))
            elif op_name == "searchResDone":
                result_code = int(op_val["resultCode"])
                if result_code != RESULT_CODE_SUCCESS:
                    diag = str(op_val["diagnosticMessage"])
                    msg = f"Search failed with resultCode {result_code}: {diag}"
                    raise LdapSearchError(msg)
                break
            elif op_name == "searchResRef":
                # Ignore referrals per follow_referrals=False specification
                continue
            else:
                msg = f"Unexpected search response operation: {op_name}"
                raise LdapProtocolError(msg)

        return entries

    async def unbind(self) -> None:
        """Send UnbindRequest and close transport."""
        if self._writer is not None and not self._writer.is_closing():
            try:
                req_bytes = build_unbind_request(self._next_msg_id())
                self._writer.write(req_bytes)
                await self._writer.drain()
            except (TimeoutError, OSError):
                pass
        await self.close()

    async def close(self) -> None:
        """Close connection and reset TLS state."""
        if self._writer is not None:
            try:
                self._writer.close()
                await self._writer.wait_closed()
            except (TimeoutError, OSError):
                pass
            finally:
                self._writer = None
                self._reader = None
                self._tls_established = False

    async def __aenter__(self) -> Self:
        """Async context manager entry: connects and verifies TLS."""
        await self.connect()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Async context manager exit: performs unbind and teardown."""
        del exc_type, exc_val, exc_tb
        await self.unbind()
