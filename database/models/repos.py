# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Re-export of ProjectRepoBinding for backwards-compatible module naming (KB-DEVSECOPS-BUS-01)."""

from database.models.repo_binding import ProjectRepoBinding

__all__ = ["ProjectRepoBinding"]
