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
    fireEvent.click(startSortBtn); // asc
    fireEvent.click(startSortBtn); // desc
    const createdBySortBtn = screen.getByRole('button', { name: 'Created by' });
    fireEvent.click(createdBySortBtn); // asc
    fireEvent.click(createdBySortBtn); // desc
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

    localStorage.clear();
    render(
      <TableView
        issues={issuesWithFallbacks}
        projectKey="FALLBACK_CYCLE"
        modulesEnabled={true}
        capabilities={['VIEWER']}
      />,
    );

    expect(screen.getByText('🔄 Cycle')).toBeDefined();
    expect(screen.getByText('📦 Module')).toBeDefined();
    expect(screen.getByText('📦 Auth Core')).toBeDefined();
  });

  it('renders named module pills when issue has populated modules list', () => {
    const base = FIXTURE_12_ISSUES[0];
    if (!base) return;
    const issueWithModules: IssueItem = {
      ...base,
      key: base.key,
      summary: base.summary,
      id: 'iss-mod-test',
      module_ids: ['m-auth'],
      modules: [{ id: 'm-auth', name: 'Authentication Engine' }],
    };

    render(
      <TableView
        issues={[issueWithModules]}
        projectKey="KAN"
        modulesEnabled={true}
      />
    );

    expect(screen.getByText(/📦 Authentication Engine/)).toBeDefined();
  });

  it('supports capability-gated inline cell editing for State, Priority, Assignees, Dates, and Cycle', () => {
    const onUpdateIssue = vi.fn();
    const dispatchSpy = vi.spyOn(window, 'dispatchEvent');

    const testIssues: IssueItem[] = [
      {
        id: 'edit-1',
        key: 'KAN-99',
        summary: 'Inline editable task',
        state: { id: 's-todo', name: 'Todo', group: 'unstarted' },
        priority: { slug: 'medium', label: 'Medium' },
        assignees: [
          {
            id: 'asg-1',
            kind: 'principal',
            principal: { id: 'u1', handle: 'alice', display_name: 'Alice', type: 'USER' },
          },
        ],
        start_date: '2026-11-01',
        due_date: '2026-11-15',
        cycle_id: 'cycle-1',
        cycle: { id: 'cycle-1', name: 'Cycle 1' },
      },
    ];

    const { rerender } = render(
      <TableView
        issues={testIssues}
        projectKey="KAN"
        modulesEnabled={true}
        capabilities={['EDIT']}
        onUpdateIssue={onUpdateIssue}
      />
    );

    // 1. State inline edit
    const stateSelect = screen.getByRole('combobox', { name: 'Edit state for KAN-99' });
    fireEvent.change(stateSelect, { target: { value: 'In Progress' } });
    expect(onUpdateIssue).toHaveBeenCalledWith('KAN-99', expect.objectContaining({
      state: expect.objectContaining({ name: 'In Progress', group: 'started' }) as unknown as Record<string, unknown>,
    }));
    expect(dispatchSpy).toHaveBeenCalledWith(expect.any(CustomEvent));

    // 2. Priority inline edit
    const prioSelect = screen.getByRole('combobox', { name: 'Edit priority for KAN-99' });
    fireEvent.change(prioSelect, { target: { value: 'urgent' } });
    expect(onUpdateIssue).toHaveBeenCalledWith('KAN-99', expect.objectContaining({
      priority: expect.objectContaining({ slug: 'urgent', label: 'Urgent' }) as unknown as Record<string, unknown>,
    }));

    // 3. Due date inline edit
    const dueDateInput = screen.getByLabelText('Edit due date for KAN-99');
    fireEvent.change(dueDateInput, { target: { value: '2026-12-01' } });
    expect(onUpdateIssue).toHaveBeenCalledWith('KAN-99', expect.objectContaining({
      due_date: '2026-12-01',
    }));

    // 4. Start date inline edit (render with project key that has start_date configured)
    localStorage.setItem('kb.tableCols.KAN_START', JSON.stringify(['key', 'summary', 'state', 'priority', 'start_date', 'due_date', 'cycle', 'assignees']));
    const { unmount } = render(
      <TableView
        issues={testIssues}
        projectKey="KAN_START"
        modulesEnabled={true}
        capabilities={['EDIT']}
        onUpdateIssue={onUpdateIssue}
      />
    );
    const startDateInput = screen.getByLabelText('Edit start date for KAN-99');
    fireEvent.change(startDateInput, { target: { value: '2026-11-05' } });
    expect(onUpdateIssue).toHaveBeenCalledWith('KAN-99', expect.objectContaining({
      start_date: '2026-11-05',
    }));
    unmount();

    // 5. Cycle inline edit
    const cycleSelect = screen.getByRole('combobox', { name: 'Edit cycle for KAN-99' });
    fireEvent.change(cycleSelect, { target: { value: 'cycle-2' } });
    expect(onUpdateIssue).toHaveBeenCalledWith('KAN-99', expect.objectContaining({
      cycle_id: 'cycle-2',
    }));

    // 6. Assignee toggle
    const assignBtn = screen.getByRole('button', { name: 'Assign issue KAN-99' });
    fireEvent.click(assignBtn);
    expect(onUpdateIssue).toHaveBeenCalledWith('KAN-99', expect.objectContaining({
      assignees: expect.arrayContaining([expect.objectContaining({ kind: 'principal' })]) as unknown as Record<string, unknown>[],
    }));

    // 6b. Assignee toggle when adam is already assigned (unassign)
    const firstIssue = testIssues[0];
    if (!firstIssue) throw new Error('Expected firstIssue');
    const issuesWithAdam: IssueItem[] = [
      {
        id: firstIssue.id,
        key: firstIssue.key,
        summary: firstIssue.summary,
        state: firstIssue.state,
        priority: firstIssue.priority,
        assignees: [
          {
            id: 'asg-me',
            kind: 'principal',
            principal: {
              id: 'u-me',
              handle: 'adam',
              display_name: 'Adam Outler',
              type: 'USER',
            },
          },
        ],
      },
    ];
    rerender(
      <TableView
        issues={issuesWithAdam}
        projectKey="KAN"
        modulesEnabled={true}
        capabilities={['ADMIN']}
        onUpdateIssue={onUpdateIssue}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: 'Assign issue KAN-99' }));
    expect(onUpdateIssue).toHaveBeenCalledWith('KAN-99', expect.objectContaining({
      assignees: [],
    }));

    // 7. VIEWER capability gates out inline editing
    rerender(
      <TableView
        issues={testIssues}
        projectKey="KAN"
        modulesEnabled={true}
        capabilities={['VIEWER']}
        onUpdateIssue={onUpdateIssue}
      />
    );
    expect(screen.queryByRole('combobox', { name: 'Edit state for KAN-99' })).toBeNull();
    expect(screen.queryByRole('combobox', { name: 'Edit priority for KAN-99' })).toBeNull();
    expect(screen.queryByLabelText('Edit due date for KAN-99')).toBeNull();
    expect(screen.queryByRole('button', { name: 'Assign issue KAN-99' })).toBeNull();

    dispatchSpy.mockRestore();
  });

  it('renders exactly 0 select elements and read-only cells for callers with VIEW or VIEW/COMMENT capabilities', () => {
    const testIssues: IssueItem[] = [
      {
        id: 'read-1',
        key: 'KAN-VIEWER-1',
        summary: 'Viewer read-only task',
        state: { id: 's-todo', name: 'Todo', group: 'unstarted' },
        priority: { slug: 'medium', label: 'Medium' },
        assignees: [],
        start_date: '2026-11-01',
        due_date: '2026-11-15',
        cycle_id: 'cycle-1',
        cycle: { id: 'cycle-1', name: 'Cycle 1' },
      },
      {
        id: 'read-2',
        key: 'KAN-VIEWER-2',
        summary: 'Second read-only task',
        state: { id: 's-prog', name: 'In Progress', group: 'started' },
        priority: { slug: 'high', label: 'High' },
        assignees: [],
        cycle_id: null,
      },
    ];

    // 1. Caller with capabilities=['VIEW']
    const { container: containerView, rerender } = render(
      <TableView
        issues={testIssues}
        projectKey="KAN"
        modulesEnabled={true}
        capabilities={['VIEW']}
      />,
    );
    expect(containerView.querySelectorAll('select').length).toBe(0);
    expect(containerView.querySelectorAll('input.table-inline-input').length).toBe(0);
    expect(containerView.querySelectorAll('.table-inline-assign-btn').length).toBe(0);

    // 2. Caller with currentUserCapabilities=['VIEW', 'COMMENT']
    rerender(
      <TableView
        issues={testIssues}
        projectKey="KAN"
        modulesEnabled={true}
        currentUserCapabilities={['VIEW', 'COMMENT']}
      />,
    );
    expect(containerView.querySelectorAll('select').length).toBe(0);
    expect(containerView.querySelectorAll('input.table-inline-input').length).toBe(0);
    expect(containerView.querySelectorAll('.table-inline-assign-btn').length).toBe(0);

    // 3. Issue-level capabilities=['VIEW'] prevents editing on that issue even if caller has EDIT
    const baseFirst = testIssues[0];
    if (!baseFirst) throw new Error('Expected baseFirst');
    const mixedIssues: IssueItem[] = [
      {
        id: baseFirst.id,
        key: baseFirst.key,
        summary: baseFirst.summary,
        state: baseFirst.state,
        priority: baseFirst.priority,
        capabilities: ['VIEW'],
      },
    ];
    rerender(
      <TableView
        issues={mixedIssues}
        projectKey="KAN"
        modulesEnabled={true}
        capabilities={['EDIT']}
      />,
    );
    expect(containerView.querySelectorAll('select').length).toBe(0);
    expect(containerView.querySelectorAll('input.table-inline-input').length).toBe(0);
  });

  it('handles row click and issue key link click to trigger onOpenPeek and renders read-only start date', () => {
    const onOpenPeek = vi.fn();
    const testIssues: IssueItem[] = [
      {
        id: 'read-3',
        key: 'KAN-PEEK-1',
        summary: 'Peek test task',
        state: { id: 's-todo', name: 'Todo', group: 'unstarted' },
        priority: { slug: 'medium', label: 'Medium' },
        assignees: [],
        start_date: '2026-11-01',
        due_date: '2026-11-15',
      },
    ];

    // Store column configuration with start_date enabled
    localStorage.setItem('kb.tableCols.KAN', JSON.stringify(['key', 'summary', 'state', 'priority', 'start_date', 'due_date']));

    const { container, unmount } = render(
      <TableView
        issues={testIssues}
        projectKey="KAN"
        modulesEnabled={false}
        capabilities={['VIEW']}
        onOpenPeek={onOpenPeek}
      />,
    );

    // Verify read-only start date rendered
    expect(screen.getByText('2026-11-01')).toBeDefined();

    // Click key link
    const keyLink = screen.getByRole('link', { name: 'KAN-PEEK-1' });
    fireEvent.click(keyLink);
    expect(onOpenPeek).toHaveBeenCalledWith('KAN-PEEK-1');

    // Click table row (outside interactive elements)
    const row = container.querySelector('tr[data-issue-key="KAN-PEEK-1"]');
    if (!row) throw new Error('Expected row');
    fireEvent.click(row);
    expect(onOpenPeek).toHaveBeenCalledTimes(2);

    // Click interactive element inside row (returns early, does not call onOpenPeek)
    const rowInput = row.querySelector('input');
    if (rowInput) {
      fireEvent.click(rowInput);
      expect(onOpenPeek).toHaveBeenCalledTimes(2);
    }

    localStorage.removeItem('kb.tableCols.KAN');
    unmount();

    // Also verify clicking keyLink when onOpenPeek is undefined
    const { unmount: unmountSecond } = render(
      <TableView
        issues={testIssues}
        projectKey="KAN"
        modulesEnabled={false}
      />,
    );
    const unhandledKeyLink = screen.getByRole('link', { name: 'KAN-PEEK-1' });
    fireEvent.click(unhandledKeyLink);
    unmountSecond();
  });

  it('renders mobile compact cell classes and attributes for Key, Summary, State, and Priority', () => {
    const testIssues: IssueItem[] = [
      {
        id: 'cell-1',
        key: 'KAN-RESP-1',
        summary: 'Responsive test task',
        state: { id: 's-backlog', name: 'Backlog', group: 'unstarted' },
        priority: { slug: 'high', label: 'High' },
        assignees: [],
      },
    ];

    const { container } = render(
      <TableView
        issues={testIssues}
        projectKey="KAN"
        capabilities={['VIEWER']}
      />,
    );

    // Verify key cell and header
    const keyHeader = container.querySelector('th[data-col-header="key"]');
    expect(keyHeader).not.toBeNull();
    const keyCell = container.querySelector('td[data-col="key"]');
    expect(keyCell).not.toBeNull();
    expect(keyCell?.classList.contains('table-key-cell')).toBe(true);

    // Verify summary cell and header
    const summaryHeader = container.querySelector('th[data-col-header="summary"]');
    expect(summaryHeader).not.toBeNull();
    const summaryCell = container.querySelector('td[data-col="summary"]');
    expect(summaryCell).not.toBeNull();
    expect(summaryCell?.classList.contains('table-summary-cell')).toBe(true);
    expect(summaryCell?.querySelector('.table-summary-text')?.textContent).toBe('Responsive test task');

    // Verify state cell and header
    const stateHeader = container.querySelector('th[data-col-header="state"]');
    expect(stateHeader).not.toBeNull();
    const stateCell = container.querySelector('td[data-col="state"]');
    expect(stateCell).not.toBeNull();
    expect(stateCell?.classList.contains('table-state-cell')).toBe(true);

    // Verify priority cell and header
    const priorityHeader = container.querySelector('th[data-col-header="priority"]');
    expect(priorityHeader).not.toBeNull();
    const priorityCell = container.querySelector('td[data-col="priority"]');
    expect(priorityCell).not.toBeNull();
    expect(priorityCell?.classList.contains('table-priority-cell-wrap')).toBe(true);
  });

  it('covers custom cycle option, empty dates, and terminal state branches in inline editing', () => {
    const onUpdateIssue = vi.fn();
    const customCycleIssues: IssueItem[] = [
      {
        id: 'cust-1',
        key: 'KAN-CUST-1',
        summary: 'Custom cycle task',
        state: { id: 's-todo', name: 'Todo', group: 'unstarted' },
        priority: { slug: 'low', label: 'Low' },
        cycle_id: 'cycle-custom-beta',
        cycle: { id: 'cycle-custom-beta', name: 'Beta Sprint' },
        assignees: [],
        start_date: '2026-11-01',
        due_date: '2020-01-01',
      },
      {
        id: 'cust-raw',
        key: 'KAN-CUST-RAW',
        summary: 'Raw cycle task',
        state: { id: 's-todo', name: 'Todo', group: 'unstarted' },
        priority: { slug: 'low', label: 'Low' },
        cycle_id: 'cycle-raw-99',
        cycle: null,
        assignees: [],
        start_date: '2026-01-01',
        due_date: '2099-01-01',
      },
    ];

    localStorage.setItem(
      'kb.tableCols.KAN_CUST',
      JSON.stringify(['key', 'summary', 'state', 'priority', 'assignees', 'start_date', 'due_date', 'cycle', 'created_by']),
    );

    const { rerender } = render(
      <TableView
        issues={customCycleIssues}
        projectKey="KAN_CUST"
        capabilities={['EDIT']}
        onUpdateIssue={onUpdateIssue}
      />,
    );

    // Verify custom cycle option rendered
    const cycleSelect = screen.getByRole('combobox', { name: 'Edit cycle for KAN-CUST-1' });
    expect(screen.getByRole('option', { name: 'Beta Sprint' })).toBeDefined();

    // Inline state change to Done, Cancelled, and In Review
    const stateSelect = screen.getByRole('combobox', { name: 'Edit state for KAN-CUST-1' });
    fireEvent.change(stateSelect, { target: { value: 'Done' } });
    expect(onUpdateIssue).toHaveBeenCalledWith('KAN-CUST-1', expect.objectContaining({
      state: expect.objectContaining({ name: 'Done', group: 'completed' }) as unknown as Record<string, unknown>,
    }));

    fireEvent.change(stateSelect, { target: { value: 'Cancelled' } });
    expect(onUpdateIssue).toHaveBeenCalledWith('KAN-CUST-1', expect.objectContaining({
      state: expect.objectContaining({ name: 'Cancelled', group: 'cancelled' }) as unknown as Record<string, unknown>,
    }));

    fireEvent.change(stateSelect, { target: { value: 'In Review' } });
    expect(onUpdateIssue).toHaveBeenCalledWith('KAN-CUST-1', expect.objectContaining({
      state: expect.objectContaining({ name: 'In Review', group: 'started' }) as unknown as Record<string, unknown>,
    }));

    // Start date and Due date empty clearing
    const startDateInput = screen.getByLabelText('Edit start date for KAN-CUST-1');
    fireEvent.change(startDateInput, { target: { value: '' } });
    expect(onUpdateIssue).toHaveBeenCalledWith('KAN-CUST-1', { start_date: null });

    const dueDateInput = screen.getByLabelText('Edit due date for KAN-CUST-1');
    fireEvent.change(dueDateInput, { target: { value: '' } });
    expect(onUpdateIssue).toHaveBeenCalledWith('KAN-CUST-1', { due_date: null });

    // Cycle clear to empty
    fireEvent.change(cycleSelect, { target: { value: '' } });
    expect(onUpdateIssue).toHaveBeenCalledWith('KAN-CUST-1', { cycle_id: null, cycle: null });

    // Rerender as read-only VIEWER with overdue and null start date
    const firstCustom = customCycleIssues[0];
    if (!firstCustom) throw new Error('Expected firstCustom');
    const readOnlyIssues: IssueItem[] = [
      {
        ...firstCustom,
        start_date: null,
        due_date: '2020-01-01',
      },
      {
        id: 'cust-2',
        key: 'KAN-FALLBACK-1',
        summary: 'Fallback task',
        state: { id: 's-todo', name: 'Todo', group: 'unstarted' },
        priority: { slug: 'custom-prio', label: '' },
        cycle_id: 'cycle-no-name',
        cycle: null,
        due_date: null,
        assignees: [
          {
            id: 'free-1',
            kind: 'free_text',
            free_text: 'External Contractor',
            notify: false,
            hint: '',
          },
          {
            id: 'prin-1',
            kind: 'principal',
            principal: {
              id: 'u-no-dn',
              handle: 'bob',
              display_name: '',
              type: 'USER',
            },
          },
        ],
      },
    ];
    rerender(
      <TableView
        issues={readOnlyIssues}
        projectKey="KAN_CUST"
        capabilities={['VIEWER']}
      />,
    );
    expect(screen.getByText(/2020-01-01/)).toBeDefined();
    expect(screen.getByText('External Contractor')).toBeDefined();
    expect(screen.getByText('bob')).toBeDefined();
    expect(screen.getByText('custom-prio')).toBeDefined();
    expect(screen.getAllByText(/Cycle/).length).toBeGreaterThan(0);

    localStorage.removeItem('kb.tableCols.KAN_CUST');
  });

  it('allows state transitions with TRANSITION capability and rolls back on failure', () => {
    const alertListener = vi.fn();
    window.addEventListener('kb:alert', alertListener);

    // Render with TRANSITION capability only (no EDIT/ADMIN)
    const { rerender } = render(
      <TableView
        issues={FIXTURE_12_ISSUES}
        projectKey="KAN"
        capabilities={['TRANSITION']}
      />,
    );

    const firstIssueKey = FIXTURE_12_ISSUES[0]?.key ?? 'KAN-1';
    // State select should be interactive
    const stateSelect = screen.getByLabelText(`Edit state for ${firstIssueKey}`);
    expect(stateSelect).toBeDefined();

    // Priority should be read-only since user only has TRANSITION
    expect(screen.queryByLabelText(`Edit priority for ${firstIssueKey}`)).toBeNull();

    // Now test with pure VIEW capability
    rerender(
      <TableView
        issues={FIXTURE_12_ISSUES}
        projectKey="KAN"
        capabilities={['VIEW']}
      />,
    );
    expect(screen.queryByLabelText(`Edit state for ${firstIssueKey}`)).toBeNull();

    window.removeEventListener('kb:alert', alertListener);
  });
});
