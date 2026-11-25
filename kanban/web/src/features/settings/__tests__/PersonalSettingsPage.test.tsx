// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router';
import { PersonalSettingsPage } from '../PersonalSettingsPage';
import * as api from '../personalSettingsApi';
import * as authApi from '../../auth/authApi';
import { ApiProblem } from '../../../api/problem';
import { Aal2StepUpCancelledError } from '../../../api/client';

vi.mock('../personalSettingsApi');
vi.mock('../../auth/authApi');

vi.mock('../../auth/SecondFactorStep', () => ({
  SecondFactorStep: ({
    onSuccess,
    onError,
    onSessionExpired,
    onCancel,
  }: {
    onSuccess: () => void;
    onError: () => void;
    onSessionExpired: () => void;
    onCancel: () => void;
  }) => (
    <div data-testid="mock-second-factor-step">
      <button data-testid="mock-2fa-success" onClick={onSuccess}>
        BtnMockSuccess
      </button>
      <button data-testid="mock-2fa-error" onClick={onError}>
        BtnMockError
      </button>
      <button data-testid="mock-2fa-expired" onClick={onSessionExpired}>
        BtnMockExpired
      </button>
      <button data-testid="mock-2fa-cancel" onClick={onCancel}>
        BtnMockCancel
      </button>
    </div>
  ),
}));

const mockProfile: api.UserProfileResponse = {
  principal_id: '11111111-1111-4111-8111-111111111111',
  display_name: 'Jane Doe',
  username: 'janedoe',
  email: 'jane@example.com',
  timezone: 'America/New_York',
  avatar_url: '/api/v1/users/11111111-1111-4111-8111-111111111111/avatar',
  roles: ['user'],
  is_server_admin: false,
};

const mockMfaStatus: api.MfaStatusResponse = {
  totp_enabled: true,
  passkeys_count: 1,
  recovery_codes_remaining: 10,
};

const mockPasskeys: api.WebauthnCredentialItem[] = [
  {
    id: 'pk-1',
    nickname: 'MacBook TouchID',
    created_at: '2026-01-01T00:00:00Z',
    last_used_at: '2026-02-01T00:00:00Z',
    aaguid: '00000000-0000-0000-0000-000000000000',
  },
];

describe('PersonalSettingsPage', () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
      },
    });
    vi.clearAllMocks();

    vi.mocked(api.fetchMyProfile).mockResolvedValue(mockProfile);
    vi.mocked(api.fetchMfaStatus).mockResolvedValue(mockMfaStatus);
    vi.mocked(api.fetchPasskeys).mockResolvedValue(mockPasskeys);
    vi.mocked(api.fetchExternalIdentities).mockResolvedValue([]);
    vi.mocked(authApi.fetchAuthCards).mockResolvedValue({ cards: [] });
  });

  const renderComponent = () =>
    render(
      <MemoryRouter>
        <QueryClientProvider client={queryClient}>
          <PersonalSettingsPage />
        </QueryClientProvider>
      </MemoryRouter>,
    );

  it('renders personal settings sections with loaded profile data', async () => {
    renderComponent();

    await waitFor(() => {
      expect(screen.getByTestId('personal-settings-page')).toBeDefined();
    });

    const displayNameInput = screen.getByTestId<HTMLInputElement>('display-name-input');
    expect(displayNameInput.value).toBe('Jane Doe');

    const tzSelect = screen.getByTestId<HTMLSelectElement>('timezone-select');
    expect(tzSelect.value).toBe('America/New_York');

    expect(screen.getByText('MacBook TouchID')).toBeDefined();
    expect(screen.getByTestId('mfa-status-passkeys').textContent).toBe('1 Enrolled');
    expect(screen.getByText('Passkeys (Primary 2FA)')).toBeDefined();
    expect(screen.getByTestId('mfa-status-totp').textContent).toBe('Active');
    expect(screen.getByText('Authenticator App (Backup TOTP)')).toBeDefined();
    expect(screen.getByTestId('mfa-status-recovery-count').textContent).toBe('10');
  });

  it('updates display name and timezone', async () => {
    vi.mocked(api.updateMyProfile).mockResolvedValue({
      ...mockProfile,
      display_name: 'Jane Smith',
      timezone: 'Europe/London',
    });

    renderComponent();

    await waitFor(() => {
      expect(screen.getByTestId('display-name-input')).toBeDefined();
    });

    fireEvent.change(screen.getByTestId('display-name-input'), { target: { value: 'Jane Smith' } });
    fireEvent.change(screen.getByTestId('timezone-select'), { target: { value: 'Europe/London' } });
    fireEvent.click(screen.getByTestId('save-profile-btn'));

    await waitFor(() => {
      expect(api.updateMyProfile).toHaveBeenCalledWith({
        display_name: 'Jane Smith',
        timezone: 'Europe/London',
      });
      expect(screen.getByTestId('alert-success').textContent).toContain('Profile updated successfully.');
    });
  });

  it('rejects SVG avatar upload client-side', async () => {
    renderComponent();

    await waitFor(() => {
      expect(screen.getByTestId('avatar-file-input')).toBeDefined();
    });

    const file = new File(['<svg></svg>'], 'bad.svg', { type: 'image/svg+xml' });
    const input = screen.getByTestId('avatar-file-input');
    fireEvent.change(input, { target: { files: [file] } });

    await waitFor(() => {
      expect(screen.getByTestId('alert-error').textContent).toContain('SVG avatars are rejected for security');
    });
    expect(api.uploadAvatar).not.toHaveBeenCalled();
  });

  it('validates password length and matching confirmation', async () => {
    renderComponent();

    await waitFor(() => {
      expect(screen.getByTestId('current-password-input')).toBeDefined();
    });

    fireEvent.change(screen.getByTestId('current-password-input'), { target: { value: 'oldpassword123' } });
    fireEvent.change(screen.getByTestId('new-password-input'), { target: { value: 'short' } });
    fireEvent.change(screen.getByTestId('confirm-password-input'), { target: { value: 'mismatch' } });
    fireEvent.click(screen.getByTestId('change-password-btn'));

    await waitFor(() => {
      expect(screen.getByTestId('alert-error').textContent).toContain('New passwords do not match');
    });

    fireEvent.change(screen.getByTestId('confirm-password-input'), { target: { value: 'short' } });
    fireEvent.click(screen.getByTestId('change-password-btn'));

    await waitFor(() => {
      expect(screen.getByTestId('alert-error').textContent).toContain('Password must be at least 12 characters');
    });
    expect(api.changePassword).not.toHaveBeenCalled();
  });

  it('renames passkey and displays updated list', async () => {
    vi.mocked(api.renamePasskey).mockResolvedValue({
      id: 'pk-1',
      nickname: 'Work YubiKey',
      created_at: '2026-01-01T00:00:00Z',
      last_used_at: null,
      aaguid: null,
    });

    renderComponent();

    await waitFor(() => {
      expect(screen.getByTestId('rename-passkey-pk-1')).toBeDefined();
    });

    fireEvent.click(screen.getByTestId('rename-passkey-pk-1'));
    expect(screen.getByTestId('passkey-nickname-input')).toBeDefined();

    fireEvent.change(screen.getByTestId('passkey-nickname-input'), { target: { value: 'Work YubiKey' } });
    fireEvent.click(screen.getByTestId('save-passkey-nickname-btn'));

    await waitFor(() => {
      expect(api.renamePasskey).toHaveBeenCalledWith('pk-1', 'Work YubiKey');
      expect(screen.getByTestId('alert-success').textContent).toContain('Passkey renamed.');
    });
  });

  it('regenerates recovery codes and displays modal', async () => {
    const newCodes = ['1111-2222', '3333-4444', '5555-6666'];
    vi.mocked(api.regenerateRecoveryCodes).mockResolvedValue({ recovery_codes: newCodes });
    vi.spyOn(window, 'confirm').mockReturnValue(true);

    renderComponent();

    await waitFor(() => {
      expect(screen.getByTestId('regenerate-recovery-codes-btn')).toBeDefined();
    });

    fireEvent.click(screen.getByTestId('regenerate-recovery-codes-btn'));

    await waitFor(() => {
      expect(api.regenerateRecoveryCodes).toHaveBeenCalled();
      expect(screen.getByTestId('recovery-codes-grid')).toBeDefined();
      expect(screen.getByText('1111-2222')).toBeDefined();
      expect(screen.getByTestId('copy-recovery-codes-btn')).toBeDefined();
    });

    /* eslint-disable @typescript-eslint/no-deprecated */
    document.execCommand = vi.fn().mockReturnValue(true);
    /* eslint-enable @typescript-eslint/no-deprecated */
    fireEvent.click(screen.getByTestId('copy-recovery-codes-btn'));
    await waitFor(() => {
      expect(screen.getByText('Copied!')).toBeDefined();
    });
    await waitFor(
      () => {
        expect(screen.getByText('Copy Codes')).toBeDefined();
      },
      { timeout: 3000 },
    );

    fireEvent.click(screen.getByTestId('close-recovery-modal-btn'));
    expect(screen.queryByTestId('recovery-codes-grid')).toBeNull();
  });

  it('renders loading state when profile is loading', () => {
    vi.mocked(api.fetchMyProfile).mockReturnValue(new Promise(() => { /* never resolves */ }));
    renderComponent();
    expect(screen.getByTestId('personal-settings-loading')).toBeDefined();
    expect(screen.getByText('Loading personal settings...')).toBeDefined();
  });

  it('handles valid avatar upload and avatar removal', async () => {
    vi.mocked(api.uploadAvatar).mockResolvedValue({
      ...mockProfile,
      avatar_url: '/api/v1/users/1111/avatar.png',
    });
    vi.mocked(api.deleteAvatar).mockResolvedValue({
      ...mockProfile,
      avatar_url: null,
    });

    renderComponent();

    await waitFor(() => {
      expect(screen.getByTestId('upload-avatar-btn')).toBeDefined();
    });

    // Upload picture button triggers file input click
    const fileInput = screen.getByTestId('avatar-file-input');
    const clickSpy = vi.spyOn(fileInput, 'click');
    fireEvent.click(screen.getByTestId('upload-avatar-btn'));
    expect(clickSpy).toHaveBeenCalled();

    // Upload valid image file opens AvatarCropModal
    const validFile = new File(['valid-image-bytes'], 'avatar.png', { type: 'image/png' });
    fireEvent.change(fileInput, { target: { files: [validFile] } });

    await waitFor(() => {
      expect(screen.getByTestId('avatar-crop-modal')).toBeDefined();
    });
    fireEvent.click(screen.getByTestId('avatar-crop-save-btn'));

    await waitFor(() => {
      expect(api.uploadAvatar).toHaveBeenCalled();
      expect(screen.getByTestId('alert-success').textContent).toContain('Avatar uploaded successfully.');
    });

    // Remove avatar
    expect(screen.getByTestId('remove-avatar-btn')).toBeDefined();
    fireEvent.click(screen.getByTestId('remove-avatar-btn'));

    await waitFor(() => {
      expect(api.deleteAvatar).toHaveBeenCalled();
      expect(screen.getByTestId('alert-success').textContent).toContain('Avatar removed.');
    });
  });

  it('toggles password visibility and handles successful password update', async () => {
    vi.mocked(api.changePassword).mockResolvedValue({ ok: true, message: 'Password updated' });

    renderComponent();

    await waitFor(() => {
      expect(screen.getByTestId('current-password-input')).toBeDefined();
    });

    const currentPwInput = screen.getByTestId<HTMLInputElement>('current-password-input');
    const newPwInput = screen.getByTestId<HTMLInputElement>('new-password-input');

    // Toggle current password visibility
    const showPwButtons = screen.getAllByLabelText('Show password');
    const firstShowPwBtn = showPwButtons[0];
    if (firstShowPwBtn) fireEvent.click(firstShowPwBtn);
    expect(currentPwInput.type).toBe('text');
    fireEvent.click(screen.getByLabelText('Hide password'));
    expect(currentPwInput.type).toBe('password');

    // Enter valid passwords
    fireEvent.change(currentPwInput, { target: { value: 'oldpassword123' } });
    fireEvent.change(newPwInput, { target: { value: 'newpassword12345' } });
    fireEvent.change(screen.getByTestId('confirm-password-input'), { target: { value: 'newpassword12345' } });
    fireEvent.click(screen.getByTestId('change-password-btn'));

    await waitFor(() => {
      expect(api.changePassword).toHaveBeenCalledWith({
        current_password: 'oldpassword123',
        new_password: 'newpassword12345',
      });
      expect(screen.getByTestId('alert-success').textContent).toContain('Password updated successfully.');
    });

    // Dismiss success alert
    fireEvent.click(screen.getByText('Dismiss'));
    expect(screen.queryByTestId('alert-success')).toBeNull();
  });

  it('handles password change API error response and dismisses alert', async () => {
    vi.mocked(api.changePassword).mockRejectedValue(new Error('Incorrect current password'));

    renderComponent();

    await waitFor(() => {
      expect(screen.getByTestId('current-password-input')).toBeDefined();
    });

    fireEvent.change(screen.getByTestId('current-password-input'), { target: { value: 'wrongpassword' } });
    fireEvent.change(screen.getByTestId('new-password-input'), { target: { value: 'newpassword12345' } });
    fireEvent.change(screen.getByTestId('confirm-password-input'), { target: { value: 'newpassword12345' } });
    fireEvent.click(screen.getByTestId('change-password-btn'));

    await waitFor(() => {
      expect(screen.getByTestId('alert-error').textContent).toContain('Incorrect current password');
    });

    fireEvent.click(screen.getByText('Dismiss'));
    expect(screen.queryByTestId('alert-error')).toBeNull();
  });

  it('manages TOTP enrollment and disabling', async () => {
    vi.mocked(api.fetchMfaStatus).mockResolvedValue({
      ...mockMfaStatus,
      totp_enabled: false,
    });
    vi.mocked(api.enrollTotp).mockResolvedValue({
      secret: 'MOCKSECRET123456',
      provisioning_uri: 'otpauth://totp/kanban:jane?secret=MOCKSECRET123456',
    });
    vi.mocked(api.confirmTotp).mockResolvedValue({
      ok: true,
      recovery_codes: ['rec-code-1', 'rec-code-2'],
    });
    vi.mocked(api.deleteTotp).mockResolvedValue(undefined);

    renderComponent();

    await waitFor(() => {
      expect(screen.getByTestId('enable-totp-btn')).toBeDefined();
    });

    // Start TOTP enrollment
    fireEvent.click(screen.getByTestId('enable-totp-btn'));

    await waitFor(() => {
      expect(api.enrollTotp).toHaveBeenCalled();
      expect(screen.getByTestId('totp-secret-key').textContent).toBe('MOCKSECRET123456');
    });

    // Confirm TOTP with valid 6-digit code
    fireEvent.change(screen.getByTestId('totp-verification-input'), { target: { value: '654321' } });
    fireEvent.click(screen.getByTestId('confirm-totp-btn'));

    await waitFor(() => {
      expect(api.confirmTotp).toHaveBeenCalledWith('654321');
      expect(screen.getByTestId('alert-success').textContent).toContain('Two-factor authentication enabled successfully.');
      expect(screen.getByTestId('recovery-codes-grid')).toBeDefined();
    });

    fireEvent.click(screen.getByTestId('close-recovery-modal-btn'));
  });

  it('manages disabling TOTP when already active', async () => {
    vi.mocked(api.deleteTotp).mockResolvedValue(undefined);

    renderComponent();

    await waitFor(() => {
      expect(screen.getByTestId('disable-totp-btn')).toBeDefined();
    });

    // Disable TOTP with confirm: false (should not call deleteTotp)
    vi.spyOn(window, 'confirm').mockReturnValueOnce(false);
    fireEvent.click(screen.getByTestId('disable-totp-btn'));
    expect(api.deleteTotp).not.toHaveBeenCalled();

    // Disable TOTP with confirm: true
    vi.spyOn(window, 'confirm').mockReturnValueOnce(true);
    fireEvent.click(screen.getByTestId('disable-totp-btn'));

    await waitFor(() => {
      expect(api.deleteTotp).toHaveBeenCalled();
      expect(screen.getByTestId('alert-success').textContent).toContain('TOTP disabled.');
    });
  });

  it('manages passkey deletion with confirmation', async () => {
    vi.mocked(api.deletePasskey).mockResolvedValue(undefined);

    renderComponent();

    await waitFor(() => {
      expect(screen.getByTestId('delete-passkey-pk-1')).toBeDefined();
    });

    // Cancel deletion in confirm dialog
    vi.spyOn(window, 'confirm').mockReturnValueOnce(false);
    fireEvent.click(screen.getByTestId('delete-passkey-pk-1'));
    expect(api.deletePasskey).not.toHaveBeenCalled();

    // Confirm deletion
    vi.spyOn(window, 'confirm').mockReturnValueOnce(true);
    fireEvent.click(screen.getByTestId('delete-passkey-pk-1'));

    await waitFor(() => {
      expect(api.deletePasskey).toHaveBeenCalledWith('pk-1');
      expect(screen.getByTestId('alert-success').textContent).toContain('Passkey removed.');
    });
  });

  it('cancels passkey rename modal when clicking cancel', async () => {
    renderComponent();

    await waitFor(() => {
      expect(screen.getByTestId('rename-passkey-pk-1')).toBeDefined();
    });

    fireEvent.click(screen.getByTestId('rename-passkey-pk-1'));
    expect(screen.getByTestId('passkey-nickname-input')).toBeDefined();

    // Click Header Cancel button in rename modal
    const cancelButtons = screen.getAllByRole('button', { name: 'Cancel' });
    const firstCancelBtn = cancelButtons[0];
    if (firstCancelBtn) fireEvent.click(firstCancelBtn);
    expect(screen.queryByTestId('passkey-nickname-input')).toBeNull();

    // Reopen and click Footer Cancel button in rename modal
    fireEvent.click(screen.getByTestId('rename-passkey-pk-1'));
    const cancelButtonsFooter = screen.getAllByRole('button', { name: 'Cancel' });
    const secondCancelBtn = cancelButtonsFooter[1];
    if (secondCancelBtn) fireEvent.click(secondCancelBtn);
    expect(screen.queryByTestId('passkey-nickname-input')).toBeNull();
  });

  it('renders empty passkey notice when passkeys list is empty', async () => {
    vi.mocked(api.fetchPasskeys).mockResolvedValue([]);
    renderComponent();

    await waitFor(() => {
      expect(screen.getByText('No passkeys registered yet.')).toBeDefined();
    });
  });

  it('enforces 14 character password minimum for server administrators', async () => {
    vi.mocked(api.fetchMyProfile).mockResolvedValue({
      ...mockProfile,
      is_server_admin: true,
    });

    renderComponent();

    await waitFor(() => {
      expect(screen.getByTestId('current-password-input')).toBeDefined();
    });

    fireEvent.change(screen.getByTestId('current-password-input'), { target: { value: 'currentpass123' } });
    fireEvent.change(screen.getByTestId('new-password-input'), { target: { value: 'twelvechars!' } });
    fireEvent.change(screen.getByTestId('confirm-password-input'), { target: { value: 'twelvechars!' } });
    fireEvent.click(screen.getByTestId('change-password-btn'));

    await waitFor(() => {
      expect(screen.getByTestId('alert-error').textContent).toContain('Password must be at least 14 characters.');
    });
    expect(api.changePassword).not.toHaveBeenCalled();
  });

  it('silently ignores Aal2StepUpCancelledError on password change without error banner', async () => {
    vi.mocked(api.changePassword).mockRejectedValue(new Aal2StepUpCancelledError());

    renderComponent();

    await waitFor(() => {
      expect(screen.getByTestId('current-password-input')).toBeDefined();
    });

    fireEvent.change(screen.getByTestId('current-password-input'), { target: { value: 'oldpassword123' } });
    fireEvent.change(screen.getByTestId('new-password-input'), { target: { value: 'newpassword12345' } });
    fireEvent.change(screen.getByTestId('confirm-password-input'), { target: { value: 'newpassword12345' } });
    fireEvent.click(screen.getByTestId('change-password-btn'));

    await waitFor(() => {
      expect(api.changePassword).toHaveBeenCalled();
    });

    expect(screen.queryByTestId('alert-error')).toBeNull();
    expect(screen.queryByTestId('aal2-stepup-dialog')).toBeNull();
  });

  it('rejects oversized avatar files and renders fallback initials when avatar and name are absent', async () => {
    vi.mocked(api.fetchMyProfile).mockResolvedValue({
      ...mockProfile,
      avatar_url: null,
      display_name: undefined as unknown as string,
      username: 'anonymous',
    });

    renderComponent();

    await waitFor(() => {
      expect(screen.getByText('A')).toBeDefined();
    });

    // Upload oversized file (> 2MB)
    const file = new File(['content'], 'avatar.png', { type: 'image/png' });
    Object.defineProperty(file, 'size', { value: 3 * 1024 * 1024 });

    const fileInput = screen.getByTestId('avatar-file-input');
    fireEvent.change(fileInput, { target: { files: [file] } });

    await waitFor(() => {
      expect(screen.getByTestId('alert-error').textContent).toContain('Avatar file size exceeds 2 MiB limit.');
    });
  });

  it('handles mutation errors for profile update, avatar deletion, and password visibility toggles', async () => {
    vi.mocked(api.updateMyProfile).mockRejectedValue(new Error('Profile update error'));
    vi.mocked(api.deleteAvatar).mockRejectedValue(new Error('Delete avatar error'));

    renderComponent();

    await waitFor(() => {
      expect(screen.getByTestId('save-profile-btn')).toBeDefined();
    });

    // Submit profile update failure
    fireEvent.click(screen.getByTestId('save-profile-btn'));
    await waitFor(() => {
      expect(screen.getByTestId('alert-error').textContent).toContain('Profile update error');
    });

    // Delete avatar failure
    fireEvent.click(screen.getByTestId('remove-avatar-btn'));
    await waitFor(() => {
      expect(screen.getByTestId('alert-error').textContent).toContain('Delete avatar error');
    });

    // Toggle new password show/hide
    const togglePwBtns = screen.getAllByRole('button', { name: 'Show password' });
    if (togglePwBtns[0]) {
      fireEvent.click(togglePwBtns[0]);
      expect(screen.getAllByRole('button', { name: 'Hide password' })[0]).toBeDefined();
    }
  });

  it('handles mutation errors during TOTP confirmation, TOTP disable, and recovery codes regen', async () => {
    vi.mocked(api.fetchMfaStatus).mockResolvedValue({
      totp_enabled: false,
      passkeys_count: 1,
      recovery_codes_remaining: 10,
    });
    vi.mocked(api.enrollTotp).mockResolvedValue({
      provisioning_uri: 'otpauth://totp/mock',
      otpauth_url: 'otpauth://totp/mock',
      secret: 'SECRETKEY',
    });
    vi.mocked(api.confirmTotp).mockRejectedValue(new Error('Invalid TOTP verification code'));
    vi.mocked(api.deleteTotp).mockRejectedValue(new Error('Failed to disable TOTP'));
    vi.mocked(api.regenerateRecoveryCodes).mockRejectedValue(new Error('Regen error'));

    renderComponent();

    await waitFor(() => {
      expect(screen.getByTestId('enable-totp-btn')).toBeDefined();
    });

    // Enroll and confirm error
    fireEvent.click(screen.getByTestId('enable-totp-btn'));
    await waitFor(() => {
      expect(screen.getByTestId('confirm-totp-btn')).toBeDefined();
    });

    fireEvent.change(screen.getByTestId('totp-verification-input'), { target: { value: '000000' } });
    fireEvent.click(screen.getByTestId('confirm-totp-btn'));

    await waitFor(() => {
      expect(screen.getByTestId('alert-error').textContent).toContain('Invalid TOTP verification code');
    });

    // Test non-Error rejection fallback for confirmTotp
    vi.mocked(api.confirmTotp).mockRejectedValueOnce('raw string reject');
    fireEvent.click(screen.getByTestId('confirm-totp-btn'));
    await waitFor(() => {
      expect(screen.getByTestId('alert-error').textContent).toContain('Invalid TOTP code.');
    });

    // Regenerate recovery codes error
    vi.spyOn(window, 'confirm').mockReturnValueOnce(true);
    fireEvent.click(screen.getByTestId('regenerate-recovery-codes-btn'));

    await waitFor(() => {
      expect(screen.getByTestId('alert-error').textContent).toContain('Regen error');
    });
  });

  it('silently ignores Aal2StepUpCancelledError on sensitive actions', async () => {
    vi.mocked(api.deletePasskey).mockRejectedValueOnce(new Aal2StepUpCancelledError());

    vi.spyOn(window, 'confirm').mockReturnValue(true);

    renderComponent();

    await waitFor(() => {
      expect(screen.getByTestId('delete-passkey-pk-1')).toBeDefined();
    });

    fireEvent.click(screen.getByTestId('delete-passkey-pk-1'));

    await waitFor(() => {
      expect(api.deletePasskey).toHaveBeenCalledWith('pk-1');
    });

    expect(screen.queryByTestId('alert-error')).toBeNull();
    expect(screen.queryByTestId('aal2-stepup-dialog')).toBeNull();
  });

  it('handles SVG avatar rejection and empty avatar file selection', async () => {
    renderComponent();

    await waitFor(() => {
      expect(screen.getByTestId('avatar-file-input')).toBeDefined();
    });

    const fileInput = screen.getByTestId('avatar-file-input');

    // Empty file selection
    fireEvent.change(fileInput, { target: { files: [] } });

    // SVG rejection by mime type
    const svgFile = new File(['<svg></svg>'], 'avatar.svg', { type: 'image/svg+xml' });
    fireEvent.change(fileInput, { target: { files: [svgFile] } });

    await waitFor(() => {
      expect(screen.getByTestId('alert-error').textContent).toContain('SVG avatars are rejected');
    });

    // SVG rejection by extension
    const svgByName = new File(['binary'], 'malicious.SVG', { type: 'image/png' });
    fireEvent.change(fileInput, { target: { files: [svgByName] } });

    await waitFor(() => {
      expect(screen.getByTestId('alert-error').textContent).toContain('SVG avatars are rejected');
    });
  });

  it('handles passkey rename and confirmation cancellations', async () => {
    vi.mocked(api.fetchPasskeys).mockResolvedValue([
      {
        id: 'pk-unnamed',
        nickname: '',
        created_at: '2026-01-01T00:00:00Z',
        last_used_at: null,
        aaguid: '00000000-0000-0000-0000-000000000000',
      },
    ]);
    vi.mocked(api.renamePasskey).mockResolvedValue({
      id: 'pk-unnamed',
      nickname: 'YubiKey 5',
      created_at: '2026-01-01T00:00:00Z',
      last_used_at: null,
      aaguid: '00000000-0000-0000-0000-000000000000',
    });

    renderComponent();

    // Check fallback label and Never date
    await waitFor(() => {
      expect(screen.getByText('Passkey')).toBeDefined();
      expect(screen.getByText('Never')).toBeDefined();
    });

    // Rename passkey
    fireEvent.click(screen.getByTestId('rename-passkey-pk-unnamed'));
    expect(screen.getByTestId('passkey-nickname-input')).toBeDefined();

    fireEvent.change(screen.getByTestId('passkey-nickname-input'), { target: { value: 'YubiKey 5' } });
    fireEvent.click(screen.getByTestId('save-passkey-nickname-btn'));

    await waitFor(() => {
      expect(api.renamePasskey).toHaveBeenCalledWith('pk-unnamed', 'YubiKey 5');
    });

    // Window confirm cancel paths
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false);
    fireEvent.click(screen.getByTestId('delete-passkey-pk-unnamed'));
    expect(api.deletePasskey).not.toHaveBeenCalled();

    fireEvent.click(screen.getByTestId('disable-totp-btn'));
    expect(api.deleteTotp).not.toHaveBeenCalled();

    fireEvent.click(screen.getByTestId('regenerate-recovery-codes-btn'));
    expect(api.regenerateRecoveryCodes).not.toHaveBeenCalled();
    confirmSpy.mockRestore();
  });

  it('handles non-Error string rejection in password update and passkey rename', async () => {
    vi.mocked(api.changePassword).mockRejectedValue('Forbidden string reject');
    vi.mocked(api.renamePasskey).mockRejectedValue('Rename string reject');

    renderComponent();

    await waitFor(() => {
      expect(screen.getByTestId('new-password-input')).toBeDefined();
    });

    fireEvent.change(screen.getByTestId('current-password-input'), { target: { value: 'OldPassword123!' } });
    fireEvent.change(screen.getByTestId('new-password-input'), { target: { value: 'NewPassword12345!' } });
    fireEvent.change(screen.getByTestId('confirm-password-input'), { target: { value: 'NewPassword12345!' } });
    fireEvent.click(screen.getByTestId('change-password-btn'));

    await waitFor(() => {
      expect(screen.getByTestId('alert-error').textContent).toContain('Failed to change password.');
    });

    // Rename passkey error
    fireEvent.click(screen.getByTestId('rename-passkey-pk-1'));
    fireEvent.click(screen.getByTestId('save-passkey-nickname-btn'));

    await waitFor(() => {
      expect(screen.getByTestId('alert-error').textContent).toContain('Failed to rename passkey.');
    });
  });

  it('covers AAL2 intercept and non-Error fallback errors for delete passkey, TOTP enroll/delete, and recovery regen', async () => {
    vi.mocked(api.fetchMfaStatus).mockResolvedValue({
      totp_enabled: true,
      passkeys_count: 1,
      recovery_codes_remaining: 10,
    });

    vi.mocked(api.deletePasskey).mockRejectedValueOnce(new Aal2StepUpCancelledError());
    vi.mocked(api.deleteTotp).mockRejectedValueOnce(new Aal2StepUpCancelledError());
    vi.mocked(api.regenerateRecoveryCodes).mockRejectedValueOnce(new Aal2StepUpCancelledError());

    renderComponent();

    await waitFor(() => {
      expect(screen.getByTestId('delete-passkey-pk-1')).toBeDefined();
    });

    vi.spyOn(window, 'confirm').mockReturnValue(true);

    // 1. Delete passkey triggers AAL2 cancellation silently
    fireEvent.click(screen.getByTestId('delete-passkey-pk-1'));
    await waitFor(() => {
      expect(api.deletePasskey).toHaveBeenCalledTimes(1);
    });
    expect(screen.queryByTestId('alert-error')).toBeNull();

    // Delete passkey string error fallback
    vi.mocked(api.deletePasskey).mockRejectedValueOnce('String delete passkey failure');
    fireEvent.click(screen.getByTestId('delete-passkey-pk-1'));
    await waitFor(() => {
      expect(screen.getByTestId('alert-error').textContent).toContain('Failed to delete passkey.');
    });

    // 2. Disable TOTP triggers AAL2 cancellation silently
    fireEvent.click(screen.getByTestId('disable-totp-btn'));
    await waitFor(() => {
      expect(api.deleteTotp).toHaveBeenCalledTimes(1);
    });

    // Disable TOTP string error fallback
    vi.mocked(api.deleteTotp).mockRejectedValueOnce('String delete totp failure');
    fireEvent.click(screen.getByTestId('disable-totp-btn'));
    await waitFor(() => {
      expect(screen.getByTestId('alert-error').textContent).toContain('Failed to disable TOTP.');
    });

    // 3. Regenerate recovery codes triggers AAL2 cancellation silently
    fireEvent.click(screen.getByTestId('regenerate-recovery-codes-btn'));
    await waitFor(() => {
      expect(api.regenerateRecoveryCodes).toHaveBeenCalledTimes(1);
    });

    // Regenerate recovery codes string error fallback
    vi.mocked(api.regenerateRecoveryCodes).mockRejectedValueOnce('String regen codes failure');
    fireEvent.click(screen.getByTestId('regenerate-recovery-codes-btn'));
    await waitFor(() => {
      expect(screen.getByTestId('alert-error').textContent).toContain('Failed to regenerate recovery codes.');
    });
  });

  it('covers string error on enroll TOTP when totp is disabled', async () => {
    vi.mocked(api.fetchMfaStatus).mockResolvedValue({
      totp_enabled: false,
      passkeys_count: 1,
      recovery_codes_remaining: 10,
    });

    vi.mocked(api.enrollTotp).mockRejectedValue('String enroll totp failure');

    renderComponent();

    const enableTotpBtn = await screen.findByTestId('enable-totp-btn');
    fireEvent.click(enableTotpBtn);

    await waitFor(() => {
      expect(screen.getByTestId('alert-error').textContent).toContain('Failed to initiate TOTP setup.');
    });
  });

  it('covers non-Error string rejection on avatar upload/delete and profile update', async () => {
    vi.mocked(api.updateMyProfile).mockRejectedValue('String profile update reject');
    vi.mocked(api.uploadAvatar).mockRejectedValue('String upload avatar reject');
    vi.mocked(api.deleteAvatar).mockRejectedValue('String delete avatar reject');

    renderComponent();

    await waitFor(() => {
      expect(screen.getByTestId('save-profile-btn')).toBeDefined();
    });

    fireEvent.click(screen.getByTestId('save-profile-btn'));
    await waitFor(() => {
      expect(screen.getByTestId('alert-error').textContent).toContain('Failed to update profile.');
    });

    fireEvent.click(screen.getByTestId('remove-avatar-btn'));
    await waitFor(() => {
      expect(screen.getByTestId('alert-error').textContent).toContain('Failed to delete avatar.');
    });

    const file = new File(['valid content'], 'pic.png', { type: 'image/png' });
    fireEvent.change(screen.getByTestId('avatar-file-input'), { target: { files: [file] } });
    await waitFor(() => {
      expect(screen.getByTestId('avatar-crop-modal')).toBeDefined();
    });
    fireEvent.click(screen.getByTestId('avatar-crop-save-btn'));
    await waitFor(() => {
      expect(screen.getByTestId('alert-error').textContent).toContain('Failed to upload avatar.');
    });
  });

  it('covers window.confirm cancellation on disable TOTP, regenerate recovery codes, and delete passkey', async () => {
    const localClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false);

    render(
      <MemoryRouter>
        <QueryClientProvider client={localClient}>
          <PersonalSettingsPage />
        </QueryClientProvider>
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('disable-totp-btn')).toBeDefined();
      expect(screen.getByTestId('delete-passkey-pk-1')).toBeDefined();
    });

    fireEvent.click(screen.getByTestId('disable-totp-btn'));
    expect(api.deleteTotp).not.toHaveBeenCalled();

    fireEvent.click(screen.getByTestId('regenerate-recovery-codes-btn'));
    expect(api.regenerateRecoveryCodes).not.toHaveBeenCalled();

    fireEvent.click(screen.getByTestId('delete-passkey-pk-1'));
    expect(api.deletePasskey).not.toHaveBeenCalled();

    confirmSpy.mockRestore();
  });

  it('covers otpauth_url fallback and confirmTotp with empty recovery codes', async () => {
    const localClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    vi.mocked(api.fetchMfaStatus).mockResolvedValue({
      totp_enabled: false,
      passkeys_count: 1,
      recovery_codes_remaining: 0,
    });
    vi.mocked(api.enrollTotp).mockResolvedValue({
      otpauth_url: 'otpauth://totp/kanban:alice?secret=TESTSECRET',
      secret: 'TESTSECRET',
    });
    vi.mocked(api.confirmTotp).mockResolvedValue({
      ok: true,
      recovery_codes: [],
    });

    render(
      <MemoryRouter>
        <QueryClientProvider client={localClient}>
          <PersonalSettingsPage />
        </QueryClientProvider>
      </MemoryRouter>,
    );

    const enableTotpBtn = await screen.findByTestId('enable-totp-btn');
    fireEvent.click(enableTotpBtn);

    await waitFor(() => {
      expect(screen.getByTestId('totp-secret-key').textContent).toContain('TESTSECRET');
    });

    const codeInput = screen.getByTestId('totp-verification-input');
    fireEvent.change(codeInput, { target: { value: '123456' } });
    fireEvent.click(screen.getByTestId('confirm-totp-btn'));

    await waitFor(() => {
      expect(screen.getByTestId('alert-success').textContent).toContain('Two-factor authentication enabled successfully.');
    });
  });

  it('covers Aal2StepUpCancelledError on enrollTotp, plus rename and confirm string errors', async () => {
    const localClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });

    vi.mocked(api.fetchMfaStatus).mockResolvedValue({
      totp_enabled: false,
      passkeys_count: 1,
      recovery_codes_remaining: 10,
    });
    vi.mocked(api.enrollTotp).mockRejectedValue(new Aal2StepUpCancelledError());
    vi.mocked(api.confirmTotp).mockRejectedValue('String TOTP reject');
    vi.mocked(api.renamePasskey).mockRejectedValue('String rename reject');

    render(
      <MemoryRouter>
        <QueryClientProvider client={localClient}>
          <PersonalSettingsPage />
        </QueryClientProvider>
      </MemoryRouter>,
    );

    const enableTotpBtn = await screen.findByTestId('enable-totp-btn');
    fireEvent.click(enableTotpBtn);

    await waitFor(() => {
      expect(api.enrollTotp).toHaveBeenCalled();
    });
    expect(screen.queryByTestId('alert-error')).toBeNull();

    // Rename passkey string rejection
    await waitFor(() => {
      expect(screen.getByTestId('rename-passkey-pk-1')).toBeDefined();
    });
    const renameBtn = screen.getByTestId('rename-passkey-pk-1');
    fireEvent.click(renameBtn);

    const nicknameInput = screen.getByTestId('passkey-nickname-input');
    fireEvent.change(nicknameInput, { target: { value: 'New Key Name' } });
    fireEvent.click(screen.getByTestId('save-passkey-nickname-btn'));

    await waitFor(() => {
      expect(screen.getByTestId('alert-error').textContent).toContain('Failed to rename passkey.');
    });
  });

  it('renders linked external identities and handles unlinking with confirm', async () => {
    const mockIdentities: api.ExternalIdentityItem[] = [
      {
        id: 'ident-1',
        card_slug: 'github-corp',
        card_display_name: 'GitHub Enterprise',
        provider_kind: 'oauth2',
        immutable_subject_id: 'gh-123',
        subject_email_at_link: 'jane@github.example',
        created_at: '2026-01-15T00:00:00Z',
        last_login_at: '2026-01-15T00:00:00Z',
      },
    ];
    vi.mocked(api.fetchExternalIdentities).mockResolvedValue(mockIdentities);
    vi.mocked(api.unlinkIdentity).mockResolvedValue(undefined);
    vi.spyOn(window, 'confirm').mockReturnValue(true);

    renderComponent();

    await waitFor(() => {
      expect(screen.getByTestId('identity-row-ident-1')).toBeDefined();
      expect(screen.getByText('github-corp')).toBeDefined();
      expect(screen.getByText('(OAUTH2)')).toBeDefined();
      expect(screen.getByText('jane@github.example')).toBeDefined();
    });

    const unlinkBtn = screen.getByTestId('unlink-identity-ident-1');
    fireEvent.click(unlinkBtn);

    await waitFor(() => {
      expect(api.unlinkIdentity).toHaveBeenCalledWith('ident-1');
      expect(screen.getByTestId('alert-success').textContent).toContain('Account unlinked.');
    });
  });

  it('cancels unlinking identity when confirm is false and handles unlink error', async () => {
    const mockIdentities: api.ExternalIdentityItem[] = [
      {
        id: 'ident-2',
        card_slug: 'google',
        card_display_name: null,
        provider_kind: 'oidc',
        immutable_subject_id: 'g-456',
        subject_email_at_link: null,
        created_at: '2026-02-01T00:00:00Z',
        last_login_at: '2026-02-01T00:00:00Z',
      },
    ];
    vi.mocked(api.fetchExternalIdentities).mockResolvedValue(mockIdentities);
    vi.mocked(api.unlinkIdentity).mockRejectedValue(new Error('Cannot unlink'));
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false);

    renderComponent();

    await waitFor(() => {
      expect(screen.getByTestId('identity-row-ident-2')).toBeDefined();
      expect(screen.getByText('google')).toBeDefined();
      expect(screen.getByText('(OIDC)')).toBeDefined();
      expect(screen.getByText('g-456')).toBeDefined();
    });

    fireEvent.click(screen.getByTestId('unlink-identity-ident-2'));
    expect(api.unlinkIdentity).not.toHaveBeenCalled();

    confirmSpy.mockReturnValue(true);
    fireEvent.click(screen.getByTestId('unlink-identity-ident-2'));

    await waitFor(() => {
      expect(screen.getByTestId('alert-error').textContent).toContain('Cannot unlink');
    });

    vi.mocked(api.unlinkIdentity).mockRejectedValue('non-error failure');
    fireEvent.click(screen.getByTestId('unlink-identity-ident-2'));
    await waitFor(() => {
      expect(screen.getByTestId('alert-error').textContent).toContain('Failed to unlink identity.');
    });

    vi.mocked(api.unlinkIdentity).mockRejectedValue(new Aal2StepUpCancelledError());
    fireEvent.click(screen.getByTestId('unlink-identity-ident-2'));
    await waitFor(() => {
      expect(api.unlinkIdentity).toHaveBeenCalled();
    });
  });

  it('safely handles external identity with undefined provider_kind and created_at without crashing', async () => {
    const mockIdentities: api.ExternalIdentityItem[] = [
      {
        id: 'ident-3',
        card_slug: 'custom-card',
        card_display_name: null,
        provider_kind: undefined as unknown as string,
        immutable_subject_id: null,
        subject_email_at_link: null,
        created_at: null as unknown as string,
      },
    ];
    vi.mocked(api.fetchExternalIdentities).mockResolvedValue(mockIdentities);

    renderComponent();

    await waitFor(() => {
      expect(screen.getByTestId('identity-row-ident-3')).toBeDefined();
      expect(screen.getByText('custom-card')).toBeDefined();
      expect(screen.getByText('N/A')).toBeDefined();
      expect(screen.getByText('Unknown')).toBeDefined();
    });
  });

  it('covers show/hide password toggle and TOTP setup modal cancel', async () => {
    vi.mocked(api.fetchMfaStatus).mockResolvedValue({
      totp_enabled: false,
      passkeys_count: 0,
      recovery_codes_remaining: 0,
    });
    vi.mocked(api.enrollTotp).mockResolvedValue({
      secret: 'ABCDEF',
      otpauth_url: 'otpauth://totp/test',
    });

    renderComponent();

    await waitFor(() => {
      expect(screen.getByTestId('personal-settings-page')).toBeDefined();
    });

    // Toggle current password and new password visibility
    const toggleBtns = screen.getAllByRole('button', { name: /Show password/i });
    if (toggleBtns[0]) {
      fireEvent.click(toggleBtns[0]);
      fireEvent.click(toggleBtns[0]);
    }
    if (toggleBtns[1]) {
      fireEvent.click(toggleBtns[1]);
      fireEvent.click(toggleBtns[1]);
    }

    // Open and cancel TOTP modal
    const enableTotpBtn = screen.getByTestId('enable-totp-btn');
    fireEvent.click(enableTotpBtn);
    await waitFor(() => {
      expect(screen.getByTestId('confirm-totp-btn')).toBeDefined();
    });
    const cancelBtns = screen.getAllByRole('button', { name: 'Cancel' });
    if (cancelBtns[0]) fireEvent.click(cancelBtns[0]);
    expect(screen.queryByTestId('confirm-totp-btn')).toBeNull();

    // Reopen and cancel via footer cancel button
    fireEvent.click(enableTotpBtn);
    await waitFor(() => {
      expect(screen.getByTestId('confirm-totp-btn')).toBeDefined();
    });
    const cancelBtns2 = screen.getAllByRole('button', { name: 'Cancel' });
    if (cancelBtns2[1]) fireEvent.click(cancelBtns2[1]);
    expect(screen.queryByTestId('confirm-totp-btn')).toBeNull();
  });

  it('covers passkey rename non-Error, passkey delete cancel, and avatar non-Error rejections', async () => {
    vi.mocked(api.fetchMfaStatus).mockResolvedValue(mockMfaStatus);
    vi.mocked(api.fetchPasskeys).mockResolvedValue(mockPasskeys);
    vi.mocked(api.renamePasskey).mockRejectedValue('raw-rename-error');
    vi.mocked(api.deletePasskey).mockRejectedValue('raw-delete-error');
    vi.mocked(api.deleteAvatar).mockRejectedValue('raw-avatar-delete-error');

    const confirmSpy = vi.spyOn(window, 'confirm');

    renderComponent();

    await waitFor(() => {
      expect(screen.getByTestId('personal-settings-page')).toBeDefined();
    });

    // Rename passkey with non-Error rejection
    const renameBtn = screen.getByTestId(`rename-passkey-${mockPasskeys[0]?.id ?? ''}`);
    fireEvent.click(renameBtn);

    const submitRenameBtn = screen.getByTestId('save-passkey-nickname-btn');
    fireEvent.click(submitRenameBtn);

    await waitFor(() => {
      expect(screen.getByTestId('alert-error').textContent).toContain('Failed to rename passkey.');
    });

    // Delete passkey cancel
    confirmSpy.mockReturnValue(false);
    const deletePasskeyBtn = screen.getByTestId(`delete-passkey-${mockPasskeys[0]?.id ?? ''}`);
    fireEvent.click(deletePasskeyBtn);
    expect(api.deletePasskey).not.toHaveBeenCalled();

    // Delete passkey confirm with non-Error rejection
    confirmSpy.mockReturnValue(true);
    fireEvent.click(deletePasskeyBtn);
    await waitFor(() => {
      expect(screen.getByTestId('alert-error').textContent).toContain('Failed to delete passkey.');
    });

    // Delete avatar with non-Error rejection
    const deleteAvatarBtn = screen.getByTestId('remove-avatar-btn');
    fireEvent.click(deleteAvatarBtn);
    await waitFor(() => {
      expect(screen.getByTestId('alert-error').textContent).toContain('Failed to delete avatar.');
    });

    // Dismiss error alert
    const dismissBtn = screen.getByText('Dismiss');
    fireEvent.click(dismissBtn);
    expect(screen.queryByTestId('alert-error')).toBeNull();
  });

  it('renders fallback U initial when profile display_name and username are null', async () => {
    vi.mocked(api.fetchMyProfile).mockResolvedValue({
      ...mockProfile,
      avatar_url: null,
      display_name: null as unknown as string,
      username: null as unknown as string,
    });

    const { unmount } = renderComponent();

    await waitFor(() => {
      expect(screen.getByText('U')).toBeDefined();
    });
    unmount();

    // Fallback to username initial
    queryClient.clear();
    vi.mocked(api.fetchMyProfile).mockResolvedValue({
      ...mockProfile,
      avatar_url: null,
      display_name: null as unknown as string,
      username: 'alice',
    });
    const render2 = renderComponent();
    await waitFor(() => {
      expect(screen.getByText('A')).toBeDefined();
    });
    render2.unmount();

    // Empty strings fallback
    queryClient.clear();
    vi.mocked(api.fetchMyProfile).mockResolvedValue({
      ...mockProfile,
      avatar_url: null,
      display_name: '',
      username: '',
    });
    renderComponent();
    await waitFor(() => {
      expect(screen.getByTestId('avatar-preview')).toBeDefined();
    });
  });

  it('covers non-Error fallback branches for TOTP, recovery codes, and passkey operations', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    vi.mocked(api.deleteTotp).mockRejectedValue('String reject');
    vi.mocked(api.regenerateRecoveryCodes).mockRejectedValue('String reject');
    vi.mocked(api.deletePasskey).mockRejectedValue('String reject');
    vi.mocked(api.renamePasskey).mockRejectedValue('String reject');

    renderComponent();

    await waitFor(() => {
      expect(screen.getByTestId('disable-totp-btn')).toBeDefined();
    });

    // 1. Empty files on avatar input (hits if (!file) return)
    fireEvent.change(screen.getByTestId('avatar-file-input'), { target: { files: [] } });

    // 2. Disable TOTP non-Error rejection
    fireEvent.click(screen.getByTestId('disable-totp-btn'));
    await waitFor(() => {
      expect(screen.getByTestId('alert-error').textContent).toContain('Failed to disable TOTP.');
    });

    // 3. Regenerate recovery codes non-Error rejection
    fireEvent.click(screen.getByTestId('regenerate-recovery-codes-btn'));
    await waitFor(() => {
      expect(screen.getByTestId('alert-error').textContent).toContain('Failed to regenerate recovery codes.');
    });

    // 4. Delete passkey non-Error rejection
    fireEvent.click(screen.getByTestId('delete-passkey-pk-1'));
    await waitFor(() => {
      expect(screen.getByTestId('alert-error').textContent).toContain('Failed to delete passkey.');
    });

    // 5. Rename passkey non-Error rejection
    fireEvent.click(screen.getByTestId('rename-passkey-pk-1'));
    fireEvent.change(screen.getByTestId('passkey-nickname-input'), { target: { value: 'New Name' } });
    fireEvent.click(screen.getByTestId('save-passkey-nickname-btn'));
    await waitFor(() => {
      expect(screen.getByTestId('alert-error').textContent).toContain('Failed to rename passkey.');
    });
  });

  it('covers TOTP enroll/confirm/delete errors, passkey rename/delete errors, and avatar upload error', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    vi.mocked(api.fetchMfaStatus).mockResolvedValue({
      totp_enabled: false,
      passkeys_count: 1,
      recovery_codes_remaining: 10,
    });

    renderComponent();

    await waitFor(() => {
      expect(screen.getByTestId('enable-totp-btn')).toBeDefined();
    });

    // 1. enrollTotp error
    vi.mocked(api.enrollTotp).mockRejectedValueOnce(new Error('TOTP setup error'));
    fireEvent.click(screen.getByTestId('enable-totp-btn'));
    await waitFor(() => {
      expect(screen.getByText('TOTP setup error')).toBeDefined();
    });

    // 2. confirmTotp error
    vi.mocked(api.enrollTotp).mockResolvedValueOnce({
      secret: 'SECRET123',
      provisioning_uri: 'otpauth://totp/test',
    });
    vi.mocked(api.confirmTotp).mockRejectedValueOnce(new Error('Invalid TOTP code.'));
    fireEvent.click(screen.getByTestId('enable-totp-btn'));
    await waitFor(() => {
      expect(screen.getByTestId('totp-verification-input')).toBeDefined();
    });
    fireEvent.change(screen.getByTestId('totp-verification-input'), { target: { value: '000000' } });
    fireEvent.click(screen.getByTestId('confirm-totp-btn'));
    await waitFor(() => {
      expect(screen.getByText('Invalid TOTP code.')).toBeDefined();
    });

    // 3. deleteTotp error
    vi.mocked(api.deleteTotp).mockRejectedValueOnce(new Error('Failed to disable TOTP.'));
    const disableTotpBtn = screen.queryByTestId('disable-totp-btn');
    if (disableTotpBtn) {
      fireEvent.click(disableTotpBtn);
      await waitFor(() => {
        expect(screen.getByText('Failed to disable TOTP.')).toBeDefined();
      });
    }

    // 4. renamePasskey error
    const renamePasskeyBtn = screen.getByTestId('rename-passkey-pk-1');
    vi.mocked(api.renamePasskey).mockRejectedValueOnce(new Error('Failed to rename passkey.'));
    fireEvent.click(renamePasskeyBtn);
    const saveNicknameBtn = screen.getByTestId('save-passkey-nickname-btn');
    fireEvent.click(saveNicknameBtn);
    await waitFor(() => {
      expect(screen.getByTestId('alert-error').textContent).toContain('Failed to rename passkey.');
    });

    // 5. deletePasskey error
    const deletePasskeyBtn = screen.getByTestId('delete-passkey-pk-1');
    vi.mocked(api.deletePasskey).mockRejectedValueOnce(new Error('Failed to delete passkey.'));
    fireEvent.click(deletePasskeyBtn);
    await waitFor(() => {
      expect(screen.getByTestId('alert-error').textContent).toContain('Failed to delete passkey.');
    });
  });

  it('silently ignores Aal2StepUpCancelledError on regenerateRecoveryCodes', async () => {
    vi.mocked(api.fetchMfaStatus).mockResolvedValue({
      totp_enabled: true,
      passkeys_count: 1,
      recovery_codes_remaining: 10,
    });
    vi.mocked(api.regenerateRecoveryCodes).mockRejectedValueOnce(new Aal2StepUpCancelledError());

    renderComponent();
    await waitFor(() => {
      expect(screen.getByTestId('regenerate-recovery-codes-btn')).toBeDefined();
    });

    fireEvent.click(screen.getByTestId('regenerate-recovery-codes-btn'));
    await waitFor(() => {
      expect(api.regenerateRecoveryCodes).toHaveBeenCalled();
    });
    expect(screen.queryByTestId('alert-error')).toBeNull();
  });

  it('covers passkey-only 2FA with undefined recovery codes count', async () => {
    vi.mocked(api.fetchMfaStatus).mockResolvedValue({
      totp_enabled: false,
      passkeys_count: 1,
      recovery_codes_remaining: undefined as unknown as number,
    });
    vi.mocked(api.fetchPasskeys).mockResolvedValue(mockPasskeys);

    renderComponent();
    await waitFor(() => {
      expect(screen.getByTestId('mfa-status-recovery-count').textContent).toBe('0');
      expect(screen.getByTestId('enable-totp-btn')).toBeDefined();
    });
    const regenBtn = screen.getByTestId('regenerate-recovery-codes-btn');
    expect(regenBtn.hasAttribute('disabled')).toBe(false);
    expect(regenBtn.getAttribute('title')).toBeNull();
  });

  it('handles copyToClipboard failure when copying recovery codes', async () => {
    const clipboard = await import('../../../utils/clipboard');
    vi.spyOn(clipboard, 'copyToClipboard').mockResolvedValue(false);
    vi.mocked(api.regenerateRecoveryCodes).mockResolvedValue({
      recovery_codes: ['REC-1', 'REC-2'],
    });

    renderComponent();
    await waitFor(() => {
      expect(screen.getByTestId('regenerate-recovery-codes-btn')).toBeDefined();
    });

    fireEvent.click(screen.getByTestId('regenerate-recovery-codes-btn'));
    await waitFor(() => {
      expect(screen.getByTestId('copy-recovery-codes-btn')).toBeDefined();
    });

    fireEvent.click(screen.getByTestId('copy-recovery-codes-btn'));
    expect(screen.getByText('Copy Codes')).toBeDefined();
  });

  it('covers passkey with null nickname and zero-2fa state', async () => {
    const nullNickPasskeys: api.WebauthnCredentialItem[] = [
      {
        id: 'pk-null',
        nickname: null,
        created_at: '2026-01-01T00:00:00Z',
        last_used_at: '2026-01-02T00:00:00Z',
        aaguid: '00000000-0000-0000-0000-000000000000',
      },
    ];
    vi.mocked(api.fetchPasskeys).mockResolvedValue(nullNickPasskeys);
    vi.mocked(api.fetchMfaStatus).mockResolvedValue({
      totp_enabled: false,
      passkeys_count: 0,
      recovery_codes_remaining: 0,
    });

    const { unmount } = renderComponent();
    await waitFor(() => {
      expect(screen.getByTestId('rename-passkey-pk-null')).toBeDefined();
    });

    fireEvent.click(screen.getByTestId('rename-passkey-pk-null'));
    expect(screen.getByTestId<HTMLInputElement>('passkey-nickname-input').value).toBe('');
    unmount();

    // Zero-2fa state
    queryClient.clear();
    vi.mocked(api.fetchPasskeys).mockResolvedValue([]);
    renderComponent();
    await waitFor(() => {
      expect(screen.getByTestId('mfa-status-passkeys').textContent).toBe('Default 2FA');
      expect(screen.getByTestId('regenerate-hint')).toBeDefined();
    });
    const regenBtn = screen.getByTestId('regenerate-recovery-codes-btn');
    expect(regenBtn.getAttribute('title')).toBe('Enable TOTP or Passkey 2FA first');
  });

  it('preserves unsaved display_name and timezone input when avatar is uploaded and removed', async () => {
    vi.mocked(api.uploadAvatar).mockResolvedValue({
      ...mockProfile,
      avatar_url: '/api/v1/users/11111111-1111-4111-8111-111111111111/avatar?v=abcdef123456',
    });
    vi.mocked(api.deleteAvatar).mockResolvedValue({
      ...mockProfile,
      avatar_url: null,
    });

    renderComponent();

    await waitFor(() => {
      expect(screen.getByTestId('display-name-input')).toBeDefined();
    });

    const nameInput = screen.getByTestId<HTMLInputElement>('display-name-input');
    const tzSelect = screen.getByTestId<HTMLSelectElement>('timezone-select');

    // Type unsaved draft
    fireEvent.change(nameInput, { target: { value: 'Unsaved Draft Name' } });
    fireEvent.change(tzSelect, { target: { value: 'Asia/Tokyo' } });

    expect(nameInput.value).toBe('Unsaved Draft Name');
    expect(tzSelect.value).toBe('Asia/Tokyo');

    // Upload avatar via crop modal
    const file = new File(['valid content'], 'pic.png', { type: 'image/png' });
    fireEvent.change(screen.getByTestId('avatar-file-input'), { target: { files: [file] } });

    await waitFor(() => {
      expect(screen.getByTestId('avatar-crop-modal')).toBeDefined();
    });
    fireEvent.click(screen.getByTestId('avatar-crop-save-btn'));

    await waitFor(() => {
      expect(screen.getByTestId('alert-success').textContent).toContain('Avatar uploaded successfully.');
    });

    // Verify unsaved draft is preserved
    expect(nameInput.value).toBe('Unsaved Draft Name');
    expect(tzSelect.value).toBe('Asia/Tokyo');

    // Remove avatar
    fireEvent.click(screen.getByTestId('remove-avatar-btn'));
    await waitFor(() => {
      expect(screen.getByTestId('alert-success').textContent).toContain('Avatar removed.');
    });

    // Verify unsaved draft is still preserved
    expect(nameInput.value).toBe('Unsaved Draft Name');
    expect(tzSelect.value).toBe('Asia/Tokyo');
  });

  it('opens and closes AvatarCropModal without saving', async () => {
    renderComponent();
    await waitFor(() => {
      expect(screen.getByTestId('avatar-file-input')).toBeDefined();
    });

    const file = new File(['valid content'], 'pic.png', { type: 'image/png' });
    fireEvent.change(screen.getByTestId('avatar-file-input'), { target: { files: [file] } });

    await waitFor(() => {
      expect(screen.getByTestId('avatar-crop-modal')).toBeDefined();
    });

    fireEvent.click(screen.getByTestId('avatar-crop-cancel-btn'));
    expect(screen.queryByTestId('avatar-crop-modal')).toBeNull();
  });

  it('opens and closes AvatarLightboxModal when clicking avatar preview', async () => {
    vi.mocked(api.fetchMyProfile).mockResolvedValue({
      ...mockProfile,
      avatar_url: '/api/v1/users/11111111-1111-4111-8111-111111111111/avatar?v=123456789012',
    });

    renderComponent();
    await waitFor(() => {
      expect(screen.getByTestId('avatar-preview')).toBeDefined();
    });

    // Click avatar preview to open lightbox
    fireEvent.click(screen.getByTestId('avatar-preview'));

    await waitFor(() => {
      expect(screen.getByTestId('avatar-lightbox-modal')).toBeDefined();
    });

    // Close lightbox
    fireEvent.click(screen.getByTestId('avatar-lightbox-close-btn'));
    expect(screen.queryByTestId('avatar-lightbox-modal')).toBeNull();
  });

  it('renders default empty fallbacks when profile fields are null or empty', async () => {
    vi.mocked(api.fetchMyProfile).mockResolvedValue({
      ...mockProfile,
      display_name: null as unknown as string,
      timezone: null as unknown as string,
    });

    renderComponent();
    await waitFor(() => {
      expect(screen.getByTestId('display-name-input')).toBeDefined();
    });

    const displayInput = screen.getByTestId<HTMLInputElement>('display-name-input');
    expect(displayInput.value).toBe('');

    // Empty files does nothing
    fireEvent.change(screen.getByTestId('avatar-file-input'), { target: { files: [] } });

    // Selecting an SVG by type triggers rejection error
    const svgFile = new File(['<svg></svg>'], 'pic.svg', { type: 'image/svg+xml' });
    fireEvent.change(screen.getByTestId('avatar-file-input'), { target: { files: [svgFile] } });
    expect(screen.getByTestId('alert-error').textContent).toContain('SVG avatars are rejected for security.');

    // Selecting an SVG by extension with generic type
    const svgFile2 = new File(['<svg></svg>'], 'bad.SVG', { type: '' });
    fireEvent.change(screen.getByTestId('avatar-file-input'), { target: { files: [svgFile2] } });
    expect(screen.getByTestId('alert-error').textContent).toContain('SVG avatars are rejected for security.');
  });

  it('renders insecure context notice when isSecureContext is false and disables enrollment buttons', async () => {
    Object.defineProperty(window, 'isSecureContext', {
      writable: true,
      configurable: true,
      value: false,
    });

    renderComponent();
    await waitFor(() => {
      expect(screen.getByTestId('webauthn-insecure-context-notice')).toBeDefined();
    });

    const addPasskeyBtn = screen.getByTestId<HTMLButtonElement>('add-passkey-btn');
    const addFido2Btn = screen.getByTestId<HTMLButtonElement>('add-fido2-key-btn');
    expect(addPasskeyBtn.disabled).toBe(true);
    expect(addFido2Btn.disabled).toBe(true);
  });

  it('opens PasskeyEnrollModal when clicking Add Passkey or Add FIDO2 Security Key in secure context', async () => {
    Object.defineProperty(window, 'isSecureContext', {
      writable: true,
      configurable: true,
      value: true,
    });
    (window as unknown as { PublicKeyCredential?: unknown }).PublicKeyCredential = function () {
      return undefined;
    };
    Object.defineProperty(navigator, 'credentials', {
      writable: true,
      configurable: true,
      value: {
        get: vi.fn(),
        create: vi.fn(),
      },
    });

    renderComponent();
    await waitFor(() => {
      expect(screen.queryByTestId('webauthn-insecure-context-notice')).toBeNull();
    });

    const addPasskeyBtn = screen.getByTestId<HTMLButtonElement>('add-passkey-btn');
    expect(addPasskeyBtn.disabled).toBe(false);

    fireEvent.click(addPasskeyBtn);
    await waitFor(() => {
      expect(screen.getByTestId('passkey-enroll-modal')).toBeDefined();
    });

    // Close enroll modal
    fireEvent.click(screen.getByTestId('passkey-enroll-close-btn'));
    expect(screen.queryByTestId('passkey-enroll-modal')).toBeNull();

    // Click Add FIDO2 Key
    const addFido2Btn = screen.getByTestId<HTMLButtonElement>('add-fido2-key-btn');
    fireEvent.click(addFido2Btn);
    await waitFor(() => {
      expect(screen.getByTestId('passkey-enroll-modal')).toBeDefined();
    });
    const crossRadio = screen.getByTestId<HTMLInputElement>('attachment-cross-platform-radio');
    expect(crossRadio.checked).toBe(true);

    // Complete enrollment from modal to cover onSuccess in PersonalSettingsPage
    const mockRegOptions: api.PublicKeyCredentialCreationOptionsJSON = {
      rp: { name: 'KB' },
      user: { id: 'u1', name: 'u', displayName: 'U' },
      challenge: 'c1',
      pubKeyCredParams: [],
    };
    vi.mocked(api.fetchWebauthnRegistrationOptions).mockResolvedValueOnce(mockRegOptions);
    vi.mocked(api.verifyWebauthnRegistration).mockResolvedValueOnce({
      verified: true,
      credential_id: 'pk-new',
      nickname: 'New YubiKey',
    });
    const mockCreate = vi.fn().mockResolvedValueOnce({
      id: 'mock-reg-id',
      rawId: new Uint8Array([1]).buffer,
      type: 'public-key',
      response: {
        clientDataJSON: new TextEncoder().encode('{}').buffer,
        attestationObject: new Uint8Array([2]).buffer,
      },
      getClientExtensionResults: () => ({}),
    });
    Object.defineProperty(navigator, 'credentials', {
      writable: true,
      configurable: true,
      value: { create: mockCreate, get: vi.fn() },
    });

    fireEvent.change(screen.getByTestId('passkey-enroll-nickname-input'), {
      target: { value: 'New YubiKey' },
    });
    fireEvent.click(screen.getByTestId('passkey-enroll-submit-btn'));

    await waitFor(() => {
      expect(screen.getByTestId('alert-success').textContent).toContain('Passkey registered successfully.');
    });
  });

  it('renders device badges and clone warning pill in passkeys table', async () => {
    vi.mocked(api.fetchPasskeys).mockResolvedValueOnce([
      {
        id: 'pk-internal',
        nickname: 'Mac Touch ID',
        transports: ['internal'],
        created_at: '2026-01-01T00:00:00Z',
        last_used_at: '2026-02-01T00:00:00Z',
        aaguid: '00000000-0000-0000-0000-000000000000',
      },
      {
        id: 'pk-usb',
        nickname: 'YubiKey 5C',
        transports: ['usb', 'nfc'],
        created_at: '2026-01-02T00:00:00Z',
        last_used_at: null,
        aaguid: null,
      },
      {
        id: 'pk-cloned',
        nickname: 'Suspicious Key',
        transports: ['hybrid'],
        suspect_clone_at: '2026-03-01T12:00:00Z',
        created_at: '2026-01-03T00:00:00Z',
        last_used_at: '2026-03-01T12:00:00Z',
        aaguid: null,
      },
    ]);

    renderComponent();
    await waitFor(() => {
      expect(screen.getByTestId('passkey-row-pk-internal')).toBeDefined();
    });

    expect(screen.getByTestId('passkey-badge-pk-internal').textContent).toContain('📱 Passkey');
    expect(screen.getByTestId('passkey-badge-pk-usb').textContent).toContain('🔑 FIDO2 Security Key');
    expect(screen.getByTestId('passkey-badge-pk-cloned').textContent).toContain('📱 Passkey');
    expect(screen.getByTestId('passkey-clone-warning-pk-cloned')).toBeDefined();
    expect(screen.getByTestId('passkey-clone-warning-pk-cloned').textContent).toContain('⚠️ Suspected Clone');
  });

  it('handles Test Key button execution and shows verified banner', async () => {
    const mockAuthOptions: api.PublicKeyCredentialRequestOptionsJSON = { challenge: 'chall-auth', rpId: 'localhost' };
    const mockAssertion = {
      id: 'cred-1',
      rawId: new Uint8Array([1, 2]).buffer,
      type: 'public-key',
      response: {
        clientDataJSON: new TextEncoder().encode('{}').buffer,
        authenticatorData: new Uint8Array([3]).buffer,
        signature: new Uint8Array([4]).buffer,
        userHandle: null,
      },
      getClientExtensionResults: () => ({}),
    } as unknown as PublicKeyCredential;

    vi.mocked(api.fetchWebauthnAuthenticationOptions).mockResolvedValueOnce(mockAuthOptions);
    vi.mocked(api.verifyWebauthnAuthentication).mockResolvedValueOnce({ verified: true, credential_id: 'pk-1', aal_level: 2 });

    const mockGet = vi.fn().mockResolvedValue(mockAssertion);
    Object.defineProperty(navigator, 'credentials', {
      writable: true,
      configurable: true,
      value: {
        get: mockGet,
        create: vi.fn(),
      },
    });

    renderComponent();
    await waitFor(() => {
      expect(screen.getByTestId('test-passkey-pk-1')).toBeDefined();
    });

    fireEvent.click(screen.getByTestId('test-passkey-pk-1'));

    await waitFor(() => {
      expect(api.fetchWebauthnAuthenticationOptions).toHaveBeenCalled();
      expect(mockGet).toHaveBeenCalled();
      expect(api.verifyWebauthnAuthentication).toHaveBeenCalled();
      expect(screen.getByTestId('alert-success').textContent).toContain('👍 Key verified');
      expect(screen.getByTestId('passkey-verified-banner').textContent).toContain('👍 Key verified (MacBook TouchID)');
    });

    // Dismiss the inline section-level banner
    const bannerDismissBtn = screen.getByTestId('passkey-verified-banner').querySelector('button');
    expect(bannerDismissBtn).not.toBeNull();
    if (bannerDismissBtn) {
      fireEvent.click(bannerDismissBtn);
    }
    expect(screen.queryByTestId('passkey-verified-banner')).toBeNull();
  });

  it('scopes allowCredentials to the clicked credential and handles credential mismatch', async () => {
    const mockMultiAuthOptions: api.PublicKeyCredentialRequestOptionsJSON = {
      challenge: 'Y2hhbGxlbmdlMQ',
      timeout: 60000,
      rpId: 'localhost',
      allowCredentials: [
        { id: 'pk-1', type: 'public-key' },
        { id: 'other-pk', type: 'public-key' },
      ],
    };

    const mockAssertion = {
      id: 'mock-key-id',
      type: 'public-key',
      response: {
        clientDataJSON: new TextEncoder().encode('{}').buffer,
        authenticatorData: new Uint8Array([3]).buffer,
        signature: new Uint8Array([4]).buffer,
        userHandle: null,
      },
      getClientExtensionResults: () => ({}),
    } as unknown as PublicKeyCredential;

    vi.mocked(api.fetchWebauthnAuthenticationOptions).mockResolvedValueOnce(mockMultiAuthOptions);
    vi.mocked(api.verifyWebauthnAuthentication).mockResolvedValueOnce({
      verified: true,
      credential_id: 'pk-1',
      aal_level: 2,
    });

    const mockGet = vi.fn().mockResolvedValue(mockAssertion);
    Object.defineProperty(navigator, 'credentials', {
      writable: true,
      configurable: true,
      value: { get: mockGet, create: vi.fn() },
    });

    renderComponent();
    await waitFor(() => {
      expect(screen.getByTestId('test-passkey-pk-1')).toBeDefined();
    });

    fireEvent.click(screen.getByTestId('test-passkey-pk-1'));

    await waitFor(() => {
      expect(mockGet).toHaveBeenCalled();
      const calls = mockGet.mock.calls as unknown[][];
      const requestArg = calls[0]?.[0] as CredentialRequestOptions | undefined;
      // Verify allowCredentials was filtered to only pk-1
      expect(requestArg?.publicKey?.allowCredentials).toHaveLength(1);
      expect(screen.getByTestId('passkey-verified-banner').textContent).toContain('👍 Key verified');
    });

    // When verification returns a different credential than the one tested
    vi.mocked(api.fetchWebauthnAuthenticationOptions).mockResolvedValueOnce(mockMultiAuthOptions);
    vi.mocked(api.verifyWebauthnAuthentication).mockResolvedValueOnce({
      verified: true,
      credential_id: 'different-pk-uuid',
      aal_level: 2,
    });

    fireEvent.click(screen.getByTestId('test-passkey-pk-1'));
    await waitFor(() => {
      expect(screen.getByTestId('alert-error').textContent).toContain(
        'A different credential responded than the one tested.',
      );
    });
  });

  it('renders clone warning with aria-label and responsive cell labels', async () => {
    const clonePasskey: api.WebauthnCredentialItem = {
      id: 'pk-clone',
      nickname: 'Cloned Key',
      created_at: '2026-01-01T00:00:00Z',
      last_used_at: null,
      aaguid: null,
      transports: ['usb'],
      suspect_clone_at: '2026-03-01T12:00:00Z',
    };

    vi.mocked(api.fetchPasskeys).mockResolvedValueOnce([clonePasskey]);

    renderComponent();
    await waitFor(() => {
      expect(screen.getByTestId('passkey-row-pk-clone')).toBeDefined();
    });

    const cloneWarning = screen.getByTestId('passkey-clone-warning-pk-clone');
    expect(cloneWarning.getAttribute('aria-label')).toBe('Suspected cloned credential');
    expect(cloneWarning.textContent).toContain('⚠️ Suspected Clone');

    const row = screen.getByTestId('passkey-row-pk-clone');
    const createdCell = row.querySelector('[data-label="Created"]');
    expect(createdCell).not.toBeNull();
    const lastUsedCell = row.querySelector('[data-label="Last Used"]');
    expect(lastUsedCell).not.toBeNull();
    expect(lastUsedCell?.textContent).toContain('Never');
  });

  it('handles Test Key cancellation and error conditions', async () => {
    // Null assertion returned
    const mockCancelOptions: api.PublicKeyCredentialRequestOptionsJSON = { challenge: 'c1' };
    vi.mocked(api.fetchWebauthnAuthenticationOptions).mockResolvedValueOnce(mockCancelOptions);
    Object.defineProperty(navigator, 'credentials', {
      writable: true,
      configurable: true,
      value: { get: vi.fn().mockResolvedValue(null) },
    });

    renderComponent();
    await waitFor(() => {
      expect(screen.getByTestId('test-passkey-pk-1')).toBeDefined();
    });

    fireEvent.click(screen.getByTestId('test-passkey-pk-1'));
    await waitFor(() => {
      expect(screen.getByTestId('alert-error').textContent).toContain('WebAuthn assertion was cancelled.');
    });

    // NotAllowedError
    const notAllowed = new Error('Cancelled');
    notAllowed.name = 'NotAllowedError';
    vi.mocked(api.fetchWebauthnAuthenticationOptions).mockRejectedValueOnce(notAllowed);

    fireEvent.click(screen.getByTestId('test-passkey-pk-1'));
    await waitFor(() => {
      expect(screen.getByTestId('alert-error').textContent).toContain('Key verification was cancelled or timed out.');
    });

    // ApiProblem error
    const problem = new ApiProblem(400, { detail: 'Custom key problem' });
    vi.mocked(api.fetchWebauthnAuthenticationOptions).mockRejectedValueOnce(problem);

    fireEvent.click(screen.getByTestId('test-passkey-pk-1'));
    await waitFor(() => {
      expect(screen.getByTestId('alert-error').textContent).toContain('Custom key problem');
    });

    // Generic Error with empty message fallback
    vi.mocked(api.fetchWebauthnAuthenticationOptions).mockRejectedValueOnce(new Error(''));

    fireEvent.click(screen.getByTestId('test-passkey-pk-1'));
    await waitFor(() => {
      expect(screen.getByTestId('alert-error').textContent).toContain('Key verification failed.');
    });

    // String throw
    vi.mocked(api.fetchWebauthnAuthenticationOptions).mockRejectedValueOnce('raw-key-err');

    fireEvent.click(screen.getByTestId('test-passkey-pk-1'));
    await waitFor(() => {
      expect(screen.getByTestId('alert-error').textContent).toContain('Key verification failed.');
    });
  });

  it('silently ignores Aal2StepUpCancelledError across sensitive actions', async () => {
    // 1. Password change with Aal2StepUpCancelledError
    vi.mocked(api.changePassword).mockRejectedValueOnce(new Aal2StepUpCancelledError());

    renderComponent();
    await waitFor(() => {
      expect(screen.getByTestId('current-password-input')).toBeDefined();
    });

    fireEvent.change(screen.getByTestId('current-password-input'), { target: { value: 'ValidPass123!long' } });
    fireEvent.change(screen.getByTestId('new-password-input'), { target: { value: 'ValidPass123!longer' } });
    fireEvent.change(screen.getByTestId('confirm-password-input'), { target: { value: 'ValidPass123!longer' } });

    fireEvent.click(screen.getByTestId('change-password-btn'));

    await waitFor(() => {
      expect(api.changePassword).toHaveBeenCalledTimes(1);
    });
    expect(screen.queryByTestId('alert-error')).toBeNull();

    // 2. Passkey delete with Aal2StepUpCancelledError
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    vi.mocked(api.deletePasskey).mockRejectedValueOnce(new Aal2StepUpCancelledError());

    fireEvent.click(screen.getByTestId('delete-passkey-pk-1'));
    await waitFor(() => {
      expect(api.deletePasskey).toHaveBeenCalledTimes(1);
    });
    expect(screen.queryByTestId('alert-error')).toBeNull();

    // 3. Test Key with Aal2StepUpCancelledError
    vi.mocked(api.fetchWebauthnAuthenticationOptions).mockRejectedValueOnce(new Aal2StepUpCancelledError());
    fireEvent.click(screen.getByTestId('test-passkey-pk-1'));
    await waitFor(() => {
      expect(api.fetchWebauthnAuthenticationOptions).toHaveBeenCalledTimes(1);
    });
    expect(screen.queryByTestId('alert-error')).toBeNull();

    confirmSpy.mockRestore();
  });

  describe('External Identity Linking (KAN-27)', () => {
    const mockAuthCards = {
      cards: [
        {
          id: 'card-gh',
          slug: 'github',
          provider_kind: 'OIDC' as const,
          display_name: 'GitHub OAuth',
          button_subtext: null,
          icon_preset: 'github',
        },
        {
          id: 'card-ldap',
          slug: 'corp-ldap',
          provider_kind: 'LDAP' as const,
          display_name: 'Corp LDAP',
          button_subtext: null,
          icon_preset: 'ldap',
        },
        {
          id: 'card-local',
          slug: 'local-admin',
          provider_kind: 'LOCAL_ADMIN' as const,
          display_name: 'Local Admin',
          button_subtext: null,
          icon_preset: 'local',
        },
      ],
    };

    it('renders + Connect buttons for enabled external cards and filters out LOCAL_ADMIN and already-linked cards', async () => {
      vi.mocked(authApi.fetchAuthCards).mockResolvedValue(mockAuthCards);
      vi.mocked(api.fetchExternalIdentities).mockResolvedValue([
        {
          id: 'ident-gh',
          card_slug: 'github',
          provider_kind: 'OIDC',
          immutable_subject_id: 'sub-gh',
          created_at: '2026-01-01T00:00:00Z',
        },
      ]);

      renderComponent();

      await waitFor(() => {
        expect(screen.getByTestId('personal-settings-page')).toBeDefined();
      });

      // github is already linked: button should not be present
      expect(screen.queryByTestId('connect-provider-github')).toBeNull();

      // local-admin is LOCAL_ADMIN: button should not be present
      expect(screen.queryByTestId('connect-provider-local-admin')).toBeNull();

      // corp-ldap is external and not linked: button should be present
      const ldapBtn = screen.getByTestId('connect-provider-corp-ldap');
      expect(ldapBtn).toBeDefined();
      expect(ldapBtn.textContent).toContain('+ Connect Corp LDAP');
    });

    it('handles connecting OIDC/OAuth2 provider, navigating to authorize_url', async () => {
      vi.mocked(authApi.fetchAuthCards).mockResolvedValue(mockAuthCards);
      vi.mocked(api.startLinkIdentity).mockResolvedValue({
        mode: 'redirect',
        authorize_url: 'https://idp.example.com/oauth/authorize?state=xyz',
      });

      const originalLocation = window.location;
      const assignMock = vi.fn();
      // @ts-expect-error mocking window.location
      delete window.location;
      // @ts-expect-error mocking window.location
      window.location = {
        href: '',
        pathname: '/settings/profile',
        search: '',
        assign: assignMock,
      } as unknown as Location;

      renderComponent();

      await waitFor(() => {
        expect(screen.getByTestId('connect-provider-github')).toBeDefined();
      });

      fireEvent.click(screen.getByTestId('connect-provider-github'));

      await waitFor(() => {
        expect(api.startLinkIdentity).toHaveBeenCalledWith('github');
        expect(window.location.href).toBe('https://idp.example.com/oauth/authorize?state=xyz');
      });

      // @ts-expect-error test location restoring
      window.location = originalLocation;
    });

    it('silently ignores Aal2StepUpCancelledError when connecting OIDC provider', async () => {
      vi.mocked(authApi.fetchAuthCards).mockResolvedValue(mockAuthCards);
      vi.mocked(api.startLinkIdentity).mockRejectedValueOnce(new Aal2StepUpCancelledError());

      renderComponent();

      await waitFor(() => {
        expect(screen.getByTestId('connect-provider-github')).toBeDefined();
      });

      fireEvent.click(screen.getByTestId('connect-provider-github'));

      await waitFor(() => {
        expect(api.startLinkIdentity).toHaveBeenCalledWith('github');
      });

      expect(screen.queryByTestId('alert-error')).toBeNull();
      expect(screen.queryByTestId('aal2-stepup-dialog')).toBeNull();
    });

    it('handles connecting LDAP provider via modal and links successfully', async () => {
      vi.mocked(authApi.fetchAuthCards).mockResolvedValue(mockAuthCards);
      vi.mocked(api.startLinkIdentity).mockResolvedValue({
        mode: 'ldap_credentials',
        link_intent_id: 'intent-ldap-1',
      });
      vi.mocked(api.linkLdapIdentity).mockResolvedValue({
        linked: true,
      });

      renderComponent();

      await waitFor(() => {
        expect(screen.getByTestId('connect-provider-corp-ldap')).toBeDefined();
      });

      // Click Connect Corp LDAP to open modal
      fireEvent.click(screen.getByTestId('connect-provider-corp-ldap'));

      await waitFor(() => {
        expect(screen.getByTestId('ldap-credentials-modal')).toBeDefined();
      });

      fireEvent.change(screen.getByTestId('ldap-link-username-input'), {
        target: { value: 'alice_ldap' },
      });
      fireEvent.change(screen.getByTestId('ldap-link-password-input'), {
        target: { value: 'secret123' },
      });

      fireEvent.click(screen.getByTestId('submit-ldap-link-btn'));

      await waitFor(() => {
        expect(api.startLinkIdentity).toHaveBeenCalledWith('corp-ldap');
        expect(api.linkLdapIdentity).toHaveBeenCalledWith(
          'intent-ldap-1',
          'alice_ldap',
          'secret123',
        );
        expect(screen.queryByTestId('ldap-credentials-modal')).toBeNull();
      });
    });

    it('silently ignores Aal2StepUpCancelledError when linking LDAP provider', async () => {
      vi.mocked(authApi.fetchAuthCards).mockResolvedValue(mockAuthCards);
      vi.mocked(api.startLinkIdentity).mockRejectedValueOnce(new Aal2StepUpCancelledError());

      renderComponent();

      await waitFor(() => {
        expect(screen.getByTestId('connect-provider-corp-ldap')).toBeDefined();
      });

      fireEvent.click(screen.getByTestId('connect-provider-corp-ldap'));

      await waitFor(() => {
        expect(screen.getByTestId('ldap-credentials-modal')).toBeDefined();
      });

      fireEvent.change(screen.getByTestId('ldap-link-username-input'), {
        target: { value: 'alice_ldap' },
      });
      fireEvent.change(screen.getByTestId('ldap-link-password-input'), {
        target: { value: 'secret123' },
      });

      fireEvent.click(screen.getByTestId('submit-ldap-link-btn'));

      await waitFor(() => {
        expect(api.startLinkIdentity).toHaveBeenCalledWith('corp-ldap');
      });

      expect(screen.queryByTestId('ldap-modal-error')).toBeNull();
      expect(screen.queryByTestId('aal2-stepup-dialog')).toBeNull();
    });

    it('renders empty providers notice and admin link for server admins when no external cards enabled', async () => {
      vi.mocked(authApi.fetchAuthCards).mockResolvedValue({
        cards: [
          {
            id: 'c-loc',
            slug: 'local-admin',
            provider_kind: 'LOCAL_ADMIN',
            display_name: 'Local Admin',
            button_subtext: null,
            icon_preset: 'local',
          },
        ],
      });
      vi.mocked(api.fetchMyProfile).mockResolvedValue({
        ...mockProfile,
        is_server_admin: true,
      });

      renderComponent();

      await waitFor(() => {
        expect(screen.getByTestId('no-external-providers-notice')).toBeDefined();
      });

      expect(screen.getByTestId('configure-providers-link')).toBeDefined();
      expect(screen.getByTestId('configure-providers-link').getAttribute('href')).toBe('/admin/auth');
    });

    it('renders empty providers notice without admin link for non-admin users', async () => {
      vi.mocked(authApi.fetchAuthCards).mockResolvedValue({ cards: [] });
      vi.mocked(api.fetchMyProfile).mockResolvedValue({
        ...mockProfile,
        is_server_admin: false,
      });

      renderComponent();

      await waitFor(() => {
        expect(screen.getByTestId('no-external-providers-notice')).toBeDefined();
      });

      expect(screen.queryByTestId('configure-providers-link')).toBeNull();
    });

    it('handles ?linked and ?link_error search parameters on mount', async () => {
      const originalLocation = window.location;
      // @ts-expect-error mocking window.location
      delete window.location;
      // @ts-expect-error mocking window.location
      window.location = {
        href: '',
        search: '?linked=github',
        pathname: '/settings/profile',
      } as unknown as Location;

      const replaceStateSpy = vi.spyOn(window.history, 'replaceState');

      const { unmount: unmount1 } = renderComponent();

      await waitFor(() => {
        expect(screen.getByTestId('alert-success')).toBeDefined();
      });

      expect(screen.getByTestId('alert-success').textContent).toContain(
        'Account successfully linked (github).',
      );
      expect(replaceStateSpy).toHaveBeenCalledWith({}, '', '/settings/profile');
      unmount1();

      // Test ?link_error=IDENTITY_ALREADY_LINKED
      (window.location as unknown as { search: string }).search = '?link_error=IDENTITY_ALREADY_LINKED';

      queryClient.clear();
      const { unmount: unmount2 } = renderComponent();

      await waitFor(() => {
        expect(screen.getByTestId('alert-error')).toBeDefined();
      });

      expect(screen.getByTestId('alert-error').textContent).toContain(
        'External identity is already linked to another account.',
      );
      unmount2();

      // Test ?link_error=UNKNOWN_ERROR
      (window.location as unknown as { search: string }).search = '?link_error=OIDC_CALLBACK_FAILED';

      queryClient.clear();
      const { unmount: unmount3 } = renderComponent();

      await waitFor(() => {
        expect(screen.getByTestId('alert-error')).toBeDefined();
      });

      expect(screen.getByTestId('alert-error').textContent).toContain(
        'Failed to link external identity (OIDC_CALLBACK_FAILED).',
      );
      unmount3();

      // @ts-expect-error test location restoring
      window.location = originalLocation;
      replaceStateSpy.mockRestore();
    });

    it('handles connecting OIDC provider error and non-redirect mode', async () => {
      vi.mocked(authApi.fetchAuthCards).mockResolvedValue(mockAuthCards);
      vi.mocked(api.startLinkIdentity).mockRejectedValueOnce(new Error('Identity provider unreachable'));

      renderComponent();

      await waitFor(() => {
        expect(screen.getByTestId('connect-provider-github')).toBeDefined();
      });

      fireEvent.click(screen.getByTestId('connect-provider-github'));

      await waitFor(() => {
        expect(screen.getByTestId('alert-error')).toBeDefined();
      });
      expect(screen.getByTestId('alert-error').textContent).toContain('Identity provider unreachable');

      // Test string error rejection
      vi.mocked(api.startLinkIdentity).mockRejectedValueOnce('Network failure');
      fireEvent.click(screen.getByTestId('connect-provider-github'));

      await waitFor(() => {
        expect(screen.getByTestId('alert-error').textContent).toContain('Failed to initiate account linking.');
      });

      // Test non-redirect response mode
      vi.mocked(api.startLinkIdentity).mockResolvedValueOnce({ mode: 'form' });
      fireEvent.click(screen.getByTestId('connect-provider-github'));
    });

    it('cancels LDAP linking modal via Close button, Cancel button, and Escape key with focus restore', async () => {
      vi.mocked(authApi.fetchAuthCards).mockResolvedValue(mockAuthCards);
      renderComponent();

      await waitFor(() => {
        expect(screen.getByTestId('connect-provider-corp-ldap')).toBeDefined();
      });

      const ldapTriggerBtn = screen.getByTestId('connect-provider-corp-ldap');
      ldapTriggerBtn.focus();

      // 1. Open modal and dismiss via header Close button
      fireEvent.click(ldapTriggerBtn);
      await waitFor(() => {
        expect(screen.getByTestId('ldap-credentials-modal')).toBeDefined();
      });
      // Initial focus on username input
      await waitFor(() => {
        expect(document.activeElement).toBe(screen.getByTestId('ldap-link-username-input'));
      });

      const closeBtn = screen.getByRole('button', { name: 'Close LDAP modal' });
      fireEvent.click(closeBtn);
      expect(screen.queryByTestId('ldap-credentials-modal')).toBeNull();
      expect(document.activeElement).toBe(ldapTriggerBtn);

      // 2. Open again and dismiss via footer Cancel button
      fireEvent.click(ldapTriggerBtn);
      await waitFor(() => {
        expect(screen.getByTestId('ldap-credentials-modal')).toBeDefined();
      });
      const cancelBtn = screen.getByRole('button', { name: 'Cancel' });
      fireEvent.click(cancelBtn);
      expect(screen.queryByTestId('ldap-credentials-modal')).toBeNull();
      expect(document.activeElement).toBe(ldapTriggerBtn);

      // 3. Open again and dismiss via Escape key
      fireEvent.click(ldapTriggerBtn);
      await waitFor(() => {
        expect(screen.getByTestId('ldap-credentials-modal')).toBeDefined();
      });
      fireEvent.keyDown(window, { key: 'Escape' });
      expect(screen.queryByTestId('ldap-credentials-modal')).toBeNull();
      expect(document.activeElement).toBe(ldapTriggerBtn);
    });

    it('displays inline role="alert" ldap-modal-error on failed LDAP link and prevents backdrop error bleed', async () => {
      vi.mocked(authApi.fetchAuthCards).mockResolvedValue(mockAuthCards);
      renderComponent();

      await waitFor(() => {
        expect(screen.getByTestId('connect-provider-corp-ldap')).toBeDefined();
      });

      // Open modal
      fireEvent.click(screen.getByTestId('connect-provider-corp-ldap'));
      await waitFor(() => {
        expect(screen.getByTestId('ldap-credentials-modal')).toBeDefined();
      });

      fireEvent.change(screen.getByTestId('ldap-link-username-input'), { target: { value: 'testuser' } });
      fireEvent.change(screen.getByTestId('ldap-link-password-input'), { target: { value: 'testpass' } });

      // Missing link_intent_id from server
      vi.mocked(api.startLinkIdentity).mockResolvedValueOnce({ mode: 'redirect' });
      fireEvent.click(screen.getByTestId('submit-ldap-link-btn'));

      await waitFor(() => {
        expect(screen.getByTestId('ldap-modal-error')).toBeDefined();
      });
      expect(screen.getByTestId('ldap-modal-error').textContent).toContain('Missing link intent ID from server.');
      // Modal remains open and no error rendered on page behind backdrop
      expect(screen.getByTestId('ldap-credentials-modal')).toBeDefined();
      expect(screen.queryByTestId('alert-error')).toBeNull();

      // Next failure: linkLdapIdentity rejects with string error
      vi.mocked(api.startLinkIdentity).mockResolvedValueOnce({ mode: 'redirect', link_intent_id: 'intent-ldap' });
      vi.mocked(api.linkLdapIdentity).mockRejectedValueOnce('Directory unreachable');
      fireEvent.click(screen.getByTestId('submit-ldap-link-btn'));

      await waitFor(() => {
        expect(screen.getByTestId('ldap-modal-error').textContent).toContain('Failed to link LDAP account.');
      });
      expect(screen.getByTestId('ldap-credentials-modal')).toBeDefined();
      expect(screen.queryByTestId('alert-error')).toBeNull();
    });

    it('renders identities table cells with responsive data-label attributes matching columns', async () => {
      const testIdentities: api.ExternalIdentityItem[] = [
        {
          id: 'ident-1',
          card_slug: 'github-corp',
          card_display_name: 'GitHub Enterprise',
          provider_kind: 'oauth2',
          immutable_subject_id: 'gh-123',
          subject_email_at_link: 'jane@github.example',
          created_at: '2026-01-15T00:00:00Z',
          last_login_at: '2026-01-15T00:00:00Z',
        },
      ];
      vi.mocked(api.fetchExternalIdentities).mockResolvedValue(testIdentities);
      renderComponent();

      await waitFor(() => {
        expect(screen.getByTestId('identities-table')).toBeDefined();
      });

      const row = screen.getByTestId('identity-row-ident-1');
      const cells = row.querySelectorAll('td');
      expect(cells.length).toBe(4);
      expect(cells[0]?.getAttribute('data-label')).toBe('Provider');
      expect(cells[1]?.getAttribute('data-label')).toBe('Subject / Account');
      expect(cells[2]?.getAttribute('data-label')).toBe('Linked');
      expect(cells[3]?.getAttribute('data-label')).toBe('Actions');
    });

    it('renders provider card key with card.slug fallback when card.id is empty', async () => {
      vi.mocked(authApi.fetchAuthCards).mockResolvedValue({
        cards: [
          {
            id: '',
            slug: 'no-id-provider',
            provider_kind: 'OIDC' as const,
            display_name: 'No ID Provider',
            button_subtext: null,
            icon_preset: 'oidc',
          },
        ],
      });

      renderComponent();

      await waitFor(() => {
        expect(screen.getByTestId('connect-provider-no-id-provider')).toBeDefined();
      });
    });

    it('handles Test Key with fallback cred name and error details', async () => {
      vi.mocked(api.fetchPasskeys).mockResolvedValueOnce([
        {
          id: 'pk-fallback',
          credential_id: 'pk-fallback-cred',
          nickname: '',
          created_at: '2026-01-01T00:00:00Z',
          last_used_at: null,
          transports: ['usb'],
          aaguid: '00000000-0000-0000-0000-000000000000',
        },
      ]);
      const mockAuthOptions: api.PublicKeyCredentialRequestOptionsJSON = {
        challenge: 'chall-auth',
        rpId: 'localhost',
        allowCredentials: [{ id: 'other-cred', type: 'public-key' }],
      };
      const mockAssertion = {
        id: 'pk-fallback',
        rawId: new Uint8Array([1, 2]).buffer,
        type: 'public-key',
        response: {
          clientDataJSON: new TextEncoder().encode('{}').buffer,
          authenticatorData: new Uint8Array([3]).buffer,
          signature: new Uint8Array([4]).buffer,
          userHandle: null,
        },
        getClientExtensionResults: () => ({}),
      } as unknown as PublicKeyCredential;

      vi.mocked(api.fetchWebauthnAuthenticationOptions).mockResolvedValueOnce(mockAuthOptions);
      vi.mocked(api.verifyWebauthnAuthentication).mockResolvedValueOnce({ verified: true });

      const mockGet = vi.fn().mockResolvedValue(mockAssertion);
      Object.defineProperty(navigator, 'credentials', {
        writable: true,
        configurable: true,
        value: { get: mockGet, create: vi.fn() },
      });

      renderComponent();
      await waitFor(() => {
        expect(screen.getByTestId('test-passkey-pk-fallback')).toBeDefined();
      });

      fireEvent.click(screen.getByTestId('test-passkey-pk-fallback'));

      await waitFor(() => {
        expect(screen.getByTestId('alert-success').textContent).toContain('👍 Key verified (Passkey)');
      });
    });

    it('renders Passkey label with raw AAGUID and transport flags collapsed in AdvancedSection (KAN-370)', async () => {
      const mockAdvPasskey: api.WebauthnCredentialItem = {
        id: 'pk-adv-1',
        credential_id: 'cred-98765-adv',
        nickname: 'Hardware Security Key Pro',
        created_at: '2026-11-20T10:00:00Z',
        last_used_at: '2026-11-22T14:30:00Z',
        aaguid: '01a20000-beef-feed-dead-c001cafe1234',
        transports: ['usb', 'nfc'],
        sign_count: 88,
      };

      vi.mocked(api.fetchPasskeys).mockResolvedValueOnce([mockAdvPasskey]);

      renderComponent();

      await waitFor(() => {
        expect(screen.getByTestId('passkey-row-pk-adv-1')).toBeDefined();
      });

      // Passkey label and badge are primary and visible
      expect(screen.getByText('Hardware Security Key Pro')).toBeDefined();
      expect(screen.getByTestId('passkey-badge-pk-adv-1').textContent).toContain('🔑 FIDO2 Security Key');

      // AdvancedSection is present and collapsed by default
      const advSection = screen.getByTestId('passkey-advanced-pk-adv-1');
      expect(advSection).toBeDefined();
      expect(advSection.hasAttribute('open')).toBe(false);

      // Raw AAGUID, Credential ID, Sign Count, and Transport Flags are encapsulated inside
      const detailsContainer = within(advSection).getByTestId('passkey-advanced-details-pk-adv-1');
      expect(detailsContainer).toBeDefined();
      expect(within(detailsContainer).getByTestId('passkey-aaguid-pk-adv-1').textContent).toBe(
        '01a20000-beef-feed-dead-c001cafe1234',
      );
      expect(within(detailsContainer).getByTestId('passkey-cred-id-pk-adv-1').textContent).toBe(
        'cred-98765-adv',
      );
      expect(within(detailsContainer).getByTestId('passkey-sign-count-pk-adv-1').textContent).toBe('88');
      expect(within(detailsContainer).getByTestId('passkey-transports-pk-adv-1').textContent).toBe('usb, nfc');
      expect(within(detailsContainer).getByTestId('passkey-session-metadata-pk-adv-1').textContent).toContain(
        'AAL2-Bound Passkey Token',
      );

      // Toggle button expands the AdvancedSection
      const toggleBtn = screen.getByTestId('passkey-advanced-pk-adv-1-toggle');
      fireEvent.click(toggleBtn);
      expect(advSection.hasAttribute('open')).toBe(true);

      // Toggle button collapses the AdvancedSection
      fireEvent.click(toggleBtn);
      expect(advSection.hasAttribute('open')).toBe(false);
    });
  });
});
