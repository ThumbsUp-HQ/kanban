import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { BoardCard } from '../../board/BoardCard.tsx';
import type { BoardIssue, BoardWorkflowState } from '../../board/boardApi.ts';
import { StickyCard } from '../../stickies/StickyCard.tsx';
import type { StickyItem } from '../../stickies/stickiesApi.ts';
import { TouchReorderPopover } from '../TouchReorderPopover.tsx';
import { useTouchDragSensor } from '../useTouchDragSensor.ts';

const mockStates: BoardWorkflowState[] = [
  { id: 'st-backlog', name: 'Backlog', group: 'backlog', sort_order: 1 },
  { id: 'st-todo', name: 'To Do', group: 'unstarted', sort_order: 2 },
  { id: 'st-progress', name: 'In Progress', group: 'started', sort_order: 3 },
  { id: 'st-review', name: 'In Review', group: 'started', sort_order: 4 },
  { id: 'st-done', name: 'Done', group: 'completed', sort_order: 5 },
];

const mockIssue: BoardIssue = {
  id: 'iss-touch-1',
  key: 'KAN-142',
  summary: 'Tune mobile touch sensor and popovers',
  state_id: 'st-todo',
  board_rank: '0000000000000010',
  priority: { id: 'p2', label: 'High', slug: 'high' },
};

const mockSticky: StickyItem = {
  id: 'stk-touch-1',
  workspace_id: 'ws-1',
  project_id: 'proj-1',
  body_markdown: 'Mobile ergonomics scratchpad',
  color_token: 'amber',
  sort_rank: '0000000000000050',
  promotion_recommended: false,
  promotion_snoozed_at_length: null,
  promoted_to_doc_id: null,
  is_promoted_stub: false,
  triggers: [],
  capabilities: ['VIEW', 'EDIT', 'DELETE'],
};

describe('BoardTouchInteractions Component Suite (KAN-342)', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.runOnlyPendingTimers();
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  /**
   * Required Test Case 1: Positive case verifying mobile quick-move action button
   * renders on touch devices and triggers state transition on selection.
   */
  it('Required Case 1: positive case verifying mobile quick-move action button renders on touch devices and triggers state transition on selection', () => {
    const onStateTransition = vi.fn();
    const onKeyboardMove = vi.fn();

    render(
      <BoardCard
        issue={mockIssue}
        stateGroup="unstarted"
        projectStates={mockStates}
        onStateTransition={onStateTransition}
        onKeyboardMove={onKeyboardMove}
      />,
    );

    // 1. Mobile quick-move action button renders with touch affordance
    const touchActionBtn = screen.getByTestId('board-card-touch-action-KAN-142');
    expect(touchActionBtn).toBeDefined();
    expect(touchActionBtn.getAttribute('aria-label')).toBe('Quick move KAN-142');

    // 2. Tapping the quick-move button opens the touch reorder popover
    fireEvent.click(touchActionBtn);

    const popover = screen.getByTestId('touch-reorder-popover');
    expect(popover).toBeDefined();
    expect(screen.getByText('Move KAN-142')).toBeDefined();

    // 3. Target workflow states are listed
    const doneOption = screen.getByTestId('touch-state-option-st-done');
    expect(doneOption).toBeDefined();

    // 4. Selecting target state triggers state transition callback
    fireEvent.click(doneOption);
    expect(onStateTransition).toHaveBeenCalledWith('KAN-142', 'st-done');

    // 5. Popover closes cleanly after selection
    expect(screen.queryByTestId('touch-reorder-popover')).toBeNull();
  });

  /**
   * Required Test Case 2: Negative case verifying drag sensor does not trigger
   * when user performs a standard touch scroll gesture.
   */
  it('Required Case 2: negative case verifying drag sensor does not trigger when user performs a standard touch scroll gesture', () => {
    const { container } = render(
      <BoardCard
        issue={mockIssue}
        stateGroup="unstarted"
        projectStates={mockStates}
      />,
    );

    const card = screen.getByTestId('board-card-KAN-142');
    expect(card.className).not.toContain('board-card--touch-lifted');

    // User touches screen at (100, 100)
    fireEvent.touchStart(card, {
      touches: [{ clientX: 100, clientY: 100 }],
    });

    // Advance 50ms (before the 200ms delay threshold)
    act(() => {
      vi.advanceTimersByTime(50);
    });

    // User performs standard vertical scroll gesture: moves finger to (100, 125)
    // Distance = 25px, which exceeds the 8px tolerance threshold!
    fireEvent.touchMove(card, {
      touches: [{ clientX: 100, clientY: 125 }],
    });

    // Advance past the 200ms threshold (to 300ms total)
    act(() => {
      vi.advanceTimersByTime(250);
    });

    // Drag sensor must NOT activate: no visual lift indicator, no dragging state
    expect(card.className).not.toContain('board-card--touch-lifted');
    expect(card.getAttribute('data-touch-lifted')).toBeNull();
    expect(container.querySelector('.board-card--touch-lifted')).toBeNull();
    expect(screen.queryByTestId('touch-reorder-popover')).toBeNull();
  });

  /**
   * Required Test Case 3: Boundary case verifying reorder popover closes cleanly
   * on tap outside or backdrop dismiss without state mutation.
   */
  it('Required Case 3: boundary case verifying reorder popover closes cleanly on tap outside or backdrop dismiss without state mutation', () => {
    const onStateTransition = vi.fn();

    render(
      <BoardCard
        issue={mockIssue}
        stateGroup="unstarted"
        projectStates={mockStates}
        onStateTransition={onStateTransition}
      />,
    );

    // Open touch reorder popover
    const touchActionBtn = screen.getByTestId('board-card-touch-action-KAN-142');
    fireEvent.click(touchActionBtn);
    expect(screen.getByTestId('touch-reorder-popover')).toBeDefined();

    // Backdrop element exists
    const backdrop = screen.getByTestId('touch-reorder-backdrop');
    expect(backdrop).toBeDefined();

    // Tap backdrop overlay to dismiss
    fireEvent.click(backdrop);

    // Popover is removed from DOM
    expect(screen.queryByTestId('touch-reorder-popover')).toBeNull();

    // Crucial: Zero state mutation occurred
    expect(onStateTransition).not.toHaveBeenCalled();
  });

  it('verifies cancel button and Escape key dismiss popover with zero state mutation', () => {
    const onStateTransition = vi.fn();

    const { rerender } = render(
      <BoardCard
        issue={mockIssue}
        stateGroup="unstarted"
        projectStates={mockStates}
        onStateTransition={onStateTransition}
      />,
    );

    // 1. Test Cancel button dismiss
    fireEvent.click(screen.getByTestId('board-card-touch-action-KAN-142'));
    expect(screen.getByTestId('touch-reorder-popover')).toBeDefined();

    const cancelBtn = screen.getByTestId('touch-reorder-cancel-btn');
    fireEvent.click(cancelBtn);
    expect(screen.queryByTestId('touch-reorder-popover')).toBeNull();
    expect(onStateTransition).not.toHaveBeenCalled();

    // 2. Test Escape key dismiss
    fireEvent.click(screen.getByTestId('board-card-touch-action-KAN-142'));
    expect(screen.getByTestId('touch-reorder-popover')).toBeDefined();

    fireEvent.keyDown(window, { key: 'Escape' });
    expect(screen.queryByTestId('touch-reorder-popover')).toBeNull();
    expect(onStateTransition).not.toHaveBeenCalled();

    // 3. Test Close (X) button dismiss
    rerender(
      <BoardCard
        issue={mockIssue}
        stateGroup="unstarted"
        projectStates={mockStates}
        onStateTransition={onStateTransition}
      />,
    );
    fireEvent.click(screen.getByTestId('board-card-touch-action-KAN-142'));
    fireEvent.click(screen.getByTestId('touch-reorder-close-btn'));
    expect(screen.queryByTestId('touch-reorder-popover')).toBeNull();
    expect(onStateTransition).not.toHaveBeenCalled();
  });

  it('verifies long-press triggers visual lift indicator and haptic feedback when movement stays within 8px tolerance for 200ms', () => {
    const vibrateMock = vi.fn();
    Object.defineProperty(navigator, 'vibrate', {
      value: vibrateMock,
      configurable: true,
      writable: true,
    });

    render(
      <BoardCard
        issue={mockIssue}
        stateGroup="unstarted"
        projectStates={mockStates}
      />,
    );

    const card = screen.getByTestId('board-card-KAN-142');

    // Touch start at (200, 200)
    fireEvent.touchStart(card, {
      touches: [{ clientX: 200, clientY: 200 }],
    });

    // Slight micro-jitter: finger moves 2px to (201, 202) -> distance ~2.2px <= 8px tolerance
    act(() => {
      vi.advanceTimersByTime(100);
    });
    fireEvent.touchMove(card, {
      touches: [{ clientX: 201, clientY: 202 }],
    });

    // Advance remaining 100ms to complete 200ms threshold
    act(() => {
      vi.advanceTimersByTime(100);
    });

    // Card should now have visual lift indicator
    expect(card.className).toContain('board-card--touch-lifted');
    expect(card.getAttribute('data-touch-lifted')).toBe('true');
    expect(vibrateMock).toHaveBeenCalledWith(50);

    // Touch end clears the lifted state
    fireEvent.touchEnd(card);
    expect(card.className).not.toContain('board-card--touch-lifted');
  });

  it('supports explicit rank position selection (top/bottom) and Move Card action in TouchReorderPopover', () => {
    const onStateTransition = vi.fn();
    const onKeyboardMove = vi.fn();

    render(
      <BoardCard
        issue={mockIssue}
        stateGroup="unstarted"
        projectStates={mockStates}
        onStateTransition={onStateTransition}
        onKeyboardMove={onKeyboardMove}
      />,
    );

    fireEvent.click(screen.getByTestId('board-card-touch-action-KAN-142'));

    // Select top rank position
    const topRankBtn = screen.getByTestId('touch-rank-top');
    fireEvent.click(topRankBtn);
    expect(topRankBtn.className).toContain('touch-reorder-rank-btn--active');

    // Click Apply Move button
    const applyBtn = screen.getByTestId('touch-reorder-apply-btn');
    fireEvent.click(applyBtn);

    expect(onStateTransition).toHaveBeenCalledWith('KAN-142', 'st-todo');
    expect(onKeyboardMove).toHaveBeenCalledWith(mockIssue, 'up');
    expect(screen.queryByTestId('touch-reorder-popover')).toBeNull();
  });

  it('renders mobile touch quick-action on StickyCard and triggers rank reorder', () => {
    const onUpdate = vi.fn();
    const onDelete = vi.fn();
    const onPromote = vi.fn();

    render(
      <StickyCard
        sticky={mockSticky}
        onUpdate={onUpdate}
        onDelete={onDelete}
        onPromote={onPromote}
      />,
    );

    const stickyActionBtn = screen.getByTestId('sticky-touch-action-stk-touch-1');
    expect(stickyActionBtn).toBeDefined();

    // Click sticky touch action button
    fireEvent.click(stickyActionBtn);

    expect(screen.getByTestId('touch-reorder-popover')).toBeDefined();
    expect(screen.getByText('Move Sticky-stk-to')).toBeDefined();

    // Select Top rank
    fireEvent.click(screen.getByTestId('touch-rank-top'));

    expect(onUpdate).toHaveBeenCalledWith(
      'stk-touch-1',
      { sort_rank: '0000000000000001' },
      undefined,
    );
    expect(screen.queryByTestId('touch-reorder-popover')).toBeNull();
  });

  it('handles multi-touch gesture cancellation and touchcancel events in useTouchDragSensor', () => {
    function TestSensorComponent() {
      const { isTouchLifted, touchHandlers } = useTouchDragSensor({ delay: 200, tolerance: 8 });
      return (
        <div data-testid="sensor-target" data-lifted={String(isTouchLifted)} {...touchHandlers}>
          Sensor Target
        </div>
      );
    }

    render(<TestSensorComponent />);
    const el = screen.getByTestId('sensor-target');

    // Multi-touch (>1 touches) cancels touch sensor immediately
    fireEvent.touchStart(el, {
      touches: [{ clientX: 10, clientY: 10 }, { clientX: 20, clientY: 20 }],
    });
    act(() => {
      vi.advanceTimersByTime(300);
    });
    expect(el.getAttribute('data-lifted')).toBe('false');

    // Touch start then touchcancel cancels touch sensor
    fireEvent.touchStart(el, {
      touches: [{ clientX: 50, clientY: 50 }],
    });
    fireEvent.touchCancel(el);
    act(() => {
      vi.advanceTimersByTime(300);
    });
    expect(el.getAttribute('data-lifted')).toBe('false');
  });

  it('verifies standalone TouchReorderPopover renders correctly when closed', () => {
    const { container } = render(
      <TouchReorderPopover
        isOpen={false}
        itemKey="KAN-999"
        onClose={vi.fn()}
      />,
    );
    expect(container.firstChild).toBeNull();
  });

  it('covers TouchReorderPopover fallback to first state when currentStateId is undefined', () => {
    const onSelectState = vi.fn();
    const onSelectRank = vi.fn();
    const onApplyMove = vi.fn();

    render(
      <TouchReorderPopover
        isOpen={true}
        itemKey="KAN-500"
        itemSummary="Issue without initial state"
        states={mockStates}
        onClose={vi.fn()}
        onSelectState={onSelectState}
        onSelectRank={onSelectRank}
        onApplyMove={onApplyMove}
      />,
    );

    expect(screen.getByTestId('touch-state-option-st-backlog')).toBeDefined();

    // Select rank top
    fireEvent.click(screen.getByTestId('touch-rank-top'));
    expect(onSelectRank).toHaveBeenCalledWith('top');

    // Click Apply Move button
    fireEvent.click(screen.getByTestId('touch-reorder-apply-btn'));
    expect(onApplyMove).toHaveBeenCalledWith('st-backlog', 'top');
    expect(onSelectState).toHaveBeenCalledWith('st-backlog');
  });

  it('covers TouchReorderPopover apply for sticky notes', () => {
    const onReorderSticky = vi.fn();
    const onClose = vi.fn();

    render(
      <TouchReorderPopover
        isOpen={true}
        itemKey="Sticky-123"
        kind="sticky"
        onClose={onClose}
        onReorderSticky={onReorderSticky}
      />,
    );

    fireEvent.click(screen.getByTestId('touch-rank-bottom'));
    fireEvent.click(screen.getByTestId('touch-reorder-apply-btn'));

    expect(onReorderSticky).toHaveBeenCalledWith('bottom');
    expect(onClose).toHaveBeenCalled();
  });

  it('cancels lifted state if movement exceeds tolerance after lift activation', () => {
    render(
      <BoardCard
        issue={mockIssue}
        stateGroup="unstarted"
        projectStates={mockStates}
      />,
    );

    const card = screen.getByTestId('board-card-KAN-142');

    // Touch start and hold for 200ms -> activates lift
    fireEvent.touchStart(card, {
      touches: [{ clientX: 100, clientY: 100 }],
    });
    act(() => {
      vi.advanceTimersByTime(200);
    });
    expect(card.className).toContain('board-card--touch-lifted');

    // Now user moves finger > 8px (to 100, 130) -> scroll gesture post-lift cancels lift
    fireEvent.touchMove(card, {
      touches: [{ clientX: 100, clientY: 130 }],
    });
    expect(card.className).not.toContain('board-card--touch-lifted');
  });

  it('covers remaining branch edge cases in TouchReorderPopover and useTouchDragSensor', () => {
    // 1. TouchReorderPopover with empty states
    const { rerender } = render(
      <TouchReorderPopover
        isOpen={true}
        itemKey="EMPTY-1"
        states={[]}
        onClose={vi.fn()}
      />,
    );
    expect(screen.getByTestId('touch-reorder-popover')).toBeDefined();

    // Keydown other than Escape
    fireEvent.keyDown(window, { key: 'Tab' });
    expect(screen.getByTestId('touch-reorder-popover')).toBeDefined();

    // Apply with empty state
    fireEvent.click(screen.getByTestId('touch-reorder-apply-btn'));

    // 2. useTouchDragSensor edge cases: onTouchMove without start coords, navigator without vibrate
    function DummySensor() {
      const { touchHandlers } = useTouchDragSensor();
      return (
        <div data-testid="dummy-sensor" {...touchHandlers}>
          Dummy
        </div>
      );
    }
    rerender(<DummySensor />);
    const dummy = screen.getByTestId('dummy-sensor');

    // Move without start
    fireEvent.touchMove(dummy, { touches: [{ clientX: 50, clientY: 50 }] });

    // Touch start without touches array element
    fireEvent.touchStart(dummy, { touches: [] });

    // Touch start with vibrate throwing
    Object.defineProperty(navigator, 'vibrate', {
      value: () => {
        throw new Error('Vibration disabled');
      },
      configurable: true,
      writable: true,
    });
    fireEvent.touchStart(dummy, { touches: [{ clientX: 10, clientY: 10 }] });
    act(() => {
      vi.advanceTimersByTime(200);
    });
  });
});
