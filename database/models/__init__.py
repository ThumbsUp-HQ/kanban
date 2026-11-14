"""Universal Object Graph SQLAlchemy 2.0 ORM models for kanban-database."""

from database.models.activity import ActivityChainHead, ActivityRecord
from database.models.agent_definition import AgentDefinition
from database.models.attachments import Attachment
from database.models.auth import (
    AuthProviderCard,
    LdapGroupMapping,
    LocalAdminCredential,
    OidcAuthRequest,
    RecoveryCode,
    TotpFactor,
    UserSession,
    WebauthnChallenge,
    WebauthnCredential,
)
from database.models.base import (
    Base,
    InvalidLinkReason,
    LinkKind,
    LtreeType,
    ObjectKind,
    RbacRole,
    ViewLayout,
)
from database.models.custom_field import CustomFieldDefinition, CustomFieldValue
from database.models.embeddings import ObjectEmbedding
from database.models.issues import (
    CommentReaction,
    Issue,
    IssueAssignee,
    IssueComment,
    IssueLabel,
    IssueModule,
    IssueSubscription,
)
from database.models.knowledge import Doc, Page, PageVersion, Sticky
from database.models.mcp_api_key import McpApiKey
from database.models.notifications import Notification
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
    "AgentDefinition",
    "Attachment",
    "AuthProviderCard",
    "Base",
    "CommentReaction",
    "CustomFieldDefinition",
    "CustomFieldValue",
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
    "LdapGroupMapping",
    "LinkKind",
    "LinkTypeMatrix",
    "LocalAdminCredential",
    "LtreeType",
    "McpApiKey",
    "Module",
    "Notification",
    "ObjectEmbedding",
    "ObjectKind",
    "ObjectLink",
    "ObjectRecord",
    "OidcAuthRequest",
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
    "RecoveryCode",
    "ResourceAclEntry",
    "RoleBinding",
    "Sticky",
    "TotpFactor",
    "User",
    "UserSession",
    "View",
    "ViewLayout",
    "WebauthnChallenge",
    "WebauthnCredential",
    "WorkflowState",
    "Workspace",
]
