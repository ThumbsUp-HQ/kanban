# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Sparkle FIM completion router adapter without module layer violation (KB-P3-AUDIT-04)."""

from __future__ import annotations

import importlib

__all__ = ["SparkleRequest", "router"]  # noqa: F822


def __getattr__(name: str) -> object:
    """Dynamically resolve attributes from agent.sparkle to maintain layer boundary."""
    if name == "router":
        mod = importlib.import_module("agent.sparkle.router")
        return mod.router
    if name == "SparkleRequest":
        mod = importlib.import_module("agent.sparkle.pipeline")
        return mod.SparkleRequest
    msg = f"module {__name__!r} has no attribute {name!r}"
    raise AttributeError(msg)
