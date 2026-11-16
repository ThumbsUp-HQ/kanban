# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Feature unit tests for remote runner PKI and CSR enrollment (KB-P5-22a, S14.2, S11.4)."""

from __future__ import annotations

import base64
import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, ed25519, rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, ExtensionOID, NameOID
from sqlalchemy import select, text, update

from database.models.remote_runner import RemoteRunner, RemoteRunnerEnrollmentToken
from kanban.runners.pki import (
    CsrValidationError,
    compute_cert_fingerprint,
    derive_runner_ca,
    validate_and_sign_csr,
)
from kanban.security.keys import KeyMaterial

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    import httpx
    from sqlalchemy.ext.asyncio import AsyncSession

    from kanban.tests.api.conftest import ApiEnv, SeededUser

pytestmark = pytest.mark.committed_db


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


@pytest.fixture(autouse=True)
def setup_test_key_material(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set up valid test key material in environment."""
    monkeypatch.delenv("KANBAN_KEYRING_FILE", raising=False)
    monkeypatch.setenv("KANBAN_MASTER_KEK", _b64(b"k" * 32))
    monkeypatch.setenv("KANBAN_AUTH_PEPPER", _b64(b"p" * 32))
    monkeypatch.setenv("KANBAN_SESSION_HMAC_KEY", _b64(b"s" * 32))
    monkeypatch.setenv("KANBAN_MASTER_KEK_KID", "test-kid-1")


async def _enroll_totp(session: AsyncSession, p_id: uuid.UUID) -> None:
    """Enroll and confirm active TOTP factor to satisfy require_admin_aal2."""
    await session.execute(
        text("SELECT kb_auth.totp_enroll(:p_id, :blob, :dek, 'kek-v1')"),
        {
            "p_id": p_id,
            "blob": b"\x01" + b"\x00" * 28,
            "dek": b"\x01" + b"\x00" * 44,
        },
    )
    res = await session.execute(
        text("SELECT id FROM kb_auth.totp_get_pending(:p_id)"),
        {"p_id": p_id},
    )
    p_row = res.mappings().first()
    if p_row:
        await session.execute(
            text("SELECT kb_auth.totp_confirm(:p_fid, 100)"),
            {"p_fid": p_row["id"]},
        )
    await session.commit()


def _generate_csr(
    key: ec.EllipticCurvePrivateKey | ed25519.Ed25519PrivateKey | rsa.RSAPrivateKey,
    cn: str = "runner-node-1",
    *,
    is_ca: bool = False,
) -> str:
    """Generate PKCS#10 CSR in PEM format."""
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])
    builder = x509.CertificateSigningRequestBuilder().subject_name(name)
    if is_ca:
        builder = builder.add_extension(
            x509.BasicConstraints(ca=True, path_length=None), critical=True
        )

    hash_algo = None if isinstance(key, ed25519.Ed25519PrivateKey) else hashes.SHA256()
    csr = builder.sign(key, hash_algo)
    return csr.public_bytes(serialization.Encoding.PEM).decode("ascii")


def test_pki_compute_fingerprint_variants() -> None:
    """Unit test compute_cert_fingerprint with PEM, DER bytes, 64-char hex, and 32-byte raw."""
    priv = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "test")])
    now = datetime.now(UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(priv.public_key())
        .serial_number(1)
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=1))
        .sign(priv, hashes.SHA256())
    )
    expected_fp = cert.fingerprint(hashes.SHA256())
    pem_str = cert.public_bytes(serialization.Encoding.PEM).decode("ascii")
    der_bytes = cert.public_bytes(serialization.Encoding.DER)

    assert compute_cert_fingerprint(pem_str) == expected_fp
    assert compute_cert_fingerprint(der_bytes) == expected_fp
    assert compute_cert_fingerprint(expected_fp.hex()) == expected_fp
    assert compute_cert_fingerprint(expected_fp) == expected_fp
    b64_str = base64.b64encode(expected_fp).decode("ascii")
    assert compute_cert_fingerprint(b64_str) == expected_fp


def test_pki_derive_ca_deterministic() -> None:
    """Verify derive_runner_ca produces stable certificate for same workspace."""
    km = KeyMaterial(
        master_kek=b"\x01" * 32,
        auth_pepper=b"\x02" * 32,
        session_hmac_key=b"\x03" * 32,
    )
    ws_id = uuid.uuid4()
    ca1, key1 = derive_runner_ca(km, ws_id)
    ca2, key2 = derive_runner_ca(km, ws_id)

    assert ca1.fingerprint(hashes.SHA256()) == ca2.fingerprint(hashes.SHA256())
    assert key1.private_numbers().private_value == key2.private_numbers().private_value


@pytest.mark.asyncio
async def test_case_1_positive_mint_and_enroll(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Test Case 1: Positive flow - admin mints token, runner calls /enroll, receives leaf cert."""
    admin = await make_user("runner-admin", workspace_role="WORKSPACE_ADMIN")
    await _enroll_totp(api_env.seed, admin.id)
    admin_client = as_principal(admin, aal_level=2)

    # 1. Admin mints token
    mint_resp = await admin_client.post(
        "/api/v1/admin/agent-runners/enrollment-tokens",
        json={"pool_slug": "gpu-pool-a", "ttl_seconds": 600},
    )
    assert mint_resp.status_code == 201, mint_resp.text
    mint_data = mint_resp.json()
    token = mint_data["enrollment_token"]
    assert token.startswith("kb_rnr_enroll_")
    assert mint_data["pool_slug"] == "gpu-pool-a"

    # 2. Runner generates P-256 key & CSR
    runner_key = ec.generate_private_key(ec.SECP256R1())
    csr_pem = _generate_csr(runner_key, cn="runner-box-1")

    # 3. Unauthenticated runner enrolls
    api_env.resolver.principal = None
    anon_client = api_env.client
    enroll_resp = await anon_client.post(
        "/api/v1/agent-runners/enroll",
        json={
            "enrollment_token": token,
            "csr_pem": csr_pem,
            "hostname": "runner-box-1.internal",
            "capabilities": {"gpu": "a100", "ram_gb": 64},
        },
    )
    assert enroll_resp.status_code == 201, enroll_resp.text
    enroll_data = enroll_resp.json()
    runner_id_str = enroll_data["runner_id"]
    client_cert_pem = enroll_data["client_cert_pem"]
    ca_cert_pem = enroll_data["ca_cert_pem"]
    assert enroll_data["wss_url"] == "/api/v1/agent-runners/ws"

    # Parse leaf cert and verify invariants
    leaf_cert = x509.load_pem_x509_certificate(client_cert_pem.encode("ascii"))
    ca_cert = x509.load_pem_x509_certificate(ca_cert_pem.encode("ascii"))

    # Verify signature
    ca_pub = ca_cert.public_key()
    assert isinstance(ca_pub, ec.EllipticCurvePublicKey)
    ca_pub.verify(
        leaf_cert.signature,
        leaf_cert.tbs_certificate_bytes,
        ec.ECDSA(hashes.SHA256()),
    )

    # Verify SAN URI
    san_ext = leaf_cert.extensions.get_extension_for_oid(ExtensionOID.SUBJECT_ALTERNATIVE_NAME)
    assert isinstance(san_ext.value, x509.SubjectAlternativeName)
    uris = [n.value for n in san_ext.value if isinstance(n, x509.UniformResourceIdentifier)]
    expected_uri = (
        f"spiffe://kanban.internal/ws/{api_env.workspace_id}/pool/gpu-pool-a/runner/{runner_id_str}"
    )
    assert expected_uri in uris

    # Verify ExtendedKeyUsage
    eku_ext = leaf_cert.extensions.get_extension_for_oid(ExtensionOID.EXTENDED_KEY_USAGE)
    assert isinstance(eku_ext.value, x509.ExtendedKeyUsage)
    assert ExtendedKeyUsageOID.CLIENT_AUTH in eku_ext.value

    # Verify database state
    runner_uuid = uuid.UUID(runner_id_str)
    r_row = (
        (await api_env.seed.execute(select(RemoteRunner).where(RemoteRunner.id == runner_uuid)))
        .scalars()
        .first()
    )
    assert r_row is not None
    assert r_row.pool_slug == "gpu-pool-a"
    assert r_row.hostname == "runner-box-1.internal"
    assert r_row.status == "offline"
    assert r_row.client_cert_sha256 == leaf_cert.fingerprint(hashes.SHA256())

    t_row = (
        (
            await api_env.seed.execute(
                select(RemoteRunnerEnrollmentToken).where(
                    RemoteRunnerEnrollmentToken.id == uuid.UUID(mint_data["id"])
                )
            )
        )
        .scalars()
        .first()
    )
    assert t_row is not None
    assert t_row.consumed_at is not None
    assert t_row.consumed_by_runner_id == runner_uuid


@pytest.mark.asyncio
async def test_case_2_security_single_use_expiry_and_bad_csr(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Test Case 2: Security checks - single-use replay, expired token, CA:TRUE & tampered CSR."""
    admin = await make_user("runner-admin-2", workspace_role="WORKSPACE_ADMIN")
    await _enroll_totp(api_env.seed, admin.id)

    # 1. Mint token and enroll once
    admin_client = as_principal(admin, aal_level=2)
    mint_resp = await admin_client.post(
        "/api/v1/admin/agent-runners/enrollment-tokens",
        json={"pool_slug": "pool-replay", "ttl_seconds": 300},
    )
    assert mint_resp.status_code == 201, mint_resp.text
    token = mint_resp.json()["enrollment_token"]
    key1 = ec.generate_private_key(ec.SECP256R1())
    csr1 = _generate_csr(key1, cn="node-1")

    api_env.resolver.principal = None
    resp1 = await api_env.client.post(
        "/api/v1/agent-runners/enroll",
        json={"enrollment_token": token, "csr_pem": csr1, "hostname": "node-1"},
    )
    assert resp1.status_code == 201

    # Replay: same token second time -> 401 ENROLLMENT_TOKEN_INVALID
    resp_replay = await api_env.client.post(
        "/api/v1/agent-runners/enroll",
        json={"enrollment_token": token, "csr_pem": csr1, "hostname": "node-1-replay"},
    )
    assert resp_replay.status_code == 401
    assert resp_replay.json()["code"] == "ENROLLMENT_TOKEN_INVALID"

    # 2. Expired token: mint token and force expires_at to the past
    admin_client = as_principal(admin, aal_level=2)
    mint_resp2 = await admin_client.post(
        "/api/v1/admin/agent-runners/enrollment-tokens",
        json={"pool_slug": "pool-expired", "ttl_seconds": 60},
    )
    assert mint_resp2.status_code == 201, mint_resp2.text
    token2_id = uuid.UUID(mint_resp2.json()["id"])
    token2 = mint_resp2.json()["enrollment_token"]

    await api_env.seed.execute(
        update(RemoteRunnerEnrollmentToken)
        .where(RemoteRunnerEnrollmentToken.id == token2_id)
        .values(expires_at=datetime.now(UTC) - timedelta(seconds=10))
    )
    await api_env.seed.commit()

    api_env.resolver.principal = None
    resp_expired = await api_env.client.post(
        "/api/v1/agent-runners/enroll",
        json={"enrollment_token": token2, "csr_pem": csr1, "hostname": "node-expired"},
    )
    assert resp_expired.status_code == 401
    assert resp_expired.json()["code"] == "ENROLLMENT_TOKEN_INVALID"

    # 3. CSR requesting basicConstraints CA:TRUE -> 422 CSR_INVALID
    admin_client = as_principal(admin, aal_level=2)
    mint_resp3 = await admin_client.post(
        "/api/v1/admin/agent-runners/enrollment-tokens",
        json={"pool_slug": "pool-bad-csr", "ttl_seconds": 300},
    )
    assert mint_resp3.status_code == 201, mint_resp3.text
    token3 = mint_resp3.json()["enrollment_token"]
    ca_csr = _generate_csr(key1, cn="fake-ca", is_ca=True)

    api_env.resolver.principal = None
    resp_ca = await api_env.client.post(
        "/api/v1/agent-runners/enroll",
        json={"enrollment_token": token3, "csr_pem": ca_csr, "hostname": "fake-ca-node"},
    )
    assert resp_ca.status_code == 422
    assert resp_ca.json()["code"] == "CSR_INVALID"

    # 4. Tampered CSR signature -> 422 CSR_INVALID
    tampered_csr = csr1.replace("A", "B", 10)
    resp_tampered = await api_env.client.post(
        "/api/v1/agent-runners/enroll",
        json={"enrollment_token": token3, "csr_pem": tampered_csr, "hostname": "tampered-node"},
    )
    assert resp_tampered.status_code == 422
    assert resp_tampered.json()["code"] == "CSR_INVALID"

    # 5. Weak RSA key (< 3072, e.g. 2048) -> 422 CSR_INVALID
    weak_rsa = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    weak_csr = _generate_csr(weak_rsa, cn="weak-rsa-node")
    resp_weak = await api_env.client.post(
        "/api/v1/agent-runners/enroll",
        json={"enrollment_token": token3, "csr_pem": weak_csr, "hostname": "weak-rsa-node"},
    )
    assert resp_weak.status_code == 422
    assert resp_weak.json()["code"] == "CSR_INVALID"


@pytest.mark.asyncio
async def test_case_3_ed25519_and_p384_csr_support(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Verify Ed25519 and P-384 CSRs are accepted and signed properly."""
    admin = await make_user("runner-admin-3", workspace_role="WORKSPACE_ADMIN")
    await _enroll_totp(api_env.seed, admin.id)

    # 1. Ed25519 CSR
    admin_client = as_principal(admin, aal_level=2)
    mint1 = await admin_client.post(
        "/api/v1/admin/agent-runners/enrollment-tokens",
        json={"pool_slug": "ed25519-pool", "ttl_seconds": 300},
    )
    assert mint1.status_code == 201, mint1.text
    ed_key = ed25519.Ed25519PrivateKey.generate()
    ed_csr = _generate_csr(ed_key, cn="ed25519-node")

    api_env.resolver.principal = None
    token_ed = mint1.json()["enrollment_token"]
    resp_ed = await api_env.client.post(
        "/api/v1/agent-runners/enroll",
        json={"enrollment_token": token_ed, "csr_pem": ed_csr, "hostname": "ed-box"},
    )
    assert resp_ed.status_code == 201

    # 2. P-384 CSR
    admin_client = as_principal(admin, aal_level=2)
    mint2 = await admin_client.post(
        "/api/v1/admin/agent-runners/enrollment-tokens",
        json={"pool_slug": "p384-pool", "ttl_seconds": 300},
    )
    assert mint2.status_code == 201, mint2.text
    p384_key = ec.generate_private_key(ec.SECP384R1())
    p384_csr = _generate_csr(p384_key, cn="p384-node")

    api_env.resolver.principal = None
    token_p384 = mint2.json()["enrollment_token"]
    resp_p384 = await api_env.client.post(
        "/api/v1/agent-runners/enroll",
        json={"enrollment_token": token_p384, "csr_pem": p384_csr, "hostname": "p384-box"},
    )
    assert resp_p384.status_code == 201


@pytest.mark.asyncio
async def test_case_4_admin_list_and_revoke_routes(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Verify admin listing with filters and revoke endpoint."""
    admin = await make_user("runner-admin-4", workspace_role="WORKSPACE_ADMIN")
    await _enroll_totp(api_env.seed, admin.id)

    # Enroll a runner in pool-alpha
    admin_client = as_principal(admin, aal_level=2)
    m = await admin_client.post(
        "/api/v1/admin/agent-runners/enrollment-tokens",
        json={"pool_slug": "pool-alpha", "ttl_seconds": 300},
    )
    assert m.status_code == 201, m.text
    k = ec.generate_private_key(ec.SECP256R1())
    c = _generate_csr(k, cn="alpha-node")

    api_env.resolver.principal = None
    token_alpha = m.json()["enrollment_token"]
    e = await api_env.client.post(
        "/api/v1/agent-runners/enroll",
        json={"enrollment_token": token_alpha, "csr_pem": c, "hostname": "alpha-node"},
    )
    assert e.status_code == 201
    runner_id = e.json()["runner_id"]

    # 1. List with filter
    admin_client = as_principal(admin, aal_level=2)
    list_resp = await admin_client.get(
        "/api/v1/admin/agent-runners",
        params={"pool_slug": "pool-alpha", "status": "offline"},
    )
    assert list_resp.status_code == 200
    runners = list_resp.json()
    assert any(r["id"] == runner_id for r in runners)

    # List with non-matching pool
    empty_resp = await admin_client.get(
        "/api/v1/admin/agent-runners",
        params={"pool_slug": "other-pool"},
    )
    assert empty_resp.status_code == 200
    assert not any(r["id"] == runner_id for r in empty_resp.json())

    # 2. Revoke runner
    revoke_resp = await admin_client.post(f"/api/v1/admin/agent-runners/{runner_id}:revoke")
    assert revoke_resp.status_code == 200
    assert revoke_resp.json()["status"] == "revoked"

    # Revoke non-existent runner -> 404
    non_existent = str(uuid.uuid4())
    rev_404 = await admin_client.post(f"/api/v1/admin/agent-runners/{non_existent}:revoke")
    assert rev_404.status_code == 404

    # 3. Invalid pool slug on mint -> 422
    bad_mint = await admin_client.post(
        "/api/v1/admin/agent-runners/enrollment-tokens",
        json={"pool_slug": "BAD_SLUG!", "ttl_seconds": 300},
    )
    assert bad_mint.status_code == 422
    assert bad_mint.json()["code"] == "POOL_SLUG_INVALID"


def test_compute_cert_fingerprint_formats() -> None:
    """Verify compute_cert_fingerprint across formats."""
    k = ec.generate_private_key(ec.SECP256R1())
    csr_pem = _generate_csr(k, cn="fp-test")
    km = KeyMaterial(
        master_kek=b"k" * 32,
        auth_pepper=b"p" * 32,
        session_hmac_key=b"s" * 32,
        master_kek_kid="test-kid-1",
    )
    ws_id = uuid.uuid4()
    issued = validate_and_sign_csr(csr_pem, ws_id, "gpu-pool", uuid.uuid4(), km)
    leaf_pem, fp = issued.client_cert_pem, issued.client_cert_sha256

    cert = x509.load_pem_x509_certificate(leaf_pem.encode("utf-8"))
    der_bytes = cert.public_bytes(serialization.Encoding.DER)
    pem_bytes = cert.public_bytes(serialization.Encoding.PEM)

    # 1. bytes PEM
    assert compute_cert_fingerprint(pem_bytes) == fp
    # 2. bytes DER
    assert compute_cert_fingerprint(der_bytes) == fp
    # 3. base64 DER string
    b64_der = base64.b64encode(der_bytes).decode("ascii")
    assert compute_cert_fingerprint(b64_der) == fp
    # 4. hex string
    assert compute_cert_fingerprint(fp.hex()) == fp
    # 5. raw bytes
    assert compute_cert_fingerprint(fp) == fp


def test_csr_crypto_and_policy_rejections() -> None:
    """Verify CSR rejection on weak RSA, invalid curves, CA basicConstraints, and bad signatures."""
    km = KeyMaterial(
        master_kek=b"k" * 32,
        auth_pepper=b"p" * 32,
        session_hmac_key=b"s" * 32,
        master_kek_kid="test-kid-1",
    )
    ws_id = uuid.uuid4()

    # 1. Weak RSA key (< 3072)
    rsa_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    builder = x509.CertificateSigningRequestBuilder().subject_name(
        x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "weak-rsa")])
    )
    weak_rsa_csr = (
        builder.sign(rsa_key, hashes.SHA256())
        .public_bytes(serialization.Encoding.PEM)
        .decode("ascii")
    )
    with pytest.raises(CsrValidationError, match="3072-bit minimum"):
        validate_and_sign_csr(weak_rsa_csr, ws_id, "pool", uuid.uuid4(), km)

    # 2. Disallowed curve (SECP224R1)
    curve_key = ec.generate_private_key(ec.SECP224R1())
    curve_csr = _generate_csr(curve_key, cn="bad-curve")
    with pytest.raises(CsrValidationError, match="not permitted"):
        validate_and_sign_csr(curve_csr, ws_id, "pool", uuid.uuid4(), km)

    # 3. CA:TRUE basic constraints
    ec_key = ec.generate_private_key(ec.SECP256R1())
    ca_builder = (
        x509.CertificateSigningRequestBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "ca-sub")]))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
    )
    ca_csr = (
        ca_builder.sign(ec_key, hashes.SHA256())
        .public_bytes(serialization.Encoding.PEM)
        .decode("ascii")
    )
    with pytest.raises(CsrValidationError, match="CA:TRUE forbidden"):
        validate_and_sign_csr(ca_csr, ws_id, "pool", uuid.uuid4(), km)

    # 4. Tampered signature
    valid_pem = _generate_csr(ec_key, cn="tamper-test")
    valid_csr = x509.load_pem_x509_csr(valid_pem.encode("ascii"))
    der = bytearray(valid_csr.public_bytes(serialization.Encoding.DER))
    der[-5] ^= 0xFF
    b64_tampered = base64.encodebytes(der).decode("ascii")
    tampered_pem = (
        f"-----BEGIN CERTIFICATE REQUEST-----\n{b64_tampered}-----END CERTIFICATE REQUEST-----\n"
    )
    with pytest.raises(CsrValidationError, match="signature verification failed"):
        validate_and_sign_csr(tampered_pem, ws_id, "pool", uuid.uuid4(), km)

    # 5. Valid RSA 3072-bit key CSR succeeds
    rsa_3072 = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    rsa_builder = x509.CertificateSigningRequestBuilder().subject_name(
        x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "valid-rsa")])
    )
    valid_rsa_csr = (
        rsa_builder.sign(rsa_3072, hashes.SHA256())
        .public_bytes(serialization.Encoding.PEM)
        .decode("ascii")
    )
    issued_rsa = validate_and_sign_csr(valid_rsa_csr, ws_id, "pool", uuid.uuid4(), km)
    assert issued_rsa.client_cert_sha256

    # 6. BasicConstraints ca=False succeeds
    leaf_bc_builder = (
        x509.CertificateSigningRequestBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "leaf-bc")]))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=False)
    )
    leaf_bc_csr = (
        leaf_bc_builder.sign(ec_key, hashes.SHA256())
        .public_bytes(serialization.Encoding.PEM)
        .decode("ascii")
    )
    issued_bc = validate_and_sign_csr(leaf_bc_csr, ws_id, "pool", uuid.uuid4(), km)
    assert issued_bc.client_cert_sha256
