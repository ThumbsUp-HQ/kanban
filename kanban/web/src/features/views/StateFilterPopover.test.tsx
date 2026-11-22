import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import React, { useState } from 'react';
import {
  StateFilterPopover,
  resolveEffectiveProjectStates,
  sanitizeStateSearchQuery,
} from './StateFilterPopover';
import {
  createActionableStateFilterPreference,
  type ProjectStateFilterPreference,
} from './issueFilterCookie';
import type { IssueItem, StateSummary } from './viewsApi';

describe('StateFilterPopover (KAN-308 Problem 2)', () => {
  const projectStates: StateSummary[] = [
    { id: 'st-backlog', name: 'Backlog', group: 'backlog', sort_order: 10 },
    { id: 'st-todo', name: 'Todo', group: 'unstarted', sort_order: 20 },
    { id: 'st-crazy', name: 'Crazy_Ideas', group: 'unstarted', sort_order: 25 },
    { id: 'st-prog', name: 'In Progress', group: 'started', sort_order: 30 },
    { id: 'st-done', name: 'Done', group: 'completed', sort_order: 40 },
    { id: 'st-cancel', name: 'Cancelled', group: 'cancelled', sort_order: 50 },
  ];

  const sampleIssues: IssueItem[] = [
    {
      id: 'i-1',
      key: 'KAN-1',
      summary: 'Active Todo',
      state: { id: 'st-todo', name: 'Todo', group: 'unstarted' },
      priority: { slug: 'high', label: 'High' },
    },
    {
      id: 'i-2',
      key: 'KAN-2',
      summary: 'Crazy Idea',
      state: { id: 'st-crazy', name: 'Crazy_Ideas', group: 'unstarted' },
      priority: { slug: 'low', label: 'Low' },
    },
    {
      id: 'i-3',
      key: 'KAN-3',
      summary: 'Finished Task',
      state: { id: 'st-done', name: 'Done', group: 'completed' },
      priority: { slug: 'medium', label: 'Medium' },
    },
  ];

  function ControlledHarness({
    initialPref = createActionableStateFilterPreference(),
    onOpenChange,
  }: {
    initialPref?: ProjectStateFilterPreference;
    onOpenChange?: (open: boolean) => void;
  }) {
    const [pref, setPref] = useState<ProjectStateFilterPreference>(initialPref);
    return (
      <StateFilterPopover
        projectStates={projectStates}
        issues={sampleIssues}
        value={pref}
        onChange={setPref}
        onOpenChange={onOpenChange}
      />
    );
  }

  it('renders trigger pill with Actionable preset by default and opens grouped checkbox dialog with zero inline styles', () => {
    const onOpenChange = vi.fn();
    const { container } = render(<ControlledHarness onOpenChange={onOpenChange} />);

    const trigger = screen.getByTestId('navigator-filter-state');
    expect(trigger.getAttribute('data-state-preset')).toBe('actionable');
    expect(trigger.getAttribute('aria-expanded')).toBe('false');
    expect(trigger.textContent).toContain('States: Actionable (4)');

    // Open popover
    fireEvent.click(trigger);
    expect(onOpenChange).toHaveBeenCalledWith(true);
    expect(trigger.getAttribute('aria-expanded')).toBe('true');

    const dialog = screen.getByTestId('navigator-state-popover');
    expect(dialog.getAttribute('role')).toBe('dialog');
    expect(screen.getByTestId('state-filter-group-actionable')).toBeDefined();
    expect(screen.getByTestId('state-filter-group-closed')).toBeDefined();

    // Actionable checkboxes are checked by default (including Crazy_Ideas); Closed are unchecked
    expect(screen.getByTestId<HTMLInputElement>('state-checkbox-st-backlog').checked).toBe(true);
    expect(screen.getByTestId<HTMLInputElement>('state-checkbox-st-todo').checked).toBe(true);
    expect(screen.getByTestId<HTMLInputElement>('state-checkbox-st-crazy').checked).toBe(true);
    expect(screen.getByTestId<HTMLInputElement>('state-checkbox-st-prog').checked).toBe(true);
    expect(screen.getByTestId<HTMLInputElement>('state-checkbox-st-done').checked).toBe(false);
    expect(screen.getByTestId<HTMLInputElement>('state-checkbox-st-cancel').checked).toBe(false);

    // Issue counts are accurate
    expect(screen.getByTestId('state-count-st-todo').textContent).toBe('1');
    expect(screen.getByTestId('state-count-st-crazy').textContent).toBe('1');
    expect(screen.getByTestId('state-count-st-done').textContent).toBe('1');
    expect(screen.getByTestId('state-count-st-backlog').textContent).toBe('0');

    // Strict CSP invariant: zero inline style attributes inside popover
    expect(container.querySelectorAll('[style]').length).toBe(0);
  });

  it('filters checkboxes via literal substring search, handles XSS/regex payloads safely, and toggles checkboxes & presets', () => {
    render(<ControlledHarness />);

    fireEvent.click(screen.getByTestId('navigator-filter-state'));
    const searchInput = screen.getByTestId<HTMLInputElement>('state-filter-search-input');

    // Type "done" -> only Done checkbox visible
    fireEvent.change(searchInput, { target: { value: 'done' } });
    expect(screen.getByTestId('state-checkbox-st-done')).toBeDefined();
    expect(screen.queryByTestId('state-checkbox-st-todo')).toBeNull();

    // Check Done while filtered
    fireEvent.click(screen.getByTestId('state-checkbox-st-done'));
    expect(screen.getByTestId<HTMLInputElement>('state-checkbox-st-done').checked).toBe(true);
    expect(screen.getByTestId('navigator-filter-state').textContent).toContain('States: 5 selected');

    // Hostile XSS and catastrophic regex payloads throw 0 errors, inject 0 DOM elements, and render empty message
    fireEvent.change(searchInput, { target: { value: '<img src=x onerror=alert(1)>' } });
    expect(screen.getByTestId('state-filter-empty').textContent).toBe('No matching workflow states');
    expect(document.querySelectorAll('img').length).toBe(0);

    fireEvent.change(searchInput, { target: { value: '((a+)+)$[' } });
    expect(screen.getByTestId('state-filter-empty')).toBeDefined();

    // Control characters and >128 char input are stripped and capped at 128
    const longDirty = `done\x00\x1f${String.fromCharCode(0xd800)}${'x'.repeat(200)}`;
    const sanitized = sanitizeStateSearchQuery(longDirty);
    expect(sanitized.length).toBe(128);
    expect(sanitized.startsWith('donexxx')).toBe(true);

    // Clear search and test All / None / Actionable presets
    fireEvent.change(searchInput, { target: { value: '' } });

    fireEvent.click(screen.getByTestId('state-preset-all'));
    expect(screen.getByTestId('navigator-filter-state').getAttribute('data-state-preset')).toBe('all');
    expect(screen.getByTestId('navigator-filter-state').textContent).toContain('States: All');

    fireEvent.click(screen.getByTestId('state-preset-none'));
    expect(screen.getByTestId('navigator-filter-state').getAttribute('data-state-preset')).toBe('none');
    expect(screen.getByTestId('navigator-filter-state').textContent).toContain('States: None (0)');

    fireEvent.click(screen.getByTestId('state-preset-actionable'));
    expect(screen.getByTestId('navigator-filter-state').getAttribute('data-state-preset')).toBe('actionable');
  });

  it('supports keyboard navigation (ArrowDown, ArrowUp, Escape) and outside pointerdown close', async () => {
    const onOpenChange = vi.fn();
    render(
      <div>
        <button type="button" data-testid="outside-btn">
          Outside
        </button>
        <ControlledHarness onOpenChange={onOpenChange} />
      </div>,
    );

    const trigger = screen.getByTestId('navigator-filter-state');
    fireEvent.click(trigger);
    await act(async () => {
      await new Promise((r) => setTimeout(r, 10));
    });

    const dialog = screen.getByTestId('navigator-state-popover');
    const searchInput = screen.getByTestId('state-filter-search-input');
    searchInput.focus();

    // ArrowDown moves focus from search input to first checkbox
    fireEvent.keyDown(dialog, { key: 'ArrowDown' });
    expect(document.activeElement).toBe(screen.getByTestId('state-checkbox-st-backlog'));

    // ArrowUp moves focus back to search input
    fireEvent.keyDown(dialog, { key: 'ArrowUp' });
    expect(document.activeElement).toBe(searchInput);

    // ArrowUp from search input wraps to last checkbox
    fireEvent.keyDown(dialog, { key: 'ArrowUp' });
    expect(document.activeElement).toBe(screen.getByTestId('state-checkbox-st-cancel'));

    // ArrowDown from last checkbox wraps to search input
    fireEvent.keyDown(dialog, { key: 'ArrowDown' });
    expect(document.activeElement).toBe(searchInput);

    // Escape closes popover
    fireEvent.keyDown(dialog, { key: 'Escape' });
    expect(screen.queryByTestId('navigator-state-popover')).toBeNull();
    expect(onOpenChange).toHaveBeenLastCalledWith(false);

    // Reopen and close via outside pointerdown
    fireEvent.click(trigger);
    expect(screen.getByTestId('navigator-state-popover')).toBeDefined();
    fireEvent.pointerDown(screen.getByTestId('outside-btn'));
    expect(screen.queryByTestId('navigator-state-popover')).toBeNull();
  });

  it('falls back to DEFAULT_WORKFLOW_STATES when projectStates is omitted and sorts ties by name', () => {
    const tiedStates: StateSummary[] = [
      { id: 's-b', name: 'Beta', group: 'unstarted' },
      { id: 's-a', name: 'Alpha', group: 'unstarted' },
    ];
    const resolved = resolveEffectiveProjectStates(tiedStates);
    expect(resolved[0]?.name).toBe('Alpha');
    expect(resolved[1]?.name).toBe('Beta');

    const defaults = resolveEffectiveProjectStates([]);
    expect(defaults.length).toBe(6);

    const onChange = vi.fn();
    render(
      <StateFilterPopover
        value={createActionableStateFilterPreference()}
        onChange={onChange}
        issues={[
          {
            id: 'i-norm',
            key: 'KAN-NORM',
            summary: 'Normalized state match',
            state: { id: 'custom-todo-id', name: 'To Do', group: 'unstarted' },
            priority: { slug: 'low', label: 'Low' },
          },
        ]}
      />,
    );
    fireEvent.click(screen.getByTestId('navigator-filter-state'));
    expect(screen.getByTestId('state-count-state-todo').textContent).toBe('1');
  });
});
