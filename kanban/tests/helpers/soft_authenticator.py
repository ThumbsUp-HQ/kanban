# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
# ruff: noqa: PLR0913
"""Test-only ES256 software authenticator built with cryptography (KB-P2-05b)."""

from __future__ import annotations

import hashlib
import json
import secrets
import struct
from typing import Any

import cbor2
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from webauthn.helpers import bytes_to_base64url


class SoftAuthenticator:
    """In-memory ES256 FIDO2 / WebAuthn software authenticator for testing."""

    def __init__(self) -> None:
        """Initialize in-memory credential store."""
        self.credentials: dict[bytes, dict[str, Any]] = {}

    def create_credential(
        self,
        options: dict[str, Any],
        *,
        origin: str | None = None,
        uv: bool = True,
        up: bool = True,
        sign_count: int = 0,
        credential_id: bytes | None = None,
        override_rp_id_hash: bytes | None = None,
        override_type: str | None = None,
    ) -> dict[str, Any]:
        """Generate a registration credential matching PublicKeyCredential creation options."""
        rp_info = options.get("rp", {})
        rp_id = rp_info.get("id", "localhost")
        challenge_b64 = options.get("challenge", "")

        priv_key = ec.generate_private_key(ec.SECP256R1())
        pub_numbers = priv_key.public_key().public_numbers()
        x_bytes = pub_numbers.x.to_bytes(32, "big")
        y_bytes = pub_numbers.y.to_bytes(32, "big")

        cose_key = {
            1: 2,  # key type: EC2
            3: -7,  # alg: ES256
            -1: 1,  # crv: P-256
            -2: x_bytes,
            -3: y_bytes,
        }
        cose_key_bytes = cbor2.dumps(cose_key)

        cred_id = credential_id if credential_id is not None else secrets.token_bytes(32)
        rp_id_hash = override_rp_id_hash or hashlib.sha256(rp_id.encode("utf-8")).digest()

        flags = (
            (0x01 if up else 0x00) | (0x04 if uv else 0x00) | 0x40
        )  # AT (attestation data present)
        sign_count_bytes = struct.pack(">I", sign_count)
        aaguid = b"\x00" * 16
        cred_id_len = struct.pack(">H", len(cred_id))

        auth_data = (
            rp_id_hash
            + bytes([flags])
            + sign_count_bytes
            + aaguid
            + cred_id_len
            + cred_id
            + cose_key_bytes
        )

        attestation_obj = {
            "fmt": "none",
            "attStmt": {},
            "authData": auth_data,
        }
        attestation_obj_bytes = cbor2.dumps(attestation_obj)

        eff_origin = origin or f"https://{rp_id}"
        client_data = {
            "type": override_type or "webauthn.create",
            "challenge": challenge_b64,
            "origin": eff_origin,
            "crossOrigin": False,
        }
        client_data_bytes = json.dumps(client_data).encode("utf-8")

        self.credentials[cred_id] = {
            "private_key": priv_key,
            "sign_count": sign_count,
            "public_key": cose_key_bytes,
            "rp_id": rp_id,
        }

        return {
            "id": bytes_to_base64url(cred_id),
            "rawId": bytes_to_base64url(cred_id),
            "type": "public-key",
            "response": {
                "clientDataJSON": bytes_to_base64url(client_data_bytes),
                "attestationObject": bytes_to_base64url(attestation_obj_bytes),
                "transports": ["internal"],
            },
        }

    def get_assertion(
        self,
        options: dict[str, Any],
        *,
        credential_id: bytes | None = None,
        origin: str | None = None,
        uv: bool = True,
        up: bool = True,
        sign_count: int | None = None,
        override_rp_id_hash: bytes | None = None,
        override_type: str | None = None,
        tamper_signature: bool = False,
    ) -> dict[str, Any]:
        """Generate an authentication assertion matching PublicKeyCredential request options."""
        rp_id = options.get("rpId", "localhost")
        challenge_b64 = options.get("challenge", "")

        if credential_id is not None:
            cred = self.credentials.get(credential_id)
            if cred is None:
                msg = f"Credential {credential_id!r} not found in authenticator"
                raise KeyError(msg)
            used_cred_id = credential_id
        elif self.credentials:
            used_cred_id, cred = next(iter(self.credentials.items()))
        else:
            msg = "No credentials registered in authenticator"
            raise ValueError(msg)

        if sign_count is not None:
            actual_sign_count = sign_count
            cred["sign_count"] = sign_count
        else:
            actual_sign_count = cred["sign_count"] + 1
            cred["sign_count"] = actual_sign_count

        rp_id_hash = override_rp_id_hash or hashlib.sha256(rp_id.encode("utf-8")).digest()
        flags = (0x01 if up else 0x00) | (0x04 if uv else 0x00)
        auth_data = rp_id_hash + bytes([flags]) + struct.pack(">I", actual_sign_count)

        eff_origin = origin or f"https://{rp_id}"
        client_data = {
            "type": override_type or "webauthn.get",
            "challenge": challenge_b64,
            "origin": eff_origin,
            "crossOrigin": False,
        }
        client_data_bytes = json.dumps(client_data).encode("utf-8")
        client_data_hash = hashlib.sha256(client_data_bytes).digest()

        data_to_sign = auth_data + client_data_hash
        private_key = cred["private_key"]
        sig = private_key.sign(data_to_sign, ec.ECDSA(hashes.SHA256()))

        if tamper_signature:
            # Flip bits in signature to make it cryptographically invalid
            sig = bytes([sig[0] ^ 0xFF]) + sig[1:]

        return {
            "id": bytes_to_base64url(used_cred_id),
            "rawId": bytes_to_base64url(used_cred_id),
            "type": "public-key",
            "response": {
                "clientDataJSON": bytes_to_base64url(client_data_bytes),
                "authenticatorData": bytes_to_base64url(auth_data),
                "signature": bytes_to_base64url(sig),
            },
        }
