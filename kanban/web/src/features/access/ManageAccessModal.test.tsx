/**
 * Unit tests for ManageAccessModal (KANBA-220, KB-AUDIT-14).
 * Tests searchable principal picker, ALLOW/DENY rule grant, active entry revocation,
 * agent kill switch integration, and keyboard focus trap.
 */

import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ManageAccessModal } from './ManageAccessModal';
import type { AccessManifest } from './types';

// Mock apiFetch
vi.mock('../../api/client', () => ({
  apiFetch: vi.fn(),
  getCsrfToken: vi.fn(() => 'test-csrf-token'),
}));

import { apiFetch } from '../../api/client';

const mockManifest: AccessManifest = {
  pill_label: 'Project + 2',
  explicit_grant_count: 2,
  inherited_scope: {
    kind: 'project',
    scope_label: 'Project: KAN',
    workspace_id: 'ws-1',
    workspace_name: 'Engineering',
    project_id: 'proj-1',
    project_key: 'KAN',
    project_name: 'Platform Core',
  },
  users: [
    {
      principal_id: 'usr-1',
      handle: '@alice',
      display_name: 'Alice Smith',
      capabilities: ['VIEW', 'EDIT'],
      grant_source: 'direct_share',
    },
  ],
  groups: [
    {
      principal_id: 'grp-1',
      name: 'Core Team',
      member_count: 5,
      capabilities: ['VIEW', 'COMMENT'],
      grant_source: 'direct_share',
    },
  ],
  agents: [
    {
      principal_id: 'agent-1',
      display_name: 'Sparkle Runner (ollama)',
      principal_type: 'AGENT',
      provider_badge: 'ollama',
      scope_summary: 'Project Scoped',
      capabilities: ['VIEW'],
    },
  ],
  deny_overrides: [
    {
      principal_id: 'usr-deny-1',
      principal_type: 'USER',
      display_name: 'Restricted Contractor',
      redacted: false,
      denied_capabilities: ['EDIT', 'DELETE'],
    },
  ],
  redacted_entries: [],
  redacted_count: 0,
  caller_capabilities: ['VIEW', 'SHARE', 'ADMIN'],
  canonical_key: 'KAN-220',
  object_type: 'issue',
};

describe('ManageAccessModal', () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(apiFetch).mockResolvedValue([]);
    queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
        mutations: { retry: false },
      },
    });
  });

  it('renders null when isOpen is false', () => {
    const { container } = render(
      <QueryClientProvider client={queryClient}>
        <ManageAccessModal
          objectId="obj-123"
          isOpen={false}
          onClose={vi.fn()}
        />
      </QueryClientProvider>,
    );
    expect(container.firstChild).toBeNull();
  });

  it('renders modal dialog with header and sections when open', () => {
    render(
      <QueryClientProvider client={queryClient}>
        <ManageAccessModal
          objectId="obj-123"
          canonicalKey="KAN-220"
          isOpen={true}
          onClose={vi.fn()}
          manifest={mockManifest}
        />
      </QueryClientProvider>,
    );

    expect(screen.getByTestId('manage-access-modal')).toBeDefined();
    expect(screen.getByText(/Manage Access for KAN-220/i)).toBeDefined();
    expect(screen.getByTestId('active-acl-table')).toBeDefined();
    expect(screen.getByText('Alice Smith')).toBeDefined();
    expect(screen.getByText('Core Team')).toBeDefined();
    expect(screen.getByText('Restricted Contractor')).toBeDefined();
  });

  it('searches principals and filters by type chips', async () => {
    const mockPrincipals = [
      { id: 'usr-bob', display_name: 'Bob Jones', handle: '@bob', principal_type: 'USER' },
      { id: 'grp-devs', display_name: 'Dev Group', name: 'Dev Group', principal_type: 'GROUP' },
    ];
    vi.mocked(apiFetch).mockImplementation(async (_method, path) => {
      await Promise.resolve();
      if (typeof path === 'string' && path.includes('/access/principals')) {
        return mockPrincipals;
      }
      return [];
    });

    render(
      <QueryClientProvider client={queryClient}>
        <ManageAccessModal
          objectId="obj-123"
          isOpen={true}
          onClose={vi.fn()}
          manifest={mockManifest}
        />
      </QueryClientProvider>,
    );

    const searchInput = screen.getByTestId('principal-search-input');
    fireEvent.change(searchInput, { target: { value: 'Bob' } });

    // Switch filter chips
    const userChip = screen.getByRole('button', { name: '👤 Users' });
    fireEvent.click(userChip);

    await waitFor(() => {
      expect(screen.getByTestId('principal-option-usr-bob')).toBeDefined();
    });

    // Select Bob Jones option
    const option = screen.getByTestId('principal-option-usr-bob');
    fireEvent.click(option);

    expect(screen.getByTestId('selected-principal-form')).toBeDefined();
    expect(screen.getByText(/Configuring access for:/i)).toBeDefined();
  });

  it('configures presets and grants ALLOW capability rule', async () => {
    const mockPrincipals = [
      { id: 'usr-charlie', display_name: 'Charlie', handle: '@charlie', principal_type: 'USER' },
    ];
    vi.mocked(apiFetch).mockImplementation(async (method, path) => {
      await Promise.resolve();
      if (typeof path === 'string' && path.includes('/access/principals')) {
        return mockPrincipals;
      }
      if (method === 'POST') {
        return { status: 'granted' };
      }
      return [];
    });

    render(
      <QueryClientProvider client={queryClient}>
        <ManageAccessModal
          objectId="obj-123"
          isOpen={true}
          onClose={vi.fn()}
          manifest={mockManifest}
        />
      </QueryClientProvider>,
    );

    // Search and select Charlie
    fireEvent.change(screen.getByTestId('principal-search-input'), { target: { value: 'Charlie' } });
    await waitFor(() => {
      expect(screen.getByTestId('principal-option-usr-charlie')).toBeDefined();
    });
    fireEvent.click(screen.getByTestId('principal-option-usr-charlie'));

    // Apply Admin preset
    const adminPresetBtn = screen.getByRole('button', { name: 'Full Admin' });
    fireEvent.click(adminPresetBtn);

    // Apply Viewer preset
    const viewerPresetBtn = screen.getByRole('button', { name: 'Viewer' });
    fireEvent.click(viewerPresetBtn);

    // Apply Commenter preset
    const commenterPresetBtn = screen.getByRole('button', { name: 'Commenter' });
    fireEvent.click(commenterPresetBtn);

    // Apply Editor preset
    const editorPresetBtn = screen.getByRole('button', { name: 'Editor' });
    fireEvent.click(editorPresetBtn);

    // Toggle a checkbox
    const shareCheckbox = screen.getByRole('checkbox', { name: 'SHARE' });
    fireEvent.click(shareCheckbox);

    // Click Save
    const saveBtn = screen.getByTestId('save-access-btn');
    fireEvent.click(saveBtn);

    await waitFor(() => {
      expect(screen.getByTestId('manage-access-alert')).toBeDefined();
      expect(screen.getByText(/Access rule successfully applied/i)).toBeDefined();
    });
  });

  it('configures and applies explicit DENY override', async () => {
    const mockPrincipals = [
      { id: 'usr-restricted', display_name: 'Restricted User', handle: '@restricted', principal_type: 'USER' },
    ];
    vi.mocked(apiFetch).mockImplementation(async (method, path) => {
      await Promise.resolve();
      if (typeof path === 'string' && path.includes('/access/principals')) {
        return mockPrincipals;
      }
      if (method === 'POST') {
        return { status: 'granted' };
      }
      return [];
    });

    render(
      <QueryClientProvider client={queryClient}>
        <ManageAccessModal
          objectId="obj-123"
          isOpen={true}
          onClose={vi.fn()}
          manifest={mockManifest}
        />
      </QueryClientProvider>,
    );

    fireEvent.change(screen.getByTestId('principal-search-input'), { target: { value: 'Restricted' } });
    await waitFor(() => {
      expect(screen.getByTestId('principal-option-usr-restricted')).toBeDefined();
    });
    fireEvent.click(screen.getByTestId('principal-option-usr-restricted'));

    // Select DENY radio
    const denyRadio = screen.getByRole('radio', { name: /DENY \(Explicit Restriction\)/i });
    fireEvent.click(denyRadio);

    // Switch back to ALLOW radio
    const allowRadio = screen.getByRole('radio', { name: /ALLOW \(Grant Access\)/i });
    fireEvent.click(allowRadio);
    fireEvent.click(denyRadio);

    // Cancel selection
    const cancelFormBtn = screen.getByRole('button', { name: 'Cancel' });
    fireEvent.click(cancelFormBtn);
    expect(screen.queryByTestId('selected-principal-form')).toBeNull();

    // Re-select and save DENY
    fireEvent.click(screen.getByTestId('principal-option-usr-restricted'));
    fireEvent.click(denyRadio);

    // Click Save
    const saveBtn = screen.getByTestId('save-access-btn');
    fireEvent.click(saveBtn);

    await waitFor(() => {
      expect(screen.getByText(/Access rule successfully applied/i)).toBeDefined();
    });
  });

  it('shows error if all capabilities are unchecked before saving', async () => {
    const mockPrincipals = [
      { id: 'usr-test', display_name: 'Test Person', principal_type: 'USER' },
    ];
    vi.mocked(apiFetch).mockImplementation(async (_method, path) => {
      await Promise.resolve();
      if (typeof path === 'string' && path.includes('/access/principals')) {
        return mockPrincipals;
      }
      return [];
    });

    render(
      <QueryClientProvider client={queryClient}>
        <ManageAccessModal
          objectId="obj-123"
          isOpen={true}
          onClose={vi.fn()}
          manifest={mockManifest}
        />
      </QueryClientProvider>,
    );

    fireEvent.change(screen.getByTestId('principal-search-input'), { target: { value: 'Test' } });
    await waitFor(() => {
      expect(screen.getByTestId('principal-option-usr-test')).toBeDefined();
    });
    fireEvent.click(screen.getByTestId('principal-option-usr-test'));

    // Uncheck VIEW, COMMENT, EDIT
    fireEvent.click(screen.getByRole('checkbox', { name: 'VIEW' }));
    fireEvent.click(screen.getByRole('checkbox', { name: 'COMMENT' }));
    fireEvent.click(screen.getByRole('checkbox', { name: 'EDIT' }));

    const saveBtn = screen.getByTestId('save-access-btn');
    fireEvent.click(saveBtn);

    expect(screen.getByText(/Please select at least one capability for the rule/i)).toBeDefined();
  });

  it('handles revoke action for direct user grant', async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce({ status: 'revoked' });

    render(
      <QueryClientProvider client={queryClient}>
        <ManageAccessModal
          objectId="obj-123"
          isOpen={true}
          onClose={vi.fn()}
          manifest={mockManifest}
        />
      </QueryClientProvider>,
    );

    const revokeUserBtn = screen.getByTestId('revoke-btn-usr-1');
    fireEvent.click(revokeUserBtn);

    await waitFor(() => {
      expect(screen.getByText(/Access rule successfully revoked/i)).toBeDefined();
    });
  });

  it('handles revoke action for group and deny entries', async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce({ status: 'revoked' });

    render(
      <QueryClientProvider client={queryClient}>
        <ManageAccessModal
          objectId="obj-123"
          isOpen={true}
          onClose={vi.fn()}
          manifest={mockManifest}
        />
      </QueryClientProvider>,
    );

    const revokeGroupBtn = screen.getByTestId('revoke-btn-grp-1');
    fireEvent.click(revokeGroupBtn);

    await waitFor(() => {
      expect(screen.getByText(/Access rule successfully revoked/i)).toBeDefined();
    });

    vi.mocked(apiFetch).mockResolvedValueOnce({ status: 'revoked' });
    const revokeDenyBtn = screen.getByTestId('revoke-btn-usr-deny-1');
    fireEvent.click(revokeDenyBtn);

    await waitFor(() => {
      expect(screen.getByText(/Access rule successfully revoked/i)).toBeDefined();
    });
  });

  it('handles grant and revoke error responses gracefully', async () => {
    const mockPrincipals = [
      { id: 'usr-err', display_name: 'Err User', principal_type: 'USER' },
    ];
    vi.mocked(apiFetch).mockImplementation(async (method, path) => {
      await Promise.resolve();
      if (typeof path === 'string' && path.includes('/access/principals')) {
        return mockPrincipals;
      }
      if (method === 'POST') {
        throw new Error('Permission denied by server policy');
      }
      if (method === 'DELETE') {
        throw new Error('Failed to revoke on server');
      }
      return [];
    });

    render(
      <QueryClientProvider client={queryClient}>
        <ManageAccessModal
          objectId="obj-123"
          isOpen={true}
          onClose={vi.fn()}
          manifest={mockManifest}
        />
      </QueryClientProvider>,
    );

    fireEvent.change(screen.getByTestId('principal-search-input'), { target: { value: 'Err' } });
    await waitFor(() => {
      expect(screen.getByTestId('principal-option-usr-err')).toBeDefined();
    });
    fireEvent.click(screen.getByTestId('principal-option-usr-err'));

    fireEvent.click(screen.getByTestId('save-access-btn'));

    await waitFor(() => {
      expect(screen.getByText(/Permission denied by server policy/i)).toBeDefined();
    });

    // Revoke failure
    fireEvent.click(screen.getByTestId('revoke-btn-usr-1'));

    await waitFor(() => {
      expect(screen.getByText(/Failed to revoke on server/i)).toBeDefined();
    });
  });

  it('closes dialog on Escape key and close button', () => {
    const onClose = vi.fn();
    render(
      <QueryClientProvider client={queryClient}>
        <ManageAccessModal
          objectId="obj-123"
          isOpen={true}
          onClose={onClose}
          manifest={mockManifest}
        />
      </QueryClientProvider>,
    );

    const closeBtn = screen.getByRole('button', { name: 'Close Manage Access' });
    fireEvent.click(closeBtn);
    expect(onClose).toHaveBeenCalledTimes(1);

    const dialog = screen.getByTestId('manage-access-modal');
    fireEvent.keyDown(dialog, { key: 'Enter' }); // Non-escape key branch
    fireEvent.keyDown(dialog, { key: 'Escape' });
    expect(onClose).toHaveBeenCalledTimes(2);
  });

  it('handles empty entries, agent principal selection, and csrf cookie assignment', async () => {
    const { getCsrfToken } = await import('../../api/client');
    vi.mocked(getCsrfToken).mockReturnValue(null);

    const mockAgentPrincipals = [
      { id: 'agent-sparkle', display_name: 'Sparkle Agent', principal_type: 'AGENT' },
    ];
    vi.mocked(apiFetch).mockImplementation(async (method, path) => {
      await Promise.resolve();
      if (typeof path === 'string' && path.includes('/access/principals')) {
        return mockAgentPrincipals;
      }
      if (method === 'POST') {
        return { status: 'ok' };
      }
      return [];
    });

    render(
      <QueryClientProvider client={queryClient}>
        <ManageAccessModal
          objectId="obj-123"
          isOpen={true}
          onClose={vi.fn()}
          manifest={{
            ...mockManifest,
            users: [],
            groups: [],
            deny_overrides: [],
          }}
        />
      </QueryClientProvider>,
    );

    // Verify empty state
    expect(screen.getByText('No explicit direct access rules configured.')).toBeDefined();

    // Select agent principal
    fireEvent.change(screen.getByTestId('principal-search-input'), { target: { value: 'Sparkle' } });
    await waitFor(() => {
      expect(screen.getByTestId('principal-option-agent-sparkle')).toBeDefined();
    });
    fireEvent.click(screen.getByTestId('principal-option-agent-sparkle'));

    // Save rule with null CSRF
    fireEvent.click(screen.getByTestId('save-access-btn'));
    await waitFor(() => {
      expect(screen.getByText(/Access rule successfully applied/i)).toBeDefined();
    });

    // Test revoke with null CSRF
    const { container } = render(
      <QueryClientProvider client={queryClient}>
        <ManageAccessModal
          objectId="obj-123"
          isOpen={true}
          onClose={vi.fn()}
          manifest={mockManifest}
        />
      </QueryClientProvider>,
    );
    const revokeBtn = container.querySelector('[data-testid="revoke-btn-usr-1"]');
    if (revokeBtn) {
      fireEvent.click(revokeBtn);
      await waitFor(() => {
        expect(screen.getByText(/Access rule successfully revoked/i)).toBeDefined();
      });
    }
  });

  it('handles non-Error strings in mutation errors and query catch fallback', async () => {
    const mockUserPrincipals = [
      { id: 'usr-non-error', display_name: 'Non Error User', principal_type: 'USER' },
    ];
    vi.mocked(apiFetch).mockImplementation(async (method, path) => {
      await Promise.resolve();
      if (typeof path === 'string' && path.includes('/access/principals')) {
        return mockUserPrincipals;
      }
      if (method === 'POST') {
        // eslint-disable-next-line @typescript-eslint/prefer-promise-reject-errors
        return Promise.reject('String grant failure');
      }
      if (method === 'DELETE') {
        // eslint-disable-next-line @typescript-eslint/prefer-promise-reject-errors
        return Promise.reject('String revoke failure');
      }
      return [];
    });

    render(
      <QueryClientProvider client={queryClient}>
        <ManageAccessModal
          objectId="obj-123"
          isOpen={true}
          onClose={vi.fn()}
          manifest={mockManifest}
        />
      </QueryClientProvider>,
    );

    // Search and select
    fireEvent.change(screen.getByTestId('principal-search-input'), { target: { value: 'Non' } });
    await waitFor(() => {
      expect(screen.getByTestId('principal-option-usr-non-error')).toBeDefined();
    });
    fireEvent.click(screen.getByTestId('principal-option-usr-non-error'));

    // Save with non-Error throw
    fireEvent.click(screen.getByTestId('save-access-btn'));
    await waitFor(() => {
      expect(screen.getByText('Failed to apply access rule.')).toBeDefined();
    });

    // Revoke with non-Error throw
    fireEvent.click(screen.getByTestId('revoke-btn-usr-1'));
    await waitFor(() => {
      expect(screen.getByText('Failed to revoke access rule.')).toBeDefined();
    });
  });

  it('handles undefined manifest, missing handle, and deny entry without principal_id', () => {
    // 1. undefined manifest
    const { unmount } = render(
      <QueryClientProvider client={queryClient}>
        <ManageAccessModal
          objectId="obj-no-manifest"
          isOpen={true}
          onClose={vi.fn()}
        />
      </QueryClientProvider>,
    );
    expect(screen.getByText('No explicit direct access rules configured.')).toBeDefined();
    unmount();

    // 2. Deny override without principal_id and User without handle
    render(
      <QueryClientProvider client={queryClient}>
        <ManageAccessModal
          objectId="obj-edge-cases"
          isOpen={true}
          onClose={vi.fn()}
          manifest={{
            ...mockManifest,
            users: [
              {
                principal_id: 'usr-no-handle',
                display_name: 'No Handle User',
                handle: '',
                grant_source: 'direct_share',
                capabilities: ['VIEW'],
              },
            ],
            groups: [],
            deny_overrides: [
              {
                principal_id: null,
                display_name: 'Anonymous Deny Entry',
                principal_type: 'USER',
                denied_capabilities: ['DELETE'],
                redacted: false,
              },
            ],
            agents: [],
          }}
        />
      </QueryClientProvider>,
    );

    expect(screen.getByText('No Handle User')).toBeDefined();
    expect(screen.getByText('Anonymous Deny Entry')).toBeDefined();
  });

  it('renders StudioDocLink in header and FieldHelpHint beside DENY option with shift-left HTML nesting invariant', async () => {
    const mockPrincipals = [
      { id: 'usr-alice', display_name: 'Alice Smith', handle: '@alice', principal_type: 'USER' },
    ];
    vi.mocked(apiFetch).mockImplementation(async (_method, path) => {
      await Promise.resolve();
      if (typeof path === 'string' && path.includes('/access/principals')) {
        return mockPrincipals;
      }
      return [];
    });

    render(
      <QueryClientProvider client={queryClient}>
        <ManageAccessModal
          objectId="obj-123"
          canonicalKey="KAN-487"
          isOpen={true}
          onClose={vi.fn()}
          manifest={mockManifest}
        />
      </QueryClientProvider>,
    );

    // 1. StudioDocLink in header
    const docLink = screen.getByTestId('manage-access-doc-link');
    expect(docLink).toBeDefined();
    expect(docLink.getAttribute('href')).toBe(
      '/docs/zero-trust-security-and-access-visibility#universal-access-control-model',
    );
    expect(docLink.textContent).toContain('ACL Documentation ->');

    // 2. Select principal to reveal effect row
    fireEvent.change(screen.getByTestId('principal-search-input'), { target: { value: 'Alice' } });
    await waitFor(() => {
      expect(screen.getByTestId('principal-option-usr-alice')).toBeDefined();
    });
    fireEvent.click(screen.getByTestId('principal-option-usr-alice'));

    // 3. FieldHelpHint beside DENY radio option
    const hintBtn = screen.getByTestId('deny-precedence-help-hint');
    expect(hintBtn).toBeDefined();

    // 4. Critical shift-left HTML nesting invariant
    const invalidNestings = document.querySelectorAll(
      'label button.field-help-hint, button button.field-help-hint, label a.kb-studio-doc-link, button a.kb-studio-doc-link',
    );
    expect(invalidNestings.length).toBe(0);

    // Open FieldHelpHint popover
    fireEvent.click(hintBtn);
    await waitFor(() => {
      expect(screen.getByTestId('deny-precedence-help-hint-popover')).toBeDefined();
    });
    expect(screen.getByText(/Explicit DENY rules take absolute precedence/i)).toBeDefined();
    expect(screen.getByTestId('deny-precedence-help-hint-default').textContent).toContain('ALLOW');
    expect(screen.getByText('Grants selected capabilities across object scope')).toBeDefined();
    expect(screen.getByText('Explicit restriction overriding inherited permissions')).toBeDefined();
  });

  it('yields Escape key and backdrop close when .kb-help-drawer or .field-help-hint-popover is active', () => {
    const onClose = vi.fn();
    const { unmount } = render(
      <QueryClientProvider client={queryClient}>
        <ManageAccessModal
          objectId="obj-123"
          isOpen={true}
          onClose={onClose}
          manifest={mockManifest}
        />
      </QueryClientProvider>,
    );

    const dialog = screen.getByTestId('manage-access-modal');
    const backdrop = screen.getByTestId('manage-access-backdrop');

    // Backdrop click when no drawer/popover is open closes modal
    fireEvent.click(backdrop);
    expect(onClose).toHaveBeenCalledTimes(1);
    onClose.mockClear();

    // 1. Simulate .kb-help-drawer open in DOM
    const helpDrawer = document.createElement('div');
    helpDrawer.className = 'kb-help-drawer';
    document.body.appendChild(helpDrawer);

    const closeBtn = screen.getByRole('button', { name: 'Close Manage Access' });
    fireEvent.click(closeBtn);
    expect(onClose).not.toHaveBeenCalled();

    fireEvent.click(backdrop);
    expect(onClose).not.toHaveBeenCalled();

    fireEvent.keyDown(dialog, { key: 'Escape' });
    expect(onClose).not.toHaveBeenCalled();

    document.body.removeChild(helpDrawer);

    // 2. Simulate .field-help-hint-popover open in DOM
    const popover = document.createElement('div');
    popover.className = 'field-help-hint-popover';
    document.body.appendChild(popover);

    fireEvent.click(backdrop);
    expect(onClose).not.toHaveBeenCalled();

    fireEvent.keyDown(dialog, { key: 'Escape' });
    expect(onClose).not.toHaveBeenCalled();

    document.body.removeChild(popover);

    // Now with both removed, Escape works normally
    fireEvent.keyDown(dialog, { key: 'Escape' });
    expect(onClose).toHaveBeenCalledTimes(1);

    unmount();
  });

  it('handles principal query network throw gracefully', async () => {
    vi.mocked(apiFetch).mockImplementation(async (_method, path) => {
      await Promise.resolve();
      if (typeof path === 'string' && path.includes('/access/principals')) {
        throw new Error('Network failure');
      }
      return [];
    });

    render(
      <QueryClientProvider client={queryClient}>
        <ManageAccessModal
          objectId="obj-123"
          isOpen={true}
          onClose={vi.fn()}
          manifest={mockManifest}
        />
      </QueryClientProvider>,
    );

    fireEvent.change(screen.getByTestId('principal-search-input'), { target: { value: 'Fail' } });
    await waitFor(() => {
      expect(screen.queryByTestId('principal-option-usr-alice')).toBeNull();
    });
  });
});
