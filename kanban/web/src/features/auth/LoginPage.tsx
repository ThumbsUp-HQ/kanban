import React, { useEffect, useState, useRef, type JSX } from 'react';
import { EmojiHint } from '../../components/emoji/EmojiHint';
import {
  fetchAuthCards,
  fetchSessionInfo,
  resolveSafeNext,
  formatAuthError,
  type AuthCard,
  type AuthLoginResponse,
  type FormattedError,
  type MfaMethod,
} from './authApi';
import { apiFetch } from '../../api/client';
import { AuthCardButton } from './AuthCardButton';
import { LdapLoginForm } from './LdapLoginForm';
import { LocalAdminDisclosure } from './LocalAdminDisclosure';
import { SecondFactorStep } from './SecondFactorStep';
import './auth.css';

export interface LoginPageProps {
  initialCards?: AuthCard[];
  initialNext?: string;
  onNavigate?: (url: string) => void;
}

export function LoginPage({
  initialCards,
  initialNext,
  onNavigate,
}: LoginPageProps): JSX.Element {
  const [cards, setCards] = useState<AuthCard[]>(initialCards ?? []);
  const [loading, setLoading] = useState(!initialCards);
  const [expandedLdapSlug, setExpandedLdapSlug] = useState<string | null>(null);
  const [rememberMe, setRememberMe] = useState(true);

  // MFA second-factor state
  const [mfaChallenge, setMfaChallenge] = useState<{
    challengeId: string;
    methods: MfaMethod[];
  } | null>(null);

  const [error, setError] = useState<FormattedError | null>(() => {
    const sp = new URLSearchParams(window.location.search);
    const hasError = sp.get('error') ?? sp.get('error_description');
    if (hasError && hasError.trim().length > 0) {
      return { message: 'Sign-in failed. Check your credentials and try again.' };
    }
    return null;
  });
  const [copiedCommand, setCopiedCommand] = useState(false);
  const copyTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    return () => {
      if (copyTimeoutRef.current) {
        clearTimeout(copyTimeoutRef.current);
      }
    };
  }, []);

  const alertRef = useRef<HTMLDivElement | null>(null);

  // Resolve safe next parameter
  const searchParams = new URLSearchParams(window.location.search);
  const rawNext = initialNext ?? searchParams.get('next') ?? '/';
  const safeNext = resolveSafeNext(rawNext);

  useEffect(() => {
    const isMounted = { current: true };
    void (async () => {
      try {
        const sessionInfo = await fetchSessionInfo();
        if (isMounted.current && sessionInfo.authenticated && sessionInfo.mfa_pending) {
          setMfaChallenge({
            challengeId: sessionInfo.session_id ?? 'session-mfa',
            methods: ['totp', 'webauthn', 'recovery'],
          });
        }
      } catch {
        // Session bootstrap error non-fatal; continue to card fetching
      }

      if (initialCards) return;

      try {
        const response = await fetchAuthCards();
        if (isMounted.current) {
          setCards(response.cards);
        }
      } catch (err) {
        if (isMounted.current) {
          setError(formatAuthError(err));
        }
      } finally {
        if (isMounted.current) {
          setLoading(false);
        }
      }
    })();

    return () => {
      isMounted.current = false;
    };
  }, [initialCards]);

  useEffect(() => {
    if (error && alertRef.current) {
      alertRef.current.focus();
    }
  }, [error]);

  const handleAuthSuccess = () => {
    if (onNavigate) {
      onNavigate(safeNext);
    } else {
      window.location.assign(safeNext);
    }
  };

  const handleLoginResponse = (response: AuthLoginResponse) => {
    setError(null);
    if (response.status === 'mfa_required') {
      setMfaChallenge({
        challengeId: response.challenge_id,
        methods: response.methods,
      });
    } else {
      handleAuthSuccess();
    }
  };

  const handleCopyUnlockCommand = async () => {
    const cmd = 'kanban-ctl auth emergency-unlock --enable-local-admin';
    try {
      await navigator.clipboard.writeText(cmd);
      setCopiedCommand(true);
      if (copyTimeoutRef.current) {
        clearTimeout(copyTimeoutRef.current);
      }
      copyTimeoutRef.current = setTimeout(() => {
        setCopiedCommand(false);
      }, 2000);
    } catch {
      // fallback
    }
  };

  // Filter top-level cards (OIDC, OAUTH2, LDAP) preserving server sort order
  const safeCards = cards;
  const topCards = safeCards.filter((c) => c.provider_kind !== 'LOCAL_ADMIN');
  const hasLocalAdmin = safeCards.some((c) => c.provider_kind === 'LOCAL_ADMIN');

  return (
    <main className="auth-container" data-testid="login-page" aria-labelledby="login-title">
      <div className="auth-panel">
        <header className="auth-header">
          <div className="auth-header-title-row">
            <EmojiHint
              kind="access"
              label="About sign-in security"
              content="Sign-in cards are listed in the order set by your Server Admin. Accounts link by card and subject ID only, never by matching email."
            />
            <h1 id="login-title" className="auth-title">
              Kanban Workspace Sign-in
            </h1>
          </div>
          <p className="auth-subtitle">
            Sign in to access your workspace tickets, docs, and projects.
          </p>
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
              {error.code === 'RATE_LIMITED' ? (
                <EmojiHint
                  kind="warning"
                  label="About sign-in rate limits"
                  content="Sign-in attempts are limited per account and per network address to block password guessing."
                />
              ) : null}
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

        {mfaChallenge ? (
          <SecondFactorStep
            challengeId={mfaChallenge.challengeId}
            methods={mfaChallenge.methods}
            onSuccess={handleAuthSuccess}
            onError={(err) => { setError(err); }}
            onSessionExpired={() => {
              setMfaChallenge(null);
              setError({
                message: 'Your sign-in session expired. Start again.',
                code: 'CHALLENGE_EXPIRED',
              });
              void apiFetch('POST', '/api/v1/auth/logout' as never).catch(() => undefined);
            }}
            onCancel={() => {
              setMfaChallenge(null);
              setError(null);
              void apiFetch('POST', '/api/v1/auth/logout' as never).catch(() => undefined);
            }}
          />
        ) : loading ? (
          <div className="auth-empty-state">Loading authentication providers...</div>
        ) : cards.length === 0 ? (
          <div className="auth-empty-state">
            <p>No sign-in methods are enabled.</p>
            <p>A Server Admin can restore access with:</p>
            <div className="auth-empty-command-box">
              <code className="auth-code">
                kanban-ctl auth emergency-unlock --enable-local-admin
              </code>
              <button
                type="button"
                className="auth-copy-btn"
                onClick={() => {
                  void handleCopyUnlockCommand();
                }}
              >
                {copiedCommand ? 'Copied!' : 'Copy'}
              </button>
            </div>
          </div>
        ) : (
          <>
            {/* Remember Me Persistent Session Option (KANBA-186) */}
            <div className="auth-remember-me-container">
              <label className="auth-checkbox-label" htmlFor="login-remember-me">
                <input
                  id="login-remember-me"
                  data-testid="login-remember-me-checkbox"
                  type="checkbox"
                  className="auth-checkbox-input"
                  checked={rememberMe}
                  onChange={(e) => { setRememberMe(e.target.checked); }}
                />
                <span className="auth-checkbox-text">Keep me signed in on this device</span>
              </label>
              <EmojiHint
                kind="access"
                label="About persistent sessions"
                content="Keeps your session active across browser restarts for up to 30 days (7 days idle). Uncheck on public or shared computers."
              />
            </div>

            {topCards.length > 0 ? (
              <div className="auth-section">
                <ul className="auth-card-list" role="list">
                  {topCards.map((card, index) => {
                    const isPrimary = index === 0;
                    const isExpanded = expandedLdapSlug === card.slug;
                    const formId = `ldap-form-${card.slug}`;

                    return (
                      <li key={card.id} className="auth-card-item">
                        <AuthCardButton
                          card={card}
                          isPrimary={isPrimary}
                          next={safeNext}
                          rememberMe={rememberMe}
                          isLdapExpanded={isExpanded}
                          onToggleLdap={() => { setExpandedLdapSlug((prev) => (prev === card.slug ? null : card.slug)); }
                          }
                          formId={formId}
                        />
                        {card.provider_kind === 'LDAP' && isExpanded ? (
                          <LdapLoginForm
                            card={card}
                            formId={formId}
                            rememberMe={rememberMe}
                            onSuccess={handleLoginResponse}
                            onError={(err) => { setError(err); }}
                            onCollapse={() => { setExpandedLdapSlug(null); }}
                          />
                        ) : null}
                      </li>
                    );
                  })}
                </ul>
              </div>
            ) : null}

            {hasLocalAdmin ? (
              <div className="auth-section">
                {topCards.length > 0 ? (
                  <div className="auth-divider">
                    <span>or Local Administrator</span>
                  </div>
                ) : null}
                <LocalAdminDisclosure
                  rememberMe={rememberMe}
                  onSuccess={handleLoginResponse}
                  onError={(err) => { setError(err); }}
                />
              </div>
            ) : null}
          </>
        )}
      </div>
    </main>
  );
}
