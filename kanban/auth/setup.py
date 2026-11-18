# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""First-boot setup bootstrap service and claim handling (KB-P2-12)."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import logging
import os
import re
import secrets
import sys
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Final

from sqlalchemy import text

from database.session import RLSContext
from kanban.api.problems import ProblemException
from kanban.auth.local.hashing import DUMMY_HASH, hash_password, verify_password
from kanban.security.keys import derive_subkey, load_key_material

if TYPE_CHECKING:
    from io import TextIOBase

    from sqlalchemy.ext.asyncio import AsyncSession

    from database.session import RLSSessionFactory
    from kanban.security.keys import KeyMaterial
    from kanban.settings import Settings

logger = logging.getLogger(__name__)

SETUP_TOKEN_PREFIX: Final[str] = "kb_setup_"  # noqa: S105
SETUP_TOKEN_REGEX: Final[re.Pattern[str]] = re.compile(r"^kb_setup_[A-Za-z0-9_-]{43}$")
SETUP_SUBKEY_PURPOSE: Final[str] = "setup/claim-token"
DEFAULT_SETUP_TTL_SECONDS: Final[int] = 3600


def generate_setup_token() -> str:
    """Generate a single-use 256-bit setup claim token matching ^kb_setup_[A-Za-z0-9_-]{43}$."""
    raw = secrets.token_bytes(32)
    b64 = base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")
    return f"{SETUP_TOKEN_PREFIX}{b64}"


def hash_setup_token(token: str, pepper: bytes) -> bytes:
    """Derive dedicated subkey and compute HMAC-SHA256 at-rest digest."""
    subkey = derive_subkey(pepper, SETUP_SUBKEY_PURPOSE)
    return hmac.new(subkey, token.encode("ascii"), hashlib.sha256).digest()


class SetupBootstrapService:
    """Service managing first-boot token issuance and initial administrator claiming."""

    def __init__(
        self,
        session_factory: RLSSessionFactory,
        *,
        key_material: KeyMaterial | None = None,
        settings: Settings | None = None,
    ) -> None:
        """Initialize setup bootstrap service with dependencies."""
        self._session_factory = session_factory
        self._key_material = key_material
        self._settings = settings

    def _resolve_key_material(self) -> KeyMaterial:
        if self._key_material is not None:
            return self._key_material
        self._key_material = load_key_material()
        return self._key_material

    async def is_initialized(self, session: AsyncSession) -> bool:
        """Check whether the instance has already been claimed by at least one user."""
        res = await session.execute(text("SELECT kb_auth.setup_is_initialized()"))
        return bool(res.scalar_one())

    async def mint_token_if_uninitialized(
        self,
        *,
        ttl_seconds: int = DEFAULT_SETUP_TTL_SECONDS,
        stdout: TextIOBase | None = None,
    ) -> str | None:
        """Mint single-use setup token if 0 users exist and print URL to stdout."""
        km = self._resolve_key_material()
        raw_token = generate_setup_token()
        token_hmac = hash_setup_token(raw_token, km.auth_pepper)

        anon_ctx = RLSContext(principal_id=uuid.UUID(int=0), workspace_id=uuid.UUID(int=0))
        async with self._session_factory.session(anon_ctx) as session:
            res = await session.execute(
                text("SELECT kb_auth.setup_mint_token(:hmac, :ttl)"),
                {"hmac": token_hmac, "ttl": ttl_seconds},
            )
            minted = bool(res.scalar_one())

        if not minted:
            return None

        origin = "http://localhost:8080"
        if self._settings is not None:
            origin = self._settings.effective_origin

        token_file = os.environ.get("KB_SETUP_TOKEN_FILE", "/run/kanban/setup_token")

        def _persist_token(dest: str, secret: str) -> bool:
            try:
                p = Path(dest)
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(secret, encoding="utf-8")
                p.chmod(0o600)
            except OSError:
                return False
            else:
                return True

        written = await asyncio.to_thread(_persist_token, token_file, raw_token)
        file_hint = (
            f" (claim token written to {token_file})"
            if written
            else " (token claim available via setup wizard)"
        )

        out_stream = stdout if stdout is not None else sys.stdout
        out_stream.write(
            f"👍 First-boot setup URL: {origin}/setup?token=[REDACTED:SETUP_TOKEN]{file_hint}\n"
        )
        out_stream.flush()

        return raw_token

    async def claim_initial_admin(  # noqa: PLR0913
        self,
        session: AsyncSession,
        *,
        token: str,
        username: str,
        display_name: str,
        email: str,
        password: str,
        workspace_name: str | None = None,
        workspace_slug: str | None = None,
        project_name: str | None = None,
        project_key: str | None = None,
    ) -> tuple[str, str, str]:
        """Atomically claim instance, provision first SERVER_ADMIN, and return IDs."""
        km = self._resolve_key_material()

        if not SETUP_TOKEN_REGEX.match(token):
            # Equalize timing with dummy Argon2 verify on malformed format
            await verify_password(DUMMY_HASH, "dummy_password_for_timing", pepper=km.auth_pepper)
            raise ProblemException(
                code="SETUP_TOKEN_INVALID",
                status=401,
                title="Setup Token Invalid",
                detail="The setup token is invalid, expired, or has already been used.",
            )

        token_hmac = hash_setup_token(token, km.auth_pepper)
        password_hash = await hash_password(password, pepper=km.auth_pepper)

        res = await session.execute(
            text(
                "SELECT principal_id, workspace_id, local_card_id "
                "FROM kb_auth.setup_consume_and_create_admin("
                "  :token_hmac, :username, :display_name, :email, :password_hash"
                ")"
            ),
            {
                "token_hmac": token_hmac,
                "username": username,
                "display_name": display_name,
                "email": email,
                "password_hash": password_hash,
            },
        )
        row = res.mappings().first()

        if row is None:
            raise ProblemException(
                code="SETUP_TOKEN_INVALID",
                status=401,
                title="Setup Token Invalid",
                detail="The setup token is invalid, expired, or has already been used.",
            )

        principal_id = row["principal_id"]
        workspace_id = row["workspace_id"]
        local_card_id = row["local_card_id"]

        # Update initial workspace name & slug if provided
        ws_name = (workspace_name or "Default Workspace").strip()
        ws_slug = (workspace_slug or "default").strip()
        await session.execute(
            text("UPDATE workspaces SET name = :name, slug = :slug WHERE id = :ws_id"),
            {"name": ws_name, "slug": ws_slug, "ws_id": workspace_id},
        )

        # Provision initial project if provided
        p_name = (project_name or "Default Project").strip()
        p_key = (project_key or "KAN").strip().upper()
        p_check = await session.execute(
            text("SELECT id FROM projects WHERE workspace_id = :ws_id AND identifier = :p_key"),
            {"ws_id": workspace_id, "p_key": p_key},
        )
        if p_check.first() is None:
            proj_res = await session.execute(text("SELECT uuidv7()"))
            proj_id = proj_res.scalar_one()

            await session.execute(
                text(
                    "INSERT INTO objects ("
                    "  id, object_type, workspace_id, project_id, canonical_key, "
                    "  display_title, created_by_id, created_at"
                    ") VALUES ("
                    "  :proj_id, 'project'::object_kind, :ws_id, NULL, :p_key, "
                    "  :p_name, :p_id, clock_timestamp()"
                    ")"
                ),
                {
                    "proj_id": proj_id,
                    "ws_id": workspace_id,
                    "p_key": p_key,
                    "p_name": p_name,
                    "p_id": principal_id,
                },
            )
            await session.execute(
                text(
                    "INSERT INTO projects ("
                    "  id, object_type, workspace_id, identifier, name, description_markdown"
                    ") VALUES ("
                    "  :proj_id, 'project'::object_kind, :ws_id, :p_key, :p_name, ''"
                    ")"
                ),
                {
                    "proj_id": proj_id,
                    "ws_id": workspace_id,
                    "p_key": p_key,
                    "p_name": p_name,
                },
            )

        return (
            str(principal_id),
            str(workspace_id),
            str(local_card_id),
        )


async def mint_setup_token_if_uninitialized(
    session_factory: RLSSessionFactory,
    *,
    key_material: KeyMaterial | None = None,
    settings: Settings | None = None,
    ttl_seconds: int = DEFAULT_SETUP_TTL_SECONDS,
    stdout: TextIOBase | None = None,
) -> str | None:
    """Mint setup token on startup if uninitialized."""
    svc = SetupBootstrapService(session_factory, key_material=key_material, settings=settings)
    return await svc.mint_token_if_uninitialized(ttl_seconds=ttl_seconds, stdout=stdout)
