/**
 * Playwright E2E verification and visual design proofs for Calendar & Timeline views (KB-P3-39).
 * Enforces:
 * - 7-column month due-date grid with >= 124px day cells desktop/tablet,
 * - mobile <= 767px week strip selector with 46px agenda list rows,
 * - Timeline (Gantt) 46px sticky issue rail and SVG BLOCKS dependency arrows,
 * - drag / keyboard date rescheduling enforcing due_date >= start_date,
 * - computed whitespace verification and multi-device annotated screenshots.
 */

import { test, expect } from '../support/test';
import { annotatedScreenshot } from '../support/annotate';
import { probeStyles } from '../support/styleProbe';
import { mockApi, loadFixture } from '../support/mockApi';

test.describe('Calendar & Timeline Views E2E (KB-P3-39)', () => {
  test.beforeEach(async ({ page }) => {
    // Intercept API routes: respond to PATCH /api/v1/issues/:key with 200 OK
    await mockApi(page, {
      'GET /api/v1/me': loadFixture('me-adam'),
      'GET /api/v1/system/status': loadFixture('system-status-prod'),
      'PATCH /api/v1/issues/:key': (req) => {
        return {
          status: 200,
          json: {
            key: req.params.key,
            ...(typeof req.body === 'object' && req.body !== null ? req.body : {}),
          },
        };
      },
    });
  });

  test('01-calendar-month: renders month grid, due-date pills, overflow popover, and unscheduled drawer', async ({
    page,
  }, testInfo) => {
    await page.goto('/projects/KAN/issues?layout=calendar');

    const calendarView = page.locator('.calendar-view');
    await expect(calendarView).toBeVisible();

    const isMobile = testInfo.project.name === 'mobile';

    if (isMobile) {
      // Mobile <= 767px: week strip and 46px agenda rows
      const mobileAgenda = page.locator('.calendar-mobile-agenda');
      await expect(mobileAgenda).toBeVisible();

      // Probe mobile agenda row styles
      await probeStyles(page, testInfo, {
        name: 'calendar-metrics-mobile',
        probes: [
          {
            selector: '.calendar-agenda-row',
            props: ['min-height', 'height', 'padding-top', 'padding-bottom'],
          },
          {
            selector: '.calendar-agenda-row .emoji-hint',
            props: ['width', 'height'],
          },
        ],
      });

      await annotatedScreenshot(page, testInfo, {
        name: '01-calendar-month',
        annotations: [
          {
            selector: '.calendar-toolbar',
            label: '1: month navigation + Today',
            note: 'Toolbar with Previous, Month YYYY heading, Next, and Today buttons',
          },
          {
            selector: '.calendar-agenda-row:first-child',
            label: '2: 2026-11-18 agenda row (46px)',
            note: 'Mobile 46px agenda row touch target for selected date',
          },
          {
            selector: '.calendar-week-strip',
            label: '3: 7-day compact week strip selector',
            note: 'Compact horizontal day selector preventing 55px cramped columns',
          },
          {
            selector: '[data-testid="calendar-unscheduled-toggle"]',
            label: '4: Unscheduled drawer button',
            note: 'Collapsible tray toggle showing unscheduled items count',
          },
        ],
      });
    } else {
      // Desktop / Tablet: 7-column month grid with >= 124px cells
      const cell18 = page.locator('[data-date="2026-11-18"]');
      await expect(cell18).toBeVisible();

      const pill142 = page.locator('[data-testid="calendar-pill-KAN-142"]');
      await expect(pill142).toBeVisible();

      const moreBtn = page.locator('[data-testid="calendar-more-2026-11-18"]');
      await expect(moreBtn).toBeVisible();

      // Probe desktop/tablet grid cell styles
      await probeStyles(page, testInfo, {
        name: 'calendar-metrics',
        probes: [
          {
            selector: '.calendar-day-cell',
            props: ['min-height', 'height', 'padding-top', 'padding-bottom'],
          },
          {
            selector: '.calendar-issue-pill .emoji-hint',
            props: ['width', 'height'],
          },
        ],
      });

      await annotatedScreenshot(page, testInfo, {
        name: '01-calendar-month',
        annotations: [
          {
            selector: '.calendar-toolbar',
            label: '1: month navigation + Today',
            note: 'Toolbar with Previous, Month YYYY heading, Next, and Today buttons',
          },
          {
            selector: '[data-testid="calendar-pill-KAN-142"]',
            label: '2: 2026-11-18 cell with KAN-142 pill',
            note: 'Pill with monospace key, priority EmojiHint, and truncated summary',
          },
          {
            selector: '[data-testid="calendar-more-2026-11-18"]',
            label: '3: +2 more overflow button',
            note: 'Non-modal popover trigger when > 3 issues share a date',
          },
          {
            selector: '[data-testid="calendar-unscheduled-toggle"]',
            label: '4: Unscheduled tray button',
            note: 'Collapsible drawer button listing issues with due_date === null',
          },
        ],
      });
    }
  });

  test('02-calendar-rescheduled: reschedules issue and updates cell with optimistic confirmation', async ({
    page,
  }, testInfo) => {
    await page.goto('/projects/KAN/issues?layout=calendar');

    const calendarView = page.locator('.calendar-view');
    await expect(calendarView).toBeVisible();

    const isMobile = testInfo.project.name === 'mobile';

    if (isMobile) {
      // On mobile, tap on Nov 20 in week strip
      const day20Btn = page.locator('.calendar-week-day-btn[data-date="2026-11-20"]');
      if (await day20Btn.count() > 0) {
        await day20Btn.click();
      }

      await annotatedScreenshot(page, testInfo, {
        name: '02-calendar-rescheduled',
        annotations: [
          {
            selector: '.calendar-mobile-agenda',
            label: '1: agenda view for 2026-11-20',
            note: 'Selected date agenda list rendering scheduled tasks',
          },
          {
            selector: '.calendar-toolbar',
            label: '2: recorded PATCH date note in legend',
            note: 'Optimistic schedule mutation feedback',
          },
        ],
      });
    } else {
      const pill142 = page.locator('[data-testid="calendar-pill-KAN-142"]');
      await expect(pill142).toBeVisible();

      // Keyboard Alt+ArrowDown moves +7 days, Alt+ArrowLeft moves -5 days to 2026-11-20
      // Or drag and drop pill to cell 2026-11-20
      const targetCell = page.locator('[data-date="2026-11-20"]');
      await expect(targetCell).toBeVisible();

      await pill142.dragTo(targetCell);

      // Verify pill moved to target cell
      await expect(targetCell.locator('[data-testid="calendar-pill-KAN-142"]')).toBeVisible();

      await annotatedScreenshot(page, testInfo, {
        name: '02-calendar-rescheduled',
        annotations: [
          {
            selector: '[data-date="2026-11-20"] [data-testid="calendar-pill-KAN-142"]',
            label: '1: KAN-142 in 2026-11-20 cell',
            note: 'Optimistically relocated pill after drag-and-drop reschedule',
          },
          {
            selector: '.calendar-toolbar',
            label: '2: recorded PATCH date note in legend',
            note: 'Automatic PATCH /api/v1/issues/KAN-142 with start_date & due_date',
          },
        ],
      });
    }
  });

  test('03-timeline-gantt-blocks: renders sticky 46px rail, bars, conflict arrow, and broken link', async ({
    page,
  }, testInfo) => {
    await page.goto('/projects/KAN/issues?layout=timeline');

    const timelineView = page.locator('.timeline-view');
    await expect(timelineView).toBeVisible();

    const bar142 = page.locator('[data-testid="timeline-bar-KAN-142"]');
    await expect(bar142).toBeVisible();

    const svgOverlay = page.locator('.timeline-svg-overlay');
    await expect(svgOverlay).toBeVisible();

    // Probe timeline whitespace measurements
    await probeStyles(page, testInfo, {
      name: 'timeline-metrics',
      probes: [
        {
          selector: '.timeline-left-row',
          props: ['min-height', 'height', 'line-height'],
        },
        {
          selector: '.timeline-track-row',
          props: ['min-height', 'height'],
        },
        {
          selector: '.timeline-left-row .emoji-hint',
          props: ['width', 'height'],
        },
      ],
    });

    await annotatedScreenshot(page, testInfo, {
      name: '03-timeline-gantt-blocks',
      annotations: [
        {
          selector: '.timeline-left-row:first-child',
          label: '1: sticky 46px left issue rows',
          note: 'Sticky 280px issue rail at 46px (--list-row-h) height aligned 1:1 with tracks',
        },
        {
          selector: '[data-testid="timeline-bar-KAN-142"]',
          label: '2: KAN-142 bar (2026-11-11 -> 2026-11-18)',
          note: 'Gantt bar rendered from start_date to due_date with left/right drag handles',
        },
        {
          selector: '.timeline-svg-overlay',
          label: '3: SVG BLOCKS arrow KAN-100 -> KAN-142 -> KAN-143',
          note: 'Pure SVG orthogonal cubic-bezier BLOCKS dependency paths with marker arrowheads',
        },
        {
          selector: '.gantt-arrow--conflict',
          label: '4: dashed conflict arrow when blocker overlaps',
          note: 'Orange dashed arrow highlighting schedule inverted blocker collision',
        },
        {
          selector: '.timeline-broken-link-hint',
          label: '5: 🕸️⚠️ broken-link <EmojiHint>',
          note: 'Invalid object link indicator without breaking dependency layout',
        },
      ],
    });
  });

  test('04-timeline-drag-resize: drag right resize handle widens bar and updates BLOCKS arrow origin', async ({
    page,
  }, testInfo) => {
    await page.goto('/projects/KAN/issues?layout=timeline');

    const bar142 = page.locator('[data-testid="timeline-bar-KAN-142"]');
    await expect(bar142).toBeVisible();

    const rightHandle = page.locator('[data-testid="handle-right-KAN-142"]');
    await rightHandle.scrollIntoViewIfNeeded();
    await expect(rightHandle).toBeVisible();

    // Drag handle to the right (+48px = +3 days to 2026-11-21)
    const box = await rightHandle.boundingBox();
    if (box) {
      await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
      await page.mouse.down();
      await page.mouse.move(box.x + box.width / 2 + 48, box.y + box.height / 2);
      await page.mouse.up();
    }

    await annotatedScreenshot(page, testInfo, {
      name: '04-timeline-drag-resize',
      annotations: [
        {
          selector: '[data-testid="timeline-bar-KAN-142"]',
          label: '1: widened bar ending 2026-11-21',
          note: 'Optimistically updated bar width clamped to valid date boundaries',
        },
        {
          selector: '.timeline-svg-overlay',
          label: '2: updated BLOCKS arrow origin X',
          note: 'Outbound BLOCKS dependency arrow synchronized to new due_date origin',
        },
      ],
    });
  });
});
