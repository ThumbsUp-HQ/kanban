// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router';
import { ProjectSettingsPage } from '../ProjectSettingsPage';
import * as clientModule from '../../../api/client';

describe('ProjectSettingsPage (KANBA-202)', () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
      },
    });
    vi.clearAllMocks();
  });

  const renderComponent = (projectKey = 'KAN') =>
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={[`/projects/${projectKey}/settings`]}>
          <ProjectSettingsPage />
        </MemoryRouter>
      </QueryClientProvider>,
    );

  it('renders project settings page tabs and switches between them', async () => {
    vi.spyOn(clientModule, 'apiFetch').mockImplementation(async (method, path) => {
      await Promise.resolve();
      const url = path;
      if (url.includes('/api/v1/projects/KAN/members')) {
        return [
          {
            id: 'member-1',
            principal_id: 'user-1',
            principal_type: 'USER',
            role: 'PROJECT_ADMIN',
            display_name: 'Alice Admin',
            handle: 'alice',
            avatar_url: null,
          },
        ];
      }
      if (url.includes('/api/v1/projects/KAN')) {
        return {
          id: 'p-1',
          identifier: 'KAN',
          name: 'Kanban Platform',
          description: 'Primary platform project',
          modules_enabled: true,
          is_project_admin: true,
        };
      }
      return {};
    });

    renderComponent('KAN');

    expect(await screen.findByTestId('project-settings-page')).toBeDefined();
    expect(screen.getByRole('heading', { level: 1 })).toBeDefined();

    // Verify tabs
    const generalTab = screen.getByTestId('tab-general');
    const membersTab = screen.getByTestId('tab-members');
    const integrationsTab = screen.getByTestId('tab-integrations');
    const dangerTab = screen.getByTestId('tab-danger');

    expect(generalTab).toBeDefined();
    expect(membersTab).toBeDefined();
    expect(integrationsTab).toBeDefined();
    expect(dangerTab).toBeDefined();

    // General tab content
    expect(await screen.findByDisplayValue('Kanban Platform')).toBeDefined();

    // Switch to Members & Access
    fireEvent.click(membersTab);
    expect(await screen.findByText('Alice Admin')).toBeDefined();

    // Switch to Automation & Integrations
    fireEvent.click(integrationsTab);
    expect(screen.getByText('Workflows & States')).toBeDefined();

    // Switch to Danger Zone
    fireEvent.click(dangerTab);
    expect(screen.getByText('Move Project to Trash')).toBeDefined();
    expect(screen.getByTestId('request-delete-btn')).toBeDefined();
  });

  it('allows adding and removing project members with role selection', async () => {
    let membersList = [
      {
        id: 'member-1',
        principal_id: 'user-1',
        principal_type: 'USER',
        role: 'PROJECT_ADMIN',
        display_name: 'Alice Admin',
        handle: 'alice',
        avatar_url: null,
      },
    ];

    vi.spyOn(clientModule, 'apiFetch').mockImplementation(async (method, path, options) => {
      await Promise.resolve();
      const url = path;
      const m = method.toUpperCase();

      if (url.includes('/api/v1/projects/KAN/members') && m === 'GET') {
        return membersList;
      }
      if (url.includes('/api/v1/projects/KAN/members') && m === 'POST') {
        const body = JSON.parse(String((options as { body?: string }).body)) as { principal_id: string; role: string };
        const newMember = {
          id: 'member-2',
          principal_id: body.principal_id,
          principal_type: 'USER',
          role: body.role,
          display_name: 'Bob Builder',
          handle: 'bob',
          avatar_url: null,
        };
        membersList = [...membersList, newMember];
        return newMember;
      }
      if (url.includes('/api/v1/projects/KAN/members/') && m === 'DELETE') {
        membersList = membersList.filter((mem) => !url.includes(mem.principal_id));
        return {};
      }
      if (url.includes('/api/v1/projects/KAN')) {
        return {
          id: 'p-1',
          identifier: 'KAN',
          name: 'Kanban Platform',
          is_project_admin: true,
        };
      }
      return {};
    });

    renderComponent('KAN');

    // Switch to members tab
    const membersTab = await screen.findByTestId('tab-members');
    fireEvent.click(membersTab);

    expect(await screen.findByText('Alice Admin')).toBeDefined();

    // Add member
    const input = screen.getByTestId('member-principal-id-input');
    fireEvent.change(input, { target: { value: 'user-2' } });

    const roleSelect = screen.getByTestId('member-role-select');
    fireEvent.change(roleSelect, { target: { value: 'VIEWER' } });

    const addBtn = screen.getByTestId('add-member-submit-btn');
    fireEvent.click(addBtn);

    await waitFor(() => {
      expect(screen.getByText('Bob Builder')).toBeDefined();
    });

    // Remove member
    const removeBtn = screen.getByTestId('remove-member-user-2');
    fireEvent.click(removeBtn);

    await waitFor(() => {
      expect(screen.queryByText('Bob Builder')).toBeNull();
    });
  });
});
