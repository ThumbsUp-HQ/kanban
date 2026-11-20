import { act, render, renderHook, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import {
  RealtimeProvider,
  useRealtimeClient,
  useRealtimeLiveState,
  useRealtimeSubscription,
  RealtimeClient,
  type RealtimeEvent,
} from './index';

describe('Realtime Module & React Hooks', () => {
  let queryClient: QueryClient;
  let mockClient: RealtimeClient;

  let connectSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    mockClient = new RealtimeClient();
    connectSpy = vi.spyOn(mockClient, 'connect').mockImplementation(() => {
      // test stub
    });
    vi.spyOn(mockClient, 'close').mockImplementation(() => {
      // test stub
    });
  });

  afterEach(() => {
    queryClient.clear();
    vi.restoreAllMocks();
  });

  function wrapper({ children }: { children: React.ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>
        <RealtimeProvider client={mockClient} autoConnect={false} bindInvalidation={false}>
          {children}
        </RealtimeProvider>
      </QueryClientProvider>
    );
  }

  it('provides client and live state via context', () => {
    const { result } = renderHook(
      () => ({
        client: useRealtimeClient(),
        state: useRealtimeLiveState(),
      }),
      { wrapper },
    );

    expect(result.current.client).toBe(mockClient);
    expect(result.current.state).toBe('closed');
  });

  it('updates useRealtimeLiveState when client state changes', () => {
    const { result } = renderHook(() => useRealtimeLiveState(), { wrapper });

    expect(result.current).toBe('closed');

    act(() => {
      const target = mockClient as unknown as { stateListeners: Set<(s: string) => void> };
      target.stateListeners.forEach((l) => {
        l('open');
      });
    });
  });

  it('falls back to default client and open state when rendered outside provider', () => {
    const { result } = renderHook(() => ({
      client: useRealtimeClient(),
      state: useRealtimeLiveState(),
    }));

    expect(result.current.client).toBeDefined();
    expect(result.current.state).toBe('open');
  });

  it('auto-connects client on mount when autoConnect is true and session is authenticated', () => {
    render(
      <QueryClientProvider client={queryClient}>
        <RealtimeProvider
          client={mockClient}
          autoConnect={true}
          bindInvalidation={false}
          session={{ authenticated: true, mfa_pending: false }}
        >
          <div data-testid="child">Loaded</div>
        </RealtimeProvider>
      </QueryClientProvider>,
    );

    expect(connectSpy).toHaveBeenCalled();
    expect(screen.getByTestId('child').textContent).toBe('Loaded');
  });

  it('binds TanStack Query cache invalidations when bindInvalidation is true', () => {
    const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries').mockResolvedValue();

    render(
      <QueryClientProvider client={queryClient}>
        <RealtimeProvider client={mockClient} autoConnect={false} bindInvalidation={true}>
          <div>Ready</div>
        </RealtimeProvider>
      </QueryClientProvider>,
    );

    act(() => {
      mockClient.simulateEvent({
        id: 'ev-1',
        channel: 'project:KAN',
        type: 'issue.updated',
        payload: { key: 'KAN-42', project_key: 'KAN' },
      });
    });

    expect(invalidateSpy).toHaveBeenCalled();
  });

  it('subscribes and routes events with useRealtimeSubscription', () => {
    const received: RealtimeEvent[] = [];
    const handler = (ev: RealtimeEvent) => {
      received.push(ev);
    };

    const subscribeSpy = vi.spyOn(mockClient, 'subscribe');

    const { unmount } = renderHook(
      () => {
        useRealtimeSubscription('project:TEST', handler);
      },
      { wrapper },
    );

    expect(subscribeSpy).toHaveBeenCalledWith('project:TEST', expect.any(Function));

    const testEvent: RealtimeEvent = {
      id: 'e1',
      channel: 'project:TEST',
      type: 'issue.created',
      payload: { key: 'TEST-1' },
    };

    act(() => {
      mockClient.simulateEvent(testEvent);
    });

    expect(received).toHaveLength(1);
    expect(received[0]?.id).toBe('e1');

    unmount();
  });

  it('skips subscription when channel is null or undefined', () => {
    const subscribeSpy = vi.spyOn(mockClient, 'subscribe');

    renderHook(() => {
      useRealtimeSubscription(null);
    }, { wrapper });
    renderHook(() => {
      useRealtimeSubscription(undefined);
    }, { wrapper });

    expect(subscribeSpy).not.toHaveBeenCalled();
  });

  it('renders RealtimeProvider with default props and attaches to window', () => {
    const { unmount } = render(
      <QueryClientProvider client={queryClient}>
        <RealtimeProvider
          client={mockClient}
          session={{ authenticated: true, mfa_pending: false }}
        >
          <div data-testid="child">child</div>
        </RealtimeProvider>
      </QueryClientProvider>,
    );
    expect(screen.getByTestId('child')).toBeDefined();
    expect(connectSpy).toHaveBeenCalled();
    expect((window as unknown as { __kanbanRealtimeClient?: RealtimeClient }).__kanbanRealtimeClient).toBe(mockClient);
    unmount();
  });

  describe('Session gating & KAN-7 remediation', () => {
    it('makes 0 connect/WebSocket/EventSource/fetch attempts when authenticated is false', () => {
      const fetchSpy = vi.spyOn(globalThis, 'fetch');
      const wsSpy = vi.fn();
      vi.stubGlobal('WebSocket', wsSpy);
      const sseSpy = vi.fn();
      vi.stubGlobal('EventSource', sseSpy);

      const unauthClient = new RealtimeClient({ session: { authenticated: false, mfa_pending: false } });
      const localConnectSpy = vi.spyOn(unauthClient, 'connect');

      render(
        <QueryClientProvider client={queryClient}>
          <RealtimeProvider
            client={unauthClient}
            autoConnect={true}
            session={{ authenticated: false, mfa_pending: false }}
          >
            <div data-testid="unauth-content">Unauth</div>
          </RealtimeProvider>
        </QueryClientProvider>,
      );

      expect(localConnectSpy).not.toHaveBeenCalled();
      expect(wsSpy).not.toHaveBeenCalled();
      expect(sseSpy).not.toHaveBeenCalled();
      const sseFetches = fetchSpy.mock.calls.filter(([url]) => {
        const urlStr = typeof url === 'string' ? url : url instanceof URL ? url.toString() : '';
        return urlStr.includes('/sse');
      });
      expect(sseFetches).toHaveLength(0);
      expect(unauthClient.state).toBe('closed');
    });

    it('makes 0 connect/WebSocket/EventSource/fetch attempts when mfa_pending is true', () => {
      const fetchSpy = vi.spyOn(globalThis, 'fetch');
      const wsSpy = vi.fn();
      vi.stubGlobal('WebSocket', wsSpy);
      const sseSpy = vi.fn();
      vi.stubGlobal('EventSource', sseSpy);

      const mfaClient = new RealtimeClient({ session: { authenticated: true, mfa_pending: true } });
      const localConnectSpy = vi.spyOn(mfaClient, 'connect');

      render(
        <QueryClientProvider client={queryClient}>
          <RealtimeProvider
            client={mfaClient}
            autoConnect={true}
            session={{ authenticated: true, mfa_pending: true }}
          >
            <div data-testid="mfa-content">MFA Pending</div>
          </RealtimeProvider>
        </QueryClientProvider>,
      );

      expect(localConnectSpy).not.toHaveBeenCalled();
      expect(wsSpy).not.toHaveBeenCalled();
      expect(sseSpy).not.toHaveBeenCalled();
      const sseFetches = fetchSpy.mock.calls.filter(([url]) => {
        const urlStr = typeof url === 'string' ? url : url instanceof URL ? url.toString() : '';
        return urlStr.includes('/sse');
      });
      expect(sseFetches).toHaveLength(0);
      expect(mfaClient.state).toBe('closed');
    });

    it('connects when authenticated is true and mfa_pending is false', () => {
      const authClient = new RealtimeClient({ session: { authenticated: true, mfa_pending: false } });
      const localConnectSpy = vi.spyOn(authClient, 'connect').mockImplementation(() => undefined);

      render(
        <QueryClientProvider client={queryClient}>
          <RealtimeProvider
            client={authClient}
            autoConnect={true}
            session={{ authenticated: true, mfa_pending: false }}
          >
            <div data-testid="auth-content">Authenticated</div>
          </RealtimeProvider>
        </QueryClientProvider>,
      );

      expect(localConnectSpy).toHaveBeenCalledTimes(1);
    });

    it('dynamically connects when session transitions from unauthenticated to authenticated, and disconnects on logout', () => {
      const dynamicClient = new RealtimeClient();
      const localConnectSpy = vi.spyOn(dynamicClient, 'connect').mockImplementation(() => {
        dynamicClient.state = 'connecting';
      });
      const localCloseSpy = vi.spyOn(dynamicClient, 'close').mockImplementation(() => {
        dynamicClient.state = 'closed';
      });

      const { rerender } = render(
        <QueryClientProvider client={queryClient}>
          <RealtimeProvider
            client={dynamicClient}
            autoConnect={true}
            session={{ authenticated: false, mfa_pending: false }}
          >
            <div>Dynamic</div>
          </RealtimeProvider>
        </QueryClientProvider>,
      );

      expect(localConnectSpy).not.toHaveBeenCalled();

      // Transition to authenticated
      rerender(
        <QueryClientProvider client={queryClient}>
          <RealtimeProvider
            client={dynamicClient}
            autoConnect={true}
            session={{ authenticated: true, mfa_pending: false }}
          >
            <div>Dynamic</div>
          </RealtimeProvider>
        </QueryClientProvider>,
      );

      expect(localConnectSpy).toHaveBeenCalledTimes(1);

      // Transition to logout
      rerender(
        <QueryClientProvider client={queryClient}>
          <RealtimeProvider
            client={dynamicClient}
            autoConnect={true}
            session={{ authenticated: false, mfa_pending: false }}
          >
            <div>Dynamic</div>
          </RealtimeProvider>
        </QueryClientProvider>,
      );

      expect(localCloseSpy).toHaveBeenCalled();
    });

    it('suppresses connection when window pathname is /login or /setup', () => {
      const originalPathname = window.location.pathname;
      try {
        window.history.pushState({}, '', '/login');
        const loginClient = new RealtimeClient();
        const localConnectSpy = vi.spyOn(loginClient, 'connect').mockImplementation(() => undefined);

        render(
          <QueryClientProvider client={queryClient}>
            <RealtimeProvider client={loginClient} autoConnect={true}>
              <div>Login View</div>
            </RealtimeProvider>
          </QueryClientProvider>,
        );

        expect(localConnectSpy).not.toHaveBeenCalled();
        expect(loginClient.state).toBe('closed');
      } finally {
        window.history.pushState({}, '', originalPathname);
      }
    });

    it('responds to kb:auth-logout and storage events by closing client on public auth route', () => {
      const originalPathname = window.location.pathname;
      try {
        window.history.pushState({}, '', '/login');
        const logoutClient = new RealtimeClient();
        logoutClient.state = 'open';
        const localCloseSpy = vi.spyOn(logoutClient, 'close').mockImplementation(() => {
          logoutClient.state = 'closed';
        });

        render(
          <QueryClientProvider client={queryClient}>
            <RealtimeProvider client={logoutClient} autoConnect={false}>
              <div>Logged Out</div>
            </RealtimeProvider>
          </QueryClientProvider>,
        );

        localCloseSpy.mockClear();

        act(() => {
          logoutClient.state = 'open';
          window.dispatchEvent(new CustomEvent('kb:auth-logout'));
        });
        expect(localCloseSpy).toHaveBeenCalledTimes(1);

        act(() => {
          logoutClient.state = 'open';
          window.dispatchEvent(new StorageEvent('storage', { key: 'kb_logout' }));
        });
        expect(localCloseSpy).toHaveBeenCalledTimes(2);

        act(() => {
          logoutClient.state = 'closed';
          window.dispatchEvent(new CustomEvent('kb:auth-logout'));
        });
        expect(localCloseSpy).toHaveBeenCalledTimes(2);
      } finally {
        window.history.pushState({}, '', originalPathname);
      }
    });

    it('queries /api/v1/auth/session via useQuery when session prop is omitted on protected path', async () => {
      const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ authenticated: true, mfa_pending: false }),
      } as Response);

      const queriedClient = new RealtimeClient();
      const localConnectSpy = vi.spyOn(queriedClient, 'connect').mockImplementation(() => undefined);

      const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });

      render(
        <QueryClientProvider client={qc}>
          <RealtimeProvider client={queriedClient} autoConnect={true}>
            <div>Protected View</div>
          </RealtimeProvider>
        </QueryClientProvider>,
      );

      await vi.waitFor(() => {
        expect(fetchSpy).toHaveBeenCalledWith(
          '/api/v1/auth/session',
          expect.objectContaining({ method: 'GET' }),
        );
      });
      await vi.waitFor(() => {
        expect(localConnectSpy).toHaveBeenCalled();
      });
    });

    it('handles /api/v1/auth/session failure in useQuery gracefully and fails closed', async () => {
      vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce({
        ok: false,
      } as Response);
      const wsSpy = vi.fn();
      vi.stubGlobal('WebSocket', wsSpy);
      const sseSpy = vi.fn();
      vi.stubGlobal('EventSource', sseSpy);

      const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
      const failClient = new RealtimeClient();
      const localConnectSpy = vi.spyOn(failClient, 'connect');

      render(
        <QueryClientProvider client={qc}>
          <RealtimeProvider client={failClient} autoConnect={true}>
            <div>Failing View</div>
          </RealtimeProvider>
        </QueryClientProvider>,
      );

      await vi.waitFor(() => {
        expect(failClient.isSessionAllowed()).toBe(false);
      });
      expect(localConnectSpy).not.toHaveBeenCalled();
      expect(wsSpy).not.toHaveBeenCalled();
      expect(sseSpy).not.toHaveBeenCalled();
      expect(failClient.state).toBe('closed');
    });

    it('handles /api/v1/auth/session network error rejection in useQuery gracefully and fails closed', async () => {
      vi.spyOn(globalThis, 'fetch').mockRejectedValueOnce(new Error('Network error'));
      const wsSpy = vi.fn();
      vi.stubGlobal('WebSocket', wsSpy);
      const sseSpy = vi.fn();
      vi.stubGlobal('EventSource', sseSpy);

      const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
      const errClient = new RealtimeClient();
      const localConnectSpy = vi.spyOn(errClient, 'connect');

      render(
        <QueryClientProvider client={qc}>
          <RealtimeProvider client={errClient} autoConnect={true}>
            <div>Error View</div>
          </RealtimeProvider>
        </QueryClientProvider>,
      );

      await vi.waitFor(() => {
        expect(errClient.isSessionAllowed()).toBe(false);
      });
      expect(localConnectSpy).not.toHaveBeenCalled();
      expect(wsSpy).not.toHaveBeenCalled();
      expect(sseSpy).not.toHaveBeenCalled();
      expect(errClient.state).toBe('closed');
    });

    it('closes open client when autoConnect is false but session is unauthenticated', () => {
      const openClient = new RealtimeClient();
      openClient.state = 'open';
      const closeSpy = vi.spyOn(openClient, 'close').mockImplementation(() => undefined);

      render(
        <QueryClientProvider client={queryClient}>
          <RealtimeProvider client={openClient} autoConnect={false} session={{ authenticated: false }}>
            <div>Closed</div>
          </RealtimeProvider>
        </QueryClientProvider>,
      );

      expect(closeSpy).toHaveBeenCalled();
    });

    it('handles session prop explicitly passed as null and fails closed', () => {
      const nullClient = new RealtimeClient();
      render(
        <QueryClientProvider client={queryClient}>
          <RealtimeProvider client={nullClient} autoConnect={false} session={null}>
            <div>Null session</div>
          </RealtimeProvider>
        </QueryClientProvider>,
      );
      expect(nullClient.isSessionAllowed()).toBe(false);
    });

    it('uses default getRealtimeClient when client prop is omitted', () => {
      render(
        <QueryClientProvider client={queryClient}>
          <RealtimeProvider autoConnect={false} bindInvalidation={false}>
            <div data-testid="no-client-prop">No prop</div>
          </RealtimeProvider>
        </QueryClientProvider>,
      );

      expect(screen.getByTestId('no-client-prop')).toBeDefined();
    });

    it('skips connect if client is already connecting or open', () => {
      const activeClient = new RealtimeClient();
      activeClient.state = 'connecting';
      const localConnectSpy = vi.spyOn(activeClient, 'connect');
      render(
        <QueryClientProvider client={queryClient}>
          <RealtimeProvider
            client={activeClient}
            autoConnect={true}
            session={{ authenticated: true, mfa_pending: false }}
          >
            <div>Active</div>
          </RealtimeProvider>
        </QueryClientProvider>,
      );
      expect(localConnectSpy).not.toHaveBeenCalled();
    });
  });
});
