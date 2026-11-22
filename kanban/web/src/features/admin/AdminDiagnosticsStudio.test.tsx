// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router';
import { AdminDiagnosticsStudio } from './AdminDiagnosticsStudio';
import { apiFetch } from '../../api/client';

vi.mock('../../api/client', async () => {
  const actual = await vi.importActual<typeof import('../../api/client')>(
    '../../api/client',
  );
  return {
    ...actual,
    apiFetch: vi.fn(),
    getCsrfToken: vi.fn(() => 'csrf-mock-token'),
  };
});

const mockAdminUser = {
  id: 'usr-admin-1',
  email: 'admin@example.com',
  is_server_admin: true,
  is_workspace_admin: true,
  aal_level: 2,
  auth_aal: 'aal2',
};

const mockNonAdminUser = {
  id: 'usr-member-1',
  email: 'member@example.com',
  is_server_admin: false,
  is_workspace_admin: false,
  workspace_role: 'MEMBER',
  aal_level: 1,
  auth_aal: 'aal1',
};

const mockDiagnosticsData = {
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

function renderStudio(
  initialEntry = '/admin/diagnostics',
  defaultTab?: 'all' | 'health' | 'realtime' | 'runtime' | 'config' | 'links',
) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[initialEntry]}>
        <AdminDiagnosticsStudio {...(defaultTab !== undefined ? { defaultTab } : {})} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function extractPath(args: unknown[]): string {
  if (typeof args[1] === 'string') return args[1];
  if (typeof args[0] === 'string') return args[0];
  return '';
}

describe('AdminDiagnosticsStudio Component', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders NotFoundView when user is non-admin or lacks AAL2', async () => {
    vi.mocked(apiFetch).mockImplementation((...args: unknown[]) => {
      const path = extractPath(args);
      if (path.includes('/api/v1/auth/session/me') || path.includes('/api/v1/auth/me')) {
        return Promise.resolve(mockNonAdminUser);
      }
      return Promise.reject(new Error('unauthorized'));
    });

    renderStudio('/admin/diagnostics');
    await waitFor(() => {
      expect(screen.getByTestId('not-found-view')).toBeDefined();
    });
  });

  it('renders all 7 subsystem health cards and top summary strip for AAL2 admin', async () => {
    vi.mocked(apiFetch).mockImplementation((...args: unknown[]) => {
      const path = extractPath(args);
      if (path.includes('/api/v1/auth/session/me') || path.includes('/api/v1/auth/me')) {
        return Promise.resolve(mockAdminUser);
      }
      if (path.includes('/api/v1/admin/diagnostics')) {
        return Promise.resolve(mockDiagnosticsData);
      }
      return Promise.resolve({});
    });

    renderStudio('/admin/diagnostics', 'health');

    await waitFor(() => {
      expect(screen.getByTestId('admin-diagnostics-studio')).toBeDefined();
    });

    // Verify 4-Card Summary Strip
    expect(screen.getByTestId('summary-card-realtime')).toBeDefined();
    expect(screen.getByTestId('summary-card-runtime')).toBeDefined();
    expect(screen.getByTestId('summary-card-config')).toBeDefined();
    expect(screen.getByTestId('summary-card-links')).toBeDefined();

    // Verify 7 Subsystem health cards
    expect(screen.getByTestId('subsystem-card-postgresql_rls')).toBeDefined();
    expect(screen.getByTestId('subsystem-card-realtime_hub_outbox')).toBeDefined();
    expect(screen.getByTestId('subsystem-card-job_worker_pool')).toBeDefined();
    expect(screen.getByTestId('subsystem-card-wasm_script_sandbox')).toBeDefined();
    expect(screen.getByTestId('subsystem-card-agent_runtime_providers')).toBeDefined();
    expect(screen.getByTestId('subsystem-card-remote_runner_fleet')).toBeDefined();
    expect(screen.getByTestId('subsystem-card-rate_limiter')).toBeDefined();

    // Verify Refresh and WS Probe Buttons
    expect(screen.getByTestId('refresh-diagnostics-btn')).toBeDefined();
    expect(screen.getByTestId('run-ws-ping-btn')).toBeDefined();
    expect(screen.getByTestId('ws-probe-badge')).toBeDefined();
  });

  it('handles tab switching between sections', async () => {
    vi.mocked(apiFetch).mockImplementation((...args: unknown[]) => {
      const path = extractPath(args);
      if (path.includes('/api/v1/auth/session/me') || path.includes('/api/v1/auth/me')) {
        return Promise.resolve(mockAdminUser);
      }
      if (path.includes('/api/v1/admin/diagnostics')) {
        return Promise.resolve(mockDiagnosticsData);
      }
      if (path.includes('/api/v1/admin/link-auditor/scan') || path.includes('/api/v1/admin/object-links/audits')) {
        return Promise.resolve({ flagged_total: 0, by_reason: {}, items: [], has_more: false });
      }
      return Promise.resolve({});
    });

    renderStudio('/admin/diagnostics', 'health');

    await waitFor(() => {
      expect(screen.getByTestId('admin-diagnostics-studio')).toBeDefined();
    });

    // Switch to Realtime tab
    fireEvent.click(screen.getByTestId('tab-realtime'));
    expect(screen.getByTestId('panel-realtime')).toBeDefined();
    expect(screen.getByTestId('run-pg-probe-btn')).toBeDefined();

    // Switch to Runtime tab
    fireEvent.click(screen.getByTestId('tab-runtime'));
    expect(screen.getByTestId('panel-runtime')).toBeDefined();

    // Switch to Config tab
    fireEvent.click(screen.getByTestId('tab-config'));
    expect(screen.getByTestId('panel-config')).toBeDefined();
    expect(screen.getByTestId('config-search-input')).toBeDefined();
    expect(screen.getByTestId('copy-config-btn')).toBeDefined();

    // Switch to Link Inspector tab
    fireEvent.click(screen.getByTestId('tab-links'));
    expect(screen.getByTestId('panel-links')).toBeDefined();
  });

  it('runs WS Ping probe when button is clicked', async () => {
    vi.mocked(apiFetch).mockImplementation((...args: unknown[]) => {
      const path = extractPath(args);
      if (path.includes('/api/v1/auth/session/me') || path.includes('/api/v1/auth/me')) {
        return Promise.resolve(mockAdminUser);
      }
      if (path.includes('/api/v1/admin/diagnostics')) {
        return Promise.resolve(mockDiagnosticsData);
      }
      return Promise.resolve({});
    });

    renderStudio('/admin/diagnostics', 'health');

    await waitFor(() => {
      expect(screen.getByTestId('run-ws-ping-btn')).toBeDefined();
    });

    fireEvent.click(screen.getByTestId('run-ws-ping-btn'));
    await waitFor(() => {
      expect(screen.getByTestId('ws-probe-badge').textContent).toContain('WS Live');
    });
  });

  it('defaults to links tab when navigated via /admin/link-auditor', async () => {
    vi.mocked(apiFetch).mockImplementation((...args: unknown[]) => {
      const path = extractPath(args);
      if (path.includes('/api/v1/auth/session/me') || path.includes('/api/v1/auth/me')) {
        return Promise.resolve(mockAdminUser);
      }
      if (path.includes('/api/v1/admin/diagnostics')) {
        return Promise.resolve(mockDiagnosticsData);
      }
      if (path.includes('/api/v1/admin/link-auditor/scan') || path.includes('/api/v1/admin/object-links/audits')) {
        return Promise.resolve({ flagged_total: 0, by_reason: {}, items: [], has_more: false });
      }
      return Promise.resolve({});
    });

    renderStudio('/admin/link-auditor');

    await waitFor(() => {
      expect(screen.getByTestId('tab-links').className).toContain('admin-diag-tab--active');
      expect(screen.getByTestId('panel-links')).toBeDefined();
    });
  });
});
