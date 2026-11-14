import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AgentKillSwitchControl } from './AgentKillSwitchControl';
import * as RealtimeModule from '../../api/RealtimeStatus';
import kan142Data from '../../../e2e/fixtures/access-inspector-kan-142.json';

const TEST_OBJECT_ID = 'c0000000-0000-0000-0000-000000000142';

function renderWithClient(ui: React.ReactElement, initialData?: unknown) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  if (initialData) {
    queryClient.setQueryData(['access', TEST_OBJECT_ID], initialData);
  }
  return {
    queryClient,
    ...render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>),
  };
}

describe('AgentKillSwitchControl', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(document, 'cookie', 'get').mockReturnValue('__Host-kb_csrf=csrf-test-token-123');
  });

  it('renders [ Kill Switch ] and triggers 2-step confirmation with default Cancel focus', () => {
    renderWithClient(
      <AgentKillSwitchControl
        objectId={TEST_OBJECT_ID}
        canonicalKey="KAN-142"
        agentsCount={2}
      />,
      kan142Data,
    );

    const btn = screen.getByRole('button', { name: /kill switch/i });
    expect(btn).toBeDefined();

    fireEvent.click(btn);

    // Confirmation banner appears
    expect(
      screen.getByText('Revoke all active agent grants on KAN-142?'),
    ).toBeDefined();

    const cancelBtn = screen.getByRole('button', { name: /cancel/i });
    const confirmBtn = screen.getByRole('button', { name: /confirm kill switch/i });

    expect(cancelBtn).toBeDefined();
    expect(confirmBtn).toBeDefined();

    // Focus moved to Cancel by default to prevent accidental Enter activation
    expect(document.activeElement).toBe(cancelBtn);

    // Clicking Cancel closes confirmation
    fireEvent.click(cancelBtn);
    expect(
      screen.queryByText('Revoke all active agent grants on KAN-142?'),
    ).toBeNull();
  });

  it('optimistically clears agents and calls POST endpoint with CSRF token', async () => {
    let capturedMethod = '';
    let capturedHeaders: Record<string, string> = {};

    vi.spyOn(globalThis, 'fetch').mockImplementation((_url, init) => {
      capturedMethod = init?.method ?? '';
      capturedHeaders = init?.headers ? (init.headers as Record<string, string>) : {};
      return Promise.resolve(
        new Response(JSON.stringify({ ...kan142Data, agents: [] }), {
          status: 200,
          headers: { 'content-type': 'application/json' },
        }),
      );
    });

    const { queryClient } = renderWithClient(
      <AgentKillSwitchControl
        objectId={TEST_OBJECT_ID}
        canonicalKey="KAN-142"
        agentsCount={2}
      />,
      kan142Data,
    );

    // Open confirmation
    fireEvent.click(screen.getByRole('button', { name: /kill switch/i }));

    // Confirm
    const confirmBtn = screen.getByRole('button', { name: /confirm kill switch/i });
    fireEvent.click(confirmBtn);

    await waitFor(() => {
      expect(capturedMethod).toBe('POST');
    });

    expect(capturedHeaders['X-CSRF-Token']).toBe('csrf-test-token-123');

    // Query data is cleared
    const cached = queryClient.getQueryData<typeof kan142Data>(['access', TEST_OBJECT_ID]);
    expect(cached?.agents).toEqual([]);
  });

  it('rolls back to previous snapshot on HTTP 500 error and announces rollback', async () => {
    const announceSpy = vi.spyOn(RealtimeModule, 'announce');

    vi.spyOn(globalThis, 'fetch').mockImplementation(() => {
      return Promise.resolve(
        new Response(JSON.stringify({ error: 'Internal Server Error' }), {
          status: 500,
          headers: { 'content-type': 'application/json' },
        }),
      );
    });

    const { queryClient } = renderWithClient(
      <AgentKillSwitchControl
        objectId={TEST_OBJECT_ID}
        canonicalKey="KAN-142"
        agentsCount={2}
      />,
      kan142Data,
    );

    fireEvent.click(screen.getByRole('button', { name: /kill switch/i }));
    fireEvent.click(screen.getByRole('button', { name: /confirm kill switch/i }));

    await waitFor(() => {
      expect(announceSpy).toHaveBeenCalledWith(
        'Failed to revoke agent grants. Reverting changes.',
      );
    });

    // Check cache is restored
    const cached = queryClient.getQueryData<typeof kan142Data>(['access', TEST_OBJECT_ID]);
    expect(cached?.agents.length).toBe(2);
  });

  it('handles missing CSRF token and empty cache gracefully', async () => {
    vi.restoreAllMocks();
    // Simulate no cookie present
    vi.spyOn(document, 'cookie', 'get').mockReturnValue('');
    let cookieSet = '';
    vi.spyOn(document, 'cookie', 'set').mockImplementation((val) => {
      cookieSet = val;
    });

    vi.spyOn(globalThis, 'fetch').mockImplementation(() => {
      return Promise.resolve(
        new Response(JSON.stringify({ agents: [] }), {
          status: 200,
          headers: { 'content-type': 'application/json' },
        }),
      );
    });

    renderWithClient(
      <AgentKillSwitchControl
        objectId={TEST_OBJECT_ID}
        canonicalKey=""
        agentsCount={1}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: /kill switch/i }));
    expect(
      screen.getByText(`Revoke all active agent grants on ${TEST_OBJECT_ID}?`),
    ).toBeDefined();
    fireEvent.click(screen.getByRole('button', { name: /confirm kill switch/i }));

    await waitFor(() => {
      expect(cookieSet).toContain('kb_csrf');
    });
  });
});
