# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Envelope encryption, DEK sealing, and AAL2 two-stage crypto-shredding (KB-SEC-SHRED-01)."""

from __future__ import annotations

import hashlib
import json
import secrets
import threading
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any, Final, Literal, cast

from sqlalchemy import func, select, update

from database.models.activity_key import ActivityRecordKey
from kanban.api.problems import ProblemException
from kanban.security.envelope import (
    BLOB_VERSION,
    NONCE_LENGTH_BYTES,
    KekProvider,
    SealedSecret,
    StaticKekProvider,
    open_bound,
    seal_bound,
)

if TYPE_CHECKING:
    import uuid
    from collections.abc import Sequence

    from sqlalchemy.ext.asyncio import AsyncSession

    from database.models.activity import ActivityRecord
    from kanban.api.deps import PrincipalContext

__all__ = [
    "DEFAULT_KEK_KID",
    "ShredConfirmationToken",
    "ShredExecuteOut",
    "ShredRequestOut",
    "crypto_shred_keys_for_objects",
    "execute_crypto_shred",
    "request_crypto_shred",
    "resolve_kek_provider",
    "seal_activity_payload",
    "shred_token_store",
    "unwrap_activity_payload",
]

DEFAULT_KEK_KID: Final[str] = "kek-v1"
_DEFAULT_KEK_BYTES: Final[bytes] = b"k" * 32
_DEFAULT_KEK_FALLBACK: Final[StaticKekProvider] = StaticKekProvider(
    keys={DEFAULT_KEK_KID: _DEFAULT_KEK_BYTES},
    current=DEFAULT_KEK_KID,
)

_TOKEN_TTL_SECONDS: Final[int] = 300


def resolve_kek_provider(
    app_state: object | None = None,
    kek_provider: KekProvider | None = None,
) -> KekProvider:
    """Resolve active KekProvider from parameter, app state, or fallback."""
    if kek_provider is not None:
        return kek_provider
    if app_state is not None:
        provider = getattr(app_state, "kek_provider", None)
        if provider is not None:
            return cast("KekProvider", provider)
    return _DEFAULT_KEK_FALLBACK


def seal_activity_payload(
    payload_bytes: bytes,
    workspace_id: uuid.UUID,
    activity_id: uuid.UUID,
    event_type: str,
    kek_provider: KekProvider | None = None,
) -> tuple[int, bytes, bytes, bytes, bytes, bytes, str]:
    """Seal an activity payload using AES-256-GCM envelope encryption with bound AAD.

    Returns:
        (encryption_ver, payload_ciphertext, payload_nonce, payload_aad_sha256,
         wrapped_dek, dek_nonce, dek_kid)

    """
    kek = resolve_kek_provider(kek_provider=kek_provider)
    aad = f"{workspace_id}|{activity_id}|{event_type}".encode()
    aad_sha256 = hashlib.sha256(aad).digest()

    sealed = seal_bound(payload_bytes, aad, kek)
    blob = sealed.encrypted_secret_blob
    payload_nonce = blob[1 : 1 + NONCE_LENGTH_BYTES]
    payload_ciphertext = blob[1 + NONCE_LENGTH_BYTES :]

    wrapped_dek = sealed.wrapped_dek
    dek_nonce = wrapped_dek[1 : 1 + NONCE_LENGTH_BYTES]
    dek_kid = sealed.dek_kid

    return (
        1,
        payload_ciphertext,
        payload_nonce,
        aad_sha256,
        wrapped_dek,
        dek_nonce,
        dek_kid,
    )


def unwrap_activity_payload(
    record: ActivityRecord,
    key: ActivityRecordKey | None,
    kek_provider: KekProvider | None = None,
) -> dict[str, Any]:
    """Unwrap an encrypted activity payload or return a CRYPTO_SHREDDED tombstone.

    Returns a tombstone dict if key is missing or shredded, without raising.
    """
    if key is None or key.wrapped_dek is None or key.shredded_at is not None:
        shredded_at_str = key.shredded_at.isoformat() if (key and key.shredded_at) else None
        return {
            "redacted": True,
            "reason": "CRYPTO_SHREDDED",
            "shredded_at": shredded_at_str,
        }

    if record.payload_ciphertext is None or record.payload_nonce is None:
        return dict(record.payload)

    kek = resolve_kek_provider(kek_provider=kek_provider)
    aad = f"{record.workspace_id}|{record.id}|{record.event_type}".encode()
    encrypted_blob = bytes([BLOB_VERSION]) + record.payload_nonce + record.payload_ciphertext
    sealed = SealedSecret(
        encrypted_secret_blob=encrypted_blob,
        wrapped_dek=key.wrapped_dek,
        dek_kid=key.dek_kid,
    )

    try:
        decrypted_bytes = open_bound(sealed, aad, kek)
        return cast("dict[str, Any]", json.loads(decrypted_bytes.decode("utf-8")))
    except Exception:  # noqa: BLE001
        return {
            "redacted": True,
            "reason": "CRYPTO_SHREDDED",
            "shredded_at": None,
        }


@dataclass(frozen=True)
class ShredConfirmationToken:
    """Single-use confirmation token for two-stage crypto-shredding."""

    token: str
    workspace_id: uuid.UUID
    principal_id: uuid.UUID
    target_type: Literal["activity_id", "object_id", "subject_principal_id"]
    target_id: uuid.UUID
    records_matched: int
    blast_hash: str
    confirm_phrase: str
    expires_at: datetime


class ShredTokenStore:
    """Thread-safe in-memory store for single-use crypto-shred confirmation tokens."""

    def __init__(self) -> None:
        """Initialize empty token registry."""
        self._tokens: dict[str, ShredConfirmationToken] = {}
        self._lock = threading.Lock()

    def create_token(  # noqa: PLR0913
        self,
        *,
        workspace_id: uuid.UUID,
        principal_id: uuid.UUID,
        target_type: Literal["activity_id", "object_id", "subject_principal_id"],
        target_id: uuid.UUID,
        records_matched: int,
        blast_hash: str,
        confirm_phrase: str,
        ttl_seconds: int = _TOKEN_TTL_SECONDS,
    ) -> ShredConfirmationToken:
        """Generate and store a new confirmation token."""
        raw_token = f"kb_shred_{secrets.token_urlsafe(32)}"
        expires_at = datetime.now(UTC) + timedelta(seconds=ttl_seconds)
        entry = ShredConfirmationToken(
            token=raw_token,
            workspace_id=workspace_id,
            principal_id=principal_id,
            target_type=target_type,
            target_id=target_id,
            records_matched=records_matched,
            blast_hash=blast_hash,
            confirm_phrase=confirm_phrase,
            expires_at=expires_at,
        )
        with self._lock:
            self._tokens[raw_token] = entry
        return entry

    def consume_token(
        self,
        token: str,
        confirm_phrase: str,
        caller: PrincipalContext,
    ) -> ShredConfirmationToken:
        """Validate and immediately consume a confirmation token (fail closed)."""
        with self._lock:
            entry = self._tokens.pop(token, None)

        if entry is None:
            raise ProblemException(
                code="INVALID_CONFIRMATION_TOKEN",
                status=409,
                title="Invalid Confirmation Token",
                detail="Confirmation token is invalid, expired, or already consumed.",
            )

        if datetime.now(UTC) > entry.expires_at:
            raise ProblemException(
                code="TOKEN_EXPIRED",
                status=409,
                title="Token Expired",
                detail="Confirmation token has expired; request a new shred token.",
            )

        if entry.workspace_id != caller.workspace_id or entry.principal_id != caller.principal_id:
            raise ProblemException(
                code="TOKEN_CALLER_MISMATCH",
                status=403,
                title="Token Caller Mismatch",
                detail="Confirmation token does not belong to the invoking principal context.",
            )

        if entry.confirm_phrase != confirm_phrase.strip():
            raise ProblemException(
                code="CONFIRM_PHRASE_MISMATCH",
                status=409,
                title="Confirmation Phrase Mismatch",
                detail=f"Expected confirm_phrase '{entry.confirm_phrase}', got '{confirm_phrase}'",
            )

        return entry


shred_token_store = ShredTokenStore()


@dataclass(frozen=True)
class ShredRequestOut:
    """Stage 1 response for crypto-shredding request."""

    stage: str
    target_type: str
    target_id: str
    records_matched: int
    records_to_shred: int
    blast_hash: str
    confirmation_token: str
    confirm_phrase: str
    expires_in_sec: int


@dataclass(frozen=True)
class ShredExecuteOut:
    """Stage 2 response for crypto-shredding execution."""

    status: str
    target_type: str
    target_id: str
    records_shredded: int
    shredded_at: datetime
    shred_audit_id: str


async def request_crypto_shred(  # noqa: PLR0913
    session: AsyncSession,
    caller: PrincipalContext,
    *,
    activity_id: uuid.UUID | None = None,
    object_id: uuid.UUID | None = None,
    subject_principal_id: uuid.UUID | None = None,
    reason: str,
) -> ShredRequestOut:
    """Initiate Stage 1 of AAL2 two-stage crypto-shredding."""
    targets = [
        ("activity_id", activity_id),
        ("object_id", object_id),
        ("subject_principal_id", subject_principal_id),
    ]
    provided = [(name, val) for name, val in targets if val is not None]
    if len(provided) != 1:
        msg = "Exactly one of activity_id, object_id, or subject_principal_id must be provided."
        raise ProblemException(
            code="INVALID_TARGET",
            status=422,
            title="Invalid Shred Target",
            detail=msg,
        )

    target_name, target_id = provided[0]
    target_literal: Literal["activity_id", "object_id", "subject_principal_id"] = cast(
        "Literal['activity_id', 'object_id', 'subject_principal_id']", target_name
    )

    stmt = select(
        func.count(ActivityRecordKey.activity_id).label("total_matched"),
        func.count(ActivityRecordKey.activity_id)
        .filter(ActivityRecordKey.shredded_at.is_(None))
        .label("active_keys"),
    ).where(ActivityRecordKey.workspace_id == caller.workspace_id)

    if target_name == "activity_id":
        stmt = stmt.where(ActivityRecordKey.activity_id == target_id)
    elif target_name == "object_id":
        stmt = stmt.where(ActivityRecordKey.object_id == target_id)
    elif target_name == "subject_principal_id":
        stmt = stmt.where(ActivityRecordKey.actor_id == target_id)

    row = (await session.execute(stmt)).one()
    records_matched = row.total_matched or 0
    records_to_shred = row.active_keys or 0

    confirm_phrase = f"SHRED {target_name.upper()} {target_id}"
    raw_hash_material = (
        f"{caller.workspace_id}:{target_name}:{target_id}:{records_matched}:{reason}"
    )
    blast_hash = hashlib.sha256(raw_hash_material.encode("utf-8")).hexdigest()

    token_entry = shred_token_store.create_token(
        workspace_id=caller.workspace_id,
        principal_id=caller.principal_id,
        target_type=target_literal,
        target_id=target_id,
        records_matched=records_matched,
        blast_hash=blast_hash,
        confirm_phrase=confirm_phrase,
    )

    return ShredRequestOut(
        stage="confirmation_required",
        target_type=target_name,
        target_id=str(target_id),
        records_matched=records_matched,
        records_to_shred=records_to_shred,
        blast_hash=blast_hash,
        confirmation_token=token_entry.token,
        confirm_phrase=confirm_phrase,
        expires_in_sec=_TOKEN_TTL_SECONDS,
    )


async def execute_crypto_shred(
    session: AsyncSession,
    caller: PrincipalContext,
    *,
    confirmation_token: str,
    confirm_phrase: str,
    reason: str,
) -> ShredExecuteOut:
    """Execute Stage 2 of AAL2 two-stage crypto-shredding."""
    token_entry = shred_token_store.consume_token(
        token=confirmation_token,
        confirm_phrase=confirm_phrase,
        caller=caller,
    )

    now = datetime.now(UTC)
    stmt = (
        update(ActivityRecordKey)
        .where(
            ActivityRecordKey.workspace_id == caller.workspace_id,
            ActivityRecordKey.shredded_at.is_(None),
        )
        .values(
            wrapped_dek=None,
            dek_nonce=None,
            shredded_at=now,
            shredded_by_id=caller.principal_id,
            shred_reason=reason,
        )
    )

    if token_entry.target_type == "activity_id":
        stmt = stmt.where(ActivityRecordKey.activity_id == token_entry.target_id)
    elif token_entry.target_type == "object_id":
        stmt = stmt.where(ActivityRecordKey.object_id == token_entry.target_id)
    elif token_entry.target_type == "subject_principal_id":
        stmt = stmt.where(ActivityRecordKey.actor_id == token_entry.target_id)

    res = await session.execute(stmt)
    records_shredded = res.rowcount

    # Append immutable CRYPTO_SHRED_EXECUTED audit event
    from kanban.services.activity import (  # noqa: PLC0415
        ActivityEventType,
        record_activity,
    )

    audit_id = await record_activity(
        session=session,
        workspace_id=caller.workspace_id,
        object_id=token_entry.target_id if token_entry.target_type == "object_id" else None,
        actor_principal_id=caller.principal_id,
        event_type=ActivityEventType.CRYPTO_SHRED_EXECUTED,
        payload={
            "target_type": token_entry.target_type,
            "target_id": str(token_entry.target_id),
            "records_shredded": records_shredded,
            "reason": reason,
            "blast_hash": token_entry.blast_hash,
        },
        encrypt_payload=False,
    )

    return ShredExecuteOut(
        status="shredded",
        target_type=token_entry.target_type,
        target_id=str(token_entry.target_id),
        records_shredded=records_shredded,
        shredded_at=now,
        shred_audit_id=str(audit_id),
    )


async def crypto_shred_keys_for_objects(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    object_ids: Sequence[uuid.UUID],
    actor_id: uuid.UUID | None,
    reason: str,
) -> int:
    """Crypto-shred all activity keys associated with a set of purged object IDs."""
    if not object_ids:
        return 0

    now = datetime.now(UTC)
    stmt = (
        update(ActivityRecordKey)
        .where(
            ActivityRecordKey.workspace_id == workspace_id,
            ActivityRecordKey.object_id.in_(list(object_ids)),
            ActivityRecordKey.shredded_at.is_(None),
        )
        .values(
            wrapped_dek=None,
            dek_nonce=None,
            shredded_at=now,
            shredded_by_id=actor_id,
            shred_reason=reason,
        )
    )
    res = await session.execute(stmt)
    return res.rowcount
