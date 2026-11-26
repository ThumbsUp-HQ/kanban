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

  it('supports toggling scope checkboxes', async () => {
    render(
      <MemoryRouter>
        <ConnectOAuthAppModal
          user={{ is_workspace_admin: false }}
          onClose={vi.fn()}
        />
      </MemoryRouter>,
    );

    await act(async () => {
      await Promise.resolve();
    });

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

  it('closes on Escape key press and backdrop click', async () => {
    const handleClose = vi.fn();
    render(
      <MemoryRouter>
        <ConnectOAuthAppModal
          user={{ is_workspace_admin: false }}
          onClose={handleClose}
        />
      </MemoryRouter>,
    );

    await act(async () => {
      await Promise.resolve();
    });

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

  it('handles unmount while project fetch is pending', () => {
    let resolvePromise: (val: unknown) => void = () => undefined;
    const pendingPromise = new Promise((resolve) => {
      resolvePromise = resolve;
    });
    vi.stubGlobal('fetch', vi.fn().mockReturnValue(pendingPromise));

    const { unmount } = render(
      <MemoryRouter>
        <ConnectOAuthAppModal onClose={vi.fn()} />
      </MemoryRouter>,
    );

    unmount();
    resolvePromise({
      ok: true,
      json: () => Promise.resolve([{ key: 'P1' }]),
    });

    vi.unstubAllGlobals();
  });

  describe('FieldHelpHint and StudioDocLink (KAN-518)', () => {
    it('renders connect-oauth-doc-link in modal header with documentation href and title', async () => {
      render(
        <MemoryRouter>
          <ConnectOAuthAppModal
            workspaceSlug="kanban"
            onClose={vi.fn()}
          />
        </MemoryRouter>,
      );

      await act(async () => {
        await Promise.resolve();
      });

      const docLink = screen.getByTestId('connect-oauth-doc-link');
      expect(docLink).toBeDefined();
      expect(docLink.getAttribute('href')).toBe('/docs/three-surface-mcp-server-architecture#oauth-21--pkce');
      expect(docLink.getAttribute('aria-label')).toBe('MCP OAuth 2.1 and PKCE Documentation');
      expect(docLink.textContent).toContain('Documentation ->');
    });

    it('renders Target Scope FieldHelpHint popover with scope boundary descriptions and doc link', async () => {
      render(
        <MemoryRouter>
          <ConnectOAuthAppModal
            workspaceSlug="corp-eng"
            onClose={vi.fn()}
          />
        </MemoryRouter>,
      );

      await act(async () => {
        await Promise.resolve();
      });

      const scopeHelpBtn = screen.getByTestId('target-scope-help');
      expect(scopeHelpBtn).toBeDefined();
      expect(scopeHelpBtn.getAttribute('aria-label')).toBe('Help for Target Scope');

      act(() => {
        scopeHelpBtn.focus();
      });

      const popover = screen.getByTestId('target-scope-help-popover');
      expect(popover).toBeDefined();
      expect(popover.textContent).toContain('Target Scope');
      expect(popover.textContent).toContain('Security boundary defining whether OAuth client tokens access');
      expect(popover.textContent).toContain('Workspace');
      expect(popover.textContent).toContain('Single Project');
      expect(popover.textContent).toContain('Server (Global)');

      const docLink = screen.getByTestId('target-scope-help-doc-link');
      expect(docLink.getAttribute('href')).toBe('/docs/three-surface-mcp-server-architecture#oauth-21--pkce');
    });

    it('renders Target MCP Surface FieldHelpHint popover with surfaces and doc link', async () => {
      render(
        <MemoryRouter>
          <ConnectOAuthAppModal
            user={{ is_server_admin: true }}
            workspaceSlug="corp-eng"
            onClose={vi.fn()}
          />
        </MemoryRouter>,
      );

      await act(async () => {
        await Promise.resolve();
      });

      const surfaceHelpBtn = screen.getByTestId('target-surface-help');
      expect(surfaceHelpBtn).toBeDefined();
      expect(surfaceHelpBtn.getAttribute('aria-label')).toBe('Help for Target MCP Surface');

      act(() => {
        surfaceHelpBtn.focus();
      });

      const popover = screen.getByTestId('target-surface-help-popover');
      expect(popover).toBeDefined();
      expect(popover.textContent).toContain('Target MCP Surface');
      expect(popover.textContent).toContain('/mcp/agent');
      expect(popover.textContent).toContain('/mcp/docs');
      expect(popover.textContent).toContain('/mcp/admin');

      const docLink = screen.getByTestId('target-surface-help-doc-link');
      expect(docLink.getAttribute('href')).toBe('/docs/three-surface-mcp-server-architecture#oauth-21--pkce');
    });

    it('verifies light and dark modal non-regression including copy and close interactions', async () => {
      const handleClose = vi.fn();
      const writeTextMock = vi.fn().mockResolvedValue(undefined);
      Object.assign(navigator, {
        clipboard: { writeText: writeTextMock },
      });

      // Test under light mode
      document.documentElement.setAttribute('data-theme', 'light');
      const { unmount } = render(
        <MemoryRouter>
          <ConnectOAuthAppModal
            workspaceSlug="light-ws"
            onClose={handleClose}
          />
        </MemoryRouter>,
      );

      await act(async () => {
        await Promise.resolve();
      });

      expect(screen.getByTestId('connect-oauth-app-modal')).toBeDefined();
      expect(screen.getByTestId('connect-oauth-doc-link')).toBeDefined();
      expect(screen.getByTestId('target-scope-help')).toBeDefined();
      expect(screen.getByTestId('target-surface-help')).toBeDefined();

      // Copy snippet button works in light mode
      const copySnippetBtn = screen.getByTestId('copy-snippet-btn');
      await act(async () => {
        fireEvent.click(copySnippetBtn);
        await Promise.resolve();
      });
      expect(writeTextMock).toHaveBeenCalled();

      // Bottom close button works
      const bottomCloseBtn = screen.getByTestId('close-modal-bottom-btn');
      fireEvent.click(bottomCloseBtn);
      expect(handleClose).toHaveBeenCalledTimes(1);
      unmount();

      // Test under dark mode
      document.documentElement.setAttribute('data-theme', 'dark');
      const handleCloseDark = vi.fn();
      render(
        <MemoryRouter>
          <ConnectOAuthAppModal
            workspaceSlug="dark-ws"
            onClose={handleCloseDark}
          />
        </MemoryRouter>,
      );

      await act(async () => {
        await Promise.resolve();
      });

      expect(screen.getByTestId('connect-oauth-app-modal')).toBeDefined();
      expect(screen.getByTestId('connect-oauth-doc-link')).toBeDefined();
      expect(screen.getByTestId('target-scope-help')).toBeDefined();
      expect(screen.getByTestId('target-surface-help')).toBeDefined();

      // Switching client tab in dark mode
      fireEvent.click(screen.getByTestId('tab-cursor'));
      expect(screen.getByTestId('command-snippet').textContent).toContain('"url": "http://localhost:3000/mcp/agent/w/dark-ws"');

      // Top close button works
      fireEvent.click(screen.getByTestId('close-connect-oauth-modal-btn'));
      expect(handleCloseDark).toHaveBeenCalledTimes(1);

      document.documentElement.removeAttribute('data-theme');
    });

    it('verifies header actions styling and responsive wrap rules in ConnectOAuthAppModal.css', async () => {
      const fs = await import('node:fs');
      const path = await import('node:path');
      const cssPath = path.resolve(__dirname, '../ConnectOAuthAppModal.css');
      const cssContent = fs.readFileSync(cssPath, 'utf-8');

      expect(cssContent).toContain('.kb-connect-oauth-header-actions');
      expect(cssContent).toContain('white-space: nowrap;');
      expect(cssContent).toContain('flex-wrap: wrap;');

      render(
        <MemoryRouter>
          <ConnectOAuthAppModal onClose={vi.fn()} />
        </MemoryRouter>,
      );

      await act(async () => {
        await Promise.resolve();
      });

      const headerActions = screen.getByTestId('connect-oauth-doc-link').parentElement;
      expect(headerActions).toBeDefined();
      expect(headerActions?.className).toBe('kb-connect-oauth-header-actions');
      expect(headerActions?.getAttribute('style')).toBeNull();
    });
  });

  describe('Default Scope Option with FieldHelpHint (KAN-519)', () => {
    it('renders [Default] suffix on the Workspace option and defaults to workspace scope', async () => {
      render(
        <MemoryRouter>
          <ConnectOAuthAppModal
            workspaceSlug="acme-engineering"
            onClose={vi.fn()}
          />
        </MemoryRouter>,
      );

      await act(async () => {
        await Promise.resolve();
      });

      const scopeSelect = screen.getByTestId<HTMLSelectElement>('scope-tier-select');
      expect(scopeSelect.value).toBe('workspace');

      const options = Array.from(scopeSelect.querySelectorAll('option'));
      const workspaceOpt = options.find((opt) => opt.value === 'workspace');
      expect(workspaceOpt).toBeDefined();
      expect(workspaceOpt?.textContent).toBe('Workspace (acme-engineering) [Default]');
      expect(scopeSelect.selectedOptions[0]?.textContent).toBe('Workspace (acme-engineering) [Default]');
    });

    it('renders Target Scope FieldHelpHint with default selection notice, [Default] in validValues and defaultValue, and checks ARIA', async () => {
      render(
        <MemoryRouter>
          <ConnectOAuthAppModal
            workspaceSlug="kanban"
            onClose={vi.fn()}
          />
        </MemoryRouter>,
      );

      await act(async () => {
        await Promise.resolve();
      });

      const scopeHelpBtn = screen.getByTestId('target-scope-help');
      expect(scopeHelpBtn).toBeDefined();
      expect(scopeHelpBtn.getAttribute('aria-label')).toBe('Help for Target Scope');
      expect(scopeHelpBtn.getAttribute('aria-expanded')).toBe('false');

      // Verify HTML semantics: FieldHelpHint is not nested inside label
      const scopeLabel = screen.getByText('Target Scope');
      expect(scopeLabel.tagName.toLowerCase()).toBe('label');
      expect(scopeLabel.contains(scopeHelpBtn)).toBe(false);

      act(() => {
        scopeHelpBtn.focus();
      });

      expect(scopeHelpBtn.getAttribute('aria-expanded')).toBe('true');
      const popover = screen.getByTestId('target-scope-help-popover');
      expect(popover).toBeDefined();

      // Summary explicitly clarifies default selection
      expect(popover.textContent).toContain('Workspace scope is selected by default.');

      // Valid values list includes Workspace [Default] with explanation
      expect(popover.textContent).toContain('Workspace [Default]');
      expect(popover.textContent).toContain('Access all projects and resources in the active workspace (default).');
      expect(popover.textContent).toContain('Single Project');
      expect(popover.textContent).toContain('Server (Global)');

      // Default value row rendered
      expect(popover.textContent).toContain('Default:');
      expect(popover.textContent).toContain('Workspace [Default]');
    });

    it('handles Escape key behavior: closes FieldHelpHint popover without closing the modal', async () => {
      const handleClose = vi.fn();
      render(
        <MemoryRouter>
          <ConnectOAuthAppModal
            workspaceSlug="kanban"
            onClose={handleClose}
          />
        </MemoryRouter>,
      );

      await act(async () => {
        await Promise.resolve();
      });

      const scopeHelpBtn = screen.getByTestId('target-scope-help');

      // Open popover via focus
      act(() => {
        scopeHelpBtn.focus();
      });
      expect(screen.getByTestId('target-scope-help-popover')).toBeDefined();

      // Press Escape while focused on trigger button
      act(() => {
        fireEvent.keyDown(scopeHelpBtn, { key: 'Escape' });
      });

      // Popover closes, but modal onClose was NOT called
      expect(screen.queryByTestId('target-scope-help-popover')).toBeNull();
      expect(handleClose).not.toHaveBeenCalled();

      // Press Escape again now that popover is closed
      act(() => {
        window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
      });

      // Modal onClose is now called
      expect(handleClose).toHaveBeenCalledTimes(1);
    });

    it('preserves non-regression across all scope tier selections and client snippets', async () => {
      render(
        <MemoryRouter>
          <ConnectOAuthAppModal
            workspaceSlug="prod-ws"
            projectKey="CORE"
            scopeTier="all"
            onClose={vi.fn()}
          />
        </MemoryRouter>,
      );

      await act(async () => {
        await Promise.resolve();
      });

      const scopeSelect = screen.getByTestId<HTMLSelectElement>('scope-tier-select');
      expect(scopeSelect.value).toBe('workspace');
      expect(screen.getByTestId('mcp-resource-url').textContent).toContain('/mcp/agent/w/prod-ws');

      // Switch to Single Project
      act(() => {
        fireEvent.change(scopeSelect, { target: { value: 'project' } });
      });
      expect(scopeSelect.value).toBe('project');
      expect(screen.getByTestId('mcp-resource-url').textContent).toContain('/mcp/agent/w/prod-ws/p/CORE');

      // Switch to Server
      act(() => {
        fireEvent.change(scopeSelect, { target: { value: 'server' } });
      });
      expect(scopeSelect.value).toBe('server');
      expect(screen.getByTestId('mcp-resource-url').textContent).toContain('/mcp/agent');
      expect(screen.getByTestId('mcp-resource-url').textContent).not.toContain('/w/');

      // Switch back to Workspace default
      act(() => {
        fireEvent.change(scopeSelect, { target: { value: 'workspace' } });
      });
      expect(scopeSelect.value).toBe('workspace');
      expect(screen.getByTestId('mcp-resource-url').textContent).toContain('/mcp/agent/w/prod-ws');

      // Check snippets across tabs
      fireEvent.click(screen.getByTestId('tab-antigravity'));
      expect(screen.getByTestId('command-snippet').textContent).toContain('/mcp/agent/w/prod-ws');

      fireEvent.click(screen.getByTestId('tab-codex'));
      expect(screen.getByTestId('command-snippet').textContent).toContain('codex mcp add kanban');
    });

    it('verifies ConnectOAuthAppModal.css contains all 3 theme modes, adjacent gap: 6px, and mobile constraints', async () => {
      const fs = await import('node:fs');
      const path = await import('node:path');
      const cssPath = path.resolve(__dirname, '../ConnectOAuthAppModal.css');
      const cssContent = fs.readFileSync(cssPath, 'utf-8');

      // 3 Theme Modes
      expect(cssContent).toContain(':root {');
      expect(cssContent).toContain("[data-theme='dark'] {");
      expect(cssContent).toContain('@media (prefers-color-scheme: dark) {');

      // Adjacent (?) with gap: 6px and margin: 0
      expect(cssContent).toContain('.kb-connect-oauth-label-row {');
      expect(cssContent).toContain('.kb-connect-oauth-label-row .field-help-hint {');
      expect(cssContent).toContain('.kb-connect-oauth-label {');
      expect(cssContent).toContain('display: inline-flex;');
      expect(cssContent).toContain('gap: 6px;');
      expect(cssContent).toContain('.kb-connect-oauth-label .field-help-hint {');
      expect(cssContent).toContain('margin: 0;');

      // High contrast badge-fg links
      expect(cssContent).toContain('color: var(--badge-fg);');

      // Mobile unclipped constraints
      expect(cssContent).toContain('@media (max-width: 640px) {');
      expect(cssContent).toContain('max-height: min(96vh, 880px);');
      expect(cssContent).toContain('overflow-y: auto;');
    });
  });
});
