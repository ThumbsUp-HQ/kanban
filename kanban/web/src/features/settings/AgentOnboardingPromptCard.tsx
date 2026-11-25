// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import React, { useState, useContext, useMemo, type JSX } from 'react';
import {
  useQuery,
  useMutation,
  useQueryClient,
  QueryClientContext,
  QueryClientProvider,
  QueryClient,
} from '@tanstack/react-query';
import {
  fetchUserPreferences,
  updateUserPreferences,
  type AgentOnboardingPrefs,
} from './personalSettingsApi';
import { buildAgentOnboardingPrompt } from './agentOnboardingPrompt';
import { copyToClipboard } from '../../utils/clipboard';
import './AgentOnboardingPromptCard.css';

export interface AgentOnboardingPromptCardProps {
  projectKey?: string | undefined;
}

function AgentOnboardingPromptCardInner({ projectKey }: AgentOnboardingPromptCardProps): JSX.Element {
  const queryClient = useQueryClient();

  const { data: prefData, isLoading } = useQuery({
    queryKey: ['userPreferences'],
    queryFn: fetchUserPreferences,
  });

  const [scopeInput, setScopeInput] = useState<'local_only' | 'global_allowed' | null>(null);
  const [executionModeInput, setExecutionModeInput] = useState<
    'single_thread' | 'teamwork' | 'swarm' | null
  >(null);
  const [modelStrategyInput, setModelStrategyInput] = useState<
    'quota_sipping_flash' | 'hybrid' | 'unconstrained_max' | null
  >(null);
  const [qaRigorInput, setQaRigorInput] = useState<'standard' | 'strict_forensic' | null>(null);
  const [customNotesInput, setCustomNotesInput] = useState<string | null>(null);

  const prefs = (
    prefData as { agent_onboarding_prefs?: Partial<AgentOnboardingPrefs> } | undefined
  )?.agent_onboarding_prefs;

  const scope = scopeInput ?? prefs?.scope ?? 'local_only';
  const executionMode = executionModeInput ?? prefs?.execution_mode ?? 'swarm';
  const modelStrategy =
    modelStrategyInput ?? prefs?.model_strategy ?? 'quota_sipping_flash';
  const qaRigor = qaRigorInput ?? prefs?.qa_rigor ?? 'strict_forensic';
  const customNotes = customNotesInput ?? prefs?.custom_notes ?? '';

  const [isCopied, setIsCopied] = useState<boolean>(false);
  const [saveSuccess, setSaveSuccess] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);

  const updateMutation = useMutation({
    mutationFn: (updated: AgentOnboardingPrefs) =>
      updateUserPreferences({
        agent_onboarding_prefs: updated,
      }),
    onSuccess: (data) => {
      queryClient.setQueryData(['userPreferences'], data);
      setScopeInput(null);
      setExecutionModeInput(null);
      setModelStrategyInput(null);
      setQaRigorInput(null);
      setCustomNotesInput(null);
      setSaveSuccess('Preferences saved successfully.');
      setSaveError(null);
      setTimeout(() => {
        setSaveSuccess(null);
      }, 3000);
    },
    onError: (err: unknown) => {
      const msg = err instanceof Error ? err.message : 'Failed to save preferences.';
      setSaveError(msg);
      setSaveSuccess(null);
    },
  });

  const computedPrompt = buildAgentOnboardingPrompt({
    scope,
    executionMode,
    modelStrategy,
    qaRigor,
    customNotes,
    projectKey,
  });

  const handleCopy = async (): Promise<void> => {
    const ok = await copyToClipboard(computedPrompt);
    if (ok) {
      setIsCopied(true);
      setTimeout(() => {
        setIsCopied(false);
      }, 2000);
    }
  };

  const handleSave = (): void => {
    updateMutation.mutate({
      scope,
      execution_mode: executionMode,
      model_strategy: modelStrategy,
      qa_rigor: qaRigor,
      custom_notes: customNotes,
    });
  };

  return (
    <div className="kb-agent-onboarding-card" data-testid="agent-onboarding-prompt-card">
      <div className="kb-agent-onboarding-card-header">
        <h3 className="kb-agent-onboarding-title">
          <span>🤖</span> Agent Onboarding Prompt (/llms.txt)
        </h3>
        <p className="kb-agent-onboarding-subtitle">
          Configure how autonomous coding agents (Claude Code, OpenAI Codex, Gemini CLI / Antigravity)
          interact with your codebase. Persistence defaults strictly to your local project folder.
        </p>
      </div>

      <div className="kb-agent-onboarding-grid">
        <div className="kb-agent-onboarding-field">
          <label htmlFor="pref-scope-select" className="kb-agent-onboarding-label">
            Persistence Scope
          </label>
          <select
            id="pref-scope-select"
            data-testid="pref-scope-select"
            className="kb-agent-onboarding-select"
            value={scope}
            onChange={(e) => {
              setScopeInput(e.target.value as 'local_only' | 'global_allowed');
            }}
          >
            <option value="local_only">
              Local project folder only (.agents/skills/ &amp; AGENTS.md) [Default / Recommended]
            </option>
            <option value="global_allowed">
              Global workstation directories (~/.claude, ~/.codex, ~/.gemini, ~/.agents)
            </option>
          </select>
        </div>

        <div className="kb-agent-onboarding-field">
          <label htmlFor="pref-exec-mode-select" className="kb-agent-onboarding-label">
            Execution Topology
          </label>
          <select
            id="pref-exec-mode-select"
            data-testid="pref-exec-mode-select"
            className="kb-agent-onboarding-select"
            value={executionMode}
            onChange={(e) => {
              setExecutionModeInput(e.target.value as 'single_thread' | 'teamwork' | 'swarm');
            }}
          >
            <option value="swarm">Multi-Agent Swarm (Parallel Worktree Builders) [Recommended]</option>
            <option value="teamwork">Teamwork (Coordinator + Sub-Agents)</option>
            <option value="single_thread">Single-Threaded Agent (Solo Execution)</option>
          </select>
        </div>

        <div className="kb-agent-onboarding-field">
          <label htmlFor="pref-model-strat-select" className="kb-agent-onboarding-label">
            Model &amp; Quota Strategy
          </label>
          <select
            id="pref-model-strat-select"
            data-testid="pref-model-strat-select"
            className="kb-agent-onboarding-select"
            value={modelStrategy}
            onChange={(e) => {
              setModelStrategyInput(
                e.target.value as 'quota_sipping_flash' | 'hybrid' | 'unconstrained_max',
              );
            }}
          >
            <option value="quota_sipping_flash">
              Quota-Sipping Flash 3.8 / Haiku [Recommended / 4x Multiplier]
            </option>
            <option value="hybrid">Balanced Hybrid (Sonnet / Argon + Flash / Haiku)</option>
            <option value="unconstrained_max">
              Unconstrained Sol MAX / Claude Ultra / Gemini Carbon
            </option>
          </select>
        </div>

        <div className="kb-agent-onboarding-field">
          <label htmlFor="pref-qa-rigor-select" className="kb-agent-onboarding-label">
            QA &amp; Verification Rigor
          </label>
          <select
            id="pref-qa-rigor-select"
            data-testid="pref-qa-rigor-select"
            className="kb-agent-onboarding-select"
            value={qaRigor}
            onChange={(e) => {
              setQaRigorInput(e.target.value as 'standard' | 'strict_forensic');
            }}
          >
            <option value="strict_forensic">
              Clean-Room Forensic reality-checker + &gt;=95% Coverage [Recommended]
            </option>
            <option value="standard">Pragmatic Baseline (&gt;=80% Unit Coverage)</option>
          </select>
        </div>

        {scope === 'global_allowed' && (
          <div
            className="kb-agent-onboarding-warning-banner"
            role="alert"
            data-testid="onboarding-scope-warning"
          >
            ⚠️ <strong>Warning:</strong> Global installation permits modifying system-wide dot-directories
            (~/.claude, ~/.codex, ~/.gemini, ~/.agents). Restricting configuration strictly to the local
            project folder (.agents/skills/ and AGENTS.md) is recommended to prevent workstation-level drift.
          </div>
        )}

        <div className="kb-agent-onboarding-field kb-agent-onboarding-field-full">
          <label htmlFor="pref-custom-notes" className="kb-agent-onboarding-label">
            Custom Instructions / Constraints (Optional, max 4096 chars)
          </label>
          <textarea
            id="pref-custom-notes"
            data-testid="pref-custom-notes-input"
            className="kb-agent-onboarding-textarea"
            maxLength={4096}
            placeholder="e.g. Always generate Playwright screenshots for UI changes, never modify production credentials..."
            value={customNotes}
            onChange={(e) => {
              setCustomNotesInput(e.target.value);
            }}
          />
        </div>

        <div className="kb-agent-onboarding-prompt-box">
          <label htmlFor="prompt-preview" className="kb-agent-onboarding-label">
            Generated Agent Onboarding Prompt
          </label>
          <div
            id="prompt-preview"
            data-testid="agent-onboarding-prompt-preview"
            className="kb-agent-onboarding-prompt-preview"
          >
            {computedPrompt}
          </div>
        </div>
      </div>

      <div className="kb-agent-onboarding-actions">
        <button
          type="button"
          data-testid="copy-agent-onboarding-prompt-btn"
          className="kb-agent-onboarding-btn kb-agent-onboarding-btn-primary"
          onClick={() => {
            void handleCopy();
          }}
        >
          {isCopied ? 'Copied Prompt!' : '📋 Copy Agent Onboarding Prompt'}
        </button>

        <button
          type="button"
          data-testid="save-agent-onboarding-prefs-btn"
          className="kb-agent-onboarding-btn kb-agent-onboarding-btn-secondary"
          onClick={handleSave}
          disabled={isLoading || updateMutation.isPending}
        >
          {updateMutation.isPending ? 'Saving...' : '💾 Save Preferences'}
        </button>
      </div>

      {saveSuccess && (
        <div
          role="status"
          className="kb-agent-onboarding-alert kb-agent-onboarding-alert-success"
          data-testid="onboarding-save-success"
        >
          {saveSuccess}
        </div>
      )}

      {saveError && (
        <div
          role="alert"
          className="kb-agent-onboarding-alert kb-agent-onboarding-alert-error"
          data-testid="onboarding-save-error"
        >
          {saveError}
        </div>
      )}
    </div>
  );
}

export function AgentOnboardingPromptCard(props: AgentOnboardingPromptCardProps): JSX.Element {
  const existingClient = useContext(QueryClientContext);
  const fallbackClient = useMemo(() => {
    if (existingClient) return null;
    return new QueryClient({
      defaultOptions: {
        queries: { retry: false },
      },
    });
  }, [existingClient]);

  if (!existingClient && fallbackClient) {
    return (
      <QueryClientProvider client={fallbackClient}>
        <AgentOnboardingPromptCardInner {...props} />
      </QueryClientProvider>
    );
  }

  return <AgentOnboardingPromptCardInner {...props} />;
}
