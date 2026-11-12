# Copyright 2026 Kanban Platform Contributors
"""Entity resolution service re-exports."""

from __future__ import annotations

from kanban.resolve.service import (
    KindProvider,
    ResolutionService,
    ResolvedRef,
)

__all__ = [
    "KindProvider",
    "ResolutionService",
    "ResolvedRef",
]
