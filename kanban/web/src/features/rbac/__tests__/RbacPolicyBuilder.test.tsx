// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { RbacPolicyBuilder, type RbacRole } from '../RbacPolicyBuilder';
import * as clientModule from '../../../api/client';

const MOCK_ROLES: RbacRole[] = [
  {
    id: 'role-1',
    slug: 'system-admin',
    name: 'System Admin',
    color_hex: '#dc2626',
    is_system: true,
    permissions: ['workspace:create', 'issue:create', 'field:modify_summary'],
  },
  {
    id: 'role-2',
    slug: 'workspace-admin',
    name: 'Workspace Admin',
    color_hex: '#ea580c',
    is_system: true,
  },
  {
    id: 'role-3',
    slug: 'users',
    name: 'Users',
    color_hex: '#3b82f6',
    is_system: true,
    permissions: ['issue:view', 'issue:comment', 'field:modify_summary'],
  },
];

describe('RbacPolicyBuilder Component (KAN-83)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders narrative sentence header, fetches per-role permissions fallback, and selects/deselects roles', async () => {
    vi.spyOn(clientModule, 'apiFetch').mockImplementation((_method, path) => {
      if (path.endsWith('/api/v1/admin/rbac/roles')) {
        return Promise.resolve(MOCK_ROLES as never);
      }
      if (path.includes('/api/v1/admin/rbac/roles/role-2/permissions')) {
        return Promise.resolve({ permissions: ['issue:create'] } as never);
      }
      return Promise.resolve([] as never);
    });

    render(<RbacPolicyBuilder isServerAdmin={true} />);

    await waitFor(() => {
      expect(screen.getByTestId('rbac-selected-role-users')).toBeDefined();
    });

    // Switch tier selector
    fireEvent.change(screen.getByTestId('rbac-tier-select'), {
      target: { value: 'project admin' },
    });

    // Add second role from dropdown (creates indeterminate state for permissions only on one role)
    fireEvent.change(screen.getByTestId('rbac-select-role-dropdown'), {
      target: { value: 'role-1' },
    });
    expect(screen.getByTestId('rbac-selected-role-system-admin')).toBeDefined();

    // Deselect users role via chip remove button
    fireEvent.click(screen.getByLabelText('Deselect Users'));
    expect(screen.queryByTestId('rbac-selected-role-users')).toBeNull();

    // Deselect last role -> 0 roles selected
    fireEvent.click(screen.getByLabelText('Deselect System Admin'));
    expect(screen.queryByTestId('rbac-selected-role-system-admin')).toBeNull();
  });

  it('locks workspace permissions and shows warning banner for workspace admin', async () => {
    vi.spyOn(clientModule, 'apiFetch').mockImplementation((_method, path) => {
      if (path.endsWith('/api/v1/admin/rbac/roles')) {
        return Promise.resolve(MOCK_ROLES as never);
      }
      return Promise.reject(new Error('perm fetch failed'));
    });

    render(<RbacPolicyBuilder isServerAdmin={false} initialRoleTier="workspace admin" />);

    await waitFor(() => {
      expect(screen.getByTestId('workspace-locked-banner')).toBeDefined();
    });

    const wsFieldset = screen.getByTestId<HTMLFieldSetElement>('rbac-fieldset-workspace');
    expect(wsFieldset.disabled).toBe(true);
  });

  it('allows granting and revoking permissions via batch PUT call and handles errors', async () => {
    const putSpy = vi.fn().mockResolvedValue({ status: 'ok' });
    vi.spyOn(clientModule, 'apiFetch').mockImplementation((method, path, opts) => {
      if (path.endsWith('/api/v1/admin/rbac/roles')) {
        return Promise.resolve(MOCK_ROLES as never);
      }
      if (path.includes('/api/v1/admin/rbac/roles/permissions:batch')) {
        return Promise.resolve(putSpy(method, path, opts) as never);
      }
      return Promise.resolve({ permissions: [] } as never);
    });

    render(<RbacPolicyBuilder isServerAdmin={true} />);

    await waitFor(() => {
      expect(screen.getByTestId('perm-item-issue:create')).toBeDefined();
    });

    const createIssueCheckbox = screen
      .getByTestId('perm-item-issue:create')
      .querySelector('input');
    if (!createIssueCheckbox) {
      throw new Error('Checkbox not found');
    }

    // 1. Grant unchecked permission
    fireEvent.click(createIssueCheckbox);
    await waitFor(() => {
      expect(putSpy).toHaveBeenCalledTimes(1);
    });

    // 2. Revoke checked permission
    fireEvent.click(createIssueCheckbox);
    await waitFor(() => {
      expect(putSpy).toHaveBeenCalledTimes(2);
    });

    // 2b. Toggle a workspace permission and a field permission
    const wsCheckbox = screen
      .getByTestId('perm-item-workspace:create')
      .querySelector('input');
    const fieldCheckbox = screen
      .getByTestId('perm-item-field:modify_summary')
      .querySelector('input');
    if (wsCheckbox && fieldCheckbox) {
      fireEvent.click(wsCheckbox);
      fireEvent.click(fieldCheckbox);
    }

    // 3. Error branch on batch PUT (with detail and with plain empty object fallback)
    putSpy.mockRejectedValueOnce({ detail: 'Locked by tier governance' });
    fireEvent.click(createIssueCheckbox);
    await waitFor(() => {
      expect(screen.getByTestId('rbac-error-banner').textContent).toContain(
        'Locked by tier governance',
      );
    });

    putSpy.mockRejectedValueOnce({});
    fireEvent.click(createIssueCheckbox);
    await waitFor(() => {
      expect(screen.getByTestId('rbac-error-banner').textContent).toContain(
        'Failed to update permission.',
      );
    });
  });

  it('opens create new role popover, customizes slug/color/clone, creates role, and handles errors', async () => {
    const onRolesChanged = vi.fn();
    const postSpy = vi.fn().mockResolvedValue({
      id: 'role-new',
      slug: 'lead-dev',
      name: 'Lead Dev',
      color_hex: '#059669',
      permissions: [],
    });

    vi.spyOn(clientModule, 'apiFetch').mockImplementation((method, path, opts) => {
      if (path.endsWith('/api/v1/admin/rbac/roles')) {
        if (method === 'POST') {
          return Promise.resolve(postSpy(method, path, opts) as never);
        }
        return Promise.resolve(MOCK_ROLES as never);
      }
      return Promise.resolve({ permissions: [] } as never);
    });

    render(<RbacPolicyBuilder isServerAdmin={true} onRolesChanged={onRolesChanged} />);

    await waitFor(() => {
      expect(screen.getByTestId('rbac-open-create-role')).toBeDefined();
    });

    // Open and cancel popover
    fireEvent.click(screen.getByTestId('rbac-open-create-role'));
    fireEvent.click(screen.getByText('Cancel'));
    expect(screen.queryByTestId('rbac-create-role-popover')).toBeNull();

    // Open again and fill fields
    fireEvent.click(screen.getByTestId('rbac-open-create-role'));
    fireEvent.change(screen.getByTestId('rbac-new-role-name'), { target: { value: 'Lead Dev' } });
    fireEvent.change(screen.getByTestId('rbac-new-role-slug'), { target: { value: 'custom-lead' } });
    fireEvent.click(screen.getByLabelText('Select color #059669'));
    fireEvent.change(screen.getByTestId('rbac-clone-role-select'), { target: { value: '' } });

    // Error branch on create
    postSpy.mockRejectedValueOnce(new Error('Role slug already exists'));
    fireEvent.click(screen.getByTestId('rbac-submit-create-role'));
    await waitFor(() => {
      expect(screen.getByTestId('rbac-error-banner').textContent).toContain(
        'Role slug already exists',
      );
    });

    // Success branch on create
    postSpy.mockResolvedValueOnce({
      id: 'role-new',
      slug: 'custom-lead',
      name: 'Lead Dev',
      color_hex: '#059669',
      permissions: [],
    });
    fireEvent.click(screen.getByTestId('rbac-submit-create-role'));
    await waitFor(() => {
      expect(onRolesChanged).toHaveBeenCalled();
    });
  });

  it('displays error banner when loading roles fails', async () => {
    vi.spyOn(clientModule, 'apiFetch').mockRejectedValueOnce(new Error('Network offline'));
    render(<RbacPolicyBuilder isServerAdmin={true} />);
    await waitFor(() => {
      expect(screen.getByTestId('rbac-error-banner').textContent).toContain('Network offline');
    });
  });
});
