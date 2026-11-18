/**
 * Timezone-safe calendar date calculations and month matrix builder (KB-P3-39, S6.4 item 2, S12.2).
 * Operates strictly on integer UTC epoch days to eliminate browser timezone off-by-one drift.
 */

export interface CalendarDayCell {
  date: string; // ISO "YYYY-MM-DD"
  dayOfMonth: number;
  isCurrentMonth: boolean;
  isToday: boolean;
}

export type CalendarCell = CalendarDayCell;

export interface CalendarMonthMatrix {
  year: number;
  month: number; // 1-12
  weeks: CalendarDayCell[][]; // exactly 6 weeks (42 cells)
}

const MS_PER_DAY = 86_400_000;

/**
 * Returns integer epoch days from an ISO "YYYY-MM-DD" string.
 */
export function dateToEpochDays(dateStr: string): number {
  const parts = dateStr ? dateStr.split('-') : [];
  const y = Number.parseInt(parts[0] ?? '1970', 10);
  const m = Number.parseInt(parts[1] ?? '01', 10);
  const d = Number.parseInt(parts[2] ?? '01', 10);
  return Math.floor(Date.UTC(y, m - 1, d) / MS_PER_DAY);
}

/**
 * Converts integer epoch days back to an ISO "YYYY-MM-DD" string.
 */
export function epochDaysToDate(epochDays: number): string {
  const dt = new Date(epochDays * MS_PER_DAY);
  const y = dt.getUTCFullYear();
  const m = String(dt.getUTCMonth() + 1).padStart(2, '0');
  const d = String(dt.getUTCDate()).padStart(2, '0');
  return `${String(y)}-${m}-${d}`;
}

/**
 * Adds integer days to an ISO date string.
 */
export function addDays(dateStr: string, days: number): string {
  return epochDaysToDate(dateToEpochDays(dateStr) + days);
}

/**
 * Computes dateA - dateB in days.
 */
export function diffDays(dateA: string, dateB: string): number {
  return dateToEpochDays(dateA) - dateToEpochDays(dateB);
}

/**
 * Formats a Year and Month (1-12) to human-readable Month YYYY in English.
 */
export function formatMonthYear(year: number, month: number): string {
  const dt = new Date(Date.UTC(year, month - 1, 1));
  return dt.toLocaleDateString('en-US', {
    month: 'long',
    year: 'numeric',
    timeZone: 'UTC',
  });
}

/**
 * Returns today's date formatted as ISO "YYYY-MM-DD" using UTC.
 */
export function getUtcTodayDate(): string {
  const now = new Date();
  const y = now.getUTCFullYear();
  const m = String(now.getUTCMonth() + 1).padStart(2, '0');
  const d = String(now.getUTCDate()).padStart(2, '0');
  return `${String(y)}-${m}-${d}`;
}

/**
 * Builds an exact 14-day (2 weeks x 7 columns) grid starting on Sunday of anchorDate's week.
 */
export function buildTwoWeekGrid(
  anchorDate: string,
  todayDate: string = getUtcTodayDate(),
): CalendarDayCell[] {
  const dt = new Date(anchorDate + 'T00:00:00Z');
  const dayOfWeek = isNaN(dt.getTime()) ? 0 : dt.getUTCDay();
  const anchorEpoch = isNaN(dt.getTime())
    ? Math.floor(Date.now() / MS_PER_DAY)
    : Math.floor(dt.getTime() / MS_PER_DAY);
  const startEpoch = anchorEpoch - dayOfWeek;

  const cells: CalendarDayCell[] = [];
  for (let i = 0; i < 14; i += 1) {
    const cellDt = new Date((startEpoch + i) * MS_PER_DAY);
    const cellYear = cellDt.getUTCFullYear();
    const cellMonth = cellDt.getUTCMonth() + 1;
    const cellDay = cellDt.getUTCDate();
    const dateStr = `${String(cellYear)}-${String(cellMonth).padStart(2, '0')}-${String(cellDay).padStart(2, '0')}`;

    cells.push({
      date: dateStr,
      dayOfMonth: cellDay,
      isCurrentMonth: true,
      isToday: dateStr === todayDate,
    });
  }

  return cells;
}

/**
 * Builds an exact 42-day (6 weeks x 7 columns) month grid starting on Sunday.
 */
export function buildMonthGrid(
  year: number,
  month: number,
  todayDate: string = getUtcTodayDate(),
): CalendarMonthMatrix {
  // First day of target month in UTC
  const firstDayDt = new Date(Date.UTC(year, month - 1, 1));
  const firstDayEpoch = Math.floor(firstDayDt.getTime() / MS_PER_DAY);
  const startDayOfWeek = firstDayDt.getUTCDay(); // 0 = Sunday, 1 = Monday, ...

  // Starting Sunday epoch days
  const gridStartEpoch = firstDayEpoch - startDayOfWeek;

  const weeks: CalendarDayCell[][] = [];
  let currentEpoch = gridStartEpoch;

  for (let w = 0; w < 6; w += 1) {
    const week: CalendarDayCell[] = [];
    for (let d = 0; d < 7; d += 1) {
      const dt = new Date(currentEpoch * MS_PER_DAY);
      const cellYear = dt.getUTCFullYear();
      const cellMonth = dt.getUTCMonth() + 1;
      const cellDay = dt.getUTCDate();
      const dateStr = `${String(cellYear)}-${String(cellMonth).padStart(2, '0')}-${String(cellDay).padStart(2, '0')}`;

      week.push({
        date: dateStr,
        dayOfMonth: cellDay,
        isCurrentMonth: cellYear === year && cellMonth === month,
        isToday: dateStr === todayDate,
      });

      currentEpoch += 1;
    }
    weeks.push(week);
  }

  return {
    year,
    month,
    weeks,
  };
}
