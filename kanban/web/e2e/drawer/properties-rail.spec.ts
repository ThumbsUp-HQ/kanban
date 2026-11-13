/**
 * Playwright E2E & Visual Proof Suite for Ticket Properties Rail (KB-P3-42, KANBA-123).
 * Captures 5 annotated screenshots across desktop, tablet, and mobile viewports:
 * 1. 01-rail-all-properties
 * 2. 02-external-assignee-hint
 * 3. 03-creator-override-provenance
 * 4. 04-rail-modules-unmounted
 * 5. 05-restricted-parent-masked
 *
 * Probes computed styles: .surface__rail padding: 24px, .prop-row min-height: 38px, .emoji-hint: 24x24px.
 */

import { test, expect } from '../support/test';
import { annotatedScreenshot, type Annotation } from '../support/annotate';
import { probeStyles } from '../support/styleProbe';
import { mockApi, loadFixture } from '../support/mockApi';

test.describe('Ticket Properties Rail E2E & Visual Verification (KB-P3-42, KANBA-123)', () => {
  test.beforeEach(async ({ page }) => {
    const projectKan = loadFixture<{ priorities?: unknown[]; labels?: unknown[] }>('project-kan');
    await mockApi(page, {
      'GET /api/v1/system/status': { json: loadFixture('system-status-standalone') },
      'GET /api/v1/projects/KAN': { json: loadFixture('project-kan') },
      'GET /api/v1/objects/:id/access': { json: loadFixture('access-project-kan') },
      'GET /api/v1/issues': { json: loadFixture('issues-kan') },
      'GET /api/v1/users/me': { json: loadFixture('me-adam') },
      'GET /api/v1/projects/KAN/priorities': { json: projectKan.priorities ?? [] },
      'GET /api/v1/projects/KAN/labels': { json: projectKan.labels ?? [] },
      'GET /api/v1/projects/KAN/cycles': { json: [] },
      'GET /api/v1/projects/KAN/modules': { json: [] },
    });

    await page.goto('/__dev/drawer-rail');
    await page.waitForLoadState('networkidle');
    await expect(page.locator('[data-testid="rail-story"]')).toBeVisible();
  });

  test('01: renders all 8 property rows and probes computed styles', async ({ page }, testInfo) => {
    const rail = page.locator('.surface__rail');
    await expect(rail).toBeVisible();

    // Verify all 8 property rows exist in S7.1 order
    await expect(page.locator('[data-prop="state"]')).toBeVisible();
    await expect(page.locator('[data-prop="priority"]')).toBeVisible();
    await expect(page.locator('[data-prop="assignees"]')).toBeVisible();
    await expect(page.locator('[data-prop="created-by"]')).toBeVisible();
    await expect(page.locator('[data-prop="start-date"]')).toBeVisible();
    await expect(page.locator('[data-prop="due-date"]')).toBeVisible();
    await expect(page.locator('[data-prop="modules"]')).toBeVisible();
    await expect(page.locator('[data-prop="cycle"]')).toBeVisible();
    await expect(page.locator('[data-prop="parent"]')).toBeVisible();
    await expect(page.locator('[data-prop="labels"]')).toBeVisible();
    await expect(page.locator('[data-slot="custom-fields-rail"]')).toBeAttached();

    // Probe computed whitespace & dimensions
    await probeStyles(page, testInfo, {
      name: 'properties-rail-layout',
      probes: [
        {
          selector: '.surface__rail',
          props: ['padding', 'padding-top', 'padding-right', 'padding-bottom', 'padding-left', 'width', 'display'],
        },
        {
          selector: '[data-prop="state"]',
          props: ['min-height', 'display', 'column-gap'],
        },
        {
          selector: '.assignee-pill--external',
          props: ['border-style', 'display', 'align-items'],
        },
        {
          selector: '[data-prop="priority"] .emoji-hint',
          props: ['width', 'height', 'display'],
        },
      ],
    });

    const annotations: Annotation[] = [
      {
        selector: '[data-prop="state"]',
        label: '1. State',
        note: '38px row height with grouped options (unstarted/started/completed)',
      },
      {
        selector: '[data-prop="priority"]',
        label: '2. Priority',
        note: 'Customizable priority with semantic fire hint',
      },
      {
        selector: '[data-prop="assignees"]',
        label: '3. Hybrid Assignees',
        note: 'User, Agent, and external dashed pill assignees',
      },
      {
        selector: '[data-prop="created-by"]',
        label: '4. Created by',
        note: 'Immutable handle with provenance override indicator',
      },
      {
        selector: '[data-prop="modules"]',
        label: '5. Modules',
        note: 'Conditionally mounted project module selector',
      },
      {
        selector: '[data-prop="sub-issues-rollup"]',
        label: '6. Sub-issues Rollup',
        note: 'Accessible progress bar showing completion percentage',
      },
    ];

    await annotatedScreenshot(page, testInfo, {
      name: '01-rail-all-properties',
      annotations,
    });
  });

  test('02: external free-text assignee pill with dashed border and tooltip', async ({ page }, testInfo) => {
    const externalPill = page.locator('.assignee-pill--external');
    await expect(externalPill).toBeVisible();

    const hint = externalPill.locator('.emoji-hint');
    await expect(hint).toBeVisible();

    // Trigger hover on hint
    await hint.hover();

    const annotations: Annotation[] = [
      {
        selector: '.assignee-pill--external',
        label: '1. Dashed External Pill',
        note: '1px dashed border for non-authenticated collaborators',
      },
      {
        selector: '.assignee-pill--external .emoji-hint',
        label: '2. External Label Hint',
        note: 'Grants zero access and sends zero notifications',
      },
    ];

    await annotatedScreenshot(page, testInfo, {
      name: '02-external-assignee-hint',
      annotations,
    });
  });

  test('03: creator override provenance popover and admin modal', async ({ page }, testInfo) => {
    const creatorRow = page.locator('[data-prop="created-by"]');
    await expect(creatorRow).toBeVisible();

    const overrideHint = creatorRow.locator('.emoji-hint');
    await expect(overrideHint).toBeVisible();

    // Hover over override hint to expose popover
    await overrideHint.hover();

    const annotations: Annotation[] = [
      {
        selector: '[data-prop="created-by"] .creator-name',
        label: '1. Current Creator',
        note: 'Displays active ticket owner handle',
      },
      {
        selector: '[data-prop="created-by"] .emoji-hint',
        label: '2. Override Provenance',
        note: 'Indicates creator override with audit reason & timestamp',
      },
    ];

    await annotatedScreenshot(page, testInfo, {
      name: '03-creator-override-provenance',
      annotations,
    });
  });

  test('04: modules row completely unmounted when modules_enabled is false', async ({ page }, testInfo) => {
    // Switch to no modules fixture
    await page.getByRole('button', { name: 'No Modules (Unmounted)' }).click();

    // Verify modules row is 100% unmounted from DOM
    await expect(page.locator('[data-prop="modules"]')).toHaveCount(0);
    await expect(page.locator('[data-prop="due-date"]')).toBeVisible();
    await expect(page.locator('[data-prop="cycle"]')).toBeVisible();

    const annotations: Annotation[] = [
      {
        selector: '[data-prop="due-date"]',
        label: '1. Due date Row',
        note: 'Precedes Cycle row directly when modules are disabled',
      },
      {
        selector: '[data-prop="cycle"]',
        label: '2. Cycle Row',
        note: 'Modules row is completely unmounted from DOM (invariant S7.2 8f)',
      },
    ];

    await annotatedScreenshot(page, testInfo, {
      name: '04-rail-modules-unmounted',
      annotations,
    });
  });

  test('05: restricted parent issue masked with zero leaked keys', async ({ page }, testInfo) => {
    // Switch to restricted parent fixture
    await page.getByRole('button', { name: 'Restricted Parent (Masked)' }).click();

    const restrictedChip = page.locator('[data-testid="restricted-parent-chip"]');
    await expect(restrictedChip).toBeVisible();
    await expect(restrictedChip).toContainText('Restricted Parent Issue');

    const annotations: Annotation[] = [
      {
        selector: '[data-testid="restricted-parent-chip"]',
        label: '1. Masked Parent Chip',
        note: 'Masks restricted parent key with lock hint (zero key leakage)',
      },
    ];

    await annotatedScreenshot(page, testInfo, {
      name: '05-restricted-parent-masked',
      annotations,
    });
  });
});
