import fs from 'node:fs';
import path from 'node:path';
import { act, fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { BoardCard } from '../BoardCard.tsx';
import type { BoardIssue, StateGroup } from '../boardApi.ts';

const baseIssue: BoardIssue = {
  id: 'iss-test-1',
  key: 'KAN-383',
  summary: 'Card Color Coding Verification',
  state_id: 'state-started',
  board_rank: '0000000000000001',
};

describe('BoardCard Color Codes & Priority Accents (KAN-383)', () => {
  it('renders board-card--state-<group> modifier class and data-state-group for all 5 state groups', () => {
    const stateGroups: StateGroup[] = ['backlog', 'unstarted', 'started', 'completed', 'cancelled'];

    for (const group of stateGroups) {
      const { unmount } = render(
        <BoardCard
          issue={{
            ...baseIssue,
            state: { id: `state-${group}`, name: group, group },
          }}
          stateGroup={group}
        />,
      );

      const card = screen.getByTestId('board-card-KAN-383');
      expect(card.classList.contains(`board-card--state-${group}`)).toBe(true);
      expect(card.getAttribute('data-state-group')).toBe(group);

      unmount();
    }
  });

  it('renders data-priority attribute matching issue priority slug or none', () => {
    // Priority urgent
    const { rerender } = render(
      <BoardCard
        issue={{
          ...baseIssue,
          priority: { id: 'p1', label: 'Urgent', slug: 'urgent' },
        }}
        stateGroup="started"
      />,
    );
    const card = screen.getByTestId('board-card-KAN-383');
    expect(card.getAttribute('data-priority')).toBe('urgent');

    // Priority high
    rerender(
      <BoardCard
        issue={{
          ...baseIssue,
          priority: { id: 'p2', label: 'High', slug: 'high' },
        }}
        stateGroup="started"
      />,
    );
    expect(card.getAttribute('data-priority')).toBe('high');

    // Priority medium
    rerender(
      <BoardCard
        issue={{
          ...baseIssue,
          priority: { id: 'p3', label: 'Medium', slug: 'medium' },
        }}
        stateGroup="started"
      />,
    );
    expect(card.getAttribute('data-priority')).toBe('medium');

    // Priority low
    rerender(
      <BoardCard
        issue={{
          ...baseIssue,
          priority: { id: 'p4', label: 'Low', slug: 'low' },
        }}
        stateGroup="started"
      />,
    );
    expect(card.getAttribute('data-priority')).toBe('low');

    // No priority
    rerender(
      <BoardCard
        issue={{
          ...baseIssue,
          priority: null,
        }}
        stateGroup="started"
      />,
    );
    expect(card.getAttribute('data-priority')).toBe('none');
  });

  it('synchronizes --card-state-accent via useLayoutEffect when custom valid state.color_hex is provided', () => {
    const { rerender } = render(
      <BoardCard
        issue={{
          ...baseIssue,
          state: { id: 'state-custom-1', name: 'Custom State', group: 'started', color_hex: '#7c3aed' },
        }}
        stateGroup="started"
      />,
    );

    const card = screen.getByTestId('board-card-KAN-383');
    expect(card.style.getPropertyValue('--card-state-accent')).toBe('#7c3aed');

    // Rerender with another valid hex
    rerender(
      <BoardCard
        issue={{
          ...baseIssue,
          state: { id: 'state-custom-2', name: 'Emerald Done', group: 'completed', color_hex: '#10B981' },
        }}
        stateGroup="completed"
      />,
    );
    expect(card.style.getPropertyValue('--card-state-accent')).toBe('#10B981');
  });

  it('rejects malformed or unsafe hex strings and removes --card-state-accent property', () => {
    const invalidHexes = [
      'red',
      '#fff',
      '#12345',
      '#1234567',
      'javascript:alert(1)',
      '#zzzzzz',
      '   ',
    ];

    const { rerender } = render(
      <BoardCard
        issue={{
          ...baseIssue,
          state: { id: 's1', name: 'Valid First', group: 'started', color_hex: '#2563eb' },
        }}
        stateGroup="started"
      />,
    );
    const card = screen.getByTestId('board-card-KAN-383');
    expect(card.style.getPropertyValue('--card-state-accent')).toBe('#2563eb');

    for (const invalidHex of invalidHexes) {
      rerender(
        <BoardCard
          issue={{
            ...baseIssue,
            state: { id: 's1', name: 'Invalid State', group: 'started', color_hex: invalidHex },
          }}
          stateGroup="started"
        />,
      );
      expect(card.style.getPropertyValue('--card-state-accent')).toBe('');
    }

    // null / undefined color_hex
    rerender(
      <BoardCard
        issue={{
          ...baseIssue,
          state: { id: 's1', name: 'No Color State', group: 'started', color_hex: null },
        }}
        stateGroup="started"
      />,
    );
    expect(card.style.getPropertyValue('--card-state-accent')).toBe('');
  });

  it('renders status dot indicator and glyph inside .board-card-state-btn', () => {
    render(
      <BoardCard
        issue={{
          ...baseIssue,
          state: { id: 'state-in-prog', name: 'In Progress', group: 'started', color_hex: '#f59e0b' },
        }}
        stateGroup="started"
      />,
    );

    const stateBtn = screen.getByTestId('board-card-state-btn-KAN-383');
    expect(stateBtn).toBeDefined();

    const dot = stateBtn.querySelector('.board-card-state-btn-dot');
    expect(dot).not.toBeNull();

    const glyph = stateBtn.querySelector('.board-card-state-btn-glyph');
    expect(glyph).not.toBeNull();
    expect(glyph?.textContent).toBe('⇄');
    expect(stateBtn.textContent).toContain('In Progress');
  });

  it('renders priority color pill with slug-based modifier class in .board-card-meta', () => {
    const priorities = [
      { slug: 'urgent', label: 'Urgent' },
      { slug: 'high', label: 'High' },
      { slug: 'medium', label: 'Medium' },
      { slug: 'low', label: 'Low' },
    ];

    for (const p of priorities) {
      const { unmount } = render(
        <BoardCard
          issue={{
            ...baseIssue,
            priority: { id: `p-${p.slug}`, label: p.label, slug: p.slug },
          }}
          stateGroup="started"
        />,
      );

      const pill = screen.getByTestId('priority-pill-KAN-383');
      expect(pill.classList.contains('board-card-priority-pill')).toBe(true);
      expect(pill.classList.contains(`board-card-priority-pill--${p.slug}`)).toBe(true);
      expect(pill.textContent).toContain(p.label);

      unmount();
    }
  });

  it('board.css defines left accent border and semantic color mappings for all 5 state groups and priority levels', () => {
    const cssPath = path.resolve(__dirname, '../board.css');
    const css = fs.readFileSync(cssPath, 'utf-8');

    // Left accent bar
    expect(css).toContain('border-left: 3.5px solid var(--card-state-accent);');
    expect(css).toContain('--card-state-accent: var(--state-unstarted-fg, #3b82f6);');
    expect(css).toContain('--card-priority-accent: var(--fg-muted, #94a3b8);');
    expect(css).toContain('border-left-color: var(--card-state-accent);');

    // 5 State group color token fallbacks
    expect(css).toContain('--card-state-accent: var(--state-backlog-fg, #64748b);');
    expect(css).toContain('--card-state-accent: var(--state-unstarted-fg, #3b82f6);');
    expect(css).toContain('--card-state-accent: var(--state-started-fg, #f59e0b);');
    expect(css).toContain('--card-state-accent: var(--state-completed-fg, #10b981);');
    expect(css).toContain('--card-state-accent: var(--state-cancelled-fg, #ef4444);');

    // State classes and data attributes
    expect(css).toContain('.board-card.board-card--state-backlog');
    expect(css).toContain('.board-card.board-card--state-unstarted');
    expect(css).toContain('.board-card.board-card--state-started');
    expect(css).toContain('.board-card.board-card--state-completed');
    expect(css).toContain('.board-card.board-card--state-cancelled');

    // Priority color pill styles
    expect(css).toContain('.board-card-priority-pill');
    expect(css).toContain('.board-card-priority-pill--urgent');
    expect(css).toContain('.board-card-priority-pill--high');
    expect(css).toContain('.board-card-priority-pill--medium');
    expect(css).toContain('.board-card-priority-pill--low');

    // State button indicator styles
    expect(css).toContain('.board-card-state-btn-dot');
    expect(css).toContain('.board-card-state-btn-glyph');
  });

  it('exercises quick move touch action button, popover cancellation, and state/rank transition', () => {
    const onStateTransition = vi.fn();
    const onKeyboardMove = vi.fn();

    const { unmount } = render(
      <BoardCard
        issue={{
          ...baseIssue,
          state: { id: 'state-started', name: 'In Progress', group: 'started' },
        }}
        stateGroup="started"
        onStateTransition={onStateTransition}
        onKeyboardMove={onKeyboardMove}
      />,
    );

    const touchBtn = screen.getByTestId('board-card-touch-action-KAN-383');
    fireEvent.click(touchBtn);

    // Cancel closes popover
    const cancelBtn = screen.getByTestId('touch-reorder-cancel-btn');
    fireEvent.click(cancelBtn);
    expect(screen.queryByTestId('touch-reorder-cancel-btn')).toBeNull();

    // Reopen and select state directly
    fireEvent.click(touchBtn);
    const doneOption = screen.getByTestId('touch-state-option-state-done');
    fireEvent.click(doneOption);
    expect(onStateTransition).toHaveBeenCalledWith('KAN-383', 'state-done');

    // Reopen, select rank top and apply move
    fireEvent.click(touchBtn);
    const topRankBtn = screen.getByTestId('touch-rank-top');
    fireEvent.click(topRankBtn);
    const applyBtn = screen.getByTestId('touch-reorder-apply-btn');
    fireEvent.click(applyBtn);
    expect(onKeyboardMove).toHaveBeenCalledWith(expect.anything(), 'up');

    unmount();

    // Custom projectStates and bottom rank position (rank down)
    const customStates = [
      { id: 's-1', name: 'Open', group: 'unstarted' as const, sort_order: 1 },
      { id: 's-2', name: 'Closed', group: 'completed' as const, sort_order: 2 },
    ];
    const { unmount: unmount2 } = render(
      <BoardCard
        issue={{ ...baseIssue, state: undefined, priority: null }}
        stateGroup="unstarted"
        projectStates={customStates}
        onStateTransition={onStateTransition}
        onKeyboardMove={onKeyboardMove}
      />,
    );
    const touchBtn2 = screen.getByTestId('board-card-touch-action-KAN-383');
    fireEvent.click(touchBtn2);
    const bottomRankBtn = screen.getByTestId('touch-rank-bottom');
    fireEvent.click(bottomRankBtn);
    const applyBtn2 = screen.getByTestId('touch-reorder-apply-btn');
    fireEvent.click(applyBtn2);
    expect(onKeyboardMove).toHaveBeenCalledWith(expect.anything(), 'down');
    unmount2();

    // Without onKeyboardMove
    const { unmount: unmount3 } = render(
      <BoardCard
        issue={{ ...baseIssue, state: undefined, priority: null }}
        stateGroup="unstarted"
        onStateTransition={onStateTransition}
      />,
    );
    fireEvent.click(screen.getByTestId('board-card-touch-action-KAN-383'));
    fireEvent.click(screen.getByTestId('touch-reorder-apply-btn'));
    unmount3();
  });

  it('covers state popover without onStateTransition and aging WIP without currentAgeHours', () => {
    const { unmount, rerender } = render(
      <BoardCard
        issue={{
          ...baseIssue,
          state: undefined,
          priority: null,
          is_aging_wip: true,
          age_in_current_state_hours: undefined,
        }}
        stateGroup="started"
      />,
    );

    expect(screen.getByTestId('aging-wip-KAN-383')).toBeDefined();

    const stateBtn = screen.getByTestId('board-card-state-btn-KAN-383');
    fireEvent.click(stateBtn);

    // Aging WIP with age hours
    rerender(
      <BoardCard
        issue={{
          ...baseIssue,
          is_aging_wip: true,
          age_in_current_state_hours: 48,
        }}
        stateGroup="started"
      />,
    );
    expect(screen.getByTestId('aging-wip-KAN-383').textContent).toContain('48h');

    unmount();
  });

  it('exercises touch lift state with timer advance and state popover dialog', () => {
    vi.useFakeTimers();
    navigator.vibrate = vi.fn();
    const onStateTransition = vi.fn();

    const { unmount } = render(
      <BoardCard
        issue={{
          ...baseIssue,
          state: { id: 'state-started', name: 'In Progress', group: 'started' },
        }}
        stateGroup="started"
        onStateTransition={onStateTransition}
      />,
    );

    const card = screen.getByTestId('board-card-KAN-383');
    fireEvent.touchStart(card, {
      touches: [{ clientX: 200, clientY: 200 }],
    });
    act(() => {
      vi.advanceTimersByTime(250);
    });
    expect(card.classList.contains('board-card--touch-lifted')).toBe(true);
    expect(card.getAttribute('data-touch-lifted')).toBe('true');
    fireEvent.touchEnd(card);
    expect(card.classList.contains('board-card--touch-lifted')).toBe(false);

    // Open state popover
    const stateBtn = screen.getByTestId('board-card-state-btn-KAN-383');
    fireEvent.click(stateBtn);
    const popover = screen.getByRole('dialog');
    expect(popover).toBeDefined();

    vi.useRealTimers();
    unmount();
  });
});
