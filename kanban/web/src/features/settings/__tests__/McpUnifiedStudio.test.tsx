// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import React from 'react';
import { MemoryRouter, Routes, Route, useLocation } from 'react-router';
import { McpAccessStudio } from '../McpAccessStudio';
import * as settingsApi from '../settingsApi';
import * as clientModule from '../../../api/client';
import { ApiProblem } from '../../../api/problem';
import { ProjectMcpRedirect, WorkspaceMcpRedirect, AdminMcpRedirect } from '../../../app/routes';

vi.mock('../../../app/useSystemStatus', () => ({
  useSystemStatus: vi.fn(() => ({
    data: { allow_unlimited_mcp_keys: true },
    isLoading: false,
    error: null,
  })),
}));

vi.mock('../../auth/SecondFactorStep', () => ({
  SecondFactorStep: ({
    onSuccess,
    onError,
    onSessionExpired,
    onCancel,
  }: {
    onSuccess?: () => void;
    onError?: () => void;
    onSessionExpired?: () => void;
    onCancel?: () => void;
  }) => (
    <div data-testid="second-factor-step-mock">
      <button type="button" data-testid="mfa-success-btn" onClick={() => onSuccess?.()}>
        MFA Success
      </button>
      <button type="button" data-testid="mfa-expired-btn" onClick={() => onSessionExpired?.()}>
        MFA Expired
      </button>
      <button type="button" data-testid="mfa-cancel-btn" onClick={() => onCancel?.()}>
        MFA Cancel
      </button>
      <button type="button" data-testid="mfa-error-btn" onClick={() => onError?.()}>
        MFA Error
      </button>
    </div>
  ),
}));

describe('Unified MCP Studio (KAN-31)', () => {
  const mockKeys: settingsApi.McpApiKeyItem[] = [
    {
      id: 'key-personal',
      label: 'Personal Developer Key',
      display_hint: '1a2b',
      surface: 'agent',
      scope_tier: 'personal_user',
      scopes: ['agent:read', 'agent:write'],
      allowed_projects: null,
      created_at: new Date().toISOString(),
      expires_at: null,
      last_used_at: null,
      revoked_at: null,
    },
    {
      id: 'key-project-kanba',
      label: 'KANBA Automation Bot',
      display_hint: '3c4d',
      surface: 'agent',
      scope_tier: 'project',
      scopes: ['agent:read', 'agent:write'],
      allowed_projects: ['KANBA'],
      created_at: new Date().toISOString(),
      expires_at: null,
      last_used_at: null,
      revoked_at: null,
    },
    {
      id: 'key-project-qaadm',
      label: 'QAADM Automation Bot',
      display_hint: '5e6f',
      surface: 'agent',
      scope_tier: 'project',
      scopes: ['agent:read', 'agent:write'],
      allowed_projects: ['QAADM'],
      created_at: new Date().toISOString(),
      expires_at: null,
      last_used_at: null,
      revoked_at: null,
    },
    {
      id: 'key-workspace',
      label: 'Workspace Shared Bot',
      display_hint: '7g8h',
      surface: 'agent',
      scope_tier: 'workspace',
      scopes: ['agent:read'],
      allowed_projects: null,
      created_at: new Date().toISOString(),
      expires_at: null,
      last_used_at: null,
      revoked_at: null,
    },
    {
      id: 'key-server',
      label: 'Server Administrative Bot',
      display_hint: '9i0j',
      surface: 'admin',
      scope_tier: 'global',
      scopes: ['admin:read'],
      allowed_projects: null,
      created_at: new Date().toISOString(),
      expires_at: null,
      last_used_at: null,
      revoked_at: null,
    },
  ];

  const adminUser = {
    is_server_admin: true,
    is_workspace_admin: true,
    is_project_admin: true,
    workspace_role: 'SERVER_ADMIN',
  };

  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(clientModule, 'apiFetch').mockResolvedValue(adminUser);
    vi.spyOn(settingsApi, 'fetchPersonalMcpKeys').mockResolvedValue(mockKeys);
    vi.spyOn(settingsApi, 'fetchUnifiedMcpKeys').mockResolvedValue(mockKeys);
    vi.spyOn(settingsApi, 'fetchConnectedApps').mockResolvedValue([]);
  });

  it('renders unified scope pills and explanatory architecture card', async () => {
    render(
      <MemoryRouter initialEntries={['/settings/mcp']}>
        <McpAccessStudio user={adminUser} />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('mcp-access-studio')).toBeDefined();
      expect(screen.getByTestId('mcp-scope-explainer')).toBeDefined();
      expect(screen.getByTestId('scope-pill-all')).toBeDefined();
      expect(screen.getByTestId('scope-pill-project')).toBeDefined();
      expect(screen.getByTestId('scope-pill-workspace')).toBeDefined();
      expect(screen.getByTestId('scope-pill-server')).toBeDefined();
    });

    // Check explainer text content contains key distinctions
    const explainer = screen.getByTestId('mcp-scope-explainer');
    expect(explainer.textContent).toContain('Personal Keys vs Service Bot Keys');
    expect(explainer.textContent).toContain('Scope Tiers');
  });

  it('filters keys by scope pills and shows project selector when Project scope is active', async () => {
    render(
      <MemoryRouter initialEntries={['/settings/mcp']}>
        <McpAccessStudio user={adminUser} />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('key-row-key-personal')).toBeDefined();
      expect(screen.getByTestId('key-row-key-project-kanba')).toBeDefined();
      expect(screen.getByTestId('key-row-key-workspace')).toBeDefined();
      expect(screen.getByTestId('key-row-key-server')).toBeDefined();
    });

    // Switch to Workspace pill
    fireEvent.click(screen.getByTestId('scope-pill-workspace'));
    await waitFor(() => {
      expect(screen.getByTestId('key-row-key-workspace')).toBeDefined();
      expect(screen.queryByTestId('key-row-key-personal')).toBeNull();
      expect(screen.queryByTestId('key-row-key-server')).toBeNull();
    });

    // Switch to Server pill
    fireEvent.click(screen.getByTestId('scope-pill-server'));
    await waitFor(() => {
      expect(screen.getByTestId('key-row-key-server')).toBeDefined();
      expect(screen.queryByTestId('key-row-key-workspace')).toBeNull();
    });

    // Switch to Project pill
    fireEvent.click(screen.getByTestId('scope-pill-project'));
    await waitFor(() => {
      expect(screen.getByTestId('scope-project-container')).toBeDefined();
      expect(screen.getByTestId('scope-project-select')).toBeDefined();
      expect(screen.getByTestId('key-row-key-project-kanba')).toBeDefined();
      expect(screen.queryByTestId('key-row-key-project-qaadm')).toBeNull();
    });

    // Change project selector to QAADM
    fireEvent.change(screen.getByTestId('scope-project-select'), {
      target: { value: 'QAADM' },
    });
    await waitFor(() => {
      expect(screen.getByTestId('key-row-key-project-qaadm')).toBeDefined();
      expect(screen.queryByTestId('key-row-key-project-kanba')).toBeNull();
    });
  });

  it('switches between My Keys and Governance views and updates title', async () => {
    render(
      <MemoryRouter initialEntries={['/settings/mcp']}>
        <McpAccessStudio user={adminUser} />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('admin-view-toggle')).toBeDefined();
      expect(screen.getByTestId('studio-title').textContent).toContain('Personal MCP Keys & Connected Apps');
    });

    // Switch to Governance
    fireEvent.click(screen.getByTestId('view-governance-btn'));
    await waitFor(() => {
      expect(screen.getByTestId('studio-title').textContent).toContain('Governance');
      expect(settingsApi.fetchUnifiedMcpKeys).toHaveBeenCalledWith(
        expect.objectContaining({ view: 'governance' }),
      );
    });

    // Switch back to My Keys
    fireEvent.click(screen.getByTestId('view-mine-btn'));
    await waitFor(() => {
      expect(screen.getByTestId('studio-title').textContent).toContain('Personal MCP Keys & Connected Apps');
    });
  });

  it('hides admin view toggle when caller is non-admin viewer or guest', async () => {
    const regularUser = {
      is_server_admin: false,
      is_workspace_admin: false,
      is_project_admin: false,
      workspace_role: 'WORKSPACE_MEMBER',
    };

    render(
      <MemoryRouter initialEntries={['/settings/mcp']}>
        <McpAccessStudio user={regularUser} />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('mcp-access-studio')).toBeDefined();
      expect(screen.queryByTestId('admin-view-toggle')).toBeNull();
    });
  });

  it('pre-fills scope tier in mint modal according to active scope filter', async () => {
    render(
      <MemoryRouter initialEntries={['/settings/mcp?scope=server']}>
        <McpAccessStudio user={adminUser} />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('mint-key-button')).toBeDefined();
    });

    fireEvent.click(screen.getByTestId('mint-key-button'));
    await waitFor(() => {
      expect(screen.getByTestId('mint-modal-card')).toBeDefined();
      const scopeSelect = screen.getByTestId<HTMLSelectElement>('mint-scope-select');
      expect(scopeSelect.value).toBe('global');
    });
  });

  it('handles inline AAL2 challenge step-up modal on 403 AAL2_REQUIRED in governance view', async () => {
    const aal2Error = new ApiProblem(403, {
      code: 'AAL2_REQUIRED',
      challenge_id: 'test-aal2-challenge',
      methods: ['totp', 'webauthn'],
    });

    vi.spyOn(settingsApi, 'fetchUnifiedMcpKeys')
      .mockRejectedValueOnce(aal2Error)
      .mockResolvedValueOnce(mockKeys);

    render(
      <MemoryRouter initialEntries={['/settings/mcp?view=governance']}>
        <McpAccessStudio user={adminUser} />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('aal2-modal-card')).toBeDefined();
      expect(screen.getByText('Admin Verification Required (AAL2)')).toBeDefined();
    });

    // Close button cancels modal
    const closeBtn = screen.getByRole('button', { name: 'x' });
    fireEvent.click(closeBtn);
    await waitFor(() => {
      expect(screen.queryByTestId('aal2-modal-card')).toBeNull();
    });
  });

  it('completes MFA challenge on loadData retry and handles session expired and cancel', async () => {
    const aal2Error = new ApiProblem(403, {
      code: 'AAL2_REQUIRED',
      challenge_id: 'test-challenge',
      methods: ['totp'],
    });

    const fetchSpy = vi
      .spyOn(settingsApi, 'fetchUnifiedMcpKeys')
      .mockRejectedValueOnce(aal2Error)
      .mockResolvedValueOnce(mockKeys);

    render(
      <MemoryRouter initialEntries={['/settings/mcp?view=governance']}>
        <McpAccessStudio user={adminUser} />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('second-factor-step-mock')).toBeDefined();
    });

    // Trigger MFA success
    fireEvent.click(screen.getByTestId('mfa-success-btn'));
    await waitFor(() => {
      expect(fetchSpy).toHaveBeenCalledTimes(2);
      expect(screen.queryByTestId('aal2-modal-card')).toBeNull();
    });
  });

  it('handles AAL2 step-up challenge on minting and retries on MFA success, error, and cancel', async () => {
    const aal2MintError = new ApiProblem(403, {
      code: 'AAL2_REQUIRED',
      challenge_id: 'mint-challenge',
      methods: ['webauthn'],
    });

    const mintSpy = vi
      .spyOn(settingsApi, 'mintPersonalMcpKey')
      .mockRejectedValueOnce(aal2MintError)
      .mockResolvedValueOnce({
        id: 'new-key-1',
        token: 'kb_mcp_sec_secret123',
        raw_key: 'kb_mcp_sec_secret123',
        label: 'Step-up Key',
        surface: 'agent',
        scope_tier: 'workspace',
        scopes: ['agent:read'],
        display_hint: '1234',
        key_prefix: 'kb_mcp_sec_',
        created_at: new Date().toISOString(),
        expires_at: null,
        last_used_at: null,
        revoked_at: null,
      } as unknown as settingsApi.McpApiKeyItem);

    render(
      <MemoryRouter initialEntries={['/settings/mcp']}>
        <McpAccessStudio user={adminUser} />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('mint-key-button')).toBeDefined();
    });

    fireEvent.click(screen.getByTestId('mint-key-button'));
    await waitFor(() => {
      expect(screen.getByTestId('mint-modal-card')).toBeDefined();
    });

    // Fill label and change scope
    const labelInput = screen.getByTestId<HTMLInputElement>('mint-label-input');
    fireEvent.change(labelInput, { target: { value: 'Step-up Key' } });

    const scopeSelect = screen.getByTestId<HTMLSelectElement>('mint-scope-select');
    fireEvent.change(scopeSelect, { target: { value: 'project' } });

    await waitFor(() => {
      expect(screen.getByTestId('mint-project-input')).toBeDefined();
    });
    const projInput = screen.getByTestId<HTMLInputElement>('mint-project-input');
    fireEvent.change(projInput, { target: { value: 'KANBA' } });

    // Submit
    const submitBtn = screen.getByRole('button', { name: 'Mint Key' });
    fireEvent.click(submitBtn);

    // Expect AAL2 modal
    await waitFor(() => {
      expect(screen.getByTestId('aal2-modal-card')).toBeDefined();
    });

    // Test error callback (handled inside SecondFactorStep)
    fireEvent.click(screen.getByTestId('mfa-error-btn'));

    // Trigger MFA success to finish minting
    fireEvent.click(screen.getByTestId('mfa-success-btn'));
    await waitFor(() => {
      expect(mintSpy).toHaveBeenCalledTimes(2);
      expect(screen.getByTestId('mcp-snippet-modal')).toBeDefined();
    });
  });

  it('handles MFA challenge cancel and session expired', async () => {
    const aal2MintError = new ApiProblem(403, {
      code: 'AAL2_REQUIRED',
      challenge_id: 'mint-cancel-challenge',
      methods: ['totp'],
    });
    vi.spyOn(settingsApi, 'mintPersonalMcpKey').mockRejectedValue(aal2MintError);

    render(
      <MemoryRouter initialEntries={['/settings/mcp']}>
        <McpAccessStudio user={adminUser} />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('mint-key-button')).toBeDefined();
    });
    fireEvent.click(screen.getByTestId('mint-key-button'));
    await waitFor(() => {
      expect(screen.getByTestId('mint-modal-card')).toBeDefined();
    });
    const labelInput = screen.getByTestId<HTMLInputElement>('mint-label-input');
    fireEvent.change(labelInput, { target: { value: 'Cancel Key' } });
    fireEvent.click(screen.getByRole('button', { name: 'Mint Key' }));

    await waitFor(() => {
      expect(screen.getByTestId('aal2-modal-card')).toBeDefined();
    });
    fireEvent.click(screen.getByTestId('mfa-expired-btn'));
    await waitFor(() => {
      expect(screen.queryByTestId('aal2-modal-card')).toBeNull();
    });

    fireEvent.click(screen.getByRole('button', { name: 'Mint Key' }));
    await waitFor(() => {
      expect(screen.getByTestId('aal2-modal-card')).toBeDefined();
    });
    fireEvent.click(screen.getByTestId('mfa-cancel-btn'));
    await waitFor(() => {
      expect(screen.queryByTestId('aal2-modal-card')).toBeNull();
    });
  });

  it('handles mint error reporting on generic failure', async () => {
    vi.spyOn(settingsApi, 'mintPersonalMcpKey').mockRejectedValueOnce(
      new Error('Quota limit reached'),
    );

    render(
      <MemoryRouter initialEntries={['/settings/mcp']}>
        <McpAccessStudio user={adminUser} />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('mint-key-button')).toBeDefined();
    });

    fireEvent.click(screen.getByTestId('mint-key-button'));
    await waitFor(() => {
      expect(screen.getByTestId('mint-modal-card')).toBeDefined();
    });

    const labelInput = screen.getByTestId<HTMLInputElement>('mint-label-input');
    fireEvent.change(labelInput, { target: { value: 'Quota Key' } });

    const submitBtn = screen.getByRole('button', { name: 'Mint Key' });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(screen.getByText('Quota limit reached')).toBeDefined();
    });
  });

  it('handles AAL2 step-up challenge on revoking keys and retries on MFA success', async () => {
    const aal2RevokeError = new ApiProblem(403, {
      code: 'AAL2_REQUIRED',
      challenge_id: 'revoke-challenge',
      methods: ['totp'],
    });

    const revokeSpy = vi
      .spyOn(settingsApi, 'revokePersonalMcpKey')
      .mockRejectedValueOnce(aal2RevokeError)
      .mockResolvedValueOnce(undefined);

    render(
      <MemoryRouter initialEntries={['/settings/mcp?view=governance']}>
        <McpAccessStudio user={adminUser} />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('key-row-key-project-kanba')).toBeDefined();
    });

    // Click revoke button for key-project-kanba
    const revokeBtn = screen.getByTestId('revoke-btn-key-project-kanba');
    fireEvent.click(revokeBtn);

    await waitFor(() => {
      expect(screen.getByTestId('confirm-revoke-btn')).toBeDefined();
    });

    // Confirm revocation inline
    fireEvent.click(screen.getByTestId('confirm-revoke-btn'));

    // Expect AAL2 modal
    await waitFor(() => {
      expect(screen.getByTestId('aal2-modal-card')).toBeDefined();
    });

    // Click MFA success
    fireEvent.click(screen.getByTestId('mfa-success-btn'));

    await waitFor(() => {
      expect(revokeSpy).toHaveBeenCalledTimes(2);
      expect(screen.queryByTestId('aal2-modal-card')).toBeNull();
    });
  });

  it('handles scope filter changes and clears scope on All pill', async () => {
    render(
      <MemoryRouter initialEntries={['/settings/mcp?scope=workspace']}>
        <McpAccessStudio user={adminUser} />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('scope-pill-workspace')).toBeDefined();
    });

    // Click All pill to delete scope
    fireEvent.click(screen.getByTestId('scope-pill-all'));
    await waitFor(() => {
      expect(screen.getByTestId('scope-pill-all').className).toContain(
        'kb-mcp-filter-pill-active',
      );
    });

    // Open mint modal from workspace scope to verify initialTier workspace
    fireEvent.click(screen.getByTestId('scope-pill-workspace'));
    fireEvent.click(screen.getByTestId('mint-key-button'));
    await waitFor(() => {
      const scopeSelect = screen.getByTestId<HTMLSelectElement>('mint-scope-select');
      expect(scopeSelect.value).toBe('workspace');
    });
  });

  it('handles global tier personal key revocation and connected app revocation', async () => {
    const revokePersonalSpy = vi
      .spyOn(settingsApi, 'revokePersonalMcpKey')
      .mockResolvedValue(undefined);

    const mockApps: settingsApi.OAuthConnectedApp[] = [
      {
        id: 'grant-123',
        client_id: 'client-ci-runner',
        client_name: 'External CI Runner',
        surface: 'agent',
        scopes: ['agent:read'],
        allowed_projects: null,
        created_at: new Date().toISOString(),
        revoked_at: null,
      },
    ];
    vi.spyOn(settingsApi, 'fetchConnectedApps').mockResolvedValue(mockApps);

    render(
      <MemoryRouter initialEntries={['/admin/mcp']}>
        <McpAccessStudio user={adminUser} tier="global" />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('key-row-key-server')).toBeDefined();
    });

    // Revoke key-server
    const revokeBtn = screen.getByTestId('revoke-btn-key-server');
    fireEvent.click(revokeBtn);
    await waitFor(() => {
      expect(screen.getByTestId('confirm-revoke-btn')).toBeDefined();
    });
    fireEvent.click(screen.getByTestId('confirm-revoke-btn'));
    await waitFor(() => {
      expect(revokePersonalSpy).toHaveBeenCalledWith('key-server', 'global');
    });
  });

  it('handles connected app revocation in personal view', async () => {
    const mockApps: settingsApi.OAuthConnectedApp[] = [
      {
        id: 'grant-123',
        client_id: 'client-ci-runner',
        client_name: 'External CI Runner',
        surface: 'agent',
        scopes: ['agent:read'],
        allowed_projects: null,
        created_at: new Date().toISOString(),
        revoked_at: null,
      },
    ];
    vi.spyOn(settingsApi, 'fetchConnectedApps').mockResolvedValue(mockApps);
    const revokeAppSpy = vi
      .spyOn(settingsApi, 'revokeConnectedApp')
      .mockResolvedValue(undefined);

    render(
      <MemoryRouter initialEntries={['/settings/mcp']}>
        <McpAccessStudio user={adminUser} />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('app-row-grant-123')).toBeDefined();
    });

    // Revoke connected app
    const disconnectBtn = screen.getByTestId('disconnect-btn-grant-123');
    fireEvent.click(disconnectBtn);
    await waitFor(() => {
      expect(screen.getByTestId('confirm-disconnect-btn')).toBeDefined();
    });
    fireEvent.click(screen.getByTestId('confirm-disconnect-btn'));
    await waitFor(() => {
      expect(revokeAppSpy).toHaveBeenCalledWith('grant-123');
    });
  });

  it('covers branch edges: custom project option, fallback project in mint, stale AAL2, and empty allowed_projects', async () => {
    const keysWithEdgeCases: settingsApi.McpApiKeyItem[] = [
      {
        id: 'key-edge-proj',
        label: 'Edge Project Key',
        display_hint: '9999',
        surface: 'agent',
        scope_tier: 'project',
        scopes: ['agent:read'],
        allowed_projects: null,
        created_at: new Date().toISOString(),
        expires_at: null,
        last_used_at: null,
        revoked_at: null,
      },
    ];

    const staleError = new ApiProblem(403, {
      code: 'AAL2_STALE',
    });

    vi.spyOn(settingsApi, 'fetchUnifiedMcpKeys')
      .mockRejectedValueOnce(staleError)
      .mockResolvedValueOnce(keysWithEdgeCases);

    const mintSpy = vi
      .spyOn(settingsApi, 'mintPersonalMcpKey')
      .mockRejectedValueOnce(staleError)
      .mockResolvedValueOnce({
        id: 'new-key-custom',
        token: 'kb_mcp_sec_custom',
        raw_key: 'kb_mcp_sec_custom',
        label: 'Custom Key',
        surface: 'agent',
        scope_tier: 'project',
        scopes: ['agent:read'],
        display_hint: '8888',
        key_prefix: 'kb_mcp_sec_',
        created_at: new Date().toISOString(),
        expires_at: null,
        last_used_at: null,
        revoked_at: null,
      } as unknown as settingsApi.McpApiKeyItem);

    const revokeSpy = vi
      .spyOn(settingsApi, 'revokePersonalMcpKey')
      .mockRejectedValueOnce(staleError)
      .mockResolvedValueOnce(undefined);

    render(
      <MemoryRouter initialEntries={['/settings/mcp?view=governance&scope=project&project=CUSTOM']}>
        <McpAccessStudio user={adminUser} allowUnlimitedKeys={false} />
      </MemoryRouter>,
    );

    // 1. Initial load hits AAL2_STALE without challengeId or methods
    await waitFor(() => {
      expect(screen.getByTestId('aal2-modal-card')).toBeDefined();
    });
    fireEvent.click(screen.getByTestId('mfa-success-btn'));

    // 2. Project select should include custom option 'CUSTOM' and key-edge-proj is visible
    await waitFor(() => {
      expect(screen.getByTestId('key-row-key-edge-proj')).toBeDefined();
      const projSelect = screen.getByTestId<HTMLSelectElement>('scope-project-select');
      expect(projSelect.value).toBe('CUSTOM');
    });

    // 3. Open mint modal in project scope, test project input onChange and minting
    fireEvent.click(screen.getByTestId('mint-key-button'));
    await waitFor(() => {
      expect(screen.getByTestId('mint-project-input')).toBeDefined();
    });
    const projInput = screen.getByTestId<HTMLInputElement>('mint-project-input');
    fireEvent.change(projInput, { target: { value: 'CUSTOM_PRJ' } });
    const labelInput = screen.getByTestId<HTMLInputElement>('mint-label-input');
    fireEvent.change(labelInput, { target: { value: 'Custom Key' } });

    // Submit minting -> hits AAL2_STALE
    fireEvent.click(screen.getByRole('button', { name: 'Mint Key' }));
    await waitFor(() => {
      expect(screen.getByTestId('aal2-modal-card')).toBeDefined();
    });
    fireEvent.click(screen.getByTestId('mfa-success-btn'));
    await waitFor(() => {
      expect(mintSpy).toHaveBeenCalledTimes(2);
    });

    // 4. Revoke key-edge-proj -> hits AAL2_STALE
    fireEvent.click(screen.getByTestId('revoke-btn-key-edge-proj'));
    await waitFor(() => {
      expect(screen.getByTestId('confirm-revoke-btn')).toBeDefined();
    });
    fireEvent.click(screen.getByTestId('confirm-revoke-btn'));
    await waitFor(() => {
      expect(screen.getByTestId('aal2-modal-card')).toBeDefined();
    });
    fireEvent.click(screen.getByTestId('mfa-success-btn'));
    await waitFor(() => {
      expect(revokeSpy).toHaveBeenCalledTimes(2);
    });
  });

  it('redirects old routes preserving scope and project search params', () => {
    function RouteInspector(): React.JSX.Element {
      const loc = useLocation();
      return <div data-testid="resolved-location">{loc.pathname}{loc.search}</div>;
    }

    // 1. Project redirect: /projects/:projectKey/settings/mcp
    const { unmount: u1 } = render(
      <MemoryRouter initialEntries={['/projects/PRJ1/settings/mcp?extra=1']}>
        <Routes>
          <Route path="/projects/:projectKey/settings/mcp" element={<ProjectMcpRedirect />} />
          <Route path="/settings/mcp" element={<RouteInspector />} />
        </Routes>
      </MemoryRouter>,
    );
    expect(screen.getByTestId('resolved-location').textContent).toBe(
      '/settings/mcp?extra=1&scope=project&project=PRJ1',
    );
    u1();

    // 2. Workspace redirect: /workspaces/settings/mcp
    const { unmount: u2 } = render(
      <MemoryRouter initialEntries={['/workspaces/settings/mcp?foo=bar']}>
        <Routes>
          <Route path="/workspaces/settings/mcp" element={<WorkspaceMcpRedirect />} />
          <Route path="/settings/mcp" element={<RouteInspector />} />
        </Routes>
      </MemoryRouter>,
    );
    expect(screen.getByTestId('resolved-location').textContent).toBe(
      '/settings/mcp?foo=bar&scope=workspace',
    );
    u2();

    // 3. Admin redirect: /admin/mcp
    render(
      <MemoryRouter initialEntries={['/admin/mcp']}>
        <Routes>
          <Route path="/admin/mcp" element={<AdminMcpRedirect />} />
          <Route path="/settings/mcp" element={<RouteInspector />} />
        </Routes>
      </MemoryRouter>,
    );
    expect(screen.getByTestId('resolved-location').textContent).toBe(
      '/settings/mcp?scope=server',
    );
  });
});
