// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import React, { useState, useEffect, useCallback, type JSX } from 'react';
import {
  fetchAgentDefinitions,
  deleteAgentDefinition,
  type AgentDefinitionResponse,
} from './agentDefinitionsApi';
import { AgentValidationModal } from './AgentValidationModal';
import { AgentDefinitionEditorDrawer } from './AgentDefinitionEditorDrawer';
import { StudioDocLink } from '../../components/help/StudioDocLink';
import { dispatchAal2StepUpIfRequired } from '../../api/problem';
import { ErrorHelpHint } from '../../components/help/ErrorHelpHint';
import './agentStudio.css';

export interface AgentStudioPageProps {
  projectId?: string | null | undefined;
  workspaceSlug?: string | undefined;
}

export function AgentStudioPage({
  projectId,
  workspaceSlug,
}: AgentStudioPageProps = {}): JSX.Element {
  const [agents, setAgents] = useState<AgentDefinitionResponse[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Modals state
  const [validatingAgent, setValidatingAgent] = useState<AgentDefinitionResponse | null>(null);
  const [editingAgent, setEditingAgent] = useState<AgentDefinitionResponse | null>(null);
  const [isDrawerOpen, setIsDrawerOpen] = useState<boolean>(false);
  const [agentToDelete, setAgentToDelete] = useState<AgentDefinitionResponse | null>(null);

  const [reloadCounter, setReloadCounter] = useState<number>(0);

  useEffect(() => {
    let active = true;

    async function load() {
      try {
        const list = await fetchAgentDefinitions(workspaceSlug ?? 'current', projectId ?? undefined);
        if (!active) return;
        setAgents(list);
      } catch (err: unknown) {
        if (!active) return;
        dispatchAal2StepUpIfRequired(err);
        setError(err instanceof Error ? err.message : 'Failed to load agent definitions');
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
  }, [reloadCounter, projectId, workspaceSlug]);

  const refreshAgents = useCallback((): void => {
    setReloadCounter((c) => c + 1);
  }, []);

  const handleConfirmDelete = async (): Promise<void> => {
    if (!agentToDelete) return;
    try {
      await deleteAgentDefinition(agentToDelete.id);
      setAgentToDelete(null);
      refreshAgents();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to delete agent definition');
    }
  };

  return (
    <section className="kb-agent-studio" data-testid="agent-studio-page">
      <div className="kb-agent-studio-header">
        <div className="kb-agent-studio-title-group">
          <h1>
            <span aria-hidden="true">🤖</span> Autonomous Agent Definitions Studio
          </h1>
          <p className="kb-agent-studio-subtitle">
            Register and manage autonomous AI agents (In-App SDK, sandboxed CLI Pipe, and Remote mTLS Runners) with strict policy validation.
          </p>
        </div>

        <div className="kb-agent-studio-header-actions">
          <StudioDocLink
            href="/docs/multi-provider-ai-engine-and-runners"
            title="Autonomous Agents Documentation"
            testId="agent-studio-doc-link"
          />
          <button
            type="button"
            className="kb-btn kb-btn-primary"
            onClick={() => {
              setEditingAgent(null);
              setIsDrawerOpen(true);
            }}
            data-testid="register-agent-btn"
          >
            + Register Agent
          </button>
        </div>
      </div>

      {error && (
        <div className="kb-form-hint kb-agent-studio-error" role="alert" data-testid="agent-studio-error">
          <span>{error}</span>
          <ErrorHelpHint error={error} />
        </div>
      )}

      {isLoading ? (
        <div className="kb-loading-state" data-testid="agent-studio-loading">
          Loading agent definitions...
        </div>
      ) : agents.length === 0 ? (
        <div
          style={{
            padding: '32px',
            textAlign: 'center',
            backgroundColor: 'var(--kb-color-bg-surface, #ffffff)',
            borderRadius: '8px',
            border: '1px dashed var(--kb-color-border-subtle, #d1d5db)',
          }}
          data-testid="empty-agents-placeholder"
        >
          <p style={{ margin: 0, color: 'var(--kb-color-text-secondary, #4b5563)' }}>
            No autonomous agents registered yet. Click <strong>+ Register Agent</strong> to add one.
          </p>
        </div>
      ) : (
        <div className="kb-agents-grid" data-testid="agents-grid">
          {agents.map((ag) => (
            <div key={ag.id} className="kb-agent-card" data-testid={`agent-card-${ag.id}`}>
              <div>
                <div className="kb-agent-card-header">
                  <span
                    className={`kb-harness-badge kb-harness-badge--${ag.harness_kind}`}
                    data-testid={`harness-badge-${ag.harness_kind}`}
                  >
                    {ag.harness_kind.replace('_', ' ')}
                  </span>
                  <span className="kb-agent-handle" data-testid={`agent-handle-${ag.id}`}>
                    @{ag.slug}
                  </span>
                </div>

                <h3 className="kb-agent-card-name">{ag.display_name}</h3>

                <div className="kb-agent-meta-row">
                  {ag.harness_kind === 'in_app_sdk' && (
                    <>
                      <span>Model:</span>
                      <code>
                        {ag.provider_kind}: {ag.model_id}
                      </code>
                    </>
                  )}

                  {ag.harness_kind === 'cli_pipe' && (
                    <>
                      <span>CLI:</span>
                      <code>
                        {ag.cli_binary_allowlist_id} {ag.cli_args.join(' ')}
                      </code>
                    </>
                  )}

                  {ag.harness_kind === 'remote_runner' && (
                    <>
                      <span>Runner Pool:</span>
                      <code>{ag.remote_runner_pool_slug}</code>
                    </>
                  )}
                </div>

                <div className="kb-agent-meta-row">
                  <span>Timeout:</span>
                  <code>{ag.timeout_ms}ms</code>
                  <span>Repo Access:</span>
                  <code>{ag.repo_access_mode}</code>
                </div>

                <div className="kb-agent-tools-container">
                  <span>Allowed Tools: </span>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px', marginTop: '4px' }}>
                    {ag.mcp_allowed_tools.map((t) => (
                      <span key={t} className="kb-model-chip">
                        {t}
                      </span>
                    ))}
                  </div>
                </div>
              </div>

              <div className="kb-agent-card-actions">
                <button
                  type="button"
                  className="kb-btn kb-btn-primary"
                  style={{ backgroundColor: '#059669', borderColor: '#059669', color: '#ffffff' }}
                  onClick={() => { setValidatingAgent(ag); }}
                  data-testid={`validate-agent-btn-${ag.id}`}
                >
                  Test Validation
                </button>

                <button
                  type="button"
                  className="kb-btn kb-btn-secondary"
                  onClick={() => {
                    setEditingAgent(ag);
                    setIsDrawerOpen(true);
                  }}
                  data-testid={`edit-agent-btn-${ag.id}`}
                >
                  Edit
                </button>

                <button
                  type="button"
                  className="kb-btn kb-btn-danger"
                  onClick={() => { setAgentToDelete(ag); }}
                  data-testid={`delete-agent-btn-${ag.id}`}
                >
                  Delete
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Test Validation Modal */}
      <AgentValidationModal
        isOpen={validatingAgent !== null}
        onClose={() => { setValidatingAgent(null); }}
        agent={validatingAgent}
      />

      {/* Editor Drawer */}
      <AgentDefinitionEditorDrawer
        isOpen={isDrawerOpen}
        onClose={() => {
          setIsDrawerOpen(false);
          setEditingAgent(null);
        }}
        agent={editingAgent}
        onSaved={refreshAgents}
        projectId={projectId}
        workspaceSlug={workspaceSlug}
      />

      {/* Delete Confirmation Modal */}
      {agentToDelete && (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="delete-agent-title"
          className="kb-modal-backdrop"
          data-testid="delete-agent-modal"
        >
          <div className="kb-modal-card">
            <h2 id="delete-agent-title" className="kb-modal-title">
              Confirm Agent Removal
            </h2>
            <p className="kb-modal-desc">
              Are you sure you want to remove agent definition <strong>@{agentToDelete.slug}</strong> ({agentToDelete.display_name})? Any workflow hooks referencing this agent will need to be reconfigured.
            </p>
            <div className="kb-modal-footer">
              <button
                type="button"
                className="kb-btn kb-btn-secondary"
                onClick={() => { setAgentToDelete(null); }}
                data-testid="cancel-delete-agent-btn"
              >
                Cancel
              </button>
              <button
                type="button"
                className="kb-btn kb-btn-danger"
                onClick={() => { void handleConfirmDelete(); }}
                data-testid="confirm-delete-agent-btn"
              >
                Remove Agent
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}

export default AgentStudioPage;
