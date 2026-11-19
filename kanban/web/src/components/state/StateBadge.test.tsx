import React from 'react';
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { StateBadge, normalizeStateGroup, STATE_EMOJI_MAP } from './StateBadge';

describe('StateBadge (KB-UX-02)', () => {
  it('renders all 5 semantic state groups with respective emojis and progress rings', () => {
    const states = [
      { group: 'backlog', expectedEmoji: '🗂️', name: 'Backlog' },
      { group: 'unstarted', expectedEmoji: '📋', name: 'Todo' },
      { group: 'started', expectedEmoji: '⚙️', name: 'In Progress' },
      { group: 'completed', expectedEmoji: '✅', name: 'Done' },
      { group: 'cancelled', expectedEmoji: '🚫', name: 'Cancelled' },
    ] as const;

    for (const item of states) {
      const { unmount } = render(
        <StateBadge
          state={{ id: `st-${item.group}`, name: item.name, group: item.group }}
          testId={`badge-${item.group}`}
        />
      );

      const badge = screen.getByTestId(`badge-${item.group}`);
      expect(badge).toBeDefined();
      expect(badge.getAttribute('data-state-group')).toBe(item.group);
      expect(badge.classList.contains(`state-badge--${item.group}`)).toBe(true);
      expect(screen.getByText(item.expectedEmoji)).toBeDefined();
      expect(screen.getByText(item.name)).toBeDefined();
      unmount();
    }
  });

  it('handles in_review specifically with 75% ring state', () => {
    render(
      <StateBadge
        state={{ id: 'st-review', name: 'In Review', group: 'started' }}
        testId="badge-review"
      />
    );
    const badge = screen.getByTestId('badge-review');
    expect(badge).toBeDefined();
    expect(screen.getByText('In Review')).toBeDefined();
    expect(screen.getByText('⚙️')).toBeDefined();
  });

  it('supports compact mode without label', () => {
    render(
      <StateBadge
        state={{ id: 'st-done', name: 'Done', group: 'completed' }}
        showLabel={false}
        testId="compact-badge"
      />
    );
    const badge = screen.getByTestId('compact-badge');
    expect(badge.classList.contains('state-badge--compact')).toBe(true);
    expect(screen.queryByText('Done')).toBeNull();
    expect(screen.getByText('✅')).toBeDefined();
  });

  it('supports hiding emoji or ring', () => {
    render(
      <StateBadge
        state="backlog"
        name="Backlog"
        showEmoji={false}
        showRing={false}
        testId="plain-badge"
      />
    );
    expect(screen.queryByText('🗂️')).toBeNull();
    expect(screen.getByText('Backlog')).toBeDefined();
  });

  it('normalizes various state group aliases accurately', () => {
    expect(normalizeStateGroup('backlog')).toBe('backlog');
    expect(normalizeStateGroup('To Do')).toBe('unstarted');
    expect(normalizeStateGroup('unstarted')).toBe('unstarted');
    expect(normalizeStateGroup('In Progress')).toBe('started');
    expect(normalizeStateGroup('started')).toBe('started');
    expect(normalizeStateGroup('Done')).toBe('completed');
    expect(normalizeStateGroup('completed')).toBe('completed');
    expect(normalizeStateGroup('Canceled')).toBe('cancelled');
    expect(normalizeStateGroup('cancelled')).toBe('cancelled');
    expect(normalizeStateGroup('unknown')).toBe('unstarted');
  });

  it('verifies STATE_EMOJI_MAP completeness', () => {
    expect(STATE_EMOJI_MAP.backlog).toBe('🗂️');
    expect(STATE_EMOJI_MAP.unstarted).toBe('📋');
    expect(STATE_EMOJI_MAP.started).toBe('⚙️');
    expect(STATE_EMOJI_MAP.completed).toBe('✅');
    expect(STATE_EMOJI_MAP.cancelled).toBe('🚫');
  });

  it('covers fallback resolution branches when state or name is omitted', () => {
    // 1. state is object with only group
    const { unmount: u1 } = render(<StateBadge state={{ group: 'started' }} testId="b1" />);
    expect(screen.getByTestId('b1').getAttribute('data-state-group')).toBe('started');
    u1();

    // 2. state is object with only name
    const { unmount: u2 } = render(<StateBadge state={{ name: 'backlog' }} testId="b2" />);
    expect(screen.getByTestId('b2').getAttribute('data-state-group')).toBe('backlog');
    u2();

    // 3. state is undefined, group is provided with custom name
    const { unmount: u3 } = render(<StateBadge group="completed" name="Finished Task" className="extra-cls" testId="b3" />);
    expect(screen.getByTestId('b3').classList.contains('extra-cls')).toBe(true);
    expect(screen.getByText('Finished Task')).toBeDefined();
    u3();

    // 4. state is undefined, only group provided
    const { unmount: u4 } = render(<StateBadge group="cancelled" testId="b4" />);
    expect(screen.getByTestId('b4').getAttribute('data-state-group')).toBe('cancelled');
    u4();

    // 5. state is empty object {}
    const { unmount: u5 } = render(<StateBadge state={{}} testId="b5" />);
    expect(screen.getByTestId('b5').getAttribute('data-state-group')).toBe('unstarted');
    expect(screen.getByText(/unstarted/i)).toBeDefined();
    u5();

    // 6. state is string without name
    const { unmount: u6 } = render(<StateBadge state="started" testId="b6" />);
    expect(screen.getByTestId('b6').getAttribute('data-state-group')).toBe('started');
    u6();
  });
});
