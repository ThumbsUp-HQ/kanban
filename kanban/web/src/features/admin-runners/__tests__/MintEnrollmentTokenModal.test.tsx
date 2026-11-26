// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import React from 'react';
import { MintEnrollmentTokenModal } from '../MintEnrollmentTokenModal';
import * as runnersApi from '../runnersAdminApi';

describe('MintEnrollmentTokenModal (KAN-458)', () => {
  const mockTokenResponse: runnersApi.EnrollmentTokenResponse = {
    id: 'tok-458',
    pool_slug: 'default',
    enrollment_token: 'kb_enroll_secret_token_458_xyz',
    expires_at: '2026-11-26T20:00:00Z',
    created_at: '2026-11-26T19:45:00Z',
  };

  beforeEach(() => {
    vi.restoreAllMocks();
    document.documentElement.removeAttribute('data-theme');
  });

  afterEach(() => {
    document.documentElement.removeAttribute('data-theme');
  });

  it('renders modal with default lifetime label and burn-on-first-use guidance', () => {
    render(<MintEnrollmentTokenModal isOpen={true} onClose={vi.fn()} />);

    // Label with default lifetime
    const ttlLabel = screen.getByText(/Token Expiration \(TTL\) \(Default: 15 minutes\)/i);
    expect(ttlLabel).toBeDefined();

    // Helper text with 15-minute (900s) lifetime, burn-on-first-enrollment, and read-only capability scopes
    const hint = screen.getByTestId('token-ttl-hint');
    expect(hint.textContent).toContain('15-minute (900s)');
    expect(hint.textContent).toContain('burn-on-first-enrollment');
    expect(hint.textContent).toContain('read-only runner capability scopes');

    // Default select value is 900
    const select = screen.getByTestId<HTMLSelectElement>('token-ttl-select');
    expect(select.value).toBe('900');
  });

  it('renders FieldHelpHint popover with 900s lifetime, burn-on-first-use security, and wiki link', () => {
    render(<MintEnrollmentTokenModal isOpen={true} onClose={vi.fn()} />);

    const helpBtn = screen.getByTestId('mint-token-ttl-help');
    expect(helpBtn).toBeDefined();
    expect(helpBtn.getAttribute('aria-label')).toContain('Token Expiration (TTL)');

    // Focus triggers popover display
    act(() => {
      helpBtn.focus();
    });

    const popover = screen.getByTestId('mint-token-ttl-help-popover');
    expect(popover).toBeDefined();
    expect(popover.textContent).toContain('15-minute (900s)');
    expect(popover.textContent).toContain('burn-on-first-enrollment');
    expect(popover.textContent).toContain('burn-on-first-use');
    expect(popover.textContent).toContain('read-only runner capability scopes');

    // Default value section
    const defaultEl = screen.getByTestId('mint-token-ttl-help-default');
    expect(defaultEl.textContent).toContain('15 minutes (900 seconds - Max)');

    // Documentation link
    const docLink = screen.getByTestId('mint-token-ttl-help-doc-link');
    expect(docLink.getAttribute('href')).toBe(
      '/docs/multi-provider-ai-engine-and-runners#runner-infrastructure-and-protocol-security',
    );
  });

  it('submits token minting request in light mode with default 15m (900s) TTL', async () => {
    document.documentElement.setAttribute('data-theme', 'light');
    const mintSpy = vi.spyOn(runnersApi, 'mintEnrollmentToken').mockResolvedValue(mockTokenResponse);
    const onTokenMinted = vi.fn();
    const onClose = vi.fn();

    render(
      <MintEnrollmentTokenModal
        isOpen={true}
        onClose={onClose}
        onTokenMinted={onTokenMinted}
      />,
    );

    fireEvent.click(screen.getByTestId('submit-mint-token-btn'));

    await waitFor(() => {
      expect(mintSpy).toHaveBeenCalledWith({
        pool_slug: 'default',
        ttl_seconds: 900,
      });
      expect(screen.getByTestId('single-reveal-token-view')).toBeDefined();
    });

    expect(screen.getByTestId('token-plaintext').textContent).toBe(
      'kb_enroll_secret_token_458_xyz',
    );

    fireEvent.click(screen.getByTestId('dismiss-mint-modal-btn'));
    expect(onClose).toHaveBeenCalled();
    expect(onTokenMinted).toHaveBeenCalled();
  });

  it('submits token minting request in dark mode with custom TTL without regressions', async () => {
    document.documentElement.setAttribute('data-theme', 'dark');
    const mintSpy = vi.spyOn(runnersApi, 'mintEnrollmentToken').mockResolvedValue({
      ...mockTokenResponse,
      pool_slug: 'gpu-pool',
    });
    const onTokenMinted = vi.fn();
    const onClose = vi.fn();

    render(
      <MintEnrollmentTokenModal
        isOpen={true}
        onClose={onClose}
        onTokenMinted={onTokenMinted}
      />,
    );

    fireEvent.change(screen.getByTestId('token-pool-slug-input'), {
      target: { value: 'gpu-pool' },
    });
    fireEvent.change(screen.getByTestId('token-ttl-select'), {
      target: { value: '300' },
    });

    fireEvent.click(screen.getByTestId('submit-mint-token-btn'));

    await waitFor(() => {
      expect(mintSpy).toHaveBeenCalledWith({
        pool_slug: 'gpu-pool',
        ttl_seconds: 300,
      });
      expect(screen.getByTestId('single-reveal-token-view')).toBeDefined();
    });

    expect(screen.getByTestId('token-plaintext').textContent).toBe(
      'kb_enroll_secret_token_458_xyz',
    );
  });

  it('does not render when isOpen is false', () => {
    const { container } = render(
      <MintEnrollmentTokenModal isOpen={false} onClose={vi.fn()} />,
    );
    expect(container.firstChild).toBeNull();
  });

  it('cancels modal when cancel button is clicked', () => {
    const onClose = vi.fn();
    render(<MintEnrollmentTokenModal isOpen={true} onClose={onClose} />);

    fireEvent.click(screen.getByTestId('cancel-mint-token-btn'));
    expect(onClose).toHaveBeenCalled();
  });
});
