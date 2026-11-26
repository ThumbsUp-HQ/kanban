// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import React from 'react';
import fs from 'node:fs';
import path from 'node:path';
import { MemoryRouter, Routes, Route } from 'react-router';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import {
  McpAccessStudio,
  validateCidrInput,
  getCapabilityPresetName,
  formatMintKeySummary,
} from '../McpAccessStudio';
import * as settingsApi from '../settingsApi';
import * as clientModule from '../../../api/client';

vi.mock('../../auth/SecondFactorStep', () => ({
  SecondFactorStep: ({
    onSuccess,
    onError,
    onSessionExpired,
    onCancel,
  }: {
    onSuccess: () => void;
    onError: (err: unknown) => void;
    onSessionExpired: () => void;
    onCancel?: () => void;
  }) => (
    <div data-testid="mock-second-factor-step">
      <button type="button" data-testid="mock-mfa-success-btn" onClick={onSuccess}>
        Trigger MFA Success
      </button>
      <button type="button" data-testid="mock-mfa-error-btn" onClick={() => { onError('mfa error'); }}>
        Trigger MFA Error
      </button>
      <button type="button" data-testid="mock-mfa-expired-btn" onClick={onSessionExpired}>
        Trigger MFA Expired
      </button>
      <button type="button" data-testid="mock-mfa-cancel-btn" onClick={onCancel}>
        Trigger MFA Cancel
      </button>
    </div>
  ),
}));

vi.mock('../../../app/useSystemStatus', () => ({
  useSystemStatus: vi.fn(() => ({
    data: { allow_unlimited_mcp_keys: true },
    isLoading: false,
    error: null,
  })),
}));

vi.mock('../McpUnifiedStudio', () => ({
  WorkloadFederationSection: () => <div data-testid="mock-workload-federation" />,
}));

describe('McpAccessStudio & McpConfigSnippetModal (KB-P4-16)', () => {
  const mockKeys: settingsApi.McpApiKeyItem[] = [
    {
      id: 'key-1',
      label: 'Personal CLI Key',
      display_hint: '4a2b',
      surface: 'agent',
      scope_tier: 'personal_user',
      scopes: ['agent:read', 'agent:write'],
      allowed_projects: null,
      created_at: new Date().toISOString(),
      expires_at: new Date(Date.now() + 86400000 * 60).toISOString(),
      last_used_at: null,
      revoked_at: null,
    },
    {
      id: 'key-2',
      label: 'Revoked Key',
      display_hint: '9z8y',
      surface: 'docs',
      scope_tier: 'personal_user',
      scopes: ['docs:read'],
      allowed_projects: null,
      created_at: new Date().toISOString(),
      expires_at: new Date().toISOString(),
      last_used_at: null,
      revoked_at: new Date().toISOString(),
    },
    {
      id: 'key-3',
      label: 'Workspace Bot Key',
      display_hint: '3w3w',
      surface: 'agent',
      scope_tier: 'workspace',
      scopes: ['agent:read'],
      allowed_projects: null,
      created_at: new Date().toISOString(),
      expires_at: new Date().toISOString(),
      last_used_at: null,
      revoked_at: null,
    },
    {
      id: 'key-4',
      label: 'Global Admin Bot Key',
      display_hint: '4g4g',
      surface: 'admin',
      scope_tier: 'global',
      scopes: ['admin:read'],
      allowed_projects: null,
      created_at: new Date().toISOString(),
      expires_at: new Date().toISOString(),
      last_used_at: null,
      revoked_at: null,
    },
    {
      id: 'key-5',
      label: 'Project Bot Key',
      display_hint: '5p5p',
      surface: 'agent',
      scope_tier: 'project',
      scopes: ['agent:read'],
      allowed_projects: ['KANBA'],
      created_at: new Date().toISOString(),
      expires_at: new Date().toISOString(),
      last_used_at: null,
      revoked_at: null,
    },
  ];

  const mockApps: settingsApi.OAuthConnectedApp[] = [
    {
      id: 'grant-1',
      client_id: 'client_claude',
      client_name: '<img src=x onerror=alert(1)> Claude Code',
      surface: 'agent',
      scopes: ['agent:read'],
      allowed_projects: ['KANBA'],
      created_at: new Date().toISOString(),
      revoked_at: null,
    },
    {
      id: 'grant-2',
      client_id: 'client_headless',
      client_name: undefined,
      surface: 'agent',
      scopes: ['agent:read'],
      allowed_projects: null,
      created_at: new Date().toISOString(),
      revoked_at: null,
    },
  ];

  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(settingsApi, 'fetchUnifiedMcpKeys').mockResolvedValue(mockKeys);
    vi.spyOn(settingsApi, 'fetchPersonalMcpKeys').mockResolvedValue(mockKeys);
    vi.spyOn(clientModule, 'apiFetch').mockImplementation((_method: string, path: string) => {
      if (path === '/api/v1/projects') {
        return Promise.resolve({
          items: [
            { id: 'proj-kanba', identifier: 'KANBA', name: 'Kanban Core' },
            { id: 'proj-ops', identifier: 'OPS', name: 'Operations' },
            { id: 'proj-same', identifier: 'SAME', name: 'SAME' },
            { id: 'proj-noname', identifier: 'NONAME', name: '' },
          ],
        });
      }
      return Promise.resolve({
        is_server_admin: true,
        is_workspace_admin: true,
      });
    });
  });

  it('renders scope tiers correctly across all 4 mount routes', async () => {
    vi.spyOn(settingsApi, 'fetchUnifiedMcpKeys').mockResolvedValue(mockKeys);
    vi.spyOn(settingsApi, 'fetchConnectedApps').mockResolvedValue(mockApps);

    // Personal tier
    const { unmount: unmount1 } = render(
      <MemoryRouter initialEntries={['/settings/mcp']}>
        <McpAccessStudio tier="personal" />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('studio-title').textContent).toContain('Personal MCP Keys & Connected Apps');
      expect(screen.getAllByTestId('tier-badge-personal').length).toBeGreaterThan(0);
    });
    unmount1();

    // Project tier
    const { unmount: unmount2 } = render(
      <MemoryRouter initialEntries={['/projects/KANBA/settings/mcp']}>
        <Routes>
          <Route
            path="/projects/:projectKey/settings/mcp"
            element={<McpAccessStudio tier="project" />}
          />
        </Routes>
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('studio-title').textContent).toContain('Project (KANBA) MCP Bot Keys');
    });
    unmount2();

    // Workspace tier
    const { unmount: unmount3 } = render(
      <MemoryRouter initialEntries={['/workspaces/settings/mcp']}>
        <McpAccessStudio tier="workspace" />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('studio-title').textContent).toContain('Workspace MCP Bot Keys');
    });
    unmount3();

    // Global tier
    render(
      <MemoryRouter initialEntries={['/admin/mcp']}>
        <McpAccessStudio tier="global" />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('studio-title').textContent).toContain('Global Cross-Workspace Bot Keys');
      expect(screen.getByTestId('tab-admin-mcp')).toBeDefined();
      expect(screen.getByTestId('tab-admin-oauth')).toBeDefined();
      expect(screen.getByTestId('tab-admin-imports')).toBeDefined();
    });
  });

  it('renders Project: QAADM badge when key has allowed_projects set to QAADM across settings surfaces (KANBA-218)', async () => {
    const qaadmKey: settingsApi.McpApiKeyItem = {
      id: 'key-qaadm',
      label: 'QA Admin Key',
      display_hint: '99aa',
      surface: 'agent',
      scope_tier: 'project',
      scopes: ['agent:read', 'agent:write'],
      allowed_projects: ['QAADM'],
      created_at: new Date().toISOString(),
      expires_at: null,
      last_used_at: null,
      revoked_at: null,
    };

    vi.spyOn(settingsApi, 'fetchUnifiedMcpKeys').mockResolvedValue([qaadmKey]);
    vi.spyOn(settingsApi, 'fetchConnectedApps').mockResolvedValue([]);

    render(
      <MemoryRouter initialEntries={['/settings/mcp']}>
        <McpAccessStudio tier="personal" />
      </MemoryRouter>,
    );

    await waitFor(() => {
      const badge = screen.getByTestId('tier-badge-project');
      expect(badge.textContent).toContain('Project: QAADM');
      expect(badge.textContent).not.toContain('Project: KANBA');
    });
  });

  it('renders NotFoundView when standard user navigates to workspace or admin mcp', () => {
    const standardUser = { is_server_admin: false, is_workspace_admin: false };
    const { unmount: u1 } = render(
      <MemoryRouter initialEntries={['/admin/mcp']}>
        <McpAccessStudio tier="global" user={standardUser} />
      </MemoryRouter>,
    );
    expect(screen.getByTestId('not-found-view')).toBeDefined();
    expect(screen.getByText('Not found or no access')).toBeDefined();
    u1();

    const { unmount: u2 } = render(
      <MemoryRouter initialEntries={['/workspaces/settings/mcp']}>
        <McpAccessStudio tier="workspace" user={standardUser} />
      </MemoryRouter>,
    );
    expect(screen.getByTestId('not-found-view')).toBeDefined();
    expect(screen.getByText('Not found or no access')).toBeDefined();
    u2();
  });

  it('mints key, opens snippet modal with plaintext, copies, and wipes secret on close (Test Case 3)', async () => {
    vi.spyOn(settingsApi, 'fetchUnifiedMcpKeys').mockResolvedValue([]);
    vi.spyOn(settingsApi, 'fetchConnectedApps').mockResolvedValue([]);

    const newlyMintedKey: settingsApi.McpApiKeyItem = {
      id: 'key-new',
      label: 'CI Bot Token',
      display_hint: '7f3e',
      surface: 'agent',
      scope_tier: 'project',
      scopes: ['agent:read', 'agent:write'],
      allowed_projects: ['KANBA'],
      created_at: new Date().toISOString(),
      expires_at: new Date(Date.now() + 86400000 * 60).toISOString(),
      last_used_at: null,
      revoked_at: null,
      raw_key: 'kb_agt_mock_key',
    };

    vi.spyOn(settingsApi, 'mintUnifiedMcpKey').mockResolvedValue(newlyMintedKey);

    const writeTextMock = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, {
      clipboard: {
        writeText: writeTextMock,
      },
    });

    render(
      <MemoryRouter initialEntries={['/projects/KANBA/settings/mcp']}>
        <Routes>
          <Route
            path="/projects/:projectKey/settings/mcp"
            element={<McpAccessStudio tier="project" />}
          />
        </Routes>
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('mint-key-button')).not.toBeNull();
    });

    fireEvent.click(screen.getByTestId('mint-key-button'));

    const labelInput = screen.getByTestId('mint-label-input');
    fireEvent.change(labelInput, { target: { value: 'CI Bot Token' } });

    const surfaceSelect = screen.getByTestId('mint-surface-select');
    fireEvent.change(surfaceSelect, { target: { value: 'agent' } });

    const expirySelect = screen.getByTestId('mint-expiry-select');
    fireEvent.change(expirySelect, { target: { value: 60 } });

    const submitBtn = screen.getByTestId('mint-submit-btn');
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(settingsApi.mintUnifiedMcpKey).toHaveBeenCalledWith(
        expect.objectContaining({
          label: 'CI Bot Token',
          surface: 'agent',
          scopes: ['agent:read', 'agent:write'],
          scope_tier: 'project',
          allowed_projects: ['KANBA'],
          expires_in_days: 60,
        }),
      );
      // Plaintext key modal rendered
      expect(screen.getByTestId('raw-key-banner')).not.toBeNull();
    });

    // Verify plaintext key display
    expect(screen.getByTestId('raw-key-display').textContent).toContain(
      'kb_agt_mock_key',
    );

    // Copy key
    fireEvent.click(screen.getByTestId('copy-key-button'));
    expect(writeTextMock).toHaveBeenCalledWith('kb_agt_mock_key');

    // Snippet verification (.gemini/settings.json)
    const snippetCode = screen.getByTestId('snippet-code-box');
    expect(snippetCode.textContent).toContain('/mcp/agent/w/kanban/p/KANBA');
    expect(snippetCode.textContent).toContain('kb_agt_mock_key');

    // Switch to Antigravity tab
    fireEvent.click(screen.getByTestId('tab-antigravity'));
    expect(snippetCode.textContent).toContain('"serverUrl":');
    expect(snippetCode.textContent).toContain('agy mcp add --header');

    // Switch to Claude tab
    fireEvent.click(screen.getByTestId('tab-claude'));
    expect(snippetCode.textContent).toContain('mcpServers');

    // Switch to OAuth tab (RFC 8414 Discovery)
    fireEvent.click(screen.getByTestId('tab-oauth'));
    expect(snippetCode.textContent).toContain('/.well-known/oauth-authorization-server');

    // Switch URL scope to Workspace
    const urlSelect = screen.getByTestId('url-scope-select');
    fireEvent.change(urlSelect, { target: { value: 'workspace' } });
    expect(snippetCode.textContent).toContain('/mcp/agent/w/kanban');

    // Switch URL scope to Global
    fireEvent.change(urlSelect, { target: { value: 'global' } });
    expect(snippetCode.textContent).toContain('/mcp/agent');

    // Switch back to Gemini tab
    fireEvent.click(screen.getByTestId('tab-gemini'));
    expect(snippetCode.textContent).toContain('"kanban":');

    // Copy snippet
    fireEvent.click(screen.getByTestId('copy-snippet-button'));
    expect(writeTextMock).toHaveBeenCalledTimes(2);

    // Close modal -> Volatile state sanitization: plaintext key MUST disappear from DOM!
    fireEvent.click(screen.getByTestId('done-button'));

    await waitFor(() => {
      expect(screen.queryByTestId('raw-key-banner')).toBeNull();
    });

    // In the table, only display_hint is present
    expect(screen.getByTestId('key-hint-key-new').textContent).toContain('kb_agt_...7f3e');
    expect(document.body.textContent).not.toContain('kb_agt_mock_key');
  });

  it('performs 2-step inline revocation and deauth (Test Case 4)', async () => {
    vi.spyOn(settingsApi, 'fetchUnifiedMcpKeys').mockResolvedValue(mockKeys);
    vi.spyOn(settingsApi, 'fetchConnectedApps').mockResolvedValue(mockApps);
    vi.spyOn(settingsApi, 'revokeUnifiedMcpKey').mockResolvedValue(undefined);
    vi.spyOn(settingsApi, 'revokeConnectedApp').mockResolvedValue(undefined);

    render(
      <MemoryRouter initialEntries={['/settings/mcp']}>
        <McpAccessStudio tier="personal" />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('revoke-btn-key-1')).not.toBeNull();
    });

    // 1. Revoke MCP Key - Step 1: Open inline confirmation
    fireEvent.click(screen.getByTestId('revoke-btn-key-1'));
    expect(screen.getByTestId('confirm-revoke-bar')).not.toBeNull();

    // Cancel first
    fireEvent.click(screen.getByTestId('cancel-revoke-btn'));
    expect(screen.queryByTestId('confirm-revoke-bar')).toBeNull();

    // Re-open and confirm
    fireEvent.click(screen.getByTestId('revoke-btn-key-1'));
    fireEvent.click(screen.getByTestId('confirm-revoke-btn'));

    await waitFor(() => {
      expect(settingsApi.revokeUnifiedMcpKey).toHaveBeenCalledWith('key-1');
      expect(screen.getAllByTestId('status-revoked').length).toBe(2);
    });

    // 2. Disconnect Connected App (Claude Code)
    const disconnectBtn = screen.getByTestId('disconnect-btn-grant-1');
    fireEvent.click(disconnectBtn);
    expect(screen.getByTestId('confirm-disconnect-bar')).not.toBeNull();

    // Cancel first
    fireEvent.click(screen.getByTestId('cancel-disconnect-btn'));
    expect(screen.queryByTestId('confirm-disconnect-bar')).toBeNull();

    // Re-open and confirm disconnect
    fireEvent.click(screen.getByTestId('disconnect-btn-grant-1'));
    expect(screen.getByTestId('confirm-disconnect-bar')).not.toBeNull();
    fireEvent.click(screen.getByTestId('confirm-disconnect-btn'));

    await waitFor(() => {
      expect(settingsApi.revokeConnectedApp).toHaveBeenCalledWith('grant-1');
      expect(screen.queryByTestId('app-row-grant-1')).toBeNull();
    });
  });

  it('renders hostile app names strictly as escaped text nodes (Anti-XSS)', async () => {
    vi.spyOn(settingsApi, 'fetchUnifiedMcpKeys').mockResolvedValue([]);
    vi.spyOn(settingsApi, 'fetchConnectedApps').mockResolvedValue(mockApps);

    render(
      <MemoryRouter initialEntries={['/settings/mcp']}>
        <McpAccessStudio tier="personal" />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('app-row-grant-1')).not.toBeNull();
    });

    const appNameEl = screen.getByTestId('app-name-grant-1');
    expect(appNameEl.textContent).toBe('<img src=x onerror=alert(1)> Claude Code');
    expect(appNameEl.querySelector('img')).toBeNull();
  });

  it('closes snippet modal on Escape key press and backdrop click', async () => {
    vi.spyOn(settingsApi, 'fetchUnifiedMcpKeys').mockResolvedValue([]);
    vi.spyOn(settingsApi, 'fetchConnectedApps').mockResolvedValue([]);

    const newlyMintedKey: settingsApi.McpApiKeyItem = {
      id: 'key-esc',
      label: 'Esc Test Key',
      display_hint: '1234',
      surface: 'agent',
      scope_tier: 'workspace',
      scopes: ['agent:read'],
      allowed_projects: null,
      created_at: new Date().toISOString(),
      expires_at: new Date().toISOString(),
      last_used_at: null,
      revoked_at: null,
      raw_key: 'raw_key_esc',
    };
    vi.spyOn(settingsApi, 'mintUnifiedMcpKey').mockResolvedValue(newlyMintedKey);

    render(
      <MemoryRouter initialEntries={['/settings/mcp']}>
        <McpAccessStudio tier="personal" />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('mint-key-button')).not.toBeNull();
    });

    fireEvent.click(screen.getByTestId('mint-key-button'));
    fireEvent.change(screen.getByTestId('mint-label-input'), { target: { value: 'Esc Test Key' } });
    fireEvent.click(screen.getByTestId('mint-submit-btn'));

    await screen.findByTestId('mcp-snippet-modal');
    await new Promise((r) => setTimeout(r, 50));

    // Close via Escape key press
    act(() => {
      fireEvent.keyDown(window, { key: 'Escape' });
    });

    await waitFor(() => {
      expect(screen.queryByTestId('mcp-snippet-modal')).toBeNull();
    }, { timeout: 8000 });
  });

  it('closes mint modal via cancel button and backdrop click, handles empty label and load error', async () => {
    // 1. Initial fetch failure
    vi.spyOn(settingsApi, 'fetchUnifiedMcpKeys').mockRejectedValueOnce(new Error('Network error'));
    vi.spyOn(settingsApi, 'fetchConnectedApps').mockResolvedValue([]);

    const { unmount } = render(
      <MemoryRouter initialEntries={['/settings/mcp']}>
        <McpAccessStudio tier="personal" />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('mint-key-button')).not.toBeNull();
    });
    unmount();

    // 2. Normal render
    vi.spyOn(settingsApi, 'fetchUnifiedMcpKeys').mockResolvedValue([]);
    vi.spyOn(settingsApi, 'fetchConnectedApps').mockResolvedValue([]);

    render(
      <MemoryRouter initialEntries={['/settings/mcp']}>
        <McpAccessStudio tier="personal" />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('mint-key-button')).not.toBeNull();
    });

    // Test empty label submit
    fireEvent.click(screen.getByTestId('mint-key-button'));
    const mintForm = screen.getByTestId('mint-label-input').closest('form');
    if (mintForm) {
      fireEvent.submit(mintForm);
    }
    // Still in modal because label was empty
    expect(screen.getByTestId('mint-label-input')).not.toBeNull();

    // Close via Cancel button
    const cancelBtn = screen.getByText('Cancel');
    fireEvent.click(cancelBtn);
    expect(screen.queryByTestId('mint-label-input')).toBeNull();

    // Open mint modal and close via close 'x' button
    fireEvent.click(screen.getByTestId('mint-key-button'));
    expect(screen.getByTestId('mint-label-input')).not.toBeNull();
    const closeBtn = screen.getByText('x');
    fireEvent.click(closeBtn);
    expect(screen.queryByTestId('mint-label-input')).toBeNull();

    // Open mint modal and close via backdrop click
    fireEvent.click(screen.getByTestId('mint-key-button'));
    expect(screen.getByTestId('mint-label-input')).not.toBeNull();
    const backdrop = screen.getByTestId('mint-modal-backdrop');
    fireEvent.click(backdrop);
    expect(screen.queryByTestId('mint-label-input')).toBeNull();
  });

  it('supports unlimited key minting with friction checkbox and disables button until confirmed', async () => {
    vi.spyOn(settingsApi, 'fetchUnifiedMcpKeys').mockResolvedValue([]);
    vi.spyOn(settingsApi, 'fetchConnectedApps').mockResolvedValue([]);

    const mintSpy = vi.spyOn(settingsApi, 'mintUnifiedMcpKey').mockResolvedValue({
      id: 'key-unlimited',
      label: 'Unlimited Token',
      display_hint: 'unl1',
      surface: 'agent',
      scope_tier: 'workspace',
      scopes: ['agent:read', 'agent:write'],
      allowed_projects: null,
      created_at: new Date().toISOString(),
      expires_at: null,
      last_used_at: null,
      revoked_at: null,
      raw_key: 'kb_agt_unlimited_secret',
    });

    render(
      <MemoryRouter initialEntries={['/settings/mcp']}>
        <McpAccessStudio tier="personal" />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('mint-key-button')).not.toBeNull();
    });

    fireEvent.click(screen.getByTestId('mint-key-button'));

    const labelInput = screen.getByTestId('mint-label-input');
    fireEvent.change(labelInput, { target: { value: 'Unlimited Token' } });

    const expirySelect = screen.getByTestId('mint-expiry-select');
    expect(screen.getByTestId('option-unlimited')).not.toBeNull();
    fireEvent.change(expirySelect, { target: { value: 'unlimited' } });

    // Warning box should be visible
    expect(screen.getByTestId('unlimited-warning-box')).not.toBeNull();

    // Submit button should be disabled until confirm checkbox is checked
    const submitBtn = screen.getByTestId('mint-submit-btn');
    expect((submitBtn as HTMLButtonElement).disabled).toBe(true);

    // Check confirmation checkbox
    const confirmCheckbox = screen.getByTestId('confirm-unlimited-checkbox');
    fireEvent.click(confirmCheckbox);
    expect((submitBtn as HTMLButtonElement).disabled).toBe(false);

    // Submit form
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(mintSpy).toHaveBeenCalledWith(
        expect.objectContaining({
          label: 'Unlimited Token',
          surface: 'agent',
          scopes: ['agent:read', 'agent:write'],
          scope_tier: 'workspace',
          owner_kind: 'personal_user',
          unlimited: true,
          confirm_unlimited: true,
        }),
      );
    });

    // Keys table should render 'Never (Unlimited)' for expires_at: null
    expect(screen.getByTestId('key-unlimited-key-unlimited')).not.toBeNull();
    expect(screen.getByTestId('key-unlimited-key-unlimited').textContent).toContain('Never (Unlimited)');
  });

  it('hides unlimited option when allow_unlimited_mcp_keys is false', async () => {
    vi.spyOn(settingsApi, 'fetchUnifiedMcpKeys').mockResolvedValue([]);
    vi.spyOn(settingsApi, 'fetchConnectedApps').mockResolvedValue([]);

    render(
      <MemoryRouter initialEntries={['/settings/mcp']}>
        <McpAccessStudio tier="personal" allowUnlimitedKeys={false} />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('mint-key-button')).not.toBeNull();
    });

    fireEvent.click(screen.getByTestId('mint-key-button'));
    expect(screen.queryByTestId('option-unlimited')).toBeNull();
  });

  it('supports granular tool disabling into disabled_tools on minting', async () => {
    vi.spyOn(settingsApi, 'fetchUnifiedMcpKeys').mockResolvedValue([]);
    vi.spyOn(settingsApi, 'fetchConnectedApps').mockResolvedValue([]);

    const mintSpy = vi.spyOn(settingsApi, 'mintUnifiedMcpKey').mockResolvedValue({
      id: 'key-narrow',
      label: 'Narrowed Agent Key',
      display_hint: 'nar1',
      surface: 'agent',
      scope_tier: 'workspace',
      scopes: ['agent:read', 'agent:write'],
      allowed_projects: null,
      created_at: new Date().toISOString(),
      expires_at: new Date(Date.now() + 86400000 * 30).toISOString(),
      disabled_tools: ['complete_work', 'add_comment'],
      last_used_at: null,
      revoked_at: null,
      raw_key: 'kb_agt_narrow_secret',
    });

    render(
      <MemoryRouter initialEntries={['/settings/mcp']}>
        <McpAccessStudio tier="personal" />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('mint-key-button')).not.toBeNull();
    });

    fireEvent.click(screen.getByTestId('mint-key-button'));
    fireEvent.change(screen.getByTestId('mint-label-input'), { target: { value: 'Narrowed Agent Key' } });

    // Tools selection grid should have tools
    expect(screen.getByTestId('tools-selection-grid')).not.toBeNull();
    const completeWorkCheckbox = screen.getByTestId('disable-tool-complete_work');
    const addCommentCheckbox = screen.getByTestId('disable-tool-add_comment');

    fireEvent.click(completeWorkCheckbox);
    fireEvent.click(addCommentCheckbox);

    fireEvent.click(screen.getByTestId('mint-submit-btn'));

    await waitFor(() => {
      expect(mintSpy).toHaveBeenCalledWith(
        expect.objectContaining({
          label: 'Narrowed Agent Key',
          surface: 'agent',
          scopes: ['agent:read', 'agent:write'],
          scope_tier: 'workspace',
          owner_kind: 'personal_user',
          expires_in_days: 60,
          disabled_tools: ['complete_work', 'add_comment'],
        }),
      );
    });
  });

  it('renders visible role="alert" error banner inside mint modal when API fails', async () => {
    vi.spyOn(settingsApi, 'fetchUnifiedMcpKeys').mockResolvedValue([]);
    vi.spyOn(settingsApi, 'fetchConnectedApps').mockResolvedValue([]);
    vi.spyOn(settingsApi, 'mintUnifiedMcpKey').mockRejectedValue(
      new Error('Forbidden: Insufficient privileges to mint key'),
    );

    render(
      <MemoryRouter initialEntries={['/settings/mcp']}>
        <McpAccessStudio tier="personal" />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('mint-key-button')).not.toBeNull();
    });

    fireEvent.click(screen.getByTestId('mint-key-button'));
    fireEvent.change(screen.getByTestId('mint-label-input'), {
      target: { value: 'Failing Key' },
    });

    fireEvent.click(screen.getByTestId('mint-submit-btn'));

    await waitFor(() => {
      const alert = screen.getByRole('alert');
      expect(alert).toBeDefined();
      expect(alert.textContent).toContain('Forbidden: Insufficient privileges to mint key');
    });
  });

  it('covers unlimited without confirm, unchecking disabled tools, and non-Error mint error fallback', async () => {
    vi.spyOn(settingsApi, 'fetchUnifiedMcpKeys').mockResolvedValue([]);
    vi.spyOn(settingsApi, 'fetchConnectedApps').mockResolvedValue([]);
    const mintSpy = vi.spyOn(settingsApi, 'mintUnifiedMcpKey').mockRejectedValueOnce('raw-string-error');

    const { container } = render(
      <MemoryRouter initialEntries={['/settings/mcp']}>
        <McpAccessStudio tier="personal" />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('mint-key-button')).not.toBeNull();
    });

    fireEvent.click(screen.getByTestId('mint-key-button'));
    fireEvent.change(screen.getByTestId('mint-label-input'), {
      target: { value: 'Unlimited Key' },
    });

    // Select unlimited without checking confirmUnlimited
    const expirySelect = screen.getByTestId('mint-expiry-select');
    fireEvent.change(expirySelect, { target: { value: 'unlimited' } });

    // Submit form directly while unconfirmed (exercises line 124-125 return)
    const form = container.querySelector<HTMLFormElement>('.kb-mcp-mint-form');
    expect(form).not.toBeNull();
    if (!form) {
      throw new Error('Mint form element not found');
    }
    fireEvent.submit(form);
    expect(mintSpy).not.toHaveBeenCalled();

    // Check disable tool then uncheck it (exercises line 595 filter)
    const disableToolCheckbox = screen.getByTestId('disable-tool-complete_work');
    fireEvent.click(disableToolCheckbox); // checked
    fireEvent.click(disableToolCheckbox); // unchecked

    // Now check confirmUnlimited
    const confirmCheckbox = screen.getByTestId('confirm-unlimited-checkbox');
    fireEvent.click(confirmCheckbox);

    // Submit with rejection (string error exercises line 159)
    fireEvent.submit(form);

    await waitFor(() => {
      const alert = screen.getByRole('alert');
      expect(alert).toBeDefined();
      expect(alert.textContent).toContain('Failed to mint MCP key.');
    });
  });

  it('covers minting under tier="global" and tier="project"', async () => {
    vi.spyOn(settingsApi, 'fetchUnifiedMcpKeys').mockResolvedValue([]);
    vi.spyOn(settingsApi, 'fetchConnectedApps').mockResolvedValue([]);
    const mintSpy = vi.spyOn(settingsApi, 'mintUnifiedMcpKey').mockResolvedValue({
      id: 'key-g1',
      label: 'Global Test Key',
      display_hint: 'g1g1',
      surface: 'agent',
      scope_tier: 'global',
      scopes: ['agent:read', 'agent:write'],
      allowed_projects: null,
      created_at: new Date().toISOString(),
      expires_at: new Date().toISOString(),
      last_used_at: null,
      revoked_at: null,
      raw_key: 'kb_mcp_raw_test_global',
    });

    const { unmount: u1 } = render(
      <MemoryRouter initialEntries={['/settings/mcp']}>
        <McpAccessStudio tier="global" />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('mint-key-button')).not.toBeNull();
    });

    fireEvent.click(screen.getByTestId('mint-key-button'));
    fireEvent.change(screen.getByTestId('mint-label-input'), {
      target: { value: 'Global Test Key' },
    });
    fireEvent.click(screen.getByTestId('mint-submit-btn'));

    await waitFor(() => {
      expect(mintSpy).toHaveBeenCalledWith(
        expect.objectContaining({ scope_tier: 'global', owner_kind: 'service_bot' }),
      );
    });
    u1();

    // Now test project tier
    const mintProjectSpy = vi.spyOn(settingsApi, 'mintUnifiedMcpKey').mockResolvedValue({
      id: 'key-p1',
      label: 'Project Test Key',
      display_hint: 'p1p1',
      surface: 'agent',
      scope_tier: 'project',
      scopes: ['agent:read', 'agent:write'],
      allowed_projects: ['KANBA'],
      created_at: new Date().toISOString(),
      expires_at: new Date().toISOString(),
      last_used_at: null,
      revoked_at: null,
      raw_key: 'kb_mcp_raw_test_proj',
    });

    render(
      <MemoryRouter initialEntries={['/projects/KANBA/settings/mcp']}>
        <Routes>
          <Route
            path="/projects/:projectKey/settings/mcp"
            element={<McpAccessStudio tier="project" />}
          />
        </Routes>
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('mint-key-button')).not.toBeNull();
    });

    fireEvent.click(screen.getByTestId('mint-key-button'));
    fireEvent.change(screen.getByTestId('mint-label-input'), {
      target: { value: 'Project Test Key' },
    });
    fireEvent.click(screen.getByTestId('mint-submit-btn'));

    await waitFor(() => {
      expect(mintProjectSpy).toHaveBeenCalledWith(
        expect.objectContaining({ scope_tier: 'project', allowed_projects: ['KANBA'] }),
      );
    });
  });

  it('covers tier badge edge cases, viewer tool narrowing, and non-Error rejections', async () => {
    vi.spyOn(settingsApi, 'fetchUnifiedMcpKeys').mockResolvedValue([
      {
        id: 'key-edge-1',
        label: 'Edge Tier Key',
        display_hint: 'e1e1',
        surface: 'agent',
        scope_tier: 'project',
        scopes: [],
        allowed_projects: [],
        created_at: new Date().toISOString(),
        expires_at: null,
        last_used_at: null,
        revoked_at: null,
      },
      {
        id: 'key-edge-2',
        label: 'Custom Tier Key',
        display_hint: 'e2e2',
        surface: 'agent',
        scope_tier: 'custom_tier' as never,
        scopes: [],
        allowed_projects: null,
        created_at: new Date().toISOString(),
        expires_at: null,
        last_used_at: null,
        revoked_at: null,
      },
    ]);

    // Mock viewer role
    vi.spyOn(settingsApi, 'fetchConnectedApps').mockResolvedValue([]);
    vi.spyOn(clientModule, 'apiFetch').mockImplementation((_method: string, path: string) => {
      if (path === '/api/v1/projects') {
        return Promise.resolve({
          items: [
            { id: 'proj-kanba', identifier: 'KANBA', name: 'Kanban Core' },
            { id: 'proj-ops', identifier: 'OPS', name: 'Operations' },
          ],
        });
      }
      return Promise.resolve({
        id: 'u-viewer',
        handle: 'viewer_user',
        workspace_role: 'VIEWER',
        is_workspace_admin: false,
        is_server_admin: false,
      });
    });

    render(
      <MemoryRouter initialEntries={['/settings/mcp']}>
        <McpAccessStudio tier="personal" />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByText(/Project: KANBA/)).toBeDefined();
      expect(screen.getByTestId('revoke-btn-key-edge-1')).toBeDefined();
    });

    // Revoke failure with non-Error string
    vi.spyOn(settingsApi, 'revokeUnifiedMcpKey').mockRejectedValueOnce('Plain revoke failure');
    fireEvent.click(screen.getByTestId('revoke-btn-key-edge-1'));
    fireEvent.click(screen.getByTestId('confirm-revoke-btn'));
    await waitFor(() => {
      expect(screen.queryByTestId('confirm-revoke-bar')).toBeNull();
    });

    // Mint modal with viewer role and non-Error mint rejection
    fireEvent.click(screen.getByTestId('mint-key-button'));
    vi.spyOn(settingsApi, 'mintUnifiedMcpKey').mockRejectedValueOnce('Plain mint failure');
    fireEvent.change(screen.getByTestId('mint-label-input'), {
      target: { value: 'Viewer Key' },
    });
    fireEvent.click(screen.getByTestId('mint-submit-btn'));
    await waitFor(() => {
      expect(screen.getByTestId('mint-error-banner').textContent).toContain('Failed to mint MCP key.');
    });
  });

  it('renders dynamic KAN and OPS project options in scope-project-select with 0 hardcoded KANBA or QAADM options', async () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    vi.spyOn(settingsApi, 'fetchUnifiedMcpKeys').mockResolvedValue(mockKeys);
    vi.spyOn(settingsApi, 'fetchConnectedApps').mockResolvedValue(mockApps);
    vi.spyOn(clientModule, 'apiFetch').mockImplementation((_method: string, path: string) => {
      if (path === '/api/v1/projects') {
        return Promise.resolve({
          items: [
            { id: 'p-kan', identifier: 'KAN', name: 'Kanban Core' },
            { id: 'p-ops', identifier: 'OPS', name: 'Operations' },
          ],
        });
      }
      return Promise.resolve({ is_server_admin: true, is_workspace_admin: true });
    });

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={['/settings/mcp?scope=project']}>
          <McpAccessStudio tier="personal" />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('scope-project-select')).toBeDefined();
    });

    const select = screen.getByTestId<HTMLSelectElement>('scope-project-select');
    const options = Array.from(select.querySelectorAll('option')).map((o) => o.value);
    expect(options).toEqual(['KAN', 'OPS']);
    expect(options).not.toContain('KANBA');
    expect(options).not.toContain('QAADM');
  });

  it('awaits queryClient.invalidateQueries and reloads data upon minting a key', async () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries');

    vi.spyOn(settingsApi, 'fetchUnifiedMcpKeys').mockResolvedValue(mockKeys);
    vi.spyOn(settingsApi, 'fetchConnectedApps').mockResolvedValue(mockApps);
    vi.spyOn(settingsApi, 'mintUnifiedMcpKey').mockResolvedValue({
      id: 'key-new',
      label: 'Newly Minted Key',
      display_hint: 'n3w1',
      surface: 'agent',
      scope_tier: 'workspace',
      scopes: ['agent:read'],
      allowed_projects: null,
      created_at: new Date().toISOString(),
      expires_at: null,
      last_used_at: null,
      revoked_at: null,
      raw_key: 'mpk_live_secret_123',
    });

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={['/settings/mcp']}>
          <McpAccessStudio tier="personal" />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('mint-key-button')).toBeDefined();
    });

    fireEvent.click(screen.getByTestId('mint-key-button'));
    fireEvent.change(screen.getByTestId('mint-label-input'), {
      target: { value: 'Newly Minted Key' },
    });
    fireEvent.click(screen.getByTestId('mint-submit-btn'));

    await waitFor(() => {
      expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['mcp-keys'] });
    });
  });

  it('opens and closes ConnectOAuthAppModal from header button and empty state', async () => {
    vi.spyOn(settingsApi, 'fetchUnifiedMcpKeys').mockResolvedValue(mockKeys);
    vi.spyOn(settingsApi, 'fetchConnectedApps').mockResolvedValue(mockApps);

    render(
      <MemoryRouter initialEntries={['/settings/mcp']}>
        <McpAccessStudio tier="personal" />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('connect-oauth-app-btn')).toBeDefined();
    });

    // 1. Open modal via header button
    fireEvent.click(screen.getByTestId('connect-oauth-app-btn'));
    await waitFor(() => {
      expect(screen.getByTestId('connect-oauth-app-modal')).toBeDefined();
      expect(screen.getByTestId('scope-tier-select')).toBeDefined();
    });

    // Close modal via close button
    fireEvent.click(screen.getByTestId('close-connect-oauth-modal-btn'));
    await waitFor(() => {
      expect(screen.queryByTestId('connect-oauth-app-modal')).toBeNull();
    });
  });

  it('handles projects returned as array or with key field, and covers modal backdrop close', async () => {
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    vi.spyOn(settingsApi, 'fetchUnifiedMcpKeys').mockResolvedValue(mockKeys);
    vi.spyOn(settingsApi, 'fetchConnectedApps').mockResolvedValue([]);
    vi.spyOn(clientModule, 'apiFetch').mockImplementation((_method: string, path: string) => {
      if (path === '/api/v1/projects') {
        return Promise.resolve([
          { id: 'p-direct', key: 'DIR', name: 'Direct Project' },
        ]);
      }
      if (path === '/api/v1/workspaces') {
        return Promise.resolve([{ id: 'w1', name: 'W1', slug: 'w1-slug', is_current: true }]);
      }
      return Promise.resolve({ is_server_admin: true, is_workspace_admin: true });
    });

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={['/settings/mcp?scope=project']}>
          <McpAccessStudio tier="personal" />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('scope-project-select')).toBeDefined();
    });

    const select = screen.getByTestId<HTMLSelectElement>('scope-project-select');
    expect(select.value).toBe('DIR');

    // Open connect modal and close via backdrop click
    fireEvent.click(screen.getByTestId('empty-connect-oauth-app-btn'));
    await waitFor(() => {
      expect(screen.getByTestId('connect-oauth-app-modal')).toBeDefined();
    });
    fireEvent.click(screen.getByTestId('connect-oauth-modal-backdrop'));
    await waitFor(() => {
      expect(screen.queryByTestId('connect-oauth-app-modal')).toBeNull();
    });
  });

  it('mints a service_bot key when Key Type is switched to Service Bot in mint modal', async () => {
    vi.spyOn(settingsApi, 'fetchUnifiedMcpKeys').mockResolvedValue([]);
    vi.spyOn(settingsApi, 'fetchConnectedApps').mockResolvedValue([]);
    const mintSpy = vi.spyOn(settingsApi, 'mintUnifiedMcpKey').mockResolvedValue({
      id: 'key-bot-1',
      label: 'Automation Bot Key',
      display_hint: 'bot1',
      surface: 'agent',
      scope_tier: 'workspace',
      owner_kind: 'service_bot',
      scopes: ['agent:read', 'agent:write'],
      allowed_projects: null,
      created_at: new Date().toISOString(),
      expires_at: null,
      last_used_at: null,
      revoked_at: null,
      raw_key: 'kb_agt_bot_key_123',
    });

    render(
      <MemoryRouter initialEntries={['/settings/mcp']}>
        <McpAccessStudio tier="personal" />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('mint-key-button')).not.toBeNull();
    });

    fireEvent.click(screen.getByTestId('mint-key-button'));

    const labelInput = screen.getByTestId('mint-label-input');
    fireEvent.change(labelInput, { target: { value: 'Automation Bot Key' } });

    // Switch Key Type to Service Bot
    const ownerSelect = screen.getByTestId('mint-key-scope-type-select');
    fireEvent.change(ownerSelect, { target: { value: 'service_bot:workspace' } });

    fireEvent.click(screen.getByTestId('mint-submit-btn'));

    await waitFor(() => {
      expect(mintSpy).toHaveBeenCalledWith(
        expect.objectContaining({
          label: 'Automation Bot Key',
          owner_kind: 'service_bot',
          scope_tier: 'workspace',
        }),
      );
    });
  });

  it('allows admin in governance view to revoke a service_bot or foreign key via revokeUnifiedMcpKey without 404', async () => {
    const foreignBotKey: settingsApi.McpApiKeyItem = {
      id: 'bot-foreign-999',
      label: 'Foreign Service Bot',
      display_hint: 'f999',
      surface: 'agent',
      scope_tier: 'workspace',
      owner_kind: 'service_bot',
      scopes: ['agent:read'],
      allowed_projects: null,
      created_at: new Date().toISOString(),
      expires_at: null,
      last_used_at: null,
      revoked_at: null,
    };

    vi.spyOn(settingsApi, 'fetchUnifiedMcpKeys').mockResolvedValue([foreignBotKey]);
    const revokeSpy = vi.spyOn(settingsApi, 'revokeUnifiedMcpKey').mockResolvedValue(undefined);

    render(
      <MemoryRouter initialEntries={['/settings/mcp?view=governance']}>
        <McpAccessStudio user={{ is_server_admin: true, is_workspace_admin: true }} />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('key-row-bot-foreign-999')).toBeDefined();
    });

    fireEvent.click(screen.getByTestId('revoke-btn-bot-foreign-999'));
    await waitFor(() => {
      expect(screen.getByTestId('confirm-revoke-btn')).toBeDefined();
    });
    fireEvent.click(screen.getByTestId('confirm-revoke-btn'));

    await waitFor(() => {
      expect(revokeSpy).toHaveBeenCalledWith('bot-foreign-999');
    });
  });

  it('selects View Only preset, sends scopes: ["agent:read"], capability_mask: 1, allowed_cidrs: ["192.168.1.0/24"], and renders narrowing badges on key row (KAN-68 Action 1)', async () => {
    vi.spyOn(settingsApi, 'fetchUnifiedMcpKeys').mockResolvedValue([]);
    vi.spyOn(settingsApi, 'fetchConnectedApps').mockResolvedValue([]);
    const mintSpy = vi.spyOn(settingsApi, 'mintUnifiedMcpKey').mockResolvedValue({
      id: 'key-view-only-1',
      label: 'Readonly Auditor Key',
      display_hint: 'v1v1',
      surface: 'agent',
      scope_tier: 'workspace',
      scopes: ['agent:read'],
      allowed_projects: null,
      capability_mask: 1,
      allowed_cidrs: ['192.168.1.0/24'],
      created_at: new Date().toISOString(),
      expires_at: null,
      last_used_at: null,
      revoked_at: null,
      raw_key: 'kb_agt_readonly_token',
    });

    render(
      <MemoryRouter initialEntries={['/settings/mcp']}>
        <McpAccessStudio tier="personal" />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('mint-key-button')).not.toBeNull();
    });

    fireEvent.click(screen.getByTestId('mint-key-button'));

    // Label
    fireEvent.change(screen.getByTestId('mint-label-input'), {
      target: { value: 'Readonly Auditor Key' },
    });

    // Capability preset selector: choose View Only (1)
    const presetSelect = screen.getByTestId('capability-preset-select');
    fireEvent.change(presetSelect, { target: { value: '1' } });

    // Allowed CIDRs input: enter valid CIDR
    const cidrInput = screen.getByTestId('mint-allowed-cidrs-input');
    fireEvent.change(cidrInput, { target: { value: '192.168.1.0/24' } });

    expect(screen.queryByTestId('cidr-error-message')).toBeNull();

    // Submit
    fireEvent.click(screen.getByTestId('mint-submit-btn'));

    await waitFor(() => {
      expect(mintSpy).toHaveBeenCalledWith(
        expect.objectContaining({
          label: 'Readonly Auditor Key',
          surface: 'agent',
          scopes: ['agent:read'],
          capability_mask: 1,
          allowed_cidrs: ['192.168.1.0/24'],
        }),
      );
    });

    // Close snippet modal
    fireEvent.click(screen.getByTestId('modal-close-button'));

    // Check narrowing badges rendered on key row
    await waitFor(() => {
      expect(screen.getByTestId('key-cap-mask-key-view-only-1').textContent).toContain('Mask: 1');
      expect(screen.getByTestId('key-cidr-badge-key-view-only-1').textContent).toContain('CIDR: 192.168.1.0/24');
    });
  });

  it('validates CIDR input client-side, showing inline accessible error on malformed CIDR and disabling submit (KAN-68 Negative)', async () => {
    vi.spyOn(settingsApi, 'fetchUnifiedMcpKeys').mockResolvedValue([]);
    vi.spyOn(settingsApi, 'fetchConnectedApps').mockResolvedValue([]);

    render(
      <MemoryRouter initialEntries={['/settings/mcp']}>
        <McpAccessStudio tier="personal" />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('mint-key-button')).not.toBeNull();
    });

    fireEvent.click(screen.getByTestId('mint-key-button'));

    fireEvent.change(screen.getByTestId('mint-label-input'), {
      target: { value: 'CIDR Test Key' },
    });

    const cidrInput = screen.getByTestId('mint-allowed-cidrs-input');
    const submitBtn = screen.getByTestId<HTMLButtonElement>('mint-submit-btn');

    // Enter malformed CIDR
    fireEvent.change(cidrInput, { target: { value: '999.999.1.1/99' } });

    expect(screen.getByTestId('cidr-error-message')).toBeDefined();
    expect(screen.getByTestId('cidr-error-message').textContent).toContain('Invalid CIDR format');
    expect(submitBtn.disabled).toBe(true);

    // Enter another invalid format (missing prefix)
    fireEvent.change(cidrInput, { target: { value: '192.168.1.1' } });
    expect(screen.getByTestId('cidr-error-message')).toBeDefined();
    expect(submitBtn.disabled).toBe(true);

    // Enter valid IPv4 and IPv6 CIDRs
    fireEvent.change(cidrInput, { target: { value: '10.0.0.0/8, 2001:db8::/32' } });
    expect(screen.queryByTestId('cidr-error-message')).toBeNull();
    expect(submitBtn.disabled).toBe(false);
  });

  it('supports granular capability bit toggles and switches preset to custom (KAN-68 Edge)', async () => {
    vi.spyOn(settingsApi, 'fetchUnifiedMcpKeys').mockResolvedValue([]);
    vi.spyOn(settingsApi, 'fetchConnectedApps').mockResolvedValue([]);

    render(
      <MemoryRouter initialEntries={['/settings/mcp']}>
        <McpAccessStudio tier="personal" />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('mint-key-button')).not.toBeNull();
    });

    fireEvent.click(screen.getByTestId('mint-key-button'));

    const presetSelect = screen.getByTestId<HTMLSelectElement>('capability-preset-select');
    expect(presetSelect.value).toBe('31');

    // Toggle bit 128 (DELETE) on -> mask becomes 31 | 128 = 159
    const deleteBit = screen.getByTestId<HTMLInputElement>('cap-bit-128');
    expect(deleteBit.checked).toBe(false);
    fireEvent.click(deleteBit);
    expect(deleteBit.checked).toBe(true);

    // Preset select reflects custom
    expect(presetSelect.value).toBe('custom');

    // Toggle bit 128 back off
    fireEvent.click(deleteBit);
    expect(deleteBit.checked).toBe(false);
    expect(presetSelect.value).toBe('31');

    // Select Full / Admin (255)
    fireEvent.change(presetSelect, { target: { value: '255' } });
    expect(deleteBit.checked).toBe(true);
  });

  it('handles AAL2 cancellation on mint, load, and revoke operations', async () => {
    // 1. AAL2 cancellation on loadData
    vi.spyOn(settingsApi, 'fetchUnifiedMcpKeys').mockRejectedValueOnce(
      new clientModule.Aal2StepUpCancelledError(),
    );
    vi.spyOn(settingsApi, 'fetchConnectedApps').mockResolvedValue([]);

    const { unmount } = render(
      <MemoryRouter initialEntries={['/settings/mcp']}>
        <McpAccessStudio tier="personal" />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(settingsApi.fetchUnifiedMcpKeys).toHaveBeenCalled();
    });
    expect(screen.queryByTestId('aal2-modal-card')).toBeNull();
    expect(screen.queryByTestId('studio-error-banner')).toBeNull();
    unmount();

    // 2. AAL2 cancellation on minting
    vi.spyOn(settingsApi, 'fetchUnifiedMcpKeys').mockResolvedValue([]);
    vi
      .spyOn(settingsApi, 'mintUnifiedMcpKey')
      .mockRejectedValueOnce(new clientModule.Aal2StepUpCancelledError())
      .mockResolvedValueOnce({
        id: 'k-stepped-up',
        label: 'Step-Up Key',
        display_hint: 'su1',
        surface: 'agent',
        scope_tier: 'workspace',
        scopes: ['agent:read'],
        allowed_projects: null,
        created_at: new Date().toISOString(),
        expires_at: null,
        last_used_at: null,
        revoked_at: null,
        raw_key: 'kb_agt_stepped_key',
      });

    render(
      <MemoryRouter initialEntries={['/settings/mcp']}>
        <McpAccessStudio tier="personal" />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('mint-key-button')).not.toBeNull();
    });

    fireEvent.click(screen.getByTestId('mint-key-button'));
    fireEvent.change(screen.getByTestId('mint-label-input'), {
      target: { value: 'Step-Up Key' },
    });
    fireEvent.click(screen.getByTestId('mint-submit-btn'));

    await waitFor(() => {
      expect(settingsApi.mintUnifiedMcpKey).toHaveBeenCalledTimes(1);
    });
    expect(screen.queryByTestId('mint-error-banner')).toBeNull();

    // Re-submit and test success
    fireEvent.click(screen.getByTestId('mint-submit-btn'));

    await waitFor(() => {
      expect(screen.getByTestId('mcp-snippet-modal')).toBeDefined();
    });
    fireEvent.click(screen.getByTestId('modal-close-button'));

    // 3. AAL2 cancellation on revoke
    const revokeSpy = vi
      .spyOn(settingsApi, 'revokeUnifiedMcpKey')
      .mockRejectedValueOnce(new clientModule.Aal2StepUpCancelledError())
      .mockResolvedValueOnce(undefined);

    fireEvent.click(screen.getByTestId('revoke-btn-k-stepped-up'));
    fireEvent.click(screen.getByTestId('confirm-revoke-btn'));

    await waitFor(() => {
      expect(revokeSpy).toHaveBeenCalledWith('k-stepped-up');
    });
    expect(screen.queryByTestId('studio-error-banner')).toBeNull();

    fireEvent.click(screen.getByTestId('revoke-btn-k-stepped-up'));
    fireEvent.click(screen.getByTestId('confirm-revoke-btn'));
    await waitFor(() => {
      expect(revokeSpy).toHaveBeenCalledTimes(2);
    });
  });

  it('exercises validateCidrInput comprehensive branch coverage', () => {
    // Empty / whitespace
    expect(validateCidrInput('')).toEqual({ valid: true, cidrs: [] });
    expect(validateCidrInput('   \n  ')).toEqual({ valid: true, cidrs: [] });

    // IPv4 valid and invalid
    expect(validateCidrInput('192.168.1.1').valid).toBe(false);
    expect(validateCidrInput('192.168.1.1/33').valid).toBe(false);
    expect(validateCidrInput('192.168.1.1/abc').valid).toBe(false);
    expect(validateCidrInput('192.168.1/24').valid).toBe(false);
    expect(validateCidrInput('192.168.1.1.1/24').valid).toBe(false);
    expect(validateCidrInput('192.168.1.256/24').valid).toBe(false);
    expect(validateCidrInput('192.168.01.1/24').valid).toBe(false);
    expect(validateCidrInput('192.168.1.x/24').valid).toBe(false);

    // IPv6 valid and invalid
    expect(validateCidrInput('2001:db8::/129').valid).toBe(false);
    expect(validateCidrInput('2001:db8::/abc').valid).toBe(false);
    expect(validateCidrInput('2001:::1/64').valid).toBe(false);
    expect(validateCidrInput('2001::db8::1/64').valid).toBe(false);
    expect(validateCidrInput('2001:db8:1:2:3:4:5/64').valid).toBe(false);
    expect(validateCidrInput('2001:db8:1:2:3:4:5:6:7::/64').valid).toBe(false);
    expect(validateCidrInput('2001:db8:12345::1/64').valid).toBe(false);
    expect(validateCidrInput('2001:db8:zzzz::1/64').valid).toBe(false);
    expect(validateCidrInput('2001:db8:0:0:0:0:0:1/128').valid).toBe(true);
    expect(validateCidrInput('fe80::1/64').valid).toBe(true);

    // Multiple valid
    const multi = validateCidrInput('2001:db8::/32, 10.0.0.0/8');
    expect(multi.valid).toBe(true);
    expect(multi.cidrs).toEqual(['2001:db8::/32', '10.0.0.0/8']);
  });

  it('covers scope filter pills, project selector change, and view toggling', async () => {
    vi.spyOn(settingsApi, 'fetchUnifiedMcpKeys').mockResolvedValue([]);
    vi.spyOn(settingsApi, 'fetchConnectedApps').mockResolvedValue([]);

    render(
      <MemoryRouter initialEntries={['/settings/mcp?scope=all']}>
        <McpAccessStudio tier="global" user={{ is_server_admin: true }} />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('mcp-filter-bar')).not.toBeNull();
    });

    // Toggle views
    await act(async () => {
      fireEvent.click(screen.getByTestId('view-governance-btn'));
      await Promise.resolve();
    });
    await act(async () => {
      fireEvent.click(screen.getByTestId('view-mine-btn'));
      await Promise.resolve();
    });

    // Toggle scope pills
    await act(async () => {
      fireEvent.click(screen.getByTestId('scope-pill-project'));
      await Promise.resolve();
    });
    expect(screen.getByTestId('scope-project-container')).not.toBeNull();
    await act(async () => {
      fireEvent.change(screen.getByTestId('scope-project-select'), { target: { value: 'OPS' } });
      await Promise.resolve();
    });

    await act(async () => {
      fireEvent.click(screen.getByTestId('scope-pill-workspace'));
      fireEvent.click(screen.getByTestId('scope-pill-server'));
      fireEvent.click(screen.getByTestId('scope-pill-all'));
      await Promise.resolve();
    });
  });

  it('supports minting personal_user and project scoped keys with custom CIDRs', async () => {
    vi.spyOn(settingsApi, 'fetchUnifiedMcpKeys').mockResolvedValue([]);
    vi.spyOn(settingsApi, 'fetchConnectedApps').mockResolvedValue([]);

    const mintSpy = vi.spyOn(settingsApi, 'mintUnifiedMcpKey').mockResolvedValue({
      id: 'k-custom-scope',
      label: 'Personal Key',
      display_hint: 'ps1',
      surface: 'agent',
      scope_tier: 'workspace',
      scopes: ['agent:read'],
      allowed_projects: ['PROJ-A'],
      created_at: new Date().toISOString(),
      expires_at: null,
      last_used_at: null,
      revoked_at: null,
      raw_key: 'kb_agt_proj_secret',
    });

    render(
      <MemoryRouter initialEntries={['/settings/mcp']}>
        <McpAccessStudio tier="workspace" user={{ is_server_admin: true }} />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('mint-key-button')).not.toBeNull();
    });

    fireEvent.click(screen.getByTestId('mint-key-button'));

    // Select project scope
    fireEvent.change(screen.getByTestId('mint-key-scope-type-select'), {
      target: { value: 'personal_user:project' },
    });
    expect(screen.getByTestId('mint-project-input')).not.toBeNull();
    fireEvent.change(screen.getByTestId('mint-project-input'), {
      target: { value: 'PROJ-A' },
    });

    // Set valid IPv6 and IPv4 CIDRs
    fireEvent.change(screen.getByTestId('mint-allowed-cidrs-input'), {
      target: { value: '2001:db8::/32, 10.0.0.0/8' },
    });
    fireEvent.change(screen.getByTestId('mint-label-input'), {
      target: { value: 'Project Key' },
    });

    fireEvent.click(screen.getByTestId('mint-submit-btn'));

    await waitFor(() => {
      expect(mintSpy).toHaveBeenCalledWith(
        expect.objectContaining({
          label: 'Project Key',
          scope_tier: 'project',
          allowed_projects: ['PROJ-A'],
          allowed_cidrs: ['2001:db8::/32', '10.0.0.0/8'],
        }),
      );
    });
  });

  it('handles AAL2 cancellation on loadData, minting, and revoking without errors and reports generic errors', async () => {
    // 1. Cancellation on loadData
    vi.spyOn(settingsApi, 'fetchUnifiedMcpKeys').mockRejectedValueOnce(
      new clientModule.Aal2StepUpCancelledError(),
    );
    vi.spyOn(settingsApi, 'fetchConnectedApps').mockResolvedValue([]);

    const { unmount } = render(
      <MemoryRouter initialEntries={['/settings/mcp?project=UNKNOWN_PROJ&scope=project']}>
        <McpAccessStudio tier="project" />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(settingsApi.fetchUnifiedMcpKeys).toHaveBeenCalled();
    });
    expect(screen.queryByTestId('studio-error-banner')).toBeNull();
    unmount();

    // 2. Cancellation on minting
    vi.spyOn(settingsApi, 'fetchUnifiedMcpKeys').mockResolvedValue([]);
    vi.spyOn(settingsApi, 'mintUnifiedMcpKey').mockRejectedValueOnce(
      new clientModule.Aal2StepUpCancelledError(),
    );

    const { unmount: unmount2 } = render(
      <MemoryRouter initialEntries={['/settings/mcp']}>
        <McpAccessStudio tier="personal" />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('mint-key-button')).not.toBeNull();
    });

    fireEvent.click(screen.getByTestId('mint-key-button'));
    fireEvent.change(screen.getByTestId('mint-label-input'), { target: { value: 'Stale Key' } });
    fireEvent.click(screen.getByTestId('mint-submit-btn'));

    await waitFor(() => {
      expect(settingsApi.mintUnifiedMcpKey).toHaveBeenCalled();
    });
    expect(screen.queryByTestId('mint-error-banner')).toBeNull();
    unmount2();

    // 3. Cancellation on revoke
    vi.spyOn(settingsApi, 'fetchUnifiedMcpKeys').mockResolvedValue([
      {
        id: 'k-stale-rev',
        label: 'Stale Revoke',
        display_hint: 'sr1',
        surface: 'agent',
        scope_tier: 'workspace',
        scopes: ['agent:read'],
        allowed_projects: null,
        created_at: new Date().toISOString(),
        expires_at: null,
        last_used_at: null,
        revoked_at: null,
      },
    ]);
    const revokeSpy = vi.spyOn(settingsApi, 'revokeUnifiedMcpKey').mockRejectedValueOnce(
      new clientModule.Aal2StepUpCancelledError(),
    );

    render(
      <MemoryRouter initialEntries={['/settings/mcp']}>
        <McpAccessStudio tier="personal" />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('revoke-btn-k-stale-rev')).not.toBeNull();
    });

    fireEvent.click(screen.getByTestId('revoke-btn-k-stale-rev'));
    fireEvent.click(screen.getByTestId('confirm-revoke-btn'));

    await waitFor(() => {
      expect(revokeSpy).toHaveBeenCalledWith('k-stale-rev');
    });
    expect(screen.queryByTestId('studio-error-banner')).toBeNull();

    // Also cover regular Error on revoke
    revokeSpy.mockRejectedValueOnce(new Error('Generic revoke failure'));
    fireEvent.click(screen.getByTestId('revoke-btn-k-stale-rev'));
    fireEvent.click(screen.getByTestId('confirm-revoke-btn'));
    await waitFor(() => {
      expect(screen.getByTestId('studio-error-banner')).not.toBeNull();
    });
  });

  it('handles global scope in query parameters', async () => {
    vi.spyOn(settingsApi, 'fetchUnifiedMcpKeys').mockResolvedValue([]);
    vi.spyOn(settingsApi, 'fetchConnectedApps').mockResolvedValue([]);

    render(
      <MemoryRouter initialEntries={['/settings/mcp?scope=global']}>
        <McpAccessStudio tier="personal" user={{ is_server_admin: true }} />
      </MemoryRouter>,
    );
    await waitFor(() => {
      expect(screen.getByTestId('mcp-filter-bar')).not.toBeNull();
    });
  });

  it('renders keys with project scope and null allowed_projects', async () => {
    const sampleKeys: settingsApi.McpApiKeyItem[] = [
      {
        id: 'k-proj-null',
        label: 'Proj Key Null Allowed',
        display_hint: 'pn1',
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
    vi.spyOn(settingsApi, 'fetchUnifiedMcpKeys').mockResolvedValue(sampleKeys);
    vi.spyOn(settingsApi, 'fetchConnectedApps').mockResolvedValue([]);

    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <MemoryRouter initialEntries={['/settings/mcp?scope=project&project=OPS']}>
          <McpAccessStudio tier="project" user={{ is_server_admin: true }} />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    await waitFor(() => {
      expect(screen.getByTestId('key-row-k-proj-null')).not.toBeNull();
    });
  });

  it('handles non-Error rejection on revoke and displays studio error banner', async () => {
    const sampleKeys: settingsApi.McpApiKeyItem[] = [
      {
        id: 'k-serv',
        label: 'Server Key',
        display_hint: 'sv1',
        surface: 'agent',
        scope_tier: 'global',
        scopes: ['agent:read'],
        allowed_projects: null,
        created_at: new Date().toISOString(),
        expires_at: null,
        last_used_at: null,
        revoked_at: null,
      },
    ];
    vi.spyOn(settingsApi, 'fetchUnifiedMcpKeys').mockResolvedValue(sampleKeys);
    vi.spyOn(settingsApi, 'fetchConnectedApps').mockResolvedValue([]);
    vi.spyOn(settingsApi, 'revokeUnifiedMcpKey').mockRejectedValueOnce('string revoke rejection');

    render(
      <MemoryRouter initialEntries={['/settings/mcp?scope=server']}>
        <McpAccessStudio tier="global" user={{ is_server_admin: true }} />
      </MemoryRouter>,
    );
    await waitFor(() => {
      expect(screen.getByTestId('revoke-btn-k-serv')).not.toBeNull();
    });
    fireEvent.click(screen.getByTestId('revoke-btn-k-serv'));
    fireEvent.click(screen.getByTestId('confirm-revoke-btn'));
    await waitFor(() => {
      expect(screen.getByTestId('studio-error-banner')).not.toBeNull();
    });
  });

  it('mints global key with invalid CIDR submit edge case', async () => {
    vi.spyOn(settingsApi, 'fetchUnifiedMcpKeys').mockResolvedValue([]);
    vi.spyOn(settingsApi, 'fetchConnectedApps').mockResolvedValue([]);

    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <MemoryRouter initialEntries={['/settings/mcp']}>
          <McpAccessStudio tier="workspace" user={{ is_server_admin: true }} />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('mint-key-button')).not.toBeNull();
    });

    // Select Global scope in mint modal, enter invalid CIDR, and force form submit
    fireEvent.click(screen.getByTestId('mint-key-button'));
    fireEvent.change(screen.getByTestId('mint-key-scope-type-select'), { target: { value: 'service_bot:global' } });
    fireEvent.change(screen.getByTestId('mint-label-input'), { target: { value: 'Global Key' } });
    fireEvent.change(screen.getByTestId('mint-allowed-cidrs-input'), { target: { value: '999.999.999.999/99' } });

    const form = screen.getByTestId('mint-label-input').closest('form');
    expect(form).not.toBeNull();
    if (form) {
      fireEvent.submit(form);
    }
    await waitFor(() => {
      expect(screen.getByTestId('mint-error-banner')).not.toBeNull();
    });
  });

  it('covers fallback projects from keys and error catching in projects/workspaces queries', async () => {
    vi.spyOn(clientModule, 'apiFetch').mockImplementation((_method, path) => {
      if (path === '/api/v1/projects' || path === '/api/v1/workspaces') {
        return Promise.reject(new Error('Network failure'));
      }
      return Promise.resolve({});
    });

    vi.spyOn(settingsApi, 'fetchUnifiedMcpKeys').mockResolvedValue([
      {
        id: 'k-fallback-p',
        label: 'Fallback Key',
        display_hint: 'fb1',
        surface: 'agent',
        scope_tier: 'project',
        scopes: ['agent:read'],
        allowed_projects: ['FALLBACK_PROJ', ''],
        created_at: new Date().toISOString(),
        expires_at: null,
        last_used_at: null,
        revoked_at: null,
      },
    ]);
    vi.spyOn(settingsApi, 'fetchConnectedApps').mockResolvedValue([]);

    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <MemoryRouter initialEntries={['/settings/mcp?scope=all']}>
          <McpAccessStudio tier="personal" user={{ is_server_admin: true }} />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('key-row-k-fallback-p')).not.toBeNull();
    });
  });

  it('covers custom preset selection, project datalist fallback, and snippet modal projectKey branch', async () => {
    vi.spyOn(settingsApi, 'fetchUnifiedMcpKeys').mockResolvedValue([]);
    vi.spyOn(settingsApi, 'fetchConnectedApps').mockResolvedValue([]);
    vi.spyOn(clientModule, 'apiFetch').mockImplementation((_method: string, path: string) => {
      if (path === '/api/v1/projects') {
        return Promise.resolve({
          items: [
            { id: 'proj-kanba', identifier: 'KANBA', name: 'Kanban Core' },
            { id: 'proj-same', identifier: 'SAME', name: 'SAME' },
            { id: 'proj-noname', identifier: 'NONAME', name: '' },
          ],
        });
      }
      return Promise.resolve({
        is_server_admin: true,
        is_workspace_admin: true,
      });
    });

    const mintSpy = vi.spyOn(settingsApi, 'mintUnifiedMcpKey').mockResolvedValue({
      id: 'k-snippet-p',
      label: 'Snippet Proj Key',
      display_hint: 'sn1',
      surface: 'agent',
      scope_tier: 'project',
      scopes: ['agent:read'],
      allowed_projects: ['KANBA'],
      created_at: new Date().toISOString(),
      expires_at: null,
      last_used_at: null,
      revoked_at: null,
      raw_key: 'kb_agt_snip_key',
    });

    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <MemoryRouter initialEntries={['/settings/mcp']}>
          <McpAccessStudio tier="workspace" user={{ is_server_admin: true }} />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('mint-key-button')).not.toBeNull();
    });

    fireEvent.click(screen.getByTestId('mint-key-button'));

    // 1. Toggle bit to make capability mask custom (e.g. uncheck bit 128 DELETE)
    const delBit = screen.getByTestId<HTMLInputElement>('cap-bit-128');
    fireEvent.click(delBit);

    // Now preset select renders custom option; select 'custom' to test val !== 'custom' false branch
    const presetSelect = screen.getByTestId('capability-preset-select');
    fireEvent.change(presetSelect, { target: { value: 'custom' } });

    // 2. Switch to project scope tier so mint-project-datalist renders with SAME and NONAME
    fireEvent.change(screen.getByTestId('mint-key-scope-type-select'), { target: { value: 'personal_user:project' } });
    const datalist = screen.getByTestId('mint-project-input');
    expect(datalist).toBeDefined();

    // 3. Leave project input empty so newKeyProject.trim() is false and falls back to effectiveProjectKey
    fireEvent.change(screen.getByTestId('mint-project-input'), { target: { value: '' } });
    fireEvent.change(screen.getByTestId('mint-label-input'), { target: { value: 'Empty Proj Key' } });

    const form = screen.getByTestId('mint-label-input').closest('form');
    expect(form).not.toBeNull();
    if (form) {
      fireEvent.submit(form);
    }

    await waitFor(() => {
      expect(screen.getByTestId('mcp-snippet-modal')).toBeDefined();
    });
    fireEvent.click(screen.getByTestId('modal-close-button'));

    // 4. Open again and submit with non-empty projectKey so newKeyProject.trim() is true
    fireEvent.click(screen.getByTestId('mint-key-button'));
    fireEvent.change(screen.getByTestId('mint-key-scope-type-select'), { target: { value: 'personal_user:project' } });
    fireEvent.change(screen.getByTestId('mint-project-input'), { target: { value: 'PROJ-SNIP' } });
    fireEvent.change(screen.getByTestId('mint-label-input'), { target: { value: 'Snippet Proj Key' } });

    const form2 = screen.getByTestId('mint-label-input').closest('form');
    expect(form2).not.toBeNull();
    if (form2) {
      fireEvent.submit(form2);
    }

    await waitFor(() => {
      expect(screen.getByTestId('mcp-snippet-modal')).toBeDefined();
    });
    expect(mintSpy).toHaveBeenCalledWith(
      expect.objectContaining({
        label: 'Snippet Proj Key',
        scope_tier: 'project',
        allowed_projects: ['PROJ-SNIP'],
      }),
    );
  });

  describe('settingsApi standalone helpers', () => {
    beforeEach(() => {
      vi.restoreAllMocks();
    });

    it('exercises fetchUnifiedMcpKeys with all options and both response shapes', async () => {
      const apiFetchSpy = vi.spyOn(clientModule, 'apiFetch').mockResolvedValue({
        keys: [
          {
            id: 'k-1',
            label: 'Key 1',
            surface: 'agent',
            capability_mask: 7,
            allowed_cidrs: ['10.0.0.0/8'],
          },
        ],
      });

      const res1 = await settingsApi.fetchUnifiedMcpKeys({
        view: 'governance',
        scope_tier: 'workspace',
        project_ref: 'KANBA',
        surface: 'agent',
      });
      expect(res1[0]?.id).toBe('k-1');
      expect(res1[0]?.capability_mask).toBe(7);
      expect(res1[0]?.allowed_cidrs).toEqual(['10.0.0.0/8']);
      expect(apiFetchSpy).toHaveBeenCalledWith(
        'GET',
        '/api/v1/mcp-keys?view=governance&scope_tier=workspace&project_ref=KANBA&surface=agent',
      );

      // Array shape
      apiFetchSpy.mockResolvedValueOnce([
        { id: 'k-2', surface: 'docs', display_hint: 'd2' },
      ]);
      const res2 = await settingsApi.fetchUnifiedMcpKeys();
      expect(res2[0]?.id).toBe('k-2');
      expect(res2[0]?.label).toBe('d2');
    });

    it('exercises mintUnifiedMcpKey and revokeUnifiedMcpKey', async () => {
      const apiFetchSpy = vi.spyOn(clientModule, 'apiFetch').mockResolvedValue({
        id: 'k-mint',
        surface: 'agent',
      });

      const res = await settingsApi.mintUnifiedMcpKey({
        label: 'New Minter',
        surface: 'agent',
        scopes: ['agent:read'],
        capability_mask: 1,
        allowed_cidrs: ['192.168.1.0/24'],
      });
      expect(res.id).toBe('k-mint');
      expect(res.label).toBe('New Minter');
      expect(apiFetchSpy).toHaveBeenCalledWith('POST', '/api/v1/mcp-keys', {
        body: JSON.stringify({
          label: 'New Minter',
          surface: 'agent',
          scopes: ['agent:read'],
          capability_mask: 1,
          allowed_cidrs: ['192.168.1.0/24'],
        }),
        headers: { 'Content-Type': 'application/json' },
      });

      apiFetchSpy.mockResolvedValueOnce(undefined);
      await settingsApi.revokeUnifiedMcpKey('k-mint');
      expect(apiFetchSpy).toHaveBeenCalledWith('DELETE', '/api/v1/mcp-keys/{key_id}', {
        params: { key_id: 'k-mint' },
      });
    });

    it('exercises personal MCP key operations with global and standard tier', async () => {
      const apiFetchSpy = vi.spyOn(clientModule, 'apiFetch').mockResolvedValue([
        { id: 'k-p1', surface: 'agent' },
      ]);

      const resStandard = await settingsApi.fetchPersonalMcpKeys();
      expect(resStandard[0]?.id).toBe('k-p1');
      expect(apiFetchSpy).toHaveBeenCalledWith('GET', '/api/v1/auth/mcp-keys');

      apiFetchSpy.mockResolvedValueOnce({
        keys: [{ id: 'k-pg', surface: 'admin' }],
      });
      const resGlobal = await settingsApi.fetchPersonalMcpKeys('global');
      expect(resGlobal[0]?.id).toBe('k-pg');
      expect(apiFetchSpy).toHaveBeenCalledWith('GET', '/api/v1/admin/mcp-keys');

      apiFetchSpy.mockResolvedValueOnce({ id: 'k-p-mint', surface: 'agent' });
      await settingsApi.mintPersonalMcpKey(
        { label: 'Personal', surface: 'agent', scopes: ['agent:read'] },
        'global',
      );
      expect(apiFetchSpy).toHaveBeenCalledWith('POST', '/api/v1/admin/mcp-keys', {
        body: JSON.stringify({ label: 'Personal', surface: 'agent', scopes: ['agent:read'] }),
        headers: { 'Content-Type': 'application/json' },
      });

      apiFetchSpy.mockResolvedValueOnce({ id: 'k-p-mint2', surface: 'agent' });
      await settingsApi.mintPersonalMcpKey({
        label: 'Personal2',
        surface: 'agent',
        scopes: ['agent:read'],
      });
      expect(apiFetchSpy).toHaveBeenCalledWith('POST', '/api/v1/auth/mcp-keys', {
        body: JSON.stringify({ label: 'Personal2', surface: 'agent', scopes: ['agent:read'] }),
        headers: { 'Content-Type': 'application/json' },
      });

      apiFetchSpy.mockResolvedValueOnce(undefined);
      await settingsApi.revokePersonalMcpKey('k-pg', 'global');
      expect(apiFetchSpy).toHaveBeenCalledWith('DELETE', '/api/v1/admin/mcp-keys/{key_id}', {
        params: { key_id: 'k-pg' },
      });

      apiFetchSpy.mockResolvedValueOnce(undefined);
      await settingsApi.revokePersonalMcpKey('k-p1');
      expect(apiFetchSpy).toHaveBeenCalledWith('DELETE', '/api/v1/auth/mcp-keys/{key_id}', {
        params: { key_id: 'k-p1' },
      });
    });

    it('exercises fetchConnectedApps and revokeConnectedApp', async () => {
      const apiFetchSpy = vi.spyOn(clientModule, 'apiFetch').mockResolvedValue([
        { id: 'app-1', client_id: 'cid', surface: 'agent', scopes: ['agent:read'], created_at: '', revoked_at: null },
      ]);

      const apps = await settingsApi.fetchConnectedApps();
      expect(apps[0]?.id).toBe('app-1');
      expect(apiFetchSpy).toHaveBeenCalledWith('GET', '/api/v1/auth/oauth-grants');

      apiFetchSpy.mockResolvedValueOnce(undefined);
      await settingsApi.revokeConnectedApp('app-1');
      expect(apiFetchSpy).toHaveBeenCalledWith('DELETE', '/api/v1/auth/oauth-grants/{grant_id}', {
        params: { grant_id: 'app-1' },
      });
    });

    it('Case 1: McpAccessStudio selects capability presets cleanly and reveals raw bitmask/CIDR controls when AdvancedSection is expanded', async () => {
      vi.spyOn(settingsApi, 'fetchUnifiedMcpKeys').mockResolvedValue([]);
      vi.spyOn(settingsApi, 'fetchConnectedApps').mockResolvedValue([]);

      render(
        <MemoryRouter initialEntries={['/settings/mcp']}>
          <McpAccessStudio tier="workspace" />
        </MemoryRouter>,
      );

      await waitFor(() => {
        expect(screen.getByTestId('mint-key-button')).not.toBeNull();
      });

      fireEvent.click(screen.getByTestId('mint-key-button'));
      expect(screen.getByTestId('mint-label-input')).not.toBeNull();

      // Capability preset select exists and defaults to Standard Developer Agent (31)
      const presetSelect = screen.getByTestId<HTMLSelectElement>('capability-preset-select');
      expect(presetSelect).toBeDefined();
      expect(presetSelect.value).toBe('31');

      // Switch preset to Read-Only Agent (1)
      fireEvent.change(presetSelect, { target: { value: '1' } });
      expect(presetSelect.value).toBe('1');

      // Switch preset to Full Project Agent (255)
      fireEvent.change(presetSelect, { target: { value: '255' } });
      expect(presetSelect.value).toBe('255');

      // Advanced section is collapsed by default
      const advSection = screen.getByTestId('advanced-capability-restrictions');
      expect(advSection).toBeDefined();
      expect(advSection.hasAttribute('open')).toBe(false);

      // Expand AdvancedSection
      const toggle = screen.getByTestId('advanced-capability-restrictions-toggle');
      fireEvent.click(toggle);

      expect(advSection.hasAttribute('open')).toBe(true);

      // Raw bitmask matrix and CIDR input are revealed
      expect(screen.getByTestId('capability-bits-grid')).toBeDefined();
      expect(screen.getByTestId('mint-allowed-cidrs-input')).toBeDefined();
      expect(screen.getByTestId('tools-selection-grid')).toBeDefined();
    });
  });

  describe('Simplified Mint Modal 4-Question Form (KAN-390)', () => {
    beforeEach(() => {
      vi.restoreAllMocks();
      vi.spyOn(settingsApi, 'fetchUnifiedMcpKeys').mockResolvedValue(mockKeys);
      vi.spyOn(settingsApi, 'fetchConnectedApps').mockResolvedValue(mockApps);
      vi.spyOn(clientModule, 'apiFetch').mockImplementation((_method: string, path: string) => {
        if (path === '/api/v1/projects') {
          return Promise.resolve({
            items: [
              { id: 'proj-1', identifier: 'KAN', name: 'Kanban Core' },
              { id: 'proj-2', identifier: 'OPS', name: 'Operations' },
            ],
          });
        }
        return Promise.resolve({
          is_server_admin: true,
          is_workspace_admin: true,
        });
      });
    });

    it('structures modal around the 4 plain-English questions and live summary', async () => {
      render(
        <MemoryRouter initialEntries={['/settings/mcp']}>
          <McpAccessStudio tier="workspace" />
        </MemoryRouter>,
      );

      await waitFor(() => {
        expect(screen.getByTestId('mint-key-button')).not.toBeNull();
      });

      fireEvent.click(screen.getByTestId('mint-key-button'));

      // Question 1
      expect(screen.getByText(/What is the key name\?/i)).toBeDefined();
      expect(screen.getByTestId('mint-label-input')).toBeDefined();

      // Question 2
      expect(screen.getByText(/Who is this key for & what can it access\?/i)).toBeDefined();
      expect(screen.getByTestId('mint-key-scope-type-select')).toBeDefined();

      // Old separate selectors must NOT exist
      expect(screen.queryByTestId('mint-owner-kind-select')).toBeNull();
      expect(screen.queryByTestId('mint-scope-select')).toBeNull();

      // Question 3
      expect(screen.getByText(/What can it do\?/i)).toBeDefined();
      expect(screen.getByTestId('mint-surface-select')).toBeDefined();
      expect(screen.getByTestId('mint-expiry-select')).toBeDefined();

      // AdvancedSection collapsed by default
      const advSection = screen.getByTestId('advanced-capability-restrictions');
      expect(advSection.hasAttribute('open')).toBe(false);

      // Question 4: Live Plain-Language Key Summary
      expect(screen.getByText(/Key Summary/i)).toBeDefined();
      const liveSummary = screen.getByTestId('mint-key-summary');
      expect(liveSummary).toBeDefined();
      expect(liveSummary.textContent).toBe(
        'Key "Untitled" for Personal User can access This Workspace and use Agent tools (Standard Developer Agent).',
      );
    });

    it('reveals Allowed Project picker and updates live summary when selecting single project for personal user and service bot', async () => {
      const mintSpy = vi.spyOn(settingsApi, 'mintUnifiedMcpKey').mockResolvedValue({
        id: 'new-proj-key',
        label: 'My Project Key',
        display_hint: 'm1p1',
        surface: 'agent',
        scope_tier: 'project',
        scopes: ['agent:read', 'agent:write'],
        allowed_projects: ['OPS'],
        created_at: new Date().toISOString(),
        expires_at: new Date().toISOString(),
        last_used_at: null,
        revoked_at: null,
        raw_key: 'kb_mcp_raw_test_project',
      });

      render(
        <MemoryRouter initialEntries={['/settings/mcp']}>
          <McpAccessStudio />
        </MemoryRouter>,
      );

      await waitFor(() => {
        expect(screen.getByTestId('mint-key-button')).not.toBeNull();
      });

      fireEvent.click(screen.getByTestId('mint-key-button'));

      const keyScopeSelect = screen.getByTestId<HTMLSelectElement>('mint-key-scope-type-select');
      const labelInput = screen.getByTestId('mint-label-input');

      // Initially workspace: no project input
      expect(screen.queryByTestId('mint-project-input')).toBeNull();

      // 1. Select Personal - Single Project
      fireEvent.change(keyScopeSelect, { target: { value: 'personal_user:project' } });
      expect(screen.getByTestId('mint-project-input')).toBeDefined();

      // Type label
      fireEvent.change(labelInput, { target: { value: 'My Project Key' } });
      const projInput = screen.getByTestId('mint-project-input');
      fireEvent.change(projInput, { target: { value: 'OPS' } });

      // Check live summary
      expect(screen.getByTestId('mint-key-summary').textContent).toBe(
        'Key "My Project Key" for Personal User can access Project OPS and use Agent tools (Standard Developer Agent).',
      );

      // 2. Select Service Bot - Single Project
      fireEvent.change(keyScopeSelect, { target: { value: 'service_bot:project' } });
      expect(screen.getByTestId('mint-key-summary').textContent).toBe(
        'Key "My Project Key" for Service Bot can access Project OPS and use Agent tools (Standard Developer Agent).',
      );

      // Submit and verify exact payload
      fireEvent.click(screen.getByTestId('mint-submit-btn'));

      await waitFor(() => {
        expect(mintSpy).toHaveBeenCalledWith(
          expect.objectContaining({
            label: 'My Project Key',
            owner_kind: 'service_bot',
            scope_tier: 'project',
            project_ref: 'OPS',
            allowed_projects: ['OPS'],
            capability_mask: 31,
          }),
        );
      });
    });

    it('expands Advanced Capability & Network Restrictions revealing capability-preset-select, updating overrides and summary', async () => {
      render(
        <MemoryRouter initialEntries={['/settings/mcp']}>
          <McpAccessStudio />
        </MemoryRouter>,
      );

      await waitFor(() => {
        expect(screen.getByTestId('mint-key-button')).not.toBeNull();
      });

      fireEvent.click(screen.getByTestId('mint-key-button'));

      const advSection = screen.getByTestId('advanced-capability-restrictions');
      const toggle = screen.getByTestId('advanced-capability-restrictions-toggle');

      // Initially collapsed
      expect(advSection.hasAttribute('open')).toBe(false);
      // activeOverridesCount starts at 0 with default capabilityMask=31
      expect(advSection.textContent).not.toContain('custom setting active');

      // Expand
      fireEvent.click(toggle);
      expect(advSection.hasAttribute('open')).toBe(true);

      const presetSelect = screen.getByTestId<HTMLSelectElement>('capability-preset-select');
      expect(presetSelect).toBeDefined();
      expect(presetSelect.value).toBe('31');

      // Change preset to Read-Only Agent (1)
      fireEvent.change(presetSelect, { target: { value: '1' } });
      expect(presetSelect.value).toBe('1');

      // Override count should reflect non-default mask (1 custom setting active)
      expect(advSection.textContent).toContain('1 custom setting active');

      // Summary updates with Read-Only Agent
      expect(screen.getByTestId('mint-key-summary').textContent).toContain(
        '(Read-Only Agent)',
      );

      // Change preset to Full Project Agent (255)
      fireEvent.change(presetSelect, { target: { value: '255' } });
      expect(screen.getByTestId('mint-key-summary').textContent).toContain(
        '(Full Project Agent)',
      );

      // Change preset back to Standard Developer Agent (31)
      fireEvent.change(presetSelect, { target: { value: '31' } });
      expect(advSection.textContent).not.toContain('custom setting active');
      expect(screen.getByTestId('mint-key-summary').textContent).toContain(
        '(Standard Developer Agent)',
      );
    });

    it('non-server-admin user never sees Service Bot - Server / Global in unified selector', async () => {
      render(
        <MemoryRouter initialEntries={['/settings/mcp']}>
          <McpAccessStudio
            user={{
              is_server_admin: false,
              is_workspace_admin: true,
              is_project_admin: true,
              workspace_role: 'WORKSPACE_ADMIN',
            }}
          />
        </MemoryRouter>,
      );

      await waitFor(() => {
        expect(screen.getByTestId('mint-key-button')).not.toBeNull();
      });

      fireEvent.click(screen.getByTestId('mint-key-button'));

      const keyScopeSelect = screen.getByTestId<HTMLSelectElement>('mint-key-scope-type-select');
      const options = Array.from(keyScopeSelect.querySelectorAll('option')).map(
        (o) => o.value,
      );

      expect(options).toContain('personal_user:project');
      expect(options).toContain('personal_user:workspace');
      expect(options).toContain('service_bot:project');
      expect(options).toContain('service_bot:workspace');
      expect(options).not.toContain('service_bot:global');
      expect(screen.queryByText(/Service Bot - Server \/ Global/i)).toBeNull();
    });

    it('submitting while Advanced is collapsed sends default capability_mask cleanly', async () => {
      const mintSpy = vi.spyOn(settingsApi, 'mintUnifiedMcpKey').mockResolvedValue({
        id: 'new-def-key',
        label: 'Default Mask Key',
        display_hint: 'd1m1',
        surface: 'agent',
        scope_tier: 'workspace',
        scopes: ['agent:read', 'agent:write'],
        allowed_projects: null,
        created_at: new Date().toISOString(),
        expires_at: new Date().toISOString(),
        last_used_at: null,
        revoked_at: null,
        raw_key: 'kb_mcp_raw_test_default',
      });

      render(
        <MemoryRouter initialEntries={['/settings/mcp']}>
          <McpAccessStudio />
        </MemoryRouter>,
      );

      await waitFor(() => {
        expect(screen.getByTestId('mint-key-button')).not.toBeNull();
      });

      fireEvent.click(screen.getByTestId('mint-key-button'));

      const advSection = screen.getByTestId('advanced-capability-restrictions');
      expect(advSection.hasAttribute('open')).toBe(false);

      fireEvent.change(screen.getByTestId('mint-label-input'), {
        target: { value: 'Default Mask Key' },
      });

      fireEvent.click(screen.getByTestId('mint-submit-btn'));

      await waitFor(() => {
        expect(mintSpy).toHaveBeenCalledWith(
          expect.objectContaining({
            label: 'Default Mask Key',
            capability_mask: 31,
          }),
        );
      });
    });

    it('exercises getCapabilityPresetName and formatMintKeySummary helper functions directly', () => {
      expect(getCapabilityPresetName(1)).toBe('Read-Only Agent');
      expect(getCapabilityPresetName(3)).toBe('View + Comment');
      expect(getCapabilityPresetName(31)).toBe('Standard Developer Agent');
      expect(getCapabilityPresetName(255)).toBe('Full Project Agent');
      expect(getCapabilityPresetName(42)).toBe('Custom (42)');

      // formatMintKeySummary with fallback Untitled and workspace
      expect(
        formatMintKeySummary({
          label: '',
          ownerKind: 'personal_user',
          scopeTier: 'workspace',
          surface: 'agent',
          capabilityMask: 31,
        }),
      ).toBe(
        'Key "Untitled" for Personal User can access This Workspace and use Agent tools (Standard Developer Agent).',
      );

      // formatMintKeySummary with global scope, service_bot, admin surface
      expect(
        formatMintKeySummary({
          label: 'Infra Orchestrator',
          ownerKind: 'service_bot',
          scopeTier: 'global',
          surface: 'admin',
          capabilityMask: 255,
        }),
      ).toBe(
        'Key "Infra Orchestrator" for Service Bot can access Entire Server and use Admin tools (Full Project Agent).',
      );

      // formatMintKeySummary with project scope, docs surface, custom mask
      expect(
        formatMintKeySummary({
          label: 'Docs Bot',
          ownerKind: 'service_bot',
          scopeTier: 'project',
          project: 'DOCS',
          surface: 'docs',
          capabilityMask: 3,
        }),
      ).toBe(
        'Key "Docs Bot" for Service Bot can access Project DOCS and use Docs tools (View + Comment).',
      );

      // formatMintKeySummary with project scope but no project specified
      expect(
        formatMintKeySummary({
          label: 'No Project Bot',
          ownerKind: 'personal_user',
          scopeTier: 'project',
          project: '',
          surface: 'agent',
          capabilityMask: 1,
        }),
      ).toBe(
        'Key "No Project Bot" for Personal User can access Project (None) and use Agent tools (Read-Only Agent).',
      );
    });

    it('supports segmented role and scope selectors and workspace policy TTL clamping (KAN-417)', async () => {
      vi.spyOn(settingsApi, 'fetchUnifiedMcpKeys').mockResolvedValue([]);
      vi.spyOn(settingsApi, 'fetchConnectedApps').mockResolvedValue([]);

      render(
        <MemoryRouter initialEntries={['/settings/mcp']}>
          <McpAccessStudio
            tier="workspace"
            maxKeyTtlDays={90}
            user={{ is_server_admin: true, is_workspace_admin: true }}
          />
        </MemoryRouter>,
      );

      await waitFor(() => {
        expect(screen.getByTestId('mint-key-button')).not.toBeNull();
      });

      fireEvent.click(screen.getByTestId('mint-key-button'));

      // Check segmented role pills
      const personalPill = screen.getByTestId('role-pill-personal');
      const serviceBotPill = screen.getByTestId('role-pill-service_bot');
      expect(personalPill).toBeDefined();
      expect(serviceBotPill).toBeDefined();

      // Check segmented scope pills
      const projectPill = screen.getByTestId('scope-tier-pill-project');
      const workspacePill = screen.getByTestId('scope-tier-pill-workspace');
      const globalPill = screen.getByTestId('scope-tier-pill-global');
      expect(projectPill).toBeDefined();
      expect(workspacePill).toBeDefined();
      expect(globalPill).toBeDefined();

      // Click service bot pill and project pill
      fireEvent.click(serviceBotPill);
      fireEvent.click(projectPill);

      const select = screen.getByTestId<HTMLSelectElement>('mint-key-scope-type-select');
      expect(select.value).toBe('service_bot:project');

      // Click global pill
      fireEvent.click(globalPill);
      expect(select.value).toBe('service_bot:global');

      // Click personal pill while in global scope to verify auto-reset to workspace
      fireEvent.click(personalPill);
      expect(select.value).toBe('personal_user:workspace');

      // Click workspace pill
      fireEvent.click(workspacePill);
      expect(select.value).toBe('personal_user:workspace');

      // Check policy TTL badge
      expect(screen.getByTestId('policy-ttl-badge').textContent).toContain('Workspace policy enforces maximum 90-day TTL');

      // Verify unlimited option is not present due to TTL policy
      expect(screen.queryByTestId('option-unlimited')).toBeNull();
    });

    it('permits minting a key with capability_mask 0 without disabling submit button (KAN-417)', async () => {
      render(
        <MemoryRouter initialEntries={['/settings/mcp']}>
          <McpAccessStudio user={{ is_server_admin: true, is_workspace_admin: true }} allowUnlimitedKeys={true} />
        </MemoryRouter>,
      );

      await waitFor(() => {
        expect(screen.getByTestId('mint-key-button')).not.toBeNull();
      });

      fireEvent.click(screen.getByTestId('mint-key-button'));

      fireEvent.change(screen.getByTestId('mint-label-input'), {
        target: { value: 'Zero Mask Key' },
      });
      // Expand advanced section
      fireEvent.click(screen.getByTestId('advanced-capability-restrictions-toggle'));

      // Uncheck default capability bits (1, 2, 4, 8, 16) so mask becomes 0
      for (const bit of [1, 2, 4, 8, 16]) {
        const cb = screen.getByTestId<HTMLInputElement>(`cap-bit-${String(bit)}`);
        if (cb.checked) {
          fireEvent.click(cb);
        }
      }

      // Submit button should NOT be disabled for mask 0
      const submitBtn = screen.getByTestId<HTMLButtonElement>('mint-submit-btn');
      expect(submitBtn.disabled).toBe(false);
    });

    it('copies agent skills prompt on llms callout button click', async () => {
      vi.spyOn(settingsApi, 'fetchUnifiedMcpKeys').mockResolvedValue([]);
      vi.spyOn(settingsApi, 'fetchConnectedApps').mockResolvedValue([]);

      render(
        <MemoryRouter initialEntries={['/settings/mcp']}>
          <McpAccessStudio tier="personal" />
        </MemoryRouter>,
      );

      await waitFor(() => {
        expect(screen.getByTestId('mcp-copy-llms-prompt-btn')).not.toBeNull();
      });

      fireEvent.click(screen.getByTestId('mcp-copy-llms-prompt-btn'));
    });

    it('handles AAL2 cancellation during connected app revocation', async () => {
      const app = {
        id: 'grant-aal2-cancel',
        client_id: 'client_123',
        client_name: 'Cancel App',
        client_type: 'public' as const,
        scopes: ['agent:read'],
        surface: 'agent' as const,
        allowed_projects: null,
        created_at: new Date().toISOString(),
        last_used_at: null,
        revoked_at: null,
      };
      vi.spyOn(settingsApi, 'fetchUnifiedMcpKeys').mockResolvedValue([]);
      vi.spyOn(settingsApi, 'fetchConnectedApps').mockResolvedValue([app]);
      vi.spyOn(settingsApi, 'revokeConnectedApp').mockRejectedValue(new clientModule.Aal2StepUpCancelledError());

      render(
        <MemoryRouter initialEntries={['/settings/mcp']}>
          <McpAccessStudio tier="personal" />
        </MemoryRouter>,
      );

      await waitFor(() => {
        expect(screen.getByTestId('disconnect-btn-grant-aal2-cancel')).not.toBeNull();
      });

      fireEvent.click(screen.getByTestId('disconnect-btn-grant-aal2-cancel'));

      await waitFor(() => {
        expect(screen.getByTestId('confirm-disconnect-btn')).not.toBeNull();
      });

      fireEvent.click(screen.getByTestId('confirm-disconnect-btn'));

      await waitFor(() => {
        expect(screen.queryByTestId('confirm-disconnect-btn')).toBeNull();
      });
    });
  });

  describe('KAN-517: CTA Button Contrast and Subnav Contrast (WCAG AA >= 4.5:1)', () => {
    it('renders + Mint MCP Key with .kb-mcp-studio-mint-btn and preserves click behavior', async () => {
      vi.spyOn(settingsApi, 'fetchUnifiedMcpKeys').mockResolvedValue([]);
      vi.spyOn(settingsApi, 'fetchConnectedApps').mockResolvedValue([]);

      render(
        <MemoryRouter initialEntries={['/settings/mcp']}>
          <McpAccessStudio tier="personal" />
        </MemoryRouter>,
      );

      await waitFor(() => {
        expect(screen.getByTestId('mint-key-button')).not.toBeNull();
      });

      const mintBtn = screen.getByTestId('mint-key-button');
      expect(mintBtn.classList.contains('kb-mcp-studio-mint-btn')).toBe(true);
      expect(mintBtn.textContent).toContain('+ Mint MCP Key');

      // Click behavior opens mint modal
      fireEvent.click(mintBtn);
      await waitFor(() => {
        expect(screen.getByTestId('mint-label-input')).not.toBeNull();
      });
    });

    it('renders + Add Workload Policy with .kb-mcp-studio-mint-btn and preserves click behavior', async () => {
      const { WorkloadFederationSection } = await vi.importActual<typeof import('../McpUnifiedStudio')>(
        '../McpUnifiedStudio',
      );

      vi.spyOn(clientModule, 'apiFetch').mockResolvedValue([]);

      render(<WorkloadFederationSection isAdmin={true} />);

      await waitFor(() => {
        expect(screen.getByTestId('add-workload-policy-btn')).not.toBeNull();
      });

      const addPolicyBtn = screen.getByTestId('add-workload-policy-btn');
      expect(addPolicyBtn.classList.contains('kb-mcp-studio-mint-btn')).toBe(true);
      expect(addPolicyBtn.textContent).toContain('+ Add Workload Policy');

      // Click behavior opens workload policy modal
      fireEvent.click(addPolicyBtn);
      await waitFor(() => {
        expect(screen.getByTestId('workload-policy-modal')).not.toBeNull();
      });
    });

    it('verifies McpAccessStudio.css defines >= 4.5:1 WCAG AA contrast colors and zero low-contrast fills', () => {
      const cssPath = path.resolve(__dirname, '../McpAccessStudio.css');
      expect(fs.existsSync(cssPath)).toBe(true);
      const cssContent = fs.readFileSync(cssPath, 'utf8');

      // 1. Verify .kb-mcp-studio-mint-btn uses emerald #047857 and hover #065f46
      expect(cssContent).toMatch(/\.kb-mcp-studio-mint-btn\s*\{[^}]*background-color:\s*#047857;/);
      expect(cssContent).toMatch(/\.kb-mcp-studio-mint-btn:hover:not\(:disabled\)\s*\{[^}]*background-color:\s*#065f46;/);

      // 2. Verify .kb-mcp-connect-btn uses emerald #047857 and hover #065f46
      expect(cssContent).toMatch(/\.kb-mcp-connect-btn\s*\{[^}]*background-color:\s*#047857;/);
      expect(cssContent).toMatch(/\.kb-mcp-connect-btn:hover:not\(:disabled\)\s*\{[^}]*background-color:\s*#065f46;/);

      // 3. Verify .kb-mcp-admin-subnav-active uses high-contrast --badge-fg
      expect(cssContent).toMatch(/\.kb-mcp-admin-subnav-active\s*\{[^}]*color:\s*var\(--badge-fg\)\s*!important;/);
      expect(cssContent).toMatch(/\.kb-mcp-admin-subnav-active\s*\{[^}]*border-bottom-color:\s*var\(--badge-fg\)\s*!important;/);

      // 4. Verify zero occurrences of #10b981 or #2ea043 low-contrast fills
      expect(cssContent).not.toContain('#10b981');
      expect(cssContent).not.toContain('#2ea043');

      // 5. Calculate and verify WCAG AA contrast ratio >= 4.5:1 for white text on button fills
      function getLuminance(r: number, g: number, b: number): number {
        const toLinear = (c: number): number => {
          const s = c / 255;
          return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
        };
        return 0.2126 * toLinear(r) + 0.7152 * toLinear(g) + 0.0722 * toLinear(b);
      }

      function getContrastRatio(rgb1: [number, number, number], rgb2: [number, number, number]): number {
        const l1 = getLuminance(...rgb1);
        const l2 = getLuminance(...rgb2);
        const lighter = Math.max(l1, l2);
        const darker = Math.min(l1, l2);
        return (lighter + 0.05) / (darker + 0.05);
      }

      const white: [number, number, number] = [255, 255, 255];
      const emeraldBase: [number, number, number] = [4, 120, 87]; // #047857
      const emeraldHover: [number, number, number] = [6, 95, 70]; // #065f46

      const baseContrast = getContrastRatio(white, emeraldBase);
      const hoverContrast = getContrastRatio(white, emeraldHover);

      // Both must exceed 4.5:1 (WCAG AA minimum for normal text)
      expect(baseContrast).toBeGreaterThanOrEqual(4.5);
      expect(hoverContrast).toBeGreaterThanOrEqual(4.5);
      expect(baseContrast).toBeGreaterThan(5.4);
      expect(hoverContrast).toBeGreaterThan(7.0);

      // Verify subnav active --badge-fg contrast in light (#2563eb on #ffffff) and dark (#93c5fd on #0d1117)
      const lightBg: [number, number, number] = [255, 255, 255];
      const lightBadgeFg: [number, number, number] = [37, 99, 235]; // #2563eb
      const darkBg: [number, number, number] = [13, 17, 23]; // #0d1117
      const darkBadgeFg: [number, number, number] = [147, 197, 253]; // #93c5fd

      const lightSubnavContrast = getContrastRatio(lightBadgeFg, lightBg);
      const darkSubnavContrast = getContrastRatio(darkBadgeFg, darkBg);

      expect(lightSubnavContrast).toBeGreaterThanOrEqual(4.5);
      expect(darkSubnavContrast).toBeGreaterThanOrEqual(4.5);
    });
  });

  describe('Copy Agent Skill Prompt Contrast & Responsive Callout (KAN-521)', () => {
    beforeEach(() => {
      vi.restoreAllMocks();
      vi.spyOn(settingsApi, 'fetchUnifiedMcpKeys').mockResolvedValue(mockKeys);
      vi.spyOn(settingsApi, 'fetchPersonalMcpKeys').mockResolvedValue(mockKeys);
      vi.spyOn(settingsApi, 'fetchConnectedApps').mockResolvedValue(mockApps);
      vi.spyOn(clientModule, 'apiFetch').mockImplementation((_method: string, path: string) => {
        if (path === '/api/v1/projects') {
          return Promise.resolve({
            items: [{ id: 'proj-kanba', identifier: 'KANBA', name: 'Kanban Core' }],
          });
        }
        return Promise.resolve({
          is_server_admin: true,
          is_workspace_admin: true,
        });
      });
    });

    it('renders Copy Agent Skill Prompt button with .kb-mcp-copy-prompt-btn and copies cleanly in Light theme', async () => {
      document.documentElement.setAttribute('data-theme', 'light');
      try {
        render(
          <MemoryRouter initialEntries={['/settings/mcp']}>
            <McpAccessStudio tier="personal" />
          </MemoryRouter>,
        );

        await waitFor(() => {
          expect(screen.getByTestId('mcp-copy-llms-prompt-btn')).not.toBeNull();
        });

        const copyBtn = screen.getByTestId('mcp-copy-llms-prompt-btn');
        expect(copyBtn.classList.contains('kb-mcp-copy-prompt-btn')).toBe(true);
        expect(copyBtn.textContent).toContain('Copy Agent Skill Prompt');

        fireEvent.click(copyBtn);
      } finally {
        document.documentElement.removeAttribute('data-theme');
      }
    });

    it('renders and copies cleanly in Dark theme', async () => {
      document.documentElement.setAttribute('data-theme', 'dark');
      try {
        render(
          <MemoryRouter initialEntries={['/settings/mcp']}>
            <McpAccessStudio tier="personal" />
          </MemoryRouter>,
        );

        await waitFor(() => {
          expect(screen.getByTestId('mcp-copy-llms-prompt-btn')).not.toBeNull();
        });

        const copyBtn = screen.getByTestId('mcp-copy-llms-prompt-btn');
        expect(copyBtn.classList.contains('kb-mcp-copy-prompt-btn')).toBe(true);
        expect(copyBtn.textContent).toContain('Copy Agent Skill Prompt');

        fireEvent.click(copyBtn);
      } finally {
        document.documentElement.removeAttribute('data-theme');
      }
    });

    it('asserts McpAccessStudio.css enforces WCAG AA tokens on .kb-mcp-copy-prompt-btn and responsive callout', () => {
      const cssPath = path.resolve(__dirname, '../McpAccessStudio.css');
      expect(fs.existsSync(cssPath)).toBe(true);
      const css = fs.readFileSync(cssPath, 'utf8');

      // .kb-mcp-copy-prompt-btn binds var(--badge-fg) and var(--bg-surface-raised)
      expect(css).toMatch(/\.kb-mcp-copy-prompt-btn\s*\{[^}]*color:\s*var\(--badge-fg/);
      expect(css).toMatch(/\.kb-mcp-copy-prompt-btn\s*\{[^}]*background:\s*var\(--bg-surface-raised/);
      expect(css).toMatch(/\.kb-mcp-copy-prompt-btn\s*\{[^}]*border:\s*1px solid var\(--border-subtle/);

      // Hover uses var(--bg-hover) and var(--badge-fg)
      expect(css).toMatch(/\.kb-mcp-copy-prompt-btn:hover:not\(:disabled\)\s*\{[^}]*background:\s*var\(--bg-hover/);
      expect(css).toMatch(/\.kb-mcp-copy-prompt-btn:hover:not\(:disabled\)\s*\{[^}]*color:\s*var\(--badge-fg/);

      // Focus ring
      expect(css).toMatch(/\.kb-mcp-copy-prompt-btn:focus-visible\s*\{[^}]*outline:\s*2px solid var\(--focus-ring/);

      // Mobile callout wrapping at 640px
      expect(css).toMatch(/@media\s*\(max-width:\s*640px\)\s*\{[^}]*\.kb-mcp-llms-callout\s*\{[^}]*flex-direction:\s*column;/);

      // No forbidden unicode dashes
      expect(css).not.toContain('\u2014');
      expect(css).not.toContain('\u2013');
    });
  });
});
