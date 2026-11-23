# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Re-export of ProjectRepoBinding and CommitAttestation for backwards-compatible module naming."""

from database.models.repo_binding import CommitAttestation, ProjectRepoBinding

__all__ = ["CommitAttestation", "ProjectRepoBinding"]
