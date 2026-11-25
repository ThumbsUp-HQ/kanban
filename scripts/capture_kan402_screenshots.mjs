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

async function setupInterceptions(page, userRole = 'WORKSPACE_ADMIN') {
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
      const isWorkspaceAdmin = userRole === 'WORKSPACE_ADMIN';
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          authenticated: true,
          mfa_pending: false,
          csrf_token: 'mock-csrf-token-12345',
          principal_id: isWorkspaceAdmin ? 'usr_ws_admin_1' : 'usr_proj_admin_1',
          workspace_id: 'ws_default',
          aal_level: isWorkspaceAdmin ? 2 : 1,
          aal2_active: isWorkspaceAdmin,
          aal2_expires_at: isWorkspaceAdmin ? new Date(Date.now() + 890_000).toISOString() : null,
        }),
      });
    }

    if (url.includes('/api/v1/users/me') || url.includes('/api/v1/auth/me')) {
      const isWorkspaceAdmin = userRole === 'WORKSPACE_ADMIN';
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id: isWorkspaceAdmin ? 'usr_ws_admin_1' : 'usr_proj_admin_1',
          email: isWorkspaceAdmin ? 'wsadmin@kanban.local' : 'projadmin@kanban.local',
          username: isWorkspaceAdmin ? 'wsadmin' : 'projadmin',
          display_name: isWorkspaceAdmin ? 'Workspace Administrator' : 'Project Administrator',
          is_server_admin: false,
          is_workspace_admin: isWorkspaceAdmin,
          workspace_role: isWorkspaceAdmin ? 'WORKSPACE_ADMIN' : 'MEMBER',
          aal_level: isWorkspaceAdmin ? 2 : 1,
          auth_aal: isWorkspaceAdmin ? 'aal2' : 'aal1',
          aal2_active: isWorkspaceAdmin,
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

    async function captureItem({ vp, colorScheme, url, selector, filename, role }) {
      console.log(`Capturing ${filename} (${vp.width}x${vp.height} ${colorScheme})...`);
      const context = await browser.newContext({
        viewport: { width: vp.width, height: vp.height },
        colorScheme,
      });
      const page = await context.newPage();
      await setupInterceptions(page, role);
      await page.goto(url, { waitUntil: 'networkidle' });
      await page.evaluate((theme) => {
        document.documentElement.dataset.theme = theme;
        localStorage.setItem('theme', theme);
      }, colorScheme);
      await page.waitForSelector(selector, { timeout: 10000 });
      await page.waitForTimeout(500);
      await page.screenshot({
        path: path.join(OUT_DIR, filename),
        fullPage: false,
      });
      await context.close();
    }

    // 1. Viewport 1440x900 light
    await captureItem({
      vp: VIEWPORTS[0],
      colorScheme: 'light',
      url: `${BASE_URL}/workspaces/settings/ai`,
      selector: '[data-testid="ai-studio-page"]',
      filename: '01-workspace-ai-desktop-1440x900-light.png',
      role: 'WORKSPACE_ADMIN',
    });
    await captureItem({
      vp: VIEWPORTS[0],
      colorScheme: 'light',
      url: `${BASE_URL}/workspaces/settings/agents`,
      selector: '[data-testid="agent-studio-page"]',
      filename: '01-workspace-agents-desktop-1440x900-light.png',
      role: 'WORKSPACE_ADMIN',
    });
    await captureItem({
      vp: VIEWPORTS[0],
      colorScheme: 'light',
      url: `${BASE_URL}/projects/KAN/settings?tab=ai-agents`,
      selector: '[data-testid="project-ai-agents-section"]',
      filename: '01-project-ai-agents-desktop-1440x900-light.png',
      role: 'PROJECT_ADMIN',
    });

    // 2. Viewport 1440x900 dark
    await captureItem({
      vp: VIEWPORTS[1],
      colorScheme: 'dark',
      url: `${BASE_URL}/workspaces/settings/ai`,
      selector: '[data-testid="ai-studio-page"]',
      filename: '02-workspace-ai-desktop-1440x900-dark.png',
      role: 'WORKSPACE_ADMIN',
    });
    await captureItem({
      vp: VIEWPORTS[1],
      colorScheme: 'dark',
      url: `${BASE_URL}/workspaces/settings/agents`,
      selector: '[data-testid="agent-studio-page"]',
      filename: '02-workspace-agents-desktop-1440x900-dark.png',
      role: 'WORKSPACE_ADMIN',
    });
    await captureItem({
      vp: VIEWPORTS[1],
      colorScheme: 'dark',
      url: `${BASE_URL}/projects/KAN/settings?tab=ai-agents`,
      selector: '[data-testid="project-ai-agents-section"]',
      filename: '02-project-ai-agents-desktop-1440x900-dark.png',
      role: 'PROJECT_ADMIN',
    });

    // 3. Viewport 1024x768 Tablet Landscape
    await captureItem({
      vp: VIEWPORTS[2],
      colorScheme: 'light',
      url: `${BASE_URL}/workspaces/settings/ai`,
      selector: '[data-testid="ai-studio-page"]',
      filename: '03-workspace-ai-tablet-landscape-1024x768.png',
      role: 'WORKSPACE_ADMIN',
    });
    await captureItem({
      vp: VIEWPORTS[2],
      colorScheme: 'light',
      url: `${BASE_URL}/projects/KAN/settings?tab=ai-agents`,
      selector: '[data-testid="project-ai-agents-section"]',
      filename: '03-project-ai-agents-tablet-landscape-1024x768.png',
      role: 'PROJECT_ADMIN',
    });

    // 4. Viewport 768x1024 Tablet Portrait
    await captureItem({
      vp: VIEWPORTS[3],
      colorScheme: 'light',
      url: `${BASE_URL}/workspaces/settings/ai`,
      selector: '[data-testid="ai-studio-page"]',
      filename: '04-workspace-ai-tablet-portrait-768x1024.png',
      role: 'WORKSPACE_ADMIN',
    });
    await captureItem({
      vp: VIEWPORTS[3],
      colorScheme: 'light',
      url: `${BASE_URL}/projects/KAN/settings?tab=ai-agents`,
      selector: '[data-testid="project-ai-agents-section"]',
      filename: '04-project-ai-agents-tablet-portrait-768x1024.png',
      role: 'PROJECT_ADMIN',
    });

    // 5. Viewport 390x844 Mobile Portrait
    await captureItem({
      vp: VIEWPORTS[4],
      colorScheme: 'light',
      url: `${BASE_URL}/workspaces/settings/ai`,
      selector: '[data-testid="ai-studio-page"]',
      filename: '05-workspace-ai-mobile-390x844.png',
      role: 'WORKSPACE_ADMIN',
    });
    await captureItem({
      vp: VIEWPORTS[4],
      colorScheme: 'light',
      url: `${BASE_URL}/projects/KAN/settings?tab=ai-agents`,
      selector: '[data-testid="project-ai-agents-section"]',
      filename: '05-project-ai-agents-mobile-390x844.png',
      role: 'PROJECT_ADMIN',
    });

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
