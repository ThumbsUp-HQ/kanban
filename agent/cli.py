# Copyright 2026 Kanban Platform Contributors
"""Agent CLI entry point, subcommand registry, and manual validation workbench."""

from __future__ import annotations

import argparse
import asyncio
import sys
from dataclasses import dataclass
from typing import TYPE_CHECKING, NoReturn

from agent.cli_commands.validate_echo import (
    configure_validate_echo_parser,
    handle_validate_echo,
)
from agent.cli_report import (
    ContextScrubber,
    ExitCode,
    ValidationReport,
    render_report,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Mapping, Sequence

__all__ = [
    "SubcommandSpec",
    "add_common_agent_flags",
    "get_registered_subcommands",
    "main",
    "register_subcommand",
]


@dataclass(frozen=True)
class SubcommandSpec:
    """Specification defining a registered agent CLI subcommand."""

    name: str
    help: str
    configure_parser: Callable[[argparse.ArgumentParser], None]
    handler: Callable[[argparse.Namespace], Awaitable[tuple[ValidationReport, ExitCode]]]


_REGISTRY: dict[str, SubcommandSpec] = {}


def register_subcommand(spec: SubcommandSpec) -> None:
    """Register a new subcommand specification in the agent CLI registry."""
    if spec.name in _REGISTRY:
        msg = f"Subcommand '{spec.name}' is already registered"
        raise ValueError(msg)
    _REGISTRY[spec.name] = spec


def get_registered_subcommands() -> Mapping[str, SubcommandSpec]:
    """Return an immutable view of registered CLI subcommands."""
    return dict(_REGISTRY)


def add_common_agent_flags(
    parser: argparse.ArgumentParser,
    *,
    available_providers: Sequence[str] = ("fixture", "ollama", "gemini", "openai"),
) -> None:
    """Add standard provider, model, cassette, and reporting flags to a parser."""
    parser.add_argument(
        "--provider",
        choices=available_providers,
        default="fixture",
        help="LLM provider or execution runtime harness.",
    )
    parser.add_argument(
        "--model",
        type=str,
        default="fixture-echo-v1",
        help="Target model identifier.",
    )
    parser.add_argument(
        "--cassette",
        type=str,
        default=None,
        help="Path to YAML fixture cassette for offline replay.",
    )
    parser.add_argument(
        "--http-cassette",
        type=str,
        default=None,
        help="Path to YAML HTTP cassette for offline HTTP provider replay.",
    )
    parser.add_argument(
        "--base-url",
        type=str,
        default=None,
        help="Base URL for remote or local LLM daemon (e.g. http://127.0.0.1:11434).",
    )
    parser.add_argument(
        "--verbose-tools",
        action="store_true",
        help="Print verbose JSON arguments and results for all executed tool steps.",
    )
    parser.add_argument(
        "--report",
        choices=("text", "json"),
        default="text",
        help="Output report serialization format.",
    )


class _CustomArgumentParser(argparse.ArgumentParser):
    """Custom ArgumentParser exiting with code 2 on flag or validation errors."""

    def error(self, message: str) -> NoReturn:
        sys.stderr.write(f"error: {message}\n")
        sys.exit(ExitCode.SCHEMA_OR_POLICY_VIOLATION.value)


async def _async_main(
    argv: Sequence[str] | None = None,
    *,
    scrubber: ContextScrubber | None = None,
) -> int:
    parser = _CustomArgumentParser(
        prog="kanban-agent",
        description="Kanban AI agent manual CLI validation workbench",
    )
    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    for name, spec in _REGISTRY.items():
        sub = subparsers.add_parser(name, help=spec.help)
        spec.configure_parser(sub)

    args = parser.parse_args(argv)
    spec = _REGISTRY[args.subcommand]

    try:
        if scrubber is not None:
            try:
                report, exit_code = await spec.handler(args, scrubber=scrubber)  # type: ignore[call-arg]
            except TypeError:
                report, exit_code = await spec.handler(args)
        else:
            report, exit_code = await spec.handler(args)
    except Exception as err:  # noqa: BLE001  # Top-level CLI boundary catches all errors
        sys.stderr.write(f"error: {err}\n")
        return ExitCode.RUNTIME_ERROR.value

    output = render_report(
        report,
        getattr(args, "report", "text"),
        verbose_tools=getattr(args, "verbose_tools", False),
    )
    sys.stdout.write(output + "\n")
    return exit_code.value


def main(
    argv: Sequence[str] | None = None,
    *,
    scrubber: ContextScrubber | None = None,
) -> int:
    """Run kanban-agent CLI entry point synchronously."""
    return asyncio.run(_async_main(argv, scrubber=scrubber))


# Register built-in validate-echo demo subcommand
register_subcommand(
    SubcommandSpec(
        name="validate-echo",
        help="Validate echo stream and structured output against FixtureLLMProvider",
        configure_parser=configure_validate_echo_parser,
        handler=handle_validate_echo,
    )
)

if __name__ == "__main__":
    raise SystemExit(main())
