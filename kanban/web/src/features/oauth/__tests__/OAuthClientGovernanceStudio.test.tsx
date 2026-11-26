// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import React from 'react';
import fs from 'node:fs';
import path from 'node:path';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { OAuthClientGovernanceStudio } from '../OAuthClientGovernanceStudio';
import * as oauthApi from '../oauthApi';
import { ApiProblem } from '../../../api/problem';
import { Aal2StepUpCancelledError } from '../../../api/client';
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

  it('renders ErrorHelpHint on AAL2_STALE or AAL2_REQUIRED error', async () => {
    const aal2Prob = new ApiProblem(403, {
      code: 'AAL2_STALE',
      detail: 'AAL2 verification is stale (950s > 900s).',
      challenge_id: 'chall-oauth-aal2',
      methods: ['totp'],
    });

    vi.spyOn(oauthApi, 'fetchAdminOAuthClients').mockRejectedValueOnce(aal2Prob);

    render(
      <MemoryRouter initialEntries={['/admin/oauth']}>
        <OAuthClientGovernanceStudio />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('error-alert')).toBeDefined();
      expect(screen.getByTestId('error-help-doc-link')).toBeDefined();
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
      expect(registerSpy).toHaveBeenCalledWith(
        expect.objectContaining({
          client_name: 'VS Code Tool',
          redirect_uris: ['http://127.0.0.1:9090/cb'],
          client_type: 'public',
          token_endpoint_auth_method: 'none',
          pkce_enforce: true,
          access_token_ttl: 3600,
          grant_types: ['authorization_code', 'refresh_token'],
        }),
      );
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
      expect(registerSpy).toHaveBeenCalledWith(
        expect.objectContaining({
          client_name: 'MCP Client',
          redirect_uris: ['https://app.example.com/oauth/callback'],
          client_type: 'public',
          token_endpoint_auth_method: 'private_key_jwt',
          pkce_enforce: true,
          access_token_ttl: 3600,
          grant_types: ['authorization_code', 'refresh_token'],
        }),
      );
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
      expect(registerSpy).toHaveBeenCalledWith(
        expect.objectContaining({
          client_name: 'Gemini Agent Service',
          redirect_uris: ['https://gemini.google.com/oauth/callback'],
          client_type: 'confidential',
          token_endpoint_auth_method: 'client_secret_basic',
          pkce_enforce: true,
          access_token_ttl: 3600,
          grant_types: ['authorization_code', 'refresh_token'],
        }),
      );
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

  it('handles row selection, select all, and bulk delete flows', async () => {
    vi.spyOn(oauthApi, 'fetchAdminOAuthClients').mockResolvedValue(mockClients);
    const bulkDeleteSpy = vi
      .spyOn(oauthApi, 'bulkDeleteAdminOAuthClients')
      .mockResolvedValue({ deleted_count: 2, deleted_client_ids: ['client_active_app', 'client_pending_app'] });

    render(
      <MemoryRouter initialEntries={['/admin/oauth']}>
        <OAuthClientGovernanceStudio />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('select-all-clients-checkbox')).toBeDefined();
    });

    // Select all
    fireEvent.click(screen.getByTestId('select-all-clients-checkbox'));
    expect(screen.getByTestId('delete-selected-btn')).toBeDefined();

    // Toggle select all off
    fireEvent.click(screen.getByTestId('select-all-clients-checkbox'));
    expect(screen.queryByTestId('delete-selected-btn')).toBeNull();

    // Select single row
    fireEvent.click(screen.getByTestId('select-client-checkbox-client_active_app'));
    expect(screen.getByTestId('delete-selected-btn')).toBeDefined();

    // Unselect single row
    fireEvent.click(screen.getByTestId('select-client-checkbox-client_active_app'));
    expect(screen.queryByTestId('delete-selected-btn')).toBeNull();

    // Select single row and trigger bulk delete cancel
    fireEvent.click(screen.getByTestId('select-client-checkbox-client_active_app'));
    fireEvent.click(screen.getByTestId('delete-selected-btn'));
    expect(screen.getByTestId('cancel-bulk-delete-btn')).toBeDefined();
    fireEvent.click(screen.getByTestId('cancel-bulk-delete-btn'));
    expect(screen.queryByTestId('cancel-bulk-delete-btn')).toBeNull();

    // Trigger bulk delete confirm
    fireEvent.click(screen.getByTestId('delete-selected-btn'));
    fireEvent.click(screen.getByTestId('confirm-bulk-delete-btn'));

    await waitFor(() => {
      expect(bulkDeleteSpy).toHaveBeenCalledWith({ client_ids: ['client_active_app'] });
      expect(screen.getByTestId('success-alert').textContent).toContain('Permanently deleted 2 selected');
    });

    // Bulk delete error branch with Error and non-Error fallback
    bulkDeleteSpy.mockRejectedValueOnce(new Error('Bulk delete forbidden'));
    fireEvent.click(screen.getByTestId('select-client-checkbox-client_active_app'));
    fireEvent.click(screen.getByTestId('delete-selected-btn'));
    fireEvent.click(screen.getByTestId('confirm-bulk-delete-btn'));
    await waitFor(() => {
      expect(screen.getByTestId('error-alert').textContent).toContain('Bulk delete forbidden');
    });

    bulkDeleteSpy.mockRejectedValueOnce('Raw bulk delete error');
    fireEvent.click(screen.getByTestId('delete-selected-btn'));
    fireEvent.click(screen.getByTestId('confirm-bulk-delete-btn'));
    await waitFor(() => {
      expect(screen.getByTestId('error-alert').textContent).toContain('Failed to delete selected OAuth clients.');
    });
  });

  it('handles purge unused/revoked clients flow', async () => {
    vi.spyOn(oauthApi, 'fetchAdminOAuthClients').mockResolvedValue(mockClients);
    const purgeSpy = vi
      .spyOn(oauthApi, 'bulkDeleteAdminOAuthClients')
      .mockResolvedValue({ deleted_count: 5, deleted_client_ids: ['d1', 'd2', 'd3', 'd4', 'd5'] });

    render(
      <MemoryRouter initialEntries={['/admin/oauth']}>
        <OAuthClientGovernanceStudio />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('purge-clients-btn')).toBeDefined();
    });

    // Click purge, then cancel
    fireEvent.click(screen.getByTestId('purge-clients-btn'));
    expect(screen.getByTestId('cancel-purge-btn')).toBeDefined();
    fireEvent.click(screen.getByTestId('cancel-purge-btn'));
    expect(screen.queryByTestId('cancel-purge-btn')).toBeNull();

    // Click purge, then confirm
    fireEvent.click(screen.getByTestId('purge-clients-btn'));
    fireEvent.click(screen.getByTestId('confirm-purge-btn'));

    await waitFor(() => {
      expect(purgeSpy).toHaveBeenCalledWith({ purge_unused_dcr: true, purge_revoked: true });
      expect(screen.getByTestId('success-alert').textContent).toContain('Purged 5 unused DCR and revoked');
    });

    // Purge error branch with Error and non-Error fallback
    purgeSpy.mockRejectedValueOnce(new Error('Purge database locked'));
    fireEvent.click(screen.getByTestId('purge-clients-btn'));
    fireEvent.click(screen.getByTestId('confirm-purge-btn'));
    await waitFor(() => {
      expect(screen.getByTestId('error-alert').textContent).toContain('Purge database locked');
    });

    purgeSpy.mockRejectedValueOnce('Raw purge failure');
    fireEvent.click(screen.getByTestId('purge-clients-btn'));
    fireEvent.click(screen.getByTestId('confirm-purge-btn'));
    await waitFor(() => {
      expect(screen.getByTestId('error-alert').textContent).toContain('Failed to purge stale OAuth clients.');
    });
  });

  it('handles row-level permanent delete flow with cancel, confirm, and errors', async () => {
    vi.spyOn(oauthApi, 'fetchAdminOAuthClients').mockResolvedValue(mockClients);
    const deleteSpy = vi.spyOn(oauthApi, 'deleteAdminOAuthClient').mockResolvedValue(undefined);

    render(
      <MemoryRouter initialEntries={['/admin/oauth']}>
        <OAuthClientGovernanceStudio />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('delete-btn-client_active_app')).toBeDefined();
    });

    // Click Delete, then Cancel
    fireEvent.click(screen.getByTestId('delete-btn-client_active_app'));
    expect(screen.getByTestId('cancel-delete-client_active_app')).toBeDefined();
    fireEvent.click(screen.getByTestId('cancel-delete-client_active_app'));
    expect(screen.queryByTestId('cancel-delete-client_active_app')).toBeNull();

    // Click Delete, then Confirm
    fireEvent.click(screen.getByTestId('delete-btn-client_active_app'));
    fireEvent.click(screen.getByTestId('confirm-delete-client_active_app'));

    await waitFor(() => {
      expect(deleteSpy).toHaveBeenCalledWith('client_active_app', { permanent: true });
      expect(screen.getByTestId('success-alert').textContent).toContain('permanently deleted');
    });

    // Delete error with Error and non-Error fallback
    deleteSpy.mockRejectedValueOnce(new Error('Cannot delete client'));
    fireEvent.click(screen.getByTestId('delete-btn-client_pending_app'));
    fireEvent.click(screen.getByTestId('confirm-delete-client_pending_app'));
    await waitFor(() => {
      expect(screen.getByTestId('error-alert').textContent).toContain('Cannot delete client');
    });

    deleteSpy.mockRejectedValueOnce('Raw delete error');
    fireEvent.click(screen.getByTestId('delete-btn-client_pending_app'));
    fireEvent.click(screen.getByTestId('confirm-delete-client_pending_app'));
    await waitFor(() => {
      expect(screen.getByTestId('error-alert').textContent).toContain('Failed to delete client client_pending_app.');
    });
  });

  it('handles search input, status filter pills, and pagination controls', async () => {
    const fetchSpy = vi.spyOn(oauthApi, 'fetchAdminOAuthClients').mockResolvedValue({
      items: mockClients,
      total: 105,
      limit: 50,
      offset: 0,
    });

    render(
      <MemoryRouter initialEntries={['/admin/oauth']}>
        <OAuthClientGovernanceStudio />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('search-clients-input')).toBeDefined();
    });

    // Change search query
    fireEvent.change(screen.getByTestId('search-clients-input'), {
      target: { value: 'Claude' },
    });
    await waitFor(() => {
      expect(fetchSpy).toHaveBeenCalledWith(
        expect.objectContaining({ q: 'Claude' }),
      );
    });

    // Change status filter pills
    fireEvent.click(screen.getByTestId('filter-pill-active'));
    await waitFor(() => {
      expect(fetchSpy).toHaveBeenCalledWith(
        expect.objectContaining({ status: 'active' }),
      );
    });

    fireEvent.click(screen.getByTestId('filter-pill-suspended'));
    await waitFor(() => {
      expect(fetchSpy).toHaveBeenCalledWith(
        expect.objectContaining({ status: 'suspended' }),
      );
    });

    fireEvent.click(screen.getByTestId('filter-pill-revoked'));
    await waitFor(() => {
      expect(fetchSpy).toHaveBeenCalledWith(
        expect.objectContaining({ status: 'revoked' }),
      );
    });

    fireEvent.click(screen.getByTestId('filter-pill-all'));
    await waitFor(() => {
      expect(fetchSpy).toHaveBeenCalledWith(
        expect.objectContaining({ status: 'all' }),
      );
    });

    // Pagination: Next and Prev
    expect(screen.getByTestId('pagination-info').textContent).toContain('Showing 1-50 of 105');
    fireEvent.click(screen.getByTestId('next-page-btn'));
    await waitFor(() => {
      expect(fetchSpy).toHaveBeenCalledWith(
        expect.objectContaining({ offset: 50 }),
      );
    });

    fireEvent.click(screen.getByTestId('prev-page-btn'));
    await waitFor(() => {
      expect(fetchSpy).toHaveBeenCalledWith(
        expect.objectContaining({ offset: 0 }),
      );
    });
  });

  it('ignores Aal2StepUpCancelledError gracefully in loadClients and actions', async () => {
    vi.spyOn(oauthApi, 'fetchAdminOAuthClients').mockRejectedValueOnce(new Aal2StepUpCancelledError());

    render(
      <MemoryRouter initialEntries={['/admin/oauth']}>
        <OAuthClientGovernanceStudio />
      </MemoryRouter>,
    );

    // No error alert rendered when step-up is cancelled
    await waitFor(() => {
      expect(screen.queryByTestId('error-alert')).toBeNull();
    expect(screen.queryByRole('alert')).toBeNull();
      expect(screen.queryByRole('alert')).toBeNull();
    });

    // Also in action handlers
    vi.spyOn(oauthApi, 'fetchAdminOAuthClients').mockResolvedValue(mockClients);
    vi.spyOn(oauthApi, 'patchAdminOAuthClient').mockRejectedValue(new Aal2StepUpCancelledError());
    vi.spyOn(oauthApi, 'deleteAdminOAuthClient').mockRejectedValue(new Aal2StepUpCancelledError());
    vi.spyOn(oauthApi, 'bulkDeleteAdminOAuthClients').mockRejectedValue(new Aal2StepUpCancelledError());
    vi.spyOn(oauthApi, 'registerAdminOAuthClient').mockRejectedValue(new Aal2StepUpCancelledError());

    act(() => {
      fireEvent.click(screen.getByTestId('refresh-clients-btn'));
    });
    await waitFor(() => {
      expect(screen.getByTestId('suspend-btn-client_active_app')).toBeDefined();
    });

    // Suspend cancel
    await act(async () => {
      fireEvent.click(screen.getByTestId('suspend-btn-client_active_app'));
      await Promise.resolve();
    });
    expect(screen.queryByTestId('error-alert')).toBeNull();
    expect(screen.queryByRole('alert')).toBeNull();

    // Revoke cancel
    act(() => {
      fireEvent.click(screen.getByTestId('revoke-btn-client_active_app'));
    });
    await act(async () => {
      fireEvent.click(screen.getByTestId('confirm-revoke-client_active_app'));
      await Promise.resolve();
    });
    expect(screen.queryByTestId('error-alert')).toBeNull();
    expect(screen.queryByRole('alert')).toBeNull();

    // Delete cancel
    act(() => {
      fireEvent.click(screen.getByTestId('delete-btn-client_active_app'));
    });
    await act(async () => {
      fireEvent.click(screen.getByTestId('confirm-delete-client_active_app'));
      await Promise.resolve();
    });
    expect(screen.queryByTestId('error-alert')).toBeNull();
    expect(screen.queryByRole('alert')).toBeNull();

    // Bulk delete cancel
    act(() => {
      fireEvent.click(screen.getByTestId('select-client-checkbox-client_active_app'));
      fireEvent.click(screen.getByTestId('delete-selected-btn'));
    });
    await act(async () => {
      fireEvent.click(screen.getByTestId('confirm-bulk-delete-btn'));
      await Promise.resolve();
    });
    expect(screen.queryByTestId('error-alert')).toBeNull();
    expect(screen.queryByRole('alert')).toBeNull();

    // Purge cancel
    act(() => {
      fireEvent.click(screen.getByTestId('purge-clients-btn'));
    });
    await act(async () => {
      fireEvent.click(screen.getByTestId('confirm-purge-btn'));
      await Promise.resolve();
    });
    expect(screen.queryByTestId('error-alert')).toBeNull();
    expect(screen.queryByRole('alert')).toBeNull();

    // Register cancel
    act(() => {
      fireEvent.click(screen.getByTestId('register-client-btn'));
    });
    fireEvent.change(screen.getByTestId('input-redirect-uris'), {
      target: { value: 'http://127.0.0.1:9090/cb' },
    });
    await act(async () => {
      fireEvent.click(screen.getByTestId('submit-register-btn'));
      await Promise.resolve();
    });
    expect(screen.queryByTestId('register-error-alert')).toBeNull();

    // Edit URIs cancel
    act(() => {
      fireEvent.click(screen.getByTestId('cancel-register-btn'));
    });
    act(() => {
      fireEvent.click(screen.getByTestId('edit-uris-btn-client_active_app'));
    });
    vi.spyOn(oauthApi, 'patchAdminOAuthClient').mockRejectedValueOnce(new Aal2StepUpCancelledError());
    await act(async () => {
      fireEvent.click(screen.getByTestId('submit-edit-uris-btn'));
      await Promise.resolve();
    });
    expect(screen.queryByTestId('edit-uris-error')).toBeNull();
  });

  it('covers advanced registration options, disabled status, and fallback branches', async () => {
    const disabledClient: oauthApi.OAuthClientItem = {
      client_id: 'client_disabled_no_name',
      client_name: undefined,
      client_type: 'confidential',
      token_endpoint_auth_method: 'client_secret_basic',
      redirect_uris: ['http://127.0.0.1:9090/cb'],
      status: 'disabled',
      client_secret_prefix: 'sec_dis...',
      created_at: '2026-03-29T10:00:00Z',
    };

    vi.spyOn(oauthApi, 'fetchAdminOAuthClients').mockResolvedValue([disabledClient]);
    const patchSpy = vi.spyOn(oauthApi, 'patchAdminOAuthClient').mockResolvedValue(undefined);

    render(
      <MemoryRouter initialEntries={['/admin/oauth']}>
        <OAuthClientGovernanceStudio />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('status-badge-disabled')).toBeDefined();
    });

    // Test approve with Aal2StepUpCancelledError
    patchSpy.mockRejectedValueOnce(new Aal2StepUpCancelledError());
    await act(async () => {
      fireEvent.click(screen.getByTestId('approve-btn-client_disabled_no_name'));
      await Promise.resolve();
    });
    expect(screen.queryByTestId('error-alert')).toBeNull();
    expect(screen.queryByRole('alert')).toBeNull();

    // Test Edit URIs with missing client_name (uses client_id in title)
    fireEvent.click(screen.getByTestId('edit-uris-btn-client_disabled_no_name'));
    expect(screen.getByTestId('edit-uris-modal-title').textContent).toContain('Edit Redirect URIs: client_disabled_no_name');
    fireEvent.click(screen.getByTestId('close-edit-uris-btn'));

    // Open register modal and exercise advanced controls
    fireEvent.click(screen.getByTestId('register-client-btn'));

    // Switch to confidential then back to public
    const clientTypeSelect = screen.getByTestId('select-client-type');
    fireEvent.change(clientTypeSelect, { target: { value: 'confidential' } });
    fireEvent.change(clientTypeSelect, { target: { value: 'public' } });

    // Open Advanced Section
    fireEvent.click(screen.getByTestId('advanced-oauth-parameters-toggle'));

    // Toggle PKCE
    const pkceToggle = screen.getByTestId('toggle-pkce-s256');
    fireEvent.click(pkceToggle);

    // TTL input with value then empty fallback
    const ttlInput = screen.getByTestId('input-access-token-ttl');
    fireEvent.change(ttlInput, { target: { value: '7200' } });
    fireEvent.change(ttlInput, { target: { value: '' } });

    // Grant types input
    const grantTypesInput = screen.getByTestId('input-grant-types');
    fireEvent.change(grantTypesInput, { target: { value: 'authorization_code,refresh_token' } });

    fireEvent.click(screen.getByTestId('cancel-register-btn'));
  });

  it('submits customized advanced parameters (PKCE, TTL, grant types) to registerAdminOAuthClient (KAN-417)', async () => {
    vi.spyOn(oauthApi, 'fetchAdminOAuthClients').mockResolvedValue(mockClients);
    const registerSpy = vi.spyOn(oauthApi, 'registerAdminOAuthClient').mockResolvedValue({
      client_id: 'client_custom_adv',
      client_name: 'Custom Advanced Client',
      client_type: 'confidential',
      token_endpoint_auth_method: 'client_secret_post',
      redirect_uris: ['https://custom.example.com/callback'],
      status: 'active',
      created_at: new Date().toISOString(),
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

    fireEvent.change(screen.getByTestId('input-client-name'), {
      target: { value: 'Custom Advanced Client' },
    });
    fireEvent.change(screen.getByTestId('input-redirect-uris'), {
      target: { value: 'https://custom.example.com/callback' },
    });
    fireEvent.change(screen.getByTestId('select-client-type'), {
      target: { value: 'confidential' },
    });
    fireEvent.change(screen.getByTestId('select-auth-method'), {
      target: { value: 'client_secret_post' },
    });

    // Expand Advanced Section
    fireEvent.click(screen.getByTestId('advanced-oauth-parameters-toggle'));

    // Toggle PKCE to false
    fireEvent.click(screen.getByTestId('toggle-pkce-s256'));

    // Change TTL to 7200
    fireEvent.change(screen.getByTestId('input-access-token-ttl'), {
      target: { value: '7200' },
    });

    // Change Grant Types
    fireEvent.change(screen.getByTestId('input-grant-types'), {
      target: { value: 'authorization_code' },
    });

    fireEvent.click(screen.getByTestId('submit-register-btn'));

    await waitFor(() => {
      expect(registerSpy).toHaveBeenCalledWith(
        expect.objectContaining({
          client_name: 'Custom Advanced Client',
          redirect_uris: ['https://custom.example.com/callback'],
          client_type: 'confidential',
          token_endpoint_auth_method: 'client_secret_post',
          pkce_enforce: false,
          access_token_ttl: 7200,
          grant_types: ['authorization_code'],
        }),
      );
    });
  });

  describe('KAN-523: Purge and Action Button Contrast and Semantic Tokens', () => {
    it('renders Purge Unused / Revoked Clients button cleanly in light theme', async () => {
      document.documentElement.removeAttribute('data-theme');
      vi.spyOn(oauthApi, 'fetchAdminOAuthClients').mockResolvedValue(mockClients);

      render(
        <MemoryRouter initialEntries={['/admin/oauth']}>
          <OAuthClientGovernanceStudio />
        </MemoryRouter>,
      );

      await waitFor(() => {
        expect(screen.getByTestId('purge-clients-btn')).toBeDefined();
      });

      const purgeBtn = screen.getByTestId('purge-clients-btn');
      expect(purgeBtn.textContent).toContain('Purge Unused / Revoked Clients');
      expect(purgeBtn.className).toContain('kb-oauth-gov-purge-btn');

      // Assert zero inline hardcoded color overrides
      expect(purgeBtn.style.backgroundColor).toBe('');
      expect(purgeBtn.style.borderColor).toBe('');
      expect(purgeBtn.style.color).toBe('');

      // Click enters confirm state
      fireEvent.click(purgeBtn);
      expect(screen.getByTestId('confirm-purge-btn')).toBeDefined();
    });

    it('renders Purge Unused / Revoked Clients button cleanly in dark theme', async () => {
      document.documentElement.setAttribute('data-theme', 'dark');
      vi.spyOn(oauthApi, 'fetchAdminOAuthClients').mockResolvedValue(mockClients);

      try {
        render(
          <MemoryRouter initialEntries={['/admin/oauth']}>
            <OAuthClientGovernanceStudio />
          </MemoryRouter>,
        );

        await waitFor(() => {
          expect(screen.getByTestId('purge-clients-btn')).toBeDefined();
        });

        const purgeBtn = screen.getByTestId('purge-clients-btn');
        expect(purgeBtn.textContent).toContain('Purge Unused / Revoked Clients');
        expect(purgeBtn.className).toContain('kb-oauth-gov-purge-btn');
        expect(purgeBtn.style.backgroundColor).toBe('');
        expect(purgeBtn.style.borderColor).toBe('');
        expect(purgeBtn.style.color).toBe('');
      } finally {
        document.documentElement.removeAttribute('data-theme');
      }
    });

    it('asserts OAuthClientGovernanceStudio.css removes #d29922 and uses WCAG AA semantic tokens for purge button', () => {
      const cssPath = path.resolve(import.meta.dirname, '../OAuthClientGovernanceStudio.css');
      const cssContent = fs.readFileSync(cssPath, 'utf8');

      const purgeRuleMatch = /\.kb-oauth-gov-purge-btn\s*\{[^}]+\}/.exec(cssContent);
      expect(purgeRuleMatch).not.toBeNull();
      const purgeRule = purgeRuleMatch?.[0] ?? '';

      // Assert #d29922 is completely removed from the purge button class
      expect(purgeRule).not.toContain('#d29922');

      // Assert WCAG AA >= 4.5:1 semantic tokens
      expect(purgeRule).toContain('background-color: var(--warn-bg);');
      expect(purgeRule).toContain('border: 1px solid var(--border-warning);');
      expect(purgeRule).toContain('color: var(--warn-fg);');

      // Assert hover state uses semantic warning tokens
      const hoverMatch = /\.kb-oauth-gov-purge-btn:hover[^{]*\{[^}]+\}/.exec(cssContent);
      expect(hoverMatch).not.toBeNull();
      const hoverRule = hoverMatch?.[0] ?? '';
      expect(hoverRule).toContain('background-color: var(--bg-warning-subtle);');
      expect(hoverRule).toContain('border-color: var(--warn-fg);');
      expect(hoverRule).toContain('color: var(--warn-fg);');
    });

    it('asserts semantic tokens for register, filter pill, and bulk delete buttons', () => {
      const cssPath = path.resolve(import.meta.dirname, '../OAuthClientGovernanceStudio.css');
      const cssContent = fs.readFileSync(cssPath, 'utf8');

      // Register button
      const registerMatch = /\.kb-oauth-gov-register-btn\s*\{[^}]+\}/.exec(cssContent);
      expect(registerMatch).not.toBeNull();
      const registerRule = registerMatch?.[0] ?? '';
      expect(registerRule).toContain('background-color: var(--accent-primary);');
      expect(registerRule).toContain('color: var(--accent-primary-fg);');
      expect(registerRule).toContain('border: 1px solid var(--accent-primary);');

      // Filter pill active
      const filterPillMatch = /\.kb-oauth-filter-pill-active\s*\{[^}]+\}/.exec(cssContent);
      expect(filterPillMatch).not.toBeNull();
      const filterPillRule = filterPillMatch?.[0] ?? '';
      expect(filterPillRule).toContain('background-color: var(--accent-primary);');
      expect(filterPillRule).toContain('color: var(--accent-primary-fg);');
      expect(filterPillRule).toContain('border-color: var(--accent-primary);');

      // Bulk delete button
      const bulkDeleteMatch = /\.kb-oauth-gov-bulk-delete-btn\s*\{[^}]+\}/.exec(cssContent);
      expect(bulkDeleteMatch).not.toBeNull();
      const bulkDeleteRule = bulkDeleteMatch?.[0] ?? '';
      expect(bulkDeleteRule).toContain('background-color: var(--danger-bg);');
      expect(bulkDeleteRule).toContain('border: 1px solid var(--danger-fg);');
      expect(bulkDeleteRule).toContain('color: var(--danger-fg);');
    });
  });

  describe('KAN-522: OAuth Client Registration Form FieldHelpHint and Default Indicators', () => {
    it('renders triggers, ARIA attributes, explicit default indicators, and helper texts', async () => {
      vi.spyOn(oauthApi, 'fetchAdminOAuthClients').mockResolvedValue(mockClients);

      render(
        <MemoryRouter initialEntries={['/admin/oauth']}>
          <OAuthClientGovernanceStudio />
        </MemoryRouter>,
      );

      await waitFor(() => {
        expect(screen.getByTestId('register-client-btn')).toBeDefined();
      });

      // Open Register Client modal
      fireEvent.click(screen.getByTestId('register-client-btn'));

      // 1. Client Type FieldHelpHint & Default Indicator
      const clientTypeHelp = screen.getByTestId('reg-client-type-help');
      expect(clientTypeHelp).toBeDefined();
      expect(clientTypeHelp.getAttribute('aria-label')).toBe('Help for Client Type');
      expect(clientTypeHelp.getAttribute('aria-haspopup')).toBe('dialog');
      expect(clientTypeHelp.getAttribute('aria-expanded')).toBe('false');

      const clientTypeIndicator = screen.getByTestId('reg-client-type-default-indicator');
      expect(clientTypeIndicator).toBeDefined();
      expect(clientTypeIndicator.textContent).toBe('(Default: Public (PKCE only))');

      const clientTypeSelect = screen.getByTestId<HTMLSelectElement>('select-client-type');
      expect(clientTypeSelect.value).toBe('public');
      expect(clientTypeSelect.getAttribute('aria-describedby')).toBe('reg-client-type-hint');

      const clientTypeHint = document.getElementById('reg-client-type-hint');
      expect(clientTypeHint?.textContent).toContain('Default: Public (PKCE only)');

      // 2. Token Endpoint Auth Method FieldHelpHint & Default Indicator
      const authMethodHelp = screen.getByTestId('reg-auth-method-help');
      expect(authMethodHelp).toBeDefined();
      expect(authMethodHelp.getAttribute('aria-label')).toBe(
        'Help for Token Endpoint Authentication Method',
      );
      expect(authMethodHelp.getAttribute('aria-haspopup')).toBe('dialog');
      expect(authMethodHelp.getAttribute('aria-expanded')).toBe('false');

      const authMethodIndicator = screen.getByTestId('reg-auth-method-default-indicator');
      expect(authMethodIndicator).toBeDefined();
      expect(authMethodIndicator.textContent).toBe('(Default: none)');

      const authMethodSelect = screen.getByTestId<HTMLSelectElement>('select-auth-method');
      expect(authMethodSelect.value).toBe('none');
      expect(authMethodSelect.getAttribute('aria-describedby')).toBe('reg-auth-method-hint');

      const authMethodHint = document.getElementById('reg-auth-method-hint');
      expect(authMethodHint?.textContent).toContain('Default: none');
    });

    it('opens Client Type popover on focus, verifies ARIA dialog and content, closes on Escape', async () => {
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

      const clientTypeHelp = screen.getByTestId('reg-client-type-help');

      // Focus opens popover
      act(() => {
        clientTypeHelp.focus();
      });

      expect(clientTypeHelp.getAttribute('aria-expanded')).toBe('true');

      const popover = screen.getByTestId('reg-client-type-help-popover');
      expect(popover).toBeDefined();
      expect(popover.getAttribute('role')).toBe('dialog');
      expect(popover.getAttribute('aria-label')).toBe('Client Type');

      // Verify explanation of RFC 9700 Public vs Confidential
      expect(popover.textContent).toContain('RFC 9700');
      expect(popover.textContent).toContain('Public');
      expect(popover.textContent).toContain('Confidential');
      expect(popover.textContent).toContain('PKCE');

      // Verify default value in popover
      const defaultVal = screen.getByTestId('reg-client-type-help-default');
      expect(defaultVal.textContent).toContain('Default:');
      expect(defaultVal.textContent).toContain('Public (PKCE only)');

      // Verify documentation link
      const docLink = screen.getByTestId('reg-client-type-help-doc-link');
      expect(docLink.getAttribute('href')).toBe(
        '/docs/three-surface-mcp-server-architecture#oauth-21--pkce',
      );

      // Escape closes popover
      act(() => {
        fireEvent.keyDown(clientTypeHelp, { key: 'Escape' });
      });

      expect(clientTypeHelp.getAttribute('aria-expanded')).toBe('false');
      expect(screen.queryByTestId('reg-client-type-help-popover')).toBeNull();
    });

    it('opens Auth Method popover on focus, verifies ARIA dialog and content, closes on Escape', async () => {
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

      const authMethodHelp = screen.getByTestId('reg-auth-method-help');

      // Focus opens popover
      act(() => {
        authMethodHelp.focus();
      });

      expect(authMethodHelp.getAttribute('aria-expanded')).toBe('true');

      const popover = screen.getByTestId('reg-auth-method-help-popover');
      expect(popover).toBeDefined();
      expect(popover.getAttribute('role')).toBe('dialog');
      expect(popover.getAttribute('aria-label')).toBe('Token Endpoint Authentication Method');

      // Verify explanation of RFC 9700 and OAuth 2.1
      expect(popover.textContent).toContain('RFC 9700');
      expect(popover.textContent).toContain('/oauth/token');
      expect(popover.textContent).toContain('PKCE S256');

      // Verify default value in popover
      const defaultVal = screen.getByTestId('reg-auth-method-help-default');
      expect(defaultVal.textContent).toContain('Default:');
      expect(defaultVal.textContent).toContain('none');

      // Verify documentation link
      const docLink = screen.getByTestId('reg-auth-method-help-doc-link');
      expect(docLink.getAttribute('href')).toBe(
        '/docs/three-surface-mcp-server-architecture#oauth-21--pkce',
      );

      // Escape closes popover
      act(() => {
        fireEvent.keyDown(authMethodHelp, { key: 'Escape' });
      });

      expect(authMethodHelp.getAttribute('aria-expanded')).toBe('false');
      expect(screen.queryByTestId('reg-auth-method-help-popover')).toBeNull();
    });

    it('renders cleanly in Light theme (data-theme="light") with zero inline style violations', async () => {
      document.documentElement.setAttribute('data-theme', 'light');
      vi.spyOn(oauthApi, 'fetchAdminOAuthClients').mockResolvedValue(mockClients);

      try {
        render(
          <MemoryRouter initialEntries={['/admin/oauth']}>
            <OAuthClientGovernanceStudio />
          </MemoryRouter>,
        );

        await waitFor(() => {
          expect(screen.getByTestId('register-client-btn')).toBeDefined();
        });

        fireEvent.click(screen.getByTestId('register-client-btn'));

        const clientTypeHelp = screen.getByTestId('reg-client-type-help');
        const authMethodHelp = screen.getByTestId('reg-auth-method-help');
        const clientTypeIndicator = screen.getByTestId('reg-client-type-default-indicator');
        const authMethodIndicator = screen.getByTestId('reg-auth-method-default-indicator');

        // Zero inline style props
        expect(clientTypeHelp.style.length).toBe(0);
        expect(authMethodHelp.style.length).toBe(0);
        expect(clientTypeIndicator.style.length).toBe(0);
        expect(authMethodIndicator.style.length).toBe(0);

        // Open popovers in Light theme without crash
        act(() => {
          clientTypeHelp.focus();
        });
        const clientPopover = screen.getByTestId('reg-client-type-help-popover');
        expect(clientPopover).toBeDefined();
        // Zero color or background inline style overrides (positioning managed by positionHint)
        expect(clientPopover.style.color).toBe('');
        expect(clientPopover.style.backgroundColor).toBe('');

        act(() => {
          fireEvent.keyDown(clientTypeHelp, { key: 'Escape' });
        });

        act(() => {
          authMethodHelp.focus();
        });
        const authPopover = screen.getByTestId('reg-auth-method-help-popover');
        expect(authPopover).toBeDefined();
        expect(authPopover.style.color).toBe('');
        expect(authPopover.style.backgroundColor).toBe('');
      } finally {
        document.documentElement.removeAttribute('data-theme');
      }
    });

    it('renders cleanly in Dark theme (data-theme="dark") with zero inline style violations', async () => {
      document.documentElement.setAttribute('data-theme', 'dark');
      vi.spyOn(oauthApi, 'fetchAdminOAuthClients').mockResolvedValue(mockClients);

      try {
        render(
          <MemoryRouter initialEntries={['/admin/oauth']}>
            <OAuthClientGovernanceStudio />
          </MemoryRouter>,
        );

        await waitFor(() => {
          expect(screen.getByTestId('register-client-btn')).toBeDefined();
        });

        fireEvent.click(screen.getByTestId('register-client-btn'));

        const clientTypeHelp = screen.getByTestId('reg-client-type-help');
        const authMethodHelp = screen.getByTestId('reg-auth-method-help');
        const clientTypeIndicator = screen.getByTestId('reg-client-type-default-indicator');
        const authMethodIndicator = screen.getByTestId('reg-auth-method-default-indicator');

        // Zero inline style props
        expect(clientTypeHelp.style.length).toBe(0);
        expect(authMethodHelp.style.length).toBe(0);
        expect(clientTypeIndicator.style.length).toBe(0);
        expect(authMethodIndicator.style.length).toBe(0);

        // Open popovers in Dark theme without crash
        act(() => {
          clientTypeHelp.focus();
        });
        const clientPopover = screen.getByTestId('reg-client-type-help-popover');
        expect(clientPopover).toBeDefined();
        // Zero color or background inline style overrides (positioning managed by positionHint)
        expect(clientPopover.style.color).toBe('');
        expect(clientPopover.style.backgroundColor).toBe('');

        act(() => {
          fireEvent.keyDown(clientTypeHelp, { key: 'Escape' });
        });

        act(() => {
          authMethodHelp.focus();
        });
        const authPopover = screen.getByTestId('reg-auth-method-help-popover');
        expect(authPopover).toBeDefined();
        expect(authPopover.style.color).toBe('');
        expect(authPopover.style.backgroundColor).toBe('');
      } finally {
        document.documentElement.removeAttribute('data-theme');
      }
    });

    it('asserts CSS rules for .kb-oauth-form-label, .kb-oauth-default-indicator, and 480px responsive media query', () => {
      const cssPath = path.resolve(import.meta.dirname, '../OAuthClientGovernanceStudio.css');
      const cssContent = fs.readFileSync(cssPath, 'utf8');

      // Label and flex alignment
      expect(cssContent).toContain('.kb-oauth-form-label');
      expect(cssContent).toContain('display: flex;');
      expect(cssContent).toContain('justify-content: space-between;');

      // Default indicator styling
      expect(cssContent).toContain('.kb-oauth-default-indicator');
      expect(cssContent).toContain('var(--kb-color-text-secondary, var(--fg-secondary, #8b949e))');

      // Mobile 480px responsiveness for zero clipping
      expect(cssContent).toContain('@media (max-width: 480px)');
      expect(cssContent).toContain('.kb-oauth-modal-card');
    });
  });
});
