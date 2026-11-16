// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import React from 'react';
import { describe, expect, it, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
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
    expect(screen.getByLabelText(/Approved Wasm Module/i)).toBeDefined();
    expect(screen.queryByLabelText(/Agent Definition/i)).toBeNull();

    // Check mutable field labels checkbox is disabled for sync_validator
    const labelsCheckbox = screen.getByRole<HTMLInputElement>('checkbox', { name: /labels/i });
    expect(labelsCheckbox.disabled).toBe(true);

    // Switch to sync_mutator: Wasm module is visible, mutable fields are enabled
    fireEvent.click(screen.getByLabelText('Sync Wasm Mutator'));
    expect(screen.getByLabelText(/Approved Wasm Module/i)).toBeDefined();
    expect(screen.queryByLabelText(/Agent Definition/i)).toBeNull();
    expect(labelsCheckbox.disabled).toBe(false);

    // Switch to agent_interceptor: Wasm module hidden, Agent definition visible
    fireEvent.click(screen.getByLabelText('Agent Interceptor'));
    expect(screen.queryByLabelText(/Approved Wasm Module/i)).toBeNull();
    expect(screen.getByLabelText(/Agent Definition/i)).toBeDefined();
    expect(screen.getByTestId('agent-details-summary')).toBeDefined();
    expect(screen.getByText(/Validated CLI Args:/i)).toBeDefined();

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
    fireEvent.click(screen.getByLabelText('Agent Interceptor'));
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
});
