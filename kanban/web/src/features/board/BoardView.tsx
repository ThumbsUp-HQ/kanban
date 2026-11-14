import React, { useCallback, useEffect, useMemo, useState, type JSX } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { monitorForElements } from '@atlaskit/pragmatic-drag-and-drop/element/adapter';
import { announce } from '../../api/RealtimeStatus.tsx';
import { apiFetch } from '../../api/client.ts';
import type { RealtimeClient } from '../../api/realtime.ts';
import { useOptimisticMutation } from '../../api/optimistic.ts';
import { qk } from '../../api/queryKeys.ts';
import { useGateRealtimeSync, cancelGateTransitionApi } from '../gates/index.ts';
import { BoardColumn } from './BoardColumn.tsx';
import { HardWipOverrideModal } from './HardWipOverrideModal.tsx';
import {
  applyOptimisticMove,
  moveIssueApi,
  type BoardIssue,
  type BoardWorkflowState,
  type IssueMoveParams,
  type IssueMoveResponse,
} from './boardApi.ts';
import { midpointRank } from './fractionalRank.ts';
import './board.css';

export interface BoardViewProps {
  projectKey: string;
  states?: BoardWorkflowState[];
  issues?: BoardIssue[];
  currentUserCapabilities?: string[];
  realtimeClient?: RealtimeClient | undefined;
  onOpenPeek?: (issueKey: string) => void;
  onNewItem?: (stateId: string) => void;
  onMoveSuccess?: (res: IssueMoveResponse) => void;
  monitorFactory?: typeof monitorForElements;
}

interface PendingHardWipMove {
  params: IssueMoveParams;
  targetState: BoardWorkflowState;
  count: number;
}

const DEFAULT_STATES: BoardWorkflowState[] = [
  { id: 'state-backlog', name: 'Backlog', group: 'backlog', sort_order: 1 },
  { id: 'state-todo', name: 'To Do', group: 'unstarted', sort_order: 2 },
  { id: 'state-in-progress', name: 'In Progress', group: 'started', sort_order: 3, wip_soft_limit: 3 },
  { id: 'state-in-review', name: 'In Review', group: 'started', sort_order: 4, wip_hard_limit: 3 },
  { id: 'state-done', name: 'Done', group: 'completed', sort_order: 5 },
];

/**
 * High-performance virtualized Kanban Board view with Pragmatic DnD (KB-P3-37, S6.1-6.4).
 */
export function BoardView({
  projectKey,
  states: propStates,
  issues: propIssues,
  currentUserCapabilities: propCapabilities,
  realtimeClient,
  onOpenPeek,
  onNewItem,
  onMoveSuccess,
  monitorFactory = monitorForElements,
}: BoardViewProps): JSX.Element {
  const queryClient = useQueryClient();
  const [localIssues, setLocalIssues] = useState<BoardIssue[] | null>(null);
  const [draggingKey, setDraggingKey] = useState<string | null>(null);
  const [dropTargetKey, setDropTargetKey] = useState<string | null>(null);
  const [dropEdge, setDropEdge] = useState<'top' | 'bottom' | null>(null);
  const [toastMessage, setToastMessage] = useState<string | null>(null);
  const [pendingHardWipMove, setPendingHardWipMove] = useState<PendingHardWipMove | null>(null);

  useGateRealtimeSync({
    client: realtimeClient,
    queryClient,
    projectKey,
    onToast: (msg) => {
      setToastMessage(msg);
      setTimeout(() => {
        setToastMessage((prev) => (prev === msg ? null : prev));
      }, 5000);
    },
  });

  // Fetch project details for states and capabilities when omitted
  const projectQuery = useQuery({
    queryKey: qk.project(projectKey),
    queryFn: async () => {
      const data: unknown = await apiFetch('GET', '/api/v1/projects/{project_ref}', {
        params: { project_ref: projectKey },
      });
      return data;
    },
    enabled: propStates === undefined,
  });

  const states = useMemo(() => {
    if (propStates) return propStates;
    const data = projectQuery.data;
    if (
      data !== null &&
      typeof data === 'object' &&
      'states' in data &&
      Array.isArray(data.states) &&
      data.states.length > 0
    ) {
      return data.states as BoardWorkflowState[];
    }
    return DEFAULT_STATES;
  }, [propStates, projectQuery.data]);

  const currentUserCapabilities = useMemo(() => {
    if (propCapabilities !== undefined && propCapabilities.length > 0) {
      return propCapabilities;
    }
    const data = projectQuery.data;
    if (
      data !== null &&
      typeof data === 'object' &&
      'capabilities' in data &&
      Array.isArray(data.capabilities)
    ) {
      return data.capabilities as string[];
    }
    return propCapabilities ?? [];
  }, [propCapabilities, projectQuery.data]);

  // Fetch issues if propIssues is not provided
  const issuesQuery = useQuery({
    queryKey: qk.issues(projectKey, {}),
    queryFn: async (): Promise<BoardIssue[]> => {
      const data: unknown = await apiFetch('GET', '/api/v1/projects/{project_ref}/issues', {
        params: { project_ref: projectKey },
      });
      if (Array.isArray(data)) {
        return data as BoardIssue[];
      }
      if (
        data !== null &&
        typeof data === 'object' &&
        'items' in data &&
        Array.isArray(data.items)
      ) {
        return data.items as BoardIssue[];
      }
      return [];
    },
    enabled: propIssues === undefined,
    initialData: propIssues,
  });

  const rawQueryIssues = issuesQuery.data;
  const issues = useMemo(() => {
    const raw = localIssues ?? propIssues ?? rawQueryIssues ?? [];
    return raw.map((iss) => {
      const record = iss as { state_id?: string; state?: { id?: string } };
      const stateId = record.state_id ?? record.state?.id ?? '';
      return {
        ...iss,
        state_id: stateId,
      };
    });
  }, [localIssues, propIssues, rawQueryIssues]);

  const isAdmin = useMemo(() => {
    return currentUserCapabilities.some((cap) =>
      ['ADMIN', 'PROJECT_ADMIN', 'SERVER_ADMIN'].includes(cap.toUpperCase()),
    );
  }, [currentUserCapabilities]);

  // Group and sort issues by state and board_rank (COLLATE "C")
  const issuesByState = useMemo(() => {
    const map: Record<string, BoardIssue[]> = {};
    for (const st of states) {
      map[st.id] = [];
    }
    for (const issue of issues) {
      map[issue.state_id] ??= [];
      map[issue.state_id]?.push(issue);
    }
    // Sort strictly by board_rank in ASCII byte order
    for (const stId of Object.keys(map)) {
      map[stId]?.sort((a, b) => (a.board_rank < b.board_rank ? -1 : a.board_rank > b.board_rank ? 1 : 0));
    }
    return map;
  }, [states, issues]);

  // Optimistic mutation hook
  const moveMutation = useOptimisticMutation<IssueMoveParams, IssueMoveResponse, BoardIssue[]>({
    mutationFn: (vars) => moveIssueApi(vars),
    queryKey: qk.issues(projectKey, {}),
    apply: (cache, vars) => applyOptimisticMove(cache, vars),
    onRollbackMessage: () => 'Failed to move issue. Changes were reverted.',
  });

  const executeMove = useCallback(
    async (moveParams: IssueMoveParams) => {
      // Optimistically update local issues synchronously (< 12ms budget)
      const previousIssues = issues;
      const updatedIssues = applyOptimisticMove(previousIssues, moveParams);
      setLocalIssues(updatedIssues);

      try {
        const res = await moveMutation.mutateAsync(moveParams);
        onMoveSuccess?.(res);
      } catch {
        // Rollback local state
        setLocalIssues(previousIssues);
      }
    },
    [issues, moveMutation, onMoveSuccess],
  );

  const handlePerformMove = useCallback(
    (issueKey: string, targetData: Record<string, unknown>) => {
      const movedIssue = issues.find((i) => i.key === issueKey);
      if (!movedIssue) return;

      const targetType = targetData.type as string;
      let targetStateId = '';
      let targetCardKey: string | null = null;
      let edge: 'top' | 'bottom' = 'bottom';

      if (targetType === 'card') {
        targetStateId = targetData.stateId as string;
        targetCardKey = targetData.issueKey as string;
        edge = targetData.edge === 'top' ? 'top' : 'bottom';
      } else if (targetType === 'column') {
        targetStateId = targetData.stateId as string;
      } else {
        return;
      }

      const targetState = states.find((s) => s.id === targetStateId);
      if (!targetState) return;

      // Filter target column cards (excluding the moving card for intra-column move)
      const targetColCards = (issuesByState[targetStateId] ?? []).filter((i) => i.key !== issueKey);

      let aboveCard: BoardIssue | null = null;
      let belowCard: BoardIssue | null = null;

      if (targetCardKey && targetCardKey !== issueKey) {
        const targetIdx = targetColCards.findIndex((i) => i.key === targetCardKey);
        if (targetIdx !== -1) {
          if (edge === 'top') {
            belowCard = targetColCards[targetIdx] ?? null;
            aboveCard = targetIdx > 0 ? targetColCards[targetIdx - 1] ?? null : null;
          } else {
            aboveCard = targetColCards[targetIdx] ?? null;
            belowCard = targetIdx < targetColCards.length - 1 ? targetColCards[targetIdx + 1] ?? null : null;
          }
        }
      } else {
        // Dropped onto column: append at bottom
        aboveCard = targetColCards.length > 0 ? targetColCards[targetColCards.length - 1] ?? null : null;
        belowCard = null;
      }

      const newRank = midpointRank(aboveCard?.board_rank ?? null, belowCard?.board_rank ?? null);
      const isCrossColumn = movedIssue.state_id !== targetStateId;
      const targetCount = targetColCards.length;

      // Hard WIP limit enforcement (Section 6.4)
      if (isCrossColumn && targetState.wip_hard_limit != null && targetCount >= targetState.wip_hard_limit) {
        if (!isAdmin) {
          // Non-admin: blocked without network call
          const msg = `Hard WIP limit reached (${String(targetCount)}/${String(targetState.wip_hard_limit)}) on ${targetState.name}. Ask a Project Admin to raise the limit or override.`;
          setToastMessage(msg);
          announce(msg);
          return;
        }

        // Admin: open HardWipOverrideModal
        setPendingHardWipMove({
          params: {
            projectKey,
            issueKey,
            targetStateId,
            afterIssueKey: aboveCard ? aboveCard.key : null,
            beforeIssueKey: belowCard ? belowCard.key : null,
            boardRank: newRank,
          },
          targetState,
          count: targetCount,
        });
        return;
      }

      // Soft WIP announcement
      if (isCrossColumn && targetState.wip_soft_limit != null && targetCount >= targetState.wip_soft_limit) {
        announce(
          `Soft WIP limit exceeded (${String(targetCount + 1)} / ${String(targetState.wip_soft_limit)}). Transitions remain allowed.`,
        );
      }

      void executeMove({
        projectKey,
        issueKey,
        targetStateId,
        afterIssueKey: aboveCard ? aboveCard.key : null,
        beforeIssueKey: belowCard ? belowCard.key : null,
        boardRank: newRank,
      });
    },
    [issues, states, issuesByState, isAdmin, projectKey, executeMove],
  );

  // Global Drag and Drop monitor
  useEffect(() => {
    return monitorFactory({
      onDragStart: ({ source }) => {
        const data = source.data;
        if (data.type === 'card' && typeof data.issueKey === 'string') {
          setDraggingKey(data.issueKey);
        }
      },
      onDropTargetChange: ({ location }) => {
        const current = location.current.dropTargets[0];
        if (current?.data.type === 'card') {
          setDropTargetKey(current.data.issueKey as string);
          setDropEdge(current.data.edge === 'top' ? 'top' : 'bottom');
        } else {
          setDropTargetKey(null);
          setDropEdge(null);
        }
      },
      onDrop: ({ source, location }) => {
        setDraggingKey(null);
        setDropTargetKey(null);
        setDropEdge(null);

        const sourceData = source.data;
        if (sourceData.type !== 'card') return;

        const issueKey = sourceData.issueKey as string;
        const dropTarget = location.current.dropTargets[0];
        if (!dropTarget) return;

        handlePerformMove(issueKey, dropTarget.data);
      },
    });
  }, [handlePerformMove, monitorFactory]);

  // Keyboard navigation handler (Alt+Arrows)
  const handleKeyboardMove = useCallback(
    (issue: BoardIssue, direction: 'up' | 'down' | 'left' | 'right') => {
      const currentStateIdx = states.findIndex((s) => s.id === issue.state_id);
      const currentState = states[currentStateIdx];
      if (!currentState) return;

      const colCards = issuesByState[issue.state_id] ?? [];
      const cardIdx = colCards.findIndex((i) => i.key === issue.key);

      if (direction === 'left' || direction === 'right') {
        const targetStateIdx = direction === 'left' ? currentStateIdx - 1 : currentStateIdx + 1;
        if (targetStateIdx < 0 || targetStateIdx >= states.length) return;

        const targetState = states[targetStateIdx];
        if (!targetState) return;

        handlePerformMove(issue.key, {
          type: 'column',
          stateId: targetState.id,
        });
        announce(`Moved ${issue.key} to ${targetState.name}`);
      } else if (direction === 'up' && cardIdx > 0) {
        // Swap with card above
        const aboveTarget = colCards[cardIdx - 1];
        /* v8 ignore next 3 */
        if (!aboveTarget) {
          return;
        }

        handlePerformMove(issue.key, {
          type: 'card',
          stateId: currentState.id,
          issueKey: aboveTarget.key,
          edge: 'top',
        });
        announce(`Moved ${issue.key} up in ${currentState.name}`);
      } else if (direction === 'down' && cardIdx < colCards.length - 1) {
        // Swap with card below
        const belowTarget = colCards[cardIdx + 1];
        /* v8 ignore next 3 */
        if (!belowTarget) {
          return;
        }

        handlePerformMove(issue.key, {
          type: 'card',
          stateId: currentState.id,
          issueKey: belowTarget.key,
          edge: 'bottom',
        });
        announce(`Moved ${issue.key} down in ${currentState.name}`);
      }
    },
    [states, issuesByState, handlePerformMove],
  );

  const handleHardWipModalSubmit = (reason: string) => {
    /* v8 ignore next 3 */
    if (!pendingHardWipMove) {
      return;
    }
    const { params } = pendingHardWipMove;
    setPendingHardWipMove(null);

    void executeMove({
      ...params,
      overrideWip: true,
      wipOverrideReason: reason,
    });
  };

  return (
    <div className="board-canvas" data-testid="board-canvas">
      {toastMessage && (
        <div role="alert" className="board-alert-toast" data-testid="board-alert-toast">
          <span>⚠️</span>
          <span>{toastMessage}</span>
          <button
            type="button"
            className="board-alert-toast-close"
            onClick={() => { setToastMessage(null); }}
            aria-label="Dismiss alert"
          >
            ✕
          </button>
        </div>
      )}

      <div className="board-lanes" data-testid="board-lanes">
        {states.map((st) => {
          /* v8 ignore next */
          const colIssues = issuesByState[st.id] ?? [];
          return (
            <BoardColumn
              key={st.id}
              state={st}
              issues={colIssues}
              draggingKey={draggingKey}
              dropTargetKey={dropTargetKey}
              dropEdge={dropEdge}
              canCancelGate={isAdmin || true}
              onCancelGate={async (execId) => {
                await cancelGateTransitionApi(execId);
              }}
              onOpenPeek={onOpenPeek}
              onKeyboardMove={handleKeyboardMove}
              onNewItem={onNewItem}
            />
          );
        })}
      </div>

      {pendingHardWipMove && (
        <HardWipOverrideModal
          isOpen={true}
          state={pendingHardWipMove.targetState}
          count={pendingHardWipMove.count}
          onCancel={() => { setPendingHardWipMove(null); }}
          onSubmit={handleHardWipModalSubmit}
        />
      )}
    </div>
  );
}
