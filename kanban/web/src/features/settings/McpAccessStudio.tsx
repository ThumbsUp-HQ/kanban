// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import React, { useState, useEffect, useCallback, type JSX } from 'react';
import { useParams, useSearchParams, Link } from 'react-router';
import {
  fetchPersonalMcpKeys,
  mintPersonalMcpKey,
  revokePersonalMcpKey,
  fetchConnectedApps,
  revokeConnectedApp,
  fetchUnifiedMcpKeys,
  type McpApiKeyItem,
  type OAuthConnectedApp,
  type ScopeTier,
} from './settingsApi';
import { McpConfigSnippetModal } from './McpConfigSnippetModal';
import { SecondFactorStep } from '../auth/SecondFactorStep';
import type { MfaMethod } from '../auth/authApi';
import { ApiProblem } from '../../api/problem';
import { EmojiHint } from '../../components/emoji/EmojiHint';
import { useSystemStatus } from '../../app/useSystemStatus';
import { apiFetch } from '../../api/client';
import { NotFoundView } from '../../app/routes';
import './McpAccessStudio.css';

export const SURFACE_TOOLS: Record<'agent' | 'docs' | 'admin', readonly string[]> = {
  agent: [
    'ping_agent',
    'search_tickets',
    'read_ticket',
    'create_ticket',
    'update_ticket',
    'begin_work',
    'transition_ticket',
    'complete_work',
    'add_comment',
    'link_objects',
  ],
  docs: [
    'ping_docs',
    'search_docs',
    'search_knowledge',
    'read_doc',
    'create_doc',
    'update_doc',
    'upsert_doc',
    'manage_stickies',
    'promote_sticky_to_doc',
    'link_knowledge',
  ],
  admin: [
    'manage_principals_and_groups',
    'manage_access_policies',
    'audit_links',
    'override_ticket_provenance',
    'audit_and_purge_object_links',
    'manage_ai_and_agent_runners',
    'destructive_lifecycle',
  ],
};

export const WRITE_MCP_TOOLS = new Set([
  'create_ticket',
  'update_ticket',
  'begin_work',
  'transition_ticket',
  'complete_work',
  'link_objects',
  'create_doc',
  'update_doc',
  'upsert_doc',
  'manage_stickies',
  'promote_sticky_to_doc',
  'link_knowledge',
  'manage_principals_and_groups',
  'manage_access_policies',
  'audit_links',
  'override_ticket_provenance',
  'audit_and_purge_object_links',
  'manage_ai_and_agent_runners',
  'destructive_lifecycle',
]);

export type ActiveScopeFilter = 'all' | 'project' | 'workspace' | 'server';
export type ActiveView = 'mine' | 'governance';

export interface McpAccessStudioProps {
  tier?: ('personal' | 'project' | 'workspace' | 'global') | undefined;
  allowUnlimitedKeys?: boolean | undefined;
  user?: {
    is_server_admin?: boolean;
    is_workspace_admin?: boolean;
    is_project_admin?: boolean;
    workspace_role?: string;
  } | null | undefined;
}

export function McpAccessStudio({
  tier,
  allowUnlimitedKeys,
  user: propUser,
}: McpAccessStudioProps): JSX.Element {
  const [searchParams, setSearchParams] = useSearchParams();
  const routeParams = useParams<{ projectKey?: string }>();

  // Determine initial scope filter from props or query
  const queryScope = searchParams.get('scope');
  const queryProject = searchParams.get('project');
  const queryView = searchParams.get('view');

  const resolvedInitialScope: ActiveScopeFilter = (() => {
    if (tier === 'global') return 'server';
    if (tier === 'workspace') return 'workspace';
    if (tier === 'project') return 'project';
    if (queryScope === 'server' || queryScope === 'global') return 'server';
    if (queryScope === 'workspace') return 'workspace';
    if (queryScope === 'project') return 'project';
    return 'all';
  })();

  const [activeScope, setActiveScope] = useState<ActiveScopeFilter>(resolvedInitialScope);
  const [selectedProject, setSelectedProject] = useState<string>(
    queryProject ?? routeParams.projectKey ?? 'KANBA',
  );
  const [activeView, setActiveView] = useState<ActiveView>(
    queryView === 'governance' ? 'governance' : 'mine',
  );

  const [fetchedUser, setFetchedUser] = useState<{
    is_server_admin?: boolean;
    is_workspace_admin?: boolean;
    is_project_admin?: boolean;
    workspace_role?: string;
  } | null>(null);

  useEffect(() => {
    if (propUser !== undefined) return;
    const isMounted = { current: true };
    void (async () => {
      try {
        const u = (await apiFetch('GET', '/api/v1/auth/me')) as {
          is_server_admin?: boolean;
          is_workspace_admin?: boolean;
          is_project_admin?: boolean;
          workspace_role?: string;
        };
        if (isMounted.current) setFetchedUser(u);
      } catch {
        // Unmocked in unit test
      }
    })();
    return () => {
      isMounted.current = false;
    };
  }, [propUser]);

  const currentUser = propUser ?? fetchedUser;
  const isServerAdmin = currentUser?.is_server_admin === true;
  const isWorkspaceAdmin = currentUser?.is_workspace_admin === true || isServerAdmin;
  const isProjectAdmin = currentUser?.is_project_admin === true || isWorkspaceAdmin;
  const canAccessGovernance = isServerAdmin || isWorkspaceAdmin || isProjectAdmin;
  const isViewer =
    currentUser?.workspace_role === 'VIEWER' || currentUser?.workspace_role === 'WORKSPACE_GUEST';

  const systemStatusQuery = useSystemStatus();
  const allowUnlimited =
    allowUnlimitedKeys ?? systemStatusQuery.data?.allow_unlimited_mcp_keys ?? true;

  const effectiveProjectKey = selectedProject;

  const [keys, setKeys] = useState<McpApiKeyItem[]>([]);
  const [connectedApps, setConnectedApps] = useState<OAuthConnectedApp[]>([]);
  const [loading, setLoading] = useState<boolean>(true);

  // Mint modal state
  const [showMintModal, setShowMintModal] = useState<boolean>(false);
  const [newKeyLabel, setNewKeyLabel] = useState<string>('');
  const [newKeySurface, setNewKeySurface] = useState<'agent' | 'docs' | 'admin'>('agent');
  const [newKeyScopeTier, setNewKeyScopeTier] = useState<ScopeTier>(
    activeScope === 'server' ? 'global' : activeScope === 'project' ? 'project' : 'workspace',
  );
  const [newKeyProject, setNewKeyProject] = useState<string>(effectiveProjectKey);
  const [newKeyExpiry, setNewKeyExpiry] = useState<number>(60);
  const [isUnlimited, setIsUnlimited] = useState<boolean>(false);
  const [confirmUnlimited, setConfirmUnlimited] = useState<boolean>(false);
  const [disabledTools, setDisabledTools] = useState<string[]>([]);
  const [minting, setMinting] = useState<boolean>(false);
  const [mintError, setMintError] = useState<string | null>(null);

  // Snippet modal state (ephemeral secret)
  const [activeSnippetKey, setActiveSnippetKey] = useState<string | undefined>(undefined);
  const [showSnippetModal, setShowSnippetModal] = useState<boolean>(false);

  // 2-step inline revocation confirmation states
  const [confirmRevokeKeyId, setConfirmRevokeKeyId] = useState<string | null>(null);
  const [confirmRevokeAppId, setConfirmRevokeAppId] = useState<string | null>(null);

  // Inline AAL2 challenge state
  const [aal2Challenge, setAal2Challenge] = useState<{
    challengeId: string;
    methods: MfaMethod[];
  } | null>(null);
  const [pendingAction, setPendingAction] = useState<(() => Promise<void>) | null>(null);

  const loadData = useCallback(async (): Promise<void> => {
    setLoading(true);
    try {
      if (activeView === 'governance') {
        const fetched = await fetchUnifiedMcpKeys({
          view: 'governance',
          scope_tier: activeScope !== 'all' ? activeScope : undefined,
          project_ref: activeScope === 'project' ? effectiveProjectKey : undefined,
        });
        setKeys(fetched);
        setConnectedApps([]);
      } else {
        const [fetchedKeys, fetchedApps] = await Promise.all([
          tier === 'global' ? fetchPersonalMcpKeys('global') : fetchPersonalMcpKeys(),
          fetchConnectedApps(),
        ]);
        setKeys(fetchedKeys);
        setConnectedApps(fetchedApps);
      }
    } catch (err: unknown) {
      if (err instanceof ApiProblem && (err.code === 'AAL2_REQUIRED' || err.code === 'AAL2_STALE')) {
        const data = err.data;
        const challengeId = typeof data.challenge_id === 'string' ? data.challenge_id : 'aal2-stepup';
        const methods = Array.isArray(data.methods)
          ? (data.methods as MfaMethod[])
          : (['webauthn', 'totp'] as MfaMethod[]);
        setAal2Challenge({ challengeId, methods });
        setPendingAction(() => async () => {
          await loadData();
        });
      }
    } finally {
      setLoading(false);
    }
  }, [activeView, activeScope, effectiveProjectKey, tier]);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  const handleScopeFilterChange = (newScope: ActiveScopeFilter): void => {
    setActiveScope(newScope);
    setSearchParams((prev) => {
      const updated = new URLSearchParams(prev);
      if (newScope === 'all') {
        updated.delete('scope');
      } else {
        updated.set('scope', newScope);
      }
      return updated;
    });
  };

  const handleProjectSelectChange = (newProject: string): void => {
    setSelectedProject(newProject);
    setSearchParams((prev) => {
      const updated = new URLSearchParams(prev);
      updated.set('project', newProject);
      return updated;
    });
  };

  const handleViewToggle = (newView: ActiveView): void => {
    setActiveView(newView);
    setSearchParams((prev) => {
      const updated = new URLSearchParams(prev);
      if (newView === 'governance') {
        updated.set('view', 'governance');
      } else {
        updated.delete('view');
      }
      return updated;
    });
  };

  const handleOpenMintModal = (): void => {
    let initialTier: ScopeTier = 'workspace';
    if (activeScope === 'server' || tier === 'global') {
      initialTier = 'global';
    } else if (activeScope === 'project' || tier === 'project') {
      initialTier = 'project';
    } else if (activeScope === 'workspace' || tier === 'workspace') {
      initialTier = 'workspace';
    } else {
      initialTier = 'workspace';
    }
    setNewKeyScopeTier(initialTier);
    setNewKeyProject(effectiveProjectKey);
    setShowMintModal(true);
  };

  const handleMintSubmit = async (e: React.SyntheticEvent): Promise<void> => {
    e.preventDefault();
    if (!newKeyLabel.trim()) {
      return;
    }
    if (isUnlimited && !confirmUnlimited) {
      return;
    }
    setMinting(true);
    setMintError(null);

    const mintAction = async (): Promise<void> => {
      const resolvedScopeTier: ScopeTier =
        tier === 'global' ? 'global' : tier === 'project' ? 'project' : newKeyScopeTier;

      const payload = {
        label: newKeyLabel.trim(),
        surface: newKeySurface,
        scopes: [`${newKeySurface}:read`, `${newKeySurface}:write`],
        scope_tier: resolvedScopeTier,
        ...(resolvedScopeTier === 'project'
          ? { allowed_projects: [newKeyProject.trim() ? newKeyProject.trim() : effectiveProjectKey] }
          : {}),
        ...(isUnlimited
          ? { unlimited: true, confirm_unlimited: confirmUnlimited }
          : { expires_in_days: newKeyExpiry }),
        ...(disabledTools.length > 0 ? { disabled_tools: disabledTools } : {}),
      };

      const minted = await mintPersonalMcpKey(payload);

      setKeys((prev) => [minted, ...prev]);
      setActiveSnippetKey(minted.raw_key);
      setShowMintModal(false);
      setShowSnippetModal(true);
      setNewKeyLabel('');
      setIsUnlimited(false);
      setConfirmUnlimited(false);
      setDisabledTools([]);
      setNewKeyExpiry(60);
      setMintError(null);
    };

    try {
      await mintAction();
    } catch (err: unknown) {
      if (err instanceof ApiProblem && (err.code === 'AAL2_REQUIRED' || err.code === 'AAL2_STALE')) {
        const data = err.data;
        const challengeId = typeof data.challenge_id === 'string' ? data.challenge_id : 'aal2-stepup';
        const methods = Array.isArray(data.methods)
          ? (data.methods as MfaMethod[])
          : (['webauthn', 'totp'] as MfaMethod[]);
        setAal2Challenge({ challengeId, methods });
        setPendingAction(() => async () => {
          await mintAction();
        });
        return;
      }
      if (err instanceof Error) {
        setMintError(err.message);
      } else {
        setMintError('Failed to mint MCP key.');
      }
    } finally {
      setMinting(false);
    }
  };

  const handleConfirmRevokeKey = async (keyId: string): Promise<void> => {
    const revokeAction = async (): Promise<void> => {
      if (tier === 'global') {
        await revokePersonalMcpKey(keyId, 'global');
      } else {
        await revokePersonalMcpKey(keyId);
      }
      setKeys((prev) =>
        prev.map((k) => (k.id === keyId ? { ...k, revoked_at: new Date().toISOString() } : k)),
      );
    };

    try {
      await revokeAction();
    } catch (err: unknown) {
      if (err instanceof ApiProblem && (err.code === 'AAL2_REQUIRED' || err.code === 'AAL2_STALE')) {
        const data = err.data;
        const challengeId = typeof data.challenge_id === 'string' ? data.challenge_id : 'aal2-stepup';
        const methods = Array.isArray(data.methods)
          ? (data.methods as MfaMethod[])
          : (['webauthn', 'totp'] as MfaMethod[]);
        setAal2Challenge({ challengeId, methods });
        setPendingAction(() => async () => {
          await revokeAction();
        });
        return;
      }
    } finally {
      setConfirmRevokeKeyId(null);
    }
  };

  const handleConfirmRevokeApp = async (grantId: string): Promise<void> => {
    try {
      await revokeConnectedApp(grantId);
      setConnectedApps((prev) => prev.filter((app) => app.id !== grantId));
    } catch {
      // Handle error
    } finally {
      setConfirmRevokeAppId(null);
    }
  };

  const handleAal2Success = async (): Promise<void> => {
    const action = pendingAction;
    setAal2Challenge(null);
    setPendingAction(null);
    if (action) {
      await action();
    }
  };

  const getTierBadge = (
    keyTier: ScopeTier,
    allowedProjects?: string[] | null,
  ): JSX.Element => {
    if (keyTier === 'global') {
      return (
        <span className="kb-mcp-tier-badge kb-mcp-tier-global" data-testid="tier-badge-global">
          <EmojiHint kind="access" /> Global
        </span>
      );
    }
    if (keyTier === 'workspace') {
      return (
        <span className="kb-mcp-tier-badge kb-mcp-tier-workspace" data-testid="tier-badge-workspace">
          <EmojiHint kind="access" /> Workspace: kanban
        </span>
      );
    }
    if (keyTier === 'project') {
      const projLabel =
        allowedProjects && allowedProjects.length > 0
          ? allowedProjects.join(', ')
          : effectiveProjectKey;
      return (
        <span className="kb-mcp-tier-badge kb-mcp-tier-project" data-testid="tier-badge-project">
          <EmojiHint kind="access" /> Project: {projLabel}
        </span>
      );
    }
    return (
      <span className="kb-mcp-tier-badge kb-mcp-tier-personal" data-testid="tier-badge-personal">
        <EmojiHint kind="access" /> Personal
      </span>
    );
  };

  const titleForTier: Record<string, string> = {
    personal: 'Personal MCP Keys & Connected Apps',
    project: `Project (${effectiveProjectKey}) MCP Bot Keys`,
    workspace: 'Workspace MCP Bot Keys & Client Approvals',
    global: 'Global Cross-Workspace Bot Keys (meatloaf-bot)',
  };

  const displayedTitle =
    activeView === 'governance'
      ? 'MCP Key Governance (All Scoped Keys)'
      : (tier ? titleForTier[tier] : 'Personal MCP Keys & Connected Apps');

  // Filter keys for display based on activeScope when in 'mine' view
  const displayedKeys = keys.filter((k) => {
    if (activeView === 'governance') return true;
    if (activeScope === 'all') return true;
    if (activeScope === 'project') {
      if (k.scope_tier !== 'project') return false;
      if (effectiveProjectKey && k.allowed_projects && k.allowed_projects.length > 0) {
        return k.allowed_projects.includes(effectiveProjectKey);
      }
      return true;
    }
    if (activeScope === 'workspace') {
      return k.scope_tier === 'workspace';
    }
    return k.scope_tier === 'global';
  });

  if (currentUser !== null) {
    if (tier === 'global' && !isServerAdmin) {
      return <NotFoundView />;
    }
    if (tier === 'workspace' && !isWorkspaceAdmin) {
      return <NotFoundView />;
    }
  }

  return (
    <div className="kb-mcp-studio-container" data-testid="mcp-access-studio">
      <header className="kb-mcp-studio-header">
        <div>
          <h1 className="kb-mcp-studio-title" data-testid="studio-title">{displayedTitle}</h1>
          <p className="kb-mcp-studio-subtitle">
            Mint and manage Model Context Protocol API keys with explicit scope tiers and one-click revocation.
          </p>
        </div>
        <button
          type="button"
          className="kb-mcp-studio-mint-btn"
          data-testid="mint-key-button"
          onClick={handleOpenMintModal}
        >
          + Mint MCP Key
        </button>
      </header>

      {/* Admin subnav for global tier */}
      {tier === 'global' && (
        <nav className="kb-mcp-admin-subnav" aria-label="Admin MCP and Governance Navigation">
          <Link
            to="/admin/mcp"
            className="kb-mcp-admin-subnav-link kb-mcp-admin-subnav-active"
            data-testid="tab-admin-mcp"
          >
            Bot API Keys
          </Link>
          <Link
            to="/admin/oauth"
            className="kb-mcp-admin-subnav-link"
            data-testid="tab-admin-oauth"
          >
            OAuth 2.1 Clients
          </Link>
          <Link
            to="/admin/imports"
            className="kb-mcp-admin-subnav-link"
            data-testid="tab-admin-imports"
          >
            Plane Migration Studio
          </Link>
        </nav>
      )}

      {/* Admin View Switch (My Keys vs Governance) */}
      {canAccessGovernance && (
        <div className="kb-mcp-view-toggle" data-testid="admin-view-toggle">
          <button
            type="button"
            className={`kb-mcp-view-btn ${activeView === 'mine' ? 'kb-mcp-view-btn-active' : ''}`}
            data-testid="view-mine-btn"
            onClick={() => {
              handleViewToggle('mine');
            }}
          >
            My Keys & Connected Apps
          </button>
          <button
            type="button"
            className={`kb-mcp-view-btn ${activeView === 'governance' ? 'kb-mcp-view-btn-active' : ''}`}
            data-testid="view-governance-btn"
            onClick={() => {
              handleViewToggle('governance');
            }}
          >
            Governance (All Scoped Keys)
          </button>
        </div>
      )}

      {/* Explanatory Architecture Card */}
      <div className="kb-mcp-explainer-card" data-testid="mcp-scope-explainer">
        <div className="kb-mcp-explainer-item">
          <strong>Personal Keys vs Service Bot Keys:</strong> Personal keys act on your behalf across permitted surfaces, while Service Bot keys provide dedicated automation identities tied to project, workspace, or server scopes.
        </div>
        <div className="kb-mcp-explainer-item">
          <strong>Scope Tiers:</strong> Project keys are confined to tickets and docs in designated projects. Workspace keys cover all projects in this workspace. Server keys have system-wide privileges for administrative orchestration.
        </div>
      </div>

      {/* Scope Filter Pills & Project Selector */}
      <div className="kb-mcp-filter-bar" data-testid="mcp-filter-bar">
        <div className="kb-mcp-pills-group" data-testid="mcp-pills-group">
          <button
            type="button"
            className={`kb-mcp-filter-pill ${activeScope === 'all' ? 'kb-mcp-filter-pill-active' : ''}`}
            data-testid="scope-pill-all"
            onClick={() => {
              handleScopeFilterChange('all');
            }}
          >
            All
          </button>
          <button
            type="button"
            className={`kb-mcp-filter-pill ${activeScope === 'project' ? 'kb-mcp-filter-pill-active' : ''}`}
            data-testid="scope-pill-project"
            onClick={() => {
              handleScopeFilterChange('project');
            }}
          >
            Project
          </button>
          <button
            type="button"
            className={`kb-mcp-filter-pill ${activeScope === 'workspace' ? 'kb-mcp-filter-pill-active' : ''}`}
            data-testid="scope-pill-workspace"
            onClick={() => {
              handleScopeFilterChange('workspace');
            }}
          >
            Workspace
          </button>
          <button
            type="button"
            className={`kb-mcp-filter-pill ${activeScope === 'server' ? 'kb-mcp-filter-pill-active' : ''}`}
            data-testid="scope-pill-server"
            onClick={() => {
              handleScopeFilterChange('server');
            }}
          >
            Server
          </button>
        </div>

        {activeScope === 'project' && (
          <div className="kb-mcp-project-selector" data-testid="scope-project-container">
            <label htmlFor="scope-project-select">Target Project:</label>
            <select
              id="scope-project-select"
              className="kb-mcp-form-select"
              data-testid="scope-project-select"
              value={effectiveProjectKey}
              onChange={(e) => {
                handleProjectSelectChange(e.target.value);
              }}
            >
              <option value="KANBA">KANBA</option>
              <option value="QAADM">QAADM</option>
              {effectiveProjectKey !== 'KANBA' && effectiveProjectKey !== 'QAADM' && (
                <option value={effectiveProjectKey}>{effectiveProjectKey}</option>
              )}
            </select>
          </div>
        )}
      </div>

      {/* MCP Keys Table Section */}
      <section className="kb-mcp-studio-section" data-testid="mcp-keys-section">
        <h2 className="kb-mcp-section-title">
          <EmojiHint kind="agent" /> {activeView === 'governance' ? 'Governance Scoped Keys' : 'Active MCP Keys'}
        </h2>
        <div className="kb-mcp-table-wrap">
          <table className="kb-mcp-table" data-testid="mcp-keys-table">
            <thead>
              <tr>
                <th className="kb-mcp-th">Label</th>
                <th className="kb-mcp-th">Key Hint</th>
                <th className="kb-mcp-th">Scope Tier</th>
                <th className="kb-mcp-th">Surface</th>
                <th className="kb-mcp-th">Expires</th>
                <th className="kb-mcp-th">Status</th>
                <th className="kb-mcp-th">Actions</th>
              </tr>
            </thead>
            <tbody>
              {displayedKeys.length === 0 && !loading && (
                <tr>
                  <td colSpan={7} className="kb-mcp-empty-state">
                    No active MCP keys configured. Click "+ Mint MCP Key" to create one.
                  </td>
                </tr>
              )}
              {displayedKeys.map((k) => {
                const isRevoked = Boolean(k.revoked_at);
                const isConfirming = confirmRevokeKeyId === k.id;
                const prefix = k.surface === 'agent' ? 'kb_agt_' : k.surface === 'docs' ? 'kb_doc_' : 'kb_adm_';

                return (
                  <tr key={k.id} className="kb-mcp-tr" data-testid={`key-row-${k.id}`}>
                    <td className="kb-mcp-td">
                      <span className={isRevoked ? 'kb-mcp-status-revoked' : ''}>{k.label}</span>
                    </td>
                    <td className="kb-mcp-td">
                      <code className="kb-mcp-key-hint" data-testid={`key-hint-${k.id}`}>
                        {prefix}...{k.display_hint}
                      </code>
                    </td>
                    <td className="kb-mcp-td">{getTierBadge(k.scope_tier, k.allowed_projects)}</td>
                    <td className="kb-mcp-td">{((k.surface as string | undefined) ?? '').toUpperCase()}</td>
                    <td className="kb-mcp-td" data-testid={`key-expires-${k.id}`}>
                      {k.expires_at ? (
                        new Date(k.expires_at).toLocaleDateString()
                      ) : (
                        <span className="kb-mcp-unlimited-pill" data-testid={`key-unlimited-${k.id}`}>
                          Never (Unlimited)
                        </span>
                      )}
                    </td>
                    <td className="kb-mcp-td">
                      {isRevoked ? (
                        <span className="kb-mcp-status-revoked" data-testid="status-revoked">Revoked</span>
                      ) : (
                        <span>Active</span>
                      )}
                    </td>
                    <td className="kb-mcp-td">
                      {!isRevoked && (
                        <>
                          {isConfirming ? (
                            <div className="kb-mcp-confirm-bar" data-testid="confirm-revoke-bar">
                              <button
                                type="button"
                                className="kb-mcp-cancel-btn"
                                data-testid="cancel-revoke-btn"
                                autoFocus
                                onClick={() => {
                                  setConfirmRevokeKeyId(null);
                                }}
                              >
                                Cancel
                              </button>
                              <button
                                type="button"
                                className="kb-mcp-confirm-revoke-btn"
                                data-testid="confirm-revoke-btn"
                                onClick={() => {
                                  void handleConfirmRevokeKey(k.id);
                                }}
                              >
                                Confirm Revoke
                              </button>
                            </div>
                          ) : (
                            <button
                              type="button"
                              className="kb-mcp-action-btn"
                              data-testid={`revoke-btn-${k.id}`}
                              onClick={() => {
                                setConfirmRevokeKeyId(k.id);
                              }}
                            >
                              Revoke
                            </button>
                          )}
                        </>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>

      {/* Connected OAuth Apps Section (in mine view) */}
      {activeView === 'mine' && (
        <section className="kb-mcp-studio-section" data-testid="connected-apps-section">
          <h2 className="kb-mcp-section-title">
            <EmojiHint kind="restricted" /> Connected OAuth Apps
          </h2>
          <div className="kb-mcp-table-wrap">
            <table className="kb-mcp-table" data-testid="connected-apps-table">
              <thead>
                <tr>
                  <th className="kb-mcp-th">Application</th>
                  <th className="kb-mcp-th">Client ID</th>
                  <th className="kb-mcp-th">Surface</th>
                  <th className="kb-mcp-th">Connected Date</th>
                  <th className="kb-mcp-th">Actions</th>
                </tr>
              </thead>
              <tbody>
                {connectedApps.length === 0 && !loading && (
                  <tr>
                    <td colSpan={5} className="kb-mcp-empty-state">
                      No external OAuth applications currently connected.
                    </td>
                  </tr>
                )}
                {connectedApps.map((app) => {
                  const isConfirming = confirmRevokeAppId === app.id;

                  return (
                    <tr key={app.id} className="kb-mcp-tr" data-testid={`app-row-${app.id}`}>
                      <td className="kb-mcp-td" data-testid={`app-name-${app.id}`}>
                        {/* Render client_name strictly as text node against XSS */}
                        <span>{app.client_name ?? app.client_id}</span>
                      </td>
                      <td className="kb-mcp-td">
                        <code>{app.client_id}</code>
                      </td>
                      <td className="kb-mcp-td">{((app.surface as string | undefined) ?? '').toUpperCase()}</td>
                      <td className="kb-mcp-td">
                        {new Date(app.created_at).toLocaleDateString()}
                      </td>
                      <td className="kb-mcp-td">
                        {isConfirming ? (
                          <div className="kb-mcp-confirm-bar" data-testid="confirm-disconnect-bar">
                            <button
                              type="button"
                              className="kb-mcp-cancel-btn"
                              data-testid="cancel-disconnect-btn"
                              autoFocus
                              onClick={() => {
                                setConfirmRevokeAppId(null);
                              }}
                            >
                              Cancel
                            </button>
                            <button
                              type="button"
                              className="kb-mcp-confirm-revoke-btn"
                              data-testid="confirm-disconnect-btn"
                              onClick={() => {
                                void handleConfirmRevokeApp(app.id);
                              }}
                            >
                              Confirm Disconnect
                            </button>
                          </div>
                        ) : (
                          <button
                            type="button"
                            className="kb-mcp-action-btn"
                            data-testid={`disconnect-btn-${app.id}`}
                            onClick={() => {
                              setConfirmRevokeAppId(app.id);
                            }}
                          >
                            Disconnect
                          </button>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {/* Mint Key Modal */}
      {showMintModal && (
        <div
          className="kb-snippet-modal-backdrop"
          data-testid="mint-modal-backdrop"
          onClick={(e) => {
            if (e.target === e.currentTarget) {
              setShowMintModal(false);
            }
          }}
        >
          <div
            className="kb-snippet-modal-card"
            role="dialog"
            aria-modal="true"
            aria-labelledby="mint-modal-title"
            data-testid="mint-modal-card"
          >
            <div className="kb-snippet-modal-header">
              <h2 id="mint-modal-title" className="kb-snippet-modal-title">Mint New MCP Access Key</h2>
              <button
                type="button"
                className="kb-snippet-modal-close-btn"
                onClick={() => {
                  setShowMintModal(false);
                  setMintError(null);
                }}
              >
                x
              </button>
            </div>
            <form
              onSubmit={(e) => {
                void handleMintSubmit(e);
              }}
              className="kb-mcp-mint-form"
            >
              {mintError && (
                <div className="kb-mcp-mint-error" role="alert" data-testid="mint-error-banner">
                  {mintError}
                </div>
              )}
              <div className="kb-mcp-form-row">
                <label htmlFor="mint-label-input" className="kb-mcp-form-label">
                  Key Label:
                </label>
                <input
                  id="mint-label-input"
                  type="text"
                  className="kb-mcp-form-input"
                  data-testid="mint-label-input"
                  placeholder="e.g. CI Agent Token"
                  value={newKeyLabel}
                  onChange={(e) => {
                    setNewKeyLabel(e.target.value);
                  }}
                  autoFocus
                  required
                />
              </div>

              {/* Scope Tier Selector in Mint Modal */}
              <div className="kb-mcp-form-row">
                <label htmlFor="mint-scope-select" className="kb-mcp-form-label">
                  Scope Tier:
                </label>
                <select
                  id="mint-scope-select"
                  className="kb-mcp-form-select"
                  data-testid="mint-scope-select"
                  value={newKeyScopeTier}
                  onChange={(e) => {
                    setNewKeyScopeTier(e.target.value as ScopeTier);
                  }}
                >
                  <option value="workspace">Workspace Bot Key</option>
                  <option value="project">Project Bot Key</option>
                  {isServerAdmin && <option value="global">Server / Global Key</option>}
                  <option value="personal_user">Personal User Key</option>
                </select>
              </div>

              {newKeyScopeTier === 'project' && (
                <div className="kb-mcp-form-row">
                  <label htmlFor="mint-project-input" className="kb-mcp-form-label">
                    Allowed Project:
                  </label>
                  <input
                    id="mint-project-input"
                    type="text"
                    className="kb-mcp-form-input"
                    data-testid="mint-project-input"
                    value={newKeyProject}
                    onChange={(e) => {
                      setNewKeyProject(e.target.value);
                    }}
                    required
                  />
                </div>
              )}

              <div className="kb-mcp-form-row">
                <label htmlFor="mint-surface-select" className="kb-mcp-form-label">
                  Target Surface:
                </label>
                <select
                  id="mint-surface-select"
                  className="kb-mcp-form-select"
                  data-testid="mint-surface-select"
                  value={newKeySurface}
                  onChange={(e) => {
                    setNewKeySurface(e.target.value as 'agent' | 'docs' | 'admin');
                    setDisabledTools([]);
                  }}
                >
                  <option value="agent">/mcp/agent (Standard Tools)</option>
                  <option value="docs">/mcp/docs (Knowledge & Markdown)</option>
                  {isWorkspaceAdmin && (
                    <option value="admin">/mcp/admin (Administrative Ops)</option>
                  )}
                </select>
              </div>

              <div className="kb-mcp-form-row">
                <label htmlFor="mint-expiry-select" className="kb-mcp-form-label">
                  Expiration:
                </label>
                <select
                  id="mint-expiry-select"
                  className="kb-mcp-form-select"
                  data-testid="mint-expiry-select"
                  value={isUnlimited ? 'unlimited' : newKeyExpiry}
                  onChange={(e) => {
                    if (e.target.value === 'unlimited') {
                      setIsUnlimited(true);
                    } else {
                      setIsUnlimited(false);
                      setNewKeyExpiry(Number(e.target.value));
                      setConfirmUnlimited(false);
                    }
                  }}
                >
                  <option value={30}>30 Days</option>
                  <option value={60}>60 Days</option>
                  <option value={90}>90 Days</option>
                  <option value={365}>1 Year</option>
                  {allowUnlimited && (
                    <option value="unlimited" data-testid="option-unlimited">
                      Unlimited (not recommended)
                    </option>
                  )}
                </select>
              </div>

              {isUnlimited && (
                <div
                  className="kb-mcp-unlimited-warning"
                  data-testid="unlimited-warning-box"
                  data-test-banner="unlimited-warning-banner"
                >
                  <p className="kb-mcp-warning-text">
                    ⚠️ <strong>Are you sure?</strong> Unlimited keys never expire. This poses a significant security risk if the token is leaked or compromised.
                  </p>
                  <label className="kb-mcp-confirm-unlimited-label">
                    <input
                      type="checkbox"
                      data-testid="confirm-unlimited-checkbox"
                      checked={confirmUnlimited}
                      onChange={(e) => {
                        setConfirmUnlimited(e.target.checked);
                      }}
                    />
                    <span>I understand the security risk and confirm creating an unlimited key</span>
                  </label>
                </div>
              )}

              <div className="kb-mcp-form-row">
                <label className="kb-mcp-form-label">
                  Narrow Tools (Disable specific capabilities):
                </label>
                <div className="kb-mcp-tools-grid" data-testid="tools-selection-grid">
                  {SURFACE_TOOLS[newKeySurface]
                    .filter((toolName) => !isViewer || !WRITE_MCP_TOOLS.has(toolName))
                    .map((toolName) => {
                    const isDisabled = disabledTools.includes(toolName);
                    return (
                      <label key={toolName} className="kb-mcp-tool-checkbox-label">
                        <input
                          type="checkbox"
                          data-testid={`disable-tool-${toolName}`}
                          checked={isDisabled}
                          onChange={(e) => {
                            if (e.target.checked) {
                              setDisabledTools([...disabledTools, toolName]);
                            } else {
                              setDisabledTools(disabledTools.filter((t) => t !== toolName));
                            }
                          }}
                        />
                        <span><code>{toolName}</code> (disable)</span>
                      </label>
                    );
                  })}
                </div>
              </div>

              <div className="kb-mcp-form-actions">
                <button
                  type="button"
                  className="kb-snippet-copy-btn"
                  onClick={() => {
                    setShowMintModal(false);
                    setMintError(null);
                    setIsUnlimited(false);
                    setConfirmUnlimited(false);
                    setDisabledTools([]);
                  }}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="kb-snippet-done-btn"
                  data-testid="mint-submit-btn"
                  disabled={minting || !newKeyLabel.trim() || (isUnlimited && !confirmUnlimited)}
                >
                  {minting ? 'Minting...' : 'Mint Key'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Snippet / Plaintext Key Modal */}
      {showSnippetModal && (
        <McpConfigSnippetModal
          rawKey={activeSnippetKey}
          surface={newKeySurface}
          projectKey={effectiveProjectKey}
          onClose={() => {
            setActiveSnippetKey(undefined);
            setShowSnippetModal(false);
          }}
        />
      )}

      {/* Inline AAL2 Step-Up Modal */}
      {aal2Challenge && (
        <div className="kb-snippet-modal-backdrop" data-testid="aal2-modal-backdrop">
          <div
            className="kb-snippet-modal-card"
            role="dialog"
            aria-modal="true"
            aria-labelledby="aal2-modal-title"
            data-testid="aal2-modal-card"
          >
            <div className="kb-snippet-modal-header">
              <h2 id="aal2-modal-title" className="kb-snippet-modal-title">
                Admin Verification Required (AAL2)
              </h2>
              <button
                type="button"
                className="kb-snippet-modal-close-btn"
                onClick={() => {
                  setAal2Challenge(null);
                  setPendingAction(null);
                }}
              >
                x
              </button>
            </div>
            <div className="kb-mcp-studio-section">
              <SecondFactorStep
                challengeId={aal2Challenge.challengeId}
                methods={aal2Challenge.methods}
                onSuccess={() => {
                  void handleAal2Success();
                }}
                onError={() => {
                  // Handled inside SecondFactorStep
                }}
                onSessionExpired={() => {
                  setAal2Challenge(null);
                  setPendingAction(null);
                }}
                onCancel={() => {
                  setAal2Challenge(null);
                  setPendingAction(null);
                }}
              />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
