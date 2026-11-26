// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import React, { useState, useEffect, useCallback, useRef, type JSX } from 'react';
import { apiFetch, isAal2StepUpCancelled } from '../../api/client';
import { FieldHelpHint } from '../../components/help/FieldHelpHint';
import { StudioDocLink } from '../../components/help/StudioDocLink';
import { useAal2DirtyKeepalive } from '../../components/help/WebSudoModalHost';
import { AdvancedSection } from '../../ui/AdvancedSection';
import { McpAccessStudio } from './McpAccessStudio';
import './McpAccessStudio.css';

export interface WorkloadIdentityPolicyItem {
  id: string;
  workspace_id: string;
  name: string;
  description: string | null;
  issuer: string;
  client_id: string;
  subject_pattern: string;
  required_claims_json: Record<string, unknown>;
  surface: 'agent' | 'docs';
  scopes: string[];
  allowed_project_ids: string[];
  capability_mask: number;
  allowed_cidrs: string[];
  max_ttl_seconds: number;
  is_enabled: boolean;
  created_by_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface WorkloadPolicyCreatePayload {
  name: string;
  description?: string | undefined;
  issuer: string;
  client_id: string;
  subject_pattern: string;
  required_claims_json?: Record<string, unknown> | undefined;
  surface: 'agent' | 'docs';
  scopes?: string[] | undefined;
  allowed_project_ids?: string[] | undefined;
  capability_mask?: number | undefined;
  allowed_cidrs?: string[] | undefined;
  max_ttl_seconds?: number | undefined;
}

export interface WorkloadPolicyUpdatePayload {
  name?: string | undefined;
  description?: string | undefined;
  subject_pattern?: string | undefined;
  required_claims_json?: Record<string, unknown> | undefined;
  scopes?: string[] | undefined;
  allowed_project_ids?: string[] | undefined;
  capability_mask?: number | undefined;
  allowed_cidrs?: string[] | undefined;
  max_ttl_seconds?: number | undefined;
  is_enabled?: boolean | undefined;
}

export interface WorkloadFederationSectionProps {
  isAdmin?: boolean;
}

export function WorkloadFederationSection({
  isAdmin = false,
}: WorkloadFederationSectionProps): JSX.Element {
  const [policies, setPolicies] = useState<WorkloadIdentityPolicyItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Modal state
  const [showModal, setShowModal] = useState(false);
  const [editingPolicy, setEditingPolicy] = useState<WorkloadIdentityPolicyItem | null>(null);
  const [formName, setFormName] = useState('');
  const [formDesc, setFormDesc] = useState('');
  const [formIssuer, setFormIssuer] = useState('');
  const [formClientId, setFormClientId] = useState('');
  const [formSubjectPattern, setFormSubjectPattern] = useState('');
  const [formSurface, setFormSurface] = useState<'agent' | 'docs'>('agent');
  const [formCapMask, setFormCapMask] = useState('255');
  const [formCidrs, setFormCidrs] = useState('');
  const [formTtl, setFormTtl] = useState('3600');
  const [submitting, setSubmitting] = useState(false);
  const isMountedRef = useRef(true);

  const isDirty = showModal && Boolean(formName || formIssuer || formClientId || formDesc);
  useAal2DirtyKeepalive(isDirty);

  useEffect(() => {
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
    };
  }, []);

  const fetchPolicies = useCallback(async (): Promise<void> => {
    if (!isAdmin) return;
    if (isMountedRef.current) {
      setLoading(true);
      setError(null);
    }
    try {
      const data = (await apiFetch(
        'GET',
        '/api/v1/admin/workload-identities',
      )) as WorkloadIdentityPolicyItem[] | undefined;
      if (isMountedRef.current) {
        setPolicies(Array.isArray(data) ? data : []);
      }
    } catch (err) {
      if (isMountedRef.current) {
        if (isAal2StepUpCancelled(err)) return;
        setError(err instanceof Error ? err.message : 'Failed to load workload policies');
      }
    } finally {
      if (isMountedRef.current) {
        setLoading(false);
      }
    }
  }, [isAdmin]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void fetchPolicies();
  }, [fetchPolicies]);

  const handleOpenCreate = (): void => {
    setEditingPolicy(null);
    setFormName('');
    setFormDesc('');
    setFormIssuer('');
    setFormClientId('');
    setFormSubjectPattern('*');
    setFormSurface('agent');
    setFormCapMask('255');
    setFormCidrs('');
    setFormTtl('3600');
    setShowModal(true);
  };

  const handleOpenEdit = (pol: WorkloadIdentityPolicyItem): void => {
    setEditingPolicy(pol);
    setFormName(pol.name);
    setFormDesc(pol.description ?? '');
    setFormIssuer(pol.issuer);
    setFormClientId(pol.client_id);
    setFormSubjectPattern(pol.subject_pattern);
    setFormSurface(pol.surface);
    setFormCapMask(String(pol.capability_mask));
    setFormCidrs(pol.allowed_cidrs.join(', '));
    setFormTtl(String(pol.max_ttl_seconds));
    setShowModal(true);
  };

  const handleSubmit = async (e: React.SyntheticEvent): Promise<void> => {
    e.preventDefault();
    setSubmitting(true);
    setError(null);

    const parsedCidrs = formCidrs
      .split(',')
      .map((c) => c.trim())
      .filter(Boolean);
    const rawCap = parseInt(formCapMask, 10);
    const parsedCapMask = Number.isNaN(rawCap) ? 255 : rawCap;
    const rawTtl = parseInt(formTtl, 10);
    const parsedTtl = Number.isNaN(rawTtl) ? 3600 : rawTtl;

    const action = async (): Promise<void> => {
      try {
        if (editingPolicy) {
          const payload: WorkloadPolicyUpdatePayload = {
            name: formName.trim(),
            description: formDesc.trim() || undefined,
            subject_pattern: formSubjectPattern.trim(),
            capability_mask: parsedCapMask,
            allowed_cidrs: parsedCidrs,
            max_ttl_seconds: parsedTtl,
          };
          await apiFetch(
            'PATCH',
            `/api/v1/admin/workload-identities/${editingPolicy.id}` as unknown as keyof import('../../api/schema.gen.ts').paths,
            { body: payload },
          );
        } else {
          const payload: WorkloadPolicyCreatePayload = {
            name: formName.trim(),
            description: formDesc.trim() || undefined,
            issuer: formIssuer.trim(),
            client_id: formClientId.trim(),
            subject_pattern: formSubjectPattern.trim(),
            surface: formSurface,
            capability_mask: parsedCapMask,
            allowed_cidrs: parsedCidrs,
            max_ttl_seconds: parsedTtl,
          };
          await apiFetch(
            'POST',
            '/api/v1/admin/workload-identities',
            { body: payload },
          );
        }
        setShowModal(false);
        await fetchPolicies();
      } catch (err) {
        if (isAal2StepUpCancelled(err)) return;
        setError(err instanceof Error ? err.message : 'Failed to save workload policy');
      } finally {
        setSubmitting(false);
      }
    };

    await action();
  };

  const handleToggle = async (pol: WorkloadIdentityPolicyItem): Promise<void> => {
    setError(null);
    try {
      await apiFetch(
        'PATCH',
        `/api/v1/admin/workload-identities/${pol.id}` as unknown as keyof import('../../api/schema.gen.ts').paths,
        { body: { is_enabled: !pol.is_enabled } },
      );
      await fetchPolicies();
    } catch (err) {
      if (isAal2StepUpCancelled(err)) return;
      setError(err instanceof Error ? err.message : 'Failed to toggle policy');
    }
  };

  const handleDelete = async (policyId: string): Promise<void> => {
    setError(null);
    try {
      await apiFetch(
        'DELETE',
        `/api/v1/admin/workload-identities/${policyId}` as unknown as keyof import('../../api/schema.gen.ts').paths,
      );
      await fetchPolicies();
    } catch (err) {
      if (isAal2StepUpCancelled(err)) return;
      setError(err instanceof Error ? err.message : 'Failed to delete policy');
    }
  };

  if (!isAdmin) {
    return <></>;
  }

  return (
    <div className="kb-mcp-studio-section" data-testid="workload-federation-section">
      <div className="kb-mcp-studio-header">
        <div>
          <h2 className="kb-mcp-section-title">
            <span>Workload Identity Federation (RFC 8693)</span>
            <FieldHelpHint
              title="Workload Identity Federation"
              summary="Enables keyless OIDC JWT token exchange (RFC 8693) for CI/CD pipelines (GitHub Actions, GitLab CI) and Kubernetes workloads to acquire scoped MCP credentials without long-lived static secrets."
              docHref="/docs/zero-trust-service-auth-and-workload-oidc"
              testId="workload-federation-header-help"
            />
          </h2>
          <p className="kb-mcp-studio-subtitle">
            Configure headless CI/CD runners (GitHub Actions, GitLab CI, Kubernetes) to exchange OIDC JWT tokens for scoped MCP credentials without long-lived static secrets.
          </p>
        </div>
        <div className="kb-mcp-header-actions">
          <StudioDocLink
            href="/docs/zero-trust-service-auth-and-workload-oidc"
            title="Workload Identity Federation Documentation"
            testId="workload-federation-doc-link"
          />
          <button
            type="button"
            className="kb-mcp-studio-mint-btn"
            data-testid="add-workload-policy-btn"
            onClick={handleOpenCreate}
          >
            + Add Workload Policy
          </button>
        </div>
      </div>

      {error && (
        <div className="kb-mcp-error-banner" data-testid="workload-error-banner">
          {error}
        </div>
      )}

      {loading && <div data-testid="workload-loading">Loading policies...</div>}

      {!loading && policies.length === 0 && (
        <div className="kb-mcp-empty-state" data-testid="workload-empty-state">
          No workload identity federation policies configured yet.
        </div>
      )}

      {!loading && policies.length > 0 && (
        <div className="kb-mcp-table-wrap">
          <table className="kb-mcp-table" data-testid="workload-policies-table">
            <thead>
              <tr>
                <th className="kb-mcp-th">Policy</th>
                <th className="kb-mcp-th">Issuer & Audience</th>
                <th className="kb-mcp-th">Subject Pattern</th>
                <th className="kb-mcp-th">Surface / Cap</th>
                <th className="kb-mcp-th">Allowed CIDRs</th>
                <th className="kb-mcp-th">Status</th>
                <th className="kb-mcp-th">Actions</th>
              </tr>
            </thead>
            <tbody>
              {policies.map((p) => (
                <tr key={p.id} className="kb-mcp-tr" data-testid={`workload-row-${p.id}`}>
                  <td className="kb-mcp-td">
                    <strong>{p.name}</strong>
                    {p.description && (
                      <div className="kb-mcp-studio-subtitle">{p.description}</div>
                    )}
                  </td>
                  <td className="kb-mcp-td">
                    <div><code>{p.issuer}</code></div>
                    <div className="kb-mcp-key-hint">{p.client_id}</div>
                  </td>
                  <td className="kb-mcp-td">
                    <code>{p.subject_pattern}</code>
                  </td>
                  <td className="kb-mcp-td">
                    <span className={`kb-mcp-tier-badge kb-mcp-tier-${p.surface}`}>
                      {p.surface}
                    </span>
                    <span className="kb-mcp-key-hint">Cap: {p.capability_mask}</span>
                  </td>
                  <td className="kb-mcp-td">
                    {p.allowed_cidrs.length > 0 ? (
                      <code>{p.allowed_cidrs.join(', ')}</code>
                    ) : (
                      <span>Any</span>
                    )}
                  </td>
                  <td className="kb-mcp-td">
                    <span
                      className={`kb-mcp-tier-badge ${
                        p.is_enabled ? 'kb-mcp-tier-workspace' : 'kb-mcp-tier-personal'
                      }`}
                      data-testid={`policy-status-${p.id}`}
                    >
                      {p.is_enabled ? 'Active' : 'Disabled'}
                    </span>
                  </td>
                  <td className="kb-mcp-td kb-mcp-actions-cell">
                    <button
                      type="button"
                      className="kb-mcp-action-btn"
                      data-testid={`toggle-policy-btn-${p.id}`}
                      onClick={() => void handleToggle(p)}
                    >
                      {p.is_enabled ? 'Disable' : 'Enable'}
                    </button>
                    <button
                      type="button"
                      className="kb-mcp-action-btn"
                      data-testid={`edit-policy-btn-${p.id}`}
                      onClick={() => { handleOpenEdit(p); }}
                    >
                      Edit
                    </button>
                    <button
                      type="button"
                      className="kb-mcp-btn-danger"
                      data-testid={`delete-policy-btn-${p.id}`}
                      onClick={() => void handleDelete(p.id)}
                    >
                      Delete
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Create / Edit Modal */}
      {showModal && (
        <div className="kb-snippet-modal-backdrop" data-testid="workload-policy-modal">
          <div
            className="kb-snippet-modal-card"
            role="dialog"
            aria-modal="true"
            aria-labelledby="workload-modal-title"
          >
            <div className="kb-snippet-modal-header">
              <h2 id="workload-modal-title" className="kb-snippet-modal-title">
                {editingPolicy ? 'Edit Workload Policy' : 'Create Workload Identity Policy'}
              </h2>
              <button
                type="button"
                className="kb-snippet-modal-close-btn"
                onClick={() => { setShowModal(false); }}
              >
                x
              </button>
            </div>
            <form onSubmit={(e) => void handleSubmit(e)}>
              {!editingPolicy && (
                <div
                  className="kb-mcp-presets-bar"
                  data-testid="workload-presets-bar"
                  style={{ display: 'flex', gap: '8px', marginBottom: '16px', alignItems: 'center', flexWrap: 'wrap' }}
                >
                  <span style={{ fontSize: '12px', fontWeight: 600, color: 'var(--kb-color-text-secondary, #8b949e)' }}>
                    1-Click Presets:
                  </span>
                  <button
                    type="button"
                    className="kb-mcp-filter-pill"
                    data-testid="preset-github-actions"
                    onClick={() => {
                      if (!formName) setFormName('GitHub Actions CI');
                      setFormIssuer('https://token.actions.githubusercontent.com');
                      setFormClientId(window.location.origin);
                      setFormSubjectPattern('repo:org/repo:ref:refs/heads/*');
                      setFormSurface('agent');
                    }}
                  >
                    GitHub Actions
                  </button>
                  <button
                    type="button"
                    className="kb-mcp-filter-pill"
                    data-testid="preset-gitlab-ci"
                    onClick={() => {
                      if (!formName) setFormName('GitLab CI');
                      setFormIssuer('https://gitlab.com');
                      setFormClientId(window.location.origin);
                      setFormSubjectPattern('project_path:group/project:ref:*:ref_type:branch');
                      setFormSurface('agent');
                    }}
                  >
                    GitLab CI
                  </button>
                  <button
                    type="button"
                    className="kb-mcp-filter-pill"
                    data-testid="preset-kubernetes"
                    onClick={() => {
                      if (!formName) setFormName('Kubernetes Workload');
                      setFormIssuer('https://kubernetes.default.svc.cluster.local');
                      setFormClientId(window.location.origin);
                      setFormSubjectPattern('system:serviceaccount:default:*');
                      setFormSurface('agent');
                    }}
                  >
                    Kubernetes
                  </button>
                </div>
              )}
              <div className="kb-mcp-form-row">
                <label className="kb-mcp-form-label" htmlFor="wl-policy-name">Policy Name *</label>
                <input
                  id="wl-policy-name"
                  type="text"
                  className="kb-mcp-form-input"
                  data-testid="policy-name-input"
                  required
                  value={formName}
                  onChange={(e) => { setFormName(e.target.value); }}
                />
              </div>

              <div className="kb-mcp-form-row">
                <label className="kb-mcp-form-label" htmlFor="wl-policy-desc">Description</label>
                <input
                  id="wl-policy-desc"
                  type="text"
                  className="kb-mcp-form-input"
                  data-testid="policy-description-input"
                  value={formDesc}
                  onChange={(e) => { setFormDesc(e.target.value); }}
                />
              </div>

              {!editingPolicy && (
                <>
                  <div className="kb-mcp-form-row">
                    <label className="kb-mcp-form-label" htmlFor="wl-policy-issuer">Issuer URL *</label>
                    <input
                      id="wl-policy-issuer"
                      type="url"
                      className="kb-mcp-form-input"
                      data-testid="policy-issuer-input"
                      required
                      placeholder="https://token.actions.githubusercontent.com"
                      value={formIssuer}
                      onChange={(e) => { setFormIssuer(e.target.value); }}
                    />
                  </div>

                  <div className="kb-mcp-form-row">
                    <label className="kb-mcp-form-label" htmlFor="wl-policy-client-id">Client ID / Audience *</label>
                    <input
                      id="wl-policy-client-id"
                      type="text"
                      className="kb-mcp-form-input"
                      data-testid="policy-client-id-input"
                      required
                      placeholder="https://kanban.example.com"
                      value={formClientId}
                      onChange={(e) => { setFormClientId(e.target.value); }}
                    />
                  </div>

                  <div className="kb-mcp-form-row">
                    <label className="kb-mcp-form-label" htmlFor="wl-policy-surface">Surface *</label>
                    <select
                      id="wl-policy-surface"
                      className="kb-mcp-form-select"
                      data-testid="policy-surface-select"
                      value={formSurface}
                      onChange={(e) => { setFormSurface(e.target.value as 'agent' | 'docs'); }}
                    >
                      <option value="agent">Agent (/mcp/agent)</option>
                      <option value="docs">Docs (/mcp/docs)</option>
                    </select>
                  </div>
                </>
              )}

              <div className="kb-mcp-form-row">
                <label className="kb-mcp-form-label" htmlFor="wl-policy-subject-pattern">Subject Pattern *</label>
                <input
                  id="wl-policy-subject-pattern"
                  type="text"
                  className="kb-mcp-form-input"
                  data-testid="policy-subject-pattern-input"
                  required
                  placeholder="repo:org/repo:ref:refs/heads/*"
                  value={formSubjectPattern}
                  onChange={(e) => { setFormSubjectPattern(e.target.value); }}
                />
              </div>

              <AdvancedSection
                title="Advanced Parameters"
                summary="Capability mask ceilings, allowed CIDR ranges, and token TTL"
                testId="workload-advanced-section"
                defaultOpen={Boolean(editingPolicy)}
                activeOverridesCount={
                  (formCapMask !== '255' ? 1 : 0) +
                  (formCidrs.trim() ? 1 : 0) +
                  (formTtl !== '3600' ? 1 : 0)
                }
              >
                <div className="kb-mcp-form-row">
                  <label className="kb-mcp-form-label" htmlFor="wl-policy-cap-mask">
                    Capability Mask (0-255)
                    <FieldHelpHint
                      title="Capability Mask"
                      summary="Bitmask ceiling governing allowed Model Context Protocol operations."
                      defaultValue="31 (Standard Developer Agent)"
                      validValues={['0 to 255']}
                      docHref="/docs/three-surface-mcp-server-architecture#scope-tiers"
                      testId="policy-cap-mask-help"
                    />
                  </label>
                  <input
                    id="wl-policy-cap-mask"
                    type="number"
                    className="kb-mcp-form-input"
                    data-testid="policy-cap-mask-input"
                    min="0"
                    max="255"
                    value={formCapMask}
                    onChange={(e) => { setFormCapMask(e.target.value); }}
                  />
                </div>

                <div className="kb-mcp-form-row">
                  <label className="kb-mcp-form-label" htmlFor="wl-policy-cidrs">Allowed CIDRs (comma-separated)</label>
                  <input
                    id="wl-policy-cidrs"
                    type="text"
                    className="kb-mcp-form-input"
                    data-testid="policy-cidrs-input"
                    placeholder="192.168.1.0/24, 10.0.0.0/8"
                    value={formCidrs}
                    onChange={(e) => { setFormCidrs(e.target.value); }}
                  />
                </div>

                <div className="kb-mcp-form-row">
                  <label className="kb-mcp-form-label" htmlFor="wl-policy-ttl">
                    Max TTL Seconds
                    <FieldHelpHint
                      title="Max TTL Seconds"
                      summary="Maximum allowed token lifetime in seconds for exchanged workload identity tokens."
                      defaultValue="3600 seconds (1 hour)"
                      validValues={['60 to 86400 seconds']}
                      docHref="/docs/three-surface-mcp-server-architecture#scope-tiers"
                      testId="policy-ttl-help"
                    />
                  </label>
                  <input
                    id="wl-policy-ttl"
                    type="number"
                    className="kb-mcp-form-input"
                    data-testid="policy-ttl-input"
                    min="60"
                    max="86400"
                    value={formTtl}
                    onChange={(e) => { setFormTtl(e.target.value); }}
                  />
                </div>
              </AdvancedSection>

              <div className="kb-mcp-form-actions">
                <button
                  type="button"
                  className="kb-snippet-copy-btn"
                  data-testid="policy-cancel-btn"
                  onClick={() => { setShowModal(false); }}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="kb-snippet-done-btn"
                  data-testid="policy-submit-btn"
                  disabled={submitting}
                >
                  {submitting ? 'Saving...' : 'Save Policy'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

export { McpAccessStudio as McpUnifiedStudio };
export * from './McpAccessStudio';
