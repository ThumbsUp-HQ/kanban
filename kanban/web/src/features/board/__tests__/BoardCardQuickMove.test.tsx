import React from 'react';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { BoardCard } from '../BoardCard.tsx';
import { BoardView } from '../BoardView.tsx';
import * as boardApi from '../boardApi.ts';
import type { BoardIssue, BoardWorkflowState } from '../boardApi.ts';

const mockStates: BoardWorkflowState[] = [
  { id: 'st-backlog', name: 'Backlog', group: 'backlog', sort_order: 1 },
  { id: 'st-todo', name: 'To Do', group: 'unstarted', sort_order: 2 },
  { id: 'st-progress', name: 'In Progress', group: 'started', sort_order: 3 },
  { id: 'st-review', name: 'In Review', group: 'started', sort_order: 4 },
  { id: 'st-done', name: 'Done', group: 'completed', sort_order: 5 },
];

function renderWithClient(ui: React.ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
}

describe('BoardCardQuickMove (KAN-384)', () => {
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
        toJSON: () => ({ top: 0, left: 0, bottom: 900, right: 324, width: 324, height: 900, x: 0, y: 0 }),
      }),
    });
  });

  describe('1. State Name Resolution on BoardCard Header', () => {
    it('resolves workflow state name from projectStates when issue.state is omitted', () => {
      const issueWithoutState: BoardIssue = {
        id: 'iss-101',
        key: 'KAN-101',
        summary: 'Card with state_id only',
        state_id: 'st-progress',
        board_rank: '00000001',
      };

      render(
        <BoardCard
          issue={issueWithoutState}
          stateGroup="started"
          projectStates={mockStates}
        />,
      );

      const stateBtn = screen.getByTestId('board-card-state-btn-KAN-101');
      expect(stateBtn).toBeDefined();
      expect(stateBtn.textContent).toContain('In Progress');
      expect(stateBtn.textContent).not.toContain('Move');
    });

    it('falls back to issue.state.name when embedded directly', () => {
      const issueWithEmbeddedState: BoardIssue = {
        id: 'iss-102',
        key: 'KAN-102',
        summary: 'Card with embedded state object',
        state_id: 'st-custom',
        state: { id: 'st-custom', name: 'QA Review', group: 'started' },
        board_rank: '00000002',
      };

      render(
        <BoardCard
          issue={issueWithEmbeddedState}
          stateGroup="started"
          projectStates={mockStates}
        />,
      );

      const stateBtn = screen.getByTestId('board-card-state-btn-KAN-102');
      expect(stateBtn.textContent).toContain('QA Review');
    });

    it('falls back to Move when state cannot be resolved from projectStates or issue.state', () => {
      const issueUnresolved: BoardIssue = {
        id: 'iss-103',
        key: 'KAN-103',
        summary: 'Card with unknown state_id',
        state_id: 'st-nonexistent',
        board_rank: '00000003',
      };

      render(
        <BoardCard
          issue={issueUnresolved}
          stateGroup="unstarted"
          projectStates={mockStates}
        />,
      );

      const stateBtn = screen.getByTestId('board-card-state-btn-KAN-103');
      expect(stateBtn.textContent).toContain('Move');
    });

    it('hides state transition button when user lacks TRANSITION/EDIT capabilities', () => {
      const issue: BoardIssue = {
        id: 'iss-104',
        key: 'KAN-104',
        summary: 'Viewer read-only card',
        state_id: 'st-todo',
        board_rank: '00000004',
      };

      render(
        <BoardCard
          issue={issue}
          stateGroup="unstarted"
          projectStates={mockStates}
          currentUserCapabilities={['VIEWER']}
        />,
      );

      expect(screen.queryByTestId('board-card-state-btn-KAN-104')).toBeNull();
    });

    it('handles touch action button opening TouchReorderPopover, onSelectState, onApplyMove and onClose', () => {
      const onStateTransition = vi.fn();
      const onKeyboardMove = vi.fn();
      const issue: BoardIssue = {
        id: 'iss-105',
        key: 'KAN-105',
        summary: 'Touch reorderable card',
        state_id: 'st-todo',
        board_rank: '00000005',
      };

      const { unmount } = render(
        <BoardCard
          issue={issue}
          stateGroup="unstarted"
          projectStates={mockStates}
          onStateTransition={onStateTransition}
          onKeyboardMove={onKeyboardMove}
        />,
      );

      // Click touch action button
      const touchBtn = screen.getByTestId('board-card-touch-action-KAN-105');
      fireEvent.click(touchBtn);

      // Verify TouchReorderPopover rendered
      expect(screen.getByTestId('touch-reorder-popover')).toBeDefined();

      // Test onSelectState
      const doneOption = screen.getByTestId('touch-state-option-st-done');
      fireEvent.click(doneOption);
      expect(onStateTransition).toHaveBeenCalledWith('KAN-105', 'st-done');

      // Re-open and test onApplyMove top
      fireEvent.click(touchBtn);
      const moveTopBtn = screen.getByTestId('touch-rank-top');
      fireEvent.click(moveTopBtn);
      const applyBtn1 = screen.getByTestId('touch-reorder-apply-btn');
      fireEvent.click(applyBtn1);
      expect(onKeyboardMove).toHaveBeenCalledWith(issue, 'up');

      // Re-open and test onApplyMove bottom
      fireEvent.click(touchBtn);
      const moveBottomBtn = screen.getByTestId('touch-rank-bottom');
      fireEvent.click(moveBottomBtn);
      const applyBtn2 = screen.getByTestId('touch-reorder-apply-btn');
      fireEvent.click(applyBtn2);
      expect(onKeyboardMove).toHaveBeenCalledWith(issue, 'down');

      // Re-open and test backdrop / cancel onClose
      fireEvent.click(touchBtn);
      const cancelBtn = screen.getByTestId('touch-reorder-cancel-btn');
      fireEvent.click(cancelBtn);
      expect(screen.queryByTestId('touch-reorder-popover')).toBeNull();

      unmount();
    });

    it('handles onApplyMove without rank and without onKeyboardMove callback', () => {
      const onStateTransition = vi.fn();
      const issue: BoardIssue = {
        id: 'iss-105b',
        key: 'KAN-105B',
        summary: 'Touch reorderable card without rank change',
        state_id: 'st-todo',
        board_rank: '00000005',
      };

      const { unmount } = render(
        <BoardCard
          issue={issue}
          stateGroup="unstarted"
          projectStates={mockStates}
          onStateTransition={onStateTransition}
        />,
      );
      const touchBtn = screen.getByTestId('board-card-touch-action-KAN-105B');
      fireEvent.click(touchBtn);
      // Click Move Card directly without changing rank
      const applyBtn = screen.getByTestId('touch-reorder-apply-btn');
      fireEvent.click(applyBtn);
      expect(onStateTransition).toHaveBeenCalledWith('KAN-105B', 'st-todo');
      unmount();
    });

    it('covers anchor modifier click branches (metaKey, shiftKey, altKey)', () => {
      const onOpenPeek = vi.fn();
      const issue: BoardIssue = {
        id: 'iss-mod',
        key: 'KAN-MOD',
        summary: 'Modifier click card',
        state_id: 'st-todo',
        board_rank: '00000007',
      };

      render(
        <BoardCard
          issue={issue}
          stateGroup="unstarted"
          onOpenPeek={onOpenPeek}
        />,
      );

      const keyAnchor = screen.getByTestId('board-card-key-KAN-MOD');

      const metaEv = new MouseEvent('click', { bubbles: true, cancelable: true, button: 0, metaKey: true });
      keyAnchor.dispatchEvent(metaEv);
      expect(onOpenPeek).not.toHaveBeenCalled();

      const shiftEv = new MouseEvent('click', { bubbles: true, cancelable: true, button: 0, shiftKey: true });
      keyAnchor.dispatchEvent(shiftEv);
      expect(onOpenPeek).not.toHaveBeenCalled();

      const altEv = new MouseEvent('click', { bubbles: true, cancelable: true, button: 0, altKey: true });
      keyAnchor.dispatchEvent(altEv);
      expect(onOpenPeek).not.toHaveBeenCalled();
    });

    it('covers aging WIP display branches and thresholds', () => {
      const issueWithAging: BoardIssue = {
        id: 'iss-aging',
        key: 'KAN-AGE',
        summary: 'Aging issue',
        state_id: 'st-progress',
        board_rank: '00000008',
        age_in_current_state_hours: 48.6,
        column_p85_age_hours: 24,
      };

      const { rerender } = render(
        <BoardCard
          issue={issueWithAging}
          stateGroup="started"
        />,
      );
      expect(screen.getByTestId('aging-wip-KAN-AGE').textContent).toContain('Aging WIP (49h)');

      // isAgingWarning true with no hours
      const issueNoHours: BoardIssue = {
        id: 'iss-no-hours',
        key: 'KAN-NOH',
        summary: 'No hours issue',
        state_id: 'st-progress',
        board_rank: '00000009',
        is_aging_wip: true,
      };
      rerender(
        <BoardCard
          issue={issueNoHours}
          stateGroup="started"
          isAgingWarning={true}
        />,
      );
      expect(screen.getByTestId('aging-wip-KAN-NOH').textContent).toBe('⏱️ Aging WIP');
    });

    it('renders TouchReorderPopover with fallback states when projectStates is undefined', () => {
      const issue: BoardIssue = {
        id: 'iss-106',
        key: 'KAN-106',
        summary: 'Fallback touch card',
        state_id: 'state-todo',
        board_rank: '00000006',
      };

      render(
        <BoardCard
          issue={issue}
          stateGroup="unstarted"
        />,
      );

      const touchBtn = screen.getByTestId('board-card-touch-action-KAN-106');
      fireEvent.click(touchBtn);
      expect(screen.getByTestId('touch-reorder-popover')).toBeDefined();
    });
  });

  describe('2. BoardView State Transition Wiring', () => {
    it('clicking board-card-state-btn opens QuickFieldPopover with workflow states and transitions card', async () => {
      const moveSpy = vi.spyOn(boardApi, 'moveIssueApi').mockResolvedValue({
        issue_key: 'KAN-201',
        state_id: 'st-done',
        board_rank: '0000000000000099',
        rebalance_scheduled: false,
      });

      const issues: BoardIssue[] = [
        {
          id: 'iss-201',
          key: 'KAN-201',
          summary: 'Wire state transition on BoardView cards',
          state_id: 'st-todo',
          board_rank: '00000001',
        },
      ];

      renderWithClient(
        <BoardView
          projectKey="KAN"
          states={mockStates}
          issues={issues}
          currentUserCapabilities={['ADMIN', 'TRANSITION']}
        />,
      );

      // Verify the state button displays resolved state name 'To Do' instead of fallback 'Move'
      const stateBtn = screen.getByTestId('board-card-state-btn-KAN-201');
      expect(stateBtn.textContent).toContain('To Do');

      // Click the state transition button
      fireEvent.click(stateBtn);

      // Verify QuickFieldPopover opened with project states
      const popover = screen.getByRole('dialog', { name: 'Quick State Picker' });
      expect(popover).toBeDefined();

      // Check all workflow state options are rendered
      expect(screen.getByRole('option', { name: 'Backlog' })).toBeDefined();
      expect(screen.getByRole('option', { name: 'To Do' })).toBeDefined();
      expect(screen.getByRole('option', { name: 'In Progress' })).toBeDefined();
      expect(screen.getByRole('option', { name: 'In Review' })).toBeDefined();
      expect(screen.getByRole('option', { name: 'Done' })).toBeDefined();

      // Select target state 'In Progress'
      const inProgressOption = screen.getByRole('option', { name: 'In Progress' });
      fireEvent.click(inProgressOption);

      // Verify moveIssueApi was called with correct targetStateId
      await waitFor(() => {
        expect(moveSpy).toHaveBeenCalledWith(
          expect.objectContaining({
            projectKey: 'KAN',
            issueKey: 'KAN-201',
            targetStateId: 'st-progress',
          }),
        );
      });
    });
  });

  describe('3. CSS Structure and Desktop Fine-Pointer Rules', () => {
    it('board.css includes desktop media query to hide touch quick-move button', () => {
      const cssPath = resolve(__dirname, '../board.css');
      const cssContent = readFileSync(cssPath, 'utf-8');

      // Check fine-pointer desktop media query hiding .board-card-touch-action-btn
      expect(cssContent).toMatch(
        /@media\s*\(\s*hover:\s*hover\s*\)\s*and\s*\(\s*pointer:\s*fine\s*\)\s*\{[\s\S]*?\.board-card-touch-action-btn\s*\{[\s\S]*?display:\s*none;?/,
      );

      // Check .board-card-top flex properties preventing overlap
      expect(cssContent).toMatch(/\.board-card-top\s*\{[^}]*min-width:\s*0/);
      expect(cssContent).toMatch(/\.board-card-top\s*\{[^}]*display:\s*flex/);
      expect(cssContent).toMatch(/\.board-card-top\s*\{[^}]*justify-content:\s*space-between/);

      // Check .board-card-top-badges flex-shrink
      expect(cssContent).toMatch(/\.board-card-top-badges\s*\{[^}]*flex-shrink:\s*1/);
      expect(cssContent).toMatch(/\.board-card-top-badges\s*\{[^}]*min-width:\s*0/);

      // Check .board-card-state-btn max-width and ellipsis
      expect(cssContent).toMatch(/\.board-card-state-btn\s*\{[^}]*max-width:\s*148px/);
      expect(cssContent).toMatch(/\.board-card-state-btn\s*\{[^}]*overflow:\s*hidden/);
      expect(cssContent).toMatch(/\.board-card-state-btn\s*\{[^}]*text-overflow:\s*ellipsis/);
      expect(cssContent).toMatch(/\.board-card-state-btn\s*\{[^}]*white-space:\s*nowrap/);

      // Check .board-card-key flex-shrink: 0
      expect(cssContent).toMatch(/\.board-card-key\s*\{[^}]*flex-shrink:\s*0/);
    });

    it('boardView.css includes desktop media query to hide touch quick-move button', () => {
      const cssPath = resolve(__dirname, '../../views/boardView.css');
      const cssContent = readFileSync(cssPath, 'utf-8');

      expect(cssContent).toMatch(
        /@media\s*\(\s*hover:\s*hover\s*\)\s*and\s*\(\s*pointer:\s*fine\s*\)\s*\{[\s\S]*?\.board-card-touch-action-btn\s*\{[\s\S]*?display:\s*none;?/,
      );
    });
  });
});
