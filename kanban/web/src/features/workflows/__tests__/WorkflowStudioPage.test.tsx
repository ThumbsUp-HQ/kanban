// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import React from 'react';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router';
import { WorkflowStudioPage } from '../WorkflowStudioPage';
import { AttachHookDialog } from '../AttachHookDialog';
import { CustomFieldDefinitionEditor } from '../../custom-fields/CustomFieldDefinitionEditor';
import * as api from '../api';
import { Aal2StepUpCancelledError } from '../../../api/client';

describe('WorkflowStudioPage (KB-P5-24, S14.4)', () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false, staleTime: Infinity },
      },
    });
    vi.restoreAllMocks();
  });

  function renderPage(
    props: { isAdmin?: boolean; projectKey?: string; initialEntries?: string[] } = {},
  ) {
    return render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter
          initialEntries={
            props.initialEntries ?? [`/projects/${props.projectKey ?? 'KAN'}/settings/workflows`]
          }
        >
          <WorkflowStudioPage
            projectKeyOverride={props.projectKey ?? 'KAN'}
            isAdmin={props.isAdmin ?? true}
          />
        </MemoryRouter>
      </QueryClientProvider>,
    );
  }

  it('renders In Review -> Done card with the 3 S14.4 hooks matching wireframe (Mandatory Test Case 1)', async () => {
    vi.spyOn(api, 'fetchWorkflowHooks').mockResolvedValue(api.DEFAULT_S14_4_RULES);

    renderPage();

    // Verify header
    await waitFor(() => {
      expect(screen.getByText(/Scripted Workflows & Transition Helpers/i)).toBeDefined();
      expect(screen.getByText('KAN')).toBeDefined();
    });

    // Verify top arrow bar
    expect(screen.getByTestId('active-hooks-count').textContent).toContain('3 Active Hooks');
    expect(screen.getByText(/In Review/i)).toBeDefined();
    expect(screen.getByText(/Done/i)).toBeDefined();

    // Verify 3 hooks in order
    expect(screen.getByText('require-qa-proof-link')).toBeDefined();
    expect(screen.getByText('forensic-code-check')).toBeDefined();
    expect(screen.getByText('sec-invariant-scan')).toBeDefined();

    // Verify sync hook details
    expect(screen.getByText('⚡ [Sync Wasm Validator]')).toBeDefined();
    expect(screen.getByTestId('hook-latency-hook-1').textContent).toContain('<2ms');

    // Verify agent hook details
    expect(screen.getByText('(${context} | agy -p)')).toBeDefined();
    expect(screen.getByText('(ollama/qwen2.5-coder)')).toBeDefined();
    expect(screen.getAllByText('kanban-main')[0]).toBeDefined();
    expect(screen.getAllByText(/\(:ro mount\)/i)[0]).toBeDefined();
    expect(screen.getByText('[labels]')).toBeDefined();

    // Verify popover details for agent
    const emojiPill = screen.getByTestId('emoji-hint-hook-2');
    expect(emojiPill).toBeDefined();
    fireEvent.click(emojiPill);

    await waitFor(() => {
      expect(screen.getByTestId('emoji-hint-hook-2-popup')).toBeDefined();
      expect(screen.getByText(/Harness: cli_pipe/i)).toBeDefined();
    });
  });

  it('reorders hooks with keyboard Move up and toggles enabled state (Mandatory Test Case 2)', async () => {
    vi.spyOn(api, 'fetchWorkflowHooks').mockResolvedValue(api.DEFAULT_S14_4_RULES);
    const reorderSpy = vi.spyOn(api, 'reorderWorkflowHooks').mockResolvedValue(undefined);
    const disableSpy = vi.spyOn(api, 'disableWorkflowHook').mockResolvedValue(undefined);

    renderPage();

    await waitFor(() => {
      expect(screen.getByText('forensic-code-check')).toBeDefined();
    });

    // Move hook 2 (forensic-code-check) up
    const moveUpBtn = screen.getByRole('button', { name: 'Move forensic-code-check up' });
    fireEvent.click(moveUpBtn);

    await waitFor(() => {
      expect(reorderSpy).toHaveBeenCalledWith(
        'KAN',
        expect.objectContaining({
          transition: { from_state: 'In Review', to_state: 'Done' },
          ordered_hook_ids: ['hook-2', 'hook-1', 'hook-3'],
        }),
      );
    });

    // Toggle hook 1 disabled
    const toggleSwitch = screen.getByRole('checkbox', { name: 'Toggle require-qa-proof-link' });
    fireEvent.click(toggleSwitch);

    await waitFor(() => {
      expect(disableSpy).toHaveBeenCalledWith('hook-1');
    });
  });

  it('renders uniform Not found or no access for non-admin user with 0 write calls (Mandatory Test Case 5)', async () => {
    const createSpy = vi.spyOn(api, 'createWorkflowHook');
    const reorderSpy = vi.spyOn(api, 'reorderWorkflowHooks');

    renderPage({ isAdmin: false });

    await waitFor(() => {
      expect(screen.getByText('Not found or no access')).toBeDefined();
    });

    expect(screen.queryByText(/Scripted Workflows & Transition Helpers/i)).toBeNull();
    expect(createSpy).not.toHaveBeenCalled();
    expect(reorderSpy).not.toHaveBeenCalled();
  });

  it('safely escapes hostile hook names and rejection reasons without script injection (Mandatory Test Case 5)', async () => {
    const hostileRules: api.TransitionRule[] = [
      {
        from_state: 'In Progress',
        to_state: 'In Review',
        active_hook_count: 1,
        hooks: [
          {
            id: 'hostile-hook-1',
            name: '<img src=x onerror=alert(1)>',
            from_state: 'In Progress',
            to_state: 'In Review',
            hook_kind: 'sync_validator',
            sort_rank: '0001',
            failure_policy: 'fail_closed',
            manifest_sha256: 'deadbeef',
            is_enabled: true,
            description: '<script>alert("xss")</script>',
          },
        ],
      },
    ];

    vi.spyOn(api, 'fetchWorkflowHooks').mockResolvedValue(hostileRules);

    const { container } = renderPage();

    await waitFor(() => {
      expect(screen.getByText('<img src=x onerror=alert(1)>')).toBeDefined();
    });

    // Zero injected img or script elements
    expect(container.querySelectorAll('img[src="x"]')).toHaveLength(0);
    expect(container.querySelectorAll('script')).toHaveLength(0);
  });

  it('silently ignores Aal2StepUpCancelledError on hook detach (Mandatory Test Case 5)', async () => {
    vi.spyOn(api, 'fetchWorkflowHooks').mockResolvedValue(api.DEFAULT_S14_4_RULES);

    const deleteSpy = vi.spyOn(api, 'deleteWorkflowHook').mockRejectedValueOnce(
      new Aal2StepUpCancelledError(),
    );

    renderPage();

    await waitFor(() => {
      expect(screen.getByText('require-qa-proof-link')).toBeDefined();
    });

    // Detach hook 1
    const detachBtn = screen.getByRole('button', { name: 'Detach require-qa-proof-link' });
    fireEvent.click(detachBtn);

    await waitFor(() => {
      expect(deleteSpy).toHaveBeenCalledWith('hook-1');
    });

    expect(screen.queryByText('Admin Verification Required (AAL2)')).toBeNull();
  });

  it('silently ignores Aal2StepUpCancelledError on hook toggle (KAN-393)', async () => {
    vi.spyOn(api, 'fetchWorkflowHooks').mockResolvedValue(api.DEFAULT_S14_4_RULES);

    const disableSpy = vi.spyOn(api, 'disableWorkflowHook').mockRejectedValueOnce(
      new Aal2StepUpCancelledError(),
    );

    renderPage();

    await waitFor(() => {
      expect(screen.getByText('require-qa-proof-link')).toBeDefined();
    });

    const toggleBtn = screen.getByRole('checkbox', { name: 'Toggle require-qa-proof-link' });
    fireEvent.click(toggleBtn);

    await waitFor(() => {
      expect(disableSpy).toHaveBeenCalledWith('hook-1');
    });

    expect(screen.queryByText('Admin Verification Required (AAL2)')).toBeNull();
  });

  it('renders empty state CTA when transition has 0 hooks (Mandatory Test Case 6)', async () => {
    const emptyRules: api.TransitionRule[] = [
      {
        from_state: 'Backlog',
        to_state: 'In Progress',
        active_hook_count: 0,
        hooks: [],
      },
    ];

    vi.spyOn(api, 'fetchWorkflowHooks').mockResolvedValue(emptyRules);

    renderPage();

    await waitFor(() => {
      expect(screen.getByTestId('empty-hooks-cta').textContent).toContain(
        "No hooks configured for this transition. Click '+ Add Hook' to attach a validator or agent gate.",
      );
    });
  });

  it('rolls back optimistic order and shows alert on 422 REORDER_SET_MISMATCH (Mandatory Test Case 6)', async () => {
    vi.spyOn(api, 'fetchWorkflowHooks').mockResolvedValue(api.DEFAULT_S14_4_RULES);
    vi.spyOn(api, 'reorderWorkflowHooks').mockRejectedValue(
      new Error('Reorder failed: 422 REORDER_SET_MISMATCH'),
    );

    renderPage();

    await waitFor(() => {
      expect(screen.getByText('forensic-code-check')).toBeDefined();
    });

    // Move hook 2 up
    const moveUpBtn = screen.getByRole('button', { name: 'Move forensic-code-check up' });
    fireEvent.click(moveUpBtn);

    await waitFor(() => {
      expect(screen.getByRole('alert').textContent).toContain('422 REORDER_SET_MISMATCH');
    });
  });

  it('reads ?to_state= and ?attach=1 on mount to auto-open AttachHookDialog', async () => {
    vi.spyOn(api, 'fetchWorkflowHooks').mockResolvedValue(api.DEFAULT_S14_4_RULES);
    vi.spyOn(api, 'fetchProjectStates').mockResolvedValue([
      { id: 'st-1', name: 'Backlog' },
      { id: 'st-2', name: 'In Progress' },
      { id: 'st-3', name: 'Done' },
    ]);

    renderPage({
      initialEntries: ['/projects/KAN/settings/workflows?to_state=In%20Progress&attach=1'],
    });

    await waitFor(() => {
      expect(screen.getByRole('dialog', { name: /Attach Workflow/i })).toBeDefined();
    });
  });

  it('renders project empty state when rules array is empty', async () => {
    vi.spyOn(api, 'fetchWorkflowHooks').mockResolvedValue([]);

    renderPage();

    await waitFor(() => {
      expect(
        screen.getByText(/No workflow transition rules configured for Project KAN/i),
      ).toBeDefined();
    });
  });

  it('handles edit hook, detach hook, and AAL2 cancellation without error banners', async () => {
    vi.spyOn(api, 'fetchWorkflowHooks').mockResolvedValue(api.DEFAULT_S14_4_RULES);
    const deleteSpy = vi.spyOn(api, 'deleteWorkflowHook').mockResolvedValue(undefined);
    vi.spyOn(api, 'disableWorkflowHook')
      .mockRejectedValueOnce(new Aal2StepUpCancelledError())
      .mockResolvedValueOnce(undefined);

    renderPage();

    await waitFor(() => {
      expect(screen.getByText('require-qa-proof-link')).toBeDefined();
    });

    // 1. Edit hook
    const editBtn = screen.getByRole('button', { name: 'Edit require-qa-proof-link' });
    fireEvent.click(editBtn);
    expect(screen.getByRole('dialog', { name: /Edit Hook/i })).toBeDefined();

    // Close dialog
    const cancelBtn = screen.getByRole('button', { name: /Cancel/i });
    fireEvent.click(cancelBtn);

    // 2. Detach hook
    const detachBtn = screen.getByRole('button', { name: 'Detach require-qa-proof-link' });
    fireEvent.click(detachBtn);
    await waitFor(() => {
      expect(deleteSpy).toHaveBeenCalledWith('hook-1');
    });

    // 3. Toggle hook with AAL2 cancellation
    const toggle = screen.getByRole('checkbox', { name: 'Toggle require-qa-proof-link' });
    fireEvent.click(toggle);

    await waitFor(() => {
      expect(api.disableWorkflowHook).toHaveBeenCalled();
    });
    expect(screen.queryByText('Admin Verification Required (AAL2)')).toBeNull();
  });

  it('renders rules with from_state === null, handles non-AAL2 error on toggle, and resolves route projectKey param', async () => {
    const rulesWithNullFrom: api.TransitionRule[] = [
      {
        from_state: null,
        to_state: 'In Progress',
        active_hook_count: 1,
        hooks: [
          {
            ...api.DEFAULT_S14_4_RULES[0]?.hooks[0],
            id: 'h-any-state',
            name: 'any-state-hook',
            from_state: null,
            to_state: 'In Progress',
          } as api.WorkflowHook,
        ],
      },
    ];

    vi.spyOn(api, 'fetchWorkflowHooks').mockResolvedValue(rulesWithNullFrom);
    vi.spyOn(api, 'disableWorkflowHook').mockRejectedValue(new Error('Generic network error'));

    // Render with route params and NO projectKeyOverride
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={['/projects/CUSTOM_PRJ/settings/workflows']}>
          <WorkflowStudioPage isAdmin={true} />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    await waitFor(() => {
      expect(screen.getByText(/Any State/)).toBeDefined();
      expect(screen.getByText('any-state-hook')).toBeDefined();
    });

    // Toggle hook with generic error (exercises non-AAL2 branch)
    const toggle = screen.getByRole('checkbox', { name: 'Toggle any-state-hook' });
    fireEvent.click(toggle);

    // Render with no projectKeyOverride and no route params (fallback to KAN)
    const { unmount } = render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={['/settings/workflows']}>
          <WorkflowStudioPage isAdmin={true} />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    await waitFor(() => {
      expect(screen.getAllByText(/Any State/).length).toBeGreaterThan(0);
    });
    unmount();
  });

  describe('Progressive Disclosure (KB-ADVANCED-DISCLOSURE-03 / KAN-369)', () => {
    it('Positive case 2: AttachHookDialog renders hook trigger and action with advanced execution policies collapsed', () => {
      render(
        <AttachHookDialog
          isOpen={true}
          projectKey="KAN"
          states={api.DEFAULT_PROJECT_STATES}
          agentDefinitions={[]}
          wasmModules={api.DEFAULT_WASM_MODULES}
          onSave={vi.fn()}
          onClose={vi.fn()}
        />,
      );

      // Primary trigger and action fields are directly visible
      expect(screen.getByLabelText(/From State/i)).toBeDefined();
      expect(screen.getByLabelText(/To State/i)).toBeDefined();
      expect(screen.getByLabelText(/Hook Name/i)).toBeDefined();
      expect(screen.getByText('Sync Wasm Validator')).toBeDefined();

      // Advanced Hook Settings section is collapsed by default
      const advSection = screen.getByTestId<HTMLDetailsElement>('attach-hook-advanced-section');
      expect(advSection.open).toBe(false);
      expect(screen.getByTestId('attach-hook-advanced-section-toggle').getAttribute('aria-expanded')).toBe('false');

      // Active overrides badge is displayed
      expect(screen.getByTestId('attach-hook-advanced-section-toggle').textContent).toContain('custom setting');

      // Toggle open
      fireEvent.click(screen.getByTestId('attach-hook-advanced-section-toggle'));
      expect(advSection.open).toBe(true);
      expect(screen.getByRole('combobox', { name: /^Failure Policy/i })).toBeDefined();
      expect(screen.getByLabelText(/Approved WebAssembly Module/i)).toBeDefined();
      expect(screen.getByText(/Allowed Mutable Fields/i)).toBeDefined();
      expect(screen.getByTestId('hook-execution-logs-section')).toBeDefined();
    });

    it('Positive case 3: CustomFieldDefinitionEditor collapses raw JSON format metadata behind Advanced mode', async () => {
      render(
        <QueryClientProvider client={queryClient}>
          <CustomFieldDefinitionEditor projectKey="KAN" isAdmin={true} />
        </QueryClientProvider>,
      );

      // Primary basic properties are rendered
      expect(await screen.findByTestId('field-name-input')).toBeDefined();
      expect(screen.getByTestId('field-slug-input')).toBeDefined();
      expect(screen.getByTestId('field-flavor-select')).toBeDefined();
      expect(screen.getByTestId('output-format-select')).toBeDefined();
      expect(screen.getByTestId('is-enabled-checkbox')).toBeDefined();

      // Advanced format & sandbox script section is collapsed by default
      const advSection = screen.getByTestId<HTMLDetailsElement>('custom-field-advanced-section');
      expect(advSection.open).toBe(false);
      expect(screen.getByTestId('custom-field-advanced-section-toggle').getAttribute('aria-expanded')).toBe('false');

      // Toggle open
      fireEvent.click(screen.getByTestId('custom-field-advanced-section-toggle'));
      expect(advSection.open).toBe(true);
      expect(screen.getByTestId('format-metadata-textarea')).toBeDefined();
      expect(screen.getByTestId('script-source-textarea')).toBeDefined();
      expect(screen.getByTestId('custom-field-test-panel')).toBeDefined();
    });
  });
});
