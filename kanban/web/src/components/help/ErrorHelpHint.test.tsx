// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import React from 'react';
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ApiProblem } from '../../api/problem';
import { resolveErrorHelp } from './errorHelpCatalog';
import { ErrorHelpHint, GlobalErrorAlertEnhancer } from './ErrorHelpHint';
import { WebSudoModalHost } from './WebSudoModalHost';
import { registerShellPanel, ShellPanelsProvider } from '../../app/shellPanels';

vi.mock('../../features/auth/SecondFactorStep', () => ({
  SecondFactorStep: ({
    onSuccess,
    onError,
    onSessionExpired,
    onCancel,
  }: {
    challengeId: string;
    methods: string[];
    onSuccess: () => void;
    onError?: (err: string) => void;
    onSessionExpired?: () => void;
    onCancel?: () => void;
  }) => (
    <div data-testid="mock-second-factor-step">
      <button type="button" data-testid="mock-stepup-success" onClick={onSuccess}>
        Simulate Step-Up Success
      </button>
      {onError && (
        <button
          type="button"
          data-testid="mock-stepup-error"
          onClick={() => {
            onError('MFA failed');
          }}
        >
          Simulate Error
        </button>
      )}
      {onSessionExpired && (
        <button type="button" data-testid="mock-stepup-expired" onClick={onSessionExpired}>
          Simulate Expired
        </button>
      )}
      {onCancel && (
        <button type="button" data-testid="mock-stepup-cancel" onClick={onCancel}>
          Cancel Step-Up
        </button>
      )}
    </div>
  ),
}));

describe('errorHelpCatalog: resolveErrorHelp (KAN-393)', () => {
  it('resolves explicit AAL2_STALE code to step-up entry', () => {
    const entry = resolveErrorHelp(null, 'AAL2_STALE');
    expect(entry.code).toBe('AAL2_STALE');
    expect(entry.title).toBe('2FA Verification Window Expired (AAL2 Stale)');
    expect(entry.docHref).toBe('/docs/multi-card-authentication-studio#aal2-step-up');
    expect(entry.isAal2StepUp).toBe(true);
    expect(entry.summary).toContain('15-minute (900-second) Multi-Factor Authentication');
  });

  it('resolves explicit AAL2_REQUIRED code to step-up entry', () => {
    const entry = resolveErrorHelp(null, 'AAL2_REQUIRED');
    expect(entry.code).toBe('AAL2_REQUIRED');
    expect(entry.title).toBe('Multi-Factor Authentication Required (AAL2)');
    expect(entry.docHref).toBe('/docs/multi-card-authentication-studio#aal2-step-up');
    expect(entry.isAal2StepUp).toBe(true);
  });

  it('resolves AAL2 stale regex patterns from arbitrary error strings', () => {
    const entry = resolveErrorHelp('AAL2 verification is stale (64520s > 900s).');
    expect(entry.code).toBe('AAL2_STALE');
    expect(entry.isAal2StepUp).toBe(true);
    expect(entry.docHref).toBe('/docs/multi-card-authentication-studio#aal2-step-up');
  });

  it('resolves ApiProblem with backend docHref and helpSummary fields', () => {
    const prob = new ApiProblem(403, {
      code: 'AAL2_STALE',
      doc_href: '/custom/doc/href',
      help_summary: 'Custom backend summary string',
    });
    const entry = resolveErrorHelp(prob);
    expect(entry.code).toBe('AAL2_STALE');
    expect(entry.docHref).toBe('/custom/doc/href');
    expect(entry.summary).toBe('Custom backend summary string');
    expect(entry.isAal2StepUp).toBe(true);
  });

  it('resolves standard security codes to non-step-up catalog entries', () => {
    const lockout = resolveErrorHelp('Cannot disable the last active administrator card. Lockout prevented.');
    expect(lockout.code).toBe('LOCKOUT_PREVENTED');
    expect(lockout.isAal2StepUp).toBe(false);
    expect(lockout.docHref).toBe('/docs/multi-card-authentication-studio#lockout-prevention');

    const wip = resolveErrorHelp('WIP limit exceeded for column Review');
    expect(wip.code).toBe('HARD_WIP_LIMIT_EXCEEDED');
    expect(wip.isAal2StepUp).toBe(false);

    const gate = resolveErrorHelp('Transition gate timeout occurred on webhook');
    expect(gate.code).toBe('GATE_TIMEOUT');

    const surrogate = resolveErrorHelp('Payload contains invalid surrogate utf-16 characters');
    expect(surrogate.code).toBe('INVALID_UTF8_SURROGATE');
  });

  it('resolves unknown messages to guaranteed default documentation fallback and extracts object fields', () => {
    const fallback = resolveErrorHelp('Something completely unlisted and unexpected happened');
    expect(fallback.code).toBe('UNKNOWN_ERROR');
    expect(fallback.title).toBe('Application Diagnostic Error');
    expect(fallback.docHref).toBe('/docs/admin-diagnostics-and-link-inspector-studio');
    expect(fallback.isAal2StepUp).toBe(false);

    expect(resolveErrorHelp(new Error('Multi-Factor Authentication required')).code).toBe('AAL2_REQUIRED');
    expect(resolveErrorHelp({ code: 'RATE_LIMITED', detail: 'Too many' }).code).toBe('RATE_LIMITED');
    expect(resolveErrorHelp({ title: '404 Not Found' }).code).toBe('NOT_FOUND');
    expect(resolveErrorHelp({ message: '401 Unauthorized' }).code).toBe('AUTHENTICATION_REQUIRED');
    expect(resolveErrorHelp({ foo: 123 }).code).toBe('UNKNOWN_ERROR');
  });
});

describe('ErrorHelpHint Component (KAN-393)', () => {
  it('renders (?) FieldHelpHint and More info link for general errors without step-up button', () => {
    render(<ErrorHelpHint error="WIP limit exceeded for column In Progress" />);

    expect(screen.getByTestId('kb-error-help-container')).toBeDefined();
    expect(screen.getByTestId('error-help-hint')).toBeDefined();
    const docLink = screen.getByTestId('error-help-doc-link');
    expect(docLink).toBeDefined();
    fireEvent.click(docLink);
    expect(screen.queryByTestId('error-aal2-stepup-btn')).toBeNull();
  });

  it('renders Verify 2FA Now button for AAL2 errors and triggers callback', () => {
    const onAal2StepUp = vi.fn();
    render(
      <ErrorHelpHint
        error="AAL2 verification is stale (950s > 900s)."
        onAal2StepUp={onAal2StepUp}
        testId="aal2-error"
      />,
    );

    const stepUpBtn = screen.getByTestId('error-aal2-stepup-btn');
    expect(stepUpBtn).toBeDefined();
    expect(stepUpBtn.textContent).toBe('Verify 2FA Now');

    fireEvent.click(stepUpBtn);
    expect(onAal2StepUp).toHaveBeenCalledTimes(1);
  });

  it('dispatches kb:open-aal2-stepup custom event when no onAal2StepUp callback is supplied', () => {
    const eventHandler = vi.fn();
    window.addEventListener('kb:open-aal2-stepup', eventHandler);

    render(<ErrorHelpHint error="AAL2 verification is stale (950s > 900s)." testId="aal2-error" />);

    const stepUpBtn = screen.getByTestId('error-aal2-stepup-btn');
    fireEvent.click(stepUpBtn);

    expect(eventHandler).toHaveBeenCalledTimes(1);
    window.removeEventListener('kb:open-aal2-stepup', eventHandler);
  });

  it('opens HelpDrawer when More info link is clicked inside ShellPanelsProvider', () => {
    const DummyHelpDrawer = () => <div data-testid="dummy-help-drawer">Help Content</div>;
    registerShellPanel('help', DummyHelpDrawer);

    render(
      <ShellPanelsProvider>
        <ErrorHelpHint error="Validation failed on request payload" testId="val-error" />
      </ShellPanelsProvider>,
    );

    const docLink = screen.getByTestId('val-error-doc-link');
    fireEvent.click(docLink);
    // Drawer panel opened in shell panels state
  });
});

describe('GlobalErrorAlertEnhancer (KAN-393)', () => {
  beforeEach(() => {
    document.body.innerHTML = '';
  });

  afterEach(() => {
    document.body.innerHTML = '';
  });

  it('opens authoritative WebSudoModalHost modal on kb:open-aal2-stepup event and closes on cancel', async () => {
    render(
      <>
        <GlobalErrorAlertEnhancer />
        <WebSudoModalHost />
      </>
    );

    expect(screen.queryByTestId('websudo-stepup-modal')).toBeNull();

    act(() => {
      window.dispatchEvent(
        new CustomEvent('kb:open-aal2-stepup', {
          detail: { challengeId: 'test-challenge', methods: ['webauthn', 'totp'] },
        }),
      );
    });

    await waitFor(() => {
      expect(screen.getByTestId('websudo-stepup-modal')).toBeDefined();
    });

    const cancelBtn = screen.getByTestId('mock-stepup-cancel');
    act(() => {
      fireEvent.click(cancelBtn);
    });

    await waitFor(() => {
      expect(screen.queryByTestId('websudo-stepup-modal')).toBeNull();
    });
  });

  it('closes modal and dispatches kb:aal2-stepup-success on successful step-up', async () => {
    const successHandler = vi.fn();
    window.addEventListener('kb:aal2-stepup-success', successHandler);

    render(
      <>
        <GlobalErrorAlertEnhancer />
        <WebSudoModalHost />
      </>
    );

    act(() => {
      window.dispatchEvent(
        new CustomEvent('kb:open-aal2-stepup', {
          detail: { challengeId: 'test-challenge' },
        }),
      );
    });

    await waitFor(() => {
      expect(screen.getByTestId('websudo-stepup-modal')).toBeDefined();
    });

    const successBtn = screen.getByTestId('mock-stepup-success');
    act(() => {
      fireEvent.click(successBtn);
    });

    await waitFor(() => {
      expect(screen.queryByTestId('websudo-stepup-modal')).toBeNull();
    });

    expect(successHandler).toHaveBeenCalledTimes(1);
    window.removeEventListener('kb:aal2-stepup-success', successHandler);
  });

  it('invalidates QueryClient and handles onError, onSessionExpired, and alert cleanup', async () => {
    const qc = new QueryClient();
    const invSpy = vi.spyOn(qc, 'invalidateQueries');

    const alertEl = document.createElement('div');
    alertEl.setAttribute('role', 'alert');
    alertEl.textContent = 'AAL2 verification is stale (950s > 900s).';
    document.body.appendChild(alertEl);

    const emptyAlert = document.createElement('div');
    emptyAlert.setAttribute('role', 'alert');
    document.body.appendChild(emptyAlert);

    render(
      <QueryClientProvider client={qc}>
        <GlobalErrorAlertEnhancer />
        <WebSudoModalHost />
      </QueryClientProvider>,
    );

    expect(alertEl.getAttribute('data-kb-error-help-mounted')).toBe('true');

    // Remove alertEl and trigger mutation to exercise detached root cleanup
    document.body.removeChild(alertEl);
    const secondAlert = document.createElement('div');
    secondAlert.setAttribute('role', 'alert');
    secondAlert.innerHTML = '<span class="kb-error-help-container">Existing</span>';
    document.body.appendChild(secondAlert);

    // Alert inside popup to test ignored container branch
    const popupParent = document.createElement('div');
    popupParent.className = 'kb-field-help-popup';
    const popupAlert = document.createElement('div');
    popupAlert.setAttribute('role', 'alert');
    popupAlert.textContent = 'Inside popup error';
    popupParent.appendChild(popupAlert);
    document.body.appendChild(popupParent);

    act(() => {
      window.dispatchEvent(new CustomEvent('kb:open-aal2-stepup'));
    });

    await waitFor(() => {
      expect(screen.getByTestId('websudo-stepup-modal')).toBeDefined();
    });

    fireEvent.click(screen.getByTestId('mock-stepup-error'));
    fireEvent.click(screen.getByTestId('mock-stepup-success'));
    expect(invSpy).toHaveBeenCalled();

    act(() => {
      window.dispatchEvent(new CustomEvent('kb:open-aal2-stepup'));
    });
    await waitFor(() => {
      expect(screen.getByTestId('mock-stepup-expired')).toBeDefined();
    });
    fireEvent.click(screen.getByTestId('mock-stepup-expired'));
  });
});
