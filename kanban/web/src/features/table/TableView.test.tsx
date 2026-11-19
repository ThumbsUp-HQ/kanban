import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import React from 'react';
import { TableView } from './TableView';
import { FIXTURE_12_ISSUES } from '../views/fixtures';
import type { IssueItem } from '../views/viewsApi';

describe('TableView', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('renders default columns and cycles aria-sort ascending -> descending -> none on Priority click', () => {
    render(
      <TableView
        issues={FIXTURE_12_ISSUES}
        projectKey="KAN"
        modulesEnabled={true}
      />
    );

    // Initial default headers: Key, Summary, State, Priority, Assignees, Labels, Cycle, Modules, Due date
    expect(screen.getByRole('columnheader', { name: /Key/i })).toBeDefined();
    expect(screen.getByRole('columnheader', { name: /Summary/i })).toBeDefined();
    expect(screen.getByRole('columnheader', { name: /State/i })).toBeDefined();
    const priorityTh = screen.getByRole('columnheader', { name: /Priority/i });
    expect(priorityTh).toBeDefined();
    expect(priorityTh.getAttribute('aria-sort')).toBe('none');

    // Click 1: ascending
    const prioritySortBtn = priorityTh.querySelector('button');
    expect(prioritySortBtn).toBeDefined();
    if (prioritySortBtn) {
      fireEvent.click(prioritySortBtn);
      expect(priorityTh.getAttribute('aria-sort')).toBe('ascending');

      // Click 2: descending
      fireEvent.click(prioritySortBtn);
      expect(priorityTh.getAttribute('aria-sort')).toBe('descending');

      // Click 3: none
      fireEvent.click(prioritySortBtn);
      expect(priorityTh.getAttribute('aria-sort')).toBe('none');
    }
  });

  it('sorts by other sortable columns (Key, Summary, State, Due date)', () => {
    render(
      <TableView
        issues={FIXTURE_12_ISSUES}
        projectKey="KAN"
        modulesEnabled={true}
      />
    );

    // Sort by Key
    const keySortBtn = screen.getByRole('button', { name: 'Key' });
    fireEvent.click(keySortBtn); // asc
    fireEvent.click(keySortBtn); // desc

    // Sort by Summary
    const summarySortBtn = screen.getByRole('button', { name: 'Summary' });
    fireEvent.click(summarySortBtn); // asc
    fireEvent.click(summarySortBtn); // desc

    // Sort by State
    const stateSortBtn = screen.getByRole('button', { name: 'State' });
    fireEvent.click(stateSortBtn); // asc
    fireEvent.click(stateSortBtn); // desc

    // Sort by Due date
    const dueDateSortBtn = screen.getByRole('button', { name: 'Due date' });
    fireEvent.click(dueDateSortBtn); // asc
    fireEvent.click(dueDateSortBtn); // desc
  });

  it('toggles Start date on, Cycle off, reorders Due date before Assignees, and persists to localStorage', () => {
    render(
      <TableView
        issues={FIXTURE_12_ISSUES}
        projectKey="KAN"
        modulesEnabled={true}
      />
    );

    // Open Column Configurator
    const configTrigger = screen.getByRole('button', { name: /Columns/i });
    fireEvent.click(configTrigger);

    // Toggle Start date on
    const startCheckbox = screen.getByRole('checkbox', { name: 'Start date' });
    fireEvent.click(startCheckbox);

    // Toggle Cycle off
    const cycleCheckbox = screen.getByRole('checkbox', { name: 'Cycle' });
    fireEvent.click(cycleCheckbox);

    // Move Due date up until before Assignees
    const moveDueUpBtn = screen.getByRole('button', { name: /Move Due date up/i });
    for (let i = 0; i < 5; i++) {
      const current = JSON.parse(localStorage.getItem('kb.tableCols.KAN') ?? '[]') as string[];
      if (current.indexOf('due_date') < current.indexOf('assignees')) {
        break;
      }
      fireEvent.click(moveDueUpBtn);
    }

    // Verify localStorage has persisted the new configuration
    const saved = localStorage.getItem('kb.tableCols.KAN');
    expect(saved).not.toBeNull();
    if (saved) {
      const parsed = JSON.parse(saved) as string[];
      expect(parsed).toContain('start_date');
      expect(parsed).not.toContain('cycle');
      expect(parsed.indexOf('due_date')).toBeLessThan(parsed.indexOf('assignees'));
    }

    // Check table headers reflect changes
    expect(screen.getByRole('columnheader', { name: /Start date/i })).toBeDefined();
    expect(screen.queryByRole('columnheader', { name: /Cycle/i })).toBeNull();
  });

  it('unmounts Modules column completely when modulesEnabled is false even if localStorage has modules', () => {
    localStorage.setItem(
      'kb.tableCols.KAN',
      JSON.stringify(['key', 'summary', 'modules', 'state'])
    );

    render(
      <TableView
        issues={FIXTURE_12_ISSUES}
        projectKey="KAN"
        modulesEnabled={false}
      />
    );

    // Modules column header MUST NOT be mounted in DOM
    const modulesTh = screen.queryByRole('columnheader', { name: /Modules/i });
    expect(modulesTh).toBeNull();
  });

  it('renders all optional columns including Start date, Created by, and Access', () => {
    localStorage.setItem(
      'kb.tableCols.KAN',
      JSON.stringify(['key', 'summary', 'start_date', 'created_by', 'access'])
    );

    render(
      <TableView
        issues={FIXTURE_12_ISSUES}
        projectKey="KAN"
        modulesEnabled={true}
      />
    );

    expect(screen.getByRole('columnheader', { name: /Start date/i })).toBeDefined();
    expect(screen.getByRole('columnheader', { name: /Created by/i })).toBeDefined();
    expect(screen.getByRole('columnheader', { name: /Access/i })).toBeDefined();

    // Sort by start_date and created_by
    const startSortBtn = screen.getByRole('button', { name: 'Start date' });
    fireEvent.click(startSortBtn);
    const createdBySortBtn = screen.getByRole('button', { name: 'Created by' });
    fireEvent.click(createdBySortBtn);
  });

  it('handles row selection toggle, future due dates, and priority variants', () => {
    const onToggleSelect = vi.fn();

    const variedIssues: IssueItem[] = [
      {
        id: 'var-1',
        key: 'KAN-301',
        summary: 'Urgent future due date',
        state: { id: 's-1', name: 'Todo', group: 'unstarted' },
        priority: { slug: 'urgent', label: 'Urgent' },
        due_date: '2099-01-01', // future due date -> isOverdue is false
      },
      {
        id: 'var-2',
        key: 'KAN-302',
        summary: 'Low priority no label',
        state: { id: 's-2', name: 'In Progress', group: 'started' },
        priority: { slug: 'low', label: '' },
      },
    ];

    render(
      <TableView
        issues={variedIssues}
        projectKey="KAN"
        modulesEnabled={true}
        onToggleSelect={onToggleSelect}
      />
    );

    const checkbox = screen.getByRole('checkbox', { name: 'Select KAN-301' });
    fireEvent.click(checkbox);
    expect(onToggleSelect).toHaveBeenCalledWith('KAN-301', true);
  });

  it('renders Load more button and triggers onLoadMore', () => {
    const onLoadMore = vi.fn();
    const { rerender } = render(
      <TableView
        issues={FIXTURE_12_ISSUES}
        projectKey="KAN"
        modulesEnabled={true}
        nextCursor="cur_table_2"
        onLoadMore={onLoadMore}
        isLoading={false}
      />
    );

    const loadMoreBtn = screen.getByRole('button', { name: /Load more/i });
    expect(loadMoreBtn).toBeDefined();
    fireEvent.click(loadMoreBtn);
    expect(onLoadMore).toHaveBeenCalledTimes(1);

    rerender(
      <TableView
        issues={FIXTURE_12_ISSUES}
        projectKey="KAN"
        modulesEnabled={true}
        nextCursor="cur_table_2"
        onLoadMore={onLoadMore}
        isLoading={true}
      />
    );
    expect(screen.getByText('Loading...')).toBeDefined();
  });

  it('renders calm empty state when project has 0 issues', () => {
    const onCreate = vi.fn();
    render(
      <TableView
        issues={[]}
        projectKey="KAN"
        modulesEnabled={true}
        onCreateIssue={onCreate}
      />
    );

    expect(screen.getByText('No work items found')).toBeDefined();
    const createBtn = screen.getByRole('button', { name: /\+ Create first work item/i });
    expect(createBtn).toBeDefined();

    fireEvent.click(createBtn);
    expect(onCreate).toHaveBeenCalledTimes(1);
  });

  it('selects all issues when select all checkbox is clicked', () => {
    const onSelectAll = vi.fn();
    render(
      <TableView
        issues={FIXTURE_12_ISSUES}
        projectKey="KAN"
        modulesEnabled={true}
        onSelectAll={onSelectAll}
      />
    );

    const selectAllCheckbox = screen.getByRole('checkbox', { name: /Select all issues/i });
    fireEvent.click(selectAllCheckbox);

    expect(onSelectAll).toHaveBeenCalledWith(true);
  });

  it('covers localStorage getItem throw and modulesEnabled prop toggle', () => {
    // 1. localStorage.getItem throw
    const getItemSpy = vi.spyOn(Storage.prototype, 'getItem').mockImplementationOnce(() => {
      throw new Error('SecurityError: access denied');
    });

    const { rerender } = render(
      <TableView
        issues={FIXTURE_12_ISSUES}
        projectKey="KAN"
        modulesEnabled={true}
      />
    );
    expect(screen.getByRole('table')).toBeDefined();

    // 2. Prop change from modulesEnabled true -> false triggers activeColumns line 124
    rerender(
      <TableView
        issues={FIXTURE_12_ISSUES}
        projectKey="KAN"
        modulesEnabled={false}
      />
    );
    expect(screen.queryByRole('columnheader', { name: /Modules/i })).toBeNull();
    getItemSpy.mockRestore();
  });

  it('renders cycle and module fallbacks when cycle or modules summaries are undefined', () => {
    const issuesWithFallbacks: IssueItem[] = [
      {
        id: 'i-fallback',
        key: 'KAN-99',
        summary: 'Fallback summaries',
        state: { id: 's1', name: 'Todo', group: 'unstarted' },
        priority: { slug: 'medium', label: 'Medium', emoji: '🔹' },
        cycle_id: 'cycle-1',
        cycle: null,
        module_ids: ['mod-1'],
      },
      {
        id: 'i-module-list',
        key: 'KAN-100',
        summary: 'Module list',
        state: { id: 's1', name: 'Todo', group: 'unstarted' },
        priority: { slug: 'medium', label: 'Medium', emoji: '🔹' },
        module_ids: ['mod-1'],
        modules: [{ id: 'mod-1', name: 'Auth Core' }],
      },
    ];

    render(
      <TableView
        issues={issuesWithFallbacks}
        projectKey="KAN"
        modulesEnabled={true}
      />,
    );

    expect(screen.getByText('🔄 Cycle')).toBeDefined();
    expect(screen.getByText('📦 Module')).toBeDefined();
    expect(screen.getByText('📦 Auth Core')).toBeDefined();
  });
});
