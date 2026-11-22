# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Deterministic context builder for spotlighted transition YAML payloads (S14.3)."""

from __future__ import annotations

import hashlib
import re
import secrets
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final, Literal, cast

import yaml
from pydantic import BaseModel, ConfigDict, Field, PrivateAttr

from database.models.prose import UNTRUSTED_PROVENANCE_TIERS
from kanban.security.scrubber import scrub_text

if TYPE_CHECKING:
    import random
    from pathlib import Path

__all__ = [
    "ContextDelimiterCollisionError",
    "ContextTooLargeError",
    "McpAccess",
    "RenderedContext",
    "RepoContext",
    "TicketSnapshot",
    "TransitionContextModel",
    "TransitionMetadata",
    "build_transition_context",
]

MAX_DESCRIPTION_BYTES: Final[int] = 196_608
MAX_CONTEXT_BYTES: Final[int] = 262_144
MAX_DELIMITER_ATTEMPTS: Final[int] = 8

# Matches Unicode zero-width characters (U+200B..U+200F) and tags (U+E0000..U+E007F)
_RE_ZERO_WIDTH_TAG: Final[re.Pattern[str]] = re.compile(r"[\u200B-\u200F\U000E0000-\U000E007F]")


class ContextDelimiterCollisionError(ValueError):
    """Raised when generated untrusted delimiter collides with ticket content."""


class ContextTooLargeError(ValueError):
    """Raised when rendered transition context exceeds maximum size cap."""


class TransitionMetadata(BaseModel):
    """Metadata describing the target workflow transition."""

    model_config = ConfigDict(extra="forbid", strict=True)

    project: str
    issue: str
    from_state: str
    to_state: str
    actor: str


class RepoContext(BaseModel):
    """Read-only repository mount configuration for the agent execution."""

    model_config = ConfigDict(extra="forbid", strict=True)

    mount_path: str = "/workspace/repo"
    access: Literal["read-only"] = "read-only"
    head_commit: str
    _mirror_path: str | Path | None = PrivateAttr(default=None)

    def __init__(
        self,
        *,
        mount_path: str = "/workspace/repo",
        access: Literal["read-only"] = "read-only",
        head_commit: str,
        mirror_path: str | Path | None = None,
        **kwargs: Any,  # noqa: ANN401
    ) -> None:
        """Initialize repository mount configuration."""
        super().__init__(mount_path=mount_path, access=access, head_commit=head_commit, **kwargs)
        self._mirror_path = mirror_path

    @property
    def mirror_path(self) -> Path | str | None:
        """Bare git repository mirror path."""
        return self._mirror_path

    @mirror_path.setter
    def mirror_path(self, val: Path | str | None) -> None:
        self._mirror_path = val


class McpAccess(BaseModel):
    """Configuration for ephemeral MCP service connections."""

    model_config = ConfigDict(extra="forbid", strict=True)

    agent_url: str
    docs_url: str
    ephemeral_bearer_env: Literal["KANBAN_EPHEMERAL_MCP_TOKEN"] = "KANBAN_EPHEMERAL_MCP_TOKEN"


class TicketSnapshot(BaseModel):
    """Sanitized and spotlighted snapshot of the ticket undergoing transition."""

    model_config = ConfigDict(extra="forbid", strict=True)

    delimiter: str
    summary: str
    priority: str
    labels: list[str] = Field(default_factory=list)
    description_markdown: str
    actor: str | None = None
    comments: list[dict[str, Any]] | None = None

    @classmethod
    def __get_pydantic_json_schema__(
        cls,
        core_schema: Any,  # noqa: ANN401
        handler: Any,  # noqa: ANN401
    ) -> dict[str, Any]:
        """Preserve canonical v1 schema export for backwards compatibility."""
        json_schema = handler(core_schema)
        props = json_schema.get("properties", {})
        props.pop("actor", None)
        props.pop("comments", None)
        return cast("dict[str, Any]", json_schema)


class TransitionContextModel(BaseModel):
    """Canonical schema for kb-transition-context/v1 payload."""

    model_config = ConfigDict(extra="forbid", strict=True, populate_by_name=True)

    schema_version: Literal["kb-transition-context/v1"] = Field(
        default="kb-transition-context/v1",
        alias="schema",
    )
    execution_id: str
    verdict_nonce: str
    transition: TransitionMetadata
    repo_context: RepoContext | None = None
    mcp_access: McpAccess
    ticket_snapshot: TicketSnapshot


@dataclass
class RenderedContext:
    """Rendered and spotlighted transition context ready for agent execution."""

    yaml_bytes: bytes
    sha256: str
    delimiter: str
    verdict_nonce: str
    ephemeral_token: bytearray
    allowed_mutable_fields: frozenset[str]
    repo_context: RepoContext | None = None
    mcp_access: McpAccess | None = None

    def destroy(self) -> None:
        """Securely zeroize ephemeral token bytes in mutable memory."""
        for i in range(len(self.ephemeral_token)):
            self.ephemeral_token[i] = 0
        del self.ephemeral_token[:]


class _SpotlightDumper(yaml.SafeDumper):
    """Custom YAML SafeDumper formatting multiline strings as block scalars."""


def _str_representer(dumper: yaml.SafeDumper, data: str) -> yaml.ScalarNode:
    if "\n" in data:
        return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")
    return dumper.represent_scalar("tag:yaml.org,2002:str", data)


_SpotlightDumper.add_representer(str, _str_representer)


def _sanitize_untrusted_text(text: str) -> str:
    """Strip zero-width / tag characters and run outbound secret scrubber."""
    no_zero_width = _RE_ZERO_WIDTH_TAG.sub("", text)
    return scrub_text(no_zero_width)


def _truncate_utf8_bytes(text: str, max_bytes: int) -> tuple[str, int]:
    """Truncate text to at most max_bytes respecting UTF-8 character boundaries."""
    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return text, 0

    truncated_bytes = len(encoded) - max_bytes
    # Slice encoded bytes and decode with ignore to avoid splitting multibyte character
    truncated_text = encoded[:max_bytes].decode("utf-8", errors="ignore")
    return truncated_text, truncated_bytes


def build_transition_context(  # noqa: C901, PLR0912, PLR0913, PLR0915
    execution: object,
    issue: object,
    agent_def: object,
    repo_context: RepoContext | None = None,
    mcp_urls: object = None,
    *,
    rng: random.Random | None = None,
    ephemeral_token: bytes | bytearray | str | None = None,
    spotlight_all: bool | None = None,
) -> RenderedContext:
    """Construct deterministic, spotlighted, and sanitized transition context YAML."""
    # Extract execution identifiers
    exec_dict = execution if isinstance(execution, dict) else {}
    execution_id = str(
        getattr(execution, "id", None) or exec_dict.get("id") or exec_dict.get("execution_id") or ""
    )
    project_key = str(
        getattr(execution, "project_key", None)
        or getattr(execution, "project_id", None)
        or exec_dict.get("project_key")
        or exec_dict.get("project")
        or "KAN"
    )
    from_state = str(
        getattr(execution, "from_state", None)
        or getattr(execution, "from_state_name", None)
        or exec_dict.get("from_state")
        or "In Review"
    )
    to_state = str(
        getattr(execution, "to_state", None)
        or getattr(execution, "to_state_name", None)
        or exec_dict.get("to_state")
        or "Done"
    )
    raw_actor = str(
        getattr(execution, "actor", None)
        or getattr(execution, "actor_handle", None)
        or getattr(execution, "actor_name", None)
        or exec_dict.get("actor")
        or "@system"
    )
    actor = _sanitize_untrusted_text(raw_actor)

    allowed_mutable_raw = (
        getattr(execution, "allowed_mutable_fields", None)
        or (execution.get("allowed_mutable_fields") if isinstance(execution, dict) else None)
        or ()
    )
    allowed_mutable = frozenset(allowed_mutable_raw)

    # Extract issue details
    issue_key = str(
        getattr(issue, "key", None)
        or getattr(issue, "identifier", None)
        or getattr(issue, "id", None)
        or (
            issue.get("key") or issue.get("identifier") or issue.get("id")
            if isinstance(issue, dict)
            else ""
        )
        or "KAN-1"
    )
    raw_summary = str(
        getattr(issue, "summary", None)
        or getattr(issue, "title", None)
        or (issue.get("summary") or issue.get("title") if isinstance(issue, dict) else "")
        or ""
    )
    summary = _sanitize_untrusted_text(raw_summary)

    raw_priority = str(
        getattr(issue, "priority", None)
        or (issue.get("priority") if isinstance(issue, dict) else "")
        or "None"
    )
    priority = _sanitize_untrusted_text(raw_priority)

    raw_labels = (
        getattr(issue, "labels", None)
        or (issue.get("labels") if isinstance(issue, dict) else None)
        or []
    )
    labels = [_sanitize_untrusted_text(str(lbl)) for lbl in raw_labels]

    issue_dict = issue if isinstance(issue, dict) else {}
    raw_desc = str(
        getattr(issue, "description_markdown", None)
        or getattr(issue, "description", None)
        or issue_dict.get("description_markdown")
        or issue_dict.get("description")
        or ""
    )
    cleaned_desc = _sanitize_untrusted_text(raw_desc)

    # Truncate description if exceeding limit
    truncated_desc, trunc_bytes = _truncate_utf8_bytes(cleaned_desc, MAX_DESCRIPTION_BYTES)
    if trunc_bytes > 0:
        truncated_desc = f"{truncated_desc}\n[TRUNCATED {trunc_bytes} bytes]"

    # Extract comments
    raw_comments = (
        getattr(issue, "comments", None)
        or (issue.get("comments") if isinstance(issue, dict) else None)
        or getattr(execution, "comments", None)
        or (execution.get("comments") if isinstance(execution, dict) else None)
        or []
    )

    has_untrusted_provenance = bool(
        getattr(issue, "is_untrusted_content", False)
        or (issue.get("is_untrusted_content") if isinstance(issue, dict) else False)
        or getattr(issue, "provenance_tier", "") in UNTRUSTED_PROVENANCE_TIERS
        or (issue.get("provenance_tier") if isinstance(issue, dict) else "")
        in UNTRUSTED_PROVENANCE_TIERS
        or any(
            (
                c.get("is_untrusted_content")
                if isinstance(c, dict)
                else getattr(c, "is_untrusted_content", False)
            )
            or (
                c.get("provenance_tier")
                if isinstance(c, dict)
                else getattr(c, "provenance_tier", "")
            )
            in UNTRUSTED_PROVENANCE_TIERS
            for c in raw_comments
        )
    )
    should_spotlight = spotlight_all if spotlight_all is not None else has_untrusted_provenance

    # Delimiter generation with collision detection across all fields including comments
    comment_texts: list[str] = []
    for c in raw_comments:
        if isinstance(c, dict):
            c_body = str(c.get("body") or c.get("content") or c.get("body_markdown") or "")
        else:
            c_body = str(
                getattr(c, "body", "")
                or getattr(c, "content", "")
                or getattr(c, "body_markdown", "")
                or c
            )
        comment_texts.append(_sanitize_untrusted_text(c_body))

    fields_to_check = [summary, priority, " ".join(labels), truncated_desc, actor, *comment_texts]
    delimiter: str | None = None
    for _ in range(MAX_DELIMITER_ATTEMPTS):
        if rng is not None:
            token_hex_suffix = f"{rng.getrandbits(64):016x}"
        else:
            token_hex_suffix = secrets.token_hex(8)
        candidate = f"<<<UNTRUSTED_TICKET_DATA_{token_hex_suffix}>>>"
        if not any(candidate in field_text for field_text in fields_to_check):
            delimiter = candidate
            break

    if delimiter is None:
        msg = (
            f"CONTEXT_DELIMITER_COLLISION: Failed to generate unique delimiter "
            f"after {MAX_DELIMITER_ATTEMPTS} attempts"
        )
        raise ContextDelimiterCollisionError(msg)

    # Wrap description inside delimiter block
    block_description = f"{delimiter}\n{truncated_desc}\n{delimiter}\n"

    # Verdict nonce (128-bit hex string)
    verdict_nonce = f"{rng.getrandbits(128):032x}" if rng is not None else secrets.token_hex(16)

    # MCP access URLs
    if isinstance(mcp_urls, dict):
        agent_url = mcp_urls.get("agent_url", "https://kanban.internal/mcp/agent")
        docs_url = mcp_urls.get("docs_url", "https://kanban.internal/mcp/docs")
    else:
        agent_url = getattr(mcp_urls, "agent_url", "https://kanban.internal/mcp/agent")
        docs_url = getattr(mcp_urls, "docs_url", "https://kanban.internal/mcp/docs")
    mcp_access = McpAccess(agent_url=agent_url, docs_url=docs_url)

    # Ephemeral token management (kept exclusively in bytearray)
    if ephemeral_token is None:
        token_bytes = secrets.token_bytes(32)
    elif isinstance(ephemeral_token, bytearray):
        token_bytes = bytes(ephemeral_token)
    elif isinstance(ephemeral_token, bytes):
        token_bytes = ephemeral_token
    else:
        token_bytes = str(ephemeral_token).encode("utf-8")
    ephemeral_bytearray = bytearray(token_bytes)

    # Repo context check: omit if repo_access_mode == 'none'
    agent_dict = agent_def if isinstance(agent_def, dict) else {}
    repo_access_mode = str(
        agent_dict.get("repo_access_mode")
        or getattr(agent_def, "repo_access_mode", "read-only")
        or "read-only"
    )
    include_repo = repo_context is not None and repo_access_mode != "none"

    # Build context dictionary
    context_dict: dict[str, Any] = {
        "schema": "kb-transition-context/v1",
        "execution_id": execution_id,
        "verdict_nonce": verdict_nonce,
        "transition": {
            "project": project_key,
            "issue": issue_key,
            "from_state": from_state,
            "to_state": to_state,
            "actor": actor,
        },
    }

    if include_repo and repo_context is not None:
        context_dict["repo_context"] = {
            "mount_path": repo_context.mount_path,
            "access": repo_context.access,
            "head_commit": repo_context.head_commit,
        }

    context_dict["mcp_access"] = {
        "agent_url": agent_url,
        "docs_url": docs_url,
        "ephemeral_bearer_env": "KANBAN_EPHEMERAL_MCP_TOKEN",
    }

    if should_spotlight:
        wrapped_summary = f"{delimiter}\n{summary}\n{delimiter}\n"
        wrapped_priority = f"{delimiter}\n{priority}\n{delimiter}\n"
        wrapped_labels = [f"{delimiter}\n{lbl}\n{delimiter}\n" for lbl in labels]
        wrapped_actor = f"{delimiter}\n{actor}\n{delimiter}\n"
    else:
        wrapped_summary = summary
        wrapped_priority = priority
        wrapped_labels = labels
        wrapped_actor = actor

    formatted_comments: list[dict[str, Any]] = []
    for c in raw_comments:
        if isinstance(c, dict):
            c_body = _sanitize_untrusted_text(
                str(c.get("body") or c.get("content") or c.get("body_markdown") or "")
            )
            c_tier = str(c.get("provenance_tier") or "trusted_member")
            c_author = _sanitize_untrusted_text(str(c.get("author") or c.get("actor") or ""))
        else:
            c_body = _sanitize_untrusted_text(
                str(
                    getattr(c, "body", "")
                    or getattr(c, "content", "")
                    or getattr(c, "body_markdown", "")
                    or c
                )
            )
            c_tier = str(getattr(c, "provenance_tier", "trusted_member"))
            c_author = _sanitize_untrusted_text(
                str(getattr(c, "author", "") or getattr(c, "actor", ""))
            )

        entry: dict[str, Any] = {
            "provenance_tier": c_tier,
            "body": f"{delimiter}\n{c_body}\n{delimiter}\n" if should_spotlight else c_body,
        }
        if c_author:
            entry["author"] = (
                f"{delimiter}\n{c_author}\n{delimiter}\n" if should_spotlight else c_author
            )
        formatted_comments.append(entry)

    snapshot_dict: dict[str, Any] = {
        "delimiter": delimiter,
        "summary": wrapped_summary,
        "priority": wrapped_priority,
        "labels": wrapped_labels,
        "description_markdown": block_description,
    }
    if should_spotlight or raw_comments:
        snapshot_dict["actor"] = wrapped_actor
    if formatted_comments:
        snapshot_dict["comments"] = formatted_comments

    context_dict["ticket_snapshot"] = snapshot_dict

    yaml_text = yaml.dump(
        context_dict,
        Dumper=_SpotlightDumper,
        allow_unicode=True,
        sort_keys=False,
    )
    yaml_bytes = yaml_text.encode("utf-8")

    if len(yaml_bytes) > MAX_CONTEXT_BYTES:
        msg = (
            f"CONTEXT_TOO_LARGE: Rendered context size ({len(yaml_bytes)} bytes) "
            f"exceeds cap of {MAX_CONTEXT_BYTES} bytes"
        )
        raise ContextTooLargeError(msg)

    sha256 = hashlib.sha256(yaml_bytes).hexdigest()

    return RenderedContext(
        yaml_bytes=yaml_bytes,
        sha256=sha256,
        delimiter=delimiter,
        verdict_nonce=verdict_nonce,
        ephemeral_token=ephemeral_bytearray,
        allowed_mutable_fields=allowed_mutable,
        repo_context=repo_context,
        mcp_access=mcp_access,
    )
