"""Base DeclarativeBase, custom PostgreSQL types, and StrEnums for kanban-database."""

import re
from collections.abc import Callable
from enum import StrEnum

from sqlalchemy.dialects.postgresql import ENUM as PG_ENUM
from sqlalchemy.engine.interfaces import Dialect
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.types import UserDefinedType

_LTREE_REGEX = re.compile(r"^[A-Za-z0-9_]+(\.[A-Za-z0-9_]+)*$")


class Base(DeclarativeBase):
    """DeclarativeBase for all kanban PostgreSQL entities."""


class LtreeType(UserDefinedType[str]):
    """Custom PostgreSQL LTREE type with in-tree validation (zero sqlalchemy-utils dependency)."""

    cache_ok = True

    def get_col_spec(self, **_kw: object) -> str:
        """Return the PostgreSQL column specification."""
        return "LTREE"

    def bind_processor(self, _dialect: Dialect) -> Callable[[object], str | None]:
        """Validate and bind python string to PostgreSQL ltree format."""

        def process(value: object) -> str | None:
            if value is None:
                return None
            s = str(value)
            if not _LTREE_REGEX.match(s):
                msg = f"Invalid ltree path: {s!r}"
                raise ValueError(msg)
            return s

        return process

    def result_processor(
        self, _dialect: Dialect, _coltype: object
    ) -> Callable[[object], str | None]:
        """Convert PostgreSQL ltree result to python string."""

        def process(value: object) -> str | None:
            if value is None:
                return None
            return str(value)

        return process


class ObjectKind(StrEnum):
    """PostgreSQL object_kind enum mirror."""

    ISSUE = "issue"
    STICKY = "sticky"
    DOC = "doc"
    USER = "user"
    PROJECT = "project"
    CYCLE = "cycle"
    MODULE = "module"
    VIEW = "view"
    PAGE = "page"
    SCM_ARTIFACT = "scm_artifact"


class LinkKind(StrEnum):
    """PostgreSQL link_kind enum mirror."""

    BLOCKS = "BLOCKS"
    BLOCKED_BY = "BLOCKED_BY"
    RELATES_TO = "RELATES_TO"
    DUPLICATES = "DUPLICATES"
    PARENT_OF = "PARENT_OF"
    ASSIGNED_TO = "ASSIGNED_TO"
    IN_CYCLE = "IN_CYCLE"
    IN_MODULE = "IN_MODULE"
    PROMOTED_TO_DOC = "PROMOTED_TO_DOC"
    VERIFIED_BY_DOC = "VERIFIED_BY_DOC"
    DERIVED_FROM_STICKY = "DERIVED_FROM_STICKY"
    EMBEDS_OBJECT = "EMBEDS_OBJECT"
    GOVERNED_BY_VIEW = "GOVERNED_BY_VIEW"
    IMPLEMENTED_IN_PR = "IMPLEMENTED_IN_PR"
    REFERENCED_BY_COMMIT = "REFERENCED_BY_COMMIT"
    TRACKED_ON_BRANCH = "TRACKED_ON_BRANCH"


class ViewLayout(StrEnum):
    """PostgreSQL view_layout enum mirror."""

    BOARD = "board"
    LIST = "list"
    CALENDAR = "calendar"
    TIMELINE = "timeline"
    TABLE = "table"


class RbacRole(StrEnum):
    """PostgreSQL rbac_role enum mirror."""

    SERVER_ADMIN = "SERVER_ADMIN"
    WORKSPACE_ADMIN = "WORKSPACE_ADMIN"
    WORKSPACE_MEMBER = "WORKSPACE_MEMBER"
    WORKSPACE_GUEST = "WORKSPACE_GUEST"
    PROJECT_ADMIN = "PROJECT_ADMIN"
    MEMBER = "MEMBER"
    VIEWER = "VIEWER"


class InvalidLinkReason(StrEnum):
    """PostgreSQL invalid_link_reason enum mirror."""

    DANGLING_SOURCE = "DANGLING_SOURCE"
    DANGLING_TARGET = "DANGLING_TARGET"
    SOFT_DELETED_ENDPOINT = "SOFT_DELETED_ENDPOINT"
    ARCHIVED_POLICY_VIOLATION = "ARCHIVED_POLICY_VIOLATION"
    TYPE_MATRIX_VIOLATION = "TYPE_MATRIX_VIOLATION"
    CROSS_WORKSPACE_LEAK = "CROSS_WORKSPACE_LEAK"
    PERMISSION_SEVERED = "PERMISSION_SEVERED"


# Pre-configured PG_ENUM instances bound with create_type=False and values_callable
object_kind_pg_enum = PG_ENUM(
    ObjectKind,
    name="object_kind",
    create_type=False,
    values_callable=lambda x: [e.value for e in x],
)
link_kind_pg_enum = PG_ENUM(
    LinkKind,
    name="link_kind",
    create_type=False,
    values_callable=lambda x: [e.value for e in x],
)
view_layout_pg_enum = PG_ENUM(
    ViewLayout,
    name="view_layout",
    create_type=False,
    values_callable=lambda x: [e.value for e in x],
)
rbac_role_pg_enum = PG_ENUM(
    RbacRole,
    name="rbac_role",
    create_type=False,
    values_callable=lambda x: [e.value for e in x],
)
invalid_link_reason_pg_enum = PG_ENUM(
    InvalidLinkReason,
    name="invalid_link_reason",
    create_type=False,
    values_callable=lambda x: [e.value for e in x],
)
