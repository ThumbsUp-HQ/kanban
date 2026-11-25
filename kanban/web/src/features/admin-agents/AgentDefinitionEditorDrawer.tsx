// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import React, { useState, useEffect, type JSX } from 'react';
import { FieldHelpHint } from '../../components/help/FieldHelpHint';
import { AdvancedSection } from '../../ui/AdvancedSection';
import { useAal2DirtyKeepalive } from '../../components/help/WebSudoModalHost';
import { isAal2StepUpCancelled } from '../../api/client';
import {
  createAgentDefinition,
  updateAgentDefinition,
  type AgentDefinitionResponse,
  type AgentDefinitionCreate,
  type AgentDefinitionPatch,
  type HarnessKind,
  type ProviderKind,
  type RepoAccessMode,
} from './agentDefinitionsApi';
import {
  validateCliArguments,
  ALLOWED_CLI_BINARIES,
  CODEX_PINNED_PREFIX,
} from './cliPolicy';
import { fetchAiProviders, type ProviderConfigPublic } from '../admin-ai/aiAdminApi';

interface AgentDefinitionEditorDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  agent: AgentDefinitionResponse | null;
  onSaved: () => void;
  aiProviders?: ProviderConfigPublic[] | undefined;
  projectId?: string | null | undefined;
  workspaceSlug?: string | undefined;
}

const ALL_MCP_TOOLS = ['search_tickets', 'read_ticket', 'search_knowledge', 'read_doc'] as const;

function AgentDefinitionEditorContent({
  onClose,
  agent,
  onSaved,
  aiProviders,
  projectId,
  workspaceSlug,
}: {
  onClose: () => void;
  agent: AgentDefinitionResponse | null;
  onSaved: () => void;
  aiProviders?: ProviderConfigPublic[] | undefined;
  projectId?: string | null | undefined;
  workspaceSlug?: string | undefined;
}): JSX.Element {
  const isEditing = agent !== null;

  const [slug, setSlug] = useState<string>(agent?.slug ?? '');
  const [displayName, setDisplayName] = useState<string>(agent?.display_name ?? '');
  const [harnessKind, setHarnessKind] = useState<HarnessKind>(agent?.harness_kind ?? 'in_app_sdk');
  const [providerKind, setProviderKind] = useState<ProviderKind>(agent?.provider_kind ?? 'gemini');
  const [modelId, setModelId] = useState<string>(agent?.model_id ?? 'gemini-2.5-flash');
  const [fetchedProviders, setFetchedProviders] = useState<ProviderConfigPublic[]>([]);

  useEffect(() => {
    if (aiProviders !== undefined) {
      return;
    }
    let isMounted = true;
    const fetchCall = workspaceSlug
      ? fetchAiProviders(projectId ?? undefined, workspaceSlug)
      : fetchAiProviders(projectId ?? undefined);
    fetchCall
      .then((data) => {
        if (isMounted) {
          setFetchedProviders(data);
        }
      })
      .catch(() => {
        // Fallback gracefully on network error
      });
    return () => {
      isMounted = false;
    };
  }, [aiProviders, projectId, workspaceSlug]);

  const providers = aiProviders ?? fetchedProviders;
  const matchingProviders = providers.filter(
    (p) => p.provider_kind === providerKind && p.is_enabled,
  );
  const quickPickModels = Array.from(
    new Set(matchingProviders.flatMap((p) => p.model_allowlist)),
  ).filter((m) => m.trim().length > 0);
  const [cliBinary, setCliBinary] = useState<string>(agent?.cli_binary_allowlist_id ?? 'agy');
  const [cliArgsString, setCliArgsString] = useState<string>(agent ? agent.cli_args.join(' ') : '-p');
  const [runnerPool, setRunnerPool] = useState<string>(agent?.remote_runner_pool_slug ?? 'default');
  const [repoAccessMode, setRepoAccessMode] = useState<RepoAccessMode>(agent?.repo_access_mode ?? 'none');
  const [timeoutMs, setTimeoutMs] = useState<number>(agent?.timeout_ms ?? 60000);
  const [selectedTools, setSelectedTools] = useState<string[]>(
    agent ? agent.mcp_allowed_tools : ['search_tickets', 'read_ticket', 'search_knowledge', 'read_doc'],
  );
  const [systemInstructions, setSystemInstructions] = useState<string>(
    agent?.system_instructions_md ?? 'You are an autonomous Kanban specialist agent.',
  );
  const [isSaving, setIsSaving] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const isDirty = React.useMemo(() => {
    if (!agent) {
      return Boolean(
        displayName.trim() ||
        slug.trim() ||
        harnessKind !== 'in_app_sdk' ||
        providerKind !== 'gemini' ||
        modelId !== 'gemini-2.5-flash' ||
        systemInstructions.trim() !== 'You are an autonomous Kanban specialist agent.'
      );
    }
    return (
      displayName !== agent.display_name ||
      slug !== agent.slug ||
      harnessKind !== agent.harness_kind ||
      providerKind !== agent.provider_kind ||
      modelId !== agent.model_id ||
      systemInstructions !== agent.system_instructions_md ||
      timeoutMs !== agent.timeout_ms ||
      repoAccessMode !== agent.repo_access_mode ||
      runnerPool !== (agent.remote_runner_pool_slug ?? 'default') ||
      cliBinary !== (agent.cli_binary_allowlist_id ?? 'agy')
    );
  }, [
    agent,
    displayName,
    slug,
    harnessKind,
    providerKind,
    modelId,
    systemInstructions,
    timeoutMs,
    repoAccessMode,
    runnerPool,
    cliBinary,
  ]);

  useAal2DirtyKeepalive(isDirty);

  const handleCliBinaryChange = (binary: string): void => {
    setCliBinary(binary);
    if (binary === 'codex') {
      setCliArgsString(CODEX_PINNED_PREFIX.join(' '));
    } else if (binary === 'agy') {
      setCliArgsString('-p');
    }
  };

  const parseArgs = (raw: string): string[] => {
    return raw
      .split(/[\s,]+/)
      .map((s) => s.trim())
      .filter((s) => s.length > 0);
  };

  const parsedCliArgs = parseArgs(cliArgsString);
  const cliValidation =
    harnessKind === 'cli_pipe'
      ? validateCliArguments(cliBinary, parsedCliArgs)
      : { valid: true };

  const handleSubmit = async (e: React.SyntheticEvent): Promise<void> => {
    e.preventDefault();

    if (!slug.trim()) {
      setError('Slug is required');
      return;
    }
    if (!/^[a-z0-9][a-z0-9-]{1,62}$/.test(slug.trim())) {
      setError("Slug must match '^[a-z0-9][a-z0-9-]{1,62}$' (lowercase alphanumeric with hyphens)");
      return;
    }
    if (!displayName.trim()) {
      setError('Display name is required');
      return;
    }

    if (harnessKind === 'cli_pipe' && !cliValidation.valid) {
      setError(cliValidation.error ?? 'Invalid CLI arguments');
      return;
    }

    try {
      setIsSaving(true);
      setError(null);

      if (agent) {
        const payload: AgentDefinitionPatch = {
          display_name: displayName.trim(),
          provider_kind: harnessKind === 'in_app_sdk' ? providerKind : null,
          model_id: harnessKind === 'in_app_sdk' ? modelId.trim() : null,
          cli_binary_allowlist_id: harnessKind === 'cli_pipe' ? cliBinary : null,
          cli_args: harnessKind === 'cli_pipe' ? parsedCliArgs : [],
          remote_runner_pool_slug: harnessKind === 'remote_runner' ? runnerPool.trim() : null,
          repo_access_mode: repoAccessMode,
          mcp_allowed_tools: selectedTools,
          system_instructions_md: systemInstructions,
          timeout_ms: timeoutMs,
        };

        await updateAgentDefinition(agent.id, payload);
      } else {
        const payload: AgentDefinitionCreate = {
          slug: slug.trim(),
          display_name: displayName.trim(),
          project_id: projectId ?? null,
          harness_kind: harnessKind,
          provider_kind: harnessKind === 'in_app_sdk' ? providerKind : null,
          model_id: harnessKind === 'in_app_sdk' ? modelId.trim() : null,
          cli_binary_allowlist_id: harnessKind === 'cli_pipe' ? cliBinary : null,
          cli_args: harnessKind === 'cli_pipe' ? parsedCliArgs : [],
          remote_runner_pool_slug: harnessKind === 'remote_runner' ? runnerPool.trim() : null,
          repo_access_mode: repoAccessMode,
          mcp_allowed_tools: selectedTools,
          system_instructions_md: systemInstructions,
          timeout_ms: timeoutMs,
        };

        if (workspaceSlug) {
          await createAgentDefinition(payload, workspaceSlug);
        } else {
          await createAgentDefinition(payload);
        }
      }

      setIsSaving(false);
      onSaved();
      onClose();
    } catch (err: unknown) {
      setIsSaving(false);
      if (isAal2StepUpCancelled(err)) {
        return;
      }
      setError(err instanceof Error ? err.message : 'Failed to save agent definition');
    }
  };

  return (
    <div className="kb-modal-card">
      <div className="kb-modal-header">
        <h2 id="agent-drawer-title">
          {isEditing ? `Edit @${agent.slug}` : 'Register Autonomous Agent'}
        </h2>
        <button
          type="button"
          className="kb-btn kb-btn-secondary"
          onClick={onClose}
          aria-label="Close dialog"
          data-testid="close-agent-drawer-btn"
        >
          ✕
        </button>
      </div>

      {error && (
        <div className="kb-form-hint kb-agent-drawer-error" data-testid="agent-editor-error">
          {error}
        </div>
      )}

      <form noValidate onSubmit={(e) => { void handleSubmit(e); }}>
        <div className="kb-form-group">
          <label htmlFor="agent-slug-input" className="kb-form-label">
            Agent Slug (Permanent Handle)
          </label>
          <input
            id="agent-slug-input"
            type="text"
            className="kb-form-input"
            value={slug}
            onChange={(e) => { setSlug(e.target.value.toLowerCase()); }}
            placeholder="e.g. reality-checker"
            disabled={isEditing}
            required
            data-testid="agent-slug-input"
          />
          <span className="kb-form-hint">Pattern: ^[a-z0-9][a-z0-9-]{'{1,62}'}$</span>
        </div>

        <div className="kb-form-group">
          <label htmlFor="agent-name-input" className="kb-form-label">
            Display Name
          </label>
          <input
            id="agent-name-input"
            type="text"
            className="kb-form-input"
            value={displayName}
            onChange={(e) => { setDisplayName(e.target.value); }}
            placeholder="e.g. Reality Checker Forensic QA"
            required
            data-testid="agent-name-input"
          />
        </div>

        <div className="kb-form-group">
          <label htmlFor="agent-harness-select" className="kb-form-label">
            Autonomous Execution Harness
            <FieldHelpHint
              title="Autonomous Execution Harness"
              fieldKey="agent_harness_kind"
              docHref="/docs/multi-provider-ai-engine-and-runners#execution-harnesses"
              summary="Selects runtime execution harness: In-App SDK, sandboxed CLI Pipe, or mTLS Remote Runner."
              validValues={['in_app_sdk', 'cli_pipe', 'remote_runner']}
              defaultValue="in_app_sdk"
            />
          </label>
          <select
            id="agent-harness-select"
            className="kb-form-select"
            value={harnessKind}
            onChange={(e) => { setHarnessKind(e.target.value as HarnessKind); }}
            disabled={isEditing}
            data-testid="agent-harness-select"
          >
            <option value="in_app_sdk">In-App SDK (Direct Provider / Cloud or Local)</option>
            <option value="cli_pipe">CLI Pipe (Sandboxed Zero-Shell Binary)</option>
            <option value="remote_runner">Remote Runner (mTLS Isolated Worker)</option>
          </select>
        </div>

        {harnessKind === 'in_app_sdk' && (
          <>
            <div className="kb-form-group">
              <label htmlFor="agent-provider-select" className="kb-form-label">
                Provider Kind
              </label>
              <select
                id="agent-provider-select"
                className="kb-form-select"
                value={providerKind}
                onChange={(e) => { setProviderKind(e.target.value as ProviderKind); }}
                data-testid="agent-provider-select"
              >
                <option value="gemini">Google Gemini</option>
                <option value="openai">OpenAI</option>
                <option value="ollama">Ollama (Local)</option>
                <option value="fixture">Offline Fixture</option>
              </select>
            </div>

            <div className="kb-form-group">
              <label htmlFor="agent-model-input" className="kb-form-label">
                Model Identifier
              </label>
              <input
                id="agent-model-input"
                type="text"
                list="agent-model-datalist"
                className="kb-form-input"
                value={modelId}
                onChange={(e) => { setModelId(e.target.value); }}
                placeholder="e.g. gemini-2.5-flash or gpt-4o-mini"
                required
                data-testid="agent-model-input"
              />
              <datalist id="agent-model-datalist" data-testid="agent-model-datalist">
                {quickPickModels.map((m) => (
                  <option key={m} value={m} />
                ))}
              </datalist>

              {quickPickModels.length > 0 && (
                <div className="kb-model-quickpicks" data-testid="agent-model-quickpicks">
                  <span className="kb-form-hint">Probed Models:</span>
                  <div className="kb-quickpick-chips">
                    {quickPickModels.map((m) => (
                      <button
                        key={m}
                        type="button"
                        className={`kb-quickpick-chip ${modelId === m ? 'kb-quickpick-chip--selected' : ''}`}
                        onClick={() => { setModelId(m); }}
                        data-testid={`quickpick-model-${m}`}
                      >
                        {m}
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </>
        )}

        {harnessKind === 'cli_pipe' && (
          <div className="kb-form-group">
            <label htmlFor="agent-cli-binary-select" className="kb-form-label">
              Allowlisted CLI Binary
            </label>
            <select
              id="agent-cli-binary-select"
              className="kb-form-select"
              value={cliBinary}
              onChange={(e) => { handleCliBinaryChange(e.target.value); }}
              data-testid="agent-cli-binary-select"
            >
              {Object.entries(ALLOWED_CLI_BINARIES).map(([id, path]) => (
                <option key={id} value={id}>
                  {id} ({path})
                </option>
              ))}
            </select>
          </div>
        )}

        {harnessKind === 'remote_runner' && (
          <div className="kb-form-group">
            <label htmlFor="agent-runner-pool-input" className="kb-form-label">
              Remote Runner Pool Slug
            </label>
            <input
              id="agent-runner-pool-input"
              type="text"
              className="kb-form-input"
              value={runnerPool}
              onChange={(e) => { setRunnerPool(e.target.value); }}
              placeholder="default"
              required
              data-testid="agent-runner-pool-input"
            />
          </div>
        )}

        <AdvancedSection
          title="Advanced Model & Harness Configuration"
          summary="System prompt instructions, CLI arguments, tool filters, and repository access policy"
          testId="advanced-model-harness-config"
          hasErrors={harnessKind === 'cli_pipe' && !cliValidation.valid}
        >
          {harnessKind === 'cli_pipe' && (
            <div className="kb-form-group">
              <label htmlFor="agent-cli-args-input" className="kb-form-label">
                CLI Arguments (enforcing pinned prefix & banned-flag policy)
              </label>
              <input
                id="agent-cli-args-input"
                type="text"
                className="kb-form-input"
                value={cliArgsString}
                onChange={(e) => { setCliArgsString(e.target.value); }}
                placeholder={cliBinary === 'codex' ? 'exec -s read-only -' : '-p'}
                data-testid="agent-cli-args-input"
              />
              <span className="kb-form-hint">
                {cliBinary === 'codex'
                  ? "Pinned prefix required: 'exec -s read-only -'. Zero sandbox escapes."
                  : "e.g. '-p'. Banned flags (--yolo, --dangerously*) are strictly rejected."}
              </span>

              {!cliValidation.valid && (
                <div
                  className="kb-agent-cli-validation-error"
                  data-testid="cli-validation-error-hint"
                >
                  ⚠️ {cliValidation.error}
                </div>
              )}
            </div>
          )}

          <div className="kb-form-group">
            <label htmlFor="agent-timeout-input" className="kb-form-label">
              Timeout (milliseconds, 1000 to 300000)
              <FieldHelpHint
                title="Agent Timeout"
                summary="Execution deadline in milliseconds before aborting agent harness invocation."
                defaultValue="60000 ms (60 seconds)"
                validValues={['1000 to 300000 ms']}
                docHref="/docs/multi-provider-ai-engine-and-runners"
                testId="agent-timeout-help"
              />
            </label>
            <input
              id="agent-timeout-input"
              type="number"
              min="1000"
              max="300000"
              step="1000"
              className="kb-form-input"
              value={timeoutMs}
              onChange={(e) => { setTimeoutMs(parseInt(e.target.value, 10) || 60000); }}
              data-testid="agent-timeout-input"
            />
          </div>

          <div className="kb-form-group">
            <label htmlFor="agent-repo-mode-select" className="kb-form-label">
              Repository Access Mode
              <FieldHelpHint
                title="Repository Access Mode"
                fieldKey="agent_repo_access_mode"
                docHref="/docs/multi-provider-ai-engine-and-runners#repository-access"
                summary="Restricts filesystem/git access: None (Zero local egress), Read-Only Bare Git Tools, or Read-Only VFS Mount."
                validValues={['none', 'bare_git_tools', 'ro_vfs_mount']}
                defaultValue="none"
              />
            </label>
            <select
              id="agent-repo-mode-select"
              className="kb-form-select"
              value={repoAccessMode}
              onChange={(e) => { setRepoAccessMode(e.target.value as RepoAccessMode); }}
              data-testid="agent-repo-mode-select"
            >
              <option value="none">None (Zero Local Egress)</option>
              <option value="bare_git_tools">Bare Git Tools (Read-Only)</option>
              <option value="ro_vfs_mount">Read-Only VFS Mount</option>
            </select>
          </div>

          <div className="kb-form-group">
            <label className="kb-form-label">Allowed MCP Agent Tools</label>
            <div className="kb-agent-tools-grid">
              {ALL_MCP_TOOLS.map((tool) => (
                <label key={tool} className="kb-agent-tool-item">
                  <input
                    type="checkbox"
                    checked={selectedTools.includes(tool)}
                    onChange={(e) => {
                      if (e.target.checked) {
                        setSelectedTools([...selectedTools, tool]);
                      } else {
                        setSelectedTools(selectedTools.filter((t) => t !== tool));
                      }
                    }}
                    data-testid={`tool-checkbox-${tool}`}
                  />
                  <code>{tool}</code>
                </label>
              ))}
            </div>
          </div>

          <div className="kb-form-group">
            <label htmlFor="agent-instructions-textarea" className="kb-form-label">
              System Instructions (Markdown)
            </label>
            <textarea
              id="agent-instructions-textarea"
              rows={4}
              className="kb-form-textarea"
              value={systemInstructions}
              onChange={(e) => { setSystemInstructions(e.target.value); }}
              placeholder="System prompt context and rules of engagement..."
              data-testid="agent-instructions-textarea"
            />
          </div>
        </AdvancedSection>

        <div className="kb-modal-footer">
          <button
            type="button"
            className="kb-btn kb-btn-secondary"
            onClick={onClose}
            data-testid="cancel-agent-drawer-btn"
          >
            Cancel
          </button>
          <button
            type="submit"
            className="kb-btn kb-btn-primary"
            disabled={isSaving || (harnessKind === 'cli_pipe' && !cliValidation.valid)}
            data-testid="save-agent-btn"
          >
            {isSaving ? 'Saving...' : isEditing ? 'Save Agent' : 'Register Agent'}
          </button>
        </div>
      </form>
    </div>
  );
}

export function AgentDefinitionEditorDrawer({
  isOpen,
  onClose,
  agent,
  onSaved,
  aiProviders,
  projectId,
  workspaceSlug,
}: AgentDefinitionEditorDrawerProps): JSX.Element | null {
  if (!isOpen) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="agent-drawer-title"
      className="kb-modal-backdrop"
      data-testid="agent-editor-drawer"
    >
      <AgentDefinitionEditorContent
        key={agent?.id ?? 'new'}
        onClose={onClose}
        agent={agent}
        onSaved={onSaved}
        aiProviders={aiProviders}
        projectId={projectId}
        workspaceSlug={workspaceSlug}
      />
    </div>
  );
}
