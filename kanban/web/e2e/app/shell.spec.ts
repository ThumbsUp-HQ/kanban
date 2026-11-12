/**
 * Playwright E2E & Visual Proof Suite for Breathable App Shell (KB-P3-34, KANBA-104).
 * Captures 9 annotated screenshots across desktop, tablet, and mobile viewports:
 * 1. 01-shell-overview
 * 2. 02-sidebar-nav
 * 3. 03-sidebar-modules-disabled
 * 4. 04-sidebar-collapsed
 * 5. 05-standalone-pill-hover
 * 6. 06-access-pill-hover
 * 7. 07-airgap-pill-focus
 * 8. 08-command-palette
 * 9. 09-dark-theme-shell
 *
 * Probes computed styles: topbar 52px, sidebar 256px/0px, canvas pad 24px 28px / 16px, pill 24x24px.
 */

import { test, expect } from '../support/test';
import { annotatedScreenshot, type Annotation } from '../support/annotate';
import { probeStyles } from '../support/styleProbe';
import { mockApi, loadFixture } from '../support/mockApi';

test.describe('AppShell E2E & Visual Verification (KB-P3-34, KANBA-104)', () => {
  test.beforeEach(async ({ page }) => {
    await mockApi(page, {
      'GET /api/v1/system/status': { json: loadFixture('system-status-standalone') },
      'GET /api/v1/projects/KAN': { json: loadFixture('project-kan') },
      'GET /api/v1/objects/:id/access': { json: loadFixture('access-project-kan') },
      'GET /api/v1/issues': { json: loadFixture('issues-kan') },
      'GET /api/v1/users/me': { json: loadFixture('me-adam') },
    });
  });

  test('01: shell overview layout, dimensions, breadcrumb, and computed styles', async ({
    page,
  }, testInfo) => {
    await page.goto('/projects/KAN/issues');
    await page.waitForLoadState('networkidle');

    const topbar = page.locator('.kb-topbar');
    const mainCanvas = page.locator('#main');

    await expect(topbar).toBeVisible();
    await expect(mainCanvas).toBeVisible();

    // Style probing
    await probeStyles(page, testInfo, {
      name: 'shell-layout-dimensions',
      probes: [
        {
          selector: '.kb-topbar',
          props: ['height', 'display', 'border-bottom-width', 'box-sizing'],
        },
        {
          selector: '.kb-sidebar',
          props: ['width', 'display', 'border-right-width', 'box-sizing'],
        },
        {
          selector: '#main',
          props: [
            'padding',
            'padding-top',
            'padding-right',
            'padding-bottom',
            'padding-left',
            'display',
          ],
        },
        {
          selector: '.emoji-hint',
          props: ['width', 'height', 'display', 'align-items', 'justify-content'],
        },
      ],
    });

    const isDesktop = testInfo.project.name === 'desktop';
    const annotations: Annotation[] = [
      {
        selector: '.kb-topbar',
        label: 'Topbar',
        note: '52px fixed height with breadcrumb, search trigger & pills',
      },
      ...(isDesktop
        ? [
            {
              selector: '.kb-sidebar',
              label: 'Sidebar Rail',
              note: '256px width, collapsible via [ shortcut or button',
            },
          ]
        : [
            {
              selector: '.kb-topbar-hamburger',
              label: 'Navigation Drawer Trigger',
              note: 'Opens mobile overlay navigation drawer',
            },
          ]),
      {
        selector: '#main',
        label: 'Main Canvas',
        note: 'Canvas padding 24px 28px (mobile 16px)',
      },
      {
        selector: '.kb-breadcrumb',
        label: 'Breadcrumb',
        note: 'Semantic navigation with project icon and issue count badge',
      },
    ];

    await annotatedScreenshot(page, testInfo, {
      name: '01-shell-overview',
      annotations,
    });
  });

  test('02: sidebar navigation items, workspace branding, and new work item button', async ({
    page,
  }, testInfo) => {
    await page.goto('/projects/KAN/issues');
    await page.waitForLoadState('networkidle');

    if (testInfo.project.name !== 'desktop') {
      await page.locator('.kb-topbar-hamburger').click();
      await expect(page.locator('.kb-sidebar-overlay')).toBeVisible();
    }

    const brand = page.locator('.kb-workspace-switcher');
    const newItemBtn = page.locator('.kb-new-item-btn');
    const projectSubitems = page.locator('.kb-project-subitems');

    await expect(brand).toBeVisible();
    await expect(newItemBtn).toBeVisible();
    await expect(projectSubitems).toBeVisible();

    await annotatedScreenshot(page, testInfo, {
      name: '02-sidebar-nav',
      annotations: [
        {
          selector: '.kb-workspace-switcher',
          label: 'Workspace Brand',
          note: 'Literal [👍] 👍kanban branding with switcher menu anchor',
        },
        {
          selector: '.kb-new-item-btn',
          label: 'New Item Action',
          note: '+ New work item dispatches kb:create-issue event',
        },
        {
          selector: '.kb-project-subitems',
          label: 'Project Subitems',
          note: 'Work Items, Cycles, Modules, Views, and Docs (Pages)',
        },
      ],
    });
  });

  test('03: modules link unmounted completely when modules_enabled is false', async ({
    page,
  }, testInfo) => {
    await page.route('**/api/v1/projects/KAN', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(loadFixture('project-kan-nomodules')),
      });
    });

    await page.goto('/projects/KAN/issues');
    await page.waitForLoadState('networkidle');

    if (testInfo.project.name !== 'desktop') {
      await page.locator('.kb-topbar-hamburger').click();
      await expect(page.locator('.kb-sidebar-overlay')).toBeVisible();
    }

    const modulesLink = page.locator('.kb-sidebar-nav-item', { hasText: 'Modules' });
    await expect(modulesLink).toHaveCount(0);

    await annotatedScreenshot(page, testInfo, {
      name: '03-sidebar-modules-disabled',
      annotations: [
        {
          selector: '.kb-project-subitems',
          label: 'Project Subitems',
          note: 'Modules nav item is completely unmounted from the DOM',
        },
      ],
    });
  });

  test('04: sidebar collapse rail toggled via keyboard shortcut or footer button', async ({
    page,
  }, testInfo) => {
    await page.goto('/projects/KAN/issues');
    await page.waitForLoadState('networkidle');

    if (testInfo.project.name !== 'desktop') {
      await page.locator('.kb-topbar-hamburger').click();
      const sidebarOverlay = page.locator('.kb-sidebar-overlay');
      await expect(sidebarOverlay).toBeVisible();

      await annotatedScreenshot(page, testInfo, {
        name: '04-sidebar-collapsed',
        annotations: [
          {
            selector: '.kb-sidebar-overlay',
            label: 'Mobile Drawer',
            note: 'Drawer overlay with backdrop scrim and focus trap',
          },
          {
            selector: '.kb-topbar',
            label: 'Header Bar',
            note: '52px topbar behind drawer scrim',
          },
        ],
      });
      return;
    }

    const sidebar = page.locator('.kb-sidebar');
    const collapseBtn = page.locator('.kb-sidebar-collapse-btn');

    await collapseBtn.click();
    await expect(sidebar).toHaveClass(/kb-sidebar-collapsed/);

    await probeStyles(page, testInfo, {
      name: 'sidebar-collapsed-state',
      probes: [
        {
          selector: '.kb-sidebar',
          props: ['width', 'border-right-width', 'box-sizing'],
        },
      ],
    });

    await annotatedScreenshot(page, testInfo, {
      name: '04-sidebar-collapsed',
      annotations: [
        {
          selector: '.kb-topbar',
          label: 'Topbar Header',
          note: 'Sticky topbar spans full page width when sidebar is collapsed',
        },
        {
          selector: '#main',
          label: 'Expanded Canvas',
          note: 'Main canvas expands seamlessly with 24px 28px padding',
        },
      ],
    });
  });

  test('05: standalone warning pill hover popover with ephemeral notice', async ({
    page,
  }, testInfo) => {
    await page.goto('/projects/KAN/issues');
    await page.waitForLoadState('networkidle');

    const warnPill = page.locator('.emoji-hint', { hasText: '⚠️' }).first();
    await expect(warnPill).toBeVisible();

    await warnPill.hover();
    const popover = page.locator('.emoji-hint-popup');
    await expect(popover).toBeVisible();

    await annotatedScreenshot(page, testInfo, {
      name: '05-standalone-pill-hover',
      annotations: [
        {
          selector: '.emoji-hint:has-text("⚠️")',
          label: 'Standalone Warning Pill',
          note: '⚠️ pill visible in single-container mode',
        },
        {
          selector: '.emoji-hint-popup',
          label: 'Standalone Notice',
          note: 'Volume persistence warning and compose export prompt',
        },
      ],
    });
  });

  test('06: access transparency pill hover showing user and group counts', async ({
    page,
  }, testInfo) => {
    await page.goto('/projects/KAN/issues');
    await page.waitForLoadState('networkidle');

    const accessPill = page.locator('.emoji-hint', { hasText: '🛡️' }).first();
    await expect(accessPill).toBeVisible();

    await accessPill.hover();
    const popover = page.locator('.emoji-hint-popup');
    await expect(popover).toBeVisible();

    await annotatedScreenshot(page, testInfo, {
      name: '06-access-pill-hover',
      annotations: [
        {
          selector: '.emoji-hint:has-text("🛡️")',
          label: 'Access Pill',
          note: 'Shows current permission scope and collaborator count',
        },
        {
          selector: '.emoji-hint-popup',
          label: 'Access Details',
          note: 'Explicit user, group, agent counts and redacted external notice',
        },
      ],
    });
  });

  test('07: air-gap pill focus showing socket-level LLM egress disabled', async ({
    page,
  }, testInfo) => {
    await page.route('**/api/v1/system/status', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(loadFixture('system-status-airgap')),
      });
    });

    await page.goto('/projects/KAN/issues');
    await page.waitForLoadState('networkidle');

    const airgapPill = page.locator('.emoji-hint', { hasText: '📴' }).first();
    await expect(airgapPill).toBeVisible();

    await airgapPill.focus();
    const popover = page.locator('.emoji-hint-popup');
    await expect(popover).toBeVisible();

    await annotatedScreenshot(page, testInfo, {
      name: '07-airgap-pill-focus',
      annotations: [
        {
          selector: '.emoji-hint:has-text("📴")',
          label: 'Air-gap Pill',
          note: 'Active when external egress is blocked at the socket level',
        },
        {
          selector: '.emoji-hint-popup',
          label: 'Air-gap Notice',
          note: 'Endpoint visible only to server admins',
        },
      ],
    });
  });

  test('08: command palette opens on Mod+K or search trigger with fuzzy filtering', async ({
    page,
  }, testInfo) => {
    await page.goto('/projects/KAN/issues');
    await page.waitForLoadState('networkidle');

    const searchTrigger = page.locator('.kb-search-trigger');
    await searchTrigger.click();

    const dialog = page.locator('.kb-palette-dialog');
    await expect(dialog).toBeVisible();

    const input = page.locator('.kb-palette-input');
    await expect(input).toBeFocused();

    await input.fill('Work');
    await expect(page.locator('.kb-palette-option', { hasText: 'Work Items' })).toBeVisible();

    await annotatedScreenshot(page, testInfo, {
      name: '08-command-palette',
      annotations: [
        {
          selector: '.kb-palette-dialog',
          label: 'Command Palette',
          note: 'Accessible modal dialog with focus trap and subsequence scoring',
        },
        {
          selector: '.kb-palette-input',
          label: 'Filter Input',
          note: 'Input capped at 200 characters, hostile summaries sanitized',
        },
      ],
    });
  });

  test('09: dark theme shell applied via user avatar menu', async ({
    page,
  }, testInfo) => {
    await page.goto('/projects/KAN/issues');
    await page.waitForLoadState('networkidle');

    const avatarBtn = page.locator('.kb-avatar-button');
    await avatarBtn.click();

    const darkOption = page.locator('.kb-theme-radio', { hasText: 'Dark' });
    await expect(darkOption).toBeVisible();
    await darkOption.click();

    await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');

    const isDesktop = testInfo.project.name === 'desktop';
    const annotations: Annotation[] = [
      {
        selector: '.kb-topbar',
        label: 'Dark Topbar',
        note: 'Dark theme high contrast header tokens applied',
      },
      ...(isDesktop
        ? [
            {
              selector: '.kb-sidebar',
              label: 'Dark Sidebar',
              note: 'Surface raised dark tokens with subtle borders',
            },
          ]
        : [
            {
              selector: '#main',
              label: 'Dark Canvas',
              note: 'Main canvas rendered with dark theme background token',
            },
          ]),
    ];

    await annotatedScreenshot(page, testInfo, {
      name: '09-dark-theme-shell',
      annotations,
    });
  });
});
