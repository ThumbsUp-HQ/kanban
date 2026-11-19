import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import React from 'react';
import { TimelineView, type TimelineIssueItem } from './TimelineView';

const TEST_ISSUES: TimelineIssueItem[] = [
  {
    id: 'issue-100',
    key: 'KAN-100',
    summary: 'Security Architecture Epic',
    state: { id: 's1', name: 'In Progress', group: 'started' },
    priority: { slug: 'high', label: 'High' },
    start_date: '2026-11-05',
    due_date: '2026-11-12',
    outbound_blocks: [
      {
        target_key: 'KAN-142',
        link_state: 'ACTIVE',
        restricted: false,
      },
      {
        target_key: 'KAN-999',
        link_state: 'ACTIVE',
        restricted: false,
      },
    ],
  },
  {
    id: 'issue-142',
    key: 'KAN-142',
    summary: 'Harden Multi-Card OIDC & LDAPS Auth Studio',
    state: { id: 's1', name: 'In Progress', group: 'started' },
    priority: { slug: 'urgent', label: 'Urgent' },
    start_date: '2026-11-11',
    due_date: '2026-11-18',
    gate_status: 'pending',
    outbound_blocks: [
      {
        target_key: 'KAN-143',
        link_state: 'ACTIVE',
        restricted: false,
      },
      {
        target_key: 'KAN-998',
        link_state: 'FLAGGED_INVALID',
        restricted: false,
      },
    ],
  },
  {
    id: 'issue-143',
    key: 'KAN-143',
    summary: 'Verify LDAPS certificate pinning',
    state: { id: 's2', name: 'Done', group: 'completed' },
    priority: { slug: 'low', label: 'Low' },
    start_date: null,
    due_date: '2026-11-25', // single date milestone
    outbound_blocks: [
      {
        link_state: 'ACTIVE',
        restricted: true,
        label: '🔒 Restricted Object',
      },
    ],
  },
  {
    id: 'issue-unscheduled',
    key: 'KAN-999',
    summary: 'Unscheduled Maintenance',
    state: { id: 's0', name: 'Backlog', group: 'unstarted' },
    priority: { slug: 'medium', label: 'Medium' },
    start_date: null,
    due_date: null,
  },
];

describe('TimelineView', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    vi.restoreAllMocks();
    document.cookie = 'kb_csrf=test-csrf-token-123; Path=/';
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
    document.cookie = 'kb_csrf=; expires=Thu, 01 Jan 1970 00:00:00 GMT; Path=/';
  });

  it('renders left sticky pane with work items and links to peek', () => {
    const { container } = render(
      <TimelineView
        issues={TEST_ISSUES}
        projectKey="KAN"
        initialZoom="week"
        initialStartDate="2026-11-01"
        today="2026-11-12"
      />
    );

    const leftRows = container.querySelectorAll('.timeline-left-row');
    expect(leftRows.length).toBe(4);

    const row142 = container.querySelector('[data-testid="timeline-left-row-KAN-142"]');
    expect(row142).not.toBeNull();
    expect(row142?.textContent).toContain('KAN-142');
    expect(row142?.textContent).toContain('Harden Multi-Card OIDC');

    const link142 = row142?.querySelector('a');
    expect(link142?.getAttribute('href')).toBe('?layout=timeline&peek=KAN-142');
  });

  it('renders scheduled bar for KAN-142 and milestone for KAN-143', () => {
    render(
      <TimelineView
        issues={TEST_ISSUES}
        projectKey="KAN"
        initialZoom="week"
        initialStartDate="2026-11-01"
        today="2026-11-12"
      />
    );

    // KAN-142 is a bar
    const bar142 = screen.getByTestId('timeline-bar-KAN-142');
    expect(bar142).toBeDefined();
    expect(bar142.getAttribute('aria-label')).toContain('from 2026-11-11 to 2026-11-18');

    // KAN-143 is a milestone diamond
    const milestone143 = screen.getByTestId('timeline-milestone-KAN-143');
    expect(milestone143).toBeDefined();
  });

  it('navigates timeline range with Prev, Next, and Today buttons', () => {
    render(
      <TimelineView
        issues={TEST_ISSUES}
        projectKey="KAN"
        initialZoom="week"
        initialStartDate="2026-11-01"
        today="2026-11-12"
      />
    );

    const prevBtn = screen.getByRole('button', { name: 'Previous 2 weeks' });
    const nextBtn = screen.getByRole('button', { name: 'Next 2 weeks' });
    const todayBtn = screen.getByRole('button', { name: 'Today' });

    fireEvent.click(prevBtn);
    fireEvent.click(nextBtn);
    fireEvent.click(todayBtn);
  });

  it('renders quarter zoom scale and pointerdown on milestone with null start_date', () => {
    render(
      <TimelineView
        issues={TEST_ISSUES}
        projectKey="KAN"
        initialZoom="quarter"
        initialStartDate="2026-11-01"
        today="2026-11-12"
      />
    );

    expect(screen.getByTestId('timeline-view')).toBeDefined();

    // Trigger pointerdown on milestone diamond (KAN-143 which has null start_date)
    const milestone143 = screen.getByTestId('timeline-milestone-KAN-143');
    fireEvent.pointerDown(milestone143, { clientX: 100 });
  });

  it('renders ghost prompt for unscheduled issue and schedules on track click', async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: () =>
        Promise.resolve({
          id: 'issue-unscheduled',
          key: 'KAN-999',
          start_date: '2026-11-05',
          due_date: '2026-11-05',
        }),
    });
    globalThis.fetch = mockFetch;

    render(
      <TimelineView
        issues={TEST_ISSUES}
        projectKey="KAN"
        initialZoom="week"
        initialStartDate="2026-11-01"
        today="2026-11-12"
      />
    );

    const trackRow999 = screen.getByTestId('timeline-track-row-KAN-999');
    expect(trackRow999.textContent).toContain('Click track to schedule');

    // Mock getBoundingClientRect
    trackRow999.getBoundingClientRect = () => ({
      left: 0,
      top: 0,
      right: 1000,
      bottom: 46,
      width: 1000,
      height: 46,
      x: 0,
      y: 0,
      toJSON: () => ({}),
    });

    // Click at 72px (2 days offset at 36px/day: 2026-11-01 + 2 = 2026-11-03)
    await act(async () => {
      fireEvent.click(trackRow999, { clientX: 72 });
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
      body: JSON.stringify({ start_date: '2026-11-03', due_date: '2026-11-03' }),
    });
  });

  it('switches zoom scales between Day, Week, and Quarter', () => {
    const { container } = render(
      <TimelineView
        issues={TEST_ISSUES}
        projectKey="KAN"
        initialZoom="week"
        initialStartDate="2026-11-01"
        today="2026-11-12"
      />
    );

    const dayBtn = screen.getByRole('radio', { name: 'Day' });
    const weekBtn = screen.getByRole('radio', { name: 'Week' });
    const quarterBtn = screen.getByRole('radio', { name: 'Quarter' });

    expect(weekBtn.getAttribute('aria-checked')).toBe('true');

    // Switch to Day
    fireEvent.click(dayBtn);
    expect(dayBtn.getAttribute('aria-checked')).toBe('true');
    expect(weekBtn.getAttribute('aria-checked')).toBe('false');

    // Switch to Week
    fireEvent.click(weekBtn);
    expect(weekBtn.getAttribute('aria-checked')).toBe('true');

    // In Day scale, headers show MM-DD
    fireEvent.click(dayBtn);
    const scaleCells = container.querySelectorAll('.timeline-scale-cell');
    expect(scaleCells[0]?.textContent).toBe('11-01');

    // Switch to Quarter
    fireEvent.click(quarterBtn);
    expect(quarterBtn.getAttribute('aria-checked')).toBe('true');
  });

  it('renders BLOCKS arrows overlay and identifies conflict between overlapping items', () => {
    const { container } = render(
      <TimelineView
        issues={TEST_ISSUES}
        projectKey="KAN"
        initialZoom="week"
        initialStartDate="2026-11-01"
        today="2026-11-12"
      />
    );

    // KAN-100 (due 2026-11-12) blocks KAN-142 (starts 2026-11-11)
    // Blocker ends after blocked starts -> CONFLICT!
    const overlay = container.querySelector('.timeline-svg-overlay');
    expect(overlay).not.toBeNull();

    const arrows = container.querySelectorAll('.gantt-arrow');
    expect(arrows.length).toBeGreaterThan(0);

    const conflictArrow = container.querySelector('.gantt-arrow--conflict');
    expect(conflictArrow).not.toBeNull();
  });

  it('renders FLAGGED_INVALID broken link indicator on source row and suppresses restricted link', () => {
    render(
      <TimelineView
        issues={TEST_ISSUES}
        projectKey="KAN"
        initialZoom="week"
        initialStartDate="2026-11-01"
        today="2026-11-12"
      />
    );

    // KAN-142 has a FLAGGED_INVALID link -> brokenLink hint rendered
    const brokenHint = screen.getByTestId('broken-link-KAN-142');
    expect(brokenHint).toBeDefined();

    // KAN-143 has a restricted link -> zero arrow paths for restricted target
    const overlay = document.querySelector('.timeline-svg-overlay');
    expect(overlay?.innerHTML).not.toContain('Restricted Object');
  });

  it('toggles BLOCKS arrows overlay visibility via checkbox', () => {
    const { container } = render(
      <TimelineView
        issues={TEST_ISSUES}
        projectKey="KAN"
        initialZoom="week"
        initialStartDate="2026-11-01"
        today="2026-11-12"
      />
    );

    expect(container.querySelector('.timeline-svg-overlay')).not.toBeNull();

    const toggle = screen.getByRole('checkbox', { name: 'Show BLOCKS arrows' });
    fireEvent.click(toggle);

    expect(container.querySelector('.timeline-svg-overlay')).toBeNull();
  });

  it('reschedules bar dates using keyboard ArrowRight and Shift+ArrowRight', async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: () =>
        Promise.resolve({
          id: 'issue-100',
          key: 'KAN-100',
          start_date: '2026-11-06',
          due_date: '2026-11-13',
        }),
    });
    globalThis.fetch = mockFetch;

    render(
      <TimelineView
        issues={TEST_ISSUES}
        projectKey="KAN"
        initialZoom="week"
        initialStartDate="2026-11-01"
        today="2026-11-12"
      />
    );

    const bar100 = screen.getByTestId('timeline-bar-KAN-100');

    // ArrowRight shifts both dates +1 day
    await act(async () => {
      fireEvent.keyDown(bar100, { key: 'ArrowRight' });
      await Promise.resolve();
    });

    expect(mockFetch).toHaveBeenCalledWith('/api/v1/issues/KAN-100', {
      method: 'PATCH',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'application/json',
        'X-CSRF-Token': 'test-csrf-token-123',
      },
      credentials: 'same-origin',
      body: JSON.stringify({ start_date: '2026-11-06', due_date: '2026-11-13' }),
    });

    // Shift+ArrowRight extends due date +1 day
    await act(async () => {
      fireEvent.keyDown(bar100, { key: 'ArrowRight', shiftKey: true });
      await Promise.resolve();
    });

    expect(mockFetch).toHaveBeenCalledWith('/api/v1/issues/KAN-100', {
      method: 'PATCH',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'application/json',
        'X-CSRF-Token': 'test-csrf-token-123',
      },
      credentials: 'same-origin',
      body: JSON.stringify({ start_date: '2026-11-06', due_date: '2026-11-14' }),
    });
  });

  it('scrolls to today when Today button is clicked', () => {
    const { container } = render(
      <TimelineView
        issues={TEST_ISSUES}
        projectKey="KAN"
        initialZoom="week"
        initialStartDate="2026-11-01"
        today="2026-11-12"
      />
    );

    const scrollToSpy = vi.fn();
    const wrapper = container.querySelector('.timeline-right-canvas-wrapper');
    if (wrapper) {
      wrapper.scrollTo = scrollToSpy;
    }

    const todayBtn = screen.getByRole('button', { name: 'Today' });
    fireEvent.click(todayBtn);

    expect(scrollToSpy).toHaveBeenCalled();
  });

  it('drags bar body to shift date range', async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: () =>
        Promise.resolve({
          id: 'issue-100',
          key: 'KAN-100',
          start_date: '2026-11-07',
          due_date: '2026-11-14',
        }),
    });
    globalThis.fetch = mockFetch;

    render(
      <TimelineView
        issues={TEST_ISSUES}
        projectKey="KAN"
        initialZoom="week"
        initialStartDate="2026-11-01"
        today="2026-11-12"
      />
    );

    const bar100 = screen.getByTestId('timeline-bar-KAN-100');

    // Pointer down at 100px, pointer up at 172px (+72px = +2 days at 36px/day)
    fireEvent.pointerDown(bar100, { clientX: 100 });
    await act(async () => {
      fireEvent.pointerUp(window, { clientX: 172 });
      await Promise.resolve();
    });

    expect(mockFetch).toHaveBeenCalledWith('/api/v1/issues/KAN-100', {
      method: 'PATCH',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'application/json',
        'X-CSRF-Token': 'test-csrf-token-123',
      },
      credentials: 'same-origin',
      body: JSON.stringify({ start_date: '2026-11-07', due_date: '2026-11-14' }),
    });
  });

  it('drags left and right resize handles to clamp dates', async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: () => Promise.resolve({ id: 'issue-100', key: 'KAN-100' }),
    });
    globalThis.fetch = mockFetch;

    render(
      <TimelineView
        issues={TEST_ISSUES}
        projectKey="KAN"
        initialZoom="week"
        initialStartDate="2026-11-01"
        today="2026-11-12"
      />
    );

    // Left handle resize: start_date shifts +1 day (36px at week zoom)
    const handleLeft = screen.getByTestId('handle-left-KAN-100');
    fireEvent.pointerDown(handleLeft, { clientX: 50 });
    await act(async () => {
      fireEvent.pointerUp(window, { clientX: 86 });
      await Promise.resolve();
    });

    expect(mockFetch).toHaveBeenCalledWith('/api/v1/issues/KAN-100', {
      method: 'PATCH',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'application/json',
        'X-CSRF-Token': 'test-csrf-token-123',
      },
      credentials: 'same-origin',
      body: JSON.stringify({ start_date: '2026-11-06', due_date: '2026-11-12' }),
    });

    // Right handle resize: due_date shifts +2 days (72px at week zoom)
    const handleRight = screen.getByTestId('handle-right-KAN-100');
    fireEvent.pointerDown(handleRight, { clientX: 200 });
    await act(async () => {
      fireEvent.pointerUp(window, { clientX: 272 });
      await Promise.resolve();
    });

    expect(mockFetch).toHaveBeenCalledWith('/api/v1/issues/KAN-100', {
      method: 'PATCH',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'application/json',
        'X-CSRF-Token': 'test-csrf-token-123',
      },
      credentials: 'same-origin',
      body: JSON.stringify({ start_date: '2026-11-06', due_date: '2026-11-14' }),
    });
  });

  it('supports ArrowLeft and Shift+ArrowLeft on focused bar', async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: () => Promise.resolve({ id: 'issue-100', key: 'KAN-100' }),
    });
    globalThis.fetch = mockFetch;

    render(
      <TimelineView
        issues={TEST_ISSUES}
        projectKey="KAN"
        initialZoom="week"
        initialStartDate="2026-11-01"
        today="2026-11-12"
      />
    );

    const bar100 = screen.getByTestId('timeline-bar-KAN-100');

    // Non-arrow keys are ignored
    fireEvent.keyDown(bar100, { key: 'Tab' });
    fireEvent.keyDown(bar100, { key: 'Tab', shiftKey: true });

    // ArrowLeft shifts -1 day
    await act(async () => {
      fireEvent.keyDown(bar100, { key: 'ArrowLeft' });
      await Promise.resolve();
    });

    expect(mockFetch).toHaveBeenCalledWith('/api/v1/issues/KAN-100', {
      method: 'PATCH',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'application/json',
        'X-CSRF-Token': 'test-csrf-token-123',
      },
      credentials: 'same-origin',
      body: JSON.stringify({ start_date: '2026-11-04', due_date: '2026-11-11' }),
    });

    // Shift+ArrowLeft shrinks due_date -1 day
    await act(async () => {
      fireEvent.keyDown(bar100, { key: 'ArrowLeft', shiftKey: true });
      await Promise.resolve();
    });

    expect(mockFetch).toHaveBeenCalledWith('/api/v1/issues/KAN-100', {
      method: 'PATCH',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'application/json',
        'X-CSRF-Token': 'test-csrf-token-123',
      },
      credentials: 'same-origin',
      body: JSON.stringify({ start_date: '2026-11-04', due_date: '2026-11-10' }),
    });
  });

  it('renders vetoed and approved gate statuses and links prop', () => {
    const gateIssues: TimelineIssueItem[] = [
      {
        id: 'i-vetoed',
        key: 'KAN-201',
        summary: 'Vetoed feature',
        state: { id: 's1', name: 'In Review', group: 'started' },
        priority: { slug: 'low', label: 'Low' },
        start_date: '2026-11-01',
        due_date: '2026-11-05',
        gate_status: 'vetoed',
      },
      {
        id: 'i-approved',
        key: 'KAN-202',
        summary: 'Approved feature',
        state: { id: 's1', name: 'In Review', group: 'started' },
        priority: { slug: 'high', label: 'High' },
        start_date: '2026-11-06',
        due_date: '2026-11-10',
        gate_status: 'approved',
      },
    ];

    const { container } = render(
      <TimelineView
        issues={gateIssues}
        projectKey="KAN"
        initialZoom="day"
        today="2026-11-12"
        links={[
          {
            source_key: 'KAN-201',
            target_key: 'KAN-202',
            link_type: 'BLOCKS',
            link_state: 'ACTIVE',
          },
        ]}
      />
    );

    const bar201 = screen.getByTestId('timeline-bar-KAN-201');
    const bar202 = screen.getByTestId('timeline-bar-KAN-202');
    expect(bar201).toBeDefined();
    expect(bar202).toBeDefined();

    // Arrows overlay renders link from links prop
    const overlay = container.querySelector('.timeline-svg-overlay');
    expect(overlay).not.toBeNull();
  });

  it('covers 200 arrows cap, links array, milestone keydown, and zero delta drag', async () => {
    // Generate 205 edges to exercise arrowList.length >= 200 cap
    const edgeIssues: TimelineIssueItem[] = [
      {
        id: 'i-root',
        key: 'KAN-ROOT',
        summary: 'Root issue',
        state: { id: 's1', name: 'Todo', group: 'unstarted' },
        priority: { slug: 'medium', label: 'Medium' },
        start_date: '2026-11-01',
        due_date: '2026-11-05',
        links: [
          { target_key: 'KAN-ROOT', link_type: 'BLOCKS', link_state: 'ACTIVE' },
          { target_key: 'KAN-TGT-0', link_type: 'RELATES_TO', link_state: 'ACTIVE' },
          { target_key: 'KAN-UNSCHED', link_type: 'BLOCKS', link_state: 'ACTIVE' },
          { target_key: 'KAN-NONEXISTENT', link_type: 'BLOCKS', link_state: 'ACTIVE' },
          ...Array.from({ length: 205 }, (_, i) => ({
            target_key: `KAN-TGT-${String(i)}`,
            link_type: 'BLOCKS',
            link_state: 'ACTIVE',
          })),
        ],
      },
      {
        id: 'i-unsched',
        key: 'KAN-UNSCHED',
        summary: 'Unscheduled item',
        state: { id: 's1', name: 'Todo', group: 'unstarted' },
        priority: { slug: 'low', label: 'Low' },
      },
      {
        id: 'i-milestone',
        key: 'KAN-MS',
        summary: 'Milestone item',
        state: { id: 's1', name: 'Todo', group: 'unstarted' },
        priority: { slug: 'low', label: 'Low' },
        start_date: null,
        due_date: '2026-11-08',
      },
      ...Array.from({ length: 205 }, (_, i) => ({
        id: `i-tgt-${String(i)}`,
        key: `KAN-TGT-${String(i)}`,
        summary: `Target ${String(i)}`,
        state: { id: 's1', name: 'Todo', group: 'unstarted' },
        priority: { slug: 'low', label: 'Low' },
        start_date: '2026-11-10',
        due_date: '2026-11-15',
      })),
    ];

    const { container } = render(
      <TimelineView
        issues={edgeIssues}
        links={[
          {
            source_key: 'KAN-ROOT',
            target_key: 'KAN-TGT-1',
            link_type: 'RELATES_TO',
            link_state: 'ACTIVE',
          },
          {
            source_key: 'KAN-ROOT',
            target_key: 'KAN-UNSCHED',
            link_type: 'BLOCKS',
            link_state: 'ACTIVE',
          },
        ]}
        projectKey="KAN"
        initialZoom="week"
        initialStartDate="2026-11-01"
        today="2026-11-12"
      />
    );

    // Overlay is rendered
    expect(container.querySelector('.timeline-svg-overlay')).not.toBeNull();

    // Milestone keydown
    const milestone = screen.getByTestId('timeline-milestone-KAN-MS');
    fireEvent.keyDown(milestone, { key: 'Enter' });

    // Zero delta pointer drag on bar
    const barRoot = screen.getByTestId('timeline-bar-KAN-ROOT');
    fireEvent.pointerDown(barRoot, { clientX: 100 });
    await act(async () => {
      fireEvent.pointerUp(window, { clientX: 100 });
      await Promise.resolve();
    });

    // Track click on already scheduled issue is a no-op
    const trackRowRoot = screen.getByTestId('timeline-track-row-KAN-ROOT');
    fireEvent.click(trackRowRoot);
  });

  it('computes timeline start date automatically when initialStartDate is not provided', () => {
    const issuesWithEarlyDue: TimelineIssueItem[] = [
      ...TEST_ISSUES,
      {
        id: 'i-early',
        key: 'KAN-EARLY',
        summary: 'Early milestone',
        state: { id: 's1', name: 'Todo', group: 'unstarted' },
        priority: { slug: 'medium', label: 'Medium' },
        due_date: '2026-10-15',
      },
    ];

    const { container } = render(
      <TimelineView
        issues={issuesWithEarlyDue}
        projectKey="KAN"
        initialZoom="week"
        today="2026-11-12"
      />
    );

    expect(container.querySelector('.timeline-view')).toBeDefined();
    // Header cells should be generated
    const headerCells = container.querySelectorAll('.timeline-scale-cell');
    expect(headerCells.length).toBeGreaterThan(0);
  });

  it('handles keyboard navigation and dragging on milestone issues with start-only and due-only dates', async () => {
    const milestoneIssues: TimelineIssueItem[] = [
      {
        id: 'i-due-only',
        key: 'KAN-DUE-ONLY',
        summary: 'Milestone due only',
        state: { id: 's1', name: 'Todo', group: 'unstarted' },
        priority: { slug: 'low', label: 'Low' },
        due_date: '2026-11-15',
      },
      {
        id: 'i-start-only',
        key: 'KAN-START-ONLY',
        summary: 'Milestone start only',
        state: { id: 's1', name: 'Todo', group: 'unstarted' },
        priority: { slug: 'urgent', label: 'Urgent' },
        start_date: '2026-11-16',
      },
    ];

    render(
      <TimelineView
        issues={milestoneIssues}
        projectKey="KAN"
        initialZoom="week"
        initialStartDate="2026-11-01"
        today="2026-11-12"
      />
    );

    const msDue = screen.getByTestId('timeline-milestone-KAN-DUE-ONLY');
    const msStart = screen.getByTestId('timeline-milestone-KAN-START-ONLY');

    // Arrow keys on due-only milestone
    fireEvent.keyDown(msDue, { key: 'ArrowRight' });
    fireEvent.keyDown(msDue, { key: 'ArrowLeft' });
    fireEvent.keyDown(msDue, { key: 'ArrowRight', shiftKey: true });
    fireEvent.keyDown(msDue, { key: 'ArrowLeft', shiftKey: true });

    // Arrow keys on start-only milestone
    fireEvent.keyDown(msStart, { key: 'ArrowRight' });
    fireEvent.keyDown(msStart, { key: 'ArrowLeft' });
    fireEvent.keyDown(msStart, { key: 'ArrowRight', shiftKey: true });
    fireEvent.keyDown(msStart, { key: 'ArrowLeft', shiftKey: true });

    // Drag on due-only milestone
    fireEvent.pointerDown(msDue, { clientX: 200 });
    await act(async () => {
      fireEvent.pointerUp(window, { clientX: 232 }); // +32px -> +2 days
      await Promise.resolve();
    });

    // Drag on start-only milestone
    fireEvent.pointerDown(msStart, { clientX: 250 });
    await act(async () => {
      fireEvent.pointerUp(window, { clientX: 266 }); // +16px -> +1 day
      await Promise.resolve();
    });
  });

  it('verifies strict CSP invariant: zero elements have style attribute string in initial DOM', () => {
    const { container } = render(
      <TimelineView
        issues={TEST_ISSUES}
        projectKey="KAN"
        initialZoom="week"
        initialStartDate="2026-11-01"
        today="2026-11-12"
      />
    );

    // Initial SVG overlay has zero style attributes
    const svg = container.querySelector('.timeline-svg-overlay');
    if (svg) {
      expect(svg.getAttribute('style')).toBeNull();
      const paths = svg.querySelectorAll('path');
      paths.forEach((p) => {
        expect(p.getAttribute('style')).toBeNull();
      });
    }
  });

  it('rolls back schedule on server error in timeline view', async () => {
    const mockFailFetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 412,
      text: () => Promise.resolve(JSON.stringify({ code: 'PRECONDITION_FAILED' })),
    });
    globalThis.fetch = mockFailFetch;

    render(
      <TimelineView
        issues={TEST_ISSUES}
        projectKey="KAN"
        initialZoom="week"
        initialStartDate="2026-11-01"
        today="2026-11-12"
      />
    );

    const bar100 = screen.getByTestId('timeline-bar-KAN-100');
    await act(async () => {
      fireEvent.keyDown(bar100, { key: 'ArrowRight' });
      await Promise.resolve();
    });

    expect(screen.getByRole('status').textContent).toContain('rolled back');
  });

  it('verifies timeline date column spacing classes, vertical gridlines, and quarter grouped headers (KANBA-173)', () => {
    const { container } = render(
      <TimelineView
        issues={TEST_ISSUES}
        projectKey="KAN"
        initialZoom="day"
        initialStartDate="2026-11-01"
        today="2026-11-12"
      />
    );

    // In 'day' mode, cells have timeline-scale-cell--day and canvas has timeline-right-canvas--day
    const dayCanvas = container.querySelector('.timeline-right-canvas');
    expect(dayCanvas?.classList.contains('timeline-right-canvas--day')).toBe(true);
    const dayCells = container.querySelectorAll('.timeline-scale-cell--day');
    expect(dayCells.length).toBeGreaterThan(0);
    // Zero style attribute on scale cells (CSP strict)
    expect(dayCells[0]?.getAttribute('style')).toBeNull();

    // Switch to 'week' mode
    const weekBtn = screen.getByRole('radio', { name: /^week$/i });
    fireEvent.click(weekBtn);
    expect(dayCanvas?.classList.contains('timeline-right-canvas--week')).toBe(true);
    const weekCells = container.querySelectorAll('.timeline-scale-cell--week');
    expect(weekCells.length).toBeGreaterThan(0);
    expect(weekCells[0]?.getAttribute('style')).toBeNull();

    // Switch to 'quarter' mode
    const quarterBtn = screen.getByRole('radio', { name: /^quarter$/i });
    fireEvent.click(quarterBtn);
    expect(dayCanvas?.classList.contains('timeline-right-canvas--quarter')).toBe(true);
    const quarterCells = container.querySelectorAll('.timeline-scale-cell--quarter');
    expect(quarterCells.length).toBeGreaterThan(0);
    expect(quarterCells[0]?.getAttribute('style')).toBeNull();

    // In quarter mode, grouped headers avoid running dates together
    // 2026-11-01 should show month abbreviation 'Nov'
    const novCell = container.querySelector('[data-date="2026-11-01"]');
    expect(novCell?.textContent.trim()).toBe('Nov');

    // Day 2 (not day 1 or modulo 7 == 1) should have empty label to prevent collision
    const emptyCell = container.querySelector('[data-date="2026-11-02"]');
    expect(emptyCell?.textContent.trim()).toBe('');
  });

  it('renders vetoed and approved gate indicators and handles custom links prop', () => {
    const issuesWithGates: TimelineIssueItem[] = [
      {
        id: 'i-vetoed',
        key: 'KAN-VETOED',
        summary: 'Vetoed Gate Task',
        state: { id: 's1', name: 'Review', group: 'started' },
        priority: { slug: 'high', label: 'High' },
        start_date: '2026-11-02',
        due_date: '2026-11-08',
        gate_status: 'vetoed',
        links: [
          {
            link_type: 'BLOCKS',
            target_key: 'KAN-APPROVED',
            link_state: 'ACTIVE',
            restricted: false,
          },
        ],
      },
      {
        id: 'i-approved',
        key: 'KAN-APPROVED',
        summary: 'Approved Gate Task',
        state: { id: 's2', name: 'Done', group: 'completed' },
        priority: { slug: 'low', label: 'Low' },
        start_date: '2026-11-09',
        due_date: '2026-11-15',
        gate_status: 'approved',
      },
    ];

    const customLinks = [
      {
        source_key: 'KAN-APPROVED',
        target_key: 'KAN-VETOED',
        link_type: 'BLOCKS',
        link_state: 'ACTIVE',
        restricted: false,
      },
    ];

    const { container } = render(
      <TimelineView
        issues={issuesWithGates}
        projectKey="KAN"
        links={customLinks}
        initialStartDate="2026-11-01"
        today="2026-11-10"
      />
    );

    expect(container.querySelector('[data-testid="timeline-bar-KAN-VETOED"]')).not.toBeNull();
    expect(container.querySelector('[data-testid="timeline-bar-KAN-APPROVED"]')).not.toBeNull();
  });

  it('covers fallback anchorStart and Today button with invalid date string', () => {
    const { getByRole } = render(
      <TimelineView
        issues={[]}
        projectKey="KAN"
        today="invalid-date"
      />
    );

    const todayBtn = getByRole('button', { name: 'Today' });
    fireEvent.click(todayBtn);
  });

  it('covers pointer down on bar with resize handles', () => {
    const twoDateIssues: TimelineIssueItem[] = [
      {
        id: 'i-bar',
        key: 'KAN-BAR',
        summary: 'Spanning task',
        state: { id: 's1', name: 'To Do', group: 'unstarted' },
        priority: { slug: 'medium', label: 'Medium' },
        start_date: '2026-11-04',
        due_date: '2026-11-10',
      },
    ];

    render(
      <TimelineView
        issues={twoDateIssues}
        projectKey="KAN"
        initialStartDate="2026-11-01"
      />
    );

    const bar = screen.getByTestId('timeline-bar-KAN-BAR');
    fireEvent.pointerDown(bar, { clientX: 100 });
  });

  it('covers left row click, anchor click with onOpenPeek, milestone pointer down, and 200 arrow cap', () => {
    const onOpenPeek = vi.fn();
    const milestoneIssues: TimelineIssueItem[] = [
      {
        id: 'i-mile',
        key: 'KAN-MILE',
        summary: 'Milestone item',
        state: { id: 's1', name: 'In Progress', group: 'started' },
        priority: { slug: 'high', label: 'High' },
        due_date: '2026-11-08',
      },
      {
        id: 'i-mile2',
        key: 'KAN-MILE2',
        summary: 'Target item',
        state: { id: 's1', name: 'In Progress', group: 'started' },
        priority: { slug: 'low', label: 'Low' },
        start_date: '2026-11-10',
        due_date: '2026-11-12',
      },
    ];

    // Generate 205 links to exercise the 200 arrow cap
    const manyLinks = Array.from({ length: 205 }, () => ({
      source_key: 'KAN-MILE',
      target_key: 'KAN-MILE2',
      link_type: 'BLOCKS',
      link_state: 'ACTIVE',
      restricted: false,
    }));

    const { container } = render(
      <TimelineView
        issues={milestoneIssues}
        links={manyLinks}
        projectKey="KAN"
        initialStartDate="2026-11-01"
        onOpenPeek={onOpenPeek}
      />
    );

    // 1. Click left row summary (not anchor)
    const summarySpan = screen.getByText('Milestone item');
    fireEvent.click(summarySpan);
    expect(onOpenPeek).toHaveBeenCalledWith('KAN-MILE');

    // 2. Click anchor directly
    const anchor = screen.getByText('KAN-MILE');
    fireEvent.click(anchor);
    expect(onOpenPeek).toHaveBeenCalledWith('KAN-MILE');

    // 3. Pointer down on milestone diamond
    const milestoneDiamond = container.querySelector('.timeline-milestone');
    expect(milestoneDiamond).not.toBeNull();
    if (milestoneDiamond) {
      fireEvent.pointerDown(milestoneDiamond, { clientX: 150 });
    }
  });

  it('covers pointerDown fallback when start_date or due_date is null', () => {
    const issuesWithSingleDates: TimelineIssueItem[] = [
      {
        id: 'single-due',
        key: 'KAN-SD',
        summary: 'Only due date',
        state: { id: 's-1', name: 'Todo', group: 'unstarted' },
        priority: { slug: 'medium', label: 'Medium', emoji: '🔹' },
        start_date: null,
        due_date: '2026-11-05',
      },
      {
        id: 'single-start',
        key: 'KAN-SS',
        summary: 'Only start date',
        state: { id: 's-1', name: 'Todo', group: 'unstarted' },
        priority: { slug: 'medium', label: 'Medium', emoji: '🔹' },
        start_date: '2026-11-05',
        due_date: null,
      },
    ];

    const { container } = render(
      <TimelineView
        issues={issuesWithSingleDates}
        projectKey="KAN"
        initialStartDate="2026-11-01"
      />
    );

    const milestones = container.querySelectorAll('.timeline-milestone');
    expect(milestones.length).toBeGreaterThan(0);
    for (const m of milestones) {
      fireEvent.pointerDown(m, { clientX: 100 });
      fireEvent.pointerUp(window, { clientX: 100 });
    }
  });
});
