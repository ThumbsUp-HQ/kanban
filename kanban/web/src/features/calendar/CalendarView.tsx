import React, {
  useState,
  useMemo,
  type JSX,
  type DragEvent,
  type KeyboardEvent,
} from 'react';
import { EmojiHint } from '../../components/emoji/EmojiHint';
import type { ViewComponentProps } from '../views/viewRegistry';
import type { IssueItem } from '../views/viewsApi';
import {
  buildTwoWeekGrid,
  addDays,
  diffDays,
  dateToEpochDays,
  epochDaysToDate,
  type CalendarDayCell,
} from './calendarGrid';
import { useRescheduleIssue } from '../timeline/scheduleMutation';
import '../timeline/calendarTimeline.css';

export interface CalendarViewProps extends ViewComponentProps {
  initialYear?: number;
  initialMonth?: number;
  today?: string;
}

const WEEKDAY_NAMES = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];

export function CalendarView({
  issues,
  initialYear,
  initialMonth,
  today,
  onOpenPeek,
}: CalendarViewProps): JSX.Element {
  const todayDate = useMemo(() => {
    return today ?? new Date().toISOString().slice(0, 10);
  }, [today]);

  // Determine initial anchor date for the 2-week view
  const defaultAnchorDate = useMemo(() => {
    if (today) return today;
    if (initialYear && initialMonth) {
      return `${String(initialYear)}-${String(initialMonth).padStart(2, '0')}-01`;
    }
    const firstDue = issues.find((i: IssueItem) => Boolean(i.due_date))?.due_date;
    if (firstDue) return firstDue;
    return new Date().toISOString().slice(0, 10);
  }, [initialYear, initialMonth, issues, today]);

  const [anchorDate, setAnchorDate] = useState<string>(defaultAnchorDate);
  const [scheduleError, setScheduleError] = useState<string | null>(null);
  const [isUnscheduledOpen, setIsUnscheduledOpen] = useState<boolean>(false);
  const [popoverDate, setPopoverDate] = useState<string | null>(null);
  const [draggedKey, setDraggedKey] = useState<string | null>(null);
  const [dragOverDate, setDragOverDate] = useState<string | null>(null);
  const [mobileSelectedDate, setMobileSelectedDate] = useState<string>(todayDate);
  const [scheduleOverrides, setScheduleOverrides] = useState<
    Record<string, { start_date: string | null; due_date: string | null }>
  >({});

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

  // Group issues by due_date
  const { issuesByDate, unscheduledIssues } = useMemo(() => {
    const byDate: Record<string, IssueItem[]> = {};
    const unscheduled: IssueItem[] = [];

    for (const issue of effIssues) {
      if (!issue.due_date) {
        unscheduled.push(issue);
      } else {
        const d = issue.due_date;
        const list = byDate[d] ?? [];
        list.push(issue);
        byDate[d] = list;
      }
    }
    return { issuesByDate: byDate, unscheduledIssues: unscheduled };
  }, [effIssues]);

  const twoWeekGrid = useMemo(() => {
    return buildTwoWeekGrid(anchorDate, todayDate);
  }, [anchorDate, todayDate]);

  const rangeStart = twoWeekGrid[0]?.date ?? anchorDate;
  const rangeEnd = twoWeekGrid[13]?.date ?? anchorDate;
  const rangeLabel = `${rangeStart} - ${rangeEnd}`;

  // Mobile week strip: compute 7 days around mobileSelectedDate
  const mobileWeekDays = useMemo(() => {
    const selectedEpoch = dateToEpochDays(mobileSelectedDate);
    // Find Sunday of this week
    const dateObj = new Date(mobileSelectedDate + 'T00:00:00Z');
    const dayOfWeek = dateObj.getUTCDay(); // 0=Sun, 1=Mon, ...
    const sundayEpoch = selectedEpoch - dayOfWeek;

    const days: { date: string; dayName: string; dayNum: number }[] = [];
    for (let i = 0; i < 7; i++) {
      const d = epochDaysToDate(sundayEpoch + i);
      const dayNum = parseInt(d.slice(8, 10), 10);
      days.push({
        date: d,
        dayName: WEEKDAY_NAMES[i] ?? '',
        dayNum,
      });
    }
    return days;
  }, [mobileSelectedDate]);

  // 2-week navigation handlers
  const handlePrev = () => {
    setAnchorDate(addDays(rangeStart, -14));
    setPopoverDate(null);
  };

  const handleNext = () => {
    setAnchorDate(addDays(rangeStart, 14));
    setPopoverDate(null);
  };

  const handleToday = () => {
    setAnchorDate(todayDate);
    setMobileSelectedDate(todayDate);
    setPopoverDate(null);
  };

  // Reschedule handler enforcing S7.2 8e (due_date >= start_date)
  const applyReschedule = (issueKey: string, targetDate: string) => {
    const issue = effIssues.find((i: IssueItem) => i.key === issueKey);
    if (!issue) return;

    let newStartDate = issue.start_date;
    if (issue.start_date && issue.due_date) {
      // Shift start date by the same delta when moving a scheduled range
      const duration = diffDays(issue.due_date, issue.start_date);
      const targetEpoch = dateToEpochDays(targetDate);
      const startEpoch = targetEpoch - duration;
      newStartDate = epochDaysToDate(startEpoch);
    } else if (issue.start_date && issue.start_date > targetDate) {
      // Clamp start_date = new_due_date so due_date >= start_date is never violated
      newStartDate = targetDate;
    }

    void reschedule({
      issueRef: issue.key,
      dueDate: targetDate,
      startDate: newStartDate,
      originalStartDate: issue.start_date ?? null,
      originalDueDate: issue.due_date ?? null,
    });
  };

  // Drag and drop handlers
  const handleDragStart = (e: DragEvent<HTMLElement>, key: string) => {
    e.dataTransfer.setData('text/plain', key);
    e.dataTransfer.effectAllowed = 'move';
    setDraggedKey(key);
  };

  const handleDragOver = (e: DragEvent<HTMLElement>, date: string) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    if (dragOverDate !== date) {
      setDragOverDate(date);
    }
  };

  const handleDragLeave = (_e: DragEvent<HTMLElement>, date: string) => {
    if (dragOverDate === date) {
      setDragOverDate(null);
    }
  };

  const handleDrop = (e: DragEvent<HTMLElement>, targetDate: string) => {
    e.preventDefault();
    const droppedKey = e.dataTransfer.getData('text/plain') || draggedKey;
    setDraggedKey(null);
    setDragOverDate(null);

    if (droppedKey) {
      applyReschedule(droppedKey, targetDate);
    }
  };

  // Keyboard navigation on issue pills (Alt+ArrowLeft/Right/Up/Down)
  const handlePillKeyDown = (
    e: KeyboardEvent<HTMLAnchorElement>,
    issue: IssueItem,
    currentDate: string
  ) => {
    if (!e.altKey) return;

    let delta = 0;
    if (e.key === 'ArrowLeft') delta = -1;
    else if (e.key === 'ArrowRight') delta = 1;
    else if (e.key === 'ArrowUp') delta = -7;
    else if (e.key === 'ArrowDown') delta = 7;

    if (delta !== 0) {
      e.preventDefault();
      const nextDate = addDays(currentDate, delta);
      applyReschedule(issue.key, nextDate);
    }
  };

  // Priority helper
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
    <div className="calendar-view" data-testid="calendar-view">
      {/* Calendar Toolbar */}
      <div className="calendar-toolbar" role="toolbar" aria-label="Calendar navigation">
        <div className="calendar-toolbar-left">
          <button
            type="button"
            className="calendar-toolbar-btn"
            onClick={handlePrev}
            aria-label="Previous 2 weeks"
          >
            Prev
          </button>
          <button
            type="button"
            className="calendar-toolbar-btn"
            onClick={handleToday}
            aria-label="Jump to today"
          >
            Today
          </button>
          <button
            type="button"
            className="calendar-toolbar-btn"
            onClick={handleNext}
            aria-label="Next 2 weeks"
          >
            Next
          </button>
          <span className="calendar-month-heading" aria-live="polite">
            {rangeLabel}
          </span>
        </div>

        <div className="calendar-toolbar-right">
          <button
            type="button"
            className="calendar-toolbar-btn calendar-unscheduled-toggle"
            onClick={() => { setIsUnscheduledOpen((open) => !open); }}
            aria-expanded={isUnscheduledOpen}
            data-testid="calendar-unscheduled-toggle"
          >
            Unscheduled ({unscheduledIssues.length})
          </button>
        </div>
      </div>

      {scheduleError && (
        <div className="calendar-error-banner" role="alert" data-testid="calendar-error-banner">
          {scheduleError}
        </div>
      )}

      {announcement && (
        <div className="calendar-live-announcement sr-only" role="status" aria-live="polite">
          {announcement}
        </div>
      )}

      {/* 7-column 2-Week Grid (14 Day Cells, Desktop & Tablet) */}
      <div className="calendar-month-grid" role="grid" aria-label={`2-week grid for ${rangeLabel}`}>
        {/* Weekday headers */}
        <div className="calendar-weekday-headers-row" role="row" aria-rowindex={1}>
          {WEEKDAY_NAMES.map((name, colIdx) => (
            <div
              key={name}
              className="calendar-weekday-header"
              role="columnheader"
              aria-colindex={colIdx + 1}
            >
              {name}
            </div>
          ))}
        </div>

        {/* 14 Day cells */}
        {twoWeekGrid.map((cell: CalendarDayCell, idx: number) => {
          const colIdx = idx % 7;
          const rowIdx = Math.floor(idx / 7) + 2;
          const cellIssues = issuesByDate[cell.date] ?? [];
          const visibleIssues = cellIssues.slice(0, 3);
          const hiddenCount = cellIssues.length - 3;
          const isToday = cell.date === todayDate;
          const isDragOver = dragOverDate === cell.date;

          let cellClassName = 'calendar-day-cell';
          if (!cell.isCurrentMonth) cellClassName += ' calendar-day-cell--outside';
          if (isToday) cellClassName += ' calendar-day-cell--today';
          if (isDragOver) cellClassName += ' calendar-day-cell--drag-over';

          return (
            <div
              key={cell.date}
              className={cellClassName}
              role="gridcell"
              aria-rowindex={rowIdx}
              aria-colindex={colIdx + 1}
              tabIndex={idx === 0 ? 0 : -1}
              data-date={cell.date}
              onDragOver={(e) => { handleDragOver(e, cell.date); }}
              onDragLeave={(e) => { handleDragLeave(e, cell.date); }}
              onDrop={(e) => { handleDrop(e, cell.date); }}
            >
              <div className="calendar-day-header">
                <span className="calendar-day-number">{cell.dayOfMonth}</span>
                {isToday && <span className="calendar-today-badge">Today</span>}
              </div>

              <div className="calendar-pills-container">
                {visibleIssues.map((issue) => {
                  const isTerminal =
                    issue.state.group === 'completed' || issue.state.group === 'cancelled';
                  const isOverdue = Boolean(
                    issue.due_date && issue.due_date < todayDate && !isTerminal
                  );

                  let pillClass = 'calendar-issue-pill';
                  if (isOverdue) pillClass += ' calendar-issue-pill--overdue';

                  const priorityKind = getPriorityKind(issue.priority.slug);

                  return (
                    <a
                      key={issue.key}
                      href={`?layout=calendar&peek=${encodeURIComponent(issue.key)}`}
                      className={pillClass}
                      draggable
                      onDragStart={(e) => { handleDragStart(e, issue.key); }}
                      onKeyDown={(e) => { handlePillKeyDown(e, issue, cell.date); }}
                      onClick={(e) => {
                        if (onOpenPeek) {
                          e.preventDefault();
                          onOpenPeek(issue.key);
                        }
                      }}
                      title={`${issue.key}: ${issue.summary}`}
                      data-issue-key={issue.key}
                      data-testid={`calendar-pill-${issue.key}`}
                    >
                      <span className="calendar-issue-pill-key">{issue.key}</span>
                      <EmojiHint kind={priorityKind} testId={`hint-${issue.key}`} />
                      <span className="calendar-issue-pill-summary">{issue.summary}</span>
                    </a>
                  );
                })}

                {hiddenCount > 0 && (
                  <button
                    type="button"
                    className="calendar-more-btn"
                    onClick={() => { setPopoverDate(popoverDate === cell.date ? null : cell.date); }}
                    aria-haspopup="dialog"
                    aria-expanded={popoverDate === cell.date}
                    data-testid={`calendar-more-${cell.date}`}
                  >
                    +{hiddenCount} more
                  </button>
                )}
              </div>

              {/* Overflow Popover */}
              {popoverDate === cell.date && (
                <div
                  className="calendar-more-popover"
                  role="dialog"
                  aria-label={`Issues on ${cell.date}`}
                >
                  <div className="calendar-more-popover-header">
                    <span>{cell.date}</span>
                    <button
                      type="button"
                      className="calendar-more-popover-close"
                      onClick={() => { setPopoverDate(null); }}
                      aria-label="Close overflow popover"
                    >
                      &times;
                    </button>
                  </div>
                  {cellIssues.map((issue) => {
                    const isTerminal =
                      issue.state.group === 'completed' || issue.state.group === 'cancelled';
                    const isOverdue = Boolean(
                      issue.due_date && issue.due_date < todayDate && !isTerminal
                    );

                    let pillClass = 'calendar-issue-pill';
                    if (isOverdue) pillClass += ' calendar-issue-pill--overdue';

                    const priorityKind = getPriorityKind(issue.priority.slug);

                    return (
                      <a
                        key={issue.key}
                        href={`?layout=calendar&peek=${encodeURIComponent(issue.key)}`}
                        className={pillClass}
                        draggable
                        onDragStart={(e) => { handleDragStart(e, issue.key); }}
                        onClick={(e) => {
                          if (onOpenPeek) {
                            e.preventDefault();
                            onOpenPeek(issue.key);
                          }
                        }}
                        data-issue-key={issue.key}
                      >
                        <span className="calendar-issue-pill-key">{issue.key}</span>
                        <EmojiHint kind={priorityKind} />
                        <span className="calendar-issue-pill-summary">{issue.summary}</span>
                      </a>
                    );
                  })}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Mobile Week Strip & Agenda (<= 767px) */}
      <div className="calendar-mobile-agenda" data-testid="calendar-mobile-agenda">
        <div className="calendar-week-strip" role="tablist" aria-label="Week days">
          {mobileWeekDays.map((d) => {
            const isSelected = d.date === mobileSelectedDate;
            let btnClass = 'calendar-week-day-btn';
            if (isSelected) btnClass += ' calendar-week-day-btn--selected';

            return (
              <button
                key={d.date}
                type="button"
                className={btnClass}
                role="tab"
                aria-selected={isSelected}
                onClick={() => { setMobileSelectedDate(d.date); }}
                data-date={d.date}
              >
                <span className="calendar-week-day-name">{d.dayName}</span>
                <span className="calendar-week-day-num">{d.dayNum}</span>
              </button>
            );
          })}
        </div>

        <div
          className="calendar-agenda-list"
          role="region"
          aria-label={`Agenda for ${mobileSelectedDate}`}
        >
          {(issuesByDate[mobileSelectedDate] ?? []).map((issue) => {
            const isTerminal =
              issue.state.group === 'completed' || issue.state.group === 'cancelled';
            const isOverdue = !isTerminal && String(issue.due_date) < todayDate;

            let rowClass = 'calendar-agenda-row';
            if (isOverdue) rowClass += ' calendar-agenda-row--overdue';

            const priorityKind = getPriorityKind(issue.priority.slug);

            return (
              <a
                key={issue.key}
                href={`?layout=calendar&peek=${encodeURIComponent(issue.key)}`}
                className={rowClass}
                data-testid={`agenda-row-${issue.key}`}
                onClick={(e) => {
                  if (onOpenPeek) {
                    e.preventDefault();
                    onOpenPeek(issue.key);
                  }
                }}
              >
                <span className="calendar-issue-pill-key">{issue.key}</span>
                <EmojiHint kind={priorityKind} />
                <span className="calendar-issue-pill-summary">{issue.summary}</span>
              </a>
            );
          })}
          {(issuesByDate[mobileSelectedDate] ?? []).length === 0 && (
            <div className="calendar-agenda-row calendar-agenda-empty">
              No issues scheduled for this date
            </div>
          )}
        </div>
      </div>

      {/* Unscheduled Issues Drawer */}
      {isUnscheduledOpen && (
        <div
          className="calendar-unscheduled-tray"
          data-testid="calendar-unscheduled-tray"
          role="region"
          aria-label="Unscheduled issues"
        >
          <div className="calendar-unscheduled-header">
            <span className="calendar-unscheduled-title">
              Unscheduled Issues ({unscheduledIssues.length})
            </span>
            <button
              type="button"
              className="calendar-toolbar-btn"
              onClick={() => { setIsUnscheduledOpen(false); }}
              aria-label="Close unscheduled tray"
            >
              Close
            </button>
          </div>
          <div className="calendar-unscheduled-list">
            {unscheduledIssues.map((issue) => {
              const priorityKind = getPriorityKind(issue.priority.slug);
              return (
                <div
                  key={issue.key}
                  className="calendar-issue-pill"
                  draggable
                  onDragStart={(e) => { handleDragStart(e, issue.key); }}
                  data-issue-key={issue.key}
                  data-testid={`unscheduled-pill-${issue.key}`}
                >
                  <span className="calendar-issue-pill-key">{issue.key}</span>
                  <EmojiHint kind={priorityKind} />
                  <span className="calendar-issue-pill-summary">{issue.summary}</span>
                </div>
              );
            })}
            {unscheduledIssues.length === 0 && <span>No unscheduled issues.</span>}
          </div>
        </div>
      )}
    </div>
  );
}
