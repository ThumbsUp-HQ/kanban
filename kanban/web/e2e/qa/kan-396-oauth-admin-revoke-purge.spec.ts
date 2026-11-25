// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import { resolve } from 'node:path';
import { mkdirSync } from 'node:fs';
import type { Page } from '@playwright/test';
import { test, expect } from '../support/test';
import { mockApi, loadFixture, type MockHandlers } from '../support/mockApi';

process.env.QA_TICKET_ID = 'KAN-396';
const SCREENSHOT_DIR = resolve(
  import.meta.dirname,
  '../../../../docs/qa/KAN-396/screenshots',
);
mkdirSync(SCREENSHOT_DIR, { recursive: true });

async function applyTheme(page: Page, theme: 'light' | 'dark'): Promise<void> {
  await page.evaluate((t: string) => {
    localStorage.setItem('kb:theme', t);
    document.documentElement.dataset.theme = t;
  }, theme);
  await page.waitForTimeout(100);
}

const mockServerAdmin = {
  id: 'usr-admin-396',
  handle: 'server_admin',
  display_name: 'Security Admin',
  email: 'sec-admin@example.com',
  is_server_admin: true,
  is_workspace_admin: true,
  aal_level: 2,
  auth_aal: 'aal2',
};

const mockClients = [
  {
    client_id: 'client_active_app',
    client_name: 'Primary OAuth Client with Very Long Name and Extensive Callback Routing Configuration',
    client_type: 'confidential',
    token_endpoint_auth_method: 'client_secret_basic',
    redirect_uris: [
      'https://auth.internal.example.org/oauth2/v1/callback',
      'http://127.0.0.1:8080/callback',
    ],
    grant_types: ['authorization_code', 'refresh_token'],
    response_types: ['code'],
    scope: 'openid email profile agent:read agent:write',
    status: 'active',
    require_pkce: true,
    access_token_ttl_seconds: 3600,
    client_secret_prefix: 'sec_act...',
    created_at: '2026-03-29T10:00:00Z',
  },
  {
    client_id: 'client_suspended_cli',
    client_name: 'Suspended Headless CLI Companion',
    client_type: 'public',
    token_endpoint_auth_method: 'none',
    redirect_uris: ['http://127.0.0.1:9090/cb'],
    grant_types: ['authorization_code'],
    response_types: ['code'],
    scope: 'agent:read',
    status: 'suspended',
    require_pkce: true,
    access_token_ttl_seconds: 1800,
    created_at: '2026-03-28T14:30:00Z',
  },
  {
    client_id: 'client_revoked_worker',
    client_name: 'Decommissioned Microservice Worker',
    client_type: 'confidential',
    token_endpoint_auth_method: 'client_secret_basic',
    redirect_uris: ['https://microservice.internal/oauth/callback'],
    grant_types: ['authorization_code'],
    response_types: ['code'],
    scope: 'agent:write',
    status: 'revoked',
    require_pkce: true,
    access_token_ttl_seconds: 3600,
    client_secret_prefix: 'sec_rev...',
    created_at: '2026-03-25T08:00:00Z',
  },
  {
    client_id: 'client_dcr_stale',
    client_name: 'Ephemeral Dynamic Client Registration App',
    client_type: 'public',
    token_endpoint_auth_method: 'none',
    redirect_uris: ['http://127.0.0.1:7777/cb'],
    grant_types: ['authorization_code'],
    response_types: ['code'],
    scope: 'agent:read',
    status: 'active',
    require_pkce: true,
    access_token_ttl_seconds: 3600,
    created_at: '2026-03-20T12:00:00Z',
  },
];

function getOAuthStudioMocks(): MockHandlers {
  return {
    'GET /api/v1/system/status': { json: loadFixture('system-status-standalone') },
    'GET /api/v1/projects': { json: [loadFixture('project-kan')] },
    'GET /api/v1/projects/KAN': { json: loadFixture('project-kan') },
    'GET /api/v1/objects/:id/access': { json: loadFixture('access-project-kan') },
    'GET /api/v1/auth/session': { json: { csrf_token: 'mock-csrf-token-396' } },
    'GET /api/v1/setup/status': { json: { initialized: true, is_initialized: true, requires_setup: false } },
    'GET /api/v1/notifications': { json: { items: [], total: 0, unread_count: 0 } },
    'GET /api/v1/workspaces/current': {
      json: {
        id: '01a1f1aa-7d7a-782f-a996-6a87f9e9e667',
        name: 'Platform Engineering',
        slug: 'platform-engineering',
        is_current: true,
      },
    },
    'GET /api/v1/workspaces': {
      json: [
        {
          id: '01a1f1aa-7d7a-782f-a996-6a87f9e9e667',
          name: 'Platform Engineering',
          slug: 'platform-engineering',
          is_current: true,
        },
      ],
    },
    'GET /api/v1/auth/me': { json: mockServerAdmin },
    'GET /api/v1/users/me': { json: mockServerAdmin },
    'GET /api/v1/admin/oauth-clients': {
      headers: { 'x-total-count': String(mockClients.length) },
      json: {
        items: mockClients,
        total: mockClients.length,
        limit: 50,
        offset: 0,
      },
    },
    'PATCH /api/v1/admin/oauth-clients/:id': (req) => ({
      status: 200,
      json: { client_id: req.params.id, status: 'revoked' },
    }),
    'DELETE /api/v1/admin/oauth-clients/:id': { status: 204 },
    'POST /api/v1/admin/oauth-clients/bulk-delete': {
      status: 200,
      json: {
        deleted_count: 2,
        deleted_client_ids: ['client_revoked_worker', 'client_dcr_stale'],
      },
    },
  };
}

test.describe('KAN-396 Visual Verification: OAuth Governance Studio Layout and Actions', () => {
  test.beforeEach(async ({ context, page }) => {
    page.on('response', (res) => {
      if (res.status() === 599) {
        console.error('599_UNMATCHED:', res.request().method(), res.url());
      }
    });
    await context.addCookies([
      {
        name: 'kb_csrf',
        value: 'test-csrf-token-396',
        domain: '127.0.0.1',
        path: '/',
      },
    ]);
  });

  test('01-oauth-governance-layout-and-unclipped-actions', async ({ page }, testInfo) => {
    const projectName = testInfo.project.name;
    await mockApi(page, getOAuthStudioMocks());
    await page.goto('/admin/oauth');

    // 1. Studio container and controls visible
    const studio = page.getByTestId('oauth-client-governance-studio');
    await expect(studio).toBeVisible({ timeout: 10000 });

    // Verify toolbar elements
    await expect(page.getByTestId('search-clients-input')).toBeVisible();
    await expect(page.getByTestId('filter-pill-all')).toBeVisible();
    await expect(page.getByTestId('filter-pill-active')).toBeVisible();
    await expect(page.getByTestId('filter-pill-suspended')).toBeVisible();
    await expect(page.getByTestId('filter-pill-revoked')).toBeVisible();
    await expect(page.getByTestId('purge-clients-btn')).toBeVisible();
    await expect(page.getByTestId('pagination-info')).toBeVisible();

    // 2. Select first row to display active bulk toolbar with selection count
    const firstCheckbox = page.getByTestId('select-client-checkbox-client_active_app');
    await expect(firstCheckbox).toBeVisible();
    await firstCheckbox.check();

    const deleteSelectedBtn = page.getByTestId('delete-selected-btn');
    await expect(deleteSelectedBtn).toBeVisible();
    await expect(deleteSelectedBtn).toHaveText(/Delete Selected \(1\)/);

    // 3. Trigger inline revocation on first client row to display Confirm Revoke + Cancel
    const revokeBtn = page.getByTestId('revoke-btn-client_active_app');
    await expect(revokeBtn).toBeVisible();
    await revokeBtn.click();

    const confirmRevokeBtn = page.getByTestId('confirm-revoke-client_active_app');
    const cancelRevokeBtn = page.getByTestId('cancel-revoke-client_active_app');
    await expect(confirmRevokeBtn).toBeVisible();
    await expect(cancelRevokeBtn).toBeVisible();

    // 4. Assert zero horizontal overflow clipping across viewport
    const overflowCheck = await page.evaluate(() => {
      const docEl = document.documentElement;
      const body = document.body;
      const scrollW = Math.max(docEl.scrollWidth, body.scrollWidth);
      const clientW = window.innerWidth;
      return {
        scrollW,
        clientW,
        hasHorizontalOverflow: scrollW > clientW + 2, // 2px margin of safety
      };
    });
    expect(overflowCheck.hasHorizontalOverflow).toBe(false);

    // 5. Verify action button bounding boxes are 100% inside viewport width for ALL 6 controls
    const controls = [
      { name: 'Delete', locator: page.getByTestId('delete-btn-client_suspended_cli') },
      { name: 'Confirm Revoke', locator: confirmRevokeBtn },
      { name: 'Edit URIs', locator: page.getByTestId('edit-uris-btn-client_suspended_cli') },
      { name: 'Suspend', locator: page.getByTestId('suspend-btn-client_dcr_stale') },
      { name: 'Delete Selected (1)', locator: deleteSelectedBtn },
      { name: 'Purge Unused / Revoked Clients', locator: page.getByTestId('purge-clients-btn') },
    ];

    for (const ctrl of controls) {
      await expect(ctrl.locator).toBeVisible();
      const box = await ctrl.locator.boundingBox();
      expect(box, `${ctrl.name} bounding box must not be null`).not.toBeNull();
      if (box) {
        expect(box.x, `${ctrl.name} left edge inside viewport`).toBeGreaterThanOrEqual(0);
        expect(
          box.x + box.width,
          `${ctrl.name} right edge inside viewport`,
        ).toBeLessThanOrEqual((page.viewportSize()?.width ?? 1440) + 1);
      }
    }

    // 6. Reset scroll positions to 0 on main canvas and all scrollable containers, and remove overlays
    await page.evaluate(() => {
      window.scrollTo(0, 0);
      document.documentElement.scrollTop = 0;
      document.body.scrollTop = 0;
      const mainCanvas = document.querySelector('.kb-main-canvas');
      if (mainCanvas) {
        mainCanvas.scrollTop = 0;
      }
      document.querySelectorAll('*').forEach((el) => {
        if (el.scrollTop > 0) {
          el.scrollTop = 0;
        }
      });
      document
        .querySelectorAll(
          '[class*="offline"], [class*="toast"], .kb-toast-container, [role="status"]',
        )
        .forEach((el) => {
          if (!el.closest('[data-testid="oauth-client-governance-studio"]')) {
            el.remove();
          }
        });
    });
    await page.waitForTimeout(200);

    // Capture Light screenshot
    await applyTheme(page, 'light');
    await page.screenshot({
      path: resolve(SCREENSHOT_DIR, `01-oauth-governance-light-${projectName}.png`),
      fullPage: true,
    });

    // Capture Dark screenshot
    await applyTheme(page, 'dark');
    await page.screenshot({
      path: resolve(SCREENSHOT_DIR, `01-oauth-governance-dark-${projectName}.png`),
      fullPage: true,
    });
  });
});
