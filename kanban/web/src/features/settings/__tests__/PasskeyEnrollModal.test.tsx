// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { PasskeyEnrollModal } from '../PasskeyEnrollModal';
import * as personalSettingsApi from '../personalSettingsApi';
import { ApiProblem } from '../../../api/problem';

function renderModal(
  props: Partial<React.ComponentProps<typeof PasskeyEnrollModal>> = {},
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } }),
) {
  const defaultProps: React.ComponentProps<typeof PasskeyEnrollModal> = {
    isOpen: true,
    onClose: vi.fn(),
    onSuccess: vi.fn(),
    initialAttachment: 'platform',
    ...props,
  };

  return {
    ...render(
      <QueryClientProvider client={client}>
        <PasskeyEnrollModal {...defaultProps} />
      </QueryClientProvider>,
    ),
    client,
    props: defaultProps,
  };
}

describe('PasskeyEnrollModal (KAN-25)', () => {
  const mockOptions: personalSettingsApi.PublicKeyCredentialCreationOptionsJSON = {
    rp: { name: 'Kanban RP' },
    user: { id: 'dXNlcjE', name: 'alice', displayName: 'Alice' },
    challenge: 'Y2hhbGxlbmdlMQ',
    pubKeyCredParams: [{ alg: -7, type: 'public-key' }],
    timeout: 60000,
  };

  const mockCred = {
    id: 'cred-mock-id',
    rawId: new Uint8Array([1, 2, 3]).buffer,
    type: 'public-key',
    response: {
      clientDataJSON: new TextEncoder().encode('{"type":"webauthn.create"}').buffer,
      attestationObject: new Uint8Array([4, 5, 6]).buffer,
      getTransports: () => ['internal', 'hybrid'],
    },
    getClientExtensionResults: () => ({}),
  } as unknown as PublicKeyCredential;

  let mockCredentials: {
    create: ReturnType<typeof vi.fn>;
    get: ReturnType<typeof vi.fn>;
  };

  beforeEach(() => {
    vi.restoreAllMocks();

    mockCredentials = {
      create: vi.fn().mockResolvedValue(mockCred),
      get: vi.fn().mockResolvedValue(null),
    };

    Object.defineProperty(navigator, 'credentials', {
      writable: true,
      configurable: true,
      value: mockCredentials,
    });
  });

  it('renders nothing when isOpen is false', () => {
    const { container } = renderModal({ isOpen: false });
    expect(container.firstChild).toBeNull();
  });

  it('renders modal with initial attachment and switches radio choices', () => {
    renderModal({ initialAttachment: 'cross-platform' });

    expect(screen.getByRole('dialog')).toBeDefined();
    expect(screen.getByTestId('passkey-enroll-title')).toBeDefined();

    const crossRadio = screen.getByTestId<HTMLInputElement>('attachment-cross-platform-radio');
    expect(crossRadio.checked).toBe(true);

    const platformRadio = screen.getByTestId<HTMLInputElement>('attachment-platform-radio');
    fireEvent.click(platformRadio);
    expect(platformRadio.checked).toBe(true);

    const anyRadio = screen.getByTestId<HTMLInputElement>('attachment-any-radio');
    fireEvent.click(anyRadio);
    expect(anyRadio.checked).toBe(true);

    fireEvent.click(crossRadio);
    expect(crossRadio.checked).toBe(true);
  });

  it('calls onClose when clicking Cancel button or header close', () => {
    const onClose = vi.fn();
    renderModal({ onClose });

    fireEvent.click(screen.getByTestId('passkey-enroll-close-btn'));
    expect(onClose).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByTestId('passkey-enroll-cancel-btn'));
    expect(onClose).toHaveBeenCalledTimes(2);
  });

  it('prevents submission when nickname is empty or whitespace', () => {
    renderModal();

    const input = screen.getByTestId('passkey-enroll-nickname-input');
    const form = input.closest('form');
    expect(form).not.toBeNull();
    if (form) {
      fireEvent.submit(form);
    }

    expect(screen.getByTestId('passkey-enroll-error')).toBeDefined();
    expect(screen.getByTestId('passkey-enroll-error').textContent).toContain('Nickname is required.');
  });

  it('prevents submission when nickname exceeds 64 characters', () => {
    renderModal();

    const input = screen.getByTestId<HTMLInputElement>('passkey-enroll-nickname-input');
    fireEvent.change(input, { target: { value: 'a'.repeat(65) } });

    const form = input.closest('form');
    expect(form).not.toBeNull();
    if (form) {
      fireEvent.submit(form);
    }

    expect(screen.getByTestId('passkey-enroll-error')).toBeDefined();
    expect(screen.getByTestId('passkey-enroll-error').textContent).toContain('Nickname must not exceed 64 characters.');
  });

  it('completes passkey registration flow successfully', async () => {
    const getOptionsSpy = vi
      .spyOn(personalSettingsApi, 'fetchWebauthnRegistrationOptions')
      .mockResolvedValueOnce(mockOptions);
    const verifySpy = vi
      .spyOn(personalSettingsApi, 'verifyWebauthnRegistration')
      .mockResolvedValueOnce({ verified: true, credential_id: 'cred-123', nickname: 'MacBook Touch ID' });

    const onSuccess = vi.fn();
    const onClose = vi.fn();
    const { client } = renderModal({ onSuccess, onClose, initialAttachment: 'platform' });

    const invalidateSpy = vi.spyOn(client, 'invalidateQueries');

    const input = screen.getByTestId('passkey-enroll-nickname-input');
    fireEvent.change(input, { target: { value: 'MacBook Touch ID' } });

    const submitBtn = screen.getByTestId('passkey-enroll-submit-btn');
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(getOptionsSpy).toHaveBeenCalledWith('platform');
      expect(mockCredentials.create).toHaveBeenCalled();
      expect(verifySpy).toHaveBeenCalledWith(
        expect.objectContaining({
          nickname: 'MacBook Touch ID',
        }),
      );
      const verifyCall = verifySpy.mock.calls[0]?.[0];
      expect(verifyCall?.credential.id).toBe('cred-mock-id');
      expect(onSuccess).toHaveBeenCalledWith('Passkey registered successfully.');
      expect(onClose).toHaveBeenCalled();
      expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['myPasskeys'] });
      expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['myMfaStatus'] });
    });
  });

  it('handles any authenticator choice passing undefined to registration options', async () => {
    const getOptionsSpy = vi
      .spyOn(personalSettingsApi, 'fetchWebauthnRegistrationOptions')
      .mockResolvedValueOnce(mockOptions);
    vi.spyOn(personalSettingsApi, 'verifyWebauthnRegistration').mockResolvedValueOnce({
      verified: true,
      credential_id: 'cred-any',
      nickname: 'Any Key',
    });

    renderModal({ initialAttachment: 'platform' });

    fireEvent.click(screen.getByTestId('attachment-any-radio'));
    fireEvent.change(screen.getByTestId('passkey-enroll-nickname-input'), {
      target: { value: 'Any Key' },
    });
    fireEvent.click(screen.getByTestId('passkey-enroll-submit-btn'));

    await waitFor(() => {
      expect(getOptionsSpy).toHaveBeenCalledWith(undefined);
    });
  });

  it('handles null credential from navigator.credentials.create', async () => {
    vi.spyOn(personalSettingsApi, 'fetchWebauthnRegistrationOptions').mockResolvedValueOnce(mockOptions);
    mockCredentials.create.mockResolvedValueOnce(null);

    renderModal();

    fireEvent.change(screen.getByTestId('passkey-enroll-nickname-input'), {
      target: { value: 'Null Key' },
    });
    fireEvent.click(screen.getByTestId('passkey-enroll-submit-btn'));

    await waitFor(() => {
      expect(screen.getByTestId('passkey-enroll-error').textContent).toContain('Credential creation returned null.');
    });
  });

  it('handles NotAllowedError user cancellation or timeout', async () => {
    vi.spyOn(personalSettingsApi, 'fetchWebauthnRegistrationOptions').mockResolvedValueOnce(mockOptions);
    const notAllowed = new Error('The operation was cancelled by the user.');
    notAllowed.name = 'NotAllowedError';
    mockCredentials.create.mockRejectedValueOnce(notAllowed);

    renderModal();

    fireEvent.change(screen.getByTestId('passkey-enroll-nickname-input'), {
      target: { value: 'Cancelled Key' },
    });
    fireEvent.click(screen.getByTestId('passkey-enroll-submit-btn'));

    await waitFor(() => {
      expect(screen.getByTestId('passkey-enroll-error').textContent).toContain(
        'Passkey registration was cancelled or timed out. Please try again.',
      );
    });
  });

  it('handles ApiProblem during registration options or verify', async () => {
    const problem = new ApiProblem(409, { code: 'CREDENTIAL_LIMIT', detail: 'Maximum of 10 credentials reached.' });
    vi.spyOn(personalSettingsApi, 'fetchWebauthnRegistrationOptions').mockRejectedValueOnce(problem);

    renderModal();

    const input = screen.getByTestId('passkey-enroll-nickname-input');
    fireEvent.change(input, {
      target: { value: 'YubiKey 5C' },
    });
    fireEvent.click(screen.getByTestId('passkey-enroll-submit-btn'));

    await waitFor(() => {
      expect(screen.getByTestId('passkey-enroll-error').textContent).toContain('Maximum of 10 credentials reached.');
    });

    // Typing in nickname input clears errorMsg
    fireEvent.change(input, {
      target: { value: 'YubiKey 5C New' },
    });
    expect(screen.queryByTestId('passkey-enroll-error')).toBeNull();
  });

  it('handles ApiProblem with title fallback and generic fallback', async () => {
    const problemWithTitle = new ApiProblem(400, { title: 'Registration Rejected' });
    vi.spyOn(personalSettingsApi, 'fetchWebauthnRegistrationOptions').mockRejectedValueOnce(problemWithTitle);

    renderModal();

    const input = screen.getByTestId('passkey-enroll-nickname-input');
    fireEvent.change(input, { target: { value: 'Title Only Key' } });
    fireEvent.click(screen.getByTestId('passkey-enroll-submit-btn'));

    await waitFor(() => {
      expect(screen.getByTestId('passkey-enroll-error').textContent).toContain('Registration Rejected');
    });

    // ApiProblem without detail and without title
    const problemEmpty = new ApiProblem(500, {});
    vi.spyOn(personalSettingsApi, 'fetchWebauthnRegistrationOptions').mockRejectedValueOnce(problemEmpty);

    fireEvent.click(screen.getByTestId('passkey-enroll-submit-btn'));
    await waitFor(() => {
      expect(screen.getByTestId('passkey-enroll-error').textContent).toContain('Failed to register passkey.');
    });
  });

  it('handles non-Error thrown during registration', async () => {
    vi.spyOn(personalSettingsApi, 'fetchWebauthnRegistrationOptions').mockRejectedValueOnce('Network failure');

    renderModal();

    fireEvent.change(screen.getByTestId('passkey-enroll-nickname-input'), {
      target: { value: 'Test String Throw' },
    });
    fireEvent.click(screen.getByTestId('passkey-enroll-submit-btn'));

    await waitFor(() => {
      expect(screen.getByTestId('passkey-enroll-error').textContent).toContain(
        'An unexpected error occurred during passkey registration.',
      );
    });
  });

  it('handles generic Error during registration with empty message fallback', async () => {
    vi.spyOn(personalSettingsApi, 'fetchWebauthnRegistrationOptions').mockRejectedValueOnce(new Error(''));

    renderModal();

    fireEvent.change(screen.getByTestId('passkey-enroll-nickname-input'), {
      target: { value: 'Empty Msg Key' },
    });
    fireEvent.click(screen.getByTestId('passkey-enroll-submit-btn'));

    await waitFor(() => {
      expect(screen.getByTestId('passkey-enroll-error').textContent).toContain('Failed to register passkey.');
    });
  });

  it('delegates to onInterceptAal2 when AAL2 stepup is challenged', async () => {
    const aal2Problem = new ApiProblem(403, { code: 'AAL2_REQUIRED', challenge_id: 'stepup-123', methods: ['webauthn', 'totp'] });
    vi.spyOn(personalSettingsApi, 'fetchWebauthnRegistrationOptions').mockRejectedValueOnce(aal2Problem);

    const onInterceptAal2 = vi.fn().mockReturnValue(true);
    renderModal({ onInterceptAal2 });

    fireEvent.change(screen.getByTestId('passkey-enroll-nickname-input'), {
      target: { value: 'AAL2 Key' },
    });
    fireEvent.click(screen.getByTestId('passkey-enroll-submit-btn'));

    await waitFor(() => {
      expect(onInterceptAal2).toHaveBeenCalledWith(aal2Problem, expect.any(Function));
    });
  });
});
