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

  it('auto-connects client on mount when autoConnect is true', () => {
    render(
      <QueryClientProvider client={queryClient}>
        <RealtimeProvider client={mockClient} autoConnect={true} bindInvalidation={false}>
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
});
