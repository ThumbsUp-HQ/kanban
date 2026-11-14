import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import React from 'react';
import { QuickCreateIssueModal } from './QuickCreateIssueModal';
import type { IssueItem } from './viewsApi';

describe('QuickCreateIssueModal (KB-P3-40, S6.4 item 4, S7.2 8f)', () => {
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

  it('renders summary, description, state, priority, and module fields when open', () => {
    const handleCreate = vi.fn();
    const handleClose = vi.fn();

    render(
      <QuickCreateIssueModal
        isOpen={true}
        onClose={handleClose}
        onCreate={handleCreate}
        projectKey="KAN"
        modulesEnabled={true}
      />
    );

    expect(screen.getByRole('dialog')).toBeDefined();
    expect(screen.getByLabelText(/summary/i)).toBeDefined();
    expect(screen.getByLabelText(/description/i)).toBeDefined();
    expect(screen.getByLabelText(/^state$/i)).toBeDefined();
    expect(screen.getByLabelText(/^priority$/i)).toBeDefined();
    expect(screen.getByLabelText(/^module$/i)).toBeDefined();

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
});
