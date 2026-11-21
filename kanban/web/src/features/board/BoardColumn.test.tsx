import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
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
  let cleanupNav: (() => void) | undefined;
  beforeEach(() => {
    const navHandler = (e: Event): void => {
      e.preventDefault();
    };
    window.addEventListener('click', navHandler, true);
    cleanupNav = () => {
      window.removeEventListener('click', navHandler, true);
    };
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

  afterEach(() => {
    cleanupNav?.();
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

  it('navigates to workflow settings when + Workflow button is clicked', () => {
    const assignSpy = vi.fn();
    Object.defineProperty(window, 'location', {
      writable: true,
      value: { assign: assignSpy, pathname: '/projects/KAN/issues' },
    });

    render(
      <BoardColumn
        state={baseState}
        issues={[]}
      />,
    );

    const workflowBtn = screen.getByTestId(`section-add-workflow-btn-${baseState.name}`);
    fireEvent.click(workflowBtn);
    expect(assignSpy).toHaveBeenCalledWith(
      `/projects/KAN/settings/workflows?to_state=${encodeURIComponent(baseState.name)}&attach=1`,
    );
  });

  it('synchronizes custom state color and pending gate count (KAN-43 Problem 2)', () => {
    const customColorState: BoardWorkflowState = {
      ...baseState,
      color_hex: '#7C3AED',
    };
    const gateIssues: BoardIssue[] = [
      {
        id: 'iss-gate',
        key: 'KAN-99',
        summary: 'Issue with Gate',
        state_id: 'state-started',
        board_rank: 'rank-000099',
        gate_status: 'pending',
      },
    ];

    const { rerender } = render(
      <BoardColumn
        state={customColorState}
        issues={gateIssues}
        canManageWorkflows={false}
      />,
    );

    const colSection = screen.getByTestId(`board-column-${customColorState.id}`);
    expect(colSection.style.getPropertyValue('--state-custom-fg')).toBe('#7C3AED');
    expect(screen.getByTestId(`board-column-gate-count-${customColorState.id}`)).toBeDefined();
    expect(screen.queryByTestId(`section-add-workflow-btn-${customColorState.name}`)).toBeNull();

    // Rerender with null color to verify removal
    rerender(
      <BoardColumn
        state={baseState}
        issues={[]}
      />,
    );
    expect(colSection.style.getPropertyValue('--state-custom-fg')).toBe('');
    expect(screen.queryByTestId(`board-column-gate-count-${baseState.id}`)).toBeNull();
  });

  it('exercises drag state, drop edge, and explicit projectKey props', () => {
    const issues = generateIssues(1);
    const { unmount } = render(
      <BoardColumn
        state={baseState}
        issues={issues}
        projectKey="EXPLICIT_KEY"
        draggingKey="KAN-1"
        dropTargetKey="KAN-1"
        dropEdge="top"
      />,
    );
    expect(screen.getByText('KAN-1')).toBeDefined();
    unmount();
  });

  it('renders untruncated Purple Review header with WIP label, + Workflow button, and WIP warn simultaneously', () => {
    const purpleReviewState: BoardWorkflowState = {
      ...baseState,
      id: 'state-purple-review',
      name: 'Purple Review',
      group: 'started',
      color_hex: '#7c3aed',
      wip_soft_limit: 2,
      wip_hard_limit: 5,
    };
    const issues = generateIssues(3);

    const { container } = render(
      <BoardColumn
        state={purpleReviewState}
        issues={issues}
        canManageWorkflows={true}
      />,
    );

    const colSection = screen.getByTestId(`board-column-${purpleReviewState.id}`);
    expect(colSection.classList.contains('board-column--warn')).toBe(true);
    expect(colSection.style.getPropertyValue('--state-custom-fg')).toBe('#7c3aed');

    const titleEl = container.querySelector('.board-column-title');
    expect(titleEl?.textContent).toBe('Purple Review');

    expect(screen.getByText('(WIP 5)')).toBeDefined();
    expect(screen.getByTestId('section-add-workflow-btn-Purple Review')).toBeDefined();
    expect(screen.getByTestId('wip-warning-state-purple-review')).toBeDefined();

    // Verify 2-row layout classes
    expect(container.querySelector('.board-column-header-left')).toBeDefined();
    expect(container.querySelector('.board-column-header-right')).toBeDefined();
  });
});
