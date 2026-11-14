/**
 * Playwright E2E Verification & Design Proofs for Ticket Header & Overflow Actions (KB-P3-43).
 * Validates Subscribe 🔔, Link & Object Graph 🔗, Archive eligibility, Make a copy,
 * and Delete blast radius modal across Desktop (1440x900), Tablet (1024x768), and Mobile (390x844).
 */

import { test, expect } from '../support/test';
import { annotatedScreenshot } from '../support/annotate';
import { probeStyles } from '../support/styleProbe';
import { mockApi, loadFixture } from '../support/mockApi';

test.describe('Ticket Header & Overflow Actions E2E & Visual Proofs (KB-P3-43)', () => {
  test.beforeEach(async ({ page, context }) => {
    // Set CSRF cookie for mutating requests
    await context.addCookies([
      {
        name: 'kb_csrf',
        value: 'test-csrf-token-e2e',
        domain: '127.0.0.1',
        path: '/',
      },
    ]);

    // Stateful subscription variables for refetching
    let isSubscribed = false;
    let mutedEventTypes: string[] = [];

    // Install mock API handlers for all drawer action surfaces and app shell queries
    await mockApi(page, {
      'GET /api/v1/auth/me': { json: { handle: 'adamoutler' } },
      'GET /api/v1/objects/:id/access': { json: loadFixture('access-project-kan') },
      'GET /api/v1/projects/:id': { json: loadFixture('project-kan') },
      'GET /api/v1/system/status': loadFixture('system-status-prod'),
      'GET /api/v1/me': loadFixture('me-adam'),
      'GET /api/v1/users/me': loadFixture('me-adam'),
      'GET /api/v1/issues/:id/subscription': () => ({
        json: {
          subscribed: isSubscribed,
          muted_event_types: mutedEventTypes,
          source: isSubscribed ? 'manual' : null,
        },
      }),
      'PUT /api/v1/issues/:id/subscription': () => {
        isSubscribed = true;
        return {
          json: {
            subscribed: true,
            muted_event_types: mutedEventTypes,
            source: 'manual',
          },
        };
      },
      'PATCH /api/v1/issues/:id/subscription': (req) => {
        const body = req.body as { muted_event_types?: string[] } | null;
        if (body && Array.isArray(body.muted_event_types)) {
          mutedEventTypes = body.muted_event_types;
        }
        return {
          json: {
            subscribed: isSubscribed,
            muted_event_types: mutedEventTypes,
            source: isSubscribed ? 'manual' : null,
          },
        };
      },
      'DELETE /api/v1/issues/:id/subscription': () => {
        isSubscribed = false;
        mutedEventTypes = [];
        return { status: 204 };
      },
      'GET /api/v1/objects/:id/canonical-url': { json: loadFixture('canonical-kan-142') },
      'GET /api/v1/objects/:id/links': { json: loadFixture('links-kan-142') },
      'POST /api/v1/objects/:id/links': {
        status: 201,
        json: { id: 'link-new', link_type: 'RELATES_TO', link_state: 'ACTIVE' },
      },
      'DELETE /api/v1/links/:id': { status: 204 },
      'POST /api/v1/issues/:id/copy': {
        status: 201,
        json: {
          issue: { key: 'KAN-999', summary: '[Copy] Harden OAuth and MCP token security' },
          copied_sub_issues: [],
          skipped: { restricted_sub_issues: 0 },
        },
      },
      'POST /api/v1/issues/:id/archive': { status: 200, json: { archived: true } },
      'POST /api/v1/issues/:id/unarchive': { status: 200, json: { archived: false } },
      'GET /api/v1/issues/:id/delete-preview': { json: loadFixture('delete-preview-kan-142') },
      'DELETE /api/v1/issues/:id': {
        status: 200,
        json: {
          issue_key: 'KAN-142',
          deleted_at: '2026-11-12T00:00:00Z',
          purge_after: '2026-12-12T00:00:00Z',
        },
      },
    });

    const response = await page.goto('/__dev/drawer-actions');
    expect(response).not.toBeNull();
    expect(response?.status()).toBe(200);
    await expect(page.locator('[data-testid="drawer-actions-story"]')).toBeVisible();
  });

  test('01: header subscribe action and notification mute popover', async ({ page }, testInfo) => {
    const subscribeBtn = page.locator('[data-testid="subscribe-toggle-btn"]');
    await expect(subscribeBtn).toBeVisible();
    await expect(subscribeBtn).toContainText('Subscribe');

    // Probe styles for button height and surface header
    await probeStyles(page, testInfo, {
      name: 'subscribe-btn',
      probes: [
        {
          selector: '[data-testid="subscribe-toggle-btn"]',
          props: ['min-height', 'height', 'padding-top', 'padding-bottom'],
        },
      ],
    });

    await probeStyles(page, testInfo, {
      name: 'surface-header',
      probes: [
        {
          selector: '.drawer-actions-story__header',
          props: ['min-height', 'height', 'padding-top', 'padding-bottom'],
        },
      ],
    });

    // Toggle to subscribed
    await subscribeBtn.click();
    await expect(subscribeBtn).toContainText('Subscribed');

    // Click mute trigger chevron to open popover
    const muteTrigger = page.locator('[data-testid="subscribe-mute-trigger"]');
    await expect(muteTrigger).toBeVisible();
    await muteTrigger.click();

    const mutePopover = page.locator('[data-testid="mute-popover"]');
    await expect(mutePopover).toBeVisible();

    // Toggle mute checkbox
    const stateCheckbox = page.locator('[data-testid="mute-checkbox-ISSUE_STATE_CHANGED"]');
    await expect(stateCheckbox).toBeVisible();
    await stateCheckbox.click();
    await expect(stateCheckbox).toBeChecked();

    await annotatedScreenshot(page, testInfo, {
      name: '01-header-subscribe-mute',
      annotations: [
        {
          selector: '[data-testid="subscribe-toggle-btn"]',
          label: 'Subscribe Toggle',
          note: 'Active subscribed state',
        },
        {
          selector: '[data-testid="subscribe-mute-trigger"]',
          label: 'Mute Chevron',
          note: 'Opens notification settings',
        },
        {
          selector: '[data-testid="mute-popover"]',
          label: 'Mute Popover',
          note: '7 customizable event types',
        },
      ],
    });
  });

  test('02: link graph action and typed object links popover', async ({ page }, testInfo) => {
    const linkTrigger = page.locator('[data-testid="link-graph-trigger"]');
    await expect(linkTrigger).toBeVisible();
    await linkTrigger.click();

    const linkPopover = page.locator('[data-testid="link-graph-popover"]');
    await expect(linkPopover).toBeVisible();

    // Outbound link shows masked restricted object
    const outboundItem = page.locator('[data-testid="link-item-link-out-1"]');
    await expect(outboundItem).toBeVisible();
    await expect(outboundItem).toContainText('Restricted Object');

    // Inbound link shows broken link indicator
    const inboundList = page.locator('[data-testid="inbound-links-list"]');
    await expect(inboundList).toBeVisible();
    await expect(inboundList).toContainText('KAN-10');

    // Add link form
    await expect(page.locator('[data-testid="link-type-select"]')).toBeVisible();
    await expect(page.locator('[data-testid="link-target-input"]')).toBeVisible();

    await annotatedScreenshot(page, testInfo, {
      name: '02-link-graph-popover',
      annotations: [
        {
          selector: '[data-testid="copy-canonical-url-btn"]',
          label: 'Copy URL',
          note: 'Server-authoritative canonical URL',
        },
        {
          selector: '[data-testid="copy-markdown-btn"]',
          label: 'Copy Markdown',
          note: 'Cmd+Shift+C link chord',
        },
        {
          selector: '[data-testid="link-item-link-out-1"]',
          label: 'Restricted Object',
          note: 'Masked unreadable far endpoint',
        },
        {
          selector: '[data-testid="inbound-links-list"]',
          label: 'Inbound Links',
          note: 'Broken link indicator present',
        },
      ],
    });
  });

  test('03: overflow menu archive disabled reason on started vs enabled on completed', async ({
    page,
  }, testInfo) => {
    const overflowTrigger = page.locator('[data-testid="issue-overflow-trigger"]');
    await expect(overflowTrigger).toBeVisible();
    await overflowTrigger.click();

    const menu = page.locator('[data-testid="issue-overflow-menu"]');
    await expect(menu).toBeVisible();

    // Probe styles for menu and menu item
    await probeStyles(page, testInfo, {
      name: 'overflow-menu',
      probes: [
        {
          selector: '[data-testid="issue-overflow-menu"]',
          props: ['min-height', 'height', 'padding-top', 'padding-bottom', 'background-color'],
        },
      ],
    });

    await probeStyles(page, testInfo, {
      name: 'overflow-menu-item',
      probes: [
        {
          selector: '[data-testid="overflow-make-copy-btn"]',
          props: ['min-height', 'height', 'padding-top', 'padding-bottom'],
        },
      ],
    });

    // Check archive disabled with exact visible sublabel
    const archiveBtn = page.locator('[data-testid="overflow-archive-btn"]');
    await expect(archiveBtn).toHaveAttribute('aria-disabled', 'true');
    const reasonLabel = page.locator('[data-testid="archive-disabled-reason"]');
    await expect(reasonLabel).toBeVisible();
    await expect(reasonLabel).toHaveText('Only completed or canceled work items can be archived');

    await annotatedScreenshot(page, testInfo, {
      name: '03-overflow-archive-disabled-reason',
      annotations: [
        {
          selector: '[data-testid="overflow-make-copy-btn"]',
          label: 'Make a Copy',
          note: 'Opens copy dialog',
        },
        {
          selector: '[data-testid="overflow-toggle-fullscreen-btn"]',
          label: 'Toggle Full Screen',
          note: 'Zero-remount surface toggle',
        },
        {
          selector: '[data-testid="overflow-archive-btn"]',
          label: 'Archive Action',
          note: 'Disabled with explanatory rule',
        },
        {
          selector: '[data-testid="overflow-delete-btn"]',
          label: 'Delete Action',
          note: 'Pre-flight blast radius modal',
        },
      ],
    });

    // Close menu, select completed task KAN-143, and verify archive enabled
    await page.keyboard.press('Escape');
    await expect(menu).not.toBeVisible();

    await page.locator('[data-testid="select-done-btn"]').click();
    await overflowTrigger.click();
    await expect(archiveBtn).toHaveAttribute('aria-disabled', 'false');
    await expect(reasonLabel).not.toBeVisible();
  });

  test('04: make a copy dialog with 3 options and creator attribution', async ({ page }, testInfo) => {
    const overflowTrigger = page.locator('[data-testid="issue-overflow-trigger"]');
    await overflowTrigger.click();

    const makeCopyBtn = page.locator('[data-testid="overflow-make-copy-btn"]');
    await makeCopyBtn.click();

    const copyDialog = page.locator('[data-testid="make-copy-dialog"]');
    await expect(copyDialog).toBeVisible();

    await probeStyles(page, testInfo, {
      name: 'make-copy-dialog',
      probes: [
        {
          selector: '[data-testid="make-copy-dialog"]',
          props: ['min-height', 'height', 'padding-top', 'padding-bottom', 'background-color'],
        },
      ],
    });

    // Verify preview and creator attribution notice
    const preview = page.locator('[data-testid="copy-preview-title"]');
    await expect(preview).toContainText('[Copy] Harden OAuth and MCP token security');

    const creatorNotice = page.locator('[data-testid="copy-creator-notice"]');
    await expect(creatorNotice).toHaveText('Created by will be set to @adamoutler');

    // 3 checkboxes default unchecked
    await expect(page.locator('[data-testid="copy-include-sub-issues"]')).not.toBeChecked();
    await expect(page.locator('[data-testid="copy-include-attachments"]')).not.toBeChecked();
    await expect(page.locator('[data-testid="copy-link-relates-to"]')).not.toBeChecked();

    await annotatedScreenshot(page, testInfo, {
      name: '04-make-copy-dialog',
      annotations: [
        {
          selector: '[data-testid="copy-preview-title"]',
          label: 'Summary Preview',
          note: 'Clamped to 500 characters',
        },
        {
          selector: '[data-testid="copy-creator-notice"]',
          label: 'Creator Attribution',
          note: 'Attributed to active user handle',
        },
        {
          selector: '[data-testid="confirm-copy-btn"]',
          label: 'Make Copy Button',
          note: 'Submits duplicate request',
        },
      ],
    });

    // Close dialog
    await page.locator('.modal-close-btn').click();
    await expect(copyDialog).not.toBeVisible();
  });

  test('05: delete blast radius modal with retention notice and destructive action', async ({
    page,
  }, testInfo) => {
    const overflowTrigger = page.locator('[data-testid="issue-overflow-trigger"]');
    await overflowTrigger.click();

    const deleteBtn = page.locator('[data-testid="overflow-delete-btn"]');
    await deleteBtn.click();

    const deleteModal = page.locator('[data-testid="delete-blast-radius-modal"]');
    await expect(deleteModal).toBeVisible();

    await probeStyles(page, testInfo, {
      name: 'blast-radius-modal',
      probes: [
        {
          selector: '[data-testid="delete-blast-radius-modal"]',
          props: ['min-height', 'height', 'padding-top', 'padding-bottom', 'background-color'],
        },
      ],
    });

    // Blast radius summary counts
    const summaryText = page.locator('[data-testid="blast-radius-summary-text"]');
    await expect(summaryText).toContainText('2 sub-issues unparented, 3 inbound object_links flagged');

    // Soft-trash retention notice
    const retentionNotice = page.locator('[data-testid="soft-trash-retention-notice"]');
    await expect(retentionNotice).toHaveText(
      'Moved to trash for 30 days before permanent audited purge.',
    );

    // Destructive confirm button
    const confirmBtn = page.locator('[data-testid="confirm-delete-btn"]');
    await expect(confirmBtn).toBeVisible();
    await expect(confirmBtn).toContainText('Move KAN-142 to trash');

    await annotatedScreenshot(page, testInfo, {
      name: '05-delete-blast-radius-modal',
      annotations: [
        {
          selector: '[data-testid="blast-radius-summary-text"]',
          label: 'Blast Radius Counts',
          note: 'Pre-flight unparented & flagged counts',
        },
        {
          selector: '[data-testid="soft-trash-retention-notice"]',
          label: 'Soft-Trash Notice',
          note: '30-day retention before audited purge',
        },
        {
          selector: '[data-testid="confirm-delete-btn"]',
          label: 'Destructive Confirm',
          note: 'Sends Kb-Blast-Hash concurrency header',
        },
      ],
    });

    // Close modal
    await page.locator('.modal-close-btn').click();
    await expect(deleteModal).not.toBeVisible();
  });
});
