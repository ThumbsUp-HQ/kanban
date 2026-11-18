// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { PersonalSettingsPage } from '../PersonalSettingsPage';
import * as api from '../personalSettingsApi';

vi.mock('../personalSettingsApi');

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
  });

  const renderComponent = () =>
    render(
      <QueryClientProvider client={queryClient}>
        <PersonalSettingsPage />
      </QueryClientProvider>,
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
    expect(screen.getByTestId('mfa-status-totp').textContent).toBe('Active');
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
    });

    fireEvent.click(screen.getByTestId('close-recovery-modal-btn'));
    expect(screen.queryByTestId('recovery-codes-grid')).toBeNull();
  });
});
