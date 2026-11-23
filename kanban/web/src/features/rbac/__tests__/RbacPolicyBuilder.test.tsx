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
    permissions: ['issue:create', 'field:modify_summary'],
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

  it('renders narrative sentence header with tier selector and sections', async () => {
    vi.spyOn(clientModule, 'apiFetch').mockImplementation((_method, path) => {
      if (path.endsWith('/api/v1/admin/rbac/roles')) {
        return Promise.resolve(MOCK_ROLES as never);
      }
      return Promise.resolve([] as never);
    });

    render(<RbacPolicyBuilder isServerAdmin={true} />);

    expect(screen.getByText('As a')).toBeDefined();
    expect(screen.getByText('I want')).toBeDefined();
    expect(screen.getByText('to have access to')).toBeDefined();

    await waitFor(() => {
      expect(screen.getByTestId('rbac-selected-role-users')).toBeDefined();
    });

    expect(screen.getByTestId('rbac-fieldset-workspace')).toBeDefined();
    expect(screen.getByTestId('rbac-fieldset-issue')).toBeDefined();
    expect(screen.getByTestId('rbac-fieldset-field')).toBeDefined();
  });

  it('locks workspace permissions and shows warning banner for workspace admin', async () => {
    vi.spyOn(clientModule, 'apiFetch').mockImplementation((_method, path) => {
      if (path.endsWith('/api/v1/admin/rbac/roles')) {
        return Promise.resolve(MOCK_ROLES as never);
      }
      return Promise.resolve([] as never);
    });

    render(<RbacPolicyBuilder isServerAdmin={false} initialRoleTier="workspace admin" />);

    await waitFor(() => {
      expect(screen.getByTestId('workspace-locked-banner')).toBeDefined();
    });

    const wsFieldset = screen.getByTestId<HTMLFieldSetElement>('rbac-fieldset-workspace');
    expect(wsFieldset.disabled).toBe(true);
  });

  it('allows toggling permissions via batch PUT call', async () => {
    const putSpy = vi.fn().mockResolvedValue({ status: 'ok' });
    vi.spyOn(clientModule, 'apiFetch').mockImplementation((method, path, opts) => {
      if (path.endsWith('/api/v1/admin/rbac/roles')) {
        return Promise.resolve(MOCK_ROLES as never);
      }
      if (path.includes('/api/v1/admin/rbac/roles/permissions:batch')) {
        return Promise.resolve(putSpy(method, path, opts) as never);
      }
      return Promise.resolve([] as never);
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

    fireEvent.click(createIssueCheckbox);

    await waitFor(() => {
      expect(putSpy).toHaveBeenCalled();
    });
  });

  it('opens create new role popover, computes slug, and creates role', async () => {
    const postSpy = vi.fn().mockResolvedValue({
      id: 'role-new',
      slug: 'lead-dev',
      name: 'Lead Dev',
      color_hex: '#3b82f6',
      permissions: [],
    });

    vi.spyOn(clientModule, 'apiFetch').mockImplementation((method, path, opts) => {
      if (path.endsWith('/api/v1/admin/rbac/roles')) {
        if (method === 'POST') {
          return Promise.resolve(postSpy(method, path, opts) as never);
        }
        return Promise.resolve(MOCK_ROLES as never);
      }
      return Promise.resolve([] as never);
    });

    render(<RbacPolicyBuilder isServerAdmin={true} />);

    await waitFor(() => {
      expect(screen.getByTestId('rbac-open-create-role')).toBeDefined();
    });

    fireEvent.click(screen.getByTestId('rbac-open-create-role'));

    expect(screen.getByTestId('rbac-create-role-popover')).toBeDefined();

    const nameInput = screen.getByTestId('rbac-new-role-name');
    fireEvent.change(nameInput, { target: { value: 'Lead Dev' } });

    const slugInput = screen.getByTestId<HTMLInputElement>('rbac-new-role-slug');
    expect(slugInput.value).toBe('lead-dev');

    fireEvent.click(screen.getByTestId('rbac-submit-create-role'));

    await waitFor(() => {
      expect(postSpy).toHaveBeenCalled();
    });
  });
});
