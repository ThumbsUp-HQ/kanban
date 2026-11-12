"""Universal Object Graph SQLAlchemy 2.0 ORM models for kanban-database."""

from database.models.activity import ActivityChainHead, ActivityRecord
from database.models.attachments import Attachment
from database.models.auth import AuthProviderCard, UserSession
from database.models.base import (
    Base,
    InvalidLinkReason,
    LinkKind,
    LtreeType,
    ObjectKind,
    RbacRole,
    ViewLayout,
)
from database.models.embeddings import ObjectEmbedding
from database.models.issues import (
    Issue,
    IssueAssignee,
    IssueComment,
    IssueLabel,
    IssueModule,
    IssueSubscription,
)
from database.models.knowledge import Doc, Page, PageVersion, Sticky
from database.models.outbox import OutboxEvent
from database.models.principals import (
    EffectiveResourceAccess,
    Group,
    Principal,
    PrincipalGroupClosure,
    PrincipalGroupEdge,
    ResourceAclEntry,
    RoleBinding,
    User,
)
from database.models.projects import (
    Cycle,
    Module,
    Project,
    ProjectLabel,
    ProjectModuleDefault,
    ProjectPriority,
    View,
    WorkflowState,
)
from database.models.ratelimit import RateLimitBucket
from database.models.spine import (
    InvalidObjectLinkAudit,
    LinkTypeMatrix,
    ObjectLink,
    ObjectRecord,
    Workspace,
)

__all__ = [
    "ActivityChainHead",
    "ActivityRecord",
    "Attachment",
    "AuthProviderCard",
    "Base",
    "Cycle",
    "Doc",
    "EffectiveResourceAccess",
    "Group",
    "InvalidLinkReason",
    "InvalidObjectLinkAudit",
    "Issue",
    "IssueAssignee",
    "IssueComment",
    "IssueLabel",
    "IssueModule",
    "IssueSubscription",
    "LinkKind",
    "LinkTypeMatrix",
    "LtreeType",
    "Module",
    "ObjectEmbedding",
    "ObjectKind",
    "ObjectLink",
    "ObjectRecord",
    "OutboxEvent",
    "Page",
    "PageVersion",
    "Principal",
    "PrincipalGroupClosure",
    "PrincipalGroupEdge",
    "Project",
    "ProjectLabel",
    "ProjectModuleDefault",
    "ProjectPriority",
    "RateLimitBucket",
    "RbacRole",
    "ResourceAclEntry",
    "RoleBinding",
    "Sticky",
    "User",
    "UserSession",
    "View",
    "ViewLayout",
    "WorkflowState",
    "Workspace",
]
