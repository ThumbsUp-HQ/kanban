// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, act, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { AuthProvider, useAuth, isPublicAuthPath } from './AuthContext';
import * as clientModule from '../../api/client';

describe('AuthContext and isPublicAuthPath', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  describe('isPublicAuthPath', () => {
    it('identifies public auth paths correctly', () => {
      expect(isPublicAuthPath('/login')).toBe(true);
      expect(isPublicAuthPath('/login/oauth')).toBe(true);
      expect(isPublicAuthPath('/setup')).toBe(true);
      expect(isPublicAuthPath('/setup/step-1')).toBe(true);
      expect(isPublicAuthPath('/activate')).toBe(true);
      expect(isPublicAuthPath('/activate/invite')).toBe(true);
      expect(isPublicAuthPath('/__dev')).toBe(true);
      expect(isPublicAuthPath('/__dev/mock')).toBe(true);
      expect(isPublicAuthPath('/workspaces')).toBe(false);
      expect(isPublicAuthPath('/projects/KAN/issues')).toBe(false);
      expect(isPublicAuthPath('/')).toBe(false);
    });
  });

  describe('useAuth fallback outside provider', () => {
    it('returns safe fallback value when used outside AuthProvider', async () => {
      let authValue: ReturnType<typeof useAuth> | undefined;

      function TestConsumer() {
        authValue = useAuth();
        return <div>Consumer</div>;
      }

      render(<TestConsumer />);

      expect(authValue).toBeDefined();
      expect(authValue?.session).toBeNull();
      expect(authValue?.isLoading).toBe(false);
      expect(authValue?.initialized).toBe(true);

      const refreshed = await authValue?.refreshSession();
      expect(refreshed).toBeNull();

      await expect(authValue?.logout()).resolves.toBeUndefined();
    });
  });

  describe('AuthProvider', () => {
    it('handles uninitialized server status by redirecting to /setup for private paths', async () => {
      const mockFetch = vi.fn().mockImplementation((url: string) => {
        if (url === '/api/v1/setup/status') {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve({ initialized: false }),
          });
        }
        return Promise.reject(new Error('Unexpected fetch'));
      });
      globalThis.fetch = mockFetch;

      function Consumer() {
        const { initialized, isLoading } = useAuth();
        return (
          <div>
            <span data-testid="initialized">{String(initialized)}</span>
            <span data-testid="loading">{String(isLoading)}</span>
          </div>
        );
      }

      render(
        <MemoryRouter initialEntries={['/projects/KAN']}>
          <AuthProvider>
            <Consumer />
          </AuthProvider>
        </MemoryRouter>,
      );

      await waitFor(() => {
        expect(screen.getByTestId('initialized').textContent).toBe('false');
        expect(screen.getByTestId('loading').textContent).toBe('false');
      });
    });

    it('stays on public path when uninitialized', async () => {
      const mockFetch = vi.fn().mockImplementation((url: string) => {
        if (url === '/api/v1/setup/status') {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve({ initialized: false }),
          });
        }
        return Promise.reject(new Error('Unexpected fetch'));
      });
      globalThis.fetch = mockFetch;

      function Consumer() {
        const { initialized } = useAuth();
        return <div data-testid="initialized">{String(initialized)}</div>;
      }

      render(
        <MemoryRouter initialEntries={['/setup']}>
          <AuthProvider>
            <Consumer />
          </AuthProvider>
        </MemoryRouter>,
      );

      await waitFor(() => {
        expect(screen.getByTestId('initialized').textContent).toBe('false');
      });
    });

    it('loads authenticated session and sets csrf token', async () => {
      const setCsrfSpy = vi.spyOn(clientModule, 'setCsrfToken');

      const mockFetch = vi.fn().mockImplementation((url: string) => {
        if (url === '/api/v1/setup/status') {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve({ initialized: true }),
          });
        }
        if (url === '/api/v1/auth/session') {
          return Promise.resolve({
            ok: true,
            json: () =>
              Promise.resolve({
                authenticated: true,
                principal_id: 'user-1',
                workspace_id: 'ws-1',
                aal_level: 1,
                mfa_pending: false,
                csrf_token: 'test-csrf-123',
              }),
          });
        }
        return Promise.reject(new Error('Unexpected fetch'));
      });
      globalThis.fetch = mockFetch;

      function Consumer() {
        const { session, isLoading } = useAuth();
        if (isLoading) return <div>Loading...</div>;
        return (
          <div>
            <span data-testid="auth">{String(session?.authenticated)}</span>
            <span data-testid="principal">{session?.principal_id}</span>
          </div>
        );
      }

      render(
        <MemoryRouter initialEntries={['/projects/KAN']}>
          <AuthProvider>
            <Consumer />
          </AuthProvider>
        </MemoryRouter>,
      );

      await waitFor(() => {
        expect(screen.getByTestId('auth').textContent).toBe('true');
        expect(screen.getByTestId('principal').textContent).toBe('user-1');
      });

      expect(setCsrfSpy).toHaveBeenCalledWith('test-csrf-123');
    });

    it('handles session fetch error and unauthenticated response', async () => {
      const mockFetch = vi.fn().mockImplementation((url: string) => {
        if (url === '/api/v1/setup/status') {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve({ initialized: true }),
          });
        }
        if (url === '/api/v1/auth/session') {
          return Promise.resolve({
            ok: false,
            status: 401,
          });
        }
        return Promise.reject(new Error('Offline'));
      });
      globalThis.fetch = mockFetch;

      function Consumer() {
        const { session, isLoading } = useAuth();
        return (
          <div>
            <span data-testid="loading">{String(isLoading)}</span>
            <span data-testid="session">{session ? 'present' : 'none'}</span>
          </div>
        );
      }

      render(
        <MemoryRouter initialEntries={['/login']}>
          <AuthProvider>
            <Consumer />
          </AuthProvider>
        </MemoryRouter>,
      );

      await waitFor(() => {
        expect(screen.getByTestId('loading').textContent).toBe('false');
        expect(screen.getByTestId('session').textContent).toBe('none');
      });
    });

    it('handles logout and navigates to login with csrf token header', async () => {
      const setCsrfSpy = vi.spyOn(clientModule, 'setCsrfToken');

      const mockFetch = vi.fn().mockImplementation((url: string) => {
        if (url === '/api/v1/setup/status') {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve({ initialized: true }),
          });
        }
        if (url === '/api/v1/auth/session') {
          return Promise.resolve({
            ok: true,
            json: () =>
              Promise.resolve({
                authenticated: true,
                principal_id: 'user-1',
                workspace_id: 'ws-1',
                aal_level: 1,
                mfa_pending: false,
                csrf_token: 'csrf-logout-test',
              }),
          });
        }
        if (url === '/api/v1/auth/logout') {
          return Promise.resolve({ ok: true });
        }
        return Promise.reject(new Error('Unexpected fetch'));
      });
      globalThis.fetch = mockFetch;

      function Consumer() {
        const auth = useAuth();
        return (
          <div>
            <div data-testid="auth-state">{auth.session ? 'authenticated' : 'logged-out'}</div>
            <button data-testid="logout-btn" onClick={() => void auth.logout()}>
              Logout
            </button>
          </div>
        );
      }

      render(
        <MemoryRouter initialEntries={['/projects/KAN']}>
          <AuthProvider>
            <Consumer />
          </AuthProvider>
        </MemoryRouter>,
      );

      await waitFor(() => {
        expect(screen.getByTestId('auth-state').textContent).toBe('authenticated');
      });

      act(() => {
        screen.getByTestId('logout-btn').click();
      });

      await waitFor(() => {
        expect(screen.getByTestId('auth-state').textContent).toBe('logged-out');
      });

      const logoutCall = (mockFetch.mock.calls as [string, RequestInit | undefined][]).find(
        (c) => c[0] === '/api/v1/auth/logout',
      );
      expect(logoutCall).toBeDefined();
      expect(logoutCall?.[1]?.method).toBe('POST');
      expect((logoutCall?.[1]?.headers as Record<string, string> | undefined)?.['X-CSRF-Token']).toBe('csrf-logout-test');
      expect(setCsrfSpy).toHaveBeenCalledWith(null);
    });

    it('handles logout network exception gracefully without throwing', async () => {
      const mockFetch = vi.fn().mockImplementation((url: string) => {
        if (url === '/api/v1/setup/status') {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve({ initialized: true }),
          });
        }
        if (url === '/api/v1/auth/session') {
          return Promise.resolve({
            ok: true,
            json: () =>
              Promise.resolve({
                authenticated: true,
                principal_id: 'user-2',
                workspace_id: 'ws-1',
                aal_level: 1,
                mfa_pending: false,
                csrf_token: null,
              }),
          });
        }
        if (url === '/api/v1/auth/logout') {
          return Promise.reject(new Error('Network error on logout'));
        }
        return Promise.reject(new Error('Unexpected fetch'));
      });
      globalThis.fetch = mockFetch;

      function Consumer() {
        const auth = useAuth();
        return (
          <div>
            <div data-testid="auth-state">{auth.session ? 'authenticated' : 'logged-out'}</div>
            <button data-testid="logout-btn" onClick={() => void auth.logout()}>
              Logout
            </button>
          </div>
        );
      }

      render(
        <MemoryRouter initialEntries={['/projects/KAN']}>
          <AuthProvider>
            <Consumer />
          </AuthProvider>
        </MemoryRouter>,
      );

      await waitFor(() => {
        expect(screen.getByTestId('auth-state').textContent).toBe('authenticated');
      });

      act(() => {
        screen.getByTestId('logout-btn').click();
      });

      await waitFor(() => {
        expect(screen.getByTestId('auth-state').textContent).toBe('logged-out');
      });
    });
  });
});
