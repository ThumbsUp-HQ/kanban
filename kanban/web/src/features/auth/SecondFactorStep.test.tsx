import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import React from 'react';
import { SecondFactorStep } from './SecondFactorStep';
import * as authApi from './authApi';
import type { PublicKeyCredentialRequestOptionsJSON } from './authApi';
import { ApiProblem } from '../../api/problem';

describe('SecondFactorStep (KB-P3-35)', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('renders method tabs in provided order (Action 7)', () => {
    const onSuccess = vi.fn();
    const onError = vi.fn();
    const onExpired = vi.fn();

    render(
      <SecondFactorStep
        challengeId="chall-test"
        methods={['totp', 'recovery']}
        onSuccess={onSuccess}
        onError={onError}
        onSessionExpired={onExpired}
      />,
    );

    const tabs = screen.getAllByRole('tab');
    expect(screen.getByTestId('second-factor-step')).toBeDefined();
    expect(tabs.length).toBe(2);
    expect(tabs[0]?.textContent).toBe('Authenticator code');
    expect(tabs[1]?.textContent).toBe('Recovery code');
  });

  it('disables Passkey tab with exact message when PublicKeyCredential is undefined (Mandatory Test Case 7)', () => {
    const originalPKC = (window as unknown as { PublicKeyCredential?: unknown }).PublicKeyCredential;
    (window as unknown as { PublicKeyCredential?: unknown }).PublicKeyCredential = undefined;

    const onSuccess = vi.fn();
    const onError = vi.fn();
    const onExpired = vi.fn();

    render(
      <SecondFactorStep
        challengeId="chall-test"
        methods={['webauthn', 'totp']}
        onSuccess={onSuccess}
        onError={onError}
        onSessionExpired={onExpired}
      />,
    );

    const passkeyTab = screen.getByRole('tab', { name: /Passkey/i });
    expect(passkeyTab.getAttribute('aria-disabled')).toBe('true');
    expect(
      screen.getByText('This browser does not support passkeys. Use an authenticator code.'),
    ).toBeDefined();

    (window as unknown as { PublicKeyCredential?: unknown }).PublicKeyCredential = originalPKC;
  });

  it('TOTP boundary: accepts 6 digits and auto-submits; 5 digits does not; normalizes spaces (Mandatory Test Case 6)', async () => {
    const verifyTotpSpy = vi.spyOn(authApi, 'verifyTotp').mockResolvedValue({
      status: 'authenticated',
    });

    const onSuccess = vi.fn();
    const onError = vi.fn();
    const onExpired = vi.fn();

    render(
      <SecondFactorStep
        challengeId="chall-totp"
        methods={['totp']}
        onSuccess={onSuccess}
        onError={onError}
        onSessionExpired={onExpired}
      />,
    );

    const totpInput = screen.getByLabelText<HTMLInputElement>(/6-digit Authenticator Code/i);

    // 1. Enter 5 digits -> does NOT auto-submit
    fireEvent.change(totpInput, { target: { value: '12345' } });
    expect(totpInput.value).toBe('12345');
    expect(verifyTotpSpy).not.toHaveBeenCalled();

    // 2. Paste "12 34 56" with spaces -> normalized to "123456" and auto-submits once
    fireEvent.change(totpInput, { target: { value: '12 34 56' } });
    expect(totpInput.value).toBe('123456');

    await waitFor(() => {
      expect(verifyTotpSpy).toHaveBeenCalledTimes(1);
      expect(verifyTotpSpy).toHaveBeenCalledWith({
        challenge_id: 'chall-totp',
        code: '123456',
      });
      expect(onSuccess).toHaveBeenCalledTimes(1);
    });
  });

  it('triggers onSessionExpired when server returns CHALLENGE_EXPIRED', async () => {
    vi.spyOn(authApi, 'verifyTotp').mockRejectedValueOnce(
      new ApiProblem(401, { code: 'CHALLENGE_EXPIRED', detail: 'Challenge expired' }),
    );

    const onSuccess = vi.fn();
    const onError = vi.fn();
    const onExpired = vi.fn();

    render(
      <SecondFactorStep
        challengeId="chall-expired"
        methods={['totp']}
        onSuccess={onSuccess}
        onError={onError}
        onSessionExpired={onExpired}
      />,
    );

    const totpInput = screen.getByLabelText(/6-digit Authenticator Code/i);
    fireEvent.change(totpInput, { target: { value: '999999' } });

    await waitFor(() => {
      expect(onExpired).toHaveBeenCalledTimes(1);
    });
  });

  it('executes Passkey assertion flow and reports success', async () => {
    (window as unknown as { PublicKeyCredential?: unknown }).PublicKeyCredential = vi.fn();

    const mockGetOptions = vi.spyOn(authApi, 'getWebauthnAssertionOptions').mockResolvedValue({
      options: {
        challenge: 'dGVzdC1jaGFsbGVuZ2U',
        rpId: 'localhost',
        userVerification: 'required',
        allowCredentials: [
          {
            id: 'dGVzdC1jcmVk',
            type: 'public-key',
            transports: ['internal'],
          },
        ],
      },
    });

    const mockVerifyAssertion = vi.spyOn(authApi, 'verifyWebauthnAssertion').mockResolvedValue({
      status: 'authenticated',
    });

    const mockCred = {
      id: 'cred-1',
      rawId: new Uint8Array([1, 2]).buffer,
      type: 'public-key',
      response: {
        clientDataJSON: new Uint8Array([3, 4]).buffer,
        authenticatorData: new Uint8Array([5, 6]).buffer,
        signature: new Uint8Array([7, 8]).buffer,
        userHandle: null,
      },
    } as unknown as PublicKeyCredential;

    Object.defineProperty(navigator, 'credentials', {
      writable: true,
      value: { get: vi.fn().mockResolvedValue(mockCred) },
    });

    const onSuccess = vi.fn();
    const onError = vi.fn();
    const onExpired = vi.fn();

    render(
      <SecondFactorStep
        challengeId="chall-passkey"
        methods={['webauthn']}
        onSuccess={onSuccess}
        onError={onError}
        onSessionExpired={onExpired}
      />,
    );

    const passkeyBtn = screen.getByRole('button', { name: /Use passkey/i });
    fireEvent.click(passkeyBtn);

    await waitFor(() => {
      expect(mockGetOptions).toHaveBeenCalledWith({ challenge_id: 'chall-passkey' });
      expect(mockVerifyAssertion).toHaveBeenCalledTimes(1);
      expect(onSuccess).toHaveBeenCalledTimes(1);
    });
  });

  it('verifies recovery code input and triggers error on invalid format', async () => {
    const onSuccess = vi.fn();
    const onError = vi.fn();
    const onExpired = vi.fn();

    render(
      <SecondFactorStep
        challengeId="chall-rec"
        methods={['recovery']}
        onSuccess={onSuccess}
        onError={onError}
        onSessionExpired={onExpired}
      />,
    );

    const recInput = screen.getByLabelText(/Single-use Recovery Code/i);
    const pattern = recInput.getAttribute('pattern');
    expect(pattern).toBeTruthy();
    const patternStr = pattern ?? '';
    // Explicit assertion: Chromium UnicodeSets (/v) compiles without throwing SyntaxError
    expect(() => new RegExp(patternStr, 'v')).not.toThrow();
    const vRegExp = new RegExp(patternStr, 'v');
    expect(vRegExp.test('valid-recovery-code-1234')).toBe(true);
    expect(vRegExp.test('xxxx-xxxx-xxxx')).toBe(true);

    const recForm = recInput.closest('form');
    expect(recForm).not.toBeNull();
    // Short code (<8) fails client-side format
    fireEvent.change(recInput, { target: { value: 'short' } });
    if (recForm) {
      fireEvent.submit(recForm);
    }

    expect(onError).toHaveBeenCalledWith(
      expect.objectContaining({ message: 'Invalid recovery code format.' }),
    );

    // Valid format submits to verifyRecoveryCode
    const verifyRecSpy = vi.spyOn(authApi, 'verifyRecoveryCode').mockResolvedValue({
      status: 'authenticated',
    });

    fireEvent.change(recInput, { target: { value: 'valid-recovery-code-1234' } });
    if (recForm) {
      fireEvent.submit(recForm);
    }

    await waitFor(() => {
      expect(verifyRecSpy).toHaveBeenCalledWith({
        challenge_id: 'chall-rec',
        code: 'valid-recovery-code-1234',
      });
      expect(onSuccess).toHaveBeenCalledTimes(1);
    });
  });

  it('handles Passkey assertion failure and null credential', async () => {
    (window as unknown as { PublicKeyCredential?: unknown }).PublicKeyCredential = vi.fn();
    vi.spyOn(authApi, 'getWebauthnAssertionOptions').mockResolvedValue({
      options: { challenge: 'ch' },
    });

    Object.defineProperty(navigator, 'credentials', {
      writable: true,
      value: { get: vi.fn().mockResolvedValue(null) },
    });

    const onSuccess = vi.fn();
    const onError = vi.fn();
    const onExpired = vi.fn();

    render(
      <SecondFactorStep
        challengeId="chall-null"
        methods={['webauthn']}
        onSuccess={onSuccess}
        onError={onError}
        onSessionExpired={onExpired}
      />,
    );

    const passkeyBtn = screen.getByRole('button', { name: /Use passkey/i });
    fireEvent.click(passkeyBtn);

    await waitFor(() => {
      expect(onError).toHaveBeenCalledWith(
        expect.objectContaining({
          message: 'Passkey verification failed. Try again or use an authenticator code.',
          code: 'WEBAUTHN_FAILED',
        }),
      );
    });
  });

  it('renders cancel button and triggers onCancel when provided', () => {
    const onCancel = vi.fn();
    render(
      <SecondFactorStep
        challengeId="chall-cancel"
        methods={['totp']}
        onSuccess={vi.fn()}
        onError={vi.fn()}
        onSessionExpired={vi.fn()}
        onCancel={onCancel}
      />,
    );

    const cancelBtn = screen.getByRole('button', { name: /Cancel and return to sign-in/i });
    fireEvent.click(cancelBtn);
    expect(onCancel).toHaveBeenCalledTimes(1);
  });

  it('triggers onSessionExpired when Passkey assertion returns CHALLENGE_EXPIRED', async () => {
    (window as unknown as { PublicKeyCredential?: unknown }).PublicKeyCredential = vi.fn();
    vi.spyOn(authApi, 'getWebauthnAssertionOptions').mockRejectedValueOnce(
      new ApiProblem(401, { code: 'CHALLENGE_EXPIRED' }),
    );

    const onExpired = vi.fn();
    render(
      <SecondFactorStep
        challengeId="chall-expired-pk"
        methods={['webauthn']}
        onSuccess={vi.fn()}
        onError={vi.fn()}
        onSessionExpired={onExpired}
      />,
    );

    const passkeyBtn = screen.getByRole('button', { name: /Use passkey/i });
    fireEvent.click(passkeyBtn);

    await waitFor(() => {
      expect(onExpired).toHaveBeenCalledTimes(1);
    });
  });

  it('handles recovery code errors (CHALLENGE_EXPIRED and generic failure)', async () => {
    const onExpired = vi.fn();
    const onError = vi.fn();

    // 1. Generic failure
    vi.spyOn(authApi, 'verifyRecoveryCode').mockRejectedValueOnce(
      new ApiProblem(401, { code: 'INVALID_CREDENTIALS' }),
    );

    const { rerender } = render(
      <SecondFactorStep
        challengeId="chall-rec-err"
        methods={['recovery']}
        onSuccess={vi.fn()}
        onError={onError}
        onSessionExpired={onExpired}
      />,
    );

    const recInput = screen.getByLabelText(/Single-use Recovery Code/i);
    const recForm1 = recInput.closest('form');
    expect(recForm1).not.toBeNull();
    fireEvent.change(recInput, { target: { value: 'recovery-code-fail-1' } });
    if (recForm1) {
      fireEvent.submit(recForm1);
    }

    await waitFor(() => {
      expect(onError).toHaveBeenCalledWith(
        expect.objectContaining({ code: 'INVALID_CREDENTIALS' }),
      );
    });

    // 2. Session expired
    vi.spyOn(authApi, 'verifyRecoveryCode').mockRejectedValueOnce(
      new ApiProblem(401, { code: 'CHALLENGE_EXPIRED' }),
    );

    rerender(
      <SecondFactorStep
        challengeId="chall-rec-exp"
        methods={['recovery']}
        onSuccess={vi.fn()}
        onError={onError}
        onSessionExpired={onExpired}
      />,
    );

    const recInput2 = screen.getByLabelText(/Single-use Recovery Code/i);
    const recForm2 = recInput2.closest('form');
    expect(recForm2).not.toBeNull();
    fireEvent.change(recInput2, {
      target: { value: 'recovery-code-fail-2' },
    });
    if (recForm2) {
      fireEvent.submit(recForm2);
    }

    await waitFor(() => {
      expect(onExpired).toHaveBeenCalledTimes(1);
    });
  });

  it('handles empty methods array fallback to totp and allows switching tabs', () => {
    (window as unknown as { PublicKeyCredential?: unknown }).PublicKeyCredential = vi.fn();
    const { unmount: unmountEmpty } = render(
      <SecondFactorStep
        challengeId="chall-empty"
        methods={[]}
        onSuccess={vi.fn()}
        onError={vi.fn()}
        onSessionExpired={vi.fn()}
      />,
    );

    expect(screen.getByRole('tab', { name: /Authenticator code/i })).toBeDefined();
    unmountEmpty();

    // Test switching tabs with all 3 methods
    const { unmount } = render(
      <SecondFactorStep
        challengeId="chall-all-3"
        methods={['webauthn', 'totp', 'recovery']}
        onSuccess={vi.fn()}
        onError={vi.fn()}
        onSessionExpired={vi.fn()}
      />,
    );

    const passkeyTab = screen.getByRole('tab', { name: /Passkey/i });
    const totpTab = screen.getByRole('tab', { name: /Authenticator code/i });
    const recTab = screen.getByRole('tab', { name: /Recovery code/i });

    // Switch to Authenticator tab
    fireEvent.click(totpTab);
    expect(screen.getByLabelText(/6-digit Authenticator Code/i)).toBeDefined();

    // Switch to Recovery tab
    fireEvent.click(recTab);
    expect(screen.getByLabelText(/Single-use Recovery Code/i)).toBeDefined();

    // Switch back to Passkey tab
    fireEvent.click(passkeyTab);
    expect(screen.getByRole('button', { name: /Use passkey/i })).toBeDefined();

    unmount();
  });

  it('handles passkey null credential and expired challenge branches', async () => {
    (window as unknown as { PublicKeyCredential?: unknown }).PublicKeyCredential = vi.fn();

    vi.spyOn(authApi, 'getWebauthnAssertionOptions').mockResolvedValue({
      options: {
        challenge: 'dGVzdC1jaGFsbGVuZ2U',
        rpId: 'localhost',
      },
    });

    // Null credential returned from navigator.credentials.get
    Object.defineProperty(navigator, 'credentials', {
      writable: true,
      value: { get: vi.fn().mockResolvedValue(null) },
    });

    const onError = vi.fn();
    const onExpired = vi.fn();

    const { rerender } = render(
      <SecondFactorStep
        challengeId="chall-passkey-null"
        methods={['webauthn']}
        onSuccess={vi.fn()}
        onError={onError}
        onSessionExpired={onExpired}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: /Use passkey/i }));

    await waitFor(() => {
      expect(onError).toHaveBeenCalledWith(
        expect.objectContaining({ code: 'WEBAUTHN_FAILED' }),
      );
    });

    // Challenge expired error
    vi.spyOn(authApi, 'getWebauthnAssertionOptions').mockRejectedValueOnce(
      new ApiProblem(400, { code: 'CHALLENGE_EXPIRED' }),
    );

    rerender(
      <SecondFactorStep
        challengeId="chall-passkey-exp"
        methods={['webauthn']}
        onSuccess={vi.fn()}
        onError={onError}
        onSessionExpired={onExpired}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: /Use passkey/i }));

    await waitFor(() => {
      expect(onExpired).toHaveBeenCalledTimes(1);
    });
  });

  it('handles TOTP form submit event with 6 digits and < 6 digits, and error handling', async () => {
    const verifyTotpSpy = vi.spyOn(authApi, 'verifyTotp').mockResolvedValue({
      status: 'authenticated',
    });

    const onSuccess = vi.fn();
    const onError = vi.fn();

    const { rerender } = render(
      <SecondFactorStep
        challengeId="chall-totp-submit"
        methods={['totp']}
        onSuccess={onSuccess}
        onError={onError}
        onSessionExpired={vi.fn()}
      />,
    );

    const input = screen.getByLabelText(/6-digit Authenticator Code/i);
    const form = input.closest('form');
    expect(form).not.toBeNull();

    if (form) {
      // 1. Submit with 3 digits -> does not call submitTotp
      fireEvent.change(input, { target: { value: '123' } });
      fireEvent.submit(form);
      expect(verifyTotpSpy).not.toHaveBeenCalled();

      // 2. Submit with 6 digits via form submit
      fireEvent.change(input, { target: { value: '123456' } });
      fireEvent.submit(form);
      await waitFor(() => {
        expect(verifyTotpSpy).toHaveBeenCalled();
        expect(onSuccess).toHaveBeenCalled();
      });
    }

    // 3. Generic error from verifyTotp in a clean render
    verifyTotpSpy.mockRejectedValueOnce(
      new ApiProblem(400, { code: 'INVALID_CREDENTIALS', detail: 'Bad TOTP code' }),
    );

    rerender(
      <SecondFactorStep
        challengeId="chall-totp-err-clean"
        methods={['totp']}
        onSuccess={onSuccess}
        onError={onError}
        onSessionExpired={vi.fn()}
      />,
    );

    const input2 = screen.getByLabelText(/6-digit Authenticator Code/i);
    fireEvent.change(input2, { target: { value: '654321' } });
    await waitFor(() => {
      expect(onError).toHaveBeenCalledWith(
        expect.objectContaining({ code: 'INVALID_CREDENTIALS' }),
      );
    });
  });

  it('prevents multiple concurrent submissions when isVerifying is active', () => {
    (window as unknown as { PublicKeyCredential?: unknown }).PublicKeyCredential = vi.fn();

    let resolveAssertion: ((val: { options: PublicKeyCredentialRequestOptionsJSON }) => void) | undefined;
    vi.spyOn(authApi, 'getWebauthnAssertionOptions').mockReturnValue(
      new Promise<{ options: PublicKeyCredentialRequestOptionsJSON }>((resolve) => {
        resolveAssertion = resolve;
      }),
    );

    render(
      <SecondFactorStep
        challengeId="chall-concurrent"
        methods={['webauthn']}
        onSuccess={vi.fn()}
        onError={vi.fn()}
        onSessionExpired={vi.fn()}
      />,
    );

    const btn = screen.getByRole('button', { name: /Use passkey/i });
    // First click initiates assertion
    fireEvent.click(btn);
    // Second click should be ignored because isVerifying is true
    fireEvent.click(btn);

    expect(authApi.getWebauthnAssertionOptions).toHaveBeenCalledTimes(1);
    resolveAssertion?.({
      options: { challenge: 'Y2hhbA', rpId: 'localhost' },
    });
  });

  it('ignores tab click when passkey is disabled', () => {
    const origPKC = (window as unknown as { PublicKeyCredential?: unknown }).PublicKeyCredential;
    (window as unknown as { PublicKeyCredential?: unknown }).PublicKeyCredential = undefined;

    render(
      <SecondFactorStep
        challengeId="chall-disabled-tab"
        methods={['totp', 'webauthn']}
        onSuccess={vi.fn()}
        onError={vi.fn()}
        onSessionExpired={vi.fn()}
      />,
    );

    const passkeyTab = screen.getByRole('tab', { name: /Passkey/i });
    fireEvent.click(passkeyTab);

    // Selected tab remains Authenticator code
    const totpTab = screen.getByRole('tab', { name: /Authenticator code/i });
    expect(totpTab.getAttribute('aria-selected')).toBe('true');

    (window as unknown as { PublicKeyCredential?: unknown }).PublicKeyCredential = origPKC;
  });

  it('prevents concurrent recovery code submission when isVerifying is true', () => {
    let resolveRecovery: ((val: { status: 'authenticated' }) => void) | undefined;
    const verifySpy = vi.spyOn(authApi, 'verifyRecoveryCode').mockReturnValue(
      new Promise<{ status: 'authenticated' }>((resolve) => {
        resolveRecovery = resolve;
      }),
    );

    render(
      <SecondFactorStep
        challengeId="chall-rec-concurrent"
        methods={['recovery']}
        onSuccess={vi.fn()}
        onError={vi.fn()}
        onSessionExpired={vi.fn()}
      />,
    );

    const recInput = screen.getByLabelText(/Single-use Recovery Code/i);
    fireEvent.change(recInput, { target: { value: 'recovery-code-valid-1' } });
    const form = recInput.closest('form');
    expect(form).not.toBeNull();

    if (form) {
      fireEvent.submit(form);
      fireEvent.submit(form);
    }

    expect(verifySpy).toHaveBeenCalledTimes(1);
    resolveRecovery?.({ status: 'authenticated' });
  });

  it('supports keyboard navigation (ArrowRight, ArrowLeft, Home, End) across method tabs', () => {
    (window as unknown as { PublicKeyCredential?: unknown }).PublicKeyCredential = vi.fn();

    render(
      <SecondFactorStep
        challengeId="chall-keyboard"
        methods={['totp', 'webauthn', 'recovery']}
        onSuccess={vi.fn()}
        onError={vi.fn()}
        onSessionExpired={vi.fn()}
      />
    );

    const tabs = screen.getAllByRole('tab');
    expect(tabs.length).toBe(3);
    const tab0 = tabs[0];
    const tab1 = tabs[1];
    const tab2 = tabs[2];
    expect(tab0).toBeDefined();
    expect(tab1).toBeDefined();
    expect(tab2).toBeDefined();
    if (!tab0 || !tab1 || !tab2) return;

    // Initial selected is totp (index 0)
    expect(tab0.getAttribute('aria-selected')).toBe('true');

    // ArrowRight moves to webauthn (index 1)
    fireEvent.keyDown(tab0, { key: 'ArrowRight' });
    expect(tab1.getAttribute('aria-selected')).toBe('true');

    // ArrowDown moves to recovery (index 2)
    fireEvent.keyDown(tab1, { key: 'ArrowDown' });
    expect(tab2.getAttribute('aria-selected')).toBe('true');

    // ArrowRight wraps to totp (index 0)
    fireEvent.keyDown(tab2, { key: 'ArrowRight' });
    expect(tab0.getAttribute('aria-selected')).toBe('true');

    // ArrowLeft wraps to recovery (index 2)
    fireEvent.keyDown(tab0, { key: 'ArrowLeft' });
    expect(tab2.getAttribute('aria-selected')).toBe('true');

    // ArrowUp moves to webauthn (index 1)
    fireEvent.keyDown(tab2, { key: 'ArrowUp' });
    expect(tab1.getAttribute('aria-selected')).toBe('true');

    // Home moves to first (index 0)
    fireEvent.keyDown(tab1, { key: 'Home' });
    expect(tab0.getAttribute('aria-selected')).toBe('true');

    // End moves to last (index 2)
    fireEvent.keyDown(tab0, { key: 'End' });
    expect(tab2.getAttribute('aria-selected')).toBe('true');

    // Non-navigation key does not trigger tab change
    fireEvent.keyDown(tab2, { key: 'Tab' });
    expect(tab2.getAttribute('aria-selected')).toBe('true');
  });

  it('handles fallback when first method entry is undefined', () => {
    render(
      <SecondFactorStep
        challengeId="chall-undef-method"
        methods={[undefined as unknown as authApi.MfaMethod]}
        onSuccess={vi.fn()}
        onError={vi.fn()}
        onSessionExpired={vi.fn()}
      />,
    );
    expect(screen.getByRole('textbox', { name: /6-digit Authenticator Code/i })).toBeDefined();
  });

  it('prevents concurrent passkey assertions when isVerifying is already true', () => {
    (window as unknown as { PublicKeyCredential?: unknown }).PublicKeyCredential = vi.fn();
    let resolveOptions: ((val: { options: { challenge: string; rpId: string } }) => void) | undefined;
    vi.spyOn(authApi, 'getWebauthnAssertionOptions').mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveOptions = resolve;
        }),
    );

    render(
      <SecondFactorStep
        challengeId="chall-passkey-concurrent"
        methods={['webauthn']}
        onSuccess={vi.fn()}
        onError={vi.fn()}
        onSessionExpired={vi.fn()}
      />,
    );

    const passkeyBtn = screen.getByRole('button', { name: /Use passkey/i });
    fireEvent.click(passkeyBtn);
    // While isVerifying is true, second click should hit early return
    fireEvent.click(passkeyBtn);

    expect(authApi.getWebauthnAssertionOptions).toHaveBeenCalledTimes(1);
    resolveOptions?.({ options: { challenge: 'Y2hhbA', rpId: 'localhost' } });
  });
});
