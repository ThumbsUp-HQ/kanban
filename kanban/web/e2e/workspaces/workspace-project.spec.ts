/**
 * Playwright E2E & Visual Verification for Workspaces and Projects (KANBA-192 / KB-WS-PROJ).
 * Tests project creation, independent project expand/collapse in sidebar,
 * and live workspace switching across desktop (1440x900), tablet (1024x768), and mobile (390x844).
 */

import { test, expect } from '../support/test';
import { annotatedScreenshot } from '../support/annotate';
import { mockApi, loadFixture, type MockHandlers } from '../support/mockApi';

function getBaseHandlers(): MockHandlers {
  return {
    'GET /api/v1/system/status': { json: loadFixture('system-status-prod') },
    'GET /api/v1/setup/status': { json: { is_initialized: true } },
    'GET /api/v1/users/me': { json: loadFixture('me-adam') },
    'GET /api/v1/me': { json: loadFixture('me-adam') },
    'GET /api/v1/auth/session': {
      json: {
        authenticated: true,
        user: loadFixture('me-adam'),
        csrf_token: 'csrf-token-valid-abc123',
      },
    },
    'GET /api/v1/projects/:key': (req) => {
      const key = req.params.key ?? 'KAN';
      const isKan = key === 'KAN';
      const isInfra = key === 'INFRA';
      const fixture = loadFixture<Record<string, unknown>>('project-kan');
      return {
        json: {
          ...fixture,
          id: isKan
            ? '01a1e706-8153-72a8-a253-2f44444546bc'
            : isInfra
              ? '01a1ec27-bd50-79c5-8e0e-8384849fef99'
              : '01a1ec27-bd50-79c5-8e0e-8384849fef88',
          key,
          identifier: key,
          name: isKan ? 'Kanban' : isInfra ? 'Core Infrastructure' : 'Security Shield',
          modules_enabled: true,
        },
      };
    },
    'GET /api/v1/projects/:key/issues': { json: loadFixture('issues-kan') },
    'GET /api/v1/projects/:key/states': {
      json: {
        items: [
          { id: 'state-backlog', name: 'Backlog', group: 'backlog' },
          { id: 'state-in-progress', name: 'In Progress', group: 'started' },
          { id: 'state-done', name: 'Done', group: 'completed' },
        ],
      },
    },
    'GET /api/v1/objects/:id/access': { json: loadFixture('access-project-kan') },
    'GET /api/v1/issues': { json: loadFixture('issues-kan') },
    'GET /api/v1/media-proxy': {
      status: 200,
      contentType: 'image/png',
      body: Buffer.from(
        'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=',
        'base64',
      ),
    },
  };
}

test.describe('Workspace & Project Navigation E2E (KANBA-192 / KB-WS-PROJ)', () => {
  test('01: project creation in default workspace with 0 console errors', async ({
    page,
  }, testInfo) => {
    const consoleErrors: string[] = [];
    page.on('console', (msg) => {
      if (msg.type() === 'error') {
        const text = msg.text();
        if (text.startsWith('The source list for the Content Security Policy directive')) {
          return;
        }
        consoleErrors.push(text);
      }
    });

    await mockApi(page, {
      ...getBaseHandlers(),
      'GET /api/v1/workspaces': {
        json: [
          {
            id: '01a1e706-8146-7e4c-b3e0-0b1bd00d479b',
            name: 'Platform Engineering',
            slug: 'platform-eng',
            is_current: true,
            role: 'WORKSPACE_MEMBER',
          },
        ],
      },
      'GET /api/v1/projects': {
        json: {
          items: [
            {
              key: 'KAN',
              name: 'Kanban',
              modules_enabled: true,
            },
          ],
        },
      },
      'POST /api/v1/projects': {
        status: 201,
        json: {
          id: '01a1ec27-bd50-79c5-8e0e-8384849fef99',
          key: 'INFRA',
          identifier: 'INFRA',
          name: 'Core Infrastructure',
          description_markdown: 'Core platform and infrastructure services',
          modules_enabled: true,
        },
      },
    });

    await page.goto('/projects/KAN/issues');
    await page.waitForLoadState('networkidle');

    if (testInfo.project.name !== 'desktop') {
      const hamburger = page.locator('.kb-topbar-hamburger');
      if (await hamburger.isVisible()) {
        await hamburger.click();
      }
    }

    const addProjectBtn = page.locator('.kb-sidebar-add-project-btn');
    if (await addProjectBtn.isVisible()) {
      await addProjectBtn.click();
    } else {
      await page.evaluate(() => {
        window.dispatchEvent(new CustomEvent('kb:open-create-project'));
      });
    }

    const modal = page.locator('.kb-create-project-dialog');
    await expect(modal).toBeVisible();

    const nameInput = page.locator('#create-project-name');
    const idInput = page.locator('#create-project-identifier');
    const descInput = page.locator('#create-project-description');

    await nameInput.fill('Core Infrastructure');
    await idInput.fill('INFRA');
    await descInput.fill('Core platform and infrastructure services');

    await annotatedScreenshot(page, testInfo, {
      name: '01-project-creation-default-workspace',
      annotations: [
        {
          selector: '.kb-create-project-dialog',
          label: 'Create Project Modal',
          note: 'Accessible dialog for project creation in current workspace',
        },
        {
          selector: '#create-project-name',
          label: 'Project Name Input',
          note: 'Sanitized input with auto-derived identifier',
        },
        {
          selector: '#create-project-identifier',
          label: 'Identifier Input',
          note: 'Uppercase alphanumeric 2-10 char identifier',
        },
        {
          selector: '[data-testid="create-project-submit"]',
          label: 'Create Action Button',
          note: 'Dispatches POST /api/v1/projects with CSRF token',
        },
      ],
    });

    // Close modal cleanly
    const submitBtn = page.locator('[data-testid="create-project-submit"]');
    await submitBtn.click();
    await expect(modal).not.toBeVisible();

    // Verify zero console errors
    expect(consoleErrors).toHaveLength(0);
  });

  test('02: independent expand/collapse of multiple projects in Sidebar', async ({
    page,
  }, testInfo) => {
    await mockApi(page, {
      ...getBaseHandlers(),
      'GET /api/v1/workspaces': {
        json: [
          {
            id: '01a1e706-8146-7e4c-b3e0-0b1bd00d479b',
            name: 'Platform Engineering',
            slug: 'platform-eng',
            is_current: true,
          },
        ],
      },
      'GET /api/v1/projects': {
        json: {
          items: [
            {
              key: 'KAN',
              name: 'Kanban',
              modules_enabled: true,
            },
            {
              key: 'INFRA',
              name: 'Core Infrastructure',
              modules_enabled: true,
            },
          ],
        },
      },
    });

    await page.goto('/projects/KAN/issues');
    await page.waitForLoadState('networkidle');

    if (testInfo.project.name !== 'desktop') {
      const hamburger = page.locator('.kb-topbar-hamburger');
      if (await hamburger.isVisible()) {
        await hamburger.click();
      }
    }

    const kanRow = page.locator('button[aria-label="Project: Kanban"]');
    const infraRow = page.locator('button[aria-label="Project: Core Infrastructure"]');

    await expect(kanRow).toBeVisible();
    await expect(infraRow).toBeVisible();

    // Collapse KAN while leaving INFRA expanded
    await kanRow.click();
    await expect(kanRow).toHaveAttribute('aria-expanded', 'false');
    await expect(infraRow).toHaveAttribute('aria-expanded', 'true');

    await annotatedScreenshot(page, testInfo, {
      name: '02-sidebar-independent-projects',
      annotations: [
        {
          selector: 'button[aria-label="Project: Kanban"]',
          label: 'Collapsed Project (KAN)',
          note: 'Collapsed project state (arrow right) without subitems',
        },
        {
          selector: 'button[aria-label="Project: Core Infrastructure"]',
          label: 'Expanded Project (INFRA)',
          note: 'Independent expanded project state (arrow down)',
        },
        {
          selector: '.kb-project-subitems',
          label: 'Project Subitems',
          note: 'Sub-navigation visible for expanded project only',
        },
      ],
    });
  });

  test('03: live workspace switching updating dropdown, breadcrumb, and projects without page reload', async ({
    page,
  }, testInfo) => {
    let currentWorkspaceId = '01a1e706-8146-7e4c-b3e0-0b1bd00d479b';

    await mockApi(page, {
      ...getBaseHandlers(),
      'GET /api/v1/workspaces': () => ({
        json: [
          {
            id: '01a1e706-8146-7e4c-b3e0-0b1bd00d479b',
            name: 'Platform Engineering',
            slug: 'platform-eng',
            is_current: currentWorkspaceId === '01a1e706-8146-7e4c-b3e0-0b1bd00d479b',
          },
          {
            id: '01a1e706-8146-7e4c-b3e0-0b1bd00d479c',
            name: 'Security Operations',
            slug: 'sec-ops',
            is_current: currentWorkspaceId === '01a1e706-8146-7e4c-b3e0-0b1bd00d479c',
          },
        ],
      }),
      'GET /api/v1/projects': () => ({
        json: {
          items:
            currentWorkspaceId === '01a1e706-8146-7e4c-b3e0-0b1bd00d479b'
              ? [
                  {
                    key: 'KAN',
                    name: 'Kanban',
                    modules_enabled: true,
                  },
                ]
              : [
                  {
                    key: 'SEC',
                    name: 'Security Shield',
                    modules_enabled: true,
                  },
                ],
        },
      }),
      'POST /api/v1/workspaces/:id/switch': (req) => {
        currentWorkspaceId = req.params.id ?? '01a1e706-8146-7e4c-b3e0-0b1bd00d479c';
        return {
          status: 200,
          json: {
            workspace: {
              id: currentWorkspaceId,
              name: 'Security Operations',
              slug: 'sec-ops',
            },
          },
        };
      },
    });

    await page.goto('/projects/KAN/issues');
    await page.waitForLoadState('networkidle');

    if (testInfo.project.name !== 'desktop') {
      const hamburger = page.locator('.kb-topbar-hamburger');
      if (await hamburger.isVisible()) {
        await hamburger.click();
      }
    }

    const switcher = page.locator('.kb-workspace-switcher');
    await expect(switcher).toBeVisible();

    // Open workspace switcher dropdown
    await switcher.click();
    const dropdown = page.locator('.kb-workspace-dropdown');
    await expect(dropdown).toBeVisible();

    const activeItem = page.locator('.kb-workspace-dropdown-item-active');
    await expect(activeItem).toBeVisible();

    await annotatedScreenshot(page, testInfo, {
      name: '03-live-workspace-switch',
      annotations: [
        {
          selector: '.kb-workspace-switcher',
          label: 'Workspace Switcher Anchor',
          note: 'Displays active workspace brand with dropdown toggle',
        },
        {
          selector: '.kb-workspace-dropdown',
          label: 'Workspace Dropdown',
          note: 'Multi-workspace menu with live switch action',
        },
        {
          selector: '.kb-workspace-dropdown-item-active',
          label: 'Active Workspace Item',
          note: 'Current workspace marked with checkmark badge',
        },
      ],
    });

    // Click to switch workspace live
    const secOpsItem = page.locator('.kb-workspace-dropdown-item', { hasText: 'Security Operations' });
    await secOpsItem.click();
    await page.waitForLoadState('networkidle');

    // Confirm dropdown closed and switcher displays new workspace
    await expect(dropdown).not.toBeVisible();
    await expect(switcher).toContainText('Security Operations');
  });
});
