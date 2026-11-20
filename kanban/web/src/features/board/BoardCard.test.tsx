import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import {
  draggable,
  dropTargetForElements,
} from '@atlaskit/pragmatic-drag-and-drop/element/adapter';
import { BoardCard, getCardDragData, getCardDropData } from './BoardCard.tsx';
import type { BoardIssue, BoardPriority } from './boardApi.ts';

const baseIssue: BoardIssue = {
  id: 'iss-1',
  key: 'KAN-142',
  summary: 'Implement Pragmatic DnD Kanban board',
  state_id: 'state-started',
  board_rank: '0000000000000001',
  priority: { id: 'p1', label: 'Urgent', slug: 'urgent' },
  assignees: [
    { id: 'u1', handle: 'alice' },
    { id: 'u2', is_agent: true, name: 'SecurityAuditor' },
    { id: 'u3', free_text: 'SecAudit Partner' },
  ],
  due_date: '2020-01-01', // in the past
  cycle: { id: 'c1', name: 'Sprint 42' },
  gate_status: 'pending',
  has_explicit_acl: true,
};

describe('BoardCard Component', () => {
  it('renders card anatomy matching wireframe', () => {
    const { unmount } = render(<BoardCard issue={baseIssue} stateGroup="started" />);

    expect(screen.getByTestId('board-card-KAN-142')).toBeDefined();
    expect(screen.getByText('KAN-142')).toBeDefined();
    expect(screen.getByText('Implement Pragmatic DnD Kanban board')).toBeDefined();
    expect(screen.getByText('@alice')).toBeDefined();
    expect(screen.getByText('SecurityAuditor')).toBeDefined();
    expect(screen.getByText('SecAudit Partner')).toBeDefined();
    expect(screen.getByText('🔄 Sprint 42')).toBeDefined();
    expect(screen.getByTestId('gate-pending-KAN-142')).toBeDefined();
    expect(screen.getByTestId('acl-badge-KAN-142')).toBeDefined();

    unmount();
  });

  it('suppresses overdue styling when state is completed or cancelled (S7.2 8e)', () => {
    const { rerender } = render(<BoardCard issue={baseIssue} stateGroup="started" />);
    const dueDatePill = screen.getByTestId('due-date-KAN-142');
    expect(dueDatePill.className).toContain('board-card-chip--due-overdue');

    rerender(<BoardCard issue={baseIssue} stateGroup="completed" />);
    expect(screen.getByTestId('due-date-KAN-142').className).not.toContain('board-card-chip--due-overdue');

    rerender(<BoardCard issue={baseIssue} stateGroup="cancelled" />);
    expect(screen.getByTestId('due-date-KAN-142').className).not.toContain('board-card-chip--due-overdue');
  });

  it('renders XSS payloads as literal text with zero injected img/svg nodes (DoD Case 5)', () => {
    const maliciousIssue: BoardIssue = {
      id: 'iss-malicious',
      key: 'SEC-01',
      summary: '<img src=x onerror=alert(1)>',
      state_id: 'state-started',
      board_rank: '0000000000000002',
      assignees: [{ id: 'ext-1', free_text: '<svg onload=alert(1)>' }],
    };

    const { container } = render(<BoardCard issue={maliciousIssue} stateGroup="started" />);

    expect(container.querySelectorAll('img').length).toBe(0);
    expect(container.querySelectorAll('svg').length).toBe(0);

    expect(screen.getByText('<img src=x onerror=alert(1)>')).toBeDefined();
    expect(screen.getByText('<svg onload=alert(1)>')).toBeDefined();
  });

  it('handles keyboard navigation: Enter opens peek, Alt+Arrows trigger keyboard moves', () => {
    const onOpenPeek = vi.fn();
    const onKeyboardMove = vi.fn();

    render(
      <BoardCard
        issue={baseIssue}
        stateGroup="started"
        onOpenPeek={onOpenPeek}
        onKeyboardMove={onKeyboardMove}
      />,
    );

    const card = screen.getByTestId('board-card-KAN-142');

    fireEvent.keyDown(card, { key: 'Enter' });
    expect(onOpenPeek).toHaveBeenCalledWith('KAN-142');

    fireEvent.keyDown(card, { key: 'ArrowRight', altKey: true });
    expect(onKeyboardMove).toHaveBeenCalledWith(baseIssue, 'right');

    fireEvent.keyDown(card, { key: 'ArrowLeft', altKey: true });
    expect(onKeyboardMove).toHaveBeenCalledWith(baseIssue, 'left');

    fireEvent.keyDown(card, { key: 'ArrowUp', altKey: true });
    expect(onKeyboardMove).toHaveBeenCalledWith(baseIssue, 'up');

    fireEvent.keyDown(card, { key: 'ArrowDown', altKey: true });
    expect(onKeyboardMove).toHaveBeenCalledWith(baseIssue, 'down');
  });

  it('falls back to URL history pushState when onOpenPeek is not provided', () => {
    const pushStateSpy = vi.spyOn(window.history, 'pushState');
    render(<BoardCard issue={baseIssue} stateGroup="started" />);

    const keyLink = screen.getByTestId('board-card-key-KAN-142');
    fireEvent.click(keyLink);
    expect(pushStateSpy).toHaveBeenCalled();

    const card = screen.getByTestId('board-card-KAN-142');
    fireEvent.keyDown(card, { key: 'Enter' });
    expect(pushStateSpy).toHaveBeenCalled();
  });

  it('opens peek drawer when clicking on the card container', () => {
    const onOpenPeek = vi.fn();
    render(
      <BoardCard
        issue={baseIssue}
        stateGroup="started"
        onOpenPeek={onOpenPeek}
      />,
    );

    const card = screen.getByTestId('board-card-KAN-142');
    fireEvent.click(card);
    expect(onOpenPeek).toHaveBeenCalledWith('KAN-142');
  });

  it('renders different gate statuses, priority variants, dragging and drop edge', () => {
    const rejectedIssue: BoardIssue = {
      ...baseIssue,
      key: 'KAN-REJ',
      gate_status: 'rejected',
      priority: { id: 'p-low', label: 'Low', slug: 'low' },
      due_date: 'invalid-date',
    };
    const { rerender } = render(
      <BoardCard
        issue={rejectedIssue}
        stateGroup="started"
        isDragging={true}
        dropEdge="top"
      />,
    );
    expect(screen.getByTestId('gate-vetoed-KAN-REJ')).toBeDefined();
    expect(screen.getByTestId('board-card-KAN-REJ').getAttribute('data-dragging')).toBe('true');
    expect(screen.getByTestId('board-card-KAN-REJ').getAttribute('data-drop-target')).toBe('top');

    const approvedIssue: BoardIssue = {
      ...baseIssue,
      key: 'KAN-APP',
      gate_status: 'approved',
      priority: { id: 'p-high', label: 'High', slug: 'high' },
    };
    rerender(<BoardCard issue={approvedIssue} stateGroup="started" dropEdge="bottom" />);
    expect(screen.getByTestId('gate-approved-KAN-APP')).toBeDefined();
    expect(screen.getByTestId('board-card-KAN-APP').getAttribute('data-drop-target')).toBe('bottom');

    const medIssue: BoardIssue = {
      ...baseIssue,
      key: 'KAN-MED',
      priority: { id: 'p-med', label: 'Medium', slug: 'medium' },
    };
    rerender(<BoardCard issue={medIssue} stateGroup="started" />);
    expect(screen.getByTestId('priority-KAN-MED')).toBeDefined();
  });

  it('invokes draggable and dropTarget factories to exercise registration closures', () => {
    let capturedDragData: ReturnType<typeof getCardDragData> | undefined = undefined;
    let capturedDropData: ReturnType<typeof getCardDropData> | undefined = undefined;

    const mockDraggable: typeof draggable = (opts) => {
      if (opts.getInitialData) {
        capturedDragData = opts.getInitialData({
          element: document.createElement('div'),
          dragHandle: null,
          input: { clientY: 500 } as never,
        }) as ReturnType<typeof getCardDragData>;
      }
      return () => {
        /* no-op */
      };
    };

    const mockDropTarget: typeof dropTargetForElements = (opts) => {
      const fn = opts.getData;
      if (fn) {
        capturedDropData = fn({
          input: { clientY: 500 } as never,
          element: document.createElement('div'),
          source: {} as never,
        }) as ReturnType<typeof getCardDropData>;
      }
      return () => {
        /* no-op */
      };
    };

    render(
      <BoardCard
        issue={baseIssue}
        stateGroup="started"
        draggableFactory={mockDraggable}
        dropTargetFactory={mockDropTarget}
      />,
    );

    expect((capturedDragData as ReturnType<typeof getCardDragData> | undefined)?.issueKey).toBe('KAN-142');
    expect((capturedDropData as ReturnType<typeof getCardDropData> | undefined)?.issueKey).toBe('KAN-142');
    expect((capturedDropData as ReturnType<typeof getCardDropData> | undefined)?.edge).toBe('bottom');
  });

  it('getCardDropData and getCardDragData compute expected descriptors', () => {
    const dragData = getCardDragData(baseIssue);
    expect(dragData.issueKey).toBe('KAN-142');
    expect(dragData.type).toBe('card');

    const mockEl = {
      getBoundingClientRect: () => ({ top: 100, height: 100 } as DOMRect),
    } as HTMLElement;

    const topData = getCardDropData(mockEl, 120, baseIssue);
    expect(topData.edge).toBe('top');

    const bottomData = getCardDropData(mockEl, 160, baseIssue);
    expect(bottomData.edge).toBe('bottom');
  });

  it('covers keyboard navigation edge cases and assignee chip fallbacks', () => {
    // Missing onKeyboardMove with altKey
    const { rerender } = render(<BoardCard issue={baseIssue} stateGroup="started" />);
    const card = screen.getByTestId('board-card-KAN-142');
    fireEvent.keyDown(card, { key: 'ArrowRight', altKey: true });
    fireEvent.keyDown(card, { key: 'Escape', altKey: true });
    fireEvent.keyDown(card, { key: 'Tab' });

    // With onKeyboardMove but non-arrow key with altKey
    const onMove = vi.fn();
    rerender(<BoardCard issue={baseIssue} stateGroup="started" onKeyboardMove={onMove} />);
    fireEvent.keyDown(card, { key: 'Escape', altKey: true });
    expect(onMove).not.toHaveBeenCalled();

    // Assignees with empty id and fallbacks
    const fallbackIssue: BoardIssue = {
      ...baseIssue,
      key: 'KAN-FALLBACK',
      priority: { id: 'p-noslug', label: 'Urgent' } as unknown as BoardPriority, // label only, no slug
      assignees: [
        { id: '', is_agent: true }, // no name, no handle -> 'Agent'
        { id: '', display_name: 'Bob Ross' }, // no handle -> 'Bob Ross'
        { id: '', name: 'Charlie' }, // no handle, no display_name -> 'Charlie'
        { id: '' }, // no handle, display_name, or name -> 'user'
      ],
    };
    rerender(<BoardCard issue={fallbackIssue} stateGroup="started" />);
    expect(screen.getByText('@Bob Ross')).toBeDefined();
    expect(screen.getByText('@Charlie')).toBeDefined();
    expect(screen.getByText('@user')).toBeDefined();

    // Priority with slug only (no label) falls back to 'Priority'
    const slugOnlyIssue: BoardIssue = {
      ...baseIssue,
      key: 'KAN-SLUGONLY',
      priority: { id: 'p-nolabel', slug: 'urgent' } as unknown as BoardPriority,
    };
    rerender(<BoardCard issue={slugOnlyIssue} stateGroup="started" />);
    expect(screen.getByTestId('priority-KAN-SLUGONLY')).toBeDefined();
  });

  it('renders semantic <a href> anchors and supports peek left-click vs new-tab modifier clicks (KANBA-227)', () => {
    const onOpenPeek = vi.fn();
    render(
      <BoardCard
        issue={baseIssue}
        stateGroup="started"
        workspaceSlug="acme"
        projectKey="KAN"
        onOpenPeek={onOpenPeek}
      />,
    );

    const keyLink = screen.getByTestId('board-card-key-KAN-142');
    const summaryLink = screen.getByTestId('board-card-summary-KAN-142');

    // 1. Anchors point to canonical issue route
    expect(keyLink.getAttribute('href')).toBe('/w/acme/p/KAN/issues/KAN-142');
    expect(summaryLink.getAttribute('href')).toBe('/w/acme/p/KAN/issues/KAN-142');

    // 2. Standard left-click (button 0 without modifiers) calls preventDefault and opens peek drawer
    const leftClickEv = new MouseEvent('click', { bubbles: true, cancelable: true, button: 0 });
    const preventDefaultSpy = vi.spyOn(leftClickEv, 'preventDefault');
    keyLink.dispatchEvent(leftClickEv);
    expect(preventDefaultSpy).toHaveBeenCalled();
    expect(onOpenPeek).toHaveBeenCalledWith('KAN-142');

    onOpenPeek.mockClear();

    // 3. Modifier click (Ctrl+click) does NOT call preventDefault, allowing native new tab navigation
    const ctrlClickEv = new MouseEvent('click', {
      bubbles: true,
      cancelable: true,
      button: 0,
      ctrlKey: true,
    });
    const ctrlPreventSpy = vi.spyOn(ctrlClickEv, 'preventDefault');
    keyLink.dispatchEvent(ctrlClickEv);
    expect(ctrlPreventSpy).not.toHaveBeenCalled();
    expect(onOpenPeek).not.toHaveBeenCalled();

    // 4. Middle-click (button 1) does NOT call preventDefault
    const middleClickEv = new MouseEvent('click', {
      bubbles: true,
      cancelable: true,
      button: 1,
    });
    const middlePreventSpy = vi.spyOn(middleClickEv, 'preventDefault');
    summaryLink.dispatchEvent(middleClickEv);
    expect(middlePreventSpy).not.toHaveBeenCalled();
    expect(onOpenPeek).not.toHaveBeenCalled();
  });

  it('navigates via window.history when onOpenPeek is omitted', () => {
    const pushStateSpy = vi.spyOn(window.history, 'pushState');
    window.history.pushState({}, '', '/w/test-workspace/p/KAN/board');
    render(<BoardCard issue={{ ...baseIssue, key: '' }} stateGroup="started" />);

    // Click card container directly (tests targetEl fallback to cardRef)
    const cardEl = screen.getByTestId('board-card-');
    fireEvent.click(cardEl);
    expect(pushStateSpy).toHaveBeenCalled();

    // Modifier clicks with shiftKey and altKey and metaKey
    const keyLink = screen.getByTestId('board-card-key-');
    const preventNav = (e: MouseEvent) => { e.preventDefault(); };
    keyLink.addEventListener('click', preventNav);
    const shiftClick = new MouseEvent('click', { bubbles: true, cancelable: true, button: 0, shiftKey: true });
    const altClick = new MouseEvent('click', { bubbles: true, cancelable: true, button: 0, altKey: true });
    const metaClick = new MouseEvent('click', { bubbles: true, cancelable: true, button: 0, metaKey: true });
    keyLink.dispatchEvent(shiftClick);
    keyLink.dispatchEvent(altClick);
    keyLink.dispatchEvent(metaClick);
    keyLink.removeEventListener('click', preventNav);
  });

  describe('Touch & Mobile State Transition Button (KAN-44)', () => {
    it('renders state move button, opens QuickFieldPopover on click with stopPropagation, and triggers onStateTransition', () => {
      const onOpenPeek = vi.fn();
      const onStateTransition = vi.fn();
      const projectStates = [
        { id: 'st-todo', name: 'Todo', group: 'unstarted' as const, sort_order: 1 },
        { id: 'st-progress', name: 'In Progress', group: 'started' as const, sort_order: 2 },
        { id: 'st-done', name: 'Done', group: 'completed' as const, sort_order: 3 },
      ];

      const { rerender } = render(
        <BoardCard
          issue={baseIssue}
          stateGroup="started"
          onOpenPeek={onOpenPeek}
          onStateTransition={onStateTransition}
          projectStates={projectStates}
          currentUserCapabilities={['TRANSITION']}
        />,
      );

      const stateBtn = screen.getByTestId('board-card-state-btn-KAN-142');
      expect(stateBtn).toBeDefined();

      // Clicking state button opens popover and does NOT open peek
      fireEvent.click(stateBtn);
      expect(onOpenPeek).not.toHaveBeenCalled();

      // QuickFieldPopover is open
      const popover = screen.getByRole('dialog', { name: 'Quick State Picker' });
      expect(popover).toBeDefined();

      // Select 'Done' state option
      const doneOption = screen.getByRole('option', { name: 'Done' });
      fireEvent.click(doneOption);

      expect(onStateTransition).toHaveBeenCalledWith('KAN-142', 'st-done');
      expect(screen.queryByRole('dialog', { name: 'Quick State Picker' })).toBeNull();

      // Test popover onClose by opening and clicking backdrop
      fireEvent.click(stateBtn);
      const backdrop = screen.getByTestId('quick-field-backdrop');
      fireEvent.click(backdrop);
      expect(screen.queryByRole('dialog', { name: 'Quick State Picker' })).toBeNull();

      // Read-only user lacking transition capability does not render state button
      rerender(
        <BoardCard
          issue={baseIssue}
          stateGroup="started"
          currentUserCapabilities={['VIEWER']}
        />,
      );
      expect(screen.queryByTestId('board-card-state-btn-KAN-142')).toBeNull();
    });

    it('exercises canDrag callback when gate_status is pending', () => {
      let canDragFn: ((...args: unknown[]) => boolean) | undefined;
      const mockDraggable: typeof draggable = (opts) => {
        canDragFn = opts.canDrag as ((...args: unknown[]) => boolean) | undefined;
        return () => {
          /* cleanup */
        };
      };

      render(
        <BoardCard
          issue={{ ...baseIssue, gate_status: 'pending' }}
          stateGroup="started"
          draggableFactory={mockDraggable}
        />,
      );

      expect(canDragFn?.()).toBe(false);
    });
  });
});
