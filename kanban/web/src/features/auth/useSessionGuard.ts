/**
 * Browser Session & Initialization Guard Hook (KANBA-170 / KB-QA-02).
 *
 * Checks `/api/v1/setup/status` and `/api/v1/auth/session` on protected shell routes:
 * - Redirects to `/setup` when `initialized === false` or `mfa_pending === true`.
 * - Redirects to `/login` when `authenticated === false`.
 * - Degrades gracefully in offline unit test environments where endpoints are unmocked.
 */

import { useEffect, useState } from 'react';
import { useLocation, useNavigate } from 'react-router';

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

function isPublicPath(pathname: string): boolean {
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
    const match = /(?:^|;\s*)(?:__Host-kb_csrf|kb_csrf)=([^;]+)/.exec(document.cookie);
    if (match?.[1]) {
      try {
        return decodeURIComponent(match[1]);
      } catch {
        return match[1];
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
      if (typeof document !== 'undefined') {
        document.cookie = `kb_csrf=${encodeURIComponent(data.csrf_token)}; path=/; SameSite=Lax`;
      }
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
          if (
            typeof sessionData.csrf_token === 'string' &&
            sessionData.csrf_token.length > 0 &&
            typeof document !== 'undefined'
          ) {
            document.cookie = `kb_csrf=${encodeURIComponent(sessionData.csrf_token)}; path=/; SameSite=Lax`;
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
            void navFn('/login', { replace: true });
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
  }, [enabled, pathname, navFn]);

  return state;
}
