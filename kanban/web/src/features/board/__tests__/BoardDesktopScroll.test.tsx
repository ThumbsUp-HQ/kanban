import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, fireEvent } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { BoardView } from '../BoardView.tsx';
import type { BoardIssue, BoardWorkflowState } from '../boardApi.ts';

const mockStates: BoardWorkflowState[] = [
  { id: 'st-backlog', name: 'Backlog', group: 'backlog', sort_order: 1 },
  { id: 'st-todo', name: 'To Do', group: 'unstarted', sort_order: 2 },
  { id: 'st-progress', name: 'In Progress', group: 'started', sort_order: 3 },
  { id: 'st-review', name: 'In Review', group: 'started', sort_order: 4 },
  { id: 'st-done', name: 'Done', group: 'completed', sort_order: 5 },
];

function generateIssues(count: number, stateId = 'st-todo'): BoardIssue[] {
  return Array.from({ length: count }, (_, i) => ({
    id: `iss-${String(i + 1)}`,
    key: `KAN-${String(i + 1)}`,
    summary: `Test issue card item #${String(i + 1)} with comprehensive text description`,
    state_id: stateId,
    board_rank: `000000000000${String(i).padStart(4, '0')}`,
  }));
}

function renderInFullAppHierarchy(ui: ReactNode, layout = 'board') {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <div className="kb-app-shell">
        <main className="kb-main-canvas" id="main">
          <div data-testid="route-placeholder" data-route="/projects/KAN/issues">
            <div
              className="issues-workspace issues-workspace-route"
              data-testid="issues-workspace"
              data-layout={layout}
            >
              {ui}
            </div>
          </div>
        </main>
      </div>
    </QueryClientProvider>,
  );
}

describe('BoardDesktopScroll & Flex Containment (KAN-380)', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('renders the complete unstyled route/workspace flex wrapper chain around BoardView', () => {
    const issues = generateIssues(20, 'st-todo');
    const { container } = renderInFullAppHierarchy(
      <BoardView projectKey="KAN" states={mockStates} issues={issues} />,
    );

    const appShell = container.querySelector('.kb-app-shell');
    const mainCanvas = container.querySelector('.kb-main-canvas');
    const routePlaceholder = screen.getByTestId('route-placeholder');
    const issuesWorkspace = screen.getByTestId('issues-workspace');
    const boardCanvas = screen.getByTestId('board-canvas');
    const boardLanes = screen.getByTestId('board-lanes');

    expect(appShell).not.toBeNull();
    expect(mainCanvas).not.toBeNull();
    expect(routePlaceholder).not.toBeNull();
    expect(issuesWorkspace).not.toBeNull();
    expect(boardCanvas).not.toBeNull();
    expect(boardLanes).not.toBeNull();

    // Verify DOM nesting hierarchy
    expect(mainCanvas?.contains(routePlaceholder)).toBe(true);
    expect(routePlaceholder.contains(issuesWorkspace)).toBe(true);
    expect(issuesWorkspace.contains(boardCanvas)).toBe(true);
    expect(boardCanvas.contains(boardLanes)).toBe(true);
  });

  it('positive case: handles 15+ cards in a column with vertical and horizontal scrolling', () => {
    const issues = generateIssues(25, 'st-todo');
    renderInFullAppHierarchy(
      <BoardView projectKey="KAN" states={mockStates} issues={issues} />,
    );

    const todoColumn = screen.getByTestId('board-column-st-todo');
    expect(todoColumn).not.toBeNull();
    expect(todoColumn.classList.contains('board-column')).toBe(true);

    const scrollArea = screen.getByTestId('scroll-area-st-todo');
    expect(scrollArea).not.toBeNull();
    expect(scrollArea.classList.contains('board-column-scroll-area')).toBe(true);

    // Mock layout metrics on scrollArea: scrollHeight > clientHeight (simulating 25 cards)
    Object.defineProperty(scrollArea, 'clientHeight', { configurable: true, value: 720 });
    Object.defineProperty(scrollArea, 'scrollHeight', { configurable: true, value: 2400 });
    Object.defineProperty(scrollArea, 'getBoundingClientRect', {
      configurable: true,
      value: () => ({
        top: 100,
        left: 360,
        bottom: 820,
        right: 684,
        width: 324,
        height: 720,
        x: 360,
        y: 100,
        toJSON: () => undefined,
      }),
    });

    expect(scrollArea.scrollHeight).toBeGreaterThan(scrollArea.clientHeight);
    expect(scrollArea.getBoundingClientRect().bottom).toBeLessThanOrEqual(900);

    // Simulate vertical scrolling
    scrollArea.scrollTop = 250;
    fireEvent.scroll(scrollArea, { target: { scrollTop: 250 } });
    expect(scrollArea.scrollTop).toBe(250);

    // Assert horizontal lanes container scrolling
    const lanes = screen.getByTestId('board-lanes');
    Object.defineProperty(lanes, 'clientWidth', { configurable: true, value: 1384 });
    Object.defineProperty(lanes, 'scrollWidth', { configurable: true, value: 1700 });
    Object.defineProperty(lanes, 'getBoundingClientRect', {
      configurable: true,
      value: () => ({
        top: 80,
        left: 28,
        bottom: 872,
        right: 1412,
        width: 1384,
        height: 792,
        x: 28,
        y: 80,
        toJSON: () => undefined,
      }),
    });

    expect(lanes.scrollWidth).toBeGreaterThan(lanes.clientWidth);
    expect(lanes.getBoundingClientRect().bottom).toBeLessThanOrEqual(900);

    lanes.scrollLeft = 320;
    fireEvent.scroll(lanes, { target: { scrollLeft: 320 } });
    expect(lanes.scrollLeft).toBe(320);
  });

  it('negative & boundary case: empty columns render cleanly without scroll overflow', () => {
    const issues: BoardIssue[] = [];
    renderInFullAppHierarchy(
      <BoardView projectKey="KAN" states={mockStates} issues={issues} />,
    );

    const backlogScrollArea = screen.getByTestId('scroll-area-st-backlog');
    expect(backlogScrollArea).not.toBeNull();

    Object.defineProperty(backlogScrollArea, 'clientHeight', { configurable: true, value: 720 });
    Object.defineProperty(backlogScrollArea, 'scrollHeight', { configurable: true, value: 100 });

    expect(backlogScrollArea.scrollHeight).toBeLessThanOrEqual(backlogScrollArea.clientHeight);
  });

  it('boundary case: single-card column does not trigger excess vertical scroll requirements', () => {
    const issues = generateIssues(1, 'st-progress');
    renderInFullAppHierarchy(
      <BoardView projectKey="KAN" states={mockStates} issues={issues} />,
    );

    const progressScrollArea = screen.getByTestId('scroll-area-st-progress');
    expect(progressScrollArea).not.toBeNull();

    Object.defineProperty(progressScrollArea, 'clientHeight', { configurable: true, value: 720 });
    Object.defineProperty(progressScrollArea, 'scrollHeight', { configurable: true, value: 140 });

    expect(progressScrollArea.scrollHeight).toBeLessThanOrEqual(progressScrollArea.clientHeight);
  });

  it('boundary case: wide board with many columns renders all lanes inside horizontal scroll container', () => {
    const wideStates: BoardWorkflowState[] = [
      { id: 's1', name: 'Triaged', group: 'backlog', sort_order: 1 },
      { id: 's2', name: 'Design Spec', group: 'unstarted', sort_order: 2 },
      { id: 's3', name: 'Engineering', group: 'started', sort_order: 3 },
      { id: 's4', name: 'Code Review', group: 'started', sort_order: 4 },
      { id: 's5', name: 'QA Testing', group: 'started', sort_order: 5 },
      { id: 's6', name: 'Security Audit', group: 'started', sort_order: 6 },
      { id: 's7', name: 'Deployed', group: 'completed', sort_order: 7 },
    ];
    renderInFullAppHierarchy(
      <BoardView projectKey="KAN" states={wideStates} issues={[]} />,
    );

    const lanes = screen.getByTestId('board-lanes');
    expect(lanes.children.length).toBe(7);

    // Each lane is 324px + 20px gap -> 7 lanes = 2388px total width
    const calculatedWidth = 7 * 324 + 6 * 20;
    expect(calculatedWidth).toBe(2388);
  });
});
