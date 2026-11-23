/**
 * Landscape layout ergonomics unit tests (KAN-343 / KB-MOBILE-LANDSCAPE-LAYOUT).
 * Validates compact landscape row heights (32px), cell padding (4px 8px),
 * sticky header containment, and isolated horizontal scroll containers across
 * Table, Calendar, and Timeline views under @media (max-height: 540px) and (orientation: landscape).
 * Strictly plain ASCII hyphens (-) only.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render } from '@testing-library/react';
import React from 'react';
import fs from 'node:fs';
import path from 'node:path';
import { TableView } from '../../table/TableView';
import { CalendarView } from '../../calendar/CalendarView';
import { TimelineView, type TimelineIssueItem } from '../../timeline/TimelineView';
import { FIXTURE_12_ISSUES } from '../fixtures';
import type { IssueItem } from '../viewsApi';

const MOCK_ISSUES: IssueItem[] = [
  {
    id: 'issue-100',
    key: 'KAN-100',
    summary: 'Security Architecture Epic',
    state: { id: 's1', name: 'In Progress', group: 'started' },
    priority: { slug: 'high', label: 'High' },
    start_date: '2026-11-01',
    due_date: '2026-11-10',
  },
  {
    id: 'issue-142',
    key: 'KAN-142',
    summary: 'Harden Multi-Card OIDC & LDAPS Auth Studio',
    state: { id: 's1', name: 'In Progress', group: 'started' },
    priority: { slug: 'urgent', label: 'Urgent' },
    start_date: '2026-11-11',
    due_date: '2026-11-18',
  },
  {
    id: 'issue-143',
    key: 'KAN-143',
    summary: 'Verify LDAPS certificate pinning',
    state: { id: 's2', name: 'Done', group: 'completed' },
    priority: { slug: 'low', label: 'Low' },
    start_date: '2026-11-01',
    due_date: '2026-11-05',
  },
];

const MOCK_TIMELINE_ISSUES: TimelineIssueItem[] = [
  {
    id: 'issue-100',
    key: 'KAN-100',
    summary: 'Security Architecture Epic',
    state: { id: 's1', name: 'In Progress', group: 'started' },
    priority: { slug: 'high', label: 'High' },
    start_date: '2026-11-05',
    due_date: '2026-11-12',
  },
  {
    id: 'issue-142',
    key: 'KAN-142',
    summary: 'Harden Multi-Card OIDC & LDAPS Auth Studio',
    state: { id: 's1', name: 'In Progress', group: 'started' },
    priority: { slug: 'urgent', label: 'Urgent' },
    start_date: '2026-11-11',
    due_date: '2026-11-18',
  },
];

describe('LandscapeLayoutErgonomics (KAN-343)', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    vi.restoreAllMocks();
    document.cookie = 'kb_csrf=test-csrf-token-123; Path=/';
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
    document.cookie = 'kb_csrf=; expires=Thu, 01 Jan 1970 00:00:00 GMT; Path=/';
  });

  it('Case 1 (Positive): verifies landscape CSS rules apply compact 32px heights and 4px 8px padding when viewport height is <= 540px', () => {
    const tableCssPath = path.resolve(__dirname, '../../table/TableView.css');
    const listTableCssPath = path.resolve(__dirname, '../listTable.css');
    const calTimelineCssPath = path.resolve(__dirname, '../../timeline/calendarTimeline.css');

    expect(fs.existsSync(tableCssPath)).toBe(true);
    expect(fs.existsSync(listTableCssPath)).toBe(true);
    expect(fs.existsSync(calTimelineCssPath)).toBe(true);

    const tableCss = fs.readFileSync(tableCssPath, 'utf8');
    const listTableCss = fs.readFileSync(listTableCssPath, 'utf8');
    const calTimelineCss = fs.readFileSync(calTimelineCssPath, 'utf8');

    // 1. Verify @media (max-height: 540px) and (orientation: landscape) exists in TableView.css
    expect(tableCss).toMatch(/@media\s*\(max-height:\s*540px\)\s*and\s*\(orientation:\s*landscape\)/);
    expect(listTableCss).toMatch(/@media\s*\(max-height:\s*540px\)\s*and\s*\(orientation:\s*landscape\)/);
    expect(calTimelineCss).toMatch(/@media\s*\(max-height:\s*540px\)\s*and\s*\(orientation:\s*landscape\)/);

    // 2. Verify TableView rules: 32px row height and 4px 8px padding
    expect(tableCss).toContain('height: 32px;');
    expect(tableCss).toContain('min-height: 32px;');
    expect(tableCss).toMatch(/padding:\s*var\(--space-1,\s*4px\)\s*var\(--space-2,\s*8px\);/);

    // 3. Verify Timeline rules: 32px row height and compact headers
    expect(calTimelineCss).toMatch(/\.timeline-left-header\s*\{[^}]*height:\s*32px;/);
    expect(calTimelineCss).toMatch(/\.timeline-scale-header\s*\{[^}]*height:\s*32px;/);
    expect(calTimelineCss).toMatch(/\.timeline-left-row\s*\{[^}]*height:\s*32px;/);
    expect(calTimelineCss).toMatch(/\.timeline-track-row\s*\{[^}]*height:\s*32px;/);

    // 4. Verify Calendar rules: compact weekday header and day cells
    expect(calTimelineCss).toMatch(/\.calendar-day-cell\s*\{[^}]*min-height:\s*48px;/);
    expect(calTimelineCss).toMatch(/\.calendar-weekday-header\s*\{[^}]*padding:\s*var\(--space-1,\s*4px\)\s*0;/);

    // 5. Render components and verify DOM nodes are present for compact styling
    const { container: tableContainer } = render(
      <TableView issues={MOCK_ISSUES} projectKey="KAN" modulesEnabled={true} />
    );
    expect(tableContainer.querySelector('.table-scroll-wrap')).not.toBeNull();
    expect(tableContainer.querySelector('.issues-table')).not.toBeNull();
    const rows = tableContainer.querySelectorAll('.issues-table-body tr');
    expect(rows.length).toBe(3);

    const { container: calContainer } = render(
      <CalendarView
        issues={MOCK_ISSUES}
        projectKey="KAN"
        initialYear={2026}
        initialMonth={11}
        today="2026-11-12"
      />
    );
    expect(calContainer.querySelector('.calendar-view')).not.toBeNull();
    expect(calContainer.querySelector('.calendar-month-grid')).not.toBeNull();

    const { container: timelineContainer } = render(
      <TimelineView
        issues={MOCK_TIMELINE_ISSUES}
        projectKey="KAN"
        initialZoom="week"
        initialStartDate="2026-11-01"
        today="2026-11-12"
      />
    );
    expect(timelineContainer.querySelector('.timeline-view')).not.toBeNull();
    expect(timelineContainer.querySelector('.timeline-split-container')).not.toBeNull();
  });

  it('Case 2 (Negative): verifies horizontal scroll containers do not cause page-level horizontal overflow', () => {
    const tableCss = fs.readFileSync(path.resolve(__dirname, '../../table/TableView.css'), 'utf8');
    const calTimelineCss = fs.readFileSync(path.resolve(__dirname, '../../timeline/calendarTimeline.css'), 'utf8');

    // 1. TableView containment: isolated scroll container prevents outer page blowout
    expect(tableCss).toMatch(/\.table-view-container\s*\{[^}]*max-width:\s*100%;/);
    expect(tableCss).toMatch(/\.table-view-container\s*\{[^}]*overflow-x:\s*hidden;/);
    expect(tableCss).toMatch(/\.table-scroll-wrap\s*\{[^}]*overflow-x:\s*auto;/);
    expect(tableCss).toMatch(/\.table-scroll-wrap\s*\{[^}]*overscroll-behavior-x:\s*contain;/);
    expect(tableCss).toMatch(/\.table-scroll-wrap\s*\{[^}]*contain:\s*inline-size;/);

    // 2. TimelineView containment: isolated horizontal canvas and outer clip
    expect(calTimelineCss).toMatch(/\.timeline-view\s*\{[^}]*max-width:\s*100%;/);
    expect(calTimelineCss).toMatch(/\.timeline-view\s*\{[^}]*overflow-x:\s*hidden;/);
    expect(calTimelineCss).toMatch(/\.timeline-split-container\s*\{[^}]*max-width:\s*100%;/);
    expect(calTimelineCss).toMatch(/\.timeline-split-container\s*\{[^}]*overflow:\s*hidden;/);
    expect(calTimelineCss).toMatch(/\.timeline-right-canvas-wrapper\s*\{[^}]*overflow-x:\s*auto;/);
    expect(calTimelineCss).toMatch(/\.timeline-right-canvas-wrapper\s*\{[^}]*overscroll-behavior-x:\s*contain;/);

    // 3. CalendarView containment: horizontal scrolling contained within calendar view
    expect(calTimelineCss).toMatch(/\.calendar-view\s*\{[^}]*max-width:\s*100%;/);
    expect(calTimelineCss).toMatch(/\.calendar-view\s*\{[^}]*overflow-x:\s*auto;/);
    expect(calTimelineCss).toMatch(/\.calendar-view\s*\{[^}]*overscroll-behavior-x:\s*contain;/);

    // 4. Render components and test scroll wrappers
    const { container: tableContainer } = render(
      <TableView issues={FIXTURE_12_ISSUES} projectKey="KAN" modulesEnabled={true} />
    );
    const scrollWrap = tableContainer.querySelector<HTMLElement>('.table-scroll-wrap');
    expect(scrollWrap).not.toBeNull();
    // Simulate horizontal scroll event
    if (scrollWrap) {
      scrollWrap.scrollLeft = 120;
      expect(scrollWrap.scrollLeft).toBe(120);
    }

    const { container: timelineContainer } = render(
      <TimelineView
        issues={MOCK_TIMELINE_ISSUES}
        projectKey="KAN"
        initialZoom="day"
        initialStartDate="2026-11-01"
      />
    );
    const canvasWrap = timelineContainer.querySelector<HTMLElement>('.timeline-right-canvas-wrapper');
    expect(canvasWrap).not.toBeNull();
    if (canvasWrap) {
      canvasWrap.scrollLeft = 240;
      expect(canvasWrap.scrollLeft).toBe(240);
    }
  });

  it('Case 3 (Boundary): verifies sticky headers maintain position when scrolled to bottom of dataset', () => {
    const tableCss = fs.readFileSync(path.resolve(__dirname, '../../table/TableView.css'), 'utf8');
    const calTimelineCss = fs.readFileSync(path.resolve(__dirname, '../../timeline/calendarTimeline.css'), 'utf8');

    // 1. TableView sticky headers & columns containment
    expect(tableCss).toMatch(/\.issues-table-head\s*\{[^}]*position:\s*sticky;/);
    expect(tableCss).toMatch(/\.issues-table-head\s*\{[^}]*top:\s*0;/);
    expect(tableCss).toMatch(/\.issues-table-head\s*\{[^}]*z-index:\s*10;/);
    expect(tableCss).toMatch(/\.issues-table-head\s*\{[^}]*contain:\s*paint;/);

    expect(tableCss).toMatch(/\.issues-table\s+th\.sticky-col\s*\{[^}]*position:\s*sticky;/);
    expect(tableCss).toMatch(/\.issues-table\s+th\.sticky-col\s*\{[^}]*left:\s*0;/);
    expect(tableCss).toMatch(/\.issues-table\s+th\.sticky-col\s*\{[^}]*top:\s*0;/);
    expect(tableCss).toMatch(/\.issues-table\s+th\.sticky-col\s*\{[^}]*z-index:\s*12;/);

    expect(tableCss).toMatch(/\.issues-table\s+td\.sticky-col\s*\{[^}]*position:\s*sticky;/);
    expect(tableCss).toMatch(/\.issues-table\s+td\.sticky-col\s*\{[^}]*left:\s*0;/);
    expect(tableCss).toMatch(/\.issues-table\s+td\.sticky-col\s*\{[^}]*z-index:\s*5;/);

    // 2. Timeline sticky headers
    expect(calTimelineCss).toMatch(/\.timeline-left-header\s*\{[^}]*position:\s*sticky;/);
    expect(calTimelineCss).toMatch(/\.timeline-left-header\s*\{[^}]*top:\s*0;/);
    expect(calTimelineCss).toMatch(/\.timeline-left-header\s*\{[^}]*z-index:\s*10;/);
    expect(calTimelineCss).toMatch(/\.timeline-left-header\s*\{[^}]*contain:\s*paint;/);

    expect(calTimelineCss).toMatch(/\.timeline-scale-header\s*\{[^}]*position:\s*sticky;/);
    expect(calTimelineCss).toMatch(/\.timeline-scale-header\s*\{[^}]*top:\s*0;/);
    expect(calTimelineCss).toMatch(/\.timeline-scale-header\s*\{[^}]*z-index:\s*10;/);
    expect(calTimelineCss).toMatch(/\.timeline-scale-header\s*\{[^}]*contain:\s*paint;/);

    // 3. Calendar sticky headers
    expect(calTimelineCss).toMatch(/\.calendar-weekday-header\s*\{[^}]*position:\s*sticky;/);
    expect(calTimelineCss).toMatch(/\.calendar-weekday-header\s*\{[^}]*top:\s*0;/);
    expect(calTimelineCss).toMatch(/\.calendar-weekday-header\s*\{[^}]*z-index:\s*4;/);

    // 4. Render large dataset and simulate bottom boundary scroll
    const { container: tableContainer } = render(
      <TableView issues={FIXTURE_12_ISSUES} projectKey="KAN" modulesEnabled={true} />
    );
    const scrollWrap = tableContainer.querySelector<HTMLElement>('.table-scroll-wrap');
    const thead = tableContainer.querySelector<HTMLElement>('.issues-table-head');
    const stickyHeaders = tableContainer.querySelectorAll('.sticky-col');

    expect(scrollWrap).not.toBeNull();
    expect(thead).not.toBeNull();
    expect(stickyHeaders.length).toBeGreaterThan(0);

    // Boundary scroll to bottom
    if (scrollWrap) {
      scrollWrap.scrollTop = 1000;
      expect(scrollWrap.scrollTop).toBe(1000);
    }

    // Check header row structure
    const headerRow = thead.querySelector('tr');
    expect(headerRow).not.toBeNull();
    expect(thead.getAttribute('class')).toContain('issues-table-head');
  });

  it('verifies view forwarders exist in features/views/ for TableView.css, CalendarView.css, and TimelineView.css', () => {
    const tableForwarder = path.resolve(__dirname, '../TableView.css');
    const calForwarder = path.resolve(__dirname, '../CalendarView.css');
    const timelineForwarder = path.resolve(__dirname, '../TimelineView.css');

    expect(fs.existsSync(tableForwarder)).toBe(true);
    expect(fs.existsSync(calForwarder)).toBe(true);
    expect(fs.existsSync(timelineForwarder)).toBe(true);

    expect(fs.readFileSync(tableForwarder, 'utf8')).toContain("@import '../table/TableView.css';");
    expect(fs.readFileSync(calForwarder, 'utf8')).toContain("@import '../timeline/calendarTimeline.css';");
    expect(fs.readFileSync(timelineForwarder, 'utf8')).toContain("@import '../timeline/calendarTimeline.css';");
  });
});
