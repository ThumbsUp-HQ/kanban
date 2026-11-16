// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import React from 'react';
import { McpConfigSnippetModal } from '../McpConfigSnippetModal';

describe('McpConfigSnippetModal direct unit tests', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('renders fallback placeholder when rawKey is not provided', () => {
    const handleClose = vi.fn();
    render(
      <McpConfigSnippetModal
        surface="agent"
        workspaceSlug="kanban"
        projectKey="KANBA"
        rawKey={undefined}
        onClose={handleClose}
      />,
    );

    const snippet = screen.getByTestId('snippet-code-box');
    expect(snippet.textContent).toContain('<your-mcp-key>');
    expect(screen.queryByTestId('raw-key-banner')).toBeNull();
  });

  it('handles backdrop click, escape key, and modal click', () => {
    const handleClose = vi.fn();
    render(
      <McpConfigSnippetModal
        surface="agent"
        workspaceSlug="kanban"
        projectKey="KANBA"
        rawKey="kb_agt_test_key"
        onClose={handleClose}
      />,
    );

    // Clicking child card should NOT trigger onClose
    const modalCard = screen.getByTestId('mcp-snippet-modal');
    fireEvent.click(modalCard);
    expect(handleClose).not.toHaveBeenCalled();

    // Non-escape key should NOT trigger onClose
    fireEvent.keyDown(window, { key: 'Enter' });
    expect(handleClose).not.toHaveBeenCalled();

    // Escape key triggers onClose
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(handleClose).toHaveBeenCalledTimes(1);

    // Clicking backdrop directly triggers onClose
    const backdrop = screen.getByTestId('mcp-snippet-modal-backdrop');
    fireEvent.click(backdrop);
    expect(handleClose).toHaveBeenCalledTimes(2);
  });

  it('handles clipboard copy and tabs/url scopes cleanly', () => {
    const handleClose = vi.fn();
    const writeTextMock = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, {
      clipboard: {
        writeText: writeTextMock,
      },
    });

    render(
      <McpConfigSnippetModal
        surface="agent"
        workspaceSlug="kanban"
        projectKey="KANBA"
        rawKey="kb_agt_test_key"
        onClose={handleClose}
      />,
    );

    // Switch tabs
    fireEvent.click(screen.getByTestId('tab-antigravity'));
    const snippetBox = screen.getByTestId('snippet-code-box');
    expect(snippetBox.textContent).toContain('serverUrl');
    expect(snippetBox.textContent).toContain('headers');
    expect(snippetBox.textContent).toContain('agy mcp add --header');

    fireEvent.click(screen.getByTestId('tab-claude'));
    fireEvent.click(screen.getByTestId('tab-gemini'));

    // Switch url scope
    const urlSelect = screen.getByTestId('url-scope-select');
    fireEvent.change(urlSelect, { target: { value: 'global' } });
    fireEvent.change(urlSelect, { target: { value: 'workspace' } });
    fireEvent.change(urlSelect, { target: { value: 'project' } });

    // Copy buttons
    fireEvent.click(screen.getByTestId('copy-key-button'));
    expect(writeTextMock).toHaveBeenCalledWith('kb_agt_test_key');

    fireEvent.click(screen.getByTestId('copy-snippet-button'));
    expect(writeTextMock).toHaveBeenCalledTimes(2);
  });
});
