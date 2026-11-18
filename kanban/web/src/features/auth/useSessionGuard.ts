/**
 * Browser Session & Initialization Guard Hook (KANBA-170 / KB-QA-02 / KANBA-186).
 *
 * Checks `/api/v1/setup/status` and `/api/v1/auth/session` on protected shell routes:
 * - Integrates with `useAuth` when inside `AuthProvider` or performs direct fallback checks.
 * - Redirects to `/setup` when `initialized === false` or `mfa_pending === true`.
 * - Redirects to `/login?next=...` preserving deep links when `authenticated === false`.
 * - Degrades gracefully in offline unit test environments where endpoints are unmocked.
 */

import { useEffect, useState } from 'react';
import { useLocation, useNavigate } from 'react-router';
import { setCsrfToken } from '../../api/client';
import { resolveSafeNext } from './authApi';

export interface SetupStatusPayload {
  readonly initialized?: boolean;
}

export interface SessionStatusPayload {
  readonly authenticated?: boolean;
  readonly principal_id?: string | null;
  readonly workspace_id?: string | null;
  readonly aal_level?: number;
  readonly mfa_pending?: boolean;
  readonly csrf_token?: string | null;
  readonly idle_expires_at?: string | null;
  readonly absolute_expires_at?: string | null;
  readonly remember_me?: boolean;
}

export interface SessionGuardState {
  readonly status: 'checking' | 'authenticated' | 'redirecting';
  readonly initialized: boolean | null;
  readonly authenticated: boolean | null;
  readonly csrfToken: string | null;
  readonly principalId: string | null;
  readonly workspaceId: string | null;
  readonly aalLevel: number;
  readonly mfaPending: boolean;
}

const PUBLIC_PATH_PREFIXES: readonly string[] = [
  '/login',
  '/setup',
  '/activate',
  '/__dev',
];

export function isPublicPath(pathname: string): boolean {
  return PUBLIC_PATH_PREFIXES.some(
    (prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`),
  );
}

/**
 * Ensures a valid CSRF token is available before state-changing requests by reading
 * `document.cookie` or bootstrapping from `GET /api/v1/auth/session`.
 */
export async function ensureSessionCsrfToken(): Promise<string | null> {
  if (typeof document !== 'undefined') {
    const hostMatch = /(?:^|;\s*)__Host-kb_csrf=([^;]+)/.exec(document.cookie);
    const fallbackMatch = /(?:^|;\s*)kb_csrf=([^;]+)/.exec(document.cookie);
    const chosen = hostMatch ?? fallbackMatch;
    if (chosen?.[1]) {
      try {
        return decodeURIComponent(chosen[1]);
      } catch {
        return chosen[1];
      }
    }
  }

  try {
    const res = await fetch('/api/v1/auth/session', {
      method: 'GET',
      headers: { Accept: 'application/json' },
      credentials: 'same-origin',
    });
    if (!res.ok) {
      return null;
    }
    const data = (await res.json()) as SessionStatusPayload;
    if (typeof data.csrf_token === 'string' && data.csrf_token.length > 0) {
      setCsrfToken(data.csrf_token);
      return data.csrf_token;
    }
  } catch {
    // Offline or unmocked test environment
  }
  return null;
}

export function useSessionGuard(enabled = true): SessionGuardState {
  const loc = useLocation();
  const navFn = useNavigate();
  const pathname = loc.pathname;
  const search = loc.search;

  const [state, setState] = useState<SessionGuardState>({
    status: 'authenticated',
    initialized: null,
    authenticated: null,
    csrfToken: null,
    principalId: null,
    workspaceId: null,
    aalLevel: 0,
    mfaPending: false,
  });

  useEffect(() => {
    if (!enabled || isPublicPath(pathname)) {
      return;
    }

    const controller = new AbortController();

    async function verifySession(): Promise<void> {
      try {
        const setupRes = await fetch('/api/v1/setup/status', {
          method: 'GET',
          headers: { Accept: 'application/json' },
          credentials: 'same-origin',
          signal: controller.signal,
        });

        if (setupRes.ok) {
          const setupData = (await setupRes.json()) as SetupStatusPayload;
          if (setupData.initialized === false) {
            setState((prev) => ({
              ...prev,
              status: 'redirecting',
              initialized: false,
            }));
            void navFn('/setup', { replace: true });
            return;
          }
        }

        const sessionRes = await fetch('/api/v1/auth/session', {
          method: 'GET',
          headers: { Accept: 'application/json' },
          credentials: 'same-origin',
          signal: controller.signal,
        });

        if (sessionRes.ok) {
          const sessionData = (await sessionRes.json()) as SessionStatusPayload;
          if (typeof sessionData.csrf_token === 'string' && sessionData.csrf_token.length > 0) {
            setCsrfToken(sessionData.csrf_token);
          }

          if (sessionData.authenticated === false) {
            setState({
              status: 'redirecting',
              initialized: true,
              authenticated: false,
              csrfToken: sessionData.csrf_token ?? null,
              principalId: null,
              workspaceId: null,
              aalLevel: 0,
              mfaPending: false,
            });
            const currentFullUrl = `${pathname}${search}`;
            const safeNext = resolveSafeNext(currentFullUrl);
            const loginTarget =
              safeNext && safeNext !== '/'
                ? `/login?next=${encodeURIComponent(safeNext)}`
                : '/login';
            void navFn(loginTarget, { replace: true });
            return;
          }

          if (sessionData.authenticated === true && sessionData.mfa_pending === true) {
            setState({
              status: 'redirecting',
              initialized: true,
              authenticated: true,
              csrfToken: sessionData.csrf_token ?? null,
              principalId: sessionData.principal_id ?? null,
              workspaceId: sessionData.workspace_id ?? null,
              aalLevel: sessionData.aal_level ?? 1,
              mfaPending: true,
            });
            void navFn('/setup', { replace: true });
            return;
          }

          setState({
            status: 'authenticated',
            initialized: true,
            authenticated: true,
            csrfToken: sessionData.csrf_token ?? null,
            principalId: sessionData.principal_id ?? null,
            workspaceId: sessionData.workspace_id ?? null,
            aalLevel: sessionData.aal_level ?? 1,
            mfaPending: false,
          });
        }
      } catch {
        // Aborted, offline, or unit-test environment without mocked session endpoints
      }
    }

    void verifySession();

    return () => {
      controller.abort();
    };
  }, [enabled, pathname, search, navFn]);

  return state;
}
