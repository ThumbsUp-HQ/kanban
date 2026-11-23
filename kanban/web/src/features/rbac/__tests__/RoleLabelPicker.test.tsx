// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { RoleLabelPicker } from '../RoleLabelPicker';
import * as clientModule from '../../../api/client';

const MOCK_ASSIGNED = [
  {
    id: 'prl-1',
    principal_id: 'user-1',
    role_id: 'role-1',
    role_name: 'Lead Dev',
    role_slug: 'lead-dev',
    role_color_hex: '#3b82f6',
  },
];

const MOCK_AVAILABLE = [
  {
    id: 'role-1',
    slug: 'lead-dev',
    name: 'Lead Dev',
    color_hex: '#3b82f6',
  },
  {
    id: 'role-2',
    slug: 'qa-tester',
    name: 'QA Tester',
    color_hex: '#10b981',
  },
];

describe('RoleLabelPicker Component (KAN-83)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders assigned role labels with color dots', async () => {
    vi.spyOn(clientModule, 'apiFetch').mockImplementation(async (method, path) => {
      if ((path as string) === '/api/v1/admin/principals/user-1/role-labels') {
        return MOCK_ASSIGNED as never;
      }
      return [] as never;
    });

    render(<RoleLabelPicker principalId="user-1" availableRoles={MOCK_AVAILABLE} />);

    await waitFor(() => {
      expect(screen.getByTestId('role-chip-lead-dev')).toBeDefined();
    });

    expect(screen.getByText('Lead Dev')).toBeDefined();
  });

  it('removes assigned role label on click', async () => {
    const deleteSpy = vi.fn().mockResolvedValue({ status: 'deleted' });
    vi.spyOn(clientModule, 'apiFetch').mockImplementation(async (method, path, opts) => {
      if ((path as string) === '/api/v1/admin/principals/user-1/role-labels') {
        if (method === 'DELETE') {
          return deleteSpy(method, path, opts) as never;
        }
        return MOCK_ASSIGNED as never;
      }
      return [] as never;
    });

    render(<RoleLabelPicker principalId="user-1" availableRoles={MOCK_AVAILABLE} />);

    await waitFor(() => {
      expect(screen.getByTestId('remove-role-lead-dev')).toBeDefined();
    });

    fireEvent.click(screen.getByTestId('remove-role-lead-dev'));

    await waitFor(() => {
      expect(deleteSpy).toHaveBeenCalled();
    });
  });

  it('adds new role label from select dropdown', async () => {
    const postSpy = vi.fn().mockResolvedValue({
      id: 'prl-2',
      principal_id: 'user-1',
      role_id: 'role-2',
      role_name: 'QA Tester',
      role_slug: 'qa-tester',
      role_color_hex: '#10b981',
    });

    vi.spyOn(clientModule, 'apiFetch').mockImplementation(async (method, path, opts) => {
      if ((path as string) === '/api/v1/admin/principals/user-1/role-labels') {
        if (method === 'POST') {
          return postSpy(method, path, opts) as never;
        }
        return MOCK_ASSIGNED as never;
      }
      return [] as never;
    });

    render(<RoleLabelPicker principalId="user-1" availableRoles={MOCK_AVAILABLE} />);

    await waitFor(() => {
      expect(screen.getByTestId('add-role-label-select')).toBeDefined();
    });

    fireEvent.change(screen.getByTestId('add-role-label-select'), {
      target: { value: 'role-2' },
    });

    await waitFor(() => {
      expect(postSpy).toHaveBeenCalled();
    });
  });
});
