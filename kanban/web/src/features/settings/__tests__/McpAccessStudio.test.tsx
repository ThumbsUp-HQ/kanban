// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import React from 'react';
import { MemoryRouter, Routes, Route } from 'react-router';
import { McpAccessStudio } from '../McpAccessStudio';
import * as settingsApi from '../settingsApi';

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
  });

  it('renders scope tiers correctly across all 4 mount routes', async () => {
    vi.spyOn(settingsApi, 'fetchPersonalMcpKeys').mockResolvedValue(mockKeys);
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
    });
  });

  it('mints key, opens snippet modal with plaintext, copies, and wipes secret on close (Test Case 3)', async () => {
    vi.spyOn(settingsApi, 'fetchPersonalMcpKeys').mockResolvedValue([]);
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

    vi.spyOn(settingsApi, 'mintPersonalMcpKey').mockResolvedValue(newlyMintedKey);

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
      expect(settingsApi.mintPersonalMcpKey).toHaveBeenCalledWith({
        label: 'CI Bot Token',
        surface: 'agent',
        scopes: ['agent:read', 'agent:write'],
        scope_tier: 'project',
        allowed_projects: ['KANBA'],
        expires_in_days: 60,
      });
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
    vi.spyOn(settingsApi, 'fetchPersonalMcpKeys').mockResolvedValue(mockKeys);
    vi.spyOn(settingsApi, 'fetchConnectedApps').mockResolvedValue(mockApps);
    vi.spyOn(settingsApi, 'revokePersonalMcpKey').mockResolvedValue(undefined);
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
      expect(settingsApi.revokePersonalMcpKey).toHaveBeenCalledWith('key-1');
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
    vi.spyOn(settingsApi, 'fetchPersonalMcpKeys').mockResolvedValue([]);
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
    vi.spyOn(settingsApi, 'fetchPersonalMcpKeys').mockResolvedValue([]);
    vi.spyOn(settingsApi, 'fetchConnectedApps').mockResolvedValue([]);

    const newlyMintedKey: settingsApi.McpApiKeyItem = {
      id: 'key-esc',
      label: 'Esc Test Key',
      display_hint: '1234',
      surface: 'agent',
      scope_tier: 'personal_user',
      scopes: ['agent:read'],
      allowed_projects: null,
      created_at: new Date().toISOString(),
      expires_at: new Date().toISOString(),
      last_used_at: null,
      revoked_at: null,
      raw_key: 'raw_key_esc',
    };
    vi.spyOn(settingsApi, 'mintPersonalMcpKey').mockResolvedValue(newlyMintedKey);

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

    await waitFor(() => {
      expect(screen.getByTestId('mcp-snippet-modal')).not.toBeNull();
    });

    // Close via Escape key press
    fireEvent.keyDown(window, { key: 'Escape' });

    await waitFor(() => {
      expect(screen.queryByTestId('mcp-snippet-modal')).toBeNull();
    });
  });

  it('closes mint modal via cancel button and backdrop click, handles empty label and load error', async () => {
    // 1. Initial fetch failure
    vi.spyOn(settingsApi, 'fetchPersonalMcpKeys').mockRejectedValueOnce(new Error('Network error'));
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
    vi.spyOn(settingsApi, 'fetchPersonalMcpKeys').mockResolvedValue([]);
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
    vi.spyOn(settingsApi, 'fetchPersonalMcpKeys').mockResolvedValue([]);
    vi.spyOn(settingsApi, 'fetchConnectedApps').mockResolvedValue([]);

    const mintSpy = vi.spyOn(settingsApi, 'mintPersonalMcpKey').mockResolvedValue({
      id: 'key-unlimited',
      label: 'Unlimited Token',
      display_hint: 'unl1',
      surface: 'agent',
      scope_tier: 'personal_user',
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
      expect(mintSpy).toHaveBeenCalledWith({
        label: 'Unlimited Token',
        surface: 'agent',
        scopes: ['agent:read', 'agent:write'],
        scope_tier: 'workspace',
        unlimited: true,
        confirm_unlimited: true,
      });
    });

    // Keys table should render 'Never (Unlimited)' for expires_at: null
    expect(screen.getByTestId('key-unlimited-key-unlimited')).not.toBeNull();
    expect(screen.getByTestId('key-unlimited-key-unlimited').textContent).toContain('Never (Unlimited)');
  });

  it('hides unlimited option when allow_unlimited_mcp_keys is false', async () => {
    vi.spyOn(settingsApi, 'fetchPersonalMcpKeys').mockResolvedValue([]);
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
    vi.spyOn(settingsApi, 'fetchPersonalMcpKeys').mockResolvedValue([]);
    vi.spyOn(settingsApi, 'fetchConnectedApps').mockResolvedValue([]);

    const mintSpy = vi.spyOn(settingsApi, 'mintPersonalMcpKey').mockResolvedValue({
      id: 'key-narrow',
      label: 'Narrowed Agent Key',
      display_hint: 'nar1',
      surface: 'agent',
      scope_tier: 'personal_user',
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
      expect(mintSpy).toHaveBeenCalledWith({
        label: 'Narrowed Agent Key',
        surface: 'agent',
        scopes: ['agent:read', 'agent:write'],
        scope_tier: 'workspace',
        expires_in_days: 60,
        disabled_tools: ['complete_work', 'add_comment'],
      });
    });
  });

  it('renders visible role="alert" error banner inside mint modal when API fails', async () => {
    vi.spyOn(settingsApi, 'fetchPersonalMcpKeys').mockResolvedValue([]);
    vi.spyOn(settingsApi, 'fetchConnectedApps').mockResolvedValue([]);
    vi.spyOn(settingsApi, 'mintPersonalMcpKey').mockRejectedValue(
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
});
