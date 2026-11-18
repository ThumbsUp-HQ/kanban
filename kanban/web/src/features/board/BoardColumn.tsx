import React, { useLayoutEffect, useRef, useEffect, type JSX } from 'react';
import { useVirtualizer } from '@tanstack/react-virtual';
import { dropTargetForElements } from '@atlaskit/pragmatic-drag-and-drop/element/adapter';
import { EmojiHint } from '../../components/emoji/EmojiHint.tsx';
import { StateBadge } from '../../components/state/StateBadge.tsx';
import { BoardCard } from './BoardCard.tsx';
import type { BoardIssue, BoardWorkflowState, StateGroup } from './boardApi.ts';

export interface BoardColumnProps {
  state: BoardWorkflowState;
  issues: BoardIssue[];
  draggingKey?: string | null | undefined;
  dropTargetKey?: string | null | undefined;
  dropEdge?: 'top' | 'bottom' | null | undefined;
  canCancelGate?: boolean | undefined;
  canManageWorkflows?: boolean | undefined;
  onCancelGate?: ((executionId: string) => void | Promise<void>) | undefined;
  onJumpToComment?: ((commentId: string) => void) | undefined;
  onOpenPeek?: ((issueKey: string) => void) | undefined;
  onKeyboardMove?: ((issue: BoardIssue, direction: 'up' | 'down' | 'left' | 'right') => void) | undefined;
  onNewItem?: ((stateId: string) => void) | undefined;
  dropTargetFactory?: typeof dropTargetForElements | undefined;
}

export function getColumnDropData(stateId: string) {
  return {
    type: 'column' as const,
    stateId,
  };
}

const STATE_GLYPHS: Record<StateGroup, string> = {
  backlog: '○',
  unstarted: '◌',
  started: '◐',
  completed: '●',
  cancelled: '⊘',
};

interface VirtualCardWrapperProps {
  start: number;
  virtualIndex: number;
  measureElement: (node: HTMLElement | null) => void;
  children: React.ReactNode;
}

function VirtualCardWrapper({
  start,
  virtualIndex,
  measureElement,
  children,
}: VirtualCardWrapperProps): JSX.Element {
  const elRef = useRef<HTMLDivElement | null>(null);

  useLayoutEffect(() => {
    /* v8 ignore next 3 */
    if (!elRef.current) {
      return;
    }
    elRef.current.style.transform = `translateY(${String(start)}px)`;
  }, [start]);

  return (
    <div
      ref={(el) => {
        elRef.current = el;
        measureElement(el);
      }}
      data-index={virtualIndex}
      className="board-card-wrapper"
    >
      {children}
    </div>
  );
}

/**
 * 324px virtualized Kanban lane with WIP enforcement (KB-P3-37, S6.1, S6.3).
 */
export function BoardColumn({
  state,
  issues,
  draggingKey,
  dropTargetKey,
  dropEdge,
  canCancelGate,
  canManageWorkflows = true,
  onCancelGate,
  onJumpToComment,
  onOpenPeek,
  onKeyboardMove,
  onNewItem,
  dropTargetFactory = dropTargetForElements,
}: BoardColumnProps): JSX.Element {
  const pathMatch = typeof window !== 'undefined' ? /\/projects\/([^/]+)/.exec(window.location.pathname) : null;
  const projectKey = pathMatch?.[1] ?? 'KAN';
  const colRef = useRef<HTMLDivElement | null>(null);
  const parentRef = useRef<HTMLDivElement | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);

  const glyph = STATE_GLYPHS[state.group];
  const count = issues.length;
  const pendingGateCount = issues.filter(
    (i) => i.gate_status === 'pending' || Boolean(i.pending_gate),
  ).length;

  const isSoftWipExceeded = Boolean(state.wip_soft_limit && count > state.wip_soft_limit);
  const isHardWipExceeded = Boolean(state.wip_hard_limit && count >= state.wip_hard_limit);
  const isWipExceeded = isSoftWipExceeded || isHardWipExceeded;

  let wipLimitNum: number | null = null;
  if (state.wip_hard_limit != null) {
    wipLimitNum = state.wip_hard_limit;
  } else if (state.wip_soft_limit != null) {
    wipLimitNum = state.wip_soft_limit;
  }
  const wipLabel = wipLimitNum != null ? `(WIP ${String(wipLimitNum)})` : null;

  let wipTooltipContent = '';
  if (isHardWipExceeded) {
    wipTooltipContent = `Hard WIP limit reached (${String(count)}/${String(state.wip_hard_limit)}) on ${state.name}. Ask a Project Admin to raise the limit or override.`;
  } else if (isSoftWipExceeded) {
    wipTooltipContent = `Soft WIP limit exceeded (${String(count)} / ${String(state.wip_soft_limit)}). Transitions remain allowed.`;
  }

  // Register column as drop target
  useEffect(() => {
    const el = colRef.current;
    /* v8 ignore next 3 */
    if (!el) {
      return;
    }

    return dropTargetFactory({
      element: el,
      getData: () => getColumnDropData(state.id),
    });
  }, [state.id, dropTargetFactory]);

  // Virtualizer with CSP-safe sizing
  // eslint-disable-next-line react-hooks/incompatible-library
  const virtualizer = useVirtualizer({
    count: issues.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => 124,
    gap: 12,
    overscan: 6,
  });

  const totalHeight = virtualizer.getTotalSize();
  const virtualItems = virtualizer.getVirtualItems();

  useLayoutEffect(() => {
    /* v8 ignore next 3 */
    if (!containerRef.current) {
      return;
    }
    containerRef.current.style.height = `${String(totalHeight)}px`;
  }, [totalHeight]);

  return (
    <section
      ref={colRef}
      className={`board-column ${isWipExceeded ? 'board-column--warn' : ''}`}
      data-testid={`board-column-${state.id}`}
      data-state-id={state.id}
      data-state-name={state.name}
      aria-label={`${state.name} lane, ${String(count)} issues`}
    >
      <header className="board-column-header">
        <div className="board-column-header-left">
          <StateBadge
            state={state}
            showLabel={false}
            className="board-column-glyph"
          />
          <span hidden aria-hidden="true">
            {glyph}
          </span>
          <span className="board-column-title" title={state.name}>
            {state.name}
          </span>
          <span className="board-column-count">{count}</span>
          {pendingGateCount >= 1 && (
            <span
              className="board-column-header-gate-count"
              data-testid={`board-column-gate-count-${state.id}`}
              title={`${String(pendingGateCount)} gate(s) pending in this column`}
            >
              <span aria-hidden="true">⏳🤖</span>
              <span>{pendingGateCount}</span>
            </span>
          )}
          {wipLabel && <span className="board-column-wip">{wipLabel}</span>}
        </div>
        <div className="board-column-header-right">
          {canManageWorkflows && (
            <button
              type="button"
              className="board-column-add-workflow-btn"
              data-testid={`section-add-workflow-btn-${state.name}`}
              title={`Attach workflow transition to ${state.name}`}
              onClick={(e) => {
                e.stopPropagation();
                if (typeof window !== 'undefined') {
                  window.location.assign(
                    `/projects/${projectKey}/settings/workflows?to_state=${encodeURIComponent(state.name)}&attach=1`,
                  );
                }
              }}
            >
              + Workflow
            </button>
          )}
          {isWipExceeded && (
            <EmojiHint
              kind="warning"
              content={wipTooltipContent}
              testId={`wip-warning-${state.id}`}
            />
          )}
        </div>
      </header>

      <div
        ref={parentRef}
        className="board-column-scroll-area"
        data-testid={`scroll-area-${state.id}`}
      >
        <div ref={containerRef} className="board-column-virtual-container">
          {virtualItems.map((virtualItem) => {
            const issue = issues[virtualItem.index];
            /* v8 ignore next 3 */
            if (!issue) {
              return null;
            }
            return (
              <VirtualCardWrapper
                key={issue.key}
                start={virtualItem.start}
                virtualIndex={virtualItem.index}
                measureElement={virtualizer.measureElement}
              >
                <BoardCard
                  issue={issue}
                  stateGroup={state.group}
                  onOpenPeek={onOpenPeek}
                  onKeyboardMove={onKeyboardMove}
                  isDragging={draggingKey === issue.key}
                  dropEdge={dropTargetKey === issue.key ? dropEdge : null}
                  canCancelGate={canCancelGate}
                  onCancelGate={onCancelGate}
                  onJumpToComment={onJumpToComment}
                />
              </VirtualCardWrapper>
            );
          })}
        </div>
      </div>

      <footer className="board-column-footer">
        <button
          type="button"
          className="board-new-item-btn"
          onClick={() => onNewItem?.(state.id)}
          data-testid={`new-item-${state.id}`}
        >
          <span>+</span> New work item
        </button>
      </footer>
    </section>
  );
}
