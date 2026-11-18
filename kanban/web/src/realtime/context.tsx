import React, {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type JSX,
  type ReactNode,
} from 'react';
import { useQueryClient } from '@tanstack/react-query';
import {
  RealtimeClient,
  bindQueryInvalidation,
  getRealtimeClient,
  type RealtimeEvent,
  type RealtimeEventHandler,
} from '../api/realtime';
import { type RealtimeState } from '../api/RealtimeStatus';

export interface RealtimeContextValue {
  client: RealtimeClient;
  state: RealtimeState;
}

export const RealtimeContext = createContext<RealtimeContextValue | null>(null);

export interface RealtimeProviderProps {
  client?: RealtimeClient | undefined;
  autoConnect?: boolean | undefined;
  bindInvalidation?: boolean | undefined;
  children: ReactNode;
}

/**
 * Universal Realtime provider mounting client WebSocket / SSE connection
 * and binding TanStack Query cache invalidations across the tree.
 */
export function RealtimeProvider({
  client: propClient,
  autoConnect = true,
  bindInvalidation = true,
  children,
}: RealtimeProviderProps): JSX.Element {
  const queryClient = useQueryClient();
  const [client] = useState<RealtimeClient>(() => propClient ?? getRealtimeClient());
  const [state, setState] = useState<RealtimeState>(() => client.state);

  useEffect(() => {
    return client.onStateChange((nextState) => {
      setState(nextState);
    });
  }, [client]);

  useEffect(() => {
    if (!bindInvalidation) {
      return undefined;
    }
    return bindQueryInvalidation(client, queryClient);
  }, [client, queryClient, bindInvalidation]);

  useEffect(() => {
    if (typeof window !== 'undefined') {
      (window as unknown as { __kanbanRealtimeClient?: RealtimeClient }).__kanbanRealtimeClient = client;
    }
  }, [client]);

  useEffect(() => {
    if (autoConnect) {
      client.connect();
    }
  }, [client, autoConnect]);

  const value = useMemo<RealtimeContextValue>(() => ({ client, state }), [client, state]);

  return <RealtimeContext.Provider value={value}>{children}</RealtimeContext.Provider>;
}

/**
 * Hook to access the active RealtimeClient instance.
 */
export function useRealtimeClient(): RealtimeClient {
  const ctx = useContext(RealtimeContext);
  return ctx ? ctx.client : getRealtimeClient();
}

/**
 * Hook to read the active live connection state ('connecting' | 'open' | 'reconnecting' | 'sse-fallback' | 'closed').
 */
export function useRealtimeLiveState(): RealtimeState {
  const ctx = useContext(RealtimeContext);
  return ctx ? ctx.state : 'open';
}

/**
 * Hook to subscribe to a realtime channel (e.g. `workspace:<id>`, `project:<id>`, `issue:<id>`).
 * Keeps the channel subscribed for the component lifetime and routes events to handler.
 */
export function useRealtimeSubscription(
  channel: string | null | undefined,
  handler?: RealtimeEventHandler,
): void {
  const client = useRealtimeClient();
  const savedHandler = useRef<RealtimeEventHandler | undefined>(handler);

  useEffect(() => {
    savedHandler.current = handler;
  });

  useEffect(() => {
    if (!channel) {
      return undefined;
    }
    const stableHandler: RealtimeEventHandler = (event: RealtimeEvent) => {
      savedHandler.current?.(event);
    };
    return client.subscribe(channel, stableHandler);
  }, [client, channel]);
}
