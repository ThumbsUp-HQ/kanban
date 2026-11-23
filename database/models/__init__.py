"""Universal Object Graph SQLAlchemy 2.0 ORM models for kanban-database."""

from database.models.activity import ActivityChainHead, ActivityRecord
from database.models.activity_key import ActivityRecordKey
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
from database.models.destructive_token import DestructiveConfirmationToken
from database.models.embeddings import ObjectEmbedding
from database.models.import_mapping import ImportEntityMapping
from database.models.issue_alias import IssueKeyAlias
from database.models.issue_lease import IssueLease
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
from database.models.mcp_read_taint import McpReadTaint
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
    UserPreference,
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
from database.models.remote_runner import RemoteRunner, RemoteRunnerEnrollmentToken
from database.models.repo_binding import CommitAttestation, ProjectRepoBinding
from database.models.spine import (
    InvalidObjectLinkAudit,
    LinkTypeMatrix,
    ObjectLink,
    ObjectRecord,
    Workspace,
)
from database.models.wasm_module import ApprovedWasmModule
from database.models.webhooks import (
    ScmArtifact,
    ScmWebhookDelivery,
    WebhookDelivery,
    WebhookSubscription,
)
from database.models.workflow import (
    WorkflowHookInvocation,
    WorkflowTransitionExecution,
    WorkflowTransitionHook,
)
from database.models.workload_identity import (
    WorkloadIdentityPolicy,
    WorkloadJtiReplay,
)
from database.models.workspace_settings import WorkspaceSettings

__all__ = [
    "AIProviderConfig",
    "AITokenLedger",
    "ActivityChainHead",
    "ActivityRecord",
    "ActivityRecordKey",
    "AgentDefinition",
    "ApprovedWasmModule",
    "Attachment",
    "AuthProviderCard",
    "Base",
    "CommentReaction",
    "CommitAttestation",
    "CustomFieldApproval",
    "CustomFieldDefinition",
    "CustomFieldValue",
    "Cycle",
    "DestructiveConfirmationToken",
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
    "IssueKeyAlias",
    "IssueLabel",
    "IssueLease",
    "IssueModule",
    "IssueSubscription",
    "LdapGroupMapping",
    "LinkKind",
    "LinkTypeMatrix",
    "LocalAdminCredential",
    "LtreeType",
    "McpApiKey",
    "McpEphemeralToken",
    "McpReadTaint",
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
    "ProjectRepoBinding",
    "RateLimitBucket",
    "RbacRole",
    "RecoveryCode",
    "RemoteRunner",
    "RemoteRunnerEnrollmentToken",
    "ResourceAclEntry",
    "RoleBinding",
    "ScmArtifact",
    "ScmWebhookDelivery",
    "SetupClaimToken",
    "Sticky",
    "TotpFactor",
    "User",
    "UserIdentity",
    "UserPreference",
    "UserSession",
    "View",
    "ViewLayout",
    "WebauthnChallenge",
    "WebauthnCredential",
    "WebhookDelivery",
    "WebhookSubscription",
    "WorkflowHookInvocation",
    "WorkflowState",
    "WorkflowTransitionExecution",
    "WorkflowTransitionHook",
    "WorkloadIdentityPolicy",
    "WorkloadJtiReplay",
    "Workspace",
    "WorkspaceSettings",
]
