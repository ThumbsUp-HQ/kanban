/**
 * Unit tests for DeleteAuditModal (KB-P3-AUDIT-23).
 */

import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { registerShellPanel, ShellPanelsProvider } from '../../../app/shellPanels';
import { DeleteAuditModal } from '../DeleteAuditModal';
import * as clientModule from '../../../api/client';

describe('DeleteAuditModal', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('renders nothing when isOpen is false or item is null', () => {
    const { rerender } = render(
      <DeleteAuditModal
        isOpen={false}
        onClose={vi.fn()}
        onConfirmedDelete={vi.fn()}
        kind="state"
        item={{ id: 'state-1', name: 'In Progress' }}
        projectKey="KAN"
      />
    );
    expect(screen.queryByTestId('delete-audit-modal')).toBeNull();

    rerender(
      <DeleteAuditModal
        isOpen={true}
        onClose={vi.fn()}
        onConfirmedDelete={vi.fn()}
        kind="state"
        item={null}
        projectKey="KAN"
      />
    );
    expect(screen.queryByTestId('delete-audit-modal')).toBeNull();
  });

  it('fetches state audit impact, displays blast radius and confirms deletion', async () => {
    vi.spyOn(clientModule, 'apiFetch').mockResolvedValueOnce({
      state_id: 'state-1',
      state_name: 'In Progress',
      issues_count: 5,
      sample_issue_keys: ['KAN-101', 'KAN-102'],
      workflow_hooks: [
        {
          id: 'hook-1',
          name: 'Slack Hook',
          from_state_id: 'state-1',
          to_state_id: 'state-2',
          is_enabled: true,
        },
        {
          id: 'hook-2',
          name: 'Inactive Hook',
          from_state_id: 'state-1',
          to_state_id: 'state-3',
          is_enabled: false,
        },
      ],
      pending_executions_count: 0,
      historical_executions_count: 12,
      saved_views: [{ id: 'view-1', name: 'Sprint View' }],
      is_default: false,
      blocking_reasons: [],
      valid_replacement_states: [
        { id: 'state-2', name: 'Done', group: 'completed', color_hex: '#059669' },
        { id: 'state-3', name: 'Closed', group: 'completed', color_hex: '#64748b' },
      ],
    });

    const handleConfirm = vi.fn().mockResolvedValue(undefined);
    const handleClose = vi.fn();

    render(
      <DeleteAuditModal
        isOpen={true}
        onClose={handleClose}
        onConfirmedDelete={handleConfirm}
        kind="state"
        item={{ id: 'state-1', name: 'In Progress' }}
        projectKey="KAN"
      />
    );

    // Initial loading indicator
    expect(screen.getByTestId('audit-loading')).toBeDefined();

    await waitFor(() => {
      expect(screen.getByTestId('audit-issues-count').textContent).toBe('5');
    });

    expect(screen.getByTestId('audit-sample-keys').textContent).toContain('KAN-101');
    expect(screen.getByTestId('audit-hooks-count').textContent).toBe('2');
    expect(screen.getByTestId('audit-pending-count').textContent).toBe('0');
    expect(screen.getByTestId('audit-historical-count').textContent).toBe('12');
    expect(screen.getByTestId('audit-views-count').textContent).toBe('1');
    expect(screen.getByTestId('audit-hooks-list').textContent).toContain('Slack Hook (Enabled)');
    expect(screen.getByTestId('audit-hooks-list').textContent).toContain('Inactive Hook (Disabled)');
    expect(screen.getByTestId('audit-views-list').textContent).toContain('Sprint View');

    // Replacement select defaults to the first valid replacement
    const select = screen.getByTestId<HTMLSelectElement>('audit-replacement-select');
    expect(select.value).toBe('state-2');

    // Change replacement to state-3
    fireEvent.change(select, { target: { value: 'state-3' } });
    expect(select.value).toBe('state-3');

    // Migrate hooks checkbox is checked by default
    const checkbox = screen.getByTestId<HTMLInputElement>('audit-migrate-hooks-checkbox');
    expect(checkbox.checked).toBe(true);

    // Toggle checkbox
    fireEvent.click(checkbox);
    expect(checkbox.checked).toBe(false);

    // Click confirm
    const confirmBtn = screen.getByTestId('audit-confirm-delete-btn');
    expect(confirmBtn.hasAttribute('disabled')).toBe(false);
    fireEvent.click(confirmBtn);

    await waitFor(() => {
      expect(handleConfirm).toHaveBeenCalledWith('state-3', false);
      expect(handleClose).toHaveBeenCalled();
    });
  });

  it('fetches label audit impact, displays blast radius and confirms deletion', async () => {
    vi.spyOn(clientModule, 'apiFetch').mockResolvedValueOnce({
      label_id: 'label-1',
      label_name: 'bug',
      issues_count: 2,
      sample_issue_keys: ['KAN-201'],
      saved_views: [{ id: 'view-2', name: 'Bugs Board' }],
      blocking_reasons: [],
      valid_replacement_labels: [
        { id: 'label-2', name: 'defect', color_hex: '#dc2626' },
      ],
    });

    const handleConfirm = vi.fn().mockResolvedValue(undefined);
    const handleClose = vi.fn();

    render(
      <DeleteAuditModal
        isOpen={true}
        onClose={handleClose}
        onConfirmedDelete={handleConfirm}
        kind="label"
        item={{ id: 'label-1', name: 'bug' }}
        projectKey="KAN"
      />
    );

    await waitFor(() => {
      expect(screen.getByTestId('audit-issues-count').textContent).toBe('2');
    });

    expect(screen.getByTestId('audit-views-count').textContent).toBe('1');
    expect(screen.getByTestId('audit-views-list').textContent).toContain('Bugs Board');

    // Confirm button is enabled and calls handleConfirm
    fireEvent.click(screen.getByTestId('audit-confirm-delete-btn'));

    await waitFor(() => {
      expect(handleConfirm).toHaveBeenCalledWith('label-2', undefined);
      expect(handleClose).toHaveBeenCalled();
    });
  });

  it('renders blocking reasons and disables confirm button', async () => {
    vi.spyOn(clientModule, 'apiFetch').mockResolvedValueOnce({
      state_id: 'state-default',
      state_name: 'Todo',
      issues_count: 10,
      sample_issue_keys: ['KAN-1'],
      workflow_hooks: [],
      pending_executions_count: 1,
      historical_executions_count: 3,
      saved_views: [],
      is_default: true,
      blocking_reasons: ['DEFAULT_STATE', 'TRANSITION_IN_FLIGHT'],
      valid_replacement_states: [],
    });

    render(
      <DeleteAuditModal
        isOpen={true}
        onClose={vi.fn()}
        onConfirmedDelete={vi.fn()}
        kind="state"
        item={{ id: 'state-default', name: 'Todo' }}
        projectKey="KAN"
      />
    );

    await waitFor(() => {
      expect(screen.getByTestId('audit-blocking-reasons')).toBeDefined();
    });

    expect(screen.getByTestId('audit-blocking-reasons').textContent).toContain('Cannot delete the default state');
    expect(screen.getByTestId('audit-blocking-reasons').textContent).toContain('Transitions are currently in flight');

    const confirmBtn = screen.getByTestId('audit-confirm-delete-btn');
    expect(confirmBtn.hasAttribute('disabled')).toBe(true);
  });

  it('handles LAST_STATE_IN_GROUP, ACTIVE_AUTOMATION_HOOK_REQUIRES_STATE, and unknown reasons', async () => {
    vi.spyOn(clientModule, 'apiFetch').mockResolvedValueOnce({
      state_id: 'state-grp',
      state_name: 'Backlog',
      issues_count: 0,
      sample_issue_keys: [],
      workflow_hooks: [],
      pending_executions_count: 0,
      historical_executions_count: 0,
      saved_views: [],
      is_default: false,
      blocking_reasons: [
        'LAST_STATE_IN_GROUP',
        'ACTIVE_AUTOMATION_HOOK_REQUIRES_STATE',
        'CUSTOM_BLOCK_REASON',
      ],
      valid_replacement_states: [],
    });

    render(
      <DeleteAuditModal
        isOpen={true}
        onClose={vi.fn()}
        onConfirmedDelete={vi.fn()}
        kind="state"
        item={{ id: 'state-grp', name: 'Backlog' }}
        projectKey="KAN"
      />
    );

    await waitFor(() => {
      expect(screen.getByTestId('audit-blocking-reasons')).toBeDefined();
    });

    expect(screen.getByTestId('audit-blocking-reasons').textContent).toContain('Cannot delete the only state in this workflow group');
    expect(screen.getByTestId('audit-blocking-reasons').textContent).toContain('Enabled automation hooks reference this state');
    expect(screen.getByTestId('audit-blocking-reasons').textContent).toContain('CUSTOM_BLOCK_REASON');
  });

  it('handles audit fetch failure gracefully with fallback message', async () => {
    vi.spyOn(clientModule, 'apiFetch').mockRejectedValueOnce({});

    render(
      <DeleteAuditModal
        isOpen={true}
        onClose={vi.fn()}
        onConfirmedDelete={vi.fn()}
        kind="state"
        item={{ id: 'state-1', name: 'Test' }}
        projectKey="KAN"
      />
    );

    await waitFor(() => {
      expect(screen.getByTestId('audit-error-message').textContent).toContain('Failed to compute reverse audit impact.');
    });
  });

  it('handles delete execution failure gracefully with fallback message', async () => {
    vi.spyOn(clientModule, 'apiFetch').mockResolvedValueOnce({
      state_id: 'state-1',
      state_name: 'Test',
      issues_count: 0,
      sample_issue_keys: [],
      workflow_hooks: [],
      pending_executions_count: 0,
      historical_executions_count: 0,
      saved_views: [],
      is_default: false,
      blocking_reasons: [],
      valid_replacement_states: [],
    });

    const handleConfirm = vi.fn().mockRejectedValueOnce({});

    render(
      <DeleteAuditModal
        isOpen={true}
        onClose={vi.fn()}
        onConfirmedDelete={handleConfirm}
        kind="state"
        item={{ id: 'state-1', name: 'Test' }}
        projectKey="KAN"
      />
    );

    await waitFor(() => {
      expect(screen.getByTestId('audit-confirm-delete-btn')).toBeDefined();
    });

    fireEvent.click(screen.getByTestId('audit-confirm-delete-btn'));

    await waitFor(() => {
      expect(screen.getByTestId('audit-error-message').textContent).toContain('Failed to delete item.');
    });
  });

  it('triggers onClose when clicking cancel or the close X button', async () => {
    vi.spyOn(clientModule, 'apiFetch').mockResolvedValueOnce({
      label_id: 'label-1',
      label_name: 'test',
      issues_count: 0,
      sample_issue_keys: [],
      saved_views: [],
      blocking_reasons: [],
      valid_replacement_labels: [],
    });

    const handleClose = vi.fn();
    render(
      <DeleteAuditModal
        isOpen={true}
        onClose={handleClose}
        onConfirmedDelete={vi.fn()}
        kind="label"
        item={{ id: 'label-1', name: 'test' }}
        projectKey="KAN"
      />
    );

    await waitFor(() => {
      expect(screen.getByTestId('audit-cancel-btn')).toBeDefined();
    });

    fireEvent.click(screen.getByTestId('audit-cancel-btn'));
    expect(handleClose).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByTestId('audit-close-x-btn'));
    expect(handleClose).toHaveBeenCalledTimes(2);
  });

  it('handles unmounting before API response resolves without error', () => {
    let resolveApi: (value: unknown) => void = () => {
      // noop
    };
    const pendingPromise = new Promise((resolve) => {
      resolveApi = resolve;
    });
    vi.spyOn(clientModule, 'apiFetch').mockReturnValueOnce(pendingPromise);

    const { unmount } = render(
      <DeleteAuditModal
        isOpen={true}
        onClose={vi.fn()}
        onConfirmedDelete={vi.fn()}
        kind="state"
        item={{ id: 'state-unmount', name: 'Unmount' }}
        projectKey="KAN"
      />
    );

    unmount();
    resolveApi({
      state_id: 'state-unmount',
      state_name: 'Unmount',
      issues_count: 0,
      sample_issue_keys: [],
      workflow_hooks: [],
      pending_executions_count: 0,
      historical_executions_count: 0,
      saved_views: [],
      is_default: false,
      blocking_reasons: [],
      valid_replacement_states: [],
    });
  });

  it('handles empty replacement states and labels gracefully', async () => {
    vi.spyOn(clientModule, 'apiFetch').mockResolvedValueOnce({
      state_id: 'state-empty',
      project_id: 'p-1',
      issues_count: 0,
      sample_issue_keys: [],
      workflow_hooks: [],
      pending_executions_count: 0,
      saved_views: [],
      is_default: false,
      blocking_reasons: [],
      valid_replacement_states: [],
    });

    render(
      <DeleteAuditModal
        isOpen={true}
        onClose={vi.fn()}
        onConfirmedDelete={vi.fn()}
        kind="state"
        item={{ id: 'state-empty', name: 'Empty State' }}
        projectKey="KAN"
      />
    );

    await waitFor(() => {
      expect(screen.getByTestId('audit-issues-count').textContent).toBe('0');
    });

    vi.spyOn(clientModule, 'apiFetch').mockResolvedValueOnce({
      label_id: 'label-empty',
      project_id: 'p-1',
      issues_count: 0,
      sample_issue_keys: [],
      saved_views: [],
      blocking_reasons: [],
      valid_replacement_labels: [],
    });

    render(
      <DeleteAuditModal
        isOpen={true}
        onClose={vi.fn()}
        onConfirmedDelete={vi.fn()}
        kind="label"
        item={{ id: 'label-empty', name: 'Empty Label' }}
        projectKey="KAN"
      />
    );

    await waitFor(() => {
      expect(screen.getAllByTestId('audit-issues-count')[1]?.textContent).toBe('0');
    });
  });

  it('correctly reads is_enabled: true, renders (Enabled), and enforces replacement requirement', async () => {
    vi.spyOn(clientModule, 'apiFetch').mockResolvedValueOnce({
      state_id: 'state-active-hook',
      state_name: 'In Review',
      issues_count: 0,
      sample_issue_keys: [],
      workflow_hooks: [
        {
          id: 'hook-active-1',
          name: 'CI Guard Hook',
          from_state_id: 'state-active-hook',
          to_state_id: 'state-target',
          is_enabled: true,
        },
        {
          id: 'hook-disabled-2',
          name: 'Legacy Audit Hook',
          from_state_id: 'state-active-hook',
          to_state_id: 'state-target',
          enabled: false,
        },
        {
          id: 'hook-legacy-active-3',
          name: 'Legacy Active Hook',
          from_state_id: 'state-active-hook',
          to_state_id: 'state-target',
          enabled: true,
        },
      ],
      pending_executions_count: 0,
      historical_executions_count: 0,
      saved_views: [],
      is_default: false,
      blocking_reasons: [],
      valid_replacement_states: [
        { id: 'state-target', name: 'Done', group: 'completed', color_hex: '#10b981' },
      ],
    });

    render(
      <DeleteAuditModal
        isOpen={true}
        onClose={vi.fn()}
        onConfirmedDelete={vi.fn()}
        kind="state"
        item={{ id: 'state-active-hook', name: 'In Review' }}
        projectKey="KAN"
      />
    );

    await waitFor(() => {
      expect(screen.getByTestId('audit-hooks-count').textContent).toBe('3');
    });

    const hooksList = screen.getByTestId('audit-hooks-list');
    expect(hooksList.textContent).toContain('CI Guard Hook (Enabled)');
    expect(hooksList.textContent).not.toContain('CI Guard Hook (Disabled)');
    expect(hooksList.textContent).toContain('Legacy Audit Hook (Disabled)');
    expect(hooksList.textContent).toContain('Legacy Active Hook (Enabled)');

    // Because an active hook exists, replacement is required
    const confirmBtn = screen.getByTestId('audit-confirm-delete-btn');
    expect(confirmBtn.hasAttribute('disabled')).toBe(false);

    // If replacement selection is cleared/empty, confirm button is blocked
    const select = screen.getByTestId<HTMLSelectElement>('audit-replacement-select');
    fireEvent.change(select, { target: { value: '' } });
    expect(confirmBtn.hasAttribute('disabled')).toBe(true);
  });

  describe('StudioDocLink Header Integration and ARIA Verification (KAN-506)', () => {
    afterEach(() => {
      document.documentElement.removeAttribute('data-theme');
    });

    it('renders delete-audit-doc-link with correct href, title, and aria-label in modal header actions group in Light and Dark themes', async () => {
      for (const theme of ['light', 'dark'] as const) {
        vi.spyOn(clientModule, 'apiFetch').mockResolvedValueOnce({
          state_id: 'state-1',
          state_name: 'In Progress',
          issues_count: 0,
          sample_issue_keys: [],
          workflow_hooks: [],
          pending_executions_count: 0,
          historical_executions_count: 0,
          saved_views: [],
          is_default: false,
          blocking_reasons: [],
          valid_replacement_states: [],
        });

        document.documentElement.setAttribute('data-theme', theme);
        const { unmount } = render(
          <DeleteAuditModal
            isOpen={true}
            onClose={vi.fn()}
            onConfirmedDelete={vi.fn()}
            kind="state"
            item={{ id: 'state-1', name: 'In Progress' }}
            projectKey="KAN"
          />
        );

        await waitFor(() => {
          expect(screen.getByTestId('delete-audit-doc-link')).toBeDefined();
        });

        const docLink = screen.getByTestId('delete-audit-doc-link');
        expect(docLink).toBeDefined();
        expect(docLink.getAttribute('href')).toBe(
          '/docs/universal-object-graph-and-link-auditor#state-deletion'
        );
        expect(docLink.getAttribute('aria-label')).toBe(
          'State Deletion and Dependency Remapping Documentation'
        );
        expect(docLink.textContent).toContain('Documentation ->');

        // Confirm modal accessibility attributes
        const modal = screen.getByTestId('delete-audit-modal');
        expect(modal.getAttribute('role')).toBe('dialog');
        expect(modal.getAttribute('aria-modal')).toBe('true');

        // Confirm header actions container wraps both doc link and close button
        const headerActions = docLink.closest('.kb-modal-header-actions');
        expect(headerActions).not.toBeNull();
        if (!headerActions) throw new Error('headerActions is null');

        const closeBtn = headerActions.querySelector('[data-testid="audit-close-x-btn"]');
        expect(closeBtn).not.toBeNull();

        unmount();
      }
    });

    it('supports keyboard focus navigation to the doc link', async () => {
      vi.spyOn(clientModule, 'apiFetch').mockResolvedValueOnce({
        state_id: 'state-1',
        state_name: 'In Progress',
        issues_count: 0,
        sample_issue_keys: [],
        workflow_hooks: [],
        pending_executions_count: 0,
        historical_executions_count: 0,
        saved_views: [],
        is_default: false,
        blocking_reasons: [],
        valid_replacement_states: [],
      });

      render(
        <DeleteAuditModal
          isOpen={true}
          onClose={vi.fn()}
          onConfirmedDelete={vi.fn()}
          kind="state"
          item={{ id: 'state-1', name: 'In Progress' }}
          projectKey="KAN"
        />
      );

      await waitFor(() => {
        expect(screen.getByTestId('delete-audit-doc-link')).toBeDefined();
      });

      const docLink = screen.getByTestId('delete-audit-doc-link');
      docLink.focus();
      expect(document.activeElement).toBe(docLink);
    });

    it('opens in-app help panel via ShellPanelsProvider without closing modal state', async () => {
      vi.spyOn(clientModule, 'apiFetch').mockResolvedValueOnce({
        state_id: 'state-1',
        state_name: 'In Progress',
        issues_count: 0,
        sample_issue_keys: [],
        workflow_hooks: [],
        pending_executions_count: 0,
        historical_executions_count: 0,
        saved_views: [],
        is_default: false,
        blocking_reasons: [],
        valid_replacement_states: [],
      });

      const unregister = registerShellPanel('help', ({ arg }) => (
        <div data-testid="in-app-help-panel">
          Help Drawer for {(arg as { href?: string } | undefined)?.href}
        </div>
      ));

      try {
        render(
          <ShellPanelsProvider>
            <DeleteAuditModal
              isOpen={true}
              onClose={vi.fn()}
              onConfirmedDelete={vi.fn()}
              kind="state"
              item={{ id: 'state-1', name: 'In Progress' }}
              projectKey="KAN"
            />
          </ShellPanelsProvider>
        );

        await waitFor(() => {
          expect(screen.getByTestId('delete-audit-doc-link')).toBeDefined();
        });

        const docLink = screen.getByTestId('delete-audit-doc-link');
        fireEvent.click(docLink);

        const helpPanel = screen.getByTestId('in-app-help-panel');
        expect(helpPanel).toBeDefined();
        expect(helpPanel.textContent).toContain(
          '/docs/universal-object-graph-and-link-auditor#state-deletion'
        );

        // Modal title remains visible and functional
        expect(screen.getByText('Delete Workflow State: In Progress')).toBeDefined();
      } finally {
        unregister();
      }
    });
  });
});
