import { describe, it, expect } from 'vitest';
import {
  dateToEpochDays,
  epochDaysToDate,
  addDays,
  diffDays,
  formatMonthYear,
  getUtcTodayDate,
  buildMonthGrid,
  buildTwoWeekGrid,
} from './calendarGrid';

describe('calendarGrid pure date math', () => {
  it('converts ISO dates to integer epoch days and back without timezone drift', () => {
    // 1970-01-01 is epoch day 0
    expect(dateToEpochDays('1970-01-01')).toBe(0);
    expect(epochDaysToDate(0)).toBe('1970-01-01');

    // 2026-11-18
    const epochDays = dateToEpochDays('2026-11-18');
    expect(epochDaysToDate(epochDays)).toBe('2026-11-18');
  });

  it('handles empty or malformed date string fallbacks', () => {
    expect(dateToEpochDays('')).toBeDefined();
    expect(dateToEpochDays('2026')).toBeDefined();
    expect(dateToEpochDays('2026-05')).toBeDefined();
  });

  it('adds days correctly across month and year boundaries and leap days', () => {
    expect(addDays('2026-11-28', 5)).toBe('2026-12-03');
    expect(addDays('2026-12-31', 1)).toBe('2027-01-01');

    // Leap day in 2028 (leap year)
    expect(addDays('2028-02-28', 1)).toBe('2028-02-29');
    expect(addDays('2028-02-28', 2)).toBe('2028-03-01');
  });

  it('computes exact diff in days', () => {
    expect(diffDays('2026-11-18', '2026-11-11')).toBe(7);
    expect(diffDays('2026-11-11', '2026-11-18')).toBe(-7);
    expect(diffDays('2026-11-18', '2026-11-18')).toBe(0);
  });

  it('formats month and year in English', () => {
    expect(formatMonthYear(2026, 11)).toBe('November 2026');
    expect(formatMonthYear(2027, 1)).toBe('January 2027');
  });

  it('returns valid UTC today date', () => {
    const today = getUtcTodayDate();
    expect(today).toMatch(/^\d{4}-\d{2}-\d{2}$/);
  });

  it('builds exact 42-cell matrix for November 2026', () => {
    const matrix = buildMonthGrid(2026, 11, '2026-11-18');
    expect(matrix.year).toBe(2026);
    expect(matrix.month).toBe(11);
    expect(matrix.weeks.length).toBe(6);

    let cellCount = 0;
    let nov18Found = false;

    for (const week of matrix.weeks) {
      expect(week.length).toBe(7);
      for (const cell of week) {
        cellCount += 1;
        if (cell.date === '2026-11-18') {
          nov18Found = true;
          expect(cell.isCurrentMonth).toBe(true);
          expect(cell.isToday).toBe(true);
          expect(cell.dayOfMonth).toBe(18);
        }
      }
    }

    expect(cellCount).toBe(42);
    expect(nov18Found).toBe(true);

    // November 1, 2026 is Sunday, so week 0 cell 0 should be 2026-11-01
    const cell00 = matrix.weeks[0]?.[0];
    expect(cell00?.date).toBe('2026-11-01');
    expect(cell00?.isCurrentMonth).toBe(true);

    // Week 5 (index 4) should have Nov 30 (Monday) and Dec 1 (Tuesday)
    const cell41 = matrix.weeks[4]?.[1];
    expect(cell41?.date).toBe('2026-11-30');
    expect(cell41?.isCurrentMonth).toBe(true);
    const cell42 = matrix.weeks[4]?.[2];
    expect(cell42?.date).toBe('2026-12-01');
    expect(cell42?.isCurrentMonth).toBe(false);
  });

  it('builds grid when month starts on weekday other than Sunday', () => {
    // July 2026 starts on Wednesday (getUTCDay() = 3)
    const matrix = buildMonthGrid(2026, 7);
    const cell00 = matrix.weeks[0]?.[0];
    expect(cell00?.date).toBe('2026-06-28');
    expect(cell00?.isCurrentMonth).toBe(false);
    const cell03 = matrix.weeks[0]?.[3];
    expect(cell03?.date).toBe('2026-07-01');
    expect(cell03?.isCurrentMonth).toBe(true);
  });

  it('builds two-week grid returning 14 continuous days starting on Sunday', () => {
    // 2026-11-18 is Wednesday. Preceding Sunday is 2026-11-15.
    const cells = buildTwoWeekGrid('2026-11-18', '2026-11-18');
    expect(cells).toHaveLength(14);
    expect(cells[0]?.date).toBe('2026-11-15');
    expect(cells[13]?.date).toBe('2026-11-28');

    const todayCell = cells.find((c) => c.date === '2026-11-18');
    expect(todayCell?.isToday).toBe(true);
    expect(todayCell?.dayOfMonth).toBe(18);

    const nonTodayCell = cells.find((c) => c.date === '2026-11-15');
    expect(nonTodayCell?.isToday).toBe(false);
    expect(nonTodayCell?.dayOfMonth).toBe(15);
  });

  it('builds two-week grid with invalid anchorDate falling back to today epoch and day 0', () => {
    const cells = buildTwoWeekGrid('invalid-date');
    expect(cells).toHaveLength(14);
  });
});
