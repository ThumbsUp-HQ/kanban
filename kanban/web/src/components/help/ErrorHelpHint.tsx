// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import React, {
  useEffect,
  useRef,
  useState,
  type JSX,
} from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { useQueryClient } from '@tanstack/react-query';
import { useOptionalShellPanels } from '../../app/shellPanels';
import { FieldHelpHint } from './FieldHelpHint';
import { resolveErrorHelp, type ErrorHelpEntry } from './errorHelpCatalog';
import { SecondFactorStep } from '../../features/auth/SecondFactorStep';
import type { MfaMethod } from '../../features/auth/authApi';
import './ErrorHelpHint.css';

export interface ErrorHelpHintProps {
  error?: unknown;
  code?: string;
  onAal2StepUp?: () => void;
  testId?: string;
  className?: string;
}

/**
 * Universal Error Help Hint component (KB-UX-ERROR-DOCS-AAL2, KAN-393).
 * Attaches accessible (?) FieldHelpHint, inline More info -> documentation link,
 * and prominent 'Verify 2FA Now' button for AAL2 expiration/step-up.
 */
export function ErrorHelpHint({
  error,
  code,
  onAal2StepUp,
  testId,
  className = '',
}: ErrorHelpHintProps): JSX.Element {
  const shellPanels = useOptionalShellPanels();
  const entry: ErrorHelpEntry = resolveErrorHelp(error, code);

  const handleDocClick = (e: React.MouseEvent): void => {
    e.preventDefault();
    if (shellPanels) {
      shellPanels.openPanel('help', { href: entry.docHref, title: entry.title });
    } else {
      window.location.assign(entry.docHref);
    }
  };

  const handleStepUpClick = (e: React.MouseEvent): void => {
    e.preventDefault();
    if (onAal2StepUp) {
      onAal2StepUp();
    } else {
      window.dispatchEvent(
        new CustomEvent('kb:open-aal2-stepup', {
          detail: {
            code: entry.code,
          },
        }),
      );
    }
  };

  const questionTestId = testId ? `${testId}-question` : 'error-help-hint';
  const docLinkTestId = testId ? `${testId}-doc-link` : 'error-help-doc-link';

  return (
    <span
      className={`kb-error-help-container ${className}`.trim()}
      data-testid={testId ?? 'kb-error-help-container'}
      data-kb-error-help-mounted="true"
    >
      <FieldHelpHint
        title={entry.title}
        summary={`${entry.summary} ${entry.remediation}`}
        docHref={entry.docHref}
        testId={questionTestId}
      />
      <button
        type="button"
        className="kb-error-help-doc-link"
        data-testid={docLinkTestId}
        onClick={handleDocClick}
      >
        More info &rarr;
      </button>
      {entry.isAal2StepUp && (
        <button
          type="button"
          className="kb-error-help-stepup-btn"
          data-testid="error-aal2-stepup-btn"
          onClick={handleStepUpClick}
        >
          Verify 2FA Now
        </button>
      )}
    </span>
  );
}

/**
 * Global Error Alert Enhancer (KB-UX-ERROR-DOCS-AAL2, KAN-393).
 * Mounts in AppShell to automatically attach (?) and More info -> links to all
 * [role="alert"] error elements across the application, and hosts the global
 * SecondFactorStep modal for instant AAL2 step-up.
 */
export function GlobalErrorAlertEnhancer(): JSX.Element {
  const [isStepUpOpen, setIsStepUpOpen] = useState(false);
  const [challengeId, setChallengeId] = useState('aal2-stepup');
  const [methods, setMethods] = useState<MfaMethod[]>(['webauthn', 'totp']);

  let queryClient: ReturnType<typeof useQueryClient> | null = null;
  try {
    queryClient = useQueryClient();
  } catch {
    // Outside QueryClientProvider (e.g. isolated test environments)
  }

  // Listen for global AAL2 step-up events
  useEffect(() => {
    const handleOpen = (e: Event): void => {
      const customEv = e as CustomEvent<{ challengeId?: string; methods?: MfaMethod[] }>;
      if (customEv.detail?.challengeId) {
        setChallengeId(customEv.detail.challengeId);
      }
      if (customEv.detail?.methods && Array.isArray(customEv.detail.methods)) {
        setMethods(customEv.detail.methods);
      }
      setIsStepUpOpen(true);
    };

    window.addEventListener('kb:open-aal2-stepup', handleOpen);
    return () => {
      window.removeEventListener('kb:open-aal2-stepup', handleOpen);
    };
  }, []);

  const handleStepUpSuccess = (): void => {
    setIsStepUpOpen(false);
    if (queryClient) {
      void queryClient.invalidateQueries();
    }
    window.dispatchEvent(new CustomEvent('kb:aal2-stepup-success'));
  };

  const rootsRef = useRef<Map<HTMLElement, Root>>(new Map());

  // MutationObserver to scan and enhance [role="alert"] and known error banners
  useEffect(() => {
    const selectors = [
      '[role="alert"]',
      '.kb-error-banner',
      '.auth-alert',
      '.workflow-alert-danger',
      '.kb-oauth-gov-alert-error',
      '.link-auditor-alert--error',
      '.kb-personal-settings-alert-error',
      '.kb-settings-alert-error',
    ];

    const scanAndEnhance = (): void => {
      // Clean up unmounted element roots
      rootsRef.current.forEach((root, el) => {
        if (!document.body.contains(el)) {
          try {
            root.unmount();
          } catch {
            // Ignore unmount errors on detached nodes
          }
          rootsRef.current.delete(el);
        }
      });

      const elements = document.body.querySelectorAll<HTMLElement>(selectors.join(', '));
      elements.forEach((el) => {
        if (el.getAttribute('data-kb-error-help-mounted') === 'true') {
          return;
        }
        if (
          el.closest('.kb-error-help-container') ||
          el.closest('.kb-field-help-popup') ||
          el.closest('.kb-field-help-trigger')
        ) {
          return;
        }
        if (el.querySelector('.kb-error-help-container') || el.querySelector('.field-help-hint')) {
          el.setAttribute('data-kb-error-help-mounted', 'true');
          return;
        }

        const text = (el.textContent || '').trim();
        if (!text) {
          return;
        }

        const container = document.createElement('span');
        container.className = 'kb-error-help-container';
        container.setAttribute('data-kb-enhancer-injected', 'true');
        el.appendChild(container);
        el.setAttribute('data-kb-error-help-mounted', 'true');

        try {
          const root = createRoot(container);
          rootsRef.current.set(el, root);
          root.render(<ErrorHelpHint error={text} />);
        } catch {
          // Ignore render errors in restricted environments
        }
      });
    };

    scanAndEnhance();

    const observer = new MutationObserver(() => {
      scanAndEnhance();
    });

    observer.observe(document.body, {
      childList: true,
      subtree: true,
      characterData: true,
    });

    return () => {
      observer.disconnect();
      rootsRef.current.forEach((root) => {
        try {
          root.unmount();
        } catch {
          // Ignore unmount error during teardown
        }
      });
      rootsRef.current.clear();
    };
  }, []);

  return (
    <>
      {isStepUpOpen && (
        <div
          className="kb-aal2-modal-backdrop"
          role="dialog"
          aria-modal="true"
          aria-labelledby="global-aal2-stepup-title"
          data-testid="global-aal2-stepup-modal"
        >
          <div className="kb-aal2-modal-container">
            <header className="kb-aal2-modal-header">
              <h2 id="global-aal2-stepup-title" className="kb-aal2-modal-title">
                2FA Verification Required
              </h2>
              <p className="kb-aal2-modal-desc">
                Your 15-minute Admin 2FA verification window (AAL2) has expired or is required.
                Verify with your Passkey or Authenticator app to continue.
              </p>
            </header>
            <SecondFactorStep
              challengeId={challengeId}
              methods={methods}
              onSuccess={handleStepUpSuccess}
              onError={(err) => {
                // Log or dispatch error event
                window.dispatchEvent(
                  new CustomEvent('kb:aal2-stepup-error', { detail: err }),
                );
              }}
              onSessionExpired={() => {
                setIsStepUpOpen(false);
                window.location.assign('/login');
              }}
              onCancel={() => {
                setIsStepUpOpen(false);
              }}
            />
          </div>
        </div>
      )}
    </>
  );
}
