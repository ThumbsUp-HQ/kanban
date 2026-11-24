// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import React from 'react';
import fs from 'node:fs';
import path from 'node:path';
import { MemoryRouter } from 'react-router';
import { McpAccessStudio } from '../McpAccessStudio';
import { McpConfigSnippetModal } from '../McpConfigSnippetModal';
import * as settingsApi from '../settingsApi';
import * as clientModule from '../../../api/client';

vi.mock('../../auth/SecondFactorStep', () => ({
  SecondFactorStep: ({ onSuccess, onCancel }: { onSuccess: () => void; onCancel?: () => void }) => (
    <div data-testid="mock-second-factor-step">
      <button type="button" data-testid="mock-mfa-success-btn" onClick={onSuccess}>
        Success
      </button>
      <button type="button" data-testid="mock-mfa-cancel-btn" onClick={onCancel}>
        Cancel
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

const mockKeys: settingsApi.McpApiKeyItem[] = [
  {
    id: 'key-1',
    label: 'Automation Token',
    display_hint: 'a1b2',
    surface: 'agent',
    scope_tier: 'workspace',
    scopes: ['agent:read', 'agent:write'],
    allowed_projects: null,
    created_at: new Date().toISOString(),
    expires_at: new Date(Date.now() + 86400000 * 30).toISOString(),
    last_used_at: null,
    revoked_at: null,
  },
];

const mockApps: settingsApi.OAuthConnectedApp[] = [
  {
    id: 'grant-1',
    client_id: 'client_claude',
    client_name: 'Claude Code CLI',
    surface: 'agent',
    scopes: ['agent:read'],
    allowed_projects: null,
    created_at: new Date().toISOString(),
    revoked_at: null,
  },
];

describe('McpAccessStudioModalScroll (KAN-382)', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(settingsApi, 'fetchUnifiedMcpKeys').mockResolvedValue(mockKeys);
    vi.spyOn(settingsApi, 'fetchPersonalMcpKeys').mockResolvedValue(mockKeys);
    vi.spyOn(settingsApi, 'fetchConnectedApps').mockResolvedValue(mockApps);
    vi.spyOn(clientModule, 'apiFetch').mockImplementation((_method: string, p: string) => {
      if (p === '/api/v1/projects') {
        return Promise.resolve({
          items: [{ id: 'proj-kan', identifier: 'KAN', name: 'Kanban Core' }],
        });
      }
      return Promise.resolve({
        is_server_admin: true,
        is_workspace_admin: true,
      });
    });
  });

  describe('CSS Rule Integrity for Modal Constraints', () => {
    const snippetCssPath = path.resolve(__dirname, '../McpConfigSnippetModal.css');
    const studioCssPath = path.resolve(__dirname, '../McpAccessStudio.css');
    const snippetCss = fs.readFileSync(snippetCssPath, 'utf8');
    const studioCss = fs.readFileSync(studioCssPath, 'utf8');

    it('enforces overflow-y: auto and box-sizing on .kb-snippet-modal-backdrop', () => {
      expect(snippetCss).toContain('.kb-snippet-modal-backdrop');
      expect(snippetCss).toMatch(/\.kb-snippet-modal-backdrop\s*\{[^}]*overflow-y:\s*auto/);
      expect(snippetCss).toMatch(/\.kb-snippet-modal-backdrop\s*\{[^}]*box-sizing:\s*border-box/);
    });

    it('enforces bounded max-height, vertical scrolling, and overscroll on .kb-snippet-modal-card', () => {
      expect(snippetCss).toMatch(/\.kb-snippet-modal-card\s*\{[^}]*max-height:\s*calc\(100vh\s*-\s*40px\)/);
      expect(snippetCss).toMatch(/\.kb-snippet-modal-card\s*\{[^}]*max-height:\s*calc\(100dvh\s*-\s*40px\)/);
      expect(snippetCss).toMatch(/\.kb-snippet-modal-card\s*\{[^}]*overflow-y:\s*auto/);
      expect(snippetCss).toMatch(/\.kb-snippet-modal-card\s*\{[^}]*overscroll-behavior:\s*contain/);
      expect(snippetCss).toMatch(/\.kb-snippet-modal-card\s*\{[^}]*box-sizing:\s*border-box/);
    });

    it('enforces sticky header with top: 0, z-index: 2, and background on .kb-snippet-modal-header', () => {
      expect(snippetCss).toMatch(/\.kb-snippet-modal-header\s*\{[^}]*position:\s*sticky/);
      expect(snippetCss).toMatch(/\.kb-snippet-modal-header\s*\{[^}]*top:\s*0/);
      expect(snippetCss).toMatch(/\.kb-snippet-modal-header\s*\{[^}]*z-index:\s*2/);
      expect(snippetCss).toMatch(/\.kb-snippet-modal-header\s*\{[^}]*background:\s*var\(--bg-surface\)/);
    });

    it('enforces sticky footer actions with bottom: 0, z-index: 2, and background on .kb-mcp-form-actions', () => {
      expect(studioCss).toMatch(/\.kb-mcp-form-actions\s*\{[^}]*position:\s*sticky/);
      expect(studioCss).toMatch(/\.kb-mcp-form-actions\s*\{[^}]*bottom:\s*0/);
      expect(studioCss).toMatch(/\.kb-mcp-form-actions\s*\{[^}]*z-index:\s*2/);
      expect(studioCss).toMatch(/\.kb-mcp-form-actions\s*\{[^}]*background:\s*var\(--bg-surface\)/);
      expect(studioCss).toMatch(/\.kb-mcp-form-actions\s*\{[^}]*border-top:\s*1px solid var\(--border-subtle/);
      expect(studioCss).toMatch(/\.kb-mcp-form-actions\s*\{[^}]*padding-top:\s*12px/);
    });

    it('enforces sticky footer with bottom: 0 and z-index: 2 on .kb-snippet-footer-row', () => {
      expect(snippetCss).toMatch(/\.kb-snippet-footer-row\s*\{[^}]*position:\s*sticky/);
      expect(snippetCss).toMatch(/\.kb-snippet-footer-row\s*\{[^}]*bottom:\s*0/);
      expect(snippetCss).toMatch(/\.kb-snippet-footer-row\s*\{[^}]*z-index:\s*2/);
      expect(snippetCss).toMatch(/\.kb-snippet-footer-row\s*\{[^}]*background:\s*var\(--bg-surface\)/);
    });

    it('defines responsive max-height and padding adjustments in @media (max-width: 640px)', () => {
      expect(snippetCss).toContain('@media (max-width: 640px)');
      expect(snippetCss).toMatch(/@media \(max-width:\s*640px\)[\s\S]*?max-height:\s*calc\(100vh\s*-\s*24px\)/);
      expect(snippetCss).toMatch(/@media \(max-width:\s*640px\)[\s\S]*?max-height:\s*calc\(100dvh\s*-\s*24px\)/);
    });
  });

  describe('Mint Modal DOM Hierarchy and AdvancedSection Expansion', () => {
    it('opens mint modal and enforces .kb-snippet-modal-card and .kb-mcp-mint-form container classes', async () => {
      render(
        <MemoryRouter initialEntries={['/settings/mcp']}>
          <McpAccessStudio tier="workspace" />
        </MemoryRouter>,
      );

      await waitFor(() => {
        expect(screen.getByTestId('mint-key-button')).toBeDefined();
      });

      // Open mint modal
      act(() => {
        fireEvent.click(screen.getByTestId('mint-key-button'));
      });

      const backdrop = screen.getByTestId('mint-modal-backdrop');
      const card = screen.getByTestId('mint-modal-card');
      const form = card.querySelector('form');
      const header = card.querySelector('.kb-snippet-modal-header');
      const actions = card.querySelector('.kb-mcp-form-actions');

      expect(backdrop.classList.contains('kb-snippet-modal-backdrop')).toBe(true);
      expect(card.classList.contains('kb-snippet-modal-card')).toBe(true);
      expect(form).not.toBeNull();
      expect(form?.classList.contains('kb-mcp-mint-form')).toBe(true);
      expect(header).not.toBeNull();
      expect(actions).not.toBeNull();
    });

    it('renders and expands AdvancedSection while keeping sticky header and footer reachable', async () => {
      render(
        <MemoryRouter initialEntries={['/settings/mcp']}>
          <McpAccessStudio tier="workspace" />
        </MemoryRouter>,
      );

      await waitFor(() => {
        expect(screen.getByTestId('mint-key-button')).toBeDefined();
      });

      act(() => {
        fireEvent.click(screen.getByTestId('mint-key-button'));
      });

      // Verify AdvancedSection disclosure exists and is initially collapsed
      const advancedToggle = screen.getByTestId('advanced-capability-restrictions-toggle');
      expect(advancedToggle).toBeDefined();
      expect(advancedToggle.getAttribute('aria-expanded')).toBe('false');

      // Expand AdvancedSection
      act(() => {
        fireEvent.click(advancedToggle);
      });
      expect(advancedToggle.getAttribute('aria-expanded')).toBe('true');

      // Confirm large form elements are rendered into the DOM
      const bitsGrid = screen.getByTestId('capability-bits-grid');
      const cidrInput = screen.getByTestId('mint-allowed-cidrs-input');
      const toolsGrid = screen.getByTestId('tools-selection-grid');

      expect(bitsGrid).toBeDefined();
      expect(cidrInput).toBeDefined();
      expect(toolsGrid).toBeDefined();

      // Form actions (Cancel and Mint Key) remain present and actionable
      const submitBtn = screen.getByTestId<HTMLButtonElement>('mint-submit-btn');
      const labelInput = screen.getByTestId('mint-label-input');

      expect(submitBtn).toBeDefined();
      expect(submitBtn.disabled).toBe(true);

      // Enter label to enable submit
      act(() => {
        fireEvent.change(labelInput, { target: { value: 'Production CI Token' } });
      });
      expect(submitBtn.disabled).toBe(false);

      // Interact with granular capability toggles
      const capBit1 = screen.getByTestId<HTMLInputElement>('cap-bit-1');
      expect(capBit1.checked).toBe(true);
      act(() => {
        fireEvent.click(capBit1);
      });
      expect(capBit1.checked).toBe(false);

      // Interact with tool selection checkboxes
      const toolCheck = screen.getByTestId<HTMLInputElement>('disable-tool-ping_agent');
      expect(toolCheck.checked).toBe(false);
      act(() => {
        fireEvent.click(toolCheck);
      });
      expect(toolCheck.checked).toBe(true);

      // Cancel button resets and dismisses modal
      const cancelBtn = screen.getByText('Cancel');
      act(() => {
        fireEvent.click(cancelBtn);
      });

      await waitFor(() => {
        expect(screen.queryByTestId('mint-modal-card')).toBeNull();
      });
    });

    it('verifies McpConfigSnippetModal also utilizes bounded .kb-snippet-modal-card and sticky footer', () => {
      const handleClose = vi.fn();
      render(
        <McpConfigSnippetModal
          surface="agent"
          workspaceSlug="kanban"
          projectKey="KAN"
          rawKey="kb_agt_test_token"
          onClose={handleClose}
        />,
      );

      const card = screen.getByTestId('mcp-snippet-modal');
      const backdrop = screen.getByTestId('mcp-snippet-modal-backdrop');
      const header = card.querySelector('.kb-snippet-modal-header');
      const footer = card.querySelector('.kb-snippet-footer-row');

      expect(card.classList.contains('kb-snippet-modal-card')).toBe(true);
      expect(backdrop.classList.contains('kb-snippet-modal-backdrop')).toBe(true);
      expect(header).not.toBeNull();
      expect(footer).not.toBeNull();

      const doneBtn = screen.getByTestId('done-button');
      fireEvent.click(doneBtn);
      expect(handleClose).toHaveBeenCalledTimes(1);
    });
  });
});
