// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import React, { useState, useEffect, useCallback, type JSX } from 'react';
import {
  fetchAiProviders,
  disableAiProvider,
  updateAiProvider,
  deleteAiProvider,
  fetchAirGapMode,
  type ProviderConfigPublic,
} from './aiAdminApi';
import { AiBudgetModal } from './AiBudgetModal';
import { AiProviderEditorDrawer } from './AiProviderEditorDrawer';
import './aiStudio.css';

export function AiStudioPage(): JSX.Element {
  const [providers, setProviders] = useState<ProviderConfigPublic[]>([]);
  const [airGapMode, setAirGapMode] = useState<boolean>(false);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Modals state
  const [selectedBudgetProvider, setSelectedBudgetProvider] = useState<ProviderConfigPublic | null>(null);
  const [editingProvider, setEditingProvider] = useState<ProviderConfigPublic | null>(null);
  const [isDrawerOpen, setIsDrawerOpen] = useState<boolean>(false);
  const [providerToDelete, setProviderToDelete] = useState<ProviderConfigPublic | null>(null);

  const [reloadCounter, setReloadCounter] = useState<number>(0);

  useEffect(() => {
    let active = true;

    async function load() {
      try {
        const [provList, isAirGap] = await Promise.all([
          fetchAiProviders(),
          fetchAirGapMode(),
        ]);
        if (!active) return;
        setProviders(provList);
        setAirGapMode(isAirGap);
      } catch (err: unknown) {
        if (!active) return;
        setError(err instanceof Error ? err.message : 'Failed to load AI providers');
      } finally {
        if (active) {
          setIsLoading(false);
        }
      }
    }

    void load();

    return () => {
      active = false;
    };
  }, [reloadCounter]);

  const refreshData = useCallback((): void => {
    setReloadCounter((c) => c + 1);
  }, []);

  const handleToggleEnable = async (provider: ProviderConfigPublic): Promise<void> => {
    try {
      if (provider.is_enabled) {
        await disableAiProvider(provider.id);
      } else {
        await updateAiProvider(provider.id, { is_enabled: true });
      }
      refreshData();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to toggle provider enablement');
    }
  };

  const handleConfirmDelete = async (): Promise<void> => {
    if (!providerToDelete) return;
    try {
      await deleteAiProvider(providerToDelete.id);
      setProviderToDelete(null);
      refreshData();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to delete provider');
    }
  };

  return (
    <section className="kb-ai-studio" data-testid="ai-studio-page">
      <div className="kb-ai-studio-header">
        <div className="kb-ai-studio-title-group">
          <h1>
            <span aria-hidden="true">🧠</span> AI Providers & Token Caps Studio
          </h1>
          <p className="kb-ai-studio-subtitle">
            Configure workspace LLM providers, model allowlists, monthly token caps, and zero-egress policies.
          </p>
        </div>

        <button
          type="button"
          className="kb-btn kb-btn-primary"
          onClick={() => {
            setEditingProvider(null);
            setIsDrawerOpen(true);
          }}
          data-testid="register-provider-btn"
        >
          + Register Provider
        </button>
      </div>

      {airGapMode && (
        <div className="kb-air-gap-banner" data-testid="air-gap-active-banner">
          <span className="kb-air-gap-banner-icon" aria-hidden="true">
            🛡️
          </span>
          <div className="kb-air-gap-banner-content">
            <strong>Enterprise Air-Gap Mode Active</strong>
            Cloud AI providers (OpenAI, Gemini) are blocked by enterprise security policy. Only local zero-egress runtimes (Ollama) are authorized for completions.
          </div>
        </div>
      )}

      {error && (
        <div className="kb-form-hint" style={{ color: '#ef4444' }} data-testid="ai-studio-error">
          {error}
        </div>
      )}

      {isLoading ? (
        <div className="kb-loading-state" data-testid="ai-studio-loading">
          Loading AI providers...
        </div>
      ) : providers.length === 0 ? (
        <div
          style={{
            padding: '32px',
            textAlign: 'center',
            backgroundColor: 'var(--kb-color-bg-surface, #ffffff)',
            borderRadius: '8px',
            border: '1px dashed var(--kb-color-border-subtle, #d1d5db)',
          }}
          data-testid="empty-providers-placeholder"
        >
          <p style={{ margin: 0, color: 'var(--kb-color-text-secondary, #4b5563)' }}>
            No AI providers configured yet. Click <strong>+ Register Provider</strong> to add one.
          </p>
        </div>
      ) : (
        <div className="kb-providers-grid" data-testid="providers-grid">
          {providers.map((p) => {
            const isCloud = p.provider_kind === 'openai' || p.provider_kind === 'gemini';
            const isBlockedByAirGap = airGapMode && isCloud;

            return (
              <div
                key={p.id}
                className="kb-provider-card"
                data-testid={`provider-card-${p.id}`}
              >
                <div>
                  <div className="kb-provider-card-header">
                    <span
                      className={`kb-provider-kind-badge kb-provider-kind--${p.provider_kind}`}
                      data-testid={`provider-kind-badge-${p.provider_kind}`}
                    >
                      {p.provider_kind}
                    </span>
                    <button
                      type="button"
                      className={`kb-btn ${p.is_enabled ? 'kb-btn-secondary' : 'kb-btn-primary'}`}
                      style={{ padding: '2px 8px', fontSize: '11px', minHeight: '30px' }}
                      onClick={() => { void handleToggleEnable(p); }}
                      disabled={isBlockedByAirGap && !p.is_enabled}
                      data-testid={`toggle-enable-btn-${p.id}`}
                    >
                      {p.is_enabled ? 'Enabled' : 'Disabled'}
                    </button>
                  </div>

                  <h3 className="kb-provider-card-name">{p.display_name}</h3>

                  <div className="kb-provider-card-meta">
                    <div className="kb-provider-meta-row">
                      <span>Priority:</span>
                      <code>{p.priority}</code>
                      <span>Tier:</span>
                      <code>{p.residency_tier}</code>
                    </div>

                    {p.base_url && (
                      <div className="kb-provider-meta-row">
                        <span>URL:</span>
                        <code>{p.base_url}</code>
                      </div>
                    )}

                    <div className="kb-provider-meta-row">
                      <span>API Key:</span>
                      <span
                        style={{
                          color: p.api_key_set ? '#059669' : '#dc2626',
                          fontWeight: 500,
                        }}
                        data-testid={`key-status-${p.id}`}
                      >
                        {p.api_key_set ? '🔒 Key Configured (Write-Only)' : '⚠️ Key Not Set'}
                      </span>
                    </div>

                    {isBlockedByAirGap && (
                      <div className="kb-provider-meta-row" style={{ color: '#b45309' }}>
                        <span>⚠️ Blocked by Air-Gap mode</span>
                      </div>
                    )}

                    <div>
                      <span>Allowed Models:</span>
                      <div className="kb-provider-models-list">
                        {p.model_allowlist.map((m) => (
                          <span key={m} className="kb-model-chip">
                            {m}
                          </span>
                        ))}
                      </div>
                    </div>
                  </div>
                </div>

                <div className="kb-provider-card-actions">
                  <button
                    type="button"
                    className="kb-btn kb-btn-secondary"
                    onClick={() => { setSelectedBudgetProvider(p); }}
                    data-testid={`manage-budget-btn-${p.id}`}
                  >
                    Token Budget
                  </button>

                  <button
                    type="button"
                    className="kb-btn kb-btn-secondary"
                    onClick={() => {
                      setEditingProvider(p);
                      setIsDrawerOpen(true);
                    }}
                    data-testid={`edit-provider-btn-${p.id}`}
                  >
                    Edit
                  </button>

                  <button
                    type="button"
                    className="kb-btn kb-btn-danger"
                    onClick={() => { setProviderToDelete(p); }}
                    data-testid={`delete-provider-btn-${p.id}`}
                  >
                    Delete
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Token Budget Modal */}
      <AiBudgetModal
        isOpen={selectedBudgetProvider !== null}
        onClose={() => { setSelectedBudgetProvider(null); }}
        provider={selectedBudgetProvider}
        onBudgetUpdated={refreshData}
      />

      {/* Editor Drawer */}
      <AiProviderEditorDrawer
        isOpen={isDrawerOpen}
        onClose={() => {
          setIsDrawerOpen(false);
          setEditingProvider(null);
        }}
        provider={editingProvider}
        airGapMode={airGapMode}
        onSaved={refreshData}
      />

      {/* Delete Confirmation Modal */}
      {providerToDelete && (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="delete-provider-title"
          className="kb-modal-backdrop"
          data-testid="delete-provider-modal"
        >
          <div className="kb-modal-card">
            <h2 id="delete-provider-title" style={{ margin: '0 0 12px 0' }}>
              Confirm Provider Deletion
            </h2>
            <p style={{ margin: '0 0 20px 0' }}>
              Are you sure you want to delete <strong>{providerToDelete.display_name}</strong>? Any automated agents or completions relying on this provider will fall back to secondary providers.
            </p>
            <div className="kb-modal-footer">
              <button
                type="button"
                className="kb-btn kb-btn-secondary"
                onClick={() => { setProviderToDelete(null); }}
                data-testid="cancel-delete-provider-btn"
              >
                Cancel
              </button>
              <button
                type="button"
                className="kb-btn kb-btn-danger"
                onClick={() => { void handleConfirmDelete(); }}
                data-testid="confirm-delete-provider-btn"
              >
                Delete Provider
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}

export default AiStudioPage;
