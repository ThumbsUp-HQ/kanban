# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Companion servers for Slice 1 Phase 3 Live Workout (KAN-408).

Provides:
1. Hardened TLS LDAPS server on 127.0.0.1:10636 and StartTLS LDAP on 127.0.0.1:10389.
2. Hardened HTTPS OIDC IdP server on 127.0.0.1:18081.
"""

from __future__ import annotations

import asyncio
import base64
import datetime
import hashlib
import ipaddress
import json
import logging
import os
import secrets
import ssl
import sys
import tempfile
import time
import urllib.parse
from dataclasses import dataclass
from typing import Any

import uvicorn
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from joserfc import jwt
from joserfc.jwk import RSAKey
from fastapi import FastAPI
from fastapi.responses import JSONResponse, RedirectResponse, Response
from starlette.requests import Request

from kanban.auth.ldap.asn1_ber import (
    RESULT_CODE_INVALID_CREDENTIALS,
    RESULT_CODE_SUCCESS,
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

PORT_LDAP_TLS = 10636
PORT_LDAP_PLAIN = 10389
PORT_OIDC = 18081

logger = logging.getLogger("slice1_companions")
logging.basicConfig(level=logging.INFO)


@dataclass(frozen=True)
class CompanionCertificates:
    """Certificate bundle for local loopback companion servers."""

    ca_cert_pem: str
    ca_key_pem: str
    server_cert_pem: str
    server_key_pem: str
    spki_sha256: str
    ca_file: str
    server_cert_file: str
    server_key_file: str


def generate_workout_certificates() -> CompanionCertificates:
    """Generate self-signed Root CA and Server certificate with 127.0.0.1 and localhost SAN."""
    now = datetime.datetime.now(datetime.UTC)
    ca_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Kanban Workout Root CA")])
    ca_cert = (
        x509.CertificateBuilder()
        .subject_name(ca_name)
        .issuer_name(ca_name)
        .public_key(ca_key.public_key())
        .serial_number(1)
        .not_valid_before(now - datetime.timedelta(hours=1))
        .not_valid_after(now + datetime.timedelta(days=7))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(ca_key, hashes.SHA256())
    )
    ca_pem = ca_cert.public_bytes(serialization.Encoding.PEM).decode("ascii")
    ca_key_pem = ca_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption(),
    ).decode("ascii")

    srv_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    srv_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "127.0.0.1")])
    srv_cert = (
        x509.CertificateBuilder()
        .subject_name(srv_name)
        .issuer_name(ca_name)
        .public_key(srv_key.public_key())
        .serial_number(2)
        .not_valid_before(now - datetime.timedelta(hours=1))
        .not_valid_after(now + datetime.timedelta(days=7))
        .add_extension(
            x509.SubjectAlternativeName([
                x509.IPAddress(ipaddress.ip_address("127.0.0.1")),
                x509.DNSName("localhost"),
            ]),
            critical=False,
        )
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

    # Write temporary PEM files
    tmp_dir = tempfile.mkdtemp(prefix="kb_workout_certs_")
    ca_path = os.path.join(tmp_dir, "ca.pem")
    cert_path = os.path.join(tmp_dir, "server.crt")
    key_path = os.path.join(tmp_dir, "server.key")

    with open(ca_path, "w", encoding="ascii") as f:
        f.write(ca_pem)
    with open(cert_path, "w", encoding="ascii") as f:
        f.write(srv_pem)
    with open(key_path, "w", encoding="ascii") as f:
        f.write(srv_key_pem)

    return CompanionCertificates(
        ca_cert_pem=ca_pem,
        ca_key_pem=ca_key_pem,
        server_cert_pem=srv_pem,
        server_key_pem=srv_key_pem,
        spki_sha256=spki_sha256,
        ca_file=ca_path,
        server_cert_file=cert_path,
        server_key_file=key_path,
    )


# ---------------------------------------------------------------------------
# LDAP Companion
# ---------------------------------------------------------------------------

def _make_extended_response(msg_id: int, result_code: int = 0, diag: str = "") -> bytes:
    from pyasn1.codec.ber import encoder
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
    from pyasn1.codec.ber import encoder
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
    from pyasn1.codec.ber import encoder
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
    from pyasn1.codec.ber import encoder
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


class LiveLdapCompanion:
    """Mock LDAP server serving LDAPS on port 10636 and LDAP on port 10389."""

    def __init__(self, certs: CompanionCertificates) -> None:
        self.certs = certs
        self.ldaps_server: asyncio.Server | None = None
        self.ldap_server: asyncio.Server | None = None
        self.directory: dict[str, dict[str, list[bytes]]] = {}
        self.passwords: dict[str, str] = {}
        self._seed_directory()

    def _seed_directory(self) -> None:
        # Bind user
        admin_dn = "cn=admin,dc=planetexpress,dc=com"
        self.passwords[admin_dn] = "GoodNewsEveryone"
        self.directory[admin_dn] = {
            "objectclass": [b"top", b"person", b"organizationalPerson"],
            "cn": [b"admin"],
            "mail": [b"admin@planetexpress.com"],
        }

        # Delivery Subteam Group (child)
        delivery_dn = "cn=delivery-subteam,ou=groups,dc=planetexpress,dc=com"
        self.directory[delivery_dn] = {
            "objectclass": [b"top", b"group"],
            "cn": [b"Delivery-Subteam"],
            "memberOf": [b"cn=bureaucrats-parent,ou=groups,dc=planetexpress,dc=com"],
            "member": [b"cn=hermes,ou=users,dc=planetexpress,dc=com"],
        }

        # Bureaucrats Parent Group (parent)
        bureaucrats_dn = "cn=bureaucrats-parent,ou=groups,dc=planetexpress,dc=com"
        self.directory[bureaucrats_dn] = {
            "objectclass": [b"top", b"group"],
            "cn": [b"Bureaucrats-Parent"],
            "member": [b"cn=delivery-subteam,ou=groups,dc=planetexpress,dc=com"],
        }

        # User hermes (nested in delivery-subteam which nests into bureaucrats-parent)
        hermes_dn = "cn=hermes,ou=users,dc=planetexpress,dc=com"
        self.passwords[hermes_dn] = "hermespassword"
        self.directory[hermes_dn] = {
            "objectclass": [b"top", b"person", b"organizationalPerson", b"user"],
            "cn": [b"Hermes Conrad"],
            "sAMAccountName": [b"hermes"],
            "uid": [b"hermes"],
            "mail": [b"hermes@planetexpress.com"],
            "displayName": [b"Hermes Conrad"],
            "memberOf": [
                b"cn=delivery-subteam,ou=groups,dc=planetexpress,dc=com",
            ],
            "entryUUID": [b"01a21408-0001-7000-8000-000000000001"],
        }

        # User fry
        fry_dn = "cn=fry,ou=users,dc=planetexpress,dc=com"
        self.passwords[fry_dn] = "frypassword"
        self.directory[fry_dn] = {
            "objectclass": [b"top", b"person", b"organizationalPerson", b"user"],
            "cn": [b"Philip J. Fry"],
            "sAMAccountName": [b"fry"],
            "uid": [b"fry"],
            "mail": [b"fry@planetexpress.com"],
            "displayName": [b"Philip J. Fry"],
            "memberOf": [b"cn=delivery-subteam,ou=groups,dc=planetexpress,dc=com"],
            "entryUUID": [b"01a21408-0002-7000-8000-000000000002"],
        }

    async def _handle_client(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        is_tls: bool,
    ) -> None:
        try:
            while not reader.at_eof():
                packet = await read_ber_packet(reader)
                if not packet:
                    break
                msg_id, op_name, op_val = decode_ldap_message(packet)

                if op_name == "bindRequest":
                    bind_dn = str(op_val["name"]).lower().strip()
                    auth_bytes = bytes(op_val["authentication"].asOctets())
                    pwd_str = auth_bytes.decode("utf-8", errors="replace")
                    expected_pwd = self.passwords.get(bind_dn)
                    if expected_pwd is not None and expected_pwd == pwd_str:
                        writer.write(_make_bind_response(msg_id, RESULT_CODE_SUCCESS))
                    else:
                        writer.write(
                            _make_bind_response(
                                msg_id,
                                RESULT_CODE_INVALID_CREDENTIALS,
                                "Invalid bind credentials",
                            )
                        )
                    await writer.drain()

                elif op_name == "searchRequest":
                    base_dn = str(op_val["baseObject"]).lower().strip()
                    filter_raw = (
                        bytes(op_val["filter"].asOctets())
                        if hasattr(op_val["filter"], "asOctets")
                        else bytes(op_val["filter"])
                    )

                    # Extract octet strings from BER filter AST
                    strings: list[str] = []
                    pos = 0
                    while pos < len(filter_raw):
                        if filter_raw[pos] == 0x04:
                            pos += 1
                            if pos < len(filter_raw):
                                length = filter_raw[pos]
                                pos += 1
                                if pos + length <= len(filter_raw):
                                    try:
                                        strings.append(
                                            filter_raw[pos : pos + length].decode(
                                                "utf-8", errors="replace"
                                            )
                                        )
                                    except Exception:
                                        pass
                                    pos += length
                                    continue
                        pos += 1

                    target_user = None
                    for idx, s in enumerate(strings):
                        if s.lower() in ("uid", "samaccountname", "cn") and idx + 1 < len(strings):
                            target_user = strings[idx + 1].lower()
                            break

                    def _get_attr_vals(at: dict[str, list[bytes]], k_name: str) -> list[str]:
                        kn = k_name.lower()
                        for k, v in at.items():
                            if k.lower() == kn:
                                return [
                                    val.decode("utf-8", errors="replace").lower() for val in v
                                ]
                        return []

                    matched_entries = []
                    for dn, attrs in self.directory.items():
                        if base_dn and not dn.endswith(base_dn) and dn != base_dn:
                            continue
                        if target_user is not None:
                            sam = _get_attr_vals(attrs, "sAMAccountName")
                            uids = _get_attr_vals(attrs, "uid")
                            cns = _get_attr_vals(attrs, "cn")
                            if target_user in sam or target_user in uids or target_user in cns:
                                matched_entries.append((dn, attrs))
                        else:
                            matched_entries.append((dn, attrs))

                    for dn, attrs in matched_entries:
                        writer.write(_make_search_entry(msg_id, dn, attrs))
                        await writer.drain()
                    writer.write(_make_search_done(msg_id, RESULT_CODE_SUCCESS))
                    await writer.drain()

                elif op_name == "extendedReq":
                    oid = str(op_val["requestName"])
                    if oid == STARTTLS_OID:
                        writer.write(_make_extended_response(msg_id, RESULT_CODE_SUCCESS))
                        await writer.drain()

                        # Upgrade transport to TLS
                        ssl_ctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
                        ssl_ctx.load_cert_chain(
                            self.certs.server_cert_file, self.certs.server_key_file
                        )
                        ssl_ctx.minimum_version = ssl.TLSVersion.TLSv1_2
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
                        reader._transport = new_transport  # type: ignore[attr-defined] # noqa: SLF001
                        is_tls = True
                    else:
                        writer.write(_make_extended_response(msg_id, 2, "Unsupported extended operation"))
                        await writer.drain()

                elif op_name == "unbindRequest":
                    break
        except Exception as exc:
            logger.exception("LDAP client session error: %s", exc)
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass

    async def start(self) -> None:
        ssl_ctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        ssl_ctx.load_cert_chain(self.certs.server_cert_file, self.certs.server_key_file)
        ssl_ctx.minimum_version = ssl.TLSVersion.TLSv1_2

        async def _ldaps_cb(r: asyncio.StreamReader, w: asyncio.StreamWriter) -> None:
            await self._handle_client(r, w, is_tls=True)

        async def _ldap_cb(r: asyncio.StreamReader, w: asyncio.StreamWriter) -> None:
            await self._handle_client(r, w, is_tls=False)

        # Start LDAPS on 127.0.0.1:10636
        self.ldaps_server = await asyncio.start_server(
            _ldaps_cb,
            host="127.0.0.1",
            port=10636,
            ssl=ssl_ctx,
        )
        # Start plain LDAP on 127.0.0.1:10389
        self.ldap_server = await asyncio.start_server(
            _ldap_cb,
            host="127.0.0.1",
            port=10389,
        )
        logger.info("LDAPS listening on 127.0.0.1:10636, LDAP listening on 127.0.0.1:10389")

    async def stop(self) -> None:
        if self.ldaps_server:
            self.ldaps_server.close()
            await self.ldaps_server.wait_closed()
        if self.ldap_server:
            self.ldap_server.close()
            await self.ldap_server.wait_closed()
        logger.info("LDAP servers stopped")


# ---------------------------------------------------------------------------
# OIDC Companion
# ---------------------------------------------------------------------------

class LiveOidcCompanion:
    """Mock HTTPS OIDC IdP running on 127.0.0.1:18081."""

    def __init__(self, certs: CompanionCertificates) -> None:
        self.certs = certs
        self.issuer = "https://127.0.0.1:18081"
        self.client_id = "kanban-test"
        self.client_secret = "kanban-test-secret-12345"
        self.kid = "workout-oidc-key-1"
        self.email_verified = True
        self.issued_codes: dict[str, dict[str, Any]] = {}

        # Generate RSA signing key for ID tokens
        self._rsa_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self._priv_pem = self._rsa_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        self._pub_pem = self._rsa_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        self._jwk = RSAKey.import_key(
            self._priv_pem, {"kid": self.kid, "use": "sig", "alg": "RS256"}
        )
        self._pub_jwk_dict = self._jwk.as_dict(private=False)

        self.app = self._build_starlette_app()
        self._server: uvicorn.Server | None = None
        self._task: asyncio.Task[Any] | None = None

    def create_id_token(
        self,
        subject: str,
        email: str,
        email_verified: bool,
        nonce: str | None = None,
    ) -> str:
        now = int(time.time())
        header = {"alg": "RS256", "typ": "JWT", "kid": self.kid}
        claims = {
            "iss": self.issuer,
            "sub": subject,
            "aud": self.client_id,
            "iat": now,
            "exp": now + 3600,
            "email": email,
            "email_verified": email_verified,
            "name": f"User {subject}",
            "preferred_username": subject,
        }
        if nonce:
            claims["nonce"] = nonce
        return jwt.encode(header, claims, self._jwk)

    def _build_starlette_app(self) -> FastAPI:
        app = FastAPI()

        @app.get("/.well-known/openid-configuration")
        async def discovery() -> JSONResponse:
            return JSONResponse({
                "issuer": self.issuer,
                "authorization_endpoint": f"{self.issuer}/oauth/authorize",
                "token_endpoint": f"{self.issuer}/oauth/token",
                "jwks_uri": f"{self.issuer}/.well-known/jwks.json",
                "userinfo_endpoint": f"{self.issuer}/oauth/userinfo",
                "id_token_signing_alg_values_supported": ["RS256"],
            })

        @app.get("/.well-known/jwks.json")
        async def jwks() -> JSONResponse:
            return JSONResponse({"keys": [self._pub_jwk_dict]})

        @app.get("/oauth/authorize")
        async def authorize(request: Request) -> Response:
            params = dict(request.query_params)
            code = f"code-{secrets.token_hex(8)}"
            self.issued_codes[code] = {
                "client_id": params.get("client_id", ""),
                "redirect_uri": params.get("redirect_uri", ""),
                "code_challenge": params.get("code_challenge", ""),
                "code_challenge_method": params.get("code_challenge_method", ""),
                "state": params.get("state", ""),
                "nonce": params.get("nonce"),
            }
            redirect_uri = params.get("redirect_uri", "")
            state = params.get("state", "")
            target = f"{redirect_uri}?code={code}&state={state}"
            return RedirectResponse(target, status_code=302)

        @app.post("/oauth/token")
        async def token_endpoint(request: Request) -> JSONResponse:
            raw_body = (await request.body()).decode("utf-8", errors="replace")
            form = dict(urllib.parse.parse_qsl(raw_body))
            code = form.get("code")
            code_verifier = form.get("code_verifier")
            meta = self.issued_codes.get(str(code), {})

            # Validate PKCE S256 if present
            if meta.get("code_challenge"):
                calc_challenge = hashlib.sha256(str(code_verifier).encode("ascii")).digest()
                calc_b64 = base64.urlsafe_b64encode(calc_challenge).rstrip(b"=").decode("ascii")
                if calc_b64 != meta.get("code_challenge"):
                    return JSONResponse({"error": "invalid_grant", "error_description": "PKCE verification failed"}, status_code=400)

            # Issue ID token
            if self.email_verified:
                subject = "usr-amy-wong"
                email = "amy@planetexpress.com"
            else:
                subject = "usr-bender-bending"
                email = "bender@planetexpress.com"

            id_token = self.create_id_token(
                subject=subject,
                email=email,
                email_verified=self.email_verified,
                nonce=meta.get("nonce"),
            )
            return JSONResponse({
                "access_token": f"at-{secrets.token_hex(16)}",
                "token_type": "Bearer",
                "expires_in": 3600,
                "id_token": id_token,
            })

        @app.get("/oauth/userinfo")
        async def userinfo() -> JSONResponse:
            return JSONResponse({
                "sub": "usr-amy-wong",
                "email": "amy@planetexpress.com",
                "email_verified": self.email_verified,
                "name": "Amy Wong",
            })

        @app.api_route("/set_verified", methods=["GET", "POST"])
        async def set_verified(val: bool = True) -> JSONResponse:
            self.email_verified = val
            return JSONResponse({"email_verified": self.email_verified})

        return app

    async def start(self) -> None:
        config = uvicorn.Config(
            self.app,
            host="127.0.0.1",
            port=18081,
            ssl_certfile=self.certs.server_cert_file,
            ssl_keyfile=self.certs.server_key_file,
            log_level="warning",
        )
        self._server = uvicorn.Server(config)
        self._task = asyncio.create_task(self._server.serve())
        # Wait for readiness
        for _ in range(50):
            if self._server.started:
                break
            await asyncio.sleep(0.1)
        logger.info("HTTPS OIDC companion listening on https://127.0.0.1:18081")

    async def stop(self) -> None:
        if self._server:
            self._server.should_exit = True
            if self._task:
                await self._task
        logger.info("OIDC companion stopped")


generate_workout_certs = generate_workout_certificates
