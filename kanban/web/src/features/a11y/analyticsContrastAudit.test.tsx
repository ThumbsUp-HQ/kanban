// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import React from 'react';
import fs from 'node:fs';
import path from 'node:path';
import { CycleBurndownChart, type BurndownResponse } from '../analytics/charts/CycleBurndownChart';
import { AgingWipChart } from '../analytics/charts/AgingWipChart';
import { CycleTimeScatterChart } from '../analytics/charts/CycleTimeScatterChart';
import { CfdAreaChart } from '../analytics/charts/CfdAreaChart';
import { StateBadge, type StateGroupKey } from '../../components/state/StateBadge';

const STYLES_DIR = path.resolve(import.meta.dirname, '../../styles');
const ANALYTICS_DIR = path.resolve(import.meta.dirname, '../analytics');

const mockBurndown: BurndownResponse = {
  cycle_id: 'cyc-1',
  series: [
    { date: '2026-11-01', scope: 20, remaining: 20 },
    { date: '2026-11-02', scope: 20, remaining: 16 },
    { date: '2026-11-03', scope: 22, remaining: 14 },
    { date: '2026-11-04', scope: 22, remaining: 10 },
  ],
  ideal: [
    { date: '2026-11-01', remaining: 20 },
    { date: '2026-11-02', remaining: 15 },
    { date: '2026-11-03', remaining: 10 },
    { date: '2026-11-04', remaining: 5 },
  ],
};

const mockAgingActiveIssues = [
  {
    issue_id: 'iss-1',
    issue_key: 'KAN-101',
    title: 'Normal active item',
    state_id: 'st-in-progress',
    state_name: 'In Progress',
    state_color_hex: '#3b82f6',
    state_entered_at: '2026-11-20T10:00:00Z',
    first_started_at: '2026-11-20T10:00:00Z',
    age_in_current_state_hours: 24.0,
    total_wip_hours: 24.0,
  },
  {
    issue_id: 'iss-2',
    issue_key: 'KAN-102',
    title: 'Exceeded active item',
    state_id: 'st-in-progress',
    state_name: 'In Progress',
    state_color_hex: '#3b82f6',
    state_entered_at: '2026-11-15T10:00:00Z',
    first_started_at: '2026-11-15T10:00:00Z',
    age_in_current_state_hours: 96.0,
    total_wip_hours: 96.0,
  },
];

const mockColumnThresholds = {
  'st-in-progress': {
    state_id: 'st-in-progress',
    state_name: 'In Progress',
    state_group: 'started',
    color_hex: '#3b82f6',
    p50_hours: 20.0,
    p85_hours: 48.0,
    p95_hours: 72.0,
    sample_size: 15,
  },
};

const mockScatterPoints = [
  {
    issue_id: 'sp-1',
    issue_key: 'KAN-201',
    title: 'Fast task',
    cycle_time_days: 1.5,
    lead_time_days: 2.0,
    completed_at: '2026-11-02T10:00:00Z',
  },
  {
    issue_id: 'sp-2',
    issue_key: 'KAN-202',
    title: 'Slow task exceeding p85',
    cycle_time_days: 6.0,
    lead_time_days: 8.5,
    completed_at: '2026-11-04T12:00:00Z',
  },
];

const mockScatterPercentiles = { p50: 2.0, p85: 4.0, p95: 5.5 };

const mockCfdStates = [
  { id: 's-backlog', name: 'Backlog', state_group: 'backlog', color_hex: '#94a3b8', sort_order: 1 },
  { id: 's-unstarted', name: 'Todo', state_group: 'unstarted', color_hex: '#60a5fa', sort_order: 2 },
  { id: 's-started', name: 'In Progress', state_group: 'started', color_hex: '#f59e0b', sort_order: 3 },
  { id: 's-completed', name: 'Done', state_group: 'completed', color_hex: '#10b981', sort_order: 4 },
];

const mockCfdPoints = [
  { date: '2026-11-01', backlog: 10, unstarted: 4, started: 3, completed: 1, cancelled: 0, total: 18 },
  { date: '2026-11-02', backlog: 8, unstarted: 5, started: 4, completed: 2, cancelled: 0, total: 19 },
];

describe('WCAG 2.2 AA Contrast Tokens & Non-Color Differentiation Audit (KAN-361)', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  describe('Test Case 1: Flow Analytics and Burndown Charts SVG path and stroke tokens resolve to semantic CSS variables', () => {
    it('verifies CycleBurndownChart renders without raw hex colors and uses semantic tokens', () => {
      const { container } = render(
        <CycleBurndownChart burndown={mockBurndown} cycleName="Sprint 42" />
      );

      const paths = container.querySelectorAll('path');
      expect(paths.length).toBeGreaterThanOrEqual(2);

      // Check ideal trajectory path stroke
      const idealPath = Array.from(paths).find((p) => p.getAttribute('stroke-dasharray') === '6 4');
      expect(idealPath).toBeDefined();
      expect(idealPath?.getAttribute('stroke')).toContain('var(--chart-line-2');
      expect(idealPath?.getAttribute('stroke')).not.toMatch(/^#[0-9a-fA-F]{3,8}$/);

      // Check remaining trajectory path stroke
      const remainingPath = Array.from(paths).find((p) => !p.getAttribute('stroke-dasharray') && p.getAttribute('stroke-width') === '2.5');
      expect(remainingPath).toBeDefined();
      expect(remainingPath?.getAttribute('stroke')).toContain('var(--chart-line-1');
      expect(remainingPath?.getAttribute('stroke')).not.toMatch(/^#[0-9a-fA-F]{3,8}$/);

      // Check remaining circles
      const circles = container.querySelectorAll('circle');
      expect(circles.length).toBe(mockBurndown.series.length);
      for (const circle of circles) {
        expect(circle.getAttribute('fill')).toContain('var(--chart-line-1');
        expect(circle.getAttribute('stroke')).toContain('var(--bg-surface');
      }
    });

    it('verifies AgingWipChart threshold lines, active items, and labels use semantic tokens', () => {
      const { container } = render(
        <AgingWipChart
          activeIssues={mockAgingActiveIssues}
          columnThresholds={mockColumnThresholds}
          totalActiveWip={2}
        />
      );

      // Guide threshold lines
      const lines = container.querySelectorAll('line');
      const p50Line = Array.from(lines).find((l) => l.getAttribute('stroke-dasharray') === '3 3');
      const p85Line = Array.from(lines).find((l) => l.getAttribute('stroke-dasharray') === '4 4');
      const p95Line = Array.from(lines).find((l) => l.getAttribute('stroke-dasharray') === '2 2');

      expect(p50Line?.getAttribute('stroke')).toContain('var(--chart-line-1');
      expect(p85Line?.getAttribute('stroke')).toContain('var(--warn-fg');
      expect(p95Line?.getAttribute('stroke')).toContain('var(--danger-fg');

      // Active circles
      const normalItem = container.querySelector('[data-testid="aging-item-KAN-101"] circle');
      const exceededItem = container.querySelector('[data-testid="aging-item-KAN-102"] circle');

      expect(normalItem?.getAttribute('fill')).toContain('var(--chart-line-1');
      expect(exceededItem?.getAttribute('fill')).toContain('var(--danger-fg');
      expect(normalItem?.getAttribute('stroke')).toContain('var(--bg-surface');
      expect(exceededItem?.getAttribute('stroke')).toContain('var(--bg-surface');

      // Active text labels
      const normalText = container.querySelector('[data-testid="aging-item-KAN-101"] text');
      const exceededText = container.querySelector('[data-testid="aging-item-KAN-102"] text');
      expect(normalText?.getAttribute('fill')).toContain('var(--fg-secondary');
      expect(exceededText?.getAttribute('fill')).toContain('var(--danger-fg');
    });

    it('verifies CycleTimeScatterChart and CfdAreaChart resolve SVG colors to tokens', () => {
      const { container: scatterContainer } = render(
        <CycleTimeScatterChart
          points={mockScatterPoints}
          cycleTimePercentiles={mockScatterPercentiles}
          leadTimePercentiles={mockScatterPercentiles}
          totalCompleted={2}
        />
      );

      expect(scatterContainer.querySelector('[data-testid="p50-line"]')?.getAttribute('stroke')).toContain('var(--chart-line-1');
      expect(scatterContainer.querySelector('[data-testid="p85-line"]')?.getAttribute('stroke')).toContain('var(--warn-fg');
      expect(scatterContainer.querySelector('[data-testid="p95-line"]')?.getAttribute('stroke')).toContain('var(--ok-fg');

      const fastDot = scatterContainer.querySelector('[data-testid="scatter-dot-KAN-201"]');
      const slowDot = scatterContainer.querySelector('[data-testid="scatter-dot-KAN-202"]');
      expect(fastDot?.getAttribute('fill')).toContain('var(--chart-line-1');
      expect(slowDot?.getAttribute('fill')).toContain('var(--danger-fg');

      const { container: cfdContainer } = render(
        <CfdAreaChart points={mockCfdPoints} states={mockCfdStates} />
      );

      expect(cfdContainer.querySelector('[data-testid="cfd-area-backlog"]')?.getAttribute('fill')).toContain('var(--state-backlog-fg');
      expect(cfdContainer.querySelector('[data-testid="cfd-area-unstarted"]')?.getAttribute('fill')).toContain('var(--state-unstarted-fg');
      expect(cfdContainer.querySelector('[data-testid="cfd-area-started"]')?.getAttribute('fill')).toContain('var(--state-started-fg');
      expect(cfdContainer.querySelector('[data-testid="cfd-area-completed"]')?.getAttribute('fill')).toContain('var(--state-completed-fg');
    });
  });

  describe('Test Case 2: Non-color differentiation across burndown and analytics SVG series (dashed/dotted strokes and distinct markers)', () => {
    it('verifies ideal vs actual burndown series provide non-color differentiation via stroke pattern and data markers', () => {
      const { container } = render(
        <CycleBurndownChart burndown={mockBurndown} cycleName="Sprint 42" />
      );

      const paths = Array.from(container.querySelectorAll('path'));
      const idealPath = paths.find((p) => p.getAttribute('stroke-dasharray') === '6 4');
      const remainingPath = paths.find((p) => !p.getAttribute('stroke-dasharray') && p.getAttribute('stroke-width') === '2.5');

      // Ideal line must have dashed stroke
      expect(idealPath).toBeDefined();
      expect(idealPath?.getAttribute('stroke-dasharray')).toBe('6 4');

      // Remaining line must be solid with circular data point markers
      expect(remainingPath).toBeDefined();
      expect(remainingPath?.getAttribute('stroke-dasharray')).toBeNull();

      const dataMarkers = container.querySelectorAll('circle');
      expect(dataMarkers.length).toBe(mockBurndown.series.length);
      expect(dataMarkers[0]?.getAttribute('r')).toBe('4');
    });

    it('verifies percentile threshold guide lines in scatter chart use distinct strokeDasharray patterns', () => {
      const { container } = render(
        <CycleTimeScatterChart
          points={mockScatterPoints}
          cycleTimePercentiles={mockScatterPercentiles}
          leadTimePercentiles={mockScatterPercentiles}
          totalCompleted={2}
        />
      );

      const p50 = container.querySelector('[data-testid="p50-line"]');
      const p85 = container.querySelector('[data-testid="p85-line"]');
      const p95 = container.querySelector('[data-testid="p95-line"]');

      expect(p50?.getAttribute('stroke-dasharray')).toBe('4 4');
      expect(p85?.getAttribute('stroke-dasharray')).toBe('6 4');
      expect(p95?.getAttribute('stroke-dasharray')).toBe('2 2');

      // Verify all 3 threshold lines have mutually distinct dash array patterns
      const dashArrays = new Set([
        p50?.getAttribute('stroke-dasharray'),
        p85?.getAttribute('stroke-dasharray'),
        p95?.getAttribute('stroke-dasharray'),
      ]);
      expect(dashArrays.size).toBe(3);
    });

    it('verifies exceeded threshold items use distinct visual marker sizes and stroke styles', () => {
      const { container: agingContainer } = render(
        <AgingWipChart
          activeIssues={mockAgingActiveIssues}
          columnThresholds={mockColumnThresholds}
          totalActiveWip={2}
        />
      );

      const normalCircle = agingContainer.querySelector('[data-testid="aging-item-KAN-101"] circle');
      const exceededCircle = agingContainer.querySelector('[data-testid="aging-item-KAN-102"] circle');

      // Normal item radius is 5, exceeded item radius is 7
      expect(Number(normalCircle?.getAttribute('r'))).toBe(5);
      expect(Number(exceededCircle?.getAttribute('r'))).toBe(7);

      // Exceeded circle includes dashed stroke pattern for tactile/visual distinction
      expect(exceededCircle?.getAttribute('stroke-dasharray')).toBe('3 1');
      expect(normalCircle?.getAttribute('stroke-dasharray')).toBeNull();

      // Exceeded text has font-weight 700 and "(EXCEEDS p85)" title
      const exceededText = agingContainer.querySelector('[data-testid="aging-item-KAN-102"] text');
      expect(exceededText?.getAttribute('font-weight')).toBe('700');
      expect(exceededCircle?.querySelector('title')?.textContent).toContain('(EXCEEDS p85)');

      // Verify scatter chart exceeded item has distinct radius and dashed stroke
      const { container: scatterContainer } = render(
        <CycleTimeScatterChart
          points={mockScatterPoints}
          cycleTimePercentiles={mockScatterPercentiles}
          leadTimePercentiles={mockScatterPercentiles}
          totalCompleted={2}
        />
      );

      const fastDot = scatterContainer.querySelector('[data-testid="scatter-dot-KAN-201"]');
      const slowDot = scatterContainer.querySelector('[data-testid="scatter-dot-KAN-202"]');

      expect(Number(fastDot?.getAttribute('r'))).toBe(4.5);
      expect(Number(slowDot?.getAttribute('r'))).toBe(6);
      expect(slowDot?.getAttribute('stroke-dasharray')).toBe('2 1');
    });
  });

  describe('Test Case 3: Status badges and flow analytics badges/chips contrast token audit across light and dark themes', () => {
    it('verifies FlowAnalyticsPage.css defines percentile badges via semantic CSS variables without raw hex codes', () => {
      const cssPath = path.join(ANALYTICS_DIR, 'FlowAnalyticsPage.css');
      expect(fs.existsSync(cssPath)).toBe(true);
      const cssContent = fs.readFileSync(cssPath, 'utf8');

      // Match .kb-badge-p50, .kb-badge-p85, .kb-badge-p95 blocks
      const badgeP50Match = /\.kb-badge-p50\s*\{([^}]+)\}/.exec(cssContent);
      const badgeP85Match = /\.kb-badge-p85\s*\{([^}]+)\}/.exec(cssContent);
      const badgeP95Match = /\.kb-badge-p95\s*\{([^}]+)\}/.exec(cssContent);

      expect(badgeP50Match).not.toBeNull();
      expect(badgeP85Match).not.toBeNull();
      expect(badgeP95Match).not.toBeNull();

      const p50Block = badgeP50Match?.[1] ?? '';
      const p85Block = badgeP85Match?.[1] ?? '';
      const p95Block = badgeP95Match?.[1] ?? '';

      // Must use semantic CSS variables for text color
      expect(p50Block).toContain('var(--chart-line-1');
      expect(p85Block).toContain('var(--warn-fg');
      expect(p95Block).toContain('var(--ok-fg');

      // Verify no raw hex declarations without var() wrap inside badge declarations
      const rawHexRegex = /:\s*(#[0-9a-fA-F]{3,8})\s*;/g;
      expect(Array.from(p50Block.matchAll(rawHexRegex))).toEqual([]);
      expect(Array.from(p85Block.matchAll(rawHexRegex))).toEqual([]);
      expect(Array.from(p95Block.matchAll(rawHexRegex))).toEqual([]);
    });

    it('verifies theme.css defines canonical chart tokens and high-contrast dark mode state borders', () => {
      const themeCssPath = path.join(STYLES_DIR, 'theme.css');
      expect(fs.existsSync(themeCssPath)).toBe(true);
      const themeCss = fs.readFileSync(themeCssPath, 'utf8');

      // Light mode canonical tokens
      expect(themeCss).toContain('--chart-line-1: #2563eb;');
      expect(themeCss).toContain('--chart-line-2: #94a3b8;');

      // Dark mode token overrides in [data-theme="dark"]
      const darkThemeMatch = /\[data-theme="dark"\]\s*\{([^}]+)\}/.exec(themeCss);
      expect(darkThemeMatch).not.toBeNull();
      const darkBlock = darkThemeMatch?.[1] ?? '';

      expect(darkBlock).toContain('--chart-line-1: #60a5fa;');
      expect(darkBlock).toContain('--chart-line-2: #cbd5e1;');
      expect(darkBlock).toContain('--state-backlog-border: rgba(148, 163, 184, 0.45);');
      expect(darkBlock).toContain('--state-unstarted-border: rgba(96, 165, 250, 0.45);');
      expect(darkBlock).toContain('--state-started-border: rgba(245, 158, 11, 0.45);');
      expect(darkBlock).toContain('--state-completed-border: rgba(16, 185, 129, 0.45);');
      expect(darkBlock).toContain('--state-cancelled-border: rgba(239, 68, 68, 0.45);');
    });

    it('verifies StateBadge renders multi-modal non-color status indicators across all workflow states', () => {
      const groups: StateGroupKey[] = ['backlog', 'unstarted', 'started', 'completed', 'cancelled'];
      for (const grp of groups) {
        const { container, unmount } = render(
          <StateBadge group={grp} name={grp.toUpperCase()} testId={`audit-badge-${grp}`} />
        );

        const badge = screen.getByTestId(`audit-badge-${grp}`);
        expect(badge).toBeDefined();

        // 1. Semantic Emoji icon present
        const emoji = container.querySelector('.state-badge__emoji');
        expect(emoji).not.toBeNull();
        expect(emoji ? emoji.textContent.trim().length : 0).toBeGreaterThan(0);

        // 2. SVG StateProgressRing present
        const ring = container.querySelector('.state-badge__ring');
        expect(ring).not.toBeNull();

        // 3. Accessible text label present
        const label = container.querySelector('.state-badge__label');
        expect(label?.textContent).toBe(grp.toUpperCase());

        unmount();
      }
    });
  });
});
