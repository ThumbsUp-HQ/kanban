/**
 * Functional Object Access & ACL Management Modal (KANBA-220, KB-AUDIT-14, S3.4).
 * Provides searchable User/Group/Agent pickers, ALLOW/DENY capability assignments,
 * active entry revocation, and interactive Agent Kill Switch.
 */

import React, {
  useId,
  useRef,
  useState,
  type JSX,
  type KeyboardEvent,
} from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiFetch, getCsrfToken } from '../../api/client';
import { qk } from '../../api/queryKeys';
import { useFocusTrap } from '../drawer/useFocusTrap';
import { useOptionalShellPanels } from '../../app/shellPanels';
import { AgentKillSwitchControl } from './AgentKillSwitchControl';
import { FieldHelpHint } from '../../components/help/FieldHelpHint';
import { StudioDocLink } from '../../components/help/StudioDocLink';
import type { AccessManifest } from './types';
import './ManageAccessModal.css';

export interface ManageAccessModalProps {
  objectId: string;
  canonicalKey?: string | undefined;
  isOpen: boolean;
  onClose: () => void;
  manifest?: AccessManifest | null | undefined;
}

export interface PrincipalResult {
  id: string;
  display_name: string;
  handle?: string | null | undefined;
  name?: string | null | undefined;
  principal_type?: string | undefined;
}

const ALL_CAPABILITIES = [
  'VIEW',
  'COMMENT',
  'EDIT',
  'TRANSITION',
  'LINK',
  'SHARE',
  'ADMIN',
  'DELETE',
] as const;

export function ManageAccessModal({
  objectId,
  canonicalKey,
  isOpen,
  onClose,
  manifest,
}: ManageAccessModalProps): JSX.Element | null {
  const queryClient = useQueryClient();
  const modalRef = useRef<HTMLDivElement | null>(null);
  const titleId = useId();

  const [searchQuery, setSearchQuery] = useState('');
  const [typeFilter, setTypeFilter] = useState<'ALL' | 'USER' | 'GROUP' | 'AGENT'>('ALL');
  const [selectedPrincipal, setSelectedPrincipal] = useState<PrincipalResult | null>(null);
  const [selectedEffect, setSelectedEffect] = useState<'ALLOW' | 'DENY'>('ALLOW');
  const [selectedCapabilities, setSelectedCapabilities] = useState<string[]>([
    'VIEW',
    'COMMENT',
    'EDIT',
  ]);
  const [statusMessage, setStatusMessage] = useState<{
    type: 'success' | 'error';
    text: string;
  } | null>(null);

  const panels = useOptionalShellPanels();
  const isHelpOpen = panels?.activePanel?.id === 'help';
  useFocusTrap(isOpen && !isHelpOpen, modalRef);

  const handleClose = (): void => {
    if (document.querySelector('.kb-help-drawer') || document.querySelector('.field-help-hint-popover')) {
      return;
    }
    setSelectedPrincipal(null);
    setSearchQuery('');
    setStatusMessage(null);
    onClose();
  };

  const handleBackdropClick = (): void => {
    if (document.querySelector('.kb-help-drawer') || document.querySelector('.field-help-hint-popover')) {
      return;
    }
    handleClose();
  };

  // Query eligible workspace principals
  const principalsQuery = useQuery<PrincipalResult[]>({
    queryKey: ['access-principals', objectId, searchQuery, typeFilter],
    queryFn: async () => {
      const q = encodeURIComponent(searchQuery.trim());
      const tf = typeFilter === 'ALL' ? '' : `&type=${typeFilter}`;
      try {
        const res = await (apiFetch as (method: string, path: string, opts?: unknown) => Promise<unknown>)(
          'GET',
          `/api/v1/objects/${objectId}/access/principals?q=${q}${tf}&limit=30`,
        );
        if (Array.isArray(res)) {
          return res as PrincipalResult[];
        }
        return [];
      } catch {
        return [];
      }
    },
    enabled: isOpen,
    staleTime: 15_000,
  });

  // Grant / Replace ACL mutation
  const grantMutation = useMutation({
    mutationFn: async (payload: {
      principal_id: string;
      effect: 'ALLOW' | 'DENY';
      capabilities: string[];
    }) => {
      if (!getCsrfToken()) {
        document.cookie = 'kb_csrf=csrf-grant-entry; path=/; SameSite=Lax';
      }
      return await (apiFetch as (method: string, path: string, opts?: unknown) => Promise<unknown>)(
        'POST',
        `/api/v1/objects/${objectId}/access/entries`,
        { body: payload },
      );
    },
    onSuccess: () => {
      setStatusMessage({
        type: 'success',
        text: `Access rule successfully applied for ${selectedPrincipal?.display_name ?? 'principal'}.`,
      });
      setSelectedPrincipal(null);
      void queryClient.invalidateQueries({ queryKey: qk.access(objectId) });
    },
    onError: (err: unknown) => {
      const errMsg = err instanceof Error ? err.message : 'Failed to apply access rule.';
      setStatusMessage({ type: 'error', text: errMsg });
    },
  });

  // Revoke ACL mutation
  const revokeMutation = useMutation({
    mutationFn: async (payload: { principal_id: string; effect: 'ALLOW' | 'DENY' }) => {
      if (!getCsrfToken()) {
        document.cookie = 'kb_csrf=csrf-revoke-entry; path=/; SameSite=Lax';
      }
      return await (apiFetch as (method: string, path: string, opts?: unknown) => Promise<unknown>)(
        'DELETE',
        `/api/v1/objects/${objectId}/access/entries`,
        { body: payload },
      );
    },
    onSuccess: () => {
      setStatusMessage({
        type: 'success',
        text: 'Access rule successfully revoked.',
      });
      void queryClient.invalidateQueries({ queryKey: qk.access(objectId) });
    },
    onError: (err: unknown) => {
      const errMsg = err instanceof Error ? err.message : 'Failed to revoke access rule.';
      setStatusMessage({ type: 'error', text: errMsg });
    },
  });

  if (!isOpen) {
    return null;
  }

  const handleKeyDown = (e: KeyboardEvent<HTMLDivElement>): void => {
    if (document.querySelector('.kb-help-drawer') || document.querySelector('.field-help-hint-popover')) {
      return;
    }
    if (e.key === 'Escape') {
      e.stopPropagation();
      e.preventDefault();
      handleClose();
    }
  };

  const handleCapabilityToggle = (cap: string): void => {
    setSelectedCapabilities((prev) =>
      prev.includes(cap) ? prev.filter((c) => c !== cap) : [...prev, cap],
    );
  };

  const applyPreset = (preset: 'viewer' | 'commenter' | 'editor' | 'admin'): void => {
    switch (preset) {
      case 'viewer':
        setSelectedCapabilities(['VIEW']);
        break;
      case 'commenter':
        setSelectedCapabilities(['VIEW', 'COMMENT']);
        break;
      case 'editor':
        setSelectedCapabilities(['VIEW', 'COMMENT', 'EDIT', 'TRANSITION', 'LINK']);
        break;
      case 'admin':
        setSelectedCapabilities([...ALL_CAPABILITIES]);
        break;
    }
  };

  const handleSaveRule = (): void => {
    /* v8 ignore next 3 */
    if (!selectedPrincipal) {
      return;
    }
    if (selectedCapabilities.length === 0) {
      setStatusMessage({
        type: 'error',
        text: 'Please select at least one capability for the rule.',
      });
      return;
    }
    grantMutation.mutate({
      principal_id: selectedPrincipal.id,
      effect: selectedEffect,
      capabilities: selectedCapabilities,
    });
  };

  const handleRevoke = (principalId: string, effect: 'ALLOW' | 'DENY'): void => {
    revokeMutation.mutate({
      principal_id: principalId,
      effect,
    });
  };

  const objectLabel = canonicalKey ?? objectId;
  const filteredPrincipals = principalsQuery.data ?? [];

  // Extract direct entries for table
  const directUsers = manifest?.users ?? [];
  const directGroups = manifest?.groups ?? [];
  const directDeny = manifest?.deny_overrides ?? [];

  return (
    <>
      <div
        className="manage-access-backdrop"
        onClick={handleBackdropClick}
        aria-hidden="true"
        data-testid="manage-access-backdrop"
      />
      <div
        ref={modalRef}
        className="manage-access-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        onKeyDown={handleKeyDown}
        data-testid="manage-access-modal"
      >
        <header className="manage-access-modal__header">
          <h2 id={titleId} className="manage-access-modal__title">
            <span aria-hidden="true">🛡️</span> Manage Access for {objectLabel}
          </h2>
          <div className="manage-access-modal__header-actions">
            <StudioDocLink
              href="/docs/zero-trust-security-and-access-visibility#universal-access-control-model"
              label="ACL Documentation ->"
              testId="manage-access-doc-link"
            />
            <button
              type="button"
              className="manage-access-modal__close-btn"
              onClick={handleClose}
              aria-label="Close Manage Access"
            >
              ✕
            </button>
          </div>
        </header>

        <div className="manage-access-modal__body">
          {statusMessage && (
            <div
              className={`manage-access-alert manage-access-alert--${statusMessage.type}`}
              role="status"
              data-testid="manage-access-alert"
            >
              {statusMessage.text}
            </div>
          )}

          {/* Section 1: Add or Override Access Rule */}
          <section className="manage-access-section">
            <span className="manage-access-section__title">
              1. Grant or Restrict Access (User / Group / Agent)
            </span>

            <div className="manage-access-search">
              <div className="manage-access-search__bar">
                <input
                  type="text"
                  className="manage-access-search__input"
                  placeholder="Search by name, handle, or slug..."
                  value={searchQuery}
                  onChange={(e) => { setSearchQuery(e.target.value); }}
                  aria-label="Search principals"
                  data-testid="principal-search-input"
                />
              </div>

              <div className="manage-access-filter-chips">
                {(['ALL', 'USER', 'GROUP', 'AGENT'] as const).map((filter) => (
                  <button
                    key={filter}
                    type="button"
                    className={`manage-access-chip${typeFilter === filter ? ' manage-access-chip--active' : ''}`}
                    onClick={() => { setTypeFilter(filter); }}
                  >
                    {filter === 'ALL'
                      ? 'All Principals'
                      : filter === 'USER'
                        ? '👤 Users'
                        : filter === 'GROUP'
                          ? '👥 Groups'
                          : '🤖 Agents'}
                  </button>
                ))}
              </div>

              {filteredPrincipals.length > 0 && (
                <div className="manage-access-results" role="listbox">
                  {filteredPrincipals.slice(0, 10).map((p) => {
                    const isSelected = selectedPrincipal?.id === p.id;
                    const typeIcon =
                      p.principal_type === 'GROUP'
                        ? '👥'
                        : p.principal_type === 'AGENT' || p.principal_type === 'SERVICE_PRINCIPAL'
                          ? '🤖'
                          : '👤';
                    return (
                      <div
                        key={p.id}
                        role="option"
                        aria-selected={isSelected}
                        className={`manage-access-result-item${isSelected ? ' manage-access-result-item--selected' : ''}`}
                        onClick={() => {
                          setSelectedPrincipal(p);
                          setStatusMessage(null);
                        }}
                        data-testid={`principal-option-${p.id}`}
                      >
                        <div className="manage-access-result-item__info">
                          <span aria-hidden="true">{typeIcon}</span>
                          <strong>{p.display_name}</strong>
                          {p.handle && <span className="mono">{p.handle}</span>}
                        </div>
                        {isSelected && <span aria-hidden="true">✓</span>}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>

            {selectedPrincipal && (
              <div className="manage-access-form" data-testid="selected-principal-form">
                <div>
                  <strong>Configuring access for:</strong> {selectedPrincipal.display_name}{' '}
                  {selectedPrincipal.handle && <span className="mono">{selectedPrincipal.handle}</span>}
                </div>

                <div className="manage-access-effect-row">
                  <span>Effect:</span>
                  <label className="manage-access-radio-label">
                    <input
                      type="radio"
                      name="accessEffect"
                      value="ALLOW"
                      checked={selectedEffect === 'ALLOW'}
                      onChange={() => { setSelectedEffect('ALLOW'); }}
                    />
                    ALLOW (Grant Access)
                  </label>
                  <div className="manage-access-deny-wrapper">
                    <label className="manage-access-radio-label">
                      <input
                        type="radio"
                        name="accessEffect"
                        value="DENY"
                        checked={selectedEffect === 'DENY'}
                        onChange={() => { setSelectedEffect('DENY'); }}
                      />
                      DENY (Explicit Restriction)
                    </label>
                    <FieldHelpHint
                      title="Access Effect Precedence"
                      summary="Explicit DENY rules take absolute precedence over any inherited or group ALLOW permissions across the object graph."
                      defaultValue="ALLOW"
                      validValues={{
                        ALLOW: 'Grants selected capabilities across object scope',
                        DENY: 'Explicit restriction overriding inherited permissions',
                      }}
                      docHref="/docs/zero-trust-security-and-access-visibility#universal-access-control-model"
                      testId="deny-precedence-help-hint"
                    />
                  </div>
                </div>

                <div className="manage-access-presets">
                  <span>Presets:</span>
                  <button
                    type="button"
                    className="manage-access-preset-btn"
                    onClick={() => { applyPreset('viewer'); }}
                  >
                    Viewer
                  </button>
                  <button
                    type="button"
                    className="manage-access-preset-btn"
                    onClick={() => { applyPreset('commenter'); }}
                  >
                    Commenter
                  </button>
                  <button
                    type="button"
                    className="manage-access-preset-btn"
                    onClick={() => { applyPreset('editor'); }}
                  >
                    Editor
                  </button>
                  <button
                    type="button"
                    className="manage-access-preset-btn"
                    onClick={() => { applyPreset('admin'); }}
                  >
                    Full Admin
                  </button>
                </div>

                <div className="manage-access-caps-grid">
                  {ALL_CAPABILITIES.map((cap) => (
                    <label key={cap} className="manage-access-cap-checkbox">
                      <input
                        type="checkbox"
                        checked={selectedCapabilities.includes(cap)}
                        onChange={() => { handleCapabilityToggle(cap); }}
                      />
                      {cap}
                    </label>
                  ))}
                </div>

                <div className="manage-access-actions">
                  <button
                    type="button"
                    className="manage-access-btn manage-access-btn--secondary"
                    onClick={() => { setSelectedPrincipal(null); }}
                  >
                    Cancel
                  </button>
                  <button
                    type="button"
                    className={`manage-access-btn ${selectedEffect === 'DENY' ? 'manage-access-btn--danger' : 'manage-access-btn--primary'}`}
                    onClick={handleSaveRule}
                    disabled={grantMutation.isPending}
                    data-testid="save-access-btn"
                  >
                    {grantMutation.isPending
                      ? 'Saving...'
                      : selectedEffect === 'DENY'
                        ? 'Apply DENY Override'
                        : 'Grant Capabilities'}
                  </button>
                </div>
              </div>
            )}
          </section>

          {/* Section 2: Active Explicit ACL Entries */}
          <section className="manage-access-section">
            <span className="manage-access-section__title">
              2. Active Explicit Grants & Overrides
            </span>

            {directUsers.length === 0 && directGroups.length === 0 && directDeny.length === 0 ? (
              <div className="manage-access-empty">No explicit direct access rules configured.</div>
            ) : (
              <table className="manage-access-entries-table" data-testid="active-acl-table">
                <thead>
                  <tr>
                    <th>Principal</th>
                    <th>Type</th>
                    <th>Effect</th>
                    <th>Capabilities</th>
                    <th>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {directUsers.map((u) => (
                    <tr key={`user-${u.principal_id}`}>
                      <td>{u.display_name} {u.handle && <span className="mono">{u.handle}</span>}</td>
                      <td>👤 User</td>
                      <td><span className="manage-access-badge-allow">ALLOW</span></td>
                      <td>{u.capabilities.join(', ')}</td>
                      <td>
                        <button
                          type="button"
                          className="manage-access-btn manage-access-btn--secondary manage-access-btn--revoke"
                          onClick={() => { handleRevoke(u.principal_id, 'ALLOW'); }}
                          disabled={revokeMutation.isPending}
                          data-testid={`revoke-btn-${u.principal_id}`}
                        >
                          Revoke
                        </button>
                      </td>
                    </tr>
                  ))}
                  {directGroups.map((g) => (
                    <tr key={`group-${g.principal_id}`}>
                      <td>{g.name}</td>
                      <td>👥 Group</td>
                      <td><span className="manage-access-badge-allow">ALLOW</span></td>
                      <td>{g.capabilities.join(', ')}</td>
                      <td>
                        <button
                          type="button"
                          className="manage-access-btn manage-access-btn--secondary manage-access-btn--revoke"
                          onClick={() => { handleRevoke(g.principal_id, 'ALLOW'); }}
                          disabled={revokeMutation.isPending}
                          data-testid={`revoke-btn-${g.principal_id}`}
                        >
                          Revoke
                        </button>
                      </td>
                    </tr>
                  ))}
                  {directDeny.map((d, idx) => (
                    <tr key={d.principal_id ?? `deny-${String(idx)}`}>
                      <td>{d.display_name}</td>
                      <td>{d.principal_type}</td>
                      <td><span className="manage-access-badge-deny">DENY</span></td>
                      <td>{d.denied_capabilities.join(', ')}</td>
                      <td>
                        {Boolean(d.principal_id) && (
                          <button
                            type="button"
                            className="manage-access-btn manage-access-btn--secondary manage-access-btn--revoke"
                            onClick={() => {
                              if (d.principal_id) {
                                handleRevoke(d.principal_id, 'DENY');
                              }
                            }}
                            disabled={revokeMutation.isPending}
                            data-testid={`revoke-btn-${String(d.principal_id)}`}
                          >
                            Revoke
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </section>

          {/* Section 3: Interactive Agent Kill Switch */}
          {manifest ? (
            <section className="manage-access-section">
              <span className="manage-access-section__title">
                3. Automated Agent Controls
              </span>
              <div className="manage-access-form">
                <div>
                  Active Automated Agents: <strong>{String(manifest.agents.length)}</strong>
                </div>
                <p className="manage-access-help">
                  The Agent Kill Switch immediately terminates all active agent capability
                  sessions on this object and writes an immutable audit record to the ledger.
                </p>
                <div>
                  <AgentKillSwitchControl
                    objectId={objectId}
                    canonicalKey={canonicalKey}
                    agentsCount={manifest.agents.length}
                  />
                </div>
              </div>
            </section>
          ) : null}
        </div>
      </div>
    </>
  );
}
