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
  {
    id: 'role-4',
    slug: 'custom-no-color',
    name: 'No Color Role',
    color_hex: null as unknown as string,
    is_system: false,
    permissions: [],
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

  it('supports category bulk permission quick-selectors (Select All, Clear All, Read-Only preset)', async () => {
    const batchCalls: { permission_key: string; granted: boolean }[] = [];
    vi.spyOn(clientModule, 'apiFetch').mockImplementation((_method, path, opts) => {
      if (path.endsWith('/api/v1/admin/rbac/roles')) {
        return Promise.resolve(MOCK_ROLES as never);
      }
      if (path.includes('/api/v1/admin/rbac/roles/permissions:batch')) {
        const body = (opts as { body: { permission_key: string; granted: boolean } }).body;
        batchCalls.push(body);
        return Promise.resolve({ status: 'ok' } as never);
      }
      return Promise.resolve({ permissions: [] } as never);
    });

    render(<RbacPolicyBuilder isServerAdmin={true} />);

    await waitFor(() => {
      expect(screen.getByTestId('bulk-select-all-issue')).toBeDefined();
    });

    // 1. Select All on Issue permissions
    fireEvent.click(screen.getByTestId('bulk-select-all-issue'));
    await waitFor(() => {
      expect(batchCalls.length).toBe(10);
      expect(batchCalls.every((c) => c.granted)).toBe(true);
    });

    // 2. Clear All on Issue permissions
    batchCalls.length = 0;
    fireEvent.click(screen.getByTestId('bulk-clear-all-issue'));
    await waitFor(() => {
      expect(batchCalls.length).toBe(10);
      expect(batchCalls.every((c) => !c.granted)).toBe(true);
    });

    // 3. Read-Only on Issue permissions (issue:view true, others false)
    batchCalls.length = 0;
    fireEvent.click(screen.getByTestId('bulk-readonly-issue'));
    await waitFor(() => {
      expect(batchCalls.length).toBe(10);
      const viewCall = batchCalls.find((c) => c.permission_key === 'issue:view');
      const otherCalls = batchCalls.filter((c) => c.permission_key !== 'issue:view');
      expect(viewCall?.granted).toBe(true);
      expect(otherCalls.every((c) => !c.granted)).toBe(true);
    });

    // 4. Workspace & Field bulk selectors
    batchCalls.length = 0;
    fireEvent.click(screen.getByTestId('bulk-select-all-workspace'));
    await waitFor(() => {
      expect(batchCalls.length).toBe(8);
      expect(batchCalls.every((c) => c.granted)).toBe(true);
    });

    batchCalls.length = 0;
    fireEvent.click(screen.getByTestId('bulk-clear-all-workspace'));
    await waitFor(() => {
      expect(batchCalls.length).toBe(8);
      expect(batchCalls.every((c) => !c.granted)).toBe(true);
    });

    batchCalls.length = 0;
    fireEvent.click(screen.getByTestId('bulk-readonly-workspace'));
    await waitFor(() => {
      expect(batchCalls.length).toBe(8);
      const auditCall = batchCalls.find((c) => c.permission_key === 'workspace:audit_logs');
      const exportCall = batchCalls.find((c) => c.permission_key === 'workspace:export_data');
      expect(auditCall?.granted).toBe(true);
      expect(exportCall?.granted).toBe(true);
    });

    batchCalls.length = 0;
    fireEvent.click(screen.getByTestId('bulk-select-all-field'));
    await waitFor(() => {
      expect(batchCalls.length).toBe(12);
      expect(batchCalls.every((c) => c.granted)).toBe(true);
    });

    batchCalls.length = 0;
    fireEvent.click(screen.getByTestId('bulk-clear-all-field'));
    await waitFor(() => {
      expect(batchCalls.length).toBe(12);
      expect(batchCalls.every((c) => !c.granted)).toBe(true);
    });

    batchCalls.length = 0;
    fireEvent.click(screen.getByTestId('bulk-readonly-field'));
    await waitFor(() => {
      expect(batchCalls.length).toBe(12);
      expect(batchCalls.every((c) => !c.granted)).toBe(true);
    });

    // 5. Error handling in bulk category permissions
    vi.spyOn(clientModule, 'apiFetch').mockImplementation((_method, path) => {
      if (path.includes('/api/v1/admin/rbac/roles/permissions:batch')) {
        return Promise.reject(new Error('Batch update failed'));
      }
      return Promise.resolve({ permissions: [] } as never);
    });
    fireEvent.click(screen.getByTestId('bulk-select-all-field'));
    await waitFor(() => {
      expect(screen.getByTestId('rbac-error-banner').textContent).toContain('Batch update failed');
    });

    // 6. Aal2StepUpCancelledError in bulk category permissions (silently ignored)
    vi.spyOn(clientModule, 'apiFetch').mockImplementation((_method, path) => {
      if (path.includes('/api/v1/admin/rbac/roles/permissions:batch')) {
        return Promise.reject(new clientModule.Aal2StepUpCancelledError());
      }
      return Promise.resolve({ permissions: [] } as never);
    });
    fireEvent.click(screen.getByTestId('bulk-clear-all-field'));

    // 7. Aal2StepUpCancelledError in handleTogglePermission (silently ignored)
    const toggleSpy = vi.spyOn(clientModule, 'apiFetch').mockImplementation((_method, path) => {
      if (path.includes('/api/v1/admin/rbac/roles/permissions')) {
        return Promise.reject(new clientModule.Aal2StepUpCancelledError());
      }
      return Promise.resolve({ permissions: [] } as never);
    });
    const permCheckbox = screen.getAllByRole('checkbox')[0];
    if (permCheckbox) fireEvent.click(permCheckbox);
    await waitFor(() => {
      expect(toggleSpy).toHaveBeenCalled();
    });

    // 8. Select role-4 with null color_hex to cover color fallback
    fireEvent.change(screen.getByTestId('rbac-select-role-dropdown'), {
      target: { value: 'role-4' },
    });
    expect(screen.getByTestId('rbac-selected-role-custom-no-color')).toBeDefined();

    // 9. Dropdown change with empty string or already selected role
    fireEvent.change(screen.getByTestId('rbac-select-role-dropdown'), {
      target: { value: '' },
    });
    fireEvent.change(screen.getByTestId('rbac-select-role-dropdown'), {
      target: { value: 'role-4' },
    });

    // 10. Bulk category update with fallback error message
    class EmptyError extends Error {
      override message = undefined as unknown as string;
    }
    vi.spyOn(clientModule, 'apiFetch').mockImplementation((_method, path) => {
      if (path.includes('/api/v1/admin/rbac/roles/permissions:batch')) {
        return Promise.reject(new EmptyError());
      }
      return Promise.resolve({ permissions: [] } as never);
    });
    fireEvent.click(screen.getByTestId('bulk-select-all-field'));
    await waitFor(() => {
      expect(screen.getByTestId('rbac-error-banner').textContent).toContain('Failed to update category permissions.');
    });
  });

  it('silently ignores Aal2StepUpCancelledError on loadRoles', () => {
    vi.spyOn(clientModule, 'apiFetch').mockRejectedValueOnce(new clientModule.Aal2StepUpCancelledError());
    render(<RbacPolicyBuilder isServerAdmin={true} />);
    expect(screen.queryByTestId('rbac-error-banner')).toBeNull();
  });

  it('handles auto-slug generation and manual customization in Create Role popover', async () => {
    vi.spyOn(clientModule, 'apiFetch').mockImplementation((_method, path) => {
      if (path.endsWith('/api/v1/admin/rbac/roles')) {
        return Promise.resolve(MOCK_ROLES as never);
      }
      return Promise.resolve({ permissions: [] } as never);
    });

    render(<RbacPolicyBuilder isServerAdmin={true} />);

    await waitFor(() => {
      expect(screen.getByTestId('rbac-open-create-role')).toBeDefined();
    });

    fireEvent.click(screen.getByTestId('rbac-open-create-role'));
    const nameInput = screen.getByTestId<HTMLInputElement>('rbac-new-role-name');
    const slugInput = screen.getByTestId<HTMLInputElement>('rbac-new-role-slug');

    // Auto-slug generated from name
    fireEvent.change(nameInput, { target: { value: 'QA Lead Engineer' } });
    expect(slugInput.value).toBe('qa-lead-engineer');

    // Manual edit prevents overwrite
    fireEvent.change(slugInput, { target: { value: 'qa-specialist' } });
    fireEvent.change(nameInput, { target: { value: 'QA Lead Architect' } });
    expect(slugInput.value).toBe('qa-specialist');
  });
});
