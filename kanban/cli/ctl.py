"""Root dispatcher for kanban-ctl operator command-line interface.

Exposes operations (backup, restore, promote) and future administrative commands
with centralized argument validation and strict secret hygiene.
"""

from __future__ import annotations

import argparse
import sys
from typing import TYPE_CHECKING

from kanban.cli.jobs import register_jobs_subparsers
from kanban.cli.ops import (
    FORBIDDEN_ARGV_MSG,
    check_forbidden_secret_args,
    register_ops_subparsers,
)

if TYPE_CHECKING:
    from collections.abc import Sequence


def main(argv: Sequence[str] | None = None) -> int:
    """Execute kanban-ctl root CLI."""
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
    register_jobs_subparsers(subparsers)

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
