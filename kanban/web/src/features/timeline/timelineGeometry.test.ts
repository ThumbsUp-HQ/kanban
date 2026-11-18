import { describe, expect, it } from 'vitest';
import {
  clampNewDueDate,
  computeBarGeometry,
  resizeDueDate,
  resizeStartDate,
  routeBlocksArrow,
  shiftDateRange,
  snapPointerDeltaToDays,
  ZOOM_PX_PER_DAY,
} from './timelineGeometry';

describe('timelineGeometry', () => {
  it('computes width and startX for 8 inclusive days at 16px/day (128px)', () => {
    // start_date: "2026-11-11" to due_date: "2026-11-18" at 16px/day
    // Timeline base start: "2026-11-01" -> 10 days offset -> 160px
    const geo = computeBarGeometry('2026-11-11', '2026-11-18', '2026-11-01', 16);
    expect(geo).not.toBeNull();
    expect(geo?.startX).toBe(10 * 16); // 160px
    expect(geo?.width).toBe(8 * 16); // 128px (8 inclusive days)
    expect(geo?.isSingleDate).toBe(false);
  });

  it('renders milestone diamond when only one date is present', () => {
    const geoStartOnly = computeBarGeometry('2026-11-15', null, '2026-11-01', 16);
    expect(geoStartOnly).not.toBeNull();
    expect(geoStartOnly?.isSingleDate).toBe(true);
    expect(geoStartOnly?.width).toBe(20);

    const geoDueOnly = computeBarGeometry(null, '2026-11-15', '2026-11-01', 16);
    expect(geoDueOnly).not.toBeNull();
    expect(geoDueOnly?.isSingleDate).toBe(true);
    expect(geoDueOnly?.width).toBe(20);

    // Clamps effective due date to start date when due < start
    const geoInverted = computeBarGeometry('2026-11-20', '2026-11-10', '2026-11-01', 16);
    expect(geoInverted).not.toBeNull();
    expect(geoInverted?.startDate).toBe('2026-11-20');
    expect(geoInverted?.dueDate).toBe('2026-11-20');
  });

  it('returns null when both dates are absent', () => {
    expect(computeBarGeometry(null, null, '2026-11-01', 16)).toBeNull();
    expect(computeBarGeometry(undefined, undefined, '2026-11-01', 16)).toBeNull();
  });

  it('snaps pointer delta to integer days across zoom scales', () => {
    expect(snapPointerDeltaToDays(72, ZOOM_PX_PER_DAY.week)).toBe(2);
    expect(snapPointerDeltaToDays(-36, ZOOM_PX_PER_DAY.week)).toBe(-1);
    expect(snapPointerDeltaToDays(64, ZOOM_PX_PER_DAY.day)).toBe(1);
  });

  it('shifts both dates together on range shift', () => {
    const shifted = shiftDateRange('2026-11-11', '2026-11-18', 2);
    expect(shifted.startDate).toBe('2026-11-13');
    expect(shifted.dueDate).toBe('2026-11-20');
  });

  it('enforces due_date >= start_date during left handle resize clamping', () => {
    // Current start 2026-11-11, due 2026-11-18
    // Dragging right +5 days -> 2026-11-16 (valid)
    expect(resizeStartDate('2026-11-11', '2026-11-18', 5)).toBe('2026-11-16');

    // Dragging right +10 days -> would be 2026-11-21 (> due 2026-11-18), must clamp to due_date
    expect(resizeStartDate('2026-11-11', '2026-11-18', 10)).toBe('2026-11-18');
  });

  it('enforces due_date >= start_date during right handle resize clamping', () => {
    // Current start 2026-11-11, due 2026-11-18
    // Dragging left -3 days -> 2026-11-15 (valid)
    expect(resizeDueDate('2026-11-11', '2026-11-18', -3)).toBe('2026-11-15');

    // Dragging left -10 days -> would be 2026-11-08 (< start 2026-11-11), must clamp to start_date
    expect(resizeDueDate('2026-11-11', '2026-11-18', -10)).toBe('2026-11-11');
  });

  it('clamps or shifts start_date when new due date is assigned', () => {
    // Range with 7 days span moved to Nov 25 -> start shifts to Nov 18
    const shifted = clampNewDueDate('2026-11-11', '2026-11-18', '2026-11-25');
    expect(shifted.startDate).toBe('2026-11-18');
    expect(shifted.dueDate).toBe('2026-11-25');

    // Start only at Nov 15 moved to Nov 10 -> start clamped to Nov 10
    const clamped = clampNewDueDate('2026-11-15', null, '2026-11-10');
    expect(clamped.startDate).toBe('2026-11-10');
    expect(clamped.dueDate).toBe('2026-11-10');
  });

  it('routes BLOCKS arrow path and detects scheduling conflicts', () => {
    // Row 0: KAN-100 (2026-11-05 to 2026-11-12)
    // Row 1: KAN-142 (2026-11-15 to 2026-11-20)
    const geo100 = computeBarGeometry('2026-11-05', '2026-11-12', '2026-11-01', 16);
    const geo142 = computeBarGeometry('2026-11-15', '2026-11-20', '2026-11-01', 16);

    const arrow = routeBlocksArrow(
      { key: 'KAN-100', rowIndex: 0, barGeometry: geo100 },
      { key: 'KAN-142', rowIndex: 1, barGeometry: geo142 },
    );

    expect(arrow).not.toBeNull();
    expect(arrow?.sourceKey).toBe('KAN-100');
    expect(arrow?.targetKey).toBe('KAN-142');
    expect(arrow?.d).toMatch(/^M \d+/);
    expect(arrow?.isConflict).toBe(false);

    // Conflict case: KAN-100 due date (2026-11-16) > KAN-142 start date (2026-11-15)
    const geo100Conflict = computeBarGeometry('2026-11-05', '2026-11-16', '2026-11-01', 16);
    const arrowConflict = routeBlocksArrow(
      { key: 'KAN-100', rowIndex: 0, barGeometry: geo100Conflict },
      { key: 'KAN-142', rowIndex: 1, barGeometry: geo142 },
    );
    expect(arrowConflict?.isConflict).toBe(true);
  });

  it('identifies FLAGGED_INVALID broken link state', () => {
    const geo1 = computeBarGeometry('2026-11-05', '2026-11-10', '2026-11-01', 16);
    const geo2 = computeBarGeometry('2026-11-15', '2026-11-20', '2026-11-01', 16);

    const arrow = routeBlocksArrow(
      { key: 'KAN-100', rowIndex: 0, barGeometry: geo1 },
      { key: 'KAN-142', rowIndex: 1, barGeometry: geo2 },
      'FLAGGED_INVALID',
    );
    expect(arrow?.isBrokenLink).toBe(true);
  });

  it('suppresses path and leaks zero info when endpoint is restricted', () => {
    const geo1 = computeBarGeometry('2026-11-05', '2026-11-10', '2026-11-01', 16);
    const arrow = routeBlocksArrow(
      { key: 'KAN-100', rowIndex: 0, barGeometry: geo1 },
      { key: 'KAN-999', rowIndex: 1, barGeometry: null, restricted: true },
    );
    expect(arrow).toBeNull();
  });

  it('routes backward loop arrow when target X is to the left of source X', () => {
    // Blocker is on 2026-11-20, blocked is on 2026-11-05
    const geo1 = computeBarGeometry('2026-11-15', '2026-11-20', '2026-11-01', 16);
    const geo2 = computeBarGeometry('2026-11-05', '2026-11-10', '2026-11-01', 16);

    const arrow = routeBlocksArrow(
      { key: 'KAN-100', rowIndex: 0, barGeometry: geo1 },
      { key: 'KAN-142', rowIndex: 1, barGeometry: geo2 },
    );
    expect(arrow).not.toBeNull();
    expect(arrow?.d).toContain('H ');
  });

  it('handles computeBarGeometry with start_date only', () => {
    const geo = computeBarGeometry('2026-11-10', null, '2026-11-01', 16);
    expect(geo).not.toBeNull();
    expect(geo?.isSingleDate).toBe(true);
    expect(geo?.startDate).toBe('2026-11-10');
  });

  it('covers all clampNewDueDate edge cases', () => {
    // Single start_date with newDueDate >= existingStart
    const res1 = clampNewDueDate('2026-11-10', null, '2026-11-15');
    expect(res1.dueDate).toBe('2026-11-15');
    expect(res1.startDate).toBeUndefined();

    // Single start_date with newDueDate < existingStart (clamps start_date)
    const res2 = clampNewDueDate('2026-11-10', null, '2026-11-05');
    expect(res2.dueDate).toBe('2026-11-05');
    expect(res2.startDate).toBe('2026-11-05');

    // No existing dates
    const res3 = clampNewDueDate(null, null, '2026-11-15');
    expect(res3.dueDate).toBe('2026-11-15');
    expect(res3.startDate).toBeUndefined();

    // Range span is 0 (start === due)
    const res4 = clampNewDueDate('2026-11-10', '2026-11-10', '2026-11-15');
    expect(res4.dueDate).toBe('2026-11-15');
  });

  it('clamps effDue to effStart when raw dueDate is prior to startDate in computeBarGeometry', () => {
    const geo = computeBarGeometry('2026-11-20', '2026-11-10', '2026-11-01', 16);
    expect(geo).not.toBeNull();
    expect(geo?.dueDate).toBe('2026-11-20');
  });

  it('routeBlocksArrow returns null if either endpoint has null barGeometry', () => {
    const geo = computeBarGeometry('2026-11-10', '2026-11-15', '2026-11-01', 16);
    expect(
      routeBlocksArrow(
        { key: 'KAN-1', rowIndex: 0, barGeometry: null },
        { key: 'KAN-2', rowIndex: 1, barGeometry: geo },
      ),
    ).toBeNull();
    expect(
      routeBlocksArrow(
        { key: 'KAN-1', rowIndex: 0, barGeometry: geo },
        { key: 'KAN-2', rowIndex: 1, barGeometry: null },
      ),
    ).toBeNull();
  });
});
