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

  it('copies resource URL, RFC 8414 URL, and snippet to clipboard', () => {
    vi.useFakeTimers();
    render(
      <MemoryRouter>
        <ConnectOAuthAppModal
          user={{ is_workspace_admin: false }}
          onClose={vi.fn()}
        />
      </MemoryRouter>,
    );

    // Copy resource URL
    act(() => {
      fireEvent.click(screen.getByTestId('copy-resource-url-btn'));
    });
    expect(writeTextMock).toHaveBeenCalled();

    // Advance timer to trigger reset
    act(() => {
      vi.advanceTimersByTime(2100);
    });

    // Copy RFC 8414 URL
    act(() => {
      fireEvent.click(screen.getByTestId('copy-rfc8414-url-btn'));
    });
    expect(writeTextMock).toHaveBeenCalled();

    // Copy snippet
    act(() => {
      fireEvent.click(screen.getByTestId('copy-snippet-btn'));
    });
    expect(writeTextMock).toHaveBeenCalled();

    // Failed copy does not trigger timer
    vi.spyOn(clipboardModule, 'copyToClipboard').mockResolvedValueOnce(false);
    act(() => {
      fireEvent.click(screen.getByTestId('copy-resource-url-btn'));
    });
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

    // Escape key press
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(handleClose).toHaveBeenCalledTimes(2);

    // Done button click
    fireEvent.click(screen.getByTestId('close-modal-bottom-btn'));
    expect(handleClose).toHaveBeenCalledTimes(3);
  });
});
