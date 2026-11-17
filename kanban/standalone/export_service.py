# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Standalone single-container deployment utilities and export service (KB-P3-52).

Provides:
- Reading standalone container status from /run/kanban/standalone_status.json
- Direct subprocess execution of pg_dump (zero-shell, strict args)
- AES-256-GCM envelope encryption (.kbkp) with PBKDF2 or HKDF key derivation
- Generation of secret-free production docker-compose.yml and promotion runbook
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from sqlalchemy.engine.url import make_url

from deploy.standalone.storage_probe import probe

if TYPE_CHECKING:
    from kanban.settings import Settings

logger = logging.getLogger(__name__)

# KBKP Format Constants
KBKP_MAGIC: Final[bytes] = b"KBKP"
KBKP_VERSION: Final[int] = 1
KDF_MODE_PASSPHRASE_PBKDF2: Final[int] = 1
KDF_MODE_MASTER_KEK_HKDF: Final[int] = 2

SALT_BYTES: Final[int] = 16
NONCE_BYTES: Final[int] = 12
PBKDF2_ITERATIONS: Final[int] = 600_000
KEY_BYTES: Final[int] = 32

HEADER_LENGTH: Final[int] = len(KBKP_MAGIC) + 1 + 1 + SALT_BYTES + NONCE_BYTES  # 34 bytes

DEFAULT_STATUS_PATH: Final[Path] = Path("/run/kanban/standalone_status.json")


class BackupError(Exception):
    """Raised when backup extraction, encryption, or validation fails."""


class RestoreError(Exception):
    """Raised when backup decryption or header validation fails."""


@dataclass(frozen=True)
class ComposeExportPayload:
    """Secret-free production Docker Compose specification and promotion runbook."""

    filename: str
    compose_yaml: str
    env_template: str
    migration_steps_markdown: str
    single_container_compose_yaml: str = ""


def get_standalone_status(  # noqa: C901
    status_path: Path | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Read runtime deployment and storage status descriptor.

    Reads from status_path (or KB_STANDALONE_STATUS_PATH / /run/kanban/standalone_status.json).
    Defaults to production_multi_container when file is missing or empty.
    """
    path = status_path
    if path is None:
        env_path = os.environ.get("KB_STANDALONE_STATUS_PATH")
        path = Path(env_path) if env_path else DEFAULT_STATUS_PATH

    air_gap = False
    if settings is not None:
        air_gap = bool(getattr(settings, "air_gap_mode", False))
    elif os.environ.get("KANBAN_AIR_GAP_MODE", "").lower() in ("true", "1", "yes"):
        air_gap = True

    local_llm_host = os.environ.get("KANBAN_LOCAL_LLM_HOST") or os.environ.get("LOCAL_LLM_HOST")

    settings_mode = getattr(settings, "deployment_mode", None) if settings is not None else None
    if not settings_mode:
        settings_mode = os.environ.get("KANBAN_DEPLOYMENT_MODE")

    if path.is_file():
        try:
            content = path.read_text(encoding="utf-8").strip()
            if content:
                data = json.loads(content)
                raw_mode = data.get("mode", settings_mode or "standalone_embedded_pg")
                deployment_mode = (
                    "standalone_embedded_pg"
                    if raw_mode in ("standalone_embedded_pg", "standalone")
                    else "production_multi_container"
                )
                return {
                    "deployment_mode": deployment_mode,
                    "persistent_volume": bool(data.get("persistent_volume", False)),
                    "data_mount_point": data.get("data_mount_point"),
                    "data_mount_fstype": data.get("data_mount_fstype"),
                    "tier_b_sandbox_available": bool(data.get("tier_b_sandbox_available", False)),
                    "air_gap_mode": bool(data.get("air_gap_mode", air_gap)),
                    "local_llm_endpoint_host": data.get("local_llm_endpoint_host", local_llm_host),
                }
        except Exception:
            logger.warning("Failed to parse standalone status from %s", path, exc_info=True)

    # Respect settings.deployment_mode when file is absent or corrupt
    if settings_mode in ("standalone", "standalone_embedded_pg"):
        persistent = False
        data_mount_point: str | None = "/var/lib/kanban/data"
        data_mount_fstype: str | None = "ext4"
        tier_b_available = False
        try:
            live_probe = probe(Path("/var/lib/kanban/data"), mode="standalone_embedded_pg")
            persistent = live_probe.persistent_volume
            if live_probe.data_mount_point:
                data_mount_point = live_probe.data_mount_point
            if live_probe.data_mount_fstype:
                data_mount_fstype = live_probe.data_mount_fstype
            tier_b_available = live_probe.tier_b_sandbox_available
        except Exception:
            logger.debug("Live storage probe fallback failed", exc_info=True)

        return {
            "deployment_mode": "standalone_embedded_pg",
            "persistent_volume": persistent,
            "data_mount_point": data_mount_point,
            "data_mount_fstype": data_mount_fstype,
            "tier_b_sandbox_available": tier_b_available,
            "air_gap_mode": air_gap,
            "local_llm_endpoint_host": local_llm_host,
        }

    # Default to production multi-container when file is absent or corrupt
    return {
        "deployment_mode": "production_multi_container",
        "persistent_volume": True,
        "data_mount_point": None,
        "data_mount_fstype": None,
        "tier_b_sandbox_available": True,
        "air_gap_mode": air_gap,
        "local_llm_endpoint_host": local_llm_host,
    }


def encrypt_backup(
    data: bytes,
    *,
    passphrase: str | None = None,
    master_kek: bytes | None = None,
) -> bytes:
    """Encrypt raw database dump bytes into a self-describing .kbkp envelope.

    Uses AES-256-GCM. Derives key via PBKDF2-HMAC-SHA256 (600,000 iterations) from
    passphrase, or HKDF-SHA256 from master_kek.
    """
    if passphrase is None and master_kek is None:
        msg = "Either passphrase or master_kek must be provided"
        raise BackupError(msg)

    salt = os.urandom(SALT_BYTES)
    nonce = os.urandom(NONCE_BYTES)

    if passphrase is not None:
        kdf_mode = KDF_MODE_PASSPHRASE_PBKDF2
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=KEY_BYTES,
            salt=salt,
            iterations=PBKDF2_ITERATIONS,
        )
        derived_key = kdf.derive(passphrase.encode("utf-8"))
    elif master_kek is not None:
        kdf_mode = KDF_MODE_MASTER_KEK_HKDF
        hkdf = HKDF(
            algorithm=hashes.SHA256(),
            length=KEY_BYTES,
            salt=salt,
            info=b"kanban-standalone-backup-v1",
        )
        derived_key = hkdf.derive(master_kek)

    header = KBKP_MAGIC + bytes([KBKP_VERSION, kdf_mode]) + salt + nonce

    aesgcm = AESGCM(derived_key)
    # Header acts as Additional Authenticated Data (AAD)
    ciphertext = aesgcm.encrypt(nonce, data, header)

    return header + ciphertext


def decrypt_backup(
    payload: bytes,
    *,
    passphrase: str | None = None,
    master_kek: bytes | None = None,
) -> bytes:
    """Decrypt a .kbkp envelope back to raw database dump bytes."""
    if len(payload) < HEADER_LENGTH + 16:
        msg = "Payload too short to contain valid .kbkp envelope"
        raise RestoreError(msg)

    magic = payload[:4]
    if magic != KBKP_MAGIC:
        msg = f"Invalid magic header: {magic!r}, expected {KBKP_MAGIC!r}"
        raise RestoreError(msg)

    version = payload[4]
    if version != KBKP_VERSION:
        msg = f"Unsupported backup version: {version}, expected {KBKP_VERSION}"
        raise RestoreError(msg)

    kdf_mode = payload[5]
    salt = payload[6:22]
    nonce = payload[22:34]
    header = payload[:HEADER_LENGTH]
    ciphertext = payload[HEADER_LENGTH:]

    if kdf_mode == KDF_MODE_PASSPHRASE_PBKDF2:
        if passphrase is None:
            msg = "Passphrase required to decrypt this backup archive"
            raise RestoreError(msg)
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=KEY_BYTES,
            salt=salt,
            iterations=PBKDF2_ITERATIONS,
        )
        derived_key = kdf.derive(passphrase.encode("utf-8"))
    elif kdf_mode == KDF_MODE_MASTER_KEK_HKDF:
        if master_kek is None:
            msg = "MASTER_KEK required to decrypt this backup archive"
            raise RestoreError(msg)
        hkdf = HKDF(
            algorithm=hashes.SHA256(),
            length=KEY_BYTES,
            salt=salt,
            info=b"kanban-standalone-backup-v1",
        )
        derived_key = hkdf.derive(master_kek)
    else:
        msg = f"Unknown KDF mode: {kdf_mode}"
        raise RestoreError(msg)

    aesgcm = AESGCM(derived_key)
    try:
        return aesgcm.decrypt(nonce, ciphertext, header)
    except Exception as exc:
        msg = "Decryption failed: invalid passphrase or corrupted payload"
        raise RestoreError(msg) from exc


async def run_pg_dump(  # noqa: C901, PLR0912, PLR0913
    *,
    pg_dump_bin: str | None = None,
    db_name: str = "kanban",
    db_user: str = "kanban_migrator",
    socket_dir: str | None = None,
    port: int | None = None,
    extra_env: dict[str, str] | None = None,
    settings: Settings | None = None,
    database_url: str | None = None,
) -> bytes:
    """Execute pg_dump over direct subprocess (zero shell) and return raw bytes."""
    binary = (
        pg_dump_bin
        or os.environ.get("KB_PG_DUMP_PATH")
        or shutil.which("pg_dump")
        or "/usr/bin/pg_dump"
    )

    resolved_db_name = db_name
    resolved_db_user = db_user
    resolved_host = socket_dir or os.environ.get("KB_TEST_PGHOST") or os.environ.get("PGHOST")
    resolved_port = port or os.environ.get("PGPORT")
    env_password: str | None = None

    url_str = database_url or (getattr(settings, "database_url", None) if settings else None)
    if url_str:
        try:
            parsed_url = make_url(str(url_str))
            if parsed_url.database:
                resolved_db_name = parsed_url.database
            if parsed_url.username:
                resolved_db_user = parsed_url.username
            if parsed_url.host and not socket_dir:
                resolved_host = parsed_url.host
            if parsed_url.port and not port:
                resolved_port = parsed_url.port
            if parsed_url.password:
                env_password = parsed_url.password
        except Exception:
            logger.warning("Could not parse database_url for pg_dump: %s", url_str, exc_info=True)

    args = [
        binary,
        "--format=custom",
        "--no-password",
        "-U",
        resolved_db_user,
        "-d",
        resolved_db_name,
    ]

    if resolved_host:
        args.extend(["-h", str(resolved_host)])

    if resolved_port:
        args.extend(["-p", str(resolved_port)])

    env = os.environ.copy()
    if env_password:
        env["PGPASSWORD"] = env_password
    if extra_env:
        env.update(extra_env)

    try:
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        stdout, stderr = await proc.communicate()
    except FileNotFoundError as exc:
        msg = f"pg_dump binary not found at '{binary}'"
        raise BackupError(msg) from exc
    except Exception as exc:
        msg = f"Subprocess execution error during pg_dump: {exc}"
        raise BackupError(msg) from exc

    if proc.returncode != 0:
        err_msg = stderr.decode("utf-8", errors="replace").strip()
        msg = f"pg_dump exited with code {proc.returncode}: {err_msg}"
        raise BackupError(msg)

    return stdout


def generate_compose_export() -> ComposeExportPayload:
    """Generate production Docker Compose YAML and promotion migration guide.

    Implements the canonical S2.4 / KB-P0-11 multi-container network topology:
    - edge_net: bridge (exposed ports)
    - app_net: internal (kanban app <-> mcp-server)
    - data_net: internal (kanban app <-> postgres)
    - sandbox_net: internal (kanban app <-> sandbox)
    - egress_llm_net: bridge (outbound LLM egress)

    Strict Invariant:
    - Zero secret values or keyring material are included.
    - mcp-server and sandbox containers do NOT attach to data_net.
    """
    compose_yaml = """# ----------------------------------------------------------------------------
# 👍kanban: Hardened Production Multi-Container Topology (Spec S2.4, KB-P0-11)
# ----------------------------------------------------------------------------
# Architecture:
# - postgres: Isolated on internal data_net with persistent volume
# - kanban (Web & API): Bridges edge_net, app_net, data_net, and egress_llm_net
# - mcp-server: Isolated on internal app_net (FORBIDDEN from data_net)
# - sandbox: Isolated on internal sandbox_net (FORBIDDEN from data_net)
# ----------------------------------------------------------------------------

services:
  postgres:
    image: pgvector/pgvector:pg16
    container_name: kanban-postgres
    restart: unless-stopped
    environment:
      POSTGRES_DB: kanban
      POSTGRES_USER: ${POSTGRES_USER:-kanban}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    volumes:
      - kanban_db_data:/var/lib/postgresql/data
    networks:
      - data_net
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER:-kanban} -d kanban"]
      interval: 5s
      timeout: 5s
      retries: 5

  kanban:
    image: thumbs-up-kanban:latest
    container_name: kanban-app
    restart: unless-stopped
    depends_on:
      postgres:
        condition: service_healthy
    ports:
      - "${PORT:-8080}:8080"
    environment:
      KANBAN_DATABASE_URL: "postgresql+asyncpg://${POSTGRES_USER:-kanban}:${POSTGRES_PASSWORD}@postgres:5432/kanban"
      KANBAN_MASTER_KEK: "${MASTER_KEK}"
      KANBAN_AUTH_PEPPER: "${AUTH_PEPPER}"
      KANBAN_SESSION_HMAC_KEY: "${SESSION_HMAC_KEY}"
      KANBAN_PUBLIC_BASE_URL: "${PUBLIC_BASE_URL:-http://localhost:8080}"
      KANBAN_AIR_GAP_MODE: "${AIR_GAP_MODE:-false}"
    networks:
      - edge_net
      - app_net
      - data_net
      - egress_llm_net

  mcp-server:
    image: thumbs-up-kanban:latest
    container_name: kanban-mcp
    restart: unless-stopped
    depends_on:
      - kanban
    command: ["uv", "run", "python", "-m", "kanban.mcp.server"]
    environment:
      KANBAN_API_BASE_URL: "http://kanban:8080"
      KANBAN_MASTER_KEK: "${MASTER_KEK}"
    networks:
      - app_net

  sandbox:
    image: thumbs-up-kanban:sandbox
    container_name: kanban-sandbox
    restart: unless-stopped
    security_opt:
      - seccomp:unconfined
    cap_add:
      - SYS_ADMIN
    networks:
      - sandbox_net

networks:
  edge_net:
    driver: bridge
  app_net:
    internal: true
  data_net:
    internal: true
  sandbox_net:
    internal: true
  egress_llm_net:
    driver: bridge

volumes:
  kanban_db_data:
"""

    env_template = """# ----------------------------------------------------------------------------
# 👍kanban Production Environment Configuration (.env)
# ----------------------------------------------------------------------------
# Generate 32-byte cryptographic keys using secrets.token_bytes(32)
# ----------------------------------------------------------------------------

PORT=8080
PUBLIC_BASE_URL=https://kanban.example.com
AIR_GAP_MODE=false

# Database Credentials
POSTGRES_PASSWORD=replace-with-secure-postgres-password
KANBAN_APP_DB_PASSWORD=replace-with-secure-app-password

# Platform Keyring (Base64URL encoded 32-byte keys)
MASTER_KEK=replace-with-base64url-32byte-master-kek
AUTH_PEPPER=replace-with-base64url-32byte-auth-pepper
SESSION_HMAC_KEY=replace-with-base64url-32byte-session-hmac-key
"""

    migration_steps_markdown = """### Standalone to Production Multi-Container Promotion Runbook

Follow these four steps to promote your standalone instance to a production deployment:

#### Step 1: Generate Production Cryptographic Keys & Configuration
Create your production `.env` file alongside `docker-compose.yml`:
```bash
# Generate 32-byte Base64URL keys
python3 -c "import secrets, base64; print('MASTER_KEK=' + \
base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())" >> .env
python3 -c "import secrets, base64; print('AUTH_PEPPER=' + \
base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())" >> .env
python3 -c "import secrets, base64; print('SESSION_HMAC_KEY=' + \
base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())" >> .env
python3 -c "import secrets; print('POSTGRES_PASSWORD=' + secrets.token_hex(24))" >> .env
python3 -c "import secrets; print('KANBAN_APP_DB_PASSWORD=' + secrets.token_hex(24))" >> .env
```

#### Step 2: Download Encrypted Backup (.kbkp)
From Standalone Status Panel, supply an encryption passphrase (minimum 16 characters)
and click **Download Encrypted Backup (.kbkp)**.

#### Step 3: Decrypt Backup & Boot PostgreSQL Container
Decrypt your archive locally and spin up the PostgreSQL 16 service:
```bash
# Decrypt .kbkp archive to raw custom dump
python3 -c "
from kanban.standalone.export_service import decrypt_backup
with open('kanban-backup.kbkp', 'rb') as f:
    decrypted = decrypt_backup(f.read(), passphrase='YOUR_PASSPHRASE')
with open('kanban-backup.dump', 'wb') as f:
    f.write(decrypted)
"

# Start the PostgreSQL database service
docker compose up -d postgres
```

#### Step 4: Restore Database & Launch Multi-Container Stack
Restore the database dump into PostgreSQL 16 and boot all platform services:
```bash
# Wait for PostgreSQL healthcheck
docker compose exec postgres pg_isready -U kanban_migrator -d kanban

# Restore schema and data
docker compose exec -T postgres pg_restore -U kanban_migrator -d kanban \
  --clean --if-exists < kanban-backup.dump

# Boot full hardened multi-container topology
docker compose up -d
```
"""

    # Standalone Single-Container Deployment (docker-compose.standalone.yml)
    # -----------------------------------------------------------------
    header_sep = "# " + "-" * 65
    single_container_compose_yaml = (
        f"{header_sep}\n"
        "# 👍kanban: Standalone Single-Container Deployment (docker-compose.yml)\n"
        f"{header_sep}\n"
        "services:\n"
        "  kanban:\n"
        "    image: thumbs-up-kanban:latest\n"
        "    container_name: kanban-standalone\n"
        "    restart: unless-stopped\n"
        "    ports:\n"
        '      - "${PORT:-8080}:8080"\n'
        "    volumes:\n"
        "      - kanban_data:/var/lib/kanban/data\n"
        "    environment:\n"
        '      KANBAN_PUBLIC_BASE_URL: "${PUBLIC_BASE_URL:-http://localhost:8080}"\n'
        '      KANBAN_AIR_GAP_MODE: "${AIR_GAP_MODE:-false}"\n'
        "\n"
        "volumes:\n"
        "  kanban_data:\n"
    )

    return ComposeExportPayload(
        filename="docker-compose.yml",
        compose_yaml=compose_yaml.strip() + "\n",
        env_template=env_template.strip() + "\n",
        migration_steps_markdown=migration_steps_markdown.strip() + "\n",
        single_container_compose_yaml=single_container_compose_yaml.strip() + "\n",
    )
