/**
 * Unit Tests for StandaloneStatusPanel and ComposeExportTab (KB-P3-52, S2.2, S2.4, S6.2).
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, act, fireEvent, waitFor, within } from '@testing-library/react';
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { StandaloneStatusPanel } from '../StandaloneStatusPanel';
import { ComposeExportTab } from '../ComposeExportTab';
import { HeaderPills } from '../../../app/HeaderPills';
import { ShellPanelsProvider, registerShellPanel } from '../../../app/shellPanels';
import type { SystemStatus } from '../../../app/useSystemStatus';
import { setCsrfToken } from '../../../api/client';

const OriginalResponse = globalThis.Response;
class JsonFriendlyResponse extends OriginalResponse {
  constructor(body?: BodyInit | null, init?: ResponseInit) {
    const headers = new Headers(init?.headers);
    if (!headers.has('Content-Type')) {
      if (typeof body === 'string' && (body.startsWith('{') || body.startsWith('['))) {
        headers.set('Content-Type', 'application/json');
      }
    }
    super(body, { ...init, headers });
  }
}
globalThis.Response = JsonFriendlyResponse;

describe('StandaloneStatusPanel', () => {
  let queryClient: QueryClient;
  let clipboardWriteTextMock: ReturnType<typeof vi.fn>;
  let createObjectURLMock: ReturnType<typeof vi.fn>;
  let revokeObjectURLMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });

    clipboardWriteTextMock = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, {
      clipboard: {
        writeText: clipboardWriteTextMock,
      },
    });

    createObjectURLMock = vi.fn().mockReturnValue('blob:mock-url-1234');
    revokeObjectURLMock = vi.fn();
    window.URL.createObjectURL = createObjectURLMock as unknown as typeof window.URL.createObjectURL;
    window.URL.revokeObjectURL = revokeObjectURLMock as unknown as typeof window.URL.revokeObjectURL;

    document.cookie = 'kb_csrf=mock-csrf-token-xyz';
    setCsrfToken('mock-csrf-token-xyz');
    const meta = document.createElement('meta');
    meta.name = 'csrf-token';
    meta.content = 'mock-csrf-token-xyz';
    document.head.appendChild(meta);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('Case 4: renders exact ephemeral warning and copies docker run command when persistent_volume is false', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const ephemeralStatus: SystemStatus = {
      deployment_mode: 'standalone_embedded_pg',
      persistent_volume: false,
      air_gap_mode: false,
      local_llm_endpoint_host: null,
      is_server_admin: true,
      data_mount_point: '/var/lib/kanban/data',
      data_mount_fstype: 'overlayfs',
      tier_b_sandbox_available: false,
    };

    render(
      <QueryClientProvider client={queryClient}>
        <StandaloneStatusPanel onClose={() => { /* noop */ }} initialStatus={ephemeralStatus} />
      </QueryClientProvider>,
    );

    // Exact warning text verification
    expect(
      screen.getByText(
        'Ephemeral Storage Detected (overlayfs): Mount -v kanban_data:/var/lib/kanban/data to persist data across container removal',
      ),
    ).toBeDefined();

    // Verify sandbox disclosure
    expect(screen.getByText('Built-in Formula Sandbox (WebAssembly)')).toBeDefined();
    expect(
      screen.getByText(
        'ℹ️ Optional - Not enabled in single-container mode',
      ),
    ).toBeDefined();

    // Copy button
    const copyBtn = screen.getByRole('button', { name: 'Copy docker run command' });
    expect(copyBtn).toBeDefined();

    await act(async () => {
      fireEvent.click(copyBtn);
      await Promise.resolve();
    });

    expect(clipboardWriteTextMock).toHaveBeenCalledWith(
      'docker run -d -p 8080:8080 -v kanban_data:/var/lib/kanban/data thumbs-up-kanban:latest',
    );
    expect(screen.getByText('Copied!')).toBeDefined();

    // Advance timer to clear 'Copied!'
    act(() => {
      vi.advanceTimersByTime(2500);
    });
    expect(screen.queryByText('Copied!')).toBeNull();
    vi.useRealTimers();
  });

  it('Case 4b: renders Persistent Volume Mounted with ext4 when persistent_volume is true', () => {
    const persistentStatus: SystemStatus = {
      deployment_mode: 'standalone_embedded_pg',
      persistent_volume: true,
      air_gap_mode: false,
      local_llm_endpoint_host: null,
      is_server_admin: true,
      data_mount_point: '/var/lib/kanban/data',
      data_mount_fstype: 'ext4',
      tier_b_sandbox_available: true,
    };

    render(
      <QueryClientProvider client={queryClient}>
        <StandaloneStatusPanel onClose={() => { /* noop */ }} initialStatus={persistentStatus} />
      </QueryClientProvider>,
    );

    expect(screen.getByText('Persistent Volume Mounted')).toBeDefined();
    expect(screen.getByText('/var/lib/kanban/data (ext4)')).toBeDefined();
    expect(screen.queryByText(/Ephemeral Storage Detected/)).toBeNull();
  });

  it('Case 5: non-admin member sees calm notice; backup form & compose download are absent from DOM', () => {
    const memberStatus: SystemStatus = {
      deployment_mode: 'standalone_embedded_pg',
      persistent_volume: true,
      air_gap_mode: false,
      local_llm_endpoint_host: null,
      is_server_admin: false,
      data_mount_point: null,
      data_mount_fstype: null,
      tier_b_sandbox_available: false,
    };

    const { unmount } = render(
      <QueryClientProvider client={queryClient}>
        <StandaloneStatusPanel onClose={() => { /* noop */ }} initialStatus={memberStatus} />
      </QueryClientProvider>,
    );

    // Calm notice
    expect(
      screen.getByText('Contact a Server Administrator to export backups or promote this instance.'),
    ).toBeDefined();
    expect(screen.getByText('Persistent volume verified')).toBeDefined();

    // Verify backup form controls and compose download buttons are absent
    expect(screen.queryByLabelText('Backup Passphrase')).toBeNull();
    expect(screen.queryByRole('button', { name: /Download Encrypted Backup/ })).toBeNull();
    expect(screen.queryByRole('button', { name: /Download docker-compose.yml/ })).toBeNull();
    expect(screen.queryByRole('button', { name: /Copy .env.example/ })).toBeNull();

    // Tab key with only 1 focusable (Close button) exercises line 86 (focusables.length <= 1)
    fireEvent.keyDown(document, { key: 'Tab' });
    unmount();
  });

  it('Case 5b: admin backup validation, CSRF token header, and blob URL revocation', async () => {
    let capturedUrl = '';
    let capturedBody = '';
    let capturedHeaders: Record<string, string> = {};

    const mockFetch = vi.fn().mockImplementation((url: string, init?: RequestInit) => {
      if (url.endsWith('/api/v1/admin/standalone/backup')) {
        capturedUrl = url;
        if (init?.body && typeof init.body === 'string') {
          capturedBody = init.body;
        }
        if (init?.headers) {
          capturedHeaders = init.headers as Record<string, string>;
        }
        return Promise.resolve(
          new Response('encrypted-kbkp-octets', {
            status: 200,
            headers: {
              'Content-Type': 'application/octet-stream',
              'Content-Disposition': 'attachment; filename="kanban-backup-20261113T120000Z.kbbak"',
            },
          }),
        );
      }
      return Promise.resolve(new Response('{}', { status: 200 }));
    });
    global.fetch = mockFetch;

    const adminStatus: SystemStatus = {
      deployment_mode: 'standalone_embedded_pg',
      persistent_volume: true,
      air_gap_mode: false,
      local_llm_endpoint_host: null,
      is_server_admin: true,
      data_mount_point: '/var/lib/kanban/data',
      data_mount_fstype: 'ext4',
      tier_b_sandbox_available: false,
    };

    render(
      <QueryClientProvider client={queryClient}>
        <StandaloneStatusPanel onClose={() => { /* noop */ }} initialStatus={adminStatus} />
      </QueryClientProvider>,
    );

    const input = screen.getByLabelText('Backup Passphrase', { selector: 'input' });
    const submitBtn = screen.getByRole('button', {
      name: 'Download Encrypted Backup (.kbbak)',
    });

    // 1. Initially empty passphrase: button disabled
    expect(submitBtn.hasAttribute('disabled')).toBe(true);

    // 2. 15-char passphrase: fails min length, button disabled
    fireEvent.change(input, { target: { value: '123456789012345' } });
    expect(submitBtn.hasAttribute('disabled')).toBe(true);

    // 3. 16-char passphrase: button enabled
    fireEvent.change(input, { target: { value: 'a-secure-passphrase-16' } });
    expect(submitBtn.hasAttribute('disabled')).toBe(false);

    // 4. Submit form
    await act(async () => {
      fireEvent.click(submitBtn);
      await Promise.resolve();
    });

    await waitFor(() => {
      expect(capturedUrl).toContain('/api/v1/admin/standalone/backup');
    });

    expect(capturedHeaders['X-CSRF-Token']).toBe('mock-csrf-token-xyz');
    expect(JSON.parse(capturedBody || '{}')).toEqual({
      passphrase: 'a-secure-passphrase-16',
    });

    // Verify blob URL was created and immediately revoked
    await waitFor(() => {
      expect(createObjectURLMock).toHaveBeenCalled();
    });
    expect(revokeObjectURLMock).toHaveBeenCalledWith('blob:mock-url-1234');
  });

  it('retries backup download with refreshed CSRF token upon receiving 403', async () => {
    let callCount = 0;
    const mockFetch = vi.fn().mockImplementation((url: string) => {
      if (url.includes('/api/v1/auth/session')) {
        return Promise.resolve(new Response(JSON.stringify({ csrf_token: 'fresh-csrf-token-123' }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }));
      }
      if (url.endsWith('/api/v1/admin/standalone/backup')) {
        callCount++;
        if (callCount === 1) {
          return Promise.resolve(new Response(JSON.stringify({ detail: 'CSRF invalid' }), {
            status: 403,
            headers: { 'Content-Type': 'application/json' },
          }));
        }
        return Promise.resolve(
          new Response('encrypted-octets', {
            status: 200,
            headers: {
              'Content-Type': 'application/octet-stream',
              'Content-Disposition': 'attachment; filename="kanban-backup-retry.kbbak"',
            },
          }),
        );
      }
      return Promise.resolve(new Response('{}', { status: 200 }));
    });
    global.fetch = mockFetch;

    const adminStatus: SystemStatus = {
      deployment_mode: 'standalone_embedded_pg',
      persistent_volume: true,
      air_gap_mode: false,
      local_llm_endpoint_host: null,
      is_server_admin: true,
    };

    render(
      <QueryClientProvider client={queryClient}>
        <StandaloneStatusPanel
          onClose={() => { /* noop */ }}
          initialStatus={adminStatus}
          initialTab="backup"
        />
      </QueryClientProvider>,
    );

    const input = screen.getByLabelText('Backup Passphrase', { selector: 'input' });
    const submitBtn = screen.getByRole('button', {
      name: 'Download Encrypted Backup (.kbbak)',
    });
    fireEvent.change(input, { target: { value: 'a-secure-passphrase-16' } });

    await act(async () => {
      fireEvent.click(submitBtn);
      await Promise.resolve();
    });

    await waitFor(() => {
      expect(callCount).toBe(2);
      expect(createObjectURLMock).toHaveBeenCalled();
    });
  });

  it('Case 5c: handles backup validation error and API failure branches', async () => {
    const adminStatus: SystemStatus = {
      deployment_mode: 'standalone_embedded_pg',
      persistent_volume: true,
      air_gap_mode: false,
      local_llm_endpoint_host: null,
      is_server_admin: true,
      data_mount_point: '/var/lib/kanban/data',
      data_mount_fstype: 'ext4',
      tier_b_sandbox_available: false,
    };

    const mockFetch = vi.fn().mockImplementation((url: string) => {
      if (url.includes('/api/v1/admin/standalone/backup')) {
        return Promise.resolve(
          new Response(JSON.stringify({ detail: 'Server backup failure' }), {
            status: 500,
            headers: { 'Content-Type': 'application/json' },
          }),
        );
      }
      return Promise.resolve(new Response('{}', { status: 200 }));
    });
    global.fetch = mockFetch;

    render(
      <QueryClientProvider client={queryClient}>
        <StandaloneStatusPanel onClose={() => { /* noop */ }} initialStatus={adminStatus} />
      </QueryClientProvider>,
    );

    const form = screen.getByRole('button', {
      name: 'Download Encrypted Backup (.kbbak)',
    }).closest('form');
    expect(form).not.toBeNull();
    if (!form) return;
    const input = screen.getByLabelText('Backup Passphrase', { selector: 'input' });

    // 1. Submit directly with short passphrase (<16)
    fireEvent.change(input, { target: { value: 'short' } });
    fireEvent.submit(form);
    expect(screen.getByText('Passphrase must be at least 16 characters')).toBeDefined();

    // 2. Typing >= 16 chars clears passphrase error
    fireEvent.change(input, { target: { value: '1234567890123456' } });
    expect(screen.queryByText('Passphrase must be at least 16 characters')).toBeNull();

    // 3. Submit and receive 500 error from API
    act(() => {
      fireEvent.submit(form);
    });

    await waitFor(() => {
      expect(screen.getByText('Server backup failure')).toBeDefined();
    });
  });

  it('Case 5d: handles backup API error with nested detail object and network exception', async () => {
    const adminStatus: SystemStatus = {
      deployment_mode: 'standalone_embedded_pg',
      persistent_volume: true,
      air_gap_mode: false,
      local_llm_endpoint_host: null,
      is_server_admin: true,
    };

    let fetchCount = 0;
    const mockFetch = vi.fn().mockImplementation((url: string) => {
      if (url.includes('/api/v1/admin/standalone/backup')) {
        fetchCount++;
        if (fetchCount === 1) {
          return Promise.resolve(
            new Response(JSON.stringify({ detail: { detail: 'Nested error msg' } }), {
              status: 500,
              headers: { 'Content-Type': 'application/json' },
            }),
          );
        }
        return Promise.reject(new Error('Network offline'));
      }
      return Promise.resolve(new Response('{}', { status: 200 }));
    });
    global.fetch = mockFetch;

    render(
      <QueryClientProvider client={queryClient}>
        <StandaloneStatusPanel onClose={() => { /* noop */ }} initialStatus={adminStatus} />
      </QueryClientProvider>,
    );

    const form = screen.getByRole('button', {
      name: 'Download Encrypted Backup (.kbbak)',
    }).closest('form');
    expect(form).not.toBeNull();
    if (!form) return;
    const input = screen.getByLabelText('Backup Passphrase', { selector: 'input' });
    fireEvent.change(input, { target: { value: '1234567890123456' } });

    // Nested detail error
    act(() => {
      fireEvent.submit(form);
    });
    await waitFor(() => {
      expect(screen.getByText('Nested error msg')).toBeDefined();
    });

    // Network error
    act(() => {
      fireEvent.submit(form);
    });
    await waitFor(() => {
      expect(screen.getByText('Network offline')).toBeDefined();
    });
  });

  it('Case 6: Keyboard A11y - Clicking ⚠️ opens panel, Tab traps focus, Escape closes and restores focus', () => {
    const standaloneStatus: SystemStatus = {
      deployment_mode: 'standalone_embedded_pg',
      persistent_volume: false,
      air_gap_mode: false,
      local_llm_endpoint_host: null,
      is_server_admin: true,
      data_mount_point: '/var/lib/kanban/data',
      data_mount_fstype: 'overlayfs',
      tier_b_sandbox_available: false,
    };

    // Register real panel
    const unregister = registerShellPanel('standalone', StandaloneStatusPanel);

    render(
      <QueryClientProvider client={queryClient}>
        <ShellPanelsProvider>
          <HeaderPills systemStatus={standaloneStatus} />
        </ShellPanelsProvider>
      </QueryClientProvider>,
    );

    const warnPill = screen.getByRole('button', { name: 'Standalone mode warning' });
    act(() => {
      warnPill.focus();
    });

    // Click ⚠️ pill to open panel
    act(() => {
      fireEvent.click(warnPill);
    });

    // Panel dialog must now be visible in DOM
    const dialog = screen.getByRole('dialog', { name: 'Standalone deployment status' });
    expect(dialog).toBeDefined();

    // Close button should be present
    const closeBtn = screen.getByRole('button', { name: 'Close' });
    expect(closeBtn).toBeDefined();

    // Test Tab trap: Shift+Tab on first element wraps to last element
    const focusables = dialog.querySelectorAll<HTMLElement>(
      'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
    );
    expect(focusables.length).toBeGreaterThan(1);
    const firstFocusable = focusables[0];
    const lastFocusable = focusables[focusables.length - 1];

    act(() => {
      firstFocusable?.focus();
      fireEvent.keyDown(document, { key: 'Tab', shiftKey: true });
    });
    expect(document.activeElement).toBe(lastFocusable);

    // Tab on last element wraps to first element
    act(() => {
      lastFocusable?.focus();
      fireEvent.keyDown(document, { key: 'Tab', shiftKey: false });
    });
    expect(document.activeElement).toBe(firstFocusable);

    // Tab on middle element does not wrap
    const middleFocusable = focusables[1];
    act(() => {
      middleFocusable?.focus();
      fireEvent.keyDown(document, { key: 'Tab', shiftKey: false });
      fireEvent.keyDown(document, { key: 'Tab', shiftKey: true });
    });

    // Escape key closes dialog
    act(() => {
      fireEvent.keyDown(document, { key: 'Escape' });
    });

    expect(screen.queryByRole('dialog', { name: 'Standalone deployment status' })).toBeNull();

    unregister();
  });

  it('covers remaining branches: no CSRF, missing filename, non-Error throws, null fstype, active sandbox', async () => {
    // Clear CSRF cookie and meta tag
    document.cookie = 'kb_csrf=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;';
    const metas = document.querySelectorAll('meta[name="csrf-token"]');
    metas.forEach((m) => {
      m.remove();
    });

    const activeSandboxStatus: SystemStatus = {
      deployment_mode: 'standalone_embedded_pg',
      persistent_volume: true,
      air_gap_mode: false,
      local_llm_endpoint_host: null,
      is_server_admin: true,
      data_mount_point: '/var/lib/kanban/data',
      data_mount_fstype: null, // Tests fallback to 'ext4'
      tier_b_sandbox_available: true, // Tests 'Tier B nsjail CLI Sandbox: Active'
    };

    const mockFetch = vi.fn().mockImplementation((url: string) => {
      if (url.includes('/api/v1/admin/standalone/backup')) {
        return Promise.resolve(
          new Response('dump', {
            status: 200,
            headers: {
              'Content-Type': 'application/octet-stream',
              // No content-disposition header to test default filename fallback
            },
          }),
        );
      }
      return Promise.resolve(new Response('{}', { status: 200 }));
    });
    global.fetch = mockFetch;

    render(
      <QueryClientProvider client={queryClient}>
        <StandaloneStatusPanel onClose={() => { /* noop */ }} initialStatus={activeSandboxStatus} />
      </QueryClientProvider>,
    );

    // Verify active sandbox text
    expect(
      screen.getByText(
        'Runs full Python/CLI scripts and local CLI transition agents with isolated Linux namespaces and allowlisted HTTP egress.',
      ),
    ).toBeDefined();
    // Verify default 'ext4' fallback
    expect(screen.getByText('/var/lib/kanban/data (ext4)')).toBeDefined();

    const input = screen.getByLabelText('Backup Passphrase', { selector: 'input' });
    const submitBtn = screen.getByRole('button', {
      name: 'Download Encrypted Backup (.kbbak)',
    });
    fireEvent.change(input, { target: { value: 'passphrase-without-csrf-16' } });

    await act(async () => {
      fireEvent.click(submitBtn);
      await Promise.resolve();
    });

    await waitFor(() => {
      expect(createObjectURLMock).toHaveBeenCalled();
    });
  });

  it('covers non-Error throw branches in backup and copy', async () => {
    const adminStatus: SystemStatus = {
      deployment_mode: 'standalone_embedded_pg',
      persistent_volume: false,
      air_gap_mode: false,
      local_llm_endpoint_host: null,
      is_server_admin: true,
    };

    global.fetch = vi.fn().mockRejectedValue('Raw string error');
    clipboardWriteTextMock.mockRejectedValueOnce('Clipboard string failure');

    render(
      <QueryClientProvider client={queryClient}>
        <StandaloneStatusPanel onClose={() => { /* noop */ }} initialStatus={adminStatus} />
      </QueryClientProvider>,
    );

    // 1. Copy docker run with string throw
    const copyBtn = screen.getByRole('button', { name: 'Copy docker run command' });
    await act(async () => {
      fireEvent.click(copyBtn);
      await Promise.resolve();
    });

    // 2. Submit backup with string throw
    const input = screen.getByLabelText('Backup Passphrase', { selector: 'input' });
    const submitBtn = screen.getByRole('button', {
      name: 'Download Encrypted Backup (.kbbak)',
    });
    fireEvent.change(input, { target: { value: 'passphrase-string-err-16' } });
    await act(async () => {
      fireEvent.click(submitBtn);
      await Promise.resolve();
    });

    await waitFor(() => {
      expect(screen.getByText('Backup export failed')).toBeDefined();
    });
  });

  it('covers middle tab, empty detail fallback, and error object branches', async () => {
    // 1. Middle tab navigation does not wrap
    const standaloneStatus: SystemStatus = {
      deployment_mode: 'standalone_embedded_pg',
      persistent_volume: true,
      air_gap_mode: false,
      local_llm_endpoint_host: null,
      is_server_admin: true,
    };

    render(
      <QueryClientProvider client={queryClient}>
        <StandaloneStatusPanel onClose={() => { /* noop */ }} initialStatus={standaloneStatus} />
      </QueryClientProvider>,
    );

    const dialog = screen.getByRole('dialog');
    const input = screen.getByLabelText('Backup Passphrase', { selector: 'input' });
    fireEvent.change(input, { target: { value: 'passphrase-fallback-502' } });

    const focusables = dialog.querySelectorAll<HTMLElement>(
      'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
    );
    expect(focusables.length).toBeGreaterThan(2);
    const middleFocusable = focusables[1];
    middleFocusable?.focus();
    // Shift+Tab on middle element does not wrap to last
    fireEvent.keyDown(document, { key: 'Tab', shiftKey: true });
    // Normal Tab on middle element does not wrap to first
    fireEvent.keyDown(document, { key: 'Tab', shiftKey: false });

    // 2. Backup API returns empty object without detail field -> status code fallback
    global.fetch = vi.fn().mockImplementation((url: string) => {
      if (url.includes('/api/v1/admin/standalone/backup')) {
        return Promise.resolve(
          new Response(JSON.stringify({}), {
            status: 502,
            headers: { 'Content-Type': 'application/json' },
          }),
        );
      }
      return Promise.resolve(new Response('{}', { status: 200 }));
    });

    const form = screen.getByRole('button', {
      name: 'Download Encrypted Backup (.kbbak)',
    }).closest('form');
    expect(form).not.toBeNull();
    if (!form) return;
    fireEvent.change(input, { target: { value: 'passphrase-fallback-502' } });

    act(() => {
      fireEvent.submit(form);
    });

    await waitFor(() => {
      expect(screen.getByText('Backup failed with status 502')).toBeDefined();
    });
  });

  it('restores focus via fallback querySelector when trigger element is not directly focusable', () => {
    const focusSpy = vi.fn();
    const pill = document.createElement('button');
    pill.setAttribute('aria-label', 'Standalone mode warning');
    pill.focus = focusSpy;
    document.body.appendChild(pill);

    const prevActive = document.activeElement;
    Object.defineProperty(document, 'activeElement', {
      value: null,
      configurable: true,
    });

    const { unmount } = render(
      <QueryClientProvider client={queryClient}>
        <StandaloneStatusPanel onClose={() => { /* noop */ }} />
      </QueryClientProvider>,
    );

    unmount();
    expect(focusSpy).toHaveBeenCalled();
    document.body.removeChild(pill);
    Object.defineProperty(document, 'activeElement', {
      value: prevActive,
      configurable: true,
    });
  });

  it('switches between 3 tabs and renders respective panels', async () => {
    const adminStatus: SystemStatus = {
      deployment_mode: 'standalone_embedded_pg',
      persistent_volume: true,
      air_gap_mode: false,
      local_llm_endpoint_host: null,
      is_server_admin: true,
    };

    render(
      <QueryClientProvider client={queryClient}>
        <StandaloneStatusPanel onClose={() => { /* noop */ }} initialStatus={adminStatus} />
      </QueryClientProvider>,
    );

    // Initial tab: Health
    const healthTab = screen.getByRole('tab', { name: 'Storage & Capabilities Health' });
    const backupTab = screen.getByRole('tab', { name: 'Backup, Auto-Backup & Restore' });
    const composeTab = screen.getByRole('tab', { name: 'Docker Compose Export' });

    expect(healthTab.getAttribute('aria-selected')).toBe('true');
    expect(backupTab.getAttribute('aria-selected')).toBe('false');

    // Switch to Backup tab
    await act(async () => {
      fireEvent.click(backupTab);
      await Promise.resolve();
    });
    expect(backupTab.getAttribute('aria-selected')).toBe('true');
    expect(screen.getByText('Manual Encrypted Backup (.kbbak)')).toBeDefined();

    // Switch to Compose tab
    await act(async () => {
      fireEvent.click(composeTab);
      await Promise.resolve();
    });
    expect(composeTab.getAttribute('aria-selected')).toBe('true');
    expect(screen.getByText('Production Compose Export & Promotion')).toBeDefined();
  });

  it('tests 2-stage restore flow requiring RESTORE confirmation', async () => {
    let restoreSubmitted = false;
    const mockFetch = vi.fn().mockImplementation((url: string) => {
      if (url.includes('/backup/verify')) {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              valid: true,
              manifest: { format_version: 1, pg_server_version: '16', alembic_revision: 'head' },
            }),
            { status: 200, headers: { 'Content-Type': 'application/json' } },
          ),
        );
      }
      if (url.includes('/restore')) {
        restoreSubmitted = true;
        return Promise.resolve(
          new Response(JSON.stringify({ status: 'success' }), {
            status: 200,
            headers: { 'Content-Type': 'application/json' },
          }),
        );
      }
      return Promise.resolve(new Response('[]', { status: 200 }));
    });
    global.fetch = mockFetch;

    const adminStatus: SystemStatus = {
      deployment_mode: 'standalone_embedded_pg',
      persistent_volume: true,
      air_gap_mode: false,
      local_llm_endpoint_host: null,
      is_server_admin: true,
    };

    render(
      <QueryClientProvider client={queryClient}>
        <StandaloneStatusPanel
          onClose={() => { /* noop */ }}
          initialStatus={adminStatus}
          initialTab="backup"
        />
      </QueryClientProvider>,
    );

    // Verify step with a file
    const fileInput = screen.getByLabelText(/Upload Backup Archive/);
    const mockFile = new File(['mock-backup-octets'], 'test.kbbak', { type: 'application/octet-stream' });
    fireEvent.change(fileInput, { target: { files: [mockFile] } });

    const verifyBtn = screen.getByRole('button', { name: /Step 1: Verify Backup Archive/ });
    await act(async () => {
      fireEvent.click(verifyBtn);
      await Promise.resolve();
    });

    await waitFor(() => {
      expect(screen.getByText('✓ Backup Archive Verified')).toBeDefined();
    });

    // Step 2: Destructive confirmation
    const confirmInput = screen.getByPlaceholderText('RESTORE');
    const restoreBtn = screen.getByRole('button', { name: /Step 2: Restore Database/ });

    // Disabled initially
    expect(restoreBtn.hasAttribute('disabled')).toBe(true);

    // Type incorrect text
    fireEvent.change(confirmInput, { target: { value: 'yes' } });
    expect(restoreBtn.hasAttribute('disabled')).toBe(true);

    // Type RESTORE exactly
    fireEvent.change(confirmInput, { target: { value: 'RESTORE' } });
    expect(restoreBtn.hasAttribute('disabled')).toBe(false);

    // Submit restore
    await act(async () => {
      fireEvent.click(restoreBtn);
      await Promise.resolve();
    });

    await waitFor(() => {
      expect(restoreSubmitted).toBe(true);
      expect(screen.getByText(/Database restored successfully/)).toBeDefined();
    });
  });

  it('KANBA-208: supports WAI-ARIA tab navigation with ArrowRight, ArrowLeft, Home, and End keys', async () => {
    const adminStatus: SystemStatus = {
      deployment_mode: 'standalone_embedded_pg',
      persistent_volume: true,
      air_gap_mode: false,
      local_llm_endpoint_host: null,
      is_server_admin: true,
    };

    render(
      <QueryClientProvider client={queryClient}>
        <StandaloneStatusPanel onClose={() => { /* noop */ }} initialStatus={adminStatus} />
      </QueryClientProvider>,
    );

    const tablist = screen.getByRole('tablist', { name: 'System status sections' });
    const healthTab = screen.getByRole('tab', { name: 'Storage & Capabilities Health' });
    const backupTab = screen.getByRole('tab', { name: 'Backup, Auto-Backup & Restore' });
    const composeTab = screen.getByRole('tab', { name: 'Docker Compose Export' });

    // Initial roving tabIndex
    expect(healthTab.getAttribute('tabindex')).toBe('0');
    expect(backupTab.getAttribute('tabindex')).toBe('-1');
    expect(composeTab.getAttribute('tabindex')).toBe('-1');

    // ArrowRight -> backup
    await act(async () => {
      fireEvent.keyDown(tablist, { key: 'ArrowRight' });
      await Promise.resolve();
    });
    expect(backupTab.getAttribute('tabindex')).toBe('0');
    expect(healthTab.getAttribute('tabindex')).toBe('-1');

    // ArrowRight -> compose
    await act(async () => {
      fireEvent.keyDown(tablist, { key: 'ArrowRight' });
      await Promise.resolve();
    });
    expect(composeTab.getAttribute('tabindex')).toBe('0');

    // ArrowRight -> wrap to health
    await act(async () => {
      fireEvent.keyDown(tablist, { key: 'ArrowRight' });
      await Promise.resolve();
    });
    expect(healthTab.getAttribute('tabindex')).toBe('0');

    // ArrowLeft -> wrap back to compose
    await act(async () => {
      fireEvent.keyDown(tablist, { key: 'ArrowLeft' });
      await Promise.resolve();
    });
    expect(composeTab.getAttribute('tabindex')).toBe('0');

    // Home -> health
    await act(async () => {
      fireEvent.keyDown(tablist, { key: 'Home' });
      await Promise.resolve();
    });
    expect(healthTab.getAttribute('tabindex')).toBe('0');

    // End -> compose
    await act(async () => {
      fireEvent.keyDown(tablist, { key: 'End' });
      await Promise.resolve();
    });
    expect(composeTab.getAttribute('tabindex')).toBe('0');

    // Non-navigation keys (e.g. Tab, Escape) do not change roving index
    act(() => {
      fireEvent.keyDown(tablist, { key: 'Tab' });
    });
    expect(composeTab.getAttribute('tabindex')).toBe('0');
    act(() => {
      fireEvent.keyDown(tablist, { key: 'x' });
    });
    expect(composeTab.getAttribute('tabindex')).toBe('0');
  });

  it('KANBA-208: displays dismissible error alert with correlation ID on backup schedule 500 error', async () => {
    const adminStatus: SystemStatus = {
      deployment_mode: 'standalone_embedded_pg',
      persistent_volume: true,
      air_gap_mode: false,
      local_llm_endpoint_host: null,
      is_server_admin: true,
    };

    const mockFetch = vi.fn().mockImplementation((url: string, options?: { method?: string }) => {
      if (url.includes('/backup-schedule') && options?.method === 'PUT') {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              detail: 'Database write failed for backup schedule',
              request_id: 'req-sched-err-789',
            }),
            {
              status: 500,
              headers: { 'Content-Type': 'application/json' },
            },
          ),
        );
      }
      if (url.includes('/backup-schedule')) {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              enabled: false,
              interval_hours: 24,
              retention_count: 7,
              last_run_at: null,
              next_run_at: null,
            }),
            { status: 200, headers: { 'Content-Type': 'application/json' } },
          ),
        );
      }
      if (url.includes('/backups')) {
        return Promise.resolve(new Response('[]', { status: 200, headers: { 'Content-Type': 'application/json' } }));
      }
      return Promise.resolve(new Response('{}', { status: 200 }));
    });
    global.fetch = mockFetch;

    render(
      <QueryClientProvider client={queryClient}>
        <StandaloneStatusPanel
          onClose={() => { /* noop */ }}
          initialStatus={adminStatus}
          initialTab="backup"
        />
      </QueryClientProvider>,
    );

    const saveBtn = screen.getByRole('button', { name: 'Save Schedule' });
    act(() => {
      fireEvent.click(saveBtn);
    });

    await waitFor(() => {
      expect(screen.getByTestId('standalone-api-error-alert')).toBeDefined();
    });

    expect(screen.getByText('Database write failed for backup schedule')).toBeDefined();
    const corrIdEl = screen.getByTestId('correlation-id');
    expect(corrIdEl.textContent).toBe('req-sched-err-789');

    // Dismiss the error
    const dismissBtn = screen.getByRole('button', { name: 'Dismiss error' });
    act(() => {
      fireEvent.click(dismissBtn);
    });

    expect(screen.queryByTestId('standalone-api-error-alert')).toBeNull();
  });

  it('KANBA-208: updates backup schedule inputs and saves schedule successfully', async () => {
    const adminStatus: SystemStatus = {
      deployment_mode: 'standalone_embedded_pg',
      persistent_volume: true,
      air_gap_mode: false,
      local_llm_endpoint_host: null,
      is_server_admin: true,
    };

    let savedPayload: string | null = null;
    global.fetch = vi.fn().mockImplementation((url: string, options?: { method?: string; body?: string }) => {
      if (url.includes('/backup-schedule') && options?.method === 'PUT') {
        savedPayload = options.body ?? null;
        return Promise.resolve(
          new Response(
            JSON.stringify({
              enabled: true,
              interval_hours: 48,
              retention_count: 14,
              last_run_at: null,
              next_run_at: '2026-11-20T00:00:00Z',
            }),
            { status: 200, headers: { 'Content-Type': 'application/json' } },
          ),
        );
      }
      if (url.includes('/backup-schedule')) {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              enabled: false,
              interval_hours: 24,
              retention_count: 7,
              last_run_at: null,
              next_run_at: null,
            }),
            { status: 200, headers: { 'Content-Type': 'application/json' } },
          ),
        );
      }
      if (url.includes('/backups')) {
        return Promise.resolve(new Response('[]', { status: 200 }));
      }
      return Promise.resolve(new Response('{}', { status: 200 }));
    });

    render(
      <QueryClientProvider client={queryClient}>
        <StandaloneStatusPanel
          onClose={() => { /* noop */ }}
          initialStatus={adminStatus}
          initialTab="backup"
        />
      </QueryClientProvider>,
    );

    // Modify inputs
    const enableCheckbox = screen.getByLabelText<HTMLInputElement>('Enable Automated Backups');
    fireEvent.click(enableCheckbox);
    expect(enableCheckbox.checked).toBe(true);

    const intervalInput = screen.getByLabelText('Backup Interval (hours)', { selector: 'input' });
    fireEvent.change(intervalInput, { target: { value: '48' } });

    const retentionInput = screen.getByLabelText('Keep Latest Snapshots', { selector: 'input' });
    fireEvent.change(retentionInput, { target: { value: '14' } });

    // Save
    const saveBtn = screen.getByRole('button', { name: 'Save Schedule' });
    act(() => {
      fireEvent.click(saveBtn);
    });

    await waitFor(() => {
      expect(screen.getByText('Schedule Saved!')).toBeDefined();
    });
    expect(savedPayload).not.toBeNull();
    expect(JSON.parse(String(savedPayload))).toEqual({
      enabled: true,
      interval_hours: 48,
      retention_count: 14,
    });

    // Click health tab
    const healthTab = screen.getByRole('tab', { name: 'Storage & Capabilities Health' });
    act(() => {
      fireEvent.click(healthTab);
    });
    expect(healthTab.getAttribute('aria-selected')).toBe('true');
  });

  it('KANBA-208: displays dismissible error alert with correlation ID on run-now 500 error', async () => {
    const adminStatus: SystemStatus = {
      deployment_mode: 'standalone_embedded_pg',
      persistent_volume: true,
      air_gap_mode: false,
      local_llm_endpoint_host: null,
      is_server_admin: true,
    };

    const mockFetch = vi.fn().mockImplementation((url: string, options?: { method?: string }) => {
      if (url.includes('/backups/run-now') && options?.method === 'POST') {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              detail: 'pg_dump failed with exit code 1',
              request_id: 'req-run-now-err-101',
            }),
            {
              status: 500,
              headers: { 'Content-Type': 'application/json' },
            },
          ),
        );
      }
      if (url.includes('/backup-schedule')) {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              enabled: false,
              interval_hours: 24,
              retention_count: 7,
              last_run_at: null,
              next_run_at: null,
            }),
            { status: 200, headers: { 'Content-Type': 'application/json' } },
          ),
        );
      }
      if (url.includes('/backups')) {
        return Promise.resolve(new Response('[]', { status: 200, headers: { 'Content-Type': 'application/json' } }));
      }
      return Promise.resolve(new Response('{}', { status: 200 }));
    });
    global.fetch = mockFetch;

    render(
      <QueryClientProvider client={queryClient}>
        <StandaloneStatusPanel
          onClose={() => { /* noop */ }}
          initialStatus={adminStatus}
          initialTab="backup"
        />
      </QueryClientProvider>,
    );

    const runNowBtn = screen.getByRole('button', { name: 'Run Backup Now' });
    act(() => {
      fireEvent.click(runNowBtn);
    });

    await waitFor(() => {
      expect(screen.getByTestId('standalone-api-error-alert')).toBeDefined();
    });

    expect(screen.getByText('pg_dump failed with exit code 1')).toBeDefined();
    const corrIdEl = screen.getByTestId('correlation-id');
    expect(corrIdEl.textContent).toBe('req-run-now-err-101');
  });

  it('KANBA-208: wraps modal content inside .standalone-panel__body leaving tabs accessible', () => {
    const adminStatus: SystemStatus = {
      deployment_mode: 'standalone_embedded_pg',
      persistent_volume: true,
      air_gap_mode: false,
      local_llm_endpoint_host: null,
      is_server_admin: true,
    };

    const { container } = render(
      <QueryClientProvider client={queryClient}>
        <StandaloneStatusPanel onClose={() => { /* noop */ }} initialStatus={adminStatus} />
      </QueryClientProvider>,
    );

    const panel = container.querySelector('.standalone-panel');
    expect(panel).not.toBeNull();
    const body = container.querySelector('.standalone-panel__body');
    expect(body).not.toBeNull();
    const tabs = container.querySelector('.standalone-panel__tabs');
    expect(tabs).not.toBeNull();

    // Verify tabs are outside .standalone-panel__body
    expect(body?.contains(tabs)).toBe(false);
  });

  it('KANBA-208: renders existing snapshots table and handles snapshot selection', async () => {
    const adminStatus: SystemStatus = {
      deployment_mode: 'standalone_embedded_pg',
      persistent_volume: true,
      air_gap_mode: false,
      local_llm_endpoint_host: null,
      is_server_admin: true,
    };

    const mockSnapshots = [
      {
        filename: 'snapshot-2026-11-18.kbbak',
        size_bytes: 204800,
        created_at: '2026-11-18T10:00:00Z',
      },
    ];

    global.fetch = vi.fn().mockImplementation((url: string) => {
      if (url.includes('/backup-schedule')) {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              enabled: true,
              interval_hours: 12,
              retention_count: 5,
              last_run_at: '2026-11-18T08:00:00Z',
              next_run_at: '2026-11-18T20:00:00Z',
            }),
            { status: 200, headers: { 'Content-Type': 'application/json' } },
          ),
        );
      }
      if (url.includes('/backups')) {
        return Promise.resolve(
          new Response(JSON.stringify(mockSnapshots), {
            status: 200,
            headers: { 'Content-Type': 'application/json' },
          }),
        );
      }
      return Promise.resolve(new Response('{}', { status: 200 }));
    });

    render(
      <QueryClientProvider client={queryClient}>
        <StandaloneStatusPanel
          onClose={() => { /* noop */ }}
          initialStatus={adminStatus}
          initialTab="backup"
        />
      </QueryClientProvider>,
    );

    await waitFor(() => {
      expect(screen.getByText('snapshot-2026-11-18.kbbak')).toBeDefined();
    });

    expect(screen.getByText('200.0 KB')).toBeDefined();

    // Select snapshot from dropdown
    const select = screen.getByLabelText<HTMLSelectElement>('Select Server Snapshot');
    fireEvent.change(select, { target: { value: 'snapshot-2026-11-18.kbbak' } });
    expect(select.value).toBe('snapshot-2026-11-18.kbbak');
  });

  it('KANBA-208: handles loadScheduleAndSnapshots error branches and network failures', async () => {
    const adminStatus: SystemStatus = {
      deployment_mode: 'standalone_embedded_pg',
      persistent_volume: true,
      air_gap_mode: false,
      local_llm_endpoint_host: null,
      is_server_admin: true,
    };

    // 1. Schedule load fails
    global.fetch = vi.fn().mockImplementation((url: string) => {
      if (url.includes('/backup-schedule')) {
        return Promise.resolve(
          new Response(JSON.stringify({ detail: 'Failed reading schedule' }), {
            status: 500,
            headers: { 'Content-Type': 'application/json' },
          }),
        );
      }
      return Promise.resolve(new Response('[]', { status: 200 }));
    });

    const { unmount } = render(
      <QueryClientProvider client={queryClient}>
        <StandaloneStatusPanel
          onClose={() => { /* noop */ }}
          initialStatus={adminStatus}
          initialTab="backup"
        />
      </QueryClientProvider>,
    );

    await waitFor(() => {
      expect(screen.getByText('Failed reading schedule')).toBeDefined();
    });
    unmount();

    // 2. Snapshot list load fails
    global.fetch = vi.fn().mockImplementation((url: string) => {
      if (url.includes('/backups')) {
        return Promise.resolve(
          new Response(JSON.stringify({ detail: 'Failed listing backups' }), {
            status: 500,
            headers: { 'Content-Type': 'application/json' },
          }),
        );
      }
      return Promise.resolve(
        new Response(
          JSON.stringify({
            enabled: false,
            interval_hours: 24,
            retention_count: 7,
            last_run_at: null,
            next_run_at: null,
          }),
          { status: 200 },
        ),
      );
    });

    const render2 = render(
      <QueryClientProvider client={queryClient}>
        <StandaloneStatusPanel
          onClose={() => { /* noop */ }}
          initialStatus={adminStatus}
          initialTab="backup"
        />
      </QueryClientProvider>,
    );

    await waitFor(() => {
      expect(screen.getByText('Failed listing backups')).toBeDefined();
    });
    render2.unmount();

    // 3. Network throw on load
    global.fetch = vi.fn().mockRejectedValue(new Error('Connection refused'));
    render(
      <QueryClientProvider client={queryClient}>
        <StandaloneStatusPanel
          onClose={() => { /* noop */ }}
          initialStatus={adminStatus}
          initialTab="backup"
        />
      </QueryClientProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('standalone-api-error-alert')).toBeDefined();
    });
    expect(
      within(screen.getByTestId('standalone-api-error-alert')).getByText('Connection refused'),
    ).toBeDefined();
  });

  it('KANBA-208: handles verify and restore failure branches with API errors and file upload', async () => {
    const adminStatus: SystemStatus = {
      deployment_mode: 'standalone_embedded_pg',
      persistent_volume: true,
      air_gap_mode: false,
      local_llm_endpoint_host: null,
      is_server_admin: true,
    };

    let verifyCount = 0;
    let restoreCount = 0;
    global.fetch = vi.fn().mockImplementation((url: string, opts?: { method?: string }) => {
      if (url.includes('/backup/verify')) {
        verifyCount++;
        if (verifyCount === 1) {
          return Promise.resolve(
            new Response(JSON.stringify({ detail: 'Invalid checksum' }), {
              status: 400,
              headers: { 'Content-Type': 'application/json' },
            }),
          );
        }
        return Promise.resolve(
          new Response(
            JSON.stringify({
              valid: true,
              manifest: { format_version: 1, pg_server_version: '16.1', alembic_revision: 'rev_123' },
            }),
            { status: 200, headers: { 'Content-Type': 'application/json' } },
          ),
        );
      }
      if (url.includes('/restore') && opts?.method === 'POST') {
        restoreCount++;
        if (restoreCount === 1) {
          return Promise.resolve(
            new Response(JSON.stringify({ detail: 'pg_restore execution failed' }), {
              status: 500,
              headers: { 'Content-Type': 'application/json' },
            }),
          );
        }
        return Promise.resolve(new Response('{}', { status: 200 }));
      }
      return Promise.resolve(new Response('{}', { status: 200 }));
    });

    render(
      <QueryClientProvider client={queryClient}>
        <StandaloneStatusPanel
          onClose={() => { /* noop */ }}
          initialStatus={adminStatus}
          initialTab="backup"
        />
      </QueryClientProvider>,
    );

    // Upload a mock file
    const fileInput = screen.getByLabelText<HTMLInputElement>('Upload Backup Archive (.kbbak or .kbkp)');
    const testFile = new File(['dummy-archive-content'], 'test-archive.kbbak', {
      type: 'application/octet-stream',
    });
    fireEvent.change(fileInput, { target: { files: [testFile] } });

    // Add passphrase
    const passphraseInput = screen.getByLabelText('Passphrase (if encrypted with passphrase)');
    fireEvent.change(passphraseInput, { target: { value: 'test-passphrase-123' } });

    const verifyBtn = screen.getByRole('button', { name: 'Step 1: Verify Backup Archive' });

    // 1. Verify returns 400 error
    act(() => {
      fireEvent.click(verifyBtn);
    });

    await waitFor(() => {
      expect(screen.getByText('Invalid checksum')).toBeDefined();
    });

    // 2. Verify succeeds with manifest
    act(() => {
      fireEvent.click(verifyBtn);
    });

    await waitFor(() => {
      expect(screen.getByText(/✓ Backup Archive Verified/)).toBeDefined();
    });

    // 3. Confirm restore with wrong string
    const confirmInput = screen.getByPlaceholderText('RESTORE');
    const restoreBtn = screen.getByRole('button', { name: /Step 2: Restore Database/ });

    fireEvent.change(confirmInput, { target: { value: 'WRONG' } });
    expect(restoreBtn.hasAttribute('disabled')).toBe(true);

    fireEvent.change(confirmInput, { target: { value: 'RESTORE' } });
    expect(restoreBtn.hasAttribute('disabled')).toBe(false);

    // 4. Submit restore, returns 500 error
    act(() => {
      fireEvent.click(restoreBtn);
    });

    await waitFor(() => {
      expect(screen.getByText('pg_restore execution failed')).toBeDefined();
    });
  });

  it('KANBA-208: handles verify and restore using selectedSnapshotFilename and network exception branches', async () => {
    const adminStatus: SystemStatus = {
      deployment_mode: 'standalone_embedded_pg',
      persistent_volume: true,
      air_gap_mode: false,
      local_llm_endpoint_host: null,
      is_server_admin: true,
    };

    const mockSnapshots = [
      {
        filename: 'server-snap-1.kbbak',
        size_bytes: 10240,
        created_at: '2026-11-18T12:00:00Z',
      },
    ];

    let restoreCallBody: string | null = null;
    let restoreCallCount = 0;
    global.fetch = vi.fn().mockImplementation((url: string, opts?: { method?: string; body?: string }) => {
      if (url.includes('/backup-schedule')) {
        return Promise.resolve(new Response('{}', { status: 200 }));
      }
      if (url.includes('/backups')) {
        return Promise.resolve(new Response(JSON.stringify(mockSnapshots), { status: 200 }));
      }
      if (url.includes('/backup/verify')) {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              valid: true,
              manifest: { format_version: 1, pg_server_version: '16.0' },
            }),
            { status: 200 },
          ),
        );
      }
      if (url.includes('/restore') && opts?.method === 'POST') {
        restoreCallCount++;
        if (restoreCallCount === 1) {
          restoreCallBody = opts.body ?? null;
          return Promise.resolve(new Response('{}', { status: 200 }));
        }
        return Promise.reject(new Error('Network socket disconnected'));
      }
      return Promise.resolve(new Response('{}', { status: 200 }));
    });

    render(
      <QueryClientProvider client={queryClient}>
        <StandaloneStatusPanel
          onClose={() => { /* noop */ }}
          initialStatus={adminStatus}
          initialTab="backup"
        />
      </QueryClientProvider>,
    );

    await waitFor(() => {
      expect(screen.getByLabelText('Select Server Snapshot')).toBeDefined();
    });

    const select = screen.getByLabelText('Select Server Snapshot');
    fireEvent.change(select, { target: { value: 'server-snap-1.kbbak' } });

    const verifyBtn = screen.getByRole('button', { name: 'Step 1: Verify Backup Archive' });
    act(() => {
      fireEvent.click(verifyBtn);
    });

    await waitFor(() => {
      expect(screen.getByText(/✓ Backup Archive Verified/)).toBeDefined();
    });

    // Destructive confirm
    const confirmInput = screen.getByPlaceholderText('RESTORE');
    const restoreBtn = screen.getByRole('button', { name: /Step 2: Restore Database/ });

    fireEvent.change(confirmInput, { target: { value: 'RESTORE' } });
    act(() => {
      fireEvent.click(restoreBtn);
    });

    await waitFor(() => {
      expect(screen.getByText(/Database restored successfully/)).toBeDefined();
    });
    expect(restoreCallBody).not.toBeNull();
    expect(JSON.parse(String(restoreCallBody))).toEqual({
      filename: 'server-snap-1.kbbak',
      confirm_overwrite: 'RESTORE',
    });
  });

  it('KANBA-208: covers edge branches including non-admin backup tab, verify/restore errors, run-now success, and malformed json error', async () => {
    // 1. Non-admin switches to backup tab -> hits isServerAdmin early return and non-admin tabs
    const memberStatus: SystemStatus = {
      deployment_mode: 'standalone_embedded_pg',
      persistent_volume: true,
      air_gap_mode: false,
      local_llm_endpoint_host: null,
      is_server_admin: false,
    };

    const { unmount: unmountMember } = render(
      <QueryClientProvider client={queryClient}>
        <StandaloneStatusPanel
          onClose={() => { /* noop */ }}
          initialStatus={memberStatus}
          initialTab="health"
        />
      </QueryClientProvider>,
    );

    const backupTabBtn = screen.getByRole('tab', { name: /Backup/i });
    fireEvent.click(backupTabBtn);
    expect(screen.getByText(/Contact a Server Administrator to export backups/i)).toBeDefined();
    unmountMember();

    // 2. Admin operations: run-now success, verify without selection, restore without confirmation
    const adminStatus: SystemStatus = {
      deployment_mode: 'standalone_embedded_pg',
      persistent_volume: true,
      air_gap_mode: false,
      local_llm_endpoint_host: null,
      is_server_admin: true,
    };

    const mockSnapshots = [
      {
        filename: 'server-snap-1.kbbak',
        size_bytes: 10240,
        created_at: '2026-11-18T12:00:00Z',
      },
    ];

    let runNowCalled = false;
    global.fetch = vi.fn().mockImplementation((url: string, opts?: { method?: string }) => {
      if (url.includes('/backup-schedule')) {
        if (opts?.method === 'PUT') {
          return Promise.reject(new Error('Network drop on schedule save'));
        }
        return Promise.resolve(new Response('{}', { status: 200 }));
      }
      if (url.includes('/backups/run-now') && opts?.method === 'POST') {
        runNowCalled = true;
        return Promise.resolve(new Response('{}', { status: 200 }));
      }
      if (url.includes('/backups')) {
        return Promise.resolve(new Response(JSON.stringify(mockSnapshots), { status: 200 }));
      }
      if (url.includes('/backup/verify')) {
        // Return valid without manifest to test manifest fallback branch
        return Promise.resolve(new Response(JSON.stringify({ valid: true }), { status: 200 }));
      }
      return Promise.resolve(new Response('{}', { status: 200 }));
    });

    render(
      <QueryClientProvider client={queryClient}>
        <StandaloneStatusPanel
          onClose={() => { /* noop */ }}
          initialStatus={adminStatus}
          initialTab="backup"
        />
      </QueryClientProvider>,
    );

    // Test run-now success
    const runNowBtn = screen.getByRole('button', { name: 'Run Backup Now' });
    act(() => {
      fireEvent.click(runNowBtn);
    });
    await waitFor(() => {
      expect(runNowCalled).toBe(true);
    });

    // Test save-schedule network failure
    const saveSchedBtn = screen.getByRole('button', { name: 'Save Schedule' });
    act(() => {
      fireEvent.click(saveSchedBtn);
    });
    await waitFor(() => {
      expect(screen.getByText('Network drop on schedule save')).toBeDefined();
    });

    // Test run-now network failure
    global.fetch = vi.fn().mockImplementation((url: string, opts?: { method?: string }) => {
      if (url.includes('/backups/run-now') && opts?.method === 'POST') {
        return Promise.reject(new Error('Network drop on run now'));
      }
      return Promise.resolve(new Response('{}', { status: 200 }));
    });

    act(() => {
      fireEvent.click(runNowBtn);
    });
    await waitFor(() => {
      expect(screen.getByText('Network drop on run now')).toBeDefined();
    });

    // Dismiss the error before testing verify and restore
    const dismissBtn = screen.getByRole('button', { name: 'Dismiss error' });
    fireEvent.click(dismissBtn);

    // Select snapshot and run verify (manifest: undefined fallback branch)
    await waitFor(() => {
      expect(screen.getByLabelText('Select Server Snapshot')).toBeDefined();
    });
    const select = screen.getByLabelText('Select Server Snapshot');
    fireEvent.change(select, { target: { value: 'server-snap-1.kbbak' } });

    const verifyBtn = screen.getByRole('button', { name: 'Step 1: Verify Backup Archive' });
    act(() => {
      fireEvent.click(verifyBtn);
    });
    await waitFor(() => {
      expect(screen.getByText(/✓ Backup Archive Verified/)).toBeDefined();
    });

    // Destructive confirmation form is now visible
    const restoreForm = screen.getByRole('button', { name: /Step 2: Restore Database/ }).closest('form');
    expect(restoreForm).not.toBeNull();
    const confirmInput = screen.getByPlaceholderText('RESTORE');

    // Test restore submit with unconfirmed text
    fireEvent.change(confirmInput, { target: { value: 'WRONG' } });
    if (restoreForm) {
      act(() => {
        fireEvent.submit(restoreForm);
      });
      await waitFor(() => {
        expect(screen.getByText('You must type RESTORE exactly to confirm destructive database overwrite')).toBeDefined();
      });
    }

    // Now test with text RESTORE but no file or snapshot (clear select)
    fireEvent.change(select, { target: { value: '' } });
    fireEvent.change(confirmInput, { target: { value: 'RESTORE' } });
    if (restoreForm) {
      act(() => {
        fireEvent.submit(restoreForm);
      });
      await waitFor(() => {
        expect(screen.getByText('Please select a backup file or snapshot to restore')).toBeDefined();
      });
    }

    // Test empty interval and retention fallback branches
    const intervalInput = screen.getByLabelText('Backup Interval (hours)', { selector: 'input' });
    const retentionInput = screen.getByLabelText('Keep Latest Snapshots', { selector: 'input' });
    fireEvent.change(intervalInput, { target: { value: '' } });
    fireEvent.change(retentionInput, { target: { value: '' } });

    // Test clearing file input (files: null / empty array)
    const fileInput = screen.getByLabelText('Upload Backup Archive (.kbbak or .kbkp)');
    fireEvent.change(fileInput, { target: { files: [] } });

    // Test verify network failure
    global.fetch = vi.fn().mockImplementation((url: string) => {
      if (url.includes('/backup/verify')) {
        return Promise.reject(new Error('Verify network failure'));
      }
      return Promise.resolve(new Response('{}', { status: 200 }));
    });
    fireEvent.change(select, { target: { value: 'server-snap-1.kbbak' } });
    act(() => {
      fireEvent.click(verifyBtn);
    });
    await waitFor(() => {
      expect(screen.getByText('Verify network failure')).toBeDefined();
    });

    // Test verify non-Error failure
    global.fetch = vi.fn().mockImplementation((url: string) => {
      if (url.includes('/backup/verify')) {
        // eslint-disable-next-line @typescript-eslint/prefer-promise-reject-errors
        return Promise.reject('String verify failure');
      }
      return Promise.resolve(new Response('{}', { status: 200 }));
    });
    act(() => {
      fireEvent.click(verifyBtn);
    });
    await waitFor(() => {
      expect(screen.getByText('Backup verification failed')).toBeDefined();
    });

    // Test malformed non-JSON response without correlation ID header
    global.fetch = vi.fn().mockImplementation((url: string, opts?: { method?: string }) => {
      if (url.includes('/backups/run-now') && opts?.method === 'POST') {
        return Promise.resolve({
          ok: false,
          status: 500,
          headers: new Headers(),
          json: () => Promise.reject(new Error('SyntaxError')),
        } as unknown as Response);
      }
      return Promise.resolve(new Response('{}', { status: 200 }));
    });

    act(() => {
      fireEvent.click(runNowBtn);
    });
    await waitFor(() => {
      expect(screen.getByText(/Immediate backup snapshot failed with status 500/)).toBeDefined();
    });

    // Remove CSRF meta tags to cover if (csrf) false branches across actions
    document.querySelectorAll('meta[name="csrf-token"]').forEach((el) => { el.remove(); });

    // Test non-Error throw on schedule save
    global.fetch = vi.fn().mockImplementation((url: string, opts?: { method?: string }) => {
      if (url.includes('/backup-schedule') && opts?.method === 'PUT') {
        // eslint-disable-next-line @typescript-eslint/prefer-promise-reject-errors
        return Promise.reject('String save schedule failure');
      }
      return Promise.resolve(new Response('{}', { status: 200 }));
    });
    act(() => {
      fireEvent.click(saveSchedBtn);
    });
    await waitFor(() => {
      expect(screen.getByText('Failed to save backup schedule')).toBeDefined();
    });

    // Test non-Error throw on run now
    global.fetch = vi.fn().mockImplementation((url: string, opts?: { method?: string }) => {
      if (url.includes('/backups/run-now') && opts?.method === 'POST') {
        // eslint-disable-next-line @typescript-eslint/prefer-promise-reject-errors
        return Promise.reject('String run now failure');
      }
      return Promise.resolve(new Response('{}', { status: 200 }));
    });
    act(() => {
      fireEvent.click(runNowBtn);
    });
    await waitFor(() => {
      expect(screen.getByText('Immediate backup snapshot failed')).toBeDefined();
    });

    // Test non-Error throw on restore
    global.fetch = vi.fn().mockImplementation((url: string, opts?: { method?: string }) => {
      if (url.includes('/backup/verify')) {
        return Promise.resolve(new Response(JSON.stringify({ valid: true, manifest: { format_version: 1 } }), { status: 200 }));
      }
      if (url.includes('/restore') && opts?.method === 'POST') {
        // eslint-disable-next-line @typescript-eslint/prefer-promise-reject-errors
        return Promise.reject('String restore failure');
      }
      return Promise.resolve(new Response('{}', { status: 200 }));
    });

    const dismiss2 = screen.getByRole('button', { name: 'Dismiss error' });
    fireEvent.click(dismiss2);

    fireEvent.change(select, { target: { value: 'server-snap-1.kbbak' } });
    act(() => {
      fireEvent.click(verifyBtn);
    });
    await waitFor(() => {
      expect(screen.getByText(/✓ Backup Archive Verified/)).toBeDefined();
    });

    const newRestoreForm = screen.getByRole('button', { name: /Step 2: Restore Database/ }).closest('form');
    const newConfirmInput = screen.getByPlaceholderText('RESTORE');
    fireEvent.change(newConfirmInput, { target: { value: 'RESTORE' } });
    if (newRestoreForm) {
      act(() => {
        fireEvent.submit(newRestoreForm);
      });
      await waitFor(() => {
        expect(screen.getByText('Database restore failed')).toBeDefined();
      });
    }

    // Re-attach CSRF meta tag for subsequent tests
    const meta = document.createElement('meta');
    meta.name = 'csrf-token';
    meta.content = 'mock-csrf-token-xyz';
    document.head.appendChild(meta);
  });
});

describe('ComposeExportTab', () => {
  let clipboardMock: ReturnType<typeof vi.fn>;
  let createObjectURLMock: ReturnType<typeof vi.fn>;
  let revokeObjectURLMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    clipboardMock = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, {
      clipboard: {
        writeText: clipboardMock,
      },
    });

    createObjectURLMock = vi.fn().mockReturnValue('blob:mock-compose-url');
    revokeObjectURLMock = vi.fn();
    window.URL.createObjectURL = createObjectURLMock as unknown as typeof window.URL.createObjectURL;
    window.URL.revokeObjectURL = revokeObjectURLMock as unknown as typeof window.URL.revokeObjectURL;
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('handles res.ok false in fetchExportData and null exportData in download/copy', async () => {
    // 1. Mock fetch returns 500
    const mockFetch = vi.fn().mockResolvedValue(
      new Response('Internal server error', {
        status: 500,
        headers: { 'Content-Type': 'text/plain' },
      }),
    );
    global.fetch = mockFetch;

    render(<ComposeExportTab />);

    await waitFor(() => {
      expect(screen.getByText('Failed to load compose export: 500')).toBeDefined();
    });

    // Clicking download when fetchExportData returns null hits lines 67, 70
    const downloadBtn = screen.getByRole('button', { name: 'Download docker-compose.yml' });
    act(() => {
      fireEvent.click(downloadBtn);
    });
    expect(createObjectURLMock).not.toHaveBeenCalled();

    // Clicking copy when fetchExportData returns null hits lines 95, 98
    const copyBtn = screen.getByRole('button', { name: 'Copy .env.example' });
    await act(async () => {
      fireEvent.click(copyBtn);
      await Promise.resolve();
    });
    expect(clipboardMock).not.toHaveBeenCalled();
  });

  it('handles copy and download errors when data is present', async () => {
    const mockExportData = {
      filename: '',
      compose_yaml: 'services:\n  kanban:\n    image: kanban:latest\n',
      env_template: 'KB_SECRET=test-secret-123\n',
      migration_steps_markdown: '1. step\n',
    };

    render(<ComposeExportTab initialData={mockExportData} />);

    // 1. Copy error with string throw
    clipboardMock.mockRejectedValueOnce('Clipboard raw failure');
    const copyBtn = screen.getByRole('button', { name: 'Copy .env.example' });
    await act(async () => {
      fireEvent.click(copyBtn);
      await Promise.resolve();
    });
    await waitFor(() => {
      expect(screen.getByText('Failed to copy')).toBeDefined();
    });

    // 1b. Copy error with Error instance
    clipboardMock.mockRejectedValueOnce(new Error('Clipboard denied instance'));
    await act(async () => {
      fireEvent.click(copyBtn);
      await Promise.resolve();
    });
    await waitFor(() => {
      expect(screen.getByText('Clipboard denied instance')).toBeDefined();
    });

    // 1c. Successful download with empty filename fallback
    const downloadBtn = screen.getByRole('button', { name: 'Download docker-compose.yml' });
    await act(async () => {
      fireEvent.click(downloadBtn);
      await Promise.resolve();
    });
    await waitFor(() => {
      expect(createObjectURLMock).toHaveBeenCalled();
    });

    // 2. Download error with string throw
    createObjectURLMock.mockImplementationOnce(() => {
      // eslint-disable-next-line @typescript-eslint/only-throw-error
      throw 'Blob creation raw failure';
    });
    act(() => {
      fireEvent.click(downloadBtn);
    });
    await waitFor(() => {
      expect(screen.getByText('Download failed')).toBeDefined();
    });

    // 2b. Download error with Error instance
    createObjectURLMock.mockImplementationOnce(() => {
      throw new Error('Blob creation error instance');
    });
    act(() => {
      fireEvent.click(downloadBtn);
    });
    await waitFor(() => {
      expect(screen.getByText('Blob creation error instance')).toBeDefined();
    });
  });

  it('renders 4-step monospace checklist, downloads compose YAML and copies env template', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const mockExportData = {
      filename: 'docker-compose.yml',
      compose_yaml: 'services:\n  kanban:\n    image: kanban:latest\n',
      env_template: 'KB_SECRET=test-secret-123\n',
      migration_steps_markdown: '1. step\n',
    };

    render(<ComposeExportTab initialData={mockExportData} />);

    // 4-step checklist verification
    expect(screen.getByText('PostgreSQL 16 Promotion Runbook:')).toBeDefined();
    const checklistPre = screen.getByText(/1\. Generate secrets/);
    expect(checklistPre.textContent).toContain('1. Generate secrets');
    expect(checklistPre.textContent).toContain('2. Download encrypted backup (.kbbak)');
    expect(checklistPre.textContent).toContain('3. docker compose up -d postgres');
    expect(checklistPre.textContent).toContain(
      '4. kanban-ctl restore / pg_restore into external PostgreSQL 16',
    );

    // Download compose button
    const downloadBtn = screen.getByRole('button', {
      name: 'Download docker-compose.yml',
    });
    act(() => {
      fireEvent.click(downloadBtn);
    });

    await waitFor(() => {
      expect(createObjectURLMock).toHaveBeenCalled();
    });
    expect(revokeObjectURLMock).toHaveBeenCalledWith('blob:mock-compose-url');

    // Copy env button
    const copyEnvBtn = screen.getByRole('button', { name: 'Copy .env.example' });
    await act(async () => {
      fireEvent.click(copyEnvBtn);
      await Promise.resolve();
    });

    expect(clipboardMock).toHaveBeenCalledWith('KB_SECRET=test-secret-123\n');
    expect(screen.getByText('Copied!')).toBeDefined();

    // Advance timer to test timeout reset
    act(() => {
      vi.advanceTimersByTime(2500);
    });
    expect(screen.queryByText('Copied!')).toBeNull();
    vi.useRealTimers();
  });

  it('fetches compose export data on mount when initialData is omitted and covers remaining branches', async () => {
    const mockExport = {
      filename: 'docker-compose.yml',
      compose_yaml: 'services:\n  kanban:\n    image: kanban:latest\n',
      env_template: 'KB_VAR=123\n',
      migration_steps_markdown: 'Steps\n',
    };

    const mockFetch = vi.fn().mockImplementation(() => {
      return Promise.resolve(
        new Response(JSON.stringify(mockExport), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
      );
    });
    global.fetch = mockFetch;

    render(<ComposeExportTab />);

    const downloadBtn = screen.getByRole('button', {
      name: 'Download docker-compose.yml',
    });

    await waitFor(() => {
      expect(downloadBtn.hasAttribute('disabled')).toBe(false);
    });

    // Both download and copy should now operate on fetched data
    await act(async () => {
      fireEvent.click(downloadBtn);
      await Promise.resolve();
    });
    await waitFor(() => {
      expect(createObjectURLMock).toHaveBeenCalled();
    });
  });

  it('handles copy early return when fetchExportData fails and returns null', async () => {
    const mockFetch = vi.fn().mockImplementation(() => {
      return Promise.resolve(new Response('Forbidden', { status: 403 }));
    });
    global.fetch = mockFetch;

    render(<ComposeExportTab />);

    await waitFor(() => {
      expect(screen.getByRole('alert')).toBeDefined();
    });

    const copyBtn = screen.getByRole('button', { name: 'Copy .env.example' });
    await act(async () => {
      fireEvent.click(copyBtn);
      await Promise.resolve();
    });

    const downloadBtn = screen.getByRole('button', { name: 'Download docker-compose.yml' });
    await act(async () => {
      fireEvent.click(downloadBtn);
      await Promise.resolve();
    });

    // Clipboard write should not be called because exportData is null
    expect(clipboardMock).not.toHaveBeenCalled();
  });

  it('supports single-container and multi-container toggle in ComposeExportTab', () => {
    const mockData = {
      filename: 'docker-compose.yml',
      compose_yaml: 'services:\n  kanban:\n    image: thumbs-up-kanban:latest\n',
      single_container_compose_yaml: 'services:\n  standalone:\n    image: thumbs-up-kanban:latest\n',
      env_template: 'PORT=8080\n',
      migration_steps_markdown: '### Steps',
    };

    const { unmount: unmountFirst } = render(<ComposeExportTab initialData={mockData} />);

    expect(screen.getByRole('button', { name: 'Download docker-compose.yml' })).toBeDefined();

    // Toggle to Single-Container
    const singleTab = screen.getByRole('button', { name: 'Single-Container (Standalone)' });
    act(() => {
      fireEvent.click(singleTab);
    });

    const singleDownloadBtn = screen.getByRole('button', { name: 'Download docker-compose.standalone.yml' });
    expect(singleDownloadBtn).toBeDefined();
    fireEvent.click(singleDownloadBtn);
    expect(screen.getByText(/Runs 👍kanban and embedded PostgreSQL in a single container/)).toBeDefined();

    // Toggle back to Multi-Container
    const multiTab = screen.getByRole('button', { name: 'Multi-Container Stack (Production)' });
    act(() => {
      fireEvent.click(multiTab);
    });
    expect(screen.getByRole('button', { name: 'Download docker-compose.yml' })).toBeDefined();
    unmountFirst();

    // Test single-container download fallback when single_container_compose_yaml is omitted
    const mockDataNoSingle = {
      filename: 'docker-compose.yml',
      compose_yaml: 'services:\n  kanban:\n    image: kanban:latest\n',
      env_template: 'PORT=8080\n',
      migration_steps_markdown: '### Steps',
    };
    const { unmount } = render(<ComposeExportTab initialData={mockDataNoSingle} />);
    const singleBtn = screen.getByRole('button', { name: 'Single-Container (Standalone)' });
    fireEvent.click(singleBtn);
    const dlSingleBtn = screen.getByRole('button', { name: 'Download docker-compose.standalone.yml' });
    fireEvent.click(dlSingleBtn);
    unmount();
  });

  it('covers ComposeExportTab copy env failure when clipboard returns false or throws', async () => {
    Object.defineProperty(navigator, 'clipboard', {
      value: { writeText: undefined },
      configurable: true,
    });
    /* eslint-disable @typescript-eslint/no-deprecated */
    const originalExec = typeof document.execCommand === 'function' ? document.execCommand.bind(document) : undefined;
    document.execCommand = vi.fn().mockReturnValue(false);
    /* eslint-enable @typescript-eslint/no-deprecated */

    render(
      <ComposeExportTab
        initialData={{
          filename: 'docker-compose.yml',
          compose_yaml: 'services:\n',
          env_template: 'VAR=1\n',
          migration_steps_markdown: 'Steps',
        }}
      />,
    );

    const copyBtn = screen.getByRole('button', { name: 'Copy .env.example' });
    await act(async () => {
      fireEvent.click(copyBtn);
      await Promise.resolve();
    });

    expect(screen.getByRole('alert').textContent).toContain('Failed to copy');
    /* eslint-disable @typescript-eslint/no-deprecated */
    if (originalExec) {
      document.execCommand = originalExec;
    }
    /* eslint-enable @typescript-eslint/no-deprecated */
  });

  it('handles automated backup schedule editing and saving', async () => {
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const adminStatus: SystemStatus = {
      deployment_mode: 'standalone_embedded_pg',
      persistent_volume: true,
      air_gap_mode: false,
      local_llm_endpoint_host: null,
      is_server_admin: true,
      data_mount_point: '/var/lib/kanban/data',
      data_mount_fstype: 'ext4',
      tier_b_sandbox_available: true,
    };

    const mockSchedule = { enabled: false, interval_hours: 24, retention_count: 7 };
    const mockSnapshots: unknown[] = [];

    const mockFetch = vi.fn().mockImplementation((url: string, opts?: RequestInit) => {
      if (url === '/api/v1/admin/standalone/backup-schedule' && (!opts || opts.method === 'GET')) {
        return Promise.resolve(new Response(JSON.stringify(mockSchedule), { status: 200 }));
      }
      if (url === '/api/v1/admin/standalone/backups' && (!opts || opts.method === 'GET')) {
        return Promise.resolve(new Response(JSON.stringify(mockSnapshots), { status: 200 }));
      }
      if (url === '/api/v1/admin/standalone/backup-schedule' && opts?.method === 'PUT') {
        return Promise.resolve(
          new Response(
            JSON.stringify({ enabled: true, interval_hours: 12, retention_count: 14 }),
            { status: 200 },
          ),
        );
      }
      return Promise.resolve(new Response('{}', { status: 200 }));
    });
    global.fetch = mockFetch;

    render(
      <QueryClientProvider client={queryClient}>
        <StandaloneStatusPanel onClose={() => undefined} initialStatus={adminStatus} />
      </QueryClientProvider>,
    );

    // Switch to Backups & Restore tab
    const backupsTab = screen.getByRole('tab', { name: 'Backup, Auto-Backup & Restore' });
    act(() => {
      fireEvent.click(backupsTab);
    });

    const enableCheckbox = screen.getByLabelText<HTMLInputElement>('Enable Automated Backups');
    const intervalInput = screen.getByLabelText<HTMLInputElement>('Backup Interval (hours)', { selector: 'input' });
    const retentionInput = screen.getByLabelText<HTMLInputElement>('Keep Latest Snapshots', { selector: 'input' });

    act(() => {
      fireEvent.click(enableCheckbox);
      fireEvent.change(intervalInput, { target: { value: '12' } });
      fireEvent.change(retentionInput, { target: { value: '14' } });
    });

    const saveScheduleBtn = screen.getByRole('button', { name: 'Save Schedule' });
    await act(async () => {
      fireEvent.click(saveScheduleBtn);
      await Promise.resolve();
    });

    expect(mockFetch).toHaveBeenCalledWith(
      '/api/v1/admin/standalone/backup-schedule',
      expect.objectContaining({
        method: 'PUT',
        body: JSON.stringify({ enabled: true, interval_hours: 12, retention_count: 14 }),
      }),
    );
  });

  it('triggers manual backup run and verifies snapshot restoration', async () => {
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const adminStatus: SystemStatus = {
      deployment_mode: 'standalone_embedded_pg',
      persistent_volume: true,
      air_gap_mode: false,
      local_llm_endpoint_host: null,
      is_server_admin: true,
      data_mount_point: '/var/lib/kanban/data',
      data_mount_fstype: 'ext4',
      tier_b_sandbox_available: true,
    };

    const mockSchedule = { enabled: true, interval_hours: 24, retention_count: 7 };
    const mockSnapshots = [
      {
        filename: 'kanban-backup-test.kbbak',
        size_bytes: 2048,
        created_at: '2026-03-01T12:00:00Z',
      },
    ];

    const mockFetch = vi.fn().mockImplementation((url: string) => {
      if (url === '/api/v1/admin/standalone/backup-schedule') {
        return Promise.resolve(new Response(JSON.stringify(mockSchedule), { status: 200 }));
      }
      if (url === '/api/v1/admin/standalone/backups') {
        return Promise.resolve(new Response(JSON.stringify(mockSnapshots), { status: 200 }));
      }
      if (url === '/api/v1/admin/standalone/backups/run-now') {
        return Promise.resolve(new Response('{"ok":true}', { status: 200 }));
      }
      if (url === '/api/v1/admin/standalone/backup/verify') {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              manifest: { pg_server_version: '16.2', alembic_revision: 'head_123' },
            }),
            { status: 200 },
          ),
        );
      }
      if (url === '/api/v1/admin/standalone/restore') {
        return Promise.resolve(
          new Response(JSON.stringify({ ok: true, message: 'Restore complete' }), { status: 200 }),
        );
      }
      return Promise.resolve(new Response('{}', { status: 200 }));
    });
    global.fetch = mockFetch;

    render(
      <QueryClientProvider client={queryClient}>
        <StandaloneStatusPanel onClose={() => undefined} initialStatus={adminStatus} />
      </QueryClientProvider>,
    );

    // Switch to Backups & Storage tab
    const backupsTab = screen.getByRole('tab', { name: 'Backup, Auto-Backup & Restore' });
    act(() => {
      fireEvent.click(backupsTab);
    });

    // Run Backup Now
    const runBackupBtn = screen.getByRole('button', { name: 'Run Backup Now' });
    await act(async () => {
      fireEvent.click(runBackupBtn);
      await Promise.resolve();
    });
    expect(mockFetch).toHaveBeenCalledWith(
      '/api/v1/admin/standalone/backups/run-now',
      expect.objectContaining({ method: 'POST' }),
    );

    // Verify existing snapshot table
    await waitFor(() => {
      expect(screen.getByText('kanban-backup-test.kbbak')).toBeDefined();
    });

    // Select snapshot from dropdown
    const snapshotSelect = screen.getByLabelText<HTMLSelectElement>('Select Server Snapshot');
    act(() => {
      fireEvent.change(snapshotSelect, { target: { value: 'kanban-backup-test.kbbak' } });
    });

    // Enter passphrase
    const passphraseInput = screen.getByLabelText<HTMLInputElement>(
      'Passphrase (if encrypted with passphrase)',
    );
    act(() => {
      fireEvent.change(passphraseInput, { target: { value: 'secretpass' } });
    });

    // Step 1: Verify Backup Archive
    const verifyBtn = screen.getByRole('button', { name: 'Step 1: Verify Backup Archive' });
    await act(async () => {
      fireEvent.click(verifyBtn);
      await Promise.resolve();
    });

    await waitFor(() => {
      expect(screen.getByText('✓ Backup Archive Verified')).toBeDefined();
    });

    // Step 2: Confirm Overwrite
    const confirmInput = screen.getByLabelText<HTMLInputElement>(
      'Type RESTORE to confirm overwriting current database:',
    );
    act(() => {
      fireEvent.change(confirmInput, { target: { value: 'RESTORE' } });
    });

    const restoreBtn = screen.getByRole('button', { name: 'Step 2: Restore Database' });
    await act(async () => {
      fireEvent.click(restoreBtn);
      await Promise.resolve();
    });

    await waitFor(() => {
      expect(
        screen.getByText(
          'Database restored successfully! Invariants, roles, and schema verified.',
        ),
      ).toBeDefined();
    });
  });

  it('handles backup verification failure and invalid restore confirmation text', async () => {
    const adminStatus: SystemStatus = {
      deployment_mode: 'standalone_embedded_pg',
      persistent_volume: true,
      air_gap_mode: false,
      local_llm_endpoint_host: null,
      is_server_admin: true,
      data_mount_point: '/var/lib/kanban/data',
      data_mount_fstype: 'ext4',
      tier_b_sandbox_available: true,
    };

    const mockSchedule = { enabled: true, interval_hours: 24, retention_count: 7 };
    const mockSnapshots = [
      {
        filename: 'corrupt-backup.kbbak',
        size_bytes: 1024,
        created_at: '2026-03-01T12:00:00Z',
      },
    ];

    const mockFetch = vi.fn().mockImplementation((url: string) => {
      if (url === '/api/v1/admin/standalone/backup-schedule') {
        return Promise.resolve(new Response(JSON.stringify(mockSchedule), { status: 200 }));
      }
      if (url === '/api/v1/admin/standalone/backups') {
        return Promise.resolve(new Response(JSON.stringify(mockSnapshots), { status: 200 }));
      }
      if (url === '/api/v1/admin/standalone/backup/verify') {
        return Promise.resolve(
          new Response(JSON.stringify({ detail: 'Corrupt archive header' }), { status: 400 }),
        );
      }
      return Promise.resolve(new Response('{}', { status: 200 }));
    });
    global.fetch = mockFetch;

    const testQueryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const onClose = vi.fn();
    document.cookie = 'kb_csrf=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;';
    render(
      <QueryClientProvider client={testQueryClient}>
        <StandaloneStatusPanel onClose={onClose} initialStatus={adminStatus} />
      </QueryClientProvider>,
    );

    const backupsTab = screen.getByRole('tab', { name: 'Backup, Auto-Backup & Restore' });
    fireEvent.click(backupsTab);

    // Wait for snapshots query to resolve
    await waitFor(() => {
      expect(screen.getByText('corrupt-backup.kbbak')).toBeDefined();
    });

    // Select snapshot and trigger verification error
    const snapshotSelect = screen.getByLabelText<HTMLSelectElement>('Select Server Snapshot');
    fireEvent.change(snapshotSelect, { target: { value: 'corrupt-backup.kbbak' } });

    const verifyBtn = screen.getByRole('button', { name: 'Step 1: Verify Backup Archive' });
    fireEvent.click(verifyBtn);

    await waitFor(() => {
      expect(screen.getByText('Corrupt archive header')).toBeDefined();
    });

    // Now mock valid verify so destructive form renders
    mockFetch.mockImplementationOnce((url: string) => {
      if (url === '/api/v1/admin/standalone/backup/verify') {
        return Promise.resolve(
          new Response(JSON.stringify({ manifest: { pg_server_version: '16.2' } }), { status: 200 }),
        );
      }
      return Promise.resolve(new Response('{}', { status: 200 }));
    });

    fireEvent.click(verifyBtn);

    await waitFor(() => {
      expect(screen.getByText('✓ Backup Archive Verified')).toBeDefined();
    });

    // Submit restore form with incorrect confirmation text
    const destructiveForm = document.querySelector('.standalone-panel__destructive-form');
    if (destructiveForm) {
      fireEvent.submit(destructiveForm);
    }

    await waitFor(() => {
      expect(screen.getByText('You must type RESTORE exactly to confirm destructive database overwrite')).toBeDefined();
    });

    // Backdrop click triggers onClose
    const backdrop = document.querySelector('.standalone-panel__backdrop');
    if (backdrop) {
      fireEvent.click(backdrop);
      expect(onClose).toHaveBeenCalled();
    }
  });

  it('covers restore from uploaded file with passphrase and manifest fallback', async () => {
    const adminStatus: SystemStatus = {
      deployment_mode: 'standalone_embedded_pg',
      persistent_volume: true,
      air_gap_mode: false,
      local_llm_endpoint_host: null,
      is_server_admin: true,
      data_mount_point: '/var/lib/kanban/data',
      data_mount_fstype: 'ext4',
      tier_b_sandbox_available: true,
    };

    let verifyBody: BodyInit | null | undefined = null;
    let restoreBody: BodyInit | null | undefined = null;

    const mockFetch = vi.fn().mockImplementation((url: string, init?: RequestInit) => {
      if (url === '/api/v1/admin/standalone/snapshots') {
        return Promise.resolve(new Response(JSON.stringify({ snapshots: [] }), { status: 200 }));
      }
      if (url === '/api/v1/admin/standalone/backup/verify') {
        verifyBody = init?.body;
        // Return without manifest to exercise fallback
        return Promise.resolve(new Response(JSON.stringify({ valid: true }), { status: 200 }));
      }
      if (url === '/api/v1/admin/standalone/restore') {
        restoreBody = init?.body;
        return Promise.resolve(new Response(JSON.stringify({ success: true }), { status: 200 }));
      }
      return Promise.resolve(new Response('{}', { status: 200 }));
    });
    globalThis.fetch = mockFetch;

    const testQueryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    document.cookie = 'kb_csrf=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;';
    document.cookie = 'kb_csrf=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;';
    render(
      <QueryClientProvider client={testQueryClient}>
        <StandaloneStatusPanel onClose={vi.fn()} initialStatus={adminStatus} />
      </QueryClientProvider>,
    );

    // Switch to Backups tab
    const backupsTab = screen.getByRole('tab', { name: 'Backup, Auto-Backup & Restore' });
    fireEvent.click(backupsTab);

    // Upload backup file
    const fileInput = screen.getByLabelText(/Upload Backup Archive/i);
    const testFile = new File(['mock binary archive content'], 'my-backup.kbbak', { type: 'application/octet-stream' });
    fireEvent.change(fileInput, { target: { files: [testFile] } });

    // Enter passphrase
    const passInput = screen.getByLabelText(/Passphrase \(if encrypted/i);
    fireEvent.change(passInput, { target: { value: 'SecretKey123!' } });

    // Click verify
    const verifyBtn = screen.getByRole('button', { name: 'Step 1: Verify Backup Archive' });
    fireEvent.click(verifyBtn);

    await waitFor(() => {
      expect(verifyBody).toBeInstanceOf(FormData);
      expect(screen.getByText('✓ Backup Archive Verified')).toBeDefined();
    });

    // Fill restore confirm
    const confirmInput = screen.getByLabelText(/Type RESTORE to confirm/i);
    fireEvent.change(confirmInput, { target: { value: 'RESTORE' } });

    // Click restore
    const restoreBtn = screen.getByRole('button', { name: /Step 2: Restore Database/i });
    fireEvent.click(restoreBtn);

    await waitFor(() => {
      expect(restoreBody).toBeInstanceOf(FormData);
      expect(screen.getByText('Database restored successfully! Invariants, roles, and schema verified.')).toBeDefined();
    });
  });

  it('handles restore failure with server error detail and string rejection', async () => {
    const adminStatus: SystemStatus = {
      deployment_mode: 'standalone_embedded_pg',
      persistent_volume: true,
      air_gap_mode: false,
      local_llm_endpoint_host: null,
      is_server_admin: true,
      data_mount_point: '/var/lib/kanban/data',
      data_mount_fstype: 'ext4',
      tier_b_sandbox_available: true,
    };

    let restoreFailMode = 'json';

    const mockFetch = vi.fn().mockImplementation((url: string) => {
      if (url === '/api/v1/admin/standalone/snapshots') {
        return Promise.resolve(new Response(JSON.stringify({ snapshots: [] }), { status: 200 }));
      }
      if (url === '/api/v1/admin/standalone/backup/verify') {
        return Promise.resolve(new Response(JSON.stringify({ valid: true }), { status: 200 }));
      }
      if (url === '/api/v1/admin/standalone/restore') {
        if (restoreFailMode === 'json') {
          return Promise.resolve(new Response(JSON.stringify({ detail: 'Schema migration conflict' }), { status: 500 }));
        }
        if (restoreFailMode === 'html') {
          return Promise.resolve(new Response('Gateway Timeout', { status: 504 }));
        }
        // eslint-disable-next-line @typescript-eslint/prefer-promise-reject-errors
        return Promise.reject('Connection drop');
      }
      return Promise.resolve(new Response('{}', { status: 200 }));
    });
    globalThis.fetch = mockFetch;

    const testQueryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    document.cookie = 'kb_csrf=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;';
    document.cookie = 'kb_csrf=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;';
    render(
      <QueryClientProvider client={testQueryClient}>
        <StandaloneStatusPanel onClose={vi.fn()} initialStatus={adminStatus} />
      </QueryClientProvider>,
    );

    const backupsTab = screen.getByRole('tab', { name: 'Backup, Auto-Backup & Restore' });
    fireEvent.click(backupsTab);

    const fileInput = screen.getByLabelText(/Upload Backup Archive/i);
    const testFile = new File(['mock content'], 'test.kbbak', { type: 'application/octet-stream' });
    fireEvent.change(fileInput, { target: { files: [testFile] } });

    fireEvent.click(screen.getByRole('button', { name: 'Step 1: Verify Backup Archive' }));

    await waitFor(() => {
      expect(screen.getByText('✓ Backup Archive Verified')).toBeDefined();
    });

    const confirmInput = screen.getByLabelText(/Type RESTORE to confirm/i);
    fireEvent.change(confirmInput, { target: { value: 'RESTORE' } });

    // 1. JSON error
    const restoreBtn = screen.getByRole('button', { name: /Step 2: Restore Database/i });
    fireEvent.click(restoreBtn);

    await waitFor(() => {
      expect(screen.getByText('Schema migration conflict')).toBeDefined();
    });

    // 2. HTML 504 error
    restoreFailMode = 'html';
    fireEvent.click(restoreBtn);
    await waitFor(() => {
      expect(screen.getByText('Database restore failed with status 504')).toBeDefined();
    });

    // 3. String rejection
    restoreFailMode = 'string';
    fireEvent.click(restoreBtn);
    await waitFor(() => {
      expect(screen.getByText('Database restore failed')).toBeDefined();
    });
  });

  it('covers tier_b_sandbox_available false, empty input schedule fallbacks, and verification status fallback', async () => {
    const testQueryClient = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });

    const mockAdminStatus: SystemStatus = {
      deployment_mode: 'standalone_embedded_pg',
      persistent_volume: false,
      air_gap_mode: false,
      local_llm_endpoint_host: null,
      is_server_admin: true,
      tier_b_sandbox_available: false,
    };

    vi.spyOn(window, 'fetch').mockImplementation(async (input: RequestInfo | URL) => {
      await Promise.resolve();
      const urlStr = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url;
      if (urlStr.includes('/backup-schedule')) {
        return new Response(
          JSON.stringify({ enabled: true, interval_hours: 12, retention_count: 5 }),
          { status: 200 },
        );
      }
      if (urlStr.includes('/snapshots')) {
        return new Response(JSON.stringify([]), { status: 200 });
      }
      if (urlStr.includes('/backup/verify')) {
        // Return 400 with empty JSON body
        return new Response('{}', { status: 400 });
      }
      return new Response('{}', { status: 200 });
    });

    document.cookie = 'kb_csrf=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;';
    render(
      <QueryClientProvider client={testQueryClient}>
        <StandaloneStatusPanel
          onClose={vi.fn()}
          initialStatus={mockAdminStatus}
        />
      </QueryClientProvider>,
    );

    // Verify tier B sandbox false is reflected
    expect(screen.getByText('Isolated Process & CLI Sandbox (Linux Namespaces)')).toBeDefined();
    expect(screen.getByText(/Not enabled in single-container mode/i)).toBeDefined();

    const backupsTab = screen.getByRole('tab', { name: 'Backup, Auto-Backup & Restore' });
    fireEvent.click(backupsTab);

    // Clear schedule input fields to trigger NaN fallback
    const intervalInput = screen.getByLabelText(/Backup Interval/i, { selector: 'input' });
    fireEvent.change(intervalInput, { target: { value: '' } });

    const retentionInput = screen.getByLabelText(/Keep Latest Snapshots/i, { selector: 'input' });
    fireEvent.change(retentionInput, { target: { value: '' } });

    // Upload backup and trigger verify error with empty detail fallback
    const fileInput = screen.getByLabelText(/Upload Backup Archive/i);
    const testFile = new File(['mock content'], 'test.kbbak', { type: 'application/octet-stream' });
    fireEvent.change(fileInput, { target: { files: [testFile] } });

    fireEvent.click(screen.getByRole('button', { name: 'Step 1: Verify Backup Archive' }));

    await waitFor(() => {
      expect(screen.getByText('Backup verification failed with status 400')).toBeDefined();
    });
  });

  it('progressively discloses technical details (storage volume, SQLite WAL dials, and sandbox bounds) in AdvancedSection', () => {
    const testQueryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    const mockStatus: SystemStatus = {
      deployment_mode: 'standalone_embedded_pg',
      persistent_volume: true,
      air_gap_mode: false,
      local_llm_endpoint_host: null,
      data_mount_point: '/var/lib/kanban/data',
      data_mount_fstype: 'ext4',
      tier_b_sandbox_available: true,
    };

    render(
      <QueryClientProvider client={testQueryClient}>
        <StandaloneStatusPanel
          onClose={vi.fn()}
          initialStatus={mockStatus}
        />
      </QueryClientProvider>,
    );

    // Advanced section is present and collapsed by default
    const advancedDetails = screen.getByTestId('standalone-advanced-technical-details');
    expect(advancedDetails).toBeDefined();
    expect(advancedDetails.hasAttribute('open')).toBe(false);

    // Toggle open
    const toggle = screen.getByTestId('standalone-advanced-technical-details-toggle');
    fireEvent.click(toggle);

    expect(advancedDetails.hasAttribute('open')).toBe(true);
    expect(screen.getByText(/Storage Volume Mount:/i)).toBeDefined();
    expect(screen.getByText(/Row-Level Security:/i)).toBeDefined();
    expect(screen.getByText(/FORCE ROW LEVEL SECURITY/i)).toBeDefined();
    expect(screen.getByText(/Tier-B nsjail strict cgroups/i)).toBeDefined();
  });

  it('downloads snapshot via handleDownloadSnapshot using apiFetchBlob', async () => {
    let downloadedUrl = '';
    const mockFetch = vi.fn().mockImplementation((url: string) => {
      if (url.includes('/api/v1/admin/standalone/backups/my-snap.kbbak')) {
        downloadedUrl = url;
        return Promise.resolve(
          new Response('snapshot-file-content', {
            status: 200,
            headers: {
              'Content-Type': 'application/octet-stream',
              'Content-Disposition': 'attachment; filename="my-snap.kbbak"',
            },
          }),
        );
      }
      if (url.includes('/api/v1/admin/standalone/backups')) {
        return Promise.resolve(
          new Response(
            JSON.stringify([
              {
                filename: 'my-snap.kbbak',
                size_bytes: 2048,
                created_at: '2026-11-20T10:00:00Z',
              },
            ]),
            { status: 200, headers: { 'Content-Type': 'application/json' } },
          ),
        );
      }
      return Promise.resolve(new Response('{}', { status: 200 }));
    });
    global.fetch = mockFetch;

    const snapClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const adminStatus: SystemStatus = {
      deployment_mode: 'standalone',
      is_server_admin: true,
      persistent_volume: true,
      air_gap_mode: false,
      local_llm_endpoint_host: null,
    };
    render(
      <QueryClientProvider client={snapClient}>
        <StandaloneStatusPanel
          onClose={vi.fn()}
          initialStatus={adminStatus}
          initialTab="backup"
        />
      </QueryClientProvider>,
    );

    await waitFor(() => {
      expect(screen.getByText('my-snap.kbbak')).toBeDefined();
    });

    const downloadBtn = screen.getByRole('button', { name: 'Download' });
    await act(async () => {
      fireEvent.click(downloadBtn);
      await Promise.resolve();
    });

    await waitFor(() => {
      expect(downloadedUrl).toContain('/api/v1/admin/standalone/backups/my-snap.kbbak');
    });
  });

  it('handles snapshot download failure with API error', async () => {
    global.fetch = vi.fn().mockImplementation((url: string) => {
      if (url.includes('/api/v1/admin/standalone/backups/err-snap.kbbak')) {
        return Promise.resolve(
          new Response(JSON.stringify({ detail: 'File corrupted' }), {
            status: 500,
            headers: { 'Content-Type': 'application/problem+json' },
          }),
        );
      }
      if (url.includes('/api/v1/admin/standalone/backups')) {
        return Promise.resolve(
          new Response(
            JSON.stringify([
              {
                filename: 'err-snap.kbbak',
                size_bytes: 1024,
                created_at: '2026-11-20T10:00:00Z',
              },
            ]),
            { status: 200, headers: { 'Content-Type': 'application/json' } },
          ),
        );
      }
      return Promise.resolve(new Response('{}', { status: 200 }));
    });

    const errClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const adminStatus: SystemStatus = {
      deployment_mode: 'standalone',
      is_server_admin: true,
      persistent_volume: true,
      air_gap_mode: false,
      local_llm_endpoint_host: null,
    };
    render(
      <QueryClientProvider client={errClient}>
        <StandaloneStatusPanel
          onClose={vi.fn()}
          initialStatus={adminStatus}
          initialTab="backup"
        />
      </QueryClientProvider>,
    );

    await waitFor(() => {
      expect(screen.getByText('err-snap.kbbak')).toBeDefined();
    });

    const errDownloadBtn = screen.getByRole('button', { name: 'Download' });
    await act(async () => {
      fireEvent.click(errDownloadBtn);
      await Promise.resolve();
    });

    await waitFor(() => {
      expect(screen.getByText('File corrupted')).toBeDefined();
    });
  });

  describe('KAN-530: Standalone Status Panel Backup & Schedule FieldHelpHints', () => {
    it('renders all 3 FieldHelpHint popovers for Backup Passphrase, Interval, and Retention', () => {
      const testClient = new QueryClient({
        defaultOptions: { queries: { retry: false } },
      });
      const adminStatus: SystemStatus = {
        deployment_mode: 'standalone',
        is_server_admin: true,
        persistent_volume: true,
        air_gap_mode: false,
        local_llm_endpoint_host: null,
      };

      render(
        <QueryClientProvider client={testClient}>
          <StandaloneStatusPanel
            onClose={vi.fn()}
            initialStatus={adminStatus}
            initialTab="backup"
          />
        </QueryClientProvider>,
      );

      // 1. Backup Passphrase Help Hint
      const passphraseHelpBtn = screen.getByTestId('backup-passphrase-help');
      expect(passphraseHelpBtn).toBeDefined();
      expect(passphraseHelpBtn.getAttribute('aria-label')).toContain('Backup Passphrase');

      act(() => {
        passphraseHelpBtn.focus();
      });

      const passphrasePopover = screen.getByTestId('backup-passphrase-help-popover');
      expect(passphrasePopover).toBeDefined();
      expect(passphrasePopover.textContent).toContain('AES-256-GCM authenticated encryption');
      expect(passphrasePopover.textContent).toContain('Argon2id/PBKDF2');

      const passphraseDocLink = screen.getByTestId('backup-passphrase-help-doc-link');
      expect(passphraseDocLink.getAttribute('href')).toBe('/docs/production-promotion-and-backup-runbook');

      // 2. Backup Interval (hours) Help Hint
      const intervalHelpBtn = screen.getByTestId('schedule-interval-help');
      expect(intervalHelpBtn).toBeDefined();
      expect(intervalHelpBtn.getAttribute('aria-label')).toContain('Backup Interval');

      act(() => {
        intervalHelpBtn.focus();
      });

      const intervalPopover = screen.getByTestId('schedule-interval-help-popover');
      expect(intervalPopover).toBeDefined();
      const intervalDefault = screen.getByTestId('schedule-interval-help-default');
      expect(intervalDefault.textContent).toContain('24 hours');

      const intervalDocLink = screen.getByTestId('schedule-interval-help-doc-link');
      expect(intervalDocLink.getAttribute('href')).toBe('/docs/production-promotion-and-backup-runbook');

      // 3. Keep Latest Snapshots Help Hint
      const retentionHelpBtn = screen.getByTestId('schedule-retention-help');
      expect(retentionHelpBtn).toBeDefined();
      expect(retentionHelpBtn.getAttribute('aria-label')).toContain('Keep Latest Snapshots');

      act(() => {
        retentionHelpBtn.focus();
      });

      const retentionPopover = screen.getByTestId('schedule-retention-help-popover');
      expect(retentionPopover).toBeDefined();
      const retentionDefault = screen.getByTestId('schedule-retention-help-default');
      expect(retentionDefault.textContent).toContain('7 snapshots');

      const retentionDocLink = screen.getByTestId('schedule-retention-help-doc-link');
      expect(retentionDocLink.getAttribute('href')).toBe('/docs/production-promotion-and-backup-runbook');
    });

    it('renders backup and schedule FieldHelpHints without regressions in light and dark mode', () => {
      const testClient = new QueryClient({
        defaultOptions: { queries: { retry: false } },
      });
      const adminStatus: SystemStatus = {
        deployment_mode: 'standalone',
        is_server_admin: true,
        persistent_volume: true,
        air_gap_mode: false,
        local_llm_endpoint_host: null,
      };

      const { container } = render(
        <QueryClientProvider client={testClient}>
          <StandaloneStatusPanel
            onClose={vi.fn()}
            initialStatus={adminStatus}
            initialTab="backup"
          />
        </QueryClientProvider>,
      );

      // Light mode verification
      document.documentElement.setAttribute('data-theme', 'light');
      expect(container.querySelector('.standalone-panel')).toBeDefined();
      expect(screen.getByTestId('backup-passphrase-help')).toBeDefined();
      expect(screen.getByTestId('schedule-interval-help')).toBeDefined();
      expect(screen.getByTestId('schedule-retention-help')).toBeDefined();

      // Dark mode verification
      document.documentElement.setAttribute('data-theme', 'dark');
      expect(container.querySelector('.standalone-panel')).toBeDefined();
      expect(screen.getByTestId('backup-passphrase-help')).toBeDefined();
      expect(screen.getByTestId('schedule-interval-help')).toBeDefined();
      expect(screen.getByTestId('schedule-retention-help')).toBeDefined();

      // Cleanup
      document.documentElement.removeAttribute('data-theme');
    });
  });
});
