// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import React from 'react';
import fs from 'node:fs';
import path from 'node:path';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
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

    // Switch to All tab
    fireEvent.click(screen.getByTestId('tab-all'));
    expect(screen.getByTestId('panel-realtime')).toBeDefined();

    // Switch back to Health tab
    fireEvent.click(screen.getByTestId('tab-health'));
    expect(screen.getByTestId('subsystem-card-postgresql_rls')).toBeDefined();
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

    class MockWebSocket {
      static OPEN = 1;
      readyState = 1;
      onopen: (() => void) | null = null;
      onmessage: ((evt: { data: string }) => void) | null = null;
      onerror: (() => void) | null = null;
      close = vi.fn();
      constructor() {
        setTimeout(() => {
          this.onopen?.();
        }, 10);
      }
      send() {
        setTimeout(() => {
          this.onmessage?.({ data: JSON.stringify({ type: 'pong' }) });
        }, 10);
      }
    }
    vi.stubGlobal('WebSocket', MockWebSocket);

    renderStudio('/admin/diagnostics', 'health');

    await waitFor(() => {
      expect(screen.getByTestId('run-ws-ping-btn')).toBeDefined();
    });

    fireEvent.click(screen.getByTestId('run-ws-ping-btn'));
    await waitFor(() => {
      expect(screen.getByTestId('ws-probe-badge').textContent).toContain('WS Live');
    });
    vi.unstubAllGlobals();
  });

  it('reports genuine WS Disconnected / Error when WebSocket probe fails', async () => {
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

    class FailingWebSocket {
      static OPEN = 1;
      readyState = 3;
      onopen: (() => void) | null = null;
      onmessage: ((evt: { data: string }) => void) | null = null;
      onerror: (() => void) | null = null;
      close = vi.fn();
      constructor() {
        setTimeout(() => {
          this.onerror?.();
        }, 10);
      }
      send() {
        void 0;
      }
    }
    vi.stubGlobal('WebSocket', FailingWebSocket);

    renderStudio('/admin/diagnostics', 'health');

    await waitFor(() => {
      expect(screen.getByTestId('run-ws-ping-btn')).toBeDefined();
    });

    fireEvent.click(screen.getByTestId('run-ws-ping-btn'));
    await waitFor(() => {
      expect(screen.getByTestId('ws-probe-badge').textContent).toContain('WS Disconnected / Error');
    });
    vi.unstubAllGlobals();
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

  it('handles refresh diagnostics and PG LISTEN/NOTIFY probe success and failure', async () => {
    let probeSuccess = true;
    vi.mocked(apiFetch).mockImplementation((...args: unknown[]) => {
      const path = extractPath(args);
      if (path.includes('/api/v1/auth/session/me') || path.includes('/api/v1/auth/me')) {
        return Promise.resolve(mockAdminUser);
      }
      if (path.includes('/api/v1/admin/diagnostics/probes/realtime')) {
        if (probeSuccess) {
          return Promise.resolve({ success: true, db_latency_ms: 1.5, notify_rtt_ms: 3.2, message: 'PG NOTIFY OK' });
        }
        return Promise.reject(new Error('Broker disconnected'));
      }
      if (path.includes('/api/v1/admin/diagnostics')) {
        return Promise.resolve(mockDiagnosticsData);
      }
      return Promise.resolve({});
    });

    renderStudio('/admin/diagnostics', 'realtime');

    await waitFor(() => {
      expect(screen.getByTestId('run-pg-probe-btn')).toBeDefined();
    });

    // Test PG Probe Success
    fireEvent.click(screen.getByTestId('run-pg-probe-btn'));
    await waitFor(() => {
      expect(screen.getByTestId('probe-alert').textContent).toContain('PG NOTIFY OK');
    });

    // Test PG Probe Failure
    probeSuccess = false;
    fireEvent.click(screen.getByTestId('run-pg-probe-btn'));
    await waitFor(() => {
      expect(screen.getByTestId('probe-alert').textContent).toContain('Broker disconnected');
    });

    // Test Refresh diagnostics button
    fireEvent.click(screen.getByTestId('refresh-diagnostics-btn'));
  });

  it('handles config searching, subsystem filtering, and safe JSON copying', async () => {
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

    const writeTextMock = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, {
      clipboard: {
        writeText: writeTextMock,
      },
    });

    renderStudio('/admin/diagnostics', 'config');

    await waitFor(() => {
      expect(screen.getByTestId('panel-config')).toBeDefined();
    });

    // Search filter
    const searchInput = screen.getByTestId('config-search-input');
    fireEvent.change(searchInput, { target: { value: 'pepper' } });
    expect(screen.getByText('auth_pepper')).toBeDefined();

    // Subsystem filter
    const select = screen.getByTestId('config-subsystem-select');
    fireEvent.change(select, { target: { value: 'Auth & AAL2' } });

    // Copy Safe JSON Summary
    const copyBtn = screen.getByTestId('copy-config-btn');
    fireEvent.click(copyBtn);
    expect(writeTextMock).toHaveBeenCalled();
  });

  it('renders all sections when defaultTab is "all"', async () => {
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

    renderStudio('/admin/diagnostics', 'all');

    await waitFor(() => {
      expect(screen.getByTestId('admin-diagnostics-studio')).toBeDefined();
      expect(screen.getByTestId('panel-realtime')).toBeDefined();
      expect(screen.getByTestId('panel-runtime')).toBeDefined();
      expect(screen.getByTestId('panel-config')).toBeDefined();
      expect(screen.getByTestId('panel-links')).toBeDefined();
    });
  });

  it('renders loading state when diagnostics is loading', async () => {
    vi.mocked(apiFetch).mockImplementation((...args: unknown[]) => {
      const path = extractPath(args);
      if (path.includes('/api/v1/auth/session/me') || path.includes('/api/v1/auth/me')) {
        return Promise.resolve(mockAdminUser);
      }
      if (path.includes('/api/v1/admin/diagnostics')) {
        return new Promise<unknown>(() => {
          void 0;
        }); // never resolves
      }
      return Promise.resolve({});
    });

    renderStudio('/admin/diagnostics', 'health');

    await waitFor(() => {
      expect(screen.getByText(/Loading system diagnostics/i)).toBeDefined();
    });
  });

  it('renders root process, bare metal/podman, and degraded/unhealthy subsystem cards', async () => {
    const customDiagnostics = {
      ...mockDiagnosticsData,
      runtime_and_container: {
        ...mockDiagnosticsData.runtime_and_container,
        is_non_root: false,
        container_runtime: 'podman',
      },
      subsystems: {
        ...mockDiagnosticsData.subsystems,
        postgresql_rls: {
          subsystem: 'postgresql_rls',
          name: 'PostgreSQL & RLS Enforcement',
          status: 'degraded',
          description: 'High latency',
          details: { latency_ms: 120 },
        },
        realtime_hub_outbox: {
          subsystem: 'realtime_hub_outbox',
          name: 'Realtime Hub & Outbox Relay',
          status: 'unhealthy',
          description: 'Outbox backlog',
          details: { dead_letters: 5 },
        },
      },
    };

    vi.mocked(apiFetch).mockImplementation((...args: unknown[]) => {
      const path = extractPath(args);
      if (path.includes('/api/v1/auth/session/me') || path.includes('/api/v1/auth/me')) {
        return Promise.resolve(mockAdminUser);
      }
      if (path.includes('/api/v1/admin/diagnostics')) {
        return Promise.resolve(customDiagnostics);
      }
      return Promise.resolve({});
    });

    renderStudio('/admin/diagnostics', 'health');

    await waitFor(() => {
      expect(screen.getByText('Podman Container')).toBeDefined();
      expect(screen.getByText('Root Process')).toBeDefined();
      expect(screen.getByText('DEGRADED')).toBeDefined();
      expect(screen.getByText('UNHEALTHY')).toBeDefined();
    });
  });

  it('handles WebSocket probe timeout and non-pong or invalid message payload', async () => {
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

    class TimeoutWebSocket {
      static OPEN = 1;
      static CONNECTING = 0;
      readyState = 0;
      onopen: (() => void) | null = null;
      onmessage: ((evt: { data: unknown }) => void) | null = null;
      onerror: (() => void) | null = null;
      close = vi.fn(() => {
        this.readyState = 3;
      });
      constructor() {
        setTimeout(() => {
          this.readyState = 1;
          this.onopen?.();
          // send invalid non-string, invalid json, and non-pong
          this.onmessage?.({ data: 12345 });
          this.onmessage?.({ data: 'not-valid-json' });
          this.onmessage?.({ data: JSON.stringify({ type: 'hello' }) });
        }, 10);
      }
      send() {
        void 0;
      }
    }
    vi.stubGlobal('WebSocket', TimeoutWebSocket);

    renderStudio('/admin/diagnostics', 'health');

    await waitFor(() => {
      expect(screen.getByTestId('run-ws-ping-btn')).toBeDefined();
    });

    fireEvent.click(screen.getByTestId('run-ws-ping-btn'));

    // Wait for the 1500ms timeout
    await waitFor(
      () => {
        expect(screen.getByTestId('ws-probe-badge').textContent).toContain('WS Disconnected / Error');
      },
      { timeout: 3000 },
    );

    vi.unstubAllGlobals();
  });

  it('handles probe success=false, empty err message, https wss scheme, bare metal runtime, and ws throws', async () => {
    const customDiagnostics = {
      ...mockDiagnosticsData,
      realtime: {
        ...mockDiagnosticsData.realtime,
        active_connections_total: undefined as unknown as number,
        heartbeat_interval_s: undefined as unknown as number,
        broker_kind: undefined as unknown as string,
        outbox_pending_count: undefined as unknown as number,
        outbox_dead_letter_count: undefined as unknown as number,
      },
      storage: {
        ...mockDiagnosticsData.storage,
        directories: undefined as unknown as typeof mockDiagnosticsData.storage.directories,
      },
      runtime_and_container: {
        ...mockDiagnosticsData.runtime_and_container,
        container_runtime: 'bare_metal',
      },
    };

    let probeMode = 'pending_then_success_false';
    let resolveProbe: (v: unknown) => void = () => {
      void 0;
    };
    vi.mocked(apiFetch).mockImplementation((...args: unknown[]) => {
      const path = extractPath(args);
      if (path.includes('/api/v1/auth/session/me') || path.includes('/api/v1/auth/me')) {
        return Promise.resolve(mockAdminUser);
      }
      if (path.includes('/api/v1/admin/diagnostics/probes/realtime')) {
        if (probeMode === 'pending_then_success_false') {
          return new Promise((res) => {
            resolveProbe = () => {
              res({ success: false, db_latency_ms: 0, message: 'Notify failed' });
            };
          });
        }
        return Promise.reject(new Error(''));
      }
      if (path.includes('/api/v1/admin/diagnostics')) {
        return Promise.resolve(customDiagnostics);
      }
      return Promise.resolve({});
    });

    // Test https protocol for wss:
    const origLocation = window.location;
    delete (window as unknown as { location?: unknown }).location;
    const mockLoc = Object.create(origLocation) as Location;
    Object.defineProperty(mockLoc, 'protocol', { value: 'https:', configurable: true });
    (window as unknown as { location: unknown }).location = mockLoc;

    // Make WebSocket constructor throw
    vi.stubGlobal('WebSocket', function MockThrowingWS() {
      throw new Error('WebSocket blocked');
    });

    renderStudio('/admin/diagnostics', 'all');

    await waitFor(() => {
      expect(screen.getByText('Bare Metal Host')).toBeDefined();
    });

    // Click WS probe which throws
    fireEvent.click(screen.getByTestId('run-ws-ping-btn'));
    await waitFor(() => {
      expect(screen.getByTestId('ws-probe-badge').textContent).toContain('WS Disconnected / Error');
    });

    // Trigger realtime probe and observe "Testing..." pending state
    fireEvent.click(screen.getByTestId('run-pg-probe-btn'));
    await waitFor(() => {
      expect(screen.getByText('Testing...')).toBeDefined();
    });
    resolveProbe(null);

    await waitFor(() => {
      expect(screen.getByTestId('probe-alert').textContent).toContain('Notify failed');
    });

    // Trigger realtime probe with empty err.message
    probeMode = 'empty_error';
    fireEvent.click(screen.getByTestId('run-pg-probe-btn'));
    await waitFor(() => {
      expect(screen.getByTestId('probe-alert').textContent).toContain('Realtime probe execution failed');
    });

    vi.unstubAllGlobals();
    delete (window as unknown as { location?: unknown }).location;
    (window as unknown as { location: unknown }).location = origLocation;
  });

  describe('KAN-524: FieldHelpHint on Subsystem Health Header and Dark Mode Tab Contrast', () => {
    beforeEach(() => {
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
    });

    it('renders FieldHelpHint triggers on System Summary and Subsystem Health headers with required ARIA attributes', async () => {
      renderStudio('/admin/diagnostics', 'health');

      await waitFor(() => {
        expect(screen.getByTestId('system-summary-help')).toBeDefined();
        expect(screen.getByTestId('subsystem-health-help')).toBeDefined();
      });

      const summaryTrigger = screen.getByTestId('system-summary-help');
      expect(summaryTrigger.getAttribute('aria-label')).toBe('Help for System Operational Summary');
      expect(summaryTrigger.getAttribute('aria-haspopup')).toBe('dialog');
      expect(summaryTrigger.getAttribute('aria-expanded')).toBe('false');

      const trigger = screen.getByTestId('subsystem-health-help');
      expect(trigger.getAttribute('aria-label')).toBe('Help for Subsystem Operational Health');
      expect(trigger.getAttribute('aria-haspopup')).toBe('dialog');
      expect(trigger.getAttribute('aria-expanded')).toBe('false');
      expect(trigger.className).toContain('field-help-hint');
    });

    it('opens popover dialog on keyboard focus and closes on Escape with thresholds and remediation', async () => {
      renderStudio('/admin/diagnostics', 'health');

      await waitFor(() => {
        expect(screen.getByTestId('subsystem-health-help')).toBeDefined();
      });

      const trigger = screen.getByTestId('subsystem-health-help');

      // Focus opens the popover
      act(() => {
        trigger.focus();
      });

      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeDefined();
      });

      const dialog = screen.getByRole('dialog');
      expect(dialog.getAttribute('aria-label')).toBe('Subsystem Operational Health');
      expect(dialog.textContent).toContain('Real-time operational health telemetry across core subsystems');
      expect(dialog.textContent).toContain('OK (<100ms)');
      expect(dialog.textContent).toContain('DEGRADED');
      expect(dialog.textContent).toContain('DOWN');
      expect(dialog.textContent).toContain('Remediation: Run WS Ping / Refresh Diagnostics');

      // Verify doc link href
      const docLink = screen.getByTestId('subsystem-health-help-doc-link');
      expect(docLink.getAttribute('href')).toBe('/docs/admin-diagnostics-and-link-inspector-studio');
      expect(trigger.getAttribute('aria-expanded')).toBe('true');

      // Escape closes the popover
      act(() => {
        fireEvent.keyDown(trigger, { key: 'Escape' });
      });
      expect(screen.queryByTestId('subsystem-health-help-popover')).toBeNull();
      expect(trigger.getAttribute('aria-expanded')).toBe('false');
    });

    it('opens system-summary-help popover and displays connection thresholds and remediation', async () => {
      renderStudio('/admin/diagnostics', 'health');

      await waitFor(() => {
        expect(screen.getByTestId('system-summary-help')).toBeDefined();
      });

      const trigger = screen.getByTestId('system-summary-help');

      act(() => {
        trigger.focus();
      });

      await waitFor(() => {
        expect(screen.getByTestId('system-summary-help-popover')).toBeDefined();
      });

      const popover = screen.getByTestId('system-summary-help-popover');
      expect(popover.textContent).toContain('System Operational Summary');
      expect(popover.textContent).toContain('OK (<100ms)');
      expect(popover.textContent).toContain('DEGRADED');
      expect(popover.textContent).toContain('DOWN');
      expect(popover.textContent).toContain('Remediation: Run WS Ping / Refresh Diagnostics');

      act(() => {
        fireEvent.keyDown(trigger, { key: 'Escape' });
      });
      expect(screen.queryByTestId('system-summary-help-popover')).toBeNull();
    });

    it('renders FieldHelpHint and active tab across Light and Dark themes', async () => {
      for (const theme of ['light', 'dark']) {
        document.documentElement.setAttribute('data-theme', theme);
        const { unmount } = renderStudio('/admin/diagnostics', 'health');

        await waitFor(() => {
          expect(screen.getByTestId('subsystem-health-help')).toBeDefined();
        });

        const activeTab = screen.getByTestId('tab-health');
        expect(activeTab.className).toContain('admin-diag-tab--active');
        expect(activeTab.getAttribute('aria-selected')).toBe('true');

        unmount();
      }
      document.documentElement.removeAttribute('data-theme');
    });

    it('verifies CSS rules for field-help-hint margin and active tab dark mode token', () => {
      const cssPath = path.resolve(__dirname, 'AdminDiagnosticsStudio.css');
      const cssContent = fs.readFileSync(cssPath, 'utf-8');

      // Adjacent inline (?) with margin-left: 0
      expect(cssContent).toContain('.admin-diag-panel-title .field-help-hint');
      expect(cssContent).toMatch(
        /\.admin-diag-panel-title\s+\.field-help-hint\s*\{[^}]*margin-left:\s*0;/,
      );

      // Dark mode active tab uses var(--badge-fg)
      expect(cssContent).toContain(":root[data-theme='dark'] .admin-diag-tab--active");
      expect(cssContent).toContain('@media (prefers-color-scheme: dark)');
      expect(cssContent).toMatch(
        /\[data-theme=['"]dark['"]\][\s\S]*?\.admin-diag-tab--active[\s\S]*?\{[^}]*color:\s*var\(--badge-fg\);/,
      );
    });

    it('covers directory statuses (Read-Only and Missing), missing config, and refreshing button state', async () => {
      const directoryBranchDiagnostics = {
        ...mockDiagnosticsData,
        config: [],
        storage: {
          ...mockDiagnosticsData.storage,
          directories: [
            {
              name: 'readonly_dir',
              path: '/var/lib/kanban/data/readonly',
              exists: true,
              writable: false,
              free_bytes: 10737418240,
              total_bytes: 53687091200,
            },
            {
              name: 'missing_dir',
              path: '/var/lib/kanban/data/missing',
              exists: false,
              writable: false,
              free_bytes: 0,
              total_bytes: 0,
            },
          ],
        },
      };

      vi.mocked(apiFetch).mockImplementation((...args: unknown[]) => {
        const p = extractPath(args);
        if (p.includes('/api/v1/auth/session/me') || p.includes('/api/v1/auth/me')) {
          return Promise.resolve(mockAdminUser);
        }
        if (p.includes('/api/v1/admin/diagnostics')) {
          return Promise.resolve(directoryBranchDiagnostics);
        }
        return Promise.resolve({});
      });

      renderStudio('/admin/diagnostics', 'runtime');

      await waitFor(() => {
        expect(screen.getByText('Read-Only')).toBeDefined();
        expect(screen.getByText('Missing')).toBeDefined();
      });

      // Also verify config card with empty config falls back to 0
      expect(screen.getByTestId('summary-card-config').textContent).toContain('0 Settings');
    });

    it('covers isFetching state showing Refreshing... on button', async () => {
      vi.mocked(apiFetch).mockImplementation((...args: unknown[]) => {
        const p = extractPath(args);
        if (p.includes('/api/v1/auth/session/me') || p.includes('/api/v1/auth/me')) {
          return Promise.resolve(mockAdminUser);
        }
        if (p.includes('/api/v1/admin/diagnostics')) {
          return Promise.resolve(mockDiagnosticsData);
        }
        return Promise.resolve({});
      });

      renderStudio('/admin/diagnostics', 'health');

      await waitFor(() => {
        expect(screen.getByTestId('refresh-diagnostics-btn')).toBeDefined();
      });

      let finishRefetch: () => void = () => {
        void 0;
      };
      const pendingPromise = new Promise((res) => {
        finishRefetch = () => {
          res(mockDiagnosticsData);
        };
      });
      vi.mocked(apiFetch).mockImplementation((...args: unknown[]) => {
        const p = extractPath(args);
        if (p.includes('/api/v1/admin/diagnostics')) {
          return pendingPromise;
        }
        return Promise.resolve(mockAdminUser);
      });

      fireEvent.click(screen.getByTestId('refresh-diagnostics-btn'));

      await waitFor(() => {
        expect(screen.getByTestId('refresh-diagnostics-btn').textContent).toContain('Refreshing...');
      });

      finishRefetch();
      await waitFor(() => {
        expect(screen.getByTestId('refresh-diagnostics-btn').textContent).toContain('Refresh Diagnostics');
      });
    });

    it('standardizes header action cadence: status badge -> secondary action -> primary action CTA -> studio doc link (KAN-532)', async () => {
      vi.mocked(apiFetch).mockImplementation((...args: unknown[]) => {
        const p = extractPath(args);
        if (p.includes('/api/v1/auth/session/me') || p.includes('/api/v1/auth/me')) {
          return Promise.resolve(mockAdminUser);
        }
        if (p.includes('/api/v1/admin/diagnostics')) {
          return Promise.resolve(mockDiagnosticsData);
        }
        return Promise.resolve({});
      });

      renderStudio('/admin/diagnostics', 'health');

      await waitFor(() => {
        expect(screen.getByTestId('admin-diagnostics-studio')).toBeDefined();
      });

      const headerActions = document.querySelector('.admin-diag-header-actions');
      expect(headerActions).not.toBeNull();
      const children = Array.from(headerActions?.children ?? []);
      expect(children.length).toBe(4);
      expect(children[0]?.getAttribute('data-testid')).toBe('ws-probe-badge');
      expect(children[1]?.getAttribute('data-testid')).toBe('run-ws-ping-btn');
      expect(children[2]?.getAttribute('data-testid')).toBe('refresh-diagnostics-btn');
      expect(children[3]?.getAttribute('data-testid')).toBe('diagnostics-doc-link');
    });
  });
});
