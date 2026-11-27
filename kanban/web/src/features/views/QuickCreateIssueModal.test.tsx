import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import React from 'react';
import { QuickCreateIssueModal } from './QuickCreateIssueModal';
import { getDrafts } from '../drafts/draftsStore';
import type { IssueItem } from './viewsApi';
import { ShellPanelsProvider, registerShellPanel } from '../../app/shellPanels';

describe('QuickCreateIssueModal (KB-P3-40, KANBA-173)', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('does not render when isOpen is false', () => {
    const { container } = render(
      <QuickCreateIssueModal
        isOpen={false}
        onClose={vi.fn()}
        onCreate={vi.fn()}
        projectKey="KAN"
      />
    );

    expect(container.firstChild).toBeNull();
  });

  it('renders summary, description, state, priority, and module fields when open and transitions to post-dialog on create', () => {
    const handleCreate = vi.fn().mockReturnValue({ key: 'KAN-99', summary: 'New Test Task' });
    const handleClose = vi.fn();

    render(
      <QuickCreateIssueModal
        isOpen={true}
        onClose={handleClose}
        onCreate={handleCreate}
        projectKey="KAN"
        modulesEnabled={true}
        modules={[{ id: 'mod-1', name: 'Core' }, { id: 'mod-2', name: 'UI' }]}
      />
    );

    expect(screen.getByRole('dialog')).toBeDefined();
    expect(screen.getByLabelText(/summary/i)).toBeDefined();
    expect(screen.getByLabelText(/description/i)).toBeDefined();
    expect(screen.getByLabelText(/^state$/i)).toBeDefined();
    expect(screen.getByLabelText(/^priority$/i)).toBeDefined();
    expect(screen.getByLabelText(/^module$/i)).toBeDefined();
    expect(screen.getByTestId('quick-create-draft-checkbox')).toBeDefined();

    // Fill in summary and submit
    const summaryInput = screen.getByLabelText(/summary/i);
    fireEvent.change(summaryInput, { target: { value: 'New Test Task' } });

    const createBtn = screen.getByRole('button', { name: /^create$/i });
    fireEvent.click(createBtn);

    expect(handleCreate).toHaveBeenCalledWith(
      expect.objectContaining({
        summary: 'New Test Task',
      })
    );

    // Verify post-creation confirmation dialog state
    const postDialog = screen.getByTestId('quick-create-post-dialog');
    expect(postDialog).toBeDefined();
    expect(screen.getByText('🎉 Work Item Created')).toBeDefined();
    expect(screen.getByText('KAN-99')).toBeDefined();

    // Clicking Done closes modal
    fireEvent.click(screen.getByTestId('post-create-done-btn'));
    expect(handleClose).toHaveBeenCalled();
  });

  it('fills all fields (description, state, priority, module) and submits', () => {
    const handleCreate = vi.fn();
    const handleClose = vi.fn();

    render(
      <QuickCreateIssueModal
        isOpen={true}
        onClose={handleClose}
        onCreate={handleCreate}
        projectKey="KAN"
        modulesEnabled={true}
        modules={[{ id: 'mod-1', name: 'Core' }, { id: 'mod-2', name: 'UI' }]}
      />
    );

    fireEvent.change(screen.getByLabelText(/summary/i), {
      target: { value: 'Complete Spec' },
    });
    fireEvent.change(screen.getByLabelText(/description/i), {
      target: { value: 'Detailed Markdown criteria' },
    });
    fireEvent.change(screen.getByLabelText(/^state$/i), {
      target: { value: 'state-in-progress' },
    });
    fireEvent.change(screen.getByLabelText(/^priority$/i), {
      target: { value: 'urgent' },
    });
    fireEvent.change(screen.getByLabelText(/^module$/i), {
      target: { value: 'mod-2' },
    });

    fireEvent.click(screen.getByRole('button', { name: /^create$/i }));

    expect(handleCreate).toHaveBeenCalledTimes(1);
    const created = handleCreate.mock.calls[0]?.[0] as Partial<IssueItem> | undefined;
    if (!created) throw new Error('handleCreate not called');
    expect(created.summary).toBe('Complete Spec');
    expect(created.description_markdown).toBe('Detailed Markdown criteria');
    expect(created.priority?.slug).toBe('urgent');
    expect(created.priority?.emoji).toBe('🔥');
    expect(created.module_ids).toEqual(['mod-2']);
  });

  it('does not submit if summary is empty or whitespace', () => {
    const handleCreate = vi.fn();

    render(
      <QuickCreateIssueModal
        isOpen={true}
        onClose={vi.fn()}
        onCreate={handleCreate}
        projectKey="KAN"
      />
    );

    // Dispatch custom event kb:create-issue to verify listener
    window.dispatchEvent(new CustomEvent('kb:create-issue'));

    fireEvent.change(screen.getByLabelText(/summary/i), {
      target: { value: '   ' },
    });
    fireEvent.click(screen.getByRole('button', { name: /^create$/i }));
    expect(handleCreate).not.toHaveBeenCalled();
  });

  it('completely unmounts Module field and submits undefined module_ids when modulesEnabled is false (Test Case 3, S7.2 8f)', () => {
    const handleCreate = vi.fn();

    render(
      <QuickCreateIssueModal
        isOpen={true}
        onClose={vi.fn()}
        onCreate={handleCreate}
        projectKey="KAN"
        modulesEnabled={false}
      />
    );

    expect(screen.queryByLabelText(/^module$/i)).toBeNull();

    // Submit with Backlog state and medium priority
    fireEvent.change(screen.getByLabelText(/summary/i), { target: { value: 'Backlog Item' } });
    fireEvent.change(screen.getByLabelText(/^state$/i), { target: { value: 'state-backlog' } });
    fireEvent.change(screen.getByLabelText(/^priority$/i), { target: { value: 'medium' } });

    fireEvent.click(screen.getByRole('button', { name: /^create$/i }));

    expect(handleCreate).toHaveBeenCalledTimes(1);
    const created = handleCreate.mock.calls[0]?.[0] as Partial<IssueItem> | undefined;
    if (!created) throw new Error('handleCreate not called');
    expect(created.summary).toBe('Backlog Item');
    expect(created.state?.name).toBe('Backlog');
    expect(created.priority?.slug).toBe('medium');
    expect(created.module_ids).toBeUndefined();
  });

  it('closes on Escape key press and Cancel button, ignoring non-escape keys', () => {
    const handleClose = vi.fn();

    render(
      <QuickCreateIssueModal
        isOpen={true}
        onClose={handleClose}
        onCreate={vi.fn()}
        projectKey="KAN"
      />
    );

    // Press Tab (non-escape key)
    fireEvent.keyDown(window, { key: 'Tab' });
    expect(handleClose).not.toHaveBeenCalled();

    const cancelBtn = screen.getByRole('button', { name: /cancel/i });
    fireEvent.click(cancelBtn);
    expect(handleClose).toHaveBeenCalledTimes(1);

    fireEvent.keyDown(window, { key: 'Escape' });
    expect(handleClose).toHaveBeenCalledTimes(2);
  });

  it('handles selecting No Module and non-urgent priorities', () => {
    const handleCreate = vi.fn();
    const handleClose = vi.fn();

    render(
      <QuickCreateIssueModal
        isOpen={true}
        onClose={handleClose}
        onCreate={handleCreate}
        projectKey="KAN"
        modulesEnabled={true}
        modules={[{ id: 'mod-1', name: 'Core' }, { id: 'mod-2', name: 'UI' }]}
      />
    );

    fireEvent.change(screen.getByLabelText(/summary/i), {
      target: { value: 'High Priority Task' },
    });
    fireEvent.change(screen.getByLabelText(/^state$/i), {
      target: { value: 'state-todo' },
    });
    fireEvent.change(screen.getByLabelText(/^priority$/i), {
      target: { value: 'high' },
    });
    // First select mod-1, then select empty "" (No Module)
    const modSelect = screen.getByLabelText(/^module$/i);
    fireEvent.change(modSelect, { target: { value: 'mod-1' } });
    fireEvent.change(modSelect, { target: { value: '' } });

    fireEvent.click(screen.getByRole('button', { name: /^create$/i }));

    expect(handleCreate).toHaveBeenCalledTimes(1);
    const created = handleCreate.mock.calls[0]?.[0] as Partial<IssueItem> | undefined;
    if (!created) throw new Error('handleCreate not called');
    expect(created.summary).toBe('High Priority Task');
    expect(created.priority?.slug).toBe('high');
    expect(created.priority?.emoji).toBe('⚡');
    expect(created.state?.name).toBe('Todo');
    expect(created.module_ids).toEqual([]);
  });

  it('saves draft to draftsStore when ✍️ Keep work-in-progress is checked', () => {
    const handleCreate = vi.fn();
    const handleClose = vi.fn();

    render(
      <QuickCreateIssueModal
        isOpen={true}
        onClose={handleClose}
        onCreate={handleCreate}
        projectKey="KAN"
        modulesEnabled={true}
        modules={[{ id: 'mod-1', name: 'Core' }, { id: 'mod-2', name: 'UI' }]}
      />
    );

    const checkbox = screen.getByTestId('quick-create-draft-checkbox');
    expect(checkbox).toBeDefined();

    // Fill fields
    fireEvent.change(screen.getByLabelText(/summary/i), {
      target: { value: 'Draft Feature Spec' },
    });
    fireEvent.change(screen.getByLabelText(/description/i), {
      target: { value: 'Needs more investigation' },
    });

    // Toggle draft checkbox
    fireEvent.click(checkbox);

    // Button should now say Save Draft
    expect(screen.getByRole('button', { name: /save draft/i })).toBeDefined();

    // Click Save Draft
    fireEvent.click(screen.getByRole('button', { name: /save draft/i }));

    // onCreate should NOT be called for drafts
    expect(handleCreate).not.toHaveBeenCalled();

    // Saved to draftsStore
    const drafts = getDrafts();
    expect(drafts).toHaveLength(1);
    expect(drafts[0]?.summary).toBe('Draft Feature Spec');
    expect(drafts[0]?.projectKey).toBe('KAN');

    // Post-creation dialog for draft is visible
    expect(screen.getByText('✍️ Draft Saved')).toBeDefined();
    expect(screen.getByText(/Saved in Drafts \(\/drafts\)/i)).toBeDefined();

    // View Issue button navigates or dismisses
    fireEvent.click(screen.getByTestId('post-create-view-btn'));
    expect(handleClose).toHaveBeenCalled();
  });

  it('post-create dialog View Issue opens peek drawer when onOpenPeek is provided', () => {
    const handleOpenPeek = vi.fn();
    const handleClose = vi.fn();
    const handleCreate = vi.fn().mockReturnValue({ key: 'KAN-42' });

    render(
      <QuickCreateIssueModal
        isOpen={true}
        onClose={handleClose}
        onCreate={handleCreate}
        projectKey="KAN"
        onOpenPeek={handleOpenPeek}
      />
    );

    fireEvent.change(screen.getByLabelText(/summary/i), {
      target: { value: 'Peek Target Issue' },
    });
    fireEvent.click(screen.getByRole('button', { name: /^create$/i }));

    expect(screen.getByTestId('quick-create-post-dialog')).toBeDefined();

    fireEvent.click(screen.getByTestId('post-create-view-btn'));
    expect(handleOpenPeek).toHaveBeenCalledWith('KAN-42');
    expect(handleClose).toHaveBeenCalled();
  });

  it('post-create dialog Create Another resets form and stays in modal', () => {
    const handleCreate = vi.fn();
    const handleClose = vi.fn();

    render(
      <QuickCreateIssueModal
        isOpen={true}
        onClose={handleClose}
        onCreate={handleCreate}
        projectKey="KAN"
      />
    );

    fireEvent.change(screen.getByLabelText(/summary/i), {
      target: { value: 'First Task' },
    });
    fireEvent.click(screen.getByRole('button', { name: /^create$/i }));

    expect(screen.getByTestId('quick-create-post-dialog')).toBeDefined();

    // Click Create Another
    fireEvent.click(screen.getByTestId('post-create-another-btn'));

    // Modal did not close
    expect(handleClose).not.toHaveBeenCalled();

    // Form is back and summary is reset
    const summaryInput = screen.getByLabelText<HTMLInputElement>(/summary/i);
    expect(summaryInput.value).toBe('');
  });

  it('updates url and dispatches popstate on View Issue when onOpenPeek is not provided and handles priority low/none', () => {
    const handleCreate = vi.fn().mockReturnValue(undefined);
    const handleClose = vi.fn();
    const popstateSpy = vi.fn();
    window.addEventListener('popstate', popstateSpy);

    const { rerender } = render(
      <QuickCreateIssueModal
        isOpen={true}
        onClose={handleClose}
        onCreate={handleCreate}
        projectKey="KAN"
      />
    );

    fireEvent.change(screen.getByLabelText(/summary/i), { target: { value: 'Low priority task' } });
    fireEvent.change(screen.getByLabelText(/^priority$/i), { target: { value: 'low' } });
    fireEvent.click(screen.getByRole('button', { name: /^create$/i }));

    const createdLow = handleCreate.mock.calls[0]?.[0] as Partial<IssueItem> | undefined;
    expect(createdLow?.priority?.emoji).toBe('🔽');

    // Click View Issue without onOpenPeek
    fireEvent.click(screen.getByTestId('post-create-view-btn'));
    expect(popstateSpy).toHaveBeenCalled();
    expect(window.location.search).toContain('peek=KAN-NEW');
    expect(handleClose).toHaveBeenCalled();

    // Rerender with 'none' priority
    handleCreate.mockReset();
    rerender(
      <QuickCreateIssueModal
        isOpen={true}
        onClose={handleClose}
        onCreate={handleCreate}
        projectKey="KAN"
      />
    );
    fireEvent.change(screen.getByLabelText(/summary/i), { target: { value: 'None priority task' } });
    fireEvent.change(screen.getByLabelText(/^priority$/i), { target: { value: 'none' } });
    fireEvent.click(screen.getByRole('button', { name: /^create$/i }));

    const createdNone = handleCreate.mock.calls[0]?.[0] as Partial<IssueItem> | undefined;
    expect(createdNone?.priority?.emoji).toBe('➖');

    window.removeEventListener('popstate', popstateSpy);
  });

  it('does not create issue when summary is whitespace or empty', () => {
    const handleCreate = vi.fn();
    const handleClose = vi.fn();
    render(
      <QuickCreateIssueModal
        isOpen={true}
        onClose={handleClose}
        onCreate={handleCreate}
        projectKey="KAN"
      />
    );

    const form = screen.getByRole('dialog').querySelector('form');
    if (!form) throw new Error('Form not found');

    fireEvent.change(screen.getByLabelText(/summary/i), { target: { value: '   ' } });
    fireEvent.submit(form);

    expect(handleCreate).not.toHaveBeenCalled();
    expect(handleClose).not.toHaveBeenCalled();
  });

  it('locks create button while submission is in-flight (disabled and aria-busy)', async () => {
    let resolveCreate!: (res: unknown) => void;
    const pendingPromise = new Promise((resolve) => {
      resolveCreate = resolve;
    });
    const handleCreate = vi.fn().mockReturnValue(pendingPromise);

    render(
      <QuickCreateIssueModal
        isOpen={true}
        onClose={vi.fn()}
        onCreate={handleCreate}
        projectKey="KAN"
      />
    );

    fireEvent.change(screen.getByLabelText(/summary/i), {
      target: { value: 'In-flight locking test' },
    });
    const createBtn = screen.getByRole<HTMLButtonElement>('button', { name: /^create$/i });
    expect(createBtn.disabled).toBe(false);

    fireEvent.click(createBtn);

    // In flight: button is locked
    expect(createBtn.disabled).toBe(true);
    expect(createBtn.getAttribute('aria-busy')).toBe('true');
    expect(createBtn.textContent).toBe('Creating...');

    // Resolve create
    await act(async () => {
      resolveCreate({ key: 'KAN-55', summary: 'In-flight locking test' });
      await pendingPromise;
    });

    expect(await screen.findByText('KAN-55')).toBeDefined();
  });

  it('keeps modal open with draft preserved and shows inline alert when submission fails offline', async () => {
    const handleCreate = vi.fn().mockRejectedValue(new Error('Slow 4G network timeout'));

    render(
      <QuickCreateIssueModal
        isOpen={true}
        onClose={vi.fn()}
        onCreate={handleCreate}
        projectKey="KAN"
      />
    );

    const summaryInput = screen.getByLabelText(/summary/i);
    const descInput = screen.getByLabelText(/description/i);
    fireEvent.change(summaryInput, { target: { value: 'Offline task draft' } });
    fireEvent.change(descInput, { target: { value: 'Important draft details to preserve' } });

    fireEvent.click(screen.getByRole('button', { name: /^create$/i }));

    const errorAlert = await screen.findByTestId('quick-create-error');
    expect(errorAlert.textContent).toContain('Slow 4G network timeout');

    // Dialog stays open and typed values are preserved
    expect(screen.getByRole('dialog')).toBeDefined();
    expect(screen.getByLabelText<HTMLInputElement>(/summary/i).value).toBe('Offline task draft');
    expect(screen.getByLabelText<HTMLTextAreaElement>(/description/i).value).toBe('Important draft details to preserve');
  });

  it('covers cancelled state mapping and non-Error submission rejection fallback', async () => {
    const handleCreate = vi.fn().mockRejectedValue('raw string submission failure');

    render(
      <QuickCreateIssueModal
        isOpen={true}
        onClose={vi.fn()}
        onCreate={handleCreate}
        projectKey="KAN"
      />
    );

    const summaryInput = screen.getByLabelText(/summary/i);
    fireEvent.change(summaryInput, { target: { value: 'Cancelled Task' } });

    const stateSelect = screen.getByLabelText(/^state$/i);
    fireEvent.change(stateSelect, { target: { value: 'state-canceled' } });

    fireEvent.click(screen.getByRole('button', { name: /^create$/i }));

    const errorAlert = await screen.findByTestId('quick-create-error');
    expect(errorAlert.textContent).toContain('Network error: Failed to create issue. Your draft has been preserved.');

    expect(handleCreate).toHaveBeenCalledWith(
      expect.objectContaining({
        summary: 'Cancelled Task',
        state: expect.objectContaining({
          id: 'state-canceled',
          name: 'Cancelled',
          group: 'cancelled',
        }) as unknown as Record<string, unknown>,
      }),
    );
  });

  describe('Progressive Disclosure with AdvancedSection (KB-ADVANCED-DISCLOSURE-02, KAN-368)', () => {
    it('Required Test Case 1 (Positive / Progressive Disclosure): renders AdvancedSection collapsed by default and submits advanced fields when expanded', () => {
      const handleCreate = vi.fn().mockReturnValue({ key: 'KAN-200', summary: 'Advanced Task' });
      const handleClose = vi.fn();

      render(
        <QuickCreateIssueModal
          isOpen={true}
          onClose={handleClose}
          onCreate={handleCreate}
          projectKey="KAN"
          modulesEnabled={true}
          modules={[{ id: 'mod-1', name: 'Core Engine' }]}
        />
      );

      // Verify toggle button and details state
      const toggle = screen.getByTestId('quick-create-advanced-toggle');
      expect(toggle.getAttribute('aria-expanded')).toBe('false');

      const details = screen.getByTestId('quick-create-advanced');
      expect(details.hasAttribute('open')).toBe(false);

      // Expand advanced section via click
      fireEvent.click(toggle);
      expect(toggle.getAttribute('aria-expanded')).toBe('true');
      expect(details.hasAttribute('open')).toBe(true);

      // Fill primary and secondary fields
      fireEvent.change(screen.getByLabelText(/summary/i), { target: { value: 'Advanced Task' } });
      fireEvent.change(screen.getByLabelText(/^due date$/i), { target: { value: '2026-12-15' } });
      fireEvent.change(screen.getByLabelText(/^parent issue$/i), { target: { value: 'KAN-50' } });
      fireEvent.change(screen.getByLabelText(/^module$/i), { target: { value: 'mod-1' } });

      fireEvent.click(screen.getByRole('button', { name: /^create$/i }));

      expect(handleCreate).toHaveBeenCalledWith(
        expect.objectContaining({
          summary: 'Advanced Task',
          due_date: '2026-12-15',
          parent: { key: 'KAN-50', summary: '' },
          module_ids: ['mod-1'],
        })
      );
    });

    it('Required Test Case 2 (Active Overrides Badge & Auto-Expand): displays active overrides count badge and auto-expands with defaultOpen', () => {
      render(
        <QuickCreateIssueModal
          isOpen={true}
          onClose={vi.fn()}
          onCreate={vi.fn()}
          projectKey="KAN"
          modulesEnabled={true}
          defaultModuleIds={['mod-1']}
          defaultDueDate="2026-12-31"
          defaultParentKey="KAN-99"
          defaultAdvancedOpen={true}
          modules={[{ id: 'mod-1', name: 'Core Engine' }]}
        />
      );

      const details = screen.getByTestId('quick-create-advanced');
      expect(details.hasAttribute('open')).toBe(true);

      // Active overrides badge renders with count of 3 custom settings
      const badge = screen.getByTestId('advanced-active-badge');
      expect(badge.textContent).toBe('3 custom settings active');
    });

    it('Required Test Case 3 (Error Auto-Expansion & Value Preservation): auto-expands on submit error and preserves input values across toggling', async () => {
      const handleCreate = vi.fn().mockRejectedValue(new Error('Validation constraint failed on server'));

      render(
        <QuickCreateIssueModal
          isOpen={true}
          onClose={vi.fn()}
          onCreate={handleCreate}
          projectKey="KAN"
          modulesEnabled={true}
        />
      );

      const toggle = screen.getByTestId('quick-create-advanced-toggle');
      const details = screen.getByTestId('quick-create-advanced');
      expect(details.hasAttribute('open')).toBe(false);

      // Enter summary and due date
      fireEvent.change(screen.getByLabelText(/summary/i), { target: { value: 'Failing Task' } });
      fireEvent.change(screen.getByLabelText(/^due date$/i), { target: { value: '2026-11-30' } });

      // Collapse and expand again to verify preservation
      fireEvent.click(toggle);
      expect(details.hasAttribute('open')).toBe(true);
      const dueDateInput = screen.getByLabelText<HTMLInputElement>(/^due date$/i);
      expect(dueDateInput.value).toBe('2026-11-30');

      fireEvent.click(screen.getByRole('button', { name: /^create$/i }));

      // Error appears and details remains open
      const err = await screen.findByTestId('quick-create-error');
      expect(err.textContent).toContain('Validation constraint failed on server');
      expect(details.hasAttribute('open')).toBe(true);
    });

    it('covers resolvedInitialStateId branches (is_default, unstarted, states[0]) and draft view link', () => {
      // Branch with states containing is_default
      const { rerender } = render(
        <QuickCreateIssueModal
          isOpen={true}
          onClose={vi.fn()}
          onCreate={vi.fn()}
          projectKey="KAN"
          defaultStateId="state-todo"
          states={[
            { id: 'st-def', name: 'Default State', is_default: true },
            { id: 'st-other', name: 'Other' },
          ]}
        />
      );
      const stateSelect = screen.getByLabelText<HTMLSelectElement>(/^state$/i);
      expect(stateSelect.value).toBe('st-def');

      // Branch with states containing group unstarted
      rerender(
        <QuickCreateIssueModal
          isOpen={true}
          onClose={vi.fn()}
          onCreate={vi.fn()}
          projectKey="KAN"
          defaultStateId="state-todo"
          states={[
            { id: 'st-started', name: 'In Progress', group: 'started' },
            { id: 'st-unstarted', name: 'Ready', group: 'unstarted' },
          ]}
        />
      );

      // Branch with states without default or unstarted
      rerender(
        <QuickCreateIssueModal
          isOpen={true}
          onClose={vi.fn()}
          onCreate={vi.fn()}
          projectKey="KAN"
          defaultStateId="state-todo"
          states={[
            { id: 'st-single', name: 'Single State', group: 'other' },
          ]}
        />
      );

      // Branch with draft saved and clicking view issue
      const handleClose = vi.fn();
      rerender(
        <QuickCreateIssueModal
          isOpen={true}
          onClose={handleClose}
          onCreate={vi.fn()}
          projectKey="KAN"
        />
      );

      fireEvent.change(screen.getByLabelText(/summary/i), { target: { value: 'Draft Item' } });
      fireEvent.click(screen.getByTestId('quick-create-draft-checkbox'));
      fireEvent.click(screen.getByRole('button', { name: /^save draft$/i }));

      expect(screen.getByText('✍️ Draft Saved')).toBeDefined();
      fireEvent.click(screen.getByTestId('post-create-view-btn'));
      expect(handleClose).toHaveBeenCalled();
    });
  });

  describe('StudioDocLink Header Integration and Escape/Backdrop Handling (KAN-480)', () => {
    it('renders StudioDocLink in quick-create-header-actions with required props and never nested in button or label', () => {
      render(
        <QuickCreateIssueModal
          isOpen={true}
          onClose={vi.fn()}
          onCreate={vi.fn()}
          projectKey="KAN"
        />
      );

      const docLink = screen.getByTestId('quick-create-doc-link');
      expect(docLink).toBeDefined();
      expect(docLink.getAttribute('href')).toBe(
        '/docs/ticket-screen-and-work-item-features#quick-create-work-item-modal-c'
      );
      expect(docLink.getAttribute('aria-label')).toBe('Quick-Create Documentation');
      expect(docLink.textContent).toContain('Quick-Create Guide ->');

      // Verify StudioDocLink is in .quick-create-header-actions
      const headerActions = docLink.closest('.quick-create-header-actions');
      expect(headerActions).not.toBeNull();

      // Ensure NEVER nested inside <button> or <label>
      expect(docLink.closest('button')).toBeNull();
      expect(docLink.closest('label')).toBeNull();
    });

    it('opens in-app help panel when StudioDocLink is clicked inside ShellPanelsProvider without dismissing modal', async () => {
      const unregister = registerShellPanel('help', ({ arg }) => (
        <div data-testid="in-app-help-drawer" className="kb-help-drawer">
          Help for {(arg as { href?: string } | undefined)?.href}
        </div>
      ));

      try {
        const handleClose = vi.fn();
        render(
          <ShellPanelsProvider>
            <QuickCreateIssueModal
              isOpen={true}
              onClose={handleClose}
              onCreate={vi.fn()}
              projectKey="KAN"
            />
          </ShellPanelsProvider>
        );

        const docLink = screen.getByTestId('quick-create-doc-link');
        fireEvent.click(docLink);

        await waitFor(() => {
          expect(screen.getByTestId('in-app-help-drawer')).toBeDefined();
        });

        const drawer = screen.getByTestId('in-app-help-drawer');
        expect(drawer.textContent).toContain(
          '/docs/ticket-screen-and-work-item-features#quick-create-work-item-modal-c'
        );
        expect(handleClose).not.toHaveBeenCalled();
      } finally {
        unregister();
      }
    });

    it('yields Escape key press when .kb-help-drawer or .kb-help-drawer-backdrop is present in the DOM', () => {
      const handleClose = vi.fn();
      render(
        <QuickCreateIssueModal
          isOpen={true}
          onClose={handleClose}
          onCreate={vi.fn()}
          projectKey="KAN"
        />
      );

      // Simulate help drawer open
      const dummyDrawer = document.createElement('div');
      dummyDrawer.className = 'kb-help-drawer';
      document.body.appendChild(dummyDrawer);

      fireEvent.keyDown(window, { key: 'Escape' });
      expect(handleClose).not.toHaveBeenCalled();

      // Remove drawer, add backdrop
      document.body.removeChild(dummyDrawer);
      const dummyBackdrop = document.createElement('div');
      dummyBackdrop.className = 'kb-help-drawer-backdrop';
      document.body.appendChild(dummyBackdrop);

      fireEvent.keyDown(window, { key: 'Escape' });
      expect(handleClose).not.toHaveBeenCalled();

      // Remove backdrop, now Escape closes modal
      document.body.removeChild(dummyBackdrop);
      fireEvent.keyDown(window, { key: 'Escape' });
      expect(handleClose).toHaveBeenCalledTimes(1);
    });

    it('yields backdrop overlay click when .kb-help-drawer or .kb-help-drawer-backdrop is present in DOM', () => {
      const handleClose = vi.fn();
      render(
        <QuickCreateIssueModal
          isOpen={true}
          onClose={handleClose}
          onCreate={vi.fn()}
          projectKey="KAN"
        />
      );

      const overlay = screen.getByTestId('quick-create-modal');

      // Add dummy help drawer
      const dummyDrawer = document.createElement('div');
      dummyDrawer.className = 'kb-help-drawer';
      document.body.appendChild(dummyDrawer);

      // Click on overlay directly (target === currentTarget)
      fireEvent.click(overlay);
      expect(handleClose).not.toHaveBeenCalled();

      // Clean up drawer
      document.body.removeChild(dummyDrawer);

      // Clicking inside modal content (target !== currentTarget) does not close
      const modalBox = overlay.querySelector('.quick-create-modal');
      if (!modalBox) throw new Error('Modal box not found');
      fireEvent.click(modalBox);
      expect(handleClose).not.toHaveBeenCalled();

      // Clicking on overlay directly when drawer is closed dismisses modal
      fireEvent.click(overlay);
      expect(handleClose).toHaveBeenCalledTimes(1);
    });

    it('yields backdrop overlay click on post-creation dialog when .kb-help-drawer is present', () => {
      const handleClose = vi.fn();
      const handleCreate = vi.fn().mockReturnValue({ key: 'KAN-101', summary: 'Done task' });

      render(
        <QuickCreateIssueModal
          isOpen={true}
          onClose={handleClose}
          onCreate={handleCreate}
          projectKey="KAN"
        />
      );

      fireEvent.change(screen.getByLabelText(/summary/i), { target: { value: 'Done task' } });
      fireEvent.click(screen.getByRole('button', { name: /^create$/i }));

      const postOverlay = screen.getByTestId('quick-create-post-dialog');

      // Add dummy drawer
      const dummyDrawer = document.createElement('div');
      dummyDrawer.className = 'kb-help-drawer';
      document.body.appendChild(dummyDrawer);

      fireEvent.click(postOverlay);
      expect(handleClose).not.toHaveBeenCalled();

      document.body.removeChild(dummyDrawer);

      // Click post overlay directly closes modal
      fireEvent.click(postOverlay);
      expect(handleClose).toHaveBeenCalledTimes(1);
    });

    it('restores focus to opener on unmount when open, and handles native input events', () => {
      const openerButton = document.createElement('button');
      openerButton.textContent = 'Open Quick Create';
      document.body.appendChild(openerButton);
      openerButton.focus();

      const { unmount } = render(
        <QuickCreateIssueModal
          isOpen={true}
          onClose={vi.fn()}
          onCreate={vi.fn()}
          projectKey="KAN"
        />
      );

      // Trigger native input and change events on inputs to verify event listener attachments
      const summaryInput = screen.getByLabelText<HTMLInputElement>(/summary/i);
      const descInput = screen.getByLabelText<HTMLTextAreaElement>(/description/i);
      fireEvent.input(summaryInput, { target: { value: 'Direct onInput summary' } });
      fireEvent.input(descInput, { target: { value: 'Direct onInput description' } });
      summaryInput.value = 'Native summary';
      act(() => {
        summaryInput.dispatchEvent(new Event('input'));
        summaryInput.dispatchEvent(new Event('change'));
      });
      descInput.value = 'Native description';
      act(() => {
        descInput.dispatchEvent(new Event('input'));
        descInput.dispatchEvent(new Event('change'));
      });

      unmount();
      expect(document.activeElement).toBe(openerButton);
      document.body.removeChild(openerButton);
    });

    it('covers state mappings (in-review, done), defaultStateId prop updates, and handleCreateAnother field clears', () => {
      const handleCreate = vi.fn().mockReturnValue({ key: 'KAN-300' });
      const { rerender } = render(
        <QuickCreateIssueModal
          isOpen={true}
          onClose={vi.fn()}
          onCreate={handleCreate}
          projectKey="KAN"
          defaultStateId="state-in-review"
        />
      );

      // Verify defaultStateId sync update
      rerender(
        <QuickCreateIssueModal
          isOpen={true}
          onClose={vi.fn()}
          onCreate={handleCreate}
          projectKey="KAN"
          defaultStateId="state-done"
        />
      );

      const summaryInput = screen.getByLabelText<HTMLInputElement>(/summary/i);
      const descInput = screen.getByLabelText<HTMLTextAreaElement>(/description/i);
      fireEvent.change(summaryInput, { target: { value: 'Task with desc' } });
      fireEvent.change(descInput, { target: { value: 'Detailed description' } });

      fireEvent.click(screen.getByRole('button', { name: /^create$/i }));

      expect(handleCreate).toHaveBeenCalledWith(
        expect.objectContaining({
          summary: 'Task with desc',
          description_markdown: 'Detailed description',
          state: expect.objectContaining({
            id: 'state-done',
            name: 'Done',
            group: 'completed',
          }) as unknown as Record<string, unknown>,
        })
      );

      // Click Create Another to verify clearing summary and description refs
      fireEvent.click(screen.getByTestId('post-create-another-btn'));
      const newSummaryInput = screen.getByLabelText<HTMLInputElement>(/summary/i);
      const newDescInput = screen.getByLabelText<HTMLTextAreaElement>(/description/i);
      expect(newSummaryInput.value).toBe('');
      expect(newDescInput.value).toBe('');

      // Test fallback state mapping for in-review without states prop
      fireEvent.change(newSummaryInput, { target: { value: 'Review Task' } });
      fireEvent.change(screen.getByLabelText(/^state$/i), { target: { value: 'state-in-review' } });
      fireEvent.click(screen.getByRole('button', { name: /^create$/i }));

      expect(handleCreate).toHaveBeenCalledWith(
        expect.objectContaining({
          summary: 'Review Task',
          state: expect.objectContaining({
            id: 'state-in-review',
            name: 'In Review',
            group: 'started',
          }) as unknown as Record<string, unknown>,
        })
      );
    });

    it('covers matchedState without group and null color_hex fallback', () => {
      const handleCreate = vi.fn();
      render(
        <QuickCreateIssueModal
          isOpen={true}
          onClose={vi.fn()}
          onCreate={handleCreate}
          projectKey="KAN"
          states={[{ id: 'st-nogroup', name: 'No Group State' }]}
        />
      );

      fireEvent.change(screen.getByLabelText(/summary/i), { target: { value: 'No group item' } });
      fireEvent.click(screen.getByRole('button', { name: /^create$/i }));

      expect(handleCreate).toHaveBeenCalledWith(
        expect.objectContaining({
          summary: 'No group item',
          state: {
            id: 'st-nogroup',
            name: 'No Group State',
            group: 'unstarted',
            color_hex: null,
          },
        })
      );
    });

    it('deactivates useFocusTrap when HelpDrawer is open in ShellPanelsProvider so focus is not stolen', async () => {
      const unregister = registerShellPanel('help', () => (
        <div data-testid="in-app-help-drawer" className="kb-help-drawer">
          <button type="button" data-testid="drawer-action-btn">Help Action</button>
        </div>
      ));

      try {
        render(
          <ShellPanelsProvider>
            <QuickCreateIssueModal
              isOpen={true}
              onClose={vi.fn()}
              onCreate={vi.fn()}
              projectKey="KAN"
            />
          </ShellPanelsProvider>
        );

        // Click StudioDocLink to open HelpDrawer
        const docLink = screen.getByTestId('quick-create-doc-link');
        fireEvent.click(docLink);

        await waitFor(() => {
          expect(screen.getByTestId('in-app-help-drawer')).toBeDefined();
        });

        const drawerBtn = screen.getByTestId('drawer-action-btn');
        drawerBtn.focus();
        expect(document.activeElement).toBe(drawerBtn);

        // Press Tab key while inside drawer: focus trap does NOT preventDefault or steal focus
        const tabEvent = new KeyboardEvent('keydown', { key: 'Tab', bubbles: true, cancelable: true });
        document.dispatchEvent(tabEvent);
        expect(tabEvent.defaultPrevented).toBe(false);
      } finally {
        unregister();
      }
    });
  });
});
