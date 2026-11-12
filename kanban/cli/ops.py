"""Operational CLI subcommands for backup, restore, and production promotion.

Registers backup, restore, and promote subcommands under kanban-ctl with strict
process-list secret hygiene, fail-closed validation, and structured console reports.
"""

from __future__ import annotations

import argparse
import getpass
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Final

from kanban.ops.backup_crypto import (
    BackupCryptoError,
    BackupIntegrityError,
    KeySource,
    PassphraseKeySource,
    RawKeySource,
)
from kanban.ops.backup_service import (
    BackupError,
    RestoreError,
    TargetDatabaseNotEmptyError,
    create_backup,
    restore_backup,
    verify_backup,
)
from kanban.ops.compose_export import export_production_bundle

if TYPE_CHECKING:
    from collections.abc import Sequence

FORBIDDEN_ARGV_MSG: Final[str] = (
    "Error: SECRET_IN_ARGV_FORBIDDEN: Passing keys or passphrases as command-line arguments "
    "is strictly forbidden to prevent disclosure in process lists (ps). "
    "Use --key-env or --passphrase-file."
)


def check_forbidden_secret_args(argv: Sequence[str]) -> bool:
    """Return True if any forbidden secret parameter is found on argv."""
    for arg in argv:
        if arg in ("--key", "--passphrase") or arg.startswith(("--key=", "--passphrase=")):
            return True
    return False


def _resolve_fallback_key_source() -> KeySource | None:
    """Check standard environment variables or interactive tty prompt."""
    env_key = os.environ.get("KB_BACKUP_KEY")
    if env_key:
        return RawKeySource(env_key)

    env_pass_file = os.environ.get("KB_BACKUP_PASSPHRASE_FILE")
    if env_pass_file:
        p = Path(env_pass_file)
        if p.is_file():
            content = p.read_text(encoding="utf-8").strip()
            if content:
                return PassphraseKeySource(content)

    if sys.stdin.isatty():
        prompted = getpass.getpass("Enter backup passphrase: ").strip()
        if prompted:
            return PassphraseKeySource(prompted)

    return None


def _resolve_key_source(
    key_env: str | None,
    passphrase_file: str | None,
) -> KeySource:
    """Resolve KeySource from environment variable or passphrase file."""
    if key_env:
        val = os.environ.get(key_env)
        if not val:
            msg = f"Environment variable {key_env} is not set or empty"
            raise ValueError(msg)
        return RawKeySource(val)

    if passphrase_file:
        p = Path(passphrase_file)
        if not p.is_file():
            msg = f"Passphrase file does not exist: {passphrase_file}"
            raise ValueError(msg)
        content = p.read_text(encoding="utf-8").strip()
        if not content:
            msg = f"Passphrase file is empty: {passphrase_file}"
            raise ValueError(msg)
        return PassphraseKeySource(content)

    fallback = _resolve_fallback_key_source()
    if fallback is not None:
        return fallback

    msg = (
        "Key source required. Provide --key-env <VAR> or --passphrase-file <PATH> "
        "or set KB_BACKUP_KEY in environment."
    )
    raise ValueError(msg)


def _handle_backup_create(args: argparse.Namespace) -> int:
    """Handle backup create subcommand."""
    db_url = args.db_url or os.environ.get("DATABASE_URL") or os.environ.get("KB_DB_URL")
    if not db_url:
        sys.stderr.write(
            "Error: Database URL is required. Provide --db-url or set DATABASE_URL in env.\n"
        )
        return 2

    try:
        key_source = _resolve_key_source(args.key_env, args.passphrase_file)
    except ValueError as err:
        sys.stderr.write(f"Error: {err}\n")
        return 2

    out_path = Path(args.out)
    keyring_path = Path(args.keyring) if args.keyring else None
    attachments_dir = Path(args.attachments_dir) if args.attachments_dir else None

    try:
        summary = create_backup(
            db_url=db_url,
            out_path=out_path,
            key_source=key_source,
            include_secrets=args.include_secrets,
            keyring_path=keyring_path,
            attachments_dir=attachments_dir,
        )
        sys.stdout.write(
            f"Successfully created encrypted backup: {summary.archive_path} "
            f"({summary.size_bytes} bytes, duration {summary.duration_seconds:.2f}s)\n"
            f"Alembic revision: {summary.manifest.alembic_revision}\n"
        )
    except (BackupError, BackupCryptoError, ValueError) as err:
        sys.stderr.write(f"Backup creation failed: {err}\n")
        return 2
    except (OSError, RuntimeError) as err:
        sys.stderr.write(f"Unexpected backup error: {err}\n")
        return 1

    return 0


def _handle_backup_verify(args: argparse.Namespace) -> int:
    """Handle backup verify subcommand."""
    in_path = Path(args.in_file)
    if not in_path.is_file():
        sys.stderr.write(f"Error: Backup archive not found: {in_path}\n")
        return 2

    try:
        key_source = _resolve_key_source(args.key_env, args.passphrase_file)
        manifest = verify_backup(in_path, key_source)
        sys.stdout.write(
            f"Archive verification PASSED: {in_path}\n"
            f"Format version: {manifest.format_version}\n"
            f"Created at: {manifest.created_at}\n"
            f"Alembic revision: {manifest.alembic_revision}\n"
            f"Database SHA-256: {manifest.sha256_pgdump}\n"
            f"Includes keyring secrets: {manifest.includes_keyring_secrets}\n"
        )
    except (BackupIntegrityError, BackupCryptoError, ValueError) as err:
        sys.stderr.write(f"Archive verification FAILED: {err}\n")
        return 2

    return 0


def _validate_restore_args(
    args: argparse.Namespace,
) -> tuple[Path, str, KeySource, Path | None, Path | None] | int:
    """Validate restore arguments and return parsed inputs or error code."""
    in_path = Path(args.in_file)
    if not in_path.is_file():
        sys.stderr.write(f"Error: Backup archive not found: {in_path}\n")
        return 2

    target_db_url = args.target_db_url or os.environ.get("TARGET_DATABASE_URL")
    if not target_db_url:
        sys.stderr.write("Error: Target database URL is required via --target-db-url.\n")
        return 2

    try:
        key_source = _resolve_key_source(args.key_env, args.passphrase_file)
    except ValueError as err:
        sys.stderr.write(f"Error: {err}\n")
        return 2

    target_keyring = Path(args.target_keyring) if args.target_keyring else None
    restore_att_dir = (
        Path(args.restore_attachments_dir) if args.restore_attachments_dir else None
    )
    return in_path, target_db_url, key_source, target_keyring, restore_att_dir


def _handle_restore(args: argparse.Namespace) -> int:
    """Handle restore subcommand."""
    res = _validate_restore_args(args)
    if isinstance(res, int):
        return res

    in_path, target_db_url, key_source, target_keyring, restore_att_dir = res

    try:
        report = restore_backup(
            archive_path=in_path,
            target_db_url=target_db_url,
            key_source=key_source,
            confirm_overwrite=args.confirm_overwrite,
            target_keyring_path=target_keyring,
            restore_attachments_dir=restore_att_dir,
        )
        sys.stdout.write(
            f"Restore PASSED into {target_db_url}\n"
            f"Workspaces verified: {report.workspaces_verified}\n"
            f"Links audited: {report.links_audited}\n"
            f"Secrets restored: {report.secrets_restored}\n"
            f"Duration: {report.duration_seconds:.2f}s\n"
        )
    except (TargetDatabaseNotEmptyError, RestoreError, BackupIntegrityError) as err:
        sys.stderr.write(f"Restore verification failed: {err}\n")
        return 2
    except (OSError, RuntimeError) as err:
        sys.stderr.write(f"Unexpected restore failure: {err}\n")
        return 1

    return 0


def _handle_promote_compose(args: argparse.Namespace) -> int:
    """Handle promote export-compose subcommand."""
    out_dir = Path(args.out_dir)
    domain = args.domain or "localhost"
    keyring_path = Path(args.carry_over_keyring) if args.carry_over_keyring else None

    try:
        summary = export_production_bundle(
            out_dir=out_dir,
            keyring_path=keyring_path,
            domain=domain,
        )
        sys.stdout.write(
            f"Exported production bundle to {summary.out_dir}\n"
            f"Compose file: {summary.compose_path}\n"
            f"Caddyfile: {summary.caddyfile_path}\n"
            f"Environment file: {summary.env_path} (mode 0600)\n"
            f"Carried over keyring secrets: {summary.carried_over_secrets}\n"
        )
    except (OSError, RuntimeError, ValueError) as err:
        sys.stderr.write(f"Compose export failed: {err}\n")
        return 1

    return 0


def register_ops_subparsers(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    """Register backup, restore, and promote command trees under a parent parser."""
    backup_parser = subparsers.add_parser(
        "backup",
        help="Encrypted backup creation and verification commands",
    )
    backup_subs = backup_parser.add_subparsers(dest="backup_subcommand", required=True)

    create_p = backup_subs.add_parser("create", help="Create encrypted backup archive")
    create_p.add_argument("--out", required=True, help="Destination .kbbak archive path")
    create_p.add_argument("--db-url", help="Database connection URL")
    create_p.add_argument("--key-env", help="Environment variable containing 256-bit raw key")
    create_p.add_argument("--passphrase-file", help="Path to file containing passphrase")
    create_p.add_argument(
        "--include-secrets",
        action="store_true",
        help="Include MASTER_KEK and KB_AUTH_PEPPER carryover",
    )
    create_p.add_argument("--keyring", help="Path to source standalone keyring.json")
    create_p.add_argument("--attachments-dir", help="Directory of content-addressed attachments")
    create_p.set_defaults(func=_handle_backup_create)

    verify_p = backup_subs.add_parser("verify", help="Verify archive integrity and checksums")
    verify_p.add_argument("--in", dest="in_file", required=True, help="Input .kbbak archive path")
    verify_p.add_argument("--key-env", help="Environment variable containing 256-bit raw key")
    verify_p.add_argument("--passphrase-file", help="Path to file containing passphrase")
    verify_p.set_defaults(func=_handle_backup_verify)

    restore_p = subparsers.add_parser("restore", help="Restore database from encrypted backup")
    restore_p.add_argument("--in", dest="in_file", required=True, help="Input .kbbak archive path")
    restore_p.add_argument(
        "--target-db-url",
        required=True,
        help="Target PostgreSQL 16 connection URL",
    )
    restore_p.add_argument(
        "--confirm-overwrite",
        "--confirm-overwrite-empty-or-drop",
        dest="confirm_overwrite",
        action="store_true",
        help="Allow restoring over a non-empty target database",
    )
    restore_p.add_argument("--key-env", help="Environment variable containing 256-bit raw key")
    restore_p.add_argument("--passphrase-file", help="Path to file containing passphrase")
    restore_p.add_argument("--target-keyring", help="Path to write target keyring.json")
    restore_p.add_argument(
        "--restore-attachments-dir",
        help="Path to restore attachment files",
    )
    restore_p.set_defaults(func=_handle_restore)

    promote_p = subparsers.add_parser("promote", help="Standalone to production promotion helpers")
    promote_subs = promote_p.add_subparsers(dest="promote_subcommand", required=True)

    export_p = promote_subs.add_parser(
        "export-compose",
        help="Export hardened 5-network docker-compose.yml bundle",
    )
    export_p.add_argument(
        "--out-dir",
        required=True,
        help="Destination directory for compose bundle",
    )
    export_p.add_argument("--domain", required=True, help="Domain FQDN for Caddyfile")
    export_p.add_argument(
        "--carry-over-keyring",
        help="Path to standalone keyring.json to carry over MASTER_KEK and pepper",
    )
    export_p.set_defaults(func=_handle_promote_compose)


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entrypoint for standalone ops execution."""
    raw_argv = list(sys.argv[1:] if argv is None else argv)

    if check_forbidden_secret_args(raw_argv):
        sys.stderr.write(FORBIDDEN_ARGV_MSG + "\n")
        return 2

    parser = argparse.ArgumentParser(
        prog="kanban-ctl",
        description="Kanban platform operational management utility",
    )
    subparsers = parser.add_subparsers(dest="subcommand", required=True)
    register_ops_subparsers(subparsers)

    try:
        args = parser.parse_args(raw_argv)
    except SystemExit as err:
        return err.code if isinstance(err.code, int) else 2

    if hasattr(args, "func"):
        return int(args.func(args))

    parser.print_help(sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
