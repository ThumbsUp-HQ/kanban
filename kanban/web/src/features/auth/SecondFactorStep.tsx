import React, { useState, type JSX } from 'react';
import type { MfaMethod, FormattedError } from './authApi';
import {
  getWebauthnAssertionOptions,
  verifyWebauthnAssertion,
  verifyTotp,
  verifyRecoveryCode,
  formatAuthError,
} from './authApi';
import {
  base64urlToBuffer,
  serializeAssertionCredential,
  isWebAuthnSupported,
} from './webauthn';
import './auth.css';

export interface SecondFactorStepProps {
  challengeId: string;
  methods: MfaMethod[];
  onSuccess: () => void;
  onError: (formattedError: FormattedError) => void;
  onSessionExpired: () => void;
  onCancel?: () => void;
}

export function SecondFactorStep({
  challengeId,
  methods,
  onSuccess,
  onError,
  onSessionExpired,
  onCancel,
}: SecondFactorStepProps): JSX.Element {
  // Ordered by methods provided by server
  const activeMethods: MfaMethod[] = methods.length > 0 ? methods : ['totp'];
  const initialMethod: MfaMethod = activeMethods[0] ?? 'totp';
  const [selectedMethod, setSelectedMethod] = useState<MfaMethod>(initialMethod);

  const [totpCode, setTotpCode] = useState('');
  const [recoveryCode, setRecoveryCode] = useState('');
  const [isVerifying, setIsVerifying] = useState(false);

  const supportsWebAuthn = isWebAuthnSupported();

  const handleAssertion = async () => {
    if (isVerifying) return;
    setIsVerifying(true);

    try {
      const { options } = await getWebauthnAssertionOptions({ challenge_id: challengeId });

      const requestOptions: PublicKeyCredentialRequestOptions = {
        challenge: base64urlToBuffer(options.challenge),
        timeout: options.timeout ?? 60000,
        userVerification: options.userVerification ?? 'required',
        ...(options.rpId ? { rpId: options.rpId } : {}),
        ...(options.allowCredentials
          ? {
              allowCredentials: options.allowCredentials.map((cred) => ({
                id: base64urlToBuffer(cred.id),
                type: cred.type as PublicKeyCredentialType,
                transports: cred.transports as AuthenticatorTransport[],
              })),
            }
          : {}),
      };

      const credential = (await navigator.credentials.get({
        publicKey: requestOptions,
      })) as PublicKeyCredential | null;

      if (!credential) {
        throw new Error('WEBAUTHN_FAILED');
      }

      const serialized = serializeAssertionCredential(credential);
      await verifyWebauthnAssertion({
        challenge_id: challengeId,
        credential: serialized,
      });

      onSuccess();
    } catch (err: unknown) {
      const formatted = formatAuthError(err);
      if (formatted.code === 'CHALLENGE_EXPIRED') {
        onSessionExpired();
      } else {
        onError({
          message: 'Passkey verification failed. Try again or use an authenticator code.',
          code: 'WEBAUTHN_FAILED',
        });
      }
    } finally {
      setIsVerifying(false);
    }
  };

  const submitTotp = async (codeStr: string) => {
    if (isVerifying) return;
    setIsVerifying(true);

    try {
      await verifyTotp({
        challenge_id: challengeId,
        code: codeStr,
      });
      onSuccess();
    } catch (err) {
      const formatted = formatAuthError(err);
      if (formatted.code === 'CHALLENGE_EXPIRED') {
        onSessionExpired();
      } else {
        onError(formatted);
      }
    } finally {
      setIsVerifying(false);
    }
  };

  const handleTotpChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    // Strip non-digits and normalize spaces (e.g. pasted '12 34 56' -> '123456')
    const cleaned = e.target.value.replace(/\D/g, '').slice(0, 6);
    setTotpCode(cleaned);

    // Auto-fire submit when exactly 6 digits are entered
    if (cleaned.length === 6) {
      void submitTotp(cleaned);
    }
  };

  const handleRecoverySubmit = async (e: React.SyntheticEvent) => {
    e.preventDefault();
    if (isVerifying) return;

    const trimmed = recoveryCode.trim();
    if (!/^[A-Za-z0-9-]{8,32}$/.test(trimmed)) {
      onError({ message: 'Invalid recovery code format.', code: 'INVALID_CREDENTIALS' });
      return;
    }

    setIsVerifying(true);
    try {
      await verifyRecoveryCode({
        challenge_id: challengeId,
        code: trimmed,
      });
      onSuccess();
    } catch (err) {
      const formatted = formatAuthError(err);
      if (formatted.code === 'CHALLENGE_EXPIRED') {
        onSessionExpired();
      } else {
        onError(formatted);
      }
    } finally {
      setIsVerifying(false);
    }
  };

  return (
    <div className="auth-second-factor-step">
      <div className="auth-tablist" role="tablist" aria-label="Second factor methods">
        {activeMethods.map((m, index) => {
          const isSelected = selectedMethod === m;
          const isPasskeyDisabled = m === 'webauthn' && !supportsWebAuthn;
          let label = 'Passkey';
          if (m === 'totp') label = 'Authenticator code';
          if (m === 'recovery') label = 'Recovery code';

          const handleKeyDown = (e: React.KeyboardEvent<HTMLButtonElement>) => {
            let nextIndex: number | null = null;
            if (e.key === 'ArrowRight' || e.key === 'ArrowDown') {
              e.preventDefault();
              nextIndex = (index + 1) % activeMethods.length;
            } else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') {
              e.preventDefault();
              nextIndex = (index - 1 + activeMethods.length) % activeMethods.length;
            } else if (e.key === 'Home') {
              e.preventDefault();
              nextIndex = 0;
            } else if (e.key === 'End') {
              e.preventDefault();
              nextIndex = activeMethods.length - 1;
            }
            if (nextIndex !== null) {
              const target = activeMethods[nextIndex];
              if (target) {
                setSelectedMethod(target);
                const buttons = e.currentTarget.parentElement?.querySelectorAll<HTMLButtonElement>('[role="tab"]');
                buttons?.[nextIndex]?.focus();
              }
            }
          };

          return (
            <button
              key={m}
              role="tab"
              type="button"
              className="auth-tab"
              aria-selected={isSelected}
              aria-disabled={isPasskeyDisabled ? 'true' : undefined}
              disabled={isPasskeyDisabled}
              tabIndex={isSelected ? 0 : -1}
              onKeyDown={handleKeyDown}
              onClick={() => {
                if (!isPasskeyDisabled) {
                  setSelectedMethod(m);
                }
              }}
            >
              {label}
            </button>
          );
        })}
      </div>

      {selectedMethod === 'webauthn' && (
        <div className="auth-tab-panel" role="tabpanel">
          {!supportsWebAuthn ? (
            <p className="auth-empty-state">
              This browser does not support passkeys. Use an authenticator code.
            </p>
          ) : (
            <div className="auth-form">
              <p className="auth-label">
                Click below to verify your identity using your device Passkey or security key.
              </p>
              <button
                type="button"
                className="auth-submit-btn"
                onClick={() => {
                  void handleAssertion();
                }}
                disabled={isVerifying}
                aria-busy={isVerifying}
              >
                {isVerifying ? 'Awaiting Passkey...' : 'Use passkey'}
              </button>
            </div>
          )}
        </div>
      )}

      {selectedMethod === 'totp' && (
        <div className="auth-tab-panel" role="tabpanel">
          <form
            className="auth-form"
            onSubmit={(e) => {
              e.preventDefault();
              if (totpCode.length === 6) {
                void submitTotp(totpCode);
              }
            }}
          >
            <div className="auth-field">
              <label className="auth-label" htmlFor="totp-code-input">
                6-digit Authenticator Code
              </label>
              <input
                id="totp-code-input"
                className="auth-input auth-mono"
                type="text"
                inputMode="numeric"
                autoComplete="one-time-code"
                pattern="^[0-9]{6}$"
                maxLength={6}
                value={totpCode}
                onChange={handleTotpChange}
                placeholder="123456"
                required
                disabled={isVerifying}
                autoFocus
              />
            </div>
            <button
              type="submit"
              className="auth-submit-btn"
              disabled={isVerifying || totpCode.length !== 6}
              aria-busy={isVerifying}
            >
              {isVerifying ? 'Verifying code...' : 'Verify code'}
            </button>
          </form>
        </div>
      )}

      {selectedMethod === 'recovery' && (
        <div className="auth-tab-panel" role="tabpanel">
          <form
            className="auth-form"
            onSubmit={(e) => {
              void handleRecoverySubmit(e);
            }}
          >
            <div className="auth-field">
              <label className="auth-label" htmlFor="recovery-code-input">
                Single-use Recovery Code
              </label>
              <input
                id="recovery-code-input"
                className="auth-input auth-mono"
                type="text"
                pattern="^[A-Za-z0-9-]{8,32}$"
                maxLength={32}
                value={recoveryCode}
                onChange={(e) => { setRecoveryCode(e.target.value); }}
                placeholder="xxxx-xxxx-xxxx"
                required
                disabled={isVerifying}
                autoFocus
              />
            </div>
            <button
              type="submit"
              className="auth-submit-btn"
              disabled={isVerifying || recoveryCode.trim().length < 8}
              aria-busy={isVerifying}
            >
              {isVerifying ? 'Verifying...' : 'Verify recovery code'}
            </button>
          </form>
        </div>
      )}

      {onCancel && (
        <div className="auth-cancel-row">
          <button
            type="button"
            className="auth-copy-btn"
            onClick={onCancel}
            disabled={isVerifying}
          >
            Cancel and return to sign-in
          </button>
        </div>
      )}
    </div>
  );
}
