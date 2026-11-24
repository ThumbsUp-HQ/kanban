// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { OAuthClientGovernanceStudio } from '../OAuthClientGovernanceStudio';
import * as oauthApi from '../oauthApi';
import * as clipboardModule from '../../../utils/clipboard';

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
  {
    client_id: 'client_unknown_app',
    client_name: 'Unknown Status App',
    client_type: 'public',
    redirect_uris: ['https://unknown.example.com/callback'],
    status: 'other' as never,
    created_at: new Date('2026-05-01T00:00:00Z').toISOString(),
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
    // Close via Done button
    fireEvent.click(screen.getByRole('button', { name: 'Done' }));
    expect(screen.queryByTestId('inspect-modal-card')).toBeNull();
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

  it('opens register OAuth client modal and registers a new client successfully', async () => {
    vi.spyOn(oauthApi, 'fetchAdminOAuthClients').mockResolvedValue(mockClients);
    const registerSpy = vi.spyOn(oauthApi, 'registerAdminOAuthClient').mockResolvedValue({
      client_id: 'client_brand_new_123',
      client_name: 'VS Code Tool',
      client_type: 'public',
      redirect_uris: ['http://127.0.0.1:9090/cb'],
      status: 'active',
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    });

    const writeTextMock = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, {
      clipboard: {
        writeText: writeTextMock,
      },
    });

    render(
      <MemoryRouter initialEntries={['/admin/oauth']}>
        <OAuthClientGovernanceStudio />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('register-client-btn')).toBeDefined();
    });

    fireEvent.click(screen.getByTestId('register-client-btn'));

    expect(screen.getByTestId('register-client-modal')).toBeDefined();
    expect(screen.getByTestId('input-client-name')).toBeDefined();
    expect(screen.getByTestId('input-redirect-uris')).toBeDefined();

    fireEvent.change(screen.getByTestId('input-client-name'), {
      target: { value: 'VS Code Tool' },
    });
    fireEvent.change(screen.getByTestId('input-redirect-uris'), {
      target: { value: 'http://127.0.0.1:9090/cb' },
    });

    fireEvent.click(screen.getByTestId('submit-register-btn'));

    await waitFor(() => {
      expect(registerSpy).toHaveBeenCalledWith({
        client_name: 'VS Code Tool',
        redirect_uris: ['http://127.0.0.1:9090/cb'],
        client_type: 'public',
        token_endpoint_auth_method: 'none',
      });
      expect(screen.getByTestId('register-success-view')).toBeDefined();
      expect(screen.getByTestId('registered-client-id').textContent).toBe('client_brand_new_123');
    });

    vi.useFakeTimers();
    const copySpy = vi.spyOn(clipboardModule, 'copyToClipboard').mockResolvedValue(true);
    await act(async () => {
      fireEvent.click(screen.getByTestId('copy-client-id-btn'));
      await vi.advanceTimersByTimeAsync(10);
    });
    expect(copySpy).toHaveBeenCalledWith('client_brand_new_123');
    expect(screen.getByTestId('copy-client-id-btn').textContent).toBe('Copied!');

    await act(async () => {
      await vi.advanceTimersByTimeAsync(2100);
    });
    expect(screen.getByTestId('copy-client-id-btn').textContent).toBe('Copy Client ID');

    // Test copy failure branch
    copySpy.mockResolvedValueOnce(false);
    await act(async () => {
      fireEvent.click(screen.getByTestId('copy-client-id-btn'));
      await vi.advanceTimersByTimeAsync(10);
    });
    expect(screen.getByTestId('copy-client-id-btn').textContent).toBe('Copy Client ID');
    vi.useRealTimers();

    fireEvent.click(screen.getByTestId('done-register-btn'));
    expect(screen.queryByTestId('register-client-modal')).toBeNull();
  });

  it('displays error in register modal when registration fails', async () => {
    vi.spyOn(oauthApi, 'fetchAdminOAuthClients').mockResolvedValue(mockClients);
    vi.spyOn(oauthApi, 'registerAdminOAuthClient').mockRejectedValue(
      new Error('Invalid redirect URI scheme'),
    );

    render(
      <MemoryRouter initialEntries={['/admin/oauth']}>
        <OAuthClientGovernanceStudio />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('register-client-btn')).toBeDefined();
    });

    fireEvent.click(screen.getByTestId('register-client-btn'));

    fireEvent.change(screen.getByTestId('input-redirect-uris'), {
      target: { value: 'http://evil.com/cb' },
    });

    fireEvent.click(screen.getByTestId('submit-register-btn'));

    await waitFor(() => {
      expect(screen.getByTestId('register-error-alert').textContent).toContain(
        'Invalid redirect URI scheme',
      );
    });

    fireEvent.click(screen.getByTestId('cancel-register-btn'));
    expect(screen.queryByTestId('modal-register-client')).toBeNull();
  });

  it('closes register modal via close button and backdrop click', async () => {
    vi.spyOn(oauthApi, 'fetchAdminOAuthClients').mockResolvedValue(mockClients);

    const { unmount } = render(
      <MemoryRouter initialEntries={['/admin/oauth']}>
        <OAuthClientGovernanceStudio />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('register-client-btn')).toBeDefined();
    });

    // Open and close via X button
    fireEvent.click(screen.getByTestId('register-client-btn'));
    expect(screen.getByTestId('register-client-modal')).toBeDefined();
    fireEvent.click(screen.getByTestId('close-register-modal-btn'));
    expect(screen.queryByTestId('register-client-modal')).toBeNull();

    // Open and close via backdrop click
    fireEvent.click(screen.getByTestId('register-client-btn'));
    expect(screen.getByTestId('register-client-modal')).toBeDefined();
    fireEvent.click(screen.getByTestId('register-modal-backdrop'));
    expect(screen.queryByTestId('register-client-modal')).toBeNull();

    unmount();
  });

  it('supports selecting private_key_jwt auth method during client registration', async () => {
    vi.spyOn(oauthApi, 'fetchAdminOAuthClients').mockResolvedValue(mockClients);
    const registerSpy = vi.spyOn(oauthApi, 'registerAdminOAuthClient').mockResolvedValue({
      client_id: 'client_jwt_123',
      client_name: undefined,
      client_type: 'public',
      status: 'active',
      redirect_uris: ['https://app.example.com/oauth/callback'],
      token_endpoint_auth_method: 'private_key_jwt',
      created_at: '2026-03-31T00:00:00Z',
    });

    render(
      <MemoryRouter initialEntries={['/admin/oauth']}>
        <OAuthClientGovernanceStudio />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('register-client-btn')).toBeDefined();
    });

    fireEvent.click(screen.getByTestId('register-client-btn'));

    // Leave client name empty to exercise default 'MCP Client' fallback
    fireEvent.change(screen.getByTestId('input-client-name'), {
      target: { value: '   ' },
    });
    fireEvent.change(screen.getByTestId('input-redirect-uris'), {
      target: { value: 'https://app.example.com/oauth/callback' },
    });
    fireEvent.change(screen.getByTestId('select-auth-method'), {
      target: { value: 'private_key_jwt' },
    });

    fireEvent.click(screen.getByTestId('submit-register-btn'));

    await waitFor(() => {
      expect(registerSpy).toHaveBeenCalledWith({
        client_name: 'MCP Client',
        redirect_uris: ['https://app.example.com/oauth/callback'],
        client_type: 'public',
        token_endpoint_auth_method: 'private_key_jwt',
      });
      expect(screen.getByTestId('registered-client-id').textContent).toContain('client_jwt_123');
    });
  });

  it('validates required redirect URIs and handles non-Error registration failure', async () => {
    vi.spyOn(oauthApi, 'fetchAdminOAuthClients').mockResolvedValue(mockClients);
    render(
      <MemoryRouter initialEntries={['/admin/oauth']}>
        <OAuthClientGovernanceStudio />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('register-client-btn')).toBeDefined();
    });

    fireEvent.click(screen.getByTestId('register-client-btn'));

    // Submit with empty URIs
    fireEvent.change(screen.getByTestId('input-redirect-uris'), { target: { value: '   ' } });
    fireEvent.click(screen.getByTestId('submit-register-btn'));
    expect(screen.getByTestId('register-error-alert').textContent).toContain(
      'At least one redirect URI is required.',
    );

    // Non-Error rejection
    vi.spyOn(oauthApi, 'registerAdminOAuthClient').mockRejectedValueOnce('raw rejection');
    fireEvent.change(screen.getByTestId('input-redirect-uris'), {
      target: { value: 'https://app.example.com/cb' },
    });
    fireEvent.click(screen.getByTestId('submit-register-btn'));
    await waitFor(() => {
      expect(screen.getByTestId('register-error-alert').textContent).toContain(
        'Failed to register OAuth client.',
      );
    });
  });

  it('handles non-Error rejection in loadClients', async () => {
    vi.spyOn(oauthApi, 'fetchAdminOAuthClients').mockRejectedValueOnce('raw network failure');
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

  it('handles non-Error rejection in approve, suspend, and revoke', async () => {
    vi.spyOn(oauthApi, 'fetchAdminOAuthClients').mockResolvedValue(mockClients);
    vi.spyOn(oauthApi, 'patchAdminOAuthClient').mockRejectedValueOnce('failed to approve');
    vi.spyOn(oauthApi, 'deleteAdminOAuthClient').mockRejectedValueOnce('failed to revoke');

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
      expect(screen.getByTestId('error-alert').textContent).toContain(
        'Failed to activate client client_pending_app.',
      );
    });

    // Suspend non-error
    vi.spyOn(oauthApi, 'patchAdminOAuthClient').mockRejectedValueOnce('failed to suspend');
    fireEvent.click(screen.getByTestId('suspend-btn-client_active_app'));
    await waitFor(() => {
      expect(screen.getByTestId('error-alert').textContent).toContain(
        'Failed to suspend client client_active_app.',
      );
    });

    // Revoke non-error
    fireEvent.click(screen.getByTestId('revoke-btn-client_active_app'));
    fireEvent.click(screen.getByTestId('confirm-revoke-client_active_app'));
    await waitFor(() => {
      expect(screen.getByTestId('error-alert').textContent).toContain(
        'Failed to revoke client client_active_app.',
      );
    });
  });

  it('registers a confidential OAuth client and displays one-time client_secret copy panel', async () => {
    vi.spyOn(oauthApi, 'fetchAdminOAuthClients').mockResolvedValue(mockClients);
    const registerSpy = vi.spyOn(oauthApi, 'registerAdminOAuthClient').mockResolvedValue({
      client_id: 'client_confidential_999',
      client_name: 'Gemini Agent Service',
      client_type: 'confidential',
      token_endpoint_auth_method: 'client_secret_basic',
      redirect_uris: ['https://gemini.google.com/oauth/callback'],
      status: 'active',
      client_secret: 'kb_ocs_secret_key_1234567890abcdef',
      client_secret_prefix: 'kb_ocs_sec...',
      created_at: new Date().toISOString(),
    });

    const copySpy = vi.spyOn(clipboardModule, 'copyToClipboard').mockResolvedValue(true);

    render(
      <MemoryRouter initialEntries={['/admin/oauth']}>
        <OAuthClientGovernanceStudio />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('register-client-btn')).toBeDefined();
    });

    fireEvent.click(screen.getByTestId('register-client-btn'));

    fireEvent.change(screen.getByTestId('input-client-name'), {
      target: { value: 'Gemini Agent Service' },
    });
    fireEvent.change(screen.getByTestId('select-client-type'), {
      target: { value: 'confidential' },
    });
    fireEvent.change(screen.getByTestId('select-auth-method'), {
      target: { value: 'client_secret_basic' },
    });
    fireEvent.change(screen.getByTestId('input-redirect-uris'), {
      target: { value: 'https://gemini.google.com/oauth/callback' },
    });

    fireEvent.click(screen.getByTestId('submit-register-btn'));

    await waitFor(() => {
      expect(registerSpy).toHaveBeenCalledWith({
        client_name: 'Gemini Agent Service',
        redirect_uris: ['https://gemini.google.com/oauth/callback'],
        client_type: 'confidential',
        token_endpoint_auth_method: 'client_secret_basic',
      });
      expect(screen.getByTestId('client-secret-panel')).toBeDefined();
      expect(screen.getByTestId('secret-warning')).toBeDefined();
      expect(screen.getByTestId('registered-client-secret').textContent).toBe(
        'kb_ocs_secret_key_1234567890abcdef',
      );
    });

    // Test copying the client secret
    vi.useFakeTimers();
    await act(async () => {
      fireEvent.click(screen.getByTestId('copy-client-secret-btn'));
      await vi.advanceTimersByTimeAsync(10);
    });
    expect(copySpy).toHaveBeenCalledWith('kb_ocs_secret_key_1234567890abcdef');
    expect(screen.getByTestId('copy-client-secret-btn').textContent).toBe('Copied!');

    await act(async () => {
      await vi.advanceTimersByTimeAsync(2100);
    });
    expect(screen.getByTestId('copy-client-secret-btn').textContent).toBe('Copy Client Secret');
    vi.useRealTimers();

    fireEvent.click(screen.getByTestId('done-register-btn'));
    expect(screen.queryByTestId('register-client-modal')).toBeNull();
  });

  it('allows editing redirect URIs on an existing client and saves changes', async () => {
    vi.spyOn(oauthApi, 'fetchAdminOAuthClients').mockResolvedValue(mockClients);
    const patchSpy = vi.spyOn(oauthApi, 'patchAdminOAuthClient').mockResolvedValue(undefined);

    render(
      <MemoryRouter initialEntries={['/admin/oauth']}>
        <OAuthClientGovernanceStudio />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('edit-uris-btn-client_active_app')).toBeDefined();
    });

    fireEvent.click(screen.getByTestId('edit-uris-btn-client_active_app'));
    expect(screen.getByTestId('edit-uris-modal')).toBeDefined();

    fireEvent.change(screen.getByTestId('input-edit-redirect-uris'), {
      target: {
        value: 'https://cursor.com/new-callback\nhttp://127.0.0.1:4567/new-callback',
      },
    });

    fireEvent.click(screen.getByTestId('submit-edit-uris-btn'));

    await waitFor(() => {
      expect(patchSpy).toHaveBeenCalledWith('client_active_app', {
        redirect_uris: [
          'https://cursor.com/new-callback',
          'http://127.0.0.1:4567/new-callback',
        ],
      });
      expect(screen.getByTestId('success-alert').textContent).toContain(
        'Redirect URIs updated for client client_active_app.',
      );
    });
  });

  it('validates edit redirect URIs modal boundary errors and cancelation', async () => {
    vi.spyOn(oauthApi, 'fetchAdminOAuthClients').mockResolvedValue(mockClients);
    render(
      <MemoryRouter initialEntries={['/admin/oauth']}>
        <OAuthClientGovernanceStudio />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('edit-uris-btn-client_active_app')).toBeDefined();
    });

    fireEvent.click(screen.getByTestId('edit-uris-btn-client_active_app'));

    // Empty URIs
    fireEvent.change(screen.getByTestId('input-edit-redirect-uris'), { target: { value: '   ' } });
    fireEvent.click(screen.getByTestId('submit-edit-uris-btn'));
    expect(screen.getByTestId('edit-uris-error').textContent).toContain(
      'At least one redirect URI is required.',
    );

    // More than 16 URIs
    const seventeenUris = Array.from(
      { length: 17 },
      (_, i) => `https://app.com/cb/${String(i)}`,
    ).join('\n');
    fireEvent.change(screen.getByTestId('input-edit-redirect-uris'), {
      target: { value: seventeenUris },
    });
    fireEvent.click(screen.getByTestId('submit-edit-uris-btn'));
    expect(screen.getByTestId('edit-uris-error').textContent).toContain(
      'Maximum 16 redirect URIs permitted.',
    );

    // Close via close button
    fireEvent.click(screen.getByTestId('close-edit-uris-btn'));
    expect(screen.queryByTestId('edit-uris-modal')).toBeNull();

    // Reopen and close via cancel button
    fireEvent.click(screen.getByTestId('edit-uris-btn-client_active_app'));
    expect(screen.getByTestId('edit-uris-modal')).toBeDefined();
    fireEvent.click(screen.getByTestId('cancel-edit-uris-btn'));
    expect(screen.queryByTestId('edit-uris-modal')).toBeNull();

    // Reopen and close via backdrop click
    fireEvent.click(screen.getByTestId('edit-uris-btn-client_active_app'));
    expect(screen.getByTestId('edit-uris-modal-backdrop')).toBeDefined();
    fireEvent.click(screen.getByTestId('edit-uris-modal-backdrop'));
    expect(screen.queryByTestId('edit-uris-modal')).toBeNull();
  });

  it('handles edit redirect URIs patch failure branches', async () => {
    vi.spyOn(oauthApi, 'fetchAdminOAuthClients').mockResolvedValue(mockClients);
    vi.spyOn(oauthApi, 'patchAdminOAuthClient').mockRejectedValueOnce(
      new Error('Invalid URI scheme'),
    );

    render(
      <MemoryRouter initialEntries={['/admin/oauth']}>
        <OAuthClientGovernanceStudio />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('edit-uris-btn-client_active_app')).toBeDefined();
    });

    fireEvent.click(screen.getByTestId('edit-uris-btn-client_active_app'));
    fireEvent.click(screen.getByTestId('submit-edit-uris-btn'));

    await waitFor(() => {
      expect(screen.getByTestId('edit-uris-error').textContent).toContain('Invalid URI scheme');
    });

    // Non-error fallback
    vi.spyOn(oauthApi, 'patchAdminOAuthClient').mockRejectedValueOnce('raw error');
    fireEvent.click(screen.getByTestId('submit-edit-uris-btn'));

    await waitFor(() => {
      expect(screen.getByTestId('edit-uris-error').textContent).toContain(
        'Failed to update redirect URIs.',
      );
    });
  });

  it('inspects client details including masked client secret prefix and auth method', async () => {
    const clientsWithSecret: oauthApi.OAuthClientItem[] = [
      {
        client_id: 'client_conf_mcp',
        client_name: 'MCP Confidential Server',
        client_type: 'confidential',
        token_endpoint_auth_method: 'client_secret_post',
        client_secret_prefix: 'kb_ocs_9988...',
        redirect_uris: ['https://mcp.example.com/oauth/callback'],
        status: 'active',
        created_at: new Date('2026-03-01T00:00:00Z').toISOString(),
      },
    ];
    vi.spyOn(oauthApi, 'fetchAdminOAuthClients').mockResolvedValue(clientsWithSecret);

    render(
      <MemoryRouter initialEntries={['/admin/oauth']}>
        <OAuthClientGovernanceStudio />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('inspect-btn-client_conf_mcp')).toBeDefined();
    });

    fireEvent.click(screen.getByTestId('inspect-btn-client_conf_mcp'));

    expect(screen.getByTestId('inspect-client-secret-prefix').textContent).toContain(
      'kb_ocs_9988... (Masked)',
    );
    expect(screen.getByText('client_secret_post')).toBeDefined();
  });

  it('handles unmounting gracefully during loadClients', async () => {
    let resolvePromise: (value: oauthApi.OAuthClientItem[]) => void = () => undefined;
    vi.spyOn(oauthApi, 'fetchAdminOAuthClients').mockImplementation(
      () =>
        new Promise((resolve) => {
          resolvePromise = resolve;
        }),
    );
    const { unmount } = render(
      <MemoryRouter initialEntries={['/admin/oauth']}>
        <OAuthClientGovernanceStudio />
      </MemoryRouter>,
    );
    unmount();
    resolvePromise(mockClients);
    await Promise.resolve();
  });
});
