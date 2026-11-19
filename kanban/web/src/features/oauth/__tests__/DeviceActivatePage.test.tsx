// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import React from 'react';
import { MemoryRouter } from 'react-router';
import { DeviceActivatePage, formatUserCodeInput } from '../DeviceActivatePage';
import * as oauthApi from '../oauthApi';

describe('DeviceActivatePage (KB-P4-16)', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  describe('formatUserCodeInput helper', () => {
    it('filters non-consonant characters and formats XXXX-XXXX', () => {
      expect(formatUserCodeInput('wdjbmjht')).toBe('WDJB-MJHT');
      expect(formatUserCodeInput('w d j b - m j h t')).toBe('WDJB-MJHT');
      // Vowels and numbers filtered
      expect(formatUserCodeInput('A1E8O0')).toBe('');
      expect(formatUserCodeInput('ABCD')).toBe('BCD');
      expect(formatUserCodeInput('BCDFGHJKLM')).toBe('BCDF-GHJK');
    });
  });

  it('renders input field, accepts user code, and fetches device info (Test Case 1)', async () => {
    const mockInfo: oauthApi.DeviceCodeInfoResponse = {
      user_code: 'WDJB-MJHT',
      client_name: 'Antigravity CLI',
      client_id: 'client_123',
      resource: 'https://kanban.example.com/mcp/agent',
      surface: 'agent',
      requested_scopes: ['agent:read', 'agent:write'],
      allowed_projects: ['KANBA'],
      expires_at: new Date(Date.now() + 600000).toISOString(),
    };

    vi.spyOn(oauthApi, 'fetchDeviceCodeInfo').mockResolvedValue(mockInfo);
    vi.spyOn(oauthApi, 'submitDeviceActivation').mockResolvedValue({ status: 'approved' });

    render(
      <MemoryRouter initialEntries={['/activate']}>
        <DeviceActivatePage />
      </MemoryRouter>,
    );

    const input = screen.getByTestId<HTMLInputElement>('user-code-input');
    fireEvent.change(input, { target: { value: 'WDJBMJHT' } });
    expect(input.value).toBe('WDJB-MJHT');

    const lookupBtn = screen.getByTestId<HTMLButtonElement>('lookup-button');
    expect(lookupBtn.disabled).toBe(false);
    fireEvent.click(lookupBtn);

    await waitFor(() => {
      expect(screen.getByTestId('consent-section')).not.toBeNull();
    });

    expect(screen.getByTestId('client-name').textContent).toContain('Antigravity CLI');
    expect(screen.getByTestId('verified-code').textContent).toContain('WDJB-MJHT');
    expect(screen.getByTestId('resource-target').textContent).toContain('/mcp/agent');

    // Narrow scopes and projects
    const scopeWrite = screen.getByTestId('scope-checkbox-agent:write');
    const scopeRead = screen.getByTestId('scope-checkbox-agent:read');
    fireEvent.click(scopeWrite); // Uncheck write
    fireEvent.click(scopeWrite); // Re-check write
    fireEvent.click(scopeWrite); // Uncheck write again

    // Uncheck read to test empty scopes disabling approve button
    fireEvent.click(scopeRead);
    const approveBtn = screen.getByTestId<HTMLButtonElement>('approve-button');
    expect(approveBtn.disabled).toBe(true);
    fireEvent.click(scopeRead); // Re-check read
    expect(approveBtn.disabled).toBe(false);

    // Toggle project
    const projBox = screen.getByTestId('project-checkbox-KANBA');
    fireEvent.click(projBox); // Uncheck KANBA
    fireEvent.click(projBox); // Check KANBA back

    fireEvent.click(approveBtn);

    await waitFor(() => {
      expect(oauthApi.submitDeviceActivation).toHaveBeenCalledWith({
        user_code: 'WDJB-MJHT',
        approved: true,
        scopes: ['agent:read'],
        allowed_projects: ['KANBA'],
      });
      expect(screen.getByTestId('completion-approved')).not.toBeNull();
    });
  });

  it('displays consonant-only helper caption and non-destructive feedback on vowel/digit entry', () => {
    render(
      <MemoryRouter initialEntries={['/activate']}>
        <DeviceActivatePage />
      </MemoryRouter>,
    );

    // Verify helper caption
    const helper = screen.getByTestId('user-code-helper');
    expect(helper.textContent).toContain('BCDFGHJKLMNPQRSTVWXZ');

    const input = screen.getByTestId<HTMLInputElement>('user-code-input');

    // Type a vowel or digit
    fireEvent.change(input, { target: { value: 'A1E' } });
    expect(screen.getByTestId('user-code-input-notice').textContent).toContain(
      'Vowels (A, E, I, O, U) and numbers are not used',
    );

    // Type valid consonants
    fireEvent.change(input, { target: { value: 'BCDF' } });
    expect(screen.queryByTestId('user-code-input-notice')).toBeNull();
    expect(input.value).toBe('BCDF');
  });

  it('auto-loads device info when pre-filled via query parameter', async () => {
    const mockInfo: oauthApi.DeviceCodeInfoResponse = {
      user_code: 'BCDF-GHJK',
      client_name: 'Claude Code',
      client_id: 'client_claude',
      resource: 'https://kanban.example.com/mcp/agent',
      surface: 'agent',
      requested_scopes: ['agent:read'],
      allowed_projects: null,
      expires_at: new Date().toISOString(),
    };

    vi.spyOn(oauthApi, 'fetchDeviceCodeInfo').mockResolvedValue(mockInfo);

    render(
      <MemoryRouter initialEntries={['/activate?user_code=bcdfghjk']}>
        <DeviceActivatePage />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('consent-section')).not.toBeNull();
      expect(screen.getByTestId('client-name').textContent).toContain('Claude Code');
    });
  });

  it('handles query param with short code or failed auto-lookup', async () => {
    // 1. Short code query param
    const { unmount } = render(
      <MemoryRouter initialEntries={['/activate?user_code=short']}>
        <DeviceActivatePage />
      </MemoryRouter>,
    );
    expect(screen.getByTestId('user-code-input')).not.toBeNull();
    unmount();

    // 2. Failed auto-lookup via query param (expired)
    vi.spyOn(oauthApi, 'fetchDeviceCodeInfo').mockRejectedValueOnce({
      code: 'EXPIRED_CODE',
    });

    const { unmount: unmount2 } = render(
      <MemoryRouter initialEntries={['/activate?user_code=bcdfghjk']}>
        <DeviceActivatePage />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('error-banner').textContent).toContain(
        'This user code has expired. Please initiate device login again.',
      );
    });
    unmount2();

    // 3. Failed auto-lookup via query param (rate limited)
    vi.spyOn(oauthApi, 'fetchDeviceCodeInfo').mockRejectedValueOnce({
      code: 'RATE_LIMIT_EXCEEDED',
    });
    const { unmount: unmount3 } = render(
      <MemoryRouter initialEntries={['/activate?user_code=bcdfghjk']}>
        <DeviceActivatePage />
      </MemoryRouter>,
    );
    await waitFor(() => {
      expect(screen.getByTestId('error-banner').textContent).toContain('Too many attempts.');
    });
    unmount3();

    // 4. Failed auto-lookup via query param (already processed)
    vi.spyOn(oauthApi, 'fetchDeviceCodeInfo').mockRejectedValueOnce({
      code: 'ALREADY_PROCESSED',
    });
    const { unmount: unmount4 } = render(
      <MemoryRouter initialEntries={['/activate?user_code=bcdfghjk']}>
        <DeviceActivatePage />
      </MemoryRouter>,
    );
    await waitFor(() => {
      expect(screen.getByTestId('error-banner').textContent).toContain('already been approved');
    });
    unmount4();

    // 5. Failed auto-lookup via query param (generic error)
    vi.spyOn(oauthApi, 'fetchDeviceCodeInfo').mockRejectedValueOnce(new Error('Unknown failure'));
    render(
      <MemoryRouter initialEntries={['/activate?user_code=bcdfghjk']}>
        <DeviceActivatePage />
      </MemoryRouter>,
    );
    await waitFor(() => {
      expect(screen.getByTestId('error-banner').textContent).toContain('Unknown failure');
    });
  });

  it('handles user denial decision', async () => {
    const mockInfo: oauthApi.DeviceCodeInfoResponse = {
      user_code: 'WDJB-MJHT',
      client_name: 'Test CLI',
      client_id: 'client_test',
      resource: 'https://kanban.example.com/mcp/agent',
      surface: 'agent',
      requested_scopes: ['agent:read'],
      allowed_projects: null,
      expires_at: new Date().toISOString(),
    };

    vi.spyOn(oauthApi, 'fetchDeviceCodeInfo').mockResolvedValue(mockInfo);
    vi.spyOn(oauthApi, 'submitDeviceActivation').mockResolvedValue({ status: 'denied' });

    render(
      <MemoryRouter initialEntries={['/activate?user_code=WDJB-MJHT']}>
        <DeviceActivatePage />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('deny-button')).not.toBeNull();
    });

    fireEvent.click(screen.getByTestId('deny-button'));

    await waitFor(() => {
      expect(oauthApi.submitDeviceActivation).toHaveBeenCalledWith({
        user_code: 'WDJB-MJHT',
        approved: false,
        scopes: undefined,
        allowed_projects: undefined,
      });
      expect(screen.getByTestId('completion-denied')).not.toBeNull();
    });
  });

  it('displays AAL2 banner and handles AAL2 step-up requirement (Test Case 2)', async () => {
    const mockAdminInfo: oauthApi.DeviceCodeInfoResponse = {
      user_code: 'WDJB-MJHT',
      client_name: 'Admin CLI',
      client_id: 'client_admin',
      resource: 'https://kanban.example.com/mcp/admin',
      surface: 'admin',
      requested_scopes: ['admin:read'],
      allowed_projects: null,
      expires_at: new Date().toISOString(),
    };

    vi.spyOn(oauthApi, 'fetchDeviceCodeInfo').mockResolvedValue(mockAdminInfo);
    vi.spyOn(oauthApi, 'submitDeviceActivation').mockRejectedValue({
      code: 'AAL2_REQUIRED',
      message: 'AAL2 required',
    });

    render(
      <MemoryRouter initialEntries={['/activate?user_code=WDJB-MJHT']}>
        <DeviceActivatePage />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('aal2-banner')).not.toBeNull();
    });

    fireEvent.click(screen.getByTestId('approve-button'));

    await waitFor(() => {
      expect(screen.getByTestId('error-banner').textContent).toContain(
        'AAL2 Passkey or TOTP verification required',
      );
    });
  });

  it('displays appropriate errors for rate limiting, expiration, and already processed codes', async () => {
    vi.spyOn(oauthApi, 'fetchDeviceCodeInfo').mockRejectedValueOnce({
      code: 'RATE_LIMIT_EXCEEDED',
    });

    render(
      <MemoryRouter initialEntries={['/activate']}>
        <DeviceActivatePage />
      </MemoryRouter>,
    );

    const input = screen.getByTestId('user-code-input');
    fireEvent.change(input, { target: { value: 'WDJBMJHT' } });
    fireEvent.click(screen.getByTestId('lookup-button'));

    await waitFor(() => {
      expect(screen.getByTestId('error-banner').textContent).toContain(
        'Too many attempts. Please wait 5 minutes before trying again.',
      );
    });

    // Test expired code
    vi.spyOn(oauthApi, 'fetchDeviceCodeInfo').mockRejectedValueOnce({
      code: 'EXPIRED_CODE',
    });
    fireEvent.click(screen.getByTestId('lookup-button'));
    await waitFor(() => {
      expect(screen.getByTestId('error-banner').textContent).toContain(
        'This user code has expired.',
      );
    });

    // Test already processed code
    vi.spyOn(oauthApi, 'fetchDeviceCodeInfo').mockRejectedValueOnce({
      code: 'ALREADY_PROCESSED',
    });
    fireEvent.click(screen.getByTestId('lookup-button'));
    await waitFor(() => {
      expect(screen.getByTestId('error-banner').textContent).toContain(
        'This device code has already been approved or denied.',
      );
    });

    // Test generic fallback error
    vi.spyOn(oauthApi, 'fetchDeviceCodeInfo').mockRejectedValueOnce(new Error('Network offline'));
    fireEvent.click(screen.getByTestId('lookup-button'));
    await waitFor(() => {
      expect(screen.getByTestId('error-banner').textContent).toContain('Network offline');
    });

    // Test fallback message when errObj.message is undefined
    vi.spyOn(oauthApi, 'fetchDeviceCodeInfo').mockRejectedValueOnce({});
    fireEvent.click(screen.getByTestId('lookup-button'));
    await waitFor(() => {
      expect(screen.getByTestId('error-banner').textContent).toContain('Invalid code or code not found.');
    });
  });

  it('handles generic activation error and button disabled state for short codes', async () => {
    const mockInfo: oauthApi.DeviceCodeInfoResponse = {
      user_code: 'WDJB-MJHT',
      client_name: 'Failing CLI',
      client_id: 'client_fail',
      resource: 'https://kanban.example.com/mcp/agent',
      surface: 'agent',
      requested_scopes: ['agent:read'],
      allowed_projects: ['KANBA'],
      expires_at: new Date().toISOString(),
    };

    vi.spyOn(oauthApi, 'fetchDeviceCodeInfo').mockResolvedValue(mockInfo);
    vi.spyOn(oauthApi, 'submitDeviceActivation').mockRejectedValueOnce({});

    render(
      <MemoryRouter initialEntries={['/activate?user_code=WDJB-MJHT']}>
        <DeviceActivatePage />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('approve-button')).not.toBeNull();
    });

    fireEvent.click(screen.getByTestId('approve-button'));

    await waitFor(() => {
      expect(screen.getByTestId('error-banner').textContent).toContain(
        'An error occurred while processing approval.',
      );
    });
  });

  it('does not set state if unmounted during query param auto-lookup', () => {
    let resolvePromise!: (val: oauthApi.DeviceCodeInfoResponse) => void;
    let rejectPromise!: (err: unknown) => void;

    // 1. Resolve after unmount
    vi.spyOn(oauthApi, 'fetchDeviceCodeInfo').mockReturnValueOnce(
      new Promise((resolve) => {
        resolvePromise = resolve;
      }),
    );

    const { unmount: unmount1 } = render(
      <MemoryRouter initialEntries={['/activate?user_code=bcdfghjk']}>
        <DeviceActivatePage />
      </MemoryRouter>,
    );

    unmount1();
    resolvePromise({
      user_code: 'BCDF-GHJK',
      client_name: 'Unmounted',
      client_id: 'client_unmounted',
      resource: 'https://kanban.example.com/mcp/agent',
      surface: 'agent',
      requested_scopes: ['agent:read'],
      allowed_projects: null,
      expires_at: new Date().toISOString(),
    });

    // 2. Reject after unmount
    vi.spyOn(oauthApi, 'fetchDeviceCodeInfo').mockReturnValueOnce(
      new Promise((_resolve, reject) => {
        rejectPromise = reject;
      }),
    );

    const { unmount: unmount2 } = render(
      <MemoryRouter initialEntries={['/activate?user_code=bcdfghjk']}>
        <DeviceActivatePage />
      </MemoryRouter>,
    );

    unmount2();
    rejectPromise(new Error('Rejected after unmount'));
  });

  it('renders hostile client names strictly as escaped text nodes (Anti-XSS)', async () => {
    const hostileName = '<img src=x onerror=alert(1)> Hostile App';
    const mockInfo: oauthApi.DeviceCodeInfoResponse = {
      user_code: 'WDJB-MJHT',
      client_name: hostileName,
      client_id: 'client_xss',
      resource: 'https://kanban.example.com/mcp/agent',
      surface: 'agent',
      requested_scopes: ['agent:read'],
      allowed_projects: null,
      expires_at: new Date().toISOString(),
    };

    vi.spyOn(oauthApi, 'fetchDeviceCodeInfo').mockResolvedValue(mockInfo);

    render(
      <MemoryRouter initialEntries={['/activate?user_code=WDJB-MJHT']}>
        <DeviceActivatePage />
      </MemoryRouter>,
    );

    await waitFor(() => {
      const clientNameEl = screen.getByTestId('client-name');
      expect(clientNameEl.textContent).toBe(hostileName);
      expect(clientNameEl.querySelector('img')).toBeNull();
    });
  });
});
