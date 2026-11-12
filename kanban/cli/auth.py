# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""CLI commands for auth operations, including emergency break-glass unlock (KB-P2-09, S4.3)."""

from __future__ import annotations

import asyncio
import concurrent.futures
import os
import re
import sys
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

if TYPE_CHECKING:
    import argparse

_CONTROL_CHARS_RE = re.compile(r"[\x00-\x1F\x7F]")
_MAX_REASON_LENGTH = 256


def _get_admin_dsn() -> str:
    """Resolve administrative database connection DSN from environment."""
    dsn = (
        os.environ.get("KANBAN_ADMIN_DATABASE_URL")
        or os.environ.get("KANBAN_DATABASE_URL")
        or os.environ.get("DATABASE_URL")
    )
    if dsn:
        return dsn

    socket_dir = os.environ.get("KB_TEST_PGHOST", "/tmp/kb-pgsock-17")  # noqa: S108
    user = os.environ.get("KB_ADMIN_PGUSER", "kanban_migrator")
    dbname = os.environ.get("PGDATABASE", "kanban")
    return f"postgresql+asyncpg://{user}@/{dbname}?host={socket_dir}"


def register_auth_subparsers(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    """Register 'auth' subcommand and break-glass emergency-unlock utility."""
    auth_parser = subparsers.add_parser(
        "auth",
        help="Authentication and access control management",
        description="Administrative and break-glass auth utilities",
    )
    auth_subparsers = auth_parser.add_subparsers(dest="auth_subcommand", required=True)

    unlock_parser = auth_subparsers.add_parser(
        "emergency-unlock",
        help="Host-shell emergency break-glass to re-enable local administrator card (S4.3)",
        description=(
            "Atomically enables LOCAL_ADMIN and records an indelible activity ledger audit entry."
        ),
    )
    unlock_parser.add_argument(
        "--enable-local-admin",
        action="store_true",
        default=False,
        help="Mandatory explicit confirmation flag to activate break-glass unlock",
    )
    unlock_parser.add_argument(
        "--workspace",
        type=str,
        default=None,
        help="Workspace slug or UUID (defaults to primary workspace if only one exists)",
    )
    unlock_parser.add_argument(
        "--reason",
        type=str,
        default="Host shell emergency unlock",
        help=("Mandatory administrative justification (max 256 chars, stripped of control chars)"),
    )
    unlock_parser.set_defaults(func=handle_emergency_unlock)


def handle_emergency_unlock(args: argparse.Namespace) -> int:
    """Dispatch emergency break-glass procedure synchronously."""
    # 1. Require explicit --enable-local-admin flag
    if not getattr(args, "enable_local_admin", False):
        sys.stderr.write(
            "Error: --enable-local-admin flag is required to perform break-glass unlock.\n"
        )
        return 2

    # 2. Validate reason length (max 256 chars per S4.3)
    default_reason = "Host shell emergency unlock"
    raw_reason = getattr(args, "reason", default_reason) or default_reason
    if len(raw_reason) > _MAX_REASON_LENGTH:
        sys.stderr.write(
            f"Error: --reason exceeds {_MAX_REASON_LENGTH} characters "
            f"({len(raw_reason)} > {_MAX_REASON_LENGTH}).\n"
        )
        return 2

    clean_reason = _CONTROL_CHARS_RE.sub("", raw_reason).strip()
    if not clean_reason:
        sys.stderr.write("Error: --reason cannot be empty or contain only control characters.\n")
        return 2

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(
                lambda: asyncio.run(_run_emergency_unlock(args.workspace, clean_reason))
            ).result()

    return asyncio.run(_run_emergency_unlock(args.workspace, clean_reason))


async def _run_emergency_unlock(workspace_arg: str | None, reason: str) -> int:
    """Execute emergency unlock in privileged database context."""
    dsn = _get_admin_dsn()
    engine = create_async_engine(dsn)

    try:
        async with engine.begin() as conn:
            # Resolve workspace ID
            ws_id: uuid.UUID | None = None
            if workspace_arg:
                try:
                    ws_id = uuid.UUID(workspace_arg)
                except ValueError:
                    # Look up slug
                    row = (
                        await conn.execute(
                            text("SELECT id FROM workspaces WHERE slug = :slug"),
                            {"slug": workspace_arg},
                        )
                    ).first()
                    if not row:
                        sys.stderr.write(
                            f"Error: Workspace not found with slug '{workspace_arg}'.\n"
                        )
                        return 1
                    ws_id = row[0]
            else:
                rows = (
                    await conn.execute(
                        text("SELECT id FROM workspaces ORDER BY created_at ASC LIMIT 2")
                    )
                ).all()
                if not rows:
                    sys.stderr.write("Error: No workspaces exist in database.\n")
                    return 1
                if len(rows) > 1:
                    sys.stderr.write(
                        "Error: Multiple workspaces exist. "
                        "Specify target workspace with --workspace <slug_or_uuid>.\n"
                    )
                    return 2
                ws_id = rows[0][0]

            os_uid = os.getuid()
            try:
                tty = os.ttyname(sys.stdin.fileno())
            except (OSError, ValueError):
                tty = os.environ.get("TTY", "unknown")

            # Invoke privileged security definer function
            stmt = text(
                "SELECT workspace_id, card_id, activity_id "
                "FROM kb_auth.emergency_enable_local_admin(:ws_id, :uid, :tty, :reason)"
            )
            result = (
                (
                    await conn.execute(
                        stmt,
                        {
                            "ws_id": ws_id,
                            "uid": os_uid,
                            "tty": tty,
                            "reason": reason,
                        },
                    )
                )
                .mappings()
                .first()
            )

            if not result:
                sys.stderr.write("Error: Emergency unlock failed to execute.\n")
                return 1

            # Print single-line structured confirmation to stdout
            sys.stdout.write(
                f"EMERGENCY_UNLOCK_SUCCESS workspace={result['workspace_id']} "
                f"card={result['card_id']} activity={result['activity_id']} "
                f"reason={reason!r}\n"
            )
            return 0

    except Exception as exc:  # noqa: BLE001
        msg = str(exc)
        if "42501" in msg or "insufficient_privilege" in msg:
            sys.stderr.write(
                f"Permission Denied: kanban_app cannot execute emergency unlock "
                f"(S4.3 privilege wall): {exc}\n"
            )
        else:
            sys.stderr.write(f"Error executing emergency unlock: {exc}\n")
        return 1
    finally:
        await engine.dispose()
