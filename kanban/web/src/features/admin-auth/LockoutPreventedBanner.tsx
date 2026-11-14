import React, { useRef, useEffect, useState, type JSX } from 'react';
import { EmojiHint } from '../../components/emoji/EmojiHint';
import './adminAuth.css';

export interface LockoutPreventedBannerProps {
  reasonCode?: string | null | undefined;
  detail?: string | null | undefined;
  onDismiss?: (() => void) | undefined;
}

const REASON_MESSAGES: Record<string, string> = {
  ZERO_ADMIN_CARDS:
    'Lockout prevented: disabling or deleting this card would leave zero enabled sign-in cards capable of authenticating an active Server Administrator.',
  HANDSHAKE_STALE_FOR_LOCAL_DISABLE:
    'Lockout prevented: Local Administrator cannot be disabled until at least one external Server-Admin identity provider card completes a verified login handshake within the past 15 minutes.',
};

const CLI_COMMAND = 'kanban-ctl auth emergency-unlock --enable-local-admin';
const NOOP = (): void => {
  // default onDismiss handler
};

export function LockoutPreventedBanner({
  reasonCode,
  detail,
  onDismiss = NOOP,
}: LockoutPreventedBannerProps): JSX.Element {
  const alertRef = useRef<HTMLDivElement | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    alertRef.current?.focus();
  }, []);

  const message =
    (reasonCode ? REASON_MESSAGES[reasonCode] : null) ??
    detail ??
    'Lockout prevented: this change would block Server Administrator sign-in.';

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(CLI_COMMAND);
      setCopied(true);
      setTimeout(() => {
        setCopied(false);
      }, 2000);
    } catch {
      // Fallback ignore clipboard errors
    }
  };

  return (
    <div
      ref={alertRef}
      className="auth-lockout-banner"
      role="alert"
      aria-live="assertive"
      tabIndex={-1}
    >
      <div className="auth-lockout-header">
        <div className="auth-lockout-title-row">
          <EmojiHint
            kind="warning"
            label="Lockout safeguard info"
            content="Three-layer anti-lockout safeguard (DB trigger, 15-minute IdP handshake gate, host CLI break-glass)."
          />
          <span>Security Safeguard Triggered</span>
        </div>
        <button
          type="button"
          className="auth-btn-secondary"
          onClick={onDismiss}
          aria-label="Dismiss lockout alert"
        >
          ×
        </button>
      </div>

      <p className="auth-lockout-body">{message}</p>

      <details className="auth-lockout-disclosure">
        <summary>Emergency host CLI recovery</summary>
        <div className="auth-lockout-cli-row">
          <code className="auth-lockout-code">{CLI_COMMAND}</code>
          <button
            type="button"
            className="auth-btn-secondary"
            onClick={() => {
              void handleCopy();
            }}
          >
            {copied ? 'Copied!' : 'Copy command'}
          </button>
        </div>
      </details>
    </div>
  );
}
