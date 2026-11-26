# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Local HTTPS OIDC JWKS companion server on 127.0.0.1:18083 for RFC 8693 workout (KAN-418)."""

from __future__ import annotations

import base64
import datetime
import json
import ssl
import sys
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
import joserfc.jwk
import joserfc.jwt

COMPANION_PORT = 18083
COMPANION_HOST = "127.0.0.1"
ISSUER_URL = f"https://{COMPANION_HOST}:{COMPANION_PORT}"
KEY_ID = "companion-key-1"


def generate_ca_and_server_certs(
    out_dir: Path,
) -> tuple[Path, Path, Path]:
    """Generate self-signed CA and server certificates for 127.0.0.1."""
    out_dir.mkdir(parents=True, exist_ok=True)
    ca_key_path = out_dir / "ca.key"
    ca_crt_path = out_dir / "ca.crt"
    server_key_path = out_dir / "server.key"
    server_crt_path = out_dir / "server.crt"

    # 1. Generate CA
    ca_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    ca_name = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, "Kanban Workout Test CA"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Kanban Platform Test"),
    ])
    now = datetime.datetime.now(datetime.timezone.utc)
    ca_cert = (
        x509.CertificateBuilder()
        .subject_name(ca_name)
        .issuer_name(ca_name)
        .public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=30))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(ca_key, hashes.SHA256())
    )

    ca_key_path.write_bytes(
        ca_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    ca_crt_path.write_bytes(ca_cert.public_bytes(serialization.Encoding.PEM))

    # 2. Generate Server Certificate
    server_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    server_name = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, COMPANION_HOST),
    ])
    server_cert = (
        x509.CertificateBuilder()
        .subject_name(server_name)
        .issuer_name(ca_name)
        .public_key(server_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=30))
        .add_extension(
            x509.SubjectAlternativeName([
                x509.IPAddress(ipaddress_ip := __import__("ipaddress").ip_address(COMPANION_HOST)),
                x509.DNSName("localhost"),
            ]),
            critical=False,
        )
        .sign(ca_key, hashes.SHA256())
    )

    server_key_path.write_bytes(
        server_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    server_crt_path.write_bytes(server_cert.public_bytes(serialization.Encoding.PEM))

    return ca_crt_path, server_key_path, server_crt_path


class OidcCompanionState:
    def __init__(self, cert_dir: Path) -> None:
        self.cert_dir = cert_dir
        self.ca_crt_path, self.server_key_path, self.server_crt_path = generate_ca_and_server_certs(cert_dir)
        self.signing_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.jwk_dict = self._build_jwk()
        self.jwks_dict = {"keys": [self.jwk_dict]}

    def _build_jwk(self) -> dict[str, Any]:
        pub_numbers = self.signing_key.public_key().public_numbers()
        n_bytes = pub_numbers.n.to_bytes((pub_numbers.n.bit_length() + 7) // 8, byteorder="big")
        e_bytes = pub_numbers.e.to_bytes((pub_numbers.e.bit_length() + 7) // 8, byteorder="big")

        def b64url(b: bytes) -> str:
            return base64.urlsafe_b64encode(b).decode("ascii").rstrip("=")

        return {
            "kty": "RSA",
            "kid": KEY_ID,
            "use": "sig",
            "alg": "RS256",
            "n": b64url(n_bytes),
            "e": b64url(e_bytes),
        }

    def mint_jwt(
        self,
        sub: str = "repo:ThumbsUp-HQ/kanban:ref:refs/heads/main",
        aud: str = "kanban-workload-aud",
        iss: str = ISSUER_URL,
        ttl_seconds: int = 300,
        extra_claims: dict[str, Any] | None = None,
    ) -> str:
        now = int(time.time())
        claims = {
            "iss": iss,
            "sub": sub,
            "aud": aud,
            "exp": now + ttl_seconds,
            "nbf": now - 10,
            "iat": now,
            "jti": f"workload-jti-{time.time_ns()}",
        }
        if extra_claims:
            claims.update(extra_claims)

        priv_pem = self.signing_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        rsa_key = joserfc.jwk.RSAKey.import_key(priv_pem, {"kid": KEY_ID})
        return joserfc.jwt.encode({"alg": "RS256", "kid": KEY_ID, "typ": "JWT"}, claims, rsa_key)


_GLOBAL_STATE: OidcCompanionState | None = None


class OidcHandler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        pass

    def do_GET(self) -> None:  # noqa: N802
        state = _GLOBAL_STATE
        if not state:
            self.send_response(HTTPStatus.INTERNAL_SERVER_ERROR)
            self.end_headers()
            return

        path = self.path.split("?")[0]
        if path == "/.well-known/openid-configuration":
            doc = {
                "issuer": ISSUER_URL,
                "authorization_endpoint": f"{ISSUER_URL}/oauth/authorize",
                "token_endpoint": f"{ISSUER_URL}/oauth/token",
                "jwks_uri": f"{ISSUER_URL}/.well-known/jwks.json",
                "id_token_signing_alg_values_supported": ["RS256"],
            }
            body = json.dumps(doc).encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path == "/.well-known/jwks.json":
            body = json.dumps(state.jwks_dict).encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        self.send_response(HTTPStatus.NOT_FOUND)
        self.end_headers()

    def do_POST(self) -> None:  # noqa: N802
        state = _GLOBAL_STATE
        if not state:
            self.send_response(HTTPStatus.INTERNAL_SERVER_ERROR)
            self.end_headers()
            return

        path = self.path.split("?")[0]
        if path == "/mint-token":
            try:
                length = int(self.headers.get("Content-Length", 0))
                payload = json.loads(self.rfile.read(length).decode("utf-8")) if length else {}
                if "exp_in" in payload and "ttl_seconds" not in payload:
                    payload["ttl_seconds"] = payload.pop("exp_in")
                token = state.mint_jwt(**payload)
                body = json.dumps({"token": token}).encode("utf-8")
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            except Exception as e:
                err_body = json.dumps({"error": str(e)}).encode("utf-8")
                self.send_response(HTTPStatus.BAD_REQUEST)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(err_body)))
                self.end_headers()
                self.wfile.write(err_body)
                return

        self.send_response(HTTPStatus.NOT_FOUND)
        self.end_headers()


class OidcCompanionServer:
    def __init__(self, cert_dir: Path | None = None) -> None:
        global _GLOBAL_STATE
        if cert_dir is None:
            cert_dir = Path("/tmp/kan418-oidc-certs")
        self.state = OidcCompanionState(cert_dir)
        _GLOBAL_STATE = self.state

        self.httpd = HTTPServer((COMPANION_HOST, COMPANION_PORT), OidcHandler)
        ssl_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ssl_ctx.load_cert_chain(
            certfile=str(self.state.server_crt_path),
            keyfile=str(self.state.server_key_path),
        )
        self.httpd.socket = ssl_ctx.wrap_socket(self.httpd.socket, server_side=True)
        self.thread: threading.Thread | None = None

    def start(self) -> None:
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def stop(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=2.0)

    def mint_token(self, **kwargs: Any) -> str:
        return self.state.mint_jwt(**kwargs)


if __name__ == "__main__":
    server = OidcCompanionServer()
    server.start()
    print(f"OIDC Companion running at {ISSUER_URL}")
    print(f"CA Cert: {server.state.ca_crt_path}")
    token = server.mint_token()
    print(f"Sample Token: {token[:25]}...")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        server.stop()
