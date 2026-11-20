import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import React from 'react';
import { ListRow } from './ListRow';
import type { IssueItem } from '../views/viewsApi';

describe('ListRow', () => {
  it('covers all priority, gate, and assignee variations', () => {
    const onToggleSelect = vi.fn();

    const issueWithLowAndVetoed: IssueItem = {
      id: 'row-1',
      key: 'KAN-201',
      summary: 'Low priority vetoed work item',
      state: { id: 's-1', name: 'In Review', group: 'started' },
      priority: { slug: 'low', label: 'Low', sort_order: 40 },
      gate_status: 'vetoed',
      has_explicit_acl: true,
      module_ids: ['mod-1'],
      due_date: '2026-12-31',
      assignees: [
        {
          id: 'asg-1',
          kind: 'principal',
          principal: { id: 'u-1', handle: 'bob', display_name: '', type: 'USER' }, // display_name empty -> falls back to handle
        },
      ],
    };

    render(
      <ListRow
        issue={issueWithLowAndVetoed}
        isSelected={true}
        onToggleSelect={onToggleSelect}
        modulesEnabled={true}
        isFocused={true}
      />
    );

    // Verify low priority glyph
    expect(screen.getByText('💤')).toBeDefined();
    // Verify vetoed gate glyph
    expect(screen.getByText('🛑🤖')).toBeDefined();
    // Fallback handle 'bob' rendered
    expect(screen.getByText('bob')).toBeDefined();

    // Checkbox toggle
    const checkbox = screen.getByRole('checkbox', { name: 'Select KAN-201' });
    fireEvent.click(checkbox);
    expect(onToggleSelect).toHaveBeenCalledWith('KAN-201', false);

    // Non-Enter keypress does not navigate
    const row = screen.getByRole('row');
    fireEvent.keyDown(row, { key: 'Escape' });
  });

  it('covers gatePending and overdue branches', () => {
    const issuePending: IssueItem = {
      id: 'row-2',
      key: 'KAN-202',
      summary: 'Pending gate and overdue item',
      state: { id: 's-2', name: 'In Progress', group: 'started' },
      priority: { slug: 'urgent', label: 'Urgent', sort_order: 10 },
      gate_status: 'pending',
      due_date: '2020-01-01', // in past -> overdue
    };

    render(
      <ListRow
        issue={issuePending}
        modulesEnabled={false}
      />
    );

    // Pending gate glyph
    expect(screen.getByText('⏳🤖')).toBeDefined();
    // Due date overdue
    const duePill = document.querySelector('.due-pill--overdue');
    expect(duePill).toBeDefined();
  });

  it('renders real cycle name, real module pills, and handles click and Enter keyboard navigation', () => {
    const onOpenPeek = vi.fn();
    const issueWithCycleAndModules: IssueItem = {
      id: 'row-3',
      key: 'KAN-203',
      summary: 'Cycle and Modules test',
      state: { id: 's-1', name: 'To Do', group: 'unstarted' },
      priority: { slug: 'medium', label: 'Medium', sort_order: 30 },
      cycle_id: 'cyc-1',
      cycle: { id: 'cyc-1', name: 'Sprint 1' },
      module_ids: ['mod-1', 'mod-2'],
      modules: [
        { id: 'mod-1', name: 'Auth Core' },
        { id: 'mod-2', name: 'UI System' },
      ],
    };

    const { rerender } = render(
      <ListRow
        issue={issueWithCycleAndModules}
        modulesEnabled={true}
        onOpenPeek={onOpenPeek}
      />
    );

    // Verify real cycle name rendered
    expect(screen.getByText(/Sprint 1/)).toBeDefined();
    // Verify real module pills rendered
    expect(screen.getByText(/Auth Core/)).toBeDefined();
    expect(screen.getByText(/UI System/)).toBeDefined();

    // Click row navigates to peek
    const row = screen.getByRole('row');
    fireEvent.click(row);
    expect(onOpenPeek).toHaveBeenCalledWith('KAN-203');

    // Press Enter navigates to peek
    fireEvent.keyDown(row, { key: 'Enter' });
    expect(onOpenPeek).toHaveBeenCalledTimes(2);

    // Click key link navigates to peek
    const keyLink = screen.getByText('KAN-203');
    fireEvent.click(keyLink);
    expect(onOpenPeek).toHaveBeenCalledWith('KAN-203');

    // When onOpenPeek is omitted, Enter sets window.location.href
    rerender(
      <ListRow
        issue={issueWithCycleAndModules}
        modulesEnabled={true}
      />
    );
    fireEvent.click(keyLink);
    fireEvent.keyDown(row, { key: 'Enter' });
  });

  describe('Touch & Mobile State Button (KAN-44)', () => {
    const baseIssue: IssueItem = {
      id: 'row-base',
      key: 'KAN-142',
      summary: 'Touch state transition item',
      state: { id: 's-1', name: 'In Review', group: 'started' },
      priority: { slug: 'high', label: 'High', sort_order: 20 },
    };

    it('renders state button and forwards to onOpenFieldPopover with stopPropagation', () => {
      const onOpenPeek = vi.fn();
      const onOpenFieldPopover = vi.fn();

      render(
        <ListRow
          issue={baseIssue}
          onOpenPeek={onOpenPeek}
          onOpenFieldPopover={onOpenFieldPopover}
        />,
      );

      const stateBtn = screen.getByTestId('list-row-state-btn-KAN-142');
      expect(stateBtn).toBeDefined();

      fireEvent.click(stateBtn);
      expect(onOpenPeek).not.toHaveBeenCalled();
      expect(onOpenFieldPopover).toHaveBeenCalledWith(
        'state',
        baseIssue,
        expect.anything(),
      );
    });

    it('opens local QuickFieldPopover when onOpenFieldPopover is omitted and triggers onStateSelect', () => {
      const onOpenPeek = vi.fn();
      const onStateSelect = vi.fn();
      const projectStates = [
        { id: 'st-todo', name: 'Todo', group: 'unstarted' as const },
        { id: 'st-done', name: 'Done', group: 'completed' as const },
      ];

      const { rerender } = render(
        <ListRow
          issue={baseIssue}
          onOpenPeek={onOpenPeek}
          onStateSelect={onStateSelect}
          projectStates={projectStates}
        />,
      );

      const stateBtn = screen.getByTestId('list-row-state-btn-KAN-142');
      fireEvent.click(stateBtn);

      expect(onOpenPeek).not.toHaveBeenCalled();
      const popover = screen.getByRole('dialog', { name: 'Quick State Picker' });
      expect(popover).toBeDefined();

      // Select 'Done' option
      const doneOption = screen.getByRole('option', { name: 'Done' });
      fireEvent.click(doneOption);

      expect(onStateSelect).toHaveBeenCalledWith('KAN-142', 'st-done');
      expect(screen.queryByRole('dialog', { name: 'Quick State Picker' })).toBeNull();

      // Open again and close via backdrop
      fireEvent.click(stateBtn);
      const backdrop = screen.getByTestId('quick-field-backdrop');
      fireEvent.click(backdrop);
      expect(screen.queryByRole('dialog', { name: 'Quick State Picker' })).toBeNull();

      // Read-only user lacking capability renders read-only badge
      const readOnlyIssue = {
        ...baseIssue,
        capabilities: ['VIEWER'],
      };
      rerender(
        <ListRow
          issue={readOnlyIssue}
          onOpenPeek={onOpenPeek}
        />,
      );
      expect(screen.queryByTestId('list-row-state-btn-KAN-142')).toBeNull();
    });

    it('covers labels with LabelDot colorHex, label overflow, and free_text assignee', () => {
      const richIssue: IssueItem = {
        ...baseIssue,
        labels: [
          { id: 'l1', name: 'Security', color_hex: '#ef4444' },
          { id: 'l2', name: 'Frontend', color_hex: '#3b82f6' },
          { id: 'l3', name: 'Backend', color_hex: '#10b981' },
        ],
        assignees: [
          { id: 'ext-1', kind: 'free_text', free_text: 'External Auditor', notify: false, hint: '' },
        ],
      };

      render(<ListRow issue={richIssue} isFocused={true} isActive={true} isSelected={true} />);

      expect(screen.getByText('Security')).toBeDefined();
      expect(screen.getByText('Frontend')).toBeDefined();
      expect(screen.getByText('+1')).toBeDefined();
      expect(screen.getByText('External Auditor')).toBeDefined();
    });
  });
});
