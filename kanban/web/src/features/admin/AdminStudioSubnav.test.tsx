// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import React from 'react';
import fs from 'node:fs';
import path from 'node:path';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AdminStudioSubnav } from './AdminStudioSubnav';
import { apiFetch } from '../../api/client';

vi.mock('../../api/client', async () => {
  const actual = await vi.importActual<typeof import('../../api/client')>(
    '../../api/client',
  );
  return {
    ...actual,
    apiFetch: vi.fn(),
  };
});

describe('AdminStudioSubnav Component and CSS Tokens (KAN-525)', () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    vi.clearAllMocks();
    queryClient = new QueryClient({
      defaultOptions: {
        queries: {
          retry: false,
        },
      },
    });
  });

  afterEach(() => {
    document.documentElement.removeAttribute('data-theme');
  });

  it('verifies AdminStudioSubnav.css binds active tab to var(--badge-fg) and eliminates legacy hexes', () => {
    const cssPath = path.resolve(__dirname, 'AdminStudioSubnav.css');
    const cssContent = fs.readFileSync(cssPath, 'utf8');

    // Asserts active tab class rule exists and uses semantic tokens
    expect(cssContent).toContain('.admin-studio-subnav__item--active');
    expect(cssContent).toContain('color: var(--badge-fg) !important;');
    expect(cssContent).toContain('border-bottom-color: var(--badge-fg) !important;');
    expect(cssContent).toContain('background-color: var(--bg-accent-subtle);');
    expect(cssContent).toContain('.admin-studio-subnav__icon');
    expect(cssContent).toContain('color: inherit;');

    // Asserts sudo pills use semantic tokens
    expect(cssContent).toContain('.admin-sudo-pill--active');
    expect(cssContent).toContain('background-color: var(--bg-success-subtle);');
    expect(cssContent).toContain('border-color: var(--border-success);');
    expect(cssContent).toContain('color: var(--text-success);');

    expect(cssContent).toContain('.admin-sudo-pill--locked');
    expect(cssContent).toContain('background-color: var(--danger-bg);');
    expect(cssContent).toContain('border-color: var(--border-danger);');
    expect(cssContent).toContain('color: var(--danger-fg);');

    // Asserts drop button uses semantic hover tokens
    expect(cssContent).toContain('background-color: var(--bg-hover);');
    expect(cssContent).toContain('background-color: var(--bg-secondary-hover);');

    // Asserts legacy hardcoded GitHub dark hexes and poorly contrasting accent are eliminated
    expect(cssContent).not.toContain('#3fb950');
    expect(cssContent).not.toContain('#f85149');
    expect(cssContent).not.toContain('#58a6ff');
  });

  it('renders all studio tabs for server admin in light and dark themes', async () => {
    vi.mocked(apiFetch).mockResolvedValue({
      authenticated: true,
      aal2_active: false,
      aal2_expires_at: null,
    });

    for (const theme of ['light', 'dark']) {
      document.documentElement.setAttribute('data-theme', theme);

      const { unmount } = render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={['/admin/agents']}>
            <AdminStudioSubnav isServerAdmin={true} activeTab="agents" />
          </MemoryRouter>
        </QueryClientProvider>,
      );

      // Verify active tab element
      await waitFor(() => {
        const activeTab = screen.getByTestId('tab-admin-agents');
        expect(activeTab.className).toContain('admin-studio-subnav__item--active');
        expect(activeTab.className).toContain('kb-mcp-admin-subnav-active');
        expect(activeTab.getAttribute('aria-current')).toBe('page');
        expect(activeTab.textContent).toContain('Agents');
        expect(activeTab.textContent).toContain('🤖');
      });

      // Verify other tabs are visible and inactive
      const authTab = screen.getByTestId('tab-admin-auth');
      expect(authTab.className).not.toContain('admin-studio-subnav__item--active');
      expect(authTab.getAttribute('aria-current')).toBeNull();

      const diagTab = screen.getByTestId('tab-admin-diagnostics');
      expect(diagTab.className).not.toContain('admin-studio-subnav__item--active');

      const pill = screen.getByTestId('admin-sudo-pill');
      expect(pill.className).toContain('admin-sudo-pill--locked');
      expect(pill.textContent).toContain('Sudo Locked');

      unmount();
    }
  });

  it('renders only non-server-only tabs when isServerAdmin is false', async () => {
    vi.mocked(apiFetch).mockResolvedValue({
      authenticated: true,
      aal2_active: false,
      aal2_expires_at: null,
    });

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={['/admin/diagnostics']}>
          <AdminStudioSubnav isServerAdmin={false} activeTab="diagnostics" />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('tab-admin-diagnostics')).toBeDefined();
    });
    expect(screen.queryByTestId('tab-admin-auth')).toBeNull();
    expect(screen.queryByTestId('tab-admin-ai')).toBeNull();
    expect(screen.queryByTestId('tab-admin-agents')).toBeNull();
  });

  it('renders active sudo pill when aal2_active is true and drops elevation on click', async () => {
    const futureExpires = new Date(Date.now() + 300_000).toISOString();
    vi.mocked(apiFetch).mockImplementation((_method: string, path: string) => {
      if (path === '/api/v1/auth/session') {
        return Promise.resolve({
          authenticated: true,
          aal2_active: true,
          aal2_expires_at: futureExpires,
        });
      }
      if (path === '/api/v1/auth/aal2/drop') {
        return Promise.resolve({ ok: true });
      }
      return Promise.resolve({});
    });

    for (const theme of ['light', 'dark']) {
      document.documentElement.setAttribute('data-theme', theme);

      const { unmount } = render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={['/admin/auth']}>
            <AdminStudioSubnav isServerAdmin={true} activeTab="auth" />
          </MemoryRouter>
        </QueryClientProvider>,
      );

      await waitFor(() => {
        const pill = screen.getByTestId('admin-sudo-pill');
        expect(pill.className).toContain('admin-sudo-pill--active');
        expect(pill.textContent).toContain('Sudo');
      });

      const dropBtn = screen.getByTestId('admin-sudo-drop-btn');
      expect(dropBtn).toBeDefined();

      act(() => {
        fireEvent.click(dropBtn);
      });

      expect(vi.mocked(apiFetch)).toHaveBeenCalledWith('POST', '/api/v1/auth/aal2/drop');

      unmount();
    }
  });

  it('renders fallback anchor links when outside router context', async () => {
    vi.mocked(apiFetch).mockResolvedValue({
      authenticated: true,
      aal2_active: false,
      aal2_expires_at: null,
    });

    render(
      <QueryClientProvider client={queryClient}>
        <AdminStudioSubnav isServerAdmin={true} activeTab="diagnostics" />
      </QueryClientProvider>,
    );

    await waitFor(() => {
      const diagTab = screen.getByTestId('tab-admin-diagnostics');
      expect(diagTab.tagName.toLowerCase()).toBe('a');
      expect(diagTab.getAttribute('href')).toBe('/admin/diagnostics');
      expect(diagTab.className).toContain('admin-studio-subnav__item--active');
    });
  });
});
