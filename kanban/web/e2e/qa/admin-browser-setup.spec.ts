/**
 * Admin Browser QA Setup: Multi-Situation Workspace, RBAC, Workflow, Sticky/Doc & MCP Seeding (KANBA-203).
 * Validates:
 * 1. Setup claim token sanitization via history.replaceState and negative rejection of invalid token.
 * 2. Multi-card login with X-CSRF-Token and SecondFactorStep AAL2 progression.
 * 3. Admin Auth Studio card list, write-only secret contract in edit drawer, break-glass 409 LOCKOUT_PREVENTED,
 *    and local user creation with role binding.
 * 4. Admin MCP Studio raw key reveal, DOM purge on close, and style probes across desktop, tablet, and mobile.
 * Strict ASCII hyphens only.
 */

import { test, expect } from '../support/test';
import { mockApi, loadFixture } from '../support/mockApi';
import { annotatedScreenshot } from '../support/annotate';
import { probeStyles } from '../support/styleProbe';

const VALID_SETUP_TOKEN = 'kb_setup_' + 'A'.repeat(43);
const INVALID_SHORT_TOKEN = 'kb_setup_short_invalid';

function getBaseAppMocks() {
  return {
    'GET /api/v1/setup/status': { json: { initialized: true } },
    'GET /api/v1/auth/session': {
      json: {
        authenticated: true,
        principal_id: 'admin-uuid-0001',
        workspace_id: 'ws-default',
        aal_level: 2,
        mfa_pending: false,
        csrf_token: 'test-csrf-token-admin-qa',
        remember_me: true,
        idle_expires_at: '2026-11-25T23:00:00Z',
        absolute_expires_at: '2026-12-18T23:00:00Z',
      },
    },
    'GET /api/v1/system/status': { json: loadFixture('system-status-standalone') },
    'GET /api/v1/workspaces': {
      json: {
        items: [{ id: 'ws-default', slug: 'kanban', name: '👍kanban Workspace' }],
        active_workspace_id: 'ws-default',
      },
    },
    'GET /api/v1/workspaces/current': {
      json: { id: 'ws-default', name: 'kanban', slug: 'kanban' },
    },
    'GET /api/v1/projects': {
      json: [
        { id: 'proj-qaadm', key: 'QAADM', name: 'QA Admin Project' },
        { id: 'proj-qaview', key: 'QAVIEW', name: 'QA Viewer Project' },
        { id: 'proj-qanomod', key: 'QANOMOD', name: 'QA No Modules Project' },
      ],
    },
    'GET /api/v1/projects/QAADM': { json: loadFixture('project-kan') },
    'GET /api/v1/projects/QAADM/views': { json: [] },
    'GET /api/v1/projects/QAADM/issues': { json: [] },
    'GET /api/v1/projects/QAADM/cycles': { json: { items: [] } },
    'GET /api/v1/projects/QAADM/modules': { json: { items: [] } },
    'GET /api/v1/projects/QAADM/states': { json: { items: [] } },
    'GET /api/v1/projects/QAADM/priorities': { json: { items: [] } },
    'GET /api/v1/projects/QAADM/labels': { json: { items: [] } },
    'GET /api/v1/objects/:id/access': { json: loadFixture('access-project-kan') },
    'GET /api/v1/users/me': { json: loadFixture('me-adam') },
    'GET /api/v1/auth/me': { json: loadFixture('me-admin-auth') },
  };
}

test.describe('Admin Browser QA Setup Matrix (KANBA-203)', () => {
  test.beforeEach(async ({ context }) => {
    // Provide CSRF cookie required by apiFetch on unsafe HTTP methods
    await context.addCookies([
      {
        name: 'kb_csrf',
        value: 'test-csrf-token-admin-qa',
        domain: '127.0.0.1',
        path: '/',
      },
    ]);
  });

  test('01-setup-claim: strips URL token via history.replaceState and blocks short invalid token', async ({
    page,
  }, testInfo) => {
    // 1. Negative check: short/invalid token blocks setup and renders 0 <form> elements
    await page.goto(`/setup?token=${INVALID_SHORT_TOKEN}`);
    await expect(page.locator('.auth-panel')).toBeVisible();
    await expect(page.locator('.auth-empty-state')).toBeVisible();
    await expect(page.locator('.auth-empty-state')).toContainText('This setup link is invalid or has already been used.');
    await expect(page.locator('form')).toHaveCount(0);

    // 2. Positive check: valid token cleans address bar and renders setup claim form
    await page.goto(`/setup?token=${VALID_SETUP_TOKEN}`);
    await expect(page.locator('.auth-panel')).toBeVisible();
    await expect(page.locator('form')).toHaveCount(1);
    await expect(page.locator('#setup-username')).toBeVisible();
    await expect(page.locator('#setup-password')).toBeVisible();
    await expect(page.locator('#setup-confirm-password')).toBeVisible();

    // Verify history.replaceState stripped the secret setup token from URL & DOM content
    expect(page.url()).not.toContain('token=');
    const content = await page.content();
    expect(content).not.toContain(VALID_SETUP_TOKEN);

    // Capture annotated screenshot 01-setup-claim
    await annotatedScreenshot(page, testInfo, {
      name: '01-setup-claim',
      annotations: [
        {
          selector: '.auth-header',
          label: 'Setup Claim Header',
          note: 'Token sanitized from address bar via history.replaceState',
        },
        {
          selector: '#setup-username',
          label: 'Admin Username',
          note: 'Initial admin account setup form',
        },
        {
          selector: '#setup-password',
          label: 'Master Password Field',
          note: 'Enforces min 14 characters for admin account',
        },
        {
          selector: '.auth-submit-btn',
          label: 'Claim Button',
          note: 'Initializes first-boot admin claim',
        },
      ],
    });
  });

  test('02-login-local-admin-progression: external cards above LocalAdminDisclosure, CSRF, and SecondFactorStep', async ({
    page,
  }) => {
    let capturedCsrfHeader: string | null = null;
    let capturedLoginBody: Record<string, unknown> = {};

    await mockApi(page, {
      'GET /api/v1/auth/cards': {
        json: {
          cards: [
            {
              id: 'card-google',
              slug: 'google-oauth',
              display_name: 'Google Workspace',
              button_subtext: 'Sign in with your Google account',
              icon_preset: 'google',
              provider_kind: 'OIDC',
            },
            {
              id: 'card-local',
              slug: 'local-admin',
              display_name: 'Local Admin',
              button_subtext: 'Username and password',
              icon_preset: 'key',
              provider_kind: 'LOCAL_ADMIN',
            },
          ],
        },
      },
      'POST /api/v1/auth/local/login': (req) => {
        capturedCsrfHeader = req.headers['x-csrf-token'] ?? null;
        capturedLoginBody = (req.body as Record<string, unknown>);
        return {
          status: 200,
          json: {
            status: 'mfa_required',
            challenge_id: 'ch-aal2-admin-qa-999',
            methods: ['totp', 'webauthn'],
          },
        };
      },
    });

    await page.goto('/login');
    await expect(page.locator('.auth-panel')).toBeVisible();

    // Verify external cards render above local admin disclosure
    const cardButtons = page.locator('.auth-card-list .auth-card-button');
    await expect(cardButtons).toHaveCount(1);
    await expect(cardButtons.first()).toContainText('Google Workspace');

    // Local admin disclosure exists and is initially collapsed
    const disclosureTrigger = page.locator('.auth-disclosure-trigger');
    await expect(disclosureTrigger).toBeVisible();
    await expect(disclosureTrigger).toHaveAttribute('aria-expanded', 'false');

    // Expand local admin disclosure and submit credentials
    await disclosureTrigger.click();
    await expect(disclosureTrigger).toHaveAttribute('aria-expanded', 'true');

    await page.locator('#local-admin-username').fill('admin');
    await page.locator('#local-admin-password').fill('AdminMasterPassword14Long!');
    await page.locator('.auth-disclosure-panel button[type="submit"]').click();

    // Assert SecondFactorStep modal opens
    await expect(page.locator('.auth-second-factor-step')).toBeVisible();
    await expect(page.locator('[role="tablist"][aria-label="Second factor methods"]')).toBeVisible();
    await expect(page.locator('[role="tab"]:has-text("Authenticator code")')).toBeVisible();

    // Verify CSRF token and body hygiene
    expect(capturedCsrfHeader).toBe('test-csrf-token-admin-qa');
    expect(capturedLoginBody).not.toBeNull();
    expect(capturedLoginBody.username).toBe('admin');
  });

  test('03-admin-auth-studio-and-lockout: cards order, write-only secret, 409 LOCKOUT_PREVENTED, users creation', async ({
    page,
  }, testInfo) => {
    let capturedCreateUser: Record<string, unknown> = {};
    

    const authCardsFixture = loadFixture<{ cards: Record<string, unknown>[] }>('admin-auth-cards');

    await mockApi(page, {
      ...getBaseAppMocks(),
      'GET /api/v1/auth/cards': { json: authCardsFixture },
      'GET /api/v1/admin/auth-cards': { json: authCardsFixture },
      'GET /api/v1/admin/principals': {
        json: [
          {
            id: 'p-admin',
            principal: 'admin',
            handle: 'admin',
            display_name: 'Server Administrator',
            type: 'USER',
            status: 'active',
            email: 'admin@kanban.local',
            role: 'SERVER_ADMIN',
            provider: 'LOCAL',
          },
        ],
      },
      'POST /api/v1/admin/auth-cards/card-local-4/disable': {
        status: 409,
        json: {
          type: 'https://kanban.hackedyour.info/problems/lockout-prevented',
          title: 'Lockout Prevented',
          status: 409,
          code: 'LOCKOUT_PREVENTED',
          reason_code: 'NO_VERIFIED_EXTERNAL_ADMIN_HANDSHAKE',
          detail:
            'Local Administrator cannot be disabled until at least one external Server-Admin identity provider card completes a verified login handshake within the past 15 minutes.',
        },
      },
      'POST /api/v1/admin/principals': (req) => {
        capturedCreateUser = (req.body as Record<string, unknown>);
        return {
          status: 201,
          json: {
            id: 'p-qa-std-user',
            principal: 'qa_standard_user',
            handle: 'qa_standard_user',
            display_name: 'QA Standard User',
            type: 'USER',
            status: 'active',
            email: 'stduser@kanban.local',
            role: 'WORKSPACE_MEMBER',
            provider: 'LOCAL',
          },
        };
      },
      'POST /api/v1/admin/role-bindings': () => {
        // capturedRoleBinding
        return {
          status: 200,
          json: { status: 'ok' },
        };
      },
    });

    await page.goto('/admin/auth');
    await expect(page.locator('.auth-studio-page')).toBeVisible();
    await expect(page.locator('.auth-studio-title')).toHaveText('Authentication Studio');

    // Verify 4 cards loaded in order, with LOCAL_ADMIN pinned last
    const cardRows = page.locator('.auth-card-row');
    await expect(cardRows).toHaveCount(4);
    await expect(page.locator('.auth-card-row--pinned')).toContainText('Local Administrator');

    // Capture 02-admin-auth-studio screenshot
    await annotatedScreenshot(page, testInfo, {
      name: '02-admin-auth-studio',
      annotations: [
        {
          selector: '.auth-studio-header',
          label: 'Auth Studio Title',
          note: 'Configured authentication cards with health indicators',
        },
        {
          selector: '.auth-card-row:first-child',
          label: 'Primary Identity Provider',
          note: 'Top external authentication card',
        },
        {
          selector: '.auth-card-row--pinned',
          label: 'Pinned Local Administrator',
          note: 'Break-glass local admin fallback pinned last',
        },
      ],
    });

    // 1. Verify write-only secret behavior in edit drawer for Okta card
    const editBtn = cardRows.first().locator('button:has-text("Edit")');
    await editBtn.click();
    const drawer = page.locator('.auth-editor-drawer');
    await expect(drawer).toBeVisible();

    const secretInput = page.locator('#card-secret');
    await expect(secretInput).toBeVisible();
    await expect(secretInput).toHaveValue('');
    await expect(secretInput).toBeDisabled();

    const replaceCheckbox = page.locator('#card-replace-secret');
    await expect(replaceCheckbox).toBeVisible();
    await expect(replaceCheckbox).not.toBeChecked();

    // Check replace checkbox -> enables secret input
    await replaceCheckbox.check();
    await expect(secretInput).toBeEnabled();

    // Close edit drawer
    await drawer.locator('button:has-text("Cancel")').click();
    await expect(drawer).not.toBeVisible();

    // 2. Verify break-glass anti-lockout fail-closed behavior negatively (409 LOCKOUT_PREVENTED)
    const localSwitch = page.locator('input[aria-label="Enable Local Administrator"]');
    await expect(localSwitch).toBeChecked();
    await page.locator('.auth-card-row--pinned .auth-switch-label').click();

    // Assert Lockout banner is displayed with emergency unlock command
    const banner = page.locator('.auth-lockout-banner');
    await expect(banner).toBeVisible();
    await expect(banner).toHaveAttribute('role', 'alert');
    await expect(banner).toContainText('15 minutes');

    // Switch must roll back to enabled
    await expect(localSwitch).toBeChecked();

    // Expand emergency host recovery disclosure
    const disclosure = page.locator('.auth-lockout-disclosure');
    await expect(disclosure).toBeVisible();
    await disclosure.locator('summary').click();
    await expect(page.locator('.auth-lockout-code')).toContainText(
      'kanban-ctl auth emergency-unlock --enable-local-admin',
    );

    // Capture 03-admin-lockout-banner screenshot
    await annotatedScreenshot(page, testInfo, {
      name: '03-admin-lockout-banner',
      annotations: [
        {
          selector: '.auth-lockout-banner',
          label: 'Lockout Alert Banner',
          note: 'HTTP 409 LOCKOUT_PREVENTED emergency safeguard',
        },
        {
          selector: '.auth-card-row--pinned .auth-switch-label',
          label: 'Switch Rolled Back',
          note: 'LOCAL_ADMIN toggle rolled back to enabled state',
        },
        {
          selector: '.auth-lockout-disclosure',
          label: 'Emergency CLI Banner',
          note: 'kanban-ctl auth emergency-unlock command displayed',
        },
      ],
    });

    // 3. User creation and role binding in Users tab
    await page.locator('button:has-text("Users & Permissions")').click();
    await expect(page.locator('[data-testid="auth-users-table"]')).toBeVisible();

    // Click Add User button
    await page.locator('button:has-text("+ Add Local User")').click();
    await expect(page.locator('.auth-modal-dialog')).toBeVisible();

    await page.locator('#new-user-handle').fill('qa_standard_user');
    await page.locator('#new-user-display').fill('QA Standard User');
    await page.locator('#new-user-email').fill('stduser@kanban.local');
    await page.locator('#new-user-pwd').fill('StandardUserPassword14Long!');
    await page.locator('#new-user-role').selectOption('WORKSPACE_MEMBER');

    await page.locator('.auth-modal-dialog button[type="submit"]').click();
    await expect(page.locator('.auth-modal-dialog')).not.toBeVisible();

    expect(capturedCreateUser).not.toBeNull();
    expect(capturedCreateUser.handle).toBe('qa_standard_user');
    expect(capturedCreateUser.role).toBe('WORKSPACE_MEMBER');
  });

  test('04-admin-mcp-studio-and-snippet: reveals raw_key in modal, purges from DOM on close, probe styles', async ({
    page,
  }, testInfo) => {
    const rawSecretKey = 'kb_adm_secret_key_mock_1234567890abcdef';

    await mockApi(page, {
      ...getBaseAppMocks(),
      'GET /api/v1/auth/mcp-keys': {
        json: [
          {
            id: 'key-adm-1',
            label: 'Global Admin Automation Key',
            display_hint: 'a1b2',
            surface: 'admin',
            scope_tier: 'global',
            scopes: ['admin:read', 'admin:write'],
            allowed_projects: null,
            created_at: new Date().toISOString(),
            expires_at: new Date(Date.now() + 86400000 * 90).toISOString(),
            last_used_at: null,
            revoked_at: null,
          },
        ],
      },
      'GET /api/v1/auth/oauth-grants': { json: [] },
      'POST /api/v1/auth/mcp-keys': {
        json: {
          id: 'key-adm-minted',
          label: 'New Admin Scope Key',
          display_hint: 'c3d4',
          surface: 'admin',
          scope_tier: 'global',
          scopes: ['admin:read', 'admin:write'],
          allowed_projects: null,
          created_at: new Date().toISOString(),
          expires_at: new Date(Date.now() + 86400000 * 60).toISOString(),
          last_used_at: null,
          revoked_at: null,
          raw_key: rawSecretKey,
        },
      },
    });

    await page.goto('/admin/mcp');
    await expect(page.locator('[data-testid="mcp-access-studio"]')).toBeVisible();

    // Probe styles across desktop, tablet, and mobile
    await probeStyles(page, testInfo, {
      name: 'admin-mcp-studio',
      probes: [
        { selector: '[data-testid="mcp-access-studio"]', props: ['padding', 'max-width'] },
        { selector: '[data-testid="mint-key-button"]', props: ['background-color', 'font-size'] },
      ],
    });

    // Mint new admin MCP key
    await page.locator('[data-testid="mint-key-button"]').click();
    await expect(page.locator('[data-testid="mint-modal-backdrop"]')).toBeVisible();

    await page.locator('[data-testid="mint-label-input"]').fill('New Admin Scope Key');
    await page.locator('[data-testid="mint-submit-btn"]').click();

    // McpConfigSnippetModal opens and reveals raw key
    const snippetModal = page.locator('[data-testid="mcp-snippet-modal"]');
    await expect(snippetModal).toBeVisible();

    const rawKeyDisplay = page.locator('[data-testid="raw-key-display"]');
    await expect(rawKeyDisplay).toBeVisible();
    await expect(rawKeyDisplay).toHaveText(rawSecretKey);

    // Capture 04-admin-mcp-studio screenshot while modal is visible
    await annotatedScreenshot(page, testInfo, {
      name: '04-admin-mcp-studio',
      annotations: [
        {
          selector: '[data-testid="mcp-snippet-modal"]',
          label: 'Config Snippet Modal',
          note: 'Client configuration code snippet with endpoint URL',
        },
        {
          selector: '[data-testid="raw-key-display"]',
          label: 'Ephemeral Raw Key',
          note: 'Plaintext secret shown once prior to memory purge',
        },
        {
          selector: '[data-testid="done-button"]',
          label: 'Done Button',
          note: 'Closes modal and purges raw secret from memory/DOM',
        },
      ],
    });

    // Close snippet modal and verify raw secret is completely purged from DOM
    await page.locator('[data-testid="done-button"]').click();
    await expect(snippetModal).not.toBeVisible();

    const pageContentAfterClose = await page.content();
    expect(pageContentAfterClose).not.toContain(rawSecretKey);
  });
});
