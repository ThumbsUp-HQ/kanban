"""Archive service operations routing alias (S7.2 8p)."""

from __future__ import annotations

from kanban.services.issue_archive import archive_issue, unarchive_issue

__all__ = ["archive_issue", "unarchive_issue"]
