# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Kanban API middleware package."""

from __future__ import annotations

from kanban.api.middleware.script_depth import ScriptDepthGuardMiddleware

__all__ = [
    "ScriptDepthGuardMiddleware",
]
