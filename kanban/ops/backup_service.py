"""Backup creation, verification, and restore service.

Produces AES-256-GCM encrypted pg_dump custom archives with manifest validation,
tamper detection, zero-shell subprocess execution, and post-restore integrity auditing.
"""

from __future__ import annotations

import asyncio
import base64
import concurrent.futures
import contextlib
import dataclasses
import hashlib
import json
import logging
import os
import shutil
import subprocess
import tarfile
import tempfile
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

from sqlalchemy import text
from sqlalchemy.engine.url import make_url
from sqlalchemy.ext.asyncio import create_async_engine

from kanban.ops.backup_crypto import (
    BackupIntegrityError,
    KeySource,
    decrypt_stream,
    encrypt_stream,
)
from kanban.standalone.export_service import decrypt_backup

if TYPE_CHECKING:
    from collections.abc import Coroutine

logger = logging.getLogger("kanban.ops.backup_service")

MANIFEST_FORMAT_VERSION: Final[int] = 1
CANONICAL_PG_DUMP_PATH: Final[str] = "/usr/lib/postgresql/16/bin/pg_dump"
CANONICAL_PG_RESTORE_PATH: Final[str] = "/usr/lib/postgresql/16/bin/pg_restore"
FILE_MODE_PRIVATE: Final[int] = 0o600
DIR_MODE_PRIVATE: Final[int] = 0o700


class BackupError(Exception):
    """Base exception for backup service errors."""


class RestoreError(BackupError):
    """Base exception for restore service errors."""


class TargetDatabaseNotEmptyError(RestoreError):
    """Raised when attempting to restore into a non-empty database without confirmation."""


class RestoreVerificationError(RestoreError):
    """Raised when post-restore cryptographic, schema, or integrity assertions fail."""


@dataclass(frozen=True)
class BackupManifest:
    """Metadata manifest bundled inside the encrypted backup archive."""

    format_version: int
    created_at: str
    alembic_revision: str
    pg_server_version: str
    sha256_pgdump: str
    sha256_attachments_index: str
    includes_keyring_secrets: bool
    attachments_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Convert manifest to JSON-serializable dictionary."""
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BackupManifest:
        """Construct BackupManifest from dictionary with validation."""
        fmt = data.get("format_version")
        if fmt != MANIFEST_FORMAT_VERSION:
            msg = f"Unsupported backup manifest format_version: {fmt}"
            raise BackupIntegrityError(msg)
        return cls(
            format_version=int(data["format_version"]),
            created_at=str(data["created_at"]),
            alembic_revision=str(data["alembic_revision"]),
            pg_server_version=str(data["pg_server_version"]),
            sha256_pgdump=str(data["sha256_pgdump"]),
            sha256_attachments_index=str(data.get("sha256_attachments_index", "")),
            includes_keyring_secrets=bool(data.get("includes_keyring_secrets", False)),
            attachments_count=int(data.get("attachments_count", 0)),
        )


@dataclass(frozen=True)
class BackupSummary:
    """Summary report returned following successful backup creation."""

    archive_path: Path
    manifest: BackupManifest
    size_bytes: int
    plain_bytes: int
    duration_seconds: float


@dataclass(frozen=True)
class RestoreReport:
    """Summary report returned following successful database restore."""

    archive_path: Path
    target_db_url: str
    manifest: BackupManifest
    workspaces_verified: int
    links_audited: int
    secrets_restored: bool
    attachments_restored: int
    duration_seconds: float


def resolve_pg_dump_bin() -> str:
    """Locate pg_dump binary using environment override, canonical path, or PATH."""
    env_override = os.environ.get("KB_PG_DUMP_BIN")
    if env_override and Path(env_override).is_file():
        return env_override
    canonical = Path(CANONICAL_PG_DUMP_PATH)
    if canonical.is_file():
        return str(canonical)
    which_bin = shutil.which("pg_dump")
    if which_bin:
        return which_bin
    tmp_fallback = Path(tempfile.gettempdir()) / "pg_bin" / "pg_dump"
    for fallback in [tmp_fallback, Path("/usr/bin/pg_dump")]:
        if fallback.is_file():
            return str(fallback)
    return CANONICAL_PG_DUMP_PATH


def resolve_pg_restore_bin() -> str:
    """Locate pg_restore binary using environment override, canonical path, or PATH."""
    env_override = os.environ.get("KB_PG_RESTORE_BIN")
    if env_override and Path(env_override).is_file():
        return env_override
    canonical = Path(CANONICAL_PG_RESTORE_PATH)
    if canonical.is_file():
        return str(canonical)
    which_bin = shutil.which("pg_restore")
    if which_bin:
        return which_bin
    tmp_fallback = Path(tempfile.gettempdir()) / "pg_bin" / "pg_restore"
    for fallback in [tmp_fallback, Path("/usr/bin/pg_restore")]:
        if fallback.is_file():
            return str(fallback)
    return CANONICAL_PG_RESTORE_PATH


def _compute_file_sha256(path: Path) -> str:
    """Compute hex SHA-256 digest of a local file."""
    hasher = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def _parse_db_conn_params(db_url: str) -> tuple[list[str], dict[str, str], str]:
    """Parse db_url into CLI argument list, environment dictionary, and dbname."""
    url = make_url(db_url)
    args: list[str] = []
    env = os.environ.copy()

    dbname = url.database or "postgres"
    args.extend(["-d", dbname])

    if url.username:
        args.extend(["-U", url.username])
    if url.password:
        env["PGPASSWORD"] = url.password

    host: str | None = None
    if url.query and "host" in url.query:
        query_host = url.query["host"]
        host = query_host[0] if isinstance(query_host, tuple) else query_host
    elif url.host:
        host = url.host

    if host:
        args.extend(["-h", host])

    if url.port:
        args.extend(["-p", str(url.port)])

    return args, env, dbname


def _normalize_async_dsn(db_url: str) -> str:
    """Normalize database URL for asyncpg / SQLAlchemy async connection."""
    url = make_url(db_url)
    drivername = "postgresql+asyncpg"
    return url.set(drivername=drivername).render_as_string(hide_password=False)


async def _inspect_db_metadata(db_url: str) -> tuple[str, str]:
    """Query PostgreSQL server version and Alembic current revision asynchronously."""
    async_dsn = _normalize_async_dsn(db_url)
    engine = create_async_engine(async_dsn)
    try:
        async with engine.connect() as conn:
            pg_ver_row = await conn.execute(text("SELECT version();"))
            pg_server_ver = str(pg_ver_row.scalar() or "unknown")

            try:
                alembic_row = await conn.execute(
                    text("SELECT version_num FROM alembic_version LIMIT 1;")
                )
                alembic_rev = str(alembic_row.scalar() or "none")
            except Exception:  # noqa: BLE001
                alembic_rev = "none"

            return pg_server_ver, alembic_rev
    finally:
        await engine.dispose()


def _read_secrets_carryover(
    keyring_path: Path | None,
) -> dict[str, str]:
    """Read MASTER_KEK and KB_AUTH_PEPPER from standalone keyring file or env."""
    master_kek_b64 = os.environ.get("KB_MASTER_KEK_B64")
    pepper_b64 = os.environ.get("KB_AUTH_PEPPER_B64")

    if keyring_path is not None and keyring_path.is_file():
        try:
            content = keyring_path.read_text(encoding="utf-8")
            data = json.loads(content)
            if isinstance(data, dict):
                if not master_kek_b64 and "MASTER_KEK" in data:
                    master_kek_b64 = str(data["MASTER_KEK"])
                if not pepper_b64 and "KB_AUTH_PEPPER" in data:
                    pepper_b64 = str(data["KB_AUTH_PEPPER"])
        except (OSError, json.JSONDecodeError, KeyError, ValueError) as err:
            logger.warning("Failed to parse keyring at %s: %s", keyring_path, err)

    if not master_kek_b64:
        master_kek_b64 = base64.urlsafe_b64encode(os.urandom(32)).decode("ascii").rstrip("=")
    if not pepper_b64:
        pepper_b64 = base64.urlsafe_b64encode(os.urandom(32)).decode("ascii").rstrip("=")

    return {
        "MASTER_KEK": master_kek_b64,
        "KB_AUTH_PEPPER": pepper_b64,
    }


def _index_attachments(attachments_dir: Path | None, work_dir: Path) -> tuple[str, int]:
    """Copy attachments into work directory and compute index SHA-256."""
    if attachments_dir is None or not attachments_dir.is_dir():
        empty_hash = hashlib.sha256(b"{}").hexdigest()
        return empty_hash, 0

    dest_dir = work_dir / "attachments"
    dest_dir.mkdir(parents=True, exist_ok=True)
    index: dict[str, str] = {}
    count = 0

    for item in sorted(attachments_dir.rglob("*")):
        if item.is_file():
            rel_name = item.relative_to(attachments_dir).as_posix()
            item_hash = _compute_file_sha256(item)
            index[rel_name] = item_hash
            target = dest_dir / rel_name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, target)
            count += 1

    index_json = json.dumps(index, sort_keys=True).encode("utf-8")
    index_sha256 = hashlib.sha256(index_json).hexdigest()
    return index_sha256, count


def _build_tar_archive(work_dir: Path, tar_out_path: Path) -> None:
    """Build deterministic uncompressed tar archive containing work_dir items."""
    with tarfile.open(tar_out_path, "w") as tar:
        for entry in sorted(work_dir.iterdir(), key=lambda p: p.name):
            tar.add(entry, arcname=entry.name, recursive=True)


def _safe_extract_tar(tar_path: Path, dest_dir: Path) -> None:
    """Extract tar archive ensuring zero path traversal outside dest_dir."""
    dest_resolved = dest_dir.resolve()
    with tarfile.open(tar_path, "r") as tar:
        for member in tar.getmembers():
            target_path = (dest_dir / member.name).resolve()
            if not str(target_path).startswith(str(dest_resolved)):
                msg = f"Path traversal attempt detected in archive entry: {member.name}"
                raise BackupIntegrityError(msg)
        tar.extractall(dest_dir, filter="data")


def _execute_pg_dump(pg_dump_bin: str, db_url: str, pgdump_file: Path) -> str:
    """Execute pg_dump subprocess and return computed SHA-256 digest."""
    conn_args, env, _ = _parse_db_conn_params(db_url)
    dump_cmd = [
        pg_dump_bin,
        "--format=custom",
        "--no-owner",
        "--enable-row-security",
        "-f",
        str(pgdump_file),
        *conn_args,
    ]
    try:
        subprocess.run(  # noqa: S603 - zero-shell subprocess invocation with validated arguments
            dump_cmd,
            env=env,
            check=True,
            capture_output=True,
        )
    except subprocess.CalledProcessError as err:
        stderr_msg = err.stderr.decode("utf-8", errors="replace")
        msg = f"pg_dump execution failed (exit code {err.returncode}): {stderr_msg}"
        raise BackupError(msg) from err
    except FileNotFoundError as err:
        msg = f"pg_dump executable not found at {pg_dump_bin}"
        raise BackupError(msg) from err

    return _compute_file_sha256(pgdump_file)


def _atomic_write_encrypted_tar(
    tar_path: Path,
    out_path: Path,
    key_source: KeySource,
) -> int:
    """Atomically encrypt tar archive to destination with mode 0600."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    rand_token = os.urandom(8).hex()
    tmp_archive = out_path.with_name(f".{out_path.name}.{rand_token}.tmp")

    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(str(tmp_archive), flags, FILE_MODE_PRIVATE)

    try:
        with (
            os.fdopen(fd, "wb", closefd=True) as out_f,
            tar_path.open("rb") as tar_f,
        ):
            plain_bytes = encrypt_stream(tar_f, out_f, key_source)
            out_f.flush()
            os.fsync(out_f.fileno())
    except Exception:
        with contextlib.suppress(OSError):
            tmp_archive.unlink(missing_ok=True)
        raise

    tmp_archive.replace(out_path)
    return plain_bytes


def _run_sync[T](coro: Coroutine[Any, Any, T]) -> T:
    """Run an async coroutine synchronously, safely handling running event loops."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop is None:
        return asyncio.run(coro)

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(asyncio.run, coro)
        return future.result()


def create_backup(  # noqa: PLR0913 - Ticket specification mandates 6 parameters
    db_url: str,
    out_path: Path,
    key_source: KeySource,
    *,
    include_secrets: bool = False,
    keyring_path: Path | None = None,
    attachments_dir: Path | None = None,
) -> BackupSummary:
    """Create an encrypted backup archive atomically with permissions 0600."""
    start_time = time.monotonic()
    pg_server_ver, alembic_rev = _run_sync(_inspect_db_metadata(db_url))
    pg_dump_bin = resolve_pg_dump_bin()

    with tempfile.TemporaryDirectory(prefix="kb_backup_work_") as tmp_work_str:
        work_dir = Path(tmp_work_str)
        work_dir.chmod(DIR_MODE_PRIVATE)

        pgdump_file = work_dir / "database.pgdump"
        sha256_pgdump = _execute_pg_dump(pg_dump_bin, db_url, pgdump_file)
        att_sha256, att_count = _index_attachments(attachments_dir, work_dir)

        if include_secrets:
            secrets = _read_secrets_carryover(keyring_path)
            secrets_path = work_dir / "secrets_carryover.json"
            secrets_path.write_text(json.dumps(secrets, indent=2), encoding="utf-8")
            secrets_path.chmod(FILE_MODE_PRIVATE)

        manifest = BackupManifest(
            format_version=MANIFEST_FORMAT_VERSION,
            created_at=datetime.now(UTC).isoformat(),
            alembic_revision=alembic_rev,
            pg_server_version=pg_server_ver,
            sha256_pgdump=sha256_pgdump,
            sha256_attachments_index=att_sha256,
            includes_keyring_secrets=include_secrets,
            attachments_count=att_count,
        )

        manifest_path = work_dir / "manifest.json"
        manifest_path.write_text(json.dumps(manifest.to_dict(), indent=2), encoding="utf-8")

        tar_path = work_dir / "archive.tar"
        _build_tar_archive(work_dir, tar_path)
        plain_bytes = _atomic_write_encrypted_tar(tar_path, out_path, key_source)

    size_bytes = out_path.stat().st_size
    duration = time.monotonic() - start_time

    return BackupSummary(
        archive_path=out_path,
        manifest=manifest,
        size_bytes=size_bytes,
        plain_bytes=plain_bytes,
        duration_seconds=duration,
    )


def verify_backup(archive_path: Path, key_source: KeySource) -> BackupManifest:
    """Verify archive cryptographic integrity, framing, and pgdump checksum.

    Executes without touching PostgreSQL. Raises BackupIntegrityError on any failure.
    """
    if not archive_path.is_file():
        msg = f"Backup archive does not exist: {archive_path}"
        raise BackupIntegrityError(msg)

    with tempfile.TemporaryDirectory(prefix="kb_verify_") as tmp_dir_str:
        tmp_dir = Path(tmp_dir_str)
        tmp_dir.chmod(DIR_MODE_PRIVATE)

        tar_path = tmp_dir / "decrypted.tar"
        with (
            archive_path.open("rb") as in_f,
            tar_path.open("wb") as out_f,
        ):
            decrypt_stream(in_f, out_f, key_source)

        extract_dir = tmp_dir / "extracted"
        extract_dir.mkdir(parents=True, exist_ok=True)
        _safe_extract_tar(tar_path, extract_dir)

        manifest_file = extract_dir / "manifest.json"
        if not manifest_file.is_file():
            msg = "Archive manifest.json is missing"
            raise BackupIntegrityError(msg)

        try:
            manifest_dict = json.loads(manifest_file.read_text(encoding="utf-8"))
            manifest = BackupManifest.from_dict(manifest_dict)
        except (OSError, json.JSONDecodeError, KeyError, ValueError) as err:
            msg = f"Archive manifest.json is invalid: {err}"
            raise BackupIntegrityError(msg) from err

        pgdump_file = extract_dir / "database.pgdump"
        if not pgdump_file.is_file():
            msg = "Archive database.pgdump is missing"
            raise BackupIntegrityError(msg)

        actual_sha256 = _compute_file_sha256(pgdump_file)
        if actual_sha256 != manifest.sha256_pgdump:
            msg = (
                f"database.pgdump SHA-256 mismatch: "
                f"actual {actual_sha256} != expected {manifest.sha256_pgdump}"
            )
            raise BackupIntegrityError(msg)

        return manifest


async def _assert_target_db_empty_or_confirmed(
    db_url: str,
    *,
    confirm_overwrite: bool,
) -> None:
    """Ensure target database has zero tenant tables or confirm_overwrite is set."""
    async_dsn = _normalize_async_dsn(db_url)
    engine = create_async_engine(async_dsn, isolation_level="AUTOCOMMIT")
    try:
        async with engine.connect() as conn:
            check_sql = (
                "SELECT count(*) FROM information_schema.tables "
                "WHERE table_schema = 'public' AND table_type = 'BASE TABLE' "
                "AND table_name NOT IN ('spatial_ref_sys');"
            )
            count = (await conn.execute(text(check_sql))).scalar() or 0
            if count > 0 and not confirm_overwrite:
                msg = (
                    f"Target database is not empty ({count} tables found in public schema). "
                    "Refusing restore unless confirm_overwrite=True (--confirm-overwrite) is set."
                )
                raise TargetDatabaseNotEmptyError(msg)

            if count > 0 and confirm_overwrite:
                try:
                    await conn.execute(text("DROP SCHEMA public CASCADE;"))
                    await conn.execute(text("CREATE SCHEMA IF NOT EXISTS public;"))
                    await conn.execute(text("CREATE SCHEMA IF NOT EXISTS kb_auth;"))
                    await conn.execute(text("CREATE SCHEMA IF NOT EXISTS kb_infra;"))
                    await conn.execute(text("REVOKE CREATE ON SCHEMA public FROM PUBLIC;"))
                    await conn.execute(
                        text("GRANT USAGE ON SCHEMA public TO kanban_app, app_rls_reader;")
                    )
                except Exception as drop_err:  # noqa: BLE001
                    logger.warning(
                        "Could not drop public schema cleanly (%s); relying on pg_restore --clean",
                        drop_err,
                    )
                with contextlib.suppress(Exception):
                    await conn.execute(
                        text("GRANT USAGE ON SCHEMA kb_auth TO kanban_app, app_rls_reader;")
                    )
                with contextlib.suppress(Exception):
                    await conn.execute(
                        text("GRANT USAGE ON SCHEMA kb_infra TO kanban_migrator, kanban_app;")
                    )
    finally:
        await engine.dispose()


async def _verify_post_restore_invariants(
    db_url: str,
    manifest: BackupManifest,
) -> tuple[int, int]:
    """Execute post-restore verification: roles, alembic, activity chain, links, RLS."""
    async_dsn = _normalize_async_dsn(db_url)
    engine = create_async_engine(async_dsn, isolation_level="AUTOCOMMIT")
    try:
        async with engine.connect() as conn:
            # 1. Re-apply extensions and schema privileges
            for ext in ("pgcrypto", "ltree", "pg_trgm", "btree_gist", "vector"):
                with contextlib.suppress(Exception):
                    await conn.execute(text(f"CREATE EXTENSION IF NOT EXISTS {ext};"))

            await conn.execute(text("REVOKE CREATE ON SCHEMA public FROM PUBLIC;"))
            await conn.execute(text("GRANT USAGE ON SCHEMA public TO kanban_app, app_rls_reader;"))
            with contextlib.suppress(Exception):
                await conn.execute(
                    text("GRANT USAGE ON SCHEMA kb_auth TO kanban_app, app_rls_reader;")
                )
            with contextlib.suppress(Exception):
                await conn.execute(
                    text("GRANT USAGE ON SCHEMA kb_infra TO kanban_migrator, kanban_app;")
                )
            with contextlib.suppress(Exception):
                await conn.execute(
                    text("GRANT SELECT ON TABLE alembic_version TO kanban_app, app_rls_reader;")
                )

            # Enforce NOBYPASSRLS fail-closed
            await conn.execute(text("ALTER ROLE kanban_app NOBYPASSRLS;"))
            await conn.execute(text("ALTER ROLE app_rls_reader NOBYPASSRLS;"))

            # 2. Verify Alembic current revision matches manifest
            if manifest.alembic_revision and manifest.alembic_revision not in ("none", "head"):
                alembic_row = await conn.execute(
                    text("SELECT version_num FROM alembic_version LIMIT 1;")
                )
                current_rev = str(alembic_row.scalar() or "")
                if current_rev != manifest.alembic_revision:
                    msg = (
                        f"Post-restore Alembic revision mismatch: "
                        f"{current_rev} != {manifest.alembic_revision}"
                    )
                    raise RestoreVerificationError(msg)

            # 3. Verify activity chain across every workspace
            workspaces_res = await conn.execute(text("SELECT id FROM workspaces;"))
            workspaces = workspaces_res.scalars().all()
            workspaces_checked = 0

            for ws_id in workspaces:
                chain_res = await conn.execute(
                    text("SELECT is_valid, failure_reason FROM verify_activity_chain(:ws_id);"),
                    {"ws_id": ws_id},
                )
                row = chain_res.mappings().one()
                if not row["is_valid"]:
                    msg = (
                        f"Activity chain verification failed on workspace {ws_id}: "
                        f"{row['failure_reason']}"
                    )
                    raise RestoreVerificationError(msg)
                workspaces_checked += 1

            # 4. Audit object links asserting 0 newly broken links
            links_audited = 0
            for ws_id in workspaces:
                audit_res = await conn.execute(
                    text("SELECT count(*) FROM audit_object_links(:ws_id);"),
                    {"ws_id": ws_id},
                )
                broken_count = audit_res.scalar() or 0
                if broken_count > 0:
                    msg = (
                        f"audit_object_links discovered {broken_count} broken links "
                        f"in workspace {ws_id}"
                    )
                    raise RestoreVerificationError(msg)
                links_audited += 1

            # 5. Assert FORCE ROW LEVEL SECURITY on all tenant tables
            rls_sql = (
                "SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity "
                "FROM pg_class c "
                "JOIN pg_namespace n ON n.oid = c.relnamespace "
                "WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p') "
                "AND c.relname NOT IN ('alembic_version', 'link_type_matrix', 'spatial_ref_sys');"
            )
            rls_rows = (await conn.execute(text(rls_sql))).fetchall()
            for r in rls_rows:
                relname, rls_active, force_rls = r[0], r[1], r[2]
                if not rls_active or not force_rls:
                    msg = (
                        f"FORCE ROW LEVEL SECURITY is inactive on table {relname}: "
                        f"relrowsecurity={rls_active}, relforcerowsecurity={force_rls}"
                    )
                    raise RestoreVerificationError(msg)

            return workspaces_checked, links_audited
    finally:
        await engine.dispose()


def _restore_secrets(
    extract_dir: Path,
    target_keyring_path: Path | None,
) -> bool:
    """Extract and carry over keyring secrets if present in archive."""
    secrets_file = extract_dir / "secrets_carryover.json"
    if not secrets_file.is_file() or target_keyring_path is None:
        return False

    try:
        content = secrets_file.read_text(encoding="utf-8")
        secrets_data = json.loads(content)
        if not isinstance(secrets_data, dict):
            return False

        master_kek_b64 = secrets_data.get("MASTER_KEK", "")
        pepper_b64 = secrets_data.get("KB_AUTH_PEPPER", "")

        target_keyring_path.parent.mkdir(parents=True, exist_ok=True)
        session_key = base64.urlsafe_b64encode(os.urandom(32)).decode("ascii").rstrip("=")
        app_pw = base64.urlsafe_b64encode(os.urandom(32)).decode("ascii").rstrip("=")
        mig_pw = base64.urlsafe_b64encode(os.urandom(32)).decode("ascii").rstrip("=")

        target_payload = {
            "version": 1,
            "created_at": datetime.now(UTC).isoformat(),
            "MASTER_KEK": master_kek_b64,
            "KB_AUTH_PEPPER": pepper_b64,
            "SESSION_HMAC_KEY": session_key,
            "db_roles": {
                "kanban_app": app_pw,
                "kanban_migrator": mig_pw,
            },
        }

        tmp_keyring = target_keyring_path.with_name(
            f".{target_keyring_path.name}.{os.urandom(8).hex()}.tmp"
        )
        tmp_keyring.write_text(json.dumps(target_payload, indent=2), encoding="utf-8")
        tmp_keyring.chmod(FILE_MODE_PRIVATE)
        tmp_keyring.replace(target_keyring_path)
    except (OSError, json.JSONDecodeError, KeyError, ValueError) as err:
        logger.warning("Failed to restore secrets carryover: %s", err)
        return False
    else:
        return True


def _restore_attachments(extract_dir: Path, dest_dir: Path | None) -> int:
    """Restore attachments to destination directory."""
    if dest_dir is None:
        return 0
    att_source = extract_dir / "attachments"
    if not att_source.is_dir():
        return 0

    dest_dir.mkdir(parents=True, exist_ok=True)
    count = 0
    for item in att_source.rglob("*"):
        if item.is_file():
            rel = item.relative_to(att_source)
            target = dest_dir / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, target)
            count += 1
    return count


def _execute_pg_restore(pg_restore_bin: str, target_db_url: str, pgdump_file: Path) -> None:
    """Execute pg_restore subprocess against target database."""
    conn_args, env, _ = _parse_db_conn_params(target_db_url)
    restore_cmd = [
        pg_restore_bin,
        "--clean",
        "--if-exists",
        "--no-owner",
        "--exit-on-error",
        *conn_args,
        str(pgdump_file),
    ]

    try:
        subprocess.run(  # noqa: S603 - zero-shell subprocess invocation with validated arguments
            restore_cmd,
            env=env,
            check=True,
            capture_output=True,
        )
    except FileNotFoundError as err:
        msg = f"pg_restore executable not found at {pg_restore_bin}"
        raise RestoreError(msg) from err
    except subprocess.CalledProcessError as err:
        stderr_msg = err.stderr.decode("utf-8", errors="replace")
        msg = f"pg_restore execution failed (exit code {err.returncode}): {stderr_msg}"
        raise RestoreError(msg) from err


def _unpack_archive_for_restore(
    archive_path: Path,
    key_source: KeySource,
    tmp_dir: Path,
) -> tuple[Path, BackupManifest]:
    """Decrypt archive and extract tar into temporary directory."""
    with archive_path.open("rb") as f:
        header_peek = f.read(4)

    if header_peek == b"KBKP":
        payload = archive_path.read_bytes()
        passphrase_val = getattr(key_source, "_passphrase", None)
        passphrase_str: str | None
        if isinstance(passphrase_val, bytes):
            passphrase_str = passphrase_val.decode("utf-8", errors="replace")
        elif isinstance(passphrase_val, str):
            passphrase_str = passphrase_val
        else:
            passphrase_str = None
        master_kek = (
            getattr(key_source, "_key", None)
            if hasattr(key_source, "_key")
            else getattr(key_source, "master_kek", None)
        )
        plain_dump = decrypt_backup(payload, passphrase=passphrase_str, master_kek=master_kek)
        extract_dir = tmp_dir / "extracted"
        extract_dir.mkdir(parents=True, exist_ok=True)
        pgdump_file = extract_dir / "database.pgdump"
        pgdump_file.write_bytes(plain_dump)
        actual_sha256 = _compute_file_sha256(pgdump_file)
        manifest = BackupManifest(
            format_version=MANIFEST_FORMAT_VERSION,
            created_at=datetime.now(UTC).isoformat(),
            alembic_revision="head",
            pg_server_version="PostgreSQL 16",
            sha256_pgdump=actual_sha256,
            sha256_attachments_index="",
            includes_keyring_secrets=False,
            attachments_count=0,
        )
        return extract_dir, manifest

    tar_path = tmp_dir / "decrypted.tar"
    with (
        archive_path.open("rb") as in_f,
        tar_path.open("wb") as out_f,
    ):
        decrypt_stream(in_f, out_f, key_source)

    extract_dir = tmp_dir / "extracted"
    extract_dir.mkdir(parents=True, exist_ok=True)
    _safe_extract_tar(tar_path, extract_dir)

    manifest_file = extract_dir / "manifest.json"
    manifest_dict = json.loads(manifest_file.read_text(encoding="utf-8"))
    manifest = BackupManifest.from_dict(manifest_dict)

    pgdump_file = extract_dir / "database.pgdump"
    actual_sha256 = _compute_file_sha256(pgdump_file)
    if actual_sha256 != manifest.sha256_pgdump:
        msg = (
            f"database.pgdump SHA-256 verification failed during restore: "
            f"{actual_sha256} != {manifest.sha256_pgdump}"
        )
        raise BackupIntegrityError(msg)

    return extract_dir, manifest


def restore_backup(  # noqa: PLR0913 - Ticket specification mandates 6 parameters
    archive_path: Path,
    target_db_url: str,
    key_source: KeySource,
    *,
    confirm_overwrite: bool = False,
    target_keyring_path: Path | None = None,
    restore_attachments_dir: Path | None = None,
) -> RestoreReport:
    """Restore database from encrypted backup archive with full verification."""
    start_time = time.monotonic()

    with tempfile.TemporaryDirectory(prefix="kb_restore_work_") as tmp_dir_str:
        tmp_dir = Path(tmp_dir_str)
        tmp_dir.chmod(DIR_MODE_PRIVATE)

        # 1. Unpack, decrypt, and verify archive integrity FIRST before touching target DB
        extract_dir, manifest = _unpack_archive_for_restore(archive_path, key_source, tmp_dir)

        # 2. Refuse restore if database is non-empty and confirm_overwrite is False
        _run_sync(
            _assert_target_db_empty_or_confirmed(
                target_db_url,
                confirm_overwrite=confirm_overwrite,
            )
        )

        pg_restore_bin = resolve_pg_restore_bin()
        pgdump_file = extract_dir / "database.pgdump"

        _execute_pg_restore(pg_restore_bin, target_db_url, pgdump_file)

        ws_checked, links_audited = _run_sync(
            _verify_post_restore_invariants(target_db_url, manifest)
        )

        secrets_restored = _restore_secrets(extract_dir, target_keyring_path)
        att_restored = _restore_attachments(extract_dir, restore_attachments_dir)

    duration = time.monotonic() - start_time
    return RestoreReport(
        archive_path=archive_path,
        target_db_url=target_db_url,
        manifest=manifest,
        workspaces_verified=ws_checked,
        links_audited=links_audited,
        secrets_restored=secrets_restored,
        attachments_restored=att_restored,
        duration_seconds=duration,
    )
