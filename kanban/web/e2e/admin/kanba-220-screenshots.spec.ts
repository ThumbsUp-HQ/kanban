// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import { resolve } from 'node:path';
import { mkdirSync } from 'node:fs';
import type { Page } from '@playwright/test';
import { test, expect } from '../support/test';
import { mockApi, type MockHandlers } from '../support/mockApi';
import { annotatedScreenshot } from '../support/annotate';

const SCREENSHOT_DIR = resolve(
  import.meta.dirname,
  '../../../../docs/qa/KANBA-220/screenshots',
);

process.env.QA_TICKET_ID = 'KANBA-220';
mkdirSync(SCREENSHOT_DIR, { recursive: true });

const OBJECT_ID_142 = 'c0000000-0000-0000-0000-000000000142';

const mockAdminUser = {
  id: 'usr-admin-1',
  handle: 'adam_architect',
  display_name: 'Adam Architect',
  email: 'adam@example.com',
  workspace_role: 'WORKSPACE_ADMIN',
  is_workspace_admin: true,
  is_server_admin: true,
  aal_level: 2,
  auth_aal: 'aal2',
};

const mockProject = {
  id: 'proj-kan-1',
  identifier: 'KAN',
  name: 'Platform Core',
  description_markdown: 'Core platform engineering workspace',
  modules_enabled: true,
  auto_archive_days: 90,
  capabilities: ['VIEW', 'COMMENT', 'EDIT', 'SHARE', 'ADMIN', 'PROJECT_ADMIN'],
  is_project_admin: true,
  project_role: 'ADMIN',
};

const mockWorkspaces = [
  {
    id: '01a1f1aa-7d7a-782f-a996-6a87f9e9e667',
    name: 'Platform Engineering',
    slug: 'platform-engineering',
    is_current: true,
  },
];

const mockStates = [
  { id: 'st-todo', name: 'To Do', group: 'unstarted', sort_order: 1 },
  { id: 'st-in-progress', name: 'In Progress', group: 'started', sort_order: 2 },
  { id: 'st-done', name: 'Done', group: 'completed', sort_order: 3 },
];

const mockPriorities = {
  items: [
    { id: 'prio-high', slug: 'high', label: 'High', emoji: '⚡', sort_order: 1 },
  ],
};

const issueKan142 = {
  id: OBJECT_ID_142,
  key: 'KAN-142',
  object_id: OBJECT_ID_142,
  project_key: 'KAN',
  project_name: 'Platform Core',
  summary: 'Implement Access Manifest Inspector & Link Auditor',
  description_markdown: 'Detailed description of the auth hardening task.',
  priority: {
    slug: 'high',
    label: 'High',
    emoji: '⚡',
    sort_order: 2,
    sla_target: null,
  },
  state: {
    name: 'In Progress',
    group: 'started',
  },
  capabilities: ['VIEW', 'COMMENT', 'EDIT', 'SHARE', 'ADMIN'],
  etag: '"etag-kan-142"',
};

const mockIssues = {
  items: [issueKan142],
  total: 1,
};

const mockAccessManifest = {
  object_id: OBJECT_ID_142,
  canonical_key: 'KAN-142',
  object_type: 'ISSUE',
  caller_capabilities: ['VIEW', 'COMMENT', 'EDIT', 'TRANSITION', 'LINK', 'SHARE', 'ADMIN'],
  effective_permissions: {
    view: true,
    comment: true,
    edit: true,
    transition: true,
    link: true,
    share: true,
    admin: true,
    delete: true,
  },
  provenance_chain: [
    {
      capability: 'ADMIN',
      effect: 'ALLOW',
      grant_source: 'project_role',
      inherited_from: 'Project: KAN',
      priority: 100,
    },
    {
      capability: 'SHARE',
      effect: 'ALLOW',
      grant_source: 'project_role',
      inherited_from: 'Project: KAN',
      priority: 90,
    },
  ],
  inherited_scope: {
    kind: 'project',
    scope_label: 'Project: KAN',
    workspace_id: '01a1f1aa-7d7a-782f-a996-6a87f9e9e667',
    workspace_name: 'Platform Engineering',
    project_id: 'proj-kan-1',
    project_key: 'KAN',
    project_name: 'Platform Core',
  },
  users: [
    {
      principal_id: 'usr-admin-1',
      handle: '@adam_architect',
      display_name: 'Adam Architect',
      capabilities: ['VIEW', 'COMMENT', 'EDIT', 'SHARE', 'ADMIN'],
      grant_source: 'project_role',
    },
    {
      principal_id: 'usr-alice',
      handle: '@alice',
      display_name: 'Alice Smith',
      capabilities: ['VIEW', 'COMMENT', 'EDIT'],
      grant_source: 'direct_share',
    },
  ],
  groups: [
    {
      principal_id: 'grp-core',
      name: 'Core Platform Engineering',
      member_count: 8,
      external_source: 'LDAP',
      capabilities: ['VIEW', 'COMMENT', 'EDIT'],
      grant_source: 'group_binding',
    },
  ],
  agents: [
    {
      principal_id: 'agent-codebot',
      display_name: 'Codebot (openai/gpt-4o)',
      principal_type: 'AGENT',
      provider_badge: 'openai/gpt-4o',
      scope_summary: 'Scoped to Project KAN',
      role: 'Agent Collaborator',
      capabilities: ['VIEW', 'COMMENT', 'EDIT', 'TRANSITION'],
    },
  ],
  deny_overrides: [
    {
      principal_id: 'grp-contractors',
      principal_type: 'GROUP',
      display_name: 'Contractor Vendors',
      denied_capabilities: ['DELETE', 'ADMIN'],
      redacted: false,
    },
  ],
  redacted_count: 1,
  redacted_entries: [
    {
      kind: 'user',
      masked_label: 'External Collaborator',
      count: 1,
    },
  ],
};

const mockPrincipals = [
  { id: 'usr-bob', display_name: 'Bob Builder', handle: '@bob', principal_type: 'USER' },
  { id: 'usr-carol', display_name: 'Carol Security', handle: '@carol', principal_type: 'USER' },
  { id: 'grp-security', display_name: 'Security Team', name: 'Security Team', principal_type: 'GROUP' },
  { id: 'agent-auditor', display_name: 'AuditBot', principal_type: 'AGENT' },
];

const mockAuditItems = [
  {
    id: 'aud-1',
    workspace_id: 'ws-1',
    link_id: 'lnk-1',
    reason: 'DANGLING_TARGET',
    detected_at: '2026-11-19T02:00:00Z',
    purged_at: null,
    resolved_at: null,
    link_snapshot: {
      id: 'lnk-1',
      source_id: 'iss-142',
      target_id: 'iss-999-deleted',
      link_type: 'BLOCKS',
      status: 'flagged',
      metadata: { detected_reason: 'DANGLING_TARGET' },
    },
    source_snapshot: {
      id: 'iss-142',
      key: 'KAN-142',
      title: 'Implement Access Manifest Inspector',
      object_type: 'ISSUE',
      is_deleted: false,
    },
    target_snapshot: null,
  },
  {
    id: 'aud-2',
    workspace_id: 'ws-1',
    link_id: 'lnk-2',
    reason: 'SOFT_DELETED_ENDPOINT',
    detected_at: '2026-11-19T02:10:00Z',
    purged_at: null,
    resolved_at: null,
    link_snapshot: {
      id: 'lnk-2',
      source_id: 'doc-1',
      target_id: 'iss-142',
      link_type: 'RELATES_TO',
      status: 'flagged',
      metadata: { detected_reason: 'SOFT_DELETED_ENDPOINT' },
    },
    source_snapshot: {
      id: 'doc-1',
      title: 'Architecture Blueprint',
      object_type: 'DOC',
      is_deleted: true,
    },
    target_snapshot: {
      id: 'iss-142',
      key: 'KAN-142',
      title: 'Implement Access Manifest Inspector',
      object_type: 'ISSUE',
      is_deleted: false,
    },
  },
  {
    id: 'aud-3',
    workspace_id: 'ws-1',
    link_id: 'lnk-3',
    reason: 'CROSS_WORKSPACE_LEAK',
    detected_at: '2026-11-19T02:20:00Z',
    purged_at: null,
    resolved_at: null,
    link_snapshot: {
      id: 'lnk-3',
      source_id: 'iss-142',
      target_id: 'iss-other-ws',
      link_type: 'RELATES_TO',
      status: 'flagged',
      metadata: { detected_reason: 'CROSS_WORKSPACE_LEAK' },
    },
    source_snapshot: {
      id: 'iss-142',
      key: 'KAN-142',
      title: 'Implement Access Manifest Inspector',
      object_type: 'ISSUE',
      is_deleted: false,
    },
    target_snapshot: {
      id: 'iss-other-ws',
      key: 'SEC-44',
      title: 'External Workspace Item',
      object_type: 'ISSUE',
      is_deleted: false,
    },
  },
  {
    id: 'aud-4',
    workspace_id: 'ws-1',
    link_id: 'lnk-4',
    reason: 'PERMISSION_SEVERED',
    detected_at: '2026-11-19T02:30:00Z',
    purged_at: null,
    resolved_at: null,
    link_snapshot: {
      id: 'lnk-4',
      source_id: 'iss-142',
      target_id: 'secret-page-1',
      link_type: 'MENTIONS',
      status: 'flagged',
      metadata: { detected_reason: 'PERMISSION_SEVERED' },
    },
    source_snapshot: {
      id: 'iss-142',
      key: 'KAN-142',
      title: 'Implement Access Manifest Inspector',
      object_type: 'ISSUE',
      is_deleted: false,
    },
    target_snapshot: {
      id: 'secret-page-1',
      title: 'Restricted Security Notes',
      object_type: 'PAGE',
      is_deleted: false,
    },
  },
  {
    id: 'aud-5',
    workspace_id: 'ws-1',
    link_id: 'lnk-5',
    reason: 'DANGLING_SOURCE',
    detected_at: '2026-11-19T02:40:00Z',
    purged_at: null,
    resolved_at: null,
    link_snapshot: {
      id: 'lnk-5',
      source_id: 'deleted-page-9',
      target_id: 'iss-142',
      link_type: 'REFERENCES',
      status: 'flagged',
      metadata: { detected_reason: 'DANGLING_SOURCE' },
    },
    source_snapshot: null,
    target_snapshot: {
      id: 'iss-142',
      key: 'KAN-142',
      title: 'Implement Access Manifest Inspector',
      object_type: 'ISSUE',
      is_deleted: false,
    },
  },
  {
    id: 'aud-6',
    workspace_id: 'ws-1',
    link_id: 'lnk-6',
    reason: 'TYPE_MATRIX_VIOLATION',
    detected_at: '2026-11-19T02:50:00Z',
    purged_at: null,
    resolved_at: null,
    link_snapshot: {
      id: 'lnk-6',
      source_id: 'sticky-1',
      target_id: 'user-2',
      link_type: 'PARENT_OF',
      status: 'flagged',
      metadata: { detected_reason: 'TYPE_MATRIX_VIOLATION' },
    },
    source_snapshot: {
      id: 'sticky-1',
      title: 'Quick Sticky',
      object_type: 'STICKY',
      is_deleted: false,
    },
    target_snapshot: {
      id: 'user-2',
      title: 'User Profile',
      object_type: 'USER',
      is_deleted: false,
    },
  },
];

function getCommonMocks(): MockHandlers {
  return {
    'GET /api/v1/auth/me': { json: mockAdminUser },
    'GET /api/v1/me': { json: mockAdminUser },
    'GET /api/v1/auth/session': { json: { csrf_token: 'mock-csrf-token' } },
    'GET /api/v1/setup/status': { json: { initialized: true, is_initialized: true, requires_setup: false } },
    'GET /api/v1/admin/principals': { json: mockPrincipals },
    'GET /api/v1/admin/workspace-settings': {
      json: {
        id: 'ws-default',
        name: 'Platform Engineering',
        slug: 'platform-engineering',
        default_project_visibility: 'workspace',
        session_idle_timeout_min: 120,
        session_absolute_timeout_min: 1440,
        trash_retention_days: 30,
      },
    },
    'GET /api/v1/system/status': {
      json: {
        deployment_mode: 'multi_container',
        air_gap_mode: false,
        persistent_volume: true,
      },
    },
    'GET /api/v1/workspaces/current': { json: mockWorkspaces[0] },
    'GET /api/v1/workspaces': { json: mockWorkspaces },
    'GET /api/v1/projects': { json: [mockProject] },
    'GET /api/v1/projects/KAN': { json: mockProject },
    'GET /api/v1/projects/KAN/states': { json: mockStates },
    'GET /api/v1/projects/KAN/priorities': { json: mockPriorities },
    'GET /api/v1/projects/KAN/labels': { json: { items: [] } },
    'GET /api/v1/projects/KAN/cycles': { json: { items: [] } },
    'GET /api/v1/projects/KAN/modules': { json: { items: [] } },
    'GET /api/v1/projects/KAN/issues': { json: mockIssues },
    'GET /api/v1/projects/KAN/views': { json: { items: [], total: 0 } },
    'GET /api/v1/projects/KAN/custom-fields': { json: [] },
    'GET /api/v1/issues/KAN-142': { json: issueKan142 },
    'GET /api/v1/issues/KAN-142/activity': { json: { items: [], total: 0 } },
    'GET /api/v1/issues/KAN-142/comments': { json: { items: [], total: 0 } },
    'GET /api/v1/issues/KAN-142/state': { json: { name: 'In Progress', group: 'started' } },
    'GET /api/v1/issues/KAN-142/subscription': { json: { subscribed: false } },
    'GET /api/v1/objects/KAN-142/canonical-url': { json: { url: '/projects/KAN/issues/KAN-142' } },
    'GET /api/v1/objects/KAN/access': { json: mockAccessManifest },
    'GET /api/v1/objects/KAN-142/access': { json: mockAccessManifest },
    [`GET /api/v1/objects/${OBJECT_ID_142}/access`]: { json: mockAccessManifest },
    'GET /api/v1/objects/:id/access': { json: mockAccessManifest },
    'GET /api/v1/objects/:id/access/principals': { json: mockPrincipals },
    'POST /api/v1/objects/:id/access/entries': { json: { status: 'granted' } },
    'DELETE /api/v1/objects/:id/access/entries': { json: { status: 'revoked' } },
    'POST /api/v1/objects/:id/agent-kill-switch': {
      json: {
        object_id: OBJECT_ID_142,
        revoked_count: 1,
        revoked_agents: ['agent-codebot'],
        timestamp: '2026-11-19T03:00:00Z',
      },
    },
    'POST /api/v1/objects/:id/access/agent-kill-switch': {
      json: {
        object_id: OBJECT_ID_142,
        revoked_count: 1,
        revoked_agents: ['agent-codebot'],
        timestamp: '2026-11-19T03:00:00Z',
      },
    },
    'GET /api/v1/admin/object-links/audits': {
      json: {
        items: mockAuditItems,
        has_more: false,
        total: 6,
      },
    },
    'POST /api/v1/admin/object-links:audit': {
      json: {
        flagged_total: 6,
        by_reason: {
          DANGLING_TARGET: 1,
          SOFT_DELETED_ENDPOINT: 1,
          CROSS_WORKSPACE_LEAK: 1,
          PERMISSION_SEVERED: 1,
          DANGLING_SOURCE: 1,
          TYPE_MATRIX_VIOLATION: 1,
        },
      },
    },
    'POST /api/v1/admin/object-links:purge': {
      json: {
        purged_count: 1,
        activity_ids: ['act-1'],
      },
    },
    'GET /api/v1/notifications': { json: { items: [], unread_count: 0 } },
  };
}

async function applyTheme(page: Page, theme: 'light' | 'dark'): Promise<void> {
  await page.evaluate((t) => {
    document.documentElement.setAttribute('data-theme', t);
    localStorage.setItem('kb:theme', t);
  }, theme);
  await page.waitForTimeout(100);
}

test.describe('KANBA-220 Access Inspector, ACL Modal, Agent Kill Switch, Link Auditor & Purger QA Proofs', () => {
  test('01: Access Inspector Popover showing project role and Manage Access button', async ({ page }, testInfo) => {
    await page.unroute('**/api/v1/**');
    await mockApi(page, getCommonMocks());
    await page.goto('/__dev/drawer');
    await page.waitForSelector('[data-testid="link-kan-142"]', { state: 'visible' });

    // Open Access Inspector Popover via custom event on host
    await page.evaluate((objectId) => {
      window.dispatchEvent(
        new CustomEvent('kb:open-access-inspector', {
          detail: { objectId },
        }),
      );
    }, OBJECT_ID_142);

    const dialog = page.locator('div.access-inspector[role="dialog"]');
    await expect(dialog).toBeVisible();

    const manageBtn = dialog.locator('button.access-inspector__btn--secondary');
    await expect(manageBtn).toBeVisible();

    for (const theme of ['light', 'dark'] as const) {
      await applyTheme(page, theme);
      await annotatedScreenshot(page, testInfo, {
        name: `01-access-inspector-popover-${theme}`,
        annotations: [
          {
            selector: 'div.access-inspector[role="dialog"]',
            label: 'Effective Access Inspector showing object provenance and permissions',
          },
          {
            selector: 'button.access-inspector__btn--secondary',
            label: 'Manage Access button visible to callers with SHARE or ADMIN capability',
          },
          {
            selector: 'button.access-inspector__kill-switch-btn',
            label: 'Interactive Agent Kill Switch revoking active agent and OBO tokens',
          },
        ],
      });
    }
  });

  test('02: ManageAccessModal open with principal search, capabilities, and Agent Kill Switch', async ({ page }, testInfo) => {
    await page.unroute('**/api/v1/**');
    await mockApi(page, getCommonMocks());
    await page.goto('/__dev/drawer');
    await page.waitForSelector('[data-testid="link-kan-142"]', { state: 'visible' });

    // Open Access Inspector Popover via custom event on host
    await page.evaluate((objectId) => {
      window.dispatchEvent(
        new CustomEvent('kb:open-access-inspector', {
          detail: { objectId },
        }),
      );
    }, OBJECT_ID_142);

    const dialog = page.locator('div.access-inspector[role="dialog"]');
    await expect(dialog).toBeVisible();

    const manageBtn = dialog.locator('button.access-inspector__btn--secondary');
    await expect(manageBtn).toBeVisible();
    await manageBtn.click();

    await page.waitForSelector('[data-testid="manage-access-modal"]', { state: 'visible' });
    await expect(page.locator('[data-testid="principal-search-input"]')).toBeVisible();
    await expect(page.locator('[data-testid="active-acl-table"]')).toBeVisible();

    for (const theme of ['light', 'dark'] as const) {
      await applyTheme(page, theme);
      await annotatedScreenshot(page, testInfo, {
        name: `02-manage-access-modal-${theme}`,
        annotations: [
          {
            selector: '[data-testid="manage-access-modal"]',
            label: 'Manage Access modal with principal picker, capability matrix, and ACL entries',
          },
          {
            selector: '[data-testid="principal-search-input"]',
            label: 'Searchable principal picker filtering users, groups, and agents',
          },
          {
            selector: '[data-testid="active-acl-table"]',
            label: 'Active explicit ACL entries table with grant and revocation controls',
          },
        ],
      });
    }
  });

  test('03: Link Auditor Studio (/admin/link-auditor) showing 6 metric cards and flagged links table', async ({ page }, testInfo) => {
    await page.unroute('**/api/v1/**');
    await mockApi(page, getCommonMocks());
    await page.goto('/admin/link-auditor');
    await page.waitForSelector('[data-testid="link-auditor-studio"]', { state: 'visible' });
    await expect(page.locator('.link-auditor-metrics')).toBeVisible();
    await expect(page.locator('[data-testid="audit-links-table"]')).toBeVisible();

    for (const theme of ['light', 'dark'] as const) {
      await applyTheme(page, theme);
      await annotatedScreenshot(page, testInfo, {
        name: `03-link-auditor-studio-${theme}`,
        annotations: [
          {
            selector: '[data-testid="link-auditor-studio"]',
            label: 'Invalid Object Link Auditor & Purger studio gated on Workspace/Server Admin AAL2',
          },
          {
            selector: '.link-auditor-metrics',
            label: '6-class link integrity breakdown cards showing flagged counts by reason',
          },
          {
            selector: '[data-testid="audit-links-table"]',
            label: 'Keyset-paginated invalid links table with human source/target keys and inspect/purge actions',
          },
        ],
      });
    }
  });

  test('04: Inspect Link Drawer showing source, link, and target snapshots', async ({ page }, testInfo) => {
    await page.unroute('**/api/v1/**');
    await mockApi(page, getCommonMocks());
    await page.goto('/admin/link-auditor');
    await page.waitForSelector('[data-testid="link-auditor-studio"]', { state: 'visible' });

    // Open inspect drawer for aud-1
    await page.click('[data-testid="inspect-btn-aud-1"]');
    await page.waitForSelector('[data-testid="inspect-drawer"]', { state: 'visible' });
    await expect(page.locator('[data-testid="inspect-drawer"] h2')).toBeVisible();

    for (const theme of ['light', 'dark'] as const) {
      await applyTheme(page, theme);
      await annotatedScreenshot(page, testInfo, {
        name: `04-inspect-link-drawer-${theme}`,
        annotations: [
          {
            selector: '[data-testid="inspect-drawer"]',
            label: 'Inspect Link Drawer rendering link metadata, source snapshot, and target snapshot',
          },
          {
            selector: '[data-testid="drawer-purge-btn"]',
            label: '1-click purge action triggering audited justification modal',
          },
        ],
      });
    }
  });

  test('05: Audited Purge Modal with 10-char justification validation', async ({ page }, testInfo) => {
    await page.unroute('**/api/v1/**');
    await mockApi(page, getCommonMocks());
    await page.goto('/admin/link-auditor');
    await page.waitForSelector('[data-testid="link-auditor-studio"]', { state: 'visible' });

    // Open purge modal for aud-1
    await page.click('[data-testid="purge-single-btn-aud-1"]');
    await page.waitForSelector('[data-testid="purge-modal"]', { state: 'visible' });
    await expect(page.locator('[data-testid="purge-reason-input"]')).toBeVisible();

    // Fill valid justification
    await page.fill('[data-testid="purge-reason-input"]', 'Severing dangling target link after item deletion.');
    await expect(page.locator('[data-testid="confirm-purge-btn"]')).toBeEnabled();

    for (const theme of ['light', 'dark'] as const) {
      await applyTheme(page, theme);
      await annotatedScreenshot(page, testInfo, {
        name: `05-audited-purge-modal-${theme}`,
        annotations: [
          {
            selector: '[data-testid="purge-modal"]',
            label: 'Audited Link Purge Modal enforcing mandatory justification (>= 10 chars)',
          },
          {
            selector: '[data-testid="confirm-purge-btn"]',
            label: 'Confirm purge button requiring blast radius and justification verification',
          },
        ],
      });
    }
  });
});
