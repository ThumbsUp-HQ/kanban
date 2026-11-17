import React, { useState, useRef, type JSX } from 'react';
import { EmojiHint } from '../../components/emoji/EmojiHint';
import type { AuthLoginResponse } from './authApi';
import { submitLocalAdminLogin, formatAuthError } from './authApi';
import './auth.css';

export interface LocalAdminDisclosureProps {
  rememberMe?: boolean;
  onSuccess: (response: AuthLoginResponse) => void;
  onError: (formattedError: ReturnType<typeof formatAuthError>) => void;
}

export function LocalAdminDisclosure({
  rememberMe = true,
  onSuccess,
  onError,
}: LocalAdminDisclosureProps): JSX.Element {
  const [isExpanded, setIsExpanded] = useState(false);
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const passwordInputRef = useRef<HTMLInputElement | null>(null);

  const handleSubmit = async (e: React.SyntheticEvent) => {
    e.preventDefault();
    if (isSubmitting) return;

    setIsSubmitting(true);
    const pwdToSend = password;

    try {
      const response = await submitLocalAdminLogin({
        username: username.trim(),
        password: pwdToSend,
        remember_me: rememberMe,
      });
      onSuccess(response);
    } catch (err) {
      onError(formatAuthError(err));
    } finally {
      // Volatile State Sanitization (Mandatory Test Case 4):
      // Overwrite password state with '' and clear DOM input value in finally block
      setPassword('');
      if (passwordInputRef.current) {
        passwordInputRef.current.value = '';
      }
      setIsSubmitting(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Escape') {
      e.preventDefault();
      setIsExpanded(false);
      triggerRef.current?.focus();
    }
  };

  return (
    <div className="auth-disclosure-container" onKeyDown={handleKeyDown}>
      <div className="auth-disclosure-header">
        <button
          ref={triggerRef}
          type="button"
          className="auth-disclosure-trigger"
          onClick={() => { setIsExpanded((prev) => !prev); }}
          aria-expanded={isExpanded}
          aria-controls="local-admin-panel"
        >
          <span aria-hidden="true">{isExpanded ? '▾' : '▸'}</span>
          <span>Sign in with Local Admin + Passkey / TOTP</span>
        </button>
        <EmojiHint
          kind="restricted"
          label="About Local Administrator sign-in"
          content="Break-glass Local Administrator. Requires password plus Passkey or TOTP (AAL2). Use only when your identity provider is unavailable."
        />
      </div>

      {isExpanded ? (
        <div id="local-admin-panel" className="auth-disclosure-panel">
          <form
            className="auth-form"
            onSubmit={(e) => {
              void handleSubmit(e);
            }}
          >
            <div className="auth-field">
              <label className="auth-label" htmlFor="local-admin-username">
                Local Administrator Username
              </label>
              <input
                id="local-admin-username"
                className="auth-input"
                type="text"
                value={username}
                onChange={(e) => { setUsername(e.target.value); }}
                autoComplete="username"
                spellCheck="false"
                maxLength={256}
                required
                disabled={isSubmitting}
                autoFocus
              />
            </div>

            <div className="auth-field">
              <div className="auth-label-row">
                <label className="auth-label" htmlFor="local-admin-password">
                  Password
                </label>
                <button
                  type="button"
                  className="auth-toggle-visibility-btn"
                  onClick={() => { setShowPassword((prev) => !prev); }}
                  aria-label={showPassword ? 'Hide' : 'Show'}
                  tabIndex={0}
                >
                  {showPassword ? 'Hide' : 'Show'}
                </button>
              </div>
              <input
                id="local-admin-password"
                ref={passwordInputRef}
                className="auth-input"
                type={showPassword ? 'text' : 'password'}
                value={password}
                onChange={(e) => { setPassword(e.target.value); }}
                aria-label="Password"
                autoComplete="current-password"
                maxLength={1024}
                required
                disabled={isSubmitting}
              />
            </div>

            <button
              type="submit"
              className="auth-submit-btn"
              disabled={isSubmitting}
              aria-busy={isSubmitting}
            >
              {isSubmitting ? 'Authenticating...' : 'Sign in as Local Administrator'}
            </button>
          </form>
        </div>
      ) : null}
    </div>
  );
}
