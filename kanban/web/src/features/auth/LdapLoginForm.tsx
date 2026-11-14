import React, { useState, useRef, type JSX } from 'react';
import type { AuthCard, AuthLoginResponse } from './authApi';
import { submitLdapLogin, formatAuthError } from './authApi';
import './auth.css';

export interface LdapLoginFormProps {
  card: AuthCard;
  formId: string;
  onSuccess: (response: AuthLoginResponse) => void;
  onError: (formattedError: ReturnType<typeof formatAuthError>) => void;
  onCollapse: () => void;
}

export function LdapLoginForm({
  card,
  formId,
  onSuccess,
  onError,
  onCollapse,
}: LdapLoginFormProps): JSX.Element {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const passwordInputRef = useRef<HTMLInputElement | null>(null);

  const handleSubmit = async (e: React.SyntheticEvent) => {
    e.preventDefault();
    if (isSubmitting) return;

    setIsSubmitting(true);
    const pwdToSend = password;

    try {
      const response = await submitLdapLogin(card.slug, {
        username: username.trim(),
        password: pwdToSend,
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
      onCollapse();
    }
  };

  return (
    <div id={formId} className="auth-disclosure-panel" onKeyDown={handleKeyDown}>
      <form
        className="auth-form"
        onSubmit={(e) => {
          void handleSubmit(e);
        }}
      >
        <div className="auth-field">
          <label className="auth-label" htmlFor={`ldap-user-${card.slug}`}>
            Username
          </label>
          <input
            id={`ldap-user-${card.slug}`}
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
          <label className="auth-label" htmlFor={`ldap-pwd-${card.slug}`}>
            Password
          </label>
          <input
            id={`ldap-pwd-${card.slug}`}
            ref={passwordInputRef}
            className="auth-input"
            type="password"
            value={password}
            onChange={(e) => { setPassword(e.target.value); }}
            autoComplete="current-password"
            maxLength={1024}
            required
            disabled={isSubmitting}
          />
        </div>

        <button
          type="submit"
          className="auth-submit-btn auth-ldap-submit-btn"
          disabled={isSubmitting}
          aria-busy={isSubmitting}
        >
          {isSubmitting ? 'Signing in...' : `Sign in to ${card.display_name}`}
        </button>
      </form>
    </div>
  );
}
