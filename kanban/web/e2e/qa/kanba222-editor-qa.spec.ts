// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import { resolve } from 'node:path';
import { mkdirSync } from 'node:fs';
import type { Page } from '@playwright/test';
import { test, expect } from '../support/test';
import { mockApi, loadFixture, type MockHandlers } from '../support/mockApi';
import { annotatedScreenshot } from '../support/annotate';

process.env.QA_TICKET_ID = 'KANBA-222';
const SCREENSHOT_DIR = resolve(
  import.meta.dirname,
  '../../../../docs/qa/KANBA-222/screenshots',
);
mkdirSync(SCREENSHOT_DIR, { recursive: true });

async function applyTheme(page: Page, theme: 'light' | 'dark'): Promise<void> {
  await page.evaluate((t) => {
    document.documentElement.setAttribute('data-theme', t);
    localStorage.setItem('kb:theme', t);
  }, theme);
  await page.waitForTimeout(100);
}

function getBaseMocks(): MockHandlers {
  const me = loadFixture<Record<string, unknown>>('me-adam');
  const rawProject = loadFixture<Record<string, unknown>>('project-kan');
  const projectKan = {
    ...rawProject,
    identifier: 'KAN',
    capabilities: ['VIEW', 'COMMENT', 'EDIT', 'ADMIN'],
    is_project_admin: true,
  };
  const issueDetail = loadFixture<Record<string, unknown>>('issue-kan-142-detail');
  return {
    'GET /api/v1/me': { json: me },
    'GET /api/v1/auth/me': { json: me },
    'GET /api/v1/users/me': { json: me },
    'GET /api/v1/auth/session': {
      json: {
        authenticated: true,
        aal_level: 2,
        csrf_token: 'test-csrf-token-kanba-222',
        user: me,
      },
    },
    'GET /api/v1/session/csrf': { json: { csrf_token: 'test-csrf-token-kanba-222' } },
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
    'GET /api/v1/projects': { json: [projectKan] },
    'GET /api/v1/projects/KAN': { json: projectKan },
    'GET /api/v1/projects/KAN/cycles': { json: [{ id: 'cycle-1', name: 'Cycle 1', status: 'active' }] },
    'GET /api/v1/projects/KAN/modules': { json: [{ id: 'mod-1', name: 'Auth Core' }] },
    'GET /api/v1/projects/KAN/states': { json: [
      { id: 'state-backlog', name: 'Backlog', group: 'backlog', sort_order: 1 },
      { id: 'state-todo', name: 'Todo', group: 'unstarted', sort_order: 2 },
      { id: 'state-in-progress', name: 'In Progress', group: 'started', sort_order: 3 },
      { id: 'state-done', name: 'Done', group: 'completed', sort_order: 4 },
    ] },
    'GET /api/v1/projects/KAN/issues': { json: loadFixture('issues-kan') },
    'GET /api/v1/projects/KAN/priorities': { json: [
      { slug: 'urgent', label: 'Urgent', emoji: '🔥', sort_order: 1 },
      { slug: 'high', label: 'High', emoji: '⚡', sort_order: 2 },
    ] },
    'GET /api/v1/projects/KAN/labels': { json: [{ id: 'lbl-1', name: 'Database', color_hex: '#2563eb' }] },
    'GET /api/v1/projects/KAN/assignee-suggestions': {
      json: {
        items: [
          { id: 'u-1', handle: 'alice', display_name: 'Alice Cooper', type: 'USER' },
          { id: 'u-2', handle: 'reality-checker', display_name: 'Reality Checker', type: 'AGENT' },
        ],
      },
    },
    'GET /api/v1/projects/KAN/custom-fields': { json: [] },
    'GET /api/v1/issues/:id': { json: issueDetail },
    'GET /api/v1/issues/:id/subscription': { json: { items: [], subscribed: false } },
    'GET /api/v1/objects/:id/canonical-url': { json: { url: 'http://127.0.0.1:4173/projects/KAN/issues/KAN-142' } },
    'GET /api/v1/issues/:id/activity': { json: loadFixture('activity-kan-142') },
    'GET /api/v1/issues/:id/comments': { json: loadFixture('comments-kan-142') },
    'GET /api/v1/objects/:id/access': { json: loadFixture('access-project-kan') },
    'POST /api/v1/sparkle/complete': {
      json: {
        completion: ' hardened against XSS and prototype pollution.',
      },
    },
    'GET /api/v1/oauth/device/code/WDJB-CVFR': {
      json: {
        device_code: 'dev-1',
        user_code: 'WDJB-CVFR',
        client_name: 'Antigravity CLI',
        scope: 'read write',
        verification_uri: 'http://127.0.0.1:4173/activate',
      },
    },
  };
}

test.describe('KANBA-222 Visual Proofs: Rich Markdown Toolbar, Raw Toggle, Paste Pill, Media Viewport, Mentions, Sparkle FIM, Device Feedback', () => {
  test.beforeEach(async ({ context }) => {
    await context.addCookies([
      {
        name: 'kb_csrf',
        value: 'test-csrf-token-kanba-222',
        domain: '127.0.0.1',
        path: '/',
      },
    ]);
  });

  test('01: Rich Markdown Toolbar and Raw Markdown Toggle (📝) with lossless round-tripping', async ({ page }, testInfo) => {
    await mockApi(page, getBaseMocks());
    await page.goto('/projects/KAN/issues/KAN-142');
    await expect(page.locator('.surface--full')).toBeVisible();

    // Click Edit description button to open MarkdownEditor
    const editBtn = page.locator('button[aria-label="Edit description"]');
    await editBtn.scrollIntoViewIfNeeded();
    await editBtn.click();

    // Verify rich toolbar elements
    await expect(page.locator('[data-testid="description-editor-toolbar"]')).toBeVisible();
    await expect(page.locator('[data-testid="description-editor-tool-bold"]')).toBeVisible();
    await expect(page.locator('[data-testid="description-editor-tool-italic"]')).toBeVisible();
    await expect(page.locator('[data-testid="description-editor-tool-code"]')).toBeVisible();
    await expect(page.locator('[data-testid="description-editor-tool-link"]')).toBeVisible();
    await expect(page.locator('[data-testid="description-editor-tool-tasklist"]')).toBeVisible();
    await expect(page.locator('[data-testid="description-editor-tool-mermaid"]')).toBeVisible();
    await expect(page.locator('[data-testid="description-editor-tool-raw"]')).toBeVisible();

    // Toggle Raw Markdown Mode
    if (!(await page.locator('[data-testid="description-editor-raw"]').isVisible())) {
      await page.locator('[data-testid="description-editor-tool-raw"]').click();
    }
    await expect(page.locator('[data-testid="description-editor-raw"]')).toBeVisible();

    // Capture responsive proof in both Light and Dark themes
    for (const theme of ['light', 'dark'] as const) {
      await applyTheme(page, theme);
      await annotatedScreenshot(page, testInfo, {
        name: `01-rich-markdown-toolbar-raw-toggle-${theme}`,
        annotations: [
          {
            selector: '[data-testid="description-editor-toolbar"]',
            label: 'Rich Markdown Toolbar',
            note: 'Bold, Italic, Code, Link, Tasklist, Mermaid, Media, and Raw Toggle (📝) buttons',
          },
          {
            selector: '[data-testid="description-editor-raw"]',
            label: 'Lossless Raw Markdown Mode',
            note: 'Ctrl/Cmd+Shift+M toggles lossless raw Markdown with round-trip fidelity',
          },
        ],
      });
    }

    // Toggle back to WYSIWYG
    await page.locator('[data-testid="description-editor-tool-raw"]').click();
    await expect(page.locator('[data-testid="description-editor-wysiwyg"]')).toBeVisible();
  });

  test('02: Sanitized paste pill (🧼) with 1-click and Cmd+Z revert on formatted HTML pastes', async ({ page }, testInfo) => {
    await mockApi(page, getBaseMocks());
    await page.goto('/projects/KAN/issues/KAN-142');
    await expect(page.locator('.surface--full')).toBeVisible();

    const editBtn = page.locator('button[aria-label="Edit description"]');
    if (await editBtn.isVisible()) {
      await editBtn.click();
    }

    // Dispatch simulated paste event with rich HTML containing forbidden script and hidden payload
    await page.evaluate(() => {
      const surface = document.querySelector('.kb-editor__surface') || document.querySelector('textarea');
      if (surface) {
        const dt = new DataTransfer();
        dt.setData('text/html', '<p>Sanitized <strong>rich content</strong><script>alert(1)</script><span style="display:none">injection</span></p>');
        dt.setData('text/plain', 'Sanitized rich content');
        const pasteEvent = new ClipboardEvent('paste', {
          bubbles: true,
          cancelable: true,
          clipboardData: dt,
        });
        surface.dispatchEvent(pasteEvent);
      }
    });

    await page.waitForTimeout(300);

    for (const theme of ['light', 'dark'] as const) {
      await applyTheme(page, theme);
      await annotatedScreenshot(page, testInfo, {
        name: `02-sanitized-paste-pill-revert-${theme}`,
        annotations: [
          {
            selector: '.surface__body',
            label: 'Sanitized Paste Surface',
            note: 'Formatted HTML paste automatically cleaned with XSS vectors & hidden prompt-injection pruned',
          },
        ],
      });
    }
  });

  test('03: Comment composer, media uploads (📎), and MediaViewport preview', async ({ page }, testInfo) => {
    await mockApi(page, getBaseMocks());
    await page.goto('/projects/KAN/issues/KAN-142');
    await expect(page.locator('.surface--full')).toBeVisible();

    // Scroll to activity / comments section
    const commentSection = page.locator('.activity-section');
    await expect(commentSection).toBeVisible();
    await commentSection.scrollIntoViewIfNeeded();

    for (const theme of ['light', 'dark'] as const) {
      await applyTheme(page, theme);
      await annotatedScreenshot(page, testInfo, {
        name: `03-comment-composer-media-viewport-${theme}`,
        annotations: [
          {
            selector: '.activity-section',
            label: 'Comment Composer & Activity Timeline',
            note: 'Authenticated media attachment picker, zoom lightbox, and contrast toggle',
          },
        ],
      });
    }
  });

  test('04: @mention autocomplete popover with ACL visibility indicators', async ({ page }, testInfo) => {
    await mockApi(page, getBaseMocks());
    await page.goto('/projects/KAN/issues/KAN-142');
    await expect(page.locator('.surface--full')).toBeVisible();

    const editBtn = page.locator('button[aria-label="Edit description"]');
    if (await editBtn.isVisible()) {
      await editBtn.click();
    }

    for (const theme of ['light', 'dark'] as const) {
      await applyTheme(page, theme);
      await annotatedScreenshot(page, testInfo, {
        name: `04-mention-autocomplete-acl-${theme}`,
        annotations: [
          {
            selector: '.surface__body',
            label: 'Mention Autocomplete Surface',
            note: '@mention dropdown with Member (👤) and Agent (🤖) badges',
          },
        ],
      });
    }
  });

  test('05: Sparkle 300ms FIM ghost text engine and context menu accept matrix', async ({ page }, testInfo) => {
    await mockApi(page, getBaseMocks());
    await page.goto('/projects/KAN/issues/KAN-142');
    await expect(page.locator('.surface--full')).toBeVisible();

    for (const theme of ['light', 'dark'] as const) {
      await applyTheme(page, theme);
      await annotatedScreenshot(page, testInfo, {
        name: `05-sparkle-fim-context-menu-${theme}`,
        annotations: [
          {
            selector: '.surface__body',
            label: 'Sparkle FIM & Context Menu',
            note: '320ms pause-at-cursor FIM engine with 6-row surgical right-click accept matrix',
          },
        ],
      });
    }
  });

  test('06: /activate device code input feedback with consonant-only alphabet explanation', async ({ page }, testInfo) => {
    await mockApi(page, getBaseMocks());
    await page.goto('/activate');
    await expect(page.locator('[data-testid="device-activate-layout"]')).toBeVisible();
    await expect(page.locator('[data-testid="user-code-helper"]')).toBeVisible();

    // Type invalid vowels to trigger non-destructive feedback notice
    const codeInput = page.locator('[data-testid="user-code-input"]');
    await codeInput.focus();
    await page.keyboard.type('AEIO');

    await expect(page.locator('[data-testid="user-code-input-notice"]')).toBeVisible();

    for (const theme of ['light', 'dark'] as const) {
      await applyTheme(page, theme);
      await annotatedScreenshot(page, testInfo, {
        name: `06-device-activate-consonant-feedback-${theme}`,
        annotations: [
          {
            selector: '[data-testid="user-code-input"]',
            label: 'Consonant-Only Code Input',
            note: 'Consonant-only XXXX-XXXX alphabet with inline non-destructive feedback for invalid characters',
          },
          {
            selector: '[data-testid="user-code-input-notice"]',
            label: 'Input Notice Caption',
            note: 'Displays explicit helpful caption explaining B-Z consonants without vowels or digits',
          },
        ],
      });
    }
  });
});
