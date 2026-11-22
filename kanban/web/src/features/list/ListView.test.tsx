import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import React from 'react';
import { ListView, sortIssuesList, type IssueSortOption } from './ListView';
import type { IssueItem, StateSummary } from '../views/viewsApi';

describe('ListView (KAN-52 Left Master Rail)', () => {
  const mockIssues: IssueItem[] = [
    {
      id: 'i-1',
      key: 'KAN-101',
      summary: 'First Issue Title',
      state: { id: 'state-todo', name: 'Todo', group: 'unstarted' },
      priority: { slug: 'high', label: 'High' },
      created_at: '2026-11-20T10:00:00Z',
      updated_at: '2026-11-20T12:00:00Z',
      due_date: '2026-11-30',
      board_rank: '0|hzzzzz:',
    },
    {
      id: 'i-2',
      key: 'KAN-102',
      summary: 'Second Issue Title',
      state: { id: 'state-done', name: 'Done', group: 'completed' },
      priority: { slug: 'urgent', label: 'Urgent' },
      created_at: '2026-11-19T10:00:00Z',
      updated_at: '2026-11-20T14:00:00Z',
      due_date: '2026-11-25',
      board_rank: '0|i00000:',
    },
  ];

  it('renders rail header with Order by sort selector, direction toggle, and refresh button', () => {
    const onRefresh = vi.fn();
    render(<ListView issues={mockIssues} onRefresh={onRefresh} />);

    expect(screen.getByTestId('issue-rail-header')).toBeDefined();
    expect(screen.getByTestId('issue-sort-select')).toBeDefined();
    expect(screen.getByTestId('issue-sort-dir-btn')).toBeDefined();
    expect(screen.getByTestId('issue-rail-refresh-btn')).toBeDefined();

    // Click refresh
    const refreshBtn = screen.getByTestId('issue-rail-refresh-btn');
    fireEvent.click(refreshBtn);
    expect(onRefresh).toHaveBeenCalled();
  });

  it('renders compact 2-line cards with priority icon, key, state button, favorite star, and summary', () => {
    const onOpenPeek = vi.fn();
    render(
      <ListView
        issues={mockIssues}
        activeKey="KAN-101"
        onOpenPeek={onOpenPeek}
      />,
    );

    const card101 = screen.getByTestId('issue-list-card-KAN-101');
    expect(card101).toBeDefined();
    expect(card101.classList.contains('list-row--active')).toBe(true);
    expect(screen.getByText('KAN-101')).toBeDefined();
    expect(screen.getByText('First Issue Title')).toBeDefined();

    // Line 1 interactive state pill
    expect(screen.getByTestId('list-row-state-btn-KAN-101')).toBeDefined();

    // Favorite star button
    const starBtns = screen.getAllByTestId(/^rail-favorite-toggle-/);
    expect(starBtns.length).toBe(2);
    const firstStar = starBtns[0];
    if (firstStar) {
      fireEvent.click(firstStar);
      expect(firstStar.textContent).toBe('⭐');
    }

    // Click card opens peek
    fireEvent.click(card101);
    expect(onOpenPeek).toHaveBeenCalledWith('KAN-101');
  });

  it('handles Order by sorting across priority, key, created, and due date', () => {
    render(<ListView issues={mockIssues} />);

    const sortSelect = screen.getByTestId('issue-sort-select');
    const dirBtn = screen.getByTestId('issue-sort-dir-btn');

    // Sort by priority desc: urgent (KAN-102) before high (KAN-101)
    fireEvent.change(sortSelect, { target: { value: 'priority' } });
    const cardsPriority = screen.getAllByRole('row');
    expect(cardsPriority[0]?.getAttribute('data-issue-key')).toBe('KAN-102');

    // Toggle dir to asc: high (KAN-101) before urgent (KAN-102)
    fireEvent.click(dirBtn);
    const cardsPriorityAsc = screen.getAllByRole('row');
    expect(cardsPriorityAsc[0]?.getAttribute('data-issue-key')).toBe('KAN-101');

    // Sort by key
    fireEvent.change(sortSelect, { target: { value: 'key' } });
    expect(screen.getAllByRole('row')[0]?.getAttribute('data-issue-key')).toBe('KAN-101');

    // Sort by created
    fireEvent.change(sortSelect, { target: { value: 'created' } });
    expect(screen.getAllByRole('row')).toBeDefined();

    // Sort by due date
    fireEvent.change(sortSelect, { target: { value: 'due_date' } });
    expect(screen.getAllByRole('row')).toBeDefined();

    // Sort by rank
    fireEvent.change(sortSelect, { target: { value: 'rank' } });
    expect(screen.getAllByRole('row')).toBeDefined();

    // Sort by state
    fireEvent.change(sortSelect, { target: { value: 'state' } });
    expect(screen.getAllByRole('row')).toBeDefined();
  });

  it('forwards state button click to onOpenFieldPopover and preserves KAN-44 mobile controls', () => {
    const onOpenFieldPopover = vi.fn();
    render(
      <ListView
        issues={mockIssues}
        onOpenFieldPopover={onOpenFieldPopover}
      />,
    );

    const stateBtn = screen.getByTestId('list-row-state-btn-KAN-101');
    fireEvent.click(stateBtn);
    expect(onOpenFieldPopover).toHaveBeenCalledWith('state', mockIssues[0], expect.any(Object));
  });

  it('renders calm empty state when issues array is empty', () => {
    const onCreateIssue = vi.fn();
    render(<ListView issues={[]} onCreateIssue={onCreateIssue} />);

    expect(screen.getByText('No work items found')).toBeDefined();
    const createBtn = screen.getByText('+ Create first work item');
    fireEvent.click(createBtn);
    expect(onCreateIssue).toHaveBeenCalled();
  });

  it('renders Load more button when nextCursor is present and handles isLoading true', () => {
    const onLoadMore = vi.fn();
    const { rerender } = render(
      <ListView
        issues={mockIssues}
        nextCursor="cur_123"
        onLoadMore={onLoadMore}
        isLoading={false}
      />,
    );

    const loadMoreBtn = screen.getByRole('button', { name: 'Load more' });
    fireEvent.click(loadMoreBtn);
    expect(onLoadMore).toHaveBeenCalled();

    rerender(
      <ListView
        issues={mockIssues}
        nextCursor="cur_123"
        onLoadMore={onLoadMore}
        isLoading={true}
      />,
    );
    expect(screen.getByText('Loading...')).toBeDefined();
  });

  it('handles keyboard navigation and card click with/without onOpenPeek', () => {
    const onOpenPeek = vi.fn();
    const { rerender } = render(
      <ListView
        issues={mockIssues}
        focusedKey="KAN-101"
        onOpenPeek={onOpenPeek}
      />,
    );

    const card = screen.getByTestId('issue-list-card-KAN-101');
    expect(card.classList.contains('list-row--active')).toBe(true);

    // Non-Enter keydown
    fireEvent.keyDown(card, { key: 'ArrowDown' });
    expect(onOpenPeek).not.toHaveBeenCalled();

    // Enter keydown
    fireEvent.keyDown(card, { key: 'Enter' });
    expect(onOpenPeek).toHaveBeenCalledWith('KAN-101');

    // Without onOpenPeek
    rerender(
      <ListView
        issues={mockIssues}
        focusedKey="KAN-102"
        capabilities={['EDIT']}
      />,
    );
    fireEvent.click(screen.getByTestId('issue-list-card-KAN-102'));
    fireEvent.keyDown(screen.getByTestId('issue-list-card-KAN-102'), { key: 'Enter' });
  });

  it('opens local QuickFieldPopover when onOpenFieldPopover is omitted and handles selection and close', () => {
    const onStateSelect = vi.fn();
    render(
      <ListView
        issues={mockIssues}
        onStateSelect={onStateSelect}
      />,
    );

    const stateBtn = screen.getByTestId('list-row-state-btn-KAN-101');
    fireEvent.click(stateBtn);
    // Popover is open
    expect(screen.getByRole('dialog')).toBeDefined();

    // Select state option from popover
    const inProgOption = screen.getByRole('option', { name: 'In Progress' });
    fireEvent.click(inProgOption);
    expect(onStateSelect).toHaveBeenCalledWith('KAN-101', 'state-in-progress');

    // Reopen and test close callback
    fireEvent.click(screen.getByTestId('list-row-state-btn-KAN-101'));
    expect(screen.getByRole('dialog')).toBeDefined();
    // Press Escape or close popover
    fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' });
  });

  it('supports capabilities as a Set object and handles window refresh dispatch', () => {
    const dispatchSpy = vi.spyOn(window, 'dispatchEvent');
    const { rerender } = render(
      <ListView
        issues={mockIssues}
        capabilities={new Set(['ADMIN'])}
      />,
    );
    expect(screen.getByTestId('list-row-state-btn-KAN-101')).toBeDefined();

    // Set with lowercase admin
    rerender(
      <ListView
        issues={mockIssues}
        capabilities={new Set(['admin'])}
      />,
    );
    expect(screen.getByTestId('list-row-state-btn-KAN-101')).toBeDefined();

    // Set without transition caps (read-only)
    rerender(
      <ListView
        issues={mockIssues}
        capabilities={new Set(['VIEWER'])}
      />,
    );
    expect(screen.getByTestId('list-row-state-readonly-KAN-101')).toBeDefined();

    // Default refresh dispatch when onRefresh is omitted
    rerender(
      <ListView
        issues={mockIssues}
      />,
    );
    fireEvent.click(screen.getByTestId('issue-rail-refresh-btn'));
    expect(dispatchSpy).toHaveBeenCalledWith(expect.any(CustomEvent));
    dispatchSpy.mockRestore();
  });

  it('handles row selection toggle and card click ignore on interactive targets', () => {
    const onToggleSelect = vi.fn();
    const onOpenPeek = vi.fn();
    render(
      <ListView
        issues={mockIssues}
        onToggleSelect={onToggleSelect}
        onOpenPeek={onOpenPeek}
      />,
    );
    const checkbox = screen.getByLabelText('Select KAN-101');
    fireEvent.click(checkbox);
    expect(onToggleSelect).toHaveBeenCalledWith('KAN-101', true);

    // Clicking button inside card should not trigger onOpenPeek
    const stateBtn = screen.getByTestId('list-row-state-btn-KAN-101');
    fireEvent.click(stateBtn);
    expect(onOpenPeek).not.toHaveBeenCalled();
  });

  it('enforces VIEWER RBAC gating with static StateBadge when TRANSITION/EDIT is absent', () => {
    // 1. Read-only viewer capabilities
    const { rerender } = render(
      <ListView
        issues={mockIssues}
        capabilities={['VIEW']}
      />,
    );

    expect(screen.getByTestId('list-row-state-readonly-KAN-101')).toBeDefined();
    expect(screen.queryByTestId('list-row-state-btn-KAN-101')).toBeNull();

    // 2. Interactive with TRANSITION capability
    rerender(
      <ListView
        issues={mockIssues}
        capabilities={['TRANSITION']}
      />,
    );
    expect(screen.getByTestId('list-row-state-btn-KAN-101')).toBeDefined();
    expect(screen.queryByTestId('list-row-state-readonly-KAN-101')).toBeNull();
  });

  it('supports controlled sortBy and sortDir props with change callbacks', () => {
    const onSortByChange = vi.fn();
    const onSortDirChange = vi.fn();
    render(
      <ListView
        issues={mockIssues}
        sortBy="priority"
        onSortByChange={onSortByChange}
        sortDir="asc"
        onSortDirChange={onSortDirChange}
      />,
    );

    const sortSelect = screen.getByTestId<HTMLSelectElement>('issue-sort-select');
    expect(sortSelect.value).toBe('priority');

    fireEvent.change(sortSelect, { target: { value: 'created' } });
    expect(onSortByChange).toHaveBeenCalledWith('created');

    const dirBtn = screen.getByTestId('issue-sort-dir-btn');
    fireEvent.click(dirBtn);
    expect(onSortDirChange).toHaveBeenCalledWith('desc');
  });

  it('covers sortIssuesList edge branches and un-favoriting toggle', () => {
    // 1. Un-favoriting
    localStorage.setItem('kb_favorite_issues', JSON.stringify(['KAN-101']));
    const { rerender } = render(<ListView issues={mockIssues} />);
    const starBtn = screen.getByTestId('rail-favorite-toggle-KAN-101');
    expect(starBtn.textContent).toBe('⭐');
    // Click to unfavorite
    fireEvent.click(starBtn);
    expect(starBtn.textContent).toBe('☆');

    // 2. localStorage throw in initialization
    const getSpy = vi.spyOn(Storage.prototype, 'getItem').mockImplementationOnce(() => {
      throw new Error('Access denied');
    });
    rerender(<ListView issues={mockIssues} />);
    getSpy.mockRestore();

    // 3. sortIssuesList directly with various defensive branches
    const mixedIssues: IssueItem[] = [
      {
        id: '',
        key: 'KEY-NOTANUMBER',
        summary: 'Non numeric key',
        state: { id: 's1', name: 'Beta State', group: 'unstarted', sort_order: 1 },
        priority: { slug: 'unknown_slug_a', label: '' },
        due_date: null,
      },
      {
        id: 'm2',
        key: 'ALPHA-99',
        summary: 'Alpha',
        state: { id: 's2', name: 'Alpha State', group: 'unstarted', sort_order: 1 },
        priority: { slug: 'unknown_slug_b', label: '' },
        due_date: '2026-11-20',
        board_rank: '0|a:',
        created_at: '2026-11-20T00:00:00Z',
        updated_at: '2026-11-20T00:00:00Z',
      },
      {
        id: 'm3',
        key: 'NOHYPHENKEY',
        summary: 'No hyphen key',
        state: { id: 's3', name: 'Gamma State', group: 'unstarted', sort_order: 2 },
        priority: { slug: 'high', label: '' },
        due_date: '2026-11-25',
        board_rank: '0|b:',
        created_at: '2026-11-25T00:00:00Z',
        updated_at: '2026-11-25T00:00:00Z',
      },
    ];

    // default branch
    const resDefault = sortIssuesList(mixedIssues, 'default_unknown' as unknown as IssueSortOption, 'asc');
    expect(resDefault.length).toBe(3);

    // key branch
    const resKey = sortIssuesList(mixedIssues, 'key', 'asc');
    expect(resKey[0]?.key).toBe('KEY-NOTANUMBER');

    // state branch with identical sort_order
    const resState = sortIssuesList(mixedIssues, 'state', 'asc');
    expect(resState[0]?.state.name).toBe('Alpha State');

    // due_date branch with null
    const resDue = sortIssuesList(mixedIssues, 'due_date', 'asc');
    expect(resDue.length).toBe(3);

    // rank branch with null
    const resRank = sortIssuesList(mixedIssues, 'rank', 'asc');
    expect(resRank.length).toBe(3);

    // updated branch with null
    const resUpdated = sortIssuesList(mixedIssues, 'updated', 'asc');
    expect(resUpdated.length).toBe(3);

    // created branch with null
    const resCreated = sortIssuesList(mixedIssues, 'created', 'asc');
    expect(resCreated.length).toBe(3);
  });

  it('covers onCreateIssue button, selected row state, and missing state name fallback', () => {
    const onCreateIssue = vi.fn();
    const issueWithoutStateName: IssueItem = {
      id: 'i-noname',
      key: 'KAN-NONAME',
      summary: 'No state name',
      state: { id: 's-no-name', group: 'unstarted' } as unknown as StateSummary,
      priority: { slug: 'low', label: 'Low' },
    };

    render(
      <ListView
        issues={[issueWithoutStateName]}
        selectedIds={['KAN-NONAME']}
        onCreateIssue={onCreateIssue}
      />,
    );

    const createBtn = screen.getByTestId('issue-rail-new-btn');
    fireEvent.click(createBtn);
    expect(onCreateIssue).toHaveBeenCalled();

    const row = screen.getByTestId('issue-list-card-KAN-NONAME');
    expect(row.classList.contains('list-row--selected')).toBe(true);

    const stateBtn = screen.getByTestId('list-row-state-btn-KAN-NONAME');
    expect(stateBtn.getAttribute('aria-label')).toBe('Status: ');
  });

  it('covers localStorage pre-hydration, favorites change events, refresh fallback dispatch, and popover non-state selection', () => {
    // Non-array JSON in localStorage initially
    localStorage.setItem('kb_favorite_issues', JSON.stringify({ not: 'an_array' }));
    const dispatchSpy = vi.spyOn(window, 'dispatchEvent');

    const issuesWithoutIds: IssueItem[] = [
      {
        id: '',
        key: 'KAN-999',
        summary: 'Missing id issue',
        state: { id: 'state-todo', name: 'Todo', group: 'unstarted' },
        priority: { slug: 'low', label: 'Low' },
      },
    ];

    const { unmount } = render(
      <ListView
        issues={issuesWithoutIds}
      />,
    );

    // Refresh button without onRefresh prop dispatches kb:refresh-issues
    const refreshBtn = screen.getByTestId('issue-rail-refresh-btn');
    fireEvent.click(refreshBtn);
    expect(dispatchSpy).toHaveBeenCalledWith(expect.objectContaining({ type: 'kb:refresh-issues' }));
    unmount();

    // Refresh button with onRefresh prop provided
    const onRefreshMock = vi.fn();
    const { unmount: unmountRefresh } = render(
      <ListView
        issues={issuesWithoutIds}
        onRefresh={onRefreshMock}
      />,
    );
    fireEvent.click(screen.getByTestId('issue-rail-refresh-btn'));
    expect(onRefreshMock).toHaveBeenCalledTimes(1);

    // Favorites change event with valid, non-array, empty/null, corrupt JSON, and non-string elements in localStorage while component is mounted
    localStorage.setItem('kb_favorite_issues', JSON.stringify(['KAN-999', 42, null]));
    act(() => {
      window.dispatchEvent(new CustomEvent('kb:favorites-changed'));
    });

    localStorage.removeItem('kb_favorite_issues');
    act(() => {
      window.dispatchEvent(new CustomEvent('kb:favorites-changed'));
    });

    localStorage.setItem('kb_favorite_issues', JSON.stringify({ not: 'an_array' }));
    act(() => {
      window.dispatchEvent(new CustomEvent('kb:favorites-changed'));
    });

    localStorage.setItem('kb_favorite_issues', 'invalid-json-string');
    act(() => {
      window.dispatchEvent(new CustomEvent('kb:favorites-changed'));
    });
    unmountRefresh();

    // Sorting by rank with defined and undefined board_rank
    const issueA = mockIssues[0];
    const issueB = mockIssues[1];
    if (!issueA || !issueB) {
      throw new Error('mockIssues missing');
    }
    const rankIssues: IssueItem[] = [
      { ...issueA, key: 'KAN-A', board_rank: '0|hzzzzz:' },
      { ...issueB, key: 'KAN-B' },
    ];
    const { unmount: unmountRank } = render(<ListView issues={rankIssues} sortBy="rank" sortDir="asc" />);
    expect(screen.getByTestId('issue-list-card-KAN-A')).toBeDefined();
    unmountRank();

    // Sorting by due_date with defined and undefined due_date
    const dueDateIssues: IssueItem[] = [
      { ...issueA, key: 'KAN-D1', due_date: '2026-12-01' },
      { ...issueB, key: 'KAN-D2', due_date: null },
    ];
    const { unmount: unmountDue } = render(<ListView issues={dueDateIssues} sortBy="due_date" sortDir="asc" />);
    expect(screen.getByTestId('issue-list-card-KAN-D1')).toBeDefined();
    unmountDue();

    // Local popover selection when onStateSelect is omitted
    const { unmount: unmountNoStateSelect } = render(<ListView issues={mockIssues} />);
    fireEvent.click(screen.getByTestId('list-row-state-btn-KAN-101'));
    const inProgOpt = screen.getByRole('option', { name: 'In Progress' });
    fireEvent.click(inProgOpt);
    unmountNoStateSelect();

    localStorage.clear();
  });

  it('covers remaining sorting branches and parseIssueNumber edge cases', () => {
    const issue1: IssueItem = {
      id: 'i-1',
      key: 'INVALID',
      summary: 'No hyphen issue',
      state: { id: 's-1', name: 'Alpha State', group: 'unstarted', sort_order: 10 },
      priority: { slug: 'low', label: 'Low' },
    };
    const issue2: IssueItem = {
      id: 'i-2',
      key: 'KAN-99',
      summary: 'Hyphen issue',
      state: { id: 's-2', name: 'Beta State', group: 'unstarted', sort_order: 10 },
      priority: { slug: 'high', label: 'High' },
      updated_at: '2026-11-20T10:00:00Z',
      created_at: '2026-11-20T10:00:00Z',
    };

    // State sort with matching sort_order covers secondary name comparison (cmp === 0)
    const sortedState = sortIssuesList([issue2, issue1], 'state', 'asc');
    expect(sortedState[0]?.key).toBe('INVALID');

    // Key sort with non-numeric key covers parseIssueNumber fallback
    const sortedKey = sortIssuesList([issue2, issue1], 'key', 'asc');
    expect(sortedKey[0]?.key).toBe('INVALID');

    // Updated and created sort with missing date strings
    const sortedUpdated = sortIssuesList([issue2, issue1], 'updated', 'asc');
    expect(sortedUpdated.length).toBe(2);
    const sortedCreated = sortIssuesList([issue2, issue1], 'created', 'asc');
    expect(sortedCreated.length).toBe(2);

    // Default branch
    const sortedDefault = sortIssuesList([issue1, issue2], 'custom' as unknown as IssueSortOption, 'asc');
    expect(sortedDefault.length).toBe(2);

    // Pre-hydrated localStorage with corrupted string on initial render
    localStorage.setItem('kb_favorite_issues', '{not_json');
    const { unmount } = render(<ListView issues={[issue1]} />);
    expect(screen.getByTestId('issue-list-card-INVALID')).toBeDefined();
    unmount();
    localStorage.clear();
  });

  it('renders list-view-loading skeleton when issues is empty and isLoading is true', () => {
    render(<ListView issues={[]} isLoading={true} />);
    expect(screen.getByTestId('list-view-loading')).toBeDefined();
  });

  it('KAN-308 Problem 4: sorts updated and created using numeric Date.parse across timezone offsets with deterministic key tie-breaking', () => {
    const tzIssues: IssueItem[] = [
      {
        id: 'tz-1',
        key: 'KAN-20',
        summary: 'Offset +02:00 (13:30 UTC)',
        state: { id: 's-1', name: 'Todo', group: 'unstarted' },
        priority: { slug: 'medium', label: 'Medium' },
        updated_at: '2026-11-20T15:30:00+02:00',
      },
      {
        id: 'tz-2',
        key: 'KAN-10',
        summary: 'UTC Z (14:00 UTC, newer than 15:30+02:00)',
        state: { id: 's-1', name: 'Todo', group: 'unstarted' },
        priority: { slug: 'medium', label: 'Medium' },
        updated_at: '2026-11-20T14:00:00.500Z',
      },
      {
        id: 'tz-3',
        key: 'KAN-5',
        summary: 'Same instant as KAN-20 (13:30 UTC), lower issue number',
        state: { id: 's-1', name: 'Todo', group: 'unstarted' },
        priority: { slug: 'medium', label: 'Medium' },
        updated_at: '2026-11-20T13:30:00Z',
      },
      {
        id: 'tz-4',
        key: 'KAN-30',
        summary: 'Fallback to created_at (13:45 UTC)',
        state: { id: 's-1', name: 'Todo', group: 'unstarted' },
        priority: { slug: 'medium', label: 'Medium' },
        created_at: '2026-11-20T13:45:00Z',
      },
    ];

    const desc = sortIssuesList(tzIssues, 'updated', 'desc');
    expect(desc.map((i) => i.key)).toEqual(['KAN-10', 'KAN-30', 'KAN-5', 'KAN-20']);

    const baseTz = tzIssues[0];
    if (!baseTz) throw new Error('missing baseTz');
    const createdTies = sortIssuesList(
      [
        { ...baseTz, key: 'KAN-20', created_at: '2026-11-20T13:30:00Z' },
        { ...baseTz, key: 'KAN-5', created_at: '2026-11-20T15:30:00+02:00' },
        { ...baseTz, key: 'ALPHA-5', created_at: '2026-11-20T13:30:00Z' },
      ],
      'created',
      'desc',
    );
    expect(createdTies.map((i) => i.key)).toEqual(['ALPHA-5', 'KAN-5', 'KAN-20']);
  });

  it('KAN-308 Problem 4: renders empty-state-hidden-terminal and empty-state-filtered when totalProjectIssueCount > 0', () => {
    const onShowAllStates = vi.fn();
    const onResetFilters = vi.fn();

    const { rerender } = render(
      <ListView
        issues={[]}
        totalProjectIssueCount={4}
        hiddenByStateCount={4}
        onShowAllStates={onShowAllStates}
      />,
    );

    expect(screen.getByTestId('empty-state-hidden-terminal')).toBeDefined();
    expect(screen.getByText('No actionable work items')).toBeDefined();
    fireEvent.click(screen.getByTestId('empty-show-all-states-btn'));
    expect(onShowAllStates).toHaveBeenCalledTimes(1);

    rerender(
      <ListView
        issues={[]}
        totalProjectIssueCount={4}
        hiddenByStateCount={0}
        onResetFilters={onResetFilters}
      />,
    );

    expect(screen.getByTestId('empty-state-filtered')).toBeDefined();
    expect(screen.getByText('No matching work items')).toBeDefined();
    fireEvent.click(screen.getByTestId('empty-reset-filters-btn'));
    expect(onResetFilters).toHaveBeenCalledTimes(1);
  });
});
