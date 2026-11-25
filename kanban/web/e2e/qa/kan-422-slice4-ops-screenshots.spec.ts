// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import { resolve } from 'node:path';
import { mkdirSync } from 'node:fs';
import type { Page } from '@playwright/test';
import { test, expect } from '../support/test';
import { mockApi, type MockHandlers } from '../support/mockApi';

process.env.QA_TICKET_ID = 'KAN-422';
const SCREENSHOT_DIR = resolve(
  import.meta.dirname,
  '../../../../docs/qa/KAN-422/screenshots',
);
mkdirSync(SCREENSHOT_DIR, { recursive: true });

async function applyTheme(page: Page, theme: 'light' | 'dark'): Promise<void> {
  await page.evaluate((t: string) => {
    localStorage.setItem('kb:theme', t);
    document.documentElement.dataset.theme = t;
  }, theme);
  await page.waitForTimeout(100);
}

const mockAdminUser = {
  id: 'usr-admin-1',
  handle: 'server_admin',
  display_name: 'Server Admin',
  email: 'admin@example.com',
  is_server_admin: true,
  is_workspace_admin: true,
  aal_level: 2,
  auth_aal: 'aal2',
};

const mockDiagnostics = {
  status: 'healthy',
  runtime_and_container: {
    deployment_mode: 'production_multi_container',
    in_container: true,
    container_runtime: 'docker',
    container_id_short: 'c116ba38',
    os_platform: 'Linux-6.6.137',
    python_version: '3.12.7',
    process_uid: 1000,
    process_gid: 1000,
    is_non_root: true,
    uptime_seconds: 3600.0,
    cgroup_version: 'v2',
    memory_limit_bytes: 4294967296,
    memory_current_bytes: 524288000,
    cpu_quota: 'max',
    pids_limit: 4096,
    pids_current: 42,
  },
  storage: {
    persistent_volume: true,
    data_mount_point: '/var/lib/kanban/data',
    data_mount_fstype: 'ext4',
    attachments_backend: 'local',
    sri_manifest_present: true,
    directories: [
      {
        name: 'attachments',
        path: '/var/lib/kanban/data/attachments',
        exists: true,
        writable: true,
        free_bytes: 107374182400,
        total_bytes: 536870912000,
      },
      {
        name: 'backups',
        path: '/var/lib/kanban/data/backups',
        exists: true,
        writable: true,
        free_bytes: 107374182400,
        total_bytes: 536870912000,
      },
    ],
  },
  database: {
    connected: true,
    latency_ms: 1.25,
    server_version: 'PostgreSQL 16.2',
    active_role_non_bypass: true,
    force_rls_verified: true,
    alembic_head_current: true,
    code_heads: ['p6_19_server_admin_cross_workspace_role_access'],
    db_heads: ['p6_19_server_admin_cross_workspace_role_access'],
    pool: {
      size: 10,
      checked_in: 9,
      checked_out: 1,
      overflow: 0,
    },
    sanitized_dsn_target: {
      dialect: 'postgresql',
      host: '127.0.0.1',
      port: 5432,
      database: 'kanban',
      is_unix_socket: false,
    },
  },
  realtime: {
    ws_enabled: true,
    ws_paths: ['/ws', '/api/v1/ws'],
    sse_enabled: true,
    sse_path: '/sse',
    hub_running: true,
    hub_draining: false,
    broker_kind: 'pg_notify',
    broker_listener_connected: true,
    broker_publisher_connected: true,
    outbox_relay_running: true,
    outbox_pending_count: 0,
    outbox_dead_letter_count: 0,
    active_connections_total: 8,
    workspace_connections: { 'ws-01': 8 },
    ws_connections: 6,
    sse_connections: 2,
    heartbeat_interval_s: 25.0,
    session_recheck_interval_s: 60.0,
    replay_retention_minutes: 60,
    background_tasks: {
      listener_alive: true,
      ping_alive: true,
      session_check_alive: true,
    },
  },
  request_proxy_check: {
    detected_scheme: 'https',
    is_https: true,
    resolved_client_ip: '127.0.0.1',
    forwarded_proto_present: true,
    forwarded_host: 'localhost',
    origin_header: 'https://localhost:8921',
    origin_allowed_for_ws: true,
    trusted_proxies_configured: false,
    csp_connect_src_allows_wss: true,
    warnings: [],
  },
  sandbox: {
    tier_a_wasm: {
      available: true,
      engine: 'wasmtime',
      max_fuel: 50000000,
      max_memory_bytes: 33554432,
      timeout_ms: 500,
      cached_modules: 3,
    },
    tier_b_nsjail: {
      available: false,
      binary_exists: false,
      binary_owned_by_root: false,
      permissions_safe: false,
      userns_probe_ok: false,
      error_code: 'SANDBOX_UNAVAILABLE_IN_STANDALONE',
      reason: 'nsjail not found',
      seccomp_profile_present: false,
    },
  },
  services: {
    rate_limiter_backend: 'pg',
    valkey_configured: false,
    background_jobs: [{ name: 'auto_archive', interval_seconds: 3600.0, alive: true }],
    mcp_mounted: true,
    mcp_surfaces: ['/mcp/agent', '/mcp/docs', '/mcp/admin'],
    ai_providers: { total: 2, enabled: 1, kinds: ['openai', 'ollama'] },
    auth_cards: { total: 3, enabled: 3, kinds: ['local', 'oidc', 'webauthn'] },
    remote_runners: { connected_count: 1 },
    keyring: { configured: true, source: 'master_kek_env', master_kek_kid: 'kek-active-01' },
  },
  config: [
    {
      key: 'session_idle_timeout_minutes',
      subsystem: 'Auth & AAL2',
      value: 60,
      source: 'default',
      redacted: false,
      notes: 'Idle timeout window',
    },
    {
      key: 'auth_pepper',
      subsystem: 'Auth & AAL2',
      value: '[REDACTED]',
      source: 'env',
      redacted: true,
      notes: 'Server-side pepper',
    },
  ],
  build: {
    version: '2.0.0',
    git_commit: 'ea30b70a',
    build_timestamp: '2026-11-25T00:00:00Z',
    openapi_version: '2.0.0',
    openapi_bundle_hash: 'hash-abc',
    frontend_bundle_hash: 'hash-def',
  },
  subsystems: {
    postgresql_rls: {
      subsystem: 'postgresql_rls',
      name: 'PostgreSQL & RLS Enforcement',
      status: 'healthy',
      description: 'Row-Level Security isolation',
      details: { latency_ms: 1.25, force_rls_verified: true },
    },
    realtime_hub_outbox: {
      subsystem: 'realtime_hub_outbox',
      name: 'Realtime Hub & Outbox Relay',
      status: 'healthy',
      description: 'WebSocket fanout hub',
      details: { hub_running: true, broker_kind: 'pg_notify' },
    },
    job_worker_pool: {
      subsystem: 'job_worker_pool',
      name: 'Background Job Worker Pool',
      status: 'healthy',
      description: 'Task scheduler',
      details: { running: true, total_jobs: 1 },
    },
    wasm_script_sandbox: {
      subsystem: 'wasm_script_sandbox',
      name: 'Wasm Script Sandbox',
      status: 'healthy',
      description: 'Tier A Wasmtime runtime',
      details: { tier_a_wasm_available: true },
    },
    agent_runtime_providers: {
      subsystem: 'agent_runtime_providers',
      name: 'Agent Runtime & AI Providers',
      status: 'healthy',
      description: 'LLM providers',
      details: { total_providers: 2, enabled_providers: 1 },
    },
    remote_runner_fleet: {
      subsystem: 'remote_runner_fleet',
      name: 'Remote Runner Fleet',
      status: 'healthy',
      description: 'Connected runners',
      details: { connected_runners: 1 },
    },
    rate_limiter: {
      subsystem: 'rate_limiter',
      name: 'Sliding Window Rate Limiter',
      status: 'healthy',
      description: 'Token bucket limiter',
      details: { backend: 'pg' },
    },
  },
  postgresql_rls: {
    subsystem: 'postgresql_rls',
    name: 'PostgreSQL & RLS Enforcement',
    status: 'healthy',
    description: 'Row-Level Security isolation',
    details: { latency_ms: 1.25, force_rls_verified: true },
  },
  realtime_hub_outbox: {
    subsystem: 'realtime_hub_outbox',
    name: 'Realtime Hub & Outbox Relay',
    status: 'healthy',
    description: 'WebSocket fanout hub',
    details: { hub_running: true, broker_kind: 'pg_notify' },
  },
  job_worker_pool: {
    subsystem: 'job_worker_pool',
    name: 'Background Job Worker Pool',
    status: 'healthy',
    description: 'Task scheduler',
    details: { running: true, total_jobs: 1 },
  },
  wasm_script_sandbox: {
    subsystem: 'wasm_script_sandbox',
    name: 'Wasm Script Sandbox',
    status: 'healthy',
    description: 'Tier A Wasmtime runtime',
    details: { tier_a_wasm_available: true },
  },
  agent_runtime_providers: {
    subsystem: 'agent_runtime_providers',
    name: 'Agent Runtime & AI Providers',
    status: 'healthy',
    description: 'LLM providers',
    details: { total_providers: 2, enabled_providers: 1 },
  },
  remote_runner_fleet: {
    subsystem: 'remote_runner_fleet',
    name: 'Remote Runner Fleet',
    status: 'healthy',
    description: 'Connected runners',
    details: { connected_runners: 1 },
  },
  rate_limiter: {
    subsystem: 'rate_limiter',
    name: 'Sliding Window Rate Limiter',
    status: 'healthy',
    description: 'Token bucket limiter',
    details: { backend: 'pg' },
  },
};

function getSlice4Mocks(): MockHandlers {
  return {
    'GET /api/v1/auth/me': { json: mockAdminUser },
    'GET /api/v1/users/me': { json: mockAdminUser },
    'GET /api/v1/auth/session': {
      json: {
        authenticated: true,
        aal_level: 2,
        csrf_token: 'csrf-test-token',
        user: mockAdminUser,
      },
    },
    'GET /api/v1/session/csrf': { json: { csrf_token: 'csrf-test-token' } },
    'GET /api/v1/setup/status': { json: { initialized: true, is_initialized: true, requires_setup: false } },
    'GET /api/v1/workspaces/current': {
      json: {
        id: 'ws-1',
        name: '👍kanban',
        slug: 'kanban',
        is_current: true,
      },
    },
    'GET /api/v1/workspaces': {
      json: [
        {
          id: 'ws-1',
          name: '👍kanban',
          slug: 'kanban',
          is_current: true,
        },
      ],
    },
    'GET /api/v1/projects': { json: [{ id: 'proj-1', key: 'KAN', name: 'kanban' }] },
    'GET /api/v1/projects/KAN': { json: [{ id: 'proj-1', key: 'KAN', name: 'kanban' }] },
    'GET /api/v1/notifications': { json: { items: [], total: 0, unread_count: 0 } },
    'GET /api/v1/system/status': {
      json: {
        deployment_mode: 'standalone_embedded_pg',
        persistent_volume: false,
        data_mount_point: '/var/lib/kanban/data',
        data_mount_fstype: 'overlayfs',
        tier_b_sandbox_available: false,
        air_gap_mode: false,
        local_llm_endpoint_host: 'http://host.docker.internal:11434',
        is_server_admin: true,
      },
    },
    'GET /api/v1/admin/standalone/backup-schedule': {
      json: {
        enabled: true,
        interval_hours: 24,
        retention_count: 7,
        last_run_at: '2026-11-24T12:00:00Z',
        next_run_at: '2026-11-25T12:00:00Z',
      },
    },
    'GET /api/v1/admin/standalone/backups': {
      json: [
        {
          filename: 'kanban-backup-20261124-120000.kbbak',
          size_bytes: 1048576,
          created_at: '2026-11-24T12:00:00Z',
        },
      ],
    },
    'GET /api/v1/admin/standalone/compose-export': {
      json: {
        filename: 'docker-compose.yml',
        compose_yaml: 'version: "3.9"\nservices:\n  kanban:\n    image: thumbs-up-kanban:latest\n    ports:\n      - "8921:8921"\n',
        env_template: 'POSTGRES_PASSWORD=secret\nSECRET_KEY=secret\n',
        migration_steps_markdown: '1. Generate secrets\n2. Download backup\n3. Start compose stack',
        single_container_compose_yaml: 'services:\n  standalone:\n    image: thumbs-up-kanban:latest\n',
      },
    },
    'GET /api/v1/admin/diagnostics': {
      json: mockDiagnostics,
    },
    'GET /api/v1/admin/link-auditor/scan': {
      json: {
        flagged_total: 0,
        by_reason: {},
        items: [],
        has_more: false,
      },
    },
    'GET /api/v1/admin/object-links/audits': {
      json: {
        flagged_total: 0,
        by_reason: {},
        items: [],
        has_more: false,
      },
    },
  };
}

test.describe('KAN-422 Slice-4 Simplified Studios Visual Verification', () => {
  test('Capture visual proof across simplified Slice-4 studios and 5 viewports', async ({ page }, testInfo) => {
    const projectName = testInfo.project.name;
    const themes: ('light' | 'dark')[] = projectName === 'desktop' ? ['light', 'dark'] : ['light'];

    await mockApi(page, getSlice4Mocks());

    for (const theme of themes) {
      // 1. Migration Import Studio
      await page.goto('/admin/imports');
      await applyTheme(page, theme);
      await expect(page.locator('h1')).toHaveText('Migration Import Studio');
      await expect(page.getByTestId('mode-paste-btn')).toBeVisible();

      // Click Paste Mode
      await page.getByTestId('mode-paste-btn').click();

      // Expand AdvancedSection to reveal the User Mapping JSON textarea
      await page.getByTestId('advanced-import-options').click();
      await expect(page.getByTestId('import-user-mapping-json')).toBeVisible();

      // Assert CUT controls are absent
      await expect(page.locator('[data-testid="import-batch-size-input"]')).toHaveCount(0);
      await expect(page.locator('[data-testid="import-conflict-strategy-select"]')).toHaveCount(0);
      await expect(page.locator('[data-testid="import-preserve-legacy-uuids-checkbox"]')).toHaveCount(0);

      await page.screenshot({
        path: resolve(SCREENSHOT_DIR, `01-imports-studio-${projectName}-${theme}.png`),
        fullPage: true,
      });

      // 2. Standalone Operations & Backup Panel
      await page.goto('/admin/standalone');
      await applyTheme(page, theme);
      const standaloneDialog = page.getByRole('dialog', { name: 'Standalone deployment status' });
      await expect(standaloneDialog).toBeVisible();
      await expect(page.getByText('System Storage, Backups & Deployment')).toBeVisible();
      await expect(page.getByText('thumbs-up-kanban:latest').first()).toBeVisible();

      // Expand Advanced Technical Details so PostgreSQL 16 details are visible
      await page.getByTestId('standalone-advanced-technical-details').click();
      await expect(page.getByText('PostgreSQL 16 (Unix Domain Socket /var/run/postgresql)')).toBeVisible();

      await page.screenshot({
        path: resolve(SCREENSHOT_DIR, `02-standalone-panel-${projectName}-${theme}.png`),
        fullPage: true,
      });

      // Switch to Docker Compose tab to demonstrate compose export and PostgreSQL 16 runbook
      await page.getByRole('tab', { name: 'Docker Compose Export' }).click();
      await expect(page.getByText('PostgreSQL 16 Promotion Runbook:')).toBeVisible();

      await page.screenshot({
        path: resolve(SCREENSHOT_DIR, `02b-standalone-compose-${projectName}-${theme}.png`),
        fullPage: true,
      });

      // 3. Admin Diagnostics Studio
      await page.goto('/admin/diagnostics');
      await applyTheme(page, theme);
      await expect(page.getByTestId('admin-diagnostics-studio')).toBeVisible();
      await expect(page.getByTestId('summary-card-links')).toContainText('7-class Link Auditor');

      await page.screenshot({
        path: resolve(SCREENSHOT_DIR, `03-diagnostics-studio-${projectName}-${theme}.png`),
        fullPage: true,
      });

      // 4. Link Auditor Studio
      await page.goto('/admin/link-auditor');
      await applyTheme(page, theme);
      await expect(page.getByTestId('link-auditor-studio')).toBeVisible();
      await expect(page.getByText('Invalid Object Link Auditor & Purger')).toBeVisible();

      await page.screenshot({
        path: resolve(SCREENSHOT_DIR, `04-link-auditor-studio-${projectName}-${theme}.png`),
        fullPage: true,
      });
    }
  });
});
