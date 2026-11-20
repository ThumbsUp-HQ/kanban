// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import React, { useState, type JSX, type SyntheticEvent } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { qk } from '../../api/queryKeys';
import { ApiProblem } from '../../api/problem';
import {
  prepareCreationOptions,
  serializeRegistrationCredential,
} from '../auth/webauthn';
import {
  fetchWebauthnRegistrationOptions,
  verifyWebauthnRegistration,
} from './personalSettingsApi';
import './PasskeyEnrollModal.css';

export type AuthenticatorAttachmentChoice = 'platform' | 'cross-platform' | 'any';

export interface PasskeyEnrollModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: (message: string) => void;
  initialAttachment?: 'platform' | 'cross-platform';
  onInterceptAal2?: (err: unknown, retryAction: () => Promise<void>) => boolean;
}

export function PasskeyEnrollModal({
  isOpen,
  onClose,
  onSuccess,
  initialAttachment = 'platform',
  onInterceptAal2,
}: PasskeyEnrollModalProps): JSX.Element | null {
  const queryClient = useQueryClient();
  const [attachmentChoice, setAttachmentChoice] = useState<AuthenticatorAttachmentChoice>(
    initialAttachment,
  );
  const [prevAttachment, setPrevAttachment] = useState(initialAttachment);
  if (initialAttachment !== prevAttachment) {
    setPrevAttachment(initialAttachment);
    setAttachmentChoice(initialAttachment);
  }
  const [nickname, setNickname] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  if (!isOpen) {
    return null;
  }

  const handleClose = (): void => {
    setNickname('');
    setErrorMsg(null);
    setIsSubmitting(false);
    onClose();
  };

  const executeRegistration = async (): Promise<void> => {
    setIsSubmitting(true);
    setErrorMsg(null);
    try {
      const attachmentHint = attachmentChoice === 'any' ? undefined : attachmentChoice;
      const options = await fetchWebauthnRegistrationOptions(attachmentHint);
      const creationOptions = prepareCreationOptions(options);

      const credential = (await navigator.credentials.create({
        publicKey: creationOptions,
      })) as PublicKeyCredential | null;

      if (!credential) {
        throw new Error('Credential creation returned null.');
      }

      const serialized = serializeRegistrationCredential(credential);
      await verifyWebauthnRegistration({
        nickname: nickname.trim(),
        credential: serialized,
      });

      void queryClient.invalidateQueries({ queryKey: ['myPasskeys'] });
      void queryClient.invalidateQueries({ queryKey: ['myMfaStatus'] });
      void queryClient.invalidateQueries({ queryKey: qk.me() });
      void queryClient.invalidateQueries({ queryKey: ['myProfile'] });
      void queryClient.invalidateQueries({ queryKey: ['auth', 'me'] });

      handleClose();
      onSuccess('Passkey registered successfully.');
    } catch (err: unknown) {
      if (onInterceptAal2?.(err, executeRegistration)) {
        return;
      }
      if (err instanceof Error && err.name === 'NotAllowedError') {
        setErrorMsg('Passkey registration was cancelled or timed out. Please try again.');
      } else if (err instanceof ApiProblem) {
        setErrorMsg(err.detail ?? err.title ?? 'Failed to register passkey.');
      } else if (err instanceof Error) {
        setErrorMsg(err.message.length > 0 ? err.message : 'Failed to register passkey.');
      } else {
        setErrorMsg('An unexpected error occurred during passkey registration.');
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleSubmit = (e: SyntheticEvent): void => {
    e.preventDefault();
    const cleanNickname = nickname.trim();
    if (!cleanNickname) {
      setErrorMsg('Nickname is required.');
      return;
    }
    if (cleanNickname.length > 64) {
      setErrorMsg('Nickname must not exceed 64 characters.');
      return;
    }
    void executeRegistration();
  };

  return (
    <div className="kb-passkey-enroll-backdrop" role="presentation">
      <div
        className="kb-passkey-enroll-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="passkey-enroll-title"
        data-testid="passkey-enroll-modal"
      >
        <div className="kb-passkey-enroll-header">
          <h3
            id="passkey-enroll-title"
            data-testid="passkey-enroll-title"
            className="kb-passkey-enroll-title"
          >
            Register Passkey or Security Key
          </h3>
          <button
            type="button"
            className="kb-personal-settings-btn kb-personal-settings-btn-secondary"
            data-testid="passkey-enroll-close-btn"
            disabled={isSubmitting}
            onClick={handleClose}
          >
            Cancel
          </button>
        </div>

        <form onSubmit={handleSubmit}>
          <div className="kb-passkey-enroll-body">
            <p className="kb-passkey-enroll-intro">
              Register a hardware security key or synced passkey for fast, phishing-resistant authentication.
            </p>

            {errorMsg && (
              <div
                className="kb-passkey-enroll-error"
                role="alert"
                data-testid="passkey-enroll-error"
              >
                {errorMsg}
              </div>
            )}

            <div className="kb-passkey-enroll-field">
              <label htmlFor="passkey-enroll-nickname" className="kb-passkey-enroll-label">
                Nickname
              </label>
              <input
                id="passkey-enroll-nickname"
                data-testid="passkey-enroll-nickname-input"
                type="text"
                className="kb-passkey-enroll-input"
                maxLength={64}
                placeholder="e.g. MacBook Touch ID, YubiKey 5C NFC"
                value={nickname}
                onChange={(e) => {
                  setNickname(e.target.value);
                  if (errorMsg) setErrorMsg(null);
                }}
                disabled={isSubmitting}
                required
                autoFocus
              />
            </div>

            <div className="kb-passkey-enroll-field">
              <span className="kb-passkey-enroll-label">Authenticator Type</span>
              <div className="kb-passkey-enroll-attachment-grid" role="radiogroup" aria-label="Authenticator Type">
                <label
                  className={`kb-passkey-enroll-option ${
                    attachmentChoice === 'platform' ? 'kb-passkey-enroll-option--selected' : ''
                  }`}
                  data-testid="attachment-platform-label"
                >
                  <input
                    type="radio"
                    name="authenticator-attachment"
                    value="platform"
                    checked={attachmentChoice === 'platform'}
                    onChange={() => { setAttachmentChoice('platform'); }}
                    disabled={isSubmitting}
                    className="kb-passkey-enroll-option-radio"
                    data-testid="attachment-platform-radio"
                  />
                  <div className="kb-passkey-enroll-option-content">
                    <span className="kb-passkey-enroll-option-title">
                      📱 Passkey (Device / Synced)
                    </span>
                    <span className="kb-passkey-enroll-option-desc">
                      Touch ID, Face ID, Windows Hello, or iCloud Keychain
                    </span>
                  </div>
                </label>

                <label
                  className={`kb-passkey-enroll-option ${
                    attachmentChoice === 'cross-platform' ? 'kb-passkey-enroll-option--selected' : ''
                  }`}
                  data-testid="attachment-cross-platform-label"
                >
                  <input
                    type="radio"
                    name="authenticator-attachment"
                    value="cross-platform"
                    checked={attachmentChoice === 'cross-platform'}
                    onChange={() => { setAttachmentChoice('cross-platform'); }}
                    disabled={isSubmitting}
                    className="kb-passkey-enroll-option-radio"
                    data-testid="attachment-cross-platform-radio"
                  />
                  <div className="kb-passkey-enroll-option-content">
                    <span className="kb-passkey-enroll-option-title">
                      🔑 FIDO2 Hardware Key (USB / NFC)
                    </span>
                    <span className="kb-passkey-enroll-option-desc">
                      YubiKey, Feitian, or other external hardware security key
                    </span>
                  </div>
                </label>

                <label
                  className={`kb-passkey-enroll-option ${
                    attachmentChoice === 'any' ? 'kb-passkey-enroll-option--selected' : ''
                  }`}
                  data-testid="attachment-any-label"
                >
                  <input
                    type="radio"
                    name="authenticator-attachment"
                    value="any"
                    checked={attachmentChoice === 'any'}
                    onChange={() => { setAttachmentChoice('any'); }}
                    disabled={isSubmitting}
                    className="kb-passkey-enroll-option-radio"
                    data-testid="attachment-any-radio"
                  />
                  <div className="kb-passkey-enroll-option-content">
                    <span className="kb-passkey-enroll-option-title">
                      🛡️ Any Authenticator
                    </span>
                    <span className="kb-passkey-enroll-option-desc">
                      Let browser and operating system choose available modality
                    </span>
                  </div>
                </label>
              </div>
            </div>
          </div>

          <div className="kb-passkey-enroll-footer">
            <button
              type="button"
              className="kb-personal-settings-btn kb-personal-settings-btn-secondary"
              data-testid="passkey-enroll-cancel-btn"
              disabled={isSubmitting}
              onClick={handleClose}
            >
              Cancel
            </button>
            <button
              type="submit"
              className="kb-personal-settings-btn kb-personal-settings-btn-primary"
              data-testid="passkey-enroll-submit-btn"
              disabled={isSubmitting || !nickname.trim()}
            >
              {isSubmitting ? 'Registering...' : 'Continue'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
