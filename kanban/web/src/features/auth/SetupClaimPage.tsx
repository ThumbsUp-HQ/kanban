import React, { useCallback, useEffect, useRef, useState, type JSX } from 'react';
import { EmojiHint } from '../../components/emoji/EmojiHint';
import {
  submitSetupClaim,
  fetchSessionInfo,
  getWebauthnRegistrationOptions,
  verifyWebauthnRegistration,
  enrollTotp,
  verifyTotpEnrollment,
  formatAuthError,
  type FormattedError,
} from './authApi';
import {
  base64urlToBuffer,
  serializeRegistrationCredential,
  isWebAuthnSupported,
} from './webauthn';
import { copyToClipboard } from '../../utils/clipboard';
import './auth.css';

const TOKEN_REGEX = /^kb_setup_[A-Za-z0-9_-]{43}$/;
const USERNAME_REGEX = /^[a-z0-9][a-z0-9._-]{2,63}$/;

export interface SetupClaimPageProps {
  initialToken?: string;
  onNavigate?: (url: string) => void;
}

export function SetupClaimPage({
  initialToken,
  onNavigate,
}: SetupClaimPageProps): JSX.Element {
  const [tokenValid, setTokenValid] = useState<boolean>(() => {
    let token = initialToken;
    if (!token && typeof window !== 'undefined') {
      const search = new URLSearchParams(window.location.search);
      token = search.get('token') ?? undefined;
    }
    return Boolean(token && TOKEN_REGEX.test(token));
  });

  const tokenRef = useRef<string | null>(
    (() => {
      let token = initialToken;
      if (!token && typeof window !== 'undefined') {
        const search = new URLSearchParams(window.location.search);
        token = search.get('token') ?? undefined;
      }
      return token && TOKEN_REGEX.test(token) ? token : null;
    })(),
  );

  // Step 1: Claim form
  const [currentStep, setCurrentStep] = useState<1 | 2 | 3>(1);
  const [username, setUsername] = useState('admin');
  const [displayName, setDisplayName] = useState('Server Administrator');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [workspaceName, setWorkspaceName] = useState('Kanban Workspace');
  const [workspaceSlug, setWorkspaceSlug] = useState('kanban-workspace');
  const [slugTouched, setSlugTouched] = useState(false);
  const [projectName, setProjectName] = useState('Default Project');
  const [projectKey, setProjectKey] = useState('KANBA');
  const [isSubmitting, setIsSubmitting] = useState(false);

  // Step 2: MFA Enrollment
  const [enrollmentId, setEnrollmentId] = useState<string | null>(null);
  const [enrollMethod, setEnrollMethod] = useState<'webauthn' | 'totp'>('webauthn');
  const [totpEnrollData, setTotpEnrollData] = useState<{
    secret_base32: string;
    otpauth_uri: string;
  } | null>(null);
  const [totpVerifyCode, setTotpVerifyCode] = useState('');
  const [copiedKey, setCopiedKey] = useState(false);

  // Step 3: Recovery Codes
  const [recoveryCodes, setRecoveryCodes] = useState<string[]>([]);
  const [confirmedSaved, setConfirmedSaved] = useState(false);
  const [copiedCodes, setCopiedCodes] = useState(false);

  const [error, setError] = useState<FormattedError | null>(null);
  const alertRef = useRef<HTMLDivElement | null>(null);

  const supportsWebAuthn = isWebAuthnSupported();
  const isPlainHttp =
    typeof window !== 'undefined' &&
    window.location.protocol === 'http:' &&
    window.location.hostname !== 'localhost' &&
    window.location.hostname !== '127.0.0.1';

  const slugify = (text: string): string => {
    return text.toLowerCase().replace(/[^a-z0-9_-]+/g, '-').replace(/^-+|-+$/g, '');
  };

  const handleWorkspaceNameChange = (val: string) => {
    setWorkspaceName(val);
    if (!slugTouched) {
      setWorkspaceSlug(slugify(val) || 'kanban-workspace');
    }
  };


  useEffect(() => {
    if (typeof window !== 'undefined') {
      const search = new URLSearchParams(window.location.search);
      // IMMEDIATELY strip token from address bar and history (Action 9, Test Case 4)
      if (search.get('token')) {
        window.history.replaceState(null, '', '/setup');
      }
    }
  }, []);

  useEffect(() => {
    let active = true;
    async function checkSession() {
      try {
        const session = await fetchSessionInfo();
        if (active && session.authenticated && session.mfa_pending) {
          setTokenValid(true);
          setEnrollmentId(session.session_id ?? 'session-mfa');
          setCurrentStep(2);
        }
      } catch {
        // Ignore session bootstrap error
      }
    }
    void checkSession();
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    let active = true;
    async function checkPlatformAuth() {
      if (typeof window === 'undefined') return;
      if (isPlainHttp) {
        if (active) {
          setEnrollMethod('totp');
        }
        return;
      }
      if (
        'PublicKeyCredential' in window &&
        Boolean(window.PublicKeyCredential) &&
        typeof window.PublicKeyCredential.isUserVerifyingPlatformAuthenticatorAvailable === 'function'
      ) {
        try {
          const available = await window.PublicKeyCredential.isUserVerifyingPlatformAuthenticatorAvailable();
          if (active && !available) {
            setEnrollMethod('totp');
          }
        } catch {
          // Keep current selection
        }
      }
    }
    void checkPlatformAuth();
    return () => {
      active = false;
    };
  }, [isPlainHttp]);

  const handleStartTotpEnroll = useCallback(async () => {
    if (isSubmitting || !enrollmentId) return;
    setIsSubmitting(true);
    setError(null);

    try {
      const data = await enrollTotp({ enrollment_id: enrollmentId });
      setTotpEnrollData(data);
      setEnrollMethod('totp');
    } catch (err) {
      setError(formatAuthError(err));
    } finally {
      setIsSubmitting(false);
    }
  }, [enrollmentId, isSubmitting]);

  useEffect(() => {
    if (currentStep === 2 && enrollMethod === 'totp' && !totpEnrollData && enrollmentId && !isSubmitting) {
      const timer = setTimeout(() => {
        void handleStartTotpEnroll();
      }, 0);
      return () => {
        clearTimeout(timer);
      };
    }
  }, [currentStep, enrollMethod, totpEnrollData, enrollmentId, isSubmitting, handleStartTotpEnroll]);

  useEffect(() => {
    if (error && alertRef.current) {
      alertRef.current.focus();
    }
  }, [error]);

  // Step 1: Submit Claim Form
  const handleClaimSubmit = async (e: React.SyntheticEvent) => {
    e.preventDefault();
    if (isSubmitting || !tokenRef.current) return;

    if (!USERNAME_REGEX.test(username)) {
      setError({
        message: 'Username must be 3-64 characters (lowercase letters, digits, ., _, -).',
        code: 'INVALID_CREDENTIALS',
      });
      return;
    }

    if (displayName.trim().length < 1 || displayName.length > 120) {
      setError({
        message: 'Display name must be between 1 and 120 characters.',
        code: 'INVALID_CREDENTIALS',
      });
      return;
    }

    if (password.length < 14) {
      setError({
        message: 'Password must be at least 14 characters long.',
        code: 'INVALID_CREDENTIALS',
      });
      return;
    }

    if (password !== confirmPassword) {
      setError({
        message: 'Passwords do not match.',
        code: 'INVALID_CREDENTIALS',
      });
      return;
    }

    const cleanProjectKey = projectKey.trim().toUpperCase();
    if (!/^[A-Z][A-Z0-9]{1,9}$/.test(cleanProjectKey)) {
      setError({
        message: 'Project key must be 2-10 uppercase alphanumeric characters starting with a letter (e.g. KANBA).',
        code: 'INVALID_CREDENTIALS',
      });
      return;
    }

    setIsSubmitting(true);
    setError(null);

    const tokenToSend = tokenRef.current;
    const trimmedEmail = email.trim();
    try {
      const result = await submitSetupClaim({
        token: tokenToSend,
        username: username.trim(),
        display_name: displayName.trim(),
        password,
        workspace_name: workspaceName.trim(),
        workspace_slug: workspaceSlug.trim(),
        project_name: projectName.trim(),
        project_key: cleanProjectKey,
        ...(trimmedEmail.length > 0 ? { email: trimmedEmail } : {}),
      });

      // Clear token from memory after claim
      tokenRef.current = null;
      setEnrollmentId(result.enrollment_id);
      setCurrentStep(2);
    } catch (err) {
      setError(formatAuthError(err));
    } finally {
      setPassword('');
      setConfirmPassword('');
      setIsSubmitting(false);
    }
  };

  // Step 2: Register Passkey
  const handleRegisterPasskey = async () => {
    if (isSubmitting || !enrollmentId) return;
    setIsSubmitting(true);
    setError(null);

    try {
      const { options } = await getWebauthnRegistrationOptions({
        enrollment_id: enrollmentId,
      });

      const creationOptions: PublicKeyCredentialCreationOptions = {
        rp: options.rp,
        user: {
          ...options.user,
          id: base64urlToBuffer(options.user.id),
        },
        challenge: base64urlToBuffer(options.challenge),
        pubKeyCredParams: options.pubKeyCredParams.map((p) => ({
          alg: p.alg,
          type: p.type as PublicKeyCredentialType,
        })),
        timeout: options.timeout ?? 60000,
        ...(options.excludeCredentials
          ? {
              excludeCredentials: options.excludeCredentials.map((c) => ({
                id: base64urlToBuffer(c.id),
                type: c.type as PublicKeyCredentialType,
              })),
            }
          : {}),
        authenticatorSelection: options.authenticatorSelection ?? {
          userVerification: 'required',
        },
      };

      const credential = (await navigator.credentials.create({
        publicKey: creationOptions,
      })) as PublicKeyCredential | null;

      if (!credential) {
        throw new Error('WEBAUTHN_FAILED');
      }

      const serialized = serializeRegistrationCredential(credential);
      const res = await verifyWebauthnRegistration({
        enrollment_id: enrollmentId,
        credential: serialized,
      });

      setRecoveryCodes(res.recovery_codes);
      setCurrentStep(3);
    } catch {
      setError({
        message: 'Passkey verification failed. Try again or use an authenticator code.',
        code: 'WEBAUTHN_FAILED',
      });
    } finally {
      setIsSubmitting(false);
    }
  };

  // Step 2: Verify TOTP Code
  const handleVerifyTotpEnroll = async (e: React.SyntheticEvent) => {
    e.preventDefault();
    if (isSubmitting || !enrollmentId) return;

    if (totpVerifyCode.length !== 6) {
      setError({ message: 'Please enter a 6-digit code.', code: 'INVALID_CREDENTIALS' });
      return;
    }

    setIsSubmitting(true);
    setError(null);

    try {
      const res = await verifyTotpEnrollment({
        enrollment_id: enrollmentId,
        code: totpVerifyCode,
      });
      setRecoveryCodes(res.recovery_codes);
      setCurrentStep(3);
    } catch (err) {
      setError(formatAuthError(err));
    } finally {
      setIsSubmitting(false);
    }
  };

  // Step 3: Copy all recovery codes
  const handleCopyCodes = async () => {
    const text = recoveryCodes.join('\n');
    const ok = await copyToClipboard(text);
    if (ok) {
      setCopiedCodes(true);
      setTimeout(() => { setCopiedCodes(false); }, 2000);
    }
  };

  // Step 3: Download recovery codes as .txt
  const handleDownloadCodes = () => {
    const text = `Kanban Recovery Codes\nGenerated: ${new Date().toISOString()}\n\n${recoveryCodes.join('\n')}\n\nKeep these codes in a secure password manager.`;
    const blob = new Blob([text], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'kanban-recovery-codes.txt';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  // Step 3: Finish and navigate to workspace
  const handleFinishSetup = () => {
    // Clear codes from memory
    setRecoveryCodes([]);
    if (onNavigate) {
      onNavigate('/');
    } else {
      window.location.assign('/');
    }
  };

  // Format base32 in 4-character chunks
  const formatBase32 = (secret: string) => {
    return secret.match(/.{1,4}/g)?.join(' ') ?? secret;
  };

  return (
    <main className="auth-container" data-testid="setup-claim-page" aria-labelledby="setup-title">
      <div className="auth-panel">
        <header className="auth-header">
          <div className="auth-header-title-row">
            <EmojiHint
              kind="restricted"
              label="About first-boot setup"
              content="First-boot installation claim. Registers the initial Server Administrator and configures mandatory second-factor credentials."
            />
            <h1 id="setup-title" className="auth-title">
              Kanban Initial Setup
            </h1>
          </div>
          {tokenValid ? (
            <div className="auth-step-pill" aria-current="step">
              Step {currentStep} of 3
            </div>
          ) : null}
        </header>

        {error ? (
          <div
            ref={alertRef}
            className="auth-alert"
            role="alert"
            tabIndex={-1}
            aria-live="assertive"
          >
            <div className="auth-alert-content">
              <span>{error.message}</span>
            </div>
            <button
              type="button"
              className="auth-copy-btn"
              onClick={() => { setError(null); }}
              aria-label="Dismiss error"
            >
              ×
            </button>
          </div>
        ) : null}

        {!tokenValid ? (
          <div className="auth-empty-state">
            <p>This setup link is invalid or has already been used.</p>
            <p>Check the container logs for the current setup URL.</p>
          </div>
        ) : currentStep === 1 ? (
          <form className="auth-form" onSubmit={(e) => { void handleClaimSubmit(e); }}>
            <div className="auth-field">
              <label className="auth-label" htmlFor="setup-username">
                Server Administrator Username
              </label>
              <input
                id="setup-username"
                className="auth-input"
                type="text"
                value={username}
                onChange={(e) => { setUsername(e.target.value); }}
                autoComplete="username"
                spellCheck="false"
                maxLength={63}
                required
                disabled={isSubmitting}
                autoFocus
              />
            </div>

            <div className="auth-field">
              <label className="auth-label" htmlFor="setup-display-name">
                Display Name
              </label>
              <input
                id="setup-display-name"
                className="auth-input"
                type="text"
                value={displayName}
                onChange={(e) => { setDisplayName(e.target.value); }}
                maxLength={120}
                required
                disabled={isSubmitting}
              />
            </div>

            <div className="auth-field">
              <label className="auth-label" htmlFor="setup-email">
                Administrator Email (optional)
              </label>
              <input
                id="setup-email"
                className="auth-input"
                type="email"
                value={email}
                onChange={(e) => { setEmail(e.target.value); }}
                autoComplete="email"
                maxLength={320}
                placeholder={`${username.trim() || 'admin'}@local.kanban`}
                disabled={isSubmitting}
              />
            </div>

            <div className="auth-field">
              <label className="auth-label" htmlFor="setup-password">
                Master Password
              </label>
              <input
                id="setup-password"
                className="auth-input"
                type="password"
                value={password}
                onChange={(e) => { setPassword(e.target.value); }}
                autoComplete="new-password"
                minLength={14}
                maxLength={1024}
                required
                disabled={isSubmitting}
              />
              <span className="auth-password-hint">
                Minimum 14 characters. Used for break-glass local administrative access.
              </span>
            </div>

            <div className="auth-field">
              <label className="auth-label" htmlFor="setup-confirm-password">
                Confirm Password
              </label>
              <input
                id="setup-confirm-password"
                className="auth-input"
                type="password"
                value={confirmPassword}
                onChange={(e) => { setConfirmPassword(e.target.value); }}
                autoComplete="new-password"
                minLength={14}
                maxLength={1024}
                required
                disabled={isSubmitting}
              />
            </div>

            <div className="auth-field">
              <label className="auth-label" htmlFor="setup-workspace-name">
                Workspace Name
              </label>
              <input
                id="setup-workspace-name"
                data-testid="setup-workspace-name"
                className="auth-input"
                type="text"
                value={workspaceName}
                onChange={(e) => { handleWorkspaceNameChange(e.target.value); }}
                maxLength={100}
                required
                disabled={isSubmitting}
              />
            </div>

            <div className="auth-field">
              <label className="auth-label" htmlFor="setup-workspace-slug">
                Workspace Slug
              </label>
              <input
                id="setup-workspace-slug"
                data-testid="setup-workspace-slug"
                className="auth-input"
                type="text"
                value={workspaceSlug}
                onChange={(e) => {
                  setSlugTouched(true);
                  setWorkspaceSlug(e.target.value.toLowerCase().replace(/[^a-z0-9_-]/g, ''));
                }}
                maxLength={64}
                required
                disabled={isSubmitting}
              />
            </div>

            <div className="auth-field">
              <label className="auth-label" htmlFor="setup-project-name">
                Initial Project Name
              </label>
              <input
                id="setup-project-name"
                data-testid="setup-project-name"
                className="auth-input"
                type="text"
                value={projectName}
                onChange={(e) => { setProjectName(e.target.value); }}
                maxLength={100}
                required
                disabled={isSubmitting}
              />
            </div>

            <div className="auth-field">
              <label className="auth-label" htmlFor="setup-project-key">
                Initial Project Key
              </label>
              <input
                id="setup-project-key"
                data-testid="setup-project-key"
                className="auth-input auth-mono"
                type="text"
                value={projectKey}
                onChange={(e) => {
                  setProjectKey(e.target.value.toUpperCase().replace(/[^A-Z0-9]/g, '').slice(0, 10));
                }}
                pattern="^[A-Z][A-Z0-9]{1,9}$"
                minLength={2}
                maxLength={10}
                placeholder="KANBA"
                required
                disabled={isSubmitting}
              />
              <span className="auth-password-hint">
                2-10 uppercase alphanumeric characters starting with a letter (e.g. KANBA).
              </span>
            </div>

            <button
              type="submit"
              className="auth-submit-btn"
              disabled={isSubmitting}
              aria-busy={isSubmitting}
            >
              {isSubmitting ? 'Creating Administrator...' : 'Claim Instance & Continue'}
            </button>
          </form>
        ) : currentStep === 2 ? (
          <div className="auth-form">
            <h2 className="auth-title auth-title-step">
              Mandatory Two-Factor Authentication Setup
            </h2>
            <p className="auth-subtitle auth-subtitle-step">
              Server Administrators must enroll a Passkey or Authenticator App before accessing
              the workspace.
            </p>

            <div className="auth-tablist" role="tablist">
              <button
                type="button"
                role="tab"
                className="auth-tab"
                aria-selected={enrollMethod === 'webauthn'}
                onClick={() => { setEnrollMethod('webauthn'); }}
              >
                Passkey (Recommended)
              </button>
              <button
                type="button"
                role="tab"
                className="auth-tab"
                aria-selected={enrollMethod === 'totp'}
                onClick={() => {
                  setEnrollMethod('totp');
                  if (!totpEnrollData) {
                    void handleStartTotpEnroll();
                  }
                }}
              >
                Authenticator App
              </button>
            </div>

            {enrollMethod === 'webauthn' ? (
              <div>
                {isPlainHttp ? (
                  <p className="auth-alert" style={{ marginBottom: 16 }}>
                    Passkeys require HTTPS. When accessing over plain HTTP, please use the Authenticator App tab.
                  </p>
                ) : null}
                {!supportsWebAuthn ? (
                  <p className="auth-empty-state">
                    This browser does not support passkeys. Please switch to the Authenticator App
                    tab.
                  </p>
                ) : (
                  <div>
                    <p className="auth-label auth-label-spacious">
                      Register your platform biometric (Touch ID / Windows Hello) or security key.
                    </p>
                    <button
                      type="button"
                      className="auth-submit-btn"
                      onClick={() => { void handleRegisterPasskey(); }}
                      disabled={isSubmitting}
                      aria-busy={isSubmitting}
                    >
                      {isSubmitting ? 'Awaiting Key...' : 'Register a passkey'}
                    </button>
                  </div>
                )}
              </div>
            ) : (
              <div>
                {totpEnrollData ? (
                  <form onSubmit={(e) => { void handleVerifyTotpEnroll(e); }}>
                    <p className="auth-label">Manual Setup Key:</p>
                    <div className="auth-setup-key-row">
                      <code className="auth-code auth-mono auth-code-lg">
                        {formatBase32(totpEnrollData.secret_base32)}
                      </code>
                      <button
                        type="button"
                        className="auth-copy-btn"
                        onClick={() => {
                          void (async () => {
                            const ok = await copyToClipboard(totpEnrollData.secret_base32);
                            if (ok) {
                              setCopiedKey(true);
                              setTimeout(() => { setCopiedKey(false); }, 2000);
                            }
                          })();
                        }}
                      >
                        {copiedKey ? 'Copied!' : 'Copy setup key'}
                      </button>
                      <button
                        type="button"
                        className="auth-copy-btn"
                        data-testid="copy-secret-btn"
                        onClick={() => {
                          void (async () => {
                            const ok = await copyToClipboard(totpEnrollData.secret_base32);
                            if (ok) {
                              setCopiedKey(true);
                              setTimeout(() => { setCopiedKey(false); }, 2000);
                            }
                          })();
                        }}
                      >
                        {copiedKey ? 'Copied Secret!' : 'Copy Secret'}
                      </button>
                    </div>

                    <p className="auth-label">Authenticator URI:</p>
                    <code className="auth-code auth-code-block">
                      {totpEnrollData.otpauth_uri}
                    </code>

                    <div className="auth-field auth-field-spacious">
                      <label className="auth-label" htmlFor="setup-totp-verify">
                        Verify 6-digit Code from Authenticator
                      </label>
                      <input
                        id="setup-totp-verify"
                        className="auth-input auth-mono"
                        type="text"
                        inputMode="numeric"
                        maxLength={6}
                        value={totpVerifyCode}
                        onChange={(e) => { setTotpVerifyCode(e.target.value.replace(/\D/g, '').slice(0, 6)); }
                        }
                        placeholder="123456"
                        required
                        disabled={isSubmitting}
                        autoFocus
                      />
                    </div>

                    <button
                      type="submit"
                      className="auth-submit-btn"
                      disabled={isSubmitting || totpVerifyCode.length !== 6}
                      aria-busy={isSubmitting}
                    >
                      {isSubmitting ? 'Verifying Code...' : 'Verify & Continue'}
                    </button>
                  </form>
                ) : (
                  <p className="auth-empty-state">Loading authenticator setup details...</p>
                )}
              </div>
            )}
          </div>
        ) : (
          <div className="auth-form">
            <div className="auth-header-title-row">
              <h2 className="auth-title auth-title-step">
                Emergency Recovery Codes
              </h2>
              <EmojiHint
                kind="restricted"
                label="About recovery codes"
                content="Each recovery code works once. They are shown only now and are stored server-side as hashes."
              />
            </div>
            <p className="auth-subtitle auth-subtitle-step">
              Store these 10 one-time recovery codes in a secure vault. If you lose access to your
              Passkey or Authenticator app, these are the ONLY way to regain administrative access.
            </p>

            <div className="auth-recovery-grid" role="list">
              {recoveryCodes.map((code, idx) => (
                <div key={idx} className="auth-recovery-code-item" role="listitem">
                  {code}
                </div>
              ))}
            </div>

            <div className="auth-recovery-actions">
              <button type="button" className="auth-copy-btn" onClick={() => { void handleCopyCodes(); }}>
                {copiedCodes ? 'Copied All!' : 'Copy all'}
              </button>
              <button type="button" className="auth-copy-btn" onClick={handleDownloadCodes}>
                Download .txt
              </button>
            </div>

            <label className="auth-checkbox-wrap">
              <input
                type="checkbox"
                checked={confirmedSaved}
                onChange={(e) => { setConfirmedSaved(e.target.checked); }}
              />
              <span>I stored these recovery codes somewhere safe</span>
            </label>

            <button
              type="button"
              className="auth-submit-btn"
              disabled={!confirmedSaved}
              onClick={handleFinishSetup}
            >
              Continue to workspace
            </button>
          </div>
        )}
      </div>
    </main>
  );
}
