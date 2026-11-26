// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import React, { useState, type JSX } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { isAal2StepUpCancelled } from '../../api/client';
import { FieldHelpHint } from '../../components/help/FieldHelpHint';
import './workflows.css';
import {
  fetchRepoBindings,
  createRepoBinding,
  refreshRepoBinding,
  deleteRepoBinding,
  validateGitRemoteUrl,
  type RepoBindingDetail,
  type CreateRepoBindingPayload,
} from './api';

export interface GitRepoBindingsSectionProps {
  projectKey: string;
  isUserAdmin: boolean;
  onAal2Intercept?:
    | ((
        err: unknown,
        mutation: { type: string; execute: () => Promise<void> },
      ) => boolean)
    | undefined;
}

export function GitRepoBindingsSection({
  projectKey,
  isUserAdmin,
  onAal2Intercept,
}: GitRepoBindingsSectionProps): JSX.Element {
  const queryClient = useQueryClient();
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [syncingId, setSyncingId] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  // Form State
  const [slug, setSlug] = useState('');
  const [remoteUrl, setRemoteUrl] = useState('');
  const [defaultRef, setDefaultRef] = useState('main');
  const [accessMode, setAccessMode] = useState<'ro_vfs_mount' | 'bare_git_tools'>('ro_vfs_mount');
  const [credential, setCredential] = useState('');
  const [patToken, setPatToken] = useState('');
  const [urlValidation, setUrlValidation] = useState<{ valid: boolean; error?: string } | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const bindingsQuery = useQuery({
    queryKey: ['project-repo-bindings', projectKey],
    queryFn: () => fetchRepoBindings(projectKey),
  });

  const bindings = bindingsQuery.data ?? [];
  const isLoading = bindingsQuery.isLoading;

  const resetForm = () => {
    setSlug('');
    setRemoteUrl('');
    setDefaultRef('main');
    setAccessMode('ro_vfs_mount');
    setCredential('');
    setPatToken('');
    setUrlValidation(null);
    setFormError(null);
    setIsSubmitting(false);
  };

  const handleOpenModal = () => {
    resetForm();
    setIsModalOpen(true);
  };

  const handleCloseModal = () => {
    if (!isSubmitting) {
      setIsModalOpen(false);
      resetForm();
    }
  };

  const handleUrlChange = (value: string) => {
    setRemoteUrl(value);
    if (value.trim()) {
      setUrlValidation(validateGitRemoteUrl(value));
    } else {
      setUrlValidation(null);
    }
  };

  const handleRefresh = async (binding: RepoBindingDetail) => {
    setActionError(null);
    setSyncingId(binding.id);
    const action = async () => {
      try {
        await refreshRepoBinding(binding.id);
        await queryClient.invalidateQueries({ queryKey: ['project-repo-bindings', projectKey] });
      } finally {
        setSyncingId(null);
      }
    };

    try {
      await action();
    } catch (err: unknown) {
      if (isAal2StepUpCancelled(err) || onAal2Intercept?.(err, { type: 'refresh_repo', execute: action })) {
        setSyncingId(null);
        return;
      }
      const msg = err instanceof Error ? err.message : 'Failed to refresh repository mirror.';
      setActionError(msg);
      setSyncingId(null);
    }
  };

  const handleDelete = async (binding: RepoBindingDetail) => {
    if (!window.confirm(`Are you sure you want to remove git mirror '${binding.slug}'?`)) {
      return;
    }

    setActionError(null);
    setDeletingId(binding.id);
    const action = async () => {
      try {
        await deleteRepoBinding(binding.id);
        await queryClient.invalidateQueries({ queryKey: ['project-repo-bindings', projectKey] });
      } finally {
        setDeletingId(null);
      }
    };

    try {
      await action();
    } catch (err: unknown) {
      if (isAal2StepUpCancelled(err) || onAal2Intercept?.(err, { type: 'delete_repo', execute: action })) {
        setDeletingId(null);
        return;
      }
      const msg = err instanceof Error ? err.message : 'Failed to delete repository mirror.';
      setActionError(msg);
      setDeletingId(null);
    }
  };

  const handleCreateSubmit = async (e: React.SyntheticEvent) => {
    e.preventDefault();
    setFormError(null);

    const trimmedSlug = slug.trim().toLowerCase();
    const slugRegex = /^[a-z0-9][a-z0-9-]{1,62}$/;
    if (!slugRegex.test(trimmedSlug)) {
      setFormError('Slug must be 2-63 lowercase alphanumeric characters or hyphens (starting with alphanumeric).');
      return;
    }

    const validation = validateGitRemoteUrl(remoteUrl);
    if (!validation.valid) {
      setFormError(validation.error ?? 'Invalid git remote URL.');
      return;
    }

    if (credential === 'workspace-pat') {
      const trimmedPat = patToken.trim();
      if (!trimmedPat) {
        setFormError('Personal Access Token (PAT) is required when workspace-pat credential is selected.');
        return;
      }
    }

    const payload: CreateRepoBindingPayload = {
      slug: trimmedSlug,
      remote_url: remoteUrl.trim(),
      default_ref: defaultRef.trim() || 'main',
      access_mode: accessMode,
      ...(credential ? { credential: credential === 'workspace-pat' ? patToken.trim() : credential } : {}),
    };

    setIsSubmitting(true);
    const action = async () => {
      try {
        await createRepoBinding(projectKey, payload);
        await queryClient.invalidateQueries({ queryKey: ['project-repo-bindings', projectKey] });
        setIsModalOpen(false);
        resetForm();
      } finally {
        setIsSubmitting(false);
      }
    };

    try {
      await action();
    } catch (err: unknown) {
      if (isAal2StepUpCancelled(err) || onAal2Intercept?.(err, { type: 'create_repo', execute: action })) {
        setIsSubmitting(false);
        return;
      }
      const msg = err instanceof Error ? err.message : 'Failed to bind git repository.';
      setFormError(msg);
      setIsSubmitting(false);
    }
  };

  return (
    <section className="repo-bindings-section" aria-label="Git Repository Bindings">
      <header className="repo-bindings-header">
        <div className="repo-bindings-title-group">
          <h2 className="repo-bindings-title">
            <span>📦 Git Repository Bindings</span>
            <span className="repo-ro-badge">:ro bare mirror</span>
          </h2>
          <p className="repo-bindings-subtitle">
            Read-only bare mirrors for agent code inspection, diff audits, and verification proof validation.
          </p>
        </div>
        {isUserAdmin && (
          <button
            type="button"
            className="workflow-btn workflow-btn-primary"
            onClick={handleOpenModal}
            aria-label="Bind Git Repository"
          >
            + Bind Git Repository
          </button>
        )}
      </header>

      {actionError && (
        <div className="workflow-alert workflow-alert-danger" role="alert">
          {actionError}
        </div>
      )}

      {isLoading ? (
        <div className="empty-hooks-cta">Loading repository mirrors...</div>
      ) : bindings.length === 0 ? (
        <div className="empty-hooks-cta" data-testid="empty-repo-bindings">
          No git repository mirrors bound to this project. Bind a remote repository to enable bare git tooling and read-only inspection.
        </div>
      ) : (
        <div className="repo-bindings-list">
          {bindings.map((b, index) => {
            const isSyncing = syncingId === b.id;
            const isDeleting = deletingId === b.id;
            return (
              <div
                key={b.id || b.slug || `binding-${String(index)}`}
                className="repo-binding-card"
                data-testid={`repo-card-${b.slug}`}
              >
                <div className="repo-binding-card-header">
                  <div className="repo-binding-slug-group">
                    <span className="repo-binding-slug">{b.slug}</span>
                    <div className="repo-binding-badges">
                      <span className="repo-badge repo-badge-access">
                        {b.access_mode === 'ro_vfs_mount' ? 'VFS Mount (:ro)' : 'Bare Git Tools'}
                      </span>
                      {b.last_fetch_error ? (
                        <span className="repo-badge repo-badge-status-error" title={b.last_fetch_error}>
                          Sync Error
                        </span>
                      ) : isSyncing ? (
                        <span className="repo-badge repo-badge-status-syncing">Syncing...</span>
                      ) : b.last_fetched_commit ? (
                        <span className="repo-badge repo-badge-status-synced">
                          Synced ({b.last_fetched_commit.slice(0, 7)})
                        </span>
                      ) : (
                        <span className="repo-badge repo-badge-status-pending">Pending Sync</span>
                      )}
                    </div>
                  </div>
                  {isUserAdmin && (
                    <div className="repo-binding-actions">
                      <button
                        type="button"
                        className="workflow-btn workflow-btn-secondary workflow-btn-sm"
                        onClick={() => { void handleRefresh(b); }}
                        disabled={isSyncing || isDeleting}
                        aria-label={`Refresh mirror ${b.slug}`}
                      >
                        {isSyncing ? 'Refreshing...' : 'Refresh Mirror'}
                      </button>
                      <button
                        type="button"
                        className="workflow-btn workflow-btn-danger workflow-btn-sm"
                        onClick={() => { void handleDelete(b); }}
                        disabled={isSyncing || isDeleting}
                        aria-label={`Remove mirror ${b.slug}`}
                      >
                        {isDeleting ? 'Removing...' : 'Remove'}
                      </button>
                    </div>
                  )}
                </div>

                <div className="repo-binding-meta">
                  <div className="repo-binding-url-ref">
                    <span className="repo-binding-url">{b.remote_url}</span>
                    <span className="repo-binding-ref">ref: {b.default_ref}</span>
                  </div>
                  {b.last_fetched_at && (
                    <span className="repo-binding-timestamp">
                      Last synced: {new Date(b.last_fetched_at).toLocaleString()}
                    </span>
                  )}
                </div>

                {b.last_fetch_error && (
                  <div className="workflow-alert workflow-alert-danger repo-fetch-error-alert">
                    {b.last_fetch_error}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* Bind Git Repository Modal */}
      {isModalOpen && (
        <div className="workflow-modal-backdrop" role="presentation">
          <div
            className="workflow-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="bind-repo-title"
          >
            <div className="workflow-dialog-header">
              <h2 id="bind-repo-title" className="workflow-dialog-title">
                Bind Git Repository (:ro Bare Mirror)
              </h2>
            </div>

            <form onSubmit={(e) => { void handleCreateSubmit(e); }} className="workflow-dialog-form">
              <div className="workflow-dialog-body">
                {formError && (
                  <div className="workflow-alert workflow-alert-danger" role="alert">
                    {formError}
                  </div>
                )}

                {/* Slug */}
                <div className="workflow-form-group">
                  <label htmlFor="repo-slug-input" className="workflow-form-label">
                    Repository Identifier / Slug (Required)
                  </label>
                  <input
                    id="repo-slug-input"
                    type="text"
                    className="workflow-form-control"
                    placeholder="e.g. core-engine"
                    value={slug}
                    onChange={(e) => { setSlug(e.target.value); }}
                    required
                  />
                  <span className="workflow-notice">
                    Unique project identifier (lowercase alphanumeric with hyphens, 2-63 chars).
                  </span>
                </div>

                {/* Remote URL */}
                <div className="workflow-form-group">
                  <label htmlFor="repo-url-input" className="workflow-form-label">
                    Remote Git URL (Required)
                  </label>
                  <input
                    id="repo-url-input"
                    type="text"
                    className="workflow-form-control"
                    placeholder="https://github.com/org/repo.git or git@github.com:org/repo.git"
                    value={remoteUrl}
                    onChange={(e) => { handleUrlChange(e.target.value); }}
                    required
                  />
                  {urlValidation && (
                    <div
                      className={`repo-url-validation-feedback ${
                        urlValidation.valid ? 'repo-url-valid' : 'repo-url-invalid'
                      }`}
                    >
                      {urlValidation.valid
                        ? 'Valid remote git URL (HTTPS / SSH).'
                        : urlValidation.error}
                    </div>
                  )}
                  <span className="workflow-notice" data-testid="repo-url-ssrf-callout">
                    <strong>SSRF Restrictions:</strong> Only public HTTPS and SSH remote URLs are permitted. Private IP ranges (10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16), loopback addresses (127.0.0.1, localhost), and cloud metadata endpoints (169.254.169.254) are strictly blocked to protect internal infrastructure.
                  </span>
                </div>

                {/* Default Ref */}
                <div className="workflow-form-group">
                  <div className="workflow-form-label-row">
                    <label htmlFor="repo-ref-input" className="workflow-form-label">
                      Default Branch / Ref
                    </label>
                    <FieldHelpHint
                      title="Default Branch / Ref"
                      summary="Default git branch checked out by autonomous agent runners during scripted transitions."
                      defaultValue="main"
                      testId="repo-ref-help"
                      docHref="/docs/scripted-workflows-and-transition-helpers#read-only-bare-git-repository-bindings"
                    />
                  </div>
                  <input
                    id="repo-ref-input"
                    type="text"
                    className="workflow-form-control"
                    placeholder="main"
                    value={defaultRef}
                    onChange={(e) => { setDefaultRef(e.target.value); }}
                  />
                </div>

                {/* Access Mode */}
                <div className="workflow-form-group">
                  <div className="workflow-form-label-row">
                    <label htmlFor="repo-access-select" className="workflow-form-label">
                      Access Mode
                    </label>
                    <FieldHelpHint
                      title="Access Mode"
                      summary="Filesystem mounting and tooling isolation boundary granted to agent transition runners."
                      validValues={[
                        {
                          label: 'Read-Only Virtual Filesystem Mount (:ro VFS)',
                          description:
                            'Materializes a detached, immutable snapshot of the git commit in a read-only VFS mount. Prevents repository tampering while enabling fast file-tree inspection.',
                        },
                        {
                          label: 'Bare Git Tools Only',
                          description:
                            'Provides direct access to bare git porcelain and plumbing commands without mounting a materialized working tree.',
                        },
                      ]}
                      defaultValue="Read-Only Virtual Filesystem Mount (:ro VFS)"
                      testId="repo-access-help"
                      docHref="/docs/scripted-workflows-and-transition-helpers#read-only-bare-git-repository-bindings"
                    />
                  </div>
                  <select
                    id="repo-access-select"
                    className="workflow-form-control"
                    value={accessMode}
                    onChange={(e) => {
                      setAccessMode(e.target.value as 'ro_vfs_mount' | 'bare_git_tools');
                    }}
                  >
                    <option value="ro_vfs_mount">Read-Only Virtual Filesystem Mount (:ro VFS)</option>
                    <option value="bare_git_tools">Bare Git Tools Only</option>
                  </select>
                </div>

                {/* Authentication Credential */}
                <div className="workflow-form-group">
                  <label htmlFor="repo-cred-select" className="workflow-form-label">
                    Authentication Credential / Secret
                  </label>
                  <select
                    id="repo-cred-select"
                    className="workflow-form-control"
                    value={credential}
                    onChange={(e) => { setCredential(e.target.value); }}
                  >
                    <option value="">None (Public Repository)</option>
                    <option value="workspace-pat">Workspace Personal Access Token (PAT)</option>
                    <option value="ssh-key">Workspace Deploy SSH Key</option>
                  </select>
                </div>

                {credential === 'workspace-pat' && (
                  <div className="workflow-form-group" data-testid="repo-pat-group">
                    <label htmlFor="repo-pat-input" className="workflow-form-label">
                      Personal Access Token (PAT)
                    </label>
                    <input
                      id="repo-pat-input"
                      type="text"
                      className="workflow-form-control kb-masked-api-key"
                      data-testid="repo-pat-input"
                      placeholder="ghp_... or glpat-..."
                      value={patToken}
                      onChange={(e) => { setPatToken(e.target.value); }}
                      autoComplete="off"
                      data-1p-ignore="true"
                      data-lpignore="true"
                      data-bwignore="true"
                      data-form-type="other"
                    />
                    <span className="workflow-notice">
                      Token is securely encrypted at rest. Never stored in shell history or logs.
                    </span>
                  </div>
                )}
              </div>

              {/* Actions - Sticky Footer */}
              <div className="workflow-dialog-actions">
                <button
                  type="button"
                  className="workflow-btn workflow-btn-secondary"
                  onClick={handleCloseModal}
                  disabled={isSubmitting}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="workflow-btn workflow-btn-primary"
                  disabled={isSubmitting || (urlValidation !== null && !urlValidation.valid)}
                >
                  {isSubmitting ? 'Binding...' : 'Bind Repository'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </section>
  );
}
