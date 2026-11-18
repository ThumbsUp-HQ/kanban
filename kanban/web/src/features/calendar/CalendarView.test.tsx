import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import React from 'react';
import { CalendarView } from './CalendarView';
import type { IssueItem } from '../views/viewsApi';

const TEST_ISSUES: IssueItem[] = [
  {
    id: 'issue-100',
    key: 'KAN-100',
    summary: 'Security Architecture Epic',
    state: { id: 's1', name: 'In Progress', group: 'started' },
    priority: { slug: 'high', label: 'High' },
    start_date: '2026-11-01',
    due_date: '2026-11-10',
  },
  {
    id: 'issue-142',
    key: 'KAN-142',
    summary: 'Harden Multi-Card OIDC & LDAPS Auth Studio',
    state: { id: 's1', name: 'In Progress', group: 'started' },
    priority: { slug: 'urgent', label: 'Urgent' },
    start_date: '2026-11-11',
    due_date: '2026-11-18',
  },
  {
    id: 'issue-143',
    key: 'KAN-143',
    summary: 'Verify LDAPS certificate pinning',
    state: { id: 's2', name: 'Done', group: 'completed' },
    priority: { slug: 'low', label: 'Low' },
    start_date: '2026-11-01',
    due_date: '2026-11-05',
  },
  {
    id: 'issue-unscheduled',
    key: 'KAN-999',
    summary: 'Unscheduled Maintenance',
    state: { id: 's0', name: 'Backlog', group: 'unstarted' },
    priority: { slug: 'medium', label: 'Medium' },
    due_date: null,
  },
];

describe('CalendarView', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    vi.restoreAllMocks();
    document.cookie = 'kb_csrf=test-csrf-token-123; Path=/';
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
    document.cookie = 'kb_csrf=; expires=Thu, 01 Jan 1970 00:00:00 GMT; Path=/';
  });

  it('renders 2-week grid for November 2026 and places KAN-142 in cell 2026-11-18', () => {
    const { container } = render(
      <CalendarView
        issues={TEST_ISSUES}
        projectKey="KAN"
        initialYear={2026}
        initialMonth={11}
        today="2026-11-12"
      />
    );

    expect(screen.getByText('2026-11-08 - 2026-11-21')).toBeDefined();

    // Check that 14 day cells are rendered
    const dayCells = container.querySelectorAll('.calendar-day-cell');
    expect(dayCells.length).toBe(14);

    // KAN-142 is in cell 2026-11-18
    const cell18 = container.querySelector('[data-date="2026-11-18"]');
    expect(cell18).toBeDefined();
    expect(cell18?.textContent).toContain('KAN-142');

    // Link peek URL check
    const pillLink = cell18?.querySelector('a');
    expect(pillLink?.getAttribute('href')).toBe('?layout=calendar&peek=KAN-142');

    // Drag start on pill
    if (pillLink) {
      fireEvent.dragStart(pillLink, { dataTransfer: { setData: vi.fn() } });
    }
  });

  it('infers initial anchor date from first issue due date when initialYear is omitted', () => {
    render(<CalendarView issues={TEST_ISSUES} projectKey="KAN" />);
    // First issue with due_date is KAN-100 (2026-11-10). Week starts Sunday 2026-11-08.
    expect(screen.getByText('2026-11-08 - 2026-11-21')).toBeDefined();
  });

  it('navigates Prev, Next, and Today in toolbar', () => {
    render(
      <CalendarView
        issues={TEST_ISSUES}
        projectKey="KAN"
        initialYear={2026}
        initialMonth={11}
        today="2026-11-12"
      />
    );

    expect(screen.getByText('2026-11-08 - 2026-11-21')).toBeDefined();

    // Click Next (advances 14 days)
    fireEvent.click(screen.getByRole('button', { name: 'Next 2 weeks' }));
    expect(screen.getByText('2026-11-22 - 2026-12-05')).toBeDefined();

    // Click Prev twice -> 2026-10-25 - 2026-11-07
    fireEvent.click(screen.getByRole('button', { name: 'Previous 2 weeks' }));
    fireEvent.click(screen.getByRole('button', { name: 'Previous 2 weeks' }));
    expect(screen.getByText('2026-10-25 - 2026-11-07')).toBeDefined();

    // Click Today -> returns to 2026-11-08 - 2026-11-21
    fireEvent.click(screen.getByRole('button', { name: 'Jump to today' }));
    expect(screen.getByText('2026-11-08 - 2026-11-21')).toBeDefined();
  });

  it('opens and closes Unscheduled tray listing issues lacking due_date', () => {
    render(
      <CalendarView
        issues={TEST_ISSUES}
        projectKey="KAN"
        initialYear={2026}
        initialMonth={11}
        today="2026-11-12"
      />
    );

    const unscheduledToggle = screen.getByRole('button', { name: /Unscheduled \(1\)/i });
    expect(unscheduledToggle).toBeDefined();

    // Tray is initially not in document
    expect(screen.queryByTestId('calendar-unscheduled-tray')).toBeNull();

    // Click toggle to open
    fireEvent.click(unscheduledToggle);
    expect(screen.getByTestId('calendar-unscheduled-tray')).toBeDefined();
    expect(screen.getByTestId('unscheduled-pill-KAN-999')).toBeDefined();

    // Close tray
    fireEvent.click(screen.getByRole('button', { name: 'Close unscheduled tray' }));
    expect(screen.queryByTestId('calendar-unscheduled-tray')).toBeNull();
  });

  it('opens +N more dialog popover when > 3 issues share a date', () => {
    const multiIssues: IssueItem[] = [
      {
        id: 'i1',
        key: 'KAN-1',
        summary: 'Task 1',
        state: { id: 's1', name: 'Todo', group: 'unstarted' },
        priority: { slug: 'medium', label: 'Medium' },
        due_date: '2026-11-18',
      },
      {
        id: 'i2',
        key: 'KAN-2',
        summary: 'Task 2',
        state: { id: 's1', name: 'Todo', group: 'unstarted' },
        priority: { slug: 'medium', label: 'Medium' },
        due_date: '2026-11-18',
      },
      {
        id: 'i3',
        key: 'KAN-3',
        summary: 'Task 3',
        state: { id: 's1', name: 'Todo', group: 'unstarted' },
        priority: { slug: 'medium', label: 'Medium' },
        due_date: '2026-11-18',
      },
      {
        id: 'i4',
        key: 'KAN-4',
        summary: 'Task 4',
        state: { id: 's1', name: 'In Progress', group: 'started' },
        priority: { slug: 'medium', label: 'Medium' },
        due_date: '2026-11-10', // overdue
      },
      {
        id: 'i5',
        key: 'KAN-5',
        summary: 'Task 5',
        state: { id: 's2', name: 'Cancelled', group: 'cancelled' },
        priority: { slug: 'medium', label: 'Medium' },
        due_date: '2026-11-10',
      },
      {
        id: 'i6',
        key: 'KAN-6',
        summary: 'Task 6',
        state: { id: 's1', name: 'Todo', group: 'unstarted' },
        priority: { slug: 'medium', label: 'Medium' },
        due_date: '2026-11-10',
      },
      {
        id: 'i7',
        key: 'KAN-7',
        summary: 'Task 7',
        state: { id: 's1', name: 'Todo', group: 'unstarted' },
        priority: { slug: 'medium', label: 'Medium' },
        due_date: '2026-11-10',
      },
    ];

    render(
      <CalendarView
        issues={multiIssues}
        projectKey="KAN"
        initialYear={2026}
        initialMonth={11}
        today="2026-11-12"
      />
    );

    // +1 more button appears for 2026-11-10 (4 issues on 2026-11-10)
    const moreBtn = screen.getByTestId('calendar-more-2026-11-10');
    expect(moreBtn.textContent).toBe('+1 more');

    // Click to open popover
    fireEvent.click(moreBtn);
    const popover = screen.getByRole('dialog', { name: 'Issues on 2026-11-10' });
    expect(popover).toBeDefined();

    // Drag start on a pill inside popover
    const popoverPill = popover.querySelector('a');
    if (popoverPill) {
      fireEvent.dragStart(popoverPill, {
        dataTransfer: { setData: vi.fn() },
      });
    }

    // Close popover via close button
    fireEvent.click(screen.getByRole('button', { name: 'Close overflow popover' }));
    expect(screen.queryByRole('dialog', { name: 'Issues on 2026-11-10' })).toBeNull();

    // Toggle open and closed via moreBtn click
    fireEvent.click(moreBtn);
    expect(screen.getByRole('dialog', { name: 'Issues on 2026-11-10' })).toBeDefined();
    fireEvent.click(moreBtn);
    expect(screen.queryByRole('dialog', { name: 'Issues on 2026-11-10' })).toBeNull();
  });

  it('drags unscheduled pill and tests empty calendar fallback to current month', () => {
    const { container } = render(
      <CalendarView
        issues={TEST_ISSUES}
        projectKey="KAN"
        initialYear={2026}
        initialMonth={11}
        today="2026-11-12"
      />
    );

    // Drag over cell10 then dragLeave on cell11 (mismatched date) and cell10 (matching date)
    const cell10 = container.querySelector('[data-date="2026-11-10"]');
    const cell11 = container.querySelector('[data-date="2026-11-11"]');
    if (cell10 && cell11) {
      fireEvent.dragOver(cell10, { dataTransfer: { dropEffect: 'move' } });
      fireEvent.dragLeave(cell11);
      fireEvent.dragLeave(cell10);
    }

    // Drop on cell with no dataTransfer data and no active drag (droppedKey is empty)
    if (cell10) {
      fireEvent.drop(cell10, {
        dataTransfer: { getData: () => '' },
      });
    }

    // Open unscheduled tray and drag unscheduled pill
    fireEvent.click(screen.getByRole('button', { name: /Unscheduled/i }));
    const unscheduledPill = screen.getByTestId('unscheduled-pill-KAN-999');
    fireEvent.dragStart(unscheduledPill, {
      dataTransfer: { setData: vi.fn() },
    });

    // Render with no issues and no initialYear -> defaults to current month
    const { unmount } = render(<CalendarView issues={[]} projectKey="KAN" />);
    expect(screen.getAllByTestId('calendar-view').length).toBeGreaterThan(0);
    unmount();
  });

  it('highlights overdue items only when due_date < today and not completed or cancelled', () => {
    const { container } = render(
      <CalendarView
        issues={TEST_ISSUES}
        projectKey="KAN"
        initialYear={2026}
        initialMonth={11}
        today="2026-11-12"
      />
    );

    // KAN-100 is due 2026-11-10 (before today 2026-11-12) and state is 'started' -> overdue
    const pill100 = container.querySelector('[data-issue-key="KAN-100"]');
    expect(pill100?.classList.contains('calendar-issue-pill--overdue')).toBe(true);

    // KAN-142 is due 2026-11-18 (after today 2026-11-12) -> NOT overdue
    const pill142 = container.querySelector('[data-issue-key="KAN-142"]');
    expect(pill142?.classList.contains('calendar-issue-pill--overdue')).toBe(false);

    // KAN-143 is due 2026-11-05 (before today) but state.group is 'completed' -> NOT overdue
    // In 2-week view anchored at 2026-11-08 - 2026-11-21, navigate Prev to see 2026-11-05
    fireEvent.click(screen.getByRole('button', { name: 'Previous 2 weeks' }));
    const pill143 = container.querySelector('[data-issue-key="KAN-143"]');
    expect(pill143?.classList.contains('calendar-issue-pill--overdue')).toBe(false);
  });

  it('drops unscheduled issue onto a cell and calls PATCH with target date', async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: () =>
        Promise.resolve({
          id: 'issue-unscheduled',
          key: 'KAN-999',
          summary: 'Unscheduled Maintenance',
          due_date: '2026-11-20',
        }),
    });
    globalThis.fetch = mockFetch;

    const { container } = render(
      <CalendarView
        issues={TEST_ISSUES}
        projectKey="KAN"
        initialYear={2026}
        initialMonth={11}
        today="2026-11-12"
      />
    );

    const cell20 = container.querySelector('[data-date="2026-11-20"]');
    expect(cell20).not.toBeNull();
    if (!cell20) return;

    // Simulate drag over and drop
    fireEvent.dragOver(cell20, {
      dataTransfer: { dropEffect: 'move' },
    });
    expect(cell20.classList.contains('calendar-day-cell--drag-over')).toBe(true);

    await act(async () => {
      fireEvent.drop(cell20, {
        dataTransfer: {
          getData: () => 'KAN-999',
        },
      });
      await Promise.resolve();
    });

    expect(mockFetch).toHaveBeenCalledWith('/api/v1/issues/KAN-999', {
      method: 'PATCH',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'application/json',
        'X-CSRF-Token': 'test-csrf-token-123',
      },
      credentials: 'same-origin',
      body: JSON.stringify({ due_date: '2026-11-20' }),
    });
  });

  it('reschedules scheduled issue using Alt+ArrowRight on keyboard', async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: () =>
        Promise.resolve({
          id: 'issue-142',
          key: 'KAN-142',
          start_date: '2026-11-12',
          due_date: '2026-11-19',
        }),
    });
    globalThis.fetch = mockFetch;

    render(
      <CalendarView
        issues={TEST_ISSUES}
        projectKey="KAN"
        initialYear={2026}
        initialMonth={11}
        today="2026-11-12"
      />
    );

    const pill142 = screen.getByTestId('calendar-pill-KAN-142');

    // Alt+ArrowRight shifts range +1 day: due 2026-11-19, start 2026-11-12
    await act(async () => {
      fireEvent.keyDown(pill142, { key: 'ArrowRight', altKey: true });
      await Promise.resolve();
    });

    expect(mockFetch).toHaveBeenCalledWith('/api/v1/issues/KAN-142', {
      method: 'PATCH',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'application/json',
        'X-CSRF-Token': 'test-csrf-token-123',
      },
      credentials: 'same-origin',
      body: JSON.stringify({ start_date: '2026-11-12', due_date: '2026-11-19' }),
    });
  });

  it('renders mobile week strip and agenda list when selected date changes', () => {
    const mobileIssues: IssueItem[] = [
      ...TEST_ISSUES,
      {
        id: 'issue-cancelled',
        key: 'KAN-CANCELLED',
        summary: 'Cancelled bug',
        state: { id: 's-can', name: 'Cancelled', group: 'cancelled' },
        priority: { slug: 'low', label: 'Low' },
        due_date: '2026-11-10',
      },
      {
        id: 'issue-completed',
        key: 'KAN-COMPLETED',
        summary: 'Completed feature',
        state: { id: 's-done', name: 'Done', group: 'completed' },
        priority: { slug: 'medium', label: 'Medium' },
        due_date: '2026-11-10',
      },
    ];

    const { container } = render(
      <CalendarView
        issues={mobileIssues}
        projectKey="KAN"
        initialYear={2026}
        initialMonth={11}
        today="2026-11-18"
      />
    );

    const mobileAgenda = screen.getByTestId('calendar-mobile-agenda');
    expect(mobileAgenda).toBeDefined();

    // KAN-142 is due 2026-11-18 so it appears in agenda
    expect(screen.getByTestId('agenda-row-KAN-142')).toBeDefined();

    // Click 2026-11-10 button in week strip (KAN-100 is overdue relative to 2026-11-18, KAN-CANCELLED is not overdue because it is cancelled)
    const dayBtn10 = container.querySelector('.calendar-week-day-btn[data-date="2026-11-10"]');
    if (dayBtn10) {
      fireEvent.click(dayBtn10);
      const row100 = screen.getByTestId('agenda-row-KAN-100');
      expect(row100.classList.contains('calendar-agenda-row--overdue')).toBe(true);
      const rowCan = screen.getByTestId('agenda-row-KAN-CANCELLED');
      expect(rowCan.classList.contains('calendar-agenda-row--overdue')).toBe(false);
      const rowDone = screen.getByTestId('agenda-row-KAN-COMPLETED');
      expect(rowDone.classList.contains('calendar-agenda-row--overdue')).toBe(false);
    }

    // Click another day button in week strip (e.g. 2026-11-19)
    const dayBtn = container.querySelector('.calendar-week-day-btn[data-date="2026-11-19"]');
    if (dayBtn) {
      fireEvent.click(dayBtn);
      expect(screen.getByText('No issues scheduled for this date')).toBeDefined();
    }
  });

  it('navigates 2-week windows across year boundaries', () => {
    // Start in January 2026
    const { unmount } = render(
      <CalendarView
        issues={TEST_ISSUES}
        projectKey="KAN"
        initialYear={2026}
        initialMonth={1}
        today="2026-01-05"
      />
    );

    // Week starts Sunday 2026-01-04 to 2026-01-17
    expect(screen.getByText('2026-01-04 - 2026-01-17')).toBeDefined();

    // Click Prev -> December 2025
    fireEvent.click(screen.getByRole('button', { name: 'Previous 2 weeks' }));
    expect(screen.getByText('2025-12-21 - 2026-01-03')).toBeDefined();

    unmount();

    // Start in December 2026
    render(
      <CalendarView
        issues={TEST_ISSUES}
        projectKey="KAN"
        initialYear={2026}
        initialMonth={12}
        today="2026-12-28"
      />
    );

    // Week starts Sunday 2026-12-27 to 2027-01-09
    expect(screen.getByText('2026-12-27 - 2027-01-09')).toBeDefined();

    // Click Next -> January 2027
    fireEvent.click(screen.getByRole('button', { name: 'Next 2 weeks' }));
    expect(screen.getByText('2027-01-10 - 2027-01-23')).toBeDefined();
  });

  it('handles keyboard Alt+ArrowLeft, Alt+ArrowUp, Alt+ArrowDown, and ignores non-alt keys', async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: () => Promise.resolve({ id: 'issue-142', key: 'KAN-142' }),
    });
    globalThis.fetch = mockFetch;

    render(
      <CalendarView
        issues={TEST_ISSUES}
        projectKey="KAN"
        initialYear={2026}
        initialMonth={11}
        today="2026-11-12"
      />
    );

    const pill142 = screen.getByTestId('calendar-pill-KAN-142');

    // Non-alt key ignored, and Alt+non-arrow key ignored
    fireEvent.keyDown(pill142, { key: 'ArrowRight', altKey: false });
    fireEvent.keyDown(pill142, { key: 'Tab', altKey: true });
    expect(mockFetch).not.toHaveBeenCalled();

    // Alt+ArrowLeft: -1 day (due 2026-11-17, start 2026-11-10)
    await act(async () => {
      fireEvent.keyDown(pill142, { key: 'ArrowLeft', altKey: true });
      await Promise.resolve();
    });
    expect(mockFetch).toHaveBeenCalledWith(
      '/api/v1/issues/KAN-142',
      expect.objectContaining({
        body: JSON.stringify({ start_date: '2026-11-10', due_date: '2026-11-17' }),
      })
    );

    // Alt+ArrowUp: -7 days
    await act(async () => {
      const p1 = screen.getByTestId('calendar-pill-KAN-142');
      fireEvent.keyDown(p1, { key: 'ArrowUp', altKey: true });
      await Promise.resolve();
    });
    expect(mockFetch).toHaveBeenCalledWith(
      '/api/v1/issues/KAN-142',
      expect.objectContaining({
        body: JSON.stringify({ start_date: '2026-11-03', due_date: '2026-11-10' }),
      })
    );

    // Alt+ArrowDown: +7 days
    await act(async () => {
      const p2 = screen.getByTestId('calendar-pill-KAN-142');
      fireEvent.keyDown(p2, { key: 'ArrowDown', altKey: true });
      await Promise.resolve();
    });
    expect(mockFetch).toHaveBeenCalledWith(
      '/api/v1/issues/KAN-142',
      expect.objectContaining({
        body: JSON.stringify({ start_date: '2026-11-10', due_date: '2026-11-17' }),
      })
    );
  });

  it('handles drag leave and clamps start_date when start_date > targetDate', async () => {
    const clampIssues: IssueItem[] = [
      {
        id: 'i-clamp',
        key: 'KAN-555',
        summary: 'Clamp check',
        state: { id: 's1', name: 'Todo', group: 'unstarted' },
        priority: { slug: 'medium', label: 'Medium' },
        start_date: '2026-11-20',
        due_date: null,
      },
    ];

    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: () => Promise.resolve({ id: 'i-clamp', key: 'KAN-555' }),
    });
    globalThis.fetch = mockFetch;

    const { container } = render(
      <CalendarView
        issues={clampIssues}
        projectKey="KAN"
        initialYear={2026}
        initialMonth={11}
        today="2026-11-12"
      />
    );

    const cell10 = container.querySelector('[data-date="2026-11-10"]');
    expect(cell10).not.toBeNull();
    if (!cell10) return;

    // Drag over then drag leave
    fireEvent.dragOver(cell10, { dataTransfer: { dropEffect: 'move' } });
    expect(cell10.classList.contains('calendar-day-cell--drag-over')).toBe(true);
    fireEvent.dragLeave(cell10);
    expect(cell10.classList.contains('calendar-day-cell--drag-over')).toBe(false);

    // Drop KAN-555 onto 2026-11-10 (start_date 2026-11-20 > targetDate 2026-11-10 -> clamps start_date)
    await act(async () => {
      fireEvent.drop(cell10, {
        dataTransfer: { getData: () => 'KAN-555' },
      });
      await Promise.resolve();
    });

    expect(mockFetch).toHaveBeenCalledWith(
      '/api/v1/issues/KAN-555',
      expect.objectContaining({
        body: JSON.stringify({ start_date: '2026-11-10', due_date: '2026-11-10' }),
      })
    );
  });

  it('renders empty unscheduled message when all issues have due dates', () => {
    const scheduledOnly: IssueItem[] = [
      {
        id: 'i-sched',
        key: 'KAN-111',
        summary: 'Fully scheduled',
        state: { id: 's1', name: 'Todo', group: 'unstarted' },
        priority: { slug: 'low', label: 'Low' },
        due_date: '2026-11-15',
      },
    ];

    render(
      <CalendarView
        issues={scheduledOnly}
        projectKey="KAN"
        initialYear={2026}
        initialMonth={11}
        today="2026-11-12"
      />
    );

    const toggle = screen.getByRole('button', { name: /Unscheduled \(0\)/i });
    fireEvent.click(toggle);

    expect(screen.getByText('No unscheduled issues.')).toBeDefined();
  });

  it('verifies strict CSP invariant: zero elements have style attribute string in DOM', () => {
    const { container } = render(
      <CalendarView
        issues={TEST_ISSUES}
        projectKey="KAN"
        initialYear={2026}
        initialMonth={11}
        today="2026-11-12"
      />
    );

    const styledElements = container.querySelectorAll('[style]');
    expect(styledElements.length).toBe(0);
  });

  it('rolls back schedule on server error', async () => {
    const mockFailFetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 412,
      text: () => Promise.resolve(JSON.stringify({ code: 'PRECONDITION_FAILED' })),
    });
    globalThis.fetch = mockFailFetch;

    render(
      <CalendarView
        issues={TEST_ISSUES}
        projectKey="KAN"
        initialYear={2026}
        initialMonth={11}
        today="2026-11-12"
      />
    );

    const pill142 = screen.getByTestId('calendar-pill-KAN-142');
    await act(async () => {
      fireEvent.keyDown(pill142, { key: 'ArrowLeft', altKey: true });
      await Promise.resolve();
    });

    expect(screen.getByRole('status').textContent).toContain('rolled back');
  });

  it('uses initialYear and initialMonth when today is omitted, and invokes onOpenPeek on pill and agenda click', () => {
    // 1. InitialYear/InitialMonth without today
    const { unmount: u1 } = render(
      <CalendarView
        issues={[]}
        projectKey="KAN"
        initialYear={2027}
        initialMonth={5}
      />
    );
    expect(screen.getByText('2027-04-25 - 2027-05-08')).toBeDefined();
    u1();

    // 2. onOpenPeek handler on desktop pill and mobile agenda row
    const onOpenPeek = vi.fn();
    const overdueIssue: IssueItem = {
      id: 'i-overdue',
      key: 'KAN-OVERDUE',
      summary: 'Overdue task',
      state: { id: 's-todo', name: 'To Do', group: 'unstarted' },
      priority: { slug: 'high', label: 'High' },
      due_date: '2026-11-16',
    };

    const { container } = render(
      <CalendarView
        issues={[overdueIssue]}
        projectKey="KAN"
        today="2026-11-18"
        onOpenPeek={onOpenPeek}
      />
    );

    // Desktop pill click with onOpenPeek
    const pill = screen.getByTestId('calendar-pill-KAN-OVERDUE');
    fireEvent.click(pill);
    expect(onOpenPeek).toHaveBeenCalledWith('KAN-OVERDUE');

    // Select date 2026-11-16 on mobile strip
    const dateBtn = container.querySelector('button[data-date="2026-11-16"]');
    expect(dateBtn).toBeTruthy();
    if (dateBtn) {
      fireEvent.click(dateBtn);
    }

    const agendaRow = screen.getByTestId('agenda-row-KAN-OVERDUE');
    expect(agendaRow.className).toContain('calendar-agenda-row--overdue');

    fireEvent.click(agendaRow);
    expect(onOpenPeek).toHaveBeenCalledTimes(2);
  });

  it('covers outside month cell styling and overflow popover pill peek click', () => {
    const onOpenPeek = vi.fn();
    const fourIssues: IssueItem[] = Array.from({ length: 4 }, (_, i) => ({
      id: `ov-${String(i)}`,
      key: `KAN-OV-${String(i)}`,
      summary: `Overflow task ${String(i)}`,
      state: { id: 's1', name: 'Todo', group: 'unstarted' },
      priority: { slug: 'low', label: 'Low' },
      due_date: '2026-11-30',
    }));

    render(
      <CalendarView
        issues={fourIssues}
        projectKey="KAN"
        today="2026-11-28"
        onOpenPeek={onOpenPeek}
      />
    );

    // Open overflow popover
    const moreBtn = screen.getByTestId('calendar-more-2026-11-30');
    fireEvent.click(moreBtn);

    // Find popover and click pill inside
    const popover = screen.getByRole('dialog', { name: 'Issues on 2026-11-30' });
    expect(popover).toBeDefined();

    const popoverPill = popover.querySelector('a[data-issue-key="KAN-OV-0"]');
    if (popoverPill) fireEvent.click(popoverPill);
    expect(onOpenPeek).toHaveBeenCalledWith('KAN-OV-0');

    // Close popover
    const closeBtn = screen.getByRole('button', { name: 'Close overflow popover' });
    fireEvent.click(closeBtn);
    expect(screen.queryByRole('dialog', { name: 'Issues on 2026-11-30' })).toBeNull();
  });
});
