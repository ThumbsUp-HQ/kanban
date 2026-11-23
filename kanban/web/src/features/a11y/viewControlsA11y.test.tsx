// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import React from 'react';
import { SwimlaneBoardGrid } from '../views/SwimlaneBoardGrid';
import { ListView } from '../list/ListView';
import { TableView } from '../table/TableView';
import { CalendarView } from '../calendar/CalendarView';
import { TimelineView, type TimelineIssueItem } from '../timeline/TimelineView';
import { FIXTURE_12_ISSUES } from '../views/fixtures';

function expectElement<T extends Element = HTMLElement>(
  el: T | null | undefined,
  name = 'element'
): T {
  if (!el) throw new Error(`Expected ${name}`);
  return el;
}

describe('viewControlsA11y (KAN-358: 2D Swimlane, Navigator, Table, Calendar, and Timeline Grid ARIA and Arrow Navigation)', () => {
  let cleanupNav: (() => void) | undefined;

  beforeEach(() => {
    const navHandler = (e: Event): void => {
      e.preventDefault();
    };
    window.addEventListener('click', navHandler, true);
    cleanupNav = () => {
      window.removeEventListener('click', navHandler, true);
    };
  });

  afterEach(() => {
    cleanupNav?.();
  });

  // =========================================================================
  // Required Test Case 1: Positive case — verifies Arrow keys move focus across
  // swimlane cards and list rows
  // =========================================================================
  describe('Test Case 1: Positive Case - Arrow Keys Move Focus Across Swimlane Cards and List Rows', () => {
    it('traverses 2D swimlane cards using ArrowDown, ArrowUp, ArrowRight, ArrowLeft, Home, and End', () => {
      const handleCardClick = vi.fn();

      render(
        <SwimlaneBoardGrid
          issues={FIXTURE_12_ISSUES}
          projectKey="KAN"
          groupBy="state"
          subGroupBy="priority"
          onCardClick={handleCardClick}
        />
      );

      const allCards = document.querySelectorAll<HTMLElement>('.swimlane-card');
      expect(allCards.length).toBeGreaterThanOrEqual(2);

      const firstCard = expectElement(allCards[0], 'firstCard');
      const initialKey = firstCard.getAttribute('data-issue-key') ?? '';
      expect(firstCard.getAttribute('tabindex')).toBe('0');
      expect(firstCard.getAttribute('data-focused')).toBe('true');

      // Focus first card
      act(() => {
        firstCard.focus();
      });
      expect(document.activeElement).toBe(firstCard);

      // Press ArrowDown to navigate to next card in column or lane
      act(() => {
        fireEvent.keyDown(firstCard, { key: 'ArrowDown' });
      });
      const activeAfterDown = document.activeElement as HTMLElement;
      expect(activeAfterDown).not.toBeNull();
      expect(activeAfterDown.classList.contains('swimlane-card')).toBe(true);
      expect(activeAfterDown.getAttribute('tabindex')).toBe('0');
      expect(activeAfterDown.getAttribute('data-focused')).toBe('true');
      expect(firstCard.getAttribute('tabindex')).toBe('-1');

      // Press ArrowUp to navigate back
      act(() => {
        fireEvent.keyDown(activeAfterDown, { key: 'ArrowUp' });
      });
      const activeAfterUp = document.activeElement as HTMLElement;
      expect(activeAfterUp.getAttribute('data-issue-key')).toBe(initialKey);
      expect(activeAfterUp.getAttribute('tabindex')).toBe('0');

      // Press ArrowRight to navigate laterally
      act(() => {
        fireEvent.keyDown(activeAfterUp, { key: 'ArrowRight' });
      });
      const activeAfterRight = document.activeElement as HTMLElement;
      expect(activeAfterRight).not.toBeNull();
      expect(activeAfterRight.getAttribute('tabindex')).toBe('0');

      // Press ArrowLeft to navigate laterally back
      act(() => {
        fireEvent.keyDown(activeAfterRight, { key: 'ArrowLeft' });
      });
      const activeAfterLeft = document.activeElement as HTMLElement;
      expect(activeAfterLeft).not.toBeNull();
      expect(activeAfterLeft.getAttribute('tabindex')).toBe('0');

      // Press End to navigate to the last card
      act(() => {
        fireEvent.keyDown(activeAfterLeft, { key: 'End' });
      });
      const lastCard = document.activeElement as HTMLElement;
      const lastExpectedCard = expectElement(allCards[allCards.length - 1], 'lastExpectedCard');
      expect(lastCard.getAttribute('data-issue-key')).toBe(
        lastExpectedCard.getAttribute('data-issue-key')
      );
      expect(lastCard.getAttribute('tabindex')).toBe('0');

      // Press Home to return to the first card
      act(() => {
        fireEvent.keyDown(lastCard, { key: 'Home' });
      });
      const firstReturned = document.activeElement as HTMLElement;
      expect(firstReturned.getAttribute('data-issue-key')).toBe(initialKey);
      expect(firstReturned.getAttribute('tabindex')).toBe('0');

      // Press Enter on card to trigger click
      act(() => {
        fireEvent.keyDown(firstReturned, { key: 'Enter' });
      });
      expect(handleCardClick).toHaveBeenCalledWith(initialKey, false);
    });

    it('traverses list rows using ArrowDown, ArrowUp, Home, End, and Enter in ListView', () => {
      const handleOpenPeek = vi.fn();

      render(
        <ListView
          issues={FIXTURE_12_ISSUES}
          projectKey="KAN"
          onOpenPeek={handleOpenPeek}
        />
      );

      const rows = document.querySelectorAll<HTMLElement>('.issue-list-card');
      expect(rows.length).toBeGreaterThanOrEqual(3);

      const firstRow = expectElement(rows[0], 'firstRow');
      const secondRow = expectElement(rows[1], 'secondRow');
      const lastRow = expectElement(rows[rows.length - 1], 'lastRow');

      // Initial active row has tabIndex 0
      expect(firstRow.getAttribute('tabindex')).toBe('0');
      expect(secondRow.getAttribute('tabindex')).toBe('-1');

      act(() => {
        firstRow.focus();
      });
      expect(document.activeElement).toBe(firstRow);

      // ArrowDown to move to second row
      act(() => {
        fireEvent.keyDown(firstRow, { key: 'ArrowDown' });
      });
      expect(document.activeElement).toBe(secondRow);
      expect(secondRow.getAttribute('tabindex')).toBe('0');
      expect(firstRow.getAttribute('tabindex')).toBe('-1');

      // ArrowUp to move back to first row
      act(() => {
        fireEvent.keyDown(secondRow, { key: 'ArrowUp' });
      });
      expect(document.activeElement).toBe(firstRow);
      expect(firstRow.getAttribute('tabindex')).toBe('0');
      expect(secondRow.getAttribute('tabindex')).toBe('-1');

      // End key moves to last row
      act(() => {
        fireEvent.keyDown(firstRow, { key: 'End' });
      });
      expect(document.activeElement).toBe(lastRow);
      expect(lastRow.getAttribute('tabindex')).toBe('0');

      // Home key moves back to first row
      act(() => {
        fireEvent.keyDown(lastRow, { key: 'Home' });
      });
      expect(document.activeElement).toBe(firstRow);
      expect(firstRow.getAttribute('tabindex')).toBe('0');

      // Enter key opens peek
      act(() => {
        fireEvent.keyDown(firstRow, { key: 'Enter' });
      });
      expect(handleOpenPeek).toHaveBeenCalledWith(firstRow.getAttribute('data-issue-key'));
    });

    it('traverses table rows using ArrowDown, ArrowUp, Home, End in TableView', () => {
      const handleOpenPeek = vi.fn();

      render(
        <TableView
          issues={FIXTURE_12_ISSUES}
          projectKey="KAN"
          onOpenPeek={handleOpenPeek}
        />
      );

      const rows = document.querySelectorAll<HTMLElement>('tbody.issues-table-body tr[role="row"]');
      expect(rows.length).toBeGreaterThanOrEqual(3);

      const firstRow = expectElement(rows[0], 'firstRow');
      const secondRow = expectElement(rows[1], 'secondRow');
      const lastRow = expectElement(rows[rows.length - 1], 'lastRow');

      expect(firstRow.getAttribute('tabindex')).toBe('0');
      expect(secondRow.getAttribute('tabindex')).toBe('-1');

      act(() => {
        firstRow.focus();
      });
      expect(document.activeElement).toBe(firstRow);

      // ArrowDown moves focus
      act(() => {
        fireEvent.keyDown(firstRow, { key: 'ArrowDown' });
      });
      expect(document.activeElement).toBe(secondRow);
      expect(secondRow.getAttribute('tabindex')).toBe('0');
      expect(firstRow.getAttribute('tabindex')).toBe('-1');

      // ArrowUp moves focus back
      act(() => {
        fireEvent.keyDown(secondRow, { key: 'ArrowUp' });
      });
      expect(document.activeElement).toBe(firstRow);
      expect(firstRow.getAttribute('tabindex')).toBe('0');

      // End moves to last row
      act(() => {
        fireEvent.keyDown(firstRow, { key: 'End' });
      });
      expect(document.activeElement).toBe(lastRow);
      expect(lastRow.getAttribute('tabindex')).toBe('0');

      // Home moves to first row
      act(() => {
        fireEvent.keyDown(lastRow, { key: 'Home' });
      });
      expect(document.activeElement).toBe(firstRow);
      expect(firstRow.getAttribute('tabindex')).toBe('0');

      // Enter triggers onOpenPeek
      act(() => {
        fireEvent.keyDown(firstRow, { key: 'Enter' });
      });
      expect(handleOpenPeek).toHaveBeenCalledWith(firstRow.getAttribute('data-issue-key'));
    });
  });

  // =========================================================================
  // Required Test Case 2: Positive case — verifies grid roles render valid
  // ARIA relationships
  // =========================================================================
  describe('Test Case 2: Positive Case - Grid Roles Render Valid ARIA Relationships', () => {
    it('verifies SwimlaneBoardGrid composite grid semantics (role="grid" -> role="row" -> role="columnheader" & role="gridcell")', () => {
      render(
        <SwimlaneBoardGrid
          issues={FIXTURE_12_ISSUES}
          projectKey="KAN"
          groupBy="state"
          subGroupBy="priority"
        />
      );

      // 1. Grid container exists and declares role="grid" with valid accessible name
      const grid = screen.getByRole('grid', { name: '2D Swimlane Board Grid' });
      expect(grid).toBeDefined();
      expect(grid.getAttribute('aria-rowcount')).toBeDefined();
      expect(grid.getAttribute('aria-colcount')).toBeDefined();

      // 2. Column headers row exists with role="row" and aria-rowindex="1"
      const headerRow = expectElement(
        grid.querySelector<HTMLElement>('.swimlane-col-headers[role="row"]'),
        'headerRow'
      );
      expect(headerRow.getAttribute('aria-rowindex')).toBe('1');

      // 3. Column headers declare role="columnheader" with sequential aria-colindex
      const colHeaders = headerRow.querySelectorAll('[role="columnheader"]');
      expect(colHeaders.length).toBeGreaterThan(0);
      colHeaders.forEach((th, idx) => {
        expect(th.getAttribute('aria-colindex')).toBe(String(idx + 1));
      });

      // 4. Swimlane bands render rows with role="row" and aria-rowindex >= 2
      const bandRows = grid.querySelectorAll('.swimlane-band-columns[role="row"]');
      expect(bandRows.length).toBeGreaterThan(0);
      bandRows.forEach((row, rowIdx) => {
        expect(row.getAttribute('aria-rowindex')).toBe(String(rowIdx + 2));

        // 5. Columns inside band rows declare role="gridcell" with valid aria-colindex
        const cells = row.querySelectorAll(':scope > [role="gridcell"]');
        expect(cells.length).toBe(colHeaders.length);
        cells.forEach((cell, cellIdx) => {
          expect(cell.getAttribute('aria-colindex')).toBe(String(cellIdx + 1));
        });
      });
    });

    it('verifies CalendarView composite grid semantics (role="grid" -> role="row" -> role="columnheader" & role="gridcell")', () => {
      render(
        <CalendarView
          issues={FIXTURE_12_ISSUES}
          projectKey="KAN"
          initialYear={2026}
          initialMonth={11}
          today="2026-11-20"
        />
      );

      const grid = screen.getByRole('grid');
      expect(grid).toBeDefined();

      // Header row
      const headerRow = grid.querySelector('.calendar-weekday-headers-row[role="row"]');
      expect(headerRow).not.toBeNull();
      expect(headerRow?.getAttribute('aria-rowindex')).toBe('1');

      const colHeaders = headerRow?.querySelectorAll('[role="columnheader"]');
      expect(colHeaders?.length).toBe(7);
      colHeaders?.forEach((ch, idx) => {
        expect(ch.getAttribute('aria-colindex')).toBe(String(idx + 1));
      });

      // 14 day cells with role="gridcell" and valid row/col indexes
      const dayCells = grid.querySelectorAll('[role="gridcell"]');
      expect(dayCells.length).toBe(14);
      dayCells.forEach((dc, idx) => {
        const expectedCol = (idx % 7) + 1;
        const expectedRow = Math.floor(idx / 7) + 2;
        expect(dc.getAttribute('aria-colindex')).toBe(String(expectedCol));
        expect(dc.getAttribute('aria-rowindex')).toBe(String(expectedRow));
      });
    });

    it('verifies TableView table rows and headers declare role="row", role="columnheader", and role="gridcell"', () => {
      render(
        <TableView
          issues={FIXTURE_12_ISSUES}
          projectKey="KAN"
        />
      );

      const table = screen.getByRole('table');
      expect(table).toBeDefined();

      const headerRow = table.querySelector('thead tr[role="row"]');
      expect(headerRow).not.toBeNull();
      expect(headerRow?.getAttribute('aria-rowindex')).toBe('1');

      const headers = headerRow?.querySelectorAll('th[role="columnheader"]');
      expect(headers?.length).toBeGreaterThan(0);
      headers?.forEach((th, idx) => {
        expect(th.getAttribute('aria-colindex')).toBe(String(idx + 1));
      });

      const bodyRows = table.querySelectorAll('tbody tr[role="row"]');
      expect(bodyRows.length).toBe(FIXTURE_12_ISSUES.length);
      bodyRows.forEach((tr, idx) => {
        expect(tr.getAttribute('aria-rowindex')).toBe(String(idx + 2));
        const keyCell = tr.querySelector('td.table-key-cell[role="gridcell"]');
        expect(keyCell).not.toBeNull();
        expect(keyCell?.getAttribute('aria-colindex')).toBe('1');
      });
    });

    it('verifies TimelineView scale header and rows render valid row and columnheader roles', () => {
      render(
        <TimelineView
          issues={FIXTURE_12_ISSUES as TimelineIssueItem[]}
          projectKey="KAN"
          today="2026-11-20"
        />
      );

      const scaleHeader = document.querySelector('.timeline-scale-header[role="row"]');
      expect(scaleHeader).not.toBeNull();
      expect(scaleHeader?.getAttribute('aria-rowindex')).toBe('1');

      const scaleCells = scaleHeader?.querySelectorAll('[role="columnheader"]');
      expect(scaleCells?.length).toBeGreaterThan(0);
      scaleCells?.forEach((sc, idx) => {
        expect(sc.getAttribute('aria-colindex')).toBe(String(idx + 1));
      });

      const leftRows = document.querySelectorAll('.timeline-left-row[role="row"]');
      expect(leftRows.length).toBe(FIXTURE_12_ISSUES.length);
      leftRows.forEach((lr, idx) => {
        expect(lr.getAttribute('aria-rowindex')).toBe(String(idx + 2));
      });
    });
  });

  // =========================================================================
  // Required Test Case 3: Negative case — verifies roving tabindex correctly
  // sets tabIndex={-1} on unfocused cells
  // =========================================================================
  describe('Test Case 3: Negative Case - Roving Tabindex Sets tabIndex={-1} on Unfocused Cells', () => {
    it('sets tabIndex={-1} on all unfocused swimlane cards when a specific card is focused', () => {
      render(
        <SwimlaneBoardGrid
          issues={FIXTURE_12_ISSUES}
          projectKey="KAN"
          groupBy="state"
          subGroupBy="priority"
          focusedKey="KAN-142"
        />
      );

      const focusedCard = document.querySelector<HTMLElement>('[data-issue-key="KAN-142"]');
      expect(focusedCard).not.toBeNull();
      expect(focusedCard?.getAttribute('tabindex')).toBe('0');
      expect(focusedCard?.getAttribute('data-focused')).toBe('true');

      // Verify all other cards in the grid carry tabIndex={-1} and data-focused="false"
      const unfocusedCards = document.querySelectorAll<HTMLElement>(
        '.swimlane-card:not([data-issue-key="KAN-142"])'
      );
      expect(unfocusedCards.length).toBeGreaterThan(0);
      unfocusedCards.forEach((card) => {
        expect(card.getAttribute('tabindex')).toBe('-1');
        expect(card.getAttribute('data-focused')).toBe('false');
      });

      // Verify all non-matching column gridcells carry tabIndex={-1}
      const allGridcells = document.querySelectorAll<HTMLElement>('.board-column[role="gridcell"]');
      const unfocusedGridcells = Array.from(allGridcells).filter(
        (cell) => !cell.contains(focusedCard)
      );
      expect(unfocusedGridcells.length).toBeGreaterThan(0);
      unfocusedGridcells.forEach((cell) => {
        expect(cell.getAttribute('tabindex')).toBe('-1');
      });
    });

    it('sets tabIndex={-1} on all unfocused list rows in ListView', () => {
      render(
        <ListView
          issues={FIXTURE_12_ISSUES}
          projectKey="KAN"
          focusedKey="KAN-142"
        />
      );

      const focusedRow = document.querySelector<HTMLElement>('[data-issue-key="KAN-142"]');
      expect(focusedRow).not.toBeNull();
      expect(focusedRow?.getAttribute('tabindex')).toBe('0');

      const unfocusedRows = document.querySelectorAll<HTMLElement>(
        '.issue-list-card:not([data-issue-key="KAN-142"])'
      );
      expect(unfocusedRows.length).toBe(FIXTURE_12_ISSUES.length - 1);
      unfocusedRows.forEach((row) => {
        expect(row.getAttribute('tabindex')).toBe('-1');
      });
    });

    it('sets tabIndex={-1} on all unfocused calendar day cells except the initial cell', () => {
      render(
        <CalendarView
          issues={FIXTURE_12_ISSUES}
          projectKey="KAN"
          initialYear={2026}
          initialMonth={11}
          today="2026-11-20"
        />
      );

      const cells = document.querySelectorAll<HTMLElement>('[role="gridcell"]');
      expect(cells.length).toBe(14);

      // Cell 0 has tabIndex=0, all other 13 cells have tabIndex=-1
      expect(cells[0]?.getAttribute('tabindex')).toBe('0');
      for (let i = 1; i < cells.length; i++) {
        expect(cells[i]?.getAttribute('tabindex')).toBe('-1');
      }
    });

    it('sets tabIndex={-1} on all unfocused table rows in TableView', () => {
      render(
        <TableView
          issues={FIXTURE_12_ISSUES}
          projectKey="KAN"
          focusedKey="KAN-142"
        />
      );

      const focusedRow = document.querySelector<HTMLElement>('tbody tr[data-issue-key="KAN-142"]');
      expect(focusedRow).not.toBeNull();
      expect(focusedRow?.getAttribute('tabindex')).toBe('0');

      const unfocusedRows = document.querySelectorAll<HTMLElement>(
        'tbody tr[role="row"]:not([data-issue-key="KAN-142"])'
      );
      expect(unfocusedRows.length).toBe(FIXTURE_12_ISSUES.length - 1);
      unfocusedRows.forEach((row) => {
        expect(row.getAttribute('tabindex')).toBe('-1');
      });
    });
  });
});
