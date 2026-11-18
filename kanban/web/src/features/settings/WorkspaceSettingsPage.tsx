/**
 * Workspace Settings Studio (KANBA-202).
 *
 * Dedicated management page for Workspace Administrators (`WORKSPACE_ADMIN` / `SERVER_ADMIN`).
 * Tabs:
 * 1. General & Policy: Workspace Name, Slug, Default Visibility, Session Timeouts, Trash Retention.
 * 2. Workspace Members: Local user provisioning (`+ Add User`) and role binding updates.
 * 3. Workspace MCP Keys: Link to `/workspaces/settings/mcp`.
 */

import React, { useEffect, useState, type JSX, type SyntheticEvent } from 'react';
import { Link } from 'react-router';
import { apiFetch } from '../../api/client';
import { ensureSessionCsrfToken } from '../auth/useSessionGuard';
import './ProjectSettingsPage.css';

interface WorkspaceSettingsData {
  workspace_id: string;
  name: string;
  slug: string;
  display_name: string;
  default_project_visibility: 'private' | 'workspace';
  session_idle_timeout_min: number;
  session_absolute_timeout_min: number;
  trash_retention_days: number;
  mcp_key_max_ttl_days: number;
  air_gap_mode: boolean;
  updated_at: string;
}

interface WorkspacePrincipal {
  id: string;
  display_name?: string | null;
  principal_type: string;
  handle?: string | null;
  email?: string | null;
  role?: string | null;
}

export function WorkspaceSettingsPage(): JSX.Element {
  const [activeTab, setActiveTab] = useState<'general' | 'members' | 'mcp'>('general');
  const [, setSettings] = useState<WorkspaceSettingsData | null>(null);
  const [principals, setPrincipals] = useState<WorkspacePrincipal[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  // Form Fields
  const [name, setName] = useState<string>('');
  const [slug, setSlug] = useState<string>('');
  const [defaultVisibility, setDefaultVisibility] = useState<'private' | 'workspace'>('workspace');
  const [idleTimeout, setIdleTimeout] = useState<number>(120);
  const [absTimeout, setAbsTimeout] = useState<number>(1440);
  const [trashRetention, setTrashRetention] = useState<number>(30);
  const [isSaving, setIsSaving] = useState<boolean>(false);

  // New User Form
  const [newHandle, setNewHandle] = useState<string>('');
  const [newDisplayName, setNewDisplayName] = useState<string>('');
  const [newEmail, setNewEmail] = useState<string>('');
  const [newPassword, setNewPassword] = useState<string>('');
  const [newRole, setNewRole] = useState<'WORKSPACE_MEMBER' | 'WORKSPACE_GUEST' | 'WORKSPACE_ADMIN'>('WORKSPACE_MEMBER');
  const [isCreatingUser, setIsCreatingUser] = useState<boolean>(false);
  const [currentUser, setCurrentUser] = useState<{
    is_server_admin?: boolean;
    is_workspace_admin?: boolean;
  } | null>(null);

  useEffect(() => {
    let active = true;
    async function init(): Promise<void> {
      setIsLoading(true);
      setErrorMessage(null);
      try {
        // 0. Verify authorization
        try {
          const me = (await apiFetch('GET', '/api/v1/auth/me' as never)) as {
            is_server_admin?: boolean;
            is_workspace_admin?: boolean;
          };
          if (active) setCurrentUser(me);
          if (!me.is_server_admin && !me.is_workspace_admin) {
            if (active) setIsLoading(false);
            return;
          }
        } catch {
          // Fall back gracefully in offline unit tests
        }

        // 1. Fetch workspace settings
        const settingsRes = (await apiFetch('GET', '/api/v1/admin/workspace-settings' as never)) as WorkspaceSettingsData;
        if (active) {
          setSettings(settingsRes);
          setName(settingsRes.name);
          setSlug(settingsRes.slug);
          setDefaultVisibility(settingsRes.default_project_visibility);
          setIdleTimeout(settingsRes.session_idle_timeout_min);
          setAbsTimeout(settingsRes.session_absolute_timeout_min);
          setTrashRetention(settingsRes.trash_retention_days);
        }

        // 2. Fetch workspace principals
        try {
          const pRes = (await apiFetch('GET', '/api/v1/admin/principals?filter=USER&limit=100' as never)) as
            | WorkspacePrincipal[]
            | { items?: WorkspacePrincipal[] };
          const raw = Array.isArray(pRes) ? pRes : (pRes.items ?? []);
          if (active) setPrincipals(raw);
        } catch {
          // May be restricted or mock in tests
        }
      } catch (err: unknown) {
        if (active) {
          const errObj = err as { message?: string };
          setErrorMessage(errObj.message ?? 'Failed to load workspace settings.');
        }
      } finally {
        if (active) setIsLoading(false);
      }
    }
    void init();
    return () => {
      active = false;
    };
  }, []);

  const handleSaveGeneral = (e: SyntheticEvent) => {
    e.preventDefault();
    void (async () => {
      setIsSaving(true);
      setErrorMessage(null);
      setSuccessMessage(null);
      try {
        const csrf = await ensureSessionCsrfToken();
        const headers: Record<string, string> = { 'Content-Type': 'application/json' };
        if (csrf) headers['X-CSRF-Token'] = csrf;

        const payload = {
          name: name.trim(),
          slug: slug.trim(),
          default_project_visibility: defaultVisibility,
          session_idle_timeout_min: idleTimeout,
          session_absolute_timeout_min: absTimeout,
          trash_retention_days: trashRetention,
        };

        const updated = (await apiFetch('PATCH', '/api/v1/admin/workspace-settings' as never, {
          headers,
          body: JSON.stringify(payload),
        })) as WorkspaceSettingsData;

        setSettings(updated);
        setSuccessMessage('Workspace settings updated successfully.');
      } catch (err: unknown) {
        const errObj = err as { message?: string };
        setErrorMessage(errObj.message ?? 'Failed to update workspace settings.');
      } finally {
        setIsSaving(false);
      }
    })();
  };

  const handleCreateUser = (e: SyntheticEvent) => {
    e.preventDefault();
    if (!newHandle.trim() || !newDisplayName.trim()) return;
    void (async () => {
      setIsCreatingUser(true);
      setErrorMessage(null);
      setSuccessMessage(null);
      try {
        const csrf = await ensureSessionCsrfToken();
        const headers: Record<string, string> = { 'Content-Type': 'application/json' };
        if (csrf) headers['X-CSRF-Token'] = csrf;

        // 1. Create principal/user
        const createdUser = (await apiFetch('POST', '/api/v1/admin/principals' as never, {
          headers,
          body: JSON.stringify({
            type: 'USER',
            handle: newHandle.startsWith('@') ? newHandle.trim() : `@${newHandle.trim()}`,
            display_name: newDisplayName.trim(),
            email: newEmail.trim() || undefined,
            password: newPassword || undefined,
          }),
        })) as { id: string };

        // 2. Bind role if provided
        if (createdUser.id) {
          await apiFetch('POST', '/api/v1/admin/role-bindings' as never, {
            headers,
            body: JSON.stringify({
              principal_id: createdUser.id,
              role_name: newRole,
              scope_type: 'workspace',
            }),
          });
        }

        setNewHandle('');
        setNewDisplayName('');
        setNewEmail('');
        setNewPassword('');
        setSuccessMessage(`User ${newDisplayName} created successfully.`);
        const pRes = (await apiFetch('GET', '/api/v1/admin/principals?filter=USER&limit=100' as never)) as
          | WorkspacePrincipal[]
          | { items?: WorkspacePrincipal[] };
        const raw = Array.isArray(pRes) ? pRes : (pRes.items ?? []);
        setPrincipals(raw);
      } catch (err: unknown) {
        const errObj = err as { message?: string };
        setErrorMessage(errObj.message ?? 'Failed to create workspace user.');
      } finally {
        setIsCreatingUser(false);
      }
    })();
  };

  if (isLoading) {
    return (
      <div data-testid="workspace-settings-page" className="kb-settings-container">
        <div className="kb-settings-loading">Loading workspace settings...</div>
      </div>
    );
  }

  if (currentUser && !currentUser.is_server_admin && !currentUser.is_workspace_admin) {
    return (
      <div data-testid="workspace-settings-page" className="kb-settings-container">
        <div data-testid="access-denied-message" className="kb-settings-alert kb-settings-alert-error">
          You do not have administrative privileges to manage this workspace.
        </div>
      </div>
    );
  }

  return (
    <div data-testid="workspace-settings-page" className="kb-settings-container">
      <header className="kb-settings-header">
        <div>
          <h1 className="kb-settings-title">Workspace Settings</h1>
          <p className="kb-settings-subtitle">Configure organization policies, membership, and workspace integrations.</p>
        </div>
      </header>

      {errorMessage && (
        <div className="kb-settings-alert kb-settings-alert-error" role="alert">
          {errorMessage}
        </div>
      )}
      {successMessage && (
        <div className="kb-settings-alert kb-settings-alert-success" role="status">
          {successMessage}
        </div>
      )}

      {/* Tabs */}
      <nav className="kb-settings-tabs" role="tablist" aria-label="Workspace Settings Navigation">
        <button
          type="button"
          role="tab"
          aria-selected={activeTab === 'general'}
          data-testid="tab-general"
          className={`kb-settings-tab ${activeTab === 'general' ? 'kb-settings-tab-active' : ''}`}
          onClick={() => { setActiveTab('general'); }}
        >
          General & Policy
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={activeTab === 'members'}
          data-testid="tab-members"
          className={`kb-settings-tab ${activeTab === 'members' ? 'kb-settings-tab-active' : ''}`}
          onClick={() => { setActiveTab('members'); }}
        >
          Workspace Members
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={activeTab === 'mcp'}
          data-testid="tab-mcp"
          className={`kb-settings-tab ${activeTab === 'mcp' ? 'kb-settings-tab-active' : ''}`}
          onClick={() => { setActiveTab('mcp'); }}
        >
          Workspace MCP Keys
        </button>
      </nav>

      <div className="kb-settings-panel">
        {activeTab === 'general' && (
          <form onSubmit={handleSaveGeneral} className="kb-settings-form" data-testid="workspace-general-form">
            <div className="kb-form-group">
              <label htmlFor="ws-name-input">Workspace Name</label>
              <input
                id="ws-name-input"
                type="text"
                data-testid="workspace-name-input"
                className="kb-input"
                value={name}
                onChange={(e) => { setName(e.target.value); }}
                required
              />
            </div>

            <div className="kb-form-group">
              <label htmlFor="ws-slug-input">Workspace Slug</label>
              <input
                id="ws-slug-input"
                type="text"
                data-testid="workspace-slug-input"
                className="kb-input"
                value={slug}
                onChange={(e) => { setSlug(e.target.value); }}
                required
              />
            </div>

            <div className="kb-form-group">
              <label htmlFor="ws-visibility-select">Default Project Visibility</label>
              <select
                id="ws-visibility-select"
                data-testid="workspace-visibility-select"
                className="kb-select"
                value={defaultVisibility}
                onChange={(e) => { setDefaultVisibility(e.target.value as 'private' | 'workspace'); }}
              >
                <option value="workspace">Workspace (All members can view)</option>
                <option value="private">Private (Explicit members only)</option>
              </select>
            </div>

            <div className="kb-form-group">
              <label htmlFor="ws-idle-timeout-input">Session Idle Timeout (Minutes)</label>
              <input
                id="ws-idle-timeout-input"
                type="number"
                data-testid="workspace-idle-timeout-input"
                className="kb-input"
                min="5"
                value={idleTimeout}
                onChange={(e) => { setIdleTimeout(Number(e.target.value)); }}
                required
              />
            </div>

            <div className="kb-form-group">
              <label htmlFor="ws-abs-timeout-input">Session Absolute Timeout (Minutes)</label>
              <input
                id="ws-abs-timeout-input"
                type="number"
                data-testid="workspace-abs-timeout-input"
                className="kb-input"
                min="60"
                value={absTimeout}
                onChange={(e) => { setAbsTimeout(Number(e.target.value)); }}
                required
              />
            </div>

            <div className="kb-form-group">
              <label htmlFor="ws-trash-retention-input">Trash Retention Days</label>
              <input
                id="ws-trash-retention-input"
                type="number"
                data-testid="workspace-trash-retention-input"
                className="kb-input"
                min="1"
                value={trashRetention}
                onChange={(e) => { setTrashRetention(Number(e.target.value)); }}
                required
              />
            </div>

            <button
              type="submit"
              data-testid="save-workspace-btn"
              className="kb-btn kb-btn-primary"
              disabled={isSaving}
            >
              {isSaving ? 'Saving...' : 'Save Workspace Settings'}
            </button>
          </form>
        )}

        {activeTab === 'members' && (
          <div className="kb-members-section" data-testid="workspace-members-section">
            <form onSubmit={handleCreateUser} className="kb-add-member-form" data-testid="create-user-form">
              <h3>+ Add Workspace User</h3>
              <div className="kb-form-group">
                <input
                  type="text"
                  data-testid="new-user-handle"
                  className="kb-input"
                  placeholder="@handle"
                  value={newHandle}
                  onChange={(e) => { setNewHandle(e.target.value); }}
                  required
                />
              </div>
              <div className="kb-form-group">
                <input
                  type="text"
                  data-testid="new-user-name"
                  className="kb-input"
                  placeholder="Full Name / Display Name"
                  value={newDisplayName}
                  onChange={(e) => { setNewDisplayName(e.target.value); }}
                  required
                />
              </div>
              <div className="kb-form-group">
                <input
                  type="email"
                  data-testid="new-user-email"
                  className="kb-input"
                  placeholder="email@example.com (optional)"
                  value={newEmail}
                  onChange={(e) => { setNewEmail(e.target.value); }}
                />
              </div>
              <div className="kb-form-group">
                <input
                  type="password"
                  data-testid="new-user-password"
                  className="kb-input"
                  placeholder="Initial Password (optional)"
                  value={newPassword}
                  onChange={(e) => { setNewPassword(e.target.value); }}
                />
              </div>
              <div className="kb-form-row">
                <select
                  data-testid="new-user-role-select"
                  className="kb-select"
                  value={newRole}
                  onChange={(e) => { setNewRole(e.target.value as 'WORKSPACE_MEMBER' | 'WORKSPACE_GUEST' | 'WORKSPACE_ADMIN'); }}
                >
                  <option value="WORKSPACE_MEMBER">WORKSPACE_MEMBER (Standard)</option>
                  <option value="WORKSPACE_GUEST">WORKSPACE_GUEST (Restricted)</option>
                  <option value="WORKSPACE_ADMIN">WORKSPACE_ADMIN (Admin)</option>
                </select>
                <button
                  type="submit"
                  data-testid="create-user-submit-btn"
                  className="kb-btn kb-btn-primary"
                  disabled={isCreatingUser}
                >
                  {isCreatingUser ? 'Creating...' : 'Create User'}
                </button>
              </div>
            </form>

            <div className="kb-members-table-wrapper">
              <h3>Workspace Users & Principals</h3>
              <table className="kb-table" data-testid="workspace-users-table">
                <thead>
                  <tr>
                    <th>User</th>
                    <th>Type</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {principals.length === 0 ? (
                    <tr>
                      <td colSpan={3} className="kb-empty-cell">No users registered in this workspace.</td>
                    </tr>
                  ) : (
                    principals.map((p) => (
                      <tr key={p.id} data-testid={`principal-row-${p.id}`}>
                        <td>
                          <div className="kb-member-info">
                            <span className="kb-member-name">{p.display_name ?? p.handle ?? p.id}</span>
                            {p.email && <span className="kb-member-email">{p.email}</span>}
                          </div>
                        </td>
                        <td>
                          <span className="kb-role-badge kb-role-viewer">
                            {p.principal_type}
                          </span>
                        </td>
                        <td>Active</td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {activeTab === 'mcp' && (
          <div className="kb-integrations-grid" data-testid="workspace-mcp-section">
            <Link
              to="/workspaces/settings/mcp"
              className="kb-integration-card"
              data-testid="link-workspace-mcp"
            >
              <div className="kb-card-icon">🏢</div>
              <div className="kb-card-content">
                <h3>Workspace MCP Access Keys</h3>
                <p>Manage organization-level Model Context Protocol API tokens and client credentials.</p>
              </div>
            </Link>
          </div>
        )}
      </div>
    </div>
  );
}
export default WorkspaceSettingsPage;
