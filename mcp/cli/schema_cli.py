# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
# ruff: noqa: T201, C901, PLR0911, PLR0912, PLR0913, PLR0915, PLR2004, E501, BLE001, PTH123, PTH110, PTH111, PLC0415, TC001, ANN401, SLF001, PERF401, PIE810, RUF005
"""Schema-driven subcommand generator and 1:1 MCP tool parity engine for kanban-cli (KAN-48)."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from typing import Any, Final

import yaml

from mcp.cli.auth import ResolvedConfig
from mcp.context import (
    McpRequestContext,
    reset_current_mcp_context,
    set_current_mcp_context,
)
from mcp.errors import KbMcpError, McpErrorCode
from mcp.help import build_help
from mcp.internal_client import KanbanApiClient
from mcp.protocol import validate_tool_arguments_schema
from mcp.registry import Surface, ToolRegistry, ToolSpec
from mcp.surfaces.admin import build_admin_registry
from mcp.surfaces.agent import create_agent_registry
from mcp.surfaces.docs import build_docs_registry
from mcp.yaml_out import dump_yaml

__all__ = [
    "build_admin_cli_parser",
    "build_agent_cli_parser",
    "build_docs_cli_parser",
    "build_unified_cli_parser",
    "execute_tool_action",
    "generate_completions",
    "parse_and_execute_cli",
]

_SURROGATE_MIN: Final[int] = 0xD800
_SURROGATE_MAX: Final[int] = 0xDFFF

_PROSE_FIELD_NAMES: Final[frozenset[str]] = frozenset(
    {
        "description_markdown",
        "comment_markdown",
        "body_markdown",
        "content",
        "script_source",
        "summary_markdown",
    }
)

_STRUCTURED_FIELD_NAMES: Final[frozenset[str]] = frozenset(
    {
        "verification_proof",
        "children",
        "blueprint",
        "settings",
        "params",
        "custom_fields",
    }
)


def assert_no_surrogates(text: str) -> None:
    """Reject UTF-16 lone surrogates fail-closed."""
    for c in text:
        cp = ord(c)
        if _SURROGATE_MIN <= cp <= _SURROGATE_MAX:
            raise KbMcpError(McpErrorCode.VALIDATION_FAILED, "INVALID_UTF8_SURROGATE")


def _read_file_or_stdin(file_path: str) -> str:
    """Read content from a path or stdin with UTF-16 surrogate validation."""
    if file_path == "-":
        content = sys.stdin.read()
    else:
        path = os.path.expanduser(file_path)
        if not os.path.exists(path):
            raise KbMcpError(
                McpErrorCode.VALIDATION_FAILED,
                f"File not found: {file_path}",
                field="file",
            )
        with open(path, encoding="utf-8") as f:
            content = f.read()
    assert_no_surrogates(content)
    return content


def _parse_structured_value(raw: str) -> Any:
    """Parse object/array argument from JSON/YAML string, @path, or @-."""
    assert_no_surrogates(raw)
    if raw.startswith("@"):
        path_spec = raw[1:]
        text_content = _read_file_or_stdin(path_spec)
        try:
            return json.loads(text_content)
        except Exception:
            try:
                return yaml.safe_load(text_content)
            except Exception as exc:
                raise KbMcpError(
                    McpErrorCode.VALIDATION_FAILED,
                    f"Failed to parse structured input from {raw}: {exc}",
                ) from exc

    # Direct literal string
    try:
        return json.loads(raw)
    except Exception:
        try:
            return yaml.safe_load(raw)
        except Exception:
            return raw


def _to_kebab(name: str) -> str:
    """Convert snake_case or camelCase name to kebab-case."""
    s1 = re.sub(r"(.)([A-Z][a-z]+)", r"\1-\2", name)
    s2 = re.sub(r"([a-z0-9])([A-Z])", r"\1-\2", s1)
    return s2.replace("_", "-").lower()


def _to_snake(name: str) -> str:
    """Convert kebab-case or camelCase name to snake_case."""
    return name.replace("-", "_").lower()


def _add_tool_arguments_to_parser(parser: argparse.ArgumentParser, spec: ToolSpec) -> None:
    """Map ToolSpec JSON Schema properties deterministically to argparse flags."""
    schema = spec.input_schema or {}
    properties: dict[str, Any] = schema.get("properties") or {}

    for prop_name, prop_schema in properties.items():
        if not isinstance(prop_schema, dict):
            continue
        kebab_name = _to_kebab(prop_name)
        snake_name = _to_snake(prop_name)
        prop_type = prop_schema.get("type")
        help_desc = prop_schema.get("description", "")

        # 1. Boolean flags
        if prop_type == "boolean":
            parser.add_argument(
                f"--{kebab_name}",
                dest=snake_name,
                action=argparse.BooleanOptionalAction,
                default=None,
                help=help_desc,
            )
            if kebab_name != snake_name:
                parser.add_argument(
                    f"--{snake_name}",
                    dest=snake_name,
                    action=argparse.BooleanOptionalAction,
                    default=None,
                    help=argparse.SUPPRESS,
                )
            continue

        # 2. Integer or Number flags
        if prop_type in ("integer", "number"):
            num_type = int if prop_type == "integer" else float
            parser.add_argument(
                f"--{kebab_name}",
                dest=snake_name,
                type=num_type,
                default=None,
                help=help_desc,
            )
            if kebab_name != snake_name:
                parser.add_argument(
                    f"--{snake_name}",
                    dest=snake_name,
                    type=num_type,
                    default=None,
                    help=argparse.SUPPRESS,
                )
            continue

        # 3. Array flags (repeatable action="append")
        if prop_type == "array":
            parser.add_argument(
                f"--{kebab_name}",
                dest=snake_name,
                action="append",
                default=None,
                help=f"{help_desc} (repeatable or comma-separated/JSON list)",
            )
            if kebab_name != snake_name:
                parser.add_argument(
                    f"--{snake_name}",
                    dest=snake_name,
                    action="append",
                    default=None,
                    help=argparse.SUPPRESS,
                )
            parser.add_argument(
                f"--{kebab_name}-file",
                dest=f"{snake_name}_file",
                default=None,
                help=f"File containing JSON/YAML list for {prop_name}",
            )
            continue

        # 4. Structured Object flags
        if prop_type == "object" or prop_name in _STRUCTURED_FIELD_NAMES:
            parser.add_argument(
                f"--{kebab_name}",
                dest=snake_name,
                default=None,
                help=f"{help_desc} (JSON/YAML string or @path.json)",
            )
            if kebab_name != snake_name:
                parser.add_argument(
                    f"--{snake_name}",
                    dest=snake_name,
                    default=None,
                    help=argparse.SUPPRESS,
                )
            parser.add_argument(
                f"--{kebab_name}-file",
                dest=f"{snake_name}_file",
                default=None,
                help=f"File containing JSON/YAML object for {prop_name}",
            )
            continue

        # 5. String and Prose fields
        parser.add_argument(
            f"--{kebab_name}",
            dest=snake_name,
            default=None,
            help=help_desc,
        )
        if kebab_name != snake_name:
            parser.add_argument(
                f"--{snake_name}",
                dest=snake_name,
                default=None,
                help=argparse.SUPPRESS,
            )

        # Sibling file flags for prose / markdown fields
        if prop_name in _PROSE_FIELD_NAMES:
            parser.add_argument(
                f"--{kebab_name}-file",
                dest=f"{snake_name}_file",
                default=None,
                help=f"Path to file containing {prop_name} (or - for stdin)",
            )
            if prop_name == "description_markdown":
                parser.add_argument(
                    "--description-file",
                    dest="description_markdown_file",
                    default=None,
                    help="Alias for --description-markdown-file",
                )
            elif prop_name == "comment_markdown":
                parser.add_argument(
                    "--comment-file",
                    dest="comment_markdown_file",
                    default=None,
                    help="Alias for --comment-markdown-file",
                )
            elif prop_name == "body_markdown":
                parser.add_argument(
                    "--body-file",
                    dest="body_markdown_file",
                    default=None,
                    help="Alias for --body-markdown-file",
                )

        # Clear flag for nullable fields
        parser.add_argument(
            f"--clear-{kebab_name}",
            dest=f"clear_{snake_name}",
            action="store_true",
            default=False,
            help=f"Explicitly set {prop_name} to null",
        )

    # Attach global options to tool subparser so they are valid after subcommands
    _add_global_flags(parser, is_subparser=True)


def _add_global_flags(parser: argparse.ArgumentParser, *, is_subparser: bool = False) -> None:
    """Register global CLI options (url, workspace, project, token, lod, filter, json, jsonl, no-color)."""
    existing_flags = {opt for action in parser._actions for opt in action.option_strings}
    suppress = argparse.SUPPRESS if is_subparser else None
    bool_suppress = argparse.SUPPRESS if is_subparser else False

    if "--url" not in existing_flags:
        parser.add_argument(
            "--url",
            default=suppress,
            help="Kanban API server base URL" if not is_subparser else argparse.SUPPRESS,
        )
    if "--workspace" not in existing_flags:
        parser.add_argument(
            "--workspace",
            default=suppress,
            help="Workspace slug" if not is_subparser else argparse.SUPPRESS,
        )
    if "--project" not in existing_flags:
        parser.add_argument(
            "--project",
            default=suppress,
            help="Project key" if not is_subparser else argparse.SUPPRESS,
        )
    if "--token" not in existing_flags and "--api-key" not in existing_flags:
        parser.add_argument(
            "--token",
            "--api-key",
            dest="token",
            default=suppress,
            help="Authentication token" if not is_subparser else argparse.SUPPRESS,
        )
    if "--lod" not in existing_flags:
        parser.add_argument(
            "--lod",
            default=suppress,
            help="Level of detail: summary | standard | full"
            if not is_subparser
            else argparse.SUPPRESS,
        )
    if "--filter" not in existing_flags:
        parser.add_argument(
            "--filter",
            default=suppress,
            help="Predicate DSL search filter" if not is_subparser else argparse.SUPPRESS,
        )
    if "--json" not in existing_flags:
        parser.add_argument(
            "--json",
            action="store_true",
            default=bool_suppress,
            help="Output response formatted as JSON" if not is_subparser else argparse.SUPPRESS,
        )
    if "--jsonl" not in existing_flags:
        parser.add_argument(
            "--jsonl",
            action="store_true",
            default=bool_suppress,
            help="Stream response items as JSON Lines" if not is_subparser else argparse.SUPPRESS,
        )
    if "--no-color" not in existing_flags:
        parser.add_argument(
            "--no-color",
            action="store_true",
            default=bool_suppress,
            help="Disable ANSI color codes" if not is_subparser else argparse.SUPPRESS,
        )


def _apply_predicate_filter(arguments: dict[str, Any], filter_str: str) -> None:
    """Parse --filter predicate DSL string and populate search-tickets arguments."""
    import importlib

    pred_mod = importlib.import_module("kanban.services.predicate_compiler")
    parse_comparison_clause = pred_mod.parse_comparison_clause
    split_query_clauses = pred_mod.split_query_clauses
    tokenize_predicate_string = pred_mod.tokenize_predicate_string

    assert_no_surrogates(filter_str)
    clauses = split_query_clauses(filter_str)

    states: list[str] = list(arguments.get("states") or [])
    assignees: list[str] = list(arguments.get("assignees") or [])
    modules: list[str] = list(arguments.get("modules") or [])
    labels: list[str] = list(arguments.get("labels") or [])
    free_text_parts: list[str] = []

    for clause in clauses:
        comp = parse_comparison_clause(clause)
        if comp:
            fld = comp.field.lower()
            val = comp.value
            if fld in ("state", "status") and val:
                states.append(val)
            elif fld in ("assignee", "assignees") and val:
                assignees.append(val)
            elif fld == "cycle" and val:
                arguments["cycle"] = val
            elif fld in ("module", "modules") and val:
                modules.append(val)
            elif fld in ("label", "labels") and val:
                labels.append(val)
            elif fld == "blocked" and val:
                arguments["blocked"] = val.lower() in ("true", "1", "yes")
            elif fld in ("gate_status", "gate") and val:
                arguments["gate_status"] = val.lower()
            elif fld == "priority" and val:
                arguments["_filter_priority"] = val.lower()
            else:
                free_text_parts.append(val)
            continue

        tokens = tokenize_predicate_string(clause)
        for tok in tokens:
            if tok.field:
                fld = tok.field.lower()
                val = tok.value
                if fld in ("state", "status") and val:
                    states.append(val)
                elif fld in ("assignee", "assignees") and val:
                    assignees.append(val)
                elif fld == "cycle" and val:
                    arguments["cycle"] = val
                elif fld in ("module", "modules") and val:
                    modules.append(val)
                elif fld in ("label", "labels") and val:
                    labels.append(val)
                elif fld == "blocked" and val:
                    arguments["blocked"] = val.lower() in ("true", "1", "yes")
                elif fld in ("gate_status", "gate") and val:
                    arguments["gate_status"] = val.lower()
                elif fld == "priority" and val:
                    arguments["_filter_priority"] = val.lower()
            elif tok.value:
                free_text_parts.append(tok.value)

    if states:
        arguments["states"] = states
    if assignees:
        arguments["assignees"] = assignees
    if modules:
        arguments["modules"] = modules
    if labels:
        arguments["labels"] = labels
    if free_text_parts:
        existing_query = arguments.get("query") or ""
        combined = f"{existing_query} {' '.join(free_text_parts)}".strip()
        arguments["query"] = combined


def _normalize_parsed_arguments(
    spec: ToolSpec,
    parsed_args: dict[str, Any],
    cli_filter: str | None = None,
) -> dict[str, Any]:
    """Normalize CLI namespace into valid MCP tool argument dictionary."""
    arguments: dict[str, Any] = {}
    schema = spec.input_schema or {}
    properties: dict[str, Any] = schema.get("properties") or {}

    for prop_name, prop_schema in properties.items():
        snake_name = _to_snake(prop_name)
        prop_type = prop_schema.get("type") if isinstance(prop_schema, dict) else None

        # Check clear flag
        if parsed_args.get(f"clear_{snake_name}"):
            arguments[prop_name] = None
            continue

        # Check sibling file flag
        file_val = parsed_args.get(f"{snake_name}_file")
        if file_val is not None:
            content = _read_file_or_stdin(file_val)
            if prop_type in ("object", "array") or prop_name in _STRUCTURED_FIELD_NAMES:
                try:
                    arguments[prop_name] = json.loads(content)
                except Exception:
                    arguments[prop_name] = yaml.safe_load(content)
            else:
                arguments[prop_name] = content
            continue

        # Check regular value
        val = parsed_args.get(snake_name)
        if val is None:
            continue

        # Handle null string literal
        if isinstance(val, str) and val.strip().lower() == "null":
            arguments[prop_name] = None
            continue

        # Handle array parsing
        if prop_type == "array":
            items: list[Any] = []
            if isinstance(val, list):
                for item in val:
                    if isinstance(item, str) and (item.startswith("[") or item.startswith("@")):
                        parsed_item = _parse_structured_value(item)
                        if isinstance(parsed_item, list):
                            items.extend(parsed_item)
                        else:
                            items.append(parsed_item)
                    elif isinstance(item, str) and "," in item:
                        items.extend(x.strip() for x in item.split(",") if x.strip())
                    else:
                        items.append(item)
            elif isinstance(val, str):
                parsed_val = _parse_structured_value(val)
                if isinstance(parsed_val, list):
                    items.extend(parsed_val)
                else:
                    items.append(parsed_val)
            for itm in items:
                if isinstance(itm, str):
                    assert_no_surrogates(itm)
            arguments[prop_name] = items
            continue

        # Handle structured object parsing
        if prop_type == "object" or prop_name in _STRUCTURED_FIELD_NAMES:
            if isinstance(val, str):
                arguments[prop_name] = _parse_structured_value(val)
            else:
                arguments[prop_name] = val
            continue

        # Handle string validation and stdin
        if isinstance(val, str):
            if val == "-" and prop_name in _PROSE_FIELD_NAMES:
                val = _read_file_or_stdin("-")
            elif val.startswith("@"):
                val = _read_file_or_stdin(val[1:])
            else:
                assert_no_surrogates(val)
            arguments[prop_name] = val
            continue

        arguments[prop_name] = val

    # Apply --filter if provided
    if cli_filter and spec.name == "search_tickets":
        _apply_predicate_filter(arguments, cli_filter)

    return arguments


def _build_registry_subparsers(
    subparsers: Any,
    registry: ToolRegistry,
    prefix: str = "",
) -> dict[str, ToolSpec]:
    """Register all tools from a ToolRegistry as subcommands on an argparse subparser."""
    tool_map: dict[str, ToolSpec] = {}
    for spec in registry.list_specs():
        kebab_cmd = _to_kebab(spec.name)
        snake_cmd = _to_snake(spec.name)

        p = subparsers.add_parser(
            f"{prefix}{kebab_cmd}",
            help=spec.description,
            add_help=True,
        )
        _add_tool_arguments_to_parser(p, spec)
        tool_map[f"{prefix}{kebab_cmd}"] = spec

        if kebab_cmd != snake_cmd:
            p_snake = subparsers.add_parser(
                f"{prefix}{snake_cmd}",
                help=argparse.SUPPRESS,
                add_help=True,
            )
            _add_tool_arguments_to_parser(p_snake, spec)
            tool_map[f"{prefix}{snake_cmd}"] = spec

    return tool_map


def build_unified_cli_parser() -> tuple[
    argparse.ArgumentParser, dict[str, tuple[Surface, ToolSpec]]
]:
    """Build unified kanban-cli parser covering agent, docs, and admin surfaces."""
    parser = argparse.ArgumentParser(
        prog="kanban-cli",
        description="Kanban CLI with 1:1 MCP Tool Parity, Auth, and Deterministic Unix Output",
    )
    # Global options
    parser.add_argument("--url", default=None, help="Kanban API server base URL")
    parser.add_argument("--workspace", default=None, help="Workspace slug")
    parser.add_argument("--project", default=None, help="Project key")
    parser.add_argument(
        "--token", "--api-key", dest="token", default=None, help="Authentication token"
    )
    parser.add_argument("--lod", default=None, help="Level of detail: summary | standard | full")
    parser.add_argument("--filter", default=None, help="Predicate DSL search filter")
    parser.add_argument(
        "--json", action="store_true", default=False, help="Output response formatted as JSON"
    )
    parser.add_argument(
        "--jsonl", action="store_true", default=False, help="Stream response items as JSON Lines"
    )
    parser.add_argument(
        "--no-color", action="store_true", default=False, help="Disable ANSI color codes"
    )

    subparsers = parser.add_subparsers(dest="subcommand", title="Commands")
    tool_dispatch: dict[str, tuple[Surface, ToolSpec]] = {}

    # 1. Agent surface commands at top level
    agent_reg = create_agent_registry()
    for spec in agent_reg.list_specs():
        kebab_cmd = _to_kebab(spec.name)
        snake_cmd = _to_snake(spec.name)

        p_agent = subparsers.add_parser(kebab_cmd, help=spec.description)
        _add_tool_arguments_to_parser(p_agent, spec)
        tool_dispatch[kebab_cmd] = (Surface.AGENT, spec)

        if kebab_cmd != snake_cmd:
            p_snake = subparsers.add_parser(snake_cmd, help=argparse.SUPPRESS)
            _add_tool_arguments_to_parser(p_snake, spec)
            tool_dispatch[snake_cmd] = (Surface.AGENT, spec)

    # Alias: issue list -> search-tickets
    search_spec = agent_reg.get("search_tickets")
    if search_spec is not None:
        p_issue_list = subparsers.add_parser("issue list", help="Alias for search-tickets")
        _add_tool_arguments_to_parser(p_issue_list, search_spec)
        tool_dispatch["issue list"] = (Surface.AGENT, search_spec)

    # 2. Docs surface commands
    docs_reg = build_docs_registry()
    docs_parser = subparsers.add_parser("docs", help="Documentation and knowledge management tools")
    docs_subparsers = docs_parser.add_subparsers(dest="docs_command", title="Docs Commands")
    for spec in docs_reg.list_specs():
        k_cmd = _to_kebab(spec.name)
        s_cmd = _to_snake(spec.name)
        p_d = docs_subparsers.add_parser(k_cmd, help=spec.description)
        _add_tool_arguments_to_parser(p_d, spec)
        tool_dispatch[f"docs {k_cmd}"] = (Surface.DOCS, spec)
        if k_cmd != s_cmd:
            p_ds = docs_subparsers.add_parser(s_cmd, help=argparse.SUPPRESS)
            _add_tool_arguments_to_parser(p_ds, spec)
            tool_dispatch[f"docs {s_cmd}"] = (Surface.DOCS, spec)

    # 3. Admin surface commands
    admin_reg = build_admin_registry()
    admin_parser = subparsers.add_parser("admin", help="Administrative and configuration tools")
    admin_subparsers = admin_parser.add_subparsers(dest="admin_command", title="Admin Commands")
    for spec in admin_reg.list_specs():
        k_cmd = _to_kebab(spec.name)
        s_cmd = _to_snake(spec.name)
        p_a = admin_subparsers.add_parser(k_cmd, help=spec.description)
        _add_tool_arguments_to_parser(p_a, spec)
        tool_dispatch[f"admin {k_cmd}"] = (Surface.ADMIN, spec)
        if k_cmd != s_cmd:
            p_as = admin_subparsers.add_parser(s_cmd, help=argparse.SUPPRESS)
            _add_tool_arguments_to_parser(p_as, spec)
            tool_dispatch[f"admin {s_cmd}"] = (Surface.ADMIN, spec)

    # 4. Auth commands
    auth_parser = subparsers.add_parser("auth", help="Authentication and session management")
    auth_subparsers = auth_parser.add_subparsers(dest="auth_command", title="Auth Commands")

    login_p = auth_subparsers.add_parser("login", help="Log in to Kanban instance")
    login_p.add_argument(
        "--device", action="store_true", default=False, help="Use RFC 8628 headless device login"
    )
    login_p.add_argument(
        "--token", "--api-key", dest="token", default=None, help="Save API key or token directly"
    )

    auth_subparsers.add_parser("status", help="Show current authentication and connectivity status")
    auth_subparsers.add_parser("logout", help="Log out and remove stored credentials")

    # 5. Completions command
    comp_p = subparsers.add_parser("completions", help="Generate shell completions")
    comp_p.add_argument("shell", choices=["bash", "zsh", "fish"], help="Target shell")

    return parser, tool_dispatch


def build_agent_cli_parser() -> tuple[argparse.ArgumentParser, dict[str, tuple[Surface, ToolSpec]]]:
    """Build standalone kanban-cli-agent parser."""
    parser = argparse.ArgumentParser(
        prog="kanban-cli-agent",
        description="Kanban MCP Agent Surface CLI",
    )
    _add_global_flags(parser, is_subparser=False)
    subparsers = parser.add_subparsers(dest="subcommand")
    agent_reg = create_agent_registry()
    dispatch = _build_registry_subparsers(subparsers, agent_reg)
    return parser, {k: (Surface.AGENT, v) for k, v in dispatch.items()}


def build_docs_cli_parser() -> tuple[argparse.ArgumentParser, dict[str, tuple[Surface, ToolSpec]]]:
    """Build standalone kanban-cli-docs parser."""
    parser = argparse.ArgumentParser(
        prog="kanban-cli-docs",
        description="Kanban MCP Docs Surface CLI",
    )
    _add_global_flags(parser, is_subparser=False)
    subparsers = parser.add_subparsers(dest="subcommand")
    docs_reg = build_docs_registry()
    dispatch = _build_registry_subparsers(subparsers, docs_reg)
    return parser, {k: (Surface.DOCS, v) for k, v in dispatch.items()}


def build_admin_cli_parser() -> tuple[argparse.ArgumentParser, dict[str, tuple[Surface, ToolSpec]]]:
    """Build standalone kanban-cli-admin parser."""
    parser = argparse.ArgumentParser(
        prog="kanban-cli-admin",
        description="Kanban MCP Admin Surface CLI",
    )
    _add_global_flags(parser, is_subparser=False)
    subparsers = parser.add_subparsers(dest="subcommand")
    admin_reg = build_admin_registry()
    dispatch = _build_registry_subparsers(subparsers, admin_reg)
    return parser, {k: (Surface.ADMIN, v) for k, v in dispatch.items()}


def generate_completions(shell: str) -> str:
    """Generate shell autocompletions for kanban-cli with zero shell=True calls."""
    agent_reg = create_agent_registry()
    docs_reg = build_docs_registry()
    admin_reg = build_admin_registry()

    top_cmds: list[str] = [_to_kebab(s.name) for s in agent_reg.list_specs()] + [
        "docs",
        "admin",
        "auth",
        "completions",
    ]
    docs_cmds: list[str] = [_to_kebab(s.name) for s in docs_reg.list_specs()]
    admin_cmds: list[str] = [_to_kebab(s.name) for s in admin_reg.list_specs()]
    auth_cmds: list[str] = ["login", "status", "logout"]

    if shell == "bash":
        return f"""# bash completion for kanban-cli
_kanban_cli_completions() {{
    local cur prev words cword
    _init_completion || return

    local top_commands="{" ".join(top_cmds)}"
    local docs_commands="{" ".join(docs_cmds)}"
    local admin_commands="{" ".join(admin_cmds)}"
    local auth_commands="{" ".join(auth_cmds)}"

    if [[ $cword -eq 1 ]]; then
        COMPREPLY=( $(compgen -W "$top_commands --url --workspace --project --token --json --jsonl --help" -- "$cur") )
        return 0
    fi

    case "${{words[1]}}" in
        docs)
            COMPREPLY=( $(compgen -W "$docs_commands" -- "$cur") )
            return 0
            ;;
        admin)
            COMPREPLY=( $(compgen -W "$admin_commands" -- "$cur") )
            return 0
            ;;
        auth)
            COMPREPLY=( $(compgen -W "$auth_commands" -- "$cur") )
            return 0
            ;;
        completions)
            COMPREPLY=( $(compgen -W "bash zsh fish" -- "$cur") )
            return 0
            ;;
    esac
}}
complete -F _kanban_cli_completions kanban-cli
"""

    if shell == "zsh":
        return f"""#compdef kanban-cli
_kanban_cli() {{
    local -a top_commands docs_commands admin_commands auth_commands
    top_commands=({" ".join(f'"{c}"' for c in top_cmds)})
    docs_commands=({" ".join(f'"{c}"' for c in docs_cmds)})
    admin_commands=({" ".join(f'"{c}"' for c in admin_cmds)})
    auth_commands=({" ".join(f'"{c}"' for c in auth_cmds)})

    _arguments -C \\
        '1: :->command' \\
        '*:: :->args'

    case $state in
        command)
            _describe -t commands 'kanban-cli commands' top_commands
            ;;
        args)
            case $words[1] in
                docs)
                    _describe -t docs-commands 'docs commands' docs_commands
                    ;;
                admin)
                    _describe -t admin-commands 'admin commands' admin_commands
                    ;;
                auth)
                    _describe -t auth-commands 'auth commands' auth_commands
                    ;;
                completions)
                    _values 'shells' bash zsh fish
                    ;;
            esac
            ;;
    esac
}}
_kanban_cli "$@"
"""

    if shell == "fish":
        lines = [
            "# fish completion for kanban-cli",
            "complete -c kanban-cli -f",
        ]
        for c in top_cmds:
            lines.append(f"complete -c kanban-cli -n '__fish_use_subcommand' -a '{c}'")
        for c in docs_cmds:
            lines.append(f"complete -c kanban-cli -n '__fish_seen_subcommand_from docs' -a '{c}'")
        for c in admin_cmds:
            lines.append(f"complete -c kanban-cli -n '__fish_seen_subcommand_from admin' -a '{c}'")
        for c in auth_cmds:
            lines.append(f"complete -c kanban-cli -n '__fish_seen_subcommand_from auth' -a '{c}'")
        return "\n".join(lines) + "\n"

    return ""


async def execute_tool_action(
    surface: Surface,
    spec: ToolSpec,
    arguments: dict[str, Any],
    config: ResolvedConfig,
    *,
    json_mode: bool = False,
    jsonl_mode: bool = False,
    internal_client: KanbanApiClient | None = None,
) -> int:
    """Execute a single ToolSpec action with 1:1 MCP parity, validation, and error reporting."""
    # 1. Progressive disclosure: JIT help check
    is_help_requested = any(
        isinstance(arguments.get(k), str) and arguments.get(k, "").strip().lower() == "help"
        for k in ("identifier", "action", "source", "id", "project", "summary")
    )
    if is_help_requested:
        project_arg = arguments.get("project")
        help_data = await build_help(
            tool_name=spec.name,
            project=str(project_arg) if project_arg is not None else None,
            client=internal_client,
            subject_token=config.token,
        )
        print(dump_yaml(help_data))
        # Negative / self-correcting test case requires exit code 2 for --project help
        return 2

    # Extract client-side filter attributes before schema validation
    filter_priority = arguments.pop("_filter_priority", None)

    # 2. Pre-dispatch validation against schema
    try:
        validate_tool_arguments_schema(spec, arguments, surface=surface)
    except KbMcpError as err:
        print(err.to_yaml(), file=sys.stderr)
        return 2

    # 3. Setup client and context
    client = internal_client
    owns_client = False
    if client is None:
        owns_client = True
        client = KanbanApiClient(
            base_url=config.url,
            mode="cli_remote",
            api_token=config.token,
        )

    ctx = McpRequestContext(
        client=client,
        surface=surface,
        subject_token=config.token,
    )
    ctx_token = set_current_mcp_context(ctx)

    try:
        handler = spec.handler
        import inspect

        if inspect.iscoroutinefunction(handler):
            res = await handler(arguments)
        else:
            res = handler(arguments)
            if inspect.isawaitable(res):
                res = await res
    except KbMcpError as err:
        print(err.to_yaml(), file=sys.stderr)
        return 2
    except Exception as exc:
        internal_err = KbMcpError(
            McpErrorCode.INTERNAL,
            f"Command execution failed: {exc}",
        )
        print(internal_err.to_yaml(), file=sys.stderr)
        return 2
    finally:
        reset_current_mcp_context(ctx_token)
        if owns_client:
            await client.aclose()

    # 4. Optional client-side predicate filter post-processing (e.g. priority on search_tickets)
    if filter_priority and isinstance(res, dict) and "items" in res:
        filtered_items = [
            item
            for item in res["items"]
            if str(item.get("priority", "")).lower() == filter_priority
        ]
        res["items"] = filtered_items
        res["total"] = len(filtered_items)

    # 5. Output rendering
    if jsonl_mode:
        if isinstance(res, dict) and "items" in res:
            for item in res["items"]:
                print(json.dumps(item))
            # Stream remaining pages if cursor exists
            cursor = res.get("next_cursor")
            while cursor:
                next_args = dict(arguments)
                next_args["cursor"] = cursor
                ctx_t = set_current_mcp_context(ctx)
                try:
                    if inspect.iscoroutinefunction(spec.handler):
                        next_res = await spec.handler(next_args)
                    else:
                        next_res = spec.handler(next_args)
                        if inspect.isawaitable(next_res):
                            next_res = await next_res
                finally:
                    reset_current_mcp_context(ctx_t)
                if isinstance(next_res, dict) and "items" in next_res:
                    for item in next_res["items"]:
                        print(json.dumps(item))
                    cursor = next_res.get("next_cursor")
                else:
                    break
        elif isinstance(res, list):
            for item in res:
                print(json.dumps(item))
        else:
            print(json.dumps(res))
    elif json_mode:
        print(json.dumps(res, indent=2))
    elif isinstance(res, str):
        print(res)
    elif isinstance(res, (dict, list)):
        print(dump_yaml(res))
    else:
        print(str(res))

    return 0


async def parse_and_execute_cli(
    argv: list[str],
    *,
    surface_override: Surface | None = None,
    client: KanbanApiClient | None = None,
) -> int:
    """Parse command line arguments and execute the corresponding tool, auth, or completion action."""
    # Pre-process raw argv for compound subcommands like 'issue list' or 'docs search'
    args_list = list(argv)

    # Convert alias 'issue list' to 'issue-list' or 'search-tickets'
    if len(args_list) >= 2 and args_list[0] == "issue" and args_list[1] == "list":
        args_list = ["search-tickets"] + args_list[2:]

    if surface_override == Surface.AGENT:
        parser, dispatch = build_agent_cli_parser()
    elif surface_override == Surface.DOCS:
        parser, dispatch = build_docs_cli_parser()
    elif surface_override == Surface.ADMIN:
        parser, dispatch = build_admin_cli_parser()
    else:
        parser, dispatch = build_unified_cli_parser()

    # Check for completions before strict parsing
    if len(args_list) >= 2 and args_list[0] == "completions":
        shell = args_list[1]
        print(generate_completions(shell))
        return 0

    try:
        parsed_ns, remaining = parser.parse_known_args(args_list)
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 2

    # Check for unknown flags or parameters
    if remaining:
        # Check if the remaining arguments are unrecognized flags
        first_unknown = remaining[0]
        tool_name = parsed_ns.subcommand or "kanban-cli"
        if tool_name.startswith("--"):
            tool_name = "kanban-cli"

        err = KbMcpError(
            McpErrorCode.VALIDATION_FAILED,
            f"Unknown parameter '{first_unknown.lstrip('-')}' for tool '{tool_name}'",
            field=first_unknown.lstrip("-"),
            fix_hint=f"Unknown flag '{first_unknown}'. Check 'kanban-cli --help' for valid options.",
        )
        print(err.to_yaml(), file=sys.stderr)
        return 2

    cmd = parsed_ns.subcommand
    if not cmd:
        parser.print_help()
        return 0

    # Handle docs sub-parser routing
    if cmd == "docs":
        docs_cmd = getattr(parsed_ns, "docs_command", None)
        if not docs_cmd:
            print("Error: Missing docs subcommand (search, create, update)", file=sys.stderr)
            return 2
        cmd = f"docs {docs_cmd}"

    # Handle admin sub-parser routing
    if cmd == "admin":
        admin_cmd = getattr(parsed_ns, "admin_command", None)
        if not admin_cmd:
            print("Error: Missing admin subcommand", file=sys.stderr)
            return 2
        cmd = f"admin {admin_cmd}"

    # Handle auth sub-parser routing
    if cmd == "auth":
        from mcp.cli.auth import auth_login, auth_logout, auth_status, resolve_config

        auth_cmd = getattr(parsed_ns, "auth_command", None)
        cfg = resolve_config(
            cli_url=getattr(parsed_ns, "url", None),
            cli_workspace=getattr(parsed_ns, "workspace", None),
            cli_project=getattr(parsed_ns, "project", None),
            cli_token=getattr(parsed_ns, "token", None),
        )
        if auth_cmd == "login":
            return auth_login(
                url=cfg.url,
                device=bool(getattr(parsed_ns, "device", False)),
                token=getattr(parsed_ns, "token", None),
            )
        if auth_cmd == "status":
            return auth_status(cfg)
        if auth_cmd == "logout":
            return auth_logout()
        print("Error: Missing auth subcommand (login, status, logout)", file=sys.stderr)
        return 2

    if cmd not in dispatch:
        err = KbMcpError(
            McpErrorCode.VALIDATION_FAILED,
            f"Unknown command '{cmd}'",
            valid_options=list(dispatch.keys()),
        )
        print(err.to_yaml(), file=sys.stderr)
        return 2

    surface, spec = dispatch[cmd]
    from mcp.cli.auth import resolve_config

    cfg = resolve_config(
        cli_url=getattr(parsed_ns, "url", None),
        cli_workspace=getattr(parsed_ns, "workspace", None),
        cli_project=getattr(parsed_ns, "project", None),
        cli_token=getattr(parsed_ns, "token", None),
    )

    parsed_dict = vars(parsed_ns)
    # Inject project/workspace into tool arguments if specified globally
    if cfg.project and not parsed_dict.get("project"):
        parsed_dict["project"] = cfg.project
    if cfg.workspace and not parsed_dict.get("workspace"):
        parsed_dict["workspace"] = cfg.workspace
    cli_lod = getattr(parsed_ns, "lod", None)
    if cli_lod and not parsed_dict.get("lod"):
        parsed_dict["lod"] = cli_lod

    cli_filter = getattr(parsed_ns, "filter", None)
    try:
        normalized_args = _normalize_parsed_arguments(spec, parsed_dict, cli_filter=cli_filter)
    except KbMcpError as err:
        print(err.to_yaml(), file=sys.stderr)
        return 2

    return await execute_tool_action(
        surface=surface,
        spec=spec,
        arguments=normalized_args,
        config=cfg,
        json_mode=bool(getattr(parsed_ns, "json", False)),
        jsonl_mode=bool(getattr(parsed_ns, "jsonl", False)),
        internal_client=client,
    )
