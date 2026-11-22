# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
# ruff: noqa: T201
"""Command-line entry points for kanban-cli, kanban-cli-agent, docs, and admin (KAN-48)."""

from __future__ import annotations

import asyncio
import sys
from typing import TYPE_CHECKING

from mcp.cli.schema_cli import parse_and_execute_cli
from mcp.registry import Surface

if TYPE_CHECKING:
    from mcp.internal_client import KanbanApiClient

__all__ = [
    "main",
    "main_admin",
    "main_agent",
    "main_docs",
]


def _run_cli_coroutine(
    argv: list[str] | None,
    surface: Surface | None = None,
    client: KanbanApiClient | None = None,
) -> int:
    """Execute asynchronous CLI action synchronously inside event loop."""
    args = sys.argv[1:] if argv is None else list(argv)
    try:
        return asyncio.run(
            parse_and_execute_cli(
                args,
                surface_override=surface,
                client=client,
            )
        )
    except KeyboardInterrupt:
        print("\nOperation cancelled by user.", file=sys.stderr)
        return 130


def main(
    argv: list[str] | None = None,
    *,
    client: KanbanApiClient | None = None,
) -> int:
    """Entry point for unified kanban-cli."""
    return _run_cli_coroutine(argv, surface=None, client=client)


def main_agent(
    argv: list[str] | None = None,
    *,
    client: KanbanApiClient | None = None,
) -> int:
    """Entry point for kanban-cli-agent."""
    return _run_cli_coroutine(argv, surface=Surface.AGENT, client=client)


def main_docs(
    argv: list[str] | None = None,
    *,
    client: KanbanApiClient | None = None,
) -> int:
    """Entry point for kanban-cli-docs."""
    return _run_cli_coroutine(argv, surface=Surface.DOCS, client=client)


def main_admin(
    argv: list[str] | None = None,
    *,
    client: KanbanApiClient | None = None,
) -> int:
    """Entry point for kanban-cli-admin."""
    return _run_cli_coroutine(argv, surface=Surface.ADMIN, client=client)


if __name__ == "__main__":
    sys.exit(main())
