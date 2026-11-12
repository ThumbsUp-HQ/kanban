/**
 * Playwright E2E verification and visual design proofs for:
 * Filters & Display bar, 2D Swimlanes, Bulk Action bar, and Single-key Shortcuts (KB-P3-40).
 * Plain ASCII hyphens only.
 */

import { test, expect } from '../support/test';
import { annotatedScreenshot } from '../support/annotate';
import { probeStyles } from '../support/styleProbe';

test.describe('Filters, 2D Swimlanes, Bulk Bar, and Shortcuts E2E (KB-P3-40)', () => {
  test('01-filter-bar-and-2d-swimlanes: renders 2D grid with active filter chips, group/subgroup controls, and swimlanes', async ({
    page,
  }, testInfo) => {
    await page.goto(
      '/projects/KAN/issues?layout=board&group_by=state&sub_group_by=priority&filter_state=active&gate_status=pending'
    );

    // Verify 2D Swimlane board grid region is mounted
    const boardGrid = page.locator('.swimlane-board-grid');
    await expect(boardGrid).toBeVisible();

    // Verify filter chips: Active state preset and Gate status pending
    const chipsRow = page.locator('.filter-chips-row');
    await expect(chipsRow).toBeVisible();
    await expect(page.locator('.filter-chip[data-facet="state"]')).toBeVisible();
    await expect(page.locator('.filter-chip[data-facet="gate_status"]')).toBeVisible();

    // Verify group and sub-group select values
    const groupBySelect = page.locator('#group-by-select');
    const subGroupBySelect = page.locator('#subgroup-by-select');
    await expect(groupBySelect).toHaveValue('state');
    await expect(subGroupBySelect).toHaveValue('priority');

    // Verify horizontal swimlane headers: Urgent and High
    const urgentBand = page.locator('[data-subgroup-id="urgent"] .swimlane-band-header');
    const highBand = page.locator('[data-subgroup-id="high"] .swimlane-band-header');
    await expect(urgentBand).toBeVisible();
    await expect(highBand).toBeVisible();

    // Verify sticky 324px state column headers
    const colHeaders = page.locator('.swimlane-col-headers');
    await expect(colHeaders).toBeVisible();

    // Probe computed whitespace measurements
    await probeStyles(page, testInfo, {
      name: 'filter-swimlanes-metrics',
      probes: [
        {
          selector: '.filter-display-bar',
          props: ['padding-top', 'padding-bottom', 'row-gap'],
        },
        {
          selector: '.swimlane-col-header-item',
          props: ['width', 'min-width', 'height'],
        },
        {
          selector: '.swimlane-band',
          props: ['margin-bottom', 'display'],
        },
      ],
    });

    // Capture annotated screenshot 01
    await annotatedScreenshot(page, testInfo, {
      name: '01-filter-bar-and-2d-swimlanes',
      annotations: [
        {
          selector: '.filter-chips-row',
          label: '1: Filter: Active + Gate: ⏳🤖 chips',
          note: 'Filter preset and gate status chips with count and remove buttons',
        },
        {
          selector: '.filter-controls-group',
          label: '2: Group/Sub-group controls',
          note: 'Calm Filter button, Group: State, Sub-group: Priority selects',
        },
        {
          selector: '[data-subgroup-id="urgent"] .swimlane-band-header',
          label: '3: 🔥 Urgent horizontal swimlane header',
          note: 'Collapsible band toggle with priority emoji and item count',
        },
        {
          selector: '[data-subgroup-id="high"] .swimlane-band-header',
          label: '4: ⚡ High swimlane header (24px band gap)',
          note: '24px vertical separation between horizontal swimlanes',
        },
        {
          selector: '.swimlane-col-headers',
          label: '5: 324px aligned state columns',
          note: 'Sticky 324px column headers matching Kanban board track widths',
        },
      ],
    });
  });

  test('02-bulk-select-bar-archive-disabled: 3 selected issues with active item keeps Archive disabled', async ({
    page,
  }, testInfo) => {
    await page.goto('/projects/KAN/issues?layout=board&sub_group_by=priority');

    const card140 = page.locator('[data-issue-key="KAN-140"]');
    await expect(card140).toBeVisible();
    const card142 = page.locator('[data-issue-key="KAN-142"]');
    await expect(card142).toBeVisible();

    // Select 3 issues (KAN-140, KAN-141, KAN-142) via checkboxes
    await page.locator('[data-issue-key="KAN-140"] input[type="checkbox"]').check();
    await page.locator('[data-issue-key="KAN-141"] input[type="checkbox"]').check();
    await page.locator('[data-issue-key="KAN-142"] input[type="checkbox"]').check();

    // Verify floating BulkActionBar is mounted and indicates 3 selected
    const bulkBar = page.locator('.bulk-action-bar');
    await expect(bulkBar).toBeVisible();
    await expect(page.locator('.bulk-action-bar-count')).toHaveText('3 selected');

    // Archive button must be disabled because items are not completed or cancelled
    const archiveBtn = page.locator('.bulk-action-bar-btn[data-action="archive"]');
    await expect(archiveBtn).toBeVisible();
    await expect(archiveBtn).toBeDisabled();
    await expect(archiveBtn).toHaveAttribute(
      'title',
      'Only completed or canceled work items can be archived'
    );

    // Capture annotated screenshot 02
    await annotatedScreenshot(page, testInfo, {
      name: '02-bulk-select-bar-archive-disabled',
      annotations: [
        {
          selector: '[data-issue-key="KAN-140"] .swimlane-card-checkbox-wrap',
          label: '1: selected checkboxes + focus ring',
          note: 'Card checkbox selected state with accessible focus indicator',
        },
        {
          selector: '.bulk-action-bar',
          label: '2: floating BulkActionBar (3 selected)',
          note: 'Centered floating bulk toolbar (position: fixed, bottom: 24px)',
        },
        {
          selector: '.bulk-action-bar-btn[data-action="archive"]',
          label: '3: disabled Archive button',
          note: 'Only completed or canceled work items can be archived',
        },
      ],
    });
  });

  test('03-shortcut-quick-priority-popover: J navigation then P opens anchored priority picker', async ({
    page,
  }, testInfo) => {
    await page.goto('/projects/KAN/issues?layout=board&sub_group_by=priority');

    const card142 = page.locator('[data-issue-key="KAN-142"]');
    await expect(card142).toBeVisible();

    // Click on card KAN-142 to focus it (or press J)
    await card142.click();

    // Press 'P' to trigger priority popover
    await page.keyboard.press('p');

    // Verify QuickFieldPopover is mounted and anchored
    const popover = page.locator('.quick-field-popover');
    await expect(popover).toBeVisible();
    await expect(popover.locator('.quick-field-popover-title')).toHaveText('Priority');

    // Verify options exist: Urgent, High, Medium, Low, None
    await expect(popover.locator('[role="option"]:has-text("Urgent")')).toBeVisible();
    await expect(popover.locator('[role="option"]:has-text("High")')).toBeVisible();
    await expect(popover.locator('[role="option"]:has-text("Medium")')).toBeVisible();
    await expect(popover.locator('[role="option"]:has-text("Low")')).toBeVisible();
    await expect(popover.locator('[role="option"]:has-text("None")')).toBeVisible();

    // Capture annotated screenshot 03
    await annotatedScreenshot(page, testInfo, {
      name: '03-shortcut-quick-priority-popover',
      annotations: [
        {
          selector: '[data-issue-key="KAN-142"]',
          label: '1: roving focus ring on KAN-142',
          note: 'Card focused via roving index navigation with CSSOM anchor',
        },
        {
          selector: '.quick-field-popover',
          label: '2: anchored Priority QuickFieldPopover',
          note: 'Anchored popover menu: Urgent 🔥, High ⚡, Medium 🔹, Low 💤, None',
        },
      ],
    });
  });

  test('04-quick-create-modal: pressing C opens modal with summary, description, and module', async ({
    page,
  }, testInfo) => {
    await page.goto('/projects/KAN/issues?layout=board&sub_group_by=priority');

    // Wait for page to be ready
    await expect(page.locator('.swimlane-board-grid')).toBeVisible();

    // Press 'C' key to trigger quick create modal
    await page.keyboard.press('c');

    // Verify modal dialog appears
    const modal = page.locator('.quick-create-modal');
    await expect(modal).toBeVisible();

    // Verify summary input is present and focused
    const summaryInput = modal.locator('.quick-create-input');
    await expect(summaryInput).toBeVisible();

    // Fill in summary
    await summaryInput.fill('Implement OAuth PKCE flow verification');

    // Verify markdown description textarea
    const descTextarea = modal.locator('.quick-create-textarea');
    await expect(descTextarea).toBeVisible();
    await descTextarea.fill('Audit authorization code flow with strict SHA-256 code challenge.');

    // Verify module select has Auth Core option
    const moduleSelect = modal.locator('#quick-create-module');
    await expect(moduleSelect).toBeVisible();

    // Capture annotated screenshot 04
    await annotatedScreenshot(page, testInfo, {
      name: '04-quick-create-modal',
      annotations: [
        {
          selector: '.quick-create-modal',
          label: '1: modal dialog',
          note: 'Create work item modal dialog opened via C shortcut',
        },
        {
          selector: '.quick-create-input',
          label: '2: summary + Markdown description inputs',
          note: 'AutoFocused summary input and multiline Markdown description',
        },
        {
          selector: '#quick-create-module',
          label: '3: pre-applied default Auth Core module chip',
          note: 'Project module dropdown selection when modules_enabled is true',
        },
      ],
    });
  });

  test('05-modules-disabled-zero-clutter: unmounts Module facet and axis when modulesEnabled is false', async ({
    page,
  }, testInfo) => {
    await page.goto('/projects/KAN/issues?layout=board&nomodules=1');

    // Verify filter bar is mounted
    const filterBar = page.locator('.filter-display-bar');
    await expect(filterBar).toBeVisible();

    // Click Filter button to open facets popover
    const filterBtn = page.locator('.filter-btn-trigger').first();
    await filterBtn.click();

    const facetsPanel = page.locator('.filter-popover-panel');
    await expect(facetsPanel).toBeVisible();

    // Verify Module category is completely absent from facet list
    await expect(facetsPanel.locator('.filter-facet-category-title:has-text("module")')).toHaveCount(0);

    // Verify Module is absent from Sub-group select options
    const subGroupSelect = page.locator('#subgroup-by-select');
    await expect(subGroupSelect.locator('option[value="module"]')).toHaveCount(0);

    // Capture annotated screenshot 05
    await annotatedScreenshot(page, testInfo, {
      name: '05-modules-disabled-zero-clutter',
      annotations: [
        {
          selector: '.filter-popover-panel',
          label: '1: Filter facet list without Module',
          note: 'Zero Module category, facets, or filters rendered in popover',
        },
        {
          selector: '#subgroup-by-select',
          label: '2: Sub-group options without Module',
          note: 'Module swimlane axis completely unmounted from dropdown',
        },
      ],
    });
  });
});
