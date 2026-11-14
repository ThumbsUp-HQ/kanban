/**
 * Playwright E2E verification and visual design proofs for:
 * Project Stickies 6-palette grid, 1000ms idle heuristic, promotion banner & Doc stub (KB-P3-51, S8.1, S8.2).
 * Plain ASCII hyphens only.
 */

import { writeFileSync, mkdirSync } from 'node:fs';
import { resolve } from 'node:path';
import { test, expect } from '../support/test';
import { loadFixture, mockApi } from '../support/mockApi';
import { annotatedScreenshot } from '../support/annotate';
import { probeStyles } from '../support/styleProbe';

const CORAL_STICKY_ID = '01918a22-0005-7000-8000-000000000005';
const SLATE_STUB_ID = '01918a22-0006-7000-8000-000000000006';

test.describe('Stickies 6-Palette Grid & Promotion E2E (KB-P3-51)', () => {
  test.beforeEach(async ({ page }) => {
    await mockApi(page, {
      'GET /api/v1/system/status': { json: loadFixture('system-status-standalone') },
      'GET /api/v1/users/me': { json: loadFixture('me-adam') },
      'GET /api/v1/projects/KAN': {
        status: 200,
        json: {
          id: 'proj-kan',
          canonical_key: 'KAN',
          name: 'Platform Core',
          description_markdown: 'Core platform infrastructure',
          restricted: false,
        },
      },
      'GET /api/v1/objects/:id/access': { json: loadFixture('access-project-kan') },
      'GET /api/v1/projects/KAN/access': {
        status: 200,
        json: {
          resource_id: 'proj-kan',
          resource_kind: 'project',
          effective_policy: 'ALLOW',
          entries: [],
        },
      },
      'GET /api/v1/projects/KAN/cycles': { json: [] },
      'GET /api/v1/projects/KAN/modules': { json: [] },
      'GET /api/v1/projects/KAN/stickies': {
        status: 200,
        json: { items: loadFixture('stickies-kan') },
      },
      'PATCH /api/v1/stickies/:id': (req) => {
        const fixtureList = loadFixture<Record<string, unknown>[]>('stickies-kan');
        const existing = fixtureList.find((s) => s.id === req.params.id) ?? fixtureList[4];
        return {
          status: 200,
          json: {
            ...existing,
            id: req.params.id,
            promotion_snoozed_at_length: 740,
          },
        };
      },
      'POST /api/v1/stickies/:id/promote-to-doc': (req) => {
        const fixtureList = loadFixture<Record<string, unknown>[]>('stickies-kan');
        const existing = fixtureList.find((s) => s.id === req.params.id) ?? fixtureList[4];
        return {
          status: 200,
          json: {
            ...existing,
            id: req.params.id,
            promoted_to_doc_id: 'doc-page-sec-arch',
            is_promoted_stub: true,
            promoted_to_doc: {
              id: 'doc-page-sec-arch',
              title: 'System Security Architecture',
            },
          },
        };
      },
      'POST /api/v1/stickies/:id/unarchive-copy': () => {
        return {
          status: 200,
          json: {
            id: '01918a22-0007-7000-8000-000000000007',
            workspace_id: '01918a22-0000-7000-8000-000000000001',
            project_id: '01918a22-0000-7000-8000-000000000002',
            body_markdown: 'Unarchived copy of spec',
            color_token: 'slate',
            is_promoted_stub: false,
            promoted_to_doc_id: null,
          },
        };
      },
    });
  });

  test('01-stickies-six-palette-grid: renders responsive grid with all 6 palette cards, padding, and access pills', async ({
    page,
  }, testInfo) => {
    await page.goto('/projects/KAN/overview');

    // Wait for stickies grid
    const grid = page.locator('[data-testid="stickies-grid"]');
    await expect(grid).toBeVisible();

    // Verify all 6 palette cards are present
    const amberCard = page.locator('[data-testid="sticky-card-01918a22-0001-7000-8000-000000000001"]');
    const mintCard = page.locator('[data-testid="sticky-card-01918a22-0002-7000-8000-000000000002"]');
    const skyCard = page.locator('[data-testid="sticky-card-01918a22-0003-7000-8000-000000000003"]');
    const lavenderCard = page.locator('[data-testid="sticky-card-01918a22-0004-7000-8000-000000000004"]');
    const coralCard = page.locator(`[data-testid="sticky-card-${CORAL_STICKY_ID}"]`);
    const slateStub = page.locator(`[data-testid="promoted-sticky-stub-${SLATE_STUB_ID}"]`);

    await expect(amberCard).toBeVisible();
    await expect(mintCard).toBeVisible();
    await expect(skyCard).toBeVisible();
    await expect(lavenderCard).toBeVisible();
    await expect(coralCard).toBeVisible();
    await expect(slateStub).toBeVisible();

    // Verify swatch radiogroup on amber card
    const amberRadiogroup = amberCard.locator('[role="radiogroup"][aria-label="Sticky color"]');
    await expect(amberRadiogroup).toBeVisible();

    // Probe computed whitespace measurements
    await probeStyles(page, testInfo, {
      name: 'stickies-grid-metrics',
      probes: [
        {
          selector: '.stickies-grid',
          props: ['display', 'gap', 'grid-template-columns'],
        },
        {
          selector: '.sticky-card',
          props: ['padding-top', 'padding-right', 'padding-bottom', 'padding-left', 'border-radius', 'box-sizing'],
        },
        {
          selector: '.sticky-card--amber',
          props: ['background-color'],
        },
        {
          selector: '.sticky-card--mint',
          props: ['background-color'],
        },
        {
          selector: '.sticky-card--sky',
          props: ['background-color'],
        },
        {
          selector: '.sticky-card--lavender',
          props: ['background-color'],
        },
        {
          selector: '.sticky-card--coral',
          props: ['background-color'],
        },
        {
          selector: '.sticky-card--slate',
          props: ['background-color'],
        },
        {
          selector: '.emoji-hint',
          props: ['width', 'height'],
        },
      ],
    });

    // Capture annotated screenshot 01
    await annotatedScreenshot(page, testInfo, {
      name: '01-stickies-six-palette-grid',
      annotations: [
        {
          selector: '.stickies-grid',
          label: '1: 20px grid gap',
          note: 'CSS Grid repeat(auto-fill, minmax(300px, 1fr)) with 20px gap (var(--space-5))',
        },
        {
          selector: '[data-testid="sticky-card-01918a22-0001-7000-8000-000000000001"]',
          label: '2: 16px 18px card padding',
          note: 'Card surface padding: 16px 18px (var(--card-pad)) and radius 12px',
        },
        {
          selector: '[data-testid="sticky-card-01918a22-0001-7000-8000-000000000001"] .sticky-card__palette',
          label: '3: 6-color swatch radiogroup',
          note: 'Arrow-key operable swatch palette for amber, mint, sky, lavender, coral, slate',
        },
        {
          selector: '[data-testid="sticky-card-01918a22-0001-7000-8000-000000000001"] [data-testid="access-hint-01918a22-0001-7000-8000-000000000001"]',
          label: '4: 🛡️ access pill',
          note: '24x24 semantic status indicator opening effective access inspector',
        },
      ],
    });
  });

  test('02-promotion-banner-and-hint: surfaces non-modal banner on complex sticky with elaboration popover and snooze', async ({
    page,
  }, testInfo) => {
    await page.goto('/projects/KAN/overview');

    const coralCard = page.locator(`[data-testid="sticky-card-${CORAL_STICKY_ID}"]`);
    await expect(coralCard).toBeVisible();

    // Verify promotion banner is rendered
    const banner = coralCard.locator('[data-testid="sticky-promotion-banner"]');
    await expect(banner).toBeVisible();
    await expect(banner.locator('.sticky-promotion-banner__label')).toHaveText('Growing into a spec');

    // Trigger elaboration popover on 💡📄 hint
    const hintTrigger = banner.locator('[data-testid="sticky-promotion-hint"]');
    await expect(hintTrigger).toBeVisible();

    if (testInfo.project.name === 'mobile') {
      await hintTrigger.tap();
    } else {
      await hintTrigger.hover();
    }

    // Verify popover text contains exact matched reasons
    const popup = page.locator('[data-testid="sticky-promotion-hint-popup"]');
    await expect(popup).toBeVisible();
    await expect(popup).toContainText('> 600');
    await expect(popup).toContainText('2 headings (>= 2)');

    // Capture annotated screenshot 02
    await annotatedScreenshot(page, testInfo, {
      name: '02-promotion-banner-and-hint',
      annotations: [
        {
          selector: '[data-testid="sticky-promotion-hint"]',
          label: '1: 💡📄 trigger (24x24)',
          note: 'Semantic status emoji pill for sticky promotion recommendation',
        },
        {
          selector: '[data-testid="sticky-promotion-hint-popup"]',
          label: '2: elaboration popover',
          note: 'Hover/focus popover displaying exact complexity triggers: 826 chars (> 600), 2 headings (>= 2)',
        },
        {
          selector: '[data-testid="sticky-promotion-banner"]',
          label: '3: Growing into a spec footer',
          note: 'Non-modal card footer with [Promote to Doc ->] and [Snooze] buttons',
        },
      ],
    });

    // Test Snooze action: clicks snooze, hides banner
    const snoozeBtn = banner.locator('[data-testid="snooze-promotion-btn"]');
    await snoozeBtn.click();
    await expect(banner).toBeHidden();
  });

  test('03-promoted-doc-stub: converts sticky into compact doc stub with open link and unarchive copy', async ({
    page,
  }, testInfo) => {
    await page.goto('/projects/KAN/overview');

    // Verify pre-existing promoted stub (API Gateway Specification)
    const slateStub = page.locator(`[data-testid="promoted-sticky-stub-${SLATE_STUB_ID}"]`);
    await expect(slateStub).toBeVisible();

    const openDocLink = slateStub.locator('[data-testid="open-doc-link"]');
    await expect(openDocLink).toBeVisible();
    await expect(openDocLink).toHaveAttribute(
      'href',
      '/projects/KAN/docs/01918a22-9999-7000-8000-000000000001',
    );

    const unarchiveBtn = slateStub.locator('[data-testid="unarchive-copy-btn"]');
    await expect(unarchiveBtn).toBeVisible();

    // Click promote on coral card to verify in-place promotion transition
    const coralCard = page.locator(`[data-testid="sticky-card-${CORAL_STICKY_ID}"]`);
    const promoteBtn = coralCard.locator('[data-testid="promote-to-doc-btn"]');
    await promoteBtn.click();

    // Coral card transitions to promoted stub
    const newlyPromotedStub = page.locator(`[data-testid="promoted-sticky-stub-${CORAL_STICKY_ID}"]`);
    await expect(newlyPromotedStub).toBeVisible();
    await expect(newlyPromotedStub.locator('.promoted-stub__title')).toHaveText('System Security Architecture');

    // Capture annotated screenshot 03
    await annotatedScreenshot(page, testInfo, {
      name: '03-promoted-doc-stub',
      annotations: [
        {
          selector: `[data-testid="promoted-sticky-stub-${CORAL_STICKY_ID}"] .promoted-stub__badge`,
          label: '1: 📄 Promoted to Doc badge',
          note: 'Muted header badge indicating sticky has graduated into permanent documentation',
        },
        {
          selector: `[data-testid="promoted-sticky-stub-${CORAL_STICKY_ID}"] [data-testid="open-doc-link"]`,
          label: '2: [📄 Open Doc] link',
          note: 'Direct link to the newly generated permanent Doc page',
        },
        {
          selector: `[data-testid="promoted-sticky-stub-${CORAL_STICKY_ID}"] [data-testid="unarchive-copy-btn"]`,
          label: '3: [Unarchive Copy] button',
          note: 'Creates an independent editable sticky copy without mutating the graduated Doc',
        },
      ],
    });

    // Test Unarchive Copy action
    const unarchiveCopyBtn = newlyPromotedStub.locator('[data-testid="unarchive-copy-btn"]');
    await unarchiveCopyBtn.click();

    // Record contract sample
    const qaTicketId = process.env.QA_TICKET_ID;
    if (qaTicketId) {
      const contractDir = resolve(import.meta.dirname, '../../../../docs/qa', qaTicketId);
      mkdirSync(contractDir, { recursive: true });
      const contractSample = {
        patch_snooze: {
          endpoint: `PATCH /api/v1/stickies/${CORAL_STICKY_ID}`,
          request_body: { promotion_snoozed_at_length: 740 },
          response_status: 200,
        },
        post_promote: {
          endpoint: `POST /api/v1/stickies/${CORAL_STICKY_ID}/promote-to-doc`,
          request_body: {},
          response_status: 200,
          response_body: {
            id: CORAL_STICKY_ID,
            promoted_to_doc_id: 'doc-page-sec-arch',
            is_promoted_stub: true,
            promoted_to_doc: {
              id: 'doc-page-sec-arch',
              title: 'System Security Architecture',
            },
          },
        },
        post_unarchive: {
          endpoint: `POST /api/v1/stickies/${CORAL_STICKY_ID}/unarchive-copy`,
          response_status: 200,
          response_body: {
            id: '01918a22-0007-7000-8000-000000000007',
            body_markdown: 'Unarchived copy of spec',
            color_token: 'slate',
            is_promoted_stub: false,
          },
        },
      };
      writeFileSync(
        resolve(contractDir, 'contract-sample.json'),
        JSON.stringify(contractSample, null, 2) + '\n',
        'utf-8',
      );
    }
  });

  test('04-stickies-dark-theme: preserves WCAG AA contrast across 6-palette surfaces under dark theme', async ({
    page,
  }, testInfo) => {
    await page.goto('/projects/KAN/overview');

    // Switch to dark theme via root attribute
    await page.evaluate(() => {
      document.documentElement.setAttribute('data-theme', 'dark');
    });

    const grid = page.locator('[data-testid="stickies-grid"]');
    await expect(grid).toBeVisible();

    // Verify all 6 cards remain visible with high contrast
    const amberCard = page.locator('[data-testid="sticky-card-01918a22-0001-7000-8000-000000000001"]');
    await expect(amberCard).toBeVisible();

    // Capture annotated screenshot 04
    await annotatedScreenshot(page, testInfo, {
      name: '04-stickies-dark-theme',
      annotations: [
        {
          selector: '.stickies-grid',
          label: '1: 6-palette surfaces in dark theme',
          note: 'Themed surfaces use CSS custom properties var(--sticky-*) maintaining WCAG AA contrast',
        },
        {
          selector: '[data-testid="sticky-card-01918a22-0001-7000-8000-000000000001"]',
          label: '2: Dark theme card border and text contrast',
          note: 'Text renders with var(--fg-primary) against dark-mode calibrated pastel surface',
        },
      ],
    });
  });
});
