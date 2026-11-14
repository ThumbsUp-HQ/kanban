"""Universal Object Graph SQLAlchemy 2.0 ORM models for kanban-database."""

from database.models.activity import ActivityChainHead, ActivityRecord
from database.models.agent_definition import AgentDefinition
from database.models.ai import AIProviderConfig, AITokenLedger
from database.models.attachments import Attachment
from database.models.auth import (
    AuthProviderCard,
    IdentityLinkIntent,
    LdapGroupMapping,
    LocalAdminCredential,
    OidcAuthRequest,
    RecoveryCode,
    SetupClaimToken,
    TotpFactor,
    UserIdentity,
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
from database.models.custom_field_approval import CustomFieldApproval
from database.models.embeddings import ObjectEmbedding
from database.models.import_mapping import ImportEntityMapping
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
from database.models.mcp_ephemeral_token import McpEphemeralToken
from database.models.notifications import Notification
from database.models.oauth import (
    OAuthAuthorizationCode,
    OAuthClient,
    OAuthDeviceCode,
    OAuthGrant,
    OAuthRefreshToken,
    OAuthRevokedJti,
)
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
from database.models.workspace_settings import WorkspaceSettings

__all__ = [
    "AIProviderConfig",
    "AITokenLedger",
    "ActivityChainHead",
    "ActivityRecord",
    "AgentDefinition",
    "Attachment",
    "AuthProviderCard",
    "Base",
    "CommentReaction",
    "CustomFieldApproval",
    "CustomFieldDefinition",
    "CustomFieldValue",
    "Cycle",
    "Doc",
    "EffectiveResourceAccess",
    "Group",
    "IdentityLinkIntent",
    "ImportEntityMapping",
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
    "McpEphemeralToken",
    "Module",
    "Notification",
    "OAuthAuthorizationCode",
    "OAuthClient",
    "OAuthDeviceCode",
    "OAuthGrant",
    "OAuthRefreshToken",
    "OAuthRevokedJti",
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
    "SetupClaimToken",
    "Sticky",
    "TotpFactor",
    "User",
    "UserIdentity",
    "UserSession",
    "View",
    "ViewLayout",
    "WebauthnChallenge",
    "WebauthnCredential",
    "WorkflowState",
    "Workspace",
    "WorkspaceSettings",
]
