// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, act, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router';
import fs from 'node:fs';
import path from 'node:path';
import * as clientModule from '../../../api/client';
import { AdminStudioSubnav } from '../AdminStudioSubnav';
import { LinkAuditorStudio } from '../LinkAuditorStudio';
import { AdminDiagnosticsStudio } from '../AdminDiagnosticsStudio';

vi.mock('../../../api/client', async () => {
  const actual = await vi.importActual<typeof import('../../../api/client')>(
    '../../../api/client',
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

const mockAuditResponse = {
  items: [
    {
      id: 'aud-test-1',
      workspace_id: 'ws-1',
      link_id: 'lnk-1',
      reason: 'DANGLING_TARGET',
      detected_at: '2026-11-20T10:00:00Z',
      purged_at: null,
      resolved_at: null,
      link_snapshot: {
        id: 'lnk-1',
        source_id: 'src-1',
        target_id: 'tgt-1',
        link_type: 'RELATES_TO',
      },
      source_snapshot: { id: 'src-1', title: 'Source Issue', canonical_key: 'KAN-1' },
      target_snapshot: { id: 'tgt-1', title: 'Target Sticky', canonical_key: 'STK-2' },
    },
  ],
  total: 1,
  has_more: false,
};

const mockDiagResponse = {
  status: 'healthy',
  timestamp: '2026-11-20T10:00:00Z',
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
  database: {
    engine: 'postgresql',
    pool_size: 10,
    max_overflow: 20,
    active_connections: 2,
    rls_enforced: true,
    schema_version: '20261120_120000',
    pending_migrations_count: 0,
    db_response_time_ms: 1.2,
  },
  realtime: {
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
  subsystems: {
    database: {
      name: 'database',
      status: 'ok',
      message: 'PostgreSQL connection pool healthy',
      details: { connections: 10 },
    },
  },
  storage: {
    total_bytes: 107374182400,
    free_bytes: 53687091200,
    directories: [
      {
        name: 'uploads',
        path: '/var/lib/kanban/uploads',
        exists: true,
        writable: true,
        total_bytes: 107374182400,
        free_bytes: 53687091200,
      },
    ],
  },
  config: [
    {
      key: 'AUTH_SESSION_TTL',
      subsystem: 'auth',
      value: '86400',
      source: 'env',
      redacted: false,
      notes: 'Session lifetime in seconds',
    },
  ],
};

function renderWithClient(ui: React.ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        staleTime: Infinity,
      },
    },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/admin/diagnostics']}>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('Admin & Settings Studios Mobile Layout Ergonomics (KAN-344)', () => {
  beforeEach(async () => {
    vi.clearAllMocks();
    const { apiFetch } = await import('../../../api/client');
    vi.mocked(apiFetch).mockImplementation((_method, pathStr) => {
      if (pathStr === '/api/v1/auth/me') {
        return Promise.resolve(mockAdminUser);
      }
      if (pathStr === '/api/v1/admin/object-links/audits') {
        return Promise.resolve(mockAuditResponse);
      }
      if (pathStr === '/api/v1/admin/diagnostics') {
        return Promise.resolve(mockDiagResponse);
      }
      return Promise.resolve([]);
    });
  });

  // =========================================================================
  // Test Case 1: Horizontal swipe tabs & touch scrolling navigation
  // =========================================================================
  describe('Case 1: Horizontal swipe tabs & touch scrolling navigation', () => {
    it('renders AdminStudioSubnav with swipeable scroll container, aria attributes, and touch targets', async () => {
      let r: ReturnType<typeof render> | undefined;
      await act(async () => {
        r = renderWithClient(<AdminStudioSubnav activeTab="diagnostics" isServerAdmin={true} />);
        await Promise.resolve();
      });

      const navElement = screen.getByRole('navigation', {
        name: /Admin MCP and Governance Navigation/i,
      });
      expect(navElement).toBeTruthy();
      expect(navElement.classList.contains('admin-studio-subnav')).toBe(true);

      const scrollContainer = navElement.querySelector('.admin-studio-subnav__scroll');
      expect(scrollContainer).toBeTruthy();

      const tabs = screen.getAllByRole('link');
      expect(tabs.length).toBeGreaterThanOrEqual(8);

      const activeTab = screen.getByTestId('tab-admin-diagnostics');
      expect(activeTab.getAttribute('aria-current')).toBe('page');
      expect(activeTab.classList.contains('admin-studio-subnav__item--active')).toBe(true);
      r?.unmount();
    });

    it('renders AdminStudioSubnav with matching currentPath and subpath in router context without explicit activeTab', async () => {
      const queryClient = new QueryClient({
        defaultOptions: { queries: { retry: false } },
      });
      let r: ReturnType<typeof render> | undefined;
      await act(async () => {
        r = render(
          <QueryClientProvider client={queryClient}>
            <MemoryRouter initialEntries={['/admin/ai/new']}>
              <AdminStudioSubnav isServerAdmin={true} />
            </MemoryRouter>
          </QueryClientProvider>,
        );
        await Promise.resolve();
      });

      const aiTab = screen.getByTestId('tab-admin-ai');
      expect(aiTab.getAttribute('aria-current')).toBe('page');
      r?.unmount();
    });

    it('renders AdminStudioSubnav outside router context with matching activeTab or path fallback', async () => {
      let r1: ReturnType<typeof render> | undefined;
      await act(async () => {
        r1 = render(<AdminStudioSubnav activeTab="auth" isServerAdmin={true} />);
        await Promise.resolve();
      });
      const c1 = r1?.container;
      const links = c1?.querySelectorAll('a.admin-studio-subnav__item');
      expect(links && links.length >= 8).toBe(true);

      const authLink = c1?.querySelector('[data-testid="tab-admin-auth"]');
      expect(authLink).toBeTruthy();
      expect(authLink?.getAttribute('aria-current')).toBe('page');
      expect(authLink?.classList.contains('admin-studio-subnav__item--active')).toBe(true);
      r1?.unmount();

      // Outside router with window.location fallback (exact match and prefix match)
      const origLocation = window.location;
      try {
        delete (window as unknown as { location: unknown }).location;
        (window as unknown as { location: unknown }).location = {
          pathname: '/admin/oauth/clients',
        };
        let r2: ReturnType<typeof render> | undefined;
        await act(async () => {
          r2 = render(<AdminStudioSubnav isServerAdmin={true} />);
          await Promise.resolve();
        });
        const oauthLink = r2?.container.querySelector('[data-testid="tab-admin-oauth"]');
        expect(oauthLink?.getAttribute('aria-current')).toBe('page');
        r2?.unmount();

        (window as unknown as { location: unknown }).location = {
          pathname: '/admin/diagnostics',
        };
        let r3: ReturnType<typeof render> | undefined;
        await act(async () => {
          r3 = render(<AdminStudioSubnav isServerAdmin={true} />);
          await Promise.resolve();
        });
        const diagLink = r3?.container.querySelector('[data-testid="tab-admin-diagnostics"]');
        expect(diagLink?.getAttribute('aria-current')).toBe('page');
        r3?.unmount();

        (window as unknown as { location: unknown }).location = {
          pathname: '/unknown-route',
        };
        let r4: ReturnType<typeof render> | undefined;
        await act(async () => {
          r4 = render(<AdminStudioSubnav isServerAdmin={true} />);
          await Promise.resolve();
        });
        const activeItem = r4?.container.querySelector('.admin-studio-subnav__item--active');
        expect(activeItem).toBeNull();
        r4?.unmount();
      } finally {
        (window as unknown as { location: unknown }).location = origLocation;
      }
    });

    it('updates admin-sudo-pill live on kb:aal2-stepup-success and kb:aal2-expires-at events', async () => {
      let sessionState = {
        authenticated: true,
        aal2_active: false,
        aal2_expires_at: null as string | null,
      };

      vi.spyOn(clientModule, 'apiFetch').mockImplementation((_method, path) => {
        if ((path as string) === '/api/v1/auth/session') {
          return Promise.resolve(sessionState);
        }
        return Promise.resolve(undefined);
      });

      render(<AdminStudioSubnav activeTab="auth" isServerAdmin={true} />);

      await waitFor(() => {
        expect(screen.getByTestId('admin-sudo-pill').textContent).toContain('Sudo Locked');
      });

      // Dispatch kb:aal2-expires-at event
      const futureExpiry = new Date(Date.now() + 900_000).toISOString();
      sessionState = {
        authenticated: true,
        aal2_active: true,
        aal2_expires_at: futureExpiry,
      };

      act(() => {
        window.dispatchEvent(
          new CustomEvent('kb:aal2-expires-at', {
            detail: { expiresAt: futureExpiry },
          }),
        );
      });

      await waitFor(() => {
        expect(screen.getByTestId('admin-sudo-pill').textContent).toMatch(/Sudo (15:00|14:59)/);
      });

      // Dispatch kb:aal2-stepup-success event
      act(() => {
        window.dispatchEvent(new CustomEvent('kb:aal2-stepup-success'));
      });

      await waitFor(() => {
        expect(screen.getByTestId('admin-sudo-drop-btn')).toBeDefined();
      });
    });

    it('enforces touch scrolling rules in AdminStudioSubnav.css and AdminDiagnosticsStudio.css', () => {
      const subnavCssPath = path.resolve(
        import.meta.dirname,
        '../AdminStudioSubnav.css',
      );
      const subnavCss = fs.readFileSync(subnavCssPath, 'utf8');

      expect(subnavCss).toContain('-webkit-overflow-scrolling: touch');
      expect(subnavCss).toContain('overflow-x: auto');
      expect(subnavCss).toContain('overscroll-behavior-x: contain');
      expect(subnavCss).toContain('@media (max-width: 767px)');
      expect(subnavCss).toContain('var(--tap-min, 44px)');

      const diagCssPath = path.resolve(
        import.meta.dirname,
        '../AdminDiagnosticsStudio.css',
      );
      const diagCss = fs.readFileSync(diagCssPath, 'utf8');

      expect(diagCss).toContain('-webkit-overflow-scrolling: touch');
      expect(diagCss).toContain('overscroll-behavior-x: contain');
    });

    it('enforces horizontal swipe tabs in WorkspaceSettingsPage.css and ProjectSettingsPage.css', () => {
      const wsCssPath = path.resolve(
        import.meta.dirname,
        '../../settings/WorkspaceSettingsPage.css',
      );
      expect(fs.existsSync(wsCssPath)).toBe(true);
      const wsCss = fs.readFileSync(wsCssPath, 'utf8');

      expect(wsCss).toContain('-webkit-overflow-scrolling: touch');
      expect(wsCss).toContain('overflow-x: auto');
      expect(wsCss).toContain('flex-wrap: nowrap');

      const projCssPath = path.resolve(
        import.meta.dirname,
        '../../settings/ProjectSettingsPage.css',
      );
      const projCss = fs.readFileSync(projCssPath, 'utf8');

      expect(projCss).toContain('-webkit-overflow-scrolling: touch');
      expect(projCss).toContain('overflow-x: auto');
      expect(projCss).toContain('flex-wrap: nowrap');
    });
  });

  // =========================================================================
  // Test Case 2: Responsive column stacking for multi-column tables at <= 767px
  // =========================================================================
  describe('Case 2: Responsive column stacking for multi-column tables at <= 767px', () => {
    it('verifies LinkAuditorStudio table cells expose data-label attributes for mobile card stacking', async () => {
      renderWithClient(
        <LinkAuditorStudio />,
      );

      const table = await screen.findByTestId('audit-links-table');
      expect(table).toBeTruthy();

      const row = await screen.findByTestId('audit-row-aud-test-1');
      expect(row).toBeTruthy();

      const cells = row.querySelectorAll('td');
      expect(cells.length).toBe(8);

      expect(cells[0]?.getAttribute('data-label')).toBe('Select');
      expect(cells[1]?.getAttribute('data-label')).toBe('Invalidity Reason');
      expect(cells[2]?.getAttribute('data-label')).toBe('Source Object');
      expect(cells[3]?.getAttribute('data-label')).toBe('Link Type');
      expect(cells[4]?.getAttribute('data-label')).toBe('Target Object');
      expect(cells[5]?.getAttribute('data-label')).toBe('Detected At');
      expect(cells[6]?.getAttribute('data-label')).toBe('Status');
      expect(cells[7]?.getAttribute('data-label')).toBe('Actions');
    });

    it('verifies AdminDiagnosticsStudio storage and config tables expose data-label attributes', async () => {
      renderWithClient(
        <AdminDiagnosticsStudio defaultTab="runtime" />,
      );

      const storageVolumeCell = await screen.findByText('uploads');
      const storageTd = storageVolumeCell.closest('td');
      expect(storageTd).toBeTruthy();
      expect(storageTd?.getAttribute('data-label')).toBe('Storage Volume');
    });

    it('enforces table display block stacking and thead suppression rules in CSS files', () => {
      const linkAuditorCssPath = path.resolve(
        import.meta.dirname,
        '../LinkAuditorStudio.css',
      );
      const linkAuditorCss = fs.readFileSync(linkAuditorCssPath, 'utf8');

      expect(linkAuditorCss).toContain('@media (max-width: 767px)');
      expect(linkAuditorCss).toContain('.link-auditor-table thead');
      expect(linkAuditorCss).toContain('display: none');
      expect(linkAuditorCss).toContain('content: attr(data-label)');

      const diagCssPath = path.resolve(
        import.meta.dirname,
        '../AdminDiagnosticsStudio.css',
      );
      const diagCss = fs.readFileSync(diagCssPath, 'utf8');

      expect(diagCss).toContain('@media (max-width: 767px)');
      expect(diagCss).toContain('.admin-diag-table thead');
      expect(diagCss).toContain('display: none');
      expect(diagCss).toContain('content: attr(data-label)');

      const authCssPath = path.resolve(
        import.meta.dirname,
        '../../admin-auth/adminAuth.css',
      );
      const authCss = fs.readFileSync(authCssPath, 'utf8');

      expect(authCss).toContain('@media (max-width: 767px)');
      expect(authCss).toContain('.auth-users-th,');
      expect(authCss).toContain('display: none');
      expect(authCss).toContain('content: attr(data-label)');

      const aiCssPath = path.resolve(
        import.meta.dirname,
        '../../admin-ai/aiStudio.css',
      );
      const aiCss = fs.readFileSync(aiCssPath, 'utf8');

      expect(aiCss).toContain('@media (max-width: 767px)');
      expect(aiCss).toContain('grid-template-columns: 1fr');
    });
  });

  // =========================================================================
  // Test Case 3: Sticky and visible form action buttons and mobile touch ergonomics
  // =========================================================================
  describe('Case 3: Sticky and visible form action buttons and mobile touch ergonomics', () => {
    it('verifies action buttons and interactive controls across admin studios meet 44px tap target requirements', () => {
      const subnavCssPath = path.resolve(
        import.meta.dirname,
        '../AdminStudioSubnav.css',
      );
      const subnavCss = fs.readFileSync(subnavCssPath, 'utf8');
      expect(subnavCss).toContain('min-height: var(--tap-min, 44px)');

      const linkAuditorCssPath = path.resolve(
        import.meta.dirname,
        '../LinkAuditorStudio.css',
      );
      const linkAuditorCss = fs.readFileSync(linkAuditorCssPath, 'utf8');
      expect(linkAuditorCss).toContain('min-height: var(--tap-min, 44px)');
      expect(linkAuditorCss).toContain('min-width: var(--tap-min, 44px)');

      const diagCssPath = path.resolve(
        import.meta.dirname,
        '../AdminDiagnosticsStudio.css',
      );
      const diagCss = fs.readFileSync(diagCssPath, 'utf8');
      expect(diagCss).toContain('min-height: var(--tap-min, 44px)');
      expect(diagCss).toContain('min-width: var(--tap-min, 44px)');
    });

    it('verifies sticky action toolbars and drawer footers remain anchored on mobile viewports', () => {
      const linkAuditorCssPath = path.resolve(
        import.meta.dirname,
        '../LinkAuditorStudio.css',
      );
      const linkAuditorCss = fs.readFileSync(linkAuditorCssPath, 'utf8');
      expect(linkAuditorCss).toContain('position: sticky');
      expect(linkAuditorCss).toContain('top: var(--topbar-h, 52px)');

      const authCssPath = path.resolve(
        import.meta.dirname,
        '../../admin-auth/adminAuth.css',
      );
      const authCss = fs.readFileSync(authCssPath, 'utf8');
      expect(authCss).toContain('position: sticky');
      expect(authCss).toContain('bottom: 0');

      const aiCssPath = path.resolve(
        import.meta.dirname,
        '../../admin-ai/aiStudio.css',
      );
      const aiCss = fs.readFileSync(aiCssPath, 'utf8');
      expect(aiCss).toContain('position: sticky');
      expect(aiCss).toContain('bottom: 0');

      const wsCssPath = path.resolve(
        import.meta.dirname,
        '../../settings/WorkspaceSettingsPage.css',
      );
      const wsCss = fs.readFileSync(wsCssPath, 'utf8');
      expect(wsCss).toContain('position: sticky');
      expect(wsCss).toContain('bottom: 0');
    });

    it('verifies mobile input controls enforce font-size 16px to prevent iOS auto-zoom distortion', () => {
      const linkAuditorCssPath = path.resolve(
        import.meta.dirname,
        '../LinkAuditorStudio.css',
      );
      const linkAuditorCss = fs.readFileSync(linkAuditorCssPath, 'utf8');
      expect(linkAuditorCss).toContain('font-size: 16px');

      const diagCssPath = path.resolve(
        import.meta.dirname,
        '../AdminDiagnosticsStudio.css',
      );
      const diagCss = fs.readFileSync(diagCssPath, 'utf8');
      expect(diagCss).toContain('font-size: 16px');

      const authCssPath = path.resolve(
        import.meta.dirname,
        '../../admin-auth/adminAuth.css',
      );
      const authCss = fs.readFileSync(authCssPath, 'utf8');
      expect(authCss).toContain('font-size: 16px');
    });
  });
});
