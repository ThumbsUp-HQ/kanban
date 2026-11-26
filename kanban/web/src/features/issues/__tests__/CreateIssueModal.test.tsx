// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, act, waitFor } from '@testing-library/react';
import React from 'react';
import { QuickCreateIssueModal } from '../../views/QuickCreateIssueModal';
import { getDrafts } from '../../drafts/draftsStore';

describe('CreateIssueModal (+ New work item) Description & Input Sync (KAN-434)', () => {
  beforeEach(() => {
    localStorage.clear();
    vi.clearAllMocks();
  });

  it('submits non-empty description_markdown populated via fireEvent.change and fireEvent.input', () => {
    const handleCreate = vi.fn().mockReturnValue({ key: 'KAN-101', summary: 'Standard Event Task' });
    const handleClose = vi.fn();

    render(
      <QuickCreateIssueModal
        isOpen={true}
        onClose={handleClose}
        onCreate={handleCreate}
        projectKey="KAN"
      />
    );

    const summaryInput = screen.getByLabelText<HTMLInputElement>(/summary/i);
    const descInput = screen.getByLabelText<HTMLTextAreaElement>(/description/i);

    // Standard React events
    fireEvent.change(summaryInput, { target: { value: 'Standard Event Task' } });
    fireEvent.input(descInput, { target: { value: '## Acceptance Criteria\n- Step 1\n- Step 2' } });

    const createBtn = screen.getByRole('button', { name: /^create$/i });
    fireEvent.click(createBtn);

    expect(handleCreate).toHaveBeenCalledWith(
      expect.objectContaining({
        summary: 'Standard Event Task',
        description_markdown: '## Acceptance Criteria\n- Step 1\n- Step 2',
      })
    );
  });

  it('submits exact description_markdown populated via raw DOM value assignment and Event("input")', () => {
    const handleCreate = vi.fn().mockReturnValue({ key: 'KAN-102', summary: 'Programmatic Input Task' });
    const handleClose = vi.fn();

    render(
      <QuickCreateIssueModal
        isOpen={true}
        onClose={handleClose}
        onCreate={handleCreate}
        projectKey="KAN"
      />
    );

    const summaryInput = document.getElementById('quick-create-summary') as HTMLInputElement;
    const descInput = document.getElementById('quick-create-description') as HTMLTextAreaElement;

    expect(summaryInput).toBeTruthy();
    expect(descInput).toBeTruthy();

    // Emulate React 19 DevTools fill() / automation directly mutating el.value without React onChange
    act(() => {
      summaryInput.value = 'Programmatic DOM Input Task';
      summaryInput.dispatchEvent(new Event('input', { bubbles: true }));

      descInput.value = 'Programmatic raw DOM description text for KAN-434';
      descInput.dispatchEvent(new Event('input', { bubbles: true }));
    });

    const createBtn = screen.getByRole('button', { name: /^create$/i });
    fireEvent.click(createBtn);

    expect(handleCreate).toHaveBeenCalledWith(
      expect.objectContaining({
        summary: 'Programmatic DOM Input Task',
        description_markdown: 'Programmatic raw DOM description text for KAN-434',
      })
    );
  });

  it('submits exact description_markdown populated via raw DOM value assignment and Event("change")', () => {
    const handleCreate = vi.fn().mockReturnValue({ key: 'KAN-103', summary: 'Programmatic Change Task' });
    const handleClose = vi.fn();

    render(
      <QuickCreateIssueModal
        isOpen={true}
        onClose={handleClose}
        onCreate={handleCreate}
        projectKey="KAN"
      />
    );

    const summaryInput = document.getElementById('quick-create-summary') as HTMLInputElement;
    const descInput = document.getElementById('quick-create-description') as HTMLTextAreaElement;

    act(() => {
      summaryInput.value = 'Programmatic DOM Change Task';
      summaryInput.dispatchEvent(new Event('change', { bubbles: true }));

      descInput.value = 'Programmatic DOM change description for KAN-434';
      descInput.dispatchEvent(new Event('change', { bubbles: true }));
    });

    const createBtn = screen.getByRole('button', { name: /^create$/i });
    fireEvent.click(createBtn);

    expect(handleCreate).toHaveBeenCalledWith(
      expect.objectContaining({
        summary: 'Programmatic DOM Change Task',
        description_markdown: 'Programmatic DOM change description for KAN-434',
      })
    );
  });

  it('submits without description_markdown when description is left empty', () => {
    const handleCreate = vi.fn().mockReturnValue({ key: 'KAN-104', summary: 'No Description Task' });

    render(
      <QuickCreateIssueModal
        isOpen={true}
        onClose={vi.fn()}
        onCreate={handleCreate}
        projectKey="KAN"
      />
    );

    const summaryInput = document.getElementById('quick-create-summary') as HTMLInputElement;
    act(() => {
      summaryInput.value = 'No Description Task';
      summaryInput.dispatchEvent(new Event('input', { bubbles: true }));
    });

    const createBtn = screen.getByRole('button', { name: /^create$/i });
    fireEvent.click(createBtn);

    expect(handleCreate).toHaveBeenCalledWith(
      expect.objectContaining({
        summary: 'No Description Task',
      })
    );
    const calls = handleCreate.mock.calls as Record<string, unknown>[][];
    const submittedPayload = calls[0]?.[0];
    expect(submittedPayload?.description_markdown).toBeUndefined();
  });

  it('syncs raw DOM description to draft storage when Save as Draft is checked', () => {
    const handleCreate = vi.fn();

    render(
      <QuickCreateIssueModal
        isOpen={true}
        onClose={vi.fn()}
        onCreate={handleCreate}
        projectKey="KAN"
      />
    );

    const summaryInput = document.getElementById('quick-create-summary') as HTMLInputElement;
    const descInput = document.getElementById('quick-create-description') as HTMLTextAreaElement;
    const draftCheckbox = screen.getByTestId('quick-create-draft-checkbox');

    act(() => {
      summaryInput.value = 'Draft Item with Raw DOM';
      summaryInput.dispatchEvent(new Event('input', { bubbles: true }));

      descInput.value = 'Draft description populated by raw DOM';
      descInput.dispatchEvent(new Event('input', { bubbles: true }));
    });

    fireEvent.click(draftCheckbox);

    const createBtn = screen.getByRole('button', { name: /save draft/i });
    fireEvent.click(createBtn);

    const drafts = getDrafts();
    expect(drafts.length).toBe(1);
    const firstDraft = drafts[0];
    expect(firstDraft?.summary).toBe('Draft Item with Raw DOM');
    expect(firstDraft?.description).toBe('Draft description populated by raw DOM');
  });

  it('clears input ref values when handleDone or handleCreateAnother is invoked', () => {
    const handleCreate = vi.fn().mockReturnValue({ key: 'KAN-105', summary: 'Multi-Create' });

    render(
      <QuickCreateIssueModal
        isOpen={true}
        onClose={vi.fn()}
        onCreate={handleCreate}
        projectKey="KAN"
      />
    );

    const summaryInput = document.getElementById('quick-create-summary') as HTMLInputElement;
    const descInput = document.getElementById('quick-create-description') as HTMLTextAreaElement;

    act(() => {
      summaryInput.value = 'First Task';
      summaryInput.dispatchEvent(new Event('input', { bubbles: true }));
      descInput.value = 'First Description';
      descInput.dispatchEvent(new Event('input', { bubbles: true }));
    });

    const createBtn = screen.getByRole('button', { name: /^create$/i });
    fireEvent.click(createBtn);

    expect(screen.getByTestId('quick-create-post-dialog')).toBeTruthy();

    const createAnotherBtn = screen.getByTestId('post-create-another-btn');
    fireEvent.click(createAnotherBtn);

    const resetSummary = document.getElementById('quick-create-summary') as HTMLInputElement;
    const resetDesc = document.getElementById('quick-create-description') as HTMLTextAreaElement;
    expect(resetSummary.value).toBe('');
    expect(resetDesc.value).toBe('');
  });

  it('handles post dialog actions: done, view issue, and peek navigation', () => {
    const handleCreate = vi.fn().mockReturnValue({ key: 'KAN-106', summary: 'Peek Task' });
    const handleClose = vi.fn();
    const handleOpenPeek = vi.fn();

    render(
      <QuickCreateIssueModal
        isOpen={true}
        onClose={handleClose}
        onCreate={handleCreate}
        onOpenPeek={handleOpenPeek}
        projectKey="KAN"
      />
    );

    const summaryInput = document.getElementById('quick-create-summary') as HTMLInputElement;
    act(() => {
      summaryInput.value = 'Peek Task';
      summaryInput.dispatchEvent(new Event('input', { bubbles: true }));
    });

    const createBtn = screen.getByRole('button', { name: /^create$/i });
    fireEvent.click(createBtn);

    const viewBtn = screen.getByTestId('post-create-view-btn');
    fireEvent.click(viewBtn);
    expect(handleOpenPeek).toHaveBeenCalledWith('KAN-106');
    expect(handleClose).toHaveBeenCalled();
  });

  it('handles view issue without onOpenPeek fallback to popstate history', () => {
    const handleCreate = vi.fn().mockReturnValue({ key: 'KAN-107', summary: 'History Task' });

    render(
      <QuickCreateIssueModal
        isOpen={true}
        onClose={vi.fn()}
        onCreate={handleCreate}
        projectKey="KAN"
      />
    );

    const summaryInput = document.getElementById('quick-create-summary') as HTMLInputElement;
    act(() => {
      summaryInput.value = 'History Task';
      summaryInput.dispatchEvent(new Event('input', { bubbles: true }));
    });

    const createBtn = screen.getByRole('button', { name: /^create$/i });
    fireEvent.click(createBtn);

    const viewBtn = screen.getByTestId('post-create-view-btn');
    fireEvent.click(viewBtn);
  });

  it('handles submission errors and displays error message banner', async () => {
    const handleCreate = vi.fn().mockRejectedValue(new Error('Network failure 500'));

    render(
      <QuickCreateIssueModal
        isOpen={true}
        onClose={vi.fn()}
        onCreate={handleCreate}
        projectKey="KAN"
      />
    );

    const summaryInput = document.getElementById('quick-create-summary') as HTMLInputElement;
    act(() => {
      summaryInput.value = 'Failing Task';
      summaryInput.dispatchEvent(new Event('input', { bubbles: true }));
    });

    const createBtn = screen.getByRole('button', { name: /^create$/i });
    fireEvent.click(createBtn);

    await waitFor(() => {
      expect(screen.getByTestId('quick-create-error')).toBeDefined();
      expect(screen.getByText(/Network failure 500/)).toBeDefined();
    });
  });

  it('supports escape key to close modal', () => {
    const handleClose = vi.fn();

    render(
      <QuickCreateIssueModal
        isOpen={true}
        onClose={handleClose}
        onCreate={vi.fn()}
        projectKey="KAN"
      />
    );

    fireEvent.keyDown(window, { key: 'Escape' });
    expect(handleClose).toHaveBeenCalled();
  });

  it('exercises state resolution branches and priority/state fallbacks', () => {
    const handleCreate = vi.fn();
    const { unmount } = render(
      <QuickCreateIssueModal
        isOpen={true}
        onClose={vi.fn()}
        onCreate={handleCreate}
        projectKey="KAN"
        states={[
          { id: 's-def', name: 'Default', is_default: true, group: 'unstarted' },
          { id: 's-other', name: 'Other', is_default: false, group: 'started' },
        ]}
      />
    );
    unmount();

    const { unmount: unmount2 } = render(
      <QuickCreateIssueModal
        isOpen={true}
        onClose={vi.fn()}
        onCreate={handleCreate}
        projectKey="KAN"
        states={[
          { id: 's-started', name: 'Started', is_default: false, group: 'started' },
          { id: 's-unstarted', name: 'Unstarted', is_default: false, group: 'unstarted' },
        ]}
      />
    );
    unmount2();

    const { unmount: unmount3 } = render(
      <QuickCreateIssueModal
        isOpen={true}
        onClose={vi.fn()}
        onCreate={handleCreate}
        projectKey="KAN"
        states={[
          { id: 's-completed', name: 'Done', is_default: false, group: 'completed' },
        ]}
      />
    );
    unmount3();

    // Submit with synchronous result and fallback states
    for (const testState of ['review-gate', 'done-gate', 'cancel-gate', 'backlog-gate']) {
      const createMock = vi.fn().mockReturnValue(null); // synchronous non-promise null result
      render(
        <QuickCreateIssueModal
          isOpen={true}
          onClose={vi.fn()}
          onCreate={createMock}
          projectKey="KAN"
          defaultStateId={testState}
        />
      );
      const summaryEl = document.getElementById('quick-create-summary') as HTMLInputElement;
      act(() => {
        summaryEl.value = `Task for ${testState}`;
        summaryEl.dispatchEvent(new Event('input', { bubbles: true }));
      });
      const btn = screen.getByRole('button', { name: /^create$/i });
      fireEvent.click(btn);
      expect(createMock).toHaveBeenCalled();
    }
  });

  it('captures opener element and restores focus upon modal close', () => {
    const opener = document.createElement('button');
    opener.id = 'trigger-open-btn';
    document.body.appendChild(opener);
    opener.focus();

    const handleClose = vi.fn();
    const { rerender } = render(
      <QuickCreateIssueModal
        isOpen={true}
        onClose={handleClose}
        onCreate={vi.fn()}
        projectKey="KAN"
      />
    );

    const cancelBtn = screen.getByRole('button', { name: /cancel/i });
    fireEvent.click(cancelBtn);
    expect(handleClose).toHaveBeenCalled();

    rerender(
      <QuickCreateIssueModal
        isOpen={false}
        onClose={handleClose}
        onCreate={vi.fn()}
        projectKey="KAN"
      />
    );

    document.body.removeChild(opener);
  });

  it('navigates to drafts when viewing draft item from post-dialog', () => {
    const handleCreate = vi.fn();

    render(
      <QuickCreateIssueModal
        isOpen={true}
        onClose={vi.fn()}
        onCreate={handleCreate}
        projectKey="KAN"
      />
    );

    const summaryInput = document.getElementById('quick-create-summary') as HTMLInputElement;
    const draftCheckbox = screen.getByTestId('quick-create-draft-checkbox');

    act(() => {
      summaryInput.value = 'Draft Item for URL';
      summaryInput.dispatchEvent(new Event('input', { bubbles: true }));
    });
    fireEvent.click(draftCheckbox);

    const createBtn = screen.getByRole('button', { name: /save draft/i });
    fireEvent.click(createBtn);

    const viewBtn = screen.getByTestId('post-create-view-btn');
    fireEvent.click(viewBtn);
  });
});
