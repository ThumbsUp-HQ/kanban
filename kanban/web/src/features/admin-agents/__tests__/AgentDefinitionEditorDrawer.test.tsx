// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import React from 'react';
import { AgentDefinitionEditorDrawer } from '../AgentDefinitionEditorDrawer';
import * as aiApi from '../../admin-ai/aiAdminApi';
import type { ProviderConfigPublic } from '../../admin-ai/aiAdminApi';
import * as agentApi from '../agentDefinitionsApi';

describe('AgentDefinitionEditorDrawer Model Quick-Picker (KAN-60 / KB-AI-STUDIO-01)', () => {
  const mockAiProviders: ProviderConfigPublic[] = [
    {
      id: 'prov-gemini',
      provider_kind: 'gemini',
      display_name: 'Google Gemini',
      base_url: 'https://generativelanguage.googleapis.com',
      model_allowlist: ['gemini-2.5-flash-lite', 'gemini-2.5-flash', 'gemini-2.5-pro'],
      residency_tier: 'cloud_standard',
      priority: 10,
      settings: {},
      api_key_set: true,
      is_enabled: true,
      project_id: null,
    },
    {
      id: 'prov-ollama',
      provider_kind: 'ollama',
      display_name: 'Local Ollama',
      base_url: 'http://127.0.0.1:11434',
      model_allowlist: ['gemma3:4b', 'nemotron-3-super:latest', 'granite3.3:2b'],
      residency_tier: 'local_only',
      priority: 20,
      settings: {},
      api_key_set: false,
      is_enabled: true,
      project_id: null,
    },
  ];

  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('renders quick-pick model chips and datalist from configured AI providers for selected providerKind', () => {
    render(
      <AgentDefinitionEditorDrawer
        isOpen={true}
        onClose={vi.fn()}
        agent={null}
        onSaved={vi.fn()}
        aiProviders={mockAiProviders}
      />,
    );

    // Initial providerKind is gemini
    const modelInput = screen.getByTestId<HTMLInputElement>('agent-model-input');
    expect(modelInput.getAttribute('list')).toBe('agent-model-datalist');

    const datalist = screen.getByTestId('agent-model-datalist');
    const options = Array.from(datalist.querySelectorAll('option')).map((o) => o.value);
    expect(options).toEqual(['gemini-2.5-flash-lite', 'gemini-2.5-flash', 'gemini-2.5-pro']);

    // Check quick-pick chips are rendered
    expect(screen.getByTestId('agent-model-quickpicks')).toBeDefined();
    expect(screen.getByTestId('quickpick-model-gemini-2.5-flash-lite')).toBeDefined();
    expect(screen.getByTestId('quickpick-model-gemini-2.5-flash')).toBeDefined();
    expect(screen.getByTestId('quickpick-model-gemini-2.5-pro')).toBeDefined();

    // 1-click selection: click gemini-2.5-flash-lite
    fireEvent.click(screen.getByTestId('quickpick-model-gemini-2.5-flash-lite'));
    expect(modelInput.value).toBe('gemini-2.5-flash-lite');
    expect(screen.getByTestId('quickpick-model-gemini-2.5-flash-lite').className).toContain(
      'kb-quickpick-chip--selected',
    );
  });

  it('updates quick-pick model chips dynamically when switching providerKind', () => {
    render(
      <AgentDefinitionEditorDrawer
        isOpen={true}
        onClose={vi.fn()}
        agent={null}
        onSaved={vi.fn()}
        aiProviders={mockAiProviders}
      />,
    );

    const providerSelect = screen.getByTestId('agent-provider-select');
    const modelInput = screen.getByTestId<HTMLInputElement>('agent-model-input');

    // Switch providerKind to ollama
    fireEvent.change(providerSelect, { target: { value: 'ollama' } });

    // Chips for ollama models should now be displayed
    expect(screen.getByTestId('quickpick-model-gemma3:4b')).toBeDefined();
    expect(screen.getByTestId('quickpick-model-nemotron-3-super:latest')).toBeDefined();
    expect(screen.getByTestId('quickpick-model-granite3.3:2b')).toBeDefined();
    expect(screen.queryByTestId('quickpick-model-gemini-2.5-flash-lite')).toBeNull();

    // 1-click select nemotron-3-super:latest
    fireEvent.click(screen.getByTestId('quickpick-model-nemotron-3-super:latest'));
    expect(modelInput.value).toBe('nemotron-3-super:latest');
    expect(screen.getByTestId('quickpick-model-nemotron-3-super:latest').className).toContain(
      'kb-quickpick-chip--selected',
    );
  });

  it('fetches providers automatically when aiProviders prop is omitted', async () => {
    const fetchSpy = vi.spyOn(aiApi, 'fetchAiProviders').mockResolvedValue(mockAiProviders);

    render(
      <AgentDefinitionEditorDrawer
        isOpen={true}
        onClose={vi.fn()}
        agent={null}
        onSaved={vi.fn()}
      />,
    );

    await waitFor(() => {
      expect(fetchSpy).toHaveBeenCalled();
      expect(screen.getByTestId('quickpick-model-gemini-2.5-flash-lite')).toBeDefined();
    });
  });

  it('saves agent with selected quick-pick model successfully', async () => {
    const createSpy = vi.spyOn(agentApi, 'createAgentDefinition').mockResolvedValue({
      id: 'agent-created-1',
      workspace_id: 'ws-1',
      principal_id: 'prin-1',
      slug: 'test-qa-agent',
      display_name: 'Test QA Agent',
      harness_kind: 'in_app_sdk',
      provider_kind: 'gemini',
      model_id: 'gemini-2.5-flash-lite',
      cli_binary_allowlist_id: null,
      cli_args: [],
      remote_runner_pool_slug: null,
      repo_access_mode: 'none',
      mcp_allowed_tools: [],
      system_instructions_md: 'Audit verification packets.',
      timeout_ms: 60000,
    });
    const onSaved = vi.fn();
    const onClose = vi.fn();

    render(
      <AgentDefinitionEditorDrawer
        isOpen={true}
        onClose={onClose}
        agent={null}
        onSaved={onSaved}
        aiProviders={mockAiProviders}
      />,
    );

    fireEvent.change(screen.getByTestId('agent-slug-input'), {
      target: { value: 'test-qa-agent' },
    });
    fireEvent.change(screen.getByTestId('agent-name-input'), {
      target: { value: 'Test QA Agent' },
    });

    // 1-click pick model
    fireEvent.click(screen.getByTestId('quickpick-model-gemini-2.5-flash-lite'));

    fireEvent.click(screen.getByTestId('save-agent-btn'));

    await waitFor(() => {
      expect(createSpy).toHaveBeenCalledWith(
        expect.objectContaining({
          slug: 'test-qa-agent',
          display_name: 'Test QA Agent',
          model_id: 'gemini-2.5-flash-lite',
          provider_kind: 'gemini',
        }),
      );
      expect(onSaved).toHaveBeenCalled();
      expect(onClose).toHaveBeenCalled();
    });
  });

  it('saves agent with workspaceSlug routing successfully', async () => {
    const createSpy = vi.spyOn(agentApi, 'createAgentDefinition').mockResolvedValue({
      id: 'agent-created-2',
      workspace_id: 'ws-1',
      principal_id: 'prin-1',
      slug: 'workspace-qa-agent',
      display_name: 'Workspace QA Agent',
      harness_kind: 'in_app_sdk',
      provider_kind: 'gemini',
      model_id: 'gemini-2.5-flash-lite',
      cli_binary_allowlist_id: null,
      cli_args: [],
      remote_runner_pool_slug: null,
      repo_access_mode: 'none',
      mcp_allowed_tools: [],
      system_instructions_md: 'Workspace prompt instructions.',
      timeout_ms: 60000,
    });
    const onSaved = vi.fn();
    const onClose = vi.fn();

    render(
      <AgentDefinitionEditorDrawer
        isOpen={true}
        onClose={onClose}
        agent={null}
        onSaved={onSaved}
        aiProviders={mockAiProviders}
        workspaceSlug="qa-team"
      />,
    );

    fireEvent.change(screen.getByTestId('agent-slug-input'), {
      target: { value: 'workspace-qa-agent' },
    });
    fireEvent.change(screen.getByTestId('agent-name-input'), {
      target: { value: 'Workspace QA Agent' },
    });
    fireEvent.click(screen.getByTestId('quickpick-model-gemini-2.5-flash-lite'));
    fireEvent.click(screen.getByTestId('save-agent-btn'));

    await waitFor(() => {
      expect(createSpy).toHaveBeenCalledWith(
        expect.objectContaining({
          slug: 'workspace-qa-agent',
          display_name: 'Workspace QA Agent',
        }),
        'qa-team',
      );
      expect(onSaved).toHaveBeenCalled();
      expect(onClose).toHaveBeenCalled();
    });
  });

  it('renders inline helper description for each execution harness kind', () => {
    render(
      <AgentDefinitionEditorDrawer
        isOpen={true}
        onClose={vi.fn()}
        agent={null}
        onSaved={vi.fn()}
        aiProviders={mockAiProviders}
      />,
    );

    const harnessSelect = screen.getByTestId('agent-harness-select');
    const hintEl = screen.getByTestId('agent-harness-hint');

    // Default: in_app_sdk
    expect(hintEl.textContent).toContain('Executes in-process against configured AI providers');

    // Switch to cli_pipe
    fireEvent.change(harnessSelect, { target: { value: 'cli_pipe' } });
    expect(hintEl.textContent).toContain('Executes through a sandboxed CLI pipe binary');

    // Switch to remote_runner
    fireEvent.change(harnessSelect, { target: { value: 'remote_runner' } });
    expect(hintEl.textContent).toContain('Dispatches agent execution jobs to an isolated remote worker');
  });

  it('surfaces Air-Gap Egress Denied message when submission encounters AIR_GAP_EGRESS_DENIED', async () => {
    vi.spyOn(agentApi, 'createAgentDefinition').mockRejectedValue(
      new Error('409 Conflict: AIR_GAP_EGRESS_DENIED - egress to cloud provider is denied'),
    );

    render(
      <AgentDefinitionEditorDrawer
        isOpen={true}
        onClose={vi.fn()}
        agent={null}
        onSaved={vi.fn()}
        aiProviders={mockAiProviders}
      />,
    );

    fireEvent.change(screen.getByTestId('agent-slug-input'), {
      target: { value: 'airgap-agent' },
    });
    fireEvent.change(screen.getByTestId('agent-name-input'), {
      target: { value: 'Airgap Agent' },
    });
    fireEvent.click(screen.getByTestId('save-agent-btn'));

    await waitFor(() => {
      expect(screen.getByTestId('agent-editor-error').textContent).toContain(
        'Air-Gap Egress Denied: Autonomous agents cannot use cloud providers under active air-gap policy.',
      );
    });
  });
});
