import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, renderHook, act } from '@testing-library/react';
import React, { useState } from 'react';
import { useIssueKeyboardMap } from './useIssueKeyboardMap';
import { FIXTURE_12_ISSUES } from './fixtures';
import type { IssueItem } from './viewsApi';
import { QuickFieldPopover } from './QuickFieldPopover';

describe('useIssueKeyboardMap (KB-P3-40, S6.4 item 4, S1.3 item 3)', () => {
  beforeEach(() => {
    window.history.pushState({}, '', '/projects/KAN/issues?layout=board');
  });

  it('navigates with J/K/H/L, selects with X, toggles I, and opens shortcuts (Test Case 2)', () => {
    const handleOpenCreate = vi.fn();
    const handleOpenFilter = vi.fn();
    const handleOpenField = vi.fn();
    const handleToggleMe = vi.fn();

    function TestComponent() {
      const [selectedIds, setSelectedIds] = useState<string[]>([]);
      const { focusedKey } = useIssueKeyboardMap({
        issues: FIXTURE_12_ISSUES,
        layout: 'board',
        selectedIds,
        setSelectedIds,
        modulesEnabled: true,
        onOpenCreateModal: handleOpenCreate,
        onOpenFilter: handleOpenFilter,
        onOpenFieldPopover: handleOpenField,
        onToggleAssigneeMe: handleToggleMe,
      });

      return (
        <div>
          <span data-testid="focused">{focusedKey ?? 'none'}</span>
          <span data-testid="selected-count">{selectedIds.length}</span>
          <div data-issue-key="KAN-140" />
          <input data-testid="test-input" />
        </div>
      );
    }

    render(<TestComponent />);

    expect(screen.getByTestId('focused').textContent).toBe('none');

    // 1. 'J' focuses first issue KAN-140
    fireEvent.keyDown(window, { key: 'j' });
    expect(screen.getByTestId('focused').textContent).toBe('KAN-140');

    // 2. 'L' moves to next column / issue KAN-141
    fireEvent.keyDown(window, { key: 'l' });
    expect(screen.getByTestId('focused').textContent).toBe('KAN-141');

    // 3. 'H' moves back to KAN-140
    fireEvent.keyDown(window, { key: 'h' });
    expect(screen.getByTestId('focused').textContent).toBe('KAN-140');

    // 4. 'X' selects KAN-140
    fireEvent.keyDown(window, { key: 'x' });
    expect(screen.getByTestId('selected-count').textContent).toBe('1');

    // 5. 'I' toggles Adam assignment
    fireEvent.keyDown(window, { key: 'i' });
    expect(handleToggleMe).toHaveBeenCalledWith(
      expect.objectContaining({ key: 'KAN-140' })
    );

    // 6. 'C' opens quick create modal
    fireEvent.keyDown(window, { key: 'c' });
    expect(handleOpenCreate).toHaveBeenCalled();

    // 7. '/' opens filter
    fireEvent.keyDown(window, { key: '/' });
    expect(handleOpenFilter).toHaveBeenCalled();

    // 8. 'S', 'P', 'A', 'D' each open matching popovers
    fireEvent.keyDown(window, { key: 's' });
    expect(handleOpenField).toHaveBeenCalledWith('state', expect.anything(), expect.any(Object));

    fireEvent.keyDown(window, { key: 'p' });
    expect(handleOpenField).toHaveBeenCalledWith('priority', expect.anything(), expect.any(Object));

    fireEvent.keyDown(window, { key: 'a' });
    expect(handleOpenField).toHaveBeenCalledWith('assignee', expect.anything(), expect.any(Object));

    fireEvent.keyDown(window, { key: 'd' });
    expect(handleOpenField).toHaveBeenCalledWith('due_date', expect.anything(), expect.any(Object));

    // 9. Input shield: typing inside <input> triggers zero shortcuts
    handleOpenCreate.mockClear();
    handleOpenFilter.mockClear();
    handleToggleMe.mockClear();
    const inputEl = screen.getByTestId('test-input');
    inputEl.focus();

    for (const char of ['c', 's', 'p', 'a', 'd', 'm', 'j', 'x', '/']) {
      fireEvent.keyDown(inputEl, { key: char });
    }

    expect(handleOpenCreate).not.toHaveBeenCalled();
    expect(handleOpenFilter).not.toHaveBeenCalled();
    expect(handleToggleMe).not.toHaveBeenCalled();
  });

  it('pressing M when modulesEnabled is false is strict no-op (Test Case 3, S7.2 8f)', () => {
    const handleOpenField = vi.fn();

    function TestComponent() {
      const [selectedIds, setSelectedIds] = useState<string[]>([]);
      useIssueKeyboardMap({
        issues: FIXTURE_12_ISSUES,
        layout: 'board',
        selectedIds,
        setSelectedIds,
        modulesEnabled: false,
        onOpenFieldPopover: handleOpenField,
      });

      return <div>No modules mode</div>;
    }

    render(
      <>
        <TestComponent />
        <QuickFieldPopover
          isOpen={false}
          field="module"
          anchorRect={null}
          issue={FIXTURE_12_ISSUES[0]}
          onClose={vi.fn()}
          onSelect={vi.fn()}
          modulesEnabled={false}
        />
      </>
    );

    // Press 'M'
    fireEvent.keyDown(window, { key: 'm' });
    expect(handleOpenField).not.toHaveBeenCalled();
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('clears selection on Escape and handles Enter/Space for peek navigation', () => {
    function TestComponent() {
      const [selectedIds, setSelectedIds] = useState<string[]>(['KAN-140']);
      const { focusedKey } = useIssueKeyboardMap({
        issues: FIXTURE_12_ISSUES,
        layout: 'list',
        selectedIds,
        setSelectedIds,
      });

      return (
        <div>
          <span data-testid="focused">{focusedKey ?? 'none'}</span>
          <span data-testid="selected-count">{selectedIds.length}</span>
        </div>
      );
    }

    render(<TestComponent />);

    expect(screen.getByTestId('selected-count').textContent).toBe('1');

    // Press Escape -> clears selection
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(screen.getByTestId('selected-count').textContent).toBe('0');

    // Focus an issue and press Enter / Space
    fireEvent.keyDown(window, { key: 'j' });
    expect(screen.getByTestId('focused').textContent).toBe('KAN-140');
    fireEvent.keyDown(window, { key: 'Enter' });
    fireEvent.keyDown(window, { key: ' ' });
  });

  it('handles Shift+X range selection and capital L labels popover in list layout', () => {
    window.history.pushState({}, '', '/projects/KAN/issues?layout=list');
    const handleOpenField = vi.fn();

    function TestComponent() {
      const [selectedIds, setSelectedIds] = useState<string[]>([]);
      const { focusedKey } = useIssueKeyboardMap({
        issues: FIXTURE_12_ISSUES,
        layout: 'list',
        selectedIds,
        setSelectedIds,
        onOpenFieldPopover: handleOpenField,
      });

      return (
        <div>
          <span data-testid="focused">{focusedKey ?? 'none'}</span>
          <span data-testid="selected-count">{selectedIds.length}</span>
        </div>
      );
    }

    render(<TestComponent />);

    // Focus first
    fireEvent.keyDown(window, { key: 'j' });
    // Move to next
    fireEvent.keyDown(window, { key: 'j' });
    expect(screen.getByTestId('focused').textContent).toBe('KAN-141');

    // Shift+X selects range from KAN-140 to KAN-141
    fireEvent.keyDown(window, { key: 'X', shiftKey: true });
    expect(screen.getByTestId('selected-count').textContent).toBe('2');

    // Press 'l' in list layout -> opens labels popover
    fireEvent.keyDown(window, { key: 'l' });
    expect(handleOpenField).toHaveBeenCalledWith('labels', expect.anything(), null);
  });

  it('toggles selection off on second X and wraps roving focus at list bounds', () => {
    const twoIssues = FIXTURE_12_ISSUES.slice(0, 2);

    function TestComponent() {
      const [selectedIds, setSelectedIds] = useState<string[]>([]);
      const { focusedKey } = useIssueKeyboardMap({
        issues: twoIssues,
        layout: 'list',
        selectedIds,
        setSelectedIds,
      });

      return (
        <div>
          <span data-testid="focused">{focusedKey ?? 'none'}</span>
          <span data-testid="selected-count">{selectedIds.length}</span>
        </div>
      );
    }

    render(<TestComponent />);

    // Press 'K' while at top -> wraps to bottom
    fireEvent.keyDown(window, { key: 'k' });
    expect(screen.getByTestId('focused').textContent).toBe(twoIssues[1]?.key);

    // Press 'J' while at bottom -> wraps to top
    fireEvent.keyDown(window, { key: 'j' });
    expect(screen.getByTestId('focused').textContent).toBe(twoIssues[0]?.key);

    // Press 'X' -> selected
    fireEvent.keyDown(window, { key: 'x' });
    expect(screen.getByTestId('selected-count').textContent).toBe('1');

    // Press 'X' again -> toggles off!
    fireEvent.keyDown(window, { key: 'x' });
    expect(screen.getByTestId('selected-count').textContent).toBe('0');
  });

  it('Shift+Click range selection across 5 items selects all 5 and caps at 100 (Test Case 4)', () => {
    const { result } = renderHook(() => {
      const [selectedIds, setSelectedIds] = useState<string[]>([]);
      const map = useIssueKeyboardMap({
        issues: FIXTURE_12_ISSUES,
        layout: 'list',
        selectedIds,
        setSelectedIds,
        modulesEnabled: true,
      });
      return { ...map, selectedIds, setSelectedIds };
    });

    // Click first item KAN-140
    act(() => {
      result.current.handleRowClick('KAN-140', false);
    });
    expect(result.current.selectedIds).toEqual(['KAN-140']);

    // Shift+Click unknown item (toIndex === -1 early return)
    act(() => {
      result.current.handleRowClick('UNKNOWN-999', true);
    });
    expect(result.current.selectedIds).toEqual(['KAN-140']);

    // Click first item KAN-140 again to deselect
    act(() => {
      result.current.handleRowClick('KAN-140', false);
    });
    expect(result.current.selectedIds).toEqual([]);

    // Click again to reselect
    act(() => {
      result.current.handleRowClick('KAN-140', false);
    });

    // Shift+Click fifth item KAN-144 (indices 0 to 4 inclusive -> 5 items)
    act(() => {
      result.current.handleRowClick('KAN-144', true);
    });
    expect(result.current.selectedIds).toHaveLength(5);
    expect(result.current.selectedIds).toEqual([
      'KAN-140',
      'KAN-141',
      'KAN-142',
      'KAN-143',
      'KAN-144',
    ]);
  });

  it('handles empty issues list, popover/modal open guard, 100 cap on X, and M shortcut when enabled', () => {
    const handleOpenField = vi.fn();
    const handleOpenCreate = vi.fn();

    // 1. Empty issues list
    const { rerender } = renderHook(
      ({ issues, isOpen, selectedIds }: { issues: IssueItem[]; isOpen: boolean; selectedIds: string[] }) => {
        const [sel, setSel] = useState<string[]>(selectedIds);
        return useIssueKeyboardMap({
          issues,
          layout: 'board',
          selectedIds: sel,
          setSelectedIds: setSel,
          modulesEnabled: true,
          isPopoverOrModalOpen: isOpen,
          onOpenFieldPopover: handleOpenField,
          onOpenCreateModal: handleOpenCreate,
        });
      },
      {
        initialProps: { issues: [] as IssueItem[], isOpen: false, selectedIds: [] as string[] },
      }
    );

    fireEvent.keyDown(window, { key: 'j' });
    fireEvent.keyDown(window, { key: 'x' });
    expect(handleOpenCreate).not.toHaveBeenCalled();

    // 2. isPopoverOrModalOpen: true blocks shortcuts
    rerender({ issues: FIXTURE_12_ISSUES, isOpen: true, selectedIds: [] });
    fireEvent.keyDown(window, { key: 'c' });
    fireEvent.keyDown(window, { key: 'j' });
    expect(handleOpenCreate).not.toHaveBeenCalled();

    // 3. M shortcut when modulesEnabled is true
    rerender({ issues: FIXTURE_12_ISSUES, isOpen: false, selectedIds: [] });
    fireEvent.keyDown(window, { key: 'm' });
    expect(handleOpenField).toHaveBeenCalledWith('module', expect.anything(), null);

    // 4. Capped at 100 items on X toggle
    const hundred = Array.from({ length: 100 }, (_, i) => `KAN-${String(i + 1)}`);
    const { result: capResult } = renderHook(() => {
      const [sel, setSel] = useState<string[]>(hundred);
      return {
        map: useIssueKeyboardMap({
          issues: FIXTURE_12_ISSUES,
          layout: 'list',
          selectedIds: sel,
          setSelectedIds: setSel,
        }),
        sel,
      };
    });

    fireEvent.keyDown(window, { key: 'x' });
    expect(capResult.current.sel.length).toBe(100);

    // 5. IME composition and modifier key shields
    fireEvent.keyDown(window, { key: 'c', isComposing: true });
    fireEvent.keyDown(window, { key: 'c', ctrlKey: true });
    fireEvent.keyDown(window, { key: 'c', metaKey: true });
    fireEvent.keyDown(window, { key: 'c', altKey: true });
    expect(handleOpenCreate).not.toHaveBeenCalled();

    // 6. Range select capping when total items in range exceed 100
    const baseItem = FIXTURE_12_ISSUES[0];
    if (!baseItem) throw new Error('missing fixture');
    const manyIssues: IssueItem[] = Array.from({ length: 150 }, (_, i) => ({
      ...baseItem,
      id: `id-${String(i + 1)}`,
      key: `KAN-${String(i + 1)}`,
    }));
    const { result: rangeResult } = renderHook(() => {
      const [sel, setSel] = useState<string[]>([]);
      const map = useIssueKeyboardMap({
        issues: manyIssues,
        layout: 'list',
        selectedIds: sel,
        setSelectedIds: setSel,
      });
      return { ...map, sel };
    });

    act(() => {
      rangeResult.current.handleRowClick('KAN-1', false);
    });
    act(() => {
      rangeResult.current.handleRowClick('KAN-150', true);
    });
    expect(rangeResult.current.sel.length).toBe(100);
  });

  it('handles Enter when focusedKey is null, wrapping on L at list bounds, and unmapped keys', () => {
    const twoIssues = FIXTURE_12_ISSUES.slice(0, 2);

    function TestComponent() {
      const [selectedIds, setSelectedIds] = useState<string[]>([]);
      const { focusedKey, setFocusedKey } = useIssueKeyboardMap({
        issues: twoIssues,
        layout: 'board',
        selectedIds,
        setSelectedIds,
      });

      return (
        <div>
          <span data-testid="focused">{focusedKey ?? 'none'}</span>
          <button
            type="button"
            data-testid="set-last"
            onClick={() => {
              const lastKey = twoIssues[1]?.key;
              if (lastKey) setFocusedKey(lastKey);
            }}
          >
            Set Last
          </button>
        </div>
      );
    }

    render(<TestComponent />);

    // Press Enter while focusedKey is null (strict no-op)
    fireEvent.keyDown(window, { key: 'Enter' });
    fireEvent.keyDown(window, { key: ' ' });

    // Set focus to last issue (index 1 of 2)
    fireEvent.click(screen.getByTestId('set-last'));
    expect(screen.getByTestId('focused').textContent).toBe(twoIssues[1]?.key);

    // Press 'H' while at index 1 -> moves to index 0
    fireEvent.keyDown(window, { key: 'h' });
    expect(screen.getByTestId('focused').textContent).toBe(twoIssues[0]?.key);

    // Press 'H' while at index 0 -> wraps to index 1
    fireEvent.keyDown(window, { key: 'h' });
    expect(screen.getByTestId('focused').textContent).toBe(twoIssues[1]?.key);

    // Press 'L' at bounds -> wraps to index 0
    fireEvent.keyDown(window, { key: 'l' });
    expect(screen.getByTestId('focused').textContent).toBe(twoIssues[0]?.key);

    // Press unmapped key 'z'
    fireEvent.keyDown(window, { key: 'z' });
  });

  it('covers K pressed with null anchorKey, Escape with open dialog, and selectRange edge cases', () => {
    // 1. Press K with null anchorKey
    const { result: kResult } = renderHook(() => {
      const [sel, setSel] = useState<string[]>(['KAN-140']);
      const map = useIssueKeyboardMap({
        issues: FIXTURE_12_ISSUES,
        layout: 'board',
        selectedIds: sel,
        setSelectedIds: setSel,
        isPopoverOrModalOpen: true, // open dialog
      });
      return { ...map, sel };
    });

    // Press Escape while dialog is open -> does not clear sel
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(kResult.current.sel).toEqual(['KAN-140']);

    // 2. Press K when dialog is closed and anchorKey is null
    const { result: kResult2 } = renderHook(() => {
      const [sel, setSel] = useState<string[]>([]);
      return useIssueKeyboardMap({
        issues: FIXTURE_12_ISSUES,
        layout: 'board',
        selectedIds: sel,
        setSelectedIds: setSel,
        isPopoverOrModalOpen: false,
      });
    });

    fireEvent.keyDown(window, { key: 'k' });
    expect(kResult2.current.anchorKey).toBe(FIXTURE_12_ISSUES[FIXTURE_12_ISSUES.length - 1]?.key);

    // 3. selectRange with invalid anchorKey (fromIndex === -1)
    act(() => {
      kResult2.current.setAnchorKey('DELETED_KEY');
    });
    // Trigger shift+click on valid key
    act(() => {
      kResult2.current.handleRowClick('KAN-140', true);
    });

    // 4. selectRange with empty issues list (!fromKey)
    const { result: emptyHook } = renderHook(() => {
      const [sel, setSel] = useState<string[]>([]);
      return useIssueKeyboardMap({
        issues: [],
        layout: 'board',
        selectedIds: sel,
        setSelectedIds: setSel,
      });
    });
    act(() => {
      emptyHook.current.handleRowClick('KAN-140', true);
    });
  });
});
