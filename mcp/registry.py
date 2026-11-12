# Copyright 2026 Kanban Platform Contributors
"""Isolated surface tool registries and specifications for MCP endpoints."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Final

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

__all__ = [
    "Surface",
    "ToolRegistry",
    "ToolSpec",
    "create_placeholder_tool",
]


class Surface(StrEnum):
    """Physically isolated MCP endpoint surfaces."""

    AGENT = "agent"
    DOCS = "docs"
    ADMIN = "admin"


@dataclass(frozen=True)
class ToolSpec:
    """Specification and invocation handler for an MCP tool."""

    name: str
    description: str
    input_schema: dict[str, Any]
    surface: Surface
    handler: Callable[[dict[str, Any]], Awaitable[Any] | Any]


class ToolRegistry:
    """Isolated, surface-bound tool registry that freezes at application startup."""

    def __init__(self, surface: Surface) -> None:
        """Initialize an independent tool registry bound to a specific surface."""
        self.surface: Final[Surface] = surface
        self._tools: dict[str, ToolSpec] = {}
        self._frozen: bool = False

    @property
    def is_frozen(self) -> bool:
        """Whether the registry has been frozen against further mutations."""
        return self._frozen

    def register(self, spec: ToolSpec) -> None:
        """Register a tool specification with surface-isolation enforcement.

        Raises:
            RuntimeError: If the registry has already been frozen.
            ValueError: If the tool spec's surface does not match this registry's surface.

        """
        if self._frozen:
            msg = (
                f"Cannot register tool '{spec.name}': "
                f"registry for surface '{self.surface.value}' is frozen"
            )
            raise RuntimeError(msg)

        if spec.surface != self.surface:
            msg = (
                f"Cannot register tool '{spec.name}': tool surface '{spec.surface.value}' "
                f"does not match registry surface '{self.surface.value}'"
            )
            raise ValueError(msg)

        self._tools[spec.name] = spec

    def freeze(self) -> None:
        """Freeze the registry against further tool additions."""
        self._frozen = True

    def get(self, name: str) -> ToolSpec | None:
        """Retrieve a registered tool specification by name."""
        return self._tools.get(name)

    def list_specs(self) -> list[ToolSpec]:
        """Return a snapshot list of all registered tool specifications."""
        return list(self._tools.values())


def create_placeholder_tool(surface: Surface) -> ToolSpec:
    """Construct standard placeholder ping tool for the given surface."""

    async def _ping_handler(_args: dict[str, Any]) -> dict[str, Any]:
        return {"ok": True, "surface": surface.value}

    return ToolSpec(
        name=f"ping_{surface.value}",
        description=f"Diagnostic ping health check for the {surface.value} surface.",
        input_schema={"type": "object", "properties": {}, "additionalProperties": False},
        surface=surface,
        handler=_ping_handler,
    )
