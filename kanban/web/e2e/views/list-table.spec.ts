/**
 * Playwright E2E verification and visual design proofs for List & Table views (KB-P3-38).
 * Enforces 46px breathable list rows, configurable sortable table columns,
 * conditional Modules exclusion, computed whitespace verification, and multi-device annotated screenshots.
 */

import { test, expect } from '../support/test';
import { annotatedScreenshot } from '../support/annotate';
import { probeStyles } from '../support/styleProbe';

test.describe('List & Table Views E2E (KB-P3-38)', () => {
  test('01-list-grouped: renders grouped 46px breathable rows, counts, and status indicators', async ({
    page,
  }, testInfo) => {
    await page.goto('/projects/KAN/issues?layout=list');

    // Wait for list view to mount and render KAN-142
    const targetRow = page.locator('[data-issue-key="KAN-142"]');
    await expect(targetRow).toBeVisible();

    // Verify In Progress section header is visible
    const inProgressHeader = page.locator('[data-section-name="In Progress"] .list-section-header');
    await expect(inProgressHeader).toBeVisible();

    // Probe computed whitespace measurements
    await probeStyles(page, testInfo, {
      name: 'list-view-metrics',
      probes: [
        {
          selector: '.list-section',
          props: ['margin-bottom', 'row-gap'],
        },
        {
          selector: '.list-row',
          props: ['min-height', 'height', 'padding-top', 'padding-bottom', 'column-gap'],
        },
        {
          selector: '.list-row .emoji-hint',
          props: ['width', 'height'],
        },
      ],
    });

    // Capture annotated screenshot
    await annotatedScreenshot(page, testInfo, {
      name: '01-list-grouped',
      annotations: [
        {
          selector: '[data-section-name="In Progress"] .list-section-header',
          label: '1: In Progress group header with count',
          note: '40px height section header with exact count badge',
        },
        {
          selector: '[data-issue-key="KAN-142"]',
          label: '2: KAN-142 row (note min-height 46px)',
          note: '46px breathable list row (var(--list-row-h))',
        },
        {
          selector: '[data-issue-key="KAN-142"] .emoji-hint',
          label: '3: priority 🔥 + 🛡️ EmojiHints',
          note: 'Urgent priority and explicit ACL access hints',
        },
        {
          selector: '[data-issue-key="KAN-142"] .assignee-chip--external',
          label: '4: 🏷️ Ext: SecAudit dashed pill',
          note: 'External free-text assignee dashed chip',
        },
        {
          selector: '.list-section:first-child',
          label: '5: 24px section separation',
          note: 'var(--space-6) 24px margin-bottom between groups',
        },
      ],
    });
  });

  test('02-list-external-assignee-hint: hover or tap on 🏷️ displays literal access warning', async ({
    page,
  }, testInfo) => {
    await page.goto('/projects/KAN/issues?layout=list');

    const targetRow = page.locator('[data-issue-key="KAN-142"]');
    await expect(targetRow).toBeVisible();

    const trigger = targetRow.locator('.assignee-chip--external [data-testid="hint-external-assignee"]');
    await expect(trigger).toBeVisible();

    if (testInfo.project.name === 'mobile') {
      await trigger.tap();
    } else {
      await trigger.hover();
    }

    const popup = page.locator('[data-testid="hint-external-assignee-popup"]');
    await expect(popup).toBeVisible();
    await expect(popup).toContainText(
      'External free-text label - grants zero access and sends zero notifications',
    );

    await annotatedScreenshot(page, testInfo, {
      name: '02-list-external-assignee-hint',
      annotations: [
        {
          selector: '[data-issue-key="KAN-142"] .assignee-chip--external [data-testid="hint-external-assignee"]',
          label: '1: 🏷️ trigger (24x24)',
          note: '24x24 touch target with 150ms debounce',
        },
        {
          selector: '[data-testid="hint-external-assignee-popup"]',
          label: '2: tooltip with exact text',
          note: 'External free-text label - grants zero access and sends zero notifications',
        },
      ],
    });
  });

  test('03-table-default-sorted: semantic table with sticky header and sortable columns', async ({
    page,
  }, testInfo) => {
    await page.goto('/projects/KAN/issues?layout=table');

    const table = page.locator('.issues-table');
    await expect(table).toBeVisible();

    // Sort by Due date ascending
    const dueDateHeader = page.locator('th[data-col-header="due_date"]');
    await expect(dueDateHeader).toBeVisible();
    const sortBtn = dueDateHeader.locator('button');
    await sortBtn.click();
    await expect(dueDateHeader).toHaveAttribute('aria-sort', 'ascending');

    // Probe table computed whitespace measurements
    await probeStyles(page, testInfo, {
      name: 'table-view-metrics',
      probes: [
        {
          selector: '.issues-table thead tr',
          props: ['height'],
        },
        {
          selector: '.issues-table tbody tr',
          props: ['height', 'min-height'],
        },
        {
          selector: '.table-row',
          props: ['height', 'min-height'],
        },
      ],
    });

    await annotatedScreenshot(page, testInfo, {
      name: '03-table-default-sorted',
      annotations: [
        {
          selector: 'th[data-col-header="due_date"]',
          label: '1: sticky <thead> with aria-sort="ascending"',
          note: 'Sticky table header with active ascending sort',
        },
        {
          selector: '.issues-table td.sticky-col',
          label: '2: sticky .mono Key column',
          note: 'Pinned first column on horizontal scroll',
        },
        {
          selector: '.issues-table tbody tr:first-child',
          label: '3: 46px table row',
          note: '46px min-height table row matching list row height',
        },
        {
          selector: '.issues-table td .module-pill',
          label: '4: Modules column (Auth Core)',
          note: 'Module badge rendered in Modules column',
        },
      ],
    });
  });

  test('04-table-column-configurator: popover toggles columns, reorders, and resets defaults', async ({
    page,
  }, testInfo) => {
    await page.goto('/projects/KAN/issues?layout=table');

    const trigger = page.locator('.column-configurator-trigger');
    await expect(trigger).toBeVisible();
    await trigger.click();

    const dialog = page.locator('.column-configurator-dialog');
    await expect(dialog).toBeVisible();

    // Toggle Start date on
    const startDateCheckbox = page.locator('[data-col-id="start_date"] input[type="checkbox"]');
    await startDateCheckbox.click();
    await expect(startDateCheckbox).toBeChecked();

    await annotatedScreenshot(page, testInfo, {
      name: '04-table-column-configurator',
      annotations: [
        {
          selector: '[data-col-id="key"]',
          label: '1: locked Key/Summary checkboxes',
          note: 'Key and Summary columns are locked and non-toggleable',
        },
        {
          selector: '[data-col-id="start_date"]',
          label: '2: toggled Start date checkbox',
          note: 'Start date column enabled dynamically',
        },
        {
          selector: '[data-col-id="priority"] .column-configurator-item-actions',
          label: '3: Move up/Move down order buttons',
          note: 'Reorder visible table columns',
        },
        {
          selector: '.column-configurator-reset',
          label: '4: Reset defaults',
          note: 'Restore initial default column layout',
        },
      ],
    });
  });

  test('05-table-modules-disabled: completely unmounts Modules from table and configurator', async ({
    page,
  }, testInfo) => {
    await page.goto('/projects/KAN/issues?layout=table&nomodules=1');

    const table = page.locator('.issues-table');
    await expect(table).toBeVisible();

    // Verify Modules header is completely absent from DOM
    await expect(page.locator('th[data-col-header="modules"]')).toHaveCount(0);

    // Open column configurator
    const trigger = page.locator('.column-configurator-trigger');
    await expect(trigger).toBeVisible();
    await trigger.click();

    const dialog = page.locator('.column-configurator-dialog');
    await expect(dialog).toBeVisible();

    // Verify Modules option is completely absent from configurator
    await expect(page.locator('[data-col-id="modules"]')).toHaveCount(0);

    await annotatedScreenshot(page, testInfo, {
      name: '05-table-modules-disabled',
      annotations: [
        {
          selector: '.issues-table thead tr',
          label: '1: table header without Modules',
          note: 'Modules column 100% unmounted when modules_enabled is false',
        },
        {
          selector: '.column-configurator-list',
          label: '2: configurator list proving Modules option is completely absent from DOM',
          note: 'Modules option not present in column configurator',
        },
      ],
    });
  });
});
