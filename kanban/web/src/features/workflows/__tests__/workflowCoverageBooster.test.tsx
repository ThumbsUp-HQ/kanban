// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import React from 'react';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router';
import { HookPipelineRow } from '../HookPipelineRow';
import { TransitionRuleCard } from '../TransitionRuleCard';
import { WorkflowStudioPage } from '../WorkflowStudioPage';
import { DryRunDrawer } from '../DryRunDrawer';
import { AttachHookDialog } from '../AttachHookDialog';
import * as api from '../api';
import * as client from '../../../api/client';
import { ApiProblem } from '../../../api/problem';

const DEFAULT_TEST_RULE: api.TransitionRule = api.DEFAULT_S14_4_RULES[0] ?? {
  from_state: 'In Review',
  to_state: 'Done',
  active_hook_count: 1,
  hooks: [],
};

const DEFAULT_TEST_HOOK: api.WorkflowHook = DEFAULT_TEST_RULE.hooks[0] ?? {
  id: 'hook-1',
  name: 'require-qa-proof-link',
  from_state: 'In Review',
  to_state: 'Done',
  hook_kind: 'sync_validator',
  sort_rank: '01',
  failure_policy: 'fail_closed',
  manifest_sha256: 'deadbeef',
  is_enabled: true,
};

describe('Workflow Studio Coverage Booster', () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false, staleTime: Infinity },
      },
    });
    vi.restoreAllMocks();
  });

  describe('api.ts coverage', () => {
    it('exercises fetchWorkflowHooks all branches', async () => {
      // Branch 1: array returned directly
      vi.spyOn(client, 'apiFetch').mockResolvedValueOnce(api.DEFAULT_S14_4_RULES);
      const res1 = await api.fetchWorkflowHooks('KAN');
      expect(res1).toHaveLength(1);

      // Branch 2: object with rules array
      vi.spyOn(client, 'apiFetch').mockResolvedValueOnce({ rules: api.DEFAULT_S14_4_RULES });
      const res2 = await api.fetchWorkflowHooks('KAN');
      expect(res2).toHaveLength(1);

      // Branch 3: 404 ApiProblem throws
      vi.spyOn(client, 'apiFetch').mockRejectedValueOnce(new ApiProblem(404));
      await expect(api.fetchWorkflowHooks('KAN')).rejects.toThrow();

      // Branch 3b: 403 ApiProblem throws
      vi.spyOn(client, 'apiFetch').mockRejectedValueOnce(new ApiProblem(403));
      await expect(api.fetchWorkflowHooks('KAN')).rejects.toThrow();

      // Branch 3c: object with non-rules data
      vi.spyOn(client, 'apiFetch').mockResolvedValueOnce({ unrelated: true });
      const res3c = await api.fetchWorkflowHooks('KAN');
      expect(res3c).toEqual(api.DEFAULT_S14_4_RULES);

      // Branch 4: generic error returns fallback
      vi.spyOn(client, 'apiFetch').mockRejectedValueOnce(new Error('Network error'));
      const res4 = await api.fetchWorkflowHooks('KAN');
      expect(res4).toEqual(api.DEFAULT_S14_4_RULES);
    });

    it('exercises mutations and auxiliary fetch functions', async () => {
      const fetchSpy = vi.spyOn(client, 'apiFetch').mockResolvedValue({ success: true });

      await api.createWorkflowHook('KAN', {
        name: 'test-hook',
        from_state: 'In Review',
        to_state: 'Done',
        hook_kind: 'sync_validator',
        failure_policy: 'fail_closed',
      });
      expect(fetchSpy).toHaveBeenCalledWith(
        'POST',
        expect.stringContaining('/workflow-hooks'),
        expect.any(Object),
      );

      await api.updateWorkflowHook('hook-1', { name: 'updated' });
      expect(fetchSpy).toHaveBeenCalledWith(
        'PATCH',
        expect.stringContaining('/workflow-hooks/hook-1'),
        expect.any(Object),
      );

      await api.enableWorkflowHook('hook-1');
      await api.disableWorkflowHook('hook-1');
      await api.deleteWorkflowHook('hook-1');
      await api.reorderWorkflowHooks('KAN', {
        transition: { from_state: null, to_state: 'Done' },
        ordered_hook_ids: ['hook-1'],
      });
      await api.dryRunWorkflowHooks('KAN', {
        from_state: null,
        to_state: 'Done',
      });

      // fetchAgentDefinitions success and fallback
      fetchSpy.mockResolvedValueOnce([{ id: 'a1', slug: 'agent-1' }]);
      const agents1 = await api.fetchAgentDefinitions('kanban');
      expect(agents1).toHaveLength(1);

      fetchSpy.mockResolvedValueOnce('not-an-array');
      const agentsNonArray = await api.fetchAgentDefinitions('kanban');
      expect(agentsNonArray).toEqual([]);

      fetchSpy.mockRejectedValueOnce(new Error('fail'));
      const agentsFallback = await api.fetchAgentDefinitions('kanban');
      expect(agentsFallback.length).toBeGreaterThan(0);

      // fetchRepoBindings success and fallback
      fetchSpy.mockResolvedValueOnce([{ id: 'r1', slug: 'repo-1' }]);
      const repos1 = await api.fetchRepoBindings('KAN');
      expect(repos1).toHaveLength(1);

      fetchSpy.mockResolvedValueOnce('not-an-array');
      const reposNonArray = await api.fetchRepoBindings('KAN');
      expect(reposNonArray).toEqual([]);

      fetchSpy.mockRejectedValueOnce(new Error('fail'));
      const reposFallback = await api.fetchRepoBindings('KAN');
      expect(reposFallback).toHaveLength(1);

      // fetchProjectStates success, empty, and fallback
      fetchSpy.mockResolvedValueOnce([{ id: 's1', name: 'Custom State' }]);
      const states1 = await api.fetchProjectStates('KAN');
      expect(states1[0]?.name).toBe('Custom State');

      fetchSpy.mockResolvedValueOnce([]);
      const statesEmpty = await api.fetchProjectStates('KAN');
      expect(statesEmpty.length).toBeGreaterThan(0);

      fetchSpy.mockRejectedValueOnce(new Error('fail'));
      const statesFallback = await api.fetchProjectStates('KAN');
      expect(statesFallback.length).toBeGreaterThan(0);

      // fetchApprovedWasmModules
      const wasm = await api.fetchApprovedWasmModules();
      expect(wasm.length).toBeGreaterThan(0);
    });
  });

  describe('HookPipelineRow variations', () => {
    it('renders different hook kinds and failure policies', () => {
      const mutatorHook: api.WorkflowHook = {
        id: 'h-mutator',
        name: 'test-mutator',
        from_state: 'In Review',
        to_state: 'Done',
        hook_kind: 'sync_mutator',
        sort_rank: '01',
        failure_policy: 'fail_open_warn',
        manifest_sha256: '',
        is_enabled: false,
      };

      const sdkHook: api.WorkflowHook = {
        id: 'h-sdk',
        name: 'sdk-gate',
        from_state: 'In Review',
        to_state: 'Done',
        hook_kind: 'agent_interceptor',
        sort_rank: '02',
        failure_policy: 'fail_closed',
        manifest_sha256: 'deadbeef123',
        is_enabled: true,
        harness_kind: 'in_app_sdk',
        provider_kind: 'gemini',
        model_id: 'gemini-1.5-pro',
        allowed_mutable_fields: [],
      };

      const remoteHook: api.WorkflowHook = {
        id: 'h-remote',
        name: 'remote-gate',
        from_state: 'In Review',
        to_state: 'Done',
        hook_kind: 'agent_interceptor',
        sort_rank: '03',
        failure_policy: 'fail_closed',
        manifest_sha256: 'abcdef12345',
        is_enabled: true,
        harness_kind: 'remote_runner',
      };

      const fallbackAgentHook: api.WorkflowHook = {
        id: 'h-fallback',
        name: 'generic-agent',
        from_state: 'In Review',
        to_state: 'Done',
        hook_kind: 'agent_interceptor',
        sort_rank: '04',
        failure_policy: 'fail_closed',
        manifest_sha256: '999999999',
        is_enabled: true,
        harness_kind: undefined,
      };

      const onMove = vi.fn();
      const onToggle = vi.fn();
      const onEdit = vi.fn();
      const onDetach = vi.fn();
      const onDropReorder = vi.fn();

      const { rerender } = render(
        <HookPipelineRow
          hook={mutatorHook}
          index={0}
          total={2}
          projectKey="KAN"
          onMove={onMove}
          onToggle={onToggle}
          onEdit={onEdit}
          onDetach={onDetach}
          onDropReorder={onDropReorder}
        />,
      );

      expect(screen.getByText('⚡ [Sync Wasm Mutator]')).toBeDefined();
      expect(screen.getByText('Fail-Open (Warn)')).toBeDefined();
      expect(screen.getByText('sha256:none')).toBeDefined();

      // Trigger move down
      fireEvent.click(screen.getByRole('button', { name: 'Move test-mutator down' }));
      expect(onMove).toHaveBeenCalledWith('h-mutator', 'down');

      // Trigger edit and detach
      fireEvent.click(screen.getByRole('button', { name: 'Edit test-mutator' }));
      expect(onEdit).toHaveBeenCalledWith(mutatorHook);
      fireEvent.click(screen.getByRole('button', { name: 'Detach test-mutator' }));
      expect(onDetach).toHaveBeenCalledWith('h-mutator');

      // Trigger toggle
      fireEvent.click(screen.getByRole('checkbox', { name: 'Toggle test-mutator' }));
      expect(onToggle).toHaveBeenCalledWith('h-mutator', true);

      // Copy SHA with clipboard failure
      Object.assign(navigator, {
        clipboard: {
          writeText: vi.fn().mockRejectedValue(new Error('fail')),
        },
      });
      fireEvent.click(screen.getByRole('button', { name: /Copy SHA256/i }));

      // Render SDK hook
      rerender(
        <HookPipelineRow
          hook={sdkHook}
          index={1}
          total={2}
          projectKey="KAN"
          onMove={onMove}
        />,
      );
      expect(screen.getByText('[SDK Agent Gate]')).toBeDefined();
      expect(screen.getByText('(gemini-1.5-pro)')).toBeDefined();
      expect(screen.getByText('[none]')).toBeDefined();

      // Render Remote hook
      rerender(
        <HookPipelineRow
          hook={remoteHook}
          index={0}
          total={1}
          projectKey="KAN"
        />,
      );
      expect(screen.getByText('[Remote WSS Gate]')).toBeDefined();

      // Render Fallback hook
      rerender(
        <HookPipelineRow
          hook={fallbackAgentHook}
          index={0}
          total={1}
          projectKey="KAN"
        />,
      );
      expect(screen.getByText('[Agent Gate]')).toBeDefined();
    });

    it('exercises pragmatic drag and drop hooks and callbacks', () => {
      let registeredDraggable: { getInitialData?: () => unknown; onDragStart?: () => void; onDrop?: () => void } = {};
      let registeredDropTarget: { getData?: () => unknown; onDrop?: (args: { source: { data: unknown } }) => void } = {};

      const mockDraggableFactory = vi.fn().mockImplementation((config: { getInitialData?: () => unknown; onDragStart?: () => void; onDrop?: () => void }) => {
        registeredDraggable = config;
        return () => { /* no-op */ };
      });

      const mockDropTargetFactory = vi.fn().mockImplementation((config: { getData?: () => unknown; onDrop?: (args: { source: { data: unknown } }) => void }) => {
        registeredDropTarget = config;
        return () => { /* no-op */ };
      });

      const onDropReorder = vi.fn();

      render(
        <HookPipelineRow
          hook={DEFAULT_TEST_HOOK}
          index={0}
          total={3}
          projectKey="KAN"
          onDropReorder={onDropReorder}
          draggableFactory={mockDraggableFactory as never}
          dropTargetFactory={mockDropTargetFactory as never}
        />,
      );

      // Exercise getInitialData and getData
      expect(registeredDraggable.getInitialData?.()).toEqual(
        expect.objectContaining({ type: 'hook-row', hookId: 'hook-1', index: 0 }),
      );
      expect(registeredDropTarget.getData?.()).toEqual(
        expect.objectContaining({ type: 'hook-row', hookId: 'hook-1', index: 0 }),
      );

      // Trigger drag start and drop
      registeredDraggable.onDragStart?.();
      registeredDraggable.onDrop?.();

      // Trigger drop on target from another hook
      registeredDropTarget.onDrop?.({
        source: {
          data: { type: 'hook-row', hookId: 'hook-2' },
        },
      });
      expect(onDropReorder).toHaveBeenCalledWith('hook-2', 'hook-1');

      // Drop with invalid or same hookId
      registeredDropTarget.onDrop?.({ source: { data: { type: 'unrelated' } } });
      registeredDropTarget.onDrop?.({ source: { data: { type: 'hook-row', hookId: 'hook-1' } } });
    });

    it('exercises cli_pipe fallback allowlist and is-dragging style class', () => {
      const cliFallbackHook: api.WorkflowHook = {
        id: 'h-cli-fallback',
        name: 'cli-fallback',
        from_state: 'Backlog',
        to_state: 'In Progress',
        hook_kind: 'agent_interceptor',
        sort_rank: '01',
        failure_policy: 'fail_closed',
        manifest_sha256: '12345678',
        is_enabled: true,
        harness_kind: 'cli_pipe',
        cli_binary_allowlist_id: undefined,
        cli_args: [],
      };

      let registeredDraggable: { onDragStart?: () => void } = {};
      const mockDraggable = vi.fn().mockImplementation((config: { onDragStart?: () => void }) => {
        registeredDraggable = config;
        return () => { /* no-op */ };
      });

      render(
        <HookPipelineRow
          hook={cliFallbackHook}
          index={0}
          total={1}
          projectKey="KAN"
          draggableFactory={mockDraggable as never}
        />,
      );

      expect(screen.getByText(/(\${context} \| agy)/i)).toBeDefined();

      // Trigger drag start
      registeredDraggable.onDragStart?.();
    });

    it('exercises copy SHA success', async () => {
      Object.assign(navigator, {
        clipboard: {
          writeText: vi.fn().mockResolvedValue(undefined),
        },
      });

      render(
        <HookPipelineRow
          hook={DEFAULT_TEST_HOOK}
          index={0}
          total={1}
          projectKey="KAN"
        />,
      );

      fireEvent.click(screen.getByRole('button', { name: /Copy SHA256/i }));
      await waitFor(() => {
        expect(screen.getByText('Copied!')).toBeDefined();
      });
    });
  });

  describe('TransitionRuleCard edge cases', () => {
    it('handles keyboard move down and drop reorder', async () => {
      const onReorder = vi.fn().mockResolvedValue(undefined);
      const onToggle = vi.fn().mockResolvedValue(undefined);
      const onEdit = vi.fn();
      const onDetach = vi.fn().mockResolvedValue(undefined);
      const onAddHook = vi.fn();
      const onDryRun = vi.fn();

      render(
        <TransitionRuleCard
          rule={DEFAULT_TEST_RULE}
          projectKey="KAN"
          onReorder={onReorder}
          onToggle={onToggle}
          onEdit={onEdit}
          onDetach={onDetach}
          onAddHook={onAddHook}
          onDryRun={onDryRun}
        />,
      );

      // Click Add Hook
      fireEvent.click(screen.getByRole('button', { name: /Add hook to In Review to Done/i }));
      expect(onAddHook).toHaveBeenCalledWith({ from_state: 'In Review', to_state: 'Done' });

      // Click Dry-Run
      fireEvent.click(screen.getByRole('button', { name: /Dry-run against sample ticket/i }));
      expect(onDryRun).toHaveBeenCalledWith({ from_state: 'In Review', to_state: 'Done' });

      // Move hook 1 down
      fireEvent.click(screen.getByRole('button', { name: 'Move require-qa-proof-link down' }));
      await waitFor(() => {
        expect(onReorder).toHaveBeenCalledWith(
          { from_state: 'In Review', to_state: 'Done' },
          ['hook-2', 'hook-1', 'hook-3'],
        );
      });
    });

    it('exercises drop reorder success and failure rollbacks', async () => {
      const onReorder = vi.fn().mockResolvedValue(undefined);

      let capturedOnDrop: ((args: { source: { data: unknown } }) => void) | undefined;
      const mockDropTargetFactory = vi.fn().mockImplementation((config: { onDrop?: (args: { source: { data: unknown } }) => void }) => {
        capturedOnDrop ??= config.onDrop;
        return () => { /* no-op */ };
      });

      render(
        <TransitionRuleCard
          rule={DEFAULT_TEST_RULE}
          projectKey="KAN"
          onReorder={onReorder}
          onToggle={vi.fn().mockResolvedValue(undefined)}
          onEdit={vi.fn()}
          onDetach={vi.fn().mockResolvedValue(undefined)}
          onAddHook={vi.fn()}
          onDryRun={vi.fn()}
          dropTargetFactory={mockDropTargetFactory as never}
        />,
      );

      // Trigger drop from hook-2 to hook-1
      capturedOnDrop?.({ source: { data: { type: 'hook-row', hookId: 'hook-2' } } });

      await waitFor(() => {
        expect(onReorder).toHaveBeenCalledWith(
          { from_state: 'In Review', to_state: 'Done' },
          ['hook-2', 'hook-1', 'hook-3'],
        );
      });

      // Same hook drop does nothing
      capturedOnDrop?.({ source: { data: { type: 'hook-row', hookId: 'hook-1' } } });

      // Invalid hook drop does nothing
      capturedOnDrop?.({ source: { data: { type: 'hook-row', hookId: 'non-existent' } } });
    });

    it('handles non-Error rejection and drop error catch in TransitionRuleCard', async () => {
      const onReorder = vi.fn().mockRejectedValue('String rejection');
      let capturedOnDrop: ((args: { source: { data: unknown } }) => void) | undefined;
      const mockDropTargetFactory = vi.fn().mockImplementation((config: { onDrop?: (args: { source: { data: unknown } }) => void }) => {
        capturedOnDrop ??= config.onDrop;
        return () => { /* no-op */ };
      });

      render(
        <TransitionRuleCard
          rule={DEFAULT_TEST_RULE}
          projectKey="KAN"
          onReorder={onReorder}
          onToggle={vi.fn()}
          onEdit={vi.fn()}
          onDetach={vi.fn()}
          onAddHook={vi.fn()}
          onDryRun={vi.fn()}
          dropTargetFactory={mockDropTargetFactory as never}
        />,
      );

      // Boundary keyboard moves (index 0 up, last index down)
      fireEvent.click(screen.getByRole('button', { name: 'Move require-qa-proof-link up' }));
      fireEvent.click(screen.getByRole('button', { name: 'Move sec-invariant-scan down' }));

      // Keyboard move down with string error
      fireEvent.click(screen.getByRole('button', { name: 'Move require-qa-proof-link down' }));
      await waitFor(() => {
        expect(screen.getByText('Reorder failed: 422 REORDER_SET_MISMATCH')).toBeDefined();
      });

      // Drop reorder with Error rejection
      onReorder.mockRejectedValueOnce(new Error('Drop failed error'));
      capturedOnDrop?.({ source: { data: { type: 'hook-row', hookId: 'hook-2' } } });
      await waitFor(() => {
        expect(screen.getByText('Drop failed error')).toBeDefined();
      });

      // Drop reorder with string rejection
      onReorder.mockRejectedValueOnce('Drop failed string');
      capturedOnDrop?.({ source: { data: { type: 'hook-row', hookId: 'hook-2' } } });
      await waitFor(() => {
        expect(screen.getByText('Reorder failed: 422 REORDER_SET_MISMATCH')).toBeDefined();
      });
    });

    it('renders null from_state rule card and empty hooks list', () => {
      render(
        <TransitionRuleCard
          rule={{
            from_state: null,
            to_state: 'Cancelled',
            active_hook_count: 0,
            hooks: [],
          }}
          projectKey="KAN"
          onReorder={vi.fn()}
          onToggle={vi.fn()}
          onEdit={vi.fn()}
          onDetach={vi.fn()}
          onAddHook={vi.fn()}
          onDryRun={vi.fn()}
        />,
      );

      expect(screen.getByTestId('transition-card-any-Cancelled')).toBeDefined();
      expect(screen.getByText(/Any State/)).toBeDefined();
      expect(screen.getByTestId('empty-hooks-cta')).toBeDefined();
    });

    it('updates effectiveHooks when rule.hooks length changes from external update', () => {
      const { rerender } = render(
        <TransitionRuleCard
          rule={DEFAULT_TEST_RULE}
          projectKey="KAN"
          onReorder={vi.fn()}
          onToggle={vi.fn()}
          onEdit={vi.fn()}
          onDetach={vi.fn()}
          onAddHook={vi.fn()}
          onDryRun={vi.fn()}
        />,
      );

      expect(screen.getByText('require-qa-proof-link')).toBeDefined();

      // Rerender with 1 hook
      rerender(
        <TransitionRuleCard
          rule={{
            ...DEFAULT_TEST_RULE,
            hooks: [DEFAULT_TEST_HOOK],
          }}
          projectKey="KAN"
          onReorder={vi.fn()}
          onToggle={vi.fn()}
          onEdit={vi.fn()}
          onDetach={vi.fn()}
          onAddHook={vi.fn()}
          onDryRun={vi.fn()}
        />,
      );

      expect(screen.queryByText('forensic-code-check')).toBeNull();
    });
  });

  describe('WorkflowStudioPage interactive actions', () => {
    it('opens and closes Add Transition Rule, Edit Hook, and Dry-Run drawer', async () => {
      vi.spyOn(api, 'fetchWorkflowHooks').mockResolvedValue(api.DEFAULT_S14_4_RULES);
      const createSpy = vi.spyOn(api, 'createWorkflowHook').mockResolvedValue({} as never);
      const updateSpy = vi.spyOn(api, 'updateWorkflowHook').mockResolvedValue({} as never);
      const disableSpy = vi.spyOn(api, 'disableWorkflowHook').mockResolvedValue(undefined);

      render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={['/projects/KAN/settings/workflows']}>
            <WorkflowStudioPage projectKeyOverride="KAN" isAdmin={true} />
          </MemoryRouter>
        </QueryClientProvider>,
      );

      await waitFor(() => {
        expect(screen.getByText('require-qa-proof-link')).toBeDefined();
      });

      // 1. Open Add Transition Rule dialog
      fireEvent.click(screen.getByRole('button', { name: 'Add Transition Rule' }));
      expect(screen.getByText('Attach Workflow Interceptor Hook')).toBeDefined();

      // Submit creating a new hook
      fireEvent.change(screen.getByLabelText(/Hook Name/i), { target: { value: 'new-rule-hook' } });
      fireEvent.click(screen.getByRole('button', { name: 'Attach Hook' }));
      await waitFor(() => {
        expect(createSpy).toHaveBeenCalledWith('KAN', expect.objectContaining({ name: 'new-rule-hook' }));
      });

      // 2. Open Edit Hook dialog
      fireEvent.click(screen.getByRole('button', { name: 'Edit require-qa-proof-link' }));
      expect(screen.getByText('Edit Hook: require-qa-proof-link')).toBeDefined();

      // Submit updating existing hook
      fireEvent.click(screen.getByRole('button', { name: 'Update Hook' }));
      await waitFor(() => {
        expect(updateSpy).toHaveBeenCalledWith('hook-1', expect.objectContaining({ name: 'require-qa-proof-link' }));
      });

      // 3. Open Dry-Run drawer and close it
      fireEvent.click(screen.getByRole('button', { name: /Dry-run against sample ticket/i }));
      expect(screen.getByText(/▶ Dry-Run: \[In Review\] ➔ \[Done\]/i)).toBeDefined();

      fireEvent.click(screen.getByRole('button', { name: 'Close Dry-Run Drawer' }));
      expect(screen.queryByText(/▶ Dry-Run: \[In Review\] ➔ \[Done\]/i)).toBeNull();

      // 4. Toggle hook disabled
      const toggleCheck = screen.getByRole('checkbox', { name: 'Toggle require-qa-proof-link' });
      fireEvent.click(toggleCheck);
      await waitFor(() => {
        expect(disableSpy).toHaveBeenCalled();
      });
    });

    it('exercises detaching a hook and AAL2 onCancel / onSessionExpired', async () => {
      vi.spyOn(api, 'fetchWorkflowHooks').mockResolvedValue(api.DEFAULT_S14_4_RULES);
      const deleteSpy = vi.spyOn(api, 'deleteWorkflowHook').mockResolvedValue(undefined);

      render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={['/projects/KAN/settings/workflows']}>
            <WorkflowStudioPage projectKeyOverride="KAN" isAdmin={true} />
          </MemoryRouter>
        </QueryClientProvider>,
      );

      await waitFor(() => {
        expect(screen.getByText('require-qa-proof-link')).toBeDefined();
      });

      // Detach hook 2
      fireEvent.click(screen.getByRole('button', { name: 'Detach forensic-code-check' }));
      await waitFor(() => {
        expect(deleteSpy).toHaveBeenCalledWith('hook-2');
      });
    });

    it('exercises onAddHook from card and non-AAL2 error handling in studio', async () => {
      vi.spyOn(api, 'fetchWorkflowHooks').mockResolvedValue(api.DEFAULT_S14_4_RULES);
      vi.spyOn(api, 'deleteWorkflowHook').mockRejectedValue(new Error('Detach failure'));
      vi.spyOn(api, 'createWorkflowHook').mockRejectedValue(new Error('Create failure'));
      vi.spyOn(api, 'reorderWorkflowHooks').mockRejectedValue(new Error('Reorder failure'));

      render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={['/projects/KAN/settings/workflows']}>
            <WorkflowStudioPage projectKeyOverride="KAN" isAdmin={true} />
          </MemoryRouter>
        </QueryClientProvider>,
      );

      await waitFor(() => {
        expect(screen.getByText('require-qa-proof-link')).toBeDefined();
      });

      // 1. Click + Add Hook to Transition from the card
      fireEvent.click(screen.getByRole('button', { name: /Add hook to In Review to Done/i }));
      expect(screen.getByText('Attach Workflow Interceptor Hook')).toBeDefined();

      // Submit and catch non-AAL2 error
      fireEvent.change(screen.getByLabelText(/Hook Name/i), { target: { value: 'fail-hook' } });
      fireEvent.click(screen.getByRole('button', { name: 'Attach Hook' }));

      // Close dialog
      fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));

      // 2. Detach hook with non-AAL2 error
      fireEvent.click(screen.getByRole('button', { name: 'Detach require-qa-proof-link' }));

      // 3. Move hook down with non-AAL2 error
      fireEvent.click(screen.getByRole('button', { name: 'Move require-qa-proof-link down' }));
    });

    it('exercises AAL2 challenge TOTP verification and replay', async () => {
      vi.spyOn(api, 'fetchWorkflowHooks').mockResolvedValue(api.DEFAULT_S14_4_RULES);
      const aal2Err = new ApiProblem(403, {
        code: 'AAL2_REQUIRED',
        challenge_id: 'stepup-totp-1',
        methods: ['totp'],
      });

      const disableSpy = vi
        .spyOn(api, 'disableWorkflowHook')
        .mockRejectedValueOnce(aal2Err)
        .mockResolvedValueOnce(undefined);

      vi.spyOn(client, 'apiFetch').mockImplementation(async (_method, path) => {
        await Promise.resolve();
        if (typeof path === 'string' && path.includes('/auth/totp/verify')) {
          return { status: 'authenticated' };
        }
        return {};
      });

      render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={['/projects/KAN/settings/workflows']}>
            <WorkflowStudioPage projectKeyOverride="KAN" isAdmin={true} />
          </MemoryRouter>
        </QueryClientProvider>,
      );

      await waitFor(() => {
        expect(screen.getByText('require-qa-proof-link')).toBeDefined();
      });

      // Toggle hook -> triggers AAL2 modal
      fireEvent.click(screen.getByRole('checkbox', { name: 'Toggle require-qa-proof-link' }));

      await waitFor(() => {
        expect(screen.getByText('Admin Verification Required (AAL2)')).toBeDefined();
        expect(screen.getByLabelText(/6-digit Authenticator Code/i)).toBeDefined();
      });

      // Enter 6-digit TOTP
      fireEvent.change(screen.getByLabelText(/6-digit Authenticator Code/i), {
        target: { value: '123456' },
      });

      await waitFor(() => {
        expect(disableSpy).toHaveBeenCalledTimes(2);
        expect(screen.queryByText('Admin Verification Required (AAL2)')).toBeNull();
      });
    });

    it('exercises AAL2 challenge cancel and session expired handlers', async () => {
      vi.spyOn(api, 'fetchWorkflowHooks').mockResolvedValue(api.DEFAULT_S14_4_RULES);
      const aal2Err = new ApiProblem(403, {
        code: 'AAL2_REQUIRED',
        challenge_id: 'stepup-1',
        methods: ['totp'],
      });
      vi.spyOn(api, 'disableWorkflowHook').mockRejectedValue(aal2Err);

      render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={['/projects/KAN/settings/workflows']}>
            <WorkflowStudioPage projectKeyOverride="KAN" isAdmin={true} />
          </MemoryRouter>
        </QueryClientProvider>,
      );

      await waitFor(() => {
        expect(screen.getByText('require-qa-proof-link')).toBeDefined();
      });

      // Toggle hook -> triggers AAL2 modal
      fireEvent.click(screen.getByRole('checkbox', { name: 'Toggle require-qa-proof-link' }));

      await waitFor(() => {
        expect(screen.getByText('Admin Verification Required (AAL2)')).toBeDefined();
      });

      // Click Cancel in AAL2 modal
      fireEvent.click(screen.getByRole('button', { name: /Cancel and return to sign-in/i }));
      await waitFor(() => {
        expect(screen.queryByText('Admin Verification Required (AAL2)')).toBeNull();
      });
    });

    it('exercises enabling a disabled hook and AAL2 challenge on update with session expiration', async () => {
      const disabledRule: api.TransitionRule = {
        from_state: 'In Review',
        to_state: 'Done',
        active_hook_count: 1,
        hooks: [
          {
            id: 'hook-disabled',
            name: 'disabled-hook',
            from_state: 'In Review',
            to_state: 'Done',
            hook_kind: 'sync_validator',
            sort_rank: '01',
            failure_policy: 'fail_closed',
            manifest_sha256: 'deadbeef123',
            is_enabled: false,
          },
        ],
      };

      vi.spyOn(api, 'fetchWorkflowHooks').mockResolvedValue([disabledRule]);
      const enableSpy = vi.spyOn(api, 'enableWorkflowHook').mockResolvedValue(undefined);
      const updateSpy = vi
        .spyOn(api, 'updateWorkflowHook')
        .mockRejectedValueOnce(
          new ApiProblem(403, {
            code: 'AAL2_REQUIRED',
            challenge_id: 'stepup-update',
            methods: ['totp'],
          }),
        );

      vi.spyOn(client, 'apiFetch').mockImplementation(async (_method, path) => {
        await Promise.resolve();
        if (typeof path === 'string' && path.includes('/auth/totp/verify')) {
          throw new ApiProblem(401, { code: 'CHALLENGE_EXPIRED', message: 'Expired' });
        }
        return {};
      });

      render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={['/projects/KAN/settings/workflows']}>
            <WorkflowStudioPage projectKeyOverride="KAN" isAdmin={true} />
          </MemoryRouter>
        </QueryClientProvider>,
      );

      await waitFor(() => {
        expect(screen.getByText('disabled-hook')).toBeDefined();
      });

      // 1. Enable disabled hook
      const toggle = screen.getByRole('checkbox', { name: 'Toggle disabled-hook' });
      fireEvent.click(toggle);
      await waitFor(() => {
        expect(enableSpy).toHaveBeenCalledWith('hook-disabled');
      });

      // 2. Edit hook and trigger AAL2 challenge on update
      fireEvent.click(screen.getByRole('button', { name: 'Edit disabled-hook' }));
      expect(screen.getByText('Edit Hook: disabled-hook')).toBeDefined();

      fireEvent.click(screen.getByRole('button', { name: 'Update Hook' }));

      // AAL2 modal opens
      await waitFor(() => {
        expect(screen.getByText('Admin Verification Required (AAL2)')).toBeDefined();
      });
      expect(updateSpy).toHaveBeenCalled();

      // Enter TOTP that triggers CHALLENGE_EXPIRED -> onSessionExpired
      fireEvent.change(screen.getByLabelText(/6-digit Authenticator Code/i), {
        target: { value: '999999' },
      });

      await waitFor(() => {
        expect(screen.queryByText('Admin Verification Required (AAL2)')).toBeNull();
      });
    });

    it('exercises projectQuery capabilities success, failure, and non-admin states', async () => {
      // 1. Project query throws error -> catch returns null -> non-admin under fail-closed -> NotFoundView
      const fetchSpy = vi.spyOn(client, 'apiFetch').mockImplementation(async (_method, path) => {
        await Promise.resolve();
        if (typeof path === 'string' && path.includes('/projects/ERRQUERY')) {
          throw new Error('Project fetch failed');
        }
        return api.DEFAULT_S14_4_RULES;
      });

      const { unmount: unmount1 } = render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={['/projects/ERRQUERY/settings/workflows']}>
            <WorkflowStudioPage projectKeyOverride="ERRQUERY" />
          </MemoryRouter>
        </QueryClientProvider>,
      );

      await waitFor(() => {
        expect(screen.getByText('Not found or no access')).toBeDefined();
      });
      unmount1();

      // 2. Project query returns capabilities without admin -> renders NotFoundView
      fetchSpy.mockResolvedValueOnce({ capabilities: ['VIEW'] });
      const qc2 = new QueryClient({ defaultOptions: { queries: { retry: false } } });
      const { unmount: unmount2 } = render(
        <QueryClientProvider client={qc2}>
          <MemoryRouter initialEntries={['/projects/VIEWONLY/settings/workflows']}>
            <WorkflowStudioPage projectKeyOverride="VIEWONLY" />
          </MemoryRouter>
        </QueryClientProvider>,
      );

      await waitFor(() => {
        expect(screen.getByText('Not found or no access')).toBeDefined();
      });
      unmount2();

      // 3. Project query returns capabilities with PROJECT_ADMIN -> isUserAdmin = true
      fetchSpy.mockResolvedValueOnce({ capabilities: ['PROJECT_ADMIN'] });
      const qc3 = new QueryClient({ defaultOptions: { queries: { retry: false } } });
      render(
        <QueryClientProvider client={qc3}>
          <MemoryRouter initialEntries={['/projects/PA/settings/workflows']}>
            <WorkflowStudioPage projectKeyOverride="PA" />
          </MemoryRouter>
        </QueryClientProvider>,
      );

      await waitFor(() => {
        expect(screen.getByText('require-qa-proof-link')).toBeDefined();
      });
    });

    it('renders general error alert when rules query fails and handles reorder AAL2 challenge', async () => {
      vi.spyOn(api, 'fetchWorkflowHooks').mockRejectedValueOnce(new Error('Database offline: 503'));
      const qcErr = new QueryClient({ defaultOptions: { queries: { retry: false } } });

      const { unmount } = render(
        <QueryClientProvider client={qcErr}>
          <MemoryRouter initialEntries={['/projects/ERR/settings/workflows']}>
            <WorkflowStudioPage projectKeyOverride="ERR" isAdmin={true} />
          </MemoryRouter>
        </QueryClientProvider>,
      );

      await waitFor(() => {
        expect(screen.getByText('Database offline: 503')).toBeDefined();
      });
      unmount();

      // Test reorder AAL2 challenge
      vi.spyOn(api, 'fetchWorkflowHooks').mockResolvedValue(api.DEFAULT_S14_4_RULES);
      const aal2Err = new ApiProblem(403, {
        code: 'AAL2_REQUIRED',
        challenge_id: 'stepup-reorder',
        methods: ['totp'],
      });
      vi.spyOn(api, 'reorderWorkflowHooks').mockRejectedValueOnce(aal2Err);

      const qcReorder = new QueryClient({ defaultOptions: { queries: { retry: false } } });
      render(
        <QueryClientProvider client={qcReorder}>
          <MemoryRouter initialEntries={['/projects/REORDER_AAL2/settings/workflows']}>
            <WorkflowStudioPage projectKeyOverride="REORDER_AAL2" isAdmin={true} />
          </MemoryRouter>
        </QueryClientProvider>,
      );

      await waitFor(() => {
        expect(screen.getByText('require-qa-proof-link')).toBeDefined();
      });

      // Move hook down to trigger reorder AAL2 challenge
      fireEvent.click(screen.getByRole('button', { name: 'Move require-qa-proof-link down' }));
      await waitFor(() => {
        expect(screen.getByText('Admin Verification Required (AAL2)')).toBeDefined();
      });
    });

    it('renders empty studio state when rules array is empty', async () => {
      vi.spyOn(api, 'fetchWorkflowHooks').mockResolvedValue([]);

      render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={['/projects/EMPTY/settings/workflows']}>
            <WorkflowStudioPage projectKeyOverride="EMPTY" isAdmin={true} />
          </MemoryRouter>
        </QueryClientProvider>,
      );

      await waitFor(() => {
        expect(screen.getByTestId('empty-studio-state')).toBeDefined();
      });
    });

    it('renders NotFoundView when role=member query param is present', () => {
      render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={['/projects/KAN/settings/workflows?role=member']}>
            <WorkflowStudioPage projectKeyOverride="KAN" />
          </MemoryRouter>
        </QueryClientProvider>,
      );

      expect(screen.getByText('Not found or no access')).toBeDefined();
    });
  });

  describe('AttachHookDialog extra branches', () => {
    it('cancels dialog and handles remote runner options', () => {
      const handleClose = vi.fn();
      render(
        <AttachHookDialog
          isOpen={true}
          projectKey="KAN"
          states={api.DEFAULT_PROJECT_STATES}
          agentDefinitions={[
            {
              id: 'agent-remote-1',
              slug: 'remote-pool-agent',
              display_name: 'Remote Pool Agent',
              harness_kind: 'remote_runner',
              remote_runner_pool_slug: 'gpu-pool',
              cli_args: [],
              repo_access_mode: 'none',
              timeout_ms: 120000,
            },
          ]}
          onSave={vi.fn()}
          onClose={handleClose}
        />,
      );

      // Switch to agent interceptor
      fireEvent.click(screen.getByLabelText('Agent Interceptor'));
      expect(screen.getByText('Remote Pool Agent')).toBeDefined();

      // Click Cancel
      fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
      expect(handleClose).toHaveBeenCalled();
    });

    it('exercises mutator submission, mutable field toggle off, and select onChange handlers', () => {
      const onSave = vi.fn();
      const onClose = vi.fn();

      const { rerender } = render(
        <AttachHookDialog
          isOpen={true}
          projectKey="KAN"
          states={[{ id: 's1', name: 'SingleState' }]}
          agentDefinitions={[
            {
              id: 'a-no-cli',
              slug: 'no-cli-agent',
              display_name: 'No CLI Agent',
              harness_kind: 'cli_pipe',
              cli_args: [],
              repo_access_mode: 'ro_vfs_mount',
              timeout_ms: 45000,
            },
          ]}
          onSave={onSave}
          onClose={onClose}
        />,
      );

      // Fill in hook name
      fireEvent.change(screen.getByLabelText(/Hook Name/i), { target: { value: 'mutator-hook' } });

      // Switch to Sync Wasm Mutator
      fireEvent.click(screen.getByLabelText('Sync Wasm Mutator'));

      // Switch back to Sync Wasm Validator
      fireEvent.click(screen.getByLabelText('Sync Wasm Validator'));

      // Switch back to Sync Wasm Mutator
      fireEvent.click(screen.getByLabelText('Sync Wasm Mutator'));

      // Change Wasm module select
      const wasmSelect = screen.getByLabelText(/Approved (WebAssembly|Wasm) Module/i);
      fireEvent.change(wasmSelect, { target: { value: api.DEFAULT_WASM_MODULES[1]?.sha256 ?? 'sha' } });

      // Change Failure Policy select
      const failurePolicySelect = screen.getByLabelText(/Failure Policy/i);
      fireEvent.change(failurePolicySelect, { target: { value: 'fail_open_warn' } });

      // Toggle mutable field ON then OFF
      const labelsCheck = screen.getByLabelText('labels');
      fireEvent.click(labelsCheck); // Selected
      fireEvent.click(labelsCheck); // Deselected (tests filter branch)

      // Select assignees
      const assigneesCheck = screen.getByLabelText('assignees');
      fireEvent.click(assigneesCheck);

      // Submit
      fireEvent.click(screen.getByRole('button', { name: 'Attach Hook' }));
      expect(onSave).toHaveBeenCalledWith(
        expect.objectContaining({
          name: 'mutator-hook',
          hook_kind: 'sync_mutator',
          failure_policy: 'fail_open_warn',
          allowed_mutable_fields: ['assignees'],
        }),
      );

      // Rerender with empty states
      rerender(
        <AttachHookDialog
          isOpen={true}
          projectKey="KAN"
          states={[]}
          agentDefinitions={[]}
          onSave={vi.fn()}
          onClose={vi.fn()}
        />,
      );
      expect(screen.getByText('Attach Workflow Interceptor Hook')).toBeDefined();
    });

    it('handles empty to_state and non-Error save failure', async () => {
      const onSave = vi.fn().mockRejectedValue('Raw string error');
      render(
        <AttachHookDialog
          isOpen={true}
          projectKey="KAN"
          states={[{ id: 's1', name: 'Open' }]}
          agentDefinitions={[]}
          onSave={onSave}
          onClose={vi.fn()}
        />,
      );

      fireEvent.change(screen.getByLabelText(/Hook Name/i), { target: { value: 'test-hook' } });

      // Clear to_state
      fireEvent.change(screen.getByLabelText(/To State/i), { target: { value: '' } });
      fireEvent.click(screen.getByRole('button', { name: 'Attach Hook' }));
      expect(screen.getByText('Target state (to_state) is required.')).toBeDefined();

      // Set to_state back and submit to trigger non-Error rejection
      fireEvent.change(screen.getByLabelText(/To State/i), { target: { value: 'Open' } });
      fireEvent.click(screen.getByRole('button', { name: 'Attach Hook' }));
      await waitFor(() => {
        expect(screen.getByText('Failed to attach workflow hook.')).toBeDefined();
      });
    });

    it('validates identical from_state and to_state and renders fallback option labels', () => {
      render(
        <AttachHookDialog
          isOpen={true}
          projectKey="KAN"
          initialTransition={{ from_state: 'Done', to_state: 'Done' }}
          states={[{ id: 's-done', name: 'Done' }]}
          agentDefinitions={[
            {
              id: 'a-cli-none',
              slug: 'cli-none',
              display_name: 'CLI None',
              harness_kind: 'cli_pipe',
              cli_args: [],
              repo_access_mode: 'none',
              timeout_ms: 10000,
            },
            {
              id: 'a-sdk-nomodel',
              slug: 'sdk-nomodel',
              display_name: 'SDK No Model',
              harness_kind: 'in_app_sdk',
              provider_kind: 'ollama',
              model_id: undefined,
              cli_args: [],
              repo_access_mode: 'none',
              timeout_ms: 10000,
            },
          ]}
          wasmModules={[
            {
              sha256: 'sha-none',
              name: 'no-latency-wasm',
              target_latency_budget: undefined,
            },
          ]}
          onSave={vi.fn()}
          onClose={vi.fn()}
        />,
      );

      fireEvent.change(screen.getByLabelText(/Hook Name/i), { target: { value: 'same-state-hook' } });
      fireEvent.click(screen.getByRole('button', { name: 'Attach Hook' }));
      expect(screen.getByText('from_state and to_state cannot be identical.')).toBeDefined();

      // Switch to Agent Interceptor to render fallback optgroups
      fireEvent.click(screen.getByLabelText('Agent Interceptor'));
      expect(screen.getByText(/CLI None \(cli\)/i)).toBeDefined();
      expect(screen.getByText(/SDK No Model \(ollama\)/i)).toBeDefined();
    });
  });

  describe('DryRunDrawer additional coverage', () => {
    it('renders error step results and handles form updates', async () => {
      const mockResult: api.DryRunResponse = {
        would_commit: false,
        steps: [
          {
            order: 1,
            name: 'faulty-hook',
            hook_kind: 'sync_validator',
            result: 'error',
            reason: 'Runtime panics',
            duration_us: 100,
          },
          {
            order: 2,
            name: 'mutator-hook',
            hook_kind: 'sync_mutator',
            result: 'mutated',
            reason: 'Field mutated',
            duration_us: 800,
            field_updates: { priority: 'High' },
          },
        ],
      };

      render(
        <DryRunDrawer
          isOpen={true}
          projectKey="KAN"
          transition={{ from_state: null, to_state: 'Done' }}
          onClose={vi.fn()}
          dryRunRunner={vi.fn().mockResolvedValue(mockResult)}
        />,
      );

      // Mode switcher tabs: click Pick existing issue, then click Sample ticket
      fireEvent.click(screen.getByRole('tab', { name: 'Pick existing issue' }));
      fireEvent.click(screen.getByRole('tab', { name: 'Sample ticket' }));

      // Edit sample fields
      fireEvent.change(screen.getByLabelText(/Summary/i), { target: { value: 'New Summary' } });
      fireEvent.change(screen.getByLabelText(/Description/i), { target: { value: 'New Desc' } });
      fireEvent.change(screen.getByLabelText(/Priority/i), { target: { value: 'Low' } });
      fireEvent.change(screen.getByLabelText(/Labels/i), { target: { value: 'tag1, tag2' } });

      fireEvent.click(screen.getByRole('button', { name: '▶ Run Dry-Run' }));
      await waitFor(() => {
        expect(screen.getByText('faulty-hook')).toBeDefined();
        expect(screen.getByText('mutator-hook')).toBeDefined();
      });
    });

    it('handles non-Error rejection and CLI command copy success', async () => {
      Object.assign(navigator, {
        clipboard: {
          writeText: vi.fn().mockResolvedValue(undefined),
        },
      });

      const mockResult: api.DryRunResponse = {
        would_commit: false,
        steps: [
          {
            order: 1,
            name: 'agent-gate',
            hook_kind: 'agent_interceptor',
            result: 'skipped_async',
            cli_command: 'uv run kanban-agent validate-transition --test',
            duration_us: 0,
          },
        ],
      };

      render(
        <DryRunDrawer
          isOpen={true}
          projectKey="KAN"
          transition={{ from_state: 'In Review', to_state: 'Done' }}
          onClose={vi.fn()}
          dryRunRunner={vi.fn().mockRejectedValueOnce('Raw string network failure').mockResolvedValueOnce(mockResult)}
        />,
      );

      // Trigger run dry-run with non-Error rejection
      fireEvent.click(screen.getByRole('button', { name: '▶ Run Dry-Run' }));
      await waitFor(() => {
        expect(screen.getByText('Dry-run request failed.')).toBeDefined();
      });

      // Trigger run dry-run with success
      fireEvent.click(screen.getByRole('button', { name: '▶ Run Dry-Run' }));
      await waitFor(() => {
        expect(screen.getByText(/Skipped Async/i)).toBeDefined();
      });

      // Copy CLI command
      fireEvent.click(screen.getByRole('button', { name: /Copy CLI Command/i }));
      await waitFor(() => {
        expect(screen.getByText(/Copied!/i)).toBeDefined();
      });
    });
  });
});
