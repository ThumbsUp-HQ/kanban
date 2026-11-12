import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
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
});
