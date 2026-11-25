// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import React from 'react';
import { AgentStudioPage } from '../AgentStudioPage';
import { AgentValidationModal } from '../AgentValidationModal';
import { AgentDefinitionEditorDrawer } from '../AgentDefinitionEditorDrawer';
import * as agentApi from '../agentDefinitionsApi';
import { validateCliArguments } from '../cliPolicy';
import * as clientModule from '../../../api/client';

describe('AgentStudioPage & Components (KANBA-219)', () => {
  const mockAgentSdk: agentApi.AgentDefinitionResponse = {
    id: 'agent-1',
    workspace_id: 'ws-1',
    principal_id: 'prin-1',
    slug: 'reality-checker',
    display_name: 'Reality Checker QA',
    harness_kind: 'in_app_sdk',
    provider_kind: 'gemini',
    model_id: 'gemini-2.5-flash',
    cli_binary_allowlist_id: null,
    cli_args: [],
    remote_runner_pool_slug: null,
    repo_access_mode: 'bare_git_tools',
    mcp_allowed_tools: ['search_tickets', 'read_ticket'],
    system_instructions_md: 'Audit verification packets with passive forensic rigor.',
    timeout_ms: 45000,
  };

  const mockAgentCli: agentApi.AgentDefinitionResponse = {
    id: 'agent-2',
    workspace_id: 'ws-1',
    principal_id: 'prin-2',
    slug: 'agy-reviewer',
    display_name: 'Antigravity CLI Pipe',
    harness_kind: 'cli_pipe',
    provider_kind: null,
    model_id: null,
    cli_binary_allowlist_id: 'agy',
    cli_args: ['-p', '--model', 'gemini-2.5-flash'],
    remote_runner_pool_slug: null,
    repo_access_mode: 'none',
    mcp_allowed_tools: ['search_knowledge', 'read_doc'],
    system_instructions_md: 'CLI execution runner.',
    timeout_ms: 60000,
  };

  const mockAgentRunner: agentApi.AgentDefinitionResponse = {
    id: 'agent-3',
    workspace_id: 'ws-1',
    principal_id: 'prin-3',
    slug: 'remote-builder',
    display_name: 'Remote Runner Worker',
    harness_kind: 'remote_runner',
    provider_kind: null,
    model_id: null,
    cli_binary_allowlist_id: null,
    cli_args: [],
    remote_runner_pool_slug: 'gpu-pool-us-east',
    repo_access_mode: 'ro_vfs_mount',
    mcp_allowed_tools: ['search_tickets'],
    system_instructions_md: 'Remote agent instructions.',
    timeout_ms: 120000,
  };

  const mockValidationPass: agentApi.AgentValidationResponse = {
    valid: true,
    exit_code: 0,
    status: 'COMPLETED_CLEAN',
    command: 'kanban-agent validate-echo --agent reality-checker',
    latency_ms: 142.5,
    tokens_in: 85,
    tokens_out: 42,
    rendered_context: 'Simulated prompt payload',
    tool_trace: 'No tools invoked in echo validation',
    report_text: '=== FORENSIC REPORT ===\n1. Target: @reality-checker\n2. Status: VALID\n3. Proof: Clean echo',
  };

  const mockValidationFail: agentApi.AgentValidationResponse = {
    valid: false,
    exit_code: 1,
    status: 'POLICY_VIOLATION',
    command: 'kanban-agent validate-echo --agent bad-agent',
    latency_ms: 22.1,
    tokens_in: 0,
    tokens_out: 0,
    rendered_context: '',
    tool_trace: '',
    report_text: '=== FORENSIC REPORT ===\n1. Target: @bad-agent\n2. Status: ERROR (Exit 1)',
  };

  beforeEach(() => {
    vi.restoreAllMocks();
  });

  describe('cliPolicy validation', () => {
    it('rejects unallowlisted binaries', () => {
      const res = validateCliArguments('bash', ['-c', 'echo 1']);
      expect(res.valid).toBe(false);
      expect(res.error).toContain("Binary identifier 'bash' is not allowlisted");
    });

    it('rejects banned flags like --yolo, --dangerously*, and --allow-all-tools', () => {
      expect(validateCliArguments('agy', ['-p', '--yolo']).valid).toBe(false);
      expect(validateCliArguments('agy', ['-p', '--YOLO']).valid).toBe(false);
      expect(validateCliArguments('agy', ['-p', '--yolo=true']).valid).toBe(false);
      expect(validateCliArguments('agy', ['-p', '--dangerously-skip-permissions']).valid).toBe(false);
      expect(validateCliArguments('agy', ['-p', '--dangerously-bypass-sandbox']).valid).toBe(false);
      expect(validateCliArguments('agy', ['-p', '--full-auto']).valid).toBe(false);
      expect(validateCliArguments('agy', ['-p', '--allow-all-tools']).valid).toBe(false);
    });

    it('rejects control characters in arguments', () => {
      expect(validateCliArguments('agy', ['-p\0hack']).valid).toBe(false);
      expect(validateCliArguments('agy', ['-p\rhack']).valid).toBe(false);
      expect(validateCliArguments('agy', ['-p\nhack']).valid).toBe(false);
    });

    it('enforces pinned prefix for codex binary across all positions', () => {
      // Too few args
      const shortRes = validateCliArguments('codex', ['exec', '-s']);
      expect(shortRes.valid).toBe(false);
      expect(shortRes.error).toContain('codex binary requires initial pinned arguments');

      // Mismatch at index 0
      expect(validateCliArguments('codex', ['run', '-s', 'read-only', '-']).error).toContain("must be 'exec'");
      // Mismatch at index 1
      expect(validateCliArguments('codex', ['exec', '-x', 'read-only', '-']).error).toContain("must be '-s'");
      // Mismatch at index 2
      expect(validateCliArguments('codex', ['exec', '-s', 'read-write', '-']).error).toContain("must be 'read-only'");
      // Mismatch at index 3
      expect(validateCliArguments('codex', ['exec', '-s', 'read-only', 'file.txt']).error).toContain("must be '-'");

      // Valid codex args
      const validRes = validateCliArguments('codex', ['exec', '-s', 'read-only', '-', '--json']);
      expect(validRes.valid).toBe(true);

      // Empty arg fallback
      expect(validateCliArguments('agy', ['', '-p']).valid).toBe(true);
      expect(validateCliArguments('agy', [undefined as unknown as string]).valid).toBe(true);
    });

    it('allows permitted arguments for agy and claude-code', () => {
      expect(validateCliArguments('agy', ['-p', '--json']).valid).toBe(true);
      expect(validateCliArguments('claude-code', ['--print', '--verbose']).valid).toBe(true);
      expect(validateCliArguments('gemini-cli', ['--prompt', 'test']).valid).toBe(true);
    });
  });

  describe('agentDefinitionsApi functions', () => {
    it('exercises all agent definition API helpers', async () => {
      const fetchSpy = vi.spyOn(clientModule, 'apiFetch').mockResolvedValue([mockAgentSdk]);

      const list = await agentApi.fetchAgentDefinitions();
      expect(list).toEqual([mockAgentSdk]);

      fetchSpy.mockResolvedValueOnce([mockAgentSdk]);
      const listWithProject = await agentApi.fetchAgentDefinitions('my-ws', 'proj-123');
      expect(listWithProject).toEqual([mockAgentSdk]);
      expect(fetchSpy).toHaveBeenCalledWith(
        'GET',
        '/api/v1/workspaces/my-ws/agent-definitions?project_id=proj-123',
      );

      fetchSpy.mockResolvedValueOnce(mockAgentSdk);
      const single = await agentApi.fetchAgentDefinition('reality-checker');
      expect(single).toEqual(mockAgentSdk);

      fetchSpy.mockResolvedValueOnce(mockAgentSdk);
      const created = await agentApi.createAgentDefinition({
        slug: 'new-agent',
        display_name: 'New Agent',
        harness_kind: 'in_app_sdk',
      });
      expect(created).toEqual(mockAgentSdk);

      fetchSpy.mockResolvedValueOnce(mockAgentSdk);
      const updated = await agentApi.updateAgentDefinition('agent-1', {
        display_name: 'Updated Name',
      });
      expect(updated).toEqual(mockAgentSdk);

      fetchSpy.mockResolvedValueOnce(undefined);
      await agentApi.deleteAgentDefinition('agent-1');

      fetchSpy.mockResolvedValueOnce(mockValidationPass);
      const val = await agentApi.validateAgentDefinition('agent-1');
      expect(val).toEqual(mockValidationPass);
    });
  });

  describe('AgentStudioPage component', () => {
    it('renders agent cards for each harness kind and handles delete modal', async () => {
      vi.spyOn(agentApi, 'fetchAgentDefinitions').mockResolvedValue([
        mockAgentSdk,
        mockAgentCli,
        mockAgentRunner,
      ]);
      const deleteSpy = vi.spyOn(agentApi, 'deleteAgentDefinition').mockResolvedValue(undefined);

      render(<AgentStudioPage />);

      expect(screen.getByTestId('agent-studio-loading')).toBeDefined();

      await waitFor(() => {
        expect(screen.getByText('Reality Checker QA')).toBeDefined();
        expect(screen.getByText('Antigravity CLI Pipe')).toBeDefined();
        expect(screen.getByText('Remote Runner Worker')).toBeDefined();
      });

      expect(screen.getByTestId('agent-handle-agent-1').textContent).toBe('@reality-checker');
      expect(screen.getByTestId('harness-badge-in_app_sdk')).toBeDefined();
      expect(screen.getByTestId('harness-badge-cli_pipe')).toBeDefined();
      expect(screen.getByTestId('harness-badge-remote_runner')).toBeDefined();

      // Open and cancel delete modal
      fireEvent.click(screen.getByTestId('delete-agent-btn-agent-1'));
      expect(screen.getByTestId('delete-agent-modal')).toBeDefined();
      fireEvent.click(screen.getByTestId('cancel-delete-agent-btn'));
      expect(screen.queryByTestId('delete-agent-modal')).toBeNull();

      // Open and confirm delete
      fireEvent.click(screen.getByTestId('delete-agent-btn-agent-1'));
      fireEvent.click(screen.getByTestId('confirm-delete-agent-btn'));

      await waitFor(() => {
        expect(deleteSpy).toHaveBeenCalledWith('agent-1');
      });
    });

    it('renders empty placeholder when no agents exist', async () => {
      vi.spyOn(agentApi, 'fetchAgentDefinitions').mockResolvedValue([]);

      render(<AgentStudioPage />);

      await waitFor(() => {
        expect(screen.getByTestId('empty-agents-placeholder')).toBeDefined();
      });
    });

    it('renders error message when loading fails', async () => {
      vi.spyOn(agentApi, 'fetchAgentDefinitions').mockRejectedValue(new Error('Network failure'));

      render(<AgentStudioPage />);

      await waitFor(() => {
        expect(screen.getByTestId('agent-studio-error').textContent).toContain('Network failure');
      });
    });

    it('opens drawer on Register Agent and handles validation modal on card button click', async () => {
      vi.spyOn(agentApi, 'fetchAgentDefinitions').mockResolvedValue([mockAgentSdk]);
      vi.spyOn(agentApi, 'validateAgentDefinition').mockResolvedValue(mockValidationPass);

      render(<AgentStudioPage />);

      await waitFor(() => {
        expect(screen.getByTestId('register-agent-btn')).toBeDefined();
      });

      // Register button opens drawer
      fireEvent.click(screen.getByTestId('register-agent-btn'));
      expect(screen.getByTestId('agent-editor-drawer')).toBeDefined();

      // Close drawer
      fireEvent.click(screen.getByTestId('close-agent-drawer-btn'));
      expect(screen.queryByTestId('agent-editor-drawer')).toBeNull();

      // Click Edit button
      fireEvent.click(screen.getByTestId('edit-agent-btn-agent-1'));
      expect(screen.getByTestId('agent-editor-drawer')).toBeDefined();
      expect(screen.getByTestId<HTMLInputElement>('agent-name-input').value).toBe('Reality Checker QA');
      fireEvent.click(screen.getByTestId('cancel-agent-drawer-btn'));

      // Click Test Validation button
      fireEvent.click(screen.getByTestId('validate-agent-btn-agent-1'));
      expect(screen.getByTestId('agent-validation-modal')).toBeDefined();

      await waitFor(() => {
        expect(screen.getByTestId('validation-verdict-badge').textContent).toContain('PASS');
      });
      fireEvent.click(screen.getByTestId('dismiss-validation-btn'));
      expect(screen.queryByTestId('agent-validation-modal')).toBeNull();
    });

    it('handles delete failure gracefully', async () => {
      vi.spyOn(agentApi, 'fetchAgentDefinitions').mockResolvedValue([mockAgentSdk]);
      vi.spyOn(agentApi, 'deleteAgentDefinition').mockRejectedValue(new Error('Delete restricted'));

      render(<AgentStudioPage />);

      await waitFor(() => {
        expect(screen.getByTestId('delete-agent-btn-agent-1')).toBeDefined();
      });

      fireEvent.click(screen.getByTestId('delete-agent-btn-agent-1'));
      fireEvent.click(screen.getByTestId('confirm-delete-agent-btn'));

      await waitFor(() => {
        expect(screen.getByTestId('agent-studio-error').textContent).toContain('Delete restricted');
      });
    });
  });

  describe('AgentValidationModal component', () => {
    it('returns null when isOpen is false or agent is null', () => {
      const { container } = render(
        <AgentValidationModal isOpen={false} onClose={vi.fn()} agent={mockAgentSdk} />,
      );
      expect(container.firstChild).toBeNull();
    });

    it('renders fail verdict badge and exit code when validation fails', async () => {
      vi.spyOn(agentApi, 'validateAgentDefinition').mockResolvedValue(mockValidationFail);
      const onClose = vi.fn();

      render(
        <AgentValidationModal isOpen={true} onClose={onClose} agent={mockAgentSdk} />,
      );

      await waitFor(() => {
        expect(screen.getByTestId('validation-verdict-badge').textContent).toContain('FAIL (Exit 1)');
      });

      expect(screen.getByText(/POLICY_VIOLATION/)).toBeDefined();
      fireEvent.click(screen.getByTestId('close-validation-modal-btn'));
      expect(onClose).toHaveBeenCalled();
    });

    it('renders error message when validation request throws', async () => {
      vi.spyOn(agentApi, 'validateAgentDefinition').mockRejectedValue(new Error('Process timed out'));

      render(
        <AgentValidationModal isOpen={true} onClose={vi.fn()} agent={mockAgentSdk} />,
      );

      await waitFor(() => {
        expect(screen.getByTestId('validation-error').textContent).toContain('Process timed out');
      });
    });
  });

  describe('AgentDefinitionEditorDrawer component', () => {
    it('returns null when isOpen is false', () => {
      const { container } = render(
        <AgentDefinitionEditorDrawer isOpen={false} onClose={vi.fn()} agent={null} onSaved={vi.fn()} />,
      );
      expect(container.firstChild).toBeNull();
    });

    it('creates a new agent with validation, tool toggles, and harness switching', async () => {
      const createSpy = vi.spyOn(agentApi, 'createAgentDefinition').mockResolvedValue(mockAgentSdk);
      const onSaved = vi.fn();
      const onClose = vi.fn();

      render(
        <AgentDefinitionEditorDrawer
          isOpen={true}
          onClose={onClose}
          agent={null}
          onSaved={onSaved}
        />,
      );

      expect(screen.getByText('Register Autonomous Agent')).toBeDefined();

      // Submit without slug
      fireEvent.click(screen.getByTestId('save-agent-btn'));
      await waitFor(() => {
        expect(screen.getByTestId('agent-editor-error').textContent).toContain('Slug is required');
      });

      // Enter invalid slug
      fireEvent.change(screen.getByTestId('agent-slug-input'), { target: { value: 'BAD_SLUG!' } });
      fireEvent.change(screen.getByTestId('agent-name-input'), { target: { value: 'Valid Name' } });
      fireEvent.click(screen.getByTestId('save-agent-btn'));
      await waitFor(() => {
        expect(screen.getByTestId('agent-editor-error').textContent).toContain('lowercase alphanumeric');
      });

      // Enter valid slug
      fireEvent.change(screen.getByTestId('agent-slug-input'), { target: { value: 'code-auditor' } });

      // Change harness to cli_pipe
      fireEvent.change(screen.getByTestId('agent-harness-select'), { target: { value: 'cli_pipe' } });
      expect(screen.getByTestId('agent-cli-binary-select')).toBeDefined();

      // Select codex binary (should auto-fill pinned args)
      fireEvent.change(screen.getByTestId('agent-cli-binary-select'), { target: { value: 'codex' } });
      expect(screen.getByTestId<HTMLInputElement>('agent-cli-args-input').value).toBe(
        'exec -s read-only -',
      );

      // Select agy binary (should auto-fill -p)
      fireEvent.change(screen.getByTestId('agent-cli-binary-select'), { target: { value: 'agy' } });
      expect(screen.getByTestId<HTMLInputElement>('agent-cli-args-input').value).toBe('-p');

      // Enter banned flag to trigger warning
      fireEvent.change(screen.getByTestId('agent-cli-args-input'), { target: { value: '-p --yolo' } });
      expect(screen.getByTestId('cli-validation-error-hint')).toBeDefined();

      // Fix cli args
      fireEvent.change(screen.getByTestId('agent-cli-args-input'), { target: { value: '-p --verbose' } });
      expect(screen.queryByTestId('cli-validation-error-hint')).toBeNull();

      // Toggle tool
      const toolCheck = screen.getByTestId<HTMLInputElement>('tool-checkbox-search_tickets');
      expect(toolCheck.checked).toBe(true);
      fireEvent.click(toolCheck);
      expect(toolCheck.checked).toBe(false);

      // Change repo access mode
      fireEvent.change(screen.getByTestId('agent-repo-mode-select'), {
        target: { value: 'bare_git_tools' },
      });

      // Change timeout
      fireEvent.change(screen.getByTestId('agent-timeout-input'), { target: { value: '55000' } });

      // Save
      fireEvent.click(screen.getByTestId('save-agent-btn'));

      await waitFor(() => {
        expect(createSpy).toHaveBeenCalledWith(
          expect.objectContaining({
            slug: 'code-auditor',
            display_name: 'Valid Name',
            harness_kind: 'cli_pipe',
            cli_binary_allowlist_id: 'agy',
            cli_args: ['-p', '--verbose'],
            repo_access_mode: 'bare_git_tools',
            timeout_ms: 55000,
          }),
        );
        expect(onSaved).toHaveBeenCalled();
        expect(onClose).toHaveBeenCalled();
      });
    });

    it('updates an existing agent and handles remote_runner harness', async () => {
      const updateSpy = vi.spyOn(agentApi, 'updateAgentDefinition').mockResolvedValue(mockAgentRunner);
      const onSaved = vi.fn();
      const onClose = vi.fn();

      render(
        <AgentDefinitionEditorDrawer
          isOpen={true}
          onClose={onClose}
          agent={mockAgentRunner}
          onSaved={onSaved}
        />,
      );

      expect(screen.getByText('Edit @remote-builder')).toBeDefined();
      expect(screen.getByTestId('agent-runner-pool-input')).toBeDefined();

      fireEvent.change(screen.getByTestId('agent-name-input'), { target: { value: 'Renamed Runner' } });
      fireEvent.change(screen.getByTestId('agent-runner-pool-input'), { target: { value: 'gpu-pool-west' } });

      fireEvent.click(screen.getByTestId('save-agent-btn'));

      await waitFor(() => {
        expect(updateSpy).toHaveBeenCalledWith(
          'agent-3',
          expect.objectContaining({
            display_name: 'Renamed Runner',
            remote_runner_pool_slug: 'gpu-pool-west',
          }),
        );
        expect(onSaved).toHaveBeenCalled();
        expect(onClose).toHaveBeenCalled();
      });
    });

    it('handles api submission failure in drawer', async () => {
      vi.spyOn(agentApi, 'createAgentDefinition').mockRejectedValue(new Error('Duplicate slug'));

      render(
        <AgentDefinitionEditorDrawer
          isOpen={true}
          onClose={vi.fn()}
          agent={null}
          onSaved={vi.fn()}
        />,
      );

      fireEvent.change(screen.getByTestId('agent-slug-input'), { target: { value: 'dup-slug' } });
      fireEvent.change(screen.getByTestId('agent-name-input'), { target: { value: 'Dup Agent' } });
      fireEvent.click(screen.getByTestId('save-agent-btn'));

      await waitFor(() => {
        expect(screen.getByTestId('agent-editor-error').textContent).toContain('Duplicate slug');
      });

      // Non-Error rejection
      vi.spyOn(agentApi, 'createAgentDefinition').mockRejectedValue('raw string failure');
      fireEvent.click(screen.getByTestId('save-agent-btn'));
      await waitFor(() => {
        expect(screen.getByTestId('agent-editor-error').textContent).toContain(
          'Failed to save agent definition',
        );
      });
    });

    it('creates in_app_sdk agent and changes provider, model, instructions, and checks tools', async () => {
      const createSpy = vi.spyOn(agentApi, 'createAgentDefinition').mockResolvedValue(mockAgentSdk);
      const onSaved = vi.fn();
      const onClose = vi.fn();

      render(
        <AgentDefinitionEditorDrawer
          isOpen={true}
          onClose={onClose}
          agent={null}
          onSaved={onSaved}
        />,
      );

      fireEvent.change(screen.getByTestId('agent-slug-input'), { target: { value: 'test-sdk-agent' } });
      fireEvent.change(screen.getByTestId('agent-name-input'), { target: { value: 'Test SDK Agent' } });

      // Change provider kind to openai
      fireEvent.change(screen.getByTestId('agent-provider-select'), { target: { value: 'openai' } });
      fireEvent.change(screen.getByTestId('agent-model-input'), { target: { value: 'gpt-4o' } });

      // Check an unchecked tool
      const readTicketCheck = screen.getByTestId<HTMLInputElement>('tool-checkbox-read_ticket');
      if (!readTicketCheck.checked) {
        fireEvent.click(readTicketCheck);
      }

      // Change instructions
      fireEvent.change(screen.getByTestId('agent-instructions-textarea'), {
        target: { value: 'Custom instructions for SDK agent' },
      });

      fireEvent.click(screen.getByTestId('save-agent-btn'));

      await waitFor(() => {
        expect(createSpy).toHaveBeenCalledWith(
          expect.objectContaining({
            slug: 'test-sdk-agent',
            provider_kind: 'openai',
            model_id: 'gpt-4o',
            system_instructions_md: 'Custom instructions for SDK agent',
          }),
        );
        expect(onSaved).toHaveBeenCalled();
      });
    });
  });

  describe('AgentStudioPage & ValidationModal non-Error fallback coverage', () => {
    it('handles non-Error rejection on agent load and delete', async () => {
      vi.spyOn(agentApi, 'fetchAgentDefinitions').mockRejectedValue('raw agent load failure');

      render(<AgentStudioPage />);

      await waitFor(() => {
        expect(screen.getByTestId('agent-studio-error').textContent).toContain(
          'Failed to load agent definitions',
        );
      });
    });

    it('handles non-Error rejection on delete', async () => {
      vi.spyOn(agentApi, 'fetchAgentDefinitions').mockResolvedValue([mockAgentSdk]);
      vi.spyOn(agentApi, 'deleteAgentDefinition').mockRejectedValue('raw agent delete failure');

      render(<AgentStudioPage />);

      await waitFor(() => {
        expect(screen.getByTestId('delete-agent-btn-agent-1')).toBeDefined();
      });

      fireEvent.click(screen.getByTestId('delete-agent-btn-agent-1'));
      fireEvent.click(screen.getByTestId('confirm-delete-agent-btn'));

      await waitFor(() => {
        expect(screen.getByTestId('agent-studio-error').textContent).toContain(
          'Failed to delete agent definition',
        );
      });
    });

    it('validates empty display name and invalid cli arguments on submit', async () => {
      render(
        <AgentDefinitionEditorDrawer
          isOpen={true}
          onClose={vi.fn()}
          agent={null}
          onSaved={vi.fn()}
        />,
      );

      fireEvent.change(screen.getByTestId('agent-slug-input'), { target: { value: 'valid-slug' } });
      fireEvent.change(screen.getByTestId('agent-name-input'), { target: { value: '   ' } });

      fireEvent.click(screen.getByTestId('save-agent-btn'));
      await waitFor(() => {
        expect(screen.getByTestId('agent-editor-error').textContent).toContain('Display name is required');
      });

      // Valid display name, but cli_pipe with invalid args
      fireEvent.change(screen.getByTestId('agent-name-input'), { target: { value: 'Valid Name' } });
      fireEvent.change(screen.getByTestId('agent-harness-select'), { target: { value: 'cli_pipe' } });
      fireEvent.change(screen.getByTestId('agent-cli-args-input'), { target: { value: '-p --yolo' } });

      const form = screen.getByTestId('agent-name-input').closest('form');
      if (!form) throw new Error('form not found');
      fireEvent.submit(form);

      await waitFor(() => {
        expect(screen.getByTestId('agent-editor-error').textContent).toContain('banned CLI flag policy');
      });

      // Change binary to claude-code
      fireEvent.change(screen.getByTestId('agent-cli-binary-select'), { target: { value: 'claude-code' } });
      expect(screen.getByTestId<HTMLSelectElement>('agent-cli-binary-select').value).toBe('claude-code');
    });

    it('handles unmount during load in AgentStudioPage and AgentValidationModal (resolve and reject)', () => {
      let resolveAgents!: (v: agentApi.AgentDefinitionResponse[]) => void;
      vi.spyOn(agentApi, 'fetchAgentDefinitions').mockReturnValue(
        new Promise((resolve) => { resolveAgents = resolve; }),
      );
      const page1 = render(<AgentStudioPage />);
      page1.unmount();
      resolveAgents([mockAgentSdk]);

      let rejectAgents!: (e: unknown) => void;
      vi.spyOn(agentApi, 'fetchAgentDefinitions').mockReturnValue(
        new Promise((_, reject) => { rejectAgents = reject; }),
      );
      const page2 = render(<AgentStudioPage />);
      page2.unmount();
      rejectAgents(new Error('unmounted reject'));

      let resolveVal!: (v: agentApi.AgentValidationResponse) => void;
      vi.spyOn(agentApi, 'validateAgentDefinition').mockReturnValue(
        new Promise((resolve) => { resolveVal = resolve; }),
      );
      const val1 = render(<AgentValidationModal isOpen={true} onClose={vi.fn()} agent={mockAgentSdk} />);
      val1.unmount();
      resolveVal(mockValidationPass);

      let rejectVal!: (e: unknown) => void;
      vi.spyOn(agentApi, 'validateAgentDefinition').mockReturnValue(
        new Promise((_, reject) => { rejectVal = reject; }),
      );
      const val2 = render(<AgentValidationModal isOpen={true} onClose={vi.fn()} agent={mockAgentSdk} />);
      val2.unmount();
      rejectVal(new Error('unmounted val reject'));
    });

    it('updates an existing cli_pipe agent and handles NaN timeout fallback', async () => {
      const updateSpy = vi.spyOn(agentApi, 'updateAgentDefinition').mockResolvedValue(mockAgentCli);
      render(
        <AgentDefinitionEditorDrawer
          isOpen={true}
          onClose={vi.fn()}
          agent={mockAgentCli}
          onSaved={vi.fn()}
        />,
      );

      fireEvent.change(screen.getByTestId('agent-timeout-input'), { target: { value: '' } });
      fireEvent.change(screen.getByTestId('agent-name-input'), { target: { value: 'Updated CLI Agent' } });
      fireEvent.click(screen.getByTestId('save-agent-btn'));

      await waitFor(() => {
        expect(updateSpy).toHaveBeenCalledWith(
          'agent-2',
          expect.objectContaining({
            cli_binary_allowlist_id: 'agy',
            timeout_ms: 60000,
          }),
        );
      });
    });

    it('updates an existing in_app_sdk agent and toggles tools', async () => {
      const updateSpy = vi.spyOn(agentApi, 'updateAgentDefinition').mockResolvedValue(mockAgentSdk);
      const onSaved = vi.fn();
      const onClose = vi.fn();

      render(
        <AgentDefinitionEditorDrawer
          isOpen={true}
          onClose={onClose}
          agent={mockAgentSdk}
          onSaved={onSaved}
        />,
      );

      // Toggle tool checkbox off and on
      const searchTicketsCheck = screen.getByTestId<HTMLInputElement>('tool-checkbox-search_tickets');
      expect(searchTicketsCheck.checked).toBe(true);
      fireEvent.click(searchTicketsCheck);
      expect(searchTicketsCheck.checked).toBe(false);
      fireEvent.click(searchTicketsCheck);
      expect(searchTicketsCheck.checked).toBe(true);

      fireEvent.change(screen.getByTestId('agent-name-input'), { target: { value: 'Renamed SDK' } });
      fireEvent.click(screen.getByTestId('save-agent-btn'));

      await waitFor(() => {
        expect(updateSpy).toHaveBeenCalledWith(
          'agent-1',
          expect.objectContaining({
            display_name: 'Renamed SDK',
            provider_kind: 'gemini',
            model_id: 'gemini-2.5-flash',
          }),
        );
        expect(onSaved).toHaveBeenCalled();
        expect(onClose).toHaveBeenCalled();
      });
    });
    it('handles non-array response from fetchAgentDefinitions gracefully', async () => {
      vi.spyOn(agentApi, 'fetchAgentDefinitions').mockResolvedValue(
        {} as unknown as agentApi.AgentDefinitionResponse[],
      );
      render(<AgentStudioPage />);
      await waitFor(() => {
        expect(screen.getByTestId('empty-agents-placeholder')).toBeDefined();
      });
    });

    it('silently ignores Aal2StepUpCancelledError during load with zero role="alert" banners', async () => {
      vi.spyOn(agentApi, 'fetchAgentDefinitions').mockRejectedValue(new clientModule.Aal2StepUpCancelledError());
      render(<AgentStudioPage />);
      await waitFor(() => {
        expect(screen.queryByTestId('loading-spinner')).toBeNull();
      });
      expect(screen.queryByRole('alert')).toBeNull();
      expect(screen.queryByTestId('agent-studio-error')).toBeNull();
    });

    it('silently ignores Aal2StepUpCancelledError during delete with zero role="alert" banners', async () => {
      vi.spyOn(agentApi, 'fetchAgentDefinitions').mockResolvedValue([mockAgentSdk]);
      vi.spyOn(agentApi, 'deleteAgentDefinition').mockRejectedValue(new clientModule.Aal2StepUpCancelledError());
      render(<AgentStudioPage />);
      await waitFor(() => {
        expect(screen.getByTestId('delete-agent-btn-agent-1')).toBeDefined();
      });
      fireEvent.click(screen.getByTestId('delete-agent-btn-agent-1'));
      await waitFor(() => {
        expect(screen.getByTestId('confirm-delete-agent-btn')).toBeDefined();
      });
      fireEvent.click(screen.getByTestId('confirm-delete-agent-btn'));
      await waitFor(() => {
        expect(screen.queryByRole('alert')).toBeNull();
        expect(screen.queryByTestId('agent-studio-error')).toBeNull();
      });
    });

    it('renders AdminStudioSubnav when showSubnav is not false and not inside project', async () => {
      vi.spyOn(agentApi, 'fetchAgentDefinitions').mockResolvedValue([mockAgentSdk]);
      render(<AgentStudioPage isServerAdmin={true} /> as React.ReactElement);
      await waitFor(() => {
        expect(screen.getByTestId('tab-admin-agents')).toBeDefined();
      });
    });

    it('suppresses AdminStudioSubnav when projectId is present or showSubnav is false', async () => {
      vi.spyOn(agentApi, 'fetchAgentDefinitions').mockResolvedValue([mockAgentSdk]);
      const { unmount } = render(<AgentStudioPage projectId="proj-123" />);
      await waitFor(() => {
        expect(screen.getByTestId('agent-card-agent-1')).toBeDefined();
      });
      expect(screen.queryByTestId('tab-admin-agents')).toBeNull();

      unmount();

      render(<AgentStudioPage showSubnav={false} />);
      await waitFor(() => {
        expect(screen.getByTestId('agent-card-agent-1')).toBeDefined();
      });
      expect(screen.queryByTestId('tab-admin-agents')).toBeNull();
    });
  });
});
