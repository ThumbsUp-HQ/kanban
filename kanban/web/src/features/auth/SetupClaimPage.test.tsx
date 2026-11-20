import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import React from 'react';
import { SetupClaimPage } from './SetupClaimPage';
import * as authApi from './authApi';
import type { EnrollmentSuccessResponse } from './authApi';

describe('SetupClaimPage (KB-P3-35)', () => {
  const validToken43 = 'kb_setup_' + 'A'.repeat(43);
  const shortToken42 = 'kb_setup_' + 'A'.repeat(42);
  const longToken44 = 'kb_setup_' + 'A'.repeat(44);

  beforeEach(() => {
    vi.restoreAllMocks();
    Object.defineProperty(window, 'isSecureContext', {
      value: true,
      configurable: true,
      writable: true,
    });
  });

  it('boundary: setup token with 42 or 44 chars is rejected, 43 accepted (Mandatory Test Case 6)', () => {
    // 1. 42 chars -> rejected with invalid link message, zero form
    const { unmount: unmount42 } = render(<SetupClaimPage initialToken={shortToken42} />);
    expect(
      screen.getByText('This setup link is invalid or has already been used.'),
    ).toBeDefined();
    expect(screen.queryByLabelText(/Server Administrator Username/i)).toBeNull();
    unmount42();

    // 2. 44 chars -> rejected
    const { unmount: unmount44 } = render(<SetupClaimPage initialToken={longToken44} />);
    expect(
      screen.getByText('This setup link is invalid or has already been used.'),
    ).toBeDefined();
    expect(screen.queryByLabelText(/Server Administrator Username/i)).toBeNull();
    unmount44();

    // 3. 43 chars -> accepted and renders form
    render(<SetupClaimPage initialToken={validToken43} />);
    expect(screen.getByLabelText(/Server Administrator Username/i)).toBeDefined();
    expect(screen.getByText('Step 1 of 3')).toBeDefined();
  });

  it('volatile secret: history.replaceState called with /setup and token cleared after claim (Mandatory Test Case 4)', async () => {
    const replaceStateSpy = vi.spyOn(window.history, 'replaceState');

    // Simulate arriving at /setup?token=kb_setup_...
    Object.defineProperty(window, 'location', {
      writable: true,
      value: { search: `?token=${validToken43}`, pathname: '/setup' },
    });

    const submitClaimSpy = vi.spyOn(authApi, 'submitSetupClaim').mockResolvedValue({
      status: 'enrollment_required',
      enrollment_id: 'enr-12345',
    });

    render(<SetupClaimPage />);

    // history.replaceState must have been called immediately with '/setup'
    expect(replaceStateSpy).toHaveBeenCalledWith(null, '', '/setup');

    // Submit Step 1 form
    const pwdInput = screen.getByLabelText(/^Master Password/i);
    const confirmPwdInput = screen.getByLabelText(/^Confirm Password/i);

    fireEvent.change(pwdInput, { target: { value: 'MasterPassword14CharsLong!' } });
    fireEvent.change(confirmPwdInput, { target: { value: 'MasterPassword14CharsLong!' } });

    const submitBtn = screen.getByRole('button', { name: /Claim Instance & Continue/i });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(submitClaimSpy).toHaveBeenCalledWith(
        expect.objectContaining({
          token: validToken43,
          username: 'admin',
          display_name: 'Server Administrator',
          password: 'MasterPassword14CharsLong!',
        }),
      );
      // Advances to Step 2
      expect(screen.getByText('Step 2 of 3')).toBeDefined();
    });
  });

  it('walks through Step 2 TOTP enrollment and Step 3 recovery codes gate', async () => {
    vi.spyOn(authApi, 'submitSetupClaim').mockResolvedValue({
      status: 'enrollment_required',
      enrollment_id: 'enr-999',
    });

    const enrollTotpSpy = vi.spyOn(authApi, 'enrollTotp').mockResolvedValue({
      secret_base32: 'JBSWY3DPEHPK3PXP',
      otpauth_uri: 'otpauth://totp/kanban:admin?secret=JBSWY3DPEHPK3PXP',
    });

    const mockCodes = [
      'code-01',
      'code-02',
      'code-03',
      'code-04',
      'code-05',
      'code-06',
      'code-07',
      'code-08',
      'code-09',
      'code-10',
    ];

    const verifyTotpEnrollSpy = vi.spyOn(authApi, 'verifyTotpEnrollment').mockResolvedValue({
      status: 'enrolled',
      recovery_codes: mockCodes,
    });

    const onNavigate = vi.fn();
    render(<SetupClaimPage initialToken={validToken43} onNavigate={onNavigate} />);

    // Step 1: Submit claim
    fireEvent.change(screen.getByTestId('setup-workspace-slug'), {
      target: { value: 'custom-workspace' },
    });
    fireEvent.change(screen.getByTestId('setup-project-name'), {
      target: { value: 'Custom Project' },
    });
    fireEvent.change(screen.getByTestId('setup-project-key'), {
      target: { value: 'CUSTOM' },
    });
    fireEvent.change(screen.getByLabelText(/^Master Password/i), {
      target: { value: 'ValidMasterPassword123!' },
    });
    fireEvent.change(screen.getByLabelText(/^Confirm Password/i), {
      target: { value: 'ValidMasterPassword123!' },
    });
    fireEvent.click(screen.getByRole('button', { name: /Claim Instance & Continue/i }));

    await waitFor(() => {
      expect(screen.getByText('Step 2 of 3')).toBeDefined();
    });

    // Step 2: Switch to Authenticator App tab
    const totpTab = screen.getByRole('tab', { name: /Authenticator App/i });
    fireEvent.click(totpTab);

    await waitFor(() => {
      expect(enrollTotpSpy).toHaveBeenCalledWith({ enrollment_id: 'enr-999' });
      expect(screen.getByText('JBSW Y3DP EHPK 3PXP')).toBeDefined();
    });

    fireEvent.click(screen.getByTestId('copy-secret-btn'));
    fireEvent.click(screen.getByRole('button', { name: /Copy setup key/i }));

    // Enter 6-digit TOTP verify code
    const verifyInput = screen.getByLabelText(/Verify 6-digit Code from Authenticator/i);
    fireEvent.change(verifyInput, { target: { value: '654321' } });

    fireEvent.click(screen.getByRole('button', { name: /Verify & Continue/i }));

    await waitFor(() => {
      expect(verifyTotpEnrollSpy).toHaveBeenCalledWith({
        enrollment_id: 'enr-999',
        code: '654321',
      });
      // Step 3 reached
      expect(screen.getByText('Step 3 of 3')).toBeDefined();
      expect(screen.getByText('Emergency Recovery Codes')).toBeDefined();
    });

    // Step 3: Verify 10 recovery codes rendered
    for (const code of mockCodes) {
      expect(screen.getByText(code)).toBeDefined();
    }

    // "Continue to workspace" button disabled until checkbox is checked
    const continueBtn = screen.getByRole('button', { name: /Continue to workspace/i });
    expect(continueBtn.hasAttribute('disabled')).toBe(true);

    const checkbox = screen.getByRole('checkbox', {
      name: /I stored these recovery codes somewhere safe/i,
    });
    fireEvent.click(checkbox);
    expect(continueBtn.hasAttribute('disabled')).toBe(false);

    // Click Continue
    fireEvent.click(continueBtn);
    expect(onNavigate).toHaveBeenCalledWith('/');
  });

  it('validates password mismatch and length errors in Step 1', () => {
    render(<SetupClaimPage initialToken={validToken43} />);

    // Password too short (<14)
    fireEvent.change(screen.getByLabelText(/^Master Password/i), {
      target: { value: 'short' },
    });
    fireEvent.change(screen.getByLabelText(/^Confirm Password/i), {
      target: { value: 'short' },
    });
    fireEvent.click(screen.getByRole('button', { name: /Claim Instance & Continue/i }));

    expect(
      screen.getByText('Password must be at least 14 characters long.'),
    ).toBeDefined();

    // Password mismatch
    fireEvent.change(screen.getByLabelText(/^Master Password/i), {
      target: { value: 'LongEnoughPassword12345!' },
    });
    fireEvent.change(screen.getByLabelText(/^Confirm Password/i), {
      target: { value: 'DifferentPassword12345!' },
    });
    fireEvent.click(screen.getByRole('button', { name: /Claim Instance & Continue/i }));

    expect(screen.getByText('Passwords do not match.')).toBeDefined();
  });

  it('validates username and display name boundaries in Step 1', () => {
    render(<SetupClaimPage initialToken={validToken43} />);

    // Invalid username (capital letter or too short)
    fireEvent.change(screen.getByLabelText(/Server Administrator Username/i), {
      target: { value: 'Admin' },
    });
    fireEvent.change(screen.getByLabelText(/^Master Password/i), {
      target: { value: 'ValidPassword14Chars!' },
    });
    fireEvent.change(screen.getByLabelText(/^Confirm Password/i), {
      target: { value: 'ValidPassword14Chars!' },
    });

    fireEvent.click(screen.getByRole('button', { name: /Claim Instance & Continue/i }));
    expect(
      screen.getByText(/Username must be 3-64 characters/i),
    ).toBeDefined();

    // Invalid display name (empty)
    fireEvent.change(screen.getByLabelText(/Server Administrator Username/i), {
      target: { value: 'admin' },
    });
    fireEvent.change(screen.getByLabelText(/Display Name/i), {
      target: { value: ' ' },
    });

    fireEvent.click(screen.getByRole('button', { name: /Claim Instance & Continue/i }));
    expect(
      screen.getByText(/Display name must be between 1 and 120 characters/i),
    ).toBeDefined();
  });

  it('registers passkey in Step 2, and tests Copy All and Download .txt in Step 3', async () => {
    (window as unknown as { PublicKeyCredential?: unknown }).PublicKeyCredential = vi.fn();

    vi.spyOn(authApi, 'submitSetupClaim').mockResolvedValue({
      status: 'enrollment_required',
      enrollment_id: 'enr-passkey',
    });

    vi.spyOn(authApi, 'getWebauthnRegistrationOptions').mockResolvedValue({
      options: {
        rp: { name: 'Kanban' },
        user: { id: 'dXNlcg', name: 'admin', displayName: 'Admin' },
        challenge: 'Y2hhbGxlbmdl',
        pubKeyCredParams: [{ alg: -7, type: 'public-key' }],
        excludeCredentials: [{ id: 'ZXhjbHVkZTE', type: 'public-key' }],
      },
    });

    const mockRegCred = {
      id: 'reg-cred-1',
      rawId: new Uint8Array([1, 2]).buffer,
      type: 'public-key',
      response: {
        clientDataJSON: new Uint8Array([3, 4]).buffer,
        attestationObject: new Uint8Array([5, 6]).buffer,
      },
    } as unknown as PublicKeyCredential;

    Object.defineProperty(navigator, 'credentials', {
      writable: true,
      value: {
        create: vi.fn().mockResolvedValue(mockRegCred),
        get: vi.fn().mockResolvedValue(null),
      },
    });

    const mockCodes = ['code-1', 'code-2', 'code-3'];
    vi.spyOn(authApi, 'verifyWebauthnRegistration').mockResolvedValue({
      status: 'enrolled',
      recovery_codes: mockCodes,
    });

    const writeTextSpy = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'clipboard', {
      writable: true,
      value: { writeText: writeTextSpy },
    });

    render(<SetupClaimPage initialToken={validToken43} />);

    // Step 1: Submit claim
    fireEvent.change(screen.getByLabelText(/^Master Password/i), {
      target: { value: 'MasterPassword14Long!' },
    });
    fireEvent.change(screen.getByLabelText(/^Confirm Password/i), {
      target: { value: 'MasterPassword14Long!' },
    });
    fireEvent.click(screen.getByRole('button', { name: /Claim Instance & Continue/i }));

    await waitFor(() => {
      expect(screen.getByText('Step 2 of 3')).toBeDefined();
    });

    // Step 2: Register passkey
    const regBtn = screen.getByRole('button', { name: /Register a passkey/i });
    fireEvent.click(regBtn);

    await waitFor(() => {
      expect(screen.getByText('Step 3 of 3')).toBeDefined();
    });

    // Test Copy All
    const copyAllBtn = screen.getByRole('button', { name: /Copy all/i });
    fireEvent.click(copyAllBtn);
    expect(writeTextSpy).toHaveBeenCalledWith(mockCodes.join('\n'));
    await waitFor(() => {
      expect(screen.getByText('Copied All!')).toBeDefined();
    });

    // Test Download .txt
    const downloadBtn = screen.getByRole('button', { name: /Download \.txt/i });
    fireEvent.click(downloadBtn);

    // Continue to workspace without onNavigate -> calls window.location.assign('/')
    const assignSpy = vi.fn();
    Object.defineProperty(window, 'location', {
      writable: true,
      value: { assign: assignSpy, search: '', pathname: '/setup' },
    });

    const checkbox = screen.getByRole('checkbox', {
      name: /I stored these recovery codes somewhere safe/i,
    });
    fireEvent.click(checkbox);

    const continueBtn = screen.getByRole('button', { name: /Continue to workspace/i });
    fireEvent.click(continueBtn);

    expect(assignSpy).toHaveBeenCalledWith('/');
  });

  it('handles Passkey registration failure in Step 2', async () => {
    (window as unknown as { PublicKeyCredential?: unknown }).PublicKeyCredential = vi.fn();

    vi.spyOn(authApi, 'submitSetupClaim').mockResolvedValue({
      status: 'enrollment_required',
      enrollment_id: 'enr-passkey-fail',
    });

    vi.spyOn(authApi, 'getWebauthnRegistrationOptions').mockRejectedValueOnce(
      new Error('Failed options'),
    );

    render(<SetupClaimPage initialToken={validToken43} />);

    // Step 1: Submit claim
    fireEvent.change(screen.getByLabelText(/^Master Password/i), {
      target: { value: 'MasterPassword14Long!' },
    });
    fireEvent.change(screen.getByLabelText(/^Confirm Password/i), {
      target: { value: 'MasterPassword14Long!' },
    });
    fireEvent.click(screen.getByRole('button', { name: /Claim Instance & Continue/i }));

    await waitFor(() => {
      expect(screen.getByText('Step 2 of 3')).toBeDefined();
    });

    // Step 2: Register passkey -> fails
    const regBtn = screen.getByRole('button', { name: /Register a passkey/i });
    fireEvent.click(regBtn);

    await waitFor(() => {
      expect(
        screen.getByText('Passkey verification failed. Try again or use an authenticator code.'),
      ).toBeDefined();
    });

    // Dismiss error
    const dismissBtn = screen.getByRole('button', { name: /Dismiss error/i });
    fireEvent.click(dismissBtn);
    expect(
      screen.queryByText('Passkey verification failed. Try again or use an authenticator code.'),
    ).toBeNull();
  });

  it('handles TOTP enrollment and verification failures in Step 2', async () => {
    vi.spyOn(authApi, 'submitSetupClaim').mockResolvedValue({
      status: 'enrollment_required',
      enrollment_id: 'enr-totp-fail',
    });

    vi.spyOn(authApi, 'enrollTotp').mockResolvedValue({
      secret_base32: 'ABCDEFGH',
      otpauth_uri: 'otpauth://totp/fail',
    });

    vi.spyOn(authApi, 'verifyTotpEnrollment').mockRejectedValueOnce(
      new Error('Verification failed'),
    );

    render(<SetupClaimPage initialToken={validToken43} />);

    // Step 1
    fireEvent.change(screen.getByLabelText(/^Master Password/i), {
      target: { value: 'MasterPassword14Long!' },
    });
    fireEvent.change(screen.getByLabelText(/^Confirm Password/i), {
      target: { value: 'MasterPassword14Long!' },
    });
    fireEvent.click(screen.getByRole('button', { name: /Claim Instance & Continue/i }));

    await waitFor(() => {
      expect(screen.getByText('Step 2 of 3')).toBeDefined();
    });

    // Step 2: Click Authenticator tab
    fireEvent.click(screen.getByRole('tab', { name: /Authenticator App/i }));

    await waitFor(() => {
      expect(screen.getByText('ABCD EFGH')).toBeDefined();
    });

    // Test Copy Setup Key button
    const copyKeyBtn = screen.getByRole('button', { name: /Copy setup key/i });
    fireEvent.click(copyKeyBtn);

    // Switch back to Passkey tab
    fireEvent.click(screen.getByRole('tab', { name: /Passkey \(Recommended\)/i }));
    // Switch to Authenticator tab again
    fireEvent.click(screen.getByRole('tab', { name: /Authenticator App/i }));

    // Submit invalid length code
    const codeInput = screen.getByLabelText(/Verify 6-digit Code from Authenticator/i);
    const form = codeInput.closest('form');
    expect(form).not.toBeNull();
    fireEvent.change(codeInput, { target: { value: '123' } });
    if (form) {
      fireEvent.submit(form);
    }

    expect(screen.getByText('Please enter a 6-digit code.')).toBeDefined();

    // Submit 6-digit code that rejects
    fireEvent.change(codeInput, { target: { value: '123456' } });
    if (form) {
      fireEvent.submit(form);
    }

    await waitFor(() => {
      expect(screen.getByText('Sign-in is unavailable right now.')).toBeDefined();
    });
  });

  it('handles submitSetupClaim rejection in Step 1', async () => {
    vi.spyOn(authApi, 'submitSetupClaim').mockRejectedValueOnce(
      new Error('Claim rejected by server'),
    );

    render(<SetupClaimPage initialToken={validToken43} />);

    fireEvent.change(screen.getByLabelText(/^Master Password/i), {
      target: { value: 'MasterPassword14Long!' },
    });
    fireEvent.change(screen.getByLabelText(/^Confirm Password/i), {
      target: { value: 'MasterPassword14Long!' },
    });
    fireEvent.click(screen.getByRole('button', { name: /Claim Instance & Continue/i }));

    await waitFor(() => {
      expect(screen.getByText('Sign-in is unavailable right now.')).toBeDefined();
    });
  });

  it('handles navigator.credentials.create returning null in Step 2', async () => {
    (window as unknown as { PublicKeyCredential?: unknown }).PublicKeyCredential = vi.fn();

    vi.spyOn(authApi, 'submitSetupClaim').mockResolvedValue({
      status: 'enrollment_required',
      enrollment_id: 'enr-passkey-null',
    });

    vi.spyOn(authApi, 'getWebauthnRegistrationOptions').mockResolvedValue({
      options: {
        rp: { name: 'Kanban' },
        user: { id: 'dXNlcg', name: 'admin', displayName: 'Admin' },
        challenge: 'Y2hhbGxlbmdl',
        pubKeyCredParams: [{ alg: -7, type: 'public-key' }],
      },
    });

    Object.defineProperty(navigator, 'credentials', {
      writable: true,
      value: {
        create: vi.fn().mockResolvedValue(null),
        get: vi.fn().mockResolvedValue(null),
      },
    });

    render(<SetupClaimPage initialToken={validToken43} />);

    fireEvent.change(screen.getByLabelText(/^Master Password/i), {
      target: { value: 'MasterPassword14Long!' },
    });
    fireEvent.change(screen.getByLabelText(/^Confirm Password/i), {
      target: { value: 'MasterPassword14Long!' },
    });
    fireEvent.click(screen.getByRole('button', { name: /Claim Instance & Continue/i }));

    await waitFor(() => {
      expect(screen.getByText('Step 2 of 3')).toBeDefined();
    });

    fireEvent.click(screen.getByRole('button', { name: /Register a passkey/i }));

    await waitFor(() => {
      expect(
        screen.getByText('Passkey verification failed. Try again or use an authenticator code.'),
      ).toBeDefined();
    });
  });

  it('handles enrollTotp rejection in Step 2', async () => {
    vi.spyOn(authApi, 'submitSetupClaim').mockResolvedValue({
      status: 'enrollment_required',
      enrollment_id: 'enr-totp-reject',
    });

    vi.spyOn(authApi, 'enrollTotp').mockRejectedValueOnce(
      new Error('Failed to generate TOTP secret'),
    );

    render(<SetupClaimPage initialToken={validToken43} />);

    fireEvent.change(screen.getByLabelText(/^Master Password/i), {
      target: { value: 'MasterPassword14Long!' },
    });
    fireEvent.change(screen.getByLabelText(/^Confirm Password/i), {
      target: { value: 'MasterPassword14Long!' },
    });
    fireEvent.click(screen.getByRole('button', { name: /Claim Instance & Continue/i }));

    await waitFor(() => {
      expect(screen.getByText('Step 2 of 3')).toBeDefined();
    });

    fireEvent.click(screen.getByRole('tab', { name: /Authenticator App/i }));

    await waitFor(() => {
      expect(screen.getByText('Sign-in is unavailable right now.')).toBeDefined();
    });
  });

  it('renders passkey unsupported empty state in Step 2 when WebAuthn is unavailable', async () => {
    (window as unknown as { PublicKeyCredential?: unknown }).PublicKeyCredential = undefined;

    vi.spyOn(authApi, 'submitSetupClaim').mockResolvedValue({
      status: 'enrollment_required',
      enrollment_id: 'enr-no-pkc',
    });

    render(<SetupClaimPage initialToken={validToken43} />);

    fireEvent.change(screen.getByLabelText(/^Master Password/i), {
      target: { value: 'MasterPassword14Long!' },
    });
    fireEvent.change(screen.getByLabelText(/^Confirm Password/i), {
      target: { value: 'MasterPassword14Long!' },
    });
    fireEvent.click(screen.getByRole('button', { name: /Claim Instance & Continue/i }));

    await waitFor(() => {
      expect(screen.getByText('Step 2 of 3')).toBeDefined();
    });

    // Clicking Passkey tab displays unsupported message when WebAuthn is unavailable
    fireEvent.click(screen.getByRole('tab', { name: /Passkey/i }));
    expect(
      screen.getByText(/This browser does not support passkeys/i),
    ).toBeDefined();
  });

  it('prevents concurrent TOTP enrollment verification in Step 2', async () => {
    vi.spyOn(authApi, 'submitSetupClaim').mockResolvedValue({
      status: 'enrollment_required',
      enrollment_id: 'enr-totp-concurrent',
    });

    vi.spyOn(authApi, 'enrollTotp').mockResolvedValue({
      secret_base32: 'ABCDEFGH',
      otpauth_uri: 'otpauth://totp/concurrent',
    });

    let resolveVerify: ((val: EnrollmentSuccessResponse) => void) | undefined;
    const verifySpy = vi.spyOn(authApi, 'verifyTotpEnrollment').mockReturnValue(
      new Promise<EnrollmentSuccessResponse>((resolve) => {
        resolveVerify = resolve;
      }),
    );

    render(<SetupClaimPage initialToken={validToken43} />);

    fireEvent.change(screen.getByLabelText(/^Master Password/i), {
      target: { value: 'MasterPassword14Long!' },
    });
    fireEvent.change(screen.getByLabelText(/^Confirm Password/i), {
      target: { value: 'MasterPassword14Long!' },
    });
    fireEvent.click(screen.getByRole('button', { name: /Claim Instance & Continue/i }));

    await waitFor(() => {
      expect(screen.getByText('Step 2 of 3')).toBeDefined();
    });

    fireEvent.click(screen.getByRole('tab', { name: /Authenticator App/i }));

    await waitFor(() => {
      expect(screen.getByLabelText(/Verify 6-digit Code/i)).toBeDefined();
    });

    const codeInput = screen.getByLabelText(/Verify 6-digit Code/i);
    fireEvent.change(codeInput, { target: { value: '123456' } });
    const form = codeInput.closest('form');
    expect(form).not.toBeNull();

    if (form) {
      // First submit fires
      fireEvent.submit(form);
      // Second submit while isSubmitting is true should be ignored
      fireEvent.submit(form);
    }

    expect(verifySpy).toHaveBeenCalledTimes(1);
    resolveVerify?.({ status: 'enrolled', recovery_codes: ['code-a', 'code-b'] });
  });

  it('forwards optional #setup-email when populated in Step 1', async () => {
    const submitClaimSpy = vi.spyOn(authApi, 'submitSetupClaim').mockResolvedValue({
      status: 'enrollment_required',
      enrollment_id: 'enr-email-1',
    });

    render(<SetupClaimPage initialToken={validToken43} />);

    fireEvent.change(screen.getByLabelText(/Administrator Email/i), {
      target: { value: 'admin@kanban.local' },
    });
    fireEvent.change(screen.getByLabelText(/^Master Password/i), {
      target: { value: 'MasterPassword14Long!' },
    });
    fireEvent.change(screen.getByLabelText(/^Confirm Password/i), {
      target: { value: 'MasterPassword14Long!' },
    });
    fireEvent.click(screen.getByRole('button', { name: /Claim Instance & Continue/i }));

    await waitFor(() => {
      expect(submitClaimSpy).toHaveBeenCalledWith(
        expect.objectContaining({
          token: validToken43,
          username: 'admin',
          display_name: 'Server Administrator',
          password: 'MasterPassword14Long!',
          email: 'admin@kanban.local',
        }),
      );
      expect(screen.getByText('Step 2 of 3')).toBeDefined();
    });
  });

  it('validates Step 1 fields (username, displayName, password mismatch, short password, invalid projectKey)', () => {
    render(<SetupClaimPage initialToken={validToken43} />);
    const submitForm = (el: Element) => {
      const form = el.closest('form');
      if (form) fireEvent.submit(form);
    };

    // Short password
    fireEvent.change(screen.getByLabelText(/^Master Password/i), { target: { value: 'short' } });
    fireEvent.change(screen.getByLabelText(/^Confirm Password/i), { target: { value: 'short' } });
    submitForm(screen.getByRole('button', { name: /Claim Instance & Continue/i }));
    expect(screen.getByText(/Password must be at least 14 characters long/i)).toBeDefined();

    // Password mismatch
    fireEvent.change(screen.getByLabelText(/^Master Password/i), { target: { value: 'ValidPassword14Long!' } });
    fireEvent.change(screen.getByLabelText(/^Confirm Password/i), { target: { value: 'MismatchPassword14!' } });
    submitForm(screen.getByRole('button', { name: /Claim Instance & Continue/i }));
    expect(screen.getByText(/Passwords do not match/i)).toBeDefined();

    // Invalid username
    fireEvent.change(screen.getByLabelText(/^Confirm Password/i), { target: { value: 'ValidPassword14Long!' } });
    fireEvent.change(screen.getByLabelText(/Server Administrator Username/i), { target: { value: '!' } });
    submitForm(screen.getByRole('button', { name: /Claim Instance & Continue/i }));
    expect(screen.getByText(/Username must be 3-64 characters/i)).toBeDefined();

    // Reset username, invalid display name
    fireEvent.change(screen.getByLabelText(/Server Administrator Username/i), { target: { value: 'admin' } });
    fireEvent.change(screen.getByLabelText(/Display Name/i), { target: { value: ' ' } });
    submitForm(screen.getByRole('button', { name: /Claim Instance & Continue/i }));
    expect(screen.getByText(/Display name must be between 1 and 120 characters/i)).toBeDefined();

    // Reset display name, invalid projectKey
    fireEvent.change(screen.getByLabelText(/Display Name/i), { target: { value: 'Admin' } });
    fireEvent.change(screen.getByTestId('setup-project-key'), { target: { value: '1INVALID' } });
    submitForm(screen.getByRole('button', { name: /Claim Instance & Continue/i }));
    expect(screen.getByText(/Project key must be 2-10 uppercase alphanumeric/i)).toBeDefined();

    // Workspace slug auto-slugify and manual change
    fireEvent.change(screen.getByTestId('setup-workspace-name'), { target: { value: 'My Awesome Team' } });
    const slugInput = screen.getByTestId<HTMLInputElement>('setup-workspace-slug');
    expect(slugInput.value).toBe('my-awesome-team');
    fireEvent.change(slugInput, { target: { value: 'custom-slug' } });
    expect(slugInput.value).toBe('custom-slug');
  });

  it('covers Step 2 copy secret button and Step 3 copy/download/finish flow', async () => {
    vi.spyOn(authApi, 'submitSetupClaim').mockResolvedValue({
      status: 'enrollment_required',
      enrollment_id: 'enr-full-step-3',
    });

    vi.spyOn(authApi, 'enrollTotp').mockResolvedValue({
      secret_base32: 'JBSWY3DPEHPK3PXP',
      otpauth_uri: 'otpauth://totp/kanban:admin?secret=JBSWY3DPEHPK3PXP',
    });

    vi.spyOn(authApi, 'verifyTotpEnrollment').mockResolvedValue({
      status: 'enrolled',
      recovery_codes: ['rec-01', 'rec-02'],
    });

    // Mock clipboard writeText
    const writeTextSpy = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'clipboard', {
      writable: true,
      value: { writeText: writeTextSpy },
    });

    const onNavigateMock = vi.fn();

    render(<SetupClaimPage initialToken={validToken43} onNavigate={onNavigateMock} />);

    const submitForm = (el: Element) => {
      const form = el.closest('form');
      if (form) fireEvent.submit(form);
    };

    fireEvent.change(screen.getByLabelText(/^Master Password/i), {
      target: { value: 'ValidPassword14Long!' },
    });
    fireEvent.change(screen.getByLabelText(/^Confirm Password/i), {
      target: { value: 'ValidPassword14Long!' },
    });
    submitForm(screen.getByRole('button', { name: /Claim Instance & Continue/i }));

    await waitFor(() => {
      expect(screen.getByText('Step 2 of 3')).toBeDefined();
    });

    fireEvent.click(screen.getByRole('tab', { name: /Authenticator App/i }));

    await waitFor(() => {
      expect(screen.getByTestId('copy-secret-btn')).toBeDefined();
    });

    fireEvent.click(screen.getByTestId('copy-secret-btn'));
    fireEvent.click(screen.getByRole('button', { name: /Copy setup key/i }));

    // Verify TOTP to go to Step 3
    fireEvent.change(screen.getByLabelText(/Verify 6-digit Code/i), {
      target: { value: '123456' },
    });
    submitForm(screen.getByRole('button', { name: /Verify & Continue/i }));

    await waitFor(() => {
      expect(screen.getByText('Step 3 of 3')).toBeDefined();
    });

    // Step 3 actions
    fireEvent.click(screen.getByRole('button', { name: /Copy all/i }));
    fireEvent.click(screen.getByRole('button', { name: /Download \.txt/i }));

    // Checkbox gating finish button
    const finishBtn = screen.getByRole('button', { name: /Continue to workspace/i });
    expect(finishBtn.getAttribute('disabled')).not.toBeNull();

    const checkbox = screen.getByRole('checkbox');
    fireEvent.click(checkbox);
    expect(finishBtn.getAttribute('disabled')).toBeNull();

    fireEvent.click(finishBtn);
    expect(onNavigateMock).toHaveBeenCalledWith('/');
  });

  it('covers platform authenticator unavailable and isPlainHttp branches', async () => {
    // 1. isUserVerifyingPlatformAuthenticatorAvailable returns false
    (window as unknown as { PublicKeyCredential: { isUserVerifyingPlatformAuthenticatorAvailable: () => Promise<boolean> } }).PublicKeyCredential = {
      isUserVerifyingPlatformAuthenticatorAvailable: vi.fn().mockResolvedValue(false),
    };

    const { unmount } = render(<SetupClaimPage initialToken={validToken43} />);
    await waitFor(() => {
      expect(screen.getByText('Step 1 of 3')).toBeDefined();
    });
    unmount();

    // 2. isPlainHttp branch (http: and non-localhost)
    const originalLocation = window.location;
    Object.defineProperty(window, 'location', {
      writable: true,
      value: {
        protocol: 'http:',
        hostname: 'kanban.internal.example',
        search: '',
        pathname: '/setup',
      },
    });

    render(<SetupClaimPage initialToken={validToken43} />);
    await waitFor(() => {
      expect(screen.getByText('Step 1 of 3')).toBeDefined();
    });

    Object.defineProperty(window, 'location', {
      writable: true,
      value: originalLocation,
    });
  });

  it('boots directly into Step 2 when session is authenticated with mfa_pending', async () => {
    vi.spyOn(authApi, 'fetchSessionInfo').mockResolvedValueOnce({
      authenticated: true,
      mfa_pending: true,
      session_id: 'sess-enr-direct',
    });

    render(<SetupClaimPage />);

    await waitFor(() => {
      expect(screen.getByText('Step 2 of 3')).toBeDefined();
    });
  });

  it('covers validation edge branches, slugify fallback, and email inclusion', async () => {
    vi.spyOn(authApi, 'fetchSessionInfo').mockResolvedValueOnce({
      authenticated: true,
      mfa_pending: true,
      session_id: null,
    });

    const { unmount } = render(<SetupClaimPage initialToken={validToken43} />);

    await waitFor(() => {
      expect(screen.getByText('Step 2 of 3')).toBeDefined();
    });
    unmount();

    // Step 1 validation branches
    render(<SetupClaimPage initialToken={validToken43} />);

    // 1. Empty display name
    const displayInput = screen.getByLabelText(/Display Name/i);
    fireEvent.change(displayInput, { target: { value: '' } });
    fireEvent.submit(screen.getByRole('button', { name: /Claim Instance/i }));
    expect(screen.getByText('Display name must be between 1 and 120 characters.')).toBeDefined();

    // Fix display name, invalidate project key
    fireEvent.change(displayInput, { target: { value: 'Admin' } });
    const projectKeyInput = screen.getByLabelText(/Initial Project Key/i);
    fireEvent.change(projectKeyInput, { target: { value: '1INVALID' } });
    const passInput = document.getElementById('setup-password') as HTMLInputElement;
    const confirmInput = document.getElementById('setup-confirm-password') as HTMLInputElement;
    fireEvent.change(passInput, { target: { value: 'ValidPassword123!' } });
    fireEvent.change(confirmInput, { target: { value: 'ValidPassword123!' } });
    fireEvent.submit(screen.getByRole('button', { name: /Claim Instance/i }));
    expect(
      screen.getByText(/Project key must be 2-10 uppercase alphanumeric characters/i),
    ).toBeDefined();

    // 2. Slugify fallback when name is symbols
    const wsNameInput = screen.getByLabelText(/Workspace Name/i);
    fireEvent.change(wsNameInput, { target: { value: '$$$###' } });
    const slugInput = screen.getByLabelText<HTMLInputElement>(/Workspace Slug/i);
    expect(slugInput.value).toBe('kanban-workspace');

    // Touch slug then change name (slugTouched branch)
    fireEvent.change(slugInput, { target: { value: 'custom-slug' } });
    fireEvent.change(wsNameInput, { target: { value: 'Another Workspace' } });
    expect(slugInput.value).toBe('custom-slug');

    // 3. Valid submit with email
    fireEvent.change(projectKeyInput, { target: { value: 'KANBA' } });
    const emailInput = document.getElementById('setup-email') as HTMLInputElement;
    fireEvent.change(emailInput, { target: { value: 'admin@kanban.local' } });

    const submitClaimSpy = vi.spyOn(authApi, 'submitSetupClaim').mockResolvedValueOnce({
      enrollment_id: 'enr-email-1',
      status: 'enrollment_required',
    });

    fireEvent.submit(screen.getByRole('button', { name: /Claim Instance/i }));
    await waitFor(() => {
      expect(submitClaimSpy).toHaveBeenCalledWith(
        expect.objectContaining({ email: 'admin@kanban.local' }),
      );
    });
  });

  it('renders Step 2 plain HTTP warning when accessing over http', async () => {
    vi.spyOn(authApi, 'fetchSessionInfo').mockResolvedValueOnce({
      authenticated: true,
      mfa_pending: true,
      session_id: 'sess-enr-http',
    });

    const originalLocation = window.location;
    Object.defineProperty(window, 'location', {
      writable: true,
      value: {
        protocol: 'http:',
        hostname: 'remote.corp.example',
        search: '',
        pathname: '/setup',
      },
    });

    render(<SetupClaimPage initialToken={validToken43} />);
    const passkeyTab = await screen.findByRole('tab', { name: /Passkey/i });
    fireEvent.click(passkeyTab);

    await waitFor(() => {
      expect(screen.getByText(/Passkeys require HTTPS/i)).toBeDefined();
    });

    Object.defineProperty(window, 'location', {
      writable: true,
      value: originalLocation,
    });
  });

  it('handles totp enrollment failure in Step 2', async () => {
    vi.spyOn(authApi, 'fetchSessionInfo').mockResolvedValueOnce({
      authenticated: true,
      mfa_pending: true,
      session_id: 'sess-enr-direct',
    });
    vi.spyOn(authApi, 'enrollTotp').mockRejectedValueOnce(new Error('TOTP service unavailable'));

    render(<SetupClaimPage />);

    await waitFor(() => {
      expect(screen.getByText('Step 2 of 3')).toBeDefined();
    });

    const totpTab = screen.getByRole('tab', { name: /Authenticator App/i });
    fireEvent.click(totpTab);

    await waitFor(() => {
      expect(screen.getByText('Sign-in is unavailable right now.')).toBeDefined();
    });
  });
});
