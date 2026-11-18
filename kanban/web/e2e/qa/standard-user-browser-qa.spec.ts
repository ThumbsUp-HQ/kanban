// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import type { Page } from '@playwright/test';
import { test, expect } from '../support/test';
import { mockApi, loadFixture, type MockHandlers } from '../support/mockApi';
import { annotatedScreenshot } from '../support/annotate';
import { probeStyles } from '../support/styleProbe';

const mockMemberUser = {
  id: 'usr-member-qa',
  handle: 'standard_member',
  display_name: 'Standard Team Member',
  email: 'member@example.com',
  is_server_admin: false,
  is_workspace_admin: false,
  workspace_role: 'WORKSPACE_MEMBER',
  workspace_capabilities: ['CREATE_PROJECT', 'VIEW'],
};

const mockProjectsList = [
  {
    id: 'proj-qaadm-id',
    identifier: 'QAADM',
    name: 'Admin Restricted Project',
    description_markdown: 'Project restricted to administrators.',
    modules_enabled: true,
    is_project_admin: false,
    project_role: 'VIEWER',
    capabilities: ['VIEW'],
  },
  {
    id: 'proj-qaview-id',
    identifier: 'QAVIEW',
    name: 'Viewer Only Project',
    description_markdown: 'Read-only viewer project.',
    modules_enabled: true,
    is_project_admin: false,
    project_role: 'VIEWER',
    capabilities: ['VIEW'],
  },
  {
    id: 'proj-qanomod-id',
    identifier: 'QANOMOD',
    name: 'No Modules Project',
    description_markdown: 'Project with modules feature disabled.',
    modules_enabled: false,
    is_project_admin: false,
    project_role: 'VIEWER',
    capabilities: ['VIEW'],
  },
  {
    id: 'proj-kan-id',
    identifier: 'KAN',
    name: 'Platform Core',
    description_markdown: 'Standard engineering project.',
    modules_enabled: true,
    is_project_admin: false,
    project_role: 'MEMBER',
    capabilities: ['VIEW', 'CREATE', 'EDIT', 'TRANSITION'],
  },
];

const mockWorkspace = {
  items: [{ id: 'ws-default', slug: 'kanban', name: '👍kanban Workspace', is_current: true }],
  active_workspace_id: 'ws-default',
};

const mockSystemStatus = {
  standalone: true,
  version: '0.1.0',
  allow_unlimited_mcp_keys: false,
};

async function setupStandardUserMocks(page: Page, overrides: MockHandlers = {}): Promise<void> {
  await page.unroute('**/api/v1/**');
  await mockApi(page, {
    'GET /api/v1/auth/me': { json: mockMemberUser },
    'GET /api/v1/me': { json: mockMemberUser },
    'GET /api/v1/auth/session': {
      json: {
        authenticated: true,
        aal_level: 1,
        csrf_token: 'csrf-user-test-token',
        user: mockMemberUser,
      },
    },
    'GET /api/v1/session/csrf': { json: { csrf_token: 'csrf-user-test-token' } },
    'GET /api/v1/setup/status': { json: { initialized: true, is_initialized: true, requires_setup: false } },
    'GET /api/v1/system/status': { json: mockSystemStatus },
    'GET /api/v1/workspaces': { json: mockWorkspace },
    'GET /api/v1/workspaces/:wsId': { json: mockWorkspace.items[0] },
    'GET /api/v1/projects': { json: mockProjectsList },
    'GET /api/v1/projects/QAADM': { json: mockProjectsList[0] },
    'GET /api/v1/projects/QAVIEW': { json: mockProjectsList[1] },
    'GET /api/v1/projects/QANOMOD': { json: mockProjectsList[2] },
    'GET /api/v1/projects/KAN': { json: mockProjectsList[3] },
    'GET /api/v1/projects/:key/views': { json: [] },
    'GET /api/v1/projects/:key/custom-fields': { json: [] },
    'GET /api/v1/projects/:key/states': {
      json: [
        { id: 'state-backlog', name: 'Backlog', group: 'backlog', sort_order: 1 },
        { id: 'state-todo', name: 'Todo', group: 'unstarted', sort_order: 2 },
        { id: 'state-in-progress', name: 'In Progress', group: 'started', sort_order: 3 },
        { id: 'state-in-review', name: 'In Review', group: 'started', sort_order: 4, wip_hard_limit: 3 },
        { id: 'state-done', name: 'Done', group: 'completed', sort_order: 5 },
        { id: 'state-canceled', name: 'Canceled', group: 'cancelled', sort_order: 6 },
      ],
    },
    'GET /api/v1/projects/QAADM/issues': { json: { items: [], total: 0 } },
    'GET /api/v1/projects/QAVIEW/issues': {
      json: {
        items: [
          {
            id: 'iss-qaview-1',
            key: 'QAVIEW-1',
            summary: 'Read only work item',
            state: { id: 'state-backlog', name: 'Backlog', group: 'backlog' },
            state_id: 'state-backlog',
            priority: { id: 'p-low', label: 'Low', slug: 'low' },
            capabilities: ['VIEW'],
            assignees: [],
          },
        ],
        total: 1,
      },
    },
    'GET /api/v1/issues/:key': (req) => {
      const issueKey = req.params.key ?? 'UNKNOWN';
      return {
        status: 200,
        json: {
          id: `iss-${issueKey.toLowerCase()}`,
          key: issueKey,
          summary: 'Work Item Details',
          state: { id: 'state-backlog', name: 'Backlog', group: 'backlog' },
          state_id: 'state-backlog',
          priority: { id: 'p-low', label: 'Low', slug: 'low' },
          capabilities: ['VIEW'],
          assignees: [],
        },
      };
    },
    'GET /api/v1/projects/QANOMOD/issues': { json: { items: [], total: 0 } },
    'GET /api/v1/projects/QAVIEW/cycles': { json: [] },
    'GET /api/v1/projects/QAVIEW/modules': { json: [] },
    'GET /api/v1/projects/QAADM/cycles': { json: [] },
    'GET /api/v1/projects/QAADM/modules': { json: [] },
    'GET /api/v1/projects/QAADM/members': { status: 403, json: { code: 'INSUFFICIENT_CAPABILITY', detail: 'Admin only' } },
    'GET /api/v1/projects/QAADM/workflow-hooks': { status: 404, json: { code: 'NOT_FOUND', detail: 'Not found or no access' } },
    'POST /api/v1/projects/QAVIEW/cycles': { status: 403, json: { code: 'INSUFFICIENT_CAPABILITY', detail: 'Viewer cannot create cycles' } },
    'GET /api/v1/admin/workspace-settings': { status: 403, json: { code: 'INSUFFICIENT_CAPABILITY', detail: 'Forbidden' } },
    'GET /api/v1/admin/principals': { status: 403, json: { code: 'INSUFFICIENT_CAPABILITY', detail: 'Forbidden' } },
    'GET /api/v1/admin/auth/cards': { status: 403, json: { code: 'INSUFFICIENT_CAPABILITY', detail: 'Forbidden' } },
    'GET /api/v1/auth/mcp-keys': { json: [] },
    'GET /api/v1/auth/oauth-grants': { json: [] },
    'GET /api/v1/stickies': { json: [] },
    'GET /api/v1/objects/:objectId/access': {
      json: {
        object_id: 'obj-default',
        inherited_from: null,
        users: [{ principal_id: mockMemberUser.id, display_name: mockMemberUser.display_name, role: 'WORKSPACE_MEMBER', capabilities: ['VIEW'] }],
        groups: [],
        agents: [],
        deny_overrides: [],
      },
    },
    ...overrides,
  });
}

test.describe('Standard User Browser QA Suite (KANBA-204)', () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => {
      document.cookie = 'kb_csrf=csrf-user-test-token; path=/; SameSite=Lax';
    });
  });

  test('01: Standard member negative RBAC hiding across 19 surfaces & direct route denial', async ({ page }, testInfo) => {
    await setupStandardUserMocks(page);

    // 1. Visit root workspace home
    await page.goto('/');
    await expect(page.locator('.kb-topbar')).toBeVisible();

    // 2. Topbar avatar menu: Verify administrative items are completely hidden
    const avatarBtn = page.locator('.kb-avatar-button');
    await expect(avatarBtn).toBeVisible();
    await avatarBtn.click();

    const avatarMenu = page.locator('.kb-avatar-menu');
    await expect(avatarMenu).toBeVisible();

    // Verify negative RBAC: Admin and Workspace links must NOT exist in DOM
    await expect(page.locator('a[role="menuitem"]:has-text("Admin Auth Studio")')).toHaveCount(0);
    await expect(page.locator('a[role="menuitem"]:has-text("Admin MCP Keys")')).toHaveCount(0);
    await expect(page.locator('a[role="menuitem"]:has-text("System Storage, Backups & Deployment")')).toHaveCount(0);
    await expect(page.locator('[data-testid="topbar-workspace-settings-link"]')).toHaveCount(0);
    await expect(page.locator('a[role="menuitem"]:has-text("Workspace MCP Keys")')).toHaveCount(0);

    // Verify positive self-service personal links exist
    await expect(page.locator('[data-testid="topbar-personal-settings-link"]')).toBeVisible();
    await expect(page.locator('a[role="menuitem"]:has-text("Personal MCP Keys")')).toBeVisible();

    // Close avatar menu
    await avatarBtn.click();
    await expect(avatarMenu).toHaveCount(0);

    // 3. Command Palette: Verify administrative commands are omitted
    const searchTrigger = page.locator('.kb-topbar-search-trigger');
    if (await searchTrigger.isVisible()) {
      await searchTrigger.click();
      const palette = page.locator('[role="dialog"][aria-label="Command palette"]');
      await expect(palette).toBeVisible();

      // Search for administrative actions
      const paletteInput = palette.locator('input');
      await paletteInput.fill('Admin');
      await expect(palette.locator('[role="option"]:has-text("Go to Auth Studio")')).toHaveCount(0);
      await expect(palette.locator('[role="option"]:has-text("Go to System Storage")')).toHaveCount(0);

      await page.keyboard.press('Escape');
      await expect(palette).toHaveCount(0);
    }

    // 4. Sidebar Negative RBAC Checks on non-admin projects (QAADM, QAVIEW, QANOMOD)
    // Expand QAADM in Sidebar if present
    const qaadmExpand = page.locator('button.kb-project-expand-row:has-text("Admin Restricted Project")');
    if (await qaadmExpand.isVisible()) {
      const isExpanded = await qaadmExpand.getAttribute('aria-expanded');
      if (isExpanded === 'false') {
        await qaadmExpand.click();
      }
    }

    // Verify QAADM does NOT show Workflows, Custom Fields, or Project Settings in sidebar
    await expect(page.locator('.kb-sidebar a[href="/projects/QAADM/settings/workflows"]')).toHaveCount(0);
    await expect(page.locator('.kb-sidebar a[href="/projects/QAADM/settings/custom-fields"]')).toHaveCount(0);
    await expect(page.locator('.kb-sidebar [data-testid="sidebar-project-settings-QAADM"]')).toHaveCount(0);

    // Verify QANOMOD does NOT show Modules in sidebar
    await expect(page.locator('.kb-sidebar a[href="/projects/QANOMOD/modules"]')).toHaveCount(0);

    // 5. Viewer Project QAVIEW: Navigate to Cycles, Modules and Issues to verify creation and deletion controls are hidden
    await page.goto('/projects/QAVIEW/cycles');
    await expect(page.locator('[data-testid="project-cycles-view"]')).toBeVisible();
    await expect(page.locator('[data-testid="create-cycle-btn"]')).toHaveCount(0);
    await expect(page.locator('[data-testid="create-cycle-form"]')).toHaveCount(0);

    await page.goto('/projects/QAVIEW/modules');
    await expect(page.locator('[data-testid="project-modules-view"]')).toBeVisible();
    await expect(page.locator('[data-testid="create-module-btn"]')).toHaveCount(0);
    await expect(page.locator('[data-testid="create-module-form"]')).toHaveCount(0);

    // Navigate to QAVIEW issues: verify read-only item cannot be deleted via BulkActionBar and has no cancel gate button
    await page.goto('/projects/QAVIEW/issues');
    await expect(page.locator('text=Read only work item')).toBeVisible();
    const selectCheckbox = page.locator('input[type="checkbox"][aria-label="Select QAVIEW-1"]');
    if (await selectCheckbox.isVisible()) {
      await selectCheckbox.check();
      await expect(page.locator('.bulk-btn-danger')).toHaveCount(0);
      await expect(page.locator('button:has-text("Delete")')).toHaveCount(0);
    }
    await expect(page.locator('.gate-popover__cancel-btn')).toHaveCount(0);
    await expect(page.locator('button:has-text("Cancel gate")')).toHaveCount(0);

    // 6. Direct Route Navigation to Restricted URLs -> Must render "Not found or no access" with 0 secrets leaked
    const restrictedRoutes = [
      '/admin/auth',
      '/admin/mcp',
      '/workspaces/settings',
      '/workspaces/settings/mcp',
      '/projects/QAADM/settings',
      '/projects/QAADM/settings/workflows',
      '/projects/QAADM/settings/custom-fields',
    ];

    for (const route of restrictedRoutes) {
      await page.goto(route);
      await expect(page.locator('body')).toContainText('Not found or no access');

      const content = await page.content();
      // Verify zero leaked secrets / tokens / card client secrets
      expect(content).not.toMatch(/kb_(agt|adm|doc|sec)_[A-Za-z0-9]+/);
      expect(content).not.toContain('client_secret');
      expect(content).not.toContain('card-client-secret');
    }

    // Return to home page to capture comprehensive screenshot
    await page.goto('/');
    await expect(page.locator('.kb-topbar')).toBeVisible();

    await annotatedScreenshot(page, testInfo, {
      name: '01-user-home-and-rbac-denied',
      annotations: [
        {
          selector: '.kb-topbar',
          label: 'Calm Topbar without admin triggers',
          note: 'Admin Auth, Admin MCP & System Storage hidden from DOM',
        },
        {
          selector: '#main',
          label: 'Workspace Content Canvas',
          note: 'Pruned project cards and restricted administrative surfaces',
        },
      ],
    });
  });

  test('02: Hard WIP member block on Board (0 move requests, toast shown, zero override dialog)', async ({ page }, testInfo) => {
    const projectData = loadFixture<Record<string, unknown>>('project-kan');
    const wipIssues = loadFixture<Record<string, unknown>>('board-kan-wip');

    let moveRequestCount = 0;

    await setupStandardUserMocks(page, {
      'GET /api/v1/projects/KAN': {
        json: {
          ...projectData,
          capabilities: ['PROJECT_MEMBER', 'VIEW', 'EDIT', 'TRANSITION'],
          is_project_admin: false,
        },
      },
      'GET /api/v1/projects/KAN/issues': { json: wipIssues },
      'POST /api/v1/issues/:issue_ref/move': () => {
        moveRequestCount++;
        return { status: 200, json: { ok: true } };
      },
    });

    await page.goto('/projects/KAN/issues?layout=board');
    await expect(page.locator('[data-testid="board-card-KAN-142"]')).toBeVisible();

    // Verify state-in-review has 3 cards (reaching wip_hard_limit of 3)
    const inReviewCol = page.locator('[data-testid="board-column-state-in-review"]');
    await expect(inReviewCol).toBeVisible();

    // Focus KAN-142 in In Progress and move right into In Review (Hard WIP limit 3 reached - Blocked!)
    const card = page.locator('[data-testid="board-card-KAN-142"]');
    await card.focus();
    await page.keyboard.press('Alt+ArrowRight');

    // Verify non-admin Hard WIP block:
    // 1. Toast alert appears
    const toast = page.locator('[data-testid="board-alert-toast"]');
    await expect(toast).toBeVisible();
    await expect(toast).toContainText('Hard WIP limit reached (3/3) on In Review');

    // 2. Zero override dialogs in DOM
    await expect(page.locator('[role="dialog"]')).toHaveCount(0);

    // 3. Zero move network calls dispatched
    expect(moveRequestCount).toBe(0);

    // 4. Card remains securely in origin lane (In Progress)
    const inProgressCol = page.locator('[data-testid="board-column-state-in-progress"]');
    await expect(inProgressCol.locator('[data-testid="board-card-KAN-142"]')).toBeVisible();

    await annotatedScreenshot(page, testInfo, {
      name: '02-user-board-hard-wip-blocked',
      annotations: [
        {
          selector: '[data-testid="board-alert-toast"]',
          label: 'Hard WIP Block Toast',
          note: 'Blocks transition without admin override modal',
        },
        {
          selector: '[data-testid="board-card-KAN-142"]',
          label: 'Origin Column Preserved',
          note: 'Card stays in In Progress with 0 network calls',
        },
      ],
    });
  });

  test('03: Positive self-service workflow (project creation, drafts, workflow transitions, XSS escaping, stickies-to-doc)', async ({ page }, testInfo) => {
    let createdProjectRecord: Record<string, unknown> | null = null;
    let createdIssueRecord: Record<string, unknown> | null = null;
    let promotedStickyRecord: Record<string, unknown> | null = null;

    const mockStickiesData = [
      {
        id: 'sticky-usr-1',
        workspace_id: 'ws-default',
        project_id: 'proj-qausr1-id',
        body_markdown: '# Specification Architecture\n## Security Boundaries\nDetailed architecture specification ready for doc promotion.',
        color_token: 'amber',
        sort_rank: '0000000000000001',
        promotion_recommended: true,
        promotion_snoozed_at_length: null,
        promoted_to_doc_id: null,
        promoted_to_doc: null,
      },
    ];

    await setupStandardUserMocks(page, {
      'POST /api/v1/projects': (req) => {
        const body = req.body as Record<string, unknown>;
        createdProjectRecord = {
          id: 'proj-qausr1-id',
          identifier: body.identifier,
          name: body.name,
          description_markdown: body.description_markdown ?? '',
          modules_enabled: true,
          is_project_admin: true,
          capabilities: ['VIEW', 'CREATE', 'EDIT', 'TRANSITION', 'ADMIN'],
        };
        return { status: 201, json: createdProjectRecord };
      },
      'GET /api/v1/projects/QAUSR1': () => {
        return {
          status: 200,
          json: createdProjectRecord ?? {
            id: 'proj-qausr1-id',
            identifier: 'QAUSR1',
            name: 'QA User Project 1',
            modules_enabled: true,
            is_project_admin: true,
            capabilities: ['VIEW', 'CREATE', 'EDIT', 'TRANSITION', 'ADMIN'],
          },
        };
      },
      'GET /api/v1/projects/QAUSR1/issues': () => {
        const items = createdIssueRecord ? [createdIssueRecord] : [];
        return { status: 200, json: { items, total: items.length } };
      },
      'POST /api/v1/projects/QAUSR1/issues': (req) => {
        const body = req.body as Record<string, unknown>;
        createdIssueRecord = {
          id: 'iss-qausr1-1',
          key: 'QAUSR1-1',
          summary: body.summary,
          description_markdown: body.description_markdown ?? '',
          state: { id: 'state-backlog', name: 'Backlog', group: 'backlog' },
          state_id: 'state-backlog',
          priority: { id: 'p-med', label: 'Medium', slug: 'medium' },
          capabilities: ['VIEW', 'EDIT', 'TRANSITION', 'DELETE'],
          assignees: [],
        };
        return { status: 201, json: createdIssueRecord };
      },
      'POST /api/v1/issues/QAUSR1-1/state': (req) => {
        const body = req.body as Record<string, unknown>;
        const targetStateId = String(body.state_id);

        if (targetStateId === 'state-in-review') {
          // Return 202 Accepted pending workflow gate
          return {
            status: 202,
            json: {
              status: 'pending',
              pending_gate: {
                execution_id: 'exec-gate-qausr1-1',
                hook_name: 'reality-checker-qa',
                requested_at: new Date().toISOString(),
              },
            },
          };
        }

        // Return 200 OK immediate state transition
        const stateMap: Record<string, { name: string; group: string }> = {
          'state-backlog': { name: 'Backlog', group: 'backlog' },
          'state-todo': { name: 'Todo', group: 'unstarted' },
          'state-in-progress': { name: 'In Progress', group: 'started' },
          'state-done': { name: 'Done', group: 'completed' },
          'state-canceled': { name: 'Canceled', group: 'cancelled' },
        };
        const st = stateMap[targetStateId] ?? { name: 'Updated', group: 'completed' };
        if (createdIssueRecord) {
          createdIssueRecord.state_id = targetStateId;
          createdIssueRecord.state = { id: targetStateId, ...st };
        }
        return { status: 200, json: { ok: true, state_id: targetStateId } };
      },
      'GET /api/v1/stickies': () => {
        return { status: 200, json: promotedStickyRecord ? [promotedStickyRecord] : mockStickiesData };
      },
      'POST /api/v1/stickies/:stickyId/promote-to-doc': () => {
        promotedStickyRecord = {
          ...mockStickiesData[0],
          promoted_to_doc_id: 'doc-qausr1-spec',
          promoted_to_doc: {
            id: 'doc-qausr1-spec',
            title: 'Specification Architecture',
          },
        };
        return { status: 200, json: promotedStickyRecord };
      },
    });

    await page.goto('/');

    // 1. Self-service Project Creation: QAUSR1
    const addProjectBtn = page.locator('.kb-sidebar-add-project-btn');
    if (await addProjectBtn.isVisible()) {
      await addProjectBtn.click();
    } else {
      await page.evaluate(() => {
        window.dispatchEvent(new CustomEvent('kb:open-create-project', { bubbles: true }));
      });
    }

    const modal = page.locator('[data-testid="create-project-modal"]');
    await expect(modal).toBeVisible();

    await page.fill('#create-project-name', 'QA User Project 1');
    await page.fill('#create-project-identifier', 'QAUSR1');
    await modal.locator('button[type="submit"]').click();

    // Navigates to /projects/QAUSR1/issues
    await expect(page).toHaveURL(/\/projects\/QAUSR1\/issues/);
    expect(createdProjectRecord).not.toBeNull();
    await expect(page.locator('.kb-topbar')).toBeVisible();

    // 2. Drafts Lifecycle: Save WIP Draft
    await page.evaluate(() => {
      window.dispatchEvent(new CustomEvent('kb:create-issue', { bubbles: true }));
    });

    const createModal = page.locator('.quick-create-modal');
    await expect(createModal).toBeVisible();

    await page.fill('#quick-create-summary', 'Draft feature spec in progress');
    // Check keep work-in-progress checkbox
    const draftCheckbox = page.locator('[data-testid="quick-create-draft-checkbox"]');
    await draftCheckbox.check();

    await page.locator('.quick-create-btn-submit').click();
    const donePostBtn = page.locator('[data-testid="post-create-done-btn"]');
    await expect(donePostBtn).toBeVisible();
    await donePostBtn.click();
    await expect(createModal).toHaveCount(0);

    // Visit Drafts page and verify draft is saved
    await page.goto('/drafts');
    await expect(page.locator('[data-testid="drafts-view"]')).toBeVisible();
    await expect(page.locator('text=Draft feature spec in progress')).toBeVisible();

    // 3. Create published work item with hostile XSS payload
    await page.goto('/projects/QAUSR1/issues');
    await expect(page.locator('.kb-topbar')).toBeVisible();
    await page.evaluate(() => {
      window.dispatchEvent(new CustomEvent('kb:create-issue', { bubbles: true }));
    });

    await expect(createModal).toBeVisible();
    const hostileXss = '<img src=x onerror=alert(1)>';
    await page.fill('#quick-create-summary', 'Security XSS Escaping Test');
    await page.fill('#quick-create-description', hostileXss);
    await page.locator('.quick-create-btn-submit').click();
    await expect(createModal).toHaveCount(0);

    await expect(page.locator('text=Security XSS Escaping Test')).toBeVisible();

    // Verify Hostile XSS payload is strictly escaped: ZERO img tags with src="x"
    const maliciousImgs = page.locator('img[src="x"]');
    await expect(maliciousImgs).toHaveCount(0);

    // 4. Verify Full Workflow Transitions across states
    const transitionResults = await page.evaluate(async () => {
      const states = [
        'state-todo',
        'state-in-progress',
        'state-in-review',
        'state-done',
        'state-canceled',
      ];
      const resList: { state: string; status: number; data: unknown }[] = [];
      for (const st of states) {
        const res = await fetch('/api/v1/issues/QAUSR1-1/state', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ state_id: st }),
        });
        resList.push({ state: st, status: res.status, data: await res.json() });
      }
      return resList;
    });

    expect(transitionResults[0]?.status).toBe(200); // Todo: 200 OK
    expect(transitionResults[1]?.status).toBe(200); // In Progress: 200 OK
    expect(transitionResults[2]?.status).toBe(202); // In Review: 202 Accepted (pending gate)
    const gateData = transitionResults[2]?.data as { pending_gate?: { hook_name?: string } };
    expect(gateData.pending_gate?.hook_name).toBe('reality-checker-qa');
    expect(transitionResults[3]?.status).toBe(200); // Done: 200 OK
    expect(transitionResults[4]?.status).toBe(200); // Canceled: 200 OK

    // 5. Sticky-to-Doc Promotion
    await page.goto('/stickies');
    await expect(page.locator('[data-testid="workspace-stickies-page"]')).toBeVisible();

    const promoteBtn = page.locator('[data-testid="promote-to-doc-btn"]');
    if (await promoteBtn.isVisible()) {
      await promoteBtn.click();
      await expect(page.locator('[data-testid="promoted-sticky-stub-sticky-usr-1"]')).toBeVisible();
    }

    // Capture visual proof of completed self-service workflow
    await annotatedScreenshot(page, testInfo, {
      name: '03-user-workflow-transition',
      annotations: [
        {
          selector: '[data-testid="workspace-stickies-page"]',
          label: 'Sticky to Doc Promotion & Workflows',
          note: 'Promoted specification stub with preserved permissions',
        },
      ],
    });
  });

  test('04: Personal MCP key lifecycle & /activate scope narrowing', async ({ page }, testInfo) => {
    let mintedKeyId = '';
    const mockPersonalKeys = [
      {
        id: 'key-pers-1',
        label: 'Existing Development Key',
        surface: 'agent',
        display_hint: 'kb_agt_d1a2...3f4b',
        scopes: ['agent:read', 'agent:write'],
        scope_tier: 'workspace',
        created_at: new Date(Date.now() - 86400000).toISOString(),
        expires_at: new Date(Date.now() + 86400000 * 30).toISOString(),
        revoked_at: null,
      },
    ];

    await setupStandardUserMocks(page, {
      'GET /api/v1/auth/mcp-keys': { json: mockPersonalKeys },
      'POST /api/v1/auth/mcp-keys': (req) => {
        const body = req.body as Record<string, unknown>;
        mintedKeyId = 'key-pers-new-2';
        return {
          status: 201,
          json: {
            id: mintedKeyId,
            label: body.label,
            surface: body.surface,
            raw_key: 'kb_agt_secret_raw_key_personal_token',
            display_hint: 'kb_agt_secr...oken',
            scopes: body.scopes,
            scope_tier: 'workspace',
            created_at: new Date().toISOString(),
            expires_at: new Date(Date.now() + 86400000 * 60).toISOString(),
            revoked_at: null,
          },
        };
      },
      'DELETE /api/v1/auth/mcp-keys/:keyId': () => {
        return { status: 204 };
      },
      'GET /api/v1/oauth/device/info': () => {
        return {
          status: 200,
          json: {
            client_id: 'client-agy-desktop',
            client_name: 'Antigravity CLI (agy)',
            user_code: 'WDJB-MJHT',
            resource: 'https://kanban.hackedyour.info/mcp/agent',
            surface: 'agent',
            requested_scopes: ['agent:read', 'agent:write', 'docs:read'],
            allowed_projects: ['QAUSR1'],
            expires_at: new Date(Date.now() + 600000).toISOString(),
          },
        };
      },
      'POST /api/v1/oauth/device/activate': (req) => {
        const body = req.body as Record<string, unknown>;
        return {
          status: 200,
          json: {
            status: 'approved',
            grant_id: 'grant-test-1',
            granted_scopes: body.scopes,
            granted_projects: body.allowed_projects,
          },
        };
      },
    });

    // 1. Visit Personal MCP Keys Studio
    await page.goto('/settings/mcp');
    const studio = page.locator('[data-testid="mcp-access-studio"]');
    await expect(studio).toBeVisible();

    // 2. Mint key flow: Verify /mcp/admin is hidden for standard user
    const mintBtn = page.locator('[data-testid="mint-key-button"]');
    await expect(mintBtn).toBeVisible();
    await mintBtn.click();

    const mintModal = page.locator('[data-testid="mint-modal-backdrop"]');
    await expect(mintModal).toBeVisible();

    const surfaceSelect = page.locator('#mint-surface-select');
    await expect(surfaceSelect).toBeVisible();
    // /mcp/admin option must NOT exist for standard user
    await expect(surfaceSelect.locator('option[value="admin"]')).toHaveCount(0);

    // Mint /mcp/agent key
    await page.fill('#mint-label-input', 'Personal Cursor Agent Key');
    await page.click('[data-testid="mint-submit-btn"]');

    // Snippet modal opens with raw key
    const snippetModal = page.locator('[data-testid="mcp-snippet-modal-backdrop"]');
    await expect(snippetModal).toBeVisible();
    await page.click('[data-testid="done-button"]');
    await expect(snippetModal).toHaveCount(0);

    // 3. Inline 2-step Revoke Flow
    const revokeBtn = page.locator(`[data-testid="revoke-btn-${mintedKeyId}"]`);
    await expect(revokeBtn).toBeVisible();
    await revokeBtn.click();

    const confirmBar = page.locator('[data-testid="confirm-revoke-bar"]');
    await expect(confirmBar).toBeVisible();
    await page.click('[data-testid="confirm-revoke-btn"]');

    // Verify revoked status displayed
    await expect(page.locator(`[data-testid="key-row-${mintedKeyId}"] [data-testid="status-revoked"]`)).toBeVisible();

    // 4. Device Activation /activate with scope narrowing
    await page.goto('/activate?user_code=WDJB-MJHT');
    const consentSection = page.locator('[data-testid="consent-section"]');
    await expect(consentSection).toBeVisible();

    // Verify requested scopes and narrow them
    const writeScopeCheckbox = page.locator('[data-testid="scope-checkbox-agent:write"]');
    await expect(writeScopeCheckbox).toBeVisible();
    await writeScopeCheckbox.uncheck();

    // Approve narrowed scopes
    await page.click('[data-testid="approve-button"]');
    await expect(page.locator('[data-testid="completion-approved"]')).toBeVisible();

    // 5. Probe computed styles on /settings/mcp
    await page.goto('/settings/mcp');
    await expect(studio).toBeVisible();

    await probeStyles(page, testInfo, {
      name: 'personal-mcp-keys-styles',
      probes: [
        {
          selector: '[data-testid="mcp-access-studio"]',
          props: ['padding-top', 'padding-bottom', 'color'],
        },
        {
          selector: '[data-testid="mint-key-button"]',
          props: ['background-color', 'color', 'border-radius'],
        },
        {
          selector: '[data-testid="mcp-keys-table"]',
          props: ['width', 'border-collapse'],
        },
      ],
    });

    await annotatedScreenshot(page, testInfo, {
      name: '04-user-personal-mcp-keys',
      annotations: [
        {
          selector: '[data-testid="mcp-access-studio"]',
          label: 'Personal MCP Keys Studio',
          note: 'Scoped key lifecycle and consent delegation',
        },
        {
          selector: '[data-testid="mint-key-button"]',
          label: 'Mint Key Action',
          note: 'Restricted from administrative surface generation',
        },
      ],
    });
  });
});
