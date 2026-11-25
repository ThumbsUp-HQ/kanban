// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import React, { useState, useEffect, useContext, type JSX } from 'react';
import { QueryClientContext } from '@tanstack/react-query';
import { apiClient, registerAal2StepUpHandler } from '../../api/client';
import { SecondFactorStep } from '../../features/auth/SecondFactorStep';
import type { MfaMethod } from '../../features/auth/authApi';
import './ErrorHelpHint.css';

/**
 * Periodically touches the AAL2 session while a form/drawer is dirty (KAN-404).
 * Prevents session expiry during prolonged form entry (e.g. typing LDAP DNs).
 */
export function useAal2DirtyKeepalive(isDirty: boolean): void {
  useEffect(() => {
    if (!isDirty) {
      return;
    }

    const touch = (): void => {
      void apiClient.post('/api/v1/auth/aal2/touch').catch(() => {
        // Non-blocking background keepalive probe
      });
    };

    // Immediate ping when becoming dirty
    touch();

    // Periodic ping every 45s while dirty
    const timer = setInterval(touch, 45_000);
    return () => {
      clearInterval(timer);
    };
  }, [isDirty]);
}

/**
 * Global WebSudo Modal Host (KAN-404).
 * Hosts the singleflight in-place AAL2 step-up challenge modal at z-index: 10050,
 * overlaid cleanly above any open drawers to preserve user inputs during request replay.
 */
export function WebSudoModalHost(): JSX.Element | null {
  const [isOpen, setIsOpen] = useState(false);
  const [challengeId, setChallengeId] = useState('aal2-stepup');
  const [methods, setMethods] = useState<MfaMethod[]>(['webauthn', 'totp']);
  const resolverRef = React.useRef<((success: boolean) => void) | null>(null);

  const queryClient = useContext(QueryClientContext) ?? null;

  useEffect(() => {
    registerAal2StepUpHandler((challenge) => {
      return new Promise<boolean>((resolve) => {
        setChallengeId(challenge.challengeId ?? 'aal2-stepup');
        if (challenge.methods && Array.isArray(challenge.methods)) {
          setMethods(challenge.methods as MfaMethod[]);
        }
        resolverRef.current = resolve;
        setIsOpen(true);
      });
    });

    return () => {
      registerAal2StepUpHandler(null);
    };
  }, []);

  const handleSuccess = (): void => {
    setIsOpen(false);
    if (resolverRef.current) {
      resolverRef.current(true);
      resolverRef.current = null;
    }
    if (queryClient) {
      void queryClient.invalidateQueries();
    }
    if (typeof window !== 'undefined') {
      window.dispatchEvent(new CustomEvent('kb:aal2-stepup-success'));
    }
  };

  const handleCancel = (): void => {
    setIsOpen(false);
    if (resolverRef.current) {
      resolverRef.current(false);
      resolverRef.current = null;
    }
  };

  const handleSessionExpired = (): void => {
    setIsOpen(false);
    if (resolverRef.current) {
      resolverRef.current(false);
      resolverRef.current = null;
    }
    if (typeof window !== 'undefined') {
      window.location.assign('/login');
    }
  };

  if (!isOpen) {
    return null;
  }

  return (
    <div
      className="kb-websudo-modal-backdrop"
      role="dialog"
      aria-modal="true"
      aria-labelledby="websudo-stepup-title"
      data-testid="websudo-stepup-modal"
    >
      <div className="kb-websudo-modal-container">
        <header className="kb-websudo-modal-header">
          <h2 id="websudo-stepup-title" className="kb-websudo-modal-title">
            Admin Verification Required (AAL2)
          </h2>
          <p className="kb-websudo-modal-desc">
            Your 15-minute Admin 2FA verification window (AAL2) has expired or is required.
            Verify with your Passkey or Authenticator app to continue without losing your edits.
          </p>
        </header>
        <SecondFactorStep
          challengeId={challengeId}
          methods={methods}
          onSuccess={handleSuccess}
          onError={(err) => {
            if (typeof window !== 'undefined') {
              window.dispatchEvent(
                new CustomEvent('kb:aal2-stepup-error', { detail: err }),
              );
            }
          }}
          onSessionExpired={handleSessionExpired}
          onCancel={handleCancel}
        />
      </div>
    </div>
  );
}
