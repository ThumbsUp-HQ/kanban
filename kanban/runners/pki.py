# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Runner PKI: CSR validation, ECDSA leaf cert issuance & fingerprint pinning (KB-P5-22a, S14.2)."""

from __future__ import annotations

import base64
import uuid  # noqa: TC003
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Final

from cryptography import x509
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, ed25519, rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, ExtensionOID, NameOID

from kanban.security.keys import derive_subkey

if TYPE_CHECKING:
    from kanban.security.keys import KeyMaterial

__all__ = [
    "CertVerificationError",
    "CsrValidationError",
    "IssuedCertificate",
    "compute_cert_fingerprint",
    "derive_runner_ca",
    "validate_and_sign_csr",
    "verify_runner_client_cert_chain",
]

_MIN_RSA_KEY_SIZE: Final[int] = 3072
_CERT_VALIDITY_DAYS: Final[int] = 30
_CA_VALIDITY_DAYS: Final[int] = 3650
_HEX_FINGERPRINT_LEN: Final[int] = 64
_DIGEST_BYTES_LEN: Final[int] = 32
_SECP256R1_ORDER: Final[int] = 0xFFFFFFFF00000000FFFFFFFFFFFFFFFFBCE6FAADA7179E84F3B9CAC2FC632551
_ALLOWED_EC_CURVES: Final[tuple[type[ec.EllipticCurve], ...]] = (
    ec.SECP256R1,
    ec.SECP384R1,
    ec.SECP521R1,
)


class CertVerificationError(ValueError):
    """Raised when a client certificate chain fails cryptographic or policy verification."""

    def __init__(self, code: str, detail: str) -> None:
        """Initialize with machine-readable error code and human description."""
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail
        self.status = 401


class CsrValidationError(ValueError):
    """Raised when a PKCS#10 Certificate Signing Request fails validation."""

    def __init__(self, code: str, detail: str) -> None:
        """Initialize with machine-readable error code and human description."""
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail
        self.status = 422


def _csr_err(detail: str) -> CsrValidationError:
    """Construct CsrValidationError with standard CSR_INVALID code."""
    code = "CSR_INVALID"
    return CsrValidationError(code, detail)


@dataclass(frozen=True, slots=True)
class IssuedCertificate:
    """Bundle containing leaf certificate, CA certificate, fingerprint and expiry."""

    runner_id: uuid.UUID
    client_cert_pem: str
    ca_cert_pem: str
    client_cert_sha256: bytes
    cert_expires_at: datetime


def compute_cert_fingerprint(cert_data: str | bytes) -> bytes:  # noqa: PLR0911
    """Compute 32-byte SHA-256 fingerprint from PEM or DER certificate bytes."""
    if isinstance(cert_data, str):
        cleaned = cert_data.strip()
        if cleaned.startswith("-----BEGIN"):
            cert = x509.load_pem_x509_certificate(cleaned.encode("utf-8"))
            return cert.fingerprint(hashes.SHA256())
        if len(cleaned) == _HEX_FINGERPRINT_LEN:
            return bytes.fromhex(cleaned)
        raw = base64.b64decode(cleaned)
        if len(raw) == _DIGEST_BYTES_LEN:
            return raw
        cert = x509.load_der_x509_certificate(raw)
        return cert.fingerprint(hashes.SHA256())

    if cert_data.startswith(b"-----BEGIN"):
        cert = x509.load_pem_x509_certificate(cert_data)
        return cert.fingerprint(hashes.SHA256())
    if len(cert_data) == _DIGEST_BYTES_LEN:
        return cert_data
    cert = x509.load_der_x509_certificate(cert_data)
    return cert.fingerprint(hashes.SHA256())


_CA_CACHE: dict[tuple[bytes, uuid.UUID], tuple[x509.Certificate, ec.EllipticCurvePrivateKey]] = {}


def derive_runner_ca(
    key_material: KeyMaterial, workspace_id: uuid.UUID
) -> tuple[x509.Certificate, ec.EllipticCurvePrivateKey]:
    """Derive deterministic workspace runner CA key and self-signed CA certificate."""
    cache_key = (key_material.master_kek, workspace_id)
    if cache_key in _CA_CACHE:
        return _CA_CACHE[cache_key]

    ca_seed = derive_subkey(key_material.master_kek, f"runner-ca/{workspace_id}")
    curve = ec.SECP256R1()
    scalar = (int.from_bytes(ca_seed, "big") % (_SECP256R1_ORDER - 1)) + 1
    ca_private_key = ec.derive_private_key(scalar, curve)

    ca_name = x509.Name(
        [
            x509.NameAttribute(NameOID.COMMON_NAME, f"👍kanban Runner CA {workspace_id}"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "👍kanban Platform"),
        ]
    )
    fixed_start = datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)
    fixed_serial = int.from_bytes(ca_seed[:16], "big")
    ca_cert = (
        x509.CertificateBuilder()
        .subject_name(ca_name)
        .issuer_name(ca_name)
        .public_key(ca_private_key.public_key())
        .serial_number(fixed_serial)
        .not_valid_before(fixed_start)
        .not_valid_after(fixed_start + timedelta(days=_CA_VALIDITY_DAYS))
        .add_extension(
            x509.BasicConstraints(ca=True, path_length=0),
            critical=True,
        )
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                key_cert_sign=True,
                crl_sign=True,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(
            x509.SubjectKeyIdentifier.from_public_key(ca_private_key.public_key()),
            critical=False,
        )
        .sign(ca_private_key, hashes.SHA256())
    )
    _CA_CACHE[cache_key] = (ca_cert, ca_private_key)
    return ca_cert, ca_private_key


def validate_and_sign_csr(
    csr_pem: str | bytes,
    workspace_id: uuid.UUID,
    pool_slug: str,
    runner_id: uuid.UUID,
    key_material: KeyMaterial,
) -> IssuedCertificate:
    """Validate PKCS#10 CSR signature, key strength, and sign 30-day leaf certificate."""
    csr_bytes = csr_pem.strip().encode("utf-8") if isinstance(csr_pem, str) else csr_pem

    try:
        csr = x509.load_pem_x509_csr(csr_bytes)
    except Exception as exc:
        msg = f"Failed to parse PKCS#10 CSR: {exc}"
        raise _csr_err(msg) from exc

    if not csr.is_signature_valid:
        msg = "CSR cryptographic signature verification failed"
        raise _csr_err(msg)

    pubkey = csr.public_key()
    if isinstance(pubkey, ec.EllipticCurvePublicKey):
        if not isinstance(pubkey.curve, _ALLOWED_EC_CURVES):
            msg = (
                f"Curve {pubkey.curve.name} is not permitted. "
                "Only NIST P-256, P-384, or P-521 are allowed."
            )
            raise _csr_err(msg)
    elif isinstance(pubkey, ed25519.Ed25519PublicKey):
        pass
    elif isinstance(pubkey, rsa.RSAPublicKey):
        if pubkey.key_size < _MIN_RSA_KEY_SIZE:
            msg = f"RSA key length {pubkey.key_size} is below mandatory 3072-bit minimum"
            raise _csr_err(msg)
    else:
        msg = f"Unsupported asymmetric key algorithm {type(pubkey).__name__}"
        raise _csr_err(msg)

    try:
        bc_ext = csr.extensions.get_extension_for_oid(ExtensionOID.BASIC_CONSTRAINTS)
        bc_val = bc_ext.value
        if isinstance(bc_val, x509.BasicConstraints) and bc_val.ca is True:
            msg = "CSR requested basicConstraints CA:TRUE forbidden for leaf certificates"
            raise _csr_err(msg)
    except x509.ExtensionNotFound:
        pass

    ca_cert, ca_private_key = derive_runner_ca(key_material, workspace_id)

    now = datetime.now(UTC)
    not_before = now - timedelta(minutes=5)
    cert_expires_at = now + timedelta(days=_CERT_VALIDITY_DAYS)
    san_uri = f"spiffe://kanban.internal/ws/{workspace_id}/pool/{pool_slug}/runner/{runner_id}"

    builder = (
        x509.CertificateBuilder()
        .subject_name(
            x509.Name(
                [
                    x509.NameAttribute(NameOID.COMMON_NAME, f"runner:{runner_id}"),
                    x509.NameAttribute(NameOID.ORGANIZATION_NAME, "👍kanban Remote Runners"),
                ]
            )
        )
        .issuer_name(ca_cert.subject)
        .public_key(pubkey)
        .serial_number(x509.random_serial_number())
        .not_valid_before(not_before)
        .not_valid_after(cert_expires_at)
        .add_extension(
            x509.BasicConstraints(ca=False, path_length=None),
            critical=True,
        )
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                key_encipherment=isinstance(pubkey, rsa.RSAPublicKey),
                key_agreement=isinstance(pubkey, ec.EllipticCurvePublicKey),
                content_commitment=False,
                data_encipherment=False,
                key_cert_sign=False,
                crl_sign=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(
            x509.ExtendedKeyUsage([ExtendedKeyUsageOID.CLIENT_AUTH]),
            critical=False,
        )
        .add_extension(
            x509.SubjectAlternativeName([x509.UniformResourceIdentifier(san_uri)]),
            critical=False,
        )
        .add_extension(
            x509.SubjectKeyIdentifier.from_public_key(pubkey),
            critical=False,
        )
        .add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_private_key.public_key()),
            critical=False,
        )
    )

    leaf_cert = builder.sign(ca_private_key, hashes.SHA256())
    client_cert_sha256 = leaf_cert.fingerprint(hashes.SHA256())
    client_cert_pem = leaf_cert.public_bytes(serialization.Encoding.PEM).decode("ascii")
    ca_cert_pem = ca_cert.public_bytes(serialization.Encoding.PEM).decode("ascii")

    return IssuedCertificate(
        runner_id=runner_id,
        client_cert_pem=client_cert_pem,
        ca_cert_pem=ca_cert_pem,
        client_cert_sha256=client_cert_sha256,
        cert_expires_at=cert_expires_at,
    )


def _load_x509_cert(cert_data: str | bytes) -> x509.Certificate:
    """Parse an X.509 certificate from PEM string/bytes or DER bytes."""
    if isinstance(cert_data, str):
        cleaned = cert_data.strip()
        if cleaned.startswith("-----BEGIN"):
            try:
                return x509.load_pem_x509_certificate(cleaned.encode("utf-8"))
            except Exception as exc:
                msg = f"Failed to parse certificate PEM text: {exc}"
                msg_0 = "CERT_PARSE_ERROR"
                raise CertVerificationError(msg_0, msg) from exc
        try:
            raw = base64.b64decode(cleaned)
            return x509.load_der_x509_certificate(raw)
        except Exception as exc:
            msg = f"Failed to parse certificate PEM/base64: {exc}"
            msg_0 = "CERT_PARSE_ERROR"
            raise CertVerificationError(msg_0, msg) from exc

    if cert_data.strip().startswith(b"-----BEGIN"):
        try:
            return x509.load_pem_x509_certificate(cert_data)
        except Exception as exc:
            msg = f"Failed to parse certificate PEM bytes: {exc}"
            msg_0 = "CERT_PARSE_ERROR"
            raise CertVerificationError(msg_0, msg) from exc

    try:
        return x509.load_der_x509_certificate(cert_data)
    except Exception as exc:
        msg = f"Failed to parse certificate DER bytes: {exc}"
        msg_0 = "CERT_PARSE_ERROR"
        raise CertVerificationError(msg_0, msg) from exc


def verify_runner_client_cert_chain(  # noqa: C901, PLR0912, PLR0913, PLR0915
    leaf_pem_or_der: str | bytes,
    *,
    active_ca_cert_pem: str | bytes,
    previous_ca_cert_pem: str | bytes | None = None,
    expected_runner_id: uuid.UUID | str,
    expected_fingerprint_sha256: bytes | str,
    now: datetime | None = None,
) -> x509.Certificate:
    """Cryptographically verify leaf certificate against CA, constraints, CN, and fingerprint."""
    leaf_cert = _load_x509_cert(leaf_pem_or_der)

    # 1. SHA-256 DER fingerprint match
    actual_fp = leaf_cert.fingerprint(hashes.SHA256())
    if isinstance(expected_fingerprint_sha256, str):
        clean_fp = expected_fingerprint_sha256.strip()
        if len(clean_fp) == _HEX_FINGERPRINT_LEN:
            target_fp = bytes.fromhex(clean_fp)
        else:
            target_fp = base64.b64decode(clean_fp)
    else:
        target_fp = bytes(expected_fingerprint_sha256)

    if actual_fp != target_fp:
        msg = f"Fingerprint mismatch: actual {actual_fp.hex()} != expected {target_fp.hex()}"
        msg_0 = "FINGERPRINT_MISMATCH"
        raise CertVerificationError(msg_0, msg)

    # 2. Subject CN == runner:{expected_runner_id} (or runner-{expected_runner_id})
    cn_attrs = leaf_cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
    if not cn_attrs:
        msg = "Subject Common Name is missing from leaf certificate"
        msg_0 = "SUBJECT_MISMATCH"
        raise CertVerificationError(msg_0, msg)
    actual_cn = str(cn_attrs[0].value)
    expected_id_str = str(expected_runner_id)
    if actual_cn not in (f"runner:{expected_id_str}", f"runner-{expected_id_str}"):
        msg = f"Subject CN '{actual_cn}' does not match expected 'runner:{expected_id_str}'"
        msg_0 = "SUBJECT_MISMATCH"
        raise CertVerificationError(msg_0, msg)

    # 3. BasicConstraints(ca=False)
    try:
        bc_ext = leaf_cert.extensions.get_extension_for_oid(ExtensionOID.BASIC_CONSTRAINTS)
        bc_val = bc_ext.value
        if not isinstance(bc_val, x509.BasicConstraints) or bc_val.ca is not False:
            msg = "Leaf certificate must have BasicConstraints with ca=False"
            msg_0 = "BASIC_CONSTRAINTS_INVALID"
            raise CertVerificationError(msg_0, msg)
    except x509.ExtensionNotFound as exc:
        msg = "BasicConstraints extension is missing from leaf certificate"
        msg_0 = "BASIC_CONSTRAINTS_MISSING"
        raise CertVerificationError(msg_0, msg) from exc

    # 4. ExtendedKeyUsage(CLIENT_AUTH)
    try:
        eku_ext = leaf_cert.extensions.get_extension_for_oid(ExtensionOID.EXTENDED_KEY_USAGE)
        eku_val = eku_ext.value
        if (
            not isinstance(eku_val, x509.ExtendedKeyUsage)
            or ExtendedKeyUsageOID.CLIENT_AUTH not in eku_val
        ):
            msg = "ExtendedKeyUsage does not permit client authentication (CLIENT_AUTH)"
            msg_0 = "EXTENDED_KEY_USAGE_INVALID"
            raise CertVerificationError(msg_0, msg)
    except x509.ExtensionNotFound as exc:
        msg = "ExtendedKeyUsage extension is missing from leaf certificate"
        msg_0 = "EXTENDED_KEY_USAGE_MISSING"
        raise CertVerificationError(msg_0, msg) from exc

    # 5. Validity window (not_valid_before_utc <= now <= not_valid_after_utc)
    check_time = now if now is not None else datetime.now(UTC)
    if check_time.tzinfo is None:
        check_time = check_time.replace(tzinfo=UTC)

    not_before = (
        leaf_cert.not_valid_before_utc
        if hasattr(leaf_cert, "not_valid_before_utc")
        else leaf_cert.not_valid_before.replace(tzinfo=UTC)
    )
    not_after = (
        leaf_cert.not_valid_after_utc
        if hasattr(leaf_cert, "not_valid_after_utc")
        else leaf_cert.not_valid_after.replace(tzinfo=UTC)
    )
    if check_time < not_before:
        msg = f"Certificate not yet valid (valid from {not_before.isoformat()})"
        msg_0 = "CERT_NOT_YET_VALID"
        raise CertVerificationError(msg_0, msg)
    if check_time > not_after:
        msg = f"Certificate has expired (expired at {not_after.isoformat()})"
        msg_0 = "CERT_EXPIRED"
        raise CertVerificationError(msg_0, msg)

    # 6. Cryptographic issuer signature against active or previous (grace) CA
    ca_candidates: list[str | bytes] = [active_ca_cert_pem]
    if previous_ca_cert_pem is not None:
        ca_candidates.append(previous_ca_cert_pem)

    verified = False
    last_err: Exception | None = None
    for ca_raw in ca_candidates:
        try:
            ca_cert = _load_x509_cert(ca_raw)
            leaf_cert.verify_directly_issued_by(ca_cert)
            verified = True
            break
        except (ValueError, TypeError, InvalidSignature) as exc:
            last_err = exc

    if not verified:
        msg = f"Leaf certificate issuer signature verification failed against CA chain: {last_err}"
        msg_0 = "ISSUER_SIGNATURE_INVALID"
        raise CertVerificationError(msg_0, msg)

    return leaf_cert
