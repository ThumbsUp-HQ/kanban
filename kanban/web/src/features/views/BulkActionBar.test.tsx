import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import React from 'react';
import { BulkActionBar } from './BulkActionBar';
import { FIXTURE_12_ISSUES } from './fixtures';

describe('BulkActionBar (KB-P3-40, S6.4 item 3, S7.2 8p, S7.2 8f)', () => {
  it('does not render when selectedKeys is empty', () => {
    const { container } = render(
      <BulkActionBar
        selectedKeys={[]}
        issues={FIXTURE_12_ISSUES}
        onClearSelection={vi.fn()}
      />
    );

    expect(container.firstChild).toBeNull();
  });

  it('renders count, action buttons, and handles clear selection', () => {
    const handleClear = vi.fn();
    const handleUpdateState = vi.fn();

    render(
      <BulkActionBar
        selectedKeys={['KAN-140', 'KAN-141']}
        issues={FIXTURE_12_ISSUES}
        onClearSelection={handleClear}
        onBatchUpdateState={handleUpdateState}
        modulesEnabled={true}
      />
    );

    expect(screen.getByText('2 selected')).toBeDefined();
    expect(screen.getByRole('toolbar', { name: /bulk actions/i })).toBeDefined();

    const clearBtn = screen.getByRole('button', { name: /clear selection/i });
    fireEvent.click(clearBtn);
    expect(handleClear).toHaveBeenCalled();

    const stateBtns = screen.getAllByRole('button', { name: /^state$/i });
    expect(stateBtns).toHaveLength(1);
    const priorityBtns = screen.getAllByRole('button', { name: /^priority$/i });
    expect(priorityBtns).toHaveLength(1);
    const stateBtn = stateBtns[0];
    if (!stateBtn) throw new Error('missing State button');
    fireEvent.click(stateBtn);
    expect(handleUpdateState).toHaveBeenCalledWith('done');
  });

  it('disables Delete button when any selected issue lacks DELETE or ADMIN capability', () => {
    const firstIssue = FIXTURE_12_ISSUES[0];
    if (!firstIssue) throw new Error('missing fixture');
    const issuesWithCaps = [
      {
        ...firstIssue,
        key: 'KAN-VIEW',
        capabilities: ['VIEW'],
      },
    ];

    render(
      <BulkActionBar
        selectedKeys={['KAN-VIEW']}
        issues={issuesWithCaps}
        onClearSelection={vi.fn()}
        onBatchDelete={vi.fn()}
      />
    );

    expect(screen.queryByRole('button', { name: /delete/i })).toBeNull();
  });

  it('archive rule: disabled with tooltip/reason when 1 of 3 selected items is In Progress (Test Case 4, S7.2 8p)', () => {
    // KAN-142 is In Progress ('started'), KAN-148 is Done ('completed'), KAN-150 is Cancelled ('cancelled')
    const selectedKeys = ['KAN-142', 'KAN-148', 'KAN-150'];
    const handleArchive = vi.fn();

    render(
      <BulkActionBar
        selectedKeys={selectedKeys}
        issues={FIXTURE_12_ISSUES}
        onClearSelection={vi.fn()}
        onBatchArchive={handleArchive}
      />
    );

    const archiveBtn = screen.getByRole('button', { name: /archive/i });
    expect(archiveBtn.getAttribute('disabled')).toBeDefined();
    expect(archiveBtn.getAttribute('data-reason')).toBe(
      'Only completed or canceled work items can be archived'
    );
    expect(archiveBtn.getAttribute('title')).toBe(
      'Only completed or canceled work items can be archived'
    );

    fireEvent.click(archiveBtn);
    expect(handleArchive).not.toHaveBeenCalled();
  });

  it('archive rule: enabled when all selected items are completed or cancelled (Test Case 4)', () => {
    // KAN-148 is Done, KAN-149 is Done, KAN-150 is Cancelled
    const selectedKeys = ['KAN-148', 'KAN-149', 'KAN-150'];
    const handleArchive = vi.fn();

    render(
      <BulkActionBar
        selectedKeys={selectedKeys}
        issues={FIXTURE_12_ISSUES}
        onClearSelection={vi.fn()}
        onBatchArchive={handleArchive}
      />
    );

    const archiveBtn = screen.getByRole('button', { name: /archive/i });
    expect(archiveBtn.hasAttribute('disabled')).toBe(false);
    expect(archiveBtn.getAttribute('title')).toBe('Archive selected items');

    fireEvent.click(archiveBtn);
    expect(handleArchive).toHaveBeenCalled();
  });

  it('announces cap warning when selection reaches 100 items (Test Case 4)', () => {
    const hundredKeys = Array.from({ length: 100 }, (_, i) => `KAN-${String(i + 1)}`);

    render(
      <BulkActionBar
        selectedKeys={hundredKeys}
        issues={FIXTURE_12_ISSUES}
        onClearSelection={vi.fn()}
      />
    );

    expect(screen.getByText('100 selected')).toBeDefined();
    expect(
      screen.getByText('Bulk selection is capped at 100 work items')
    ).toBeDefined();
  });

  it('omits Module button when modulesEnabled is false (Test Case 3, S7.2 8f)', () => {
    render(
      <BulkActionBar
        selectedKeys={['KAN-142']}
        issues={FIXTURE_12_ISSUES}
        onClearSelection={vi.fn()}
        modulesEnabled={false}
      />
    );

    expect(screen.queryByRole('button', { name: /^module$/i })).toBeNull();
  });

  it('triggers all batch operations when buttons are clicked', () => {
    const handleUpdateState = vi.fn();
    const handleUpdatePriority = vi.fn();
    const handleUpdateAssignees = vi.fn();
    const handleUpdateLabels = vi.fn();
    const handleUpdateCycle = vi.fn();
    const handleUpdateModule = vi.fn();

    render(
      <BulkActionBar
        selectedKeys={['KAN-140']}
        issues={FIXTURE_12_ISSUES}
        onClearSelection={vi.fn()}
        onBatchUpdateState={handleUpdateState}
        onBatchUpdatePriority={handleUpdatePriority}
        onBatchUpdateAssignees={handleUpdateAssignees}
        onBatchUpdateLabels={handleUpdateLabels}
        onBatchUpdateCycle={handleUpdateCycle}
        onBatchUpdateModule={handleUpdateModule}
        modulesEnabled={true}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: /^state$/i }));
    expect(handleUpdateState).toHaveBeenCalledWith('done');

    fireEvent.click(screen.getByRole('button', { name: /^priority$/i }));
    expect(handleUpdatePriority).toHaveBeenCalledWith('urgent');

    fireEvent.click(screen.getByRole('button', { name: /^assignees$/i }));
    expect(handleUpdateAssignees).toHaveBeenCalledWith(['alice']);

    fireEvent.click(screen.getByRole('button', { name: /^labels$/i }));
    expect(handleUpdateLabels).toHaveBeenCalledWith(['lbl-sec']);

    fireEvent.click(screen.getByRole('button', { name: /^cycle$/i }));
    expect(handleUpdateCycle).toHaveBeenCalledWith('cycle-1');

    fireEvent.click(screen.getByRole('button', { name: /^module$/i }));
    expect(handleUpdateModule).toHaveBeenCalledWith(['mod-1']);
  });

  it('triggers onBatchDelete prop directly when provided', () => {
    const handleDelete = vi.fn();
    render(
      <BulkActionBar
        selectedKeys={['KAN-140']}
        issues={FIXTURE_12_ISSUES}
        onClearSelection={vi.fn()}
        onBatchDelete={handleDelete}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: /^delete$/i }));
    expect(handleDelete).toHaveBeenCalled();
  });

  it('opens and confirms delete via modal when onBatchDelete is not provided', () => {
    const handleClear = vi.fn();
    render(
      <BulkActionBar
        selectedKeys={['KAN-140']}
        issues={FIXTURE_12_ISSUES}
        onClearSelection={handleClear}
      />
    );

    // Open modal
    fireEvent.click(screen.getByRole('button', { name: /^delete$/i }));
    expect(screen.getByRole('dialog', { name: /delete 1 work items\?/i })).toBeDefined();

    // Cancel modal
    fireEvent.click(screen.getByRole('button', { name: /cancel/i }));
    expect(screen.queryByRole('dialog')).toBeNull();

    // Re-open and confirm
    fireEvent.click(screen.getByRole('button', { name: /^delete$/i }));
    fireEvent.click(screen.getByRole('button', { name: /confirm delete/i }));
    expect(handleClear).toHaveBeenCalled();
  });
});
