# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
# ruff: noqa: ICN001, PLR0917, D107, FBT001, FBT002, PTH108, PTH110, C901, PLR0912, PLR0915, BLE001, SIM113, SIM105, ASYNC240, E501
"""In-memory TLS/StartTLS LDAPv3 mock server for offline unit tests (KB-P2-07)."""

from __future__ import annotations

import asyncio
import datetime
import hashlib
import os
import ssl
import tempfile
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Final, Self
from uuid import uuid4

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from pyasn1.codec.ber import encoder

from kanban.auth.ldap.asn1_ber import (
    MAX_BER_MESSAGE_SIZE,
    RESULT_CODE_INVALID_CREDENTIALS,
    RESULT_CODE_SUCCESS,
    RESULT_CODE_UNAVAILABLE,
    STARTTLS_OID,
    AttributeValue,
    AttributeValues,
    BindResponse,
    ExtendedResponse,
    LDAPMessage,
    PartialAttribute,
    PartialAttributeList,
    ProtocolOp,
    SearchResultDone,
    SearchResultEntry,
    decode_ldap_message,
    read_ber_packet,
)

if TYPE_CHECKING:
    from types import TracebackType

__all__ = [
    "FakeLdapDirectory",
    "FakeLdapServer",
    "LdapTestCerts",
    "generate_ldap_test_certs",
]

CERT_VALIDITY_DAYS: Final[int] = 2


@dataclass(frozen=True, slots=True)
class LdapTestCerts:
    """X.509 certificate material and SPKI SHA-256 public-key pins."""

    ca_pem: str
    server_cert_pem: str
    server_key_pem: str
    spki_sha256: str
    mismatch_spki_sha256: str
    mismatch_server_cert_pem: str
    mismatch_server_key_pem: str


def generate_ldap_test_certs() -> LdapTestCerts:
    """Generate self-signed root CA and leaf certificates for TLS/StartTLS tests."""
    # 1. Root CA
    ca_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Kanban Test LDAP CA")])
    now = datetime.datetime.now(datetime.UTC)
    ca_cert = (
        x509.CertificateBuilder()
        .subject_name(ca_name)
        .issuer_name(ca_name)
        .public_key(ca_key.public_key())
        .serial_number(1)
        .not_valid_before(now)
        .not_valid_after(now + datetime.timedelta(days=CERT_VALIDITY_DAYS))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(ca_key, hashes.SHA256())
    )
    ca_pem = ca_cert.public_bytes(serialization.Encoding.PEM).decode("ascii")

    # 2. Main Server Leaf Cert
    srv_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    srv_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
    srv_cert = (
        x509.CertificateBuilder()
        .subject_name(srv_name)
        .issuer_name(ca_name)
        .public_key(srv_key.public_key())
        .serial_number(2)
        .not_valid_before(now)
        .not_valid_after(now + datetime.timedelta(days=CERT_VALIDITY_DAYS))
        .sign(ca_key, hashes.SHA256())
    )
    srv_pem = srv_cert.public_bytes(serialization.Encoding.PEM).decode("ascii")
    srv_key_pem = srv_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption(),
    ).decode("ascii")

    spki_der = srv_cert.public_key().public_bytes(
        serialization.Encoding.DER,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    spki_sha256 = hashlib.sha256(spki_der).hexdigest().lower()

    # 3. Mismatch Server Leaf Cert (Valid CA signature, different public key)
    rot_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    rot_cert = (
        x509.CertificateBuilder()
        .subject_name(srv_name)
        .issuer_name(ca_name)
        .public_key(rot_key.public_key())
        .serial_number(3)
        .not_valid_before(now)
        .not_valid_after(now + datetime.timedelta(days=CERT_VALIDITY_DAYS))
        .sign(ca_key, hashes.SHA256())
    )
    rot_pem = rot_cert.public_bytes(serialization.Encoding.PEM).decode("ascii")
    rot_key_pem = rot_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption(),
    ).decode("ascii")

    rot_spki_der = rot_cert.public_key().public_bytes(
        serialization.Encoding.DER,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    rot_spki_sha256 = hashlib.sha256(rot_spki_der).hexdigest().lower()

    return LdapTestCerts(
        ca_pem=ca_pem,
        server_cert_pem=srv_pem,
        server_key_pem=srv_key_pem,
        spki_sha256=spki_sha256,
        mismatch_spki_sha256=rot_spki_sha256,
        mismatch_server_cert_pem=rot_pem,
        mismatch_server_key_pem=rot_key_pem,
    )


@dataclass
class FakeLdapDirectory:
    """In-memory directory database for LDAP tests."""

    # Map of lowercase DN -> {attr_name: [bytes]}
    entries: dict[str, dict[str, list[bytes]]] = field(default_factory=dict)
    # Map of lowercase DN -> password str
    passwords: dict[str, str] = field(default_factory=dict)


def _make_extended_response(msg_id: int, result_code: int = 0, diag: str = "") -> bytes:
    resp = ExtendedResponse()
    resp["resultCode"] = result_code
    resp["matchedDN"] = ""
    resp["diagnosticMessage"] = diag
    op = ProtocolOp()
    op["extendedResp"] = resp
    msg = LDAPMessage()
    msg["messageID"] = msg_id
    msg["protocolOp"] = op
    return bytes(encoder.encode(msg))


def _make_bind_response(msg_id: int, result_code: int = 0, diag: str = "") -> bytes:
    resp = BindResponse()
    resp["resultCode"] = result_code
    resp["matchedDN"] = ""
    resp["diagnosticMessage"] = diag
    op = ProtocolOp()
    op["bindResponse"] = resp
    msg = LDAPMessage()
    msg["messageID"] = msg_id
    msg["protocolOp"] = op
    return bytes(encoder.encode(msg))


def _make_search_entry(msg_id: int, dn: str, attributes: dict[str, list[bytes]]) -> bytes:
    entry = SearchResultEntry()
    entry["objectName"] = dn
    attr_list = PartialAttributeList()
    for idx, (attr_name, vals) in enumerate(attributes.items()):
        pa = PartialAttribute()
        pa["type"] = attr_name
        val_set = AttributeValues()
        for v_idx, v in enumerate(vals):
            val_set.setComponentByPosition(v_idx, AttributeValue(v))
        pa["vals"] = val_set
        attr_list.setComponentByPosition(idx, pa)
    entry["attributes"] = attr_list
    op = ProtocolOp()
    op["searchResEntry"] = entry
    msg = LDAPMessage()
    msg["messageID"] = msg_id
    msg["protocolOp"] = op
    return bytes(encoder.encode(msg))


def _make_search_done(msg_id: int, result_code: int = 0, diag: str = "") -> bytes:
    done = SearchResultDone()
    done["resultCode"] = result_code
    done["matchedDN"] = ""
    done["diagnosticMessage"] = diag
    op = ProtocolOp()
    op["searchResDone"] = done
    msg = LDAPMessage()
    msg["messageID"] = msg_id
    msg["protocolOp"] = op
    return bytes(encoder.encode(msg))


class FakeLdapServer:
    """Mock LDAPv3 server supporting LDAPS and StartTLS over Unix domain sockets."""

    def __init__(  # noqa: PLR0913
        self,
        certs: LdapTestCerts,
        mode: str = "ldaps",
        reject_starttls: bool = False,
        use_mismatched_cert: bool = False,
        min_tls_version: ssl.TLSVersion = ssl.TLSVersion.TLSv1_2,
        max_tls_version: ssl.TLSVersion = ssl.TLSVersion.TLSv1_3,
        accept_anonymous_bind: bool = False,
        oversized_response_bytes: int = 0,
    ) -> None:
        self.certs = certs
        self.mode = mode
        self.reject_starttls = reject_starttls
        self.use_mismatched_cert = use_mismatched_cert
        self.min_tls_version = min_tls_version
        self.max_tls_version = max_tls_version
        self.accept_anonymous_bind = accept_anonymous_bind
        self.oversized_response_bytes = oversized_response_bytes

        self.directory = FakeLdapDirectory()
        self.sock_path = f"/tmp/fake_ldap_{uuid4().hex[:12]}.sock"
        self._server: asyncio.Server | None = None

        # Spy metrics for test verification
        self.raw_pre_tls_bytes = bytearray()
        self.raw_post_tls_bytes = bytearray()
        self.deref_aliases_seen: list[int] = []
        self.bind_calls: list[tuple[str, bytes]] = []

    def _create_server_ssl_context(self) -> ssl.SSLContext:
        ctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        ctx.minimum_version = self.min_tls_version
        ctx.maximum_version = self.max_tls_version

        cert_pem = (
            self.certs.mismatch_server_cert_pem
            if self.use_mismatched_cert
            else self.certs.server_cert_pem
        )
        key_pem = (
            self.certs.mismatch_server_key_pem
            if self.use_mismatched_cert
            else self.certs.server_key_pem
        )

        with (
            tempfile.NamedTemporaryFile("wb", delete=False) as f_cert,
            tempfile.NamedTemporaryFile("wb", delete=False) as f_key,
        ):
            f_cert.write(cert_pem.encode("utf-8"))
            f_cert.flush()
            f_key.write(key_pem.encode("utf-8"))
            f_key.flush()
            ctx.load_cert_chain(f_cert.name, f_key.name)
            os.unlink(f_cert.name)
            os.unlink(f_key.name)

        return ctx

    async def _handle_connection(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        """Handle incoming LDAP connection session."""
        is_tls = self.mode == "ldaps"

        try:
            while not reader.at_eof():
                # Read packet
                try:
                    packet = await read_ber_packet(reader, max_bytes=MAX_BER_MESSAGE_SIZE * 2)
                except asyncio.IncompleteReadError:
                    break
                except Exception:
                    break

                if not is_tls:
                    self.raw_pre_tls_bytes.extend(packet)
                else:
                    self.raw_post_tls_bytes.extend(packet)

                # Return oversized response if configured for testing
                if self.oversized_response_bytes > 0:
                    oversized_payload = (
                        bytes([0x30]) + bytes([0x84, 0x00, 0x04, 0x00, 0x01]) + b"\x00" * 262145
                    )
                    writer.write(oversized_payload)
                    await writer.drain()
                    break

                msg_id, op_name, op_val = decode_ldap_message(packet)

                if op_name == "extendedReq":
                    oid = str(op_val["requestName"])
                    if oid == STARTTLS_OID:
                        if self.reject_starttls:
                            resp = _make_extended_response(
                                msg_id,
                                result_code=RESULT_CODE_UNAVAILABLE,
                                diag="StartTLS unavailable",
                            )
                            writer.write(resp)
                            await writer.drain()
                        else:
                            resp = _make_extended_response(msg_id, result_code=RESULT_CODE_SUCCESS)
                            writer.write(resp)
                            await writer.drain()

                            # Upgrade transport
                            ssl_ctx = self._create_server_ssl_context()
                            loop = asyncio.get_running_loop()
                            server_transport = writer.transport
                            protocol = server_transport.get_protocol()
                            new_transport = await loop.start_tls(
                                server_transport,
                                protocol,
                                ssl_ctx,
                                server_side=True,
                            )
                            writer._transport = new_transport  # type: ignore[attr-defined] # noqa: SLF001
                            is_tls = True

                elif op_name == "bindRequest":
                    bind_dn = str(op_val["name"]).lower()
                    auth_bytes = bytes(op_val["authentication"].asOctets())
                    self.bind_calls.append((bind_dn, auth_bytes))

                    if len(auth_bytes) == 0:
                        if self.accept_anonymous_bind:
                            writer.write(_make_bind_response(msg_id, RESULT_CODE_SUCCESS))
                        else:
                            writer.write(
                                _make_bind_response(
                                    msg_id,
                                    RESULT_CODE_INVALID_CREDENTIALS,
                                    "Anonymous bind prohibited",
                                )
                            )
                    else:
                        pwd_str = auth_bytes.decode("utf-8", errors="replace")
                        expected_pwd = self.directory.passwords.get(bind_dn)
                        if expected_pwd is not None and expected_pwd == pwd_str:
                            writer.write(_make_bind_response(msg_id, RESULT_CODE_SUCCESS))
                        else:
                            writer.write(
                                _make_bind_response(
                                    msg_id,
                                    RESULT_CODE_INVALID_CREDENTIALS,
                                    "Invalid credentials",
                                )
                            )
                    await writer.drain()

                elif op_name == "searchRequest":
                    deref = int(op_val["derefAliases"])
                    self.deref_aliases_seen.append(deref)
                    size_limit = int(op_val["sizeLimit"])

                    # Match filter against directory entries
                    # Extract filter string representation or check attributes
                    raw_filter_bytes = bytes(op_val["filter"].asOctets())
                    matched_entries: list[tuple[str, dict[str, list[bytes]]]] = []

                    for dn, attrs in self.directory.entries.items():
                        # Match identity attributes (uid, cn, mail, sAMAccountName) against filter bytes
                        matched = False
                        for attr_name, vals in attrs.items():
                            if attr_name.lower() in (
                                "uid",
                                "cn",
                                "mail",
                                "samaccountname",
                                "entryuuid",
                            ):
                                for v in vals:
                                    if v and v in raw_filter_bytes:
                                        matched = True
                                        break
                            if matched:
                                break
                        if matched:
                            matched_entries.append((dn, attrs))

                    # Send matched entries up to sizeLimit
                    count = 0
                    for dn, attrs in matched_entries:
                        if size_limit > 0 and count >= size_limit:
                            break
                        writer.write(_make_search_entry(msg_id, dn, attrs))
                        await writer.drain()
                        count += 1

                    writer.write(_make_search_done(msg_id, RESULT_CODE_SUCCESS))
                    await writer.drain()

                elif op_name == "unbindRequest":
                    break

        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:  # noqa: S110
                pass

    async def start(self) -> None:
        """Start Unix domain socket server."""
        if self.mode == "ldaps":
            ssl_ctx = self._create_server_ssl_context()
            self._server = await asyncio.start_unix_server(
                self._handle_connection,
                path=self.sock_path,
                ssl=ssl_ctx,
            )
        else:
            self._server = await asyncio.start_unix_server(
                self._handle_connection,
                path=self.sock_path,
            )

    async def stop(self) -> None:
        """Stop server and clean up socket file."""
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
        if os.path.exists(self.sock_path):
            try:
                os.unlink(self.sock_path)
            except OSError:
                pass

    async def __aenter__(self) -> Self:
        """Async context manager entry: starts server."""
        await self.start()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Async context manager exit: stops server."""
        del exc_type, exc_val, exc_tb
        await self.stop()
