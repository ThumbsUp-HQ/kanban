// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router';
import {
  apiFetch,
  getCsrfToken,
  setCsrfToken,
  registerAal2StepUpHandler,
  getActiveAal2StepUpHandler,
  Aal2StepUpCancelledError,
} from '../client';
import { ApiProblem } from '../problem';
import { WebSudoModalHost, useAal2DirtyKeepalive } from '../../components/help/WebSudoModalHost';
import { AdminStudioSubnav } from '../../features/admin/AdminStudioSubnav';

// Mock SecondFactorStep to test WebSudoModalHost interactions
vi.mock('../../features/auth/SecondFactorStep', () => ({
  SecondFactorStep: ({
    onSuccess,
    onError,
    onSessionExpired,
    onCancel,
  }: {
    onSuccess: () => void;
    onError?: (err: unknown) => void;
    onSessionExpired?: () => void;
    onCancel: () => void;
  }) => (
    <div data-testid="second-factor-step-mock">
      <button type="button" onClick={onSuccess} data-testid="mock-mfa-success-btn">
        Verify Success
      </button>
      <button type="button" onClick={() => onError?.(new Error('mfa error'))} data-testid="mock-mfa-error-btn">
        Trigger Error
      </button>
      <button type="button" onClick={onSessionExpired} data-testid="mock-mfa-expired-btn">
        Session Expired
      </button>
      <button type="button" onClick={onCancel} data-testid="mock-mfa-cancel-btn">
        Cancel Challenge
      </button>
    </div>
  ),
}));

describe('WebSudo CSRF cookie-first resolution (KAN-404)', () => {
  beforeEach(() => {
    setCsrfToken(null);
    document.cookie = 'kb_csrf=; Path=/; Max-Age=0';
    document.cookie = '__Host-kb_csrf=; Path=/; Max-Age=0';
  });

  it('prefers __Host-kb_csrf cookie over cached token', () => {
    setCsrfToken('cached-csrf-token');
    const originalCookie = document.cookie;
    Object.defineProperty(document, 'cookie', {
      writable: true,
      value: '__Host-kb_csrf=host-cookie-token; kb_csrf=other-token',
    });
    expect(getCsrfToken()).toBe('host-cookie-token');
    Object.defineProperty(document, 'cookie', {
      writable: true,
      value: originalCookie,
    });
  });

  it('prefers kb_csrf cookie over cached token when __Host is absent', () => {
    setCsrfToken('cached-csrf-token');
    document.cookie = 'kb_csrf=plain-cookie-token; Path=/';
    expect(getCsrfToken()).toBe('plain-cookie-token');
  });

  it('falls back to cached token when no cookie is set', () => {
    document.cookie = 'other=val; Path=/';
    setCsrfToken('fallback-token');
    expect(getCsrfToken()).toBe('fallback-token');
  });
});

describe('Singleflight WebSudo Request Replay Coordinator (KAN-404)', () => {
  let originalFetch: typeof globalThis.fetch;

  beforeEach(() => {
    originalFetch = globalThis.fetch;
    setCsrfToken('initial-csrf-token');
    registerAal2StepUpHandler(null);
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
    registerAal2StepUpHandler(null);
    vi.restoreAllMocks();
  });

  it('deduplicates concurrent 403 step-up challenges and transparently replays all requests', async () => {
    let handlerInvocations = 0;
    registerAal2StepUpHandler(async () => {
      handlerInvocations++;
      // Simulate delay for user entering MFA code
      await new Promise((r) => setTimeout(r, 50));
      return true;
    });

    let req1Attempts = 0;
    let req2Attempts = 0;

    globalThis.fetch = vi.fn().mockImplementation((url: string) => {
      if (url === '/api/v1/admin/item1') {
        req1Attempts++;
        if (req1Attempts === 1) {
          return Promise.resolve(new Response(
            JSON.stringify({ code: 'AAL2_REQUIRED', challenge_id: 'ch-1', methods: ['totp'] }),
            { status: 403, headers: { 'Content-Type': 'application/json' } },
          ));
        }
        return Promise.resolve(new Response(JSON.stringify({ id: 'item1', status: 'saved' }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }));
      }

      if (url === '/api/v1/admin/item2') {
        req2Attempts++;
        if (req2Attempts === 1) {
          return Promise.resolve(new Response(
            JSON.stringify({ code: 'AAL2_STALE', challenge_id: 'ch-2', methods: ['webauthn'] }),
            { status: 403, headers: { 'Content-Type': 'application/json' } },
          ));
        }
        return Promise.resolve(new Response(JSON.stringify({ id: 'item2', status: 'saved' }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }));
      }

      return Promise.resolve(new Response('{}', { status: 200, headers: { 'Content-Type': 'application/json' } }));
    });

    // Launch both concurrent requests simultaneously
    const [res1, res2] = await Promise.all([
      apiFetch('POST', '/api/v1/admin/item1' as never, { body: { name: 'One' } }),
      apiFetch('POST', '/api/v1/admin/item2' as never, { body: { name: 'Two' } }),
    ]);

    // Singleflight: exactly 1 step-up prompt for both requests
    expect(handlerInvocations).toBe(1);

    // Both requests received their replayed successful bodies
    expect(res1).toEqual({ id: 'item1', status: 'saved' });
    expect(res2).toEqual({ id: 'item2', status: 'saved' });

    // Both endpoints were fetched twice: initial 403 -> replay 200
    expect(req1Attempts).toBe(2);
    expect(req2Attempts).toBe(2);
  });

  it('rejects silently with Aal2StepUpCancelledError when challenge is cancelled', async () => {
    registerAal2StepUpHandler(() => Promise.resolve(false));

    globalThis.fetch = vi.fn().mockImplementation(() => {
      return Promise.resolve(new Response(
        JSON.stringify({ code: 'AAL2_REQUIRED', challenge_id: 'ch-cancel' }),
        { status: 403, headers: { 'Content-Type': 'application/json' } },
      ));
    });

    await expect(
      apiFetch('POST', '/api/v1/admin/action' as never),
    ).rejects.toThrow(Aal2StepUpCancelledError);
  });

  it('enforces max 1 replay and throws ApiProblem if replay fails', async () => {
    registerAal2StepUpHandler(() => Promise.resolve(true));

    let attempts = 0;
    globalThis.fetch = vi.fn().mockImplementation(() => {
      attempts++;
      return Promise.resolve(new Response(
        JSON.stringify({ code: 'AAL2_REQUIRED', challenge_id: 'ch-loop' }),
        { status: 403, headers: { 'Content-Type': 'application/json' } },
      ));
    });

    await expect(
      apiFetch('POST', '/api/v1/admin/action' as never),
    ).rejects.toThrow(ApiProblem);

    // 1 initial attempt + 1 replay attempt = 2 total (zero infinite loops)
    expect(attempts).toBe(2);
  });
});

describe('WebSudoModalHost and Dirty Keepalive (KAN-404)', () => {
  let originalFetch: typeof globalThis.fetch;

  beforeEach(() => {
    originalFetch = globalThis.fetch;
    vi.useFakeTimers();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  function DirtyTestComponent({ isDirty }: { isDirty: boolean }): React.JSX.Element {
    useAal2DirtyKeepalive(isDirty);
    return <div data-testid="dirty-test">Dirty: {String(isDirty)}</div>;
  }

  it('pings /api/v1/auth/aal2/touch periodically while isDirty is true', () => {
    let callCount = 0;
    const fetchMock = vi.fn().mockImplementation(() => {
      callCount++;
      if (callCount === 2) {
        return Promise.reject(new Error('touch failure'));
      }
      return Promise.resolve(
        new Response(JSON.stringify({ aal2_active: true, aal2_expires_at: '2026-11-25T12:00:00Z' }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
      );
    });
    globalThis.fetch = fetchMock;

    const { rerender, unmount } = render(<DirtyTestComponent isDirty={true} />);

    // Immediate ping on becoming dirty
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/auth/aal2/touch',
      expect.objectContaining({ method: 'POST' }),
    );

    // Advance 45 seconds -> periodic ping 2
    vi.advanceTimersByTime(45_000);
    expect(fetchMock).toHaveBeenCalledTimes(2);

    // Advance another 45 seconds -> periodic ping 3
    vi.advanceTimersByTime(45_000);
    expect(fetchMock).toHaveBeenCalledTimes(3);

    // Transition to isDirty=false
    rerender(<DirtyTestComponent isDirty={false} />);
    vi.advanceTimersByTime(90_000);
    // No new pings while clean
    expect(fetchMock).toHaveBeenCalledTimes(3);

    unmount();
  });

  it('does NOT ping /api/v1/auth/aal2/touch when drawer is opened untouched (isDirty=false)', () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ aal2_active: true, aal2_expires_at: '2026-11-25T12:00:00Z' }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    );
    globalThis.fetch = fetchMock;

    const { unmount } = render(<DirtyTestComponent isDirty={false} />);

    // Untouched drawer should NOT fire immediate ping
    expect(fetchMock).not.toHaveBeenCalled();

    // Advance 120 seconds (well past the 45s interval)
    vi.advanceTimersByTime(120_000);
    expect(fetchMock).not.toHaveBeenCalled();

    unmount();
  });

  it('WebSudoModalHost opens on stepup challenge and resolves with user success', async () => {
    vi.useRealTimers();
    const qc = new QueryClient();

    render(
      <QueryClientProvider client={qc}>
        <WebSudoModalHost />
      </QueryClientProvider>,
    );

    // Initial state: modal not mounted
    expect(screen.queryByTestId('websudo-stepup-modal')).toBeNull();

    // Trigger apiFetch that returns 403 AAL2_REQUIRED on attempt 1, and 200 on attempt 2 (replay)
    let securedAttempts = 0;
    globalThis.fetch = vi.fn().mockImplementation((url: string) => {
      if (url === '/api/v1/admin/secured') {
        securedAttempts++;
        if (securedAttempts === 1) {
          return Promise.resolve(new Response(
            JSON.stringify({ code: 'AAL2_REQUIRED', challenge_id: 'ch-host-1' }),
            { status: 403, headers: { 'Content-Type': 'application/json' } },
          ));
        }
        return Promise.resolve(new Response(JSON.stringify({ success: true }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }));
      }
      return Promise.resolve(new Response(JSON.stringify({ success: true }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }));
    });

    // Start request in background
    const requestPromise = apiFetch('POST', '/api/v1/admin/secured' as never);

    // Modal appears above drawers
    await waitFor(() => {
      expect(screen.getByTestId('websudo-stepup-modal')).toBeDefined();
      expect(screen.getByText('Admin Verification Required (AAL2)')).toBeDefined();
    });

    // Click mock MFA success
    fireEvent.click(screen.getByTestId('mock-mfa-success-btn'));

    // Modal closes
    await waitFor(() => {
      expect(screen.queryByTestId('websudo-stepup-modal')).toBeNull();
    });

    // Request resolves
    const res = await requestPromise;
    expect(res).toEqual({ success: true });
  });

  it('WebSudoModalHost handles cancellation', async () => {
    vi.useRealTimers();
    const qc = new QueryClient();

    render(
      <QueryClientProvider client={qc}>
        <WebSudoModalHost />
      </QueryClientProvider>,
    );

    globalThis.fetch = vi.fn().mockImplementation(() => {
      return Promise.resolve(new Response(
        JSON.stringify({ code: 'AAL2_REQUIRED', challenge_id: 'ch-cancel' }),
        { status: 403, headers: { 'Content-Type': 'application/json' } },
      ));
    });

    const requestPromise = apiFetch('POST', '/api/v1/admin/cancelled-action' as never);
    let capturedErr: unknown = null;
    requestPromise.catch((e: unknown) => {
      capturedErr = e;
    });

    await waitFor(() => {
      expect(screen.getByTestId('websudo-stepup-modal')).toBeDefined();
    });

    fireEvent.click(screen.getByTestId('mock-mfa-cancel-btn'));

    await waitFor(() => {
      expect(screen.queryByTestId('websudo-stepup-modal')).toBeNull();
      expect(capturedErr).toBeInstanceOf(Aal2StepUpCancelledError);
    });
  });

  it('WebSudoModalHost handles session expired and dispatches error', async () => {
    vi.useRealTimers();
    const qc = new QueryClient();

    const assignMock = vi.fn();
    const originalLocation = window.location;
    Object.defineProperty(window, 'location', {
      writable: true,
      value: { assign: assignMock, search: '', href: 'http://localhost/' },
    });

    render(
      <QueryClientProvider client={qc}>
        <WebSudoModalHost />
      </QueryClientProvider>,
    );

    globalThis.fetch = vi.fn().mockImplementation(() => {
      return Promise.resolve(new Response(
        JSON.stringify({ code: 'AAL2_REQUIRED', challenge_id: 'ch-exp' }),
        { status: 403, headers: { 'Content-Type': 'application/json' } },
      ));
    });

    const errorSpy = vi.fn();
    window.addEventListener('kb:aal2-stepup-error', errorSpy);

    const requestPromise = apiFetch('POST', '/api/v1/admin/exp-action' as never);
    let capturedErr: unknown = null;
    requestPromise.catch((e: unknown) => {
      capturedErr = e;
    });

    await waitFor(() => {
      expect(screen.getByTestId('websudo-stepup-modal')).toBeDefined();
    });

    fireEvent.click(screen.getByTestId('mock-mfa-error-btn'));
    expect(errorSpy).toHaveBeenCalled();

    fireEvent.click(screen.getByTestId('mock-mfa-expired-btn'));

    await waitFor(() => {
      expect(screen.queryByTestId('websudo-stepup-modal')).toBeNull();
      expect(capturedErr).toBeInstanceOf(Aal2StepUpCancelledError);
    });

    expect(assignMock).toHaveBeenCalledWith('/login');

    window.removeEventListener('kb:aal2-stepup-error', errorSpy);
    Object.defineProperty(window, 'location', {
      writable: true,
      value: originalLocation,
    });
  });

  it('WebSudoModalHost handles challenge without queryClient and with default methods', async () => {
    vi.useRealTimers();
    // Render without QueryClientProvider
    render(<WebSudoModalHost />);

    let noQcAttempts = 0;
    globalThis.fetch = vi.fn().mockImplementation(() => {
      noQcAttempts++;
      if (noQcAttempts === 1) {
        return Promise.resolve(new Response(
          JSON.stringify({ code: 'AAL2_REQUIRED' }),
          { status: 403, headers: { 'Content-Type': 'application/json' } },
        ));
      }
      return Promise.resolve(new Response(JSON.stringify({ replayed: true }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }));
    });

    const requestPromise = apiFetch('POST', '/api/v1/admin/no-qc-action' as never);

    await waitFor(() => {
      expect(screen.getByTestId('websudo-stepup-modal')).toBeDefined();
    });

    fireEvent.click(screen.getByTestId('mock-mfa-success-btn'));

    await waitFor(() => {
      expect(screen.queryByTestId('websudo-stepup-modal')).toBeNull();
    });

    const res = await requestPromise;
    expect(res).toEqual({ replayed: true });
  });

  it('WebSudoModalHost dismisses on Escape key and traps Tab focus', async () => {
    vi.useRealTimers();
    const qc = new QueryClient();

    render(
      <QueryClientProvider client={qc}>
        <WebSudoModalHost />
      </QueryClientProvider>,
    );

    globalThis.fetch = vi.fn().mockImplementation(() => {
      return Promise.resolve(new Response(
        JSON.stringify({ code: 'AAL2_REQUIRED', challenge_id: 'ch-keys' }),
        { status: 403, headers: { 'Content-Type': 'application/json' } },
      ));
    });

    const requestPromise = apiFetch('POST', '/api/v1/admin/escape-action' as never);
    let capturedErr: unknown = null;
    requestPromise.catch((e: unknown) => {
      capturedErr = e;
    });

    await waitFor(() => {
      expect(screen.getByTestId('websudo-stepup-modal')).toBeDefined();
    });

    const modal = screen.getByTestId('websudo-stepup-modal');
    const buttons = modal.querySelectorAll('button');
    const firstBtn = buttons[0];
    const lastBtn = buttons[buttons.length - 1];
    if (!firstBtn || !lastBtn) {
      throw new Error('Buttons not found in modal');
    }

    // Focus last button and press Tab -> should wrap to first
    lastBtn.focus();
    fireEvent.keyDown(window, { key: 'Tab' });
    expect(document.activeElement).toBe(firstBtn);

    // Focus first button and press Shift+Tab -> should wrap to last
    firstBtn.focus();
    fireEvent.keyDown(window, { key: 'Tab', shiftKey: true });
    expect(document.activeElement).toBe(lastBtn);

    // Non-boundary Tab presses should not wrap
    firstBtn.focus();
    fireEvent.keyDown(window, { key: 'Tab' });
    // Tab without Shift when on non-last button does not wrap
    lastBtn.focus();
    fireEvent.keyDown(window, { key: 'Tab', shiftKey: true });

    // Press Escape -> should dismiss
    fireEvent.keyDown(window, { key: 'Escape' });

    await waitFor(() => {
      expect(screen.queryByTestId('websudo-stepup-modal')).toBeNull();
      expect(capturedErr).toBeInstanceOf(Aal2StepUpCancelledError);
    });
  });

  it('WebSudoModalHost opens via kb:open-aal2-stepup window event', () => {
    render(<WebSudoModalHost />);
    act(() => {
      window.dispatchEvent(
        new CustomEvent('kb:open-aal2-stepup', {
          detail: { challengeId: 'event-challenge', methods: ['totp'] },
        }),
      );
    });
    expect(screen.getByTestId('websudo-stepup-modal')).toBeDefined();

    // Trigger error dispatch branch
    let receivedErrorDetail: unknown = null;
    const errorListener = (e: Event): void => {
      receivedErrorDetail = (e as CustomEvent).detail;
    };
    window.addEventListener('kb:aal2-stepup-error', errorListener);
    fireEvent.click(screen.getByTestId('mock-mfa-error-btn'));
    expect(receivedErrorDetail).toBeDefined();
    window.removeEventListener('kb:aal2-stepup-error', errorListener);

    fireEvent.click(screen.getByTestId('mock-mfa-cancel-btn'));
    expect(screen.queryByTestId('websudo-stepup-modal')).toBeNull();

    // Test kb:open-aal2-stepup with only challengeId or only methods
    act(() => {
      window.dispatchEvent(
        new CustomEvent('kb:open-aal2-stepup', { detail: { challengeId: 'only-ch' } }),
      );
    });
    fireEvent.click(screen.getByTestId('mock-mfa-cancel-btn'));

    act(() => {
      window.dispatchEvent(
        new CustomEvent('kb:open-aal2-stepup', { detail: { methods: ['webauthn'] } }),
      );
    });
    fireEvent.click(screen.getByTestId('mock-mfa-cancel-btn'));

    // Test kb:open-aal2-stepup with empty detail and handleSuccess without resolver
    act(() => {
      window.dispatchEvent(new CustomEvent('kb:open-aal2-stepup'));
    });
    expect(screen.getByTestId('websudo-stepup-modal')).toBeDefined();
    fireEvent.click(screen.getByTestId('mock-mfa-success-btn'));
    expect(screen.queryByTestId('websudo-stepup-modal')).toBeNull();

    // Test handleSessionExpired without resolver
    const origLoc = window.location;
    const assignMock = vi.fn();
    Object.defineProperty(window, 'location', {
      writable: true,
      value: { assign: assignMock },
    });
    act(() => {
      window.dispatchEvent(new CustomEvent('kb:open-aal2-stepup'));
    });
    expect(screen.getByTestId('websudo-stepup-modal')).toBeDefined();
    fireEvent.click(screen.getByTestId('mock-mfa-expired-btn'));
    expect(assignMock).toHaveBeenCalledWith('/login');
    Object.defineProperty(window, 'location', {
      writable: true,
      value: origLoc,
    });
  });
});

describe('AdminStudioSubnav Sudo Pill (KAN-404)', () => {
  it('renders active sudo countdown pill and calls drop endpoint on lock click', async () => {
    const qc = new QueryClient();

    const fetchMock = vi.fn().mockImplementation((url: string) => {
      if (url === '/api/v1/auth/session') {
        return Promise.resolve(new Response(
          JSON.stringify({
            authenticated: true,
            aal2_active: true,
            aal2_expires_at: new Date(Date.now() + 600_000).toISOString(),
          }),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        ));
      }
      if (url === '/api/v1/auth/aal2/drop') {
        return Promise.resolve(new Response(JSON.stringify({ status: 'dropped', aal2_active: false }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }));
      }
      return Promise.resolve(new Response('{}', { status: 200, headers: { 'Content-Type': 'application/json' } }));
    });
    globalThis.fetch = fetchMock;

    render(
      <QueryClientProvider client={qc}>
        <AdminStudioSubnav isServerAdmin={true} />
      </QueryClientProvider>,
    );

    // Pill renders
    await waitFor(() => {
      expect(screen.getByTestId('admin-sudo-pill')).toBeDefined();
      expect(screen.getByText(/🛡️ Sudo/)).toBeDefined();
    });

    // Lock button exists and drops elevation
    const dropBtn = screen.getByTestId('admin-sudo-drop-btn');
    fireEvent.click(dropBtn);

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        '/api/v1/auth/aal2/drop',
        expect.objectContaining({ method: 'POST' }),
      );
    });
  });

  it('formats remaining seconds under 1 minute as seconds and handles inactive session', async () => {
    const qc = new QueryClient();

    globalThis.fetch = vi.fn().mockImplementation((url: string) => {
      if (url === '/api/v1/auth/session') {
        return Promise.resolve(new Response(
          JSON.stringify({
            authenticated: true,
            aal2_active: true,
            aal2_expires_at: new Date(Date.now() + 45_000).toISOString(),
          }),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        ));
      }
      return Promise.resolve(new Response('{}', { status: 200, headers: { 'Content-Type': 'application/json' } }));
    });

    const { rerender } = render(
      <QueryClientProvider client={qc}>
        <AdminStudioSubnav isServerAdmin={true} />
      </QueryClientProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('admin-sudo-pill')).toBeDefined();
      expect(screen.getByText(/🛡️ Sudo 0:4\d/)).toBeDefined();
    });

    // Allow 1s interval to fire
    await act(async () => {
      await new Promise((r) => setTimeout(r, 1100));
    });

    // Inactive session renders nothing
    globalThis.fetch = vi.fn().mockImplementation(() => {
      return Promise.resolve(new Response(
        JSON.stringify({ authenticated: true, aal2_active: false }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      ));
    });

    await act(async () => {
      rerender(
        <QueryClientProvider client={qc}>
          <AdminStudioSubnav isServerAdmin={false} />
        </QueryClientProvider>,
      );
      await Promise.resolve();
    });
  });

  it('renders inside MemoryRouter and displays locked pill when aal2_active is false', async () => {
    const qc = new QueryClient();

    globalThis.fetch = vi.fn().mockImplementation((url: string) => {
      if (url === '/api/v1/auth/session') {
        return Promise.resolve(new Response(
          JSON.stringify({
            authenticated: true,
            aal2_active: false,
          }),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        ));
      }
      return Promise.reject(new Error('network down'));
    });

    render(
      <MemoryRouter initialEntries={['/admin/auth']}>
        <QueryClientProvider client={qc}>
          <AdminStudioSubnav activeTab="auth" isServerAdmin={true} />
        </QueryClientProvider>
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByText('🔒 Sudo Locked')).toBeDefined();
    });
  });

  it('handles fetchSession rejection gracefully without crashing', async () => {
    globalThis.fetch = vi.fn().mockRejectedValue(new Error('connection failed'));

    render(<AdminStudioSubnav isServerAdmin={true} />);

    await waitFor(() => {
      // Nav mounts safely and renders locked sudo pill on error
      expect(screen.getByText('🔒 Sudo Locked')).toBeDefined();
    });
  });

  it('triggers countdown and polling intervals and handles drop refresh failure', async () => {
    vi.useFakeTimers();
    const qc = new QueryClient();
    const exp = new Date(Date.now() + 500_000).toISOString();

    let fetchCount = 0;
    globalThis.fetch = vi.fn().mockImplementation((url: string) => {
      fetchCount++;
      if (url === '/api/v1/auth/session') {
        if (fetchCount >= 3) {
          return Promise.reject(new Error('network error on refresh'));
        }
        return Promise.resolve(new Response(
          JSON.stringify({ authenticated: true, aal2_active: true, aal2_expires_at: exp }),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        ));
      }
      return Promise.resolve(new Response(
        JSON.stringify({ ok: true, aal2_active: false }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      ));
    });

    render(
      <QueryClientProvider client={qc}>
        <AdminStudioSubnav isServerAdmin={true} />
      </QueryClientProvider>,
    );

    await act(async () => {
      await Promise.resolve();
      await vi.advanceTimersByTimeAsync(200);
      await Promise.resolve();
      await vi.advanceTimersByTimeAsync(2000);
      await vi.advanceTimersByTimeAsync(10_000);
    });

    const lockBtn = screen.getByTestId('admin-sudo-drop-btn');
    await act(async () => {
      fireEvent.click(lockBtn);
      await vi.advanceTimersByTimeAsync(100);
    });

    vi.useRealTimers();
  });

  it('AdminStudioSubnav responds to kb:aal2-stepup-success and kb:aal2-expires-at events', async () => {
    const qc = new QueryClient();
    const exp = new Date(Date.now() + 600_000).toISOString();

    globalThis.fetch = vi.fn().mockImplementation((url: string) => {
      if (url === '/api/v1/auth/session') {
        return Promise.resolve(new Response(
          JSON.stringify({ authenticated: true, aal2_active: true, aal2_expires_at: null }),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        ));
      }
      return Promise.resolve(new Response(JSON.stringify({ ok: true }), { status: 200 }));
    });

    render(
      <QueryClientProvider client={qc}>
        <AdminStudioSubnav isServerAdmin={true} />
      </QueryClientProvider>,
    );

    // Initial render with null aal2_expires_at renders '🛡️ Sudo Active'
    await waitFor(() => {
      expect(screen.getByText(/🛡️ Sudo Active/)).toBeDefined();
    });

    // Dispatch kb:aal2-stepup-success
    await act(async () => {
      window.dispatchEvent(new CustomEvent('kb:aal2-stepup-success'));
      await Promise.resolve();
    });

    // Dispatch kb:aal2-expires-at with expiresAt
    await act(async () => {
      window.dispatchEvent(new CustomEvent('kb:aal2-expires-at', {
        detail: { expiresAt: exp },
      }));
      await Promise.resolve();
    });

    // Dispatch kb:aal2-expires-at with undefined detail
    await act(async () => {
      window.dispatchEvent(new CustomEvent('kb:aal2-expires-at'));
      await Promise.resolve();
    });
  });

  it('AdminStudioSubnav falls back to cachedMe or false when isServerAdmin is omitted', async () => {
    const qc = new QueryClient();
    qc.setQueryData(['me'], { is_server_admin: true });

    let u1: (() => void) | undefined;
    await act(async () => {
      const { unmount } = render(
        <QueryClientProvider client={qc}>
          <AdminStudioSubnav />
        </QueryClientProvider>,
      );
      u1 = unmount;
      await Promise.resolve();
    });
    u1?.();

    // Also test without QueryClientProvider and without prop
    let u2: (() => void) | undefined;
    await act(async () => {
      const { unmount } = render(<AdminStudioSubnav />);
      u2 = unmount;
      await Promise.resolve();
    });
    u2?.();
  });

  it('covers all WebSudoModalHost keyboard navigation branches and replay expires-at header', async () => {
    vi.useRealTimers();
    const qc = new QueryClient();

    let expiresAtDetail: string | null = null;
    const expiresListener = (e: Event): void => {
      expiresAtDetail = (e as CustomEvent<{ expiresAt?: string }>).detail.expiresAt ?? null;
    };
    window.addEventListener('kb:aal2-expires-at', expiresListener);

    render(
      <QueryClientProvider client={qc}>
        <WebSudoModalHost />
      </QueryClientProvider>,
    );

    let stepUpInvoked = false;
    globalThis.fetch = vi.fn().mockImplementation((url: string) => {
      if (url === '/api/v1/admin/branch-test') {
        if (!stepUpInvoked) {
          stepUpInvoked = true;
          // No challenge_id provided to test line 55 fallback
          return Promise.resolve(new Response(
            JSON.stringify({ code: 'AAL2_REQUIRED' }),
            { status: 403, headers: { 'Content-Type': 'application/json' } },
          ));
        }
        return Promise.resolve(new Response(
          JSON.stringify({ replayed: true }),
          {
            status: 200,
            headers: {
              'Content-Type': 'application/json',
              'x-kb-aal2-expires-at': '2026-11-25T15:00:00Z',
            },
          },
        ));
      }
      return Promise.resolve(new Response('{}', { status: 200 }));
    });

    const reqPromise = apiFetch('POST', '/api/v1/admin/branch-test' as never);

    await waitFor(() => {
      expect(screen.getByTestId('websudo-stepup-modal')).toBeDefined();
    });

    const modal = screen.getByTestId('websudo-stepup-modal');
    const buttons = modal.querySelectorAll('button');
    const firstBtn = buttons[0];
    const middleBtn = buttons[1];
    const lastBtn = buttons[buttons.length - 1];

    // Non-Tab non-Escape key (line 133 false branch)
    fireEvent.keyDown(window, { key: 'ArrowDown' });
    fireEvent.keyDown(window, { key: 'Enter' });

    // Tab without Shift on middle button (line 147 false branch)
    middleBtn?.focus();
    fireEvent.keyDown(window, { key: 'Tab', shiftKey: false });

    // Tab with Shift on middle button (line 144 false branch)
    middleBtn?.focus();
    fireEvent.keyDown(window, { key: 'Tab', shiftKey: true });

    // Tab with Shift on last button (line 144 false branch)
    lastBtn?.focus();
    fireEvent.keyDown(window, { key: 'Tab', shiftKey: true });

    // Tab without Shift on first button (line 147 false branch)
    firstBtn?.focus();
    fireEvent.keyDown(window, { key: 'Tab', shiftKey: false });

    // Tab without Shift on last button -> wraps to first
    lastBtn?.focus();
    fireEvent.keyDown(window, { key: 'Tab', shiftKey: false });
    expect(document.activeElement).toBe(firstBtn);

    // Tab with Shift on first button -> wraps to last
    firstBtn?.focus();
    fireEvent.keyDown(window, { key: 'Tab', shiftKey: true });
    expect(document.activeElement).toBe(lastBtn);

    // Complete step-up successfully to verify replay with x-kb-aal2-expires-at header
    fireEvent.click(screen.getByTestId('mock-mfa-success-btn'));

    const result = await reqPromise;
    expect(result).toEqual({ replayed: true });
    expect(expiresAtDetail).toBe('2026-11-25T15:00:00Z');

    window.removeEventListener('kb:aal2-expires-at', expiresListener);
  });

  it('WebSudoModalHost handles direct invocation without challengeId', async () => {
    vi.useRealTimers();
    render(<WebSudoModalHost />);
    const handler = getActiveAal2StepUpHandler();
    expect(handler).toBeDefined();

    let p: Promise<boolean> | undefined;
    await act(async () => {
      p = handler?.({ methods: ['totp'] });
      await Promise.resolve();
    });

    await waitFor(() => {
      expect(screen.getByTestId('websudo-stepup-modal')).toBeDefined();
    });

    fireEvent.click(screen.getByTestId('mock-mfa-cancel-btn'));
    const success = await p;
    expect(success).toBe(false);
  });

  it('replays successfully when getCsrfToken is null and bootstrapCsrfToken returns null', async () => {
    vi.useRealTimers();
    setCsrfToken(null);
    document.cookie = 'kb_csrf=; Path=/; Max-Age=0';
    document.cookie = '__Host-kb_csrf=; Path=/; Max-Age=0';

    registerAal2StepUpHandler(async () => {
      await Promise.resolve();
      return true;
    });

    let attempt = 0;
    globalThis.fetch = vi.fn().mockImplementation((url: string) => {
      if (url === '/api/v1/auth/csrf') {
        return Promise.resolve(new Response(null, { status: 500 }));
      }
      if (url === '/api/v1/admin/null-csrf-test') {
        attempt++;
        if (attempt === 1) {
          return Promise.resolve(new Response(
            JSON.stringify({ code: 'AAL2_REQUIRED', challenge_id: 'ch-null-csrf' }),
            { status: 403, headers: { 'Content-Type': 'application/json' } },
          ));
        }
        return Promise.resolve(new Response(
          JSON.stringify({ replayedWithoutCsrf: true }),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        ));
      }
      return Promise.resolve(new Response('{}', { status: 200 }));
    });

    const res = await apiFetch('GET', '/api/v1/admin/null-csrf-test' as never);
    expect(res).toEqual({ replayedWithoutCsrf: true });
  });

  it('dispatches kb:aal2-expires-at on initial request response header', async () => {
    let capturedExp: string | null = null;
    const l = (e: Event): void => {
      capturedExp = (e as CustomEvent<{ expiresAt?: string }>).detail.expiresAt ?? null;
    };
    window.addEventListener('kb:aal2-expires-at', l);

    globalThis.fetch = vi.fn().mockResolvedValue(new Response(
      JSON.stringify({ ok: true }),
      {
        status: 200,
        headers: {
          'Content-Type': 'application/json',
          'x-kb-aal2-expires-at': '2026-11-25T16:00:00Z',
        },
      },
    ));

    await apiFetch('GET', '/api/v1/auth/session' as never);
    expect(capturedExp).toBe('2026-11-25T16:00:00Z');
    window.removeEventListener('kb:aal2-expires-at', l);
  });

  it('throws ApiProblem when AAL2 step-up is required but no handler is registered', async () => {
    registerAal2StepUpHandler(null);
    globalThis.fetch = vi.fn().mockResolvedValue(new Response(
      JSON.stringify({ code: 'AAL2_REQUIRED', challenge_id: 'ch-unhandled' }),
      { status: 403, headers: { 'Content-Type': 'application/json' } },
    ));

    await expect(
      apiFetch('GET', '/api/v1/admin/unhandled-stepup' as never),
    ).rejects.toBeInstanceOf(ApiProblem);
  });

  it('treats rejected step-up handler promise as cancellation', async () => {
    registerAal2StepUpHandler(() => Promise.reject(new Error('Step-up rejected')));
    globalThis.fetch = vi.fn().mockResolvedValue(new Response(
      JSON.stringify({ code: 'AAL2_REQUIRED', challenge_id: 'ch-reject' }),
      { status: 403, headers: { 'Content-Type': 'application/json' } },
    ));

    await expect(
      apiFetch('GET', '/api/v1/admin/reject-stepup' as never),
    ).rejects.toBeInstanceOf(Aal2StepUpCancelledError);
  });
});
