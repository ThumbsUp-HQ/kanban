import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { dropTargetForElements } from '@atlaskit/pragmatic-drag-and-drop/element/adapter';
import { BoardColumn, getColumnDropData } from './BoardColumn.tsx';
import type { BoardIssue, BoardWorkflowState } from './boardApi.ts';

const baseState: BoardWorkflowState = {
  id: 'state-started',
  name: 'In Progress',
  group: 'started',
  sort_order: 1,
};

function generateIssues(count: number): BoardIssue[] {
  return Array.from({ length: count }, (_, i) => ({
    id: `iss-${String(i)}`,
    key: `KAN-${String(i + 1)}`,
    summary: `Issue number ${String(i + 1)}`,
    state_id: 'state-started',
    board_rank: `rank-${String(i).padStart(6, '0')}`,
  }));
}

describe('BoardColumn Component', () => {
  beforeEach(() => {
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
      value: function () {
        return {
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
        };
      },
    });
  });

  it('renders header with glyph, state name, count, and footer button', () => {
    const issues = generateIssues(3);
    const onNewItem = vi.fn();

    const { unmount } = render(
      <BoardColumn state={baseState} issues={issues} onNewItem={onNewItem} />,
    );

    expect(screen.getByText('In Progress')).toBeDefined();
    expect(screen.getByText('◐')).toBeDefined();
    expect(screen.getByText('3')).toBeDefined();

    const newBtn = screen.getByTestId('new-item-state-started');
    expect(newBtn).toBeDefined();
    fireEvent.click(newBtn);
    expect(onNewItem).toHaveBeenCalledWith('state-started');

    unmount();
  });

  it('virtualization boundary: 250 issues in a 900px scroll container mounts <= 25 cards (DoD Case 3)', () => {
    const issues = generateIssues(250);

    const { container } = render(
      <div className="test-viewport">
        <BoardColumn state={baseState} issues={issues} />
      </div>,
    );

    const mountedCards = container.querySelectorAll('.board-card');
    expect(mountedCards.length).toBeGreaterThan(0);
    expect(mountedCards.length).toBeLessThanOrEqual(25);
  });

  it('renders Soft WIP warning and amber styling when count exceeds soft limit', () => {
    const softLimitState: BoardWorkflowState = {
      ...baseState,
      wip_soft_limit: 3,
    };
    const issues = generateIssues(4);

    const { container } = render(<BoardColumn state={softLimitState} issues={issues} />);

    expect(container.querySelector('.board-column--warn')).toBeDefined();
    expect(screen.getByText('(WIP 3)')).toBeDefined();
    expect(screen.getByTestId('wip-warning-state-started')).toBeDefined();
  });

  it('renders Hard WIP warning when count reaches or exceeds hard limit', () => {
    const hardLimitState: BoardWorkflowState = {
      ...baseState,
      wip_hard_limit: 3,
    };
    const issues = generateIssues(3);

    const { container } = render(<BoardColumn state={hardLimitState} issues={issues} />);

    expect(container.querySelector('.board-column--warn')).toBeDefined();
    expect(screen.getByText('(WIP 3)')).toBeDefined();
    expect(screen.getByTestId('wip-warning-state-started')).toBeDefined();
  });

  it('renders WIP badge without warn class when soft or hard limits are not exceeded', () => {
    const softLimitState: BoardWorkflowState = {
      ...baseState,
      wip_soft_limit: 5,
    };
    const { container, rerender } = render(
      <BoardColumn state={softLimitState} issues={generateIssues(2)} />,
    );
    expect(container.querySelector('.board-column--warn')).toBeNull();
    expect(screen.getByText('(WIP 5)')).toBeDefined();
    expect(screen.queryByTestId('wip-warning-state-started')).toBeNull();

    const hardLimitState: BoardWorkflowState = {
      ...baseState,
      wip_hard_limit: 5,
    };
    rerender(<BoardColumn state={hardLimitState} issues={generateIssues(2)} />);
    expect(container.querySelector('.board-column--warn')).toBeNull();
    expect(screen.getByText('(WIP 5)')).toBeDefined();
    expect(screen.queryByTestId('wip-warning-state-started')).toBeNull();
  });

  it('getColumnDropData returns typed column descriptor and dropTargetFactory exercises closure', () => {
    let capturedData: ReturnType<typeof getColumnDropData> | undefined = undefined;
    const mockDropTarget: typeof dropTargetForElements = (opts) => {
      if (opts.getData) {
        capturedData = opts.getData({
          input: { clientY: 500 } as never,
          element: document.createElement('div'),
          source: {} as never,
        }) as ReturnType<typeof getColumnDropData>;
      }
      return () => {
        /* no-op */
      };
    };

    render(
      <BoardColumn
        state={baseState}
        issues={[]}
        dropTargetFactory={mockDropTarget}
      />,
    );

    expect((capturedData as ReturnType<typeof getColumnDropData> | undefined)?.type).toBe('column');
    expect((capturedData as ReturnType<typeof getColumnDropData> | undefined)?.stateId).toBe('state-started');

    const data = getColumnDropData('state-started');
    expect(data.type).toBe('column');
    expect(data.stateId).toBe('state-started');
  });
});
