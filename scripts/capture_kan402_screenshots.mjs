// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import fs from 'node:fs';
import path from 'node:path';
import { spawn } from 'node:child_process';

let chromium;
try {
  ({ chromium } = await import('/home/adamoutler/.npm/_npx/81bbc6515d992ace/node_modules/playwright/index.mjs'));
} catch {
  try {
    ({ chromium } = await import('playwright'));
  } catch {
    ({ chromium } = await import('@playwright/test'));
  }
}

const PORT = 18402;
const BASE_URL = `http://127.0.0.1:${PORT}`;
const OUT_DIR = path.resolve('docs/qa/KAN-402/screenshots');

const VIEWPORTS = [
  {
    name: '01-desktop-1440x900',
    width: 1440,
    height: 900,
  },
  {
    name: '02-desktop-1440x900-dark',
    width: 1440,
    height: 900,
  },
  {
    name: '03-tablet-landscape-1024x768',
    width: 1024,
    height: 768,
  },
  {
    name: '04-tablet-portrait-768x1024',
    width: 768,
    height: 1024,
  },
  {
    name: '05-mobile-portrait-390x844',
    width: 390,
    height: 844,
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
  await page.route('**/*', async (route) => {
    const url = route.request().url();
    const method = route.request().method();

    // Do NOT intercept HTML/JS/CSS assets or page navigation
    if (!url.includes('/api/')) {
      return route.continue();
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
          principal_id: 'usr_admin_test_1',
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
          id: 'usr_admin_test_1',
          email: 'admin@kanban.local',
          username: 'admin',
          display_name: 'Platform Administrator',
          is_server_admin: true,
          is_workspace_admin: true,
          workspace_role: 'WORKSPACE_ADMIN',
          aal_level: 2,
          auth_aal: 'aal2',
          aal2_active: true,
        }),
      });
    }

    // AI Providers (Workspace & Project)
    if (url.includes('/ai-providers')) {
      if (url.includes('project_id=')) {
        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify([
            {
              id: 'b1b1b1b1-1111-4000-8000-000000000001',
              slug: 'project-openai-dedicated',
              name: 'Project Dedicated OpenAI',
              provider_kind: 'openai',
              model_allowlist: ['gpt-4o', 'o3-mini'],
              enabled: true,
              priority: 1,
              project_id: 'proj-kan-uuid',
              api_key_set: true,
              created_at: '2026-11-15T10:00:00Z',
              updated_at: '2026-11-24T12:00:00Z',
            },
          ]),
        });
      }
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([
          {
            id: 'a1a1a1a1-1111-4000-8000-000000000001',
            slug: 'anthropic-workspace',
            name: 'Anthropic Claude Workspace',
            provider_kind: 'anthropic',
            model_allowlist: ['claude-3-7-sonnet', 'claude-3-5-haiku'],
            enabled: true,
            priority: 1,
            project_id: null,
            api_key_set: true,
            created_at: '2026-11-01T10:00:00Z',
            updated_at: '2026-11-20T12:00:00Z',
          },
          {
            id: 'a2a2a2a2-2222-4000-8000-000000000002',
            slug: 'ollama-local-cluster',
            name: 'Ollama Air-Gapped Local',
            provider_kind: 'ollama',
            model_allowlist: ['deepseek-coder:6.7b', 'llama3.1:8b'],
            enabled: true,
            priority: 2,
            project_id: null,
            api_key_set: false,
            created_at: '2026-11-05T10:00:00Z',
            updated_at: '2026-11-22T12:00:00Z',
          },
        ]),
      });
    }

    // Agent Definitions (Workspace & Project)
    if (url.includes('/agent-definitions')) {
      if (url.includes('project_id=')) {
        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify([
            {
              id: 'd1d1d1d1-1111-4000-8000-000000000001',
              workspace_id: 'ws_default',
              project_id: 'proj-kan-uuid',
              principal_id: 'usr_sprint_bot',
              slug: 'project-sprint-bot',
              display_name: 'Project Sprint Assistant',
              harness_kind: 'in_app_sdk',
              provider_kind: 'openai',
              model_id: 'gpt-4o',
              cli_args: [],
              repo_access_mode: 'bare_git_tools',
              mcp_allowed_tools: ['kanban_issues', 'git_log'],
              system_instructions_md: 'Automated release notes and sprint burndown generator for Platform Core.',
              timeout_ms: 45000,
            },
          ]),
        });
      }
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([
          {
            id: 'c1c1c1c1-1111-4000-8000-000000000001',
            workspace_id: 'ws_default',
            project_id: null,
            principal_id: 'usr_triage_bot',
            slug: 'workspace-triage-bot',
            display_name: 'Workspace Triage Agent',
            harness_kind: 'in_app_sdk',
            provider_kind: 'anthropic',
            model_id: 'claude-3-5-haiku',
            cli_args: [],
            repo_access_mode: 'none',
            mcp_allowed_tools: ['issues_list', 'issues_update'],
            system_instructions_md: 'You are a workspace triage agent that categorizes incoming work items.',
            timeout_ms: 30000,
          },
          {
            id: 'c2c2c2c2-2222-4000-8000-000000000002',
            workspace_id: 'ws_default',
            project_id: null,
            principal_id: 'usr_sec_agent',
            slug: 'security-auditor-agent',
            display_name: 'Security Auditor Agent',
            harness_kind: 'cli_pipe',
            provider_kind: 'gemini',
            model_id: 'gemini-3.8-flash',
            cli_args: ['-p', 'audit'],
            repo_access_mode: 'ro_vfs_mount',
            mcp_allowed_tools: ['git_diff', 'ast_grep'],
            system_instructions_md: 'Autonomous security scanner performing forensic AST audits on pull requests.',
            timeout_ms: 60000,
          },
        ]),
      });
    }

    if (url.includes('/api/v1/workspaces/current/settings') || url.includes('/api/v1/admin/workspace-settings') || url.includes('/api/v1/workspaces/ws_default/settings')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          workspace_id: 'ws_default',
          air_gap_mode: false,
        }),
      });
    }

    if (url.endsWith('/workspaces/current') || url.includes('/workspaces/current?')) {
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

    if (url.includes('/api/v1/workspaces') && method === 'GET' && !url.includes('/ai-providers') && !url.includes('/agent-definitions') && !url.includes('/settings')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([
          { id: 'ws_default', slug: 'kanban', name: 'Platform Engineering' },
        ]),
      });
    }

    if (url.includes('/api/v1/projects') && !url.includes('/ai-providers') && !url.includes('/agent-definitions')) {
      if (url.endsWith('/projects') || url.includes('/projects?')) {
        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify([
            { id: 'proj-kan-uuid', key: 'KAN', name: 'Platform Core', workspace_id: 'ws_default' },
          ]),
        });
      }
      if (url.includes('/projects/KAN') || url.includes('/projects/proj-kan-uuid')) {
        if (url.includes('/members')) {
          return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([]) });
        }
        if (url.includes('/states')) {
          return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([]) });
        }
        if (url.includes('/priorities')) {
          return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([]) });
        }
        if (url.includes('/labels')) {
          return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([]) });
        }
        if (url.includes('/custom-fields')) {
          return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([]) });
        }
        if (url.includes('/integrations')) {
          return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([]) });
        }
        if (url.includes('/modules')) {
          return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([]) });
        }
        if (url.includes('/trash')) {
          return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([]) });
        }
        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            id: 'proj-kan-uuid',
            key: 'KAN',
            identifier: 'KAN',
            name: 'Platform Core',
            description_markdown: 'Platform Core Project with Dedicated Autonomous AI Agents',
            workspace_id: 'ws_default',
            modules_enabled: true,
            skip_loaded_sequence_numbers: false,
            default_module_ids: [],
            auto_archive_days: 30,
            capabilities: ['ADMIN', 'EDIT', 'READ'],
            is_project_admin: true,
          }),
        });
      }
    }



    if (url.includes('/api/')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({}),
      });
    }

    return route.continue();
  });
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

    // 1. Viewport 1440x900 light
    {
      const vp = VIEWPORTS[0];
      console.log(`Capturing ${vp.name}...`);
      const context = await browser.newContext({
        viewport: { width: vp.width, height: vp.height },
        colorScheme: 'light',
      });
      const page = await context.newPage();
      await setupInterceptions(page);

      // Workspace AI Studio
      await page.goto(`${BASE_URL}/workspaces/settings/ai`, { waitUntil: 'networkidle' });
      await page.evaluate(() => {
        document.documentElement.dataset.theme = 'light';
        localStorage.setItem('theme', 'light');
      });
      await page.waitForSelector('[data-testid="ai-studio-page"]', { timeout: 10000 });
      await page.waitForTimeout(400);
      await page.screenshot({
        path: path.join(OUT_DIR, '01-workspace-ai-desktop-1440x900-light.png'),
        fullPage: false,
      });

      // Workspace Agents Studio
      await page.goto(`${BASE_URL}/workspaces/settings/agents`, { waitUntil: 'networkidle' });
      await page.evaluate(() => {
        document.documentElement.dataset.theme = 'light';
        localStorage.setItem('theme', 'light');
      });
      await page.waitForSelector('[data-testid="agent-studio-page"]', { timeout: 10000 });
      await page.waitForTimeout(400);
      await page.screenshot({
        path: path.join(OUT_DIR, '01-workspace-agents-desktop-1440x900-light.png'),
        fullPage: false,
      });

      // Project Settings AI & Agents Tab
      await page.goto(`${BASE_URL}/projects/KAN/settings?tab=ai-agents`, { waitUntil: 'networkidle' });
      await page.evaluate(() => {
        document.documentElement.dataset.theme = 'light';
        localStorage.setItem('theme', 'light');
      });
      await page.waitForSelector('[data-testid="project-ai-agents-section"]', { timeout: 10000 });
      await page.waitForTimeout(400);
      await page.screenshot({
        path: path.join(OUT_DIR, '01-project-ai-agents-desktop-1440x900-light.png'),
        fullPage: false,
      });

      await context.close();
    }

    // 2. Viewport 1440x900 dark
    {
      const vp = VIEWPORTS[1];
      console.log(`Capturing ${vp.name}...`);
      const context = await browser.newContext({
        viewport: { width: vp.width, height: vp.height },
        colorScheme: 'dark',
      });
      const page = await context.newPage();
      await setupInterceptions(page);

      // Workspace AI Studio
      await page.goto(`${BASE_URL}/workspaces/settings/ai`, { waitUntil: 'networkidle' });
      await page.evaluate(() => {
        document.documentElement.dataset.theme = 'dark';
        localStorage.setItem('theme', 'dark');
      });
      await page.waitForSelector('[data-testid="ai-studio-page"]', { timeout: 10000 });
      await page.waitForTimeout(400);
      await page.screenshot({
        path: path.join(OUT_DIR, '02-workspace-ai-desktop-1440x900-dark.png'),
        fullPage: false,
      });

      // Workspace Agents Studio
      await page.goto(`${BASE_URL}/workspaces/settings/agents`, { waitUntil: 'networkidle' });
      await page.evaluate(() => {
        document.documentElement.dataset.theme = 'dark';
        localStorage.setItem('theme', 'dark');
      });
      await page.waitForSelector('[data-testid="agent-studio-page"]', { timeout: 10000 });
      await page.waitForTimeout(400);
      await page.screenshot({
        path: path.join(OUT_DIR, '02-workspace-agents-desktop-1440x900-dark.png'),
        fullPage: false,
      });

      // Project Settings AI & Agents Tab
      await page.goto(`${BASE_URL}/projects/KAN/settings?tab=ai-agents`, { waitUntil: 'networkidle' });
      await page.evaluate(() => {
        document.documentElement.dataset.theme = 'dark';
        localStorage.setItem('theme', 'dark');
      });
      await page.waitForSelector('[data-testid="project-ai-agents-section"]', { timeout: 10000 });
      await page.waitForTimeout(400);
      await page.screenshot({
        path: path.join(OUT_DIR, '02-project-ai-agents-desktop-1440x900-dark.png'),
        fullPage: false,
      });

      await context.close();
    }

    // 3. Viewport 1024x768 Tablet Landscape
    {
      const vp = VIEWPORTS[2];
      console.log(`Capturing ${vp.name}...`);
      const context = await browser.newContext({
        viewport: { width: vp.width, height: vp.height },
        colorScheme: 'light',
      });
      const page = await context.newPage();
      await setupInterceptions(page);

      // Workspace AI Studio
      await page.goto(`${BASE_URL}/workspaces/settings/ai`, { waitUntil: 'networkidle' });
      await page.evaluate(() => {
        document.documentElement.dataset.theme = 'light';
        localStorage.setItem('theme', 'light');
      });
      await page.waitForSelector('[data-testid="ai-studio-page"]', { timeout: 10000 });
      await page.waitForTimeout(400);
      await page.screenshot({
        path: path.join(OUT_DIR, '03-workspace-ai-tablet-landscape-1024x768.png'),
        fullPage: false,
      });

      // Project Settings AI & Agents
      await page.goto(`${BASE_URL}/projects/KAN/settings?tab=ai-agents`, { waitUntil: 'networkidle' });
      await page.evaluate(() => {
        document.documentElement.dataset.theme = 'light';
        localStorage.setItem('theme', 'light');
      });
      await page.waitForSelector('[data-testid="project-ai-agents-section"]', { timeout: 10000 });
      await page.waitForTimeout(400);
      await page.screenshot({
        path: path.join(OUT_DIR, '03-project-ai-agents-tablet-landscape-1024x768.png'),
        fullPage: false,
      });

      await context.close();
    }

    // 4. Viewport 768x1024 Tablet Portrait
    {
      const vp = VIEWPORTS[3];
      console.log(`Capturing ${vp.name}...`);
      const context = await browser.newContext({
        viewport: { width: vp.width, height: vp.height },
        colorScheme: 'light',
      });
      const page = await context.newPage();
      await setupInterceptions(page);

      // Workspace AI Studio
      await page.goto(`${BASE_URL}/workspaces/settings/ai`, { waitUntil: 'networkidle' });
      await page.evaluate(() => {
        document.documentElement.dataset.theme = 'light';
        localStorage.setItem('theme', 'light');
      });
      await page.waitForSelector('[data-testid="ai-studio-page"]', { timeout: 10000 });
      await page.waitForTimeout(400);
      await page.screenshot({
        path: path.join(OUT_DIR, '04-workspace-ai-tablet-portrait-768x1024.png'),
        fullPage: false,
      });

      // Project Settings AI & Agents
      await page.goto(`${BASE_URL}/projects/KAN/settings?tab=ai-agents`, { waitUntil: 'networkidle' });
      await page.evaluate(() => {
        document.documentElement.dataset.theme = 'light';
        localStorage.setItem('theme', 'light');
      });
      await page.waitForSelector('[data-testid="project-ai-agents-section"]', { timeout: 10000 });
      await page.waitForTimeout(400);
      await page.screenshot({
        path: path.join(OUT_DIR, '04-project-ai-agents-tablet-portrait-768x1024.png'),
        fullPage: false,
      });

      await context.close();
    }

    // 5. Viewport 390x844 Mobile Portrait
    {
      const vp = VIEWPORTS[4];
      console.log(`Capturing ${vp.name}...`);
      const context = await browser.newContext({
        viewport: { width: vp.width, height: vp.height },
        colorScheme: 'light',
      });
      const page = await context.newPage();
      await setupInterceptions(page);

      // Workspace AI Studio
      await page.goto(`${BASE_URL}/workspaces/settings/ai`, { waitUntil: 'networkidle' });
      await page.evaluate(() => {
        document.documentElement.dataset.theme = 'light';
        localStorage.setItem('theme', 'light');
      });
      await page.waitForSelector('[data-testid="ai-studio-page"]', { timeout: 10000 });
      await page.waitForTimeout(400);
      await page.screenshot({
        path: path.join(OUT_DIR, '05-workspace-ai-mobile-390x844.png'),
        fullPage: false,
      });

      // Project Settings AI & Agents
      await page.goto(`${BASE_URL}/projects/KAN/settings?tab=ai-agents`, { waitUntil: 'networkidle' });
      await page.evaluate(() => {
        document.documentElement.dataset.theme = 'light';
        localStorage.setItem('theme', 'light');
      });
      await page.waitForSelector('[data-testid="project-ai-agents-section"]', { timeout: 10000 });
      await page.waitForTimeout(400);
      await page.screenshot({
        path: path.join(OUT_DIR, '05-project-ai-agents-mobile-390x844.png'),
        fullPage: false,
      });

      await context.close();
    }

    await browser.close();
    console.log('All 5 viewport screenshots captured successfully in docs/qa/KAN-402/screenshots/');
  } finally {
    previewProc.kill();
  }
}

main().catch((err) => {
  console.error('Screenshot capture failed:', err);
  process.exit(1);
});
