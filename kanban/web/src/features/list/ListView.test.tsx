import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, act, within } from '@testing-library/react';
import React from 'react';
import { ListView } from './ListView';
import { FIXTURE_12_ISSUES } from '../views/fixtures';
import type { IssueItem } from '../views/viewsApi';

describe('ListView', () => {
  it('groups 12 fixture issues into state sections in sort_order with exact counts', () => {
    const onToggleSelect = vi.fn();

    const { container } = render(
      <ListView
        issues={FIXTURE_12_ISSUES}
        projectKey="KAN"
        modulesEnabled={true}
        onToggleSelect={onToggleSelect}
      />
    );

    const toggles = container.querySelectorAll('.list-section-toggle');
    expect(toggles.length).toBeGreaterThan(0);

    const backlogToggle = Array.from(toggles).find((t) => t.textContent.includes('Backlog'));
    expect(backlogToggle).toBeDefined();
    expect(backlogToggle?.textContent).toContain('2');

    const inProgressToggle = Array.from(toggles).find((t) => t.textContent.includes('In Progress'));
    expect(inProgressToggle).toBeDefined();
    expect(inProgressToggle?.textContent).toContain('2');

    const doneToggle = Array.from(toggles).find((t) => t.textContent.includes('Done'));
    expect(doneToggle).toBeDefined();
    expect(doneToggle?.textContent).toContain('3');
  });

  it('collapses and expands Backlog section via aria-expanded toggle', () => {
    const { container } = render(
      <ListView
        issues={FIXTURE_12_ISSUES}
        projectKey="KAN"
        modulesEnabled={true}
      />
    );

    const toggles = container.querySelectorAll('.list-section-toggle');
    const backlogToggle = Array.from(toggles).find((t) => t.textContent.includes('Backlog')) as HTMLButtonElement;
    expect(backlogToggle).toBeDefined();
    expect(backlogToggle.getAttribute('aria-expanded')).toBe('true');

    // Issue KAN-140 is visible
    expect(screen.getByText('KAN-140')).toBeDefined();

    // Click to collapse
    fireEvent.click(backlogToggle);
    expect(backlogToggle.getAttribute('aria-expanded')).toBe('false');
    expect(screen.queryByText('KAN-140')).toBeNull();

    // Click to expand again
    fireEvent.click(backlogToggle);
    expect(backlogToggle.getAttribute('aria-expanded')).toBe('true');
    expect(screen.getByText('KAN-140')).toBeDefined();
  });

  it('renders external assignee with literal hint and links KAN-142 to peek', () => {
    render(
      <ListView
        issues={FIXTURE_12_ISSUES}
        projectKey="KAN"
        modulesEnabled={true}
      />
    );

    // Link for KAN-142
    const link = screen.getByRole('link', { name: 'KAN-142' });
    expect(link.getAttribute('href')).toBe('?layout=list&peek=KAN-142');

    // Free text assignee Ext: SecAudit
    expect(screen.getByText('Ext: SecAudit')).toBeDefined();

    // External assignee emoji trigger
    const extAssigneeBtn = screen.getByRole('button', { name: 'External free-text assignee' });
    expect(extAssigneeBtn).toBeDefined();

    // Focus to reveal popup with literal S7.2 8b text
    act(() => {
      fireEvent.focus(extAssigneeBtn);
    });

    const popup = document.querySelector('.emoji-hint-popup');
    expect(popup).toBeDefined();
    expect(popup?.textContent).toContain(
      'External free-text label - grants zero access and sends zero notifications'
    );
  });

  it('handles keyboard navigation and Enter peek link trigger', () => {
    const { container } = render(
      <ListView
        issues={FIXTURE_12_ISSUES}
        projectKey="KAN"
        modulesEnabled={true}
      />
    );

    const listView = container.querySelector('.list-view');
    expect(listView).toBeDefined();

    if (listView) {
      // ArrowDown and ArrowUp roving focus
      fireEvent.keyDown(listView, { key: 'ArrowDown' });
      fireEvent.keyDown(listView, { key: 'ArrowUp' });
    }

    // Enter on a list row
    const row = container.querySelector('.list-row');
    expect(row).toBeDefined();
    if (row) {
      fireEvent.keyDown(row, { key: 'Enter' });
    }
  });

  it('renders Load more button and handles click and loading state', () => {
    const onLoadMore = vi.fn();
    const { rerender } = render(
      <ListView
        issues={FIXTURE_12_ISSUES}
        projectKey="KAN"
        modulesEnabled={true}
        nextCursor="cur_page_2"
        onLoadMore={onLoadMore}
        isLoading={false}
      />
    );

    const loadMoreBtn = screen.getByRole('button', { name: /Load more/i });
    expect(loadMoreBtn).toBeDefined();
    fireEvent.click(loadMoreBtn);
    expect(onLoadMore).toHaveBeenCalledTimes(1);

    // Rerender with isLoading true
    rerender(
      <ListView
        issues={FIXTURE_12_ISSUES}
        projectKey="KAN"
        modulesEnabled={true}
        nextCursor="cur_page_2"
        onLoadMore={onLoadMore}
        isLoading={true}
      />
    );
    expect(screen.getByText('Loading...')).toBeDefined();
  });

  it('unmounts Modules pill completely when modulesEnabled is false', () => {
    render(
      <ListView
        issues={FIXTURE_12_ISSUES}
        projectKey="KAN"
        modulesEnabled={false}
      />
    );

    expect(screen.queryByText('Modules')).toBeNull();
  });

  it('safely renders hostile issue summary, drops invalid label hex, and handles fallback fields', () => {
    const hostileIssue: IssueItem = {
      id: '',
      key: 'KAN-999',
      summary: '<img src=x onerror=alert(1)>',
      state: { id: 's-custom', name: 'CustomState', group: 'backlog', sort_order: 15 },
      priority: { slug: 'high', label: 'High' },
      labels: [{ id: 'l-1', name: 'Evil', color_hex: 'red;background:url(//evil)' }],
    };

    const unnamedStateIssue: IssueItem = {
      id: '',
      key: 'KAN-998',
      summary: 'Unnamed state issue',
      state: { id: 's-empty', name: '', group: '' },
      priority: { slug: 'low', label: 'Low' },
    };

    render(
      <ListView
        issues={[hostileIssue, unnamedStateIssue]}
        projectKey="KAN"
        modulesEnabled={true}
      />
    );

    // Summary is rendered as literal text, not HTML element
    const summarySpan = screen.getByText('<img src=x onerror=alert(1)>');
    expect(summarySpan).toBeDefined();
    expect(document.querySelector('img[src="x"]')).toBeNull();

    // Label dot should not have invalid style applied
    const labelDot = document.querySelector('.label-dot');
    expect(labelDot).toBeDefined();
    expect(labelDot?.getAttribute('style') ?? '').toBe('');
  });

  it('renders calm empty state when project has 0 issues', () => {
    const onCreate = vi.fn();
    render(
      <ListView
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

  it('suppresses overdue indicator for completed or cancelled issues', () => {
    render(
      <ListView
        issues={FIXTURE_12_ISSUES}
        projectKey="KAN"
        modulesEnabled={true}
      />
    );

    // KAN-148 is Done with past due date 2026-01-01 -> overdue pill must NOT be applied
    const kan148Row = screen.getByText('KAN-148').closest('li');
    expect(kan148Row).toBeDefined();
    const overduePills = kan148Row?.querySelectorAll('.due-pill--overdue');
    expect(overduePills?.length ?? 0).toBe(0);

    // KAN-150 is Cancelled with past due date 2026-01-15 -> overdue pill must NOT be applied
    const kan150Row = screen.getByText('KAN-150').closest('li');
    expect(kan150Row).toBeDefined();
    const cancelledOverdue = kan150Row?.querySelectorAll('.due-pill--overdue');
    expect(cancelledOverdue?.length ?? 0).toBe(0);
  });

  it('renders Single Filter Card Dropdown and handles search, state, priority, and + New (KANBA-174)', () => {
    const onCreate = vi.fn();
    const onOpenPeek = vi.fn();

    render(
      <ListView
        issues={FIXTURE_12_ISSUES}
        projectKey="KAN"
        modulesEnabled={true}
        onCreateIssue={onCreate}
        onOpenPeek={onOpenPeek}
        activeKey="KAN-140"
      />
    );

    // Verify compact topbar rendered
    expect(screen.getByTestId('list-compact-topbar')).toBeDefined();

    // + New button triggers onCreateIssue
    const newBtn = screen.getByRole('button', { name: 'New work item' });
    fireEvent.click(newBtn);
    expect(onCreate).toHaveBeenCalledTimes(1);

    // Filter dropdown toggle
    const filterBtn = screen.getByRole('button', { name: 'Filter & Group' });
    expect(filterBtn.getAttribute('aria-expanded')).toBe('false');

    fireEvent.click(filterBtn);
    expect(filterBtn.getAttribute('aria-expanded')).toBe('true');
    expect(screen.getByRole('dialog', { name: 'Filter and Group options' })).toBeDefined();

    const popover = screen.getByRole('dialog', { name: 'Filter and Group options' });

    // 1. Text Search Filter
    const searchInput = within(popover).getByLabelText(/Search/i);
    fireEvent.change(searchInput, { target: { value: 'OAuth' } });

    // KAN-142 has summary with "OAuth"
    expect(screen.getByText('KAN-142')).toBeDefined();
    expect(screen.queryByText('KAN-140')).toBeNull();

    // 2. Reset filters
    const resetBtn = within(popover).getByRole('button', { name: 'Reset filters' });
    fireEvent.click(resetBtn);
    expect(screen.getByText('KAN-140')).toBeDefined();

    // 3. Priority filter
    const prioSelect = within(popover).getByLabelText(/^Priority$/i);
    fireEvent.change(prioSelect, { target: { value: 'urgent' } });
    expect(screen.getByText('KAN-142')).toBeDefined();
    expect(screen.queryByText('KAN-140')).toBeNull();

    // Reset again
    fireEvent.click(within(popover).getByRole('button', { name: 'Reset filters' }));

    // 4. Group by Priority
    const groupSelect = within(popover).getByLabelText(/Group By/i);
    fireEvent.change(groupSelect, { target: { value: 'priority' } });
    expect(screen.getByText('Urgent')).toBeDefined();

    // Close popover via Escape
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(screen.queryByRole('dialog', { name: 'Filter and Group options' })).toBeNull();

    // Clicking row triggers onOpenPeek
    const kan142Row = screen.getByText('KAN-142').closest('li');
    expect(kan142Row).toBeDefined();
    if (kan142Row) {
      fireEvent.click(kan142Row);
      expect(onOpenPeek).toHaveBeenCalledWith('KAN-142');
    }
  });

  it('navigates to workflow settings when + Workflow button is clicked', () => {
    const assignSpy = vi.fn();
    Object.defineProperty(window, 'location', {
      writable: true,
      value: { assign: assignSpy, pathname: '/projects/KAN/issues' },
    });

    render(<ListView issues={FIXTURE_12_ISSUES} projectKey="KAN" />);
    const workflowBtn = screen.getByTestId('section-add-workflow-btn-Backlog');
    fireEvent.click(workflowBtn);
    expect(assignSpy).toHaveBeenCalledWith(
      '/projects/KAN/settings/workflows?to_state=Backlog&attach=1',
    );
  });

  it('covers state filter, key search, groupBy none, custom priority, and outside click', () => {
    const customIssues: IssueItem[] = [
      ...FIXTURE_12_ISSUES,
      {
        ...FIXTURE_12_ISSUES[0],
        id: 'issue-custom-prio',
        key: 'KAN-999',
        summary: 'Custom priority item',
        state: { id: 's-in-prog', name: 'In Progress', group: 'started' },
        priority: { slug: 'custom_tier', label: 'Custom Tier', emoji: '✨' },
      },
      {
        ...FIXTURE_12_ISSUES[0],
        id: 'issue-unlabeled-prio',
        key: 'KAN-998',
        summary: 'Unlabeled priority item',
        state: { id: 's-in-prog', name: 'In Progress', group: 'started' },
        priority: { slug: 'unlabeled_tier', label: '', emoji: '✨' },
      },
    ];

    render(<ListView issues={customIssues} projectKey="KAN" />);

    const filterBtn = screen.getByRole('button', { name: 'Filter & Group' });
    fireEvent.click(filterBtn);
    const popover = screen.getByRole('dialog', { name: 'Filter and Group options' });

    // 1. Search by Key only (summary does not match)
    const searchInput = within(popover).getByLabelText(/Search/i);
    fireEvent.change(searchInput, { target: { value: '999' } });
    expect(screen.getByText('KAN-999')).toBeDefined();

    // Search by non-matching query
    fireEvent.change(searchInput, { target: { value: 'nonexistentquery' } });
    expect(screen.queryByText('KAN-999')).toBeNull();

    // Reset search
    fireEvent.change(searchInput, { target: { value: '' } });

    // 2. Filter by State (group match e.g. "started", name match e.g. "done", partial name match)
    const stateSelect = within(popover).getByLabelText(/^State$/i);
    fireEvent.change(stateSelect, { target: { value: 'started' } });
    expect(screen.getByText('KAN-999')).toBeDefined();

    fireEvent.change(stateSelect, { target: { value: 'completed' } });
    expect(screen.getByText('KAN-148')).toBeDefined();
    expect(screen.queryByText('KAN-999')).toBeNull();

    // Partial name match e.g. "prog"
    fireEvent.change(stateSelect, { target: { value: 'prog' } });
    expect(screen.getByText('KAN-999')).toBeDefined();

    // Cancelled state (excludes KAN-999)
    fireEvent.change(stateSelect, { target: { value: 'cancelled' } });
    expect(screen.queryByText('KAN-999')).toBeNull();

    // Reset state
    fireEvent.change(stateSelect, { target: { value: 'all' } });

    // 3. Group by "none"
    const groupSelect = within(popover).getByLabelText(/Group By/i);
    fireEvent.change(groupSelect, { target: { value: 'none' } });
    expect(screen.getByText('All Work Items')).toBeDefined();

    // 4. Group by "priority" with custom priority and fallback slug
    fireEvent.change(groupSelect, { target: { value: 'priority' } });
    expect(screen.getByText('Custom Tier')).toBeDefined();

    // 5. Group by "cycle"
    fireEvent.change(groupSelect, { target: { value: 'cycle' } });
    expect(screen.getByText('No Cycle')).toBeDefined();

    // 6. Group by "module"
    fireEvent.change(groupSelect, { target: { value: 'module' } });
    expect(screen.getByText('No Module')).toBeDefined();

    // Inside click and non-Escape keypress do not close popover
    fireEvent.mouseDown(popover);
    expect(screen.queryByRole('dialog', { name: 'Filter and Group options' })).not.toBeNull();
    fireEvent.keyDown(window, { key: 'Tab' });
    expect(screen.queryByRole('dialog', { name: 'Filter and Group options' })).not.toBeNull();

    // 5. Outside click closes the popover
    fireEvent.mouseDown(document.body);
    expect(screen.queryByRole('dialog', { name: 'Filter and Group options' })).toBeNull();
  });

  it('groups by cycle and module with real summaries and fallback labels', () => {
    const firstIssue = FIXTURE_12_ISSUES[0];
    const secondIssue = FIXTURE_12_ISSUES[1];
    expect(firstIssue).toBeDefined();
    expect(secondIssue).toBeDefined();
    if (!firstIssue || !secondIssue) {
      throw new Error('Missing fixtures');
    }

    const issuesWithCycleAndMod: IssueItem[] = [
      {
        ...firstIssue,
        id: 'iss-c1',
        key: 'KAN-C1',
        cycle_id: 'cycle-123456',
        cycle: { id: 'cycle-123456', name: 'Sprint Alpha' },
        modules: [{ id: 'mod-1', name: 'Core Engine' }],
      },
      {
        ...secondIssue,
        id: 'iss-c2',
        key: 'KAN-C2',
        cycle_id: 'cycle-654321',
        cycle: null,
        module_ids: ['mod-fallback-123'],
      },
    ];

    render(
      <ListView issues={issuesWithCycleAndMod} projectKey="KAN" modulesEnabled={true} />
    );

    const filterBtn = screen.getByRole('button', { name: 'Filter & Group' });
    fireEvent.click(filterBtn);
    const popover = screen.getByRole('dialog', { name: 'Filter and Group options' });
    const groupSelect = within(popover).getByLabelText(/Group By/i);

    // Group by Cycle
    fireEvent.change(groupSelect, { target: { value: 'cycle' } });
    expect(screen.getByText('Sprint Alpha')).toBeDefined();
    expect(screen.getByText('Cycle cycle-')).toBeDefined();

    // Group by Module
    fireEvent.change(groupSelect, { target: { value: 'module' } });
    expect(screen.getByText('Core Engine')).toBeDefined();
    expect(screen.getByText('Module mod-fa')).toBeDefined();
  });
});
