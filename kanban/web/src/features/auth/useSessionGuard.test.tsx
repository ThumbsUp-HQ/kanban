import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import {
  isPublicPath,
  ensureSessionCsrfToken,
  useSessionGuard,
} from './useSessionGuard';

function TestGuardComponent({ enabled = true }: { enabled?: boolean }) {
  const guard = useSessionGuard(enabled);
  return (
    <div>
      <span data-testid="status">{guard.status}</span>
      <span data-testid="authenticated">{String(guard.authenticated)}</span>
      <span data-testid="mfaPending">{String(guard.mfaPending)}</span>
    </div>
  );
}

describe('useSessionGuard & CSRF bootstrap', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe('isPublicPath', () => {
    it('correctly identifies public and protected paths', () => {
      expect(isPublicPath('/login')).toBe(true);
      expect(isPublicPath('/login/callback')).toBe(true);
      expect(isPublicPath('/setup')).toBe(true);
      expect(isPublicPath('/activate')).toBe(true);
      expect(isPublicPath('/__dev')).toBe(true);
      expect(isPublicPath('/')).toBe(false);
      expect(isPublicPath('/projects')).toBe(false);
      expect(isPublicPath('/projects/KAN/issues')).toBe(false);
    });
  });

  describe('ensureSessionCsrfToken', () => {
    it('extracts CSRF token from document.cookie when available', async () => {
      Object.defineProperty(document, 'cookie', {
        writable: true,
        value: '__Host-kb_csrf=host-csrf-token-123; other=value',
      });

      const token = await ensureSessionCsrfToken();
      expect(token).toBe('host-csrf-token-123');
    });

    it('extracts fallback kb_csrf cookie when __Host-kb_csrf is absent', async () => {
      Object.defineProperty(document, 'cookie', {
        writable: true,
        value: 'kb_csrf=fallback-csrf-token-456; other=value',
      });

      const token = await ensureSessionCsrfToken();
      expect(token).toBe('fallback-csrf-token-456');
    });

    it('returns raw cookie value if decodeURIComponent throws', async () => {
      Object.defineProperty(document, 'cookie', {
        writable: true,
        value: '__Host-kb_csrf=%E0%A4%A; other=val',
      });
      const token = await ensureSessionCsrfToken();
      expect(token).toBe('%E0%A4%A');
    });

    it('returns null when /api/v1/auth/session returns not ok', async () => {
      Object.defineProperty(document, 'cookie', {
        writable: true,
        value: '',
      });
      vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce({
        ok: false,
      } as Response);
      const token = await ensureSessionCsrfToken();
      expect(token).toBeNull();
    });

    it('fetches CSRF token from /api/v1/auth/session when no cookie exists', async () => {
      Object.defineProperty(document, 'cookie', {
        writable: true,
        value: '',
      });

      vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ csrf_token: 'api-fetched-csrf-789' }),
      } as Response);

      const token = await ensureSessionCsrfToken();
      expect(token).toBe('api-fetched-csrf-789');
    });

    it('returns null when /api/v1/auth/session returns csrf_token that is not a non-empty string', async () => {
      Object.defineProperty(document, 'cookie', {
        writable: true,
        value: '',
      });

      vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ csrf_token: '' }),
      } as Response);

      const token = await ensureSessionCsrfToken();
      expect(token).toBeNull();
    });

    it('returns null when /api/v1/auth/session fetch fails or rejects', async () => {
      Object.defineProperty(document, 'cookie', {
        writable: true,
        value: '',
      });

      vi.spyOn(globalThis, 'fetch').mockRejectedValueOnce(new Error('Network drop'));

      const token = await ensureSessionCsrfToken();
      expect(token).toBeNull();
    });
  });

  describe('useSessionGuard lifecycle & auth logout dispatch', () => {
    it('does nothing when enabled is false or on a public path', () => {
      const fetchSpy = vi.spyOn(globalThis, 'fetch');

      render(
        <MemoryRouter initialEntries={['/login']}>
          <TestGuardComponent enabled={true} />
        </MemoryRouter>,
      );

      expect(fetchSpy).not.toHaveBeenCalled();
      expect(screen.getByTestId('status').textContent).toBe('authenticated');
    });

    it('dispatches kb:auth-logout and redirects to /setup when initialized is false', async () => {
      const logoutEventSpy = vi.fn();
      window.addEventListener('kb:auth-logout', logoutEventSpy);

      vi.spyOn(globalThis, 'fetch').mockImplementation((input) => {
        const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
        if (url.includes('/api/v1/setup/status')) {
          return Promise.resolve(
            new Response(JSON.stringify({ initialized: false }), { status: 200 }),
          );
        }
        return Promise.resolve(new Response(null, { status: 404 }));
      });

      render(
        <MemoryRouter initialEntries={['/projects/KAN']}>
          <TestGuardComponent enabled={true} />
        </MemoryRouter>,
      );

      await waitFor(() => {
        expect(screen.getByTestId('status').textContent).toBe('redirecting');
      });
      expect(logoutEventSpy).toHaveBeenCalled();
      window.removeEventListener('kb:auth-logout', logoutEventSpy);
    });

    it('dispatches kb:auth-logout and redirects to /login when authenticated is false', async () => {
      const logoutEventSpy = vi.fn();
      window.addEventListener('kb:auth-logout', logoutEventSpy);

      vi.spyOn(globalThis, 'fetch').mockImplementation((input) => {
        const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
        if (url.includes('/api/v1/setup/status')) {
          return Promise.resolve(
            new Response(JSON.stringify({ initialized: true }), { status: 200 }),
          );
        }
        if (url.includes('/api/v1/auth/session')) {
          return Promise.resolve(
            new Response(
              JSON.stringify({ authenticated: false, csrf_token: 'test-csrf' }),
              { status: 200 },
            ),
          );
        }
        return Promise.resolve(new Response(null, { status: 404 }));
      });

      render(
        <MemoryRouter initialEntries={['/projects/KAN/issues']}>
          <TestGuardComponent enabled={true} />
        </MemoryRouter>,
      );

      await waitFor(() => {
        expect(screen.getByTestId('status').textContent).toBe('redirecting');
      });
      expect(logoutEventSpy).toHaveBeenCalled();
      window.removeEventListener('kb:auth-logout', logoutEventSpy);
    });

    it('dispatches kb:auth-logout and redirects to /login when mfa_pending is true', async () => {
      const logoutEventSpy = vi.fn();
      window.addEventListener('kb:auth-logout', logoutEventSpy);

      vi.spyOn(globalThis, 'fetch').mockImplementation((input) => {
        const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
        if (url.includes('/api/v1/setup/status')) {
          return Promise.resolve(
            new Response(JSON.stringify({ initialized: true }), { status: 200 }),
          );
        }
        if (url.includes('/api/v1/auth/session')) {
          return Promise.resolve(
            new Response(
              JSON.stringify({
                authenticated: true,
                mfa_pending: true,
                csrf_token: 'test-csrf-mfa',
              }),
              { status: 200 },
            ),
          );
        }
        return Promise.resolve(new Response(null, { status: 404 }));
      });

      render(
        <MemoryRouter initialEntries={['/projects/KAN/issues']}>
          <TestGuardComponent enabled={true} />
        </MemoryRouter>,
      );

      await waitFor(() => {
        expect(screen.getByTestId('status').textContent).toBe('redirecting');
      });
      expect(screen.getByTestId('mfaPending').textContent).toBe('true');
      expect(logoutEventSpy).toHaveBeenCalled();
      window.removeEventListener('kb:auth-logout', logoutEventSpy);
    });

    it('sets authenticated state when session is active and mfa_pending is false', async () => {
      vi.spyOn(globalThis, 'fetch').mockImplementation((input) => {
        const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
        if (url.includes('/api/v1/setup/status')) {
          return Promise.resolve(
            new Response(JSON.stringify({ initialized: true }), { status: 200 }),
          );
        }
        if (url.includes('/api/v1/auth/session')) {
          return Promise.resolve(
            new Response(
              JSON.stringify({
                authenticated: true,
                mfa_pending: false,
                principal_id: 'prin-1',
                workspace_id: 'ws-1',
                csrf_token: 'valid-csrf',
              }),
              { status: 200 },
            ),
          );
        }
        return Promise.resolve(new Response(null, { status: 404 }));
      });

      render(
        <MemoryRouter initialEntries={['/projects/KAN/issues']}>
          <TestGuardComponent enabled={true} />
        </MemoryRouter>,
      );

      await waitFor(() => {
        expect(screen.getByTestId('status').textContent).toBe('authenticated');
        expect(screen.getByTestId('authenticated').textContent).toBe('true');
        expect(screen.getByTestId('mfaPending').textContent).toBe('false');
      });
    });

    it('handles unauthenticated redirect when path is root / without deep link next', async () => {
      const logoutEventSpy = vi.fn();
      window.addEventListener('kb:auth-logout', logoutEventSpy);

      vi.spyOn(globalThis, 'fetch').mockImplementation((input) => {
        const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
        if (url.includes('/api/v1/setup/status')) {
          return Promise.resolve(
            new Response(JSON.stringify({ initialized: true }), { status: 200 }),
          );
        }
        if (url.includes('/api/v1/auth/session')) {
          return Promise.resolve(
            new Response(JSON.stringify({ authenticated: false }), { status: 200 }),
          );
        }
        return Promise.resolve(new Response(null, { status: 404 }));
      });

      render(
        <MemoryRouter initialEntries={['/']}>
          <TestGuardComponent enabled={true} />
        </MemoryRouter>,
      );

      await waitFor(() => {
        expect(screen.getByTestId('status').textContent).toBe('redirecting');
      });
      expect(logoutEventSpy).toHaveBeenCalled();
      window.removeEventListener('kb:auth-logout', logoutEventSpy);
    });

    it('sets authenticated state with fallback nulls when optional fields are omitted', async () => {
      vi.spyOn(globalThis, 'fetch').mockImplementation((input) => {
        const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
        if (url.includes('/api/v1/setup/status')) {
          return Promise.resolve(new Response(null, { status: 500 }));
        }
        if (url.includes('/api/v1/auth/session')) {
          return Promise.resolve(
            new Response(
              JSON.stringify({
                authenticated: true,
                mfa_pending: false,
              }),
              { status: 200 },
            ),
          );
        }
        return Promise.resolve(new Response(null, { status: 404 }));
      });

      render(
        <MemoryRouter initialEntries={['/projects/KAN']}>
          <TestGuardComponent enabled={true} />
        </MemoryRouter>,
      );

      await waitFor(() => {
        expect(screen.getByTestId('status').textContent).toBe('authenticated');
      });
    });

    it('handles offline or fetch exceptions gracefully', () => {
      vi.spyOn(globalThis, 'fetch').mockRejectedValueOnce(new Error('Network drop'));
      render(
        <MemoryRouter initialEntries={['/projects/KAN/issues']}>
          <TestGuardComponent enabled={true} />
        </MemoryRouter>,
      );
      expect(screen.getByTestId('status').textContent).toBe('authenticated');
    });
  });
});
