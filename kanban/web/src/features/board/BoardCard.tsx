import React, { useEffect, useRef, type JSX } from 'react';
import {
  draggable,
  dropTargetForElements,
} from '@atlaskit/pragmatic-drag-and-drop/element/adapter';
import { EmojiHint } from '../../components/emoji/EmojiHint.tsx';
import type { EmojiKey } from '../../components/emoji/emojiRegistry.ts';
import type { BoardAssignee, BoardIssue, BoardPriority, StateGroup } from './boardApi.ts';

export interface BoardCardProps {
  issue: BoardIssue;
  stateGroup: StateGroup;
  onOpenPeek?: ((issueKey: string) => void) | undefined;
  onKeyboardMove?: ((issue: BoardIssue, direction: 'up' | 'down' | 'left' | 'right') => void) | undefined;
  isDragging?: boolean | undefined;
  dropEdge?: 'top' | 'bottom' | null | undefined;
  draggableFactory?: typeof draggable | undefined;
  dropTargetFactory?: typeof dropTargetForElements | undefined;
}

export function getCardDragData(issue: BoardIssue) {
  return {
    type: 'card' as const,
    issueKey: issue.key,
    stateId: issue.state_id,
    rank: issue.board_rank,
  };
}

export function getCardDropData(
  element: HTMLElement,
  clientY: number,
  issue: BoardIssue,
) {
  const rect = element.getBoundingClientRect();
  const midY = rect.top + rect.height / 2;
  const edge = clientY < midY ? 'top' : 'bottom';
  return {
    type: 'card' as const,
    issueKey: issue.key,
    stateId: issue.state_id,
    rank: issue.board_rank,
    edge,
  };
}

function formatDueDate(rawDate: string): string {
  const d = new Date(rawDate);
  if (Number.isNaN(d.getTime())) return rawDate;
  return new Intl.DateTimeFormat('en-US', { month: 'short', day: 'numeric', timeZone: 'UTC' }).format(d);
}

function checkIsOverdue(rawDate: string): boolean {
  const d = new Date(rawDate);
  const time = d.getTime();
  if (Number.isNaN(time)) return false;
  return time < Date.now();
}

function getPriorityEmojiKind(priority: BoardPriority | null | undefined): EmojiKey | null {
  if (!priority) return null;
  const slug = (priority.slug || priority.label).toLowerCase();
  if (slug.includes('urgent')) return 'priorityUrgent';
  if (slug.includes('high')) return 'priorityHigh';
  if (slug.includes('low')) return 'priorityLow';
  return 'priorityMedium';
}

function getAssigneeLabel(a: BoardAssignee): string {
  return a.name ?? a.handle ?? 'Agent';
}

function getUserHandle(a: BoardAssignee): string {
  return a.handle ?? a.display_name ?? a.name ?? 'user';
}

/**
 * Accessible, draggable Plane-parity Kanban card (KB-P3-37, S6.3).
 */
export function BoardCard({
  issue,
  stateGroup,
  onOpenPeek,
  onKeyboardMove,
  isDragging = false,
  dropEdge = null,
  draggableFactory = draggable,
  dropTargetFactory = dropTargetForElements,
}: BoardCardProps): JSX.Element {
  const cardRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const el = cardRef.current;
    /* v8 ignore next 3 */
    if (!el) {
      return;
    }

    const cleanupDraggable = draggableFactory({
      element: el,
      getInitialData: () => getCardDragData(issue),
    });

    const cleanupDropTarget = dropTargetFactory({
      element: el,
      getData: ({ input, element }) => getCardDropData(element as HTMLElement, input.clientY, issue),
    });

    return () => {
      cleanupDraggable();
      cleanupDropTarget();
    };
  }, [issue, draggableFactory, dropTargetFactory]);

  const handleOpenPeek = (): void => {
    if (onOpenPeek) {
      onOpenPeek(issue.key);
    } else {
      const url = new URL(window.location.href);
      url.searchParams.set('layout', 'board');
      url.searchParams.set('peek', issue.key);
      window.history.pushState({}, '', url.toString());
      window.dispatchEvent(new PopStateEvent('popstate'));
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLDivElement>): void => {
    if (e.key === 'Enter') {
      e.preventDefault();
      handleOpenPeek();
      return;
    }

    if (e.altKey && onKeyboardMove) {
      if (e.key === 'ArrowUp') {
        e.preventDefault();
        onKeyboardMove(issue, 'up');
      } else if (e.key === 'ArrowDown') {
        e.preventDefault();
        onKeyboardMove(issue, 'down');
      } else if (e.key === 'ArrowLeft') {
        e.preventDefault();
        onKeyboardMove(issue, 'left');
      } else if (e.key === 'ArrowRight') {
        e.preventDefault();
        onKeyboardMove(issue, 'right');
      }
    }
  };

  const priorityKind = getPriorityEmojiKind(issue.priority);

  // Overdue style suppressed when completed or cancelled (S7.2 8e)
  const isOverdue = Boolean(issue.due_date && checkIsOverdue(issue.due_date));
  const showOverdueStyle = isOverdue && stateGroup !== 'completed' && stateGroup !== 'cancelled';

  return (
    <div
      ref={cardRef}
      role="button"
      tabIndex={0}
      className="board-card"
      data-testid={`board-card-${issue.key}`}
      data-issue-key={issue.key}
      data-dragging={isDragging ? 'true' : undefined}
      data-drop-target={dropEdge ?? undefined}
      onKeyDown={handleKeyDown}
      aria-label={`${issue.key}: ${issue.summary}`}
    >
      <div className="board-card-top">
        <a
          href={`?layout=board&peek=${encodeURIComponent(issue.key)}`}
          className="board-card-key mono"
          data-testid={`board-card-key-${issue.key}`}
          onClick={(e) => {
            e.preventDefault();
            e.stopPropagation();
            handleOpenPeek();
          }}
        >
          {issue.key}
        </a>
        <div className="board-card-top-badges">
          {issue.gate_status === 'pending' && (
            <EmojiHint kind="gatePending" testId={`gate-pending-${issue.key}`} />
          )}
          {issue.gate_status === 'rejected' && (
            <EmojiHint kind="gateVetoed" testId={`gate-vetoed-${issue.key}`} />
          )}
          {issue.gate_status === 'approved' && (
            <EmojiHint kind="gateApproved" testId={`gate-approved-${issue.key}`} />
          )}
          {issue.has_explicit_acl && (
            <EmojiHint kind="access" label="Access scope" testId={`acl-badge-${issue.key}`} />
          )}
        </div>
      </div>

      <div className="board-card-summary">{issue.summary}</div>

      <div className="board-card-meta">
        {priorityKind && (
          <EmojiHint
            kind={priorityKind}
            label={issue.priority?.label ?? 'Priority'}
            testId={`priority-${issue.key}`}
          />
        )}

        {issue.assignees?.map((a, idx) => {
          const chipKey = a.id || String(idx);
          if (a.is_agent) {
            const agentName = getAssigneeLabel(a);
            return (
              <span key={chipKey} className="board-card-chip">
                <EmojiHint kind="agent" label={agentName} />
                <span>{agentName}</span>
              </span>
            );
          }
          if (a.free_text) {
            return (
              <span
                key={chipKey}
                className="board-card-chip board-card-chip--external assignee-chip--external"
                data-testid={`external-assignee-${issue.key}`}
              >
                <EmojiHint kind="externalAssignee" label="External free-text assignee" />
                <span>{a.free_text}</span>
              </span>
            );
          }
          return (
            <span key={chipKey} className="board-card-chip">
              @{getUserHandle(a)}
            </span>
          );
        })}

        {issue.due_date && (
          <span
            className={`board-card-chip ${showOverdueStyle ? 'board-card-chip--due-overdue' : ''}`}
            data-testid={`due-date-${issue.key}`}
          >
            📅 {formatDueDate(issue.due_date)}
          </span>
        )}

        {issue.cycle && (
          <span className="board-card-chip" data-testid={`cycle-${issue.key}`}>
            🔄 {issue.cycle.name}
          </span>
        )}
      </div>
    </div>
  );
}
