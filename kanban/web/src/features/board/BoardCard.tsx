import React, { useEffect, useRef, type JSX } from 'react';
import {
  draggable,
  dropTargetForElements,
} from '@atlaskit/pragmatic-drag-and-drop/element/adapter';
import { EmojiHint } from '../../components/emoji/EmojiHint.tsx';
import type { EmojiKey } from '../../components/emoji/emojiRegistry.ts';
import { GateStatusPill } from '../gates/GateStatusPill.tsx';
import { setOpenerElement } from '../drawer/IssueKeyLink.tsx';
import type { BoardAssignee, BoardIssue, BoardPriority, StateGroup } from './boardApi.ts';

export interface BoardCardProps {
  issue: BoardIssue;
  stateGroup: StateGroup;
  workspaceSlug?: string | undefined;
  projectKey?: string | undefined;
  onOpenPeek?: ((issueKey: string) => void) | undefined;
  onKeyboardMove?: ((issue: BoardIssue, direction: 'up' | 'down' | 'left' | 'right') => void) | undefined;
  isDragging?: boolean | undefined;
  dropEdge?: 'top' | 'bottom' | null | undefined;
  canCancelGate?: boolean | undefined;
  onCancelGate?: ((executionId: string) => void | Promise<void>) | undefined;
  onJumpToComment?: ((commentId: string) => void) | undefined;
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
  workspaceSlug,
  projectKey,
  onOpenPeek,
  onKeyboardMove,
  isDragging = false,
  dropEdge = null,
  canCancelGate = true,
  onCancelGate,
  onJumpToComment,
  draggableFactory = draggable,
  dropTargetFactory = dropTargetForElements,
}: BoardCardProps): JSX.Element {
  const cardRef = useRef<HTMLDivElement | null>(null);
  const isGatePending = issue.gate_status === 'pending' || Boolean(issue.pending_gate);

  const resolvedProjectKey =
    projectKey ?? issue.project_key ?? (issue.key ? issue.key.split('-')[0] : 'KAN') ?? 'KAN';
  const resolvedWorkspaceSlug =
    workspaceSlug ??
    (/^\/w\/([^/]+)/.exec(typeof window !== 'undefined' ? window.location.pathname : '')?.[1] ??
      'default');
  const canonicalHref = `/w/${encodeURIComponent(resolvedWorkspaceSlug)}/p/${encodeURIComponent(resolvedProjectKey)}/issues/${encodeURIComponent(issue.key)}`;

  const handleAnchorClick = (e: React.MouseEvent<HTMLAnchorElement>): void => {
    // Normal left-click without modifier keys opens peek drawer in-page
    if (e.button === 0 && !e.ctrlKey && !e.metaKey && !e.shiftKey && !e.altKey) {
      e.preventDefault();
      e.stopPropagation();
      handleOpenPeek(e.currentTarget);
    }
  };

  useEffect(() => {
    const el = cardRef.current;
    /* v8 ignore next 3 */
    if (!el) {
      return;
    }

    const cleanupDraggable = draggableFactory({
      element: el,
      canDrag: () => !isGatePending,
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
  }, [issue, isGatePending, draggableFactory, dropTargetFactory]);

  const handleOpenPeek = (targetEl?: HTMLElement | null): void => {
    setOpenerElement(targetEl ?? cardRef.current);
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

  const handleCardClick = (e: React.MouseEvent<HTMLDivElement>): void => {
    const target = e.target as HTMLElement | null;
    if (
      target?.closest(
        'button, input, select, textarea, a, [role="button"]:not(.board-card)',
      )
    ) {
      return;
    }
    handleOpenPeek(cardRef.current);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLDivElement>): void => {
    if (e.key === 'Enter') {
      e.preventDefault();
      handleOpenPeek(cardRef.current);
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
      className={`board-card ${isGatePending ? 'board-card--pending-gate' : ''}`}
      data-testid={`board-card-${issue.key}`}
      data-issue-key={issue.key}
      data-gate-pending={isGatePending ? 'true' : undefined}
      aria-disabled={isGatePending ? 'true' : undefined}
      title={isGatePending ? 'Transition gate in progress' : undefined}
      data-dragging={isDragging ? 'true' : undefined}
      data-drop-target={dropEdge ?? undefined}
      onKeyDown={handleKeyDown}
      onClick={handleCardClick}
      aria-label={`${issue.key} ${issue.summary}`.trim()}
    >
      <div className="board-card-top">
        <a
          href={canonicalHref}
          className="board-card-key mono"
          data-testid={`board-card-key-${issue.key}`}
          onClick={handleAnchorClick}
        >
          {issue.key}
        </a>
        <div className="board-card-top-badges">
          {isGatePending && (
            <GateStatusPill
              status="pending"
              pendingGate={issue.pending_gate}
              issueKey={issue.key}
              canCancel={canCancelGate}
              onCancelGate={onCancelGate}
            />
          )}
          {!isGatePending &&
            (issue.gate_status === 'rejected' ||
              issue.latest_gate_verdict?.decision === 'reject') && (
              <GateStatusPill
                status="rejected"
                latestVerdict={issue.latest_gate_verdict}
                issueKey={issue.key}
                onJumpToComment={onJumpToComment}
              />
            )}
          {!isGatePending &&
            (issue.gate_status === 'approved' ||
              issue.latest_gate_verdict?.decision === 'approve') && (
              <GateStatusPill
                status="approved"
                latestVerdict={issue.latest_gate_verdict}
                issueKey={issue.key}
              />
            )}
          {issue.has_explicit_acl && (
            <EmojiHint kind="access" label="Access scope" testId={`acl-badge-${issue.key}`} />
          )}
        </div>
      </div>

      <a
        href={canonicalHref}
        className="board-card-summary-link"
        data-testid={`board-card-summary-${issue.key}`}
        onClick={handleAnchorClick}
      >
        <div className="board-card-summary">{issue.summary}</div>
      </a>

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
