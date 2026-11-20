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
import { useQuery, useQueryClient } from '@tanstack/react-query';
import {
  RealtimeClient,
  bindQueryInvalidation,
  getRealtimeClient,
  type RealtimeEvent,
  type RealtimeEventHandler,
  type RealtimeSessionState,
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
  session?: RealtimeSessionState | null | undefined;
  children: ReactNode;
}

function isPublicAuthRoute(): boolean {
  /* v8 ignore next 3 */
  if (typeof window === 'undefined') {
    return false;
  }
  const path = window.location.pathname;
  return (
    path === '/login' ||
    path.startsWith('/login/') ||
    path === '/setup' ||
    path.startsWith('/setup/') ||
    path === '/activate' ||
    path.startsWith('/activate/')
  );
}

/**
 * Universal Realtime provider mounting client WebSocket / SSE connection
 * and binding TanStack Query cache invalidations across the tree.
 * Strictly gated so NO /ws or /sse connection is opened unless
 * session?.authenticated === true && session?.mfa_pending !== true (KAN-7).
 */
export function RealtimeProvider({
  client: propClient,
  autoConnect = true,
  bindInvalidation = true,
  session: propSession,
  children,
}: RealtimeProviderProps): JSX.Element {
  const queryClient = useQueryClient();
  const [client] = useState<RealtimeClient>(() => propClient ?? getRealtimeClient());
  const [state, setState] = useState<RealtimeState>(() => client.state);

  const sessionQuery = useQuery<RealtimeSessionState | null>({
    queryKey: ['auth', 'session'],
    queryFn: async ({ signal }) => {
      try {
        const res = await fetch('/api/v1/auth/session', {
          method: 'GET',
          headers: { Accept: 'application/json' },
          credentials: 'same-origin',
          signal,
        });
        if (res.ok) {
          return (await res.json()) as RealtimeSessionState;
        }
      } catch {
        // Fallback
      }
      return { authenticated: false, mfa_pending: false };
    },
    staleTime: 5000,
    retry: false,
    enabled: propSession === undefined && autoConnect && !isPublicAuthRoute(),
  });

  const effectiveSession: RealtimeSessionState = useMemo(() => {
    if (propSession !== undefined) {
      return propSession ?? { authenticated: false, mfa_pending: false };
    }
    if (isPublicAuthRoute()) {
      return { authenticated: false, mfa_pending: false };
    }
    const data = sessionQuery.data;
    if (data?.authenticated === true && data.mfa_pending !== true) {
      return data;
    }
    return { authenticated: false, mfa_pending: false };
  }, [propSession, sessionQuery.data]);

  const isPermitted =
    effectiveSession.authenticated === true && effectiveSession.mfa_pending !== true;

  useEffect(() => {
    client.setSession(effectiveSession);
  }, [client, effectiveSession]);

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
    (window as unknown as { __kanbanRealtimeClient?: RealtimeClient }).__kanbanRealtimeClient = client;
  }, [client]);

  useEffect(() => {
    if (autoConnect && isPermitted) {
      if (client.state === 'closed') {
        client.connect();
      }
    } else if (!isPermitted && client.state !== 'closed') {
      client.close();
    }
  }, [client, autoConnect, isPermitted]);

  useEffect(() => {
    /* v8 ignore next 3 */
    if (typeof window === 'undefined') {
      return undefined;
    }
    const handleAuthChange = () => {
      void queryClient.invalidateQueries({ queryKey: ['auth', 'session'] });
      if (client.state !== 'closed') {
        client.close();
      }
    };
    window.addEventListener('kb:auth-logout', handleAuthChange);
    window.addEventListener('storage', handleAuthChange);
    return () => {
      window.removeEventListener('kb:auth-logout', handleAuthChange);
      window.removeEventListener('storage', handleAuthChange);
    };
  }, [client, queryClient]);

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
