// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import React, { useState, useEffect, useCallback, type JSX } from 'react';
import {
  fetchAiProviders,
  disableAiProvider,
  updateAiProvider,
  deleteAiProvider,
  reorderAiProviders,
  testAiConnection,
  fetchAirGapMode,
  isLocalEndpoint,
  type ProviderConfigPublic,
} from './aiAdminApi';
import { AiBudgetModal } from './AiBudgetModal';
import { AiProviderEditorDrawer } from './AiProviderEditorDrawer';
import { StudioDocLink } from '../../components/help/StudioDocLink';
import './aiStudio.css';

interface CardTestStatus {
  kind: 'loading' | 'success' | 'error';
  message: string;
}

export function AiStudioPage(): JSX.Element {
  const [providers, setProviders] = useState<ProviderConfigPublic[]>([]);
  const [airGapMode, setAirGapMode] = useState<boolean>(false);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Card connection test state map
  const [cardTestStatuses, setCardTestStatuses] = useState<Record<string, CardTestStatus>>({});

  // Drag and drop state
  const [draggedIndex, setDraggedIndex] = useState<number | null>(null);
  const [dragOverIndex, setDragOverIndex] = useState<number | null>(null);

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
        const sorted = [...provList].sort((a, b) => a.priority - b.priority);
        setProviders(sorted);
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

  const handleReorder = async (newOrder: ProviderConfigPublic[]): Promise<void> => {
    const previousOrder = [...providers];
    setProviders(newOrder);
    try {
      const orderedIds = newOrder.map((p) => p.id);
      const updated = await reorderAiProviders(orderedIds);
      const sorted = [...updated].sort((a, b) => a.priority - b.priority);
      setProviders(sorted);
    } catch (err: unknown) {
      setProviders(previousOrder);
      setError(err instanceof Error ? err.message : 'Failed to reorder providers');
    }
  };

  const handleMove = (fromIndex: number, toIndex: number): void => {
    if (toIndex < 0 || toIndex >= providers.length) return;
    const copy = [...providers];
    const [moved] = copy.splice(fromIndex, 1);
    if (moved !== undefined) {
      copy.splice(toIndex, 0, moved);
      void handleReorder(copy);
    }
  };

  const handleDragStart = (e: React.DragEvent, index: number): void => {
    const target = e.target as HTMLElement | null;
    if (target?.closest('button, input, select, textarea, a')) {
      e.preventDefault();
      return;
    }
    setDraggedIndex(index);
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData('text/plain', String(index));
  };

  const handleDragEnd = (): void => {
    setDraggedIndex(null);
    setDragOverIndex(null);
  };

  const handleDragOver = (e: React.DragEvent, index: number): void => {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    if (dragOverIndex !== index) {
      setDragOverIndex(index);
    }
  };

  const handleDragLeave = (e: React.DragEvent): void => {
    if (!e.currentTarget.contains(e.relatedTarget as Node | null)) {
      setDragOverIndex(null);
    }
  };

  const handleDrop = (e: React.DragEvent, targetIndex: number): void => {
    e.preventDefault();
    setDragOverIndex(null);
    const fromIndex = draggedIndex;
    setDraggedIndex(null);
    if (fromIndex !== null && fromIndex !== targetIndex) {
      handleMove(fromIndex, targetIndex);
    }
  };

  const handleTestCardConnection = async (provider: ProviderConfigPublic): Promise<void> => {
    setCardTestStatuses((prev) => ({
      ...prev,
      [provider.id]: { kind: 'loading', message: 'Testing connection...' },
    }));

    try {
      const res = await testAiConnection({}, provider.id);
      if (res.ok) {
        setCardTestStatuses((prev) => ({
          ...prev,
          [provider.id]: {
            kind: 'success',
            message: `Connected in ${String(Math.round(res.latency_ms))}ms - ${String(res.model_count)} models available`,
          },
        }));
      } else {
        setCardTestStatuses((prev) => ({
          ...prev,
          [provider.id]: {
            kind: 'error',
            message: `Connection failed: ${res.error_code ?? 'ERROR'}${res.message ? ` - ${res.message}` : ''}`,
          },
        }));
      }
    } catch (err: unknown) {
      setCardTestStatuses((prev) => ({
        ...prev,
        [provider.id]: {
          kind: 'error',
          message: err instanceof Error ? err.message : 'Connection test failed',
        },
      }));
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
            Configure workspace LLM providers, failover priority stack, model allowlists, monthly token caps, and zero-egress policies.
          </p>
        </div>

        <div className="kb-ai-studio-header-actions">
          <StudioDocLink
            href="/docs/multi-provider-ai-engine-and-runners"
            title="Multi-Provider AI Engine Documentation"
            testId="ai-studio-doc-link"
          />
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
        <div className="kb-form-error" data-testid="ai-studio-error">
          {error}
        </div>
      )}

      {isLoading ? (
        <div className="kb-loading-state" data-testid="ai-studio-loading">
          Loading AI providers...
        </div>
      ) : providers.length === 0 ? (
        <div className="kb-empty-placeholder" data-testid="empty-providers-placeholder">
          <p className="kb-empty-placeholder-text">
            No AI providers configured yet. Click <strong>+ Register Provider</strong> to add one.
          </p>
        </div>
      ) : (
        <div className="kb-provider-stack kb-providers-grid" data-testid="providers-stack">
          {providers.map((p, index) => {
            const isCloud = p.provider_kind === 'openai' || p.provider_kind === 'gemini';
            const isLocal = isLocalEndpoint(p.provider_kind, p.base_url);
            const isBlockedByAirGap = airGapMode && isCloud;
            const isDragging = draggedIndex === index;
            const isDragOver = dragOverIndex === index;
            const cardTest = cardTestStatuses[p.id];

            return (
              <div
                key={p.id}
                className={`kb-provider-card kb-provider-stack-item ${isDragging ? 'kb-provider-stack-item--dragging' : ''} ${isDragOver ? 'kb-provider-stack-item--drag-over' : ''}`}
                draggable={true}
                onDragStart={(e) => { handleDragStart(e, index); }}
                onDragEnd={handleDragEnd}
                onDragOver={(e) => { handleDragOver(e, index); }}
                onDragLeave={handleDragLeave}
                onDrop={(e) => { handleDrop(e, index); }}
                data-testid={`provider-card-${p.id}`}
              >
                <div>
                  <div className="kb-provider-card-header">
                    <div className="kb-provider-card-header-left">
                      <div className="kb-provider-order-controls">
                        <span
                          role="img"
                          className="kb-drag-handle"
                          aria-label={`Drag to reorder ${p.display_name}`}
                          data-testid={`drag-handle-${p.id}`}
                        >
                          ⋮⋮
                        </span>
                        <span className="kb-provider-rank" data-testid={`provider-rank-${p.id}`}>
                          #{index + 1}
                        </span>
                        <button
                          type="button"
                          className="kb-btn kb-btn-secondary kb-reorder-btn"
                          onClick={() => { handleMove(index, index - 1); }}
                          disabled={index === 0}
                          aria-label={`Move ${p.display_name} up`}
                          data-testid={`move-up-btn-${p.id}`}
                        >
                          ▲
                        </button>
                        <button
                          type="button"
                          className="kb-btn kb-btn-secondary kb-reorder-btn"
                          onClick={() => { handleMove(index, index + 1); }}
                          disabled={index === providers.length - 1}
                          aria-label={`Move ${p.display_name} down`}
                          data-testid={`move-down-btn-${p.id}`}
                        >
                          ▼
                        </button>
                      </div>

                      <span
                        className={`kb-provider-kind-badge kb-provider-kind--${p.provider_kind}`}
                        data-testid={`provider-kind-badge-${p.provider_kind}`}
                      >
                        {p.provider_kind}
                      </span>

                      <span
                        className={`kb-residency-badge kb-residency-badge--${isLocal ? 'local' : 'cloud'}`}
                        data-testid={`residency-badge-${p.id}`}
                      >
                        {isLocal ? '🏠 Local / Zero-Egress' : '☁️ Cloud'}
                      </span>
                    </div>

                    <button
                      type="button"
                      className={`kb-btn ${p.is_enabled ? 'kb-btn-secondary' : 'kb-btn-primary'} kb-provider-enable-btn`}
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
                      <span>Failover Priority:</span>
                      <code>#{index + 1} (Priority {p.priority})</code>
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
                      {p.api_key_set ? (
                        <span className="kb-key-status kb-key-status--set" data-testid={`key-status-${p.id}`}>
                          🔒 Key Configured (Write-Only)
                        </span>
                      ) : isLocal ? (
                        <span className="kb-key-status kb-key-status--no-key" data-testid={`key-status-${p.id}`}>
                          🔓 No Key Required (Local)
                        </span>
                      ) : (
                        <span className="kb-key-status kb-key-status--missing" data-testid={`key-status-${p.id}`}>
                          ⚠️ Key Not Set
                        </span>
                      )}
                    </div>

                    {isBlockedByAirGap && (
                      <div className="kb-provider-meta-row kb-provider-air-gap-alert">
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

                    {cardTest && (
                      <div
                        className={`kb-test-connection-status kb-test-connection-status--${cardTest.kind}`}
                        data-testid={`test-status-${p.id}`}
                      >
                        {cardTest.message}
                      </div>
                    )}
                  </div>
                </div>

                <div className="kb-provider-card-actions">
                  <button
                    type="button"
                    className="kb-btn kb-btn-secondary"
                    onClick={() => { void handleTestCardConnection(p); }}
                    data-testid={`test-connection-btn-${p.id}`}
                  >
                    Test Connection
                  </button>

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
        providersCount={providers.length}
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
            <h2 id="delete-provider-title" className="kb-delete-modal-title">
              Confirm Provider Deletion
            </h2>
            <p className="kb-delete-modal-text">
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
