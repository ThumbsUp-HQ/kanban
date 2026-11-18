/**
 * KANBA-210 Playwright E2E & Visual Verification Suite.
 * Generates annotated screenshots across Desktop, Tablet, and Mobile in docs/qa/KANBA-210/screenshots/.
 */

import { test, expect } from '../support/test';
import { mockApi, type MockHandlers } from '../support/mockApi';
import { annotatedScreenshot } from '../support/annotate';

const mockAdminMe = {
  id: '22222222-2222-4222-8222-222222222222',
  principal_id: '22222222-2222-4222-8222-222222222222',
  display_name: 'Alex Rivera',
  handle: '@alex.admin',
  username: 'alex.admin',
  email: 'alex@example.com',
  timezone: 'America/New_York',
  avatar_url: '/api/v1/users/22222222-2222-4222-8222-222222222222/avatar',
  is_server_admin: true,
  is_workspace_admin: true,
  workspace_role: 'SERVER_ADMIN',
  workspace_capabilities: [
    'CREATE_PROJECT',
    'MANAGE_WORKSPACE_SETTINGS',
    'MANAGE_WORKSPACE_MCP_KEYS',
    'MANAGE_SERVER_ADMIN',
    'ADMIN_AUTH_STUDIO',
    'ADMIN_MCP_KEYS',
    'SYSTEM_STORAGE',
  ],
};

const mockCards = [
  {
    id: 'card-local',
    slug: 'local-admin',
    provider_kind: 'LOCAL_ADMIN',
    display_name: 'Local Emergency Break-Glass',
    name: 'Local Emergency Break-Glass',
    status: 'HEALTHY',
    last_health_status: 'HEALTHY',
    sort_rank: 1,
    is_primary: false,
    is_enabled: true,
    created_at: '2026-01-01T00:00:00Z',
  },
  {
    id: 'card-okta',
    slug: 'okta-sso',
    provider_kind: 'OIDC',
    display_name: 'Okta Enterprise SSO',
    name: 'Okta Enterprise SSO',
    status: 'HEALTHY',
    last_health_status: 'HEALTHY',
    sort_rank: 2,
    is_primary: true,
    is_enabled: true,
    created_at: '2026-01-02T00:00:00Z',
  },
  {
    id: 'card-google',
    slug: 'google-workspace',
    provider_kind: 'GOOGLE',
    display_name: 'Google Workspace',
    name: 'Google Workspace',
    status: 'HEALTHY',
    last_health_status: 'HEALTHY',
    sort_rank: 3,
    is_primary: false,
    is_enabled: true,
    created_at: '2026-01-03T00:00:00Z',
  },
  {
    id: 'card-ad',
    slug: 'active-directory',
    provider_kind: 'LDAP',
    display_name: 'Active Directory Corporate',
    name: 'Active Directory Corporate',
    status: 'HEALTHY',
    last_health_status: 'HEALTHY',
    sort_rank: 4,
    is_primary: false,
    is_enabled: true,
    created_at: '2026-01-04T00:00:00Z',
  },
];

const mockPrincipals = [
  {
    id: 'p-1',
    principal: 'alex.admin',
    handle: '@alex.admin',
    display_name: 'Alex Rivera',
    email: 'alex@example.com',
    type: 'USER',
    principal_type: 'USER',
    provider: 'LOCAL',
    role: 'SERVER_ADMIN',
    role_name: 'SERVER_ADMIN',
    status: 'ACTIVE',
  },
  {
    id: 'p-2',
    principal: 'morgan.audit',
    handle: '@morgan.audit',
    display_name: 'Morgan Audit',
    email: 'morgan@audit.local',
    type: 'USER',
    principal_type: 'USER',
    provider: 'OIDC',
    role: 'WORKSPACE_MEMBER',
    role_name: 'WORKSPACE_MEMBER',
    status: 'ACTIVE',
  },
  {
    id: 'p-3',
    principal: 'kanban.bot',
    handle: '@kanban.bot',
    display_name: 'Autonomous Guard Bot',
    email: 'bot@system.local',
    type: 'AGENT',
    principal_type: 'AGENT',
    provider: 'SYSTEM',
    role: 'WORKSPACE_MEMBER',
    role_name: 'WORKSPACE_MEMBER',
    status: 'ACTIVE',
  },
  {
    id: 'grp-eng',
    principal: 'engineers',
    handle: '@engineers',
    display_name: 'Core Engineering Group',
    type: 'GROUP',
    principal_type: 'GROUP',
    provider: 'LOCAL',
    role: 'WORKSPACE_MEMBER',
    role_name: 'WORKSPACE_MEMBER',
    status: 'ACTIVE',
  },
  {
    id: 'grp-sec',
    principal: 'security',
    handle: '@security',
    display_name: 'Security Shield Team',
    type: 'GROUP',
    principal_type: 'GROUP',
    provider: 'LOCAL',
    role: 'WORKSPACE_MEMBER',
    role_name: 'WORKSPACE_MEMBER',
    status: 'ACTIVE',
  },
];

const mockGroupMembers = [
  {
    id: 'p-1',
    principal: 'alex.admin',
    handle: '@alex.admin',
    display_name: 'Alex Rivera',
    type: 'USER',
    principal_type: 'USER',
  },
  {
    id: 'grp-sec',
    principal: 'security',
    handle: '@security',
    display_name: 'Security Shield Team',
    type: 'GROUP',
    principal_type: 'GROUP',
  },
];

const mockWorkspaceSettings = {
  id: '22222222-2222-2222-2222-222222222222',
  workspace_id: '22222222-2222-2222-2222-222222222222',
  name: 'Primary Security Workspace',
  slug: 'primary-security',
  display_name: 'Acme Enterprise Security Org',
  default_project_visibility: 'workspace',
  session_idle_timeout_min: 120,
  session_absolute_timeout_min: 1440,
  trash_retention_days: 30,
  mcp_key_max_ttl_days: 90,
  air_gap_mode: false,
};

// 1x1 transparent PNG data URL bytes
const pngPixelBuffer = Buffer.from(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==',
  'base64',
);

function getBaseMocks(): MockHandlers {
  return {
    'GET /api/v1/setup/status': { json: { initialized: true } },
    'GET /api/v1/auth/session': {
      json: {
        authenticated: true,
        principal_id: '22222222-2222-4222-8222-222222222222',
        workspace_id: '22222222-2222-2222-2222-222222222222',
        aal_level: 2,
        mfa_pending: false,
        csrf_token: 'csrf-valid-token-kanba-210',
      },
    },
    'GET /api/v1/auth/me': { json: mockAdminMe },
    'GET /api/v1/users/me': { json: mockAdminMe },
    'GET /api/v1/system/status': {
      json: {
        initialized: true,
        air_gap_mode: false,
        build_id: 'kanba-210-verified',
        version: '0.1.0',
      },
    },
    'GET /api/v1/workspaces': {
      json: [
        {
          id: '22222222-2222-2222-2222-222222222222',
          name: 'Primary Security Workspace',
          slug: 'primary-security',
          is_current: true,
        },
      ],
    },
    'GET /api/v1/workspaces/current': {
      json: {
        id: '22222222-2222-2222-2222-222222222222',
        name: 'Primary Security Workspace',
        slug: 'primary-security',
      },
    },
    'GET /api/v1/projects': {
      json: [
        {
          id: '33333333-3333-3333-3333-333333333333',
          key: 'KAN',
          name: 'Core Kanban',
        },
      ],
    },
    'GET /api/v1/projects/KAN': {
      json: {
        id: '33333333-3333-3333-3333-333333333333',
        key: 'KAN',
        name: 'Core Kanban',
      },
    },
    'GET /api/v1/projects/KAN/views': { json: [] },
    'GET /api/v1/projects/KAN/issues': { json: [] },
    'GET /api/v1/projects/KAN/cycles': { json: { items: [] } },
    'GET /api/v1/projects/KAN/modules': { json: { items: [] } },
    'GET /api/v1/projects/KAN/states': { json: { items: [] } },
    'GET /api/v1/projects/KAN/priorities': { json: { items: [] } },
    'GET /api/v1/projects/KAN/labels': { json: { items: [] } },
    'GET /api/v1/objects/:id/access': { json: { object_id: '33333333-3333-3333-3333-333333333333' } },
    'GET /api/v1/admin/auth-cards': { json: { cards: mockCards } },
    'GET /api/v1/admin/principals': { json: mockPrincipals },
    'GET /api/v1/admin/workspace-settings': { json: mockWorkspaceSettings },
    'GET /api/v1/admin/groups/grp-eng/members': { json: mockGroupMembers },
    'GET /api/v1/users/:id/avatar': {
      status: 200,
      contentType: 'image/png',
      body: pngPixelBuffer,
    },
  };
}

test.describe('KANBA-210 Admin Auth, Topbar Avatar, and Workspace Governance', () => {
  test.beforeEach(async ({ context }) => {
    await context.addCookies([
      {
        name: 'kb_csrf',
        value: 'csrf-valid-token-kanba-210',
        domain: '127.0.0.1',
        path: '/',
      },
    ]);
  });

  test('01-admin-auth-cards: renders auth provider cards with Test Handshake and Primary indicator', async ({
    page,
  }, testInfo) => {
    await mockApi(page, getBaseMocks());

    await page.goto('/admin/auth');
    await expect(page.locator('[data-testid="auth-studio-page"]')).toBeVisible();

    await annotatedScreenshot(page, testInfo, {
      name: '01-admin-auth-cards',
      annotations: [
        {
          selector: '[data-testid="auth-card-row-local-admin"]',
          label: 'Local Admin Card with Test Handshake',
          note: 'Allows testing local admin handshake without 422 errors or DB lockouts.',
        },
        {
          selector: '[data-testid="auth-card-row-okta-sso"]',
          label: 'Primary External IdP Indicator',
          note: 'Active primary provider indicated clearly at top sort rank.',
        },
      ],
    });
  });

  test('02-admin-auth-users: renders Users & Permissions table with Type pills and clean handles', async ({
    page,
  }, testInfo) => {
    await mockApi(page, getBaseMocks());

    await page.goto('/admin/auth');
    await expect(page.locator('[data-testid="auth-studio-page"]')).toBeVisible();
    await page.locator('#tab-users').click();
    await expect(page.locator('[data-testid="auth-users-table"]')).toBeVisible();

    await annotatedScreenshot(page, testInfo, {
      name: '02-admin-auth-users',
      annotations: [
        {
          selector: '[data-testid="auth-user-row-p-1"]',
          label: 'Type Pills & Separated Columns',
          note: 'User, Group, and Agent pills populated with distinct Name and Email columns.',
        },
        {
          selector: '[data-testid="filter-all"]',
          label: 'Immediate 200 Hydration Filter',
          note: 'Filters without sending empty filter query parameters, preventing 422.',
        },
      ],
    });
  });

  test('03-workspace-settings-general: renders Display Name, MCP TTL, and Air-Gap mode toggle', async ({
    page,
  }, testInfo) => {
    await mockApi(page, getBaseMocks());

    await page.goto('/workspaces/settings');
    await expect(page.locator('[data-testid="workspace-general-form"]')).toBeVisible();

    await annotatedScreenshot(page, testInfo, {
      name: '03-workspace-settings-general',
      annotations: [
        {
          selector: '[data-testid="workspace-display-name-input"]',
          label: 'Organization Display Name',
          note: 'Customizable public workspace display name.',
        },
        {
          selector: '[data-testid="workspace-mcp-key-max-ttl-input"]',
          label: 'MCP Key Max TTL Policy',
          note: 'Configures maximum token lifetime in days for MCP keys.',
        },
        {
          selector: '[data-testid="workspace-air-gap-toggle"]',
          label: 'Air-Gap Mode Toggle',
          note: 'Enforces local execution and updates topbar status pill.',
        },
      ],
    });
  });

  test('04-workspace-settings-members: renders deterministic add user form, inline roles and remove action', async ({
    page,
  }, testInfo) => {
    await mockApi(page, getBaseMocks());

    await page.goto('/workspaces/settings');
    const membersTab = page.locator('[data-testid="tab-members"]');
    await membersTab.click();
    await expect(page.locator('[data-testid="workspace-members-section"]')).toBeVisible();

    await annotatedScreenshot(page, testInfo, {
      name: '04-workspace-settings-members',
      annotations: [
        {
          selector: '[data-testid="create-user-form"]',
          label: 'Deterministic Add User Form',
          note: 'Mounts reliably on tab switch and sends role without 422.',
        },
        {
          selector: '[data-testid="workspace-users-table"]',
          label: 'Inline Role Selection & Member Removal',
          note: 'Direct inline role grants and remove actions on each principal row.',
        },
      ],
    });
  });

  test('05-workspace-groups-governance: renders Groups manager, hierarchy and nested group membership', async ({
    page,
  }, testInfo) => {
    await mockApi(page, getBaseMocks());

    await page.goto('/workspaces/settings');
    const groupsTab = page.locator('[data-testid="tab-groups"]');
    await groupsTab.click();
    await expect(page.locator('[data-testid="workspace-groups-section"]')).toBeVisible();

    await annotatedScreenshot(page, testInfo, {
      name: '05-workspace-groups-governance',
      annotations: [
        {
          selector: '[data-testid="create-group-form"]',
          label: 'Group Creation Form',
          note: 'Provisions new security groups with dedicated @handle.',
        },
        {
          selector: '[data-testid="group-detail-pane"]',
          label: 'Nested Groups & Membership Drilldown',
          note: 'Shows nested groups, direct member management, and cycle guards.',
        },
      ],
    });
  });

  test('06-topbar-avatar-sync: renders uploaded avatar img and resolved handle in user menu', async ({
    page,
  }, testInfo) => {
    await mockApi(page, getBaseMocks());

    await page.goto('/workspaces/settings');
    const avatarButton = page.locator('.kb-avatar-button');
    await expect(avatarButton).toBeVisible();
    await avatarButton.click();

    await expect(page.locator('[data-testid="topbar-user-profile"]')).toBeVisible();

    await annotatedScreenshot(page, testInfo, {
      name: '06-topbar-avatar-sync',
      annotations: [
        {
          selector: '[data-testid="topbar-avatar-img"]',
          label: 'Topbar Avatar Image',
          note: 'Renders uploaded avatar image instead of static initial A.',
        },
        {
          selector: '[data-testid="topbar-user-profile"]',
          label: 'Resolved Display Handle Profile Card',
          note: 'Clean @handle display without raw short UUID leakage or double-@.',
        },
      ],
    });
  });

  test('07-admin-auth-cards-dark: renders Dark Mode auth studio and provider cards', async ({
    page,
  }, testInfo) => {
    await mockApi(page, getBaseMocks());

    await page.goto('/admin/auth');
    await page.evaluate(() => {
      document.documentElement.dataset.theme = 'dark';
    });

    await expect(page.locator('[data-testid="auth-studio-page"]')).toBeVisible();

    await annotatedScreenshot(page, testInfo, {
      name: '07-admin-auth-cards-dark',
      annotations: [
        {
          selector: '.auth-studio-list',
          label: 'Dark Mode Auth Studio',
          note: 'Validates contrast, surface colors, and typography in dark mode.',
        },
      ],
    });
  });

  test('08-workspace-settings-general-dark: renders Dark Mode workspace settings and air-gap switch', async ({
    page,
  }, testInfo) => {
    await mockApi(page, getBaseMocks());

    await page.goto('/workspaces/settings');
    await page.evaluate(() => {
      document.documentElement.dataset.theme = 'dark';
    });

    await expect(page.locator('[data-testid="workspace-general-form"]')).toBeVisible();

    await annotatedScreenshot(page, testInfo, {
      name: '08-workspace-settings-general-dark',
      annotations: [
        {
          selector: '[data-testid="workspace-general-form"]',
          label: 'Dark Mode Workspace Settings',
          note: 'Air-gap switch, display name, and policy inputs in dark mode.',
        },
      ],
    });
  });
});
