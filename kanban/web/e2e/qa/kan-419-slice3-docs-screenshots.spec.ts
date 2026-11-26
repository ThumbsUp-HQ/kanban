// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import { resolve } from 'node:path';
import { mkdirSync } from 'node:fs';
import type { Page } from '@playwright/test';
import { test, expect } from '../support/test';
import { mockApi, type MockHandlers } from '../support/mockApi';

process.env.QA_TICKET_ID = 'KAN-419';
const SCREENSHOT_DIR = resolve(
  import.meta.dirname,
  '../../../../docs/qa/KAN-419/screenshots',
);
mkdirSync(SCREENSHOT_DIR, { recursive: true });

async function applyTheme(page: Page, theme: 'light' | 'dark'): Promise<void> {
  await page.evaluate((t: string) => {
    localStorage.setItem('kb:theme', t);
    document.documentElement.dataset.theme = t;
  }, theme);
  await page.waitForTimeout(100);
}

async function assertNoHorizontalClipping(page: Page, expectedWidth: number): Promise<void> {
  const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth);
  expect(scrollWidth).toBeLessThanOrEqual(expectedWidth + 1);

  const headerControls = page.locator('.kb-docs-header button, .kb-docs-header a');
  const count = await headerControls.count();
  for (let i = 0; i < count; i++) {
    const box = await headerControls.nth(i).boundingBox();
    if (box && box.width > 0 && box.height > 0) {
      expect(box.x + box.width).toBeLessThanOrEqual(expectedWidth + 2);
    }
  }
}

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

function getDocsMocks(): MockHandlers {
  return {
    'GET /api/v1/me': { json: mockAdminUser },
    'GET /api/v1/auth/me': { json: mockAdminUser },
    'GET /api/v1/users/me': { json: mockAdminUser },
    'GET /api/v1/auth/session/me': { json: mockAdminUser },
    'GET /api/v1/auth/session': {
      json: {
        authenticated: true,
        aal_level: 2,
        csrf_token: 'csrf-test-token-docs',
        user: mockAdminUser,
      },
    },
    'GET /api/v1/session/csrf': { json: { csrf_token: 'csrf-test-token-docs' } },
    'GET /api/v1/setup/status': { json: { initialized: true, is_initialized: true, requires_setup: false } },
    'GET /api/v1/system/status': {
      json: {
        deployment_mode: 'production_multi_container',
        persistent_volume: true,
        data_mount_point: '/var/lib/kanban/data',
        is_server_admin: true,
      },
    },
    'GET /api/v1/system/about': {
      json: {
        platform: '👍kanban',
        slug: 'thumbs-up-kanban',
        tagline: 'The difference between a swarm and an Agile team is a kanban.',
        version: '0.2.1220',
        license_spdx: 'Apache-2.0',
      },
    },
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
      },
    },
    'GET /api/v1/projects': {
      json: [
        {
          id: 'proj-kan-1',
          identifier: 'KAN',
          name: 'Platform Core',
        },
      ],
    },
    'GET /api/v1/projects/KAN': {
      json: {
        id: 'proj-kan-1',
        identifier: 'KAN',
        name: 'Platform Core',
      },
    },
    'GET /api/v1/notifications': { json: { items: [], total: 0, unread_count: 0 } },
    'GET /api/v1/notifications/unread-count': { json: { unread_count: 0 } },
  };
}

const targetChapters = [
  {
    prefix: '01-three-surface-mcp',
    slug: 'three-surface-mcp-server-architecture',
    title: 'Three-Surface MCP Server Architecture',
  },
  {
    prefix: '02-zero-trust-service-auth',
    slug: 'zero-trust-service-auth-and-workload-oidc',
    title: 'Zero-Trust Service Auth & Workload OIDC',
  },
  {
    prefix: '03-mcp-tools-reference',
    slug: 'mcp-tools-reference',
    title: 'MCP Tools Reference Manual',
  },
  {
    prefix: '04-studio-config-ref',
    slug: 'studio-configuration-reference',
    title: 'Studio Configuration Reference',
  },
];

test.describe('KAN-419: Slice-3 Published Docs Visual Verification', () => {
  test('Capture verified Docs Center screenshots across Slice-3 chapters and required viewports', async ({ page }) => {
    test.setTimeout(120000);
    await mockApi(page, getDocsMocks());

    // 00. Docs Center Home (1440x900 Desktop Light & Dark)
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto('/docs');
    await applyTheme(page, 'light');
    await expect(page.locator('[data-testid="docs-center-page"]')).toBeVisible();
    await assertNoHorizontalClipping(page, 1440);
    await page.waitForTimeout(200);
    await page.screenshot({
      path: resolve(SCREENSHOT_DIR, '00-docs-center-home-1440x900-light.png'),
      fullPage: false,
    });

    await applyTheme(page, 'dark');
    await page.waitForTimeout(200);
    await page.screenshot({
      path: resolve(SCREENSHOT_DIR, '00-docs-center-home-1440x900-dark.png'),
      fullPage: false,
    });

    // Loop through each of the 4 Slice-3 target chapters across 5 viewports
    for (const chapter of targetChapters) {
      const url = `/docs/${chapter.slug}`;

      // Viewport 1: 1440x900 Desktop Light
      await page.setViewportSize({ width: 1440, height: 900 });
      await page.goto(url);
      await applyTheme(page, 'light');
      await expect(page.locator('[data-testid="docs-center-page"]')).toBeVisible();
      await assertNoHorizontalClipping(page, 1440);
      await page.waitForTimeout(200);
      await page.screenshot({
        path: resolve(SCREENSHOT_DIR, `${chapter.prefix}-1440x900-desktop-light.png`),
        fullPage: false,
      });

      // Viewport 2: 1440x900 Desktop Dark
      await applyTheme(page, 'dark');
      await page.waitForTimeout(200);
      await page.screenshot({
        path: resolve(SCREENSHOT_DIR, `${chapter.prefix}-1440x900-desktop-dark.png`),
        fullPage: false,
      });

      // Reset scroll position
      await page.evaluate(() => {
        window.scrollTo(0, 0);
      });

      // Viewport 3: 1024x768 Tablet Landscape
      await page.setViewportSize({ width: 1024, height: 768 });
      await applyTheme(page, 'light');
      await assertNoHorizontalClipping(page, 1024);
      await page.waitForTimeout(200);
      await page.screenshot({
        path: resolve(SCREENSHOT_DIR, `${chapter.prefix}-1024x768-tablet-landscape.png`),
        fullPage: false,
      });

      // Viewport 4: 768x1024 Tablet Portrait
      await page.setViewportSize({ width: 768, height: 1024 });
      await applyTheme(page, 'light');
      await assertNoHorizontalClipping(page, 768);
      await page.waitForTimeout(200);
      await page.screenshot({
        path: resolve(SCREENSHOT_DIR, `${chapter.prefix}-768x1024-tablet-portrait.png`),
        fullPage: false,
      });

      // Viewport 5: 390x844 Mobile Portrait
      await page.setViewportSize({ width: 390, height: 844 });
      await applyTheme(page, 'light');
      await assertNoHorizontalClipping(page, 390);
      await page.waitForTimeout(200);
      await page.screenshot({
        path: resolve(SCREENSHOT_DIR, `${chapter.prefix}-390x844-mobile-portrait.png`),
        fullPage: false,
      });
    }

    // Focused Scrolled View 05: Embedded Slice-3 Images Rendered in /docs
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto('/docs/three-surface-mcp-server-architecture');
    await applyTheme(page, 'light');
    const embeddedImg = page.locator('.kb-docs-main img[src*="slice3"]').first();
    await expect(embeddedImg).toBeVisible();
    const naturalWidth = await embeddedImg.evaluate((img: HTMLImageElement) => img.naturalWidth);
    expect(naturalWidth).toBeGreaterThan(0);
    await embeddedImg.scrollIntoViewIfNeeded();
    await page.waitForTimeout(300);
    await page.screenshot({
      path: resolve(SCREENSHOT_DIR, '05-embedded-slice3-images-rendered-1440x900.png'),
      fullPage: false,
    });

    // Focused Scrolled View 06: Slice-3 Studio Configuration Reference Tables
    await page.goto('/docs/studio-configuration-reference#6-mcp-access-studio');
    await applyTheme(page, 'light');
    const slice3Heading = page.locator('h2', { hasText: 'MCP Access Studio' }).first();
    await expect(slice3Heading).toBeVisible();
    await slice3Heading.scrollIntoViewIfNeeded();
    await page.waitForTimeout(300);
    await page.screenshot({
      path: resolve(SCREENSHOT_DIR, '06-slice3-studio-config-tables-1440x900.png'),
      fullPage: false,
    });

    // Focused Scrolled View 07: Mermaid Diagrams Rendered Cleanly
    await page.goto('/docs/three-surface-mcp-server-architecture');
    await applyTheme(page, 'light');
    const mermaidContainer = page.locator('.mermaid-block, [data-lang="mermaid"], .mermaid-block__preview, svg[id^="mermaid-"]').first();
    await expect(mermaidContainer).toBeVisible({ timeout: 10000 });
    await mermaidContainer.scrollIntoViewIfNeeded();
    await page.waitForTimeout(500);
    await page.screenshot({
      path: resolve(SCREENSHOT_DIR, '07-slice3-mermaid-diagrams-rendered-1440x900.png'),
      fullPage: false,
    });

    // Focused Scrolled View 08: OAuth 2.1 Governance Studio Section
    await page.goto('/docs/studio-configuration-reference#7-oauth-21-governance-studio');
    await applyTheme(page, 'light');
    const oauthHeading = page.locator('h2', { hasText: 'OAuth 2.1 Governance Studio' }).first();
    await expect(oauthHeading).toBeVisible();
    await oauthHeading.scrollIntoViewIfNeeded();
    await page.waitForTimeout(300);
    await page.screenshot({
      path: resolve(SCREENSHOT_DIR, '08-slice3-oauth-governance-tables-1440x900.png'),
      fullPage: false,
    });
  });
});
