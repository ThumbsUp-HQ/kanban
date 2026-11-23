// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import { resolve } from 'node:path';
import { mkdirSync, copyFileSync } from 'node:fs';
import type { Page } from '@playwright/test';
import { test, expect } from './support/test';
import { mockApi, loadFixture, type MockHandlers } from './support/mockApi';

process.env.QA_TICKET_ID = 'KAN-323';
const SCREENSHOT_DIR_323 = resolve(
  import.meta.dirname,
  '../../../docs/qa/KAN-323/screenshots',
);
const SCREENSHOT_DIR_311 = resolve(
  import.meta.dirname,
  '../../../docs/qa/KAN-311/screenshots',
);
mkdirSync(SCREENSHOT_DIR_323, { recursive: true });
mkdirSync(SCREENSHOT_DIR_311, { recursive: true });

async function applyTheme(page: Page, theme: 'light' | 'dark'): Promise<void> {
  await page.evaluate((t) => {
    document.documentElement.setAttribute('data-theme', t);
    try {
      localStorage.setItem('kb:theme', t);
    } catch {
      // ignore localStorage on cross-origin or restricted frames
    }
  }, theme);
  await page.waitForTimeout(100);
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
    code_heads: ['rev_head_01'],
    db_heads: ['rev_head_01'],
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
    git_commit: 'c116ba38',
    build_timestamp: '2026-11-22T10:00:00Z',
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
  },
};

const mockFlowAnalytics = {
  cfd: {
    states: [
      { id: 's1', name: 'Backlog', state_group: 'backlog', color_hex: '#94a3b8', sort_order: 1 },
      { id: 's2', name: 'Todo', state_group: 'unstarted', color_hex: '#64748b', sort_order: 2 },
      { id: 's3', name: 'In Progress', state_group: 'started', color_hex: '#3b82f6', sort_order: 3 },
      { id: 's4', name: 'Done', state_group: 'completed', color_hex: '#10b981', sort_order: 4 },
    ],
    state_groups: ['backlog', 'unstarted', 'started', 'completed', 'cancelled'],
    points: [
      { date: '2026-11-18', backlog: 10, unstarted: 8, started: 4, completed: 5, cancelled: 0, total: 27 },
      { date: '2026-11-19', backlog: 8, unstarted: 7, started: 6, completed: 8, cancelled: 0, total: 29 },
      { date: '2026-11-20', backlog: 6, unstarted: 5, started: 8, completed: 14, cancelled: 0, total: 33 },
      { date: '2026-11-21', backlog: 4, unstarted: 3, started: 7, completed: 21, cancelled: 0, total: 35 },
      { date: '2026-11-22', backlog: 2, unstarted: 2, started: 5, completed: 30, cancelled: 0, total: 39 },
    ],
  },
  cycle_lead_time: {
    points: [
      {
        issue_id: 'i1',
        issue_key: 'KAN-1',
        title: 'Multi-Card Authentication Studio',
        cycle_time_days: 1.5,
        lead_time_days: 3.0,
        completed_at: '2026-11-19T10:00:00Z',
      },
      {
        issue_id: 'i2',
        issue_key: 'KAN-2',
        title: 'Master-Detail Issue Navigator',
        cycle_time_days: 2.0,
        lead_time_days: 4.5,
        completed_at: '2026-11-20T12:00:00Z',
      },
      {
        issue_id: 'i3',
        issue_key: 'KAN-3',
        title: 'Unified Admin Diagnostics Studio',
        cycle_time_days: 1.8,
        lead_time_days: 3.2,
        completed_at: '2026-11-21T15:00:00Z',
      },
    ],
    cycle_time_percentiles: { p50: 1.8, p85: 2.0, p95: 2.0 },
    lead_time_percentiles: { p50: 3.2, p85: 4.5, p95: 4.5 },
    total_completed_in_window: 3,
  },
  aging_wip: {
    active_issues: [
      {
        issue_id: 'i4',
        issue_key: 'KAN-323',
        title: 'Full Documentation Review & Offline Docs Sync Epic',
        state_id: 's3',
        state_name: 'In Progress',
        state_color_hex: '#3b82f6',
        state_entered_at: '2026-11-22T20:00:00Z',
        first_started_at: '2026-11-22T20:00:00Z',
        age_in_current_state_hours: 6.5,
        total_wip_hours: 6.5,
      },
    ],
    column_thresholds: {
      s3: {
        state_id: 's3',
        state_name: 'In Progress',
        state_group: 'started',
        color_hex: '#3b82f6',
        p50_hours: 24.0,
        p85_hours: 40.0,
        p95_hours: 72.0,
        sample_size: 10,
      },
    },
    total_active_wip: 1,
  },
  monte_carlo: {
    trials: 10000,
    historical_daily_throughput: [1, 2, 0, 1, 3],
    average_daily_throughput: 1.4,
    how_many: {
      horizon_days: 14,
      p50: 18,
      p85: 12,
      p95: 9,
      distribution: { '9': 500, '12': 3500, '18': 5000 },
    },
    when: {
      target_items: 20,
      p50_days: 15,
      p50_date: '2026-12-07',
      p85_days: 22,
      p85_date: '2026-12-14',
      p95_days: 28,
      p95_date: '2026-12-20',
      distribution: { '15': 5000, '22': 3500, '28': 1500 },
    },
  },
};

const mockAboutData = {
  platform: '👍kanban',
  slug: 'thumbs-up-kanban',
  tagline: 'The difference between a swarm and an Agile team is a kanban.',
  version: '0.2.1220',
  license_spdx: 'Apache-2.0',
  git_commit: 'b308d37655cb',
  build_timestamp: '2026-11-22T22:13:07Z',
  openapi_version: '0.2.1220',
  openapi_bundle_hash: 'd64700b6562fe939bb1f32a7620eb500',
  frontend_bundle_hash: 'e8992ba0189a0398bb27918cae883719',
  api_docs_urls: {
    swagger_ui: '/api/docs',
    redoc: '/api/redoc',
    openapi_json: '/api/openapi.json',
  },
  license: 'Apache License Version 2.0',
  notice: 'Third-Party Software Notices',
  sbom_summary: {
    total_components: 121,
    python_components: 54,
    web_components: 67,
    permissive_count: 121,
    allowlisted_count: 121,
    unknown_count: 0,
    deny_count: 0,
  },
  components: [
    {
      name: 'fastapi',
      version: '0.115.0',
      ecosystem: 'python',
      purl: 'pkg:pypi/fastapi@0.115.0',
      license: 'MIT',
      license_verdict: 'ALLOW',
      scope: 'required',
      description: 'FastAPI web framework',
    },
  ],
};

function getCommonMocks(): MockHandlers {
  const projectKan = {
    id: 'proj-kan-1',
    identifier: 'KAN',
    name: 'Platform Core',
    description_markdown: 'Core platform engineering workspace',
    modules_enabled: true,
    auto_archive_days: 90,
    capabilities: ['VIEW', 'COMMENT', 'EDIT', 'ADMIN', 'PROJECT_ADMIN'],
    is_project_admin: true,
    project_role: 'ADMIN',
  };

  const mockPriorities = {
    items: [
      { id: 'prio-urgent', slug: 'urgent', label: 'Urgent', emoji: '🔥', sort_order: 1 },
      { id: 'prio-high', slug: 'high', label: 'High', emoji: '⚡', sort_order: 2 },
      { id: 'prio-medium', slug: 'medium', label: 'Medium', emoji: '🔹', sort_order: 3 },
      { id: 'prio-low', slug: 'low', label: 'Low', emoji: '🔽', sort_order: 4 },
    ],
  };

  const mockStates = [
    { id: 'st-backlog', name: 'Backlog', group: 'backlog', sort_order: 1 },
    { id: 'st-todo', name: 'To Do', group: 'unstarted', sort_order: 2 },
    { id: 'st-in-progress', name: 'In Progress', group: 'started', sort_order: 3 },
    { id: 'st-done', name: 'Done', group: 'completed', sort_order: 4 },
  ];

  const mockCycles = [
    { id: 'cycle-1', name: 'Cycle 1 (Active)', status: 'active', start_date: '2026-03-01', end_date: '2026-03-14' },
  ];

  const mockModules = [
    { id: 'mod-1', name: 'Documentation & Architecture', status: 'in_progress', start_date: '2026-03-01', target_date: '2026-03-31' },
  ];

  const mockIssues = {
    items: [
      {
        id: 'iss-1',
        key: 'KAN-142',
        project_key: 'KAN',
        summary: 'Hardened Multi-Card Authentication Studio',
        state: { id: 'st-in-progress', name: 'In Progress', group: 'started' },
        priority: { id: 'prio-urgent', slug: 'urgent', label: 'Urgent', emoji: '🔥', sort_order: 1 },
        cycle_id: 'cycle-1',
        cycle: { id: 'cycle-1', name: 'Cycle 1 (Active)' },
        module_ids: ['mod-1'],
        modules: [{ id: 'mod-1', name: 'Documentation & Architecture' }],
        due_date: '2026-03-14',
        capabilities: ['VIEW', 'COMMENT', 'EDIT', 'ADMIN'],
      },
      {
        id: 'iss-2',
        key: 'KAN-323',
        project_key: 'KAN',
        summary: 'Full Documentation Review & Offline Docs Sync Epic',
        state: { id: 'st-in-progress', name: 'In Progress', group: 'started' },
        priority: { id: 'prio-high', slug: 'high', label: 'High', emoji: '⚡', sort_order: 2 },
        cycle_id: 'cycle-1',
        cycle: { id: 'cycle-1', name: 'Cycle 1 (Active)' },
        module_ids: ['mod-1'],
        modules: [{ id: 'mod-1', name: 'Documentation & Architecture' }],
        due_date: '2026-03-28',
        capabilities: ['VIEW', 'COMMENT', 'EDIT', 'ADMIN'],
      },
    ],
    total: 2,
  };

  return {
    'GET /api/v1/me': { json: mockAdminUser },
    'GET /api/v1/auth/me': { json: mockAdminUser },
    'GET /api/v1/users/me': { json: mockAdminUser },
    'GET /api/v1/auth/session/me': { json: mockAdminUser },
    'GET /api/v1/auth/session': {
      json: {
        authenticated: true,
        aal_level: 2,
        csrf_token: 'test-csrf-token-wiki',
        user: mockAdminUser,
      },
    },
    'GET /api/v1/session/csrf': { json: { csrf_token: 'test-csrf-token-wiki' } },
    'GET /api/v1/setup/status': { json: { initialized: true, is_initialized: true, requires_setup: false } },
    'GET /api/v1/system/status': { json: loadFixture('system-status-prod') },
    'GET /api/v1/system/about': { json: mockAboutData },
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
    'GET /api/v1/projects': { json: [projectKan] },
    'GET /api/v1/projects/KAN': { json: projectKan },
    'GET /api/v1/projects/KAN/cycles': { json: mockCycles },
    'GET /api/v1/projects/KAN/modules': { json: mockModules },
    'GET /api/v1/projects/KAN/states': { json: mockStates },
    'GET /api/v1/projects/KAN/priorities': { json: mockPriorities },
    'GET /api/v1/projects/KAN/views': { json: [] },
    'GET /api/v1/projects/KAN/custom-fields': { json: [] },
    'GET /api/v1/projects/KAN/labels': { json: [] },
    'GET /api/v1/projects/KAN/members': { json: [] },
    'GET /api/v1/projects/KAN/issues': { json: mockIssues },
    'GET /api/v1/issues': { json: mockIssues },
    'GET /api/v1/issues/:id': (req) => {
      const found = mockIssues.items.find(
        (i) => i.key === req.params.id || i.id === req.params.id,
      );
      return { json: found ?? mockIssues.items[0] };
    },
    'GET /api/v1/issues/:id/comments': { json: { items: [], total: 0 } },
    'GET /api/v1/issues/:id/activity': { json: { items: [], total: 0 } },
    'GET /api/v1/issues/:id/subscription': { json: { subscribed: false } },
    'GET /api/v1/issues/:id/transitions': { json: [] },
    'GET /api/v1/objects/:id/canonical-url': {
      json: { canonical_url: 'http://127.0.0.1:4173/projects/KAN/issues/KAN-142' },
    },
    'GET /api/v1/projects/KAN/analytics/flow': { json: mockFlowAnalytics },
    'GET /api/v1/cycles/cycle-1/burndown': { json: { points: [] } },
    'GET /api/v1/notifications': { json: { items: [], unread_count: 0 } },
    'GET /api/v1/notifications/unread-count': { json: { unread_count: 0 } },
    'GET /api/v1/objects/:id/access': { json: loadFixture('access-project-kan') },
    'GET /api/v1/admin/diagnostics': { json: mockDiagnostics },
    'POST /api/v1/admin/diagnostics/probes/realtime': {
      json: {
        success: true,
        db_latency_ms: 1.15,
        notify_rtt_ms: 2.3,
        message: 'PG_NOTIFY loopback probe healthy',
      },
    },
    'GET /api/v1/admin/link-auditor/scan': {
      json: { flagged_total: 0, by_reason: {}, items: [], has_more: false },
    },
    'GET /api/v1/admin/object-links/audits': {
      json: { flagged_total: 0, by_reason: {}, items: [], has_more: false },
    },
  };
}

test.describe('Documentation & Visual Proof Screenshot Capture (KAN-323 / KAN-311)', () => {
  test('01: desktop light - Docs Center Overview', async ({ page }: { page: Page }) => {
    await mockApi(page, getCommonMocks());
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto('/docs');
    await applyTheme(page, 'light');
    await expect(page.locator('[data-testid="docs-center-page"]')).toBeVisible();

    const shot323 = resolve(SCREENSHOT_DIR_323, '1440x900-desktop-light.png');
    await page.screenshot({ path: shot323, fullPage: false });
    copyFileSync(shot323, resolve(SCREENSHOT_DIR_311, '1440x900-desktop-light.png'));
  });

  test('02: desktop dark - Docs Center Chapter with Media', async ({ page }: { page: Page }) => {
    await mockApi(page, getCommonMocks());
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto('/docs/enterprise-whitespace-and-kanban-board');
    await applyTheme(page, 'dark');
    await expect(page.locator('[data-testid="docs-center-page"]')).toBeVisible();

    const shot323 = resolve(SCREENSHOT_DIR_323, '1440x900-desktop-dark.png');
    await page.screenshot({ path: shot323, fullPage: false });
    copyFileSync(shot323, resolve(SCREENSHOT_DIR_311, '1440x900-desktop-dark.png'));
  });

  test('03: tablet - Master-Detail Issue Navigator', async ({ page }: { page: Page }) => {
    await mockApi(page, getCommonMocks());
    await page.setViewportSize({ width: 768, height: 1024 });
    await page.goto('/projects/KAN/issues?layout=list');
    await applyTheme(page, 'light');
    await expect(page.locator('[data-issue-key="KAN-142"]')).toBeVisible();

    const shot323 = resolve(SCREENSHOT_DIR_323, '768x1024-tablet.png');
    await page.screenshot({ path: shot323, fullPage: false });
    copyFileSync(shot323, resolve(SCREENSHOT_DIR_311, '768x1024-tablet.png'));
  });

  test('04: mobile portrait - Flow Telemetry Studio & Analytics', async ({ page }: { page: Page }) => {
    await mockApi(page, getCommonMocks());
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto('/projects/KAN/analytics');
    await applyTheme(page, 'light');
    await page.waitForTimeout(500);

    const shot323 = resolve(SCREENSHOT_DIR_323, '390x844-mobile-portrait.png');
    await page.screenshot({ path: shot323, fullPage: false });
    copyFileSync(shot323, resolve(SCREENSHOT_DIR_311, '390x844-mobile-portrait.png'));
  });

  test('05: mobile landscape - Unified Admin Diagnostics Studio', async ({ page }: { page: Page }) => {
    await mockApi(page, getCommonMocks());
    await page.setViewportSize({ width: 844, height: 390 });
    await page.goto('/admin/diagnostics');
    await applyTheme(page, 'light');
    await page.waitForTimeout(500);

    const shot323 = resolve(SCREENSHOT_DIR_323, '844x390-mobile-landscape.png');
    await page.screenshot({ path: shot323, fullPage: false });
    copyFileSync(shot323, resolve(SCREENSHOT_DIR_311, '844x390-mobile-landscape.png'));
  });
});
