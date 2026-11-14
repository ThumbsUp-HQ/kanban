/**
 * Pure timeline / Gantt geometry, scale conversions, and BLOCKS arrow routing (KB-P3-39, S6.4 item 2, S7.2).
 */

import { addDays, diffDays } from '../calendar/calendarGrid';

export type ZoomScale = 'day' | 'week' | 'quarter';

export const ZOOM_PX_PER_DAY: Record<ZoomScale, number> = {
  day: 36,
  week: 16,
  quarter: 6,
};

export const LIST_ROW_HEIGHT_PX = 46;
export const BAR_HEIGHT_PX = 28;
export const MILESTONE_SIZE_PX = 20;

export interface BarGeometry {
  startX: number;
  width: number;
  isSingleDate: boolean;
  startDate: string;
  dueDate: string;
}

export interface BlocksArrowPath {
  sourceKey: string;
  targetKey: string;
  d: string;
  isConflict: boolean;
  isBrokenLink: boolean;
  isRestricted: boolean;
}

/**
 * Computes pixel geometry for an issue's scheduled date range.
 * If both dates are missing, returns null (unscheduled).
 */
export function computeBarGeometry(
  startDate: string | null | undefined,
  dueDate: string | null | undefined,
  timelineStartDate: string,
  pxPerDay: number,
): BarGeometry | null {
  if (!startDate && !dueDate) {
    return null;
  }

  // Single date milestone: start date only
  if (startDate && !dueDate) {
    const offsetDays = diffDays(startDate, timelineStartDate);
    const centerX = offsetDays * pxPerDay + pxPerDay / 2;
    return {
      startX: centerX - MILESTONE_SIZE_PX / 2,
      width: MILESTONE_SIZE_PX,
      isSingleDate: true,
      startDate,
      dueDate: startDate,
    };
  }

  // Single date milestone: due date only
  if (!startDate && dueDate) {
    const offsetDays = diffDays(dueDate, timelineStartDate);
    const centerX = offsetDays * pxPerDay + pxPerDay / 2;
    return {
      startX: centerX - MILESTONE_SIZE_PX / 2,
      width: MILESTONE_SIZE_PX,
      isSingleDate: true,
      startDate: dueDate,
      dueDate,
    };
  }

  // Both dates present: enforce due >= start for rendering
  const effStart = String(startDate);
  const effDueCandidate = String(dueDate);
  const effDue = diffDays(effDueCandidate, effStart) >= 0 ? effDueCandidate : effStart;

  const startOffsetDays = diffDays(effStart, timelineStartDate);
  const totalDaysInclusive = diffDays(effDue, effStart) + 1;

  return {
    startX: startOffsetDays * pxPerDay,
    width: Math.max(totalDaysInclusive * pxPerDay, MILESTONE_SIZE_PX),
    isSingleDate: false,
    startDate: effStart,
    dueDate: effDue,
  };
}

/**
 * Converts a horizontal pixel delta into integer days based on active zoom scale.
 */
export function snapPointerDeltaToDays(deltaPx: number, pxPerDay: number): number {
  return Math.round(deltaPx / pxPerDay);
}

/**
 * Shifts both start_date and due_date by deltaDays.
 */
export function shiftDateRange(
  startDate: string,
  dueDate: string,
  deltaDays: number,
): { startDate: string; dueDate: string } {
  return {
    startDate: addDays(startDate, deltaDays),
    dueDate: addDays(dueDate, deltaDays),
  };
}

/**
 * Adjusts start_date via left handle resize, clamped strictly to <= dueDate (S7.2 8e).
 */
export function resizeStartDate(
  currentStart: string,
  dueDate: string,
  deltaDays: number,
): string {
  const newStart = addDays(currentStart, deltaDays);
  return diffDays(dueDate, newStart) >= 0 ? newStart : dueDate;
}

/**
 * Adjusts due_date via right handle resize, clamped strictly to >= startDate (S7.2 8e).
 */
export function resizeDueDate(
  startDate: string,
  currentDue: string,
  deltaDays: number,
): string {
  const newDue = addDays(currentDue, deltaDays);
  return diffDays(newDue, startDate) >= 0 ? newDue : startDate;
}

/**
 * Normalizes an issue's schedule when moving to a new due date,
 * shifting or clamping start_date if needed so due_date >= start_date always holds.
 */
export function clampNewDueDate(
  existingStart: string | null | undefined,
  existingDue: string | null | undefined,
  newDueDate: string,
): { startDate?: string; dueDate: string } {
  if (!existingStart) {
    return { dueDate: newDueDate };
  }

  if (existingDue) {
    const rangeSpan = diffDays(existingDue, existingStart);
    if (rangeSpan > 0) {
      // Shift range maintaining span
      const newStart = addDays(newDueDate, -rangeSpan);
      return { startDate: newStart, dueDate: newDueDate };
    }
  }

  // Single date or clamp
  if (diffDays(newDueDate, existingStart) < 0) {
    return { startDate: newDueDate, dueDate: newDueDate };
  }

  return { dueDate: newDueDate };
}

export interface LinkEndpointInfo {
  key: string;
  rowIndex: number;
  barGeometry: BarGeometry | null;
  restricted?: boolean;
}

/**
 * Routes orthogonal cubic-bezier SVG arrow from blocker right edge to blocked left edge.
 * Returns null if either endpoint is restricted, unscheduled, or invalid.
 */
export function routeBlocksArrow(
  source: LinkEndpointInfo,
  target: LinkEndpointInfo,
  linkState?: string,
): BlocksArrowPath | null {
  if (source.restricted || target.restricted) {
    return null;
  }

  if (!source.barGeometry || !target.barGeometry) {
    return null;
  }

  const isConflict = diffDays(source.barGeometry.dueDate, target.barGeometry.startDate) > 0;
  const isBrokenLink = linkState === 'FLAGGED_INVALID';

  const x1 = source.barGeometry.startX + source.barGeometry.width;
  const y1 = source.rowIndex * LIST_ROW_HEIGHT_PX + LIST_ROW_HEIGHT_PX / 2;

  const x2 = target.barGeometry.startX;
  const y2 = target.rowIndex * LIST_ROW_HEIGHT_PX + LIST_ROW_HEIGHT_PX / 2;

  let d = '';
  if (x2 >= x1 + 16) {
    // Standard forward curve
    const dx = x2 - x1;
    const midX = x1 + dx / 2;
    d = `M ${String(x1)} ${String(y1)} C ${String(midX)} ${String(y1)}, ${String(midX)} ${String(y2)}, ${String(x2)} ${String(y2)}`;
  } else {
    // Backward loop around rows
    const exitX = x1 + 14;
    const enterX = x2 - 14;
    const midY = (y1 + y2) / 2;
    d = `M ${String(x1)} ${String(y1)} H ${String(exitX)} C ${String(exitX + 16)} ${String(y1)}, ${String(exitX + 16)} ${String(midY)}, ${String(exitX)} ${String(midY)} H ${String(enterX)} C ${String(enterX - 16)} ${String(midY)}, ${String(enterX - 16)} ${String(y2)}, ${String(enterX)} ${String(y2)} H ${String(x2)}`;
  }

  return {
    sourceKey: source.key,
    targetKey: target.key,
    d,
    isConflict,
    isBrokenLink,
    isRestricted: false,
  };
}
