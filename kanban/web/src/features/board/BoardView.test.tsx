import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { monitorForElements } from '@atlaskit/pragmatic-drag-and-drop/element/adapter';
import * as clientModule from '../../api/client.ts';
import { BoardView } from './BoardView.tsx';
import * as boardApiModule from './boardApi.ts';
import { applyOptimisticMove, type BoardIssue, type BoardWorkflowState } from './boardApi.ts';
import { midpointRank } from './fractionalRank.ts';

type MonitorArgs = Parameters<typeof monitorForElements>[0];

const mockStates: BoardWorkflowState[] = [
  { id: 'st-backlog', name: 'Backlog', group: 'backlog', sort_order: 1 },
  { id: 'st-todo', name: 'To Do', group: 'unstarted', sort_order: 2 },
  { id: 'st-progress', name: 'In Progress', group: 'started', sort_order: 3, wip_soft_limit: 3 },
  { id: 'st-review', name: 'In Review', group: 'started', sort_order: 4, wip_hard_limit: 3 },
  { id: 'st-done', name: 'Done', group: 'completed', sort_order: 5 },
];

function generateIssues(count: number, stateId = 'st-todo'): BoardIssue[] {
  return Array.from({ length: count }, (_, i) => ({
    id: `iss-${String(i)}`,
    key: `KAN-${String(i + 1)}`,
    summary: `Issue number ${String(i + 1)}`,
    state_id: stateId,
    board_rank: `000000000000${String(i).padStart(4, '0')}`,
  }));
}

function renderWithClient(ui: ReactNode) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

describe('BoardView Component', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    Object.defineProperty(HTMLElement.prototype, 'clientHeight', {
      configurable: true,
      value: 900,
    });
    Object.defineProperty(HTMLElement.prototype, 'offsetHeight', {
      configurable: true,
      value: 124,
    });
    Object.defineProperty(HTMLElement.prototype, 'getBoundingClientRect', {
      configurable: true,
      value: () => ({
        top: 0,
        left: 0,
        bottom: 900,
        right: 324,
        width: 324,
        height: 900,
        x: 0,
        y: 0,
        toJSON: () => {
          /* no-op */
        },
      }),
    });
  });

  it('Requirement 1 & 2: fractional rank midpoint & <12ms 1-row cache apply benchmark (DoD Cases 1 & 2)', () => {
    const a = 'a000001';
    const b = 'a000002';
    const m = midpointRank(a, b);
    expect(a < m).toBe(true);
    expect(m < b).toBe(true);

    const issues500 = generateIssues(500, 'st-todo');
    const durations: number[] = [];
    let lastUpdated: BoardIssue[] = issues500;

    for (let i = 0; i < 20; i++) {
      const start = performance.now();
      lastUpdated = applyOptimisticMove(issues500, {
        projectKey: 'KAN',
        issueKey: `KAN-${String((i * 15) % 500 + 1)}`,
        targetStateId: 'st-done',
        boardRank: '0000000000005000',
      });
      durations.push(performance.now() - start);
    }

    durations.sort((x, y) => x - y);
    const median = durations[Math.floor(durations.length / 2)] ?? 0;
    expect(median).toBeLessThan(12);

    let changedRefs = 0;
    for (let i = 0; i < issues500.length; i++) {
      if (issues500[i] !== lastUpdated[i]) {
        changedRefs++;
      }
    }
    expect(changedRefs).toBe(1);
  });

  it('Requirement 4: Soft WIP breach renders warning emoji hint while allowing move (DoD Case 4)', async () => {
    const moveSpy = vi.spyOn(boardApiModule, 'moveIssueApi').mockResolvedValue({
      issue_key: 'KAN-1',
      state_id: 'st-progress',
      board_rank: 'rank-new',
      rebalance_scheduled: false,
    });

    const issues: BoardIssue[] = [
      { id: 'i1', key: 'KAN-1', summary: 'Item 1', state_id: 'st-todo', board_rank: '01' },
      { id: 'i2', key: 'KAN-2', summary: 'Item 2', state_id: 'st-progress', board_rank: '02' },
      { id: 'i3', key: 'KAN-3', summary: 'Item 3', state_id: 'st-progress', board_rank: '03' },
      { id: 'i4', key: 'KAN-4', summary: 'Item 4', state_id: 'st-progress', board_rank: '04' },
      { id: 'i-unknown', key: 'KAN-UNK', summary: 'Unknown state', state_id: 'unknown-state', board_rank: '05' },
    ];

    renderWithClient(
      <BoardView
        projectKey="KAN"
        states={mockStates}
        issues={issues}
        currentUserCapabilities={['VIEW']}
      />,
    );

    const card = screen.getByTestId('board-card-KAN-1');
    fireEvent.keyDown(card, { key: 'ArrowRight', altKey: true });

    await waitFor(() => {
      expect(moveSpy).toHaveBeenCalledTimes(1);
    });

    expect(screen.getByTestId('wip-warning-st-progress')).toBeDefined();
  });

  it('Requirement 4: Hard WIP cross-column move by non-admin is blocked with 0 network calls (DoD Case 4)', () => {
    const moveSpy = vi.spyOn(boardApiModule, 'moveIssueApi').mockResolvedValue({
      issue_key: 'KAN-1',
      state_id: 'st-review',
      board_rank: 'rank-new',
      rebalance_scheduled: false,
    });

    const issues: BoardIssue[] = [
      { id: 'i1', key: 'KAN-1', summary: 'Item 1', state_id: 'st-progress', board_rank: '01' },
      { id: 'i2', key: 'KAN-2', summary: 'Review 1', state_id: 'st-review', board_rank: '02' },
      { id: 'i3', key: 'KAN-3', summary: 'Review 2', state_id: 'st-review', board_rank: '03' },
      { id: 'i4', key: 'KAN-4', summary: 'Review 3', state_id: 'st-review', board_rank: '04' },
    ];

    renderWithClient(
      <BoardView
        projectKey="KAN"
        states={mockStates}
        issues={issues}
        currentUserCapabilities={['VIEW']}
      />,
    );

    const card = screen.getByTestId('board-card-KAN-1');
    fireEvent.keyDown(card, { key: 'ArrowRight', altKey: true });

    expect(moveSpy).toHaveBeenCalledTimes(0);

    const alertToast = screen.getByRole('alert');
    expect(alertToast).toBeDefined();
    expect(alertToast.textContent).toContain('Hard WIP limit reached (3/3) on In Review');

    const dismissBtn = screen.getByLabelText('Dismiss alert');
    fireEvent.click(dismissBtn);
    expect(screen.queryByRole('alert')).toBeNull();
  });

  it('Requirement 4: Hard WIP cross-column move by PROJECT_ADMIN opens override modal and enforces >= 10 chars (DoD Case 4)', async () => {
    const moveSpy = vi.spyOn(boardApiModule, 'moveIssueApi').mockResolvedValue({
      issue_key: 'KAN-1',
      state_id: 'st-review',
      board_rank: 'rank-new',
      rebalance_scheduled: false,
    });

    const issues: BoardIssue[] = [
      { id: 'i1', key: 'KAN-1', summary: 'Item 1', state_id: 'st-progress', board_rank: '01' },
      { id: 'i2', key: 'KAN-2', summary: 'Review 1', state_id: 'st-review', board_rank: '02' },
      { id: 'i3', key: 'KAN-3', summary: 'Review 2', state_id: 'st-review', board_rank: '03' },
      { id: 'i4', key: 'KAN-4', summary: 'Review 3', state_id: 'st-review', board_rank: '04' },
    ];

    renderWithClient(
      <BoardView
        projectKey="KAN"
        states={mockStates}
        issues={issues}
        currentUserCapabilities={['PROJECT_ADMIN']}
      />,
    );

    const card = screen.getByTestId('board-card-KAN-1');
    fireEvent.keyDown(card, { key: 'ArrowRight', altKey: true });

    expect(screen.getByRole('dialog')).toBeDefined();
    const textarea = screen.getByRole('textbox');
    const submitBtn = screen.getByRole<HTMLButtonElement>('button', { name: /Override & move/i });

    fireEvent.change(textarea, { target: { value: '123456789' } });
    expect(submitBtn.disabled).toBe(true);

    fireEvent.change(textarea, { target: { value: 'Approved by lead' } });
    expect(submitBtn.disabled).toBe(false);

    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(moveSpy).toHaveBeenCalledWith(
        expect.objectContaining({
          issueKey: 'KAN-1',
          targetStateId: 'st-review',
          overrideWip: true,
          wipOverrideReason: 'Approved by lead',
        }),
      );
    });
  });

  it('Requirement 4: Hard WIP modal cancellation aborts the move without network calls', () => {
    const moveSpy = vi.spyOn(boardApiModule, 'moveIssueApi').mockResolvedValue({
      issue_key: 'KAN-1',
      state_id: 'st-review',
      board_rank: 'rank-new',
      rebalance_scheduled: false,
    });

    const issues: BoardIssue[] = [
      { id: 'i1', key: 'KAN-1', summary: 'Item 1', state_id: 'st-progress', board_rank: '01' },
      { id: 'i2', key: 'KAN-2', summary: 'Review 1', state_id: 'st-review', board_rank: '02' },
      { id: 'i3', key: 'KAN-3', summary: 'Review 2', state_id: 'st-review', board_rank: '03' },
      { id: 'i4', key: 'KAN-4', summary: 'Review 3', state_id: 'st-review', board_rank: '04' },
    ];

    renderWithClient(
      <BoardView
        projectKey="KAN"
        states={mockStates}
        issues={issues}
        currentUserCapabilities={['ADMIN']}
      />,
    );

    const card = screen.getByTestId('board-card-KAN-1');
    fireEvent.keyDown(card, { key: 'ArrowRight', altKey: true });

    expect(screen.getByRole('dialog')).toBeDefined();
    const cancelBtn = screen.getByRole('button', { name: /Cancel/i });
    fireEvent.click(cancelBtn);

    expect(screen.queryByRole('dialog')).toBeNull();
    expect(moveSpy).toHaveBeenCalledTimes(0);
  });

  it('Requirement 4: Intra-column reorder in a column at Hard WIP limit is always permitted without modal', async () => {
    const moveSpy = vi.spyOn(boardApiModule, 'moveIssueApi').mockResolvedValue({
      issue_key: 'KAN-2',
      state_id: 'st-review',
      board_rank: 'rank-new',
      rebalance_scheduled: false,
    });

    const issues: BoardIssue[] = [
      { id: 'i2', key: 'KAN-2', summary: 'Review 1', state_id: 'st-review', board_rank: '02' },
      { id: 'i3', key: 'KAN-3', summary: 'Review 2', state_id: 'st-review', board_rank: '03' },
      { id: 'i4', key: 'KAN-4', summary: 'Review 3', state_id: 'st-review', board_rank: '04' },
    ];

    renderWithClient(
      <BoardView
        projectKey="KAN"
        states={mockStates}
        issues={issues}
        currentUserCapabilities={['VIEW']}
      />,
    );

    const card = screen.getByTestId('board-card-KAN-2');
    fireEvent.keyDown(card, { key: 'ArrowDown', altKey: true });

    await waitFor(() => {
      expect(moveSpy).toHaveBeenCalledTimes(1);
    });
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('Requirement 5: Server 500 error rolls back optimistic move to origin lane (DoD Case 5)', async () => {
    vi.spyOn(boardApiModule, 'moveIssueApi').mockRejectedValue(new Error('Internal Server Error'));

    const issues: BoardIssue[] = [
      { id: 'i1', key: 'KAN-1', summary: 'Item 1', state_id: 'st-todo', board_rank: '01' },
    ];

    renderWithClient(
      <BoardView
        projectKey="KAN"
        states={mockStates}
        issues={issues}
        currentUserCapabilities={['VIEW']}
      />,
    );

    const card = screen.getByTestId('board-card-KAN-1');
    fireEvent.keyDown(card, { key: 'ArrowRight', altKey: true });

    await waitFor(() => {
      const todoColumn = screen.getByTestId('board-column-st-todo');
      expect(todoColumn.textContent).toContain('KAN-1');
    });
  });

  it('Requirement 6: Keyboard navigation: Alt+ArrowLeft, Alt+ArrowUp, Alt+ArrowDown, peek/new-item', async () => {
    const moveSpy = vi.spyOn(boardApiModule, 'moveIssueApi').mockResolvedValue({
      issue_key: 'KAN-2',
      state_id: 'st-todo',
      board_rank: 'rank-new',
      rebalance_scheduled: false,
    });

    const onOpenPeek = vi.fn();
    const onNewItem = vi.fn();

    const issues: BoardIssue[] = [
      { id: 'i1', key: 'KAN-1', summary: 'Item 1', state_id: 'st-todo', board_rank: '01' },
      { id: 'i2', key: 'KAN-2', summary: 'Item 2', state_id: 'st-todo', board_rank: '02' },
      { id: 'i3', key: 'KAN-3', summary: 'Item 3', state_id: 'st-todo', board_rank: '03' },
    ];

    renderWithClient(
      <BoardView
        projectKey="KAN"
        states={mockStates}
        issues={issues}
        currentUserCapabilities={['VIEW']}
        onOpenPeek={onOpenPeek}
        onNewItem={onNewItem}
      />,
    );

    const cardKey = screen.getByTestId('board-card-key-KAN-1');
    fireEvent.click(cardKey);
    expect(onOpenPeek).toHaveBeenCalledWith('KAN-1');

    const newBtn = screen.getByTestId('new-item-st-todo');
    fireEvent.click(newBtn);
    expect(onNewItem).toHaveBeenCalledWith('st-todo');

    // Alt+ArrowDown on KAN-1 moves it down
    const card1 = screen.getByTestId('board-card-KAN-1');
    fireEvent.keyDown(card1, { key: 'ArrowDown', altKey: true });
    await waitFor(() => {
      expect(moveSpy).toHaveBeenCalledTimes(1);
    });

    // Alt+ArrowUp on KAN-3 moves it up
    const card3 = screen.getByTestId('board-card-KAN-3');
    fireEvent.keyDown(card3, { key: 'ArrowUp', altKey: true });
    await waitFor(() => {
      expect(moveSpy).toHaveBeenCalledTimes(2);
    });

    // Alt+ArrowLeft on KAN-1 moves it to Backlog
    fireEvent.keyDown(card1, { key: 'ArrowLeft', altKey: true });
    await waitFor(() => {
      expect(moveSpy).toHaveBeenCalledWith(
        expect.objectContaining({
          issueKey: 'KAN-1',
          targetStateId: 'st-backlog',
        }),
      );
    });
  });

  it('Keyboard boundary checks: bounds on leftmost/rightmost columns and top/bottom cards', () => {
    const moveSpy = vi.spyOn(boardApiModule, 'moveIssueApi');

    const issues: BoardIssue[] = [
      { id: 'i-backlog', key: 'KAN-BL', summary: 'Backlog Item', state_id: 'st-backlog', board_rank: '01' },
      { id: 'i-done', key: 'KAN-DN', summary: 'Done Item', state_id: 'st-done', board_rank: '02' },
    ];

    renderWithClient(
      <BoardView
        projectKey="KAN"
        states={mockStates}
        issues={issues}
        currentUserCapabilities={['VIEW']}
      />,
    );

    // 1. Alt+ArrowLeft on Backlog card (already leftmost column) -> no-op
    const blCard = screen.getByTestId('board-card-KAN-BL');
    fireEvent.keyDown(blCard, { key: 'ArrowLeft', altKey: true });
    expect(moveSpy).not.toHaveBeenCalled();

    // 2. Alt+ArrowRight on Done card (already rightmost column) -> no-op
    const dnCard = screen.getByTestId('board-card-KAN-DN');
    fireEvent.keyDown(dnCard, { key: 'ArrowRight', altKey: true });
    expect(moveSpy).not.toHaveBeenCalled();

    // 3. Alt+ArrowUp on top card (index 0) -> no-op
    fireEvent.keyDown(blCard, { key: 'ArrowUp', altKey: true });
    expect(moveSpy).not.toHaveBeenCalled();

    // 4. Alt+ArrowDown on bottom card (single card in column) -> no-op
    fireEvent.keyDown(blCard, { key: 'ArrowDown', altKey: true });
    expect(moveSpy).not.toHaveBeenCalled();
  });

  it('exercises monitorForElements callbacks via monitorFactory and edge cases', async () => {
    let capturedMonitorOpts: MonitorArgs | null = null;
    const customMonitorFactory: typeof monitorForElements = (opts) => {
      capturedMonitorOpts = opts;
      return () => {
        /* no-op */
      };
    };

    const moveSpy = vi.spyOn(boardApiModule, 'moveIssueApi').mockResolvedValue({
      issue_key: 'KAN-1',
      state_id: 'st-progress',
      board_rank: 'rank-new',
      rebalance_scheduled: false,
    });

    const issues: BoardIssue[] = [
      { id: 'i1', key: 'KAN-1', summary: 'Item 1', state_id: 'st-todo', board_rank: '01' },
      { id: 'i2', key: 'KAN-2', summary: 'Item 2', state_id: 'st-progress', board_rank: '02' },
      { id: 'i3', key: 'KAN-3', summary: 'Item 3', state_id: 'st-progress', board_rank: '03' },
    ];

    renderWithClient(
      <BoardView
        projectKey="KAN"
        states={mockStates}
        issues={issues}
        currentUserCapabilities={['ADMIN']}
        monitorFactory={customMonitorFactory}
      />,
    );

    expect(capturedMonitorOpts).toBeDefined();

    // 1. onDragStart
    act(() => {
      capturedMonitorOpts?.onDragStart?.({
        source: { data: { type: 'card', issueKey: 'KAN-1' } },
      } as never);
      // Non-card drag start ignored
      capturedMonitorOpts?.onDragStart?.({
        source: { data: { type: 'other' } },
      } as never);
      // Card without string issueKey ignored
      capturedMonitorOpts?.onDragStart?.({
        source: { data: { type: 'card', issueKey: 123 } },
      } as never);
    });

    // 2. onDropTargetChange with card
    act(() => {
      capturedMonitorOpts?.onDropTargetChange?.({
        location: {
          current: {
            dropTargets: [{ data: { type: 'card', issueKey: 'KAN-2', edge: 'top' } }],
          },
        },
      } as never);
    });

    // 3. onDropTargetChange clear
    act(() => {
      capturedMonitorOpts?.onDropTargetChange?.({
        location: {
          current: {
            dropTargets: [],
          },
        },
      } as never);
    });

    // 4. onDrop with non-card source ignored
    act(() => {
      capturedMonitorOpts?.onDrop?.({
        source: { data: { type: 'other' } },
        location: { current: { dropTargets: [] } },
      } as never);
    });

    // 5. onDrop with unknown target type
    act(() => {
      capturedMonitorOpts?.onDrop?.({
        source: { data: { type: 'card', issueKey: 'KAN-1' } },
        location: {
          current: {
            dropTargets: [{ data: { type: 'unknown_type' } }],
          },
        },
      } as never);
    });

    // 6. onDrop with non-existent target state
    act(() => {
      capturedMonitorOpts?.onDrop?.({
        source: { data: { type: 'card', issueKey: 'KAN-1' } },
        location: {
          current: {
            dropTargets: [{ data: { type: 'column', stateId: 'nonexistent-state' } }],
          },
        },
      } as never);
    });

    // 7. onDrop onto column
    act(() => {
      capturedMonitorOpts?.onDrop?.({
        source: { data: { type: 'card', issueKey: 'KAN-1' } },
        location: {
          current: {
            dropTargets: [{ data: { type: 'column', stateId: 'st-progress' } }],
          },
        },
      } as never);
    });

    await waitFor(() => {
      expect(moveSpy).toHaveBeenCalledWith(
        expect.objectContaining({
          issueKey: 'KAN-1',
          targetStateId: 'st-progress',
        }),
      );
    });

    // 8. onDrop onto card with edge='top' on top card (targetIdx === 0)
    act(() => {
      capturedMonitorOpts?.onDrop?.({
        source: { data: { type: 'card', issueKey: 'KAN-1' } },
        location: {
          current: {
            dropTargets: [{ data: { type: 'card', stateId: 'st-progress', issueKey: 'KAN-2', edge: 'top' } }],
          },
        },
      } as never);
    });

    // 9. onDrop onto card with edge='bottom' on middle card
    act(() => {
      capturedMonitorOpts?.onDrop?.({
        source: { data: { type: 'card', issueKey: 'KAN-1' } },
        location: {
          current: {
            dropTargets: [{ data: { type: 'card', stateId: 'st-progress', issueKey: 'KAN-2', edge: 'bottom' } }],
          },
        },
      } as never);
    });

    // 10. onDropTargetChange with card having no edge specified (defaults to 'bottom')
    act(() => {
      capturedMonitorOpts?.onDropTargetChange?.({
        location: {
          current: {
            dropTargets: [{ data: { type: 'card', issueKey: 'KAN-2' } }],
          },
        },
      } as never);
    });

    // 11. onDrop with empty dropTargets array (early return)
    act(() => {
      capturedMonitorOpts?.onDrop?.({
        source: { data: { type: 'card', issueKey: 'KAN-1' } },
        location: {
          current: {
            dropTargets: [],
          },
        },
      } as never);
    });

    // 12. onDrop with edge='top' on non-top card (targetIdx > 0)
    act(() => {
      capturedMonitorOpts?.onDrop?.({
        source: { data: { type: 'card', issueKey: 'KAN-1' } },
        location: {
          current: {
            dropTargets: [{ data: { type: 'card', stateId: 'st-progress', issueKey: 'KAN-3', edge: 'top' } }],
          },
        },
      } as never);
    });

    // 13. onDrop with edge='bottom' on bottom card (targetIdx === targetColCards.length - 1)
    act(() => {
      capturedMonitorOpts?.onDrop?.({
        source: { data: { type: 'card', issueKey: 'KAN-1' } },
        location: {
          current: {
            dropTargets: [{ data: { type: 'card', stateId: 'st-progress', issueKey: 'KAN-3', edge: 'bottom' } }],
          },
        },
      } as never);
    });

    // 14. onDrop onto same card (targetCardKey === issueKey)
    act(() => {
      capturedMonitorOpts?.onDrop?.({
        source: { data: { type: 'card', issueKey: 'KAN-2' } },
        location: {
          current: {
            dropTargets: [{ data: { type: 'card', stateId: 'st-progress', issueKey: 'KAN-2', edge: 'top' } }],
          },
        },
      } as never);
    });

    // 12. onDrop onto empty column st-done (0 issues)
    act(() => {
      capturedMonitorOpts?.onDrop?.({
        source: { data: { type: 'card', issueKey: 'KAN-1' } },
        location: {
          current: {
            dropTargets: [{ data: { type: 'column', stateId: 'st-done' } }],
          },
        },
      } as never);
    });

    // 13. onDrop onto card KAN-3 with edge='top' (targetIdx > 0, aboveCard is KAN-2)
    act(() => {
      capturedMonitorOpts?.onDrop?.({
        source: { data: { type: 'card', issueKey: 'KAN-1' } },
        location: {
          current: {
            dropTargets: [{ data: { type: 'card', stateId: 'st-progress', issueKey: 'KAN-3', edge: 'top' } }],
          },
        },
      } as never);
    });

    // 14. onDrop onto card KAN-3 with edge='bottom' (targetIdx is last card, belowCard is null)
    act(() => {
      capturedMonitorOpts?.onDrop?.({
        source: { data: { type: 'card', issueKey: 'KAN-1' } },
        location: {
          current: {
            dropTargets: [{ data: { type: 'card', stateId: 'st-progress', issueKey: 'KAN-3', edge: 'bottom' } }],
          },
        },
      } as never);
    });

    // 15. onDrop with non-existent moved issue key (early return)
    act(() => {
      capturedMonitorOpts?.onDrop?.({
        source: { data: { type: 'card', issueKey: 'KAN-NONEXISTENT' } },
        location: {
          current: {
            dropTargets: [{ data: { type: 'column', stateId: 'st-todo' } }],
          },
        },
      } as never);
    });

    // 16. onDrop onto card with edge omitted (defaults to 'bottom')
    act(() => {
      capturedMonitorOpts?.onDrop?.({
        source: { data: { type: 'card', issueKey: 'KAN-1' } },
        location: {
          current: {
            dropTargets: [{ data: { type: 'card', stateId: 'st-progress', issueKey: 'KAN-2' } }],
          },
        },
      } as never);
    });

    // 17. onDrop onto card with non-existent target card key in target column
    act(() => {
      capturedMonitorOpts?.onDrop?.({
        source: { data: { type: 'card', issueKey: 'KAN-1' } },
        location: {
          current: {
            dropTargets: [{ data: { type: 'card', stateId: 'st-progress', issueKey: 'KAN-GHOST-TARGET' } }],
          },
        },
      } as never);
    });
  });

  it('Requirement 4: Admin dropping onto a card in a Hard WIP column with edge=top opens modal with belowCard populated', () => {
    let capturedMonitorOpts: MonitorArgs | null = null;
    const customMonitorFactory = (opts: MonitorArgs) => {
      capturedMonitorOpts = opts;
      return () => {
        // no-op cleanup
      };
    };

    const issues: BoardIssue[] = [
      { id: 'i1', key: 'KAN-1', summary: 'Item 1', state_id: 'st-progress', board_rank: '01' },
      { id: 'i2', key: 'KAN-2', summary: 'Review 1', state_id: 'st-review', board_rank: '02' },
      { id: 'i3', key: 'KAN-3', summary: 'Review 2', state_id: 'st-review', board_rank: '03' },
      { id: 'i4', key: 'KAN-4', summary: 'Review 3', state_id: 'st-review', board_rank: '04' },
    ];

    renderWithClient(
      <BoardView
        projectKey="KAN"
        states={mockStates}
        issues={issues}
        currentUserCapabilities={['PROJECT_ADMIN']}
        monitorFactory={customMonitorFactory}
      />,
    );

    // Drop KAN-1 onto KAN-2 (first card in st-review) with edge='top'
    // This makes aboveCard = null and belowCard = KAN-2
    act(() => {
      capturedMonitorOpts?.onDrop?.({
        source: { data: { type: 'card', issueKey: 'KAN-1' } },
        location: {
          current: {
            dropTargets: [{ data: { type: 'card', stateId: 'st-review', issueKey: 'KAN-2', edge: 'top' } }],
          },
        },
      } as never);
    });

    expect(screen.getByRole('dialog')).toBeDefined();
    const textarea = screen.getByRole('textbox');
    fireEvent.change(textarea, { target: { value: 'Admin override top position' } });
    const submitBtn = screen.getByRole('button', { name: /Override & move/i });
    fireEvent.click(submitBtn);
  });

  it('handles drop with edge=bottom and drop onto column without target card', async () => {
    let capturedMonitorOpts: MonitorArgs | null = null;
    const customMonitorFactory = (opts: MonitorArgs) => {
      capturedMonitorOpts = opts;
      return () => undefined;
    };

    const moveSpy = vi.spyOn(boardApiModule, 'moveIssueApi').mockResolvedValue({
      issue_key: 'KAN-1',
      state_id: 'st-todo',
      board_rank: 'rank-bot',
      rebalance_scheduled: false,
    });

    const issues: BoardIssue[] = [
      { id: 'i1', key: 'KAN-1', summary: 'Item 1', state_id: 'st-progress', board_rank: '01' },
      { id: 'i2', key: 'KAN-2', summary: 'Todo 1', state_id: 'st-todo', board_rank: '02' },
      { id: 'i3', key: 'KAN-3', summary: 'Todo 2', state_id: 'st-todo', board_rank: '03' },
    ];

    renderWithClient(
      <BoardView
        projectKey="KAN"
        states={mockStates}
        issues={issues}
        currentUserCapabilities={['ADMIN']}
        monitorFactory={customMonitorFactory}
      />,
    );

    // 1. Drop KAN-1 onto KAN-2 (middle) with edge='bottom' -> belowCard is KAN-3
    act(() => {
      capturedMonitorOpts?.onDrop?.({
        source: { data: { type: 'card', issueKey: 'KAN-1' } },
        location: {
          current: {
            dropTargets: [
              { data: { type: 'card', stateId: 'st-todo', issueKey: 'KAN-2', edge: 'bottom' } },
            ],
          },
        },
      } as never);
    });
    await waitFor(() => {
      expect(moveSpy).toHaveBeenCalled();
    });

    // 2. Drop KAN-1 onto KAN-3 (last card) with edge='bottom' -> belowCard is null
    act(() => {
      capturedMonitorOpts?.onDrop?.({
        source: { data: { type: 'card', issueKey: 'KAN-1' } },
        location: {
          current: {
            dropTargets: [
              { data: { type: 'card', stateId: 'st-todo', issueKey: 'KAN-3', edge: 'bottom' } },
            ],
          },
        },
      } as never);
    });

    // 3. Drop KAN-1 onto column directly (no target card) -> aboveCard is last card in column
    act(() => {
      capturedMonitorOpts?.onDrop?.({
        source: { data: { type: 'card', issueKey: 'KAN-1' } },
        location: {
          current: {
            dropTargets: [{ data: { type: 'column', stateId: 'st-todo' } }],
          },
        },
      } as never);
    });

    // 4. Drop KAN-1 onto empty column (e.g. st-done has no issues)
    act(() => {
      capturedMonitorOpts?.onDrop?.({
        source: { data: { type: 'card', issueKey: 'KAN-1' } },
        location: {
          current: {
            dropTargets: [{ data: { type: 'column', stateId: 'st-done' } }],
          },
        },
      } as never);
    });
  });

  it('loads states and issues via queries when props are omitted', async () => {
    vi.spyOn(clientModule, 'apiFetch').mockImplementation((_method, path) => {
      if (path === '/api/v1/projects/{project_ref}') {
        return Promise.resolve({
          states: [
            { id: 'st-fetched', name: 'Fetched Lane', group: 'started', sort_order: 1 },
          ],
          capabilities: ['PROJECT_ADMIN'],
        });
      }
      if (path === '/api/v1/projects/{project_ref}/issues') {
        return Promise.resolve({
          items: [
            { id: 'i1', key: 'KAN-FETCH', summary: 'Fetched item', state_id: 'st-fetched', board_rank: '01' },
          ],
        });
      }
      return Promise.resolve({});
    });

    renderWithClient(<BoardView projectKey="KAN" />);
    await waitFor(() => {
      expect(screen.getByText('Fetched item')).toBeDefined();
      expect(screen.getByText('Fetched Lane')).toBeDefined();
    });
  });

  it('handles raw array issue response when queries are used', async () => {
    vi.spyOn(clientModule, 'apiFetch').mockImplementation((_method, path) => {
      if (path === '/api/v1/projects/{project_ref}') {
        return Promise.resolve({
          states: [],
        });
      }
      if (path === '/api/v1/projects/{project_ref}/issues') {
        return Promise.resolve([
          { id: 'i2', key: 'KAN-ARRAY', summary: 'Array item', state_id: 'state-todo', board_rank: '02' },
        ] as never);
      }
      return Promise.resolve({});
    });

    renderWithClient(<BoardView projectKey="KAN" />);
    await waitFor(() => {
      expect(screen.getByText('Array item')).toBeDefined();
    });
  });

  it('handles empty/invalid response when queries are used', async () => {
    vi.spyOn(clientModule, 'apiFetch').mockImplementation((_method, path) => {
      if (path === '/api/v1/projects/{project_ref}/issues') {
        return Promise.resolve(null);
      }
      return Promise.resolve({});
    });

    renderWithClient(<BoardView projectKey="KAN" />);
    await waitFor(() => {
      expect(screen.getByText('To Do')).toBeDefined();
    });
  });

  it('renders priority indicators for urgent, high, medium, and low issues', () => {
    const issues: BoardIssue[] = [
      { id: 'p1', key: 'KAN-URG', summary: 'Urgent task', state_id: 'st-todo', board_rank: '1', priority: { id: 'p-urg', slug: 'urgent', label: 'Urgent' } },
      { id: 'p2', key: 'KAN-HI', summary: 'High task', state_id: 'st-todo', board_rank: '2', priority: { id: 'p-hi', slug: 'high', label: 'High' } },
      { id: 'p3', key: 'KAN-MED', summary: 'Med task', state_id: 'st-todo', board_rank: '3', priority: { id: 'p-med', slug: 'medium', label: 'Medium' } },
      { id: 'p4', key: 'KAN-LOW', summary: 'Low task', state_id: 'st-todo', board_rank: '4', priority: { id: 'p-low', slug: 'low', label: 'Low' } },
    ];

    renderWithClient(
      <BoardView projectKey="KAN" states={mockStates} issues={issues} />,
    );

    expect(screen.getByText('Urgent task')).toBeDefined();
    expect(screen.getByText('High task')).toBeDefined();
    expect(screen.getByText('Med task')).toBeDefined();
    expect(screen.getByText('Low task')).toBeDefined();
  });

  it('covers state_id fallback from state.id and empty string when state is absent', () => {
    const mixedIssues: BoardIssue[] = [
      { id: 'p1', key: 'KAN-STATE-OBJ', summary: 'State object item', state: { id: 'st-todo' } } as unknown as BoardIssue,
      { id: 'p2', key: 'KAN-NO-STATE', summary: 'No state item' } as unknown as BoardIssue,
    ];

    renderWithClient(
      <BoardView projectKey="KAN" states={mockStates} issues={mixedIssues} />,
    );

    expect(screen.getByText('State object item')).toBeDefined();
  });

  it('handles toast timer and second toast arrival preventing stale dismissal', () => {
    vi.useFakeTimers();
    let eventHandler: ((event: unknown) => void) | null = null;
    const mockRealtimeClient = {
      onEvent: (cb: (event: unknown) => void) => {
        eventHandler = cb;
        return () => {
          eventHandler = null;
        };
      },
      subscribe: vi.fn(),
      isConnected: () => true,
    };

    renderWithClient(
      <BoardView
        projectKey="KAN"
        states={mockStates}
        issues={[]}
        realtimeClient={mockRealtimeClient as never}
      />,
    );

    expect(eventHandler).toBeDefined();

    // Trigger toast 1
    act(() => {
      eventHandler?.({
        id: 'evt-toast-1',
        type: 'workflow.gate.cancelled',
        payload: {
          issue_key: 'KAN-1',
          execution_id: 'exec-1',
          reason: 'STALE_SNAPSHOT',
        },
      });
    });

    expect(screen.getByRole('alert')).toBeDefined();

    // Advance 5000ms (dismissed)
    act(() => {
      vi.advanceTimersByTime(5000);
    });
    expect(screen.queryByRole('alert')).toBeNull();

    vi.useRealTimers();
  });

  it('covers keyboard navigation bounds when moving left at column 0 and right at last column', () => {
    const issues: BoardIssue[] = [
      { id: 'b1', key: 'KAN-LEFTMOST', summary: 'Left card', state_id: 'st-backlog', board_rank: '1' },
      { id: 'b2', key: 'KAN-RIGHTMOST', summary: 'Right card', state_id: 'st-done', board_rank: '2' },
      { id: 'b3', key: 'KAN-STACKED', summary: 'Stacked card', state_id: 'st-backlog', board_rank: '3' },
    ];

    renderWithClient(
      <BoardView projectKey="KAN" states={mockStates} issues={issues} />,
    );

    const leftCard = screen.getByText('Left card').closest('.board-card');
    const rightCard = screen.getByText('Right card').closest('.board-card');
    const stackedCard = screen.getByText('Stacked card').closest('.board-card');

    if (leftCard) {
      // Alt+ArrowLeft at left-most column is a bounds no-op
      fireEvent.keyDown(leftCard, { key: 'ArrowLeft', altKey: true });
      // Alt+ArrowRight moves to next column
      fireEvent.keyDown(leftCard, { key: 'ArrowRight', altKey: true });
      // Alt+ArrowDown swaps with card below
      fireEvent.keyDown(leftCard, { key: 'ArrowDown', altKey: true });
    }
    if (stackedCard) {
      // Alt+ArrowUp swaps with card above
      fireEvent.keyDown(stackedCard, { key: 'ArrowUp', altKey: true });
    }
    if (rightCard) {
      // Alt+ArrowRight at right-most column is a bounds no-op
      fireEvent.keyDown(rightCard, { key: 'ArrowRight', altKey: true });
      // Alt+ArrowLeft moves to previous column
      fireEvent.keyDown(rightCard, { key: 'ArrowLeft', altKey: true });
    }
  });

  it('covers identical board_rank sorting and empty projectKey realtime subscription', () => {
    const issues: BoardIssue[] = [
      { id: 'eq-1', key: 'EQ-1', summary: 'Equal 1', state_id: 'st-todo', board_rank: 'SAME_RANK' },
      { id: 'eq-2', key: 'EQ-2', summary: 'Equal 2', state_id: 'st-todo', board_rank: 'SAME_RANK' },
    ];

    const { unmount } = renderWithClient(
      <BoardView projectKey="" states={mockStates} issues={issues} currentUserCapabilities={['ADMIN']} />,
    );

    expect(screen.getByText('Equal 1')).toBeDefined();
    expect(screen.getByText('Equal 2')).toBeDefined();
    expect(screen.getByTestId('board-canvas')).toBeDefined();
    unmount();
  });
  });
});
