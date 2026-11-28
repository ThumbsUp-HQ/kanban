# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Tool definitions and strict argument validation for read-only SDK transition tools (S14.2).

Contract: every model-supplied argument dict is hostile. ``validate_tool_args`` rejects
non-dict payloads, unknown kwargs, bool-for-int, out-of-range ints, and oversized strings
before any toolkit method is invoked. Pure and synchronous (microseconds).
"""

from __future__ import annotations

from typing import Annotated, Any, Final

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr, ValidationError

from agent.providers.base import ToolDefinition
from agent.tools.repo_path_guard import CODE_REPO_PATH_INVALID, RepoToolPolicyError

__all__ = [
    "MAX_TOOL_STRING_LEN",
    "MCP_READ_TOOL_DEFINITIONS",
    "REPO_TOOL_DEFINITIONS",
    "validate_tool_args",
]

MAX_TOOL_STRING_LEN: Final[int] = 512
_Str = Annotated[StrictStr, Field(max_length=MAX_TOOL_STRING_LEN)]
_Limit = Annotated[StrictInt, Field(ge=1, le=50)]
_CODE_NOT_PERMITTED: Final[str] = "TOOL_NOT_PERMITTED"
_STRICT = ConfigDict(extra="forbid", strict=True)


class _RepoTreeArgs(BaseModel):
    model_config = _STRICT
    path: _Str = ""
    max_depth: Annotated[StrictInt, Field(ge=1, le=6)] = 3


class _RepoReadFileArgs(BaseModel):
    model_config = _STRICT
    path: _Str
    start_line: Annotated[StrictInt, Field(ge=1, le=10_000_000)] = 1
    end_line: Annotated[StrictInt, Field(ge=1, le=10_000_000)] = 200


class _RepoGrepArgs(BaseModel):
    model_config = _STRICT
    pattern: Annotated[StrictStr, Field(min_length=1, max_length=200)]
    path: _Str = ""


class _RepoGitLogArgs(BaseModel):
    model_config = _STRICT
    path: _Str = ""
    max_commits: Annotated[StrictInt, Field(ge=1, le=50)] = 20


class _RepoGitDiffArgs(BaseModel):
    model_config = _STRICT
    base_ref: Annotated[StrictStr, Field(min_length=1, max_length=120)]
    path: _Str = ""


class _SearchArgs(BaseModel):
    model_config = _STRICT
    query: _Str
    limit: _Limit = 10


class _ReadTicketArgs(BaseModel):
    model_config = _STRICT
    identifier: Annotated[StrictStr, Field(min_length=1, max_length=128)]


class _ReadDocArgs(BaseModel):
    model_config = _STRICT
    slug: Annotated[StrictStr, Field(min_length=1, max_length=256)]


_ARG_MODELS: Final[dict[str, type[BaseModel]]] = {
    "repo_tree": _RepoTreeArgs,
    "repo_read_file": _RepoReadFileArgs,
    "repo_grep": _RepoGrepArgs,
    "repo_git_log": _RepoGitLogArgs,
    "repo_git_diff": _RepoGitDiffArgs,
    "search_tickets": _SearchArgs,
    "read_ticket": _ReadTicketArgs,
    "search_knowledge": _SearchArgs,
    "read_doc": _ReadDocArgs,
}


def _def(name: str, description: str) -> ToolDefinition:
    schema = _ARG_MODELS[name].model_json_schema()
    schema.pop("title", None)
    for prop in schema.get("properties", {}).values():
        prop.pop("title", None)
    schema["additionalProperties"] = False
    return ToolDefinition(name=name, description=description, parameters=schema)


REPO_TOOL_DEFINITIONS: Final[tuple[ToolDefinition, ...]] = (
    _def("repo_tree", "List files in the commit-pinned repository up to max_depth."),
    _def("repo_read_file", "Read a 1-indexed line range of a text file at the pinned commit."),
    _def("repo_grep", "Literal string search across the pinned commit."),
    _def("repo_git_log", "Show commit history leading to the pinned commit."),
    _def("repo_git_diff", "Unified diff between base_ref and the pinned commit."),
)

MCP_READ_TOOL_DEFINITIONS: Final[tuple[ToolDefinition, ...]] = (
    _def("search_tickets", "Search tickets by text query."),
    _def("read_ticket", "Read a ticket by human-readable identifier."),
    _def("search_knowledge", "Search knowledge-base docs by text query."),
    _def("read_doc", "Read a knowledge-base doc by slug."),
)


def validate_tool_args(tool_name: str, raw_args: dict[str, Any]) -> dict[str, Any]:
    """Validate and return sanitized tool args; raise RepoToolPolicyError on violation."""
    model = _ARG_MODELS.get(tool_name)
    if model is None:
        msg = f"Unknown tool '{tool_name}'"
        raise RepoToolPolicyError(_CODE_NOT_PERMITTED, msg)
    candidate: object = raw_args
    if not isinstance(candidate, dict):
        msg = f"Arguments for '{tool_name}' must be an object"
        raise RepoToolPolicyError(CODE_REPO_PATH_INVALID, msg)
    try:
        return model.model_validate(raw_args).model_dump()
    except ValidationError as exc:
        first = exc.errors()[0]
        loc = ".".join(str(p) for p in first["loc"]) or "args"
        msg = f"Invalid arguments for '{tool_name}': {loc}: {first['type']}"
        raise RepoToolPolicyError(CODE_REPO_PATH_INVALID, msg) from exc
