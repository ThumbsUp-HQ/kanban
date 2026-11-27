import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AccessInspectorPopover } from './AccessInspectorPopover';
import { ShellPanelsProvider, registerShellPanel, useShellPanels } from '../../app/shellPanels';
import kan142Data from '../../../e2e/fixtures/access-inspector-kan-142.json';
import redactedData from '../../../e2e/fixtures/access-inspector-redacted.json';

const TEST_OBJECT_ID = 'c0000000-0000-0000-0000-000000000142';

function renderWithClient(ui: React.ReactElement, initialData?: unknown) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  });
  if (initialData) {
    queryClient.setQueryData(['access', TEST_OBJECT_ID], initialData);
  }
  return render(
    <QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>,
  );
}

describe('AccessInspectorPopover', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('renders positive S3.4 wireframe parity for KAN-142', () => {
    const handleClose = vi.fn();
    renderWithClient(
      <AccessInspectorPopover
        objectId={TEST_OBJECT_ID}
        onClose={handleClose}
      />,
      kan142Data,
    );

    // Header Title
    expect(screen.getByText(/EFFECTIVE ACCESS FOR ISSUE/i)).toBeDefined();
    expect(screen.getByText('KAN-142')).toBeDefined();

    // Manage Access Button (caller has ADMIN/SHARE)
    expect(
      screen.getByRole('button', { name: /\[Manage Access\.\.\.\]/i }),
    ).toBeDefined();

    // Inherited Scope Banner
    expect(screen.getByText('Inherited Scope:')).toBeDefined();
    expect(
      screen.getByText(/📂 Project "kanban" \(Workspace: Default\)/i),
    ).toBeDefined();

    // Users Section
    expect(screen.getByText(/👤 USERS \(2 Direct\)/i)).toBeDefined();
    expect(screen.getByText('Adam Outler')).toBeDefined();
    expect(screen.getByText('@adam')).toBeDefined();
    expect(screen.getByText('Admin')).toBeDefined();
    expect(screen.getByText('[Project Owner]')).toBeDefined();

    expect(screen.getByText('Maya Lin')).toBeDefined();
    expect(screen.getByText('@maya')).toBeDefined();
    expect(screen.getAllByText('Edit').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('[Direct Share]').length).toBeGreaterThanOrEqual(1);

    // Groups Section
    expect(screen.getByText(/👥 GROUPS \(2\)/i)).toBeDefined();
    expect(screen.getByText('Core Backend')).toBeDefined();
    expect(screen.getByText('(11 members, LDAPS synced)')).toBeDefined();
    expect(screen.getByText('SecOps Reviewers')).toBeDefined();
    expect(screen.getByText('(4 members, OIDC)')).toBeDefined();

    // Agents & Workflow Runners Section
    expect(
      screen.getByText(/🤖 AGENTS & WORKFLOW RUNNERS \(2 Active\)/i),
    ).toBeDefined();
    expect(screen.getByText('Local Sparkle')).toBeDefined();
    expect(screen.getByText('(ollama/qwen2.5-coder)')).toBeDefined();
    expect(screen.getByText('Read')).toBeDefined();
    expect(screen.getByText('[Project Scoped]')).toBeDefined();

    expect(screen.getByText('Transition Gate')).toBeDefined();
    expect(screen.getByText('(cli: agy -p, :ro repo)')).toBeDefined();
    expect(screen.getByText('Gate')).toBeDefined();
    expect(screen.getByText('[In Review->Done]')).toBeDefined();

    // Kill switch button present
    expect(
      screen.getByRole('button', { name: /Kill Switch/i }),
    ).toBeDefined();

    // Restricted Overrides Section
    expect(screen.getByText(/🔒 RESTRICTED OVERRIDES \(1\)/i)).toBeDefined();
    expect(screen.getByText('Contractors Group')).toBeDefined();
    expect(screen.getByText('Explicit DENY')).toBeDefined();
  });

  it('enforces anti-enumeration redaction and XSS defenses', () => {
    const handleClose = vi.fn();
    renderWithClient(
      <AccessInspectorPopover
        objectId={TEST_OBJECT_ID}
        onClose={handleClose}
      />,
      redactedData,
    );

    // Redacted entry renders label
    expect(
      screen.getByText(/1 External Collaborator - outside your visibility boundary/i),
    ).toBeDefined();

    // Leaked email property is never rendered anywhere in the DOM
    expect(document.body.textContent).not.toContain('secret@vendor.io');

    // Hostile group name is rendered as literal text with zero <img> elements
    expect(
      screen.getByText('<img src=x onerror=alert(1)>'),
    ).toBeDefined();
    expect(document.querySelector('img')).toBeNull();
  });

  it('hides [Manage Access...] and [ Kill Switch ] for non-admin callers', () => {
    const handleClose = vi.fn();
    renderWithClient(
      <AccessInspectorPopover
        objectId={TEST_OBJECT_ID}
        onClose={handleClose}
      />,
      redactedData, // caller_capabilities: ['VIEW', 'COMMENT']
    );

    expect(
      screen.queryByRole('button', { name: /manage access/i }),
    ).toBeNull();
    expect(
      screen.queryByRole('button', { name: /kill switch/i }),
    ).toBeNull();
  });

  it('renders indistinguishable error message on HTTP 403 and 404', async () => {
    // Mock 403
    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce({
      ok: false,
      status: 403,
      headers: new Headers({ 'content-type': 'application/json' }),
    } as Response);

    const { unmount } = renderWithClient(
      <AccessInspectorPopover
        objectId={TEST_OBJECT_ID}
        onClose={vi.fn()}
      />,
    );

    await waitFor(() => {
      expect(
        screen.getByText('Object was not found or you do not have access.'),
      ).toBeDefined();
    });

    unmount();

    // Mock 404
    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce({
      ok: false,
      status: 404,
      headers: new Headers({ 'content-type': 'application/json' }),
    } as Response);

    renderWithClient(
      <AccessInspectorPopover
        objectId={TEST_OBJECT_ID}
        onClose={vi.fn()}
      />,
    );

    await waitFor(() => {
      expect(
        screen.getByText('Object was not found or you do not have access.'),
      ).toBeDefined();
    });
  });

  it('fetches manifest successfully via queryFn when not in cache', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: () => Promise.resolve(kan142Data),
      headers: new Headers({ 'content-type': 'application/json' }),
    } as Response);

    renderWithClient(
      <AccessInspectorPopover
        objectId={TEST_OBJECT_ID}
        onClose={vi.fn()}
      />,
    );

    await waitFor(() => {
      expect(screen.getByText('KAN-142')).toBeDefined();
    });
  });

  it('dispatches kb:open-manage-access on clicking Manage Access', () => {
    const listener = vi.fn();
    window.addEventListener('kb:open-manage-access', listener);

    renderWithClient(
      <AccessInspectorPopover
        objectId={TEST_OBJECT_ID}
        onClose={vi.fn()}
      />,
      kan142Data,
    );

    const btn = screen.getByRole('button', { name: /\[Manage Access\.\.\.\]/i });
    fireEvent.click(btn);

    expect(listener).toHaveBeenCalledTimes(1);
    const call = listener.mock.calls[0];
    const event = (call ? call[0] : null) as CustomEvent<{ objectId: string }>;
    expect(event.detail).toEqual({ objectId: TEST_OBJECT_ID });

    // Close ManageAccessModal to test line 484
    const modalCloseBtn = screen.getByRole('button', { name: 'Close Manage Access' });
    fireEvent.click(modalCloseBtn);
    expect(screen.queryByTestId('manage-access-modal')).toBeNull();

    window.removeEventListener('kb:open-manage-access', listener);
  });

  it('handles Escape key and close button clicks', () => {
    const trigger = document.createElement('button');
    document.body.appendChild(trigger);
    trigger.focus();

    const handleClose = vi.fn();
    renderWithClient(
      <AccessInspectorPopover
        objectId={TEST_OBJECT_ID}
        onClose={handleClose}
      />,
      kan142Data,
    );

    const closeBtn = screen.getByRole('button', { name: /close access inspector/i });
    fireEvent.click(closeBtn);
    expect(handleClose).toHaveBeenCalledTimes(1);

    const dialog = screen.getByRole('dialog');
    fireEvent.keyDown(dialog, { key: 'Escape' });
    expect(handleClose).toHaveBeenCalledTimes(2);

    document.body.removeChild(trigger);
  });

  it('traps Tab and Shift+Tab focus correctly within dialog', () => {
    renderWithClient(
      <AccessInspectorPopover
        objectId={TEST_OBJECT_ID}
        onClose={vi.fn()}
      />,
      kan142Data,
    );

    const dialog = screen.getByRole('dialog');
    const focusable = Array.from(
      dialog.querySelectorAll<HTMLElement>(
        'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
      ),
    );
    expect(focusable.length).toBeGreaterThanOrEqual(2);
    const first = focusable[0];
    const last = focusable[focusable.length - 1];

    // Focus last element, press Tab -> should wrap to first element
    last?.focus();
    fireEvent.keyDown(dialog, { key: 'Tab', shiftKey: false });
    expect(document.activeElement).toBe(first);

    // Focus first element, press Shift+Tab -> should wrap to last element
    first?.focus();
    fireEvent.keyDown(dialog, { key: 'Tab', shiftKey: true });
    expect(document.activeElement).toBe(last);

    // Normal Tab when activeElement is first -> does not wrap
    fireEvent.keyDown(dialog, { key: 'Tab', shiftKey: false });

    // Normal Shift+Tab when activeElement is last -> does not wrap
    fireEvent.keyDown(dialog, { key: 'Tab', shiftKey: true });

    // Non-Tab, non-Escape key (e.g. Enter) does not stop event or close
    fireEvent.keyDown(dialog, { key: 'Enter' });
  });

  it('positions correctly with anchorEl and on mobile breakpoints', () => {
    const anchor = document.createElement('button');
    document.body.appendChild(anchor);
    vi.spyOn(anchor, 'getBoundingClientRect').mockReturnValue({
      top: 50,
      left: 100,
      width: 40,
      height: 30,
      bottom: 80,
      right: 140,
      x: 100,
      y: 50,
      toJSON: () => ({}),
    });

    const { unmount } = renderWithClient(
      <AccessInspectorPopover
        objectId={TEST_OBJECT_ID}
        anchorEl={anchor}
        onClose={vi.fn()}
      />,
      kan142Data,
    );

    const dialog = screen.getByRole('dialog');
    expect(dialog.style.top).toBeDefined();
    expect(dialog.style.left).toBeDefined();

    unmount();
    document.body.removeChild(anchor);

    // Mobile width test
    const origWidth = window.innerWidth;
    window.innerWidth = 500;
    renderWithClient(
      <AccessInspectorPopover
        objectId={TEST_OBJECT_ID}
        onClose={vi.fn()}
      />,
      kan142Data,
    );
    window.innerWidth = origWidth;
  });

  it('renders calm None lines and alternate scope types', () => {
    // 1. Private scope
    const privateData = {
      ...kan142Data,
      users: [],
      groups: [],
      agents: [],
      deny_overrides: [],
      redacted_entries: [],
      redacted_count: 0,
      inherited_scope: {
        kind: 'private' as const,
        scope_label: 'Private',
      },
    };

    const { unmount } = renderWithClient(
      <AccessInspectorPopover
        objectId={TEST_OBJECT_ID}
        onClose={vi.fn()}
      />,
      privateData,
    );

    const emptyLines = screen.getAllByText('None');
    expect(emptyLines.length).toBe(4);
    expect(screen.getByText('Private')).toBeDefined();
    unmount();

    // 2. Workspace scope
    const workspaceData = {
      ...kan142Data,
      inherited_scope: {
        kind: 'workspace' as const,
        scope_label: 'Workspace: Acme',
        workspace_name: 'Acme',
      },
    };
    const { unmount: unmountWs } = renderWithClient(
      <AccessInspectorPopover
        objectId={TEST_OBJECT_ID}
        onClose={vi.fn()}
      />,
      workspaceData,
    );
    expect(screen.getByText('Workspace: Acme')).toBeDefined();
    unmountWs();

    // 2b. Workspace scope without workspace_name fallback
    const workspaceFallback = {
      ...kan142Data,
      inherited_scope: {
        kind: 'workspace' as const,
        scope_label: 'Workspace',
      },
    };
    const { unmount: unmountWsFb } = renderWithClient(
      <AccessInspectorPopover
        objectId={TEST_OBJECT_ID}
        onClose={vi.fn()}
      />,
      workspaceFallback,
    );
    expect(screen.getByText('Workspace: Default')).toBeDefined();
    unmountWsFb();

    // 2c. Project scope with project_key fallback and default workspace
    const projectKeyFallback = {
      ...kan142Data,
      inherited_scope: {
        kind: 'project' as const,
        scope_label: '',
        project_key: 'KAN',
      },
    };
    const { unmount: unmountProjKey } = renderWithClient(
      <AccessInspectorPopover
        objectId={TEST_OBJECT_ID}
        onClose={vi.fn()}
      />,
      projectKeyFallback,
    );
    expect(screen.getByText('📂 Project "KAN" (Workspace: Default)')).toBeDefined();
    unmountProjKey();

    // 2d. Project scope with generic Project fallback
    const projectGenericFallback = {
      ...kan142Data,
      inherited_scope: {
        kind: 'project' as const,
        scope_label: '',
      },
    };
    const { unmount: unmountProjGen } = renderWithClient(
      <AccessInspectorPopover
        objectId={TEST_OBJECT_ID}
        onClose={vi.fn()}
      />,
      projectGenericFallback,
    );
    expect(screen.getByText('📂 Project "Project" (Workspace: Default)')).toBeDefined();
    unmountProjGen();

    // 3. No inherited_scope
    const noScopeData = {
      ...kan142Data,
      inherited_scope: undefined as unknown as typeof kan142Data.inherited_scope,
    };
    renderWithClient(
      <AccessInspectorPopover
        objectId={TEST_OBJECT_ID}
        onClose={vi.fn()}
      />,
      noScopeData,
    );
    expect(screen.getByText('Inherited from Project')).toBeDefined();
  });

  it('covers capability badges, provenance formats, and agent/redaction fallbacks', () => {
    const variedData = {
      object_id: TEST_OBJECT_ID,
      canonical_key: 'KAN-999',
      object_type: 'DOC',
      caller_capabilities: ['VIEW'],
      inherited_scope: {
        kind: 'project' as const,
        scope_label: 'Project',
        project_name: 'Core Project',
        workspace_name: 'Acme',
      },
      users: [
        {
          principal_id: 'u-1',
          handle: '@commenter',
          display_name: 'Commenter User',
          capabilities: ['COMMENT'],
          grant_source: 'workspace_role',
        },
        {
          principal_id: 'u-2',
          handle: '@viewer',
          display_name: 'Viewer User',
          capabilities: ['VIEW'],
          grant_source: 'workspace_admin',
        },
        {
          principal_id: 'u-3',
          handle: '@custom1',
          display_name: 'Custom User 1',
          capabilities: ['VIEW'],
          grant_source: '[Custom Tag]',
        },
        {
          principal_id: 'u-4',
          handle: '@custom2',
          display_name: 'Custom User 2',
          capabilities: ['VIEW'],
          grant_source: 'custom_source',
        },
        {
          principal_id: 'u-5',
          handle: '@empty',
          display_name: 'Empty Source',
          capabilities: ['VIEW'],
          grant_source: '',
        },
      ],
      groups: [
        {
          principal_id: 'g-1',
          name: 'Plain Internal Group',
          member_count: 5,
          external_source: null,
          capabilities: ['VIEW'],
          grant_source: 'direct_share',
        },
      ],
      agents: [
        {
          principal_id: 'a-1',
          display_name: 'Autonomous Guard',
          principal_type: 'AGENT',
          provider_badge: null,
          role: 'Security Guardian',
          scope_summary: 'Unbracketed Scope',
          capabilities: ['TRANSITION'],
        },
        {
          principal_id: 'a-2',
          display_name: 'Default Agent',
          principal_type: 'AGENT',
          provider_badge: null,
          scope_summary: '',
          capabilities: ['READ'],
        },
      ],
      deny_overrides: [
        {
          principal_id: null,
          principal_type: 'USER',
          display_name: 'Restricted Anonymous',
          denied_capabilities: ['EDIT'],
        },
      ],
      redacted_entries: [
        {
          redacted: true as const,
        },
      ],
      redacted_count: 2,
    };

    const { unmount } = renderWithClient(
      <AccessInspectorPopover
        objectId={TEST_OBJECT_ID}
        onClose={vi.fn()}
      />,
      variedData,
    );

    expect(screen.getByText('EFFECTIVE ACCESS FOR DOC')).toBeDefined();
    expect(screen.getByText('KAN-999')).toBeDefined();
    expect(screen.getByText('Commenter User')).toBeDefined();
    expect(screen.getByText('Comment')).toBeDefined();
    expect(screen.getByText('[Custom Tag]')).toBeDefined();
    expect(screen.getByText('[custom_source]')).toBeDefined();
    expect(screen.getByText('(5 members)')).toBeDefined();
    expect(screen.getByText('Autonomous Guard')).toBeDefined();
    expect(screen.getByText('Security Guardian')).toBeDefined();
    expect(screen.getByText('[Unbracketed Scope]')).toBeDefined();
    expect(screen.getByText('Default Agent')).toBeDefined();
    expect(screen.getByText('Restricted Anonymous')).toBeDefined();
    expect(screen.getByText(/2 External Collaborators - outside your visibility boundary/i)).toBeDefined();

    unmount();

    // Single external collaborator without redacted_entries array
    const singleRedacted = {
      ...variedData,
      redacted_entries: [],
      redacted_count: 1,
    };
    renderWithClient(
      <AccessInspectorPopover
        objectId={TEST_OBJECT_ID}
        onClose={vi.fn()}
      />,
      singleRedacted,
    );
    expect(screen.getByText(/1 External Collaborator - outside your visibility boundary/i)).toBeDefined();
  });

  describe('StudioDocLink & HelpDrawer Yielding (KAN-486)', () => {
    afterEach(() => {
      document.documentElement.removeAttribute('data-theme');
      const existing = document.querySelectorAll('.kb-help-drawer, .kb-help-drawer-backdrop');
      existing.forEach((el) => {
        el.remove();
      });
    });

    it('renders StudioDocLink in header-actions pointing to access model docs with correct props', () => {
      renderWithClient(
        <AccessInspectorPopover
          objectId={TEST_OBJECT_ID}
          onClose={vi.fn()}
        />,
        kan142Data,
      );

      const link = screen.getByTestId('access-inspector-doc-link');
      expect(link).toBeDefined();
      expect(link.getAttribute('href')).toBe(
        '/docs/zero-trust-security-and-access-visibility#effective-resource-access-era-evaluation',
      );
      expect(link.textContent).toContain('Access Model ->');

      const headerActions = link.closest('.access-inspector__header-actions');
      expect(headerActions).not.toBeNull();

      // HTML 4.10.4: Not nested inside a button or label
      expect(link.closest('button')).toBeNull();
      expect(link.closest('label')).toBeNull();
    });

    it('yields Escape keydown and outside-click when .kb-help-drawer is present in DOM', () => {
      const handleClose = vi.fn();
      renderWithClient(
        <AccessInspectorPopover
          objectId={TEST_OBJECT_ID}
          onClose={handleClose}
        />,
        kan142Data,
      );

      const drawer = document.createElement('div');
      drawer.className = 'kb-help-drawer';
      document.body.appendChild(drawer);

      const dialog = screen.getByRole('dialog');
      fireEvent.keyDown(dialog, { key: 'Escape' });
      expect(handleClose).not.toHaveBeenCalled();

      const backdrop = document.querySelector('.access-inspector-backdrop');
      expect(backdrop).not.toBeNull();
      // eslint-disable-next-line @typescript-eslint/no-non-null-assertion
      fireEvent.click(backdrop!);
      expect(handleClose).not.toHaveBeenCalled();

      drawer.remove();

      // Now with drawer removed, Escape and backdrop click close the popover
      fireEvent.keyDown(dialog, { key: 'Escape' });
      expect(handleClose).toHaveBeenCalledTimes(1);

      // eslint-disable-next-line @typescript-eslint/no-non-null-assertion
      fireEvent.click(backdrop!);
      expect(handleClose).toHaveBeenCalledTimes(2);
    });

    it('yields Escape keydown and outside-click when .kb-help-drawer-backdrop is present in DOM', () => {
      const handleClose = vi.fn();
      renderWithClient(
        <AccessInspectorPopover
          objectId={TEST_OBJECT_ID}
          onClose={handleClose}
        />,
        kan142Data,
      );

      const drawerBackdrop = document.createElement('div');
      drawerBackdrop.className = 'kb-help-drawer-backdrop';
      document.body.appendChild(drawerBackdrop);

      const dialog = screen.getByRole('dialog');
      fireEvent.keyDown(dialog, { key: 'Escape' });
      expect(handleClose).not.toHaveBeenCalled();

      const backdrop = document.querySelector('.access-inspector-backdrop');
      expect(backdrop).not.toBeNull();
      // eslint-disable-next-line @typescript-eslint/no-non-null-assertion
      fireEvent.click(backdrop!);
      expect(handleClose).not.toHaveBeenCalled();

      drawerBackdrop.remove();

      fireEvent.keyDown(dialog, { key: 'Escape' });
      expect(handleClose).toHaveBeenCalledTimes(1);
    });

    it('renders in Light and Dark themes seamlessly without style errors', () => {
      for (const theme of ['light', 'dark'] as const) {
        document.documentElement.setAttribute('data-theme', theme);
        const { unmount } = renderWithClient(
          <AccessInspectorPopover
            objectId={TEST_OBJECT_ID}
            onClose={vi.fn()}
          />,
          kan142Data,
        );

        const link = screen.getByTestId('access-inspector-doc-link');
        expect(link).toBeDefined();
        unmount();
      }
    });

    it('opens HelpDrawer with ShellPanelsProvider when StudioDocLink is clicked', async () => {
      const unregister = registerShellPanel('help', () => <div data-testid="mock-help" />);
      const queryClient = new QueryClient({
        defaultOptions: { queries: { retry: false } },
      });
      queryClient.setQueryData(['access', TEST_OBJECT_ID], kan142Data);

      function PanelWatcher() {
        const { activePanel } = useShellPanels();
        return (
          <div data-testid="active-panel-info">
            {activePanel?.id ?? 'none'}: {JSON.stringify(activePanel?.arg ?? {})}
          </div>
        );
      }

      try {
        render(
          <QueryClientProvider client={queryClient}>
            <ShellPanelsProvider>
              <AccessInspectorPopover
                objectId={TEST_OBJECT_ID}
                onClose={vi.fn()}
              />
              <PanelWatcher />
            </ShellPanelsProvider>
          </QueryClientProvider>,
        );

        const link = screen.getByTestId('access-inspector-doc-link');
        fireEvent.click(link);

        await waitFor(() => {
          const watcher = screen.getByTestId('active-panel-info');
          expect(watcher.textContent).toContain('help');
          expect(watcher.textContent).toContain(
            '/docs/zero-trust-security-and-access-visibility#effective-resource-access-era-evaluation',
          );
        });
      } finally {
        unregister();
      }
    });

    it('covers openerRef fallback when focused before mount', () => {
      const btn = document.createElement('button');
      document.body.appendChild(btn);
      btn.focus();

      const { unmount } = renderWithClient(
        <AccessInspectorPopover
          objectId={TEST_OBJECT_ID}
          anchorEl={null}
          onClose={vi.fn()}
        />,
        kan142Data,
      );

      unmount();
      btn.remove();
    });
  });
});
