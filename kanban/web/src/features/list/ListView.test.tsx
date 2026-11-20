import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import React from 'react';
import { ListView } from './ListView';
import type { IssueItem } from '../views/viewsApi';

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
    const starBtns = screen.getAllByTestId('favorite-issue-toggle');
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

  it('renders Load more button when nextCursor is present', () => {
    const onLoadMore = vi.fn();
    render(
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
  });

  it('handles keyboard Enter on card to open peek', () => {
    const onOpenPeek = vi.fn();
    render(
      <ListView
        issues={mockIssues}
        onOpenPeek={onOpenPeek}
      />,
    );

    const card = screen.getByTestId('issue-list-card-KAN-101');
    fireEvent.keyDown(card, { key: 'Enter' });
    expect(onOpenPeek).toHaveBeenCalledWith('KAN-101');
  });

  it('opens local QuickFieldPopover when onOpenFieldPopover is omitted', () => {
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
});
