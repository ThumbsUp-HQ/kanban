# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
# ruff: noqa: D102, D107, ANN401, PLC0415, PLR0913, SLF001, E501, RUF059
"""Comprehensive unit and integration tests for KAN-64: PKI CA chain, PoP, and anti-hijacking."""

from __future__ import annotations

import asyncio
import base64
import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any, cast

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, ed25519, rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

from kanban.api.v1.remote_runners import remote_runner_websocket_endpoint
from kanban.runners.hub import (
    ChallengeHelloFrame,
    ChallengeResponseFrame,
    HelloAckFrame,
    HelloFrame,
    RunnerAlreadyConnectedError,
    RunnerWssHub,
)
from kanban.runners.pki import (
    CertVerificationError,
    verify_runner_client_cert_chain,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    import httpx

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


class AsyncWsTestClient:
    """In-memory mock WebSocket session for testing remote runner WebSocket endpoint."""

    def __init__(self, app: Any, headers: dict[str, str] | None = None) -> None:
        self.scope = {
            "type": "websocket",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "server": ("127.0.0.1", 80),
            "client": ("127.0.0.1", 12345),
            "scheme": "wss",
            "path": "/api/v1/agent-runners/ws",
            "raw_path": b"/api/v1/agent-runners/ws",
            "query_string": b"",
            "headers": [
                (k.lower().encode("latin-1"), v.encode("latin-1"))
                for k, v in (headers or {}).items()
            ],
            "app": app,
        }
        self.inbound: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self.inbound.put_nowait({"type": "websocket.connect"})
        self.outbound: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        from starlette.websockets import WebSocket

        self.ws = WebSocket(
            self.scope,
            receive=self.inbound.get,
            send=self.outbound.put,  # type: ignore[arg-type]
        )

    async def send_text(self, text: str) -> None:
        await self.inbound.put({"type": "websocket.receive", "text": text})

    async def disconnect(self, code: int = 1000) -> None:
        await self.inbound.put({"type": "websocket.disconnect", "code": code})

    async def receive_msg(self) -> dict[str, Any]:
        return await self.outbound.get()


def _build_test_ca(
    key: ec.EllipticCurvePrivateKey | rsa.RSAPrivateKey | ed25519.Ed25519PrivateKey,
    cn: str = "Test CA",
) -> x509.Certificate:
    """Build a self-signed root CA certificate for testing."""
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])
    now = datetime.now(UTC)
    builder = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=365))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
    )
    if isinstance(key, ed25519.Ed25519PrivateKey):
        return builder.sign(key, None)
    return builder.sign(key, hashes.SHA256())


def _build_test_leaf(
    leaf_key: ec.EllipticCurvePrivateKey | rsa.RSAPrivateKey | ed25519.Ed25519PrivateKey,
    ca_key: ec.EllipticCurvePrivateKey | rsa.RSAPrivateKey | ed25519.Ed25519PrivateKey,
    ca_cert: x509.Certificate,
    *,
    runner_id: uuid.UUID,
    not_before: datetime | None = None,
    not_after: datetime | None = None,
    is_ca: bool = False,
    include_client_auth: bool = True,
    include_bc: bool = True,
    include_eku: bool = True,
    cn_override: str | None = None,
) -> x509.Certificate:
    """Build a leaf certificate signed by ca_key."""
    now = datetime.now(UTC)
    nb = not_before or (now - timedelta(minutes=5))
    na = not_after or (now + timedelta(days=30))
    cn = cn_override if cn_override is not None else f"runner:{runner_id}"

    builder = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)]))
        .issuer_name(ca_cert.subject)
        .public_key(leaf_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(nb)
        .not_valid_after(na)
    )
    if include_bc:
        builder = builder.add_extension(
            x509.BasicConstraints(ca=is_ca, path_length=None), critical=True
        )
    if include_eku:
        ekus = (
            [ExtendedKeyUsageOID.CLIENT_AUTH]
            if include_client_auth
            else [ExtendedKeyUsageOID.SERVER_AUTH]
        )
        builder = builder.add_extension(x509.ExtendedKeyUsage(ekus), critical=False)

    if isinstance(ca_key, ed25519.Ed25519PrivateKey):
        return builder.sign(ca_key, None)
    return builder.sign(ca_key, hashes.SHA256())


# -----------------------------------------------------------------------------
# Action 1: verify_runner_client_cert_chain tests
# -----------------------------------------------------------------------------


def test_verify_cert_chain_valid_active_and_grace_ca() -> None:
    """Verify valid leaf cert against active CA and against grace (previous) CA."""
    runner_id = uuid.uuid4()
    ca_key = ec.generate_private_key(ec.SECP256R1())
    ca_cert = _build_test_ca(ca_key, "Active CA")
    ca_pem = ca_cert.public_bytes(serialization.Encoding.PEM).decode("ascii")

    leaf_key = ec.generate_private_key(ec.SECP256R1())
    leaf_cert = _build_test_leaf(leaf_key, ca_key, ca_cert, runner_id=runner_id)
    leaf_pem = leaf_cert.public_bytes(serialization.Encoding.PEM).decode("ascii")
    leaf_fp = leaf_cert.fingerprint(hashes.SHA256())

    # 1. Active CA verification passes
    verified = verify_runner_client_cert_chain(
        leaf_pem,
        active_ca_cert_pem=ca_pem,
        expected_runner_id=runner_id,
        expected_fingerprint_sha256=leaf_fp.hex(),
    )
    assert verified.serial_number == leaf_cert.serial_number

    # 2. Grace CA verification passes when active CA is rotated
    new_ca_key = ec.generate_private_key(ec.SECP256R1())
    new_ca_cert = _build_test_ca(new_ca_key, "New Active CA")
    new_ca_pem = new_ca_cert.public_bytes(serialization.Encoding.PEM).decode("ascii")

    verified_grace = verify_runner_client_cert_chain(
        leaf_pem,
        active_ca_cert_pem=new_ca_pem,
        previous_ca_cert_pem=ca_pem,
        expected_runner_id=str(runner_id),
        expected_fingerprint_sha256=leaf_fp,
    )
    assert verified_grace.serial_number == leaf_cert.serial_number


def test_verify_cert_chain_der_and_pem_bytes() -> None:
    """Verify verify_runner_client_cert_chain accepts DER bytes and PEM bytes."""
    runner_id = uuid.uuid4()
    ca_key = ec.generate_private_key(ec.SECP256R1())
    ca_cert = _build_test_ca(ca_key)
    ca_pem = ca_cert.public_bytes(serialization.Encoding.PEM)

    leaf_key = ec.generate_private_key(ec.SECP256R1())
    leaf_cert = _build_test_leaf(leaf_key, ca_key, ca_cert, runner_id=runner_id)
    leaf_der = leaf_cert.public_bytes(serialization.Encoding.DER)
    leaf_pem_bytes = leaf_cert.public_bytes(serialization.Encoding.PEM)
    leaf_fp = leaf_cert.fingerprint(hashes.SHA256())

    # DER bytes
    v1 = verify_runner_client_cert_chain(
        leaf_der,
        active_ca_cert_pem=ca_pem,
        expected_runner_id=runner_id,
        expected_fingerprint_sha256=leaf_fp,
    )
    assert v1.serial_number == leaf_cert.serial_number

    # PEM bytes
    v2 = verify_runner_client_cert_chain(
        leaf_pem_bytes,
        active_ca_cert_pem=ca_pem.decode("ascii"),
        expected_runner_id=runner_id,
        expected_fingerprint_sha256=leaf_fp.hex(),
    )
    assert v2.serial_number == leaf_cert.serial_number


def test_verify_cert_chain_multiple_algorithms() -> None:
    """Verify support for RSA (3072-bit), Ed25519, and ECDSA CA/leaf keys."""
    runner_id = uuid.uuid4()

    # Ed25519 CA and leaf
    ed_ca_key = ed25519.Ed25519PrivateKey.generate()
    ed_ca_cert = _build_test_ca(ed_ca_key)
    ed_leaf_key = ed25519.Ed25519PrivateKey.generate()
    ed_leaf_cert = _build_test_leaf(ed_leaf_key, ed_ca_key, ed_ca_cert, runner_id=runner_id)
    v_ed = verify_runner_client_cert_chain(
        ed_leaf_cert.public_bytes(serialization.Encoding.PEM).decode("ascii"),
        active_ca_cert_pem=ed_ca_cert.public_bytes(serialization.Encoding.PEM).decode("ascii"),
        expected_runner_id=runner_id,
        expected_fingerprint_sha256=ed_leaf_cert.fingerprint(hashes.SHA256()),
    )
    assert v_ed.serial_number == ed_leaf_cert.serial_number

    # RSA 3072 CA and leaf
    rsa_ca_key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    rsa_ca_cert = _build_test_ca(rsa_ca_key)
    rsa_leaf_key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    rsa_leaf_cert = _build_test_leaf(rsa_leaf_key, rsa_ca_key, rsa_ca_cert, runner_id=runner_id)
    v_rsa = verify_runner_client_cert_chain(
        rsa_leaf_cert.public_bytes(serialization.Encoding.PEM).decode("ascii"),
        active_ca_cert_pem=rsa_ca_cert.public_bytes(serialization.Encoding.PEM).decode("ascii"),
        expected_runner_id=runner_id,
        expected_fingerprint_sha256=rsa_leaf_cert.fingerprint(hashes.SHA256()),
    )
    assert v_rsa.serial_number == rsa_leaf_cert.serial_number


def test_verify_cert_chain_rejections() -> None:
    """Test policy rejections: fingerprint mismatch, CN mismatch, ca=True, missing EKU, expiry."""
    runner_id = uuid.uuid4()
    ca_key = ec.generate_private_key(ec.SECP256R1())
    ca_cert = _build_test_ca(ca_key)
    ca_pem = ca_cert.public_bytes(serialization.Encoding.PEM).decode("ascii")

    leaf_key = ec.generate_private_key(ec.SECP256R1())
    valid_leaf = _build_test_leaf(leaf_key, ca_key, ca_cert, runner_id=runner_id)
    valid_pem = valid_leaf.public_bytes(serialization.Encoding.PEM).decode("ascii")
    valid_fp = valid_leaf.fingerprint(hashes.SHA256())

    # 1. Fingerprint mismatch
    with pytest.raises(CertVerificationError) as exc_fp:
        verify_runner_client_cert_chain(
            valid_pem,
            active_ca_cert_pem=ca_pem,
            expected_runner_id=runner_id,
            expected_fingerprint_sha256=b"\x00" * 32,
        )
    assert exc_fp.value.code == "FINGERPRINT_MISMATCH"

    # 2. Subject CN mismatch
    with pytest.raises(CertVerificationError) as exc_cn:
        verify_runner_client_cert_chain(
            valid_pem,
            active_ca_cert_pem=ca_pem,
            expected_runner_id=uuid.uuid4(),
            expected_fingerprint_sha256=valid_fp,
        )
    assert exc_cn.value.code == "SUBJECT_MISMATCH"

    # 3. BasicConstraints ca=True
    ca_flag_leaf = _build_test_leaf(leaf_key, ca_key, ca_cert, runner_id=runner_id, is_ca=True)
    with pytest.raises(CertVerificationError) as exc_bc:
        verify_runner_client_cert_chain(
            ca_flag_leaf.public_bytes(serialization.Encoding.PEM).decode("ascii"),
            active_ca_cert_pem=ca_pem,
            expected_runner_id=runner_id,
            expected_fingerprint_sha256=ca_flag_leaf.fingerprint(hashes.SHA256()),
        )
    assert exc_bc.value.code == "BASIC_CONSTRAINTS_INVALID"

    # 4. Missing BasicConstraints
    no_bc_leaf = _build_test_leaf(leaf_key, ca_key, ca_cert, runner_id=runner_id, include_bc=False)
    with pytest.raises(CertVerificationError) as exc_no_bc:
        verify_runner_client_cert_chain(
            no_bc_leaf.public_bytes(serialization.Encoding.PEM).decode("ascii"),
            active_ca_cert_pem=ca_pem,
            expected_runner_id=runner_id,
            expected_fingerprint_sha256=no_bc_leaf.fingerprint(hashes.SHA256()),
        )
    assert exc_no_bc.value.code == "BASIC_CONSTRAINTS_MISSING"

    # 5. Invalid ExtendedKeyUsage (SERVER_AUTH only)
    no_cli_leaf = _build_test_leaf(
        leaf_key, ca_key, ca_cert, runner_id=runner_id, include_client_auth=False
    )
    with pytest.raises(CertVerificationError) as exc_eku:
        verify_runner_client_cert_chain(
            no_cli_leaf.public_bytes(serialization.Encoding.PEM).decode("ascii"),
            active_ca_cert_pem=ca_pem,
            expected_runner_id=runner_id,
            expected_fingerprint_sha256=no_cli_leaf.fingerprint(hashes.SHA256()),
        )
    assert exc_eku.value.code == "EXTENDED_KEY_USAGE_INVALID"

    # 6. Missing ExtendedKeyUsage
    no_eku_leaf = _build_test_leaf(
        leaf_key, ca_key, ca_cert, runner_id=runner_id, include_eku=False
    )
    with pytest.raises(CertVerificationError) as exc_no_eku:
        verify_runner_client_cert_chain(
            no_eku_leaf.public_bytes(serialization.Encoding.PEM).decode("ascii"),
            active_ca_cert_pem=ca_pem,
            expected_runner_id=runner_id,
            expected_fingerprint_sha256=no_eku_leaf.fingerprint(hashes.SHA256()),
        )
    assert exc_no_eku.value.code == "EXTENDED_KEY_USAGE_MISSING"

    # 7. Expired cert
    now = datetime.now(UTC)
    expired_leaf = _build_test_leaf(
        leaf_key,
        ca_key,
        ca_cert,
        runner_id=runner_id,
        not_before=now - timedelta(days=60),
        not_after=now - timedelta(days=1),
    )
    with pytest.raises(CertVerificationError) as exc_exp:
        verify_runner_client_cert_chain(
            expired_leaf.public_bytes(serialization.Encoding.PEM).decode("ascii"),
            active_ca_cert_pem=ca_pem,
            expected_runner_id=runner_id,
            expected_fingerprint_sha256=expired_leaf.fingerprint(hashes.SHA256()),
        )
    assert exc_exp.value.code == "CERT_EXPIRED"

    # 8. Not yet valid cert
    future_leaf = _build_test_leaf(
        leaf_key,
        ca_key,
        ca_cert,
        runner_id=runner_id,
        not_before=now + timedelta(days=1),
        not_after=now + timedelta(days=60),
    )
    with pytest.raises(CertVerificationError) as exc_fut:
        verify_runner_client_cert_chain(
            future_leaf.public_bytes(serialization.Encoding.PEM).decode("ascii"),
            active_ca_cert_pem=ca_pem,
            expected_runner_id=runner_id,
            expected_fingerprint_sha256=future_leaf.fingerprint(hashes.SHA256()),
        )
    assert exc_fut.value.code == "CERT_NOT_YET_VALID"

    # 9. Untrusted CA
    other_ca_key = ec.generate_private_key(ec.SECP256R1())
    other_ca_cert = _build_test_ca(other_ca_key, "Other CA")
    other_ca_pem = other_ca_cert.public_bytes(serialization.Encoding.PEM).decode("ascii")
    with pytest.raises(CertVerificationError) as exc_sig:
        verify_runner_client_cert_chain(
            valid_pem,
            active_ca_cert_pem=other_ca_pem,
            expected_runner_id=runner_id,
            expected_fingerprint_sha256=valid_fp,
        )
    assert exc_sig.value.code == "ISSUER_SIGNATURE_INVALID"


# -----------------------------------------------------------------------------
# Action 3: RunnerHub duplicate slot anti-hijacking tests
# -----------------------------------------------------------------------------


def test_hub_anti_hijacking_already_connected() -> None:
    """Action 3: RunnerHub.register rejects active slot overwrites with RunnerAlreadyConnectedError."""
    hub = RunnerWssHub()
    runner_id = uuid.uuid4()
    workspace_id = uuid.uuid4()
    mock_ws1 = cast("Any", object())
    mock_ws2 = cast("Any", object())

    # 1. Initial registration succeeds
    runner1 = hub.register_runner(
        runner_id=runner_id,
        workspace_id=workspace_id,
        pool_slug="test-pool",
        hostname="node-1",
        websocket=mock_ws1,
    )
    assert runner1.status == "online"
    assert runner_id in hub._connections

    # 2. Second register with same runner_id raises RunnerAlreadyConnectedError
    with pytest.raises(RunnerAlreadyConnectedError) as exc:
        hub.register_runner(
            runner_id=runner_id,
            workspace_id=workspace_id,
            pool_slug="test-pool",
            hostname="node-2-hijacker",
            websocket=mock_ws2,
        )
    assert exc.value.code == "ALREADY_CONNECTED"

    # hub.register alias works identically
    with pytest.raises(RunnerAlreadyConnectedError):
        hub.register(
            runner_id=runner_id,
            workspace_id=workspace_id,
            pool_slug="test-pool",
            hostname="node-3-hijacker",
            websocket=mock_ws2,
        )

    # 3. Disconnect / unregister allows subsequent registration
    hub.unregister_runner(runner_id)
    runner2 = hub.register(
        runner_id=runner_id,
        workspace_id=workspace_id,
        pool_slug="test-pool",
        hostname="node-reconnect",
        websocket=mock_ws2,
    )
    assert runner2.hostname == "node-reconnect"


# -----------------------------------------------------------------------------
# Action 2: WebSocket PoP Challenge-Response & CA Integration tests
# -----------------------------------------------------------------------------


async def _setup_enrolled_runner_with_bundle(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> tuple[str, uuid.UUID, str, str, ec.EllipticCurvePrivateKey, Any]:
    """Enroll a runner returning (runner_id_str, runner_uuid, leaf_pem, fp_hex, leaf_key, app)."""
    admin = await make_user(f"rnr-adm-{uuid.uuid4().hex[:6]}", workspace_role="WORKSPACE_ADMIN")
    from kanban.tests.runners.test_wss_hub import _enroll_totp

    await _enroll_totp(api_env.seed, admin.id)

    admin_client = as_principal(admin, aal_level=2)
    mint_resp = await admin_client.post(
        "/api/v1/admin/agent-runners/enrollment-tokens",
        json={"pool_slug": "pop-pool", "ttl_seconds": 300},
    )
    token = mint_resp.json()["enrollment_token"]

    runner_key = ec.generate_private_key(ec.SECP256R1())
    csr_builder = x509.CertificateSigningRequestBuilder().subject_name(
        x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "pop-node")])
    )
    csr_pem = (
        csr_builder.sign(runner_key, hashes.SHA256())
        .public_bytes(serialization.Encoding.PEM)
        .decode("ascii")
    )

    api_env.resolver.principal = None
    enroll_resp = await api_env.client.post(
        "/api/v1/agent-runners/enroll",
        json={"enrollment_token": token, "csr_pem": csr_pem, "hostname": "pop-node"},
    )
    assert enroll_resp.status_code == 201
    data = enroll_resp.json()
    runner_id_str = data["runner_id"]
    runner_uuid = uuid.UUID(runner_id_str)
    leaf_pem = data["client_cert_pem"]
    leaf_cert = x509.load_pem_x509_certificate(leaf_pem.encode("ascii"))
    fp_hex = leaf_cert.fingerprint(hashes.SHA256()).hex()

    transport = cast("Any", api_env.client._transport)
    return runner_id_str, runner_uuid, leaf_pem, fp_hex, runner_key, transport.app


@pytest.mark.asyncio
async def test_websocket_pop_success_lifecycle(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Action 2: Full positive PoP challenge-response handshake over WebSocket."""
    (
        runner_id_str,
        runner_uuid,
        leaf_pem,
        fp_hex,
        runner_key,
        app,
    ) = await _setup_enrolled_runner_with_bundle(api_env, make_user, as_principal)

    client = AsyncWsTestClient(app, headers={"x-client-cert-pem": leaf_pem})
    task = asyncio.create_task(remote_runner_websocket_endpoint(client.ws))

    # 1. Server accepts websocket
    accept_msg = await client.receive_msg()
    assert accept_msg["type"] == "websocket.accept"

    # 2. Server sends challenge_hello with 32-byte hex nonce
    ch_msg = await client.receive_msg()
    assert ch_msg["type"] == "websocket.send"
    ch_data = json.loads(ch_msg["text"])
    challenge = ChallengeHelloFrame.model_validate(ch_data)
    assert challenge.runner_id == runner_uuid
    assert len(challenge.nonce) == 64

    # 3. Client signs challenge over kb-runner-pop-v1:{runner_id}:{nonce}:{cert_sha256}
    pop_payload = f"kb-runner-pop-v1:{runner_uuid}:{challenge.nonce}:{fp_hex}".encode()
    sig = runner_key.sign(pop_payload, ec.ECDSA(hashes.SHA256()))
    sig_b64 = base64.b64encode(sig).decode("ascii")

    resp_frame = ChallengeResponseFrame(signature_b64=sig_b64)
    await client.send_text(resp_frame.model_dump_json())

    # 4. Client sends HelloFrame
    hello = HelloFrame(
        schema="kb-runner-ws/v1",
        runner_id=runner_uuid,
        max_concurrency=2,
        capabilities={"os": "linux"},
    )
    await client.send_text(hello.model_dump_json(by_alias=True))

    # 5. Server responds with HelloAckFrame
    ack_msg = await client.receive_msg()
    assert ack_msg["type"] == "websocket.send"
    ack_data = json.loads(ack_msg["text"])
    ack = HelloAckFrame.model_validate(ack_data)
    assert ack.heartbeat_interval_s == 15

    # 6. Verify runner registered in global hub
    from kanban.runners.hub import get_global_hub

    hub = get_global_hub()
    assert runner_uuid in hub._connections
    assert hub._connections[runner_uuid].status == "online"

    # Clean disconnect
    await client.disconnect()
    await task


@pytest.mark.asyncio
async def test_websocket_pop_invalid_signature_rejection(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Action 2: Corrupted or forged PoP signature rejected with close code 4401."""
    (
        runner_id_str,
        runner_uuid,
        leaf_pem,
        fp_hex,
        runner_key,
        app,
    ) = await _setup_enrolled_runner_with_bundle(api_env, make_user, as_principal)

    client = AsyncWsTestClient(app, headers={"x-client-cert-pem": leaf_pem})
    task = asyncio.create_task(remote_runner_websocket_endpoint(client.ws))

    await client.receive_msg()  # accept
    ch_msg = await client.receive_msg()  # challenge_hello
    ch_data = json.loads(ch_msg["text"])

    # Wrong key signs challenge
    attacker_key = ec.generate_private_key(ec.SECP256R1())
    pop_payload = f"kb-runner-pop-v1:{runner_uuid}:{ch_data['nonce']}:{fp_hex}".encode()
    forged_sig = attacker_key.sign(pop_payload, ec.ECDSA(hashes.SHA256()))

    resp_frame = ChallengeResponseFrame(signature_b64=base64.b64encode(forged_sig).decode("ascii"))
    await client.send_text(resp_frame.model_dump_json())

    # Server must close with 4401
    close_msg = await client.receive_msg()
    assert close_msg["type"] == "websocket.close"
    assert close_msg["code"] == 4401
    await task


@pytest.mark.asyncio
async def test_websocket_slot_hijacking_4409_close(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Action 3: Inbound WebSocket connection for already connected slot rejected with 4409."""
    (
        runner_id_str,
        runner_uuid,
        leaf_pem,
        fp_hex,
        runner_key,
        app,
    ) = await _setup_enrolled_runner_with_bundle(api_env, make_user, as_principal)

    # First runner connects and completes handshake
    c1 = AsyncWsTestClient(app, headers={"x-client-cert-pem": leaf_pem})
    t1 = asyncio.create_task(remote_runner_websocket_endpoint(c1.ws))
    await c1.receive_msg()  # accept
    ch_msg = await c1.receive_msg()
    ch_data = json.loads(ch_msg["text"])
    pop_payload = f"kb-runner-pop-v1:{runner_uuid}:{ch_data['nonce']}:{fp_hex}".encode()
    sig = runner_key.sign(pop_payload, ec.ECDSA(hashes.SHA256()))
    await c1.send_text(
        ChallengeResponseFrame(
            signature_b64=base64.b64encode(sig).decode("ascii")
        ).model_dump_json()
    )
    await c1.send_text(
        HelloFrame(
            schema="kb-runner-ws/v1", runner_id=runner_uuid, max_concurrency=1
        ).model_dump_json(by_alias=True)
    )
    await c1.receive_msg()  # hello_ack

    # Second runner attempts to connect with same certificate / runner slot
    c2 = AsyncWsTestClient(app, headers={"x-client-cert-pem": leaf_pem})
    t2 = asyncio.create_task(remote_runner_websocket_endpoint(c2.ws))
    await c2.receive_msg()  # accept
    ch2_msg = await c2.receive_msg()
    ch2_data = json.loads(ch2_msg["text"])
    pop2_payload = f"kb-runner-pop-v1:{runner_uuid}:{ch2_data['nonce']}:{fp_hex}".encode()
    sig2 = runner_key.sign(pop2_payload, ec.ECDSA(hashes.SHA256()))
    await c2.send_text(
        ChallengeResponseFrame(
            signature_b64=base64.b64encode(sig2).decode("ascii")
        ).model_dump_json()
    )
    await c2.send_text(
        HelloFrame(
            schema="kb-runner-ws/v1", runner_id=runner_uuid, max_concurrency=1
        ).model_dump_json(by_alias=True)
    )

    # Server must close second connection with code 4409 ALREADY_CONNECTED
    close_msg = await c2.receive_msg()
    assert close_msg["type"] == "websocket.close"
    assert close_msg["code"] == 4409
    assert close_msg["reason"] == "ALREADY_CONNECTED"
    await t2

    # Clean up first client
    await c1.disconnect()
    await t1
