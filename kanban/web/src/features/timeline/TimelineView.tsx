import React, {
  useState,
  useMemo,
  useRef,
  useLayoutEffect,
  type JSX,
  type KeyboardEvent,
  type PointerEvent,
} from 'react';
import { EmojiHint } from '../../components/emoji/EmojiHint';
import type { ViewComponentProps } from '../views/viewRegistry';
import type { IssueItem } from '../views/viewsApi';
import { addDays, diffDays } from '../calendar/calendarGrid';
import {
  ZOOM_PX_PER_DAY,
  LIST_ROW_HEIGHT_PX,
  computeBarGeometry,
  snapPointerDeltaToDays,
  shiftDateRange,
  resizeStartDate,
  resizeDueDate,
  routeBlocksArrow,
  type ZoomScale,
  type BarGeometry,
  type BlocksArrowPath,
  type LinkEndpointInfo,
} from './timelineGeometry';
import { TimelineSvgOverlay } from './TimelineSvgOverlay';
import { useRescheduleIssue } from './scheduleMutation';
import './calendarTimeline.css';

export interface OutboundBlockLink {
  target_key?: string;
  target_id?: string;
  link_state?: string;
  restricted?: boolean;
  label?: string;
}

export interface TimelineIssueItem extends IssueItem {
  outbound_blocks?: OutboundBlockLink[];
  links?: {
    target_key?: string;
    target_id?: string;
    link_type?: string;
    link_state?: string;
    restricted?: boolean;
    label?: string;
  }[];
}

export interface TimelineViewProps extends ViewComponentProps {
  issues: TimelineIssueItem[];
  initialZoom?: ZoomScale;
  initialStartDate?: string;
  today?: string;
  links?: {
    source_key: string;
    target_key: string;
    link_type: string;
    link_state?: string;
    restricted?: boolean;
  }[];
}

interface TimelineBarProps {
  issue: TimelineIssueItem;
  geom: BarGeometry;
  isOverdue: boolean;
  onPointerDownMove: (e: PointerEvent<HTMLDivElement>, issue: TimelineIssueItem) => void;
  onPointerDownResizeLeft: (e: PointerEvent<HTMLDivElement>, issue: TimelineIssueItem) => void;
  onPointerDownResizeRight: (e: PointerEvent<HTMLDivElement>, issue: TimelineIssueItem) => void;
  onKeyDown: (e: KeyboardEvent<HTMLDivElement>, issue: TimelineIssueItem) => void;
}

function TimelineBar({
  issue,
  geom,
  isOverdue,
  onPointerDownMove,
  onPointerDownResizeLeft,
  onPointerDownResizeRight,
  onKeyDown,
}: TimelineBarProps): JSX.Element {
  const barRef = useRef<HTMLDivElement>(null);

  // Strict CSP (S5.4): CSSOM element ref positioning, zero JSX inline style string
  const isSingleDay = geom.startDate === geom.dueDate;
  useLayoutEffect(() => {
    if (barRef.current) {
      const widthVal = isSingleDay ? Math.max(geom.width, 120) : geom.width;
      barRef.current.style.transform = `translate3d(${String(geom.startX)}px, 0, 0)`;
      barRef.current.style.width = `${String(widthVal)}px`;
    }
  }, [geom.startX, geom.width, isSingleDay]);

  let barClass = 'timeline-bar';
  if (isOverdue) barClass += ' timeline-bar--overdue';
  if (isSingleDay) barClass += ' timeline-bar--single-day';

  // Gate EmojiHint mapping
  let gateKind: 'gatePending' | 'gateVetoed' | 'gateApproved' | null = null;
  if (issue.gate_status === 'pending') gateKind = 'gatePending';
  else if (issue.gate_status === 'vetoed') gateKind = 'gateVetoed';
  else if (issue.gate_status === 'approved') gateKind = 'gateApproved';

  return (
    <div
      ref={barRef}
      className={barClass}
      tabIndex={0}
      role="button"
      aria-label={`Schedule for ${issue.key}: from ${geom.startDate} to ${geom.dueDate}`}
      onPointerDown={(e) => { onPointerDownMove(e, issue); }}
      onKeyDown={(e) => { onKeyDown(e, issue); }}
      data-issue-key={issue.key}
      data-testid={`timeline-bar-${issue.key}`}
    >
      <div
        className="timeline-bar-handle-left"
        role="separator"
        aria-label="Resize start date"
        onPointerDown={(e) => {
          e.stopPropagation();
          onPointerDownResizeLeft(e, issue);
        }}
        data-testid={`handle-left-${issue.key}`}
      />
      <div className="timeline-bar-label">
        <span className="timeline-bar-key">{issue.key}</span>
        {gateKind && <EmojiHint kind={gateKind} />}
        <span className="timeline-bar-summary">{issue.summary}</span>
      </div>
      <div
        className="timeline-bar-handle-right"
        role="separator"
        aria-label="Resize due date"
        onPointerDown={(e) => {
          e.stopPropagation();
          onPointerDownResizeRight(e, issue);
        }}
        data-testid={`handle-right-${issue.key}`}
        data-handle="due"
      />
    </div>
  );
}

interface TimelineMilestoneProps {
  issue: TimelineIssueItem;
  geom: BarGeometry;
  isOverdue: boolean;
  onPointerDownMove?: (e: PointerEvent<HTMLDivElement>, issue: TimelineIssueItem) => void;
  onKeyDown: (e: KeyboardEvent<HTMLDivElement>, issue: TimelineIssueItem) => void;
}

function TimelineMilestone({
  issue,
  geom,
  isOverdue,
  onPointerDownMove,
  onKeyDown,
}: TimelineMilestoneProps): JSX.Element {
  const milestoneRef = useRef<HTMLDivElement>(null);

  useLayoutEffect(() => {
    if (milestoneRef.current) {
      milestoneRef.current.style.transform = `translate3d(${String(geom.startX)}px, 0, 0) rotate(45deg)`;
    }
  }, [geom.startX]);

  let milestoneClass = 'timeline-milestone';
  if (isOverdue) milestoneClass += ' timeline-milestone--overdue';

  return (
    <div
      ref={milestoneRef}
      className={milestoneClass}
      tabIndex={0}
      role="button"
      aria-label={`Milestone for ${issue.key} on ${geom.dueDate}`}
      onPointerDown={(e) => { onPointerDownMove?.(e, issue); }}
      onKeyDown={(e) => { onKeyDown(e, issue); }}
      title={`${issue.key} milestone: ${geom.dueDate}`}
      data-issue-key={issue.key}
      data-testid={`timeline-milestone-${issue.key}`}
    />
  );
}

export function TimelineView({
  issues,
  initialZoom = 'week',
  initialStartDate,
  today,
  links,
  onOpenPeek,
}: TimelineViewProps): JSX.Element {
  const todayDate = useMemo(() => {
    return today ?? new Date().toISOString().slice(0, 10);
  }, [today]);

  const [zoomScale, setZoomScale] = useState<ZoomScale>(initialZoom);
  const [showArrows, setShowArrows] = useState<boolean>(true);
  const canvasWrapperRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLDivElement>(null);

  const [scheduleOverrides, setScheduleOverrides] = useState<
    Record<string, { start_date: string | null; due_date: string | null }>
  >({});
  const [scheduleError, setScheduleError] = useState<string | null>(null);

  const { reschedule, announcement } = useRescheduleIssue({
    onOptimisticUpdate: (key, patch) => {
      setScheduleError(null);
      setScheduleOverrides((prev) => ({
        ...prev,
        [key]: {
          start_date: patch.startDate ?? null,
          due_date: patch.dueDate ?? null,
        },
      }));
    },
    onRollback: (key, original) => {
      setScheduleOverrides((prev) => ({
        ...prev,
        [key]: {
          start_date: original.startDate,
          due_date: original.dueDate,
        },
      }));
    },
    onError: (_key, err) => {
      setScheduleError(err.message || 'Failed to reschedule issue');
    },
    onSuccess: () => {
      setScheduleError(null);
    },
  });

  const effIssues = useMemo(() => {
    return issues.map((i) => {
      const o = scheduleOverrides[i.key];
      if (!o) return i;
      return {
        ...i,
        start_date: o.start_date,
        due_date: o.due_date,
      };
    });
  }, [issues, scheduleOverrides]);

  const pxPerDay = ZOOM_PX_PER_DAY[zoomScale];

  // Start of current 2-week window: Sunday of todayDate (or initialStartDate if provided)
  const defaultAnchorStart = useMemo(() => {
    if (initialStartDate) return initialStartDate;
    const dt = new Date(todayDate + 'T00:00:00Z');
    const dayOfWeek = isNaN(dt.getTime()) ? 0 : dt.getUTCDay();
    return addDays(todayDate, -dayOfWeek);
  }, [initialStartDate, todayDate]);

  const [anchorStart, setAnchorStart] = useState<string>(defaultAnchorStart);
  const timelineStartDate = anchorStart;
  const daysCount = 14;

  const canvasWidth = daysCount * pxPerDay;
  const canvasHeight = Math.max(effIssues.length * LIST_ROW_HEIGHT_PX, 400);

  // Set CSS custom property on canvas container for pure CSSOM styling
  useLayoutEffect(() => {
    canvasRef.current?.style.setProperty('width', `${String(canvasWidth)}px`);
  }, [canvasWidth]);

  // Compute geometries for each issue
  const barGeometries = useMemo(() => {
    const map = new Map<string, BarGeometry | null>();
    for (const issue of effIssues) {
      const geom = computeBarGeometry(
        issue.start_date,
        issue.due_date,
        timelineStartDate,
        pxPerDay
      );
      map.set(issue.key, geom);
    }
    return map;
  }, [effIssues, timelineStartDate, pxPerDay]);

  // Compute scale header cells
  const scaleCells = useMemo(() => {
    const cells: { date: string; label: string; isToday: boolean }[] = [];
    for (let i = 0; i < daysCount; i++) {
      const d = addDays(timelineStartDate, i);
      const isToday = d === todayDate;
      const dayNum = d.slice(8, 10);
      let label = dayNum;
      if (zoomScale === 'day') {
        label = d.slice(5); // MM-DD
      } else if (zoomScale === 'quarter') {
        // Grouped headers in quarter mode (16px per cell) so dates never run together
        if (dayNum === '01') {
          const monthNum = parseInt(d.slice(5, 7), 10);
          const monthNames = ['', 'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
          label = monthNames[monthNum] ?? '';
        } else if (parseInt(dayNum, 10) % 7 === 1) {
          label = dayNum;
        } else {
          label = '';
        }
      }
      cells.push({ date: d, label, isToday });
    }
    return cells;
  }, [daysCount, timelineStartDate, todayDate, zoomScale]);

  // Extract BLOCKS arrows and broken-link states
  const { arrows, brokenLinksByIssue } = useMemo(() => {
    const arrowList: BlocksArrowPath[] = [];
    const brokenMap = new Map<string, boolean>();

    const issueIndexMap = new Map<string, number>();
    effIssues.forEach((issue, idx) => {
      issueIndexMap.set(issue.key, idx);
    });

    // Collect edges from issue.outbound_blocks, issue.links, or links prop
    const edges: {
      sourceKey: string;
      targetKey?: string | undefined;
      linkState?: string | undefined;
      isRestricted?: boolean | undefined;
    }[] = [];

    // From links prop
    if (links) {
      for (const l of links) {
        if (l.link_type === 'BLOCKS') {
          edges.push({
            sourceKey: l.source_key,
            targetKey: l.target_key,
            linkState: l.link_state,
            isRestricted: l.restricted,
          });
        }
      }
    }

    // From issue fields
    for (const issue of effIssues) {
      if (issue.outbound_blocks) {
        for (const ob of issue.outbound_blocks) {
          edges.push({
            sourceKey: issue.key,
            targetKey: ob.target_key,
            linkState: ob.link_state,
            isRestricted: ob.restricted,
          });
        }
      }
      if (issue.links) {
        for (const il of issue.links) {
          if (il.link_type === 'BLOCKS') {
            edges.push({
              sourceKey: issue.key,
              targetKey: il.target_key,
              linkState: il.link_state,
              isRestricted: il.restricted,
            });
          }
        }
      }
    }

    for (const edge of edges) {
      if (edge.linkState === 'FLAGGED_INVALID') {
        brokenMap.set(edge.sourceKey, true);
      }

      // Security invariant: restricted targets render zero arrow paths and leak no id/key
      if (edge.isRestricted || !edge.targetKey) {
        continue;
      }

      if (arrowList.length >= 200) {
        break;
      }

      const sourceIdx = issueIndexMap.get(edge.sourceKey);
      const targetIdx = issueIndexMap.get(edge.targetKey);

      if (sourceIdx !== undefined && targetIdx !== undefined) {
        const sourceGeom = barGeometries.get(edge.sourceKey);
        const targetGeom = barGeometries.get(edge.targetKey);

        if (sourceGeom && targetGeom) {
          const sourceEndpoint: LinkEndpointInfo = {
            key: edge.sourceKey,
            rowIndex: sourceIdx,
            barGeometry: sourceGeom,
          };
          const targetEndpoint: LinkEndpointInfo = {
            key: edge.targetKey,
            rowIndex: targetIdx,
            barGeometry: targetGeom,
          };

          const arrow = routeBlocksArrow(sourceEndpoint, targetEndpoint, edge.linkState);
          if (arrow) {
            arrowList.push(arrow);
          }
        }
      }
    }

    return { arrows: arrowList, brokenLinksByIssue: brokenMap };
  }, [effIssues, links, barGeometries]);

  // Pointer drag/resize logic
  const handlePointerDown = (
    e: PointerEvent<HTMLDivElement>,
    mode: 'move' | 'resize-start' | 'resize-due',
    issue: TimelineIssueItem
  ) => {
    const startX = e.clientX;
    const initialStart = issue.start_date ?? String(issue.due_date);
    const initialDue = issue.due_date ?? String(issue.start_date);

    const onPointerMove = () => {
      // Visual feedback can be updated here if needed
    };

    const onPointerUp = (upEvent: globalThis.PointerEvent) => {
      window.removeEventListener('pointermove', onPointerMove);
      window.removeEventListener('pointerup', onPointerUp);

      const deltaPx = upEvent.clientX - startX;
      const deltaDays = snapPointerDeltaToDays(deltaPx, pxPerDay);

      if (deltaDays === 0) return;

      if (mode === 'move') {
        const shifted = shiftDateRange(initialStart, initialDue, deltaDays);
        void reschedule({
          issueRef: issue.key,
          startDate: shifted.startDate,
          dueDate: shifted.dueDate,
          originalStartDate: initialStart,
          originalDueDate: initialDue,
        });
      } else if (mode === 'resize-start') {
        const newStart = resizeStartDate(initialStart, initialDue, deltaDays);
        void reschedule({
          issueRef: issue.key,
          startDate: newStart,
          dueDate: initialDue,
          originalStartDate: initialStart,
          originalDueDate: initialDue,
        });
      } else {
        const newDue = resizeDueDate(initialStart, initialDue, deltaDays);
        void reschedule({
          issueRef: issue.key,
          startDate: initialStart,
          dueDate: newDue,
          originalStartDate: initialStart,
          originalDueDate: initialDue,
        });
      }
    };

    window.addEventListener('pointermove', onPointerMove);
    window.addEventListener('pointerup', onPointerUp);
  };

  // Keyboard navigation on focused bar
  const handleBarKeyDown = (e: KeyboardEvent<HTMLDivElement>, issue: TimelineIssueItem) => {
    const currentStart = issue.start_date ?? String(issue.due_date);
    const currentDue = issue.due_date ?? String(issue.start_date);

    if (e.shiftKey) {
      // Extend or shrink due date
      let delta = 0;
      if (e.key === 'ArrowLeft') delta = -1;
      else if (e.key === 'ArrowRight') delta = 1;

      if (delta !== 0) {
        e.preventDefault();
        const newDue = resizeDueDate(currentStart, currentDue, delta);
        void reschedule({
          issueRef: issue.key,
          startDate: currentStart,
          dueDate: newDue,
          originalStartDate: currentStart,
          originalDueDate: currentDue,
        });
      }
    } else {
      // Shift range
      let delta = 0;
      if (e.key === 'ArrowLeft') delta = -1;
      else if (e.key === 'ArrowRight') delta = 1;

      if (delta !== 0) {
        e.preventDefault();
        const shifted = shiftDateRange(currentStart, currentDue, delta);
        void reschedule({
          issueRef: issue.key,
          startDate: shifted.startDate,
          dueDate: shifted.dueDate,
          originalStartDate: currentStart,
          originalDueDate: currentDue,
        });
      }
    }
  };

  // Click on unscheduled track row to schedule
  const handleTrackRowClick = (
    e: React.MouseEvent<HTMLDivElement>,
    issue: TimelineIssueItem
  ) => {
    if (issue.start_date || issue.due_date) return;
    const rect = e.currentTarget.getBoundingClientRect();
    const clickX = e.clientX - rect.left;
    const offsetDays = Math.floor(clickX / pxPerDay);
    const clickedDate = addDays(timelineStartDate, offsetDays);

    void reschedule({
      issueRef: issue.key,
      startDate: clickedDate,
      dueDate: clickedDate,
      originalStartDate: null,
      originalDueDate: null,
    });
  };

  // Scroll to today button
  const handleScrollToToday = () => {
    const todayOffset = diffDays(todayDate, timelineStartDate);
    const targetX = Math.max(0, todayOffset * pxPerDay - 200);
    const el = canvasWrapperRef.current;
    if (el) {
      if (typeof el.scrollTo === 'function') {
        el.scrollTo({
          left: targetX,
          behavior: 'smooth',
        });
      } else {
        el.scrollLeft = targetX;
      }
    }
  };

  const getPriorityKind = (
    pSlug: string
  ): 'priorityUrgent' | 'priorityHigh' | 'priorityMedium' | 'priorityLow' => {
    const slug = pSlug.toLowerCase();
    if (slug === 'urgent') return 'priorityUrgent';
    if (slug === 'high') return 'priorityHigh';
    if (slug === 'low') return 'priorityLow';
    return 'priorityMedium';
  };

  return (
    <div className="timeline-view" data-testid="timeline-view">
      {/* Timeline Toolbar */}
      <div className="timeline-toolbar" role="toolbar" aria-label="Timeline navigation">
        <div className="timeline-toolbar-left">
          <button
            type="button"
            className="calendar-toolbar-btn"
            onClick={() => {
              setAnchorStart((prev) => addDays(prev, -14));
            }}
            aria-label="Previous 2 weeks"
          >
            Prev
          </button>
          <button
            type="button"
            className="calendar-toolbar-btn"
            onClick={() => {
              const dt = new Date(todayDate + 'T00:00:00Z');
              const dayOfWeek = isNaN(dt.getTime()) ? 0 : dt.getUTCDay();
              setAnchorStart(addDays(todayDate, -dayOfWeek));
              handleScrollToToday();
            }}
            aria-label="Today"
          >
            Today
          </button>
          <button
            type="button"
            className="calendar-toolbar-btn"
            onClick={() => {
              setAnchorStart((prev) => addDays(prev, 14));
            }}
            aria-label="Next 2 weeks"
          >
            Next
          </button>
          <span className="timeline-range-heading" aria-live="polite">
            {`${anchorStart} - ${addDays(anchorStart, 13)}`}
          </span>

          <div
            className="timeline-zoom-group"
            role="radiogroup"
            aria-label="Timeline zoom scale"
          >
            <button
              type="button"
              className={`timeline-zoom-btn ${zoomScale === 'day' ? 'timeline-zoom-btn--active' : ''}`}
              role="radio"
              aria-checked={zoomScale === 'day'}
              onClick={() => { setZoomScale('day'); }}
            >
              Day
            </button>
            <button
              type="button"
              className={`timeline-zoom-btn ${zoomScale === 'week' ? 'timeline-zoom-btn--active' : ''}`}
              role="radio"
              aria-checked={zoomScale === 'week'}
              onClick={() => { setZoomScale('week'); }}
            >
              Week
            </button>
            <button
              type="button"
              className={`timeline-zoom-btn ${zoomScale === 'quarter' ? 'timeline-zoom-btn--active' : ''}`}
              role="radio"
              aria-checked={zoomScale === 'quarter'}
              onClick={() => { setZoomScale('quarter'); }}
            >
              Quarter
            </button>
          </div>
        </div>

        <div className="timeline-toolbar-right">
          <label className="timeline-arrows-toggle">
            <input
              type="checkbox"
              checked={showArrows}
              onChange={(e) => { setShowArrows(e.target.checked); }}
            />
            Show BLOCKS arrows
          </label>
        </div>
      </div>

      {scheduleError && (
        <div className="timeline-error-banner" role="alert" data-testid="timeline-error-banner">
          {scheduleError}
        </div>
      )}

      {/* Split Grid: Left sticky rail + Right canvas */}
      <div className="timeline-split-container">
        {/* Left Sticky Issue Pane (280px desktop, 132px mobile) */}
        <div className="timeline-left-pane" role="region" aria-label="Issue list">
          <div className="timeline-left-header">Work Item</div>
          <div className="timeline-left-rows">
            {effIssues.map((issue) => {
              const priorityKind = getPriorityKind(issue.priority.slug);
              const isBroken = brokenLinksByIssue.get(issue.key);

              return (
                <div
                  key={issue.key}
                  className="timeline-left-row"
                  data-issue-key={issue.key}
                  data-testid={`timeline-left-row-${issue.key}`}
                  onClick={(e) => {
                    const target = e.target as HTMLElement | null;
                    if (target?.closest('a, button, input')) return;
                    onOpenPeek?.(issue.key);
                  }}
                >
                  <EmojiHint kind={priorityKind} />
                  <a
                    href={`?layout=timeline&peek=${encodeURIComponent(issue.key)}`}
                    className="timeline-left-row-key"
                    onClick={(e) => {
                      if (onOpenPeek) {
                        e.preventDefault();
                        onOpenPeek(issue.key);
                      }
                    }}
                  >
                    {issue.key}
                  </a>
                  <span className="timeline-left-row-summary" title={issue.summary}>
                    {issue.summary}
                  </span>
                  {isBroken && (
                    <span className="timeline-broken-link-hint">
                      <EmojiHint
                        kind="brokenLink"
                        testId={`broken-link-${issue.key}`}
                        label="Broken link flagged by auditor"
                      />
                    </span>
                  )}
                </div>
              );
            })}
          </div>
        </div>

        {/* Right Scrollable Timeline Canvas */}
        <div ref={canvasWrapperRef} className="timeline-right-canvas-wrapper">
          <div ref={canvasRef} className={`timeline-right-canvas timeline-right-canvas--${zoomScale}`}>
            {/* Scale Header Row */}
            <div className="timeline-scale-header" role="row">
              {scaleCells.map((c) => (
                <div
                  key={c.date}
                  className={`timeline-scale-cell timeline-scale-cell--${zoomScale} ${c.isToday ? 'timeline-scale-cell--today' : ''}`}
                  role="columnheader"
                  title={c.date}
                  data-date={c.date}
                >
                  {c.label}
                </div>
              ))}
            </div>

            {/* Track Rows */}
            <div className="timeline-track-rows">
              {effIssues.map((issue) => {
                const geom = barGeometries.get(issue.key);
                const isTerminal =
                  issue.state.group === 'completed' || issue.state.group === 'cancelled';
                const isOverdue = Boolean(
                  issue.due_date && issue.due_date < todayDate && !isTerminal
                );

                return (
                  <div
                    key={issue.key}
                    className="timeline-track-row"
                    data-issue-key={issue.key}
                    data-testid={`timeline-track-row-${issue.key}`}
                    onClick={(e) => { handleTrackRowClick(e, issue); }}
                  >
                    {!geom && (
                      <div className="timeline-ghost-prompt">
                        Click track to schedule
                      </div>
                    )}

                    {geom && !geom.isSingleDate && (
                      <TimelineBar
                        issue={issue}
                        geom={geom}
                        isOverdue={isOverdue}
                        onPointerDownMove={(e, iss) => { handlePointerDown(e, 'move', iss); }}
                        onPointerDownResizeLeft={(e, iss) => { handlePointerDown(e, 'resize-start', iss); }
                        }
                        onPointerDownResizeRight={(e, iss) => { handlePointerDown(e, 'resize-due', iss); }
                        }
                        onKeyDown={handleBarKeyDown}
                      />
                    )}

                    {geom && geom.isSingleDate && (
                      <TimelineMilestone
                        issue={issue}
                        geom={geom}
                        isOverdue={isOverdue}
                        onPointerDownMove={(e, iss) => { handlePointerDown(e, 'move', iss); }}
                        onKeyDown={handleBarKeyDown}
                      />
                    )}
                  </div>
                );
              })}

              {/* BLOCKS Dependency Arrows SVG Overlay */}
              {showArrows && arrows.length > 0 && (
                <TimelineSvgOverlay
                  totalWidth={canvasWidth}
                  totalHeight={canvasHeight}
                  arrows={arrows}
                  visible={showArrows}
                />
              )}
            </div>
          </div>
        </div>
      </div>
      {announcement && (
        <div className="timeline-live-announcement sr-only" role="status" aria-live="polite">
          {announcement}
        </div>
      )}
    </div>
  );
}
