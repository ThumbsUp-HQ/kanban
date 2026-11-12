"""Archive API routing alias for issue archive operations."""

from __future__ import annotations

from kanban.api.v1.issue_archive import archive_issue, router, unarchive_issue

__all__ = ["archive_issue", "router", "unarchive_issue"]
