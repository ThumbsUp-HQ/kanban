/**
 * Project Settings Studio (KANBA-202).
 *
 * Dedicated management page for Project Administrators (`PROJECT_ADMIN`).
 * Tabs:
 * 1. General: Project Name, Description Markdown, Modules Enabled, Auto-Archive Days.
 * 2. Members & Access: Project Role Bindings (`PROJECT_ADMIN`, `MEMBER`, `VIEWER`), Add Member, Remove Member, and Access Inspector trigger.
 * 3. Automation & Integrations: Direct navigation cards to Workflows (`/projects/:projectKey/settings/workflows`), Custom Fields (`/projects/:projectKey/settings/custom-fields`), and Project MCP Keys (`/projects/:projectKey/settings/mcp`).
 * 4. Danger Zone: 2-stage Project deletion with confirmation phrase and blast radius computation.
 */

import React, { useEffect, useState, type JSX, type SyntheticEvent } from 'react';
import { Link, useNavigate, useParams } from 'react-router';
import { apiFetch } from '../../api/client';
import { ensureSessionCsrfToken } from '../auth/useSessionGuard';
import './ProjectSettingsPage.css';

interface ProjectDetail {
  id: string;
  identifier: string;
  name: string;
  description_markdown?: string | null;
  modules_enabled?: boolean;
  auto_archive_days?: number | null;
  capabilities?: string[];
  is_project_admin?: boolean;
  project_role?: string | null;
}

interface ProjectMember {
  id: string;
  principal_id: string;
  project_id: string;
  role: 'PROJECT_ADMIN' | 'MEMBER' | 'VIEWER';
  display_name?: string | null;
  handle?: string | null;
  email?: string | null;
  created_at: string;
}

interface DestructiveRequestOut {
  stage: string;
  target: string;
  target_kind: string;
  target_id: string;
  mode: string;
  blast_summary: {
    issues_count?: number;
    sub_issues_count?: number;
    pages_count?: number;
    stickies_count?: number;
    [key: string]: unknown;
  };
  blast_hash: string;
  confirm_phrase: string;
  confirmation_token: string;
  expires_in_sec: number;
}

export function ProjectSettingsPage(): JSX.Element {
  const { projectKey = 'KAN' } = useParams<{ projectKey: string }>();
  const navigate = useNavigate();

  const [activeTab, setActiveTab] = useState<'general' | 'members' | 'integrations' | 'danger'>('general');
  const [project, setProject] = useState<ProjectDetail | null>(null);
  const [members, setMembers] = useState<ProjectMember[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  // General Tab Form State
  const [name, setName] = useState<string>('');
  const [description, setDescription] = useState<string>('');
  const [modulesEnabled, setModulesEnabled] = useState<boolean>(true);
  const [autoArchiveDays, setAutoArchiveDays] = useState<string>('');
  const [isSaving, setIsSaving] = useState<boolean>(false);

  // Add Member State
  const [newPrincipalId, setNewPrincipalId] = useState<string>('');
  const [newRole, setNewRole] = useState<'PROJECT_ADMIN' | 'MEMBER' | 'VIEWER'>('MEMBER');
  const [isAddingMember, setIsAddingMember] = useState<boolean>(false);

  // Danger Zone State
  const [dangerStage, setDangerStage] = useState<'idle' | 'requested' | 'executing'>('idle');
  const [destructiveToken, setDestructiveToken] = useState<DestructiveRequestOut | null>(null);
  const [enteredPhrase, setEnteredPhrase] = useState<string>('');
  const [dangerError, setDangerError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    async function init(): Promise<void> {
      setIsLoading(true);
      setErrorMessage(null);
      try {
        const projRes = (await apiFetch('GET', `/api/v1/projects/${encodeURIComponent(projectKey)}` as never)) as ProjectDetail;
        if (active) {
          setProject(projRes);
          setName(projRes.name);
          setDescription(projRes.description_markdown ?? '');
          setModulesEnabled(projRes.modules_enabled ?? true);
          setAutoArchiveDays(projRes.auto_archive_days !== null && projRes.auto_archive_days !== undefined ? String(projRes.auto_archive_days) : '');
        }

        try {
          const memRes: unknown = await apiFetch('GET', `/api/v1/projects/${encodeURIComponent(projectKey)}/members` as never);
          if (active && Array.isArray(memRes)) {
            setMembers(memRes as ProjectMember[]);
          }
        } catch {
          // Members list may fail if not authorized
        }
      } catch (err: unknown) {
        if (active) {
          const errObj = err as { message?: string };
          setErrorMessage(errObj.message ?? 'Failed to load project settings.');
        }
      } finally {
        if (active) setIsLoading(false);
      }
    }
    void init();
    return () => {
      active = false;
    };
  }, [projectKey]);

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
          description_markdown: description,
          modules_enabled: modulesEnabled,
          auto_archive_days: autoArchiveDays ? parseInt(autoArchiveDays, 10) : null,
        };

        const updated = (await apiFetch('PATCH', `/api/v1/projects/${encodeURIComponent(projectKey)}` as never, {
          headers,
          body: JSON.stringify(payload),
        })) as ProjectDetail;

        setProject(updated);
        setSuccessMessage('Project settings saved successfully.');
      } catch (err: unknown) {
        const errObj = err as { message?: string };
        setErrorMessage(errObj.message ?? 'Failed to update project settings.');
      } finally {
        setIsSaving(false);
      }
    })();
  };

  const handleAddMember = (e: SyntheticEvent) => {
    e.preventDefault();
    if (!newPrincipalId.trim()) return;
    void (async () => {
      setIsAddingMember(true);
      setErrorMessage(null);
      try {
        const csrf = await ensureSessionCsrfToken();
        const headers: Record<string, string> = { 'Content-Type': 'application/json' };
        if (csrf) headers['X-CSRF-Token'] = csrf;

        await apiFetch('POST', `/api/v1/projects/${encodeURIComponent(projectKey)}/members` as never, {
          headers,
          body: JSON.stringify({ principal_id: newPrincipalId.trim(), role: newRole }),
        });

        setNewPrincipalId('');
        setSuccessMessage('Project member added.');
        const memRes = (await apiFetch('GET', `/api/v1/projects/${encodeURIComponent(projectKey)}/members` as never)) as
          | ProjectMember[]
          | { items: ProjectMember[] };
        if (Array.isArray(memRes)) {
          setMembers(memRes);
        } else {
          setMembers(memRes.items);
        }
      } catch (err: unknown) {
        const errObj = err as { message?: string };
        setErrorMessage(errObj.message ?? 'Failed to add project member.');
      } finally {
        setIsAddingMember(false);
      }
    })();
  };

  const handleRemoveMember = (principalId: string) => {
    setErrorMessage(null);
    void (async () => {
      try {
        const csrf = await ensureSessionCsrfToken();
        const headers: Record<string, string> = {};
        if (csrf) headers['X-CSRF-Token'] = csrf;

        await apiFetch('DELETE', `/api/v1/projects/${encodeURIComponent(projectKey)}/members/${encodeURIComponent(principalId)}` as never, {
          headers,
        });

        setMembers((prev) => prev.filter((m) => m.principal_id !== principalId));
        setSuccessMessage('Member removed from project.');
      } catch (err: unknown) {
        const errObj = err as { message?: string };
        setErrorMessage(errObj.message ?? 'Failed to remove project member.');
      }
    })();
  };

  const handleTriggerAccessInspector = () => {
    if (typeof window !== 'undefined' && project) {
      window.dispatchEvent(
        new CustomEvent('kb:open-access-inspector', {
          bubbles: true,
          detail: { objectId: project.id, title: project.name },
        }),
      );
    }
  };

  const handleRequestDelete = () => {
    setDangerError(null);
    void (async () => {
      try {
        const csrf = await ensureSessionCsrfToken();
        const headers: Record<string, string> = { 'Content-Type': 'application/json' };
        if (csrf) headers['X-CSRF-Token'] = csrf;

        const res = (await apiFetch('POST', '/api/v1/admin/destructive:request' as never, {
          headers,
          body: JSON.stringify({
            target_kind: 'project',
            target: projectKey,
            mode: 'soft',
          }),
        })) as DestructiveRequestOut;

        setDestructiveToken(res);
        setDangerStage('requested');
      } catch (err: unknown) {
        const errObj = err as { message?: string };
        setDangerError(errObj.message ?? 'Failed to initiate project deletion.');
      }
    })();
  };

  const handleExecuteDelete = () => {
    if (!destructiveToken) return;
    setDangerError(null);
    setDangerStage('executing');
    void (async () => {
      try {
        const csrf = await ensureSessionCsrfToken();
        const headers: Record<string, string> = { 'Content-Type': 'application/json' };
        if (csrf) headers['X-CSRF-Token'] = csrf;

        await apiFetch('POST', '/api/v1/admin/destructive:execute' as never, {
          headers,
          body: JSON.stringify({
            confirmation_token: destructiveToken.confirmation_token,
            confirm_phrase: enteredPhrase.trim(),
            blast_hash: destructiveToken.blast_hash,
          }),
        });

        void navigate('/projects');
      } catch (err: unknown) {
        const errObj = err as { message?: string };
        setDangerError(errObj.message ?? 'Failed to execute project deletion.');
        setDangerStage('requested');
      }
    })();
  };

  if (isLoading) {
    return (
      <div data-testid="project-settings-page" className="kb-settings-container">
        <div className="kb-settings-loading">Loading project settings...</div>
      </div>
    );
  }

  const isProjectAdmin = project?.is_project_admin === true || (project?.capabilities?.includes('ADMIN') ?? false);

  if (!isProjectAdmin) {
    return (
      <div data-testid="project-settings-page" className="kb-settings-container">
        <div className="kb-settings-error" role="alert">
          <h2>Not found or no access</h2>
          <p>You do not have project administrator permissions for {projectKey}.</p>
        </div>
      </div>
    );
  }

  return (
    <div data-testid="project-settings-page" className="kb-settings-container">
      <header className="kb-settings-header">
        <div>
          <h1 className="kb-settings-title">Project Settings: {project?.name ?? projectKey}</h1>
          <p className="kb-settings-subtitle">Manage project identity, membership, workflows, and integrations.</p>
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

      {/* Tabs Navigation */}
      <nav className="kb-settings-tabs" role="tablist" aria-label="Project Settings Navigation">
        <button
          type="button"
          role="tab"
          aria-selected={activeTab === 'general'}
          data-testid="tab-general"
          className={`kb-settings-tab ${activeTab === 'general' ? 'kb-settings-tab-active' : ''}`}
          onClick={() => { setActiveTab('general'); }}
        >
          General
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={activeTab === 'members'}
          data-testid="tab-members"
          className={`kb-settings-tab ${activeTab === 'members' ? 'kb-settings-tab-active' : ''}`}
          onClick={() => { setActiveTab('members'); }}
        >
          Members & Access
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={activeTab === 'integrations'}
          data-testid="tab-integrations"
          className={`kb-settings-tab ${activeTab === 'integrations' ? 'kb-settings-tab-active' : ''}`}
          onClick={() => { setActiveTab('integrations'); }}
        >
          Automation & Integrations
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={activeTab === 'danger'}
          data-testid="tab-danger"
          className={`kb-settings-tab ${activeTab === 'danger' ? 'kb-settings-tab-active' : ''}`}
          onClick={() => { setActiveTab('danger'); }}
        >
          Danger Zone
        </button>
      </nav>

      {/* Tab Panels */}
      <div className="kb-settings-panel">
        {activeTab === 'general' && (
          <form onSubmit={handleSaveGeneral} className="kb-settings-form" data-testid="general-form">
            <div className="kb-form-group">
              <label htmlFor="proj-name-input">Project Name</label>
              <input
                id="proj-name-input"
                type="text"
                data-testid="project-name-input"
                className="kb-input"
                value={name}
                onChange={(e) => { setName(e.target.value); }}
                required
              />
            </div>

            <div className="kb-form-group">
              <label htmlFor="proj-desc-input">Description (Markdown)</label>
              <textarea
                id="proj-desc-input"
                data-testid="project-desc-input"
                className="kb-textarea"
                rows={4}
                value={description}
                onChange={(e) => { setDescription(e.target.value); }}
              />
            </div>

            <div className="kb-form-group-checkbox">
              <label className="kb-checkbox-label">
                <input
                  type="checkbox"
                  data-testid="project-modules-checkbox"
                  checked={modulesEnabled}
                  onChange={(e) => { setModulesEnabled(e.target.checked); }}
                />
                <span>Enable Modules for this project</span>
              </label>
            </div>

            <div className="kb-form-group">
              <label htmlFor="proj-auto-archive-input">Auto-Archive Days (optional)</label>
              <input
                id="proj-auto-archive-input"
                type="number"
                data-testid="project-auto-archive-input"
                className="kb-input"
                min="1"
                placeholder="Leave blank to disable"
                value={autoArchiveDays}
                onChange={(e) => { setAutoArchiveDays(e.target.value); }}
              />
            </div>

            <button
              type="submit"
              data-testid="save-general-btn"
              className="kb-btn kb-btn-primary"
              disabled={isSaving}
            >
              {isSaving ? 'Saving...' : 'Save Changes'}
            </button>
          </form>
        )}

        {activeTab === 'members' && (
          <div className="kb-members-section" data-testid="members-section">
            <div className="kb-members-actions-bar">
              <button
                type="button"
                data-testid="inspect-access-btn"
                className="kb-btn kb-btn-secondary"
                onClick={handleTriggerAccessInspector}
              >
                🔍 Inspect Effective Access
              </button>
            </div>

            <form onSubmit={handleAddMember} className="kb-add-member-form" data-testid="add-member-form">
              <h3>Add Project Member</h3>
              <div className="kb-form-row">
                <input
                  type="text"
                  data-testid="member-principal-id-input"
                  className="kb-input"
                  placeholder="Principal UUID or User ID"
                  value={newPrincipalId}
                  onChange={(e) => { setNewPrincipalId(e.target.value); }}
                  required
                />
                <select
                  data-testid="member-role-select"
                  className="kb-select"
                  value={newRole}
                  onChange={(e) => { setNewRole(e.target.value as 'PROJECT_ADMIN' | 'MEMBER' | 'VIEWER'); }}
                >
                  <option value="VIEWER">VIEWER (Read-only)</option>
                  <option value="MEMBER">MEMBER (Work item edit)</option>
                  <option value="PROJECT_ADMIN">PROJECT_ADMIN (Full control)</option>
                </select>
                <button
                  type="submit"
                  data-testid="add-member-submit-btn"
                  className="kb-btn kb-btn-primary"
                  disabled={isAddingMember}
                >
                  {isAddingMember ? 'Adding...' : 'Add Member'}
                </button>
              </div>
            </form>

            <div className="kb-members-table-wrapper">
              <h3>Current Project Members</h3>
              <table className="kb-table" data-testid="members-table">
                <thead>
                  <tr>
                    <th>Member</th>
                    <th>Role</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {members.length === 0 ? (
                    <tr>
                      <td colSpan={3} className="kb-empty-cell">No explicit project role bindings found.</td>
                    </tr>
                  ) : (
                    members.map((member) => (
                      <tr key={member.id} data-testid={`member-row-${member.principal_id}`}>
                        <td>
                          <div className="kb-member-info">
                            <span className="kb-member-name">{member.display_name ?? member.handle ?? member.principal_id}</span>
                            {member.email && <span className="kb-member-email">{member.email}</span>}
                          </div>
                        </td>
                        <td>
                          <span className={`kb-role-badge kb-role-${member.role.toLowerCase()}`}>
                            {member.role}
                          </span>
                        </td>
                        <td>
                          <button
                            type="button"
                            data-testid={`remove-member-${member.principal_id}`}
                            className="kb-btn kb-btn-danger-sm"
                            onClick={() => { handleRemoveMember(member.principal_id); }}
                          >
                            Remove
                          </button>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {activeTab === 'integrations' && (
          <div className="kb-integrations-grid" data-testid="integrations-section">
            <Link
              to={`/projects/${projectKey}/settings/workflows`}
              className="kb-integration-card"
              data-testid="integration-workflows-card"
            >
              <div className="kb-card-icon">🔀</div>
              <div className="kb-card-content">
                <h3>Workflows & States</h3>
                <p>Configure lifecycle transition hooks, approval gates, and automation rules.</p>
              </div>
            </Link>

            <Link
              to={`/projects/${projectKey}/settings/custom-fields`}
              className="kb-integration-card"
              data-testid="integration-custom-fields-card"
            >
              <div className="kb-card-icon">⚙️</div>
              <div className="kb-card-content">
                <h3>Custom Fields</h3>
                <p>Define custom metadata attributes, validation rules, and schema definitions.</p>
              </div>
            </Link>

            <Link
              to={`/projects/${projectKey}/settings/mcp`}
              className="kb-integration-card"
              data-testid="integration-mcp-card"
            >
              <div className="kb-card-icon">🤖</div>
              <div className="kb-card-content">
                <h3>Project MCP Keys</h3>
                <p>Manage scoped Model Context Protocol API tokens for autonomous agent runners.</p>
              </div>
            </Link>
          </div>
        )}

        {activeTab === 'danger' && (
          <div className="kb-danger-zone" data-testid="danger-section">
            <div className="kb-danger-header">
              <h3>Move Project to Trash</h3>
              <p>
                Deleting this project moves all associated work items, cycles, modules, and docs to trash according to retention policies.
              </p>
            </div>

            {dangerError && (
              <div className="kb-settings-alert kb-settings-alert-error" role="alert">
                {dangerError}
              </div>
            )}

            {dangerStage === 'idle' && (
              <button
                type="button"
                data-testid="request-delete-btn"
                className="kb-btn kb-btn-danger"
                onClick={handleRequestDelete}
              >
                🗑️ Move Project to Trash...
              </button>
            )}

            {dangerStage === 'requested' && destructiveToken && (
              <div className="kb-danger-confirm-card" data-testid="danger-confirm-card">
                <h4>Stage 2: Confirm Project Deletion</h4>
                <div className="kb-blast-radius-box">
                  <p><strong>Impacted Objects:</strong></p>
                  <ul>
                    <li>Work Items: {destructiveToken.blast_summary.issues_count}</li>
                    <li>Docs / Pages: {destructiveToken.blast_summary.pages_count}</li>
                    <li>Stickies: {destructiveToken.blast_summary.stickies_count}</li>
                  </ul>
                </div>

                <p className="kb-confirm-prompt">
                  To confirm, please type exact phrase: <code>{destructiveToken.confirm_phrase}</code>
                </p>

                <input
                  type="text"
                  data-testid="confirm-phrase-input"
                  className="kb-input"
                  placeholder="Type confirmation phrase exactly"
                  value={enteredPhrase}
                  onChange={(e) => { setEnteredPhrase(e.target.value); }}
                />

                <div className="kb-danger-actions">
                  <button
                    type="button"
                    data-testid="execute-delete-btn"
                    className="kb-btn kb-btn-danger"
                    disabled={enteredPhrase.trim() !== destructiveToken.confirm_phrase}
                    onClick={handleExecuteDelete}
                  >
                    Confirm Permanent Deletion
                  </button>
                  <button
                    type="button"
                    data-testid="cancel-delete-btn"
                    className="kb-btn kb-btn-secondary"
                    onClick={() => {
                      setDangerStage('idle');
                      setDestructiveToken(null);
                      setEnteredPhrase('');
                    }}
                  >
                    Cancel
                  </button>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
export default ProjectSettingsPage;
