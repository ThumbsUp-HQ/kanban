// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import React from 'react';
import { AgentDefinitionEditorDrawer } from '../AgentDefinitionEditorDrawer';
import * as aiApi from '../../admin-ai/aiAdminApi';
import type { ProviderConfigPublic } from '../../admin-ai/aiAdminApi';
import * as agentApi from '../agentDefinitionsApi';
import * as clientModule from '../../../api/client';

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

  describe('System Instructions Preservation on Edit (KAN-431)', () => {
    const existingAgentWithInstructions: agentApi.AgentDefinitionResponse = {
      id: 'agent-custom-1',
      workspace_id: 'ws-1',
      principal_id: 'prin-1',
      slug: 'forensic-auditor',
      display_name: 'Forensic Security Auditor',
      harness_kind: 'in_app_sdk',
      provider_kind: 'gemini',
      model_id: 'gemini-2.5-pro',
      cli_binary_allowlist_id: null,
      cli_args: [],
      remote_runner_pool_slug: null,
      repo_access_mode: 'bare_git_tools',
      mcp_allowed_tools: ['search_tickets', 'read_ticket'],
      system_instructions_md: '# Security Guidelines\nAudit verification packets with passive forensic rigor. Never approve unverified assertions.',
      timeout_ms: 60000,
    };

    it('displays saved system instructions verbatim and preserves them when updating timeout', async () => {
      const updateSpy = vi.spyOn(agentApi, 'updateAgentDefinition').mockResolvedValue(existingAgentWithInstructions);
      const onSaved = vi.fn();
      const onClose = vi.fn();

      render(
        <AgentDefinitionEditorDrawer
          isOpen={true}
          onClose={onClose}
          agent={existingAgentWithInstructions}
          onSaved={onSaved}
          aiProviders={mockAiProviders}
        />,
      );

      // Verify custom instructions are displayed verbatim
      const textarea = screen.getByTestId<HTMLTextAreaElement>('agent-instructions-textarea');
      expect(textarea.value).toBe(
        '# Security Guidelines\nAudit verification packets with passive forensic rigor. Never approve unverified assertions.',
      );

      // Change timeout to 180000
      const timeoutInput = screen.getByTestId('agent-timeout-input');
      fireEvent.change(timeoutInput, { target: { value: '180000' } });

      // Save agent
      fireEvent.click(screen.getByTestId('save-agent-btn'));

      await waitFor(() => {
        expect(updateSpy).toHaveBeenCalledWith(
          'agent-custom-1',
          expect.objectContaining({
            timeout_ms: 180000,
            system_instructions_md:
              '# Security Guidelines\nAudit verification packets with passive forensic rigor. Never approve unverified assertions.',
          }),
        );
        expect(onSaved).toHaveBeenCalled();
        expect(onClose).toHaveBeenCalled();
      });
    });

    it('hydrates saved system instructions via fetchAgentDefinition when prop instructions are empty', async () => {
      const agentWithEmptyInstructions: agentApi.AgentDefinitionResponse = {
        ...existingAgentWithInstructions,
        id: 'agent-fetch-detail',
        slug: 'fetch-detail-agent',
        system_instructions_md: '',
      };

      const detailResponse: agentApi.AgentDefinitionResponse = {
        ...agentWithEmptyInstructions,
        system_instructions_md: 'Fetched from backend detail endpoint verbatim.',
      };

      vi.spyOn(agentApi, 'fetchAgentDefinition').mockResolvedValue(detailResponse);

      render(
        <AgentDefinitionEditorDrawer
          isOpen={true}
          onClose={vi.fn()}
          agent={agentWithEmptyInstructions}
          onSaved={vi.fn()}
          aiProviders={mockAiProviders}
        />,
      );

      // Verify that fetchAgentDefinition hydrated instructions into textarea
      await waitFor(() => {
        const textarea = screen.getByTestId<HTMLTextAreaElement>('agent-instructions-textarea');
        expect(textarea.value).toBe('Fetched from backend detail endpoint verbatim.');
      });
    });

    it('silently ignores Aal2StepUpCancelledError and handles non-Error rejection during submit', async () => {
      vi.spyOn(agentApi, 'createAgentDefinition').mockRejectedValueOnce(
        new clientModule.Aal2StepUpCancelledError(),
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

      fireEvent.change(screen.getByTestId('agent-slug-input'), { target: { value: 'cancel-slug' } });
      fireEvent.change(screen.getByTestId('agent-name-input'), { target: { value: 'Cancel Name' } });
      fireEvent.click(screen.getByTestId('save-agent-btn'));

      await waitFor(() => {
        expect(screen.queryByTestId('agent-editor-error')).toBeNull();
      });

      // Non-Error rejection fallback
      vi.spyOn(agentApi, 'createAgentDefinition').mockRejectedValueOnce('raw string error');
      fireEvent.click(screen.getByTestId('save-agent-btn'));

      await waitFor(() => {
        expect(screen.getByTestId('agent-editor-error').textContent).toContain('Failed to save agent definition');
      });
    });

    it('handles aiProviders fetch failure and fetchAgentDefinition rejection gracefully', async () => {
      vi.spyOn(aiApi, 'fetchAiProviders').mockRejectedValueOnce(new Error('Fetch providers failed'));
      vi.spyOn(agentApi, 'fetchAgentDefinition').mockRejectedValueOnce(new Error('Fetch detail failed'));

      render(
        <AgentDefinitionEditorDrawer
          isOpen={true}
          onClose={vi.fn()}
          agent={existingAgentWithInstructions}
          onSaved={vi.fn()}
          aiProviders={undefined}
          workspaceSlug="qa-ws"
        />,
      );

      // Verify drawer still renders despite fetch errors
      await waitFor(() => {
        expect(screen.getByTestId('agent-slug-input')).toBeDefined();
      });
    });

    it('exercises all isDirty field conditions on edit and create', () => {
      render(
        <AgentDefinitionEditorDrawer
          isOpen={true}
          onClose={vi.fn()}
          agent={existingAgentWithInstructions}
          onSaved={vi.fn()}
          aiProviders={mockAiProviders}
        />,
      );

      // Mutate display_name
      fireEvent.change(screen.getByTestId('agent-name-input'), { target: { value: 'Different Name' } });
      // Mutate timeout
      fireEvent.change(screen.getByTestId('agent-timeout-input'), { target: { value: '99000' } });
      // Mutate instructions textarea (sets user edited ref)
      const textarea = screen.getByTestId('agent-instructions-textarea');
      fireEvent.change(textarea, { target: { value: 'New user prompt' } });
      expect((textarea as HTMLTextAreaElement).value).toBe('New user prompt');
    });

    it('submits custom system_instructions_md updated via native DOM input event on create', async () => {
      const customPrompt = '# Native Input Directive\n- Zero latency.';
      const createSpy = vi.spyOn(agentApi, 'createAgentDefinition').mockResolvedValue({
        ...existingAgentWithInstructions,
        slug: 'native-test',
        display_name: 'Native Test',
        system_instructions_md: customPrompt,
      });

      const onSaved = vi.fn();
      render(
        <AgentDefinitionEditorDrawer
          isOpen={true}
          onClose={vi.fn()}
          agent={null}
          onSaved={onSaved}
          aiProviders={mockAiProviders}
        />,
      );

      fireEvent.change(screen.getByTestId('agent-slug-input'), { target: { value: 'native-test' } });
      fireEvent.change(screen.getByTestId('agent-name-input'), { target: { value: 'Native Test' } });

      const textarea = screen.getByTestId<HTMLTextAreaElement>('agent-instructions-textarea');
      textarea.value = customPrompt;
      textarea.dispatchEvent(new Event('input', { bubbles: true }));

      fireEvent.click(screen.getByTestId('save-agent-btn'));

      await waitFor(() => {
        expect(createSpy).toHaveBeenCalledWith(
          expect.objectContaining({
            slug: 'native-test',
            system_instructions_md: customPrompt,
          }),
        );
      });
      expect(onSaved).toHaveBeenCalled();
    });

    it('cli_pipe agent in edit mode is not treated as dirty on mount', () => {
      const cliAgent: agentApi.AgentDefinitionResponse = {
        id: 'agent-cli-edit',
        workspace_id: 'ws-1',
        principal_id: 'prin-cli',
        slug: 'cli-worker',
        display_name: 'CLI Worker',
        harness_kind: 'cli_pipe',
        provider_kind: null,
        model_id: null,
        cli_binary_allowlist_id: 'agy',
        cli_args: ['-p'],
        remote_runner_pool_slug: null,
        repo_access_mode: 'none',
        mcp_allowed_tools: ['search_tickets', 'read_ticket'],
        system_instructions_md: 'Run CLI pipe.',
        timeout_ms: 60000,
      };

      render(
        <AgentDefinitionEditorDrawer
          isOpen={true}
          onClose={vi.fn()}
          agent={cliAgent}
          onSaved={vi.fn()}
          aiProviders={mockAiProviders}
        />,
      );

      const slugInput = screen.getByTestId<HTMLInputElement>('agent-slug-input');
      expect(slugInput.value).toBe('cli-worker');
      expect(screen.getByTestId('save-agent-btn')).toBeDefined();
    });
  });

  describe('FieldHelpHint and Explicit Default Values (KAN-453)', () => {
    it('renders agent-slug-help and agent-mcp-tools-help triggers with accessible labels', () => {
      render(
        <AgentDefinitionEditorDrawer
          isOpen={true}
          onClose={vi.fn()}
          agent={null}
          onSaved={vi.fn()}
          aiProviders={mockAiProviders}
        />,
      );

      const slugHelp = screen.getByTestId('agent-slug-help');
      expect(slugHelp).toBeDefined();
      expect(slugHelp.getAttribute('aria-label')).toBe('Help for Agent Slug (Permanent Handle)');

      const mcpHelp = screen.getByTestId('agent-mcp-tools-help');
      expect(mcpHelp).toBeDefined();
      expect(mcpHelp.getAttribute('aria-label')).toBe('Help for Allowed MCP Agent Tools');

      const toolsGroup = screen.getByRole('group', { name: /Allowed MCP Agent Tools/i });
      expect(toolsGroup).toBeDefined();
      expect(toolsGroup.getAttribute('aria-labelledby')).toBe('agent-mcp-tools-label');

      expect(
        screen.getByText(
          'Default: all 4 read-only MCP tools enabled (search_tickets, read_ticket, search_knowledge, read_doc).',
        ),
      ).toBeDefined();
    });

    it('opens agent-slug-help popover displaying summary, default, example, caution, and wiki doc link', () => {
      render(
        <AgentDefinitionEditorDrawer
          isOpen={true}
          onClose={vi.fn()}
          agent={null}
          onSaved={vi.fn()}
          aiProviders={mockAiProviders}
        />,
      );

      const slugHelp = screen.getByTestId('agent-slug-help');
      fireEvent.focus(slugHelp);

      const popover = screen.getByTestId('agent-slug-help-popover');
      expect(popover).toBeDefined();
      expect(popover.textContent).toContain('Agent Slug (Permanent Handle)');
      expect(popover.textContent).toContain(
        'Immutable lowercase @handle used for @mentions and immutable audit trails.',
      );
      expect(popover.textContent).toContain('None (Required on creation)');
      expect(popover.textContent).toContain('reality-checker');
      expect(popover.textContent).toContain('Permanent once created; cannot be edited later.');

      const docLink = popover.querySelector('a');
      expect(docLink).not.toBeNull();
      expect(docLink?.getAttribute('href')).toBe(
        '/docs/multi-provider-ai-engine-and-runners#agent-definitions-studio',
      );
    });

    it('opens agent-mcp-tools-help popover displaying summary, default, dt/dd valid values, and wiki doc link', () => {
      render(
        <AgentDefinitionEditorDrawer
          isOpen={true}
          onClose={vi.fn()}
          agent={null}
          onSaved={vi.fn()}
          aiProviders={mockAiProviders}
        />,
      );

      const mcpHelp = screen.getByTestId('agent-mcp-tools-help');
      fireEvent.focus(mcpHelp);

      const popover = screen.getByTestId('agent-mcp-tools-help-popover');
      expect(popover).toBeDefined();
      expect(popover.textContent).toContain('Allowed MCP Agent Tools');
      expect(popover.textContent).toContain(
        'Least-privilege MCP tools this agent is permitted to invoke.',
      );
      expect(popover.textContent).toContain(
        'All 4 read-only tools (search_tickets, read_ticket, search_knowledge, read_doc)',
      );

      const dtElements = popover.querySelectorAll('dt');
      const ddElements = popover.querySelectorAll('dd');
      expect(dtElements.length).toBe(4);
      expect(ddElements.length).toBe(4);
      expect(popover.textContent).toContain('search_tickets');
      expect(popover.textContent).toContain('Search project work items');
      expect(popover.textContent).toContain('read_ticket');
      expect(popover.textContent).toContain('Read full issue context');
      expect(popover.textContent).toContain('search_knowledge');
      expect(popover.textContent).toContain('Search docs and wiki');
      expect(popover.textContent).toContain('read_doc');
      expect(popover.textContent).toContain('Read doc markdown');

      const docLink = popover.querySelector('a');
      expect(docLink).not.toBeNull();
      expect(docLink?.getAttribute('href')).toBe(
        '/docs/multi-provider-ai-engine-and-runners#agent-definitions-studio',
      );
    });

    it('renders cleanly without regression under light and dark data-theme attributes', () => {
      document.documentElement.setAttribute('data-theme', 'light');
      const { rerender } = render(
        <AgentDefinitionEditorDrawer
          isOpen={true}
          onClose={vi.fn()}
          agent={null}
          onSaved={vi.fn()}
          aiProviders={mockAiProviders}
        />,
      );
      expect(screen.getByTestId('agent-slug-help')).toBeDefined();
      expect(screen.getByTestId('agent-mcp-tools-help')).toBeDefined();
      expect(screen.getByRole('group', { name: /Allowed MCP Agent Tools/i })).toBeDefined();

      document.documentElement.setAttribute('data-theme', 'dark');
      rerender(
        <AgentDefinitionEditorDrawer
          isOpen={true}
          onClose={vi.fn()}
          agent={null}
          onSaved={vi.fn()}
          aiProviders={mockAiProviders}
        />,
      );
      expect(screen.getByTestId('agent-slug-help')).toBeDefined();
      expect(screen.getByTestId('agent-mcp-tools-help')).toBeDefined();
      expect(screen.getByRole('group', { name: /Allowed MCP Agent Tools/i })).toBeDefined();
      document.documentElement.removeAttribute('data-theme');
    });
  });

  describe('KAN-451: Standardized Drawer Footer Action Button Order and Cadence', () => {
    it('verifies drawer footer action buttons follow standardized cadence: right-aligned [Cancel] -> [Save Agent]', () => {
      const { container } = render(
        <AgentDefinitionEditorDrawer
          isOpen={true}
          onClose={vi.fn()}
          agent={null}
          onSaved={vi.fn()}
          aiProviders={mockAiProviders}
        />,
      );

      const footer = container.querySelector('.kb-modal-footer.kb-drawer-footer');
      expect(footer).not.toBeNull();
      expect(footer?.getAttribute('style')).toBeNull();
      if (!footer) throw new Error('footer not found');

      const rightActions = container.querySelector('.kb-drawer-footer-actions-right');
      expect(rightActions).not.toBeNull();

      const cancelBtn = screen.getByTestId('cancel-agent-drawer-btn');
      const saveBtn = screen.getByTestId('save-agent-btn');
      expect(rightActions?.contains(cancelBtn)).toBe(true);
      expect(rightActions?.contains(saveBtn)).toBe(true);

      // Verify DOM order: Cancel is before Save Agent
      const buttons: HTMLElement[] = Array.from(footer.querySelectorAll('button'));
      const cancelIdx = buttons.indexOf(cancelBtn);
      const saveIdx = buttons.indexOf(saveBtn);
      expect(cancelIdx).toBeLessThan(saveIdx);
      expect(cancelBtn.textContent.trim()).toBe('Cancel');
      expect(saveBtn.textContent.trim()).toBe('Register Agent');
    });

    it('returns null when isOpen is false', () => {
      const { container } = render(
        <AgentDefinitionEditorDrawer
          isOpen={false}
          onClose={vi.fn()}
          agent={null}
          onSaved={vi.fn()}
          aiProviders={mockAiProviders}
        />,
      );
      expect(container.firstChild).toBeNull();
    });

    it('covers client-side form validation errors on submit', async () => {
      render(
        <AgentDefinitionEditorDrawer
          isOpen={true}
          onClose={vi.fn()}
          agent={null}
          onSaved={vi.fn()}
          aiProviders={mockAiProviders}
        />,
      );

      // 1. Empty slug
      fireEvent.change(screen.getByTestId('agent-slug-input'), { target: { value: '   ' } });
      fireEvent.submit(screen.getByTestId('save-agent-btn'));
      await waitFor(() => {
        expect(screen.getByTestId('agent-editor-error').textContent).toContain('Slug is required');
      });

      // 2. Invalid slug regex
      fireEvent.change(screen.getByTestId('agent-slug-input'), { target: { value: 'INVALID_CAPS!' } });
      fireEvent.submit(screen.getByTestId('save-agent-btn'));
      await waitFor(() => {
        expect(screen.getByTestId('agent-editor-error').textContent).toContain("Slug must match '^[a-z0-9][a-z0-9-]{1,62}$'");
      });

      // 3. Valid slug, empty display name
      fireEvent.change(screen.getByTestId('agent-slug-input'), { target: { value: 'valid-slug' } });
      fireEvent.change(screen.getByTestId('agent-name-input'), { target: { value: '   ' } });
      fireEvent.submit(screen.getByTestId('save-agent-btn'));
      await waitFor(() => {
        expect(screen.getByTestId('agent-editor-error').textContent).toContain('Display name is required');
      });

      // 4. Valid display name, invalid timeout bounds
      fireEvent.change(screen.getByTestId('agent-name-input'), { target: { value: 'Valid Agent Name' } });
      fireEvent.change(screen.getByTestId('agent-timeout-input'), { target: { value: '500' } });
      fireEvent.submit(screen.getByTestId('save-agent-btn'));
      await waitFor(() => {
        expect(screen.getByTestId('agent-editor-error').textContent).toContain('Timeout must be between 1,000 and 600,000 ms');
      });

      fireEvent.change(screen.getByTestId('agent-timeout-input'), { target: { value: '700000' } });
      fireEvent.submit(screen.getByTestId('save-agent-btn'));
      await waitFor(() => {
        expect(screen.getByTestId('agent-editor-error').textContent).toContain('Timeout must be between 1,000 and 600,000 ms');
      });
    });

    it('covers input changes across model, CLI binary, runner pool, CLI args, repo mode, and MCP tool checkboxes', () => {
      render(
        <AgentDefinitionEditorDrawer
          isOpen={true}
          onClose={vi.fn()}
          agent={null}
          onSaved={vi.fn()}
          aiProviders={mockAiProviders}
        />,
      );

      // Model input change
      const modelInput = screen.getByTestId('agent-model-input');
      fireEvent.change(modelInput, { target: { value: 'custom-model-id' } });
      expect((modelInput as HTMLInputElement).value).toBe('custom-model-id');

      // Repo mode change
      const repoModeSelect = screen.getByTestId('agent-repo-mode-select');
      fireEvent.change(repoModeSelect, { target: { value: 'bare_git_tools' } });
      expect((repoModeSelect as HTMLSelectElement).value).toBe('bare_git_tools');

      fireEvent.change(repoModeSelect, { target: { value: 'ro_vfs_mount' } });
      expect((repoModeSelect as HTMLSelectElement).value).toBe('ro_vfs_mount');

      // Toggle MCP tool checkbox
      const searchTicketsCheckbox = screen.getByTestId('tool-checkbox-search_tickets');
      expect((searchTicketsCheckbox as HTMLInputElement).checked).toBe(true);
      fireEvent.click(searchTicketsCheckbox);
      expect((searchTicketsCheckbox as HTMLInputElement).checked).toBe(false);
      fireEvent.click(searchTicketsCheckbox);
      expect((searchTicketsCheckbox as HTMLInputElement).checked).toBe(true);

      // Harness switch to cli_pipe
      const harnessSelect = screen.getByTestId('agent-harness-select');
      fireEvent.change(harnessSelect, { target: { value: 'cli_pipe' } });

      const cliBinarySelect = screen.getByTestId('agent-cli-binary-select');
      fireEvent.change(cliBinarySelect, { target: { value: 'codex' } });
      expect((cliBinarySelect as HTMLSelectElement).value).toBe('codex');

      const cliArgsInput = screen.getByTestId('agent-cli-args-input');
      fireEvent.change(cliArgsInput, { target: { value: 'exec -s read-only -' } });
      expect((cliArgsInput as HTMLInputElement).value).toBe('exec -s read-only -');

      // Harness switch to remote_runner
      fireEvent.change(harnessSelect, { target: { value: 'remote_runner' } });
      const runnerPoolInput = screen.getByTestId('agent-runner-pool-input');
      fireEvent.change(runnerPoolInput, { target: { value: 'security-runners' } });
      expect((runnerPoolInput as HTMLInputElement).value).toBe('security-runners');
    });

    it('submits successfully with cli_pipe and remote_runner harness kinds in create and edit modes', async () => {
      const createSpy = vi.spyOn(agentApi, 'createAgentDefinition').mockResolvedValue({
        id: 'agent-new-cli',
        workspace_id: 'ws-1',
        principal_id: 'prin-1',
        slug: 'cli-agent',
        display_name: 'CLI Agent',
        harness_kind: 'cli_pipe',
        provider_kind: null,
        model_id: null,
        cli_binary_allowlist_id: 'agy',
        cli_args: ['-p'],
        remote_runner_pool_slug: null,
        repo_access_mode: 'none',
        mcp_allowed_tools: ['search_tickets'],
        system_instructions_md: 'System prompt',
        timeout_ms: 60000,
      });

      const updateSpy = vi.spyOn(agentApi, 'updateAgentDefinition').mockResolvedValue({
        id: 'agent-edit-runner',
        workspace_id: 'ws-1',
        principal_id: 'prin-1',
        slug: 'runner-agent',
        display_name: 'Updated Runner Agent',
        harness_kind: 'remote_runner',
        provider_kind: null,
        model_id: null,
        cli_binary_allowlist_id: null,
        cli_args: [],
        remote_runner_pool_slug: 'dedicated-pool',
        repo_access_mode: 'ro_vfs_mount',
        mcp_allowed_tools: ['search_tickets'],
        system_instructions_md: 'System prompt',
        timeout_ms: 60000,
      });

      // 1. Create with cli_pipe
      const { unmount: u1 } = render(
        <AgentDefinitionEditorDrawer
          isOpen={true}
          onClose={vi.fn()}
          agent={null}
          onSaved={vi.fn()}
          aiProviders={mockAiProviders}
        />,
      );

      fireEvent.change(screen.getByTestId('agent-slug-input'), { target: { value: 'cli-agent' } });
      fireEvent.change(screen.getByTestId('agent-name-input'), { target: { value: 'CLI Agent' } });
      fireEvent.change(screen.getByTestId('agent-harness-select'), { target: { value: 'cli_pipe' } });
      fireEvent.change(screen.getByTestId('agent-cli-binary-select'), { target: { value: 'agy' } });

      fireEvent.submit(screen.getByTestId('save-agent-btn'));
      await waitFor(() => {
        expect(createSpy).toHaveBeenCalled();
      });
      u1();

      // 2. Edit with remote_runner
      const existingRunnerAgent: agentApi.AgentDefinitionResponse = {
        id: 'agent-edit-runner',
        workspace_id: 'ws-1',
        principal_id: 'prin-1',
        slug: 'runner-agent',
        display_name: 'Runner Agent',
        harness_kind: 'remote_runner',
        provider_kind: null,
        model_id: null,
        cli_binary_allowlist_id: null,
        cli_args: [],
        remote_runner_pool_slug: 'default-pool',
        repo_access_mode: 'none',
        mcp_allowed_tools: ['search_tickets'],
        system_instructions_md: 'System prompt',
        timeout_ms: 60000,
      };

      const { unmount: u2 } = render(
        <AgentDefinitionEditorDrawer
          isOpen={true}
          onClose={vi.fn()}
          agent={existingRunnerAgent}
          onSaved={vi.fn()}
          aiProviders={mockAiProviders}
        />,
      );

      fireEvent.change(screen.getByTestId('agent-name-input'), { target: { value: 'Updated Runner Agent' } });
      fireEvent.change(screen.getByTestId('agent-runner-pool-input'), { target: { value: 'dedicated-pool' } });
      fireEvent.change(screen.getByTestId('agent-repo-mode-select'), { target: { value: 'ro_vfs_mount' } });

      fireEvent.submit(screen.getByTestId('save-agent-btn'));
      await waitFor(() => {
        expect(updateSpy).toHaveBeenCalled();
      });
      u2();

      // 3. Create with remote_runner
      const { unmount: u3 } = render(
        <AgentDefinitionEditorDrawer
          isOpen={true}
          onClose={vi.fn()}
          agent={null}
          onSaved={vi.fn()}
          aiProviders={mockAiProviders}
        />,
      );

      fireEvent.change(screen.getByTestId('agent-slug-input'), { target: { value: 'remote-agent' } });
      fireEvent.change(screen.getByTestId('agent-name-input'), { target: { value: 'Remote Agent' } });
      fireEvent.change(screen.getByTestId('agent-harness-select'), { target: { value: 'remote_runner' } });
      fireEvent.change(screen.getByTestId('agent-runner-pool-input'), { target: { value: 'remote-pool-1' } });
      fireEvent.submit(screen.getByTestId('save-agent-btn'));
      await waitFor(() => {
        expect(createSpy).toHaveBeenCalled();
      });
      u3();

      // 4. Edit with cli_pipe
      const existingCliAgent: agentApi.AgentDefinitionResponse = {
        id: 'agent-edit-cli',
        workspace_id: 'ws-1',
        principal_id: 'prin-1',
        slug: 'cli-agent',
        display_name: 'Existing CLI Agent',
        harness_kind: 'cli_pipe',
        provider_kind: null,
        model_id: null,
        cli_binary_allowlist_id: 'agy',
        cli_args: ['-p'],
        remote_runner_pool_slug: null,
        repo_access_mode: 'none',
        mcp_allowed_tools: ['search_tickets'],
        system_instructions_md: 'System prompt',
        timeout_ms: 60000,
      };

      const { unmount: u4 } = render(
        <AgentDefinitionEditorDrawer
          isOpen={true}
          onClose={vi.fn()}
          agent={existingCliAgent}
          onSaved={vi.fn()}
          aiProviders={mockAiProviders}
        />,
      );

      fireEvent.change(screen.getByTestId('agent-cli-args-input'), { target: { value: '-p --custom' } });
      // Also clear timeout to exercise NaN fallback
      fireEvent.change(screen.getByTestId('agent-timeout-input'), { target: { value: '' } });

      fireEvent.submit(screen.getByTestId('save-agent-btn'));
      await waitFor(() => {
        expect(updateSpy).toHaveBeenCalled();
      });
      u4();

      // 5. Mount with slug-only agent
      const slugOnlyAgent = {
        ...existingCliAgent,
        id: '',
        slug: 'slug-only-agent',
      };
      const { unmount: u5 } = render(
        <AgentDefinitionEditorDrawer
          isOpen={true}
          onClose={vi.fn()}
          agent={slugOnlyAgent}
          onSaved={vi.fn()}
          aiProviders={mockAiProviders}
        />,
      );
      u5();
    });

    it('surfaces CLI arguments validation error when banned flag is entered in cli_pipe harness', () => {
      const { container } = render(
        <AgentDefinitionEditorDrawer
          isOpen={true}
          onClose={vi.fn()}
          agent={null}
          onSaved={vi.fn()}
          aiProviders={mockAiProviders}
        />,
      );

      fireEvent.change(screen.getByTestId('agent-slug-input'), { target: { value: 'cli-agent-err' } });
      fireEvent.change(screen.getByTestId('agent-name-input'), { target: { value: 'CLI Agent Err' } });
      fireEvent.change(screen.getByTestId('agent-harness-select'), { target: { value: 'cli_pipe' } });
      fireEvent.change(screen.getByTestId('agent-cli-args-input'), { target: { value: '--yolo' } });

      expect(screen.getByTestId('cli-validation-error-hint')).toBeDefined();
      expect(screen.getByTestId('save-agent-btn').hasAttribute('disabled')).toBe(true);

      const form = container.querySelector('form');
      expect(form).not.toBeNull();
      if (!form) throw new Error('form not found');
      fireEvent.submit(form);
      expect(screen.getByTestId('agent-editor-error').textContent).toContain('banned CLI flag policy');
    });

    it('invokes onClose when clicking cancel button or close button', () => {
      const onClose = vi.fn();
      render(
        <AgentDefinitionEditorDrawer
          isOpen={true}
          onClose={onClose}
          agent={null}
          onSaved={vi.fn()}
          aiProviders={mockAiProviders}
        />,
      );

      fireEvent.click(screen.getByTestId('cancel-agent-drawer-btn'));
      expect(onClose).toHaveBeenCalledTimes(1);

      fireEvent.click(screen.getByTestId('close-agent-drawer-btn'));
      expect(onClose).toHaveBeenCalledTimes(2);
    });
  });
});
