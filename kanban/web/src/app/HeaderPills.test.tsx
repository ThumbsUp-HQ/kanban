import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, act } from '@testing-library/react';
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { HeaderPills } from './HeaderPills';
import { ShellPanelsProvider } from './shellPanels';
import * as ShellPanelsModule from './shellPanels';
import type { SystemStatus } from './useSystemStatus';

describe('HeaderPills', () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
  });

  it('renders ⚠️ warning pill only in standalone mode with exact copy and ephemeral warning', () => {
    const standaloneStatus: SystemStatus = {
      deployment_mode: 'standalone_embedded_pg',
      persistent_volume: false,
      air_gap_mode: false,
      local_llm_endpoint_host: null,
    };

    render(
      <QueryClientProvider client={queryClient}>
        <ShellPanelsProvider>
          <HeaderPills systemStatus={standaloneStatus} />
        </ShellPanelsProvider>
      </QueryClientProvider>,
    );

    const warnPill = screen.getByRole('button', { name: 'Standalone mode warning' });
    expect(warnPill).toBeDefined();

    // Trigger popover by focusing
    act(() => {
      warnPill.focus();
    });

    expect(
      screen.getByText(
        /Standalone Single-Container Mode \(Not Recommended for Production\) - Click for volume status, encrypted backup, & 1-click docker-compose.yml export/,
      ),
    ).toBeDefined();
    expect(
      screen.getByText(
        /Ephemeral Storage: Mount -v kanban_data:\/var\/lib\/kanban\/data to persist data across container removal/,
      ),
    ).toBeDefined();
  });

  it('omits ⚠️ pill in multi-container / production mode', () => {
    const prodStatus: SystemStatus = {
      deployment_mode: 'multi_container',
      persistent_volume: true,
      air_gap_mode: false,
      local_llm_endpoint_host: null,
    };

    render(
      <QueryClientProvider client={queryClient}>
        <ShellPanelsProvider>
          <HeaderPills systemStatus={prodStatus} />
        </ShellPanelsProvider>
      </QueryClientProvider>,
    );

    expect(screen.queryByRole('button', { name: 'Standalone mode warning' })).toBeNull();
  });

  it('renders 📴 air-gap pill with "visible to server admins only" when local_llm_endpoint_host is null', () => {
    const airgapStatus: SystemStatus = {
      deployment_mode: 'multi_container',
      persistent_volume: true,
      air_gap_mode: true,
      local_llm_endpoint_host: null,
    };

    render(
      <QueryClientProvider client={queryClient}>
        <ShellPanelsProvider>
          <HeaderPills systemStatus={airgapStatus} />
        </ShellPanelsProvider>
      </QueryClientProvider>,
    );

    const airgapPill = screen.getByRole('button', { name: 'Air-gap local-only mode' });
    expect(airgapPill).toBeDefined();

    act(() => {
      airgapPill.focus();
    });

    expect(
      screen.getByText(
        /Air-Gap Local-Only Mode: external LLM and media egress are disabled at the socket level\./,
      ),
    ).toBeDefined();
    expect(screen.getByText(/visible to server admins only/)).toBeDefined();
  });

  it('renders 📴 air-gap pill displaying specific local model host', () => {
    const customHostStatus: SystemStatus = {
      deployment_mode: 'multi_container',
      persistent_volume: true,
      air_gap_mode: true,
      local_llm_endpoint_host: 'http://127.0.0.1:11434',
    };

    render(
      <QueryClientProvider client={queryClient}>
        <ShellPanelsProvider>
          <HeaderPills systemStatus={customHostStatus} />
        </ShellPanelsProvider>
      </QueryClientProvider>,
    );

    const airgapPill = screen.getByRole('button', { name: 'Air-gap local-only mode' });
    act(() => {
      airgapPill.focus();
    });

    expect(screen.getByText(/http:\/\/127\.0\.0\.1:11434/)).toBeDefined();
  });

  it('renders 🛡️ access pill with counts and zero redacted names', () => {
    const manifest = {
      pill_label: 'Project + 2',
      explicit_grant_count: 2,
      inherited_scope: {
        kind: 'project',
        scope_label: 'Project + 2',
        workspace_name: 'Engineering',
        project_name: 'Platform Core',
      },
      users: [{}, {}, {}, {}], // 4 users
      groups: [{}, {}], // 2 groups
      agents: [{}], // 1 agent
      deny_overrides: [{}], // 1 deny override
      redacted_count: 1,
    };

    render(
      <QueryClientProvider client={queryClient}>
        <ShellPanelsProvider>
          <HeaderPills accessManifest={manifest} />
        </ShellPanelsProvider>
      </QueryClientProvider>,
    );

    const accessPill = screen.getByRole('button', { name: 'Access: Project + 2' });
    expect(accessPill).toBeDefined();

    act(() => {
      accessPill.focus();
    });

    expect(screen.getByText('Project: Platform Core')).toBeDefined();
    expect(
      screen.getByText('4 users, 2 groups, 1 🤖 agents, 1 🔒 deny rules'),
    ).toBeDefined();
    expect(screen.getByText('1 external collaborator(s)')).toBeDefined();

    // Confirm zero secret/redacted names leaked
    expect(screen.queryByText(/Restricted Principal/)).toBeNull();
    expect(screen.queryByText(/External Collaborator Name/)).toBeNull();
  });

  it('triggers onActivate callbacks opening standalone and access panels', () => {
    let panelIdCalled = '';
    function DummyPanel({ arg }: { arg?: unknown }): React.JSX.Element {
      panelIdCalled = String(arg);
      return <div data-testid="active-panel">Panel: {panelIdCalled}</div>;
    }

    ShellPanelsModule.registerShellPanel('standalone', DummyPanel);
    ShellPanelsModule.registerShellPanel('access', DummyPanel);

    const status: SystemStatus = {
      deployment_mode: 'standalone',
      persistent_volume: true,
      air_gap_mode: false,
      local_llm_endpoint_host: null,
    };
    const manifest = {
      pill_label: 'Project + 2',
      users: [],
    };

    render(
      <QueryClientProvider client={queryClient}>
        <ShellPanelsProvider>
          <HeaderPills
            systemStatus={status}
            accessManifest={manifest}
            projectId="KAN"
          />
        </ShellPanelsProvider>
      </QueryClientProvider>,
    );

    const warnBtn = screen.getByRole('button', { name: 'Standalone mode warning' });
    act(() => {
      warnBtn.click();
    });
    expect(screen.getByTestId('active-panel')).toBeDefined();

    const accessBtn = screen.getByRole('button', { name: 'Access: Project + 2' });
    act(() => {
      accessBtn.click();
    });
    expect(screen.getByTestId('active-panel')).toBeDefined();
  });

  it('fetches access manifest from API when accessManifest prop is omitted', async () => {
    const mockManifest = {
      pill_label: 'Project + 1',
      inherited_scope: { project_name: 'Fetched Core' },
      users: [{}],
    };

    const getRequestUrl = (input: RequestInfo | URL): string => {
      if (typeof input === 'string') return input;
      if (input instanceof URL) return input.href;
      return input.url;
    };

    vi.spyOn(window, 'fetch').mockImplementation((url) => {
      const urlStr = getRequestUrl(url);
      if (urlStr.includes('/access')) {
        return Promise.resolve(new Response(JSON.stringify(mockManifest), { status: 200 }));
      }
      return Promise.resolve(new Response(JSON.stringify({ deployment_mode: 'prod' }), { status: 200 }));
    });

    render(
      <QueryClientProvider client={queryClient}>
        <ShellPanelsProvider>
          <HeaderPills projectId="KAN" />
        </ShellPanelsProvider>
      </QueryClientProvider>,
    );

    const accessPill = await screen.findByRole('button', { name: 'Access: Project + 1' });
    expect(accessPill).toBeDefined();
  });

  it('handles non-ok access fetch response gracefully', () => {
    const getRequestUrl = (input: RequestInfo | URL): string => {
      if (typeof input === 'string') return input;
      if (input instanceof URL) return input.href;
      return input.url;
    };

    vi.spyOn(window, 'fetch').mockImplementation((url) => {
      const urlStr = getRequestUrl(url);
      if (urlStr.includes('/access')) {
        return Promise.resolve(new Response(null, { status: 500 }));
      }
      return Promise.resolve(new Response(JSON.stringify({ deployment_mode: 'prod' }), { status: 200 }));
    });

    render(
      <QueryClientProvider client={queryClient}>
        <ShellPanelsProvider>
          <HeaderPills projectId="KAN" />
        </ShellPanelsProvider>
      </QueryClientProvider>,
    );

    // Pill is omitted when access fetch fails
    const accessPill = screen.queryByRole('button', { name: /Access:/ });
    expect(accessPill).toBeNull();
  });
});
