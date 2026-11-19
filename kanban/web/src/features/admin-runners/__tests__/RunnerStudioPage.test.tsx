// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import React from 'react';
import { RunnerStudioPage } from '../RunnerStudioPage';
import { MintEnrollmentTokenModal } from '../MintEnrollmentTokenModal';
import * as runnersApi from '../runnersAdminApi';
import * as clientModule from '../../../api/client';

describe('RunnerStudioPage & Components (KANBA-219)', () => {
  const mockActiveRunner: runnersApi.RemoteRunnerResponse = {
    id: 'runner-1',
    workspace_id: 'ws-1',
    pool_slug: 'gpu-pool',
    hostname: 'runner-01.infra.internal',
    client_cert_sha256_hex: 'a1b2c3d4e5f60718293a4b5c6d7e8f90123456789abcdef0123456789abcdef0',
    cert_expires_at: '2027-01-01T00:00:00Z',
    capabilities: { os: 'linux', arch: 'x86_64', gpus: 2 },
    status: 'active',
    last_heartbeat_at: '2026-11-18T22:00:00Z',
    revoked_at: null,
    created_at: '2026-11-01T00:00:00Z',
  };

  const mockRevokedRunner: runnersApi.RemoteRunnerResponse = {
    id: 'runner-2',
    workspace_id: 'ws-1',
    pool_slug: 'default',
    hostname: 'runner-02.infra.internal',
    client_cert_sha256_hex: 'b2c3d4e5f60718293a4b5c6d7e8f90123456789abcdef0123456789abcdef01',
    cert_expires_at: '2026-12-01T00:00:00Z',
    capabilities: {},
    status: 'revoked',
    last_heartbeat_at: null,
    revoked_at: '2026-11-18T20:00:00Z',
    created_at: '2026-10-15T00:00:00Z',
  };

  const mockTokenResponse: runnersApi.EnrollmentTokenResponse = {
    id: 'tok-1',
    pool_slug: 'ci-cluster',
    enrollment_token: 'kb_enroll_secret_token_1234567890',
    expires_at: '2026-11-18T23:30:00Z',
    created_at: '2026-11-18T23:15:00Z',
  };

  beforeEach(() => {
    vi.restoreAllMocks();
  });

  describe('runnersAdminApi functions', () => {
    it('exercises all runner API helpers with and without filters', async () => {
      const fetchSpy = vi.spyOn(clientModule, 'apiFetch').mockResolvedValue([mockActiveRunner]);

      // fetch without params
      const resAll = await runnersApi.fetchRemoteRunners();
      expect(resAll).toEqual([mockActiveRunner]);
      expect(fetchSpy).toHaveBeenCalledWith('GET', '/api/v1/admin/agent-runners');

      // fetch with poolSlug and status
      fetchSpy.mockResolvedValueOnce([mockRevokedRunner]);
      const resFiltered = await runnersApi.fetchRemoteRunners('default', 'revoked');
      expect(resFiltered).toEqual([mockRevokedRunner]);
      expect(fetchSpy).toHaveBeenCalledWith(
        'GET',
        '/api/v1/admin/agent-runners?pool_slug=default&status=revoked',
      );

      // mint token
      fetchSpy.mockResolvedValueOnce(mockTokenResponse);
      const minted = await runnersApi.mintEnrollmentToken({
        pool_slug: 'ci-cluster',
        ttl_seconds: 600,
      });
      expect(minted).toEqual(mockTokenResponse);
      expect(fetchSpy).toHaveBeenCalledWith(
        'POST',
        '/api/v1/admin/agent-runners/enrollment-tokens',
        { body: { pool_slug: 'ci-cluster', ttl_seconds: 600 } },
      );

      // revoke runner
      fetchSpy.mockResolvedValueOnce({
        id: 'runner-1',
        status: 'revoked',
        revoked_at: '2026-11-18T23:00:00Z',
      });
      const revoked = await runnersApi.revokeRemoteRunner('runner-1');
      expect(revoked.status).toBe('revoked');
      expect(fetchSpy).toHaveBeenCalledWith('POST', '/api/v1/admin/agent-runners/runner-1:revoke');
    });
  });

  describe('RunnerStudioPage component', () => {
    it('renders runner cards, status filters, and handles revocation flow', async () => {
      vi.spyOn(runnersApi, 'fetchRemoteRunners').mockResolvedValue([
        mockActiveRunner,
        mockRevokedRunner,
      ]);
      const revokeSpy = vi.spyOn(runnersApi, 'revokeRemoteRunner').mockResolvedValue({
        id: 'runner-1',
        status: 'revoked',
        revoked_at: '2026-11-18T23:00:00Z',
      });

      render(<RunnerStudioPage />);

      expect(screen.getByTestId('runner-studio-loading')).toBeDefined();

      await waitFor(() => {
        expect(screen.getByText('runner-01.infra.internal')).toBeDefined();
        expect(screen.getByText('runner-02.infra.internal')).toBeDefined();
      });

      expect(screen.getByTestId('runner-status-runner-1').textContent).toBe('active');
      expect(screen.getByTestId('runner-status-runner-2').textContent).toBe('revoked');

      // Check capabilities chip on active runner
      expect(screen.getByText('os: linux')).toBeDefined();
      expect(screen.getByText('gpus: 2')).toBeDefined();

      // Revoked button is disabled
      const revokedBtn = screen.getByTestId<HTMLButtonElement>('revoke-runner-btn-runner-2');
      expect(revokedBtn.disabled).toBe(true);
      expect(revokedBtn.textContent).toBe('Revoked');

      // Test status filter buttons
      fireEvent.click(screen.getByTestId('filter-active-btn'));
      await waitFor(() => {
        expect(runnersApi.fetchRemoteRunners).toHaveBeenCalledWith(undefined, 'active');
      });

      fireEvent.click(screen.getByTestId('filter-revoked-btn'));
      await waitFor(() => {
        expect(runnersApi.fetchRemoteRunners).toHaveBeenCalledWith(undefined, 'revoked');
      });

      fireEvent.click(screen.getByTestId('filter-offline-btn'));
      await waitFor(() => {
        expect(runnersApi.fetchRemoteRunners).toHaveBeenCalledWith(undefined, 'offline');
      });

      fireEvent.click(screen.getByTestId('filter-all-btn'));
      await waitFor(() => {
        expect(runnersApi.fetchRemoteRunners).toHaveBeenCalledWith(undefined, undefined);
      });

      // Open revocation modal and cancel
      fireEvent.click(screen.getByTestId('revoke-runner-btn-runner-1'));
      expect(screen.getByTestId('revoke-runner-modal')).toBeDefined();
      expect(screen.getByText(/Immediate Disconnect/)).toBeDefined();

      fireEvent.click(screen.getByTestId('cancel-revoke-btn'));
      expect(screen.queryByTestId('revoke-runner-modal')).toBeNull();

      // Open revocation modal and confirm
      fireEvent.click(screen.getByTestId('revoke-runner-btn-runner-1'));
      fireEvent.click(screen.getByTestId('confirm-revoke-btn'));

      await waitFor(() => {
        expect(revokeSpy).toHaveBeenCalledWith('runner-1');
      });
    });

    it('renders empty placeholder when 0 runners match filter', async () => {
      vi.spyOn(runnersApi, 'fetchRemoteRunners').mockResolvedValue([]);

      render(<RunnerStudioPage />);

      await waitFor(() => {
        expect(screen.getByTestId('empty-runners-placeholder')).toBeDefined();
      });
    });

    it('renders error message when loading fails', async () => {
      vi.spyOn(runnersApi, 'fetchRemoteRunners').mockRejectedValue(new Error('mTLS daemon down'));

      render(<RunnerStudioPage />);

      await waitFor(() => {
        expect(screen.getByTestId('runner-studio-error').textContent).toContain('mTLS daemon down');
      });
    });

    it('handles revocation failure gracefully with Error instance and non-Error rejection', async () => {
      vi.spyOn(runnersApi, 'fetchRemoteRunners').mockResolvedValue([mockActiveRunner]);
      const revokeSpy = vi.spyOn(runnersApi, 'revokeRemoteRunner').mockRejectedValue(
        new Error('AAL2 authentication required'),
      );

      render(<RunnerStudioPage />);

      await waitFor(() => {
        expect(screen.getByTestId('revoke-runner-btn-runner-1')).toBeDefined();
      });

      fireEvent.click(screen.getByTestId('revoke-runner-btn-runner-1'));
      fireEvent.click(screen.getByTestId('confirm-revoke-btn'));

      await waitFor(() => {
        expect(screen.getByTestId('runner-studio-error').textContent).toContain(
          'AAL2 authentication required',
        );
      });

      // Also non-Error rejection
      revokeSpy.mockRejectedValueOnce('raw revoke string error');
      fireEvent.click(screen.getByTestId('revoke-runner-btn-runner-1'));
      fireEvent.click(screen.getByTestId('confirm-revoke-btn'));

      await waitFor(() => {
        expect(screen.getByTestId('runner-studio-error').textContent).toContain(
          'Failed to revoke remote runner',
        );
      });
    });

    it('handles load failure gracefully with non-Error rejection', async () => {
      vi.spyOn(runnersApi, 'fetchRemoteRunners').mockRejectedValue('raw runner load error');

      render(<RunnerStudioPage />);

      await waitFor(() => {
        expect(screen.getByTestId('runner-studio-error').textContent).toContain(
          'Failed to load remote runners',
        );
      });
    });

    it('opens mint enrollment token modal on button click', async () => {
      vi.spyOn(runnersApi, 'fetchRemoteRunners').mockResolvedValue([mockActiveRunner]);

      render(<RunnerStudioPage />);

      await waitFor(() => {
        expect(screen.getByTestId('open-mint-modal-btn')).toBeDefined();
      });

      fireEvent.click(screen.getByTestId('open-mint-modal-btn'));
      expect(screen.getByTestId('mint-enrollment-token-modal')).toBeDefined();

      fireEvent.click(screen.getByTestId('close-mint-modal-btn'));
      expect(screen.queryByTestId('mint-enrollment-token-modal')).toBeNull();
    });
  });

  describe('MintEnrollmentTokenModal component', () => {
    it('returns null when isOpen is false', () => {
      const { container } = render(
        <MintEnrollmentTokenModal isOpen={false} onClose={vi.fn()} />,
      );
      expect(container.firstChild).toBeNull();
    });

    it('validates pool slug format', async () => {
      render(
        <MintEnrollmentTokenModal isOpen={true} onClose={vi.fn()} />,
      );

      fireEvent.change(screen.getByTestId('token-pool-slug-input'), {
        target: { value: 'INVALID_SLUG!' },
      });
      fireEvent.click(screen.getByTestId('submit-mint-token-btn'));

      await waitFor(() => {
        expect(screen.getByTestId('mint-token-error').textContent).toContain("Pool slug must match '^[a-z0-9]");
      });
    });

    it('mints token, displays single-reveal view, copies to clipboard, and closes', async () => {
      const mintSpy = vi.spyOn(runnersApi, 'mintEnrollmentToken').mockResolvedValue(mockTokenResponse);
      const onTokenMinted = vi.fn();
      const onClose = vi.fn();

      // Mock navigator clipboard
      const writeTextMock = vi.fn().mockResolvedValue(undefined);
      Object.assign(navigator, {
        clipboard: {
          writeText: writeTextMock,
        },
      });

      render(
        <MintEnrollmentTokenModal
          isOpen={true}
          onClose={onClose}
          onTokenMinted={onTokenMinted}
        />,
      );

      fireEvent.change(screen.getByTestId('token-pool-slug-input'), {
        target: { value: 'ci-cluster' },
      });
      fireEvent.change(screen.getByTestId('token-ttl-select'), {
        target: { value: '600' },
      });

      fireEvent.click(screen.getByTestId('submit-mint-token-btn'));

      await waitFor(() => {
        expect(mintSpy).toHaveBeenCalledWith({
          pool_slug: 'ci-cluster',
          ttl_seconds: 600,
        });
        expect(screen.getByTestId('single-reveal-token-view')).toBeDefined();
      });

      expect(screen.getByTestId('single-reveal-warning')).toBeDefined();
      expect(screen.getByTestId('token-plaintext').textContent).toBe(
        'kb_enroll_secret_token_1234567890',
      );

      // Click copy button
      fireEvent.click(screen.getByTestId('copy-token-btn'));
      expect(writeTextMock).toHaveBeenCalledWith('kb_enroll_secret_token_1234567890');

      await waitFor(() => {
        expect(screen.getByTestId('copy-token-btn').textContent).toContain('Copied');
      });

      // Dismiss modal
      fireEvent.click(screen.getByTestId('dismiss-mint-modal-btn'));
      expect(onClose).toHaveBeenCalled();
      expect(onTokenMinted).toHaveBeenCalled();
    });

    it('handles clipboard failure gracefully and sets copied state', async () => {
      vi.spyOn(runnersApi, 'mintEnrollmentToken').mockResolvedValue(mockTokenResponse);

      // Clipboard absent
      Object.defineProperty(navigator, 'clipboard', { value: undefined, configurable: true });

      render(
        <MintEnrollmentTokenModal isOpen={true} onClose={vi.fn()} />,
      );

      fireEvent.click(screen.getByTestId('submit-mint-token-btn'));

      await waitFor(() => {
        expect(screen.getByTestId('copy-token-btn')).toBeDefined();
      });

      fireEvent.click(screen.getByTestId('copy-token-btn'));
      await waitFor(() => {
        expect(screen.getByTestId('copy-token-btn').textContent).toContain('Copied');
      });

      // Dismiss without onTokenMinted callback provided
      fireEvent.click(screen.getByTestId('dismiss-mint-modal-btn'));
    });

    it('handles unmount during load in RunnerStudioPage (resolve and reject)', () => {
      let resolveRunners!: (v: runnersApi.RemoteRunnerResponse[]) => void;
      vi.spyOn(runnersApi, 'fetchRemoteRunners').mockReturnValue(
        new Promise((resolve) => {
          resolveRunners = resolve;
        }),
      );

      const page1 = render(<RunnerStudioPage />);
      page1.unmount();
      resolveRunners([mockActiveRunner]);

      let rejectRunners!: (e: unknown) => void;
      vi.spyOn(runnersApi, 'fetchRemoteRunners').mockReturnValue(
        new Promise((_, reject) => {
          rejectRunners = reject;
        }),
      );

      const page2 = render(<RunnerStudioPage />);
      page2.unmount();
      rejectRunners(new Error('unmounted reject'));
    });

    it('resets copied state after 2 seconds', async () => {
      vi.spyOn(runnersApi, 'mintEnrollmentToken').mockResolvedValue(mockTokenResponse);
      render(<MintEnrollmentTokenModal isOpen={true} onClose={vi.fn()} />);
      fireEvent.click(screen.getByTestId('submit-mint-token-btn'));
      await waitFor(() => {
        expect(screen.getByTestId('copy-token-btn')).toBeDefined();
      });
      fireEvent.click(screen.getByTestId('copy-token-btn'));
      await waitFor(() => {
        expect(screen.getByTestId('copy-token-btn').textContent).toContain('Copied');
      });

      await new Promise((r) => setTimeout(r, 2100));
      await waitFor(() => {
        expect(screen.getByTestId('copy-token-btn').textContent).toBe('Copy');
      });

      // Dismiss without onTokenMinted callback provided
      fireEvent.click(screen.getByTestId('dismiss-mint-modal-btn'));
    }, 6000);

    it('handles non-Error rejection on minting token', async () => {
      vi.spyOn(runnersApi, 'mintEnrollmentToken').mockRejectedValue('raw token mint fail');

      render(
        <MintEnrollmentTokenModal isOpen={true} onClose={vi.fn()} />,
      );

      fireEvent.click(screen.getByTestId('submit-mint-token-btn'));

      await waitFor(() => {
        expect(screen.getByTestId('mint-token-error').textContent).toContain(
          'Failed to mint enrollment token',
        );
      });
    });

    it('handles minting api error', async () => {
      vi.spyOn(runnersApi, 'mintEnrollmentToken').mockRejectedValue(
        new Error('Token pool quota exceeded'),
      );

      render(
        <MintEnrollmentTokenModal isOpen={true} onClose={vi.fn()} />,
      );

      fireEvent.click(screen.getByTestId('submit-mint-token-btn'));

      await waitFor(() => {
        expect(screen.getByTestId('mint-token-error').textContent).toContain(
          'Token pool quota exceeded',
        );
      });
    });

    it('handles cancel button before minting', () => {
      const onClose = vi.fn();
      render(
        <MintEnrollmentTokenModal isOpen={true} onClose={onClose} />,
      );

      fireEvent.click(screen.getByTestId('cancel-mint-token-btn'));
      expect(onClose).toHaveBeenCalled();
    });
  });
});
