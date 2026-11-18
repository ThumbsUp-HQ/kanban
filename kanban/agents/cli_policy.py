"""Shared CLI policy module for binary allowlisting and banned-flag validation (KB-P5-16, S14.3)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING, Final, Protocol

if TYPE_CHECKING:
    from collections.abc import Sequence

    from database.models.agent_definition import AgentDefinition

BANNED_FLAGS: Final[frozenset[str]] = frozenset(
    {
        "--yolo",
        "--dangerously-bypass-approvals-and-sandbox",
        "--dangerously-skip-permissions",
        "--full-auto",
        "--allow-all-tools",
    }
)

BINARY_ALLOWLIST: Final[Mapping[str, str]] = MappingProxyType(
    {
        "agy": "/usr/local/bin/agy",
        "codex": "/usr/local/bin/codex",
        "gemini-cli": "/usr/local/bin/gemini",
        "claude-code": "/usr/local/bin/claude",
    }
)

CODEX_PINNED_PREFIX: Final[tuple[str, ...]] = ("exec", "-s", "read-only", "-")

_MAX_CLI_ARGS: Final[int] = 32
_MIN_ARG_BYTES: Final[int] = 1
_MAX_ARG_BYTES: Final[int] = 256


class CliPolicyError(ValueError):
    """Raised when CLI arguments violate safety or sandboxing policy."""

    def __init__(self, code: str, detail: str) -> None:
        """Initialize with machine-readable error code and human explanation."""
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail
        self.status = 422


@dataclass(frozen=True, slots=True)
class ValidatedArgv:
    """Immutable validated command-line argument vector for direct execve execution."""

    argv: tuple[str, ...]


class AgentRecordProtocol(Protocol):
    """Structural protocol for stored agent records containing CLI fields."""

    cli_binary_allowlist_id: str | None
    cli_args_json: object


def _validate_single_arg(index: int, arg: object) -> str:
    """Validate a single CLI argument element."""
    if not isinstance(arg, str):
        msg = f"Argument at index {index} must be a string (got {type(arg).__name__})"
        raise CliPolicyError(code="CLI_ARGS_INVALID", detail=msg)

    if "\x00" in arg or "\r" in arg or "\n" in arg:
        msg = f"Argument at index {index} contains forbidden control characters"
        raise CliPolicyError(code="CLI_ARGS_INVALID", detail=msg)

    raw_bytes = arg.encode("utf-8")
    if not (_MIN_ARG_BYTES <= len(raw_bytes) <= _MAX_ARG_BYTES):
        msg = (
            f"Argument at index {index} has byte length {len(raw_bytes)}, "
            f"must be between {_MIN_ARG_BYTES} and {_MAX_ARG_BYTES}"
        )
        raise CliPolicyError(code="CLI_ARGS_INVALID", detail=msg)

    folded = arg.casefold()
    if (
        folded in BANNED_FLAGS
        or any(folded.startswith(f"{banned}=") for banned in BANNED_FLAGS)
        or folded.startswith("--dangerously")
    ):
        msg = f"Argument at index {index} ({arg!r}) violates banned CLI flag policy"
        raise CliPolicyError(code="BANNED_CLI_FLAG", detail=msg)

    return arg


def _validate_codex_sandbox(args: list[str]) -> None:
    """Assert codex starts with pinned prefix and contains no sandbox overrides."""
    pinned_len = len(CODEX_PINNED_PREFIX)
    if len(args) < pinned_len or tuple(args[:pinned_len]) != CODEX_PINNED_PREFIX:
        msg = f"codex binary requires initial pinned arguments {list(CODEX_PINNED_PREFIX)!r}"
        raise CliPolicyError(code="CODEX_SANDBOX_OVERRIDE", detail=msg)

    for sub_index, sub_arg in enumerate(args[pinned_len:], start=pinned_len):
        sub_folded = sub_arg.casefold()
        if (
            sub_folded in ("-s", "--sandbox", "-c", "--config", "-p", "--profile")
            or sub_folded.startswith(("--sandbox=", "--config=", "--profile="))
        ):
            msg = (
                f"codex argument at index {sub_index} ({sub_arg!r}) attempts "
                "to override sandbox mode or profile"
            )
            raise CliPolicyError(code="CODEX_SANDBOX_OVERRIDE", detail=msg)


def validate_cli_args(binary_id: str, args: Sequence[str]) -> ValidatedArgv:
    """Validate CLI binary allowlist ID and argument list against sandbox policies.

    Enforces:
    - Binary allowlist membership (CLI_BINARY_NOT_ALLOWLISTED).
    - Max 32 arguments, each 1..256 UTF-8 bytes, no NUL/CR/LF (CLI_ARGS_INVALID).
    - Casefolded banned flag matching, <banned>=, and --dangerously (BANNED_CLI_FLAG).
    - Pinned ('exec', '-s', 'read-only', '-') prefix for codex, with no subsequent -s,
      --sandbox, -c, --config, -p, or --profile overrides (CODEX_SANDBOX_OVERRIDE).

    Returns ValidatedArgv containing an immutable tuple: (binary_path, *args).
    """
    if binary_id not in BINARY_ALLOWLIST:
        msg = f"Binary identifier {binary_id!r} is not in allowlist"
        raise CliPolicyError(code="CLI_BINARY_NOT_ALLOWLISTED", detail=msg)

    if len(args) > _MAX_CLI_ARGS:
        msg = f"Argument count {len(args)} exceeds maximum limit of {_MAX_CLI_ARGS}"
        raise CliPolicyError(code="CLI_ARGS_INVALID", detail=msg)

    validated_args = [_validate_single_arg(i, arg) for i, arg in enumerate(args)]

    if binary_id == "codex":
        _validate_codex_sandbox(validated_args)

    binary_path = BINARY_ALLOWLIST[binary_id]
    return ValidatedArgv(argv=(binary_path, *validated_args))


def assert_runtime_argv(
    defn: AgentDefinition | AgentRecordProtocol | Mapping[str, object],
) -> ValidatedArgv:
    """Validate stored agent definition CLI parameters immediately before process execution.

    Re-runs full validate_cli_args against the persisted record to guard against
    direct database tampering or historical rows written prior to policy updates.
    """
    binary_id: str | None
    raw_args: object

    if isinstance(defn, Mapping):
        val = defn.get("cli_binary_allowlist_id")
        binary_id = val if isinstance(val, str) else None
        raw_args = defn.get("cli_args_json")
        if raw_args is None:
            raw_args = defn.get("cli_args")
    else:
        val = getattr(defn, "cli_binary_allowlist_id", None)
        binary_id = val if isinstance(val, str) else None
        raw_args = getattr(defn, "cli_args_json", None)
        if raw_args is None:
            raw_args = getattr(defn, "cli_args", None)

    if binary_id is None:
        msg = "Agent definition has no CLI binary allowlist identifier configured"
        raise CliPolicyError(code="CLI_BINARY_NOT_ALLOWLISTED", detail=msg)

    args = [str(a) for a in raw_args] if isinstance(raw_args, (list, tuple)) else []
    return validate_cli_args(binary_id, args)
