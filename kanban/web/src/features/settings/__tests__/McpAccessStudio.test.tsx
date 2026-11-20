// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import React from 'react';
import { MemoryRouter, Routes, Route } from 'react-router';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { McpAccessStudio } from '../McpAccessStudio';
import * as settingsApi from '../settingsApi';
import * as clientModule from '../../../api/client';

vi.mock('../../../app/useSystemStatus', () => ({
  useSystemStatus: vi.fn(() => ({
    data: { allow_unlimited_mcp_keys: true },
    isLoading: false,
    error: null,
  })),
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
        expect.objectContaining({ scope_tier: 'global', owner_kind: 'personal_user' }),
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
    const ownerSelect = screen.getByTestId('mint-owner-kind-select');
    fireEvent.change(ownerSelect, { target: { value: 'service_bot' } });

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
});
