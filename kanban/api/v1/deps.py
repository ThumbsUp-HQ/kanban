# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""API v1 route dependencies and feature-flag gates (KB-P3-10b)."""

from __future__ import annotations

from kanban.services.modules import require_modules_enabled

__all__ = ["require_modules_enabled"]
