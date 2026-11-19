/**
 * Playwright Visual & QA Proof Verification for KAN-13.
 * Captures Desktop (1440x900) and Mobile (390x844) in Light and Dark themes.
 * Plain ASCII hyphens only. Zero em-dashes or en-dashes.
 */

import { test } from '../support/test';
import type { Page } from '@playwright/test';
import { mockApi, loadFixture } from '../support/mockApi';
import { resolve } from 'node:path';
import { mkdirSync } from 'node:fs';

const REPO_ROOT = resolve(import.meta.dirname, '../../../..');
const SCREENSHOT_DIR = resolve(REPO_ROOT, 'docs/qa/KAN-13/screenshots');

mkdirSync(SCREENSHOT_DIR, { recursive: true });

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

const rawProject = loadFixture<Record<string, unknown>>('project-kan');
const projectKan = {
  ...rawProject,
  identifier: 'KAN',
  capabilities: ['VIEW', 'COMMENT', 'EDIT', 'ADMIN'],
  is_project_admin: true,
};

const issueKan13 = {
  key: 'KAN-13',
  object_id: '11111111-1111-1111-1111-111111111113',
  project_key: 'KAN',
  project_name: 'Platform Core',
  summary: 'Render Mermaid outside Docs, fix fence newlines & ligatures, move Hide Nav',
  description_markdown: `### Architecture and Rendering Pipeline

Here is the architectural dataflow for Mermaid SVG rendering outside docs:

\`\`\`mermaid
flowchart TD
  UserRequest[User Request or Edit] --> SafeMarkdownPreview[SafeMarkdownPreview Ingestion]
  SafeMarkdownPreview --> FencedCheck{codeLang == 'mermaid'?}
  FencedCheck -->|Yes: Render SVG| MermaidBlockView[MermaidBlockView Live SVG]
  FencedCheck -->|No: Code Syntax| SyntaxPre[pre className="code-block"]
\`\`\`

All issue descriptions and comments now render live vector SVGs directly!`,
  priority: {
    slug: 'high',
    label: 'High',
    emoji: '⚡',
    sort_order: 2,
    sla_target: null,
  },
  state: {
    id: 'state-in-progress',
    name: 'In Progress',
    group: 'started',
  },
  etag: '"etag-kan-13"',
};

const commentsKan13 = {
  items: [
    {
      id: 'c1111111-1111-1111-1111-111111111113',
      issue_id: '11111111-1111-1111-1111-111111111113',
      parent_comment_id: null,
      author_id: '11111111-1111-4111-8111-111111111111',
      author: {
        id: '11111111-1111-4111-8111-111111111111',
        handle: 'architect',
        display_name: 'Security Architect',
      },
      body_markdown: `Verified live Mermaid rendering in issue comments:

\`\`\`mermaid
sequenceDiagram
  participant User
  participant Topbar
  participant Sidebar
  User->>Sidebar: Click PanelLeftClose
  Sidebar->>Topbar: State lifted to AppShell
  Topbar-->>User: Show PanelLeftOpen button
\`\`\`

The diagram renders with zero code leaks or ligatures.`,
      body_sha256: 'abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890',
      permalink: '/projects/KAN/issues/KAN-13#comment-c1111111-1111-1111-1111-111111111113',
      created_at: '2026-11-19T14:30:00Z',
      edited_at: null,
      deleted: false,
      etag: '"etag-comment-13"',
      reactions: [
        {
          emoji: '🚀',
          count: 2,
          reacted_by_me: true,
        },
      ],
      replies: [],
    },
  ],
};

function getBaseMocks() {
  return {
    'GET /api/v1/me': { json: mockUser },
    'GET /api/v1/auth/me': { json: mockUser },
    'GET /api/v1/users/me': { json: mockUser },
    'GET /api/v1/auth/session': {
      json: {
        authenticated: true,
        aal_level: 2,
        csrf_token: 'test-csrf-token-kan13',
        user: mockUser,
      },
    },
    'GET /api/v1/session/csrf': { json: { csrf_token: 'test-csrf-token-kan13' } },
    'GET /api/v1/setup/status': { json: { initialized: true, is_initialized: true, requires_setup: false } },
    'GET /api/v1/system/status': { json: loadFixture('system-status-prod') },
    'GET /api/v1/workspaces': {
      json: [
        {
          id: '01918a22-0000-7000-8000-000000000001',
          name: 'Primary Workspace',
          slug: 'kanban',
          is_current: true,
        },
      ],
    },
    'GET /api/v1/workspaces/current': {
      json: {
        id: '01918a22-0000-7000-8000-000000000001',
        name: 'Primary Workspace',
        slug: 'kanban',
        is_current: true,
      },
    },
    'GET /api/v1/projects': { json: [projectKan] },
    'GET /api/v1/projects/KAN': { json: projectKan },
    'GET /api/v1/projects/KAN/views': { json: [] },
    'GET /api/v1/projects/KAN/cycles': {
      json: [
        { id: 'cycle-1', name: 'Cycle 1', status: 'active' },
      ],
    },
    'GET /api/v1/projects/KAN/modules': {
      json: [
        { id: 'mod-1', name: 'Auth Core' },
        { id: 'mod-2', name: 'Kanban Board' },
      ],
    },
    'GET /api/v1/projects/KAN/states': {
      json: [
        { id: 'state-backlog', name: 'Backlog', group: 'backlog', sort_order: 1 },
        { id: 'state-todo', name: 'Todo', group: 'unstarted', sort_order: 2 },
        { id: 'state-in-progress', name: 'In Progress', group: 'started', sort_order: 3 },
        { id: 'state-in-review', name: 'In Review', group: 'started', sort_order: 4 },
        { id: 'state-done', name: 'Done', group: 'completed', sort_order: 5 },
        { id: 'state-cancelled', name: 'Cancelled', group: 'cancelled', sort_order: 6 },
      ],
    },
    'GET /api/v1/projects/KAN/issues': { json: [issueKan13] },
    'GET /api/v1/projects/KAN/priorities': {
      json: [
        { slug: 'urgent', label: 'Urgent', emoji: '🔥', sort_order: 1 },
        { slug: 'high', label: 'High', emoji: '⚡', sort_order: 2 },
        { slug: 'medium', label: 'Medium', emoji: '🔹', sort_order: 3 },
        { slug: 'low', label: 'Low', emoji: '💤', sort_order: 4 },
      ],
    },
    'GET /api/v1/projects/KAN/labels': {
      json: [
        { id: 'lbl-1', name: 'Database', color_hex: '#2563eb' },
        { id: 'lbl-2', name: 'Security', color_hex: '#dc2626' },
      ],
    },
    'GET /api/v1/projects/KAN/assignee-suggestions': {
      json: {
        items: [
          { id: 'u-1', handle: '@alice', display_name: 'Alice Cooper', type: 'USER' },
          { id: 'u-2', handle: '@adam', display_name: 'Adam Outler', type: 'USER' },
        ],
      },
    },
    'GET /api/v1/projects/KAN/custom-fields': { json: [] },
    'GET /api/v1/issues/:id': { json: issueKan13 },
    'GET /api/v1/issues/:id/subscription': { json: { items: [], subscribed: false } },
    'GET /api/v1/objects/:id/canonical-url': { json: { url: 'http://127.0.0.1:4183/projects/KAN/issues/KAN-13' } },
    'GET /api/v1/issues/:id/activity': { json: { items: [] } },
    'GET /api/v1/issues/:id/comments': { json: commentsKan13 },
    'GET /api/v1/issues/:id/subscribers': { json: [] },
    'GET /api/v1/objects/:id/access': { json: loadFixture('access-project-kan') },
    'GET /api/v1/notifications': { json: { items: [] } },
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

async function applyTheme(page: Page, theme: 'light' | 'dark'): Promise<void> {
  await page.evaluate((t: string) => {
    localStorage.setItem('kb.theme', t);
    document.documentElement.dataset.theme = t;
  }, theme);
  await page.waitForTimeout(150);
}

test.describe('KAN-13 Visual Verification & Proofs', () => {
  test.beforeEach(async ({ context }) => {
    await context.addCookies([
      {
        name: 'kb_csrf',
        value: 'test-csrf-token-kan13',
        domain: '127.0.0.1',
        path: '/',
      },
      {
        name: 'kb_session',
        value: 'mock_session_kan13',
        domain: '127.0.0.1',
        path: '/',
        httpOnly: true,
        sameSite: 'Lax',
      },
    ]);
  });

  test('01: Render Mermaid diagrams in issue surface and comments (Desktop & Mobile)', async ({ page }, testInfo) => {
    const projectName = testInfo.project.name;
    if (projectName !== 'desktop' && projectName !== 'mobile') return;

    await mockApi(page, getBaseMocks());
    await page.goto('/projects/KAN/issues/KAN-13');

    // Wait for the issue surface and mermaid SVGs to render
    await page.waitForSelector('.surface__description');
    await page.waitForTimeout(600);

    if (projectName === 'desktop') {
      // 1. Light Desktop
      await applyTheme(page, 'light');
      await page.screenshot({
        path: resolve(SCREENSHOT_DIR, '01-desktop-light-mermaid-issue.png'),
        fullPage: false,
      });

      // 2. Dark Desktop
      await applyTheme(page, 'dark');
      await page.screenshot({
        path: resolve(SCREENSHOT_DIR, '02-desktop-dark-mermaid-issue.png'),
        fullPage: false,
      });
    } else {
      // 3. Light Mobile
      await applyTheme(page, 'light');
      await page.screenshot({
        path: resolve(SCREENSHOT_DIR, '03-mobile-light-mermaid-issue.png'),
        fullPage: false,
      });

      // 4. Dark Mobile
      await applyTheme(page, 'dark');
      await page.screenshot({
        path: resolve(SCREENSHOT_DIR, '04-mobile-dark-mermaid-issue.png'),
        fullPage: false,
      });
    }
  });

  test('02: WorkspaceBadge monogram replacing [👍] (Desktop & Mobile)', async ({ page }, testInfo) => {
    const projectName = testInfo.project.name;
    if (projectName !== 'desktop' && projectName !== 'mobile') return;

    await mockApi(page, getBaseMocks());
    await page.goto('/projects/KAN/issues');

    if (projectName === 'desktop') {
      // Wait for sidebar and breadcrumb
      await page.waitForSelector('.kb-sidebar');
      await page.waitForSelector('.kb-breadcrumb');
      await page.waitForTimeout(300);

      // 5. Desktop Light WorkspaceBadge
      await applyTheme(page, 'light');
      await page.screenshot({
        path: resolve(SCREENSHOT_DIR, '05-desktop-light-workspace-badge.png'),
        fullPage: false,
      });

      // 6. Desktop Dark WorkspaceBadge
      await applyTheme(page, 'dark');
      await page.screenshot({
        path: resolve(SCREENSHOT_DIR, '06-desktop-dark-workspace-badge.png'),
        fullPage: false,
      });
    } else {
      // Mobile Topbar with WorkspaceBadge
      await page.waitForSelector('.kb-topbar');
      await page.waitForTimeout(300);

      // 11. Mobile Light WorkspaceBadge
      await applyTheme(page, 'light');
      await page.screenshot({
        path: resolve(SCREENSHOT_DIR, '11-mobile-light-workspace-badge.png'),
        fullPage: false,
      });

      // 12. Mobile Dark WorkspaceBadge
      await applyTheme(page, 'dark');
      await page.screenshot({
        path: resolve(SCREENSHOT_DIR, '12-mobile-dark-workspace-badge.png'),
        fullPage: false,
      });
    }
  });

  test('03: Sidebar Collapse in Workspace Header & Topbar Expand Button (Desktop)', async ({ page }, testInfo) => {
    const projectName = testInfo.project.name;
    if (projectName !== 'desktop') return;

    await mockApi(page, getBaseMocks());
    await page.goto('/projects/KAN/issues/KAN-13');
    await page.waitForSelector('.kb-sidebar');

    // 1. Expanded Sidebar state with PanelLeftClose in sidebar header
    await applyTheme(page, 'light');
    await page.screenshot({
      path: resolve(SCREENSHOT_DIR, '09-desktop-light-sidebar-expanded.png'),
      fullPage: false,
    });

    await applyTheme(page, 'dark');
    await page.screenshot({
      path: resolve(SCREENSHOT_DIR, '10-desktop-dark-sidebar-expanded.png'),
      fullPage: false,
    });

    // 2. Click collapse button in sidebar header
    const collapseBtn = page.getByRole('button', { name: 'Collapse navigation sidebar' });
    await collapseBtn.click();
    await page.waitForTimeout(300);

    // Collapsed Sidebar state with PanelLeftOpen in topbar
    await applyTheme(page, 'light');
    await page.screenshot({
      path: resolve(SCREENSHOT_DIR, '07-desktop-light-sidebar-collapsed.png'),
      fullPage: false,
    });

    await applyTheme(page, 'dark');
    await page.screenshot({
      path: resolve(SCREENSHOT_DIR, '08-desktop-dark-sidebar-collapsed.png'),
      fullPage: false,
    });
  });
});
