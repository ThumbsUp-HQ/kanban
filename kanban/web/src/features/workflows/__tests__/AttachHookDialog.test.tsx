// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import React from 'react';
import { describe, expect, it, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { AttachHookDialog } from '../AttachHookDialog';
import {
  DEFAULT_PROJECT_STATES,
  DEFAULT_WASM_MODULES,
  type AgentDefinitionSummary,
  type WorkflowHook,
} from '../api';

const mockAgents: AgentDefinitionSummary[] = [
  {
    id: 'agent-1',
    slug: 'forensic-code-check',
    display_name: 'Forensic Code Check',
    harness_kind: 'cli_pipe',
    cli_binary_allowlist_id: 'agy',
    cli_args: ['-p'],
    repo_access_mode: 'ro_vfs_mount',
    timeout_ms: 60000,
  },
  {
    id: 'agent-2',
    slug: 'sec-invariant-scan',
    display_name: 'Security Invariant Scanner',
    harness_kind: 'in_app_sdk',
    provider_kind: 'ollama',
    model_id: 'ollama/qwen2.5-coder',
    cli_args: [],
    repo_access_mode: 'ro_vfs_mount',
    timeout_ms: 30000,
  },
  {
    id: 'agent-3',
    slug: 'remote-runner-pool',
    display_name: 'Remote Runner Pool',
    harness_kind: 'remote_runner',
    remote_runner_pool_slug: 'gpu-pool-1',
    cli_args: [],
    repo_access_mode: 'none',
    timeout_ms: 90000,
  },
  {
    id: 'agent-4',
    slug: 'gemini-fallback',
    display_name: 'Gemini Direct',
    harness_kind: 'in_app_sdk',
    provider_kind: 'gemini',
    cli_args: [],
    repo_access_mode: 'ro_vfs_mount',
    timeout_ms: 30000,
  },
];

describe('AttachHookDialog (KB-P5-24)', () => {
  it('does not render when isOpen is false', () => {
    const { container } = render(
      <AttachHookDialog
        isOpen={false}
        projectKey="KAN"
        states={DEFAULT_PROJECT_STATES}
        agentDefinitions={mockAgents}
        onSave={vi.fn()}
        onClose={vi.fn()}
      />,
    );
    expect(container.firstChild).toBeNull();
  });

  it('switches hook_kind between sync_validator, sync_mutator, and agent_interceptor showing/hiding selectors (Mandatory Test Case 3)', () => {
    render(
      <AttachHookDialog
        isOpen={true}
        projectKey="KAN"
        states={DEFAULT_PROJECT_STATES}
        agentDefinitions={mockAgents}
        wasmModules={DEFAULT_WASM_MODULES}
        onSave={vi.fn()}
        onClose={vi.fn()}
      />,
    );

    // Initial is sync_validator
    expect(screen.getByLabelText(/Approved (WebAssembly|Wasm) Module/i)).toBeDefined();
    expect(screen.queryByLabelText(/Agent Definition/i)).toBeNull();

    // Check mutable field labels checkbox is disabled for sync_validator
    const labelsCheckbox = screen.getByRole<HTMLInputElement>('checkbox', { name: /labels/i });
    expect(labelsCheckbox.disabled).toBe(true);

    // Switch to sync_mutator: Wasm module is visible, mutable fields are enabled
    fireEvent.click(screen.getByLabelText('Sync Wasm Mutator'));
    expect(screen.getByLabelText(/Approved (WebAssembly|Wasm) Module/i)).toBeDefined();
    expect(screen.queryByLabelText(/Agent Definition/i)).toBeNull();
    expect(labelsCheckbox.disabled).toBe(false);

    // Switch to agent_interceptor: Wasm module hidden, Agent definition visible
    fireEvent.click(screen.getByLabelText('Agent Transition Helper'));
    expect(screen.queryByLabelText(/Approved Wasm Module/i)).toBeNull();
    expect(screen.getByLabelText(/Agent Definition/i)).toBeDefined();
    expect(screen.getByTestId('agent-details-summary')).toBeDefined();
    expect(screen.getByText(/Validated CLI Args:/i)).toBeDefined();

    // Switch back to sync_validator
    fireEvent.click(screen.getByLabelText('Sync Wasm Validator'));
    expect(screen.getByLabelText(/Approved (WebAssembly|Wasm) Module/i)).toBeDefined();

    // Invariant: state and description_markdown cannot be selected
    expect(screen.queryByRole('checkbox', { name: /^state$/i })).toBeNull();
    expect(screen.queryByRole('checkbox', { name: /^description_markdown$/i })).toBeNull();
  });

  it('validates required fields and prevents from_state === to_state', () => {
    const handleSave = vi.fn();
    render(
      <AttachHookDialog
        isOpen={true}
        projectKey="KAN"
        states={DEFAULT_PROJECT_STATES}
        agentDefinitions={mockAgents}
        onSave={handleSave}
        onClose={vi.fn()}
      />,
    );

    // Missing name
    fireEvent.submit(screen.getByRole('button', { name: 'Attach Hook' }));
    expect(screen.getByRole('alert').textContent).toContain('Hook name is required');
    expect(handleSave).not.toHaveBeenCalled();

    // Set identical from and to state
    fireEvent.change(screen.getByLabelText(/Hook Name/i), { target: { value: 'custom-check' } });
    fireEvent.change(screen.getByLabelText(/From State/i), { target: { value: 'Done' } });
    fireEvent.change(screen.getByLabelText(/To State/i), { target: { value: 'Done' } });

    fireEvent.submit(screen.getByRole('button', { name: 'Attach Hook' }));
    expect(screen.getByRole('alert').textContent).toContain('cannot be identical');
    expect(handleSave).not.toHaveBeenCalled();
  });

  it('successfully creates an agent_interceptor hook with selected mutable fields', async () => {
    const handleSave = vi.fn().mockResolvedValue(undefined);
    const handleClose = vi.fn();

    render(
      <AttachHookDialog
        isOpen={true}
        projectKey="KAN"
        states={DEFAULT_PROJECT_STATES}
        agentDefinitions={mockAgents}
        onSave={handleSave}
        onClose={handleClose}
      />,
    );

    // Fill form
    fireEvent.change(screen.getByLabelText(/Hook Name/i), { target: { value: 'code-review-agent' } });
    fireEvent.change(screen.getByLabelText(/From State/i), { target: { value: 'In Review' } });
    fireEvent.change(screen.getByLabelText(/To State/i), { target: { value: 'Done' } });

    // Switch to agent_interceptor
    fireEvent.click(screen.getByLabelText('Agent Transition Helper'));
    fireEvent.change(screen.getByLabelText(/Agent Definition/i), { target: { value: 'forensic-code-check' } });

    // Check mutable fields
    const labelsCheckbox = screen.getByRole('checkbox', { name: /labels/i });
    fireEvent.click(labelsCheckbox);

    // Submit
    fireEvent.click(screen.getByRole('button', { name: 'Attach Hook' }));

    await waitFor(() => {
      expect(handleSave).toHaveBeenCalledWith({
        name: 'code-review-agent',
        from_state: 'In Review',
        to_state: 'Done',
        hook_kind: 'agent_interceptor',
        failure_policy: 'fail_closed',
        agent: 'forensic-code-check',
        allowed_mutable_fields: ['labels'],
        timeout_ms: 60000,
      });
      expect(handleClose).toHaveBeenCalled();
    });
  });

  it('populates editingHook data when editing an existing hook', async () => {
    const existingHook: WorkflowHook = {
      id: 'hook-edit-1',
      name: 'existing-validator',
      from_state: 'In Progress',
      to_state: 'In Review',
      hook_kind: 'sync_validator',
      sort_rank: '0001',
      failure_policy: 'fail_open_warn',
      manifest_sha256: 'abc123',
      is_enabled: true,
      wasm_module_sha256: DEFAULT_WASM_MODULES[0]?.sha256,
    };

    const handleSave = vi.fn().mockResolvedValue(undefined);

    render(
      <AttachHookDialog
        isOpen={true}
        projectKey="KAN"
        editingHook={existingHook}
        states={DEFAULT_PROJECT_STATES}
        agentDefinitions={mockAgents}
        onSave={handleSave}
        onClose={vi.fn()}
      />,
    );

    expect(screen.getByText('Edit Hook: existing-validator')).toBeDefined();
    expect(screen.getByDisplayValue('existing-validator')).toBeDefined();

    // Update name and submit
    fireEvent.change(screen.getByLabelText(/Hook Name/i), { target: { value: 'updated-validator' } });
    fireEvent.click(screen.getByRole('button', { name: 'Update Hook' }));

    await waitFor(() => {
      expect(handleSave).toHaveBeenCalledWith(
        expect.objectContaining({
          name: 'updated-validator',
          failure_policy: 'fail_open_warn',
          hook_kind: 'sync_validator',
        }),
      );
    });
  });

  it('handles save errors and displays error alert', async () => {
    const handleSave = vi.fn().mockRejectedValue(new Error('Server validation failed: unapproved Wasm'));

    render(
      <AttachHookDialog
        isOpen={true}
        projectKey="KAN"
        states={DEFAULT_PROJECT_STATES}
        agentDefinitions={mockAgents}
        onSave={handleSave}
        onClose={vi.fn()}
      />,
    );

    fireEvent.change(screen.getByLabelText(/Hook Name/i), { target: { value: 'failing-hook' } });
    fireEvent.click(screen.getByRole('button', { name: 'Attach Hook' }));

    await waitFor(() => {
      expect(screen.getByRole('alert').textContent).toContain('unapproved Wasm');
    });
  });

  it('renders Configure Agent Definitions link pointing to /admin/agents when no agents exist (KAN-60)', () => {
    render(
      <MemoryRouter>
        <AttachHookDialog
          isOpen={true}
          projectKey="KAN"
          states={DEFAULT_PROJECT_STATES}
          agentDefinitions={[]}
          onSave={vi.fn()}
          onClose={vi.fn()}
        />
      </MemoryRouter>,
    );

    // Switch to agent_interceptor
    fireEvent.click(screen.getByLabelText('Agent Transition Helper'));

    expect(screen.getByTestId('no-agents-warning')).toBeDefined();
    const configLink = screen.getByTestId<HTMLAnchorElement>('configure-agents-link');
    expect(configLink.getAttribute('href')).toBe('/admin/agents');
  });

  it('supports Select All and Clear All toggles for allowed_mutable_fields and displays kind subtext descriptions', () => {
    render(
      <MemoryRouter>
        <AttachHookDialog
          isOpen={true}
          projectKey="KAN"
          states={DEFAULT_PROJECT_STATES}
          onSave={vi.fn()}
          onClose={vi.fn()}
        />
      </MemoryRouter>,
    );

    // Verify subtext descriptions for hook kinds
    expect(screen.getAllByText(/Deterministic WebAssembly rule/i).length).toBe(2);
    expect(screen.getByText(/Probabilistic autonomous AI Agent/i)).toBeDefined();

    // Switch to sync_mutator to enable mutable fields picker
    fireEvent.click(screen.getByLabelText('Sync Wasm Mutator'));

    // Open Advanced Section
    const advToggle = screen.getByTestId('attach-hook-advanced-section');
    fireEvent.click(advToggle);

    const selectAllBtn = screen.getByTestId('select-all-mutable-fields-btn');
    const clearAllBtn = screen.getByTestId('clear-all-mutable-fields-btn');

    fireEvent.click(selectAllBtn);
    fireEvent.click(clearAllBtn);

    // Toggle individual mutable field off and on
    const priorityCheckbox = screen.getByRole('checkbox', { name: /priority/i });
    fireEvent.click(priorityCheckbox);
    expect((priorityCheckbox as HTMLInputElement).checked).toBe(true);
    fireEvent.click(priorityCheckbox);
    expect((priorityCheckbox as HTMLInputElement).checked).toBe(false);

    // Toggle failure policy select
    const failureSelect = document.getElementById('failure-policy-select') as HTMLSelectElement;
    fireEvent.change(failureSelect, { target: { value: 'fail_open_warn' } });
    expect(failureSelect.value).toBe('fail_open_warn');
    fireEvent.change(failureSelect, { target: { value: 'fail_closed' } });
    expect(failureSelect.value).toBe('fail_closed');

    // Change wasm module
    const wasmSelect = document.getElementById('wasm-module-select') as HTMLSelectElement;
    fireEvent.change(wasmSelect, { target: { value: DEFAULT_WASM_MODULES[1]?.sha256 } });
  });

  it('renders raw execution logs when editing a hook with prior run logs', () => {
    const hookWithLogs: WorkflowHook = {
      id: 'hook-log-1',
      name: 'logged-validator',
      from_state: 'In Progress',
      to_state: 'In Review',
      hook_kind: 'sync_validator',
      sort_rank: '0001',
      failure_policy: 'fail_closed',
      manifest_sha256: 'abc123',
      is_enabled: true,
      last_execution_log: '2026-11-25 15:00:00 [PASS] All validation assertions satisfied.',
    };

    render(
      <AttachHookDialog
        isOpen={true}
        projectKey="KAN"
        editingHook={hookWithLogs}
        states={DEFAULT_PROJECT_STATES}
        agentDefinitions={mockAgents}
        onSave={vi.fn()}
        onClose={vi.fn()}
      />,
    );

    // Open advanced section
    const advToggle = screen.getByTestId('attach-hook-advanced-section');
    fireEvent.click(advToggle);

    expect(screen.getByTestId('hook-execution-log-output')).toBeDefined();
    expect(screen.getByTestId('hook-execution-log-output').textContent).toContain('[PASS] All validation assertions satisfied.');
  });

  it('covers agent definition selection across CLI, SDK, and Remote runner pools', () => {
    render(
      <AttachHookDialog
        isOpen={true}
        projectKey="KAN"
        states={DEFAULT_PROJECT_STATES}
        agentDefinitions={mockAgents}
        onSave={vi.fn()}
        onClose={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByLabelText('Agent Transition Helper'));
    const agentSelect = screen.getByLabelText(/Agent Definition/i);

    // Select SDK agent (timeout 30000, empty cli_args)
    fireEvent.change(agentSelect, { target: { value: 'sec-invariant-scan' } });
    expect(screen.getByText(/Harness: in_app_sdk/i)).toBeDefined();

    // Select Remote runner agent (timeout 90000)
    fireEvent.change(agentSelect, { target: { value: 'remote-runner-pool' } });
    expect(screen.getByText(/Harness: remote_runner/i)).toBeDefined();
  });

  it('covers saving agent hook when agent has no timeout_ms and non-Error save rejection', async () => {
    const mockOnSave = vi.fn().mockRejectedValueOnce('raw string rejection');
    const agentWithoutTimeout: AgentDefinitionSummary[] = [
      {
        id: 'agent-no-timeout',
        slug: 'no-timeout-agent',
        display_name: 'No Timeout Agent',
        harness_kind: 'cli_pipe',
        cli_args: [],
        repo_access_mode: 'none',
        timeout_ms: (undefined as unknown as number),
      },
    ];
    render(
      <AttachHookDialog
        isOpen={true}
        projectKey="KAN"
        states={DEFAULT_PROJECT_STATES}
        agentDefinitions={agentWithoutTimeout}
        onSave={mockOnSave}
        onClose={vi.fn()}
      />,
    );

    fireEvent.change(screen.getByLabelText(/Hook Name/i), { target: { value: 'No Timeout Hook' } });
    fireEvent.click(screen.getByLabelText('Agent Transition Helper'));
    fireEvent.click(screen.getByRole('button', { name: /Attach Hook/i }));

    expect(await screen.findByRole('alert')).toBeDefined();
    expect(screen.getByRole('alert').textContent).toContain('Failed to attach workflow hook.');
  });

  it('supports selecting wildcard all states for from_state', () => {
    render(
      <AttachHookDialog
        isOpen={true}
        projectKey="KAN"
        states={DEFAULT_PROJECT_STATES}
        agentDefinitions={mockAgents}
        onSave={vi.fn()}
        onClose={vi.fn()}
      />,
    );
    const fromSelect = document.getElementById('from-state-select') as HTMLSelectElement;
    fireEvent.change(fromSelect, { target: { value: '*' } });
    expect(fromSelect.value).toBe('*');
  });

  it('covers fallback wasm latency budget and provider_kind fallback when model_id is unset', () => {
    const customWasm = [
      {
        sha256: 'custom-sha-1234567890abcdef',
        name: 'custom-wasm',
        description: 'custom description',
        target_latency_budget: undefined,
      },
    ];
    render(
      <AttachHookDialog
        isOpen={true}
        projectKey="KAN"
        states={DEFAULT_PROJECT_STATES}
        agentDefinitions={mockAgents}
        wasmModules={customWasm}
        onSave={vi.fn()}
        onClose={vi.fn()}
      />,
    );
    expect(screen.getByText(/custom-wasm \(custom-s\.\.\. - <25ms\)/i)).toBeDefined();

    fireEvent.click(screen.getByLabelText('Agent Transition Helper'));
    const agentSelect = screen.getByLabelText(/Agent Definition/i);
    fireEvent.change(agentSelect, { target: { value: 'gemini-fallback' } });
    expect(screen.getByText(/Gemini Direct \(gemini\)/i)).toBeDefined();
  });
});
