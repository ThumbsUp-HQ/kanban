// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { OAuthClientGovernanceStudio } from '../OAuthClientGovernanceStudio';
import * as oauthApi from '../oauthApi';

const mockClients: oauthApi.OAuthClientItem[] = [
  {
    client_id: 'client_active_app',
    client_name: 'Cursor IDE Assistant',
    client_type: 'confidential',
    redirect_uris: [
      'https://cursor.com/callback',
      'http://127.0.0.1:4567/callback',
      'http://127.0.0.1:4568/callback',
    ],
    status: 'active',
    created_at: new Date('2026-01-01T00:00:00Z').toISOString(),
  },
  {
    client_id: 'client_pending_app',
    client_name: 'Claude Code Agent',
    client_type: 'public',
    redirect_uris: ['http://127.0.0.1:8920/oauth/callback'],
    status: 'suspended',
    created_at: new Date('2026-02-01T00:00:00Z').toISOString(),
  },
  {
    client_id: 'client_disabled_app',
    client_name: null,
    client_type: 'public',
    redirect_uris: ['http://127.0.0.1:9999/callback'],
    status: 'disabled',
    created_at: '',
  },
  {
    client_id: 'client_revoked_app',
    client_name: 'Evil Compromised Client',
    client_type: 'public',
    redirect_uris: ['https://evil.example.com/callback'],
    status: 'revoked',
    created_at: new Date('2026-04-01T00:00:00Z').toISOString(),
  },
];

describe('OAuthClientGovernanceStudio', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('renders title, subnav, and client rows', async () => {
    vi.spyOn(oauthApi, 'fetchAdminOAuthClients').mockResolvedValue(mockClients);

    render(
      <MemoryRouter initialEntries={['/admin/oauth']}>
        <OAuthClientGovernanceStudio />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('studio-title').textContent).toContain(
        'OAuth 2.1 + PKCE Client Governance',
      );
      expect(screen.getByTestId('tab-admin-mcp')).toBeDefined();
      expect(screen.getByTestId('tab-admin-oauth')).toBeDefined();
      expect(screen.getByTestId('tab-admin-imports')).toBeDefined();
      expect(screen.getByTestId('client-name-client_active_app').textContent).toContain(
        'Cursor IDE Assistant',
      );
      expect(screen.getByTestId('client-name-client_disabled_app').textContent).toContain(
        'client_disabled_app',
      );
    });
  });

  it('handles empty clients state cleanly', async () => {
    vi.spyOn(oauthApi, 'fetchAdminOAuthClients').mockResolvedValue([]);

    render(
      <MemoryRouter initialEntries={['/admin/oauth']}>
        <OAuthClientGovernanceStudio />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('empty-clients')).toBeDefined();
    });
  });

  it('inspects client details in modal and closes modal', async () => {
    vi.spyOn(oauthApi, 'fetchAdminOAuthClients').mockResolvedValue(mockClients);

    render(
      <MemoryRouter initialEntries={['/admin/oauth']}>
        <OAuthClientGovernanceStudio />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('inspect-btn-client_active_app')).toBeDefined();
    });

    fireEvent.click(screen.getByTestId('inspect-btn-client_active_app'));
    expect(screen.getByTestId('inspect-modal-card')).toBeDefined();
    expect(screen.getByText('PKCE S256 Mandatory - Wildcard Redirects Prohibited (RFC 9700)')).toBeDefined();

    // Close modal via close button
    fireEvent.click(screen.getByTestId('close-inspect-btn'));
    expect(screen.queryByTestId('inspect-modal-card')).toBeNull();

    // Open again and click backdrop to close
    fireEvent.click(screen.getByTestId('inspect-btn-client_active_app'));
    expect(screen.getByTestId('inspect-modal-backdrop')).toBeDefined();
    fireEvent.click(screen.getByTestId('inspect-modal-backdrop'));
    expect(screen.queryByTestId('inspect-modal-card')).toBeNull();

    // Inspect client with null client_name and null updated_at
    fireEvent.click(screen.getByTestId('inspect-btn-client_disabled_app'));
    expect(screen.getByTestId('inspect-modal-card').textContent).toContain('client_disabled_app');
    fireEvent.click(screen.getByTestId('close-inspect-btn'));
  });

  it('approves / activates a suspended or disabled client', async () => {
    vi.spyOn(oauthApi, 'fetchAdminOAuthClients').mockResolvedValue(mockClients);
    const patchSpy = vi.spyOn(oauthApi, 'patchAdminOAuthClient').mockResolvedValue(undefined);

    render(
      <MemoryRouter initialEntries={['/admin/oauth']}>
        <OAuthClientGovernanceStudio />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('approve-btn-client_pending_app')).toBeDefined();
    });

    fireEvent.click(screen.getByTestId('approve-btn-client_pending_app'));

    await waitFor(() => {
      expect(patchSpy).toHaveBeenCalledWith('client_pending_app', { status: 'active' });
      expect(screen.getByTestId('success-alert').textContent).toContain(
        'Client client_pending_app activated successfully.',
      );
    });
  });

  it('suspends an active client', async () => {
    vi.spyOn(oauthApi, 'fetchAdminOAuthClients').mockResolvedValue(mockClients);
    const patchSpy = vi.spyOn(oauthApi, 'patchAdminOAuthClient').mockResolvedValue(undefined);

    render(
      <MemoryRouter initialEntries={['/admin/oauth']}>
        <OAuthClientGovernanceStudio />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('suspend-btn-client_active_app')).toBeDefined();
    });

    fireEvent.click(screen.getByTestId('suspend-btn-client_active_app'));

    await waitFor(() => {
      expect(patchSpy).toHaveBeenCalledWith('client_active_app', { status: 'suspended' });
      expect(screen.getByTestId('success-alert').textContent).toContain(
        'Client client_active_app suspended',
      );
    });
  });

  it('performs 2-step inline revocation with cancel and confirm', async () => {
    vi.spyOn(oauthApi, 'fetchAdminOAuthClients').mockResolvedValue(mockClients);
    const deleteSpy = vi.spyOn(oauthApi, 'deleteAdminOAuthClient').mockResolvedValue(undefined);

    render(
      <MemoryRouter initialEntries={['/admin/oauth']}>
        <OAuthClientGovernanceStudio />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('revoke-btn-client_active_app')).toBeDefined();
    });

    // Step 1: click revoke
    fireEvent.click(screen.getByTestId('revoke-btn-client_active_app'));
    expect(screen.getByTestId('confirm-revoke-bar-client_active_app')).toBeDefined();

    // Cancel
    fireEvent.click(screen.getByTestId('cancel-revoke-client_active_app'));
    expect(screen.queryByTestId('confirm-revoke-bar-client_active_app')).toBeNull();

    // Re-open and confirm
    fireEvent.click(screen.getByTestId('revoke-btn-client_active_app'));
    fireEvent.click(screen.getByTestId('confirm-revoke-client_active_app'));

    await waitFor(() => {
      expect(deleteSpy).toHaveBeenCalledWith('client_active_app');
      expect(screen.getByTestId('success-alert').textContent).toContain('revoked permanently');
    });
  });

  it('handles load and action errors with role="alert"', async () => {
    vi.spyOn(oauthApi, 'fetchAdminOAuthClients').mockRejectedValueOnce(new Error('Network offline'));

    const { unmount } = render(
      <MemoryRouter initialEntries={['/admin/oauth']}>
        <OAuthClientGovernanceStudio />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('error-alert').textContent).toContain('Network offline');
    });
    unmount();

    // Load error with non-Error fallback
    vi.spyOn(oauthApi, 'fetchAdminOAuthClients').mockRejectedValueOnce('Raw failure');
    render(
      <MemoryRouter initialEntries={['/admin/oauth']}>
        <OAuthClientGovernanceStudio />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('error-alert').textContent).toContain(
        'Failed to load registered OAuth clients.',
      );
    });
  });

  it('handles action patch and delete error branches', async () => {
    vi.spyOn(oauthApi, 'fetchAdminOAuthClients').mockResolvedValue(mockClients);
    vi.spyOn(oauthApi, 'patchAdminOAuthClient').mockRejectedValueOnce(new Error('Patch failed'));

    render(
      <MemoryRouter initialEntries={['/admin/oauth']}>
        <OAuthClientGovernanceStudio />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('approve-btn-client_pending_app')).toBeDefined();
    });

    fireEvent.click(screen.getByTestId('approve-btn-client_pending_app'));
    await waitFor(() => {
      expect(screen.getByTestId('error-alert').textContent).toContain('Patch failed');
    });

    // Patch error with non-Error fallback
    vi.spyOn(oauthApi, 'patchAdminOAuthClient').mockRejectedValueOnce('Unknown string error');
    fireEvent.click(screen.getByTestId('approve-btn-client_pending_app'));
    await waitFor(() => {
      expect(screen.getByTestId('error-alert').textContent).toContain(
        'Failed to activate client client_pending_app.',
      );
    });

    // Suspend error with Error and non-Error fallback
    vi.spyOn(oauthApi, 'patchAdminOAuthClient').mockRejectedValueOnce(new Error('Suspend rejected'));
    fireEvent.click(screen.getByTestId('suspend-btn-client_active_app'));
    await waitFor(() => {
      expect(screen.getByTestId('error-alert').textContent).toContain('Suspend rejected');
    });

    vi.spyOn(oauthApi, 'patchAdminOAuthClient').mockRejectedValueOnce('Suspend raw string');
    fireEvent.click(screen.getByTestId('suspend-btn-client_active_app'));
    await waitFor(() => {
      expect(screen.getByTestId('error-alert').textContent).toContain(
        'Failed to suspend client client_active_app.',
      );
    });

    // Delete error with Error and non-Error fallback
    vi.spyOn(oauthApi, 'deleteAdminOAuthClient').mockRejectedValueOnce(new Error('Delete rejected'));
    fireEvent.click(screen.getByTestId('revoke-btn-client_active_app'));
    fireEvent.click(screen.getByTestId('confirm-revoke-client_active_app'));
    await waitFor(() => {
      expect(screen.getByTestId('error-alert').textContent).toContain('Delete rejected');
    });

    vi.spyOn(oauthApi, 'deleteAdminOAuthClient').mockRejectedValueOnce('Delete raw string');
    fireEvent.click(screen.getByTestId('revoke-btn-client_active_app'));
    fireEvent.click(screen.getByTestId('confirm-revoke-client_active_app'));
    await waitFor(() => {
      expect(screen.getByTestId('error-alert').textContent).toContain(
        'Failed to revoke client client_active_app.',
      );
    });
  });

  it('handles refresh button click', async () => {
    const fetchSpy = vi
      .spyOn(oauthApi, 'fetchAdminOAuthClients')
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce(mockClients);

    render(
      <MemoryRouter initialEntries={['/admin/oauth']}>
        <OAuthClientGovernanceStudio />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(fetchSpy).toHaveBeenCalledTimes(1);
    });

    fireEvent.click(screen.getByTestId('refresh-clients-btn'));

    await waitFor(() => {
      expect(fetchSpy).toHaveBeenCalledTimes(2);
    });
  });
});
