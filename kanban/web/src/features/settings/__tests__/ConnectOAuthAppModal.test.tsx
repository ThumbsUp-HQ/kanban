// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import React from 'react';
import { MemoryRouter } from 'react-router';
import { ConnectOAuthAppModal } from '../ConnectOAuthAppModal';
import * as clipboardModule from '../../../utils/clipboard';

describe('ConnectOAuthAppModal (KAN-28)', () => {
  const writeTextMock = vi.fn().mockResolvedValue(undefined);

  beforeEach(() => {
    vi.restoreAllMocks();
    writeTextMock.mockClear();
    Object.assign(navigator, {
      clipboard: {
        writeText: writeTextMock,
      },
    });
  });

  it('renders modal with surface picker, scopes, URLs, and tabs for standard user', () => {
    const handleClose = vi.fn();
    render(
      <MemoryRouter>
        <ConnectOAuthAppModal
          user={{ is_workspace_admin: false, is_server_admin: false }}
          workspaceSlug="engineering"
          projectKey="ENG"
          onClose={handleClose}
        />
      </MemoryRouter>,
    );

    expect(screen.getByTestId('connect-oauth-app-modal')).toBeDefined();
    expect(screen.getByText('Connect OAuth Application')).toBeDefined();

    // Standard user does NOT see admin surface
    const surfaceSelect = screen.getByTestId<HTMLSelectElement>('surface-select');
    expect(surfaceSelect.value).toBe('agent');
    expect(screen.queryByText(/Admin Surface/)).toBeNull();

    // Resource and RFC 8414 URLs rendered
    expect(screen.getByTestId('mcp-resource-url').textContent).toContain('/mcp/agent/w/engineering/p/ENG');
    expect(screen.getByTestId('rfc8414-url').textContent).toContain('/.well-known/oauth-authorization-server');

    // Default tab is Claude Code
    expect(screen.getByTestId('command-snippet').textContent).toContain('claude mcp add --transport http');

    // Close button works
    fireEvent.click(screen.getByTestId('close-connect-oauth-modal-btn'));
    expect(handleClose).toHaveBeenCalledTimes(1);
  });

  it('allows admin users to select admin surface and updates available scopes', () => {
    const handleClose = vi.fn();

    // 1. is_server_admin
    const { unmount: u1 } = render(
      <MemoryRouter>
        <ConnectOAuthAppModal
          user={{ is_server_admin: true }}
          workspaceSlug="admin-ws"
          projectKey="ADM"
          onClose={handleClose}
        />
      </MemoryRouter>,
    );
    expect(screen.getByText(/Admin Surface/)).toBeDefined();
    u1();

    // 2. workspace_role SERVER_ADMIN
    const { unmount: u2 } = render(
      <MemoryRouter>
        <ConnectOAuthAppModal
          user={{ workspace_role: 'SERVER_ADMIN' }}
          onClose={handleClose}
        />
      </MemoryRouter>,
    );
    expect(screen.getByText(/Admin Surface/)).toBeDefined();
    u2();

    // 3. user is undefined
    const { unmount: u3 } = render(
      <MemoryRouter>
        <ConnectOAuthAppModal onClose={handleClose} />
      </MemoryRouter>,
    );
    expect(screen.queryByText(/Admin Surface/)).toBeNull();
    u3();

    // 4. workspace_role WORKSPACE_ADMIN
    render(
      <MemoryRouter>
        <ConnectOAuthAppModal
          user={{ workspace_role: 'WORKSPACE_ADMIN' }}
          workspaceSlug="admin-ws"
          projectKey="ADM"
          onClose={handleClose}
        />
      </MemoryRouter>,
    );

    const surfaceSelect = screen.getByTestId<HTMLSelectElement>('surface-select');
    expect(screen.getByText(/Admin Surface/)).toBeDefined();

    // Switch to docs surface
    fireEvent.change(surfaceSelect, { target: { value: 'docs' } });
    expect(screen.getByTestId('scope-check-docs:read')).toBeDefined();
    expect(screen.getByTestId('scope-check-docs:write')).toBeDefined();
    expect(screen.getByTestId('mcp-resource-url').textContent).toContain('/mcp/docs/w/admin-ws/p/ADM');

    // Switch to admin surface
    fireEvent.change(surfaceSelect, { target: { value: 'admin' } });
    expect(screen.getByTestId('scope-check-admin:read')).toBeDefined();
    expect(screen.getByTestId('scope-check-admin:write')).toBeDefined();
    expect(screen.getByTestId('scope-check-admin:destructive')).toBeDefined();
    expect(screen.getByTestId('mcp-resource-url').textContent).toContain('/mcp/admin/w/admin-ws/p/ADM');
  });

  it('supports toggling scope checkboxes', () => {
    render(
      <MemoryRouter>
        <ConnectOAuthAppModal
          user={{ is_workspace_admin: false }}
          onClose={vi.fn()}
        />
      </MemoryRouter>,
    );

    const agentWriteCheck = screen.getByTestId<HTMLInputElement>('scope-check-agent:write');
    expect(agentWriteCheck.checked).toBe(true);

    fireEvent.click(agentWriteCheck);
    expect(agentWriteCheck.checked).toBe(false);

    fireEvent.click(agentWriteCheck);
    expect(agentWriteCheck.checked).toBe(true);
  });

  it('switches client tabs and formats configuration snippets', () => {
    render(
      <MemoryRouter>
        <ConnectOAuthAppModal
          user={{ is_workspace_admin: false }}
          workspaceSlug="demo"
          projectKey="DEMO"
          onClose={vi.fn()}
        />
      </MemoryRouter>,
    );

    // Cursor / VS Code tab
    fireEvent.click(screen.getByTestId('tab-cursor'));
    expect(screen.getByTestId('command-snippet').textContent).toContain('"auth": "oauth"');

    // Antigravity tab
    fireEvent.click(screen.getByTestId('tab-antigravity'));
    expect(screen.getByTestId('command-snippet').textContent).toContain('agy mcp add kanban');

    // Codex tab
    fireEvent.click(screen.getByTestId('tab-codex'));
    expect(screen.getByTestId('command-snippet').textContent).toContain('codex mcp add kanban');

    // Claude Code tab
    fireEvent.click(screen.getByTestId('tab-claude-code'));
    expect(screen.getByTestId('command-snippet').textContent).toContain('claude mcp add --transport http');
  });

  it('copies resource URL, RFC 8414 URL, and snippet to clipboard', async () => {
    vi.useFakeTimers();
    const copySpy = vi.spyOn(clipboardModule, 'copyToClipboard').mockResolvedValue(true);
    render(
      <MemoryRouter>
        <ConnectOAuthAppModal
          user={{ is_workspace_admin: false }}
          onClose={vi.fn()}
        />
      </MemoryRouter>,
    );

    // Copy resource URL
    await act(async () => {
      fireEvent.click(screen.getByTestId('copy-resource-url-btn'));
      await vi.advanceTimersByTimeAsync(10);
    });
    expect(copySpy).toHaveBeenCalled();
    expect(screen.getByTestId('copy-resource-url-btn').textContent).toBe('Copied!');

    // Advance timer to trigger reset
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2100);
    });
    expect(screen.getByTestId('copy-resource-url-btn').textContent).toBe('Copy');

    // Copy RFC 8414 URL
    await act(async () => {
      fireEvent.click(screen.getByTestId('copy-rfc8414-url-btn'));
      await vi.advanceTimersByTimeAsync(10);
    });
    expect(copySpy).toHaveBeenCalled();
    expect(screen.getByTestId('copy-rfc8414-url-btn').textContent).toBe('Copied!');

    await act(async () => {
      await vi.advanceTimersByTimeAsync(2100);
    });
    expect(screen.getByTestId('copy-rfc8414-url-btn').textContent).toBe('Copy');

    // Copy snippet
    await act(async () => {
      fireEvent.click(screen.getByTestId('copy-snippet-btn'));
      await vi.advanceTimersByTimeAsync(10);
    });
    expect(copySpy).toHaveBeenCalled();
    expect(screen.getByTestId('copy-snippet-btn').textContent).toBe('Copied Command!');

    await act(async () => {
      await vi.advanceTimersByTimeAsync(2100);
    });
    expect(screen.getByTestId('copy-snippet-btn').textContent).toBe('Copy Command');

    // Failed copy does not trigger timer
    copySpy.mockResolvedValueOnce(false);
    await act(async () => {
      fireEvent.click(screen.getByTestId('copy-resource-url-btn'));
      await vi.advanceTimersByTimeAsync(10);
    });
    expect(screen.getByTestId('copy-resource-url-btn').textContent).toBe('Copy');

    vi.useRealTimers();
  });

  it('closes on Escape key press and backdrop click', () => {
    const handleClose = vi.fn();
    render(
      <MemoryRouter>
        <ConnectOAuthAppModal
          user={{ is_workspace_admin: false }}
          onClose={handleClose}
        />
      </MemoryRouter>,
    );

    // Backdrop click
    fireEvent.click(screen.getByTestId('connect-oauth-modal-backdrop'));
    expect(handleClose).toHaveBeenCalledTimes(1);

    // Non-Escape key press (no-op)
    fireEvent.keyDown(window, { key: 'Enter' });
    expect(handleClose).toHaveBeenCalledTimes(1);

    // Escape key press
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(handleClose).toHaveBeenCalledTimes(2);

    // Done button click
    fireEvent.click(screen.getByTestId('close-modal-bottom-btn'));
    expect(handleClose).toHaveBeenCalledTimes(3);
  });

  it('renders workspace-scoped URL cleanly when scopeTier is not project or no project selected', () => {
    // 1. scopeTier='workspace'
    const { unmount: u1 } = render(
      <MemoryRouter>
        <ConnectOAuthAppModal
          workspaceSlug="engineering"
          scopeTier="workspace"
          onClose={vi.fn()}
        />
      </MemoryRouter>,
    );
    expect(screen.getByTestId('mcp-resource-url').textContent).toBe(
      'http://localhost:3000/mcp/agent/w/engineering',
    );
    expect(screen.getByTestId('mcp-resource-url').textContent).not.toContain('/p/');
    u1();

    // 2. No projectKey and no scopeTier (defaults to workspace-scoped URL)
    const { unmount: u2 } = render(
      <MemoryRouter>
        <ConnectOAuthAppModal
          workspaceSlug="marketing"
          onClose={vi.fn()}
        />
      </MemoryRouter>,
    );
    expect(screen.getByTestId('mcp-resource-url').textContent).toBe(
      'http://localhost:3000/mcp/agent/w/marketing',
    );
    expect(screen.getByTestId('mcp-resource-url').textContent).not.toContain('/p/');
    expect(screen.getByTestId('mcp-resource-url').textContent).not.toContain('KANBA');
    u2();
  });

  it('fetches first project from /api/v1/projects when project scope has empty projectKey', async () => {
    const mockFetch = vi.fn().mockImplementation((url: string) => {
      if (url.includes('/api/v1/projects')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ items: [{ identifier: 'LIVE' }, { identifier: 'OPS' }] }),
        });
      }
      return Promise.reject(new Error('Unknown'));
    });
    vi.stubGlobal('fetch', mockFetch);

    render(
      <MemoryRouter>
        <ConnectOAuthAppModal
          workspaceSlug="production"
          scopeTier="project"
          onClose={vi.fn()}
        />
      </MemoryRouter>,
    );

    await act(async () => {
      await Promise.resolve();
    });

    expect(screen.getByTestId('mcp-resource-url').textContent).toBe(
      'http://localhost:3000/mcp/agent/w/production/p/LIVE',
    );

    vi.unstubAllGlobals();
  });

  it('falls back to <PROJECT_KEY> placeholder when project scope has 0 projects', async () => {
    const mockFetch = vi.fn().mockImplementation((url: string) => {
      if (url.includes('/api/v1/projects')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ items: [] }),
        });
      }
      return Promise.reject(new Error('Unknown'));
    });
    vi.stubGlobal('fetch', mockFetch);

    render(
      <MemoryRouter>
        <ConnectOAuthAppModal
          workspaceSlug="empty-ws"
          scopeTier="project"
          onClose={vi.fn()}
        />
      </MemoryRouter>,
    );

    await act(async () => {
      await Promise.resolve();
    });

    expect(screen.getByTestId('mcp-resource-url').textContent).toBe(
      'http://localhost:3000/mcp/agent/w/empty-ws/p/<PROJECT_KEY>',
    );

    vi.unstubAllGlobals();
  });

  it('handles network error and non-ok status when fetching projects in project scope', async () => {
    // 1. Network throw
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('Network down')));

    const { unmount: u1 } = render(
      <MemoryRouter>
        <ConnectOAuthAppModal
          workspaceSlug="offline-ws"
          scopeTier="project"
          onClose={vi.fn()}
        />
      </MemoryRouter>,
    );

    await act(async () => {
      await Promise.resolve();
    });

    expect(screen.getByTestId('mcp-resource-url').textContent).toBe(
      'http://localhost:3000/mcp/agent/w/offline-ws/p/<PROJECT_KEY>',
    );
    u1();

    // 2. HTTP 500 error
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false }));
    const { unmount: u2 } = render(
      <MemoryRouter>
        <ConnectOAuthAppModal
          workspaceSlug="err-ws"
          scopeTier="project"
          onClose={vi.fn()}
        />
      </MemoryRouter>,
    );

    await act(async () => {
      await Promise.resolve();
    });

    expect(screen.getByTestId('mcp-resource-url').textContent).toBe(
      'http://localhost:3000/mcp/agent/w/err-ws/p/<PROJECT_KEY>',
    );
    u2();

    // 3. Raw array format with .key
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve([{ key: 'ARRAY_PROJ' }]),
      }),
    );
    render(
      <MemoryRouter>
        <ConnectOAuthAppModal
          workspaceSlug="arr-ws"
          scopeTier="project"
          onClose={vi.fn()}
        />
      </MemoryRouter>,
    );

    await act(async () => {
      await Promise.resolve();
    });

    expect(screen.getByTestId('mcp-resource-url').textContent).toBe(
      'http://localhost:3000/mcp/agent/w/arr-ws/p/ARRAY_PROJ',
    );

    vi.unstubAllGlobals();
  });

  it('switches to Gemini App tab, displaying instructions and OAuth 2.1 details (KAN-395)', () => {
    render(
      <MemoryRouter>
        <ConnectOAuthAppModal
          user={{ is_workspace_admin: false }}
          workspaceSlug="gemini-ws"
          projectKey="GEM"
          onClose={vi.fn()}
        />
      </MemoryRouter>,
    );

    // Switch to Gemini App tab
    fireEvent.click(screen.getByTestId('tab-gemini-app'));
    expect(screen.getByTestId('gemini-app-instructions')).toBeDefined();
    expect(screen.getByTestId('gemini-app-instructions').textContent).toContain('Google Gemini Connected Apps');

    const snippet = screen.getByTestId('command-snippet').textContent;
    expect(snippet).toContain('Google Gemini Connected Apps (OAuth 2.1 PKCE)');
    expect(snippet).toContain('http://localhost:3000/mcp/agent/w/gemini-ws/p/GEM');
    expect(snippet).toContain('agent:read, agent:write');
  });

  it('allows dynamically changing Target Scope between Workspace, Single Project, and Server (KAN-395)', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: () =>
          Promise.resolve([
            { key: 'PROJ-ALPHA', name: 'Alpha Project' },
            { key: 'PROJ-BETA', name: 'Beta Project' },
          ]),
      }),
    );

    render(
      <MemoryRouter>
        <ConnectOAuthAppModal
          workspaceSlug="dynamic-ws"
          scopeTier="workspace"
          onClose={vi.fn()}
        />
      </MemoryRouter>,
    );

    await act(async () => {
      await Promise.resolve();
    });

    const scopeSelect = screen.getByTestId<HTMLSelectElement>('scope-tier-select');
    expect(scopeSelect.value).toBe('workspace');
    expect(screen.getByTestId('mcp-resource-url').textContent).toBe(
      'http://localhost:3000/mcp/agent/w/dynamic-ws',
    );

    // Switch to Server scope
    act(() => {
      fireEvent.change(scopeSelect, { target: { value: 'server' } });
    });
    expect(screen.getByTestId('mcp-resource-url').textContent).toBe(
      'http://localhost:3000/mcp/agent',
    );
    expect(screen.queryByTestId('project-select')).toBeNull();

    // Switch to Single Project scope
    act(() => {
      fireEvent.change(scopeSelect, { target: { value: 'project' } });
    });
    const projSelect = screen.getByTestId<HTMLSelectElement>('project-select');
    expect(projSelect).toBeDefined();
    expect(screen.getByTestId('mcp-resource-url').textContent).toBe(
      'http://localhost:3000/mcp/agent/w/dynamic-ws/p/PROJ-ALPHA',
    );

    // Switch selected project to PROJ-BETA
    act(() => {
      fireEvent.change(projSelect, { target: { value: 'PROJ-BETA' } });
    });
    expect(screen.getByTestId('mcp-resource-url').textContent).toBe(
      'http://localhost:3000/mcp/agent/w/dynamic-ws/p/PROJ-BETA',
    );

    vi.unstubAllGlobals();
  });

  it('wires selectedScopes into snippets and updates scope hint (KAN-395)', () => {
    render(
      <MemoryRouter>
        <ConnectOAuthAppModal
          workspaceSlug="scopes-ws"
          projectKey="SCP"
          onClose={vi.fn()}
        />
      </MemoryRouter>,
    );

    expect(screen.getByTestId('scope-hint').textContent).toContain('Selected scopes: agent:read, agent:write');

    // Uncheck agent:write
    const writeCheck = screen.getByTestId<HTMLInputElement>('scope-check-agent:write');
    fireEvent.click(writeCheck);

    expect(screen.getByTestId('scope-hint').textContent).toBe('Selected scopes: agent:read');

    // Check snippet reflects single scope
    fireEvent.click(screen.getByTestId('tab-cursor'));
    expect(screen.getByTestId('command-snippet').textContent).toContain('"agent:read"');
    expect(screen.getByTestId('command-snippet').textContent).not.toContain('"agent:write"');

    // Check Gemini snippet reflects single scope
    fireEvent.click(screen.getByTestId('tab-gemini-app'));
    expect(screen.getByTestId('command-snippet').textContent).toContain('Requested Scopes: agent:read');

    // Uncheck agent:read as well (empty scopes fallback branches)
    const readCheck = screen.getByTestId<HTMLInputElement>('scope-check-agent:read');
    fireEvent.click(readCheck);
    expect(screen.getByTestId('scope-hint').textContent).toBe('Selected scopes: None');
    expect(screen.getByTestId('command-snippet').textContent).toContain('Requested Scopes: agent:read, agent:write');
    expect(screen.getByTestId('gemini-app-instructions').textContent).toContain('agent:read, agent:write');
  });

  it('covers server scope tier initialization and project without scopeTier', () => {
    // 1. scopeTier="server" initial state
    const { unmount: u1 } = render(
      <MemoryRouter>
        <ConnectOAuthAppModal
          scopeTier="server"
          onClose={vi.fn()}
        />
      </MemoryRouter>,
    );
    expect(screen.getByTestId<HTMLSelectElement>('scope-tier-select').value).toBe('server');
    expect(screen.getByTestId('mcp-resource-url').textContent).toBe('http://localhost:3000/mcp/agent');
    u1();

    // 2. !scopeTier and projectKey="CUSTOM"
    const { unmount: u2 } = render(
      <MemoryRouter>
        <ConnectOAuthAppModal
          projectKey="CUSTOM"
          onClose={vi.fn()}
        />
      </MemoryRouter>,
    );
    expect(screen.getByTestId<HTMLSelectElement>('scope-tier-select').value).toBe('project');
    u2();
  });

  it('renders project options where name equals key or name is absent', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: () =>
          Promise.resolve([
            { key: 'SAME', name: 'SAME' },
            { key: 'NONAME' },
          ]),
      }),
    );

    render(
      <MemoryRouter>
        <ConnectOAuthAppModal
          workspaceSlug="test-ws"
          scopeTier="project"
          onClose={vi.fn()}
        />
      </MemoryRouter>,
    );

    await act(async () => {
      await Promise.resolve();
    });

    const projectSelect = screen.getByTestId<HTMLSelectElement>('project-select');
    expect(projectSelect.options.length).toBe(2);
    expect(projectSelect.options[0]?.text).toBe('SAME');
    expect(projectSelect.options[1]?.text).toBe('NONAME');

    vi.unstubAllGlobals();
  });
});
