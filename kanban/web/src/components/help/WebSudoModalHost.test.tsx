// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import React from 'react';
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act, renderHook } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import fs from 'node:fs';
import path from 'node:path';
import { WebSudoModalHost, useAal2DirtyKeepalive } from './WebSudoModalHost';
import { apiClient, registerAal2StepUpHandler } from '../../api/client';
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

describe('WebSudoModalHost StudioDocLink Integration (KAN-474)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    document.body.innerHTML = '';
  });

  afterEach(() => {
    document.body.innerHTML = '';
    registerAal2StepUpHandler(null);
  });

  it('renders StudioDocLink beneath kb-websudo-modal-desc with exact href and label when modal opens', async () => {
    render(<WebSudoModalHost />);

    expect(screen.queryByTestId('websudo-stepup-modal')).toBeNull();
    expect(screen.queryByTestId('websudo-doc-link')).toBeNull();

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

    const docLink = screen.getByTestId('websudo-doc-link');
    expect(docLink).toBeDefined();
    expect(docLink.getAttribute('href')).toBe('/docs/multi-card-authentication-studio');
    expect(docLink.getAttribute('aria-label')).toBe('Admin Security Architecture ->');
    expect(docLink.textContent).toContain('Admin Security Architecture ->');
    expect(docLink.className).toContain('kb-studio-doc-link');

    // Confirm doc link is placed inside the header beneath description
    const header = screen.getByTestId('websudo-stepup-modal').querySelector('.kb-websudo-modal-header');
    expect(header).toBeDefined();
    expect(header?.querySelector('.kb-websudo-modal-desc')).toBeDefined();
    expect(header?.querySelector('[data-testid="websudo-doc-link"]')).toBe(docLink);
  });

  it('opens HelpDrawer when StudioDocLink is clicked inside ShellPanelsProvider without closing or breaking WebSudo modal state', async () => {
    const DummyHelpDrawer = ({ arg }: { arg?: unknown }) => {
      const data = arg as { href?: string; title?: string } | undefined;
      return (
        <div data-testid="dummy-help-drawer" data-href={data?.href} data-title={data?.title}>
          Help Content for {data?.title} ({data?.href})
        </div>
      );
    };
    const unregister = registerShellPanel('help', DummyHelpDrawer);

    render(
      <ShellPanelsProvider>
        <WebSudoModalHost />
      </ShellPanelsProvider>,
    );

    act(() => {
      window.dispatchEvent(
        new CustomEvent('kb:open-aal2-stepup', {
          detail: { challengeId: 'ch-websudo-test', methods: ['totp'] },
        }),
      );
    });

    await waitFor(() => {
      expect(screen.getByTestId('websudo-stepup-modal')).toBeDefined();
    });

    const docLink = screen.getByTestId('websudo-doc-link');
    fireEvent.click(docLink);

    // HelpDrawer is opened
    await waitFor(() => {
      expect(screen.getByTestId('dummy-help-drawer')).toBeDefined();
    });
    const drawer = screen.getByTestId('dummy-help-drawer');
    expect(drawer.getAttribute('data-href')).toBe('/docs/multi-card-authentication-studio');
    expect(drawer.getAttribute('data-title')).toBe('Admin Security Architecture ->');

    // WebSudo modal remains intact and open
    expect(screen.getByTestId('websudo-stepup-modal')).toBeDefined();
    expect(screen.getByTestId('mock-second-factor-step')).toBeDefined();
    unregister();
  });

  it('yields Escape key to HelpDrawer when HelpDrawer is open, closing only HelpDrawer without dismissing WebSudo modal', async () => {
    let helpDrawerClosed = false;
    const DummyHelpDrawer = ({ onClose }: { onClose: () => void }) => {
      React.useEffect(() => {
        const handleKeyDown = (e: KeyboardEvent): void => {
          if (e.key === 'Escape') {
            e.stopPropagation();
            helpDrawerClosed = true;
            onClose();
          }
        };
        window.addEventListener('keydown', handleKeyDown);
        return () => {
          window.removeEventListener('keydown', handleKeyDown);
        };
      }, [onClose]);

      return (
        <div className="kb-help-drawer" data-testid="real-class-help-drawer">
          <button type="button" onClick={onClose} data-testid="close-help-drawer-btn">
            Close
          </button>
        </div>
      );
    };
    const unregister = registerShellPanel('help', DummyHelpDrawer);

    render(
      <ShellPanelsProvider>
        <WebSudoModalHost />
      </ShellPanelsProvider>,
    );

    act(() => {
      window.dispatchEvent(
        new CustomEvent('kb:open-aal2-stepup', {
          detail: { challengeId: 'ch-websudo-test', methods: ['totp'] },
        }),
      );
    });

    await waitFor(() => {
      expect(screen.getByTestId('websudo-stepup-modal')).toBeDefined();
    });

    // Click StudioDocLink to open HelpDrawer
    const docLink = screen.getByTestId('websudo-doc-link');
    fireEvent.click(docLink);

    await waitFor(() => {
      expect(screen.getByTestId('real-class-help-drawer')).toBeDefined();
    });

    // Press Escape while HelpDrawer is open in the DOM
    fireEvent.keyDown(window, { key: 'Escape' });

    // HelpDrawer received Escape and closed
    expect(helpDrawerClosed).toBe(true);

    // WebSudoModalHost remains open in DOM because it yielded to .kb-help-drawer
    expect(screen.getByTestId('websudo-stepup-modal')).toBeDefined();

    unregister();
  });

  it('verifies z-index coordination between WebSudoModalHost, HelpDrawer, and FieldHelpHint', () => {
    const helpDrawerCss = fs.readFileSync(path.resolve(__dirname, '../../features/docs-center/HelpDrawer.css'), 'utf8');
    const fieldHelpCss = fs.readFileSync(path.resolve(__dirname, 'FieldHelpHint.css'), 'utf8');
    const errorHelpCss = fs.readFileSync(path.resolve(__dirname, 'ErrorHelpHint.css'), 'utf8');

    expect(errorHelpCss).toContain('z-index: 10050');
    expect(helpDrawerCss).toContain('z-index: 10060');
    expect(helpDrawerCss).toContain('z-index: 10061');
    expect(fieldHelpCss).toContain('z-index: 10070');
  });

  it('verifies static source AST invariants: zero <FieldHelpHint> nested inside <label htmlFor> and zero inline style={{}} props in WebSudoModalHost.tsx', () => {
    const filePath = path.resolve(__dirname, 'WebSudoModalHost.tsx');
    expect(fs.existsSync(filePath)).toBe(true);
    const source = fs.readFileSync(filePath, 'utf8');

    // 1. Zero inline styles
    expect(source).not.toMatch(/style\s*=\s*\{\{/);

    // 2. Zero FieldHelpHint inside label
    expect(source).not.toContain('<FieldHelpHint');
    expect(source).not.toMatch(/<label[^>]*>[\s\S]*?<FieldHelpHint/);

    // 3. StudioDocLink presence with required props
    expect(source).toContain('<StudioDocLink');
    expect(source).toContain('href="/docs/multi-card-authentication-studio"');
    expect(source).toContain('label="Admin Security Architecture ->"');
    expect(source).toContain('testId="websudo-doc-link"');
  });

  it('verifies CSS tokens in ErrorHelpHint.css for .kb-websudo-modal-doc-link and header classes', () => {
    const cssPath = path.resolve(__dirname, 'ErrorHelpHint.css');
    const css = fs.readFileSync(cssPath, 'utf8');

    expect(css).toContain('.kb-websudo-modal-doc-link');
    expect(css).toContain('var(--space-3, 12px)');
    expect(css).toContain('.kb-websudo-modal-container');
    expect(css).toContain('z-index: 10050');
  });

  it('covers useAal2DirtyKeepalive hook when dirty is false and when dirty is true with periodic timer and error catch', () => {
    vi.useFakeTimers();
    const postSpy = vi.spyOn(apiClient, 'post').mockRejectedValue(new Error('Network probe rejected'));

    // When isDirty is false
    const { rerender, unmount } = renderHook(
      ({ dirty }) => {
        useAal2DirtyKeepalive(dirty);
      },
      {
        initialProps: { dirty: false },
      },
    );
    expect(postSpy).not.toHaveBeenCalled();

    // When isDirty becomes true -> triggers immediate probe
    rerender({ dirty: true });
    expect(postSpy).toHaveBeenCalledTimes(1);

    // Advance 45s interval
    act(() => {
      vi.advanceTimersByTime(45000);
    });
    expect(postSpy).toHaveBeenCalledTimes(2);

    unmount();
    vi.useRealTimers();
  });

  it('handles keyboard navigation and dismissal on Escape key', async () => {
    vi.spyOn(window, 'location', 'get').mockReturnValue({
      assign: vi.fn(),
    } as unknown as Location);

    const qc = new QueryClient();

    render(
      <QueryClientProvider client={qc}>
        <WebSudoModalHost />
      </QueryClientProvider>,
    );

    // Open via event without challengeId or methods
    act(() => {
      window.dispatchEvent(new CustomEvent('kb:open-aal2-stepup'));
    });
    await waitFor(() => {
      expect(screen.getByTestId('websudo-stepup-modal')).toBeDefined();
    });

    // Test tab key cycling and escape key dismissal
    fireEvent.keyDown(window, { key: 'Tab', shiftKey: false });
    fireEvent.keyDown(window, { key: 'Tab', shiftKey: true });

    // Escape closes modal
    fireEvent.keyDown(window, { key: 'Escape' });
    await waitFor(() => {
      expect(screen.queryByTestId('websudo-stepup-modal')).toBeNull();
    });
  });
});
