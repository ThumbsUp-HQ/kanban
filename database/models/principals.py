"""Principal models: principals, users, groups, edges, closure, role_bindings, ACLs."""

import uuid
from datetime import datetime

from sqlalchemy import (
    Computed,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    LargeBinary,
    SmallInteger,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from database.models.base import (
    Base,
    ObjectKind,
    RbacRole,
    object_kind_pg_enum,
    rbac_role_pg_enum,
)


class Principal(Base):
    """Unified security principal identity (USER, GROUP, SERVICE_PRINCIPAL, AGENT)."""

    __tablename__ = "principals"
    __table_args__ = (
        UniqueConstraint("id", "principal_type", name="principals_id_principal_type_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=text("uuidv7()"))
    principal_type: Mapped[str] = mapped_column(String, nullable=False)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[str] = mapped_column(String, nullable=False, server_default=text("'ACTIVE'"))
    display_name: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )


class User(Base):
    """First-class human or system user principal."""

    __tablename__ = "users"
    __table_args__ = (
        ForeignKeyConstraint(
            ["id", "object_type"],
            ["objects.id", "objects.object_type"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["id", "principal_type"],
            ["principals.id", "principals.principal_type"],
            ondelete="RESTRICT",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    object_type: Mapped[ObjectKind] = mapped_column(
        object_kind_pg_enum, nullable=False, server_default=text("'user'")
    )
    principal_type: Mapped[str] = mapped_column(
        String, nullable=False, server_default=text("'USER'")
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="RESTRICT"), nullable=False
    )
    email: Mapped[str] = mapped_column(String, nullable=False)


class Group(Base):
    """Principal group for authorization and membership aggregation."""

    __tablename__ = "groups"
    __table_args__ = (
        ForeignKeyConstraint(
            ["id", "principal_type"],
            ["principals.id", "principals.principal_type"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("workspace_id", "name", name="groups_workspace_id_name_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    principal_type: Mapped[str] = mapped_column(
        String, nullable=False, server_default=text("'GROUP'")
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="RESTRICT"), nullable=False
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    external_source: Mapped[str | None] = mapped_column(String, nullable=True)
    external_id: Mapped[str | None] = mapped_column(String, nullable=True)


class PrincipalGroupEdge(Base):
    """Direct membership edge between a principal and a group."""

    __tablename__ = "principal_group_edges"

    member_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("principals.id", ondelete="CASCADE"), primary_key=True
    )
    group_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("groups.id", ondelete="CASCADE"), primary_key=True
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )


class PrincipalGroupClosure(Base):
    """Transitive closure table maintaining full group membership hierarchy."""

    __tablename__ = "principal_group_closure"

    member_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("principals.id", ondelete="CASCADE"), primary_key=True
    )
    ancestor_group_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("groups.id", ondelete="CASCADE"), primary_key=True
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="RESTRICT"), nullable=False
    )
    depth: Mapped[int] = mapped_column(SmallInteger, nullable=False)


class RoleBinding(Base):
    """Scoped RBAC role binding at SERVER, WORKSPACE, or PROJECT level."""

    __tablename__ = "role_bindings"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "principal_id",
            "role",
            "scope_type",
            "project_id",
            name="role_bindings_workspace_id_principal_id_role_scope_type_pro_key",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=text("uuidv7()"))
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="RESTRICT"), nullable=False
    )
    principal_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("principals.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[RbacRole] = mapped_column(rbac_role_pg_enum, nullable=False)
    scope_type: Mapped[str] = mapped_column(String, nullable=False)
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )


class ResourceAclEntry(Base):
    """Object-level access control entry with bitmask capabilities."""

    __tablename__ = "resource_acl_entries"
    __table_args__ = (
        UniqueConstraint(
            "object_id",
            "principal_id",
            "effect",
            name="resource_acl_entries_object_id_principal_id_effect_key",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=text("uuidv7()"))
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="RESTRICT"), nullable=False
    )
    object_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("objects.id", ondelete="CASCADE"), nullable=False
    )
    principal_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("principals.id", ondelete="CASCADE"), nullable=False
    )
    effect: Mapped[str] = mapped_column(String, nullable=False)
    capability_mask: Mapped[int] = mapped_column(Integer, nullable=False)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("principals.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )


class EffectiveResourceAccess(Base):
    """Materialized access closure calculating effective bitmask per (object, principal)."""

    __tablename__ = "effective_resource_access"

    object_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    principal_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="RESTRICT"), nullable=False
    )
    allow_mask: Mapped[int] = mapped_column(Integer, nullable=False)
    deny_mask: Mapped[int] = mapped_column(Integer, nullable=False)
    effective_mask: Mapped[int | None] = mapped_column(
        Computed("allow_mask & (~deny_mask)", persisted=True), nullable=True
    )


class UserPreference(Base):
    """Per-user settings and preferences (timezone, avatar metadata)."""

    __tablename__ = "user_preferences"

    principal_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("principals.id", ondelete="CASCADE"), primary_key=True
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    timezone: Mapped[str] = mapped_column(String, nullable=False, server_default=text("'UTC'"))
    avatar_storage_key: Mapped[str | None] = mapped_column(String, nullable=True)
    avatar_content_type: Mapped[str | None] = mapped_column(String, nullable=True)
    avatar_sha256: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )
