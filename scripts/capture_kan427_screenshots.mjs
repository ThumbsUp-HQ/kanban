// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import fs from 'node:fs';
import path from 'node:path';
import { spawn } from 'node:child_process';

let chromium;
try {
  ({ chromium } = await import('/home/adamoutler/kanban/kanban/web/node_modules/@playwright/test/index.mjs'));
} catch {
  try {
    ({ chromium } = await import('@playwright/test'));
  } catch {
    ({ chromium } = await import('playwright'));
  }
}

const PORT = 18427;
const BASE_URL = `http://127.0.0.1:${PORT}`;
const OUT_DIR = path.resolve('docs/qa/KAN-427/screenshots');

const VIEWPORTS = [
  {
    name: '01-desktop-1440x900-light',
    width: 1440,
    height: 900,
    theme: 'light',
  },
  {
    name: '02-desktop-1440x900-dark',
    width: 1440,
    height: 900,
    theme: 'dark',
  },
  {
    name: '03-tablet-landscape-1024x768',
    width: 1024,
    height: 768,
    theme: 'light',
  },
  {
    name: '04-tablet-portrait-768x1024',
    width: 768,
    height: 1024,
    theme: 'light',
  },
  {
    name: '05-mobile-portrait-390x844',
    width: 390,
    height: 844,
    theme: 'light',
  },
];

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

  await page.route('**/*', async (route) => {
    const url = route.request().url();
    const method = route.request().method();

    // Strip Content-Security-Policy on non-API requests so test stylesheets and unclip styles apply cleanly
    if (!url.includes('/api/')) {
      const response = await route.fetch();
      const headers = { ...response.headers() };
      delete headers['content-security-policy'];
      delete headers['Content-Security-Policy'];
      return route.fulfill({ response, headers });
    }

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
          csrf_token: 'mock-csrf-token-12345',
          principal_id: 'usr_admin_1',
          workspace_id: 'ws_default',
          aal_level: 2,
          aal2_active: true,
          aal2_expires_at: new Date(Date.now() + 890_000).toISOString(),
        }),
      });
    }

    if (url.includes('/api/v1/users/me') || url.includes('/api/v1/auth/me')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id: 'usr_admin_1',
          email: 'admin@kanban.local',
          username: 'admin',
          display_name: 'Security Architect',
          is_server_admin: true,
          is_workspace_admin: true,
          is_project_admin: true,
          workspace_role: 'WORKSPACE_ADMIN',
          aal_level: 2,
          auth_aal: 'aal2',
          aal2_active: true,
          timezone: 'America/New_York',
          agent_onboarding_prefs: { hide_onboarding_prompt: false },
        }),
      });
    }

    if (url.includes('/api/v1/auth/mfa/status')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          totp_enabled: true,
          passkeys_count: 1,
          recovery_codes_remaining: 8,
          preferred_method: 'webauthn',
        }),
      });
    }

    if (url.includes('/api/v1/auth/webauthn/credentials') || url.includes('/api/v1/users/me/security-keys')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([
          {
            id: 'cred-1',
            nickname: 'MacBook Touch ID (Platform Passkey)',
            credential_type: 'passkey',
            created_at: '2026-10-15T09:00:00Z',
            last_used_at: '2026-11-25T12:00:00Z',
            aaguid: '00000000-0000-0000-0000-000000000000',
          },
          {
            id: 'cred-2',
            nickname: 'YubiKey 5C NFC (Hardware Security Key)',
            credential_type: 'security_key',
            created_at: '2026-10-20T14:00:00Z',
            last_used_at: '2026-11-24T18:00:00Z',
            aaguid: 'cb69481e-8ff7-4039-93ec-0a2729a100ae',
          },
        ]),
      });
    }

    if (url.includes('/api/v1/auth/identities')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ identities: [] }),
      });
    }

    if (url.includes('/api/v1/users/me/preferences')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          agent_onboarding_prefs: { hide_onboarding_prompt: false },
        }),
      });
    }

    if (url.includes('/api/v1/admin/auth-cards')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ cards: [] }),
      });
    }

    if (url.includes('/api/v1/workspaces/current') || (url.includes('/api/v1/workspaces') && method === 'GET')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id: 'ws_default',
          slug: 'kanban',
          name: 'Platform Core Workspace',
          is_current: true,
          role: 'WORKSPACE_ADMIN',
          is_admin: true,
          is_workspace_admin: true,
        }),
      });
    }

    if (url.includes('/api/v1/admin/workspace-settings')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          workspace_id: 'ws_default',
          name: 'Platform Core Workspace',
          slug: 'kanban',
          display_name: 'Platform Core Workspace',
          session_idle_timeout_min: 30,
          session_absolute_timeout_min: 1440,
          trash_retention_days: 30,
          enforce_mfa: true,
          allowed_auth_providers: ['local', 'passkey', 'oidc'],
          air_gap_mode: false,
          default_skip_loaded_sequence_numbers: false,
          issue_export_enabled: true,
          issue_import_enabled: true,
        }),
      });
    }

    if (url.includes('/api/v1/admin/principals')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          items: [
            {
              id: 'grp-1',
              name: 'Core Platform Engineers',
              handle: 'core-engineers',
              type: 'GROUP',
              principal_type: 'GROUP',
              member_count: 5,
            },
            {
              id: 'usr_admin_1',
              name: 'Security Architect',
              handle: 'admin',
              type: 'USER',
              principal_type: 'USER',
            },
          ],
        }),
      });
    }

    if (url.includes('/api/v1/admin/groups/grp-1/members')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([
          {
            id: 'usr_admin_1',
            name: 'Security Architect',
            handle: 'admin',
          },
        ]),
      });
    }

    if (url.includes('/api/v1/admin/trash') || url.includes('/trash')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          items: [
            {
              id: 'trash-item-1',
              object_type: 'ISSUE',
              object_id: 'iss-old-1',
              title: 'Deprecated CI Hook Runner Config',
              deleted_at: '2026-11-20T10:00:00Z',
              deleted_by: 'Security Architect',
            },
          ],
          total: 1,
          retention_days: 30,
        }),
      });
    }

    if (url.includes('/api/v1/admin/destructive:request')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          token: 'dest-tok-12345',
          mode: 'permanent_purge',
          confirm_phrase: 'PURGE PLATFORM CORE PERMANENTLY',
          expires_at: '2026-11-25T20:00:00Z',
          blast_summary: {
            issues_count: 42,
            docs_count: 12,
            stickies_count: 7,
            modules_count: 3,
          },
        }),
      });
    }

    if (url.includes('/projects/KAN/states')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([
          { id: 'st-backlog', name: 'Backlog', state_kind: 'backlog', color: '#94a3b8' },
          { id: 'st-in-review', name: 'In Review', state_kind: 'started', color: '#38bdf8' },
          { id: 'st-done', name: 'Done', state_kind: 'completed', color: '#22c55e' },
        ]),
      });
    }

    if (url.includes('/projects/KAN/priorities')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([
          { id: 'P0', label: 'Urgent', emoji: '🔥', color: '#ef4444' },
          { id: 'P1', label: 'High', emoji: '⚡', color: '#f97316' },
          { id: 'P2', label: 'Medium', emoji: '⏳', color: '#eab308' },
          { id: 'P3', label: 'Low', emoji: '🔵', color: '#3b82f6' },
        ]),
      });
    }

    if (url.includes('/projects/KAN/labels')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([
          { id: 'lbl-1', name: 'security', color: '#ef4444' },
          { id: 'lbl-2', name: 'performance', color: '#3b82f6' },
        ]),
      });
    }

    if (url.includes('/projects/KAN/modules')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([
          { id: 'mod-1', name: 'Core Engine', slug: 'core-engine' },
          { id: 'mod-2', name: 'Audit Subsystem', slug: 'audit-subsystem' },
        ]),
      });
    }

    if (url.includes('/projects/KAN/members')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([
          { id: 'usr_admin_1', name: 'Security Architect', role: 'ADMIN' },
        ]),
      });
    }

    if (url.includes('/projects/KAN/workflow-hooks/dry-run')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          dry_run: true,
          simulated_mutations: [
            {
              field: 'status',
              before: 'IN_REVIEW',
              after: 'DONE',
            },
            {
              field: 'labels',
              before: ['qa-pending'],
              after: ['qa-pending', 'verified'],
            },
          ],
          logs: [
            '[INFO] Starting dry-run simulation for hook: Enforce PR Link & Security Gate',
            '[INFO] Validation passed: PR #427 linked',
            '[INFO] DRY-RUN SIMULATION: No database changes were committed.',
          ],
        }),
      });
    }

    if (url.includes('/projects/KAN/workflow-hooks')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          rules: [
            {
              from_state: 'In Review',
              to_state: 'Done',
              active_hook_count: 2,
              hooks: [
                {
                  id: 'hook-1',
                  name: 'require-qa-proof-link',
                  from_state: 'In Review',
                  to_state: 'Done',
                  hook_kind: 'sync_validator',
                  sort_rank: '0000000000000001',
                  failure_policy: 'fail_closed',
                  manifest_sha256: '92d31f66098dd8194837346df091aace6d7db8ef63106181c0910ad85463f968',
                  is_enabled: true,
                  wasm_module_name: 'qa-proof-validator',
                  target_latency_budget: '<2ms',
                  description: 'Ensures description or comments include docs/qa/ proof bundle',
                },
                {
                  id: 'hook-2',
                  name: 'forensic-code-check',
                  from_state: 'In Review',
                  to_state: 'Done',
                  hook_kind: 'agent_interceptor',
                  sort_rank: '0000000000000002',
                  failure_policy: 'fail_closed',
                  manifest_sha256: '4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945',
                  is_enabled: true,
                  agent_slug: 'forensic-code-check',
                  agent_display_name: 'Forensic Code Check',
                  harness_kind: 'cli_pipe',
                  cli_binary_allowlist_id: 'agy',
                  cli_args: ['-p'],
                  timeout_ms: 60000,
                  repo_binding_slug: 'kanban-mirror',
                  allowed_mutable_fields: ['labels'],
                  description: 'Repo: kanban-mirror (:ro mount) | Mutable Fields: [labels]',
                },
              ],
            },
          ],
        }),
      });
    }

    if (url.includes('/projects/KAN/repo-bindings')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([
          {
            id: 'bind-1',
            slug: 'kanban-mirror',
            remote_url: 'https://git.internal.corp/platform/core.git',
            default_ref: 'main',
            access_mode: 'ro_vfs_mount',
            pat_configured: true,
            last_sync_at: '2026-11-25T14:00:00Z',
            sync_status: 'HEALTHY',
          },
        ]),
      });
    }

    if (url.includes('/projects/KAN/custom-fields/approvals')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([
          {
            id: 'appr-1',
            field_id: 'f-2',
            field_name: 'Compliance Audit Badge',
            field_slug: 'compliance-badge',
            requested_scope: 'WORKSPACE',
            requested_credential_mode: 'PROJECT_ADMIN_SP',
            requested_by: 'developer@kanban.local',
            requested_at: '2026-11-24T18:00:00Z',
            manifest_sha256: 'b2c3d4e5f60718293a4b5c6d7e8f90123456789abcdef0123456789abcdef01',
            status: 'PENDING',
            escalation_reason: 'Requires workspace egress to internal compliance audit server',
          },
        ]),
      });
    }

    if (url.includes('/projects/KAN/custom-fields')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([
          {
            id: 'f-1',
            slug: 'cvss-score',
            name: 'CVSS Score',
            tier: 'wasm',
            output_format: 'number',
            output_format_metadata: { maximum_fraction_digits: 1, unit_suffix: 'pts' },
            script_source: 'return { score: 8.8 };',
            target_scope: 'PROJECT',
            credential_mode: 'INVOKING_USER',
            egress_allowlist: [],
            manifest_sha256: 'a1b2c3d4e5f60718293a4b5c6d7e8f90123456789abcdef0123456789abcdef0',
            is_enabled: true,
            approval_status: 'APPROVED',
          },
          {
            id: 'f-2',
            slug: 'compliance-badge',
            name: 'Compliance Audit Badge',
            tier: 'nsjail',
            output_format: 'badge',
            output_format_metadata: { color_token: 'crimson', allowed_labels: ['SOC2', 'ISO27001', 'HIPAA'] },
            script_source: 'return "SOC2";',
            target_scope: 'WORKSPACE',
            credential_mode: 'PROJECT_ADMIN_SP',
            egress_allowlist: ['https://audit.corp.internal'],
            manifest_sha256: 'b2c3d4e5f60718293a4b5c6d7e8f90123456789abcdef0123456789abcdef01',
            is_enabled: true,
            approval_status: 'PENDING',
          },
        ]),
      });
    }

    if (url.includes('/projects/KAN')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id: 'proj-kan',
          key: 'KAN',
          name: 'Platform Core',
          description: 'Platform core microservices and security architecture',
          capabilities: ['ADMIN', 'PROJECT_ADMIN', 'EDIT', 'READ'],
          is_admin: true,
          is_project_admin: true,
          modules_enabled: true,
        }),
      });
    }

    if (url.includes('/projects')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([
          {
            id: 'proj-kan',
            key: 'KAN',
            name: 'Platform Core',
            capabilities: ['ADMIN', 'PROJECT_ADMIN', 'EDIT', 'READ'],
          },
        ]),
      });
    }

    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({}),
    });
  });
}

async function preparePageForScreenshot(page, vp, theme) {
  // Set theme in DOM and localStorage
  await page.evaluate((t) => {
    document.documentElement.dataset.theme = t;
    localStorage.setItem('theme', t);
  }, theme);

  // Assert 100vh layout invariant: scrollWidth should fit inside viewport width
  await page.evaluate((width) => {
    const sw = document.documentElement.scrollWidth;
    if (sw > width + 2) {
      console.warn(`Horizontal scroll width (${sw}) exceeds viewport width (${width})`);
    }
  }, vp.width);

  // Apply required unclip CSS before fullPage screenshot
  // CRITICAL MANDATE: do NOT hide .realtime-status-chip
  await page.addStyleTag({
    content: `
      .kb-app-shell, .kb-main-canvas {
        height: auto !important;
        max-height: none !important;
        overflow: visible !important;
      }
      .kb-topbar, header {
        position: static !important;
      }
      .realtime-status-chip {
        display: inline-flex !important;
        visibility: visible !important;
      }
    `,
  });

  await page.waitForTimeout(200);
}

async function main() {
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
      executablePath: '/usr/bin/google-chrome',
      headless: true,
      args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage', '--disable-gpu'],
    });

    for (const vp of VIEWPORTS) {
      console.log(`=== Processing Viewport: ${vp.name} (${vp.width}x${vp.height}, theme=${vp.theme}) ===`);

      // 1. Workspace Settings (expand Advanced Security & Governance)
      {
        const context = await browser.newContext({
          viewport: { width: vp.width, height: vp.height },
          colorScheme: vp.theme,
          bypassCSP: true,
        });
        const page = await context.newPage();
        await setupInterceptions(page);
        await page.goto(`${BASE_URL}/workspaces/settings`, { waitUntil: 'networkidle' });

        try {
          const advToggle = page.locator('[data-testid="workspace-advanced-security-section-toggle"]');
          if (await advToggle.count()) {
            await advToggle.click();
            await page.waitForSelector('[data-testid="idle-preset-30m"]', { timeout: 4000 });
          }
        } catch (e) {
          console.warn('workspace settings elements warning:', e.message);
        }

        await preparePageForScreenshot(page, vp, vp.theme);
        const filename = `01-workspace-settings-${vp.name}.png`;
        await page.screenshot({ path: path.join(OUT_DIR, filename), fullPage: true });
        console.log(`Captured ${filename}`);
        await context.close();
      }

      // 2a. Project Settings Priorities Tab (emoji palette)
      {
        const context = await browser.newContext({
          viewport: { width: vp.width, height: vp.height },
          colorScheme: vp.theme,
          bypassCSP: true,
        });
        const page = await context.newPage();
        await setupInterceptions(page);
        await page.goto(`${BASE_URL}/projects/KAN/settings`, { waitUntil: 'networkidle' });

        try {
          const prioritiesTab = page.locator('[data-testid="tab-priorities"]');
          if (await prioritiesTab.count()) {
            await prioritiesTab.click();
            await page.waitForSelector('[data-testid="priority-emoji-palette"]', { timeout: 4000 });
          }
        } catch (e) {
          console.warn('project priorities error:', e.message);
        }

        await preparePageForScreenshot(page, vp, vp.theme);
        const filename = `02a-project-settings-priorities-${vp.name}.png`;
        await page.screenshot({ path: path.join(OUT_DIR, filename), fullPage: true });
        console.log(`Captured ${filename}`);
        await context.close();
      }

      // 2b. Project Settings Danger Zone Tab (reactive blast-radius counters)
      {
        const context = await browser.newContext({
          viewport: { width: vp.width, height: vp.height },
          colorScheme: vp.theme,
          bypassCSP: true,
        });
        const page = await context.newPage();
        await setupInterceptions(page);
        await page.goto(`${BASE_URL}/projects/KAN/settings`, { waitUntil: 'networkidle' });

        try {
          const dangerTab = page.locator('[data-testid="tab-danger"]');
          if (await dangerTab.count()) {
            await dangerTab.click();
            const purgeBtn = page.locator('[data-testid="request-purge-btn"]');
            if (await purgeBtn.count()) {
              await purgeBtn.click();
              await page.waitForSelector('[data-testid="danger-card-purge"]', { timeout: 4000 });
            }
          }
        } catch (e) {
          console.warn('project danger zone error:', e.message);
        }

        await preparePageForScreenshot(page, vp, vp.theme);
        const filename = `02b-project-settings-danger-purge-${vp.name}.png`;
        await page.screenshot({ path: path.join(OUT_DIR, filename), fullPage: true });
        console.log(`Captured ${filename}`);
        await context.close();
      }

      // 3. Personal Settings (searchable timezone filter + passkeys copy)
      {
        const context = await browser.newContext({
          viewport: { width: vp.width, height: vp.height },
          colorScheme: vp.theme,
          bypassCSP: true,
        });
        const page = await context.newPage();
        await setupInterceptions(page);
        await page.goto(`${BASE_URL}/settings/profile`, { waitUntil: 'networkidle' });

        try {
          await page.waitForSelector('[data-testid="timezone-filter-input"]', { timeout: 6000 });
          const filterInput = page.locator('[data-testid="timezone-filter-input"]');
          await filterInput.fill('New_York');
        } catch (e) {
          console.warn('personal settings error:', e.message);
        }

        await preparePageForScreenshot(page, vp, vp.theme);
        const filename = `03-personal-settings-${vp.name}.png`;
        await page.screenshot({ path: path.join(OUT_DIR, filename), fullPage: true });
        console.log(`Captured ${filename}`);
        await context.close();
      }

      // 4. Custom Fields Studio (structured metadata form)
      {
        const context = await browser.newContext({
          viewport: { width: vp.width, height: vp.height },
          colorScheme: vp.theme,
          bypassCSP: true,
        });
        const page = await context.newPage();
        await setupInterceptions(page);
        await page.goto(`${BASE_URL}/projects/KAN/settings/custom-fields`, { waitUntil: 'networkidle' });

        try {
          await page.waitForSelector('[data-testid="custom-fields-editor-layout"], [data-testid="custom-fields-def-list"]', { timeout: 6000 });
          const cvssField = page.locator('[data-testid="field-item-cvss-score"]');
          if (await cvssField.count()) {
            await cvssField.click();
            const advSectionToggle = page.locator('[data-testid="custom-field-advanced-section-toggle"]');
            if (await advSectionToggle.count()) {
              await advSectionToggle.click();
              await page.waitForSelector('[data-testid="structured-format-metadata"]', { timeout: 4000 });
            }
          }
        } catch (e) {
          console.warn('custom fields studio error:', e.message);
        }

        await preparePageForScreenshot(page, vp, vp.theme);
        const filename = `04-custom-fields-studio-${vp.name}.png`;
        await page.screenshot({ path: path.join(OUT_DIR, filename), fullPage: true });
        console.log(`Captured ${filename}`);
        await context.close();
      }

      // 5. Workflow Studio (transition cards, git repo bindings, and SSRF callout)
      {
        const context = await browser.newContext({
          viewport: { width: vp.width, height: vp.height },
          colorScheme: vp.theme,
          bypassCSP: true,
        });
        const page = await context.newPage();
        await setupInterceptions(page);
        await page.goto(`${BASE_URL}/projects/KAN/settings/workflows`, { waitUntil: 'networkidle' });

        try {
          await page.waitForSelector('[data-testid="workflow-studio-page"], .workflow-studio', { timeout: 8000 });
        } catch (e) {
          console.warn('workflow studio error:', e.message);
        }

        await preparePageForScreenshot(page, vp, vp.theme);
        const filename = `05-workflow-studio-${vp.name}.png`;
        await page.screenshot({ path: path.join(OUT_DIR, filename), fullPage: true });
        console.log(`Captured ${filename}`);
        await context.close();
      }
    }

    await browser.close();
    console.log(`All multi-viewport screenshots captured successfully into ${OUT_DIR}`);
  } finally {
    previewProc.kill('SIGTERM');
  }
}

main().catch((err) => {
  console.error('Fatal error during screenshot capture:', err);
  process.exit(1);
});
