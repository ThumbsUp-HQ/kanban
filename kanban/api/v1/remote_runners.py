# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""REST & WebSocket endpoints for remote runner registry and hub (KB-P5-22a, S14.2, S11.4)."""

from __future__ import annotations

import asyncio
import base64
import contextlib
import hashlib
import json
import logging
import re
import secrets
import urllib.parse
import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, Final

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, ed25519, padding, rsa
from fastapi import APIRouter, Depends, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.websockets import WebSocket, WebSocketDisconnect

from database.models.remote_runner import RemoteRunner, RemoteRunnerEnrollmentToken
from database.session import RLSContext, RLSSessionFactory
from kanban.api.deps import PrincipalContext, get_rls_session
from kanban.api.problems import ProblemException, not_found
from kanban.auth.mfa.policy import require_admin_aal2
from kanban.runners.hub import (
    MAX_FRAME_BYTES,
    ChallengeHelloFrame,
    ChallengeResponseFrame,
    HelloAckFrame,
    HelloFrame,
    RunnerAlreadyConnectedError,
    get_global_hub,
)
from kanban.runners.pki import (
    CertVerificationError,
    CsrValidationError,
    compute_cert_fingerprint,
    derive_runner_ca,
    validate_and_sign_csr,
    verify_runner_client_cert_chain,
)
from kanban.security.keys import KeyMaterial, load_key_material

logger = logging.getLogger(__name__)

_POOL_SLUG_REGEX: Final[re.Pattern[str]] = re.compile(r"^[a-z0-9][a-z0-9-]{1,62}$")
_ENROLL_TOKEN_PREFIX: Final[str] = "kb_rnr_enroll_"  # noqa: S105

router = APIRouter(tags=["remote-runners"])
admin_router = APIRouter(
    prefix="/admin/agent-runners",
    tags=["admin-agent-runners"],
    dependencies=[Depends(require_admin_aal2)],
)

Caller = Annotated[PrincipalContext, Depends(require_admin_aal2)]
Session = Annotated[AsyncSession, Depends(get_rls_session)]


# --- Schemas ---


class MintEnrollmentTokenRequest(BaseModel):
    """Payload to mint a new runner enrollment token."""

    model_config = ConfigDict(extra="forbid")

    pool_slug: str = Field(min_length=2, max_length=63)
    ttl_seconds: int = Field(default=900, ge=60, le=900)


class EnrollmentTokenResponse(BaseModel):
    """Single-use enrollment token response returned only once at creation."""

    id: uuid.UUID
    pool_slug: str
    enrollment_token: str
    expires_at: datetime
    created_at: datetime


class RemoteRunnerResponse(BaseModel):
    """Public representation of registered remote runner."""

    id: uuid.UUID
    workspace_id: uuid.UUID
    pool_slug: str
    hostname: str
    client_cert_sha256_hex: str
    cert_expires_at: datetime
    capabilities: dict[str, Any]
    status: str
    last_heartbeat_at: datetime | None
    revoked_at: datetime | None
    created_at: datetime


class EnrollRunnerRequest(BaseModel):
    """Payload for runner CSR exchange."""

    model_config = ConfigDict(extra="forbid")

    enrollment_token: str
    csr_pem: str
    hostname: str = Field(min_length=1, max_length=253)
    capabilities: dict[str, Any] = Field(default_factory=dict)


class EnrollRunnerResponse(BaseModel):
    """Issued client certificates and WSS connection URL for runner."""

    runner_id: uuid.UUID
    client_cert_pem: str
    ca_cert_pem: str
    wss_url: str


# --- Admin Routes (require_admin_aal2) ---


@admin_router.post(
    "/enrollment-tokens",
    status_code=status.HTTP_201_CREATED,
    response_model=EnrollmentTokenResponse,
    summary="Mint a single-use mTLS runner enrollment token",
)
async def mint_enrollment_token(
    body: MintEnrollmentTokenRequest,
    caller: Caller,
    session: Session,
) -> EnrollmentTokenResponse:
    """Mint single-use runner enrollment token valid for 60..900s."""
    if not _POOL_SLUG_REGEX.match(body.pool_slug):
        msg = f"Invalid pool slug '{body.pool_slug}': must match ^[a-z0-9][a-z0-9-]{{1,62}}$"
        code = "POOL_SLUG_INVALID"
        title = "Invalid Pool Slug"
        raise ProblemException(
            status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            code=code,
            title=title,
            detail=msg,
        )

    b64_raw = secrets.token_urlsafe(32)
    plaintext_token = f"{_ENROLL_TOKEN_PREFIX}{b64_raw}"
    token_sha256 = hashlib.sha256(plaintext_token.encode("ascii")).digest()

    now = datetime.now(UTC)
    expires_at = now + timedelta(seconds=body.ttl_seconds)

    record = RemoteRunnerEnrollmentToken(
        workspace_id=caller.workspace_id,
        pool_slug=body.pool_slug,
        token_sha256=token_sha256,
        created_by_id=caller.principal_id,
        expires_at=expires_at,
        created_at=now,
    )
    session.add(record)
    await session.flush()

    return EnrollmentTokenResponse(
        id=record.id,
        pool_slug=record.pool_slug,
        enrollment_token=plaintext_token,
        expires_at=record.expires_at,
        created_at=record.created_at,
    )


@admin_router.get(
    "",
    response_model=list[RemoteRunnerResponse],
    summary="List registered remote runners in workspace",
)
async def list_remote_runners(
    caller: Caller,
    session: Session,
    pool_slug: Annotated[str | None, Query()] = None,
    runner_status: Annotated[str | None, Query(alias="status")] = None,
) -> list[RemoteRunnerResponse]:
    """List registered runners with optional pool_slug and status filtering."""
    stmt = (
        select(RemoteRunner)
        .where(RemoteRunner.workspace_id == caller.workspace_id)
        .order_by(RemoteRunner.created_at.desc())
    )
    if pool_slug is not None:
        stmt = stmt.where(RemoteRunner.pool_slug == pool_slug)
    if runner_status is not None:
        stmt = stmt.where(RemoteRunner.status == runner_status)

    runners = (await session.execute(stmt)).scalars().all()
    return [
        RemoteRunnerResponse(
            id=r.id,
            workspace_id=r.workspace_id,
            pool_slug=r.pool_slug,
            hostname=r.hostname,
            client_cert_sha256_hex=r.client_cert_sha256.hex(),
            cert_expires_at=r.cert_expires_at,
            capabilities=r.capabilities_json,
            status=r.status,
            last_heartbeat_at=r.last_heartbeat_at,
            revoked_at=r.revoked_at,
            created_at=r.created_at,
        )
        for r in runners
    ]


@admin_router.post(
    "/{runner_id}:revoke",
    response_model=dict[str, Any],
    summary="Revoke remote runner certificate and disconnect active session",
)
async def revoke_remote_runner(
    runner_id: uuid.UUID,
    caller: Caller,
    session: Session,
) -> dict[str, Any]:
    """Revoke runner credentials, disconnect active WebSocket, and cancel in-flight jobs."""
    stmt = select(RemoteRunner).where(
        RemoteRunner.id == runner_id,
        RemoteRunner.workspace_id == caller.workspace_id,
    )
    runner = (await session.execute(stmt)).scalar_one_or_none()
    if runner is None:
        raise not_found()

    now = datetime.now(UTC)
    runner.status = "revoked"
    runner.revoked_at = now
    runner.revoked_by_id = caller.principal_id
    await session.flush()

    hub = get_global_hub()
    await hub.revoke_runner(runner_id)

    return {
        "id": str(runner.id),
        "status": "revoked",
        "revoked_at": runner.revoked_at.isoformat(),
    }


# --- Public / Runner Routes ---


@router.post(
    "/agent-runners/enroll",
    status_code=status.HTTP_201_CREATED,
    response_model=EnrollRunnerResponse,
    summary="Exchange enrollment token and CSR for mTLS leaf certificate",
)
async def enroll_remote_runner_endpoint(
    body: EnrollRunnerRequest,
    request: Request,
) -> EnrollRunnerResponse:
    """Consume single-use token, validate CSR, sign leaf cert, and register runner."""
    raw_token = body.enrollment_token.strip()
    token_sha256 = hashlib.sha256(raw_token.encode("ascii")).digest()

    session_factory: RLSSessionFactory | None = getattr(request.app.state, "session_factory", None)
    if session_factory is None:
        msg = "RLS session factory not configured on app.state.session_factory"
        raise RuntimeError(msg)

    key_material: KeyMaterial | None = getattr(request.app.state, "key_material", None)
    if key_material is None:
        key_material = load_key_material()

    anon_ctx = RLSContext(principal_id=uuid.UUID(int=0), workspace_id=uuid.UUID(int=0))
    async with session_factory.session(anon_ctx) as session:
        # 1. Atomically consume token via SECURITY DEFINER helper
        consume_stmt = text(
            "SELECT token_id, workspace_id, pool_slug "
            "FROM consume_runner_enrollment_token(:token_sha256)"
        )
        res = await session.execute(consume_stmt, {"token_sha256": token_sha256})
        row = res.first()
        if row is None:
            code = "ENROLLMENT_TOKEN_INVALID"
            title = "Enrollment Token Invalid"
            detail = "Enrollment token is expired, already consumed, or invalid."
            raise ProblemException(
                status=status.HTTP_401_UNAUTHORIZED,
                code=code,
                title=title,
                detail=detail,
            )

        token_id, workspace_id, pool_slug = row[0], row[1], row[2]
        runner_id = uuid.uuid4()

        # 2. Validate PKCS#10 CSR and sign leaf certificate
        try:
            cert_bundle = validate_and_sign_csr(
                body.csr_pem,
                workspace_id=workspace_id,
                pool_slug=pool_slug,
                runner_id=runner_id,
                key_material=key_material,
            )
        except CsrValidationError as exc:
            title = "CSR Validation Failed"
            raise ProblemException(
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
                code=exc.code,
                title=title,
                detail=exc.detail,
            ) from exc

        # 3. Register runner in remote_runners table
        reg_stmt = text(
            "SELECT register_remote_runner("
            ":runner_id, :workspace_id, :pool_slug, :hostname, "
            ":client_cert_sha256, :cert_expires_at, :capabilities_json, :token_id"
            ")"
        )
        await session.execute(
            reg_stmt,
            {
                "runner_id": runner_id,
                "workspace_id": workspace_id,
                "pool_slug": pool_slug,
                "hostname": body.hostname.strip(),
                "client_cert_sha256": cert_bundle.client_cert_sha256,
                "cert_expires_at": cert_bundle.cert_expires_at,
                "capabilities_json": json.dumps(body.capabilities),
                "token_id": token_id,
            },
        )

    return EnrollRunnerResponse(
        runner_id=runner_id,
        client_cert_pem=cert_bundle.client_cert_pem,
        ca_cert_pem=cert_bundle.ca_cert_pem,
        wss_url="/api/v1/agent-runners/ws",
    )


def _extract_peer_cert_and_fingerprint(
    websocket: WebSocket,
) -> tuple[str | bytes | None, bytes | None]:
    """Extract raw peer certificate bytes/PEM and SHA-256 fingerprint from headers or scope."""
    for header in (
        "x-client-cert-pem",
        "x-client-cert",
        "ssl-client-cert",
        "x-ssl-cert",
        "x-forwarded-tls-client-cert",
    ):
        val = websocket.headers.get(header)
        if val:
            if "%" in val:
                val = urllib.parse.unquote(val)
            with contextlib.suppress(Exception):
                fp = compute_cert_fingerprint(val)
                return val, fp

    client_cert = websocket.scope.get("client_cert") or websocket.scope.get("tls_client_cert")
    if client_cert:
        with contextlib.suppress(Exception):
            fp = compute_cert_fingerprint(client_cert)
            return client_cert, fp

    transport = websocket.scope.get("transport")
    if transport is not None:
        ssl_obj = getattr(transport, "get_extra_info", lambda _: None)("ssl_object")
        if ssl_obj is not None:
            with contextlib.suppress(Exception):
                der = ssl_obj.getpeercert(binary_form=True)
                if der:
                    return der, compute_cert_fingerprint(der)

    for header in (
        "x-client-cert-sha256",
        "ssl-client-cert-sha256",
        "x-forwarded-tls-client-cert-sha256",
        "x-ssl-client-sha256",
    ):
        val = websocket.headers.get(header)
        if val:
            with contextlib.suppress(Exception):
                return None, compute_cert_fingerprint(val)

    return None, None


def _extract_peer_cert_fingerprint(websocket: WebSocket) -> bytes | None:
    """Extract SHA-256 certificate fingerprint from verified proxy headers or TLS scope."""
    _, fp = _extract_peer_cert_and_fingerprint(websocket)
    return fp


def _verify_pop_signature(
    pubkey: object,
    signature: bytes,
    message: bytes,
) -> None:
    """Verify Proof-of-Possession signature against ECDSA, Ed25519, or RSA public key."""
    if isinstance(pubkey, ec.EllipticCurvePublicKey):
        pubkey.verify(signature, message, ec.ECDSA(hashes.SHA256()))
    elif isinstance(pubkey, ed25519.Ed25519PublicKey):
        pubkey.verify(signature, message)
    elif isinstance(pubkey, rsa.RSAPublicKey):
        try:
            pubkey.verify(
                signature,
                message,
                padding.PSS(
                    mgf=padding.MGF1(hashes.SHA256()),
                    salt_length=padding.PSS.MAX_LENGTH,
                ),
                hashes.SHA256(),
            )
        except (InvalidSignature, ValueError):
            pubkey.verify(signature, message, padding.PKCS1v15(), hashes.SHA256())
    else:
        msg = f"Unsupported public key type: {type(pubkey).__name__}"
        raise TypeError(msg)


@router.websocket("/agent-runners/ws")
async def remote_runner_websocket_endpoint(  # noqa: C901, PLR0911, PLR0912, PLR0915
    websocket: WebSocket,
) -> None:
    """WebSocket control hub connection endpoint authenticated via mTLS peer certificate."""
    raw_cert, cert_sha256 = _extract_peer_cert_and_fingerprint(websocket)
    if cert_sha256 is None:
        await websocket.close(code=4401, reason="peer certificate required")
        return

    session_factory: RLSSessionFactory | None = getattr(
        websocket.app.state, "session_factory", None
    )
    if session_factory is None:
        await websocket.close(code=1011, reason="internal server error")
        return

    anon_ctx = RLSContext(principal_id=uuid.UUID(int=0), workspace_id=uuid.UUID(int=0))
    async with session_factory.session(anon_ctx) as session:
        lookup_stmt = text(
            "SELECT runner_id, workspace_id, pool_slug, hostname, "
            "status, cert_expires_at, capabilities_json "
            "FROM get_runner_by_cert_sha256(:cert_sha256)"
        )
        res = await session.execute(lookup_stmt, {"cert_sha256": cert_sha256})
        row = res.first()

    if row is None:
        await websocket.close(code=4401, reason="unregistered certificate")
        return

    runner_id, workspace_id, pool_slug, hostname, runner_status, cert_expires_at, capabilities = (
        row[0],
        row[1],
        row[2],
        row[3],
        row[4],
        row[5],
        row[6],
    )

    if runner_status == "revoked":
        await websocket.close(code=4003, reason="runner revoked")
        return

    if cert_expires_at <= datetime.now(UTC):
        await websocket.close(code=4401, reason="certificate expired")
        return

    leaf_cert = None
    if raw_cert is not None:
        key_material: KeyMaterial | None = getattr(websocket.app.state, "key_material", None)
        if key_material is None:
            key_material = load_key_material()
        ca_cert, _ = derive_runner_ca(key_material, workspace_id)
        active_ca_pem = ca_cert.public_bytes(serialization.Encoding.PEM).decode("ascii")

        try:
            leaf_cert = verify_runner_client_cert_chain(
                raw_cert,
                active_ca_cert_pem=active_ca_pem,
                expected_runner_id=runner_id,
                expected_fingerprint_sha256=cert_sha256,
            )
        except CertVerificationError as exc:
            await websocket.close(code=4401, reason=f"certificate verification failed: {exc.code}")
            return

    await websocket.accept()

    stashed_hello: str | None = None
    if leaf_cert is not None:
        nonce = secrets.token_hex(32)
        challenge = ChallengeHelloFrame(nonce=nonce, runner_id=runner_id)
        await websocket.send_text(challenge.model_dump_json())

        try:
            async with asyncio.timeout(5.0):
                while True:
                    incoming = await websocket.receive_text()
                    if len(incoming.encode("utf-8")) > MAX_FRAME_BYTES:
                        await websocket.close(code=1009, reason="frame too large")
                        return
                    data = json.loads(incoming)
                    msg_type = data.get("type")
                    if msg_type == "challenge_response":
                        pop_resp = ChallengeResponseFrame.model_validate(data)
                        sig_bytes = base64.b64decode(pop_resp.signature_b64)
                        expected_msg = (
                            f"kb-runner-pop-v1:{runner_id}:{nonce}:{cert_sha256.hex()}".encode()
                        )
                        _verify_pop_signature(leaf_cert.public_key(), sig_bytes, expected_msg)
                        break
                    if msg_type == "hello":
                        stashed_hello = incoming
                    else:
                        await websocket.close(code=4401, reason="unexpected frame during challenge")
                        return
        except TimeoutError:
            await websocket.close(code=4408, reason="challenge response timeout")
            return
        except WebSocketDisconnect:
            return
        except Exception:  # noqa: BLE001
            await websocket.close(code=4401, reason="proof of possession failed")
            return

    if stashed_hello is not None:
        raw_hello = stashed_hello
    else:
        try:
            raw_hello = await websocket.receive_text()
        except WebSocketDisconnect:
            return

    if len(raw_hello.encode("utf-8")) > MAX_FRAME_BYTES:
        await websocket.close(code=1009, reason="frame too large")
        return

    try:
        hello_data = json.loads(raw_hello)
        hello = HelloFrame.model_validate(hello_data)
    except (json.JSONDecodeError, ValueError, KeyError):
        await websocket.close(code=4401, reason="invalid handshake frame")
        return

    if hello.runner_id != runner_id:
        await websocket.close(code=4401, reason="runner_id mismatch")
        return

    hub = get_global_hub()
    try:
        hub.register_runner(
            runner_id=runner_id,
            workspace_id=workspace_id,
            pool_slug=pool_slug,
            hostname=hostname,
            websocket=websocket,
            max_concurrency=hello.max_concurrency,
            capabilities=capabilities,
        )
    except RunnerAlreadyConnectedError:
        await websocket.close(code=4409, reason="ALREADY_CONNECTED")
        return

    ack = HelloAckFrame()
    await websocket.send_text(ack.model_dump_json())

    with contextlib.suppress(Exception):
        async with session_factory.session(anon_ctx) as session:
            await session.execute(
                text("SELECT touch_runner_heartbeat(:runner_id, 'online')"),
                {"runner_id": runner_id},
            )

    try:
        while True:
            raw_msg = await websocket.receive_text()
            if len(raw_msg.encode("utf-8")) > MAX_FRAME_BYTES:
                await websocket.close(code=1009, reason="frame too large")
                break
            try:
                frame_data = json.loads(raw_msg)
            except json.JSONDecodeError:
                continue

            hub.handle_frame(runner_id, frame_data)

            if frame_data.get("type") == "heartbeat":
                with contextlib.suppress(Exception):
                    async with session_factory.session(anon_ctx) as session:
                        await session.execute(
                            text("SELECT touch_runner_heartbeat(:runner_id)"),
                            {"runner_id": runner_id},
                        )
    except WebSocketDisconnect:
        pass
    finally:
        hub.unregister_runner(runner_id)
        with contextlib.suppress(Exception):
            async with session_factory.session(anon_ctx) as session:
                await session.execute(
                    text("SELECT touch_runner_heartbeat(:runner_id, 'offline')"),
                    {"runner_id": runner_id},
                )


router.include_router(admin_router)
