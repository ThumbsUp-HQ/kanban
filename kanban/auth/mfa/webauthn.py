# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""WebAuthn and Passkeys registration and assertion service (KB-P2-05b)."""

from __future__ import annotations

import json
import logging
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Final

from sqlalchemy import text
from webauthn import (
    base64url_to_bytes,
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers.cose import COSEAlgorithmIdentifier
from webauthn.helpers.structs import (
    AttestationConveyancePreference,
    AuthenticatorAttachment,
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from kanban.api.problems import ProblemException
from kanban.services.activity import ActivityEventType, record_activity

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

MAX_NICKNAME_LENGTH: Final[int] = 64


class WebauthnCloneDetectedError(Exception):
    """Internal exception raised when an authenticator signature counter regression is detected."""


@dataclass(frozen=True, slots=True)
class WebauthnCredentialRecord:
    """Internal representation of a persisted WebAuthn credential."""

    id: uuid.UUID
    principal_id: uuid.UUID
    credential_id: bytes
    public_key: bytes
    sign_count: int
    aaguid: uuid.UUID | None
    transports: list[str]
    nickname: str | None
    suspect_clone_at: datetime | None
    created_at: datetime
    last_used_at: datetime | None


def _extract_client_data(resp_dict: object, expected_type: str) -> bytes:
    """Validate client data JSON and extract challenge bytes."""
    if not isinstance(resp_dict, dict):
        logger.info("WebAuthn missing response dictionary")
        raise ProblemException(
            code="MFA_INVALID",
            status=401,
            title="MFA Invalid",
            detail="WebAuthn verification failed.",
        )

    client_data_raw_b64 = resp_dict.get("clientDataJSON")
    if not isinstance(client_data_raw_b64, str) or not client_data_raw_b64:
        logger.info("WebAuthn missing clientDataJSON")
        raise ProblemException(
            code="MFA_INVALID",
            status=401,
            title="MFA Invalid",
            detail="WebAuthn verification failed.",
        )

    try:
        client_data_bytes = base64url_to_bytes(client_data_raw_b64)
        client_data = json.loads(client_data_bytes)
    except Exception as exc:  # noqa: BLE001
        logger.info("WebAuthn clientDataJSON parsing failed: %s", type(exc).__name__)
        raise ProblemException(
            code="MFA_INVALID",
            status=401,
            title="MFA Invalid",
            detail="WebAuthn verification failed.",
        ) from None

    if not isinstance(client_data, dict):
        logger.info("WebAuthn clientDataJSON not a dict")
        raise ProblemException(
            code="MFA_INVALID",
            status=401,
            title="MFA Invalid",
            detail="WebAuthn verification failed.",
        )

    challenge_b64 = client_data.get("challenge")
    if not isinstance(challenge_b64, str) or not challenge_b64:
        logger.info("Missing challenge in clientDataJSON")
        raise ProblemException(
            code="MFA_INVALID",
            status=401,
            title="MFA Invalid",
            detail="WebAuthn verification failed.",
        )

    try:
        challenge_bytes = base64url_to_bytes(challenge_b64)
    except Exception as exc:  # noqa: BLE001
        logger.info("WebAuthn challenge decoding failed: %s", type(exc).__name__)
        raise ProblemException(
            code="MFA_INVALID",
            status=401,
            title="MFA Invalid",
            detail="WebAuthn verification failed.",
        ) from None

    client_type = client_data.get("type")

    if client_type != expected_type:
        logger.info("WebAuthn type confusion: %s", client_type)
        raise ProblemException(
            code="MFA_INVALID",
            status=401,
            title="MFA Invalid",
            detail="WebAuthn verification failed.",
        )

    return challenge_bytes


def _parse_aaguid(raw_aaguid: object) -> uuid.UUID | None:
    """Safely parse AAGUID to UUID."""
    if not raw_aaguid:
        return None
    try:
        return uuid.UUID(str(raw_aaguid))
    except ValueError:
        return None


def _resolve_credential_id(credential_payload: dict[str, Any]) -> bytes:
    """Extract and base64url-decode credential identifier."""
    raw_cred_id_b64 = credential_payload.get("rawId") or credential_payload.get("id")
    if not raw_cred_id_b64:
        logger.info("WebAuthn payload missing credential id")
        raise ProblemException(
            code="MFA_INVALID",
            status=401,
            title="MFA Invalid",
            detail="WebAuthn verification failed.",
        )
    try:
        return base64url_to_bytes(raw_cred_id_b64)
    except Exception:  # noqa: BLE001
        logger.info("WebAuthn credential id base64url decode failed")
        raise ProblemException(
            code="MFA_INVALID",
            status=401,
            title="MFA Invalid",
            detail="WebAuthn verification failed.",
        ) from None


class WebauthnService:
    """Core WebAuthn registration and assertion service enforcing AAL2 invariants."""

    def __init__(
        self,
        *,
        rp_id: str,
        rp_name: str = "👍kanban",
        expected_origin: str,
    ) -> None:
        """Initialize WebAuthn service with RP identifier, name, and origin."""
        self.rp_id = rp_id.strip().lower()
        self.rp_name = rp_name
        self.expected_origin = expected_origin.rstrip("/")

    async def registration_options(  # noqa: PLR0913
        self,
        session: AsyncSession,
        *,
        session_id: uuid.UUID,
        principal_id: uuid.UUID,
        username: str,
        display_name: str | None = None,
        authenticator_attachment: AuthenticatorAttachment | str | None = None,
    ) -> dict[str, Any]:
        """Generate PublicKeyCredentialCreationOptions and store a single-use challenge."""
        creds_res = await session.execute(
            text("SELECT credential_id FROM kb_auth.webauthn_credentials_for_principal(:p_id)"),
            {"p_id": principal_id},
        )
        existing_creds = [
            PublicKeyCredentialDescriptor(id=row[0])
            for row in creds_res.all()
            if row[0] is not None
        ]

        challenge_bytes = secrets.token_bytes(32)

        await session.execute(
            text(
                "SELECT kb_auth.webauthn_challenge_create("
                "  :session_id, 'register', :challenge, 300"
                ")"
            ),
            {
                "session_id": session_id,
                "challenge": challenge_bytes,
            },
        )

        auth_attachment: AuthenticatorAttachment | None = None
        if authenticator_attachment is not None:
            if isinstance(authenticator_attachment, AuthenticatorAttachment):
                auth_attachment = authenticator_attachment
            else:
                auth_attachment = AuthenticatorAttachment(str(authenticator_attachment))

        options = generate_registration_options(
            rp_id=self.rp_id,
            rp_name=self.rp_name,
            user_id=principal_id.bytes,
            user_name=username,
            user_display_name=display_name or username,
            challenge=challenge_bytes,
            timeout=300000,
            attestation=AttestationConveyancePreference.NONE,
            authenticator_selection=AuthenticatorSelectionCriteria(
                authenticator_attachment=auth_attachment,
                user_verification=UserVerificationRequirement.PREFERRED,
                resident_key=ResidentKeyRequirement.PREFERRED,
            ),
            exclude_credentials=existing_creds or None,
            supported_pub_key_algs=[
                COSEAlgorithmIdentifier.ECDSA_SHA_256,
                COSEAlgorithmIdentifier.EDDSA,
                COSEAlgorithmIdentifier.RSASSA_PKCS1_v1_5_SHA_256,
            ],
        )

        return json.loads(options_to_json(options))  # type: ignore[no-any-return]

    async def verify_registration(  # noqa: PLR0913
        self,
        session: AsyncSession,
        *,
        session_id: uuid.UUID,
        principal_id: uuid.UUID,
        credential_payload: dict[str, Any],
        nickname: str | None = None,
        workspace_id: uuid.UUID | None = None,
    ) -> WebauthnCredentialRecord:
        """Verify WebAuthn registration response and persist the new credential."""
        if nickname is not None and len(nickname) > MAX_NICKNAME_LENGTH:
            raise ProblemException(
                code="VALIDATION_ERROR",
                status=422,
                title="Validation Error",
                detail="Credential nickname must not exceed 64 characters.",
            )

        resp_dict = credential_payload.get("response")
        challenge_bytes = _extract_client_data(resp_dict, "webauthn.create")

        # Atomically consume single-use challenge
        consume_res = await session.execute(
            text(
                "SELECT kb_auth.webauthn_challenge_consume(  :session_id, 'register', :challenge)"
            ),
            {
                "session_id": session_id,
                "challenge": challenge_bytes,
            },
        )
        if not consume_res.scalar_one():
            logger.info("WebAuthn registration challenge not found, expired, or already consumed")
            raise ProblemException(
                code="MFA_INVALID",
                status=401,
                title="MFA Invalid",
                detail="WebAuthn verification failed.",
            )

        try:
            verified = verify_registration_response(
                credential=credential_payload,
                expected_challenge=challenge_bytes,
                expected_rp_id=self.rp_id,
                expected_origin=self.expected_origin,
                require_user_verification=False,
                supported_pub_key_algs=[
                    COSEAlgorithmIdentifier.ECDSA_SHA_256,
                    COSEAlgorithmIdentifier.EDDSA,
                    COSEAlgorithmIdentifier.RSASSA_PKCS1_v1_5_SHA_256,
                ],
            )
        except Exception as exc:  # noqa: BLE001
            logger.info(
                "WebAuthn verify_registration_response failed: %s",
                type(exc).__name__,
            )
            raise ProblemException(
                code="MFA_INVALID",
                status=401,
                title="MFA Invalid",
                detail="WebAuthn verification failed.",
            ) from None

        aaguid_val = _parse_aaguid(verified.aaguid)

        transports: list[str] = []
        raw_transports = resp_dict.get("transports") if isinstance(resp_dict, dict) else None
        if isinstance(raw_transports, list):
            transports = [str(t) for t in raw_transports]

        try:
            insert_res = await session.execute(
                text(
                    "SELECT kb_auth.webauthn_credential_create("
                    "  :p_id, :cred_id, :pub_key, :sign_count, :aaguid, :transports, :nickname"
                    ")"
                ),
                {
                    "p_id": principal_id,
                    "cred_id": verified.credential_id,
                    "pub_key": verified.credential_public_key,
                    "sign_count": verified.sign_count,
                    "aaguid": aaguid_val,
                    "transports": transports,
                    "nickname": nickname,
                },
            )
            cred_uuid = insert_res.scalar_one()
        except Exception as exc:
            err_msg = str(exc)
            if "CREDENTIAL_LIMIT" in err_msg or "P0003" in err_msg:
                raise ProblemException(
                    code="CREDENTIAL_LIMIT",
                    status=409,
                    title="Credential Limit Reached",
                    detail="Maximum of 10 WebAuthn credentials allowed per account.",
                ) from None
            raise

        if workspace_id is not None:
            try:
                await record_activity(
                    session,
                    workspace_id=workspace_id,
                    actor_principal_id=principal_id,
                    event_type=ActivityEventType.WEBAUTHN_REGISTERED,
                    payload={"credential_id": str(cred_uuid)},
                )
            except Exception:
                logger.debug("Failed to record WEBAUTHN_REGISTERED activity", exc_info=True)

        return WebauthnCredentialRecord(
            id=cred_uuid,
            principal_id=principal_id,
            credential_id=verified.credential_id,
            public_key=verified.credential_public_key,
            sign_count=verified.sign_count,
            aaguid=aaguid_val,
            transports=transports,
            nickname=nickname,
            suspect_clone_at=None,
            created_at=datetime.now(tz=UTC),
            last_used_at=None,
        )

    async def authentication_options(
        self,
        session: AsyncSession,
        *,
        session_id: uuid.UUID,
        principal_id: uuid.UUID,
    ) -> dict[str, Any]:
        """Generate PublicKeyCredentialRequestOptions and store a single-use challenge."""
        creds_res = await session.execute(
            text("SELECT credential_id FROM kb_auth.webauthn_credentials_for_principal(:p_id)"),
            {"p_id": principal_id},
        )
        allowed_creds = [
            PublicKeyCredentialDescriptor(id=row[0])
            for row in creds_res.all()
            if row[0] is not None
        ]

        challenge_bytes = secrets.token_bytes(32)

        await session.execute(
            text(
                "SELECT kb_auth.webauthn_challenge_create("
                "  :session_id, 'authenticate', :challenge, 300"
                ")"
            ),
            {
                "session_id": session_id,
                "challenge": challenge_bytes,
            },
        )

        options = generate_authentication_options(
            rp_id=self.rp_id,
            challenge=challenge_bytes,
            timeout=300000,
            allow_credentials=allowed_creds or None,
            user_verification=UserVerificationRequirement.PREFERRED,
        )

        return json.loads(options_to_json(options))  # type: ignore[no-any-return]

    async def verify_authentication(
        self,
        session: AsyncSession,
        *,
        session_id: uuid.UUID,
        principal_id: uuid.UUID,
        credential_payload: dict[str, Any],
        workspace_id: uuid.UUID | None = None,
    ) -> tuple[WebauthnCredentialRecord, int]:
        """Verify WebAuthn assertion response, validate sign count, and return credential."""
        resp_dict = credential_payload.get("response")
        challenge_bytes = _extract_client_data(resp_dict, "webauthn.get")

        # Atomically consume single-use challenge
        consume_res = await session.execute(
            text(
                "SELECT kb_auth.webauthn_challenge_consume("
                "  :session_id, 'authenticate', :challenge"
                ")"
            ),
            {
                "session_id": session_id,
                "challenge": challenge_bytes,
            },
        )
        if not consume_res.scalar_one():
            logger.info("WebAuthn authentication challenge not found, expired, or already consumed")
            raise ProblemException(
                code="MFA_INVALID",
                status=401,
                title="MFA Invalid",
                detail="WebAuthn verification failed.",
            )

        cred_id_bytes = _resolve_credential_id(credential_payload)

        cred_res = await session.execute(
            text("SELECT * FROM kb_auth.webauthn_credential_get(:cred_id)"),
            {"cred_id": cred_id_bytes},
        )
        cred_row = cred_res.mappings().first()
        if cred_row is None or cred_row["principal_id"] != principal_id:
            logger.info("WebAuthn credential not found or principal mismatch")
            raise ProblemException(
                code="MFA_INVALID",
                status=401,
                title="MFA Invalid",
                detail="WebAuthn verification failed.",
            )

        if cred_row["suspect_clone_at"] is not None:
            logger.info("WebAuthn credential is flagged as suspect clone")
            raise ProblemException(
                code="MFA_INVALID",
                status=401,
                title="MFA Invalid",
                detail="WebAuthn verification failed.",
            )

        stored_sign_count = int(cred_row["sign_count"])

        try:
            verified = verify_authentication_response(
                credential=credential_payload,
                expected_challenge=challenge_bytes,
                expected_rp_id=self.rp_id,
                expected_origin=self.expected_origin,
                credential_public_key=cred_row["public_key"],
                credential_current_sign_count=0,
                require_user_verification=False,
            )
        except Exception as exc:  # noqa: BLE001
            logger.info(
                "WebAuthn verify_authentication_response failed: %s",
                type(exc).__name__,
            )
            raise ProblemException(
                code="MFA_INVALID",
                status=401,
                title="MFA Invalid",
                detail="WebAuthn verification failed.",
            ) from None

        new_sign_count = verified.new_sign_count

        # Clone detection: if (new_sign_count != 0 or stored != 0) and new_sign_count <= stored
        if (new_sign_count != 0 or stored_sign_count != 0) and new_sign_count <= stored_sign_count:
            logger.info(
                "WebAuthn signature counter regression detected: new=%d <= stored=%d",
                new_sign_count,
                stored_sign_count,
            )
            await session.execute(
                text("SELECT kb_auth.webauthn_mark_clone(:cred_id)"),
                {"cred_id": cred_id_bytes},
            )
            if workspace_id is not None:
                try:
                    await record_activity(
                        session,
                        workspace_id=workspace_id,
                        actor_principal_id=principal_id,
                        event_type=ActivityEventType.WEBAUTHN_SIGN_COUNT_REGRESSION,
                        payload={
                            "credential_id": str(cred_row["id"]),
                            "new_sign_count": new_sign_count,
                            "stored_sign_count": stored_sign_count,
                        },
                    )
                except Exception:
                    logger.debug(
                        "Failed to record WEBAUTHN_SIGN_COUNT_REGRESSION activity",
                        exc_info=True,
                    )
            raise WebauthnCloneDetectedError

        # Update monotonic sign counter
        await session.execute(
            text("SELECT kb_auth.webauthn_update_sign_count(:cred_id, :new_sign_count)"),
            {
                "cred_id": cred_id_bytes,
                "new_sign_count": new_sign_count,
            },
        )

        if workspace_id is not None:
            try:
                await record_activity(
                    session,
                    workspace_id=workspace_id,
                    actor_principal_id=principal_id,
                    event_type=ActivityEventType.WEBAUTHN_VERIFIED,
                    payload={"credential_id": str(cred_row["id"])},
                )
            except Exception:
                logger.debug("Failed to record WEBAUTHN_VERIFIED activity", exc_info=True)

        record = WebauthnCredentialRecord(
            id=cred_row["id"],
            principal_id=cred_row["principal_id"],
            credential_id=cred_row["credential_id"],
            public_key=cred_row["public_key"],
            sign_count=new_sign_count,
            aaguid=cred_row["aaguid"],
            transports=list(cred_row["transports"] or []),
            nickname=cred_row["nickname"],
            suspect_clone_at=cred_row["suspect_clone_at"],
            created_at=cred_row["created_at"],
            last_used_at=datetime.now(tz=UTC),
        )
        return record, new_sign_count

    async def list_credentials(
        self,
        session: AsyncSession,
        principal_id: uuid.UUID,
    ) -> list[WebauthnCredentialRecord]:
        """List all active WebAuthn credentials for the principal."""
        res = await session.execute(
            text("SELECT * FROM kb_auth.webauthn_credentials_for_principal(:p_id)"),
            {"p_id": principal_id},
        )
        return [
            WebauthnCredentialRecord(
                id=row["id"],
                principal_id=row["principal_id"],
                credential_id=row["credential_id"],
                public_key=row["public_key"],
                sign_count=row["sign_count"],
                aaguid=row["aaguid"],
                transports=list(row["transports"] or []),
                nickname=row["nickname"],
                suspect_clone_at=row["suspect_clone_at"],
                created_at=row["created_at"],
                last_used_at=row["last_used_at"],
            )
            for row in res.mappings().all()
        ]

    async def delete_credential(
        self,
        session: AsyncSession,
        *,
        principal_id: uuid.UUID,
        credential_id: uuid.UUID,
        is_admin: bool = False,
        workspace_id: uuid.UUID | None = None,
    ) -> None:
        """Delete a registered WebAuthn credential, checking admin last-factor invariants."""
        if is_admin:
            status_res = await session.execute(
                text("SELECT * FROM kb_auth.mfa_status(:p_id)"),
                {"p_id": principal_id},
            )
            status_row = status_res.mappings().first()
            has_active_totp = bool(status_row["has_active_totp"]) if status_row else False
            webauthn_count = int(status_row["webauthn_credential_count"]) if status_row else 0

            if not has_active_totp and webauthn_count <= 1:
                raise ProblemException(
                    code="LAST_FACTOR",
                    status=409,
                    title="Cannot Delete Last Factor",
                    detail=(
                        "Administrators must retain at least one active AAL2 authentication factor."
                    ),
                )

        del_res = await session.execute(
            text("SELECT kb_auth.webauthn_credential_delete(:cred_id, :p_id)"),
            {"cred_id": credential_id, "p_id": principal_id},
        )
        if not del_res.scalar_one():
            raise ProblemException(
                code="NOT_FOUND",
                status=404,
                title="Credential Not Found",
                detail="WebAuthn credential was not found or not owned by principal.",
            )

        if workspace_id is not None:
            try:
                await record_activity(
                    session,
                    workspace_id=workspace_id,
                    actor_principal_id=principal_id,
                    event_type=ActivityEventType.WEBAUTHN_DELETED,
                    payload={"credential_id": str(credential_id)},
                )
            except Exception:
                logger.debug("Failed to record WEBAUTHN_DELETED activity", exc_info=True)
