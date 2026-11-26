// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import fs from 'node:fs';
import path from 'node:path';
import { spawn } from 'node:child_process';

let chromium;
try {
  ({ chromium } = await import('@playwright/test'));
} catch {
  try {
    ({ chromium } = await import('/home/adamoutler/kanban/kanban/web/node_modules/@playwright/test/index.mjs'));
  } catch {
    ({ chromium } = await import('playwright'));
  }
}

const PORT = 18956;
const BASE_URL = `http://127.0.0.1:${PORT}`;
const OUT_DIR = path.resolve('docs/qa/KAN-526/screenshots');

async function waitForServer(url, timeoutMs = 30000) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    try {
      const res = await fetch(url);
      if (res.ok || res.status === 200 || res.status === 404) {
        return;
      }
    } catch {
      // Retry
    }
    await new Promise((r) => setTimeout(r, 400));
  }
  throw new Error(`Timeout waiting for preview server at ${url}`);
}

async function setupInterceptions(page) {
  await page.addInitScript(() => {
    class MockWS extends EventTarget {
      constructor(url, protocols) {
        super();
        this.url = url;
        this.protocols = protocols;
        this.readyState = 1;
        setTimeout(() => {
          this.dispatchEvent(new Event('open'));
        }, 10);
      }
      send() {}
      close() {
        this.readyState = 3;
        this.dispatchEvent(new Event('close'));
      }
    }
    window.WebSocket = MockWS;
  });

  const mockAdminUser = {
    id: 'usr_admin_1',
    email: 'admin@kanban.local',
    username: 'admin',
    display_name: 'Adam Architect',
    is_server_admin: true,
    is_workspace_admin: true,
    workspace_role: 'WORKSPACE_ADMIN',
    aal_level: 2,
    auth_aal: 'aal2',
    aal2_active: true,
  };

  const mockAudits = [
    {
      id: 'aud-1',
      workspace_id: 'ws-1',
      link_id: 'lnk-1',
      reason: 'DANGLING_TARGET',
      detected_at: '2026-11-18T12:00:00Z',
      purged_at: null,
      resolved_at: null,
      link_snapshot: {
        source_id: 'iss-1',
        target_id: 'iss-999-dangling',
        link_type: 'BLOCKS',
      },
      source_snapshot: {
        id: 'iss-1',
        canonical_key: 'KAN-142',
        title: 'Fix access checks',
        kind: 'issue',
      },
      target_snapshot: null,
    },
    {
      id: 'aud-2',
      workspace_id: 'ws-1',
      link_id: 'lnk-2',
      reason: 'SOFT_DELETED_ENDPOINT',
      detected_at: '2026-11-18T13:00:00Z',
      purged_at: null,
      resolved_at: null,
      link_snapshot: {
        source_id: 'iss-2',
        target_id: 'iss-3',
        link_type: 'RELATES_TO',
      },
      source_snapshot: {
        id: 'iss-2',
        canonical_key: 'KAN-143',
        title: 'Active issue',
        kind: 'issue',
      },
      target_snapshot: {
        id: 'iss-3',
        canonical_key: 'KAN-99',
        title: 'Soft-deleted ticket',
        kind: 'issue',
        deleted_at: '2026-11-17T00:00:00Z',
      },
    },
    {
      id: 'aud-3',
      workspace_id: 'ws-1',
      link_id: 'lnk-3',
      reason: 'CROSS_WORKSPACE_LEAK',
      detected_at: '2026-11-18T14:00:00Z',
      purged_at: null,
      resolved_at: null,
      link_snapshot: {
        source_id: 'iss-4',
        target_id: 'iss-5',
        link_type: 'BLOCKS',
      },
      source_snapshot: {
        id: 'iss-4',
        canonical_key: 'KAN-201',
        title: 'Export engine',
        kind: 'issue',
      },
      target_snapshot: {
        id: 'iss-5',
        canonical_key: 'SEC-12',
        title: 'External reference',
        kind: 'issue',
      },
    },
  ];

  await page.route('**/*', async (route) => {
    const url = route.request().url();

    if (url.includes('/api/v1/setup/status')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ initialized: true, is_initialized: true, requires_setup: false }),
      });
    }

    if (url.includes('/api/v1/notifications')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ items: [], total: 0, unread_count: 0 }),
      });
    }

    if (url.includes('/api/v1/auth/session')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          authenticated: true,
          mfa_pending: false,
          csrf_token: 'mock-csrf-token',
          principal_id: 'usr_admin_1',
          workspace_id: 'ws_default',
          aal_level: 2,
          aal2_active: true,
          aal2_expires_at: new Date(Date.now() + 890_000).toISOString(),
        }),
      });
    }

    if (url.includes('/api/v1/auth/me') || url.includes('/api/v1/users/me')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(mockAdminUser),
      });
    }

    if (url.includes('/api/v1/workspaces/current')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id: 'ws_default',
          name: 'Platform Engineering',
          slug: 'kanban',
          is_current: true,
        }),
      });
    }

    if (url.includes('/api/v1/workspaces')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([
          { id: 'ws_default', slug: 'kanban', name: 'Kanban Workspace' },
        ]),
      });
    }

    if (url.includes('/api/v1/projects')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([
          { id: 'proj_kan', key: 'KAN', name: 'Kanban Project' },
        ]),
      });
    }

    if (url.includes('/api/v1/admin/object-links/audits/scan') || url.includes('/api/v1/admin/object-links:audit')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          flagged_total: 3,
          by_reason: {
            DANGLING_TARGET: 1,
            SOFT_DELETED_ENDPOINT: 1,
            CROSS_WORKSPACE_LEAK: 1,
          },
        }),
      });
    }

    if (url.includes('/api/v1/admin/object-links/audits')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          items: mockAudits,
          has_more: false,
          total: mockAudits.length,
        }),
      });
    }

    return route.continue();
  });
}

async function captureViewports() {
  fs.mkdirSync(OUT_DIR, { recursive: true });

  console.log(`Starting preview server on port ${PORT}...`);
  const previewProc = spawn(
    'pnpm',
    ['--dir', 'kanban/web', 'preview', '--port', String(PORT), '--host', '127.0.0.1'],
    { stdio: 'inherit' }
  );

  try {
    await waitForServer(BASE_URL);
    console.log(`Preview server ready at ${BASE_URL}`);

    const browser = await chromium.launch({
      headless: true,
      args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage'],
    });

    const configs = [
      { name: 'desktop-light-1440x900.png', width: 1440, height: 900, theme: 'light', openPopover: false },
      { name: 'desktop-dark-1440x900.png', width: 1440, height: 900, theme: 'dark', openPopover: false },
      { name: 'tablet-768x1024.png', width: 768, height: 1024, theme: 'light', openPopover: false },
      { name: 'tablet-dark-768x1024.png', width: 768, height: 1024, theme: 'dark', openPopover: false },
      { name: 'mobile-390x844.png', width: 390, height: 844, theme: 'light', openPopover: false },
      { name: 'mobile-dark-390x844.png', width: 390, height: 844, theme: 'dark', openPopover: false },
      { name: 'popover-open-light-1440x900.png', width: 1440, height: 900, theme: 'light', openPopover: true },
      { name: 'popover-open-dark-1440x900.png', width: 1440, height: 900, theme: 'dark', openPopover: true },
    ];

    for (const cfg of configs) {
      console.log(`Capturing ${cfg.name}...`);
      const context = await browser.newContext({
        viewport: { width: cfg.width, height: cfg.height },
        colorScheme: cfg.theme,
      });
      const page = await context.newPage();
      await setupInterceptions(page);

      await page.goto(`${BASE_URL}/admin/link-auditor`, { waitUntil: 'networkidle' });

      await page.evaluate((theme) => {
        document.documentElement.dataset.theme = theme;
        document.documentElement.setAttribute('data-theme', theme);
        localStorage.setItem('theme', theme);
        localStorage.setItem('kb:theme', theme);
      }, cfg.theme);

      const studio = page.locator('[data-testid="link-auditor-studio"]');
      await studio.waitFor({ state: 'visible', timeout: 8000 });
      await page.waitForTimeout(300);

      if (cfg.openPopover) {
        const hintBtn = page.locator('[data-testid="integrity-metrics-help"]');
        await hintBtn.waitFor({ state: 'visible', timeout: 5000 });
        await hintBtn.click();
        const popover = page.locator('[data-testid="integrity-metrics-help-popover"]');
        await popover.waitFor({ state: 'visible', timeout: 5000 });
        await page.waitForTimeout(300);
      }

      const outPath = path.join(OUT_DIR, cfg.name);
      await page.screenshot({ path: outPath, fullPage: false });
      console.log(`Saved ${outPath}`);
      await context.close();
    }

    await browser.close();
    console.log(`All 8 screenshots successfully captured in ${OUT_DIR}`);
  } finally {
    previewProc.kill();
  }
}

captureViewports().catch((err) => {
  console.error('Screenshot capture failed:', err);
  process.exit(1);
});
