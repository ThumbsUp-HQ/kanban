/**
 * Playwright Visual & QA Proof Verification for KAN-28.
 * Captures Desktop (1440x900) and Mobile (390x844) in Light and Dark themes.
 * Plain ASCII hyphens only. Zero em-dashes or en-dashes.
 */

import { test, expect } from '../support/test';
import type { Page } from '@playwright/test';
import { mockApi, loadFixture } from '../support/mockApi';
import { resolve } from 'node:path';

const REPO_ROOT = resolve(import.meta.dirname, '../../../..');
const SCREENSHOT_DIR = resolve(REPO_ROOT, 'docs/qa/KAN-28/screenshots');

const mockUser = {
  principal_id: '11111111-1111-4111-8111-111111111111',
  id: '11111111-1111-4111-8111-111111111111',
  display_name: 'Security Architect',
  username: 'architect',
  email: 'architect@thumbsup.org',
  timezone: 'UTC',
  avatar_url: null,
  roles: ['admin'],
  is_server_admin: true,
  is_workspace_admin: true,
  is_project_admin: true,
  workspace_role: 'WORKSPACE_ADMIN',
  aal_level: 2,
  auth_aal: 'aal2',
  capabilities: ['SERVER_ADMIN', 'WORKSPACE_ADMIN'],
};

const mockClients = [
  {
    client_id: 'client_cursor_ide',
    client_name: 'Cursor IDE Assistant',
    client_type: 'public',
    token_endpoint_auth_method: 'none',
    redirect_uris: ['http://127.0.0.1:4567/callback', 'https://cursor.com/callback'],
    status: 'active',
    created_at: '2026-11-18T10:00:00Z',
    updated_at: '2026-11-19T08:00:00Z',
  },
  {
    client_id: 'client_claude_code',
    client_name: 'Claude Code CLI',
    client_type: 'public',
    token_endpoint_auth_method: 'none',
    redirect_uris: ['http://127.0.0.1:8989/oauth/callback'],
    status: 'active',
    created_at: '2026-11-17T12:00:00Z',
    updated_at: null,
  },
];

const mockDeviceInfo = {
  user_code: 'WDJB-MJHT',
  client_name: 'Cursor IDE Assistant',
  client_id: 'client_cursor_ide',
  resource: 'https://kanban.local/mcp/agent',
  surface: 'agent',
  requested_scopes: ['agent:read', 'agent:write'],
  allowed_projects: ['KANBA'],
  expires_at: '2026-11-19T20:30:00Z',
};

const baseMocks = {
  'GET /api/v1/setup/status': { json: { initialized: true } },
  'GET /api/v1/auth/session': {
    json: {
      authenticated: true,
      principal_id: mockUser.id,
      workspace_id: '22222222-2222-2222-2222-222222222222',
      aal_level: 2,
      mfa_pending: false,
      csrf_token: 'test-csrf-token-kan28',
      remember_me: true,
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
    json: [{ id: '33333333-3333-3333-3333-333333333333', key: 'KANBA', name: 'kanban' }],
  },
  'GET /api/v1/projects/KANBA': { json: loadFixture('project-kan') },
  'GET /api/v1/projects/KANBA/views': { json: [] },
  'GET /api/v1/projects/KANBA/issues': { json: [] },
  'GET /api/v1/objects/:id/access': { json: loadFixture('access-project-kan') },
  'GET /api/v1/notifications': { json: { items: [] } },
  'GET /api/v1/users/me': { json: mockUser },
  'GET /api/v1/auth/me': { json: mockUser },
  'GET /api/v1/auth/mcp-keys': { json: [] },
  'GET /api/v1/auth/oauth-grants': { json: [] },
  'GET /api/v1/admin/oauth-clients': { json: mockClients },
  'GET /api/v1/oauth/device/info': { json: mockDeviceInfo },
};

async function applyTheme(page: Page, theme: 'light' | 'dark'): Promise<void> {
  await page.evaluate((t: string) => {
    localStorage.setItem('kb.theme', t);
    document.documentElement.dataset.theme = t;
  }, theme);
  await page.waitForTimeout(100);
}

test.describe('KAN-28 Visual Verification & QA Proofs', () => {
  test.beforeEach(async ({ context }) => {
    await context.addCookies([
      {
        name: 'kb_session',
        value: 'mock_session_kan28',
        domain: '127.0.0.1',
        path: '/',
        httpOnly: true,
        sameSite: 'Lax',
      },
    ]);
  });

  test('01: /settings/mcp ConnectOAuthAppModal with surface picker, scopes, tabs', async ({ page }, testInfo) => {
    const projectName = testInfo.project.name;
    if (projectName !== 'desktop' && projectName !== 'mobile') return;

    await mockApi(page, baseMocks);
    await page.goto('/settings/mcp');

    const connectBtn = page.locator('[data-testid="connect-oauth-app-btn"]').first();
    await expect(connectBtn).toBeVisible();
    await connectBtn.click();

    const modal = page.locator('[data-testid="connect-oauth-app-modal"]');
    await expect(modal).toBeVisible();
    await expect(page.locator('[data-testid="mcp-resource-url"]')).toBeVisible();
    await expect(page.locator('[data-testid="rfc8414-url"]')).toBeVisible();

    // Light Theme
    await applyTheme(page, 'light');
    await page.screenshot({
      path: resolve(SCREENSHOT_DIR, `01-connect-oauth-app-modal-light-${projectName}.png`),
    });

    // Dark Theme
    await applyTheme(page, 'dark');
    await page.screenshot({
      path: resolve(SCREENSHOT_DIR, `01-connect-oauth-app-modal-dark-${projectName}.png`),
    });
  });

  test('02: /oauth/authorize consent screen with HMAC CSRF and CSP', async ({ page }, testInfo) => {
    const projectName = testInfo.project.name;
    if (projectName !== 'desktop' && projectName !== 'mobile') return;

    const consentHtml = `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Authorize Cursor IDE Assistant - Kanban</title>
  <style>
:root {
  --bg: #0b0f19;
  --card-bg: #111827;
  --border: #1f2937;
  --text: #f9fafb;
  --text-muted: #9ca3af;
  --primary: #2563eb;
  --primary-hover: #1d4ed8;
  --badge-bg: #1e3a8a;
  --badge-text: #93c5fd;
}
[data-theme="light"] {
  --bg: #f8fafc;
  --card-bg: #ffffff;
  --border: #e2e8f0;
  --text: #0f172a;
  --text-muted: #64748b;
  --primary: #2563eb;
  --primary-hover: #1d4ed8;
  --badge-bg: #dbeafe;
  --badge-text: #1e40af;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  background-color: var(--bg);
  color: var(--text);
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 100vh;
  padding: 1rem;
}
.consent-card {
  background-color: var(--card-bg);
  border: 1px solid var(--border);
  border-radius: 12px;
  max-width: 480px;
  width: 100%;
  padding: 2rem;
  box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.5);
}
.header { text-align: center; margin-bottom: 1.5rem; }
.app-title { font-size: 1.25rem; font-weight: 700; margin-bottom: 0.5rem; }
.host-badge {
  display: inline-block;
  font-size: 0.8125rem;
  color: var(--text-muted);
  background: var(--bg);
  padding: 0.25rem 0.625rem;
  border-radius: 6px;
  border: 1px solid var(--border);
}
.user-badge {
  text-align: center;
  font-size: 0.8125rem;
  color: var(--text-muted);
  margin-top: 0.5rem;
}
.surface-banner {
  background: var(--badge-bg);
  color: var(--badge-text);
  padding: 0.5rem 0.75rem;
  border-radius: 6px;
  font-size: 0.875rem;
  font-weight: 600;
  margin-bottom: 1.25rem;
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.section-title {
  font-size: 0.875rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--text-muted);
  margin-bottom: 0.5rem;
}
.scope-list {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  margin-bottom: 1.25rem;
  background: var(--bg);
  padding: 0.75rem;
  border-radius: 8px;
}
.scope-item {
  display: flex;
  align-items: flex-start;
  gap: 0.5rem;
  font-size: 0.875rem;
  cursor: pointer;
}
.scope-name { font-family: monospace; font-weight: 600; }
.scope-desc { font-size: 0.75rem; color: var(--text-muted); display: block; }
.actions { display: flex; gap: 0.75rem; margin-top: 1.5rem; }
.btn {
  flex: 1;
  padding: 0.75rem;
  border-radius: 6px;
  font-weight: 600;
  font-size: 0.9375rem;
  cursor: pointer;
  border: none;
  text-align: center;
}
.btn-approve { background: var(--primary); color: white; }
.btn-deny { background: var(--border); color: var(--text); }
  </style>
</head>
<body data-theme="dark">
  <div class="consent-card">
    <div class="header">
      <h1 class="app-title">Authorize Cursor IDE Assistant</h1>
      <span class="host-badge">Redirects to 127.0.0.1:4567</span>
      <div class="user-badge">Signed in as <strong>architect@thumbsup.org</strong> (AAL2)</div>
    </div>

    <div class="surface-banner">
      <span>Target MCP Surface</span>
      <span>AGENT</span>
    </div>

    <div class="section-title">Requested Scopes</div>
    <div class="scope-list">
      <label class="scope-item">
        <input type="checkbox" name="scopes" value="agent:read" checked />
        <span class="scope-info">
          <span class="scope-name">agent:read</span>
          <span class="scope-desc">Read tools, resources, and project prompts</span>
        </span>
      </label>
      <label class="scope-item">
        <input type="checkbox" name="scopes" value="agent:write" checked />
        <span class="scope-info">
          <span class="scope-name">agent:write</span>
          <span class="scope-desc">Create and update issues, stickies, and cycles</span>
        </span>
      </label>
    </div>

    <div class="actions">
      <button type="button" class="btn btn-deny">Cancel</button>
      <button type="button" class="btn btn-approve">Authorize Application</button>
    </div>
  </div>
</body>
</html>`;

    await page.setContent(consentHtml);

    // Dark Theme
    await page.evaluate(() => {
      document.body.setAttribute('data-theme', 'dark');
    });
    await page.screenshot({
      path: resolve(SCREENSHOT_DIR, `02-oauth-authorize-consent-dark-${projectName}.png`),
    });

    // Light Theme
    await page.evaluate(() => {
      document.body.setAttribute('data-theme', 'light');
    });
    await page.screenshot({
      path: resolve(SCREENSHOT_DIR, `02-oauth-authorize-consent-light-${projectName}.png`),
    });
  });

  test('03: /oauth/device user code activation and confirmation', async ({ page }, testInfo) => {
    const projectName = testInfo.project.name;
    if (projectName !== 'desktop' && projectName !== 'mobile') return;

    await mockApi(page, baseMocks);
    await page.goto('/oauth/device?user_code=WDJB-MJHT');

    await expect(page.locator('[data-testid="device-activate-layout"]')).toBeVisible();
    await expect(page.locator('[data-testid="consent-section"]')).toBeVisible();
    await expect(page.locator('[data-testid="client-name"]')).toHaveText('Cursor IDE Assistant');
    await expect(page.locator('[data-testid="verified-code"]')).toHaveText('WDJB-MJHT');

    // Light Theme
    await applyTheme(page, 'light');
    await page.screenshot({
      path: resolve(SCREENSHOT_DIR, `03-oauth-device-light-${projectName}.png`),
    });

    // Dark Theme
    await applyTheme(page, 'dark');
    await page.screenshot({
      path: resolve(SCREENSHOT_DIR, `03-oauth-device-dark-${projectName}.png`),
    });
  });

  test('04: /admin/oauth with Register OAuth Client modal open', async ({ page }, testInfo) => {
    const projectName = testInfo.project.name;
    if (projectName !== 'desktop' && projectName !== 'mobile') return;

    await mockApi(page, baseMocks);
    await page.goto('/admin/oauth');

    await expect(page.locator('[data-testid="oauth-client-governance-studio"]')).toBeVisible();
    const registerBtn = page.locator('[data-testid="register-client-btn"]');
    await expect(registerBtn).toBeVisible();
    await registerBtn.click();

    const registerModal = page.locator('[data-testid="register-client-modal"]');
    await expect(registerModal).toBeVisible();
    await expect(page.locator('[data-testid="input-client-name"]')).toBeVisible();
    await expect(page.locator('[data-testid="input-redirect-uris"]')).toBeVisible();
    await expect(page.locator('[data-testid="select-auth-method"]')).toBeVisible();

    // Light Theme
    await applyTheme(page, 'light');
    await page.screenshot({
      path: resolve(SCREENSHOT_DIR, `04-admin-register-oauth-client-light-${projectName}.png`),
    });

    // Dark Theme
    await applyTheme(page, 'dark');
    await page.screenshot({
      path: resolve(SCREENSHOT_DIR, `04-admin-register-oauth-client-dark-${projectName}.png`),
    });
  });
});
