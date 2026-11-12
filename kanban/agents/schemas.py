"""Pydantic v2 schemas for agent definitions registry (KB-P5-16)."""

from __future__ import annotations

import re
import uuid  # noqa: TC003  # Required at runtime by Pydantic field resolution
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from kanban.agents.cli_policy import BINARY_ALLOWLIST, CliPolicyError, validate_cli_args
from kanban.api.problems import ProblemException
from kanban.content import ContentNormalizeError, normalize_to_markdown

SLUG_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[a-z0-9][a-z0-9-]{1,62}$")
MAX_INSTRUCTIONS_BYTES: Final[int] = 65536
ALLOWED_MCP_TOOLS: Final[frozenset[str]] = frozenset(
    {"search_tickets", "read_ticket", "search_knowledge", "read_doc"}
)

HarnessKind = Literal["in_app_sdk", "cli_pipe", "remote_runner"]
ProviderKind = Literal["openai", "ollama", "gemini", "fixture"]
RepoAccessMode = Literal["none", "bare_git_tools", "ro_vfs_mount"]


class AgentDefinitionCreate(BaseModel):
    """Request payload for POST /api/v1/workspaces/{workspace}/agent-definitions."""

    model_config = ConfigDict(extra="forbid")

    slug: str
    display_name: str = Field(min_length=1, max_length=200)
    project_id: uuid.UUID | None = None
    harness_kind: HarnessKind
    provider_kind: ProviderKind | None = None
    model_id: str | None = None
    cli_binary_allowlist_id: str | None = None
    cli_args: list[str] = Field(default_factory=list)
    remote_runner_pool_slug: str | None = None
    repo_access_mode: RepoAccessMode = "none"
    mcp_allowed_tools: list[str] = Field(
        default_factory=lambda: ["search_tickets", "read_ticket", "search_knowledge", "read_doc"]
    )
    system_instructions_md: str = ""
    timeout_ms: int = Field(default=60000, ge=1000, le=300000)

    @field_validator("slug")
    @classmethod
    def validate_slug(cls, v: str) -> str:
        """Enforce slug regex ^[a-z0-9][a-z0-9-]{1,62}$."""
        if not SLUG_PATTERN.match(v):
            raise ProblemException(
                code="HARNESS_FIELDS_INVALID",
                status=422,
                title="Invalid Slug",
                detail="Slug must match pattern '^[a-z0-9][a-z0-9-]{1,62}$'",
            )
        return v

    def _validate_mcp_tools(self) -> None:
        """Assert all requested MCP tools belong to the allowed subset."""
        for tool in self.mcp_allowed_tools:
            if tool not in ALLOWED_MCP_TOOLS:
                msg = f"Tool {tool!r} is not in allowed MCP tools subset"
                raise ProblemException(
                    code="HARNESS_FIELDS_INVALID",
                    status=422,
                    title="Invalid MCP Tool",
                    detail=msg,
                )

    def _validate_in_app_sdk(self) -> None:
        """Validate in_app_sdk harness fields."""
        if not self.provider_kind or not self.model_id:
            msg = "in_app_sdk harness requires both provider_kind and model_id"
            raise ProblemException(
                code="HARNESS_FIELDS_INVALID",
                status=422,
                title="Harness Fields Invalid",
                detail=msg,
            )
        if self.cli_binary_allowlist_id is not None or self.remote_runner_pool_slug is not None:
            msg = (
                "in_app_sdk harness cannot have cli_binary_allowlist_id or remote_runner_pool_slug"
            )
            raise ProblemException(
                code="HARNESS_FIELDS_INVALID",
                status=422,
                title="Harness Fields Invalid",
                detail=msg,
            )

    def _validate_cli_pipe(self) -> None:
        """Validate cli_pipe harness fields and run CLI policy."""
        if not self.cli_binary_allowlist_id:
            msg = "cli_pipe harness requires cli_binary_allowlist_id"
            raise ProblemException(
                code="HARNESS_FIELDS_INVALID",
                status=422,
                title="Harness Fields Invalid",
                detail=msg,
            )
        if self.remote_runner_pool_slug is not None:
            msg = "cli_pipe harness cannot have remote_runner_pool_slug"
            raise ProblemException(
                code="HARNESS_FIELDS_INVALID",
                status=422,
                title="Harness Fields Invalid",
                detail=msg,
            )
        if self.cli_binary_allowlist_id not in BINARY_ALLOWLIST:
            msg = f"Binary identifier {self.cli_binary_allowlist_id!r} is not in allowlist"
            raise ProblemException(
                code="CLI_BINARY_NOT_ALLOWLISTED",
                status=422,
                title="Binary Not Allowlisted",
                detail=msg,
            )
        try:
            validate_cli_args(self.cli_binary_allowlist_id, self.cli_args)
        except CliPolicyError as exc:
            raise ProblemException(
                code=exc.code, status=exc.status, title="CLI Policy Violation", detail=exc.detail
            ) from exc

    def _validate_system_instructions(self) -> None:
        """Validate system_instructions_md length and canonical normalization."""
        raw_instructions = self.system_instructions_md
        try:
            raw_bytes = raw_instructions.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise ProblemException(
                code="CLI_ARGS_INVALID",
                status=422,
                title="Invalid Markdown Content",
                detail="Surrogates not allowed in system_instructions_md",
            ) from exc

        if len(raw_bytes) > MAX_INSTRUCTIONS_BYTES:
            msg = (
                f"system_instructions_md byte length {len(raw_bytes)} exceeds "
                f"{MAX_INSTRUCTIONS_BYTES}"
            )
            raise ProblemException(
                code="CLI_ARGS_INVALID",
                status=422,
                title="System Instructions Too Large",
                detail=msg,
            )
        try:
            self.system_instructions_md = normalize_to_markdown(
                raw_instructions, max_input_bytes=MAX_INSTRUCTIONS_BYTES
            )
        except (ContentNormalizeError, UnicodeEncodeError) as exc:
            raise ProblemException(
                code="CLI_ARGS_INVALID",
                status=422,
                title="Invalid Markdown Content",
                detail=str(exc),
            ) from exc

    @model_validator(mode="after")
    def validate_harness_and_tools(self) -> AgentDefinitionCreate:
        """Validate harness fields consistency, tool allowlist, and CLI policy."""
        self._validate_mcp_tools()

        if self.harness_kind == "in_app_sdk":
            self._validate_in_app_sdk()
        elif self.harness_kind == "cli_pipe":
            self._validate_cli_pipe()
        elif not self.remote_runner_pool_slug:
            raise ProblemException(
                code="HARNESS_FIELDS_INVALID",
                status=422,
                title="Harness Fields Invalid",
                detail="remote_runner harness requires remote_runner_pool_slug",
            )

        self._validate_system_instructions()
        return self


class AgentDefinitionPatch(BaseModel):
    """Request payload for PATCH /api/v1/agent-definitions/{agent}."""

    model_config = ConfigDict(extra="forbid")

    display_name: str | None = Field(default=None, min_length=1, max_length=200)
    provider_kind: ProviderKind | None = None
    model_id: str | None = None
    cli_binary_allowlist_id: str | None = None
    cli_args: list[str] | None = None
    remote_runner_pool_slug: str | None = None
    repo_access_mode: RepoAccessMode | None = None
    mcp_allowed_tools: list[str] | None = None
    system_instructions_md: str | None = None
    timeout_ms: int | None = Field(default=None, ge=1000, le=300000)

    def _validate_patch_tools(self) -> None:
        """Validate MCP tools allowlist on patch."""
        if self.mcp_allowed_tools is not None:
            for tool in self.mcp_allowed_tools:
                if tool not in ALLOWED_MCP_TOOLS:
                    raise ProblemException(
                        code="HARNESS_FIELDS_INVALID",
                        status=422,
                        title="Invalid MCP Tool",
                        detail=f"Tool {tool!r} is not in allowed MCP tools subset",
                    )

    def _validate_patch_instructions(self) -> None:
        """Validate system instructions length and encoding on patch."""
        if self.system_instructions_md is not None:
            try:
                raw_bytes = self.system_instructions_md.encode("utf-8")
            except UnicodeEncodeError as exc:
                raise ProblemException(
                    code="CLI_ARGS_INVALID",
                    status=422,
                    title="Invalid Markdown Content",
                    detail="Surrogates not allowed in system_instructions_md",
                ) from exc

            if len(raw_bytes) > MAX_INSTRUCTIONS_BYTES:
                msg = (
                    f"system_instructions_md byte length {len(raw_bytes)} exceeds "
                    f"{MAX_INSTRUCTIONS_BYTES}"
                )
                raise ProblemException(
                    code="CLI_ARGS_INVALID",
                    status=422,
                    title="System Instructions Too Large",
                    detail=msg,
                )
            try:
                self.system_instructions_md = normalize_to_markdown(
                    self.system_instructions_md, max_input_bytes=MAX_INSTRUCTIONS_BYTES
                )
            except (ContentNormalizeError, UnicodeEncodeError) as exc:
                raise ProblemException(
                    code="CLI_ARGS_INVALID",
                    status=422,
                    title="Invalid Markdown Content",
                    detail=str(exc),
                ) from exc

    @model_validator(mode="after")
    def validate_patch_fields(self) -> AgentDefinitionPatch:
        """Validate patch fields if supplied."""
        self._validate_patch_tools()

        if (
            self.cli_binary_allowlist_id is not None
            and self.cli_binary_allowlist_id not in BINARY_ALLOWLIST
        ):
            raise ProblemException(
                code="CLI_BINARY_NOT_ALLOWLISTED",
                status=422,
                title="Binary Not Allowlisted",
                detail=f"Binary identifier {self.cli_binary_allowlist_id!r} is not in allowlist",
            )

        self._validate_patch_instructions()
        return self


class AgentDefinitionResponse(BaseModel):
    """Canonical representation of an agent definition returned by the API."""

    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    workspace_id: uuid.UUID
    project_id: uuid.UUID | None
    principal_id: uuid.UUID
    slug: str
    display_name: str
    harness_kind: str
    provider_kind: str | None
    model_id: str | None
    cli_binary_allowlist_id: str | None
    cli_args: list[str]
    remote_runner_pool_slug: str | None
    repo_access_mode: str
    mcp_allowed_tools: list[str]
    system_instructions_md: str
    timeout_ms: int
