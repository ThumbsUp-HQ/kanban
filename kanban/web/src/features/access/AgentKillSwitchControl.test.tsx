import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import React from 'react';
import fs from 'node:fs';
import path from 'node:path';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AgentKillSwitchControl } from './AgentKillSwitchControl';
import * as RealtimeModule from '../../api/RealtimeStatus';
import kan142Data from '../../../e2e/fixtures/access-inspector-kan-142.json';

const TEST_OBJECT_ID = 'c0000000-0000-0000-0000-000000000142';

function renderWithClient(ui: React.ReactElement, initialData?: unknown) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  if (initialData) {
    queryClient.setQueryData(['access', TEST_OBJECT_ID], initialData);
  }
  return {
    queryClient,
    ...render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>),
  };
}

describe('AgentKillSwitchControl', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(document, 'cookie', 'get').mockReturnValue('__Host-kb_csrf=csrf-test-token-123');
  });

  it('renders [ Kill Switch ] and triggers 2-step confirmation with default Cancel focus', () => {
    renderWithClient(
      <AgentKillSwitchControl
        objectId={TEST_OBJECT_ID}
        canonicalKey="KAN-142"
        agentsCount={2}
      />,
      kan142Data,
    );

    const btn = screen.getByRole('button', { name: /^kill switch$/i });
    expect(btn).toBeDefined();

    fireEvent.click(btn);

    // Confirmation banner appears
    expect(
      screen.getByText('Revoke all active agent grants on KAN-142?'),
    ).toBeDefined();

    const cancelBtn = screen.getByRole('button', { name: /cancel/i });
    const confirmBtn = screen.getByRole('button', { name: /confirm kill switch/i });

    expect(cancelBtn).toBeDefined();
    expect(confirmBtn).toBeDefined();

    // Focus moved to Cancel by default to prevent accidental Enter activation
    expect(document.activeElement).toBe(cancelBtn);

    // Clicking Cancel closes confirmation
    fireEvent.click(cancelBtn);
    expect(
      screen.queryByText('Revoke all active agent grants on KAN-142?'),
    ).toBeNull();
  });

  it('optimistically clears agents and calls POST endpoint with CSRF token', async () => {
    let capturedMethod = '';
    let capturedHeaders: Record<string, string> = {};

    vi.spyOn(globalThis, 'fetch').mockImplementation((_url, init) => {
      capturedMethod = init?.method ?? '';
      capturedHeaders = init?.headers ? (init.headers as Record<string, string>) : {};
      return Promise.resolve(
        new Response(JSON.stringify({ ...kan142Data, agents: [] }), {
          status: 200,
          headers: { 'content-type': 'application/json' },
        }),
      );
    });

    const { queryClient } = renderWithClient(
      <AgentKillSwitchControl
        objectId={TEST_OBJECT_ID}
        canonicalKey="KAN-142"
        agentsCount={2}
      />,
      kan142Data,
    );

    // Open confirmation
    fireEvent.click(screen.getByRole('button', { name: /^kill switch$/i }));

    // Confirm
    const confirmBtn = screen.getByRole('button', { name: /confirm kill switch/i });
    fireEvent.click(confirmBtn);

    await waitFor(() => {
      expect(capturedMethod).toBe('POST');
    });

    expect(capturedHeaders['X-CSRF-Token']).toBe('csrf-test-token-123');

    // Query data is cleared
    const cached = queryClient.getQueryData<typeof kan142Data>(['access', TEST_OBJECT_ID]);
    expect(cached?.agents).toEqual([]);
  });

  it('rolls back to previous snapshot on HTTP 500 error and announces rollback', async () => {
    const announceSpy = vi.spyOn(RealtimeModule, 'announce');

    vi.spyOn(globalThis, 'fetch').mockImplementation(() => {
      return Promise.resolve(
        new Response(JSON.stringify({ error: 'Internal Server Error' }), {
          status: 500,
          headers: { 'content-type': 'application/json' },
        }),
      );
    });

    const { queryClient } = renderWithClient(
      <AgentKillSwitchControl
        objectId={TEST_OBJECT_ID}
        canonicalKey="KAN-142"
        agentsCount={2}
      />,
      kan142Data,
    );

    fireEvent.click(screen.getByRole('button', { name: /^kill switch$/i }));
    fireEvent.click(screen.getByRole('button', { name: /confirm kill switch/i }));

    await waitFor(() => {
      expect(announceSpy).toHaveBeenCalledWith(
        'Failed to revoke agent grants. Reverting changes.',
      );
    });

    // Check cache is restored
    const cached = queryClient.getQueryData<typeof kan142Data>(['access', TEST_OBJECT_ID]);
    expect(cached?.agents.length).toBe(2);
  });

  it('handles missing CSRF token and empty cache gracefully', async () => {
    vi.restoreAllMocks();
    // Simulate no cookie present
    vi.spyOn(document, 'cookie', 'get').mockReturnValue('');
    let cookieSet = '';
    vi.spyOn(document, 'cookie', 'set').mockImplementation((val) => {
      cookieSet = val;
    });

    vi.spyOn(globalThis, 'fetch').mockImplementation(() => {
      return Promise.resolve(
        new Response(JSON.stringify({ agents: [] }), {
          status: 200,
          headers: { 'content-type': 'application/json' },
        }),
      );
    });

    renderWithClient(
      <AgentKillSwitchControl
        objectId={TEST_OBJECT_ID}
        canonicalKey=""
        agentsCount={1}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: /^kill switch$/i }));
    expect(
      screen.getByText(`Revoke all active agent grants on ${TEST_OBJECT_ID}?`),
    ).toBeDefined();
    fireEvent.click(screen.getByRole('button', { name: /confirm kill switch/i }));

    await waitFor(() => {
      expect(cookieSet).toContain('kb_csrf');
    });
  });

  describe('KAN-488: FieldHelpHint and Shift-Left Invariants', () => {
    it('renders FieldHelpHint adjacent to [ Kill Switch ] trigger without button or label nesting (HTML 4.10.4)', () => {
      renderWithClient(
        <AgentKillSwitchControl
          objectId={TEST_OBJECT_ID}
          canonicalKey="KAN-142"
          agentsCount={2}
        />,
        kan142Data,
      );

      const hintTrigger = screen.getByTestId('hint-agent-kill-switch');
      expect(hintTrigger).toBeDefined();

      // Invariant 1: NEVER nest <FieldHelpHint> (<button>) inside <label> or another <button>!
      expect(
        document.querySelectorAll('label button.field-help-hint, button button.field-help-hint').length,
      ).toBe(0);
      expect(hintTrigger.closest('button.access-inspector__kill-switch-btn')).toBeNull();
      expect(hintTrigger.closest('label')).toBeNull();

      // Sibling structure inside wrapper
      const wrapper = hintTrigger.closest('.access-inspector__kill-switch-wrapper');
      expect(wrapper).not.toBeNull();
      expect(wrapper?.querySelector('.access-inspector__kill-switch-btn')).toBeDefined();
    });

    it('opens FieldHelpHint popover on trigger, displaying security summary, default policy, and docHref wiki link', async () => {
      renderWithClient(
        <AgentKillSwitchControl
          objectId={TEST_OBJECT_ID}
          canonicalKey="KAN-142"
          agentsCount={2}
        />,
        kan142Data,
      );

      const hintTrigger = screen.getByTestId('hint-agent-kill-switch');
      fireEvent.focus(hintTrigger);

      const popover = screen.getByTestId('hint-agent-kill-switch-popover');
      expect(popover).toBeDefined();
      expect(popover.textContent).toContain('Immediately revokes all active agent tokens and session grants on this object.');
      expect(popover.textContent).toContain('Active grants retained until explicit revocation');

      // Doc link
      const docLink = screen.getByRole('link', { name: /more info/i });
      expect(docLink.getAttribute('href')).toBe('/docs/zero-trust-security-and-access-visibility');

      // Dismiss on Escape
      fireEvent.keyDown(hintTrigger, { key: 'Escape' });
      await waitFor(() => {
        expect(screen.queryByTestId('hint-agent-kill-switch-popover')).toBeNull();
      });
    });

    it('renders FieldHelpHint in confirmation prompt without HTML 4.10.4 nesting and allows popover interaction', async () => {
      renderWithClient(
        <AgentKillSwitchControl
          objectId={TEST_OBJECT_ID}
          canonicalKey="KAN-142"
          agentsCount={2}
        />,
        kan142Data,
      );

      // Open confirm state
      fireEvent.click(screen.getByRole('button', { name: /^kill switch$/i }));

      const confirmHintTrigger = screen.getByTestId('hint-agent-kill-switch-confirm');
      expect(confirmHintTrigger).toBeDefined();

      // Invariant 1: HTML 4.10.4 compliance
      expect(
        document.querySelectorAll('label button.field-help-hint, button button.field-help-hint').length,
      ).toBe(0);
      expect(confirmHintTrigger.closest('button.access-inspector__btn')).toBeNull();
      expect(confirmHintTrigger.closest('label')).toBeNull();

      // Open popover from confirmation banner
      fireEvent.focus(confirmHintTrigger);
      const popover = screen.getByTestId('hint-agent-kill-switch-confirm-popover');
      expect(popover).toBeDefined();
      expect(popover.textContent).toContain('Immediately revokes all active agent tokens and session grants on this object.');

      // Dismiss on Escape - confirmation prompt must remain active
      fireEvent.keyDown(confirmHintTrigger, { key: 'Escape' });
      await waitFor(() => {
        expect(screen.queryByTestId('hint-agent-kill-switch-confirm-popover')).toBeNull();
      });
      expect(screen.getByText('Revoke all active agent grants on KAN-142?')).toBeDefined();
    });

    it('verifies zero inline style={{}} props and zero HTML 4.10.4 button/label nesting in static AST', () => {
      const componentPath = path.resolve(__dirname, 'AgentKillSwitchControl.tsx');
      const content = fs.readFileSync(componentPath, 'utf8');

      // Zero inline styles
      expect(content).not.toMatch(/style\s*=\s*\{\{/);

      // Zero FieldHelpHint inside <label> or <button>
      expect(content).not.toMatch(/<button[^>]*>(?:(?!<\/button>)[\s\S])*<FieldHelpHint/);
      expect(content).not.toMatch(/<label[^>]*>(?:(?!<\/label>)[\s\S])*<FieldHelpHint/);
    });
  });
});
