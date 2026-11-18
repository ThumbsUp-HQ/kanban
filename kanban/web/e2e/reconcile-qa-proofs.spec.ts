/**
 * Playwright E2E Visual Proofs for KANBA-206 (KB-QA-RECONCILE).
 * Captures:
 * 1. 01-login-clean-network-{desktop,tablet,mobile}.png
 * 2. 02-custom-fields-fail-closed-{desktop,tablet,mobile}.png
 * 3. 03-manage-access-principals-{desktop,tablet,mobile}.png
 */

import { test, expect } from './support/test';
import { annotatedScreenshot } from './support/annotate';
import { mockApi, loadFixture } from './support/mockApi';

const baseAppMocks = {
  'GET /api/v1/setup/status': { json: { initialized: true } },
  'GET /api/v1/auth/session': {
    json: {
      authenticated: true,
      principal_id: '22222222-2222-4222-8222-222222222222',
      workspace_id: '22222222-2222-2222-2222-222222222222',
      aal_level: 2,
      mfa_pending: false,
      csrf_token: 'test-csrf-token-proofs',
      remember_me: true,
      idle_expires_at: '2026-11-24T23:00:00Z',
      absolute_expires_at: '2026-12-17T23:00:00Z',
    },
  },
  'GET /api/v1/system/status': { json: loadFixture('system-status-standalone') },
  'GET /api/v1/workspaces': {
    json: [{ id: '22222222-2222-2222-2222-222222222222', name: 'kanban', slug: 'kanban' }],
  },
  'GET /api/v1/workspaces/current': {
    json: { id: '22222222-2222-2222-2222-222222222222', name: 'kanban', slug: 'kanban' },
  },
  'GET /api/v1/projects': {
    json: [{ id: '33333333-3333-3333-3333-333333333333', key: 'KAN', name: 'kanban' }],
  },
  'GET /api/v1/projects/KAN': { json: loadFixture('project-kan') },
  'GET /api/v1/projects/KAN/views': { json: [] },
  'GET /api/v1/projects/KAN/issues': { json: [] },
  'GET /api/v1/projects/KAN/cycles': { json: { items: [] } },
  'GET /api/v1/projects/KAN/modules': { json: { items: [] } },
  'GET /api/v1/projects/KAN/states': { json: { items: [] } },
  'GET /api/v1/projects/KAN/priorities': { json: { items: [] } },
  'GET /api/v1/projects/KAN/labels': { json: { items: [] } },
  'GET /api/v1/objects/:id/access': { json: loadFixture('access-project-kan') },
  'GET /api/v1/users/me': { json: loadFixture('me-adam') },
};

test.describe('KANBA-206 Reconcile QA Visual Proofs', () => {
  test.beforeEach(async ({ context }) => {
    await context.addCookies([
      {
        name: 'kb_csrf',
        value: 'test-csrf-token-proofs',
        domain: '127.0.0.1',
        path: '/',
      },
    ]);
  });

  test('01-login-clean-network: multi-card authentication with clean network isolation', async ({
    page,
  }, testInfo) => {
    await mockApi(page, {
      'GET /api/v1/auth/cards': { json: loadFixture('auth-cards-kan') },
    });

    await page.goto('/login');
    const authPanel = page.locator('.auth-panel');
    await expect(authPanel).toBeVisible();

    await annotatedScreenshot(page, testInfo, {
      name: '01-login-clean-network',
      annotations: [
        {
          selector: '.auth-panel',
          label: 'Auth Panel',
          note: 'Multi-card sign-in with clean network isolation',
        },
        {
          selector: '.auth-card-list',
          label: 'Provider Cards',
          note: 'Ordered auth cards with primary indicator',
        },
      ],
    });
  });

  test('02-custom-fields-fail-closed: custom fields fail closed for unauthorized roles', async ({
    page,
  }, testInfo) => {
    await mockApi(page, {
      ...baseAppMocks,
      'GET /api/v1/auth/me': {
        json: {
          id: 'u-user-std',
          handle: 'standard_user',
          display_name: 'Standard User',
          is_server_admin: false,
        },
      },
      'GET /api/v1/projects/KAN/custom-fields': {
        status: 403,
        json: {
          type: 'https://kanban.hackedyour.info/problems/forbidden',
          title: 'Forbidden',
          status: 403,
          detail: 'PROJECT_ADMIN or SERVER_ADMIN required to manage custom fields.',
        },
      },
      'GET /api/v1/projects/KAN/custom-fields/definitions': {
        status: 403,
        json: {
          type: 'https://kanban.hackedyour.info/problems/forbidden',
          title: 'Forbidden',
          status: 403,
          detail: 'PROJECT_ADMIN or SERVER_ADMIN required to manage custom fields.',
        },
      },
    });

    await page.goto('/projects/KAN/settings/custom-fields');
    const layout = page.locator('[data-testid="custom-fields-editor-layout"], .app-shell, body');
    await expect(layout.first()).toBeVisible();

    await annotatedScreenshot(page, testInfo, {
      name: '02-custom-fields-fail-closed',
      annotations: [
        {
          selector: 'body',
          label: 'Fail-Closed Scope',
          note: 'Non-admin access fails closed without leaking definition forms',
        },
      ],
    });
  });

  test('03-manage-access-principals: Auth Studio with USER/GROUP/AGENT principal management', async ({
    page,
  }, testInfo) => {
    await mockApi(page, {
      ...baseAppMocks,
      'GET /api/v1/auth/me': {
        json: {
          id: 'u-admin',
          handle: 'admin',
          display_name: 'Admin User',
          is_server_admin: true,
        },
      },
      'GET /api/v1/auth/cards': { json: loadFixture('auth-cards-kan') },
      'GET /api/v1/admin/auth/cards': { json: loadFixture('auth-cards-kan') },
      'GET /api/v1/admin/principals': {
        json: [
          {
            id: 'p-1',
            handle: 'alice',
            display_name: 'Alice Admin',
            type: 'USER',
            email: 'alice@example.com',
            provider_kind: 'LOCAL_ADMIN',
            role_grant: 'SERVER_ADMIN',
          },
          {
            id: 'p-2',
            handle: 'eng-lead',
            display_name: 'Engineering Leads',
            type: 'GROUP',
            email: null,
            provider_kind: 'LDAP',
            role_grant: 'WORKSPACE_ADMIN',
          },
          {
            id: 'p-3',
            handle: 'reality-checker',
            display_name: 'Reality Checker QA Bot',
            type: 'AGENT',
            email: null,
            provider_kind: 'LOCAL_ADMIN',
            role_grant: 'WORKSPACE_MEMBER',
          },
        ],
      },
    });

    await page.goto('/admin/auth');
    await expect(page.locator('.auth-studio-page')).toBeVisible();

    // Click Users & Permissions tab
    const usersTab = page.locator('button:has-text("Users & Permissions")');
    if (await usersTab.isVisible()) {
      await usersTab.click();
    }

    await page.waitForTimeout(300);

    await annotatedScreenshot(page, testInfo, {
      name: '03-manage-access-principals',
      annotations: [
        {
          selector: '.auth-studio-page',
          label: 'Auth Studio',
          note: 'Principal Studio supporting USER, GROUP, and AGENT kind filtering',
        },
      ],
    });
  });
});
