// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import React, { useState, useRef, type JSX, type SyntheticEvent } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  fetchMyProfile,
  updateMyProfile,
  uploadAvatar,
  deleteAvatar,
  changePassword,
  fetchMfaStatus,
  fetchPasskeys,
  renamePasskey,
  deletePasskey,
  fetchWebauthnAuthenticationOptions,
  verifyWebauthnAuthentication,
  enrollTotp,
  confirmTotp,
  deleteTotp,
  regenerateRecoveryCodes,
  fetchExternalIdentities,
  unlinkIdentity,
  type UserProfileResponse,
  type WebauthnCredentialItem,
  type MfaStatusResponse,
  type ExternalIdentityItem,
} from './personalSettingsApi';
import { SecondFactorStep } from '../auth/SecondFactorStep';
import {
  isWebAuthnSupported,
  prepareRequestOptions,
  serializeAssertionCredential,
} from '../auth/webauthn';
import { PasskeyEnrollModal } from './PasskeyEnrollModal';
import { ApiProblem } from '../../api/problem';
import type { MfaMethod } from '../auth/authApi';
import { copyToClipboard } from '../../utils/clipboard';
import { qk } from '../../api/queryKeys';
import { AvatarCropModal } from './AvatarCropModal';
import { AvatarLightboxModal } from './AvatarLightboxModal';
import './PersonalSettingsPage.css';

// IANA Timezones list
const TIMEZONES = [
  'UTC',
  'America/New_York',
  'America/Chicago',
  'America/Denver',
  'America/Los_Angeles',
  'America/Anchorage',
  'America/Honolulu',
  'Europe/London',
  'Europe/Paris',
  'Europe/Berlin',
  'Asia/Tokyo',
  'Asia/Shanghai',
  'Asia/Kolkata',
  'Asia/Dubai',
  'Australia/Sydney',
];

export function PersonalSettingsPage(): JSX.Element {
  const queryClient = useQueryClient();

  // Notification state
  const [successMsg, setSuccessMsg] = useState<string | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  // Form states (controlled with fallback to profile)
  const [displayNameInput, setDisplayNameInput] = useState<string | null>(null);
  const [timezoneInput, setTimezoneInput] = useState<string | null>(null);

  // Password state
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [showCurrentPw, setShowCurrentPw] = useState(false);
  const [showNewPw, setShowNewPw] = useState(false);

  // Modals state
  const [recoveryModalCodes, setRecoveryModalCodes] = useState<string[] | null>(null);
  const [recoveryCodesCopied, setRecoveryCodesCopied] = useState(false);
  const [totpSetupStep, setTotpSetupStep] = useState<{
    provisioning_uri?: string | undefined;
    secret?: string | undefined;
  } | null>(null);
  const [totpVerificationCode, setTotpVerificationCode] = useState('');
  const [editingPasskey, setEditingPasskey] = useState<WebauthnCredentialItem | null>(null);
  const [passkeyNickname, setPasskeyNickname] = useState('');
  const [enrollModal, setEnrollModal] = useState<{
    isOpen: boolean;
    initialAttachment: 'platform' | 'cross-platform';
  }>({ isOpen: false, initialAttachment: 'platform' });
  const [testingPasskeyId, setTestingPasskeyId] = useState<string | null>(null);

  const isSecure = typeof window !== 'undefined' && window.isSecureContext;
  const isSupported = isWebAuthnSupported();

  // AAL2 Step-Up state
  const [aal2Challenge, setAal2Challenge] = useState<{
    challengeId: string;
    methods: MfaMethod[];
  } | null>(null);
  const [pendingAction, setPendingAction] = useState<(() => Promise<void>) | null>(null);

  // Avatar crop modal and lightbox states
  const [cropFile, setCropFile] = useState<File | null>(null);
  const [isLightboxOpen, setIsLightboxOpen] = useState(false);

  const fileInputRef = useRef<HTMLInputElement>(null);

  // Data fetching
  const { data: profile, isLoading: isProfileLoading } = useQuery<UserProfileResponse>({
    queryKey: ['myProfile'],
    queryFn: fetchMyProfile,
  });

  const { data: mfaStatus } = useQuery<MfaStatusResponse>({
    queryKey: ['myMfaStatus'],
    queryFn: fetchMfaStatus,
  });

  const { data: passkeys } = useQuery<WebauthnCredentialItem[]>({
    queryKey: ['myPasskeys'],
    queryFn: fetchPasskeys,
  });

  const { data: identities } = useQuery<ExternalIdentityItem[]>({
    queryKey: ['myIdentities'],
    queryFn: fetchExternalIdentities,
  });

  const currentDisplayName = displayNameInput ?? profile?.display_name ?? '';
  const currentTimezone = timezoneInput ?? profile?.timezone ?? 'UTC';

  const handleInterceptAal2 = (err: unknown, retryAction: () => Promise<void>): boolean => {
    if (err instanceof ApiProblem && (err.code === 'AAL2_REQUIRED' || err.code === 'AAL2_STALE')) {
      const data = err.data as { challenge_id?: string; methods?: MfaMethod[] };
      const challengeId = typeof data.challenge_id === 'string' ? data.challenge_id : 'stepup-challenge';
      const methods = Array.isArray(data.methods) && data.methods.length > 0
        ? data.methods
        : (['webauthn', 'totp'] as MfaMethod[]);
      setAal2Challenge({ challengeId, methods });
      setPendingAction(() => retryAction);
      return true;
    }
    return false;
  };

  const handleTestKey = async (cred: WebauthnCredentialItem): Promise<void> => {
    setTestingPasskeyId(cred.id);
    setErrorMsg(null);
    try {
      const optionsJson = await fetchWebauthnAuthenticationOptions();
      const requestOptions = prepareRequestOptions(optionsJson);

      const assertion = (await navigator.credentials.get({
        publicKey: requestOptions,
      })) as PublicKeyCredential | null;

      if (!assertion) {
        throw new Error('WebAuthn assertion was cancelled.');
      }

      const serialized = serializeAssertionCredential(assertion);
      await verifyWebauthnAuthentication({ credential: serialized });

      setSuccessMsg('👍 Key verified');
      setErrorMsg(null);
      void queryClient.invalidateQueries({ queryKey: ['myPasskeys'] });
    } catch (err: unknown) {
      if (handleInterceptAal2(err, () => handleTestKey(cred))) {
        return;
      }
      if (err instanceof Error && err.name === 'NotAllowedError') {
        setErrorMsg('Key verification was cancelled or timed out.');
      } else if (err instanceof ApiProblem) {
        setErrorMsg(err.detail ?? err.title ?? 'Key verification failed.');
      } else if (err instanceof Error) {
        setErrorMsg(err.message.length > 0 ? err.message : 'Key verification failed.');
      } else {
        setErrorMsg('Key verification failed.');
      }
    } finally {
      setTestingPasskeyId(null);
    }
  };

  // Mutations
  const updateProfileMutation = useMutation({
    mutationFn: updateMyProfile,
    onSuccess: (updated) => {
      queryClient.setQueryData(['myProfile'], updated);
      setSuccessMsg('Profile updated successfully.');
      setErrorMsg(null);
    },
    onError: (err) => {
      setErrorMsg(err instanceof Error ? err.message : 'Failed to update profile.');
    },
  });

  const uploadAvatarMutation = useMutation({
    mutationFn: uploadAvatar,
    onSuccess: (updated) => {
      queryClient.setQueryData(['myProfile'], (prev: UserProfileResponse | undefined) =>
        prev ? { ...prev, ...updated } : updated,
      );
      void queryClient.invalidateQueries({ queryKey: ['myProfile'] });
      void queryClient.invalidateQueries({ queryKey: qk.me() });
      void queryClient.invalidateQueries({ queryKey: ['auth', 'me'] });
      setSuccessMsg('Avatar uploaded successfully.');
      setErrorMsg(null);
    },
    onError: (err) => {
      setErrorMsg(err instanceof Error ? err.message : 'Failed to upload avatar.');
    },
  });

  const deleteAvatarMutation = useMutation({
    mutationFn: deleteAvatar,
    onSuccess: (updated) => {
      queryClient.setQueryData(['myProfile'], (prev: UserProfileResponse | undefined) =>
        prev ? { ...prev, ...updated } : updated,
      );
      void queryClient.invalidateQueries({ queryKey: ['myProfile'] });
      void queryClient.invalidateQueries({ queryKey: qk.me() });
      void queryClient.invalidateQueries({ queryKey: ['auth', 'me'] });
      setSuccessMsg('Avatar removed.');
      setErrorMsg(null);
    },
    onError: (err) => {
      setErrorMsg(err instanceof Error ? err.message : 'Failed to delete avatar.');
    },
  });

  const handleProfileSubmit = (e: SyntheticEvent): void => {
    e.preventDefault();
    updateProfileMutation.mutate({ display_name: currentDisplayName, timezone: currentTimezone });
  };

  const handleAvatarFileChange = (e: React.ChangeEvent<HTMLInputElement>): void => {
    const file = e.target.files?.[0];
    if (!file) return;

    if (file.type === 'image/svg+xml' || ((file.name as string | undefined) ?? '').toLowerCase().endsWith('.svg')) {
      setErrorMsg('SVG avatars are rejected for security. Please upload PNG, JPEG, or WebP.');
      e.target.value = '';
      return;
    }

    if (file.size > 2 * 1024 * 1024) {
      setErrorMsg('Avatar file size exceeds 2 MiB limit.');
      e.target.value = '';
      return;
    }

    setCropFile(file);
    e.target.value = '';
  };

  const handlePasswordSubmit = async (e: SyntheticEvent): Promise<void> => {
    e.preventDefault();
    if (newPassword !== confirmPassword) {
      setErrorMsg('New passwords do not match.');
      return;
    }

    const minLength = profile?.is_server_admin ? 14 : 12;
    if (newPassword.length < minLength) {
      setErrorMsg(`Password must be at least ${String(minLength)} characters.`);
      return;
    }

    const action = async (): Promise<void> => {
      try {
        await changePassword({ current_password: currentPassword, new_password: newPassword });
        setSuccessMsg('Password updated successfully. Other active sessions revoked.');
        setErrorMsg(null);
        setCurrentPassword('');
        setNewPassword('');
        setConfirmPassword('');
      } catch (err) {
        if (!handleInterceptAal2(err, action)) {
          setErrorMsg(err instanceof Error ? err.message : 'Failed to change password.');
        }
      }
    };

    await action();
  };

  const handleStartTotpEnroll = async (): Promise<void> => {
    const action = async (): Promise<void> => {
      try {
        const res = await enrollTotp();
        setTotpSetupStep({
          provisioning_uri: res.provisioning_uri ?? res.otpauth_url,
          secret: res.secret,
        });
      } catch (err) {
        if (!handleInterceptAal2(err, action)) {
          setErrorMsg(err instanceof Error ? err.message : 'Failed to initiate TOTP setup.');
        }
      }
    };
    await action();
  };

  const handleConfirmTotp = async (e: SyntheticEvent): Promise<void> => {
    e.preventDefault();
    try {
      const res = await confirmTotp(totpVerificationCode);
      setTotpSetupStep(null);
      setTotpVerificationCode('');
      setSuccessMsg('Two-factor authentication enabled successfully.');
      setErrorMsg(null);
      void queryClient.invalidateQueries({ queryKey: ['myMfaStatus'] });
      if (res.recovery_codes.length > 0) {
        setRecoveryModalCodes(res.recovery_codes);
      }
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : 'Invalid TOTP code.');
    }
  };

  const handleDisableTotp = async (): Promise<void> => {
    if (!window.confirm('Are you sure you want to disable Authenticator App (TOTP)?')) return;
    const action = async (): Promise<void> => {
      try {
        await deleteTotp();
        setSuccessMsg('TOTP disabled.');
        setErrorMsg(null);
        void queryClient.invalidateQueries({ queryKey: ['myMfaStatus'] });
      } catch (err) {
        if (!handleInterceptAal2(err, action)) {
          setErrorMsg(err instanceof Error ? err.message : 'Failed to disable TOTP.');
        }
      }
    };
    await action();
  };

  const handleRegenerateRecoveryCodes = async (): Promise<void> => {
    if (!window.confirm('Regenerating codes will invalidate any existing recovery codes. Continue?')) return;
    const action = async (): Promise<void> => {
      try {
        const res = await regenerateRecoveryCodes();
        setRecoveryModalCodes(res.recovery_codes);
        setSuccessMsg('Generated 10 new one-time recovery codes.');
        setErrorMsg(null);
        void queryClient.invalidateQueries({ queryKey: ['myMfaStatus'] });
      } catch (err) {
        if (!handleInterceptAal2(err, action)) {
          setErrorMsg(err instanceof Error ? err.message : 'Failed to regenerate recovery codes.');
        }
      }
    };
    await action();
  };

  const handleRenamePasskey = async (e: SyntheticEvent): Promise<void> => {
    e.preventDefault();
    if (!editingPasskey) return;
    try {
      await renamePasskey(editingPasskey.id, passkeyNickname);
      setEditingPasskey(null);
      setPasskeyNickname('');
      setSuccessMsg('Passkey renamed.');
      setErrorMsg(null);
      void queryClient.invalidateQueries({ queryKey: ['myPasskeys'] });
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : 'Failed to rename passkey.');
    }
  };

  const handleDeletePasskey = async (credentialId: string): Promise<void> => {
    if (!window.confirm('Are you sure you want to delete this passkey?')) return;
    const action = async (): Promise<void> => {
      try {
        await deletePasskey(credentialId);
        setSuccessMsg('Passkey removed.');
        setErrorMsg(null);
        void queryClient.invalidateQueries({ queryKey: ['myPasskeys'] });
        void queryClient.invalidateQueries({ queryKey: ['myMfaStatus'] });
      } catch (err) {
        if (!handleInterceptAal2(err, action)) {
          setErrorMsg(err instanceof Error ? err.message : 'Failed to delete passkey.');
        }
      }
    };
    await action();
  };

  const handleUnlinkIdentity = async (identityId: string): Promise<void> => {
    if (!window.confirm('Are you sure you want to unlink this external account?')) return;
    const action = async (): Promise<void> => {
      try {
        await unlinkIdentity(identityId);
        setSuccessMsg('Account unlinked.');
        setErrorMsg(null);
        void queryClient.invalidateQueries({ queryKey: ['myIdentities'] });
      } catch (err) {
        if (!handleInterceptAal2(err, action)) {
          setErrorMsg(err instanceof Error ? err.message : 'Failed to unlink identity.');
        }
      }
    };
    await action();
  };

  if (isProfileLoading) {
    return (
      <div className="kb-personal-settings-container" data-testid="personal-settings-loading">
        <p>Loading personal settings...</p>
      </div>
    );
  }

  return (
    <div className="kb-personal-settings-container" data-testid="personal-settings-page">
      <header className="kb-personal-settings-header">
        <h1 className="kb-personal-settings-title">Personal Settings</h1>
        <p className="kb-personal-settings-subtitle">
          Manage your user profile, timezone, avatar, authentication credentials, and security keys.
        </p>
      </header>

      {successMsg && (
        <div className="kb-personal-settings-alert kb-personal-settings-alert-success" role="alert" data-testid="alert-success">
          <span>{successMsg}</span>
          <button
            type="button"
            className="kb-personal-settings-btn kb-personal-settings-btn-secondary"
            onClick={() => { setSuccessMsg(null); }}
          >
            Dismiss
          </button>
        </div>
      )}

      {errorMsg && (
        <div className="kb-personal-settings-alert kb-personal-settings-alert-error" role="alert" data-testid="alert-error">
          <span>{errorMsg}</span>
          <button
            type="button"
            className="kb-personal-settings-btn kb-personal-settings-btn-secondary"
            onClick={() => { setErrorMsg(null); }}
          >
            Dismiss
          </button>
        </div>
      )}

      {/* Section 1: Profile & Timezone */}
      <section className="kb-personal-settings-section" aria-labelledby="section-profile-title">
        <h2 id="section-profile-title" className="kb-personal-settings-section-title">
          Profile & Timezone
        </h2>
        <p className="kb-personal-settings-section-desc">
          Your display name, time zone for timestamps, and public profile picture.
        </p>

        <div className="kb-personal-settings-avatar-row">
          {profile?.avatar_url ? (
            <button
              type="button"
              className="kb-personal-settings-avatar-preview kb-personal-settings-avatar-preview-clickable"
              aria-label="Zoom profile picture"
              data-testid="avatar-preview"
              onClick={() => { setIsLightboxOpen(true); }}
            >
              <img
                src={profile.avatar_url}
                alt={`${profile.display_name}'s avatar`}
                draggable={false}
              />
              <div className="kb-personal-settings-avatar-hover-zoom" aria-hidden="true">
                🔍
              </div>
            </button>
          ) : (
            <div className="kb-personal-settings-avatar-preview" data-testid="avatar-preview">
              <span>{((profile?.display_name ?? profile?.username ?? 'U')[0] ?? '').toUpperCase()}</span>
            </div>
          )}
          <div className="kb-personal-settings-avatar-actions">
            <input
              ref={fileInputRef}
              type="file"
              id="avatar-file-input"
              data-testid="avatar-file-input"
              accept="image/png,image/jpeg,image/webp"
              className="kb-personal-settings-file-hidden"
              onChange={handleAvatarFileChange}
            />
            <button
              type="button"
              className="kb-personal-settings-btn kb-personal-settings-btn-secondary"
              data-testid="upload-avatar-btn"
              onClick={() => { fileInputRef.current?.click(); }}
              disabled={uploadAvatarMutation.isPending}
            >
              Upload Picture
            </button>
            {profile?.avatar_url && (
              <button
                type="button"
                className="kb-personal-settings-btn kb-personal-settings-btn-danger"
                data-testid="remove-avatar-btn"
                onClick={() => { deleteAvatarMutation.mutate(); }}
                disabled={deleteAvatarMutation.isPending}
              >
                Remove
              </button>
            )}
          </div>
        </div>

        <form onSubmit={handleProfileSubmit} className="kb-personal-settings-form">
          <div className="kb-personal-settings-field">
            <label htmlFor="display-name" className="kb-personal-settings-label">
              Display Name
            </label>
            <input
              id="display-name"
              data-testid="display-name-input"
              type="text"
              className="kb-personal-settings-input"
              value={currentDisplayName}
              onChange={(e) => { setDisplayNameInput(e.target.value); }}
              required
            />
          </div>

          <div className="kb-personal-settings-field">
            <label htmlFor="timezone-select" className="kb-personal-settings-label">
              Timezone
            </label>
            <select
              id="timezone-select"
              data-testid="timezone-select"
              className="kb-personal-settings-select"
              value={currentTimezone}
              onChange={(e) => { setTimezoneInput(e.target.value); }}
            >
              {TIMEZONES.map((tz) => (
                <option key={tz} value={tz}>
                  {tz}
                </option>
              ))}
            </select>
          </div>

          <div>
            <button
              type="submit"
              className="kb-personal-settings-btn kb-personal-settings-btn-primary"
              data-testid="save-profile-btn"
              disabled={updateProfileMutation.isPending}
            >
              Save Profile
            </button>
          </div>
        </form>
      </section>

      {/* Section 2: Password Change */}
      <section className="kb-personal-settings-section" aria-labelledby="section-password-title">
        <h2 id="section-password-title" className="kb-personal-settings-section-title">
          Change Password
        </h2>
        <p className="kb-personal-settings-section-desc">
          Update your local authentication password. Requires min {profile?.is_server_admin ? 14 : 12} characters.
          Updating your password will revoke all other active sessions across devices.
        </p>

        <form onSubmit={(e) => { void handlePasswordSubmit(e); }} className="kb-personal-settings-form">
          <div className="kb-personal-settings-field">
            <label htmlFor="current-password" className="kb-personal-settings-label">
              Current Password
            </label>
            <div className="kb-personal-settings-password-wrapper">
              <input
                id="current-password"
                data-testid="current-password-input"
                type={showCurrentPw ? 'text' : 'password'}
                className="kb-personal-settings-input kb-personal-settings-password-input"
                value={currentPassword}
                onChange={(e) => { setCurrentPassword(e.target.value); }}
                autoComplete="current-password"
                required
              />
              <button
                type="button"
                className="kb-personal-settings-toggle-pw"
                onClick={() => { setShowCurrentPw(!showCurrentPw); }}
                aria-label={showCurrentPw ? 'Hide password' : 'Show password'}
              >
                {showCurrentPw ? 'Hide' : 'Show'}
              </button>
            </div>
          </div>

          <div className="kb-personal-settings-field">
            <label htmlFor="new-password" className="kb-personal-settings-label">
              New Password
            </label>
            <div className="kb-personal-settings-password-wrapper">
              <input
                id="new-password"
                data-testid="new-password-input"
                type={showNewPw ? 'text' : 'password'}
                className="kb-personal-settings-input kb-personal-settings-password-input"
                value={newPassword}
                onChange={(e) => { setNewPassword(e.target.value); }}
                autoComplete="new-password"
                required
              />
              <button
                type="button"
                className="kb-personal-settings-toggle-pw"
                onClick={() => { setShowNewPw(!showNewPw); }}
                aria-label={showNewPw ? 'Hide password' : 'Show password'}
              >
                {showNewPw ? 'Hide' : 'Show'}
              </button>
            </div>
          </div>

          <div className="kb-personal-settings-field">
            <label htmlFor="confirm-password" className="kb-personal-settings-label">
              Confirm New Password
            </label>
            <input
              id="confirm-password"
              data-testid="confirm-password-input"
              type="password"
              className="kb-personal-settings-input"
              value={confirmPassword}
              onChange={(e) => { setConfirmPassword(e.target.value); }}
              autoComplete="new-password"
              required
            />
          </div>

          <div>
            <button
              type="submit"
              className="kb-personal-settings-btn kb-personal-settings-btn-primary"
              data-testid="change-password-btn"
            >
              Update Password
            </button>
          </div>
        </form>
      </section>

      {/* Section 3: Passkeys (WebAuthn) */}
      <section className="kb-personal-settings-section" aria-labelledby="section-passkeys-title">
        <div className="kb-personal-settings-header-row">
          <div>
            <h2 id="section-passkeys-title" className="kb-personal-settings-section-title">
              Passkeys & Security Keys
            </h2>
            <p className="kb-personal-settings-section-desc">
              Fast, phishing-resistant authentication with WebAuthn / FIDO2 security keys or biometrics.
            </p>
          </div>
          <div className="kb-personal-settings-header-actions">
            <button
              type="button"
              className="kb-personal-settings-btn kb-personal-settings-btn-primary kb-personal-settings-btn--mr"
              data-testid="add-passkey-btn"
              disabled={!isSecure || !isSupported}
              onClick={() => {
                setEnrollModal({ isOpen: true, initialAttachment: 'platform' });
              }}
            >
              + Add Passkey
            </button>
            <button
              type="button"
              className="kb-personal-settings-btn kb-personal-settings-btn-secondary"
              data-testid="add-fido2-key-btn"
              disabled={!isSecure || !isSupported}
              onClick={() => {
                setEnrollModal({ isOpen: true, initialAttachment: 'cross-platform' });
              }}
            >
              + Add FIDO2 Security Key
            </button>
          </div>
        </div>

        {!isSecure && (
          <div
            className="kb-personal-settings-alert kb-personal-settings-alert-warning"
            role="status"
            data-testid="webauthn-insecure-context-notice"
          >
            Browser WebAuthn requires HTTPS or localhost to register and use passkeys or security keys.
          </div>
        )}

        {passkeys && passkeys.length > 0 ? (
          <div className="kb-table-scroll-container">
            <table className="kb-personal-settings-table" data-testid="passkeys-table">
              <thead>
                <tr>
                  <th className="kb-personal-settings-th">Name</th>
                  <th className="kb-personal-settings-th">Created</th>
                  <th className="kb-personal-settings-th">Last Used</th>
                  <th className="kb-personal-settings-th kb-personal-settings-th-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {passkeys.map((pk) => {
                  const transports = (pk.transports ?? []).map((t) => t.toLowerCase());
                  const isFido2Key =
                    transports.some((t) => t === 'usb' || t === 'nfc' || t === 'ble') &&
                    !transports.some((t) => t === 'internal' || t === 'hybrid');
                  const badgeKind = isFido2Key ? 'security-key' : 'passkey';
                  const badgeLabel = isFido2Key ? '🔑 FIDO2 Security Key' : '📱 Passkey';

                  return (
                    <tr key={pk.id} data-testid={`passkey-row-${pk.id}`}>
                      <td className="kb-personal-settings-td">
                        <div className="kb-passkey-cell-title">
                          <strong>
                            {pk.nickname && pk.nickname.length > 0 ? pk.nickname : 'Passkey'}
                          </strong>
                          <span
                            className={`kb-passkey-badge kb-passkey-badge--${badgeKind}`}
                            data-testid={`passkey-badge-${pk.id}`}
                          >
                            {badgeLabel}
                          </span>
                          {pk.suspect_clone_at && (
                            <span
                              className="kb-passkey-clone-warning"
                              data-testid={`passkey-clone-warning-${pk.id}`}
                              title={`Suspected clone recorded at ${pk.suspect_clone_at}`}
                            >
                              ⚠️ Suspected Clone
                            </span>
                          )}
                        </div>
                      </td>
                      <td className="kb-personal-settings-td">
                        {new Date(pk.created_at).toLocaleDateString()}
                      </td>
                      <td className="kb-personal-settings-td">
                        {pk.last_used_at ? new Date(pk.last_used_at).toLocaleDateString() : 'Never'}
                      </td>
                      <td className="kb-personal-settings-td kb-personal-settings-td-right">
                        <button
                          type="button"
                          className="kb-personal-settings-btn kb-personal-settings-btn-secondary kb-personal-settings-btn--mr"
                          data-testid={`test-passkey-${pk.id}`}
                          disabled={testingPasskeyId === pk.id}
                          onClick={() => { void handleTestKey(pk); }}
                        >
                          {testingPasskeyId === pk.id ? 'Testing...' : 'Test Key'}
                        </button>
                        <button
                          type="button"
                          className="kb-personal-settings-btn kb-personal-settings-btn-secondary kb-personal-settings-btn--mr"
                          data-testid={`rename-passkey-${pk.id}`}
                          onClick={() => {
                            setEditingPasskey(pk);
                            setPasskeyNickname(pk.nickname ?? '');
                          }}
                        >
                          Rename
                        </button>
                        <button
                          type="button"
                          className="kb-personal-settings-btn kb-personal-settings-btn-danger"
                          data-testid={`delete-passkey-${pk.id}`}
                          onClick={() => { void handleDeletePasskey(pk.id); }}
                        >
                          Remove
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="kb-personal-settings-empty">
            No passkeys registered yet.
          </p>
        )}
      </section>

      {/* Section 4: Two-Factor Authentication & Recovery Codes */}
      <section className="kb-personal-settings-section" aria-labelledby="section-mfa-title">
        <h2 id="section-mfa-title" className="kb-personal-settings-section-title">
          Two-Factor Authentication (2FA)
        </h2>
        <p className="kb-personal-settings-section-desc">
          Add an extra layer of protection to your account using TOTP and emergency recovery codes.
        </p>

        <div className="kb-personal-settings-status-box">
          <div className="kb-personal-settings-stat-card">
            <div className="kb-personal-settings-stat-num" data-testid="mfa-status-totp">
              {mfaStatus?.totp_enabled ? 'Active' : 'Disabled'}
            </div>
            <div className="kb-personal-settings-stat-label">Authenticator App (TOTP)</div>
          </div>
          <div className="kb-personal-settings-stat-card">
            <div className="kb-personal-settings-stat-num" data-testid="mfa-status-recovery-count">
              {mfaStatus?.recovery_codes_remaining ?? 0}
            </div>
            <div className="kb-personal-settings-stat-label">Remaining Recovery Codes</div>
          </div>
        </div>

        {(() => {
          const is2faActive = Boolean(mfaStatus?.totp_enabled) || Boolean(passkeys && passkeys.length > 0);
          return (
            <div className="kb-personal-settings-mfa-actions">
              {!mfaStatus?.totp_enabled ? (
                <button
                  type="button"
                  className="kb-personal-settings-btn kb-personal-settings-btn-primary"
                  data-testid="enable-totp-btn"
                  onClick={() => { void handleStartTotpEnroll(); }}
                >
                  Configure Authenticator App
                </button>
              ) : (
                <button
                  type="button"
                  className="kb-personal-settings-btn kb-personal-settings-btn-danger"
                  data-testid="disable-totp-btn"
                  onClick={() => { void handleDisableTotp(); }}
                >
                  Disable Authenticator App
                </button>
              )}

              <button
                type="button"
                className="kb-personal-settings-btn kb-personal-settings-btn-secondary"
                data-testid="regenerate-recovery-codes-btn"
                disabled={!is2faActive}
                title={!is2faActive ? 'Enable TOTP or Passkey 2FA first' : undefined}
                onClick={() => { void handleRegenerateRecoveryCodes(); }}
              >
                Regenerate Recovery Codes
              </button>
              {!is2faActive && (
                <span
                  className="kb-personal-settings-hint kb-personal-settings-hint-muted"
                  data-testid="regenerate-hint"
                >
                  Enable TOTP or Passkey 2FA first
                </span>
              )}
            </div>
          );
        })()}
      </section>

      {/* Section 5: Connected Accounts & External Identities */}
      <section className="kb-personal-settings-section" aria-labelledby="section-identities-title">
        <h2 id="section-identities-title" className="kb-personal-settings-section-title">
          Connected Accounts & External Identities
        </h2>
        <p className="kb-personal-settings-section-desc">
          Link external single sign-on identities (OIDC, OAuth2, LDAP) to your user profile. Unlinking requires fresh second-factor verification.
        </p>

        {identities && identities.length > 0 ? (
          <table className="kb-personal-settings-table" data-testid="identities-table">
            <thead>
              <tr>
                <th className="kb-personal-settings-th">Provider</th>
                <th className="kb-personal-settings-th">Subject / Account</th>
                <th className="kb-personal-settings-th">Linked</th>
                <th className="kb-personal-settings-th kb-personal-settings-th-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {identities.map((ident) => (
                <tr key={ident.id} data-testid={`identity-row-${ident.id}`}>
                  <td className="kb-personal-settings-td">
                    <strong>{ident.card_slug}</strong> ({(ident.provider_kind ?? ident.provider_type ?? '').toUpperCase()})
                  </td>
                  <td className="kb-personal-settings-td">
                    {ident.subject_email_at_link ?? ident.immutable_subject_id ?? ident.card_display_name ?? ident.display_name ?? ident.email ?? ident.subject_id ?? 'Unknown'}
                  </td>
                  <td className="kb-personal-settings-td">
                    {ident.created_at ? new Date(ident.created_at).toLocaleDateString() : 'N/A'}
                  </td>
                  <td className="kb-personal-settings-td kb-personal-settings-td-right">
                    <button
                      type="button"
                      className="kb-personal-settings-btn kb-personal-settings-btn-danger"
                      data-testid={`unlink-identity-${ident.id}`}
                      onClick={() => { void handleUnlinkIdentity(ident.id); }}
                    >
                      Unlink
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p className="kb-personal-settings-empty">
            No external identities linked.
          </p>
        )}
      </section>

      {/* TOTP Setup Modal */}
      {totpSetupStep && (
        <div className="kb-personal-settings-modal-backdrop" role="presentation">
          <div
            className="kb-personal-settings-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="totp-modal-title"
          >
            <div className="kb-personal-settings-modal-header">
              <h3 id="totp-modal-title" className="kb-personal-settings-modal-title">
                Configure Authenticator App
              </h3>
              <button
                type="button"
                className="kb-personal-settings-btn kb-personal-settings-btn-secondary"
                onClick={() => { setTotpSetupStep(null); }}
              >
                Cancel
              </button>
            </div>
            <form onSubmit={(e) => { void handleConfirmTotp(e); }}>
              <div className="kb-personal-settings-modal-body">
                <p className="kb-personal-settings-modal-text">
                  Scan the QR code or enter the secret code into your authenticator app (Google
                  Authenticator, 1Password, Bitwarden, etc.):
                </p>
                {totpSetupStep.secret && (
                  <div
                    className="kb-personal-settings-secret-box"
                    data-testid="totp-secret-key"
                  >
                    {totpSetupStep.secret}
                  </div>
                )}
                <div className="kb-personal-settings-field">
                  <label htmlFor="totp-verify-code" className="kb-personal-settings-label">
                    Enter 6-digit Verification Code
                  </label>
                  <input
                    id="totp-verify-code"
                    data-testid="totp-verification-input"
                    type="text"
                    maxLength={6}
                    className="kb-personal-settings-input"
                    value={totpVerificationCode}
                    onChange={(e) => { setTotpVerificationCode(e.target.value); }}
                    placeholder="123456"
                    required
                  />
                </div>
              </div>
              <div className="kb-personal-settings-modal-footer">
                <button
                  type="button"
                  className="kb-personal-settings-btn kb-personal-settings-btn-secondary"
                  onClick={() => { setTotpSetupStep(null); }}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="kb-personal-settings-btn kb-personal-settings-btn-primary"
                  data-testid="confirm-totp-btn"
                >
                  Verify & Activate
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Recovery Codes Modal */}
      {recoveryModalCodes && (
        <div className="kb-personal-settings-modal-backdrop" role="presentation">
          <div
            className="kb-personal-settings-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="recovery-modal-title"
          >
            <div className="kb-personal-settings-modal-header">
              <h3 id="recovery-modal-title" className="kb-personal-settings-modal-title">
                One-Time Recovery Codes
              </h3>
            </div>
            <div className="kb-personal-settings-modal-body">
              <p className="kb-personal-settings-modal-text">
                Store these recovery codes in a secure location. Each code can only be used once to access
                your account if you lose your 2FA device.
              </p>
              <div className="kb-personal-settings-recovery-grid" data-testid="recovery-codes-grid">
                {recoveryModalCodes.map((code, idx) => (
                  <div key={idx} className="kb-personal-settings-recovery-item">
                    {code}
                  </div>
                ))}
              </div>
            </div>
            <div className="kb-personal-settings-modal-footer">
              <button
                type="button"
                className="kb-personal-settings-btn kb-personal-settings-btn-secondary"
                data-testid="copy-recovery-codes-btn"
                onClick={() => {
                  void (async () => {
                    const codesText = recoveryModalCodes.join('\n');
                    const ok = await copyToClipboard(codesText);
                    if (ok) {
                      setRecoveryCodesCopied(true);
                      setTimeout(() => {
                        setRecoveryCodesCopied(false);
                      }, 2000);
                    }
                  })();
                }}
              >
                {recoveryCodesCopied ? 'Copied!' : 'Copy Codes'}
              </button>
              <button
                type="button"
                className="kb-personal-settings-btn kb-personal-settings-btn-primary"
                data-testid="close-recovery-modal-btn"
                onClick={() => { setRecoveryModalCodes(null); }}
              >
                I Have Saved These Codes
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Rename Passkey Modal */}
      {editingPasskey && (
        <div className="kb-personal-settings-modal-backdrop" role="presentation">
          <div
            className="kb-personal-settings-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="rename-passkey-title"
          >
            <div className="kb-personal-settings-modal-header">
              <h3 id="rename-passkey-title" className="kb-personal-settings-modal-title">
                Rename Passkey
              </h3>
              <button
                type="button"
                className="kb-personal-settings-btn kb-personal-settings-btn-secondary"
                onClick={() => { setEditingPasskey(null); }}
              >
                Cancel
              </button>
            </div>
            <form onSubmit={(e) => { void handleRenamePasskey(e); }}>
              <div className="kb-personal-settings-modal-body">
                <div className="kb-personal-settings-field">
                  <label htmlFor="passkey-nickname" className="kb-personal-settings-label">
                    Passkey Label / Nickname
                  </label>
                  <input
                    id="passkey-nickname"
                    data-testid="passkey-nickname-input"
                    type="text"
                    className="kb-personal-settings-input"
                    value={passkeyNickname}
                    onChange={(e) => { setPasskeyNickname(e.target.value); }}
                    required
                  />
                </div>
              </div>
              <div className="kb-personal-settings-modal-footer">
                <button
                  type="button"
                  className="kb-personal-settings-btn kb-personal-settings-btn-secondary"
                  onClick={() => { setEditingPasskey(null); }}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="kb-personal-settings-btn kb-personal-settings-btn-primary"
                  data-testid="save-passkey-nickname-btn"
                >
                  Save
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* AAL2 Step-Up Dialog */}
      {aal2Challenge && (
        <div className="kb-personal-settings-modal-backdrop kb-personal-settings-modal-backdrop--stepup" role="presentation">
          <div
            className="kb-personal-settings-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="aal2-stepup-title"
            data-testid="aal2-stepup-dialog"
          >
            <div className="kb-personal-settings-modal-header">
              <h3 id="aal2-stepup-title" className="kb-personal-settings-modal-title">
                Security Verification Required (AAL2)
              </h3>
              <button
                type="button"
                className="kb-personal-settings-btn kb-personal-settings-btn-secondary"
                onClick={() => {
                  setAal2Challenge(null);
                  setPendingAction(null);
                }}
              >
                Cancel
              </button>
            </div>
            <div className="kb-personal-settings-modal-body">
              <p className="kb-personal-settings-modal-text">
                This operation requires fresh second-factor verification. Please confirm with your passkey or TOTP authenticator.
              </p>
              <SecondFactorStep
                challengeId={aal2Challenge.challengeId}
                methods={aal2Challenge.methods}
                onSuccess={() => {
                  setAal2Challenge(null);
                  const action = pendingAction;
                  setPendingAction(null);
                  void action?.();
                }}
                onError={() => {
                  // handled inside SecondFactorStep
                }}
                onSessionExpired={() => {
                  setAal2Challenge(null);
                  setPendingAction(null);
                }}
                onCancel={() => {
                  setAal2Challenge(null);
                  setPendingAction(null);
                }}
              />
            </div>
          </div>
        </div>
      )}

      {/* Passkey / FIDO2 Security Key Enrollment Modal */}
      <PasskeyEnrollModal
        key={`${enrollModal.initialAttachment}-${String(enrollModal.isOpen)}`}
        isOpen={enrollModal.isOpen}
        initialAttachment={enrollModal.initialAttachment}
        onClose={() => {
          setEnrollModal((prev) => ({ ...prev, isOpen: false }));
        }}
        onSuccess={(msg) => {
          setSuccessMsg(msg);
          setErrorMsg(null);
        }}
        onInterceptAal2={handleInterceptAal2}
      />

      {cropFile && (
        <AvatarCropModal
          file={cropFile}
          onSave={(blob) => {
            uploadAvatarMutation.mutate(blob);
            setCropFile(null);
          }}
          onClose={() => { setCropFile(null); }}
          isSaving={uploadAvatarMutation.isPending}
        />
      )}

      {isLightboxOpen && profile?.avatar_url && (
        <AvatarLightboxModal
          avatarUrl={profile.avatar_url}
          displayName={profile.display_name}
          onClose={() => { setIsLightboxOpen(false); }}
        />
      )}
    </div>
  );
}
